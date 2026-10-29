import sys, json, pickle, numpy as np, cv2, collections, itertools
sys.path.insert(0, '.')
from shapelib import *
from dist import *
OUT = r'C:/Users/Tiago/Desktop/puzzle-piece-finder/docs/diagnostico/forma'
D = pickle.load(open('all.pkl', 'rb'))
R = {}


def st(x):
	x = np.asarray(x, float)
	if len(x) == 0:
		return dict(n=0)
	return dict(n=int(len(x)), mean=round(float(x.mean()), 3), std=round(float(x.std(ddof=1)), 3), min=round(float(x.min()), 3),
				p5=round(float(np.percentile(x, 5)), 3), median=round(float(np.median(x)), 3), p95=round(float(np.percentile(x, 95)), 3),
				max=round(float(x.max()), 3))


V = [p for p in D['scan_verde'] if p['ok']]
# ---------------- Task 1: size ----------------
t1 = {}
for s, P in D.items():
	P = [p for p in P if p['ok']]
	big = [max(p['sideA'], p['sideB']) for p in P]; small = [min(p['sideA'], p['sideB']) for p in P]
	allL = [l for p in P for l in p['lens']]
	opp = [p['lens'][0] - p['lens'][2] for p in P] + [p['lens'][1] - p['lens'][3] for p in P]
	ab = [p['sideA'] - p['sideB'] for p in P]
	mr = [cv2.minAreaRect(p['c'].astype(np.float32))[1] for p in P]
	t1[s] = dict(n=len(P), big=st(big), small=st(small), all_sides=st(allL), mean_side=st([(p['sideA'] + p['sideB']) / 2 for p in P]),
				 opp_diff_std=round(float(np.std(opp, ddof=1)), 3), AminusB_std=round(float(np.std(ab, ddof=1)), 3),
				 absAB_mean=round(float(np.mean(np.abs(ab))), 3),
				 minarearect_big=st([max(r) * MM for r in mr]), minarearect_small=st([min(r) * MM for r in mr]),
				 rough_median=round(float(np.median([p['rough'] for p in P])), 3),
				 corner_angle_absdev=st([abs(a - 90) for p in P for a in p['poly_ang']]))
R['task1'] = t1
# ---------------- Task 2: topology ----------------
cls = collections.Counter(p['cls'] for p in V)
sidec = collections.Counter(t for p in V for t in p['types'])
withF = [p['idx'] for p in V if 'F' in p['types']]
edgepy = [p['idx'] for p in V if p['type'] in ('edge', 'corner', 'suspect')]
cls_all = {s: dict(collections.Counter(p['cls'] for p in P if p['ok'])) for s, P in D.items()}
withF_all = {s: [p['idx'] for p in P if p['ok'] and 'F' in p['types']] for s, P in D.items()}
edgepy_all = {s: [p['idx'] for p in P if p['type'] != 'interior'] for s, P in D.items()}
R['task2'] = dict(class_hist=dict(cls.most_common()), side_types=dict(sidec), pieces_with_F=withF, edgepy_nonint=edgepy,
				  edgepy_types=dict(collections.Counter(p['type'] for p in V)), class_hist_by_scan=cls_all,
				  withF_by_scan=withF_all, edgepy_nonint_by_scan=edgepy_all,
				  maxdev_all=st([d for p in V for d in p['maxdev']]),
				  maxdev_hist=np.histogram([d for p in V for d in p['maxdev']], bins=[0, .05, .1, .15, .2, .25, .3, .35, .4, .5, .7])[0].tolist())
