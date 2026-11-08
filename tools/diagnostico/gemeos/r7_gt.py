"""Ronda 7 — verdade de terreno das propostas de gémea/par (R7_CRITERIOS.md §1, §2 H5/H6(a), §3).

Só leitura do projeto dado (usar uma CÓPIA com os ativos refeitos: `render.rebuild_stale`). Para cada
colocação por gémea (``placed`` com origem ``gemeo``) e para as 2 gémeas rejeitadas, reabre o projeto
**à data** (log truncado num diretório temporário com os mesmos ``pieces/``/``crops/``) e volta a correr
``find_twin`` com os limiares do perfil, para recuperar d1 / d2 / margem / ΔE / decisão, as vizinhas
colocadas da célula e o custo de encaixe (``fit.side_costs``) na pose prevista. Escreve
``docs/diagnostico/gemeos/r7_gt.json`` e imprime o resumo.

    python tools/diagnostico/gemeos/r7_gt.py --project <cópia> [--tmp <dir>] [--out r7_gt.json]
"""

import argparse
import collections
import json
import os
import shutil
import sys
import time

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if REPO not in sys.path:
	sys.path.insert(0, REPO)

from src import fit as F  # noqa: E402
from src import query as Q  # noqa: E402
from src import render as R  # noqa: E402
from src import twin as T  # noqa: E402
from src.locate import CellArt  # noqa: E402
from src.state import Project, read_log  # noqa: E402

DOC = os.path.join(REPO, "docs", "diagnostico", "gemeos")
MODALITY = Q.MODALITY
TOPK = Q.TOPK
DIRS = F.DIRS


def zone_of(cell):
	return F.zone_of(cell) if cell is not None else None


def zone_group(cell):
	return "ceu" if zone_of(cell) == "céu" else "fora_do_ceu"


# ---------------------------------------------------------------- projeto à data
def make_tmp(src, tmp):
	"""Cópia leve do projeto: metadados + pieces/ + crops/ + photos/ + scans/ (sem render/, sem log)."""
	if os.path.isdir(tmp):
		shutil.rmtree(tmp)
	os.makedirs(tmp)
	for f in ("project.json", "puzzle.json"):
		shutil.copy2(os.path.join(src, f), os.path.join(tmp, f))
	for d in ("pieces", "crops", "photos", "scans"):
		if os.path.isdir(os.path.join(src, d)):
			shutil.copytree(os.path.join(src, d), os.path.join(tmp, d))
	return tmp


def open_at(tmp, lines, n):
	"""Projeto com as primeiras ``n`` linhas do log (estado ANTES do evento n, 0-based)."""
	with open(os.path.join(tmp, "log.jsonl"), "w", encoding="utf-8") as f:
		f.writelines(lines[:n])
	return Project.open(tmp)


# ---------------------------------------------------------------- gémea à data
class Ctx:
	def __init__(self, pr, art, use_initial_theta=False):
		self.pr, self.art, self.items = pr, art, {}
		self.use_initial_theta = use_initial_theta

	def item(self, p):
		key = (p.id, self.use_initial_theta)
		if key not in self.items:
			th = p.theta_deg
			if th is None and self.use_initial_theta and p.estado == "colocada":
				th = R.initial_theta(self.pr, p.id)
			self.items[key] = T.TwinItem(id=p.id, shape=self.pr.shape(p.id), rgba=self.pr.crop_rgba(p.id), theta_deg=th,
										 cell=p.celula if p.estado == "colocada" else None)
		return self.items[key]


def neighbours_at(pr, cell):
	out = []
	for d in DIRS:
		nb = (cell[0] + F.STEP[d][0], cell[1] + F.STEP[d][1])
		if not pr.profile.in_grid(*nb):
			out.append(dict(dir=d, cell=None, estado="moldura"))
			continue
		b = pr.board[nb]
		out.append(dict(dir=d, cell=list(nb), estado=b["estado"], piece=b.get("peca_id"), fonte=b.get("fonte")))
	return out


