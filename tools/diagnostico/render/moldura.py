"""Lado F das peças de moldura contra a linha da borda do tabuleiro (RENDER.md §9). Só leitura do projeto.

Uso, da raiz (sempre numa CÓPIA de ``projects/alpes``; ``projects/alpes`` é recusado)::

    python tools/diagnostico/render/moldura.py --project <cópia> [--target grow|borda] [--relax MAX_MM,ITERS]
        [--fig-full <jpg fora do repo>] [--no-holes] [--no-fig] [--no-compare]

Pose = a da GUI (``render.register_piece(image=False)``, registada na hora). Para cada lado F de cada peça de moldura
colocada (cantos do puzzle: 2 F): reta ajustada aos 8-92 % do lado (como ``render.f_side_line``, aqui reimplementada
para a medição não depender do código medido), levada ao tabuleiro com a pose; ``d_mm`` = distância perpendicular
ASSINADA do ponto médio da reta à linha da borda (N y=0, W x=0, S y=rows*h, E x=cols*w), positiva = para fora do
tabuleiro; ``d_grow_mm`` = ``d_mm - grow`` (alvo a ``grow`` = ``calibration.celula_silhueta.offset_mm`` para fora, a
convenção dos alvos de Kabsch e de ``seam_gaps``). Resumo por borda N/E/S/W (peças com 1 F) e cantos (2 F).

Com ``render.F_TRANSLATION`` presente e sem ``--no-compare``: mede a pose da GUI com o interruptor desligado e ligado
no mesmo processo e aplica a porta (RENDER.md §9): (1) nenhuma junta piora > 0,2 mm; (2) mediana de |folga| não sobe;
(3) buracos <= 67 / 9; (4) |d_F - alvo| > 0,2 mm passa a 0 nos lados F usados. Figura
``moldura_antes_depois.jpg`` (<= 300 KB): P0240, P0590 e 20 peças de moldura (os 4 cantos + 4 por borda, semente fixa),
vista 3 x 3 a 300 dpi com margem fora do tabuleiro, linha da borda (amarelo) e alvo (ciano); antes | depois.
Saída: ``docs/diagnostico/render/moldura.json``.
"""

import argparse
import collections
import json
import os
import sys
import time

import cv2
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools", "diagnostico", "reports"))
sys.path.insert(0, os.path.join(REPO, "tools", "diagnostico", "render"))

from src import render as R  # noqa: E402
from src.state import Project  # noqa: E402

OUT_DIR = os.path.join(REPO, "docs", "diagnostico", "render")
SEED = 20261107
REPORTED = ["P0240", "P0590"]
F_SPAN = (0.08, 0.92)


# ---------------------------------------------------------------- medição (pura)
def f_line_scan(sh, i):
	"""Reta do lado ``i`` (8-92 % da corda) no referencial do scan: ``(ponto médio, direção unitária, rms_mm)``."""
	a, b = int(sh.corners[i]), int(sh.corners[(i + 1) % 4])
	seg = sh.c[a:b + 1] if b > a else np.vstack([sh.c[a:], sh.c[:b + 1]])
	p0, p1 = seg[0], seg[-1]
	L = float(np.linalg.norm(p1 - p0))
	u = (p1 - p0) / L
	v = np.array([-u[1], u[0]])
	x, y = (seg - p0) @ u, (seg - p0) @ v
	sel = (x > F_SPAN[0] * L) & (x < F_SPAN[1] * L)
	if sel.sum() < 6:
		return None
	c1, c0 = np.polyfit(x[sel], y[sel], 1)
	rms = float(np.sqrt(np.mean((y[sel] - (c1 * x[sel] + c0)) ** 2)))
	xm = 0.5 * L
	pm = p0 + xm * u + (c1 * xm + c0) * v
	d = u + c1 * v
	return pm, d / np.linalg.norm(d), rms


