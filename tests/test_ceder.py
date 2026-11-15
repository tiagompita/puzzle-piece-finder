"""(b) da fase de desempenho (2026-11-15, decisão do Tiago): o trabalho de fundo cede à interação.

Enquanto um pedido de detalhe (região do ``board.jpg``) ou um «verificar» corre, o ranking dos buracos, as suspeitas
calculadas depois de uma escrita e o pré-aquecimento das peças esperam (``Gui.foreground`` / ``Gui.yield_to_gui``) e
retomam onde estavam. O resultado é o mesmo, só mais tarde: com cedências forçadas = sem cedências."""
import json
import random
import threading
import time

import pytest

from src import consistency as CO
from src import fit as F
from src import server as S
from src.state import Project
from test_query import _project


def _dump(x):
	return json.dumps(x, sort_keys=True, default=str)


@pytest.fixture
def proj(tmp_path):
	from src.query import run_query
	pr, placed, tw, dec = _project(tmp_path)
	pr.place(tw, (3, 4))
	pr.save()
	run_query(pr, use_image=False)
	return pr, placed, tw, dec


def _jittery(seed=0):
	"""A pause that blocks for a random moment and lets other threads run (a forced yield)."""
	rnd = random.Random(seed)
	n = [0]

	def pause():
		n[0] += 1
		time.sleep(rnd.choice((0.0, 0.0, 0.001, 0.003)))
	return pause, n


def test_rank_all_with_forced_yields_equals_without(proj):
	pr, placed, tw, dec = proj
	ref = F.rank_all(Project.open(pr.path))
	pause, n = _jittery(1)
	got = F.rank_all(Project.open(pr.path), pause=pause)
	assert n[0] > 0
	for r in (ref, got):
		r.pop("tiras", None)
	assert _dump(ref) == _dump(got)


def test_evaluate_with_forced_yields_equals_without(proj):
	pr, placed, tw, dec = proj
	ref = CO.evaluate(pr, {})
	pause, n = _jittery(2)
	got = CO.evaluate(Project.open(pr.path), {}, pause=pause)
	assert n[0] > 0 and _dump(ref) == _dump(got)


def _gui(pr):
	return S.Gui(pr.path, prepare=False, use_image=False, log=None, queue=False)


def test_holes_wait_while_the_gui_waits_and_end_the_same(proj):
	pr, placed, tw, dec = proj
	gui = _gui(pr)
	with gui.foreground():                       # a detail region / «verificar» in progress
		gui.holes_json(wait=False)
		time.sleep(0.5)
		assert gui._holes_thread.is_alive()      # the ranking waits at its first piece
		assert gui.yields["n"] >= 0
	gui._holes_thread.join(30)
	got = gui.holes_json(wait=False)
	assert not got.get("a_calcular")
	ref = _gui(pr).holes_json(wait=True)
	for r in (got, ref):
		r["resumo"].pop("segundos", None)
	assert _dump(got["buracos"]) == _dump(ref["buracos"]) and _dump(got["resumo"]) == _dump(ref["resumo"])
	assert gui.yields["n"] >= 1 and gui.yields["s"] >= 0.4


def test_suspects_after_a_write_wait_while_the_gui_waits(proj):
	pr, placed, tw, dec = proj
	gui = _gui(pr)
	seen = []
	real = gui.emit

	def emit(name, data=None):
		if name == "suspeitas_changed":
			seen.append(time.perf_counter())
		real(name, data)
	gui.emit = emit
	with gui.foreground():
		t0 = time.perf_counter()
		gui._suspeitas_bg()
		time.sleep(0.4)
		assert not seen                          # yields while the GUI waits
	gui.wait_suspeitas()
	assert seen and seen[0] - t0 >= 0.35
	assert _dump(gui.suspeitas_json()) == _dump(_gui(pr).suspeitas_json())


def test_yield_returns_at_once_without_gui_requests(proj):
	pr, placed, tw, dec = proj
	gui = _gui(pr)
	t0 = time.perf_counter()
	for _ in range(1000):
		gui.yield_to_gui()
	assert time.perf_counter() - t0 < 0.05 and gui.yields["n"] == 0


def test_foreground_counts_nested_and_wakes_once_free(proj):
	pr, placed, tw, dec = proj
	gui = _gui(pr)
	done = threading.Event()

	def bg():
		gui.yield_to_gui()
		done.set()
	with gui.foreground():
		with gui.foreground():
			th = threading.Thread(target=bg)
			th.start()
			time.sleep(0.1)
			assert not done.is_set()
		time.sleep(0.1)
		assert not done.is_set()                 # still one request in progress
	assert done.wait(5)
