"""Registration of the reference art against the assembled board: one affine board mm -> art px.

``python -m src.artreg [--project projects/alpes] [--dry-run] [--report docs/diagnostico/arte]``

The profile's ``art.bbox`` assumes the art file spans the grid with a per-axis scale; the
physical print does not follow it exactly (BUG 4: the box art under the board drifts by up to
half a cell). Here the placed pieces themselves are the ground truth: the board is rendered
from the registered crops (layer ``pieces`` of :func:`src.render.compose_board`, corner
registration only, so the result does not depend on the art), resampled to a raster that
covers exactly ``rows x cols`` cells, and every placed cell is searched in the art rectified
with the current model (masked zero-mean NCC of L*, +/- ``SEARCH_CELL`` cell). A cell gives a
point ``board mm (cell centre) -> art px`` when its NCC >= ``NCC_MIN``, its peak is not on the
window border and its template has texture (L* std >= ``STD_MIN``); sky cells drop out by
themselves. A full 2x3 affine is fitted by weighted IRLS (weights = NCC, Huber then Tukey on
the residual in cells), then the search is repeated in a narrow window around the new model.

The result goes to ``puzzle.json`` as ``art.registration`` (:meth:`src.profile.PuzzleProfile.art_matrix`),
which every consumer reads through :func:`src.locate.load_art_rectified`. Residuals are
reported in cells, before (bbox model) and after, on the same points.

Pure: :func:`measure_points`, :func:`fit_affine`, :func:`decompose`, :func:`residual_cells`,
:func:`register_art`. I/O: :func:`render_board`, :func:`write_registration`, :func:`run`, :func:`main`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

import cv2
import numpy as np

from src.locate import rectified_size, rectify_art

__all__ = [
	"SEARCH_CELL", "SEARCH_FINE_CELL", "PAD_CELL", "NCC_MIN", "STD_MIN", "COVER_MIN", "UPSAMPLE", "INLIER_CELL",
	"measure_points", "fit_affine", "decompose", "residual_cells", "register_art", "render_board",
	"art_coverage", "write_registration", "run", "main",
]

SEARCH_CELL = 1.5        # first pass: +/- cells around the prior (bbox) location
SEARCH_FINE_CELL = 0.35  # later passes: +/- cells around the current model
PAD_CELL = 0.25          # template = the cell grown by this (cells) on each side (the bare cell if that rim is not piece)
NCC_MIN = 0.5            # a point counts if its masked ZNCC >= this ...
STD_MIN = 2.0            # ... and its template L* std (masked) >= this (no texture = no point)
COVER_MIN = 0.85         # ... and >= this fraction of the template is piece
UPSAMPLE = 2             # working raster = the art's native grid resolution x this
INLIER_CELL = 0.3        # residual (cells) under which a point is an inlier of the final fit
HUBER_CELL = 0.1
TUKEY_CELL = 0.5


# ---------------------------------------------------------------- pure helpers
def _lstar(rgb: np.ndarray) -> np.ndarray:
	return cv2.cvtColor(np.ascontiguousarray(rgb[..., :3]).astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB)[..., 0]


def _corr(img, tpl):
	return cv2.matchTemplate(np.ascontiguousarray(img, np.float32), np.ascontiguousarray(tpl, np.float32), cv2.TM_CCORR)


def _masked_zncc(win: np.ndarray, tpl: np.ndarray, mask: np.ndarray) -> np.ndarray:
	"""Zero-mean NCC of ``tpl`` (only where ``mask``) at every valid position of ``win``."""
	m = mask.astype(np.float32)
	n = float(m.sum())
	tm = tpl * m
	sT, sTT = float(tm.sum()), float((tm * tpl).sum())
	sI = _corr(win, m)
	sII = _corr(win * win, m)
	sTI = _corr(win, tm)
	num = sTI - sT * sI / n
	vT = sTT - sT * sT / n
	vI = sII - sI * sI / n
	# flat window (e.g. replicated border outside the art): no correlation, not a huge spurious one
	ok = vI > 1e-3 * max(vT, 1e-6)
	Z = np.where(ok, num / np.sqrt(np.maximum(vT * vI, 1e-12)), 0.0)
	return np.clip(Z, -1.0, 1.0).astype(np.float32)


def _parabola(fm, f0, fp) -> float:
	den = fm - 2 * f0 + fp
	if abs(den) < 1e-12:
		return 0.0
	return float(np.clip(0.5 * (fm - fp) / den, -0.5, 0.5))


def residual_cells(M, P_mm: np.ndarray, Q_px: np.ndarray, cell_mm) -> np.ndarray:
	"""Residual (cells) of ``Q ~ M @ [P, 1]``: the art-px error brought back to board mm by ``M``'s linear part."""
	M = np.asarray(M, np.float64)
	r = Q_px - (P_mm @ M[:, :2].T + M[:, 2])
	r_mm = r @ np.linalg.inv(M[:, :2]).T
	return np.hypot(r_mm[:, 0] / float(cell_mm[0]), r_mm[:, 1] / float(cell_mm[1]))


