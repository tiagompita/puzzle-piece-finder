"""Automatic puzzle-piece segmentation from a photo of the board/mat.

Given a single photo containing many pieces spread on a (roughly uniform)
surface, this module detects, splits and crops individual pieces.

Public entry point: :func:`segment_pieces` (pure, PIL in / dict out).
Filesystem wrappers: :func:`segment_pieces_from_file`, :func:`save_pieces`.

Only ``cv2`` + ``numpy`` + ``PIL`` are used. Detection logic is kept pure and
free of filesystem I/O; the two wrapper functions are the only ones that touch
disk. The dict-with-``"error"`` return idiom mirrors ``matching.py``.

Note on the Lab colour space: OpenCV's 8-bit Lab is used throughout, so the
returned ``background_lab`` is on OpenCV's scale (L in 0..255, a/b offset by
128), not the CIE 0..100 / -128..127 scale.
"""

from __future__ import annotations

import os

import cv2
import numpy as np
from PIL import Image


__all__ = [
	"segment_pieces",
	"segment_pieces_from_file",
	"save_pieces",
]


# ===== Touching-piece split tunables (step 8) =====
# Black-hat structuring-element size as a fraction of the working image's long
# side. It must exceed the dark inter-piece seam width so a closing bridges the
# gap, yet stay well under a piece so whole pieces are not swallowed. At the
# default 1600 px working size this is ~19 px, comfortably between a ~2-5 px seam
# and a ~40 px piece side.
_SEAM_KERNEL_FRAC = 0.012
# A black-hat response below this (on the 0..255 luminance scale) is treated as
# seam-free, so uniform crops and flush/interlocked sections yield no barrier and
# their distance transform is left untouched.
_SEAM_MIN_RESPONSE = 12.0


# ===== Pure detection helpers (no I/O) =====
def _to_working(bgr: np.ndarray, max_working_dim: int) -> tuple[np.ndarray, float]:
	"""Downscale ``bgr`` so its longest side is <= ``max_working_dim``.

	Returns ``(working_bgr, working_scale)`` where ``working_scale`` is the
	factor applied (<= 1.0); multiply working coords by ``1/working_scale`` to
	map back to original coords.
	"""
	h, w = bgr.shape[:2]
	long_side = max(h, w)
	if long_side <= max_working_dim:
		return bgr, 1.0
	scale = max_working_dim / float(long_side)
	new_w = max(1, int(round(w * scale)))
	new_h = max(1, int(round(h * scale)))
	work = cv2.resize(bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)
	return work, scale


