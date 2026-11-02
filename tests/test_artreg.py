"""Synthetic tests for BUG 4 (art under the board): :mod:`src.artreg`, the single board -> art
transform (:meth:`src.profile.PuzzleProfile.art_matrix`, :func:`src.locate.load_art_rectified`,
:meth:`src.locate.CellArt.load`) and the ``at_edge`` flag of :func:`src.render.image_refine`.

The "art file" is a textured raster of the grid (64 x 47 cells at 25 px/cell) warped by a known
affine (scale 1.02 / 0.98, 0.3 deg, translation ~0.6 cell): the bbox model is then wrong by up to
about a cell, the registration recovers the affine, and ``CellArt.load`` with the registration
returns the right cell content.
"""

import cv2
import numpy as np
import pytest

from src import artreg
from src import render as R
from src.locate import CellArt, body_center_mm
from src.profile import PuzzleProfile
from src.shape import analyse
from synth import art_rgb, body_mm, make_art, scan_piece
from test_shape import MMPP

ROWS, COLS, CPX = 47, 64, 25
CELL = (18.5, 17.9)
FILE_SIZE = (1720, 1260)


def _texture(seed=0):
    """Textured grid raster (smooth noise at several scales + random edges), RGB uint8."""
    rng = np.random.default_rng(seed)
    H, W = ROWS * CPX, COLS * CPX
    acc = np.zeros((H, W, 3), np.float32)
    for k, amp in ((8, 60), (24, 40), (80, 25)):
        small = rng.normal(0, 1, (H // k + 2, W // k + 2, 3)).astype(np.float32)
        acc += amp * cv2.resize(small, (W, H), interpolation=cv2.INTER_CUBIC)
    for _ in range(400):
        x0, y0 = rng.integers(0, W), rng.integers(0, H)
        x1, y1 = x0 + rng.integers(-60, 60), y0 + rng.integers(-60, 60)
        cv2.line(acc, (int(x0), int(y0)), (int(x1), int(y1)), tuple(float(v) for v in rng.uniform(-80, 80, 3)), 2)
    return np.clip(acc + 128, 0, 255).astype(np.uint8)


def _nominal_matrix():
    """The bbox-style prior: 25 px per cell, the grid centred in the file."""
    sx, sy = CPX / CELL[0], CPX / CELL[1]
    return np.array([[sx, 0, (FILE_SIZE[0] - COLS * CPX) / 2], [0, sy, (FILE_SIZE[1] - ROWS * CPX) / 2]], float)


def _true_matrix():
    """Board mm -> file px: the prior after a perturbation about the grid centre (scale 1.02 / 0.98,
    0.3 deg, translation 0.6 cell along the diagonal): up to ~1.2 cell off the prior at the corners."""
    C = np.array([COLS * CELL[0], ROWS * CELL[1]]) / 2
    t = np.radians(0.3)
    R2 = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
    L = R2 @ np.diag([1.02, 0.98])
    tr = 0.6 / np.sqrt(2) * np.array(CELL)
    P = np.c_[L, C - L @ C + tr]                              # board mm -> perturbed board mm
    M0 = _nominal_matrix()
    return np.c_[M0[:, :2] @ P[:, :2], M0[:, :2] @ P[:, 2] + M0[:, 2]]


def _warp_to_file(raster, M):
    """File px (index) -> board mm -> raster px: the art file as the known affine sees the grid."""
    k = np.diag([CPX / CELL[0], CPX / CELL[1]])               # board mm -> raster continuous px
    Minv = np.linalg.inv(M[:, :2])
    A = k @ Minv                                             # file continuous -> raster continuous
    b = -A @ M[:, 2]
    # index form: raster_idx = A (file_idx + 0.5) + b - 0.5
    Ai = np.c_[A, A @ [0.5, 0.5] + b - 0.5]
    return cv2.warpAffine(raster, Ai, FILE_SIZE, flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                          borderMode=cv2.BORDER_REFLECT)


@pytest.fixture(scope="module")
def world():
    raster = _texture(1)
    M = _true_matrix()
    file_rgb = _warp_to_file(raster, M)
    return raster, M, file_rgb


def _corner_rms_cells(Ma, Mb):
    P = np.array([[0, 0], [COLS * CELL[0], 0], [0, ROWS * CELL[1]], [COLS * CELL[0], ROWS * CELL[1]]], float)
    Qa = P @ Ma[:, :2].T + Ma[:, 2]
    return float(np.sqrt(np.mean(artreg.residual_cells(Mb, P, Qa, CELL) ** 2)))


def test_register_art_recovers_affine(world):
    raster, M, file_rgb = world
    rng = np.random.default_rng(2)
    cells = [(l, c) for l in range(1, ROWS + 1) for c in range(1, COLS + 1) if rng.random() < 0.12]
    mask = np.zeros(raster.shape[:2], bool)
    for (l, c) in cells:
        mask[(l - 1) * CPX:l * CPX, (c - 1) * CPX:c * CPX] = True
    board = raster.copy()
    board[~mask] = 60
    M0 = _nominal_matrix()                                     # the bbox-style prior
    assert _corner_rms_cells(M, M0) > 0.5                      # the prior is off by more than half a cell
    res = artreg.register_art(board, mask, file_rgb, ROWS, COLS, CELL, M0, cells)
    assert "error" not in res, res
    assert _corner_rms_cells(M, res["matrix"]) <= 0.05
    assert res["residual_cells"]["after"]["median"] < res["residual_cells"]["before"]["median"]
    d = res["decomposition"]
    assert d["rotation_deg"] == pytest.approx(0.3, abs=0.05)


def _profile(art):
    return PuzzleProfile(id="t", grid={"cols": COLS, "rows": ROWS}, cell_mm={"w": CELL[0], "h": CELL[1]},
                         symmetry={"type": "rot180"}, art=art)


def test_cellart_load_uses_registration(world, tmp_path):
    raster, M, file_rgb = world
    cv2.imwrite(str(tmp_path / "art.png"), cv2.cvtColor(file_rgb, cv2.COLOR_RGB2BGR))
    truth = CellArt.from_rgb(raster, ROWS, COLS, pitch_mm=CELL, l_shift=0.0).cell_lab_mean
    M0 = _nominal_matrix()
    bbox = [int(M0[0, 2]), int(M0[1, 2]), COLS * CPX, ROWS * CPX]  # the prior as a bbox (whole file is art)
    only_bbox = CellArt.load(_profile({"file": "art.png", "bbox": bbox}), tmp_path, l_shift=0.0)
    reg = {"matrix": M.tolist(), "units": "board_mm->art_px"}
    # with the registration the bbox is the art content of the file: here the whole file
    with_reg = CellArt.load(_profile({"file": "art.png", "bbox": [0, 0, FILE_SIZE[0], FILE_SIZE[1]], "registration": reg}),
                            tmp_path, l_shift=0.0)
    err_bbox = np.abs(only_bbox.cell_lab_mean - truth).mean()
    err_reg = np.abs(with_reg.cell_lab_mean - truth).mean()
    assert err_reg < 1.0                                       # the right cell content (dE units)
    assert err_bbox > 5 * err_reg                              # the bbox alone is displaced
    # the raster keeps the art's native resolution along each grid axis
    assert with_reg.cell_px[0] == pytest.approx(CPX * 1.02, abs=0.1)
    assert with_reg.cell_px[1] == pytest.approx(CPX * 0.98, abs=0.1)


def test_art_matrix_bbox_and_registration():
    p = _profile({"file": "x.png", "bbox": [10, 20, 1600, 1175]})
    M = p.art_matrix()
    assert np.allclose(M, [[1600 / (COLS * CELL[0]), 0, 10], [0, 1175 / (ROWS * CELL[1]), 20]])
    q = _profile({"file": "x.png", "bbox": [10, 20, 1600, 1175], "registration": {"matrix": [[1, 0, 2], [0, 1, 3]]}})
    assert np.allclose(q.art_matrix(), [[1, 0, 2], [0, 1, 3]])
    assert _profile({"file": None, "bbox": None}).art_matrix() is None


def test_bbox_rectification_is_the_plain_crop():
    """Without a registration, the rectified raster is exactly the bbox crop (old behaviour)."""
    rng = np.random.default_rng(0)
    img = rng.integers(0, 255, (60, 90, 3), np.uint8)
    from src.locate import rectify_art
    bbox = [5, 7, 64, 47]
    p = _profile({"file": "x", "bbox": bbox})
    out = rectify_art(img, p.art_matrix(), ROWS, COLS, CELL, content_bbox=bbox)
    assert np.array_equal(out, img[7:54, 5:69])


def test_image_refine_translation_only_not_at_edge():
    """``rot_deg=0`` gives one rotation sample: that is not a minimum at the edge of the rotation range."""
    rows, cols, cell, psi = 6, 8, (3, 4), 20.0
    rgb = art_rgb(rows, cols, seed=3)
    art = make_art(rgb, rows, cols)
    pts, rgba = scan_piece(rgb, body_mm("TBBT"), cell, psi=psi)
    piv = body_center_mm(analyse(pts, MMPP))
    r = R.image_refine(rgba, (0.0, 0.0), MMPP, piv, cell, -psi, art, d_mm=(0.6, -0.4), rot_deg=0)
    assert "error" not in r
    assert len(r["curve"]) == 1
    assert r["at_edge"] is False


# ---------------------------------------------------------------- cells the art file does not reach (row 47 of the Alpes)
def test_last_row_outside_art_is_no_art(world, tmp_path):
    """A registration that puts the last grid row below the art content: that row has no art
    (``cell_lab_mean`` NaN, :func:`de_cell` inf, the rendered art grey, never replicated streaks)."""
    from src.locate import de_cell, load_art_rectified, piece_render
    raster, _, _ = world
    cv2.imwrite(str(tmp_path / "art.png"), cv2.cvtColor(raster[:-CPX], cv2.COLOR_RGB2BGR))   # the file stops 1 row short
    M = np.array([[CPX / CELL[0], 0, 0], [0, CPX / CELL[1], 0]], float)
    prof = _profile({"file": "art.png", "bbox": [0, 0, COLS * CPX, (ROWS - 1) * CPX],
                     "registration": {"matrix": M.tolist(), "units": "board_mm->art_px"}})
    art = CellArt.load(prof, tmp_path, l_shift=0.0)
    assert np.isnan(art.cell_lab_mean[-1]).all()
    assert np.isfinite(art.cell_lab_mean[:-1]).all()
    assert not art.has_art(ROWS, 10) and art.has_art(ROWS - 1, 10)
    assert np.isfinite(art.lab).all()                          # whole-raster filters never see NaN
    # a crop of the art itself, on the last row: no art -> dE inf (the no-art outcome); on row ROWS-1: ~0
    crop = np.dstack([raster[(ROWS - 2) * CPX:(ROWS - 1) * CPX, 9 * CPX:10 * CPX], np.full((CPX, CPX), 255, np.uint8)])
    rnd = piece_render(crop, 0.0, art.canvas, l_shift=0.0, erode_px=0)
    d_ok = de_cell(rnd, ROWS - 1, 10, art)["dE"]
    assert np.isfinite(d_ok) and d_ok < de_cell(rnd, ROWS - 3, 30, art)["dE"]
    assert de_cell(rnd, ROWS, 10, art)["dE"] == float("inf")
    # the board underlay: the row without art is filled, not streaked
    rgb = load_art_rectified(prof, tmp_path, fill=(40, 40, 40))
    assert (rgb[-CPX + 2:] == 40).all()


def test_twin_no_art_cell_reason():
    """The twin cell has no art: reason 'sem arte na célula', no dE, never 'aceite' (the image tie-break is mandatory)."""
    import synth
    from src.shape import transform_contour
    from src.twin import TwinItem, find_twin
    rows, cols = 6, 8
    prof = synth.profile(rows, cols, symmetry={"type": "rot180"})
    rgb = synth.art_rgb(rows, cols, seed=3)
    valid = np.ones(rgb.shape[:2], bool)
    valid[-synth.CELL_PX:] = False                              # last row: no art
    art = CellArt.from_rgb(rgb, rows, cols, pitch_mm=(synth.PITCH_MM,) * 2, l_shift=0.0, valid=valid)
    rng = np.random.default_rng(1)
    cont = synth.body_mm("TBFT", deltas=(0.8, -0.5, 0.0, 0.3))
    q = TwinItem(id="Q", shape=synth.shape_of(cont / MMPP), cell=(1, 3), theta_deg=0.0)   # twin cell (6, 6)
    others = []
    for k in range(20):
        s = synth.shape_of(synth.body_mm("TBFT", deltas=tuple(rng.uniform(-2, 2, 4)), radii=tuple(rng.uniform(2.5, 3.5, 4))) / MMPP)
        if s.ok:
            others.append(TwinItem(id=f"D{k}", shape=s))
    twin = transform_contour(cont, 180, center=(0, 0)) + rng.normal(0, 0.1, cont.shape)
    t = TwinItem(id="T", shape=synth.shape_of(transform_contour(twin, 33.0) / MMPP))
    res = find_twin(q, others + [t], profile=prof, art=art)
    assert res["twin_cell"] == (6, 6)
    assert res["candidates"][0]["id"] == "T"
    assert res["decision_shape"] == "aceite"
    assert res["decision"] == "ambigua", res["reasons"]
    assert any("sem arte na célula (6, 6)" in r for r in res["reasons"]), res["reasons"]
    assert res["candidates"][0]["image"] is None
