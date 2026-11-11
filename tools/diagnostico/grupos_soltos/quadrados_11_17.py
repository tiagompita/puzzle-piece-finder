"""Quadrados 11-17 (a seguir aos 10 de 2026-11-10): mesma lista (loose_res.pkl de 2026-11-10) e mesma figura (make_fig de loose.py).
Só leitura; corre sobre uma CÓPIA do projeto. uso: python sq17.py <loose_res.pkl> <projeto-copia> <saida>"""
import sys, pickle, collections, io
sys.path.insert(0, r"D:\DEKSTOP\puzzle_piece_finder")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import numpy as np, cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from src.state import Project
from src import render
from src.fit import DIRS, STEP, NORMAL_DEG
from src.locate import body_center_mm, wrap_deg
R = pickle.load(open(sys.argv[1], "rb"))
pr = Project.open(sys.argv[2])
OUT = sys.argv[3]
zone_of_piece = R["zone"]
def zl(pcs):
    return collections.Counter(zone_of_piece[p] for p in pcs).most_common(1)[0][0]

SYM = {"N": "N", "E": "E", "S": "S", "W": "W"}


def piece_label(pid):
    p = pr.piece(pid); return f"saco {p.lote} nº {p.n_no_lote} ({pid})"


def theta_for_layout(pid, rot):
    """rotação (graus, quadro de imagem como board_dirs) que põe o lado k a olhar a direção (k-rot)%4"""
    sh = pr.shape(pid); ctr = body_center_mm(sh); angs = []
    for k, s in enumerate(sh.sides):
        v = 0.5 * (np.asarray(s.p0_mm) + np.asarray(s.p1_mm)) - ctr
        a = np.degrees(np.arctan2(v[1], v[0]))
        angs.append(float(wrap_deg(NORMAL_DEG[DIRS[(k - rot) % 4]] - a)))
    r = np.radians(angs)
    return float(np.degrees(np.arctan2(np.sin(r).mean(), np.cos(r).mean())))


def rotated(pid, rot):
    """crop rodado para a orientação do layout; devolve (rgba, centro do corpo em px do resultado)"""
    rgba = render.piece_rgba_for_display(pr, pid)
    th = theta_for_layout(pid, rot)
    p = pr.piece(pid); mmpp = render._scan_mmpp(pr, p.scan_id)
    ctr = body_center_mm(pr.shape(pid)) / mmpp - np.asarray(p.bbox[:2], float)
    h, w = rgba.shape[:2]; d = int(np.ceil(np.hypot(h, w))) * 2
    big = np.zeros((d, d, 4), np.uint8); y0, x0 = d // 2 - int(ctr[1]), d // 2 - int(ctr[0])
    big[y0:y0 + h, x0:x0 + w] = rgba
    Mx = cv2.getRotationMatrix2D((d / 2, d / 2), -th, 1.0)
    out = cv2.warpAffine(big, Mx, (d, d), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
    return out, (d / 2, d / 2)


def on_white(img):
    a = img[..., 3:4] / 255.0
    return (img[..., :3] * a + 255 * (1 - a)).astype(np.uint8)


def make_fig(s, name, title):
    pcs = sorted(s["lay"], key=lambda p: s["lay"][p][0])
    fig = plt.figure(figsize=(12, 4.2))
    gs = fig.add_gridspec(1, 5, width_ratios=[1, 1, 1, 1, 2.4])
    imgs = {}
    for n, pid in enumerate(pcs):
        ax = fig.add_subplot(gs[0, n]); rgba = render.piece_rgba_for_display(pr, pid)
        ax.imshow(on_white(rgba)); ax.set_title(piece_label(pid).replace(" (", "\n("), fontsize=8); ax.axis("off")
        imgs[pid] = rotated(pid, s["lay"][pid][1])
    ax = fig.add_subplot(gs[0, 4])
    mmpp = render._scan_mmpp(pr, pr.piece(pcs[0]).scan_id)
    pitch = int(round(0.5 * (float(pr.profile.cell_mm["w"]) + float(pr.profile.cell_mm["h"])) / mmpp))
    marg = int(0.75 * pitch); canvas = np.full((2 * pitch + 2 * marg, 2 * pitch + 2 * marg, 3), 255, np.uint8)
    r_min = min(v[0][0] for v in s["lay"].values()); c_min = min(v[0][1] for v in s["lay"].values())
    for pid, ((r, c), rot) in s["lay"].items():
        im, (cx, cy) = imgs[pid]
        X = marg + (c - c_min) * pitch + pitch // 2 - int(cx); Y = marg + (r - r_min) * pitch + pitch // 2 - int(cy)
        h, w = im.shape[:2]
        ys0, xs0 = max(0, -Y), max(0, -X); ys1, xs1 = min(h, canvas.shape[0] - Y), min(w, canvas.shape[1] - X)
        sub = im[ys0:ys1, xs0:xs1]; al = sub[..., 3:4] > 0
        reg = canvas[Y + ys0:Y + ys1, X + xs0:X + xs1]
        reg[:] = np.where(al, sub[..., :3], reg)
    ax.imshow(canvas); ax.axis("off"); ax.set_title("montagem 2×2 (peças rodadas e à distância nominal da célula; aproximada)", fontsize=8)
    fig.suptitle(title, fontsize=10); plt.tight_layout(); plt.savefig(name, dpi=110); plt.close(fig)



sq = sorted(R["sqs"].values(), key=lambda s: -s["m"])
top10 = set().union(*[set(s["lay"]) for s in sq[:10]])
which = {}
for n, s in enumerate(sq[:10], 1):
    for p in s["lay"]: which[p] = n
for n, s in enumerate(sq[10:17], 11):
    pcs = sorted(s["lay"], key=lambda p: s["lay"][p][0])
    title = f"#{n}  margem {s['m']:.3f}  zona provável {zl(pcs)}"
    make_fig(s, f"{OUT}/quadrado_{n:02d}.png", title)
    print(f"#{n} margem {s['m']:.3f} {'>=' if s['m'] >= 1.05 else '<'} 1,05 zona {zl(pcs)}")
    for pid in pcs:
        (r, c), rot = s["lay"][pid]; p = pr.piece(pid)
        rep = f"  [também no quadrado #{which[pid]}]" if pid in which else ""
        print(f"   Saco {p.lote} · nº {p.n_no_lote} ({pid}) pos ({r},{c}) estado {p.estado}{rep}")
    for (a, i, b, j, m) in s["lk"]:
        print(f"    {a} lado {i} <-> {b} lado {j} m={m:.3f}")
# ligações partilhadas com os 10
lk10 = {}
for n, s in enumerate(sq[:10], 1):
    for (a, i, b, j, m) in s["lk"]:
        lk10[frozenset([(a, i), (b, j)])] = n
for n, s in enumerate(sq[10:17], 11):
    sh = [lk10[frozenset([(a, i), (b, j)])] for (a, i, b, j, m) in s["lk"] if frozenset([(a, i), (b, j)]) in lk10]
    print(f"#{n}: ligações em comum com os 10 = {sh}")
fig, ax = plt.subplots(2, 4, figsize=(16, 8))
for k in range(8):
    a_ = ax[k // 4, k % 4]; a_.axis("off")
    if k < 7: a_.imshow(plt.imread(f"{OUT}/quadrado_{k+11:02d}.png"))
plt.tight_layout(); plt.savefig(OUT + "/quadrados_11_17_resumo.png", dpi=80)
print("ok")

