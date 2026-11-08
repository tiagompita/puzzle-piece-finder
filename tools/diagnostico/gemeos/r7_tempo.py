"""Ronda 7 — tempo da consulta completa (R7_CRITERIOS.md §5): medir antes de otimizar.

Corre ``query.run_query`` numa CÓPIA do projeto em variantes, repondo o estado (log, pares, board, fetch)
antes de cada uma, e conta as chamadas a ``de_cell`` feitas pelo gémeo:

- ``atual``      pool de hoje, código como está;
- ``pool300``    pool reduzido a <= 300 soltas (lotes 6–8 fora do pool), código como está;
- ``pool300_sem_pctl``  o mesmo pool com ``twin.PCTL_MAX_N = 0``;
- ``atual_sem_pctl``    pool de hoje com ``PCTL_MAX_N = 0``.

Guarda o ``fetch.json`` de cada variante em ``$PPF_SCRATCH/r7_fetch_<variante>.json`` e compara as propostas
(peça, célula, decisão, d1_mm, margin, dE) entre pares de variantes com o mesmo pool (invariante).

    python tools/diagnostico/gemeos/r7_tempo.py --project <cópia> [--variants atual,pool300,...] [--reps 2]
"""

import argparse
import json
import logging
import os
import re
import shutil
import sys
import time
import types

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if REPO not in sys.path:
	sys.path.insert(0, REPO)

from src import activity  # noqa: E402
from src import query as Q  # noqa: E402
from src import twin as T  # noqa: E402
from src.state import Project  # noqa: E402

SCRATCH = os.environ.get("PPF_SCRATCH", os.path.join(REPO, "docs", "diagnostico", "gemeos"))
STATE_FILES = ("log.jsonl", "pairs.json", "board.json", "fetch.json", "fetch.md", "project.json")
POOL300_LOTES_FORA = {6, 7, 8}


class Capture(logging.Handler):
	def __init__(self):
		super().__init__()
		self.lines = []

	def emit(self, record):
		self.lines.append(record.getMessage())


def snapshot(project_dir, snap_dir):
	os.makedirs(snap_dir, exist_ok=True)
	for f in STATE_FILES:
		p = os.path.join(project_dir, f)
		if os.path.exists(p):
			shutil.copy2(p, os.path.join(snap_dir, f))


def restore(project_dir, snap_dir):
	for f in STATE_FILES:
		s = os.path.join(snap_dir, f)
		d = os.path.join(project_dir, f)
		if os.path.exists(s):
			shutil.copy2(s, d)
		elif os.path.exists(d):
			os.remove(d)


def parse_steps(line):
	m = re.search(r"em ([\d.]+) s; passos: (.*)$", line)
	if not m:
		return None, {}
	steps = {}
	for part in m.group(2).split(", "):
		name, val = part.rsplit(" ", 1)
		steps[name] = float(val)
	return float(m.group(1)), steps


def run_variant(project_dir, name, pctl_max_n, lotes_fora):
	T.PCTL_MAX_N = pctl_max_n
	pr = Project.open(project_dir)
	if lotes_fora:
		orig = pr.loose_pieces

		def loose_pieces(self, lote=None, _orig=orig):
			return [p for p in _orig(lote) if p.lote not in lotes_fora]
		pr.loose_pieces = types.MethodType(loose_pieces, pr)
	n_loose = len(pr.loose_pieces())
	calls = {"de_cell": 0}
	orig_de = T.de_cell

	def counted(*a, **k):
		calls["de_cell"] += 1
		return orig_de(*a, **k)
	T.de_cell = counted
	cap = Capture()
	logging.getLogger(activity.LOGGER).addHandler(cap)
	logging.getLogger(activity.LOGGER).setLevel(logging.INFO)
	t0 = time.perf_counter()
	try:
		entries = Q.run_query(pr, use_image=True, write=True, log=False)
	finally:
		T.de_cell = orig_de
		logging.getLogger(activity.LOGGER).removeHandler(cap)
	wall = time.perf_counter() - t0
	line = next((l for l in cap.lines if l.startswith("consulta ")), "")
	total, steps = parse_steps(line)
	fj = os.path.join(project_dir, "fetch.json")
	out_fj = os.path.join(SCRATCH, f"r7_fetch_{name}.json")
	shutil.copy2(fj, out_fj)
	return dict(variante=name, pctl_max_n=pctl_max_n, n_soltas=n_loose, n_pendentes=len(pr.pending_twins()),
				n_propostas=sum(1 for e in entries if e.get("piece")), wall_s=round(wall, 1), total_s=total, passos=steps,
				de_cell_calls=calls["de_cell"], linha=line, fetch=out_fj)


