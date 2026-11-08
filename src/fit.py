"""Hole mould (M11, first half of ``src/fit.py``): rank the loose pieces for an EMPTY cell from the free
sides of its mounted neighbours. A **ranking**, never an autonomous proposal (E-fit, docs/diagnostico/fit/
RESULTADOS.md §13 and §15.6; criteria fixed before the code in M11_CRITERIOS.md).

Pipeline of :func:`rank_hole` for one hole (cell with m >= 1 mounted neighbours):

1. every neighbour contributes the side that faces the hole (:class:`HoleSide`: kind, chord, profile,
   Lab strip of the inner band); the candidate pool is the loose pieces (:class:`FitItem`), each with its
   4 sides and 4 strips, optionally after the same silhouette erosion (:func:`eroded_sides`);
2. side cost (vectorised, :func:`side_costs`): ``rms / RMS_SCALE + dE / DE_SCALE + penalty`` with ``rms``
   the profile RMS of :func:`src.shape.side_complement`, ``dE`` the median Lab distance of the mirrored
   strips (>= ``MIN_VALID`` points, else the side is infinite, as in the E-fit), and the **soft chord
   filter**: 0 within the per-type tolerance, ``SOFT_SLOPE_PER_MM`` per mm above it, infinite above
   ``chord_cut`` tolerances. T<->B is hard (F with nothing, T-T / B-B impossible);
3. joint cost (:func:`joint_costs`): ``J_r(Z) = mean_k cost(side_k, side (sigma * dir_k + r) mod 4 of Z)``,
   ``J = min_r J_r`` (the rotation of the loose piece is unknown and must be the same for every
   neighbour); the F sides required by the cell (border) are a hard rule on the rotation
   (``f_rule``); the side map has a single orientation ``sigma`` (:func:`side_orientation`), asserted;
4. ranking by ``J``, ``d1 / d2`` and margin ``d2 / d1``, **absolute rejection** (``d1 <= t_abs``,
   calibrated on holes with the right piece, out of the validation sample) and the fixed 3-level
   confidence of :func:`confidence` (``alta`` / ``media`` / ``sem`` reliable candidate; one neighbour is
   never ``alta``);
5. :func:`assign` (joint assignment holes x pieces, greedy by ``J``: each piece in one hole, each hole
   with one piece) when several holes are ranked together (:func:`rank_all`).

Nothing puzzle-specific in the code: the border sides come from the profile. The pure part (top of the
module) takes arrays and dataclasses; the project glue (``hole_queries``, ``pool_items``, ``rank_all``,
``report``) and the CLI ``python -m src.fit`` are below it. Confirmations / rejections are logged by
:mod:`src.confirm` (events ``hole_confirmed`` / ``hole_rejected`` with rank, cost, margin, confidence and
``FIT_VERSION``): they are the ground truth that :func:`report` accumulates.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

from src.locate import body_center_mm, wrap_deg
from src.shape import (N_SIDE, Shape, Side, analyse, corner_dist, f_adjacent, _neg_inv, _smooth_closed)

__all__ = [
	"FIT_VERSION", "DIRS", "DIR_IDX", "OPP", "STEP", "NORMAL_DEG", "ZONES", "CONFIDENCES",
	"RMS_SCALE", "DE_SCALE", "SOFT_SLOPE_PER_MM", "N_STRIP", "BAND_MM", "MIN_VALID",
	"HoleSide", "HoleQuery", "FitItem", "FitCalibration", "PoolArrays",
	"lab_of", "eroded_sides", "side_strips", "side_orientation", "board_dirs", "zone_of", "wilson",
	"pool_arrays", "side_costs", "joint_costs", "theta_for", "confidence", "rank_hole", "assign",
	"calibration", "piece_strips", "hole_queries", "pool_items", "board_sigma", "rank_all", "report", "main",
	"ALTA_JANELA", "ALTA_MAX_FALHAS", "alta_counter", "alta_suggestions",
]

FIT_VERSION = "m11-1"
DIRS = ("N", "E", "S", "W")
DIR_IDX = {d: i for i, d in enumerate(DIRS)}
OPP = {"N": "S", "S": "N", "E": "W", "W": "E"}
STEP = {"N": (-1, 0), "E": (0, 1), "S": (1, 0), "W": (0, -1)}
NORMAL_DEG = {"N": -90.0, "E": 0.0, "S": 90.0, "W": 180.0}   # outward normal of a cell side, image frame (y down)
SIDE_TOL_DEG = 25.0            # a side faces a board direction if its outward normal is within this of it
ZONES = (("céu", 1, 14), ("montanha/floresta", 15, 27), ("vale/aldeia", 28, 40), ("relva", 41, 47))  # fixed row bands (GT.md)
CONFIDENCES = ("alta", "media", "sem")
# «Vai buscar» pause rule (M11_CRITERIOS §8, decided by Tiago 2026-11-08): the last ALTA_JANELA ``alta`` rank-1 decisions
# after the last ``holes_alta_resumed``; >= ALTA_MAX_FALHAS rejections among them pause the suggestions.
ALTA_JANELA = 20
ALTA_MAX_FALHAS = 3
PROGRESS_EVERY_N = 20          # rank_all(progress=): a line every this many strips computed ...
PROGRESS_EVERY_S = 5.0         # ... or every this many seconds

# E5 constants (GT.md §5, RESULTADOS.md §11): fixed, never tuned
RMS_SCALE = 1.1                # mm: median profile RMS of true adjacencies (LEGADO.md)
DE_SCALE = 10.0                # dE of "same piece" (src/legacy.py)
SOFT_SLOPE_PER_MM = 1.0        # soft chord filter: cost units per mm above the per-type tolerance (fixed, M11_CRITERIOS §3)
N_STRIP = 12                   # points along the side arc
T0, T1 = 0.08, 0.92
BAND_MM = (1.0, 2.5)           # depth of the inner band from the silhouette
HALF_WIN = 1.0 / 24.0          # half-width of the window (fraction of the arc)
MIN_VALID = 6                  # strip points needed on both sides for a finite dE
ERODE_SMOOTH_SIGMA = 3.0       # contour smoothing (samples) for the normals of the erosion
MIN_D1 = 1e-9

CALIB_KEY = "buraco"           # block of profile.calibration written by the tuning step


# ================================================================ pure part
@dataclass
class HoleSide:
	"""One mounted neighbour's side facing the hole.

	piece_id: the neighbour. direction: where the neighbour is, seen from the hole (``'N'`` = the
	neighbour is above the hole). side: its :class:`src.shape.Side` facing the hole (already eroded when
	the calibration says so). f_adj: that side is F or adjacent to an F in the neighbour (chord tolerance
	2 mm). strip: ``(N_STRIP, 3)`` Lab strip of that side (NaN where missing) or None. scan_id: for the
	cross-scan colour note.
	"""

	piece_id: str
	direction: str
	side: Side
	f_adj: bool = False
	strip: Optional[np.ndarray] = None
	scan_id: Optional[str] = None


@dataclass
class HoleQuery:
	"""An empty cell and the sides of its mounted neighbours. ``f_required``: directions where the cell
	needs a flat side (puzzle border, from the profile)."""

	cell: tuple
	sides: list
	zone: Optional[str] = None
	f_required: tuple = ()

	@property
	def m(self) -> int:
		return len(self.sides)


@dataclass
class FitItem:
	"""A loose candidate: its 4 sides (eroded or not) and 4 strips ``(4, N_STRIP, 3)``."""

	id: str
	shape: Shape
	sides: list
	strips: Optional[np.ndarray] = None
	lote: Optional[int] = None
	n_no_lote: Optional[int] = None
	scan_id: Optional[str] = None


@dataclass
class FitCalibration:
	"""Parameters of the hole ranking. Only ``erosion_mm``, ``chord_cut`` and ``t_abs`` are tuned
	(M11_CRITERIOS §4); the rest are the fixed E-fit constants.

	chord_cut: multiple of the per-type chord tolerance above which a side is infinite (1.0 = the hard
	filter of the E-fit; None = never infinite by chord). t_abs: absolute rejection on the joint cost
	(None = off). calibrated: read from the profile (False = defaults, not calibrated).
	"""

	erosion_mm: float = 0.0
	chord_cut: Optional[float] = 1.0
	t_abs: Optional[float] = None
	margin_min: float = 1.5
	chord_normal_mm: float = 1.0
	chord_f_adj_mm: float = 2.0
	soft_slope: float = SOFT_SLOPE_PER_MM
	f_rule: bool = True
	calibrated: bool = False

	def to_dict(self) -> dict:
		return {"erosion_mm": self.erosion_mm, "chord_cut": self.chord_cut, "t_abs": self.t_abs,
				"margin_min": self.margin_min, "chord_normal_mm": self.chord_normal_mm,
				"chord_f_adj_mm": self.chord_f_adj_mm, "soft_slope": self.soft_slope, "f_rule": self.f_rule,
				"calibrated": self.calibrated, "fit_version": FIT_VERSION}

	@classmethod
	def from_profile(cls, profile) -> "FitCalibration":
		"""``calibration['buraco']`` of the profile (tuned values) over the chord / margin blocks."""
		cal = getattr(profile, "calibration", None) or {}
		ch = cal.get("chord") or {}
		b = cal.get(CALIB_KEY) or {}
		return cls(erosion_mm=float(b.get("erosion_mm", 0.0)),
				   chord_cut=(None if b.get("chord_cut", 1.0) is None else float(b.get("chord_cut", 1.0))),
				   t_abs=(None if b.get("t_abs") is None else float(b["t_abs"])),
				   margin_min=float(cal.get("margin_min", 1.5)),
				   chord_normal_mm=float(ch.get("normal_mm", 1.0)), chord_f_adj_mm=float(ch.get("f_adj_mm", 2.0)),
				   f_rule=bool(b.get("f_rule", True)), calibrated=bool(b))


def _fmt(x, nd: int = 2) -> str:
	if x is None or (isinstance(x, float) and not math.isfinite(x)):
		return "—"
	return f"{x:.{nd}f}".replace(".", ",")


def wilson(k: int, n: int, z: float = 1.96):
	"""Wilson 95 % interval of ``k / n`` (``(nan, nan)`` if n = 0)."""
	if n == 0:
		return (float("nan"), float("nan"))
	p = k / n
	d = 1 + z * z / n
	c = (p + z * z / (2 * n)) / d
	h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
	return (max(0.0, c - h), min(1.0, c + h))


def zone_of(cell) -> str:
	"""Fixed row band of a cell (only to slice reports; GT.md): céu / montanha-floresta / vale-aldeia / relva."""
	if cell is None:
		return "sem posição"
	for name, a, b in ZONES:
		if a <= int(cell[0]) <= b:
			return name
	return "?"


def lab_of(rgb: np.ndarray) -> np.ndarray:
	"""uint8 RGB -> float32 Lab (L* 0..100, a*/b* centred), the E-fit conversion (``fit_eval.lab_of``)."""
	lab = cv2.cvtColor(np.ascontiguousarray(rgb, np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
	lab[..., 0] *= 100.0 / 255.0
	lab[..., 1:] -= 128.0
	return lab


def _area(p: np.ndarray) -> float:
	return 0.5 * float(np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1]))


def eroded_sides(shape: Shape, d_mm: float):
	"""Sides of the silhouette eroded ``d_mm`` along the inward normal, aligned to the side indices of
	``shape`` (``fit_eval.shrink_sides``: the E-real offset of +0.48 mm, EREAL.md). None if the eroded
	contour has no 4 corners; ``d_mm <= 0`` returns the original sides."""
	if d_mm <= 0:
		return list(shape.sides)
	c = np.asarray(shape.c, float)
	cs = _smooth_closed(c, ERODE_SMOOTH_SIGMA)
	t = np.roll(cs, -1, 0) - np.roll(cs, 1, 0)
	t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)
	nrm = np.stack([t[:, 1], -t[:, 0]], 1)
	a0 = abs(_area(c))
	cand = c + d_mm * nrm
	if abs(_area(cand)) > a0:
		cand = c - d_mm * nrm
	sh2 = analyse(cand, 1.0)                    # contour already in mm
	if not sh2.ok:
		return None
	k = corner_dist(shape, sh2)[1]
	return [sh2.sides[(i + k) % 4] for i in range(4)]


def _depth_px(alpha: np.ndarray) -> np.ndarray:
	a = np.pad((alpha > 0).astype(np.uint8), 1)
	return cv2.distanceTransform(a, cv2.DIST_L2, 5)[1:-1, 1:-1]


def side_strips(rgba: np.ndarray, shape: Shape, mmpp: float, origin_px) -> np.ndarray:
	"""``(4, N_STRIP, 3)`` Lab of the inner band (``BAND_MM``) of each side, ``N_STRIP`` points along the
	arc from ``T0`` to ``T1`` (median of the pixels within ``HALF_WIN`` of each point); NaN where fewer
	than 5 pixels. ``rgba``: the display crop (RGB order, alpha), ``origin_px``: its top-left in the scan.
	Pure part of :func:`piece_strips` (``fit_eval.piece_strips``)."""
	out = np.full((4, N_STRIP, 3), np.nan, np.float32)
	if shape is None or not shape.ok or rgba is None:
		return out
	origin = np.asarray(origin_px, float)
	alpha = rgba[..., 3] > 0
	depth = _depth_px(alpha) * mmpp
	band = alpha & (depth >= BAND_MM[0]) & (depth <= BAND_MM[1])
	ys, xs = np.nonzero(band)
	if len(xs) == 0:
		return out
	lab = lab_of(rgba[..., :3])[ys, xs]
	cpx = shape.c / mmpp - origin
	n = len(cpx)
	P = np.stack([xs, ys], 1).astype(np.float32)
	near = np.empty(len(P), np.int32)
	sub = cpx[None, ::2, :].astype(np.float32)
	for s in range(0, len(P), 4000):
		d2 = ((P[s:s + 4000, None, :] - sub) ** 2).sum(-1)
		near[s:s + 4000] = np.argmin(d2, 1) * 2
	cor = list(shape.corners)
	for i in range(4):
		a, b = cor[i], cor[(i + 1) % 4]
		length = (b - a) % n
		if length <= 0:
			continue
		frac = ((near - a) % n) / float(length)
		inside = frac <= 1.0
		for k in range(N_STRIP):
			t = T0 + (T1 - T0) * k / (N_STRIP - 1)
			m = inside & (np.abs(frac - t) <= HALF_WIN)
			if m.sum() >= 5:
				out[i, k] = np.median(lab[m], 0)
	return out


def board_dirs(shape: Shape, theta_deg: float) -> Optional[dict]:
	"""``{'N': i, 'E': j, ...}``: the side index of ``shape`` facing each board direction when the piece
	is turned by ``theta_deg`` (image frame, y down); None unless the 4 sides map 1-to-1 within
	``SIDE_TOL_DEG`` (``tools/diagnostico/fit/gt.py``)."""
	if shape is None or not shape.ok or theta_deg is None:
		return None
	ctr = body_center_mm(shape)
	out = {}
	for i, s in enumerate(shape.sides):
		v = 0.5 * (np.asarray(s.p0_mm) + np.asarray(s.p1_mm)) - ctr
		a = float(np.degrees(np.arctan2(v[1], v[0]))) + float(theta_deg)
		d = min(DIRS, key=lambda k: abs(float(wrap_deg(a - NORMAL_DEG[k]))))
		if abs(float(wrap_deg(a - NORMAL_DEG[d]))) > SIDE_TOL_DEG or d in out:
			return None
		out[d] = i
	return out if len(out) == 4 else None


def side_orientation(dirs_by_piece: dict) -> dict:
	"""Orientation ``sigma`` of the side map: +1 if the side index grows N -> E -> S -> W, -1 if it
	decreases; **must be unanimous** over the given pieces (``{pid: board_dirs}``), else ``{'error'}``
	with the offenders (the invariant of M11_CRITERIOS §3: +1 in 603/603 placed pieces today)."""
	plus, minus, bad = [], [], []
	for pid, dr in dirs_by_piece.items():
		if not dr:
			continue
		k = (dr["E"] - dr["N"]) % 4
		(plus if k == 1 else minus if k == 3 else bad).append(pid)
	if bad:
		return {"error": f"mapa de lados não cíclico em {len(bad)} peça(s): {bad[:5]}", "n": len(plus) + len(minus) + len(bad)}
	if plus and minus:
		return {"error": f"orientação do mapa de lados não é única: +1 em {len(plus)}, -1 em {len(minus)} "
						 f"(ex. {minus[:3] if len(minus) <= len(plus) else plus[:3]})", "n_plus": len(plus), "n_minus": len(minus)}
	if not plus and not minus:
		return {"error": "sem peças colocadas com pose e 4 lados para fixar a orientação do mapa de lados", "n": 0}
	return {"sigma": 1 if plus else -1, "n": len(plus) + len(minus)}


@dataclass
class PoolArrays:
	"""Vectorised view of a candidate pool: per piece and side."""

	ids: list
	kind: np.ndarray        # (P, 4) '<U1'
	chord: np.ndarray       # (P, 4) mm
	negprof: np.ndarray     # (P, 4, N_SIDE, 2): _neg_inv(profile) (the mating side as the hole sees it)
	fadj: np.ndarray        # (P, 4) bool
	strips: np.ndarray      # (P, 4, N_STRIP, 3) Lab (NaN where missing)
	items: list = field(default_factory=list)


def pool_arrays(items: list) -> PoolArrays:
	P = len(items)
	kind = np.empty((P, 4), dtype="<U1")
	chord = np.zeros((P, 4))
	negprof = np.zeros((P, 4, N_SIDE, 2))
	fadj = np.zeros((P, 4), bool)
	strips = np.full((P, 4, N_STRIP, 3), np.nan, np.float32)
	for p, it in enumerate(items):
		fa = f_adjacent([s.kind for s in it.sides])
		for i, s in enumerate(it.sides):
			kind[p, i] = s.kind
			chord[p, i] = float(s.chord_mm)
			negprof[p, i] = _neg_inv(np.asarray(s.profile, float))
			fadj[p, i] = fa[i]
		if it.strips is not None:
			strips[p] = it.strips
	return PoolArrays([it.id for it in items], kind, chord, negprof, fadj, strips, list(items))


def side_costs(hs: HoleSide, pool: PoolArrays, calib: FitCalibration) -> dict:
	"""Cost of ``hs`` against every side of every candidate: ``(P, 4)`` arrays ``rms`` (mm), ``dl`` (mm),
	``dE``, ``pen`` (soft chord penalty), ``cost`` (inf where impossible: wrong kind, chord above the
	cut, no valid image)."""
	sa = hs.side
	prof = np.asarray(sa.profile, float)
	rms = np.sqrt(np.mean(np.sum((prof[None, None] - pool.negprof) ** 2, -1), -1)) * (float(sa.chord_mm) + pool.chord) / 2.0
	comp = ((pool.kind == "T") & (sa.kind == "B")) | ((pool.kind == "B") & (sa.kind == "T"))
	dl = np.abs(float(sa.chord_mm) - pool.chord)
	tol = np.where(pool.fadj | bool(hs.f_adj), calib.chord_f_adj_mm, calib.chord_normal_mm)
	pen = np.where(dl <= tol, 0.0, calib.soft_slope * (dl - tol))
	hard = np.zeros_like(comp) if calib.chord_cut is None else (dl > calib.chord_cut * tol)
	if hs.strip is None or np.isfinite(hs.strip).all(1).sum() < MIN_VALID:
		de = np.full(pool.chord.shape, np.nan)
	else:
		diff = np.linalg.norm(hs.strip[None, None] - pool.strips[:, :, ::-1], axis=-1)     # (P, 4, N_STRIP), mirrored
		de = _nanmedian_last(diff)
	cost = rms / RMS_SCALE + de / DE_SCALE + pen
	cost = np.where(comp & ~hard & np.isfinite(cost), cost, np.inf)
	return {"rms": rms, "dl": dl, "dE": de, "pen": pen, "cost": cost, "comp": comp, "hard": hard}


def _nanmedian_last(x: np.ndarray, min_valid: int = MIN_VALID) -> np.ndarray:
	"""Median over the last axis ignoring NaN (same values as ``np.nanmedian``), NaN where fewer than ``min_valid``
	finite entries; a sort with NaN pushed to +inf, much faster than ``nanmedian`` on (P, 4, 12) blocks."""
	fin = np.isfinite(x)
	v = fin.sum(-1)
	d = np.sort(np.where(fin, x, np.inf), axis=-1)
	lo = np.maximum((v - 1) // 2, 0)
	hi = np.maximum(v // 2, 0)
	a = np.take_along_axis(d, lo[..., None], -1)[..., 0]
	b = np.take_along_axis(d, hi[..., None], -1)[..., 0]
	med = 0.5 * (a + b)
	return np.where(v >= min_valid, med, np.nan)


def _f_mask(hole: HoleQuery, pool: PoolArrays, sigma: int) -> np.ndarray:
	"""``(4, P)`` True where rotation ``r`` of candidate ``p`` puts an F exactly on the required directions."""
	P = len(pool.ids)
	ok = np.ones((4, P), bool)
	req = set(hole.f_required)
	for r in range(4):
		for d in DIRS:
			j = (sigma * DIR_IDX[d] + r) % 4
			is_f = pool.kind[:, j] == "F"
			ok[r] &= is_f if d in req else ~is_f
	return ok


def joint_costs(hole: HoleQuery, pool: PoolArrays, calib: FitCalibration, sigma: int = 1):
	"""``J`` (P,), ``rot`` (P,), per-side cost dicts (list of m) for one hole against a pool.

	``J_r = mean_k C_k[:, (sigma * dir_k + r) % 4]`` and ``J = min_r J_r`` (RESULTADOS.md §11.3); with
	``calib.f_rule`` the rotations that violate the required F sides are infinite."""
	if sigma not in (1, -1):
		raise ValueError(f"sigma inválido {sigma!r}: a orientação do mapa de lados tem de ser +1 ou -1")
	per = [side_costs(hs, pool, calib) for hs in hole.sides]
	P = len(pool.ids)
	xs = np.array([(sigma * DIR_IDX[hs.direction]) % 4 for hs in hole.sides])
	best, arg = np.full(P, np.inf), np.zeros(P, int)
	fmask = _f_mask(hole, pool, sigma) if calib.f_rule else np.ones((4, P), bool)
	for r in range(4):
		Jr = np.mean(np.stack([per[k]["cost"][:, (xs[k] + r) % 4] for k in range(len(per))]), 0)
		Jr = np.where(fmask[r], Jr, np.inf)
		upd = Jr < best
		best, arg = np.where(upd, Jr, best), np.where(upd, r, arg)
	return best, arg, per, xs


def theta_for(hole: HoleQuery, item: FitItem, rot: int, sigma: int = 1) -> Optional[float]:
	"""Board pose (deg, image frame, as ``theta_deg`` of the log) of the candidate in rotation ``rot``:
	circular mean over the neighbours of ``NORMAL_DEG[dir_k] - angle(side (sigma*dir_k + rot) % 4)``."""
	sh = item.shape
	if sh is None or not sh.ok:
		return None
	ctr = body_center_mm(sh)
	z = 0j
	for hs in hole.sides:
		j = (sigma * DIR_IDX[hs.direction] + rot) % 4
		s = sh.sides[j]
		v = 0.5 * (np.asarray(s.p0_mm) + np.asarray(s.p1_mm)) - ctr
		a = float(np.degrees(np.arctan2(v[1], v[0])))
		z += np.exp(1j * np.radians(NORMAL_DEG[hs.direction] - a))
	if z == 0:
		return None
	return float(wrap_deg(np.degrees(np.angle(z))))


def confidence(m: int, d1, d2, calib: FitCalibration) -> str:
	"""Fixed rule (M11_CRITERIOS §3): ``alta`` iff m >= 2, d1 <= t_abs and d2/d1 >= margin_min;
	``media`` iff d1 <= t_abs and (m = 1 with margin >= margin_min, or m >= 2 with margin below);
	``sem`` otherwise (no finite d1, d1 > t_abs, no second finite candidate, or m = 1 with a low margin)."""
	if d1 is None or not np.isfinite(d1):
		return "sem"
	if calib.t_abs is not None and d1 > calib.t_abs:
		return "sem"
	if d2 is None or not np.isfinite(d2):
		return "sem"
	margin = d2 / max(d1, MIN_D1)
	if margin >= calib.margin_min:
		return "alta" if m >= 2 else "media"
	return "media" if m >= 2 else "sem"


def rank_hole(hole: HoleQuery, pool, *, calib: FitCalibration, sigma: int = 1, top: int = 3, exclude=()) -> dict:
	"""Rank the pool for one hole.

	Returns ``{'cell', 'm', 'n_pool', 'n_finite', 'd1', 'd2', 'margin', 'confidence', 'candidates':
	[{id, lote, n_no_lote, J, rot, theta_deg, per_side: [{direction, piece, rms, dl, dE, pen, cost}],
	rank}], 'ranking': [{id, J, rot}] (all finite, best first), 'reasons': [str], 'version', 'calib'}``
	or ``{'error': str}``. ``pool``: a list of :class:`FitItem` or a :class:`PoolArrays`. ``exclude``:
	piece ids never proposed for this cell (rejected pairs)."""
	if hole.m < 1:
		return {"error": f"célula {tuple(hole.cell)} sem vizinhas montadas"}
	if sigma not in (1, -1):
		return {"error": f"orientação do mapa de lados inválida: {sigma!r}"}
	pa = pool if isinstance(pool, PoolArrays) else pool_arrays(list(pool))
	if not pa.ids:
		return {"error": "pool vazio"}
	J, rot, per, xs = joint_costs(hole, pa, calib, sigma)
	ex = set(exclude or ())
	if ex:
		J = np.where(np.isin(np.array(pa.ids), list(ex)), np.inf, J)
	order = [int(i) for i in np.argsort(J, kind="stable") if np.isfinite(J[i])]
	d1 = float(J[order[0]]) if order else None
	d2 = float(J[order[1]]) if len(order) > 1 else None
	margin = (d2 / max(d1, MIN_D1)) if (d1 is not None and d2 is not None) else None
	conf = confidence(hole.m, d1, d2, calib)
	cands = []
	for rk, i in enumerate(order[:top], start=1):
		it = pa.items[i] if pa.items else None
		r = int(rot[i])
		ps = []
		for k, hs in enumerate(hole.sides):
			j = (xs[k] + r) % 4
			c = per[k]
			ps.append({"direction": hs.direction, "piece": hs.piece_id, "side": int(j),
					   "rms": float(c["rms"][i, j]), "dl": float(c["dl"][i, j]),
					   "dE": (None if not np.isfinite(c["dE"][i, j]) else float(c["dE"][i, j])),
					   "pen": float(c["pen"][i, j]), "cost": float(c["cost"][i, j])})
		cands.append({"id": pa.ids[i], "lote": getattr(it, "lote", None), "n_no_lote": getattr(it, "n_no_lote", None),
					  "scan_id": getattr(it, "scan_id", None), "J": float(J[i]), "rot": r,
					  "theta_deg": (theta_for(hole, it, r, sigma) if it is not None else None), "per_side": ps, "rank": rk})
	reasons = [f"{hole.m} vizinha(s): " + ", ".join(f"{hs.direction} {hs.piece_id}" for hs in hole.sides)
			   + f"; {len(pa.ids)} candidatas, {len(order)} com custo finito"
			   + (f", {len(ex)} excluídas (rejeitadas)" if ex else "")]
	if d1 is None:
		reasons.append("nenhuma candidata passa tipo / cordas / lados F / imagem")
	else:
		reasons.append(f"melhor {pa.ids[order[0]]}: custo {_fmt(d1)}" + (f", margem {_fmt(margin)} para a 2.ª" if margin is not None else ", sem 2.ª candidata finita (margem indefinida)"))
		if calib.t_abs is not None:
			reasons.append(f"custo {'<=' if d1 <= calib.t_abs else '>'} limiar absoluto {_fmt(calib.t_abs)}" + ("" if d1 <= calib.t_abs else ": rejeitada"))
		else:
			reasons.append("sem limiar absoluto calibrado: a rejeição só pela margem")
	if hole.m == 1:
		reasons.append("só uma vizinha: confiança baixa (nunca «alta»)")
	reasons.append({"alta": "confiança alta", "media": "confiança média", "sem": "sem candidata fiável"}[conf]
				   + (f" (margem {_fmt(margin)} {'>=' if margin is not None and margin >= calib.margin_min else '<'} {_fmt(calib.margin_min, 1)})"
					  if margin is not None else ""))
	if not calib.calibrated:
		reasons.append("parâmetros por calibrar (valores por omissão)")
	return {"cell": tuple(hole.cell), "m": hole.m, "zone": hole.zone, "n_pool": len(pa.ids), "n_finite": len(order),
			"sides": [{"direction": hs.direction, "piece": hs.piece_id, "kind": hs.side.kind, "scan_id": hs.scan_id} for hs in hole.sides],
			"f_required": list(hole.f_required),
			"d1": d1, "d2": d2, "margin": margin, "confidence": conf, "candidates": cands,
			"ranking": [{"id": pa.ids[i], "J": float(J[i]), "rot": int(rot[i])} for i in order],
			"reasons": reasons, "version": FIT_VERSION, "calib": calib.to_dict()}


def assign(results: list) -> dict:
	"""Joint assignment holes x pieces over several :func:`rank_hole` results: greedy by ``J`` over every
	finite (hole, piece) pair (ties broken towards the hole with more neighbours, then hole order, then piece
	id); each piece ends in one hole and each hole with one piece. Annotates each
	result with ``assigned`` (piece id or None) and, on its candidates, ``melhor_para`` = the cell that
	took that piece when it is not this one. Returns ``{cell: piece}``."""
	pairs = []
	for h, r in enumerate(results):
		if "error" in r:
			continue
		for e in r.get("ranking", []):
			pairs.append((round(float(e["J"]), 6), -int(r.get("m", 0)), h, e["id"]))     # ties (to 1e-6): more neighbours first
	pairs.sort()
	hole_of, piece_of = {}, {}
	for J, _negm, h, pid in pairs:
		if h in hole_of or pid in piece_of:
			continue
		hole_of[h], piece_of[pid] = pid, h
	out = {}
	for h, r in enumerate(results):
		if "error" in r:
			continue
		r["assigned"] = hole_of.get(h)
		if r["assigned"] is not None:
			out[tuple(r["cell"])] = r["assigned"]
		for c in r.get("candidates", []):
			other = piece_of.get(c["id"])
			c["melhor_para"] = (None if other is None or other == h else tuple(results[other]["cell"]))
	return out


# ================================================================ project glue (I/O)
def calibration(project) -> FitCalibration:
	return FitCalibration.from_profile(project.profile)


def piece_strips(project, pid: str) -> np.ndarray:
	"""``(4, N_STRIP, 3)`` strips of a piece of the project from its display crop (``fit_eval.piece_strips``)."""
	from src import render
	sh = project.shape(pid)
	if sh is None or not sh.ok:
		return np.full((4, N_STRIP, 3), np.nan, np.float32)
	rgba = render.piece_rgba_for_display(project, pid)
	if rgba is None:
		return np.full((4, N_STRIP, 3), np.nan, np.float32)
	p = project.piece(pid)
	return side_strips(rgba, sh, render._scan_mmpp(project, p.scan_id), np.asarray(p.bbox[:2], float))


class _Cache:
	"""Strips (disk, ``render/fit/strips.npz``, keyed by piece id + bbox) and eroded sides (memory)."""

	def __init__(self, project, calib: FitCalibration):
		self.pr, self.calib = project, calib
		self.path = project.p(os.path.join("render", "fit", "strips.npz"))
		self.strips, self.sides, self.shapes, self.dirty = {}, {}, {}, False
		self.on_compute = None        # callback(pid) each time a strip is computed (progress of rank_all)
		self.n_loaded = 0
		if os.path.exists(self.path):
			try:
				z = np.load(self.path, allow_pickle=False)
				for k in z.files:
					if k.startswith("bbox__"):
						continue
					bb = z[f"bbox__{k}"] if f"bbox__{k}" in z.files else None
					p = project.pieces.get(k)
					if p is not None and bb is not None and list(bb) == list(p.bbox):
						self.strips[k] = z[k]
				self.n_loaded = len(self.strips)
			except (OSError, ValueError):
				self.strips = {}

	def rebind(self, project) -> "_Cache":
		"""Point the cache at a reopened project object: entries of pieces whose bbox changed (re-segmented) or that
		disappeared are dropped; the rest (strips, eroded sides, shapes) is kept."""
		old = self.pr
		self.pr = project
		for pid in list(set(self.strips) | set(self.sides) | set(self.shapes)):
			p, q = project.pieces.get(pid), old.pieces.get(pid)
			if p is None or q is None or list(p.bbox) != list(q.bbox):
				self.strips.pop(pid, None)
				self.sides.pop(pid, None)
				self.shapes.pop(pid, None)
		return self

	def shape(self, pid):
		if pid not in self.shapes:
			self.shapes[pid] = self.pr.shape(pid)
		return self.shapes[pid]

	def strip(self, pid):
		if pid not in self.strips:
			self.strips[pid] = piece_strips(self.pr, pid)
			self.dirty = True
			if self.on_compute is not None:
				self.on_compute(pid)
		return self.strips[pid]

	def strips_todo(self, cells=None, lote=None) -> list:
		"""Pieces whose strips :func:`rank_all` will compute (not yet in the cache): the placed pieces that touch an
		empty cell (the neighbours of the holes; ``cells`` limits them) and the loose pool. A cheap upper bound for
		the progress line, not the ranking itself."""
		pr = self.pr
		todo = set()
		cell_set = None if cells is None else {tuple(c) for c in cells}
		for pid, p in pr.pieces.items():
			if p.estado != "colocada" or p.celula is None or pid in self.strips:
				continue
			for n in pr.board.neighbours(tuple(p.celula)):
				if not pr.board.occupied(n) and (cell_set is None or tuple(n) in cell_set):
					todo.add(pid)
					break
		for p in pr.loose_pieces(lote):
			if p.id not in self.strips:
				todo.add(p.id)
		return sorted(todo)

	def eroded(self, pid):
		if pid not in self.sides:
			sh = self.shape(pid)
			self.sides[pid] = None if sh is None or not sh.ok else (eroded_sides(sh, self.calib.erosion_mm) or list(sh.sides))
		return self.sides[pid]

	def save(self):
		if not self.dirty:
			return
		os.makedirs(os.path.dirname(self.path), exist_ok=True)
		arrs = {}
		for k, v in self.strips.items():
			p = self.pr.pieces.get(k)
			if p is None:
				continue
			arrs[k] = v
			arrs[f"bbox__{k}"] = np.asarray(p.bbox, int)
		np.savez_compressed(self.path, **arrs)
		self.dirty = False


def _placed_dirs(project, cache: _Cache, dcache: dict):
	"""``{pid: board_dirs}`` of the placed pieces with shape and pose (None when either is missing)."""
	from src import render
	rc = {}
	for pid, p in project.pieces.items():
		if p.estado != "colocada" or p.celula is None:
			continue
		if pid not in dcache:
			sh = cache.shape(pid)
			th = render.initial_theta(project, pid, rc)
			dcache[pid] = board_dirs(sh, th) if (sh is not None and sh.ok and th is not None) else None
	return {pid: dcache[pid] for pid, p in project.pieces.items() if p.estado == "colocada" and pid in dcache}


def board_sigma(project, cache: Optional[_Cache] = None, dcache: Optional[dict] = None) -> dict:
	"""Orientation of the side map measured on the placed pieces (:func:`side_orientation`)."""
	cache = cache or _Cache(project, calibration(project))
	return side_orientation(_placed_dirs(project, cache, {} if dcache is None else dcache))


def hole_queries(project, *, cells=None, min_neighbours: int = 1, cache: Optional[_Cache] = None,
				 dcache: Optional[dict] = None, exclude_piece: Optional[str] = None) -> list:
	"""Holes of the board: cells that are not occupied (photo-only cells count as empty, user hints are
	not neighbours) with >= ``min_neighbours`` placed 4-neighbours with shape and pose. ``cells`` limits
	the search; ``exclude_piece`` removes one placed piece (its cell becomes a hole: the inverse-direction
	measurement)."""
	cache = cache or _Cache(project, calibration(project))
	dcache = {} if dcache is None else dcache
	prof = project.profile
	todo = [tuple(c) for c in cells] if cells is not None else [lc for lc, _ in project.board.iter_cells()]
	out = []
	for lc in todo:
		b = project.board[lc]
		if b["estado"] == "colocada" and b.get("peca_id") != exclude_piece:
			continue
		if b["estado"] == "ocupada_legado" and b.get("fonte") != "foto":
			continue
		sides = []
		for d in DIRS:
			nb = (lc[0] + STEP[d][0], lc[1] + STEP[d][1])
			if not prof.in_grid(*nb):
				continue
			bn = project.board[nb]
			pid = bn.get("peca_id")
			if bn["estado"] != "colocada" or not pid or pid == exclude_piece:
				continue
			if pid not in dcache:
				from src import render
				sh = cache.shape(pid)
				th = render.initial_theta(project, pid)
				dcache[pid] = board_dirs(sh, th) if (sh is not None and sh.ok and th is not None) else None
			dr = dcache[pid]
			if dr is None:
				continue
			sds = cache.eroded(pid)
			if sds is None:
				continue
			i = dr[OPP[d]]                       # the neighbour's side that faces the hole
			fa = f_adjacent([s.kind for s in sds])
			sides.append(HoleSide(piece_id=pid, direction=d, side=sds[i], f_adj=bool(fa[i]), strip=cache.strip(pid)[i],
								  scan_id=project.piece(pid).scan_id))
		if len(sides) >= min_neighbours:
			out.append(HoleQuery(cell=lc, sides=sides, zone=zone_of(lc), f_required=tuple(sorted(prof.flat_directions(*lc)))))
	return out


def pool_items(project, *, lote: Optional[int] = None, pieces=None, cache: Optional[_Cache] = None) -> list:
	"""Loose pieces (``solta`` / ``emparelhada``, not re-scans) as :class:`FitItem` (eroded sides, strips)."""
	cache = cache or _Cache(project, calibration(project))
	ids = list(pieces) if pieces is not None else [p.id for p in project.loose_pieces(lote)]
	out = []
	for pid in ids:
		sh = cache.shape(pid)
		if sh is None or not sh.ok:
			continue
		sds = cache.eroded(pid)
		if sds is None:
			continue
		p = project.piece(pid)
		out.append(FitItem(id=pid, shape=sh, sides=sds, strips=cache.strip(pid), lote=p.lote, n_no_lote=p.n_no_lote, scan_id=p.scan_id))
	return out


def _rejected_for(project) -> dict:
	out = collections.defaultdict(set)
	for pid, cell, _origin in project.model.rejections:
		if cell is not None:
			out[tuple(cell)].add(pid)
	return out


_CONF_ORDER = {"alta": 0, "media": 1, "sem": 2}


def rank_all(project, *, calib: Optional[FitCalibration] = None, lote: Optional[int] = None, cells=None, top: int = 3,
			 min_neighbours: int = 1, joint: bool = True, cache: Optional[_Cache] = None, progress=None) -> dict:
	"""Every hole of the board against the loose pool: ``{'holes': [rank_hole dicts, ordered by confidence
	(alta with m >= 2 first, then alta, media, sem; margin within)], 'sigma', 'n_pool', 'n_holes', 'calib',
	'assigned': {cell: piece}, 'tiras': {'calculadas', 'previstas', 'em_cache', 'segundos'}}`` or ``{'error'}``.

	``progress(n, N, segundos)``: called while the image strips are computed (the slow part of a cold start,
	about 0.3 s per piece): once at the start with ``n = 0`` when ``N > 0``, then every :data:`PROGRESS_EVERY_N`
	strips or :data:`PROGRESS_EVERY_S` seconds, and at the end. ``N`` = :meth:`_Cache.strips_todo` (an upper
	bound). The ranking itself does not change with ``progress``."""
	calib = calib or calibration(project)
	cache = cache or _Cache(project, calib)
	dcache = {}
	todo = cache.strips_todo(cells=cells, lote=lote)
	n_cache0 = len(cache.strips)
	done = [0]
	t0 = time.time()
	if progress is not None and todo:
		progress(0, len(todo), 0.0)
		last = [t0, 0]

		def hook(pid):
			done[0] += 1
			now = time.time()
			if done[0] - last[1] >= PROGRESS_EVERY_N or now - last[0] >= PROGRESS_EVERY_S or done[0] >= len(todo):
				last[0], last[1] = now, done[0]
				progress(done[0], len(todo), now - t0)
		cache.on_compute = hook
	else:
		cache.on_compute = (lambda pid: done.__setitem__(0, done[0] + 1))
	try:
		sg = board_sigma(project, cache, dcache)
		if "error" in sg:
			return {"error": sg["error"], "sigma": None}
		holes = hole_queries(project, cells=cells, min_neighbours=min_neighbours, cache=cache, dcache=dcache)
		items = pool_items(project, lote=lote, cache=cache)
	finally:
		cache.on_compute = None
	tiras = {"calculadas": done[0], "previstas": len(todo), "em_cache": n_cache0, "segundos": round(time.time() - t0, 1)}
	if progress is not None and todo and done[0] < len(todo):
		progress(done[0], len(todo), time.time() - t0)      # fewer than predicted (pieces without shape): close the line
	cache.save()
	if not items:
		return {"error": "sem peças soltas no índice" + (f" (lote {lote})" if lote else ""), "sigma": sg["sigma"], "n_holes": len(holes),
				"tiras": tiras}
	pa = pool_arrays(items)
	rej = _rejected_for(project)
	res = [rank_hole(h, pa, calib=calib, sigma=sg["sigma"], top=top, exclude=rej.get(tuple(h.cell), ())) for h in holes]
	assigned = assign(res) if joint else {}
	res.sort(key=lambda r: (_CONF_ORDER.get(r.get("confidence"), 3), 0 if r.get("m", 0) >= 2 else 1,
							-(r.get("margin") or 0.0), r.get("d1") if r.get("d1") is not None else np.inf))
	for r in res:
		r.pop("ranking", None)
	return {"holes": res, "sigma": sg["sigma"], "n_sigma": sg["n"], "n_pool": len(items), "n_holes": len(holes),
			"calib": calib.to_dict(), "assigned": {f"{c[0]},{c[1]}": p for c, p in assigned.items()}, "tiras": tiras}


def alta_suggestions(holes: list) -> list:
	"""The ``alta`` suggestions for «Vai buscar» (M11_CRITERIOS §8) out of ``rank_all()['holes']``: one dict per hole
	with ``confidence == 'alta'`` whose rank-1 candidate agrees with the joint assignment (``assigned`` is that piece,
	or there is no assignment); ``{'hole': rank_hole dict, 'candidate': its rank-1 candidate}``. Holes whose
	assignment goes to another piece are left out (``conflito`` in the GUI list), as are media / sem."""
	out = []
	for h in holes:
		if h.get("confidence") != "alta" or not h.get("candidates"):
			continue
		c0 = h["candidates"][0]
		if int(c0.get("rank") or 0) != 1:
			continue
		asg = h.get("assigned")
		if asg is not None and asg != c0["id"]:
			continue
		out.append({"hole": h, "candidate": c0})
	return out


def _alta_decision(e: dict) -> bool:
	return (e.get("action") in ("hole_confirmed", "hole_rejected") and e.get("origin") == "buraco"
			and e.get("confianca") == "alta" and e.get("rank") is not None and int(e["rank"]) == 1)


def alta_counter(project, events: Optional[list] = None) -> dict:
	"""Counter and pause state of the ``alta`` suggestions (M11_CRITERIOS §8). A decision is a ``hole_confirmed`` /
	``hole_rejected`` with origin ``buraco``, ``confianca == 'alta'`` and ``rank == 1`` (the suggested piece); the
	window is the last :data:`ALTA_JANELA` decisions after the last ``holes_alta_resumed``; the suggestions are
	paused while the window holds >= :data:`ALTA_MAX_FALHAS` rejections. Returns ``{acertos, falhas, total,
	precisao, ic95, janela: {n, falhas, acertos, tamanho, max_falhas, em_pausa}, em_pausa, reativado_em,
	ultima_decisao}``; everything is derived from the log."""
	evs = project.events() if events is None else events
	dec, start, resumed = [], 0, None
	for e in evs:
		if e.get("action") == "holes_alta_resumed":
			start, resumed = len(dec), e.get("t")
		elif _alta_decision(e):
			dec.append(e)
	ok = sum(1 for e in dec if e["action"] == "hole_confirmed")
	bad = len(dec) - ok
	lo, hi = wilson(ok, len(dec))
	win = dec[start:][-ALTA_JANELA:]
	wbad = sum(1 for e in win if e["action"] == "hole_rejected")
	paused = wbad >= ALTA_MAX_FALHAS
	return {"acertos": ok, "falhas": bad, "total": len(dec), "precisao": (ok / len(dec) if dec else None),
			"ic95": ([lo, hi] if dec else None),
			"janela": {"n": len(win), "falhas": wbad, "acertos": len(win) - wbad, "tamanho": ALTA_JANELA,
					   "max_falhas": ALTA_MAX_FALHAS, "em_pausa": paused},
			"em_pausa": paused, "reativado_em": resumed, "ultima_decisao": (dec[-1].get("t") if dec else None)}


def format_counter(c: dict) -> str:
	ic = f" (Wilson {_pct(*c['ic95'])})" if c.get("ic95") else ""
	prec = f"{100 * c['precisao']:.0f} %" if c.get("precisao") is not None else "—"
	w = c["janela"]
	return (f"sugestões alta em «Vai buscar» (rank 1): acertos {c['acertos']} / falhas {c['falhas']} / total {c['total']}; precisão {prec}{ic}; "
			f"janela {w['falhas']} falhas em {w['n']} (pausa a partir de {w['max_falhas']} em {w['tamanho']}): "
			+ ("EM PAUSA" if c["em_pausa"] else "ativas") + (f"; reativadas em {c['reativado_em']}" if c.get("reativado_em") else ""))


# ---------------------------------------------------------------- report over the confirmations (GT)
def _hole_events(project) -> list:
	return [e for e in project.events() if e["action"] in ("hole_confirmed", "hole_rejected") and e.get("origin") == "buraco"]


def report(project) -> dict:
	"""Top-1 / top-3 with Wilson over the physical confirmations of hole candidates (``hole_confirmed``
	with ``rank``), by zone, number of neighbours and confidence; rejections by confidence; whether the
	threshold of RESULTADOS.md §15.6 (n >= 60, >= 40 with >= 2 neighbours, cases outside the sky) is met."""
	evs = _hole_events(project)
	conf = [e for e in evs if e["action"] == "hole_confirmed" and e.get("rank") is not None]
	rej = [e for e in evs if e["action"] == "hole_rejected"]

	def agg(rows):
		n = len(rows)
		k1 = sum(1 for e in rows if int(e["rank"]) == 1)
		k3 = sum(1 for e in rows if int(e["rank"]) <= 3)
		return {"n": n, "top1": k1, "top3": k3, "wilson1": list(wilson(k1, n)), "wilson3": list(wilson(k3, n))}

	by = {"zona": collections.defaultdict(list), "vizinhas": collections.defaultdict(list), "confianca": collections.defaultdict(list)}
	for e in conf:
		by["zona"][zone_of(e.get("cell"))].append(e)
		by["vizinhas"][str(e.get("m"))].append(e)
		by["confianca"][str(e.get("confianca"))].append(e)
	n_m2 = sum(1 for e in conf if (e.get("m") or 0) >= 2)
	n_fora_ceu = sum(1 for e in conf if zone_of(e.get("cell")) != "céu")
	return {"n": len(conf), "n_m2": n_m2, "n_fora_ceu": n_fora_ceu, "total": agg(conf),
			"por": {k: {kk: agg(v) for kk, v in sorted(d.items())} for k, d in by.items()},
			"rejeicoes": {"n": len(rej), "por_confianca": dict(collections.Counter(str(e.get("confianca")) for e in rej))},
			"limiar_15_6": {"n_ge_60": len(conf) >= 60, "n_m2_ge_40": n_m2 >= 40, "fora_do_ceu": n_fora_ceu > 0,
							"atingido": len(conf) >= 60 and n_m2 >= 40 and n_fora_ceu > 0},
			"versoes": sorted({str(e.get("fit_version")) for e in evs}),
			"alta": alta_counter(project)}


def _pct(lo, hi):
	return f"{100 * lo:.0f}–{100 * hi:.0f} %"


def format_report(r: dict) -> str:
	t = r["total"]
	lines = [f"confirmações físicas de candidatas de buraco: n = {r['n']} ({r['n_m2']} com ≥ 2 vizinhas, {r['n_fora_ceu']} fora do céu); rejeições: {r['rejeicoes']['n']} {r['rejeicoes']['por_confianca']}"]
	if r["n"]:
		lines.append(f"  top-1 {t['top1']}/{t['n']} (Wilson {_pct(*t['wilson1'])}), top-3 {t['top3']}/{t['n']} ({_pct(*t['wilson3'])})")
		for k, d in r["por"].items():
			for kk, a in d.items():
				lines.append(f"  por {k} {kk}: n={a['n']} top-1 {a['top1']} ({_pct(*a['wilson1'])}) top-3 {a['top3']}")
	lim = r["limiar_15_6"]
	lines.append("limiar do §15.6 (n ≥ 60, ≥ 40 com ≥ 2 vizinhas, casos fora do céu): " + ("ATINGIDO" if lim["atingido"] else "não atingido")
				 + f" [n ≥ 60: {lim['n_ge_60']}, ≥ 2 viz. ≥ 40: {lim['n_m2_ge_40']}, fora do céu: {lim['fora_do_ceu']}]")
	if r.get("alta"):
		lines.append(format_counter(r["alta"]))
	return "\n".join(lines)


def format_hole(r: dict) -> str:
	if "error" in r:
		return f"erro: {r['error']}"
	head = f"({r['cell'][0]},{r['cell'][1]}) {r['zone']} m={r['m']} {r['confidence']}: d1 {_fmt(r['d1'])} margem {_fmt(r['margin'])}"
	cs = "; ".join(f"#{c['rank']} {c['id']} (saco {c['lote']} nº {c['n_no_lote']}) J {_fmt(c['J'])} rot {c['rot']}"
				   + (f" → melhor para {c['melhor_para']}" if c.get("melhor_para") else "") for c in r["candidates"])
	return head + (" | " + cs if cs else " | sem candidatas finitas")


def main(argv=None) -> int:
	ap = argparse.ArgumentParser(prog="python -m src.fit", description=__doc__.split("\n")[0])
	ap.add_argument("--project", default="projects/alpes")
	ap.add_argument("--lote", type=int, default=None, help="só as soltas deste saco")
	ap.add_argument("--cell", nargs=2, type=int, metavar=("L", "C"), help="só este buraco")
	ap.add_argument("--top", type=int, default=3)
	ap.add_argument("--json", metavar="FILE", help="escreve o resultado completo em JSON")
	ap.add_argument("--relatorio", action="store_true", help="top-1/top-3 e Wilson sobre as confirmações físicas acumuladas")
	a = ap.parse_args(argv)
	from src import activity
	from src.state import Project
	activity.setup(console=True)
	pr = Project.open(a.project)
	if a.relatorio:
		r = report(pr)
		print(format_report(r))
		if a.json:
			json.dump(r, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
		return 0
	def prog(n, N, s):
		activity.get("progresso").info(f"tiras das peças: {n}/{N} ({s:.0f} s)")
	res = rank_all(pr, lote=a.lote, cells=([tuple(a.cell)] if a.cell else None), top=a.top, progress=prog)
	if "error" in res:
		print("erro:", res["error"])
		return 1
	c = res["calib"]
	print(f"σ = {res['sigma']:+d} ({res['n_sigma']} peças colocadas); {res['n_holes']} buracos, {res['n_pool']} soltas; "
		  f"calibração {'do perfil' if c['calibrated'] else 'POR CALIBRAR'}: erosão {c['erosion_mm']} mm, corte {c['chord_cut']}, T_abs {c['t_abs']}")
	cnt = collections.Counter(r["confidence"] for r in res["holes"])
	print("por confiança:", dict(cnt))
	for r in res["holes"]:
		if a.cell or r["confidence"] != "sem":
			print(format_hole(r))
			if a.cell:
				for s in r["reasons"]:
					print("   ", s)
	if a.json:
		json.dump(res, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=lambda o: float(o) if isinstance(o, np.floating) else int(o))
	return 0


if __name__ == "__main__":
	sys.exit(main())
