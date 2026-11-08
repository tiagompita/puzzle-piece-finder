"""Sugestões ``alta`` em «Vai buscar» (M11_CRITERIOS §8): ``/api/fetch.buracos_alta`` (só a rank 1 de um buraco ``alta``
coerente com a afetação), o cartão fundido com a proposta de gémea (``gemea: true`` grava ``hole_confirmed`` **e**
``placed`` com origem ``gemeo`` / ``twin_rejected``), o contador com Wilson, a regra de pausa (3 em 20) e a
reativação (``holes_alta_resumed``).

Projeto sintético :func:`_alta_project`: a fila do :func:`test_consistency._row_project` (C (2,2), B (2,4) colocadas) com
A solta (a peça certa de (2,3)) e dois chamarizes TBTB com os encaixes deslocados: dois vizinhos, a certa em 1.º com
margem ≥ 1,5 → o buraco (2,3) é ``alta`` com m = 2.
"""

import json
import os
import sys

import cv2
import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

import synth  # noqa: E402
from src import fit as F  # noqa: E402
from src import server as S  # noqa: E402
from src.shape import analyse  # noqa: E402
from src.state import Project, replay  # noqa: E402
from test_consistency import PSI  # noqa: E402
from test_query import BG, _piece_px  # noqa: E402
from test_shape import MMPP  # noqa: E402

SPEC = [("C", "BTBB", (2, 2), (0, 0, 0, 0)), ("A", "TBTB", None, (0, 0, 0, 0)), ("B", "BBBT", (2, 4), (0, 0, 0, 0)),
		("D", "TBTB", None, (1.6, -1.4, 1.5, -1.6)), ("E", "TBTB", None, (-1.5, 1.5, -1.5, 1.5))]
PSI2 = dict(PSI, D=12.0, E=-77.0)


def _alta_project(tmp_path):
	prof = synth.profile(rows=4, cols=6, p90=None)
	pp = tmp_path / "puzzle.json"
	prof.save(str(pp))
	pr = Project.create(str(tmp_path / "proj"), str(pp))
	pts_all = [_piece_px(synth.body_mm(kinds, deltas=deltas), PSI2[name], (400 + 600 * i, 400)) for i, (name, kinds, _, deltas) in enumerate(SPEC)]
	img = np.full((800, 600 * len(SPEC) + 200, 3), BG, np.uint8)
	for pts in pts_all:
		cv2.fillPoly(img, [np.round(pts).astype(np.int32).reshape(-1, 1, 2)], (200, 40, 40))
	scan = tmp_path / "scan.png"
	Image.fromarray(img).save(scan)
	sid = pr.add_scan(str(scan), dpi=300, lote=1)
	os.makedirs(pr.p("crops"), exist_ok=True)
	ids = {}
	for i, ((name, kinds, cell, _), pts) in enumerate(zip(SPEC, pts_all)):
		x0, y0 = np.floor(pts.min(0)).astype(int) - 10
		x1, y1 = np.ceil(pts.max(0)).astype(int) + 10
		al = np.zeros(img.shape[:2], np.uint8)
		cv2.fillPoly(al, [np.round(pts).astype(np.int32).reshape(-1, 1, 2)], 255)
		rel = f"crops/P{i + 1:04d}.png"
		Image.fromarray(np.ascontiguousarray(np.dstack([img, al])[y0:y1, x0:x1])).save(pr.p(rel))
		pid = pr.add_piece(sid, {"index_in_scan": i, "n_no_lote": i + 1, "shape": analyse(pts, MMPP), "contour": pts,
								 "bbox": [int(x0), int(y0), int(x1 - x0), int(y1 - y0)], "crop_path": rel})
		if cell is not None:
			pr.place(pid, cell, theta_deg=-PSI2[name])
		ids[name] = pid
	pr.save()
	return pr, ids


@pytest.fixture
def env(tmp_path):
	pr, ids = _alta_project(tmp_path)
	gui = S.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "uploads"), log=None)
	return gui, TestClient(S.create_app(gui)), pr, ids


def _events(pr, action):
	with open(pr.log_path, encoding="utf-8") as f:
		return [e for e in map(json.loads, f) if e["action"] == action]


def _ok_on_disk(path):
	pr = Project.open(path)
	assert pr.check_invariants(disk=True) == []
	rb, _ = replay(pr.log_path, pr.profile)
	assert rb == pr.board
	return pr


