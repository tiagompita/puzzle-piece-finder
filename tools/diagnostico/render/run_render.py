"""Validation of the board render (src/render.py): registration, seams, green fringe, zones vs art.

Usage (from the repository root)::

	python tools/diagnostico/render/run_render.py [--project projects/alpes] [--skip-zones]

Writes ``docs/diagnostico/render/render_resultados.json`` and small figures (<= 300 KB) in
``docs/diagnostico/render/``; the full-size 300 dpi zones go to ``$PPF_SCRATCH/render/``.
Rebuilds ``projects/<id>/render/`` (clean crops with --force, placements.json).
Numbers and figures are discussed in docs/diagnostico/render/RENDER.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

from src import render as R                       # noqa: E402
from src.locate import CellArt, body_center_mm     # noqa: E402
from src.state import Project                      # noqa: E402

DOCS = os.path.join(ROOT, "docs", "diagnostico", "render")
GT_GRASS = ("S0003", "S0004")                      # BE / BD corners, loose GT scans
GRASS_PAGES = ("S0013", "S0014", "S0015", "S0016", "S0017", "S0018", "S0019")   # montado p05..p11
SKY_REF = ("S0022", "S0023")                       # montado p14, p15 (sky)
ZONES = {"grass": (42, 1, 47, 8), "sky": (1, 5, 6, 24)}
MAGENTA = (255, 0, 255)


def scratch() -> str:
	d = os.path.join(os.environ.get("PPF_SCRATCH", os.path.join(ROOT, "scratch")), "render")
	os.makedirs(d, exist_ok=True)
	return d


def pct(v, q=(5, 25, 50, 75, 95, 99)):
	v = np.asarray(v, float)
	return {f"p{k}": round(float(np.percentile(v, k)), 3) for k in q} if len(v) else {}


def imwrite(path, img, q=85):
	ext = os.path.splitext(path)[1].lower()
	params = [cv2.IMWRITE_JPEG_QUALITY, q] if ext in (".jpg", ".jpeg") else [cv2.IMWRITE_PNG_COMPRESSION, 9]
	cv2.imencode(ext, img, params)[1].tofile(path)
	return os.path.getsize(path)


def small(path, img, max_kb=290):
	"""Save a JPEG under ``max_kb`` (quality, then size, reduced as needed)."""
	q, im = 88, img
	while True:
		n = imwrite(path, im, q)
		if n <= max_kb * 1000:
			return n
		if q > 60:
			q -= 8
		else:
			im = cv2.resize(im, (int(im.shape[1] * 0.85), int(im.shape[0] * 0.85)), interpolation=cv2.INTER_AREA)


# ---------------------------------------------------------------- 1. calibration of the green threshold
def calibrate_green(pr) -> dict:
	bg = pr.profile.background_lab
	inter, ring = [], []
	for pid, p in pr.pieces.items():
		if p.scan_id not in GT_GRASS:
			continue
		m = R.fringe_masks(pr.crop_rgba(pid), bg, R._scan_mmpp(pr, p.scan_id))
		inter.append(m["bg_dist"][m["interior"]])
		ring.append(m["bg_dist"][m["alpha"] & (m["depth_px"] <= 1.5)])
	I, G = np.concatenate(inter), np.concatenate(ring)
	out = {"n_pieces": len(inter), "interior_p1": float(np.percentile(I, 1)), "interior_p5": float(np.percentile(I, 5)),
		   "interior_p50": float(np.percentile(I, 50)), "ring_p50": float(np.percentile(G, 50)),
		   "ring_below_thr": float((G < R.BG_DIST_MAX).mean()), "BG_DIST_MAX": R.BG_DIST_MAX,
		   "PIECE_P5_FRAC": R.PIECE_P5_FRAC}
	print(f"[calibração] verde: p5 do interior das {out['n_pieces']} peças de relva GT (BE/BD) = {out['interior_p5']:.1f} "
		  f"(p1 {out['interior_p1']:.1f}, mediana {out['interior_p50']:.1f}); anel exterior mediana {out['ring_p50']:.1f}; "
		  f"BG_DIST_MAX = {R.BG_DIST_MAX}")
	return out


# ---------------------------------------------------------------- 2. shadow pass measurement
def _quadrant_counts(mask, ctr_px):
	ys, xs = np.nonzero(mask)
	if len(xs) == 0:
		return np.zeros(4, int)
	a = np.degrees(np.arctan2(ys - ctr_px[1], xs - ctr_px[0]))      # image frame, y down: 0 = E, 90 = S
	q = ((a + 45) % 360 // 90).astype(int)                          # 0 E, 1 S, 2 W, 3 N
	return np.bincount(q, minlength=4)


def measure_shadow(pr) -> dict:
	"""Shadow pass (on top of the green pass) per scan-frame side: the cast shadow is on S and W."""
	bg = pr.profile.background_lab
	out = {}
	for name, scans in (("relva_gt", GT_GRASS), ("relva_p05_p11", GRASS_PAGES), ("ceu_p14_p15", SKY_REF)):
		cnt, n_alpha, n_band = np.zeros(4, int), 0, 0
		for pid, p in pr.pieces.items():
			if p.scan_id not in scans:
				continue
			mmpp = R._scan_mmpp(pr, p.scan_id)
			rgba = pr.crop_rgba(pid)
			m = R.fringe_masks(rgba, bg, mmpp, shadow=True)
			sh = pr.shape(pid)
			ctr = body_center_mm(sh) / mmpp - np.asarray(p.bbox[:2], float)
			cnt += _quadrant_counts(m["shadow"], ctr)
			n_alpha += int(m["alpha"].sum())
			n_band += int(m["band"].sum())
		tot = int(cnt.sum())
		lit = int(cnt[0] + cnt[3])
		shd = int(cnt[1] + cnt[2])
		out[name] = {"E": int(cnt[0]), "S": int(cnt[1]), "W": int(cnt[2]), "N": int(cnt[3]),
					 "frac_of_band": round(tot / max(1, n_band), 4), "lit_over_shadow": round(lit / max(1, shd), 3)}
		print(f"[sombra] {name}: removidos E {cnt[0]} S {cnt[1]} W {cnt[2]} N {cnt[3]} "
			  f"({100 * tot / max(1, n_band):.1f} % da banda); lados iluminados/sombra = {lit / max(1, shd):.2f}")
	return out


# ---------------------------------------------------------------- 3. green cleaning stats
def green_stats(pr) -> dict:
	bg = np.asarray(pr.profile.background_lab, float)
	fr, deep, de_int, de_bg, per = [], 0, [], [], {}
	n_light, light_grass = 0, []
	for pid in R.placed_ids(pr):
		p = pr.piece(pid)
		mmpp = R._scan_mmpp(pr, p.scan_id)
		rgba = pr.crop_rgba(pid)
		m = R.fringe_masks(rgba, bg, mmpp, shadow=R.SHADOW_DEFAULT)
		if R.is_light(m):
			m = R.fringe_masks(rgba, bg, mmpp, band_mm=R.LIGHT_BAND_MM, shadow=R.SHADOW_DEFAULT)
		rem = m["removed"]
		lab = R._lab(rgba[..., :3])
		f = float(rem.sum() / max(1, m["alpha"].sum()))
		fr.append(f)
		lim = (R.LIGHT_BAND_MM if R.is_light(m) else R.BAND_MM) / mmpp
		deep += int((rem & (m["depth_px"] > lim)).sum())
		n_light += int(R.is_light(m))
		if R.is_light(m) and p.scan_id in GT_GRASS + GRASS_PAGES:
			light_grass.append(pid)
		if rem.any() and m["interior"].any():
			mi = lab[m["interior"]].mean(0)
			de_int.append(float(np.linalg.norm(lab[rem] - mi, axis=1).mean()))
			de_bg.append(float(np.linalg.norm(lab[rem] - bg, axis=1).mean()))
		per[pid] = f
	out = {"n": len(fr), "removed_frac": pct(fr), "removed_frac_mean": float(np.mean(fr)), "deep_removed": deep,
		   "dE_removed_vs_interior_mean": pct(de_int, (5, 50, 95)), "dE_removed_vs_background": pct(de_bg, (5, 50, 95)),
		   "por_grupo": {}, "n_claras": n_light, "claras_em_relva": light_grass}
	for name, scans in (("relva_gt", GT_GRASS), ("relva_p05_p11", GRASS_PAGES), ("ceu_p14_p15", SKY_REF)):
		rem = band = rim = rim_left = 0
		thr, tint0, tint1, p5s = [], [], [], []
		for pid in R.placed_ids(pr):
			p = pr.piece(pid)
			if p.scan_id not in scans:
				continue
			mmpp = R._scan_mmpp(pr, p.scan_id)
			m = R.fringe_masks(pr.crop_rgba(pid), bg, mmpp, shadow=R.SHADOW_DEFAULT)
			if R.is_light(m):
				m = R.fringe_masks(pr.crop_rgba(pid), bg, mmpp, band_mm=R.LIGHT_BAND_MM, shadow=R.SHADOW_DEFAULT)
			r = m["band"] & (m["depth_px"] <= 0.5 / mmpp)
			rem += int(m["removed"].sum())
			band += int(m["band"].sum())
			rim += int(r.sum())
			rim_left += int((r & ~m["removed"]).sum())
			thr.append(m["thr"])
			p5s.append(m["p5"])
			kept = m["band"] & ~m["removed"]
			if kept.any() and m["interior"].any():
				rgba = pr.crop_rgba(pid)
				oc = R.clean_crop(rgba, bg, mmpp)
				lab0, lab1 = R._lab(rgba[..., :3]), R._lab(oc[..., :3])
				mi = lab0[m["interior"]].mean(0)
				tint0.append(float(np.linalg.norm(lab0[kept] - mi, axis=1).mean()))
				tint1.append(float(np.linalg.norm(lab1[kept] - mi, axis=1).mean()))
		g = {"removed_of_band": round(rem / max(1, band), 3),
			 "outer_0.5mm_left": round(rim_left / max(1, rim), 3), "thr_median": round(float(np.median(thr)), 1),
			 "thr_max": round(float(np.max(thr)), 1),
			 "dE_band_kept_vs_interior_before": round(float(np.median(tint0)), 2),
			 "dE_band_kept_vs_interior_after": round(float(np.median(tint1)), 2),
			 "n_light": int(sum(1 for t in p5s if t > R.LIGHT_PIECE_P5_MIN))}
		out["por_grupo"][name] = g
		print(f"[verde] {name}: removido {100 * g['removed_of_band']:.1f} % da banda, "
			  f"resta {100 * g['outer_0.5mm_left']:.1f} % dos 0,5 mm exteriores; limiar mediana {g['thr_median']} (máx {g['thr_max']}); "
			  f"ΔE banda mantida↔interior {g['dE_band_kept_vs_interior_before']} → {g['dE_band_kept_vs_interior_after']} "
			  f"({g['n_light']} peças claras)")
	# deep paper blobs (segmentation filled a socket with paper): never touched by the cleaning
	blobs = []
	for pid in R.placed_ids(pr):
		p = pr.piece(pid)
		mmpp = R._scan_mmpp(pr, p.scan_id)
		m = R.fringe_masks(pr.crop_rgba(pid), bg, mmpp)
		cand = (m["alpha"] & (m["depth_px"] > R.BAND_MM / mmpp) & (m["bg_dist"] < 15)).astype(np.uint8)
		n, lab, st, _ = cv2.connectedComponentsWithStats(cand, connectivity=8)
		big = [int(st[k, cv2.CC_STAT_AREA]) for k in range(1, n) if st[k, cv2.CC_STAT_AREA] * mmpp * mmpp >= 1.0]
		if big:
			blobs.append({"piece": pid, "cell": list(p.celula), "area_mm2": round(sum(big) * mmpp * mmpp, 2)})
	out["papel_fundo_interior"] = blobs
	print(f"[verde] manchas de papel verde a > {R.BAND_MM} mm do bordo (≥ 1 mm², ΔE<15 ao fundo; defeito da segmentação, "
		  f"não limpas): {len(blobs)} peças " + ", ".join(f"{b['piece']}{tuple(b['cell'])} {b['area_mm2']} mm²" for b in blobs[:10]))
	print(f"[verde] peças claras (p5 > {R.LIGHT_PIECE_P5_MIN}): {n_light}; das quais em relva GT/p05-p11: {light_grass}")
	print(f"[verde] {len(fr)} peças: fração removida mediana {100 * np.median(fr):.2f} % (p95 {100 * np.percentile(fr, 95):.2f} %); "
		  f"removidos além da banda (0,7 mm; 1,2 nas claras): {deep}; ΔE removidos↔interior mediana {np.median(de_int):.1f}, "
		  f"removidos↔fundo mediana {np.median(de_bg):.1f}")
	return out, per


def overlay_figure(pr, path, pids, title):
	"""Per piece: raw crop on grey | removed pixels in magenta (native resolution)."""
	bg = pr.profile.background_lab
	tiles = []
	for pid in pids:
		p = pr.piece(pid)
		rgba = pr.crop_rgba(pid)
		mmpp = R._scan_mmpp(pr, p.scan_id)
		m = R.fringe_masks(rgba, bg, mmpp, shadow=R.SHADOW_DEFAULT)
		if R.is_light(m):
			m = R.fringe_masks(rgba, bg, mmpp, band_mm=R.LIGHT_BAND_MM, shadow=R.SHADOW_DEFAULT)
		a = rgba[..., 3:4].astype(np.float32) / 255
		grey = np.full(rgba.shape[:2] + (3,), 128, np.float32)
		raw = (rgba[..., :3] * a + grey * (1 - a)).astype(np.uint8)
		mk = raw.copy()
		mk[m["removed"]] = MAGENTA
		after = (rgba[..., :3] * (a * (~m["removed"][..., None])) + grey * (1 - a * (~m["removed"][..., None]))).astype(np.uint8)
		t = np.hstack([raw, np.full((raw.shape[0], 4, 3), 255, np.uint8), mk, np.full((raw.shape[0], 4, 3), 255, np.uint8), after])
		t = cv2.cvtColor(t, cv2.COLOR_RGB2BGR)
		cv2.putText(t, f"{pid} {tuple(p.celula)}", (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
		tiles.append(t)
	W = max(t.shape[1] for t in tiles)
	tiles = [np.pad(t, ((0, 6), (0, W - t.shape[1]), (0, 0)), constant_values=255) for t in tiles]
	img = np.vstack(tiles)
	cv2.putText(img, title, (6, img.shape[0] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
	return small(path, img)


def detail_figure(pr, path, pid, zoom=4, win=110):
	"""Zoomed edge of one piece: raw | removed in magenta, ``win`` px around the most-removed edge point."""
	p = pr.piece(pid)
	rgba = pr.crop_rgba(pid)
	m = R.fringe_masks(rgba, pr.profile.background_lab, R._scan_mmpp(pr, p.scan_id), shadow=R.SHADOW_DEFAULT)
	ys, xs = np.nonzero(m["removed"])
	if len(xs) == 0:
		return 0
	k = cv2.boxFilter(m["removed"].astype(np.float32), -1, (41, 41))
	y, x = np.unravel_index(int(np.argmax(k)), k.shape)
	y0, x0 = max(0, y - win // 2), max(0, x - win // 2)
	sl = (slice(y0, y0 + win), slice(x0, x0 + win))
	a = rgba[sl][..., 3:4].astype(np.float32) / 255
	raw = (rgba[sl][..., :3] * a + 128 * (1 - a)).astype(np.uint8)
	mk = raw.copy()
	mk[m["removed"][sl]] = MAGENTA
	t = np.hstack([raw, np.full((raw.shape[0], 2, 3), 255, np.uint8), mk])
	t = cv2.resize(t, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_NEAREST)
	return small(path, cv2.cvtColor(t, cv2.COLOR_RGB2BGR))


# ---------------------------------------------------------------- 4. registration + seams
def zone_of(g, prof):
	rows = [g["cells"][0][0], g["cells"][1][0]]
	z = []
	if all(1 <= r <= 7 for r in rows):
		z.append("ceu_1_7")
	if all(41 <= r <= 47 for r in rows):
		z.append("relva_41_47")
	if any(prof.is_border(*c) for c in g["cells"]):
		z.append("bordas")
	return z


def seam_table(pr, gaps) -> dict:
	out = {}
	for zone in ("todas", "ceu_1_7", "relva_41_47", "bordas"):
		v = [g["gap_mm"] for g in gaps if zone == "todas" or zone in zone_of(g, pr.profile)]
		a = np.abs(v)
		out[zone] = {"n": len(v), "median_gap": round(float(np.median(v)), 3) if v else None,
					 "median_abs": round(float(np.median(a)), 3) if v else None,
					 "p95_abs": round(float(np.percentile(a, 95)), 3) if v else None,
					 "frac_abs_gt_0.8": round(float((a > 0.8).mean()), 3) if v else None}
	return out


def histogram_png(path, series: dict, xlabel, bins, xr):
	"""Tiny matplotlib-free histogram (OpenCV): one row per series."""
	Wp, Hp, pad = 640, 120, 40
	img = np.full((len(series) * (Hp + 26) + pad, Wp + 2 * pad, 3), 255, np.uint8)
	edges = np.linspace(xr[0], xr[1], bins + 1)
	for i, (name, v) in enumerate(series.items()):
		h, _ = np.histogram(np.clip(v, xr[0], xr[1] - 1e-9), edges)
		y0 = i * (Hp + 26) + 20
		cv2.putText(img, f"{name} (n={len(v)}, med {np.median(v):.2f})", (pad, y0 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
					(0, 0, 0), 1, cv2.LINE_AA)
		hm = max(1, h.max())
		for j, c in enumerate(h):
			x0 = pad + int(j * Wp / bins)
			x1 = pad + int((j + 1) * Wp / bins) - 1
			cv2.rectangle(img, (x0, y0 + Hp - int(Hp * c / hm)), (x1, y0 + Hp), (180, 110, 40), -1)
		cv2.line(img, (pad, y0 + Hp), (pad + Wp, y0 + Hp), (0, 0, 0), 1)
	for t in np.linspace(xr[0], xr[1], 6):
		x = pad + int((t - xr[0]) / (xr[1] - xr[0]) * Wp)
		cv2.putText(img, f"{t:.1f}", (x - 10, img.shape[0] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1, cv2.LINE_AA)
	cv2.putText(img, xlabel, (pad + Wp // 2 - 60, img.shape[0] - 1), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1, cv2.LINE_AA)
	return imwrite(path, img)


def zone_pixel_metrics(pr, reg, ppc, variants: dict) -> dict:
	"""Gap and green pixels inside the cells of ``reg`` whose 8 neighbours are all placed.

	Each variant is rendered with only the pieces over a magenta base: gap = pixel within 80 (BGR
	distance) of magenta; green = :func:`src.render.bg_distance` < ``BG_DIST_MAX``."""
	l0, c0, l1, c1 = reg
	prof = pr.profile
	ch = ppc * float(prof.cell_mm["h"]) / float(prof.cell_mm["w"])
	occ = lambda l, c: prof.in_grid(l, c) and pr.board[(l, c)]["estado"] == "colocada"
	cells = [(l, c) for l in range(l0, l1 + 1) for c in range(c0, c1 + 1)
			 if all(occ(l + i, c + j) for i in (-1, 0, 1) for j in (-1, 0, 1))]
	out = {"n_cells_interiores": len(cells)}
	for name, kw in variants.items():
		img = R.compose_board(pr, ppc, region=reg, layers=("pieces",), base_bgr=(255, 0, 255), **kw)
		mask = np.zeros(img.shape[:2], bool)
		for l, c in cells:
			mask[int((l - l0) * ch):int((l - l0 + 1) * ch), int((c - c0) * ppc):int((c - c0 + 1) * ppc)] = True
		gap = np.linalg.norm(img.astype(float) - [255, 0, 255], axis=-1) < 80
		lab = R._lab(img[..., ::-1])
		green = R.bg_distance(lab, pr.profile.background_lab) < R.BG_DIST_MAX
		n = max(1, int(mask.sum()))
		out[name] = {"gap_px_per_mil": round(1000 * float((gap & mask).sum()) / n, 2),
					 "green_px_per_mil": round(1000 * float((green & mask & ~gap).sum()) / n, 2)}
	return out


def main(argv=None) -> int:
	ap = argparse.ArgumentParser()
	ap.add_argument("--project", default=os.path.join(ROOT, "projects", "alpes"))
	ap.add_argument("--skip-zones", action="store_true")
	a = ap.parse_args(argv)
	if hasattr(sys.stdout, "reconfigure"):
		sys.stdout.reconfigure(encoding="utf-8")
	os.makedirs(DOCS, exist_ok=True)
	pr = Project.open(a.project)
	res = {"project": os.path.relpath(pr.path, ROOT).replace("\\", "/")}
	t0 = time.time()
	res["calibracao_verde"] = calibrate_green(pr)
	res["sombra"] = measure_shadow(pr)
	res["verde"], per_frac = green_stats(pr)
	t = time.time()
	R.clean_all(pr, force=True)
	res["t_clean_s"] = round(time.time() - t, 1)

	# registration: BEFORE (make_mock pose), corners only, final (corners + image, cache)
	art = CellArt.load(pr.profile, ROOT)
	ids = R.placed_ids(pr)
	base = {pid: R.baseline_placement(pr, pid) for pid in ids}
	t = time.time()
	final = R.register_all(pr, art=art, image=True, force=True)
	res["t_register_s"] = round(time.time() - t, 1)
	corners = {}
	for pid, e in final.items():
		c = dict(e)
		if e.get("corner") and e["method"] in ("corners", "corners+image"):
			c.update(theta_deg=e["corner"]["theta_deg"], dx_mm=0.0, dy_mm=0.0)
		corners[pid] = c
	methods = {}
	for e in final.values():
		methods[e["method"]] = methods.get(e["method"], 0) + 1
	res["registo"] = {
		"n": len(final), "methods": methods,
		"residual_nominal_mm": pct([e["residual_mm"] for e in final.values() if e["residual_mm"] is not None]),
		"n_residual_nominal_gt_1": int(sum(1 for e in final.values() if (e["residual_mm"] or 0) > 1.0)),
		"shape_residual_mm": pct([e["shape_residual_mm"] for e in final.values() if e["shape_residual_mm"] is not None]),
		"n_shape_residual_gt_1": int(sum(1 for e in final.values() if (e["shape_residual_mm"] or 0) > 1.0)),
		"dtheta_corner_vs_initial_deg": pct([abs(e["corner"]["dtheta0_deg"]) for e in final.values()
											 if e.get("corner") and e["corner"].get("dtheta0_deg") is not None], (50, 90, 99, 100)),
		"image_shift_mm_all": pct([np.hypot(e["image"]["ddx_mm"], e["image"]["ddy_mm"]) for e in final.values() if e.get("image")],
								 (25, 50, 75, 90)),
		"image_at_edge": int(sum(1 for e in final.values() if e.get("image") and e["image"]["at_edge"])),
		"image_accepted": int(sum(1 for e in final.values() if e.get("image") and e["image"].get("accepted"))),
		"image_ncc": pct([e["image"]["ncc"] for e in final.values() if e.get("image")], (25, 50, 75)),
	}
	g_base = R.seam_gaps(pr, base)
	g_corn = R.seam_gaps(pr, corners)
	g_fin = R.seam_gaps(pr, final)
	res["junta"] = {"antes_make_mock": seam_table(pr, g_base), "depois_cantos": seam_table(pr, g_corn),
					"depois_cantos_imagem": seam_table(pr, g_fin)}
	for k, v in res["junta"].items():
		print(f"[junta] {k}: " + "; ".join(f"{z} n={d['n']} med|gap| {d['median_abs']} p95 {d['p95_abs']} "
											  f"(med {d['median_gap']})" for z, d in v.items()))
	histogram_png(os.path.join(DOCS, "residuo_cantos.png"),
				  {"residuo vs celula nominal (+0.48 mm)": [e["residual_mm"] for e in final.values() if e["residual_mm"] is not None],
				   "residuo vs retangulo livre (porta)": [e["shape_residual_mm"] for e in final.values() if e["shape_residual_mm"] is not None]},
				  "mm", 40, (0.0, 2.0))
	histogram_png(os.path.join(DOCS, "junta_antes_depois.png"),
				  {"antes (make_mock)": [g["gap_mm"] for g in g_base], "depois (cantos)": [g["gap_mm"] for g in g_corn],
				   "depois (cantos+imagem)": [g["gap_mm"] for g in g_fin]},
				  "seam_gap_mm (linha de corte; >0 folga, <0 sobreposicao)", 48, (-2.0, 2.0))

	# figures of the green cleaning on grass
	bg = pr.profile.background_lab

	def greenest(scans, n):
		cand = []
		for pid in ids:
			p = pr.piece(pid)
			if p.scan_id not in scans:
				continue
			m = R.fringe_masks(pr.crop_rgba(pid), bg, R._scan_mmpp(pr, p.scan_id))
			cand.append((float((m["bg_dist"][m["interior"]] < R.BG_DIST_MAX + 5).mean()), pid))
		return [pid for _, pid in sorted(cand, reverse=True)[:n]]

	gt_p = greenest(GT_GRASS, 4)
	pg_p = greenest(GRASS_PAGES, 4)
	res["figuras_verde"] = {"gt": gt_p, "paginas": pg_p}
	overlay_figure(pr, os.path.join(DOCS, "verde_gt_BE_BD.jpg"), gt_p, "cru | removido a magenta | depois (fundo cinzento)")
	overlay_figure(pr, os.path.join(DOCS, "verde_paginas_p05_p11.jpg"), pg_p, "cru | removido a magenta | depois")
	sky_p = [pid for pid in ids if pr.piece(pid).scan_id in SKY_REF][:3]
	res["figuras_verde"]["ceu"] = sky_p
	overlay_figure(pr, os.path.join(DOCS, "verde_ceu_p14_p15.jpg"), sky_p, "cru | removido a magenta | depois")
	lg = res["verde"].get("claras_em_relva") or []
	if lg:
		overlay_figure(pr, os.path.join(DOCS, "verde_relva_clara_banda12.jpg"), lg[:4],
					   "relva classificada clara (banda 1,2 mm): cru | removido | depois")
	detail_figure(pr, os.path.join(DOCS, "verde_detalhe.jpg"), gt_p[0])

	# zones at 300 dpi: BEFORE (raw crops, make_mock pose) and AFTER (clean, registered) vs art
	if not a.skip_zones:
		sc = scratch()
		ppc = float(pr.profile.cell_mm["w"]) / (25.4 / 300.0)
		for zname, reg in ZONES.items():
			t = time.time()
			before = R.compose_board(pr, ppc, region=reg, placements=base, layers=("art", "pieces"), clean=False,
									 depth_priority=False, bleed_mm=0)
			mid = R.compose_board(pr, ppc, region=reg, placements=final, layers=("art", "pieces"), depth_priority=False,
								  bleed_mm=0)
			imwrite(os.path.join(sc, f"zona_{zname}_depois_sem_prioridade.jpg"), mid, 90)
			after = R.compose_board(pr, ppc, region=reg, placements=final, layers=("art", "pieces"))
			artz = R.compose_board(pr, ppc, region=reg, layers=("art",), art_alpha=1.0)
			sep = np.full((after.shape[0], 8, 3), 255, np.uint8)
			imwrite(os.path.join(sc, f"zona_{zname}_depois_vs_arte.jpg"), np.hstack([after, sep, artz]), 90)
			imwrite(os.path.join(sc, f"zona_{zname}_antes.jpg"), before, 90)
			imwrite(os.path.join(sc, f"zona_{zname}_depois.jpg"), after, 90)
			res.setdefault("t_zone_s", {})[zname] = round(time.time() - t, 1)
			zm = zone_pixel_metrics(pr, reg, ppc, {
				"antes_make_mock": dict(placements=base, clean=False, depth_priority=False, bleed_mm=0),
				"cantos_limpo": dict(placements=final, depth_priority=False, bleed_mm=0),
				"cantos_limpo_prioridade": dict(placements=final, bleed_mm=0),
				"final_com_sangria": dict(placements=final)})
			res.setdefault("zona_pixeis", {})[zname] = zm
			print(f"[zona {zname}] células interiores {zm['n_cells_interiores']}: " + "; ".join(
				f"{k}: folga {v['gap_px_per_mil']} ‰, verde {v['green_px_per_mil']} ‰" for k, v in zm.items() if isinstance(v, dict)))
			# 100 % detail for the docs: 3 x 3 cells around the middle of the zone, before | after | art
			l0, c0, l1, c1 = reg
			lm, cm = (l0 + l1) // 2, (c0 + c1) // 2
			ch = float(pr.profile.cell_mm["h"]) / (25.4 / 300.0)
			y0, x0 = int((lm - 1 - l0) * ch), int((cm - 1 - c0) * ppc)
			hh, ww = int(2.2 * ch), int(2.2 * ppc)
			y0, x0 = max(0, y0), max(0, x0)
			crop = lambda im: im[y0:y0 + hh, x0:x0 + ww]
			det = np.hstack([crop(before), np.full((hh, 6, 3), 255, np.uint8), crop(mid), np.full((hh, 6, 3), 255, np.uint8),
							 crop(after), np.full((hh, 6, 3), 255, np.uint8), crop(artz)])
			small(os.path.join(DOCS, f"zona_{zname}_100pc_antes_depois_arte.jpg"), det)
			ov = cv2.resize(np.hstack([before, sep, after, sep, artz]), None, fx=0.18, fy=0.18, interpolation=cv2.INTER_AREA)
			small(os.path.join(DOCS, f"zona_{zname}_visao.jpg"), ov)
		# default (1.2 mm on light pieces) vs the former 0.7 mm everywhere (RENDER.md §2.5)
		reg = (2, 12, 4, 16)
		bdef = R.compose_board(pr, ppc, region=reg, placements=final, layers=("art", "pieces"))
		zw = zone_pixel_metrics(pr, ZONES["sky"], ppc, {"padrao_1.2_claras": dict(placements=final)})
		orig = R._clean_or_crop
		R._clean_or_crop = lambda project, pid: R.clean_crop(project.crop_rgba(pid), project.profile.background_lab,
															  R._scan_mmpp(project, project.piece(pid).scan_id), light_band_mm=None)
		try:
			bnarrow = R.compose_board(pr, ppc, region=reg, placements=final, layers=("art", "pieces"))
			zm = zone_pixel_metrics(pr, ZONES["sky"], ppc, {"banda_0.7_todas": dict(placements=final)})
			zg = zone_pixel_metrics(pr, ZONES["grass"], ppc, {"banda_0.7_todas": dict(placements=final)})
		finally:
			R._clean_or_crop = orig
		res["ceu_banda_larga"] = {"banda_0.7_todas": zm["banda_0.7_todas"], "padrao_1.2_claras": zw["padrao_1.2_claras"],
								  "relva_banda_0.7_todas": zg["banda_0.7_todas"]}
		print(f"[céu] 0,7 mm em todas: {zm['banda_0.7_todas']}; padrão (1,2 mm nas claras): {zw['padrao_1.2_claras']}; "
			  f"relva com 0,7 em todas: {zg['banda_0.7_todas']}")
		small(os.path.join(DOCS, "ceu_banda_07_vs_12.jpg"), np.hstack([bnarrow, np.full((bdef.shape[0], 6, 3), 255, np.uint8), bdef]))
		board = R.compose_board(pr, 60, placements=final)
		imwrite(os.path.join(sc, "tabuleiro_ppc60.jpg"), board, 88)
		small(os.path.join(DOCS, "tabuleiro_ppc60.jpg"), cv2.resize(board, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA))
	res["t_total_s"] = round(time.time() - t0, 1)
	with open(os.path.join(DOCS, "render_resultados.json"), "w", encoding="utf-8", newline="\n") as f:
		json.dump(res, f, ensure_ascii=False, indent=1, default=R._json_default)
		f.write("\n")
	print(f"resultados: {os.path.join(DOCS, 'render_resultados.json')} ({res['t_total_s']} s)")
	return 0


if __name__ == "__main__":
	sys.exit(main())