def twin_query_at(pr, art, query_id, tw, use_initial_theta=False):
	"""``find_twin`` como em ``query._step_twins`` (sem o conjunto ``proposed``), à data."""
	ctx = Ctx(pr, art, use_initial_theta)
	q = pr.piece(query_id)
	rej = Q._rejected(pr)
	cands = [p for p in pr.loose_pieces() if Q._usable(pr, p) and (p.id, tuple(tw)) not in rej]
	qi = ctx.item(q)
	res = T.find_twin(qi, [ctx.item(p) for p in cands], profile=pr.profile, modality=MODALITY, art=art, topk=TOPK)
	res["n_pool"] = len(cands)
	res["theta_query"] = qi.theta_deg
	return res


def fit_at(pr, cell, piece_id, theta_pred, cal, sigma):
	"""Encaixe da peça ``piece_id`` em ``cell`` contra as vizinhas colocadas à data: lado a lado na pose prevista
	(rotação fixada por ``theta_pred``) e J mínimo sobre as 4 rotações (como ``fit.rank_hole``)."""
	cache = F._Cache(pr, cal)
	dcache = {}
	holes = F.hole_queries(pr, cells=[tuple(cell)], cache=cache, dcache=dcache, exclude_piece=None)
	if not holes:
		return dict(m=0, estado="sem_vizinhas")
	h = holes[0]
	items = F.pool_items(pr, pieces=[piece_id], cache=cache)
	if not items:
		return dict(m=len(h.sides), estado="sem_forma")
	pa = F.pool_arrays(items)
	sh = items[0].shape
	out = dict(m=len(h.sides), estado="ok", lados=[], f_required=list(h.f_required))
	cd = F.board_dirs(sh, float(theta_pred)) if theta_pred is not None else None
	costs = []
	for hs in h.sides:
		sc = F.side_costs(hs, pa, cal)
		row = dict(dir=hs.direction, vizinha=hs.piece_id, tipo_vizinha=hs.side.kind)
		if cd is not None:
			j = cd[hs.direction]
			row.update(lado=int(j), tipo=str(pa.kind[0, j]), comp=bool(sc["comp"][0, j]), hard=bool(sc["hard"][0, j]),
					   rms=float(sc["rms"][0, j]), dl=float(sc["dl"][0, j]), dE=float(sc["dE"][0, j]),
					   pen=float(sc["pen"][0, j]), custo=float(sc["cost"][0, j]))
			costs.append(row["custo"])
		out["lados"].append(row)
	if cd is not None:
		out["J_pose"] = float(np.mean(costs)) if costs and np.all(np.isfinite(costs)) else float("inf")
		out["impossivel_pose"] = any((not r["comp"]) or r["hard"] for r in out["lados"] if "comp" in r)
		f_cand = {d for d, j in cd.items() if pa.kind[0, j] == "F"}
		out["f_ok_pose"] = f_cand == set(h.f_required)
	r = F.rank_hole(h, pa, calib=cal, sigma=sigma, top=1)
	if "error" not in r and r["candidates"]:
		c0 = r["candidates"][0]
		out["J_min4"] = float(c0["J"]) if c0["J"] is not None else None
		out["rot_min4"] = c0.get("rot")
		out["theta_min4"] = c0.get("theta_deg")
	else:
		out["J_min4"] = None
		out["rank_hole_error"] = r.get("error")
	return out


def _clean(res):
	"""Parte serializável de um resultado de ``find_twin``."""
	rows = []
	for c in res.get("candidates") or []:
		im = c.get("image")
		rows.append(dict(id=c["id"], d1_mm=c["d1_mm"], phi_deg=c["phi_deg"],
						 dE=None if not im else im.get("dE"), ncc=None if not im else im.get("ncc"),
						 theta_img=None if not im else im.get("theta_deg")))
	return dict(candidates=rows, decision=res.get("decision"), decision_shape=res.get("decision_shape"),
				margin=res.get("margin"), n_class=res.get("n_class"), n_pass=res.get("n_pass"), n_pool=res.get("n_pool"),
				reasons=res.get("reasons"), theta_query=res.get("theta_query"),
				single=None if not res.get("single_candidate") else res["single_candidate"]["id"])


