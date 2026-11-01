"""Reproduce the legacy analysis (docs/diagnostico/legado/LEGADO.md) without touching any project.

	PPF_SCRATCH=... python tools/diagnostico/legado/run_legado.py [--pages montado_p01 ...] [--no-figs]

Steps: segmentation cache (``segcache_legado.py``, ``$PPF_SCRATCH/legado/*.npz``) ->
:func:`src.legacy.analyse_page` for the 18 pages -> silhouette twins between all pieces ->
:func:`src.legacy.solve_pages` -> automatic GT (E-sym A1/B2, BE, BD matched by shape) ->
comparison with the M14 occupancy map -> ``docs/diagnostico/legado/legado_resultados.json``,
small figures in ``docs/diagnostico/legado/`` and large ones in ``$PPF_SCRATCH/legado/fig``.
The report text (LEGADO.md) is written by hand from ``legado_resultados.json`` and the
printed summary.
"""

import argparse
import json
import os
import sys
import time

import cv2
import numpy as np
from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from segcache_legado import PAGES, cache_dir, load_npz, scan_paths, segment_to_npz  # noqa: E402
from src import legacy  # noqa: E402
from src.ingest import grid_order  # noqa: E402
from src.locate import CellArt, piece_mean_lab  # noqa: E402
from src.profile import PuzzleProfile  # noqa: E402
from src.shape import analyse, side_complement  # noqa: E402

OUT_DOC = os.path.join(REPO, "docs", "diagnostico", "legado")
PROFILE = os.path.join(REPO, "projects", "alpes", "puzzle.json")
OCC = os.path.join(REPO, "docs", "diagnostico", "ocupacao", "ocupacao_2026-10-31.json")
OCC_FIX = {(1, 29): 0, (1, 34): 1}     # confirmed by Tiago 2026-11-01 (estado-e-plano §0)
README_COUNTS = {"montado_p01": 43, "montado_p02": 46, "montado_p03": 18, "montado_p04": 44, "montado_p05": 50,
				 "montado_p06": 48, "montado_p07": 36, "montado_p08": 37, "montado_p09": 34, "montado_p10": 39,
				 "montado_p11": 38, "montado_p12": 47, "montado_p13": 44, "montado_p14": 55, "montado_p15": 56,
				 "blocos_p01": 28, "blocos_p02": 36, "blocos_p03": 11}   # p12/p15: +1 objeto duplo (README)
FIG_MAX = 1400
FIG_QUALITY = 75
FIG_BYTES = 200_000


def read_rgb(path):
	im = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
	return cv2.cvtColor(im, cv2.COLOR_BGR2RGB)


def seg_of(name):
	p = os.path.join(cache_dir(), f"{name}.npz")
	if not os.path.exists(p):
		print(segment_to_npz(name, scan_paths()[name], p))
	return load_npz(p)


