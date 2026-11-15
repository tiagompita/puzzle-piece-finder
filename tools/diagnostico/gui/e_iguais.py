"""E (DETALHE.md §11.8): a composição do tabuleiro com as peças prontas em cache é a mesma, byte a byte, que a do código
de antes de E, no céu e na relva da cópia real.

Uso: ``python tools/diagnostico/gui/e_iguais.py <repo> <projeto> <saída.json>``: com o código de ``<repo>`` compõe as
regiões céu (1,20–14,40) e relva (34,30–47,50) a ppc 100 e o tabuleiro inteiro a ppc 60 (``compose_board``, camadas arte +
peças, as poses de ``render/placements.json``) e grava o sha1 dos píxeis; com o código novo também com uma
``server.ReadyCache`` (fria e quente) e com uma de orçamento minúsculo. ``--comparar a.json b.json``."""
import hashlib
import json
import sys
import time

REGS = {"ceu_100": ((1, 20, 14, 40), 100), "relva_100": ((34, 30, 47, 50), 100), "tudo_60": (None, 60)}


def run(repo, proj, out):
	sys.path.insert(0, repo)
	from src import render
	from src.state import Project
	pr = Project.open(proj)
	pl = render.load_placements(pr)["placements"] or {}
	res = {}
	variants = [("sem", None)]
	try:
		from src.server import ReadyCache
		rc = ReadyCache(600)
		tiny = ReadyCache(1.0)
		variants += [("cache_fria", rc), ("cache_quente", rc), ("cache_minuscula", tiny)]
	except ImportError:
		pass
	for name, (reg, ppc) in REGS.items():
		for vn, cache in variants:
			kw = {} if cache is None else {"ready": (lambda c: (lambda pid: c.get(pr, pid)))(cache)}
			t0 = time.perf_counter()
			img = render.compose_board(pr, ppc, region=reg, layers=("art", "pieces"), placements=pl, **kw)
			res[f"{name}/{vn}"] = {"sha1": hashlib.sha1(img.tobytes()).hexdigest(), "shape": list(img.shape),
								   "s": round(time.perf_counter() - t0, 2)}
	with open(out, "w", encoding="utf-8") as f:
		json.dump(res, f, indent=1)
	print(json.dumps(res, indent=1))


def comparar(a, b):
	A = json.load(open(a, encoding="utf-8"))
	B = json.load(open(b, encoding="utf-8"))
	ok = True
	for k, v in B.items():
		ref = A[k.split("/")[0] + "/sem"]["sha1"]
		if v["sha1"] != ref:
			ok = False
			print("DIFERENTE", k)
	print("IGUAIS" if ok else "DIFERENTES", len(B), "composições")
	return 0 if ok else 1


if __name__ == "__main__":
	if sys.argv[1] == "--comparar":
		sys.exit(comparar(sys.argv[2], sys.argv[3]))
	run(*sys.argv[1:4])
