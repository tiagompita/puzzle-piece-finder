"""Chave da cache das regiões = conteúdo da região (2026-11-15, decisão do Tiago; DETALHE.md §13).

Antes a chave era ``render_version()``: qualquer escrita deitava fora todas as regiões, mesmo as que não mudaram (o
detalhe do céu recomposto inteiro, 835 ms, depois de um «Encaixa» longe). Agora é a assinatura do que a composição
desenha ali (``Gui._region_sig``: as peças com célula na região ± 1, a pose com que são desenhadas, a peça pronta, a
arte). Prova: o JPEG servido é igual byte a byte ao de uma composição a frio (servidor acabado de abrir).
"""
import threading

from fastapi.testclient import TestClient

from src import server as S
from test_query import _project

REG = (1, 1, 2, 2)          # P0001 em (2,3) entra pela margem (coluna c1 + 1); (3,4) e (4,6) ficam fora
PPC = 120


def _setup(tmp_path):
	from src.query import run_query
	pr, placed, tw, dec = _project(tmp_path)
	run_query(pr, use_image=False)
	gui = S.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "up"), log=None, queue=False)
	cl = TestClient(S.create_app(gui))
	n = {"compose": 0}
	orig = gui._compose

	def compose(ppc, region=None):
		n["compose"] += 1
		return orig(ppc, region)
	gui._compose = compose
	return gui, cl, n, placed, tw, dec


def _cold(gui, tmp_path, tag):
	g = S.Gui(gui.path, prepare=False, use_image=False, uploads=str(tmp_path / tag), log=None, queue=False)
	try:
		return g.board_jpg(PPC, REG)
	finally:
		g.stop()


def _post(cl, body):
	r = cl.post("/api/confirm", json=body)
	assert r.status_code == 200, r.text


def test_a_far_write_keeps_the_region_and_it_equals_a_cold_composition(tmp_path):
	gui, cl, n, placed, tw, dec = _setup(tmp_path)
	a = gui.board_jpg(PPC, REG)
	assert n["compose"] == 1
	_post(cl, {"acao": "place", "piece": tw, "cell": [3, 4]})               # fora da região ± 1
	gui.wait_suspeitas()
	b = gui.board_jpg(PPC, REG)
	assert n["compose"] == 1                                               # antes: recomposta (a versão mudou)
	assert b == a == _cold(gui, tmp_path, "f1")
	gui.stop()


def test_a_write_inside_the_margin_recomposes_and_equals_a_cold_composition(tmp_path):
	gui, cl, n, placed, tw, dec = _setup(tmp_path)
	a = gui.board_jpg(PPC, REG)
	_post(cl, {"acao": "place", "piece": dec, "cell": [1, 1], "origin": "manual"})     # dentro da região
	gui.wait_suspeitas()
	b = gui.board_jpg(PPC, REG)
	assert n["compose"] == 2 and b != a
	assert b == _cold(gui, tmp_path, "f1")
	_post(cl, {"acao": "unplace", "piece": dec, "desfaz": True})           # desfeito: o conteúdo volta ao de antes
	gui.wait_suspeitas()
	c = gui.board_jpg(PPC, REG)
	assert c == a == _cold(gui, tmp_path, "f2")
	gui.stop()


def test_a_manual_pose_of_a_piece_in_the_margin_changes_the_key(tmp_path):
	gui, cl, n, placed, tw, dec = _setup(tmp_path)
	s0 = gui._region_sig(REG)
	gui.board_jpg(PPC, REG)
	r = cl.post(f"/api/pieces/{placed}/pose", json={"theta_deg": 3.0, "dx_mm": 0.5, "dy_mm": -0.4})
	assert r.status_code == 200, r.text
	assert gui._region_sig(REG) != s0
	b = gui.board_jpg(PPC, REG)
	assert n["compose"] == 2
	assert b == _cold(gui, tmp_path, "f1")
	gui.stop()


def test_a_composition_crossed_by_a_write_is_served_but_not_kept(tmp_path):
	gui, cl, n, placed, tw, dec = _setup(tmp_path)
	orig = gui._compose
	once = {"done": False}

	def compose(ppc, region=None):
		img = orig(ppc, region)
		if not once["done"]:                     # a write (inside the region) ends while this composition runs
			once["done"] = True
			th = threading.Thread(target=_post, args=(cl, {"acao": "place", "piece": dec, "cell": [1, 1], "origin": "manual"}))
			th.start()
			th.join()
		return img
	gui._compose = compose
	gui.board_jpg(PPC, REG)                      # composed with the old content, the write in between
	gui.wait_suspeitas()
	assert len(gui._regions) == 0                # not kept under the content key it was asked with
	b = gui.board_jpg(PPC, REG)
	assert b == _cold(gui, tmp_path, "f1")
	gui.stop()