def border_frame(prof):
	w, h = float(prof.cell_mm["w"]), float(prof.cell_mm["h"])
	W, H = prof.cols * w, prof.rows * h
	# direção -> (normal para fora, posição da linha ao longo da normal)
	return {"N": (np.array([0.0, -1.0]), 0.0), "S": (np.array([0.0, 1.0]), H),
			"W": (np.array([-1.0, 0.0]), 0.0), "E": (np.array([1.0, 0.0]), W)}


def f_offsets(pr, PL, shapes, grow):
	"""Por lado F de cada peça de moldura com cantos: ``[{pid, cell, i, dir, group, d_mm, d_grow_mm, rms_mm, tilt_deg,
	used, rotation}]``; e a lista das peças de moldura sem medição (sem 4 cantos / sem k)."""
	prof = pr.profile
	bf = border_frame(prof)
	rows, skipped = [], []
	for pid, e in PL.items():
		cell = tuple(e["cell"])
		flat = prof.flat_directions(*cell)
		if not flat:
			continue
		sh = shapes.get(pid)
		k = (e.get("corner") or {}).get("k")
		if sh is None or not sh.ok or len(sh.corners) != 4 or k is None:
			skipped.append((pid, list(cell), e.get("method")))
			continue
		A = R.placement_matrix(e, prof)
		group = "canto" if len(flat) == 2 else next(iter(flat))
		used = {s[0]: s[4] for s in ((e.get("f_rotation") or {}).get("per_side") or [])}
		for i, s in enumerate(sh.sides):
			if s.kind != "F":
				continue
			dr = R.DIRS[(i + int(k)) % 4]
			fl = f_line_scan(sh, i)
			if fl is None or dr not in bf:
				continue
			pm, dvec, rms = fl
			q = R._apply(A, pm)[0]
			db = A[:, :2] @ dvec
			n, pos = bf[dr]
			d = float(q @ n - pos)
			tang = np.array([-n[1], n[0]])
			tilt = float(np.degrees(np.arctan2(db @ n, abs(db @ tang))))
			rows.append(dict(pid=pid, cell=list(cell), i=i, dir=dr, group=group, in_flat=dr in flat, d_mm=d, d_grow_mm=d - grow,
							 rms_mm=rms, tilt_deg=tilt, used=bool(used.get(i, False)), rotation=e.get("rotation"),
							 method=e.get("method")))
	return rows, skipped


def stats(vals):
	a = np.asarray(vals, float)
	if len(a) == 0:
		return None
	aa = np.abs(a)
	return dict(n=int(len(a)), med=float(np.median(a)), absmed=float(np.median(aa)), p95=float(np.percentile(aa, 95)),
				max=float(aa.max()), signed_min=float(a.min()), signed_max=float(a.max()),
				gt02=int((aa > 0.2).sum()), gt05=int((aa > 0.5).sum()))


def summarize(rows):
	out = {}
	for key in ("d_mm", "d_grow_mm"):
		g = {"todos": stats([r[key] for r in rows])}
		for grp in ("N", "E", "S", "W", "canto"):
			g[grp] = stats([r[key] for r in rows if r["group"] == grp])
		g["usados"] = stats([r[key] for r in rows if r["used"]])
		g["nao_usados"] = stats([r[key] for r in rows if not r["used"]])
		out[key] = g
	return out


def print_summary(name, sm):
	for key, lab in (("d_mm", "d (à borda)"), ("d_grow_mm", "d - grow (ao alvo)")):
		print(f"[{name}] {lab}:")
		for grp, s in sm[key].items():
			if s is None:
				continue
			print(f"   {grp:10s} n={s['n']:3d} mediana {s['med']:+.3f} |med| {s['absmed']:.3f} p95 {s['p95']:.3f} máx {s['max']:.3f} "
				  f"[{s['signed_min']:+.3f}, {s['signed_max']:+.3f}] >0,2: {s['gt02']} >0,5: {s['gt05']}")