# ---------------------------------------------------------------- principal
def main(argv=None):
	ap = argparse.ArgumentParser()
	ap.add_argument("--project", required=True, help="cópia do projeto com os ativos refeitos")
	ap.add_argument("--tmp", default=None)
	ap.add_argument("--out", default=os.path.join(DOC, "r7_gt.json"))
	ap.add_argument("--no-pctl", action="store_true", default=True, help="PCTL_MAX_N = 0 (o percentil não entra na decisão)")
	args = ap.parse_args(argv)
	src = os.path.abspath(args.project)
	tmp = args.tmp or os.path.join(os.path.dirname(src), "alpes_r7_t")
	if args.no_pctl:
		T.PCTL_MAX_N = 0
	t0 = time.time()
	lines = open(os.path.join(src, "log.jsonl"), encoding="utf-8").readlines()
	L = [json.loads(l) for l in lines]
	make_tmp(src, tmp)
	pr_now = Project.open(src)
	art = CellArt.load(pr_now.profile, REPO)
	cal = F.calibration(pr_now)
	first_l4 = next(i for i, e in enumerate(L) if e["action"] == "scan_added" and (e["scan"].get("lote") or 0) >= 4)

	# ---- decisões listadas (fetch_listed) e eventos
	last_listed = None
	listed_at = {}            # (piece, cell) -> (decision, idx of fetch_listed)
	twin_placed, twin_rej, pair_reg, pair_rej, hole_conf = [], [], [], [], []
	for i, e in enumerate(L):
		a = e["action"]
		if a == "fetch_listed":
			last_listed = i
			for x in e.get("entries") or []:
				if x.get("piece") and x.get("cell"):
					listed_at[(x["piece"], tuple(x["cell"]))] = (x.get("decision"), x.get("origin"), i)
		elif a == "placed" and e.get("origin") == "gemeo":
			twin_placed.append(i)
		elif a == "twin_rejected":
			twin_rej.append(i)
		elif a == "pair_registered":
			pair_reg.append(i)
		elif a == "pair_rejected":
			pair_rej.append(i)
		elif a == "hole_confirmed":
			hole_conf.append(i)
	queries = {}
	for i, e in enumerate(L):
		if e["action"] == "twin_confirmed":
			queries[(e["piece"], tuple(e["cell"]))] = e.get("query")

	out = dict(t=time.strftime("%Y-%m-%dT%H:%M:%S"), project=src, n_events=len(L), first_l4=first_l4,
			   calib=dict(t95=pr_now.profile.calibration[MODALITY]["t95"], tmax=pr_now.profile.calibration[MODALITY]["tmax"],
						  margin_min=pr_now.profile.calibration.get("margin_min"), image_zones=pr_now.profile.image_zones,
						  buraco=pr_now.profile.calibration.get("buraco")),
			   gemeas=[], rejeitadas=[], pares=[], buracos=[], particao={})

	def replay_case(i, piece, cell, query_id, listed, kind):
		pr = open_at(tmp, lines, i)
		p = pr.piece(piece)
		q = pr.piece(query_id) if query_id else None
		row = dict(tipo=kind, piece=piece, cell=list(cell), lote=p.lote, n_no_lote=p.n_no_lote, scan_id=p.scan_id,
				   zona=zone_of(cell), grupo=zone_group(cell), listed=listed[0] if listed else None,
				   listed_origin=listed[1] if listed else None, idx=i, t=L[i]["t"], query=query_id,
				   vizinhas=neighbours_at(pr, cell), n_vizinhas=Q.mounted_neighbours(pr, cell))
		if q is not None:
			row["ancora"] = dict(cell=list(q.celula) if q.celula else None, theta_deg=q.theta_deg,
								 theta_initial=R.initial_theta(pr, q.id), estado=q.estado, seccao_id=q.seccao_id, scan_id=q.scan_id)
			if pr.shape(q.id) is None:
				row["erro"] = "âncora sem silhueta"
				return row
			res = twin_query_at(pr, art, q.id, cell)
			row["find_twin"] = _clean(res)
			top = (res.get("candidates") or [{}])[0].get("id")
			row["top_is_piece"] = top == piece
			row["reproduz"] = (res.get("decision") == (listed[0] if listed else None)) and row["top_is_piece"]
			if q.theta_deg is None and row["ancora"]["theta_initial"] is not None:
				res2 = twin_query_at(pr, art, q.id, cell, use_initial_theta=True)
				row["find_twin_theta_initial"] = _clean(res2)
		# encaixe na pose prevista: theta da colocação (gémea aceite) ou da proposta (rejeitada, passada por fora)
		row["theta_pred"] = None
		return row, pr

	# ---- gémeas aceites (43 com entrada; as sem entrada também, marcadas)
	sigma_cache = {}
	for i in twin_placed:
		e = L[i]
		key = (e["piece"], tuple(e["cell"]))
		listed = listed_at.get(key)
		query_id = queries.get(key)
		row, pr = replay_case(i, e["piece"], tuple(e["cell"]), query_id, listed, "aceite_colocada")
		row["theta_pred"] = e.get("theta_deg")
		row["score_placed"] = e.get("score")
		if row["n_vizinhas"] >= 1 and pr.shape(e["piece"]) is not None:
			sg = F.board_sigma(pr, F._Cache(pr, cal), {})
			row["fit"] = fit_at(pr, tuple(e["cell"]), e["piece"], e.get("theta_deg"), cal, sg.get("sigma", 1)) if "error" not in sg else dict(estado=sg["error"])
		out["gemeas"].append(row)
		print(f"[{len(out['gemeas'])}/{len(twin_placed)}] {e['piece']} {tuple(e['cell'])} listed={listed and listed[0]} "
			  f"-> {row.get('find_twin', {}).get('decision')} top_ok={row.get('top_is_piece')} viz={row['n_vizinhas']} "
			  f"fit={row.get('fit', {}).get('estado')} J_pose={row.get('fit', {}).get('J_pose')} ({time.time() - t0:.0f} s)", flush=True)

	# ---- gémeas rejeitadas: à data da última lista que as mostrou
	fetch_entries_by_idx = {i: e for i, e in enumerate(L) if e["action"] == "fetch_listed"}
	for i in twin_rej:
		e = L[i]
		key = (e["piece"], tuple(e["cell"]))
		listed = listed_at.get(key)
		j = listed[2] if listed else i
		row, pr = replay_case(j, e["piece"], tuple(e["cell"]), e.get("query"), listed, "rejeitada")
		row["idx_rejeicao"], row["t_rejeicao"] = i, e["t"]
		# pose prevista da proposta: theta da gémea + phi + rotação do gémeo (cadeia do query._enrich), se houver θ
		ft = row.get("find_twin") or {}
		c0 = (ft.get("candidates") or [{}])[0]
		th_q = row.get("ancora", {}).get("theta_deg")
		if th_q is None:
			th_q = row.get("ancora", {}).get("theta_initial")
		if th_q is not None and c0.get("phi_deg") is not None:
			from src.locate import snap_theta
			sh = pr.shape(e["piece"])
			row["theta_pred"] = float(snap_theta(sh, float(th_q) + float(c0["phi_deg"]) + pr.profile.twin_rotation_deg())[0]) if sh is not None else None
		if row["n_vizinhas"] >= 1 and pr.shape(e["piece"]) is not None:
			sg = F.board_sigma(pr, F._Cache(pr, cal), {})
			row["fit"] = fit_at(pr, tuple(e["cell"]), e["piece"], row["theta_pred"], cal, sg.get("sigma", 1)) if "error" not in sg else dict(estado=sg["error"])
		out["rejeitadas"].append(row)
		print(f"[rej] {e['piece']} {tuple(e['cell'])} listed={listed and listed[0]} -> {ft.get('decision')} viz={row['n_vizinhas']} fit={row.get('fit', {}).get('estado')} J_pose={row.get('fit', {}).get('J_pose')}", flush=True)

	# ---- pares: ocupação de X e twin(X) à data do registo e à data da rejeição/última lista
	for i in pair_reg:
		t = L[i]["pair"]
		pr = open_at(tmp, lines, i)
		prof = pr.profile
		cells = []
		for c in t.get("cells") or []:
			X = tuple(c["cell"])
			tw = prof.twin(*X)
			cells.append(dict(cell=list(X), score=c.get("score"), rank=c.get("rank"), zona=zone_of(X),
							  X=pr.board[X], twinX=list(tw) if tw else None, twinX_estado=pr.board[tw] if tw else None,
							  X_ocupada=pr.board.occupied(X), twinX_ocupada=bool(tw and pr.board.occupied(tw))))
		rej = next((j for j in pair_rej if L[j]["pair"] == t["id"]), None)
		row = dict(pair=t["id"], a=t["a"], b=t["b"], d1_mm=t.get("d1_mm"), margin=t.get("margin"), image=t.get("image"),
				   idx=i, t=L[i]["t"], estado_final=pr_now.pairs[t["id"]].estado if t["id"] in pr_now.pairs else None,
				   idx_rejeicao=rej, t_rejeicao=L[rej]["t"] if rej is not None else None, cells=cells,
				   lotes=[pr.piece(t["a"]).lote, pr.piece(t["b"]).lote], scans=[pr.piece(t["a"]).scan_id, pr.piece(t["b"]).scan_id],
				   cls=[pr.piece(t["a"]).cls, pr.piece(t["b"]).cls])
		# quem ocupa hoje as células propostas
		row["hoje"] = [dict(cell=c["cell"], X=pr_now.board[tuple(c["cell"])], twinX=None if c["twinX"] is None else pr_now.board[tuple(c["twinX"])]) for c in cells]
		out["pares"].append(row)
		print(f"[par] {t['id']} {t['a']}+{t['b']} d1={t.get('d1_mm'):.3f} m={t.get('margin'):.2f} células={[(c['cell'], c['X_ocupada'], c['twinX_ocupada']) for c in cells]} final={row['estado_final']}", flush=True)

	# ---- buracos confirmados (GT do M11)
	for i in hole_conf:
		e = L[i]
		out["buracos"].append(dict(piece=e["piece"], cell=e["cell"], zona=zone_of(e["cell"]), grupo=zone_group(e["cell"]),
								   confianca=e.get("confianca"), rank=e.get("rank"), m=e.get("m"), custo=e.get("custo"),
								   margem=e.get("margem"), t=e["t"], desde_lote4=i >= first_l4))

	# ---- partição §3 por folha e zona (peças colocadas com silhueta)
	part = collections.defaultdict(lambda: collections.defaultdict(int))
	for p in pr_now.pieces.values():
		if p.estado == "colocada" and p.celula and pr_now.shape(p.id) is not None:
			part[zone_of(p.celula)][p.scan_id] += 1
	particao = {}
	for z, d in part.items():
		scans = sorted(d)
		particao[z] = dict(S_T=[s for k, s in enumerate(scans) if k % 2 == 0], S_V=[s for k, s in enumerate(scans) if k % 2 == 1],
						   n_por_folha=dict(d))
	out["particao"] = particao

	# ---- resumo
	g = out["gemeas"]
	rep = sum(1 for r in g if r.get("reproduz"))
	with_listed = sum(1 for r in g if r.get("listed"))
	cnt = collections.Counter((r["grupo"], r.get("listed"), (r.get("find_twin") or {}).get("decision")) for r in g)
	out["resumo"] = dict(n_gemeas_colocadas=len(g), n_com_entrada=with_listed, n_reproduz=rep,
						 por_grupo_listed_recalc={" | ".join(map(str, k)): v for k, v in cnt.items()},
						 n_fit_incompativel_pose=sum(1 for r in g if (r.get("fit") or {}).get("impossivel_pose")),
						 n_fit_J_pose_acima_tabs=sum(1 for r in g if np.isfinite((r.get("fit") or {}).get("J_pose", np.nan)) and r["fit"]["J_pose"] > cal.t_abs),
						 n_fit_com_vizinhas=sum(1 for r in g if (r.get("fit") or {}).get("estado") == "ok"),
						 buracos=dict(n=len(out["buracos"]), por_grupo=dict(collections.Counter(b["grupo"] for b in out["buracos"]))),
						 segundos=round(time.time() - t0, 1))
	os.makedirs(os.path.dirname(args.out), exist_ok=True)
	with open(args.out, "w", encoding="utf-8") as f:
		json.dump(out, f, ensure_ascii=False, indent=1, default=lambda o: None if (isinstance(o, float) and not np.isfinite(o)) else (o.item() if hasattr(o, "item") else str(o)))
	print(json.dumps(out["resumo"], ensure_ascii=False, indent=1))
	print("partição:", json.dumps({z: {k: v for k, v in d.items() if k != "n_por_folha"} for z, d in particao.items()}, ensure_ascii=False))
	return 0


if __name__ == "__main__":
	sys.exit(main())