# ---------------------------------------------------------------- GT pieces (measurement only)
def gt_items(profile):
	"""GT pieces with their true cell: E-sym A1/B2 (grid order), BE (json contours), BD (json bbox -> cache)."""
	out = []
	mm = profile.mm_per_px()
	for tag in ("A1", "B2"):
		seg = seg_of(f"gt_{tag}")
		rgb = read_rgb(os.path.join(REPO, scan_paths()[f"gt_{tag}"]))
		P = seg["pieces"]
		n = grid_order([p["bbox"] for p in P])
		for p, k in zip(P, n):
			i = k - 1
			f, kk = divmod(i, 5)
			if tag == "A1":
				cell = (1, 5 + i)
			else:   # B(f, k) holds the twin of A(f, 4 - k) (images/pieces/gemeos_2026-10-30.md)
				cell = tuple(profile.twin(1, 5 + 5 * f + (4 - kk)))
			rgba, _ = legacy.crop_rgba(rgb, p["contour"])
			out.append({"key": f"{tag}#{k}", "shape": analyse(p["contour"], mm), "mean_lab": list(piece_mean_lab(rgba)),
						"cell": cell, "set": tag})
	be = json.load(open(os.path.join(REPO, "docs", "diagnostico", "gemeos", "ereal2_gt_BE.json"), encoding="utf-8"))
	rgb = read_rgb(os.path.join(REPO, be["ficheiro"]))
	for e in be["soltas"]:
		c = np.array(e["contorno_px"], float)
		rgba, _ = legacy.crop_rgba(rgb, c)
		out.append({"key": f"BE({e['l']},{e['c']})", "shape": analyse(c, mm), "mean_lab": list(piece_mean_lab(rgba)),
					"cell": (e["l"], e["c"]), "set": "BE"})
	bd = json.load(open(os.path.join(REPO, "docs", "diagnostico", "gemeos", "ereal_gt.json"), encoding="utf-8"))
	seg = seg_of("gt_BD")
	rgb = read_rgb(os.path.join(REPO, bd["ficheiros"]["soltas"]))
	for e in bd["soltas"]:
		bx = np.array(e["bbox"], float)
		best, bi = 0.0, None
		for p in seg["pieces"]:
			b = np.array(p["bbox"], float)
			ix = max(0, min(bx[0] + bx[2], b[0] + b[2]) - max(bx[0], b[0]))
			iy = max(0, min(bx[1] + bx[3], b[1] + b[3]) - max(bx[1], b[1]))
			iou = ix * iy / (bx[2] * bx[3] + b[2] * b[3] - ix * iy)
			if iou > best:
				best, bi = iou, p
		if bi is None or best < 0.5:
			continue
		rgba, _ = legacy.crop_rgba(rgb, bi["contour"])
		out.append({"key": f"BD({e['l']},{e['c']})", "shape": analyse(bi["contour"], mm), "mean_lab": list(piece_mean_lab(rgba)),
					"cell": (e["l"], e["c"]), "set": "BD"})
	return out


# ---------------------------------------------------------------- analysis
def analyse_all(profile, art, prior, pages):
	results = []
	for pg in pages:
		t0 = time.time()
		kind = "blocos" if pg.startswith("blocos") else "montado"
		path = os.path.join(REPO, scan_paths()[pg])
		res = legacy.analyse_page(path, profile, art, prior, kind, seg=seg_of(pg), rgb=read_rgb(path), name=pg)
		print(f"{pg}: {len(res.pieces)} peças, {len(res.components)} componentes, {time.time() - t0:.0f} s", flush=True)
		results.append(res)
	return results


def gt_eval(results, gts, profile):
	"""Shape-matched GT per page piece and the verdict of the current placement."""
	page_items = [{"key": (pi, k), "shape": p.shape, "mean_lab": p.mean_lab}
				  for pi, r in enumerate(results) for k, p in enumerate(r.pieces) if not p.excluded and p.shape is not None]
	matches = legacy.match_gt(gts, page_items, profile)
	by_piece = {}
	for m in matches:
		by_piece.setdefault(m["page"], []).append(m)
	rows = []
	for (pi, k), ms in by_piece.items():
		r = results[pi]
		comp = r.comp_of(k)
		if comp is not None and comp.decision == "duplicada":
			continue
		b = comp.best if comp is not None else None
		got = tuple(b["cells"][k]) if b is not None and k in b["cells"] else None
		cells = {m["cell"] for m in ms}
		rows.append({"page": r.name, "piece": k, "n": r.pieces[k].n, "comp": comp.id if comp else -1,
					 "decision": comp.decision if comp else "-", "true": sorted(cells), "got": got,
					 "ok": got in cells if got is not None else None, "kinds": [m["kind"] for m in ms],
					 "gt": [m["gt"] for m in ms], "d": [round(m["d_mm"], 3) for m in ms], "dE": [round(m["dE"], 1) for m in ms]})
	return matches, rows


