"""Regenerate ``projects/alpes/`` from every scan we have (idempotent: wipes it except ``puzzle.json``).

	PPF_SCRATCH=... python tools/diagnostico/legado/ingest_all.py [--project projects/alpes] [--no-query]

Order (each step goes through the project API, so ``log.jsonl`` is the whole history):

1. ``Project.create`` (the versioned ``puzzle.json`` is kept);
2. photo F0001 = M14 map ``docs/diagnostico/ocupacao/ocupacao_2026-10-31.json`` with the
   fixes confirmed by Tiago ((1,29) empty, (1,34) full); then the cells Tiago says are assembled
   (``HINTS_TIAGO``, ``Project.mark_cell_full``: ground truth ``fonte='tiago'``, hints for the
   legacy solve of step 5);
3. ground truth with silhouette (``ingest_scan`` + known cells; a GT piece is ``colocada``
   if its cell is full in the photo, else ``posicao_conhecida``):
   E-sym A1 (top border c5-24, grid order), E-sym B2 (bottom border, twins of A1 with the
   order inside a row reversed), corner BE (20 interiors, ``ereal2_gt_BE.json``) and corner
   BD (28 interiors, ``ereal_gt.json``), matched to the ingested pieces by bbox (IoU), never
   by index; objects that are not GT pieces (the assembled L border) are discarded. The
   board rotation ``theta_deg`` of each set (4 nominal rotations, each snapped to the body
   axes) is chosen by the shape: F sides where the profile has a border + facing sides of
   neighbouring GT cells that are T<->B; the image (mean dE on the known cell) is reported;
4. bag 1 (100 sky pieces of E-real-2, 4 sheets, numbering continued); the two physical
   confirmations of 2026-10-31 identified by the bbox centre (``ereal2_confirmacoes.json``);
5. legacy pages ``montado_p01..p15`` and ``blocos_p01..p03`` (``legacy.ingest_page`` with
   ``auto_anchor=False``; same-piece matches with GT become ``same_as``), ``montado_p13``
   (a re-scan of p04) marked ``same_as`` p04 piece by piece (shape + colour with mutual nearest
   neighbours, then the local grid cells, then the nearest shape without the mutual rule), then
   ``legacy.solve_project_sections`` anchors the components that are ``alta`` across pages;
   ``artreg.run`` registers the art against the placed pieces (``art.registration`` in ``puzzle.json``);
   a GT conflict (a page piece that is the same physical piece as a GT piece) never moves
   the GT piece; a GT piece kept as ``posicao_conhecida`` (cell not full in the photo) whose
   cell an anchored page fills is placed there and the page piece becomes ``same_as``;
   then ``border.solve_border`` + ``border.apply_solution`` fill the free border cells (the
   border is complete except (1,29)) with the border pieces of the sections still unanchored;
6. ``query.run_query`` (with image) -> ``fetch.md``, ``fetch.json``, ``fetch_<lote>.jpg``;
7. the M14-vs-scans comparison is in ``m14_compare`` (printed + JSON);
8. ``check_invariants`` and a determinism check (``Project.open`` on a copy -> same list).

The summary JSON goes to ``$PPF_SCRATCH/ingest_all/resumo.json``.
"""

import argparse
import json
import os
import shutil
import sys
import time

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO)

from src import legacy  # noqa: E402
from src.confirm import confirm  # noqa: E402
from src.ingest import _apply_known_cells, grid_order, ingest_scan  # noqa: E402
from src.locate import CellArt, de_cell, render_item, snap_theta  # noqa: E402
from src.photo import photo_from_json, register  # noqa: E402
from src.state import Project, section_cell  # noqa: E402

PROJECT = os.path.join(REPO, "projects", "alpes")
OCC = os.path.join(REPO, "docs", "diagnostico", "ocupacao", "ocupacao_2026-10-31.json")
OCC_FIX = [((1, 29), 0), ((1, 34), 1)]     # confirmed by Tiago (estado-e-plano §0)
# cells Tiago has assembled that the program did not show (bug 5, 2026-11-01): user hints, fonte 'tiago'
HINTS_TIAGO = [(3, 10), (7, 2), (8, 2), (5, 20), (6, 20), (5, 22), (6, 22), (2, 31), (2, 32), (3, 31), (3, 32), (3, 33)]
GEM = os.path.join(REPO, "docs", "diagnostico", "gemeos")
GT_SCANS = {
	"A1": "images/pieces/coluna5-24_300dpi_folhaA.jpg",
	"B2": "images/pieces/coluna5-24_folhaB_300dpi_rot180.jpg",
	"BE": "images/pieces/gt_canto_BE_soltas_300dpi.jpg",
	"BD": "images/pieces/gt_canto_BD_soltas_300dpi.jpg",
}
GT_THETA_EXPECTED = {"A1": 0, "B2": 180, "BE": 90, "BD": 90}   # docs: A1 F up; B2 rotated in place; BE/BD block 90 deg anticlockwise
# (sheet, scan, lote): the bags are physical (Tiago, 2026-11-01): lote 1 = f1p1 + f1p2, lote 2 = f2p1 + f2p2
SKY = [("f1p1", "images/pieces/ereal2_ceu_f1p1_300dpi.jpg", 1), ("f1p2", "images/pieces/ereal2_ceu_f1p2_300dpi.jpg", 1),
	   ("f2p1", "images/pieces/ereal2_ceu_f2p1_300dpi.jpg", 2), ("f2p2", "images/pieces/ereal2_ceu_f2p2_300dpi.jpg", 2)]
