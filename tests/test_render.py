"""Synthetic tests for :mod:`src.render` (fast, no project files).

* corner registration: a synthetic piece in its board pose, turned by 3 deg and shifted
  1.2 mm in the scan, is brought back onto its cell within 0.2 mm / 0.5 deg;
* image refinement: on a synthetic art (solid colour cells), a start translation ~1.4 mm off
  is corrected within 0.2 mm (the code path, not the real art; the rotation is not observable
  at the art scale, see RENDER.md);
* fringe cleaning: a 0.5 mm green rim goes, an interior green patch stays, and nothing
  deeper than 0.7 mm is ever touched;
* composition: 4 interlocking pieces (silhouettes grown by 0.48 mm like the real ones) on a
  2 x 2 board leave no background pixel inside the block.
"""

import cv2
import numpy as np
import pytest
from PIL import Image

from src import render as R
from src.locate import body_center_mm
from src.profile import PuzzleProfile
from src.shape import analyse, transform_contour
from src.state import Project
from synth import art_rgb, body_mm, make_art, scan_piece
from test_shape import L0, MMPP, make_piece

BG_LAB = [79.2, -50.0, 47.0]


def _profile(rows, cols, offset=0.48, w=18.5, h=18.5):
    return PuzzleProfile(id="r", grid={"cols": cols, "rows": rows}, cell_mm={"w": w, "h": h},
                         symmetry={"type": "rot180"}, dpi=300, background_lab=BG_LAB,
                         calibration={"silhueta_silhueta": {"t95": None, "tmax": None},
                                      "celula_silhueta": {"t95": None, "tmax": None, "offset_mm": offset},
                                      "chord": {"normal_mm": 1.0, "f_adj_mm": 2.0}, "margin_min": 1.5})


def _bg_rgb():
    lab = np.array([[BG_LAB]], np.float32)
    return np.clip(cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)[0, 0] * 255 + 0.5, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------- registration
@pytest.mark.parametrize("psi,shift", [(3.0, (1.2, 0.0)), (-3.0, (0.0, -1.2)), (93.0, (0.85, 0.85))])
def test_corner_register_recovers_pose(psi, shift):
    prof = _profile(6, 8)
    cell = (3, 4)
    board = body_mm("TBTB") + R.cell_centre_mm(prof, *cell)            # board pose, body centre on the cell centre
    scan = transform_contour(board, psi, center=(0.0, 0.0)) + np.asarray(shift)
    sh = analyse(scan / MMPP, MMPP)
    assert sh.ok
    cr = R.corner_register(sh, prof, cell, theta0=-psi + 4.0)
    assert cr["ok"]
    assert abs(float(R.wrap_deg(cr["theta_deg"] + psi))) < 0.5
    A = R.pose_matrix(cr["theta_deg"], body_center_mm(sh), R.cell_centre_mm(prof, *cell))
    back = R._apply(A, sh.c[sh.corners])
    true_corners = R.cell_corners_mm(prof, *cell)                     # the generator's corners are the cell's
    err = [np.min(np.linalg.norm(true_corners - q, axis=1)) for q in back]
    assert max(err) < 0.2
    assert cr["shape_residual_mm"] < 0.2


def test_corner_register_flat_rule_picks_assignment():
    prof = _profile(6, 8)
    cell = (1, 4)                                                     # border cell: N must be F
    board = body_mm("FTBT") + R.cell_centre_mm(prof, *cell)           # sides top, right, bottom, left
    sh = analyse(board / MMPP, MMPP)
    cr = R.corner_register(sh, prof, cell, theta0=None)
    assert cr["f_ok"] and not cr["ambiguous"]
    assert abs(float(R.wrap_deg(cr["theta_deg"]))) < 0.5


def test_image_refine_synthetic_art():
    rows, cols, cell, psi = 6, 8, (3, 4), 20.0
    rgb = art_rgb(rows, cols, seed=3)
    art = make_art(rgb, rows, cols)
    pts, rgba = scan_piece(rgb, body_mm("TBBT"), cell, psi=psi)
    sh = analyse(pts, MMPP)
    piv = body_center_mm(sh)
    d0 = (1.2, -0.8)
    r = R.image_refine(rgba, (0.0, 0.0), MMPP, piv, cell, -psi, art, d_mm=d0, rot_deg=0)
    assert "error" not in r
    assert abs(d0[0] + r["ddx_mm"]) < 0.2 and abs(d0[1] + r["ddy_mm"]) < 0.2
    assert r["score"] < r["score0"]
    # with the rotation search, the translation is still found even from a 2 deg-off start
    r2 = R.image_refine(rgba, (0.0, 0.0), MMPP, piv, cell, -psi + 2.0, art, d_mm=d0)
    assert abs(d0[0] + r2["ddx_mm"]) < 0.3 and abs(d0[1] + r2["ddy_mm"]) < 0.3


