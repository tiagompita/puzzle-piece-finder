"""P-a (2026-11-16, DETALHE.md §13.10): depois de uma escrita, ``/api/board``, ``/api/ghosts`` e ``/api/montar`` cedem
a uma região de detalhe em composição (``Gui.priority`` à volta da região, ``Gui.after_detail`` no início dos três),
com a espera limitada a ``DETALHE_ESPERA_S``. Um detalhe ultrapassado (409) ou que falha (500) deixa-os seguir logo,
um que nunca acaba prende-os no máximo o limite, e uma escrita nunca espera por isto (o bloqueio de escrita não entra)."""
import threading
import time

import pytest

pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from src import server as S  # noqa: E402
from test_query import _project  # noqa: E402

THREE = ("/api/board", "/api/ghosts", "/api/montar")
REGION = "/api/board.jpg?ppc=60&region=1,1,2,2"


@pytest.fixture
def env(tmp_path):
	from src.query import run_query
	pr, placed, tw, dec = _project(tmp_path)
	run_query(pr, use_image=False)
	gui = S.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "uploads"), log=None, queue=False)
	cl = TestClient(S.create_app(gui))
	for p in THREE:                              # warm (the 1st montar computes the queue)
		assert cl.get(p).status_code == 200
	return gui, cl


def _timed(cl, path, out, key):
	t0 = time.perf_counter()
	r = cl.get(path)
	out[key] = (time.perf_counter() - t0, r.status_code)


def _hold(gui, seconds, started):
	with gui.priority():
		started.set()
		time.sleep(seconds)


def test_the_three_wait_for_a_detail_in_progress(env):
	gui, cl = env
	started = threading.Event()
	th = threading.Thread(target=_hold, args=(gui, 0.6, started))
	th.start()
	started.wait(5)
	out = {}
	ts = [threading.Thread(target=_timed, args=(cl, p, out, p)) for p in THREE]
	for t in ts:
		t.start()
	for t in ts:
		t.join(10)
	th.join(10)
	for p in THREE:
		dt, code = out[p]
		assert code == 200
		assert 0.45 <= dt < 0.6 + 0.5, (p, dt)            # waited for the detail, and went on when it ended
	assert gui.det_waits["n"] >= 3


def test_a_detail_that_never_ends_holds_them_at_most_the_limit(env, monkeypatch):
	gui, cl = env
	monkeypatch.setattr(S, "DETALHE_ESPERA_S", 0.3)
	started = threading.Event()
	th = threading.Thread(target=_hold, args=(gui, 3.0, started), daemon=True)
	th.start()
	started.wait(5)
	for p in THREE:
		out = {}
		_timed(cl, p, out, p)
		dt, code = out[p]
		assert code == 200
		assert 0.25 <= dt < 0.3 + 0.5, (p, dt)


def test_a_superseded_detail_409_lets_them_go_at_once(env):
	gui, cl = env
	gui._detail_seq["c"] = 5                     # a newer detail of the same tab was already asked for
	r = cl.get(REGION, headers={"X-Detail-Client": "c", "X-Detail-Seq": "1"})
	assert r.status_code == 409
	assert gui._det_n == 0
	out = {}
	_timed(cl, "/api/board", out, "b")
	assert out["b"][1] == 200 and out["b"][0] < 0.3


def test_a_failing_detail_lets_them_go_at_once(env, monkeypatch):
	gui, cl = env
	go = threading.Event()

	def broken(ppc, region=None):
		go.wait(0.4)
		raise RuntimeError("composição partida")
	monkeypatch.setattr(gui, "_compose", broken)
	cl500 = TestClient(S.create_app(gui), raise_server_exceptions=False)
	out = {}
	td = threading.Thread(target=lambda: out.__setitem__("d", cl500.get(REGION).status_code))
	td.start()
	t0 = time.perf_counter()
	while not gui._det_n and time.perf_counter() - t0 < 5:
		time.sleep(0.005)
	assert gui._det_n == 1
	tb = threading.Thread(target=_timed, args=(cl, "/api/board", out, "b"))
	tb.start()
	time.sleep(0.05)
	go.set()                                     # the detail fails now
	td.join(10)
	tb.join(10)
	assert out["d"] == 500 and gui._det_n == 0
	assert out["b"][1] == 200 and out["b"][0] < 0.4 + 0.4   # went on when the detail failed, not at the limit


def test_a_write_during_a_detail_waits_at_most_50ms_for_the_lock(env):
	gui, cl = env
	started = threading.Event()
	th = threading.Thread(target=_hold, args=(gui, 0.8, started))
	th.start()
	started.wait(5)
	out = {}
	waiting = [threading.Thread(target=_timed, args=(cl, p, out, p)) for p in THREE]
	for t in waiting:
		t.start()
	time.sleep(0.1)                              # the three are waiting for the detail now
	worst = 0.0
	for _ in range(5):
		t0 = time.perf_counter()
		with gui.wlock:
			worst = max(worst, time.perf_counter() - t0)
		time.sleep(0.02)
	for t in waiting:
		t.join(10)
	th.join(10)
	assert worst < 0.05, worst


def test_without_a_detail_nothing_waits(env):
	gui, cl = env
	t0 = time.perf_counter()
	for _ in range(1000):
		gui.after_detail()
	assert time.perf_counter() - t0 < 0.05 and gui.det_waits["n"] == 0


def test_a_region_request_counts_while_it_runs_and_not_after(env, monkeypatch):
	gui, cl = env
	seen = []
	real = gui._compose

	def spy(ppc, region=None):
		seen.append(gui._det_n)
		return real(ppc, region)
	monkeypatch.setattr(gui, "_compose", spy)
	assert cl.get(REGION).status_code == 200
	assert seen == [1] and gui._det_n == 0
	assert cl.get("/api/board.jpg?ppc=20").status_code == 200   # the full board is not a detail
	assert gui._det_n == 0
