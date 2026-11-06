"""Verde na borda das peças no desenho do tabuleiro (RENDER.md §7): ``BOARD_SHADOW`` desligado vs ligado.

Mede pela entrada real da GUI (``render.compose_board`` com as poses de ``render/placements.json``, como
``Gui.region`` / ``Gui._compose``), no mesmo processo, com ``board_shadow=False`` e ``True``. Só lê
``projects/alpes`` (nada é escrito lá). Uso, da raiz::

    python tools/diagnostico/render/verde_tabuleiro.py [--n 100] [--seed 20261106] [--no-board] [--no-figs]

Por peça (vista da célula: 3 x 3 células a 300 dpi), no anel da peça (silhueta crua <= 1,5 mm para dentro e
0,3 mm de sangria para fora): píxeis «verdes» (``bg_distance`` < 29,5) e «esverdeados» (a* < -30, distância < 40,
L* < 62), % do contorno desenhado com um píxel desses a <= 2 px, e a porta do §6.1 sobre o recorte (perda <= 4,5 %,
>= 65 % do descartado na metade da sombra, perda nos lados iluminados <= 1,5 %, interior > 0,4 mm igual).
Tabuleiro inteiro: buracos por célula colocada (``compose_board`` a 120 px/célula, só peças, fundo magenta, inset
0,4 mm), como em ``docs/decisoes.md``. Saída: ``docs/diagnostico/render/verde_tabuleiro.json`` e as figuras
``verde_tabuleiro_*.jpg``.
"""

import argparse
import json
import os
import sys
import time

import cv2
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO)

from src import render as R  # noqa: E402
from src.state import Project  # noqa: E402

OUT_DIR = os.path.join(REPO, "docs", "diagnostico", "render")
TARGETS = ["P0778", "P0196", "P0198", "P0204", "P0234", "P0233"]
MAGENTA = (255, 0, 255)


def _lab_bgr(img):
    return R._lab(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))


