"""Parte 1 da fase de desempenho (2026-11-15): formas lidas por folha (1a), lados erodidos em disco (1b) e a chave das
tiras (1c). Tudo sintético (``test_query._project``: 1 folha, 3 peças, uma colocada)."""
import json
import os
import threading

import numpy as np
import pytest

from src import fit as F
from src import state as ST
from src.state import Project
from test_query import _project


def _fresh_stores():
	"""Como um processo novo: nenhum SidesStore em memória."""
	with F.SidesStore._stores_lock:
		F.SidesStore._stores.clear()


def _per_piece_shape(pr, pid):
	"""A leitura de antes de 1a: o zip aberto para uma peça só."""
	from src.shape import Shape
	pre = f"{pid}__"
	with np.load(pr.p("pieces", f"{pr.piece(pid).scan_id}.npz"), allow_pickle=False) as z:
		d = {k[len(pre):]: z[k] for k in z.files if k.startswith(pre)}
	return Shape.from_arrays({k: v for k, v in d.items() if k not in ("contour_px", "mask")})


def _same_shape(a, b):
	assert a.ok == b.ok and a.cls == b.cls
	assert np.array_equal(a.c, b.c) and np.array_equal(a.corners, b.corners)
	for x, y in zip(a.sides, b.sides):
		assert x.kind == y.kind and x.chord_mm == y.chord_mm and np.array_equal(x.profile, y.profile)


def _same_sides(a, b):
	assert (a is None) == (b is None)
	if a is None:
		return
	assert len(a) == len(b) == 4
	for x, y in zip(a, b):
		assert x.kind == y.kind
		assert x.chord_mm == y.chord_mm and x.direction_deg == y.direction_deg
		assert np.array_equal(x.profile, y.profile) and x.profile.dtype == y.profile.dtype
		assert np.array_equal(np.asarray(x.p0_mm, float), np.asarray(y.p0_mm, float))
		assert np.array_equal(np.asarray(x.p1_mm, float), np.asarray(y.p1_mm, float))


def test_shapes_per_sheet_equal_per_piece_and_one_read(tmp_path, monkeypatch):
	pr, placed, tw, dec = _project(tmp_path)
	ids = sorted(pr.pieces)
	ref = {pid: _per_piece_shape(pr, pid) for pid in ids}
	pr2 = Project.open(pr.path)
	n = [0]
	real = ST.read_retry

	def counting(fn):
		n[0] += 1
		return real(fn)
	monkeypatch.setattr(ST, "read_retry", counting)
	first = pr2.shape(ids[0])
	assert n[0] == 1 and set(pr2._shape_cache) == set(ids)          # a folha inteira numa leitura
	for pid in ids:
		_same_shape(pr2.shape(pid), ref[pid])
	assert n[0] == 1
	_same_shape(first, ref[ids[0]])


def test_shapes_per_sheet_forget_during_the_read_is_not_undone(tmp_path, monkeypatch):
	"""Uma re-segmentação noutro fio (``forget_shape``) a meio da leitura da folha: a peça esquecida não volta à cache
	com os arrays velhos (a mesma regra da geração de antes, agora para todas as peças da folha)."""
	pr, placed, tw, dec = _project(tmp_path)
	pr2 = Project.open(pr.path)
	real = ST.read_retry
	started, go = threading.Event(), threading.Event()

	def slow(fn):
		started.set()
		go.wait(10)
		return real(fn)
	monkeypatch.setattr(ST, "read_retry", slow)
	out = {}
	th = threading.Thread(target=lambda: out.setdefault("sh", pr2.shape(placed)))
	th.start()
	assert started.wait(10)
	pr2.forget_shape(dec)                                             # a meio da leitura
	go.set()
	th.join(10)
	assert out["sh"] is not None and out["sh"].ok
	assert placed in pr2._shape_cache and tw in pr2._shape_cache
	assert dec not in pr2._shape_cache                                # não guardada: a geração mudou
	monkeypatch.setattr(ST, "read_retry", real)
	_same_shape(pr2.shape(dec), _per_piece_shape(pr, dec))            # a próxima leitura volta a ler


def test_eroded_sides_from_disk_equal_computed(tmp_path):
	pr, placed, tw, dec = _project(tmp_path)
	_fresh_stores()
	cal = F.calibration(pr)
	c1 = F._Cache(pr, cal)
	got = {pid: c1.eroded(pid) for pid in sorted(pr.pieces)}
	assert c1.store.n_computed == 3 and c1.store.n_disk == 0
	c1.save()
	assert os.path.exists(pr.p("render", "fit", "sides.npz"))
	for pid, sds in got.items():                                       # o que se calculava antes de 1b
		sh = pr.shape(pid)
		_same_sides(sds, F.eroded_sides(sh, cal.erosion_mm) or list(sh.sides))
	_fresh_stores()
	pr2 = Project.open(pr.path)
	c2 = F._Cache(pr2, cal)
	for pid, sds in got.items():
		_same_sides(c2.eroded(pid), sds)
	assert c2.store.n_computed == 0 and c2.store.n_disk == 3
	# partilhados: outro _Cache do mesmo projeto (o «verificar», a reconsulta) não recalcula
	c3 = F._Cache(pr2, cal)
	_same_sides(c3.eroded(tw), got[tw])
	assert c3.store is c2.store and c2.store.n_computed == 0


