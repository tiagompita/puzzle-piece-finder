"""Board render that looks like the physical puzzle: fine registration, fringe cleaning, composition.

``python -m src.render --project projects/alpes [--rebuild] [--register] [--clean]
[--board out.jpg --ppc 60] [--zone L0 C0 L1 C1 --dpi 300 --out zone.jpg]``

Three steps, each usable on its own:

1. **Registration** (:func:`register_piece`, :func:`register_all`): the pose of a placed piece
   in its cell. Primary = geometry: the 4 detected corners (scan mm) are matched to the 4
   corners of the cell grown by the silhouette offset (``calibration.celula_silhueta.offset_mm``,
   the silhouette sits that far outside the cut line) with a 2D rigid Kabsch fit (no scale).
   The cyclic corner assignment must put the F sides on the border directions of the cell
   (:meth:`src.profile.PuzzleProfile.flat_directions`) and is the one closest to the initial
   pose (log ``theta_deg``, or the section rotation + the body angle for legacy sections).
   Kabsch aligns the corner centroids, so the corner solution always puts the body centre on
   the cell centre (``dx = dy = 0``); its value is the rotation and the right pivot (the mean of
   the 4 corners, not the contour mean, which the tabs pull around). Border pieces
   (``F_ROTATION``): the rotation comes instead from the line fitted to the F side(s), laid on
   the border line (:func:`f_rotation`; only F sides whose contour is straight, line RMS <=
   ``F_LINE_RMS_MAX``), so a non-rectangular cell no longer tilts the piece (RENDER.md §8); the
   translation stays the corner centroid on the cell centre unless ``F_TRANSLATION`` is on, which
   moves the piece along the border normal(s) so that the same F line(s) lie on the border line +
   the silhouette offset (:func:`f_translation`; the tangential component stays the corner one;
   RENDER.md §9). Secondary = image: the
   crop rendered at the art scale is searched over +/- ``IMG_SEARCH_CELL`` cell and
   +/- ``IMG_ROT_DEG`` deg (RMS dE in Lab + ``GRAD_W`` x (1 - gradient-magnitude NCC), parabola
   refinement); it refines the corner pose only when it lowers the score and stays within
   ``IMG_ACCEPT_MM`` / ``IMG_ACCEPT_DEG``, and it is the only method when the shape has no 4
   corners or the corner gate fails. With corners the image refines the translation only (a
   1 deg turn moves the body edge by ~0.2 art px: the rotation is not observable at 0.75 mm/px). Seam metric between
   neighbours: :func:`seam_gaps`. Results are cached in ``projects/<id>/render/placements.json``
   (derived; never written to the log).
2. **Fringe cleaning** (:func:`clean_crop`): green background blended into the outermost
   pixels of the silhouette is removed, only inside a band of ``band_mm`` (<= 0.7 mm) from the
   alpha boundary and only as connected components that touch the boundary; pixels deeper
   than the band are never touched. Cleaned crops go to ``render/clean/P####.png``;
   ``crops/`` is never modified.
3. **Composition** (:func:`compose_board`, :func:`compose_zone_vs_art`): art underlay, the
   cleaned crops warped with their registration (drawn in row order), hatched
   ``ocupada_legado`` cells, red outline on empty border cells, optional grid.

:func:`rebuild_assets` regenerates ``pieces/*.npz`` and ``crops/`` from the scans listed in the
log (the other PC only has the JSON and the log), matching every piece by index and bbox IoU;
``force_scans`` re-segments sheets whose assets exist, and a piece whose silhouette changed gets
a ``piece_resegmented`` event (its new static fields) in the log.

Frames: scan mm = contour px index x ``mm_per_px`` (the frame of :class:`src.shape.Shape`);
board mm = continuous frame where cell ``(l, c)`` spans ``[(c-1) w, c w] x [(l-1) h, l h]``
(``w, h`` = ``profile.cell_mm``); a pose maps ``x_board = R(theta) (x_scan - pivot) + centre(l, c)
+ (dx, dy)`` with ``pivot`` = body centre (:func:`src.locate.body_center_mm`) and ``R`` in the
complex convention of :mod:`src.shape` (positive = clockwise on screen). Image pixel ``i``
covers ``[i, i+1)`` in continuous coordinates.

Pure helpers are separate from the I/O wrappers (``register_all``, ``clean_all``,
``load_placements``/``save_placements``, ``rebuild_assets``, the CLI).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Optional

import cv2
import numpy as np

from src import overrides as OV
from src.locate import CellArt, body_beta_deg, body_center_mm, wrap_deg

__all__ = [
	"CORNER_RESIDUAL_MAX_MM", "F_ROTATION", "F_SPAN", "F_MAX_DEG", "F_LINE_RMS_MAX", "F_TRANSLATION", "F_TARGET_GROW", "f_side_line", "f_side_fit", "f_rotation", "f_translation", "IMG_SEARCH_CELL", "IMG_ROT_DEG", "IMG_ACCEPT_MM", "IMG_ACCEPT_DEG", "GRAD_W", "IMG_NCC_MIN",
	"BAND_MM", "LIGHT_BAND_MAX_MM", "BG_DIST_MAX", "PIECE_P5_FRAC", "LIGHT_BAND_MM", "LIGHT_PIECE_P5_MIN", "is_light", "BG_LUMA_WEIGHT", "SHADOW_L_DELTA", "SHADOW_CHROMA_MAX", "SHADOW_DEFAULT",
	"INTERIOR_MM", "SEAM_TRIM", "BLEED_MM", "RELAX_GAP_MM", "RELAX_MAX_MM", "DIRS",
	"cell_corners_mm", "cell_centre_mm", "kabsch_2d", "corner_register", "pose_matrix", "board_contour",
	"initial_theta", "baseline_placement", "image_refine", "register_piece", "register_all", "registered_theta",
	"manual_pose", "manual_pose_note", "effective_pose", "pose_brief", "candidate_entry",
	"seam_gaps", "relax", "bg_distance", "fringe_masks", "decontaminate", "clean_crop", "clean_all", "compose_board",
	"compose_zone_vs_art", "rebuild_assets", "rebuild_piece", "load_placements", "save_placements", "main",
	"stale_assets", "rebuild_stale", "STALE_AREA_FRAC", "STALE_CHORD_MM",
	"warp_rgba", "resize_rgba", "piece_rgba_for_display", "aresta_rgba", "has_aresta", "shadow_paper_mask", "DISPLAY_SHADOW", "BOARD_SHADOW",
	"paper_pocket_mask", "PAPER_POCKETS", "PAPER_POCKET_DIST_MAX",
	"DISPLAY_SHADOW_BAND_MM", "DISPLAY_SHADOW_A_MAX", "DISPLAY_SHADOW_DIST_MAX", "DISPLAY_SHADOW_L_MAX",
]

# ---------------------------------------------------------------- constants
CORNER_RESIDUAL_MAX_MM = 1.0   # RMS corner residual (mm) above which the corner solution is not trusted
F_ROTATION = True              # border pieces: rotation from the line fitted to the F side(s), not from the corners (RENDER.md §8)
F_SPAN = (0.08, 0.92)          # ... line fitted on this share of the F side's chord (corner rounding left out)
F_MAX_DEG = 10.0               # ... used only within this of the corner rotation (else the corner rotation is kept)
F_LINE_RMS_MAX = 0.15          # ... and only from an F side whose contour is straight: line RMS (mm) at most this
F_TRANSLATION = False          # border pieces: the same F line(s) also fix the translation normal to the border; OFF: gate failed (RENDER.md §9)
F_TARGET_GROW = True           # ... target line = border + silhouette offset (grow) outside, as the Kabsch targets; False = the border itself
IMG_SEARCH_CELL = 0.5          # image search: translation range (+/- fraction of a cell)
IMG_ROT_DEG = 5                # image search: rotation range (+/- deg, 1 deg steps); only without corners:
                               # a 1 deg turn moves the body edge ~0.16 mm = 0.2 art px, not observable (RENDER.md §1)
IMG_ACCEPT_MM = 0.5            # image refinement accepted only within this of the corner solution ...
IMG_ACCEPT_DEG = 2.0           # ... and this rotation
GRAD_W = 5.0                   # score = RMS dE + GRAD_W * (1 - gradient-magnitude NCC); dE units
IMG_NCC_MIN = 0.5              # image-only registration kept only with gradient NCC >= this (else method 'none')
IMG_ERODE_PX = 1               # template mask eroded by this many art px (rim/shadow out of the score)
LIGHT_BAND_MM = 1.2            # default band of LIGHT pieces only (decision 2026-11-01, RENDER.md §2.5); others keep BAND_MM
LIGHT_BAND_MAX_MM = 1.2        # upper clamp of any band
LIGHT_PIECE_P5_MIN = 44.25     # light piece: p5 of its interior bg distance > this (= 1.5 x BG_DIST_MAX; the darkest-grass
                               # calibration p5 is 29.5, so >= 95 % of a light piece is far from the paper green)
BAND_MM = 0.7                  # fringe band: alpha pixels within this distance of the alpha boundary
BG_DIST_MAX = 29.5             # "green": sqrt(0.5 dL^2 + da^2 + db^2) (CIE Lab) to background_lab below this
DECONT_T_MIN = 0.05            # band pixels with a paper share above this, connected to the outside, are unmixed
PIECE_P5_FRAC = 0.8            # per-piece threshold: max(BG_DIST_MAX, this x p5 of the piece's interior distance)
BG_LUMA_WEIGHT = 0.5           # weight of dL^2 in the background distance (as segment_scan)
SHADOW_L_DELTA = 12.0          # shadow pass: band pixel with L* < interior median - this ...
SHADOW_CHROMA_MAX = 12.0       # ... and chroma below this, connected to the outside
SHADOW_DEFAULT = False         # shadow pass off by default (RENDER.md §2: it eats dark grass)
# display only (thumbnails: cards, fetch sheets, Mesa; and, since 2026-11-06, the board drawing; never the index
# nor render/clean/): paper darkened by the cast shadow, left by the cleaning because it is just above
# BG_DIST_MAX (RENDER.md §6.1, §7)
DISPLAY_SHADOW = True          # on (decision 2026-11-01, RENDER.md §6.1)
BOARD_SHADOW = True            # the same rule in compose_board (RENDER.md §7: frontier rims showed it); False = as before
PAPER_POCKETS = True           # display: also drop paper-coloured components touching the boundary at any depth (RENDER.md §7)
PAPER_POCKET_DIST_MAX = 15.0   # ... "paper colour" = bg_distance below this (grass interior p1 24.3, RENDER.md §2.1)
PAPER_POCKET_MAX_FRAC = 0.10   # ... and each component at most this share of the piece (P0778's pocket: ~3 %)
DISPLAY_SHADOW_BAND_MM = 0.4   # only within this distance of the alpha boundary
DISPLAY_SHADOW_A_MAX = -30.0   # a* below this (paper-like green; grass interior median a* ~ -6 .. -18)
DISPLAY_SHADOW_DIST_MAX = 40.0 # bg_distance to background_lab below this
DISPLAY_SHADOW_L_MAX = 62.0    # L* below this (darkened; the paper is L* ~ 79)
INTERIOR_MM = 1.5              # pixels deeper than this are the piece interior (reference statistics)
SEAM_TRIM = 0.15               # fraction of a side ignored at each end in the seam metric (corners)
SEAM_BAND_MM = 5.0             # fallback (no corners): contour points within this of the shared edge
BLEED_MM = 0.3                 # composition: each piece's edge colour extended this far, drawn under all pieces (fills hairline gaps)
RELAX_GAP_MM = 0.8             # relaxation pass considered when |gap| > this for a notable share
RELAX_SHARE = 0.10             # ... of the seams
RELAX_MAX_MM = 0.5             # max translation of the relaxation pass
DIRS = ("N", "E", "S", "W")    # cell sides; target corner order TL, TR, BR, BL -> side j = DIRS[j]
_STEP = {"E": (0, 1), "S": (1, 0)}
PLACEMENTS_VERSION = 1
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------- geometry (pure)
def _R(theta_deg: float) -> np.ndarray:
	t = np.radians(theta_deg)
	return np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])


def cell_centre_mm(profile, l: int, c: int) -> np.ndarray:
	"""Centre of cell ``(l, c)`` in board mm."""
	w, h = float(profile.cell_mm["w"]), float(profile.cell_mm["h"])
	return np.array([(c - 0.5) * w, (l - 0.5) * h])


def cell_corners_mm(profile, l: int, c: int, grow: float = 0.0) -> np.ndarray:
	"""Corners TL, TR, BR, BL of cell ``(l, c)`` in board mm, grown by ``grow`` mm on every side.

	This order has a positive shoelace area in image coordinates, like the corners of
	:class:`src.shape.Shape`, so corner ``i`` -> target ``(i + k) % 4`` maps side ``i`` to
	``DIRS[(i + k) % 4]``.
	"""
	w, h = float(profile.cell_mm["w"]), float(profile.cell_mm["h"])
	x0, y0, x1, y1 = (c - 1) * w - grow, (l - 1) * h - grow, c * w + grow, l * h + grow
	return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], float)


def kabsch_2d(src: np.ndarray, dst: np.ndarray):
	"""Rigid fit ``dst ~ R(theta) src + t`` (no scale): ``(theta_deg, t, rms)``; complex convention."""
	S, T = np.asarray(src, float), np.asarray(dst, float)
	ms, mt = S.mean(0), T.mean(0)
	a, b = S - ms, T - mt
	dot = float(np.sum(a * b))
	cross = float(np.sum(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]))
	th = float(np.degrees(np.arctan2(cross, dot)))
	R = _R(th)
	t = mt - R @ ms
	rms = float(np.sqrt(np.mean(np.sum((S @ R.T + t - T) ** 2, 1))))
	return th, t, rms


def _grow(profile) -> float:
	"""Silhouette offset outside the cut line (``calibration.celula_silhueta.offset_mm``, mm)."""
	return float(((profile.calibration or {}).get("celula_silhueta") or {}).get("offset_mm") or 0.0)


def _f_ok(shape, k: int, flat: set) -> bool:
	"""F sides on exactly the border directions of the cell under the cyclic assignment ``k``."""
	fd = {DIRS[(i + k) % 4] for i, s in enumerate(shape.sides) if s.kind == "F"}
	return fd == set(flat)


def _rect_residual(P: np.ndarray, theta_deg: float, k: int) -> float:
	"""RMS of the 4 corners against their best-fit rectangle (free width / height, rigid pose)."""
	Q = np.zeros((4, 2))
	Q[(np.arange(4) + k) % 4] = np.asarray(P, float) @ _R(theta_deg).T
	Q -= Q.mean(0)
	w = 0.5 * ((Q[1, 0] - Q[0, 0]) + (Q[2, 0] - Q[3, 0]))
	h = 0.5 * ((Q[3, 1] - Q[0, 1]) + (Q[2, 1] - Q[1, 1]))
	T = np.array([[-w, -h], [w, -h], [w, h], [-w, h]]) / 2.0
	return kabsch_2d(Q, T)[2]


def corner_register(shape, profile, cell, theta0: Optional[float] = None, grow: Optional[float] = None) -> dict:
	"""Corner solution of ``shape`` in ``cell``: ``{ok, theta_deg, residual_mm, k, f_ok, dtheta0_deg, cands}``.

	``shape_residual_mm`` = RMS of the corners against their own best-fit rectangle (corner
	consistency, independent of the cell size). ``cands`` = the 4 cyclic assignments ``[(k, theta, rms, f_ok)]``. Choice: among the
	assignments with the F sides on the cell's border directions (all of them if none is),
	the one whose rotation is closest to ``theta0``; with ``theta0`` None and several valid,
	the lowest residual (``ambiguous`` True: the caller should decide by image).
	"""
	if shape is None or not shape.ok or len(shape.corners) != 4:
		return {"ok": False, "reason": "sem 4 cantos"}
	if grow is None:
		grow = _grow(profile)
	P = shape.c[shape.corners]
	T = cell_corners_mm(profile, cell[0], cell[1], grow)
	flat = profile.flat_directions(*cell)
	cands = []
	for k in range(4):
		th, _, rms = kabsch_2d(P, np.roll(T, -k, axis=0))
		cands.append((k, th, rms, _f_ok(shape, k, flat)))
	pool = [cd for cd in cands if cd[3]] or cands
	amb = False
	if theta0 is not None:
		best = min(pool, key=lambda cd: abs(float(wrap_deg(cd[1] - theta0))))
	else:
		best = min(pool, key=lambda cd: cd[2])
		amb = len(pool) > 1
	k, th, rms, fok = best
	return {"ok": True, "theta_deg": float(th), "residual_mm": float(rms), "k": int(k), "f_ok": bool(fok),
			"shape_residual_mm": _rect_residual(P, th, k),
			"dtheta0_deg": None if theta0 is None else float(wrap_deg(th - theta0)), "ambiguous": amb,
			"cands": [(int(a), float(b), float(c), bool(d)) for a, b, c, d in cands]}


def f_side_fit(shape, i: int) -> Optional[dict]:
	"""Least-squares line through side ``i`` within ``F_SPAN`` of its chord, in scan mm:
	``{angle_deg, rms_mm, mid_mm, dir}`` (``angle_deg`` = direction in the image frame, ``atan2(dy, dx)``
	from corner ``i`` to corner ``i + 1``; ``rms_mm`` = RMS of the points about the line; ``mid_mm`` =
	the point of the line at the middle of the chord; ``dir`` = unit direction), None with fewer than
	6 points. :func:`f_side_line` is its ``(angle_deg, rms_mm)``.
	"""
	a, b = int(shape.corners[i]), int(shape.corners[(i + 1) % 4])
	seg = shape.c[a:b + 1] if b > a else np.vstack([shape.c[a:], shape.c[:b + 1]])
	p0, p1 = seg[0], seg[-1]
	L = float(np.linalg.norm(p1 - p0))
	if L < 1e-6:
		return None
	u = (p1 - p0) / L
	v = np.array([-u[1], u[0]])
	x, y = (seg - p0) @ u / L, (seg - p0) @ v / L
	sel = (x > F_SPAN[0]) & (x < F_SPAN[1])
	if sel.sum() < 6:
		return None
	coef = np.polyfit(x[sel], y[sel], 1)
	rms = float(np.sqrt(np.mean((y[sel] - np.polyval(coef, x[sel])) ** 2)) * L)
	d = u + float(coef[0]) * v
	return {"angle_deg": float(np.degrees(np.arctan2(u[1], u[0])) + np.degrees(np.arctan(float(coef[0])))), "rms_mm": rms,
			"mid_mm": p0 + 0.5 * L * u + float(np.polyval(coef, 0.5)) * L * v, "dir": d / np.linalg.norm(d)}


def f_side_line(shape, i: int) -> Optional[tuple]:
	"""Line through side ``i`` within ``F_SPAN`` of its chord (:func:`f_side_fit`): ``(angle_deg, rms_mm)``,
	None with fewer than 6 points.

	Meant for F sides: unlike the chord it does not depend on where exactly the two corners were
	detected; the RMS says whether the contour there is a straight edge at all (a green / shadow
	fringe inside the silhouette makes it bulge, RENDER.md §8).
	"""
	f = f_side_fit(shape, i)
	return None if f is None else (f["angle_deg"], f["rms_mm"])


def f_rotation(shape, k: int, theta_ref: float, rms_max: Optional[float] = None) -> Optional[dict]:
	"""Board rotation that lays the F side(s) of ``shape`` on the border line(s) of the cell.

	Side ``i`` faces ``DIRS[(i + k) % 4]`` (the cyclic corner assignment of :func:`corner_register`);
	on the board its direction must be ``90 * ((i + k) % 4)`` deg, so each F side gives
	``theta = 90 j - angle_i`` (taken nearest ``theta_ref``). Only F sides whose contour is straight
	(line RMS <= ``rms_max``, default ``F_LINE_RMS_MAX``) count. Two F sides (puzzle corners): the
	mean weighted by chord length. Returns ``{theta_deg, dtheta_deg, n_f, per_side: [(i, dir, theta,
	rms_mm, used)], spread_deg}`` or None (no usable F side).
	"""
	if shape is None or not shape.ok or len(shape.corners) != 4:
		return None
	rms_max = F_LINE_RMS_MAX if rms_max is None else float(rms_max)
	est, wts, per = [], [], []
	for i, s in enumerate(shape.sides):
		if s.kind != "F":
			continue
		fl = f_side_line(shape, i)
		if fl is None:
			continue
		j = (i + int(k)) % 4
		th = float(theta_ref + wrap_deg(90.0 * j - fl[0] - theta_ref))
		use = fl[1] <= rms_max
		per.append((i, DIRS[j], th, fl[1], bool(use)))
		if use:
			est.append(th)
			wts.append(float(s.chord_mm))
	if not est:
		return None
	th = float(np.average(est, weights=wts))
	return {"theta_deg": th, "dtheta_deg": float(th - theta_ref), "n_f": len(est), "per_side": per,
			"spread_deg": float(np.ptp(est)) if len(est) > 1 else 0.0}


_OUT = {"N": (0.0, -1.0), "E": (1.0, 0.0), "S": (0.0, 1.0), "W": (-1.0, 0.0)}   # outward normal of a cell side (board mm)


def f_translation(shape, fr: dict, theta_deg: float, pivot_mm, profile, cell, target_mm: float) -> Optional[dict]:
	"""Translation normal to the border that puts the F line(s) of ``shape`` on the target line(s).

	``fr`` = the :func:`f_rotation` result (its ``per_side`` says which F sides were used and the cell
	direction each one faces). With the pose ``R(theta) (x - pivot) + centre(cell)`` (no ``d``), the
	midpoint of each used F line (:func:`f_side_fit`) lands at signed distance ``e`` (mm, positive =
	outside the board) from the target: the border line of the cell side moved ``target_mm`` outwards
	(the silhouette offset: the scan silhouette sits that far outside the cut, as the grown Kabsch
	targets). The translation is ``d = -sum(e_i n_i)`` (``n_i`` outward unit normal; puzzle corners: 2
	orthogonal normals, so both F lines land on their targets; the tangential component stays the
	corner one, i.e. 0). Only sides whose direction is a border direction of the cell count. Returns
	``{per_side: [(i, dir, e_mm)], dx_mm, dy_mm}`` or None (no usable F side).
	"""
	if fr is None or shape is None:
		return None
	flat = profile.flat_directions(*cell)
	w, h = float(profile.cell_mm["w"]), float(profile.cell_mm["h"])
	l, c = int(cell[0]), int(cell[1])
	edge = {"N": (l - 1) * h, "S": l * h, "W": (c - 1) * w, "E": c * w}     # border line position along its axis
	A = pose_matrix(theta_deg, pivot_mm, cell_centre_mm(profile, l, c))
	per, d = [], np.zeros(2)
	seen = set()
	for i, dr, _th, _rms, used in fr.get("per_side") or []:
		if not used or dr not in flat or dr in seen:
			continue
		f = f_side_fit(shape, int(i))
		if f is None:
			continue
		n = np.array(_OUT[dr])
		q = _apply(A, f["mid_mm"])[0]
		pos = edge[dr] * (1.0 if dr in ("S", "E") else -1.0)            # = (point on the border line) . n
		e = float(q @ n - pos - float(target_mm))
		per.append((int(i), dr, e))
		d -= e * n
		seen.add(dr)
	if not per:
		return None
	return {"per_side": per, "dx_mm": float(d[0]), "dy_mm": float(d[1])}


def _drop_f_normal(v, f_offset: Optional[dict]) -> np.ndarray:
	"""``v`` (board mm) without its components along the outward normals of the F sides in ``f_offset``
	(the :func:`f_translation` result; None = ``v`` unchanged). Used so that a later translation (image
	refinement, :func:`relax`) keeps the F line(s) on their target."""
	v = np.asarray(v, float).copy()
	for _i, dr, _e in (f_offset or {}).get("per_side") or []:
		n = np.array(_OUT[dr])
		v -= float(v @ n) * n
	return v


def pose_matrix(theta_deg: float, pivot_mm, centre_mm, d_mm=(0.0, 0.0)) -> np.ndarray:
	"""2x3 affine scan mm -> board mm: ``R(theta) (x - pivot) + centre + d``."""
	R = _R(theta_deg)
	off = np.asarray(centre_mm, float) + np.asarray(d_mm, float) - R @ np.asarray(pivot_mm, float)
	return np.c_[R, off]


def _apply(A: np.ndarray, pts) -> np.ndarray:
	p = np.asarray(pts, float).reshape(-1, 2)
	return p @ A[:, :2].T + A[:, 2]


def placement_matrix(pl: dict, profile) -> np.ndarray:
	"""Scan mm -> board mm affine of a stored placement (``theta_deg``, ``pivot_mm``, ``dx_mm``, ``dy_mm``, ``cell``)."""
	return pose_matrix(pl["theta_deg"], pl["pivot_mm"], cell_centre_mm(profile, *pl["cell"]), (pl["dx_mm"], pl["dy_mm"]))


def board_contour(shape, pl: dict, profile) -> np.ndarray:
	"""The piece contour (``shape.c``) in board mm under placement ``pl``."""
	return _apply(placement_matrix(pl, profile), shape.c)


# ---------------------------------------------------------------- initial pose
def _section_rotation(project, gid: str, cache: dict) -> float:
	if gid not in cache:
		from src.legacy import page_rotation
		s = project.sections[gid]
		cache[gid] = page_rotation([project.shape(pid) for pid in s.cells_local if project.shape(pid) is not None])
	return cache[gid]


def initial_theta(project, pid: str, cache: Optional[dict] = None) -> Optional[float]:
	"""Initial board pose of a placed piece: the log ``theta_deg``, else (legacy sections) the
	section rotation + the body angle + the anchor rotation (as :func:`src.legacy.solve_project_sections`),
	else None."""
	p = project.piece(pid)
	if p.theta_deg is not None:
		return float(p.theta_deg)
	if p.seccao_id and p.seccao_id in project.sections:
		s = project.sections[p.seccao_id]
		if not s.anchor.get("anchored"):
			return None
		sh = project.shape(pid)
		if sh is None:
			return float(s.anchor.get("rot") or 0)
		rot = _section_rotation(project, p.seccao_id, cache if cache is not None else {})
		return float(rot + wrap_deg(body_beta_deg(sh) - rot) + float(s.anchor.get("rot") or 0))
	return None


def baseline_placement(project, pid: str) -> Optional[dict]:
	"""The pose ``tools/gui_mock/make_mock.py`` uses (BEFORE): contour point mean on the cell centre,
	rotation = log ``theta_deg`` or the section anchor rotation (multiple of 90)."""
	p = project.piece(pid)
	sh = project.shape(pid)
	if p.celula is None or sh is None:
		return None
	if p.theta_deg is not None:
		th = float(p.theta_deg)
	elif p.seccao_id and p.seccao_id in project.sections:
		th = float(project.sections[p.seccao_id].anchor.get("rot") or 0)
	else:
		th = 0.0
	cpx = project.contour_px(pid)
	mmpp = _scan_mmpp(project, p.scan_id)
	mean = np.asarray(cpx, float).reshape(-1, 2).mean(0) * mmpp if cpx is not None else sh.c.mean(0)
	piv = body_center_mm(sh)
	d = _R(th) @ (piv - mean)
	return {"cell": list(p.celula), "theta_deg": th, "pivot_mm": [float(v) for v in piv], "dx_mm": float(d[0]),
			"dy_mm": float(d[1]), "method": "baseline", "residual_mm": None, "score": None}


def _scan_mmpp(project, sid: str) -> float:
	s = project.model.scans.get(sid) or {}
	v = (s.get("meta") or {}).get("mm_per_px")
	return float(v) if v else 25.4 / float(s.get("dpi") or project.profile.dpi)


# ---------------------------------------------------------------- warping helpers (pure)
def _crop_to_out(theta_deg, pivot_mm, centre_mm, d_mm, origin_px, mmpp, scale_xy, out_origin) -> np.ndarray:
	"""2x3 affine crop px index -> output px index.

	Output index = ``scale_xy`` * board mm - 0.5 - ``out_origin``; crop index u maps to scan mm
	``(u + origin_px) * mmpp``.
	"""
	B = pose_matrix(theta_deg, pivot_mm, centre_mm, d_mm)
	L = B[:, :2] * mmpp
	b = B[:, :2] @ (np.asarray(origin_px, float) * mmpp) + B[:, 2]
	S = np.diag([float(scale_xy[0]), float(scale_xy[1])])
	return np.c_[S @ L, S @ b - 0.5 - np.asarray(out_origin, float)]


def _warp(img: np.ndarray, A: np.ndarray, size, *, interp=cv2.INTER_LINEAR, border=cv2.BORDER_CONSTANT) -> np.ndarray:
	"""warpAffine with a pre-reduction (INTER_AREA) when ``A`` shrinks by more than 1.5x (no aliasing)."""
	s = float(np.sqrt(abs(np.linalg.det(A[:, :2]))))
	if s < 1.0 / 1.5:
		h, w = img.shape[:2]
		nw, nh = max(1, int(round(w * s))), max(1, int(round(h * s)))
		fx, fy = nw / float(w), nh / float(h)
		img = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
		# u = (u' + 0.5) / f - 0.5
		P = np.array([[1.0 / fx, 0, 0.5 / fx - 0.5], [0, 1.0 / fy, 0.5 / fy - 0.5], [0, 0, 1]])
		A = (np.vstack([A, [0, 0, 1]]) @ P)[:2]
	return cv2.warpAffine(img, A, (int(size[0]), int(size[1])), flags=interp, borderMode=border)


def _lab(rgb_u8: np.ndarray) -> np.ndarray:
	return cv2.cvtColor(np.ascontiguousarray(rgb_u8[..., :3]).astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB)


# ---------------------------------------------------------------- image refinement (pure)
def _grad_mag(L: np.ndarray) -> np.ndarray:
	gx = cv2.Sobel(L, cv2.CV_32F, 1, 0, ksize=3)
	gy = cv2.Sobel(L, cv2.CV_32F, 0, 1, ksize=3)
	return np.sqrt(gx * gx + gy * gy)


def _corr(img: np.ndarray, tpl: np.ndarray) -> np.ndarray:
	return cv2.matchTemplate(np.ascontiguousarray(img, np.float32), np.ascontiguousarray(tpl, np.float32), cv2.TM_CCORR)


def _score_map(win_lab, win_g, tpl_lab, tpl_g, M, Mg):
	"""RMS dE map and gradient NCC map of a masked template over a window (valid positions)."""
	n = float(M.sum())
	A = sum(_corr(win_lab[..., ch], tpl_lab[..., ch] * M) for ch in range(3))
	B = _corr((win_lab ** 2).sum(-1), M)
	C = float(((tpl_lab ** 2).sum(-1) * M).sum())
	rms = np.sqrt(np.maximum(C - 2 * A + B, 0) / max(n, 1.0))
	ng = float(Mg.sum())
	if ng < 10:
		return rms, np.zeros_like(rms)
	tg = tpl_g * Mg
	sT, sTT = float(tg.sum()), float((tg * tpl_g).sum())
	sI = _corr(win_g, Mg)
	sII = _corr(win_g ** 2, Mg)
	sTI = _corr(win_g, tg)
	num = sTI - sT * sI / ng
	den = np.sqrt(np.maximum((sTT - sT * sT / ng) * (sII - sI * sI / ng), 1e-9))
	return rms, num / den


def _parabola(fm: float, f0: float, fp: float) -> float:
	den = fm - 2 * f0 + fp
	if den <= 1e-12:
		return 0.0
	return float(np.clip(0.5 * (fm - fp) / den, -0.5, 0.5))


def image_refine(rgba: np.ndarray, origin_px, mmpp: float, pivot_mm, cell, theta_deg: float, art: CellArt, *,
				 d_mm=(0.0, 0.0), search_cell: float = IMG_SEARCH_CELL, rot_deg: int = IMG_ROT_DEG,
				 grad_w: float = GRAD_W) -> dict:
	"""Search translation / rotation of a crop against the art around a pose.

	The crop (RGBA, scan frame, top-left at ``origin_px`` scan px) is rendered at the art scale
	with pose ``(theta_deg + r, pivot_mm -> cell centre + d_mm)`` for ``r`` in
	``-rot_deg..rot_deg`` (1 deg), and its masked Lab (L* minus ``art.l_shift``) is correlated
	with the art window +/- ``search_cell`` cell around. Score = RMS dE + ``grad_w`` x (1 -
	gradient-magnitude NCC). Returns ``{dtheta_deg, ddx_mm, ddy_mm, score, score0, dE, ncc}``
	(``score0`` = at the start pose; sub-pixel / sub-degree by parabola) or ``{'error'}``.
	"""
	cw, ch = art.cell_px
	sx, sy = cw / art.pitch_mm[0], ch / art.pitch_mm[1]        # art px per mm
	Sx, Sy = int(np.ceil(search_cell * cw)), int(np.ceil(search_cell * ch))
	alpha = rgba[..., 3]
	H0, W0 = alpha.shape
	ctr = cell_centre_mm_from_art(art, cell)
	corners = np.array([[0, 0], [W0, 0], [W0, H0], [0, H0]], float)
	lab_art = art.lab
	gA = _grad_mag(lab_art[..., 0])
	ah, aw = lab_art.shape[:2]
	res = []
	for r in range(-int(rot_deg), int(rot_deg) + 1):
		A = _crop_to_out(theta_deg + r, pivot_mm, ctr, d_mm, origin_px, mmpp, (sx, sy), (0, 0))
		box = _apply(A, corners)
		x0, y0 = np.floor(box.min(0)).astype(int) - 1
		x1, y1 = np.ceil(box.max(0)).astype(int) + 2
		Aw = A.copy()
		Aw[:, 2] -= [x0, y0]
		size = (x1 - x0, y1 - y0)
		rgb = _warp(np.ascontiguousarray(rgba[..., :3]), Aw, size, border=cv2.BORDER_REPLICATE)
		al = _warp(alpha.astype(np.float32) / 255.0, Aw, size)
		M = (al >= 0.99).astype(np.uint8)
		if IMG_ERODE_PX:
			k = 2 * IMG_ERODE_PX + 1
			M = cv2.erode(M, np.ones((k, k), np.uint8))
		Mg = cv2.erode(M, np.ones((3, 3), np.uint8))
		# window of the art (replicated outside); template pixels outside the art do not count
		X0, Y0, X1, Y1 = x0 - Sx, y0 - Sy, x1 + Sx, y1 + Sy
		pad = max(0, -X0, -Y0, X1 - aw, Y1 - ah)
		labp = cv2.copyMakeBorder(lab_art, pad, pad, pad, pad, cv2.BORDER_REPLICATE) if pad else lab_art
		gp = cv2.copyMakeBorder(gA, pad, pad, pad, pad, cv2.BORDER_REPLICATE) if pad else gA
		win = labp[Y0 + pad:Y1 + pad, X0 + pad:X1 + pad]
		wg = gp[Y0 + pad:Y1 + pad, X0 + pad:X1 + pad]
		yy, xx = np.mgrid[y0:y1, x0:x1]
		inside = (xx >= 0) & (xx < aw) & (yy >= 0) & (yy < ah)
		M = (M.astype(bool) & inside).astype(np.float32)
		Mg = (Mg.astype(bool) & inside).astype(np.float32)
		if M.sum() < 20:
			return {"error": "máscara vazia na arte"}
		tl = _lab(rgb)
		tl[..., 0] -= art.l_shift
		tg = _grad_mag(tl[..., 0])
		rms, ncc = _score_map(win, wg, tl, tg, M, Mg)
		res.append((r, rms + grad_w * (1 - ncc), rms, ncc))
	best = [float(q[1].min()) for q in res]
	ib = int(np.argmin(best))
	r0 = res[ib][0]
	S = res[ib][1]
	iy, ix = np.unravel_index(int(np.argmin(S)), S.shape)
	fx = _parabola(S[iy, ix - 1], S[iy, ix], S[iy, ix + 1]) if 0 < ix < S.shape[1] - 1 else 0.0
	fy = _parabola(S[iy - 1, ix], S[iy, ix], S[iy + 1, ix]) if 0 < iy < S.shape[0] - 1 else 0.0
	fr = _parabola(best[ib - 1], best[ib], best[ib + 1]) if 0 < ib < len(best) - 1 else 0.0
	i0 = [q[0] for q in res].index(0)
	s0 = float(res[i0][1][Sy, Sx])
	return {"dtheta_deg": float(r0 + fr), "ddx_mm": float((ix + fx - Sx) / sx), "ddy_mm": float((iy + fy - Sy) / sy),
			"score": float(S[iy, ix]), "score0": s0, "dE": float(res[ib][2][iy, ix]), "ncc": float(res[ib][3][iy, ix]),
			# a single rotation sample (rot_deg=0, translation only) is not a minimum at the edge of the rotation range
			"at_edge": bool(ix in (0, S.shape[1] - 1) or iy in (0, S.shape[0] - 1)
							or (len(best) > 1 and ib in (0, len(best) - 1))),
			"curve": [round(v, 3) for v in best]}


def cell_centre_mm_from_art(art: CellArt, cell) -> np.ndarray:
	"""Cell centre in mm of the art's pitch (the art frame assumes ``art.pitch_mm`` per cell)."""
	return np.array([(cell[1] - 0.5) * art.pitch_mm[0], (cell[0] - 0.5) * art.pitch_mm[1]])


