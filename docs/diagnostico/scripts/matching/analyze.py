from common import *
import collections
refO = Image.open(ORIG).convert("RGB"); refC = Image.open(CLEAN).convert("RGB")
summary = {}


def boxcrop(ref, pos, size):
	x, y = int(pos[0]), int(pos[1]); w, h = int(size[0]), int(size[1])
	return ref.crop((x, y, x + w, y + h))


def frac(a, b):
	return f"{a}/{b} ({100.0*a/b:.0f}%)" if b else "0/0"


def stats(rs):
	n = len(rs)
	hi = [r for r in rs if r["conf"] == "high"]; am = [r for r in rs if r["conf"] != "high"]
	return {"n": n, "top1": frac(sum(r["top1"] for r in rs), n), "top5": frac(sum(r["top5"] for r in rs), n),
		"rot_ok": frac(sum(r["rot_ok"] for r in rs), n),
		"err_med_sides": float(np.median([r["err_sides"] for r in rs])) if rs else None,
		"n_high": len(hi), "high_precision": frac(sum(r["top1"] for r in hi), len(hi)),
		"n_amb": len(am), "amb_top1": frac(sum(r["top1"] for r in am), len(am)), "amb_top5": frac(sum(r["top5"] for r in am), len(am)),
		"t_mean": float(np.mean([r["t"] for r in rs])) if rs else None}


def small(ref, f):
	return ref.resize((int(ref.width * f), int(ref.height * f)), Image.Resampling.LANCZOS)


