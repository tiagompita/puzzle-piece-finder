"""Evaluation harness for the MATCHING ENGINE (not the GUI).

Establishes the first real baseline of ``src.matching.multi_scale_template_match``
against ``src.segmentation.segment_pieces`` on the real photo IMG_2114, using:
  - the correct per-piece mask,
  - num_pieces=3000,
  - the engine's OWN downscale (use_downscale=True), with NO pre-downscale of the
    reference (so this measures the engine's native baseline).

It also runs a Laplacian-variance analysis of the reference to decide whether
PuzzleOriginal.jpeg carries real full-res detail or is "empty" (soft) resolution.

This file lives at the repo root and imports src/ as a package. Run from the repo
root:  ``python eval_matching.py``

Nothing under src/ is modified. Only this harness is created.
"""

from __future__ import annotations

import os
import sys
import time

import cv2
import numpy as np
from PIL import Image

# Import src/ as a package (src has __init__.py; modules use relative imports).
from src.segmentation import segment_pieces
from src.matching import multi_scale_template_match


# ----- Paths -----
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
REF_PATH = os.path.join(REPO_ROOT, "images", "puzzles", "PuzzleOriginal.jpeg")
PHOTO_PATH = os.path.join(REPO_ROOT, "images", "pieces", "IMG_2114.DNG")

SCRATCH = (
	r"C:\Users\tiago\AppData\Local\Temp\claude"
	r"\c--Users-tiago-Desktop-puzzle-piece-finder"
	r"\6b8972e6-01fb-46f6-b86c-c04a96ab0779\scratchpad"
)

NUM_PIECES = 3000
N_HIGH_IMAGES = 5


def log(msg: str) -> None:
	"""Print with immediate flush so progress is visible during long runs."""
	print(msg, flush=True)


def to_pil_rgb(obj) -> Image.Image:
	"""Coerce a piece['image'] (already a PIL Image here) or ndarray to PIL RGB."""
	if isinstance(obj, Image.Image):
		return obj.convert("RGB")
	arr = np.asarray(obj)
	return Image.fromarray(arr).convert("RGB")


def side_by_side(piece_pil: Image.Image, ref_crop_pil: Image.Image, height: int = 320) -> Image.Image:
	"""Scale both crops to a common height and join them horizontally (piece | ref)."""
	def _scaled(im: Image.Image) -> Image.Image:
		w, h = im.size
		if h <= 0:
			return im
		new_w = max(1, int(round(w * height / float(h))))
		return im.resize((new_w, height), Image.Resampling.LANCZOS)

	left = _scaled(piece_pil.convert("RGB"))
	right = _scaled(ref_crop_pil.convert("RGB"))
	gap = 12
	canvas = Image.new("RGB", (left.width + gap + right.width, height), (30, 30, 30))
	canvas.paste(left, (0, 0))
	canvas.paste(right, (left.width + gap, 0))
	return canvas