# ---------------------------------------------------------------- registration
def manual_pose(project, pid: str) -> Optional[dict]:
	"""The piece's ``pose_manual`` (:meth:`src.state.Project.set_pose`) when it applies to its current cell, else None."""
	p = project.piece(pid)
	pm = getattr(p, "pose_manual", None)
	if pm is None or p.celula is None or [int(v) for v in (pm.get("cell") or [])] != [int(v) for v in p.celula]:
		return None
	return pm


def _manual_entry_ok(project, pid: str, pl: dict) -> bool:
	"""``pl`` (a placement entry) agrees with the piece's manual pose: the manual pose itself when there is one
	(unless the entry was asked without it, ``manual_ignorada``), not a manual entry when there is none."""
	pm = manual_pose(project, pid)
	if pm is None:
		return not pl.get("manual")
	if pl.get("manual_ignorada"):
		return True
	return bool(pl.get("manual")) and all(abs(float(pl.get(k) or 0.0) - float(pm[k])) < 1e-9
										  for k in ("theta_deg", "dx_mm", "dy_mm"))


def manual_pose_note(project) -> str:
	"""One output line for the metric tools, which measure with the automatic pose (``manual=False``)."""
	n = sum(1 for pid in placed_ids(project) if manual_pose(project, pid) is not None)
	return f"{n} peças com pose manual: medidas com a pose automática (manual=False)"


