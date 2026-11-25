"""P-b (2026-11-15, decisão do Tiago; DETALHE.md §13.8–§13.9): ``render/placements.json`` completo e sem voltar a perder.

O diagnóstico (§13.8) mostrou 620 de 699 peças colocadas sem entrada: o ficheiro antigo (sem ``f_rotation``) passou a ser
ignorado e nunca foi refeito, e um contorno re-segmentado tirava a entrada sem a repor. Agora:

- o servidor, no arranque e em fundo, completa as entradas em falta ou desatualizadas (cálculo fora do bloqueio, só o
  commit sob o bloqueio de escrita; uma entrada que uma escrita tornou velha entretanto não é gravada);
- ``rebuild_piece`` / ``rebuild_stale`` voltam a registar as peças colocadas que re-segmentam;
- a regra de registo (``render.REGISTER_IMAGE``, decidida pelas juntas, §13.9) entra na chave da entrada: uma entrada
  feita com a outra regra é refeita;
- verificação permanente: uma peça colocada sem entrada dá um aviso no arranque, uma linha em ``/api/status`` e uma
  conta em ``render.stale_assets``.
"""
import json
import os
import threading
import time

import numpy as np
from fastapi.testclient import TestClient

from src import overrides as OV
from src import render as R
from src import server as S
from src.state import Project
from test_regiao_remendo import CONTORNO, _grid_project
from test_render import _ingested, _shrink_npz_contour
from test_server import _editor_contour

CELLS = [(1, 1), (1, 2), (2, 1)]


def _placed_ingested(tmp_path):
	"""The 3 rectangles of ``test_render._ingested`` placed in a 4 × 6 board, assets coherent (only the start-up checks
	run), no ``render/placements.json``."""
	pr, sid = _ingested(tmp_path)
	for pid, cell in zip(sorted(pr.pieces), CELLS):
		pr.place(pid, cell, theta_deg=0.0)
	pr.save()
	os.makedirs(pr.p("render", "gui"), exist_ok=True)
	fp = pr.p("render", "placements.json")
	if os.path.exists(fp):
		os.remove(fp)
	return pr, sid


def _raw(pr):
	fp = pr.p("render", "placements.json")
	if not os.path.exists(fp):
		return {}
	with open(fp, encoding="utf-8") as f:
		return json.load(f)


def _valid(pr):
	"""Placed pieces with an entry that the server accepts (key and manual pose)."""
	pr = Project.open(pr.path)
	pl = R.load_placements(pr)["placements"]
	return {pid for pid in R.placed_ids(pr) if pid in pl and pl[pid].get("key") == R._entry_key(pr, pid)
			and R._manual_entry_ok(pr, pid, pl[pid])}


def _same_pose(a, b, tol=1e-6):
	"""Same pose up to float noise (a shape read back from the npz moves the body centre by ~1e-13 mm)."""
	return (abs(float(a["theta_deg"]) - float(b["theta_deg"])) < tol and abs(float(a["dx_mm"]) - float(b["dx_mm"])) < tol
			and abs(float(a["dy_mm"]) - float(b["dy_mm"])) < tol
			and np.allclose(np.asarray(a["pivot_mm"], float), np.asarray(b["pivot_mm"], float), atol=tol))


def _not_stale(pr):
	"""Every placed piece has an entry equal to what the registration gives now (no stale pose kept)."""
	pr = Project.open(pr.path)
	pl = R.load_placements(pr)["placements"]
	bad = []
	for pid in R.placed_ids(pr):
		now = R.register_piece(pr, pid, art=None, image=False)
		if pid not in pl or not _same_pose(pl[pid], now):
			bad.append(pid)
	return bad


def _start(path):
	g = S.Gui(path, prepare=True, use_image=False, log=None, queue=False)
	t0 = time.time()
	while not any(n == "ready" for _, n, _ in g.events_after(0)) and time.time() - t0 < 60:
		time.sleep(0.1)
	_wait_fill(g, path)
	return g


