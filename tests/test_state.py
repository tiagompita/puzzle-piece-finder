"""Tests for :mod:`src.state` (M12 minimum) and the CLIs ingest / photo / query / confirm.

Fast, synthetic: a 6 x 4 rot180 profile written to ``tmp_path``; ``src.twin`` and
``src.locate`` are replaced by stubs in ``sys.modules`` (the real modules belong to another
milestone), so ``run_query`` / ``confirm`` are tested for orchestration only.
"""

import json
import os
import sys
import types
from dataclasses import dataclass

import numpy as np
import pytest
from PIL import Image

from src.profile import PuzzleProfile
from src.shape import analyse
from src.state import Board, Photo, Project, StateError, replay

MMPP = 25.4 / 300


# ---------------------------------------------------------------- fixtures / helpers
def _profile_path(tmp_path, cols=6, rows=4):
    pp = tmp_path / "puzzle.json"
    PuzzleProfile(id="t", grid={"cols": cols, "rows": rows}, symmetry={"type": "rot180"}).save(str(pp))
    return str(pp)


@pytest.fixture
def proj(tmp_path):
    return Project.create(str(tmp_path / "proj"), _profile_path(tmp_path))


_RECT = analyse(np.array([[0, 0], [220, 0], [220, 210], [0, 210]]) , MMPP)


def _add(pr, n, lote=1, n_flat=None, cls=None):
    sid = pr.add_scan(None, dpi=300, lote=lote)
    ids = []
    for i in range(n):
        d = {"index_in_scan": i, "n_no_lote": i + 1, "shape": _RECT}
        if n_flat is not None:
            d.update(n_flat=n_flat, cls=cls)
        ids.append(pr.add_piece(sid, d))
    return ids


def _ok(pr):
    assert pr.check_invariants() == []


def _photo(pr, full=(), empty_all=True):
    m = [[0 if empty_all else -1] * pr.profile.cols for _ in range(pr.profile.rows)]
    for l, c in full:
        m[l - 1][c - 1] = 1
    return Photo(id=None, file="foto.jpg", map=m)


# ---------------------------------------------------------------- model
def test_round_trip_and_replay(proj):
    pr = proj
    a, b, c, d, e = _add(pr, 5)
    _ok(pr)
    pr.place(a, (1, 1), origin="manual", theta_deg=90.0)
    _ok(pr)
    pr.set_position_known(b, (2, 2), origin="gt")
    _ok(pr)
    t = pr.register_pair(c, d, d1=0.3, margin=2.0, image={"dE": 10.0}, cells=[{"cell": [1, 3], "score": 1, "rank": 1}])
    _ok(pr)
    g = pr.register_section(None, "blocos", {e: (0, 0)}, candidates=[{"cell0": [4, 6], "rot": 0}])
    _ok(pr)
    pr.anchor_section(g, 4, 6, rot=0)
    _ok(pr)
    w = pr.register_photo(_photo(pr, full=[(1, 1), (3, 3), (4, 6)]))
    assert w == []
    _ok(pr)
    pr.reject_pair(t)
    _ok(pr)
    pr.save()
    assert pr.check_invariants(disk=True) == []

    q = Project.open(pr.path)
    assert q.board == pr.board
    assert {k: v.to_dict() for k, v in q.pieces.items()} == {k: v.to_dict() for k, v in pr.pieces.items()}
    assert {k: v.to_dict() for k, v in q.pairs.items()} == {k: v.to_dict() for k, v in pr.pairs.items()}
    assert {k: v.to_dict() for k, v in q.sections.items()} == {k: v.to_dict() for k, v in pr.sections.items()}
    assert q.meta["next_ids"] == pr.meta["next_ids"]
    assert q.last_photo().map == pr.last_photo().map
    rb, rp = replay(q.log_path, q.profile)
    assert rb == q.board and rp == q.model.pieces_state()
    assert q.check_invariants(disk=True) == []
    # shapes come back from the npz
    sh = q.shape(a)
    assert sh is not None and sh.cls == _RECT.cls and np.allclose(sh.z, _RECT.z)
    # states
    assert q.piece(a).estado == "colocada" and q.piece(a).celula == (1, 1) and q.piece(a).theta_deg == 90.0
    assert q.piece(b).estado == "posicao_conhecida"
    assert q.piece(c).estado == "solta" and q.pairs[t].estado == "rejeitado"
    assert q.board[(4, 6)] == {"estado": "colocada", "peca_id": e, "fonte": "legado_scan", "foto_id": None}
    assert q.board[(3, 3)]["estado"] == "ocupada_legado"
    # ids are never reused
    f = _add(q, 1)[0]
    assert int(f[1:]) == 6