CONFIRMATIONS = {"BE(2,4)": {"sheet": "f2p1", "cell": (2, 61), "kind": "cell"},
				 "BE(5,5)": {"sheet": "f1p1", "cell": (5, 60), "kind": "position_known"}}
CONF_MM = 3.0                 # same tolerance as ereal2.find_by_centre
PAGES = [("montado", f"p{k:02d}") for k in range(1, 16)] + [("blocos", f"p{k:02d}") for k in range(1, 4)]
DUP_PAGE = ("p13", "p04")     # montado_p13 is montado_p04 scanned again (LEGADO.md)
GT_AREA_MAX = 650.0           # mm^2: above this an object of a GT sheet is the assembled L border, never a GT piece
IOU_MIN = 0.5


# ---------------------------------------------------------------- helpers
def reset_project(path: str) -> None:
	keep = os.path.join(path, "puzzle.json")
	if not os.path.exists(keep):
		raise SystemExit(f"{keep} não existe")
	for name in os.listdir(path):
		fp = os.path.join(path, name)
		if name == "puzzle.json":
			continue
		if os.path.isdir(fp):
			shutil.rmtree(fp)
		else:
			os.remove(fp)


def iou(a, b) -> float:
	a, b = np.asarray(a, float), np.asarray(b, float)
	ix = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
	iy = max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
	return ix * iy / (a[2] * a[3] + b[2] * b[3] - ix * iy)


def bbox_centre_mm(bbox, mmpp) -> np.ndarray:
	return np.array([bbox[0] + bbox[2] / 2.0, bbox[1] + bbox[3] / 2.0]) * mmpp


def gt_cells(pr, tag: str, pids: list) -> tuple:
	"""``({pid: cell}, notes)`` for the GT sheet ``tag`` (pids = pieces of the ingested scan)."""
	prof = pr.profile
	cand = [pid for pid in pids if (pr.piece(pid).area_mm2 or 0) <= GT_AREA_MAX]
	out, notes = {}, []
	if tag in ("A1", "B2"):
		if len(cand) != 20:
			notes.append(f"{tag}: {len(cand)} objetos <= {GT_AREA_MAX:g} mm² (esperadas 20): mapeamento por ordem recusado")
			return out, notes
		order = grid_order([pr.piece(pid).bbox for pid in cand])
		for pid, n in zip(cand, order):
			i = n - 1
			if tag == "A1":
				out[pid] = (1, 5 + i)
			else:   # B(f, k) holds the twin of A(f, 4 - k) (images/pieces/gemeos_2026-10-30.md)
				f, k = divmod(i, 5)
				out[pid] = tuple(prof.twin(1, 5 + 5 * f + (4 - k)))
		return out, notes
	if tag == "BE":
		d = json.load(open(os.path.join(GEM, "ereal2_gt_BE.json"), encoding="utf-8"))
		ents = d["soltas"]
	else:
		d = json.load(open(os.path.join(GEM, "ereal_gt.json"), encoding="utf-8"))
		ents = d["soltas"]
	for e in ents:
		best, bp = 0.0, None
		for pid in cand:
			v = iou(e["bbox"], pr.piece(pid).bbox)
			if v > best:
				best, bp = v, pid
		if bp is None or best < IOU_MIN:
			notes.append(f"{tag}: ({e['l']},{e['c']}) sem peça (IoU {best:.2f})")
			continue
		if bp in out:
			notes.append(f"{tag}: {bp} casa com duas entradas GT")
			continue
		out[bp] = (int(e["l"]), int(e["c"]))
	return out, notes


