import os
"""Extra checks: (a) appearance-based ground truth for re-scan matching, (b) rectangularity mixture fit."""
import sys, json, pickle, numpy as np, cv2
sys.path.insert(0, '.')
from shapelib import *
from dist import *
S = os.environ.get("PPF_SCRATCH", "scratch")
OUT = r'C:/Users/Tiago/Desktop/puzzle-piece-finder/docs/diagnostico/forma'
D = pickle.load(open('all.pkl', 'rb'))
R = json.load(open(f'{OUT}/results.json'))


def hist_feat(scan):
	d = np.load(f'{S}/seg/{scan}.npz', allow_pickle=True)
	F = {}
	for i in range(len(d['images'])):
		if d['is_cluster'][i]:
			continue
		img = np.ascontiguousarray(d['images'][i]); m = (d['masks'][i] > 0).astype(np.uint8)
		m = cv2.erode(m, np.ones((15, 15), np.uint8))  # drop the border (paper-colour bleed)
		lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)
		h = cv2.calcHist([lab], [0, 1, 2], m, [8, 8, 8], [0, 256, 0, 256, 0, 256])
		h = h.flatten(); h /= h.sum() + 1e-9
		F[i] = np.sqrt(h)  # Hellinger
	return F


V = [p for p in D['scan_verde'] if p['ok']]
FV = hist_feat('scan_verde')
out = {}
for s in ['scan_laranja', 'scan_preto', 'scan_azul', 'scan_bege', 'scan_vermelho']:
	Q = [p for p in D[s] if p['ok']]
	FQ = hist_feat(s)
	A = np.array([[np.linalg.norm(FQ[q['idx']] - FV[v['idx']]) for v in V] for q in Q])  # appearance distance
	M = np.array([[free_dist(q, v)[0] for v in V] for q in Q])
	ga = np.argmin(A, 1); sa = np.sort(A, 1)
	amut = np.array([np.argmin(A[:, ga[i]]) == i for i in range(len(Q))])
	conf = amut & (sa[:, 0] / sa[:, 1] < 0.8)       # confident appearance match = pseudo ground truth
	gs = np.argmin(M, 1)
	# shape top-1 accuracy vs pseudo-GT, and rank of the true piece
	ranks = np.array([int(np.sum(M[i] < M[i, ga[i]])) for i in range(len(Q))])
	own = M[np.arange(len(Q)), ga]
	other = np.array([np.min(np.delete(M[i], ga[i])) for i in range(len(Q))])
	c = conf
	out[s] = dict(nQ=len(Q), appearance_confident=int(c.sum()), shape_top1_acc_on_confident=round(float(np.mean(gs[c] == ga[c])), 3),
				  shape_top3_acc=round(float(np.mean(ranks[c] < 3)), 3),
				  own_rescan_mm=dict(median=round(float(np.median(own[c])), 3), p90=round(float(np.percentile(own[c], 90)), 3), max=round(float(own[c].max()), 3)),
				  nearest_other_same_scan_pair_mm=dict(median=round(float(np.median(other[c])), 3), p10=round(float(np.percentile(other[c], 10)), 3), min=round(float(other[c].min()), 3)),
				  frac_own_lt_other=round(float(np.mean(own[c] < other[c])), 3),
				  frac_margin_gt_1_5=round(float(np.mean(other[c] / own[c] > 1.5)), 3),
				  median_ratio_other_over_own=round(float(np.median(other[c] / own[c])), 2),
				  rough_corr_own=round(float(np.corrcoef(own[c], [max(Q[i]['rough'], V[ga[i]]['rough']) for i in np.where(c)[0]])[0, 1]), 3))
	if s == 'scan_laranja':
		pickle.dump(dict(ga=ga, conf=conf, own=own, other=other, Qidx=[q['idx'] for q in Q]), open('gt_laranja.pkl', 'wb'))
	print(s, out[s], flush=True)
R['task4_appearance_check'] = out
# ---- rectangularity: mixture fit of A-B ~ 0.5 N(d,s) + 0.5 N(-d,s) on distinct piece sets
sets = ['scan_verde', 'scan_verde_grupo2', 'scan_verde_grupo3', 'scan_verde_grupo4', 'scan_verde_grupo5']
ab = np.array([p['sideA'] - p['sideB'] for s in sets for p in D[s] if p['ok']])
ms = np.array([(p['sideA'] + p['sideB']) / 2 for s in sets for p in D[s] if p['ok']])
opp = np.array([d for s in sets for p in D[s] if p['ok'] for d in (p['lens'][0] - p['lens'][2], p['lens'][1] - p['lens'][3])])


DG = np.linspace(0, 2.5, 126)[:, None, None]; SG = np.linspace(0.2, 2.0, 91)[None, :, None]


def fit(x):
	X = x[None, None, :]
	L = np.sum(np.log(0.5 * np.exp(-(X - DG) ** 2 / (2 * SG * SG)) + 0.5 * np.exp(-(X + DG) ** 2 / (2 * SG * SG)) + 1e-300) - np.log(SG), axis=2)
	i, j = np.unravel_index(np.argmax(L), L.shape)
	return L[i, j], DG[i, 0, 0], SG[0, j, 0]


ll, d, sg = fit(ab)
ll0, _, sg0 = max(((np.sum(-ab ** 2 / (2 * s * s) - np.log(s)), 0, s) for s in np.linspace(0.2, 2.0, 181)))
rng = np.random.default_rng(0)
boot = []
for _ in range(150):
	ii = rng.integers(0, len(ab), len(ab))
	boot.append(fit(ab[ii])[1] / np.mean(ms[ii]))
rect = dict(n=int(len(ab)), mixture_delta_mm=round(float(d), 3), mixture_sigma_mm=round(float(sg), 3), loglik_gain_vs_square=round(float(ll - ll0), 2),
			mean_side_mm=round(float(ms.mean()), 3), ratio_long_short=round(float((ms.mean() + d / 2) / (ms.mean() - d / 2)), 4),
			delta_over_mean_ci95=[round(float(np.percentile(boot, 2.5)), 4), round(float(np.percentile(boot, 97.5)), 4)],
			opp_diff_std_mm=round(float(opp.std(ddof=1)), 3),
			moment_delta_mm=round(float(np.sqrt(max(np.mean(ab ** 2) - opp.var(ddof=1) / 2, 0))), 3),
			absAB_hist_0p25mm=np.histogram(np.abs(ab), bins=np.arange(0, 3.01, 0.25))[0].tolist(),
			grid_hypotheses_cell_ratio={f'{c}x{r}': round((1184 / c) / (843 / r), 4) for c, r in [(64, 47), (64, 48), (63, 48), (62, 48), (65, 46), (60, 50)]})
R['task1_rectangularity'] = rect
print(rect)
json.dump(R, open(f'{OUT}/results.json', 'w'), indent=1, default=lambda o: o.item() if hasattr(o, 'item') else str(o))
