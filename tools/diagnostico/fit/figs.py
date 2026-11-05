"""E-fit, passo 3: 12 exemplos visuais (6 acertos, 6 falhas escolhidas pelo pior rank) + refinamento da causa.

Cada painel mostra a peça A (consulta) com a candidata colocada no sítio: os dois cantos do lado de A coincidem com
os do lado da candidata (transformação rígida de 2 pontos), a candidata fica do outro lado. Nas falhas: à esquerda o
vizinho VERDADEIRO colocado, à direita o vencedor do E5 colocado. Saída: ``docs/diagnostico/fit/exemplos_*.jpg`` e
``exemplos.json``. Correr depois de ``fit_eval.py``.
"""

import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import REPO  # noqa: E402
from fit_eval import build, twin_map  # noqa: E402

from src import render  # noqa: E402

DOC = os.path.join(REPO, "docs", "diagnostico", "fit")
PPM = 7.0                        # px por mm no painel
PAD_MM = 4.0


def ascii_(t):
    import unicodedata
    return unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode().replace(" ", " ")


def side_pts(sh, i):
    s = sh.sides[i]
    return np.asarray(s.p0_mm, float), np.asarray(s.p1_mm, float)


def rigid_for(sa, sc):
    """R, t que levam o referencial da candidata ao de A: q1 -> p0, q0 -> p1 (lados que se encaram)."""
    p0, p1 = side_pts(*sa)
    q0, q1 = side_pts(*sc)
    va, vq = p1 - p0, q0 - q1
    ang = np.arctan2(va[1], va[0]) - np.arctan2(vq[1], vq[0])
    R = np.array([[np.cos(ang), -np.sin(ang)], [np.sin(ang), np.cos(ang)]])
    return R, p0 - R @ q1