# ---------------- A ----------------
if os.path.exists(f"{S}/diag/expA.json"):
	A = json.load(open(f"{S}/diag/expA.json"))
	R = A["records"]
	sA = {}
	for tag in ("deg", "limpo"):
		rs = [r for r in R if r["tag"] == tag]
		sA[tag] = stats(rs)
		for reg in ("ceu", "resto"):
			sA[f"{tag}_{reg}"] = stats([r for r in rs if r["region"] == reg])
	# structure-gate breakdown (why ambiguous)
	deg = [r for r in R if r["tag"] == "deg"]
	sA["deg_struct_lt4"] = frac(sum(r["struct"] < 4.0 for r in deg), len(deg))
	sA["deg_struct_lt4_top1"] = frac(sum(r["top1"] for r in deg if r["struct"] < 4.0), sum(r["struct"] < 4.0 for r in deg))
	sA["deg_struct_ge4_top1"] = frac(sum(r["top1"] for r in deg if r["struct"] >= 4.0), sum(r["struct"] >= 4.0 for r in deg))
	sA["deg_gap_ge012_top1"] = frac(sum(r["top1"] for r in deg if r["gap"] >= 0.12), sum(r["gap"] >= 0.12 for r in deg))
	sA["deg_gap_lt012_top1"] = frac(sum(r["top1"] for r in deg if r["gap"] < 0.12), sum(r["gap"] < 0.12 for r in deg))
	sA["deg_rank_hist"] = dict(collections.Counter(str(r["rank_correct"]) for r in deg))
	sA["artwork_bbox"] = A["artwork_bbox"]
	summary["A"] = sA
	for k, v in sA.items():
		log("A", k, v)
	pick = ([r for r in deg if r["conf"] == "high" and r["top1"]][:3] + [r for r in deg if r["conf"] == "high" and not r["top1"]][:3]
		+ [r for r in deg if r["conf"] != "high" and r["top1"]][:2] + [r for r in deg if r["conf"] != "high" and r["top5"] and not r["top1"]][:2])
	pick += [r for r in deg if r["conf"] != "high" and not r["top5"]][:12 - len(pick)]
	rows, labs = [], []
	for r in pick:
		z = np.load(f"{S}/diag/A_deg_{r['j']:02d}.npz")
		pc = Image.fromarray(np.rot90(z["piece"], r["rot_pred"] // 90))
		x, y, w, h = r["box"]
		rows.append([pc, boxcrop(refO, (r["pred_centre"][0] - r["size"][0] / 2, r["pred_centre"][1] - r["size"][1] / 2), r["size"]),
			refO.crop((x, y, x + w, y + h))])
		labs.append(f"deg#{r['j']} {r['region']} conf={r['conf']} gap={r['gap']:.2f} struct={r['struct']:.1f} err={r['err_sides']:.2f} lados "
			f"top1={r['top1']} top5={r['top5']} rot_ok={r['rot_ok']}")
	montage(rows, labs, "A: peca sintetica (rodada pela rotacao prevista) | ref na posicao PREVISTA | ref na posicao VERDADEIRA",
		path=f"{OUT}/A_montagem.png")
	f = 0.25; im = small(refO, f); dr = ImageDraw.Draw(im); fn = font(14)
	x0, y0, x1, y1 = A["artwork_bbox"]; dr.rectangle([x0 * f, y0 * f, x1 * f, y1 * f], outline=(255, 255, 255), width=2)
	yy = (y0 + 0.4 * (y1 - y0)) * f; dr.line([x0 * f, yy, x1 * f, yy], fill=(255, 255, 255), width=1)
	for r in deg:
		t = [v * f for v in r["true_centre"]]; p = [v * f for v in r["pred_centre"]]
		dr.line([t[0], t[1], p[0], p[1]], fill=(255, 60, 60) if not r["top1"] else (0, 255, 0), width=2)
		dr.ellipse([t[0] - 5, t[1] - 5, t[0] + 5, t[1] + 5], outline=(0, 255, 0), width=3)
		dr.ellipse([p[0] - 4, p[1] - 4, p[0] + 4, p[1] + 4], fill=(255, 0, 0))
		dr.text((t[0] + 6, t[1] - 6), str(r["j"]) + ("H" if r["conf"] == "high" else ""), fill=(255, 255, 0), font=fn)
	im.save(f"{OUT}/A_referencia_anotada.png")

# ---------------- B ----------------
if os.path.exists(f"{S}/diag/expB.json"):
	B = json.load(open(f"{S}/diag/expB.json"))
	R = B["records"]; n = len(R)
	cO = collections.Counter(r["orig"]["conf"] for r in R); cC = collections.Counter(r["clean"]["conf"] for r in R)
	hh = [r for r in R if r["orig"]["conf"] == "high" and r["clean"]["conf"] == "high"]
	anyh = [r for r in R if "high" in (r["orig"]["conf"], r["clean"]["conf"])]
	sB = {"n": n, "conf_orig": dict(cO), "conf_clean": dict(cC),
		"t_orig_mean": float(np.mean([r["orig"]["t"] for r in R])), "t_clean_mean": float(np.mean([r["clean"]["t"] for r in R])),
		"t_orig_med": float(np.median([r["orig"]["t"] for r in R])), "t_clean_med": float(np.median([r["clean"]["t"] for r in R])),
		"agree_top1": frac(sum(r["agree_top1"] for r in R), n), "agree_shortlist": frac(sum(r["agree_shortlist"] for r in R), n),
		"agree_top1_high_both": frac(sum(r["agree_top1"] for r in hh), len(hh)), "n_high_both": len(hh),
		"agree_top1_high_any": frac(sum(r["agree_top1"] for r in anyh), len(anyh)),
		"rot_agree": frac(sum(r["rot_agree"] for r in R), n), "dist_med_sides": float(np.median([r["dist_top1_sides"] for r in R])),
		"homography": {k: v for k, v in B["homography"].items() if k != "H"},
		"clean_size_px_median": float(np.median([np.sqrt(r["clean"]["size"][0] * r["clean"]["size"][1]) for r in R])),
		"orig_size_px_median": float(np.median([np.sqrt(r["orig"]["size"][0] * r["orig"]["size"][1]) for r in R]))}
	cs = np.array([r["orig"]["centre"] for r in R]); cm = np.array([r["clean"]["centre_in_orig"] for r in R])
	D = np.hypot(cs[:, None, 0] - cm[None, :, 0], cs[:, None, 1] - cm[None, :, 1])
	off = ~np.eye(n, dtype=bool)
	sB["chance_agree_offdiag"] = float((D[off] < B["side_px"]).mean())
	summary["B"] = sB
	for k, v in sB.items():
		log("B", k, v)
	f = 0.25; im = small(refO, f); dr = ImageDraw.Draw(im); fn = font(14)
	for r in R:
		p = [v * f for v in r["orig"]["centre"]]; q = [v * f for v in r["clean"]["centre_in_orig"]]
		dr.line([p[0], p[1], q[0], q[1]], fill=(0, 255, 0) if r["agree_top1"] else (255, 255, 255), width=1)
		dr.ellipse([p[0] - 5, p[1] - 5, p[0] + 5, p[1] + 5], fill=(255, 0, 0) if r["orig"]["conf"] == "high" else None, outline=(255, 0, 0), width=2)
		dr.rectangle([q[0] - 5, q[1] - 5, q[0] + 5, q[1] + 5], fill=(0, 120, 255) if r["clean"]["conf"] == "high" else None, outline=(0, 120, 255), width=2)
		dr.text((p[0] + 6, p[1] - 7), str(r["idx"]), fill=(255, 255, 0), font=fn)
		dr.text((q[0] + 6, q[1] - 7), str(r["idx"]), fill=(150, 220, 255), font=fn)
	im.save(f"{OUT}/B_referencias_anotada.png")
	d = load_seg("verde")

	def row(r):
		img = d["images"][r["idx"]]
		return ([Image.fromarray(np.rot90(img, r["orig"]["rot"] // 90)), boxcrop(refO, r["orig"]["pos"], r["orig"]["size"]),
			Image.fromarray(np.rot90(img, r["clean"]["rot"] // 90)), boxcrop(refC, r["clean"]["pos"], r["clean"]["size"])],
			f"verde#{r['idx']} {r['type']} | Orig: {r['orig']['conf']} gap={r['orig']['gap']:.2f} rot={r['orig']['rot']} | "
			f"Limpa: {r['clean']['conf']} gap={r['clean']['gap']:.2f} rot={r['clean']['rot']} | dist={r['dist_top1_sides']:.1f} lados")
	order = sorted(R, key=lambda r: (not r["agree_top1"], -int(r["orig"]["conf"] == "high") - int(r["clean"]["conf"] == "high")))
	sel = order[:5]
	sel += [r for r in order if r not in sel and "high" in (r["orig"]["conf"], r["clean"]["conf"])][:10 - len(sel)]
	rr = [row(r) for r in sel]
	montage([a for a, b in rr], [b for a, b in rr], "B: peca (rot. Orig) | crop Orig previsto | peca (rot. Limpa) | crop Limpa previsto",
		path=f"{OUT}/B_montagem_10.png")
	for part in range(0, n, 16):
		rr = [row(r) for r in R[part:part + 16]]
		montage([a for a, b in rr], [b for a, b in rr], f"B (todas, {part}-{part+15}): peca | Orig previsto | peca | Limpa previsto",
			height=120, path=f"{OUT}/B_montagem_todas_{part:02d}.png")

# ---------------- C ----------------
if os.path.exists(f"{S}/diag/expC.json") and os.path.exists(f"{S}/diag/expB.json"):
	C = json.load(open(f"{S}/diag/expC.json"))
	byV = {r["idx"]: r for r in B["records"]}
	side = B["side_px"]
	rows = []
	for c in C:
		v = byV.get(c["verde"])
		if v is None:
			continue
		dd = float(np.hypot(c["centre"][0] - v["orig"]["centre"][0], c["centre"][1] - v["orig"]["centre"][1])) / side
		dmin = min(float(np.hypot(a[0] - b[0], a[1] - b[1])) for a in c["cands"] for b in v["orig"]["cands"]) / side
		c.update({"dist_sides": dd, "agree": dd < 1.0, "agree_shortlist": dmin < 1.0, "conf_verde": v["orig"]["conf"]})
		rows.append(c)
	hh = [c for c in rows if c["conf"] == "high" and c["conf_verde"] == "high"]
	sC = {"n_pairs": len(rows), "agree_top1": frac(sum(c["agree"] for c in rows), len(rows)),
		"agree_shortlist": frac(sum(c["agree_shortlist"] for c in rows), len(rows)),
		"n_high_both": len(hh), "agree_high_both": frac(sum(c["agree"] for c in hh), len(hh)),
		"label_same": frac(sum(c["conf"] == c["conf_verde"] for c in rows), len(rows)),
		"conf_laranja": dict(collections.Counter(c["conf"] for c in rows)), "t_mean": float(np.mean([c["t"] for c in rows]))}
	summary["C"] = sC
	for k, v in sC.items():
		log("C", k, v)
	L = load_seg("laranja"); V = load_seg("verde")
	rr = []
	for c in rows[:14]:
		rr.append(([Image.fromarray(L["images"][c["laranja"]]), Image.fromarray(V["images"][c["verde"]]),
			boxcrop(refO, c["pos"], c["size"]), boxcrop(refO, byV[c["verde"]]["orig"]["pos"], byV[c["verde"]]["orig"]["size"])],
			f"laranja#{c['laranja']} <-> verde#{c['verde']} (ratio {c['pair_ratio']:.1f}) | L:{c['conf']} V:{c['conf_verde']} dist={c['dist_sides']:.1f} lados"))
	montage([a for a, b in rr], [b for a, b in rr], "C: peca laranja | peca verde emparelhada | Orig previsto (laranja) | Orig previsto (verde)",
		height=120, path=f"{OUT}/C_pares_montagem.png")
	json.dump(rows, open(f"{S}/diag/expC_rows.json", "w"), indent=1)

res = {"summary": summary}
for k in ("A", "B"):
	if os.path.exists(f"{S}/diag/exp{k}.json"):
		res["exp" + k] = json.load(open(f"{S}/diag/exp{k}.json"))
if os.path.exists(f"{S}/diag/expC_rows.json"):
	res["expC"] = json.load(open(f"{S}/diag/expC_rows.json"))
	res["expC_pairing"] = json.load(open(f"{S}/diag/pairing.json"))
json.dump(res, open(f"{OUT}/results.json", "w"), indent=1, default=str)
log("written")
