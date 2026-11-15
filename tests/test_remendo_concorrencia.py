"""Remendo das regiões sob esforço (2026-11-15, DETALHE.md §13.7): fios que pedem regiões de detalhe (remendadas sobre
a entrada guardada) enquanto o fio principal coloca, tira, desfaz e muda poses dentro dessas regiões.

``test_concorrencia.py`` escreve sem pausas, por isso quase todas as composições são cruzadas por uma escrita e nunca
ficam guardadas (uma sonda contou 169 composições inteiras «sem base», 0 remendos). Aqui as escritas têm pausas, para os
remendos acontecerem a meio delas. No fim: nenhuma exceção, houve remendos, e, depois de mais escritas já sem
concorrência (cada uma remendada sobre o que ficou guardado durante o esforço), cada região é igual byte a byte à de um
servidor acabado de abrir: uma entrada rasgada guardada passaria para os remendos seguintes.
"""
import random
import threading
import time
import traceback

import pytest
from fastapi.testclient import TestClient

from src import server as S
from test_regiao_remendo import ALVO_CEU, ALVO_RELVA, PPC, REG, _cold, _grid_project

pytestmark = pytest.mark.slow

REGIONS = [REG, (1, 3, 3, 5), (4, 2, 6, 6)]
ROUNDS = 6


def test_remendos_durante_escritas_e_igual_a_frio_no_fim(tmp_path):
	from src.query import run_query
	pr, cell_of, lc, lr = _grid_project(tmp_path)
	run_query(pr, use_image=False)
	gui = S.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "up"), log=None, queue=False)
	app = S.create_app(gui)
	cl = TestClient(app)
	stop = threading.Event()
	errors, n = [], {"n": 0}

	def reader(k):
		rnd = random.Random(k)
		c2 = TestClient(app) if k == 0 else None
		while not stop.is_set():
			try:
				reg = rnd.choice(REGIONS)
				if c2 is not None:
					r = c2.get(f"/api/board.jpg?ppc={PPC}&region={','.join(str(v) for v in reg)}")
					if r.status_code != 200:
						errors.append(f"HTTP {r.status_code}: {r.text[:300]}")
				else:
					gui.board_jpg(PPC, reg)
				n["n"] += 1
			except Exception:  # noqa: BLE001
				errors.append(traceback.format_exc())
			time.sleep(rnd.uniform(0.0, 0.05))

	def post(url, body):
		r = cl.post(url, json=body)
		assert r.status_code == 200, r.text

	viz = cell_of[(1, 4)]
	for reg in REGIONS:                         # a base for every region
		gui.board_jpg(PPC, reg)
	threads = [threading.Thread(target=reader, args=(k,), daemon=True) for k in range(3)]
	for t in threads:
		t.start()
	try:
		for i in range(ROUNDS):
			post("/api/confirm", {"acao": "place", "piece": lc, "cell": list(ALVO_CEU), "origin": "manual"})
			time.sleep(0.4)
			post("/api/confirm", {"acao": "place", "piece": lr, "cell": list(ALVO_RELVA), "origin": "manual"})
			time.sleep(0.4)
			post(f"/api/pieces/{viz}/pose", {"theta_deg": 2.0 + i % 2, "dx_mm": 0.3, "dy_mm": -0.2})
			time.sleep(0.4)
			post("/api/confirm", {"acao": "unplace", "piece": lr, "desfaz": True})
			time.sleep(0.4)
			post(f"/api/pieces/{viz}/pose/repor", {})
			post("/api/confirm", {"acao": "unplace", "piece": lc})
			time.sleep(0.4)
	finally:
		stop.set()
		for t in threads:
			t.join(60)
	assert not errors, f"{len(errors)} erros nos fios; o 1.º:\n{errors[0]}"
	assert gui.patch_stats["remendos"] > 0, gui.patch_json()
	# more writes without concurrency: each region patched over what the stress left stored, then against a cold server
	for k, body in enumerate(({"acao": "place", "piece": lr, "cell": list(ALVO_RELVA), "origin": "manual"},
							  {"acao": "place", "piece": lc, "cell": list(ALVO_CEU), "origin": "manual"})):
		post("/api/confirm", body)
		gui.wait_suspeitas()
		for j, reg in enumerate(REGIONS):
			assert gui.board_jpg(PPC, reg) == _cold(gui, tmp_path, f"f{k}{j}", reg), (body, reg, gui.patch_json())
	print("remendo:", gui.patch_json())
	gui.wait_suspeitas()
	th = getattr(gui, "_holes_thread", None)
	if th is not None:
		th.join(60)
	gui.stop()
