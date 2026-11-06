"""E-fit, passo 5: 12 exemplos visuais de buracos (6 acertos, 6 falhas pelo pior rank). Correr depois de ``buraco.py``.

Cenário (fixado em RESULTADOS.md §11): N = 100, E5 estrito, sem erosão. Acerto = top-1 em >= 50 % dos sorteios; falhas = pior
rank da peça certa no pool completo (desempate pelo id). Cada painel põe as vizinhas (rígido de 2 pontos pelo lado que
encara o buraco) e a candidata NO buraco (o lado da candidata que olha para a 1.ª vizinha coincide com o de X). Nas falhas:
à esquerda a peça certa, à direita a vencedora do E5 conjunto. Amarelo = vizinhas, ciano = certa/candidata, laranja = vencedora.
Saída: ``docs/diagnostico/fit/exemplos_buraco_{acertos,falhas}.jpg`` e ``exemplos_buraco.json``.
"""

import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import buracos  # noqa: E402
import pool  # noqa: E402
from common import REPO  # noqa: E402
from figs import PPM, PAD_MM, ascii_, hstack_pad, rigid_for, side_pts  # noqa: E402

from src import render  # noqa: E402

DOC = os.path.join(REPO, "docs", "diagnostico", "fit")


def same_for(sx, sc):
    """R, t que levam o referencial da candidata ao de X pondo o lado ``sc`` em cima do lado ``sx`` (mesmo sentido)."""
    p0, p1 = side_pts(*sx)
    q0, q1 = side_pts(*sc)
    ang = np.arctan2(*(p1 - p0)[::-1]) - np.arctan2(*(q1 - q0)[::-1])
    R = np.array([[np.cos(ang), -np.sin(ang)], [np.sin(ang), np.cos(ang)]])
    return R, p0 - R @ q0


