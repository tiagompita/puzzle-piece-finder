"""Seqlock das suspeitas (2026-11-15, decisão do Tiago; DETALHE.md §11.12).

``consistency.evaluate`` corre fora do bloqueio de escrita e lê o modelo vivo; uma escrita a meio dava um estado que
nunca existiu, sem exceção (cenário «mover»). ``Gui.wlock`` é um :class:`src.server.SeqLock` e ``Gui.seq_read`` só
aceita uma avaliação sem nenhuma escrita a começar ou acabar por baixo; à 3.ª tentativa rasgada devolve o resultado
anterior marcado ``desatualizada`` (nunca toma o bloqueio de escrita, que seguraria o POST do «Encaixa»).
"""
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from src import consistency as CO
from src import server as S
from test_query import _project

X_MS = 50       # a write during an evaluation waits at most this long for the write lock


def test_seqlock_counter_odd_during_write_reentrant_and_owned():
	lk = S.SeqLock()
	assert lk.seq == 0 and not lk.owned()
	with lk:
		assert lk.seq == 1 and lk.owned()
		with lk:                          # re-entrant: one write, one odd stretch
			assert lk.seq == 1
		assert lk.seq == 1
	assert lk.seq == 2 and not lk.owned()
	assert lk.acquire(timeout=0.1)
	seen = {}
	t = threading.Thread(target=lambda: seen.update(ok=lk.acquire(blocking=False), owned=lk.owned()))
	t.start()
	t.join()
	assert seen == {"ok": False, "owned": False}
	lk.release()
	assert lk.wait_even(0.1) == 4


def _setup(tmp_path):
	from src.query import run_query
	pr, placed, tw, dec = _project(tmp_path)
	run_query(pr, use_image=False)
	gui = S.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "up"), log=None, queue=False)
	cl = TestClient(S.create_app(gui))
	for body in ({"acao": "place", "piece": tw, "cell": [3, 4]},
				 {"acao": "place", "piece": dec, "cell": [1, 1], "origin": "manual"}):
		assert cl.post("/api/confirm", json=body).status_code == 200
	gui.wait_suspeitas()
	return gui, cl, placed, tw, dec


def _move(cl, dec, cell):
	"""The «mover» write: take ``dec`` off and put it in ``cell`` (two operations, two log versions)."""
	assert cl.post("/api/confirm", json={"acao": "unplace", "piece": dec}).status_code == 200
	assert cl.post("/api/confirm", json={"acao": "place", "piece": dec, "cell": cell, "origin": "manual"}).status_code == 200


def _fresh(gui, tmp_path, name):
	CO._RESIDUAL_CACHE.clear()
	g = S.Gui(gui.path, prepare=False, use_image=False, uploads=str(tmp_path / name), log=None, queue=False)
	try:
		return g.suspeitas_json()
	finally:
		g.stop()


def _norm(r):
	return json.dumps({"summary": r["summary"], "items": r["items"]}, sort_keys=True, default=str)


def _count_evaluations(monkeypatch):
	"""Evaluations made by THIS thread (the background pass after a write evaluates too, in its own thread)."""
	me, n = threading.get_ident(), {"n": 0}
	orig = CO.evaluate

	def counting(*a, **k):
		if threading.get_ident() == me:
			n["n"] += 1
		return orig(*a, **k)
	monkeypatch.setattr(CO, "evaluate", counting)
	return n


def _time_lock_waits(gui):
	"""Seconds each write waited for the write lock (wrapping ``SeqLock.acquire`` of this Gui)."""
	waits = []
	orig = gui.wlock.acquire

	def acquire(blocking=True, timeout=-1):
		t0 = time.perf_counter()
		ok = orig(blocking, timeout)
		waits.append(time.perf_counter() - t0)
		return ok
	gui.wlock.acquire = acquire
	return waits