def pair_check(results, solved, profile):
	"""Twin pairs whose two pieces have a placement: cell agreement and, among those, rotation agreement."""
	from src.locate import wrap_deg
	n = cell_ok = rot_ok = 0
	dev = []
	for a, b, d, phi, m in solved["pairs"]:
		ca, cb = results[a[0]].comp_of(a[1]), results[b[0]].comp_of(b[1])
		if ca is None or cb is None or not ca.placements or not cb.placements:
			continue
		pa, pb = ca.best, cb.best
		n += 1
		if tuple(profile.twin(*pa["cells"][a[1]])) == tuple(pb["cells"][b[1]]):
			cell_ok += 1
			x = float(wrap_deg(phi - profile.twin_rotation_deg() - (results[a[0]].pieces[a[1]].theta_deg + pa["rot"])
								+ (results[b[0]].pieces[b[1]].theta_deg + pb["rot"])))
			dev.append(round(x, 1))
			rot_ok += abs(x) < legacy.TWIN_ROT_TOL
	return {"n": n, "cell_ok": cell_ok, "rot_ok": rot_ok, "dev": dev}


def summary(results, rows0, rows, matches, solved, profile):
	print(f"pares de gémeas: {len(solved['pairs'])}; iterações {solved['iterations']}; movimentos {len(solved['moves'])}; "
		  f"duplicadas {solved.get('duplicates')}")
	for mv in solved["moves"][:40]:
		print("   mov", mv)
	pc = pair_check(results, solved, profile)
	print(f"pares com as duas peças colocadas: {pc['n']}; célula gémea certa {pc['cell_ok']}; rotação certa {pc['rot_ok']}; desvios {pc['dev'][:30]}")
	for tag, rr in (("antes", rows0), ("depois", rows)):
		ok = sum(1 for x in rr if x["ok"])
		n = sum(1 for x in rr if x["got"] is not None)
		oka = sum(1 for x in rr if x["ok"] and x["decision"] == "alta")
		na = sum(1 for x in rr if x["got"] is not None and x["decision"] == "alta")
		print(f"GT {tag}: {ok}/{n} verificáveis certas; nas 'alta' {oka}/{na}")
	for r in results:
		for c in r.components:
			if not c.placements:
				continue
			g = [x for x in rows if x["page"] == r.name and x["comp"] == c.id]
			b = c.best
			if len(c.members) < 2 and not g:
				continue
			print(f"  {r.name} c{c.id} n={len(c.members)} {c.decision} m={c.margin:.2f} gap={c.energy_gap:.1f} best={b['cell0']} rot {b['rot']}"
				  f" sat {b['twin_sat']} viol {b['twin_viol']} ov {b.get('overlap')} {b['origin']} GT {sum(1 for x in g if x['ok'])}/{len(g)} {c.reasons}")



# ---------------------------------------------------------------- GT veto, statistics, M14
def gt_veto(results, rows):
	"""Step 7: a component whose GT is not all right is never 'alta' (counted, so the veto is visible)."""
	vetoed = []
	for r in results:
		for c in r.components:
			g = [x for x in rows if x["page"] == r.name and x["comp"] == c.id and x["got"] is not None]
			ok = sum(1 for x in g if x["ok"])
			c.gt = {"ok": ok, "n": len(g)}
			if g and ok != len(g) and c.decision == "alta":
				c.decision = "ambigua"
				c.reasons.append(f"GT {ok}/{len(g)}")
				vetoed.append((r.name, c.id))
	return vetoed


