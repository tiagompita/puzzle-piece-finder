import os
import sys, numpy as np, cv2, collections, pickle
sys.path.insert(0, os.path.join(os.environ.get("PPF_SCRATCH", "scratch"), "forma"))
from shapelib import *
S = os.environ.get("PPF_SCRATCH", "scratch")
OUT = r'C:/Users/Tiago/Desktop/puzzle-piece-finder/docs/diagnostico/forma'
scan = sys.argv[1] if len(sys.argv) > 1 else 'scan_verde'
P = [analyse_v2(p) for p in load(f'{S}/seg/{scan}.npz')]
pickle.dump(P, open(f'{S}/forma/{scan}.pkl', 'wb'))

def tile(p, T=300, label=True):
	img = np.full((T, T, 3), 255, np.uint8)
	c = p['c']; o = c.mean(0); sc = (T - 60) / max(np.ptp(c[:, 0]), np.ptp(c[:, 1]))
	f = lambda q: np.round((q - o) * sc + T / 2).astype(np.int32)
	box = cv2.boxPoints(p['rect'])
	cv2.polylines(img, [f(box).reshape(-1, 1, 2)], True, (200, 200, 200), 1)
	[cv2.circle(img, tuple(int(v) for v in f(c[i])), 3, (150,150,150), 1) for i in p['cand']]
	cols = {'F': (0, 160, 0), 'T': (220, 0, 0), 'B': (0, 0, 220)}
	for s, t in zip(p['sides'], p['types']):
		cv2.polylines(img, [f(s).reshape(-1, 1, 2)], False, cols[t], 2)
		m = f(s[len(s) // 2]); d = m - T / 2; d = d / (np.linalg.norm(d) + 1e-9)
		pos = np.round(m + d * 14 - [5, -5]).astype(int)
		cv2.putText(img, t, tuple(int(v) for v in pos), cv2.FONT_HERSHEY_SIMPLEX, 0.5, cols[t], 2)
	bad = [abs(a - 90) > 20 for a in p['poly_ang']]
	for j, ci in enumerate(p['corners']):
		cv2.circle(img, tuple(int(v) for v in f(c[ci])), 5, (255, 0, 255) if not bad[j] else (0, 0, 0), -1)
	if label:
		cv2.putText(img, f"#{p['idx']} {p['cls']} {p['type'][:3]}", (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
		cv2.putText(img, f"{p['sideA']:.2f}x{p['sideB']:.2f} r{p['rough']:.2f} q{p['qscore']:.0f}", (4, T - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
	return img

if __name__ == '__main__':
	n = len(P); cols_ = 8; rows = (n + cols_ - 1) // cols_
	M = np.full((rows * 300, cols_ * 300, 3), 255, np.uint8)
	for i, p in enumerate(P):
		r, q = divmod(i, cols_)
		t = tile(p); cv2.rectangle(t, (0, 0), (299, 299), (120, 120, 120), 1)
		M[r * 300:(r + 1) * 300, q * 300:(q + 1) * 300] = t
	cv2.imwrite(f'{OUT}/montagem_cantos_{scan}.png', cv2.cvtColor(M, cv2.COLOR_RGB2BGR))
	for p in P:
		print(p['idx'], p['cls'], ''.join(p['types']), p['type'], ['%.0f' % a for a in p['poly_ang']], ['%.0f' % a for a in p['corner_cost']], ['%.2f' % l for l in p['lens']], '%.2f %.2f %.3f' % (p['sideA'], p['sideB'], p['rough']))
