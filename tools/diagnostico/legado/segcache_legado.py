"""Segmentation cache for the legacy pages and the GT scans (``$PPF_SCRATCH/legado/*.npz``).

``segment_scan(dpi=300, normalize_rotation=False)`` once per scan; the npz keeps only what
the legacy analysis needs (contours px, bbox, flags, area), so re-runs are fast. Crops are
rebuilt from the scan and the contour.

	python tools/diagnostico/legado/segcache_legado.py [--jobs 6] [--force]
"""

import argparse
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO)

LEG = "images/pieces/legado"
PAGES = [f"montado_p{k:02d}" for k in range(1, 16)] + [f"blocos_p{k:02d}" for k in range(1, 4)]
GT_SCANS = {
	"A1": "images/pieces/coluna5-24_300dpi_folhaA.jpg",
	"B2": "images/pieces/coluna5-24_folhaB_300dpi_rot180.jpg",
	"BE": "images/pieces/gt_canto_BE_soltas_300dpi.jpg",
	"BD": "images/pieces/gt_canto_BD_soltas_300dpi.jpg",
}


def scan_paths() -> dict:
	"""name -> path relative to the repository (legacy pages + GT scans)."""
	d = {p: f"{LEG}/{p}_300dpi.jpg" for p in PAGES}
	d.update({f"gt_{k}": v for k, v in GT_SCANS.items()})
	return d


def cache_dir() -> str:
	s = os.environ.get("PPF_SCRATCH")
	if not s:
		raise SystemExit("PPF_SCRATCH não definido")
	d = os.path.join(s, "legado")
	os.makedirs(d, exist_ok=True)
	return d


def segment_to_npz(name: str, rel: str, out: str) -> str:
	from PIL import Image
	from src.segmentation import segment_scan
	t0 = time.time()
	with Image.open(os.path.join(REPO, rel)) as im:
		photo = im.convert("RGB")
	res = segment_scan(photo, dpi=300, normalize_rotation=False)
	if "error" in res:
		return f"{name}: ERRO {res['error']}"
	P = res["pieces"]
	d = {"mm_per_px": np.array(float(res["mm_per_px"])), "n": np.array(len(P)), "src_file": np.array(rel),
		 "shape_hw": np.array(photo.size[::-1])}
	for i, p in enumerate(P):
		d[f"c{i}"] = np.asarray(p["contour"]).reshape(-1, 2).astype(np.int32)
	d["bbox"] = np.array([p["bbox"] for p in P], np.int64).reshape(-1, 4)
	d["area_px"] = np.array([float(p["area_px"]) for p in P])
	d["index"] = np.array([int(p["index"]) for p in P])
	for k in ("is_cluster", "touches_strip", "touches_frame", "refined"):
		d[k] = np.array([bool(p.get(k)) for p in P])
	np.savez_compressed(out, **d)
	return f"{name}: {len(P)} objetos em {time.time() - t0:.0f} s"


def load_npz(path: str) -> dict:
	"""Back to a light ``segment_scan``-like dict: ``{mm_per_px, pieces: [{contour, bbox, area_px, index, flags...}]}``."""
	with np.load(path, allow_pickle=False) as z:
		n = int(z["n"])
		pieces = []
		for i in range(n):
			pieces.append({"contour": z[f"c{i}"], "bbox": [int(v) for v in z["bbox"][i]], "area_px": float(z["area_px"][i]),
						   "index": int(z["index"][i]), "is_cluster": bool(z["is_cluster"][i]),
						   "touches_strip": bool(z["touches_strip"][i]), "touches_frame": bool(z["touches_frame"][i]),
						   "refined": bool(z["refined"][i])})
		return {"mm_per_px": float(z["mm_per_px"]), "pieces": pieces, "file": str(z["src_file"])}


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("--jobs", type=int, default=6)
	ap.add_argument("--force", action="store_true")
	a = ap.parse_args()
	cd = cache_dir()
	todo = [(n, r, os.path.join(cd, f"{n}.npz")) for n, r in scan_paths().items()]
	todo = [t for t in todo if a.force or not os.path.exists(t[2])]
	with ProcessPoolExecutor(a.jobs) as ex:
		for msg in ex.map(segment_to_npz, *zip(*todo)) if todo else []:
			print(msg, flush=True)


if __name__ == "__main__":
	main()