def fit_affine(P_mm: np.ndarray, Q_px: np.ndarray, w=None, cell_mm=(1.0, 1.0), M0=None, iters: int = 30) -> dict:
	"""Robust weighted affine ``Q = M @ [P, 1]`` (IRLS: Huber then Tukey on the residual in cells).

	``w`` = prior weights (NCC). ``M0`` = starting model (default plain weighted LS). Returns
	``{'matrix': 2x3, 'weights': final robust weights, 'res_cells': residual per point}``.
	"""
	P = np.asarray(P_mm, np.float64)
	Q = np.asarray(Q_px, np.float64)
	w0 = np.ones(len(P)) if w is None else np.asarray(w, np.float64)
	X = np.c_[P, np.ones(len(P))]

	def wls(wt):
		sw = np.sqrt(wt)[:, None]
		sol, *_ = np.linalg.lstsq(X * sw, Q * sw, rcond=None)
		return sol.T

	M = wls(w0) if M0 is None else np.asarray(M0, np.float64)
	rw = np.ones(len(P))
	for it in range(iters):
		r = residual_cells(M, P, Q, cell_mm)
		if it < iters // 2:
			rw = np.where(r <= HUBER_CELL, 1.0, HUBER_CELL / np.maximum(r, 1e-12))
		else:
			rw = np.where(r < TUKEY_CELL, (1 - (r / TUKEY_CELL) ** 2) ** 2, 0.0)
		if (rw * w0).sum() < 1e-9 or np.count_nonzero(rw) < 3:
			break
		M = wls(w0 * rw)
	return {"matrix": M, "weights": rw, "res_cells": residual_cells(M, P, Q, cell_mm)}


def decompose(M) -> dict:
	"""Linear part of ``M`` = R(rot) @ [[sx, shear], [0, sy]] (QR); rotation in deg (positive = clockwise on screen, y down)."""
	L = np.asarray(M, np.float64)[:, :2]
	rot = float(np.degrees(np.arctan2(L[1, 0], L[0, 0])))
	c, s = np.cos(np.radians(rot)), np.sin(np.radians(rot))
	U = np.array([[c, s], [-s, c]]) @ L
	return {"scale_x_px_per_mm": float(U[0, 0]), "scale_y_px_per_mm": float(U[1, 1]),
			"shear": float(U[0, 1] / U[1, 1]), "rotation_deg": rot,
			"translation_px": [float(M[0][2]), float(M[1][2])]}


