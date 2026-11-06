"""E-fit, passo 6: os casos do piloto (todos), os piores primeiro, com a candidata colocada no buraco. Correr depois de ``real.py``.

Ordem: posição E5 estrita no pool do lote com erosão (``real_encolhido.json``; sem rank = o pior), desempate pelo pool completo e
pelo id. Cada painel: a peça confirmada no seu buraco (ciano) com as vizinhas (amarelo, colocadas pelo lado que lhe encara o
buraco); nos casos com rank > 1, ao lado, a melhor candidata do lote (laranja) colocada no mesmo buraco com a rotação que o
custo escolheu. Saída: ``docs/diagnostico/fit/real_casos_{1,2}.jpg`` e ``real_casos.json``.
"""

import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pool  # noqa: E402
from common import REPO  # noqa: E402
from figs import hstack_pad, rigid_for  # noqa: E402
from figs_buraco import draw, same_for  # noqa: E402
from real import IDX, LOT_KIND  # noqa: E402
from gt import board_dirs  # noqa: E402

from src import render  # noqa: E402

DOC = os.path.join(REPO, "docs", "diagnostico", "fit")
BIG = 10 ** 9


def main():
    P = pool.prepare(prefer_kinds=(LOT_KIND,), with_queries=False)
    pr, sh = P["pr"], P["sh"]
    R = json.load(open(os.path.join(DOC, "real_encolhido.json"), encoding="utf-8"))
    R0 = {c["piece"]: c for c in json.load(open(os.path.join(DOC, "real.json"), encoding="utf-8"))["cases"]}
    sigma = R["sigma"]
    cases = sorted(R["cases"], key=lambda c: (-(c["a_e5_lote_str"] or BIG), -(c["a_e5_completo_str"] or BIG), c["piece"]))
    imgs, info = [], []
    for c in cases:
        Z = c["piece"]
        th = pr.piece(Z).theta_deg
        dz = board_dirs(sh[Z], th) if th is not None else {d: (sigma * IDX[d] + c["a_e5_rot_true"]) % 4 for d in IDX}
        nbs = c["nb"]
        items = []
        for n in nbs:
            Rn, tn = rigid_for((sh[Z], dz[n["d"]]), (sh[n["piece"]], n["side"]))
            items.append((n["piece"], Rn, tn, (0, 215, 255)))
        items.append((Z, np.eye(2), np.zeros(2), (255, 200, 0)))
        r0 = R0[Z]
        lines = [f"{c['m']} vizinhas ({', '.join(sorted(set(c['nb_kinds'])))}) | scan {c['scan']}",
                 f"a) E5 lote {c['a_e5_lote_str']} (sem erosao {r0['a_e5_lote_str']}) | completo {c['a_e5_completo_str']} | E4 lote {c['a_e4_lote_str']}",
                 f"b) tabuleiro: E5 rank {c['b_e5_todos']} de {c['b_n_buracos_todos']} buracos (sem erosao {r0['b_e5_todos']})"]
        left = draw(pr, sh, items, f"{Z} em {tuple(c['cell'])}", lines, minw=480)
        w = c["a_e5_winner"]
        if (c["a_e5_lote_str"] or BIG) > 1 and w:
            n0 = nbs[0]
            jw0 = (sigma * IDX[n0["d"]] + c["a_e5_winner_rot"]) % 4
            Rw, tw_ = same_for((sh[Z], dz[n0["d"]]), (sh[w], jw0))
            items_w = [it for it in items if it[0] != Z] + [(w, Rw, tw_, (0, 140, 255))]
            right = draw(pr, sh, items_w, f"vencedora do lote: {w} rot {c['a_e5_winner_rot']}", ["colocada no mesmo buraco"], minw=480)
            imgs.append(hstack_pad([left, right]))
        else:
            imgs.append(left)
        info.append(dict(piece=Z, cell=c["cell"], m=c["m"], a_e5_lote=c["a_e5_lote_str"], a_e5_completo=c["a_e5_completo_str"], b_e5=c["b_e5_todos"],
                         winner=w if (c["a_e5_lote_str"] or BIG) > 1 else None))

    def montage(sel, name):
        rs = [hstack_pad(sel[i:i + 2], gap=14) for i in range(0, len(sel), 2)]
        wd = max(r.shape[1] for r in rs)
        rs = [np.hstack([r, np.full((r.shape[0], wd - r.shape[1], 3), 25, np.uint8)]) if r.shape[1] < wd else r for r in rs]
        big = np.vstack([np.vstack([r, np.full((10, wd, 3), 255, np.uint8)]) for r in rs])
        cv2.imwrite(os.path.join(DOC, name), big, [cv2.IMWRITE_JPEG_QUALITY, 75])
        print(name, big.shape, os.path.getsize(os.path.join(DOC, name)) // 1024, "KB")

    montage(imgs[:8], "real_casos_1.jpg")
    montage(imgs[8:], "real_casos_2.jpg")
    json.dump(info, open(os.path.join(DOC, "real_casos.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