def piece_metrics(pr, pid, PL, ppc):
    """Métricas de uma peça na vista da célula, com a regra desligada e ligada."""
    prof = pr.profile
    bg = prof.background_lab
    p = pr.piece(pid)
    l, c = p.celula
    reg = (max(1, l - 1), max(1, c - 1), min(prof.rows, l + 1), min(prof.cols, c + 1))
    w_mm, h_mm = float(prof.cell_mm["w"]), float(prof.cell_mm["h"])
    ppm = ppc / w_mm
    ox, oy = (reg[1] - 1) * w_mm * ppm, (reg[0] - 1) * h_mm * ppm
    W, H = int(round((reg[3] - reg[1] + 1) * w_mm * ppm)), int(round((reg[2] - reg[0] + 1) * h_mm * ppm))
    pl = PL.get(pid)
    if pl is None or pl.get("key") != R._entry_key(pr, pid):
        pl = R.register_piece(pr, pid, art=None, image=False)
    mmpp = R._scan_mmpp(pr, p.scan_id)
    A = R._crop_to_out(pl["theta_deg"], pl["pivot_mm"], R.cell_centre_mm(prof, *pl["cell"]), (pl["dx_mm"], pl["dy_mm"]),
                       np.asarray(p.bbox[:2], float), mmpp, (ppm, ppm), (ox, oy))
    raw = pr.crop_rgba(pid)
    Wr = R._warp(raw[..., 3].astype(np.float32) / 255.0, A, (W, H)) > 0.5
    px_mm = 1.0 / ppm
    k = max(1, int(round(0.3 / px_mm)))
    zone = cv2.dilate(Wr.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1))).astype(bool)
    ring = (zone & ~Wr) | (Wr & (R._depth_px(Wr) * px_mm <= 1.5))
    out = {"pid": pid, "cell": [l, c], "region": reg}
    imgs = {}
    for tag, flag in (("off", False), ("on", True)):
        img = R.compose_board(pr, ppc, region=reg, layers=("art", "pieces"), placements=PL, board_shadow=flag)
        imgs[tag] = img
        lab = _lab_bgr(img)
        d = R.bg_distance(lab, bg)
        grn = d < R.BG_DIST_MAX
        esv = (lab[..., 1] < -30) & (d < 40) & (lab[..., 0] < 62)
        # contorno desenhado: bordo da peça limpa (com a regra desta variante) no referencial da saída
        rgba = R._clean_or_crop(pr, pid)
        if flag:
            rgba = R._drop_shadow_paper(pr, pid, rgba)
        Wc = R._warp(rgba[..., 3].astype(np.float32) / 255.0, A, (W, H)) > 0.5
        edge = Wc & ~cv2.erode(Wc.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
        near = cv2.dilate((grn | esv).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))).astype(bool)
        out[tag] = dict(green=int((grn & ring).sum()), esverdeado=int((esv & ring).sum()), ring=int(ring.sum()),
                        contour_with_green=float((near & edge).sum() / max(1, edge.sum())))
    # porta do §6.1 sobre o recorte (o que a regra tira)
    cl = R._clean_or_crop(pr, pid)
    sh = R.shadow_paper_mask(cl, bg, mmpp)
    vis = cl[..., 3] > 0
    dep = R._depth_px(vis) * mmpp
    ys, xs = np.nonzero(vis)
    yy, xx = np.mgrid[0:vis.shape[0], 0:vis.shape[1]]
    shadow_half = (xx - xs.mean() < 0) | (yy - ys.mean() > 0)        # esquerda / baixo do scan (a sombra projeta-se para S e W)
    lit_side = ((xx - xs.mean()) > np.abs(yy - ys.mean())) | ((yy - ys.mean()) < -np.abs(xx - xs.mean()))
    n = int(sh.sum())
    drop = R._drop_shadow_paper(pr, pid, cl)
    inner = vis & (dep > R.DISPLAY_SHADOW_BAND_MM)
    out["gate"] = dict(dropped=n, loss=float(n / max(1, vis.sum())), shadow_share=(float((sh & shadow_half).sum() / n) if n else None),
                       lit_loss=float((sh & lit_side).sum() / max(1, (vis & lit_side).sum())),
                       interior_same=bool(np.array_equal(drop[inner], cl[inner])))
    g = out["gate"]
    g["pass"] = bool(g["loss"] <= 0.045 and (n < 50 or g["shadow_share"] >= 0.65) and g["lit_loss"] <= 0.015 and g["interior_same"])
    return out, imgs, (Wr, ring)


def holes(pr, PL, flag, ppc=120.0):
    prof = pr.profile
    img = R.compose_board(pr, ppc, layers=("pieces",), placements=PL, base_bgr=MAGENTA, board_shadow=flag)
    w_mm, h_mm = float(prof.cell_mm["w"]), float(prof.cell_mm["h"])
    ppm = ppc / w_mm
    ins = int(round(0.4 * ppm))
    mag = np.all(img == np.array(MAGENTA, np.uint8), -1)
    fr = []
    for l in range(1, prof.rows + 1):
        for c in range(1, prof.cols + 1):
            if pr.board[(l, c)]["estado"] != "colocada":
                continue
            x0, y0 = int(round((c - 1) * w_mm * ppm)) + ins, int(round((l - 1) * h_mm * ppm)) + ins
            x1, y1 = int(round(c * w_mm * ppm)) - ins, int(round(l * h_mm * ppm)) - ins
            fr.append(float(mag[y0:y1, x0:x1].mean()))
    fr = np.array(fr)
    return dict(cells=int(len(fr)), gt5=int((fr > 0.05).sum()), gt10=int((fr > 0.10).sum()), mean=float(fr.mean()))