# ---------------------------------------------------------------- fringe cleaning
def _fringe_rgba():
    H = W = 320
    rgba = np.zeros((H, W, 4), np.uint8)
    rgba[..., :3] = (120, 80, 50)                                     # brown piece
    a = np.zeros((H, W), np.uint8)
    cv2.circle(a, (160, 160), 140, 255, -1)
    rgba[..., 3] = a
    alpha = rgba[..., 3] > 0
    depth = R._depth_px(alpha)
    rim = alpha & (depth <= 0.5 / MMPP)                              # 0.5 mm green rim
    rgba[rim, :3] = _bg_rgb()
    patch = np.zeros((H, W), bool)
    patch[150:175, 150:175] = True                                    # interior green patch (drawn green, deep)
    rgba[patch, :3] = _bg_rgb()
    return rgba, rim, patch, depth


def test_clean_crop_band_only():
    rgba, rim, patch, depth = _fringe_rgba()
    out = R.clean_crop(rgba, BG_LAB, MMPP, band_mm=0.7)
    removed = (rgba[..., 3] > 0) & (out[..., 3] == 0)
    assert removed[rim].all()                                         # the whole rim goes
    assert not removed[patch].any()                                   # the interior green stays
    assert not removed[depth > 0.7 / MMPP].any()                      # nothing beyond the band, ever
    deep = depth > 0.7 / MMPP
    assert np.array_equal(out[deep], rgba[deep])                      # alpha and colour untouched beyond the band
    # band clamp: asking for a wider band never widens it
    out2 = R.clean_crop(rgba, BG_LAB, MMPP, band_mm=3.0)
    assert not ((rgba[..., 3] > 0) & (out2[..., 3] == 0) & (depth > 0.7 / MMPP)).any()


def test_clean_crop_green_not_touching_boundary_stays():
    rgba, rim, patch, depth = _fringe_rgba()
    rgba[rim, :3] = (120, 80, 50)
    inner = (depth > 3) & (depth <= 6)                               # green ring inside the band, not on the boundary
    rgba[inner, :3] = _bg_rgb()
    out = R.clean_crop(rgba, BG_LAB, MMPP)
    assert (out[..., 3] == rgba[..., 3]).all()


# ---------------------------------------------------------------- composition
_KINDS = {(1, 1): "FTBF", (1, 2): "FFTB", (2, 1): "TBFF", (2, 2): "BFFT"}    # top, right, bottom, left
_COLOURS = {(1, 1): (200, 40, 40), (1, 2): (40, 40, 200), (2, 1): (220, 200, 30), (2, 2): (200, 40, 200)}


def _grown_contour(board_px: np.ndarray, grow_px: int):
    lo = np.floor(board_px.min(0)).astype(int) - grow_px - 4
    m = np.zeros((int(np.ceil(board_px[:, 1].max())) - lo[1] + grow_px + 6,
                  int(np.ceil(board_px[:, 0].max())) - lo[0] + grow_px + 6), np.uint8)
    cv2.fillPoly(m, [np.round(board_px - lo).astype(np.int32).reshape(-1, 1, 2)], 255)
    m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow_px + 1, 2 * grow_px + 1)))
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    return max(cs, key=cv2.contourArea).reshape(-1, 2).astype(float) + lo


