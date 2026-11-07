import numpy as np

from src import maskcmp as M

MMPP = 0.0846667


def _square(shape=(200, 200), x0=50, y0=50, side=100):
	m = np.zeros(shape, bool)
	m[y0:y0 + side, x0:x0 + side] = True
	return m


def test_identical_masks():
	gt = _square()
	r = M.mask_metrics(gt, gt, MMPP)
	assert r["iou"] == 1.0
	assert r["missing_mm2"] == 0.0 and r["excess_mm2"] == 0.0
	assert r["missing_depth_mm"] == 0.0 and r["d_max"] == 0.0


def test_bite_is_missing_with_depth_not_hidden_by_mean():
	gt = _square()
	cand = gt.copy()
	cand[50:74, 50:74] = False          # 24 px bite in a corner (≈ 2 mm)
	r = M.mask_metrics(gt, cand, MMPP)
	assert r["excess_mm2"] == 0.0
	assert abs(r["missing_mm2"] - 24 * 24 * MMPP * MMPP) < 1e-6
	assert 1.9 < r["missing_depth_mm"] < 2.2          # corner of the bite is ~24*sqrt(2)/... >= 24 px from kept mask
	assert r["d_max"] > 1.5 and r["d_mean"] < 0.5    # local bite: max large, mean small


def test_halo_is_excess():
	gt = _square()
	cand = _square(x0=44, y0=44, side=112)             # 6 px halo all around
	r = M.mask_metrics(gt, cand, MMPP)
	assert r["missing_mm2"] == 0.0
	assert r["excess_mm2"] > 0
	assert 6 * MMPP <= r["excess_depth_mm"] <= 6 * 1.5 * MMPP   # deepest point is the halo corner (6*sqrt2 px)
	assert abs(r["d_mean"] - 6 * MMPP) < 2 * MMPP


def test_best_shift_recovers_translation():
	gt = _square()
	cand = np.roll(np.roll(gt, 2, axis=0), -1, axis=1)
	dx, dy, iou = M.best_shift(gt, cand, radius=3)
	assert (dx, dy) == (1, -2) and iou == 1.0


def test_fill_contour_and_boundary():
	c = [[10, 10], [60, 10], [60, 40], [10, 40]]
	m = M.fill_contour(c, (50, 80))
	assert m.sum() == 51 * 31
	b = M.boundary(m)
	assert b.sum() == 2 * 51 + 2 * 31 - 4


def test_nearest_side_charges_points_to_their_side():
	# square 0..100, corners TL, TR, BR, BL -> sides 0 = top, 1 = right, 2 = bottom, 3 = left
	top = [[x, 0] for x in range(0, 100)]
	right = [[100, y] for y in range(0, 100)]
	bottom = [[x, 100] for x in range(100, 0, -1)]
	left = [[0, y] for y in range(100, 0, -1)]
	c = np.array(top + right + bottom + left, float)
	corners = [0, 100, 200, 300]
	pts = [[50, -3], [104, 40], [60, 98], [2, 55], [50, 2]]
	assert M.nearest_side(pts, c, corners).tolist() == [0, 1, 2, 3, 0]
