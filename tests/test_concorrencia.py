"""Teste de esforço da composição do tabuleiro fora dos bloqueios (DETALHE.md §8, passo 0b da F2).

Desde a ronda 1 do detalhe (``e252dc1``) uma região compõe-se fora de qualquer bloqueio, ao mesmo tempo que as escritas.
Aqui: 4 fios compõem em ciclo (regiões com e sem cache, o tabuleiro inteiro, o zoom 3 × 3, a miniatura da peça, o
«verificar» da F2, e um por HTTP) enquanto o fio principal coloca, tira e re-segmenta peças pelo servidor, e um outro fio deixa
``render/clean`` velhos (o caso que matou a composição com ``FileNotFoundError`` na ronda 2). No fim: nenhuma exceção nos
fios, invariantes no disco, e o que o servidor serve para a versão final é igual ao de um servidor acabado de abrir.
"""
import os
import random
import threading
import time
import traceback

import numpy as np
import pytest
from PIL import Image

from fastapi.testclient import TestClient  # noqa: E402

from src import server as S  # noqa: E402
from src.state import Project, replay  # noqa: E402
from test_query import _project  # noqa: E402
from test_server import _editor_contour  # noqa: E402

pytestmark = pytest.mark.slow

REGIONS = [(1, 1, 4, 6), (2, 2, 3, 4), (1, 2, 3, 5), (2, 3, 2, 3), (3, 3, 4, 5), (1, 3, 3, 4)]
ROUNDS = 12


def _stale_clean(pr, stop, errors):
	"""Keep a stale ``render/clean/P####.png`` (older than its crop) for every placed piece."""
	d = pr.p("render", "clean")
	os.makedirs(d, exist_ok=True)
	old = time.time() - 86400
	while not stop.is_set():
		try:
			for pid in [p.id for p in list(pr.pieces.values()) if p.estado == "colocada"]:
				fp = os.path.join(d, f"{pid}.png")
				if not os.path.exists(fp):
					Image.fromarray(np.zeros((8, 8, 4), np.uint8)).save(fp)
					os.utime(fp, (old, old))
		except OSError:
			pass                       # a reader holds it / deleted it: the next turn writes it again
		except Exception:  # noqa: BLE001
			errors.append(traceback.format_exc())
		time.sleep(0.002)


def test_compose_in_a_loop_while_placing_unplacing_and_resegmenting(tmp_path):
	from src.query import run_query
	pr, placed, tw, dec = _project(tmp_path)
	run_query(pr, use_image=False)
	gui = S.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "up"), log=None, queue=False)
	app = S.create_app(gui)
	cl = TestClient(app)
	stop = threading.Event()
	errors, counts = [], {"n": 0, "http": 0}

	def composer(k):
		rnd = random.Random(k)
		while not stop.is_set():
			try:
				x = rnd.random()
				reg = rnd.choice(REGIONS)
				if x < 0.10:
					gui.board_jpg(S.BOARD_PPC)                        # full board under rlock (patched)
				elif x < 0.40:
					gui.board_jpg(120, reg)                           # region (LRU)
				elif x < 0.40 + 0.35:
					gui._compose(rnd.choice((90, 120, 150)), reg)     # always composes
				elif x < 0.82:
					gui.zoom_jpg(rnd.randint(1, 4), rnd.randint(1, 6), "render")
				elif x < 0.90:
					# «verificar» da F2: também sem o bloqueio de escrita (DETALHE.md §8.2)
					r = gui.verify_json(2, 4, rnd.choice((tw, dec)), rnd.choice((None, 0.0, 90.0)))
					assert "error" not in r and len(r["verificacoes"]) >= 2, r
				else:
					gui.piece_png(rnd.choice((placed, tw, dec)), "board", 120)
				counts["n"] += 1
			except Exception:  # noqa: BLE001
				errors.append(traceback.format_exc())

	def http_composer():
		c2 = TestClient(app)
		rnd = random.Random(99)
		while not stop.is_set():
			reg = ",".join(str(v) for v in rnd.choice(REGIONS))
			r = c2.get(f"/api/board.jpg?ppc=110&region={reg}")
			if r.status_code != 200:
				errors.append(f"HTTP {r.status_code}: {r.text[:300]}")
			counts["http"] += 1

	threads = [threading.Thread(target=composer, args=(k,), daemon=True) for k in range(4)]
	threads += [threading.Thread(target=http_composer, daemon=True),
				threading.Thread(target=_stale_clean, args=(gui.pr, stop, errors), daemon=True)]
	for t in threads:
		t.start()
	try:
		for i in range(ROUNDS):
			for body in ({"acao": "place", "piece": tw, "cell": [3, 4]},
						 {"acao": "place", "piece": dec, "cell": [1, 1], "origin": "manual"}):
				r = cl.post("/api/confirm", json=body)
				assert r.status_code == 200, r.text
			d = cl.get(f"/api/pieces/{placed}/contorno").json()
			c = _editor_contour(d, dx=4.0 + 2.0 * (i % 2))                 # re-segment the placed piece (manual contour)
			r = cl.post(f"/api/pieces/{placed}/contorno", json={"contour": c, "origem": d["origem"], "tamanho": d["tamanho"]})
			assert r.status_code == 200, r.text
			for pid in (tw, dec):
				r = cl.post("/api/confirm", json={"acao": "unplace", "piece": pid})
				assert r.status_code == 200, r.text
	finally:
		stop.set()
		for t in threads:
			t.join(60)
	assert not errors, f"{len(errors)} erros nos fios de composição; o 1.º:\n{errors[0]}"
	assert counts["n"] > 50 and counts["http"] > 5, counts
	# disk: invariants and the board replayed from the log
	pr2 = Project.open(gui.path)
	assert pr2.check_invariants(disk=True) == []
	assert replay(pr2.log_path, pr2.profile)[0] == pr2.board
	# nothing stale under the final version: what this server serves = what a server just opened serves
	fresh = S.Gui(gui.path, prepare=False, use_image=False, uploads=str(tmp_path / "up"), log=None, queue=False)
	for reg in REGIONS:
		assert gui.board_jpg(120, reg) == fresh.board_jpg(120, reg), reg
	assert gui.zoom_jpg(2, 3, "render") == fresh.zoom_jpg(2, 3, "render")
	assert gui.piece_png(placed, "board", 120)[0] == fresh.piece_png(placed, "board", 120)[0]
	# the full board is patched cell by cell (``_base``): in memory it equals a full composition up to the patch seams
	# (measured without threads, the same writes: max 4 levels on <= 5 px); a stale piece or pose would differ on
	# thousands of px. (The JPEGs are not compared: a raster read back from the disk cache is a second JPEG generation.)
	from src import render
	gui.board_jpg(S.BOARD_PPC)
	ref = render.compose_board(fresh.pr, S.BOARD_PPC, layers=("art", "pieces"), placements=fresh.placements())
	d = np.abs(gui._board["img"].astype(int) - ref.astype(int)).max(2)
	assert d.shape == ref.shape[:2] and int(d.max()) <= 8 and int((d > 2).sum()) <= 50, (int(d.max()), int((d > 2).sum()))
