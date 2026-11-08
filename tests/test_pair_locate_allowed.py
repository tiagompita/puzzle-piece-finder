"""``pair_locate(allowed=)``: excluded cells are never proposed; with A's pose unknown and its shape given, the 4
body-aligned rotations are tried and B's ``theta_deg`` is ignored (R7_CRITERIOS §4.1, H6)."""

import numpy as np
import pytest

import synth
from src.locate import body_beta_deg, pair_locate
from src.shape import free_dist

ROWS, COLS = 6, 8


@pytest.fixture(scope="module")
def pair():
    rgb = synth.art_rgb(ROWS, COLS, seed=3)
    art = synth.make_art(rgb, ROWS, COLS)
    prof = synth.profile(ROWS, COLS)
    X = (2, 3)
    cont = synth.body_mm("TBTB", deltas=(0.6, -0.4, 0.3, -0.2))
    # A scanned turned by 90 deg: its unknown pose must be recovered by the 4 rotations
    pa, ra = synth.scan_piece(rgb, cont, X, psi=90.0)
    pb, rb = synth.scan_piece(rgb, synth.twin_board_contour(cont, prof), prof.twin(*X), psi=-30.0)
    sa, sb = synth.shape_of(pa), synth.shape_of(pb)
    phi = free_dist(sa, sb)[2]
    a = dict(rgba=ra, shape=sa, theta_deg=None, phi_deg=0.0)
    b = dict(rgba=rb, shape=sb, theta_deg=0.0, phi_deg=phi)
    return prof, art, X, a, b


def test_four_rotations_find_the_cell(pair):
    prof, art, X, a, b = pair
    res = pair_locate(a, b, prof, art, topk=3)
    assert res["cells"][0]["cell"] == X, res["cells"]
    assert res["n_cells_tested"] == (ROWS - 2) * (COLS - 2)
    # B's theta is ignored: only A's pose (here unknown) and phi matter
    res2 = pair_locate(a, dict(b, theta_deg=123.0), prof, art, topk=3)
    assert [c["cell"] for c in res2["cells"]] == [c["cell"] for c in res["cells"]]
    # the winning rotation is one of the 4 body-aligned poses of A (A was scanned turned by 90 deg: theta = -90)
    b0 = body_beta_deg(a["shape"])
    assert any(res["cells"][0]["rot_deg"] == pytest.approx(b0 + 90.0 * g) for g in range(4))
    assert ((res["cells"][0]["rot_deg"] + 90.0 + 180.0) % 360.0 - 180.0) == pytest.approx(0.0, abs=3.0)


def test_allowed_excludes_cells(pair):
    prof, art, X, a, b = pair
    al = np.ones((ROWS, COLS), bool)
    assert [c["cell"] for c in pair_locate(a, b, prof, art, allowed=al)["cells"]] == \
           [c["cell"] for c in pair_locate(a, b, prof, art)["cells"]]
    al[X[0] - 1, X[1] - 1] = False
    res = pair_locate(a, b, prof, art, topk=5, allowed=al)
    assert X not in [c["cell"] for c in res["cells"]]
    assert res["n_cells_tested"] == (ROWS - 2) * (COLS - 2) - 1
    assert not np.isfinite(res["score_map"][X[0] - 1, X[1] - 1])
    assert pair_locate(a, b, prof, art, allowed=np.ones((2, 2), bool)).get("error")
