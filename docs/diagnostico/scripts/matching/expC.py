from common import *
p = json.load(open(f"{S}/diag/pairing.json"))
conf = [x for x in p if x["mutual"] and x["ratio"] >= 1.5]
NMAX = int(sys.argv[1]) if len(sys.argv) > 1 else len(conf)
conf = conf[::max(1, len(conf) // NMAX)][:NMAX]
log("C pairs used", len(conf))
refO = Image.open(ORIG).convert("RGB")
d = load_seg("laranja")
recs = []
t0 = time.time()
for x in conf:
	i = x["a"]
	r, t = match(refO, d["images"][i], d["masks"][i], {"piece_type": str(d["types"][i])})
	recs.append({"laranja": i, "verde": x["b"], "pair_ratio": x["ratio"], "centre": centre(r["best_position"], r["piece_size_final"]),
		"pos": r["best_position"], "size": r["piece_size_final"], "rot": r["rotation"], "conf": r["confidence"], "gap": r["confidence_gap"],
		"struct": r.get("piece_structure"), "cands": cands_centres(r), "t": t})
	log(f"[L{i}->V{x['b']}] {r['confidence']} {r['confidence_gap']:.2f} t={t:.1f}")
json.dump(recs, open(f"{S}/diag/expC.json", "w"), indent=1)
log("total", time.time() - t0)
