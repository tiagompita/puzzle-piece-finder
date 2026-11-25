"""Diferença por célula entre a cache do tabuleiro em disco (render/gui/board_60.jpg) e um compose_board inteiro.

Só lê (nunca escreve no projeto). Uso: python tools/diagnostico/gui/cache_vs_inteiro.py [--project projects/alpes]"""
import argparse
import json
import os
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("--project", default=os.path.join(ROOT, "projects", "alpes"))
	ap.add_argument("--ppc", type=int, default=60)
	ap.add_argument("--limiar", type=float, default=6.0, help="diferença média absoluta (0-255) para contar a célula")
	a = ap.parse_args()
	from src import render
	from src.state import Project
	pr = Project.open(a.project)
	jp = os.path.join(a.project, "render", "gui", f"board_{a.ppc}.jpg")
	cache = cv2.imdecode(np.fromfile(jp, np.uint8), cv2.IMREAD_COLOR)
	pl = render.load_placements(pr).get("placements") or {}
	fresh = {pid: e for pid, e in pl.items() if pid in pr.pieces and e.get("key") == render._entry_key(pr, pid)}
	full = render.compose_board(pr, a.ppc, layers=("art", "pieces"), placements=fresh)
	print("formas", cache.shape, full.shape)
	rows, cols = pr.profile.rows, pr.profile.cols
	h, w = full.shape[0] / rows, full.shape[1] / cols
	d = np.abs(cache.astype(np.int16)[:full.shape[0], :full.shape[1]] - full.astype(np.int16)).mean(axis=2)
	bad = []
	for l in range(rows):
		for c in range(cols):
			v = d[int(round(l * h)):int(round((l + 1) * h)), int(round(c * w)):int(round((c + 1) * w))].mean()
			if v > a.limiar:
				bad.append((l + 1, c + 1, round(float(v), 1)))
	print("células com diferença média >", a.limiar, ":", len(bad))
	print(bad[:80])
	cells = dict(pr.board.iter_cells())
	print("peças das células:", sorted({cells[(l, c)]["peca_id"] for l, c, _ in bad if cells[(l, c)]["peca_id"]})[:40])


if __name__ == "__main__":
	main()