def _manual_entry(project, pid: str, pm: dict, sh, profile) -> dict:
	""":func:`register_piece` result of a piece with a manual pose (no registration: the stored pose)."""
	p = project.piece(pid)
	th = float(pm["theta_deg"])
	corner = None
	if sh is not None and sh.ok and len(sh.corners) == 4:
		cr = corner_register(sh, profile, tuple(p.celula), th)
		if cr.get("ok"):
			k, _thk, _rms, fok = min(cr["cands"], key=lambda cd: abs(float(wrap_deg(cd[1] - th))))
			corner = {"theta_deg": th, "k": int(k), "f_ok": bool(fok), "residual_mm": None, "shape_residual_mm": None,
					  "dtheta0_deg": None, "ambiguous": False}
	return {"cell": list(p.celula), "theta_deg": th, "dx_mm": float(pm["dx_mm"]), "dy_mm": float(pm["dy_mm"]),
			"pivot_mm": [float(v) for v in pm["pivot_mm"]], "method": "manual", "manual": True, "rotation": "manual",
			"theta0": None if p.theta_deg is None else float(p.theta_deg), "corner": corner, "image": None, "score": None,
			"residual_mm": None, "shape_residual_mm": None, "manual_t": pm.get("t"), "manual_nota": pm.get("nota") or ""}


def candidate_entry(project, pid: str, theta_deg: float, dx_mm: float, dy_mm: float, pivot_mm=None) -> dict:
	"""A placement entry for a pose not yet stored (the «avaliar» of the pose editor), built as a manual one in
	the piece's current cell (``corner.k`` = the cyclic assignment closest to ``theta_deg``). ``pivot_mm``:
	default the body centre (the pivot :meth:`src.state.Project.set_pose` stores)."""
	p = project.piece(pid)
	sh = project.shape(pid)
	if pivot_mm is None:
		pivot_mm = body_center_mm(sh)
	pm = {"cell": list(p.celula), "theta_deg": float(theta_deg), "dx_mm": float(dx_mm), "dy_mm": float(dy_mm),
		  "pivot_mm": [float(v) for v in pivot_mm], "t": None, "nota": ""}
	return _manual_entry(project, pid, pm, sh, project.profile)


def register_piece(project, pid: str, *, art: Optional[CellArt] = None, profile=None, image: bool = True,
				   _cache: Optional[dict] = None, manual: bool = True) -> dict:
	"""Fine registration of a placed piece in its cell (see the module docstring).

	Manual pose (``Piece.pose_manual`` for the current cell, :meth:`src.state.Project.set_pose`): with ``manual``
	(default) it is returned as is, nothing registered: ``method = rotation = 'manual'``, ``manual`` True,
	``corner = {theta_deg, k (the cyclic assignment whose corner rotation is closest to theta, among all 4),
	f_ok, residual_mm None, ...}``, ``image`` / ``score`` / residuals None. ``manual=False`` gives the automatic
	pose (the metric tools: a hand-set pose is not a measurement), marked ``manual_ignorada`` when the piece has a
	manual pose so :func:`compose_board` keeps it.

	Returns ``{cell, theta_deg, dx_mm, dy_mm, pivot_mm, residual_mm, shape_residual_mm, method,
	score, theta0, corner: {...}, image: {...}}`` with ``method`` in ``corners | corners+image |
	image | none`` (``dx/dy`` = body centre minus cell centre, board mm) or ``{'error': str}``.
	With the corner solution, ``rotation`` says where the rotation came from: ``corners`` or ``F``
	(``F_ROTATION`` on and the piece has an F side: the line fitted to the F side(s) laid on the
	border line(s), :func:`f_rotation`, details in ``f_rotation``; the translation is the corner
	centroid on the cell centre, or, with ``F_TRANSLATION``, the move normal to the border that lays
	the F line(s) on the target line, details in ``f_offset``, :func:`f_translation`; an accepted image
	refinement is added to it without its component normal to a used F side). ``method`` keeps its
	values (``corners`` / ``corners+image``).

	Gate of the corner solution: ``shape_residual_mm`` (corners against their best-fit
	rectangle, i.e. corner-detection consistency) <= ``CORNER_RESIDUAL_MAX_MM``.
	``residual_mm`` (against the nominal cell grown by the silhouette offset) is reported but
	not used as the gate: it mostly measures the cell-size spread of the die (RENDER.md §1).
	The image is the only method when the gate fails, and only if it is confident
	(gradient NCC >= ``IMG_NCC_MIN``, minimum not on the search border); otherwise ``none``
	(the corner pose if there is one, else the initial pose about the body centre).
	"""
	profile = profile or project.profile
	p = project.piece(pid)
	if p.celula is None:
		return {"error": f"{pid} sem célula"}
	sh = project.shape(pid)
	if sh is None:
		return {"error": f"{pid} sem forma (pieces/{p.scan_id}.npz em falta?)"}
	cell = tuple(p.celula)
	pm = manual_pose(project, pid)
	if pm is not None and manual:
		return _manual_entry(project, pid, pm, sh, profile)
	th0 = initial_theta(project, pid, _cache)
	piv = body_center_mm(sh)
	out = {"cell": list(cell), "theta0": th0, "pivot_mm": [float(v) for v in piv], "dx_mm": 0.0, "dy_mm": 0.0,
		   "residual_mm": None, "shape_residual_mm": None, "score": None, "corner": None, "image": None}
	if pm is not None:
		out["manual_ignorada"] = True
	cr = corner_register(sh, profile, cell, th0)
	rgba = None
	mmpp = _scan_mmpp(project, p.scan_id)
	if image and art is not None:
		rgba = project.crop_rgba(pid)
	origin = np.asarray(p.bbox[:2], float) if p.bbox else np.zeros(2)

	def _img(theta, d=(0.0, 0.0), rot=IMG_ROT_DEG):
		if rgba is None:
			return None
		r = image_refine(rgba, origin, mmpp, piv, cell, theta, art, d_mm=d, rot_deg=rot)
		return None if "error" in r else r

	fallback = None
	if cr["ok"]:
		out["corner"] = {k: cr[k] for k in ("theta_deg", "residual_mm", "shape_residual_mm", "k", "f_ok",
											"dtheta0_deg", "ambiguous")}
		theta = cr["theta_deg"]
		if cr["ambiguous"] and rgba is not None:
			# no initial pose: the image picks among the F-valid assignments (score at the corner pose)
			best = None
			for k, th, rms, fok in cr["cands"]:
				if not fok and any(c[3] for c in cr["cands"]):
					continue
				r = _img(th, rot=0)
				if r is not None and (best is None or r["score0"] < best[0]):
					best = (r["score0"], th, rms, k)
			if best is not None:
				theta = best[1]
				out["corner"].update(theta_deg=best[1], residual_mm=best[2], k=best[3])
		out["residual_mm"] = float(out["corner"]["residual_mm"])
		out["shape_residual_mm"] = float(cr["shape_residual_mm"])
		if out["shape_residual_mm"] <= CORNER_RESIDUAL_MAX_MM:
			out["rotation"] = "corners"
			fr = f_rotation(sh, int(out["corner"]["k"]), float(theta)) if F_ROTATION else None
			if fr is not None and abs(fr["dtheta_deg"]) <= F_MAX_DEG:
				# rotation from the F line(s); translation = Kabsch of the 4 corners with that rotation
				# fixed, i.e. corner centroid on the cell centre: the pivot (corner mean) stays on the
				# cell centre and dx = dy = 0, as for the corner solution
				theta = fr["theta_deg"]
				Pc = sh.c[sh.corners]
				Tc = np.roll(cell_corners_mm(profile, cell[0], cell[1], _grow(profile)), -int(out["corner"]["k"]), axis=0)
				Q = (Pc - Pc.mean(0)) @ _R(theta).T + Tc.mean(0)
				out["residual_mm"] = float(np.sqrt(np.mean(np.sum((Q - Tc) ** 2, 1))))
				out["rotation"] = "F"
				out["f_rotation"] = fr
				if F_TRANSLATION:
					# translation normal to the border from the same F line(s): the F line on the target line
					# (border + silhouette offset outside); the tangential component stays the corner one
					ft = f_translation(sh, fr, theta, piv, profile, cell, _grow(profile) if F_TARGET_GROW else 0.0)
					if ft is not None:
						out.update(dx_mm=ft["dx_mm"], dy_mm=ft["dy_mm"], f_offset=ft)
			out.update(theta_deg=float(theta), method="corners")
			d0 = (float(out["dx_mm"]), float(out["dy_mm"]))
			r = _img(theta, d=d0, rot=0)    # translation only: rotation is not observable at the art scale
			if r is not None:
				out["image"] = r
				out["score"] = r["score0"]
				ok = (r["score"] < r["score0"] and not r["at_edge"]
					  and np.hypot(r["ddx_mm"], r["ddy_mm"]) <= IMG_ACCEPT_MM and abs(r["dtheta_deg"]) <= IMG_ACCEPT_DEG)
				out["image"]["accepted"] = bool(ok)
				if ok:
					# added to the F offset; its component normal to a used F side is dropped (the F line is
					# far more precise than the image at 0.75 mm/px, RENDER.md §1, §9)
					dd = _drop_f_normal(np.array([r["ddx_mm"], r["ddy_mm"]]), out.get("f_offset"))
					out.update(theta_deg=float(theta + r["dtheta_deg"]), dx_mm=d0[0] + float(dd[0]), dy_mm=d0[1] + float(dd[1]),
							   method="corners+image", score=r["score"])
			return out
		cands = [float(theta)]
		fallback = float(theta)
	else:
		if th0 is not None:
			b = body_beta_deg(sh)
			cands = [float(b + 90.0 * np.round((th0 - b) / 90.0))]
			fallback = cands[0]
		else:
			cands = [body_beta_deg(sh) + 90.0 * m for m in range(4)]
	# image only (no corners, or corner gate failed); kept only if confident
	best = None
	for th in cands:
		r = _img(th)
		if r is not None and (best is None or r["score"] < best[1]["score"]):
			best = (th, r)
	if best is not None and best[1]["ncc"] >= IMG_NCC_MIN and not best[1]["at_edge"]:
		th, r = best
		r["accepted"] = True
		out.update(theta_deg=float(th + r["dtheta_deg"]), dx_mm=r["ddx_mm"], dy_mm=r["ddy_mm"], method="image",
				   score=r["score"], image=r)
		return out
	if best is not None:
		best[1]["accepted"] = False
		out["image"] = best[1]
	out.update(theta_deg=float(fallback if fallback is not None else body_beta_deg(sh)), method="none")
	return out


