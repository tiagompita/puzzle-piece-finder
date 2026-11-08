"""Ronda 7 — hipóteses H1–H4 e H6(b) (R7_CRITERIOS.md §2), medidas no estado ATUAL de uma cópia do projeto.

Só leitura (``fit._Cache`` nunca grava). Escreve ``docs/diagnostico/gemeos/r7_hipoteses.json`` e as figuras
``r7_h2_forma.png`` (d1 verdadeiro por zona) e ``r7_h3_imagem.png`` (ΔE próprio vs células aleatórias por zona).

    python tools/diagnostico/gemeos/r7_hipoteses.py --project <cópia>
"""

import argparse
import collections
import json
import os
import sys
import time

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if REPO not in sys.path:
	sys.path.insert(0, REPO)

from src import consistency as C  # noqa: E402
from src import fit as F  # noqa: E402
from src import render as R  # noqa: E402
from src import twin as T  # noqa: E402
from src.locate import CellArt, body_beta_deg, de_cell, pair_locate, render_item, snap_theta  # noqa: E402
from src.state import Project  # noqa: E402

DOC = os.path.join(REPO, "docs", "diagnostico", "gemeos")
SEED = 20261108
K_NEG = 8
P90_ATUAL = 50.0
ZONE_KEY = {"céu": "ceu", "montanha/floresta": "montanha", "vale/aldeia": "vale", "relva": "relva"}


def zone_of(cell):
	return ZONE_KEY.get(F.zone_of(cell), "?")


def wilson(k, n, z=1.96):
	if n == 0:
		return (0.0, 0.0, 1.0)
	p = k / n
	d = 1 + z * z / n
	c = (p + z * z / (2 * n)) / d
	h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
	return (p, max(0.0, c - h), min(1.0, c + h))


def auc(pos, neg):
	"""P(ΔE positivo < ΔE negativo) (empates a meio)."""
	pos, neg = np.asarray(pos, float), np.asarray(neg, float)
	if len(pos) == 0 or len(neg) == 0:
		return float("nan")
	s = 0.0
	for p in pos:
		s += np.sum(p < neg) + 0.5 * np.sum(p == neg)
	return float(s / (len(pos) * len(neg)))


def auc_boot(pos_by_piece, neg_by_piece, n=1000, seed=SEED):
	"""AUC e IC 95 % por bootstrap sobre peças (positivo e os seus negativos juntos)."""
	rng = np.random.default_rng(seed)
	ids = list(pos_by_piece)
	if not ids:
		return dict(auc=None, lo=None, hi=None, n=0)
	a0 = auc([pos_by_piece[i] for i in ids], np.concatenate([neg_by_piece[i] for i in ids]))
	vals = []
	for _ in range(n):
		pick = rng.choice(ids, len(ids), replace=True)
		vals.append(auc([pos_by_piece[i] for i in pick], np.concatenate([neg_by_piece[i] for i in pick])))
	return dict(auc=a0, lo=float(np.percentile(vals, 2.5)), hi=float(np.percentile(vals, 97.5)), n=len(ids))


