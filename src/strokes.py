"""Stroke-based contour editor: strokes -> 5-zone trimap -> marker solver -> polygon (pure, no I/O).

The user does not drag vertices; they paint over the editor crop (``src.overrides.crop_window``,
the piece bbox + 3 mm, origin ``origem`` in scan px). A **stroke** is a dict, in CROP px::

	{"ferramenta": "laco" | "pincel" | "borracha",
	 "marca": "peca" | "fundo" | "incerto" | None,      # None (or absent) only for "borracha"
	 "raio_px": float,                                   # brush / eraser radius; ignored by "laco"
	 "pontos": [[x, y], ...]}

``laco`` fills the closed polygon of its points with the mark; ``pincel`` paints the polyline with
thickness ``2 raio_px`` (round caps; a single point is a disc); ``borracha`` paints "unmarked" with
the brush geometry. Strokes apply in order, each over the previous ones; undo / redo is the client
sending a prefix of its list.

**Trimap** (:func:`trimap`, uint8): from the current contour of the piece (``auto_mask``), the
interior eroded by :data:`BANDA_MM` is "probable piece", the exterior beyond the contour dilated by
:data:`BANDA_MM` is "probable background", the band between them is "uncertain". The strokes then
overwrite: ``peca`` -> certain piece, ``fundo`` -> certain background, ``incerto`` -> uncertain.
Codes: :data:`FUNDO_CERTO` 0, :data:`FUNDO_PROV` 1, :data:`INCERTO` 2, :data:`PECA_PROV` 3,
:data:`PECA_CERTA` 4.

**Solvers** (:data:`SOLVERS`, same signature ``(rgb_crop, tri, mm_per_px, bg_lab=None, **params) ->
bool mask``) decide the *free* zone: the uncertain pixels plus the probable ones within
``alcance_mm`` of them (:func:`dominio`); certain pixels and probable ones farther away are fixed.
``grabcut`` (``cv2.grabCut`` with the trimap as mask), ``watershed`` (``cv2.watershed`` from the fixed
markers, over the smoothed colour image or the black-hat(L*) + Lab-gradient relief of the contact
watershed, or the exact priority flood of that relief) and ``limiar`` (the segmenter's
``sqrt(0.5 dL^2 + da^2 + db^2) > 28`` against the scan background; the baseline).
:func:`limpar` closes / opens by :data:`LIMPEZA_MM`, re-imposes the certain marks, keeps the largest
component and fills holes; :func:`mascara_poligono` returns the outer pixel chain.
:func:`resolver` chains it all. Measured against two hand-cut masks in
``docs/diagnostico/editor/TRACOS.md`` (choice of :data:`SOLVER_OMISSAO` and of the constants).

The RLE (:func:`rle_encode` / :func:`rle_decode`) is row-major, runs alternating background /
piece and starting with background (a first run of 0 when the first pixel is piece).
"""

import time
from typing import Optional

import cv2
import numpy as np

__all__ = [
	"FUNDO_CERTO", "FUNDO_PROV", "INCERTO", "PECA_PROV", "PECA_CERTA", "MARCAS", "FERRAMENTAS",
	"BANDA_MM", "LIMPEZA_MM", "SOLVER_OMISSAO", "SOLVER_PARAMS", "SOLVERS", "MAX_TRACOS", "MAX_PONTOS",
	"MAX_RAIO_PX",
	"parametros", "validar_tracos", "traduzir_tracos", "rasterizar_tracos", "trimap", "dominio",
	"solve_grabcut", "solve_watershed", "solve_limiar", "limpar", "mascara_poligono", "resolver",
	"rle_encode", "rle_decode",
]

FUNDO_CERTO, FUNDO_PROV, INCERTO, PECA_PROV, PECA_CERTA = 0, 1, 2, 3, 4
MARCAS = {"peca": PECA_CERTA, "fundo": FUNDO_CERTO, "incerto": INCERTO}
FERRAMENTAS = ("laco", "pincel", "borracha")
BANDA_MM = 1.0          # half-width of the uncertain band around the current contour (TRACOS.md §3)
LIMPEZA_MM = 0.3        # closing / opening of the solved mask (kernel side, odd px)
MAX_TRACOS = 2000       # payload guards
MAX_PONTOS = 200000
MAX_RAIO_PX = 500.0
_NAO_MARCADO = -1

