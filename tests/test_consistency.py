"""Synthetic tests for :mod:`src.consistency` (orientation suspects of the placed pieces; fast).

Three pieces in a row on the 4×6 synthetic profile of ``tests/test_query.py``, all interior cells:
C (2,2) ``BTBB`` | A (2,3) ``TBTB`` | B (2,4) ``BBBT`` (kinds top, right, bottom, left in the board
pose). In the right poses every shared side is T↔B: no suspect. B placed turned +90° (clockwise on the
screen) puts its bottom B on the W side, against A's E side B: B↔B, so B is ``impossivel`` and only
−90° fixes it. A's B↔B with B is explained by B (no rotation of A fixes it: its W side would face C's
T with a T), so A is not reported. The check never writes to the project.
"""

import os

import cv2
import numpy as np
from PIL import Image

import synth
from src import consistency as C
from src.shape import analyse
from src.state import Project
from test_query import BG, _piece_px
from test_shape import MMPP

PSI = {"C": 31.0, "A": 23.0, "B": -40.0}


def _row_project(tmp_path, rot_b=0.0, rot_c=0.0):
    prof = synth.profile(rows=4, cols=6, p90=None)
    pp = tmp_path / "puzzle.json"
    prof.save(str(pp))
    pr = Project.create(str(tmp_path / "proj"), str(pp))
    spec = [("C", "BTBB", (2, 2), rot_c), ("A", "TBTB", (2, 3), 0.0), ("B", "BBBT", (2, 4), rot_b)]
    pts_all = [_piece_px(synth.body_mm(kinds), PSI[name], (400 + 600 * i, 400)) for i, (name, kinds, _, _) in enumerate(spec)]
    img = np.full((800, 2000, 3), BG, np.uint8)
    for pts in pts_all:
        cv2.fillPoly(img, [np.round(pts).astype(np.int32).reshape(-1, 1, 2)], (200, 40, 40))
    scan = tmp_path / "scan.png"
    Image.fromarray(img).save(scan)
    sid = pr.add_scan(str(scan), dpi=300, lote=1)
    os.makedirs(pr.p("crops"), exist_ok=True)
    ids = {}
    for i, ((name, kinds, cell, rot), pts) in enumerate(zip(spec, pts_all)):
        x0, y0 = np.floor(pts.min(0)).astype(int) - 10
        x1, y1 = np.ceil(pts.max(0)).astype(int) + 10
        al = np.zeros(img.shape[:2], np.uint8)
        cv2.fillPoly(al, [np.round(pts).astype(np.int32).reshape(-1, 1, 2)], 255)
        rel = f"crops/P{i + 1:04d}.png"
        Image.fromarray(np.ascontiguousarray(np.dstack([img, al])[y0:y1, x0:x1])).save(pr.p(rel))
        pid = pr.add_piece(sid, {"index_in_scan": i, "n_no_lote": i + 1, "shape": analyse(pts, MMPP), "contour": pts,
                                 "bbox": [int(x0), int(y0), int(x1 - x0), int(y1 - y0)], "crop_path": rel})
        pr.place(pid, cell, theta_deg=-PSI[name] + rot)
        ids[name] = pid
    pr.save()
    return pr, ids


def _log_lines(pr):
    with open(pr.log_path, encoding="utf-8") as f:
        return f.read()


def test_right_poses_no_suspects(tmp_path):
    pr, ids = _row_project(tmp_path)
    log0 = _log_lines(pr)
    r = C.evaluate(pr)
    assert r["items"] == []
    assert r["summary"] == dict(n_colocadas=3, n_verificadas=3, n_sem_cantos=0, n_com_vizinhas=3, n_impossivel=0,
                                n_melhor_rotacao=0, n_explicadas=0)
    assert _log_lines(pr) == log0


