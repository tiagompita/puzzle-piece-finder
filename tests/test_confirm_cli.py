"""``python -m src.confirm --unplace`` and ``--cell L C --theta DEG`` (correction of a wrong orientation).

Synthetic project of :func:`test_query._project` (real :class:`src.state.Project` in ``tmp_path``): the
placed piece Q at (2, 3) with ``theta_deg`` -23, its loose twin T, a decoy D.
"""

import json

from src.confirm import main as cmain
from src.state import Project, replay
from test_query import _project


def _events(pr, action):
    with open(pr.log_path, encoding="utf-8") as f:
        return [e for e in map(json.loads, f) if e["action"] == action]


def test_unplace_then_place_with_theta(tmp_path, capsys):
    pr, q, t, d = _project(tmp_path)
    path = pr.path
    assert Project.open(path).piece(q).theta_deg == -23.0
    assert cmain([q, "--unplace", "--no-requery", "--project", path]) == 0
    p1 = Project.open(path)
    assert p1.piece(q).estado == "solta" and p1.piece(q).celula is None and p1.piece(q).theta_deg is None
    assert p1.board[(2, 3)]["estado"] == "vazia"
    assert cmain([q, "--cell", "2", "3", "--theta", "67.0", "--origin", "gt", "--no-requery", "--project", path]) == 0
    p2 = Project.open(path)
    assert p2.piece(q).estado == "colocada" and tuple(p2.piece(q).celula) == (2, 3)
    assert p2.piece(q).theta_deg == 67.0
    ev = _events(p2, "placed")[-1]
    assert ev["origin"] == "gt" and ev["theta_deg"] == 67.0 and ev["piece"] == q
    board, pieces = replay(p2.log_path, p2.profile)
    assert board == p2.board and pieces == p2.model.pieces_state()
    assert p2.check_invariants(disk=True) == []
    # the confirmation CLI also runs the orientation check of the changed area (informative line)
    assert "Suspeitas novas" in capsys.readouterr().out


def test_unplace_and_theta_refusals(tmp_path):
    from src.query import run_query
    pr, q, t, d = _project(tmp_path)
    path = pr.path
    n0 = len(_events(pr, "placed"))
    assert cmain([t, "--unplace", "--no-requery", "--project", path]) == 1          # T is loose
    assert cmain([q, "--theta", "10", "--unplace", "--no-requery", "--project", path]) == 1   # --theta only with --cell
    run_query(pr, use_image=False)
    js = json.load(open(pr.p("fetch.json"), encoding="utf-8"))
    te = next(x for x in js["entries"] if x["origin"] == "gemeo" and x["cell"] == [3, 4])
    assert te["piece"] == t and te.get("pose_known") and te.get("theta_deg") is not None
    # the list has a measured pose for T in (3, 4): --theta is refused, nothing is logged
    assert cmain([t, "--cell", "3", "4", "--theta", "10", "--no-requery", "--project", path]) == 1
    p1 = Project.open(path)
    assert len(_events(p1, "placed")) == n0 and p1.piece(t).estado == "solta"
    # without --theta the list pose is used
    assert cmain([t, "--cell", "3", "4", "--no-requery", "--project", path]) == 0
    assert abs(Project.open(path).piece(t).theta_deg - float(te["theta_deg"])) < 1e-9


def test_pose_and_pose_repor(tmp_path, capsys):
    from src import render as R
    pr, q, t, d = _project(tmp_path)
    path = pr.path
    th = R.register_piece(pr, q, art=None, image=False)["theta_deg"]
    assert cmain([q, "--pose", f"{th + 4.0}", "0.4", "-0.2", "--nota", "à mão", "--no-requery", "--project", path]) == 0
    out = capsys.readouterr().out
    assert "pose manual" in out and "Suspeitas novas" in out
    p1 = Project.open(path)
    pm = p1.piece(q).pose_manual
    assert abs(pm["theta_deg"] - (th + 4.0)) < 1e-9 and (pm["dx_mm"], pm["dy_mm"]) == (0.4, -0.2) and pm["nota"] == "à mão"
    ev = _events(p1, "pose_set")[-1]
    assert ev["antes"]["manual"] is False and abs(ev["antes"]["theta_deg"] - th) < 1e-9
    assert R.register_piece(p1, q, art=None, image=False)["method"] == "manual"
    assert p1.check_invariants(disk=True) == []
    # refusals: out of limits, a loose piece, nothing to reset on it
    assert cmain([q, "--pose", "0", "30", "0", "--no-requery", "--project", path]) == 1
    assert cmain([t, "--pose", "0", "0", "0", "--no-requery", "--project", path]) == 1
    assert cmain([t, "--pose-repor", "--no-requery", "--project", path]) == 1
    # reset, with the incremental re-query
    assert cmain([q, "--pose-repor", "--no-image", "--project", path]) == 0
    p2 = Project.open(path)
    assert p2.piece(q).pose_manual is None and _events(p2, "pose_cleared")[-1]["antes"]["dx_mm"] == 0.4
    assert "reconsulta" in capsys.readouterr().out
    assert p2.check_invariants(disk=True) == []
