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


# ---------------------------------------------------------------- parte 1: formas por folha, lados erodidos, tiras
def _fresh_fit_stores():
	from src import fit as F
	with F.SidesStore._stores_lock:
		F.SidesStore._stores.clear()


def _sides_eq(a, b):
	if a is None or b is None:
		return a is b
	return all(x.kind == y.kind and x.chord_mm == y.chord_mm and np.array_equal(x.profile, y.profile)
			   and np.array_equal(np.asarray(x.p0_mm, float), np.asarray(y.p0_mm, float)) for x, y in zip(a, b))


def test_shapes_sides_strips_follow_the_corrected_crop(env):
	from src import fit as F
	gui, cl, placed, tw, dec = env
	_fresh_fit_stores()
	cal = F.calibration(gui.pr)
	c = F._Cache(gui.pr, cal)
	for pid in (placed, tw, dec):                       # warm: shapes, sides (saved to disk), strips
		c.eroded(pid)
		c.strip(pid)
	c.save()
	old_sides, old_strip, old_shape = c.eroded(dec), c.strip(dec), gui.pr.shape(dec)
	n0 = c.store.n_computed
	_correct(cl, dec)
	gui.sync()
	c.rebind(gui.pr)
	sh = gui.pr.shape(dec)
	assert not np.array_equal(sh.c, old_shape.c)                       # the shape of the new crop
	new_sides = c.eroded(dec)
	assert c.store.n_computed == n0 + 1                                 # only this piece recomputed
	assert not _sides_eq(new_sides, old_sides)
	assert dec not in c.strips or c.keys[dec] == F.strip_key(gui.pr, dec)
	new_strip = c.strip(dec)
	for pid in (placed, tw):                                            # the others: no new computation
		c.eroded(pid)
	assert c.store.n_computed == n0 + 1
	c.save()
	# = a process just opened (stores empty, shapes and strips read from the disk / computed anew)
	_fresh_fit_stores()
	pr2 = Project.open(gui.path)
	c2 = F._Cache(pr2, cal)
	assert np.array_equal(pr2.shape(dec).c, sh.c)
	assert _sides_eq(c2.eroded(dec), new_sides) and c2.store.n_computed == 0
	assert np.array_equal(np.nan_to_num(c2.strip(dec)), np.nan_to_num(new_strip))


def test_calibration_change_recomputes_sides_and_strips(env):
	from src import fit as F
	gui, cl, placed, tw, dec = env
	_fresh_fit_stores()
	c = F._Cache(gui.pr, F.calibration(gui.pr))
	a = c.eroded(dec)
	c.strip(dec)
	c.save()
	fp = gui.pr.p("puzzle.json")
	d = json.load(open(fp, encoding="utf-8"))
	d.setdefault("calibration", {}).setdefault("buraco", {})["erosion_mm"] = 0.9
	with open(fp, "w", encoding="utf-8") as f:
		json.dump(d, f, ensure_ascii=False, indent=2)
	gui.sync()
	pr2 = Project.open(gui.path)
	cal2 = F.calibration(pr2)
	assert cal2.erosion_mm == 0.9
	c2 = F._Cache(pr2, cal2)
	assert c2.n_loaded == 0                                             # the profile is in the strip key
	n0 = c2.store.n_computed
	b = c2.eroded(dec)
	assert c2.store.n_computed == n0 + 1 and not _sides_eq(a, b)


# ---------------------------------------------------------------- E: peças prontas a desenhar (ReadyCache)
def test_ready_cache_follows_the_corrected_crop(env):
	gui, cl, placed, tw, dec = env
	gui.board_jpg(120, (1, 1, 4, 6))                        # warm: the three pieces made ready
	assert all(gui.ready.has(gui.pr, pid) for pid in (placed, tw))
	ent_tw = gui.ready.d[tw]
	n0 = gui.ready.misses
	_correct(cl, placed)
	gui.sync()
	assert placed not in gui.ready.d                         # forgotten by the contour save
	data = gui.board_jpg(120, (1, 1, 4, 6))
	assert gui.ready.d[tw] is ent_tw                         # the others were not recomputed
	assert gui.ready.misses == n0 + 1
	fresh = S.Gui(gui.path, prepare=False, use_image=False, uploads=gui.uploads, log=None, queue=False)
	assert data == fresh.board_jpg(120, (1, 1, 4, 6))