def _wait_fill(g, path, n_s=15.0):
	if hasattr(g, "wait_placements"):
		g.wait_placements(60)
		return
	t0 = time.time()                       # code without the fill: give it a fair chance, then the asserts fail
	while time.time() - t0 < n_s:
		pr = Project.open(path)
		if R.placed_ids(pr) and _valid(pr) == set(R.placed_ids(pr)):
			return
		time.sleep(0.2)


# ---------------------------------------------------------------- 1. start-up fills
def test_arranque_completa_as_entradas_em_falta(tmp_path):
	pr, _ = _placed_ingested(tmp_path)
	pl0 = R.register_piece(pr, sorted(pr.pieces)[0], art=None, image=False)
	assert "error" not in pl0
	g = _start(pr.path)
	try:
		assert _valid(pr) == set(R.placed_ids(Project.open(pr.path)))
		assert _not_stale(pr) == []
	finally:
		g.stop()


# ---------------------------------------------------------------- 2. manual contour of a placed piece
def test_contorno_manual_numa_colocada_mantem_a_entrada(tmp_path):
	pr, cell_of, _, _ = _grid_project(tmp_path)
	R.register_all(pr, image=False, progress=None, relax_pass=False)
	assert _valid(pr) == set(R.placed_ids(pr))
	pid = cell_of[(2, 3)]
	p = pr.piece(pid)
	with np.load(pr.p("pieces", f"{p.scan_id}.npz")) as z:
		c = np.asarray(z[f"{pid}__contour_px"], float).reshape(-1, 2)
	m = c.mean(0)
	rec = OV.append_override(pr, pid, (m + (c - m) * 0.97).tolist(), nota="P-b teste")
	assert "error" not in rec
	r = R.rebuild_piece(pr, pid, progress=None)
	assert not r.get("errors") and [x["piece"] for x in r["changed"]] == [pid]
	assert pid in _valid(pr)
	assert _not_stale(pr) == []


def test_contorno_manual_pela_gui_mantem_a_entrada(tmp_path):
	pr, cell_of, _, _ = _grid_project(tmp_path)
	R.register_all(pr, image=False, progress=None, relax_pass=False)
	gui = S.Gui(pr.path, prepare=False, use_image=False, log=None, queue=False)
	try:
		cl = TestClient(S.create_app(gui))
		pid = cell_of[CONTORNO]
		d = cl.get(f"/api/pieces/{pid}/contorno").json()
		r = cl.post(f"/api/pieces/{pid}/contorno", json={"contour": _editor_contour(d, dx=8.0), "origem": d["origem"],
														   "tamanho": d["tamanho"]})
		assert r.status_code == 200 and r.json().get("ok"), r.text
		gui.wait_suspeitas()
		assert pid in _valid(pr)
		assert _not_stale(pr) == []
	finally:
		gui.stop()


# ---------------------------------------------------------------- 3. rebuild_stale
def test_rebuild_stale_mantem_as_entradas_das_colocadas(tmp_path):
	pr, sid = _placed_ingested(tmp_path)
	R.register_all(pr, image=False, progress=None, relax_pass=False)
	assert _valid(pr) == set(R.placed_ids(pr))
	pid = sorted(pr.pieces)[1]
	_shrink_npz_contour(pr, sid, pid)
	pr = Project.open(pr.path)
	r = R.rebuild_stale(pr, progress=None)
	assert r["errors"] == [] and r["depois"]["n_pecas"] == 0
	assert _valid(pr) == set(R.placed_ids(pr))
	assert _not_stale(pr) == []