def _entry_key(project, pid: str) -> list:
	"""Cache key of a placement entry: cell, log theta, scan, index, section anchor; plus, only when the piece
	has a manual pose, ``['manual', t, theta, dx, dy]`` (so the keys of pieces without one, and the caches
	written before the manual pose existed, keep matching)."""
	p = project.piece(pid)
	a = project.sections[p.seccao_id].anchor if p.seccao_id in project.sections else {}
	key = [list(p.celula) if p.celula else None, p.theta_deg, p.scan_id, p.index_in_scan, a.get("rot"),
		   a.get("l0"), a.get("c0")]
	pm = manual_pose(project, pid)
	if pm is not None:
		key.append(["manual", pm.get("t"), round(float(pm["theta_deg"]), 4), round(float(pm["dx_mm"]), 4),
					round(float(pm["dy_mm"]), 4)])
	return key


def load_placements(project) -> dict:
	"""``render/placements.json`` as ``{log_len, version, placements: {pid: entry}}`` (empty if absent)."""
	fp = project.p("render", "placements.json")
	if not os.path.exists(fp):
		return {"log_len": None, "version": PLACEMENTS_VERSION, "placements": {}}
	with open(fp, encoding="utf-8") as f:
		d = json.load(f)
	rule = _rule_flags()
	if d.get("version") != PLACEMENTS_VERSION or any(d.get(k, False) != v for k, v in rule.items()):
		# another registration rule (F_ROTATION / F_TRANSLATION / its target switched since the file was
		# written; a file without the keys predates them): stale
		return {"log_len": None, "version": PLACEMENTS_VERSION, "placements": {}}
	return d


def _rule_flags() -> dict:
	"""Registration-rule switches stored in ``placements.json``: ``f_rotation`` (bool), ``f_translation``
	(False, or the target: ``"grow"`` = border + silhouette offset, ``"borda"`` = the border line)."""
	return {"f_rotation": bool(F_ROTATION),
			"f_translation": (("grow" if F_TARGET_GROW else "borda") if (F_ROTATION and F_TRANSLATION) else False)}


def save_placements(project, d: dict) -> str:
	d.update(_rule_flags())
	fp = project.p("render", "placements.json")
	os.makedirs(os.path.dirname(fp), exist_ok=True)
	tmp = fp + ".tmp"
	with open(tmp, "w", encoding="utf-8", newline="\n") as f:
		json.dump(d, f, ensure_ascii=False, indent=0, default=_json_default)
		f.write("\n")
	os.replace(tmp, fp)
	return fp


def _json_default(o):
	if isinstance(o, (np.floating,)):
		return float(o)
	if isinstance(o, (np.integer,)):
		return int(o)
	if isinstance(o, (np.bool_,)):
		return bool(o)
	if isinstance(o, np.ndarray):
		return o.tolist()
	raise TypeError(type(o))


def _log_len(project) -> int:
	with open(project.log_path, encoding="utf-8") as f:
		return sum(1 for line in f if line.strip())


def placed_ids(project) -> list:
	return sorted(pid for pid, p in project.pieces.items() if p.estado == "colocada" and p.celula is not None)


def register_all(project, *, art: Optional[CellArt] = None, image: bool = True, force: bool = False, relax_pass=None,
				 progress=print, manual: bool = True) -> dict:
	"""Register every placed piece (cache-aware) and write ``render/placements.json``.

	An entry is reused when the log length is unchanged, or when its key (cell, log theta,
	scan, index, section anchor, manual pose) is unchanged. ``relax_pass``: None = automatic (only when
	|gap| > ``RELAX_GAP_MM`` on more than ``RELAX_SHARE`` of the seams), True / False to force; the
	relaxation never moves a manual pose. ``manual=False`` (metric tools on a copy): the automatic pose
	of every piece; the entries of pieces with a manual pose get a key that never matches
	:func:`_entry_key` (suffix ``'auto'``), so the GUI does not draw them.
	Returns ``{pid: placement}``.
	"""
	if image and art is None:
		art = CellArt.load(project.profile, REPO)
	old = load_placements(project)
	n_log = _log_len(project)
	same_log = old.get("log_len") == n_log and not force
	out, cache, t0, n_new = {}, {}, time.time(), 0
	ids = placed_ids(project)
	for i, pid in enumerate(ids):
		key = _entry_key(project, pid)
		has_pm = manual_pose(project, pid) is not None
		if not manual and has_pm:
			key = key + ["auto"]
		e = old["placements"].get(pid)
		if (e is not None and not force and (same_log or e.get("key") == key) and e.get("image_used") == bool(image)
				and bool(e.get("manual")) == (manual and has_pm) and bool(e.get("manual_ignorada")) == (not manual and has_pm)):
			out[pid] = e
			continue
		r = register_piece(project, pid, art=art, image=image, _cache=cache, manual=manual)
		if "error" in r:
			if progress:
				progress(f"  {pid}: {r['error']}")
			continue
		r["key"] = key
		r["image_used"] = bool(image)
		out[pid] = r
		n_new += 1
		if progress and n_new % 100 == 0:
			progress(f"  registadas {n_new} ({i + 1}/{len(ids)}) {time.time() - t0:.0f} s")
	gaps = seam_gaps(project, out)
	share = np.mean([abs(g["gap_mm"]) > RELAX_GAP_MM for g in gaps]) if gaps else 0.0
	do_relax = relax_pass if relax_pass is not None else share > RELAX_SHARE
	if do_relax:
		out = relax(project, out)
	save_placements(project, {"log_len": n_log, "version": PLACEMENTS_VERSION, "relaxed": bool(do_relax),
							  "share_gap_gt": float(share), "placements": out})
	if progress:
		progress(f"registo: {len(out)} peças ({n_new} novas, {time.time() - t0:.1f} s); |gap| > {RELAX_GAP_MM} mm em "
				 f"{100 * share:.1f} % das junções; relaxação {'sim' if do_relax else 'não'}")
	return out


def effective_pose(project, pid: str, placements: Optional[dict] = None) -> dict:
	"""The pose the board shows for a placed piece: the ``placements`` entry (default ``render/placements.json``)
	when its key holds and it agrees with the manual pose, else :func:`register_piece` without the image (the
	manual pose when there is one). ``{'error': str}`` if the piece cannot be registered."""
	if placements is None:
		placements = load_placements(project)["placements"]
	e = placements.get(pid)
	if e is not None and e.get("key") == _entry_key(project, pid) and _manual_entry_ok(project, pid, e):
		return e
	return register_piece(project, pid, art=None, image=False)


def pose_brief(e: dict, full: bool = False) -> dict:
	"""``{theta_deg, dx_mm, dy_mm, method, manual}`` of a placement entry (the ``antes`` of ``pose_set``); with
	``full`` also ``pivot_mm``, ``residual_mm``, ``shape_residual_mm``, ``corner_k`` (the 90° assignment of the
	corner registration) and ``rotation``: the pair (automatic pose, manual pose) that
	``python -m src.overrides --pares`` measures (nothing is learnt from it)."""
	out = {"theta_deg": float(e["theta_deg"]), "dx_mm": float(e.get("dx_mm") or 0.0), "dy_mm": float(e.get("dy_mm") or 0.0),
		   "method": e.get("method"), "manual": bool(e.get("manual"))}
	if full:
		piv = e.get("pivot_mm")
		cr = e.get("corner") or {}
		out.update(pivot_mm=(None if piv is None else [float(piv[0]), float(piv[1])]),
				   residual_mm=(None if e.get("residual_mm") is None else float(e["residual_mm"])),
				   shape_residual_mm=(None if e.get("shape_residual_mm") is None else float(e["shape_residual_mm"])),
				   corner_k=(None if cr.get("k") is None else int(cr["k"])), rotation=e.get("rotation"))
	return out


def registered_theta(project, pid: str) -> Optional[float]:
	"""Board rotation (deg, complex convention) of a placed piece from the registration cache
	(computed on the fly without the image step if absent; the manual pose when there is one, through
	the key); None if the piece is not placed."""
	p = project.piece(pid)
	if p.estado != "colocada" or p.celula is None:
		return None
	e = load_placements(project)["placements"].get(pid)
	if e is not None and e.get("key") == _entry_key(project, pid):
		return float(e["theta_deg"])
	r = register_piece(project, pid, art=None, image=False)
	return None if "error" in r else float(r["theta_deg"])


# ---------------------------------------------------------------- seam metric
def _side_points(shape, i: int) -> np.ndarray:
	a, b = int(shape.corners[i]), int(shape.corners[(i + 1) % 4])
	seg = shape.c[a:b + 1] if b > a else np.vstack([shape.c[a:], shape.c[:b + 1]])
	n = len(seg)
	k = int(round(SEAM_TRIM * n))
	return seg[k:n - k] if n - 2 * k >= 3 else seg


def _facing_points(shape, A: np.ndarray, edge_mid: np.ndarray, edge_dir: np.ndarray, half_len: float) -> np.ndarray:
	"""Board-mm contour points of the side facing a shared edge (side by chord midpoint; band fallback)."""
	if shape.ok and len(shape.corners) == 4:
		mids = [_apply(A, 0.5 * (s.p0_mm + s.p1_mm))[0] for s in shape.sides]
		i = int(np.argmin([np.linalg.norm(m - edge_mid) for m in mids]))
		return _apply(A, _side_points(shape, i))
	pts = _apply(A, shape.c)
	q = pts - edge_mid
	along = q @ edge_dir
	across = q @ np.array([-edge_dir[1], edge_dir[0]])
	sel = (np.abs(along) <= (1 - 2 * SEAM_TRIM) * half_len) & (np.abs(across) <= SEAM_BAND_MM)
	return pts[sel]


def _signed_gap(pts: np.ndarray, poly: np.ndarray) -> np.ndarray:
	c = np.asarray(poly, np.float32).reshape(-1, 1, 2)
	return np.array([-cv2.pointPolygonTest(c, (float(x), float(y)), True) for x, y in pts])


def seam_gaps(project, placements: dict, *, offset_mm: Optional[float] = None, shapes: Optional[dict] = None) -> list:
	"""Signed gap between every pair of horizontally / vertically adjacent placed pieces.

	For each pair the contour points of the side of A facing B (corner trims of ``SEAM_TRIM``)
	are measured against B's whole contour (``-pointPolygonTest``: positive = outside B = gap)
	and vice versa; ``gap_sil_mm`` = mean of the two medians (silhouettes), ``gap_mm`` =
	``gap_sil_mm + 2 * offset_mm`` (cut-line estimate: each silhouette sits ``offset_mm``
	outside its cut). Returns ``[{a, b, cells, dir, gap_mm, gap_sil_mm}]``.
	"""
	prof = project.profile
	if offset_mm is None:
		offset_mm = float(((prof.calibration or {}).get("celula_silhueta") or {}).get("offset_mm") or 0.0)
	w, h = float(prof.cell_mm["w"]), float(prof.cell_mm["h"])
	by_cell = {tuple(e["cell"]): pid for pid, e in placements.items()}
	shp = shapes if shapes is not None else {}
	mats, polys = {}, {}

	def get(pid):
		if pid not in mats:
			sh = shp.get(pid) or project.shape(pid)
			shp[pid] = sh
			mats[pid] = placement_matrix(placements[pid], prof)
			polys[pid] = _apply(mats[pid], sh.c)
		return shp[pid], mats[pid], polys[pid]

	out = []
	for cell, a in sorted(by_cell.items()):
		for d, (dl, dc) in _STEP.items():
			b = by_cell.get((cell[0] + dl, cell[1] + dc))
			if b is None:
				continue
			sa, Aa, pa = get(a)
			sb, Ab, pb = get(b)
			if d == "E":
				mid = np.array([cell[1] * w, (cell[0] - 0.5) * h])
				ed, half = np.array([0.0, 1.0]), h / 2
			else:
				mid = np.array([(cell[1] - 0.5) * w, cell[0] * h])
				ed, half = np.array([1.0, 0.0]), w / 2
			qa = _facing_points(sa, Aa, mid, ed, half)
			qb = _facing_points(sb, Ab, mid, ed, half)
			if len(qa) < 3 or len(qb) < 3:
				continue
			g = 0.5 * (float(np.median(_signed_gap(qa, pb))) + float(np.median(_signed_gap(qb, pa))))
			out.append({"a": a, "b": b, "cells": [list(cell), [cell[0] + dl, cell[1] + dc]], "dir": d,
						"gap_sil_mm": g, "gap_mm": g + 2 * offset_mm})
	return out


def relax(project, placements: dict, *, max_mm: float = RELAX_MAX_MM, iters: int = 6) -> dict:
	"""Local relaxation: each piece moves (<= ``max_mm`` from its registration) to cancel the mean
	cut-line gap with its registered neighbours (Jacobi iterations, half steps). Returns a copy."""
	out = {k: dict(v) for k, v in placements.items()}
	base = {k: np.array([v["dx_mm"], v["dy_mm"]]) for k, v in placements.items()}
	for _ in range(iters):
		gaps = seam_gaps(project, out)
		push = {k: [] for k in out}
		for g in gaps:
			u = np.array([1.0, 0.0]) if g["dir"] == "E" else np.array([0.0, 1.0])
			# gap > 0: a moves towards b (+u), b towards a (-u), each half
			push[g["a"]].append(0.5 * g["gap_mm"] * u)
			push[g["b"]].append(-0.5 * g["gap_mm"] * u)
		for k, v in push.items():
			if not v or out[k].get("method") == "manual":     # a pose set by hand is never moved
				continue
			# border pieces keep their F line(s) on the target: no move normal to a used F side
			step = _drop_f_normal(0.5 * np.mean(v, axis=0), out[k].get("f_offset"))
			cur =np.array([out[k]["dx_mm"], out[k]["dy_mm"]]) + step
			dd = cur - base[k]
			n = np.linalg.norm(dd)
			if n > max_mm:
				cur = base[k] + dd * max_mm / n
			out[k]["dx_mm"], out[k]["dy_mm"] = float(cur[0]), float(cur[1])
			out[k]["relaxed"] = True
	return out


