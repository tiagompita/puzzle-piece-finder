"""F2 da GUI nova (ESPEC §4.4–§4.6; plano de 2026-11-14 com as decisões c e g do Tiago): estado e servidor.

- Par: desfazer «Encaixa» ou «Tirar do lugar» numa peça de um par desfaz só o que essa colocação fez (decisão c).
- «Pôr uma peça à mão»: ``place`` com uma vizinha montada, senão «por confirmar» (decisão g); o «Rodar» manda.
- ``verificar`` (3 verificações em palavras) sem o bloqueio de escrita; ``lookup`` por saco e nº; ``cell_json``.
"""
import threading
import time

import pytest
from fastapi.testclient import TestClient

from src import server as S
from src.confirm import confirm
from src.state import Project, replay, undone_decisions
from test_query import _project


def _pair_project(tmp_path):
	"""O projeto de test_query (P0001 colocada em (2,3), P0002 e P0003 soltas) com o par T P0002/P0003 registado.
	Na grelha 4 × 6 a gémea de (l, c) é (5 − l, 7 − c): pôr P0002 em (1,1) deixa P0003 «por confirmar» em (4,6)."""
	pr, placed, a, b = _project(tmp_path)
	tid = pr.register_pair(a, b)
	pr.save()
	return pr, placed, a, b, tid


def _ok(pr):
	assert pr.check_invariants(disk=True) == []
	rb, _ = replay(pr.log_path, pr.profile)
	assert rb == pr.board
	p2 = Project.open(pr.path)
	assert {k: (v.estado, v.celula) for k, v in p2.pieces.items()} == {k: (v.estado, v.celula) for k, v in pr.pieces.items()}
	assert {k: v.estado for k, v in p2.pairs.items()} == {k: v.estado for k, v in pr.pairs.items()}


@pytest.mark.parametrize("desfaz", [True, False])
def test_unplace_pair_piece_takes_back_what_its_placement_did(tmp_path, desfaz):
	"""Decisão c: a outra peça deixa de estar «por confirmar» e o par volta a «proposto»; com ``desfaz`` (o desfazer de
	«Encaixa») a confirmação do par deixa de contar; sem ele («Tirar do lugar») é neutro."""
	pr, placed, a, b, tid = _pair_project(tmp_path)
	r = confirm(pr, a, cell=(1, 1), origin="manual", requery=False)
	assert "error" not in r
	assert pr.pairs[tid].estado == "confirmado" and pr.piece(b).estado == "posicao_conhecida" and pr.piece(b).celula == (4, 6)
	r = confirm(pr, a, unplace=True, desfaz=desfaz, requery=False)
	assert "error" not in r, r
	assert pr.pairs[tid].estado == "proposto"
	assert pr.piece(a).estado == "emparelhada" and pr.piece(b).estado == "emparelhada" and pr.piece(b).celula is None
	evs = pr.events()
	un = [e for e in evs if e["action"] == "pair_unconfirmed"]
	assert len(un) == 1 and un[0]["pair"] == tid and bool(un[0].get("desfaz")) is desfaz
	cl = [e for e in evs if e["action"] == "position_cleared"]
	assert len(cl) == 1 and cl[0]["piece"] == b and bool(cl[0].get("desfaz")) is desfaz
	ic = next(i for i, e in enumerate(evs) if e["action"] == "pair_confirmed")
	assert (ic in undone_decisions(evs)) is desfaz
	_ok(pr)


def test_pair_confirmed_before_stays_confirmed(tmp_path):
	pr, placed, a, b, tid = _pair_project(tmp_path)
	pr.confirm_pair(tid)
	confirm(pr, a, cell=(1, 1), origin="manual", requery=False)
	assert len([e for e in pr.events() if e["action"] == "pair_confirmed"]) == 1      # no new confirmation
	assert pr.piece(b).estado == "posicao_conhecida"
	confirm(pr, a, unplace=True, requery=False)
	assert pr.pairs[tid].estado == "confirmado"                    # confirmed before this placement: stays
	assert pr.piece(b).estado == "emparelhada"                     # but the kept-aside position came from it: cleared
	assert not [e for e in pr.events() if e["action"] == "pair_unconfirmed"]
	_ok(pr)


def test_other_piece_already_placed_is_left_alone(tmp_path):
	pr, placed, a, b, tid = _pair_project(tmp_path)
	confirm(pr, a, cell=(1, 1), origin="manual", requery=False)
	confirm(pr, b, cell=(4, 6), origin="manual", requery=False)     # the other piece went in meanwhile (CLI, GUI)
	r = confirm(pr, a, unplace=True, desfaz=True, requery=False)
	assert any("fica como está" in m for m in r["messages"]) and any("fica confirmado" in m for m in r["messages"])
	assert pr.piece(b).estado == "colocada" and pr.piece(b).celula == (4, 6)
	assert pr.pairs[tid].estado == "confirmado"
	_ok(pr)


