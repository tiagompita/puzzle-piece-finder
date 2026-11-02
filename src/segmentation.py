"""Automatic puzzle-piece segmentation from a photo of the board/mat.

Given a single photo containing many pieces spread on a (roughly uniform)
surface, this module detects, splits and crops individual pieces.

Public entry points: :func:`segment_pieces` (photos; pure, PIL in / dict out) and
:func:`segment_scan` (flatbed scans: segment_pieces separation + hybrid full-res boundary).
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
	"segment_scan",
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
# Components whose bounding box touches the working-image border are NOT dropped
# (defect S1, fixed 2026-10-31: on a flatbed scan a piece < 1.2 mm from the glass
# edge is a normal case). They are kept, flagged ``touches_frame`` and excluded
# from the median-area estimate; photo margins / creases between backing sheets
# are still removed by the aspect and stroke gates below, and a frame-touching
# blob larger than ``cluster_ratio`` * median, or spanning more than this many
# median piece sides, is rejected as margin/floor/lid outline (a piece with tabs
# spans ~1.5 sides; a 2-piece mated pair at the edge ~2.5).
_FRAME_BLOB_SPAN = 3.0
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


# ===== Scan-edge paper strip tunables (defect S3, fixed 2026-10-31) =====
# On a flatbed scan the coloured paper often does not cover the whole glass, leaving
# a near-white strip of bare lid/glass along one or more edges (~4 mm on the E-real-2
# sky sheets). Against a saturated background it is strong foreground, so a piece
# abutting it merged with it and the merged blob was dropped by the aspect / frame-blob
# gates. ``_frame_strip_mask`` finds it and the strip is zeroed before labelling.
# Near-white: OpenCV 8-bit L (NOT illumination-flattened: the flattening pulls a strip
# at the edge down) and chroma sqrt((a-128)^2 + (b-128)^2). Measured on the sky sheets:
# strip L 240..255, chroma 0..5; green paper L ~190, chroma ~65.
_STRIP_MIN_L = 215.0
_STRIP_MAX_CHROMA = 12.0
# A strip spans >= this fraction of the side it runs along (rows reaching the frame zone)...
_STRIP_MIN_SPAN_FRAC = 0.25
# ...is at most this fraction of the image dimension wide (median per-row width)...
_STRIP_MAX_WIDTH_FRAC = 0.15
# ...and comes within this fraction of the dimension of the image border: the paper
# can leave a thin band of background between the strip and the frame (f1p1: ~1 mm).
_STRIP_FRAME_GAP_FRAC = 0.01
# The removal is restricted to the strip's band along the frame: a robust line fit of
# the per-row inner edge plus this tolerance (px). A light (cloud) piece abutting the
# strip joins the white component but sticks out of the band, so it is kept.
_STRIP_BAND_TOL_PX = 2
# Dilation (px, at the working resolution) of the removed strip, to swallow the
# 1-2 px colour-blend seam between strip and background.
_STRIP_DILATE_PX = 2


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


def _otsu_plateau_threshold(img_u8: np.ndarray) -> float:
	"""Otsu threshold of a uint8 image, centred on the plateau of tied maxima.

	Otsu's between-class variance is CONSTANT across a run of empty histogram bins
	(no pixel changes class as the threshold slides through them), so on a strongly
	bimodal image -- two modes separated by an empty gap -- every level in the gap is
	an equally optimal threshold. ``cv2.threshold(..., THRESH_OTSU)`` breaks that tie
	by returning the FIRST maximum, i.e. the very top of the lower (background) mode.
	The partition is the same, but any derived level then lands INSIDE the background
	mode: ``_foreground_from_bg``'s hysteresis low level (``_HYST_LOW_FACTOR * t``)
	would annex background pixels touching a piece. This returns the midpoint of the
	maximal-variance run that contains OpenCV's choice instead -- the same partition
	(``img > t``) whenever the run is a single bin, which is the usual case for a real
	photo's continuous histogram, and a threshold safely mid-gap when it is not.
	"""
	hist = np.bincount(img_u8.ravel(), minlength=256).astype(np.float64)
	total = hist.sum()
	if total <= 0:
		return 0.0
	levels = np.arange(256, dtype=np.float64)
	w0 = np.cumsum(hist) / total
	mu = np.cumsum(hist * levels) / total
	mu_t = mu[-1]
	w1 = 1.0 - w0
	valid = (w0 > 0) & (w1 > 0)
	if not valid.any():
		return 0.0
	sigma_b = np.zeros(256, dtype=np.float64)
	sigma_b[valid] = (mu_t * w0[valid] - mu[valid]) ** 2 / (w0[valid] * w1[valid])
	t0 = int(np.argmax(sigma_b))
	# Extend over the contiguous run of (numerically) tied maxima -- these are exactly
	# the empty bins following t0, across which no pixel changes class.
	t1 = t0
	while t1 + 1 < 256 and hist[t1 + 1] == 0 and valid[t1 + 1]:
		t1 += 1
	return 0.5 * (t0 + t1)


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
	# Plateau-centred Otsu (see :func:`_otsu_plateau_threshold`): identical to OpenCV's
	# Otsu on a continuous histogram, but mid-gap on a gapped one, so thr_low below can
	# never fall inside the background mode.
	t_otsu = _otsu_plateau_threshold(D)
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

	The close and the hole fill run inside a zero (background) frame of the
	close-kernel size, cropped back afterwards, so the outside of the image counts
	as background there: a piece a few px from the border is not glued to the
	border by the closing, and the corner flood fill always starts on background.
	The open keeps OpenCV's default border so a blob that touches the border is
	not pulled off it (``touches_frame`` stays truthful).
	"""
	k = max(3, int(round(0.003 * working_dim)))
	if k % 2 == 0:
		k += 1
	kern_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
	k2 = k * 2 + 1
	kern_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k2, k2))
	m = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kern_open)
	pad = k2
	m = cv2.copyMakeBorder(m, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
	m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, kern_close)
	# Enclosed background = pixels the corner flood fill cannot reach.
	h, w = m.shape[:2]
	ff = m.copy()
	ff_mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
	cv2.floodFill(ff, ff_mask, (0, 0), 255)
	holes = cv2.bitwise_not(ff)
	# Fill only holes below the smaller of (total foreground) and the image cap.
	fg_area = int((m > 0).sum())
	size_cap = min(fg_area, int(max_hole_frac * binary.shape[0] * binary.shape[1]))
	num, lab_h, stats_h, _ = cv2.connectedComponentsWithStats((holes > 0).astype(np.uint8), 8)
	if num > 1:
		small = np.nonzero(stats_h[1:, cv2.CC_STAT_AREA] < size_cap)[0] + 1
		if small.size:
			m = cv2.bitwise_or(m, (np.isin(lab_h, small).astype(np.uint8) * 255))
	return np.ascontiguousarray(m[pad:-pad, pad:-pad])


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
	comp_mask: np.ndarray, color_crop: np.ndarray, binary_raw_crop: np.ndarray,
	median_area: float, working_dim: int
) -> list[np.ndarray] | None:
	"""Separate ABUTTING pieces by REMOVING the inter-piece seam, then assigning each
	remaining connected body WHOLE to a piece (never a midline colour/DT watershed).

	Cardboard-back pieces set down touching share the SAME colour, so a colour watershed
	leaks basins through the seam; the earlier inverted-DT watershed, by contrast, redivided
	the seam at its geometric MIDLINE and so bit into the darker piece / handed a grab to its
	neighbour. The physical seam is genuinely NOT part of either piece: it is the dark gap +
	cast shadow, plus the thin background-coloured gap the step-6 CLOSE bridged over (which the
	pre-close ``binary_raw`` correctly excluded). So the seam is DROPPED, not redistributed:

	  * ``bg_invented`` = component pixels the CLOSE invented (foreground now, background in
	    ``binary_raw``) -- the background-coloured gap the close ponted across.
	  * ``barrier`` = the dark seam isolated by a black-hat (strong here, ~225 vs a 12 floor).
	  * ``remove`` = the barrier, plus every ``bg_invented`` connected component that touches
	    the seam neighbourhood (``contested``). Restricting to the contact keeps legitimate
	    interior hole-fills (a piece's own glossy blotch) untouched while opening the gap and
	    any closed background pocket that reaches the contact (e.g. an interior red sliver).

	The connected components of ``solid = comp - remove`` above ``0.25*median`` are the piece
	CORES; each is grown back over the dropped seam by NEAREST core (so the boundary sits at
	the seam, not a midline through it) while the seam pixels themselves stay background. A
	piece's OWN blank carries no dark seam and no background gap, so it is never cut. Accepted
	only when the black-hat peak is strong (``_SEAM_CARVE_TRIGGER``), ``solid`` yields >=2 cores
	(a mated pair in true pixel-to-pixel contact has one core -> ``None`` -> flagged is_cluster)
	and every sub is single-piece-plausible; otherwise ``None`` -> the component is left whole.
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
	barrier = (bh >= thr) & inside
	# The background-coloured gap the step-6 CLOSE invented (fg now, bg in binary_raw).
	bg_inv = inside & (binary_raw_crop == 0)
	# Seam neighbourhood: only bg-invented pockets that reach the dark seam are the contact
	# gap; deep-interior hole-fills stay (they are a piece's own body, refilled downstream).
	d = max(3, int(round(0.010 * working_dim)))
	if d % 2 == 0:
		d += 1
	contested = cv2.dilate(barrier.astype(np.uint8) * 255, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (d, d))) > 0
	nbi, lbi = cv2.connectedComponents((bg_inv).astype(np.uint8), 8)
	touch = np.unique(lbi[contested & bg_inv])
	touch = touch[touch > 0]
	remove = barrier | (np.isin(lbi, touch) if touch.size else np.zeros_like(bg_inv))
	k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
	solid = cv2.morphologyEx((inside & ~remove).astype(np.uint8) * 255, cv2.MORPH_OPEN, k3)
	n, lbl, stats, _ = cv2.connectedComponentsWithStats(solid, 8)
	cores = [l for l in range(1, n) if stats[l, cv2.CC_STAT_AREA] >= 0.25 * median_area]
	if len(cores) < 2:
		return None  # one body -> a mated pair or a single piece; not a clean seam split
	# Grow each core over the dropped seam by NEAREST core, so where two cores meet the
	# boundary sits on the seam; the seam pixels themselves stay background (dropped).
	core_id = np.zeros(comp_mask.shape, dtype=np.int32)
	for i, l in enumerate(cores, start=1):
		core_id[lbl == l] = i
	_, near = cv2.distanceTransformWithLabels(
		(core_id == 0).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL
	)
	lut = np.zeros(int(near.max()) + 1, dtype=np.int32)
	cys, cxs = np.where(core_id > 0)
	lut[near[cys, cxs]] = core_id[cys, cxs]
	grown = lut[near]
	assignable = inside & (remove == 0)
	subs: list[np.ndarray] = []
	for i in range(1, len(cores) + 1):
		region = (((grown == i) & assignable) | (core_id == i)).astype(np.uint8) * 255
		if int((region > 0).sum()) > 0:
			subs.append(region)
	if len(subs) < 2:
		return None
	# Plausibility gate: every sub must look like a single piece, else this was not a clean
	# inter-piece split -> leave the component whole (honest cluster), never emit garbage.
	for s in subs:
		a = int((s > 0).sum())
		if _solidity(s) < _SUB_SOLIDITY_MIN or not (0.45 * median_area <= a <= 1.7 * median_area):
			return None
	return subs


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
	binary_raw_crop: np.ndarray,
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
	Sub masks share ``comp_mask``'s frame, so each is cropped to its bbox (and the
	matching ``binary_raw`` crop with it), split, and the results pasted back at the
	same offset. Depth-bounded by ``_MAX_SPLIT_DEPTH``; a sub that does not separate
	is kept as-is.
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
		# The sub carries only this piece-body's pixels, so intersect binary_raw with it:
		# a neighbour's foreground leaking into the bbox must not count as this sub's gap.
		sub_raw = cv2.bitwise_and(binary_raw_crop[sy:sy + sh, sx:sx + sw], sub_crop)
		parts = _split_component(
			sub_crop, sub_color, sub_raw, median_area, marker_ratio, working_dim, seam_frac,
			split_trigger, depth + 1,
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
	binary_raw_crop: np.ndarray,
	median_area: float,
	marker_ratio: float,
	working_dim: int,
	seam_frac: float,
	split_trigger: float,
	depth: int = 0,
) -> list[np.ndarray] | None:
	"""Try to watershed-split one large component into touching pieces.

	``comp_mask`` is a 0/255 crop, ``color_crop`` the matching BGR crop and
	``binary_raw_crop`` the matching PRE-close foreground (the honest boundary before
	step-6 morphology bridged inter-piece gaps). The seam-carve split is tried first
	(it separates ABUTTING same-colour pieces by dropping the physical + invented
	inter-piece gap); only if it cannot separate the component is the plain colour
	watershed tried, then the dark-seam-seeded rescue, and only if all fail is a
	geometric bisection FORCED. This ordering guarantees the later paths can add
	splits but never remove one. Any sub that comes back still over-sized is re-split
	(:func:`_resplit_subs`). Returns a list of sub-piece masks, or ``None``.
	"""
	# First, carve at the inter-piece seam: this separates ABUTTING same-colour pieces that a
	# colour watershed cannot (it leaks through the seam). The seam (dark gap + close-invented
	# background gap) is DROPPED and each remaining body assigned whole, self-validated by
	# per-sub solidity, so it only fires when it produces clean single pieces.
	carve = _seam_carve_split(comp_mask, color_crop, binary_raw_crop, median_area, working_dim)
	if carve is not None:
		return _resplit_subs(
			carve, color_crop, binary_raw_crop, median_area, marker_ratio, working_dim, seam_frac,
			split_trigger, depth,
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
			subs, color_crop, binary_raw_crop, median_area, marker_ratio, working_dim, seam_frac,
			split_trigger, depth,
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


def _touches_frame(bbox: tuple[int, int, int, int], w: int, h: int) -> bool:
	"""Whether a working-coords bbox ``(x, y, bw, bh)`` reaches the ``w`` x ``h`` image border."""
	x, y, bw, bh = bbox
	return x <= 0 or y <= 0 or x + bw >= w or y + bh >= h


def _raw_touches_frame(
	bbox: tuple[int, int, int, int], comp_mask: np.ndarray, binary_raw: np.ndarray, reach: int,
) -> bool:
	"""Whether a component touches the border, directly or through its PRE-morphology foreground.

	The open of :func:`_morph_clean` can detach a ragged blob from the border by a
	few px (e.g. a vignetting/shadow blob at a photo edge). Within ``reach`` px of the
	border, the ``binary_raw`` connected component(s) overlapping ``comp_mask`` (the
	component's 0/255 crop at ``bbox``) are checked for border contact; unrelated raw
	foreground nearby (a scanner-edge line) does not count.
	"""
	h, w = binary_raw.shape[:2]
	if _touches_frame(bbox, w, h):
		return True
	x, y, bw, bh = bbox
	if x > reach and y > reach and x + bw < w - reach and y + bh < h - reach:
		return False
	x0, y0 = max(0, x - reach), max(0, y - reach)
	x1, y1 = min(w, x + bw + reach), min(h, y + bh + reach)
	_, lab = cv2.connectedComponents((binary_raw[y0:y1, x0:x1] > 0).astype(np.uint8), connectivity=8)
	own = np.unique(lab[y - y0:y - y0 + bh, x - x0:x - x0 + bw][comp_mask > 0])
	own = own[own > 0]
	if own.size == 0:
		return False
	edge = []
	if y0 == 0:
		edge.append(lab[0])
	if y1 == h:
		edge.append(lab[-1])
	if x0 == 0:
		edge.append(lab[:, 0])
	if x1 == w:
		edge.append(lab[:, -1])
	return any(np.isin(e, own).any() for e in edge)


def _frame_reach(working_dim: int) -> int:
	"""How far (px) :func:`_morph_clean` can move a boundary: its close-kernel size."""
	k = max(3, int(round(0.003 * working_dim)))
	if k % 2 == 0:
		k += 1
	return 2 * k + 1


def _strip_band_canonical(
	c: np.ndarray, offset: int, gap: int, dim_along: int, dim_across: int,
) -> tuple[np.ndarray, float] | None:
	"""Band of one white component along one side, in canonical orientation.

	``c`` is the component's bool crop with rows running ALONG the side and column 0
	the column nearest the frame, ``offset`` px away from it. Returns ``(band, width)``
	-- ``band`` a bool array like ``c`` (the component pixels inside the strip band)
	and ``width`` the median per-row strip width (px from the frame) -- or ``None``
	when the component is not a strip along this side (see ``_STRIP_*``).
	"""
	has = c.any(1)
	if not has.any():
		return None
	first = np.argmax(c, 1)
	reach = has & (offset + first < gap)
	if reach.sum() < _STRIP_MIN_SPAN_FRAC * dim_along:
		return None
	# Per-row inner edge = innermost pixel (distance from the frame, exclusive).
	inner = offset + c.shape[1] - np.argmax(c[:, ::-1], 1)
	t = np.nonzero(reach)[0].astype(np.float64)
	e = inner[reach].astype(np.float64)
	width = float(np.median(e))
	if width > _STRIP_MAX_WIDTH_FRAC * dim_across:
		return None
	# Robust straight-line fit of the inner edge (the paper edge is straight but may be
	# skewed): rows where a light piece joins the strip are outliers and are dropped.
	keep = np.ones(len(t), bool)
	coef = np.array([0.0, width])
	for _ in range(4):
		if keep.sum() < 2:
			break
		coef = np.polyfit(t[keep], e[keep], 1)
		res = e - np.polyval(coef, t)
		mad = float(np.median(np.abs(res[keep] - np.median(res[keep]))))
		keep = np.abs(res) <= max(float(_STRIP_BAND_TOL_PX), 3.0 * 1.4826 * mad)
	limit = np.polyval(coef, np.arange(c.shape[0], dtype=np.float64)) + _STRIP_BAND_TOL_PX
	dist = offset + np.arange(c.shape[1])[None, :]
	return c & (dist < limit[:, None]), width


def _frame_strip_mask(
	lab: np.ndarray, binary: np.ndarray, dilate_px: int = _STRIP_DILATE_PX,
) -> tuple[np.ndarray | None, list[dict]]:
	"""Near-white paper strip along the scan frame (defect S3).

	Candidates are foreground pixels of ``binary`` (0/255) that are near-white in
	``lab`` (OpenCV 8-bit Lab, NOT illumination-flattened): L >= ``_STRIP_MIN_L`` and
	chroma <= ``_STRIP_MAX_CHROMA``. An 8-connected candidate component is a strip
	along a side when it comes within ``_STRIP_FRAME_GAP_FRAC`` of that border on at
	least ``_STRIP_MIN_SPAN_FRAC`` of the side's rows and its median per-row width is
	at most ``_STRIP_MAX_WIDTH_FRAC`` of the image dimension. Only the component's
	pixels inside the band along the frame (robust line fit of the per-row inner edge
	+ ``_STRIP_BAND_TOL_PX``) are removed, so a light piece abutting the strip, which
	joins its component but sticks out of the band, is kept. An L-shaped strip is
	handled side by side. The union is dilated by ``dilate_px`` (colour-blend seam).

	Returns ``(mask, strips)``: ``mask`` is a 0/255 uint8 array (``None`` when no strip
	was found) and ``strips`` a list of ``{'side', 'width_px', 'span_frac'}`` (px of
	``lab``) sorted by decreasing span.
	"""
	h, w = binary.shape[:2]
	L = lab[..., 0].astype(np.float32)
	chroma = np.hypot(lab[..., 1].astype(np.float32) - 128.0, lab[..., 2].astype(np.float32) - 128.0)
	white = ((L >= _STRIP_MIN_L) & (chroma <= _STRIP_MAX_CHROMA) & (binary > 0)).astype(np.uint8)
	num, labels, stats, _ = cv2.connectedComponentsWithStats(white, connectivity=8)
	out = np.zeros((h, w), bool)
	strips: list[dict] = []
	for lid in range(1, num):
		x, y, bw, bh = (int(v) for v in stats[lid, :4])
		comp = None
		for side in ("left", "right", "top", "bottom"):
			along, across = (h, w) if side in ("left", "right") else (w, h)
			gap = max(1, int(round(_STRIP_FRAME_GAP_FRAC * across)))
			offset = {"left": x, "right": w - (x + bw), "top": y, "bottom": h - (y + bh)}[side]
			span = bh if side in ("left", "right") else bw
			if offset >= gap or span < _STRIP_MIN_SPAN_FRAC * along:
				continue
			if comp is None:
				comp = labels[y:y + bh, x:x + bw] == lid
			c = {"left": comp, "right": comp[:, ::-1], "top": comp.T, "bottom": comp.T[:, ::-1]}[side]
			got = _strip_band_canonical(c, offset, gap, along, across)
			if got is None:
				continue
			band, width = got
			band = {"left": band, "right": band[:, ::-1], "top": band.T, "bottom": band[:, ::-1].T}[side]
			out[y:y + bh, x:x + bw] |= band
			strips.append({"side": side, "width_px": width, "span_frac": float(span) / along})
	if not out.any():
		return None, []
	m = out.astype(np.uint8) * 255
	if dilate_px > 0:
		k = 2 * int(dilate_px) + 1
		m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
	strips.sort(key=lambda s: -s["span_frac"])
	return m, strips


def _touches_strip(bbox: tuple[int, int, int, int], comp_mask: np.ndarray, strip_zone: np.ndarray) -> bool:
	"""Whether a component reaches ``strip_zone`` (0/255, working coords).

	``strip_zone`` is the strip mask dilated by :func:`_frame_reach` -- the distance
	over which the step-6 closing would have glued a piece to the strip (on the
	E-real-2 sheets the abutting pieces are a few px of background away from the
	strip in the raw foreground, and only the closing merged them). ``comp_mask`` is
	the component's 0/255 crop at ``bbox``.
	"""
	x, y, bw, bh = bbox
	return bool((strip_zone[y:y + bh, x:x + bw][comp_mask > 0] > 0).any())


def _extract_components(
	binary: np.ndarray,
	work_bgr: np.ndarray,
	binary_raw: np.ndarray,
	*,
	split_touching: bool,
	min_area_ratio: float,
	marker_ratio: float,
	split_trigger: float,
	seam_frac: float,
	cluster_ratio: float,
) -> list[tuple[tuple[int, int, int, int], np.ndarray, bool]]:
	"""Label, prune and (optionally) split into per-piece working masks.

	``binary_raw`` is the PRE-close foreground (before step-6 morphology bridged
	inter-piece gaps); its crop is passed to the splitter so an abutting pair's
	dropped gap is the honest boundary rather than a bridged-then-halved seam.

	Returns a list of ``((x, y, w, h), mask_crop, is_cluster)`` in working coords,
	where ``mask_crop`` is a 0/255 uint8 array of the bbox region and
	``is_cluster`` marks a component that triggered a split, could not be
	separated, and stayed larger than ``cluster_ratio`` * median -- i.e. a genuine
	touching/assembled cluster the splitter could not resolve into single pieces.
	Components touching the image border are kept (see :func:`_touches_frame`)
	unless larger than ``cluster_ratio`` * median or wider than ``_FRAME_BLOB_SPAN``
	median sides (a photo margin / floor / lid-outline blob); they stay out of the
	median-area estimate.
	"""
	h, w = binary.shape[:2]
	working_area = h * w
	working_dim = max(h, w)
	num, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)

	# Reject dust and extreme-aspect slivers BEFORE the median so the surviving-piece
	# median is not polluted by non-pieces. Frame-touching components are kept but
	# left out of the median (they may be truncated pieces or photo-margin blobs).
	dust = 0.0005 * working_area
	kept: list[int] = []
	inset: list[int] = []
	for lab in range(1, num):
		if stats[lab, cv2.CC_STAT_AREA] < dust:
			continue
		x0 = int(stats[lab, cv2.CC_STAT_LEFT])
		y0 = int(stats[lab, cv2.CC_STAT_TOP])
		ww = int(stats[lab, cv2.CC_STAT_WIDTH])
		hh = int(stats[lab, cv2.CC_STAT_HEIGHT])
		# Extreme-aspect sliver -> thin border strip / seam shadow, not a piece.
		if max(ww, hh) / max(1, min(ww, hh)) > _MAX_BBOX_ASPECT:
			continue
		kept.append(lab)
		if not _touches_frame((x0, y0, ww, hh), w, h):
			inset.append(lab)
	if not kept:
		return []

	areas = np.array([stats[lab, cv2.CC_STAT_AREA] for lab in (inset or kept)], dtype=np.float64)
	median_area = float(np.median(areas))
	if median_area <= 0:
		return []

	# Drop under-area dust AND thin lines/creases that slipped past the bbox-aspect test.
	# The stroke gate needs the median piece side, so it runs here, after median_area.
	median_side = float(np.sqrt(median_area))
	inset_set = set(inset)
	survivors: list[int] = []
	for lab in kept:
		if stats[lab, cv2.CC_STAT_AREA] < min_area_ratio * median_area:
			continue
		# A frame-touching blob larger than a cluster is the photo margin, floor or a
		# crease between backing sheets, not a (possibly truncated) piece near the edge.
		if lab not in inset_set and (
			stats[lab, cv2.CC_STAT_AREA] > cluster_ratio * median_area
			or max(stats[lab, cv2.CC_STAT_WIDTH], stats[lab, cv2.CC_STAT_HEIGHT]) > _FRAME_BLOB_SPAN * median_side
		):
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
		# Restrict the pre-close foreground to THIS component so a touching neighbour's
		# fg in the same bbox is not read as this component's inter-piece gap.
		raw_crop = cv2.bitwise_and(binary_raw[y:y + hh, x:x + ww], comp_mask)

		subs = None
		if split_touching and area > split_trigger * median_area:
			subs = _split_component(
				comp_mask, color_crop, raw_crop, median_area, marker_ratio, working_dim, seam_frac,
				split_trigger,
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


# ===== Background-fringe rejection tunables (step, _extract_piece / _reject_bg_fringe) =====
# Width of the interior boundary band scanned for background-coloured fringe, as a fraction
# of the piece side (sqrt of mask area). The working->full-res staircase, the dropped-seam
# edge and a stray background sliver all sit within a few percent of the side; 0.04 reaches
# them without scooping into piece interior.
_FRINGE_BAND_FRAC = 0.04
# Back off the whole fringe removal if it would drop more than this fraction of the mask
# area: a genuinely background-coloured piece (or a crop with too little background margin to
# make D bimodal) would otherwise be eaten. A real fringe is a thin rim, well under this.
_FRINGE_MAX_REMOVE_FRAC = 0.12


def _bg_distance_cie(
	rgb_crop: np.ndarray, bg_lab: np.ndarray, luma_weight: float, chroma_weight: float
) -> np.ndarray:
	"""Weighted CIE-Lab distance from each crop pixel to the background, as float32.

	``bg_lab`` is the GLOBAL background on OpenCV's 8-bit Lab scale (L 0..255, a/b offset
	128); it is converted to CIE (L 0..100, a/b centred 0) to match the float ``RGB2LAB``
	crop. The same chroma-dominated weighting (``luma_weight``/``chroma_weight``) as the
	detector, so a cast shadow (near-zero chroma delta) stays low and a coloured piece edge
	stays high. Shared by :func:`_refine_boundary_band` and :func:`_reject_bg_fringe`.
	"""
	lab = cv2.cvtColor(np.ascontiguousarray(rgb_crop, np.float32) / 255.0, cv2.COLOR_RGB2LAB)
	bg_cie = np.array(
		[bg_lab[0] * 100.0 / 255.0, bg_lab[1] - 128.0, bg_lab[2] - 128.0], dtype=np.float32
	)
	diff = lab - bg_cie.reshape(1, 1, 3)
	return np.sqrt(
		luma_weight * diff[:, :, 0] ** 2
		+ chroma_weight * (diff[:, :, 1] ** 2 + diff[:, :, 2] ** 2)
	).astype(np.float32)


def _reject_bg_fringe(mask: np.ndarray, D: np.ndarray) -> np.ndarray:
	"""Peel a background-coloured fringe off the INTERIOR rim of a piece mask.

	A refined mask can still carry a thin ring of background-coloured pixels: the residual
	staircase over-reach, the slightly-inset edge where an abutting-pair seam was dropped, or
	a stray sliver of the surface the mask enclosed (e.g. a red pocket at a piece corner). All
	share one signature -- a low background-distance ``D`` (they ARE the surface colour), which
	sits far below the piece body on the chroma-dominated scale (e.g. a red mat at a*~+50 vs a
	piece at a*~+5..20). A per-crop Otsu on ``D`` (the padded crop is bimodal: piece body +
	background margin) sets the cut; only mask pixels BOTH in a thin interior boundary band
	(``_FRINGE_BAND_FRAC`` of the piece side) AND below that cut are dropped. Band-restricting
	spares the interior (a genuine interior hole is refilled downstream anyway), and the whole
	removal is backed off if it would breach ``_FRINGE_MAX_REMOVE_FRAC`` -- so a genuinely
	background-hued piece, or a crop too piece-filled to be bimodal, is left intact. Pure.
	"""
	m = mask > 0
	area = int(m.sum())
	if area == 0:
		return mask
	Dn = cv2.normalize(D, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
	t, _ = cv2.threshold(Dn, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
	bg_like = Dn < t
	side = float(np.sqrt(area))
	rb = max(1, int(round(_FRINGE_BAND_FRAC * side)))
	eroded = cv2.erode(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * rb + 1, 2 * rb + 1)))
	band = m & (eroded == 0)
	remove = band & bg_like
	rc = int(remove.sum())
	if rc == 0 or rc > _FRINGE_MAX_REMOVE_FRAC * area:
		return mask
	out = mask.copy()
	out[remove] = 0
	if not (out > 0).any():
		return mask
	return out


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

	# Background-distance map D over the whole crop, in weighted CIE-Lab units.
	D = _bg_distance_cie(rgb_crop, bg_lab, luma_weight, chroma_weight)

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
	# Drop any background-coloured fringe on the interior rim (staircase over-reach, dropped-
	# seam edge, or a stray surface sliver) before colour/fill is derived. Reuses the same
	# weighted-Lab background distance as the refine step (recomputed on the same crop).
	mask_full = _reject_bg_fringe(
		mask_full, _bg_distance_cie(rgb_crop, bg_lab, luma_weight, chroma_weight)
	)
	# Peel the interior-rim cast-shadow halo BEFORE any colour/fill is derived, so the
	# mean colour, the mean-fill and the rotation branch all inherit the clean mask.
	mask_full = _shrink_edge_shadow(mask_full, rgb_crop, max(ow, oh))
	# Enforce the solid, simply-connected piece invariant (single blob, no holes,
	# no specks) BEFORE the mean-fill so mask and img stay consistent: filled holes
	# keep their original colour in img, removed specks get mean-filled below.
	mask_full = _clean_piece_mask(mask_full)

	return _compose_piece_fullres(mask_full, rgb_crop, ox, oy, W, H, local_cnt, normalize_rotation)


def _compose_piece_fullres(
	mask_full: np.ndarray,
	rgb_crop: np.ndarray,
	ox: int,
	oy: int,
	W: int,
	H: int,
	rect_cnt: np.ndarray,
	normalize_rotation: bool,
) -> dict | None:
	"""Turn a FINAL full-res crop mask into a piece record (shared by both segmenters).

	``mask_full`` is the uint8 0/255 piece mask of the crop ``rgb_crop`` whose
	top-left corner sits at ``(ox, oy)`` of the ``W x H`` photo. The returned
	``contour`` is the largest external contour of ``mask_full`` in photo
	coordinates; ``rect_cnt`` (crop-local N x 2 points) feeds the ``minAreaRect``
	that sets the rotation angle. The background of the crop is filled with the
	piece's mean colour and, with ``normalize_rotation``, the crop is rotated to
	axis-align that rect. Returns a dict without ``index``/``is_cluster``/
	``touches_frame`` (assigned by the caller), or ``None`` if the mask is empty.
	"""
	ow, oh = mask_full.shape[1], mask_full.shape[0]
	local_cnt = rect_cnt
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


# ===== Flatbed-scan path (segment_scan) =====
# Rim band used to estimate the scan background: 100..250 px from each border at
# 300 dpi (inside the scanner's white margins, outside most pieces), in mm so it
# scales with the dpi. Port of tools/diagnostico/gemeos/esym.rim_bg.
_SCAN_RIM_MM = (100 * 25.4 / 300.0, 250 * 25.4 / 300.0)
# Robust-mode refinement of the rim median: iterations and Lab radius (8-bit units).
_SCAN_RIM_ITERS = 3
_SCAN_RIM_RADIUS = 15.0
# Weights of the squared (dL, da, db) in the scan threshold distance.
_SCAN_LAB_WEIGHTS = (0.5, 1.0, 1.0)
# Roughness diagnostic (same definition as tools/diagnostico/forma/shapelib.analyse_v2):
# contour resampled to this many points, then smoothed with this sigma (in samples).
_ROUGH_SAMPLES = 1200
_ROUGH_SIGMA = 6.0


def _rim_background(lab: np.ndarray, mm_per_px: float) -> np.ndarray:
	"""Background colour (OpenCV 8-bit Lab, float) estimated on the scan rim.

	Pixels of the band ``_SCAN_RIM_MM`` from each border are pooled; the median is
	then refined ``_SCAN_RIM_ITERS`` times as the median of the pixels within
	``_SCAN_RIM_RADIUS`` of the current estimate (a robust mode that ignores the
	pieces lying in the band). On images too small for the band, the band is
	clamped to the central half so it never inverts or empties.
	"""
	h, w = lab.shape[:2]
	lo = int(round(_SCAN_RIM_MM[0] / mm_per_px))
	hi = int(round(_SCAN_RIM_MM[1] / mm_per_px))
	hi = max(1, min(hi, min(h, w) // 2))
	lo = max(0, min(lo, hi - 1))
	pts = np.concatenate([
		lab[lo:hi, lo:w - lo].reshape(-1, 3), lab[h - hi:h - lo, lo:w - lo].reshape(-1, 3),
		lab[lo:h - lo, lo:hi].reshape(-1, 3), lab[lo:h - lo, w - hi:w - lo].reshape(-1, 3),
	]).astype(np.float32)
	m = np.median(pts, axis=0)
	for _ in range(_SCAN_RIM_ITERS):
		near = pts[np.sqrt(((pts - m) ** 2).sum(1)) < _SCAN_RIM_RADIUS]
		if len(near) == 0:
			break
		m = np.median(near, axis=0)
	return m


def _odd_kernel(mm: float, mm_per_px: float) -> int:
	"""Side (px, odd, >= 1) of a square kernel of ``mm`` millimetres."""
	k = max(1, int(round(mm / mm_per_px)))
	return k if k % 2 == 1 else k + 1


def _scan_open_mask(lab: np.ndarray, bg: np.ndarray, threshold: float, open_px: int) -> np.ndarray:
	"""Opened-only full-res foreground of a scan (first half of :func:`_scan_threshold_mask`).

	Distance ``sqrt(0.5 dL^2 + da^2 + db^2)`` in OpenCV 8-bit Lab units above
	``threshold``, then a square-kernel opening (``open_px``). Returns uint8 0/255.
	Kept separately because the closing bridges sub-millimetre gaps between pieces.
	"""
	wts = np.asarray(_SCAN_LAB_WEIGHTS, np.float32)
	d = np.sqrt((((lab - np.asarray(bg, np.float32)) ** 2) * wts).sum(-1))
	m = (d > threshold).astype(np.uint8) * 255
	return cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((open_px, open_px), np.uint8))


def _scan_threshold_mask(lab: np.ndarray, bg: np.ndarray, threshold: float, open_px: int, close_px: int) -> np.ndarray:
	"""Full-res foreground of a scan: weighted Lab distance to ``bg`` above ``threshold``.

	Distance ``sqrt(0.5 dL^2 + da^2 + db^2)`` in OpenCV 8-bit Lab units, then a
	square-kernel opening (``open_px``) and closing (``close_px``). Returns uint8 0/255.
	"""
	m = _scan_open_mask(lab, bg, threshold, open_px)
	return cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((close_px, close_px), np.uint8))


def _voronoi_from_contours(shape: tuple[int, int], contours: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
	"""Voronoi partition of the image by filled piece contours.

	Returns ``(vor, dist)``: ``vor`` (int32) holds, for every pixel, ``q + 1`` of
	the nearest piece ``contours[q]`` (pixels inside a piece get its own label);
	``dist`` (float32) is the Euclidean distance (px) to the nearest piece pixel
	(0 inside pieces).
	"""
	H, W = shape
	lab_img = np.zeros((H, W), np.int32)
	for q, c in enumerate(contours):
		cv2.fillPoly(lab_img, [np.asarray(c).reshape(-1, 1, 2).astype(np.int32)], q + 1)
	inv = (lab_img == 0).astype(np.uint8)
	dist, lbl = cv2.distanceTransformWithLabels(inv, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
	# lbl numbers the zero pixels of ``inv`` (piece pixels) 1..n in raster order;
	# map each one to the label of the piece it belongs to.
	zero = np.flatnonzero(inv.ravel() == 0)
	lut = np.zeros(int(lbl.max()) + 1, np.int32)
	lut[np.arange(1, len(zero) + 1)] = lab_img.ravel()[zero]
	return lut[lbl], dist


def _contour_roughness(contour: np.ndarray) -> float:
	"""Perimeter of the contour over that of its smoothed version (>= 1; 1 = smooth).

	The closed contour is resampled to ``_ROUGH_SAMPLES`` equidistant points and
	smoothed with a circular Gaussian of ``_ROUGH_SIGMA`` samples (same definition
	as ``rough`` in tools/diagnostico/forma/shapelib.analyse_v2). Diagnostic only.
	"""
	c = np.asarray(contour, np.float64).reshape(-1, 2)
	if len(c) < 3:
		return 1.0
	p = np.vstack([c, c[:1]])
	s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])
	if s[-1] <= 0:
		return 1.0
	t = np.linspace(0.0, s[-1], _ROUGH_SAMPLES, endpoint=False)
	r = np.c_[np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])]
	rs = _circular_gaussian(r, _ROUGH_SIGMA)

	def _per(a: np.ndarray) -> float:
		return float(np.sum(np.linalg.norm(np.diff(np.vstack([a, a[:1]]), axis=0), axis=1)))

	ps = _per(rs)
	return _per(r) / ps if ps > 0 else 1.0


# ===== Contact groups on scans (interlocked / touching pieces) =====
# Two pieces are a contact pair when their bboxes are closer than _CONTACT_BBOX_GAP_MM
# (negative gap = overlapping bboxes) or their masks, each dilated by
# _CONTACT_DILATE_MM, overlap (contour distance <= 2 x that).
_CONTACT_DILATE_MM = 0.6
_CONTACT_BBOX_GAP_MM = 1.0
# Core of a member = its old mask AND the threshold, eroded by this much (largest
# component): the body that surely belongs to it. 2 mm cuts the thin shadow bridges that
# join a neighbour's tab to it, and is far below the half-width of a piece body.
_CONTACT_CORE_MM = 2.0
# Black-hat structuring element (mm) of the watershed landscape: wider than the dark
# gap/shadow line between abutting pieces (~0.3..1 mm), narrower than a tab neck.
_CONTACT_BLACKHAT_MM = 1.5
# Opening radius (mm) that strips thin flood spurs (a shadow line along the neighbour)
# from a watershed region; the removed pixels go to the nearest kept region.
_CONTACT_SPUR_MM = 0.5
# Holes of a member's foreground smaller than this (mm^2) are filled before its core is
# eroded (dark texture spots under the threshold), larger ones (a blank's green hole) are not.
_CONTACT_HOLE_MM2 = 4.0
# A foreground component counts as a piece in the connectivity bijection when its area is
# at least this fraction of the median piece area of the scan.
_CONTACT_MIN_AREA_FRAC = 0.3
# The new region of a member is clipped to the usual band around the low-res contours
# when that keeps at least this fraction of it (same shadow extent as the normal path).
_CONTACT_BAND_KEEP = 0.95
# A member whose new mask has IoU >= this with its old one is "unchanged".
_CONTACT_SAME_IOU = 0.98
# Shape validation of a partition (src.shape.analyse): admissible side chord range, and an
# F side shorter than _CONTACT_FALSE_FLAT_MM is a false flat (a cut tab or a straight cut).
_CONTACT_CHORD_MM = (15.5, 21.0)
_CONTACT_FALSE_FLAT_MM = 17.0
# Violation count of a piece whose 4 corners are not found.
_CONTACT_NOT_OK = 3


def _bbox_gap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
	"""Gap (px) between two ``(x, y, w, h)`` boxes: max axis separation, negative when they overlap."""
	ax, ay, aw, ah = a
	bx, by, bw, bh = b
	return float(max(bx - (ax + aw), ax - (bx + bw), by - (ay + ah), ay - (by + bh)))


def _contour_distance(a: np.ndarray, b: np.ndarray) -> float:
	"""Minimum distance (px) between two closed contours (``(n, 2)``); 0 if the filled shapes overlap."""
	a = np.asarray(a, np.int32).reshape(-1, 2)
	b = np.asarray(b, np.int32).reshape(-1, 2)
	x0, y0 = np.minimum(a.min(0), b.min(0)) - 2
	x1, y1 = np.maximum(a.max(0), b.max(0)) + 3
	ma = np.zeros((y1 - y0, x1 - x0), np.uint8)
	mb = np.zeros_like(ma)
	cv2.drawContours(ma, [(a - [x0, y0]).reshape(-1, 1, 2)], -1, 1, thickness=cv2.FILLED)
	cv2.drawContours(mb, [(b - [x0, y0]).reshape(-1, 1, 2)], -1, 1, thickness=cv2.FILLED)
	if (ma & mb).any():
		return 0.0
	d = cv2.distanceTransform((1 - ma).astype(np.uint8), cv2.DIST_L2, 5)
	return float(d[mb > 0].min())


def _contact_groups(contours: list[np.ndarray], eligible: list[bool], mm_per_px: float) -> list[list[int]]:
	"""Groups (connected components of the contact-pair graph) of size >= 2, as sorted index lists.

	A pair (both ``eligible``) is in contact when the bbox gap is below
	``_CONTACT_BBOX_GAP_MM`` or the contours are within ``2 * _CONTACT_DILATE_MM``.
	"""
	n = len(contours)
	boxes = [cv2.boundingRect(np.asarray(c).astype(np.int32).reshape(-1, 1, 2)) for c in contours]
	gap_px = _CONTACT_BBOX_GAP_MM / mm_per_px
	near_px = 2.0 * _CONTACT_DILATE_MM / mm_per_px
	parent = list(range(n))

	def find(i: int) -> int:
		while parent[i] != i:
			parent[i] = parent[parent[i]]
			i = parent[i]
		return i

	for i in range(n):
		if not eligible[i]:
			continue
		for j in range(i + 1, n):
			if not eligible[j]:
				continue
			g = _bbox_gap(boxes[i], boxes[j])
			if g > max(gap_px, near_px):
				continue
			if g < gap_px or _contour_distance(contours[i], contours[j]) <= near_px:
				parent[find(i)] = find(j)
	groups: dict[int, list[int]] = {}
	for i in range(n):
		if eligible[i]:
			groups.setdefault(find(i), []).append(i)
	return sorted((sorted(g) for g in groups.values() if len(g) >= 2), key=lambda g: g[0])


def _priority_flood(height: np.ndarray, markers: np.ndarray, region: np.ndarray) -> np.ndarray:
	"""Marker watershed by priority flood (4-connected) of ``height`` inside ``region``.

	``markers`` (int32) holds labels > 0 on the seeds and 0 elsewhere; every pixel of
	``region`` reachable from a seed gets the label of the seed whose flood reaches it at
	the lowest water level (the max of ``height`` along the path). Unlike
	``cv2.watershed``, which floods by the colour difference between neighbours, this
	floods the given landscape itself. Returns the label image (0 where not reached).
	"""
	import heapq
	h, w = height.shape
	lab = markers.astype(np.int32).copy().ravel()
	reg = region.ravel()
	hf = height.astype(np.float64).ravel()
	unl = (region & (markers == 0)).astype(np.uint8)
	cross = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], np.uint8)
	front = (markers > 0) & (cv2.dilate(unl, cross) > 0)
	heap: list[tuple[float, int, int, int]] = []
	cnt = 0
	for idx in np.flatnonzero(front.ravel()):
		heap.append((-np.inf, cnt, int(idx), int(lab[idx])))
		cnt += 1
	heapq.heapify(heap)
	done = (lab > 0) & ~front.ravel()   # seeds behind the front never expand
	while heap:
		lev, _, idx, lbl = heapq.heappop(heap)
		if done[idx]:
			continue
		done[idx] = True
		lab[idx] = lbl
		y, x = divmod(idx, w)
		for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
			if 0 <= ny < h and 0 <= nx < w:
				n_idx = ny * w + nx
				if reg[n_idx] and not done[n_idx]:
					cnt += 1
					heapq.heappush(heap, (max(lev, hf[n_idx]), cnt, n_idx, lbl))
	return lab.reshape(h, w)


def _largest_filled(mask: np.ndarray) -> tuple[np.ndarray | None, np.ndarray | None]:
	"""Largest external contour of a 0/1 mask and its filled mask (uint8 0/255); ``(None, None)`` if empty."""
	cnts, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
	if not cnts:
		return None, None
	c = max(cnts, key=cv2.contourArea)
	m = np.zeros(mask.shape, np.uint8)
	cv2.drawContours(m, [c], -1, 255, thickness=cv2.FILLED)
	return c.reshape(-1, 2), m


def _shape_violations(contours: list[np.ndarray], mm_per_px: float, interlocked: bool) -> tuple[list[int], list[dict]]:
	"""Per-member shape violations of a partition and a short description per member.

	Each member is analysed with :func:`src.shape.analyse`: no 4 corners counts
	``_CONTACT_NOT_OK``; each side chord outside ``_CONTACT_CHORD_MM`` and each F side
	shorter than ``_CONTACT_FALSE_FLAT_MM`` counts 1. With ``interlocked`` (the members
	touch, no visible gap), the side of each member facing its nearest other member must
	be complementary (T against B, :func:`src.shape.side_complement`), else 1 more.
	"""
	from .shape import analyse, side_complement
	shapes = [analyse(c, mm_per_px) for c in contours]
	viol, info = [], []
	for s in shapes:
		if not s.ok:
			viol.append(_CONTACT_NOT_OK)
			info.append({"ok": False})
			continue
		v = 0
		for sd in s.sides:
			if not (_CONTACT_CHORD_MM[0] <= sd.chord_mm <= _CONTACT_CHORD_MM[1]):
				v += 1
			if sd.kind == "F" and sd.chord_mm < _CONTACT_FALSE_FLAT_MM:
				v += 1
		viol.append(v)
		info.append({"ok": True, "cls": s.cls, "chords_mm": [round(float(x), 2) for x in s.lens]})
	if interlocked and len(contours) >= 2:
		pts_mm = [np.asarray(c, np.float64).reshape(-1, 2) * mm_per_px for c in contours]

		def facing(k: int, j: int) -> int:
			"""Side of member ``k`` closest (mean point distance) to member ``j``'s contour."""
			s = shapes[k]
			other = pts_mm[j][::4]
			best, best_i = np.inf, 0
			for i in range(4):
				a, b = int(s.corners[i]), int(s.corners[(i + 1) % 4])
				seg = s.c[a:b + 1] if b > a else np.vstack([s.c[a:], s.c[:b + 1]])
				d = float(np.sqrt(((seg[::4, None, :] - other[None, :, :]) ** 2).sum(-1)).min(1).mean())
				if d < best:
					best, best_i = d, i
			return best_i

		for k in range(len(contours)):
			if not shapes[k].ok:
				continue
			ck = pts_mm[k].mean(0)
			others = [j for j in range(len(contours)) if j != k and shapes[j].ok]
			if not others:
				continue
			j = min(others, key=lambda q: float(np.linalg.norm(pts_mm[q].mean(0) - ck)))
			ik, ij = facing(k, j), facing(j, k)
			rms, _ = side_complement(shapes[k].sides[ik], shapes[j].sides[ij])
			info[k]["face"] = {"com": j, "kinds": shapes[k].sides[ik].kind + shapes[j].sides[ij].kind,
							   "rms_mm": None if not np.isfinite(rms) else round(float(rms), 3)}
			if not np.isfinite(rms):
				viol[k] += 1
	return viol, info