# ---------------------------------------------------------------- poses
def gui_poses(pr, ids, ft=None):
	if ft is not None:
		R.F_TRANSLATION = bool(ft)
	out = {}
	for pid in ids:
		r = R.register_piece(pr, pid, art=None, image=False)
		if "error" not in r:
			out[pid] = r
	return out


# ---------------------------------------------------------------- figura
def border_view(pr, PL, pid, col, grow, margin_mm=2.5, crop_cell=None):
	"""Vista 3 x 3 a 300 dpi com margem fora do tabuleiro: borda (amarelo), alvo ``grow`` para fora (ciano), contorno."""
	import triagem_r3 as TR
	prof = pr.profile
	l, c = pr.piece(pid).celula
	reg = (max(1, l - 1), max(1, c - 1), min(prof.rows, l + 1), min(prof.cols, c + 1))
	ppc = float(prof.cell_mm["w"]) / (25.4 / 300.0)
	ppm = ppc / float(prof.cell_mm["w"])
	img = R.compose_board(pr, ppc, region=reg, layers=("art", "pieces", "grid"), placements=PL)
	m = int(round(margin_mm * ppm))
	flat = prof.flat_directions(l, c)
	top, bot = (m if "N" in flat else 0), (m if "S" in flat else 0)
	lef, rig = (m if "W" in flat else 0), (m if "E" in flat else 0)
	img = cv2.copyMakeBorder(img, top, bot, lef, rig, cv2.BORDER_CONSTANT, value=(90, 90, 90))
	w, h = float(prof.cell_mm["w"]), float(prof.cell_mm["h"])
	ox, oy = (reg[1] - 1) * w * ppm - lef, (reg[0] - 1) * h * ppm - top

	def P(x, y):
		return int(round(x * ppm - ox)), int(round(y * ppm - oy))

	Wb, Hb = prof.cols * w, prof.rows * h
	x0, y0, x1, y1 = (reg[1] - 1) * w - margin_mm, (reg[0] - 1) * h - margin_mm, reg[3] * w + margin_mm, reg[2] * h + margin_mm
	for d in flat:
		for off, cc in ((0.0, (0, 255, 255)), (grow, (255, 255, 0))):
			if d == "N":
				a, b = P(x0, -off), P(x1, -off)
			elif d == "S":
				a, b = P(x0, Hb + off), P(x1, Hb + off)
			elif d == "W":
				a, b = P(-off, y0), P(-off, y1)
			else:
				a, b = P(Wb + off, y0), P(Wb + off, y1)
			cv2.line(img, a, b, cc, 1, cv2.LINE_AA)
	sh = pr.shape(pid)
	pts = R._apply(R.placement_matrix(PL[pid], prof), sh.c) * ppm - [ox, oy]
	cv2.polylines(img, [np.round(pts).astype(np.int32).reshape(-1, 1, 2)], True, col, 1, cv2.LINE_AA)
	if crop_cell is not None:
		# a célula da peça +/- crop_cell célula (as juntas com as vizinhas), mais a margem fora do tabuleiro
		ax0, ay0 = P((c - 1 - crop_cell) * w, (l - 1 - crop_cell) * h)
		ax1, ay1 = P((c + crop_cell) * w, (l + crop_cell) * h)
		ax0, ay0 = max(0, ax0 - (lef if "W" in flat else 0)), max(0, ay0 - (top if "N" in flat else 0))
		img = img[ay0:min(img.shape[0], ay1 + (bot if "S" in flat else 0)), ax0:min(img.shape[1], ax1 + (rig if "E" in flat else 0))]
	return img


def sample_pieces(PL, prof, seed=SEED):
	rng = np.random.default_rng(seed)
	by = collections.defaultdict(list)
	for pid, e in sorted(PL.items()):
		if pid in REPORTED or not e.get("corner"):
			continue
		fl = prof.flat_directions(*e["cell"])
		if len(fl) == 1:
			by[next(iter(fl))].append(pid)
		elif len(fl) == 2:
			by["canto"].append(pid)
	# os cantos do puzzle (>= 2; aqui os 4) + 4 não-canto por borda = 20 peças (cada borda com 4 + 2 cantos)
	out = [str(x) for x in rng.choice(by["canto"], min(4, len(by["canto"])), replace=False)]
	for d in ("N", "E", "S", "W"):
		out += [str(x) for x in rng.choice(by[d], min(4, len(by[d])), replace=False)]
	return out