def _flatten_illumination(L: np.ndarray, sigma: float) -> np.ndarray:
	"""Divide out low-frequency illumination on the L channel.

	``L_flat = L / max(blur(L), eps) * mean(L)`` clipped to 0..255. The heavy
	Gaussian blur is approximated on a downsampled copy for speed (the
	illumination field is low frequency, so this is visually equivalent).
	"""
	L = L.astype(np.float32)
	h, w = L.shape[:2]
	eps = 1e-6
	# Approximate a very large-sigma blur cheaply via down/up sampling.
	target = 200.0
	f = max(1, int(round(max(h, w) / target)))
	if f > 1:
		small = cv2.resize(L, (max(1, w // f), max(1, h // f)), interpolation=cv2.INTER_AREA)
		blur_small = cv2.GaussianBlur(small, (0, 0), sigmaX=max(1.0, sigma / f))
		blur = cv2.resize(blur_small, (w, h), interpolation=cv2.INTER_LINEAR)
	else:
		blur = cv2.GaussianBlur(L, (0, 0), sigmaX=max(1.0, sigma))
	mean_L = float(L.mean())
	flat = L / np.maximum(blur, eps) * mean_L
	return np.clip(flat, 0, 255).astype(np.uint8)


def _border_background(lab: np.ndarray, border_ratio: float) -> np.ndarray:
	"""Per-channel median of a border frame of the Lab image.

	The frame width is ``border_ratio`` of each dimension. Returns a length-3
	float array (L, a, b) modelling the background/surface colour.
	"""
	h, w = lab.shape[:2]
	bw = max(1, int(round(border_ratio * w)))
	bh = max(1, int(round(border_ratio * h)))
	mask = np.zeros((h, w), dtype=bool)
	mask[:bh, :] = True
	mask[-bh:, :] = True
	mask[:, :bw] = True
	mask[:, -bw:] = True
	frame = lab[mask]
	return np.median(frame.astype(np.float32), axis=0)


def _global_background(lab: np.ndarray) -> np.ndarray:
	"""Per-channel median of the whole Lab image (global background fallback).

	Used when the border frame does not sample the working surface (e.g. the
	photo's margins are floor/carpet around the mat). The whole-image median is
	dominated by the most common surface -- the mat -- so it recovers the true
	background even when the frame is misleading. Returns a length-3 float array.
	"""
	flat = lab.reshape(-1, 3).astype(np.float32)
	return np.median(flat, axis=0)


def _weighted_distance(lab: np.ndarray, bg: np.ndarray, luma_weight: float, chroma_weight: float) -> np.ndarray:
	"""Weighted Lab distance to the background, normalised to uint8 0..255."""
	diff = lab.astype(np.float32) - bg.reshape(1, 1, 3)
	dL2 = diff[:, :, 0] ** 2
	dab2 = diff[:, :, 1] ** 2 + diff[:, :, 2] ** 2
	D = np.sqrt(luma_weight * dL2 + chroma_weight * dab2)
	return cv2.normalize(D, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)


def _foreground_from_bg(
	lab: np.ndarray, bg: np.ndarray, luma_weight: float, chroma_weight: float
) -> tuple[np.ndarray, np.ndarray, float]:
	"""Distance map + Otsu binary for one background estimate.

	Returns ``(distance_u8, binary_0_255, foreground_fraction)``. Factored out so
	the border model and the global fallback share identical thresholding.
	"""
	D = _weighted_distance(lab, bg, luma_weight, chroma_weight)
	_, binary = cv2.threshold(D, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
	return D, binary, float((binary > 0).mean())


def _morph_clean(binary: np.ndarray, working_dim: int, max_hole_frac: float = 0.10) -> np.ndarray:
	"""Open -> close -> size-limited hole fill on a 0/255 mask.

	The hole fill only closes enclosed background regions smaller than both the
	total foreground area and ``max_hole_frac`` of the image. This keeps genuine
	within-piece holes (glossy highlights, print gaps) filled while refusing to
	fill the huge mat-interior background that appears on wide board shots: when
	the surrounding floor/carpet forms a closed ring around the mat it
	disconnects the between-piece background from the image border, so a plain
	flood fill from the corner treats ~all of it as one "hole" and merges every
	piece into a single blob. A within-piece hole is contained in one piece, so
	it is always smaller than the union of all pieces (the total foreground);
	the mat background is not, which makes the foreground-area bound a natural,
	self-calibrating discriminator (the image-fraction cap guards denser shots).
	On framed/zoom shots every hole is tiny, so all are still filled -- behaviour
	there is unchanged.
	"""
	k = max(3, int(round(0.003 * working_dim)))
	if k % 2 == 0:
		k += 1
	kern_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
	k2 = k * 2 + 1
	kern_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k2, k2))
	m = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kern_open)
	m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, kern_close)
	# Enclosed background = pixels the corner flood fill cannot reach.
	h, w = m.shape[:2]
	ff = m.copy()
	ff_mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
	cv2.floodFill(ff, ff_mask, (0, 0), 255)
	holes = cv2.bitwise_not(ff)
	# Fill only holes below the smaller of (total foreground) and the image cap.
	fg_area = int((m > 0).sum())
	size_cap = min(fg_area, int(max_hole_frac * h * w))
	num, lab_h, stats_h, _ = cv2.connectedComponentsWithStats((holes > 0).astype(np.uint8), 8)
	if num > 1:
		small = np.nonzero(stats_h[1:, cv2.CC_STAT_AREA] < size_cap)[0] + 1
		if small.size:
			m = cv2.bitwise_or(m, (np.isin(lab_h, small).astype(np.uint8) * 255))
	return m


