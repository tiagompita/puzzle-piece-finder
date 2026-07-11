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
	"piece_to_rgba",
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
# A component above this * median area is almost certainly >=2 pieces, so when both
# the plain and seam watersheds leave it whole (a seam too weak for either) a third,
# FORCED bisection is attempted: :func:`_forced_bisect` cuts it at its narrowest
# distance-transform waist, provided the two peaks are tall and well separated enough
# to be two piece centres. Set above ``split_trigger`` so only clearly over-sized
# blobs are ever forced; single pieces never reach it. The bisection is accepted only
# when BOTH halves look single (each <= split_trigger * median), so a >2-piece cluster
# -- whose halves stay over-sized -- is left whole and flagged, not shredded.
_FORCE_SPLIT_RATIO = 1.8
# A watershed split can hand back a sub that is itself still two fused pieces (a
# 3-piece cluster seeding as [pair, single], say). Each over-sized sub is therefore
# re-split, up to this recursion depth, so those residual pairs are separated too.
_MAX_SPLIT_DEPTH = 3
# A component between this and ``cluster_ratio`` * median that the normal split left
# whole is most often TWO near-but-unconnected pieces the closing bridged across a
# pale (background-coloured) gap: the colour watershed cannot cut it -- the pieces
# are often similar-hued so the seam has no colour edge -- and the dark-seam blackhat
# does not fire on a light gap, so the blob is emitted as one over-sized "piece". Such
# a mid-sized blob is given a final geometric bisection (:func:`_forced_bisect` on the
# distance transform, which cuts at the thin waist regardless of colour) even when it
# sits below ``split_trigger``. The cut is accepted only when BOTH halves look single
# (each <= ``split_trigger`` * median), so a single piece -- one distance peak, hence
# no bisection -- and a genuine cluster -- halves stay over-sized, or area exceeds
# ``cluster_ratio`` and it is flagged instead -- are left untouched. This only ever
# ADDS 2-piece splits; it never merges or shreds.
_BISECT_MIN_RATIO = 1.25


# ===== Seam-carve split tunables (abutting pieces joined by a dark physical seam) =====
# When pieces are set down ABUTTING, the card backs are one uniform colour so a colour
# watershed leaks basins across the seam and into the background (low-solidity garbage);
# the reliable signal is instead the dark physical SEAM between them (black-hat peaks far
# above the seam floor). Seam-carve is attempted FIRST, and only when the in-component
# black-hat peak reaches this multiple of _SEAM_MIN_RESPONSE -- a strong seam marks >=2
# abutting pieces, whereas interlocked/flush blobs (handled by the plain/colour path or
# _forced_bisect) show no such seam. At the floor 12 this fires at a peak >= 36; real
# seams measure ~200+.
_SEAM_CARVE_TRIGGER = 3.0
# The carve barrier uses a RELAXED threshold -- max(_SEAM_MIN_RESPONSE, this * peak) --
# well below _seam_barrier's 0.45*peak, so weak sections of the seam are still cut and the
# two piece bodies separate cleanly into their own carved cores.
_SEAM_CARVE_THR_FRAC = 0.20
# A connected component of the carved (seam-removed) mask seeds a piece marker only when
# its area reaches this fraction of the median piece area, so seam speckle spawns no
# spurious markers.
_SEAM_MARKER_MIN_FRAC = 0.25
# Validation (a): the median black-hat response along an accepted internal boundary must
# reach this fraction of the carve threshold -- a real inter-piece seam is dark ALL along
# the cut, unlike a blank (continuous card, no dark line).
_SEAM_BOUNDARY_SEAM_FRAC = 0.5
# Validation (b): a boundary endpoint counts as landing on a concavity when a qualifying
# convexity defect of the component contour lies within this many working px of it. A neck
# between two pieces ends in two facing concavities; a single piece's own blank does not.
_SEAM_CONCAVITY_TOL_PX = 6
# A convexity defect qualifies as a real inter-piece neck (not contour ripple) when its
# depth reaches this fraction of the median piece side.
_SEAM_CONCAVITY_DEPTH_FRAC = 0.10
# Plausibility floor on a split sub's SOLIDITY (area / convex-hull area). Data-grounded on
# the 11 backgrounds: genuine pieces -- including 4-tab pieces whose hull bridges all four
# tabs -- measure >=0.62, while leaked multi-piece / background-bled blobs collapse to
# <=0.55. 0.55 therefore accepts every real piece with margin and rejects the leak. NOTE:
# a jigsaw piece's tabs/blanks bound its solidity well below 1 (a clean 2-tab/2-blank
# piece tops out ~0.81), so this is a garbage floor, NOT a "near-solid" target.
_SUB_SOLIDITY_MIN = 0.55
# A split sub's area must fall in this window (fraction of median) to be a single piece:
# below is a fragment, above is still >=2 fused pieces.
_SUB_AREA_LO = 0.5
_SUB_AREA_HI = 1.6


# ===== Non-piece component rejection tunables (step 7) =====
# A component whose bounding box reaches within this fraction of the working long
# side of the image frame is the photo margin or a crease/fold between backing
# sheets, not a piece: real pieces sit inset on the surface. Such components are
# rejected outright (see :func:`_extract_components`). At 1600 px this is ~6 px.
_FRAME_MARGIN_FRAC = 0.004
# Jigsaw pieces are near-square: even a rotated piece with tabs rarely exceeds a
# ~2:1 bounding box. A component whose bbox long/short side ratio exceeds this is
# a thin sliver (border strip, seam/crease shadow), not a piece. Kept deliberately
# loose (4:1) so irregular or rotated real pieces are never dropped.
_MAX_BBOX_ASPECT = 4.0
# The bbox-aspect test above misses a DIAGONAL line (a sheet crease/fold or scanner
# streak): its bounding box is near-square, so it escapes as a phantom "piece". Such a
# line is instead caught by its STROKE WIDTH. The distance transform's peak is half the
# widest local thickness, so ``2 * max(DT)`` is the widest stroke; a real piece's body
# is ~a piece-side thick (ratio ~1 against ``sqrt(median_area)``) even when a tab neck is
# thin, whereas a line's stroke is a small fraction of a piece side. A component whose
# stroke falls below this fraction of the median piece side is rejected as a line/crease.
# Set well under 1 (a genuine small piece near the min-area floor still strokes ~0.5) yet
# well above a thin line's ratio, so no real piece is dropped. Measured across the 11
# backgrounds the thinnest genuine component strokes ~0.23 while a real crease/line
# strokes ~0.05, so 0.20 sits in the wide gap between them -- it drops any true line
# without ever reaching a real piece.
_MIN_STROKE_FRAC = 0.20