def test_place_errors_and_unplace(proj):
    a, b = _add(proj, 2)
    proj.place(a, (2, 3))
    with pytest.raises(StateError):
        proj.place(b, (2, 3))
    with pytest.raises(StateError):
        proj.place(a, (1, 1))          # already placed
    with pytest.raises(StateError):
        proj.place(b, (9, 9))          # outside the grid
    _ok(proj)
    # place over ocupada_legado upgrades it; unplace restores it
    proj.register_photo(_photo(proj, full=[(1, 1), (2, 3)]))
    proj.place(b, (1, 1))
    assert proj.board[(1, 1)]["estado"] == "colocada"
    proj.unplace(b)
    assert proj.board[(1, 1)]["estado"] == "ocupada_legado" and proj.piece(b).estado == "solta"
    _ok(proj)


def test_pending_twins(proj):
    a, b = _add(proj, 2)
    assert proj.pending_twins() == []
    proj.place(a, (1, 2))
    pt = proj.pending_twins()
    assert [(p.id, cell) for p, cell in pt] == [(a, (4, 5))]
    proj.place(b, (4, 5))
    assert proj.pending_twins() == []
    _ok(proj)


def test_register_photo_reconciles(proj):
    a, b = _add(proj, 2)
    proj.place(a, (2, 2))
    proj.set_position_known(b, (3, 4))
    assert proj.placeable_known_positions() == []
    # (1,1) full without log -> ocupada_legado; (2,2) placed but empty -> warning; (3,3) full -> b placeable
    w = proj.register_photo(_photo(proj, full=[(1, 1), (3, 3)]))
    assert proj.board[(1, 1)]["estado"] == "ocupada_legado" and proj.board[(1, 1)]["fonte"] == "foto"
    assert proj.board[(2, 2)]["estado"] == "colocada"
    assert len(w) == 1 and "(2,2)" in w[0]
    ev = [e for e in proj.events() if e["action"] == "position_placeable"]
    assert [(e["piece"], tuple(e["cell"])) for e in ev] == [(b, (3, 4))]
    assert [(p.id, c) for p, c in proj.placeable_known_positions()] == [(b, (3, 4))]
    # second photo: (1,1) empty -> cleared back to vazia
    proj.register_photo(_photo(proj, full=[(3, 3)]))
    assert proj.board[(1, 1)]["estado"] == "vazia"
    assert len([e for e in proj.events() if e["action"] == "position_placeable"]) == 1  # no repeat
    _ok(proj)


def test_anchor_and_unanchor_section(proj):
    a, b, c, x = _add(proj, 4)
    proj.place(x, (2, 3))
    g = proj.register_section(None, "montado", {a: (0, 0), b: (0, 1), c: (1, 0)})
    assert {proj.piece(i).estado for i in (a, b, c)} == {"em_seccao"}
    # rot 90 clockwise: (0,1) -> (1,0), (1,0) -> (0,-1)
    ev = proj.anchor_section(g, 1, 3, rot=90, fonte="manual", confianca=0.9)
    assert proj.piece(a).celula == (1, 3) and proj.piece(c).celula == (1, 2)
    assert [cf["piece"] for cf in ev["conflicts"]] == [b]            # (2,3) already holds x
    assert proj.piece(b).estado == "em_seccao"
    assert proj.board[(1, 3)]["fonte"] == "legado_scan"
    _ok(proj)
    proj.unanchor_section(g)
    assert {proj.piece(i).estado for i in (a, b, c)} == {"em_seccao"}
    assert proj.board[(1, 3)]["estado"] == "vazia" and proj.board[(2, 3)]["peca_id"] == x
    assert not proj.sections[g].anchor["anchored"]
    _ok(proj)


