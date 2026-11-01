"""Ingest a flatbed scan of loose pieces into a project (``python -m src.ingest``).

Usage::

	python -m src.ingest <scan.jpg> --lote N [--dpi 300] [--kind soltas] [--known-cells gt.json]
		[--montado pNN | --blocos pNN [--no-auto-anchor]] [--project projects/alpes] [--profile projects/alpes/puzzle.json]

Pipeline (:func:`ingest_scan`): ``segment_scan`` (crops kept in the scan frame,
``normalize_rotation=False``, so crop, contour and Shape share one frame) → fragments
rejected (area < ``MIN_PIECE_MM2``) → ``is_cluster`` or area > ``DOUBLE_AREA_FACTOR`` ×
median flagged ``objeto_duplo`` → ``shape.analyse`` → :func:`grid_order` numbering
(``n_no_lote``, continuing the bag's numbering if the bag already has pieces) → RGBA crop in
``crops/`` → ``mean_lab`` → numbered overlay ``overlays/<scan>.jpg`` (the sheet kept with
the bag).

``--known-cells gt.json``: ``{"cells": [{"index": n, "cell": [l, c], "theta_deg": opt}],
"theta_deg": opt}`` where ``index`` (alias ``n``) is the number printed on the overlay
(``n_no_lote``). Each such piece is placed (origin ``gt``) if its cell is full in the last
registered photo, otherwise it becomes ``posicao_conhecida``.

``--montado/--blocos pNN`` delegate to ``src.legacy.ingest_page``; ``--no-auto-anchor`` leaves
every section unanchored (anchor later with ``legacy.solve_project_sections``, which uses the
twins between pages).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

import numpy as np

__all__ = ["MIN_PIECE_MM2", "DOUBLE_AREA_FACTOR", "grid_order", "local_mean_lab", "ingest_scan",
		   "draw_overlay", "open_project", "add_project_args", "main"]

MIN_PIECE_MM2 = 150.0        # below this a component is a fragment (strip remnant, dust), never a piece
DOUBLE_AREA_FACTOR = 1.6     # area > 1.6 x median of the scan -> objeto_duplo (two mated pieces?)
ROW_BREAK_FRAC = 0.5         # grid_order: new row when the centre y jumps > 0.5 x median bbox height
OVERLAY_MAX_W = 2400         # px, width of the saved overlay
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PROJECT = os.path.join("projects", "alpes")
DEFAULT_PROFILE = os.path.join(REPO, "projects", "alpes", "puzzle.json")


# ---------------------------------------------------------------- pure helpers
def grid_order(bboxes) -> list:
	"""Reading-order number (1-based) of each bbox ``(x, y, w, h)``: rows by centre y (a new row
	when the jump exceeds ``ROW_BREAK_FRAC`` × median height), left to right within a row.

	Promoted from ``tools/diagnostico/gemeos/segcache.grid_order``; returns ``n[i]`` for input i.
	"""
	b = np.asarray(bboxes, float).reshape(-1, 4)
	if len(b) == 0:
		return []
	cy = b[:, 1] + b[:, 3] / 2
	cx = b[:, 0] + b[:, 2] / 2
	o = np.argsort(cy, kind="stable")
	hmed = float(np.median(b[:, 3]))
	rows, cur = [], [int(o[0])]
	for i in o[1:]:
		if cy[i] - cy[cur[-1]] > ROW_BREAK_FRAC * hmed:
			rows.append(cur)
			cur = [int(i)]
		else:
			cur.append(int(i))
	rows.append(cur)
	n = [0] * len(b)
	k = 0
	for r in rows:
		for i in sorted(r, key=lambda j: cx[j]):
			k += 1
			n[i] = k
	return n


def local_mean_lab(rgba: np.ndarray) -> list:
	"""Mean CIE Lab (L 0..100, float OpenCV conversion) over the opaque pixels of an RGBA crop."""
	import cv2
	a = np.asarray(rgba)
	m = a[..., 3] > 127
	if not m.any():
		return [float("nan")] * 3
	lab = cv2.cvtColor(a[..., :3].astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB)
	return [round(float(v), 2) for v in lab[m].mean(0)]


def _mean_lab(rgba: np.ndarray) -> list:
	try:
		from src.locate import piece_mean_lab
		v = piece_mean_lab(rgba)
		return [round(float(x), 2) for x in np.asarray(v, float).reshape(-1)[:3]]
	except Exception:  # noqa: BLE001 - src.locate optional / different signature: local fallback
		return local_mean_lab(rgba)


def draw_overlay(rgb: np.ndarray, items: list, title: str = "") -> np.ndarray:
	"""Scan with each piece contour and a large number; ``items`` = [{contour, n, colour}] (RGB)."""
	import cv2
	img = np.ascontiguousarray(rgb[..., ::-1]).copy()
	H, W = img.shape[:2]
	s = min(1.0, OVERLAY_MAX_W / float(W))
	if s < 1.0:
		img = cv2.resize(img, (int(W * s), int(H * s)), interpolation=cv2.INTER_AREA)
	lw = max(2, int(round(img.shape[1] / 600)))
	fs = img.shape[1] / 900.0
	for it in items:
		cnt = (np.asarray(it["contour"], float).reshape(-1, 2) * s).astype(np.int32)
		col = tuple(int(v) for v in it.get("colour", (0, 255, 255))[::-1])
		cv2.polylines(img, [cnt], True, col, lw, cv2.LINE_AA)
		txt = str(it["n"])
		(tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, fs, 3 * lw)
		cx, cy = cnt.mean(0)
		org = (int(cx - tw / 2), int(cy + th / 2))
		cv2.putText(img, txt, org, cv2.FONT_HERSHEY_SIMPLEX, fs, (0, 0, 0), 3 * lw + 4, cv2.LINE_AA)
		cv2.putText(img, txt, org, cv2.FONT_HERSHEY_SIMPLEX, fs, (255, 255, 255), 3 * lw, cv2.LINE_AA)
	if title:
		cv2.putText(img, title, (20, int(40 * fs) + 10), cv2.FONT_HERSHEY_SIMPLEX, fs * 0.8, (0, 0, 0), 2 * lw + 4,
					cv2.LINE_AA)
		cv2.putText(img, title, (20, int(40 * fs) + 10), cv2.FONT_HERSHEY_SIMPLEX, fs * 0.8, (255, 255, 255), 2 * lw,
					cv2.LINE_AA)
	return img


# ---------------------------------------------------------------- service
def ingest_scan(project, scan_path: str, lote: Optional[int], *, dpi: float = 300, kind: str = "soltas",
				known_cells: Optional[dict] = None, segment=None) -> dict:
	"""Segment ``scan_path`` and add its pieces to ``project`` (then ``project.save()``).

	Returns ``{scan_id, pieces: [ids], numbers: {id: n_no_lote}, rejected: [...], double: [ids],
	overlay, known: [...], n_segmented}`` or ``{'error': str}``. ``segment`` overrides
	``segment_scan`` (tests).
	"""
	import cv2
	from PIL import Image
	from src.segmentation import piece_to_rgba
	from src.shape import analyse

	if not os.path.exists(scan_path):
		return {"error": f"scan não encontrado: {scan_path}"}
	if segment is None:
		from src.segmentation import segment_scan as segment
	with Image.open(scan_path) as im:
		photo = im.convert("RGB")
	res = segment(photo, dpi=dpi, normalize_rotation=False)
	if "error" in res:
		return {"error": f"segment_scan: {res['error']}"}
	mmpp = float(res.get("mm_per_px") or 25.4 / dpi)
	raw = res["pieces"]
	rejected, kept = [], []
	for p in raw:
		area = float(p["area_px"]) * mmpp * mmpp
		if area < MIN_PIECE_MM2:
			rejected.append({"index": int(p["index"]), "area_mm2": round(area, 1),
							 "touches_strip": bool(p.get("touches_strip")), "reason": f"área < {MIN_PIECE_MM2:g} mm²"})
		else:
			kept.append((p, area))
	med = float(np.median([a for _, a in kept])) if kept else 0.0
	order = grid_order([p["bbox"] for p, _ in kept])
	sid = project.add_scan(scan_path, dpi=dpi, lote=lote, kind=kind,
						   meta={"n_segmented": len(raw), "n_rejected": len(rejected), "method": res.get("method"),
								 "mm_per_px": mmpp})
	n0 = max([q.n_no_lote or 0 for q in project.pieces.values() if lote is not None and q.lote == lote
			  and q.scan_id != sid] or [0])
	os.makedirs(project.p("crops"), exist_ok=True)
	ids, numbers, double, items = [], {}, [], []
	for (p, area), n in sorted(zip(kept, order), key=lambda t: t[1]):
		cnt = np.asarray(p["contour"]).reshape(-1, 2)
		shape = analyse(cnt, mmpp)
		dup = bool(p.get("is_cluster")) or area > DOUBLE_AREA_FACTOR * med
		rgba = np.asarray(piece_to_rgba(p["image"], p["mask"]))
		pid_next = f"P{int(project.meta['next_ids']['P']):04d}"
		crop_rel = f"crops/{pid_next}.png"
		Image.fromarray(np.ascontiguousarray(rgba)).save(project.p(crop_rel))
		pid = project.add_piece(sid, {
			"index_in_scan": int(p["index"]), "n_no_lote": n0 + n, "shape": shape, "contour": cnt,
			"bbox": [int(v) for v in p["bbox"]], "crop_path": crop_rel, "mean_lab": _mean_lab(rgba),
			"area_mm2": round(area, 2),
			"flags": {"touches_frame": bool(p.get("touches_frame")), "touches_strip": bool(p.get("touches_strip")),
					  "is_cluster": bool(p.get("is_cluster")), "objeto_duplo": dup},
		})
		assert pid == pid_next, (pid, pid_next)
		ids.append(pid)
		numbers[pid] = n0 + n
		if dup:
			double.append(pid)
		colour = (255, 0, 255) if dup else ((255, 160, 0) if shape.n_flat else (0, 255, 255))
		items.append({"contour": cnt, "n": n0 + n, "colour": colour})
	ov = draw_overlay(np.asarray(photo), items, title=f"{sid} lote {lote}: {len(ids)} pecas")
	os.makedirs(project.p("overlays"), exist_ok=True)
	ov_path = project.p("overlays", f"{sid}.jpg")
	cv2.imencode(".jpg", ov, [cv2.IMWRITE_JPEG_QUALITY, 88])[1].tofile(ov_path)

	known = []
	if known_cells:
		known = _apply_known_cells(project, ids, numbers, known_cells)
	project.save()
	return {"scan_id": sid, "pieces": ids, "numbers": numbers, "rejected": rejected, "double": double,
			"overlay": ov_path, "known": known, "n_segmented": len(raw)}


def _apply_known_cells(project, ids: list, numbers: dict, gt: dict) -> list:
	by_n = {numbers[pid]: pid for pid in ids}
	photo = project.last_photo()
	out = []
	for e in gt.get("cells", []):
		n = int(e.get("index", e.get("n")))
		cell = (int(e["cell"][0]), int(e["cell"][1]))
		theta = e.get("theta_deg", gt.get("theta_deg"))
		pid = by_n.get(n)
		if pid is None:
			out.append({"n": n, "cell": cell, "error": "número não existe neste scan"})
			continue
		full = photo is not None and photo.value(*cell) == 1
		try:
			if full:
				project.place(pid, cell, origin="gt", theta_deg=theta)
			else:
				project.set_position_known(pid, cell, origin="gt", theta_deg=theta)
			out.append({"n": n, "piece": pid, "cell": cell, "estado": project.piece(pid).estado})
		except ValueError as err:
			out.append({"n": n, "piece": pid, "cell": cell, "error": str(err)})
	return out


# ---------------------------------------------------------------- CLI
def add_project_args(ap: argparse.ArgumentParser) -> None:
	ap.add_argument("--project", default=DEFAULT_PROJECT, help="pasta do projeto (projects/<id>)")
	ap.add_argument("--profile", default=DEFAULT_PROFILE, help="puzzle.json usado se o projeto ainda não existir")


def open_project(args):
	"""Open ``args.project`` (created from ``args.profile`` if it has no project.json)."""
	from src.state import Project
	created = not os.path.exists(os.path.join(args.project, "project.json"))
	pr = Project.open_or_create(args.project, args.profile)
	if created:
		print(f"projeto criado em {pr.path} (perfil {args.profile})")
	return pr


def main(argv=None) -> int:
	ap = argparse.ArgumentParser(prog="python -m src.ingest", description="Ingere um scan de peças soltas num projeto.")
	ap.add_argument("scan")
	ap.add_argument("--lote", type=int, default=None, help="número do saco (= lote)")
	ap.add_argument("--dpi", type=float, default=300)
	ap.add_argument("--kind", default="soltas")
	ap.add_argument("--known-cells", default=None, help="gt.json {cells: [{index, cell: [l, c]}], theta_deg}")
	g = ap.add_mutually_exclusive_group()
	g.add_argument("--montado", default=None, metavar="pNN")
	g.add_argument("--blocos", default=None, metavar="pNN")
	ap.add_argument("--no-auto-anchor", action="store_true",
					help="páginas do legado: não ancorar pela própria página (ancorar depois pela solução conjunta)")
	add_project_args(ap)
	args = ap.parse_args(argv)
	try:
		pr = open_project(args)
	except ValueError as e:
		print(f"erro: {e}")
		return 1
	if args.montado or args.blocos:
		try:
			from src import legacy
		except ImportError:
			print("erro: src/legacy.py ainda não existe (passo 4 do plano M10+M12); páginas do legado não podem ser ingeridas")
			return 1
		kind, page = ("montado", args.montado) if args.montado else ("blocos", args.blocos)
		r = legacy.ingest_page(pr, args.scan, kind, page, auto_anchor=not args.no_auto_anchor)
		if isinstance(r, dict) and "error" in r:
			print(f"erro: {r['error']}")
			return 1
		pr.save()
		print(r)
		return 0
	if args.lote is None:
		print("erro: --lote é obrigatório para peças soltas")
		return 1
	gt = None
	if args.known_cells:
		with open(args.known_cells, encoding="utf-8") as f:
			gt = json.load(f)
	r = ingest_scan(pr, args.scan, args.lote, dpi=args.dpi, kind=args.kind, known_cells=gt)
	if "error" in r:
		print(f"erro: {r['error']}")
		return 1
	print(f"{r['scan_id']} lote {args.lote}: {len(r['pieces'])} peças (segmentadas {r['n_segmented']}, "
		  f"fragmentos rejeitados {len(r['rejected'])}, objeto_duplo {len(r['double'])})")
	for pid in r["pieces"]:
		p = pr.piece(pid)
		fl = ",".join(k for k, v in p.flags.items() if v)
		print(f"  #{p.n_no_lote:>3} {pid} cls {p.cls or '-':4s} F={p.n_flat} área {p.area_mm2:6.1f} mm² "
			  f"cordas {[round(x, 1) for x in p.chords_mm]} {fl}")
	for e in r["rejected"]:
		print(f"  rejeitado: índice {e['index']} ({e['reason']}, {e['area_mm2']} mm²)")
	for e in r["known"]:
		print(f"  gt: {e}")
	print(f"overlay: {r['overlay']}")
	bad = pr.check_invariants(disk=True)
	if bad:
		print("INVARIANTES VIOLADAS: " + "; ".join(bad))
		return 1
	return 0


if __name__ == "__main__":
	sys.exit(main())