# ===== Edge-shadow halo removal tunables (step 9, _extract_piece) =====
# Segmented pieces carry a thin, desaturated blue/grey cast-shadow halo on the
# INTERIOR rim of the mask (most visible hugging the tabs). Left in place it feeds
# out-of-artwork colour into the crop and a FALSE border gradient that would
# contaminate downstream edge/texture (Sobel-on-L) analysis, so the mask is shrunk
# inward before any colour or fill is derived. This is the fraction of the piece's
# long side used as the erosion radius bounding the interior rim that may be peeled.
# 0.0 disables the shrink entirely.
_EDGE_SHRINK_FRAC = 0.015
# Never shrink a piece whose long side is below this (px): the rim band would be a
# large fraction of a tiny piece and risk eating real content.
_EDGE_SHRINK_MIN_SIDE = 40
# Back off the whole shrink if peeling the shadow would drop the mask below this
# fraction of its original area (guard against over-eroding thin/narrow pieces).
_EDGE_SHRINK_MIN_AREA_KEEP = 0.70
# The thin _EDGE_SHRINK_FRAC rim only reaches shadow within ~r of the edge, but the
# desaturated navy shadow that pools INSIDE concave tab notches runs deeper and
# survived. This wider boundary band (fraction of the long side) is scanned for
# shadow too; removal stays gated on the SAME conjunctive test (clearly darker AND
# lower-chroma than the interior), so dark-but-saturated artwork and neutral/grey
# pieces -- whose rim is not both darker and greyer than their core -- are still
# spared, and the _EDGE_SHRINK_MIN_AREA_KEEP floor still bounds total removal.
_SHADOW_BAND_FRAC = 0.06
# A band pixel counts as shadow only when at least this much darker (OpenCV 8-bit L,
# 0..255) than the interior median -- "clearly darker", not marginally so -- which
# spares faintly-shaded genuine content the deeper band now reaches.
_SHADOW_L_DELTA = 10.0
# The conjunctive test also fires on isolated dark speckle scattered through the deep
# band, and peeling that speckle moth-eats a ragged mask edge (itself a false border
# gradient). An opening of this radius (fraction of the long side) is applied to the
# shadow mask first, so only contiguous crescents -- the real cast shadow -- survive
# to be peeled and the boundary stays smooth. 0.0 disables the opening.
_SHADOW_OPEN_FRAC = 0.012


# ===== Boundary normal-profile refinement tunables (step 2, _extract_piece) =====
# Each per-piece mask is seeded from the DOWNSCALED working contour (one full-res pixel
# is ~inv working px), so its boundary carries a coarse staircase (step ~= inv) dotted
# with micro-loops. :func:`_refine_boundary_band` re-snaps that boundary to the true
# colour edge in the full-res crop: it Gaussian-smooths the contour to erase the
# staircase/loops, then slides each point along its local normal to the 50% crossing of
# the background-distance profile. These constants tune that snap.
# Half-width (px) of the normal sampling window on either side of the contour.
_REFINE_BAND_PX = 8
# Hard clamp (px) on any single point's offset: the working mask already sits within a
# quantization step of the truth, so the real edge is never more than a few px away; a
# larger "crossing" is glare/printed-content noise and is capped.
_REFINE_CLAMP_PX = 6.0
# Gaussian sigma (in contour points ~= px at full-res 1px sampling) used to pre-smooth
# the contour BEFORE normals are taken and as the BASE the offsets are applied to. It
# must exceed the staircase period (~inv px) to erase it yet stay far below a tab's
# scale so tab tips are not rounded: 6 clears a ~5px step with sub-px rounding of a
# >=30px-radius tab tip.
_REFINE_CONTOUR_SIGMA = 6.0
# Crossing level between the "outside" and "inside" background-distance medians: 0.5
# puts the boundary at the half-contrast point, the natural colour edge. Module-level
# constant (not a caller knob) per the boundary-precision plan.
_REFINE_EDGE_BIAS = 0.5
# Contrast gate: a point whose local |inside - outside| background-distance separation
# falls below this keeps offset 0, so the smoothing still de-staircases it but no colour
# edge is invented. On the weighted-Lab distance scale (luma_weight ~0.075,
# chroma_weight ~1.0, CIE Lab units) a coloured piece sits ~10-40 above its surround, so
# 6 -- about half the smallest genuine gap -- zeroes only near-background-coloured rims
# (e.g. a pale piece edge on a pale mat), which is what makes the refinement a no-op on
# low-separation/white backgrounds.
_REFINE_CONTRAST_FLOOR = 6.0
# The raw offset function is denoised along the contour before it is applied: a circular
# median (this window, in points) kills isolated spikes, then a light circular Gaussian
# (this sigma) removes residual ripple, without distorting the slow variation a tab
# imposes.
_REFINE_OFFSET_MEDIAN = 31
_REFINE_OFFSET_SIGMA = 5.0
# Too few contour points to smooth/normal reliably -> skip refinement, keep the mask.
_REFINE_MIN_POINTS = 64