def figure(pr, PLb, PLa, pids, rows_b, rows_a, grow, path, full_path=None, max_bytes=300_000):
	import triagem_r3 as TR
	db = {(r["pid"], r["dir"]): r for r in rows_b}
	da = {(r["pid"], r["dir"]): r for r in rows_a}
	tiles = []
	for pid in pids:
		l, c = pr.piece(pid).celula
		pair = []
		for name, PL, col, dd in (("antes", PLb, (0, 0, 255), db), ("depois", PLa, (0, 200, 0), da)):
			img = border_view(pr, PL, pid, col, grow, crop_cell=0.35)
			fs = " ".join(f"{d}{dd[(pid, d)]['d_mm']:+.2f}" for d in "NESW" if (pid, d) in dd)
			pair.append(TR.label(img, f"{pid} ({l},{c}) {name}: d_F {fs}", scale=0.42))
		tiles.append(TR.hcat(pair))
	# duas colunas de pares para caber
	half = (len(tiles) + 1) // 2
	left, right = tiles[:half], tiles[half:]
	colL, colR = TR.grid(left), TR.grid(right) if right else None
	big = TR.hcat([colL, colR], pad=14) if colR is not None else colL
	if full_path:
		cv2.imwrite(full_path, big, [cv2.IMWRITE_JPEG_QUALITY, 92])
	q = 85
	while True:
		ok, buf = cv2.imencode(".jpg", big, [cv2.IMWRITE_JPEG_QUALITY, q])
		if len(buf) <= max_bytes:
			break
		if q > 60:
			q -= 5
		else:
			big = cv2.resize(big, (int(big.shape[1] * 0.9), int(big.shape[0] * 0.9)), interpolation=cv2.INTER_AREA)
	with open(path, "wb") as f:
		f.write(buf.tobytes())
	return {"bytes": len(buf), "quality": q, "size": [int(big.shape[1]), int(big.shape[0])]}


def _round(o, nd=4):
	if isinstance(o, float):
		return round(o, nd)
	if isinstance(o, dict):
		return {k: _round(v, nd) for k, v in o.items()}
	if isinstance(o, (list, tuple)):
		return [_round(v, nd) for v in o]
	if isinstance(o, (np.floating,)):
		return round(float(o), nd)
	return o


# ---------------------------------------------------------------- porta
def piece_seams(seams, pids):
	out = collections.defaultdict(list)
	for s in seams:
		for p in (s["a"], s["b"]):
			if p in pids:
				out[p].append(s)
	return out


