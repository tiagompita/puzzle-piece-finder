"""Synthetic tests for :mod:`src.legacy` (legacy exploded-view pages; fast, no scans).

A synthetic page is a 3 x 4 block of the synthetic artwork of ``tests/synth.py`` (cells
(1..3, 3..6) of a 6 x 8 rot180 grid, so the top row has its F side on the puzzle border)
whose pieces have complementary tabs/blanks with off-centre knobs between neighbours, laid
out exploded (24 mm pitch, one row shifted half a cell in x) and turned as a whole by
0/90/180/270 degrees. The local grid must come out right, the registration must put every
piece on its cell, and the solve must keep it. Plus: proximity groups, side compatibility,
twin pairs and their placement algebra, and ``ingest_page`` end to end on a temporary project.
"""

import numpy as np
import pytest

import synth
from src import legacy
from src.shape import analyse, side_complement
from test_shape import MMPP

ROWS, COLS = 6, 8
BLOCK = [(l, c) for l in (1, 2, 3) for c in (3, 4, 5, 6)]
PITCH_MM = 24.0
SHIFT_MM = 9.25   # row 1 of the page shifted half a cell


def _kinds_and_deltas(seed=0):
    """Side kinds (top, right, bottom, left) and knob offsets per cell, complementary between neighbours."""
    rng = np.random.default_rng(seed)
    horiz = {}   # edge between (l, c) and (l, c + 1): (kind seen from the left piece, delta)
    vert = {}    # edge between (l, c) and (l + 1, c): (kind seen from the upper piece, delta)
    for l in range(1, ROWS + 1):
        for c in range(1, COLS + 1):
            horiz[(l, c)] = ("T" if rng.random() < 0.5 else "B", float(rng.uniform(-1.6, 1.6)))
            vert[(l, c)] = ("T" if rng.random() < 0.5 else "B", float(rng.uniform(-1.6, 1.6)))
    flip = {"T": "B", "B": "T"}
    out = {}
    for (l, c) in BLOCK:
        top = ("F", 0.0) if l == 1 else (flip[vert[(l - 1, c)][0]], -vert[(l - 1, c)][1])
        right = horiz[(l, c)]
        bottom = vert[(l, c)]
        left = (flip[horiz[(l, c - 1)][0]], -horiz[(l, c - 1)][1])
        sides = [top, right, bottom, left]
        out[(l, c)] = ("".join(s[0] for s in sides), tuple(s[1] for s in sides))
    return out


def _rot(v, deg):
    t = np.radians(deg)
    return np.asarray(v, float) @ np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]]).T


def _page(art_rgb, page_rot=0.0, shift_row=1, seed=0):
    """Raw pieces of a synthetic exploded page turned by ``page_rot`` (deg, clockwise on screen)."""
    kd = _kinds_and_deltas(seed)
    raw, truth = [], {}
    for i, (l, c) in enumerate(BLOCK):
        kinds, deltas = kd[(l, c)]
        cnt_mm = synth.body_mm(kinds, deltas=deltas)
        pts, rgba = synth.scan_piece(art_rgb, cnt_mm, (l, c), psi=page_rot)
        r, cc = l - 1, c - 3
        pos = np.array([40.0 + cc * PITCH_MM + (SHIFT_MM if r == shift_row else 0.0), 40.0 + r * PITCH_MM])
        pos = _rot(pos - 80.0, page_rot) + 120.0                    # turn the whole layout (mm)
        cnt = pts - pts.mean(0) + pos / MMPP
        x, y = cnt.min(0)
        w, h = cnt.max(0) - cnt.min(0)
        area = 0.5 * abs(np.sum(cnt[:, 0] * np.roll(cnt[:, 1], -1) - np.roll(cnt[:, 0], -1) * cnt[:, 1])) * MMPP ** 2
        raw.append({"contour": cnt, "rgba": rgba, "index": i, "bbox": [int(x), int(y), int(w), int(h)], "area_mm2": area,
                    "flags": {}})
        truth[i] = (l, c)
    return raw, truth


@pytest.fixture(scope="module")
def world():
    rgb = synth.art_rgb(ROWS, COLS, seed=5)
    return rgb, synth.make_art(rgb, ROWS, COLS), synth.profile(ROWS, COLS)


