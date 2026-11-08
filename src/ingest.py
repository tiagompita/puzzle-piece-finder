"""Ingest a flatbed scan of loose pieces into a project (``python -m src.ingest``).

Usage::

	python -m src.ingest <scan.jpg|lote.pdf> [...] --lote N [--dpi 300] [--uploads DIR] [--kind soltas]
		[--known-cells gt.json] [--montado pNN | --blocos pNN [--no-auto-anchor]] [--project projects/alpes]
		[--profile projects/alpes/puzzle.json]

Several files / a multi-page PDF = several sheets of the same bag (:func:`ingest_sheets`, :mod:`src.sheets`):
the numbering of the bag continues sheet after sheet. A sheet whose sha256 is already a scan of the project is
**ignored** («já importada», nothing logged). Two phases: :func:`segment_sheet` (pure, minutes, no lock) and
:func:`commit_sheet` (seconds, under the caller's write lock); :func:`ingest_scan` = both. Warnings (never a
refusal) in ``scan.meta``: ``escala`` (median non-F chord vs the profile's cell, :func:`scale_check`) and ``fundo``
(background ΔE to the profile's ``background_lab``, :func:`background_check`).

Pipeline (:func:`segment_sheet` + :func:`commit_sheet`): ``segment_scan`` (crops kept in the scan frame,
``normalize_rotation=False``, so crop, contour and Shape share one frame) → fragments
rejected (area < ``MIN_PIECE_MM2``) → ``is_cluster`` or area > ``DOUBLE_AREA_FACTOR`` ×
median flagged ``objeto_duplo``, ``contacto`` (interlocked/touching pieces re-partitioned by
``segment_scan``; ``com`` = ``index_in_scan`` of the others) copied into ``flags`` and drawn in red on the
overlay when ``confianca == 'baixa'`` → ``shape.analyse`` → :func:`grid_order` numbering
(``n_no_lote``, continuing the bag's numbering if the bag already has pieces) → RGBA crop in
``crops/`` → ``mean_lab`` → numbered overlay ``overlays/<scan>.jpg`` (the sheet kept with
the bag).

``--known-cells gt.json``: ``{"cells": [{"index": n, "cell": [l, c], "theta_deg": opt}],
"theta_deg": opt}`` where ``index`` (alias ``n``) is the number printed on the overlay
(``n_no_lote``). Each such piece is placed (origin ``gt``) if its cell is full in the last
registered photo, otherwise it becomes ``posicao_conhecida``.

``--montado/--blocos pNN`` delegate to ``src.legacy.ingest_page``; ``--no-auto-anchor`` leaves
every section unanchored (anchor later with ``legacy.solve_project_sections``, which uses the
twins between pages).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

__all__ = ["MIN_PIECE_MM2", "DOUBLE_AREA_FACTOR", "SEG_FLAG_KEYS", "SCALE_OK", "SCALE_MIN_SIDES", "AREA_PER_CELL", "BG_DE_WARN",
		   "SheetResult", "grid_order", "local_mean_lab", "seg_flags", "scale_check", "lab8_to_cie", "background_check",
		   "segment_sheet", "commit_sheet", "prepare_sheet", "sheet_outcome", "ingest_scan", "ingest_sheets", "draw_overlay", "sheet_overlay", "write_overlay",
		   "open_project", "add_project_args", "main"]

MIN_PIECE_MM2 = 150.0        # below this a component is a fragment (strip remnant, dust), never a piece
DOUBLE_AREA_FACTOR = 1.6     # area > 1.6 x median of the scan -> objeto_duplo (two mated pieces?)
ROW_BREAK_FRAC = 0.5         # grid_order: new row when the centre y jumps > 0.5 x median bbox height
OVERLAY_MAX_W = 2400         # px, width of the saved overlay
HIGHLIGHT_RGB = (255, 191, 0)  # amber: the highlighted piece of sheet_overlay
COL_DOUBLE = (255, 0, 255)     # objeto_duplo
COL_BORDER = (255, 160, 0)     # piece with a flat side
COL_PIECE = (0, 255, 255)
COL_CONTACT_LOW = (255, 0, 0)  # contacto with confianca 'baixa' (interlocked pieces, partition uncertain)
SCALE_OK = (0.95, 1.05)      # median non-F chord / sqrt(cell_w * cell_h) outside this -> scale warning (never a refusal)
SCALE_MIN_SIDES = 3          # fewer non-F sides of 4-corner pieces than this -> every side of those pieces counts
AREA_PER_CELL = 1.12         # median piece area / cell area (Alpes: 370 mm2 / (18.5 x 17.9) mm2); second line of the warning
BG_DE_WARN = 15.0            # dE76 of the scan background to the profile's background_lab above this -> warning
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PROJECT = os.path.join("projects", "alpes")
DEFAULT_PROFILE = os.path.join(REPO, "projects", "alpes", "puzzle.json")


# ---------------------------------------------------------------- pure helpers
def grid_order(bboxes) -> list:
	"""Reading-order number (1-based) of each bbox ``(x, y, w, h)``: rows by centre y (a new row
	when the jump exceeds ``ROW_BREAK_FRAC`` × median height), left to right within a row.

	Promoted from ``tools/diagnostico/gemeos/segcache.grid_order``; returns ``n[i]`` for input i.
	"""
	b = np.asarray(bboxes, float).reshape(-1, 4)
	if len(b) == 0:
		return []
	cy = b[:, 1] + b[:, 3] / 2
	cx = b[:, 0] + b[:, 2] / 2
	o = np.argsort(cy, kind="stable")
	hmed = float(np.median(b[:, 3]))
	rows, cur = [], [int(o[0])]
	for i in o[1:]:
		if cy[i] - cy[cur[-1]] > ROW_BREAK_FRAC * hmed:
			rows.append(cur)
			cur = [int(i)]
		else:
			cur.append(int(i))
	rows.append(cur)
	n = [0] * len(b)
	k = 0
	for r in rows:
		for i in sorted(r, key=lambda j: cx[j]):
			k += 1
			n[i] = k
	return n


def local_mean_lab(rgba: np.ndarray) -> list:
	"""Mean CIE Lab (L 0..100, float OpenCV conversion) over the opaque pixels of an RGBA crop."""
	import cv2
	a = np.asarray(rgba)
	m = a[..., 3] > 127
	if not m.any():
		return [float("nan")] * 3
	lab = cv2.cvtColor(a[..., :3].astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB)
	return [round(float(v), 2) for v in lab[m].mean(0)]


def _mean_lab(rgba: np.ndarray) -> list:
	try:
		from src.locate import piece_mean_lab
		v = piece_mean_lab(rgba)
		return [round(float(x), 2) for x in np.asarray(v, float).reshape(-1)[:3]]
	except Exception:  # noqa: BLE001 - src.locate optional / different signature: local fallback
		return local_mean_lab(rgba)


def draw_overlay(rgb: np.ndarray, items: list, title: str = "", *, max_w: Optional[float] = OVERLAY_MAX_W,
				 max_px: Optional[float] = None) -> np.ndarray:
	"""Scan (RGB) with each piece contour and a large number, returned as BGR.

	``items`` = [{contour (scan px), n, colour (RGB), highlight (opt.)}]; a highlighted item
	gets a thicker amber contour and a larger, thicker label. Downscale so the width is
	<= ``max_w`` and the long side <= ``max_px`` (None = no limit); labels scale with the
	output width.
	"""
	import cv2
	img = np.ascontiguousarray(rgb[..., ::-1]).copy()
	H, W = img.shape[:2]
	s = 1.0
	if max_w:
		s = min(s, float(max_w) / W)
	if max_px:
		s = min(s, float(max_px) / max(H, W))
	if s < 1.0:
		img = cv2.resize(img, (max(1, int(W * s)), max(1, int(H * s))), interpolation=cv2.INTER_AREA)
	lw = max(2, int(round(img.shape[1] / 600)))
	fs = img.shape[1] / 900.0
	for it in sorted(items, key=lambda t: bool(t.get("highlight"))):   # highlight drawn last (on top)
		cnt = (np.asarray(it["contour"], float).reshape(-1, 2) * s).astype(np.int32)
		if len(cnt) == 0:
			continue
		hl = bool(it.get("highlight"))
		col = tuple(int(v) for v in (HIGHLIGHT_RGB if hl else it.get("colour", COL_PIECE))[::-1])
		w, f = (3 * lw, 1.4 * fs) if hl else (lw, fs)
		cv2.polylines(img, [cnt], True, col, w, cv2.LINE_AA)
		txt = str(it["n"])
		tt = (5 if hl else 3) * lw
		(tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, f, tt)
		cx, cy = cnt.mean(0)
		org = (int(cx - tw / 2), int(cy + th / 2))
		cv2.putText(img, txt, org, cv2.FONT_HERSHEY_SIMPLEX, f, (0, 0, 0), tt + 4, cv2.LINE_AA)
		cv2.putText(img, txt, org, cv2.FONT_HERSHEY_SIMPLEX, f, col if hl else (255, 255, 255), tt, cv2.LINE_AA)
	if title:
		cv2.putText(img, title, (20, int(40 * fs) + 10), cv2.FONT_HERSHEY_SIMPLEX, fs * 0.8, (0, 0, 0), 2 * lw + 4,
					cv2.LINE_AA)
		cv2.putText(img, title, (20, int(40 * fs) + 10), cv2.FONT_HERSHEY_SIMPLEX, fs * 0.8, (255, 255, 255), 2 * lw,
					cv2.LINE_AA)
	return img


SEG_FLAG_KEYS = ("touches_frame", "touches_strip", "is_cluster", "objeto_duplo", "contacto", "recuperado_mm2",
				 "suspeita_recorte")


def seg_flags(p: dict, area_mm2: float, median_mm2: float) -> dict:
	"""Piece ``flags`` derived from one ``segment_scan`` piece (keys :data:`SEG_FLAG_KEYS`).

	``objeto_duplo`` = ``is_cluster`` or area > :data:`DOUBLE_AREA_FACTOR` x the median area of
	the scan's kept pieces; ``contacto``, ``recuperado_mm2`` and ``suspeita_recorte`` only when the segmentation sets them.
	"""
	flags = {"touches_frame": bool(p.get("touches_frame")), "touches_strip": bool(p.get("touches_strip")),
			 "is_cluster": bool(p.get("is_cluster")),
			 "objeto_duplo": bool(p.get("is_cluster")) or area_mm2 > DOUBLE_AREA_FACTOR * median_mm2}
	if p.get("contacto"):
		flags["contacto"] = {"com": [int(i) for i in p["contacto"].get("com", [])],
							 "confianca": str(p["contacto"].get("confianca", "alta")),
							 "metodo": str(p["contacto"].get("metodo", "")),
							 "alterado": bool(p["contacto"].get("alterado"))}
	if p.get("recuperado_mm2"):
		flags["recuperado_mm2"] = float(p["recuperado_mm2"])
	if p.get("suspeita_recorte"):
		flags["suspeita_recorte"] = dict(p["suspeita_recorte"])  # only marks (razoes apendice / corte_de_contacto)
	return flags


def piece_label(p) -> int:
	"""Number printed for a piece on its sheet: ``n_no_lote``, else ``index_in_scan + 1``."""
	return int(p.n_no_lote) if p.n_no_lote is not None else int(p.index_in_scan) + 1


def _piece_colour(p) -> tuple:
	if p.flags.get("objeto_duplo"):
		return COL_DOUBLE
	if (p.flags.get("contacto") or {}).get("confianca") == "baixa":
		return COL_CONTACT_LOW
	return COL_BORDER if p.n_flat else COL_PIECE


# ---------------------------------------------------------------- service
def _scan_path(scan: dict) -> str:
	f = scan.get("file") or ""
	return f if os.path.isabs(f) else os.path.join(REPO, f)


def sheet_overlay(project, scan_id: str, *, highlight: Optional[str] = None, max_px: Optional[float] = None,
				  max_w: Optional[float] = None) -> np.ndarray:
	"""Numbered sheet of ``scan_id`` (BGR): the scan re-read from ``scans[sid]["file"]`` (repo
	relative or absolute), each piece's contour (:meth:`Project.contour_px`) and its
	:func:`piece_label` (the bag number, as written on the sheet kept with the bag).

	``highlight`` = piece id drawn in amber with a thicker label; ``max_px`` / ``max_w`` cap
	the long side / width. Raises ``ValueError`` if the scan or its image is missing.
	"""
	from PIL import Image
	scan = project.model.scans.get(scan_id)
	if scan is None:
		raise ValueError(f"scan desconhecido {scan_id}")
	fp = _scan_path(scan)
	if not os.path.exists(fp):
		raise ValueError(f"imagem do scan {scan_id} não encontrada: {fp}")
	with Image.open(fp) as im:
		rgb = np.asarray(im.convert("RGB"))
	pcs = sorted((p for p in project.pieces.values() if p.scan_id == scan_id), key=lambda q: (piece_label(q), q.id))
	items = []
	for p in pcs:
		cnt = project.contour_px(p.id)
		if cnt is None:
			continue
		items.append({"contour": cnt, "n": piece_label(p), "colour": _piece_colour(p), "highlight": p.id == highlight})
	lote = scan.get("lote")
	title = f"{scan_id} lote {lote}: {len(pcs)} pecas" if lote is not None else f"{scan_id}: {len(pcs)} pecas"
	return draw_overlay(rgb, items, title=title, max_w=max_w, max_px=max_px)


def write_overlay(project, scan_id: str) -> str:
	"""Write ``overlays/<scan_id>.jpg`` (:func:`sheet_overlay`, width <= ``OVERLAY_MAX_W``); returns its path."""
	import cv2
	ov = sheet_overlay(project, scan_id, max_w=OVERLAY_MAX_W)
	os.makedirs(project.p("overlays"), exist_ok=True)
	ov_path = project.p("overlays", f"{scan_id}.jpg")
	ok, buf = cv2.imencode(".jpg", ov, [cv2.IMWRITE_JPEG_QUALITY, 88])
	if not ok:
		raise ValueError(f"falha a codificar o overlay de {scan_id}")
	buf.tofile(ov_path)
	return ov_path


@dataclass
class SheetResult:
	"""What :func:`segment_sheet` read from one sheet, before anything is written to a project.

	``pieces``: one dict per kept piece in reading order (``n`` = :func:`grid_order` number within the sheet,
	``index_in_scan``, ``shape``, ``contour`` (scan px), ``bbox``, ``rgba`` (crop, in memory), ``mean_lab``,
	``area_mm2``, ``flags``). ``escala`` / ``fundo``: :func:`scale_check` / :func:`background_check` (None
	without a profile). ``skipped``: the sheet's sha256 is already a scan of the project (``scan_id``; nothing
	segmented). ``fonte``: where the sheet came from (``{origem, pagina, dpi_fontes}``, :mod:`src.sheets`)."""

	scan_path: str
	dpi: float
	kind: str = "soltas"
	sha256: Optional[str] = None
	mm_per_px: Optional[float] = None
	method: Optional[str] = None
	n_segmented: int = 0
	pieces: list = field(default_factory=list)
	rejected: list = field(default_factory=list)
	median_mm2: float = 0.0
	background_lab8: Optional[list] = None
	escala: Optional[dict] = None
	fundo: Optional[dict] = None
	avisos: list = field(default_factory=list)
	fonte: Optional[dict] = None
	error: Optional[str] = None
	skipped: Optional[str] = None
	segundos: float = 0.0


def _median(v) -> Optional[float]:
	v = [float(x) for x in v if x is not None and np.isfinite(x)]
	return float(np.median(v)) if v else None


def scale_check(shapes, cell_mm: dict, dpi: float) -> dict:
	"""Piece scale against the profile (pure): median chord of the non-F sides of the pieces with 4 corners vs
	``sqrt(cell_w * cell_h)``; with fewer than :data:`SCALE_MIN_SIDES` such sides the F sides count too.
	``{n_lados, lados, corda_mediana_mm, nominal_mm, razao, dpi_compativel, area_mediana_mm2, area_nominal_mm2,
	razao_area, aviso}``; ``aviso`` (text, never a refusal) when ``razao`` is outside :data:`SCALE_OK`."""
	nominal = float(np.sqrt(float(cell_mm["w"]) * float(cell_mm["h"])))
	area_nom = AREA_PER_CELL * float(cell_mm["w"]) * float(cell_mm["h"])
	ok = [s for s in shapes if s is not None and s.ok]
	tb = [L for s in ok for L, k in zip(s.lens, s.types) if k != "F"]
	which = "não-F"
	if len(tb) < SCALE_MIN_SIDES:
		tb = [L for s in ok for L in s.lens]
		which = "todos"
	med = _median(tb)
	amed = _median([s.area_mm2 for s in shapes if s is not None])
	out = {"n_lados": len(tb), "lados": which, "corda_mediana_mm": None if med is None else round(med, 2),
		   "nominal_mm": round(nominal, 2), "razao": None, "dpi_compativel": None,
		   "area_mediana_mm2": None if amed is None else round(amed, 1), "area_nominal_mm2": round(area_nom, 1),
		   "razao_area": None if amed is None else round(amed / area_nom, 3), "aviso": None}
	if med is None or nominal <= 0:
		return out
	r = med / nominal
	out["razao"] = round(r, 3)
	out["dpi_compativel"] = round(float(dpi) * r)
	if not (SCALE_OK[0] <= r <= SCALE_OK[1]):
		txt = (f"escala: corda mediana {med:.1f} mm = {r:.2f} do nominal ({nominal:.1f} mm); dpi {float(dpi):g} "
			   f"declarado pode estar errado; dpi compatível ≈ {round(float(dpi) * r)}")
		if amed is not None:
			txt += f"\nárea mediana {amed:.0f} mm² = {amed / area_nom:.2f} da esperada ({area_nom:.0f} mm²)"
		out["aviso"] = txt.replace(".", ",")
	return out


def lab8_to_cie(lab8) -> list:
	"""OpenCV 8-bit Lab (``L * 255 / 100``, ``a + 128``, ``b + 128``) -> CIE Lab."""
	L, a, b = (float(x) for x in lab8)
	return [L * 100.0 / 255.0, a - 128.0, b - 128.0]


def background_check(lab8, profile_lab) -> dict:
	"""Scan background (``segment_scan``'s ``scan_background_lab``, OpenCV 8-bit) vs the profile's
	``background_lab`` (CIE): ``{lab, dE, aviso}`` (ΔE76; ``aviso`` above :data:`BG_DE_WARN`, never a refusal)."""
	if lab8 is None or profile_lab is None:
		return {"lab": None, "dE": None, "aviso": None}
	lab = lab8_to_cie(lab8)
	dE = float(np.linalg.norm(np.asarray(lab) - np.asarray(profile_lab, float)))
	aviso = None
	if dE > BG_DE_WARN:
		aviso = (f"fundo: ΔE {dE:.0f} ao fundo do perfil (Lab {lab[0]:.0f}/{lab[1]:.0f}/{lab[2]:.0f} vs "
				 f"{profile_lab[0]:g}/{profile_lab[1]:g}/{profile_lab[2]:g}); a segmentação pode falhar")
	return {"lab": [round(x, 1) for x in lab], "dE": round(dE, 1), "aviso": aviso}


def segment_sheet(scan_path: str, *, dpi: float = 300, segment=None, kind: str = "soltas", project=None,
				  profile=None) -> SheetResult:
	"""Read one sheet (pure: nothing is written anywhere): ``segment_scan`` (``normalize_rotation=False``),
	fragments below :data:`MIN_PIECE_MM2` rejected, :func:`grid_order`, ``shape.analyse``, :func:`seg_flags`, RGBA
	crops and mean Lab in memory, the scale and background checks (with ``profile``, or ``project.profile``).

	With ``project``, a sheet whose sha256 is already a scan of the project is not segmented (``skipped`` = that
	scan id; segmentation takes minutes). Errors go to ``result.error``."""
	from PIL import Image
	from src.segmentation import piece_to_rgba
	from src.shape import analyse
	from src.state import file_sha256

	t0 = time.time()
	res = SheetResult(scan_path=scan_path, dpi=float(dpi), kind=kind)
	if not os.path.exists(scan_path):
		res.error = f"scan não encontrado: {scan_path}"
		return res
	res.sha256 = file_sha256(scan_path)
	if project is not None:
		old = project.scan_by_sha256(res.sha256)
		if old is not None:
			res.skipped = old
			return res
		profile = profile or project.profile
	if segment is None:
		from src.segmentation import segment_scan as segment
	try:
		with Image.open(scan_path) as im:
			photo = im.convert("RGB")
	except Exception as e:  # noqa: BLE001
		res.error = f"imagem ilegível: {type(e).__name__}: {e}"
		return res
	seg = segment(photo, dpi=dpi, normalize_rotation=False)
	if "error" in seg:
		res.error = f"segment_scan: {seg['error']}"
		return res
	mmpp = float(seg.get("mm_per_px") or 25.4 / float(dpi))
	res.mm_per_px, res.method = mmpp, seg.get("method")
	raw = seg["pieces"]
	res.n_segmented = len(raw)
	kept = []
	for p in raw:
		area = float(p["area_px"]) * mmpp * mmpp
		if area < MIN_PIECE_MM2:
			res.rejected.append({"index": int(p["index"]), "area_mm2": round(area, 1),
								 "touches_strip": bool(p.get("touches_strip")), "reason": f"área < {MIN_PIECE_MM2:g} mm²"})
		else:
			kept.append((p, area))
	res.median_mm2 = float(np.median([a for _, a in kept])) if kept else 0.0
	order = grid_order([p["bbox"] for p, _ in kept])
	for (p, area), n in sorted(zip(kept, order), key=lambda t: t[1]):
		cnt = np.asarray(p["contour"]).reshape(-1, 2)
		rgba = np.ascontiguousarray(np.asarray(piece_to_rgba(p["image"], p["mask"])))
		res.pieces.append({"n": int(n), "index_in_scan": int(p["index"]), "shape": analyse(cnt, mmpp), "contour": cnt,
						   "bbox": [int(v) for v in p["bbox"]], "rgba": rgba, "mean_lab": _mean_lab(rgba),
						   "area_mm2": round(area, 2), "flags": seg_flags(p, area, res.median_mm2)})
	bg = seg.get("scan_background_lab")
	res.background_lab8 = None if bg is None else [float(x) for x in bg]
	if profile is not None:
		_checks(res, profile)
	res.segundos = round(time.time() - t0, 2)
	return res


def _checks(res: SheetResult, profile) -> None:
	res.escala = scale_check([p["shape"] for p in res.pieces], profile.cell_mm, res.dpi)
	if not res.pieces and len(res.rejected) >= SCALE_MIN_SIDES:
		# every component below MIN_PIECE_MM2: a scan at half the declared resolution looks exactly like this
		am = _median([e["area_mm2"] for e in res.rejected])
		an = res.escala["area_nominal_mm2"]
		if am and an:
			r = float(np.sqrt(am / an))
			res.escala.update(area_mediana_mm2=round(am, 1), razao_area=round(am / an, 3), dpi_compativel=round(res.dpi * r))
			res.escala["aviso"] = (f"escala: todas as {len(res.rejected)} componentes ficaram abaixo de {MIN_PIECE_MM2:g} mm² "
								   f"(mediana {am:.0f} mm² = {am / an:.2f} da área esperada, {an:.0f} mm²); dpi {res.dpi:g} "
								   f"declarado pode estar errado; dpi compatível ≈ {round(res.dpi * r)}").replace(".", ",")
	res.fundo = background_check(res.background_lab8, profile.background_lab)
	for k in ("escala", "fundo"):
		av = (getattr(res, k) or {}).get("aviso")
		if av and av not in res.avisos:
			res.avisos.append(av)


def commit_sheet(project, result: SheetResult, lote: Optional[int], *, known_cells: Optional[dict] = None) -> dict:
	"""Add a segmented sheet to ``project`` (the caller holds the project's write lock): ``add_scan`` (refused when
	the sha256 is already registered: ``{skipped: True, scan_id, lote, motivo}``, nothing logged), the bag numbering
	continued (``n0`` = the largest ``n_no_lote`` of the bag, computed here), ``add_piece`` + crops
	``crops/P####.png``, the numbered overlay, ``known_cells``, ``project.save()``.

	``scan.meta`` keeps ``n_segmented``, ``n_rejected``, ``method``, ``mm_per_px``, ``escala``, ``fundo``, ``avisos``
	and ``fonte``. Returns ``{scan_id, lote, pieces, numbers, rejected, double, overlay, known, n_segmented, escala,
	fundo, avisos}`` or ``{'error': str}``."""
	from PIL import Image
	from src.state import StateError

	if result.error:
		return {"error": result.error}
	old = result.skipped or project.scan_by_sha256(result.sha256)
	if old is not None:
		return _skipped(project, old)
	if result.escala is None:
		_checks(result, project.profile)
	meta = {"n_segmented": result.n_segmented, "n_rejected": len(result.rejected), "method": result.method,
			"mm_per_px": result.mm_per_px, "escala": result.escala, "fundo": result.fundo, "avisos": list(result.avisos)}
	if result.fonte:
		meta["fonte"] = result.fonte
	try:
		sid = project.add_scan(result.scan_path, dpi=result.dpi, lote=lote, kind=result.kind, meta=meta, unique=True)
	except StateError:
		return _skipped(project, project.scan_by_sha256(result.sha256))
	n0 = max([q.n_no_lote or 0 for q in project.pieces.values() if lote is not None and q.lote == lote
			  and q.scan_id != sid] or [0])
	os.makedirs(project.p("crops"), exist_ok=True)
	ids, numbers, double = [], {}, []
	for p in result.pieces:
		pid_next = f"P{int(project.meta['next_ids']['P']):04d}"
		crop_rel = f"crops/{pid_next}.png"
		Image.fromarray(p["rgba"]).save(project.p(crop_rel))
		pid = project.add_piece(sid, {
			"index_in_scan": p["index_in_scan"], "n_no_lote": n0 + p["n"], "shape": p["shape"], "contour": p["contour"],
			"bbox": p["bbox"], "crop_path": crop_rel, "mean_lab": p["mean_lab"], "area_mm2": p["area_mm2"],
			"flags": p["flags"],
		})
		assert pid == pid_next, (pid, pid_next)
		ids.append(pid)
		numbers[pid] = n0 + p["n"]
		if p["flags"]["objeto_duplo"]:
			double.append(pid)
	ov_path = write_overlay(project, sid)
	known = _apply_known_cells(project, ids, numbers, known_cells) if known_cells else []
	project.save()
	return {"scan_id": sid, "lote": lote, "pieces": ids, "numbers": numbers, "rejected": result.rejected, "double": double,
			"overlay": ov_path, "known": known, "n_segmented": result.n_segmented, "escala": result.escala,
			"fundo": result.fundo, "avisos": list(result.avisos)}


def _skipped(project, sid: str) -> dict:
	lote = project.model.scans[sid].get("lote")
	return {"skipped": True, "scan_id": sid, "lote": lote, "pieces": [], "numbers": {},
			"motivo": f"folha já importada como {sid} (lote {lote})"}


def ingest_scan(project, scan_path: str, lote: Optional[int], *, dpi: float = 300, kind: str = "soltas",
				known_cells: Optional[dict] = None, segment=None) -> dict:
	"""Segment ``scan_path`` and add its pieces to ``project`` (then ``project.save()``):
	``commit_sheet(project, segment_sheet(...))``.

	Returns ``{scan_id, pieces: [ids], numbers: {id: n_no_lote}, rejected: [...], double: [ids],
	overlay, known: [...], n_segmented, escala, fundo, avisos}``, ``{skipped: True, scan_id, motivo}`` when the file
	is already a scan of the project, or ``{'error': str}``. ``segment`` overrides ``segment_scan`` (tests).
	"""
	if not os.path.exists(scan_path):
		return {"error": f"scan não encontrado: {scan_path}"}
	res = segment_sheet(scan_path, dpi=dpi, segment=segment, kind=kind, project=project)
	return commit_sheet(project, res, lote, known_cells=known_cells)


def prepare_sheet(sheet, project, *, dpi: Optional[float] = None, segment=None, kind: str = "soltas") -> SheetResult:
	""":func:`segment_sheet` of a :class:`src.sheets.Sheet` (outside any lock): resolution ``sheet.dpi or dpi or 300``,
	``fonte`` = where it came from, the sheet's own warnings first (and one when the file's dpi overrides ``dpi``)."""
	d = float(sheet.dpi or dpi or 300)
	res = segment_sheet(sheet.caminho, dpi=d, segment=segment, kind=kind, project=project)
	res.fonte = {"origem": sheet.origem, "pagina": sheet.pagina, "dpi_fontes": dict(sheet.dpi_fontes), "dpi": d,
				 "dpi_argumento": dpi}
	if sheet.dpi and dpi and abs(float(sheet.dpi) - float(dpi)) > 0.02 * float(dpi):
		res.avisos.append(f"dpi: o ficheiro diz {float(sheet.dpi):g}, pedido {float(dpi):g}; uso {float(sheet.dpi):g}")
	res.avisos = list(sheet.avisos) + res.avisos
	return res


def sheet_outcome(base: dict, res: SheetResult, r: dict) -> dict:
	"""One row of :func:`ingest_sheets`: ``base`` (k, n, caminho, origem, pagina) + the :func:`commit_sheet` dict +
	``dpi``, ``estado`` (``ok`` | ``ignorada`` | ``erro``) and ``avisos``."""
	out = dict(base, dpi=res.dpi, **r)
	out["estado"] = "erro" if "error" in r else ("ignorada" if r.get("skipped") else "ok")
	out.setdefault("avisos", list(res.avisos))
	return out


def ingest_sheets(project, sheets, lote: Optional[int], *, dpi: Optional[float] = None, segment=None, progress=None,
				  lock=None, kind: str = "soltas") -> list:
	"""Ingest several sheets (:class:`src.sheets.Sheet`) into bag ``lote``, in the given order: each one segmented
	outside ``lock`` (:func:`segment_sheet`), then committed under it (:func:`commit_sheet`; the numbering of the
	bag continues sheet after sheet). Resolution per sheet: ``sheet.dpi or dpi or 300``. ``progress(k, n, sheet,
	result)`` after each sheet. Returns one dict per sheet: the :func:`commit_sheet` dict plus ``k``, ``caminho``,
	``origem``, ``pagina``, ``dpi`` and ``estado`` (``ok`` | ``ignorada`` | ``erro``)."""
	out = []
	n = len(sheets)
	for k, sh in enumerate(sheets, 1):
		base = {"k": k, "n": n, "caminho": sh.caminho, "origem": sh.origem, "pagina": sh.pagina}
		if sh.erro or not sh.caminho:
			r = dict(base, estado="erro", error=sh.erro or "folha sem imagem", avisos=list(sh.avisos))
		else:
			res = prepare_sheet(sh, project, dpi=dpi, segment=segment, kind=kind)
			with (lock if lock is not None else contextlib.nullcontext()):
				r = commit_sheet(project, res, lote)
			r = sheet_outcome(base, res, r)
		out.append(r)
		if progress is not None:
			progress(k, n, sh, r)
	return out


def _apply_known_cells(project, ids: list, numbers: dict, gt: dict) -> list:
	by_n = {numbers[pid]: pid for pid in ids}
	photo = project.last_photo()
	out = []
	for e in gt.get("cells", []):
		n = int(e.get("index", e.get("n")))
		cell = (int(e["cell"][0]), int(e["cell"][1]))
		theta = e.get("theta_deg", gt.get("theta_deg"))
		pid = by_n.get(n)
		if pid is None:
			out.append({"n": n, "cell": cell, "error": "número não existe neste scan"})
			continue
		full = photo is not None and photo.value(*cell) == 1
		try:
			if full:
				project.place(pid, cell, origin="gt", theta_deg=theta)
			else:
				project.set_position_known(pid, cell, origin="gt", theta_deg=theta)
			out.append({"n": n, "piece": pid, "cell": cell, "estado": project.piece(pid).estado})
		except ValueError as err:
			out.append({"n": n, "piece": pid, "cell": cell, "error": str(err)})
	return out


# ---------------------------------------------------------------- CLI
def add_project_args(ap: argparse.ArgumentParser) -> None:
	ap.add_argument("--project", default=DEFAULT_PROJECT, help="pasta do projeto (projects/<id>)")
	ap.add_argument("--profile", default=DEFAULT_PROFILE, help="puzzle.json usado se o projeto ainda não existir")


def open_project(args):
	"""Open ``args.project`` (created from ``args.profile`` if it has no project.json)."""
	from src.state import Project
	created = not os.path.exists(os.path.join(args.project, "project.json"))
	pr = Project.open_or_create(args.project, args.profile)
	if created:
		print(f"projeto criado em {pr.path} (perfil {args.profile})")
	return pr


def _print_sheet(pr, r: dict) -> None:
	src = os.path.basename(r.get("origem") or r.get("caminho") or "?") + (f" p.{r['pagina']}" if r.get("pagina") else "")
	head = f"[{r.get('k', 1)}/{r.get('n', 1)}] {src}"
	if r.get("estado") == "erro" or "error" in r:
		print(f"{head}: ERRO: {r.get('error')}")
		return
	if r.get("skipped"):
		print(f"{head}: ignorada: {r['motivo']}")
		return
	nums = [r["numbers"][pid] for pid in r["pieces"]]
	rng = f"{min(nums)}..{max(nums)}" if nums else "-"
	print(f"{head}: {r['scan_id']} lote {r.get('lote')}: {len(r['pieces'])} peças, números {rng} (dpi {r.get('dpi', '?')}; "
		  f"segmentadas {r['n_segmented']}, fragmentos rejeitados {len(r['rejected'])}, objeto_duplo {len(r['double'])})")
	for pid in r["pieces"]:
		p = pr.piece(pid)
		fl = ",".join(k for k, v in p.flags.items() if v)
		print(f"  #{p.n_no_lote:>3} {pid} cls {p.cls or '-':4s} F={p.n_flat} área {p.area_mm2:6.1f} mm² "
			  f"cordas {[round(x, 1) for x in p.chords_mm]} {fl}")
	for e in r["rejected"]:
		print(f"  rejeitado: índice {e['index']} ({e['reason']}, {e['area_mm2']} mm²)")
	for e in r.get("known") or []:
		print(f"  gt: {e}")
	esc, fu = r.get("escala") or {}, r.get("fundo") or {}
	if esc.get("razao") is not None:
		print(f"  escala: corda mediana {esc['corda_mediana_mm']} mm / nominal {esc['nominal_mm']} mm = {esc['razao']} "
			  f"({esc['n_lados']} lados {esc['lados']}); área mediana {esc['area_mediana_mm2']} mm²")
	if fu.get("dE") is not None:
		print(f"  fundo: Lab {fu['lab']} ΔE {fu['dE']} ao fundo do perfil")
	for a in r.get("avisos") or []:
		print(f"  AVISO: {a}")
	print(f"  overlay: {r['overlay']}")


def main(argv=None) -> int:
	ap = argparse.ArgumentParser(prog="python -m src.ingest",
								 description="Ingere scans de peças soltas (imagens ou PDF, uma folha por página) num projeto.")
	ap.add_argument("scans", nargs="+", metavar="ficheiro", help="imagens (JPEG/PNG/TIFF) ou PDF; várias folhas do mesmo saco")
	ap.add_argument("--lote", type=int, default=None, help="número do saco (= lote)")
	ap.add_argument("--dpi", type=float, default=None,
					help="resolução quando o ficheiro não a diz (PDF: MediaBox; JPEG: JFIF); omissão 300")
	ap.add_argument("--kind", default="soltas")
	ap.add_argument("--uploads", default=None, help="pasta onde ficam os JPEG extraídos dos PDF (omissão: a pasta do PDF)")
	ap.add_argument("--known-cells", default=None, help="gt.json {cells: [{index, cell: [l, c]}], theta_deg} (uma só imagem)")
	g = ap.add_mutually_exclusive_group()
	g.add_argument("--montado", default=None, metavar="pNN")
	g.add_argument("--blocos", default=None, metavar="pNN")
	ap.add_argument("--no-auto-anchor", action="store_true",
					help="páginas do legado: não ancorar pela própria página (ancorar depois pela solução conjunta)")
	add_project_args(ap)
	args = ap.parse_args(argv)
	try:
		pr = open_project(args)
	except ValueError as e:
		print(f"erro: {e}")
		return 1
	if args.montado or args.blocos:
		if len(args.scans) != 1:
			print("erro: --montado/--blocos aceitam uma só página")
			return 1
		try:
			from src import legacy
		except ImportError:
			print("erro: src/legacy.py ainda não existe (passo 4 do plano M10+M12); páginas do legado não podem ser ingeridas")
			return 1
		kind, page = ("montado", args.montado) if args.montado else ("blocos", args.blocos)
		r = legacy.ingest_page(pr, args.scans[0], kind, page, auto_anchor=not args.no_auto_anchor)
		if isinstance(r, dict) and "error" in r:
			print(f"erro: {r['error']}")
			return 1
		pr.save()
		print(r)
		return 0
	if args.lote is None:
		print("erro: --lote é obrigatório para peças soltas")
		return 1
	from src.sheets import expand_sources
	out_dir = args.uploads or os.path.dirname(os.path.abspath(args.scans[0]))
	sheets = expand_sources(args.scans, out_dir=out_dir)
	for sh in sheets:
		if sh.pagina:
			print(f"{os.path.basename(sh.origem)} p.{sh.pagina}: {sh.caminho or '-'} (dpi {sh.dpi}; fontes {sh.dpi_fontes})"
				  + (f" ERRO: {sh.erro}" if sh.erro else ""))
	if args.known_cells:
		if len(sheets) != 1 or sheets[0].erro:
			print("erro: --known-cells exige exatamente uma folha legível")
			return 1
		with open(args.known_cells, encoding="utf-8") as f:
			gt = json.load(f)
		sh = sheets[0]
		d = float(sh.dpi or args.dpi or 300)
		r = ingest_scan(pr, sh.caminho, args.lote, dpi=d, kind=args.kind, known_cells=gt)
		if "error" in r:
			print(f"erro: {r['error']}")
			return 1
		res = [dict(r, k=1, n=1, origem=sh.origem, caminho=sh.caminho, dpi=d,
					estado="ignorada" if r.get("skipped") else "ok")]
	else:
		res = ingest_sheets(pr, sheets, args.lote, dpi=args.dpi, kind=args.kind,
							progress=lambda k, n, sh, r: _print_sheet(pr, r))
	if args.known_cells:
		_print_sheet(pr, res[0])
	ok = sum(r["estado"] == "ok" for r in res)
	ign = sum(r["estado"] == "ignorada" for r in res)
	err = sum(r["estado"] == "erro" for r in res)
	print(f"{len(res)} folhas: {ok} importadas, {ign} ignoradas (já importadas), {err} com erro")
	bad = pr.check_invariants(disk=True)
	if bad:
		print("INVARIANTES VIOLADAS: " + "; ".join(bad))
		return 1
	return 1 if err else 0


if __name__ == "__main__":
	sys.exit(main())