def _fake_twin_entry(pr, pid, cell, theta=-23.0):
	"""A fetch.json with one accepted twin proposal (what src.query would write) for the fused-card path."""
	e = {"origin": "gemeo", "piece": pid, "lote": 1, "n_no_lote": 2, "cell": list(cell), "decision": "aceite", "margin": 2.0,
		 "dE": None, "d1_mm": 0.3, "reasons": [], "query": "T0001", "pair": None, "rank": 1, "score": 0.3, "phi_deg": None,
		 "theta_deg": theta, "pose_known": True, "twin_id": "P9", "twin_cell": [3, 4], "ordem": 1}
	with open(pr.p("fetch.json"), "w", encoding="utf-8") as f:
		json.dump({"t": "2026-11-08T00:00:00", "entries": [e], "suprimidas": [], "notes": [], "rest": []}, f)
	return e


def test_hole_is_alta_and_in_fetch(env):
	gui, client, pr, ids = env
	d = gui.holes_json(wait=True)
	assert "erro" not in d["resumo"], d["resumo"]
	h = next(x for x in d["buracos"] if x["cell"] == [2, 3])
	assert h["m"] == 2 and h["confianca"] == "alta", (h["confianca"], h["margem"], h["razoes"])
	assert h["candidatas"][0]["piece"] == ids["A"] and h["candidatas"][0]["rank"] == 1
	a = client.get("/api/holes/alta").json()
	assert a["a_calcular"] is False and a["em_pausa"] is False and a["n_alta"] >= 1
	ent = [e for e in a["entries"] if e["cell"] == [2, 3]]
	assert len(ent) == 1
	e = ent[0]
	assert e["origin"] == "buraco" and e["decision"] == "alta" and e["piece"] == ids["A"] and e["grupo"] == "coloca_agora"
	assert e["hole"]["rank"] == 1 and e["hole"]["m"] == 2 and e["hole"]["fit_version"] == F.FIT_VERSION and e["hole"]["margem"] >= 1.5
	assert e["desenho"]["candidatas"][0]["piece"] == ids["A"] and e["fundida_com_gemea"] is False and e["conflito_gemea"] is None
	assert e["razoes_txt"] and e["lote"] == 1 and e["n_no_lote"] == 2
	# the same block rides on /api/fetch (what «Vai buscar» reads); the counter starts empty
	f = client.get("/api/fetch").json()
	assert f["buracos_alta"]["entries"][0]["piece"] == ids["A"]
	c = f["buracos_alta"]["contador"]
	assert c["total"] == 0 and c["em_pausa"] is False and c["janela"]["tamanho"] == F.ALTA_JANELA and c["janela"]["max_falhas"] == F.ALTA_MAX_FALHAS
	assert client.get("/api/status").json()["contador_alta"]["total"] == 0
	# média / sem are never suggestions
	assert all(x["hole"]["confianca"] == "alta" for x in a["entries"])


def test_fused_card_confirm_records_twin_and_hole(env):
	gui, client, pr, ids = env
	a = ids["A"]
	gui.holes_json(wait=True)
	_fake_twin_entry(pr, a, (2, 3))
	gui._fetch = None
	f = client.get("/api/fetch").json()
	e = next(x for x in f["buracos_alta"]["entries"] if x["cell"] == [2, 3])
	assert e["fundida_com_gemea"] is True and e["gemea_decision"] == "aceite" and e["twin_cell"] == [3, 4]
	r = client.post("/api/holes/2/3/confirmar", json={"piece": a, "gemea": True})
	assert r.status_code == 200, r.text
	p1 = _ok_on_disk(pr.path)
	assert p1.piece(a).estado == "colocada" and tuple(p1.piece(a).celula) == (2, 3)
	hc = _events(p1, "hole_confirmed")[-1]
	pl = _events(p1, "placed")[-1]
	tc = _events(p1, "twin_confirmed")
	assert hc["piece"] == a and hc["confianca"] == "alta" and hc["rank"] == 1 and hc["origin"] == "buraco"
	assert pl["piece"] == a and pl["origin"] == "gemeo" and pl["theta_deg"] is not None       # the twin outcome, as before
	assert tc and tc[-1]["piece"] == a and tc[-1]["origin"] == "gemeo" and tc[-1]["query"] == "T0001"
	c = client.get("/api/status").json()["contador_alta"]
	assert c["acertos"] == 1 and c["falhas"] == 0 and c["total"] == 1 and c["ic95"][0] < 0.5 and c["ic95"][1] == 1.0