@pytest.mark.parametrize("page_rot", [0.0, 90.0, 180.0, 270.0])
def test_page_local_grid_and_registration(world, page_rot):
    rgb, art, prof = world
    raw, truth = _page(rgb, page_rot)
    res = legacy.analyse_pieces(raw, prof, art, None, "montado", MMPP, name=f"syn{int(page_rot)}")
    assert len(res.components) == 1, [len(c.members) for c in res.components]
    comp = res.components[0]
    assert len(comp.members) == len(BLOCK)
    # the local grid is a rigid copy of the block (rows/cols, possibly turned with the page)
    true_rc = {k: (truth[res.pieces[k].index][0] - 1, truth[res.pieces[k].index][1] - 3) for k in comp.members}
    k0 = comp.members[0]
    for k in comp.members:
        d_loc = np.subtract(comp.rc[k], comp.rc[k0])
        d_true = np.subtract(true_rc[k], true_rc[k0])
        assert sorted(np.abs(d_loc)) == sorted(np.abs(d_true))
    # the F sides of the top row are labelled and point the same way
    flats = {res.pieces[k].flat_dirs for k in comp.members if truth[res.pieces[k].index][0] == 1}
    assert len(flats) == 1 and len(next(iter(flats))) == 1
    # registration: every piece on its cell, clear margin, not mirrored
    best = comp.best
    assert best is not None and not best["mirror"]
    for k in comp.members:
        assert tuple(best["cells"][k]) == truth[res.pieces[k].index]
    assert comp.decision == "alta", comp.reasons
    # the solve (no twins in a lone block) keeps it
    legacy.solve_pages([res], prof, art, None)
    assert comp.decision == "alta"
    for k in comp.members:
        assert tuple(comp.best["cells"][k]) == truth[res.pieces[k].index]


def test_shifted_row_is_still_one_grid(world):
    rgb, art, prof = world
    raw, truth = _page(rgb, 0.0, shift_row=2)
    res = legacy.analyse_pieces(raw, prof, None, None, "montado", MMPP)
    assert [len(c.members) for c in res.components] == [len(BLOCK)]
    comp = res.components[0]
    for k in comp.members:
        l, c = truth[res.pieces[k].index]
        assert comp.rc[k] == (l - 1, c - 3)


def test_side_compat_kinds():
    from test_shape import make_piece
    a = analyse(make_piece("TBTB", deltas=(0.8, 0, 0, 0)), MMPP)
    b = analyse(make_piece("BTBT", deltas=(-0.8, 0, 0, 0)), MMPP)
    f = analyse(make_piece("FTBT"), MMPP)
    top = lambda s: min(s.sides, key=lambda sd: (sd.p0_mm[1] + sd.p1_mm[1]))  # noqa: E731
    sa, sb = top(a), top(b)
    assert {sa.kind, sb.kind} == {"T", "B"}
    assert legacy.side_compat(sa, top(f))["why"] == "F"
    assert legacy.side_compat(sa, sa)["why"] == "kind"
    # a T against the complementary B (reversed knob offset) is a valid edge
    sc = legacy.side_compat(sa, sb)
    assert sc["ok"] and sc["rms"] == pytest.approx(side_complement(sa, sb)[0])


def test_group_by_proximity():
    sq = lambda x, y: np.array([[x, y], [x + 18, y], [x + 18, y + 18], [x, y + 18]], float)  # noqa: E731
    dense = lambda c: np.vstack([np.linspace(c[i], c[(i + 1) % 4], 50, endpoint=False) for i in range(4)])  # noqa: E731
    contours = [dense(sq(0, 0)), dense(sq(19.5, 0)), dense(sq(0, 19.0)), dense(sq(60, 0)), dense(sq(79, 0.5))]
    groups = legacy.group_by_proximity(contours, gap_mm=3.0)
    assert sorted(map(sorted, groups)) == [[0, 1, 2], [3, 4]]