def compare_block(pr, name, PLb, PLa, rows_b, shapes, grow, do_holes):
	"""Porta antes (``PLb``) -> depois (``PLa``): lados F, juntas, buracos, tabela por peça de moldura."""
	import triagem_r3 as TR
	rows_a, _ = f_offsets(pr, PLa, shapes, grow)
	out = {"summary": summarize(rows_a), "rows": rows_a}
	print_summary(name, out["summary"])
	key = "d_grow_mm" if getattr(R, "F_TARGET_GROW", True) else "d_mm"
	out["target_key"] = key
	sb, sa = TR.seam_list(pr, PLb, shapes), TR.seam_list(pr, PLa, shapes)
	cmpd = TR.compare_seams(sb, sa)
	kb = {(s["a"], s["b"]): s for s in sb}
	allc = sorted(({"a": s["a"], "b": s["b"], "cells": s["cells"], "dir": s["dir"], "before": kb[(s["a"], s["b"])]["gap_mm"],
					"after": s["gap_mm"], "worse": abs(s["gap_mm"]) - abs(kb[(s["a"], s["b"])]["gap_mm"])}
				   for s in sa if (s["a"], s["b"]) in kb), key=lambda x: -x["worse"])
	out["seams_before"], out["seams_after"] = TR.seam_summary(sb), TR.seam_summary(sa)
	out["seams_cmp"], out["seams_most_worse"] = cmpd, [w for w in allc if w["worse"] > 0.2] or allc[:5]
	out["seams_most_better"] = sorted(allc, key=lambda x: x["worse"])[:8]
	print(f"[{name}] juntas: mediana |folga| {out['seams_before']['absgap_med']:.4f} -> {out['seams_after']['absgap_med']:.4f}; "
		  f"p95 {out['seams_before']['absgap_p95']:.3f} -> {out['seams_after']['absgap_p95']:.3f}; >0,8: "
		  f"{out['seams_before']['gt08']} -> {out['seams_after']['gt08']}; pioram >0,2: {cmpd['n_worse_02']} "
		  f"(máx {cmpd['max_worse']:+.3f}); melhoram >0,2: {cmpd['n_better_02']}")
	for w in allc[:8]:
		print(f"   pior: {w['a']}-{w['b']} {w['cells']} {w['dir']} {w['before']:+.3f} -> {w['after']:+.3f} ({w['worse']:+.3f})")
	hb = ha = None
	if do_holes:
		import verde_tabuleiro as VT
		t = time.time()
		hb, ha = VT.holes(pr, PLb, True), VT.holes(pr, PLa, True)
		out["holes_before"], out["holes_after"] = hb, ha
		print(f"[{name}] buracos {hb} -> {ha} ({time.time() - t:.0f} s)")
	ua = [r for r in rows_a if r["used"]]
	out["gate"] = {
		"1_no_seam_worse_0.2": cmpd["n_worse_02"] == 0,
		"2_median_not_up": out["seams_after"]["absgap_med"] <= out["seams_before"]["absgap_med"] + 1e-9,
		"3_holes_le_67_9": None if ha is None else (ha["gt5"] <= 67 and ha["gt10"] <= 9),
		"4_used_f_off_target_gt0.2_zero": sum(1 for r in ua if abs(r[key]) > 0.2) == 0,
		"n_used_f_off_target_gt0.2": sum(1 for r in ua if abs(r[key]) > 0.2),
		"n_all_f_off_target_gt0.2": sum(1 for r in rows_a if abs(r[key]) > 0.2),
	}
	print(f"[{name}] porta:", out["gate"])
	bp = {r["pid"] for r in rows_a}
	psa = piece_seams(sa, bp)
	db = collections.defaultdict(list)
	for r in rows_b:
		db[r["pid"]].append(r)
	tab = []
	for pid in sorted(bp):
		ra = [r for r in rows_a if r["pid"] == pid]
		sj = [dict(other=s["b"] if s["a"] == pid else s["a"], dir=s["dir"],
				   before=kb[(s["a"], s["b"])]["gap_mm"] if (s["a"], s["b"]) in kb else None, after=s["gap_mm"]) for s in psa.get(pid, [])]
		tab.append(dict(pid=pid, cell=ra[0]["cell"], f=[(r["dir"], round(b["d_mm"], 3), round(r["d_mm"], 3)) for r, b in zip(ra, db[pid])],
						shift=[round(PLa[pid]["dx_mm"] - PLb[pid]["dx_mm"], 3), round(PLa[pid]["dy_mm"] - PLb[pid]["dy_mm"], 3)],
						seams=sj))
	out["per_piece"] = tab
	return out


