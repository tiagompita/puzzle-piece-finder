"""Auxiliar de triagem_r3.py (2026-11-07). Uso: python <este> <cópia do projeto> <saída.json>. Só lê a cópia."""
import sys, json, numpy as np
import os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from src.state import Project
from src import render as R, shape as SH
pr = Project.open(sys.argv[1]); prof = pr.profile
rows = []
seen = set()
for pid in R.placed_ids(pr):
    c = pr.piece(pid).celula
    tw = prof.twin(*c)
    q = pr.board[tuple(tw)].get('peca_id')
    if not q or pr.board[tuple(tw)]['estado'] != 'colocada' or (q, pid) in seen:
        continue
    seen.add((pid, q))
    a, b = pr.shape(pid), pr.shape(q)
    fd = float(SH.free_dist(a, b)[0])
    rows.append(dict(a=pid, b=q, ca=list(c), cb=list(tw), sa=pr.piece(pid).scan_id, sb=pr.piece(q).scan_id, cls_a=a.cls, cls_b=b.cls,
                     same_cls=a.cls == b.cls, free=fd, darea=float(a.area_mm2 - b.area_mm2), chord=SH.chord_pass(a, b)[0] if a.cls == b.cls else None))
fr = np.array([r['free'] for r in rows])
print('pares gémeos colocados', len(rows), 'free p50/p90/p97/max', [round(float(np.percentile(fr, q)), 3) for q in (50, 90, 97, 100)])
print('free > 0.6:', len(fr[fr > 0.6]), '| classe diferente:', sum(not r['same_cls'] for r in rows))
bad = sorted([r for r in rows if r['free'] > 0.6 or not r['same_cls']], key=lambda r: -r['free'])
for r in bad:
    print(f"  {r['a']} {tuple(r['ca'])} {r['sa']} {r['cls_a']} | {r['b']} {tuple(r['cb'])} {r['sb']} {r['cls_b']} free {r['free']:.2f} dArea {r['darea']:+.0f}")
for sid in ('S0009', 'S0020'):
    L = [r for r in rows if sid in (r['sa'], r['sb'])]
    print(sid, 'com gémea colocada', len(L), 'free>0.6', [(r['a'], r['b'], round(r['free'], 2)) for r in L if r['free'] > 0.6 or not r['same_cls']])
json.dump(rows, open(sys.argv[2], 'w'), indent=0)
