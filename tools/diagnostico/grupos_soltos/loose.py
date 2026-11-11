"""Ligações melhor-mútuas e quadrados 2x2 coerentes sobre as peças SOLTAS (só leitura).
uso: python loose.py <scratchpad>   (corre a partir da raiz do repo)"""
import sys, pickle, collections, time, os
sys.path.insert(0, r"D:\DEKSTOP\puzzle_piece_finder")
import numpy as np, cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from src.state import Project
from src import fit, render
from src.fit import HoleSide, side_costs, pool_arrays, pool_items, _Cache, board_dirs, DIRS, STEP, NORMAL_DEG, zone_of
from src.shape import f_adjacent
from src.locate import body_center_mm, wrap_deg

SC = sys.argv[1]
T_MIN = 1.05
pr = Project.open(r"D:\DEKSTOP\puzzle_piece_finder\projects\alpes")
calib = fit.calibration(pr)
cache = _Cache(pr, calib)
t0 = time.time()


def costs_for(ids):
    items = pool_items(pr, pieces=ids, cache=cache)
    pa = pool_arrays(items)
    meta, rows = [], []
    for k, it in enumerate(items):
        fa = f_adjacent([s.kind for s in it.sides])
        for i, s in enumerate(it.sides):
            if s.kind not in ("T", "B"):
                continue
            hs = HoleSide(piece_id=it.id, direction="N", side=s, f_adj=bool(fa[i]), strip=it.strips[i])
            c = side_costs(hs, pa, calib)["cost"].copy(); c[k, :] = np.inf
            rows.append(c.astype(np.float32)); meta.append((k, i))
    return items, meta, np.stack(rows)


def links_and_squares(items, meta, M):
    ids = [it.id for it in items]
    pm = M.min(2); pj = M.argmin(2)
    row = {m: s for s, m in enumerate(meta)}
    best = {}
    for s in range(len(meta)):
        o = np.argsort(pm[s])[:2]; c1, c2 = pm[s][o[0]], pm[s][o[1]]
        if np.isfinite(c1):
            best[s] = (int(o[0]), int(pj[s][o[0]]), float(c1), float(c2 / c1) if c1 > 0 else np.inf)
    links = {}
    for s, (b, j, c, mg) in best.items():
        k, i = meta[s]; s2 = row.get((b, j))
        if s2 is None or s2 not in best: continue
        b2, j2, c2_, mg2 = best[s2]
        if (b2, j2) == (k, i) and s < s2:
            links[(ids[k], i, ids[b], j)] = dict(m=min(mg, mg2), c=max(c, c2_))
    link2 = {}
    for (a, i, b, j), l in links.items():
        link2[(a, i)] = (b, j, l["m"]); link2[(b, j)] = (a, i, l["m"])
    sqs = {}
    for a in ids:
        for i1 in range(4):
            i2 = (i1 + 1) % 4
            l1 = link2.get((a, i1)); l2 = link2.get((a, i2))
            if not l1 or not l2: continue
            b, j1, m1 = l1; c, j2, m2 = l2
            D1, D2 = i1, i2
            rb = (j1 - (D1 + 2)) % 4; rc = (j2 - (D2 + 2)) % 4
            lb = link2.get((b, (D2 + rb) % 4)); lc = link2.get((c, (D1 + rc) % 4))
            if not lb or not lc: continue
            d1, jd1, m3 = lb; d2, jd2, m4 = lc
            if d1 != d2 or len({a, b, c, d1}) < 4: continue
            if (jd1 - (D2 + 2)) % 4 != (jd2 - (D1 + 2)) % 4: continue
            key = frozenset((a, b, c, d1))
            if key in sqs: continue
            rd = (jd1 - (D2 + 2)) % 4
            # camadas (linha, coluna) com a em (0,0), N=cima; rot = rotação do layout (lado k olha a direção (k-rot)%4)
            lay = {a: ((0, 0), 0), b: (STEP[DIRS[D1]], rb), c: (STEP[DIRS[D2]], rc),
                   d1: ((STEP[DIRS[D1]][0] + STEP[DIRS[D2]][0], STEP[DIRS[D1]][1] + STEP[DIRS[D2]][1]), rd)}
            sqs[key] = dict(m=min(m1, m2, m3, m4), lay=lay,
                            lk=[(a, i1, b, j1, m1), (a, i2, c, j2, m2), (b, (D2 + rb) % 4, d1, jd1, m3), (c, (D1 + rc) % 4, d2, jd2, m4)])
    return links, sqs