def _seam_barrier(color_crop: np.ndarray, comp_mask: np.ndarray, working_dim: int, seam_frac: float) -> np.ndarray:
	"""Dark inter-piece gap/shadow inside ``comp_mask`` as a 0/255 barrier.

	When pieces are set down abutting rather than interlocked, a thin dark seam
	(the physical gap plus its cast shadow) runs between them. A morphological
	black-hat on the Lab L channel isolates dark structures thinner than the
	structuring element -- exactly such seams -- while ignoring uniformly dark
	pieces: an all-dark piece has no brighter surround, so its black-hat response
	stays low. This local-contrast behaviour is why black-hat is preferred over an
	absolute low-L threshold, which would flag whole dark-coloured pieces as seam.

	The response is thresholded at ``seam_frac`` of its in-component maximum, gated
	by an absolute floor (``_SEAM_MIN_RESPONSE``) so a seam-free crop returns an
	empty barrier. Used to carve the distance-transform mask so two pieces joined
	only by a thin seam fall into separate watershed basins.
	"""
	L = cv2.cvtColor(color_crop, cv2.COLOR_BGR2LAB)[:, :, 0]
	k = max(9, int(round(_SEAM_KERNEL_FRAC * working_dim)))
	if k % 2 == 0:
		k += 1
	kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
	bh = cv2.morphologyEx(L, cv2.MORPH_BLACKHAT, kern)
	inside = comp_mask > 0
	if not inside.any():
		return np.zeros_like(comp_mask)
	peak = float(bh[inside].max())
	if peak < _SEAM_MIN_RESPONSE:
		return np.zeros_like(comp_mask)
	thr = max(_SEAM_MIN_RESPONSE, seam_frac * peak)
	return ((bh >= thr) & inside).astype(np.uint8) * 255


def _plain_seeds(comp_mask: np.ndarray, marker_ratio: float) -> tuple[np.ndarray, np.ndarray, int] | None:
	"""Distance-transform sure-foreground seeds (no seam), ``(sure_fg, mk, count)``.

	This is the original marker seeding: peaks of the component's own distance
	transform above ``marker_ratio`` * peak. Returns ``None`` for an empty mask.
	"""
	dist = cv2.distanceTransform(comp_mask, cv2.DIST_L2, 5)
	maxd = float(dist.max())
	if maxd <= 0:
		return None
	sure_fg = (dist > marker_ratio * maxd).astype(np.uint8)
	n, mk = cv2.connectedComponents(sure_fg)
	return sure_fg, mk, n - 1


def _seam_seeds(
	comp_mask: np.ndarray, color_crop: np.ndarray, marker_ratio: float, working_dim: int, seam_frac: float
) -> tuple[np.ndarray, np.ndarray, int] | None:
	"""Seam-reinforced seeds: plain seeds with the dark inter-piece seam cut out.

	The distance transform is still taken on the whole component (so its peak and
	the ``marker_ratio`` threshold are exactly the plain ones), and the dark seam
	(:func:`_seam_barrier`) is subtracted from the seed afterwards. Cutting the
	seed along a strong seam can only *split* a seed that the seam runs through, so
	two pieces joined across a thin seam get one marker each. Used only to rescue a
	component the plain seeds could not separate, never to disturb one they could.
	"""
	base = _plain_seeds(comp_mask, marker_ratio)
	if base is None:
		return None
	sure_fg, _, _ = base
	sure_fg = sure_fg.copy()
	barrier = _seam_barrier(color_crop, comp_mask, working_dim, seam_frac)
	sure_fg[barrier > 0] = 0
	n, mk = cv2.connectedComponents(sure_fg)
	return sure_fg, mk, n - 1


