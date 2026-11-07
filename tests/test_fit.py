"""Synthetic tests for :mod:`src.fit` (hole mould as a ranking; fast).

Pieces come from the generator of ``tests/test_shape.py`` (``make_piece``, nominal 18.5 mm square with
round knobs / sockets). A hole is built from the free sides of 2–3 synthetic neighbours: the true
piece has the complementary kinds (T facing B) and the complementary knob offsets; decoys have the
right kinds but other offsets. No image strips (``strips`` None): the dE term is NaN, so the E5 side
cost would be infinite — these tests use ``FitCalibration`` with strips absent and check the pure
shape path through ``side_costs`` with the image term disabled by giving every side the same strip.
"""

import numpy as np
import pytest

from src import fit as F
from src.shape import analyse, transform_contour
from test_shape import MMPP, make_piece

# board-pose kinds (top, right, bottom, left) of the true piece and the complementary neighbours
TRUE_KINDS = "TBTB"
OPP_KIND = {"T": "B", "B": "T", "F": "F"}
FLAT = np.zeros((F.N_STRIP, 3), np.float32)      # a constant strip: dE = 0 everywhere (image neutral)


def _shape(kinds, deltas=(0, 0, 0, 0), radii=(3, 3, 3, 3), rot_deg=0.0, noise=0.0, seed=0):
	pts = make_piece(kinds, deltas=deltas, radii=radii, noise=noise, rng=np.random.default_rng(seed)) * MMPP
	pts = transform_contour(pts, rot_deg, center=pts.mean(0))
	return analyse(pts / MMPP, MMPP)


def _side_facing(shape, direction):
	"""Side of ``shape`` (board pose) whose outward normal points to ``direction``."""
	dr = F.board_dirs(shape, 0.0)
	assert dr is not None
	return dr[direction]


def _item(pid, shape, strips=True):
	st = np.repeat(FLAT[None], 4, 0) if strips else None
	return F.FitItem(id=pid, shape=shape, sides=list(shape.sides), strips=st)


def _hole(neigh_dirs, true_deltas=(0.8, -0.5, 0.6, -0.9), radii=(3, 3, 3, 3), f_required=()):
	"""Neighbours on ``neigh_dirs`` complementary to the true piece; returns (HoleQuery, true Shape)."""
	true = _shape(TRUE_KINDS, deltas=true_deltas, radii=radii)
	sides = []
	for d in neigh_dirs:
		# the neighbour's side facing the hole has the complementary kind and the same knob offset (mirrored)
		j_true = _side_facing(true, d)
		k_true = true.sides[j_true].kind
		kinds = ["T", "B", "T", "B"]
		kinds_n = list(kinds)
		i_face = {"N": 2, "S": 0, "E": 3, "W": 1}[d]       # the neighbour's side that faces the hole, in board pose
		kinds_n[i_face] = OPP_KIND[k_true]
		deltas_n = [0.0, 0.0, 0.0, 0.0]
		deltas_n[i_face] = -true_deltas[{"N": 0, "E": 1, "S": 2, "W": 3}[d]]
		nb = _shape("".join(kinds_n), deltas=tuple(deltas_n), radii=radii)
		j = _side_facing(nb, F.OPP[d])
		fa = F.f_adjacent([s.kind for s in nb.sides])[j]
		sides.append(F.HoleSide(piece_id=f"N{d}", direction=d, side=nb.sides[j], f_adj=fa, strip=FLAT.copy(), scan_id="S1"))
	return F.HoleQuery(cell=(3, 3), sides=sides, zone="céu", f_required=tuple(f_required)), true


def _decoys(n, seed=1):
	rng = np.random.default_rng(seed)
	out = []
	for k in range(n):
		s = _shape(TRUE_KINDS, deltas=tuple(rng.uniform(-2.0, 2.0, 4)), radii=tuple(rng.uniform(2.4, 3.6, 4)), rot_deg=float(rng.uniform(0, 360)))
		if s.ok:
			out.append(_item(f"D{k}", s))
	return out


CAL = F.FitCalibration(erosion_mm=0.0, chord_cut=1.0, t_abs=None, margin_min=1.5, f_rule=False)