def proposals_key(fj):
	d = json.load(open(fj, encoding="utf-8"))
	ent = {}
	for e in d.get("entries", []):
		if e.get("piece"):
			ent[(e["origin"], e["piece"], tuple(e["cell"]) if e.get("cell") else None)] = (e.get("decision"), e.get("d1_mm"), e.get("margin"), e.get("dE"))
	sup = {}
	for s in d.get("suprimidas", []):
		sup[(s.get("origin"), s.get("query"), s.get("piece"), tuple(s["cell"]) if s.get("cell") else None)] = (s.get("decision_shape"), s.get("d1_mm"))
	return ent, sup


def diff(fa, fb, tol=1e-9):
	ea, sa = proposals_key(fa)
	eb, sb = proposals_key(fb)
	out = dict(n_a=len(ea), n_b=len(eb), so_em_a=sorted(map(str, set(ea) - set(eb))), so_em_b=sorted(map(str, set(eb) - set(ea))), diferentes=[])
	for k in set(ea) & set(eb):
		va, vb = ea[k], eb[k]
		for name, x, y in zip(("decision", "d1_mm", "margin", "dE"), va, vb):
			if isinstance(x, (int, float)) and isinstance(y, (int, float)):
				if abs(float(x) - float(y)) > tol:
					out["diferentes"].append(dict(k=str(k), campo=name, a=x, b=y))
			elif x != y:
				out["diferentes"].append(dict(k=str(k), campo=name, a=x, b=y))
	out["suprimidas"] = dict(n_a=len(sa), n_b=len(sb), iguais=sa == sb)
	out["identicas"] = not out["so_em_a"] and not out["so_em_b"] and not out["diferentes"] and sa == sb
	return out


def main(argv=None):
	ap = argparse.ArgumentParser()
	ap.add_argument("--project", required=True)
	ap.add_argument("--variants", default="atual,pool300,pool300_sem_pctl,atual_sem_pctl")
	ap.add_argument("--reps", type=int, default=1)
	ap.add_argument("--out", default=os.path.join(SCRATCH, "r7_tempo.json"))
	ap.add_argument("--tag", default="")
	args = ap.parse_args(argv)
	pd = os.path.abspath(args.project)
	snap = os.path.join(SCRATCH, "r7_tempo_snapshot")
	if not os.path.exists(os.path.join(snap, "log.jsonl")):
		snapshot(pd, snap)
	spec = {"atual": (300, None), "pool300": (300, POOL300_LOTES_FORA), "pool300_sem_pctl": (0, POOL300_LOTES_FORA), "atual_sem_pctl": (0, None)}
	results = []
	for name in args.variants.split(","):
		pctl, fora = spec[name]
		for r in range(args.reps):
			restore(pd, snap)
			res = run_variant(pd, name + (args.tag or ""), pctl, fora)
			res["rep"] = r
			results.append(res)
			print(json.dumps({k: v for k, v in res.items() if k not in ("linha", "fetch")}, ensure_ascii=False), flush=True)
	restore(pd, snap)
	out = dict(t=time.strftime("%Y-%m-%dT%H:%M:%S"), project=pd, results=results, diffs={})
	by = {r["variante"]: r["fetch"] for r in results}
	for a, b in (("pool300" + args.tag, "pool300_sem_pctl" + args.tag), ("atual" + args.tag, "atual_sem_pctl" + args.tag)):
		if a in by and b in by:
			out["diffs"][f"{a} vs {b}"] = diff(by[a], by[b])
			print(a, "vs", b, "idênticas:", out["diffs"][f"{a} vs {b}"]["identicas"], flush=True)
	prev = {}
	if os.path.exists(args.out):
		prev = json.load(open(args.out, encoding="utf-8"))
	prev.setdefault("corridas", []).append(out)
	with open(args.out, "w", encoding="utf-8") as f:
		json.dump(prev, f, ensure_ascii=False, indent=1)
	print("escrito", args.out)
	return 0


if __name__ == "__main__":
	sys.exit(main())