def theta_test(pr, art, cells: dict) -> dict:
	"""Per nominal rotation (0/90/180/270) of a GT set: F sides that match the profile, facing sides of
	neighbouring GT cells that are T<->B, mean dE of each piece rendered on its known cell, per-piece dE wins.

	The rotation is decided by F + T<->B (shape); the image is reported (on sky/grass it barely
	separates the four rotations).
	"""
	mm = pr.profile.mm_per_px()
	per, dirs = {}, {}
	for pid, cell in cells.items():
		sh, rgba = pr.shape(pid), pr.crop_rgba(pid)
		if sh is None or rgba is None:
			continue
		per[pid], dirs[pid] = {}, {}
		for t in (0, 90, 180, 270):
			th = snap_theta(sh, t)[0]
			de = de_cell(render_item(rgba, sh, th, art, mm), cell[0], cell[1], art)["dE"]
			d, ok, flat = legacy.label_sides(sh, th)
			want = tuple(sorted(pr.profile.flat_directions(*cell)))
			per[pid][t] = (float(de), bool(ok and flat == want), th)
			dirs[pid][t] = d if ok else None
	at = {cell: pid for pid, cell in cells.items() if pid in per}
	res = {}
	for t in (0, 90, 180, 270):
		v = [per[p][t][0] for p in per if np.isfinite(per[p][t][0])]
		wins = sum(1 for p in per if min(per[p], key=lambda k: per[p][k][0]) == t)
		tb = n_adj = 0
		for (l, c), pa in at.items():
			for dl, dc, oa, ob in ((0, 1, "E", "W"), (1, 0, "S", "N")):
				pb = at.get((l + dl, c + dc))
				if pb is None:
					continue
				n_adj += 1
				da, db = dirs[pa][t], dirs[pb][t]
				if da and db and {pr.shape(pa).sides[da[oa]].kind, pr.shape(pb).sides[db[ob]].kind} == {"T", "B"}:
					tb += 1
		res[t] = {"dE_mean": round(float(np.mean(v)), 2) if v else None, "dE_wins": wins,
				  "F_ok": sum(1 for p in per if per[p][t][1]), "TB_ok": tb, "n_adj": n_adj, "n": len(per)}
	return {"by_theta": res, "per_piece": per}


def m14_compare(pr) -> dict:
	"""Board (final state) against the photo map: placed on photo 0/-1; photo 1 without a placed piece."""
	ph = pr.last_photo()
	placed_bad = {"0": [], "-1": []}
	for (l, c), cell in pr.board.iter_cells():
		if cell["estado"] == "colocada":
			v = ph.value(l, c)
			if v != 1:
				p = pr.piece(cell["peca_id"])
				src = cell["fonte"] if cell["fonte"] != "log" else (p.scan_id and _origin_of(pr, p.id))
				placed_bad[str(v)].append({"cell": [l, c], "piece": p.id, "fonte": src})
	# top-1 cells of unanchored montado/blocos sections (not re-scans)
	amb = {}
	for gid, s in sorted(pr.sections.items()):
		if s.anchor.get("anchored") or not s.candidates:
			continue
		if all(pr.piece(pid).same_as for pid in s.cells_local):
			continue
		c0 = s.candidates[0]
		a = {"l0": c0["cell0"][0], "c0": c0["cell0"][1], "rot": c0.get("rot", 0), "mirror": c0.get("mirror", False)}
		for pid, rc in s.cells_local.items():
			try:
				amb.setdefault(tuple(section_cell(a, rc)), []).append(gid)
			except Exception:  # noqa: BLE001
				pass
	full_no_piece = {"ambigua_top1": [], "sem_explicacao": []}
	for (l, c), cell in pr.board.iter_cells():
		if ph.value(l, c) == 1 and cell["estado"] != "colocada":
			if (l, c) in amb:
				full_no_piece["ambigua_top1"].append({"cell": [l, c], "sections": sorted(set(amb[(l, c)]))})
			else:
				full_no_piece["sem_explicacao"].append([l, c])
	return {"colocada_foto0": placed_bad["0"], "colocada_foto_incerta": placed_bad["-1"],
			"cheia_sem_peca": full_no_piece}


def _origin_of(pr, pid: str) -> str:
	for ev in reversed(pr.events()):
		if ev["action"] == "placed" and ev["piece"] == pid:
			return ev.get("origin") or "log"
	return "log"


