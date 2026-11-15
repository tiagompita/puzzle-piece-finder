"""Remendo das regiões de detalhe (2026-11-15, decisão do Tiago; DETALHE.md §13.4 e §13.7).

Uma escrita dentro de uma região de detalhe já em cache deixava de acertar na chave por conteúdo e a região era
recomposta inteira (≈ 100 peças no céu). Agora o servidor guarda, com o JPEG, os arrays da região (a base sob as peças, a
imagem e a caixa de cada peça) e, quando o conteúdo muda, compara as partes por peça: só se redesenham, sobre a base, as
peças cuja caixa toca a zona suja (as caixas antigas e novas das peças que mudaram). Prova, em todos os casos: o JPEG
servido é igual byte a byte ao de um servidor acabado de abrir (composição a frio), e um contador mostra que o remendo
foi mesmo usado.

Projeto sintético 6 × 8 com arte (céu liso nas filas 1–3, relva com textura nas 4–6) e 16 peças colocadas; a região
(1,2)–(6,6) apanha as duas zonas.
"""
import threading

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

import synth
from src import server as S
from src.shape import analyse, transform_contour
from src.state import Project
from test_server import _editor_contour
from test_shape import MMPP

ROWS, COLS = 6, 8
REG = (1, 2, 6, 6)
PPC = 120
KEY = (float(PPC), REG)
ALVO_CEU, ALVO_RELVA = (2, 4), (5, 4)
CONTORNO = (3, 5)                    # a peça re-segmentada: sozinha noutra folha
KINDS = ["TBTB", "BTBT", "TTBB", "BBTT", "TBBT", "BTTB"]
BG = (40, 160, 60)
STEP = 420


def _art(path):
	px = 40
	img = np.zeros((ROWS * px, COLS * px, 3), np.uint8)
	y = np.linspace(0.0, 1.0, 3 * px)[:, None, None]
	sky = np.concatenate([170 + 40 * y, 200 + 30 * y, 235 + 0 * y], axis=2)
	img[:3 * px] = np.broadcast_to(sky, (3 * px, COLS * px, 3)).astype(np.uint8)
	rng = np.random.default_rng(5)
	img[3 * px:, :, 0] = rng.integers(20, 90, (3 * px, COLS * px))
	img[3 * px:, :, 1] = rng.integers(90, 200, (3 * px, COLS * px))
	img[3 * px:, :, 2] = rng.integers(10, 70, (3 * px, COLS * px))
	Image.fromarray(img).save(path)


def _texture(kind, shape, rng, i):
	h, w = shape
	if kind == "ceu":
		g = np.linspace(0.0, 1.0, h)[:, None]
		base = np.array([180 + 3 * i, 205, 240], float)
		return np.clip(base[None, None, :] + 15 * g[..., None] * np.array([1.0, 0.5, 0.0]), 0, 255).astype(np.uint8) \
			* np.ones((1, w, 1), np.uint8)
	t = np.empty((h, w, 3), np.uint8)
	t[..., 0] = rng.integers(60, 140, (h, w))
	t[..., 1] = rng.integers(70, 150, (h, w))
	t[..., 2] = rng.integers(20, 60, (h, w))
	return t


