"""Image matching & comparison orchestration."""

import warnings

import numpy as np
from PIL import Image
from .features import (
	get_image_size,
	compute_area,
	dominant_color,
	color_distance,
	estimate_scale,
)


def compute_mean_abs_diff(img_a: Image.Image, img_b: Image.Image) -> float:
	"""Return mean absolute pixel difference (0 identical .. 255 max).

	Images are converted to RGB, resized must already match.
	Use int16 arrays to avoid uint8 wrap-around when subtracting.
	"""
	a = img_a.convert("RGB")
	b = img_b.convert("RGB")
	if a.size != b.size:
		raise ValueError("Images must have same size for diff")
	arr_a = np.asarray(a, dtype=np.int16)
	arr_b = np.asarray(b, dtype=np.int16)
	diff = np.abs(arr_a - arr_b)
	return float(diff.mean())


def compare_images(puzzle_img: Image.Image, piece_img: Image.Image):
	print("=" * 50)
	print("\n📊 IMAGE PROPERTIES COMPARISON:")
	print("-" * 30)

	# Sizes & areas
	puzzle_size = get_image_size(puzzle_img)
	piece_size = get_image_size(piece_img)
	puzzle_area = compute_area(puzzle_size)
	piece_area = compute_area(piece_size)

	print(f"Puzzle size (px): {puzzle_size} -> area {puzzle_area}")
	print(f"Piece  size (px): {piece_size} -> area {piece_area}")
	area_ratio = piece_area / puzzle_area if puzzle_area else 0
	print(f"Piece / Puzzle area ratio: {area_ratio:.4f}")

	# Dominant colors
	dom_puzzle = dominant_color(puzzle_img)
	dom_piece = dominant_color(piece_img)
	dist = color_distance(dom_puzzle, dom_piece)
	print(f"Dominant color puzzle: {dom_puzzle}")
	print(f"Dominant color piece : {dom_piece}")
	print(f"Euclidean color distance: {dist:.2f}")

	# Scale estimation (ask once)
	print("\nEnter real puzzle width in cm (or blank to skip scale computation):")
	real_width_input = input("> ").strip()
	if real_width_input:
		try:
			real_width_cm = float(real_width_input)
			scale = estimate_scale(puzzle_size[0], real_width_cm)
			print(f"Scale: {scale:.2f} px/cm")
			piece_real_w = piece_size[0] / scale
			piece_real_h = piece_size[1] / scale
			print(f"Estimated piece real size: {piece_real_w:.2f}cm x {piece_real_h:.2f}cm")
		except Exception as e:
			print(f"Scale skipped (error: {e})")
	else:
		print("Scale skipped.")

	# --- Naive global pixel diff baseline ---
	print("\n🔍 Naive pixel diff (piece resized to puzzle size)")
	try:
		piece_resized = piece_img.resize(puzzle_img.size, Image.Resampling.LANCZOS)
		mean_diff = compute_mean_abs_diff(puzzle_img, piece_resized)
		similarity = 1.0 - (mean_diff / 255.0)  # 1 = identical, 0 = maximally different
		print(f"Mean absolute diff: {mean_diff:.2f} (0=identical, 255=max)")
		print(f"Similarity (approx): {similarity*100:.2f}%")
	except Exception as e:
		print(f"Pixel diff failed: {e}")

	print("\n(Next optional: sliding window diff to locate best position.)")

	# Ask user if wants sliding window search
	choice = input("\nRun sliding window local match? (y/N): ").strip().lower()
	if choice == "y":
		_run_sliding_window(puzzle_img, piece_img)


# ===== New pure helpers for GUI / programmatic use =====
def basic_metrics(
	puzzle_img: Image.Image,
	piece_img: Image.Image,
	real_width_cm: float | None = None,
	real_height_cm: float | None = None,
) -> dict:
	"""Compute core metrics without any I/O.

	If real dimensions are supplied (>0), compute pixel-per-cm scale for each axis
	and estimate real piece size using both scales.
	"""
	puzzle_size = get_image_size(puzzle_img)
	piece_size = get_image_size(piece_img)
	puzzle_area = compute_area(puzzle_size)
	piece_area = compute_area(piece_size)
	dom_puzzle = dominant_color(puzzle_img)
	dom_piece = dominant_color(piece_img)
	dist = color_distance(dom_puzzle, dom_piece)
	result: dict = {
		"puzzle_size": puzzle_size,
		"piece_size": piece_size,
		"puzzle_area": puzzle_area,
		"piece_area": piece_area,
		"area_ratio": (piece_area / puzzle_area) if puzzle_area else 0.0,
		"dominant_puzzle": dom_puzzle,
		"dominant_piece": dom_piece,
		"color_distance": dist,
	}
	# Scales
	scale_w = scale_h = None
	try:
		if real_width_cm and real_width_cm > 0:
			scale_w = estimate_scale(puzzle_size[0], real_width_cm)
			result["scale_px_per_cm_width"] = scale_w
	except Exception:
		result["scale_width_error"] = True
	try:
		if real_height_cm and real_height_cm > 0:
			scale_h = estimate_scale(puzzle_size[1], real_height_cm)
			result["scale_px_per_cm_height"] = scale_h
	except Exception:
		result["scale_height_error"] = True
	if scale_w and scale_h:
		result["scale_px_per_cm_avg"] = (scale_w + scale_h) / 2
		result["piece_real_size_cm"] = (
			piece_size[0] / scale_w,
			piece_size[1] / scale_h,
		)
	elif scale_w and not scale_h:
		result["piece_real_size_cm"] = (
			piece_size[0] / scale_w,
			piece_size[1] / scale_w,
		)
	elif scale_h and not scale_w:
		result["piece_real_size_cm"] = (
			piece_size[0] / scale_h,
			piece_size[1] / scale_h,
		)
	return result


