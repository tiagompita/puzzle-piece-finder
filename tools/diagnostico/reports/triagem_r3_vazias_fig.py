"""Uso: python <este> <cópia> <destino descartável fora do repo> <vazias_fit.json> <figura.jpg>. Só na cópia descartável alpes_r3c: ancora as secções da hipótese e desenha as células vs arte."""
import sys, json, shutil, os, numpy as np, cv2
import os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from src.state import Project
from src import render as R
from src.locate import wrap_deg
src, dst, fitp, outp = sys.argv[1:5]
_repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if os.path.normcase(os.path.abspath(dst)).startswith(os.path.normcase(_repo)):
    sys.exit("destino tem de ser uma cópia descartável fora do repositório (é apagado e recriado)")
if os.path.exists(dst):
    shutil.rmtree(dst)
shutil.copytree(src, dst)
pr = Project.open(dst)
fits = json.load(open(fitp))
def fit_theta(pid, cell):
    L = [o for o in fits if o['pid'] == pid and tuple(o['cell']) == cell]
    L.sort(key=lambda o: (o['fails'], o['cost'] if o['n_sides'] else o['dE']))
    return L[0]['theta']
hyp = [('G0040', 'P0442', (42, 55)), ('G0037', 'P0401', (43, 55)), ('G0039', 'P0425', (44, 55)), ('G0038', 'P0420', (45, 55))]
for g, pid, cell in hyp:
    th = fit_theta(pid, cell)
    pr.anchor_section(g, cell[0], cell[1], 0)
    t0 = R.initial_theta(pr, pid)
    rot = int(round(wrap_deg(th - t0) / 90.0)) * 90 % 360
    pr.unanchor_section(g)
    pr.anchor_section(g, cell[0], cell[1], rot)
    print(g, pid, cell, 'fit', round(th), 'rot', rot, 'theta0', round(R.initial_theta(pr, pid), 1))
# G0044: par P0501/P0506 em (44,37)/(45,37)
th = fit_theta('P0501', (44, 37))
pr.anchor_section('G0044', 44, 37, 0)
t0 = R.initial_theta(pr, 'P0501')
rot = int(round(wrap_deg(th - t0) / 90.0)) * 90 % 360
print('G0044 rot', rot)
if rot:
    pr.unanchor_section('G0044')
    pr.anchor_section('G0044', 44, 37, rot)
print({c: pr.board[c] for c in [(44, 37), (45, 37), (42, 55), (43, 55), (44, 55), (45, 55)]})
ppc = float(pr.profile.cell_mm['w']) / (25.4 / 150.0)
tiles = []
for reg in ((41, 54, 46, 56), (43, 36, 46, 38)):
    a = R.compose_board(pr, ppc, region=reg, layers=('art', 'pieces', 'grid'))
    b = R.compose_board(pr, ppc, region=reg, layers=('art', 'grid'), art_alpha=1.0)
    tiles.append(np.hstack([a, np.full((a.shape[0], 6, 3), 255, np.uint8), b]))
w = max(t.shape[1] for t in tiles)
img = np.vstack([np.hstack([t, np.full((t.shape[0], w - t.shape[1], 3), 255, np.uint8)]) for t in tiles])
cv2.imwrite(outp.replace('.jpg', '_big.png'), img)
q = 85
while True:
    ok, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, q])
    if len(buf) < 300_000 or q < 45: break
    q -= 8
open(outp, 'wb').write(buf.tobytes())
print(outp, len(buf))