def measure_points(board_L: np.ndarray, board_mask: np.ndarray, art_rect_L: np.ndarray, rows: int, cols: int,
				   cells, *, search_cell: float = SEARCH_CELL, pad_cell: float = PAD_CELL, std_min: float = STD_MIN,
				   cover_min: float = COVER_MIN) -> list:
	"""Shift of every cell between the board raster and the rectified art (same size, both span the grid).

	Returns one dict per cell of ``cells`` with enough piece/texture: ``{cell, ncc, at_edge,
	shift_cells: (dx, dy)}`` where the board content of the cell sits at ``cell + shift`` in
	the rectified art.
	"""
	H, W = art_rect_L.shape
	cw, ch = W / float(cols), H / float(rows)
	Sx, Sy = int(np.ceil(search_cell * cw)), int(np.ceil(search_cell * ch))
	px, py = int(round(pad_cell * cw)), int(round(pad_cell * ch))
	pad = max(Sx, Sy) + max(px, py) + 2
	artp = cv2.copyMakeBorder(art_rect_L.astype(np.float32), pad, pad, pad, pad, cv2.BORDER_REPLICATE)
	out = []
	for (l, c) in cells:
		# the cell grown by pad_cell (neighbours placed); the bare cell if the rim is not piece
		for g in ((px, py), (0, 0)):
			x0, y0 = int(round((c - 1) * cw)) - g[0], int(round((l - 1) * ch)) - g[1]
			x1, y1 = int(round(c * cw)) + g[0], int(round(l * ch)) + g[1]
			x0c, y0c, x1c, y1c = max(x0, 0), max(y0, 0), min(x1, W), min(y1, H)
			m = board_mask[y0c:y1c, x0c:x1c]
			if m.size and m.mean() >= cover_min:
				break
		if m.size == 0 or m.mean() < cover_min:
			continue
		tpl = board_L[y0c:y1c, x0c:x1c].astype(np.float32)
		vals = tpl[m]
		if vals.std() < std_min:
			continue
		win = artp[y0c - Sy + pad:y1c + Sy + pad, x0c - Sx + pad:x1c + Sx + pad]
		Z = _masked_zncc(win, tpl, m)
		iy, ix = np.unravel_index(int(np.argmax(Z)), Z.shape)
		edge = ix in (0, Z.shape[1] - 1) or iy in (0, Z.shape[0] - 1)
		fx = _parabola(Z[iy, ix - 1], Z[iy, ix], Z[iy, ix + 1]) if 0 < ix < Z.shape[1] - 1 else 0.0
		fy = _parabola(Z[iy - 1, ix], Z[iy, ix], Z[iy + 1, ix]) if 0 < iy < Z.shape[0] - 1 else 0.0
		out.append({"cell": (int(l), int(c)), "ncc": float(Z[iy, ix]), "at_edge": bool(edge),
					"shift_cells": ((ix + fx - Sx) / cw, (iy + fy - Sy) / ch)})
	return out


