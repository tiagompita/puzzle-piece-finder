"""Synthetic tests for :mod:`src.shape` (fast, no scans).

Pieces are generated in mm as a quadrilateral (nominally an 18.5 mm square) whose
sides are flat (F), carry a round knob (T, outward) or a round socket (B, inward).
A knob is a circle of radius ``r`` (~3 mm) whose centre sits ``d`` = 2 mm off the
chord, so it overhangs like a real tab and protrudes ``r + d`` = 5 mm (27 % of the
chord, above the 15 % tab threshold). The contour is sampled densely, optionally
jittered with Gaussian noise, and converted to px at 300 dpi before ``analyse``.
"""

import numpy as np
import pytest

from src.profile import PuzzleProfile
from src.shape import (Shape, analyse, canon, chord_pass, free_dist, mm_per_px, side_complement,
                       transform_contour)

MMPP = mm_per_px(300)
L0 = 18.5
STEP = 0.05  # mm between generated points


def _side_points(p0, p1, kind, delta=0.0, r=3.0, d=2.0):
    """Points from p0 (included) to p1 (excluded); knob centre at chord/2 + delta."""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    L = np.linalg.norm(p1 - p0)
    u = (p1 - p0) / L
    n = np.array([u[1], -u[0]])  # outward for the corner order TL, TR, BR, BL (y down)
    if kind == "F":
        x = np.arange(0, L, STEP)
        loc = np.c_[x, np.zeros_like(x)]
    else:
        a = np.sqrt(r * r - d * d)
        xc = L / 2 + delta
        x1 = np.arange(0, xc - a, STEP)
        al = np.arctan2(d, a)
        th = np.linspace(np.pi + al, -al, int(np.ceil(r * (np.pi + 2 * al) / STEP)), endpoint=False)
        arc = np.c_[xc + r * np.cos(th), d + r * np.sin(th)]
        x2 = np.arange(xc + a, L, STEP)
        loc = np.vstack([np.c_[x1, np.zeros_like(x1)], arc, np.c_[x2, np.zeros_like(x2)]])
        if kind == "B":
            loc[:, 1] *= -1
    return p0 + loc[:, :1] * u + loc[:, 1:] * n


def make_piece(kinds, corners=None, deltas=(0, 0, 0, 0), radii=(3, 3, 3, 3), noise=0.0, rng=None, offset=(40, 30)):
    """Contour in px (300 dpi) of a piece with side kinds ``kinds`` (top, right, bottom, left)."""
    if corners is None:
        corners = [(0, 0), (L0, 0), (L0, L0), (0, L0)]
    Q = np.asarray(corners, float) + np.asarray(offset, float)
    pts = np.vstack([_side_points(Q[i], Q[(i + 1) % 4], kinds[i], deltas[i], radii[i]) for i in range(4)])
    if noise > 0:
        pts = pts + (rng or np.random.default_rng(0)).normal(0, noise, pts.shape)
    return pts / MMPP


def test_mm_per_px():
    assert mm_per_px(300) == pytest.approx(0.0846667, rel=1e-5)


def test_analyse_tbft():
    s = analyse(make_piece("TBFT"), MMPP)
    assert s.ok
    assert s.n_flat == 1
    assert s.cls == canon(["T", "B", "F", "T"])
    assert len(s.sides) == 4
    for side in s.sides:
        assert side.chord_mm == pytest.approx(L0, abs=0.3)
        assert side.profile.shape == (64, 2)
    assert s.c.shape == (1200, 2) and s.vec.shape == (256, 2) and s.z.shape == (512,)
    # sides are in contour order: the kinds read cyclically match the generator
    assert "".join(s.types) in {"TBFT"[k:] + "TBFT"[:k] for k in range(4)}
    assert s.body_angle_deg == pytest.approx(0.0, abs=1.0) or s.body_angle_deg == pytest.approx(90.0, abs=1.0)