def _watershed_from_seeds(
	comp_mask: np.ndarray,
	color_crop: np.ndarray,
	median_area: float,
	seeds: tuple[np.ndarray, np.ndarray, int],
) -> list[np.ndarray] | None:
	"""Cap, watershed and validate one set of seeds into sub-piece masks.

	Returns the sub-masks, or ``None`` if the seeds give fewer than two markers,
	collapse to one region, or yield a fragment below ~0.3*median.
	"""
	comp_area = int((comp_mask > 0).sum())
	sure_fg, mk, markers_count = seeds
	if markers_count < 2:
		return None
	# Cap the number of sub-pieces at the area-implied expectation. This is a
	# ceiling only when markers over-fragment; the area estimate grows with the
	# cluster, so 3+ well-seeded pieces are kept (it does not pin the split at 2).
	cap = max(2, int(round(comp_area / median_area)))
	if markers_count > cap:
		areas = [(lab, int((mk == lab).sum())) for lab in range(1, markers_count + 1)]
		areas.sort(key=lambda t: t[1], reverse=True)
		keep = [lab for lab, _ in areas[:cap]]
		sure_fg = np.isin(mk, keep).astype(np.uint8)
		n, mk = cv2.connectedComponents(sure_fg)
		markers_count = n - 1
		if markers_count < 2:
			return None
	unknown = ((comp_mask > 0) & (sure_fg == 0))
	markers = mk.astype(np.int32) + 1
	markers[unknown] = 0
	cv2.watershed(color_crop, markers)
	subs: list[np.ndarray] = []
	for r in range(2, markers_count + 2):
		region = ((markers == r) & (comp_mask > 0)).astype(np.uint8) * 255
		if int((region > 0).sum()) == 0:
			continue
		subs.append(region)
	if len(subs) < 2:
		return None
	# Revert if watershed produced an implausibly small fragment.
	for s in subs:
		if int((s > 0).sum()) < 0.3 * median_area:
			return None
	return subs


def _split_component(
	comp_mask: np.ndarray,
	color_crop: np.ndarray,
	median_area: float,
	marker_ratio: float,
	working_dim: int,
	seam_frac: float,
) -> list[np.ndarray] | None:
	"""Try to watershed-split one large component into touching pieces.

	``comp_mask`` is a 0/255 crop, ``color_crop`` the matching BGR crop. The plain
	distance-transform split is tried first (identical to the historic behaviour,
	so cleanly separated pieces are untouched); only if it cannot separate the
	component is the dark inter-piece seam brought in to *rescue* a split. This
	ordering guarantees the seam can add splits but never remove one. Returns a
	list of sub-piece masks, or ``None`` to keep the component whole.
	"""
	plain = _plain_seeds(comp_mask, marker_ratio)
	if plain is None:
		return None
	subs = _watershed_from_seeds(comp_mask, color_crop, median_area, plain)
	if subs is not None:
		return subs
	seam = _seam_seeds(comp_mask, color_crop, marker_ratio, working_dim, seam_frac)
	if seam is None:
		return None
	return _watershed_from_seeds(comp_mask, color_crop, median_area, seam)


def _is_cluster_blob(comp_mask: np.ndarray, median_area: float, marker_ratio: float, cluster_ratio: float) -> bool:
	"""Whether a kept component is an irrecoverable (unsplittable) cluster.

	A component still larger than ``cluster_ratio`` * median whose own distance
	transform yields fewer than two separable peaks cannot be confidently split
	into pieces, so it is flagged rather than emitted as one normal piece.
	"""
	if int((comp_mask > 0).sum()) <= cluster_ratio * median_area:
		return False
	plain = _plain_seeds(comp_mask, marker_ratio)
	if plain is None:
		return True
	return plain[2] < 2


