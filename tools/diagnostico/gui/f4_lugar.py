"""F4 B2b (medição, só leitura do projeto real): o «lugar provável» dos grupos soltos pelas regras de 2026-11-18
(:func:`src.grupos.likely_place`: válido agora, vizinhas que não discordam, nenhum membro impossível em todas as
rotações, margem recalculada entre os válidos >= ``margin_min``), antes e depois de recalcular os candidatos com o
tabuleiro de hoje.

O recálculo segue :func:`src.legacy.solve_project_sections` (mesma máscara ``_section_allowed``, mesmo
``solve_pages`` com as secções fixadas como fixas, ``_candidates`` e ``Project.update_section_candidates`` =
evento ``section_candidates_updated``), estendido aos grupos ``blocos`` (``prior_expect`` 0, como na ingestão) e
sem fixar nada. Escreve esses eventos NA CÓPIA dada; corre SEMPRE numa cópia:
``python tools/diagnostico/gui/f4_lugar.py <cópia de projects/alpes> [--json out]``.
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

from src import grupos as GR  # noqa: E402
from src import legacy as LG  # noqa: E402
from src import mesa  # noqa: E402
from src import render  # noqa: E402
from src.locate import body_beta_deg, wrap_deg  # noqa: E402
from src.state import Project  # noqa: E402


def placements_of(pr):
	raw = render.load_placements(pr).get("placements") or {}
	return {pid: e for pid, e in raw.items() if pid in pr.pieces and e.get("key") == render._entry_key(pr, pid)}


def old_rule(pr, gid):
	"""O lugar provável do B2 (candidato 1 com margem >= margin_min, sem mais nada)."""
	s = pr.sections[gid]
	if not s.candidates:
		return None
	cd = s.candidates[0]
	m = cd.get("margin")
	return cd if cd.get("cell0") and m is not None and float(m) >= GR.margin_min(pr.profile) else None


def survey(pr, loose, placements):
	shown = mesa.effective_positions(pr)
	rows = {}
	for gid in loose:
		s = pr.sections[gid]
		cands = []
		for i, cd in enumerate(s.candidates):
			p = GR._cand_pos(cd)
			bad = GR.valid(pr, gid, p, shown)
			chk = None if bad else GR.rotation_check(pr, gid, p, dict(placements), shown=shown, checked=True)
			cands.append({"i": i + 1, "pos": p, "score": cd.get("score"), "margin": cd.get("margin"),
						  "invalido": None if bad is None else bad["motivo"],
						  "vizinhas": None if chk is None else chk["vizinhas"],
						  "impossiveis": None if chk is None else chk["impossiveis"],
						  "nao_avaliadas": None if chk is None else chk["nao_avaliadas"]})
		t0 = time.perf_counter()
		lp = GR.likely_place(pr, gid, shown, dict(placements))
		rows[gid] = {"n": len(s.cells_local), "kind": s.kind, "antigo": old_rule(pr, gid) is not None,
					 "lugar": lp, "s": round(time.perf_counter() - t0, 3), "candidatos": cands}
	return rows


def recompute(pr, loose):
	"""Candidatos novos dos grupos soltos com o tabuleiro de hoje (ver o docstring do módulo)."""
	profile = pr.profile
	art = LG._project_art(pr, None)
	prior = LG._project_prior(pr)
	hints = list(pr.hint_cells())
	results, sec_of, allowed = [], [], []
	want = set(loose)
	for gid, s in sorted(pr.sections.items()):
		anchored = bool(s.anchor.get("anchored"))
		if not anchored and gid not in want:
			continue
		if s.cells_local and all(pr.piece(pid).same_as for pid in s.cells_local):
			continue                      # a page scanned twice: nothing new (the rule of solve_project_sections)
		pids = sorted(s.cells_local, key=lambda k: s.cells_local[k])
		pieces = []
		for k, pid in enumerate(pids):
			q = pr.piece(pid)
			pp = LG.PagePiece(n=int(q.n_no_lote or k + 1), index=int(q.index_in_scan), contour=np.zeros((0, 2)),
							  bbox=q.bbox or [0, 0, 0, 0], area_mm2=float(q.area_mm2 or 0), shape=pr.shape(pid),
							  mean_lab=q.mean_lab, rgba=pr.crop_rgba(pid))
			pieces.append(pp)
		rot = LG.page_rotation([p.shape for p in pieces if p.shape is not None])
		for p in pieces:
			if p.shape is None:
				p.excluded = "sem forma"
				continue
			p.theta_deg = float(rot + wrap_deg(body_beta_deg(p.shape) - rot))
			p.dirs, p.dirs_ok, p.flat_dirs = LG.label_sides(p.shape, rot)
		comp = LG.Component(id=0, members=list(range(len(pids))), rc={k: tuple(s.cells_local[pid]) for k, pid in enumerate(pids)})
		for k in comp.members:
			pieces[k].comp = 0
			pieces[k].rc = comp.rc[k]
		kind = s.kind if s.kind in ("montado", "blocos") else "montado"
		r = LG.PageResult(name=gid, kind=kind, path=None, mm_per_px=profile.mm_per_px(), angle_deg=rot,
						  n_segmented=len(pids), pieces=pieces, components=[comp])
		if anchored:
			a = s.anchor
			cells = LG.component_cells(comp, (a["l0"], a["c0"]), a["rot"], a["mirror"])
			comp.placements = [dict(cell0=(a["l0"], a["c0"]), rot=int(a["rot"]), mirror=bool(a["mirror"]), score=0.0,
									cells=cells, origin="ancorada", twin_sat=0, twin_viol=0, adj=0.0)]
			comp.decision = "alta"
			allowed.append(None)
		else:
			am = LG._section_allowed(pr, pids)
			LG._locate_component(comp, pieces, profile, art, prior, 0 if kind == "blocos" else 1, profile.mm_per_px(),
								 constraints={"allowed": am})
			LG._decide(comp, float(profile.calibration.get("margin_min", 1.5)))
			allowed.append(am)
		results.append(r)
		sec_of.append(gid)
	LG.solve_pages(results, profile, art, prior, hints=hints, allowed=allowed)
	changed = 0
	for gid, r in zip(sec_of, results):
		if gid not in want:
			continue
		comp = r.components[0]
		cands = LG._candidates(comp)
		s = pr.sections[gid]
		if cands and cands != s.candidates:
			pr.update_section_candidates(gid, cands, notes=s.notes)
			changed += 1
	pr.save()
	return changed


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("project")
	ap.add_argument("--json")
	a = ap.parse_args()
	if os.path.samefile(a.project, os.path.join(REPO, "projects", "alpes")):
		sys.exit("corre numa cópia de projects/alpes")
	pr = Project.open(a.project)
	placements = placements_of(pr)
	loose = sorted(g for g in pr.sections if mesa.is_loose(pr, g))
	t0 = time.perf_counter()
	before = survey(pr, loose, placements)
	t_before = time.perf_counter() - t0
	t0 = time.perf_counter()
	changed = recompute(pr, loose)
	t_rec = time.perf_counter() - t0
	pr = Project.open(a.project)
	after = survey(pr, loose, placements_of(pr))

	def count(rows):
		lugar = [g for g, r in rows.items() if r["lugar"] is not None]
		inval = sum(1 for r in rows.values() for c in r["candidatos"] if c["invalido"])
		disc = sum(1 for r in rows.values() for c in r["candidatos"] if c["vizinhas"] == "discordam")
		imp = [g for g, r in rows.items() if any(c["impossiveis"] for c in r["candidatos"])]
		c1 = sum(1 for r in rows.values() if r["candidatos"] and r["candidatos"][0]["invalido"] is None)
		return {"grupos": len(rows), "lugar_antigo": sum(r["antigo"] for r in rows.values()), "lugar_novo": len(lugar),
				"com_lugar": lugar, "candidatos_invalidos": inval, "candidatos_discordam": disc,
				"grupos_com_impossivel": imp, "candidato1_valido": c1,
				"s_max": max((r["s"] for r in rows.values()), default=0.0)}
	out = {"antes": count(before), "depois": count(after), "alterados": changed, "s_recalculo": round(t_rec, 1),
		   "s_antes": round(t_before, 1), "linhas_antes": before, "linhas_depois": after}
	for k in ("antes", "depois"):
		print(k, {kk: v for kk, v in out[k].items()})
	print(f"candidatos alterados pelo recálculo: {changed} de {len(loose)} ({t_rec:.1f} s)")
	for g in loose:
		b, d = before[g], after[g]
		fmt = lambda r: ("lugar " + str(r["lugar"]["cell0"]) + f" r{r['lugar']['rot']} m{r['lugar']['margin']} c{r['lugar']['candidato']}"
						 if r["lugar"] else "—")
		cs = lambda r: " ".join(f"{c['i']}:{c['invalido'] or c['vizinhas']}{'!' if c['impossiveis'] else ''}" for c in r["candidatos"])
		print(f"{g} n{b['n']:2d} {b['kind']:7s} antigo {'S' if b['antigo'] else '-'} | antes {fmt(b):34s} [{cs(b)}] | depois {fmt(d):34s} [{cs(d)}]")
	if a.json:
		with open(a.json, "w", encoding="utf-8") as f:
			json.dump(out, f, ensure_ascii=False, indent=1, default=str)


if __name__ == "__main__":
	main()