def _fill_small_holes(mask: np.ndarray, max_area_px: float) -> np.ndarray:
	"""``mask`` (bool) with its holes smaller than ``max_area_px`` filled (dark texture spots)."""
	holes = (~mask).astype(np.uint8)
	n, cc, st, _ = cv2.connectedComponentsWithStats(holes, connectivity=4)
	out = mask.copy()
	h, w = mask.shape
	for r in range(1, n):
		x, y, bw, bh, a = st[r]
		if a < max_area_px and x > 0 and y > 0 and x + bw < w and y + bh < h:
			out[cc == r] = True
	return out


def _match_components(overlap: np.ndarray) -> list[int] | None:
	"""Bijection component -> member maximising the total overlap (``overlap[r, k]``), or ``None``.

	Exhaustive over permutations up to 6 members, greedy beyond. ``None`` when some
	component would get a member it does not overlap at all.
	"""
	import itertools
	n = overlap.shape[0]
	if n <= 6:
		best, best_p = -1.0, None
		for perm in itertools.permutations(range(n)):
			s = float(sum(overlap[r, perm[r]] for r in range(n)))
			if s > best:
				best, best_p = s, list(perm)
		assign = best_p
	else:
		assign = [-1] * n
		used: set[int] = set()
		for flat in np.argsort(-overlap, axis=None):
			r, k = divmod(int(flat), n)
			if assign[r] < 0 and k not in used:
				assign[r] = k
				used.add(k)
	if assign is None or any(overlap[r, assign[r]] <= 0 for r in range(n)):
		return None
	return assign


