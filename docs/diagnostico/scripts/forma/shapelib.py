"""Shape analysis helpers for the forma diagnostic (scratch only)."""
import numpy as np, cv2

MM = 25.4 / 300.0          # mm per px at 300 dpi
OPEN_R_MM = 3.5            # opening disk radius (mm) to remove tabs
NS = 64                    # samples per side
TAB_T = 0.15               # tab/blank threshold (fraction of side length)


def load(path):
	d = np.load(path, allow_pickle=True)
	out = []
	for i in range(len(d['contours'])):
		if bool(d['is_cluster'][i]):
			continue
		out.append(dict(idx=i, contour=np.asarray(d['contours'][i]).reshape(-1, 2).astype(np.float64),
						type=str(d['types'][i]), straight=int(d['straight'][i]),
						image=d['images'][i], bbox=d['bboxes'][i]))
	return out


def ccw(c):
	# make orientation consistent: positive signed area in image coords (y down)
	x, y = c[:, 0], c[:, 1]
	a = 0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)
	return c if a > 0 else c[::-1].copy()


def resample_closed(c, n):
	p = np.vstack([c, c[:1]])
	seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
	s = np.concatenate([[0], np.cumsum(seg)])
	t = np.linspace(0, s[-1], n, endpoint=False)
	return np.c_[np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])]


def resample_open(p, n):
	seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
	s = np.concatenate([[0], np.cumsum(seg)])
	t = np.linspace(0, s[-1], n)
	return np.c_[np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])]


def local_mask(c, pad=10):
	o = c.min(0) - pad
	cc = np.round(c - o).astype(np.int32)
	h, w = cc[:, 1].max() + pad + 1, cc[:, 0].max() + pad + 1
	m = np.zeros((h, w), np.uint8)
	cv2.fillPoly(m, [cc.reshape(-1, 1, 2)], 255)
	return m, o


def body(c):
	"""Opened ('tab-free') body: returns minAreaRect of the opened mask (orig coords) + opened contour."""
	m, o = local_mask(c, pad=60)
	r = int(round(OPEN_R_MM / MM))
	k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
	op = cv2.morphologyEx(m, cv2.MORPH_OPEN, k)
	cs, _ = cv2.findContours(op, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
	if not cs:
		return None, None
	bc = max(cs, key=cv2.contourArea).reshape(-1, 2).astype(np.float64) + o
	rect = cv2.minAreaRect(bc.astype(np.float32))
	return rect, bc


def turn_angle(c, i, k):
	n = len(c)
	a = c[(i - k) % n] - c[i]; b = c[(i + k) % n] - c[i]
	cosv = a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9)
	return float(np.degrees(np.arccos(np.clip(cosv, -1, 1))))


def find_corners(c, rect):
	"""Corner detection: rect corners of the opened body, refined to the contour point that is
	most extreme along the rect diagonal direction within a radius of 0.18*side around the rect corner."""
	box = cv2.boxPoints(rect).astype(np.float64)
	ctr = np.array(rect[0])
	side = float(np.mean(rect[1]))
	R = 0.18 * side
	idx = []
	for b in box:
		d = (b - ctr); d /= np.linalg.norm(d)
		dist = np.linalg.norm(c - b, axis=1)
		cand = np.where(dist < R)[0]
		if len(cand) == 0:
			cand = np.array([int(np.argmin(dist))])
		score = (c[cand] - ctr) @ d
		idx.append(int(cand[np.argmax(score)]))
	# order corners along contour
	idx = sorted(idx)
	return idx


def split_sides(c, idx):
	n = len(c); sides = []
	for k in range(4):
		a, b = idx[k], idx[(k + 1) % 4]
		seg = c[a:b + 1] if b > a else np.vstack([c[a:], c[:b + 1]])
		sides.append(seg)
	return sides


def normalise_side(seg, ctr):
	p0, p1 = seg[0], seg[-1]
	L = float(np.linalg.norm(p1 - p0))
	u = (p1 - p0) / L; v = np.array([-u[1], u[0]])
	q = np.c_[(seg - p0) @ u, (seg - p0) @ v] / L
	cy = ((ctr - p0) @ v) / L
	if cy > 0:          # make outward = +y
		q[:, 1] *= -1
	return resample_open(q, NS), L


def classify_side(prof):
	mx, mn = prof[:, 1].max(), prof[:, 1].min()
	if mx > TAB_T and mx >= -mn:
		return 'T'
	if -mn > TAB_T:
		return 'B'
	return 'F'