def panel(pr, sh, pa, ia, pc, ic, title, lines):
    R, t = rigid_for((sh[pa], ia), (sh[pc], ic))
    ca = sh[pa].c
    cc = (sh[pc].c @ R.T) + t
    allp = np.vstack([ca, cc])
    lo, hi = allp.min(0) - PAD_MM, allp.max(0) + PAD_MM
    W, H = (np.ceil((hi - lo) * PPM)).astype(int)
    canvas = np.full((H, W, 3), 40, np.uint8)
    for pid, Rm, tm in ((pa, np.eye(2), np.zeros(2)), (pc, R, t)):
        rgba = render.piece_rgba_for_display(pr, pid)
        if rgba is None:
            continue
        p = pr.piece(pid)
        mmpp = render._scan_mmpp(pr, p.scan_id)
        origin = np.asarray(p.bbox[:2], float)
        # px do recorte -> mm (scan) -> rígido -> px do painel
        M = np.zeros((2, 3))
        M[:, :2] = PPM * mmpp * Rm
        M[:, 2] = PPM * (Rm @ (origin * mmpp) + tm - lo)
        w = render.warp_rgba(rgba, M, (W, H))
        a = w[..., 3:4].astype(np.float32) / 255.0
        canvas = (w[..., :3][..., ::-1] * a + canvas * (1 - a)).astype(np.uint8)
    for pts, col in ((ca, (0, 215, 255)), (cc, (255, 200, 0))):
        q = ((pts - lo) * PPM).astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(canvas, [q], True, col, 1, cv2.LINE_AA)
    p0, p1 = side_pts(sh[pa], ia)
    cv2.line(canvas, tuple(((p0 - lo) * PPM).astype(int)), tuple(((p1 - lo) * PPM).astype(int)), (0, 0, 255), 2, cv2.LINE_AA)
    MINW = 560
    if W < MINW:
        canvas = np.hstack([canvas, np.full((H, MINW - W, 3), 40, np.uint8)])
        W = MINW
    bar = np.full((18 * (len(lines) + 1) + 6, W, 3), 25, np.uint8)
    cv2.putText(bar, ascii_(title), (4, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    for k, ln in enumerate(lines):
        cv2.putText(bar, ascii_(ln), (4, 15 + 18 * (k + 1)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)
    return np.vstack([bar, canvas])


def hstack_pad(imgs, gap=6):
    h = max(i.shape[0] for i in imgs)
    out = []
    for i in imgs:
        pad = np.full((h - i.shape[0], i.shape[1], 3), 25, np.uint8)
        out.append(np.vstack([i, pad]))
        out.append(np.full((h, gap, 3), 255, np.uint8))
    return np.hstack(out[:-1])


def main():
    pr, t95, chord, sh, cl, members, reps = build()
    tw = twin_map(pr, sh, reps, t95)
    rkeys = sorted(reps)
    R = json.load(open(os.path.join(DOC, "resultados.json"), encoding="utf-8"))
    rows = R["results"]

    def cand(n):
        return reps[rkeys[n // 4]], n % 4

    hits = [r for r in rows if r.get("e5_lenient") == 1]
    step = max(1, len(hits) // 6)
    hit_sel = [hits[i * step] for i in range(6)]
    fails = [r for r in rows if r.get("e5_lenient") is None or r["e5_lenient"] > 1]
    none_f = sorted([r for r in fails if r.get("e5_lenient") is None], key=lambda r: -(r.get("true_rms") or 99))
    fin_f = sorted([r for r in fails if r.get("e5_lenient") is not None], key=lambda r: -r["e5_lenient"])
    fail_sel = none_f[:3] + fin_f[:3]

    info = []

    def build_example(r, kind):
        q = r["q"]
        pa, ia, pb, ib = q["a"], q["side_a"], q["b"], q["side_b"]
        base = f"{q['zone']} · {q['prov'][0]} · {q['kind_a']}>{q['kind_b']}"
        e4 = r.get("e4_lenient")
        e5 = r.get("e5_lenient")
        true_l = [f"E4 rank {e4}, E5 rank {e5}; RMS verdadeiro {r.get('true_rms') and round(r['true_rms'], 2)} mm; |dL| {round(r.get('true_dl', 0), 2)}"]
        left = panel(pr, sh, pa, ia, pb, ib, f"{kind}: {pa} s{ia} + vizinho {pb} s{ib}", [base] + true_l)
        entry = dict(a=pa, side_a=ia, b=pb, side_b=ib, e4=e4, e5=e5, zone=q["zone"], prov=q["prov"], true_rms=r.get("true_rms"))
        if kind == "falha" and r.get("best_e5") is not None:
            pc, ic = cand(r["best_e5"])
            # distância entre o lado vencedor e o lado verdadeiro (equivalentes geométricos?)
            sa, sw = sh[pb].sides[ib], sh[pc].sides[ic]
            eq = float(np.sqrt(np.mean(np.sum((sa.profile - sw.profile) ** 2, -1))) * (sa.chord_mm + sw.chord_mm) / 2)
            right = panel(pr, sh, pa, ia, pc, ic, f"vencedor do E5: {pc} lado {ic}", [f"RMS E4 {r['rms_best']:.2f} mm (verdadeiro {r.get('true_rms') and round(r['true_rms'], 2)})",
                                                                                  f"lado vencedor vs lado verdadeiro: {eq:.2f} mm"])
            entry.update(winner=pc, winner_side=ic, winner_vs_true_mm=eq)
            info.append(entry)
            return hstack_pad([left, right])
        info.append(entry)
        return left

    acertos = [build_example(r, "acerto") for r in hit_sel]
    falhas = [build_example(r, "falha") for r in fail_sel]

    def montage(imgs, name, per_row=2):
        rows_ = []
        for i in range(0, len(imgs), per_row):
            rows_.append(hstack_pad(imgs[i:i + per_row], gap=14))
        w = max(r.shape[1] for r in rows_)
        rows_ = [np.hstack([r, np.full((r.shape[0], w - r.shape[1], 3), 25, np.uint8)]) if r.shape[1] < w else r for r in rows_]
        big = np.vstack([np.vstack([r, np.full((10, w, 3), 255, np.uint8)]) for r in rows_])
        cv2.imwrite(os.path.join(DOC, name), big, [cv2.IMWRITE_JPEG_QUALITY, 80])
        print(name, big.shape, os.path.getsize(os.path.join(DOC, name)) // 1024, "KB")

    montage(acertos, "exemplos_acertos.jpg", 3)
    montage(falhas, "exemplos_falhas.jpg", 1)
    json.dump(info, open(os.path.join(DOC, "exemplos.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