# ---------------------------------------------------------------- 4. manual pose
def test_pose_manual_preservada_no_preenchimento(tmp_path):
	pr, _ = _placed_ingested(tmp_path)
	pid = sorted(pr.pieces)[0]
	pr.set_pose(pid, 2.5, 0.3, -0.2, nota="teste")
	pr.save()
	g = _start(pr.path)
	try:
		pl = R.load_placements(Project.open(pr.path))["placements"]
		assert pid in pl and pl[pid].get("manual") is True
		assert abs(pl[pid]["theta_deg"] - 2.5) < 1e-9 and abs(pl[pid]["dx_mm"] - 0.3) < 1e-9
		assert abs(pl[pid]["dy_mm"] + 0.2) < 1e-9
		assert _valid(pr) == set(R.placed_ids(Project.open(pr.path)))
	finally:
		g.stop()


# ---------------------------------------------------------------- 5. old file format
def test_ficheiro_de_formato_antigo_e_refeito(tmp_path):
	pr, _ = _placed_ingested(tmp_path)
	R.register_all(pr, image=False, progress=None, relax_pass=False)
	d = _raw(pr)
	assert len(d["placements"]) == 3
	d.pop("f_rotation", None)                     # written before F_ROTATION existed (a249ad6): ignored as a whole
	d.pop("f_translation", None)
	with open(pr.p("render", "placements.json"), "w", encoding="utf-8") as f:
		json.dump(d, f)
	assert R.load_placements(Project.open(pr.path))["placements"] == {}
	g = _start(pr.path)
	try:
		d2 = _raw(pr)
		assert d2.get("f_rotation") is True and set(d2["placements"]) == set(R.placed_ids(Project.open(pr.path)))
		assert _valid(pr) == set(R.placed_ids(Project.open(pr.path)))
	finally:
		g.stop()


# ---------------------------------------------------------------- 6. a write crosses the fill
def test_preenchimento_cruzado_por_escritas_nao_perde_nem_guarda_velhas(tmp_path):
	pr, cell_of, lc, _ = _grid_project(tmp_path)
	gui = S.Gui(pr.path, prepare=False, use_image=False, log=None, queue=False)
	cl = TestClient(S.create_app(gui))
	target = cell_of[CONTORNO]
	posed = cell_of[(1, 4)]
	seen = []
	orig_reg = R.register_piece

	done = {"n": 0}

	def reg(project, pid, **kw):
		seen.append(pid)
		r = orig_reg(project, pid, **kw)
		writes()
		return r

	def writes():
		# right after the fill has computed the entries of ``target`` and ``posed``, three writes land (outside its
		# lock): a contour (same key, new shape), a manual pose (new key) and a new placement
		if done["n"] == 0 and target in seen and posed in seen:
			done["n"] = 1
			d = cl.get(f"/api/pieces/{target}/contorno").json()
			r = cl.post(f"/api/pieces/{target}/contorno", json={"contour": _editor_contour(d, dx=8.0), "origem": d["origem"],
																  "tamanho": d["tamanho"]})
			assert r.status_code == 200, r.text
			r = cl.post(f"/api/pieces/{posed}/pose", json={"theta_deg": 3.0, "dx_mm": 0.5, "dy_mm": -0.4})
			assert r.status_code == 200, r.text
			r = cl.post("/api/confirm", json={"acao": "place", "piece": lc, "cell": [2, 4], "origin": "manual"})
			assert r.status_code == 200, r.text
	try:
		R.register_piece = reg
		info = gui._fill_placements()
	finally:
		R.register_piece = orig_reg
	try:
		gui.wait_suspeitas()
		assert done["n"] == 1
		assert info["descartadas"] == 2                         # the contour (token) and the manual pose (key)
		assert _valid(pr) == set(R.placed_ids(Project.open(pr.path)))
		assert _not_stale(pr) == []
		pl = R.load_placements(Project.open(pr.path))["placements"]
		assert pl[posed].get("manual") is True and abs(pl[posed]["theta_deg"] - 3.0) < 1e-9
	finally:
		gui.stop()