def side_stats(results, profile, gts, rng_seed=0):
	"""side_complement RMS: true BE adjacencies (GT), accepted / rejected page edges, random T-B pairs."""
	from src.locate import body_beta_deg
	out = {}
	be = [g for g in gts if g["set"] == "BE"]
	# BE loose scan: block turned 90 deg anticlockwise (ereal2_gt_BE.json) -> scan direction d is board direction d + 90
	cell = {g["cell"]: g for g in be}
	vals, kinds = [], []
	for g in be:
		sh = g["shape"]
		dirs, ok, _ = legacy.label_sides(sh, body_beta_deg(sh))
		if not ok:
			continue
		bd = {legacy._DIRS[(legacy._DIRS.index(d) + 1) % 4]: i for d, i in dirs.items()}
		g["_bd"] = bd
	for g in be:
		if "_bd" not in g:
			continue
		for (dl, dc, o1, o2) in ((0, 1, "E", "W"), (1, 0, "S", "N")):
			q = cell.get((g["cell"][0] + dl, g["cell"][1] + dc))
			if q is None or "_bd" not in q:
				continue
			sa, sb = g["shape"].sides[g["_bd"][o1]], q["shape"].sides[q["_bd"][o2]]
			kinds.append(sa.kind + sb.kind)
			if {sa.kind, sb.kind} == {"T", "B"}:
				vals.append(side_complement(sa, sb))
	v = np.array(vals)
	out["be_true"] = {"n": len(kinds), "n_TB": len(vals), "rms": _pct(v[:, 0]) if len(v) else None,
					  "dl": _pct(v[:, 1]) if len(v) else None}
	acc = [e["rms"] for r in results for e in getattr(r, "edges", []) if e.get("verdict") == "accepted"]
	rej = [e["rms"] for r in results for e in getattr(r, "edges", []) if e.get("why") in ("rms", "dl")]
	out["edges_accepted"] = {"n": len(acc), "rms": _pct(np.array(acc)) if acc else None}
	out["edges_rejected_rms_dl"] = {"n": len(rej), "rms": _pct(np.array(rej)) if rej else None}
	ver = {}
	for r in results:
		for e in getattr(r, "edges", []):
			ver[e.get("verdict") or e.get("why")] = ver.get(e.get("verdict") or e.get("why"), 0) + 1
	out["edge_verdicts"] = ver
	T, B = [], []
	for r in results:
		for p in r.pieces:
			if p.shape is not None and p.shape.ok:
				T += [s for s in p.shape.sides if s.kind == "T"]
				B += [s for s in p.shape.sides if s.kind == "B"]
	rng = np.random.default_rng(rng_seed)
	rnd = np.array([side_complement(T[rng.integers(len(T))], B[rng.integers(len(B))])[0] for _ in range(3000)])
	out["random_TB"] = {"n": len(rnd), "rms": _pct(rnd), "frac_le_max": float(np.mean(rnd <= legacy.SIDE_RMS_MAX))}
	return out


def _pct(x):
	x = np.asarray(x, float)
	x = x[np.isfinite(x)]
	if not len(x):
		return None
	return {k: round(float(np.percentile(x, q)), 3) for k, q in (("p05", 5), ("p10", 10), ("p25", 25), ("p50", 50),
																  ("p75", 75), ("p90", 90), ("max", 100))}


def m14_compare(results, prior_raw, profile):
	"""Cells of the 'alta' montado units against the M14 map (the map also entered the energy: not independent)."""
	R, C = profile.rows, profile.cols
	scan = {}
	for r in results:
		if r.kind != "montado":
			continue
		for c in r.components:
			if c.decision != "alta" or not c.placements:
				continue
			for k, cell in c.best["cells"].items():
				scan[tuple(cell)] = (r.name, r.pieces[k].n)
	full_both = prior_raw == 1

	def neigh_full(l, c):
		nb = [(l - 1, c), (l + 1, c), (l, c - 1), (l, c + 1)]
		nb = [(a, b) for a, b in nb if 1 <= a <= R and 1 <= b <= C]
		return all(full_both[a - 1, b - 1] for a, b in nb)

	scan_not_full = []
	for (l, c), (pg, n) in sorted(scan.items()):
		v = int(prior_raw[l - 1, c - 1])
		if v != 1:
			why = ("M14 provavelmente errou" if (profile.is_border(l, c) or neigh_full(l, c))
				   else "provavelmente colocada depois da foto")
			scan_not_full.append({"cell": [l, c], "m14": v, "page": pg, "n": n, "leitura": why})
	full_no_scan = [[l, c] for l in range(1, R + 1) for c in range(1, C + 1)
					if prior_raw[l - 1, c - 1] == 1 and (l, c) not in scan]
	return {"n_scan_alta": len(scan), "n_m14_full": int((prior_raw == 1).sum()), "scan_not_full": scan_not_full,
			"m14_full_without_alta": full_no_scan, "n_m14_full_without_alta": len(full_no_scan)}