def sliding_window_search(puzzle_img: Image.Image, piece_img: Image.Image, stride: int = 4, progress_callback=None) -> dict:
	"""Programmatic sliding window search.

	Returns dict with best_pos, best_diff, similarity, positions_evaluated.
	Optional progress_callback(y, total_rows) for GUI updates.
	"""
	PW, PH = piece_img.size
	MW, MH = puzzle_img.size
	if PW > MW or PH > MH:
		return {"error": "piece_larger_than_puzzle"}
	if stride < 1:
		stride = 1

	puzzle_arr = np.asarray(puzzle_img.convert("RGB"), dtype=np.int16)
	piece_arr = np.asarray(piece_img.convert("RGB"), dtype=np.int16)

	best_diff = None
	best_pos = (0, 0)
	search_w = MW - PW + 1
	search_h = MH - PH + 1
	positions = 0

	for y in range(0, search_h, stride):
		if progress_callback:
			try:
				progress_callback(y, search_h)
			except Exception:
				pass
		for x in range(0, search_w, stride):
			region = puzzle_arr[y:y+PH, x:x+PW, :]
			diff = np.abs(region - piece_arr)
			mad = float(diff.mean())
			positions += 1
			if (best_diff is None) or (mad < best_diff):
				best_diff = mad
				best_pos = (x, y)

	if best_diff is None:
		return {"error": "no_positions"}
	return {
		"best_pos": best_pos,
		"best_diff": best_diff,
		"similarity": 1.0 - (best_diff / 255.0),
		"positions_evaluated": positions,
		"stride": stride,
	}


def _run_sliding_window(puzzle_img: Image.Image, piece_img: Image.Image):
	"""Perform a brute-force (with stride) sliding window diff to locate best match.

	Optimizations:
	- Convert to RGB & numpy arrays once
	- Use int16 for safe subtraction
	- Stride > 1 to speed up (user adjustable prompt)
	"""
	print("\n🚀 Sliding window search starting...")
	PW, PH = piece_img.size
	MW, MH = puzzle_img.size
	if PW > MW or PH > MH:
		print("Piece larger than puzzle in at least one dimension. Skipping.")
		return

	# Get stride from user (default 4)
	stride_in = input("Stride (default 4, smaller = slower & more precise): ").strip()
	try:
		stride = int(stride_in) if stride_in else 4
		if stride < 1:
			stride = 1
	except ValueError:
		stride = 4

	puzzle_arr = np.asarray(puzzle_img.convert("RGB"), dtype=np.int16)
	piece_arr = np.asarray(piece_img.convert("RGB"), dtype=np.int16)

	best_diff = None
	best_pos = (0, 0)
	# Precompute piece flattened for potential vectorization (not required now)

	search_w = MW - PW + 1
	search_h = MH - PH + 1
	positions = 0

	for y in range(0, search_h, stride):
		# Simple progress every ~10 rows
		if y % (max(1, 10 * stride)) == 0:
			print(f"  Row {y}/{search_h - 1}")
		for x in range(0, search_w, stride):
			region = puzzle_arr[y:y+PH, x:x+PW, :]
			diff = np.abs(region - piece_arr)
			mad = float(diff.mean())
			positions += 1
			if (best_diff is None) or (mad < best_diff):
				best_diff = mad
				best_pos = (x, y)

	if best_diff is None:
		print("No positions evaluated (unexpected).")
		return

	similarity = 1.0 - (best_diff / 255.0)
	print(f"\nBest match at (x={best_pos[0]}, y={best_pos[1]})")
	print(f"Best mean abs diff: {best_diff:.2f}")
	print(f"Estimated local similarity: {similarity*100:.2f}%")
	print(f"Positions evaluated: {positions} (stride={stride})")

	# Future: return mask / overlay (could move to visualization)



__all__ = [
	"compare_images",
	"compute_mean_abs_diff",
	"basic_metrics",
	"sliding_window_search",
]


# ===== Advanced / optimized matching =====
def estimate_piece_scale_factors(puzzle_img: Image.Image, piece_img: Image.Image, num_pieces: int | None) -> list[float]:
	"""Return candidate scale factors to resize the piece for matching.

	If num_pieces provided (>1), assume roughly equal area pieces:
	  expected_piece_area = puzzle_area / num_pieces
	  Maintain aspect ratio of provided piece image and solve for width/height.
	Generate a small band around the expected scale (±15%).
	If no num_pieces, use generic scales.
	"""
	pw, ph = piece_img.size
	puzzle_w, puzzle_h = puzzle_img.size
	puzzle_area = puzzle_w * puzzle_h
	if num_pieces and num_pieces > 1 and puzzle_area > 0:
		expected_area = puzzle_area / num_pieces
		aspect = pw / ph if ph else 1.0
		# width * height = expected_area; width = aspect * height => aspect*height^2 = expected_area
		# height = sqrt(expected_area / aspect); width = aspect * height
		import math
		est_h = math.sqrt(expected_area / max(aspect, 1e-6))
		est_w = aspect * est_h
		base_scale = est_w / pw if pw else 1.0
		# A jigsaw bbox carries tabs + padding, so its content is slightly smaller
		# than the unit-cell estimate; bias the band a touch upward and widen it so
		# the true matching scale is bracketed without an expensive scale sweep.
		scales = [base_scale * f for f in (0.8, 0.95, 1.1, 1.3)]
	else:
		# Generic guess set - escala mais ampla para maior flexibilidade
		scales = [0.4, 0.6, 0.8, 1.0, 1.2, 1.5]
	# Filter scales that would exceed puzzle bounds dramatically (> puzzle dimension *1.1)
	valid = []
	for s in scales:
		if s <= 0:
			continue
		new_w = int(pw * s)
		new_h = int(ph * s)
		# Mais permissivo: permitir peças até 90% do tamanho do puzzle
		if new_w <= puzzle_w * 0.9 and new_h <= puzzle_h * 0.9 and new_w > 4 and new_h > 4:
			valid.append(s)
	return valid or [1.0]