def register_art(board_rgb: np.ndarray, board_mask: np.ndarray, art_rgb: np.ndarray, rows: int, cols: int, cell_mm,
				 M0, cells=None, *, upsample: int = UPSAMPLE, ncc_min: float = NCC_MIN, passes: int = 3,
				 progress=None) -> dict:
	"""Fit the affine board mm -> art px from a board render and the art file (pure).

	``board_rgb`` (RGB uint8) and ``board_mask`` (bool, True = piece) are any raster that spans
	exactly ``rows x cols`` cells; ``art_rgb`` is the art file; ``M0`` the prior model (bbox);
	``cells`` the cells to try (default: every cell). Pass 1 searches +/- ``SEARCH_CELL`` around
	``M0``, later passes +/- ``SEARCH_FINE_CELL`` around the current fit. Returns ``{matrix,
	matrix_prior, n_points, n_tried, points: [{cell, P_mm, Q_px, ncc, inlier, res_before,
	res_after}], residual_cells: {before, after} (median / p95 / mean on the inliers),
	decomposition}`` or ``{'error'}``.
	"""
	cell_mm = (float(cell_mm[0]), float(cell_mm[1]))
	M0 = np.asarray(M0, np.float64)
	if cells is None:
		cells = [(l, c) for l in range(1, rows + 1) for c in range(1, cols + 1)]
	W0, H0 = rectified_size(M0, rows, cols, cell_mm)
	W, H = W0 * upsample, H0 * upsample
	interp = cv2.INTER_AREA if board_rgb.shape[1] > W else cv2.INTER_LINEAR
	bL = _lstar(cv2.resize(board_rgb, (W, H), interpolation=interp))
	bm = cv2.resize(board_mask.astype(np.float32), (W, H), interpolation=cv2.INTER_AREA) > 0.99
	M = M0.copy()
	pts, fit = [], None
	for k in range(passes):
		art_L = _lstar(rectify_art(art_rgb, M, rows, cols, cell_mm, (W, H)))
		meas = measure_points(bL, bm, art_L, rows, cols, cells, search_cell=SEARCH_CELL if k == 0 else SEARCH_FINE_CELL)
		pts = []
		for q in meas:
			if q["ncc"] < ncc_min or q["at_edge"]:
				continue
			l, c = q["cell"]
			P = np.array([(c - 0.5) * cell_mm[0], (l - 0.5) * cell_mm[1]])
			Pm = P + np.array([q["shift_cells"][0] * cell_mm[0], q["shift_cells"][1] * cell_mm[1]])
			pts.append({"cell": [l, c], "P_mm": P, "Q_px": M[:, :2] @ Pm + M[:, 2], "ncc": q["ncc"]})
		if len(pts) < 6:
			return {"error": f"só {len(pts)} pontos com NCC >= {ncc_min} (passo {k + 1})", "n_tried": len(meas)}
		P = np.array([p["P_mm"] for p in pts])
		Q = np.array([p["Q_px"] for p in pts])
		w = np.array([p["ncc"] for p in pts])
		fit = fit_affine(P, Q, w, cell_mm, M0=None)
		Mn = fit["matrix"]
		# change of the model over the grid corners (cells)
		corners = np.array([[0, 0], [cols * cell_mm[0], 0], [0, rows * cell_mm[1]], [cols * cell_mm[0], rows * cell_mm[1]]])
		dc = residual_cells(Mn, corners, corners @ M[:, :2].T + M[:, 2], cell_mm).max()
		if progress:
			progress(f"  passo {k + 1}: {len(pts)}/{len(meas)} pontos, mudança nos cantos {dc:.3f} célula")
		M = Mn
		if dc < 0.01 and k > 0:
			break
	P = np.array([p["P_mm"] for p in pts])
	Q = np.array([p["Q_px"] for p in pts])
	rb = residual_cells(M0, P, Q, cell_mm)
	ra = residual_cells(M, P, Q, cell_mm)
	inl = ra <= INLIER_CELL
	for p, b, a, i in zip(pts, rb, ra, inl):
		p.update(P_mm=[float(v) for v in p["P_mm"]], Q_px=[float(v) for v in p["Q_px"]], res_before=float(b),
				 res_after=float(a), inlier=bool(i))

	def st(r):
		return {"median": float(np.median(r)), "p95": float(np.percentile(r, 95)), "mean": float(np.mean(r))} if len(r) else None

	return {"matrix": M, "matrix_prior": M0, "n_points": int(inl.sum()), "n_measured": len(pts), "n_tried": len(meas),
			"points": pts, "residual_cells": {"before": st(rb[inl]), "after": st(ra[inl]),
											  "before_all": st(rb), "after_all": st(ra)},
			"decomposition": decompose(M), "decomposition_prior": decompose(M0)}


