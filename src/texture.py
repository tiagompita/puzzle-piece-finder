"""Gradient-orientation texture signatures for colour-twin disambiguation.

Two puzzle pieces can carry an almost identical zonal COLOUR signature (the
"colour twins": two low-detail sky/water pieces, or two pieces cut from the same
flat art region) yet differ in their fine STRUCTURE -- the direction the printed
detail runs. This module adds a per-cell histogram-of-gradient-orientation
descriptor the matching engine uses to re-rank colour-equal candidates.

The descriptor mirrors the engine's zonal layout (same ``grid`` x ``grid`` cells,
same rounded-``linspace`` boundaries as ``matching._cell_edges``, same masked
piece pixels) so one texture cell lines up with the colour cell it augments.
Design choices, and why:

* **Channel**: the Sobel gradient is taken on the CIE-L (luminance) channel, via
  the same float32/255 -> ``COLOR_RGB2LAB`` conversion the engine uses in
  ``_cie_lab``. Structure lives in luminance; chroma already carries identity.
* **Unsigned orientation**: ``theta = arctan2(gy, gx) mod pi`` (0..180 deg), so a
  contrast inversion between the physical-piece photo and the printed reference
  (an edge that is light-on-dark in one and dark-on-light in the other) lands in
  the same bin.
* **Magnitude-weighted, soft binning**: each pixel votes into the two nearest
  orientation bins with linear (circular) interpolation, weighted by gradient
  magnitude. Soft binning avoids the aliasing a hard histogram would suffer when
  a piece is matched at a slightly different scale/rotation than the reference.
* **Per-cell L2 normalisation**: only the DISTRIBUTION of edge directions matters,
  not their absolute strength, so illumination/contrast differences between photo
  and print cancel.
* **Flat / low-coverage cells are zeroed**: a cell with too little masked coverage,
  or whose mean gradient magnitude is below ``_FLAT_CELL_MIN_MAG`` (essentially a
  flat region whose orientation histogram would be pure noise), is emitted as an
  all-zero vector. :func:`signature_distance` skips any cell where either side is
  zero, so flat "no-texture" cells never fabricate a penalty.
* **Optional border erosion**: when a mask is supplied, ``erode_frac`` shrinks it
  inward before the gradient is sampled, keeping the false step at the mean-filled
  piece boundary -- and the dark cast shadow that pools in blank/concavity edges of
  the physical photo -- out of the orientation histogram (see the Stage-A
  contamination probe for the calibration behind the default).

Pure module: no I/O, no printing. cv2 + numpy only.
"""

from __future__ import annotations

import cv2
import numpy as np


__all__ = ["gradient_signature", "signature_distance"]


# ===== Tunables =====
# A cell counts only if this fraction of it is masked (piece) pixels -- mirrors the
# engine's _ZONAL_MIN_CELL_FRAC so a texture cell tracks the colour cell it augments.
_MIN_CELL_COVER_FRAC = 0.15
# Minimum MEAN gradient magnitude (CIE-L units per masked pixel) for a cell to count
# as textured. Below this the cell is essentially flat: its orientation histogram is
# noise, so it is zeroed ("no texture") rather than L2-normalised into a full-strength
# noise direction that would corrupt the distance. Calibrated on real IMG_2114 pieces
# at search resolution -- flat sky/water/skin cells sit well below, printed-detail
# cells well above (Stage-A contamination probe).
_FLAT_CELL_MIN_MAG = 1.5
# Default fraction of the shorter piece side eroded off the mask border before the
# gradient is sampled, so the false step at the mean-filled boundary and the dark
# shadow pooling in blank/concavity edges do not enter the histogram. Applied only
# when a mask is supplied; 0.0 disables it. The engine passes this default; the
# contamination probe compares 0.0 vs this value.
_BORDER_ERODE_FRAC = 0.06


def _cell_edges(size: int, grid: int) -> np.ndarray:
	"""Return ``grid + 1`` integer cell boundaries spanning ``[0, size]``.

	Identical to ``matching._cell_edges`` so texture cells share the colour cells'
	rounded-``linspace`` boundaries and stay index-aligned.
	"""
	return np.linspace(0, size, grid + 1).round().astype(np.int64)


def _lab_L(rgb: np.ndarray) -> np.ndarray:
	"""CIE-L (luminance, 0..100) channel of an 8-bit RGB array as float32.

	Uses the same float32/255 -> ``COLOR_RGB2LAB`` path as ``matching._cie_lab`` so
	the luminance scale matches the colour engine's.
	"""
	f = np.ascontiguousarray(rgb, dtype=np.float32) / 255.0
	lab = cv2.cvtColor(f, cv2.COLOR_RGB2LAB)
	return np.ascontiguousarray(lab[:, :, 0])


def _resolve_mask(mask, h: int, w: int, erode_frac: float) -> np.ndarray:
	"""Boolean piece mask (``True`` = piece), optionally border-eroded.

	``None`` yields an all-True mask (whole image, e.g. a reference window). A 3-D
	mask is reduced to its first channel. When ``erode_frac > 0`` the mask is eroded
	by ``round(erode_frac * min(h, w))`` px with an elliptical kernel, dropping the
	boundary ring before the gradient is sampled.
	"""
	if mask is None:
		return np.ones((h, w), dtype=bool)
	m = np.asarray(mask)
	if m.ndim == 3:
		m = m[:, :, 0]
	m = m > 0
	if erode_frac and erode_frac > 0.0:
		r = int(round(erode_frac * min(h, w)))
		if r >= 1:
			kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
			eroded = cv2.erode(m.astype(np.uint8), kernel) > 0
			# Never erode the mask into nothing (thin slivers): keep the raw mask if
			# erosion would remove every pixel.
			if eroded.any():
				m = eroded
	return m


