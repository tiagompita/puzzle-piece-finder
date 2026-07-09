"""Edge/corner classification of puzzle pieces from their own mask/contour.

Pure geometry only: a piece is analysed against its own contour and the
``cv2.minAreaRect`` fitted to it -- the puzzle reference image is never used.

For each of the rectangle's four sides we measure how far the piece boundary
deviates *perpendicular* from that side. Contour points are assigned to their
nearest rect side, the near-corner ends are trimmed, and the deviation is the
(robust) perpendicular distance of the remaining points from the rect edge. A
flat (border) side hugs the rectangle edge, so its deviation stays near zero; a
tab (protrusion) or a blank (indentation) pushes the boundary far from the
rectangle edge, so its deviation is large. Counting the near-zero (flat) sides
yields the piece type:

    0 flat sides                -> 'interior'
    1 flat side                 -> 'edge'
    2 flat sides, adjacent      -> 'corner'
    2 flat sides, opposite      -> 'suspect'  (real corners are adjacent)
    3 or 4 flat sides           -> 'suspect'

Public API:
    ``classify_piece_edges(piece) -> dict``  -- pure, one piece.
    ``classify_pieces(pieces) -> list``      -- enrichment over a piece list
    (e.g. ``segment_pieces(...)['pieces']``); merges the new fields into each
    piece dict in place and returns the same list. This is the integration
    point and needs no change to ``segmentation.py``.

Deviation is normalised by the *mean* of the two ``minAreaRect`` side lengths:
a tab/blank height scales with the overall piece scale, and the mean dimension
is a stable scale estimate for the near-square pieces this handles (using the
min dimension would penalise slightly elongated pieces). A side counts as flat
when its normalised deviation falls below ``_STRAIGHT_RATIO``.
"""

from __future__ import annotations

import cv2
import numpy as np


__all__ = ["classify_piece_edges", "classify_pieces"]


# ===== Tunables (calibrated on the four real board photos via the overlay) =====
# A side is 'straight' when its perpendicular deviation from the rect edge, as a
# fraction of the mean rect dimension, stays below this ratio. On the real
# pieces the deviations are bimodal: flat sides pile up below ~0.09 (contour
# noise, rounded corners and a small minAreaRect tilt) while real tabs/blanks
# sit at ~0.12-0.45. The density minimum falls in the 0.08-0.09 band, so the
# threshold is placed at the top of the flat cluster; nudging it up to 0.10
# mainly reclassifies shallow blanks as flat and over-flags edges.
_STRAIGHT_RATIO = 0.09
# Robust "max" deviation per side: the 95th percentile rejects single-pixel
# contour spikes while still catching the shoulders of a tab or the floor of a
# blank (both span a large fraction of the side).
_DEVIATION_PERCENTILE = 95.0
# Fraction of each side length trimmed at both ends before measuring, so corner
# rounding and side-assignment ambiguity near the box corners do not leak in.
_CORNER_MARGIN = 0.10
# Minimum central-band points required to measure a side. With the dense
# contours from segmentation this never fails in practice; if it did, the side
# is left unmeasured and treated as NOT straight, so a degenerate contour biases
# toward 'interior' rather than spuriously inflating edge/corner counts.
_MIN_SIDE_POINTS = 6


def _empty_result() -> dict:
	"""Neutral classification for a degenerate contour (no fittable rect)."""
	return {
		"straight_sides": 0,
		"sides": [False, False, False, False],
		"side_deviations": [0.0, 0.0, 0.0, 0.0],
		"piece_type": "interior",
		"min_area_box": None,
	}