def art_coverage(art_rgb: np.ndarray, M, rows: int, cols: int, cell_mm, content_bbox=None) -> dict:
	"""Which cells the art file reaches under ``M``: ``{rows_with_art: [first, last], cols_with_art: [first,
	last], cells_without_art: n}`` (a cell has art if >= ``locate.MIN_CELL_ART`` of its px are inside)."""
	from src.locate import MIN_CELL_ART
	_, valid = rectify_art(art_rgb, M, rows, cols, cell_mm, content_bbox=content_bbox, return_valid=True)
	H, W = valid.shape
	frac = cv2.resize(valid.astype(np.float32), (cols, rows), interpolation=cv2.INTER_AREA)
	has = frac >= MIN_CELL_ART
	r = np.flatnonzero(has.any(1)) + 1
	c = np.flatnonzero(has.any(0)) + 1
	return {"rows_with_art": [int(r[0]), int(r[-1])] if len(r) else None,
			"cols_with_art": [int(c[0]), int(c[-1])] if len(c) else None,
			"cells_without_art": int((~has).sum())}


# ---------------------------------------------------------------- I/O
def render_board(project, px_per_cell: float = 50.0, progress=print):
	"""Placed pieces only (corner registration, no image), as ``(rgb, mask, cells)``; nothing is written.

	``rgb``/``mask`` span the whole grid (uniform px/mm, ``px_per_cell`` px per cell width);
	``mask`` = piece pixels (rendered over a magenta sentinel).
	"""
	from src import render
	t0 = time.time()
	pl = {}
	for pid in render.placed_ids(project):
		r = render.register_piece(project, pid, art=None, image=False)
		if "error" not in r:
			pl[pid] = r
	if progress:
		progress(f"  registo por cantos: {len(pl)} peças ({time.time() - t0:.0f} s)")
	bgr = render.compose_board(project, px_per_cell, layers=("pieces",), placements=pl, base_bgr=(255, 0, 255))
	d = np.abs(bgr.astype(np.int16) - np.array([255, 0, 255], np.int16)).sum(-1)
	mask = d > 60
	cells = sorted({tuple(project.piece(pid).celula) for pid in pl})
	if progress:
		progress(f"  render {bgr.shape[1]}x{bgr.shape[0]} ({time.time() - t0:.0f} s)")
	return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), mask, cells


def _fmt_matrix(M) -> list:
	return [[round(float(v), 6) for v in row] for row in np.asarray(M)]


def write_registration(puzzle_path: str, reg: dict) -> None:
	"""Write ``art.registration`` into ``puzzle.json`` keeping the file's compact layout (only the ``art`` line changes)."""
	with open(puzzle_path, encoding="utf-8") as f:
		txt = f.read()
	d = json.loads(txt)
	art = dict(d["art"])
	art["registration"] = reg
	head = json.dumps({k: v for k, v in art.items() if k != "registration"}, ensure_ascii=False)[:-1]
	line = (f'  "art": {head},\n    "registration": '
			+ json.dumps(reg, ensure_ascii=False) + "},\n")
	new, n = re.subn(r'^  "art": .*?(?=^  "calibration")', lambda _m: line, txt, count=1, flags=re.M | re.S)
	if n != 1:
		raise ValueError("puzzle.json: linha 'art' não encontrada")
	json.loads(new)    # still valid JSON
	with open(puzzle_path, "w", encoding="utf-8", newline="\n") as f:
		f.write(new)