# ---------------------------------------------------------------- 7. permanent check
def test_verificacao_permanente_aviso_status_e_stale_assets(tmp_path):
	pr, _ = _placed_ingested(tmp_path)
	st = R.stale_assets(pr)
	assert st["n_pecas"] == 0
	assert st.get("placements_em_falta") == R.placed_ids(pr) and st.get("n_placements_em_falta") == 3
	g = _start(pr.path)
	try:
		assert any("sem registo" in m for m in g.prep_log), g.prep_log
		s = TestClient(S.create_app(g)).get("/api/status").json()
		assert s["placements"]["em_falta_no_arranque"] == 3
		assert s["placements"]["preenchidas"] == 3 and s["placements"]["em_falta"] == 0
		assert s["placements"]["a_preencher"] is False
		assert R.stale_assets(Project.open(pr.path))["n_placements_em_falta"] == 0
	finally:
		g.stop()
	# a coherent start-up fills nothing and writes nothing
	mt = os.stat(pr.p("render", "placements.json")).st_mtime_ns
	g2 = _start(pr.path)
	try:
		s = TestClient(S.create_app(g2)).get("/api/status").json()
		assert s["placements"]["em_falta_no_arranque"] == 0 and s["placements"]["preenchidas"] == 0
		assert s["placements"]["gravacoes"] == 0
		assert os.stat(pr.p("render", "placements.json")).st_mtime_ns == mt
		assert not any("sem registo" in m for m in g2.prep_log)
	finally:
		g2.stop()


# ---------------------------------------------------------------- 8. entry made with the other rule
def test_entrada_feita_com_a_outra_regra_e_refeita(tmp_path):
	pr, _ = _placed_ingested(tmp_path)
	other = not R.REGISTER_IMAGE
	d = {"log_len": R._log_len(pr), "version": R.PLACEMENTS_VERSION, "placements": {}}
	for pid in R.placed_ids(pr):
		e = R.register_piece(pr, pid, art=None, image=False)
		e["key"] = R._entry_key(pr, pid, image=other)
		e["image_used"] = other
		d["placements"][pid] = e
	R.save_placements(pr, d)
	assert R.missing_placements(Project.open(pr.path)) == R.placed_ids(pr)
	g = _start(pr.path)
	try:
		pl = R.load_placements(Project.open(pr.path))["placements"]
		assert {pid: pl[pid]["key"] for pid in pl} == {pid: R._entry_key(pr, pid) for pid in R.placed_ids(pr)}
		assert all(pl[pid].get("regra") == R.register_rule() for pid in pl)
		assert R.missing_placements(Project.open(pr.path)) == []
	finally:
		g.stop()


# ---------------------------------------------------------------- 8. cache do tabuleiro e entradas novas (2026-11-25)
def _cache_board(g):
	"""The full-board raster the server serves (the cached one), decoded."""
	import cv2
	return cv2.imdecode(np.frombuffer(g.board_jpg(), np.uint8), cv2.IMREAD_COLOR)


def _full_board(g):
	"""A whole ``compose_board`` of the project with the entries the server accepts, as JPEG (the cache's own format)."""
	import cv2
	pr = g.pr
	pl = R.load_placements(pr)["placements"]
	fresh = {p: e for p, e in pl.items() if p in pr.pieces and e.get("key") == R._entry_key(pr, p)}
	img = R.compose_board(pr, S.BOARD_PPC, layers=("art", "pieces"), placements=fresh)
	return cv2.imdecode(np.frombuffer(S._jpeg(img), np.uint8), cv2.IMREAD_COLOR)


def test_snapshot_com_entradas_distingue_entrada_nova_e_pose(tmp_path):
	pr, _ = _placed_ingested(tmp_path)
	pid = sorted(pr.pieces)[0]
	e = R.register_piece(pr, pid, art=None, image=False)
	snap0 = S.board_snapshot(pr.board, pr.pieces, None)
	assert all(len(x) == 4 for x in snap0)                                  # without entries: the old shape
	sem = S.board_snapshot(pr.board, pr.pieces, None, placements={})
	assert sem == snap0
	com = S.board_snapshot(pr.board, pr.pieces, None, placements={pid: e})
	assert com != snap0 and sum(1 for a, b in zip(com, snap0) if a != b) == 1       # one cell: the piece's
	assert com == S.board_snapshot(pr.board, pr.pieces, None, placements={pid: dict(e)})
	e2 = dict(e, theta_deg=float(e["theta_deg"]) + 1.0)
	assert S.board_snapshot(pr.board, pr.pieces, None, placements={pid: e2}) != com        # a moved pose
	assert S.placement_digest(None) is None