# ---------------------------------------------------------------- stages
def stage_gt(pr, art, summary) -> None:
	prof = pr.profile
	summary["gt"] = {}
	for tag, rel in GT_SCANS.items():
		t0 = time.time()
		r = ingest_scan(pr, os.path.join(REPO, rel), None, dpi=prof.dpi, kind="gt")
		if "error" in r:
			raise SystemExit(f"GT {tag}: {r['error']}")
		cells, notes = gt_cells(pr, tag, r["pieces"])
		tt = theta_test(pr, art, cells)
		bt = tt["by_theta"]
		exp = GT_THETA_EXPECTED[tag]
		best = max(bt, key=lambda t: (bt[t]["F_ok"] + bt[t]["TB_ok"], t == exp))
		with_img = [t for t in bt if bt[t]["dE_mean"] is not None]
		if best != exp:
			notes.append(f"{tag}: F + T<->B preferem theta {best}, esperado {exp} (usado {best})")
		if not with_img:
			# the GT cells are beyond the art file (B2 = row 47, docs/diagnostico/arte/ARTREG.md): the rotation is the
			# side-based one anyway; there is no image check to report
			notes.append(f"{tag}: imagem: sem arte nas células GT")
		else:
			img = min(with_img, key=lambda t: bt[t]["dE_mean"])
			if img != best:
				notes.append(f"{tag}: a imagem sozinha preferia theta {img} (dE {bt[img]['dE_mean']} vs {bt[best]['dE_mean']})")
		gt = {"cells": [{"index": r["numbers"][pid], "cell": list(cell),
						 "theta_deg": round(tt["per_piece"][pid][best][2], 2) if pid in tt["per_piece"] else float(best)}
						for pid, cell in cells.items()]}
		known = _apply_known_cells(pr, r["pieces"], r["numbers"], gt)
		discarded = []
		for pid in r["pieces"]:
			if pid not in cells:
				q = pr.piece(pid)
				pr.discard(pid, f"GT {tag}: objeto fora da GT (área {q.area_mm2:.0f} mm²; faixa em L montada ou fragmento)")
				discarded.append({"piece": pid, "area_mm2": q.area_mm2})
		pr.save()
		est = {}
		for e in known:
			k = e.get("estado") or "erro"
			est[k] = est.get(k, 0) + 1
		summary["gt"][tag] = {"scan": r["scan_id"], "n_objetos": len(r["pieces"]), "n_gt": len(cells),
							  "theta": best, "theta_teste": {str(k): v for k, v in bt.items()}, "estados": est,
							  "erros": [e for e in known if "error" in e], "descartadas": discarded, "notas": notes,
							  "s": round(time.time() - t0, 1)}
		print(f"GT {tag}: {r['scan_id']} {len(r['pieces'])} objetos, {len(cells)} GT, theta {best} "
			  f"{ {k: (v['F_ok'], v['TB_ok'], v['n_adj'], v['dE_mean'], v['dE_wins']) for k, v in bt.items()} } estados {est} "
			  f"descartadas {len(discarded)} {notes} ({time.time() - t0:.0f} s)")


def stage_hints(pr, summary) -> None:
	"""User hints (``HINTS_TIAGO``): cells marked assembled before the sections are solved."""
	evs = [pr.mark_cell_full(cell) for cell in HINTS_TIAGO]
	pr.save()
	summary["pistas"] = {"celulas": [list(c) for c in HINTS_TIAGO],
						 "novas": sum(1 for e in evs if e.get("action") == "cell_occupied_by_user")}
	print(f"pistas do Tiago: {summary['pistas']['novas']}/{len(HINTS_TIAGO)} células marcadas cheias")


def stage_sky(pr, summary) -> None:
	mm = pr.profile.mm_per_px()
	summary["lote1"] = {"scans": {}}
	by_sheet = {}
	for sheet, rel, lote in SKY:
		t0 = time.time()
		r = ingest_scan(pr, os.path.join(REPO, rel), lote, dpi=pr.profile.dpi, kind="soltas")
		if "error" in r:
			raise SystemExit(f"lote {lote} {sheet}: {r['error']}")
		by_sheet[sheet] = r["pieces"]
		ns = [r["numbers"][p] for p in r["pieces"]]
		summary["lote1"]["scans"][sheet] = {"scan": r["scan_id"], "lote": lote, "n": len(r["pieces"]), "n_no_lote": [min(ns), max(ns)],
											"rejeitados": r["rejected"], "duplos": r["double"]}
		print(f"lote {lote} {sheet}: {r['scan_id']} {len(r['pieces'])} peças #{min(ns)}-{max(ns)} rejeitados "
			  f"{len(r['rejected'])} duplos {len(r['double'])} ({time.time() - t0:.0f} s)")
	conf = json.load(open(os.path.join(GEM, "ereal2_confirmacoes.json"), encoding="utf-8"))
	summary["confirmacoes"] = []
	for key, spec in CONFIRMATIONS.items():
		cm = np.asarray(conf[key]["centro_mm"], float)
		best, bd = None, np.inf
		for pid in by_sheet[spec["sheet"]]:
			d = float(np.linalg.norm(bbox_centre_mm(pr.piece(pid).bbox, mm) - cm))
			if d < bd:
				best, bd = pid, d
		if bd > CONF_MM:
			raise SystemExit(f"{key}: nenhuma peça a <= {CONF_MM} mm de {cm.tolist()} (mais perto {bd:.2f} mm)")
		if spec["kind"] == "cell":
			out = confirm(pr, best, cell=spec["cell"], origin="gemeo", requery=False)
		else:
			out = confirm(pr, best, position_known=spec["cell"], requery=False)
		if "error" in out:
			raise SystemExit(f"{key}: {out['error']}")
		p = pr.piece(best)
		row = {"gt": key, "proposta": conf[key]["proposta"], "piece": best, "n_no_lote": p.n_no_lote,
			   "dist_centro_mm": round(bd, 2), "estado": p.estado, "celula": list(p.celula), "msgs": out["messages"]}
		summary["confirmacoes"].append(row)
		print(f"confirmação {key} ({conf[key]['proposta']}): {best} #{p.n_no_lote} a {bd:.2f} mm -> {p.estado} {p.celula}")


