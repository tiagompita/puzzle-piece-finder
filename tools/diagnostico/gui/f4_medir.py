"""Critérios 13 e 15 da F4 (F4_PLANO.md §4), no código deste checkout, numa cópia do projeto (nunca o real).

- ``--so m`` (critério 13): servidor real (``python -m src.server``), ranking dos buracos acabado; «Mostrar» de todos os
  grupos soltos; ``POST …/mover`` repetido no maior grupo (``--n-mover``, só as respostas 200 contam) e ``POST
  …/fixar`` em cada grupo, cada fixação desfeita com ``unanchor`` (``/api/confirm``) e o servidor de novo «pronto»
  antes da seguinte. Tempo do lado do cliente (HTTP incluído). Alvos: mover ≤ 0,3 s, fixar ≤ 2,0 s (medianas).
- ``--so p`` (critério 15): um processo novo por medição (``--n-png``), módulos importados, ``Gui(prepare=False)``,
  caches vazias, ficheiros já na cache do sistema: ``Gui.grupo_png`` do maior grupo a frio (tempo) e, noutros processos
  (``--n-mem``), o pico de memória a mais com ``tracemalloc`` (ligado só nesses, o tempo não conta). Alvos: ≤ 0,5 s,
  ≤ 50 MB.

Uso: ``python tools/diagnostico/gui/f4_medir.py <base> <trabalho> <saída.json> [--so mp]``."""
import argparse
import json
import os
import shutil
import statistics as st
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)
import f4_iguais as F  # noqa: E402

G = F.G

CHILD = r"""
import json, sys, time
sys.path.insert(0, {root!r})
mem = {mem!r}
from src import server as SV
from src import grupos as GR
gui = SV.Gui({proj!r}, prepare=False, use_image=False, uploads={up!r}, log=None, queue=False)
gid = max(sorted(s for s in gui.pr.sections if __import__('src.mesa', fromlist=['x']).is_loose(gui.pr, s)),
		  key=lambda s: len(gui.pr.sections[s].cells_local))
if mem:
	import tracemalloc
	tracemalloc.start()
	b0 = tracemalloc.get_traced_memory()[0]
t = time.perf_counter()
data = gui.grupo_png(gid, 0)
s = time.perf_counter() - t
t = time.perf_counter()
gui.grupo_png(gid, 0)
q = time.perf_counter() - t
out = {{"gid": gid, "n": len(gui.pr.sections[gid].cells_local), "frio_s": s, "quente_s": q, "bytes": len(data)}}
if mem:
	out["pico_mb"] = (tracemalloc.get_traced_memory()[1] - b0) / 2**20
print(json.dumps(out))
"""


def med(xs):
	return round(st.median(xs), 4) if xs else None