def test_cache_do_tabuleiro_em_disco_sem_uma_peca_e_refeita_quando_a_entrada_aparece(tmp_path):
	"""The real failure (24/11): at the first start the raster was composed without 57 pieces that had no entry yet
	(«sem registo»); the next start registered them (the log, hence the snapshot of the time, did not change) and the
	cached raster kept the holes. Here the disk cache is written the way that start left it: image without piece X,
	snapshot with every entry but X's. The server must draw X, and nothing else may move (JPEG loss only)."""
	import cv2
	pr, _ = _placed_ingested(tmp_path)
	g = _start(pr.path)                                    # entries filled, board cached
	try:
		want = _full_board(g)
		pl = R.load_placements(g.pr)["placements"]
		pids = sorted(R.placed_ids(g.pr))
		x = pids[0]
		cache_pl = {p: e for p, e in pl.items() if p != x}
		img = R.compose_board(g.pr, S.BOARD_PPC, layers=("art", "pieces"), placements=cache_pl,
							  piece_ids=[p for p in pids if p != x])
		snap = S.board_snapshot(g.pr.board, g.pr.pieces, OV.latest_arestas(g.pr), placements=cache_pl)
		ver, plm = g.version(), g._pl_mtime()
	finally:
		g.stop()
	jp = os.path.join(pr.path, "render", "gui", f"board_{S.BOARD_PPC}.jpg")
	mp = os.path.join(pr.path, "render", "gui", f"board_{S.BOARD_PPC}.json")
	with open(jp, "wb") as f:
		f.write(S._jpeg(img))
	with open(mp, "w", encoding="utf-8") as f:
		json.dump({"ver": ver, "ppc": S.BOARD_PPC, "pl_mtime": plm, "snap": snap}, f)
	cell = Project.open(pr.path).piece(x).celula
	h, w = want.shape[0] / pr.profile.rows, want.shape[1] / pr.profile.cols
	ys, xs = slice(int((cell[0] - 1) * h), int(cell[0] * h)), slice(int((cell[1] - 1) * w), int(cell[1] * w))
	stale = cv2.imdecode(np.fromfile(jp, np.uint8), cv2.IMREAD_COLOR)
	assert np.abs(stale[ys, xs].astype(int) - want[ys, xs]).mean() > 5          # the precondition: the cell is wrong
	g = S.Gui(pr.path, prepare=True, use_image=False, log=None, queue=False)
	try:
		t0 = time.time()
		while not any(n == "ready" for _, n, _ in g.events_after(0)) and time.time() - t0 < 60:
			time.sleep(0.1)
		g.wait_placements(60)
		got = _cache_board(g)
		d = np.abs(got.astype(int) - want.astype(int))
		assert d[ys, xs].mean() < 2.0                                   # X is drawn again
		assert d.max() < 60                                             # and the rest is the same up to JPEG loss
	finally:
		g.stop()


def test_cache_do_tabuleiro_na_mesma_sessao_igual_byte_a_byte(tmp_path):
	"""Without the disk cache the first raster is a whole ``compose_board``: the JPEG equals the whole composition's."""
	pr, _ = _placed_ingested(tmp_path)
	g = _start(pr.path)
	try:
		assert S._jpeg(R.compose_board(g.pr, S.BOARD_PPC, layers=("art", "pieces"),
									   placements={p: e for p, e in R.load_placements(g.pr)["placements"].items()
												   if e.get("key") == R._entry_key(g.pr, p)})) == g.board_jpg()
	finally:
		g.stop()