def stage_pages(pr, summary) -> None:
	summary["paginas"] = {}
	ids_of = {}
	for kind, page in PAGES:
		t0 = time.time()
		path = os.path.join(REPO, "images", "pieces", "legado", f"{kind}_{page}_300dpi.jpg")
		r = legacy.ingest_page(pr, path, kind, page, auto_anchor=False)
		if "error" in r:
			raise SystemExit(f"{kind}_{page}: {r['error']}")
		pr.save()
		ids_of[(kind, page)] = [p.id for p in pr.pieces.values() if p.scan_id == r["scan_id"]]
		dec = {}
		for s in r["sections"]:
			dec[s.get("decision", "erro")] = dec.get(s.get("decision", "erro"), 0) + 1
		summary["paginas"][f"{kind}_{page}"] = {"scan": r["scan_id"], "n": r["n_pieces"], "secoes": len(r["sections"]),
												"decisao_pagina": dec, "same_as_gt": r["same_as"], "duplos": r["double"],
												"s": round(time.time() - t0, 1)}
		print(f"{kind}_{page}: {r['scan_id']} {r['n_pieces']} peças, {len(r['sections'])} secções {dec}, "
			  f"same_as {len(r['same_as'])} ({time.time() - t0:.0f} s)")
	# p13 = p04 scanned again: every p13 piece that is the same physical piece as a p04 piece -> same_as
	dup, orig = DUP_PAGE
	A = [{"key": pid, "shape": pr.shape(pid), "mean_lab": pr.piece(pid).mean_lab, "cell": (1, 1)}
		 for pid in ids_of[("montado", orig)]]
	B = [{"key": pid, "shape": pr.shape(pid), "mean_lab": pr.piece(pid).mean_lab} for pid in ids_of[("montado", dup)]]
	ms = [m for m in legacy.match_gt(A, B, pr.profile) if m["kind"] == "mesma"]
	done = set()
	for m in ms:
		if pr.piece(m["page"]).same_as:
			continue
		pr.mark_same_as(m["page"], m["gt"])
		done.add(m["page"])
	# the rest (shape match failed): the local grid cells of both pages. Every matched pair votes for a
	# (p04 section, rotation, offset) that maps the p13 local cell onto the p04 local cell; the p13 piece
	# without a match takes the p04 piece found at its mapped cell (the layout itself was re-spread by
	# hand: a similarity fit of the bbox centres leaves ~5 mm residuals)
	sid13 = pr.piece(ids_of[("montado", dup)][0]).scan_id
	sid04 = pr.piece(ids_of[("montado", orig)][0]).scan_id
	rc13 = {pid: tuple(rc) for s_ in pr.sections.values() if s_.scan_id == sid13 for pid, rc in s_.cells_local.items()}
	at04 = {pid: (s_.id, tuple(rc)) for s_ in pr.sections.values() if s_.scan_id == sid04 for pid, rc in s_.cells_local.items()}

	def rot_rc(rc, k):
		r, c = rc
		for _ in range(k % 4):
			r, c = c, -r
		return r, c

	votes = {}
	for pid in ids_of[("montado", dup)]:
		o = pr.piece(pid).same_as
		if pid in rc13 and o in at04:
			gid, rcb = at04[o]
			for k in range(4):
				rr = rot_rc(rc13[pid], k)
				key = (gid, k, rcb[0] - rr[0], rcb[1] - rr[1])
				votes[key] = votes.get(key, 0) + 1
	best_t = {}
	for (gid, k, dr, dc), n in votes.items():
		if n >= 2 and n > best_t.get(gid, (None, 0))[1]:
			best_t[gid] = ((k, dr, dc), n)
	taken = {pr.piece(pid).same_as for pid in ids_of[("montado", dup)] if pr.piece(pid).same_as}
	by_cell = []
	for pid in ids_of[("montado", dup)]:
		if pr.piece(pid).same_as or pid not in rc13:
			continue
		for gid, ((k, dr, dc), n) in sorted(best_t.items(), key=lambda t: -t[1][1]):
			rr = rot_rc(rc13[pid], k)
			tgt = (rr[0] + dr, rr[1] + dc)
			hit = [o for o, (g, rc) in at04.items() if g == gid and rc == tgt and o not in taken]
			if hit:
				pr.mark_same_as(pid, hit[0])
				taken.add(hit[0])
				by_cell.append({"piece": pid, "same_as": hit[0], "section_p04": gid, "votos": n})
				break
	# last resort (a p04 counterpart in another p04 section, missed by the mutual-NN rule): the nearest untaken
	# p04 piece of the same class with free distance <= t95 and mean-Lab dE <= SAME_PIECE_DE
	from src.twin import shape_distances
	t95 = float(pr.profile.calibration["silhueta_silhueta"]["t95"])
	by_shape = []
	for pid in ids_of[("montado", dup)]:
		q = pr.piece(pid)
		if q.same_as or pr.shape(pid) is None:
			continue
		cand = [o for o in ids_of[("montado", orig)] if o not in taken and pr.shape(o) is not None
				and pr.shape(o).cls == pr.shape(pid).cls]
		if not cand:
			continue
		d, _ = shape_distances(pr.shape(pid), [pr.shape(o) for o in cand])
		k = int(np.argmin(d))
		de = float(np.linalg.norm(np.asarray(q.mean_lab, float) - np.asarray(pr.piece(cand[k]).mean_lab, float)))
		if d[k] <= t95 and de <= legacy.SAME_PIECE_DE:
			pr.mark_same_as(pid, cand[k])
			taken.add(cand[k])
			by_shape.append({"piece": pid, "same_as": cand[k], "d_mm": round(float(d[k]), 3), "dE": round(de, 1)})
	left = [pid for pid in ids_of[("montado", dup)] if not pr.piece(pid).same_as]
	pr.save()
	summary["p13"] = {"n": len(ids_of[("montado", dup)]), "same_as_p04_forma_cor": len(done),
					  "same_as_p04_celulas": by_cell, "same_as_p04_forma_sem_nn": by_shape, "transformacoes": {g: {"rot_k": t[0][0], "dr": t[0][1], "dc": t[0][2],
																			 "votos": t[1]} for g, t in best_t.items()},
					  "sem_par": left}
	print(f"montado_{dup}: {len(done)}/{len(ids_of[('montado', dup)])} peças same_as de montado_{orig} por forma+cor, "
		  f"{len(by_cell)} pelas células locais {by_cell}, {len(by_shape)} pela forma sem NN mútuo {by_shape}; "
		  f"sem par {left} (as restantes são same_as de GT)")