# ---- Zonal Lab colour-signature tunables ----
# A piece is described by an NxN grid of per-cell mean Lab colours (its "zonal
# signature"), so two pieces are told apart by their SPATIAL colour pattern, not
# by a single average. 4x4 keeps enough spatial detail while staying stable even
# when a piece is only ~30 px across in the reference (see the scale note below).
_ZONAL_GRID = 4
# Luminance is illumination-normalized (its constant offset is removed), so we let
# absolute chroma (a,b) dominate identity: that is what separates tan from blue.
_ZONAL_LUMA_WEIGHT = 0.5
_ZONAL_CHROMA_WEIGHT = 1.0
# A cell counts only if this fraction of it is actually piece (masked) pixels.
_ZONAL_MIN_CELL_FRAC = 0.15
# At least this many valid cells are needed for a usable signature.
_ZONAL_MIN_VALID_CELLS = 4
# Colour-distance (CIE-Lab deltaE-like, weighted) that maps to similarity 0. A
# good in-content match sits well below this; a tan<->blue mismatch is ~50, above.
_ZONAL_COST_MAX = 40.0
# Longest side the zonal search runs at (large refs are downscaled for speed and
# the winning coordinates are mapped back to the passed image's resolution). Used
# only as the LEGACY fallback when num_pieces is unknown; otherwise the search
# resolution is chosen adaptively (see _SEARCH_TARGET_PIECE_PX below).
_SEARCH_MAX_DIM = 1600
# Target side (px) of ONE piece in the search space when num_pieces is known. The
# fixed 1600px cap shrank each piece to ~25px on a 3000-piece 8k reference (cell
# ~6px), too coarse for the zonal signature. Below ~40px the per-cell colour
# signature goes poor; much above 46px only spends memory without adding search
# positions (the sweep stride scales with the piece, so positions are ~invariant).
_SEARCH_TARGET_PIECE_PX = 46
# Memory ceiling for the three Lab integral images (L, a, b), which are float64
# arrays of shape (Hs+1)(Ws+1): 3 channels x 8 bytes x (Hs+1)(Ws+1). If the target
# resolution would exceed this, the search scale is reduced to fit and a warning is
# emitted. float64 is kept deliberately (see the integral note in the engine): sums
# reach ~6e8, above float32's exact-integer range (2**24), so float32 would corrupt
# cell differences in _zonal_cost near the 0.12 confidence gap.
_SEARCH_MAX_INTEGRAL_BYTES = 256 * 1024 * 1024

# ---- Shortlist / NMS / confidence tunables ----
# Default number of DISTINCT candidates returned per piece.
_SHORTLIST_N = 5
# Local minima harvested per (rotation, scale) cost map before the global merge.
_K_PER_COMBO = 10
# A local-minimum is enforced to dominate a neighbourhood ~this fraction of the
# window's shorter side, so two harvested minima are genuinely separate spots.
_NMS_SUPPRESS_FRAC = 0.6
# Two candidate boxes overlapping more than this IoU are the SAME region; the
# worse-scoring one is dropped so the shortlist holds distinct places only.
_NMS_IOU = 0.25
# Confidence threshold on the NORMALIZED cost separation between the 1st and 2nd
# distinct candidate, gap = (cost2 - cost1) / cost2. A relative gap is used instead
# of the raw similarity difference because similarity = 1 - cost/COST_MAX compresses
# low-cost (good) matches: a real cost separation of ~1 becomes a ~0.02 similarity
# gap, indistinguishable from noise, whereas as a FRACTION of the runner-up cost the
# same separation is ~0.2. At or above this threshold the winner clearly dominates
# its best rival -> 'high'; below it the piece has near-equal alternatives (flat
# sky/water/neutral, or a colour pattern that repeats in the artwork) -> honestly
# 'ambiguous'. Tuned on the real IMG_2114 pieces so the label agrees with the eye.
_CONF_GAP_HIGH = 0.12
# Second confidence gate: the piece's INTERNAL spatial structure -- the spread of its
# per-cell mean colour across its own valid cells (see where piece_structure is
# computed). A large global gap only says the piece's COLOUR is globally rare; it does
# not say the position is pinned. A near-uniform piece (flat sky/water/neutral, or a
# thin segmentation sliver) carries no spatial pattern, so colour cannot fix WHERE it
# goes no matter how rare that colour is. To be 'high' a piece must clear BOTH the gap
# AND this structure, so flat pieces are honestly 'ambiguous' even when distinctive in
# average colour. Calibrated on IMG_2114: flat pieces score < ~3.7, detail pieces > 4.
_CONF_STRUCT_HIGH = 4.0

# ---- Texture (gradient-orientation) re-rank tunables ----
# Two pieces can share a zonal COLOUR signature yet differ in fine STRUCTURE (the
# "colour twins"). After the colour search, each shortlisted candidate is re-scored
# by how well the piece's per-cell histogram-of-gradient-orientation (see
# ``texture.gradient_signature``) matches the reference window there. The combined
# cost adds ``_TEXTURE_LAMBDA`` * texture-distance to the NORMALIZED colour cost
# (colour cost / _ZONAL_COST_MAX, both in ~[0, 1]); lambda balances the two.
_TEXTURE_LAMBDA = 0.5
# Orientation bins over [0, pi) for the gradient signature.
_TEXTURE_BINS = 8
# ---- Edge/corner border prior tunables ----
# A fixed, ~zero-cost prior added to the combined cost when a piece's own edge
# classification (piece_type from ``edges.classify_piece_edges``) disagrees with
# whether its placement box touches the reference border. Assumes the puzzle ART
# FILLS the reference image, so the artwork border == the image border -- true for
# PuzzleOriginal.jpeg. A wrong border relationship is penalised by this amount.
_EDGE_PRIOR_PENALTY = 0.10
# A box side counts as "touching the frame" when it lies within this fraction of the
# search-space larger dimension from the image edge.
_EDGE_BORDER_MARGIN_FRAC = 0.02


def _cie_lab(rgb: np.ndarray) -> np.ndarray:
	"""Convert an 8-bit RGB array to CIE-Lab floats.

	Feeding OpenCV a float32 image in [0, 1] yields the true CIE ranges
	(L in 0..100, a/b in ~-127..127), unlike the packed 8-bit Lab, so per-cell
	means and Lab distances are directly interpretable as deltaE-like quantities.
	"""
	import cv2  # local import (module keeps cv2 optional)

	f = np.ascontiguousarray(rgb, dtype=np.float32) / 255.0
	return cv2.cvtColor(f, cv2.COLOR_RGB2LAB)


def _cell_edges(size: int, grid: int) -> np.ndarray:
	"""Return ``grid + 1`` integer cell boundaries spanning ``[0, size]``."""
	return np.linspace(0, size, grid + 1).round().astype(np.int64)


