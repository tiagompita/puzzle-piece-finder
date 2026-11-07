"""Stroke editor solvers (:mod:`src.strokes`) against the two hand-cut masks of R0011/R0012 (read-only).

Ground truth: ``docs/diagnostico/reports/R0011_R0012_manual/manual_{A,B}_photoshop.png`` (RGBA on the
pixel grid of ``images/pieces/legado/montado_p12_300dpi.jpg``; alpha > 127, largest component) =
P0651 (44,1) and P0657 (45,1) of S0020. The current contour of each piece comes from
``projects/<id>/pieces/S0020.npz`` (``contour_px``), the editor crop from ``overrides.crop_window``.
Nothing is written to the project.

Scenarios (strokes synthesised from the GT, simulating the user):
  (i)   automatic trimap only (no stroke);
  (ii)  automatic trimap + 1 lasso "incerto" = the largest component of GT xor automatic, dilated 1.5 mm;
  (iii) "one wide lasso": lasso "fundo" = whole crop, lasso "incerto" = GT dilated 2.5 mm,
        lasso "peca" = GT eroded 2.5 mm (5 mm uncertain band centred on the GT); (iii-in) / (iii-out):
        the same 5 mm band shifted 1 mm inwards / outwards (an imprecise user: the band midline is not
        the GT).
For each solver x variant: ``maskcmp.mask_metrics`` against the GT and the time of ``strokes.resolver``
(median of 3 runs). Output: a markdown table on stdout, ``--json`` and the figure ``--fig``.

Usage::

	python tools/diagnostico/editor/tracos_gt.py --project projects/alpes \
		--json docs/diagnostico/editor/tracos_gt.json --fig docs/diagnostico/editor/TRACOS_gt.jpg
"""

import argparse
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO)

from src import maskcmp as M  # noqa: E402
from src import overrides as OV  # noqa: E402
from src import strokes as ST  # noqa: E402
from src.segmentation import _rim_background  # noqa: E402
from src.state import Project  # noqa: E402

GT_DIR = os.path.join(REPO, "docs", "diagnostico", "reports", "R0011_R0012_manual")
PIECES = (("P0651", "manual_A_photoshop.png"), ("P0657", "manual_B_photoshop.png"))

# solver variants measured: (label, solver, params). Explicit parameters (not the module defaults), so
# the table stays valid if the defaults change; "omissão" is the module default.
_RGB = {"espaco": "rgb", "peso_l": 1.0}
_L0 = {"espaco": "lab", "peso_l": 0.0}
VARIANTS = [
	("grabcut (omissão)", "grabcut", {}),
	("gc rgb it3", "grabcut", dict(_RGB, iters=3)),
	("grabcut rgb it3 +limiar28", "grabcut", dict(_RGB, iters=3, limiar=28.0)),
	("grabcut lab L0.25 it3", "grabcut", {"espaco": "lab", "peso_l": 0.25, "iters": 3}),
	("grabcut lab L0 it1", "grabcut", dict(_L0, iters=1)),
	("grabcut lab L0 it2", "grabcut", dict(_L0, iters=2)),
	("grabcut lab L0 it3", "grabcut", dict(_L0, iters=3)),
	("grabcut lab L0 it5", "grabcut", dict(_L0, iters=5)),
	("grabcut lab L0 it2 alc0.5", "grabcut", dict(_L0, iters=2, alcance_mm=0.5)),
	("grabcut lab L0 it2 alc1.5", "grabcut", dict(_L0, iters=2, alcance_mm=1.5)),
	("grabcut lab L0 it2 inc=fgd", "grabcut", dict(_L0, iters=2, incerto="fgd")),
	("grabcut lab L0 it2 inc=bgd", "grabcut", dict(_L0, iters=2, incerto="bgd")),
	("grabcut lab L0 it2 recorte", "grabcut", dict(_L0, iters=2, janela="recorte")),
	("watershed cor rgb", "watershed", dict(_RGB, paisagem="cor")),
	("ws cor L0", "watershed", dict(_L0, paisagem="cor")),
	("watershed relevo", "watershed", {"paisagem": "relevo"}),
	("watershed inundacao", "watershed", {"paisagem": "inundacao"}),
	("limiar (segmentador)", "limiar", {"peso_l": 0.5, "limiar": 28.0}),
	("limiar lab L0 t25", "limiar", {"peso_l": 0.0, "limiar": 25.0}),
]
DEFAULT = ("grabcut (omissão)", "grabcut", {})