def canon(t):
	s = ''.join(t)
	return min(s[k:] + s[:k] for k in range(4))


def analyse(p):
	c = ccw(resample_closed(p['contour'], 1200))
	rect, bc = body(c)
	idx = find_corners(c, rect)
	ctr = c.mean(0)
	sides = split_sides(c, idx)
	profs, lens, types, ang = [], [], [], []
	for s in sides:
		pr, L = normalise_side(s, ctr)
		profs.append(pr); lens.append(L * MM); types.append(classify_side(pr))
	k = max(3, int(round(1.5 / MM / (np.linalg.norm(c[1] - c[0]) + 1e-9))))  # ~1.5 mm arc
	ang = [turn_angle(c, i, k) for i in idx]
	# corner-polygon interior angles
	P = c[idx]
	pa = []
	for j in range(4):
		a = P[j - 1] - P[j]; b = P[(j + 1) % 4] - P[j]
		pa.append(float(np.degrees(np.arccos(np.clip(a @ b / np.linalg.norm(a) / np.linalg.norm(b), -1, 1)))))
	# shape vector: each side resampled to 64 (drop last point) in original px
	vec = np.vstack([resample_open(s, NS + 1)[:-1] for s in sides])
	p.update(c=c, rect=rect, bodyc=bc, corners=idx, sides=sides, profs=profs, lens=lens, types=types,
			 cls=canon(types), corner_turn=ang, poly_ang=pa, vec=vec,
			 body_w=max(rect[1]) * MM, body_h=min(rect[1]) * MM)
	return p


def kabsch_rms(A, B):
	"""min over rotation R of RMS ||A R - B|| (both centred). no reflection."""
	H = A.T @ B
	U, S, Vt = np.linalg.svd(H)
	dd = np.sign(np.linalg.det(U @ Vt))
	D = np.diag([1, dd])
	R = U @ D @ Vt
	return float(np.sqrt(np.mean(np.sum((A @ R - B) ** 2, axis=1)))), R


def shape_dist(pa, pb, scale=None):
	"""Rotation-invariant: 4 cyclic corner alignments x Kabsch rotation. Returns (dist_mm, best_k, R)."""
	A = pa['vec'] - pa['vec'].mean(0)
	best = (1e9, 0, None)
	for k in range(4):
		B = np.roll(pb['vec'], -k * NS, axis=0)
		B = B - B.mean(0)
		d, R = kabsch_rms(A, B)
		if d < best[0]:
			best = (d, k, R)
	return best[0] * MM, best[1], best[2]


# ---------------- v2: curvature-candidate + rectangle-fit corner search ----------------
import itertools

def smooth_closed(c, sigma_pts):
	if sigma_pts <= 0:
		return c
	n = len(c); r = int(3 * sigma_pts)
	k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma_pts) ** 2); k /= k.sum()
	out = np.empty_like(c)
	for d in range(2):
		x = np.concatenate([c[-r:, d], c[:, d], c[:r, d]])
		out[:, d] = np.convolve(x, k, mode='valid')
	return out


def corner_scores(c, step_mm):
	"""Signed angle between chords to +/-k points (deg) at arc ~step_mm; convex if cross>0 (ccw)."""
	n = len(c); per = np.sum(np.linalg.norm(np.diff(np.vstack([c, c[:1]]), axis=0), axis=1))
	k = max(2, int(round(step_mm / MM / (per / n))))
	a = np.roll(c, k, axis=0) - c; b = np.roll(c, -k, axis=0) - c
	cosv = np.sum(a * b, 1) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1) + 1e-9)
	ang = np.degrees(np.arccos(np.clip(cosv, -1, 1)))
	# convexity: for ccw (positive area, y-down image coords => visually cw) use cross of (prev->p, p->next)
	u = c - np.roll(c, k, axis=0); v = np.roll(c, -k, axis=0) - c
	cross = u[:, 0] * v[:, 1] - u[:, 1] * v[:, 0]
	return ang, cross > 0, k