def _piece_zonal_signature(
	piece_rgb: np.ndarray,
	piece_mask: np.ndarray | None,
	grid: int,
) -> tuple[np.ndarray, np.ndarray] | tuple[None, None]:
	"""Per-cell mean Lab signature of the piece, over masked pixels only.

	Returns ``(sig, valid)`` where ``sig`` is ``(grid*grid, 3)`` holding
	``[L_norm, a, b]`` per cell (row-major, ``idx = cj*grid + ci``) and ``valid``
	is a boolean mask of cells that hold enough piece pixels. ``L_norm`` has the
	signature's own valid-cell mean L subtracted so a constant brightness/exposure
	offset between the physical-piece photo and the printed reference cancels; the
	chroma a,b are kept ABSOLUTE because the ink hue is the discriminator that must
	survive (tan stays tan, blue stays blue). Returns ``(None, None)`` if too few
	cells carry piece pixels for a usable signature.
	"""
	lab = _cie_lab(piece_rgb)
	h, w = lab.shape[:2]
	if piece_mask is None:
		mask = np.ones((h, w), dtype=bool)
	else:
		mask = np.asarray(piece_mask) > 0
	xe = _cell_edges(w, grid)
	ye = _cell_edges(h, grid)

	sig = np.zeros((grid * grid, 3), dtype=np.float64)
	valid = np.zeros(grid * grid, dtype=bool)
	for cj in range(grid):
		y0, y1 = int(ye[cj]), int(ye[cj + 1])
		if y1 <= y0:
			continue
		for ci in range(grid):
			x0, x1 = int(xe[ci]), int(xe[ci + 1])
			if x1 <= x0:
				continue
			cell_mask = mask[y0:y1, x0:x1]
			cnt = int(cell_mask.sum())
			total = (y1 - y0) * (x1 - x0)
			if cnt < max(1, int(_ZONAL_MIN_CELL_FRAC * total)):
				continue
			cell = lab[y0:y1, x0:x1]
			sig[cj * grid + ci] = cell[cell_mask].mean(axis=0)
			valid[cj * grid + ci] = True

	if int(valid.sum()) < _ZONAL_MIN_VALID_CELLS:
		return None, None
	# Illumination normalization: remove the constant L offset (per signature).
	sig[:, 0] -= float(sig[valid, 0].mean())
	return sig, valid


def _zonal_cost(
	integrals: tuple[np.ndarray, np.ndarray, np.ndarray],
	sig: np.ndarray,
	valid_cells: list[int],
	xe: np.ndarray,
	ye: np.ndarray,
	ys: np.ndarray,
	xs: np.ndarray,
	luma_w: float,
	chroma_w: float,
) -> np.ndarray:
	"""Zonal Lab cost map over the sampled top-left positions ``(ys, xs)``.

	``integrals`` are the (H+1, W+1) integral images of the reference L, a, b
	channels, so any cell's mean is an O(1) four-corner lookup for EVERY window
	position at once. For each valid piece cell the reference cell-mean is compared
	to the piece cell-mean: chroma (a,b) absolutely, luminance after subtracting the
	reference window's own valid-cell mean L (mirroring the piece normalization).
	Returns a ``(len(ys), len(xs))`` deltaE-like RMS cost (lower = better match).
	"""
	IL, Ia, Ib = integrals

	def _cell_mean(I: np.ndarray, x0: int, x1: int, y0: int, y1: int) -> np.ndarray:
		area = float((x1 - x0) * (y1 - y0))
		s = (
			I[np.ix_(ys + y1, xs + x1)]
			- I[np.ix_(ys + y0, xs + x1)]
			- I[np.ix_(ys + y1, xs + x0)]
			+ I[np.ix_(ys + y0, xs + x0)]
		)
		return s / area

	shape = (len(ys), len(xs))
	ab_cost = np.zeros(shape, dtype=np.float64)
	l_maps: list[np.ndarray] = []
	for idx in valid_cells:
		ci, cj = idx % (len(xe) - 1), idx // (len(xe) - 1)
		x0, x1 = int(xe[ci]), int(xe[ci + 1])
		y0, y1 = int(ye[cj]), int(ye[cj + 1])
		l_maps.append(_cell_mean(IL, x0, x1, y0, y1))
		a_mean = _cell_mean(Ia, x0, x1, y0, y1)
		b_mean = _cell_mean(Ib, x0, x1, y0, y1)
		da = a_mean - sig[idx, 1]
		db = b_mean - sig[idx, 2]
		ab_cost += chroma_w * (da * da + db * db)

	# Reference window mean L over the SAME valid cells, then compare normalized L.
	ref_mean_l = np.zeros(shape, dtype=np.float64)
	for lm in l_maps:
		ref_mean_l += lm
	ref_mean_l /= float(len(l_maps))

	l_cost = np.zeros(shape, dtype=np.float64)
	for k, idx in enumerate(valid_cells):
		dl = (l_maps[k] - ref_mean_l) - sig[idx, 0]
		l_cost += luma_w * (dl * dl)

	msd = (l_cost + ab_cost) / float(len(valid_cells))
	return np.sqrt(msd)


def _rot90k(arr: np.ndarray, k: int) -> np.ndarray:
	"""Rotate an image array by ``k`` quarter-turns (counter-clockwise, lossless).

	``k`` matches :func:`numpy.rot90`, so degrees = ``90 * k``; the returned array
	is contiguous. Used to try the piece's four orientations inside the engine.
	"""
	k %= 4
	if k == 0:
		return arr
	return np.ascontiguousarray(np.rot90(arr, k))


def _box_iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
	"""Intersection-over-union of two ``(x, y, w, h)`` boxes (0 = disjoint)."""
	ax, ay, aw, ah = a
	bx, by, bw, bh = b
	x0 = max(ax, bx)
	y0 = max(ay, by)
	x1 = min(ax + aw, bx + bw)
	y1 = min(ay + ah, by + bh)
	iw = max(0, x1 - x0)
	ih = max(0, y1 - y0)
	inter = iw * ih
	if inter <= 0:
		return 0.0
	union = aw * ah + bw * bh - inter
	return inter / union if union > 0 else 0.0


def _cost_local_minima(cost: np.ndarray, radius_cells: int, k_max: int) -> list[tuple[int, int, float]]:
	"""Return up to ``k_max`` lowest-cost local minima of a cost map.

	A grid position wins only if it is the minimum within a ``(2*radius+1)`` window
	(morphological erosion = local-min filter), so harvested minima are separated by
	roughly the suppression radius and are therefore genuinely different spots rather
	than neighbours of one dip. Returns ``(gy, gx, cost)`` grid indices, ascending.
	"""
	import cv2  # local import (module keeps cv2 optional)

	c32 = np.ascontiguousarray(cost, dtype=np.float32)
	ksize = 2 * max(1, int(radius_cells)) + 1
	kernel = np.ones((ksize, ksize), np.uint8)
	# erode pads the border with +inf, so edge cells are not spurious minima.
	mins = cv2.erode(c32, kernel)
	gy, gx = np.where(c32 <= mins + 1e-6)
	if gy.size == 0:
		return []
	vals = c32[gy, gx]
	order = np.argsort(vals)[:k_max]
	return [(int(gy[o]), int(gx[o]), float(vals[o])) for o in order]