def _resolve_contact_group(
	members: list[int],
	contours: list[np.ndarray],
	thr: np.ndarray,
	thr_open: np.ndarray,
	lab: np.ndarray,
	vor: np.ndarray,
	band: np.ndarray,
	mm_per_px: float,
	close_px: int,
	min_area_px: float,
) -> dict | None:
	"""Re-partition the foreground of one contact group among its members.

	Window = union of the members' Voronoi cells (without the band, so a piece the
	low-resolution split cut badly is recovered whole). Foreground = the opened-only
	threshold (the closing would bridge sub-millimetre gaps), 4-connected components.

	(a) Connectivity: when the components of at least ``min_area_px`` are exactly as
	many as the members, each goes to the member whose old mask it overlaps (best
	bijection); this fixes a tab sitting in a neighbour's blank with a visible gap.
	Otherwise each component is handled alone against the member cores (old mask AND
	foreground, small holes filled, eroded by ``_CONTACT_CORE_MM``, largest
	component): touching exactly one core it goes to that member, touching none it keeps
	the Voronoi assignment. (b) A component touching >= 2 cores (no visible gap) is
	split by a priority-flood watershed from the cores over black-hat(L*) + Lab
	gradient (each normalised by its 99th percentile in the component): the boundary
	follows the dark gap/shadow line and the colour edge, not the tab neck (a distance
	transform would cut there); thin flood spurs (a shadow line along the neighbour)
	are then opened away (``_CONTACT_SPUR_MM``) and handed to the nearest region.
	Each member's region is finally closed (``close_px``), clipped to ``band`` (the
	``band_mm`` band of the low-res contours, as the normal boundary; skipped for a member
	when it would remove more than ``1 - _CONTACT_BAND_KEEP`` of the region, i.e. the
	low-res contours missed part of the piece) and its largest external contour filled.

	Returns ``None`` when a needed core or a new region is empty (group left as is),
	else ``{'contours': [new contours, photo px], 'iou': [IoU new vs old per member],
	'metodo': 'conectividade'|'watershed'}``.
	"""
	pts = [np.asarray(contours[q]).reshape(-1, 2).astype(np.int32) for q in members]
	H, W = thr.shape
	ids = np.array([q + 1 for q in members])
	ys, xs = np.nonzero(np.isin(vor, ids))
	allp = np.vstack(pts)
	pad = close_px + 2
	x0 = max(0, min(int(xs.min()), int(allp[:, 0].min())) - pad)
	y0 = max(0, min(int(ys.min()), int(allp[:, 1].min())) - pad)
	x1 = min(W, max(int(xs.max()), int(allp[:, 0].max())) + pad + 1)
	y1 = min(H, max(int(ys.max()), int(allp[:, 1].max())) + pad + 1)
	org = np.array([x0, y0])
	vor_c = vor[y0:y1, x0:x1]
	win = np.isin(vor_c, ids)
	band_c = band[y0:y1, x0:x1]
	fg = (thr_open[y0:y1, x0:x1] > 0) & win
	shp = fg.shape
	old_masks = []
	for p in pts:
		m = np.zeros(shp, np.uint8)
		cv2.drawContours(m, [(p - org).reshape(-1, 1, 2)], -1, 1, thickness=cv2.FILLED)
		old_masks.append(m > 0)
	# Voronoi member (1-based position in ``members``) of every window pixel.
	lut = np.zeros(int(vor_c.max()) + 2, np.int32)
	lut[ids] = np.arange(1, len(members) + 1)
	vor_k = lut[vor_c]
	n, cc, st, _ = cv2.connectedComponentsWithStats(fg.astype(np.uint8), connectivity=4)
	sig = [r for r in range(1, n) if st[r, cv2.CC_STAT_AREA] >= min_area_px]
	new_lbl = np.zeros(shp, np.int32)
	metodo = "conectividade"
	assign = None
	if len(sig) == len(members):
		ov = np.array([[float((old_masks[k] & (cc == r)).sum()) for k in range(len(members))] for r in sig])
		assign = _match_components(ov)
	if assign is not None:
		for r in range(1, n):
			new_lbl[cc == r] = vor_k[cc == r]
		for r, k in zip(sig, assign):
			new_lbl[cc == r] = k + 1
	else:
		core_lbl = np.zeros(shp, np.int32)
		core_r = int(round(_CONTACT_CORE_MM / mm_per_px))
		kcore = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * core_r + 1, 2 * core_r + 1))
		hole_px = _CONTACT_HOLE_MM2 / (mm_per_px * mm_per_px)
		for k in range(len(members)):
			body = _fill_small_holes(old_masks[k] & fg, hole_px)
			er = cv2.erode(body.astype(np.uint8), kcore)
			nn, ccc, sst, _ = cv2.connectedComponentsWithStats(er, connectivity=4)
			if nn < 2:
				return None
			core_lbl[ccc == 1 + int(np.argmax(sst[1:, cv2.CC_STAT_AREA]))] = k + 1
		bh = grad = None
		for r in range(1, n):
			comp = cc == r
			touched = np.unique(core_lbl[comp])
			touched = touched[touched > 0]
			if len(touched) == 0:
				new_lbl[comp] = vor_k[comp]
			elif len(touched) == 1:
				new_lbl[comp] = int(touched[0])
			else:
				metodo = "watershed"
				if bh is None:
					L = np.clip(lab[y0:y1, x0:x1, 0], 0, 255).astype(np.uint8)
					bk = max(3, int(round(_CONTACT_BLACKHAT_MM / mm_per_px)) | 1)
					bh = cv2.morphologyEx(L, cv2.MORPH_BLACKHAT,
										  cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (bk, bk))).astype(np.float32)
					sm = cv2.GaussianBlur(np.ascontiguousarray(lab[y0:y1, x0:x1], np.float32), (0, 0), 1.0)
					grad = np.zeros(shp, np.float32)
					for ch in range(3):
						gx = cv2.Sobel(sm[:, :, ch], cv2.CV_32F, 1, 0, ksize=3)
						gy = cv2.Sobel(sm[:, :, ch], cv2.CV_32F, 0, 1, ksize=3)
						grad = np.maximum(grad, np.sqrt(gx * gx + gy * gy))
				height = (bh / max(float(np.percentile(bh[comp], 99)), 1.0)
						  + grad / max(float(np.percentile(grad[comp], 99)), 1.0))
				fl = _priority_flood(height, np.where(comp, core_lbl, 0), comp)
				new_lbl[comp] = fl[comp]
	# Thin spurs: the flood can run along a shadow line hugging the neighbour (a cast
	# shadow is foreground and belongs to neither body). Open each member's region by
	# _CONTACT_SPUR_MM and hand every removed pixel to the nearest kept region.
	if metodo == "watershed":
		sr = max(1, int(round(_CONTACT_SPUR_MM / mm_per_px)))
		kspur = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * sr + 1, 2 * sr + 1))
		kept = np.zeros(shp, np.int32)
		for k in range(len(members)):
			kept[cv2.morphologyEx((new_lbl == k + 1).astype(np.uint8), cv2.MORPH_OPEN, kspur) > 0] = k + 1
		removed = (new_lbl > 0) & (kept == 0)
		if removed.any() and (kept > 0).any():
			_, near = cv2.distanceTransformWithLabels((kept == 0).astype(np.uint8), cv2.DIST_L2, 5,
													  labelType=cv2.DIST_LABEL_PIXEL)
			zero = np.flatnonzero(kept.ravel() > 0)
			lut2 = np.zeros(int(near.max()) + 1, np.int32)
			lut2[np.arange(1, len(zero) + 1)] = kept.ravel()[zero]
			new_lbl = np.where(removed, lut2[near], new_lbl)
	kclose = np.ones((close_px, close_px), np.uint8)
	new_contours, ious = [], []
	for k in range(len(members)):
		own = new_lbl == k + 1
		m = (cv2.morphologyEx(own.astype(np.uint8), cv2.MORPH_CLOSE, kclose) > 0) & win
		m &= ~((new_lbl > 0) & ~own)
		mb = m & band_c
		if mb.sum() >= _CONTACT_BAND_KEEP * m.sum():
			m = mb
		c, filled = _largest_filled(m)
		if c is None:
			return None
		fm = filled > 0
		new_contours.append(c + org)
		union = float((fm | old_masks[k]).sum())
		ious.append(float((fm & old_masks[k]).sum()) / union if union else 1.0)
	return {"contours": new_contours, "iou": ious, "metodo": metodo}


