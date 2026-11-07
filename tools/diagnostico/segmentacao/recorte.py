"""Suspect cuts and the contact trim of segment_scan (S0023 #3/#4 revisited, CONTACTOS.md §6).

Usage (from the repository root)::

	python tools/diagnostico/segmentacao/recorte.py porta  [--project projects/alpes] [--sheets S0023] [--force]
	python tools/diagnostico/segmentacao/recorte.py indice [--project projects/alpes]

``porta``: for each sheet of ``<project>/scans/S*.json`` runs ``segment_scan(normalize_rotation=False)``
with ``_CONTACT_TRIM`` off ("antes", the previous output bit for bit) and on ("depois"). Per sheet:
piece count, ``n_no_lote`` numbering (``grid_order`` of the pieces >= ``MIN_PIECE_MM2``) before vs after
and against the stored project, the pieces whose contour changed, and every ``watershed`` contact pair
with its facing-side ``side_complement`` (detector (a)) before and after; the ``suspeita_recorte``
flags of the "depois" run. For the changed pieces with a twin given in ``--gemeas`` the free
distance to the twin's stored shape. Results cached in ``$PPF_SCRATCH/recorte/<sid>.pkl``.

``indice``: the three detectors on the stored contours of every piece (distribution, p50/p95/p99/max
and the top pieces): (b) appendage (``_appendage``, opening radius 0.3 / 0.5 / 0.8 mm), (c) maximum
second difference of the T/B side profiles (mm), and the reference of (a): ``side_complement`` of the
facing sides of every pair of board-adjacent placed pieces (pose ``k`` from
``render.register_piece(image=False, manual=False)``). Only reads the project.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import pickle
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

from PIL import Image                                           # noqa: E402

from src import segmentation as SEG                             # noqa: E402
from src.ingest import MIN_PIECE_MM2, grid_order                # noqa: E402
from src.shape import analyse, free_dist, side_complement       # noqa: E402

GEMEAS = "P0777:P0420,P0778:P0425"


def scratch() -> str:
	d = os.path.join(os.environ.get("PPF_SCRATCH", os.path.join(ROOT, "scratch")), "recorte")
	os.makedirs(d, exist_ok=True)
	return d


def light(res: dict) -> dict:
	return {"count": res.get("count"), "pieces": [
		{"index": int(p["index"]), "contour": np.asarray(p["contour"]).reshape(-1, 2).astype(np.int32),
		 "bbox": tuple(int(v) for v in p["bbox"]), "area_px": int(p["area_px"]), "contacto": p.get("contacto"),
		 "suspeita": p.get("suspeita_recorte")} for p in res.get("pieces", [])]}


def run_sheet(sid: str, scan: dict, force: bool) -> dict:
	cache = os.path.join(scratch(), f"{sid}.pkl")
	if os.path.exists(cache) and not force:
		with open(cache, "rb") as f:
			return pickle.load(f)
	fp = scan["file"] if os.path.isabs(scan["file"]) else os.path.join(ROOT, scan["file"])
	with Image.open(fp) as im:
		photo = im.convert("RGB")
	dpi = float(scan.get("dpi") or 300)
	keep = SEG._CONTACT_TRIM
	try:
		SEG._CONTACT_TRIM = False
		t0 = time.time()
		a = light(SEG.segment_scan(photo, dpi=dpi, normalize_rotation=False))
		ta = time.time() - t0
		SEG._CONTACT_TRIM = True
		t0 = time.time()
		b = light(SEG.segment_scan(photo, dpi=dpi, normalize_rotation=False))
		tb = time.time() - t0
	finally:
		SEG._CONTACT_TRIM = keep
	d = {"sid": sid, "file": scan["file"], "dpi": dpi, "antes": a, "depois": b, "t_antes": ta, "t_depois": tb}
	with open(cache, "wb") as f:
		pickle.dump(d, f)
	return d


def numbering(pieces: list[dict], mmpp: float) -> dict:
	kept = [p for p in pieces if p["area_px"] * mmpp * mmpp >= MIN_PIECE_MM2]
	return {p["index"]: n for p, n in zip(kept, grid_order([p["bbox"] for p in kept]))}


def facing_pairs(pieces: list[dict], mmpp: float) -> dict:
	"""``{(i, j): (kinds, rms_mm)}`` of the watershed contact pairs (facing sides, as _shape_violations)."""
	out = {}
	by_index = {p["index"]: p for p in pieces}
	for p in pieces:
		ct = p.get("contacto") or {}
		if ct.get("metodo") != "watershed":
			continue
		for o in ct.get("com", []):
			key = tuple(sorted((p["index"], o)))
			if key in out or o not in by_index:
				continue
			_, info = SEG._shape_violations([by_index[key[0]]["contour"], by_index[key[1]]["contour"]], mmpp, True)
			f = info[0].get("face")
			out[key] = (f["kinds"], f["rms_mm"]) if f else (None, None)
	return out


def stored_shape(proj: str, sid: str, pid: str):
	from src.shape import Shape
	fp = os.path.join(proj, "pieces", f"{sid}.npz")
	if not os.path.exists(fp):
		return None
	pre = f"{pid}__"
	with np.load(fp, allow_pickle=False) as z:
		d = {k[len(pre):]: z[k] for k in z.files if k.startswith(pre)}
	if "c" not in d:
		return None
	return Shape.from_arrays({k: v for k, v in d.items() if k not in ("contour_px", "mask")})


def porta(a) -> int:
	proj = a.project if os.path.isabs(a.project) else os.path.join(ROOT, a.project)
	want = {s.strip() for s in a.sheets.split(",") if s.strip()}
	scans, where = {}, {}
	for fp in sorted(glob.glob(os.path.join(proj, "scans", "S*.json"))):
		with open(fp, encoding="utf-8") as f:
			scan = json.load(f)
		for p in scan["pieces"]:
			where[p["id"]] = (scan["id"], int(p["index_in_scan"]))
		if not want or scan["id"] in want:
			scans[scan["id"]] = scan
	gem = dict(x.split(":") for x in a.gemeas.split(",") if ":" in x)
	print("| Folha | Ficheiro | Peças antes → depois | Numeração igual | Numeração = projeto | Alteradas | t antes / depois (s) |")
	print("|---|---|---|---|---|---|---|")
	changed, pairs, flags, tot = [], [], [], [0.0, 0.0]
	for sid, scan in scans.items():
		d = run_sheet(sid, scan, a.force)
		mmpp = 25.4 / d["dpi"]
		A, B = d["antes"]["pieces"], d["depois"]["pieces"]
		na, nb = numbering(A, mmpp), numbering(B, mmpp)
		stored = {int(p["index_in_scan"]): p for p in scan["pieces"]}
		off = min((p["n_no_lote"] for p in stored.values()), default=1) - 1
		same_stored = len(nb) == len(stored) and all(stored.get(i, {}).get("n_no_lote") == n + off for i, n in nb.items())
		nch = 0
		for pa, pb in zip(A, B):
			if pa["area_px"] != pb["area_px"] or not np.array_equal(pa["contour"], pb["contour"]):
				nch += 1
				sp = stored.get(pa["index"], {})
				changed.append((sid, pa["index"], sp.get("n_no_lote"), sp.get("id"), sp.get("celula"), pa, pb, mmpp))
		fa, fb = facing_pairs(A, mmpp), facing_pairs(B, mmpp)
		for key in sorted(set(fa) | set(fb)):
			ids = [stored.get(i, {}).get("id") for i in key]
			pairs.append((sid, key, ids, fa.get(key), fb.get(key)))
		for p in B:
			if p.get("suspeita"):
				flags.append((sid, p["index"], stored.get(p["index"], {}).get("id"), p["suspeita"]))
		tot[0] += d["t_antes"]
		tot[1] += d["t_depois"]
		print(f"| {sid} | `{os.path.basename(scan['file'])}` | {d['antes']['count']} → {d['depois']['count']} | "
			  f"{'sim' if na == nb else 'NÃO'} | {'sim' if same_stored else 'NÃO'} | {nch} | {d['t_antes']:.1f} / {d['t_depois']:.1f} |",
			  flush=True)
	print(f"\ntempo total {tot[0]:.1f} / {tot[1]:.1f} s")
	print("\npeças alteradas (área mm², classe, cordas mm, apêndice mm, gémea):")
	for sid, idx, n, pid, cel, pa, pb, mmpp in changed:
		sa, sb = analyse(pa["contour"], mmpp), analyse(pb["contour"], mmpp)
		la, lb = SEG._appendage(pa["contour"], mmpp)[0], SEG._appendage(pb["contour"], mmpp)[0]
		line = (f"  {sid} idx {idx} #{n} {pid} {cel}: {sa.area_mm2:.1f} -> {sb.area_mm2:.1f}; {sa.cls} "
				f"{[round(float(x), 2) for x in sa.lens]} -> {sb.cls} {[round(float(x), 2) for x in sb.lens]}; "
				f"apêndice {la:.2f} -> {lb:.2f}")
		if pid in gem and gem[pid] in where:
			tws = stored_shape(proj, where[gem[pid]][0], gem[pid])
			if tws is not None:
				line += f"; free({gem[pid]}) {free_dist(sa, tws)[0]:.3f} -> {free_dist(sb, tws)[0]:.3f}"
		print(line)
	print("\npares watershed (lados frente a frente: tipos, RMS side_complement mm) antes -> depois:")
	for sid, key, ids, fa, fb in pairs:
		print(f"  {sid} {key} {ids}: {fa} -> {fb}")
	print("\nsuspeita_recorte (depois):")
	for sid, idx, pid, f in flags:
		print(f"  {sid} idx {idx} {pid}: {f}")
	return 0


def _side_d2(s) -> list:
	out = []
	for sd in s.sides:
		P = np.c_[sd.profile[:, 0], sd.profile[:, 1]] * sd.chord_mm
		out.append(float(np.linalg.norm(P[2:] - 2 * P[1:-1] + P[:-2], axis=1).max()))
	return out


def indice(a) -> int:
	from src import render
	from src.state import Project
	proj = a.project if os.path.isabs(a.project) else os.path.join(ROOT, a.project)
	pr = Project.open(proj)
	print(render.manual_pose_note(pr))   # as poses manuais não entram nas métricas
	mm = 25.4 / 300.0
	rows = []
	keep = SEG._SUSPECT_SPUR_MM
	try:
		for pid, p in sorted(pr.pieces.items()):
			c = pr.contour_px(pid)
			if c is None:
				continue
			c = np.asarray(c).reshape(-1, 2)
			s = analyse(c, mm)
			r = {"pid": pid, "kinds": s.types, "d2": _side_d2(s) if s.ok else []}
			for rad in (0.3, 0.5, 0.8):
				SEG._SUSPECT_SPUR_MM = rad
				r[rad] = SEG._appendage(c, mm)
			rows.append(r)
	finally:
		SEG._SUSPECT_SPUR_MM = keep
	print(f"peças com contorno: {len(rows)}")
	for rad in (0.3, 0.5, 0.8):
		L = np.array([r[rad][0] for r in rows])
		print(f"(b) abertura r={rad} mm: comprimento p50 {np.percentile(L, 50):.2f} p95 {np.percentile(L, 95):.2f} "
			  f"p99 {np.percentile(L, 99):.2f} máx {L.max():.2f}; topo "
			  f"{[(r['pid'], round(r[rad][0], 2)) for r in sorted(rows, key=lambda r: -r[rad][0])[:8]]}")
	v = [(d, r["pid"]) for r in rows for k, d in zip(r["kinds"], r["d2"]) if k in "TB"]
	D = np.array([x[0] for x in v])
	print(f"(c) 2.ª diferença máx dos lados T/B ({len(D)}): p50 {np.percentile(D, 50):.3f} p95 {np.percentile(D, 95):.3f} "
		  f"p99 {np.percentile(D, 99):.3f} máx {D.max():.3f}")
	for r in rows:
		if r["pid"] in ("P0777", "P0778"):
			print(f"   {r['pid']}: {r['kinds']} {[round(x, 3) for x in r['d2']]}")
	ids = sorted(q for q, p in pr.pieces.items() if p.estado in ("colocada", "posicao_conhecida") and p.celula is not None)
	K, cache = {}, {}
	for q in ids:
		e = render.register_piece(pr, q, art=None, image=False, _cache=cache, manual=False)
		k = None if "error" in e else (e.get("corner") or {}).get("k")
		if k is not None:
			K[q] = int(k)
	cells = {tuple(pr.piece(q).celula): q for q in K}
	j = []
	for (l, c), x in cells.items():
		for d, (dl, dc), o in (("E", (0, 1), "W"), ("S", (1, 0), "N")):
			y = cells.get((l + dl, c + dc))
			if y is None:
				continue
			sx, sy = pr.shape(x), pr.shape(y)
			if sx is None or sy is None or not sx.ok or not sy.ok:
				continue
			A = sx.sides[(render.DIRS.index(d) - K[x]) % 4]
			B = sy.sides[(render.DIRS.index(o) - K[y]) % 4]
			rms, dl_ = side_complement(A, B)
			j.append((rms, dl_, A.kind + B.kind, x, y))
	tb = np.array([x[0] for x in j if set(x[2]) == {"T", "B"}])
	print(f"(a) referência: {len(j)} juntas de vizinhas colocadas, {len(tb)} T↔B; RMS p50 {np.percentile(tb, 50):.3f} "
		  f"p90 {np.percentile(tb, 90):.3f} p99 {np.percentile(tb, 99):.3f} máx {tb.max():.3f}")
	print("    piores:", [(x[3], x[4], round(x[0], 2)) for x in sorted(j, key=lambda x: -x[0] if np.isfinite(x[0]) else 0)[:6]])
	return 0


def main(argv=None) -> int:
	ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
	ap.add_argument("modo", choices=("porta", "indice"))
	ap.add_argument("--project", default=os.path.join("projects", "alpes"))
	ap.add_argument("--sheets", default="", help="lista separada por vírgulas (por omissão todas)")
	ap.add_argument("--force", action="store_true")
	ap.add_argument("--gemeas", default=GEMEAS, help="peça:gémea separadas por vírgulas")
	a = ap.parse_args(argv)
	return porta(a) if a.modo == "porta" else indice(a)


if __name__ == "__main__":
	sys.exit(main())