# ---------------------------------------------------------------- fringe cleaning (pure)
def bg_distance(lab: np.ndarray, background_lab, luma_weight: float = BG_LUMA_WEIGHT) -> np.ndarray:
	"""``sqrt(w dL^2 + da^2 + db^2)`` (CIE Lab, L 0..100) to ``background_lab``, as float32."""
	d = np.asarray(lab, np.float32) - np.asarray(background_lab, np.float32).reshape(1, 1, 3)
	return np.sqrt(luma_weight * d[..., 0] ** 2 + d[..., 1] ** 2 + d[..., 2] ** 2).astype(np.float32)


def _depth_px(alpha: np.ndarray) -> np.ndarray:
	"""Distance (px) of every alpha pixel to the nearest non-alpha pixel; the crop border counts as outside."""
	a = np.pad((alpha > 0).astype(np.uint8), 1)
	return cv2.distanceTransform(a, cv2.DIST_L2, 5)[1:-1, 1:-1]


def _touching(cand: np.ndarray, seed: np.ndarray) -> np.ndarray:
	"""Union of the 8-connected components of ``cand`` that contain a ``seed`` pixel."""
	if not cand.any():
		return np.zeros_like(cand, bool)
	n, lab = cv2.connectedComponents(cand.astype(np.uint8), connectivity=8)
	keep = np.zeros(n, bool)
	keep[np.unique(lab[seed & cand])] = True
	keep[0] = False
	return keep[lab]


