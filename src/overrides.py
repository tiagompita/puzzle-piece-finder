"""Manual contour overrides: a piece outline drawn / adjusted by the user over the scan.

The file ``projects/<id>/overrides.jsonl`` is APPEND-ONLY, one line per save::

	{"t", "autor": "manual", "scan_id", "piece", "index_in_scan", "contour_px": [[x, y], ...], "nota"}

``contour_px`` is a closed polygon in whole-scan pixel coordinates (ints or floats); the last
line of a piece wins (:func:`latest_overrides`). Lines saved by the GUI editor may carry more
fields (``append_override(..., extra=...)``; old lines without them stay valid and nothing that applies
an override reads them)::

	"metodo": "tracos" | "vertices", "tracos": [...] (crop px, src.strokes), "origem": [x0, y0],
	"tamanho": [w, h], "solver": {"nome", "params"}, "mascara_rle": {"w", "h", "runs"} (the saved
	polygon filled in the crop, src.strokes.rle_encode), "auto_contour_px": [[x, y], ...] (int, scan
	px: the outline the save replaced), "auto_area_mm2", "auto_origem": "segmentacao" | "manual" | "gemea",
	"convencao": "indice" (saved through the editor's normalisation, src.strokes: the silhouette keeps the
	shadow halo of the index; lines without it predate 2026-11-09 and sit on the true edge), "delta_mm",
	"derivado_de": t of the line a re-edit replaces, "motivo": "renormalizacao" | ..., "base_gemea": {id, t, rms_mm}

:func:`manual_pairs` measures the automatic contour against the manual one per piece
(``python -m src.overrides --project <p> --pares``). The override is applied by
:func:`src.render.rebuild_assets` / :func:`src.render.rebuild_piece`: the polygon replaces the
segmented contour (npz arrays, crop, overlay) and the piece gets a ``piece_resegmented`` event
with ``motivo: "manual"`` and ``flags.manual_override = true``. Pieces with that flag are
excluded from every CV metric (segmentation, E-sym, §6.1 gate): their silhouette is not the
segmentation's output (``docs/gui-design.md`` §18).

Pure helpers (polygon area, simplicity, resampling, the crop record) are kept apart from the
small I/O part (reading the scan header, the jsonl file).
"""

import datetime as _dt
import json
import math
import os
from typing import Optional

import numpy as np

__all__ = [
	"OVERRIDES_FILE", "MIN_POINTS", "AREA_MIN_FRAC", "AREA_MAX_FRAC", "MARGIN_MM", "RESAMPLE_MM", "PAD_RATIO",
	"MANUAL_FLAG", "MANUAL_NOTE_FLAG", "MAX_POINTS",
	"EDITOR_EPS_PX", "clean_polygon", "polygon_area", "is_simple", "resample_closed",
	"editor_indices", "editor_polygon", "expand_polygon", "rasterize_polygon",
	"polygon_record",
	"validate_polygon", "manual_flags", "is_manual",
	"overrides_path", "read_overrides", "latest_overrides", "REPOSICAO", "has_override", "scan_file", "scan_size",
	"load_scan_rgb", "reference_area_px", "check_override", "append_override", "crop_window",
	"EXTRA_KEYS", "pair_metrics", "manual_pairs", "pose_pairs", "pose_summary", "mean_ci", "direction_of", "main",
]

OVERRIDES_FILE = "overrides.jsonl"
MIN_POINTS = 20            # fewer vertices than this cannot describe a jigsaw piece
MAX_POINTS = 5000          # guard for the O(n^2) simplicity test and the payload
AREA_MIN_FRAC = 0.5        # new area / current area of the piece, lower bound
AREA_MAX_FRAC = 1.5        # ... upper bound
MARGIN_MM = 3.0            # editor crop: bbox of the piece + this margin
RESAMPLE_MM = 1.0          # editor: vertex spacing of the initial polygon
PAD_RATIO = 0.02           # crop bbox padding, as segment_scan's default ``pad_ratio``
EDITOR_EPS_PX = 2.0        # editor handles: Douglas-Peucker tolerance (px; corners, tab tips) before densifying to RESAMPLE_MM
MANUAL_FLAG = "manual_override"
MANUAL_NOTE_FLAG = "manual_nota"
_SEG_SILHOUETTE_KEYS = ("is_cluster", "contacto", "recuperado_mm2", "suspeita_recorte")   # facts of the segmented silhouette, dropped
EXTRA_KEYS = ("metodo", "tracos", "origem", "tamanho", "solver", "mascara_rle", "auto_contour_px", "auto_area_mm2",
			  "auto_origem", "convencao", "delta_mm", "derivado_de", "motivo", "base_gemea")