def test_missing_border_cells_and_holes(proj):
    pr = proj
    border = pr.missing_border_cells()
    assert len(border) == 6 * 4 - 4 * 2          # 16 border cells on a 6x4 grid
    assert (2, 2) not in border
    pr.register_photo(_photo(pr, full=[lc for lc in border if lc != (1, 4)] + [(2, 2)]))
    assert pr.missing_border_cells() == [(1, 4)]
    assert (2, 3) in pr.holes() and (1, 4) in pr.holes()
    _ok(pr)


def test_stats_p_twin_placed(proj):
    a, b, c = _add(proj, 3)
    proj.place(a, (1, 1))
    proj.place(b, (2, 2))
    proj.place(c, (4, 6))                       # twin of (1,1): not pending
    st = proj.stats()
    assert st["gemeas_pendentes"] == 1 and st["n_por_colocar"] == 24 - 3
    assert st["p_twin_placed"] == pytest.approx(1 / 21)
    assert "1 / 21" in st["p_twin_placed_formula"]
    assert st["por_estado"]["colocada"] == 3


def test_board_dict_round_trip(tmp_path):
    p = PuzzleProfile.load(_profile_path(tmp_path))
    b = Board.empty(p)
    b.set((1, 2), {"estado": "colocada", "peca_id": "P0001", "fonte": "log"})
    assert Board.from_dict(json.loads(json.dumps(b.to_dict()))) == b
    assert b != Board.empty(p)


# ---------------------------------------------------------------- query / confirm with stubs
@dataclass
class _Item:
    id: str
    shape: object
    rgba: object
    theta_deg: object
    cell: object


class _Stub:
    """find_twin: twins given by ``twin_of`` (symmetric); everything else 'sem'."""

    def __init__(self, twin_of):
        self.twin_of = dict(twin_of)
        self.twin_of.update({v: k for k, v in twin_of.items()})
        self.calls = []
        self.pair_calls = 0

    def find_twin(self, query, candidates, *, profile, modality="silhueta_silhueta", art=None, topk=3):
        self.calls.append(query.id)
        want = self.twin_of.get(query.id)
        ids = [c.id for c in candidates]
        if want in ids:
            return {"candidates": [{"id": want, "d1_mm": 0.3, "phi_deg": 180.0, "chord_ok": True,
                                    "image": {"dE": 12.5, "ncc": 0.4, "pctl": 0.2}, "twin_cell": None}],
                    "decision": "aceite", "margin": 2.1, "twin_cell": None, "reasons": ["stub"]}
        return {"candidates": [], "decision": "sem", "margin": None, "twin_cell": None, "reasons": ["stub sem"]}

    def pair_locate(self, a, b, profile, art, *, topk=3):
        self.pair_calls += 1
        return {"cells": [{"cell": (1, 3), "score": 0.5, "rank": 1}], "n_cells_tested": 24}


@pytest.fixture
def stub(monkeypatch):
    s = _Stub({})
    twin = types.ModuleType("src.twin")
    twin.TwinItem, twin.find_twin = _Item, s.find_twin
    twin.same_shape = lambda a, b: False
    loc = types.ModuleType("src.locate")

    class CellArt:
        @classmethod
        def load(cls, profile, repo_root):
            return cls()

    loc.CellArt, loc.pair_locate = CellArt, s.pair_locate
    loc.piece_mean_lab = lambda rgba: [50.0, 0.0, 0.0]
    monkeypatch.setitem(sys.modules, "src.twin", twin)
    monkeypatch.setitem(sys.modules, "src.locate", loc)
    return s