def _extract_components(
	binary: np.ndarray,
	work_bgr: np.ndarray,
	*,
	split_touching: bool,
	min_area_ratio: float,
	marker_ratio: float,
	split_trigger: float,
	seam_frac: float,
	cluster_ratio: float,
) -> list[tuple[tuple[int, int, int, int], np.ndarray, bool]]:
	"""Label, prune and (optionally) split into per-piece working masks.

	Returns a list of ``((x, y, w, h), mask_crop, is_cluster)`` in working coords,
	where ``mask_crop`` is a 0/255 uint8 array of the bbox region and
	``is_cluster`` marks a component that stayed too large to be a single piece
	yet could not be confidently split (see :func:`_is_cluster_blob`).
	"""
	h, w = binary.shape[:2]
	working_area = h * w
	working_dim = max(h, w)
	num, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)

	dust = 0.0005 * working_area
	kept: list[int] = []
	for lab in range(1, num):
		if stats[lab, cv2.CC_STAT_AREA] >= dust:
			kept.append(lab)
	if not kept:
		return []

	areas = np.array([stats[lab, cv2.CC_STAT_AREA] for lab in kept], dtype=np.float64)
	median_area = float(np.median(areas))
	if median_area <= 0:
		return []

	survivors = [lab for lab in kept if stats[lab, cv2.CC_STAT_AREA] >= min_area_ratio * median_area]

	out: list[tuple[tuple[int, int, int, int], np.ndarray, bool]] = []
	for lab in survivors:
		x = int(stats[lab, cv2.CC_STAT_LEFT])
		y = int(stats[lab, cv2.CC_STAT_TOP])
		ww = int(stats[lab, cv2.CC_STAT_WIDTH])
		hh = int(stats[lab, cv2.CC_STAT_HEIGHT])
		area = int(stats[lab, cv2.CC_STAT_AREA])
		comp_mask = (labels[y:y + hh, x:x + ww] == lab).astype(np.uint8) * 255
		color_crop = work_bgr[y:y + hh, x:x + ww]

		if split_touching and area > split_trigger * median_area:
			subs = _split_component(comp_mask, color_crop, median_area, marker_ratio, working_dim, seam_frac)
			if subs is not None:
				for sub in subs:
					sx, sy, sw, sh = cv2.boundingRect(sub)
					sub_crop = sub[sy:sy + sh, sx:sx + sw].copy()
					flag = _is_cluster_blob(sub_crop, median_area, marker_ratio, cluster_ratio)
					out.append(((x + sx, y + sy, sw, sh), sub_crop, flag))
				continue
		# Kept whole (split not triggered, or split declined): flag it if it is an
		# irrecoverable cluster. Sub-median blobs early-return False cheaply.
		flag = _is_cluster_blob(comp_mask, median_area, marker_ratio, cluster_ratio) if split_touching else False
		out.append(((x, y, ww, hh), comp_mask, flag))
	return out


def _normalize_angle(ang: float) -> float:
	"""Fold a minAreaRect angle into (-45, 45]."""
	if ang > 45:
		ang -= 90
	elif ang < -45:
		ang += 90
	return ang


