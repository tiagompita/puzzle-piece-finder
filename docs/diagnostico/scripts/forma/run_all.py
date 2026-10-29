import os
import sys, json, pickle, numpy as np, cv2, collections, time
sys.path.insert(0, '.')
from shapelib import *
S = os.environ.get("PPF_SCRATCH", "scratch")
SCANS = ['scan_verde', 'scan_laranja', 'scan_preto', 'scan_azul', 'scan_bege', 'scan_vermelho',
		 'scan_verde_grupo2', 'scan_verde_grupo3', 'scan_verde_grupo4', 'scan_verde_grupo5', 'scan_vermelho_grupo5']
NF = 512

def free_vec(c):
	cs = smooth_closed(c, 1.5)
	z = resample_closed(cs, NF)
	z = z - z.mean(0)
	return z[:, 0] + 1j * z[:, 1]

D = {}
t0 = time.time()
for s in SCANS:
	P = [analyse_v2(p) for p in load(f'{S}/seg/{s}.npz')]
	for p in P:
		p['z'] = free_vec(p['c'])
		p['hu_c'] = p['c'].astype(np.float32).reshape(-1, 1, 2)
		del p['image']
	D[s] = P
	print(s, len(P), sum(not p['ok'] for p in P), 'fail', round(time.time() - t0, 1), flush=True)
pickle.dump(D, open('all.pkl', 'wb'))
