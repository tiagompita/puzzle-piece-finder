"""Cross-check of the "go fetch" proposals with the hole mould (:func:`src.query._cross_check`, R7_CRITERIOS §4.1).

Synthetic project (4 x 6, rot180): a placed piece P at (2, 3) whose loose twin T goes to (3, 4), a decoy D
of the same class, and a placed neighbour N at (3, 3) (class TTBB, so it never competes for T). N is placed
in the rotation that puts on its E side either the same kind as T's W side (T↔T or B↔B: impossible) or the
complementary kind; N's colour is T's (strip dE ~ 0) or a far colour (strip dE large -> joint cost above
T_abs). The real ``find_twin`` (shape only) proposes T at (3, 4) as ``aceite``; the cross-check must keep the
proposal and demote it when the neighbour does not fit. Plus: no mounted neighbour -> ``nao_testado``; the
pair entries skip stored cells whose cell or twin is occupied and put piece B in the twin cell.
"""

import json
import os

import cv2
import numpy as np
import pytest
from PIL import Image

import synth
from src.fit import board_dirs
from src.shape import analyse, transform_contour
from src.state import Project
from test_shape import MMPP

BG = (40, 160, 60)
COL_T = (40, 60, 200)
COL_FAR = (230, 220, 40)
PSI_P, PSI_T, PSI_D, PSI_N = 23.0, -61.0, 140.0, 35.0


def _cal(t_abs=2.6656):
    cal = {k: dict(v) if isinstance(v, dict) else v for k, v in synth.ALPES_CAL.items()}
    cal["buraco"] = {"erosion_mm": 0.0, "chord_cut": 2.0, "t_abs": t_abs, "f_rule": True}
    return cal


def _px(board_mm, psi, offset_px):
    return transform_contour(board_mm, psi, center=(0.0, 0.0)) / MMPP + np.asarray(offset_px, float)


def _side_kind(shape, theta, d):
    cd = board_dirs(shape, theta)
    assert cd is not None
    return shape.sides[cd[d]].kind


def _project(tmp_path, fit_kind=True, col_n=COL_T, place_n=True):
    """``fit_kind``: N's E side complementary to T's W side (else the same kind)."""
    prof = synth.profile(rows=4, cols=6, p90=None, cal=_cal())
    pp = tmp_path / "puzzle.json"
    prof.save(str(pp))
    pr = Project.create(str(tmp_path / "proj"), str(pp))
    board = synth.body_mm("TBTB", deltas=(0.8, -0.5, 0.4, 0.3))
    decoy = synth.body_mm("TBTB", deltas=(-0.9, 0.7, -0.6, -0.8))
    nb = synth.body_mm("TTBB", deltas=(0.2, -0.3, 0.1, 0.4))
    twin = synth.twin_board_contour(board, prof)
    pieces = [(_px(board, PSI_P, (400, 400)), (200, 40, 40)),
              (_px(twin, PSI_T, (1000, 400)), COL_T),
              (_px(decoy, PSI_D, (1600, 400)), (210, 170, 30)),
              (_px(nb, PSI_N, (2200, 400)), col_n)]
    img = np.full((800, 2600, 3), BG, np.uint8)
    for pts, col in pieces:
        cv2.fillPoly(img, [np.round(pts).astype(np.int32).reshape(-1, 1, 2)], col)
    scan = tmp_path / "scan.png"
    Image.fromarray(img).save(scan)
    sid = pr.add_scan(str(scan), dpi=300, lote=3)
    os.makedirs(pr.p("crops"), exist_ok=True)
    ids, shapes = [], []
    for i, (pts, _) in enumerate(pieces):
        x0, y0 = np.floor(pts.min(0)).astype(int) - 10
        x1, y1 = np.ceil(pts.max(0)).astype(int) + 10
        al = np.zeros(img.shape[:2], np.uint8)
        cv2.fillPoly(al, [np.round(pts).astype(np.int32).reshape(-1, 1, 2)], 255)
        rgba = np.dstack([img, al])[y0:y1, x0:x1]
        rel = f"crops/P{i + 1:04d}.png"
        Image.fromarray(np.ascontiguousarray(rgba)).save(pr.p(rel))
        sh = analyse(pts, MMPP)
        shapes.append(sh)
        ids.append(pr.add_piece(sid, {"index_in_scan": i, "n_no_lote": i + 1, "shape": sh, "contour": pts,
                                      "bbox": [int(x0), int(y0), int(x1 - x0), int(y1 - y0)], "crop_path": rel}))
    placed, tw, dec, n = ids
    pr.place(placed, (2, 3), theta_deg=-PSI_P)          # twin cell (3, 4)
    if place_n:
        want_w = _side_kind(shapes[1], -PSI_T, "W")     # T's W side in its predicted board pose
        theta_n = None
        for k in range(4):
            th = -PSI_N + 90.0 * k
            ke = _side_kind(shapes[3], th, "E")
            if (ke != want_w) == fit_kind and ke in "TB":
                theta_n = th
                break
        assert theta_n is not None
        pr.place(n, (3, 3), theta_deg=theta_n)           # W neighbour of (3, 4)
    pr.save()
    return pr, placed, tw, dec, n


