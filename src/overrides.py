"""Manual contour overrides: a piece outline drawn / adjusted by the user over the scan.

The file ``projects/<id>/overrides.jsonl`` is APPEND-ONLY, one line per save::

	{"t", "autor": "manual", "scan_id", "piece", "index_in_scan", "contour_px": [[x, y], ...], "nota"}

``contour_px`` is a closed polygon in whole-scan pixel coordinates (ints or floats); the last
line of a piece wins (:func:`latest_overrides`). The override is applied by
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
	"overrides_path", "read_overrides", "latest_overrides", "has_override", "scan_file", "scan_size",
	"load_scan_rgb", "reference_area_px", "check_override", "append_override", "crop_window",
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

	Edge i = (p_i, p_{i+1}); every pair of non-adjacent edges is tested (one numpy pass per edge)."""
	a = clean_polygon(pts)
	n = len(a)
	if n < 3:
		return False
	p0, p1 = a, np.roll(a, -1, axis=0)

	def orient(o, u, v):
		return (u[..., 0] - o[..., 0]) * (v[..., 1] - o[..., 1]) - (u[..., 1] - o[..., 1]) * (v[..., 0] - o[..., 0])

	def on_seg(o, u, q):     # q collinear with (o, u): inside its bounding box
		return ((np.minimum(o[..., 0], u[..., 0]) <= q[..., 0]) & (q[..., 0] <= np.maximum(o[..., 0], u[..., 0]))
				& (np.minimum(o[..., 1], u[..., 1]) <= q[..., 1]) & (q[..., 1] <= np.maximum(o[..., 1], u[..., 1])))

	for i in range(n - 2):
		j = np.arange(i + 2, n)
		if i == 0:
			j = j[j != n - 1]       # the last edge shares p_0 with edge 0
		if len(j) == 0:
			continue
		a0, a1 = np.broadcast_to(p0[i], (len(j), 2)), np.broadcast_to(p1[i], (len(j), 2))
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


def latest_overrides(project) -> dict:
	"""``{piece: override}``: the last line of each piece."""
	return {o["piece"]: o for o in read_overrides(project) if o.get("piece")}


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


def append_override(project, piece: str, contour_px, nota: str = "") -> dict:
	"""Validate (:func:`check_override`) and append one line to ``overrides.jsonl``; returns the line
	or ``{'error': str}`` (nothing written). The override is applied by :func:`src.render.rebuild_piece`."""
	pts, err = check_override(project, piece, contour_px)
	if err:
		return {"error": err}
	p = project.piece(piece)
	rec = {"t": _dt.datetime.now().isoformat(timespec="seconds"), "autor": "manual", "scan_id": p.scan_id,
		   "piece": piece, "index_in_scan": int(p.index_in_scan),
		   "contour_px": [[round(float(x), 2), round(float(y), 2)] for x, y in pts], "nota": str(nota or "")}
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
