from common import *

def feats(d):
	F = []
	for i in range(len(d["masks"])):
		m = (d["masks"][i] > 0).astype(np.uint8)
		area = float(m.sum())
		hu = cv2.HuMoments(cv2.moments(m, binaryImage=True)).ravel()
		hu = -np.sign(hu) * np.log10(np.abs(hu) + 1e-30)
		er = cv2.erode(m, np.ones((15, 15), np.uint8))
		lab = cv2.cvtColor(d["images"][i], cv2.COLOR_RGB2Lab).astype(np.float32)
		col = lab[er > 0].mean(axis=0) if er.sum() > 50 else lab[m > 0].mean(axis=0)
		# rotation-invariant colour spread: std of L, a, b
		sd = lab[er > 0].std(axis=0) if er.sum() > 50 else lab[m > 0].std(axis=0)
		F.append({"area": area, "hu": hu[:4], "col": col, "sd": sd, "cluster": bool(d["is_cluster"][i])})
	return F

def dist(a, b):
	da = abs(np.log(a["area"] / b["area"])) / 0.05          # 5% area diff = 1 unit
	dh = np.abs(a["hu"] - b["hu"]).sum() / 0.3
	dc = np.linalg.norm(a["col"] - b["col"]) / 6.0           # ~6 Lab(uint8) units = 1
	ds = np.linalg.norm(a["sd"] - b["sd"]) / 6.0
	return da + dh + dc + ds

def pair(nameA, nameB):
	A, B = feats(load_seg(nameA)), feats(load_seg(nameB))
	D = np.array([[dist(a, b) for b in B] for a in A])
	out = []
	for i in range(len(A)):
		o = np.argsort(D[i]); j = int(o[0])
		mutual = int(np.argmin(D[:, j])) == i
		ratio = float(D[i, o[1]] / max(D[i, j], 1e-9))
		out.append({"a": i, "b": j, "d1": float(D[i, j]), "d2": float(D[i, o[1]]), "ratio": ratio, "mutual": bool(mutual),
			"area_ratio": A[i]["area"] / B[j]["area"]})
	return out

if __name__ == "__main__":
	p = pair("laranja", "verde")
	conf = [x for x in p if x["mutual"] and x["ratio"] >= 1.5]
	log("pairs total", len(p), "mutual", sum(x["mutual"] for x in p), "mutual&ratio>=1.5", len(conf))
	log("unique b among confident", len(set(x["b"] for x in conf)))
	for x in p:
		log(x)
	json.dump(p, open(f"{S}/diag/pairing.json", "w"), indent=1)