# ===== Foreground hysteresis tunables (step 5, _foreground_from_bg) =====
# A single global Otsu on the background-distance map D carves the low-D reflection
# blotches out of glossy/metallic pieces (a metallic piece mirrors the surface, so D
# collapses toward background inside those patches) -- the mask develops bites on the
# contour that the interior-hole fill downstream cannot repair (they open onto the
# boundary). Foreground is therefore taken by a two-level hysteresis on D, keeping only
# the low-level components anchored by a high-level "core" pixel (see
# :func:`_foreground_from_bg`).
# HIGH factor multiplies the Otsu threshold to set the core. Held at 1.0 so the core IS
# the historic Otsu mask: pieces that already segmented well keep their exact body and
# cannot regress -- the hysteresis only ever ANNEXES weak-contrast pixels onto it.
_HYST_HIGH_FACTOR = 1.0
# LOW factor multiplies Otsu to set the candidate (annex) level. Calibrated on the two
# real photos (IMG_2129 blue background, Otsu t~93 on the 0..255 MINMAX-normalised D;
# IMG_2114). A metallic piece MIRRORS the blue surface, so D over its body collapses
# toward background and single-Otsu leaves it ~half-detected with deep boundary bites;
# the low level reconnects those weak-contrast patches to the core and recovers the whole
# piece. The value is bounded below by FUSION, not by shadow: because cast shadow is
# chroma-neutral it stays far under any level tried here (raising thr_low never lets
# shadow back in), but a fully-recovered metallic piece comes into genuine contact with
# its neighbours, so too low a level lets adjacent pieces bridge into one blob faster than
# the watershed splitter re-separates them. Measured on IMG_2114 the piece count collapses
# 68->63 at 0.80 (new fusions) and holds exactly 68->68 at 0.85; on IMG_2129 the sample
# metallic piece is only ~14% recovered at 0.95 but fully recovered (+58% area, clean
# contour) at 0.85 with the touching pair still split. 0.85 is thus the loosest level that
# recovers the reflective bodies with NO new fusion. Must stay < _HYST_HIGH_FACTOR for the
# hysteresis to have any effect.
_HYST_LOW_FACTOR = 0.85


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
	"""Distance map + hysteresis-with-connectivity binary for one background estimate.

	Returns ``(distance_u8, binary_0_255, foreground_fraction)``. Factored out so
	the border model and the global fallback share identical thresholding.

	The foreground is a two-level (hysteresis) threshold on the background-distance
	map ``D``, ANCHORED on Otsu so pieces that already segmented cleanly do not move:

	  * HIGH level ``_HYST_HIGH_FACTOR * t_otsu`` -> the high-confidence ``core``.
	    At factor 1.0 this is exactly the old single-Otsu mask, so the core is the
	    solid body every piece already had.
	  * LOW level ``_HYST_LOW_FACTOR * t_otsu`` -> weak-contrast ``candidates`` that
	    include a piece's low-``D`` blotches (e.g. a metallic piece reflecting the
	    background, where ``D`` dips far below the body).

	Only the connected components of ``candidates`` that CONTAIN a ``core`` pixel are
	kept. A reflection blotch is physically continuous with the piece body, so its
	candidate component reaches a core pixel and is recovered; a background shadow is
	separated from every core by a moat of sub-low-level pixels, so its component
	holds no core pixel and is discarded. Because the kept set always contains every
	core pixel, the result can only GROW versus the old Otsu mask -- high-contrast
	pieces (whose whole body is already core, with no weak-contrast neighbourhood to
	annex) are essentially unchanged, bounding regression by construction.
	"""
	D = _weighted_distance(lab, bg, luma_weight, chroma_weight)
	t_otsu, _ = cv2.threshold(D, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
	thr_high = _HYST_HIGH_FACTOR * t_otsu
	thr_low = _HYST_LOW_FACTOR * t_otsu
	core = D >= thr_high
	cand = (D >= thr_low).astype(np.uint8)
	# Hysteresis by connectivity: keep only candidate components anchored by a core
	# pixel. core is a subset of cand (thr_low <= thr_high), so every core pixel has a
	# positive label and ``keep`` is exactly the core-touching components.
	num, labels = cv2.connectedComponents(cand, connectivity=8)
	keep = np.unique(labels[core]) if num > 1 else np.array([], dtype=labels.dtype)
	keep = keep[keep > 0]
	binary = np.isin(labels, keep).astype(np.uint8) * 255
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


def _solidity(mask: np.ndarray) -> float:
	"""Filled area / convex-hull area of a 0/255 mask (0.0 if degenerate).

	A jigsaw piece's tabs and blanks bound its solidity well below 1: a clean
	2-tab/2-blank piece measures ~0.8 and a 4-tab piece ~0.62 (its hull bridges all
	four tabs), while a leaked multi-piece / background-bled blob collapses to <=0.55.
	Solidity is thus a reliable single-piece-vs-garbage discriminator (see
	``_SUB_SOLIDITY_MIN``). Pure; takes only the largest external contour.
	"""
	m = (mask > 0).astype(np.uint8)
	area = int(m.sum())
	if area == 0:
		return 0.0
	cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
	if not cnts:
		return 0.0
	hull_area = float(cv2.contourArea(cv2.convexHull(max(cnts, key=cv2.contourArea))))
	if hull_area <= 0.0:
		return 0.0
	return area / hull_area


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


def _forced_bisect(comp_mask: np.ndarray, median_area: float) -> list[np.ndarray] | None:
	"""Geometrically bisect a component at its narrowest waist (last resort).

	For an over-sized component both the plain and seam watersheds left whole (a
	seam too weak for either), the two piece bodies still show as two distance-
	transform peaks separated by a thinner neck -- the physical join of two pieces
	set down interlocked or flush. This cuts there directly: it seeds the two
	dominant peaks and runs the watershed on the (inverted) distance transform
	rather than colour, so the basins meet on the neck ridge and cover the whole
	component -- robust where a colour watershed lets the near-background piece
	colour bleed the outside marker inward. Accepted ONLY when the second peak is
	tall (not a rim ripple) AND the two centres are far enough apart to be two
	pieces; otherwise ``None``. Returns two 0/255 sub-masks, or ``None``.
	"""
	dist = cv2.distanceTransform(comp_mask, cv2.DIST_L2, 5)
	maxd = float(dist.max())
	if maxd <= 0:
		return None
	# Expected single-piece geometry implied by the median area.
	side = float(np.sqrt(median_area))
	radius = float(np.sqrt(median_area / np.pi))
	# Global peak, then blank a piece-radius disc around it and find the next peak.
	_, _, _, loc1 = cv2.minMaxLoc(dist)
	p1 = (int(loc1[0]), int(loc1[1]))  # (x, y)
	dist2 = dist.copy()
	cv2.circle(dist2, p1, max(1, int(round(radius))), 0.0, -1)
	if float(dist2.max()) <= 0:
		return None
	_, _, _, loc2 = cv2.minMaxLoc(dist2)
	p2 = (int(loc2[0]), int(loc2[1]))  # (x, y)
	d1 = float(dist[p1[1], p1[0]])
	d2 = float(dist[p2[1], p2[0]])
	# Reject unless the second peak is tall and the two centres well separated: a
	# single piece has one dominant peak, so a low or nearby second peak is a ripple.
	if d2 < 0.4 * d1:
		return None
	if float(np.hypot(p1[0] - p2[0], p1[1] - p2[1])) < 0.6 * side:
		return None
	# Markers: 1 = outside (a background wall on the mask's zero-distance boundary),
	# 2 and 3 = small discs on the two peaks. The topographic surface is the inverted
	# distance transform, so both peaks are valleys that flood outward and meet on the
	# thin-neck ridge; the outside wall (distance 0) keeps marker 1 out of the piece.
	markers = np.zeros(comp_mask.shape, dtype=np.int32)
	markers[comp_mask == 0] = 1
	disc = max(1, int(round(0.20 * radius)))
	cv2.circle(markers, p1, disc, 2, -1)
	cv2.circle(markers, p2, disc, 3, -1)
	dn = cv2.normalize(dist, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
	surf = cv2.cvtColor(255 - dn, cv2.COLOR_GRAY2BGR)
	cv2.watershed(surf, markers)
	subs: list[np.ndarray] = []
	for r in (2, 3):
		region = ((markers == r) & (comp_mask > 0)).astype(np.uint8) * 255
		if int((region > 0).sum()) > 0:
			subs.append(region)
	if len(subs) != 2:
		return None
	# A legitimate bisection of a barely-fused pair can hand one piece a slightly
	# sub-0.3 basin, so the fragment floor here is relaxed to 0.2*median.
	for s in subs:
		if int((s > 0).sum()) < 0.2 * median_area:
			return None
	return subs


def _seam_carve_split(
	comp_mask: np.ndarray, color_crop: np.ndarray, median_area: float, working_dim: int
) -> list[np.ndarray] | None:
	"""Separate ABUTTING pieces by carving the physical dark seam, then assigning every
	pixel with an inverted-distance-transform watershed (geometric, NEVER colour).

	Cardboard-back pieces set down touching share the SAME colour, so ``cv2.watershed`` on
	colour leaks basins through the seam and into the background (low-solidity garbage). The
	robust signal is the physical seam: a thin dark line (gap + cast shadow) where two piece
	edges meet, isolated by a black-hat (strong here: response ~225 vs a 12 floor). This CARVES
	that seam out of the mask; the connected remnants are one-per-piece cores; the inverted-DT
	watershed grows each core back to fill the whole mask, the basins meeting on the seam ridge.
	A piece's OWN blank has no dark seam through it, so carving can never cut a single piece at
	its blank. Accepted only when the black-hat peak is strong (``_SEAM_CARVE_TRIGGER``) and every
	resulting sub is single-piece-plausible (``_solidity`` >= ``_SUB_SOLIDITY_MIN``, ~one median
	piece); otherwise ``None`` -> the component is left whole (later flagged ``is_cluster``).
	"""
	L = cv2.cvtColor(color_crop, cv2.COLOR_BGR2LAB)[:, :, 0]
	k = max(9, int(round(_SEAM_KERNEL_FRAC * working_dim)))
	if k % 2 == 0:
		k += 1
	bh = cv2.morphologyEx(L, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
	inside = comp_mask > 0
	if not inside.any():
		return None
	peak = float(bh[inside].max())
	# Only carve on a STRONG seam; a weak black-hat response is texture, not a piece gap.
	if peak < _SEAM_CARVE_TRIGGER * _SEAM_MIN_RESPONSE:
		return None
	# Relaxed threshold so faint sections of a real seam are still carved through.
	thr = max(_SEAM_MIN_RESPONSE, _SEAM_CARVE_THR_FRAC * peak)
	barrier = ((bh >= thr) & inside).astype(np.uint8) * 255
	k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
	carved = cv2.morphologyEx(cv2.bitwise_and(comp_mask, cv2.bitwise_not(barrier)), cv2.MORPH_OPEN, k3)
	n, lbl, stats, _ = cv2.connectedComponentsWithStats(carved, 8)
	cores = [l for l in range(1, n) if stats[l, cv2.CC_STAT_AREA] >= 0.25 * median_area]
	if len(cores) < 2:
		return None  # the seam did not cut the component into >=2 piece-sized cores
	# Inverted-DT watershed: seed each carved core, wall off the background at distance 0,
	# flood so the seam pixels (and any sub-core remnants) fall to the nearest core.
	dist = cv2.distanceTransform(comp_mask, cv2.DIST_L2, 5)
	markers = np.zeros(comp_mask.shape, dtype=np.int32)
	markers[comp_mask == 0] = 1
	for i, l in enumerate(cores, start=2):
		markers[lbl == l] = i
	dn = cv2.normalize(dist, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
	cv2.watershed(cv2.cvtColor(255 - dn, cv2.COLOR_GRAY2BGR), markers)
	subs = []
	for r in range(2, 2 + len(cores)):
		region = ((markers == r) & (comp_mask > 0)).astype(np.uint8) * 255
		if int((region > 0).sum()) > 0:
			subs.append(region)
	if len(subs) < 2:
		return None
	# Fold any implausibly small fragment (< 0.4*median) into its largest-border neighbour.
	floor = 0.4 * median_area
	keep = [s for s in subs if int((s > 0).sum()) >= floor]
	if len(keep) < 2:
		return None
	for frag in sorted((s for s in subs if int((s > 0).sum()) < floor), key=lambda s: int((s > 0).sum())):
		dil = cv2.bitwise_and(cv2.dilate(frag, k3), comp_mask)
		best_i, best_overlap = -1, 0
		for i, kmask in enumerate(keep):
			overlap = int(((dil > 0) & (kmask > 0)).sum())
			if overlap > best_overlap:
				best_i, best_overlap = i, overlap
		if best_i < 0:
			best_i = max(range(len(keep)), key=lambda i: int((keep[i] > 0).sum()))
		keep[best_i] = cv2.bitwise_or(keep[best_i], cv2.bitwise_or(frag, dil))
	# Plausibility gate: every sub must look like a single piece, else this was not a clean
	# inter-piece split -> leave the component whole (honest cluster), never emit garbage.
	for s in keep:
		a = int((s > 0).sum())
		if _solidity(s) < _SUB_SOLIDITY_MIN or not (0.45 * median_area <= a <= 1.7 * median_area):
			return None
	return keep


def _watershed_from_seeds(
	comp_mask: np.ndarray,
	color_crop: np.ndarray,
	median_area: float,
	seeds: tuple[np.ndarray, np.ndarray, int],
) -> list[np.ndarray] | None:
	"""Cap, watershed and validate one set of seeds into sub-piece masks.

	Returns the sub-masks, or ``None`` if the seeds give fewer than two markers or
	collapse to one region. A sub that comes back implausibly small (< 0.3*median) is
	not a veto: it is merged into its neighbouring keep-sub (partial acceptance), and
	``None`` is returned only when fewer than two keep-subs remain -- i.e. the split
	was not real.
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
	# Partial acceptance instead of a wholesale revert: when the watershed leaves an
	# implausibly small fragment (< 0.3*median) it is almost always over-seeding -- the
	# marker cap or extra distance-transform peaks split ONE piece into a body plus a
	# sliver, while the genuine piece-to-piece separations are correct. Reverting the
	# whole split (the old behaviour) then re-fused a whole cluster into one blob. So
	# each tiny fragment is MERGED into its neighbouring keep-sub (largest shared
	# border) and the good subs are accepted; only if fewer than two keep-subs survive
	# is it a genuine single piece / inseparable cluster and ``None`` is returned. This
	# can only REDUCE the sub count, so it never invents spurious pieces.
	floor = 0.3 * median_area
	keep = [s for s in subs if int((s > 0).sum()) >= floor]
	if not keep:
		return None
	tiny = [s for s in subs if int((s > 0).sum()) < floor]
	if tiny:
		# Settle smallest-first so a chain of fragments resolves deterministically.
		tiny.sort(key=lambda s: int((s > 0).sum()))
		k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
		for frag in tiny:
			# Dilate across the 1px watershed ridge to find the border shared with each
			# keep-sub; fold the fragment (bridged so no 1px gap survives, clipped to the
			# component) into the keep-sub it touches most, or the largest keep if none.
			dil = cv2.bitwise_and(cv2.dilate(frag, k3), comp_mask)
			best_i, best_overlap = -1, 0
			for i, kmask in enumerate(keep):
				overlap = int(((dil > 0) & (kmask > 0)).sum())
				if overlap > best_overlap:
					best_i, best_overlap = i, overlap
			if best_i < 0:
				best_i = max(range(len(keep)), key=lambda i: int((keep[i] > 0).sum()))
			keep[best_i] = cv2.bitwise_or(keep[best_i], cv2.bitwise_or(frag, dil))
	if len(keep) < 2:
		return None
	# Solidity guard: a colour watershed that LEAKED (same-colour pieces, no gradient at the
	# seam) yields scattered / background-bled subs. Reject the whole split rather than emit
	# garbage -- the component stays whole (later flagged is_cluster, honest) or is rescued
	# cleanly by _seam_carve_split. A genuine piece scores solidity >= ~0.62; leaked garbage
	# <= ~0.55 (see _SUB_SOLIDITY_MIN).
	if any(_solidity(s) < _SUB_SOLIDITY_MIN for s in keep):
		return None
	return keep


def _resplit_subs(
	subs: list[np.ndarray],
	color_crop: np.ndarray,
	median_area: float,
	marker_ratio: float,
	working_dim: int,
	seam_frac: float,
	split_trigger: float,
	depth: int,
) -> list[np.ndarray]:
	"""Recursively re-split any sub still large enough to be >1 piece.

	A watershed can leave one sub still fused (e.g. a 3-piece cluster seeds as
	``[pair, single]``); each sub above ``split_trigger`` * median is fed back
	through :func:`_split_component` and, if it separates, replaced by its parts.
	Sub masks share ``comp_mask``'s frame, so each is cropped to its bbox, split,
	and the results pasted back at the same offset. Depth-bounded by
	``_MAX_SPLIT_DEPTH``; a sub that does not separate is kept as-is.
	"""
	if depth >= _MAX_SPLIT_DEPTH:
		return subs
	refined: list[np.ndarray] = []
	for sub in subs:
		if int((sub > 0).sum()) <= split_trigger * median_area:
			refined.append(sub)
			continue
		sx, sy, sw, sh = cv2.boundingRect(sub)
		sub_crop = sub[sy:sy + sh, sx:sx + sw]
		sub_color = color_crop[sy:sy + sh, sx:sx + sw]
		parts = _split_component(
			sub_crop, sub_color, median_area, marker_ratio, working_dim, seam_frac, split_trigger, depth + 1
		)
		if parts is None:
			refined.append(sub)
			continue
		for part in parts:
			full = np.zeros_like(sub)
			full[sy:sy + sh, sx:sx + sw] = part
			refined.append(full)
	return refined


def _split_component(
	comp_mask: np.ndarray,
	color_crop: np.ndarray,
	median_area: float,
	marker_ratio: float,
	working_dim: int,
	seam_frac: float,
	split_trigger: float,
	depth: int = 0,
) -> list[np.ndarray] | None:
	"""Try to watershed-split one large component into touching pieces.

	``comp_mask`` is a 0/255 crop, ``color_crop`` the matching BGR crop. The plain
	distance-transform split is tried first (identical to the historic behaviour,
	so cleanly separated pieces are untouched); only if it cannot separate the
	component is the dark inter-piece seam brought in to *rescue* a split, and only
	if that also fails is a geometric bisection FORCED. This ordering guarantees the
	seam and the forced cut can add splits but never remove one. Any sub that comes
	back still over-sized is re-split (:func:`_resplit_subs`). Returns a list of
	sub-piece masks, or ``None`` to keep the component whole.
	"""
	# First, carve at the physical dark seam: this separates ABUTTING same-colour pieces that a
	# colour watershed cannot (it leaks through the seam). Geometric assignment, self-validated
	# by per-sub solidity, so it only fires when it produces clean single pieces.
	carve = _seam_carve_split(comp_mask, color_crop, median_area, working_dim)
	if carve is not None:
		return _resplit_subs(
			carve, color_crop, median_area, marker_ratio, working_dim, seam_frac, split_trigger, depth
		)
	plain = _plain_seeds(comp_mask, marker_ratio)
	if plain is None:
		return None
	subs = _watershed_from_seeds(comp_mask, color_crop, median_area, plain)
	if subs is None:
		seam = _seam_seeds(comp_mask, color_crop, marker_ratio, working_dim, seam_frac)
		if seam is not None:
			subs = _watershed_from_seeds(comp_mask, color_crop, median_area, seam)
	if subs is not None:
		return _resplit_subs(
			subs, color_crop, median_area, marker_ratio, working_dim, seam_frac, split_trigger, depth
		)
	# Third, FORCED path: a component well above _FORCE_SPLIT_RATIO * median that both
	# the plain and seam watersheds left whole is almost certainly >=2 pieces joined
	# across a seam too weak for either. Bisect it at its narrowest waist, but accept
	# the cut ONLY when both halves look single (each <= split_trigger * median): a
	# genuine >2-piece cluster bisects into still-oversized halves and is left whole
	# (later flagged is_cluster) instead of being emitted as two fused chunks.
	comp_area = int((comp_mask > 0).sum())
	if comp_area > _FORCE_SPLIT_RATIO * median_area:
		halves = _forced_bisect(comp_mask, median_area)
		if halves is not None and all(
			int((h > 0).sum()) <= split_trigger * median_area for h in halves
		):
			return halves
	return None


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
	``is_cluster`` marks a component that triggered a split, could not be
	separated, and stayed larger than ``cluster_ratio`` * median -- i.e. a genuine
	touching/assembled cluster the splitter could not resolve into single pieces.
	"""
	h, w = binary.shape[:2]
	working_area = h * w
	working_dim = max(h, w)
	num, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)

	# Reject dust, frame-touching margins/creases and extreme-aspect slivers
	# BEFORE the median so the surviving-piece median is not polluted by non-pieces.
	dust = 0.0005 * working_area
	frame_margin = max(1, int(round(_FRAME_MARGIN_FRAC * working_dim)))
	kept: list[int] = []
	for lab in range(1, num):
		if stats[lab, cv2.CC_STAT_AREA] < dust:
			continue
		x0 = int(stats[lab, cv2.CC_STAT_LEFT])
		y0 = int(stats[lab, cv2.CC_STAT_TOP])
		ww = int(stats[lab, cv2.CC_STAT_WIDTH])
		hh = int(stats[lab, cv2.CC_STAT_HEIGHT])
		# Touches the image frame -> photo border / crease between backing sheets.
		if (
			x0 <= frame_margin
			or y0 <= frame_margin
			or x0 + ww >= w - frame_margin
			or y0 + hh >= h - frame_margin
		):
			continue
		# Extreme-aspect sliver -> thin border strip / seam shadow, not a piece.
		if max(ww, hh) / max(1, min(ww, hh)) > _MAX_BBOX_ASPECT:
			continue
		kept.append(lab)
	if not kept:
		return []

	areas = np.array([stats[lab, cv2.CC_STAT_AREA] for lab in kept], dtype=np.float64)
	median_area = float(np.median(areas))
	if median_area <= 0:
		return []

	# Drop under-area dust AND thin lines/creases that slipped past the bbox-aspect test.
	# The stroke gate needs the median piece side, so it runs here, after median_area.
	median_side = float(np.sqrt(median_area))
	survivors: list[int] = []
	for lab in kept:
		if stats[lab, cv2.CC_STAT_AREA] < min_area_ratio * median_area:
			continue
		x0 = int(stats[lab, cv2.CC_STAT_LEFT])
		y0 = int(stats[lab, cv2.CC_STAT_TOP])
		ww = int(stats[lab, cv2.CC_STAT_WIDTH])
		hh = int(stats[lab, cv2.CC_STAT_HEIGHT])
		comp = (labels[y0:y0 + hh, x0:x0 + ww] == lab).astype(np.uint8) * 255
		dt = cv2.distanceTransform(comp, cv2.DIST_L2, 5)
		if 2.0 * float(dt.max()) < _MIN_STROKE_FRAC * median_side:
			continue
		survivors.append(lab)

	out: list[tuple[tuple[int, int, int, int], np.ndarray, bool]] = []
	for lab in survivors:
		x = int(stats[lab, cv2.CC_STAT_LEFT])
		y = int(stats[lab, cv2.CC_STAT_TOP])
		ww = int(stats[lab, cv2.CC_STAT_WIDTH])
		hh = int(stats[lab, cv2.CC_STAT_HEIGHT])
		area = int(stats[lab, cv2.CC_STAT_AREA])
		comp_mask = (labels[y:y + hh, x:x + ww] == lab).astype(np.uint8) * 255
		color_crop = work_bgr[y:y + hh, x:x + ww]

		subs = None
		if split_touching and area > split_trigger * median_area:
			subs = _split_component(
				comp_mask, color_crop, median_area, marker_ratio, working_dim, seam_frac, split_trigger
			)
		# Fallback for a mid-sized blob the colour/seam split left whole: a bounded
		# geometric bisection catches two near-but-unconnected pieces the closing
		# bridged across a pale background gap (see _BISECT_MIN_RATIO). Bounded to
		# (_BISECT_MIN_RATIO, cluster_ratio] * median and accepted only when both
		# halves look single, so single pieces and genuine clusters are left whole.
		if (
			subs is None
			and split_touching
			and _BISECT_MIN_RATIO * median_area < area <= cluster_ratio * median_area
		):
			halves = _forced_bisect(comp_mask, median_area)
			if halves is not None and all(
				int((h > 0).sum()) <= split_trigger * median_area for h in halves
			):
				subs = halves

		if subs is not None:
			for sub in subs:
				sx, sy, sw, sh = cv2.boundingRect(sub)
				sub_crop = sub[sy:sy + sh, sx:sx + sw].copy()
				sub_area = int((sub_crop > 0).sum())
				# Emission garbage guard: a leaked/merged sub is not a clean single piece.
				# Flag it is_cluster (honest) rather than emit a deformed "piece".
				flag = (
					_is_cluster_blob(sub_crop, median_area, marker_ratio, cluster_ratio)
					or _solidity(sub_crop) < _SUB_SOLIDITY_MIN
					or sub_area > 1.6 * median_area
					or sub_area < 0.4 * median_area
				)
				out.append(((x + sx, y + sy, sw, sh), sub_crop, flag))
			continue

		if split_touching and area > split_trigger * median_area:
			# Split was TRIGGERED but could not separate this component. If it is
			# still much larger than a single piece it is a genuine touching /
			# assembled cluster of pieces, so flag it rather than emit it as one
			# deceptive over-sized "piece" (whose crop would contain several pieces
			# glued together). The split outcome is used directly because the plain
			# peak-count test alone is unreliable here: a multi-piece blob can show
			# several distance peaks yet still resist a clean watershed split.
			flag = area > cluster_ratio * median_area or _solidity(comp_mask) < _SUB_SOLIDITY_MIN
			out.append(((x, y, ww, hh), comp_mask, flag))
			continue
		# Split not triggered (or disabled): the component is close to a single piece
		# (area <= split_trigger * median). It is a clean piece UNLESS it is a low-solidity
		# blob (a shred/leak) or a sub-piece fragment -> then flag is_cluster (honest).
		flag = _solidity(comp_mask) < _SUB_SOLIDITY_MIN or area < 0.4 * median_area
		out.append(((x, y, ww, hh), comp_mask, flag))
	return out


def _normalize_angle(ang: float) -> float:
	"""Fold a minAreaRect angle into (-45, 45]."""
	if ang > 45:
		ang -= 90
	elif ang < -45:
		ang += 90
	return ang


def _shrink_edge_shadow(mask: np.ndarray, rgb_crop: np.ndarray, long_side: int) -> np.ndarray:
	"""Peel the interior-rim cast-shadow halo off a filled 0/255 piece mask.

	The mask is eroded by ``_SHADOW_BAND_FRAC * long_side`` to bound the boundary band
	that may be peeled (a hard ceiling, wide enough to reach the shadow that pools
	inside concave tab notches), then within that band -- the crown between the
	original and eroded masks -- only pixels that are BOTH clearly darker (by at least
	``_SHADOW_L_DELTA``) AND lower-chroma than the piece interior are dropped. That
	darker-and-desaturated pair is the signature of a cast shadow, so genuine painted
	rims (which keep their chroma) and fully neutral/grey pieces (whose rim is not
	darker than their own interior) are preserved -- the erosion is used only as a
	maximum, never applied wholesale.

	``rgb_crop`` is the matching RGB crop, ``long_side`` the piece's padded long side.
	Falls back to the unshrunk ``mask`` when the piece is too small, when the shrink
	would drop the mask below ``_EDGE_SHRINK_MIN_AREA_KEEP`` of its area, or when the
	result would be empty (so the mask is never emptied and small pieces are safe).
	"""
	if _EDGE_SHRINK_FRAC <= 0.0 or long_side < _EDGE_SHRINK_MIN_SIDE:
		return mask
	orig_area = int((mask > 0).sum())
	if orig_area == 0:
		return mask
	# Candidate shadow band: deep enough to reach shadow pooled inside concave
	# notches. Retreat to the thin _EDGE_SHRINK_FRAC rim if the wide erosion would
	# consume the whole piece (thin/narrow pieces).
	rb = max(1, int(round(_SHADOW_BAND_FRAC * long_side)))
	eroded = cv2.erode(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * rb + 1, 2 * rb + 1)))
	if not (eroded > 0).any():
		rb = max(1, int(round(_EDGE_SHRINK_FRAC * long_side)))
		eroded = cv2.erode(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * rb + 1, 2 * rb + 1)))
		if not (eroded > 0).any():
			return mask
	rim = (mask > 0) & (eroded == 0)
	if not rim.any():
		return mask
	# Interior reference from a still-deeper erosion so a deep halo does not bias the
	# lightness/chroma medians toward the shadow itself; fall back if it empties.
	rc = rb + rb // 2
	deep = cv2.erode(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * rc + 1, 2 * rc + 1)))
	core = deep if (deep > 0).any() else eroded
	lab = cv2.cvtColor(rgb_crop, cv2.COLOR_RGB2LAB).astype(np.float32)
	L = lab[:, :, 0]
	chroma = np.sqrt((lab[:, :, 1] - 128.0) ** 2 + (lab[:, :, 2] - 128.0) ** 2)
	core_sel = core > 0
	L_int = float(np.median(L[core_sel]))
	C_int = float(np.median(chroma[core_sel]))
	# Conjunctive test: clearly darker AND lower-chroma than the interior.
	shadow = rim & (L < L_int - _SHADOW_L_DELTA) & (chroma < C_int)
	if not shadow.any():
		return mask
	# Drop isolated speckle so only contiguous crescents are peeled (smooth boundary).
	if _SHADOW_OPEN_FRAC > 0.0:
		ok = max(1, int(round(_SHADOW_OPEN_FRAC * long_side)))
		opened = cv2.morphologyEx(
			shadow.astype(np.uint8), cv2.MORPH_OPEN,
			cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * ok + 1, 2 * ok + 1)),
		)
		shadow = opened > 0
		if not shadow.any():
			return mask
	refined = mask.copy()
	refined[shadow] = 0
	# Back off wholesale if peeling would breach the area floor: on a piece ringed by
	# extensive shadow the survivors are scattered speckle, and removing them moth-eats
	# the mask -- worse than leaving the halo. Keeping the piece intact is the safe call.
	if int((refined > 0).sum()) < _EDGE_SHRINK_MIN_AREA_KEEP * orig_area:
		return mask
	if not (refined > 0).any():
		return mask
	return refined


