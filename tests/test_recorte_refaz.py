"""Corrigir o recorte de uma peça refaz o que dela depende (plano da fase de desempenho, P5; 2026-11-15).

Cada cache nova da fase tem a sua chave no recorte da peça (e na calibração quando a usa). Aqui, num projeto sintético:
aquecer as caches, corrigir o contorno de uma peça pelo editor (``POST /api/pieces/{id}/contorno``) e verificar, por
cache, que a entrada da peça muda (não fica a velha), que fica igual à de um processo novo, e que as das outras peças
não são recalculadas. P0b: recortes decodificados (``Project.crop_rgba``, A2), assinatura das folhas ``fetch_*.jpg``
(A3), resíduo local contra a gémea (``consistency``, A4) e as vistas JSON (``Project.save``, A1). As caches da parte 1,
de E e de C acrescentam-se aqui quando entram."""
import json

import numpy as np
import pytest

from fastapi.testclient import TestClient  # noqa: E402

from src import consistency as CO  # noqa: E402
from src import query as Q  # noqa: E402
from src import render  # noqa: E402
from src import server as S  # noqa: E402
from src.state import Project  # noqa: E402
from test_query import _project  # noqa: E402
from test_server import _editor_contour  # noqa: E402


@pytest.fixture
def env(tmp_path):
	from src.query import run_query
	pr, placed, tw, dec = _project(tmp_path)
	run_query(pr, use_image=False)
	gui = S.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "up"), log=None, queue=False)
	cl = TestClient(S.create_app(gui))
	r = cl.post("/api/confirm", json={"acao": "place", "piece": tw, "cell": [3, 4]})     # the twin of ``placed``
	assert r.status_code == 200, r.text
	gui.wait_suspeitas()
	yield gui, cl, placed, tw, dec


def _correct(cl, pid, dx=5.0):
	d = cl.get(f"/api/pieces/{pid}/contorno").json()
	c = _editor_contour(d, dx=dx)
	r = cl.post(f"/api/pieces/{pid}/contorno", json={"contour": c, "origem": d["origem"], "tamanho": d["tamanho"]})
	assert r.status_code == 200, r.text


def test_crop_cache_follows_the_corrected_crop(env):
	gui, cl, placed, tw, dec = env
	pr = gui.pr
	before = {pid: pr.crop_rgba(pid) for pid in (placed, tw, dec)}
	ent_tw = pr._crop_cache[pr.p(pr.piece(tw).crop_path)]
	_correct(cl, placed)
	gui.sync()
	pr = gui.pr
	fresh = Project.open(pr.path)
	got = pr.crop_rgba(placed)
	assert np.array_equal(got, fresh.crop_rgba(placed))
	assert not (got.shape == before[placed].shape and np.array_equal(got, before[placed]))   # not the old crop
	# the other pieces: their entries were not re-read (the same cached arrays)
	assert pr._crop_cache[pr.p(pr.piece(tw).crop_path)] is ent_tw
	assert np.array_equal(pr.crop_rgba(tw), before[tw]) and np.array_equal(pr.crop_rgba(dec), before[dec])


def test_crop_cache_returns_copies(env):
	gui, cl, placed, tw, dec = env
	a = gui.pr.crop_rgba(dec)
	a[...] = 0
	assert gui.pr.crop_rgba(dec).any()


def test_twin_residual_cache_follows_the_shape_and_the_threshold(env, monkeypatch):
	gui, cl, placed, tw, dec = env
	pl = dict(gui.placements())
	CO.evaluate(gui.pr, dict(pl))
	sh_tw = gui.pr.shape(tw)
	key_tw = CO._shape_key(sh_tw)
	_correct(cl, tw)                                   # the twin's silhouette changes: a new key for both pairs
	gui.sync()
	assert CO._shape_key(gui.pr.shape(tw)) != key_tw
	r1 = CO.evaluate(gui.pr, dict(gui.placements()))
	CO._RESIDUAL_CACHE.clear()                         # a new process
	r2 = CO.evaluate(Project.open(gui.path), dict(gui.placements()))
	assert json.dumps(r1, sort_keys=True, default=str) == json.dumps(r2, sort_keys=True, default=str)
	# the calibration (threshold) is applied after the cache: changing it changes the result at once
	monkeypatch.setattr(CO, "TWIN_LOCAL_MAX_MM", 0.0)
	r3 = CO._recorte_items(gui.pr, [placed])
	CO._RESIDUAL_CACHE.clear()
	assert r3 == CO._recorte_items(gui.pr, [placed])


def test_twin_residual_cached_equals_direct(env):
	gui, cl, placed, tw, dec = env
	a, b = gui.pr.shape(placed), gui.pr.shape(tw)
	CO._RESIDUAL_CACHE.clear()
	r = CO.twin_local_residual_cached(a, b)
	assert r == CO.twin_local_residual(a, b) == CO.twin_local_residual_cached(a, b)
	assert len(CO._RESIDUAL_CACHE) == 1


def test_fetch_sheet_signature_follows_the_crop(env):
	gui, cl, placed, tw, dec = env
	pr = gui.pr
	rows = [{"piece": dec, "twin_id": None, "ordem": 1, "lote": 3, "n_no_lote": 3, "cell": [1, 1], "origin": "x",
			 "decision": "ambigua", "theta_deg": 0.0, "pose_known": True}]
	s0 = Q._sheet_sig(pr, 3, rows)
	assert Q._sheet_sig(pr, 3, rows) == s0
	_correct(cl, dec)
	gui.sync()
	assert Q._sheet_sig(gui.pr, 3, rows) != s0


def test_json_views_skipped_only_when_unchanged(env):
	gui, cl, placed, tw, dec = env
	_correct(cl, dec)                                  # changes scans/<sid>.json (the piece's record)
	gui.sync()
	pr = gui.pr
	files = {}
	import glob
	import os
	for fp in glob.glob(pr.p("scans", "*.json")) + [pr.p("board.json"), pr.p("pairs.json"), pr.p("project.json")]:
		with open(fp, "rb") as f:
			files[fp] = f.read()
	fresh = Project.open(pr.path)
	fresh.save()                                       # a new process writes every view: the bytes are the same
	for fp, b in files.items():
		with open(fp, "rb") as f:
			assert f.read() == b, os.path.basename(fp)