def test_eroded_sides_recomputed_when_the_shape_or_the_erosion_changes(tmp_path):
	pr, placed, tw, dec = _project(tmp_path)
	_fresh_stores()
	cal = F.calibration(pr)
	c = F._Cache(pr, cal)
	a = c.eroded(tw)
	c.save()
	n0 = c.store.n_computed
	# outra silhueta com a mesma bbox (um contorno manual): chave nova
	sh = pr.shape(tw)
	import copy
	sh2 = copy.deepcopy(sh)
	sh2.c = sh.c * 1.001
	assert F.side_key(sh2, cal.erosion_mm, c.profile_sha) != F.side_key(sh, cal.erosion_mm, c.profile_sha)
	pr._shape_cache[tw] = sh2
	c.eroded(tw)
	assert c.store.n_computed == n0 + 1
	# outra erosão (calibração): chave nova
	pr._shape_cache[tw] = sh
	cal2 = F.FitCalibration(**{**cal.__dict__, "erosion_mm": cal.erosion_mm + 0.1})
	c2 = F._Cache(pr, cal2)
	b = c2.eroded(tw)
	assert c.store.n_computed == n0 + 2
	assert b[0].chord_mm != a[0].chord_mm


def test_rank_all_cold_from_disk_equals_computed(tmp_path):
	pr, placed, tw, dec = _project(tmp_path)
	_fresh_stores()
	r1 = F.rank_all(pr)
	assert "error" not in r1, r1
	_fresh_stores()
	pr2 = Project.open(pr.path)
	c = F._Cache(pr2, F.calibration(pr2))
	r2 = F.rank_all(pr2, cache=c)
	assert c.store.n_computed == 0 and c.store.n_disk > 0
	assert r2["tiras"]["calculadas"] == 0
	for r in (r1, r2):
		r.pop("tiras")
	assert json.dumps(r1, sort_keys=True, default=str) == json.dumps(r2, sort_keys=True, default=str)


def test_strip_key_follows_the_crop_not_only_the_bbox(tmp_path):
	pr, placed, tw, dec = _project(tmp_path)
	_fresh_stores()
	cal = F.calibration(pr)
	c = F._Cache(pr, cal)
	s0 = c.strip(tw)
	c.save()
	assert F._Cache(pr, cal).n_loaded == 1
	# a crop rewritten in place with the same bbox (a corrected cut): the stored strips no longer count
	fp = pr.p(pr.piece(tw).crop_path)
	from PIL import Image
	with Image.open(fp) as im:
		a = np.asarray(im).copy()
	a[..., 0] = 255 - a[..., 0]
	Image.fromarray(a).save(fp)
	st = os.stat(fp)
	os.utime(fp, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
	c2 = F._Cache(pr, cal)
	assert c2.n_loaded == 0 and tw not in c2.strips
	s1 = c2.strip(tw)
	assert not np.array_equal(np.nan_to_num(s0), np.nan_to_num(s1))
	# the same _Cache bound to a reopened project drops it too (rebind by key, not by bbox)
	c.rebind(Project.open(pr.path))
	assert tw not in c.strips


def _old_format(pr, pid, bbox, value):
	os.makedirs(pr.p("render", "fit"), exist_ok=True)
	fp = pr.p("render", "fit", "strips.npz")
	np.savez_compressed(fp, **{pid: value, f"bbox__{pid}": np.asarray(bbox, int)})
	return fp


def test_strips_old_format_kept_once_only_when_bbox_and_crop_age_agree(tmp_path):
	"""The format before 1c (id + bbox): kept and converted when the bbox matches and the crop is not newer than the
	file (no re-measure of every strip after the upgrade); a crop rewritten after it, or another bbox, is measured
	again."""
	pr, placed, tw, dec = _project(tmp_path)
	p = pr.piece(tw)
	v = np.full((4, F.N_STRIP, 3), 7.0, np.float32)
	fp = _old_format(pr, tw, p.bbox, v)
	cp = pr.p(p.crop_path)
	st = os.stat(fp)
	os.utime(cp, ns=(st.st_atime_ns, st.st_mtime_ns - 10_000_000_000))       # crop older than the strips file
	c = F._Cache(pr, F.calibration(pr))
	assert c.n_loaded == 1 and np.array_equal(c.strip(tw), v) and c.dirty
	c.save()                                                                   # rewritten in the new format
	assert F._Cache(pr, F.calibration(pr)).n_loaded == 1
	# crop newer than the strips file: measured again
	fp = _old_format(pr, tw, p.bbox, v)
	st = os.stat(fp)
	os.utime(cp, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000_000))
	assert F._Cache(pr, F.calibration(pr)).n_loaded == 0
	# another bbox: measured again
	fp = _old_format(pr, tw, [b + 1 for b in p.bbox], v)
	st = os.stat(fp)
	os.utime(cp, ns=(st.st_atime_ns, st.st_mtime_ns - 10_000_000_000))
	assert F._Cache(pr, F.calibration(pr)).n_loaded == 0


def test_sides_todo_counts_pieces_without_sides(tmp_path):
	pr, placed, tw, dec = _project(tmp_path)
	_fresh_stores()
	c = F._Cache(pr, F.calibration(pr))
	todo = c.sides_todo()
	assert set(todo) == set(c.involved()) and tw in todo
	for pid in todo:
		c.eroded(pid)
	assert c.sides_todo() == []