def _sheet(pr, tmp_path, name, items, rng):
	"""One scan with ``items`` = [(kind, board_contour_mm, psi)]: returns the piece ids, in order."""
	n = len(items)
	per_row = 6
	H = STEP * ((n + per_row - 1) // per_row) + 100
	W = STEP * min(n, per_row) + 100
	img = np.full((H, W, 3), BG, np.uint8)
	pts_all = []
	for i, (kind, board, psi) in enumerate(items):
		off = (STEP // 2 + 50 + STEP * (i % per_row), STEP // 2 + 50 + STEP * (i // per_row))
		pts = transform_contour(board, psi, center=(0.0, 0.0)) / MMPP + np.asarray(off, float)
		m = np.zeros((H, W), np.uint8)
		cv2.fillPoly(m, [np.round(pts).astype(np.int32).reshape(-1, 1, 2)], 255)
		tex = _texture(kind, (H, W), rng, i)
		img[m > 0] = tex[m > 0]
		pts_all.append(pts)
	scan = tmp_path / f"{name}.png"
	Image.fromarray(img).save(scan)
	sid = pr.add_scan(str(scan), dpi=300, lote=3)
	ids = []
	for i, pts in enumerate(pts_all):
		x0, y0 = np.floor(pts.min(0)).astype(int) - 10
		x1, y1 = np.ceil(pts.max(0)).astype(int) + 10
		al = np.zeros(img.shape[:2], np.uint8)
		cv2.fillPoly(al, [np.round(pts).astype(np.int32).reshape(-1, 1, 2)], 255)
		rgba = np.dstack([img, al])[y0:y1, x0:x1]
		pid_guess = f"P{len(pr.pieces) + 1:04d}"
		rel = f"crops/{pid_guess}.png"
		Image.fromarray(np.ascontiguousarray(rgba)).save(pr.p(rel))
		pid = pr.add_piece(sid, {"index_in_scan": i, "n_no_lote": len(pr.pieces) + 1, "shape": analyse(pts, MMPP),
								 "contour": pts, "bbox": [int(x0), int(y0), int(x1 - x0), int(y1 - y0)], "crop_path": rel})
		assert pid == pid_guess
		ids.append(pid)
	return ids


def _grid_project(tmp_path):
	import os
	art = tmp_path / "arte.png"
	_art(art)
	prof = synth.profile(rows=ROWS, cols=COLS, p90=None)
	prof.art = {"file": str(art), "bbox": None}
	pp = tmp_path / "puzzle.json"
	prof.save(str(pp))
	pr = Project.create(str(tmp_path / "proj"), str(pp))
	os.makedirs(pr.p("crops"), exist_ok=True)
	rng = np.random.default_rng(11)
	cells = [(l, c) for l in range(1, 7) for c in (3, 4, 5) if (l, c) not in (ALVO_CEU, ALVO_RELVA, CONTORNO)]
	items, where = [], []
	for k, cell in enumerate(cells):
		kind = "ceu" if cell[0] <= 3 else "relva"
		board = synth.body_mm(KINDS[k % len(KINDS)], deltas=tuple(rng.uniform(-0.8, 0.8, 4)))
		items.append((kind, board, float(rng.uniform(-40, 40))))
		where.append(cell)
	for cell in (ALVO_CEU, ALVO_RELVA):
		kind = "ceu" if cell[0] <= 3 else "relva"
		items.append((kind, synth.body_mm("TBTB", deltas=tuple(rng.uniform(-0.8, 0.8, 4))), float(rng.uniform(-40, 40))))
		where.append(None)
	ids = _sheet(pr, tmp_path, "folha1", items, rng)
	psis = {pid: it[2] for pid, it in zip(ids, items)}
	cell_of = {}
	for pid, cell in zip(ids, where):
		if cell is not None:
			pr.place(pid, cell, theta_deg=-psis[pid])
			cell_of[cell] = pid
	loose_ceu, loose_relva = ids[-2], ids[-1]
	board = synth.body_mm("BTBT", deltas=(0.3, -0.2, 0.4, -0.3))
	psi = 17.0
	(cpid,) = _sheet(pr, tmp_path, "folha2", [("ceu", board, psi)], rng)
	pr.place(cpid, CONTORNO, theta_deg=-psi)
	cell_of[CONTORNO] = cpid
	pr.save()
	return pr, cell_of, loose_ceu, loose_relva


@pytest.fixture
def env(tmp_path):
	from src.query import run_query
	pr, cell_of, lc, lr = _grid_project(tmp_path)
	run_query(pr, use_image=False)
	gui = S.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "up"), log=None, queue=False)
	cl = TestClient(S.create_app(gui))
	n = {"compose": 0}
	orig = gui._compose

	def compose(ppc, region=None):
		n["compose"] += 1
		return orig(ppc, region)
	gui._compose = compose
	yield gui, cl, n, cell_of, lc, lr
	gui.wait_suspeitas()
	th = getattr(gui, "_holes_thread", None)
	if th is not None:
		th.join(60)
	gui.stop()