def _twin_entry(entries, tw):
    return next(x for x in entries if x["origin"] == "gemeo" and x["piece"] == tw)


def test_incompatible_side_kind_demotes_aceite(tmp_path):
    from src.query import run_query
    pr, placed, tw, dec, n = _project(tmp_path, fit_kind=False)
    e = _twin_entry(run_query(pr, use_image=False), tw)
    assert e["cell"] == [3, 4] and e["query"] == placed
    assert e["decision"] == "ambigua" and e["decision_antes_encaixe"] == "aceite", e["reasons"]
    enc = e["encaixe"]
    assert enc["estado"] == "incompativel" and enc["pose"] == "prevista" and enc["m"] == 1
    assert enc["J"] is None and enc["fit_version"]
    (lado,) = enc["lados"]
    assert lado["dir"] == "W" and lado["vizinha"] == n and lado["comp"] is False and lado["tipo"] == lado["tipo_vizinha"]
    assert any(r.startswith("encaixe incompatível") and f"{lado['tipo']}↔{lado['tipo']}" in r and "impossível" in r
               for r in e["reasons"]), e["reasons"]
    md = open(pr.p("fetch.md"), encoding="utf-8").read()
    assert "| razões | encaixe |" in md and "| incomp. lado |" in md
    js = json.load(open(pr.p("fetch.json"), encoding="utf-8"))
    je = _twin_entry(js["entries"], tw)
    assert je["encaixe"]["estado"] == "incompativel" and je["decision"] == "ambigua"


def test_compatible_neighbour_is_ok_and_keeps_aceite(tmp_path):
    from src.query import run_query
    pr, placed, tw, dec, n = _project(tmp_path, fit_kind=True)
    e = _twin_entry(run_query(pr, use_image=False), tw)
    enc = e["encaixe"]
    assert enc["estado"] == "ok", (enc, e["reasons"])
    assert e["decision"] == "aceite" and "decision_antes_encaixe" not in e
    assert enc["J"] is not None and enc["J"] <= enc["t_abs"] and enc["lados"][0]["comp"] is True
    assert enc["lados"][0]["dE"] is not None and enc["lados"][0]["dE"] < 5.0
    assert any(r.startswith("encaixe com 1 vizinha: custo") for r in e["reasons"]), e["reasons"]
    md = open(pr.p("fetch.md"), encoding="utf-8").read()
    assert "| ok " in md


