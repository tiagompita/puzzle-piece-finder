"""Auxiliar de triagem_r3.py (2026-11-07). Uso: python <este> <cópia do projeto> <saída.json>. Só lê a cópia."""
import sys, json, numpy as np
import os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from src.state import Project
from src import render as R
pr = Project.open(sys.argv[1])
bg = pr.profile.background_lab
rows = []
for pid in R.placed_ids(pr):
    p = pr.piece(pid)
    cl = R._clean_or_crop(pr, pid)
    mmpp = R._scan_mmpp(pr, p.scan_id)
    sh = R.shadow_paper_mask(cl, bg, mmpp)
    pk = R.paper_pocket_mask(cl, bg, mmpp) if R.PAPER_POCKETS else np.zeros_like(sh)
    vis = cl[..., 3] > 0
    dep = R._depth_px(vis) * mmpp
    ys, xs = np.nonzero(vis)
    yy, xx = np.mgrid[0:vis.shape[0], 0:vis.shape[1]]
    dx, dy = xx - xs.mean(), yy - ys.mean()
    shadow_half = (dx < 0) | (dy > 0)
    lit = (dx > np.abs(dy)) | (dy < -np.abs(dx))
    band = vis & (dep <= R.DISPLAY_SHADOW_BAND_MM)
    n = int(sh.sum())
    inner_pk = pk & (dep > R.DISPLAY_SHADOW_BAND_MM)
    rows.append(dict(pid=pid, l=p.celula[0], loss=n / max(1, vis.sum()),
                     shadow_share=(float((sh & shadow_half).sum() / n) if n else None),
                     lit_loss=float((sh & lit).sum() / max(1, (vis & lit).sum())),
                     lit_loss_band=float((sh & lit).sum() / max(1, (band & lit).sum())),
                     pocket_inner_mm2=float(inner_pk.sum() * mmpp * mmpp)))
json.dump(rows, open(sys.argv[2], 'w'), indent=0)
L = np.array([r['lit_loss'] for r in rows]); B = np.array([r['lit_loss_band'] for r in rows])
g = np.array([r['l'] >= 41 for r in rows])
print('n', len(rows), 'lit_loss >1.5%', int((L > .015).sum()), '>2.0%', int((L > .02).sum()), 'max', round(L.max()*100, 2))
print('relva n', g.sum(), 'lit p50/p90/max %', [round(float(np.percentile(L[g], q))*100, 2) for q in (50, 90, 100)])
print('lit_loss_band p50/p90/max %', [round(float(np.percentile(B, q))*100, 1) for q in (50, 90, 100)], 'relva', [round(float(np.percentile(B[g], q))*100, 1) for q in (50, 90, 100)])
print('fail1.5:', [(r['pid'], round(r['lit_loss']*100, 2), round(r['lit_loss_band']*100, 1), round(r['loss']*100, 2)) for r in rows if r['lit_loss'] > .015])
pi = [(r['pid'], round(r['pocket_inner_mm2'], 3)) for r in rows if r['pocket_inner_mm2'] > 0]
print('bolsas interiores (>0,4 mm):', len(pi), sorted(pi, key=lambda x: -x[1])[:12])
ss = [r for r in rows if r['shadow_share'] is not None and r['loss'] * 1 > 0 and r['shadow_share'] < .65]
print('quota sombra < 0.65 (n descart. qualquer):', len(ss))