def build_groups(sqs, t):
    sel = [s for s in sqs.values() if s["m"] >= t]
    adj = collections.defaultdict(list)
    for s in sel:
        for (a, i, b, j, _) in s["lk"]:
            adj[a].append((i, b, j)); adj[b].append((j, a, i))
    seen = set(); groups = []
    for p0 in sorted(adj):
        if p0 in seen: continue
        pos = {p0: ((0, 0), 0)}; occ = {(0, 0): p0}; q = [p0]; seen.add(p0); bad = False
        while q:
            a = q.pop(); (x, y), ra = pos[a]
            for (i, b, j) in adj[a]:
                dd = (i - ra) % 4; nx, ny = x + STEP[DIRS[dd]][0], y + STEP[DIRS[dd]][1]; rb = (j - (dd + 2)) % 4
                if b in pos:
                    if pos[b] != ((nx, ny), rb): bad = True
                    continue
                if (nx, ny) in occ and occ[(nx, ny)] != b: bad = True; continue
                pos[b] = ((nx, ny), rb); occ[(nx, ny)] = b; seen.add(b); q.append(b)
        groups.append(dict(n=len(pos), bad=bad, pcs=sorted(pos)))
    return groups


# ---------- zona provável: kNN sobre a cor média Lab das tiras, treinado nas colocadas (zona conhecida)
def feat(pid):
    s = cache.strip(pid)
    f = np.nanmedian(s.reshape(-1, 3), 0)
    return f


def zname(cell):
    z = zone_of(cell, pr.profile)
    return "céu" if z == "céu" else "relva" if z == "relva" else "outras"


placed = [p.id for p in pr.pieces.values() if p.estado == "colocada" and p.celula is not None and not p.same_as and pr.shape(p.id) is not None and pr.shape(p.id).ok]
X = np.array([feat(p) for p in placed]); ok = np.isfinite(X).all(1)
placed = [p for p, o in zip(placed, ok) if o]; X = X[ok]
Y = np.array([zname(tuple(pr.piece(p).celula)) for p in placed])
mu, sd = X.mean(0), X.std(0) + 1e-6
Xn = (X - mu) / sd


def knn(f, excl=None, k=15):
    d = np.linalg.norm(Xn - (f - mu) / sd, axis=1)
    if excl is not None: d[excl] = np.inf
    nn = np.argsort(d)[:k]
    c = collections.Counter(Y[nn]); z, n = c.most_common(1)[0]
    return z, n / k


loo = [knn(Xn[i] * sd + mu, excl=i)[0] for i in range(len(placed))]
acc = np.mean(np.array(loo) == Y)
print("zona provável (kNN cor Lab, k=15): acerto leave-one-out nas colocadas", round(float(acc), 3),
      {z: round(float(np.mean(np.array(loo)[Y == z] == z)), 3) for z in ("céu", "outras", "relva")}, "t", round(time.time() - t0))

# ---------- soltas
loose_ids = [p.id for p in pr.loose_pieces() if pr.shape(p.id) is not None and pr.shape(p.id).ok and not p.flags.get("objeto_duplo")]
print("soltas com forma", len(loose_ids))
items, meta, M = costs_for(loose_ids)
ids = [it.id for it in items]
print("lados T/B", len(meta), "t", round(time.time() - t0))
zone_of_piece = {}
for pid in ids:
    f = feat(pid)
    zone_of_piece[pid] = knn(f)[0] if np.isfinite(f).all() else "?"
print("soltas por zona provável", collections.Counter(zone_of_piece.values()))
links, sqs = links_and_squares(items, meta, M)


def zl(pcs):
    return collections.Counter(zone_of_piece[p] for p in pcs).most_common(1)[0][0]