def _scan_record(c: np.ndarray, rgb: np.ndarray, pad_ratio: float, normalize_rotation: bool) -> dict | None:
	"""Piece record (``_compose_piece_fullres`` keys) of a full-res contour ``c`` (photo px)."""
	H, W = rgb.shape[:2]
	c = np.asarray(c).reshape(-1, 2)
	ox, oy, ow, oh = cv2.boundingRect(c.astype(np.int32).reshape(-1, 1, 2))
	pad = int(round(pad_ratio * max(ow, oh)))
	ox, oy = max(0, ox - pad), max(0, oy - pad)
	ow, oh = min(W - ox, ow + 2 * pad), min(H - oy, oh + 2 * pad)
	local = (c - np.array([ox, oy])).astype(np.int32)
	mask_full = np.zeros((oh, ow), np.uint8)
	cv2.drawContours(mask_full, [local.reshape(-1, 1, 2)], -1, 255, thickness=cv2.FILLED)
	return _compose_piece_fullres(mask_full, rgb[oy:oy + oh, ox:ox + ow].copy(), ox, oy, W, H, local, normalize_rotation)


def _split_scan_contacts(
	pieces: list[dict],
	thr: np.ndarray,
	thr_open: np.ndarray,
	lab: np.ndarray,
	vor: np.ndarray,
	band: np.ndarray,
	rgb: np.ndarray,
	mm_per_px: float,
	close_px: int,
	pad_ratio: float,
	normalize_rotation: bool,
) -> None:
	"""Re-partition each contact group of ``pieces`` in place and flag its members ``contacto``.

	Groups (:func:`_contact_groups`, every piece eligible, ``is_cluster`` ones included)
	are re-partitioned by :func:`_resolve_contact_group`. The new partition is adopted
	only if some member changed (IoU < ``_CONTACT_SAME_IOU``) and it has no more shape
	violations (:func:`_shape_violations`) than the old one; otherwise the old records are
	kept bit for bit (and, inside an adopted group, so are the members that did not
	change). An adopted member is ``refined``; an ``is_cluster`` member whose new
	shape has no violation stops being a cluster. Every member gets ``contacto = {'com':
	[index of the other members], 'confianca': 'alta'|'baixa', 'metodo':
	'conectividade'|'watershed'|'nenhum' (group left as is: empty core), 'alterado':
	bool}``; ``baixa`` when the members touch
	(watershed) or the partition changed, and the final partition still has a shape
	violation.
	"""
	contours = [np.asarray(p["contour"]).reshape(-1, 2) for p in pieces]
	areas = [float(p["area_px"]) for p in pieces if not p["is_cluster"]]
	if not areas:
		return
	min_area = _CONTACT_MIN_AREA_FRAC * float(np.median(areas))
	for g in _contact_groups(contours, [True] * len(pieces), mm_per_px):
		r = _resolve_contact_group(g, contours, thr, thr_open, lab, vor, band, mm_per_px, close_px, min_area)
		interlocked = r is not None and r["metodo"] == "watershed"
		changed = r is not None and min(r["iou"]) < _CONTACT_SAME_IOU
		final_c = [contours[q] for q in g]
		if changed:
			v_old, _ = _shape_violations(final_c, mm_per_px, interlocked)
			v_new, _ = _shape_violations(r["contours"], mm_per_px, interlocked)
			recs = [_scan_record(c, rgb, pad_ratio, normalize_rotation) for c in r["contours"]]
			if sum(v_new) <= sum(v_old) and all(rec is not None for rec in recs):
				for q, rec, v, iou in zip(g, recs, v_new, r["iou"]):
					if iou >= _CONTACT_SAME_IOU:
						continue   # this member did not change: keep its record bit for bit
					p = pieces[q]
					p.update(rec)
					p["refined"] = True
					p["roughness"] = _contour_roughness(p["contour"])
					if p["is_cluster"] and v == 0:
						p["is_cluster"] = False
						p.pop("piece_type", None)
				final_c = [c if iou < _CONTACT_SAME_IOU else contours[q] for q, c, iou in zip(g, r["contours"], r["iou"])]
			else:
				changed = False
		baixa = False
		if changed or interlocked:
			v_fin, _ = _shape_violations(final_c, mm_per_px, interlocked)
			baixa = sum(v_fin) > 0
		for q in g:
			pieces[q]["contacto"] = {
				"com": [int(pieces[o]["index"]) for o in g if o != q],
				"confianca": "baixa" if baixa else "alta",
				"metodo": r["metodo"] if r is not None else "nenhum",
				"alterado": bool(changed),
			}


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
		'background_lab': (L, a, b), 'working_scale': float, 'frame_strip': ...}``;
		each piece is a dict with ``index, image, mask, bbox, area_px, angle,
		contour, is_cluster, touches_frame, touches_strip``. ``is_cluster`` is
		``True`` for a blob that could not be confidently split into single
		pieces (such a record also
		carries ``piece_type='cluster'``); it is ``False`` on every normal piece.
		``touches_frame`` is ``True`` when the piece's working-resolution bbox
		reaches the image border (the piece may be cut off by the frame, or be
		a photo-margin artefact); it does not set ``is_cluster``. A near-white
		paper strip along the frame (scan whose paper does not cover the
		glass, defect S3; see :func:`_frame_strip_mask`) is removed from the
		foreground before labelling: ``frame_strip`` is ``None`` or
		``{'side', 'width_px', 'span_frac', 'sides'}`` (``width_px`` in original
		px; ``sides`` lists every strip found), and ``touches_strip`` is ``True``
		on a piece within the closing reach of the strip (the pieces the strip
		used to swallow; its contour on that side is less reliable; ``touches_frame`` keeps meaning the real
		image border). With ``debug`` the strip is in ``debug['strip_mask']``. On
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

	# --- Step 5b: scan-edge paper strip (S3) ---
	# A near-white strip along the frame (paper not covering the glass) is foreground;
	# a piece touching it would merge with it and be dropped. Zero it before the
	# morphology and the labelling, remembering which raw components touched it.
	strip_mask, strips = _frame_strip_mask(cv2.cvtColor(work_bgr, cv2.COLOR_BGR2LAB), binary_raw)
	strip_zone = None
	if strip_mask is not None:
		r = _frame_reach(working_dim)
		strip_zone = cv2.dilate(strip_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
		binary_raw = binary_raw.copy()
		binary_raw[strip_mask > 0] = 0
	frame_strip = None
	if strips:
		frame_strip = {
			"side": strips[0]["side"],
			"width_px": float(strips[0]["width_px"] * inv),
			"span_frac": float(strips[0]["span_frac"]),
			"sides": [{**st, "width_px": float(st["width_px"] * inv)} for st in strips],
		}

	# --- Step 6: morphology (open -> close -> fill holes) ---
	binary = _morph_clean(binary_raw, working_dim)
	if strip_mask is not None:
		binary[strip_mask > 0] = 0

	# --- Steps 7 & 8: label, prune, split touching ---
	components = _extract_components(
		binary,
		work_bgr,
		binary_raw,
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
		touches_frame = _raw_touches_frame(bbox_w, mask_crop, binary_raw, _frame_reach(working_dim))
		touches_strip = strip_zone is not None and _touches_strip(bbox_w, mask_crop, strip_zone)
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
			rec["touches_frame"] = touches_frame
			rec["touches_strip"] = bool(touches_strip)
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
		"frame_strip": frame_strip,
	}
	if debug:
		result["debug"] = {
			"background_model": background_model,
			"distance_map": Image.fromarray(D, "L"),
			"binary_mask": Image.fromarray(binary, "L"),
			"labels_overlay": _labels_overlay(work_bgr, components),
			"strip_mask": Image.fromarray(strip_mask if strip_mask is not None else np.zeros_like(binary), "L"),
		}
	return result


def segment_scan(
	photo: Image.Image,
	*,
	dpi: float = 300,
	band_mm: float = 1.5,
	threshold: float = 28.0,
	open_mm: float = 0.42,
	close_mm: float = 0.76,
	split_contacts: bool = True,
	debug: bool = False,
	**segment_pieces_kwargs,
) -> dict:
	"""Segment a flatbed scan of loose pieces: the official path for scans.

	Hybrid contour (promoted from the E-sym diagnostic ``hibrido`` variant,
	tools/diagnostico/gemeos/esym.py): :func:`segment_pieces` decides WHICH
	pieces exist (separation of touching pieces, ``is_cluster``,
	``touches_frame``, order and indices), and a plain full-resolution Lab
	threshold decides WHERE each boundary is, restricted to the piece's Voronoi
	cell and to a band of ``band_mm`` around the ``segment_pieces`` contour.
	The boundary steps of ``segment_pieces`` that bite into dark pieces (shadow
	shrink, boundary-band refinement, fringe rejection) are not applied.

	Steps: (1) ``segment_pieces(photo, **segment_pieces_kwargs)``; (2) background
	in OpenCV 8-bit Lab from the scan rim (8.5..21 mm from each border; median +
	3 robust-mode iterations); (3) ``sqrt(0.5 dL^2 + da^2 + db^2) > threshold``,
	square opening of ``open_mm`` and closing of ``close_mm`` (5 and 9 px at
	300 dpi); (4) Voronoi of the ``segment_pieces`` piece masks and, per piece,
	the largest external contour of threshold AND own cell AND band; (5) the
	piece record is composed from that contour like ``segment_pieces`` does
	(mean-colour fill, ``pad_ratio`` bbox, ``minAreaRect`` angle and rotation).

	Calibration and known bias (measured, docs/diagnostico/gemeos/RESULTADOS.md
	and docs/diagnostico/fundo/RESULTADOS.md): the threshold/morphology
	constants were calibrated on the green-background scans (E-fundo,
	2026-10-31). On the E-sym border twins (green, 300 dpi) the hybrid contour
	gives twin free RMS ~0.38 mm (opposite pose, A2/B2), re-scan ~0.27 mm and
	top-1 20/20. The contour INCLUDES the cast shadow (~0.4 mm on the bottom and
	left sides in the scanner frame), so the median side chord is ~18.6 mm
	against 18.2 mm nominal (``segment_pieces`` gives 17.7..18.0 because it
	bites) and the twin RMS is pose-dependent (~+0.1 mm for opposite-pose
	pairs, A2/B2, against same-pose pairs). A shadow model is deferred until the
	E-real experiment shows that this bias matters.

	Args:
		photo: PIL image of the scan.
		dpi: scan resolution; sets ``mm_per_px = 25.4 / dpi`` and scales every
			mm parameter to pixels.
		band_mm: max distance (mm) of the new boundary from the
			``segment_pieces`` contour.
		threshold: weighted Lab distance (OpenCV 8-bit units) above which a pixel
			is foreground.
		open_mm, close_mm: square morphology kernels (mm; rounded to odd px).
		split_contacts: re-partition contact groups (pieces closer than ~1 mm,
			e.g. a tab sitting in a neighbour's blank) by full-res connectivity,
			then by a seam watershed, validated by shape (:func:`_split_scan_contacts`,
			docs/diagnostico/segmentacao/CONTACTOS.md). ``False`` reproduces the
			previous output bit for bit. Never changes the number of pieces.
		debug: attach ``segment_pieces``' debug images (``strip_mask``
			included), with ``threshold_mask``, ``scan_strip_mask`` (full-res
			strip removed from the threshold), ``voronoi`` (cell labels as
			colours) and ``labels_overlay`` (full-res; ``segment_pieces`` contour
			red, scan contour blue) added/replaced.
		**segment_pieces_kwargs: forwarded to :func:`segment_pieces`
			(``pad_ratio`` and ``normalize_rotation`` are also used here).

	Returns:
		The :func:`segment_pieces` dict (``pieces, count, background_lab,
		background_model, working_scale``) plus ``mm_per_px``, ``method='scan'``
		and ``scan_background_lab`` (rim estimate, OpenCV 8-bit Lab). Pieces keep
		the same order, indices and keys (``touches_strip`` included; ``frame_strip``
		gains ``width_mm``), plus ``scan_frame_strip`` (the strip(s) found and
		removed from the full-resolution threshold, or ``None``), ``refined`` (False when the
		threshold had no pixel in the band, and for ``is_cluster`` records, which
		keep the ``segment_pieces`` contour and crop) and ``roughness``
		(perimeter / smoothed perimeter; a diagnostic, never a gate); members of a
		contact group also carry ``contacto`` (``com``, ``confianca`` alta/baixa,
		``metodo``, ``alterado``). On failure
		the ``segment_pieces`` error dict with ``method`` and ``mm_per_px`` added.
	"""
	mm_per_px = 25.4 / float(dpi)
	res = segment_pieces(photo, debug=debug, **segment_pieces_kwargs)
	res["method"] = "scan"
	res["mm_per_px"] = mm_per_px
	if "error" in res:
		return res
	pad_ratio = float(segment_pieces_kwargs.get("pad_ratio", 0.02))
	normalize_rotation = bool(segment_pieces_kwargs.get("normalize_rotation", True))

	rgb = np.asarray(photo.convert("RGB"))
	H, W = rgb.shape[:2]
	lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
	bg = _rim_background(lab, mm_per_px)
	open_px = _odd_kernel(open_mm, mm_per_px)
	close_px = _odd_kernel(close_mm, mm_per_px)
	thr_open = _scan_open_mask(lab, bg, threshold, open_px)
	thr = cv2.morphologyEx(thr_open, cv2.MORPH_CLOSE, np.ones((close_px, close_px), np.uint8))
	# Paper strip at the scan edge (S3): it is in the threshold too, and the refined
	# contour of an abutting piece could annex it inside the Voronoi cell. Zero it at
	# full resolution, then re-open so the leftover colour-blend seam goes too (the
	# opening is local, so the mask away from the strip is unchanged).
	strip_dilate = max(_STRIP_DILATE_PX, int(round(_STRIP_DILATE_PX / max(res["working_scale"], 1e-6))))
	scan_strip, scan_strips = _frame_strip_mask(lab, thr, dilate_px=strip_dilate)
	if scan_strip is not None:
		thr[scan_strip > 0] = 0
		thr = cv2.morphologyEx(thr, cv2.MORPH_OPEN, np.ones((open_px, open_px), np.uint8))
		thr_open[scan_strip > 0] = 0
		thr_open = cv2.morphologyEx(thr_open, cv2.MORPH_OPEN, np.ones((open_px, open_px), np.uint8))
	if res.get("frame_strip") is not None:
		fs = res["frame_strip"]
		fs["width_mm"] = float(fs["width_px"] * mm_per_px)
		for st in fs["sides"]:
			st["width_mm"] = float(st["width_px"] * mm_per_px)
	res["scan_frame_strip"] = [
		{**st, "width_mm": float(st["width_px"] * mm_per_px)} for st in scan_strips
	] or None
	pieces = res["pieces"]
	seg_contours = [np.asarray(p["contour"]).reshape(-1, 2) for p in pieces]
	vor, dist = _voronoi_from_contours((H, W), seg_contours)
	band_px = band_mm / mm_per_px
	band = dist <= band_px
	reach = int(np.ceil(band_px)) + 2

	for q, p in enumerate(pieces):
		p["refined"] = False
		# Clusters keep the segment_pieces contour: the threshold cannot split them either.
		if not p["is_cluster"]:
			x, y, w, h = cv2.boundingRect(seg_contours[q].astype(np.int32).reshape(-1, 1, 2))
			x0, y0 = max(0, x - reach), max(0, y - reach)
			x1, y1 = min(W, x + w + reach), min(H, y + h + reach)
			m = ((thr[y0:y1, x0:x1] > 0) & (vor[y0:y1, x0:x1] == q + 1) & band[y0:y1, x0:x1]).astype(np.uint8)
			cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
			if cnts:
				c = max(cnts, key=cv2.contourArea).reshape(-1, 2) + np.array([x0, y0])
				rec = _scan_record(c, rgb, pad_ratio, normalize_rotation)
				if rec is not None:
					p.update(rec)
					p["refined"] = True
		p["roughness"] = _contour_roughness(p["contour"])

	# Contact groups (interlocked / touching pieces): the Voronoi cell of the low-res
	# separation can hand a tab to the neighbour whose blank it sits in; re-partition the
	# group's foreground by connectivity, then by a seam watershed, validated by shape.
	if split_contacts:
		_split_scan_contacts(
			pieces, thr, thr_open, lab, vor, band, rgb, mm_per_px, close_px, pad_ratio, normalize_rotation,
		)
	del lab

	res["scan_background_lab"] = (float(bg[0]), float(bg[1]), float(bg[2]))
	if debug:
		dbg = res.setdefault("debug", {})
		dbg["threshold_mask"] = Image.fromarray(thr, "L")
		dbg["scan_strip_mask"] = Image.fromarray(scan_strip if scan_strip is not None else np.zeros_like(thr), "L")
		palette = np.random.default_rng(12345).integers(60, 256, size=(len(pieces) + 1, 3)).astype(np.uint8)
		palette[0] = 0
		dbg["voronoi"] = Image.fromarray(palette[vor], "RGB")
		ov = rgb.copy()
		lw = max(1, int(round(0.1 / mm_per_px)))
		for q, p in enumerate(pieces):
			cv2.polylines(ov, [seg_contours[q].astype(np.int32).reshape(-1, 1, 2)], True, (255, 0, 0), lw)
			cv2.polylines(ov, [np.asarray(p["contour"]).astype(np.int32).reshape(-1, 1, 2)], True, (0, 0, 255), lw)
		dbg["labels_overlay"] = Image.fromarray(ov, "RGB")
	return res


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