def stage_solve(pr, summary) -> None:
	t0 = time.time()
	n0 = len(pr.events())
	out = legacy.solve_project_sections(pr)
	pr.save()
	new = pr.events()[n0:]
	conflicts = [c for ev in new if ev["action"] == "section_anchored" for c in ev.get("conflicts", [])]
	placed = sum(len(ev["placements"]) for ev in new if ev["action"] == "section_anchored")
	# a conflict = a page piece anchored on a cell that a GT piece already holds: the same physical piece
	# (the GT piece prevails, the page piece stays em_seccao and becomes same_as the occupant)
	conf_same = {"ja_same_as_ocupante": 0, "marcadas": 0, "same_as_outra": []}
	for c in conflicts:
		q = pr.piece(c["piece"])
		if q.same_as == c["occupant"]:
			conf_same["ja_same_as_ocupante"] += 1
		elif q.same_as:
			conf_same["same_as_outra"].append({"piece": q.id, "same_as": q.same_as, "occupant": c["occupant"]})
		else:
			pr.mark_same_as(q.id, c["occupant"])
			conf_same["marcadas"] += 1
	# GT prevails: a GT piece kept as posicao_conhecida (its cell was not full in the photo) whose cell an anchored
	# section fills is the piece the page shows there: the GT piece is placed (the page proves the cell is full) and
	# the page piece, now in conflict, becomes same_as the GT piece (with or without a shape + colour match)
	fixed = []
	for g in sorted(pr.pieces.values(), key=lambda q: q.id):
		if g.estado != "posicao_conhecida" or g.celula is None or _origin_of_known(pr, g.id) != "gt":
			continue
		cell = pr.board[g.celula]
		if cell["estado"] != "colocada" or cell["fonte"] != "legado_scan":
			continue
		p = pr.piece(cell["peca_id"])
		gid = p.seccao_id
		a = dict(pr.sections[gid].anchor)
		pr.unanchor_section(gid)
		pr.place(g.id, g.celula, origin="gt", theta_deg=g.theta_deg)
		ev = pr.anchor_section(gid, a["l0"], a["c0"], rot=a["rot"], mirror=a["mirror"], fonte="legado_scan",
							   confianca=a.get("confianca"), margin=a.get("margin"))
		if not pr.piece(p.id).same_as:
			pr.mark_same_as(p.id, g.id)
		fixed.append({"page_piece": p.id, "gt": g.id, "cell": list(g.celula), "section": gid,
					  "same_as_por_forma_cor": p.same_as == g.id, "conflicts": ev["conflicts"]})
	# page pieces that are the same physical piece as a GT piece but were anchored on another cell (disagreement)
	elsewhere = []
	for p in pr.pieces.values():
		if p.estado == "colocada" and p.same_as and pr.piece(p.same_as).celula not in (None, p.celula):
			elsewhere.append({"piece": p.id, "cell": list(p.celula), "same_as": p.same_as,
							  "cell_gt": list(pr.piece(p.same_as).celula)})
	pr.save()
	summary["solve"] = {"anchored": out["anchored"], "n_anchored": len(out["anchored"]), "com_pista": out.get("hinted", []),
						"ambiguous": [{"section": a["section"], "reasons": a["reasons"], "questions": a["questions"]}
									  for a in out["ambiguous"]],
						"pairs": out["pairs"], "placed": placed, "conflicts": conflicts, "conflitos_same_as": conf_same,
						"gt_fixes": fixed, "same_as_gt_noutra_celula": elsewhere,
						"s": round(time.time() - t0, 1)}
	print(f"solve: {len(out['anchored'])} secções ancoradas ({placed} peças), {len(out['ambiguous'])} ambíguas, "
		  f"{out['pairs']} pares; conflitos com GT {len(conflicts)} {conf_same}; correções GT {len(fixed)}; "
		  f"same_as GT colocadas noutra célula {elsewhere} ({time.time() - t0:.0f} s)")