# ---------------------------------------------------------------- figures
def _save_small(img_bgr, path):
	h, w = img_bgr.shape[:2]
	s = min(1.0, FIG_MAX / float(max(h, w)))
	im = cv2.resize(img_bgr, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA) if s < 1 else img_bgr
	q = FIG_QUALITY
	while True:
		ok, buf = cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, q])
		if len(buf) <= FIG_BYTES or q <= 40:
			break
		q -= 8
	buf.tofile(path)


def _text(img, txt, org, scale, colour=(255, 255, 255), th=2):
	cv2.putText(img, txt, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), th + 4, cv2.LINE_AA)
	cv2.putText(img, txt, org, cv2.FONT_HERSHEY_SIMPLEX, scale, colour, th, cv2.LINE_AA)


_DEC_COLOUR = {"alta": (60, 200, 60), "ambigua": (0, 160, 255), "duplicada": (160, 160, 160)}


def overlay_page(res, path_big, path_small):
	"""Scan with each piece: number + (l,c) if its component is 'alta', else comp:(r,c); bad internal sides red."""
	img = cv2.cvtColor(read_rgb(res.path), cv2.COLOR_RGB2BGR)
	mm = res.mm_per_px
	for k, p in enumerate(res.pieces):
		comp = res.comp_of(k)
		dec = comp.decision if comp is not None else "-"
		col = _DEC_COLOUR.get(dec, (120, 120, 120)) if not p.excluded else (255, 0, 255)
		cv2.polylines(img, [np.round(p.contour).astype(np.int32).reshape(-1, 1, 2)], True, col, 5, cv2.LINE_AA)
		if p.shape is None:
			continue
		ctr = np.asarray(p.contour, float).mean(0)
		if comp is not None and comp.placements and dec == "alta":
			l, c = comp.best["cells"][k]
			lab2 = f"({l},{c})"
		elif comp is not None and p.rc is not None:
			lab2 = f"c{comp.id}:{p.rc[0]},{p.rc[1]}"
		else:
			lab2 = p.excluded or "-"
		_text(img, str(p.n), (int(ctr[0] - 40), int(ctr[1] - 10)), 2.0, (255, 255, 255), 4)
		_text(img, lab2, (int(ctr[0] - 95), int(ctr[1] + 55)), 1.3, (255, 255, 0) if dec == "alta" else (255, 255, 255), 3)
	# internal sides that do not mate (adjacent in the local grid, incompatible sides)
	for comp in res.components:
		cell_of = {v: k for k, v in comp.rc.items()}
		for k, (r, c) in comp.rc.items():
			for d, (dr, dc), opp in (("E", (0, 1), "W"), ("S", (1, 0), "N")):
				j = cell_of.get((r + dr, c + dc))
				if j is None:
					continue
				pi, pj = res.pieces[k], res.pieces[j]
				if not (pi.dirs_ok and pj.dirs_ok):
					continue
				sc = legacy.side_compat(pi.shape.sides[pi.dirs[d]], pj.shape.sides[pj.dirs[opp]])
				if sc["ok"]:
					continue
				for pp, dd in ((pi, d), (pj, opp)):
					sd = pp.shape.sides[pp.dirs[dd]]
					a, b = (sd.p0_mm / mm).astype(int), (sd.p1_mm / mm).astype(int)
					cv2.line(img, tuple(int(v) for v in a), tuple(int(v) for v in b), (0, 0, 255), 12, cv2.LINE_AA)
	n_alta = sum(1 for c in res.components if c.decision == "alta")
	_text(img, f"{res.name}: {len(res.pieces)} pecas, {len(res.components)} comp., {n_alta} alta", (30, 70), 1.6, (255, 255, 255), 3)
	_text(img, "verde = alta (l,c); laranja = ambigua comp:r,c; cinza = duplicada; vermelho = lados internos incompativeis",
		  (30, 130), 1.1, (255, 255, 255), 3)
	cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tofile(path_big)
	_save_small(img, path_small)


