"""Synthetic tests for :mod:`src.border` (fast, no scans, no project).

A border run of 6 free cells (row 1, columns 2..7 of a 6 x 8 rot180 grid) between two
fixed corner pieces; the 6 pieces have complementary tabs/blanks with off-centre knobs
between neighbours, an F side on top, and come as 3 blocks (3 + 2 + 1 pieces) given in
turned local frames. The DP must recover the order and the rotations. Plus: the twin step
pins the right piece and the pin decides a tie, and the F-suspect rules.
"""

import numpy as np
import pytest

from src import border
from src.shape import analyse, transform_contour
from test_shape import L0, MMPP, _side_points, make_piece
import synth

COLS = list(range(2, 8))
FLIP = {"T": "B", "B": "T"}


def _kinds(seed=3):
    """Per cell (1, c), c = 1..8: (kinds top,right,bottom,left; deltas), complementary between neighbours."""
    rng = np.random.default_rng(seed)
    horiz = {c: ("T" if rng.random() < 0.5 else "B", float(rng.uniform(-2.0, 2.0))) for c in range(1, 9)}
    out = {}
    for c in range(1, 9):
        top = ("F", 0.0)
        right = ("F", 0.0) if c == 8 else horiz[c]
        bottom = ("T" if rng.random() < 0.5 else "B", float(rng.uniform(-1.5, 1.5)))
        left = ("F", 0.0) if c == 1 else (FLIP[horiz[c - 1][0]], -horiz[c - 1][1])
        sides = [top, right, bottom, left]
        out[c] = ("".join(s[0] for s in sides), tuple(s[1] for s in sides))
    return out


def _board_contour_mm(kinds, deltas):
    pts = make_piece(kinds, deltas=deltas) * MMPP
    return pts - (np.array([40.0, 30.0]) + L0 / 2)


def _bpiece(pid, contour_board_mm, local_rot):
    """BPiece whose local frame is the board frame turned back by ``local_rot`` (the solve must find it)."""
    loc = transform_contour(contour_board_mm, -local_rot, center=(0.0, 0.0))
    sh = analyse(loc / MMPP, MMPP)
    assert sh.ok
    return border.piece_from_shape(pid, sh, 0.0)


def _local_rc(board_off, rot):
    """Local offset that :func:`border._rot_rc` maps to ``board_off`` under ``rot``."""
    for r in range(-3, 4):
        for c in range(-3, 4):
            if border._rot_rc((r, c), rot) == tuple(board_off):
                return (r, c)
    raise AssertionError


def _problem(seed=3, rots=(90, 180, 270)):
    prof = synth.profile(rows=6, cols=8)
    kd = _kinds(seed)
    cont = {c: _board_contour_mm(*kd[c]) for c in range(1, 9)}
    fixed = {}
    for c in (1, 8):
        sh = analyse(cont[c] / MMPP, MMPP)
        fixed[(1, c)] = (border.piece_from_shape(f"K{c}", sh, 0.0), 0)
    groups = {"X": [2, 3, 4], "Y": [5, 6], "Z": [7]}
    rot_of = dict(zip(groups, rots))
    pieces, blocks = {}, {}
    for g, cols in groups.items():
        rot = rot_of[g]
        members = {}
        for c in cols:
            pid = f"P{c}"
            pieces[pid] = _bpiece(pid, cont[c], rot)
            members[pid] = _local_rc((0, c - cols[0]), rot)
        blocks[g] = border.Block(id=g, members=members)
    required = {(1, c) for c in COLS}
    return prof, pieces, blocks, fixed, required, rot_of


def _placements(prof, pieces, blocks, fixed, required):
    nfl = {pid: bp.n_flat for pid, bp in pieces.items()}
    allp = []
    for blk in blocks.values():
        for pl in border.enumerate_placements(blk, prof, required, lambda cell: False, n_flat_of=nfl):
            pl.terms = border.unary_cost(pl, pieces, prof, fixed)
            pl.unary = pl.terms["total"]
            allp.append(pl)
    return allp


def test_chain_recovers_order_and_rotation():
    prof, pieces, blocks, fixed, required, rot_of = _problem()
    allp = _placements(prof, pieces, blocks, fixed, required)
    res = border.solve_cover(required, allp, pieces, prof)
    assert res["complete"] and np.isfinite(res["cost"])
    got = {pid: cell for pl in res["chosen"] for pid, cell in pl.cells.items()}
    assert got == {f"P{c}": (1, c) for c in COLS}
    assert {pl.block: pl.rot for pl in res["chosen"]} == rot_of
    # the best other ordering is clearly worse: swap the blocks by forbidding the true place of Z
    alt = border.solve_cover(required, allp, pieces, prof, forbid=lambda p: p.block == "Z" and p.cells["P7"] == (1, 7))
    assert alt["cost"] > res["cost"] + 2.0


