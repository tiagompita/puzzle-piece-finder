"""``/api/holes`` (M11, molde do buraco): ranking of the holes, one hole with its drawing, confirm / reject writes
(``hole_confirmed`` / ``hole_rejected`` with rank, custo, margem, confianca, m, fit_version), cache invalidation.

Synthetic project of :func:`test_consistency._row_project` (C (2,2), A (2,3), B (2,4) placed, kinds BTBB / TBTB / BBBT):
A is unplaced, so (2,3) is a hole with two mounted neighbours and A is the only loose piece. The synthetic crops
have a flat colour, so the image strips are finite and the E5 cost is defined.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from src import server as S  # noqa: E402
from src.state import Project, replay  # noqa: E402
from test_consistency import _row_project  # noqa: E402


@pytest.fixture
def env(tmp_path):
	pr, ids = _row_project(tmp_path)
	pr.unplace(ids["A"])
	pr.save()
	gui = S.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "uploads"), log=None)
	return gui, TestClient(S.create_app(gui)), pr, ids


def _ok_on_disk(path):
	pr = Project.open(path)
	assert pr.check_invariants(disk=True) == []
	rb, _ = replay(pr.log_path, pr.profile)
	assert rb == pr.board
	return pr


def _events(pr, action):
	with open(pr.log_path, encoding="utf-8") as f:
		return [e for e in map(json.loads, f) if e["action"] == action]


def test_holes_list_and_one_hole(env):
	gui, client, pr, ids = env
	first = client.get("/api/holes").json()
	assert "a_calcular" in first                         # the first answer may still be computing
	d = gui.holes_json(wait=True)
	assert d["a_calcular"] is False and "erro" not in d["resumo"], d["resumo"]
	assert d["resumo"]["n_buracos"] >= 1 and d["resumo"]["n_soltas"] == 1 and d["resumo"]["sigma"] in (1, -1)
	h = next(x for x in d["buracos"] if x["cell"] == [2, 3])
	assert h["m"] == 2 and {v["dir"] for v in h["vizinhas"]} == {"E", "W"}
	assert h["candidatas"] and h["candidatas"][0]["piece"] == ids["A"] and h["candidatas"][0]["rank"] == 1
	assert h["confianca"] == "sem"                       # a single finite candidate has no margin: never proposed
	assert h["atribuida"] == ids["A"]
	# the list is also served and cached
	again = client.get("/api/holes").json()
	assert again["versao"] == d["versao"] and again["a_calcular"] is False
	# one hole with its drawing (neighbours + candidate contour on the cell)
	r = client.get("/api/holes/2/3")
	assert r.status_code == 200, r.text
	one = r.json()
	assert one["buraco"] is True and one["cell"] == [2, 3] and one["parcial"] is False
	dr = one["desenho"]
	assert dr["vizinhas"]["E"]["piece"] == ids["B"] and dr["vizinhas"]["W"]["piece"] == ids["C"] and dr["vizinhas"]["N"] is None
	cand = dr["candidatas"][0]
	assert cand["piece"] == ids["A"] and len(cand["contorno"]) > 50 and "translate(" in cand["svg"]["transform"]
	assert abs(cand["svg"]["translate"][0] - 2.5) < 1e-6                 # column 3 -> x = 2.5 cell widths
	# a cell that is not a hole, and one outside the grid
	assert client.get("/api/holes/1/1").json()["buraco"] is False
	assert client.get("/api/holes/9/9").status_code == 404


def test_confirm_and_reject_write_the_events(env):
	gui, client, pr, ids = env
	a = ids["A"]
	gui.holes_json(wait=True)
	seq0 = gui.seq
	# reject: informative event with the meta, the piece stays loose, the pair is excluded from the ranking
	r = client.post("/api/holes/2/3/rejeitar", json={"piece": a, "nota": "não entra"})
	assert r.status_code == 200, r.text
	body = r.json()
	assert body["ok"] and body["meta"]["rank"] == 1 and body["meta"]["m"] == 2 and body["meta"]["confianca"] == "sem"
	p1 = _ok_on_disk(pr.path)
	ev = _events(p1, "hole_rejected")[-1]
	assert ev["piece"] == a and ev["cell"] == [2, 3] and ev["origin"] == "buraco" and ev["rank"] == 1 and ev["nota"] == "não entra"
	assert ev["fit_version"] and ev["confianca"] == "sem" and ev["m"] == 2 and p1.piece(a).estado == "solta"
	names = [e[1] for e in gui.events_after(seq0)]
	assert "board_changed" in names
	d = gui.holes_json(wait=True)
	h = next(x for x in d["buracos"] if x["cell"] == [2, 3])
	assert all(c["piece"] != a for c in h["candidatas"])          # excluded after the rejection
	# refusing an unknown piece / a non-hole
	assert client.post("/api/holes/2/3/confirmar", json={"piece": "P9999"}).status_code == 400
	assert client.post("/api/holes/1/1/confirmar", json={"piece": a}).status_code == 400
	# confirm: hole_confirmed (+ meta) then placed with origin buraco; the hole disappears from the list
	r = client.post("/api/holes/2/3/confirmar", json={"piece": a})
	assert r.status_code == 200, r.text
	p2 = _ok_on_disk(pr.path)
	assert p2.piece(a).estado == "colocada" and tuple(p2.piece(a).celula) == (2, 3)
	hc = _events(p2, "hole_confirmed")[-1]
	pl = _events(p2, "placed")[-1]
	assert hc["piece"] == a and hc["origin"] == "buraco" and hc["m"] == 2 and "fit_version" in hc and hc.get("nota")
	assert pl["piece"] == a and pl["origin"] == "buraco"
	d = gui.holes_json(wait=True)
	assert "sem peças soltas" in str(d["resumo"].get("erro", "")) or all(x["cell"] != [2, 3] for x in d["buracos"])


def test_busy_blocks_hole_writes(env):
	gui, client, pr, ids = env
	gui.job = "importar x"
	r = client.post("/api/holes/2/3/confirmar", json={"piece": ids["A"]})
	assert r.status_code == 409
	gui.job = None
