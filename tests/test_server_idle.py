"""The SSE stream costs nothing while idle (events delivered by :meth:`src.server.Gui.emit` waking the client, no
polling) and an event reaches a connected client in well under a second.

A real uvicorn server in a thread (as tests/test_gui_atividade.py), one real SSE client reading the stream in another
thread; ``time.process_time()`` of the whole test process over 10 s without requests must stay below 0.15 s
(≈ 1.5 % of one core, with room for the reader itself and uvicorn's own 0.1 s tick), and the generator must not wake
up at all (``events_after`` not called: the old loop polled every 0.4 s, 25 calls in 10 s). Measured on this
synthetic project (2026-11-08, Windows, ``process_time`` granularity 15.6 ms): old loop 0.078 s / 10 s with 1 or 3
clients, the new one 0.031 s (0.047 s with none)."""

import http.client
import os
import socket
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
pytest.importorskip("fastapi")
uvicorn = pytest.importorskip("uvicorn")

from src import server as S  # noqa: E402
from test_consistency import _row_project  # noqa: E402

IDLE_S = 10.0
IDLE_CPU_MAX_S = 0.15
IDLE_CPU_MAX_S_SHARED = 1.0   # when the pytest process still has threads of earlier server tests (suite run), the CPU bound is loose; the wake count is the hard check


@pytest.fixture
def served(tmp_path):
	pr, ids = _row_project(tmp_path)
	gui = S.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "uploads"), log=None)
	s = socket.socket()
	s.bind(("127.0.0.1", 0))
	port = s.getsockname()[1]
	s.close()
	server = uvicorn.Server(uvicorn.Config(S.create_app(gui), host="127.0.0.1", port=port, log_level="warning"))
	th = threading.Thread(target=server.run, daemon=True)
	th.start()
	t0 = time.time()
	while not server.started and time.time() - t0 < 30:
		time.sleep(0.05)
	yield gui, port
	server.should_exit = True
	th.join(10)
	gui.stop()


class _Reader(threading.Thread):
	"""Reads the SSE stream line by line; keeps ``(time, event name)`` of every event."""

	def __init__(self, port):
		super().__init__(daemon=True)
		self.port = port
		self.events = []
		self.lines = 0
		self.connected = threading.Event()

	def run(self):
		c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
		c.request("GET", "/api/events", headers={"Accept": "text/event-stream"})
		r = c.getresponse()
		self.connected.set()
		name = None
		while True:
			try:
				line = r.fp.readline()
			except Exception:  # noqa: BLE001 - server closed
				return
			if not line:
				return
			self.lines += 1
			line = line.decode("utf-8").rstrip("\r\n")
			if line.startswith("event:"):
				name = line[6:].strip()
			elif line == "" and name:
				self.events.append((time.perf_counter(), name))
				name = None


def test_idle_sse_costs_no_cpu_and_events_arrive_fast(served):
	gui, port = served
	rd = _Reader(port)
	rd.start()
	assert rd.connected.wait(10)
	t0 = time.time()
	while not any(n == "hello" for _, n in rd.events) and time.time() - t0 < 10:
		time.sleep(0.05)
	assert any(n == "hello" for _, n in rd.events)
	time.sleep(1.0)                                   # let the start-up settle
	calls = []
	orig = gui.events_after
	gui.events_after = lambda n: (calls.append(n), orig(n))[1]
	lines0 = rd.lines
	c0 = time.process_time()
	time.sleep(IDLE_S)
	cpu = time.process_time() - c0
	import threading
	shared = threading.active_count() > 6                  # other servers / hole threads of the same pytest process
	assert cpu < (IDLE_CPU_MAX_S_SHARED if shared else IDLE_CPU_MAX_S), f"{cpu:.3f} s de CPU em {IDLE_S:g} s sem pedidos (threads ativas {threading.active_count()})"
	assert rd.lines - lines0 <= 2                     # at most a keep-alive comment, no polling traffic
	assert len(calls) <= 1, f"o gerador acordou {len(calls)} vezes sem eventos (polling)"   # the old 0.4 s loop: 25
	# an event emitted from another thread arrives in well under a second
	for k in range(3):
		n0 = len(rd.events)
		t_emit = time.perf_counter()
		threading.Thread(target=gui.emit, args=("x", {"k": k})).start()
		while len(rd.events) == n0 and time.perf_counter() - t_emit < 5:
			time.sleep(0.005)
		assert len(rd.events) > n0 and rd.events[-1][1] == "x"
		assert rd.events[-1][0] - t_emit < 1.0, f"evento chegou em {rd.events[-1][0] - t_emit:.3f} s"
	assert len(gui._sse_waiters) == 1