def _extract_piece(
	mask_crop: np.ndarray,
	bbox_w: tuple[int, int, int, int],
	inv: float,
	original_rgb: np.ndarray,
	normalize_rotation: bool,
	pad_ratio: float,
) -> dict | None:
	"""Lift one working-resolution mask to a full-res piece record.

	Returns a dict without ``index`` (assigned later), or ``None`` if the piece
	degenerates during extraction.
	"""
	H, W = original_rgb.shape[:2]
	xw, yw, _, _ = bbox_w
	cnts, _ = cv2.findContours(mask_crop, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
	if not cnts:
		return None
	cnt = max(cnts, key=cv2.contourArea)
	cnt_work = cnt.reshape(-1, 2).astype(np.float32) + np.array([xw, yw], dtype=np.float32)
	cnt_orig = np.round(cnt_work * inv).astype(np.int32)
	cnt_orig[:, 0] = np.clip(cnt_orig[:, 0], 0, W - 1)
	cnt_orig[:, 1] = np.clip(cnt_orig[:, 1], 0, H - 1)

	ox, oy, ow, oh = cv2.boundingRect(cnt_orig)
	# Pad the tight bbox slightly, clipped to the image.
	pad = int(round(pad_ratio * max(ow, oh)))
	ox = max(0, ox - pad)
	oy = max(0, oy - pad)
	ow = min(W - ox, ow + 2 * pad)
	oh = min(H - oy, oh + 2 * pad)
	if ow < 2 or oh < 2:
		return None

	local_cnt = cnt_orig - np.array([ox, oy], dtype=np.int32)
	mask_full = np.zeros((oh, ow), dtype=np.uint8)
	cv2.drawContours(mask_full, [local_cnt.reshape(-1, 1, 2)], -1, 255, thickness=cv2.FILLED)
	mask_full = cv2.morphologyEx(mask_full, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

	m = mask_full > 0
	if not m.any():
		return None
	rgb_crop = original_rgb[oy:oy + oh, ox:ox + ow].copy()
	mean_color = rgb_crop[m].mean(axis=0)
	mean_u8 = mean_color.astype(np.uint8)
	area_px = int(m.sum())

	img = rgb_crop.copy()
	img[~m] = mean_u8

	angle = 0.0
	if normalize_rotation and len(local_cnt) >= 5:
		rect = cv2.minAreaRect(local_cnt.astype(np.int32))
		angle = _normalize_angle(float(rect[2]))
		if abs(angle) > 0.5:
			bpad = max(ow, oh)
			fill = tuple(int(c) for c in mean_u8)
			img_p = cv2.copyMakeBorder(img, bpad, bpad, bpad, bpad, cv2.BORDER_CONSTANT, value=fill)
			mask_p = cv2.copyMakeBorder(mask_full, bpad, bpad, bpad, bpad, cv2.BORDER_CONSTANT, value=0)
			center = (rect[0][0] + bpad, rect[0][1] + bpad)
			M = cv2.getRotationMatrix2D(center, angle, 1.0)
			out_size = (img_p.shape[1], img_p.shape[0])
			img_r = cv2.warpAffine(img_p, M, out_size, flags=cv2.INTER_LINEAR, borderValue=fill)
			mask_r = cv2.warpAffine(mask_p, M, out_size, flags=cv2.INTER_NEAREST, borderValue=0)
			ys, xs = np.where(mask_r > 0)
			if len(ys) > 0:
				ty0, ty1 = ys.min(), ys.max() + 1
				tx0, tx1 = xs.min(), xs.max() + 1
				img_r = img_r[ty0:ty1, tx0:tx1]
				mask_r = mask_r[ty0:ty1, tx0:tx1]
				mask_r = (mask_r > 127).astype(np.uint8) * 255
				rm = mask_r > 0
				img_r[~rm] = mean_u8
				img, mask_full = img_r, mask_r
		else:
			angle = 0.0

	return {
		"image": Image.fromarray(img, "RGB"),
		"mask": Image.fromarray(mask_full, "L"),
		"bbox": (int(ox), int(oy), int(ow), int(oh)),
		"area_px": area_px,
		"angle": float(angle),
		"contour": cnt_orig,
	}


def _labels_overlay(work_bgr: np.ndarray, components: list[tuple[tuple[int, int, int, int], np.ndarray, bool]]) -> Image.Image:
	"""Colour each detected component over the working image for inspection.

	Normal pieces are tinted a random colour; irrecoverable clusters are tinted
	solid red so the overlay reflects what the split could and could not separate.
	"""
	rgb = cv2.cvtColor(work_bgr, cv2.COLOR_BGR2RGB).astype(np.float32)
	rng = np.random.default_rng(12345)
	for (x, y, w, h), mask, is_cluster in components:
		color = np.array([255.0, 0.0, 0.0], np.float32) if is_cluster else rng.integers(60, 256, size=3).astype(np.float32)
		region = rgb[y:y + h, x:x + w]
		sel = mask > 0
		region[sel] = 0.5 * region[sel] + 0.5 * color
	return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB")


# ===== Public API =====
def segment_pieces(
	photo: Image.Image,
	*,
	expected_pieces: int | None = None,
	max_working_dim: int = 1600,
	luma_weight: float = 0.4,
	chroma_weight: float = 1.0,
	min_area_ratio: float = 0.25,
	split_touching: bool = True,
	normalize_rotation: bool = True,
	pad_ratio: float = 0.02,
	debug: bool = False,
) -> dict:
	"""Detect and crop individual puzzle pieces from a photo.

	Args:
		photo: PIL image of many pieces on a roughly uniform surface.
		expected_pieces: optional hint (currently informational only).
		max_working_dim: longest side of the internal working copy.
		luma_weight, chroma_weight: weights of the Lab distance to background.
		min_area_ratio: drop components smaller than this * median area.
		split_touching: watershed-split large touching clusters.
		normalize_rotation: rotate each crop to axis-align its min-area rect.
		pad_ratio: padding added around each tight bbox before cropping.
		debug: attach a ``'debug'`` dict of diagnostic PIL images.

	Returns:
		On success ``{'pieces': [...], 'count': int,
		'background_lab': (L, a, b), 'working_scale': float}``; each piece is a
		dict with ``index, image, mask, bbox, area_px, angle, contour,
		is_cluster``. ``is_cluster`` is ``True`` for a blob that could not be
		confidently split into single pieces (such a record also carries
		``piece_type='cluster'``); it is ``False`` on every normal piece. On
		failure ``{'error': str, 'count': 0, ...}`` (mirrors ``matching.py``).
	"""
	# Watershed marker threshold, split trigger, seam sensitivity and the
	# irrecoverable-cluster area ratio are kept as named locals so callers see
	# stable public parameters while these stay tunable internally.
	#   marker_ratio: fraction of the distance-transform peak a pixel must exceed
	#     to seed a marker. Lowered earlier from the nominal 0.5 to 0.4; a fresh
	#     sweep of 0.35/0.40/0.45 on the four real photos kept 0.40 -- both 0.35
	#     (markers merge) and 0.45 (markers fall below threshold) drop the dense
	#     zoom shot from 134 to ~124 splits, while 0.40 matches/exceeds it.
	#   split_trigger: split components larger than this * median area.
	#   seam_frac: keep black-hat seam pixels above this fraction of the crop's
	#     peak response, so only the strongest dark seams cut a seed. The seam is
	#     used only to rescue a component the plain split could not separate, so
	#     this value is deliberately conservative (0.45): on these image-rich
	#     pieces the black-hat also fires on dark printed content, and a rescue
	#     that produced an implausible fragment would be reverted anyway.
	#   cluster_ratio: a kept component above this * median with no separable peak
	#     is flagged is_cluster instead of returned as one normal piece.
	marker_ratio = 0.40
	split_trigger = 1.6
	seam_frac = 0.45
	cluster_ratio = 2.5

	# --- Step 1: PIL -> BGR, working downscale ---
	rgb = np.asarray(photo.convert("RGB"))
	original_rgb = rgb
	bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
	work_bgr, working_scale = _to_working(bgr, max_working_dim)
	inv = 1.0 / working_scale
	wh, ww = work_bgr.shape[:2]
	working_dim = max(wh, ww)

	# --- Step 2: Lab + illumination flattening on L only ---
	lab = cv2.cvtColor(work_bgr, cv2.COLOR_BGR2LAB)
	sigma = working_dim / 8.0
	lab[:, :, 0] = _flatten_illumination(lab[:, :, 0], sigma)

	# --- Steps 3-5: background model, weighted Lab distance, Otsu + failure guard ---
	# The border frame is the PRIMARY background estimate and is correct whenever
	# the frame IS the working surface (framed/zoom shots). On wide shots whose
	# margins are floor/carpet around the mat, the frame samples the wrong surface
	# and the whole mat is mistaken for foreground, so the foreground fraction is
	# implausibly high. Detect that and fall back to a GLOBAL median background
	# (dominated by the mat), redoing the distance + Otsu threshold. Only if both
	# the border model and the global fallback stay implausible do we give up.
	fg_high = 0.60
	fg_low = 0.005

	bg = _border_background(lab, border_ratio=0.02)
	background_model = "border"
	D, binary_raw, fg_frac = _foreground_from_bg(lab, bg, luma_weight, chroma_weight)

	if fg_frac > fg_high:
		bg = _global_background(lab)
		background_model = "global"
		D, binary_raw, fg_frac = _foreground_from_bg(lab, bg, luma_weight, chroma_weight)

	base = {
		"count": 0,
		"background_lab": (float(bg[0]), float(bg[1]), float(bg[2])),
		"background_model": background_model,
		"working_scale": float(working_scale),
	}
	if fg_frac > fg_high or fg_frac < fg_low:
		result = {"error": "segmentation_failed", **base}
		if debug:
			result["debug"] = {
				"background_model": background_model,
				"distance_map": Image.fromarray(D, "L"),
				"binary_mask": Image.fromarray(binary_raw, "L"),
				"labels_overlay": Image.fromarray(cv2.cvtColor(work_bgr, cv2.COLOR_BGR2RGB), "RGB"),
			}
		return result

	# --- Step 6: morphology (open -> close -> fill holes) ---
	binary = _morph_clean(binary_raw, working_dim)

	# --- Steps 7 & 8: label, prune, split touching ---
	components = _extract_components(
		binary,
		work_bgr,
		split_touching=split_touching,
		min_area_ratio=min_area_ratio,
		marker_ratio=marker_ratio,
		split_trigger=split_trigger,
		seam_frac=seam_frac,
		cluster_ratio=cluster_ratio,
	)

	if not components:
		result = {"error": "no_pieces_found", **base}
		if debug:
			result["debug"] = {
				"background_model": background_model,
				"distance_map": Image.fromarray(D, "L"),
				"binary_mask": Image.fromarray(binary, "L"),
				"labels_overlay": _labels_overlay(work_bgr, components),
			}
		return result

	# --- Steps 9, 10, 11: full-res extraction, rotation, compose ---
	pieces: list[dict] = []
	for bbox_w, mask_crop, is_cluster in components:
		rec = _extract_piece(mask_crop, bbox_w, inv, original_rgb, normalize_rotation, pad_ratio)
		if rec is not None:
			rec["is_cluster"] = bool(is_cluster)
			if is_cluster:
				# Note: edges.classify_pieces (if run downstream) overwrites
				# piece_type; is_cluster is the reliable cluster flag.
				rec["piece_type"] = "cluster"
			pieces.append(rec)

	if not pieces:
		result = {"error": "no_pieces_found", **base}
		if debug:
			result["debug"] = {
				"background_model": background_model,
				"distance_map": Image.fromarray(D, "L"),
				"binary_mask": Image.fromarray(binary, "L"),
				"labels_overlay": _labels_overlay(work_bgr, components),
			}
		return result

	# --- Step 12: reading-order sort ---
	bbox_hs = np.array([p["bbox"][3] for p in pieces], dtype=np.float64)
	median_h = float(np.median(bbox_hs))
	row_h = max(1.0, 0.75 * median_h)

	def _sort_key(p: dict) -> tuple[int, int]:
		x, y, w, h = p["bbox"]
		cx = x + w / 2.0
		cy = y + h / 2.0
		return (int(round(cy / row_h)), int(round(cx)))

	pieces.sort(key=_sort_key)
	for i, p in enumerate(pieces):
		p["index"] = i

	result = {
		"pieces": pieces,
		"count": len(pieces),
		"background_lab": (float(bg[0]), float(bg[1]), float(bg[2])),
		"background_model": background_model,
		"working_scale": float(working_scale),
	}
	if debug:
		result["debug"] = {
			"background_model": background_model,
			"distance_map": Image.fromarray(D, "L"),
			"binary_mask": Image.fromarray(binary, "L"),
			"labels_overlay": _labels_overlay(work_bgr, components),
		}
	return result


# ===== Filesystem wrappers (only functions doing I/O) =====
def segment_pieces_from_file(path: str, **kwargs) -> dict:
	"""Open an image from ``path`` and run :func:`segment_pieces`.

	Adds ``'source_path'`` to the returned dict. All keyword arguments are
	forwarded to :func:`segment_pieces`.
	"""
	with Image.open(path) as im:
		im.load()
		result = segment_pieces(im, **kwargs)
	result["source_path"] = path
	return result


def save_pieces(pieces: list[dict], out_dir: str, prefix: str = "piece_") -> list[str]:
	"""Write each piece as an RGBA PNG (alpha = mask, RGB = mean-filled crop).

	Returns the list of written file paths, ordered by piece ``index``.
	"""
	os.makedirs(out_dir, exist_ok=True)
	paths: list[str] = []
	ordered = sorted(pieces, key=lambda p: p.get("index", 0))
	for p in ordered:
		rgb = p["image"].convert("RGB")
		alpha = p["mask"].convert("L")
		rgba = rgb.copy()
		rgba.putalpha(alpha)
		out_path = os.path.join(out_dir, f"{prefix}{p.get('index', 0)}.png")
		rgba.save(out_path)
		paths.append(out_path)
	return paths