# ---------------------------------------------------------------- H1
def h1(pr, cal, anchors):
	out = {}
	cache = F._Cache(pr, cal)
	dcache = {}
	sg = F.board_sigma(pr, cache, dcache)
	loose = [p.id for p in pr.loose_pieces()]
	for pid in anchors:
		p = pr.piece(pid)
		cell = tuple(p.celula)
		nbs = [pr.board[nb].get("peca_id") for nb in pr.board.neighbours(cell) if pr.board[nb]["estado"] == "colocada"]
		ev = C.evaluate(pr, pieces=[pid] + [n for n in nbs if n])
		items = [dict(piece=i["piece"], cell=i["cell"], grau=i["grau"], texto=i.get("texto")) for i in ev["items"]]
		row = dict(cell=list(cell), zona=zone_of(cell), estado=p.estado, theta_deg=p.theta_deg, theta_initial=R.initial_theta(pr, pid),
				   seccao_id=p.seccao_id, vizinhas=nbs, consistency=items, consistency_summary=ev["summary"])
		if p.seccao_id and p.seccao_id in pr.sections:
			s = pr.sections[p.seccao_id]
			row["seccao"] = dict(id=s.id, anchor=s.anchor, n_pecas=len(getattr(s, "cells_local", {}) or {}))
		holes = F.hole_queries(pr, cells=[cell], cache=cache, dcache=dcache, exclude_piece=pid)
		if holes and "error" not in sg:
			h = holes[0]
			items_f = F.pool_items(pr, pieces=loose + [pid], cache=cache)
			r = F.rank_hole(h, F.pool_arrays(items_f), calib=cal, sigma=sg["sigma"], top=5)
			ids = [x["id"] for x in r["ranking"]]
			row["buraco"] = dict(m=h.sides.__len__(), n_pool=len(items_f), rank=ids.index(pid) + 1 if pid in ids else None,
								 n_finite=r["n_finite"], d1=r["d1"], d2=r["d2"], margin=r["margin"], confidence=r["confidence"],
								 top5=[dict(id=c["id"], J=c["J"], rot=c["rot"]) for c in r["candidates"]],
								 J_self=next((x["J"] for x in r["ranking"] if x["id"] == pid), None),
								 P0954_rank=(ids.index("P0954") + 1) if "P0954" in ids else None)
		else:
			row["buraco"] = dict(erro="sem vizinhas com forma" if not holes else sg.get("error"))
		out[pid] = row
	return out


# ---------------------------------------------------------------- H2
def h2(pr, t95, part):
	placed = [p for p in pr.pieces.values() if p.estado == "colocada" and p.celula]
	sh = {p.id: pr.shape(p.id) for p in placed}
	ok = [p for p in placed if sh[p.id] is not None and sh[p.id].ok]
	by_cell = {tuple(p.celula): p for p in ok}
	exc = set()
	pairs = []
	for p in ok:
		tw = pr.profile.twin(*p.celula)
		q = by_cell.get(tuple(tw)) if tw else None
		if q is None or q.id <= p.id:
			continue
		if C.twin_exception(pr.profile, p.celula) or C.twin_exception(pr.profile, tw):
			exc.add((p.id, q.id))
			continue
		d, phi = T.shape_distances(sh[p.id], [sh[q.id]])
		same_cls = sh[p.id].cls == sh[q.id].cls
		pairs.append(dict(a=p.id, b=q.id, cell_a=list(p.celula), cell_b=list(q.celula), zona=zone_of(p.celula),
						  scans=[p.scan_id, q.scan_id], d1=float(d[0]), same_cls=same_cls,
						  lado=("S_T" if (p.scan_id in part.get(zone_of(p.celula), {}).get("S_T", []) and q.scan_id in part.get(zone_of(p.celula), {}).get("S_T", []))
								else "S_V" if (p.scan_id in part.get(zone_of(p.celula), {}).get("S_V", []) and q.scan_id in part.get(zone_of(p.celula), {}).get("S_V", [])) else "misto")))
	# não-gémeo mais próximo da mesma classe, entre as colocadas (pool = todas as colocadas com forma)
	ids = [p.id for p in ok]
	cls = {i: sh[i].cls for i in ids}
	twin_of = {}
	for r in pairs:
		twin_of[r["a"]], twin_of[r["b"]] = r["b"], r["a"]
	nn = {}
	for i in ids:
		others = [j for j in ids if j != i and cls[j] == cls[i] and twin_of.get(i) != j]
		if not others:
			continue
		d, _ = T.shape_distances(sh[i], [sh[j] for j in others])
		o = int(np.argmin(d))
		nn[i] = dict(id=others[o], d=float(d[o]), n_same_cls=len(others), n_below_t95=int(np.sum(d <= t95)))
	for r in pairs:
		r["nn_a"], r["nn_b"] = nn.get(r["a"]), nn.get(r["b"])
		r["margem_a"] = (r["nn_a"]["d"] / r["d1"]) if r["nn_a"] and r["d1"] > 0 else None
	# resumo por zona
	res = {}
	for z in ("ceu", "montanha", "vale", "relva"):
		rows = [r for r in pairs if r["zona"] == z]
		d = np.array([r["d1"] for r in rows])
		if len(d) == 0:
			res[z] = dict(n=0)
			continue
		below = [r for r in rows if r["d1"] <= t95]
		marg = [r["margem_a"] for r in rows if r["margem_a"] is not None]
		# negativos mesma classe: fração de pares (i, j) da zona abaixo de t95
		zi = [p.id for p in ok if zone_of(p.celula) == z and p.id in nn]
		n_neg = sum(nn[i]["n_same_cls"] for i in zi)
		k_neg = sum(nn[i]["n_below_t95"] for i in zi)
		res[z] = dict(n=len(rows), same_cls=sum(r["same_cls"] for r in rows), mediana=float(np.median(d)), p90=float(np.percentile(d, 90)),
					  p95=float(np.percentile(d, 95)), max=float(d.max()), frac_le_t95=wilson(len(below), len(rows)),
					  margem_mediana=float(np.median(marg)) if marg else None, margem_lt_1_5=sum(1 for m in marg if m < 1.5),
					  neg_mesma_classe=dict(n=n_neg, abaixo_t95=k_neg, frac=wilson(k_neg, n_neg)),
					  por_lado=dict(collections.Counter(r["lado"] for r in rows)))
	return dict(n_pares=len(pairs), n_excecao_c32c33=len(exc), por_zona=res, pares=pairs)


