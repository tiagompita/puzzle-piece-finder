"""Contorno sugerido pela gémea: quão bom ponto de partida é? (só leitura; CONVENCAO.md §4)

Mede :func:`src.shape.register_rigid` (a silhueta da gémea rodada por ``twin_rotation_deg`` e registada
sobre a silhueta própria) em três conjuntos:

1. **pares gémeos colocados** de ``projects/<id>`` com silhueta automática dos dois lados (sem
   ``manual_override``): distância de cada ponto da gémea registada à fronteira própria (média, p95, máx.,
   em mm) e RMS do registo; «piora» quando a d_mean > ``--pior-mm`` (0,6);
2. **P0651/P0657** (S0020) contra a GT do Photoshop, com as gémeas P0233/P0234 (S0009): a sugestão fica
   mais perto da GT do que o automático?
3. **E-sym** (20 pares A1↔B2 dos scans de 2026-10-30, ``segment_scan`` direto; salta se os scans faltarem).

	python tools/diagnostico/editor/gemea_sugestao.py --project projects/alpes [--json out.json] [--max N]
"""

import argparse
import json
import os
import sys

import cv2
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO)

from src import maskcmp as MC  # noqa: E402
from src import overrides as OV  # noqa: E402
from src.shape import register_rigid  # noqa: E402
from src.state import Project  # noqa: E402

GT_DIR = os.path.join(REPO, "docs", "diagnostico", "reports", "R0011_R0012_manual")
GT = {"P0651": ("manual_A_photoshop.png", "P0233"), "P0657": ("manual_B_photoshop.png", "P0234")}
ESYM = {"A1": "images/pieces/coluna5-24_300dpi_folhaA.jpg", "B2": "images/pieces/coluna5-24_folhaB_300dpi_rot180.jpg"}


def dist_to_boundary(pts_mm: np.ndarray, poly_mm: np.ndarray) -> np.ndarray:
	"""Distance (mm) of every point to the polyline ``poly_mm`` (closed), by dense resampling."""
	q = OV.resample_closed(poly_mm, 0.05)
	out = np.empty(len(pts_mm))
	block = 2000
	for i in range(0, len(pts_mm), block):
		d = pts_mm[i:i + block, None, :] - q[None, :, :]
		out[i:i + block] = np.sqrt(np.einsum("ijk,ijk->ij", d, d).min(1))
	return out


def measure_pair(own_mm, twin_mm, rot) -> dict:
	r = register_rigid(twin_mm, own_mm, rotation_deg=rot)
	d = dist_to_boundary(r["points_mm"], own_mm)
	return {"rms_mm": round(r["rms_mm"], 3), "rms_cantos_mm": None if r["rms_cantos_mm"] is None else round(r["rms_cantos_mm"], 3),
			"d_mean": round(float(d.mean()), 3), "d_p95": round(float(np.percentile(d, 95)), 3), "d_max": round(float(d.max()), 3),
			"ok": r["ok"]}


def placed_pairs(pr, max_n=None) -> list:
	rows = []
	rot = pr.profile.twin_rotation_deg()
	seen = set()
	for p in sorted(pr.pieces.values(), key=lambda q: q.id):
		if p.estado != "colocada" or p.celula is None or OV.is_manual(p):
			continue
		tw = pr.profile.twin(*p.celula)
		occ = pr.board[tw] if tw else None
		if not occ or occ.get("estado") != "colocada" or not occ.get("peca_id"):
			continue
		q = pr.piece(occ["peca_id"])
		if OV.is_manual(q) or frozenset((p.id, q.id)) in seen:
			continue
		seen.add(frozenset((p.id, q.id)))
		co, ct = pr.contour_px(p.id), pr.contour_px(q.id)
		if co is None or ct is None:
			continue
		m = measure_pair(np.asarray(co, float) * OV._mmpp(pr, p.scan_id), np.asarray(ct, float) * OV._mmpp(pr, q.scan_id), rot)
		m.update(piece=p.id, gemea=q.id, celula=list(p.celula), zona=pr.profile.zone_of(*p.celula) if hasattr(pr.profile, "zone_of") else None,
				 contacto=bool((p.flags or {}).get("contacto") or (q.flags or {}).get("contacto")),
				 suspeita=bool((p.flags or {}).get("suspeita_recorte") or (q.flags or {}).get("suspeita_recorte")))
		rows.append(m)
		if max_n and len(rows) >= max_n:
			break
	return rows