def _cnt(gui, k):
	"""The patch counters (0 before the patch existed)."""
	return (getattr(gui, "patch_stats", None) or {}).get(k, 0)


def _cold(gui, tmp_path, tag, reg=REG):
	g = S.Gui(gui.path, prepare=False, use_image=False, uploads=str(tmp_path / tag), log=None, queue=False)
	try:
		return g.board_jpg(PPC, reg)
	finally:
		g.stop()


def _post(cl, url, body):
	r = cl.post(url, json=body)
	assert r.status_code == 200, r.text
	return r.json()


def _jpg(gui):
	gui.wait_suspeitas()
	return gui.board_jpg(PPC, REG)


def test_colocar_no_ceu_e_na_relva_remenda_e_iguala_a_frio(env, tmp_path):
	gui, cl, n, cell_of, lc, lr = env
	a = _jpg(gui)
	assert _cnt(gui, "remendos") == 0
	_post(cl, "/api/confirm", {"acao": "place", "piece": lc, "cell": list(ALVO_CEU), "origin": "manual"})
	b = _jpg(gui)
	assert b != a and _cnt(gui, "remendos") == 1
	assert b == _cold(gui, tmp_path, "f1")
	_post(cl, "/api/confirm", {"acao": "place", "piece": lr, "cell": list(ALVO_RELVA), "origin": "manual"})
	c = _jpg(gui)
	assert c != b and _cnt(gui, "remendos") == 2
	assert c == _cold(gui, tmp_path, "f2")
	assert _cnt(gui, "inteiras") == 1                       # only the first one (no base yet)


def test_vizinha_que_muda_de_pose_gravada_e_reposta(env, tmp_path):
	gui, cl, n, cell_of, lc, lr = env
	viz = cell_of[(1, 4)]
	a = _jpg(gui)
	_post(cl, f"/api/pieces/{viz}/pose", {"theta_deg": 3.0, "dx_mm": 0.5, "dy_mm": -0.4})
	b = _jpg(gui)
	assert b != a and _cnt(gui, "remendos") == 1
	assert b == _cold(gui, tmp_path, "f1")
	_post(cl, f"/api/pieces/{viz}/pose/repor", {})
	c = _jpg(gui)
	assert _cnt(gui, "remendos") == 2
	assert c == a == _cold(gui, tmp_path, "f2")


def test_desfazer_volta_ao_array_de_antes(env, tmp_path):
	gui, cl, n, cell_of, lc, lr = env
	a = _jpg(gui)
	_post(cl, "/api/confirm", {"acao": "place", "piece": lr, "cell": list(ALVO_RELVA), "origin": "manual"})
	b = _jpg(gui)
	_post(cl, "/api/confirm", {"acao": "unplace", "piece": lr, "desfaz": True})
	c = _jpg(gui)
	assert b != a and _cnt(gui, "remendos") == 2
	assert c == a == _cold(gui, tmp_path, "f1")


def test_tirar_do_lugar_remenda(env, tmp_path):
	gui, cl, n, cell_of, lc, lr = env
	a = _jpg(gui)
	_post(cl, "/api/confirm", {"acao": "unplace", "piece": cell_of[(4, 4)]})
	b = _jpg(gui)
	assert b != a and _cnt(gui, "remendos") == 1
	assert b == _cold(gui, tmp_path, "f1")