# ---------------------------------------------------------------- H3 / H4
def h3_h4(pr, art, part):
	rng = np.random.default_rng(SEED)
	mmpp = pr.profile.mm_per_px()
	rows_by_zone = {"ceu": (1, 14), "montanha": (15, 27), "vale": (28, 40), "relva": (41, 47)}
	cells_by_zone = {z: [(l, c) for l in range(a, b + 1) for c in range(1, pr.profile.cols + 1) if art.has_art(l, c)] for z, (a, b) in rows_by_zone.items()}
	placed = [p for p in pr.pieces.values() if p.estado == "colocada" and p.celula]
	out_rows = []
	t0 = time.time()
	for k, p in enumerate(placed):
		sh = pr.shape(p.id)
		rgba = pr.crop_rgba(p.id)
		th = R.initial_theta(pr, p.id)
		if sh is None or not sh.ok or rgba is None or th is None or not art.has_art(*p.celula):
			continue
		z = zone_of(p.celula)
		th_s = snap_theta(sh, th)[0]
		rnd = render_item(rgba, sh, th_s, art, mmpp)
		pos = de_cell(rnd, p.celula[0], p.celula[1], art)["dE"]
		b = body_beta_deg(sh)
		rnd4 = [render_item(rgba, sh, b + 90.0 * m, art, mmpp) for m in range(4)]
		pos4 = min(de_cell(r_, p.celula[0], p.celula[1], art)["dE"] for r_ in rnd4)
		pool = [c for c in cells_by_zone[z] if c != tuple(p.celula)]
		negs = [pool[i] for i in rng.choice(len(pool), min(K_NEG, len(pool)), replace=False)]
		neg = [de_cell(rnd, l, c, art)["dE"] for l, c in negs]
		neg4 = [min(de_cell(r_, l, c, art)["dE"] for r_ in rnd4) for l, c in negs]
		lado = "S_T" if p.scan_id in part.get(z, {}).get("S_T", []) else "S_V" if p.scan_id in part.get(z, {}).get("S_V", []) else "?"
		out_rows.append(dict(piece=p.id, cell=list(p.celula), zona=z, scan_id=p.scan_id, lado=lado, theta=th, theta_log=p.theta_deg,
							 dE_pos=float(pos), dE_pos_min4=float(pos4), dE_neg=[float(v) for v in neg], dE_neg_min4=[float(v) for v in neg4],
							 negs=[list(c) for c in negs]))
		if k % 100 == 0:
			print(f"  H3: {k}/{len(placed)} ({time.time() - t0:.0f} s)", flush=True)
	res = {}
	for z in rows_by_zone:
		rows = [r for r in out_rows if r["zona"] == z and np.isfinite(r["dE_pos"])]
		if not rows:
			res[z] = dict(n=0)
			continue
		pos = {r["piece"]: r["dE_pos"] for r in rows}
		neg = {r["piece"]: np.array([v for v in r["dE_neg"] if np.isfinite(v)]) for r in rows}
		neg = {k_: v for k_, v in neg.items() if len(v)}
		pos = {k_: v for k_, v in pos.items() if k_ in neg}
		a = auc_boot(pos, neg)
		allneg = np.concatenate(list(neg.values()))
		posv = np.array(list(pos.values()))
		pos4 = np.array([r["dE_pos_min4"] for r in rows if r["piece"] in pos])
		neg4 = np.concatenate([np.array([v for v in r["dE_neg_min4"] if np.isfinite(v)]) for r in rows if r["piece"] in pos])
		st = [r for r in rows if r["lado"] == "S_T" and r["piece"] in pos]
		sv = [r for r in rows if r["lado"] == "S_V" and r["piece"] in pos]
		p90_T = float(np.percentile([r["dE_pos"] for r in st], 90)) if st else None
		val = None
		if p90_T is not None and sv:
			kp = sum(1 for r in sv if r["dE_pos"] <= p90_T)
			negv = np.concatenate([np.array([v for v in r["dE_neg"] if np.isfinite(v)]) for r in sv])
			val = dict(n_pos=len(sv), cobertura=wilson(kp, len(sv)), n_neg=int(len(negv)), neg_passam=wilson(int(np.sum(negv <= p90_T)), int(len(negv))),
					   auc=auc_boot({r["piece"]: pos[r["piece"]] for r in sv}, {r["piece"]: neg[r["piece"]] for r in sv}))
		res[z] = dict(n=len(pos), n_neg=int(len(allneg)), auc=a, pos_mediana=float(np.median(posv)), pos_p90=float(np.percentile(posv, 90)),
					  neg_mediana=float(np.median(allneg)), neg_p10=float(np.percentile(allneg, 10)),
					  neg_passam_50=wilson(int(np.sum(allneg <= P90_ATUAL)), int(len(allneg))),
					  pos_passam_50=wilson(int(np.sum(posv <= P90_ATUAL)), int(len(posv))),
					  h4=dict(pos_delta_min4=float(np.mean(posv - pos4)), neg_delta_min4=float(np.mean(allneg - neg4)),
							  neg_passam_50_min4=wilson(int(np.sum(neg4 <= P90_ATUAL)), int(len(neg4))),
							  auc_min4=auc(pos4, neg4)),
					  afinacao=dict(n_S_T=len(st), p90_S_T=p90_T, n_S_V=len(sv), validacao=val))
	# H4 (b): gémeas pendentes com âncora sem theta_deg e com θ por initial_theta
	pend = pr.pending_twins()
	n_none = [q.id for q, _ in pend if q.theta_deg is None]
	n_rec = [pid for pid in n_none if R.initial_theta(pr, pid) is not None]
	return dict(por_zona=res, n_pecas=len(out_rows), pendentes=dict(n=len(pend), theta_none=len(n_none), theta_recuperavel=len(n_rec))), out_rows