# ---------------- Task 3: within-set duplicates ----------------
n = len(V)
Df = mat(V, V, lambda a, b: free_dist(a, b)[0]); np.fill_diagonal(Df, np.inf)
Dc = mat(V, V, corner_dist); np.fill_diagonal(Dc, np.inf)
Dh = mat(V, V, hu); np.fill_diagonal(Dh, np.inf)
Dfs = np.minimum(Df, Df.T); Dcs = np.minimum(Dc, Dc.T); Dh = np.minimum(Dh, Dh.T)
nnf = Dfs.min(1); nnc = Dcs.min(1); nnh = Dh.min(1)
iu = np.triu_indices(n, 1)
pairs = sorted(zip(Dfs[iu], iu[0], iu[1]))[:8]
same_cls = [Dfs[i, j] for i, j in zip(*iu) if V[i]['cls'] == V[j]['cls']]
diff_cls = [Dfs[i, j] for i, j in zip(*iu) if V[i]['cls'] != V[j]['cls']]
R['task3'] = dict(nn_free_mm=st(nnf), nn_corner_mm=st(nnc), nn_hu=st(nnh), all_pairs_free_mm=st(Dfs[iu]),
				  same_class_pairs_free_mm=st(same_cls), diff_class_pairs_free_mm=st(diff_cls),
				  top8=[dict(a=V[i]['idx'], b=V[j]['idx'], free_mm=round(float(d), 3), corner_mm=round(float(Dcs[i, j]), 3), hu=round(float(Dh[i, j]), 4),
							 cls=(V[i]['cls'], V[j]['cls'])) for d, i, j in pairs],
				  nn_same_free_vs_corner=float(np.mean(np.argmin(Dfs, 1) == np.argmin(Dcs, 1))),
				  nn_same_free_vs_hu=float(np.mean(np.argmin(Dfs, 1) == np.argmin(Dh, 1))))
sides = [(pi, k, p['types'][k], p['profs'][k], p['lens'][k]) for pi, p in enumerate(V) for k in range(4)]


def prms(a, b):
	return float(np.sqrt(np.mean(np.sum((a - b) ** 2, 1))))


side_pairs = {}
for T in 'TB':
	ss = [x for x in sides if x[2] == T]
	ds = []
	for x, y in itertools.combinations(ss, 2):
		if x[0] == y[0]:
			continue
		ds.append((prms(x[3], y[3]), x, y))
	ds.sort(key=lambda t: t[0])
	side_pairs[T] = ds
	R['task3'][f'side_{T}{T}_rms'] = st([d[0] for d in ds])
	R['task3'][f'side_{T}{T}_top'] = [dict(a=(V[x[0]]['idx'], x[1]), b=(V[y[0]]['idx'], y[1]), rms=round(d, 4), dL_mm=round(abs(x[4] - y[4]), 2)) for d, x, y in ds[:8]]
# ---------------- Task 4: rescan matching ----------------
t4 = {}
pairs4 = {}
side_noise = {}
for s in ['scan_laranja', 'scan_preto', 'scan_azul', 'scan_bege', 'scan_vermelho']:
	Q = [p for p in D[s] if p['ok']]
	M = mat(Q, V, lambda a, b: free_dist(a, b)[0])
	Mc = mat(Q, V, corner_dist)
	b1 = np.argmin(M, 1); srt = np.sort(M, 1)
	best, second = srt[:, 0], srt[:, 1]
	mutual = np.array([np.argmin(M[:, b1[i]]) == i for i in range(len(Q))])
	ratio = best / second
	unamb = mutual & (ratio < 0.6)
	nnother = nnf[b1]
	t4[s] = dict(nQ=len(Q), nV=len(V), mutual=int(mutual.sum()), unambiguous=int(unamb.sum()), frac_unamb=round(float(unamb.mean()), 3),
				 corner_metric_same_best=int(np.sum(np.argmin(Mc, 1) == b1)),
				 rescan_mm=st(best[mutual]), second_best_mm=st(second[mutual]), nn_other_in_verde_mm=st(nnother[mutual]),
				 ratio=st(ratio[mutual]), margin_nnother_over_rescan=st((nnother / best)[mutual]),
				 rescan_corner_mm=st(Mc[np.arange(len(Q)), b1][mutual]),
				 n_ratio_ge_0_6=int(np.sum(ratio >= 0.6)), worst_ratio_cases=[(Q[i]['idx'], V[b1[i]]['idx'], round(float(best[i]), 3), round(float(second[i]), 3)) for i in np.argsort(-ratio)[:4]])
	pairs4[s] = [(Q[i], V[b1[i]], best[i], second[i], mutual[i]) for i in range(len(Q))]
	dl = []; ty = 0; tyn = 0
	for i in np.where(unamb)[0]:
		a, b = Q[i], V[b1[i]]
		_, k, _ = shape_dist(a, b)
		la = np.array(a['lens']); lb = np.roll(np.array(b['lens']), -k)
		dl += list(la - lb)
		tyn += 1; ty += int(a['cls'] == b['cls'])
	t4[s]['side_len_diff_mm'] = st(dl)
	side_noise[s] = dl
	t4[s]['same_class_in_both_scans'] = f'{ty}/{tyn}'
	t4[s]['area_ratio_vs_verde_median'] = round(float(np.median([cv2.contourArea(a['c'].astype(np.float32)) / cv2.contourArea(b['c'].astype(np.float32)) for a, b, _, _, m in pairs4[s] if m])), 4)