def test_cost_above_t_abs_is_incompatible_and_incremental_recomputes(tmp_path):
    from src.query import run_query
    pr, placed, tw, dec, n = _project(tmp_path, fit_kind=True, col_n=COL_FAR)
    e = _twin_entry(run_query(pr, use_image=False), tw)
    enc = e["encaixe"]
    assert enc["estado"] == "incompativel" and enc["lados"][0]["comp"] is True
    assert enc["J"] is not None and enc["J"] > enc["t_abs"]
    assert e["decision"] == "ambigua" and e["decision_antes_encaixe"] == "aceite"
    assert any(r.startswith(f"encaixe incompatível com a vizinha (3,3) {n}: custo") and "> T_abs 2,67" in r
               and "ΔE da tira" in r for r in e["reasons"]), e["reasons"]
    # incremental re-query keeps the entry: the cross-check is redone once (no duplicated reason, same decision)
    again = run_query(pr, use_image=False, only_cells=[], only_pieces=[])
    e2 = _twin_entry(again, tw)
    assert e2["decision"] == "ambigua" and e2["decision_antes_encaixe"] == "aceite"
    assert sum(1 for r in e2["reasons"] if r.startswith("encaixe")) == 1


def test_no_mounted_neighbour_is_not_tested(tmp_path):
    from src.query import run_query
    pr, placed, tw, dec, n = _project(tmp_path, place_n=False)
    e = _twin_entry(run_query(pr, use_image=False), tw)
    assert e["encaixe"] == {"estado": "nao_testado", "motivo": "sem vizinha montada"}
    assert e["decision"] == "aceite" and not any(r.startswith("encaixe") for r in e["reasons"])
    md = open(pr.p("fetch.md"), encoding="utf-8").read()
    assert f"| {tw} | (3,4) |" in md and md.split(f"| {tw} | (3,4) |")[1].split("\n")[0].rstrip().endswith("| — |")


def test_unknown_pose_uses_best_of_four_rotations(tmp_path):
    from src.query import _Ctx, _cross_check
    pr, placed, tw, dec, n = _project(tmp_path, fit_kind=False)
    ctx = _Ctx(pr, use_image=False)
    # same piece and neighbour, pose unknown: some rotation of T puts a complementary side on W -> not impossible
    e = {"origin": "par", "piece": tw, "cell": [3, 4], "decision": "proposto", "reasons": ["par com X"], "theta_deg": None}
    enc = _cross_check(ctx, e)
    assert enc["pose"] == "min4" and enc["lados"][0]["comp"] is True
    assert enc["estado"] in ("ok", "incompativel") and e["decision"] == "proposto"
    assert any("melhor das 4 rotações" in r for r in e["reasons"]), e["reasons"]
    assert e["reasons"][0] == "par com X"


def test_pair_entries_skip_occupied_cells_and_put_b_in_the_twin_cell(tmp_path):
    from src.query import _pair_allowed, _pair_entries
    pr, placed, tw, dec, n = _project(tmp_path, place_n=False)
    # (2, 3) is occupied; (3, 4) has its twin (2, 3) occupied; (1, 2) and its twin (4, 5) are free
    tid = pr.register_pair(tw, dec, d1=0.3, margin=2.0, cells=[{"cell": [2, 3]}, {"cell": [3, 4]}, {"cell": [1, 2]}])
    t = pr.pairs[tid]
    es = {e["piece"]: e for e in _pair_entries(pr, t, None)}
    assert es[t.a]["cell"] == [1, 2] and es[t.b]["cell"] == [4, 5]
    assert any("excluídas: [[2, 3], [3, 4]]" in r for r in es[t.a]["reasons"]), es[t.a]["reasons"]
    al = _pair_allowed(pr)
    assert al.shape == (4, 6) and not al[1, 2] and not al[2, 3] and al[0, 1]
    # every stored cell busy -> no cell, and the reason says it
    t.cells = [{"cell": [2, 3]}]
    es = _pair_entries(pr, t, None)
    assert all(e["cell"] is None for e in es) and all("sem célula livre compatível" in e["reasons"] for e in es)