# ---------------------------------------------------------------- H6(b)
def h6b(pr, art):
	"""Pares E-sym A1↔B2 (GT por casa, scans S0001/S0003): posição da célula certa com a chamada atual de
	``pair_locate`` (θ_A = 0, sem shape: 1 rotação) e com 4 rotações + shape."""
	rows = []
	gt = [p for p in pr.pieces.values() if p.estado == "colocada" and p.celula and p.scan_id == "S0001"]
	for a in gt:
		tw = pr.profile.twin(*a.celula)
		o = pr.board[tw]
		if o["estado"] != "colocada" or not o.get("peca_id"):
			continue
		b = pr.piece(o["peca_id"])
		sa, sb = pr.shape(a.id), pr.shape(b.id)
		ra, rb = pr.crop_rgba(a.id), pr.crop_rgba(b.id)
		if sa is None or sb is None or ra is None or rb is None or not sa.ok or not sb.ok:
			continue
		d, phi = T.shape_distances(sa, [sb])
		phi = float(phi[0])
		cur = pair_locate({"rgba": ra, "theta_deg": 0.0, "phi_deg": 0.0}, {"rgba": rb, "theta_deg": 0.0, "phi_deg": phi}, pr.profile, art, topk=3)
		new = pair_locate({"rgba": ra, "shape": sa, "theta_deg": None, "phi_deg": 0.0}, {"rgba": rb, "shape": sb, "theta_deg": 0.0, "phi_deg": phi}, pr.profile, art, topk=3)
		def rank_of(res):
			sm = res["score_map"]
			v = sm[a.celula[0] - 1, a.celula[1] - 1]
			if not np.isfinite(v):
				return None, int(np.isfinite(sm).sum())
			return int(np.sum(sm < v)) + 1, int(np.isfinite(sm).sum())
		rc, nc = rank_of(cur)
		rn, nn = rank_of(new)
		rows.append(dict(a=a.id, b=b.id, cell=list(a.celula), d1=float(d[0]), rank_atual=rc, n_cells_atual=nc, rank_4rot=rn, n_cells_4rot=nn,
						 top3_atual=[c["cell"] for c in cur["cells"]], top3_4rot=[c["cell"] for c in new["cells"]]))
	def summ(key):
		r = [x[key] for x in rows if x[key] is not None]
		return dict(n=len(r), mediana=float(np.median(r)) if r else None, top1=sum(1 for v in r if v == 1), top10=sum(1 for v in r if v <= 10))
	return dict(n=len(rows), atual=summ("rank_atual"), rot4=summ("rank_4rot"), pares=rows)


