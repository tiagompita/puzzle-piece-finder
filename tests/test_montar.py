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
	# saco com mais «quase certo» primeiro; E (sem vizinha montada) só no fim, como «Guardar à parte» (F1c); F já colocada
	assert [it["piece"] for it in q["itens"]] == ["B", "C", "A", "D", "E"]
	assert q["n_coloca"] == 4 and q["n_guardar"] == 1 and q["itens"][-1]["tipo"] == "guardar"
	assert q["saco"] == 5 and q["ordem_sacos"] == [5, 3]
	q = MT.fila(es, None, rec, ultimo_saco=3)
	assert q["saco"] == 3 and [it["piece"] for it in q["itens"]] == ["A", "D", "B", "C", "E"]
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
	assert not ({"alvo", "alvo_guardar", "seguinte", "por_montar"} & old)
	assert {"alvo", "seguinte", "por_montar"} <= {r["id"] for r in new}
	assert {r["id"] for r in new if r.get("curta")} == {"alvo", "alvo_guardar", "por_montar"}   # 3 entradas (ESPEC §4.1; F1c)
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


# ---------------------------------------------------------------- F1c: «Guardar à parte», ecrã vazio, lupa
def test_fila_guardar_after_coloca_never_quase_certo():
	rec = {("gemeo", None): {"n": 30, "acertos": 30, "falhas": 0, "wilson_lo": 0.9}}
	es = [_it("G1", 3, True, 1, grupo="guarda_posicao"), _it("A", 5, True, 2), _it("G2", 5, True, 3, grupo="guarda_posicao"),
		  _it("A", 5, True, 4, grupo="guarda_posicao"),                              # já na fila como «coloca agora»
		  _it("K", 5, True, 5, grupo="guarda_posicao", estado="posicao_conhecida"),  # já guardada: não volta
		  _it("Q", 5, True, 6, origin="posicao_conhecida", grupo="guarda_posicao"),
		  dict(_it("S", 5, True, 7, grupo="guarda_posicao"), piece=None, origin="seccao")]
	q = MT.fila(es, None, rec)
	assert [(it["piece"], it["tipo"]) for it in q["itens"]] == [("A", "gemea"), ("G2", "guardar"), ("G1", "guardar")]
	assert q["n_coloca"] == 1 and q["n_guardar"] == 2 and q["total"] == 3
	g = q["itens"][1]
	assert g["confianca"] == "a_confirmar" and q["itens"][0]["confianca"] == "quase_certo"   # mesma origem e histórico
	assert g["encaixa"] is None                                                               # sem «Encaixa»
	assert g["guardar"]["body"] == {"acao": "position_known", "piece": "G2", "cell": g["cell"], "origin": "gemeo", "nota": "saquinho"}
	assert g["nao_encaixa"]["body"] == {"acao": "reject", "piece": "G2"}
	assert [t["chave"] for t in g["tracos"]] == ["forma", "imagem", "distancia"] and g["tipo_base"] == "gemea"
	assert q["itens"][0]["guardar"] is None
	# só «guardar»: a fila não fica vazia
	q = MT.fila([e for e in es if e["piece"] != "A"], None, rec)
	assert q["n_coloca"] == 0 and [it["piece"] for it in q["itens"]] == ["G1", "G2"] and q["saco"] is None


def test_resumo_counts_what_is_outside_the_queue():
	es = [_it("G1", 3, True, 1, grupo="guarda_posicao"),
		  dict(_it("S", 3, True, 2), piece=None, origin="seccao", decision="por_ancorar"),
		  dict(_it("S2", 3, True, 3), piece=None, origin="seccao", decision="por_ancorar", cell=None)]
	q = MT.fila(es, None, {})
	r = MT.resumo(es, q["itens"], guardadas=4)
	assert r == {"guardar": 1, "guardadas": 4, "grupos_sem_lugar": 2, "propostas": 3}


