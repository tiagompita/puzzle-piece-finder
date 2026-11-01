"""Synthetic tests for :mod:`src.locate` (artwork as a grid of solid colours, fast)."""

import numpy as np
import pytest

import synth
from src.locate import (CellArt, de_cell, locate_group, pair_locate, piece_mean_lab, piece_render, render_item,
                        rotate_dir, snap_theta)
from src.shape import free_dist

ROWS, COLS = 6, 8


@pytest.fixture(scope="module")
def world():
    rgb = synth.art_rgb(ROWS, COLS, seed=3)
    return rgb, synth.make_art(rgb, ROWS, COLS)


def test_cellart_geometry(world):
    rgb, art = world
    assert art.cell_px == (25.0, 25.0)
    assert art.canvas == (43, 43)
    assert art.cell_lab_mean.shape == (ROWS, COLS, 3)
    win = art.cell_crop(3, 4)
    assert win.shape == (43, 43, 3)
    # the centre of the window is the cell colour
    assert np.allclose(win[21, 21], art.cell_lab_mean[2, 3], atol=1e-3)
    # windows of edge cells are NaN outside the art
    assert np.isnan(art.cell_crop(1, 1)[0, 0, 0])
    assert art.scan_scale(25.4 / 300) == pytest.approx((25 * 25.4 / 300 / 18.5,) * 2)


def test_rotate_dir():
    assert rotate_dir("N", 90) == "E" and rotate_dir("N", 180) == "S" and rotate_dir("W", 90) == "N"
    assert rotate_dir("E", 0, mirror=True) == "W" and rotate_dir("N", 270) == "W"


@pytest.mark.parametrize("psi", [0.0, 90.0, -37.0])
def test_render_and_de_cell(world, psi):
    rgb, art = world
    prof = synth.profile(ROWS, COLS)
    cont = synth.body_mm("TBTB", deltas=(0.5, -0.4, 0.2, 0.0))
    pts, rgba = synth.scan_piece(rgb, cont, (3, 4), psi=psi)
    shp = synth.shape_of(pts)
    assert shp.ok
    th, _, resid = snap_theta(shp, -psi)
    assert abs(resid) < 2.0
    R = render_item(rgba, shp, th, art, prof.mm_per_px())
    assert R["mask"].sum() > 300
    own = de_cell(R, 3, 4, art)
    others = [de_cell(R, l, c, art)["dE"] for l in range(1, ROWS + 1) for c in range(1, COLS + 1) if (l, c) != (3, 4)]
    assert own["dE"] < 3.0, own
    assert own["dE"] < min(others)
    # a wrong rotation is worse (neighbour colours fall on the tabs)
    assert de_cell(render_item(rgba, shp, th + 90, art, prof.mm_per_px()), 3, 4, art)["dE"] > own["dE"]
    m = piece_mean_lab(rgba)
    assert m.shape == (3,)


def test_piece_render_identity():
    rgba = np.zeros((40, 40, 4), np.uint8)
    rgba[10:30, 10:30] = (200, 50, 50, 255)
    R = piece_render(rgba, 0.0, (40, 40), l_shift=0.0, erode_px=0)
    assert R["mask"][12:28, 12:28].all() and not R["mask"][:8].any()


def _group(true_cells_local):
    return [dict(rc=rc) for rc in true_cells_local]


@pytest.mark.parametrize("rot", [0, 90, 180, 270])
def test_locate_group_rotations(world, rot):
    rgb, art = world
    prof = synth.profile(ROWS, COLS)
    local = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)]
    cell0 = (3, 4)
    from src.locate import _rot_rc
    items = []
    for r, c in local:
        dr, dc = _rot_rc(r, c, rot)
        l, cc = cell0[0] + int(dr), cell0[1] + int(dc)
        items.append(dict(rc=(r, c), mean_lab=art.cell_lab_mean[l - 1, cc - 1] + 0.5))
    res = locate_group(items, prof, art, topk=3, constraints={"use_flat": False})
    assert res[0]["cell0"] == cell0 and res[0]["rot"] == rot, res[0]
    assert res[0]["margin"] > 2.0
    assert not res[0]["mirror"]
    # mirror tested and reported, but the true placement (not mirrored) stays first
    res_m = locate_group(items, prof, art, topk=3, mirror=True, constraints={"use_flat": False})
    assert res_m[0]["cell0"] == cell0 and res_m[0]["rot"] == rot and not res_m[0]["mirror"]