def stage_artreg(pr, summary) -> None:
	"""Art registration (``src/artreg.py``): the placed pieces fix the board mm -> art px affine,
	written to ``puzzle.json`` (``art.registration``) before the border and the query use the art."""
	from src import artreg
	t0 = time.time()
	res = artreg.run(pr, progress=None)
	if "error" in res:
		summary["arte"] = {"error": res["error"]}
		print(f"arte: {res['error']}")
		return
	summary["arte"] = {"escrito": res["written"], **res["registration"], "decomposicao": res["decomposition"],
					   "s": round(time.time() - t0, 1)}
	rc = res["registration"]["residual_cells"]
	print(f"arte: {res['n_points']} pontos, resíduo {rc['before']['median']} -> {rc['after']['median']} célula "
		  f"(mediana), escrito {res['written']} ({time.time() - t0:.0f} s)")


def stage_border(pr, summary) -> None:
	"""Border completion (``src/border.py``): the physical border is complete except (1,29) (Tiago,
	2026-11-01), so the border pieces of the sections left unanchored fill the free border cells."""
	from src import border
	t0 = time.time()
	sol = border.solve_border(pr)
	if sol.error:
		summary["borda"] = {"error": sol.error}
		print(f"borda: {sol.error}")
		return
	ops = border.apply_solution(pr, sol)
	pr.save()
	req = [ci for ci in sol.cell_info.values() if ci["required"]]
	summary["borda"] = {
		"operacoes": len(ops), "custo": round(sol.cost, 3), "pinos": len(sol.pins),
		"confianca": {k: sum(1 for ci in req if ci["confianca"] == k) for k in ("alta", "media", "baixa")},
		"segmentos": [{"nome": sg["name"], "blocos": sg["blocks"], "margem": round(sg["margin"], 3)} for sg in sol.segments],
		"sobras": [lo["block"] for lo in sol.leftover], "em_falta": pr.missing_border_cells(),
		"s": round(time.time() - t0, 1)}
	print(f"borda: {len(ops)} operações, confiança {summary['borda']['confianca']}, sobras {summary['borda']['sobras']}, "
		  f"em falta {summary['borda']['em_falta']} ({time.time() - t0:.0f} s)")


def _origin_of_known(pr, pid: str) -> str:
	for ev in reversed(pr.events()):
		if ev["action"] == "position_known" and ev["piece"] == pid:
			return ev.get("origin") or "manual"
	return "manual"


