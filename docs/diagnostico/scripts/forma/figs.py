import os
import sys, pickle, json, numpy as np, cv2
sys.path.insert(0, '.')
from shapelib import *
from dist import *
S = os.environ.get("PPF_SCRATCH", "scratch")
OUT = r'C:/Users/Tiago/Desktop/puzzle-piece-finder/docs/diagnostico/forma'
A = pickle.load(open('ana.pkl', 'rb'))
D = pickle.load(open('all.pkl', 'rb'))
V = A['V']; byidx = {p['idx']: p for p in V}
RED, BLUE, BLK, GRN = (220, 0, 0), (0, 0, 220), (0, 0, 0), (0, 150, 0)


def save(name, img):
	cv2.imwrite(f'{OUT}/{name}', cv2.cvtColor(img, cv2.COLOR_RGB2BGR))


def draw_pts(img, pts_list, cols, T, text=None, closed=True, scale=None, center=None):
	allp = np.vstack(pts_list)
	o = allp.mean(0) if center is None else center
	sc = scale or (T - 50) / max(np.ptp(allp[:, 0]), np.ptp(allp[:, 1]))
	for p, c in zip(pts_list, cols):
		q = np.round((p - o) * sc + T / 2).astype(np.int32).reshape(-1, 1, 2)
		cv2.polylines(img, [q], closed, c, 2)
	if text:
		for k, t in enumerate(text):
			cv2.putText(img, t, (5, 16 + 16 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.45, BLK, 1)
	return img


def z2p(z):
	return np.c_[z.real, z.imag]


def grid(tiles, cols):
	T = tiles[0].shape[0]; rows = (len(tiles) + cols - 1) // cols
	M = np.full((rows * T, cols * tiles[0].shape[1], 3), 255, np.uint8)
	for i, t in enumerate(tiles):
		r, c = divmod(i, cols)
		cv2.rectangle(t, (0, 0), (t.shape[1] - 1, t.shape[0] - 1), (150, 150, 150), 1)
		M[r * T:(r + 1) * T, c * t.shape[1]:(c + 1) * t.shape[1]] = t
	return M


# ---- 0: opening failure illustration
p = byidx[14]
m, o = local_mask(p['c'], 60)
r = int(round(OPEN_R_MM / MM))
op = cv2.morphologyEx(m, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
im = np.dstack([m // 2 + op // 2] * 3)
cv2.putText(im, 'peca #14: mascara (cinza) vs abertura disco r=3.5mm (branco)', (5, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
save('falha_abertura_morfologica.png', im)

# ---- 1: top-8 most similar whole-shape pairs
tiles = []
for d, i, j in A['pairs']:
	a, b = V[i], V[j]
	za, zb, dd = aligned_b(a, b)
	t = np.full((320, 320, 3), 255, np.uint8)
	tiles.append(draw_pts(t, [z2p(za), z2p(zb)], [RED, BLUE], 320,
						  [f"#{a['idx']} (verm) vs #{b['idx']} (azul)", f"RMS {dd:.2f} mm  {a['cls']}/{b['cls']}"]))
save('t3_pares_mais_parecidos.png', grid(tiles, 4))

# ---- 2: side profile pairs (TT and BB)
for T_ in 'TB':
	tiles = []
	for d, x, y in A['side_pairs'][T_][:8]:
		t = np.full((220, 320, 3), 255, np.uint8)
		px = x[3] * x[4]; py = y[3] * y[4]   # mm
		o = np.array([max(x[4], y[4]) / 2, 0.15 * 18])
		sc = 280 / 22.0
		for pr, col in [(px, RED), (py, BLUE)]:
			q = np.round(np.c_[(pr[:, 0] - o[0]) * sc + 160, -(pr[:, 1] - o[1]) * sc + 130]).astype(np.int32).reshape(-1, 1, 2)
			cv2.polylines(t, [q], False, col, 2)
		cv2.putText(t, f"#{V[x[0]]['idx']}s{x[1]} vs #{V[y[0]]['idx']}s{y[1]}", (5, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, BLK, 1)
		cv2.putText(t, f"rms {d:.3f}L  dL {abs(x[4] - y[4]):.2f}mm", (5, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.45, BLK, 1)
		tiles.append(t)
	save(f't3_perfis_{T_}{T_}_mais_parecidos.png', grid(tiles, 4))

# ---- 3: re-scan pairs (laranja vs verde), with crops
gt = pickle.load(open('gt_laranja.pkl', 'rb'))
L = [p for p in D['scan_laranja'] if p['ok']]
dl = np.load(f'{S}/seg/scan_laranja.npz', allow_pickle=True); dv = np.load(f'{S}/seg/scan_verde.npz', allow_pickle=True)
order = np.argsort(gt['own'])
good = [i for i in order if gt['conf'][i] and gt['own'][i] < gt['other'][i]]
bad = [i for i in order if gt['conf'][i] and gt['own'][i] >= gt['other'][i]]
pick = [good[0], good[len(good) // 3], good[2 * len(good) // 3], good[-1]] + bad[:2]
tiles = []
for i in pick:
	q = L[i]; v = V[gt['ga'][i]]
	za, zb, dd = aligned_b(v, q)
	t = np.full((300, 900, 3), 255, np.uint8)
	for k, (dd_, ii) in enumerate([(dv, v['idx']), (dl, q['idx'])]):
		img = dd_['images'][ii]; h, w = img.shape[:2]; s = 280 / max(h, w)
		img = cv2.resize(np.ascontiguousarray(img), (int(w * s), int(h * s)))
		t[10:10 + img.shape[0], 10 + 300 * k:10 + 300 * k + img.shape[1]] = img
	sub = np.full((300, 300, 3), 255, np.uint8)
	draw_pts(sub, [z2p(za), z2p(zb)], [GRN, RED], 300, [f"verde#{v['idx']} vs laranja#{q['idx']}", f"re-scan {gt['own'][i]:.2f}mm, outra {gt['other'][i]:.2f}mm",
														'OK' if gt['own'][i] < gt['other'][i] else 'FALHA (forma confunde)'])
	t[:, 600:] = sub
	tiles.append(t)
save('t4_rescan_laranja_vs_verde.png', grid(tiles, 2))

# ---- 4: tab-blank complementarity
tiles = []
for sc_, r, dL, t_, b_, bb in A['comp']:
	t = np.full((240, 340, 3), 255, np.uint8)
	pt = t_[3] * t_[4]; pb = bb * b_[4]
	o = np.array([t_[4] / 2, 0.15 * 18]); s = 300 / 22.0
	for pr, col in [(pt, RED), (pb, BLUE)]:
		q = np.round(np.c_[(pr[:, 0] - o[0]) * s + 170, -(pr[:, 1] - o[1]) * s + 140]).astype(np.int32).reshape(-1, 1, 2)
		cv2.polylines(t, [q], False, col, 2)
	cv2.putText(t, f"tab #{V[t_[0]]['idx']}s{t_[1]} (verm) / blank #{V[b_[0]]['idx']}s{b_[1]} (azul)", (5, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.42, BLK, 1)
	cv2.putText(t, f"rms {r:.3f}L ({r * t_[4]:.2f}mm)  dL {dL:.2f}mm", (5, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.42, BLK, 1)
	tiles.append(t)
save('t5_tab_blank_complementares.png', grid(tiles, 3))

# ---- 5: histogram figure (nn within verde vs own re-scan laranja)
R = json.load(open(f'{OUT}/results.json'))
nn = np.array([x['nn_free_mm'] for x in R['per_piece_scan_verde']])
own = gt['own'][gt['conf']]
bins = np.arange(0, 3.21, 0.2)
h1, _ = np.histogram(nn, bins); h2, _ = np.histogram(own, bins)
W, H = 900, 420; img = np.full((H, W, 3), 255, np.uint8)
bw = (W - 80) / len(h1); ys = (H - 90) / max(h1.max(), h2.max())
for k in range(len(h1)):
	x0 = int(60 + k * bw)
	cv2.rectangle(img, (x0 + 2, H - 50 - int(h1[k] * ys)), (x0 + int(bw / 2), H - 50), (0, 0, 200), -1)
	cv2.rectangle(img, (x0 + int(bw / 2), H - 50 - int(h2[k] * ys)), (x0 + int(bw) - 2, H - 50), (230, 120, 0), -1)
	cv2.putText(img, f'{bins[k]:.1f}', (x0, H - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.4, BLK, 1)
cv2.putText(img, 'RMS forma (mm). azul: distancia ao vizinho mais proximo (outra peca, verde, n=61)', (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 200), 1)
cv2.putText(img, 'laranja: distancia a propria peca re-digitalizada (laranja vs verde, n=%d)' % len(own), (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (230, 120, 0), 1)
save('t3t4_histograma_nn_vs_rescan.png', img)
print('done', len(good), len(bad))