def zone_figure(res, art, profile, path_big, path_small, scale=2):
	"""Art (cropped to the puzzle) with the footprint of every component: chosen placement solid, top-3 faint."""
	rgb = art.rgb
	img = cv2.cvtColor(cv2.resize(rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC), cv2.COLOR_RGB2BGR)
	img = (0.75 * img + 0.25 * 255).astype(np.uint8)
	cw, ch = art.cell_px[0] * scale, art.cell_px[1] * scale

	def rect(l, c, col, th):
		x0, y0 = int((c - 1) * cw), int((l - 1) * ch)
		cv2.rectangle(img, (x0 + 1, y0 + 1), (int(x0 + cw) - 1, int(y0 + ch) - 1), col, th)

	for comp in res.components:
		if not comp.placements:
			continue
		col = _DEC_COLOUR.get(comp.decision, (120, 120, 120))
		alts, seen = [], [comp.best]
		for p in comp.placements[1:]:
			if p["mirror"] or not np.isfinite(p["score"]) or any(legacy._placement_dist(p, q) < legacy.DISTINCT_CELLS for q in seen):
				continue
			seen.append(p)
			alts.append(p)
			if len(alts) == 2:
				break
		if comp.decision != "alta":
			for p in alts:
				for (l, c) in p["cells"].values():
					rect(l, c, (200, 200, 255), 1)
		for (l, c) in comp.best["cells"].values():
			rect(l, c, col, 3)
		ls = [v[0] for v in comp.best["cells"].values()]
		cs = [v[1] for v in comp.best["cells"].values()]
		_text(img, f"c{comp.id}", (int((min(cs) - 1) * cw), int((min(ls) - 1) * ch) + 25), 0.7, col, 2)
	_text(img, f"{res.name}: verde = alta, laranja = ambigua (top-1), lilas = alternativas 2-3", (10, img.shape[0] - 15),
		  0.9, (255, 255, 255), 2)
	cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tofile(path_big)
	_save_small(img, path_small)


def board_figure(results, prior_raw, art, profile, path_small, scale=2):
	"""Whole board: cells of 'alta' montado units (green), 'ambigua' top-1 (orange), M14 full cells without alta (red dot)."""
	img = cv2.cvtColor(cv2.resize(art.rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC), cv2.COLOR_RGB2BGR)
	img = (0.6 * img + 0.4 * 255).astype(np.uint8)
	cw, ch = art.cell_px[0] * scale, art.cell_px[1] * scale
	cov = set()
	for r in results:
		if r.kind != "montado":
			continue
		for c in r.components:
			if not c.placements or c.decision == "duplicada":
				continue
			col = _DEC_COLOUR[c.decision]
			for (l, cc) in c.best["cells"].values():
				x0, y0 = int((cc - 1) * cw), int((l - 1) * ch)
				cv2.rectangle(img, (x0 + 2, y0 + 2), (int(x0 + cw) - 2, int(y0 + ch) - 2), col, -1 if c.decision == "alta" else 3)
				if c.decision == "alta":
					cov.add((l, cc))
	for l in range(1, profile.rows + 1):
		for c in range(1, profile.cols + 1):
			if prior_raw[l - 1, c - 1] == 1 and (l, c) not in cov:
				cv2.circle(img, (int((c - 0.5) * cw), int((l - 0.5) * ch)), 6, (0, 0, 255), -1)
			if prior_raw[l - 1, c - 1] == 0 and (l, c) in cov:
				cv2.circle(img, (int((c - 0.5) * cw), int((l - 0.5) * ch)), 6, (255, 0, 255), -1)
	_text(img, "verde = alta; laranja = ambigua (top-1); ponto vermelho = cheia no M14 sem peca 'alta'; magenta = alta numa celula vazia no M14",
		  (10, img.shape[0] - 15), 0.75, (255, 255, 255), 2)
	_save_small(img, path_small)


