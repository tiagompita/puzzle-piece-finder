"""Anti-regression test for :func:`src.edges.classify_piece_edges`.

Synthetic square contours are built with per-side profiles: a *flat* side hugs
the ``minAreaRect`` edge (near-zero perpendicular deviation), while a *notch*
side has a trapezoidal indentation cut inward (a synthetic blank) whose depth is
0.20 of the side -- well above the ``_STRAIGHT_RATIO`` = 0.09 flat threshold. The
four corners are always kept, so ``minAreaRect`` stays the base square and each
side's deviation is governed purely by its own profile.

Counting the flat sides drives ``piece_type`` (documented from ``_piece_type``):
    * 4 flat sides -> 'suspect' (a perfect square is NOT called 'interior')
    * 1 flat side  -> 'edge'
    * 2 flat sides, adjacent -> 'corner'
    * 0 flat sides -> 'interior'
"""

import numpy as np

from src.edges import classify_piece_edges


_SIZE = 400
_ORIGIN = (50, 50)
_DEPTH = 80  # 80 / 400 = 0.20 normalised deviation, well above _STRAIGHT_RATIO 0.09
_N_PER_SIDE = 120


def _side_points(a, b, inward, profile):
    """Points from corner ``a`` to ``b``; ``notch`` dips inward at mid-side."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    inward = np.asarray(inward, dtype=float)
    pts = []
    for t in np.linspace(0.0, 1.0, _N_PER_SIDE):
        base = a + t * (b - a)
        off = 0.0
        if profile == "notch":
            # Trapezoid centred at t=0.5, full depth over [0.4, 0.6].
            if 0.3 <= t < 0.4:
                off = _DEPTH * (t - 0.3) / 0.1
            elif 0.4 <= t <= 0.6:
                off = _DEPTH
            elif 0.6 < t <= 0.7:
                off = _DEPTH * (0.7 - t) / 0.1
        pts.append(base + inward * off)
    return pts


def _square_contour(profiles):
    """Build an Nx2 contour of a square whose 4 sides follow ``profiles``.

    ``profiles`` is [top, right, bottom, left]; each is 'flat' or 'notch'. Inward
    unit vectors point toward the square centre so a notch cuts inward.
    """
    x0, y0 = _ORIGIN
    tl, tr = (x0, y0), (x0 + _SIZE, y0)
    br, bl = (x0 + _SIZE, y0 + _SIZE), (x0, y0 + _SIZE)
    sides = [
        (tl, tr, (0, 1), profiles[0]),   # top,    inward +y
        (tr, br, (-1, 0), profiles[1]),  # right,  inward -x
        (br, bl, (0, -1), profiles[2]),  # bottom, inward -y
        (bl, tl, (1, 0), profiles[3]),   # left,   inward +x
    ]
    pts = []
    for (a, b, inward, profile) in sides:
        pts.extend(_side_points(a, b, inward, profile))
    return np.asarray(pts, dtype=np.int32)


def _classify(profiles):
    return classify_piece_edges({"contour": _square_contour(profiles)})


def test_perfect_square_is_suspect_not_interior():
    # A perfect square has 4 flat sides -> _piece_type returns 'suspect'.
    result = _classify(["flat", "flat", "flat", "flat"])
    assert result["straight_sides"] == 4
    assert result["piece_type"] == "suspect"
    assert result["piece_type"] != "interior"


def test_one_flat_side_is_edge():
    result = _classify(["flat", "notch", "notch", "notch"])
    assert result["straight_sides"] == 1
    assert result["piece_type"] == "edge"


def test_two_adjacent_flat_sides_is_corner():
    # Top and right are flat and share a corner -> adjacent -> 'corner'.
    result = _classify(["flat", "flat", "notch", "notch"])
    assert result["straight_sides"] == 2
    assert result["sides"][0] and result["sides"][1]
    assert result["piece_type"] == "corner"


def test_no_flat_side_is_interior():
    result = _classify(["notch", "notch", "notch", "notch"])
    assert result["straight_sides"] == 0
    assert result["piece_type"] == "interior"