def test_side_orientation_unanimous_and_offender():
	ok = {"A": {"N": 0, "E": 1, "S": 2, "W": 3}, "B": {"N": 2, "E": 3, "S": 0, "W": 1}}
	r = F.side_orientation(ok)
	assert r == {"sigma": 1, "n": 2}
	bad = dict(ok, C={"N": 1, "E": 0, "S": 3, "W": 2})
	assert "error" in F.side_orientation(bad) and "C" in F.side_orientation(bad)["error"]
	assert F.side_orientation({"A": {"N": 1, "E": 0, "S": 3, "W": 2}})["sigma"] == -1
	assert "error" in F.side_orientation({})


def test_true_piece_top1_with_two_and_three_neighbours():
	for dirs in (("N", "E"), ("N", "E", "S")):
		hole, true = _hole(dirs)
		pool = _decoys(25) + [F.FitItem(id="T", shape=_shape(TRUE_KINDS, deltas=(0.8, -0.5, 0.6, -0.9), rot_deg=47.0),
										 sides=None, strips=np.repeat(FLAT[None], 4, 0))]
		pool[-1].sides = list(pool[-1].shape.sides)
		res = F.rank_hole(hole, pool, calib=CAL, sigma=1)
		assert "error" not in res, res
		assert res["candidates"][0]["id"] == "T", (dirs, res["candidates"][:2], res["reasons"])
		assert res["m"] == len(dirs) and res["n_finite"] >= 2
		assert res["confidence"] == "alta", res["reasons"]
		# the pose recovered from the neighbours undoes the 47 deg scan rotation (mod 90 for the symmetric body)
		th = res["candidates"][0]["theta_deg"]
		assert th is not None and abs(((-47.0 - th) + 45) % 90 - 45) < 3.0, th


def test_single_neighbour_is_never_alta():
	hole, _ = _hole(("N",))
	pool = _decoys(25) + [_item("T", _shape(TRUE_KINDS, deltas=(0.8, -0.5, 0.6, -0.9)))]
	res = F.rank_hole(hole, pool, calib=CAL, sigma=1)
	assert res["m"] == 1 and res["confidence"] in ("media", "sem")
	assert any("só uma vizinha" in s for s in res["reasons"])
	assert F.confidence(1, 1.0, 3.0, CAL) == "media" and F.confidence(2, 1.0, 3.0, CAL) == "alta"
	assert F.confidence(2, 1.0, 1.2, CAL) == "media" and F.confidence(1, 1.0, 1.2, CAL) == "sem"
	assert F.confidence(2, None, None, CAL) == "sem" and F.confidence(2, 1.0, None, CAL) == "sem"
	assert F.confidence(2, 2.0, 4.0, F.FitCalibration(t_abs=1.5)) == "sem"


def test_soft_chord_filter_recovers_a_side_that_the_hard_filter_kills():
	hole, _ = _hole(("N", "E", "S"))
	# the true piece, but its top side read 1.4 mm longer than the neighbour's (|dL| > 1.0 tolerance): a trapezoid
	pts = make_piece(TRUE_KINDS, deltas=(0.8, -0.5, 0.6, -0.9), corners=[(0, 0), (18.5 + 1.4, 0), (18.5, 18.5), (0, 18.5)]) * MMPP
	stretched = analyse(pts / MMPP, MMPP)
	assert stretched.ok
	item = _item("T", stretched)
	pool = _decoys(25) + [item]
	hard = F.rank_hole(hole, pool, calib=CAL, sigma=1)
	soft = F.rank_hole(hole, pool, calib=F.FitCalibration(chord_cut=3.0, f_rule=False), sigma=1)
	ids_hard = [e["id"] for e in hard["ranking"]]
	assert "T" not in ids_hard, "with the hard filter the stretched true piece must be infinite"
	assert soft["candidates"][0]["id"] == "T", (soft["candidates"][:2], soft["reasons"])
	pen = [s["pen"] for s in soft["candidates"][0]["per_side"]]
	assert max(pen) > 0 and max(pen) == pytest.approx(F.SOFT_SLOPE_PER_MM * (1.4 - 1.0), abs=0.25)