# Default parameters of each solver (the caller's ``params`` override them; unknown keys are an error).
# Chosen on the R0011/R0012 hand-cut masks (TRACOS.md §2): chroma only (Lab, L* weight 0) because the
# cast shadow has the paper's hue and the lit rim the piece's; 2 GrabCut iterations = 3 or 5 in quality.
SOLVER_PARAMS = {
	"grabcut": {"iters": 2, "alcance_mm": 1.0, "incerto": "perto", "janela": "livre", "espaco": "lab", "peso_l": 0.0,
				"limiar": 0.0},
	"watershed": {"alcance_mm": 1.0, "paisagem": "cor", "suave_px": 1.0, "espaco": "lab", "peso_l": 0.0},
	"limiar": {"alcance_mm": 0.0, "limiar": 28.0, "abertura_mm": 0.42, "peso_l": 0.5},
}
SOLVER_OMISSAO = "grabcut"


# ---------------------------------------------------------------- strokes
def validar_tracos(tracos, w: Optional[int] = None, h: Optional[int] = None) -> tuple:
	"""``(normalised strokes, None)`` or ``(None, reason in Portuguese)``.

	Normalised: ``ferramenta``, ``marca`` (None for the eraser), ``raio_px`` (float; 0 for a lasso)
	and ``pontos`` as a float ``(n, 2)`` list. Rules: a list of at most :data:`MAX_TRACOS` dicts and
	:data:`MAX_PONTOS` points in all; known tool; ``laco`` / ``pincel`` with a known mark, ``borracha``
	without one; finite points (a lasso >= 3, a brush >= 1); brush / eraser radius in
	``(0, MAX_RAIO_PX]``; with ``w`` / ``h`` the points must lie within one crop size of the crop
	(strokes may overflow its edge, raster clipping handles that)."""
	if tracos is None:
		return [], None
	if not isinstance(tracos, list):
		return None, "tracos deve ser uma lista"
	if len(tracos) > MAX_TRACOS:
		return None, f"demasiados traços ({len(tracos)} > {MAX_TRACOS})"
	out, total = [], 0
	for i, t in enumerate(tracos):
		if not isinstance(t, dict):
			return None, f"traço {i}: deve ser um objeto"
		f = t.get("ferramenta")
		if f not in FERRAMENTAS:
			return None, f"traço {i}: ferramenta desconhecida {f!r} (laco, pincel, borracha)"
		m = t.get("marca")
		if f == "borracha":
			if m not in (None, ""):
				return None, f"traço {i}: a borracha não leva marca"
			m = None
		elif m not in MARCAS:
			return None, f"traço {i}: marca desconhecida {m!r} (peca, fundo, incerto)"
		try:
			p = np.asarray(t.get("pontos"), float).reshape(-1, 2)
		except (TypeError, ValueError):
			return None, f"traço {i}: pontos inválidos (lista de [x, y])"
		if not np.all(np.isfinite(p)):
			return None, f"traço {i}: pontos não finitos"
		if len(p) < (3 if f == "laco" else 1):
			return None, f"traço {i}: {len(p)} pontos (o laço precisa de 3, o pincel de 1)"
		total += len(p)
		if total > MAX_PONTOS:
			return None, f"demasiados pontos nos traços (> {MAX_PONTOS})"
		if w is not None and h is not None and len(p):
			if p[:, 0].min() < -w or p[:, 1].min() < -h or p[:, 0].max() > 2 * w or p[:, 1].max() > 2 * h:
				return None, f"traço {i}: pontos muito fora do recorte ({w} x {h})"
		r = 0.0
		if f != "laco":
			try:
				r = float(t.get("raio_px"))
			except (TypeError, ValueError):
				return None, f"traço {i}: raio_px em falta"
			if not np.isfinite(r) or r <= 0 or r > MAX_RAIO_PX:
				return None, f"traço {i}: raio_px fora de (0, {MAX_RAIO_PX:.0f}]"
		out.append({"ferramenta": f, "marca": m, "raio_px": r, "pontos": p.tolist()})
	return out, None