def test_reposicao_and_theta_force(tmp_path):
	pr, placed, a, b, tid = _pair_project(tmp_path)
	r = confirm(pr, a, cell=(1, 1), origin="manual", theta_deg=37.5, theta_force=True, reposicao=True, requery=False)
	assert "error" not in r
	ev = [e for e in pr.events() if e["action"] == "placed"][-1]
	assert ev["reposicao"] is True and abs(ev["theta_deg"] - 37.5) < 1e-9 and abs(pr.piece(a).theta_deg - 37.5) < 1e-9
	_ok(pr)


# ---------------------------------------------------------------- server
@pytest.fixture
def env(tmp_path):
	from src.query import run_query
	pr, placed, tw, dec = _project(tmp_path)
	run_query(pr, use_image=False)
	gui = S.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "uploads"), log=None, queue=False)
	return gui, TestClient(S.create_app(gui)), placed, tw, dec


def test_por_mao_place_with_neighbour_and_kept_aside_without(env):
	"""Decisão g: com uma vizinha colocada (com forma) grava ``place`` com o θ do Tiago; sem vizinha, ``position_known``
	(«por confirmar»: a célula fica vazia para o motor, não conta no progresso)."""
	gui, cl, placed, tw, dec = env
	assert cl.get("/api/cell/2/4").json()["vizinhas_com_forma"] == 1             # (2,3) holds P0001
	r = cl.post("/api/confirm", json={"acao": "por_mao", "piece": tw, "cell": [2, 4], "theta_deg": 12.0})
	assert r.status_code == 200, r.text
	assert r.json()["modo"] == "colocada"
	p = gui.pr.piece(tw)
	assert p.estado == "colocada" and p.celula == (2, 4) and abs(p.theta_deg - 12.0) < 1e-9
	ev = [e for e in gui.pr.events() if e["action"] == "placed"][-1]
	assert ev["origin"] == "manual" and ev["piece"] == tw
	assert cl.get("/api/cell/4/1").json()["vizinhas_com_forma"] == 0
	n0 = cl.get("/api/montar").json()["progresso"]["n"]
	r = cl.post("/api/confirm", json={"acao": "por_mao", "piece": dec, "cell": [4, 1], "theta_deg": -20.0})
	assert r.status_code == 200, r.text
	assert r.json()["modo"] == "por_confirmar"
	q = gui.pr.piece(dec)
	assert q.estado == "posicao_conhecida" and q.celula == (4, 1) and abs(q.theta_deg + 20.0) < 1e-9
	assert gui.pr.board[(4, 1)]["estado"] == "vazia"
	assert cl.get("/api/montar").json()["progresso"]["n"] == n0
	# another piece by hand on that place: refused, nothing written
	n_log = len(gui.pr.events())
	r = cl.post("/api/confirm", json={"acao": "por_mao", "piece": tw, "cell": [4, 1]})
	assert r.status_code == 400 and "por confirmar" in r.json()["error"] and len(gui.pr.events()) == n_log
	_ok(Project.open(gui.path))


def test_place_manual_theta_wins_over_the_list(env):
	"""O «Rodar» do Tiago manda (P10b): ``place`` manual com ``theta_deg`` grava esse θ mesmo com pose na lista; sem
	``origin: manual`` continua a ser recusado como antes."""
	gui, cl, placed, tw, dec = env
	e = next(x for x in cl.get("/api/fetch").json()["entries"] if x.get("piece") == tw)
	assert e["pose_known"] and e["theta_deg"] is not None
	r = cl.post("/api/confirm", json={"acao": "place", "piece": tw, "cell": e["cell"], "origin": "gemeo", "theta_deg": 5.0})
	assert r.status_code == 400 and "já tem a pose" in r.json()["error"]
	r = cl.post("/api/confirm", json={"acao": "place", "piece": tw, "cell": e["cell"], "origin": "manual", "theta_deg": 5.0})
	assert r.status_code == 200, r.text
	assert abs(gui.pr.piece(tw).theta_deg - 5.0) < 1e-9


