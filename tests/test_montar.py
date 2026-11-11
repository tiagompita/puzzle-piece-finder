"""Ecrã «Montar» da GUI nova (F1b, ESPEC §4.1–§4.3, §5.1–§5.2, §8.1–§8.4): src/montar.py, os eventos de desfazer
(state: ``rejection_undone``, ``pair_unrejected``, ``rejection_noted``, ``unplaced desfaz``), os contadores que
ignoram decisões desfeitas, e os endpoints (``GET /api/montar``, ``acao: undo_reject | reject_reason | unplace
desfaz``, ``escritos``, ``/api/board?ui=novo``, ``/?ui=novo``) sobre o projeto sintético de ``tests/test_query.py``.
"""

import os

import pytest

from src import montar as MT
from src.state import Project, replay, undone_decisions

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from src import server as SV  # noqa: E402
from test_query import _project  # noqa: E402


# ---------------------------------------------------------------- puro: decisões desfeitas
def _ev(a, **k):
	return dict(action=a, **k)


def test_undone_decisions_pairs_each_undo_with_its_decision():
	evs = [
		_ev("hole_confirmed", piece="P1", cell=[2, 3], origin="buraco"),       # 0 desfeita (unplaced desfaz)
		_ev("placed", piece="P1", cell=[2, 3]),
		_ev("twin_confirmed", piece="P1", cell=[2, 3], origin="gemeo"),        # 2 desfeita
		_ev("unplaced", piece="P1", cell=[2, 3], desfaz=True),
		_ev("twin_confirmed", piece="P2", cell=[4, 4], origin="gemeo"),        # 4 neutra: unplaced sem desfaz
		_ev("unplaced", piece="P2", cell=[4, 4]),
		_ev("unplaced", piece="P2", cell=[4, 4], desfaz=True),                 # nada para desfazer
		_ev("twin_rejected", piece="P3", cell=[5, 5], origin="gemeo"),         # 7 fica
		_ev("twin_rejected", piece="P3", cell=[5, 5], origin="gemeo"),         # 8 desfeita (a última)
		_ev("rejection_undone", piece="P3", cell=[5, 5], origin="gemeo"),
		_ev("hole_rejected", piece="P3", cell=[5, 5], origin="buraco"),        # 10 fica (outra origem)
		_ev("pair_rejected", pair="T0001"),                                    # 11 desfeita
		_ev("pair_unrejected", pair="T0001"),
	]
	assert undone_decisions(evs) == {0, 2, 8, 11}


def test_track_record_and_quase_certo_rule():
	class Prof:
		def zone_of(self, l, c):
			return "ceu" if l <= 14 else "relva"
	evs = [_ev("twin_confirmed", piece=f"P{i}", cell=[2, i], origin="gemeo") for i in range(1, 11)]
	rec = MT.track_record(evs, Prof())
	assert rec[("gemeo", "ceu")]["n"] == 10 and rec[("gemeo", "ceu")]["wilson_lo"] < 0.80     # 10/10: Wilson 0,72
	evs += [_ev("twin_confirmed", piece=f"Q{i}", cell=[3, i], origin="gemeo") for i in range(1, 11)]
	rec = MT.track_record(evs, Prof())
	assert rec[("gemeo", "ceu")]["wilson_lo"] >= 0.80                                            # 20/20: 0,84
	it = {"tipo": "gemea", "origin": "gemeo", "decision": "aceite", "cell": [5, 5], "tracos": []}
	assert MT.confidence(it, rec, Prof()) == "quase_certo"
	assert MT.confidence(dict(it, decision="ambigua"), rec, Prof()) == "a_confirmar"
	assert MT.confidence(dict(it, cell=[30, 5]), rec, Prof()) == "a_confirmar"                   # outra zona: sem histórico
	assert MT.confidence(dict(it, encaixe={"estado": "incompativel"}), rec, Prof()) == "a_confirmar"
	assert MT.confidence(dict(it, tracos=[{"estado": "falha"}]), rec, Prof()) == "a_confirmar"
	# desfeitas não contam: 20 confirmações das quais 11 desfeitas -> n = 9
	undo = [_ev("unplaced", piece=f"Q{i}", cell=[3, i], desfaz=True) for i in range(1, 11)]
	undo.append(_ev("unplaced", piece="P1", cell=[2, 1], desfaz=True))
	assert MT.track_record(evs + undo, Prof())[("gemeo", "ceu")]["n"] == 9