def gt_pairs(pr) -> list:
	rows = []
	rot = pr.profile.twin_rotation_deg()
	for pid, (fn, tid) in GT.items():
		fp = os.path.join(GT_DIR, fn)
		if not os.path.exists(fp) or pid not in pr.pieces or tid not in pr.pieces:
			continue
		p, t = pr.piece(pid), pr.piece(tid)
		a = cv2.imread(fp, cv2.IMREAD_UNCHANGED)
		gt_full = a[..., 3] > 127
		n, cc, st, _ = cv2.connectedComponentsWithStats(gt_full.astype(np.uint8), connectivity=8)
		gt_full = cc == 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
		cnts, _ = cv2.findContours(gt_full.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
		gt_px = max(cnts, key=cv2.contourArea).reshape(-1, 2).astype(float)
		mm_o, mm_t = OV._mmpp(pr, p.scan_id), OV._mmpp(pr, t.scan_id)
		own = np.asarray(pr.contour_px(pid), float) * mm_o
		twin = np.asarray(pr.contour_px(tid), float) * mm_t
		gt_mm = gt_px * mm_o
		r = register_rigid(twin, own, rotation_deg=rot)
		d_sug = dist_to_boundary(r["points_mm"], gt_mm)
		d_auto = dist_to_boundary(OV.resample_closed(own, 0.5), gt_mm)
		# area terms in px: fill the registered polygon in the scan frame
		H, W = gt_full.shape
		sug_mask = MC.fill_contour(r["points_mm"] / mm_o, (H, W))
		auto_mask = MC.fill_contour(np.asarray(pr.contour_px(pid), float), (H, W))
		ms, ma = MC.mask_metrics(gt_full, sug_mask, mm_o), MC.mask_metrics(gt_full, auto_mask, mm_o)
		rows.append({"piece": pid, "gemea": tid, "rms_mm": round(r["rms_mm"], 3),
					 "sugestao_vs_gt": {"d_mean": round(float(d_sug.mean()), 3), "d_p95": round(float(np.percentile(d_sug, 95)), 3),
										"iou": round(ms["iou"], 3), "falta_mm2": round(ms["missing_mm2"], 1), "a_mais_mm2": round(ms["excess_mm2"], 1)},
					 "auto_vs_gt": {"d_mean": round(float(d_auto.mean()), 3), "d_p95": round(float(np.percentile(d_auto, 95)), 3),
									"iou": round(ma["iou"], 3), "falta_mm2": round(ma["missing_mm2"], 1), "a_mais_mm2": round(ma["excess_mm2"], 1)}})
	return rows


def esym_pairs(pr) -> list:
	"""A1 ↔ B2 twins (position GT: piece i of A1 is the twin of piece i of B2 after sorting by x)."""
	from PIL import Image
	from src.segmentation import segment_scan
	paths = {k: os.path.join(REPO, v) for k, v in ESYM.items()}
	if not all(os.path.exists(v) for v in paths.values()):
		return []
	segs = {}
	for k, v in paths.items():
		with Image.open(v) as im:
			res = segment_scan(im.convert("RGB"), dpi=300, normalize_rotation=False)
		mmpp = float(res.get("mm_per_px") or 25.4 / 300)
		pcs = sorted((p for p in res["pieces"] if float(p["area_px"]) * mmpp * mmpp > 150), key=lambda p: p["bbox"][0])
		segs[k] = [(np.asarray(p["contour"], float).reshape(-1, 2) * mmpp) for p in pcs]
	a, b = segs["A1"], segs["B2"]
	# pairing by mutual nearest neighbour in free shape distance (E-sym: top-1 20/20), not by position
	from src.shape import analyse, free_dist
	sa = [analyse(c, 1.0) for c in a]
	sb = [analyse(c, 1.0) for c in b]
	D = np.array([[free_dist(x, y)[0] for y in sb] for x in sa])
	rot = pr.profile.twin_rotation_deg()
	rows = []
	for i in range(len(a)):
		j = int(np.argmin(D[i]))
		if int(np.argmin(D[:, j])) != i:
			continue
		m = measure_pair(a[i], b[j], rot)
		m.update(piece=f"A1#{i}", gemea=f"B2#{j}", free_mm=round(float(D[i, j]), 3))
		rows.append(m)
	return rows


def summary(rows, key):
	v = np.array([r[key] for r in rows if key in r and r[key] is not None], float)
	return {"n": int(len(v)), "mediana": round(float(np.median(v)), 3), "p95": round(float(np.percentile(v, 95)), 3), "max": round(float(v.max()), 3)} if len(v) else {"n": 0}


def main(argv=None) -> int:
	ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
	ap.add_argument("--project", required=True)
	ap.add_argument("--json", default=None)
	ap.add_argument("--max", type=int, default=None)
	ap.add_argument("--pior-mm", type=float, default=0.6)
	ap.add_argument("--sem-esym", action="store_true")
	a = ap.parse_args(argv)
	pr = Project.open(a.project)
	rows = placed_pairs(pr, a.max)
	print(f"## Pares gémeos colocados com silhueta automática ({len(rows)})")
	for k in ("d_mean", "d_p95", "d_max", "rms_mm"):
		print(f"- {k}: {summary(rows, k)}")
	bad = [r for r in rows if r["d_mean"] > a.pior_mm]
	print(f"- piora (d_mean > {a.pior_mm}): {len(bad)}: " + "; ".join(f"{r['piece']}↔{r['gemea']} {r['celula']} d_mean {r['d_mean']} contacto {r['contacto']} suspeita {r['suspeita']}" for r in bad[:20]))
	zones = sorted({str(r["zona"]) for r in rows})
	for z in zones:
		zr = [r for r in rows if str(r["zona"]) == z]
		print(f"  - zona {z}: n {len(zr)}, d_mean mediana {summary(zr, 'd_mean')['mediana']}, p95 das d_p95 {summary(zr, 'd_p95')['p95']}")
	gt = gt_pairs(pr)
	print("\n## P0651/P0657 contra a GT: sugestão da gémea vs automático")
	for g in gt:
		print(f"- {g['piece']} ← {g['gemea']} (RMS {g['rms_mm']}): sugestão d_mean {g['sugestao_vs_gt']['d_mean']} / p95 {g['sugestao_vs_gt']['d_p95']} / IoU {g['sugestao_vs_gt']['iou']} "
			  f"(falta {g['sugestao_vs_gt']['falta_mm2']}, a mais {g['sugestao_vs_gt']['a_mais_mm2']}); automático d_mean {g['auto_vs_gt']['d_mean']} / p95 {g['auto_vs_gt']['d_p95']} / IoU {g['auto_vs_gt']['iou']} "
			  f"(falta {g['auto_vs_gt']['falta_mm2']}, a mais {g['auto_vs_gt']['a_mais_mm2']})")
	es = [] if a.sem_esym else esym_pairs(pr)
	if es:
		print(f"\n## E-sym A1↔B2 ({len(es)} pares)")
		for k in ("d_mean", "d_p95", "rms_mm"):
			print(f"- {k}: {summary([r for r in es if 'erro' not in r], k)}")
		for r in es:
			if "erro" in r:
				print("- erro:", r["erro"])
	if a.json:
		with open(a.json, "w", encoding="utf-8") as f:
			json.dump({"pares_colocados": rows, "gt": gt, "esym": es, "pior_mm": a.pior_mm}, f, ensure_ascii=False, indent=1)
		print(f"\njson: {a.json}")
	return 0


if __name__ == "__main__":
	sys.exit(main())