R['task4'] = t4
# ---------------- Task 5: tab-blank complementarity ----------------
tabs = [x for x in sides if x[2] == 'T']; blanks = [x for x in sides if x[2] == 'B']
comp = []
for t in tabs:
	for b in blanks:
		if t[0] == b[0]:
			continue
		bb = b[3][::-1].copy(); bb[:, 0] = 1 - bb[:, 0]; bb[:, 1] = -bb[:, 1]
		r = prms(t[3], bb)
		comp.append((r * (t[4] + b[4]) / 2 + abs(t[4] - b[4]), r, abs(t[4] - b[4]), t, b, bb))
comp.sort(key=lambda x: x[0])
R['task5'] = dict(n_pairs=len(comp), score_all=st([c[0] for c in comp]), rms_all=st([c[1] for c in comp]),
				  top6=[dict(tab=(V[c[3][0]]['idx'], c[3][1]), blank=(V[c[4][0]]['idx'], c[4][1]), score_mm=round(c[0], 3), rms_norm=round(c[1], 4), dL_mm=round(c[2], 2)) for c in comp[:6]])
# ---------------- per piece ----------------
pp = []
for i, p in enumerate(V):
	j = int(np.argmin(Dfs[i]))
	pp.append(dict(idx=p['idx'], side_lengths_mm=[round(l, 2) for l in p['lens']], sideA_mm=round(p['sideA'], 2), sideB_mm=round(p['sideB'], 2),
				   corner_angles_deg=[round(a, 1) for a in p['poly_ang']], side_types=''.join(p['types']), cls=p['cls'], edgepy_type=p['type'],
				   side_maxdev=[round(d, 3) for d in p['maxdev']], roughness=round(p['rough'], 3), quad_score=round(float(p['qscore']), 1),
				   nn_idx=V[j]['idx'], nn_free_mm=round(float(nnf[i]), 3), nn_corner_mm=round(float(nnc[i]), 3), nn_hu=round(float(nnh[i]), 4)))
R['per_piece_scan_verde'] = pp
json.dump(R, open(f'{OUT}/results.json', 'w'), indent=1, default=lambda o: o.item() if hasattr(o, 'item') else str(o))
pickle.dump(dict(V=V, Dfs=Dfs, pairs=pairs, side_pairs={k: v[:8] for k, v in side_pairs.items()}, pairs4=pairs4, comp=comp[:6], side_noise=side_noise), open('ana.pkl', 'wb'))
for k in ['task1', 'task2', 'task3', 'task4', 'task5']:
	print('=====', k); print(json.dumps(R[k], default=str))