@pytest.fixture
def env_guarda(tmp_path):
	"""O projeto sintético sem vizinha montada: a proposta de gémea é ``guarda_posicao`` (0 «coloca agora»)."""
	from src.query import run_query
	pr, placed, tw, dec = _project(tmp_path)
	run_query(pr, use_image=False)
	gui = SV.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "uploads"), log=None)
	return gui, TestClient(SV.create_app(gui)), tw


def test_montar_guardar_card_position_known_and_undo(env_guarda):
	gui, client, tw = env_guarda
	f = client.get("/api/fetch").json()
	assert [e["grupo"] for e in f["entries"] if e.get("piece")] == ["guarda_posicao"]
	m = client.get("/api/montar").json()
	assert m["total"] == 1 and m["n_coloca"] == 0 and m["n_guardar"] == 1
	it = m["itens"][0]
	assert it["piece"] == tw and it["tipo"] == "guardar" and it["encaixa"] is None and it["confianca"] == "a_confirmar"
	assert m["fora_da_fila"]["guardar"] == 1
	r = client.post(it["guardar"]["url"], json=it["guardar"]["body"]).json()
	assert r["ok"] and [e["action"] for e in r["escritos"]][0] == "position_known"
	assert gui.pr.piece(tw).estado == "posicao_conhecida"
	m = client.get("/api/montar").json()
	assert m["total"] == 0 and m["fora_da_fila"]["guardadas"] == 1 and m["fora_da_fila"]["guardar"] == 0
	# desfazer «Guardei à parte» (F1c): position_cleared com desfaz, a proposta volta
	u = client.post("/api/confirm", json={"acao": "position_clear", "piece": tw, "desfaz": True}).json()
	assert u["ok"] and u["escritos"][0]["action"] == "position_cleared"
	ev = [e for e in gui.pr.events() if e["action"] == "position_cleared"][-1]
	assert ev["desfaz"] is True and ev["to"] == "solta" and ev["piece"] == tw
	assert gui.pr.piece(tw).estado == "solta" and gui.pr.piece(tw).celula is None
	assert client.get("/api/montar").json()["itens"][0]["tipo"] == "guardar"
	assert client.post("/api/confirm", json={"acao": "position_clear", "piece": tw, "desfaz": True}).status_code == 400
	_ok(gui.path)


def test_montar_nao_e_esta_and_undo(env_guarda):
	gui, client, tw = env_guarda
	it = client.get("/api/montar").json()["itens"][0]
	r = client.post(it["nao_encaixa"]["url"], json=it["nao_encaixa"]["body"]).json()
	rej = [e for e in r["escritos"] if e["action"] == "twin_rejected"]
	assert len(rej) == 1 and rej[0]["piece"] == tw
	assert client.get("/api/montar").json()["total"] == 0
	u = client.post("/api/confirm", json={"acao": "undo_reject", "rejeicoes": [rej[0]]}).json()
	assert u["ok"] and u["escritos"][0]["action"] == "rejection_undone"
	assert client.get("/api/montar").json()["itens"][0]["tipo"] == "guardar"
	_ok(gui.path)


def test_montar_only_groups_counts_them(env_guarda):
	"""Um fetch.json só com grupos por ancorar (0 «coloca agora», 0 peças): a fila fica vazia mas o resumo conta-os."""
	import json
	gui, client, tw = env_guarda
	fp = gui.pr.p("fetch.json")
	with open(fp, encoding="utf-8") as fh:
		f = json.load(fh)
	f["entries"] = [{"origin": "seccao", "decision": "por_ancorar", "piece": None, "cell": [2, 2], "section": "G0001",
					 "candidates": [], "ordem": 1}]
	with open(fp, "w", encoding="utf-8") as fh:
		json.dump(f, fh)
	gui._fetch = None
	m = client.get("/api/montar").json()
	assert m["total"] == 0 and m["fora_da_fila"]["grupos_sem_lugar"] == 1 and m["fora_da_fila"]["propostas"] == 1