@pytest.mark.parametrize("at", [1, 2, 3])
def test_move_under_the_evaluation_gives_the_final_state_not_a_torn_one(tmp_path, monkeypatch, at):
	gui, cl, placed, tw, dec = _setup(tmp_path)
	before = _fresh(gui, tmp_path, "b")
	gui._suspeitas = gui._susp_eval = None
	n = _count_evaluations(monkeypatch)
	calls = {"n": 0}

	def hook():
		calls["n"] += 1
		if calls["n"] == at:               # a «mover» from another thread, in the middle of the evaluation
			th = threading.Thread(target=_move, args=(cl, dec, [2, 4]))
			th.start()
			th.join()
	got = gui.suspeitas_json(pause=hook)
	n_eval = n["n"]
	gui.wait_suspeitas()
	after = _fresh(gui, tmp_path, "a")
	assert _norm(before) != _norm(after)              # the move changes the suspects (else the test proves nothing)
	assert not got.get("desatualizada")
	assert _norm(got) == _norm(after)                  # before the seqlock: n_com_vizinhas 1 (before 0, after 3)
	assert n_eval == 2                                 # the torn evaluation was thrown away and made once more
	assert gui.suspeitas_json() is gui.suspeitas_json() and _norm(gui.suspeitas_json()) == _norm(after)
	gui.stop()


def test_a_write_during_the_evaluation_does_not_wait_for_it(tmp_path):
	gui, cl, placed, tw, dec = _setup(tmp_path)
	gui._suspeitas = gui._susp_eval = None
	waits = _time_lock_waits(gui)
	posted = {}

	def hook():
		time.sleep(0.25)                  # a slow evaluation (≈ 1,5 s in all)
		if "s" not in posted:
			posted["s"] = 0

			def write():
				t0 = time.perf_counter()
				_move(cl, dec, [2, 4])
				posted["s"] = time.perf_counter() - t0
			threading.Thread(target=write).start()   # not joined: the write runs WHILE the evaluation goes on
	t0 = time.perf_counter()
	got = gui.suspeitas_json(pause=hook)
	eval_s = time.perf_counter() - t0
	gui.wait_suspeitas()
	assert waits, "a escrita não tomou o bloqueio"
	assert max(waits) * 1000 < X_MS, (waits, eval_s)
	assert posted["s"] < eval_s                        # the POSTs ended before the (retried) evaluation
	assert not got.get("desatualizada")
	assert _norm(got) == _norm(_fresh(gui, tmp_path, "a"))
	gui.stop()


def test_three_torn_attempts_give_the_previous_result_marked_stale_without_the_write_lock(tmp_path, monkeypatch):
	gui, cl, placed, tw, dec = _setup(tmp_path)
	prev = gui.suspeitas_json()
	gui._suspeitas = gui._susp_eval = None
	waits = _time_lock_waits(gui)
	cells = iter([[2, 4], [1, 1], [2, 4]])
	me, fresh_attempt = threading.get_ident(), {"v": False}
	orig = CO.evaluate

	def evaluate(*a, **k):
		if threading.get_ident() == me:
			fresh_attempt["v"] = True
		return orig(*a, **k)
	monkeypatch.setattr(CO, "evaluate", evaluate)
	bg = {"n": 0}
	real_bg = gui._suspeitas_bg
	# the background pass that each write starts would accept a consistent evaluation of its own in between (a newer
	# «previous result»); held back here so the stale answer can be compared with ``prev``
	gui._suspeitas_bg = lambda: bg.update(n=bg["n"] + 1)

	def hook():                           # every attempt is torn: one «mover» under each of the 3
		if fresh_attempt["v"]:
			fresh_attempt["v"] = False
			th = threading.Thread(target=_move, args=(cl, dec, next(cells)))
			th.start()
			th.join()
	got = gui.suspeitas_json(pause=hook)
	assert got["desatualizada"] is True
	assert _norm(got) == _norm(prev)
	assert gui.n_susp_desatualizadas == 1
	assert waits and max(waits) * 1000 < X_MS, waits
	assert not gui.wlock.owned() and gui.wlock.seq % 2 == 0
	assert bg["n"] >= 7                                # 6 writes + the one more pass asked by the stale answer
	# the next pass (background) gives the final state
	gui._suspeitas_bg = real_bg
	gui._suspeitas_bg()
	gui.wait_suspeitas()
	final = gui.suspeitas_json()
	assert not final.get("desatualizada")
	assert _norm(final) == _norm(_fresh(gui, tmp_path, "a"))
	gui.stop()


def test_under_the_write_lock_the_read_runs_once_without_waiting(tmp_path):
	gui, cl, placed, tw, dec = _setup(tmp_path)
	gui._suspeitas = gui._susp_eval = None
	t0 = time.perf_counter()
	with gui.wlock:                       # e.g. ``_after_suspect_write``: the caller is the write
		got = gui.suspeitas_json()
	assert time.perf_counter() - t0 < 5.0
	assert not got.get("desatualizada")
	gui.stop()
