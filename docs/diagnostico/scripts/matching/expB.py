from common import *

def homography(orig, clean):
	f = 2000.0 / orig.shape[1]
	o = cv2.cvtColor(cv2.resize(orig, None, fx=f, fy=f, interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY)
	c = cv2.cvtColor(clean, cv2.COLOR_RGB2GRAY)
	sift = cv2.SIFT_create(nfeatures=8000)
	kc, dc = sift.detectAndCompute(c, None)
	ko, do = sift.detectAndCompute(o, None)
	m = cv2.BFMatcher().knnMatch(dc, do, k=2)
	good = [a for a, b in m if a.distance < 0.75 * b.distance]
	src = np.float32([kc[g.queryIdx].pt for g in good]).reshape(-1, 1, 2)
	dst = np.float32([ko[g.trainIdx].pt for g in good]).reshape(-1, 1, 2) / f
	H, inl = cv2.findHomography(src, dst, cv2.RANSAC, 3.0 / f)
	inl = inl.ravel().astype(bool)
	proj = cv2.perspectiveTransform(src[inl], H)
	err = np.linalg.norm(proj - dst[inl], axis=2).ravel()
	corners = cv2.perspectiveTransform(np.float32([[0, 0], [1599, 0], [1599, 1199], [0, 1199]]).reshape(-1, 1, 2), H).reshape(-1, 2)
	info = {"n_kp_clean": len(kc), "n_kp_orig": len(ko), "n_good": len(good), "n_inliers": int(inl.sum()),
		"reproj_mean_px_full": float(err.mean()), "reproj_median_px_full": float(np.median(err)),
		"reproj_p95_px_full": float(np.percentile(err, 95)), "clean_corners_in_orig": corners.round(1).tolist(), "H": H.tolist()}
	return H, info

def main():
	t0 = time.time()
	refO = Image.open(ORIG).convert("RGB"); refC = Image.open(CLEAN).convert("RGB")
	aO = np.asarray(refO); aC = np.asarray(refC)
	H, hinfo = homography(aO, aC)
	log("homography", {k: v for k, v in hinfo.items() if k != "H"})
	side = float(np.sqrt(aO.shape[0] * aO.shape[1] / 3000.0))
	d = load_seg("verde")
	idxs = [i for i in range(len(d["images"])) if not bool(d["is_cluster"][i])]
	recs = []
	for i in idxs:
		img, m = d["images"][i], d["masks"][i]
		e = {"piece_type": str(d["types"][i])}
		rO, tO = match(refO, img, m, e)
		rC, tC = match(refC, img, m, e)
		cO = centre(rO["best_position"], rO["piece_size_final"])
		cC = centre(rC["best_position"], rC["piece_size_final"])
		cCm = cv2.perspectiveTransform(np.float32([[cC]]), H).ravel().tolist()
		dist = float(np.hypot(cO[0] - cCm[0], cO[1] - cCm[1]))
		# any-candidate agreement (shortlists)
		cOs = cands_centres(rO)
		cCs = [cv2.perspectiveTransform(np.float32([[c]]), H).ravel().tolist() for c in cands_centres(rC)]
		dmin = float(min(np.hypot(a[0] - b[0], a[1] - b[1]) for a in cOs for b in cCs))
		rec = {"idx": i, "type": str(d["types"][i]),
			"orig": {"centre": cO, "pos": rO["best_position"], "size": rO["piece_size_final"], "rot": rO["rotation"], "scale": rO["scale"],
				"conf": rO["confidence"], "gap": rO["confidence_gap"], "struct": rO.get("piece_structure"), "sim": rO["refined_similarity"],
				"cands": cOs, "t": tO},
			"clean": {"centre": cC, "centre_in_orig": cCm, "pos": rC["best_position"], "size": rC["piece_size_final"], "rot": rC["rotation"],
				"scale": rC["scale"], "conf": rC["confidence"], "gap": rC["confidence_gap"], "struct": rC.get("piece_structure"),
				"sim": rC["refined_similarity"], "search_piece_px": rC.get("search_piece_px"), "t": tC},
			"dist_top1_px": dist, "dist_top1_sides": dist / side, "agree_top1": dist < side,
			"min_dist_shortlists_sides": dmin / side, "agree_shortlist": dmin < side,
			"rot_agree": rO["rotation"] == rC["rotation"]}
		recs.append(rec)
		log(f"[{i}] O={rO['confidence']}({rO['confidence_gap']:.2f}) C={rC['confidence']}({rC['confidence_gap']:.2f}) "
			f"dist={dist/side:.2f}side rotO={rO['rotation']} rotC={rC['rotation']} tO={tO:.1f}s tC={tC:.1f}s")
	json.dump({"homography": hinfo, "side_px": side, "records": recs}, open(f"{S}/diag/expB.json", "w"), indent=1)
	log("total", time.time() - t0)

if __name__ == "__main__":
	main()