def blocos_figure(res, path_big, path_small):
	"""Blocos page: components (side edges) in distinct colours, local (r,c), proximity groups listed in the title."""
	img = cv2.cvtColor(read_rgb(res.path), cv2.COLOR_RGB2BGR)
	rng = np.random.default_rng(3)
	cols = {c.id: tuple(int(v) for v in rng.integers(40, 255, 3)) for c in res.components}
	for k, p in enumerate(res.pieces):
		comp = res.comp_of(k)
		col = cols.get(comp.id, (128, 128, 128)) if comp is not None else (128, 128, 128)
		cv2.polylines(img, [np.round(p.contour).astype(np.int32).reshape(-1, 1, 2)], True, col, 8, cv2.LINE_AA)
		ctr = np.asarray(p.contour, float).mean(0)
		_text(img, str(p.n), (int(ctr[0] - 40), int(ctr[1] - 10)), 2.0, (255, 255, 255), 4)
		if comp is not None and p.rc is not None:
			_text(img, f"g{comp.id}:{p.rc[0]},{p.rc[1]}", (int(ctr[0] - 95), int(ctr[1] + 55)), 1.3, col, 3)
	for comp in res.components:
		for e in comp.edges:
			a = np.asarray(res.pieces[e["i"]].contour, float).mean(0)
			b = np.asarray(res.pieces[e["j"]].contour, float).mean(0)
			cv2.line(img, tuple(int(v) for v in a), tuple(int(v) for v in b), cols[comp.id], 6, cv2.LINE_AA)
	multi = sum(1 for c in res.components if len(c.members) > 1)
	_text(img, f"{res.name}: {len(res.pieces)} pecas, {multi} grupos com >= 2 pecas pelos lados (linhas = encaixes aceites); "
			   + "; ".join(res.notes).replace("≤", "<="), (30, 70), 1.0, (255, 255, 255), 3)
	cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tofile(path_big)
	_save_small(img, path_small)


# ---------------------------------------------------------------- JSON
def _jsonable(o):
	if isinstance(o, dict):
		return {str(k): _jsonable(v) for k, v in o.items()}
	if isinstance(o, (list, tuple)):
		return [_jsonable(v) for v in o]
	if isinstance(o, (np.integer,)):
		return int(o)
	if isinstance(o, (np.floating, float)):
		return None if not np.isfinite(o) else round(float(o), 4)
	if isinstance(o, np.bool_):
		return bool(o)
	return o


def page_json(res):
	comps = []
	for c in res.components:
		alts, seen = [], []
		for p in c.placements:
			if p["mirror"] or not np.isfinite(p["score"]) or any(legacy._placement_dist(p, q) < legacy.DISTINCT_CELLS for q in seen):
				continue
			seen.append(p)
			alts.append({"cell0": p["cell0"], "rot": p["rot"], "score": p["score"], "energia": p.get("adj"),
						 "gemeas_ok": p.get("twin_sat"), "gemeas_violadas": p.get("twin_viol"), "sobreposicao": p.get("overlap"),
						 "origem": p["origin"]})
			if len(alts) == 3:
				break
		comps.append({"id": c.id, "n": len(c.members), "decisao": c.decision, "margem": c.margin, "ganho": c.energy_gap,
					  "espelho": c.mirror_ratio, "razoes": c.reasons, "perguntas": c.questions, "gt": getattr(c, "gt", None),
					  "top3": alts, "pecas": [{"n": res.pieces[k].n, "rc": c.rc[k],
											   "celula": c.best["cells"][k] if c.placements else None} for k in c.members]})
	return {"pagina": res.name, "tipo": res.kind, "n_objetos": res.n_segmented, "n_pecas": len(res.pieces),
			"readme": README_COUNTS.get(res.name), "rotacao_pagina_deg": res.angle_deg,
			"rejeitados": res.rejected, "objetos_duplos": res.double, "notas": res.notes,
			"lados_F": _f_counts(res), "componentes": comps}


def _f_counts(res):
	out = {}
	for p in res.pieces:
		if p.dirs_ok:
			k = "".join(p.flat_dirs) or "-"
			out[k] = out.get(k, 0) + 1
		else:
			out["?"] = out.get("?", 0) + 1
	return out