L105 = {k: l for k, l in links.items() if l["m"] >= T_MIN}
S105 = [s for s in sqs.values() if s["m"] >= T_MIN]
G = build_groups(sqs, T_MIN)
print("ligações melhor-mútuas (todas)", len(links), "| margem >= 1,05:", len(L105))
print("quadrados coerentes (todos)", len(sqs), "| margem >= 1,05:", len(S105), "| grupos >= 1,05:", len(G), "tamanhos", sorted(collections.Counter(g["n"] for g in G).items()), "inconsistentes", sum(g["bad"] for g in G))
tab = collections.defaultdict(lambda: [0, 0, 0, 0, 0])
for (a, i, b, j), l in links.items():
    z = zone_of_piece[a]; tab[z][0] += 1
    if l["m"] >= T_MIN: tab[z][1] += 1
for s in sqs.values():
    z = zl(list(s["lay"])); tab[z][2] += 1
    if s["m"] >= T_MIN: tab[z][3] += 1
for g in G: tab[zl(g["pcs"])][4] += 1
print("zona | lig(todas) lig>=1,05 quad(todos) quad>=1,05 grupos>=1,05")
for z in ("céu", "outras", "relva", "?"):
    if z in tab: print(z, tab[z])
pickle.dump(dict(links=links, sqs=sqs, zone=zone_of_piece, G=G), open(SC + "/loose_res.pkl", "wb"))

# ---------- top 10 quadrados
top = sorted(sqs.values(), key=lambda s: -s["m"])[:10]
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



if os.environ.get("VALID"):
    cell2p = {tuple(pr.piece(p).celula): p for p in placed}
    cand = [(l, c) for (l, c) in sorted(cell2p) if all((l + dl, c + dc) in cell2p for dl in (0, 1) for dc in (0, 1))]
    for (l, c) in [cand[len(cand) // 5], cand[len(cand) // 2], cand[-len(cand) // 8]]:
        blk = {(l + dl, c + dc): cell2p.get((l + dl, c + dc)) for dl in (0, 1) for dc in (0, 1)}
        if not all(blk.values()): continue
        lay = {}
        for (cl, cc), pid in blk.items():
            dr = board_dirs(pr.shape(pid), render.initial_theta(pr, pid)); lay[pid] = ((cl - l, cc - c), dr["N"])
        make_fig(dict(lay=lay), f"{SC}/validacao_{l}_{c}.png", f"VALIDAÇÃO quadrado colocado ({l},{c}) com rot do tabuleiro")
    sys.exit(0)

rows = []
for n, s in enumerate(top, 1):
    pcs = sorted(s["lay"], key=lambda p: s["lay"][p][0])
    title = f"#{n}  margem {s['m']:.3f}  zona provável {zl(pcs)}"
    make_fig(s, f"{SC}/quadrado_{n:02d}.png", title)
    kind = {pid: [x.kind for x in pr.shape(pid).sides] for pid in pcs}
    lk = []
    for (a, i, b, j, m) in s["lk"]:
        lk.append(f"{pr.piece(a).lote}/{pr.piece(a).n_no_lote} lado {i}({kind[a][i]}) ↔ {pr.piece(b).lote}/{pr.piece(b).n_no_lote} lado {j}({kind[b][j]}) m={m:.2f}")
    print(f"\n#{n} margem {s['m']:.3f} zona {zl(pcs)}")
    for pid in pcs:
        (r, c), rot = s["lay"][pid]; p = pr.piece(pid)
        print(f"   {piece_label(pid)}  posição (linha,col)=({r},{c})  rodar {rot*90 % 360}° (sentido horário no ecrã não garantido; ver figura)  scan {p.scan_id}")
    for t in lk: print("   ", t)
    rows.append((n, s["m"], zl(pcs), [(pid, s["lay"][pid]) for pid in pcs]))
# resumo montagem global
fig, ax = plt.subplots(2, 5, figsize=(20, 8))
for n in range(10):
    im = plt.imread(f"{SC}/quadrado_{n+1:02d}.png"); ax[n // 5, n % 5].imshow(im); ax[n // 5, n % 5].axis("off")
plt.tight_layout(); plt.savefig(SC + "/top10_resumo.png", dpi=80)
print("ok")
