"""Eaten-meadow recovery in segment_scan (``recover_bays``): before vs after, on every project sheet.

Usage (from the repository root)::

	python tools/diagnostico/segmentacao/prado.py [--project projects/alpes] [--sheets S0009,S0020] [--force]
		[--pares P0218:P0647,P0223:P0641,P0199:P0629]

For each sheet of ``<project>/scans/S*.json`` runs ``segment_scan(normalize_rotation=False)``
with ``recover_bays=False`` ("antes", the previous output) and ``recover_bays=True``
("depois"). Per sheet: piece count, ``n_no_lote`` numbering (``grid_order`` of the pieces
>= ``MIN_PIECE_MM2``) before vs after and against the stored project, pieces whose contour
changed and the time of each run. Lists every changed piece (area before -> after, class and
chords). For the ``--pares`` (piece:twin) the free distance (:func:`src.shape.free_dist`) of
the piece before/after to the twin's stored shape. Results cached in
``$PPF_SCRATCH/prado/<sid>.pkl`` (``--force`` recomputes). Only reads the project.
Discussed in docs/diagnostico/segmentacao/PRADO.md.
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
from src.shape import Shape, analyse, free_dist                 # noqa: E402

PARES = "P0218:P0647,P0223:P0641,P0199:P0629"


def scratch() -> str:
	d = os.path.join(os.environ.get("PPF_SCRATCH", os.path.join(ROOT, "scratch")), "prado")
	os.makedirs(d, exist_ok=True)
	return d


def light(res: dict) -> dict:
	return {"count": res.get("count"), "pieces": [
		{"index": int(p["index"]), "contour": np.asarray(p["contour"]).reshape(-1, 2).astype(np.int32),
		 "bbox": tuple(int(v) for v in p["bbox"]), "area_px": int(p["area_px"]),
		 "recuperado_mm2": p.get("recuperado_mm2")} for p in res.get("pieces", [])]}


def run_sheet(sid: str, scan: dict, force: bool) -> dict:
	cache = os.path.join(scratch(), f"{sid}.pkl")
	if os.path.exists(cache) and not force:
		with open(cache, "rb") as f:
			return pickle.load(f)
	fp = scan["file"] if os.path.isabs(scan["file"]) else os.path.join(ROOT, scan["file"])
	with Image.open(fp) as im:
		photo = im.convert("RGB")
	dpi = float(scan.get("dpi") or 300)
	t0 = time.time()
	a = light(SEG.segment_scan(photo, dpi=dpi, normalize_rotation=False, recover_bays=False))
	ta = time.time() - t0
	t0 = time.time()
	b = light(SEG.segment_scan(photo, dpi=dpi, normalize_rotation=False, recover_bays=True))
	tb = time.time() - t0
	d = {"sid": sid, "file": scan["file"], "dpi": dpi, "antes": a, "depois": b, "t_antes": ta, "t_depois": tb}
	with open(cache, "wb") as f:
		pickle.dump(d, f)
	return d


def numbering(pieces: list[dict], mmpp: float) -> dict:
	kept = [p for p in pieces if p["area_px"] * mmpp * mmpp >= MIN_PIECE_MM2]
	return {p["index"]: n for p, n in zip(kept, grid_order([p["bbox"] for p in kept]))}


def stored_shape(proj: str, sid: str, pid: str) -> Shape | None:
	fp = os.path.join(proj, "pieces", f"{sid}.npz")
	if not os.path.exists(fp):
		return None
	pre = f"{pid}__"
	with np.load(fp, allow_pickle=False) as z:
		d = {k[len(pre):]: z[k] for k in z.files if k.startswith(pre)}
	if "c" not in d:
		return None
	return Shape.from_arrays({k: v for k, v in d.items() if k not in ("contour_px", "mask")})


def main(argv=None) -> int:
	ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
	ap.add_argument("--project", default=os.path.join("projects", "alpes"))
	ap.add_argument("--sheets", default="", help="lista separada por vírgulas (por omissão todas)")
	ap.add_argument("--force", action="store_true")
	ap.add_argument("--pares", default=PARES, help="peça:gémea separadas por vírgulas")
	a = ap.parse_args(argv)
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
	print("| Folha | Ficheiro | Tipo | Peças antes → depois | Numeração igual | Numeração = projeto | Alteradas | t antes / depois (s) |")
	print("|---|---|---|---|---|---|---|---|")
	changed, tot = [], [0.0, 0.0]
	runs = {}
	for sid, scan in scans.items():
		d = runs[sid] = run_sheet(sid, scan, a.force)
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
				sa, sb = analyse(pa["contour"], mmpp), analyse(pb["contour"], mmpp)
				changed.append((sid, sp.get("n_no_lote"), sp.get("id"), sp.get("celula"), pa["area_px"] * mmpp * mmpp,
								pb["area_px"] * mmpp * mmpp, pb["recuperado_mm2"], sa, sb))
		tot[0] += d["t_antes"]
		tot[1] += d["t_depois"]
		print(f"| {sid} | `{os.path.basename(scan['file'])}` | {scan.get('kind')} | {d['antes']['count']} → {d['depois']['count']} | "
			  f"{'sim' if na == nb else 'NÃO'} | {'sim' if same_stored else 'NÃO'} | {nch} | {d['t_antes']:.1f} / {d['t_depois']:.1f} |",
			  flush=True)
	print(f"\ntempo total {tot[0]:.1f} / {tot[1]:.1f} s")
	print("\npeças alteradas:")
	for sid, n, pid, cel, aa, ab, rec, sa, sb in changed:
		print(f"  {sid} #{n} {pid} {cel}: {aa:.1f} -> {ab:.1f} mm2 ({100 * (ab - aa) / aa:+.2f} %, recuperado_mm2 {rec}) "
			  f"{sa.cls} {[round(float(x), 2) for x in sa.lens]} -> {sb.cls} {[round(float(x), 2) for x in sb.lens]}")
	print("\npares (peça antes/depois contra a forma guardada da gémea):")
	for pair in a.pares.split(","):
		if ":" not in pair:
			continue
		pid, tw = pair.split(":")
		if pid not in where or tw not in where or where[pid][0] not in runs:
			print(f"  {pid}:{tw} fora das folhas pedidas")
			continue
		sid, idx = where[pid]
		tws = stored_shape(proj, where[tw][0], tw)
		if tws is None:
			print(f"  {tw} sem forma guardada")
			continue
		out = []
		for k in ("antes", "depois"):
			c = [p for p in runs[sid][k]["pieces"] if p["index"] == idx][0]["contour"]
			s = analyse(c, 25.4 / runs[sid]["dpi"])
			flats = [round(float(sd.chord_mm), 2) for sd in s.sides if sd.kind == "F"]
			out.append(f"{k} {s.cls} F {flats} free {float(free_dist(s, tws)[0]):.3f} mm")
		print(f"  {pid} vs {tw} ({tws.cls}): " + " | ".join(out))
	return 0


if __name__ == "__main__":
	sys.exit(main())