def traduzir_tracos(tracos, dx: float, dy: float) -> list:
	"""Strokes moved by ``(dx, dy)`` (another crop origin: ``old origem - new origem``)."""
	out = []
	for t in tracos or []:
		p = np.asarray(t["pontos"], float).reshape(-1, 2) + np.array([dx, dy], float)
		out.append(dict(t, pontos=np.round(p, 2).tolist()))
	return out


def _footprint(t: dict, shape: tuple) -> np.ndarray:
	"""uint8 0/1 raster of one normalised stroke (sub-pixel vertices, ``shift=4``)."""
	m = np.zeros(shape[:2], np.uint8)
	p = np.round(np.asarray(t["pontos"], float).reshape(-1, 2) * 16).astype(np.int32)
	if t["ferramenta"] == "laco":
		cv2.fillPoly(m, [p.reshape(-1, 1, 2)], 1, lineType=cv2.LINE_8, shift=4)
		return m
	r = float(t["raio_px"])
	if len(p) > 1:
		cv2.polylines(m, [p.reshape(-1, 1, 2)], False, 1, thickness=max(1, int(round(2 * r))),
					  lineType=cv2.LINE_8, shift=4)
	for x, y in p:
		cv2.circle(m, (int(x), int(y)), int(round(r * 16)), 1, thickness=-1, lineType=cv2.LINE_8, shift=4)
	return m


def rasterizar_tracos(tracos, shape: tuple) -> np.ndarray:
	"""int8 map of ``shape``: -1 unmarked, else the trimap code of the last stroke covering the pixel
	(``laco`` / ``pincel`` with their mark, ``borracha`` back to -1). ``tracos`` must be normalised
	(:func:`validar_tracos`)."""
	lbl = np.full(shape[:2], _NAO_MARCADO, np.int8)
	for t in tracos or []:
		fp = _footprint(t, shape) > 0
		lbl[fp] = _NAO_MARCADO if t["ferramenta"] == "borracha" else MARCAS[t["marca"]]
	return lbl


def _ellipse(r: int) -> np.ndarray:
	return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def trimap(auto_mask: np.ndarray, tracos, mm_per_px: float, banda_mm: float = BANDA_MM) -> np.ndarray:
	"""uint8 5-zone map (see the module docstring) of the crop: ``auto_mask`` (bool, the current
	contour filled) eroded / dilated by ``banda_mm`` gives probable piece / probable background and the
	uncertain band; the normalised ``tracos`` overwrite it."""
	am = np.asarray(auto_mask, bool).astype(np.uint8)
	r = max(1, int(round(banda_mm / mm_per_px)))
	k = _ellipse(r)
	inner = cv2.erode(am, k, borderType=cv2.BORDER_CONSTANT, borderValue=0) > 0
	outer = cv2.dilate(am, k) > 0
	t = np.full(am.shape, FUNDO_PROV, np.uint8)
	t[outer] = INCERTO
	t[inner] = PECA_PROV
	lbl = rasterizar_tracos(tracos, am.shape)
	sel = lbl >= 0
	t[sel] = lbl[sel].astype(np.uint8)
	return t


def dominio(tri: np.ndarray, alcance_px: float) -> tuple:
	"""``(fixed_piece, fixed_background, free)`` bool masks: free = uncertain pixels plus the probable
	ones within ``alcance_px`` of them; the rest of each probable zone is fixed with the certain one."""
	inc = tri == INCERTO
	prov = (tri == PECA_PROV) | (tri == FUNDO_PROV)
	livre = inc.copy()
	if alcance_px > 0 and inc.any():
		d = cv2.distanceTransform((~inc).astype(np.uint8), cv2.DIST_L2, 5)
		livre |= prov & (d <= alcance_px)
	fg = (tri == PECA_CERTA) | ((tri == PECA_PROV) & ~livre)
	bg = (tri == FUNDO_CERTO) | ((tri == FUNDO_PROV) & ~livre)
	return fg, bg, livre