# ---------------------------------------------------------------- figuras
def figures(h2res, h3rows):
	try:
		import matplotlib
		matplotlib.use("Agg")
		import matplotlib.pyplot as plt
	except Exception as e:  # noqa: BLE001
		print("sem matplotlib:", e)
		return []
	outs = []
	zones = ("ceu", "montanha", "vale", "relva")
	fig, axs = plt.subplots(1, 4, figsize=(16, 3.6), sharey=False)
	for ax, z in zip(axs, zones):
		d = [r["d1"] for r in h2res["pares"] if r["zona"] == z]
		ax.hist(d, bins=np.arange(0, 3.05, 0.1), color="#4a7", alpha=0.8)
		ax.axvline(0.507, color="k", ls="--", lw=1, label="t95 0,507")
		ax.set_title(f"{z}: n = {len(d)} pares gémeos colocados")
		ax.set_xlabel("d1 free (mm)")
	axs[0].legend()
	fig.suptitle("H2 — distância free dos pares gémeos verdadeiros (peças colocadas), por zona; marcas: P1238 0,477 (vale), P1014 0,514 (relva)")
	axs[2].axvline(0.477, color="r", lw=2)
	axs[3].axvline(0.514, color="r", lw=2)
	p = os.path.join(DOC, "r7_h2_forma.png")
	fig.tight_layout()
	fig.savefig(p, dpi=110)
	outs.append(p)
	fig, axs = plt.subplots(1, 4, figsize=(16, 3.6))
	for ax, z in zip(axs, zones):
		rows = [r for r in h3rows if r["zona"] == z]
		pos = [r["dE_pos"] for r in rows if np.isfinite(r["dE_pos"])]
		neg = [v for r in rows for v in r["dE_neg"] if np.isfinite(v)]
		bins = np.arange(0, 105, 2.5)
		ax.hist(neg, bins=bins, color="#999", alpha=0.6, density=True, label=f"células aleatórias da zona (n = {len(neg)})")
		ax.hist(pos, bins=bins, color="#36c", alpha=0.7, density=True, label=f"própria célula (n = {len(pos)})")
		ax.axvline(50, color="k", ls="--", lw=1)
		ax.set_title(z)
		ax.set_xlabel("ΔE (de_cell)")
		ax.legend(fontsize=7)
	fig.suptitle("H3 — ΔE da peça colocada na própria célula vs 8 células aleatórias da mesma zona (θ previsto); tracejado = limiar atual 50")
	p = os.path.join(DOC, "r7_h3_imagem.png")
	fig.tight_layout()
	fig.savefig(p, dpi=110)
	outs.append(p)
	return outs


