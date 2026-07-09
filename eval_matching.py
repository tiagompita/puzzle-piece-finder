"""Evaluation harness for the MATCHING ENGINE (not the GUI).

Stage-A "colour-twins" A/B: measures ``src.matching.multi_scale_template_match``
on the real photo IMG_2114 (num_pieces=3000, engine's own downscale, correct
per-piece mask) in two configurations, segmenting and edge-classifying ONCE:

  A (baseline) : use_texture=False, piece_edges=None   -> colour-only re-rank
  B (stage A)  : use_texture=True  + edges border prior -> colour + gradient texture

The pieces are edge-classified with ``src.edges.classify_pieces`` so each piece's
``piece_type`` feeds the engine's border prior in the B run. The confidence
distribution of each run is reported against the frozen 5/64 colour baseline.

This file lives at the repo root and imports src/ as a package. Run from the repo
root:  ``python eval_matching.py``.  Only this harness is modified.
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np
from PIL import Image

# Import src/ as a package (src has __init__.py; modules use relative imports).
from src.segmentation import segment_pieces
from src.edges import classify_pieces
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
BASELINE_TXT = "5/64 (colour-only)"


def log(msg: str) -> None:
	"""Print with immediate flush so progress is visible during long runs."""
	print(msg, flush=True)


def to_pil_rgb(obj) -> Image.Image:
	"""Coerce a piece['image'] (PIL Image here) or ndarray to PIL RGB."""
	if isinstance(obj, Image.Image):
		return obj.convert("RGB")
	return Image.fromarray(np.asarray(obj)).convert("RGB")


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


def run_match(ref_img, piece_pil, mask, *, use_texture, piece_edges):
	"""One engine call; returns (result_dict_or_error, seconds)."""
	t = time.time()
	try:
		res = multi_scale_template_match(
			puzzle_img=ref_img,
			piece_img=piece_pil,
			num_pieces=NUM_PIECES,
			piece_mask=mask,
			use_downscale=True,
			use_texture=use_texture,
			piece_edges=piece_edges,
		)
	except Exception as exc:  # noqa: BLE001
		res = {"error": f"exception:{exc!r}"}
	return res, time.time() - t


def main() -> int:
	os.makedirs(SCRATCH, exist_ok=True)
	t0 = time.time()

	log(f"[load] reference: {REF_PATH}")
	ref_img = Image.open(REF_PATH).convert("RGB")
	W0, H0 = ref_img.size
	log(f"[load] reference size (W,H) = {ref_img.size}")

	log(f"[load] photo: {PHOTO_PATH}")
	photo_img = Image.open(PHOTO_PATH).convert("RGB")
	log(f"[load] photo size (W,H) = {photo_img.size}")

	log("[seg] segmenting photo (segment_pieces, PIL RGB in)...")
	t_seg = time.time()
	seg = segment_pieces(photo_img)
	seg_secs = time.time() - t_seg
	if "error" in seg:
		log(f"[FATAL] segmentation failed: {seg.get('error')!r}")
		return 3
	pieces = seg["pieces"]
	classify_pieces(pieces)  # enrich each piece with piece_type / edge fields in place
	clusters = [p for p in pieces if p.get("is_cluster")]
	non_cluster = [p for p in pieces if not p.get("is_cluster")]
	pt_counts: dict[str, int] = {}
	for p in non_cluster:
		pt_counts[p.get("piece_type", "?")] = pt_counts.get(p.get("piece_type", "?"), 0) + 1
	log(
		f"[seg] done in {seg_secs:.1f}s: total={seg['count']} non-cluster={len(non_cluster)} "
		f"clusters(ignored)={len(clusters)} working_scale={seg.get('working_scale'):.4f} "
		f"bg_model={seg.get('background_model')}"
	)
	log(f"[edges] piece_type distribution (non-cluster): {pt_counts}")

	total_nc = len(non_cluster)
	conf_A: dict[str, int] = {}
	conf_B: dict[str, int] = {}
	times_A: list[float] = []
	times_B: list[float] = []
	records: list[dict] = []

	log(f"[match] A/B over {total_nc} non-cluster pieces (num_pieces={NUM_PIECES})...")
	for n, piece in enumerate(non_cluster, start=1):
		idx = piece.get("index", n - 1)
		piece_pil = to_pil_rgb(piece["image"])
		mask = piece.get("mask")

		res_a, dta = run_match(ref_img, piece_pil, mask, use_texture=False, piece_edges=None)
		res_b, dtb = run_match(ref_img, piece_pil, mask, use_texture=True, piece_edges=piece)
		times_A.append(dta)
		times_B.append(dtb)

		ca = res_a.get("confidence", f"error:{res_a.get('error')}")
		cb = res_b.get("confidence", f"error:{res_b.get('error')}")
		conf_A[ca] = conf_A.get(ca, 0) + 1
		conf_B[cb] = conf_B.get(cb, 0) + 1

		rec = {
			"index": idx,
			"piece_type": piece.get("piece_type"),
			"piece_px": piece_pil.size,
			"conf_A": ca,
			"conf_B": cb,
			"sim_A": res_a.get("refined_similarity"),
			"sim_B": res_b.get("refined_similarity"),
			"gap_A": res_a.get("confidence_gap"),
			"gap_B": res_b.get("confidence_gap"),
			"struct_B": res_b.get("piece_structure"),
			"d_grad_B": res_b.get("d_grad"),
			"cost_comb_B": res_b.get("cost_comb"),
			"pos_A": res_a.get("best_position"),
			"pos_B": res_b.get("best_position"),
			"size_B": res_b.get("piece_size_final"),
			"rot_B": res_b.get("rotation"),
			"edge_type_B": res_b.get("edge_prior_type"),
			"reason_B": res_b.get("confidence_reason"),
			"t_A": dta,
			"t_B": dtb,
			"_piece_pil": piece_pil,
		}
		records.append(rec)
		moved = "" if ca == cb else f"  [{ca}->{cb}]"
		log(
			f"[match] {n}/{total_nc} idx={idx} pt={rec['piece_type']} "
			f"A={ca} B={cb}{moved} d_grad={rec['d_grad_B']} "
			f"gapA={rec['gap_A']} gapB={rec['gap_B']} tA={dta:.2f}s tB={dtb:.2f}s"
		)

	total_secs = time.time() - t0

	def dist_str(counts: dict[str, int]) -> str:
		return ", ".join(f"{k}={counts[k]}" for k in sorted(counts, key=lambda k: (-counts[k], k)))

	high_A = conf_A.get("high", 0)
	high_B = conf_B.get("high", 0)
	log("")
	log("=" * 64)
	log("A/B CONFIDENCE DISTRIBUTION (non-cluster)")
	log("=" * 64)
	log(f"total non-cluster : {total_nc}   frozen baseline: {BASELINE_TXT}")
	log(f"A (texture OFF)   : {dist_str(conf_A)}   -> high {high_A}/{total_nc}")
	log(f"B (texture ON)    : {dist_str(conf_B)}   -> high {high_B}/{total_nc}")

	# Which pieces changed label between A and B.
	promoted = [r["index"] for r in records if r["conf_A"] != "high" and r["conf_B"] == "high"]
	demoted = [r["index"] for r in records if r["conf_A"] == "high" and r["conf_B"] != "high"]
	stayed_high = [r["index"] for r in records if r["conf_A"] == "high" and r["conf_B"] == "high"]
	log(f"stayed high (A&B) : {stayed_high}")
	log(f"promoted (A->B)   : {promoted}")
	log(f"demoted  (A->B)   : {demoted}")
	log(
		f"timing: A avg={np.mean(times_A):.2f}s B avg={np.mean(times_B):.2f}s "
		f"(prev colour-only ~2.46s); total wall={total_secs:.1f}s"
	)

	# Save side-by-side crops for the B 'high' pieces.
	high_recs = [r for r in records if r["conf_B"] == "high" and r.get("pos_B")]
	saved_paths: list[str] = []
	log(f"[viz] saving up to {N_HIGH_IMAGES} side-by-side images for B-high pieces ({len(high_recs)} available)...")
	for i, r in enumerate(high_recs[:N_HIGH_IMAGES], start=1):
		x, y = r["pos_B"]
		w, h = r["size_B"]
		x0 = max(0, min(int(x), W0 - 1))
		y0 = max(0, min(int(y), H0 - 1))
		x1 = max(x0 + 1, min(int(x) + int(w), W0))
		y1 = max(y0 + 1, min(int(y) + int(h), H0))
		ref_crop = ref_img.crop((x0, y0, x1, y1))
		combo = side_by_side(r["_piece_pil"], ref_crop)
		out_path = os.path.join(SCRATCH, f"match_texture_{i}.png")
		combo.save(out_path)
		saved_paths.append(out_path)
		log(
			f"[viz] saved {out_path} (idx={r['index']} pt={r['piece_type']} "
			f"sim={r['sim_B']:.3f} d_grad={r['d_grad_B']:.3f} gapB={r['gap_B']:.3f} "
			f"was_A={r['conf_A']} pos=({x0},{y0}) size=({w},{h}))"
		)

	# ---- Write eval_summary.txt ----
	summary_path = os.path.join(SCRATCH, "eval_summary.txt")
	with open(summary_path, "w", encoding="utf-8") as fh:
		fh.write("Puzzle Piece Finder - matching engine, Stage-A texture A/B\n")
		fh.write("=" * 64 + "\n")
		fh.write(f"reference        : {REF_PATH}  size(W,H)={ref_img.size}\n")
		fh.write(f"photo            : {PHOTO_PATH}  size(W,H)={photo_img.size}\n")
		fh.write(f"num_pieces       : {NUM_PIECES}\n")
		fh.write(f"segmentation     : total={seg['count']} non-cluster={total_nc} clusters={len(clusters)} "
				 f"working_scale={seg.get('working_scale')} bg_model={seg.get('background_model')}\n")
		fh.write(f"edge piece_types : {pt_counts}\n")
		fh.write("\n")
		fh.write("A/B confidence distribution (non-cluster)\n")
		fh.write("-" * 64 + "\n")
		fh.write(f"  frozen baseline : {BASELINE_TXT}\n")
		fh.write(f"  A (texture OFF) : {dist_str(conf_A)}  -> high {high_A}/{total_nc}\n")
		fh.write(f"  B (texture ON)  : {dist_str(conf_B)}  -> high {high_B}/{total_nc}\n")
		fh.write(f"  stayed high     : {stayed_high}\n")
		fh.write(f"  promoted A->B   : {promoted}\n")
		fh.write(f"  demoted  A->B   : {demoted}\n")
		fh.write(f"  timing: A avg={np.mean(times_A):.2f}s B avg={np.mean(times_B):.2f}s "
				 f"(prev colour-only ~2.46s) total={total_secs:.1f}s\n")
		fh.write("\n")
		fh.write("Per-piece A/B results\n")
		fh.write("-" * 64 + "\n")
		for r in records:
			fh.write(
				f"  idx={r['index']:>3} pt={str(r['piece_type']):<8} A={r['conf_A']:<10} B={r['conf_B']:<10} "
				f"simB={r['sim_B']} gapA={r['gap_A']} gapB={r['gap_B']} structB={r['struct_B']} "
				f"d_grad={r['d_grad_B']} cost_combB={r['cost_comb_B']} posB={r['pos_B']} "
				f"sizeB={r['size_B']} rotB={r['rot_B']} tA={r['t_A']:.2f}s tB={r['t_B']:.2f}s\n"
			)
			fh.write(f"       reasonB: {r['reason_B']}\n")
		fh.write("\n")
		fh.write("Saved B-high side-by-side images:\n")
		for p in saved_paths:
			fh.write(f"  {p}\n")

	log(f"[out] wrote summary: {summary_path}")
	log(f"[done] total wall time {total_secs:.1f}s")
	return 0


if __name__ == "__main__":
	sys.exit(main())
