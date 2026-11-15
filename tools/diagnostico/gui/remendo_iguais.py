"""Remendo das regiões (DETALHE.md §13.7): numa cópia do projeto real, depois de cada escrita ao acaso (semente fixa), o JPEG
que o servidor serve (remendado sobre a região guardada, ou composto inteiro) é igual byte a byte ao de um servidor
acabado de abrir sobre o mesmo projeto (composição a frio).

Uso: ``python tools/diagnostico/gui/remendo_iguais.py <base> <trabalho> <saída.json> [--n 12] [--semente 20261115]``.
Copia ``<base>`` para ``<trabalho>/proj`` (``shutil.copytree``; nunca o projeto real). Regiões céu (1,20–14,40) e relva
(34,30–47,50) a ppc 100. Escritas: colocar uma solta numa célula vazia da região com vizinha colocada, desfazer a última
colocação, gravar / repor a pose manual de uma peça colocada da região, tirar do lugar uma peça da região. O ranking dos
buracos e as suspeitas depois de cada escrita ficam desligados (não entram no raster; só poupam tempo)."""
import argparse
import json
import os
import random
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

REGS = {"ceu": (1, 20, 14, 40), "relva": (34, 30, 47, 50)}
PPC = 100


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("base")
	ap.add_argument("work")
	ap.add_argument("out")
	ap.add_argument("--n", type=int, default=12)
	ap.add_argument("--semente", type=int, default=20261115)
	a = ap.parse_args()
	from fastapi.testclient import TestClient
	from src import server as S
	proj = os.path.join(a.work, "proj")
	shutil.rmtree(proj, ignore_errors=True)
	shutil.copytree(a.base, proj)
	gui = S.Gui(proj, prepare=False, use_image=False, uploads=os.path.join(a.work, "up"), log=None, queue=False)
	gui.holes_json = lambda **k: {}
	gui._suspeitas_bg = lambda: None
	cl = TestClient(S.create_app(gui))
	rnd = random.Random(a.semente)
	pr = gui.pr

	def in_reg(cell, reg):
		return reg[0] <= cell[0] <= reg[2] and reg[1] <= cell[1] <= reg[3]

	def placed_in(reg):
		return sorted(pid for pid, p in pr.pieces.items() if p.estado == "colocada" and p.celula and in_reg(p.celula, reg))

	def empty_with_neighbour(reg):
		out = []
		for l in range(reg[0], reg[2] + 1):
			for c in range(reg[1], reg[3] + 1):
				if pr.board[(l, c)]["estado"] == "vazia" and any(pr.board[q]["estado"] == "colocada" for q in pr.board.neighbours((l, c))):
					out.append((l, c))
		return out

	def cold(reg):
		g = S.Gui(proj, prepare=False, use_image=False, uploads=os.path.join(a.work, "up_frio"), log=None, queue=False)
		try:
			return g.board_jpg(PPC, reg)
		finally:
			g.stop()

	def post(url, body):
		r = cl.post(url, json=body)
		if r.status_code != 200:
			raise RuntimeError(f"{url} {body}: {r.status_code} {r.text[:300]}")
		return r.json()

	for reg in REGS.values():                   # the bases (whole compositions)
		gui.board_jpg(PPC, reg)
	loose = sorted(pid for pid, p in pr.pieces.items() if p.estado == "solta")
	rows, last_placed, posed = [], [], []
	kinds = ["colocar", "colocar", "desfazer", "pose_gravar", "pose_repor", "tirar"]
	k = 0
	while k < a.n:
		kind = rnd.choice(kinds)
		zone = rnd.choice(sorted(REGS))
		reg = REGS[zone]
		desc = None
		if kind == "colocar":
			cells = empty_with_neighbour(reg)
			if not cells:
				continue
			cell, pid = rnd.choice(cells), loose.pop(rnd.randrange(len(loose)))
			post("/api/confirm", {"acao": "place", "piece": pid, "cell": list(cell), "origin": "manual"})
			last_placed.append(pid)
			desc = {"piece": pid, "cell": list(cell)}
		elif kind == "desfazer":
			if not last_placed:
				continue
			pid = last_placed.pop()
			post("/api/confirm", {"acao": "unplace", "piece": pid, "desfaz": True})
			loose.append(pid)
			desc = {"piece": pid}
		elif kind == "pose_gravar":
			pid = rnd.choice(placed_in(reg))
			post(f"/api/pieces/{pid}/pose", {"theta_deg": round(rnd.uniform(-3, 3), 2), "dx_mm": round(rnd.uniform(-0.6, 0.6), 2),
											 "dy_mm": round(rnd.uniform(-0.6, 0.6), 2)})
			posed.append(pid)
			desc = {"piece": pid}
		elif kind == "pose_repor":
			if not posed:
				continue
			pid = posed.pop()
			post(f"/api/pieces/{pid}/pose/repor", {})
			desc = {"piece": pid}
		else:
			pid = rnd.choice([q for q in placed_in(reg) if q not in posed])
			post("/api/confirm", {"acao": "unplace", "piece": pid})
			desc = {"piece": pid, "cell": None}
		k += 1
		row = {"escrita": k, "tipo": kind, "zona_da_escrita": zone, **desc, "regioes": {}}
		for name, rg in REGS.items():
			st0 = gui.patch_json()
			t0 = time.perf_counter()
			served = gui.board_jpg(PPC, rg)
			s = time.perf_counter() - t0
			st1 = gui.patch_json()
			modo = next((m for m in ("remendos", "inteiras", "iguais") if st1[m] > st0[m]), "acerto_jpeg")
			ref = cold(rg)
			row["regioes"][name] = {"modo": modo, "igual": served == ref, "s": round(s, 3), "bytes": len(served)}
		rows.append(row)
		print(json.dumps(row, ensure_ascii=False), flush=True)
	res = {"n_escritas": len(rows), "linhas": rows, "remendo": gui.patch_json(),
		   "n_diferentes": sum(1 for r in rows for v in r["regioes"].values() if not v["igual"]),
		   "por_modo": {}}
	for r in rows:
		for v in r["regioes"].values():
			res["por_modo"][v["modo"]] = res["por_modo"].get(v["modo"], 0) + 1
	with open(a.out, "w", encoding="utf-8") as f:
		json.dump(res, f, indent=1, ensure_ascii=False)
	print(json.dumps({k: res[k] for k in ("n_escritas", "n_diferentes", "por_modo", "remendo")}, ensure_ascii=False))
	gui.stop()
	shutil.rmtree(proj, ignore_errors=True)


if __name__ == "__main__":
	main()