def test_peca_por_confirmar_nao_entra_no_raster(env, tmp_path):
	gui, cl, n, cell_of, lc, lr = env
	a = _jpg(gui)
	k = n["compose"]
	_post(cl, "/api/confirm", {"acao": "position_known", "piece": lc, "cell": list(ALVO_CEU)})
	b = _jpg(gui)
	assert n["compose"] == k                                   # the content key did not change: JPEG cache hit
	assert b == a == _cold(gui, tmp_path, "f1")


def test_peca_re_segmentada_por_contorno_manual(env, tmp_path):
	gui, cl, n, cell_of, lc, lr = env
	pid = cell_of[CONTORNO]
	a = _jpg(gui)
	k = _cnt(gui, "remendos") + _cnt(gui, "inteiras")
	d = cl.get(f"/api/pieces/{pid}/contorno").json()
	c = _editor_contour(d, dx=8.0)
	_post(cl, f"/api/pieces/{pid}/contorno", {"contour": c, "origem": d["origem"], "tamanho": d["tamanho"]})
	gui.sync()
	b = _jpg(gui)
	assert b != a
	assert _cnt(gui, "remendos") + _cnt(gui, "inteiras") == k + 1
	assert _cnt(gui, "remendos") >= 1                          # the crop key changed for one piece: a patch
	assert b == _cold(gui, tmp_path, "f1")


def test_escrita_a_meio_de_um_remendo_nao_fica_guardada(env, tmp_path):
	gui, cl, n, cell_of, lc, lr = env
	_jpg(gui)
	_post(cl, "/api/confirm", {"acao": "place", "piece": lc, "cell": list(ALVO_CEU), "origin": "manual"})
	gui.wait_suspeitas()
	entry0 = gui.patches.get(KEY) if hasattr(gui, "patches") else None
	jk = (round(float(PPC), 1), REG)
	ver0 = gui._regions[jk][0]
	orig = gui._compose
	once = {"done": False}

	def compose(ppc, region=None):
		img = orig(ppc, region)
		if not once["done"]:                     # a write (inside the region) ends while this patch runs
			once["done"] = True
			th = threading.Thread(target=_post, args=(cl, "/api/confirm", {"acao": "place", "piece": lr,
																			"cell": list(ALVO_RELVA), "origin": "manual"}))
			th.start()
			th.join()
		return img
	gui._compose = compose
	r0 = _cnt(gui, "remendos")
	gui.board_jpg(PPC, REG)                      # patched from the old content, the write in between
	assert _cnt(gui, "remendos") == r0 + 1
	assert gui.patches.get(KEY) is entry0        # neither the arrays ...
	assert gui._regions[jk][0] == ver0           # ... nor the JPEG kept
	b = _jpg(gui)
	assert b == _cold(gui, tmp_path, "f1")


def test_sem_base_ou_diferenca_grande_compoe_inteira(env, tmp_path, monkeypatch):
	gui, cl, n, cell_of, lc, lr = env
	_jpg(gui)
	assert _cnt(gui, "inteiras") == 1 and gui.patch_stats["motivos"] == {"sem_base": 1}
	monkeypatch.setattr(S, "PATCH_MAX_PECAS", 0)
	_post(cl, "/api/confirm", {"acao": "place", "piece": lc, "cell": list(ALVO_CEU), "origin": "manual"})
	b = _jpg(gui)
	assert gui.patch_stats["motivos"].get("muitas_pecas") == 1 and _cnt(gui, "remendos") == 0
	assert b == _cold(gui, tmp_path, "f1")
	monkeypatch.setattr(S, "PATCH_MAX_PECAS", 12)
	monkeypatch.setattr(S, "PATCH_MAX_FRAC", 0.001)
	_post(cl, "/api/confirm", {"acao": "unplace", "piece": lc, "desfaz": True})
	c = _jpg(gui)
	assert gui.patch_stats["motivos"].get("zona_grande") == 1 and _cnt(gui, "remendos") == 0
	assert c == _cold(gui, tmp_path, "f2")
