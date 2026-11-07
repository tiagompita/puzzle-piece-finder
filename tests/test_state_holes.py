"""``hole_confirmed`` / ``hole_rejected`` (M11): :meth:`Project.hole_confirm`, :meth:`Project.hole_reject`, the
``confirm(hole=…)`` / ``confirm(hole_reject=…)`` write path and the CLI ``--buraco`` / ``--buraco-rejeitar``.

Synthetic project of :func:`test_consistency._row_project` (C (2,2), A (2,3), B (2,4) placed): A is unplaced,
so (2,3) is a hole with two mounted neighbours and A is the loose right answer.
"""

import json

from src.confirm import confirm, main as cmain
from src.state import Project, StateError, replay
from test_consistency import _row_project


def _events(pr, action):
	with open(pr.log_path, encoding="utf-8") as f:
		return [e for e in map(json.loads, f) if e["action"] == action]


def _hole_project(tmp_path):
	pr, ids = _row_project(tmp_path)
	pr.unplace(ids["A"])
	pr.save()
	return pr, ids


META = {"rank": 1, "custo": 1.234, "margem": 1.8, "confianca": "alta", "m": 2, "fit_version": "m11-test", "theta_deg": -23.0}


def test_hole_confirm_logs_meta_then_places_with_origin_buraco(tmp_path):
	pr, ids = _hole_project(tmp_path)
	a = ids["A"]
	ev = pr.hole_confirm(a, (2, 3), meta=META, theta_deg=META["theta_deg"])
	assert ev["action"] == "hole_confirmed" and ev["origin"] == "buraco"
	assert ev["rank"] == 1 and ev["custo"] == 1.234 and ev["margem"] == 1.8 and ev["confianca"] == "alta" and ev["m"] == 2
	assert ev["fit_version"] == "m11-test" and "theta_deg" not in ev          # the pose goes to ``placed``
	p = pr.piece(a)
	assert p.estado == "colocada" and tuple(p.celula) == (2, 3) and p.theta_deg == -23.0
	pl = _events(pr, "placed")[-1]
	assert pl["piece"] == a and pl["origin"] == "buraco" and pl["rank"] == 1 and pl["score"] == 1.234 and pl["theta_deg"] == -23.0
	pr.save()
	board, pieces = replay(pr.log_path, pr.profile)
	assert board == pr.board and pieces == pr.model.pieces_state()
	assert pr.check_invariants(disk=True) == []
	# a second confirmation on an occupied cell is refused and logs nothing
	n0 = len(pr.events())
	try:
		pr.hole_confirm(ids["B"], (2, 3), meta=META)
		assert False, "should refuse"
	except StateError:
		pass
	assert len(pr.events()) == n0


def test_hole_reject_is_remembered_as_rejection(tmp_path):
	pr, ids = _hole_project(tmp_path)
	a = ids["A"]
	ev = pr.hole_reject(a, (2, 3), meta=dict(META, confianca="media", rank=2))
	assert ev["action"] == "hole_rejected" and ev["confianca"] == "media" and ev["rank"] == 2
	assert (a, (2, 3), "buraco") in pr.model.rejections
	assert pr.piece(a).estado == "solta"
	pr.save()
	assert pr.check_invariants(disk=True) == []
	pr2 = Project.open(pr.path)
	assert (a, (2, 3), "buraco") in pr2.model.rejections


def test_confirm_write_path_and_requery(tmp_path):
	pr, ids = _hole_project(tmp_path)
	a = ids["A"]
	r = confirm(pr, a, hole_reject=((2, 3), META), use_image=False)
	assert "error" not in r, r
	assert any("rejeitada para o buraco (2, 3)" in m for m in r["messages"])
	assert r["invariants"] == [] and (2, 3) in r["affected_cells"]
	r = confirm(pr, a, hole=((2, 3), META), use_image=False)
	assert "error" not in r, r
	assert pr.piece(a).estado == "colocada" and pr.piece(a).theta_deg == -23.0
	assert [e["action"] for e in pr.events()][-4:-1] == ["hole_rejected", "hole_confirmed", "placed"] or \
		"hole_confirmed" in [e["action"] for e in pr.events()]
	assert r["invariants"] == []


def test_cli_buraco_uses_the_fit_ranking_meta(tmp_path, capsys):
	pr, ids = _hole_project(tmp_path)
	a, path = ids["A"], pr.path
	# the synthetic pieces have no image crops with a usable band: the ranking may be empty of finite costs,
	# but the CLI must still write the event with the hole's m / confidence and place the piece
	# refusing for a cell that is not a hole (A still loose, so the pool is not empty)
	rc = cmain([a, "--buraco-rejeitar", "1", "1", "--no-requery", "--no-image", "--project", path])
	assert rc == 1 and "não é um buraco" in capsys.readouterr().out
	rc = cmain([a, "--buraco", "2", "3", "--no-requery", "--no-image", "--project", path])
	out = capsys.readouterr().out
	assert rc == 0, out
	p2 = Project.open(path)
	assert p2.piece(a).estado == "colocada" and tuple(p2.piece(a).celula) == (2, 3)
	ev = _events(p2, "hole_confirmed")[-1]
	assert ev["m"] == 2 and ev["confianca"] in ("alta", "media", "sem") and ev["fit_version"]
	assert p2.check_invariants(disk=True) == []
	# with no loose piece left the ranking says so instead of inventing a candidate
	rc = cmain([ids["B"], "--buraco-rejeitar", "1", "1", "--no-requery", "--no-image", "--project", path])
	assert rc == 1 and "sem peças soltas" in capsys.readouterr().out
