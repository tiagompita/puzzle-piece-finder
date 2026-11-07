"""Comparison of two silhouettes (binary masks) in the same pixel frame, in mm.

Used to measure a segmented / displayed silhouette against a hand-cut ground-truth mask
(``docs/diagnostico/segmentacao/COMIDO.md``) and, later, the automatic contour against the manual
one of every override (``src.overrides``). Pure numpy/OpenCV, no I/O.

Conventions: masks are boolean arrays of the same shape (whole scan or a common window);
``mm_per_px`` is the scan scale (0.0847 at 300 dpi). "Missing" is ground truth that the
candidate does not cover (a bite); "excess" is candidate outside the ground truth (halo, shadow).
A global RMS such as :func:`src.shape.free_dist` hides a local bite; the depth and the per-pixel
boundary distances here do not.
"""

from typing import Optional

import cv2
import numpy as np

__all__ = [
	"boundary", "fill_contour", "mask_metrics", "best_shift", "crop_union", "depth_max_mm", "nearest_side",
]


def fill_contour(contour_px, shape) -> np.ndarray:
	"""Boolean mask of ``shape`` with the closed polygon ``contour_px`` (x, y px) filled."""
	m = np.zeros(shape[:2], np.uint8)
	pts = np.asarray(contour_px, float).round().astype(np.int32).reshape(-1, 1, 2)
	if len(pts) >= 3:
		cv2.fillPoly(m, [pts], 1)
	return m > 0


def boundary(mask: np.ndarray) -> np.ndarray:
	"""Inner boundary pixels of a boolean mask (4-connected erosion difference)."""
	m = mask.astype(np.uint8)
	k = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
	return (m - cv2.erode(m, k)) > 0


def crop_union(*masks, pad: int = 8):
	"""Slice covering the union of the masks plus ``pad`` px, clipped to the frame."""
	u = np.zeros(masks[0].shape, bool)
	for m in masks:
		u |= m
	ys, xs = np.nonzero(u)
	if len(ys) == 0:
		return slice(0, 0), slice(0, 0)
	h, w = u.shape
	return (slice(max(0, ys.min() - pad), min(h, ys.max() + pad + 1)),
			slice(max(0, xs.min() - pad), min(w, xs.max() + pad + 1)))


def _dist_to(mask_px: np.ndarray) -> np.ndarray:
	"""Euclidean distance (px) from every pixel to the nearest True pixel of ``mask_px``."""
	if not mask_px.any():
		return np.full(mask_px.shape, np.inf, np.float32)
	return cv2.distanceTransform((~mask_px).astype(np.uint8), cv2.DIST_L2, 5)


def depth_max_mm(region: np.ndarray, reference: np.ndarray, mm_per_px: float) -> float:
	"""Deepest point of ``region`` measured from ``reference`` (px → mm): the depth of a bite
	(region = gt & ~cand, reference = cand) or of a halo (region = cand & ~gt, reference = gt)."""
	if not region.any():
		return 0.0
	d = _dist_to(reference)
	return float(d[region].max() * mm_per_px)


def mask_metrics(gt: np.ndarray, cand: np.ndarray, mm_per_px: float, *, window: bool = True) -> dict:
	"""Metrics of ``cand`` against ``gt`` (same shape).

	Returns ``iou``, ``gt_mm2``, ``cand_mm2``, ``missing_mm2`` (gt \\ cand), ``excess_mm2``
	(cand \\ gt), ``missing_depth_mm`` / ``excess_depth_mm`` (deepest point of each difference),
	and the symmetric boundary distances in mm: ``d_mean``, ``d_p95``, ``d_max`` over the boundary
	pixels of both masks (each to the other's boundary), plus the one-way ``cand_to_gt_*`` and
	``gt_to_cand_*``. Empty masks give NaN distances.
	"""
	gt = gt.astype(bool)
	cand = cand.astype(bool)
	if window:
		sl = crop_union(gt, cand)
		gt, cand = gt[sl], cand[sl]
	px2 = mm_per_px * mm_per_px
	inter = float((gt & cand).sum())
	union = float((gt | cand).sum())
	missing = gt & ~cand
	excess = cand & ~gt
	out = {
		"iou": inter / union if union else 0.0,
		"gt_mm2": float(gt.sum()) * px2,
		"cand_mm2": float(cand.sum()) * px2,
		"missing_mm2": float(missing.sum()) * px2,
		"excess_mm2": float(excess.sum()) * px2,
		"missing_depth_mm": depth_max_mm(missing, cand, mm_per_px),
		"excess_depth_mm": depth_max_mm(excess, gt, mm_per_px),
	}
	bg, bc = boundary(gt), boundary(cand)
	if bg.any() and bc.any():
		dg = _dist_to(bg)[bc] * mm_per_px      # cand boundary → gt boundary
		dc = _dist_to(bc)[bg] * mm_per_px      # gt boundary → cand boundary
		both = np.concatenate([dg, dc])
		for name, d in (("cand_to_gt", dg), ("gt_to_cand", dc), ("d", both)):
			out[f"{name}_mean"] = float(d.mean())
			out[f"{name}_p95"] = float(np.percentile(d, 95))
			out[f"{name}_max"] = float(d.max())
	else:
		for name in ("cand_to_gt", "gt_to_cand", "d"):
			out[f"{name}_mean"] = out[f"{name}_p95"] = out[f"{name}_max"] = float("nan")
	return out


def best_shift(gt: np.ndarray, cand: np.ndarray, radius: int = 3) -> tuple:
	"""Integer translation ``(dx, dy)`` of ``cand`` (|d| ≤ radius) that maximises IoU, and that IoU.
	Used to check that two sheets share the same pixel grid (expected (0, 0))."""
	gt = gt.astype(bool)
	cand = cand.astype(bool)
	sl = crop_union(gt, cand, pad=radius + 2)
	gt, cand = gt[sl], cand[sl]
	best: Optional[tuple] = None
	for dy in range(-radius, radius + 1):
		for dx in range(-radius, radius + 1):
			c = np.roll(np.roll(cand, dy, axis=0), dx, axis=1)
			u = float((gt | c).sum())
			iou = float((gt & c).sum()) / u if u else 0.0
			if best is None or iou > best[2] + 1e-12:
				best = (dx, dy, iou)
	return best


def nearest_side(points, contour, corners) -> np.ndarray:
	"""Side index (0..3) of the contour point nearest to each of ``points`` (``(n, 2)``, same units).

	``contour`` is the closed polygon ``(m, 2)``; ``corners`` the 4 increasing indices of its corners:
	side ``i`` spans ``corners[i] .. corners[i + 1]`` (side 3 wraps to ``corners[0]``). Used to charge
	each pixel of a mask difference to the side of the piece it lies on. Brute force in chunks.
	"""
	pts = np.asarray(points, np.float64).reshape(-1, 2)
	c = np.asarray(contour, np.float64).reshape(-1, 2)
	k = np.asarray(corners, int).reshape(-1)
	if len(k) != 4 or len(c) == 0:
		raise ValueError("nearest_side: 4 corners and a non-empty contour required")
	side_of = np.full(len(c), 3, np.int64)
	for i in range(3):
		side_of[k[i]:k[i + 1]] = i
	side_of[k[3]:] = 3
	side_of[:k[0]] = 3
	out = np.empty(len(pts), np.int64)
	for s0 in range(0, len(pts), 4096):
		q = pts[s0:s0 + 4096]
		d2 = ((q[:, None, :] - c[None, :, :]) ** 2).sum(-1)
		out[s0:s0 + 4096] = side_of[np.argmin(d2, 1)]
	return out