def _clean_piece_mask(mask: np.ndarray) -> np.ndarray:
	"""Force the solid, simply-connected invariant on a 0/255 piece mask.

	A jigsaw piece is a SOLID, simply-connected shape: a single blob with no
	genuine interior holes. Keeping only the largest EXTERNAL contour and drawing
	it FILLED does all three cleanups in one pass -- it (a) discards isolated
	specks lying outside the piece, (b) keeps only the largest connected
	component, and (c) fills every interior hole (glossy highlights, print gaps,
	pinholes left by the mask pipeline), since ``RETR_EXTERNAL`` ignores hole
	boundaries and the fill paints the whole outline solid.

	A single ``medianBlur(3)`` then shaves pixel-level boundary jaggies. It is the
	most tab-safe smoother available: a border pixel flips only when at least 5 of
	its 3x3 neighbours disagree, so it can erode ONLY 1 px hairs -- any tab neck
	>=2 px wide (the interlocking geometry ``edges.py`` reads as the fit) is left
	untouched. A morphological open, by contrast, would erode those necks, so it is
	deliberately avoided. The largest-contour fill is re-run after the blur to
	re-establish the invariant in the rare case the median nibbles a 1 px bridge
	loose or reopens a micro-hole. Returns a fresh uint8 0/255 array.
	"""
	def _largest_filled(m: np.ndarray) -> np.ndarray | None:
		cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
		if not cnts:
			return None
		cnt = max(cnts, key=cv2.contourArea)
		filled = np.zeros_like(m)
		cv2.drawContours(filled, [cnt], -1, 255, thickness=cv2.FILLED)
		return filled

	filled = _largest_filled(mask)
	if filled is None:
		return mask
	smoothed = cv2.medianBlur(filled, 3)
	refilled = _largest_filled(smoothed)
	return refilled if refilled is not None else filled