def test_runs_are_ordered_along_the_border():
    prof = synth.profile(rows=6, cols=8)
    runs = border.border_runs([(1, 5), (1, 3), (1, 4), (4, 1), (3, 1)], prof)
    assert runs == [[(3, 1), (4, 1)], [(1, 3), (1, 4), (1, 5)]]


def test_twin_pin_fixes_a_piece():
    prof = synth.profile(rows=6, cols=8)
    rng = np.random.default_rng(7)
    # 5 candidates of the same class (F on top) with different knob offsets; C2 is the twin of the piece at (6, 4)
    cands = {}
    for k in range(5):
        deltas = (0.0, float(rng.uniform(-2, 2)), float(rng.uniform(-2, 2)), float(rng.uniform(-2, 2)))
        cont = _board_contour_mm("FTBT", deltas)
        cands[f"C{k}"] = (deltas, cont)
    deltas2, cont2 = cands["C2"]
    twin_cont = transform_contour(cont2, prof.twin_rotation_deg(), center=(0.0, 0.0))
    twin_cont = twin_cont + np.random.default_rng(1).normal(0, 0.03, twin_cont.shape)
    placed = border.BPiece(id="T", shape=analyse(twin_cont / MMPP, MMPP))
    cand = {pid: border.piece_from_shape(pid, analyse(c / MMPP, MMPP), 0.0) for pid, (_, c) in cands.items()}
    cell = (1, 5)
    assert prof.twin(*cell) == (6, 4)
    pins, table = border.twin_pins([cell], {cell: placed}, cand, prof)
    assert pins == {"C2": cell}
    assert table[0]["d1"] < 0.2 and table[0]["margin"] >= 1.5
    # the pin decides a tie: two copies of the same shape compete for (1, 5)
    allp = []
    blocks = {pid: border.Block(id=pid, members={pid: (0, 0)}) for pid in ("C2", "D2")}
    pieces = {"C2": cand["C2"], "D2": border.piece_from_shape("D2", cand["C2"].shape, 0.0)}
    for blk in blocks.values():
        allp += border.enumerate_placements(blk, prof, {cell}, lambda c: False, n_flat_of={"C2": 1, "D2": 1})
    for pl in allp:
        pl.unary = border.unary_cost(pl, pieces, prof, {})["total"]
    for want in ("C2", "D2"):
        forbid = lambda p, want=want: next(iter(p.cells)) != want
        res = border.solve_cover({cell}, allp, pieces, prof, forbid=forbid)
        assert next(iter(res["chosen"][0].cells)) == want


def _piece_with_bump(r=1.6, d=0.9):
    """Contour (px) TBTF-like piece whose 'flat' left side carries a small bump (kind F, not straight)."""
    Q = np.array([(0, 0), (L0, 0), (L0, L0), (0, L0)], float) + np.array([40.0, 30.0])
    parts = [_side_points(Q[0], Q[1], "T"), _side_points(Q[1], Q[2], "B"), _side_points(Q[2], Q[3], "T"),
             _side_points(Q[3], Q[0], "T", r=r, d=d)]
    return np.vstack(parts) / MMPP


def test_f_suspects():
    sh = analyse(_piece_with_bump(), MMPP)
    assert sh.ok and sh.n_flat == 1
    bad, why = border.f_suspects(sh)
    assert bad == [sh.types.index("F")] and "desvio" in why[0]
    bp = border.piece_from_shape("S", sh, 0.0)
    assert bp.suspect and None in bp.dirs.values()          # the suspect F side is of unknown kind
    good = analyse(make_piece("FTBT"), MMPP)
    assert border.f_suspects(good) == ([], [])
    opp = analyse(make_piece("FTFB"), MMPP)
    assert "opostos" in border.f_suspects(opp)[1][0]
    corner = analyse(make_piece("FFTB"), MMPP)
    assert border.f_suspects(corner)[0] == []
    assert len(border.f_suspects(corner, corner_free=False)[0]) == 2


def test_damage():
    cell = {"w": 18.5, "h": 17.9}
    assert border.damage(analyse(make_piece("FTBT"), MMPP), cell) == []
    long = [(0, 0), (L0 + 3.6, 0), (L0 + 3.6, L0), (0, L0)]          # a merged fragment: 22.1 mm chords
    sh = analyse(make_piece("FTBT", corners=long), MMPP)
    assert sh.ok and border.damage(sh, cell)
    assert border.damage(analyse(make_piece("FTBT"), MMPP), cell) == []
    bp = border.piece_from_shape("D", sh, 0.0, cell_mm=cell)
    assert bp.damaged and all(v is None for v in bp.dirs.values())


def test_side_cost_rules():
    sh = analyse(make_piece("FTBT"), MMPP)
    f, t, b = sh.sides[0], sh.sides[1], sh.sides[2]
    assert border.side_cost(f, t) == border.SIDE_P_F
    assert border.side_cost(t, t) == border.SIDE_P_KIND
    assert border.side_cost(None, t) == border.SIDE_NEUTRAL
    assert border.side_cost(t, b) <= border.SIDE_COST_MAX