def peel(mask, rgb, mmpp, depth_mm=0.5, l_max=60):
	"""EXPERIMENT (not in src.strokes): remove the dark pixels (8-bit L* < ``l_max``) of the outer
	``depth_mm`` of ``mask`` that are 4-connected, through dark band pixels, to its boundary (the
	near-black core of the cast shadow, which chroma alone cannot call background), then clean."""
	L = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)[..., 0]
	r = max(1, int(round(depth_mm / mmpp)))
	band = mask & ~(cv2.erode(mask.astype(np.uint8), _disc(r)) > 0)
	cand = band & (L < l_max)
	_, cc = cv2.connectedComponents(cand.astype(np.uint8), connectivity=4)
	touch = np.unique(cc[M.boundary(mask) & cand])
	return ST.limpar(mask & ~np.isin(cc, touch[touch > 0]), mmpp)


def _largest(m):
	n, cc, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
	return cc == 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA])) if n > 1 else np.zeros(m.shape, bool)


def _outer(m):
	cnts, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
	return [c.reshape(-1, 2).astype(float).tolist() for c in cnts if len(c) >= 3]


def _disc(r):
	return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def scenario_strokes(name, gt, auto, mmpp):
	"""Normalised strokes of a scenario (crop px)."""
	h, w = gt.shape
	if name == "i":
		return []
	if name == "ii":
		diff = (gt ^ auto).astype(np.uint8)
		diff = cv2.morphologyEx(diff, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
		comp = _largest(diff > 0)
		zone = cv2.dilate(comp.astype(np.uint8), _disc(int(round(1.5 / mmpp)))) > 0
		tr = [{"ferramenta": "laco", "marca": "incerto", "pontos": c} for c in _outer(zone)]
	else:
		shift = {"iii": 0.0, "iii-in": -1.0, "iii-out": 1.0}[name]
		r_in, r_out = int(round((2.5 - shift) / mmpp)), int(round((2.5 + shift) / mmpp))
		inner = cv2.erode(gt.astype(np.uint8), _disc(r_in)) > 0
		outer = cv2.dilate(gt.astype(np.uint8), _disc(r_out)) > 0
		tr = [{"ferramenta": "laco", "marca": "fundo", "pontos": [[-1, -1], [w, -1], [w, h], [-1, h]]}]
		tr += [{"ferramenta": "laco", "marca": "incerto", "pontos": c} for c in _outer(outer)]
		tr += [{"ferramenta": "laco", "marca": "peca", "pontos": c} for c in _outer(_largest(inner))]
	norm, err = ST.validar_tracos(tr, w, h)
	assert err is None, err
	return norm


def _metrics(gt, cand, mmpp):
	r = M.mask_metrics(gt, cand, mmpp)
	return {k: round(float(r[k]), 4) for k in ("iou", "missing_mm2", "excess_mm2", "missing_depth_mm",
												   "excess_depth_mm", "d_mean", "d_p95", "d_max")}


def load(project):
	pr = Project.open(project)
	data = []
	rgb_scan = bg = None
	for pid, f in PIECES:
		p = pr.piece(pid)
		if rgb_scan is None:
			rgb_scan = OV.load_scan_rgb(pr, p.scan_id)
			mmpp = OV._mmpp(pr, p.scan_id)
			bg = _rim_background(cv2.cvtColor(rgb_scan, cv2.COLOR_RGB2LAB).astype(np.float32), mmpp)
		x0, y0, x1, y1, _ = OV.crop_window(pr, pid)
		gt_full = np.asarray(Image.open(os.path.join(GT_DIR, f)))[..., 3] > 127
		assert gt_full.shape == rgb_scan.shape[:2]
		gt = _largest(gt_full[y0:y1, x0:x1])
		auto_c = np.asarray(pr.contour_px(pid), float) - [x0, y0]
		auto = M.fill_contour(auto_c, gt.shape)
		data.append({"pid": pid, "rgb": np.ascontiguousarray(rgb_scan[y0:y1, x0:x1]), "gt": gt, "auto": auto,
					 "origem": (x0, y0), "mmpp": mmpp, "bg": bg, "auto_contour": auto_c})
	return data


def run(data, scenarios, variants, reps=3, banda_mm=ST.BANDA_MM, limpeza_mm=ST.LIMPEZA_MM, with_peel=False):
	rows = []
	for d in data:
		mmpp = d["mmpp"]
		rows.append({"piece": d["pid"], "scenario": "-", "variant": "índice (contour_px)", "ms": None,
					 **_metrics(d["gt"], d["auto"], mmpp)})
		for sc in scenarios:
			tr = scenario_strokes(sc, d["gt"], d["auto"], mmpp)
			for label, solver, params in variants:
				times, res = [], None
				for _ in range(reps):
					res = ST.resolver(d["rgb"], d["auto"], tr, mmpp, solver=solver, params=params, bg_lab=d["bg"],
									  banda_mm=banda_mm, limpeza_mm=limpeza_mm)
					assert "error" not in res, res
					times.append(res["ms"])
				rows.append({"piece": d["pid"], "scenario": sc, "variant": label, "ms": round(float(np.median(times)), 1),
							 "h": d["rgb"].shape[0], "w": d["rgb"].shape[1], **_metrics(d["gt"], res["mask"], mmpp)})
				if with_peel and (label, solver, params) == DEFAULT:
					for depth, lmax in ((0.3, 60), (0.5, 60), (0.5, 90)):
						rows.append({"piece": d["pid"], "scenario": sc, "ms": None,
									 "variant": f"{label} + pele {depth} mm L<{lmax} (experiência)",
									 **_metrics(d["gt"], peel(res["mask"], d["rgb"], mmpp, depth, lmax), mmpp)})
	return rows


def table(rows):
	out = ["| peça | cenário | variante | IoU | em falta mm² | a mais mm² | p95 mm | máx mm | ms |",
		   "|---|---|---|---|---|---|---|---|---|"]
	for r in rows:
		out.append(f"| {r['piece']} | {r['scenario']} | {r['variant']} | {r['iou']:.4f} | {r['missing_mm2']:.2f} | "
				   f"{r['excess_mm2']:.2f} | {r['d_p95']:.2f} | {r['d_max']:.2f} | {'' if r['ms'] is None else r['ms']} |")
	return "\n".join(out)


def summary(rows):
	"""Mean over the two pieces per (scenario, variant)."""
	keys = {}
	for r in rows:
		keys.setdefault((r["scenario"], r["variant"]), []).append(r)
	out = ["| cenário | variante | IoU média | p95 médio mm | em falta mm² (soma) | a mais mm² (soma) | ms máx |",
		   "|---|---|---|---|---|---|---|"]
	for (sc, v), rs in keys.items():
		ms = [r["ms"] for r in rs if r["ms"] is not None]
		out.append(f"| {sc} | {v} | {np.mean([r['iou'] for r in rs]):.4f} | {np.mean([r['d_p95'] for r in rs]):.2f} | "
				   f"{sum(r['missing_mm2'] for r in rs):.2f} | {sum(r['excess_mm2'] for r in rs):.2f} | "
				   f"{max(ms) if ms else ''} |")
	return "\n".join(out)


_TRI_COL = {ST.FUNDO_CERTO: (0, 70, 0), ST.FUNDO_PROV: (90, 160, 90), ST.INCERTO: (230, 200, 40),
			ST.PECA_PROV: (200, 110, 60), ST.PECA_CERTA: (140, 30, 30)}


def _diff_vis(rgb, gt, cand):
	v = (rgb.astype(np.float32) * 0.55).astype(np.uint8)
	v[gt & ~cand] = (255, 0, 255)      # missing: magenta
	v[cand & ~gt] = (0, 255, 255)      # excess: cyan
	cs, _ = cv2.findContours(gt.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
	cv2.drawContours(v, cs, -1, (255, 255, 255), 1)
	return v


def _label(img, text):
	img = img.copy()
	cv2.rectangle(img, (0, 0), (img.shape[1], 22), (0, 0, 0), -1)
	cv2.putText(img, text, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
	return img


def figure(data, fp, scenarios=("ii", "iii-in"), solvers=(("gc rgb it3", "grabcut", dict(_RGB, iters=3)),
														  ("gc L0 it2 (omissao)", "grabcut", {}),
														  ("ws cor L0", "watershed", dict(_L0, paisagem="cor")),
														  ("limiar seg.", "limiar", {"peso_l": 0.5, "limiar": 28.0}))):
	rows = []
	for d in data:
		for sc in scenarios:
			tr = scenario_strokes(sc, d["gt"], d["auto"], d["mmpp"])
			tri = ST.trimap(d["auto"], tr, d["mmpp"])
			tv = np.zeros(d["rgb"].shape, np.uint8)
			for k, c in _TRI_COL.items():
				tv[tri == k] = c
			tiles = [_label(d["rgb"], f"{d['pid']} scan"), _label(tv, f"trimap ({sc})")]
			for label, s, p in solvers:
				r = ST.resolver(d["rgb"], d["auto"], tr, d["mmpp"], solver=s, params=p, bg_lab=d["bg"])
				m = M.mask_metrics(d["gt"], r["mask"], d["mmpp"])
				tiles.append(_label(_diff_vis(d["rgb"], d["gt"], r["mask"]), f"{label} IoU {m['iou']:.3f} p95 {m['d_p95']:.2f}"))
			m = M.mask_metrics(d["gt"], d["auto"], d["mmpp"])
			tiles.append(_label(_diff_vis(d["rgb"], d["gt"], d["auto"]), f"indice IoU {m['iou']:.3f} p95 {m['d_p95']:.2f}"))
			h = max(t.shape[0] for t in tiles)
			tiles = [np.pad(t, ((0, h - t.shape[0]), (0, 4), (0, 0)), constant_values=255) for t in tiles]
			rows.append(np.hstack(tiles))
	w = max(r.shape[1] for r in rows)
	rows = [np.pad(r, ((0, 4), (0, w - r.shape[1]), (0, 0)), constant_values=255) for r in rows]
	Image.fromarray(np.vstack(rows)).save(fp, quality=88)


def main(argv=None):
	ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
	ap.add_argument("--project", default=os.path.join(REPO, "projects", "alpes"))
	ap.add_argument("--json")
	ap.add_argument("--fig")
	ap.add_argument("--reps", type=int, default=3)
	ap.add_argument("--sens", action="store_true", help="also the band / cleaning sensitivity of the default solver")
	a = ap.parse_args(argv)
	data = load(a.project)
	for d in data:
		print(f"{d['pid']}: recorte {d['rgb'].shape[1]} x {d['rgb'].shape[0]} px, origem {d['origem']}")
	rows = run(data, ("i", "ii", "iii", "iii-in", "iii-out"), VARIANTS, reps=a.reps, with_peel=True)
	print(table(rows))
	print()
	print(summary(rows))
	sens = []
	if a.sens:
		best = [DEFAULT, ("limiar (segmentador)", "limiar", {"peso_l": 0.5, "limiar": 28.0})]
		for banda in (0.5, 1.0, 1.5):
			for limp in (0.0, 0.3, 0.5):
				for r in run(data, ("i", "ii", "iii-out"), best, reps=1, banda_mm=banda, limpeza_mm=limp):
					if r["ms"] is not None:
						sens.append(dict(r, banda_mm=banda, limpeza_mm=limp))
		print()
		print("| banda mm | limpeza mm | cenário | variante | IoU média | p95 médio |")
		print("|---|---|---|---|---|---|")
		agg = {}
		for r in sens:
			agg.setdefault((r["banda_mm"], r["limpeza_mm"], r["scenario"], r["variant"]), []).append(r)
		for (b, l, sc, v), rs in agg.items():
			print(f"| {b} | {l} | {sc} | {v} | {np.mean([r['iou'] for r in rs]):.4f} | {np.mean([r['d_p95'] for r in rs]):.2f} |")
	if a.json:
		with open(a.json, "w", encoding="utf-8") as f:
			json.dump({"rows": rows, "sens": sens}, f, ensure_ascii=False, indent=1)
	if a.fig:
		figure(data, a.fig)


if __name__ == "__main__":
	main()