def _circular_gaussian(a: np.ndarray, sigma: float) -> np.ndarray:
	"""Gaussian-smooth a CLOSED sequence with wrap-around (no seam at the join).

	Accepts a 1-D array or an ``(n, d)`` array (each column smoothed independently);
	returns the same shape. A no-op when the sequence is too short for the kernel.
	"""
	arr = np.asarray(a, dtype=np.float64)
	one_d = arr.ndim == 1
	if one_d:
		arr = arr[:, None]
	n = len(arr)
	r = int(round(3 * sigma))
	if r < 1 or n < 2 * r + 2:
		return arr[:, 0] if one_d else arr
	k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
	k /= k.sum()
	out = np.empty_like(arr)
	for d in range(arr.shape[1]):
		col = arr[:, d]
		ext = np.concatenate([col[-r:], col, col[:r]])
		out[:, d] = np.convolve(ext, k, mode="valid")
	return out[:, 0] if one_d else out


def _circular_median(a: np.ndarray, win: int) -> np.ndarray:
	"""Sliding-window median of a 1-D CLOSED sequence with wrap-around."""
	arr = np.asarray(a, dtype=np.float64)
	n = len(arr)
	if win < 3 or n < win:
		return arr
	if win % 2 == 0:
		win += 1
	r = win // 2
	ext = np.concatenate([arr[-r:], arr, arr[:r]])
	windows = np.lib.stride_tricks.sliding_window_view(ext, win)
	return np.median(windows, axis=1)


