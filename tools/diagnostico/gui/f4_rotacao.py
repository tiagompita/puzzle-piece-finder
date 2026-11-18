"""F4 B2½ (diagnóstico, só leitura): a verificação da rotação de «Fixar» (grupos.rotation_check) contra o critério
das Suspeitas (consistency.evaluate), nas secções fixadas e nos lugares sugeridos (candidato 1 com margem) dos
grupos soltos; imagem (ΔE na célula, src.locate) das rotações em disputa e dos candidatos 2 e 3.

Corre SEMPRE numa cópia do projeto: ``python tools/diagnostico/gui/f4_rotacao.py <cópia de projects/alpes> [--json out]``.
Não escreve nada no projeto. Resultado e tabela: ``docs/diagnostico/gui/F4_ROTACAO.md``.

Mede o código do B2 (``56765b8``): corre-o nesse commit (``git worktree add <pasta> 56765b8``). Depois do B2b
``grupos.rotation_check`` recusa uma posição inválida (também a de uma secção já fixada) antes de avaliar, e o
critério passou a ser ``consistency.grade_at``; a medição depois das correções é ``tools/diagnostico/gui/f4_lugar.py``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, REPO)

import numpy as np  # noqa: E402

from src import consistency as C  # noqa: E402
from src import grupos as GR  # noqa: E402
from src import mesa  # noqa: E402
from src import render  # noqa: E402
from src.legacy import _STEP  # noqa: E402
from src.locate import CellArt, de_cell, render_item  # noqa: E402
from src.state import Project, section_cell  # noqa: E402

REL = (0, 1, 2, 3)          # relative assignment r: k = (k0 + r) % 4 -> rotation C._rot_deg


def placements_of(pr):
	raw = render.load_placements(pr).get("placements") or {}
	return {pid: e for pid, e in raw.items() if pid in pr.pieces and e.get("key") == render._entry_key(pr, pid)}


def suspeitas_grade(pr, gid, pos, placements, *, use_placements_k=False):
	"""The EXACT criterion of consistency.evaluate on the pieces of ``gid`` as if it sat at ``pos`` (every
	mounted neighbour counts, inside or outside the group; the ``explained`` rule applies), plus the outside
	neighbours re-graded with the group mounted. Returns {pid: dict}."""
	s = pr.sections[gid]
	p = GR._pos(pos)
	mine = {pid: section_cell(p, rc) for pid, rc in s.cells_local.items()}
	mounted = {tuple(q.celula): qid for qid, q in pr.pieces.items()
			   if q.estado == "colocada" and q.celula is not None and qid not in mine}
	# the anchor rule (state.anchor_section): a member already placed keeps its cell; an ``em_seccao`` member on a
	# cell placed by another piece (a re-scan, ``same_as``) is a conflict and never reaches the board
	skipped = {}
	for pid, cell in mine.items():
		q = pr.piece(pid)
		if q.estado == "colocada":
			mounted[tuple(cell)] = pid
		elif tuple(cell) in mounted or not pr.profile.in_grid(*cell):
			skipped[pid] = mounted.get(tuple(cell))
	for pid, cell in mine.items():
		if pr.piece(pid).estado != "colocada" and pid not in skipped:
			mounted[tuple(cell)] = pid
	mine = {pid: c for pid, c in mine.items() if pid not in skipped}
	cellof = {v: k for k, v in mounted.items()}
	cache, kmap, theta_cache, cr_of = {}, {}, {}, {}

	def k_of(pid):
		if pid in kmap:
			return kmap[pid]
		sh = pr.shape(pid)
		if sh is None or not sh.ok or len(sh.corners) != 4:
			kmap[pid] = None
			return None
		if pid in mine and not use_placements_k:
			cr = render.corner_register(sh, pr.profile, mine[pid], GR.group_theta(pr, pid, p["rot"], theta_cache))
			cr_of[pid] = cr
			kmap[pid] = int(cr["k"]) if cr.get("ok") else None
		else:
			kmap[pid] = C._k_of(pr, pid, placements, cache)
		return kmap[pid]

	graded = {}

	def grade(pid):
		if pid not in graded:
			k0 = k_of(pid)
			if k0 is None:
				graded[pid] = None
			else:
				cell = cellof[pid]
				for dl, dc in _STEP.values():
					q = mounted.get((cell[0] + dl, cell[1] + dc))
					if q is not None:
						k_of(q)
				res = C._assignments(pr, pid, k0, kmap, mounted, cell=cell)
				graded[pid] = (k0, res) + C._grade(res, k0)
		return graded[pid]

	def explained(pid, k0, res):
		cur = res[k0]
		kinds = [f for f in cur["fails"] if f["why"] == "kind"]
		if not cur["f_ok"] or not kinds:
			return False
		for f in kinds:
			g = grade(f["piece"])
			if g is None or g[2] != "impossivel" or g[3] is None:
				return False
		return True

	out = {}
	outside = set()
	for pid, cell in mine.items():
		for dl, dc in _STEP.values():
			q = mounted.get((cell[0] + dl, cell[1] + dc))
			if q is not None and q not in mine:
				outside.add(q)
	for pid in sorted(mine) + sorted(outside):
		g = grade(pid)
		row = {"cell": list(cellof[pid]), "membro": pid in mine}
		if g is None:
			row["grau"] = "sem_cantos"
			out[pid] = row
			continue
		k0, res, grau, ka = g
		if grau == "impossivel" and ka is None and explained(pid, k0, res):
			grau = "explicada"
		nin = sum(1 for dl, dc in _STEP.values() if mounted.get((cellof[pid][0] + dl, cellof[pid][1] + dc)) in mine
				  and mounted.get((cellof[pid][0] + dl, cellof[pid][1] + dc)) != pid)
		row.update(k0=k0, grau=grau, rot_alt=None if ka is None else C._rot_deg(ka, k0), n=res[k0]["n"],
				   n_dentro=nin if pid in mine else None,
				   J={C._rot_deg((k0 + r) % 4, k0): (res[(k0 + r) % 4]["n_fail"], round(res[(k0 + r) % 4]["cost"], 2),
													 bool(res[(k0 + r) % 4]["f_ok"]), res[(k0 + r) % 4]["n_kind"])
					  for r in REL})
		if pid in cr_of:
			row["thetas"] = {C._rot_deg(int(c[0]), k0): float(c[1]) for c in cr_of[pid]["cands"]}
		out[pid] = row
	for pid, occ in skipped.items():
		out[pid] = {"cell": list(section_cell(p, s.cells_local[pid])), "membro": True, "grau": "nao_colocada",
					"ocupante": occ, "same_as": pr.piece(pid).same_as}
	return out


def b2_detail(pr, gid, pos, placements):
	"""rotation_check as the server calls it, plus the per-piece res it graded (rebuilt with the same inputs)."""
	chk = GR.rotation_check(pr, gid, pos, placements=placements)
	s = pr.sections[gid]
	p = GR._pos(pos)
	mine = {pid: section_cell(p, rc) for pid, rc in s.cells_local.items()}
	mounted = {tuple(q.celula): qid for qid, q in pr.pieces.items()
			   if q.estado == "colocada" and q.celula is not None and qid not in mine}
	cache, kmap, tc = {}, {}, {}
	det = {}
	for pid, w in chk["pecas"].items():
		if w == "sem_vizinhas":
			continue
		sh = pr.shape(pid)
		if sh is None or not sh.ok or len(sh.corners) != 4:
			continue
		cell = mine[pid]
		cr = render.corner_register(sh, pr.profile, cell, GR.group_theta(pr, pid, p["rot"], tc))
		if not cr.get("ok"):
			continue
		k0 = int(cr["k"])
		for dl, dc in _STEP.values():
			q = mounted.get((cell[0] + dl, cell[1] + dc))
			if q is not None and q not in kmap:
				sq = pr.shape(q)
				kmap[q] = C._k_of(pr, q, placements, cache) if sq is not None and sq.ok and len(sq.corners) == 4 else None
		res = C._assignments(pr, pid, k0, kmap, mounted, cell=cell)
		g, ka = C._grade(res, k0)
		det[pid] = {"k0": k0, "grau": g, "rot_alt": None if ka is None else C._rot_deg(ka, k0), "n": res[k0]["n"],
					"J": {C._rot_deg((k0 + r) % 4, k0): (res[(k0 + r) % 4]["n_fail"], round(res[(k0 + r) % 4]["cost"], 2),
														  bool(res[(k0 + r) % 4]["f_ok"]), res[(k0 + r) % 4]["n_kind"])
						  for r in REL},
					"fails0": [f"{f['dir']} {f['why']} {f['kinds']} {f['piece']} rms {f['rms']:.2f} dl {f['dl']:.2f}"
							   for f in res[k0]["fails"]]}
	return chk, det


_IMG_CACHE = {}


def img_de(pr, art, pid, cell, theta):
	key = (pid, tuple(cell), round(float(theta), 2))
	if key not in _IMG_CACHE:
		rgba = pr.crop_rgba(pid)
		sh = pr.shape(pid)
		if rgba is None or sh is None:
			_IMG_CACHE[key] = float("nan")
		else:
			mmpp = render._scan_mmpp(pr, pr.piece(pid).scan_id)
			_IMG_CACHE[key] = float(de_cell(render_item(rgba, sh, float(theta), art, mmpp), int(cell[0]), int(cell[1]), art)["dE"])
	return _IMG_CACHE[key]


def group_image(pr, art, gid, pos):
	"""Median ΔE of the group's pieces on their cells at ``pos`` (corner pose with group_theta), finite only."""
	s = pr.sections[gid]
	p = GR._pos(pos)
	tc = {}
	vals = []
	for pid, rc in s.cells_local.items():
		cell = section_cell(p, rc)
		if not pr.profile.in_grid(*cell):
			continue
		sh = pr.shape(pid)
		th = GR.group_theta(pr, pid, p["rot"], tc)
		cr = render.corner_register(sh, pr.profile, cell, th) if sh is not None else {"ok": False}
		if cr.get("ok"):
			th = cr["theta_deg"]
		vals.append(img_de(pr, art, pid, cell, th))
	v = np.asarray(vals, float)
	v = v[np.isfinite(v)]
	return (float(np.median(v)) if len(v) else float("nan")), len(v)


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("project")
	ap.add_argument("--json")
	ap.add_argument("--sem-imagem", action="store_true")
	a = ap.parse_args()
	t0 = time.perf_counter()
	pr = Project.open(a.project)
	placements = placements_of(pr)
	print(f"placements em cache: {len(placements)}")
	ev = C.evaluate(pr, dict(placements), incluir_falsos=True)
	susp_items = {(it["piece"], it["grau"]): it for it in ev["items"]}
	print(f"evaluate: {ev['summary']}  ({time.perf_counter() - t0:.1f} s)")
	orient = {it["piece"]: it for it in ev["items"] if it["grau"] in ("impossivel", "melhor_rotacao")}
	print("suspeitas de orientação:", sorted((p, it["grau"], it.get("falso_alarme") is not None) for p, it in orient.items()))
	art = None if a.sem_imagem else CellArt.load(pr.profile, REPO)

	rows = []
	# fixadas
	fixed = sorted(g for g, s in pr.sections.items() if s.anchor.get("anchored"))
	loose = sorted(g for g in pr.sections if mesa.is_loose(pr, g))
	sugg = [(g, GR.likely_place(pr, g)) for g in loose]
	sugg = [(g, lp) for g, lp in sugg if lp is not None]
	print(f"secções fixadas {len(fixed)}, grupos soltos {len(loose)}, com lugar provável {len(sugg)}")
	jobs = [("fixada", g, {"l0": pr.sections[g].anchor["l0"], "c0": pr.sections[g].anchor["c0"],
						   "rot": pr.sections[g].anchor.get("rot") or 0, "mirror": bool(pr.sections[g].anchor.get("mirror"))},
			 pr.sections[g].anchor.get("margin")) for g in fixed]
	sug_ids = {g for g, _ in sugg}
	for g in loose:
		cd = (pr.sections[g].candidates or [None])[0]
		if g in sug_ids or not cd or not cd.get("cell0"):
			continue
		jobs.append(("cand1", g, {"l0": cd["cell0"][0], "c0": cd["cell0"][1], "rot": int(cd.get("rot") or 0) % 360,
								  "mirror": bool(cd.get("mirror"))}, cd.get("margin")))
	jobs += [("sugerida", g, {"l0": lp["cell0"][0], "c0": lp["cell0"][1], "rot": lp["rot"], "mirror": lp["mirror"]},
			  lp["margin"]) for g, lp in sugg]
	kmis = []
	for kind, gid, pos, margin in jobs:
		chk, det = b2_detail(pr, gid, pos, dict(placements))
		sg = suspeitas_grade(pr, gid, pos, dict(placements))
		if kind == "fixada":
			sgp = suspeitas_grade(pr, gid, pos, dict(placements), use_placements_k=True)
			for pid in sg:
				if sg[pid].get("k0") != sgp[pid].get("k0"):
					kmis.append((gid, pid, sg[pid].get("k0"), sgp[pid].get("k0")))
			# replica == evaluate? (membros)
			for pid, r in sgp.items():
				if not r["membro"]:
					continue
				ev_g = orient.get(pid, {}).get("grau")
				mine_g = r["grau"] if r["grau"] in ("impossivel", "melhor_rotacao") else None
				if ev_g != mine_g:
					print(f"  !! réplica difere de evaluate: {gid} {pid} réplica {r['grau']} evaluate {ev_g}")
			sg = sgp
		members = {p: r for p, r in sg.items() if r["membro"]}
		s_flag = {p: r for p, r in members.items() if r["grau"] in ("impossivel", "melhor_rotacao")}
		ext_flag = {p: r for p, r in sg.items() if not r["membro"] and r["grau"] in ("impossivel", "melhor_rotacao")}
		row = {"tipo": kind, "gid": gid, "pos": pos, "margem": margin, "n_pecas": len(pr.sections[gid].cells_local),
			   "b2": chk["vizinhas"], "b2_pecas": chk["pecas"], "b2_rot_alt": chk["rot_alt_deg"], "b2_det": det,
			   "susp": "discordam" if s_flag else ("confirmam/ok" if any(r.get("n") for r in members.values()) else "sem_vizinhas"),
			   "susp_membros": {p: {k: v for k, v in r.items()} for p, r in members.items()},
			   "susp_flag": {p: (r["grau"], r["rot_alt"]) for p, r in s_flag.items()},
			   "susp_ext_flag": {p: (r["grau"], r["rot_alt"], r["cell"]) for p, r in ext_flag.items()},
			   "candidatos": [{k: c.get(k) for k in ("cell0", "rot", "mirror", "score", "margin")}
							  for c in pr.sections[gid].candidates[:3]]}
		if art is not None and (s_flag or chk["vizinhas"] == "discordam"):
			img = {}
			flagged = set(s_flag) | {p for p, w in chk["pecas"].items() if w == "discordam"}
			for pid in sorted(flagged):
				r = members.get(pid) or {}
				cell = r.get("cell") or list(section_cell(GR._pos(pos), pr.sections[gid].cells_local[pid]))
				# thetas per relative rotation from the corner registration at this cell
				sh = pr.shape(pid)
				th0 = GR.group_theta(pr, pid, pos["rot"], {})
				cr = render.corner_register(sh, pr.profile, cell, th0)
				if not cr.get("ok"):
					continue
				k0 = int(cr["k"])
				img[pid] = {C._rot_deg(int(c[0]), k0): round(img_de(pr, art, pid, cell, c[1]), 2) for c in cr["cands"]}
			row["img_pecas"] = img
			cands = []
			for c in pr.sections[gid].candidates[:3]:
				if not c.get("cell0"):
					continue
				cp = {"l0": c["cell0"][0], "c0": c["cell0"][1], "rot": int(c.get("rot") or 0), "mirror": bool(c.get("mirror"))}
				med, n = group_image(pr, art, gid, cp)
				sgc = suspeitas_grade(pr, gid, cp, dict(placements))
				fl = {p: (r["grau"], r["rot_alt"]) for p, r in sgc.items() if r["membro"] and r["grau"] in ("impossivel", "melhor_rotacao")}
				nchk = sum(1 for r in sgc.values() if r["membro"] and r.get("n"))
				valid = GR.valid(pr, gid, cp)
				cands.append({"pos": cp, "score": c.get("score"), "margin": c.get("margin"), "dE_med": round(med, 2),
							  "n_img": n, "susp_flag": fl, "n_com_vizinhas": nchk,
							  "valido": valid is None, "b2": GR.rotation_check(pr, gid, cp, placements=dict(placements))["vizinhas"]})
			row["img_candidatos"] = cands
		rows.append(row)
		row["valido"] = GR.valid(pr, gid, pos) is None if kind != "fixada" else None
		row["nao_colocadas"] = {p: (r.get("ocupante"), r.get("same_as")) for p, r in members.items() if r["grau"] == "nao_colocada"}
		print(f"{kind:8s} {gid} valido {row['valido']} naocol {row['nao_colocadas']} pos ({pos['l0']},{pos['c0']}) r{pos['rot']} m {margin}: B2 {chk['vizinhas']:13s} "
			  f"susp {row['susp']:12s} flag {row['susp_flag']} ext {row['susp_ext_flag']}  b2 discord "
			  f"{ {p: chk['rot_alt_deg'].get(p) for p, w in chk['pecas'].items() if w == 'discordam'} }")
	print(f"k0 grupo_theta vs placements (fixadas): {len(kmis)} diferenças {kmis[:10]}")
	print(f"total {time.perf_counter() - t0:.1f} s")
	if a.json:
		with open(a.json, "w", encoding="utf-8") as f:
			json.dump({"rows": rows, "kmis": kmis, "orient": sorted(orient)}, f, ensure_ascii=False, indent=1, default=str)


if __name__ == "__main__":
	main()