def laplacian_analysis(ref_gray: np.ndarray) -> tuple[list[dict], float]:
	"""Compare full-res vs 4x-soft Laplacian variance on representative crops.

	Picks a centre crop plus the most textured crops found on a coarse grid scan,
	then for each: v_full (full-res) and v_soft (downscale 4x then upscale back with
	INTER_CUBIC). Returns (per-crop records, median ratio).
	"""
	H, W = ref_gray.shape[:2]
	cs = 512
	if H < cs or W < cs:
		cs = min(H, W)

	# Coarse grid of candidate top-left corners; score each by full-res Lap var.
	step = max(cs, min(H, W) // 4)
	cands: list[tuple[int, int, float]] = []
	y = 0
	while y + cs <= H:
		x = 0
		while x + cs <= W:
			crop = ref_gray[y:y + cs, x:x + cs]
			v = float(cv2.Laplacian(crop, cv2.CV_64F).var())
			cands.append((x, y, v))
			x += step
		y += step

	# Centre crop always included; then the 3 most textured distinct crops.
	cx = (W - cs) // 2
	cy = (H - cs) // 2
	selected: list[tuple[int, int, str]] = [(cx, cy, "center")]
	cands.sort(key=lambda t: t[2], reverse=True)
	for x, y, _ in cands:
		if len(selected) >= 4:
			break
		# skip near-duplicates of already-selected crops
		if any(abs(x - sx) < cs and abs(y - sy) < cs for sx, sy, _ in selected):
			continue
		selected.append((x, y, "textured"))

	records: list[dict] = []
	ratios: list[float] = []
	for x, y, kind in selected:
		crop = ref_gray[y:y + cs, x:x + cs]
		v_full = float(cv2.Laplacian(crop, cv2.CV_64F).var())
		small = cv2.resize(crop, (cs // 4, cs // 4), interpolation=cv2.INTER_AREA)
		soft = cv2.resize(small, (cs, cs), interpolation=cv2.INTER_CUBIC)
		v_soft = float(cv2.Laplacian(soft, cv2.CV_64F).var())
		ratio = v_full / v_soft if v_soft > 1e-9 else float("inf")
		ratios.append(ratio)
		records.append({
			"pos": (x, y), "size": cs, "kind": kind,
			"v_full": v_full, "v_soft": v_soft, "ratio": ratio,
		})
	median_ratio = float(np.median(ratios)) if ratios else 0.0
	return records, median_ratio


def main() -> int:
	os.makedirs(SCRATCH, exist_ok=True)
	t0 = time.time()

	# ---- 1. Load reference (PIL RGB) ----
	log(f"[load] reference: {REF_PATH}")
	ref_img = Image.open(REF_PATH).convert("RGB")
	log(f"[load] reference size (W,H) = {ref_img.size}")
	ref_arr = np.asarray(ref_img)  # RGB, (H, W, 3)
	ref_gray = cv2.cvtColor(ref_arr, cv2.COLOR_RGB2GRAY)

	# ---- 2. Load photo (PIL RGB) ----
	log(f"[load] photo: {PHOTO_PATH}")
	try:
		photo_img = Image.open(PHOTO_PATH).convert("RGB")
	except Exception as exc:  # noqa: BLE001
		log(f"[FATAL] could not open photo via PIL: {exc!r}")
		return 2
	log(f"[load] photo size (W,H) = {photo_img.size}")

	# ---- Laplacian resolution analysis (independent of matching) ----
	log("[lap] running Laplacian full-res vs 4x-soft analysis on the reference...")
	lap_records, lap_median_ratio = laplacian_analysis(ref_gray)
	for r in lap_records:
		log(
			f"[lap] {r['kind']:8s} pos={r['pos']} size={r['size']} "
			f"v_full={r['v_full']:.1f} v_soft={r['v_soft']:.1f} ratio={r['ratio']:.2f}"
		)
	lap_verdict = (
		"REAL full-res detail (adaptive resolution is worth it)"
		if lap_median_ratio > 2.0
		else "EMPTY/soft resolution (adaptive resolution NOT worth it)"
	)
	log(f"[lap] median ratio = {lap_median_ratio:.2f} -> {lap_verdict}")

	# ---- 3. Segment the photo into pieces ----
	log("[seg] segmenting photo (segment_pieces, PIL RGB in)...")
	t_seg = time.time()
	seg = segment_pieces(photo_img)
	seg_secs = time.time() - t_seg
	if "error" in seg:
		log(f"[FATAL] segmentation failed: {seg.get('error')!r}  (full: {seg})")
		return 3
	pieces = seg["pieces"]
	clusters = [p for p in pieces if p.get("is_cluster")]
	non_cluster = [p for p in pieces if not p.get("is_cluster")]
	log(
		f"[seg] done in {seg_secs:.1f}s: total={seg['count']} pieces, "
		f"non-cluster={len(non_cluster)}, clusters(ignored)={len(clusters)}, "
		f"working_scale={seg.get('working_scale'):.4f}, bg_model={seg.get('background_model')}"
	)

	# ---- 4. Match every non-cluster piece ----
	results: list[dict] = []
	conf_counts: dict[str, int] = {}
	per_piece_times: list[float] = []
	log(f"[match] matching {len(non_cluster)} non-cluster pieces (num_pieces={NUM_PIECES}, use_downscale=True)...")

	for n, piece in enumerate(non_cluster, start=1):
		idx = piece.get("index", n - 1)
		piece_pil = to_pil_rgb(piece["image"])
		mask = piece.get("mask")  # PIL 'L'; engine also accepts ndarray. None -> unmasked.

		t_p = time.time()
		try:
			res = multi_scale_template_match(
				puzzle_img=ref_img,
				piece_img=piece_pil,
				num_pieces=NUM_PIECES,
				piece_mask=mask,
				use_downscale=True,
			)
		except Exception as exc:  # noqa: BLE001
			res = {"error": f"exception:{exc!r}"}
		dt = time.time() - t_p
		per_piece_times.append(dt)

		if "error" in res:
			conf = f"error:{res['error']}"
			rec = {
				"index": idx, "confidence": conf, "confidence_reason": res.get("error"),
				"best_position": None, "piece_size_final": None, "scale": None,
				"rotation": None, "refined_similarity": None, "time_s": dt,
				"piece_px": piece_pil.size,
			}
		else:
			conf = res.get("confidence", "?")
			rec = {
				"index": idx,
				"confidence": conf,
				"confidence_reason": res.get("confidence_reason"),
				"best_position": res.get("best_position"),
				"piece_size_final": res.get("piece_size_final"),
				"scale": res.get("scale"),
				"rotation": res.get("rotation"),
				"refined_similarity": res.get("refined_similarity"),
				"confidence_gap": res.get("confidence_gap"),
				"piece_structure": res.get("piece_structure"),
				"search_dims": res.get("search_dims"),
				"search_piece_px": res.get("search_piece_px"),
				"integral_mb": res.get("integral_mb"),
				"search_target_reached": res.get("search_target_reached"),
				"coarse_scale_factor": res.get("coarse_scale_factor"),
				"time_s": dt,
				"piece_px": piece_pil.size,
			}
			rec["_piece_pil"] = piece_pil  # kept for the side-by-side export
		conf_counts[conf] = conf_counts.get(conf, 0) + 1
		results.append(rec)

		size_final = rec.get("piece_size_final")
		log(
			f"[match] {n}/{len(non_cluster)} idx={idx} conf={conf} "
			f"sim={rec.get('refined_similarity')} pos={rec.get('best_position')} "
			f"size_final={size_final} rot={rec.get('rotation')} "
			f"piece_px={rec['piece_px']} t={dt:.2f}s"
		)

	total_secs = time.time() - t0

	# ---- 5. Distribution ----
	n_high = conf_counts.get("high", 0)
	total_nc = len(non_cluster)
	log("")
	log("=" * 64)
	log("CONFIDENCE DISTRIBUTION (non-cluster pieces)")
	log("=" * 64)
	log(f"total non-cluster pieces : {total_nc}")
	log(f"clusters ignored         : {len(clusters)}")
	for cls in sorted(conf_counts, key=lambda k: (-conf_counts[k], k)):
		log(f"  {cls:24s}: {conf_counts[cls]}")
	log("-" * 64)
	log(f"NEW baseline (high)  : {n_high}/{total_nc}")
	log(f"OLD baseline (high)  : 9/51")
	if total_nc:
		log(f"NEW high rate = {100.0 * n_high / total_nc:.1f}%   OLD high rate = {100.0 * 9 / 51:.1f}%")

	if per_piece_times:
		log(
			f"timing: total={total_secs:.1f}s, per-piece avg={np.mean(per_piece_times):.2f}s, "
			f"min={np.min(per_piece_times):.2f}s, max={np.max(per_piece_times):.2f}s"
		)

	# ---- Adaptive search-resolution report (from the engine's own result fields) ----
	# The engine now picks the search resolution so a piece is ~46px across (was a
	# fixed 1600px longest-side cap -> ~25px). Report the ACTUAL values it used.
	W0, H0 = ref_img.size
	exp_side_full = float(np.sqrt((W0 * H0) / float(NUM_PIECES)))
	ok_recs = [r for r in results if r.get("search_dims") is not None]
	search_dims = ok_recs[0]["search_dims"] if ok_recs else None
	search_piece_px = ok_recs[0].get("search_piece_px") if ok_recs else None
	coarse_used = ok_recs[0].get("coarse_scale_factor") if ok_recs else None
	target_reached = ok_recs[0].get("search_target_reached") if ok_recs else None
	peak_integral_mb = max((r.get("integral_mb") or 0.0) for r in ok_recs) if ok_recs else 0.0
	log(
		f"[note] adaptive search: piece ~{exp_side_full:.0f}px full-res -> "
		f"~{(search_piece_px or 0.0):.1f}px in search space "
		f"(coarse={coarse_used}, search_dims={search_dims}, "
		f"peak_integral={peak_integral_mb:.1f}MB, target_reached={target_reached})."
	)

	# ---- 6. Save up to N side-by-side images for 'high' pieces ----
	high_recs = [r for r in results if r["confidence"] == "high" and r.get("best_position")]
	saved_paths: list[str] = []
	log(f"[viz] saving up to {N_HIGH_IMAGES} side-by-side images for 'high' pieces ({len(high_recs)} available)...")
	for i, r in enumerate(high_recs[:N_HIGH_IMAGES], start=1):
		x, y = r["best_position"]
		w, h = r["piece_size_final"]
		# clip to reference bounds
		x0 = max(0, min(int(x), W0 - 1))
		y0 = max(0, min(int(y), H0 - 1))
		x1 = max(x0 + 1, min(int(x) + int(w), W0))
		y1 = max(y0 + 1, min(int(y) + int(h), H0))
		ref_crop = ref_img.crop((x0, y0, x1, y1))
		combo = side_by_side(r["_piece_pil"], ref_crop)
		# NEW names: do not overwrite the baseline match_high_*.png (kept for compare).
		out_path = os.path.join(SCRATCH, f"match_adaptive_{i}.png")
		combo.save(out_path)
		saved_paths.append(out_path)
		log(
			f"[viz] saved {out_path}  (idx={r['index']} sim={r['refined_similarity']:.3f} "
			f"gap={r.get('confidence_gap')} struct={r.get('piece_structure')} "
			f"pos=({x0},{y0}) size=({w},{h}))"
		)

	if not high_recs:
		log("[viz] no 'high' pieces to visualize.")

	# ---- 7. Write eval_summary.txt ----
	summary_path = os.path.join(SCRATCH, "eval_summary.txt")
	with open(summary_path, "w", encoding="utf-8") as fh:
		fh.write("Puzzle Piece Finder - matching engine baseline\n")
		fh.write("=" * 60 + "\n")
		fh.write(f"reference        : {REF_PATH}  size(W,H)={ref_img.size}\n")
		fh.write(f"photo            : {PHOTO_PATH}  size(W,H)={photo_img.size}\n")
		fh.write(f"num_pieces       : {NUM_PIECES}\n")
		fh.write(f"use_downscale    : True (engine's own downscale; no pre-downscale)\n")
		fh.write(f"segmentation     : total={seg['count']} non-cluster={total_nc} clusters={len(clusters)} "
				 f"working_scale={seg.get('working_scale')} bg_model={seg.get('background_model')}\n")
		fh.write(f"segmentation time: {seg_secs:.1f}s\n")
		fh.write("\n")
		fh.write("Laplacian resolution analysis (full-res vs 4x-soft)\n")
		fh.write("-" * 60 + "\n")
		for r in lap_records:
			fh.write(
				f"  {r['kind']:8s} pos={r['pos']} size={r['size']} "
				f"v_full={r['v_full']:.1f} v_soft={r['v_soft']:.1f} ratio={r['ratio']:.2f}\n"
			)
		fh.write(f"  median ratio = {lap_median_ratio:.2f} -> {lap_verdict}\n")
		fh.write("\n")
		fh.write("Confidence distribution (non-cluster)\n")
		fh.write("-" * 60 + "\n")
		fh.write(f"  total non-cluster : {total_nc}\n")
		fh.write(f"  clusters ignored  : {len(clusters)}\n")
		for cls in sorted(conf_counts, key=lambda k: (-conf_counts[k], k)):
			fh.write(f"  {cls:24s}: {conf_counts[cls]}\n")
		fh.write(f"  NEW baseline (high): {n_high}/{total_nc}\n")
		fh.write(f"  OLD baseline (high): 9/51\n")
		fh.write(f"  timing: total={total_secs:.1f}s avg={np.mean(per_piece_times):.2f}s "
				 f"min={np.min(per_piece_times):.2f}s max={np.max(per_piece_times):.2f}s\n"
				 if per_piece_times else "  timing: n/a\n")
		fh.write("\n")
		fh.write("Adaptive search resolution (engine-reported)\n")
		fh.write("-" * 60 + "\n")
		fh.write(f"  target piece side : {46}px (was ~25px at the fixed 1600px cap)\n")
		fh.write(f"  expected side full: ~{exp_side_full:.0f}px\n")
		fh.write(f"  search_dims (W,H) : {search_dims}\n")
		fh.write(f"  search_piece_px   : {search_piece_px}\n")
		fh.write(f"  coarse_scale      : {coarse_used}\n")
		fh.write(f"  peak_integral_mb  : {peak_integral_mb:.1f} (budget 256MB)\n")
		fh.write(f"  target_reached    : {target_reached}\n")
		fh.write("\n")
		fh.write("Per-piece results\n")
		fh.write("-" * 60 + "\n")
		for r in results:
			fh.write(
				f"  idx={r['index']:>3} conf={r['confidence']:<20} "
				f"sim={r.get('refined_similarity')} gap={r.get('confidence_gap')} "
				f"struct={r.get('piece_structure')} pos={r.get('best_position')} "
				f"size={r.get('piece_size_final')} rot={r.get('rotation')} "
				f"scale={r.get('scale')} piece_px={r.get('piece_px')} t={r['time_s']:.2f}s\n"
			)
			fh.write(f"       reason: {r.get('confidence_reason')}\n")
		fh.write("\n")
		fh.write("Saved side-by-side images:\n")
		for p in saved_paths:
			fh.write(f"  {p}\n")

	log(f"[out] wrote summary: {summary_path}")
	log(f"[done] total wall time {total_secs:.1f}s")
	return 0


if __name__ == "__main__":
	sys.exit(main())
