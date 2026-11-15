"""Seqlock nos outros leitores fora do bloqueio de escrita (2026-11-15, decisão do Tiago; DETALHE.md §13.5 e §13.7).

Cenário «mover» forçado (uma peça tirada e posta noutra célula a meio da leitura, duas escritas, sem exceção):
- ``rank_all`` no fio dos buracos, na pausa 5 e na 14: antes publicava um ranking de um estado que nunca existiu e
  guardava-o em ``_holes_prev`` (a lista que «Vai buscar» mostra durante o recálculo seguinte). Agora um ranking cruzado
  por uma escrita não é publicado (nem ``_holes``, nem ``_holes_prev``, nem ``holes_changed``) e é calculado outra vez;
  durante o recálculo a lista mostrada é a anterior, marcada ``desatualizada``.
- «verificar» (``verify_json``) na 2.ª chamada de ``fit_check``: antes dava a verificação de um estado que nunca
  existiu. Agora repete (``seq_read``); à 3.ª tentativa rasgada devolve o resultado anterior da mesma
  ``(l, c, peça, θ)`` marcado ``desatualizada`` ou, sem nenhum, ``estado: nao_verificado`` (sem veredicto).

Projeto sintético de ``tests/test_query.py`` (P0001 em (2,3), a gémea em (3,4)).
"""
import json
import threading
import time

from fastapi.testclient import TestClient

from src import query as Q
from src import server as S
from test_query import _project

X_MS = 50       # a write during a «verificar» waits at most this long for the write lock


def _setup(tmp_path):
	from src.query import run_query
	pr, placed, tw, dec = _project(tmp_path)
	run_query(pr, use_image=False)
	gui = S.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "up"), log=None, queue=False)
	cl = TestClient(S.create_app(gui))
	assert cl.post("/api/confirm", json={"acao": "place", "piece": tw, "cell": [3, 4]}).status_code == 200
	gui.wait_suspeitas()
	return gui, cl, placed, tw, dec


def _move(cl, pid, cell):
	"""The «mover» write: take ``pid`` off and put it in ``cell`` (two operations, two log versions)."""
	assert cl.post("/api/confirm", json={"acao": "unplace", "piece": pid}).status_code == 200
	assert cl.post("/api/confirm", json={"acao": "place", "piece": pid, "cell": cell, "origin": "manual"}).status_code == 200


def _in_thread(fn, *a):
	th = threading.Thread(target=fn, args=a)
	th.start()
	th.join()


def _fresh(gui, tmp_path, tag):
	return S.Gui(gui.path, prepare=False, use_image=False, uploads=str(tmp_path / tag), log=None, queue=False)


def _join_holes(gui):
	th = getattr(gui, "_holes_thread", None)
	if th is not None:
		th.join(120)


def _hnorm(h):
	return json.dumps(h["buracos"], sort_keys=True, default=str)


def _fresh_holes(gui, tmp_path, tag):
	f = _fresh(gui, tmp_path, tag)
	try:
		return _hnorm(f.holes_json(wait=True))
	finally:
		f.stop()


def _record_publications(gui):
	"""Every ``holes_changed``: what ``_holes`` / ``_holes_prev`` hold then, the log version and the seqlock counter."""
	pubs = []
	orig = gui.emit

	def emit(name, data=None):
		if name == "holes_changed":
			pubs.append({"t": time.perf_counter(), "holes": _hnorm(gui._holes[1]), "key_ver": gui._holes[0][0],
						 "prev": _hnorm(gui._holes_prev) if gui._holes_prev else None, "ver": gui.version(),
						 "seq": gui.wlock.seq})
		return orig(name, data)
	gui.emit = emit
	return pubs