def _window(livre: np.ndarray, pad: int) -> tuple:
	"""Slices of the bbox of ``livre`` grown by ``pad`` (the whole frame if ``livre`` is empty)."""
	ys, xs = np.nonzero(livre)
	h, w = livre.shape
	if len(ys) == 0:
		return slice(0, h), slice(0, w)
	return (slice(max(0, ys.min() - pad), min(h, ys.max() + pad + 1)),
			slice(max(0, xs.min() - pad), min(w, xs.max() + pad + 1)))


def parametros(nome: str, params: Optional[dict] = None) -> dict:
	"""The defaults of solver ``nome`` (:data:`SOLVER_PARAMS`) updated with ``params``; ValueError on an unknown key."""
	base = dict(SOLVER_PARAMS[nome])
	for k, v in (params or {}).items():
		if k not in base:
			raise ValueError(f"parâmetro desconhecido do solver {nome}: {k}")
		base[k] = v
	return base


# ---------------------------------------------------------------- solvers
def solve_grabcut(rgb_crop, tri, mm_per_px, bg_lab=None, iters=2, alcance_mm=1.0, incerto="perto",
				  janela="livre", espaco="lab", peso_l=0.0, limiar=0.0) -> np.ndarray:
	"""``cv2.grabCut`` (``GC_INIT_WITH_MASK``, ``iters`` iterations) on the free zone of the trimap.

	Fixed piece / background -> ``GC_FGD`` / ``GC_BGD``; free probable piece / background ->
	``GC_PR_FGD`` / ``GC_PR_BGD``; the uncertain pixels -> ``GC_PR_FGD`` when nearer to the piece
	zones than to the background ones (``incerto="perto"``: the midline of the band, i.e. the current
	contour for the automatic trimap), or all ``GC_PR_FGD`` (``"fgd"``) / ``GC_PR_BGD`` (``"bgd"``).
	``janela="livre"`` runs on the bbox of the free zone + 2 ``alcance`` (colour models local to the
	edge, faster), ``"recorte"`` on the whole crop. ``espaco`` / ``peso_l``: the image the colour
	models see (:func:`_feature_image`; ``"lab"`` with a low ``peso_l`` lets the chroma decide: the cast
	shadow has the paper's hue, the lit rim the piece's). ``limiar`` > 0: free pixels that the
	segmenter's threshold calls background become ``GC_BGD`` (``bg_lab`` used only then; measured
	worse, TRACOS.md)."""
	alc = alcance_mm / mm_per_px
	fg, bg, livre = dominio(tri, alc)
	out = fg.copy()
	if not livre.any():
		return out
	mask = np.where(fg, cv2.GC_FGD, cv2.GC_BGD).astype(np.uint8)
	mask[livre & (tri == PECA_PROV)] = cv2.GC_PR_FGD
	mask[livre & (tri == FUNDO_PROV)] = cv2.GC_PR_BGD
	inc = livre & (tri == INCERTO)
	if incerto == "perto":
		pz = ((tri == PECA_PROV) | (tri == PECA_CERTA)).astype(np.uint8)
		bz = ((tri == FUNDO_PROV) | (tri == FUNDO_CERTO)).astype(np.uint8)
		dp = cv2.distanceTransform(1 - pz, cv2.DIST_L2, 5) if pz.any() else np.full(tri.shape, np.inf, np.float32)
		db = cv2.distanceTransform(1 - bz, cv2.DIST_L2, 5) if bz.any() else np.full(tri.shape, np.inf, np.float32)
		near_p = dp < db
		mask[inc & near_p] = cv2.GC_PR_FGD
		mask[inc & ~near_p] = cv2.GC_PR_BGD
	elif incerto == "fgd":
		mask[inc] = cv2.GC_PR_FGD
	elif incerto == "bgd":
		mask[inc] = cv2.GC_PR_BGD
	else:
		raise ValueError(f"incerto deve ser perto, fgd ou bgd (não {incerto!r})")
	if limiar and limiar > 0:                    # background by the segmenter's threshold: hard background
		mask[livre & ~_threshold_fg(rgb_crop, tri, mm_per_px, bg_lab, limiar)] = cv2.GC_BGD
	if janela == "livre":
		sy, sx = _window(livre, int(round(2 * alc)) + 8)
	elif janela == "recorte":
		sy, sx = slice(0, tri.shape[0]), slice(0, tri.shape[1])
	else:
		raise ValueError(f"janela deve ser livre ou recorte (não {janela!r})")
	m = np.ascontiguousarray(mask[sy, sx])
	is_f = np.isin(m, (cv2.GC_FGD, cv2.GC_PR_FGD))
	if not is_f.any() or is_f.all():           # grabCut needs both classes
		out[sy, sx] |= is_f
		return out
	img = _feature_image(rgb_crop[sy, sx], espaco, peso_l)
	bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
	cv2.setRNGSeed(0)                          # grabCut seeds its GMMs with k-means on the thread RNG: same input, same output
	cv2.grabCut(img, m, None, bgd, fgd, int(iters), cv2.GC_INIT_WITH_MASK)
	res = np.zeros(tri.shape, bool)
	res[sy, sx] = (m == cv2.GC_FGD) | (m == cv2.GC_PR_FGD)
	return fg | (res & livre)