def test_lupa_proposals_carry_group(env_guarda):
	gui, client, tw = env_guarda
	p = client.get(f"/api/pieces/{tw}").json()
	assert [e["grupo"] for e in p["propostas"]] == ["guarda_posicao"]
	l, c = p["propostas"][0]["cell"]
	d = client.get(f"/api/cell/{l}/{c}").json()
	assert [(e["piece"], e["grupo"]) for e in d["propostas"]] == [(tw, "guarda_posicao")]


def test_position_cleared_state_and_replay(tmp_path):
	from src.state import StateError
	pr, placed, tw, dec = _project(tmp_path)
	with pytest.raises(StateError):
		pr.clear_position_known(tw)
	tid = pr.register_pair(dec, tw, d1=0.2, margin=3.0)      # par ativo: volta a «emparelhada»
	pr.set_position_known(tw, (3, 4), origin="gemeo", theta_deg=12.0)
	ev = pr.clear_position_known(tw, desfaz=True)
	assert ev["to"] == "emparelhada" and ev["desfaz"] is True and list(ev["cell"]) == [3, 4]
	p = pr.piece(tw)
	assert p.estado == "emparelhada" and p.celula is None and p.theta_deg is None
	assert tid in pr.pairs
	pr.save()
	_ok(pr.path)


ALPES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "projects", "alpes")


def test_real_fetch_proposals_never_vanish_from_montar(tmp_path):
	"""Com o fetch.json real (lido numa cópia de projects/alpes): cada proposta com peça pendente está na fila do
	Montar ou contada como guardada à parte, e cada grupo por ancorar está contado. Se houver propostas, o ecrã
	nunca pode cair no «Nada para ir buscar» (o vazio só sem nada em ``fora_da_fila``)."""
	import json
	import shutil
	from src.query import fetch_group
	if not os.path.exists(os.path.join(ALPES, "fetch.json")):
		pytest.skip("projects/alpes não está presente")
	for name in ("project.json", "puzzle.json", "log.jsonl", "fetch.json"):
		shutil.copy(os.path.join(ALPES, name), tmp_path / name)
	if os.path.isdir(os.path.join(ALPES, "photos")):
		shutil.copytree(os.path.join(ALPES, "photos"), tmp_path / "photos")
	pr = Project.open(str(tmp_path))
	with open(tmp_path / "fetch.json", encoding="utf-8") as fh:
		entries = [dict(e) for e in json.load(fh).get("entries", []) if isinstance(e, dict)]
	for e in entries:
		if e.get("cell"):
			e["grupo"] = fetch_group(pr, e)
		if e.get("piece") in pr.pieces:
			e["estado_atual"] = pr.piece(e["piece"]).estado
	q = MT.fila(entries, None, MT.track_record(pr.events(), pr.profile), pr.profile)
	in_q = {it["piece"] for it in q["itens"]}
	guardadas = {p.id for p in pr.pieces.values() if p.estado == "posicao_conhecida"} - in_q
	r = MT.resumo(entries, q["itens"], len(guardadas))
	lost = [e["piece"] for e in entries if e.get("piece") and e.get("cell") and e.get("estado_atual") in MT.PENDING_STATES
			and e["piece"] not in in_q and e["piece"] not in guardadas]
	assert not lost, f"propostas com peça que não aparecem no Montar: {lost}"
	assert r["grupos_sem_lugar"] == sum(1 for e in entries if e.get("origin") == "seccao")
	if r["propostas"]:
		assert q["total"] or r["guardar"] or r["guardadas"] or r["grupos_sem_lugar"], "o Montar diria «Nada para ir buscar»"