def _rank_mover(tmp_path, at):
	gui, cl, placed, tw, dec = _setup(tmp_path)
	before = _fresh_holes(gui, tmp_path, "b")
	gui.holes_json(wait=True)                    # a complete ranking: the list shown during the next one
	_join_holes(gui)
	gui.wait_suspeitas()
	prev0 = _hnorm(gui._holes_prev)
	assert prev0 == before
	gui._holes = None
	pubs = _record_publications(gui)
	calls, seen = {"n": 0}, {}

	def hook():
		calls["n"] += 1
		if calls["n"] == at:
			_in_thread(_move, cl, tw, [1, 4])
			a = gui.alta_json()                  # the list shown while the ranking is recomputed
			seen.update(desatualizada=a["desatualizada"], a_calcular=a["a_calcular"], prev=_hnorm(gui._holes_prev))
	gui.yield_to_gui = hook
	gui.holes_json(wait=False)
	_join_holes(gui)
	del gui.yield_to_gui
	gui.wait_suspeitas()
	_join_holes(gui)
	after = _fresh_holes(gui, tmp_path, "a")
	gui.stop()
	return before, after, pubs, seen, gui, calls


def _check_rank(tmp_path, at):
	before, after, pubs, seen, gui, calls = _rank_mover(tmp_path, at)
	assert calls["n"] >= at
	assert before != after                       # the move changes the ranking
	assert seen == {"desatualizada": True, "a_calcular": True, "prev": before}
	assert pubs, "nada publicado"
	for p in pubs:                               # never a ranking of a state that did not exist
		assert p["holes"] == after and p["prev"] == after and p["key_ver"] == p["ver"], p
	assert _hnorm(gui._holes[1]) == after and _hnorm(gui._holes_prev) == after


def test_rank_all_mover_na_pausa_5(tmp_path):
	_check_rank(tmp_path, 5)


def test_rank_all_mover_na_pausa_14(tmp_path):
	_check_rank(tmp_path, 14)


def test_rank_all_escritas_seguidas_publica_logo_que_param(tmp_path):
	"""5 colocações com 1 s entre elas enquanto o ranking corre (pausa lenta: um ranking dura > 1 s): nenhuma
	publicação de uma versão que já não é a do log; a 1.ª publicação depois da última escrita chega em menos de um
	ranking + ε; o tempo máximo de lista desatualizada é impresso (DETALHE §13.7)."""
	gui, cl, placed, tw, dec = _setup(tmp_path)
	gui.holes_json(wait=True)
	_join_holes(gui)
	gui.wait_suspeitas()
	gui.yield_to_gui = lambda: time.sleep(0.05)
	gui._holes = None
	t0 = time.perf_counter()
	gui.holes_json(wait=False)
	_join_holes(gui)
	t_rank = time.perf_counter() - t0
	assert t_rank > 1.0, t_rank
	pubs = _record_publications(gui)
	cells = [[1, 1], [1, 2], [1, 1], [1, 2], [1, 1]]
	ends = []
	for i, cell in enumerate(cells):
		if i:
			assert cl.post("/api/confirm", json={"acao": "unplace", "piece": dec}).status_code == 200
		assert cl.post("/api/confirm", json={"acao": "place", "piece": dec, "cell": cell, "origin": "manual"}).status_code == 200
		ends.append(time.perf_counter())
		if i < len(cells) - 1:
			time.sleep(1.0)
	t_last = ends[-1]
	deadline = time.time() + 60
	while not any(p["t"] > t_last for p in pubs) and time.time() < deadline:
		time.sleep(0.05)
	_join_holes(gui)
	gui.wait_suspeitas()
	_join_holes(gui)
	for p in pubs:
		assert p["key_ver"] == p["ver"] and p["seq"] % 2 == 0, p
	after_pub = [p for p in pubs if p["t"] > t_last]
	assert after_pub, "nada publicado depois da última escrita"
	lag = after_pub[0]["t"] - t_last
	assert lag < t_rank + 1.5, (lag, t_rank)
	# stale = from the end of a write to the first publication after it (the list shown is the previous one, marked)
	stale = max(min(p["t"] for p in pubs if p["t"] > e) - e for e in ends)
	print(f"\nranking {t_rank:.2f} s; {len(pubs)} publicações para {len(ends)} colocações; 1.ª depois da última escrita "
		  f"{lag:.2f} s; lista desatualizada no máximo {stale:.2f} s")
	del gui.yield_to_gui
	assert _hnorm(gui._holes[1]) == _fresh_holes(gui, tmp_path, "a")
	gui.stop()


