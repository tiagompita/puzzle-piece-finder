"""Rotação das peças de moldura pela reta do lado F (RENDER.md §8): ``render.F_ROTATION`` desligado vs ligado.

Uso, da raiz (sempre numa CÓPIA de ``projects/alpes``)::

    python tools/diagnostico/render/pose_f.py --project <cópia> [--before-placements <outra cópia>] [--no-holes]
        [--no-register-all] [--no-fig]

Mede no mesmo processo a pose da GUI (``register_piece(image=False)``) com o interruptor desligado e ligado e,
se ``--before-placements`` for dado, também a pose com imagem: antes = ``render/placements.json`` dessa cópia, depois
= ``render.register_all(image=True, force=True)`` na cópia ``--project`` (escreve lá ``render/placements.json``).
Reutiliza ``tools/diagnostico/reports/triagem_r3.py`` (folga por junta igual a ``render.seam_gaps``, inclinação do
lado F) e ``verde_tabuleiro.holes`` (buracos a 120 px/célula, magenta, inset 0,4 mm).

Porta: (1) nenhuma junta ortogonal piora > 0,2 mm em |folga|; (2) a mediana de |folga| não sobe; (3) buracos
<= 67 / 9 células > 5 % / > 10 %; (4) lados F a > 3° da borda: 12 -> 0. Saída: ``docs/diagnostico/render/pose_f.json``
e ``pose_f_P0240_P0590.jpg`` (<= 300 KB).
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
import triagem_r3 as TR  # noqa: E402

OUT_DIR = os.path.join(REPO, "docs", "diagnostico", "render")
SEED = 20261107
LIST12 = ["P0655", "P0199", "P0240", "P0638", "P0590", "P0230", "P0661", "P0350", "P0636", "P0222", "P0223", "P0540"]
REPORTED = ["P0240", "P0590"]


def gui_poses(pr, ids, on):
	R.F_ROTATION = bool(on)
	out = {}
	for pid in ids:
		r = R.register_piece(pr, pid, art=None, image=False)
		if "error" not in r:
			out[pid] = r
	return out


def f_tilts(pr, PL, shapes):
	"""{pid: [(dir, tilt_line)]} dos lados F (reta 8-92 %) face à linha da borda, pose ``PL``."""
	out = {}
	for pid, e in PL.items():
		sh = shapes[pid]
		k = (e.get("corner") or {}).get("k")
		if sh is None or not sh.ok or k is None:
			continue
		st = TR.side_tilts(sh, float(e["theta_deg"]), int(k))
		ft = [(s["dir"], float(s["tilt_line"])) for s in st if s["kind"] == "F"]
		if ft:
			out[pid] = ft
	return out


def inner_tilt(sh, i, theta, k, q=30.0):
	"""Diagnóstico (fora do produto): inclinação face à borda da reta pelos pontos do lado F mais para dentro
	da peça (percentil ``q`` do desvio, 3 iterações), para lados cujo contorno não é reto (orla verde/sombra)."""
	seg = TR.side_seg(sh, i)
	p0, p1 = seg[0], seg[-1]
	L = float(np.linalg.norm(p1 - p0))
	u = (p1 - p0) / L
	v = np.array([-u[1], u[0]])
	ctr = sh.c[sh.corners].mean(0)
	sgn = 1.0 if (ctr - p0) @ v > 0 else -1.0                 # +: para dentro da peça
	x, y = (seg - p0) @ u, sgn * ((seg - p0) @ v)
	sel = (x > R.F_SPAN[0] * L) & (x < R.F_SPAN[1] * L)
	x, y = x[sel], y[sel]
	keep = np.ones(len(x), bool)
	for _ in range(3):
		b = np.polyfit(x[keep], y[keep], 1)
		r = y - np.polyval(b, x)
		keep = r >= np.percentile(r, 100 - q)
	b = np.polyfit(x[keep], y[keep], 1)
	ang = float(np.degrees(np.arctan2(u[1], u[0])) + np.degrees(np.arctan(sgn * b[0])))
	return TR.w90(ang + theta - 90 * ((i + k) % 4))


def excluded_sides(pr, PLb, PLa, shapes):
	"""Lados F com contorno não reto (RMS da reta > ``F_LINE_RMS_MAX``): ficam fora da rotação."""
	out = []
	for pid, e in PLb.items():
		sh = shapes[pid]
		k = (e.get("corner") or {}).get("k")
		if sh is None or not sh.ok or k is None:
			continue
		for i, s in enumerate(sh.sides):
			if s.kind != "F":
				continue
			fl = R.f_side_line(sh, i)
			if fl is None or fl[1] <= R.F_LINE_RMS_MAX:
				continue
			st = TR.side_tilts(sh, float(e["theta_deg"]), int(k))[i]
			out.append(dict(pid=pid, cell=list(pr.piece(pid).celula), scan=pr.piece(pid).scan_id, n=pr.piece(pid).n_no_lote,
							dir=st["dir"], rms_mm=fl[1], tilt_line=st["tilt_line"], tilt_chord=st["tilt_chord"],
							tilt_inner=inner_tilt(sh, i, float(e["theta_deg"]), int(k)),
							rotation_after=PLa[pid].get("rotation")))
	return sorted(out, key=lambda d: -d["rms_mm"])


def per_piece_seams(seams):
	bp = collections.defaultdict(list)
	for s in seams:
		bp[s["a"]].append(s)
		bp[s["b"]].append(s)
	return bp


def worse_list(A, B, thr=0.2):
	ka = {(s["a"], s["b"]): s for s in A}
	out = []
	for s in B:
		a = ka.get((s["a"], s["b"]))
		if a is None:
			continue
		dd = abs(s["gap_mm"]) - abs(a["gap_mm"])
		if dd > thr:
			out.append(dict(a=s["a"], b=s["b"], cells=s["cells"], dir=s["dir"], before=a["gap_mm"], after=s["gap_mm"],
							worse=dd, rel_before=a["rel_deg"], rel_after=s["rel_deg"]))
	return sorted(out, key=lambda x: -x["worse"])


def gate(pr, name, PLb, PLa, shapes, holes_b=None, holes_a=None):
	sb, sa = TR.seam_list(pr, PLb, shapes), TR.seam_list(pr, PLa, shapes)
	fb, fa = f_tilts(pr, PLb, shapes), f_tilts(pr, PLa, shapes)
	ftb = [(pid, d, t) for pid, L in fb.items() for d, t in L]
	fta = [(pid, d, t) for pid, L in fa.items() for d, t in L]
	g = dict(
		seams_before=TR.seam_summary(sb), seams_after=TR.seam_summary(sa), cmp=TR.compare_seams(sb, sa),
		worse=worse_list(sb, sa),
		f_sides=len(fta), f_gt3_before=sorted([(p, d, round(t, 2)) for p, d, t in ftb if abs(t) > 3], key=lambda x: -abs(x[2])),
		f_gt3_after=sorted([(p, d, round(t, 2)) for p, d, t in fta if abs(t) > 3], key=lambda x: -abs(x[2])),
		f_gt2_before=sum(1 for _, _, t in ftb if abs(t) > 2), f_gt2_after=sum(1 for _, _, t in fta if abs(t) > 2),
		f_med_before=float(np.median([abs(t) for _, _, t in ftb])), f_med_after=float(np.median([abs(t) for _, _, t in fta])),
		rotation=dict(collections.Counter(e.get("rotation", "?") for e in PLa.values())),
		methods_after=dict(collections.Counter(e["method"] for e in PLa.values())),
	)
	if holes_b is not None:
		g["holes_before"], g["holes_after"] = holes_b, holes_a
	g["gate"] = {
		"1_no_seam_worse_0.2": g["cmp"]["n_worse_02"] == 0,
		"2_median_not_up": g["seams_after"]["absgap_med"] <= g["seams_before"]["absgap_med"] + 1e-9,
		"3_holes_le_67_9": None if holes_a is None else (holes_a["gt5"] <= 67 and holes_a["gt10"] <= 9),
		"4_f_gt3_zero": len(g["f_gt3_after"]) == 0,
	}
	print(f"[{name}] juntas antes {g['seams_before']['absgap_med']:.3f} / depois {g['seams_after']['absgap_med']:.3f} mm "
		  f"(mediana |folga|); >0,8: {g['seams_before']['gt08']} -> {g['seams_after']['gt08']}; "
		  f"pioram >0,2: {g['cmp']['n_worse_02']} (máx {g['cmp']['max_worse']:.3f}), melhoram >0,2: {g['cmp']['n_better_02']}")
	print(f"[{name}] F >3°: {len(g['f_gt3_before'])} -> {len(g['f_gt3_after'])}; >2°: {g['f_gt2_before']} -> {g['f_gt2_after']}; "
		  f"mediana {g['f_med_before']:.2f} -> {g['f_med_after']:.2f}; rotação {g['rotation']}")
	for w in g["worse"]:
		print(f"   pior: {w['a']}-{w['b']} {w['cells']} {w['dir']} {w['before']:+.3f} -> {w['after']:+.3f} (+{w['worse']:.3f})")
	if holes_a is not None:
		print(f"[{name}] buracos {holes_b} -> {holes_a}")
	print(f"[{name}] porta {g['gate']}")
	return g, sb, sa, fb, fa


def piece_rows(pr, pids, PLb, PLa, sb, sa, fb, fa):
	bb, ba = per_piece_seams(sb), per_piece_seams(sa)
	kb = {(s["a"], s["b"]): s for s in sb}
	rows = []
	for pid in pids:
		if pid not in PLa:
			continue
		e = PLa[pid]
		sj = []
		for s in ba.get(pid, []):
			o = s["b"] if s["a"] == pid else s["a"]
			b = kb.get((s["a"], s["b"]))
			sj.append(dict(other=o, dir=s["dir"], cells=s["cells"], before=None if b is None else b["gap_mm"], after=s["gap_mm"]))
		rows.append(dict(pid=pid, cell=list(pr.piece(pid).celula), rotation=e.get("rotation"),
						 dtheta=float(e["theta_deg"] - PLb[pid]["theta_deg"]),
						 f_before=fb.get(pid), f_after=fa.get(pid), spread=(e.get("f_rotation") or {}).get("spread_deg"),
						 seams=sj, maxgap_before=max([abs(x["before"]) for x in sj if x["before"] is not None], default=None),
						 maxgap_after=max([abs(x["after"]) for x in sj], default=None)))
	return rows


def figure(pr, PLb, PLa, path):
	tiles = []
	for pid in REPORTED:
		pair = []
		for name, PL, col in (("antes (cantos)", PLb, (0, 0, 255)), ("depois (F)", PLa, (0, 200, 0))):
			img = TR.cell_view(pr, PL, pid, [(name, PL[pid], col)])
			l, c = pr.piece(pid).celula
			pair.append(TR.label(img, f"{pid} ({l},{c}) {name}: theta {PL[pid]['theta_deg']:.2f}", scale=0.55))
		tiles.append(TR.hcat(pair))
	big = TR.grid(tiles)
	return TR.save_jpg(path, big)


def main(argv=None):
	ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	ap.add_argument("--project", required=True)
	ap.add_argument("--before-placements", default=None, help="cópia cuja render/placements.json é a pose com imagem «antes»")
	ap.add_argument("--no-holes", action="store_true")
	ap.add_argument("--no-register-all", action="store_true")
	ap.add_argument("--no-fig", action="store_true")
	args = ap.parse_args(argv)
	if os.path.normcase(os.path.abspath(args.project)) == os.path.normcase(os.path.join(REPO, "projects", "alpes")):
		print("usar uma cópia de projects/alpes (--project)")
		return 2
	T, t0 = {}, time.time()
	F0 = R.F_ROTATION
	pr = Project.open(args.project)
	ids = R.placed_ids(pr)
	shapes = {pid: pr.shape(pid) for pid in pr.pieces if pr.piece(pid).estado != "descartada"}
	res = {"log_len": R._log_len(pr), "n_placed": len(ids)}

	t = time.time()
	PLb = gui_poses(pr, ids, False)
	PLa = gui_poses(pr, ids, True)
	T["registo_gui_2x_s"] = time.time() - t
	# equivalência com a variante «F» da triagem (só rotação em torno do centro do corpo)
	fest = {}
	for pid, L in f_tilts(pr, PLb, shapes).items():
		fest[pid] = float(np.mean([tl for _, tl in L]))
	PLtri = TR.variant_lines(PLb, fest)
	same = [p for p in PLa if PLa[p].get("rotation") == "F" and PLa[p]["f_rotation"]["n_f"] == 1 and len(PLa[p]["f_rotation"]["per_side"]) == 1]
	res["max_dtheta_vs_triagem_F"] = dict(n=len(same), max=float(max(abs(PLa[p]["theta_deg"] - PLtri[p]["theta_deg"]) for p in same)))
	res["max_dxy_after"] = float(max(np.hypot(PLa[p]["dx_mm"], PLa[p]["dy_mm"]) for p in PLa))
	sp = [e["f_rotation"]["spread_deg"] for e in PLa.values() if e.get("f_rotation") and e["f_rotation"]["n_f"] == 2]
	res["corner_pieces_two_f"] = dict(n=len(sp), spread_med=float(np.median(sp)) if sp else None, spread_max=float(max(sp)) if sp else None)
	dth = [abs(e["f_rotation"]["dtheta_deg"]) for e in PLa.values() if e.get("f_rotation")]
	res["dtheta_F_vs_corners"] = dict(n=len(dth), med=float(np.median(dth)), p95=float(np.percentile(dth, 95)), max=float(max(dth)))
	print("equivalência com a variante F da triagem: máx |dtheta|", res["max_dtheta_vs_triagem_F"], "; máx |dx,dy| depois", res["max_dxy_after"])
	print("cantos com 2 F:", res["corner_pieces_two_f"], "; |dtheta F - cantos|:", res["dtheta_F_vs_corners"])
	rr = []
	for pid, e in PLb.items():
		sh = shapes[pid]
		if sh is not None and sh.ok and e.get("corner"):
			rr += [R.f_side_line(sh, i)[1] for i, s in enumerate(sh.sides) if s.kind == "F" and R.f_side_line(sh, i)]
	rr = np.array(rr)
	res["f_line_rms"] = dict(n=len(rr), p50=float(np.median(rr)), p90=float(np.percentile(rr, 90)),
							 p95=float(np.percentile(rr, 95)), n_gt_thr=int((rr > R.F_LINE_RMS_MAX).sum()), thr=R.F_LINE_RMS_MAX)
	res["excluded_sides"] = excluded_sides(pr, PLb, PLa, shapes)
	print("RMS da reta F:", res["f_line_rms"])
	for d in res["excluded_sides"]:
		print(f"  fora: {d['pid']} {tuple(d['cell'])} {d['scan']} #{d['n']} {d['dir']} RMS {d['rms_mm']:.3f} reta {d['tilt_line']:+.2f} "
			  f"corda {d['tilt_chord']:+.2f} interior {d['tilt_inner']:+.2f} -> {d['rotation_after']}")

	hb = ha = None
	if not args.no_holes:
		import verde_tabuleiro as VT
		t = time.time()
		hb, ha = VT.holes(pr, PLb, True), VT.holes(pr, PLa, True)
		T["buracos_gui_s"] = time.time() - t
	g, sb, sa, fb, fa = gate(pr, "gui", PLb, PLa, shapes, hb, ha)
	res["gui"] = g

	rng = np.random.default_rng(SEED)
	border = sorted(p for p in PLa if PLa[p].get("rotation") == "F")
	ctrl = [str(x) for x in rng.choice([p for p in border if p not in LIST12 and p not in REPORTED], 30, replace=False)]
	res["control_seed"] = SEED
	res["control"] = ctrl
	res["focus_rows"] = piece_rows(pr, list(dict.fromkeys(REPORTED + LIST12)), PLb, PLa, sb, sa, fb, fa)
	res["control_rows"] = piece_rows(pr, ctrl, PLb, PLa, sb, sa, fb, fa)
	cr = res["control_rows"]
	res["control_summary"] = dict(
		f_abs_med_before=float(np.median([abs(t) for r in cr for _, t in (r["f_before"] or [])])),
		f_abs_med_after=float(np.median([abs(t) for r in cr for _, t in (r["f_after"] or [])])),
		maxgap_med_before=float(np.median([r["maxgap_before"] for r in cr if r["maxgap_before"] is not None])),
		maxgap_med_after=float(np.median([r["maxgap_after"] for r in cr if r["maxgap_after"] is not None])),
		n_maxgap_worse_02=sum(1 for r in cr if r["maxgap_before"] is not None and r["maxgap_after"] - r["maxgap_before"] > 0.2))
	print("controlo (30 de moldura):", res["control_summary"])
	for r in res["focus_rows"]:
		print(f"  {r['pid']} {tuple(r['cell'])} F {[(d, round(t, 2)) for d, t in (r['f_before'] or [])]} -> "
			  f"{[(d, round(t, 2)) for d, t in (r['f_after'] or [])]}; máx|folga| {r['maxgap_before']} -> {r['maxgap_after']}")

	if not args.no_fig:
		res["fig_bytes"] = figure(pr, PLb, PLa, os.path.join(OUT_DIR, "pose_f_P0240_P0590.jpg"))

	if args.before_placements and not args.no_register_all:
		prb = Project.open(args.before_placements)
		with open(prb.p("render", "placements.json"), encoding="utf-8") as fh:   # lido em bruto: sem a chave f_rotation seria «stale»
			PLib = {p: e for p, e in json.load(fh)["placements"].items() if p in PLa}
		R.F_ROTATION = True
		t = time.time()
		PLia = R.register_all(pr, image=True, force=True)
		T["register_all_image_s"] = time.time() - t
		PLib = {p: e for p, e in PLib.items() if p in PLia}
		PLia = {p: e for p, e in PLia.items() if p in PLib}
		res["image_methods_before"] = dict(collections.Counter(e["method"] for e in PLib.values()))
		hib = hia = None
		if not args.no_holes:
			import verde_tabuleiro as VT
			t = time.time()
			hib, hia = VT.holes(prb, PLib, True), VT.holes(pr, PLia, True)
			T["buracos_image_s"] = time.time() - t
		gi, *_ = gate(pr, "imagem", PLib, PLia, shapes, hib, hia)
		res["image"] = gi
	R.F_ROTATION = F0
	T["total_s"] = time.time() - t0
	res["timing_s"] = T
	with open(os.path.join(OUT_DIR, "pose_f.json"), "w", encoding="utf-8") as f:
		json.dump(res, f, ensure_ascii=False, indent=1, default=R._json_default)
	print("tempos:", {k: round(v, 1) for k, v in T.items()})
	return 0


if __name__ == "__main__":
	sys.exit(main())