def _relief(rgb_crop: np.ndarray, mm_per_px: float, region: np.ndarray) -> np.ndarray:
	"""black-hat(L*) / p99 + Lab gradient / p99 (p99 over ``region``): the contact watershed's landscape
	(:func:`src.segmentation._blackhat_gradient`)."""
	from src.segmentation import _blackhat_gradient
	lab = cv2.cvtColor(np.ascontiguousarray(rgb_crop), cv2.COLOR_RGB2LAB).astype(np.float32)
	bh, grad = _blackhat_gradient(lab, mm_per_px)
	sel = region if region.any() else np.ones(region.shape, bool)
	return (bh / max(float(np.percentile(bh[sel], 99)), 1.0)
			+ grad / max(float(np.percentile(grad[sel], 99)), 1.0))


def _feature_image(rgb: np.ndarray, espaco: str = "rgb", peso_l: float = 1.0) -> np.ndarray:
	"""uint8 3-channel image for the OpenCV solvers: ``"rgb"`` = BGR; ``"lab"`` = (``peso_l`` L*, a*, b*)
	in OpenCV 8-bit Lab (``peso_l`` 0 = chroma only)."""
	if espaco == "rgb":
		return np.ascontiguousarray(rgb[..., ::-1])
	if espaco != "lab":
		raise ValueError(f"espaco deve ser rgb ou lab (não {espaco!r})")
	lab = cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2LAB)
	out = lab.copy()
	out[..., 0] = np.clip(lab[..., 0].astype(np.float32) * float(peso_l), 0, 255).astype(np.uint8)
	return np.ascontiguousarray(out)


def solve_watershed(rgb_crop, tri, mm_per_px, bg_lab=None, alcance_mm=1.0, paisagem="cor", suave_px=1.0,
					espaco="lab", peso_l=0.0) -> np.ndarray:
	"""Marker watershed of the free zone from the fixed piece / background markers.

	``paisagem``: ``"cor"`` = ``cv2.watershed`` on the colour image (:func:`_feature_image` of ``espaco``
	/ ``peso_l``) blurred by ``suave_px`` (it floods by the colour difference between neighbours, so
	the line lands on colour edges); ``"relevo"`` =
	``cv2.watershed`` on the black-hat(L*) + Lab-gradient relief (as an 8-bit grey image);
	``"inundacao"`` = the exact priority flood of that relief
	(:func:`src.segmentation._priority_flood`, private, pure Python: slow on wide bands).
	Watershed lines (-1) go to the background. ``bg_lab`` is unused."""
	fg, bg, livre = dominio(tri, alcance_mm / mm_per_px)
	if not livre.any() or not fg.any():
		return fg
	if not bg.any():
		return fg | livre
	sy, sx = _window(livre, 4)
	f, b, lv = fg[sy, sx], bg[sy, sx], livre[sy, sx]
	mk = np.zeros(f.shape, np.int32)
	mk[b] = 1
	mk[f] = 2
	mk[lv] = 0
	crop = np.ascontiguousarray(rgb_crop[sy, sx])
	if paisagem == "cor":
		img = _feature_image(crop, espaco, peso_l)
		if suave_px and suave_px > 0:
			img = cv2.GaussianBlur(img, (0, 0), float(suave_px))
		cv2.watershed(np.ascontiguousarray(img), mk)
		res = mk == 2
	elif paisagem in ("relevo", "inundacao"):
		hgt = _relief(crop, mm_per_px, lv)
		if paisagem == "relevo":
			g = np.clip(hgt * 127.0, 0, 255).astype(np.uint8)
			cv2.watershed(np.ascontiguousarray(np.dstack([g, g, g])), mk)
			res = mk == 2
		else:
			from src.segmentation import _priority_flood
			fl = _priority_flood(hgt, mk, lv)
			res = (fl == 2) | f
	else:
		raise ValueError(f"paisagem deve ser cor, relevo ou inundacao (não {paisagem!r})")
	out = fg.copy()
	out[sy, sx] |= res & lv
	return out


