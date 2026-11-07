"""Tabs lost outside the contour (COMIDO.md §6, §10): ``segment_scan`` variants on every project sheet, against the index.

Usage (from the repository root; only reads the project)::

	python tools/diagnostico/segmentacao/baias.py --project projects/alpes [--sheets S0024,S0025] [--variants off,A,B,C]
		[--force] [--figure]

Variants (module switches of ``src.segmentation``, set per run):

* ``off``: ``_BAY_TABS``, ``_BAY_CONTACT``, ``_FLAG_BAYS`` off (the code before this change; must equal the index);
* ``A``: tabs beyond the rectangle (opening, inscribed radius, throat), flag on, contact members still skipped;
* ``B``: no tab pass; the rectangle of the old rule widened to ``_BAY_RECT_PAD_MM`` = 6 mm, shape validation decides;
* ``C``: A + contact members (candidates >= 1 mm from the other pieces): the defaults;
* ``F``: flag only (no tab pass, no contact members): what the reason ``baia`` sees without the recovery.

Per sheet: count and ``grid_order`` numbering against the stored ``n_no_lote``, pieces whose contour differs from the
index npz (area, class, chords, ``recuperado_mm2``), ``suspeita_recorte`` reasons ``baia``, time; per variant the
list of changed pieces. ``--figure`` writes ``docs/diagnostico/segmentacao/COMIDO_baias.jpg`` (index red / variant C
cyan / gained area magenta) for the changed pieces of C plus the controls. Caches in ``$PPF_SCRATCH/baias/``.
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

VARIANTS = {
	"off": {"_BAY_TABS": False, "_BAY_CONTACT": False, "_FLAG_BAYS": False},
	"A": {"_BAY_TABS": True, "_BAY_CONTACT": False, "_FLAG_BAYS": True},
	"B": {"_BAY_TABS": False, "_BAY_CONTACT": False, "_FLAG_BAYS": True, "_BAY_RECT_PAD_MM": 6.0},
	"C": {"_BAY_TABS": True, "_BAY_CONTACT": True, "_FLAG_BAYS": True},
	"F": {"_BAY_TABS": False, "_BAY_CONTACT": False, "_FLAG_BAYS": True},
}
CONTROLS = ("P0156", "P0195", "P0445")


def scratch() -> str:
	base = os.environ.get("PPF_SCRATCH") or os.path.join(ROOT, "scratch")
	d = os.path.join(base, "baias")
	os.makedirs(d, exist_ok=True)
	return d


def run_sheet(sid: str, scan: dict, var: str, force: bool) -> dict:
	fp = os.path.join(scratch(), f"{sid}_{var}.pkl")
	if os.path.exists(fp) and not force:
		with open(fp, "rb") as f:
			return pickle.load(f)
	path = scan["file"] if os.path.isabs(scan["file"]) else os.path.join(ROOT, scan["file"])
	with Image.open(path) as im:
		photo = im.convert("RGB")
	saved = {k: getattr(SEG, k) for k in VARIANTS[var]}
	t_flag = [0.0]
	orig_sig = SEG._bay_signal

	def timed(*a, **k):
		t = time.time()
		try:
			return orig_sig(*a, **k)
		finally:
			t_flag[0] += time.time() - t
	try:
		for k, v in VARIANTS[var].items():
			setattr(SEG, k, v)
		SEG._bay_signal = timed
		t0 = time.time()
		res = SEG.segment_scan(photo, dpi=float(scan.get("dpi") or 300), normalize_rotation=False)
		dt = time.time() - t0
	finally:
		for k, v in saved.items():
			setattr(SEG, k, v)
		SEG._bay_signal = orig_sig
	out = {"t": dt, "t_flag": t_flag[0], "mm_per_px": res["mm_per_px"], "pieces": [
		{"index": int(p["index"]), "contour": np.asarray(p["contour"]).reshape(-1, 2).astype(np.int32),
		 "bbox": tuple(int(v) for v in p["bbox"]), "area_px": int(p["area_px"]), "recuperado_mm2": p.get("recuperado_mm2"),
		 "suspeita_recorte": p.get("suspeita_recorte"), "contacto": bool(p.get("contacto"))} for p in res["pieces"]]}
	with open(fp, "wb") as f:
		pickle.dump(out, f)
	return out


def compare(proj: str, scan: dict, run: dict) -> dict:
	"""Count / numbering / changed pieces of one run against the project's npz and scans json."""
	mmpp = run["mm_per_px"]
	kept = [p for p in run["pieces"] if p["area_px"] * mmpp * mmpp >= MIN_PIECE_MM2]
	stored = {int(p["index_in_scan"]): p for p in scan["pieces"]}
	off = min((p["n_no_lote"] for p in stored.values()), default=1) - 1
	num = {p["index"]: n for p, n in zip(kept, grid_order([p["bbox"] for p in kept]))}
	same_num = len(num) == len(stored) and all(stored.get(i, {}).get("n_no_lote") == n + off for i, n in num.items())
	npz = os.path.join(proj, "pieces", f"{scan['id']}.npz")
	changed, baia = [], []
	with np.load(npz, allow_pickle=False) as z:
		for p in kept:
			sp = stored.get(p["index"])
			if sp is None:
				continue
			old = z[f"{sp['id']}__contour_px"]
			if old.shape != p["contour"].shape or not np.array_equal(old, p["contour"]):
				sa, sb = analyse(old, mmpp), analyse(p["contour"], mmpp)
				changed.append({"pid": sp["id"], "n": sp["n_no_lote"], "cell": sp.get("celula"), "estado": sp.get("estado"),
								"area_old": float(sp["area_mm2"]), "area_new": round(p["area_px"] * mmpp * mmpp, 2),
								"cls_old": sa.cls, "cls_new": sb.cls, "lens_old": [round(float(x), 2) for x in sa.lens],
								"lens_new": [round(float(x), 2) for x in sb.lens], "rec": p["recuperado_mm2"],
								"contacto": p["contacto"]})
			sr = p.get("suspeita_recorte") or {}
			if "baia" in (sr.get("razoes") or []):
				baia.append({"pid": sp["id"], "r_mm": sr.get("baia_r_mm"), "mm2": sr.get("baia_mm2")})
	return {"n": len(kept), "n_stored": len(stored), "same_num": same_num, "changed": changed, "baia": baia}