# ---------------------------------------------------------------- main
def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("--pages", nargs="*", default=None)
	ap.add_argument("--no-figs", action="store_true")
	a = ap.parse_args()
	t0 = time.time()
	profile = PuzzleProfile.load(PROFILE)
	art = CellArt.load(profile, REPO)
	prior = legacy.load_prior(OCC, profile, OCC_FIX)
	pages = a.pages or PAGES
	results = analyse_all(profile, art, prior, pages)
	gts = gt_items(profile)
	_, rows0 = gt_eval(results, gts, profile)
	alta0 = {(r.name, c.id) for r in results for c in r.components if c.decision == "alta"}
	solved = legacy.solve_pages(results, profile, art, prior, log=print)
	matches, rows = gt_eval(results, gts, profile)
	vetoed = gt_veto(results, rows)
	summary(results, rows0, rows, matches, solved, profile)
	stats = side_stats(results, profile, gts)
	m14 = m14_compare(results, prior, profile)
	pc = pair_check(results, solved, profile)
	gt_d = {k: _pct([m["d_mm"] for m in matches if m["kind"] == k]) for k in ("mesma", "gemea")}
	gt_dE = {k: _pct([m["dE"] for m in matches if m["kind"] == k]) for k in ("mesma", "gemea")}
	pairs_by_pages = {}
	for x, y, d, phi, m in solved["pairs"]:
		key = " ↔ ".join(sorted({results[x[0]].name, results[y[0]].name}))
		pairs_by_pages[key] = pairs_by_pages.get(key, 0) + 1
	out = {"gerado": time.strftime("%Y-%m-%d %H:%M"), "perfil": os.path.relpath(PROFILE, REPO).replace("\\", "/"),
		   "constantes": {k: getattr(legacy, k) for k in ("SIDE_TOL_DEG", "SIDE_RMS_MAX", "SIDE_DL_MAX", "NEIGH_ALONG",
															 "NEIGH_ACROSS", "TOPK", "N_IMPLY", "DISTINCT_CELLS", "W_TWIN",
															 "W_OVERLAP", "W_PRIOR", "TWIN_GAP_MIN", "MIRROR_WIN", "MIN_LINK",
															 "DUP_FRAC", "SAME_PIECE_DE", "GROUP_GAP_MM")},
		   "paginas": [page_json(r) for r in results],
		   "gemeas": {"n_pares": len(solved["pairs"]), "por_paginas": pairs_by_pages, "verificacao": pc,
					  "duplicadas": solved["duplicates"], "iteracoes": solved["iterations"], "movimentos": solved["moves"]},
		   "gt": {"antes": rows0, "depois": rows, "d_mm": gt_d, "dE": gt_dE, "vetadas": vetoed,
				  "alta_so_imagem": sorted(alta0)},
		   "lados": stats, "m14": m14}
	os.makedirs(OUT_DOC, exist_ok=True)
	with open(os.path.join(OUT_DOC, "legado_resultados.json"), "w", encoding="utf-8") as f:
		json.dump(_jsonable(out), f, ensure_ascii=False, indent=1)
	print("lados:", json.dumps(_jsonable(stats), ensure_ascii=False))
	print("GT d:", gt_d, "dE:", gt_dE)
	print(f"M14: {m14['n_scan_alta']} células 'alta'; {len(m14['scan_not_full'])} com peça mas não cheias no M14; "
		  f"{m14['n_m14_full_without_alta']} cheias no M14 sem peça 'alta'")
	print("vetadas pela GT:", vetoed)
	if not a.no_figs:
		big = os.path.join(cache_dir(), "fig")
		os.makedirs(big, exist_ok=True)
		for r in results:
			if r.kind == "montado":
				overlay_page(r, os.path.join(big, f"{r.name}_overlay.jpg"), os.path.join(OUT_DOC, f"{r.name}_overlay.jpg"))
				zone_figure(r, art, profile, os.path.join(big, f"{r.name}_zona.jpg"), os.path.join(OUT_DOC, f"{r.name}_zona.jpg"))
			else:
				blocos_figure(r, os.path.join(big, f"{r.name}_grupos.jpg"), os.path.join(OUT_DOC, f"{r.name}_grupos.jpg"))
		board_figure(results, prior, art, profile, os.path.join(OUT_DOC, "tabuleiro_legado.jpg"))
	print(f"feito em {time.time() - t0:.0f} s")


if __name__ == "__main__":
	main()
