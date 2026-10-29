from common import *

SIDE = 127.0

def make_piece(aO, art, mask_src, rng, degrade):
	x0, y0, x1, y1 = art
	m = (mask_src > 0).astype(np.uint8) * 255
	ys, xs = np.where(m > 0)
	m = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
	h, w = m.shape
	f = SIDE / np.sqrt(h * w)
	nw, nh = max(8, int(round(w * f))), max(8, int(round(h * f)))
	m = cv2.resize(m, (nw, nh), interpolation=cv2.INTER_NEAREST)
	pad = 0.6 * SIDE
	cx = rng.uniform(x0 + pad + nw / 2, x1 - pad - nw / 2)
	cy = rng.uniform(y0 + pad + nh / 2, y1 - pad - nh / 2)
	px, py = int(round(cx - nw / 2)), int(round(cy - nh / 2))
	crop = aO[py:py + nh, px:px + nw].copy()
	true_c = (px + nw / 2.0, py + nh / 2.0)
	shift = None
	if degrade:
		crop = cv2.GaussianBlur(crop, (0, 0), 1.0)
		lab = cv2.cvtColor(crop, cv2.COLOR_RGB2Lab).astype(np.float32)
		dL, da, db = rng.uniform(-6, 6), rng.uniform(-3, 3), rng.uniform(-3, 3)
		lab[:, :, 0] += dL * 255.0 / 100.0; lab[:, :, 1] += da; lab[:, :, 2] += db
		crop = cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_Lab2RGB)
		shift = [dL, da, db]
	mb = m > 0
	mean = crop[mb].mean(axis=0)
	crop[~mb] = mean.astype(np.uint8)
	k = int(rng.integers(0, 4))
	return np.ascontiguousarray(np.rot90(crop, k)), np.ascontiguousarray(np.rot90(m, k)), k, true_c, (px, py, nw, nh), shift

def run(refO, aO, art, masks, n, seed, degrade, tag):
	rng = np.random.default_rng(seed)
	recs = []
	sky_y = art[1] + 0.4 * (art[3] - art[1])
	for j in range(n):
		mi = int(rng.integers(0, len(masks)))
		piece, m, k, tc, box, shift = make_piece(aO, art, masks[mi], rng, degrade)
		res, dt = match(refO, piece, m, None)
		pc = centre(res["best_position"], res["piece_size_final"])
		err = float(np.hypot(pc[0] - tc[0], pc[1] - tc[1]))
		cerr = [float(np.hypot(c[0] - tc[0], c[1] - tc[1])) for c in cands_centres(res)]
		rot_ok = ((k + res["rotation"] // 90) % 4) == 0
		rank = next((r for r, e in enumerate(cerr) if e < SIDE / 2), None)
		rec = {"tag": tag, "j": j, "mask_idx": mi, "rot_applied_k": k, "true_centre": tc, "box": box, "lab_shift": shift,
			"region": "ceu" if tc[1] < sky_y else "resto", "pred_centre": pc, "err_px": err, "err_sides": err / SIDE,
			"top1": err < SIDE / 2, "top5": rank is not None, "rank_correct": rank, "n_cands": len(cerr),
			"rot_pred": res["rotation"], "rot_ok": bool(rot_ok), "scale": res["scale"], "size": res["piece_size_final"],
			"conf": res["confidence"], "gap": res["confidence_gap"], "struct": res.get("piece_structure"),
			"reason": res.get("confidence_reason"), "t": dt}
		recs.append(rec)
		np.savez_compressed(f"{S}/diag/A_{tag}_{j:02d}.npz", piece=piece, mask=m)
		log(f"[{tag} {j}] {rec['region']} err={err/SIDE:.2f}side top1={rec['top1']} top5={rec['top5']} rank={rank} rot_ok={rot_ok} "
			f"conf={rec['conf']} gap={rec['gap']:.2f} struct={rec['struct']:.2f} t={dt:.1f}s")
	return recs

def main():
	t0 = time.time()
	refO = Image.open(ORIG).convert("RGB"); aO = np.asarray(refO)
	art = detect_artwork(aO)
	log("artwork bbox", art)
	d = load_seg("verde")
	masks = [d["masks"][i] for i in range(len(d["masks"])) if not bool(d["is_cluster"][i])]
	n_deg = int(sys.argv[1]) if len(sys.argv) > 1 else 60
	n_clean = int(sys.argv[2]) if len(sys.argv) > 2 else 20
	recs = run(refO, aO, art, masks, n_deg, 123, True, "deg")
	recs += run(refO, aO, art, masks, n_clean, 456, False, "limpo")
	json.dump({"artwork_bbox": art, "side_px": SIDE, "records": recs}, open(f"{S}/diag/expA.json", "w"), indent=1)
	log("total", time.time() - t0)

if __name__ == "__main__":
	main()
