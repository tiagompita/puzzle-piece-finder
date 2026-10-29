import sys, pickle, json, numpy as np
sys.path.insert(0, '.')
from dist import *
OUT = r'C:/Users/Tiago/Desktop/puzzle-piece-finder/docs/diagnostico/forma'
D = pickle.load(open('all.pkl', 'rb')); V = [p for p in D['scan_verde'] if p['ok']]
R = json.load(open(f'{OUT}/results.json'))
cv_ = np.array([p['bbox'][:2] + p['bbox'][2:] / 2 for p in V])
out = {}
for s in ['scan_laranja', 'scan_azul']:
	Q = [p for p in D[s] if p['ok']]
	M = np.array([[free_dist(q, v)[0] for v in V] for q in Q])
	Mc = np.array([[corner_dist(q, v) for v in V] for q in Q])
	own, oth, top1, top1c, rk, ratio = [], [], [], [], [], []
	for i, q in enumerate(Q):
		c = q['bbox'][:2] + q['bbox'][2:] / 2
		dd = np.linalg.norm(cv_ - c, axis=1); j = int(np.argmin(dd))
		if dd[j] > 40:
			continue
		own.append(M[i, j]); oth.append(np.min(np.delete(M[i], j)))
		top1.append(int(np.argmin(M[i]) == j)); top1c.append(int(np.argmin(Mc[i]) == j)); rk.append(int(np.sum(M[i] < M[i, j])))
	own, oth = np.array(own), np.array(oth)
	out[s] = dict(n_position_gt=len(own), top1_free=round(float(np.mean(top1)), 3), top1_corner=round(float(np.mean(top1c)), 3),
				  top3_free=round(float(np.mean(np.array(rk) < 3)), 3),
				  own_mm=dict(median=round(float(np.median(own)), 3), mean=round(float(own.mean()), 3), p90=round(float(np.percentile(own, 90)), 3), max=round(float(own.max()), 3)),
				  nearest_other_mm=dict(median=round(float(np.median(oth)), 3), p10=round(float(np.percentile(oth, 10)), 3), min=round(float(oth.min()), 3)),
				  ratio_other_over_own=dict(median=round(float(np.median(oth / own)), 2), frac_gt_1=round(float(np.mean(oth > own)), 3), frac_gt_1_5=round(float(np.mean(oth / own > 1.5)), 3), frac_gt_2=round(float(np.mean(oth / own > 2)), 3)),
				  own_lt_0_4mm=int(np.sum(own < 0.4)))
	print(s, out[s])
R['task4_position_gt'] = out
json.dump(R, open(f'{OUT}/results.json', 'w'), indent=1)