def _peak_sharpness(
	integrals: tuple[np.ndarray, np.ndarray, np.ndarray],
	combo: dict,
	sx: int,
	sy: int,
	c0: float,
	luma_w: float,
	chroma_w: float,
) -> float | None:
	"""How sharply the cost rises when the winning window shifts ~half a piece.

	A confident placement is not just globally distinct, it is POSITIONALLY pinned:
	sliding the window by ~0.6 of the piece must raise the cost. A flat expanse
	(sky/water/neutral) has a broad, near-constant valley -- the window slides freely
	so the cost barely moves -- whereas a detail piece sits on a narrow spike. Returns
	``(ring_min - c0) / ring_min`` over the 8-neighbour ring at that offset (0 = flat
	peak, larger = sharper), or ``None`` if the window is too close to the border to
	sample a ring.
	"""
	sig = combo["sig"]
	vc = combo["valid_cells"]
	xe, ye = combo["xe"], combo["ye"]
	Nx, Ny = combo["Nx"], combo["Ny"]
	d = max(1, int(round(_NMS_SUPPRESS_FRAC * min(combo["sw"], combo["sh"]))))
	xr = sorted({max(0, sx - d), sx, min(Nx - 1, sx + d)})
	yr = sorted({max(0, sy - d), sy, min(Ny - 1, sy + d)})
	if len(xr) < 2 and len(yr) < 2:
		return None
	xa = np.array(xr, dtype=np.int64)
	ya = np.array(yr, dtype=np.int64)
	g = _zonal_cost(integrals, sig, vc, xe, ye, ya, xa, luma_w, chroma_w)
	ci = int(np.where(xa == sx)[0][0])
	cj = int(np.where(ya == sy)[0][0])
	ring = [g[j, i] for j in range(len(ya)) for i in range(len(xa)) if not (i == ci and j == cj)]
	if not ring:
		return None
	ring_min = float(min(ring))
	return (ring_min - c0) / ring_min if ring_min > 1e-6 else 0.0


def _greedy_nms(cands: list[dict], iou_thr: float, keep: int, key=None) -> list[dict]:
	"""Greedy non-maximum suppression on candidate boxes, best (lowest cost) first.

	Each dict must carry ``'box'`` = ``(x, y, w, h)`` and the score read by ``key``
	(default ``c['cost']``, the pure colour cost). A candidate is kept only if it
	overlaps every already-kept box by less than ``iou_thr``, so the result holds
	distinct regions (across scales and rotations) ranked by that score. Pass a
	``key`` such as ``lambda c: c['cost_comb']`` to rank by the combined cost.
	"""
	if key is None:
		key = lambda c: c["cost"]
	ordered = sorted(cands, key=key)
	selected: list[dict] = []
	for c in ordered:
		if all(_box_iou(c["box"], s["box"]) < iou_thr for s in selected):
			selected.append(c)
			if len(selected) >= keep:
				break
	return selected