def test_locate_group_flat_constraint():
    rows, cols = ROWS, COLS
    rgb = synth.art_rgb(rows, cols, seed=5)
    # copy the colours of the interior block rows 3-4, cols 3-5 onto the border block rows 1-2, cols 3-5 (+ small offset)
    blk = rgb[2 * 25:4 * 25, 2 * 25:5 * 25].astype(int)
    rgb[0:2 * 25, 2 * 25:5 * 25] = np.clip(blk + 6, 0, 255).astype(np.uint8)
    art = synth.make_art(rgb, rows, cols)
    prof = synth.profile(rows, cols)
    local = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)]
    items = [dict(rc=(r, c), mean_lab=art.cell_lab_mean[2 + r, 2 + c].copy()) for r, c in local]
    free = locate_group(items, prof, art, constraints={"use_flat": False})
    assert free[0]["cell0"] == (3, 3)   # colour alone prefers the interior copy
    for it in items:
        it["flat_dirs"] = {"N"} if it["rc"][0] == 0 else set()
    res = locate_group(items, prof, art)
    assert res[0]["cell0"] == (1, 3) and res[0]["rot"] == 0, res[0]
    assert all(prof.is_border(*res[0]["cells"][i]) for i in range(3))


def test_locate_group_prior(world):
    rgb, art = world
    prof = synth.profile(ROWS, COLS)
    items = [dict(rc=(0, 0), mean_lab=art.cell_lab_mean[2, 3].copy())]
    res = locate_group(items, prof, art, constraints={"use_flat": False})
    assert res[0]["cell0"] == (3, 4)
    prior = np.ones((ROWS, COLS), int)
    prior[2, 3] = 0       # the photo says (3, 4) is empty: an assembled group should not sit there
    res_p = locate_group(items, prof, art, constraints={"use_flat": False}, prior=prior)
    assert res_p[0]["score"] >= res[0]["score"]


def test_locate_group_refine_with_crops(world):
    rgb, art = world
    prof = synth.profile(ROWS, COLS)
    items = []
    for (r, c), (l, cc) in zip([(0, 0), (0, 1)], [(4, 2), (4, 3)]):
        cont = synth.body_mm("TBTB", deltas=(0.3 * r, -0.2, 0.4, 0.1 * c))
        pts, rgba = synth.scan_piece(rgb, cont, (l, cc), psi=90.0)
        shp = synth.shape_of(pts)
        items.append(dict(rc=(r, c), mean_lab=piece_mean_lab(rgba), rgba=rgba, shape=shp,
                          theta_deg=snap_theta(shp, -90.0)[0]))
    res = locate_group(items, prof, art, constraints={"use_flat": False}, topk=2)
    assert res[0]["cell0"] == (4, 2) and res[0]["rot"] == 0


@pytest.mark.parametrize("theta_known", [True, False])
def test_pair_locate(world, theta_known):
    rgb, art = world
    prof = synth.profile(ROWS, COLS)
    X = (2, 3)
    T = prof.twin(*X)
    cont = synth.body_mm("TBTB", deltas=(0.6, -0.4, 0.3, -0.2))
    pa, ra = synth.scan_piece(rgb, cont, X, psi=0.0)
    pb, rb = synth.scan_piece(rgb, synth.twin_board_contour(cont, prof), T, psi=90.0)
    sa, sb = synth.shape_of(pa), synth.shape_of(pb)
    phi = free_dist(sa, sb)[2]
    a = dict(rgba=ra, shape=sa, theta_deg=0.0 if theta_known else None)
    b = dict(rgba=rb, shape=sb, phi_deg=phi)
    res = pair_locate(a, b, prof, art, topk=3)
    assert "error" not in res
    assert res["cells"][0]["cell"] == X, res["cells"]
    assert res["cells"][0]["rank"] == 1
    assert res["n_cells_tested"] == (ROWS - 2) * (COLS - 2)    # interior cells only (A has no F side)
    assert pair_locate(dict(rgba=ra), dict(rgba=rb), prof, art).get("error")