def main(argv=None):
	ap = argparse.ArgumentParser()
	ap.add_argument("--project", required=True)
	ap.add_argument("--gt", default=os.path.join(DOC, "r7_gt.json"))
	ap.add_argument("--out", default=os.path.join(DOC, "r7_hipoteses.json"))
	ap.add_argument("--skip", default="", help="hipóteses a saltar, ex. h1,h6")
	args = ap.parse_args(argv)
	skip = set(args.skip.split(",")) if args.skip else set()
	t0 = time.time()
	pr = Project.open(args.project)
	art = CellArt.load(pr.profile, REPO)
	cal = F.calibration(pr)
	t95 = float(pr.profile.calibration["silhueta_silhueta"]["t95"])
	part = {}
	if os.path.exists(args.gt):
		part0 = json.load(open(args.gt, encoding="utf-8")).get("particao", {})
		part = {ZONE_KEY.get(z, z): v for z, v in part0.items()}
	out = dict(t=time.strftime("%Y-%m-%dT%H:%M:%S"), project=os.path.abspath(args.project), seed=SEED, k_neg=K_NEG)
	if "h1" not in skip:
		out["h1"] = h1(pr, cal, ["P0826", "P0125"])
		print("H1:", json.dumps({k: dict(consistency=[i["grau"] for i in v["consistency"]], buraco=v.get("buraco", {}).get("rank"), conf=v.get("buraco", {}).get("confidence"), P0954=v.get("buraco", {}).get("P0954_rank")) for k, v in out["h1"].items()}, ensure_ascii=False), f"({time.time() - t0:.0f} s)", flush=True)
	if "h2" not in skip:
		out["h2"] = h2(pr, t95, part)
		print("H2:", out["h2"]["n_pares"], "pares;", json.dumps({z: {k: v for k, v in d.items() if k in ("n", "mediana", "p95", "max", "frac_le_t95", "neg_mesma_classe")} for z, d in out["h2"]["por_zona"].items()}, ensure_ascii=False), f"({time.time() - t0:.0f} s)", flush=True)
	h3rows = []
	if "h3" not in skip:
		out["h3"], h3rows = h3_h4(pr, art, part)
		print("H3/H4:", json.dumps({z: {k: v for k, v in d.items() if k in ("n", "auc", "pos_p90", "neg_passam_50", "h4")} for z, d in out["h3"]["por_zona"].items()}, ensure_ascii=False), out["h3"]["pendentes"], f"({time.time() - t0:.0f} s)", flush=True)
	if "h6" not in skip:
		out["h6b"] = h6b(pr, art)
		print("H6(b):", out["h6b"]["atual"], out["h6b"]["rot4"], f"({time.time() - t0:.0f} s)", flush=True)
	out["figuras"] = figures(out.get("h2", dict(pares=[])), h3rows) if ("h2" not in skip and "h3" not in skip) else []
	out["h3_rows"] = h3rows
	out["segundos"] = round(time.time() - t0, 1)
	with open(args.out, "w", encoding="utf-8") as f:
		json.dump(out, f, ensure_ascii=False, indent=1, default=lambda o: None if (isinstance(o, float) and not np.isfinite(o)) else (o.item() if hasattr(o, "item") else str(o)))
	print("escrito", args.out, out["figuras"])
	return 0


if __name__ == "__main__":
	sys.exit(main())