def test_tracos_levels_and_not_tested():
	class Prof:
		calibration = {"silhueta_silhueta": {"t95": 0.5}, "buraco": {"t_abs": 2.0}, "margin_min": 1.5}

		def zone_of(self, l, c):
			return "ceu" if l <= 14 else "vale"

		def zones(self):
			return {"ceu": {"dE_p90": 50.0}, "vale": {"dE_p90": None}}
	t = MT.tracos({"tipo": "gemea", "cell": [2, 2], "d1_mm": 0.2, "dE": 10.0, "margin": 4.0}, Prof())
	assert [x["tracos"] for x in t] == [3, 3, 3] and [x["chave"] for x in t] == ["forma", "imagem", "distancia"]
	t = MT.tracos({"tipo": "gemea", "cell": [2, 2], "d1_mm": 0.4, "dE": 40.0, "margin": 2.0}, Prof())
	assert [x["tracos"] for x in t] == [2, 2, 2]
	t = MT.tracos({"tipo": "gemea", "cell": [30, 2], "d1_mm": 0.7, "dE": 10.0, "margin": 1.2}, Prof())
	assert [x["tracos"] for x in t] == [1, 0, 1]
	assert t[1]["estado"] == "nao_testado" and "não verificado" in t[1]["frase"]
	t = MT.tracos({"tipo": "buraco", "cell": [2, 2], "hole": {"J": 0.9, "margem": 1.6}}, Prof())
	assert [x["tracos"] for x in t] == [3, 0, 2]
	t = MT.tracos({"tipo": "gemea", "cell": [2, 2], "d1_mm": 0.2, "dE": 10.0, "margin": 4.0,
				   "encaixe": {"estado": "incompativel"}}, Prof())
	assert t[0]["tracos"] == 1


def _it(piece, lote, conf_ok, ordem, origin="gemeo", decision="aceite", grupo="coloca_agora", estado="solta"):
	return {"piece": piece, "lote": lote, "n_no_lote": 1, "cell": [2, ordem + 1], "origin": origin, "decision": decision,
			"grupo": grupo, "estado_atual": estado, "ordem": ordem, "margin": 4.0 if conf_ok else 1.0, "d1_mm": 0.1, "dE": None}


def test_fila_by_bag_rules():
	rec = {("gemeo", None): {"n": 30, "acertos": 30, "falhas": 0, "wilson_lo": 0.9}}
	es = [_it("A", 3, True, 1), _it("B", 5, True, 2), _it("C", 5, True, 3), _it("D", 3, False, 4),
		  _it("E", 7, True, 5, grupo="guarda_posicao"), _it("F", 7, True, 6, estado="colocada")]
	q = MT.fila(es, None, rec)
	assert [it["piece"] for it in q["itens"]] == ["B", "C", "A", "D"]          # saco com mais «quase certo» primeiro
	assert q["saco"] == 5 and q["ordem_sacos"] == [5, 3]
	q = MT.fila(es, None, rec, ultimo_saco=3)
	assert q["saco"] == 3 and [it["piece"] for it in q["itens"]] == ["A", "D", "B", "C"]
	q = MT.fila(es, None, rec, saco_atual=5, ultimo_saco=3)                     # o saco a esgotar fica fixo
	assert q["saco"] == 5
	q = MT.fila(es, None, rec, saco_atual=9, ultimo_saco=3)                     # saco esgotado: regra seguinte
	assert q["saco"] == 3
	a = q["itens"][0]
	assert a["encaixa"]["url"] == "/api/confirm" and a["encaixa"]["body"]["acao"] == "place"
	assert a["nao_encaixa"]["body"] == {"acao": "reject", "piece": "A"}
	# fundida com uma sugestão alta (um cartão, pedidos do buraco com gemea) e alta solta; em pausa não entram
	alta = {"em_pausa": False, "entries": [
		{"piece": "A", "cell": [2, 2], "fundida_com_gemea": True, "hole": {"J": 1.0, "margem": 3.0}},
		{"piece": "Z", "lote": 3, "n_no_lote": 9, "cell": [9, 9], "origin": "buraco", "decision": "alta", "estado_atual": "solta",
		 "fundida_com_gemea": False, "ordem": 1, "hole": {"J": 1.0, "margem": 3.0}}]}
	q = MT.fila(es, alta, rec, ultimo_saco=3)
	by = {it["piece"]: it for it in q["itens"]}
	assert by["A"]["tipo"] == "fundida" and by["A"]["encaixa"]["url"] == "/api/holes/2/2/confirmar"
	assert by["A"]["encaixa"]["body"] == {"piece": "A", "gemea": True}
	assert by["Z"]["tipo"] == "buraco" and by["Z"]["nao_encaixa"]["url"] == "/api/holes/9/9/rejeitar"
	q = MT.fila(es, dict(alta, em_pausa=True), rec, ultimo_saco=3)
	assert "Z" not in {it["piece"] for it in q["itens"]} and q["em_pausa"]
	assert {it["piece"]: it for it in q["itens"]}["A"]["tipo"] == "gemea"