def fringe_masks(rgba: np.ndarray, background_lab, mm_per_px: float, *, band_mm: float = BAND_MM,
				 bg_dist_max: float = BG_DIST_MAX, piece_frac: float = PIECE_P5_FRAC, shadow: bool = False,
				 shadow_l_delta: float = SHADOW_L_DELTA, shadow_chroma_max: float = SHADOW_CHROMA_MAX) -> dict:
	"""Masks of the fringe cleaning: ``{alpha, band, depth_px, green, shadow, removed, interior, L_med}``.

	``green`` = band pixels with :func:`bg_distance` < ``thr`` in components touching the alpha
	boundary, ``thr = max(bg_dist_max, piece_frac x p5 of the piece's own interior distance)``
	(a piece far from the background, e.g. sky, gets a higher threshold; dark grass keeps the
	global one); ``shadow`` (second pass, only if ``shadow``) = band pixels left after the green
	pass with L* < interior median - ``shadow_l_delta`` and chroma < ``shadow_chroma_max``, in
	components touching the new boundary. ``band_mm`` is clamped to ``LIGHT_BAND_MAX_MM``; only
	:func:`clean_crop` with ``light_band_mm`` asks for more than ``BAND_MM``.
	"""
	band_mm = min(float(band_mm), max(BAND_MM, LIGHT_BAND_MAX_MM))
	alpha = np.asarray(rgba)[..., 3] > 0
	depth = _depth_px(alpha)
	band_px = band_mm / float(mm_per_px)
	band = alpha & (depth <= band_px)
	ring = alpha & (depth <= 1.5)
	lab = _lab(np.asarray(rgba)[..., :3])
	d = bg_distance(lab, background_lab)
	interior = alpha & (depth > INTERIOR_MM / float(mm_per_px))
	thr = float(bg_dist_max)
	p5 = float(np.percentile(d[interior], 5)) if interior.sum() >= 50 else float("nan")
	if piece_frac and np.isfinite(p5):
		thr = max(thr, float(piece_frac) * p5)
	green = _touching(band & (d < thr), ring)
	L_med = float(np.median(lab[..., 0][interior])) if interior.any() else float("nan")
	sh = np.zeros_like(alpha)
	if shadow and interior.any():
		a2 = alpha & ~green
		ring2 = a2 & cv2.dilate((~a2).astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
		chroma = np.hypot(lab[..., 1], lab[..., 2])
		cand = band & a2 & (lab[..., 0] < L_med - shadow_l_delta) & (chroma < shadow_chroma_max)
		sh = _touching(cand, ring2)
	return {"alpha": alpha, "band": band, "depth_px": depth, "green": green, "shadow": sh, "removed": green | sh,
			"interior": interior, "L_med": L_med, "bg_dist": d, "thr": thr, "p5": p5}


def is_light(m: dict) -> bool:
	"""Light piece (sky, cloud, rock): p5 of its interior background distance > ``LIGHT_PIECE_P5_MIN``."""
	return bool(np.isfinite(m.get("p5", float("nan"))) and m["p5"] > LIGHT_PIECE_P5_MIN)


def decontaminate(rgba: np.ndarray, m: dict, background_lab, *, return_share: bool = False):
	"""RGB with the background component taken out of the kept band pixels.

	For each band pixel left by the cleaning, ``ci`` = Lab of the nearest interior pixel (deeper
	than the band); ``t = clip(<c - ci, bg - ci> / |bg - ci|^2, 0, 1)`` is the share of
	background in the blend and ``c - t (bg - ci)`` the corrected colour. Pixels outside the
	band are returned unchanged, and so are band pixels whose blend (``t > DECONT_T_MIN``) is not
	connected to the outside (alpha boundary ring or removed fringe). ``return_share``: also return ``t`` as an ``(h, w)`` float map
	(0 outside the kept band), the paper share used as transparency by :func:`clean_crop`.
	"""
	rgb = np.ascontiguousarray(np.asarray(rgba)[..., :3])
	sel = m["band"] & ~m["removed"]
	deep = m["alpha"] & ~m["band"]
	if not sel.any() or not deep.any():
		return (rgb.copy(), np.zeros(rgb.shape[:2], np.float32)) if return_share else rgb.copy()
	lab = _lab(rgb)
	_, lbl = cv2.distanceTransformWithLabels((~deep).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
	lut = np.zeros((int(lbl.max()) + 1, 3), np.float32)
	lut[lbl[deep]] = lab[deep]
	ci = lut[lbl[sel]]
	c = lab[sel]
	v = np.asarray(background_lab, np.float32)[None, :] - ci
	t = np.clip(np.sum((c - ci) * v, 1) / np.maximum(np.sum(v * v, 1), 1e-6), 0.0, 1.0)
	# same rule as the removal: only blends connected to the outside (boundary ring or removed fringe)
	tmap = np.zeros(rgb.shape[:2], np.float32)
	tmap[sel] = t
	ring = m["alpha"] & (m["depth_px"] <= 1.5)
	seed = ring | cv2.dilate(m["removed"].astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
	conn = _touching(sel & (tmap > DECONT_T_MIN), seed)
	t = np.where(conn[sel], t, 0.0)
	lab[sel] = c - t[:, None] * v
	out_rgb = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
	out = rgb.copy()
	out[sel] = np.clip(out_rgb[sel] * 255.0 + 0.5, 0, 255).astype(np.uint8)
	if return_share:
		share = np.zeros(rgb.shape[:2], np.float32)
		share[sel] = t
		return out, share
	return out


def _clean(rgba: np.ndarray, background_lab, mm_per_px: float, *, band_mm: float = BAND_MM,
		   shadow: bool = SHADOW_DEFAULT, bg_dist_max: float = BG_DIST_MAX, decont: bool = True,
		   light_band_mm: Optional[float] = LIGHT_BAND_MM):
	band_mm = min(float(band_mm), BAND_MM)
	m = fringe_masks(rgba, background_lab, mm_per_px, band_mm=band_mm, bg_dist_max=bg_dist_max, shadow=shadow)
	if light_band_mm and float(light_band_mm) > band_mm and is_light(m):
		band_mm = min(float(light_band_mm), LIGHT_BAND_MAX_MM)
		m = fringe_masks(rgba, background_lab, mm_per_px, band_mm=band_mm, bg_dist_max=bg_dist_max, shadow=shadow)
	out = np.array(rgba, np.uint8, copy=True)
	if decont and is_light(m):
		out[..., :3], share = decontaminate(rgba, m, background_lab, return_share=True)
		a = out[..., 3].astype(np.float32) * (1.0 - share)
		out[..., 3] = np.clip(a + 0.5, 0, 255).astype(np.uint8)
	out[..., 3][m["removed"]] = 0
	# the paper colour under the now transparent pixels must not leak into a resampled rim
	return _fill_transparent(out, band_mm / float(mm_per_px)), m


def clean_crop(rgba: np.ndarray, background_lab, mm_per_px: float, *, band_mm: float = BAND_MM,
			   shadow: bool = SHADOW_DEFAULT, bg_dist_max: float = BG_DIST_MAX, decont: bool = True,
			   light_band_mm: Optional[float] = LIGHT_BAND_MM) -> np.ndarray:
	"""RGBA crop with the green fringe (and optionally the shadow) made transparent.

	The colour under every transparent pixel is replaced by the colour of the nearest visible
	pixel deeper than the band (:func:`_fill_transparent`): alpha 0 keeps no paper green that a
	straight-alpha resampler could blend into the rim.

	Only pixels within ``band_mm`` (<= 0.7 mm) of the alpha boundary can change, by
	construction (:func:`fringe_masks`): alpha is zeroed on the fringe and, on pieces whose
	interior is far from the background (:func:`is_light`: interior p5 distance >
	``LIGHT_PIECE_P5_MIN``; sky, cloud, rock, never dark grass), the kept band pixels are unmixed
	(matting): colour :func:`decontaminate`-d and alpha x (1 - paper share). Pixels deeper than the band are returned unchanged.
	``band_mm`` is clamped to ``BAND_MM`` (0.7 mm) for every piece. ``light_band_mm`` (default
	``LIGHT_BAND_MM`` = 1.2, max ``LIGHT_BAND_MAX_MM``; None/0 = off): band of the light pieces only
	(RENDER.md §2.5: on sky the green reaches 0.74-1.17 mm inside the silhouette on some sides).
	"""
	return _clean(rgba, background_lab, mm_per_px, band_mm=band_mm, shadow=shadow, bg_dist_max=bg_dist_max,
				  decont=decont, light_band_mm=light_band_mm)[0]


def clean_all(project, *, shadow: bool = SHADOW_DEFAULT, force: bool = False,
			  light_band_mm: Optional[float] = LIGHT_BAND_MM,
			  progress=print) -> dict:
	"""Write ``render/clean/P####.png`` for every placed piece (skips up-to-date files unless ``force``).

	Returns ``{pid: {removed, removed_frac, deep}}`` (``deep`` = removed pixels deeper than the band:
	always 0)."""
	from PIL import Image
	bg = project.profile.background_lab
	od = project.p("render", "clean")
	os.makedirs(od, exist_ok=True)
	stats, t0 = {}, time.time()
	for pid in placed_ids(project):
		p = project.piece(pid)
		fp = os.path.join(od, f"{pid}.png")
		src = project.p(p.crop_path) if p.crop_path else None
		if src is None or not os.path.exists(src):
			continue
		if not force and os.path.exists(fp) and os.path.getmtime(fp) >= os.path.getmtime(src):
			continue
		rgba = project.crop_rgba(pid)
		mmpp = _scan_mmpp(project, p.scan_id)
		out, m = _clean(rgba, bg, mmpp, shadow=shadow, light_band_mm=light_band_mm)
		Image.fromarray(out).save(fp)
		lim = (min(light_band_mm, LIGHT_BAND_MAX_MM) if light_band_mm and is_light(m) else BAND_MM) / mmpp
		deep = int((m["removed"] & (m["depth_px"] > lim)).sum())
		stats[pid] = {"removed": int(m["removed"].sum()), "removed_frac": float(m["removed"].sum() / max(1, m["alpha"].sum())),
					  "deep": deep}
	if progress:
		progress(f"limpeza: {len(stats)} recortes escritos em {od} ({time.time() - t0:.1f} s)")
	return stats


# ---------------------------------------------------------------- composition
def has_aresta(project, pid: str) -> bool:
	"""True if ``pid``'s last override line carries a painted edge (A2): its display crop is :func:`aresta_rgba`."""
	return pid in OV.latest_arestas(project)


def aresta_rgba(project, pid: str) -> Optional[np.ndarray]:
	"""Display crop of a piece with a painted edge (:func:`src.overrides.aresta_px`, A2): the stored crop with
	alpha = the edge polygon filled (in crop px, origin ``bbox[:2]``) and inside the crop's own alpha (the crop
	is the index silhouette, which holds the edge; outside it the stored colour is a fill), the colour under
	alpha 0 that of the nearest visible pixel. None when the piece has no edge or no crop."""
	a = OV.aresta_px(project, pid)
	if a is None:
		return None
	rgba = project.crop_rgba(pid)
	p = project.piece(pid)
	if rgba is None or not p.bbox:
		return None
	m = np.zeros(rgba.shape[:2], np.uint8)
	cv2.fillPoly(m, [np.round(a - np.asarray(p.bbox[:2], float)).astype(np.int32).reshape(-1, 1, 2)], 1)
	out = np.array(rgba, np.uint8, copy=True)
	out[..., 3] = np.where((m > 0) & (rgba[..., 3] > 0), 255, 0).astype(np.uint8)
	if not out[..., 3].any():
		return None
	return _fill_transparent(out, BAND_MM / _scan_mmpp(project, p.scan_id))


def _clean_or_crop(project, pid: str) -> Optional[np.ndarray]:
	"""Cleaned crop of ``pid``: ``render/clean/P####.png`` when it is up to date (not older than
	``crops/P####.png`` and of the same size: the rule of :func:`clean_all`), else :func:`clean_crop` on the
	fly; a stale ``render/clean`` file (e.g. left behind by a sheet re-segmented in another checkout) is deleted.
	A piece with a painted edge (:func:`src.overrides.aresta_px`, A2) gets :func:`aresta_rgba` instead: the user
	drew the piece, no fringe rule applies."""
	from PIL import Image
	ar = aresta_rgba(project, pid)
	if ar is not None:
		return ar
	fp = project.p("render", "clean", f"{pid}.png")
	p = project.piece(pid)
	src = project.p(p.crop_path) if p.crop_path else None
	if os.path.exists(fp):
		with Image.open(fp) as im:
			cl = np.asarray(im.convert("RGBA")).copy()
		ok = src is not None and os.path.exists(src) and os.path.getmtime(fp) >= os.path.getmtime(src)
		if ok:
			with Image.open(src) as im:
				ok = im.size == (cl.shape[1], cl.shape[0])
		if ok:
			return cl
		try:
			os.remove(fp)
		except OSError:
			pass
	rgba = project.crop_rgba(pid)
	if rgba is None:
		return None
	return clean_crop(rgba, project.profile.background_lab, _scan_mmpp(project, p.scan_id))


def _art_rgb(profile) -> Optional[np.ndarray]:
	"""Art under the board (BGR uint8), rectified to the cell grid by :func:`src.locate.load_art_rectified`
	(the same board -> art transform as :class:`src.locate.CellArt`); grid px the art file does not
	reach are painted the default ``base_bgr`` grey of :func:`compose_board` (no replicated streaks).
	None if there is no readable art."""
	from src.locate import load_art_rectified
	try:
		rgb = load_art_rectified(profile, REPO, fill=(40, 40, 40))
	except (ValueError, FileNotFoundError):
		return None
	return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def _hatch(img: np.ndarray, x0: int, y0: int, x1: int, y1: int, step: int, colour, lw: int) -> None:
	for j in range(-(y1 - y0), x1 - x0, step):
		p0 = (x0 + j, y0)
		p1 = (x0 + j + (y1 - y0), y1)
		cv2.line(img, p0, p1, colour, lw, cv2.LINE_AA)


def _nearest_colour(rgb: np.ndarray, src: np.ndarray, where: np.ndarray) -> np.ndarray:
	"""Colours (``(n, 3)``) of the nearest ``src`` pixel for each ``where`` pixel (row-major order)."""
	_, lab = cv2.distanceTransformWithLabels((~src).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
	lut = np.zeros((int(lab.max()) + 1, 3), np.uint8)
	lut[lab[src]] = rgb[src]
	return lut[lab[where]]


def _fill_transparent(rgba: np.ndarray, deep_px: float = 0.0) -> np.ndarray:
	"""Copy of ``rgba`` whose colour under alpha == 0 is that of the nearest visible pixel deeper than
	``deep_px`` (any visible pixel if none). Visible pixels and alpha are unchanged."""
	out = np.array(rgba, np.uint8, copy=True)
	vis = out[..., 3] > 0
	if not vis.any() or vis.all():
		return out
	src = vis & (_depth_px(vis) > deep_px) if deep_px > 0 else vis
	if not src.any():
		src = vis
	out[..., :3][~vis] = _nearest_colour(out[..., :3], src, ~vis)
	return out


def _unpremultiply(w: np.ndarray) -> np.ndarray:
	a = np.clip(w[..., 3], 0.0, 1.0)
	col = w[..., :3] / np.maximum(a, 1e-6)[..., None]
	return _fill_transparent(np.dstack([np.clip(col + 0.5, 0, 255), np.clip(a * 255.0 + 0.5, 0, 255)]).astype(np.uint8))


def _premultiply(rgba: np.ndarray) -> np.ndarray:
	al = rgba[..., 3].astype(np.float32) / 255.0
	return np.dstack([rgba[..., :3].astype(np.float32) * al[..., None], al])


def warp_rgba(rgba: np.ndarray, A: np.ndarray, size) -> np.ndarray:
	"""Straight RGBA uint8 warped by the 2x3 ``A`` (source px -> output px) into ``size = (w, h)``,
	resampled with premultiplied alpha (:func:`_warp`: INTER_AREA pre-reduction when shrinking), so
	the colour of transparent pixels never reaches the rim; transparent output pixels get the
	nearest visible colour."""
	return _unpremultiply(_warp(_premultiply(rgba), A, size))


def resize_rgba(rgba: np.ndarray, size) -> np.ndarray:
	"""Straight RGBA uint8 resized to ``size = (w, h)`` with premultiplied alpha (INTER_AREA when shrinking)."""
	w, h = int(size[0]), int(size[1])
	interp = cv2.INTER_AREA if w < rgba.shape[1] or h < rgba.shape[0] else cv2.INTER_LINEAR
	return _unpremultiply(cv2.resize(_premultiply(rgba), (w, h), interpolation=interp))


def shadow_paper_mask(rgba: np.ndarray, background_lab, mm_per_px: float, *, band_mm: float = DISPLAY_SHADOW_BAND_MM,
					  a_max: float = DISPLAY_SHADOW_A_MAX, dist_max: float = DISPLAY_SHADOW_DIST_MAX,
					  l_max: float = DISPLAY_SHADOW_L_MAX) -> np.ndarray:
	"""Visible pixels within ``band_mm`` of the alpha boundary that look like paper darkened by the cast
	shadow (a* < ``a_max``, :func:`bg_distance` < ``dist_max``, L* < ``l_max``), in components touching
	the boundary. Pure; used only for display (:func:`piece_rgba_for_display`, :func:`compose_board`)."""
	alpha = np.asarray(rgba)[..., 3] > 0
	depth = _depth_px(alpha)
	band = alpha & (depth <= float(band_mm) / float(mm_per_px))
	lab = _lab(np.asarray(rgba)[..., :3])
	cand = band & (lab[..., 1] < a_max) & (bg_distance(lab, background_lab) < dist_max) & (lab[..., 0] < l_max)
	return _touching(cand, alpha & (depth <= 1.5))


def paper_pocket_mask(rgba: np.ndarray, background_lab, mm_per_px: float, *, dist_max: float = PAPER_POCKET_DIST_MAX,
					  seed_mm: float = BAND_MM) -> np.ndarray:
	"""Visible pixels of the very paper colour (:func:`bg_distance` < ``dist_max``, at any depth) in components that
	reach within ``seed_mm`` of the alpha boundary (the cleaning band: a pocket is open to the outside through it,
	across a thin layer of blended paper, P0778 0.47 mm): a blank filled with paper by the segmentation (RENDER.md §7).
	The interior of the grass pieces stays far above ``dist_max`` (p1 24.3, RENDER.md §2.1). Pure; display only."""
	alpha = np.asarray(rgba)[..., 3] > 0
	lab = _lab(np.asarray(rgba)[..., :3])
	cand = alpha & (bg_distance(lab, background_lab) < float(dist_max))
	hit = _touching(cand, alpha & (_depth_px(alpha) <= float(seed_mm) / float(mm_per_px)))
	if not hit.any():
		return hit
	# safety: a pocket is a small part of a piece; a piece whose own colours are the paper's is never touched
	if hit.sum() > PAPER_POCKET_MAX_FRAC * max(1, int(alpha.sum())):
		return np.zeros_like(hit)
	return hit


def _display_masks(project, pid: str, rgba: np.ndarray):
	"""``(shadow, pocket)`` masks of a cleaned crop of ``pid`` that the display drops (pocket empty if off)."""
	mmpp = _scan_mmpp(project, project.piece(pid).scan_id)
	bg = project.profile.background_lab
	sh = shadow_paper_mask(rgba, bg, mmpp)
	pk = paper_pocket_mask(rgba, bg, mmpp) if PAPER_POCKETS else np.zeros_like(sh)
	return sh, pk


def _drop_shadow_paper(project, pid: str, rgba: np.ndarray) -> np.ndarray:
	"""Copy of ``rgba`` (a cleaned crop of ``pid``) with :func:`shadow_paper_mask` (and, if ``PAPER_POCKETS``,
	:func:`paper_pocket_mask`) made transparent. Display only: the thumbnails (:func:`piece_rgba_for_display`) and
	the board drawing (:func:`compose_board`), never the index."""
	out = np.array(rgba, np.uint8, copy=True)
	sh, pk = _display_masks(project, pid, out)
	out[..., 3][sh | pk] = 0
	return out


def piece_rgba_for_display(project, pid: str, *, theta_deg: Optional[float] = None, pivot_mm=None,
						   size: Optional[int] = None, px_per_mm: Optional[float] = None) -> Optional[np.ndarray]:
	"""The piece as every thumbnail shows it (cards, fetch sheets, Mesa): straight RGBA uint8 (RGB order).

	Cleaned crop (``render/clean/`` or :func:`clean_crop` on the fly, the same as the board) with the
	colour under alpha 0 replaced by the nearest piece colour and, if ``DISPLAY_SHADOW``, the
	shadow-darkened paper of the outer 0.4 mm dropped (:func:`shadow_paper_mask`, display only: the
	board drawing does the same, ``BOARD_SHADOW``; the index keeps its silhouettes); without ``size`` that crop is returned
	at scan resolution. With ``size`` (``px_per_mm`` default: the scan resolution) it is turned by
	``theta_deg`` (default 0) about ``pivot_mm`` (scan mm; default the crop centre), the pivot at the
	centre of a ``size`` x ``size`` canvas, resampled with premultiplied alpha (:func:`warp_rgba`).
	None when the crop is missing.
	"""
	rgba = _clean_or_crop(project, pid)
	if rgba is None:
		return None
	p = project.piece(pid)
	mmpp = _scan_mmpp(project, p.scan_id)
	if DISPLAY_SHADOW and not has_aresta(project, pid):        # a painted edge already leaves the shadow out
		rgba = _drop_shadow_paper(project, pid, rgba)
	rgba = _fill_transparent(rgba, BAND_MM / mmpp)
	if size is None:
		return rgba
	ppm = float(px_per_mm) if px_per_mm else 1.0 / mmpp
	origin = np.asarray(p.bbox[:2], float) if p.bbox else np.zeros(2)
	if pivot_mm is None:
		pivot_mm = (origin + np.array(rgba.shape[1::-1]) / 2.0) * mmpp
	ctr = np.full(2, (int(size) / 2.0 + 0.5) / ppm)
	A = _crop_to_out(float(theta_deg or 0.0), pivot_mm, ctr, (0.0, 0.0), origin, mmpp, (ppm, ppm), (0, 0))
	return warp_rgba(rgba, A, (int(size), int(size)))


def _bleed_rgba(rgba: np.ndarray, r_px: int, deep_px: float = 0.0):
	"""RGBA padded by ``r_px`` whose alpha is the piece dilated by ``r_px`` and whose colour outside the
	piece is the colour of the nearest piece pixel deeper than ``deep_px`` (any piece pixel if none),
	so a residual rim never spreads into the gaps. Returns ``(rgba_ext, pad)``."""
	a = np.pad(rgba, ((r_px, r_px), (r_px, r_px), (0, 0)))
	inside = a[..., 3] > 0
	if not inside.any():
		return a, r_px
	src = inside & (_depth_px(inside) > deep_px) if deep_px > 0 else inside
	if not src.any():
		src = inside
	out = a.copy()
	out[..., :3][~inside] = _nearest_colour(a[..., :3], src, ~inside)
	k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r_px + 1, 2 * r_px + 1))
	out[..., 3] = cv2.dilate(inside.astype(np.uint8) * 255, k)
	return out, r_px


def compose_board(project, px_per_cell: float, *, region=None, art_alpha: float = 0.34,
				  layers=("art", "pieces", "legacy", "missing_border", "grid"), placements: Optional[dict] = None,
				  art_bgr: Optional[np.ndarray] = None, piece_ids=None, clean: bool = True,
				  depth_priority: bool = True, bleed_mm: float = BLEED_MM, base_bgr=(40, 40, 40),
				  board_shadow: Optional[bool] = None) -> np.ndarray:
	"""Render the board (BGR uint8).

	``px_per_cell`` = output px per cell width (the height follows ``cell_mm``; ~218.5 = 300 dpi
	for the Alpes cell). ``region = (l0, c0, l1, c1)`` (inclusive, 1-based) renders a
	sub-rectangle. Layers: ``art`` (art bbox crop blended at ``art_alpha`` over dark grey;
	``art_alpha=1`` = the art itself), ``pieces`` (cleaned crops warped with ``placements``,
	default the cache / a corner registration without image; drawn in row order), ``legacy``
	(hatched ``ocupada_legado`` cells), ``missing_border`` (red outline on empty border cells),
	``grid``. ``piece_ids`` restricts the pieces drawn; ``clean=False`` draws the raw ``crops/``
	(the BEFORE of RENDER.md). ``depth_priority``: where two silhouettes overlap, each output pixel
	shows the piece it lies deeper in (distance to that piece's own alpha boundary, mm), so the
	seam falls on the medial line of the overlap (the cut line when both silhouettes sit the same
	``offset_mm`` outside it) and the rim of the piece drawn last no longer lies on its
	neighbour; nothing changes where a piece has no neighbour. ``False`` = plain "over" in row order.
	``bleed_mm``: before the pieces, every piece is drawn once extended by this much with the
	colour of its nearest pixel deeper than the fringe band; the pieces then cover it, so it only shows in hairline gaps
	between registered neighbours (and widens the outer frontier by ``bleed_mm``). 0 = off.
	``base_bgr``: colour under everything (dark grey; a vivid colour makes gaps measurable).
	``board_shadow`` (default ``BOARD_SHADOW``): with ``clean``, the paper darkened by the cast shadow in the
	outer ``DISPLAY_SHADOW_BAND_MM`` of each cleaned crop is dropped before drawing (:func:`shadow_paper_mask`,
	the thumbnails' rule; RENDER.md §7): on frontier sides no neighbour covers that rim. The bleed pass keeps the
	cleaned silhouette, so the dropped rim is filled with the piece's deep colour, not the base. Drawing only.
	"""
	if board_shadow is None:
		board_shadow = BOARD_SHADOW
	prof = project.profile
	rows, cols = prof.rows, prof.cols
	l0, c0, l1, c1 = region if region is not None else (1, 1, rows, cols)
	w_mm, h_mm = float(prof.cell_mm["w"]), float(prof.cell_mm["h"])
	ppm = float(px_per_cell) / w_mm
	ox, oy = (c0 - 1) * w_mm * ppm, (l0 - 1) * h_mm * ppm
	W = int(round((c1 - c0 + 1) * w_mm * ppm))
	H = int(round((l1 - l0 + 1) * h_mm * ppm))
	img = np.zeros((H, W, 3), np.uint8) + np.array(base_bgr, np.uint8)
	if "art" in layers:
		art = art_bgr if art_bgr is not None else _art_rgb(prof)
		if art is not None:
			ah, aw = art.shape[:2]
			sx, sy = aw / float(cols * w_mm * ppm), ah / float(rows * h_mm * ppm)
			# output index -> art index: (i + 0.5 + o) * s - 0.5
			A = np.array([[sx, 0, (0.5 + ox) * sx - 0.5], [0, sy, (0.5 + oy) * sy - 0.5]])
			interp = cv2.INTER_CUBIC if sx < 1 else cv2.INTER_AREA
			if sx >= 1:
				big = cv2.resize(art, (int(round(cols * w_mm * ppm)), int(round(rows * h_mm * ppm))), interpolation=cv2.INTER_AREA)
				a_img = big[int(round(oy)):int(round(oy)) + H, int(round(ox)):int(round(ox)) + W]
			else:
				a_img = cv2.warpAffine(art, A, (W, H), flags=interp | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REPLICATE)
			img = cv2.addWeighted(a_img, float(art_alpha), img, 1.0 - float(art_alpha), 0)

	def cell_box(l, c):
		x0 = int(round((c - 1) * w_mm * ppm - ox))
		y0 = int(round((l - 1) * h_mm * ppm - oy))
		return x0, y0, int(round(c * w_mm * ppm - ox)), int(round(l * h_mm * ppm - oy))

	lw = max(1, int(round(px_per_cell / 60)))
	if "legacy" in layers:
		for l in range(l0, l1 + 1):
			for c in range(c0, c1 + 1):
				if project.board[(l, c)]["estado"] == "ocupada_legado":
					x0, y0, x1, y1 = cell_box(l, c)
					sub = img[max(0, y0):y1, max(0, x0):x1]
					hat = sub.copy()
					_hatch(hat, 0, 0, x1 - x0, y1 - y0, max(4, int(px_per_cell / 6)), (166, 143, 125), lw)
					img[max(0, y0):y1, max(0, x0):x1] = cv2.addWeighted(hat, 0.7, sub, 0.3, 0)
	if "pieces" in layers:
		if placements is None:
			placements = load_placements(project)["placements"] or {}
		ids = [pid for pid in placed_ids(project) if piece_ids is None or pid in piece_ids]
		ids = [pid for pid in ids if l0 - 1 <= project.piece(pid).celula[0] <= l1 + 1
			   and c0 - 1 <= project.piece(pid).celula[1] <= c1 + 1]
		ids.sort(key=lambda pid: tuple(project.piece(pid).celula))
		acc = img.astype(np.float32)
		zbuf = np.full((H, W), -np.inf, np.float32)     # depth (mm inside its own silhouette) of the winning piece
		s_mm = 1.0 / ppm                                   # width of the depth-priority transition (1 output px)
		jobs = []
		for pid in ids:
			pl = placements.get(pid)
			if pl is None or not _manual_entry_ok(project, pid, pl):
				pl = register_piece(project, pid, art=None, image=False)
				if "error" in pl:
					continue
			rgba = _clean_or_crop(project, pid) if clean else project.crop_rgba(pid)
			if rgba is None:
				continue
			# the bleed keeps the cleaned silhouette: where the shadow rim is dropped, the gap it leaves at a seam
			# or on the frontier is filled with the piece's own deep colour (as every hairline gap), never the base
			rb = rgba
			if clean and board_shadow and not has_aresta(project, pid):
				sh, pk = _display_masks(project, pid, rgba)
				if (sh | pk).any():
					dropped = np.array(rgba, np.uint8, copy=True)
					dropped[..., 3][sh | pk] = 0
					rb = _fill_transparent(dropped, BAND_MM / _scan_mmpp(project, project.piece(pid).scan_id))
					# extent of the cleaned silhouette (dropped shadow rim in the deep colour), minus a paper pocket:
					# a blank must stay open, not be painted with the piece colour
					rb[..., 3] = np.where(pk, 0, rgba[..., 3])
					rgba = dropped
			jobs.append((pid, pl, rgba, rb))
		passes = (("bleed", "pieces") if bleed_mm and bleed_mm > 0 else ("pieces",))
		for pas, (pid, pl, rgba, rb) in [(q, j) for q in passes for j in jobs]:
			p = project.piece(pid)
			mmpp = _scan_mmpp(project, p.scan_id)
			origin = np.asarray(p.bbox[:2], float)
			if pas == "bleed":
				rgba, pad = _bleed_rgba(rb, max(1, int(round(bleed_mm / mmpp))), BAND_MM / mmpp)
				origin = origin - pad
			A = _crop_to_out(pl["theta_deg"], pl["pivot_mm"], cell_centre_mm(prof, *pl["cell"]), (pl["dx_mm"], pl["dy_mm"]),
							 origin, mmpp, (ppm, ppm), (ox, oy))
			h0, w0 = rgba.shape[:2]
			box = _apply(A, [[0, 0], [w0, 0], [w0, h0], [0, h0]])
			bx0, by0 = np.maximum(np.floor(box.min(0)).astype(int) - 1, 0)
			bx1, by1 = np.minimum(np.ceil(box.max(0)).astype(int) + 2, [W, H])
			if bx1 <= bx0 or by1 <= by0:
				continue
			Aw = A.copy()
			Aw[:, 2] -= [bx0, by0]
			size = (bx1 - bx0, by1 - by0)
			# premultiplied warp: colour of transparent pixels does not bleed into the edge
			al = rgba[..., 3].astype(np.float32) / 255.0
			pm = rgba[..., :3].astype(np.float32) * al[..., None]
			wpm = _warp(np.dstack([pm, al]), Aw, size)
			a = wpm[..., 3]
			col = wpm[..., :3][..., ::-1] / np.maximum(a, 1e-6)[..., None]    # RGB -> BGR, un-premultiplied
			sub = acc[by0:by1, bx0:bx1]
			if pas == "bleed":
				wt = a[..., None]
			elif depth_priority:
				dep = _warp((_depth_px(rgba[..., 3] > 0) * mmpp).astype(np.float32), Aw, size)
				z = zbuf[by0:by1, bx0:bx1]
				k = np.where(np.isinf(z), 1.0, np.clip(0.5 + (dep - z) / (2 * s_mm), 0.0, 1.0))
				wt = (a * k)[..., None]
				zbuf[by0:by1, bx0:bx1] = np.where(a * k >= 0.5, dep, z)
			else:
				wt = a[..., None]
			acc[by0:by1, bx0:bx1] = col * wt + sub * (1.0 - wt)
		img = np.clip(acc + 0.5, 0, 255).astype(np.uint8)
	if "missing_border" in layers:
		for l in range(l0, l1 + 1):
			for c in range(c0, c1 + 1):
				if prof.is_border(l, c) and project.board[(l, c)]["estado"] == "vazia":
					x0, y0, x1, y1 = cell_box(l, c)
					cv2.rectangle(img, (x0 + lw, y0 + lw), (x1 - lw, y1 - lw), (0, 0, 255), 2 * lw)
	if "grid" in layers:
		for c in range(c0, c1 + 2):
			x = int(round((c - 1) * w_mm * ppm - ox))
			cv2.line(img, (x, 0), (x, H - 1), (90, 90, 90), 1)
		for l in range(l0, l1 + 2):
			y = int(round((l - 1) * h_mm * ppm - oy))
			cv2.line(img, (0, y), (W - 1, y), (90, 90, 90), 1)
	return img


def compose_zone_vs_art(project, region, dpi: float = 300, *, placements: Optional[dict] = None,
						layers=("art", "pieces"), clean: bool = True, depth_priority: bool = True,
						bleed_mm: float = BLEED_MM, board_shadow: Optional[bool] = None) -> np.ndarray:
	"""Side by side at ``dpi`` (300 = 1 scan px per screen px): the render of ``region`` | the art upsampled."""
	ppc = float(project.profile.cell_mm["w"]) / (25.4 / float(dpi))
	a = compose_board(project, ppc, region=region, placements=placements, layers=layers, clean=clean,
					  depth_priority=depth_priority, bleed_mm=bleed_mm, board_shadow=board_shadow)
	b = compose_board(project, ppc, region=region, layers=("art",), art_alpha=1.0)
	sep = np.full((a.shape[0], 8, 3), 255, np.uint8)
	return np.hstack([a, sep, b])


# ---------------------------------------------------------------- rebuild of the bulky assets
REBUILD_IOU_MIN = 0.6           # rebuild: stored bbox vs new bbox of the same index_in_scan below this -> order changed, sheet aborted
_STATIC_CMP = ("bbox", "cls", "chords_mm", "area_mm2")   # a piece whose silhouette changed (piece_resegmented)


def _bbox_iou(a, b) -> float:
	"""IoU of two ``(x, y, w, h)`` boxes."""
	ax, ay, aw, ah = (float(v) for v in a)
	bx, by, bw, bh = (float(v) for v in b)
	ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
	iy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
	inter = ix * iy
	union = aw * ah + bw * bh - inter
	return inter / union if union > 0 else 0.0


def _jsonable(v):
	return json.loads(json.dumps(v))


def _drop_stale_caches(project, sid: str, pids: list) -> None:
	"""Display caches that depend on a piece's crop/contour (all regenerated on demand)."""
	import glob
	for pid in pids:
		fp = project.p("render", "clean", f"{pid}.png")
		if os.path.exists(fp):
			os.remove(fp)
	for pat in (project.p("render", "sheets", f"{sid}_*.jpg"), project.p("render", "gui", "sheets", f"{sid}_*.jpg"),
				project.p("render", "gui", "board_*.jpg"), project.p("render", "gui", "board_*.json")):
		for fp in glob.glob(pat):
			os.remove(fp)
	if os.path.exists(project.p("render", "placements.json")):
		d = load_placements(project)
		if any(pid in d.get("placements", {}) for pid in pids):
			for pid in pids:
				d["placements"].pop(pid, None)
			save_placements(project, d)


def _manual_pending(project, sid: str, pcs: list, manual: dict, old: dict) -> bool:
	"""True if some manual override of the sheet is not applied yet: the stored npz contour differs
	from the polygon's rasterised contour (:func:`src.overrides.rasterize_polygon`), the piece lacks
	``flags.manual_override`` or carries another note."""
	try:
		W, H = OV.scan_size(project, sid)
	except FileNotFoundError:
		return True                         # the caller reports the missing scan
	for q in pcs:
		ov = manual.get(q.id)
		if ov is None:
			continue
		oc = old.get(f"{q.id}__contour_px")
		_, _, cnt = OV.rasterize_polygon(ov["contour_px"], W, H)
		if oc is None or oc.shape != cnt.shape or not np.array_equal(oc, cnt):
			return True
		fl = q.flags or {}
		if not fl.get(OV.MANUAL_FLAG) or (fl.get(OV.MANUAL_NOTE_FLAG) or "") != (ov.get("nota") or ""):
			return True
	return False


def rebuild_piece(project, piece: str, *, progress=None) -> dict:
	"""Apply the manual contour override of ``piece`` (:mod:`src.overrides`) without re-segmenting its
	sheet: the same path as :func:`rebuild_assets` (``scans=[scan]``, no ``clean`` / ``register``), which
	only segments when the sheet's npz or a non-manual crop is missing. Other pending overrides of the
	same sheet are applied too. Returns ``{piece, scan_id, changed: [record of this piece], all_changed,
	errors}`` or ``{'error'}`` when the piece has no override."""
	p = project.piece(piece)
	if not OV.has_override(project, piece):
		return {"error": f"{piece} não tem contorno manual em {OV.OVERRIDES_FILE}"}
	out = rebuild_assets(project, progress=progress, scans=[p.scan_id], clean=False, register=False)
	return {"piece": piece, "scan_id": p.scan_id, "changed": [c for c in out["changed"] if c["piece"] == piece],
			"all_changed": out["changed"], "errors": out["errors"], "overlays": out["overlays"]}


def rebuild_assets(project, *, progress=print, scans=None, clean: bool = True, register: bool = True,
				   force_scans=None, motivo: str = "recover_bays", segment=None, dry_run: bool = False,
				   refresh_crops=None) -> dict:
	"""Regenerate ``pieces/S####.npz`` and ``crops/P####.png`` from the scans (missing ones, or ``force_scans``).

	For each scan of ``project.model.scans`` (or only ``scans``) with a missing npz or crop, and for
	every scan id in ``force_scans`` (re-segmented even when its assets exist): the same
	segmentation as :func:`src.ingest.ingest_scan` (``segment_scan(normalize_rotation=False)``,
	or ``segment`` (tests), fragments < ``MIN_PIECE_MM2`` dropped; legacy pages go through
	``ingest_scan`` too, so the order is the same). The scan file must keep its ``sha256``.
	Piece k of the project is matched by ``index_in_scan``; the sheet is aborted with a message
	(nothing written) if the number of pieces changed or any matched bbox has IoU <
	:data:`REBUILD_IOU_MIN` with the stored one (the order changed).

	A piece whose silhouette changed (``bbox``, ``cls``, chords or area differ from the log)
	gets an event ``piece_resegmented`` (:meth:`src.state.Project.resegment_piece`, with
	``motivo``) carrying its new static fields (``flags`` = the stored non-segmentation keys +
	:func:`src.ingest.seg_flags`, ``mean_lab`` of the new crop), so ``scans/S####.json`` stays a
	faithful view after :meth:`~src.state.Project.save`. Only pieces whose contour changed (or
	whose crop is missing) get new npz arrays and crop; the others keep theirs bit for bit. For
	those pieces the display caches (``render/clean``, the scan's sheets, the GUI board raster,
	their ``placements.json`` entries) are dropped. The sheet ``overlays/S####.jpg`` is rewritten
	when missing or when a contour changed. ``dry_run`` = report only, nothing written.
	``refresh_crops`` (piece ids): crops rewritten as if missing (a crop of another size than its bbox,
	:func:`stale_assets`), even when the contour is unchanged.

	Manual overrides (:func:`src.overrides.latest_overrides`): for a piece with one, the drawn polygon
	replaces the segmented contour (npz arrays, crop cut from the scan by the polygon, bbox of the
	polygon padded like ``segment_scan``), its flags become :func:`src.overrides.manual_flags`
	(``manual_override = true``, ``manual_nota``) and its event carries ``motivo="manual"`` and the
	note, whatever ``motivo`` is; the bbox IoU check skips it. A sheet whose assets are all present
	and not forced is still processed, WITHOUT segmentation, when one of its overrides is not applied
	yet (:func:`rebuild_piece`). Then
	:func:`clean_all` and :func:`register_all` (``clean`` / ``register``; skipped on errors or
	``dry_run``).

	Returns ``{scans: {sid: {n, written, changed, seconds}}, changed: [{piece, scan_id, bbox_old,
	bbox_new, cls_old, cls_new, chords_old, chords_new, area_old, area_new, flags_new}],
	overlays: [paths], errors: [...]}``.
	"""
	from PIL import Image
	from src.ingest import MIN_PIECE_MM2, SEG_FLAG_KEYS, _mean_lab, seg_flags
	from src.segmentation import piece_to_rgba
	from src.shape import analyse
	from src.state import file_sha256
	if segment is None:
		from src.segmentation import segment_scan as segment
	out = {"scans": {}, "changed": [], "errors": [], "overlays": []}
	force = set(force_scans or ())
	unknown = sorted(force - set(project.model.scans))
	if unknown:
		out["errors"].append(f"folhas desconhecidas em force_scans: {unknown}")
		return out
	if not dry_run:
		os.makedirs(project.p("pieces"), exist_ok=True)
		os.makedirs(project.p("crops"), exist_ok=True)
	redraw, n_events = set(), 0

	def _err(msg):
		out["errors"].append(msg)
		if progress:
			progress("ERRO " + msg)

	manual_all = OV.latest_overrides(project)
	for sid, scan in sorted(project.model.scans.items()):
		if scans is not None and sid not in scans and sid not in force:
			continue
		pcs = sorted((p for p in project.pieces.values() if p.scan_id == sid), key=lambda q: q.index_in_scan)
		if not pcs:
			continue
		npz = project.p("pieces", f"{sid}.npz")
		missing_crop = {p.id for p in pcs if p.crop_path and not os.path.exists(project.p(p.crop_path))}
		missing_crop |= {p.id for p in pcs if p.crop_path and p.id in set(refresh_crops or ())}
		have_npz = os.path.exists(npz)
		manual = {q.id: manual_all[q.id] for q in pcs if q.id in manual_all}
		old = None
		if sid not in force and have_npz and not missing_crop:
			# nothing missing: only a manual contour not applied yet brings this sheet in (no segmentation)
			if not manual:
				continue
			with np.load(npz, allow_pickle=False) as z:
				old = {k: z[k] for k in z.files}
			if not _manual_pending(project, sid, pcs, manual, old):
				continue
		path = scan.get("file")
		ap = path if path and os.path.isabs(path) else os.path.join(REPO, path or "")
		if not path or not os.path.exists(ap):
			_err(f"{sid}: scan em falta ({path})")
			continue
		if scan.get("sha256") and file_sha256(ap) != scan["sha256"]:
			_err(f"{sid}: sha256 de {path} diferente do registado; o scan mudou, não regenero")
			continue
		t0 = time.time()
		with Image.open(ap) as im:
			photo = im.convert("RGB")
		dpi = float(scan.get("dpi") or project.profile.dpi)
		need_seg = sid in force or not have_npz or bool(missing_crop - set(manual))
		raw = None
		if need_seg:
			res = segment(photo, dpi=dpi, normalize_rotation=False)
			if "error" in res:
				_err(f"{sid}: segment_scan: {res['error']}")
				continue
			mmpp = float(res.get("mm_per_px") or 25.4 / dpi)
			kept = [p for p in res["pieces"] if float(p["area_px"]) * mmpp * mmpp >= MIN_PIECE_MM2]
			if len(kept) != len(pcs):
				_err(f"{sid}: a contagem mudou ({len(kept)} peças na nova segmentação, {len(pcs)} no projeto); nada escrito")
				continue
			raw = {int(p["index"]): p for p in kept}
			bad = []
			for q in pcs:
				r = raw.get(int(q.index_in_scan))
				if r is None:
					bad.append(f"{q.id}: índice {q.index_in_scan} não existe na nova segmentação")
				elif q.id not in manual and q.bbox is not None and _bbox_iou(r["bbox"], q.bbox) < REBUILD_IOU_MIN:
					# a manual piece's stored bbox is the drawn polygon's, not comparable with the segmentation
					bad.append(f"{q.id}: bbox {[int(v) for v in r['bbox']]} vs registada {q.bbox} "
							   f"(IoU {_bbox_iou(r['bbox'], q.bbox):.2f} < {REBUILD_IOU_MIN})")
			if bad:
				_err(f"{sid}: a ordem mudou ({len(bad)} peças; p. ex. {bad[0]}); nada escrito")
				continue
			med = float(np.median([float(p["area_px"]) * mmpp * mmpp for p in kept]))
		else:
			mmpp = _scan_mmpp(project, sid)
			med = float(np.median([float(q.area_mm2) for q in pcs if q.area_mm2] or [0.0]))
		rgb = np.asarray(photo) if manual else None
		if old is None:
			old = {}
			if have_npz:
				with np.load(npz, allow_pickle=False) as z:
					old = {k: z[k] for k in z.files}
		arrs = dict(old)
		written, changes, crops = [], [], {}
		for q in pcs:
			ov = manual.get(q.id)
			seg_r = raw.get(int(q.index_in_scan)) if raw is not None else None
			if ov is not None:
				r = OV.polygon_record(rgb, ov["contour_px"])     # the manual contour replaces the segmented one
			elif seg_r is None:
				continue                                          # no segmentation this time: piece untouched
			else:
				r = seg_r
			pre = f"{q.id}__"
			cnt = np.asarray(r["contour"]).reshape(-1, 2).astype(np.int32)
			oc = old.get(pre + "contour_px")
			same_cnt = oc is not None and oc.shape == cnt.shape and np.array_equal(oc, cnt)
			sh = analyse(cnt, mmpp)
			area = round(float(r["area_px"]) * mmpp * mmpp, 2)
			static = {"bbox": [int(v) for v in r["bbox"]], "cls": sh.cls, "n_flat": int(sh.n_flat),
					  "chords_mm": [round(float(x), 3) for x in sh.lens], "area_mm2": area, "shape_ok": bool(sh.ok)}
			diff = [k for k in _STATIC_CMP if _jsonable(getattr(q, k)) != _jsonable(static[k])]
			if ov is not None:
				flags = OV.manual_flags(q.flags, seg_r, area, med, ov.get("nota") or "")
				if _jsonable(flags) != _jsonable(q.flags or {}) or (not same_cnt and not diff):
					diff.append("flags" if _jsonable(flags) != _jsonable(q.flags or {}) else "contorno")
			elif (q.flags or {}).get(OV.MANUAL_FLAG) and "flags" not in diff:
				diff.append("flags")                          # reposição (src.overrides): the manual mark goes
			if not same_cnt:
				for k in [k for k in arrs if k.startswith(pre)]:
					del arrs[k]
				for k, v in sh.to_arrays().items():
					arrs[pre + k] = v
				arrs[pre + "contour_px"] = cnt
				written.append(q.id)
			rgba = None
			if q.crop_path and (not same_cnt or diff or q.id in missing_crop):
				rgba = np.ascontiguousarray(np.asarray(piece_to_rgba(r["image"], r["mask"])))
				crops[q.id] = rgba
			if diff:
				if ov is None:
					# back to the segmentation: its flags, and no manual-override marks (a reposição)
					flags = {k: v for k, v in (q.flags or {}).items()
							 if k not in SEG_FLAG_KEYS and k not in (OV.MANUAL_FLAG, OV.MANUAL_NOTE_FLAG)}
					flags.update(seg_flags(r, area, med))
				static["flags"] = flags
				if rgba is not None:
					static["mean_lab"] = _mean_lab(rgba)
				changes.append((q, static, {
					"piece": q.id, "scan_id": sid, "index_in_scan": int(q.index_in_scan),
					"motivo": "manual" if ov is not None else motivo, "nota": (ov or {}).get("nota") or "",
					"bbox_old": q.bbox, "bbox_new": static["bbox"], "cls_old": q.cls, "cls_new": static["cls"],
					"chords_old": list(q.chords_mm or []), "chords_new": static["chords_mm"],
					"area_old": q.area_mm2, "area_new": static["area_mm2"], "flags_new": flags, "diff": diff}))
		dt = time.time() - t0
		out["scans"][sid] = {"n": len(pcs), "written": len(written), "changed": len(changes), "seconds": round(dt, 1)}
		out["changed"].extend(rec for _, _, rec in changes)
		if progress:
			progress(f"{sid} ({os.path.basename(path)}): {len(pcs)} peças, {len(written)} contornos novos, "
					 f"{len(changes)} silhuetas mudadas ({', '.join(rec['piece'] for _, _, rec in changes) or '-'}) "
					 f"em {dt:.1f} s" + (" [dry-run]" if dry_run else ""))
		if dry_run:
			continue
		if written:
			np.savez_compressed(npz, **arrs)
		for pid, rgba in crops.items():
			Image.fromarray(rgba).save(project.p(project.piece(pid).crop_path))
		for pid in set(written) | set(crops):
			project._shape_cache.pop(pid, None)
		if have_npz and written:
			_drop_stale_caches(project, sid, sorted(set(written) | set(crops)))
			redraw.add(sid)
		for q, static, rec in changes:
			project.resegment_piece(q.id, motivo=rec["motivo"], nota=rec["nota"] or None, **static)
			n_events += 1
	if dry_run:
		return out
	if n_events:
		project.save()
	# numbered sheets (gitignored, shown by the GUI): regenerated from the npz when missing or redrawn
	for sid in sorted(project.model.scans):
		if scans is not None and sid not in scans and sid not in force:
			continue
		if not os.path.exists(project.p("pieces", f"{sid}.npz")):
			continue
		if sid not in redraw and os.path.exists(project.p("overlays", f"{sid}.jpg")):
			continue
		if not any(p.scan_id == sid for p in project.pieces.values()):
			continue
		try:
			from src.ingest import write_overlay
			out["overlays"].append(write_overlay(project, sid))
		except (ImportError, ValueError, OSError) as e:
			out["errors"].append(f"{sid}: overlay: {e}")
	if progress and out["overlays"]:
		progress(f"overlays regenerados: {len(out['overlays'])}")
	if out["errors"]:
		return out
	if clean:
		clean_all(project, progress=progress)
	if register:
		register_all(project, progress=progress)
	return out


STALE_AREA_FRAC = 0.005         # stale_assets: filled-contour area vs the log's area_mm2 (measured max 2.3e-5 on 958 pieces)
STALE_CHORD_MM = 0.05           # stale_assets: npz chords vs the log's chords_mm (measured max 0.000 on 958 pieces)


def _padded_bbox(c: np.ndarray, W: Optional[int], H: Optional[int], pad_ratio: float = OV.PAD_RATIO) -> list:
	"""Crop bbox of a scan contour the way ``segmentation._scan_record`` / :func:`src.overrides.rasterize_polygon`
	pad it (``pad_ratio`` x the long side, clipped to the scan when its size is known)."""
	ox, oy, ow, oh = cv2.boundingRect(np.asarray(c).reshape(-1, 1, 2).astype(np.int32))
	pad = int(round(pad_ratio * max(ow, oh)))
	x0, y0 = max(0, ox - pad), max(0, oy - pad)
	w, h = ow + 2 * pad, oh + 2 * pad
	if W is not None and H is not None:
		w, h = min(W - x0, w), min(H - y0, h)
	return [int(x0), int(y0), int(w), int(h)]


def stale_assets(project) -> dict:
	"""Pieces whose gitignored assets (``pieces/S####.npz``, ``crops/P####.png``) do not match the log.

	The log travels with git, the arrays and crops do not: a checkout that pulled a log with
	``piece_resegmented`` events keeps the old silhouettes (R0011/R0012, COMIDO.md). Per piece of every
	sheet of the log: ``npz em falta``; ``contorno em falta`` (no ``P####__contour_px``); ``área`` (filled
	contour x mmpp^2 vs ``area_mm2`` beyond :data:`STALE_AREA_FRAC`); ``bbox`` (contour bbox padded like the
	segmentation vs ``bbox``); ``recorte em falta`` / ``recorte`` (crop size != bbox w, h); ``forma`` (npz
	``cls`` or ``side_chord_mm`` vs ``cls`` / ``chords_mm`` beyond :data:`STALE_CHORD_MM`). Manual overrides
	are compared the same way (their npz contour is the rasterised polygon). Reads the disk only.

	Returns ``{sheets: {sid: {motivos: [...], pecas: [...]}}, pecas: {pid: [motivos]}, n_pecas, n_folhas}``.
	"""
	from PIL import Image
	out = {"sheets": {}, "pecas": {}}
	by_sheet = {}
	for p in project.pieces.values():
		by_sheet.setdefault(p.scan_id, []).append(p)
	for sid in sorted(by_sheet):
		pcs = sorted(by_sheet[sid], key=lambda q: q.id)
		bad = {}
		npz = project.p("pieces", f"{sid}.npz")
		try:
			W, H = OV.scan_size(project, sid)
		except (FileNotFoundError, OSError, KeyError, ValueError):
			W = H = None
		mmpp = _scan_mmpp(project, sid)
		if not os.path.exists(npz):
			bad = {q.id: ["npz em falta"] for q in pcs}
		else:
			with np.load(npz, allow_pickle=False) as z:
				keys = set(z.files)
				for q in pcs:
					why = []
					pre = f"{q.id}__"
					if pre + "contour_px" not in keys:
						why.append("contorno em falta")
					else:
						c = np.asarray(z[pre + "contour_px"]).reshape(-1, 2).astype(np.int32)
						bb = _padded_bbox(c, W, H)
						if q.bbox is not None and bb != [int(v) for v in q.bbox]:
							why.append("bbox")
						m = np.zeros((bb[3], bb[2]), np.uint8)
						cv2.drawContours(m, [(c - np.array(bb[:2], np.int32)).reshape(-1, 1, 2)], -1, 1, thickness=cv2.FILLED)
						if q.area_mm2 and abs(float(m.sum()) * mmpp * mmpp - float(q.area_mm2)) > STALE_AREA_FRAC * float(q.area_mm2):
							why.append("área")
						if pre + "side_chord_mm" in keys:
							ch = np.asarray(z[pre + "side_chord_mm"], float).reshape(-1)
							lc = np.asarray(q.chords_mm or [], float).reshape(-1)
							cls_npz = str(z[pre + "cls"]) if pre + "cls" in keys else ""
							if (cls_npz != (q.cls or "") or len(ch) != len(lc)
									or (len(ch) and float(np.abs(ch - lc).max()) > STALE_CHORD_MM)):
								why.append("forma")
					if q.crop_path:
						fp = project.p(q.crop_path)
						if not os.path.exists(fp):
							why.append("recorte em falta")
						elif q.bbox is not None:
							with Image.open(fp) as im:
								if im.size != (int(q.bbox[2]), int(q.bbox[3])):
									why.append("recorte")
					if why:
						bad[q.id] = why
		if bad:
			out["sheets"][sid] = {"motivos": sorted({w for v in bad.values() for w in v}), "pecas": sorted(bad)}
			out["pecas"].update(bad)
	out["n_pecas"] = len(out["pecas"])
	out["n_folhas"] = len(out["sheets"])
	return out


def rebuild_stale(project, *, progress=print, dry_run: bool = False, segment=None) -> dict:
	"""Re-segment only the sheets listed by :func:`stale_assets` (:func:`rebuild_assets` with ``force_scans``,
	``refresh_crops`` = the pieces with a stale crop, no ``clean`` / ``register``) and check again.

	With the code that wrote the log the new silhouettes are the log's: ``eventos`` = 0. Events
	(``piece_resegmented``, motivo ``stale``) mean this checkout segments differently from the one that
	wrote the log; they are named in ``aviso``. Returns ``{antes, folhas, pecas, eventos, changed, errors,
	depois, aviso}`` (``depois`` = :func:`stale_assets` after the rebuild; None with ``dry_run``)."""
	st = stale_assets(project)
	out = {"antes": st, "folhas": sorted(st["sheets"]), "pecas": sorted(st["pecas"]), "eventos": 0, "changed": [],
		   "errors": [], "depois": None, "aviso": None}
	if not st["sheets"]:
		if progress:
			progress("ativos coerentes com o log: nada a refazer")
		return out
	if progress:
		progress(f"{st['n_pecas']} peças desatualizadas em {st['n_folhas']} folhas: {', '.join(out['folhas'])}")
	refresh = [pid for pid, why in st["pecas"].items() if any(w.startswith("recorte") for w in why)]
	r = rebuild_assets(project, progress=progress, scans=out["folhas"], force_scans=out["folhas"], clean=False,
					   register=False, motivo="stale", segment=segment, dry_run=dry_run, refresh_crops=refresh)
	out["changed"], out["errors"] = list(r.get("changed") or []), list(r.get("errors") or [])
	out["eventos"] = 0 if dry_run else len(out["changed"])
	if out["changed"]:
		out["aviso"] = (f"{len(r['changed'])} silhuetas diferentes do log ({', '.join(c['piece'] for c in r['changed'])}): "
						"este código segmenta de outro modo do que o que escreveu o log"
						+ ("" if dry_run else "; registadas como piece_resegmented (motivo stale)"))
		if progress:
			progress("AVISO " + out["aviso"])
	if not dry_run:
		out["depois"] = stale_assets(project)
	return out


# ---------------------------------------------------------------- CLI
def _imwrite(path: str, img: np.ndarray, quality: int = 90) -> None:
	os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
	ext = os.path.splitext(path)[1].lower() or ".jpg"
	params = [cv2.IMWRITE_JPEG_QUALITY, quality] if ext in (".jpg", ".jpeg") else []
	cv2.imencode(ext, img, params)[1].tofile(path)


def main(argv=None) -> int:
	ap = argparse.ArgumentParser(prog="python -m src.render", description="Render do tabuleiro (registo fino, limpeza da franja, composição).")
	ap.add_argument("--project", default=os.path.join("projects", "alpes"))
	ap.add_argument("--rebuild", action="store_true", help="regenera pieces/*.npz e crops/ em falta a partir dos scans")
	ap.add_argument("--register", action="store_true", help="registo fino de todas as peças colocadas")
	ap.add_argument("--no-image", action="store_true", help="registo só pelos cantos (sem o passo de imagem)")
	ap.add_argument("--force", action="store_true", help="ignora a cache (placements.json, render/clean)")
	ap.add_argument("--clean", action="store_true", help="limpa a franja verde dos recortes (render/clean/)")
	ap.add_argument("--light-band", type=float, default=LIGHT_BAND_MM, metavar="MM",
					help=f"banda das peças claras (céu; p5 do interior > {LIGHT_PIECE_P5_MIN}), <= 1.2 mm; "
						 f"por omissão {LIGHT_BAND_MM}; 0 = 0,7 mm em todas")
	ap.add_argument("--board", default=None, help="imagem do tabuleiro inteiro")
	ap.add_argument("--ppc", type=float, default=60.0, help="px por célula do --board")
	ap.add_argument("--zone", type=int, nargs=4, default=None, metavar=("L0", "C0", "L1", "C1"))
	ap.add_argument("--dpi", type=float, default=300.0)
	ap.add_argument("--out", default=None, help="saída do --zone (render | arte)")
	args = ap.parse_args(argv)
	from src.state import Project, StateError
	try:
		pr = Project.open(args.project)
	except (StateError, ValueError) as e:
		print(f"erro: {e}")
		return 1
	if args.rebuild:
		r = rebuild_assets(pr, clean=False, register=False)
		if r["errors"]:
			return 1
	if args.clean or args.rebuild:
		clean_all(pr, force=args.force, light_band_mm=args.light_band)
	if args.register or args.rebuild:
		register_all(pr, image=not args.no_image, force=args.force)
	if args.board:
		img = compose_board(pr, args.ppc)
		_imwrite(args.board, img)
		print(f"tabuleiro: {args.board} ({img.shape[1]}x{img.shape[0]})")
	if args.zone:
		out = args.out or f"zona_{'_'.join(map(str, args.zone))}.jpg"
		img = compose_zone_vs_art(pr, tuple(args.zone), args.dpi)
		_imwrite(out, img)
		print(f"zona: {out} ({img.shape[1]}x{img.shape[0]})")
	return 0


if __name__ == "__main__":
	sys.exit(main())