def sample(pr, n, seed):
    rng = np.random.default_rng(seed)
    ids = [pid for pid in R.placed_ids(pr) if pid not in TARGETS and pr.piece(pid).celula is not None]
    grass = [p for p in ids if pr.piece(p).celula[0] >= 41]
    sky = [p for p in ids if pr.piece(p).celula[0] <= 14]
    rest = [p for p in ids if p not in grass and p not in sky]
    k = max(30, n * 3 // 10)
    pick = list(rng.choice(grass, min(k, len(grass)), replace=False)) + list(rng.choice(sky, min(k, len(sky)), replace=False))
    pick += list(rng.choice(rest, min(n - len(pick), len(rest)), replace=False))
    return [str(x) for x in pick]


def save_fig(path, rows, max_bytes=320_000):
    w = max(r.shape[1] for r in rows)
    rows = [np.hstack([r, np.full((r.shape[0], w - r.shape[1], 3), 255, np.uint8)]) if r.shape[1] < w else r for r in rows]
    big = np.vstack([np.vstack([r, np.full((8, w, 3), 255, np.uint8)]) for r in rows])
    q = 85
    while True:
        ok, buf = cv2.imencode(".jpg", big, [cv2.IMWRITE_JPEG_QUALITY, q])
        if len(buf) <= max_bytes or q <= 40:
            break
        if q <= 60:
            big = cv2.resize(big, (int(big.shape[1] * 0.85), int(big.shape[0] * 0.85)), interpolation=cv2.INTER_AREA)
        q -= 5
    open(path, "wb").write(buf.tobytes())
    print(" ", path, len(buf) // 1024, "KB")


def label(img, text):
    bar = np.full((22, img.shape[1], 3), 30, np.uint8)
    cv2.putText(bar, text, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return np.vstack([bar, img])


def zoom4(img, ring):
    """Zoom 4x do pedaço do anel com mais verde (o pior sítio)."""
    lab = _lab_bgr(img)
    d = R.bg_distance(lab, R_BG[0])
    bad = (((lab[..., 1] < -30) & (d < 40) & (lab[..., 0] < 62)) | (d < R.BG_DIST_MAX)) & ring
    ys, xs = np.nonzero(bad if bad.any() else ring)
    cy, cx = int(np.median(ys)), int(np.median(xs))
    s = 60
    y0, x0 = max(0, cy - s), max(0, cx - s)
    crop = img[y0:y0 + 2 * s, x0:x0 + 2 * s]
    return cv2.resize(crop, (crop.shape[1] * 4, crop.shape[0] * 4), interpolation=cv2.INTER_NEAREST), (y0, x0)


R_BG = [None]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", default=os.path.join(REPO, "projects", "alpes"))
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=20261106)
    ap.add_argument("--no-board", action="store_true")
    ap.add_argument("--no-figs", action="store_true")
    args = ap.parse_args(argv)
    t0 = time.time()
    pr = Project.open(args.project)
    R_BG[0] = pr.profile.background_lab
    PL = R.load_placements(pr)["placements"] or {}
    ppc = float(pr.profile.cell_mm["w"]) / (25.4 / 300.0)            # vista da célula a 300 dpi
    res = {"targets": [], "sample": [], "seed": args.seed}
    fig_rows, zoom_rows = [], []
    for pid in TARGETS:
        m, imgs, (Wr, ring) = piece_metrics(pr, pid, PL, ppc)
        res["targets"].append(m)
        print(f"{pid} {tuple(m['cell'])}: verde {m['off']['green']} -> {m['on']['green']} | esverdeado {m['off']['esverdeado']} -> {m['on']['esverdeado']} | "
              f"contorno com verde {100 * m['off']['contour_with_green']:.1f} -> {100 * m['on']['contour_with_green']:.1f} % | porta {m['gate']}")
        if not args.no_figs:
            a = label(imgs["off"], f"{pid} {tuple(m['cell'])} antes (BOARD_SHADOW=False)")
            b = label(imgs["on"], "depois (BOARD_SHADOW=True)")
            fig_rows.append(np.hstack([a, np.full((a.shape[0], 6, 3), 255, np.uint8), b]))
            za, (y0, x0) = zoom4(imgs["off"], ring)
            zb = cv2.resize(imgs["on"][y0:y0 + 120, x0:x0 + 120], (za.shape[1], za.shape[0]), interpolation=cv2.INTER_NEAREST)
            zoom_rows.append(np.hstack([label(za, f"{pid} 4x antes"), np.full((za.shape[0] + 22, 6, 3), 255, np.uint8), label(zb, "4x depois")]))
    print(f"alvos: {time.time() - t0:.0f}s")
    ids = sample(pr, args.n, args.seed)
    figs_sample = []
    for i, pid in enumerate(ids):
        m, imgs, (Wr, ring) = piece_metrics(pr, pid, PL, ppc)
        m["zone"] = "relva" if m["cell"][0] >= 41 else ("céu" if m["cell"][0] <= 14 else "resto")
        res["sample"].append(m)
        if not args.no_figs and len(figs_sample) < 4 and ((m["zone"] == "relva" and sum(1 for f in figs_sample if f[0] == "relva") < 2)
                                                          or (m["zone"] == "céu" and sum(1 for f in figs_sample if f[0] == "céu") < 2)):
            a = label(imgs["off"], f"{pid} {tuple(m['cell'])} {m['zone']} antes")
            b = label(imgs["on"], "depois")
            figs_sample.append((m["zone"], np.hstack([a, np.full((a.shape[0], 6, 3), 255, np.uint8), b])))
    S = res["sample"]
    worse = [m["pid"] for m in S if m["on"]["green"] > m["off"]["green"] or m["on"]["esverdeado"] > m["off"]["esverdeado"]
             or m["on"]["contour_with_green"] > m["off"]["contour_with_green"] + 1e-9]
    gate_fail = [(m["pid"], m["gate"]) for m in S if not m["gate"]["pass"]]
    res["sample_summary"] = dict(n=len(S), worse=worse, gate_fail=[g[0] for g in gate_fail],
                                 green_off=int(sum(m["off"]["green"] for m in S)), green_on=int(sum(m["on"]["green"] for m in S)),
                                 esv_off=int(sum(m["off"]["esverdeado"] for m in S)), esv_on=int(sum(m["on"]["esverdeado"] for m in S)),
                                 contour_off=float(np.mean([m["off"]["contour_with_green"] for m in S])),
                                 contour_on=float(np.mean([m["on"]["contour_with_green"] for m in S])),
                                 by_zone={z: dict(n=sum(1 for m in S if m["zone"] == z),
                                                  esv_off=int(sum(m["off"]["esverdeado"] for m in S if m["zone"] == z)),
                                                  esv_on=int(sum(m["on"]["esverdeado"] for m in S if m["zone"] == z)),
                                                  contour_off=float(np.mean([m["off"]["contour_with_green"] for m in S if m["zone"] == z] or [0])),
                                                  contour_on=float(np.mean([m["on"]["contour_with_green"] for m in S if m["zone"] == z] or [0])))
                                         for z in ("relva", "céu", "resto")})
    print("amostra:", {k: v for k, v in res["sample_summary"].items() if k != "by_zone"})
    print("por zona:", res["sample_summary"]["by_zone"])
    for pid, g in gate_fail:
        print("  porta §6.1 falha:", pid, g)
    print(f"amostra: {time.time() - t0:.0f}s")
    if not args.no_board:
        res["holes"] = {"off": holes(pr, PL, False), "on": holes(pr, PL, True)}
        print("buracos:", res["holes"], f"({time.time() - t0:.0f}s)")
    os.makedirs(OUT_DIR, exist_ok=True)
    json.dump(res, open(os.path.join(OUT_DIR, "verde_tabuleiro.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if not args.no_figs:
        save_fig(os.path.join(OUT_DIR, "verde_tabuleiro_alvos_1.jpg"), fig_rows[:3])
        save_fig(os.path.join(OUT_DIR, "verde_tabuleiro_alvos_2.jpg"), fig_rows[3:])
        save_fig(os.path.join(OUT_DIR, "verde_tabuleiro_zoom4.jpg"), zoom_rows)
        save_fig(os.path.join(OUT_DIR, "verde_tabuleiro_amostra.jpg"), [f[1] for f in figs_sample])
    return 0


if __name__ == "__main__":
    sys.exit(main())