def _refine_boundary_band(
	mask: np.ndarray,
	rgb_crop: np.ndarray,
	bg_lab: np.ndarray,
	luma_weight: float,
	chroma_weight: float,
) -> np.ndarray:
	"""Re-snap a piece mask's boundary from the working-grid staircase to the colour edge.

	The mask is seeded from the downscaled working contour, so its boundary is a coarse
	staircase (step ~= the working->full-res ratio) dotted with micro-loops. This helper
	(a) Gaussian-smooths the contour (``_REFINE_CONTOUR_SIGMA``) to erase that staircase
	and the loops, giving a clean base and per-point outward normals, then (b) slides
	each base point along its normal to the ``_REFINE_EDGE_BIAS`` crossing of the
	weighted-Lab distance-to-background profile sampled +/-``_REFINE_BAND_PX`` along that
	normal -- i.e. the true colour edge. Points whose local inside/outside contrast is
	below ``_REFINE_CONTRAST_FLOOR`` keep offset 0 (only the smoothing applies, so no
	edge is invented on low-separation/white backgrounds), every offset is clamped to
	+/-``_REFINE_CLAMP_PX`` and the offset function is denoised along the contour
	(circular median + Gaussian) to kill spikes without distorting tabs.

	``bg_lab`` is the GLOBAL background in OpenCV 8-bit Lab (``segment_pieces``' scale);
	it is converted to CIE Lab here to match the float ``RGB2LAB`` crop. Pure; returns a
	fresh, solid 0/255 mask from a single filled polygon, falling back to the input mask
	on a degenerate contour or an implausibly-shrunk result. Vectorised (numpy + remap).
	"""
	cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
	if not cnts:
		return mask
	cnt = max(cnts, key=cv2.contourArea).reshape(-1, 2).astype(np.float64)
	n = len(cnt)
	if n < _REFINE_MIN_POINTS:
		return mask
	orig_area = int((mask > 0).sum())
	h, w = mask.shape[:2]

	# Background-distance map D over the whole crop, in weighted CIE-Lab units. Convert
	# the 8-bit-Lab bg (L 0..255, a/b offset 128) to CIE (L 0..100, a/b centred 0) so it
	# matches the float32 RGB2LAB crop.
	lab = cv2.cvtColor(np.ascontiguousarray(rgb_crop, np.float32) / 255.0, cv2.COLOR_RGB2LAB)
	bg_cie = np.array(
		[bg_lab[0] * 100.0 / 255.0, bg_lab[1] - 128.0, bg_lab[2] - 128.0], dtype=np.float32
	)
	diff = lab - bg_cie.reshape(1, 1, 3)
	D = np.sqrt(
		luma_weight * diff[:, :, 0] ** 2
		+ chroma_weight * (diff[:, :, 1] ** 2 + diff[:, :, 2] ** 2)
	).astype(np.float32)

	# Smoothed base (staircase/loops removed) and its outward unit normals.
	base = _circular_gaussian(cnt, _REFINE_CONTOUR_SIGMA)
	tang = np.roll(base, -1, axis=0) - np.roll(base, 1, axis=0)
	nrm = np.stack([tang[:, 1], -tang[:, 0]], axis=1)
	nl = np.linalg.norm(nrm, axis=1, keepdims=True)
	nl[nl < 1e-6] = 1.0
	nrm = nrm / nl
	# Orient outward: if a small step along +normal mostly lands inside the mask, flip.
	probe = base + 3.0 * nrm
	pxi = np.clip(np.round(probe[:, 0]).astype(np.int64), 0, w - 1)
	pyi = np.clip(np.round(probe[:, 1]).astype(np.int64), 0, h - 1)
	if (mask[pyi, pxi] > 0).mean() > 0.5:
		nrm = -nrm

	# Sample D along each normal at integer offsets s in [-band, +band].
	ss = np.arange(-_REFINE_BAND_PX, _REFINE_BAND_PX + 1, 1.0, dtype=np.float32)
	sx = (base[:, 0:1] + nrm[:, 0:1] * ss[None, :]).astype(np.float32)
	sy = (base[:, 1:2] + nrm[:, 1:2] * ss[None, :]).astype(np.float32)
	np.clip(sx, 0, w - 1, out=sx)
	np.clip(sy, 0, h - 1, out=sy)
	prof = cv2.remap(D, sx, sy, cv2.INTER_LINEAR)  # (n, K)

	# Per-point "inside"/"outside" levels (medians of the deep samples) and target.
	inside = np.median(prof[:, ss <= -5.0], axis=1)
	outside = np.median(prof[:, ss >= 5.0], axis=1)
	target = outside + _REFINE_EDGE_BIAS * (inside - outside)

	# Sub-pixel offset = the descending zero of (prof - target) nearest the current
	# point (s=0): D falls from inside (high) to outside (low), so the piece edge is the
	# first + -> - crossing across the window.
	g = prof - target[:, None]
	pos = g >= 0.0
	desc = pos[:, :-1] & (~pos[:, 1:])  # (n, K-1) crossing between slot j and j+1
	center = int(np.argmin(np.abs(ss)))
	slot = np.arange(len(ss) - 1)
	dist_to_center = np.abs(slot - center)
	sentinel = len(ss) + 1
	cand = np.where(desc, dist_to_center[None, :], sentinel)
	best = np.argmin(cand, axis=1)
	has_cross = desc.any(axis=1)
	rows = np.arange(n)
	gj = g[rows, best]
	gj1 = g[rows, best + 1]
	denom = gj - gj1
	t = np.divide(gj, denom, out=np.zeros_like(gj), where=np.abs(denom) > 1e-9)
	s_cross = ss[best] + t * (ss[best + 1] - ss[best])
	offset = np.where(has_cross, s_cross, 0.0)

	# Contrast gate, clamp, then denoise the offset function along the contour.
	offset[np.abs(inside - outside) < _REFINE_CONTRAST_FLOOR] = 0.0
	np.clip(offset, -_REFINE_CLAMP_PX, _REFINE_CLAMP_PX, out=offset)
	offset = _circular_median(offset, _REFINE_OFFSET_MEDIAN)
	offset = _circular_gaussian(offset, _REFINE_OFFSET_SIGMA)

	# New polygon along the normals -> fresh solid mask.
	new_pts = base + offset[:, None] * nrm
	poly = np.round(new_pts).astype(np.int32)
	poly[:, 0] = np.clip(poly[:, 0], 0, w - 1)
	poly[:, 1] = np.clip(poly[:, 1], 0, h - 1)
	refined = np.zeros_like(mask)
	cv2.drawContours(refined, [poly.reshape(-1, 1, 2)], -1, 255, thickness=cv2.FILLED)
	new_area = int((refined > 0).sum())
	# A valid re-snap shifts the boundary a few px, so the area barely changes; a
	# collapse means the polygon self-destructed -> keep the un-refined mask.
	if new_area == 0 or new_area < 0.5 * orig_area:
		return mask
	return refined