def test_fused_card_reject_records_both(env):
	gui, client, pr, ids = env
	a = ids["A"]
	gui.holes_json(wait=True)
	_fake_twin_entry(pr, a, (2, 3))
	gui._fetch = None
	r = client.post("/api/holes/2/3/rejeitar", json={"piece": a, "gemea": True})
	assert r.status_code == 200, r.text
	p1 = _ok_on_disk(pr.path)
	hr = _events(p1, "hole_rejected")[-1]
	tr = _events(p1, "twin_rejected")
	assert hr["piece"] == a and hr["rank"] == 1 and hr["confianca"] == "alta" and hr["custo"] > 0 and hr["margem"] >= 1.5 and hr["fit_version"]
	assert tr and tr[-1]["piece"] == a and tr[-1]["cell"] == [2, 3] and tr[-1]["origin"] == "gemeo"
	assert p1.piece(a).estado == "solta"
	c = client.get("/api/status").json()["contador_alta"]
	assert c["falhas"] == 1 and c["total"] == 1 and c["janela"]["falhas"] == 1 and c["em_pausa"] is False


def test_rank2_rejection_is_recorded_but_not_a_decision(env):
	gui, client, pr, ids = env
	gui.holes_json(wait=True)
	h = next(x for x in gui.holes_json(wait=True)["buracos"] if x["cell"] == [2, 3])
	second = h["candidatas"][1]["piece"]
	r = client.post("/api/holes/2/3/rejeitar", json={"piece": second})
	assert r.status_code == 200, r.text
	ev = _events(Project.open(pr.path), "hole_rejected")[-1]
	assert ev["piece"] == second and ev["rank"] == 2 and ev["confianca"] == "alta"
	c = client.get("/api/status").json()["contador_alta"]
	assert c["total"] == 0                                             # only rank 1 of an alta hole counts


def test_pause_rule_and_resume(env):
	gui, client, pr, ids = env
	gui.holes_json(wait=True)
	# three alta rank-1 rejections (informative events written as the GUI would) -> paused
	for k, cell in enumerate([(1, 1), (1, 2), (1, 3)]):
		pr.log_event("hole_rejected", piece=ids["D"], cell=cell, origin="buraco", rank=1, custo=1.0, margem=2.0, confianca="alta", m=2, fit_version="t")
	pr.save()
	gui.sync()
	gui.holes_json(wait=True)                     # the log changed: the ranking is recomputed before the entries come back
	f = client.get("/api/fetch").json()["buracos_alta"]
	assert f["em_pausa"] is True and f["contador"]["janela"]["falhas"] == 3 and f["contador"]["falhas"] == 3
	assert f["entries"], "paused: the entries are still returned (the GUI moves them to the «Buracos» page)"
	assert client.get("/api/status").json()["contador_alta"]["em_pausa"] is True
	# a 4th decision that is a success does not lift the pause (the window still holds 3 rejections)
	pr.log_event("hole_confirmed", piece=ids["E"], cell=(1, 4), origin="buraco", rank=1, custo=1.0, margem=2.0, confianca="alta", m=2, fit_version="t")
	pr.save()
	gui.sync()
	gui.holes_json(wait=True)
	assert client.get("/api/fetch").json()["buracos_alta"]["em_pausa"] is True
	# reactivation: event + the window restarts
	r = client.post("/api/holes/alta/reativar", json={"nota": "confirmei à mão"})
	assert r.status_code == 200, r.text
	body = r.json()
	assert body["ok"] and body["contador"]["em_pausa"] is False and body["contador"]["janela"]["n"] == 0 and body["contador"]["total"] == 4
	ev = _events(Project.open(pr.path), "holes_alta_resumed")
	assert ev and ev[-1]["autor"] == "tiago" and ev[-1]["nota"] == "confirmei à mão"
	assert client.get("/api/fetch").json()["buracos_alta"]["em_pausa"] is False
	_ok_on_disk(pr.path)
	# the report CLI prints the counter line
	assert "EM PAUSA" not in F.format_counter(F.alta_counter(Project.open(pr.path)))
	assert "reativadas em" in F.format_counter(F.alta_counter(Project.open(pr.path)))