def find_corners_v2(c, ncand=20, LMIN=14.0, LMAX=23.0, W_OPP=4.0, W_AB=3.0):
	"""Corner search. (1) candidates = convex points whose chord angle is near 90 deg at two arc
	scales (1.2 mm and 2.5 mm) on a lightly smoothed contour, NMS 2 mm, best `ncand`.
	(2) choose the 4-subset (in contour order) minimising: sum |quad angle - 90| + 4*opposite-side
	mismatch (mm) + 3*|sideA-sideB| (mm) + arm-alignment (deg: angle between the contour arms
	leaving each corner over 2 mm and the quad edges) + 0.3*candidate cost; sides must be 14-23 mm."""
	n = len(c)
	cs = smooth_closed(c, 2)
	a1, cv1, k1 = corner_scores(cs, 1.2)
	a2, cv2_, _ = corner_scores(cs, 2.5)
	cost = np.abs(a1 - 90) + np.abs(a2 - 90) + np.where(cv1 & cv2_, 0, 1000)
	step = np.sum(np.linalg.norm(np.diff(c, axis=0), axis=1)) / n
	w = max(3, int(2.0 / MM / step)); ka = max(3, int(2.0 / MM / step))
	order = np.argsort(cost); taken = np.zeros(n, bool); cand = []
	for i in order:
		if cost[i] > 140 or len(cand) >= ncand:
			break
		if taken[i]:
			continue
		cand.append(int(i))
		for j in range(-w, w + 1):
			taken[(i + j) % n] = True
	def unit(v):
		return v / (np.linalg.norm(v) + 1e-9)
	best = (1e18, None, None)
	for q in itertools.combinations(sorted(cand), 4):
		q = list(q); P = cs[q]
		L = np.linalg.norm(P - np.roll(P, -1, axis=0), axis=1) * MM
		if L.min() < LMIN or L.max() > LMAX:
			continue
		ok = True; angs = []; arm = 0.0
		for j in range(4):
			u = P[j] - P[j - 1]; v = P[(j + 1) % 4] - P[j]
			if u[0] * v[1] - u[1] * v[0] <= 0:
				ok = False; break
			x = P[j - 1] - P[j]; y = P[(j + 1) % 4] - P[j]
			angs.append(np.degrees(np.arccos(np.clip(unit(x) @ unit(y), -1, 1))))
			fwd = cs[(q[j] + ka) % n] - cs[q[j]]; bwd = cs[(q[j] - ka) % n] - cs[q[j]]
			arm += np.degrees(np.arccos(np.clip(unit(fwd) @ unit(y), -1, 1)))
			arm += np.degrees(np.arccos(np.clip(unit(bwd) @ unit(x), -1, 1)))
		if not ok:
			continue
		A = (L[0] + L[2]) / 2; B = (L[1] + L[3]) / 2
		sc = (np.sum(np.abs(np.array(angs) - 90)) + W_OPP * (abs(L[0] - L[2]) + abs(L[1] - L[3]))
			  + W_AB * abs(A - B) + arm + 0.3 * cost[q].sum())
		if sc < best[0]:
			best = (sc, q, arm)
	return best[1], cand, cost, best[0], best[2]


def analyse_v2(p):
	c = ccw(resample_closed(p['contour'], 1200))
	idx, cand, cost, qsc, arm = find_corners_v2(c)
	ctr = c.mean(0)
	rect = cv2.minAreaRect(c.astype(np.float32))
	p.update(c=c, rect=rect, cand=cand, ok=idx is not None, qscore=qsc, arm=arm)
	if idx is None:
		return p
	sides = split_sides(c, idx)
	profs, lens, types = [], [], []
	for s in sides:
		pr, L = normalise_side(s, ctr)
		profs.append(pr); lens.append(L * MM); types.append(classify_side(pr))
	P = c[idx]; pa = []
	for j in range(4):
		a = P[j - 1] - P[j]; b = P[(j + 1) % 4] - P[j]
		pa.append(float(np.degrees(np.arccos(np.clip(a @ b / np.linalg.norm(a) / np.linalg.norm(b), -1, 1)))))
	vec = np.vstack([resample_open(s, NS + 1)[:-1] for s in sides])
	per = np.sum(np.linalg.norm(np.diff(np.vstack([c, c[:1]]), axis=0), axis=1))
	cs = smooth_closed(c, 6); pers = np.sum(np.linalg.norm(np.diff(np.vstack([cs, cs[:1]]), axis=0), axis=1))
	p.update(corners=idx, sides=sides, profs=profs, lens=lens, types=types, cls=canon(types),
			 poly_ang=pa, vec=vec, rough=per / pers, corner_cost=[float(cost[i]) for i in idx],
			 sideA=(lens[0] + lens[2]) / 2, sideB=(lens[1] + lens[3]) / 2,
			 maxdev=[float(np.max(np.abs(pr[:, 1]))) for pr in profs])
	return p
