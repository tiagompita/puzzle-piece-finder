"""Contact groups in segment_scan (interlocked / touching pieces): before vs after, on every project sheet.

Usage (from the repository root)::

	python tools/diagnostico/segmentacao/contactos.py [--project projects/alpes] [--sheets S0023,S0013]
		[--force] [--legacy-mode]

For each sheet of ``<project>/scans/S*.json`` runs ``segment_scan(normalize_rotation=False)``
twice: "antes" with ``split_contacts=False`` (the old Voronoi + band boundary) and "depois"
with the contact step on (the default). Per sheet: piece count (must not change), direct
contact pairs (bbox gap < 1 mm or contours within 1.2 mm, the criterion of
``src.segmentation._contact_groups``), pairs whose partition changed (IoU < 0.98 for either
member), pairs flagged ``contacto.confianca == 'baixa'``, whether the ``n_no_lote`` reading
order of the kept pieces changes, and the time of each run. Also follows the "bbox pairs"
of the stored project (padded bboxes of ``scans/S*.json`` with a gap < 1 mm).

``--legacy-mode`` only runs the "antes" segmentation (counts and timing). Results are cached
in ``$PPF_SCRATCH/contactos/<sid>.pkl`` (``--force`` recomputes). Writes
``docs/diagnostico/segmentacao/contactos_resultados.json`` and the montage
``docs/diagnostico/segmentacao/contactos_antes_depois.jpg`` (every changed pair, before |
after, <= 600 KB). Never writes into the project. Discussed in
docs/diagnostico/segmentacao/CONTACTOS.md.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import pickle
import sys
import time

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

from PIL import Image                                           # noqa: E402

from src import segmentation as SEG                             # noqa: E402
from src.ingest import MIN_PIECE_MM2, grid_order                # noqa: E402
from src.shape import analyse                                   # noqa: E402

OUT_DIR = os.path.join(ROOT, "docs", "diagnostico", "segmentacao")
FIG = os.path.join(OUT_DIR, "contactos_antes_depois.jpg")
RES = os.path.join(OUT_DIR, "contactos_resultados.json")
SAME_IOU = 0.98
BBOX_GAP_MM = 1.0
FIG_MAX_BYTES = 600 * 1024
TILE_H = 330


def scratch() -> str:
	d = os.path.join(os.environ.get("PPF_SCRATCH", os.path.join(ROOT, "scratch")), "contactos")
	os.makedirs(d, exist_ok=True)
	return d


def light(res: dict) -> dict:
	"""Picklable summary of a segment_scan result (contours, bboxes, flags)."""
	return {
		"count": res.get("count"),
		"mm_per_px": res.get("mm_per_px"),
		"error": res.get("error"),
		"pieces": [{"index": int(p["index"]), "contour": np.asarray(p["contour"]).reshape(-1, 2).astype(np.int32),
					"bbox": tuple(int(v) for v in p["bbox"]), "area_px": int(p["area_px"]),
					"is_cluster": bool(p["is_cluster"]), "refined": bool(p.get("refined")),
					"contacto": p.get("contacto")} for p in res.get("pieces", [])],
	}


def run_sheet(sid: str, scan: dict, force: bool, legacy_only: bool) -> dict:
	cache = os.path.join(scratch(), f"{sid}.pkl")
	if os.path.exists(cache) and not force:
		with open(cache, "rb") as f:
			d = pickle.load(f)
		if legacy_only or d.get("depois") is not None:
			return d
	fp = scan["file"] if os.path.isabs(scan["file"]) else os.path.join(ROOT, scan["file"])
	with Image.open(fp) as im:
		photo = im.convert("RGB")
	dpi = float(scan.get("dpi") or 300)
	t0 = time.time()
	before = light(SEG.segment_scan(photo, dpi=dpi, normalize_rotation=False, split_contacts=False))
	t_before = time.time() - t0
	after, t_after = None, None
	if not legacy_only:
		t0 = time.time()
		after = light(SEG.segment_scan(photo, dpi=dpi, normalize_rotation=False))
		t_after = time.time() - t0
	d = {"sid": sid, "file": scan["file"], "dpi": dpi, "antes": before, "depois": after,
		 "t_antes": t_before, "t_depois": t_after}
	with open(cache, "wb") as f:
		pickle.dump(d, f)
	return d


def filled(contour: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
	x0, y0, x1, y1 = box
	m = np.zeros((y1 - y0, x1 - x0), np.uint8)
	cv2.drawContours(m, [(contour - [x0, y0]).reshape(-1, 1, 2).astype(np.int32)], -1, 1, thickness=cv2.FILLED)
	return m > 0


def iou(c1: np.ndarray, c2: np.ndarray) -> float:
	pts = np.vstack([c1, c2])
	box = (int(pts[:, 0].min()) - 1, int(pts[:, 1].min()) - 1, int(pts[:, 0].max()) + 2, int(pts[:, 1].max()) + 2)
	a, b = filled(c1, box), filled(c2, box)
	u = float((a | b).sum())
	return float((a & b).sum()) / u if u else 1.0


def direct_pairs(pieces: list[dict], mmpp: float) -> list[tuple[int, int, float]]:
	"""Direct contact pairs ``(i, j, contour distance mm)`` with the criterion of segment_scan."""
	cs = [p["contour"] for p in pieces]
	ok = [True] * len(pieces)   # segment_scan groups every piece, clusters included
	boxes = [cv2.boundingRect(c.reshape(-1, 1, 2)) for c in cs]
	gap_px = SEG._CONTACT_BBOX_GAP_MM / mmpp
	near_px = 2 * SEG._CONTACT_DILATE_MM / mmpp
	out = []
	for i in range(len(cs)):
		for j in range(i + 1, len(cs)):
			if not (ok[i] and ok[j]):
				continue
			g = SEG._bbox_gap(boxes[i], boxes[j])
			if g > max(gap_px, near_px):
				continue
			dist = SEG._contour_distance(cs[i], cs[j])
			if g < gap_px or dist <= near_px:
				out.append((i, j, dist * mmpp))
	return out


def shape_txt(contour: np.ndarray, mmpp: float) -> dict:
	s = analyse(contour, mmpp)
	if not s.ok:
		return {"ok": False}
	return {"ok": True, "cls": s.cls, "tipos": "".join(s.types), "cordas_mm": [round(float(v), 2) for v in s.lens]}


def numbering(pieces: list[dict], mmpp: float) -> dict:
	kept = [p for p in pieces if p["area_px"] * mmpp * mmpp >= MIN_PIECE_MM2]
	order = grid_order([p["bbox"] for p in kept])
	return {p["index"]: n for p, n in zip(kept, order)}


def stored_bbox_pairs(scan_json: dict) -> list[tuple[int, int, int, int, float]]:
	"""``(idx_i, idx_j, n_i, n_j, gap_mm)`` of stored pieces whose padded bboxes are < 1 mm apart."""
	mmpp = 25.4 / float(scan_json.get("dpi") or 300)
	ps = scan_json["pieces"]
	out = []
	for a in range(len(ps)):
		for b in range(a + 1, len(ps)):
			g = SEG._bbox_gap(tuple(ps[a]["bbox"]), tuple(ps[b]["bbox"])) * mmpp
			if g < BBOX_GAP_MM:
				i, j = int(ps[a]["index_in_scan"]), int(ps[b]["index_in_scan"])
				ni, nj = ps[a].get("n_no_lote"), ps[b].get("n_no_lote")
				if i > j:
					i, j, ni, nj = j, i, nj, ni
				out.append((i, j, ni, nj, round(g, 2)))
	return out


def tile(rgb: np.ndarray, cts: list[np.ndarray], box: tuple[int, int, int, int], lines: list[str]) -> np.ndarray:
	"""Crop ``box`` of the scan (BGR, height ``TILE_H``) with the contours (red, blue) and a caption below."""
	x0, y0, x1, y1 = box
	img = np.ascontiguousarray(rgb[y0:y1, x0:x1, ::-1]).copy()
	s = TILE_H / img.shape[0]
	img = cv2.resize(img, (max(1, int(img.shape[1] * s)), TILE_H), interpolation=cv2.INTER_AREA)
	for c, col in zip(cts, ((0, 0, 255), (255, 0, 0), (0, 200, 255), (255, 0, 255))):
		q = ((c - [x0, y0]) * s).astype(np.int32).reshape(-1, 1, 2)
		cv2.polylines(img, [q], True, col, 2, cv2.LINE_AA)
	cap_w = max(img.shape[1], max(cv2.getTextSize(t, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0][0] for t in lines) + 8)
	out = np.full((TILE_H + 20 * len(lines) + 4, cap_w, 3), 255, np.uint8)
	out[:TILE_H, :img.shape[1]] = img
	for k, t in enumerate(lines):
		cv2.putText(out, t, (4, TILE_H + 16 + 20 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
	return out


def montage(items: list[np.ndarray], max_w: int = 2000) -> np.ndarray:
	"""Pack the pair images left to right in rows no wider than ``max_w`` (white gutters)."""
	if not items:
		return np.full((60, 400, 3), 255, np.uint8)
	rows, cur, cur_w = [], [], 0
	for it in items:
		if cur and cur_w + it.shape[1] + 12 > max_w:
			rows.append(cur)
			cur, cur_w = [], 0
		cur.append(it)
		cur_w += it.shape[1] + 12
	rows.append(cur)
	lines = []
	for r in rows:
		h = max(i.shape[0] for i in r)
		parts = []
		for i in r:
			parts.append(cv2.copyMakeBorder(i, 0, h - i.shape[0], 0, 12, cv2.BORDER_CONSTANT, value=(255, 255, 255)))
		line = np.hstack(parts)
		lines.append(line)
	w = max(l.shape[1] for l in lines)
	return np.vstack([cv2.copyMakeBorder(l, 6, 6, 6, 6 + w - l.shape[1], cv2.BORDER_CONSTANT, value=(255, 255, 255))
					  for l in lines])


def main(argv=None) -> int:
	ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
	ap.add_argument("--project", default=os.path.join("projects", "alpes"))
	ap.add_argument("--sheets", default="", help="lista separada por vírgulas (por omissão todas)")
	ap.add_argument("--force", action="store_true")
	ap.add_argument("--legacy-mode", action="store_true", help="só a segmentação antiga (split_contacts=False)")
	a = ap.parse_args(argv)
	proj = a.project if os.path.isabs(a.project) else os.path.join(ROOT, a.project)
	files = sorted(glob.glob(os.path.join(proj, "scans", "S*.json")))
	want = {s.strip() for s in a.sheets.split(",") if s.strip()}
	table, tiles, bbox_follow = [], [], []
	for fp in files:
		with open(fp, encoding="utf-8") as f:
			scan = json.load(f)
		sid = scan["id"]
		if want and sid not in want:
			continue
		d = run_sheet(sid, scan, a.force, a.legacy_mode)
		B = d["antes"]
		row = {"sid": sid, "file": scan["file"], "kind": scan.get("kind"), "n_antes": B["count"],
			   "t_antes_s": round(d["t_antes"], 1)}
		if a.legacy_mode or d["depois"] is None:
			table.append(row)
			print(sid, row, flush=True)
			continue
		A = d["depois"]
		mmpp = float(A["mm_per_px"])
		row.update({"n_depois": A["count"], "t_depois_s": round(d["t_depois"], 1),
					"contagem_igual": A["count"] == B["count"]})
		if A["count"] != B["count"]:
			row.update({"pares": None})
			table.append(row)
			print("CONTAGEM MUDOU", sid, B["count"], A["count"], flush=True)
			continue
		pa, pb = A["pieces"], B["pieces"]
		ious = [iou(pa[k]["contour"], pb[k]["contour"]) for k in range(len(pa))]
		pairs = direct_pairs(pb, mmpp)
		num_b, num_a = numbering(pb, mmpp), numbering(pa, mmpp)
		pair_rows = []
		rgb = None
		for i, j, dist_b in pairs:
			ca, cb = pa[i].get("contacto") or {}, pa[j].get("contacto") or {}
			changed = min(ious[i], ious[j]) < SAME_IOU
			pr = {"i": i, "j": j, "n_i": num_b.get(i), "n_j": num_b.get(j), "dist_antes_mm": round(dist_b, 2),
				  "dist_depois_mm": round(SEG._contour_distance(pa[i]["contour"], pa[j]["contour"]) * mmpp, 2),
				  "metodo": ca.get("metodo"), "confianca": ca.get("confianca"), "alterado": bool(changed),
				  "iou": [round(ious[i], 4), round(ious[j], 4)], "flag_ok": bool(ca) and bool(cb)}
			if changed:
				pr["forma_antes"] = [shape_txt(pb[i]["contour"], mmpp), shape_txt(pb[j]["contour"], mmpp)]
				pr["forma_depois"] = [shape_txt(pa[i]["contour"], mmpp), shape_txt(pa[j]["contour"], mmpp)]
				if rgb is None:
					fpath = scan["file"] if os.path.isabs(scan["file"]) else os.path.join(ROOT, scan["file"])
					with Image.open(fpath) as im:
						rgb = np.asarray(im.convert("RGB"))
				pts = np.vstack([pb[i]["contour"], pb[j]["contour"], pa[i]["contour"], pa[j]["contour"]])
				m = int(round(2.0 / mmpp))
				H, W = rgb.shape[:2]
				box = (max(0, int(pts[:, 0].min()) - m), max(0, int(pts[:, 1].min()) - m),
					   min(W, int(pts[:, 0].max()) + m), min(H, int(pts[:, 1].max()) + m))
				lab = f"{sid} #{num_b.get(i, 'i' + str(i))}/#{num_b.get(j, 'i' + str(j))}"
				fa, fd = pr["forma_antes"], pr["forma_depois"]
				t1 = tile(rgb, [pb[i]["contour"], pb[j]["contour"]], box,
						  [f"{lab} ANTES", f"{fa[0].get('tipos', 'sem 4 cantos')} / {fa[1].get('tipos', 'sem 4 cantos')}"])
				t2 = tile(rgb, [pa[i]["contour"], pa[j]["contour"]], box,
						  [f"DEPOIS {pr['metodo']} {pr['confianca']}",
						   f"{fd[0].get('tipos', 'sem 4 cantos')} / {fd[1].get('tipos', 'sem 4 cantos')}"])
				h = max(t1.shape[0], t2.shape[0])
				t1 = cv2.copyMakeBorder(t1, 0, h - t1.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(255, 255, 255))
				t2 = cv2.copyMakeBorder(t2, 0, h - t2.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(255, 255, 255))
				tiles.append(np.hstack([t1, np.full((h, 6, 3), 255, np.uint8), t2]))
			pair_rows.append(pr)
		changed_alone = [k for k in range(len(pa)) if ious[k] < SAME_IOU
						 and not any(k in (p["i"], p["j"]) for p in pair_rows)]
		row.update({
			"pares": len(pair_rows),
			"pares_fisicos_watershed": sum(1 for p in pair_rows if p["metodo"] == "watershed"),
			"pares_alterados": sum(1 for p in pair_rows if p["alterado"]),
			"pares_baixa": sum(1 for p in pair_rows if p["confianca"] == "baixa"),
			"pecas_alteradas_fora_de_pares": changed_alone,
			"numeracao_igual": num_a == num_b,
			"numeracao_diferencas": {str(k): [num_b.get(k), num_a.get(k)] for k in sorted(set(num_a) | set(num_b))
									  if num_a.get(k) != num_b.get(k)},
			"detalhe": pair_rows,
		})
		direct = {(p["i"], p["j"]): p for p in pair_rows}
		for i, j, ni, nj, g in stored_bbox_pairs(scan):
			p = direct.get((i, j))
			bbox_follow.append({"sid": sid, "n": [ni, nj], "idx": [i, j], "gap_bbox_mm": g, "detetado": p is not None,
								"dist_antes_mm": p["dist_antes_mm"] if p else round(
									SEG._contour_distance(pb[i]["contour"], pb[j]["contour"]) * mmpp, 2),
								"metodo": p["metodo"] if p else None, "alterado": p["alterado"] if p else False,
								"confianca": p["confianca"] if p else None})
		table.append(row)
		print(f"{sid}: n {B['count']}->{A['count']} pares {row['pares']} (watershed {row['pares_fisicos_watershed']}) "
			  f"alterados {row['pares_alterados']} baixa {row['pares_baixa']} numeracao_igual {row['numeracao_igual']} "
			  f"t {row['t_antes_s']}/{row['t_depois_s']} s", flush=True)
	if a.legacy_mode:
		return 0
	os.makedirs(OUT_DIR, exist_ok=True)
	img = montage(tiles)
	q = 85
	while True:
		ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
		if len(buf) <= FIG_MAX_BYTES or q <= 40:
			if len(buf) > FIG_MAX_BYTES:
				img = cv2.resize(img, None, fx=0.75, fy=0.75, interpolation=cv2.INTER_AREA)
				q = 85
				continue
			break
		q -= 5
	buf.tofile(FIG)
	tot = {k: sum((r.get(k) or 0) for r in table) for k in ("pares", "pares_fisicos_watershed", "pares_alterados",
															  "pares_baixa")}
	tot["folhas"] = len(table)
	tot["contagem_mudou"] = [r["sid"] for r in table if not r.get("contagem_igual", True)]
	tot["numeracao_mudou"] = [r["sid"] for r in table if not r.get("numeracao_igual", True)]
	tot["t_antes_s"] = round(sum(r["t_antes_s"] for r in table), 1)
	tot["t_depois_s"] = round(sum(r.get("t_depois_s") or 0 for r in table), 1)
	bb = {"total": len(bbox_follow), "detetados": sum(b["detetado"] for b in bbox_follow),
		  "watershed": sum(b["metodo"] == "watershed" for b in bbox_follow),
		  "alterados": sum(bool(b["alterado"]) for b in bbox_follow),
		  "dist_le_0_3mm": sum(b["dist_antes_mm"] <= 0.3 for b in bbox_follow)}
	with open(RES, "w", encoding="utf-8") as f:
		json.dump({"totais": tot, "pares_bbox_projeto": bb, "folhas": table, "bbox_pares": bbox_follow}, f,
				  ensure_ascii=False, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
	print("TOTAIS", tot)
	print("PARES BBOX DO PROJETO", bb)
	print("figura", FIG, os.path.getsize(FIG) // 1024, "KB;", len(tiles), "pares alterados")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