# ---------------------------------------------------------------- pure helpers
def clean_polygon(pts) -> np.ndarray:
	"""``(n, 2)`` float array without consecutive duplicates nor a repeated closing vertex."""
	a = np.asarray(pts, float).reshape(-1, 2)
	if len(a) == 0:
		return a
	keep = np.ones(len(a), bool)
	keep[1:] = np.any(np.abs(np.diff(a, axis=0)) > 1e-9, axis=1)
	a = a[keep]
	while len(a) > 1 and np.all(np.abs(a[0] - a[-1]) <= 1e-9):
		a = a[:-1]
	return a


def polygon_area(pts) -> float:
	"""Absolute shoelace area (px²) of a closed polygon."""
	a = np.asarray(pts, float).reshape(-1, 2)
	if len(a) < 3:
		return 0.0
	x, y = a[:, 0], a[:, 1]
	return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2.0)


def is_simple(pts, touch: bool = True) -> bool:
	"""True if the closed polygon has no self-intersection: no two non-adjacent edges cross; with ``touch``
	also none touching (a vertex on another edge, collinear overlap). A pixel chain from ``findContours``
	revisits a pixel at 1-px spurs (it touches itself, 1 of 60 Alpes pieces), so the override validation
	uses ``touch=False``: it rejects the crossings a dragged vertex makes, not the raster artefacts.

	Edge i = (p_i, p_{i+1}); every pair of non-adjacent edges whose closed bounding boxes overlap (a
	necessary condition for crossing or touching, so the prefilter is exact) is tested, in vectorised
	blocks of rows (a 1100-point pixel chain: ~5 ms instead of ~160 ms with one numpy pass per edge)."""
	a = clean_polygon(pts)
	n = len(a)
	if n < 3:
		return False
	p0, p1 = a, np.roll(a, -1, axis=0)
	lo, hi = np.minimum(p0, p1), np.maximum(p0, p1)

	def orient(o, u, v):
		return (u[..., 0] - o[..., 0]) * (v[..., 1] - o[..., 1]) - (u[..., 1] - o[..., 1]) * (v[..., 0] - o[..., 0])

	def on_seg(o, u, q):     # q collinear with (o, u): inside its bounding box
		return ((np.minimum(o[..., 0], u[..., 0]) <= q[..., 0]) & (q[..., 0] <= np.maximum(o[..., 0], u[..., 0]))
				& (np.minimum(o[..., 1], u[..., 1]) <= q[..., 1]) & (q[..., 1] <= np.maximum(o[..., 1], u[..., 1])))

	block = max(1, 2_000_000 // n)
	for s in range(0, n, block):
		r = np.arange(s, min(n, s + block))
		ov = ((lo[r, None, 0] <= hi[None, :, 0]) & (lo[None, :, 0] <= hi[r, None, 0])
			  & (lo[r, None, 1] <= hi[None, :, 1]) & (lo[None, :, 1] <= hi[r, None, 1]))
		i, j = np.nonzero(ov)
		i = i + s
		keep = (j >= i + 2) & ~((i == 0) & (j == n - 1))      # non-adjacent; the last edge shares p_0 with edge 0
		i, j = i[keep], j[keep]
		if len(i) == 0:
			continue
		a0, a1 = p0[i], p1[i]
		b0, b1 = p0[j], p1[j]
		d1, d2 = orient(b0, b1, a0), orient(b0, b1, a1)
		d3, d4 = orient(a0, a1, b0), orient(a0, a1, b1)
		cross = (((d1 > 0) & (d2 < 0)) | ((d1 < 0) & (d2 > 0))) & (((d3 > 0) & (d4 < 0)) | ((d3 < 0) & (d4 > 0)))
		touch_ = ((d1 == 0) & on_seg(b0, b1, a0)) | ((d2 == 0) & on_seg(b0, b1, a1)) \
			| ((d3 == 0) & on_seg(a0, a1, b0)) | ((d4 == 0) & on_seg(a0, a1, b1))
		if np.any(cross | touch_) if touch else np.any(cross):
			return False
	return True


def resample_closed(pts, step: float) -> np.ndarray:
	"""Closed polygon resampled at about ``step`` (same units) along its perimeter; >= 3 vertices."""
	a = clean_polygon(pts)
	if len(a) < 3 or step <= 0:
		return a
	b = np.vstack([a, a[:1]])
	seg = np.hypot(*np.diff(b, axis=0).T)
	s = np.concatenate([[0.0], np.cumsum(seg)])
	per = float(s[-1])
	n = max(3, int(round(per / step)))
	t = np.linspace(0.0, per, n, endpoint=False)
	return np.stack([np.interp(t, s, b[:, 0]), np.interp(t, s, b[:, 1])], axis=1)


def _dp_indices(c: np.ndarray, eps: float) -> list:
	"""Sorted indices of the Douglas-Peucker vertices (``cv2.approxPolyDP``, closed) of polygon ``c``."""
	import cv2
	cf = np.ascontiguousarray(c, np.float32)
	ap = cv2.approxPolyDP(cf.reshape(-1, 1, 2), float(eps), True).reshape(-1, 2)
	first = {}
	for i, (x, y) in enumerate(cf):
		first.setdefault((float(x), float(y)), i)
	return sorted({first[(float(x), float(y))] for x, y in ap if (float(x), float(y)) in first})


def _densify(c: np.ndarray, keep: list, step: float) -> np.ndarray:
	"""``keep`` (sorted indices of ``c``) plus indices of ``c`` spread along each stretch between two kept
	ones (the nearest point of ``c`` to each even arc position) so that the stretches are about ``step``
	of arc (at most ~1.5 ``step`` where ``c`` has points); sorted, unique."""
	n = len(c)
	seg = np.hypot(*np.diff(np.vstack([c, c[:1]]), axis=0).T)
	s = np.concatenate([[0.0], np.cumsum(seg)])          # arc length at vertex i (s[n] = perimeter)
	out = []
	for a, b in zip(keep, list(keep[1:]) + [keep[0] + n]):
		out.append(a)
		L = s[b] - s[a] if b <= n else (s[n] - s[a]) + s[b - n]
		k = max(1, int(round(L / step)))                   # stretches of about ``step`` (<= 1.5 step)
		for j in range(1, k):                                # k - 1 points spread evenly along the arc
			t = s[a] + L * j / k
			t = t - s[n] if t >= s[n] else t
			q = int(np.searchsorted(s, t))                   # the nearest point of c to arc position t
			q = q - 1 if q > 0 and (q >= n or t - s[q - 1] < s[q] - t) else q
			out.append(min(q, n - 1))
	return np.array(sorted(set(i % n for i in out)), int)


def editor_indices(poly, step: float, eps: float = EDITOR_EPS_PX) -> np.ndarray:
	"""Indices into ``poly`` of the editor's handles: its Douglas-Peucker vertices at ``eps`` (corners and
	tab tips stay) plus points of ``poly`` about every ``step`` of arc between them. Ascending (cyclic
	order of ``poly``), at least 3."""
	c = clean_polygon(poly)
	n = len(c)
	if n < 4 or step <= 0:
		return np.arange(n)
	keep = _dp_indices(c, eps)
	if len(keep) < 3:
		keep = sorted(set(np.linspace(0, n, 4, endpoint=False).astype(int).tolist()))
	return _densify(c, keep, step)


def editor_polygon(contour, step: float, eps: float = EDITOR_EPS_PX) -> np.ndarray:
	"""The editor's handles of a stored contour: ``c[editor_indices(c, step)]`` with ``c`` the contour
	itself (the full pixel chain is the exact polygon the handles index into; a Douglas-Peucker subset
	is neither raster-exact nor guaranteed simple)."""
	c = clean_polygon(contour)
	return c[editor_indices(c, step, eps)]


def expand_polygon(dense, verts, idx, keep) -> np.ndarray:
	"""Polygon saved by the editor (the JS ``cedExpanded`` does the same): each handle ``verts[i]``, and
	when the edge i -> i+1 is untouched (``keep[i]``, both handles still at their indices ``idx`` of
	``dense``) the points of ``dense`` strictly between them, so an unedited stretch keeps the exact
	contour and an edited one is the straight line between the handles."""
	d = np.asarray(dense, float).reshape(-1, 2)
	v = np.asarray(verts, float).reshape(-1, 2)
	n, m = len(v), len(d)
	out = []
	for i in range(n):
		out.append(v[i])
		a, b = idx[i], idx[(i + 1) % n]
		if keep[i] and a is not None and b is not None and n > 1:
			j, guard = (int(a) + 1) % m, 0
			while j != int(b) and guard < m:
				out.append(d[j])
				j, guard = (j + 1) % m, guard + 1
	return np.asarray(out, float)


def rasterize_polygon(pts, W: int, H: int, pad_ratio: float = PAD_RATIO):
	"""``(mask, (ox, oy, ow, oh), contour)`` of a polygon on a ``W x H`` scan, the way
	``segment_scan`` crops a piece (``segmentation._scan_record``): integer vertices clipped to the
	scan, tight bbox padded by ``pad_ratio`` x its long side, filled mask of the padded crop, and the
	returned ``contour`` (scan px, int32) = largest external contour of that mask (dense)."""
	import cv2
	c = np.round(np.asarray(pts, float).reshape(-1, 2)).astype(np.int32)
	c[:, 0] = np.clip(c[:, 0], 0, W - 1)
	c[:, 1] = np.clip(c[:, 1], 0, H - 1)
	ox, oy, ow, oh = cv2.boundingRect(c.reshape(-1, 1, 2))
	pad = int(round(pad_ratio * max(ow, oh)))
	ox, oy = max(0, ox - pad), max(0, oy - pad)
	ow, oh = min(W - ox, ow + 2 * pad), min(H - oy, oh + 2 * pad)
	mask = np.zeros((oh, ow), np.uint8)
	cv2.fillPoly(mask, [(c - np.array([ox, oy], np.int32)).reshape(-1, 1, 2)], 255)
	cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
	cnt = max(cnts, key=cv2.contourArea).reshape(-1, 2).astype(np.int32) + np.array([ox, oy], np.int32)
	return mask, (int(ox), int(oy), int(ow), int(oh)), cnt


def polygon_record(rgb: np.ndarray, pts, pad_ratio: float = PAD_RATIO) -> dict:
	"""Piece record of a polygon in the format of a ``segment_scan`` piece (``normalize_rotation=False``):
	``{image (PIL RGB, background filled with the mean piece colour), mask (PIL L), bbox, area_px,
	contour}`` so the crop is written exactly as :func:`src.segmentation.piece_to_rgba` writes the
	segmented ones."""
	from PIL import Image
	H, W = rgb.shape[:2]
	mask, (ox, oy, ow, oh), cnt = rasterize_polygon(pts, W, H, pad_ratio)
	crop = np.ascontiguousarray(rgb[oy:oy + oh, ox:ox + ow, :3]).copy()
	m = mask > 0
	if m.any():
		crop[~m] = crop[m].mean(axis=0).astype(np.uint8)
	return {"image": Image.fromarray(crop), "mask": Image.fromarray(mask), "bbox": (ox, oy, ow, oh),
			"area_px": int(m.sum()), "contour": cnt}


def validate_polygon(pts, W: int, H: int, area_ref_px: Optional[float]) -> Optional[str]:
	"""Reason (Portuguese) why ``pts`` is not an acceptable piece outline on a ``W x H`` scan, or None.

	Rules: >= :data:`MIN_POINTS` distinct vertices (<= :data:`MAX_POINTS`), finite, inside the scan,
	simple (no crossing edges; touching allowed), area within [:data:`AREA_MIN_FRAC`, :data:`AREA_MAX_FRAC`] x
	``area_ref_px`` (skipped when None)."""
	try:
		a = clean_polygon(pts)
	except (TypeError, ValueError):
		return "contorno inválido: esperava uma lista de pontos [x, y]"
	if not np.all(np.isfinite(a)):
		return "contorno com coordenadas não finitas"
	if len(a) < MIN_POINTS:
		return f"contorno com {len(a)} pontos: são precisos pelo menos {MIN_POINTS}"
	if len(a) > MAX_POINTS:
		return f"contorno com {len(a)} pontos: máximo {MAX_POINTS}"
	if a[:, 0].min() < 0 or a[:, 1].min() < 0 or a[:, 0].max() > W - 1 or a[:, 1].max() > H - 1:
		return f"contorno fora do scan ({W} x {H} px)"
	if not is_simple(a, touch=False):
		return "contorno cruza-se a si próprio (polígono não simples)"
	if area_ref_px:
		f = polygon_area(a) / float(area_ref_px)
		if f < AREA_MIN_FRAC or f > AREA_MAX_FRAC:
			return (f"área do contorno = {100 * f:.0f} % da área atual da peça "
					f"(aceite entre {100 * AREA_MIN_FRAC:.0f} % e {100 * AREA_MAX_FRAC:.0f} %)")
	return None


def manual_flags(old_flags: dict, seg_piece: Optional[dict], area_mm2: float, median_mm2: float, nota: str = "") -> dict:
	"""``flags`` of a piece whose contour is a manual override: the stored non-silhouette keys,
	``touches_frame`` / ``touches_strip`` (from the segmented record when there is one, else the
	stored ones), ``objeto_duplo`` from the new area, :data:`MANUAL_FLAG` = True and the note.
	``is_cluster``, ``contacto``, ``recuperado_mm2`` and ``suspeita_recorte`` describe the segmented
	silhouette and are dropped."""
	from src.ingest import DOUBLE_AREA_FACTOR
	old = dict(old_flags or {})
	src = seg_piece if seg_piece is not None else old
	out = {k: v for k, v in old.items() if k not in _SEG_SILHOUETTE_KEYS + (MANUAL_FLAG, MANUAL_NOTE_FLAG,
																			  "touches_frame", "touches_strip", "objeto_duplo")}
	out["touches_frame"] = bool(src.get("touches_frame"))
	out["touches_strip"] = bool(src.get("touches_strip"))
	out["is_cluster"] = False
	out["objeto_duplo"] = bool(median_mm2 and area_mm2 > DOUBLE_AREA_FACTOR * median_mm2)
	out[MANUAL_FLAG] = True
	if nota:
		out[MANUAL_NOTE_FLAG] = str(nota)
	return out


def is_manual(piece) -> bool:
	"""True if the piece's silhouette is a manual override (keep it OUT of CV metrics)."""
	flags = getattr(piece, "flags", None) if not isinstance(piece, dict) else piece.get("flags")
	return bool((flags or {}).get(MANUAL_FLAG))


# ---------------------------------------------------------------- I/O
def overrides_path(project) -> str:
	return project.p(OVERRIDES_FILE)


def read_overrides(project) -> list:
	"""Every line of ``overrides.jsonl`` (in order; a missing file = [])."""
	fp = overrides_path(project)
	if not os.path.exists(fp):
		return []
	out = []
	with open(fp, encoding="utf-8") as f:
		for line in f:
			line = line.strip()
			if line:
				out.append(json.loads(line))
	return out


REPOSICAO = "reposicao"


def latest_overrides(project, incluir_reposicao: bool = False) -> dict:
	"""``{piece: override}``: the last line of each piece. A piece whose last line is a *reposição*
	(``metodo == "reposicao"``: the user, or the renormalisation of 2026-11-09, put the automatic contour
	back) is left out, so :func:`has_override` is False, the editor starts from the segmentation and
	:func:`src.render.rebuild_assets` re-segments it (``force_scans``) without ``manual_override``;
	``incluir_reposicao=True`` returns those lines too (audit, ``--pares``)."""
	last = {o["piece"]: o for o in read_overrides(project) if o.get("piece")}
	if incluir_reposicao:
		return last
	return {k: v for k, v in last.items() if v.get("metodo") != REPOSICAO}


def has_override(project, piece: str) -> bool:
	return piece in latest_overrides(project)


def scan_file(project, sid: str) -> Optional[str]:
	"""Absolute path of the scan image of ``sid`` (as registered; may not exist)."""
	scan = project.model.scans.get(sid) or {}
	path = scan.get("file")
	if not path:
		return None
	if os.path.isabs(path):
		return path
	repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
	return os.path.join(repo, path)


def scan_size(project, sid: str) -> tuple:
	"""``(W, H)`` of the scan (header only)."""
	from PIL import Image
	fp = scan_file(project, sid)
	if not fp or not os.path.exists(fp):
		raise FileNotFoundError(f"{sid}: scan em falta ({fp})")
	with Image.open(fp) as im:
		return int(im.size[0]), int(im.size[1])


def load_scan_rgb(project, sid: str) -> np.ndarray:
	"""The scan as an ``(H, W, 3)`` uint8 RGB array (PIL, so no EXIF re-orientation surprise of cv2)."""
	from PIL import Image
	fp = scan_file(project, sid)
	if not fp or not os.path.exists(fp):
		raise FileNotFoundError(f"{sid}: scan em falta ({fp})")
	with Image.open(fp) as im:
		return np.asarray(im.convert("RGB")).copy()


def _mmpp(project, sid: str) -> float:
	s = project.model.scans.get(sid) or {}
	v = (s.get("meta") or {}).get("mm_per_px")
	return float(v) if v else 25.4 / float(s.get("dpi") or project.profile.dpi)


def reference_area_px(project, piece: str) -> Optional[float]:
	"""Current area of the piece in scan px² (``area_mm2`` of the index, else its stored contour)."""
	p = project.piece(piece)
	mmpp = _mmpp(project, p.scan_id)
	if p.area_mm2:
		return float(p.area_mm2) / (mmpp * mmpp)
	c = project.contour_px(piece)
	return polygon_area(c) if c is not None else None


def check_override(project, piece: str, contour_px) -> tuple:
	"""``(pts, None)`` with the cleaned polygon (scan px) when acceptable, else ``(None, reason)``."""
	if piece not in project.pieces:
		return None, f"peça desconhecida {piece}"
	p = project.piece(piece)
	try:
		W, H = scan_size(project, p.scan_id)
	except FileNotFoundError as e:
		return None, str(e)
	err = validate_polygon(contour_px, W, H, reference_area_px(project, piece))
	if err:
		return None, f"{piece}: {err}"
	return clean_polygon(contour_px), None


def append_override(project, piece: str, contour_px, nota: str = "", extra: Optional[dict] = None) -> dict:
	"""Validate (:func:`check_override`) and append one line to ``overrides.jsonl``; returns the line
	or ``{'error': str}`` (nothing written). The override is applied by :func:`src.render.rebuild_piece`.

	``extra``: additional JSON fields of the line, only those of :data:`EXTRA_KEYS` (the base fields
	cannot be overwritten); see the module docstring."""
	extra = dict(extra or {})
	bad = sorted(k for k in extra if k not in EXTRA_KEYS)
	if bad:
		return {"error": f"campos desconhecidos no registo: {', '.join(bad)}"}
	pts, err = check_override(project, piece, contour_px)
	if err:
		return {"error": err}
	p = project.piece(piece)
	rec = {"t": _dt.datetime.now().isoformat(timespec="seconds"), "autor": "manual", "scan_id": p.scan_id,
		   "piece": piece, "index_in_scan": int(p.index_in_scan),
		   "contour_px": [[round(float(x), 2), round(float(y), 2)] for x, y in pts], "nota": str(nota or "")}
	rec.update({k: extra[k] for k in EXTRA_KEYS if k in extra})
	with open(overrides_path(project), "a", encoding="utf-8") as f:
		f.write(json.dumps(rec, ensure_ascii=False) + "\n")
	return rec


def crop_window(project, piece: str, margin_mm: float = MARGIN_MM) -> tuple:
	"""``(x0, y0, x1, y1, margin_px)``: the piece's bbox grown by ``margin_mm``, clipped to the scan
	(x1 / y1 exclusive). The editor works in this crop's coordinates."""
	p = project.piece(piece)
	W, H = scan_size(project, p.scan_id)
	if p.bbox:
		x, y, w, h = [int(v) for v in p.bbox]
	else:
		c = project.contour_px(piece)
		if c is None:
			raise FileNotFoundError(f"{piece}: sem bbox nem contorno")
		c = np.asarray(c).reshape(-1, 2)
		x, y = int(c[:, 0].min()), int(c[:, 1].min())
		w, h = int(c[:, 0].max()) - x + 1, int(c[:, 1].max()) - y + 1
	m = int(round(margin_mm / _mmpp(project, p.scan_id)))
	return max(0, x - m), max(0, y - m), min(W, x + w + m), min(H, y + h + m), m


# ---------------------------------------------------------------- automatic vs manual (plan 2.4)
def pair_metrics(auto_px, manual_px, mm_per_px: float) -> dict:
	""":func:`src.maskcmp.mask_metrics` of the automatic polygon (candidate) against the manual one
	(ground truth), both in scan px, rasterised in a common local frame: ``missing`` = manual area the
	automatic contour does not cover (a bite), ``excess`` = automatic halo / shadow outside it."""
	from src.maskcmp import fill_contour, mask_metrics
	a = np.asarray(auto_px, float).reshape(-1, 2)
	m = np.asarray(manual_px, float).reshape(-1, 2)
	both = np.vstack([a, m])
	org = np.floor(both.min(0)) - 2
	shape = (int(np.ceil(both[:, 1].max() - org[1])) + 3, int(np.ceil(both[:, 0].max() - org[0])) + 3)
	return mask_metrics(fill_contour(m - org, shape), fill_contour(a - org, shape), mm_per_px)


def manual_pairs(project) -> list:
	"""One dict per piece with an override: ``piece``, ``t`` and ``metodo`` of its latest line, and the
	automatic contour against the manual one (:func:`pair_metrics`: ``iou``, ``missing_mm2``,
	``excess_mm2``, ``d_p95``, ``missing_depth_mm``, ``excess_depth_mm``). The automatic contour is the
	``auto_contour_px`` of the piece's first line whose ``auto_origem`` is ``"segmentacao"`` (or not
	given), else of its latest line that has one (then ``auto_origem`` says ``"manual"``: a previous
	manual outline); pieces whose lines carry none (saved before the field existed) get the metrics as
	None and ``auto_origem`` None. Sorted by piece."""
	lines = read_overrides(project)
	latest = latest_overrides(project)
	keys = ("iou", "missing_mm2", "excess_mm2", "d_p95", "missing_depth_mm", "excess_depth_mm")
	out = []
	for pid in sorted(latest):
		ov = latest[pid]
		mine = [o for o in lines if o.get("piece") == pid and o.get("auto_contour_px")]
		seg = [o for o in mine if o.get("auto_origem") in (None, "segmentacao")]
		src = seg[0] if seg else (mine[-1] if mine else None)
		row = {"piece": pid, "t": ov.get("t"), "metodo": ov.get("metodo") or "vertices", "scan_id": ov.get("scan_id"),
			   "auto_origem": (src.get("auto_origem") or "segmentacao") if src else None}
		if src is None:
			row.update({k: None for k in keys})
		else:
			r = pair_metrics(src["auto_contour_px"], ov["contour_px"], _mmpp(project, ov.get("scan_id")))
			row.update({k: float(r[k]) for k in keys})
		out.append(row)
	return out


# ---------------------------------------------------------------- automatic vs manual POSE (pose_set events; measurement only)
# Student t, 95 % two-sided, by degrees of freedom (1..30); 2.0 up to 60, 1.96 above. No scipy in the project.
_T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
		11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
		21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042}