def _threshold_fg(rgb_crop, tri, mm_per_px, bg_lab, limiar, abertura_mm=0.42, peso_l=0.5) -> np.ndarray:
	"""Opened threshold ``sqrt(peso_l dL^2 + da^2 + db^2) > limiar`` (OpenCV 8-bit Lab; with ``peso_l``
	0.5 it is the segmenter's :func:`src.segmentation._scan_open_mask`) on the crop against ``bg_lab`` or,
	without it, the median of the crop's background zones (all True if none)."""
	from src.segmentation import _odd_kernel
	lab = cv2.cvtColor(np.ascontiguousarray(rgb_crop), cv2.COLOR_RGB2LAB).astype(np.float32)
	if bg_lab is None:
		bz = tri <= FUNDO_PROV
		if not bz.any():
			return np.ones(tri.shape, bool)
		bg_lab = np.median(lab[bz], axis=0)
	d = lab - np.asarray(bg_lab, np.float32)
	dist = np.sqrt(float(peso_l) * d[..., 0] ** 2 + d[..., 1] ** 2 + d[..., 2] ** 2)
	k = _odd_kernel(abertura_mm, mm_per_px)
	m = (dist > float(limiar)).astype(np.uint8)
	return cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((k, k), np.uint8)) > 0


def solve_limiar(rgb_crop, tri, mm_per_px, bg_lab=None, alcance_mm=0.0, limiar=28.0, abertura_mm=0.42,
				 peso_l=0.5) -> np.ndarray:
	"""Baseline: in the free zone, the segmenter's threshold (``sqrt(0.5 dL^2 + da^2 + db^2) > limiar`` in
	OpenCV 8-bit Lab, opened by ``abertura_mm``, as :func:`src.segmentation._scan_open_mask`; ``peso_l``
	changes the 0.5) against ``bg_lab`` (the scan rim background, :func:`src.segmentation._rim_background`) or, without
	it, the median of the crop's background zones."""
	fg, bg, livre = dominio(tri, alcance_mm / mm_per_px)
	return fg | (livre & _threshold_fg(rgb_crop, tri, mm_per_px, bg_lab, limiar, abertura_mm, peso_l))


SOLVERS = {"grabcut": solve_grabcut, "watershed": solve_watershed, "limiar": solve_limiar}


# ---------------------------------------------------------------- post-processing
def _largest(mask: np.ndarray) -> np.ndarray:
	n, cc, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
	if n < 2:
		return np.zeros(mask.shape, bool)
	return cc == 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))


def _fill_holes(mask: np.ndarray) -> np.ndarray:
	cnts, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
	m = np.zeros(mask.shape, np.uint8)
	cv2.drawContours(m, cnts, -1, 1, thickness=cv2.FILLED)
	return m > 0


def limpar(mask: np.ndarray, mm_per_px: float, tri: Optional[np.ndarray] = None,
		   limpeza_mm: float = LIMPEZA_MM) -> np.ndarray:
	"""Closing then opening with a disc of side ``limpeza_mm`` (odd px; 0 = none), the certain marks
	of ``tri`` re-imposed (piece added, background removed), largest 8-connected component, holes
	filled."""
	from src.segmentation import _odd_kernel
	m = np.asarray(mask, bool).astype(np.uint8)
	if limpeza_mm and limpeza_mm > 0:
		k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (_odd_kernel(limpeza_mm, mm_per_px),) * 2)
		m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k)
		m = cv2.morphologyEx(m, cv2.MORPH_OPEN, k)
	m = m > 0
	if tri is not None:
		m |= tri == PECA_CERTA
		m &= tri != FUNDO_CERTO
	return _fill_holes(_largest(m))