def test_twin_and_chords():
    rng = np.random.default_rng(1)
    kinds = "TBFT"
    deltas = (0.8, -0.5, 0, 0.3)
    a = analyse(make_piece(kinds, deltas=deltas), MMPP)
    pts_mm = make_piece(kinds, deltas=deltas) * MMPP
    twin_mm = transform_contour(pts_mm, 180) + rng.normal(0, 0.1, pts_mm.shape)
    b = analyse(twin_mm / MMPP, MMPP)
    d, _, phi = free_dist(a, b)
    assert d <= 0.3, d
    assert abs(abs(phi) - 180) < 2, phi
    ok, _, _ = chord_pass(a, b)
    assert ok

    # knob of the top (T) side displaced along its chord: the free RMS grows ~0.36 mm per mm of
    # displacement (measured 0.54 mm at 1.5 mm, 0.71 at 2.0), so 1.5 mm already exceeds the
    # silhouette t95 of the Alpes profile (0.507 mm) and 2.0 mm exceeds 0.6 mm
    c = analyse(make_piece(kinds, deltas=(0.8 + 1.5, -0.5, 0, 0.3)), MMPP)
    assert free_dist(a, c)[0] > 0.507
    c2 = analyse(make_piece(kinds, deltas=(0.8 + 2.0, -0.5, 0, 0.3)), MMPP)
    assert free_dist(a, c2)[0] > 0.6

    # top chord (T, opposite the F side, tolerance 1 mm) 1.5 mm longer: fails
    long_top = [(0, 0), (L0 + 1.5, 0), (L0, L0), (0, L0)]
    e = analyse(make_piece(kinds, corners=long_top, deltas=deltas), MMPP)
    assert e.cls == a.cls
    ok, worst, dl = chord_pass(a, e)
    assert not ok and dl == pytest.approx(1.5, abs=0.3)
    # bottom chord (the F side, tolerance 2 mm) 1.5 mm longer: passes
    long_f = [(0, 0), (L0, 0), (L0 + 1.5, L0), (0, L0)]
    g = analyse(make_piece(kinds, corners=long_f, deltas=deltas), MMPP)
    assert g.cls == a.cls
    ok, _, dl = chord_pass(a, g)
    assert ok and dl == pytest.approx(1.5, abs=0.3)
    # different class never passes
    h = analyse(make_piece("TTFT"), MMPP)
    assert chord_pass(a, h)[0] is False


def _one_side(kind, delta, r):
    s = analyse(make_piece(kind + "FFF", deltas=(delta, 0, 0, 0), radii=(r, 3, 3, 3)), MMPP)
    assert s.ok
    sides = [x for x in s.sides if x.kind != "F"]
    assert len(sides) == 1, s.types
    return sides[0], s


def test_side_complement():
    rng = np.random.default_rng(2)
    tab, piece = _one_side("T", 0.6, 3.0)
    mate, _ = _one_side("B", -0.6, 3.0)  # the mate traverses the shared cut in the opposite direction
    d_mate, dl = side_complement(tab, mate)
    assert dl < 0.3
    others = []
    for _ in range(10):
        delta = rng.uniform(-2, 2)
        while abs(delta + 0.6) < 0.6:
            delta = rng.uniform(-2, 2)
        others.append(side_complement(tab, _one_side("B", delta, rng.uniform(2.5, 3.5))[0])[0])
    assert d_mate < min(others), (d_mate, others)
    assert side_complement(tab, tab)[0] == np.inf
    flat = [x for x in piece.sides if x.kind == "F"][0]
    assert side_complement(flat, mate)[0] == np.inf
    assert side_complement(tab, flat)[0] == np.inf


def test_transform_contour_and_profile_rotation():
    pts = make_piece("TBFT") * MMPP
    assert np.allclose(transform_contour(pts, 0), pts)
    assert np.allclose(transform_contour(transform_contour(pts, 180), 180), pts)
    assert np.allclose(transform_contour(transform_contour(pts, 0, mirror=True), 0, mirror=True), pts)
    p = PuzzleProfile(id="t", grid={"cols": 4, "rows": 3}, symmetry={"type": "none"})
    assert p.twin_rotation_deg() == 0
    assert np.allclose(transform_contour(pts, p.twin_rotation_deg()), pts)


def test_shape_round_trip():
    for kinds in ("TBFT", None):
        if kinds is None:  # not-ok shape (a circle has no corners)
            t = np.linspace(0, 2 * np.pi, 800, endpoint=False)
            s = analyse(np.c_[200 + 100 * np.cos(t), 200 + 100 * np.sin(t)], MMPP)
            assert not s.ok and s.cls == "" and s.area_mm2 > 0 and np.isfinite(s.roughness)
        else:
            s = analyse(make_piece(kinds, noise=0.05), MMPP)
            assert s.ok
        arr = s.to_arrays()
        assert all(isinstance(v, np.ndarray) for v in arr.values())
        r = Shape.from_arrays(arr)
        assert r.ok == s.ok and r.cls == s.cls and r.n_flat == s.n_flat
        for f in ("corners", "c", "vec", "z", "centroid_mm", "corner_cost"):
            assert np.allclose(getattr(r, f), getattr(s, f)), f
        for f in ("area_mm2", "roughness", "body_angle_deg", "qscore"):
            assert np.allclose(getattr(r, f), getattr(s, f)), f
        assert len(r.sides) == len(s.sides)
        for x, y in zip(r.sides, s.sides):
            assert x.kind == y.kind
            assert np.allclose([x.chord_mm, x.direction_deg], [y.chord_mm, y.direction_deg])
            assert np.allclose(x.profile, y.profile) and np.allclose(x.p0_mm, y.p0_mm) and np.allclose(x.p1_mm, y.p1_mm)