def t95(df: int) -> float:
	if df < 1:
		return float("nan")
	return _T95.get(df, 2.0 if df <= 60 else 1.96)


def mean_ci(xs) -> dict:
	"""``{n, media, dp, lo, hi}``: mean and 95 % t interval of a sample (``lo``/``hi`` None when n < 2)."""
	v = np.asarray([x for x in xs if x is not None and np.isfinite(x)], float)
	n = int(v.size)
	if n == 0:
		return {"n": 0, "media": None, "dp": None, "lo": None, "hi": None}
	m = float(v.mean())
	if n < 2:
		return {"n": 1, "media": m, "dp": None, "lo": None, "hi": None}
	sd = float(v.std(ddof=1))
	hw = t95(n - 1) * sd / math.sqrt(n)
	return {"n": n, "media": m, "dp": sd, "lo": m - hw, "hi": m + hw}


def direction_of(dx: float, dy: float) -> Optional[str]:
	"""Board direction of a displacement (mm, y down): the dominant axis; None when (0, 0)."""
	if abs(dx) < 1e-9 and abs(dy) < 1e-9:
		return None
	if abs(dx) >= abs(dy):
		return "E" if dx > 0 else "W"
	return "S" if dy > 0 else "N"


def _wrap180(a: float) -> float:
	a = (a + 180.0) % 360.0 - 180.0
	return 180.0 if a == -180.0 else a


