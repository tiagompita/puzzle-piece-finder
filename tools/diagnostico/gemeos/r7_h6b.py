"""Ronda 7 — H6(b): localização conjunta de um par de gémeas pela imagem, 1 rotação (chamada atual de
``query._step_pairs``: θ_A = 0, sem shape) vs 4 rotações + shape (protótipo), medida nos pares gémeos entre
peças colocadas (GT de H2) fora da fila 47 (sem arte). Os 20 pares E-sym A1↔B2 não servem: a gémea está na
fila 47, fora do ficheiro da arte (score inf nas duas variantes).

    python tools/diagnostico/gemeos/r7_h6b.py --project <cópia> [--n-por-zona 20]
"""

import argparse
import json
import os
import sys
import time

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if REPO not in sys.path:
	sys.path.insert(0, REPO)

from src import fit as F  # noqa: E402
from src import twin as T  # noqa: E402
from src.locate import CellArt, pair_locate  # noqa: E402
from src.state import Project  # noqa: E402

DOC = os.path.join(REPO, "docs", "diagnostico", "gemeos")
ZONE_KEY = {"céu": "ceu", "montanha/floresta": "montanha", "vale/aldeia": "vale", "relva": "relva"}


def main(argv=None):
	ap = argparse.ArgumentParser()
	ap.add_argument("--project", required=True)
	ap.add_argument("--n-por-zona", type=int, default=20)
	ap.add_argument("--seed", type=int, default=20261108)
	ap.add_argument("--out", default=os.path.join(DOC, "r7_hipoteses.json"))
	args = ap.parse_args(argv)
	pr = Project.open(args.project)
	art = CellArt.load(pr.profile, REPO)
	rng = np.random.default_rng(args.seed)
	placed = {tuple(p.celula): p for p in pr.pieces.values() if p.estado == "colocada" and p.celula}
	pairs = []
	for cell, a in placed.items():
		tw = pr.profile.twin(*cell)
		b = placed.get(tuple(tw)) if tw else None
		if b is None or a.id >= b.id or not art.has_art(*cell) or not art.has_art(*tw):
			continue
		sa, sb = pr.shape(a.id), pr.shape(b.id)
		if sa is None or sb is None or not sa.ok or not sb.ok or pr.crop_rgba(a.id) is None or pr.crop_rgba(b.id) is None:
			continue
		pairs.append((ZONE_KEY.get(F.zone_of(cell), "?"), a, b))
	by = {}
	for z, a, b in pairs:
		by.setdefault(z, []).append((a, b))
	sample = []
	for z, lst in sorted(by.items()):
		idx = rng.choice(len(lst), min(args.n_por_zona, len(lst)), replace=False)
		sample += [(z, lst[i][0], lst[i][1]) for i in sorted(idx)]
	print({z: len(v) for z, v in by.items()}, "amostra", len(sample), flush=True)
	rows = []
	t0 = time.time()
	for k, (z, a, b) in enumerate(sample):
		sa, sb = pr.shape(a.id), pr.shape(b.id)
		ra, rb = pr.crop_rgba(a.id), pr.crop_rgba(b.id)
		d, phi = T.shape_distances(sa, [sb])
		phi = float(phi[0])
		cur = pair_locate({"rgba": ra, "theta_deg": 0.0, "phi_deg": 0.0}, {"rgba": rb, "theta_deg": 0.0, "phi_deg": phi}, pr.profile, art, topk=3)
		new = pair_locate({"rgba": ra, "shape": sa, "theta_deg": None, "phi_deg": 0.0}, {"rgba": rb, "shape": sb, "theta_deg": 0.0, "phi_deg": phi}, pr.profile, art, topk=3)

		def rank_of(res):
			sm = res["score_map"]
			v = sm[a.celula[0] - 1, a.celula[1] - 1]
			n = int(np.isfinite(sm).sum())
			return (None if not np.isfinite(v) else int(np.sum(sm < v)) + 1), n
		rc, nc = rank_of(cur)
		rn, nn = rank_of(new)
		rows.append(dict(zona=z, a=a.id, b=b.id, cell=list(a.celula), d1=float(d[0]), rank_atual=rc, n_cells_atual=nc, rank_4rot=rn, n_cells_4rot=nn,
						 top3_atual=[list(c["cell"]) for c in cur["cells"]], top3_4rot=[list(c["cell"]) for c in new["cells"]]))
		if k % 10 == 0:
			print(f"  {k}/{len(sample)} ({time.time() - t0:.0f} s)", flush=True)

	def summ(key, rws):
		r = [x[key] for x in rws if x[key] is not None]
		return dict(n=len(rws), n_finito=len(r), mediana=float(np.median(r)) if r else None, top1=sum(1 for v in r if v == 1),
					top3=sum(1 for v in r if v <= 3), top10=sum(1 for v in r if v <= 10))
	res = dict(n=len(rows), esym_nota="os 20 pares E-sym A1↔B2 têm a gémea na fila 47, sem arte: score inf nas duas variantes (não medíveis)",
			   atual=summ("rank_atual", rows), rot4=summ("rank_4rot", rows),
			   por_zona={z: dict(atual=summ("rank_atual", [r for r in rows if r["zona"] == z]), rot4=summ("rank_4rot", [r for r in rows if r["zona"] == z])) for z in by},
			   pares=rows)
	print(json.dumps({k: v for k, v in res.items() if k != "pares"}, ensure_ascii=False, indent=1))
	h = json.load(open(args.out, encoding="utf-8")) if os.path.exists(args.out) else {}
	h["h6b"] = res
	with open(args.out, "w", encoding="utf-8") as f:
		json.dump(h, f, ensure_ascii=False, indent=1)
	return 0


if __name__ == "__main__":
	sys.exit(main())