def test_twin_pairs_and_placement_algebra(world):
    """A piece and its twin (same cut turned by the profile's twin rotation) on two pages."""
    rgb, art, prof = world
    kinds, deltas = "TBBT", (0.9, -1.2, 0.4, -0.6)
    cnt = synth.body_mm(kinds, deltas=deltas)
    twin_cnt = synth.twin_board_contour(cnt, prof)
    cell_a = (2, 3)
    cell_b = prof.twin(*cell_a)
    pa_px, rgba_a = synth.scan_piece(rgb, cnt, cell_a, psi=30.0)
    pb_px, rgba_b = synth.scan_piece(rgb, twin_cnt, cell_b, psi=-50.0)
    other = synth.body_mm("BTTB", deltas=(0.2, 0.2, -0.3, 0.1))
    po_px, _ = synth.scan_piece(rgb, other, (3, 3))
    shapes = [analyse(pa_px, MMPP), analyse(pb_px, MMPP), analyse(po_px, MMPP)]
    pairs = legacy.twin_pairs(shapes, prof)
    assert [(a, b) for a, b, *_ in pairs] == [(0, 1)]
    a, b, d, phi, m = pairs[0]
    assert d < 0.2
    # board poses: crop -> board rotation is -psi (synth convention)
    A = legacy.PagePiece(n=1, index=0, contour=pa_px, bbox=[0, 0, 1, 1], area_mm2=1.0, shape=shapes[0], theta_deg=-30.0)
    B = legacy.PagePiece(n=1, index=0, contour=pb_px, bbox=[0, 0, 1, 1], area_mm2=1.0, shape=shapes[1], theta_deg=50.0)
    assert legacy._pair_status(prof, A, (cell_a, 0), B, (cell_b, 0), phi) == 1
    assert legacy._pair_status(prof, A, (cell_a, 0), B, ((1, 1), 0), phi) == -1
    assert legacy._pair_status(prof, A, (cell_a, 90), B, (cell_b, 0), phi) == -1
    comp = legacy.Component(id=0, members=[0], rc={0: (0, 0)})
    assert legacy._implied(prof, comp, A, 0, B, (cell_b, 0), phi) == (cell_a, 0)


def test_ingest_page_end_to_end(world, tmp_path):
    from src.profile import PuzzleProfile
    from src.state import Project
    rgb, art, prof = world
    raw, truth = _page(rgb, 90.0)
    H, W = 3200, 3200
    page = np.zeros((H, W, 3), np.uint8)
    page[:] = (90, 200, 90)
    # paste every crop on the page at an integer offset, so that page, contour and crop agree
    raw2 = []
    for i, (l, c) in enumerate(BLOCK):
        kinds, deltas = _kinds_and_deltas(0)[(l, c)]
        pts, rgba = synth.scan_piece(rgb, synth.body_mm(kinds, deltas=deltas), (l, c), psi=90.0)
        target = raw[i]["contour"].mean(0)
        off = np.round(target - pts.mean(0)).astype(int)
        h, w = rgba.shape[:2]
        sub = page[off[1]:off[1] + h, off[0]:off[0] + w]
        m = rgba[..., 3] > 0
        sub[m] = rgba[..., :3][m]
        raw2.append({"contour": (pts + off).astype(np.int32), "index": i})
    import cv2

    def fake_segment(photo, **kw):
        arr = np.asarray(photo)
        pieces = []
        for r in raw2:
            cnt = r["contour"]
            x, y, w, h = cv2.boundingRect(cnt.reshape(-1, 1, 2))
            mask = np.zeros((h, w), np.uint8)
            cv2.fillPoly(mask, [(cnt - [x, y]).reshape(-1, 1, 2)], 255)
            pieces.append({"index": r["index"], "contour": cnt.reshape(-1, 1, 2), "bbox": (x, y, w, h),
                           "area_px": float(cv2.contourArea(cnt.reshape(-1, 1, 2))), "image": arr[y:y + h, x:x + w].copy(),
                           "mask": mask, "is_cluster": False, "touches_frame": False, "touches_strip": False})
        return {"pieces": pieces, "mm_per_px": MMPP, "method": "scan"}

    from PIL import Image
    scan = tmp_path / "montado_p99.png"
    Image.fromarray(page).save(scan)
    pp = tmp_path / "puzzle.json"
    PuzzleProfile.from_dict(dict(prof.to_dict(), id="syn")).save(str(pp))
    pr = Project.create(str(tmp_path / "proj"), str(pp))
    r = legacy.ingest_page(pr, str(scan), "montado", "p99", art=art, segment=fake_segment)
    assert "error" not in r, r
    assert len(r["sections"]) == 1 and r["sections"][0]["decision"] == "alta"
    assert len(r["anchored"]) == 1 and not r["anchored"][0]["conflicts"]
    placed = {pr.piece(pid).index_in_scan: pr.piece(pid).celula for pid in pr.pieces}
    assert placed == truth
    assert pr.check_invariants() == []
    out = legacy.solve_project_sections(pr, art=art)
    assert out["anchored"] == [] and out["ambiguous"] == []