# ---------------------------------------------------------------- servidor + estado
@pytest.fixture
def env(tmp_path):
	from src.query import run_query
	pr, placed, tw, dec = _project(tmp_path)
	run_query(pr, use_image=False)
	gui = SV.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "uploads"), log=None)
	client = TestClient(SV.create_app(gui))
	es = [e for e in client.get("/api/fetch").json()["entries"] if e.get("piece")]
	l, c = es[0]["cell"]
	nb = [n for n in gui.pr.board.neighbours((l, c)) if gui.pr.board[n]["estado"] == "vazia"][0]
	gui.pr.mark_cell_full(nb)                     # vizinha montada (marcada pelo Tiago): a proposta passa a «coloca agora»
	gui.pr.save()
	gui._known_stat = gui._log_stat()
	return gui, client, placed, tw, dec


def _ok(path):
	pr = Project.open(path)
	assert pr.check_invariants(disk=True) == []
	rb, _ = replay(pr.log_path, pr.profile)
	assert rb == pr.board
	return pr


def test_board_legend_rows_only_for_the_new_gui(env):
	gui, client, *_ = env
	old = {r["id"] for r in client.get("/api/board").json()["legend"]}
	new = client.get("/api/board?ui=novo").json()["legend"]
	assert not ({"alvo", "seguinte", "por_montar"} & old)
	assert {"alvo", "seguinte", "por_montar"} <= {r["id"] for r in new}
	assert {r["id"] for r in new if r.get("curta")} == {"alvo", "por_montar"}
	assert old == {r["id"] for r in SV.LEGEND if not r.get("gui")}
	assert {r["id"] for r in client.get("/api/legend").json()} == old


def test_switch_routes(env):
	gui, client, *_ = env
	r = client.get("/?ui=novo", follow_redirects=False)
	assert r.status_code == 307 and r.headers["location"] == "/novo/"
	assert "Mesa de montagem" in client.get("/").text
	html = client.get("/novo/").text
	assert "novo.js" in html and "../board.js" in html and "Montar" in html