def run_m(a, res):
	proj = os.path.join(a.work, "proj_m")
	shutil.rmtree(proj, ignore_errors=True)
	shutil.copytree(a.base, proj)
	p, f = F.start(ROOT, proj, os.path.join(a.work, "up"), os.path.join(a.work, "srv_m.log"))
	try:
		body, s1 = G._get("/api/grupos")
		s2 = G._get("/api/grupos")[1]
		res["get_grupos"] = {"primeiro_s": round(s1, 3), "segundo_s": round(s2, 3)}
		gr = json.loads(body)["grupos"]
		for i, g in enumerate(gr):
			F.post(f"/api/grupos/{g['id']}/mostrar", {"centro": [5 + (i % 8) * 5, 5 + (i // 8) * 14]})
		gr = {g["id"]: g for g in G._json("/api/grupos")["grupos"]}
		gid = max(sorted(gr), key=lambda k: gr[k]["n"])
		mv, recusas = [], 0
		for dl, dc in F.DELTAS * 6:
			if len(mv) >= a.n_mover:
				break
			cur = next(g for g in G._json("/api/grupos")["grupos"] if g["id"] == gid)["posicao"]
			t = time.perf_counter()
			s, r = F.post(f"/api/grupos/{gid}/mover", {"l0": cur["l0"] + dl, "c0": cur["c0"] + dc, "rot": cur["rot"]})
			dt = time.perf_counter() - t
			if s == 200:
				mv.append(dt)
			else:
				recusas += 1
		res["mover"] = {"grupo": gid, "n": len(mv), "recusas_409": recusas, "mediana_s": med(mv),
						"max_s": round(max(mv), 4) if mv else None, "alvo_s": 0.3}
		fx = []
		for gid in sorted(gr):
			g = next(x for x in G._json("/api/grupos")["grupos"] if x["id"] == gid)
			if not g["mostrado"] or g.get("sobreposto"):
				fx.append({"grupo": gid, "saltado": "nao_mostrado" if not g["mostrado"] else "sobreposto"})
				continue
			G._wait_ready()
			t = time.perf_counter()
			s, r = F.post(f"/api/grupos/{gid}/fixar", {})
			dt = time.perf_counter() - t
			row = {"grupo": gid, "n": g["n"], "status": s, "s": round(dt, 3), "vizinhas": r.get("vizinhas"),
				   "verificacao_s": r.get("verificacao_s")}
			fx.append(row)
			if s == 200:
				G._wait_ready()
				F.post("/api/confirm", {"acao": "unanchor", "section": gid, "desfaz": True})
				G._wait_ready()
		ok = [x["s"] for x in fx if x.get("status") == 200]
		com = [x["s"] for x in fx if x.get("status") == 200 and x.get("vizinhas") not in (None, "sem_vizinhas")]
		res["fixar"] = {"n": len(ok), "mediana_s": med(ok), "max_s": round(max(ok), 3) if ok else None,
						"com_vizinhas": {"n": len(com), "mediana_s": med(com), "max_s": round(max(com), 3) if com else None},
						"alvo_s": 2.0, "linhas": fx}
	finally:
		G._stop(p, f)
		shutil.rmtree(proj, ignore_errors=True)


def run_p(a, res):
	proj = os.path.join(a.work, "proj_p")
	shutil.rmtree(proj, ignore_errors=True)
	shutil.copytree(a.base, proj)
	up = os.path.join(a.work, "up")

	def child(mem):
		code = CHILD.format(root=ROOT, proj=proj, up=up, mem=mem)
		r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
		line = [x for x in r.stdout.splitlines() if x.startswith("{")]
		if not line:
			raise RuntimeError(r.stderr[-2000:])
		return json.loads(line[-1])
	child(False)                                     # files into the system cache
	t = [child(False) for _ in range(a.n_png)]
	m = [child(True) for _ in range(a.n_mem)]
	res["png"] = {"grupo": t[0]["gid"], "n_pecas": t[0]["n"], "frio_s": [round(x["frio_s"], 3) for x in t],
				  "frio_mediana_s": med([x["frio_s"] for x in t]), "quente_ms": [round(1000 * x["quente_s"], 2) for x in t],
				  "pico_mb": [round(x["pico_mb"], 1) for x in m], "alvo_s": 0.5, "alvo_mb": 50}
	shutil.rmtree(proj, ignore_errors=True)


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("base")
	ap.add_argument("work")
	ap.add_argument("out")
	ap.add_argument("--so", default="mp")
	ap.add_argument("--n-mover", type=int, default=21)
	ap.add_argument("--n-png", type=int, default=5)
	ap.add_argument("--n-mem", type=int, default=3)
	a = ap.parse_args()
	os.makedirs(a.work, exist_ok=True)
	res = {}
	if "m" in a.so:
		run_m(a, res)
	if "p" in a.so:
		run_p(a, res)
	with open(a.out, "w", encoding="utf-8") as fh:
		json.dump(res, fh, indent=1, ensure_ascii=False)
	brief = {k: {kk: vv for kk, vv in v.items() if kk != "linhas"} for k, v in res.items()}
	print(json.dumps(brief, ensure_ascii=False))


if __name__ == "__main__":
	main()