def pose_pairs(project) -> list:
	"""One row per ``pose_set`` event: the manual pose against the automatic one it replaced (``antes``), both
	absolute about the cell centre with the same pivot (``x = R(θ)(x_scan − pivot) + centre + (dx, dy)``), so the
	deviation is a plain difference: ``dtheta_deg``, ``dx_mm``, ``dy_mm`` (manual − automatic), ``d_mm`` =
	|(dx, dy)|, ``direcao`` (dominant axis, y down = S), ``desloc_centro_mm`` (the displacement of the body centre
	when the pivot is not that centre: the rotation moves it too), ``zona`` (:func:`src.fit.zone_of`), ``ativa``
	(the piece still shows this manual pose), ``method_auto``, ``residual_auto``, ``corner_k_auto``. Nothing is
	calibrated from this: it is the measurement ``--pares`` prints."""
	from src.fit import zone_of
	from src.locate import body_center_mm
	rows = []
	evs = [ev for ev in project.events() if ev.get("action") == "pose_set"]
	last_idx = {ev.get("piece"): i for i, ev in enumerate(evs)}        # the last pose_set of each piece (same-second saves)
	for i, ev in enumerate(evs):
		a = ev.get("antes") or {}
		pid = ev.get("piece")
		p = project.pieces.get(pid)
		pm = p.pose_manual if p is not None else None
		th_m, th_a = float(ev["theta_deg"]), (None if a.get("theta_deg") is None else float(a["theta_deg"]))
		dx, dy = float(ev["dx_mm"]) - float(a.get("dx_mm") or 0.0), float(ev["dy_mm"]) - float(a.get("dy_mm") or 0.0)
		dth = None if th_a is None else _wrap180(th_m - th_a)
		centre = None
		if p is not None and dth is not None:
			try:
				sh = project.shape(pid)
				piv = np.asarray(ev.get("pivot_mm") or a.get("pivot_mm") or body_center_mm(sh), float)
				c = body_center_mm(sh) - piv
				if np.hypot(*c) > 1e-6:
					ra, rm = np.radians(th_a), np.radians(th_m)
					rot = lambda t, v: np.array([math.cos(t) * v[0] - math.sin(t) * v[1], math.sin(t) * v[0] + math.cos(t) * v[1]])
					d = rot(rm, c) + np.array([dx, dy]) - rot(ra, c)
					centre = float(np.hypot(*d))
				else:
					centre = float(math.hypot(dx, dy))
			except Exception:  # noqa: BLE001 - a piece without shape: the plain displacement stays
				centre = None
		rows.append({"piece": pid, "cell": list(ev.get("cell") or []), "zona": zone_of(ev.get("cell")), "t": ev.get("t"),
					 "ativa": bool(pm is not None and pm.get("t") == ev.get("t") and last_idx.get(pid) == i), "theta_manual_deg": th_m, "theta_auto_deg": th_a,
					 "dtheta_deg": dth, "dx_mm": dx, "dy_mm": dy, "d_mm": float(math.hypot(dx, dy)), "direcao": direction_of(dx, dy),
					 "desloc_centro_mm": centre, "method_auto": a.get("method"), "residual_auto": a.get("residual_mm"),
					 "corner_k_auto": a.get("corner_k"), "nota": ev.get("nota") or ""})
	return rows


