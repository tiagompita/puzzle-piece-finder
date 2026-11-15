"""E da fase de desempenho (2026-11-15): peças prontas a desenhar em memória (``render.piece_ready`` +
``server.ReadyCache``). A composição com a cache é a mesma, byte a byte, que sem ela; o orçamento é respeitado (com
expulsões contínuas a saída não muda); a chave segue o recorte e a calibração."""
import json
import threading

import numpy as np
import pytest

from src import render
from src import server as S
from src.state import Project
from test_query import _project

REGIONS = [None, (1, 1, 4, 6), (2, 2, 3, 4), (1, 3, 3, 5)]


@pytest.fixture
def proj(tmp_path):
	from src.query import run_query
	pr, placed, tw, dec = _project(tmp_path)
	pr.place(tw, (3, 4))
	pr.place(dec, (1, 1))
	pr.save()
	run_query(pr, use_image=False)
	return Project.open(pr.path), placed, tw, dec


@pytest.mark.parametrize("ppc", [60, 120, 217])
def test_compose_with_ready_equals_without(proj, ppc):
	pr, placed, tw, dec = proj
	rc = S.ReadyCache(600)
	for reg in REGIONS:
		a = render.compose_board(pr, ppc, region=reg, layers=("art", "pieces"))
		b = render.compose_board(pr, ppc, region=reg, layers=("art", "pieces"), ready=lambda pid: rc.get(pr, pid))
		c = render.compose_board(pr, ppc, region=reg, layers=("art", "pieces"), ready=lambda pid: rc.get(pr, pid))
		assert a.tobytes() == b.tobytes() == c.tobytes(), reg
	st = rc.stats()
	assert st["pecas"] == 3 and st["acertos"] > 0


def test_tiny_budget_evicts_and_output_is_the_same(proj):
	pr, placed, tw, dec = proj
	one = render.ready_nbytes(render.piece_ready(pr, placed))
	rc = S.ReadyCache(1.5 * one / 2**20)                 # room for about one piece: evictions all the time
	ref = render.compose_board(pr, 120, layers=("art", "pieces"))
	for _ in range(3):
		got = render.compose_board(pr, 120, layers=("art", "pieces"), ready=lambda pid: rc.get(pr, pid))
		assert got.tobytes() == ref.tobytes()
		assert rc.nbytes <= rc.budget
	assert rc.evictions > 0
	z = S.ReadyCache(0)                                  # no cache at all
	assert render.compose_board(pr, 120, layers=("art", "pieces"), ready=lambda pid: z.get(pr, pid)).tobytes() == ref.tobytes()
	assert z.nbytes == 0


def test_ready_arrays_are_read_only_and_shared_by_threads(proj):
	pr, placed, tw, dec = proj
	rc = S.ReadyCache(600)
	rd = rc.get(pr, placed)
	with pytest.raises(ValueError):
		rd[0][0, 0, 0] = 1
	out, errs = [], []

	def go():
		try:
			out.append(rc.get(pr, tw))
		except Exception as e:  # noqa: BLE001
			errs.append(e)
	th = [threading.Thread(target=go) for _ in range(6)]
	for t in th:
		t.start()
	for t in th:
		t.join()
	assert not errs and all(x is out[0] for x in out)
	assert rc.misses == 2                                 # one computation per piece, the others waited for it


def test_key_follows_the_crop_and_the_calibration(proj):
	pr, placed, tw, dec = proj
	rc = S.ReadyCache(600)
	k0 = rc.key(pr, dec)
	rc.get(pr, dec)
	assert rc.has(pr, dec)
	# the crop file rewritten (same bytes, new mtime): another key, computed again
	fp = pr.p(pr.piece(dec).crop_path)
	import os
	st = os.stat(fp)
	os.utime(fp, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
	assert rc.key(pr, dec) != k0 and not rc.has(pr, dec)
	# the profile (background / calibration) changed: another key
	k1 = rc.key(pr, dec)
	pp = pr.p("puzzle.json")
	d = json.load(open(pp, encoding="utf-8"))
	d.setdefault("calibration", {})["nota_teste"] = 1
	with open(pp, "w", encoding="utf-8") as f:
		json.dump(d, f)
	assert rc.key(Project.open(pr.path), dec) != k1