def test_por_confirmar_is_not_a_mould_nor_neighbour_nor_progress(env_guarda):
	"""F1d ponto 2 (verificado no código antes de mudar a GUI): «Colocar aqui» continua a ser ``position_known``; a célula
	fica vazia no tabuleiro, a peça não é vizinha (``mounted_neighbours``), não é molde de nenhum buraco
	(``fit.hole_queries``: só ``colocada``), não conta no progresso do topo (P12), e ``/api/board`` dá-a em
	``posicoes_conhecidas`` com a rotação para o desenho «por confirmar»."""
	from src import fit
	from src.query import mounted_neighbours
	gui, client, tw = env_guarda
	pr = gui.pr
	it = client.get("/api/montar").json()["itens"][0]
	cell = tuple(it["cell"])
	nbs = pr.board.neighbours(cell)
	def snap():
		holes = fit.hole_queries(pr, cells=nbs + [cell], min_neighbours=1)
		return (client.get("/api/montar").json()["progresso"], [mounted_neighbours(pr, nb) for nb in nbs],
				sorted((h.cell, tuple(sorted(s.piece_id for s in h.sides))) for h in holes))
	before = snap()
	r = client.post(it["guardar"]["url"], json=it["guardar"]["body"]).json()
	assert r["ok"] and r["escritos"][0]["action"] == "position_known"
	assert pr.piece(tw).estado == "posicao_conhecida" and pr.piece(tw).celula == cell
	assert pr.board[cell]["estado"] == "vazia" and not pr.board.occupied(cell)
	after = snap()
	assert after == before
	assert all(tw not in pieces for _, pieces in after[2])
	b = client.get("/api/board?ui=novo").json()
	k = [x for x in b["posicoes_conhecidas"] if x["piece"] == tw]
	assert len(k) == 1 and tuple(k[0]["cell"]) == cell and "theta_deg" in k[0]
	assert b["progresso"]["colocadas"] == sum(1 for _, c in pr.board.iter_cells() if c["estado"] == "colocada")
	row = [r for r in b["legend"] if r["id"] == "por_confirmar"]
	assert len(row) == 1 and not row[0].get("curta") and row[0]["classe"] == "b-por-confirmar"
	assert "por_confirmar" not in {r["id"] for r in client.get("/api/board").json()["legend"]}   # só a GUI nova
	_ok(gui.path)


WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "web")


def test_novo_icons_local_and_licensed():
	"""F1d ponto 5: os ícones da GUI nova são SVG do Lucide guardados no repositório, com a licença ao lado, todos
	referidos por uma classe CSS e sem conteúdo ativo; HTML, CSS e JS de /novo/ (e o core/board que carrega) não
	referem nenhum URL externo (só o espaço de nomes do SVG)."""
	import re
	icons = os.path.join(WEB, "novo", "icons")
	lic = open(os.path.join(icons, "LICENSE-lucide.txt"), encoding="utf-8").read()
	assert "ISC License" in lic and "Lucide Icons and Contributors" in lic and "Cole Bemis" in lic
	svgs = sorted(f[:-4] for f in os.listdir(icons) if f.endswith(".svg"))
	css = open(os.path.join(WEB, "novo", "novo.css"), encoding="utf-8").read()
	js = open(os.path.join(WEB, "novo", "novo.js"), encoding="utf-8").read()
	html = open(os.path.join(WEB, "novo", "index.html"), encoding="utf-8").read()
	used = set(re.findall(r'ico\("([a-z0-9-]+)"\)', js)) | set(re.findall(r'class="ico i-([a-z0-9-]+)"', html))
	assert used and used <= set(svgs), used - set(svgs)
	for n in svgs:
		assert f'url("icons/{n}.svg")' in css, n
		t = open(os.path.join(icons, f"{n}.svg"), encoding="utf-8").read()
		assert set(re.findall(r"<([a-zA-Z]+)", t)) <= {"svg", "path", "circle", "line", "rect", "polyline", "polygon", "ellipse"}, n
		assert not re.search(r"\bon[a-z]+\s*=|href|<script", t, re.I), n
	ns = "http://www.w3.org/2000/svg"
	for name in ("novo/index.html", "novo/novo.css", "novo/novo.js", "core.js", "board.js", "board.css"):
		t = open(os.path.join(WEB, name), encoding="utf-8").read().replace(ns, "")
		assert not re.search(r"(https?:)?//[a-z0-9.-]+\.[a-z]{2,}", t, re.I), (name, re.findall(r"(?:https?:)?//[^\s\"')]+", t)[:5])
	for n in svgs:
		assert not re.search(r"https?://", open(os.path.join(icons, f"{n}.svg"), encoding="utf-8").read().replace(ns, "")), n