def _soft_orientation_hist(theta: np.ndarray, mag: np.ndarray, bins: int) -> np.ndarray:
	"""Magnitude-weighted, soft (circular linear-interp) orientation histogram.

	``theta`` in ``[0, pi)`` votes into its two nearest bins over ``[0, pi)`` with
	weights ``mag * (1 - frac)`` and ``mag * frac``; the bin axis wraps (bin
	``bins-1`` and bin ``0`` are neighbours), matching the unsigned orientation.
	"""
	bin_width = np.pi / bins
	pos = theta / bin_width  # in [0, bins)
	b0 = np.floor(pos).astype(np.int64)
	frac = pos - b0
	b0 %= bins
	b1 = (b0 + 1) % bins
	hist = np.bincount(b0, weights=mag * (1.0 - frac), minlength=bins)[:bins]
	hist = hist + np.bincount(b1, weights=mag * frac, minlength=bins)[:bins]
	return hist


def gradient_signature(
	rgb: np.ndarray,
	mask,
	grid: int = 4,
	bins: int = 8,
	*,
	erode_frac: float = _BORDER_ERODE_FRAC,
) -> np.ndarray:
	"""Per-cell histogram-of-gradient-orientation signature of ``rgb``.

	Args:
		rgb: an ``(H, W, 3)`` 8-bit RGB array (piece crop or reference window).
		mask: optional piece mask (``True``/non-zero = piece); ``None`` uses every
			pixel, as for a reference window. A 3-D mask is reduced to channel 0.
		grid: cell grid size (``grid`` x ``grid``), matching the colour engine.
		bins: orientation bins over ``[0, pi)``.
		erode_frac: fraction of the shorter side to erode off the mask border before
			sampling the gradient (mean-fill/shadow mitigation). Ignored when
			``mask`` is ``None``.

	Returns:
		A ``(grid*grid, bins)`` float64 array, row-major ``idx = cj*grid + ci`` (the
		same indexing as ``matching._piece_zonal_signature``). Each textured cell is
		an L2-normalised orientation histogram; a flat or low-coverage cell is all
		zeros ("no texture") and is skipped by :func:`signature_distance`.
	"""
	rgb = np.asarray(rgb)
	h, w = rgb.shape[:2]
	sig = np.zeros((grid * grid, bins), dtype=np.float64)
	if h < 2 or w < 2:
		return sig

	L = _lab_L(rgb)
	gx = cv2.Sobel(L, cv2.CV_64F, 1, 0, ksize=3)
	gy = cv2.Sobel(L, cv2.CV_64F, 0, 1, ksize=3)
	mag = np.hypot(gx, gy)
	theta = np.mod(np.arctan2(gy, gx), np.pi)  # unsigned orientation, [0, pi)

	m = _resolve_mask(mask, h, w, erode_frac)

	xe = _cell_edges(w, grid)
	ye = _cell_edges(h, grid)
	for cj in range(grid):
		y0, y1 = int(ye[cj]), int(ye[cj + 1])
		if y1 <= y0:
			continue
		for ci in range(grid):
			x0, x1 = int(xe[ci]), int(xe[ci + 1])
			if x1 <= x0:
				continue
			cell_m = m[y0:y1, x0:x1]
			cnt = int(cell_m.sum())
			total = (y1 - y0) * (x1 - x0)
			if cnt < max(1, int(_MIN_CELL_COVER_FRAC * total)):
				continue
			cmag = mag[y0:y1, x0:x1][cell_m]
			if float(cmag.sum()) / cnt < _FLAT_CELL_MIN_MAG:
				continue  # flat cell -> leave zeros ("no texture")
			cth = theta[y0:y1, x0:x1][cell_m]
			hist = _soft_orientation_hist(cth, cmag, bins)
			norm = float(np.sqrt((hist * hist).sum()))
			if norm > 1e-12:
				sig[cj * grid + ci] = hist / norm
	return sig


def signature_distance(a: np.ndarray, b: np.ndarray, valid_cells=None) -> float:
	"""Mean per-cell orientation distance between two gradient signatures.

	For every comparable cell the distance is ``1 - cosine`` of the two orientation
	histograms. Both are non-negative, so cosine lies in ``[0, 1]`` and the per-cell
	distance in ``[0, 1]`` (0 = identical edge-direction distribution, 1 = disjoint).
	A cell counts only when BOTH sides carry energy (norm > 0); flat "no-texture"
	cells on either side are skipped. If ``valid_cells`` is given the comparison is
	restricted to those cell indices. Returns the mean over comparable cells, or
	``0.0`` when none are comparable (no shared texture -> no penalty).
	"""
	a = np.asarray(a, dtype=np.float64)
	b = np.asarray(b, dtype=np.float64)
	idxs = range(a.shape[0]) if valid_cells is None else valid_cells

	total = 0.0
	count = 0
	for i in idxs:
		va = a[i]
		vb = b[i]
		na = float(np.sqrt((va * va).sum()))
		nb = float(np.sqrt((vb * vb).sum()))
		if na <= 1e-12 or nb <= 1e-12:
			continue
		cos = float((va * vb).sum()) / (na * nb)
		if cos > 1.0:
			cos = 1.0
		elif cos < 0.0:
			cos = 0.0
		total += 1.0 - cos
		count += 1
	if count == 0:
		return 0.0
	return total / count
