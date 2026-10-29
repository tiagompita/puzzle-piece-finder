import os
import sys, pickle, numpy as np, json
sys.path.insert(0, '.')
from shapelib import *
S = os.environ.get("PPF_SCRATCH", "scratch")
OUT = r'C:/Users/Tiago/Desktop/puzzle-piece-finder/docs/diagnostico/forma'
D = pickle.load(open('all.pkl', 'rb'))
sets = ['scan_verde', 'scan_verde_grupo2', 'scan_verde_grupo3', 'scan_verde_grupo4', 'scan_verde_grupo5']
Ls = []; L1 = []; same = 0; tot = 0
for s in sets:
	for p in D[s]:
		if not p['ok']:
			continue
		idx, *_ = find_corners_v2(p['c'], W_OPP=0.0, W_AB=0.0)
		if idx is None:
			continue
		P = p['c'][idx]; L = np.linalg.norm(P - np.roll(P, -1, axis=0), axis=1) * MM
		Ls.append(L); L1.append(p['lens'])
		tot += 1; same += int(sorted(idx) == sorted(p['corners']))
Ls = np.array(Ls); L1 = np.array(L1)
rng = np.random.default_rng(0)
def corrs(L):
	dv = L - L.mean(1, keepdims=True)
	co = np.corrcoef(np.r_[dv[:, 0], dv[:, 1]], np.r_[dv[:, 2], dv[:, 3]])[0, 1]
	ca = np.corrcoef(np.r_[dv[:, 0], dv[:, 1], dv[:, 2], dv[:, 3]], np.r_[dv[:, 1], dv[:, 2], dv[:, 3], dv[:, 0]])[0, 1]
	return co, ca
null = [corrs(np.array([rng.permutation(r) for r in Ls]))[0] for _ in range(300)]
ab = (Ls[:, 0] + Ls[:, 2]) / 2 - (Ls[:, 1] + Ls[:, 3]) / 2
opp = np.r_[Ls[:, 0] - Ls[:, 2], Ls[:, 1] - Ls[:, 3]]
res = dict(n=int(len(Ls)), same_corners_as_with_prior=f'{same}/{tot}', corr_opp_dev=round(corrs(Ls)[0], 3), corr_adj_dev=round(corrs(Ls)[1], 3),
		   null_corr_opp_mean=round(float(np.mean(null)), 3), null_corr_opp_p99=round(float(np.percentile(null, 99)), 3),
		   with_prior_corr_opp=round(corrs(L1)[0], 3), with_prior_corr_adj=round(corrs(L1)[1], 3),
		   AminusB_std=round(float(ab.std(ddof=1)), 3), opp_diff_std=round(float(opp.std(ddof=1)), 3),
		   moment_delta_mm=round(float(np.sqrt(max(np.mean(ab ** 2) - opp.var(ddof=1) / 2, 0))), 3),
		   mean_side=round(float(Ls.mean()), 3), big_pair_mean=round(float(np.mean(np.maximum((Ls[:, 0] + Ls[:, 2]) / 2, (Ls[:, 1] + Ls[:, 3]) / 2))), 3),
		   small_pair_mean=round(float(np.mean(np.minimum((Ls[:, 0] + Ls[:, 2]) / 2, (Ls[:, 1] + Ls[:, 3]) / 2))), 3))
print(res)
R = json.load(open(f'{OUT}/results.json'))
R['task1_rectangularity_no_shape_prior'] = res
json.dump(R, open(f'{OUT}/results.json', 'w'), indent=1)
