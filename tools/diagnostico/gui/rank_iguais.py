"""Parte 1 (DETALHE.md §11.7): o ranking dos buracos é o mesmo com o código antigo e o novo, a frio e com os lados lidos
do disco.

Uso: ``python tools/diagnostico/gui/rank_iguais.py <repo> <projeto base> <cópia> <saída.json> [--duas]``: com o código de
``<repo>`` corre ``fit.rank_all`` numa cópia nova (a frio, num processo novo); com ``--duas`` corre-o uma segunda vez
noutro objeto ``Project`` e com as caches de lados em memória esvaziadas (a leitura de ``render/fit/sides.npz``).
``--sem-tiras`` apaga ``render/fit/strips.npz`` da cópia (todas as tiras medidas de novo). Grava o resultado sem o campo ``tiras`` (tempos e contagens de cache) e os segundos. ``--comparar a.json b.json``."""
import json
import shutil
import guarda  # noqa: E402 (tools/diagnostico/gui/guarda.py)
import sys
import time


def run(repo, base, work, out, duas=False, sem_tiras=False):
	sys.path.insert(0, repo)
	guarda.rmtree(work, ignore_errors=True)
	guarda.copytree(base, work)
	if sem_tiras:                  # every strip measured anew (the old strips.npz may hold stale ones: §11.7)
		import os
		os.remove(os.path.join(work, "render", "fit", "strips.npz"))
	from src import fit as F
	from src.state import Project
	res = []
	for k in range(2 if duas else 1):
		if k and hasattr(F, "SidesStore"):
			with F.SidesStore._stores_lock:
				F.SidesStore._stores.clear()
		pr = Project.open(work)
		t0 = time.perf_counter()
		r = F.rank_all(pr)
		secs = time.perf_counter() - t0
		tiras = r.pop("tiras", None)
		res.append({"segundos": round(secs, 1), "tiras": tiras, "r": r})
	with open(out, "w", encoding="utf-8") as f:
		json.dump(res, f, ensure_ascii=False, default=str)


def comparar(a, b):
	A = json.load(open(a, encoding="utf-8"))
	B = json.load(open(b, encoding="utf-8"))
	ref = json.dumps(A[0]["r"], sort_keys=True)
	ok = all(json.dumps(x["r"], sort_keys=True) == ref for x in A + B)
	print("IGUAIS" if ok else "DIFERENTES", [x["segundos"] for x in A], [x["segundos"] for x in B])
	return 0 if ok else 1


if __name__ == "__main__":
	if sys.argv[1] == "--comparar":
		sys.exit(comparar(sys.argv[2], sys.argv[3]))
	run(*sys.argv[1:5], duas="--duas" in sys.argv, sem_tiras="--sem-tiras" in sys.argv)