def test_f_rule_requires_flat_sides_where_the_cell_is_border():
	hole, true = _hole(("E", "S"), f_required=("N",))
	border = _shape("FBTB", deltas=(0.0, -0.5, 0.6, -0.9))      # F on top, the other three complementary
	pool = _decoys(10) + [_item("T", _shape(TRUE_KINDS, deltas=(0.8, -0.5, 0.6, -0.9))), _item("B", border)]
	strict = F.rank_hole(hole, pool, calib=F.FitCalibration(f_rule=True), sigma=1)
	loose = F.rank_hole(hole, pool, calib=CAL, sigma=1)
	assert strict["candidates"][0]["id"] == "B", strict["reasons"]
	assert all(e["id"] != "T" for e in strict["ranking"])            # an interior piece can never fill a border cell
	assert loose["candidates"][0]["id"] == "T"
	# an interior hole rejects a piece with an F side
	interior, _ = _hole(("E", "S"))
	r = F.rank_hole(interior, pool, calib=F.FitCalibration(f_rule=True), sigma=1)
	assert all(e["id"] != "B" for e in r["ranking"])


def test_eroded_sides_shrinks_chords_and_keeps_index_order():
	s = _shape(TRUE_KINDS, deltas=(0.8, -0.5, 0.6, -0.9))
	e = F.eroded_sides(s, 0.48)
	assert e is not None and len(e) == 4
	for a, b in zip(s.sides, e):
		assert a.kind == b.kind
		assert a.chord_mm - b.chord_mm == pytest.approx(2 * 0.48, abs=0.25)
	assert F.eroded_sides(s, 0.0) == list(s.sides)


def test_assign_gives_each_piece_one_hole():
	h1, _ = _hole(("N", "E"))
	h2, _ = _hole(("N", "E"), true_deltas=(0.8, -0.5, 0.6, -0.9))      # the same mould twice: the same piece wins both
	h2.cell = (5, 5)
	pool = _decoys(15) + [_item("T", _shape(TRUE_KINDS, deltas=(0.8, -0.5, 0.6, -0.9))), _item("U", _shape(TRUE_KINDS, deltas=(0.9, -0.4, 0.5, -1.0)))]
	r1 = F.rank_hole(h1, pool, calib=CAL, sigma=1)
	r2 = F.rank_hole(h2, pool, calib=CAL, sigma=1)
	assert r1["candidates"][0]["id"] == "T" and r2["candidates"][0]["id"] == "T"
	out = F.assign([r1, r2])
	assert set(out.values()) == {"T", "U"} and len(out) == 2
	loser = r1 if r1["assigned"] != "T" else r2
	winner = r2 if loser is r1 else r1
	assert loser["candidates"][0]["melhor_para"] == tuple(winner["cell"])
	assert winner["candidates"][0]["melhor_para"] is None


def test_rank_hole_errors_and_exclusions():
	hole, _ = _hole(("N", "E"))
	assert "error" in F.rank_hole(F.HoleQuery(cell=(1, 1), sides=[]), _decoys(3), calib=CAL)
	assert "error" in F.rank_hole(hole, [], calib=CAL)
	assert "error" in F.rank_hole(hole, _decoys(3), calib=CAL, sigma=2)
	pool = _decoys(10) + [_item("T", _shape(TRUE_KINDS, deltas=(0.8, -0.5, 0.6, -0.9)))]
	r = F.rank_hole(hole, pool, calib=CAL, sigma=1, exclude=("T",))
	assert all(e["id"] != "T" for e in r["ranking"]) and "excluídas" in r["reasons"][0]


def test_wilson_and_zone():
	lo, hi = F.wilson(18, 20)
	assert 0.69 < lo < 0.71 and 0.96 < hi < 0.98
	assert all(x != x for x in F.wilson(0, 0))      # nan, nan
	assert F.zone_of((3, 10)) == "céu" and F.zone_of((45, 2)) == "relva" and F.zone_of(None) == "sem posição"