def pose_summary(rows: list) -> dict:
	"""``{total, por_zona: {zona: {campo: mean_ci}}, por_direcao: {dir: {...}}}`` over :func:`pose_pairs` rows
	(fields ``dx_mm``, ``dy_mm``, ``dtheta_deg``, ``d_mm``)."""
	fields = ("dx_mm", "dy_mm", "dtheta_deg", "d_mm")

	def agg(rs):
		return {f: mean_ci([r.get(f) for r in rs]) for f in fields}
	by_z, by_d = {}, {}
	for r in rows:
		by_z.setdefault(r["zona"], []).append(r)
		by_d.setdefault(r["direcao"] or "—", []).append(r)
	return {"total": agg(rows), "n": len(rows), "n_ativas": sum(1 for r in rows if r["ativa"]),
			"por_zona": {k: agg(v) for k, v in sorted(by_z.items())}, "por_direcao": {k: agg(v) for k, v in sorted(by_d.items())}}


def _ci_txt(c: dict, nd: int = 2) -> str:
	if not c or c["n"] == 0:
		return "—"
	s = f"n={c['n']} média {c['media']:+.{nd}f}"
	if c["lo"] is not None:
		s += f" IC95 [{c['lo']:+.{nd}f}, {c['hi']:+.{nd}f}]"
	return s