def _segment_distance(pts: np.ndarray, a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
	"""Distance from each point in ``pts`` (N, 2) to segment ``a``-``b``.

	Returns ``(distance, t)`` where ``t`` is the raw (un-clamped) projection
	parameter along the segment: ``t in [0, 1]`` means the foot of the
	perpendicular lands within the segment. For those in-span points the
	returned distance equals the perpendicular distance to the side's line.
	"""
	ab = b - a
	L2 = float(ab @ ab)
	ap = pts - a
	if L2 <= 1e-9:
		return np.linalg.norm(ap, axis=1), np.zeros(len(pts), dtype=np.float32)
	t = (ap @ ab) / L2
	tc = np.clip(t, 0.0, 1.0)
	proj = a + tc[:, None] * ab
	d = np.linalg.norm(pts - proj, axis=1)
	return d, t


def _piece_type(sides: list[bool]) -> str:
	"""Map the four straight-side flags to a piece type.

	Two straight sides are a 'corner' only when they are adjacent; two opposite
	straight sides (a strip-like piece) and any count >= 3 are 'suspect'.
	"""
	n = sum(sides)
	if n == 0:
		return "interior"
	if n == 1:
		return "edge"
	if n == 2:
		idx = [i for i, s in enumerate(sides) if s]
		if (idx[1] - idx[0]) % 4 == 2:
			return "suspect"
		return "corner"
	return "suspect"


def classify_piece_edges(piece: dict) -> dict:
	"""Classify the four sides of one piece as straight vs tab/blank.

	Args:
		piece: a piece record as produced by ``segment_pieces`` -- only its
			``contour`` (numpy ``(N, 2)`` in original image coords) is used.

	Returns:
		Dict with ``straight_sides`` (int 0-4), ``sides`` (list of 4 booleans in
		``cv2.boxPoints`` order, True = straight), ``side_deviations`` (the 4
		normalised deviations), ``piece_type`` (str) and ``min_area_box`` (the
		4 rect corners as a list, or ``None`` for a degenerate contour).
	"""
	cnt = piece.get("contour")
	if cnt is None:
		return _empty_result()
	cnt = np.asarray(cnt).reshape(-1, 2).astype(np.float32)
	if len(cnt) < 3:
		return _empty_result()

	rect = cv2.minAreaRect(cnt.astype(np.int32))
	(_, _), (rw, rh), _ = rect
	mean_dim = (rw + rh) / 2.0
	if mean_dim <= 0:
		return _empty_result()

	box = cv2.boxPoints(rect).astype(np.float32)  # (4, 2), consecutive = sides

	# Per-side distance and projection parameter for every contour point.
	dists = np.empty((4, len(cnt)), dtype=np.float32)
	tparams = np.empty((4, len(cnt)), dtype=np.float32)
	for k in range(4):
		d, t = _segment_distance(cnt, box[k], box[(k + 1) % 4])
		dists[k] = d
		tparams[k] = t
	# Each contour point belongs to its nearest side.
	assign = np.argmin(dists, axis=0)

	sides: list[bool] = []
	deviations: list[float] = []
	for k in range(4):
		sel = assign == k
		vals = np.empty(0, dtype=np.float32)
		if sel.any():
			tk = tparams[k][sel]
			dk = dists[k][sel]
			band = (tk > _CORNER_MARGIN) & (tk < 1.0 - _CORNER_MARGIN)
			vals = dk[band]
		if vals.size >= _MIN_SIDE_POINTS:
			dev = float(np.percentile(vals, _DEVIATION_PERCENTILE)) / mean_dim
			straight = dev < _STRAIGHT_RATIO
		else:
			dev = -1.0  # unmeasured (too few points) -> not straight
			straight = False
		deviations.append(dev)
		sides.append(straight)

	return {
		"straight_sides": int(sum(sides)),
		"sides": sides,
		"side_deviations": deviations,
		"piece_type": _piece_type(sides),
		"min_area_box": box.tolist(),
	}


def classify_pieces(pieces: list[dict]) -> list[dict]:
	"""Enrich a list of piece records with edge/corner classification in place.

	Applies :func:`classify_piece_edges` to each piece and merges the resulting
	fields (``straight_sides``, ``sides``, ``side_deviations``, ``piece_type``,
	``min_area_box``) into the piece dict. Intended to be called on
	``segment_pieces(...)['pieces']`` without modifying ``segmentation.py``.
	Returns the same (now enriched) list.
	"""
	for piece in pieces:
		piece.update(classify_piece_edges(piece))
	return pieces
