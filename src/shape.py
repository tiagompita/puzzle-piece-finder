"""Piece shape analysis in millimetres: corners, sides, topology class, free-shape metric.

Promotion of the E-sym prototypes (``tools/diagnostico/forma/shapelib.py``
``analyse_v2`` / ``find_corners_v2`` / ``shape_dist``, ``tools/diagnostico/forma/dist.py``
``free_dist``, ``tools/diagnostico/gemeos/esym.py`` ``free_vec``,
``tools/diagnostico/gemeos/ereal2.py`` chord rule and ``tools/diagnostico/gemeos/cortes.py``
``neg_inv``). The algorithm is unchanged; the only difference is that the contour is
converted to mm on entry (the prototype worked in px at 300 dpi and multiplied by
``MM`` at the end), so every length here is in mm.

Conventions:
	* image frame, x to the right, y down; contours are made "ccw" in the prototype sense
	  (positive shoelace area in image coordinates, i.e. clockwise on screen);
	* a piece has 4 sides in contour order, side ``i`` going from corner ``i`` to corner
	  ``i + 1``; side kinds ``'F'`` (flat), ``'T'`` (tab, outward), ``'B'`` (blank, inward);
	* ``cls`` is the side-kind string canonical under cyclic rotation (:func:`canon`).

Pure module: numpy only, no I/O, nothing puzzle-specific (the twin rotation comes from
:class:`src.profile.PuzzleProfile`).
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np

__all__ = [
	"Side", "Shape", "mm_per_px", "analyse", "free_dist", "corner_dist", "homologous_k", "chord_pass",
	"side_complement", "transform_contour", "canon", "f_adjacent",
	"N_CONTOUR", "N_SIDE", "N_FREE", "TAB_T", "FREE_SMOOTH_SIGMA",
]

# ---------------------------------------------------------------- tuned constants (E-sym, shapelib v2)
N_CONTOUR = 1200            # arclength resampling of the input contour
N_SIDE = 64                 # samples per side profile / per side of the corner vector
N_FREE = 512                # samples of the free-shape vector
FREE_SMOOTH_SIGMA = 1.5     # Gaussian smoothing (contour samples) before the free vector
TAB_T = 0.15                # tab/blank threshold on the normalised side profile (fraction of chord)
CORNER_SMOOTH_SIGMA = 2.0   # smoothing (samples) for the corner search
CORNER_STEP_MM = (1.2, 2.5)  # arc scales (mm) of the chord-angle corner score
CORNER_NMS_MM = 2.0         # non-maximum suppression radius of the corner candidates (mm of arc)
CORNER_ARM_MM = 2.0         # arm length (mm of arc) for the arm-alignment term
CORNER_COST_MAX = 140.0     # candidates above this cost are discarded
CORNER_NCAND = 20           # best candidates kept
SIDE_LMIN_MM = 14.0         # admissible corner-to-corner chord range (mm)
SIDE_LMAX_MM = 23.0
W_OPP = 4.0                 # weight of the opposite-side mismatch (per mm)
W_AB = 3.0                  # weight of the |A - B| aspect mismatch (per mm)
W_CAND = 0.3                # weight of the candidates' own cost
ROUGH_SIGMA = 6.0           # smoothing (samples) for the roughness ratio
CONCAVE_PENALTY = 1000.0
CHORD_NORMAL_MM = 1.0       # chord rule, "tipo" mode (ereal2.DL_MAX)
CHORD_F_ADJ_MM = 2.0        # chord rule on F sides and sides adjacent to an F (ereal2.DL_F_ADJ)


def mm_per_px(dpi: float) -> float:
	"""Scan scale in mm per pixel (``25.4 / dpi``). Never derive it from the GUI px/cm."""
	if dpi <= 0:
		raise ValueError("dpi must be positive")
	return 25.4 / float(dpi)


# ---------------------------------------------------------------- data classes
@dataclass
class Side:
	"""One side of a piece.

	kind: ``'F'``, ``'T'`` or ``'B'``. chord_mm: corner-to-corner distance. profile:
	``(N_SIDE, 2)`` with x in [0, 1] along the chord and y the outward deviation, both
	divided by the chord. direction_deg: angle of the chord from corner i to corner i+1
	in the image frame (``atan2(dy, dx)``, y down). p0_mm / p1_mm: the two corners in
	the frame of the input contour (mm).
	"""

	kind: str
	chord_mm: float
	profile: np.ndarray
	direction_deg: float
	p0_mm: np.ndarray
	p1_mm: np.ndarray


@dataclass
class Shape:
	"""Result of :func:`analyse`. All lengths in mm.

	ok: 4 corners found. corners: indices into ``c`` (empty if not ok). c: contour
	resampled to ``N_CONTOUR`` points, ccw. sides: 4 :class:`Side` in contour order
	(empty if not ok). cls: canonical side-kind string ('' if not ok). vec:
	``(4 * N_SIDE, 2)`` corner-aligned vector (empty if not ok). z: ``N_FREE`` complex
	centred free vector (always filled). area_mm2, roughness (perimeter / smoothed
	perimeter), centroid_mm (polygon centroid) always filled. n_flat: number of F sides.
	body_angle_deg: dominant orientation mod 90 (of the chords if ok, else of the
	contour tangents). qscore / corner_cost: corner-search costs (inf / empty if not ok).
	"""

	ok: bool
	corners: np.ndarray
	c: np.ndarray
	sides: list
	cls: str
	vec: np.ndarray
	z: np.ndarray
	area_mm2: float
	n_flat: int
	roughness: float
	centroid_mm: np.ndarray
	body_angle_deg: float
	qscore: float
	corner_cost: np.ndarray = field(default_factory=lambda: np.zeros(0))

	@property
	def types(self) -> list:
		return [s.kind for s in self.sides]

	@property
	def lens(self) -> list:
		return [float(s.chord_mm) for s in self.sides]

	def to_arrays(self) -> dict:
		"""Flat dict of numpy arrays (for ``np.savez``; no pickling needed)."""
		ns = len(self.sides)
		d = {
			"ok": np.array(bool(self.ok)),
			"corners": np.asarray(self.corners, np.int64).reshape(-1),
			"c": np.asarray(self.c, float),
			"cls": np.array(str(self.cls)),
			"vec": np.asarray(self.vec, float).reshape(-1, 2),
			"z": np.asarray(self.z, complex),
			"area_mm2": np.array(float(self.area_mm2)),
			"n_flat": np.array(int(self.n_flat)),
			"roughness": np.array(float(self.roughness)),
			"centroid_mm": np.asarray(self.centroid_mm, float),
			"body_angle_deg": np.array(float(self.body_angle_deg)),
			"qscore": np.array(float(self.qscore)),
			"corner_cost": np.asarray(self.corner_cost, float).reshape(-1),
			"side_kind": np.array([s.kind for s in self.sides], dtype="<U1").reshape(ns),
			"side_chord_mm": np.array([s.chord_mm for s in self.sides], float).reshape(ns),
			"side_profile": np.array([s.profile for s in self.sides], float).reshape(ns, N_SIDE, 2),
			"side_direction_deg": np.array([s.direction_deg for s in self.sides], float).reshape(ns),
			"side_p0_mm": np.array([s.p0_mm for s in self.sides], float).reshape(ns, 2),
			"side_p1_mm": np.array([s.p1_mm for s in self.sides], float).reshape(ns, 2),
		}
		return d

	@classmethod
	def from_arrays(cls, d: dict) -> "Shape":
		"""Inverse of :meth:`to_arrays` (exact round trip)."""
		sides = [Side(kind=str(d["side_kind"][i]), chord_mm=float(d["side_chord_mm"][i]),
					  profile=np.array(d["side_profile"][i], float), direction_deg=float(d["side_direction_deg"][i]),
					  p0_mm=np.array(d["side_p0_mm"][i], float), p1_mm=np.array(d["side_p1_mm"][i], float))
				 for i in range(len(d["side_kind"]))]
		return cls(ok=bool(d["ok"]), corners=np.array(d["corners"], np.int64), c=np.array(d["c"], float), sides=sides,
				   cls=str(d["cls"]), vec=np.array(d["vec"], float), z=np.array(d["z"], complex),
				   area_mm2=float(d["area_mm2"]), n_flat=int(d["n_flat"]), roughness=float(d["roughness"]),
				   centroid_mm=np.array(d["centroid_mm"], float), body_angle_deg=float(d["body_angle_deg"]),
				   qscore=float(d["qscore"]), corner_cost=np.array(d["corner_cost"], float))


# ---------------------------------------------------------------- contour primitives
def _signed_area(c: np.ndarray) -> float:
	x, y = c[:, 0], c[:, 1]
	return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def _ccw(c: np.ndarray) -> np.ndarray:
	"""Positive shoelace area in image coordinates (shapelib.ccw)."""
	return c if _signed_area(c) > 0 else c[::-1].copy()


def _resample_closed(c: np.ndarray, n: int) -> np.ndarray:
	p = np.vstack([c, c[:1]])
	seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
	s = np.concatenate([[0], np.cumsum(seg)])
	t = np.linspace(0, s[-1], n, endpoint=False)
	return np.c_[np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])]


def _resample_open(p: np.ndarray, n: int) -> np.ndarray:
	seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
	s = np.concatenate([[0], np.cumsum(seg)])
	t = np.linspace(0, s[-1], n)
	return np.c_[np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])]


def _smooth_closed(c: np.ndarray, sigma_pts: float) -> np.ndarray:
	if sigma_pts <= 0:
		return c
	r = int(3 * sigma_pts)
	k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma_pts) ** 2)
	k /= k.sum()
	out = np.empty_like(c)
	for d in range(2):
		x = np.concatenate([c[-r:, d], c[:, d], c[:r, d]])
		out[:, d] = np.convolve(x, k, mode="valid")
	return out


def _perimeter(c: np.ndarray) -> float:
	return float(np.sum(np.linalg.norm(np.diff(np.vstack([c, c[:1]]), axis=0), axis=1)))


def _centroid(c: np.ndarray) -> np.ndarray:
	"""Polygon (area) centroid; falls back to the point mean for degenerate polygons."""
	x, y = c[:, 0], c[:, 1]
	cr = x * np.roll(y, -1) - np.roll(x, -1) * y
	a = 0.5 * cr.sum()
	if abs(a) < 1e-12:
		return c.mean(0)
	return np.array([np.sum((x + np.roll(x, -1)) * cr), np.sum((y + np.roll(y, -1)) * cr)]) / (6 * a)


def _unit(v: np.ndarray) -> np.ndarray:
	return v / (np.linalg.norm(v) + 1e-9)


# ---------------------------------------------------------------- corners (shapelib v2)
def _corner_scores(c: np.ndarray, step_mm: float):
	"""Chord angle (deg) to +/-k points at arc ~step_mm and convexity flag (shapelib.corner_scores)."""
	n = len(c)
	k = max(2, int(round(step_mm / (_perimeter(c) / n))))
	a = np.roll(c, k, axis=0) - c
	b = np.roll(c, -k, axis=0) - c
	cosv = np.sum(a * b, 1) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1) + 1e-9)
	ang = np.degrees(np.arccos(np.clip(cosv, -1, 1)))
	u = c - np.roll(c, k, axis=0)
	v = np.roll(c, -k, axis=0) - c
	cross = u[:, 0] * v[:, 1] - u[:, 1] * v[:, 0]
	return ang, cross > 0


def _find_corners(c: np.ndarray):
	"""shapelib.find_corners_v2 in mm. Returns (indices | None, smoothed contour, cost, qscore)."""
	n = len(c)
	cs = _smooth_closed(c, CORNER_SMOOTH_SIGMA)
	a1, cv1 = _corner_scores(cs, CORNER_STEP_MM[0])
	a2, cv2 = _corner_scores(cs, CORNER_STEP_MM[1])
	cost = np.abs(a1 - 90) + np.abs(a2 - 90) + np.where(cv1 & cv2, 0, CONCAVE_PENALTY)
	step = np.sum(np.linalg.norm(np.diff(c, axis=0), axis=1)) / n
	w = max(3, int(CORNER_NMS_MM / step))
	ka = max(3, int(CORNER_ARM_MM / step))
	order = np.argsort(cost)
	taken = np.zeros(n, bool)
	cand = []
	for i in order:
		if cost[i] > CORNER_COST_MAX or len(cand) >= CORNER_NCAND:
			break
		if taken[i]:
			continue
		cand.append(int(i))
		for j in range(-w, w + 1):
			taken[(i + j) % n] = True
	best = (np.inf, None)
	for q in itertools.combinations(sorted(cand), 4):
		q = list(q)
		P = cs[q]
		L = np.linalg.norm(P - np.roll(P, -1, axis=0), axis=1)
		if L.min() < SIDE_LMIN_MM or L.max() > SIDE_LMAX_MM:
			continue
		ok = True
		angs = []
		arm = 0.0
		for j in range(4):
			u = P[j] - P[j - 1]
			v = P[(j + 1) % 4] - P[j]
			if u[0] * v[1] - u[1] * v[0] <= 0:
				ok = False
				break
			x = P[j - 1] - P[j]
			y = P[(j + 1) % 4] - P[j]
			angs.append(np.degrees(np.arccos(np.clip(_unit(x) @ _unit(y), -1, 1))))
			fwd = cs[(q[j] + ka) % n] - cs[q[j]]
			bwd = cs[(q[j] - ka) % n] - cs[q[j]]
			arm += np.degrees(np.arccos(np.clip(_unit(fwd) @ _unit(y), -1, 1)))
			arm += np.degrees(np.arccos(np.clip(_unit(bwd) @ _unit(x), -1, 1)))
		if not ok:
			continue
		A = (L[0] + L[2]) / 2
		B = (L[1] + L[3]) / 2
		sc = (np.sum(np.abs(np.array(angs) - 90)) + W_OPP * (abs(L[0] - L[2]) + abs(L[1] - L[3]))
			  + W_AB * abs(A - B) + arm + W_CAND * cost[q].sum())
		if sc < best[0]:
			best = (sc, q)
	return best[1], cost, float(best[0])


def _split_sides(c: np.ndarray, idx) -> list:
	sides = []
	for k in range(4):
		a, b = idx[k], idx[(k + 1) % 4]
		sides.append(c[a:b + 1] if b > a else np.vstack([c[a:], c[:b + 1]]))
	return sides


def _normalise_side(seg: np.ndarray, ctr: np.ndarray):
	"""Profile in the chord frame divided by the chord, outward = +y (shapelib.normalise_side)."""
	p0, p1 = seg[0], seg[-1]
	L = float(np.linalg.norm(p1 - p0))
	u = (p1 - p0) / L
	v = np.array([-u[1], u[0]])
	q = np.c_[(seg - p0) @ u, (seg - p0) @ v] / L
	if ((ctr - p0) @ v) / L > 0:
		q[:, 1] *= -1
	return _resample_open(q, N_SIDE), L


def _classify_side(prof: np.ndarray) -> str:
	mx, mn = prof[:, 1].max(), prof[:, 1].min()
	if mx > TAB_T and mx >= -mn:
		return "T"
	if -mn > TAB_T:
		return "B"
	return "F"


def canon(types) -> str:
	"""Side-kind string canonical under cyclic rotation (lexicographic minimum)."""
	s = "".join(types)
	return min(s[k:] + s[:k] for k in range(len(s))) if s else ""


def f_adjacent(types) -> list:
	"""Per side: is it F or adjacent to an F? (the corner of a flat side slides along it)."""
	n = len(types)
	return [types[s] == "F" or types[(s - 1) % n] == "F" or types[(s + 1) % n] == "F" for s in range(n)]


def _orientation_mod90(angles_deg: np.ndarray, weights: np.ndarray) -> float:
	"""Weighted 4-fold circular mean of directions, in [0, 90)."""
	z = np.sum(weights * np.exp(4j * np.radians(angles_deg)))
	return float(np.degrees(np.angle(z)) / 4.0) % 90.0


def _free_vec(c: np.ndarray) -> np.ndarray:
	"""esym.free_vec: smoothed contour, N_FREE points, centred, complex."""
	z = _resample_closed(_smooth_closed(c, FREE_SMOOTH_SIGMA), N_FREE)
	z = z - z.mean(0)
	return z[:, 0] + 1j * z[:, 1]


# ---------------------------------------------------------------- analysis
def analyse(contour_px, mm_per_px: float) -> Shape:
	"""Shape of one piece from its contour in pixels (any ``(n, 2)`` / ``(n, 1, 2)`` array).

	``mm_per_px`` converts the contour to mm on entry (use :func:`mm_per_px` of the scan
	dpi, or ``segment_scan(...)['mm_per_px']``). Equivalent to ``shapelib.analyse_v2`` +
	``esym.free_vec`` with every length in mm. If no 4-corner configuration is found,
	``ok`` is False but ``z``, ``area_mm2``, ``roughness``, ``centroid_mm`` and
	``body_angle_deg`` are filled.
	"""
	p = np.asarray(contour_px, float).reshape(-1, 2) * float(mm_per_px)
	if len(p) < 3:
		raise ValueError("contour needs at least 3 points")
	c = _ccw(_resample_closed(p, N_CONTOUR))
	cs6 = _smooth_closed(c, ROUGH_SIGMA)
	rough = _perimeter(c) / _perimeter(cs6)
	z = _free_vec(c)
	area = abs(_signed_area(c))
	ctr_area = _centroid(c)
	idx, cost, qsc = _find_corners(c)
	if idx is None:
		t = np.diff(np.vstack([c, c[:1]]), axis=0)
		ang = np.degrees(np.arctan2(t[:, 1], t[:, 0]))
		return Shape(ok=False, corners=np.zeros(0, np.int64), c=c, sides=[], cls="", vec=np.zeros((0, 2)), z=z,
					 area_mm2=area, n_flat=0, roughness=rough, centroid_mm=ctr_area,
					 body_angle_deg=_orientation_mod90(ang, np.linalg.norm(t, axis=1)), qscore=np.inf,
					 corner_cost=np.zeros(0))
	ctr = c.mean(0)  # the prototype orients the side profiles with the point mean
	segs = _split_sides(c, idx)
	sides = []
	for s in segs:
		pr, L = _normalise_side(s, ctr)
		d = s[-1] - s[0]
		sides.append(Side(kind=_classify_side(pr), chord_mm=L, profile=pr,
						  direction_deg=float(np.degrees(np.arctan2(d[1], d[0]))), p0_mm=s[0].copy(),
						  p1_mm=s[-1].copy()))
	vec = np.vstack([_resample_open(s, N_SIDE + 1)[:-1] for s in segs])
	types = [s.kind for s in sides]
	return Shape(ok=True, corners=np.array(idx, np.int64), c=c, sides=sides, cls=canon(types), vec=vec, z=z,
				 area_mm2=area, n_flat=types.count("F"), roughness=rough, centroid_mm=ctr_area,
				 body_angle_deg=_orientation_mod90(np.array([s.direction_deg for s in sides]),
												   np.array([s.chord_mm for s in sides])),
				 qscore=qsc, corner_cost=np.array([float(cost[i]) for i in idx]))


# ---------------------------------------------------------------- distances
def free_dist(a: Shape, b: Shape):
	"""Corner-free shape distance (dist.free_dist): ``(rms_mm, shift, phi_deg)``.

	Minimum over cyclic start shift and rotation of the RMS between the ``z`` vectors.
	``np.roll(b.z, -shift) * exp(1j * radians(phi_deg))`` is aligned to ``a.z``; the same
	rotation in point form is ``transform_contour(b_points, phi_deg)``.
	"""
	za, zb = a.z, b.z
	corr = np.fft.ifft(np.conj(np.fft.fft(za)) * np.fft.fft(zb))
	m = np.abs(corr)
	s = int(np.argmax(m))
	rms2 = (np.sum(np.abs(za) ** 2) + np.sum(np.abs(zb) ** 2) - 2 * m[s]) / len(za)
	return float(np.sqrt(max(rms2, 0.0))), s, float(np.degrees(-np.angle(corr[s])))


def _kabsch_rms(A: np.ndarray, B: np.ndarray):
	H = A.T @ B
	U, _, Vt = np.linalg.svd(H)
	D = np.diag([1, np.sign(np.linalg.det(U @ Vt))])
	R = U @ D @ Vt
	return float(np.sqrt(np.mean(np.sum((A @ R - B) ** 2, axis=1)))), R


def corner_dist(a: Shape, b: Shape):
	"""Corner-aligned distance (shapelib.shape_dist): ``(rms_mm, best_k, R)``.

	4 cyclic corner alignments x Kabsch rotation; side ``i`` of ``a`` <-> side
	``(i + best_k) % 4`` of ``b``. ``(inf, 0, None)`` if either shape is not ok.
	"""
	if not (a.ok and b.ok):
		return np.inf, 0, None
	A = a.vec - a.vec.mean(0)
	best = (np.inf, 0, None)
	for k in range(4):
		B = np.roll(b.vec, -k * N_SIDE, axis=0)
		B = B - B.mean(0)
		d, R = _kabsch_rms(A, B)
		if d < best[0]:
			best = (d, k, R)
	return best


def homologous_k(a: Shape, b: Shape) -> int:
	"""Cyclic offset k such that side i of ``a`` is homologous to side ``(i + k) % 4`` of ``b``."""
	return corner_dist(a, b)[1]


def chord_pass(a: Shape, b: Shape, *, normal_mm: float = CHORD_NORMAL_MM, f_adj_mm: float = CHORD_F_ADJ_MM):
	"""Chord filter on homologous sides, "tipo" mode of ereal2 (``ok, worst_side, worst_dL_mm``).

	Same ``cls`` required (else ``(False, -1, inf)``). Tolerance per side of ``a`` is
	``f_adj_mm`` if that side or its homologue in ``b`` is F or adjacent to an F, else
	``normal_mm``. ``worst_side`` (index in ``a``) is the side with the largest excess
	``|dL| - tol``; ``worst_dL_mm`` is its ``|dL|``.
	"""
	if not (a.ok and b.ok) or a.cls != b.cls:
		return False, -1, np.inf
	k = homologous_k(a, b)
	fa, fb = f_adjacent(a.types), f_adjacent(b.types)
	worst, worst_ex, worst_d = -1, -np.inf, 0.0
	ok = True
	for s in range(4):
		t = (s + k) % 4
		d = abs(a.sides[s].chord_mm - b.sides[t].chord_mm)
		tol = f_adj_mm if (fa[s] or fb[t]) else normal_mm
		if d > tol:
			ok = False
		if d - tol > worst_ex:
			worst, worst_ex, worst_d = s, d - tol, d
	return ok, worst, float(worst_d)


def _neg_inv(pr: np.ndarray) -> np.ndarray:
	"""Profile of the mating side seen from the other piece (cortes.neg_inv): reversed, mirrored, negated."""
	q = pr[::-1].copy()
	q[:, 0] = 1 - q[:, 0]
	q[:, 1] = -q[:, 1]
	return q


def side_complement(sa: Side, sb: Side):
	"""Fit of two sides: ``(rms_mm, dL_mm)``; lower rms = better mate.

	Only T with B can mate (F with anything, T with T, B with B -> rms inf). The
	profile of ``sb`` is reversed and negated and compared with ``sa``; the RMS is
	scaled by the mean chord (cortes.pair_rms). ``dL_mm`` = |chord difference| (always).
	"""
	dl = abs(float(sa.chord_mm) - float(sb.chord_mm))
	if {sa.kind, sb.kind} != {"T", "B"}:
		return np.inf, dl
	d = float(np.sqrt(np.mean(np.sum((sa.profile - _neg_inv(sb.profile)) ** 2, -1))))
	return d * (sa.chord_mm + sb.chord_mm) / 2, dl


def transform_contour(points_mm, rotation_deg: float, mirror: bool = False, center=None) -> np.ndarray:
	"""Rotate (and optionally mirror) points about ``center`` (default: their mean).

	Rotation follows the complex convention of :func:`free_dist` (``z * exp(1j*theta)``
	with ``z = x + iy``, image frame y down, so positive angles look clockwise on
	screen). ``mirror`` flips x about the centre before rotating. For a twin ghost use
	``profile.twin_rotation_deg()``, never a hard-coded 180.
	"""
	p = np.asarray(points_mm, float).reshape(-1, 2)
	ctr = p.mean(0) if center is None else np.asarray(center, float).reshape(2)
	q = p - ctr
	if mirror:
		q[:, 0] = -q[:, 0]
	t = np.radians(rotation_deg)
	ct, st = np.cos(t), np.sin(t)
	return np.c_[q[:, 0] * ct - q[:, 1] * st, q[:, 0] * st + q[:, 1] * ct] + ctr