def format_pose_pairs(rows: list, summ: dict) -> str:
	lines = ["## Poses manuais (pose_set: manual − automática, mm do tabuleiro, y para baixo; nada é calibrado daqui)",
			 "| peça | célula | zona | t | ativa | Δθ ° | Δx mm | Δy mm | |d| mm | direção | desloc. centro mm | auto |",
			 "|---|---|---|---|---|---|---|---|---|---|---|---|"]
	for r in rows:
		res = r.get("residual_auto")
		auto = (r["method_auto"] or "?") + ("" if res is None else f" ({float(res):.2f} mm)")
		lines.append(f"| {r['piece']} | {tuple(r['cell']) if r['cell'] else '—'} | {r['zona']} | {r['t']} | {'sim' if r['ativa'] else 'não'} | "
					 f"{_fmt(r['dtheta_deg'])} | {_fmt(r['dx_mm'])} | {_fmt(r['dy_mm'])} | {_fmt(r['d_mm'])} | {r['direcao'] or '—'} | "
					 f"{_fmt(r['desloc_centro_mm'])} | {auto} |")
	lines.append("")
	lines.append(f"{summ['n']} poses manuais ({summ['n_ativas']} ativas); nenhuma calibração aplicada.")
	for name, d in (("total", {"todas": summ["total"]}), ("por zona", summ["por_zona"]), ("por direção", summ["por_direcao"])):
		lines.append(f"- {name}:")
		for k, agg in d.items():
			lines.append(f"  - {k}: Δx {_ci_txt(agg['dx_mm'])}; Δy {_ci_txt(agg['dy_mm'])}; Δθ {_ci_txt(agg['dtheta_deg'], 1)}; |d| {_ci_txt(agg['d_mm'])}")
	return "\n".join(lines)


