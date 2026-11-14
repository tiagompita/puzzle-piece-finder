"""Composição de uma região do tabuleiro sozinha e com o ranking dos buracos a frio a correr noutro fio (GIL).

	.venv/Scripts/python.exe tools/diagnostico/gui/gil_buracos.py --project <cópia> [--switch 0.005]

Num processo novo (cache dos buracos fria, como no arranque do servidor): compõe 2 regiões sozinho, depois arranca
``Gui._compute_holes`` num fio (o que o 1.º ``/api/montar`` faz), espera 2 s e compõe outras 3 regiões enquanto ele
corre. ``--switch`` muda ``sys.setswitchinterval`` (omissão do Python 0,005 s) para medir o efeito «comboio» do GIL:
cada chamada numpy/OpenCV que liberta o GIL espera até um intervalo inteiro para o voltar a ter.
"""
import argparse
import json
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)
os.chdir(ROOT)


def main(argv=None) -> int:
	ap = argparse.ArgumentParser()
	ap.add_argument("--project", required=True)
	ap.add_argument("--switch", type=float, default=None)
	a = ap.parse_args(argv)
	if a.switch:
		sys.setswitchinterval(a.switch)
	from src import server as S
	gui = S.Gui(a.project, prepare=False)
	gui.placements()
	regs = [(1, 20, 14, 40), (34, 30, 47, 50), (1, 21, 14, 41), (34, 31, 47, 51), (2, 20, 15, 40)]
	out = {"switch": sys.getswitchinterval(), "sozinho": [], "com_buracos": []}
	for r in regs[:2]:
		t0 = time.perf_counter()
		gui._compose(100, r)
		out["sozinho"].append(round(time.perf_counter() - t0, 2))
	key = (gui.version(), id(gui.pr))
	th = threading.Thread(target=gui._compute_holes, args=(key,), daemon=True)
	tb = time.perf_counter()
	th.start()
	time.sleep(2)
	for r in regs[2:]:
		t0 = time.perf_counter()
		gui._compose(100, r)
		out["com_buracos"].append(round(time.perf_counter() - t0, 2))
	th.join()
	out["buracos_s"] = round(time.perf_counter() - tb, 1)
	print(json.dumps(out))
	return 0


if __name__ == "__main__":
	sys.exit(main())