def mascara_poligono(mask: np.ndarray) -> Optional[np.ndarray]:
	"""Outer pixel chain (``findContours`` ``CHAIN_APPROX_NONE``, largest) of the mask as ``(n, 2)``
	float (x, y), or None when empty. Filling it (``cv2.fillPoly``) gives back the cleaned mask."""
	cnts, _ = cv2.findContours(np.asarray(mask, bool).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
	if not cnts:
		return None
	return max(cnts, key=cv2.contourArea).reshape(-1, 2).astype(float)


def resolver(rgb_crop: np.ndarray, auto_mask: np.ndarray, tracos, mm_per_px: float,
			 solver: str = SOLVER_OMISSAO, params: Optional[dict] = None, bg_lab=None,
			 banda_mm: float = BANDA_MM, limpeza_mm: float = LIMPEZA_MM) -> dict:
	"""Strokes -> trimap -> ``solver`` -> :func:`limpar` -> polygon, on the crop.

	``tracos`` must be normalised (:func:`validar_tracos`). Returns ``{mask (bool, = the polygon
	filled), contour ((n, 2) float, crop px), trimap, area_mm2, ms, solver, params}`` or
	``{'error': str}`` (unknown solver, nothing left of the piece)."""
	t0 = time.perf_counter()
	if solver not in SOLVERS:
		return {"error": f"solver desconhecido {solver!r} ({', '.join(SOLVERS)})"}
	try:
		pr = parametros(solver, params)
	except ValueError as e:
		return {"error": str(e)}
	tri = trimap(auto_mask, tracos, mm_per_px, banda_mm)
	raw = SOLVERS[solver](rgb_crop, tri, mm_per_px, bg_lab=bg_lab, **pr)
	m = limpar(raw, mm_per_px, tri, limpeza_mm)
	poly = mascara_poligono(m)
	if poly is None or len(poly) < 3:
		return {"error": "não sobrou nenhuma peça (marca alguma zona como peça)"}
	fill = np.zeros(m.shape, np.uint8)
	cv2.fillPoly(fill, [poly.astype(np.int32).reshape(-1, 1, 2)], 1)
	fill = fill > 0
	return {"mask": fill, "contour": poly, "trimap": tri, "area_mm2": float(fill.sum()) * mm_per_px * mm_per_px,
			"ms": (time.perf_counter() - t0) * 1000.0, "solver": solver, "params": pr}


# ---------------------------------------------------------------- RLE
def rle_encode(mask: np.ndarray) -> dict:
	"""``{w, h, runs}``: row-major run lengths alternating background / piece, background first."""
	m = np.asarray(mask, bool)
	h, w = m.shape[:2]
	flat = m.ravel().astype(np.int8)
	if flat.size == 0:
		return {"w": int(w), "h": int(h), "runs": []}
	cut = np.flatnonzero(np.diff(flat)) + 1
	runs = np.diff(np.concatenate([[0], cut, [flat.size]])).tolist()
	if flat[0]:
		runs = [0] + runs
	return {"w": int(w), "h": int(h), "runs": [int(r) for r in runs]}


def rle_decode(rle: dict) -> np.ndarray:
	"""Bool ``(h, w)`` mask of :func:`rle_encode`'s dict; ValueError when the runs do not cover it."""
	try:
		w, h = int(rle["w"]), int(rle["h"])
		runs = np.asarray(rle["runs"], np.int64).ravel()
	except (KeyError, TypeError, ValueError):
		raise ValueError("mascara_rle inválida: esperava {w, h, runs}")
	if w < 0 or h < 0 or np.any(runs < 0) or int(runs.sum()) != w * h:
		raise ValueError(f"mascara_rle inválida: as corridas somam {int(runs.sum())}, não {w} x {h}")
	vals = (np.arange(len(runs)) % 2 == 1)
	return np.repeat(vals, runs).reshape(h, w)