def test_run_query_with_stubs(proj, stub):
    from src.query import run_query
    pr = proj
    placed, t1, l1, l2, l3 = _add(pr, 5)
    pr.place(placed, (1, 2))                     # pending twin cell (4, 5)
    stub.twin_of.update({placed: t1, t1: placed, l1: l2, l2: l1})
    entries = run_query(pr)
    got = {(e["origin"], e["piece"]) for e in entries}
    assert ("gemeo", t1) in got
    assert ("par", l1) in got and ("par", l2) in got
    tw = [e for e in entries if e["origin"] == "gemeo"][0]
    assert tw["cell"] == [4, 5] and tw["decision"] == "aceite" and tw["query"] == placed
    assert [e["ordem"] for e in entries] == list(range(1, len(entries) + 1))
    assert entries[0]["origin"] == "gemeo"
    assert len(pr.pairs) == 1 and stub.pair_calls == 1
    assert {pr.piece(l1).estado, pr.piece(l2).estado} == {"emparelhada"}
    md = open(pr.p("fetch.md"), encoding="utf-8").read()
    assert "| ordem | lote | nº no lote | id | célula | origem | decisão | margem | ΔE | razões |" in md
    assert f"| {t1} | (4,5) | gemeo | aceite | 2.10 | 12.5 |" in md
    assert "p_twin_placed" in md
    assert os.path.exists(pr.p("fetch_1.jpg"))
    assert any(e["action"] == "fetch_listed" for e in pr.events())
    _ok(pr)
    # a second full run does not register the pair again
    run_query(pr)
    assert len(pr.pairs) == 1


def test_confirm_requeries_only_affected(proj, stub):
    from src.confirm import confirm
    from src.query import run_query
    pr = proj
    p1, p2, t1, t2, x, y = _add(pr, 6)
    pr.place(p1, (1, 2))
    pr.place(p2, (2, 2))
    stub.twin_of.update({p1: t1, t1: p1})
    run_query(pr)
    n_full = len(stub.calls)
    assert n_full >= 2 + 3                        # 2 pending twins + loose<->loose queries
    # place a loose piece: only its new pending twin is re-queried (1 call)
    stub.calls.clear()
    stub.twin_of.update({x: t2, t2: x})
    r = confirm(pr, x, cell=(3, 3), origin="manual")
    assert "error" not in r and r["invariants"] == []
    assert stub.calls == [x]
    got = {(e["origin"], e["piece"], tuple(e["cell"])) for e in r["entries"] if e.get("cell")}
    assert ("gemeo", t2, (2, 4)) in got           # new proposal
    assert ("gemeo", t1, (4, 5)) in got           # kept from the previous list
    # confirming the proposal: t1 placed with origin from the list, logged as twin_confirmed
    stub.calls.clear()
    r = confirm(pr, t1, cell=(4, 5))
    assert "error" not in r
    assert any(e["action"] == "twin_confirmed" and e["piece"] == t1 for e in pr.events())
    assert stub.calls == []                       # (4,5)'s twin (1,2) is occupied: nothing to query
    # reject the remaining proposal
    r = confirm(pr, t2, reject=True)
    assert "error" not in r
    assert (t2, (2, 4), "gemeo") in pr.model.rejections
    assert not any(e["piece"] == t2 for e in r["entries"])
    _ok(pr)


def test_confirm_pair_gives_partner_position(proj, stub):
    from src.confirm import confirm
    from src.query import run_query
    pr = proj
    a, b, n1 = _add(pr, 3)
    stub.twin_of.update({a: b, b: a})
    run_query(pr)
    assert len(pr.pairs) == 1
    r = confirm(pr, a, cell=(1, 1))
    assert "error" not in r
    assert pr.piece(b).estado == "posicao_conhecida" and pr.piece(b).celula == (4, 6)
    assert list(pr.pairs.values())[0].estado == "confirmado"
    assert not any(e["piece"] == b for e in r["entries"])     # (4,6) has no occupied neighbour yet
    r = confirm(pr, n1, cell=(3, 6))
    assert any(e["origin"] == "posicao_conhecida" and e["piece"] == b and e["decision"] == "colocavel"
               for e in r["entries"])
    assert any(e["action"] == "position_placeable" and e["piece"] == b for e in pr.events())
    _ok(pr)


# ---------------------------------------------------------------- ingest / photo CLI
def test_grid_order():
    from src.ingest import grid_order
    #            row 2 left        row 1 right       row 1 left       row 2 right
    bb = [(10, 300, 100, 100), (400, 20, 100, 100), (50, 0, 100, 100), (300, 320, 100, 100)]
    assert grid_order(bb) == [3, 2, 1, 4]
    assert grid_order([]) == []