def multi_scale_template_match(
	puzzle_img: Image.Image,
	piece_img: Image.Image,
	num_pieces: int | None = None,
	use_downscale: bool = True,
	method: str = "SQDIFF_NORMED",
	use_gpu: bool = False,
	*,
	piece_mask=None,
	pixels_per_cm: float | None = None,
	grid: int = _ZONAL_GRID,
	use_texture: bool = True,
	piece_edges: dict | None = None,
) -> dict:
	"""Locate ``piece_img`` inside ``puzzle_img`` with a zonal Lab colour search.

	Each candidate reference window and the piece are described by an ``grid``x``grid``
	signature of per-cell mean CIE-Lab colour (:func:`_piece_zonal_signature`), so a
	piece is placed by its SPATIAL colour pattern rather than by grayscale texture --
	this is what stops a tan piece from settling on smooth blue sky and what tells one
	sky piece from another. Illumination is normalized by removing each signature's
	own mean L (constant exposure/white-balance offsets cancel) while chroma is kept
	absolute (the hue is the identity). The piece signature is computed over
	``piece_mask`` pixels only, so the mean-colour-filled background does not pollute
	the template.

	Scale is driven by ``num_pieces``: one physical piece covers only ~1/N of the
	whole-artwork reference, so the search size comes from ``reference_area /
	num_pieces`` (see :func:`estimate_piece_scale_factors`), not from the piece's own
	pixel size. ``pixels_per_cm`` is accepted as an optional reference-scale hint and
	echoed back for real-size reporting.

	Rotation is handled INSIDE the engine: the piece (and its mask) is tried at all
	four 90-degree orientations and the best per candidate is kept, so callers must
	NOT pre-rotate. From the zonal-cost maps across every scale and rotation the
	engine harvests distinct local minima, merges them with box-IoU non-maximum
	suppression, and returns the top-N as a ranked ``candidates`` shortlist. A
	confidence label needs BOTH a distinct winner and a localizable piece: the
	normalized cost SEPARATION between the 1st and 2nd distinct candidate must be wide
	(one clear colour region) AND the piece must carry enough INTERNAL spatial colour
	structure to pin its position. A flat sky/water/neutral piece (or a thin sliver)
	fails the structure gate even if its average colour is globally rare, so it is
	honestly ``'ambiguous'``; near-equal rivals also give ``'ambiguous'``. Only a
	distinct, patterned piece is ``'high'`` -- a piece that genuinely cannot be
	localized is labelled honestly instead of being forced onto a single false point.

	Args:
		puzzle_img: the full reference artwork (PIL image).
		piece_img: the piece crop (PIL image), background already mean-filled.
		num_pieces: TOTAL pieces in the puzzle (e.g. ~3000), not the loose count.
		use_downscale: downscale a large reference for the search (coords mapped back).
		method: retained for API stability; the effective metric is the zonal Lab one.
		use_gpu: accepted for API stability; the zonal search runs on CPU.
		piece_mask: optional PIL 'L' or ndarray mask (piece = non-zero); ``None`` uses
			all pixels.
		pixels_per_cm: optional reference px/cm for real-size reporting.
		grid: signature grid size (default 4 -> 4x4 cells).
		use_texture: re-rank the colour shortlist by a per-cell gradient-orientation
			signature (:mod:`texture`) so "colour twins" are separated by fine
			structure; ``False`` scores by colour alone (the A/B baseline).
		piece_edges: optional edge/corner classification of this piece (a dict with
			``piece_type`` as produced by ``edges.classify_piece_edges``). When given,
			a fixed border prior nudges the combined cost so an 'edge'/'corner' piece is
			expected to touch the reference frame and an 'interior' piece is not. This
			ASSUMES the artwork fills the reference image (frame == image border), which
			holds for PuzzleOriginal.jpeg.

	Returns:
		On success a dict whose single-best keys mirror the top candidate for GUI
		compatibility -- ``best_position``, ``scale``, ``rotation`` (deg), ``score``,
		``piece_size_final``, ``refined_similarity`` (0..1, higher=better),
		``method`` -- PLUS the shortlist/confidence additions: ``candidates`` (list of
		up to N dicts, each ``{position, scale, rotation, size, similarity, score,
		cells_valid}``, ranked best first), ``confidence`` (``'high'`` |
		``'ambiguous'``), ``confidence_reason`` (str), and ``confidence_gap`` (float,
		the normalized cost separation ``(cost2 - cost1) / cost2`` between the top two
		distinct candidates). Positions and sizes are in the passed
		``puzzle_img`` coordinates. Returns ``{'error': str}`` on failure.
	"""
	try:
		import cv2  # local import
	except ImportError:
		return {"error": "opencv_not_available"}
	from . import texture  # lazy: keeps cv2 optional at module import time

	puzzle_arr = np.asarray(puzzle_img.convert("RGB"))
	piece_arr = np.asarray(piece_img.convert("RGB"))

	# Full-res mask aligned to the piece crop (piece = non-zero).
	mask_full = None
	if piece_mask is not None:
		if isinstance(piece_mask, Image.Image):
			mask_full = np.asarray(piece_mask.convert("L"))
		else:
			mask_full = np.asarray(piece_mask)
		if mask_full.ndim == 3:
			mask_full = mask_full[:, :, 0]
		if mask_full.shape[:2] != piece_arr.shape[:2]:
			mask_full = cv2.resize(
				mask_full.astype(np.uint8), (piece_arr.shape[1], piece_arr.shape[0]),
				interpolation=cv2.INTER_NEAREST,
			)

	# --- Optional coarse downscale of the reference for the search ---
	# Choose the search resolution so one piece is ~_SEARCH_TARGET_PIECE_PX across
	# (enough for the zonal signature) instead of the old fixed longest-side cap that
	# shrank each piece to ~25px. The sweep stride scales with the piece side, so the
	# number of evaluated positions is ~invariant to this choice -- only the integral
	# images grow (~coarse_scale**2), which is bounded by _SEARCH_MAX_INTEGRAL_BYTES.
	h0, w0 = puzzle_arr.shape[:2]
	max_dim = max(h0, w0)
	coarse_scale = 1.0
	expected_side_full = None
	search_target_reached = False
	if use_downscale and num_pieces and num_pieces > 1:
		expected_side_full = float(np.sqrt((w0 * h0) / float(num_pieces)))
		# Never upscale beyond full-res; hit the target piece side otherwise.
		coarse_scale = min(1.0, _SEARCH_TARGET_PIECE_PX / expected_side_full)
		# Memory cap: the 3 float64 Lab integral images occupy
		# 3 * 8 * (round(h0*c)+1) * (round(w0*c)+1) bytes. The largest c that fits the
		# budget is c_max = sqrt(budget / (3*8*h0*w0)); if it is tighter than the
		# target scale, honour the budget and report the shortfall honestly.
		c_max = float(np.sqrt(_SEARCH_MAX_INTEGRAL_BYTES / (3.0 * 8.0 * h0 * w0)))
		if c_max < coarse_scale:
			coarse_scale = c_max
			warnings.warn(
				f"search resolution capped by memory budget "
				f"({_SEARCH_MAX_INTEGRAL_BYTES / (1024 * 1024):.0f} MB): target "
				f"{_SEARCH_TARGET_PIECE_PX}px/piece not reached, effective "
				f"~{expected_side_full * coarse_scale:.1f}px/piece.",
				stacklevel=2,
			)
		search_target_reached = (expected_side_full * coarse_scale) >= (_SEARCH_TARGET_PIECE_PX - 0.5)
	elif use_downscale and max_dim > _SEARCH_MAX_DIM:
		# Legacy fallback: fixed longest-side cap when num_pieces is unknown.
		coarse_scale = _SEARCH_MAX_DIM / float(max_dim)
	if coarse_scale < 1.0:
		search_ref = cv2.resize(
			puzzle_arr, (max(1, round(w0 * coarse_scale)), max(1, round(h0 * coarse_scale))),
			interpolation=cv2.INTER_AREA,
		)
	else:
		search_ref = puzzle_arr
	Hs, Ws = search_ref.shape[:2]

	# Integral images of the reference Lab channels (computed once, reused per scale).
	ref_lab = _cie_lab(search_ref)
	integrals = (
		cv2.integral(np.ascontiguousarray(ref_lab[:, :, 0])),
		cv2.integral(np.ascontiguousarray(ref_lab[:, :, 1])),
		cv2.integral(np.ascontiguousarray(ref_lab[:, :, 2])),
	)

	# --- Scale band from num_pieces (piece-relative factors, in passed coords) ---
	scale_candidates = estimate_piece_scale_factors(puzzle_img, piece_img, num_pieces)
	expected_side_px = None
	if num_pieces and num_pieces > 1:
		expected_side_px = float(np.sqrt((w0 * h0) / float(num_pieces)))

	# Sweep every (rotation, scale): build each combo's cost map once, harvest its
	# distinct local minima, and remember the combo data so the shortlisted winners
	# can be refined at stride 1 later without recomputing the signature.
	combos: list[dict] = []
	raw_candidates: list[dict] = []
	considered = 0
	for k in range(4):
		rot_rgb = _rot90k(piece_arr, k)
		rot_mask = _rot90k(mask_full, k) if mask_full is not None else None
		prh, prw = rot_rgb.shape[:2]  # rotated piece size in its own pixels
		rotation_deg = 90 * k
		for s in scale_candidates:
			sw = max(1, round(prw * s * coarse_scale))
			sh = max(1, round(prh * s * coarse_scale))
			if sw < grid or sh < grid or sw > Ws or sh > Hs:
				continue
			interp = cv2.INTER_AREA if s * coarse_scale < 1.0 else cv2.INTER_LINEAR
			p_res = cv2.resize(rot_rgb, (sw, sh), interpolation=interp)
			m_res = None
			if rot_mask is not None:
				m_res = cv2.resize(rot_mask.astype(np.uint8), (sw, sh), interpolation=cv2.INTER_NEAREST)
			sig, valid = _piece_zonal_signature(p_res, m_res, grid)
			if sig is None:
				continue
			considered += 1
			valid_cells = [i for i in range(grid * grid) if valid[i]]
			# Per-cell gradient-orientation signature of this (rotation, scale), built
			# once here just like the colour signature; used to re-rank the shortlist.
			# Skipped entirely when texture is off so the colour path pays nothing.
			grad_sig = texture.gradient_signature(p_res, m_res, grid, _TEXTURE_BINS) if use_texture else None
			xe = _cell_edges(sw, grid)
			ye = _cell_edges(sh, grid)

			Ny = Hs - sh + 1
			Nx = Ws - sw + 1
			cw = int(xe[1] - xe[0])
			ch = int(ye[1] - ye[0])
			stride = max(1, min(cw, ch) // 2)

			ys = np.arange(0, Ny, stride, dtype=np.int64)
			xs = np.arange(0, Nx, stride, dtype=np.int64)
			cost = _zonal_cost(integrals, sig, valid_cells, xe, ye, ys, xs, _ZONAL_LUMA_WEIGHT, _ZONAL_CHROMA_WEIGHT)

			combo_idx = len(combos)
			combos.append({
				"sig": sig, "valid_cells": valid_cells, "xe": xe, "ye": ye,
				"stride": stride, "Ny": Ny, "Nx": Nx, "sw": sw, "sh": sh,
				"scale": float(s), "rotation": rotation_deg,
				"cells_valid": len(valid_cells), "grad_sig": grad_sig,
			})

			radius_cells = max(1, round(_NMS_SUPPRESS_FRAC * min(sw, sh) / stride))
			for gy, gx, cval in _cost_local_minima(cost, radius_cells, _K_PER_COMBO):
				sx = int(xs[gx])
				sy = int(ys[gy])
				raw_candidates.append({
					"combo": combo_idx,
					"cost": cval,
					"sx": sx,
					"sy": sy,
					"box": (sx, sy, sw, sh),
				})

	if not raw_candidates:
		return {"error": "no_valid_scale"}

	# Global NMS across scales/rotations -> distinct regions (keep a margin so the
	# stride-1 refinement below can reorder without losing the eventual top-N).
	prelim = _greedy_nms(raw_candidates, _NMS_IOU, keep=max(_SHORTLIST_N * 3, 12))

	# Refine each shortlisted candidate at stride 1 around its coarse position.
	for c in prelim:
		combo = combos[c["combo"]]
		stride = combo["stride"]
		Ny, Nx = combo["Ny"], combo["Nx"]
		ry = np.arange(max(0, c["sy"] - stride), min(Ny, c["sy"] + stride + 1), dtype=np.int64)
		rx = np.arange(max(0, c["sx"] - stride), min(Nx, c["sx"] + stride + 1), dtype=np.int64)
		if ry.size and rx.size:
			cost2 = _zonal_cost(
				integrals, combo["sig"], combo["valid_cells"], combo["xe"], combo["ye"],
				ry, rx, _ZONAL_LUMA_WEIGHT, _ZONAL_CHROMA_WEIGHT,
			)
			jy, jx = np.unravel_index(int(np.argmin(cost2)), cost2.shape)
			if float(cost2[jy, jx]) <= c["cost"]:
				c["cost"] = float(cost2[jy, jx])
				c["sy"] = int(ry[jy])
				c["sx"] = int(rx[jx])
				c["box"] = (c["sx"], c["sy"], combo["sw"], combo["sh"])

	# --- Combined cost: normalized colour cost + texture re-rank + border prior ---
	# For each refined candidate compare the piece gradient-orientation signature to
	# the reference window there (texture term), then add a fixed border prior when
	# the piece's own edge type disagrees with whether its box touches the frame. The
	# pure colour ``cost`` is NOT overwritten -- it still drives the output similarity.
	pt = piece_edges.get("piece_type") if piece_edges else None
	border_margin = round(_EDGE_BORDER_MARGIN_FRAC * max(Hs, Ws))
	for c in prelim:
		combo = combos[c["combo"]]
		sx, sy, sw, sh = c["sx"], c["sy"], combo["sw"], combo["sh"]
		d_grad = 0.0
		if use_texture:
			window = search_ref[sy:sy + sh, sx:sx + sw]
			if window.shape[0] == sh and window.shape[1] == sw:
				ref_grad = texture.gradient_signature(window, None, grid, _TEXTURE_BINS)
				d_grad = texture.signature_distance(
					combo["grad_sig"], ref_grad, combo["valid_cells"]
				)
		c["d_grad"] = d_grad
		cost_comb = c["cost"] / _ZONAL_COST_MAX + (_TEXTURE_LAMBDA * d_grad if use_texture else 0.0)

		# Border prior (fixed rule, ~zero cost). Frame == image border (art fills ref).
		penalized = False
		if pt in ("edge", "corner", "interior"):
			left = sx <= border_margin
			right = sx + sw >= Ws - border_margin
			top_t = sy <= border_margin
			bottom = sy + sh >= Hs - border_margin
			n_touch = int(left) + int(right) + int(top_t) + int(bottom)
			opposite2 = n_touch == 2 and ((left and right) or (top_t and bottom))
			if pt == "edge":
				if n_touch == 0:  # a straight-edged piece must sit on the frame
					cost_comb += _EDGE_PRIOR_PENALTY
					penalized = True
			elif pt == "corner":
				if n_touch < 2:  # a corner needs two adjacent frame sides
					cost_comb += _EDGE_PRIOR_PENALTY
					penalized = True
				elif opposite2:  # two opposite sides is not a real corner
					cost_comb += _EDGE_PRIOR_PENALTY / 2.0
					penalized = True
			elif pt == "interior":
				if n_touch >= 1:  # an all-tab/blank piece should sit off the frame
					cost_comb += _EDGE_PRIOR_PENALTY / 2.0
					penalized = True
		c["cost_comb"] = cost_comb
		c["edge_penalized"] = penalized

	# Re-establish distinctness after refinement, then keep the ranked top-N. Ranking
	# now uses the combined cost so a texture/border re-rank can promote a candidate.
	final = _greedy_nms(prelim, _NMS_IOU, keep=_SHORTLIST_N, key=lambda c: c["cost_comb"])

	# Positional sharpness of the winning peak (flat pieces have a broad valley).
	best_c = final[0]
	best_combo = combos[best_c["combo"]]
	peak_sharp = _peak_sharpness(
		integrals, best_combo, best_c["sx"], best_c["sy"], best_c["cost"],
		_ZONAL_LUMA_WEIGHT, _ZONAL_CHROMA_WEIGHT,
	)
	# Internal spatial structure of the piece: how much its per-cell mean colour
	# varies across its own valid cells. A near-uniform piece (flat sky/water/neutral)
	# has almost no spatial pattern, so its position cannot be pinned by colour no
	# matter how rare that colour is -- such a piece must stay 'ambiguous'.
	_pv = best_combo["sig"][best_combo["valid_cells"]]
	if _pv.shape[0] > 1:
		piece_structure = float(np.sqrt(
			_pv[:, 1].var() + _pv[:, 2].var() + _ZONAL_LUMA_WEIGHT * _pv[:, 0].var()
		))
	else:
		piece_structure = 0.0

	def _to_passed(c: dict) -> dict:
		combo = combos[c["combo"]]
		pw_passed = max(1, round(combo["sw"] / coarse_scale))
		ph_passed = max(1, round(combo["sh"] / coarse_scale))
		px = int(round(c["sx"] / coarse_scale))
		py = int(round(c["sy"] / coarse_scale))
		px = max(0, min(px, w0 - pw_passed))
		py = max(0, min(py, h0 - ph_passed))
		sim = float(np.clip(1.0 - c["cost"] / _ZONAL_COST_MAX, 0.0, 1.0))
		return {
			"position": (px, py),
			"scale": combo["scale"],
			"rotation": combo["rotation"],
			"size": (pw_passed, ph_passed),
			"similarity": sim,
			"score": c["cost"],
			"cost_comb": c.get("cost_comb", c["cost"] / _ZONAL_COST_MAX),
			"d_grad": c.get("d_grad", 0.0),
			"edge_penalized": bool(c.get("edge_penalized", False)),
			"cells_valid": combo["cells_valid"],
		}

	# Rank by the combined cost (colour + texture + border prior), best (lowest) first;
	# the pure-colour ``similarity`` is still reported per candidate for the GUI.
	candidates = [_to_passed(c) for c in final]
	candidates.sort(key=lambda d: d["cost_comb"])
	top = candidates[0]

	# Confidence needs BOTH a distinct winner (normalized cost gap to the 2nd distinct
	# candidate) AND enough internal piece structure to pin the position: a flat
	# sky/water/neutral piece may clear the gap on a rare colour yet fail the structure
	# gate, so it is honestly 'ambiguous' rather than forced onto a single false point.
	# (peak_sharpness is also exposed for inspection but is not a decision gate: it
	# conflates flat pieces sitting in small regions with genuine detail.)
	# The gap is now measured on the COMBINED cost (colour + texture + border prior),
	# so its scale differs from the colour-only gap _CONF_GAP_HIGH was tuned on -- see
	# the recalibration note in the eval report; the threshold itself is left unchanged.
	if len(candidates) >= 2:
		comb1 = candidates[0]["cost_comb"]
		comb2 = candidates[1]["cost_comb"]
		gap = (comb2 - comb1) / comb2 if comb2 > 1e-6 else 0.0
	else:
		comb1 = candidates[0]["cost_comb"]
		comb2 = None
		gap = 1.0
	sharp_txt = "n/a" if peak_sharp is None else f"{peak_sharp:.3f}"
	gap_ok = gap >= _CONF_GAP_HIGH
	struct_ok = piece_structure >= _CONF_STRUCT_HIGH
	confidence = "high" if (gap_ok and struct_ok) else "ambiguous"
	if confidence == "high":
		why = "distinct + patterned"
	elif gap_ok and not struct_ok:
		why = "too uniform to localize"
	else:
		why = "near-equal rival"
	if comb2 is None:
		reason = (
			f"only one distinct candidate; struct={piece_structure:.2f} -> {confidence}"
		)
	else:
		reason = (
			f"rel-comb-cost gap={gap:.3f} (thr {_CONF_GAP_HIGH}), "
			f"struct={piece_structure:.2f} (thr {_CONF_STRUCT_HIGH}), "
			f"d_grad={top['d_grad']:.3f}, sharpness={sharp_txt} -> {confidence} [{why}]"
		)

	result = {
		"best_position": top["position"],
		"scale": top["scale"],
		"rotation": top["rotation"],
		"piece_size_final": top["size"],
		"score": top["score"],
		"refined_similarity": top["similarity"],
		"method": f"zonal_lab{grid}x{grid}",
		"requested_method": method,
		"coarse_scale_factor": coarse_scale,
		"search_dims": (Ws, Hs),
		"search_piece_px": (float(expected_side_full * coarse_scale) if expected_side_full is not None else None),
		"integral_mb": float(3 * 8 * (Hs + 1) * (Ws + 1) / (1024 * 1024)),
		"search_target_reached": bool(search_target_reached),
		"candidates_considered": considered,
		"scale_candidates": list(scale_candidates),
		"grid": grid,
		"cells_valid": top["cells_valid"],
		"masked": piece_mask is not None,
		"gpu_used": False,
		"expected_piece_side_px": expected_side_px,
		"candidates": candidates,
		"confidence": confidence,
		"confidence_reason": reason,
		"confidence_gap": gap,
		"peak_sharpness": peak_sharp,
		"piece_structure": piece_structure,
		"texture_used": bool(use_texture),
		"edge_prior_type": pt,
		"cost_comb": top["cost_comb"],
		"d_grad": top["d_grad"],
	}
	if expected_side_px is not None and pixels_per_cm:
		result["expected_piece_side_cm"] = expected_side_px / float(pixels_per_cm)
		result["pixels_per_cm"] = float(pixels_per_cm)
	return result


__all__.extend([
	"estimate_piece_scale_factors",
	"multi_scale_template_match",
])