def test_tirar_is_neutral_and_cell_json_fields(env):
	gui, cl, placed, tw, dec = env
	d = cl.get("/api/cell/2/3").json()
	assert d["peca"]["id"] == placed and d["posta_em"] and d["secao"] is None and d["reports_abertos"] == []
	r = cl.post("/api/confirm", json={"acao": "unplace", "piece": placed, "tirar": True})
	assert r.status_code == 200, r.text
	ev = [e for e in gui.pr.events() if e["action"] == "unplaced"][-1]
	assert ev["piece"] == placed and "desfaz" not in ev                       # neutral (P7b)
	# «por confirmar» taken off with position_clear (no desfaz): neutral too
	cl.post("/api/confirm", json={"acao": "position_known", "piece": dec, "cell": [4, 1], "origin": "manual", "theta_deg": 3.0})
	assert abs(gui.pr.piece(dec).theta_deg - 3.0) < 1e-9
	r = cl.post("/api/confirm", json={"acao": "position_clear", "piece": dec})
	assert r.status_code == 200 and "desfaz" not in [e for e in gui.pr.events() if e["action"] == "position_cleared"][-1]
	# an open report shows in the panel («já reportaste»)
	cl.post("/api/report", json={"piece": tw, "cell": [3, 4], "tipo": "mal_lida", "texto": "comida"})
	cl.post("/api/confirm", json={"acao": "position_known", "piece": tw, "cell": [3, 4], "origin": "manual"})
	d = cl.get("/api/cell/3/4").json()
	assert d["reports_abertos"] and d["reports_abertos"][0]["tipo"] == "mal_lida"


def test_lookup_by_bag_and_number(env):
	gui, cl, placed, tw, dec = env
	p = gui.pr.piece(tw)
	r = cl.get(f"/api/pieces/lookup?saco={p.lote}&n={p.n_no_lote}").json()
	assert r["piece"] == tw and r["pode_por"] is True and "está solta" in r["frase"] and r["theta_base"] is not None
	q = gui.pr.piece(placed)
	r = cl.get(f"/api/pieces/lookup?saco={q.lote}&n={q.n_no_lote}").json()
	assert r["pode_por"] is False and "já está no lugar linha 2 · coluna 3" in r["frase"]
	r = cl.get("/api/pieces/lookup?saco=99&n=1").json()
	assert r["piece"] is None and "não existe" in r["frase"]
	assert cl.get("/api/pieces/lookup?saco=x&n=1").status_code == 400
	assert cl.get(f"/api/pieces/{tw}.png?theta=30&size=120&v=1").headers["X-Pose-Theta"] == "30.00"


def test_verificar_words_rotations_and_no_neighbours(env):
	gui, cl, placed, tw, dec = env
	# a place with a mounted neighbour, no theta: the best of 4 rotations, 3 lines (2,4 is not a border cell? it is: row 2 of 4)
	r = cl.post("/api/cell/2/4/verificar", json={"piece": tw})
	assert r.status_code == 200, r.text
	v = r.json()
	assert v["theta_deg"] is not None and v["vizinhas_com_forma"] == 1 and v["modo"] == "colocar"
	keys = [x["chave"] for x in v["verificacoes"]]
	assert keys[-2:] == ["forma", "imagem"]
	for x in v["verificacoes"]:
		assert x["estado"] in ("folga", "passa", "falha", "nao_testado") and 0 <= x["tracos"] <= 3 and x["frase"]
		for bad in ("mm", "ΔE", "P0", "aceite", "alta"):
			assert bad not in x["frase"]
	# a given theta is used as is
	v2 = cl.post("/api/cell/2/4/verificar", json={"piece": tw, "theta_deg": v["theta_deg"] + 90}).json()
	assert abs(((v2["theta_deg"] - v["theta_deg"] - 90) + 180) % 360 - 180) < 0.01
	# no mounted neighbour: forma / imagem «não verificado»
	v3 = cl.post("/api/cell/4/1/verificar", json={"piece": tw}).json()
	assert v3["vizinhas_com_forma"] == 0 and v3["modo"] == "por_confirmar"
	fi = {x["chave"]: x for x in v3["verificacoes"]}
	assert fi["forma"]["estado"] == "nao_testado" and fi["imagem"]["estado"] == "nao_testado"
	assert "ainda sem peças ao lado" in fi["forma"]["frase"]
	# the border line exists only on a border place and is decided by the class and the rotation
	assert ("borda" in fi) == gui.pr.profile.is_border(4, 1)
	assert cl.post("/api/cell/4/1/verificar", json={"piece": "P9999"}).status_code == 400


def test_verificar_does_not_wait_for_the_write_lock(env):
	"""O «verificar» corre sem o bloqueio de escrita (a verificação não bloqueia, ESPEC §7 F2; DETALHE.md §8)."""
	gui, cl, placed, tw, dec = env
	cl.post("/api/cell/2/4/verificar", json={"piece": tw})            # warm (strips, sides)
	held = threading.Event()
	release = threading.Event()

	def hold():
		with gui.wlock:
			held.set()
			release.wait(10)
	th = threading.Thread(target=hold)
	th.start()
	held.wait(5)
	try:
		t0 = time.perf_counter()
		r = cl.post("/api/cell/2/4/verificar", json={"piece": tw, "theta_deg": 0})
		dt = time.perf_counter() - t0
	finally:
		release.set()
		th.join(10)
	assert r.status_code == 200 and dt < 3.0, dt