def counts(pr) -> dict:
	st = pr.stats()
	src = {}
	for _, cell in pr.board.iter_cells():
		if cell["estado"] == "colocada":
			p = pr.piece(cell["peca_id"])
			k = cell["fonte"] if cell["fonte"] != "log" else f"log/{_origin_of(pr, p.id)}"
			src[k] = src.get(k, 0) + 1
	same = sum(1 for p in pr.pieces.values() if p.same_as)
	unanch = [s for s in pr.sections.values() if not s.anchor.get("anchored")]
	rescans = [s for s in unanch if all(pr.piece(pid).same_as for pid in s.cells_local)]
	return {"stats": st, "colocadas_por_fonte": src, "same_as": same,
			"seccoes": {"total": len(pr.sections), "ancoradas": len(pr.sections) - len(unanch),
						"por_ancorar_montado": sum(1 for s in unanch if s.kind == "montado" and s not in rescans),
						"por_ancorar_blocos": sum(1 for s in unanch if s.kind == "blocos"),
						"re_scan": len(rescans),
						"pecas_em_seccao_por_ancorar": sum(len(s.cells_local) for s in unanch if s not in rescans)}}


def fetch_body(path: str) -> str:
	with open(path, encoding="utf-8") as f:
		return "".join(f.readlines()[1:])     # line 1 carries the time stamp


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("--project", default=PROJECT)
	ap.add_argument("--no-query", action="store_true")
	ap.add_argument("--out", default=None, help="pasta do resumo (omissão $PPF_SCRATCH/ingest_all)")
	args = ap.parse_args()
	out_dir = args.out or os.path.join(os.environ.get("PPF_SCRATCH") or os.path.join(REPO, "scratch"), "ingest_all")
	os.makedirs(out_dir, exist_ok=True)
	T0 = time.time()
	summary = {"t": time.strftime("%Y-%m-%dT%H:%M:%S")}
	reset_project(args.project)
	pr = Project.create(args.project, os.path.join(args.project, "puzzle.json"))
	r = register(pr, photo_from_json(OCC, OCC_FIX))
	summary["foto"] = r
	print(f"foto: {r['photo_id']} {r['changes']}")
	stage_hints(pr, summary)
	art = CellArt.load(pr.profile, REPO)
	stage_gt(pr, art, summary)
	stage_sky(pr, summary)
	stage_pages(pr, summary)
	stage_solve(pr, summary)
	stage_artreg(pr, summary)
	stage_border(pr, summary)
	summary["t_ingestao_s"] = round(time.time() - T0, 1)
	bad = pr.check_invariants(disk=True)
	summary["invariantes"] = bad or "OK"
	print(f"ingestão: {time.time() - T0:.0f} s; invariantes {bad or 'OK'}")
	if not args.no_query:
		from src.query import print_summary, run_query
		t1 = time.time()
		entries = run_query(pr)
		summary["t_query_s"] = round(time.time() - t1, 1)
		print_summary(pr, entries)
		by = {}
		for e in entries:
			k = f"{e['origin']}/{e['decision']}"
			by[k] = by.get(k, 0) + 1
		summary["fetch"] = {"n": len(entries), "por_origem_decisao": by,
							"top10": [{k: e.get(k) for k in ("ordem", "lote", "n_no_lote", "piece", "section", "cell", "origin",
															 "decision", "margin", "dE", "d1_mm", "query")} for e in entries[:10]]}
		print(f"query: {time.time() - t1:.0f} s; {by}")
		bad = pr.check_invariants(disk=True)
		summary["invariantes_pos_query"] = bad or "OK"
		# determinism: reopen a copy (the query registers pairs and logs) and run again
		cp = os.path.join(out_dir, "copia_projeto")
		if os.path.exists(cp):
			shutil.rmtree(cp)
		shutil.copytree(args.project, cp)
		t2 = time.time()
		pr2 = Project.open(cp)
		run_query(pr2)
		same = fetch_body(os.path.join(args.project, "fetch.md")) == fetch_body(os.path.join(cp, "fetch.md"))
		summary["determinismo"] = {"fetch_md_igual": same, "t_s": round(time.time() - t2, 1),
								   "invariantes_copia": pr2.check_invariants(disk=True) or "OK"}
		print(f"determinismo: fetch.md igual = {same} ({time.time() - t2:.0f} s)")
	summary["contagens"] = counts(pr)
	summary["m14"] = m14_compare(pr)
	m = summary["m14"]
	print(f"M14: colocadas em foto 0 {len(m['colocada_foto0'])}, em foto -1 {len(m['colocada_foto_incerta'])}; "
		  f"cheias sem peça: ambígua top-1 {len(m['cheia_sem_peca']['ambigua_top1'])}, "
		  f"sem explicação {len(m['cheia_sem_peca']['sem_explicacao'])}")
	print(json.dumps(summary["contagens"], ensure_ascii=False))
	with open(os.path.join(out_dir, "resumo.json"), "w", encoding="utf-8") as f:
		json.dump(summary, f, ensure_ascii=False, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
	print(f"resumo: {os.path.join(out_dir, 'resumo.json')}; total {time.time() - T0:.0f} s")


if __name__ == "__main__":
	main()