def test_neighbour_turned_90_is_impossible_and_minus_90_fixes_it(tmp_path):
    pr, ids = _row_project(tmp_path, rot_b=90.0)
    log0 = _log_lines(pr)
    pl = {}
    r = C.evaluate(pr, pl)
    assert set(pl) == set(ids.values())                 # registered on the fly and kept in the given dict
    assert [it["piece"] for it in r["items"]] == [ids["B"]]
    it = r["items"][0]
    assert it["grau"] == "impossivel" and it["cell"] == [2, 4] and it["n_vizinhas"] == 1
    assert it["rot_alt_deg"] == -90 and it["k_alt"] == (it["k0"] - 1) % 4
    assert it["falhas"] == [f"W B↔B com {ids['A']}"]
    assert it["n_falhas0"] == 1 and it["n_falhas_alt"] == 0 and it["custo_alt"] < it["custo0"]
    assert it["texto"] == "−90° fica sem falhas (1 → 0)"
    assert r["summary"]["n_impossivel"] == 1 and r["summary"]["n_melhor_rotacao"] == 0
    assert r["summary"]["n_explicadas"] == 1           # A: its B↔B is B's fault
    # the same through suspects / summary / suspects_near, and only these pieces when asked
    assert [x["piece"] for x in C.suspects(pr)] == [ids["B"]]
    assert C.summary(pr)["n_impossivel"] == 1
    assert [x["piece"] for x in C.suspects_near(pr, [(2, 4)])] == [ids["B"]]
    assert C.suspects(pr, pieces=[ids["C"]]) == []
    lines = C.suspects_lines(pr, [(2, 4)])
    assert lines[0].startswith("Suspeitas novas: 1") and "B<->B" in lines[1] and "-90°" in lines[1]
    assert _log_lines(pr) == log0                       # read-only


def test_turned_180_is_impossible_with_180_fix(tmp_path):
    pr, ids = _row_project(tmp_path, rot_b=180.0)
    it = C.suspects(pr)
    assert [x["piece"] for x in it] == [ids["B"]]
    assert it[0]["grau"] == "impossivel" and it[0]["rot_alt_deg"] == 180


def test_rot_text():
    assert [C.rot_text(d) for d in (90, -90, 180, 0)] == ["+90°", "−90°", "180°", "0°"]


def _res(n, fails, cost, f_ok=True, n_kind=0):
    return dict(f_ok=f_ok, fails=[{}] * fails, n_fail=fails, n_kind=n_kind, cost=cost, n=n)


def test_grade_rules():
    bad = _res(2, 0, 9.0, f_ok=False)
    # one failing side less: better rotation (P0833-like: 1 -> 0)
    assert C._grade({0: _res(2, 1, 4.2), 1: _res(2, 0, 2.9), 2: _res(2, 2, 6.0), 3: bad}, 0) == ("melhor_rotacao", 1)
    # cost only: needs >= BETTER_COST_MIN_SIDES neighbours, ratio and absolute gain
    assert C._grade({0: _res(1, 0, 2.2), 1: _res(1, 0, 1.3), 2: bad, 3: bad}, 0) == (None, 1)
    assert C._grade({0: _res(2, 0, 3.0), 1: _res(2, 0, 1.5), 2: bad, 3: bad}, 0) == ("melhor_rotacao", 1)
    assert C._grade({0: _res(2, 0, 3.0), 1: _res(2, 0, 2.0), 2: bad, 3: bad}, 0) == (None, 1)       # ratio 0.67
    assert C._grade({0: _res(2, 0, 1.0), 1: _res(2, 0, 0.55), 2: bad, 3: bad}, 0) == (None, 1)      # gain 0.45 mm
    # T-T / B-B now, or F sides off the border while another assignment has them right: impossible
    assert C._grade({0: _res(2, 1, 6.0, n_kind=1), 1: bad, 2: bad, 3: bad}, 0) == ("impossivel", None)
    assert C._grade({0: _res(1, 0, 1.0, f_ok=False), 1: _res(1, 0, 1.2), 2: bad, 3: bad}, 0) == ("impossivel", 1)
    # no assignment has the F sides right (an F-count / shape problem, not orientation): not reported
    assert C._grade({k: _res(1, 0, 1.0, f_ok=False) for k in range(4)}, 0) == (None, None)
