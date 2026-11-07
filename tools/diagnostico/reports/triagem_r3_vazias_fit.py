"""Auxiliar de triagem_r3.py (2026-11-07). Uso: python <este> <cópia do projeto> <saída.json>. Só lê a cópia."""
import sys, json, numpy as np
import os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from src.state import Project
from src import render as R
from src.legacy import side_compat
from src.locate import CellArt, render_item, de_cell
pr = Project.open(sys.argv[1]); prof = pr.profile
print(R.manual_pose_note(pr))   # as poses manuais não entram nas métricas
art = CellArt.load(prof, R.REPO)
OPP = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}
regs = {}
def nk(q):
    if q not in regs:
        regs[q] = R.register_piece(pr, q, image=False, manual=False)
    return regs[q]['corner']['k']
cells = [(42, 55), (43, 55), (44, 55), (45, 55), (44, 37), (45, 37), (43, 56)]
pids = ['P0401', 'P0420', 'P0425', 'P0442', 'P0501', 'P0506', 'P0573']
out = []
for pid in pids:
    sh = pr.shape(pid); p = pr.piece(pid)
    rgba = pr.crop_rgba(pid); mmpp = R._scan_mmpp(pr, p.scan_id)
    for cell in cells:
        cr = R.corner_register(sh, prof, cell, None)
        for k, th, rms, fok in cr['cands']:
            rows, fails, cost, n = [], 0, 0.0, 0
            for d, (dl, dc) in (('N', (-1, 0)), ('E', (0, 1)), ('S', (1, 0)), ('W', (0, -1))):
                q = (cell[0] + dl, cell[1] + dc)
                b = pr.board[q]
                qq = b.get('peca_id') if b['estado'] == 'colocada' else None
                i = (R.DIRS.index(d) - k) % 4
                if not qq:
                    rows.append(f"{d}:{sh.sides[i].kind}/-"); continue
                ii = (R.DIRS.index(OPP[d]) - nk(qq)) % 4
                r = side_compat(sh.sides[i], pr.shape(qq).sides[ii])
                n += 1
                if r['ok']: cost += r['cost']
                else: fails += 1
                rows.append(f"{d}:{sh.sides[i].kind}{pr.shape(qq).sides[ii].kind} {r['why'] or 'ok'} {r['rms']:.2f}/{r['dl']:.2f}")
            de = de_cell(render_item(rgba, sh, th, art, mmpp), *cell, art)
            out.append(dict(pid=pid, n=p.n_no_lote, scan=p.scan_id, cell=cell, k=k, theta=th, fails=fails, n_sides=n, cost=cost, dE=de['dE'], ncc=de['ncc'], rows=rows))
for pid in pids:
    for cell in cells:
        L = [o for o in out if o['pid'] == pid and o['cell'] == cell]
        L.sort(key=lambda o: (o['fails'], o['cost']))
        b = L[0]
        if b['n_sides'] and b['fails'] == 0:
            print(f"{pid} {b['scan']} #{b['n']} -> {cell}: k{b['k']} th {b['theta']:.0f} fails {b['fails']}/{b['n_sides']} cost {b['cost']:.2f} dE {b['dE']:.1f} ncc {b['ncc']:.2f} | {'; '.join(b['rows'])}")
        elif not b['n_sides']:
            best = min(L, key=lambda o: o['dE'])
            print(f"{pid} #{b['n']} -> {cell}: sem vizinhas; melhor imagem k{best['k']} dE {best['dE']:.1f} ncc {best['ncc']:.2f}")
json.dump(out, open(sys.argv[2], 'w'), default=float, indent=0)