def test_montar_queue_reject_reason_and_undo(env):
	gui, client, placed, tw, dec = env
	m = client.get("/api/montar").json()
	assert m["total"] == 1 and m["progresso"]["n"] == 2 and m["progresso"]["marcadas"] == 1 and m["total_celulas"] == gui.pr.profile.cell_count()
	it = m["itens"][0]
	assert it["piece"] == tw and it["tipo"] == "gemea" and it["confianca"] == "a_confirmar"   # sem histórico físico
	assert [t["chave"] for t in it["tracos"]] == ["forma", "imagem", "distancia"]
	# Não encaixa -> escritos (a rejeição) -> motivo -> desfazer
	r = client.post(it["nao_encaixa"]["url"], json=it["nao_encaixa"]["body"]).json()
	rej = [e for e in r["escritos"] if e["action"] == "twin_rejected"]
	assert len(rej) == 1 and rej[0]["piece"] == tw and rej[0]["t"]
	assert client.get("/api/montar").json()["total"] == 0
	body = {"acao": "reject_reason", "motivo": "forma", "rejeicoes": [dict(rej[0])]}
	rn = client.post("/api/confirm", json=body).json()
	assert rn["ok"] and rn["escritos"][0]["action"] == "rejection_noted"
	assert client.post("/api/confirm", json=dict(body, motivo="xx")).status_code == 400
	noted = [e for e in gui.pr.events() if e["action"] == "rejection_noted"]
	assert noted[-1]["motivo"] == "forma" and noted[-1]["ref_t"] == rej[0]["t"] and noted[-1]["origin"] == "gemeo"
	u = client.post("/api/confirm", json={"acao": "undo_reject", "rejeicoes": [rej[0]]}).json()
	assert u["ok"] and [e["action"] for e in u["escritos"]][0] == "rejection_undone"
	assert client.get("/api/montar").json()["total"] == 1                     # a proposta voltou
	assert client.post("/api/confirm", json={"acao": "undo_reject", "rejeicoes": [rej[0]]}).status_code == 400
	pr = _ok(gui.path)
	assert not pr.model.rejections
	evs = pr.events()
	assert {i for i in undone_decisions(evs) if evs[i]["action"] == "twin_rejected"}


def test_montar_encaixa_and_undo_does_not_count(env):
	gui, client, placed, tw, dec = env
	it = client.get("/api/montar").json()["itens"][0]
	r = client.post(it["encaixa"]["url"], json=it["encaixa"]["body"]).json()
	assert r["ok"] and any(e["action"] == "placed" and e["piece"] == tw for e in r["escritos"])
	assert any(e["action"] == "twin_confirmed" for e in r["escritos"])
	assert client.get("/api/montar").json()["progresso"]["n"] == 3
	u = client.post("/api/confirm", json={"acao": "unplace", "piece": tw, "desfaz": True}).json()
	assert u["ok"]
	evs = gui.pr.events()
	unp = [e for e in evs if e["action"] == "unplaced"]
	assert unp[-1]["desfaz"] is True and unp[-1]["piece"] == tw
	conf = [i for i, e in enumerate(evs) if e["action"] == "twin_confirmed"]
	assert set(conf) <= undone_decisions(evs)
	assert MT.track_record(evs, gui.pr.profile) == {}                         # a ação desfeita não conta
	m = client.get("/api/montar").json()
	assert m["total"] == 1 and m["progresso"]["n"] == 2
	_ok(gui.path)


def test_alta_counter_ignores_undone(tmp_path):
	from src import fit as F

	class P:
		def __init__(self, evs):
			self._e = evs

		def events(self):
			return self._e
	d = dict(origin="buraco", confianca="alta", rank=1)
	evs = [_ev("hole_rejected", piece="P1", cell=[2, 2], **d), _ev("hole_rejected", piece="P2", cell=[2, 3], **d),
		   _ev("hole_rejected", piece="P3", cell=[2, 4], **d)]
	assert F.alta_counter(P(evs))["em_pausa"]
	evs.append(_ev("rejection_undone", piece="P3", cell=[2, 4], origin="buraco"))
	c = F.alta_counter(P(evs))
	assert c["falhas"] == 2 and not c["em_pausa"]


def test_pair_unreject_state(tmp_path):
	pr, placed, tw, dec = _project(tmp_path)
	tid = pr.register_pair(tw, dec, d1=0.2, margin=3.0)
	pr.reject_pair(tid)
	assert pr.pairs[tid].estado == "rejeitado" and pr.piece(tw).estado == "solta"
	pr.unreject_pair(tid, ref_t="x")
	assert pr.pairs[tid].estado == "proposto" and pr.piece(tw).estado == "emparelhada"
	with pytest.raises(ValueError):
		pr.unreject_pair(tid)
	with pytest.raises(ValueError):
		pr.note_rejection(tw, "talvez", pair=tid)
	pr.note_rejection(tw, "nao_sei", pair=tid)
	pr.save()
	assert pr.check_invariants(disk=True) == []
	assert os.path.exists(pr.log_path)