def test_compose_board_no_gaps(tmp_path):
    prof = _profile(2, 2)
    pp = tmp_path / "puzzle.json"
    prof.save(str(pp))
    pr = Project.create(str(tmp_path / "proj"), str(pp))
    sid = pr.add_scan(None, dpi=300)
    grow = int(round(0.48 / MMPP))
    for k, (cell, kinds) in enumerate(sorted(_KINDS.items())):
        psi = [7.0, -12.0, 95.0, 181.0][k]
        board = make_piece(kinds, offset=(0, 0)) * MMPP + R.cell_corners_mm(prof, *cell)[0]   # board mm, exact cut
        scan_mm = transform_contour(board, psi, center=board.mean(0)) + np.array([30.0 + 40.0 * k, 30.0])
        cnt = _grown_contour(scan_mm / MMPP, grow)
        x, y, w, h = cv2.boundingRect(cnt.astype(np.int32).reshape(-1, 1, 2))
        x, y, w, h = x - 3, y - 3, w + 6, h + 6
        alpha = np.zeros((h, w), np.uint8)
        cv2.fillPoly(alpha, [(cnt - [x, y]).astype(np.int32).reshape(-1, 1, 2)], 255)
        rgba = np.dstack([np.zeros((h, w, 3), np.uint8) + np.array(_COLOURS[cell], np.uint8), alpha])
        rel = f"crops/P{k + 1:04d}.png"
        Image.fromarray(rgba).save(pr.p(rel))
        pid = pr.add_piece(sid, {"index_in_scan": k, "shape": analyse(cnt, MMPP), "contour": cnt.astype(np.int32),
                                 "bbox": [x, y, w, h], "crop_path": rel})
        pr.place(pid, cell, theta_deg=-psi)
    pr.save()
    pls = {pid: R.register_piece(pr, pid, image=False) for pid in R.placed_ids(pr)}
    assert all(p["method"] == "corners" for p in pls.values())
    gaps = R.seam_gaps(pr, pls)
    assert len(gaps) == 4
    assert max(abs(g["gap_mm"]) for g in gaps) < 0.3
    img = R.compose_board(pr, 100, layers=("pieces",), placements=pls, bleed_mm=0)   # geometry only, no gap filler
    hh, ww = img.shape[:2]
    inner = img[3:hh - 3, 3:ww - 3].astype(int)
    dist_bg = np.abs(inner - 40).max(-1)
    assert dist_bg.min() > 25, "background visible between pieces"


def test_decontaminate_band_blend():
    """A blue piece whose outer band is a 15 % blend with the green paper gets its blue back (colour
    only, band only); a fully green rim outside it is removed."""
    H = W = 200
    blue = np.array((70, 120, 190), np.float32)
    a = np.zeros((H, W), np.uint8)
    cv2.rectangle(a, (20, 20), (180, 180), 255, -1)
    rgba = np.dstack([np.zeros((H, W, 3), np.uint8) + blue.astype(np.uint8), a])
    depth = R._depth_px(a > 0)
    rgba[depth <= 2, :3] = _bg_rgb()                                  # pure green, outermost 2 px
    mix = (depth > 2) & (depth <= 5)
    rgba[mix, :3] = (0.85 * blue + 0.15 * _bg_rgb()).astype(np.uint8)  # light blend, kept by the threshold
    out = R.clean_crop(rgba, BG_LAB, MMPP)
    assert (out[depth <= 2, 3] == 0).all()
    kept = mix & (out[..., 3] > 0)
    assert kept.any()
    lab_blue = R._lab(blue.astype(np.uint8).reshape(1, 1, 3))[0, 0]
    err_before = np.linalg.norm(R._lab(rgba[..., :3])[kept] - lab_blue, axis=1).mean()
    err_after = np.linalg.norm(R._lab(out[..., :3])[kept] - lab_blue, axis=1).mean()
    assert err_after < 0.6 * err_before                               # sRGB blend unmixed in Lab: about halved
    deep = depth > 0.7 / MMPP
    assert np.array_equal(out[deep], rgba[deep])


def test_light_band_only_on_light_pieces():
    """Default: 1.2 mm band only for light pieces (interior p5 bg distance > LIGHT_PIECE_P5_MIN);
    a green-grass-like piece keeps 0.7 mm even with green reaching 1.0 mm deep."""
    H = W = 240
    a = np.zeros((H, W), np.uint8)
    cv2.rectangle(a, (20, 20), (220, 220), 255, -1)
    depth = R._depth_px(a > 0)
    rim = (a > 0) & (depth <= 1.0 / MMPP)                             # green 1.0 mm deep
    for colour, light in (((70, 120, 190), True), ((95, 140, 60), False)):   # blue sky / green grass
        rgba = np.dstack([np.zeros((H, W, 3), np.uint8) + np.array(colour, np.uint8), a])
        rgba[rim, :3] = _bg_rgb()
        m = R.fringe_masks(rgba, BG_LAB, MMPP)
        assert R.is_light(m) == light
        out = R.clean_crop(rgba, BG_LAB, MMPP)
        removed = (rgba[..., 3] > 0) & (out[..., 3] == 0)
        lim = (R.LIGHT_BAND_MM if light else R.BAND_MM) / MMPP
        assert not removed[depth > lim].any()
        assert np.array_equal(out[depth > lim], rgba[depth > lim])
        assert removed[rim & (depth <= lim)].all()
        if light:
            assert removed[rim].all()                                 # the whole 1.0 mm rim goes on sky
        else:
            assert not removed[depth > R.BAND_MM / MMPP].any()        # grass: never beyond 0.7 mm