def draw(pr, sh, items, title, lines, minw=420):
    cs = [(sh[p].c @ R.T) + t for p, R, t, _ in items]
    allp = np.vstack(cs)
    lo, hi = allp.min(0) - PAD_MM, allp.max(0) + PAD_MM
    W, H = (np.ceil((hi - lo) * PPM)).astype(int)
    canvas = np.full((H, W, 3), 40, np.uint8)
    for (pid, Rm, tm, col) in items:
        rgba = render.piece_rgba_for_display(pr, pid)
        if rgba is None:
            continue
        p = pr.piece(pid)
        mmpp = render._scan_mmpp(pr, p.scan_id)
        origin = np.asarray(p.bbox[:2], float)
        M = np.zeros((2, 3))
        M[:, :2] = PPM * mmpp * Rm
        M[:, 2] = PPM * (Rm @ (origin * mmpp) + tm - lo)
        w = render.warp_rgba(rgba, M, (W, H))
        a = w[..., 3:4].astype(np.float32) / 255.0
        canvas = (w[..., :3][..., ::-1] * a + canvas * (1 - a)).astype(np.uint8)
    for c, (_, _, _, col) in zip(cs, items):
        cv2.polylines(canvas, [((c - lo) * PPM).astype(np.int32).reshape(-1, 1, 2)], True, col, 1, cv2.LINE_AA)
    if W < minw:
        canvas = np.hstack([canvas, np.full((H, minw - W, 3), 40, np.uint8)])
        W = minw
    bar = np.full((18 * (len(lines) + 1) + 6, W, 3), 25, np.uint8)
    cv2.putText(bar, ascii_(title), (4, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    for k, ln in enumerate(lines):
        cv2.putText(bar, ascii_(ln), (4, 15 + 18 * (k + 1)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)
    return np.vstack([bar, canvas])


def main():
    P = pool.prepare()
    sh, pr, reps, rkeys = P["sh"], P["pr"], P["reps"], P["rkeys"]
    holes, _ = buracos.build(P)
    R_ = json.load(open(os.path.join(DOC, f"buraco{pool.fe.SUFFIX}.json"), encoding="utf-8"))
    rows = {h["rb"]: h for h in R_["holes"]}
    Q = P["Q"]

    def neighbours(rb):
        out = []
        for i in holes[rb]["queries"]:
            q = Q[i]
            out.append((q["a"], q["side_a"], q["xs"]))
        return out

    def panel(rb, z, rot, col, title, lines):
        X = reps[rkeys[rb]]
        nbs = neighbours(rb)
        items = [(X if False else reps[rkeys[z]], None, None, col)]
        # vizinhas colocadas contra X (no referencial de X)
        placed = []
        for pid, sa, xs in nbs:
            Rn, tn = rigid_for((sh[X], xs), (sh[pid], sa))
            placed.append((pid, Rn, tn, (0, 215, 255)))
        # candidata: o lado (xs_0 + rot) % 4 dela olha para a 1.ª vizinha, onde está o lado xs_0 de X
        pid0, sa0, xs0 = nbs[0]
        Rz, tz = same_for((sh[X], xs0), (sh[reps[rkeys[z]]], (xs0 + rot) % 4))
        placed.append((reps[rkeys[z]], Rz, tz, col))
        return draw(pr, sh, placed, title, lines)

    hits = [r for r in R_["holes"] if r["e5_hit100"] >= 0.5]
    step = max(1, len(hits) // 6)
    hit_sel = [hits[i * step] for i in range(6)]
    fails = sorted(R_["holes"], key=lambda r: (-r["e5_rank_full_str"], r["rb"]))
    fail_sel = fails[:6]
    info = []
    acertos = []
    for r in hit_sel:
        rb = r["rb"]
        lines = [f"{r['zone']} | {r['m']} vizinhas | prov {'+'.join(holes[rb]['prov'])}", f"E5 estrito top-1 em {100 * r['e5_hit100']:.0f} % dos sorteios (N=100); rank no pool completo {r['e5_rank_full_str']}"]
        acertos.append(panel(rb, rb, 0, (255, 200, 0), f"acerto: buraco de {reps[rkeys[rb]]}", lines))
        info.append(dict(kind="acerto", hole=reps[rkeys[rb]], **{k: r[k] for k in ("m", "zone", "e5_hit100", "e5_rank_full_str", "e4_rank_full_str")}))
    falhas = []
    for r in fail_sel:
        rb = r["rb"]
        lines = [f"{r['zone']} | {r['m']} vizinhas | prov {'+'.join(holes[rb]['prov'])}", f"rank da certa no pool completo: E5 {r['e5_rank_full_str']} | E4 {r['e4_rank_full_str']} (10^9 = nao passa os filtros)"]
        left = panel(rb, rb, 0, (255, 200, 0), f"falha: a certa {reps[rkeys[rb]]}", lines)
        w, wr = r["e5_winner"], r["e5_winner_rot"]
        if w is None:
            falhas.append(left)
            info.append(dict(kind="falha", hole=reps[rkeys[rb]], winner=None, **{k: r[k] for k in ("m", "zone", "e5_rank_full_str", "e4_rank_full_str")}))
            continue
        right = panel(rb, w, wr, (0, 140, 255), f"vencedora do E5: {reps[rkeys[w]]} rot {wr}", [f"{r['zone']}", "colocada no buraco pelo lado da 1.a vizinha"])
        falhas.append(hstack_pad([left, right]))
        info.append(dict(kind="falha", hole=reps[rkeys[rb]], winner=reps[rkeys[w]], winner_rot=wr, **{k: r[k] for k in ("m", "zone", "e5_rank_full_str", "e4_rank_full_str")}))

    def montage(imgs, name, per_row):
        rs = [hstack_pad(imgs[i:i + per_row], gap=14) for i in range(0, len(imgs), per_row)]
        w = max(r.shape[1] for r in rs)
        rs = [np.hstack([r, np.full((r.shape[0], w - r.shape[1], 3), 25, np.uint8)]) if r.shape[1] < w else r for r in rs]
        big = np.vstack([np.vstack([r, np.full((10, w, 3), 255, np.uint8)]) for r in rs])
        cv2.imwrite(os.path.join(DOC, name), big, [cv2.IMWRITE_JPEG_QUALITY, 80])
        print(name, big.shape, os.path.getsize(os.path.join(DOC, name)) // 1024, "KB")

    montage(acertos, "exemplos_buraco_acertos.jpg", 3)
    montage(falhas, "exemplos_buraco_falhas.jpg", 1)
    json.dump(info, open(os.path.join(DOC, "exemplos_buraco.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