def _extract_piece(
	mask_crop: np.ndarray,
	bbox_w: tuple[int, int, int, int],
	inv: float,
	original_rgb: np.ndarray,
	normalize_rotation: bool,
	pad_ratio: float,
	bg_lab: np.ndarray,
	luma_weight: float,
	chroma_weight: float,
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

	rgb_crop = original_rgb[oy:oy + oh, ox:ox + ow].copy()
	# Re-snap the coarse working-grid boundary (a ~inv-px staircase with micro-loops) to
	# the true full-res colour edge BEFORE the shadow peel and invariant cleanup consume
	# it. Uses the GLOBAL background model, not a per-piece estimate.
	mask_full = _refine_boundary_band(mask_full, rgb_crop, bg_lab, luma_weight, chroma_weight)
	# Peel the interior-rim cast-shadow halo BEFORE any colour/fill is derived, so the
	# mean colour, the mean-fill and the rotation branch all inherit the clean mask.
	mask_full = _shrink_edge_shadow(mask_full, rgb_crop, max(ow, oh))
	# Enforce the solid, simply-connected piece invariant (single blob, no holes,
	# no specks) BEFORE the mean-fill so mask and img stay consistent: filled holes
	# keep their original colour in img, removed specks get mean-filled below.
	mask_full = _clean_piece_mask(mask_full)

	# Derive the returned contour from the FINAL mask (post shrink/clean/refine) so
	# edges.py classifies the exact geometry the emitted crop mask carries -- not the
	# working-resolution contour the mask was seeded from, which drifts after those
	# steps. Taken here, PRE-rotation, so ``contour`` stays in original image coords
	# (the rotation branch below reassigns ``mask_full`` to the warped mask; this
	# contour must not follow it).
	final_cnts, _ = cv2.findContours(mask_full, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
	if not final_cnts:
		return None
	final_cnt = max(final_cnts, key=cv2.contourArea).reshape(-1, 2).astype(np.int32)
	contour_orig = final_cnt + np.array([ox, oy], dtype=np.int32)
	contour_orig[:, 0] = np.clip(contour_orig[:, 0], 0, W - 1)
	contour_orig[:, 1] = np.clip(contour_orig[:, 1], 0, H - 1)

	m = mask_full > 0
	if not m.any():
		return None
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
				# Same invariant cleanup as the non-rotated path, applied to the
				# warped mask BEFORE its mean-fill so mask_r and img_r stay in sync.
				mask_r = _clean_piece_mask(mask_r)
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
		"contour": contour_orig,
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
	luma_weight: float = 0.075,
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
		luma_weight, chroma_weight: weights of the (squared) Lab lightness and
			chroma distance to the background. The detection is deliberately
			chroma-dominated (default luma_weight 0.075 vs chroma_weight 1.0): a
			cast shadow differs from the neutral surface almost only in lightness
			(high dL, near-zero dChroma), so a low luma_weight drops shadow below
			the Otsu threshold and keeps it out of the mask -- removing the grey
			halo around crops and the shadow bridges that merge neighbouring
			pieces. luma_weight is kept non-zero (not purely chroma) so genuinely
			neutral/grey pieces, which differ from a white surface mainly in
			lightness, are still detected.
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
		rec = _extract_piece(
			mask_crop, bbox_w, inv, original_rgb, normalize_rotation, pad_ratio,
			bg, luma_weight, chroma_weight,
		)
		if rec is not None:
			# Authoritative garbage guard on the FINAL full-res mask: a leaked/scattered
			# blob that slipped the working-res emission check is flagged is_cluster here
			# (never a deformed "piece"). Real pieces score solidity >= ~0.62; garbage <= ~0.55.
			final_cluster = bool(is_cluster) or _solidity(np.asarray(rec["mask"])) < _SUB_SOLIDITY_MIN
			rec["is_cluster"] = final_cluster
			if final_cluster:
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


def piece_to_rgba(image, mask) -> Image.Image:
	"""Compose a clean, transparent-background cutout of one piece.

	``image`` supplies the RGB colour (a piece record's ``image`` already
	carries the true piece colour wherever ``mask`` is set, so no colour logic
	is applied here) and ``mask`` supplies the alpha channel: 255 -> opaque
	piece pixel, 0 -> fully transparent background. Both arguments accept
	either a PIL Image or a numpy ndarray. This is purely a *display/export*
	representation -- it does not touch detection, splitting or the
	mean-filled ``image``/``mask`` pair handed to the matcher.

	Returns a PIL Image in 'RGBA' mode.
	"""
	if isinstance(image, np.ndarray):
		image = Image.fromarray(image)
	if isinstance(mask, np.ndarray):
		mask = Image.fromarray(mask)
	rgb = image.convert("RGB")
	alpha = mask.convert("L")
	if alpha.size != rgb.size:
		alpha = alpha.resize(rgb.size, Image.NEAREST)
	rgba = rgb.copy()
	rgba.putalpha(alpha)
	return rgba


def save_pieces(pieces: list[dict], out_dir: str, prefix: str = "piece_") -> list[str]:
	"""Write each piece as a clean, transparent-background RGBA PNG.

	The RGB channels come from the piece's ``image`` and the alpha channel
	from its ``mask`` (see :func:`piece_to_rgba`), so the saved PNG shows the
	piece's true silhouette on a transparent background rather than the
	mean-filled rectangle used internally for matching.

	Returns the list of written file paths, ordered by piece ``index``.
	"""
	os.makedirs(out_dir, exist_ok=True)
	paths: list[str] = []
	ordered = sorted(pieces, key=lambda p: p.get("index", 0))
	for p in ordered:
		rgba = piece_to_rgba(p["image"], p["mask"])
		out_path = os.path.join(out_dir, f"{prefix}{p.get('index', 0)}.png")
		rgba.save(out_path)
		paths.append(out_path)
	return paths
