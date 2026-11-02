"""Ingest a flatbed scan of loose pieces into a project (``python -m src.ingest``).

Usage::

	python -m src.ingest <scan.jpg> --lote N [--dpi 300] [--kind soltas] [--known-cells gt.json]
		[--montado pNN | --blocos pNN [--no-auto-anchor]] [--project projects/alpes] [--profile projects/alpes/puzzle.json]

Pipeline (:func:`ingest_scan`): ``segment_scan`` (crops kept in the scan frame,
``normalize_rotation=False``, so crop, contour and Shape share one frame) → fragments
rejected (area < ``MIN_PIECE_MM2``) → ``is_cluster`` or area > ``DOUBLE_AREA_FACTOR`` ×
median flagged ``objeto_duplo``, ``contacto`` (interlocked/touching pieces re-partitioned by
``segment_scan``; ``com`` = ``index_in_scan`` of the others) copied into ``flags`` and drawn in red on the
overlay when ``confianca == 'baixa'`` → ``shape.analyse`` → :func:`grid_order` numbering
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
		   "draw_overlay", "sheet_overlay", "write_overlay", "open_project", "add_project_args", "main"]

MIN_PIECE_MM2 = 150.0        # below this a component is a fragment (strip remnant, dust), never a piece
DOUBLE_AREA_FACTOR = 1.6     # area > 1.6 x median of the scan -> objeto_duplo (two mated pieces?)
ROW_BREAK_FRAC = 0.5         # grid_order: new row when the centre y jumps > 0.5 x median bbox height
OVERLAY_MAX_W = 2400         # px, width of the saved overlay
HIGHLIGHT_RGB = (255, 191, 0)  # amber: the highlighted piece of sheet_overlay
COL_DOUBLE = (255, 0, 255)     # objeto_duplo
COL_BORDER = (255, 160, 0)     # piece with a flat side
COL_PIECE = (0, 255, 255)
COL_CONTACT_LOW = (255, 0, 0)  # contacto with confianca 'baixa' (interlocked pieces, partition uncertain)
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


def draw_overlay(rgb: np.ndarray, items: list, title: str = "", *, max_w: Optional[float] = OVERLAY_MAX_W,
				 max_px: Optional[float] = None) -> np.ndarray:
	"""Scan (RGB) with each piece contour and a large number, returned as BGR.

	``items`` = [{contour (scan px), n, colour (RGB), highlight (opt.)}]; a highlighted item
	gets a thicker amber contour and a larger, thicker label. Downscale so the width is
	<= ``max_w`` and the long side <= ``max_px`` (None = no limit); labels scale with the
	output width.
	"""
	import cv2
	img = np.ascontiguousarray(rgb[..., ::-1]).copy()
	H, W = img.shape[:2]
	s = 1.0
	if max_w:
		s = min(s, float(max_w) / W)
	if max_px:
		s = min(s, float(max_px) / max(H, W))
	if s < 1.0:
		img = cv2.resize(img, (max(1, int(W * s)), max(1, int(H * s))), interpolation=cv2.INTER_AREA)
	lw = max(2, int(round(img.shape[1] / 600)))
	fs = img.shape[1] / 900.0
	for it in sorted(items, key=lambda t: bool(t.get("highlight"))):   # highlight drawn last (on top)
		cnt = (np.asarray(it["contour"], float).reshape(-1, 2) * s).astype(np.int32)
		if len(cnt) == 0:
			continue
		hl = bool(it.get("highlight"))
		col = tuple(int(v) for v in (HIGHLIGHT_RGB if hl else it.get("colour", COL_PIECE))[::-1])
		w, f = (3 * lw, 1.4 * fs) if hl else (lw, fs)
		cv2.polylines(img, [cnt], True, col, w, cv2.LINE_AA)
		txt = str(it["n"])
		tt = (5 if hl else 3) * lw
		(tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, f, tt)
		cx, cy = cnt.mean(0)
		org = (int(cx - tw / 2), int(cy + th / 2))
		cv2.putText(img, txt, org, cv2.FONT_HERSHEY_SIMPLEX, f, (0, 0, 0), tt + 4, cv2.LINE_AA)
		cv2.putText(img, txt, org, cv2.FONT_HERSHEY_SIMPLEX, f, col if hl else (255, 255, 255), tt, cv2.LINE_AA)
	if title:
		cv2.putText(img, title, (20, int(40 * fs) + 10), cv2.FONT_HERSHEY_SIMPLEX, fs * 0.8, (0, 0, 0), 2 * lw + 4,
					cv2.LINE_AA)
		cv2.putText(img, title, (20, int(40 * fs) + 10), cv2.FONT_HERSHEY_SIMPLEX, fs * 0.8, (255, 255, 255), 2 * lw,
					cv2.LINE_AA)
	return img


def piece_label(p) -> int:
	"""Number printed for a piece on its sheet: ``n_no_lote``, else ``index_in_scan + 1``."""
	return int(p.n_no_lote) if p.n_no_lote is not None else int(p.index_in_scan) + 1


def _piece_colour(p) -> tuple:
	if p.flags.get("objeto_duplo"):
		return COL_DOUBLE
	if (p.flags.get("contacto") or {}).get("confianca") == "baixa":
		return COL_CONTACT_LOW
	return COL_BORDER if p.n_flat else COL_PIECE


# ---------------------------------------------------------------- service
def _scan_path(scan: dict) -> str:
	f = scan.get("file") or ""
	return f if os.path.isabs(f) else os.path.join(REPO, f)


def sheet_overlay(project, scan_id: str, *, highlight: Optional[str] = None, max_px: Optional[float] = None,
				  max_w: Optional[float] = None) -> np.ndarray:
	"""Numbered sheet of ``scan_id`` (BGR): the scan re-read from ``scans[sid]["file"]`` (repo
	relative or absolute), each piece's contour (:meth:`Project.contour_px`) and its
	:func:`piece_label` (the bag number, as written on the sheet kept with the bag).

	``highlight`` = piece id drawn in amber with a thicker label; ``max_px`` / ``max_w`` cap
	the long side / width. Raises ``ValueError`` if the scan or its image is missing.
	"""
	from PIL import Image
	scan = project.model.scans.get(scan_id)
	if scan is None:
		raise ValueError(f"scan desconhecido {scan_id}")
	fp = _scan_path(scan)
	if not os.path.exists(fp):
		raise ValueError(f"imagem do scan {scan_id} não encontrada: {fp}")
	with Image.open(fp) as im:
		rgb = np.asarray(im.convert("RGB"))
	pcs = sorted((p for p in project.pieces.values() if p.scan_id == scan_id), key=lambda q: (piece_label(q), q.id))
	items = []
	for p in pcs:
		cnt = project.contour_px(p.id)
		if cnt is None:
			continue
		items.append({"contour": cnt, "n": piece_label(p), "colour": _piece_colour(p), "highlight": p.id == highlight})
	lote = scan.get("lote")
	title = f"{scan_id} lote {lote}: {len(pcs)} pecas" if lote is not None else f"{scan_id}: {len(pcs)} pecas"
	return draw_overlay(rgb, items, title=title, max_w=max_w, max_px=max_px)


def write_overlay(project, scan_id: str) -> str:
	"""Write ``overlays/<scan_id>.jpg`` (:func:`sheet_overlay`, width <= ``OVERLAY_MAX_W``); returns its path."""
	import cv2
	ov = sheet_overlay(project, scan_id, max_w=OVERLAY_MAX_W)
	os.makedirs(project.p("overlays"), exist_ok=True)
	ov_path = project.p("overlays", f"{scan_id}.jpg")
	ok, buf = cv2.imencode(".jpg", ov, [cv2.IMWRITE_JPEG_QUALITY, 88])
	if not ok:
		raise ValueError(f"falha a codificar o overlay de {scan_id}")
	buf.tofile(ov_path)
	return ov_path


def ingest_scan(project, scan_path: str, lote: Optional[int], *, dpi: float = 300, kind: str = "soltas",
				known_cells: Optional[dict] = None, segment=None) -> dict:
	"""Segment ``scan_path`` and add its pieces to ``project`` (then ``project.save()``).

	Returns ``{scan_id, pieces: [ids], numbers: {id: n_no_lote}, rejected: [...], double: [ids],
	overlay, known: [...], n_segmented}`` or ``{'error': str}``. ``segment`` overrides
	``segment_scan`` (tests).
	"""
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
	ids, numbers, double = [], {}, []
	for (p, area), n in sorted(zip(kept, order), key=lambda t: t[1]):
		cnt = np.asarray(p["contour"]).reshape(-1, 2)
		shape = analyse(cnt, mmpp)
		dup = bool(p.get("is_cluster")) or area > DOUBLE_AREA_FACTOR * med
		rgba = np.asarray(piece_to_rgba(p["image"], p["mask"]))
		flags = {"touches_frame": bool(p.get("touches_frame")), "touches_strip": bool(p.get("touches_strip")),
				 "is_cluster": bool(p.get("is_cluster")), "objeto_duplo": dup}
		if p.get("contacto"):
			flags["contacto"] = {"com": [int(i) for i in p["contacto"].get("com", [])],
								 "confianca": str(p["contacto"].get("confianca", "alta")),
								 "metodo": str(p["contacto"].get("metodo", "")),
								 "alterado": bool(p["contacto"].get("alterado"))}
		pid_next = f"P{int(project.meta['next_ids']['P']):04d}"
		crop_rel = f"crops/{pid_next}.png"
		Image.fromarray(np.ascontiguousarray(rgba)).save(project.p(crop_rel))
		pid = project.add_piece(sid, {
			"index_in_scan": int(p["index"]), "n_no_lote": n0 + n, "shape": shape, "contour": cnt,
			"bbox": [int(v) for v in p["bbox"]], "crop_path": crop_rel, "mean_lab": _mean_lab(rgba),
			"area_mm2": round(area, 2),
			"flags": flags,
		})
		assert pid == pid_next, (pid, pid_next)
		ids.append(pid)
		numbers[pid] = n0 + n
		if dup:
			double.append(pid)
	ov_path = write_overlay(project, sid)

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
