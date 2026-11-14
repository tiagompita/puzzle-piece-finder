"""Onde vai o tempo de um raster de detalhe do tabuleiro (``Gui.board_jpg(ppc, region)``), sem browser.

Uso (sempre sobre uma CÓPIA do projeto: ``Gui`` pode reabrir o projeto, nunca escreve aqui com ``prepare=False``):

	.venv/Scripts/python.exe tools/diagnostico/gui/tempo_regiao.py --project <cópia> [--out tempos.json]
	.venv/Scripts/python.exe tools/diagnostico/gui/tempo_regiao.py --url http://127.0.0.1:8799 --bloqueio

Parte 1 (em processo): para 3 zonas (céu (5,30), relva (44,40), vazia (33,30)) × 2 zooms (lupa l±5 c±8 + 1 célula de
margem a ppc 120; perto l±2 c±3 + 1 a ppc 240) × frio / quente / morno (deslocada 1 célula), cronometra
``board_jpg`` e decompõe-no por monkeypatch das funções de ``src.render`` (``_clean_or_crop``, ``_display_masks`` +
``_fill_transparent``, ``_bleed_rgba``, ``_warp``, ``_depth_px``, ``register_piece``, ``_art_rgb``) e de
``src.server._jpeg``; o resto de ``compose_board`` (alocação, mistura em float32) fica em «resto». Regista os bytes
do JPEG e os MP.

Parte 2 (``--bloqueio``, contra um servidor a correr): durante uma composição fria de uma região, dispara
``/api/status``, ``/api/montar``, ``/api/cell/l/c`` e um ``board.jpg`` já em cache, e mede as latências com e sem
composição a correr (separa o ``rlock``, que só toca nos pedidos de imagem, do GIL, que toca em todos).
"""
import argparse
import json
import os
import statistics
import sys
import threading
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

ZONAS = {"ceu": (5, 30), "relva": (44, 40), "vazia": (33, 30)}
ZOOMS = {"lupa": (5, 8, 120), "perto": (2, 3, 240)}
ROWS, COLS = 47, 64


def regiao(l, c, dl, dc, shift=0):
	"""Região como o cliente a pede: a vista ``l±dl, c±dc`` + 1 célula de margem, presa à grelha."""
	c = c + shift
	return (max(1, l - dl - 1), max(1, c - dc - 1), min(ROWS, l + dl + 1), min(COLS, c + dc + 1))


class Fases:
	"""Acumula tempo por fase (só o fio que compõe: os relógios são por chamada, não por fio)."""

	def __init__(self):
		self.t = {}

	def wrap(self, mod, name, fase):
		f = getattr(mod, name)

		def g(*a, **k):
			t0 = time.perf_counter()
			try:
				return f(*a, **k)
			finally:
				self.t[fase] = self.t.get(fase, 0.0) + time.perf_counter() - t0
		setattr(mod, name, g)


def parte1(project: str) -> list:
	from src import render
	from src import server as S
	fs = Fases()
	for name, fase in (("_clean_or_crop", "ler recorte"), ("_display_masks", "sombra"), ("_fill_transparent", "sombra"),
					   ("_bleed_rgba", "bleed"), ("_warp", "warp"), ("_depth_px", "profundidade"),
					   ("register_piece", "registar"), ("_art_rgb", "arte")):
		fs.wrap(render, name, fase)
	fs.wrap(S, "_jpeg", "jpeg")
	gui = S.Gui(project, prepare=False)
	gui.placements()
	out = []
	for zn, (l, c) in ZONAS.items():
		for zm, (dl, dc, ppc) in ZOOMS.items():
			for estado, shift in (("frio", 0), ("quente", 0), ("morno", 1)):
				if estado == "frio":
					gui._regions.clear()
				reg = regiao(l, c, dl, dc, shift)
				fs.t = {}
				t0 = time.perf_counter()
				data = gui.board_jpg(ppc, reg)
				tot = time.perf_counter() - t0
				n = (reg[2] - reg[0] + 1) * (reg[3] - reg[1] + 1)
				fases = {k: round(v, 3) for k, v in fs.t.items()}
				fases["resto"] = round(tot - sum(fs.t.values()), 3)
				row = {"zona": zn, "zoom": zm, "estado": estado, "regiao": reg, "ppc": ppc, "celulas": n,
					   "mp": round(n * ppc * ppc * 17.9 / 18.5 / 1e6, 2), "kb": round(len(data) / 1024), "s": round(tot, 3),
					   "fases": fases}
				out.append(row)
				print(json.dumps(row, ensure_ascii=False), flush=True)
	return out


def _get(url: str) -> float:
	t0 = time.perf_counter()
	with urllib.request.urlopen(url, timeout=120) as r:
		r.read()
	return time.perf_counter() - t0


def parte2(base: str, reps: int = 5) -> dict:
	"""Latências das rotas sem e com uma composição fria a correr noutro fio (``reps`` regiões frias)."""
	rotas = {"status": "/api/status", "montar": "/api/montar", "cell": "/api/cell/5/30",
			 "board_cache": "/api/board.jpg?ppc=120&region=1,1,5,5"}
	_get(base + rotas["board_cache"])          # põe-na em cache
	for u in rotas.values():
		_get(base + u)
	res = {k: {"sem": [], "com": []} for k in rotas}
	for k, u in rotas.items():
		for _ in range(reps):
			res[k]["sem"].append(_get(base + u))
	comp = []
	for i in range(reps):
		# região fria diferente em cada repetição (relva, perto da vista da lupa)
		reg = f"{36 + i},{30},{46},{50}"
		box = {}
		th = threading.Thread(target=lambda: box.setdefault("t", _get(f"{base}/api/board.jpg?ppc=120&region={reg}&x={time.time()}")))
		th.start()
		time.sleep(0.15)
		for k, u in rotas.items():
			res[k]["com"].append(_get(base + u))
		th.join()
		comp.append(box.get("t"))
	out = {"composicao_s": [round(x, 3) for x in comp]}
	for k, v in res.items():
		out[k] = {"sem_med_ms": round(1000 * statistics.median(v["sem"])), "sem_max_ms": round(1000 * max(v["sem"])),
				  "com_med_ms": round(1000 * statistics.median(v["com"])), "com_max_ms": round(1000 * max(v["com"]))}
	print(json.dumps(out, ensure_ascii=False, indent=1))
	return out


def main(argv=None) -> int:
	ap = argparse.ArgumentParser()
	ap.add_argument("--project")
	ap.add_argument("--url")
	ap.add_argument("--bloqueio", action="store_true")
	ap.add_argument("--out")
	a = ap.parse_args(argv)
	res = {}
	if a.project:
		res["fases"] = parte1(a.project)
	if a.url and a.bloqueio:
		res["bloqueio"] = parte2(a.url.rstrip("/"))
	if a.out:
		with open(a.out, "w", encoding="utf-8") as f:
			json.dump(res, f, ensure_ascii=False, indent=1)
	return 0


if __name__ == "__main__":
	sys.exit(main())