def test_ingest_synthetic(tmp_path):
    from src.ingest import main
    bg = np.full((1000, 1400, 3), (40, 160, 60), np.uint8)
    rects = [(940, 310, 220, 210, (210, 170, 30)), (300, 320, 220, 210, (200, 40, 40)),
             (620, 330, 220, 210, (40, 60, 200))]
    for x, y, w, h, col in rects:
        bg[y:y + h, x:x + w] = col
    scan = tmp_path / "scan.png"
    Image.fromarray(bg).save(scan)
    proj = tmp_path / "proj"
    assert main([str(scan), "--lote", "7", "--project", str(proj), "--profile", _profile_path(tmp_path)]) == 0
    pr = Project.open(str(proj))
    ps = sorted(pr.pieces.values(), key=lambda p: p.n_no_lote)
    assert len(ps) == 3 and {p.estado for p in ps} == {"solta"}
    assert [p.n_no_lote for p in ps] == [1, 2, 3] and {p.lote for p in ps} == {7}
    assert [p.bbox[0] < 400 for p in ps] == [True, False, False]   # left to right
    for p in ps:
        assert os.path.exists(pr.p(p.crop_path))
        assert p.area_mm2 == pytest.approx(220 * 210 * MMPP ** 2, rel=0.05)
        assert not p.flags["objeto_duplo"] and pr.shape(p.id) is not None
        assert len(p.mean_lab) == 3
    assert os.path.exists(pr.p("overlays", "S0001.jpg"))
    assert pr.check_invariants(disk=True) == []
    # a second scan of the same bag continues the numbering
    assert main([str(scan), "--lote", "7", "--project", str(proj)]) == 0
    pr = Project.open(str(proj))
    assert sorted(p.n_no_lote for p in pr.pieces.values()) == [1, 2, 3, 4, 5, 6]


def test_photo_from_json_cli(tmp_path):
    from src.photo import main
    pp = _profile_path(tmp_path)
    cells = [[1] * 6 for _ in range(4)]
    cells[1][1] = 0
    js = tmp_path / "occ.json"
    js.write_text(json.dumps({"celulas": cells, "fontes": ["x.jpg"]}), encoding="utf-8")
    proj = str(tmp_path / "proj")
    assert main(["--from-json", str(js), "--fix", "1,1=0", "--project", proj, "--profile", pp]) == 0
    pr = Project.open(proj)
    assert pr.board[(1, 1)]["estado"] == "vazia" and pr.board[(2, 2)]["estado"] == "vazia"
    assert pr.board[(3, 3)]["estado"] == "ocupada_legado"
    assert pr.last_photo().value(1, 1) == 0


def test_ingest_known_cells(tmp_path):
    from src.ingest import main
    bg = np.full((1000, 1400, 3), (40, 160, 60), np.uint8)
    for x, y in ((300, 320), (620, 330)):
        bg[y:y + 210, x:x + 220] = (200, 40, 40)
    scan = tmp_path / "scan.png"
    Image.fromarray(bg).save(scan)
    proj, pp = str(tmp_path / "proj"), _profile_path(tmp_path)
    pr = Project.create(proj, pp)
    pr.register_photo(_photo(pr, full=[(1, 1)]))
    pr.save()
    gt = tmp_path / "gt.json"
    gt.write_text(json.dumps({"cells": [{"index": 1, "cell": [1, 1]}, {"index": 2, "cell": [2, 2]}],
                              "theta_deg": 0}), encoding="utf-8")
    assert main([str(scan), "--lote", "1", "--project", proj, "--known-cells", str(gt)]) == 0
    pr = Project.open(proj)
    by_n = {p.n_no_lote: p for p in pr.pieces.values()}
    assert by_n[1].estado == "colocada" and by_n[1].celula == (1, 1)      # full in the last photo
    assert by_n[2].estado == "posicao_conhecida" and by_n[2].celula == (2, 2)
    assert pr.check_invariants(disk=True) == []