def main(argv=None):
	ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	ap.add_argument("--project", required=True)
	ap.add_argument("--no-holes", action="store_true")
	ap.add_argument("--no-fig", action="store_true")
	ap.add_argument("--no-compare", action="store_true", help="só a pose atual (sem desligar/ligar F_TRANSLATION)")
	ap.add_argument("--out", default=os.path.join(OUT_DIR, "moldura.json"))
	ap.add_argument("--fig-full", default=None, help="cópia da figura em resolução total (fora do repo)")
	ap.add_argument("--relax", default=None, help="MAX_MM,ITERS: mede também F_TRANSLATION + render.relax (bloqueio normal ao F)")
	ap.add_argument("--target", choices=("grow", "borda"), default=None,
					help="alvo de F_TRANSLATION nesta medição (render.F_TARGET_GROW); omissão: o do módulo")
	args = ap.parse_args(argv)
	if args.target is not None:
		R.F_TARGET_GROW = args.target == "grow"
	if os.path.normcase(os.path.abspath(args.project)) == os.path.normcase(os.path.join(REPO, "projects", "alpes")):
		print("usar uma cópia de projects/alpes (--project)")
		return 2
	import triagem_r3 as TR
	t0 = time.time()
	pr = Project.open(args.project)
	prof = pr.profile
	grow = R._grow(prof)
	ids = R.placed_ids(pr)
	shapes = {pid: pr.shape(pid) for pid in ids}
	has_ft = hasattr(R, "F_TRANSLATION")
	FT0 = getattr(R, "F_TRANSLATION", None)
	res = {"log_len": R._log_len(pr), "n_placed": len(ids), "grow_mm": grow, "F_ROTATION": R.F_ROTATION,
		   "has_F_TRANSLATION": has_ft, "F_TARGET_GROW": getattr(R, "F_TARGET_GROW", None), "border_mm": {"W": prof.cols * float(prof.cell_mm["w"]), "H": prof.rows * float(prof.cell_mm["h"])}}
	compare = has_ft and not args.no_compare
	PLb = gui_poses(pr, ids, False if compare else None)
	rows_b, skipped = f_offsets(pr, PLb, shapes, grow)
	res["skipped"] = skipped
	res["n_border_pieces"] = len({r["pid"] for r in rows_b})
	res["n_f_sides"] = len(rows_b)
	res["before"] = summarize(rows_b)
	print(f"peças de moldura medidas: {res['n_border_pieces']} ({len(rows_b)} lados F); sem medição: {skipped}")
	print_summary("antes" if compare else "atual", res["before"])
	res["rows_before"] = rows_b
	worst = sorted(rows_b, key=lambda r: -abs(r["d_mm"]))[:15]
	for r in worst:
		print(f"   {r['pid']} {tuple(r['cell'])} {r['dir']} d {r['d_mm']:+.3f} d-grow {r['d_grow_mm']:+.3f} rms {r['rms_mm']:.3f} "
			  f"incl {r['tilt_deg']:+.2f}° rot {r['rotation']} usado {r['used']}")
	if compare:
		PLa = gui_poses(pr, ids, True)
		res["after"] = compare_block(pr, "depois", PLb, PLa, rows_b, shapes, grow, not args.no_holes)
		if args.relax:
			mx, it = (float(v) for v in args.relax.split(","))
			t = time.time()
			PLr = R.relax(pr, PLa, max_mm=mx, iters=int(it))
			res["after_relax"] = compare_block(pr, f"depois+relax({mx:g},{int(it)})", PLb, PLr, rows_b, shapes, grow, not args.no_holes)
			res["after_relax"]["relax"] = {"max_mm": mx, "iters": int(it), "s": time.time() - t}
		if not args.no_fig:
			pids = REPORTED + sample_pieces(PLa, prof)
			res["fig_pieces"] = pids
			res["fig_bytes"] = figure(pr, PLb, PLa, pids, rows_b, res["after"]["rows"], grow, os.path.join(OUT_DIR, "moldura_antes_depois.jpg"),
								  full_path=args.fig_full)
		R.F_TRANSLATION = FT0
	res["total_s"] = time.time() - t0
	with open(args.out, "w", encoding="utf-8") as f:
		json.dump(_round(res), f, ensure_ascii=False, indent=None, separators=(",", ":"), default=R._json_default)
	print(f"escrito {args.out} ({res['total_s']:.0f} s)")
	return 0


if __name__ == "__main__":
	sys.exit(main())