def _fmt(v, nd=2):
	return "—" if v is None else f"{v:.{nd}f}"


def main(argv=None) -> int:
	"""``python -m src.overrides --project <p> --pares [--json]``: the automatic-vs-manual tables (contours, then poses)."""
	import argparse
	from src.state import Project
	ap = argparse.ArgumentParser(prog="python -m src.overrides", description="Contornos manuais (overrides.jsonl).")
	ap.add_argument("--project", required=True)
	ap.add_argument("--pares", action="store_true", help="contorno automático vs manual por peça (maskcmp)")
	ap.add_argument("--json", action="store_true", help="com --pares: JSON (lista dos contornos) em vez da tabela")
	ap.add_argument("--json-poses", action="store_true", help="com --pares: JSON {poses, resumo} das poses manuais")
	a = ap.parse_args(argv)
	if not a.pares:
		ap.print_help()
		return 0
	pr = Project.open(a.project)
	rows = manual_pairs(pr)
	prow = pose_pairs(pr)
	if a.json_poses:
		print(json.dumps({"poses": prow, "resumo": pose_summary(prow)}, ensure_ascii=False, indent=1))
		return 0
	if a.json:
		print(json.dumps(rows, ensure_ascii=False, indent=1))
		return 0
	print("## Contornos manuais (automático vs manual, maskcmp)")
	print("| peça | t | método | origem auto | IoU | em falta mm² | a mais mm² | p95 mm | prof. falta mm | prof. a mais mm |")
	print("|---|---|---|---|---|---|---|---|---|---|")
	for r in rows:
		print(f"| {r['piece']} | {r['t']} | {r['metodo']} | {r['auto_origem'] or 'sem registo'} | {_fmt(r['iou'], 4)} | "
			  f"{_fmt(r['missing_mm2'])} | {_fmt(r['excess_mm2'])} | {_fmt(r['d_p95'])} | {_fmt(r['missing_depth_mm'])} | "
			  f"{_fmt(r['excess_depth_mm'])} |")
	n = sum(1 for r in rows if r["iou"] is not None)
	print(f"\n{len(rows)} peças com contorno manual; {n} com contorno automático registado.\n")
	print(format_pose_pairs(prow, pose_summary(prow)))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