def figure(proj: str, scans: dict, runs: dict, pids: list, out: str) -> None:
	tiles = []
	where = {}
	for sid, scan in scans.items():
		for p in scan["pieces"]:
			where[p["id"]] = (sid, int(p["index_in_scan"]))
	for pid in pids:
		sid, idx = where[pid]
		scan = scans[sid]
		path = scan["file"] if os.path.isabs(scan["file"]) else os.path.join(ROOT, scan["file"])
		rgb = np.asarray(Image.open(path).convert("RGB"))
		with np.load(os.path.join(proj, "pieces", f"{sid}.npz")) as z:
			old = z[f"{pid}__contour_px"]
		new = [p for p in runs[(sid, "C")]["pieces"] if p["index"] == idx][0]["contour"]
		H, W = rgb.shape[:2]
		mo, mn = np.zeros((H, W), np.uint8), np.zeros((H, W), np.uint8)
		cv2.drawContours(mo, [old.reshape(-1, 1, 2)], -1, 1, cv2.FILLED)
		cv2.drawContours(mn, [new.reshape(-1, 1, 2)], -1, 1, cv2.FILLED)
		x, y, w, h = cv2.boundingRect(np.vstack([old, new]).reshape(-1, 1, 2))
		pad = 40
		sl = (slice(max(0, y - pad), y + h + pad), slice(max(0, x - pad), x + w + pad))
		im = rgb[sl].copy()
		gain = (mn > 0) & (mo == 0)
		im[gain[sl]] = (im[gain[sl]] * 0.4 + np.array([255, 0, 255]) * 0.6).astype(np.uint8)
		lost = (mo > 0) & (mn == 0)
		im[lost[sl]] = (im[lost[sl]] * 0.4 + np.array([255, 160, 0]) * 0.6).astype(np.uint8)
		off = np.array([sl[1].start, sl[0].start])
		cv2.polylines(im, [(old - off).reshape(-1, 1, 2)], True, (255, 0, 0), 2)
		cv2.polylines(im, [(new - off).reshape(-1, 1, 2)], True, (0, 255, 255), 1)
		cv2.rectangle(im, (0, 0), (im.shape[1], 22), (0, 0, 0), -1)
		cv2.putText(im, f"{pid} {sid} #{idx}", (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
		tiles.append(im)
	if not tiles:
		return
	H = max(t.shape[0] for t in tiles)
	row = np.hstack([np.pad(t, ((0, H - t.shape[0]), (0, 6), (0, 0)), constant_values=255) for t in tiles])
	Image.fromarray(row).save(out, quality=88)


def main(argv=None) -> int:
	ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
	ap.add_argument("--project", required=True)
	ap.add_argument("--sheets", default="")
	ap.add_argument("--variants", default="off,A,B,C")
	ap.add_argument("--force", action="store_true")
	ap.add_argument("--figure", action="store_true")
	a = ap.parse_args(argv)
	proj = a.project if os.path.isabs(a.project) else os.path.join(ROOT, a.project)
	want = {s.strip() for s in a.sheets.split(",") if s.strip()}
	variants = [v.strip() for v in a.variants.split(",") if v.strip()]
	scans = {}
	for fp in sorted(glob.glob(os.path.join(proj, "scans", "S*.json"))):
		with open(fp, encoding="utf-8") as f:
			sc = json.load(f)
		if not want or sc["id"] in want:
			scans[sc["id"]] = sc
	runs, summary = {}, {v: {"changed": [], "baia": [], "bad": [], "t": 0.0, "t_flag": 0.0} for v in variants}
	print("| folha | " + " | ".join(f"{v}: peças / numeração / alteradas / baia / s" for v in variants) + " |")
	print("|---|" + "---|" * len(variants))
	for sid, scan in scans.items():
		cells = []
		for v in variants:
			r = runs[(sid, v)] = run_sheet(sid, scan, v, a.force)
			c = compare(proj, scan, r)
			s = summary[v]
			s["changed"] += [dict(x, sid=sid) for x in c["changed"]]
			s["baia"] += [dict(x, sid=sid) for x in c["baia"]]
			s["t"] += r["t"]
			s["t_flag"] += r["t_flag"]
			if c["n"] != c["n_stored"] or not c["same_num"]:
				s["bad"].append(sid)
			cells.append(f"{c['n']}/{c['n_stored']} / {'sim' if c['same_num'] else 'NÃO'} / {len(c['changed'])} / "
						 f"{len(c['baia'])} / {r['t']:.1f}")
		print(f"| {sid} | " + " | ".join(cells) + " |", flush=True)
	for v in variants:
		s = summary[v]
		print(f"\n== {v}: {len(s['changed'])} peças alteradas, {len(s['baia'])} com razão baia, folhas com contagem/numeração "
			  f"diferente: {s['bad'] or 'nenhuma'}; tempo {s['t']:.1f} s (sinal da baia {s['t_flag']:.1f} s)")
		for x in s["changed"]:
			print(f"   {x['sid']} #{x['n']} {x['pid']} {x['cell']} {x['estado']}: {x['area_old']:.1f} -> {x['area_new']:.1f} mm2 "
				  f"(recuperado {x['rec']}, contacto {x['contacto']}) {x['cls_old']} {x['lens_old']} -> {x['cls_new']} {x['lens_new']}")
		for x in s["baia"]:
			print(f"   baia: {x['sid']} {x['pid']} r {x['r_mm']} mm, {x['mm2']} mm2")
	if a.figure and "C" in variants:
		pids = [x["pid"] for x in summary["C"]["changed"]] + [p for p in CONTROLS]
		where = {p["id"]: sid for sid, sc in scans.items() for p in sc["pieces"]}
		pids = [p for p in pids if p in where and (where[p], "C") in runs]
		out = os.path.join(ROOT, "docs", "diagnostico", "segmentacao", "COMIDO_baias.jpg")
		figure(proj, scans, runs, pids, out)
		print(f"figura {os.path.relpath(out, ROOT)}: {pids}")
	return 0


if __name__ == "__main__":
	sys.exit(main())