# ---------------------------------------------------------------- «verificar»
def _vnorm(r):
	return json.dumps({k: r[k] for k in ("theta_deg", "verificacoes", "vizinhas_com_forma", "modo")}, sort_keys=True,
					  default=str) + json.dumps(r["diagnostico"], sort_keys=True, default=str)


def test_verificar_mover_na_2a_chamada_igual_a_um_processo_novo(tmp_path, monkeypatch):
	gui, cl, placed, tw, dec = _setup(tmp_path)
	f = _fresh(gui, tmp_path, "b")
	before = _vnorm(f.verify_json(2, 4, dec))
	f.stop()
	calls = {"n": 0}
	orig = Q.fit_check

	def fc(*a, **k):
		calls["n"] += 1
		if calls["n"] == 2:
			_in_thread(_move, cl, tw, [1, 4])
		return orig(*a, **k)
	monkeypatch.setattr(Q, "fit_check", fc)
	got = gui.verify_json(2, 4, dec)
	monkeypatch.setattr(Q, "fit_check", orig)
	gui.wait_suspeitas()
	f = _fresh(gui, tmp_path, "a")
	after = _vnorm(f.verify_json(2, 4, dec))
	f.stop()
	assert before != after
	assert got.get("estado") == "verificado" and not got.get("desatualizada")
	assert _vnorm(got) == after
	_join_holes(gui)
	gui.stop()


def _torn_every_call(monkeypatch, gui):
	"""Every ``fit_check`` call is crossed by a (contentless) write: the seqlock counter moves under it."""
	orig = Q.fit_check
	waits = []

	def fc(*a, **k):
		def write():
			t = time.perf_counter()
			with gui.wlock:
				waits.append(time.perf_counter() - t)
		_in_thread(write)
		return orig(*a, **k)
	monkeypatch.setattr(Q, "fit_check", fc)
	return orig, waits


def test_verificar_tres_tentativas_rasgadas_devolvem_o_anterior_marcado(tmp_path, monkeypatch):
	gui, cl, placed, tw, dec = _setup(tmp_path)
	first = gui.verify_json(2, 4, dec)
	assert first["estado"] == "verificado"
	orig, waits = _torn_every_call(monkeypatch, gui)
	got = gui.verify_json(2, 4, dec)
	monkeypatch.setattr(Q, "fit_check", orig)
	assert got.get("desatualizada") is True
	assert _vnorm(got) == _vnorm(first)
	assert len(waits) >= 3 and max(waits) < X_MS / 1000.0, waits
	_join_holes(gui)
	gui.stop()


def test_verificar_sem_resultado_anterior_devolve_nao_verificado(tmp_path, monkeypatch):
	gui, cl, placed, tw, dec = _setup(tmp_path)
	orig, waits = _torn_every_call(monkeypatch, gui)
	got = gui.verify_json(2, 4, dec, 90.0)
	monkeypatch.setattr(Q, "fit_check", orig)
	assert got.get("estado") == "nao_verificado"
	assert got["verificacoes"] == [] and got["falha"] is False and got["diagnostico"] is None
	assert got["theta_deg"] == 90.0
	ok = gui.verify_json(2, 4, dec, 90.0)                        # asked again, with no write: a verdict
	assert ok["estado"] == "verificado" and ok["verificacoes"]
	_join_holes(gui)
	gui.stop()


def test_uma_escrita_durante_o_verificar_nao_espera(tmp_path, monkeypatch):
	gui, cl, placed, tw, dec = _setup(tmp_path)
	orig = Q.fit_check
	started = threading.Event()

	def slow(*a, **k):
		started.set()
		time.sleep(0.5)
		return orig(*a, **k)
	monkeypatch.setattr(Q, "fit_check", slow)
	th = threading.Thread(target=gui.verify_json, args=(2, 4, dec))
	th.start()
	assert started.wait(30)
	t = time.perf_counter()
	with gui.wlock:
		w = time.perf_counter() - t
	th.join(60)
	monkeypatch.setattr(Q, "fit_check", orig)
	assert w < X_MS / 1000.0, w
	_join_holes(gui)
	gui.stop()