def run(project, *, write: bool = True, report_dir=None, ppc: float = 50.0, progress=print) -> dict:
	"""Register the art of ``project`` against its placed pieces; write ``art.registration`` to its
	``puzzle.json`` (and reload ``project.profile``) when ``write`` and the residual is not worse.

	The prior is always the ``bbox`` (never a previous registration, so the fit does not depend on
	its own past output). Returns the :func:`register_art` dict plus ``written`` (bool) and
	``registration`` (what was / would be written), or ``{'error'}``.
	"""
	from src.profile import PuzzleProfile
	prof = project.profile
	art = prof.art or {}
	if not art.get("file"):
		return {"error": "perfil sem arte"}
	repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
	im = cv2.imdecode(np.fromfile(os.path.join(repo, art["file"]), np.uint8), cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
	if im is None:
		return {"error": f"não consigo ler {art['file']}"}
	art_rgb = cv2.cvtColor(im, cv2.COLOR_BGR2RGB)
	prior = dict(art)
	prior.pop("registration", None)
	M0 = PuzzleProfile.from_dict({**prof.to_dict(), "art": prior}).art_matrix()
	cell_mm = (float(prof.cell_mm["w"]), float(prof.cell_mm["h"]))
	board, mask, cells = render_board(project, ppc, progress=progress)
	res = register_art(board, mask, art_rgb, prof.rows, prof.cols, cell_mm, M0, cells, progress=progress)
	if "error" in res:
		return res
	rc = res["residual_cells"]
	if progress:
		progress(f"pontos: {res['n_points']} inliers / {res['n_measured']} medidos / {res['n_tried']} células tentadas")
		progress(f"resíduo (células, inliers): antes mediana {rc['before']['median']:.3f} p95 {rc['before']['p95']:.3f}; "
				 f"depois mediana {rc['after']['median']:.3f} p95 {rc['after']['p95']:.3f}")
		progress(f"decomposição: {json.dumps(res['decomposition'])}")
	if report_dir:
		os.makedirs(report_dir, exist_ok=True)
		with open(os.path.join(report_dir, "artreg.json"), "w", encoding="utf-8") as f:
			json.dump(res, f, ensure_ascii=False, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
	cov = art_coverage(art_rgb, res["matrix"], prof.rows, prof.cols, cell_mm, art.get("bbox"))
	res["coverage"] = cov
	if progress and cov["cells_without_art"]:
		progress(f"sem arte no ficheiro: {cov['cells_without_art']} células; filas com arte {cov['rows_with_art']}, "
				 f"colunas com arte {cov['cols_with_art']}")
	reg = {"matrix": _fmt_matrix(res["matrix"]), "units": "board_mm->art_px", "n_points": res["n_points"],
		   "content_bbox": [int(v) for v in art["bbox"]] if art.get("bbox") is not None else None,
		   "rows_with_art": cov["rows_with_art"], "cols_with_art": cov["cols_with_art"],
		   "residual_cells": {"before": {k: round(rc["before"][k], 4) for k in ("median", "p95")},
							  "after": {k: round(rc["after"][k], 4) for k in ("median", "p95")}},
		   "date": time.strftime("%Y-%m-%d")}
	res["registration"] = reg
	res["written"] = False
	worse = rc["after"]["median"] > rc["before"]["median"] or rc["after"]["p95"] > rc["before"]["p95"]
	if worse:
		if progress:
			progress("artreg: [F] resíduo depois pior do que antes; puzzle.json não escrito")
		return res
	if write:
		fp = project.p("puzzle.json")
		write_registration(fp, reg)
		project.profile = PuzzleProfile.load(fp)
		res["written"] = True
		if progress:
			progress(f"artreg: registo escrito em {fp}")
	return res


def main(argv=None) -> int:
	from src.state import Project
	ap = argparse.ArgumentParser(description="Registo da arte contra as peças colocadas (afim mm do tabuleiro -> px da arte)")
	ap.add_argument("--project", default=os.path.join("projects", "alpes"))
	ap.add_argument("--dry-run", action="store_true", help="não escreve puzzle.json")
	ap.add_argument("--report", default=None, help="pasta para artreg.json (omissão: $PPF_SCRATCH/artreg)")
	ap.add_argument("--ppc", type=float, default=50.0, help="px por célula do render do tabuleiro")
	args = ap.parse_args(argv)
	repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
	out_dir = args.report or os.path.join(os.environ.get("PPF_SCRATCH") or os.path.join(repo, "scratch"), "artreg")
	print(f"artreg: {args.project}")
	res = run(Project.open(args.project), write=not args.dry_run, report_dir=out_dir, ppc=args.ppc)
	if "error" in res:
		print(f"artreg: {res['error']}")
		return 1
	return 0 if (res["written"] or args.dry_run) else 2


if __name__ == "__main__":
	sys.exit(main())
