"""Triagem medida dos reports abertos (2026-11-07): pose, lados, silhueta e imagem das peças colocadas. Só leitura.

Uso, da raiz (sempre com ``--project`` numa CÓPIA de ``projects/alpes``)::

    python tools/diagnostico/reports/triagem_r3.py --project <cópia> [--scratch DIR] [--no-figs] [--no-holes]

A cópia deve ter ``render/placements.json`` feito por ``render.register_all(image=True, manual=False)`` (variante «image»); a pose
que a GUI mostra hoje (sem ``placements.json`` local) é recalculada aqui com ``register_piece(image=False)``
(variante «gui»). Nada é escrito no projeto: a saída vai para ``docs/diagnostico/reports/`` (JSON, tabelas
geradas, figuras <= 300 KB) e para ``--scratch`` (vistas grandes).

Módulos (PARTE 1 do plano de 2026-11-07):

1. Pose vs vizinhas: rotação face ao múltiplo de 90° (é sobretudo a inclinação da peça no scan, não um erro),
   inclinação no tabuleiro de cada lado (corda canto-a-canto e reta dos «ombros», que não depende dos cantos),
   inclinação do lado F face à linha da borda, folga por junta (``render.seam_gaps``) e cunha por junta (declive da
   folga ao longo da junta = rotação relativa das duas peças), resíduos e método do registo. Variantes «lados»
   (rotação pela reta dos ombros) e «vizinhas» (rotação pela cunha das juntas, Jacobi) medidas como hipótese,
   sem tocar em ``src/``.
2. Lados vs vizinhas: por junta, ``legacy.side_compat`` (T<->B, RMS do perfil, |dCorda|) com o lado de cada peça
   escolhido pelo ``k`` do registo por cantos; n.º de lados F vs a célula.
3. Silhueta vs nominal, sem cor: área face à mediana da classe, cordas face ao passo (18,5 / 17,9 mm + 0,4 mm de
   viés do scan), 4 cantos, défice do lado F; e (com cor, só como causa) fração do interior com a cor do papel.
4. Imagem na junta: dE Lab mediano entre as faixas de 0,3-1,3 mm de cada lado da linha de corte (8 troços), desvio
   de L* como medida de textura; ``locate.de_cell`` nas 4 rotações (informativo).
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
sys.path.insert(0, os.path.join(REPO, "tools", "diagnostico", "render"))

from src import render as R  # noqa: E402
from src.legacy import side_compat, page_rotation  # noqa: E402
from src.locate import CellArt, render_item, de_cell, body_beta_deg, wrap_deg  # noqa: E402
from src.state import Project, section_cell  # noqa: E402

OUT_DIR = os.path.join(REPO, "docs", "diagnostico", "reports")
TAG = "TRIAGEM-2026-11-07"
SEED = 20261107
REPORTED = {"R0010": "P0333", "R0022": "P0240", "R0024": "P0083", "R0027": "P0862", "R0011": "P0651",
            "R0012": "P0657", "R0018": "P0196", "R0019": "P0198", "R0020": "P0204", "R0023": "P0218", "R0001": "P0778"}
MAL_COLOCADAS = ["P0333", "P0240", "P0083", "P0840"]   # P0862 (R0027) desancorada pelo Tiago em 2026-11-06T23:55; P0840 está agora em (14,61)
EXTRA = ["P0590", "P0840", "P0839", "P0847", "P0848", "P0343", "P0833"]   # pendente 4; secções ancoradas a 2026-11-06; orientação
EMPTY_CELLS = [(42, 55), (43, 55), (44, 55), (45, 55), (44, 37), (45, 37)]
SCAN_BIAS_MM = 0.4                                  # corda do scan acima do passo nominal (segment_scan)
SHOULDER = ((0.04, 0.28), (0.72, 0.96))             # troços dos «ombros» de um lado T/B (fração da corda)
SHOULDER_Y = 0.06                                   # |desvio| máximo do ombro face à corda (fração da corda)
F_SPAN = (0.08, 0.92)
STRIP_MM = (0.3, 1.3)                               # faixa de imagem de cada lado da junta
N_BINS = 8
PAPER_DIST = 35.0                                   # «cor do papel»: bg_distance abaixo disto
NB_ITERS, NB_MAX_DEG = 8, 6.0


def w90(a):
    """Ângulo para (-45, 45]."""
    a = (float(a) + 45.0) % 90.0 - 45.0
    return a + 90.0 if a <= -45.0 else a


# ---------------------------------------------------------------- geometria de um lado
def side_seg(sh, i):
    a, b = int(sh.corners[i]), int(sh.corners[(i + 1) % 4])
    return sh.c[a:b + 1] if b > a else np.vstack([sh.c[a:], sh.c[:b + 1]])


def side_line_dir(sh, i):
    """Direção (graus, imagem) da reta dos ombros do lado ``i`` (do lado inteiro se F) e n.º de pontos."""
    seg = side_seg(sh, i)
    p0, p1 = seg[0], seg[-1]
    L = float(np.linalg.norm(p1 - p0))
    u = (p1 - p0) / L
    v = np.array([-u[1], u[0]])
    x, y = (seg - p0) @ u / L, (seg - p0) @ v / L
    if sh.sides[i].kind == "F":
        sel = (x > F_SPAN[0]) & (x < F_SPAN[1])
    else:
        sel = (((x > SHOULDER[0][0]) & (x < SHOULDER[0][1])) | ((x > SHOULDER[1][0]) & (x < SHOULDER[1][1]))) & (np.abs(y) < SHOULDER_Y)
    chord = float(np.degrees(np.arctan2(u[1], u[0])))
    if sel.sum() < 6:
        return chord, chord, 0
    b = np.polyfit(x[sel], y[sel], 1)[0]
    return chord + float(np.degrees(np.arctan(b))), chord, int(sel.sum())


def side_tilts(sh, theta, k):
    """Por lado: (direção no tabuleiro DIRS[(i+k)%4], inclinação da corda, inclinação da reta, pontos, tipo)."""
    out = []
    for i in range(4):
        j = (i + k) % 4
        line, chord, n = side_line_dir(sh, i)
        out.append(dict(dir=R.DIRS[j], kind=sh.sides[i].kind, chord_mm=float(sh.sides[i].chord_mm),
                        tilt_chord=w90(chord + theta - 90 * j), tilt_line=w90(line + theta - 90 * j), n=n))
    return out


def tilt_estimate(st):
    """Inclinação da peça pela reta dos ombros (média pesada, F pesa 2x; sem os lados a > 3° da mediana)."""
    t = np.array([s["tilt_line"] for s in st if s["n"] > 0])
    w = np.array([s["n"] * (2.0 if s["kind"] == "F" else 1.0) for s in st if s["n"] > 0])
    if len(t) == 0:
        return None
    med = float(np.median(t))
    keep = np.abs(t - med) <= 3.0
    if keep.sum() == 0:
        return med
    return float(np.sum(t[keep] * w[keep]) / np.sum(w[keep]))


# ---------------------------------------------------------------- juntas
def seam_list(pr, PL, shapes):
    """Juntas ortogonais com folga (como ``render.seam_gaps``), cunha (rotação relativa, graus) e lados."""
    prof = pr.profile
    off = float(((prof.calibration or {}).get("celula_silhueta") or {}).get("offset_mm") or 0.0)
    w, h = float(prof.cell_mm["w"]), float(prof.cell_mm["h"])
    by_cell = {tuple(e["cell"]): pid for pid, e in PL.items()}
    mats = {pid: R.placement_matrix(PL[pid], prof) for pid in PL}
    polys = {pid: R._apply(mats[pid], shapes[pid].c) for pid in PL}
    out = []
    for cell, a in sorted(by_cell.items()):
        for d, (dl, dc) in R._STEP.items():
            b = by_cell.get((cell[0] + dl, cell[1] + dc))
            if b is None:
                continue
            sa, sb = shapes[a], shapes[b]
            if d == "E":
                mid = np.array([cell[1] * w, (cell[0] - 0.5) * h])
                ed, half, sgn = np.array([0.0, 1.0]), h / 2, 1.0
            else:
                mid = np.array([(cell[1] - 0.5) * w, cell[0] * h])
                ed, half, sgn = np.array([1.0, 0.0]), w / 2, -1.0
            qa = R._facing_points(sa, mats[a], mid, ed, half)
            qb = R._facing_points(sb, mats[b], mid, ed, half)
            if len(qa) < 3 or len(qb) < 3:
                continue
            ga, gb = R._signed_gap(qa, polys[b]), R._signed_gap(qb, polys[a])
            g = 0.5 * (float(np.median(ga)) + float(np.median(gb)))
            s = np.r_[(qa - mid) @ ed, (qb - mid) @ ed]
            gg = np.r_[ga, gb]
            slope = float(np.polyfit(s, gg, 1)[0]) if np.ptp(s) > 1e-6 else 0.0
            rel = float(np.degrees(np.arctan(sgn * slope)))      # rotação de a menos a de b (graus)
            out.append(dict(a=a, b=b, cells=[list(cell), [cell[0] + dl, cell[1] + dc]], dir=d, gap_sil_mm=g,
                            gap_mm=g + 2 * off, gap_p10=float(np.percentile(gg, 10) + 2 * off),
                            gap_p90=float(np.percentile(gg, 90) + 2 * off), rel_deg=rel, mid=mid.tolist(), ed=ed.tolist(),
                            half=half))
    return out


def facing_side(PL, pid, d):
    """Índice do lado de ``pid`` virado para a direção ``d`` (N/E/S/W) segundo o k do registo por cantos."""
    c = PL[pid].get("corner") or {}
    if c.get("k") is None:
        return None
    j = R.DIRS.index(d)
    return (j - int(c["k"])) % 4


OPP = {"N": "S", "S": "N", "E": "W", "W": "E"}


def side_checks(PL, shapes, seams):
    for s in seams:
        da = s["dir"]
        ia, ib = facing_side(PL, s["a"], da), facing_side(PL, s["b"], OPP[da])
        if ia is None or ib is None or not shapes[s["a"]].ok or not shapes[s["b"]].ok:
            s["side"] = dict(ok=None, why="sem cantos")
            continue
        sa, sb = shapes[s["a"]].sides[ia], shapes[s["b"]].sides[ib]
        r = side_compat(sa, sb)
        s["side"] = dict(ok=bool(r["ok"]), why=r["why"], kinds=sa.kind + sb.kind, rms=float(r["rms"]),
                         dl=float(abs(sa.chord_mm - sb.chord_mm)))


def orientation_check(pr, PL, shapes, placed):
    """Por peça colocada: falhas de lado (F/tipo/RMS/dL) com as vizinhas montadas em cada uma das 4 atribuições
    cíclicas k (as vizinhas ficam com o seu k). Devolve só as peças cuja atribuição atual tem falhas."""
    prof = pr.profile
    by_cell = {tuple(PL[q]["cell"]): q for q in PL}
    out = {}
    for pid in placed:
        sh = shapes.get(pid)
        e = PL.get(pid)
        if sh is None or not sh.ok or e is None or (e.get("corner") or {}).get("k") is None:
            continue
        cell = tuple(e["cell"])
        k0 = int(e["corner"]["k"])
        flat = prof.flat_directions(*cell)
        res = {}
        for k in range(4):
            fails, n, cost = [], 0, 0.0
            for d, (dl, dc) in (("N", (-1, 0)), ("E", (0, 1)), ("S", (1, 0)), ("W", (0, -1))):
                q = by_cell.get((cell[0] + dl, cell[1] + dc))
                if q is None or not shapes[q].ok:
                    continue
                ii = facing_side(PL, q, OPP[d])
                if ii is None:
                    continue
                i = (R.DIRS.index(d) - k) % 4
                r = side_compat(sh.sides[i], shapes[q].sides[ii])
                n += 1
                if r["ok"]:
                    cost += r["cost"]
                else:
                    fails.append(f"{d}:{r['why']}")
            res[k] = dict(fails=fails, n=n, cost=cost, f_ok=bool(R._f_ok(sh, k, flat)))
        cur = res[k0]
        if cur["fails"]:
            alts = [k for k in range(4) if k != k0 and res[k]["f_ok"] and len(res[k]["fails"]) < len(cur["fails"])]
            out[pid] = dict(cell=list(cell), k=k0, fails=cur["fails"], n=cur["n"],
                            alts=[dict(k=k, rot=90 * ((k - k0) % 4), fails=res[k]["fails"], cost=res[k]["cost"]) for k in alts])
    return out


# ---------------------------------------------------------------- imagem na junta
class Crops:
    def __init__(self, pr):
        self.pr, self.c = pr, {}

    def get(self, pid):
        if pid not in self.c:
            p = self.pr.piece(pid)
            rgba = self.pr.crop_rgba(pid)
            mmpp = R._scan_mmpp(self.pr, p.scan_id)
            al = rgba[..., 3] > 0
            self.c[pid] = dict(lab=R._lab(np.ascontiguousarray(rgba[..., :3])).astype(np.float32), alpha=al,
                               depth=(R._depth_px(al) * mmpp).astype(np.float32), mmpp=mmpp,
                               origin=np.asarray(p.bbox[:2], float), rgba=rgba)
        return self.c[pid]


def strip_lab(crops, pr, PL, shapes, pid, pts_board, inward):
    """Lab (n, 3) da peça nos pontos ``pts_board`` deslocados para dentro, com o s ao longo da junta."""
    cr = crops.get(pid)
    A = R.placement_matrix(PL[pid], pr.profile)
    Ai = cv2.invertAffineTransform(A)
    labs, ss = [], []
    for dmm in np.linspace(STRIP_MM[0], STRIP_MM[1], 5):
        q = pts_board + dmm * inward
        sc = R._apply(Ai, q)
        px = sc / cr["mmpp"] - cr["origin"]
        xi, yi = np.round(px[:, 0]).astype(int), np.round(px[:, 1]).astype(int)
        H, W = cr["alpha"].shape
        ok = (xi >= 0) & (yi >= 0) & (xi < W) & (yi < H)
        ok[ok] &= cr["depth"][yi[ok], xi[ok]] >= STRIP_MM[0]
        labs.append(cr["lab"][yi[ok], xi[ok]])
        ss.append(np.nonzero(ok)[0])
    return labs, ss


def seam_image(crops, pr, PL, shapes, s):
    mid, ed, half = np.array(s["mid"]), np.array(s["ed"]), s["half"]
    u = np.array([ed[1], ed[0]])                      # de a para b (E: +x, S: +y)
    n = 60
    tt = np.linspace(-(1 - 2 * R.SEAM_TRIM) * half, (1 - 2 * R.SEAM_TRIM) * half, n)
    base = mid[None, :] + tt[:, None] * ed[None, :]

    # faixas a partir da linha de corte nominal; onde a patilha da vizinha entra, o ponto cai fora da peça (descartado)
    qa = qb = base
    la, ia = strip_lab(crops, pr, PL, shapes, s["a"], qa, -u)
    lb, ib = strip_lab(crops, pr, PL, shapes, s["b"], qb, u)
    LA = np.concatenate(la) if la else np.zeros((0, 3))
    LB = np.concatenate(lb) if lb else np.zeros((0, 3))
    IA = np.concatenate(ia) if ia else np.zeros(0, int)
    IB = np.concatenate(ib) if ib else np.zeros(0, int)
    bins = np.linspace(0, n, N_BINS + 1)
    des = []
    for k in range(N_BINS):
        ma = (IA >= bins[k]) & (IA < bins[k + 1])
        mb = (IB >= bins[k]) & (IB < bins[k + 1])
        if ma.sum() >= 5 and mb.sum() >= 5:
            des.append(float(np.linalg.norm(np.median(LA[ma], 0) - np.median(LB[mb], 0))))
    tex = float(np.mean([np.std(LA[:, 0]) if len(LA) else np.nan, np.std(LB[:, 0]) if len(LB) else np.nan]))
    return dict(de_med=float(np.median(des)) if des else None, de_max=float(np.max(des)) if des else None, n_bins=len(des),
                texture_L=tex)


# ---------------------------------------------------------------- silhueta
def silhouette(pr, PL, shapes, pid, crops, cls_med, sheet_med):
    p = pr.piece(pid)
    sh = shapes.get(pid) or pr.shape(pid)
    prof = pr.profile
    out = dict(pid=pid, scan=p.scan_id, n=p.n_no_lote, cell=list(p.celula) if p.celula else None, estado=p.estado,
               cls=p.cls, ok=bool(sh is not None and sh.ok), area=float(sh.area_mm2) if sh is not None else None)
    if sh is None:
        return out
    out["area_vs_cls"] = float(sh.area_mm2 / cls_med[sh.cls]) if sh.ok and sh.cls in cls_med else None
    out["area_vs_sheet"] = float(sh.area_mm2 / sheet_med[p.scan_id]) if p.scan_id in sheet_med else None
    if sh.ok:
        ch = [float(s.chord_mm) for s in sh.sides]
        e = PL.get(pid)
        if e is not None and (e.get("corner") or {}).get("k") is not None:
            k = int(e["corner"]["k"])
            exp = [(float(prof.cell_mm["w"]) if (i + k) % 2 == 0 else float(prof.cell_mm["h"])) + SCAN_BIAS_MM for i in range(4)]
            out["chord_ref"] = "célula"
        else:   # solta: o par de lados opostos mais longo é o horizontal (18,5)
            hz = (ch[0] + ch[2]) >= (ch[1] + ch[3])
            exp = [(float(prof.cell_mm["w"]) if (i % 2 == 0) == hz else float(prof.cell_mm["h"])) + SCAN_BIAS_MM for i in range(4)]
            out["chord_ref"] = "par mais longo"
        dev = [c - x for c, x in zip(ch, exp)]
        out.update(chords=ch, chord_dev=dev, min_dev=float(min(dev)),
                   f_dev=[d for d, s in zip(dev, sh.sides) if s.kind == "F"],
                   f_len=[float(s.chord_mm) for s in sh.sides if s.kind == "F"])
    cr = crops.get(pid)
    d = R.bg_distance(cr["lab"], pr.profile.background_lab)
    inner = cr["alpha"] & (cr["depth"] > 0.5)
    out["paper_frac"] = float((d[inner] < PAPER_DIST).mean()) if inner.any() else None
    return out


# ---------------------------------------------------------------- figuras
def label(img, text, h=22, scale=0.5):
    bar = np.full((h, img.shape[1], 3), 30, np.uint8)
    cv2.putText(bar, text, (4, h - 6), cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), 1, cv2.LINE_AA)
    return np.vstack([bar, img])


def save_jpg(path, img, max_bytes=300_000):
    q = 88
    while True:
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
        if len(buf) <= max_bytes or q <= 40:
            break
        if q <= 60:
            img = cv2.resize(img, (int(img.shape[1] * 0.85), int(img.shape[0] * 0.85)), interpolation=cv2.INTER_AREA)
        q -= 6
    with open(path, "wb") as f:
        f.write(buf.tobytes())
    return len(buf)


def grid(rows, pad=6):
    w = max(r.shape[1] for r in rows)
    rows = [np.hstack([r, np.full((r.shape[0], w - r.shape[1], 3), 255, np.uint8)]) if r.shape[1] < w else r for r in rows]
    return np.vstack([np.vstack([r, np.full((pad, w, 3), 255, np.uint8)]) for r in rows])


def hcat(imgs, pad=6):
    h = max(i.shape[0] for i in imgs)
    imgs = [np.vstack([i, np.full((h - i.shape[0], i.shape[1], 3), 255, np.uint8)]) if i.shape[0] < h else i for i in imgs]
    out = []
    for i in imgs:
        out += [i, np.full((h, pad, 3), 255, np.uint8)]
    return np.hstack(out[:-1])


def cell_view(pr, PL, pid, variants, *, region=None, ppc=None, depth_priority=True, draw=True):
    """Vista 3x3 a 300 dpi (``compose_board``) com o contorno da peça por variante e os 4 cantos."""
    prof = pr.profile
    p = pr.piece(pid)
    l, c = p.celula
    reg = region or (max(1, l - 1), max(1, c - 1), min(prof.rows, l + 1), min(prof.cols, c + 1))
    ppc = ppc or float(prof.cell_mm["w"]) / (25.4 / 300.0)
    img = R.compose_board(pr, ppc, region=reg, layers=("art", "pieces", "grid"), placements=PL, depth_priority=depth_priority)
    if not draw:
        return img
    ppm = ppc / float(prof.cell_mm["w"])
    ox, oy = (reg[1] - 1) * float(prof.cell_mm["w"]) * ppm, (reg[0] - 1) * float(prof.cell_mm["h"]) * ppm
    sh = pr.shape(pid)
    for (name, pl, col) in variants:
        pts = R._apply(R.placement_matrix(pl, prof), sh.c) * ppm - [ox, oy]
        cv2.polylines(img, [np.round(pts).astype(np.int32).reshape(-1, 1, 2)], True, col, 1, cv2.LINE_AA)
        if sh.ok:
            for q in R._apply(R.placement_matrix(pl, prof), sh.c[sh.corners]) * ppm - [ox, oy]:
                cv2.circle(img, (int(round(q[0])), int(round(q[1]))), 4, col, -1, cv2.LINE_AA)
    return img


def scan_view(pr, pids, pad=40, colours=None):
    """Recorte do scan original (sem limpeza) à volta de ``pids`` com o contorno (vermelho) e os cantos (amarelo)."""
    p0 = pr.piece(pids[0])
    sc = pr.model.scans[p0.scan_id]
    img = cv2.imread(os.path.join(REPO, sc["file"]), cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
    mmpp = R._scan_mmpp(pr, p0.scan_id)
    boxes = np.array([pr.piece(q).bbox for q in pids], float)
    x0, y0 = int(max(0, boxes[:, 0].min() - pad)), int(max(0, boxes[:, 1].min() - pad))
    x1 = int(min(img.shape[1], (boxes[:, 0] + boxes[:, 2]).max() + pad))
    y1 = int(min(img.shape[0], (boxes[:, 1] + boxes[:, 3]).max() + pad))
    raw = img[y0:y1, x0:x1].copy()
    ann = raw.copy()
    for i, q in enumerate(pids):
        sh = pr.shape(q)
        col = (colours or [(0, 0, 255)] * len(pids))[i]
        pts = sh.c / mmpp - [x0, y0]
        cv2.polylines(ann, [np.round(pts).astype(np.int32).reshape(-1, 1, 2)], True, col, 1, cv2.LINE_AA)
        if sh.ok:
            for j, cc in enumerate(sh.c[sh.corners] / mmpp - [x0, y0]):
                cv2.circle(ann, (int(round(cc[0])), int(round(cc[1]))), 5, (0, 255, 255), -1, cv2.LINE_AA)
        m = sh.c.mean(0) / mmpp - [x0, y0]
        cv2.putText(ann, f"{q} #{pr.piece(q).n_no_lote}", (int(m[0]) - 40, int(m[1])), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (255, 255, 255), 2, cv2.LINE_AA)
    return raw, ann


# ---------------------------------------------------------------- variantes de pose (hipóteses medidas)
def variant_lines(PL, est):
    out = {}
    for pid, e in PL.items():
        e2 = dict(e)
        t = est.get(pid)
        if t is not None:
            e2["theta_deg"] = float(e["theta_deg"] - t)
        out[pid] = e2
    return out


def variant_neighbours(pr, PL, shapes, iters=NB_ITERS):
    cur = {k: dict(v) for k, v in PL.items()}
    base = {k: float(v["theta_deg"]) for k, v in PL.items()}
    for _ in range(iters):
        sm = seam_list(pr, cur, shapes)
        acc = {k: [] for k in cur}
        for s in sm:
            acc[s["a"]].append(s["rel_deg"])
            acc[s["b"]].append(-s["rel_deg"])
        for k, v in acc.items():
            if not v:
                continue
            step = 0.5 * float(np.median(v))
            t = cur[k]["theta_deg"] - step
            t = base[k] + float(np.clip(t - base[k], -NB_MAX_DEG, NB_MAX_DEG))
            cur[k]["theta_deg"] = t
    return cur


def seam_summary(seams):
    g = np.array([s["gap_mm"] for s in seams])
    r = np.array([abs(s["rel_deg"]) for s in seams])
    return dict(n=len(seams), gap_med=float(np.median(g)), absgap_med=float(np.median(np.abs(g))),
                absgap_p95=float(np.percentile(np.abs(g), 95)), gt08=int((np.abs(g) > 0.8).sum()),
                gt15=int((np.abs(g) > 1.5).sum()), rel_med=float(np.median(r)), rel_p95=float(np.percentile(r, 95)),
                rel_gt2=int((r > 2).sum()), rel_gt3=int((r > 3).sum()))


def compare_seams(A, B):
    """Por junta (mesmas peças), quanto piora |folga| de A para B."""
    ka = {(s["a"], s["b"]): s for s in A}
    worse = []
    for s in B:
        a = ka.get((s["a"], s["b"]))
        if a is None:
            continue
        dd = abs(s["gap_mm"]) - abs(a["gap_mm"])
        worse.append(dd)
    worse = np.array(worse)
    return dict(n_worse_02=int((worse > 0.2).sum()), max_worse=float(worse.max()), n_better_02=int((worse < -0.2).sum()))


# ---------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", required=True)
    ap.add_argument("--scratch", default=None)
    ap.add_argument("--no-figs", action="store_true")
    ap.add_argument("--no-holes", action="store_true")
    args = ap.parse_args(argv)
    if os.path.normcase(os.path.abspath(args.project)) == os.path.normcase(os.path.join(REPO, "projects", "alpes")):
        print("usar uma cópia de projects/alpes (--project)")
        return 2
    T = {}
    t0 = time.time()
    pr = Project.open(args.project)
    prof = pr.profile
    scratch = args.scratch or os.path.join(args.project, "..", "triagem_r3")
    os.makedirs(scratch, exist_ok=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    placed = R.placed_ids(pr)
    shapes = {pid: pr.shape(pid) for pid in pr.pieces if pr.piece(pid).estado != "descartada"}
    PLimg = {k: v for k, v in R.load_placements(pr)["placements"].items() if not v.get("manual")}  # pose automática
    print(R.manual_pose_note(pr))
    PL = {}
    for pid in placed:
        r = R.register_piece(pr, pid, art=None, image=False, manual=False)
        if "error" not in r:
            PL[pid] = r
    T["registo_gui_s"] = time.time() - t0
    print(f"poses: gui {len(PL)}, image {len(PLimg)} ({T['registo_gui_s']:.1f} s)")
    res = {"seed": SEED, "n_placed": len(placed), "project_log_len": R._log_len(pr)}
    rng = np.random.default_rng(SEED)
    ctrl = [str(x) for x in rng.choice([p for p in placed if p not in REPORTED.values() and p not in EXTRA], 30, replace=False)]
    res["control"] = ctrl
    focus = list(dict.fromkeys(list(REPORTED.values()) + EXTRA))

    # ---- módulo 1: pose
    t1 = time.time()
    import collections
    res["methods"] = {"gui": dict(collections.Counter(e["method"] for e in PL.values())),
                      "image": dict(collections.Counter(e["method"] for e in PLimg.values()))}
    pose = {}
    for pid, e in PL.items():
        sh = shapes[pid]
        th = float(e["theta_deg"])
        d = dict(theta=th, dev90=abs(w90(th)), method=e["method"], residual=e.get("residual_mm"),
                 shape_residual=e.get("shape_residual_mm"), k=(e.get("corner") or {}).get("k"),
                 f_ok=(e.get("corner") or {}).get("f_ok"), theta_img=float(PLimg[pid]["theta_deg"]) if pid in PLimg else None,
                 method_img=PLimg[pid]["method"] if pid in PLimg else None)
        if sh.ok and d["k"] is not None:
            st = side_tilts(sh, th, int(d["k"]))
            d["sides"] = st
            d["tilt_chord_mean"] = float(np.mean([s["tilt_chord"] for s in st]))
            d["tilt_line"] = tilt_estimate(st)
            fl = profile_flat = prof.flat_directions(*pr.piece(pid).celula)
            d["flat_dirs"] = sorted(fl)
            d["f_tilt"] = [dict(dir=s["dir"], tilt_line=s["tilt_line"], tilt_chord=s["tilt_chord"]) for s in st if s["kind"] == "F"]
            d["n_flat"] = sum(1 for s in st if s["kind"] == "F")
            d["flat_ok"] = (d["n_flat"] == len(profile_flat)) and all(s["dir"] in profile_flat for s in st if s["kind"] == "F")
        pose[pid] = d
    seams = seam_list(pr, PL, shapes)
    ref = {(g["a"], g["b"]): g for g in R.seam_gaps(pr, PL)}
    dmax = max(abs(s["gap_mm"] - ref[(s["a"], s["b"])]["gap_mm"]) for s in seams)
    print(f"juntas {len(seams)}; |folga - render.seam_gaps| máx {dmax:.2e} mm")
    res["seam_check_vs_render_max_mm"] = dmax
    side_checks(PL, shapes, seams)
    by_piece = collections.defaultdict(list)
    for s in seams:
        by_piece[s["a"]].append((s, 1))
        by_piece[s["b"]].append((s, -1))
    for pid, d in pose.items():
        L = by_piece.get(pid, [])
        d["n_seams"] = len(L)
        if L:
            d["max_absgap"] = float(max(abs(s["gap_mm"]) for s, _ in L))
            d["max_absrel"] = float(max(abs(s["rel_deg"]) for s, _ in L))
            d["nb_rel_med"] = float(np.median([sg * s["rel_deg"] for s, sg in L]))
            d["side_bad"] = [f"{s['dir']}:{s['side']['why'] or 'ok'}" for s, _ in L if s["side"].get("ok") is False]
    T["pose_s"] = time.time() - t1

    est = {pid: d.get("tilt_line") for pid, d in pose.items()}
    PL_lines = variant_lines(PL, est)
    seams_lines = seam_list(pr, PL_lines, shapes)
    PL_nb = variant_neighbours(pr, PL, shapes)
    # variante F: só peças de moldura, rotação que põe a reta do(s) lado(s) F na linha da borda
    fest = {}
    for pid, d in pose.items():
        ft = [f["tilt_line"] for f in d.get("f_tilt", [])]
        if ft:
            fest[pid] = float(np.mean(ft))
    PL_F = variant_lines(PL, fest)
    seams_F = seam_list(pr, PL_F, shapes)
    seams_nb = seam_list(pr, PL_nb, shapes)
    seams_img = seam_list(pr, {k: v for k, v in PLimg.items()}, shapes)
    res["seams"] = {"gui": seam_summary(seams), "image": seam_summary(seams_img), "lados": seam_summary(seams_lines),
                    "vizinhas": seam_summary(seams_nb), "F": seam_summary(seams_F)}
    res["seams_cmp"] = {"lados": compare_seams(seams, seams_lines), "vizinhas": compare_seams(seams, seams_nb),
                        "image": compare_seams(seams, seams_img), "F": compare_seams(seams, seams_F)}
    border_ids = set(fest)
    res["seams_border"] = {name: seam_summary([q for q in sv if q["a"] in border_ids or q["b"] in border_ids])
                           for name, sv in (("gui", seams), ("lados", seams_lines), ("F", seams_F))}
    res["n_border_F"] = len(fest)
    for name, PLv in (("lados", PL_lines), ("vizinhas", PL_nb), ("F", PL_F)):
        for pid in pose:
            pose[pid][f"theta_{name}"] = float(PLv[pid]["theta_deg"])
    for name, sv in (("lados", seams_lines), ("vizinhas", seams_nb), ("F", seams_F)):
        bp = collections.defaultdict(list)
        for s in sv:
            bp[s["a"]].append(s)
            bp[s["b"]].append(s)
        for pid in pose:
            L = bp.get(pid, [])
            if L:
                pose[pid][f"max_absgap_{name}"] = float(max(abs(s["gap_mm"]) for s in L))
                pose[pid][f"max_absrel_{name}"] = float(max(abs(s["rel_deg"]) for s in L))
    print("juntas:", json.dumps(res["seams"], ensure_ascii=False))
    print("comparação:", res["seams_cmp"])

    # resumo de pose
    tl = np.array([abs(d["tilt_line"]) for d in pose.values() if d.get("tilt_line") is not None])
    dv = np.array([d["dev90"] for d in pose.values()])
    ftl = [(pid, f["tilt_line"]) for pid, d in pose.items() for f in d.get("f_tilt", [])]
    fta = np.array([abs(t) for _, t in ftl])
    res["pose_summary"] = dict(
        n=len(pose), dev90_gt15=int((dv > 1.5).sum()), dev90_gt3=int((dv > 3).sum()), dev90_med=float(np.median(dv)),
        tilt_line_n=len(tl), tilt_line_med=float(np.median(tl)), tilt_line_gt1=int((tl > 1).sum()), tilt_line_gt2=int((tl > 2).sum()),
        tilt_line_gt3=int((tl > 3).sum()), f_sides=len(fta), f_tilt_med=float(np.median(fta)), f_tilt_gt2=int((fta > 2).sum()),
        f_tilt_gt3=int((fta > 3).sum()), f_tilt_list_gt2=sorted([(pid, round(t, 2)) for pid, t in ftl if abs(t) > 2], key=lambda x: -abs(x[1])),
        flat_bad=[pid for pid, d in pose.items() if d.get("flat_ok") is False],
        no_corners=[pid for pid, d in pose.items() if "sides" not in d])
    print("pose:", {k: v for k, v in res["pose_summary"].items() if not isinstance(v, list)})

    # ---- módulo 2: lados
    sv = [s["side"] for s in seams]
    res["sides_summary"] = dict(n=len(sv), ok=sum(1 for x in sv if x.get("ok")), by_why=dict(collections.Counter(x.get("why") or "ok" for x in sv)),
                                bad=[dict(a=s["a"], b=s["b"], cells=s["cells"], **s["side"]) for s in seams if s["side"].get("ok") is False])
    rms_ok = np.array([x["rms"] for x in sv if x.get("kinds") in ("TB", "BT") and np.isfinite(x["rms"])])
    dl_all = np.array([x["dl"] for x in sv if "dl" in x])
    res["sides_summary"].update(rms_p50=float(np.median(rms_ok)), rms_p90=float(np.percentile(rms_ok, 90)),
                                dl_p50=float(np.median(dl_all)), dl_p90=float(np.percentile(dl_all, 90)))
    print("lados:", {k: v for k, v in res["sides_summary"].items() if k != "bad"})
    oc = orientation_check(pr, PL, shapes, placed)
    res["orientation"] = oc
    res["orientation_summary"] = dict(n_with_fail=len(oc), n_kind_or_F=sum(1 for v in oc.values() if any(":kind" in f or ":F" in f for f in v["fails"])),
                                      better_alt=sorted(p for p, v in oc.items() if v["alts"]),
                                      all_ok_alt=sorted(p for p, v in oc.items() if any(not a["fails"] for a in v["alts"])))
    print("orientação:", {k: v for k, v in res["orientation_summary"].items()})

    # ---- módulo 3: silhueta
    t3 = time.time()
    crops = Crops(pr)
    cls_areas = collections.defaultdict(list)
    sheet_areas = collections.defaultdict(list)
    for pid, sh in shapes.items():
        if sh is not None and sh.ok:
            cls_areas[sh.cls].append(sh.area_mm2)
            sheet_areas[pr.piece(pid).scan_id].append(sh.area_mm2)
    cls_med = {k: float(np.median(v)) for k, v in cls_areas.items() if len(v) >= 5}
    sheet_med = {k: float(np.median(v)) for k, v in sheet_areas.items()}
    res["cls_area_median"] = cls_med
    sil = {}
    for pid in shapes:
        if shapes[pid] is None or pr.piece(pid).crop_path is None:
            continue
        sil[pid] = silhouette(pr, PL, shapes, pid, crops, cls_med, sheet_med)
    crops.c.clear()
    T["silhueta_s"] = time.time() - t3

    def sil_flag(m):
        return bool(m.get("ok") and ((m.get("area_vs_cls") or 1) < 0.94 or m.get("min_dev", 0) < -1.5))
    res["silhouette"] = {pid: sil[pid] for pid in sil if pr.piece(pid).scan_id in ("S0009", "S0020") or pid in focus}
    placed_f = [(pid, min(sil[pid]["f_len"])) for pid in placed if pid in sil and sil[pid].get("f_len")]
    res["f_short"] = sorted([(pid, round(f, 2)) for pid, f in placed_f if f < 17.0], key=lambda x: x[1])
    pf = np.array([sil[p]["paper_frac"] for p in placed if p in sil and sil[p].get("paper_frac") is not None])
    res["sil_summary"] = dict(
        n_index=len(sil), n_flag=sum(sil_flag(m) for m in sil.values()),
        flag_placed=[pid for pid in placed if pid in sil and sil_flag(sil[pid])],
        flag_all=[pid for pid in sil if sil_flag(sil[pid])],
        paper_frac_p50=float(np.median(pf)), paper_frac_p90=float(np.percentile(pf, 90)),
        no_corners_all=[pid for pid, m in sil.items() if not m.get("ok")])
    for sid in ("S0009", "S0020"):
        ids = [pid for pid in sil if pr.piece(pid).scan_id == sid]
        res["sil_summary"][sid] = dict(n=len(ids), flag=[pid for pid in ids if sil_flag(sil[pid])],
                                       no4=[pid for pid in ids if not sil[pid]["ok"]],
                                       paper_gt=[pid for pid in ids if (sil[pid].get("paper_frac") or 0) > 0.05])
    print("silhueta:", {k: (v if not isinstance(v, list) else len(v)) for k, v in res["sil_summary"].items()})

    # ---- módulo 4: imagem na junta (todas as juntas) + de_cell nas peças focadas
    t4 = time.time()
    crops = Crops(pr)
    for s in seams:
        s["img"] = seam_image(crops, pr, PL, shapes, s)
    crops.c.clear()
    de_all = np.array([s["img"]["de_med"] for s in seams if s["img"]["de_med"] is not None])
    res["seam_image_summary"] = dict(n=len(de_all), de_p50=float(np.median(de_all)), de_p90=float(np.percentile(de_all, 90)),
                                     de_p97=float(np.percentile(de_all, 97)))
    T["imagem_juntas_s"] = time.time() - t4
    art = CellArt.load(prof, REPO)
    rot4 = {}
    for pid in focus + ctrl:
        if pid not in PL:
            continue
        p = pr.piece(pid)
        rgba = pr.crop_rgba(pid)
        mmpp = R._scan_mmpp(pr, p.scan_id)
        row = []
        for m in range(4):
            r = render_item(rgba, shapes[pid], PL[pid]["theta_deg"] + 90 * m, art, mmpp)
            dd = de_cell(r, *p.celula, art)
            row.append(dict(rot=90 * m, dE=dd["dE"], ncc=dd["ncc"]))
        tw = prof.twin(*p.celula) if hasattr(prof, "twin") else None
        rot4[pid] = dict(cell=list(p.celula), rots=row, twin=list(tw) if tw else None)
    res["de_cell"] = rot4
    T["imagem_s"] = time.time() - t4

    # ---- tabela por peça focada
    def seam_rows(pid):
        rows = []
        for s, sg in by_piece.get(pid, []):
            other = s["b"] if sg == 1 else s["a"]
            d = s["dir"] if sg == 1 else OPP[s["dir"]]
            rows.append(dict(dir=d, other=other, other_cell=pr.piece(other).celula, gap=s["gap_mm"], gap_p10=s["gap_p10"],
                             gap_p90=s["gap_p90"], rel=sg * s["rel_deg"], side=s["side"], img=s["img"],
                             other_fonte=pr.board[tuple(pr.piece(other).celula)]["fonte"]))
        return rows
    res["focus"] = {}
    for pid in focus + ctrl:
        if pid not in pose:
            continue
        d = dict(pose[pid])
        d["seams"] = seam_rows(pid)
        d["fonte"] = pr.board[tuple(pr.piece(pid).celula)]["fonte"]
        d["seccao"] = pr.piece(pid).seccao_id
        d["sil"] = sil.get(pid)
        res["focus"][pid] = d

    # ---- causa partilhada: rotação
    lines_abs = {pid: abs(d["tilt_line"]) for pid, d in pose.items() if d.get("tilt_line") is not None}
    nb_abs = {pid: abs(d.get("nb_rel_med", 0)) for pid, d in pose.items() if d.get("n_seams")}
    res["rotation_share"] = dict(
        tilt_line_gt2=sorted([p for p, v in lines_abs.items() if v > 2], key=lambda p: -lines_abs[p]),
        nb_rel_gt2=sorted([p for p, v in nb_abs.items() if v > 2], key=lambda p: -nb_abs[p]),
        both_gt2=sorted([p for p in lines_abs if lines_abs[p] > 2 and nb_abs.get(p, 0) > 2], key=lambda p: -lines_abs[p]))
    fl = {pid: min(sil[pid]["f_len"]) for pid in placed if pid in sil and sil[pid].get("f_len")}
    short = [p for p in fl if fl[p] < 17.0]
    res["rotation_vs_fshort"] = dict(
        n_short=len(short), short_tilt_gt2=sum(1 for p in short if lines_abs.get(p, 0) > 2),
        n_long=len(fl) - len(short), long_tilt_gt2=sum(1 for p in fl if fl[p] >= 17.0 and lines_abs.get(p, 0) > 2))
    sr = np.array([(pose[p]["shape_residual"] or 0, lines_abs.get(p, 0)) for p in pose if lines_abs.get(p) is not None and pose[p]["shape_residual"] is not None])
    res["rotation_vs_shape_residual_spearman"] = float(np.corrcoef(np.argsort(np.argsort(sr[:, 0])), np.argsort(np.argsort(sr[:, 1])))[0, 1])
    print("partilha:", {k: len(v) for k, v in res["rotation_share"].items()}, res["rotation_vs_fshort"],
          "spearman shres~tilt", round(res["rotation_vs_shape_residual_spearman"], 3))

    # ---- ponto 2: células vazias
    t2 = time.time()
    empty = {}
    loose_pool = [pid for pid, p in pr.pieces.items() if p.estado in ("solta", "em_seccao") and shapes.get(pid) is not None and shapes[pid].ok]
    for cell in EMPTY_CELLS:
        nb = []
        for d, (dl, dc) in (("N", (-1, 0)), ("E", (0, 1)), ("S", (1, 0)), ("W", (0, -1))):
            q = (cell[0] + dl, cell[1] + dc)
            b = pr.board[q]
            pid = b.get("peca_id") if b["estado"] == "colocada" else None
            side = None
            if pid and pid in PL:
                i = facing_side(PL, pid, OPP[d])
                if i is not None and shapes[pid].ok:
                    sd = shapes[pid].sides[i]
                    side = dict(kind=sd.kind, chord=float(sd.chord_mm), i=i)
            nb.append(dict(dir=d, cell=list(q), estado=b["estado"], fonte=b.get("fonte"), piece=pid, side=side))
        # molde: todas as soltas / em secção; 4 atribuições
        cands = []
        for pid in loose_pool:
            sh = shapes[pid]
            if sh.n_flat:
                continue
            for k in range(4):
                cost, n, bad = 0.0, 0, None
                for nbi in nb:
                    if nbi["side"] is None:
                        continue
                    j = R.DIRS.index(nbi["dir"])
                    i = (j - k) % 4
                    nsh = shapes[nbi["piece"]]
                    r = side_compat(sh.sides[i], nsh.sides[nbi["side"]["i"]])
                    if not r["ok"]:
                        bad = r["why"]
                        break
                    cost += r["cost"]
                    n += 1
                if bad is None and n:
                    p = pr.piece(pid)
                    cands.append(dict(piece=pid, k=k, cost=cost / n, n=n, scan=p.scan_id, n_no_lote=p.n_no_lote, estado=p.estado,
                                      seccao=p.seccao_id, cls=p.cls))
        cands.sort(key=lambda x: x["cost"])
        best = {}
        for c in cands:
            best.setdefault(c["piece"], c)
        empty[str(cell)] = dict(board=pr.board[cell], neighbours=nb, mould_n=len(best), mould_top=list(best.values())[:8],
                                n_pool=len(loose_pool))
    # secções candidatas
    sect = {}
    for gid in ("G0044", "G0049", "G0035", "G0034", "G0036", "G0037", "G0038", "G0039", "G0040", "G0042"):
        if gid not in pr.sections:
            continue
        s = pr.sections[gid]
        info = dict(kind=s.kind, scan=s.scan_id, anchor=s.anchor, candidates=(s.candidates or [])[:4], pieces=[])
        for pid, rc in s.cells_local.items():
            p = pr.piece(pid)
            info["pieces"].append(dict(piece=pid, rc=list(rc), n_no_lote=p.n_no_lote, estado=p.estado, cls=p.cls,
                                       cell=list(p.celula) if p.celula else None))
        for cand in (s.candidates or [])[:3]:
            an = dict(l0=cand["cell0"][0], c0=cand["cell0"][1], rot=cand["rot"], mirror=cand["mirror"])
            cand["cells"] = {pid: list(section_cell(an, rc)) for pid, rc in s.cells_local.items()}
        sect[gid] = info
    # verificação dos lados das peças propostas nas células (G0044 -> (44,55)/(45,55), G0049 -> (44,37))
    def fit_in_cell(pid, cell, rot):
        sh = shapes[pid]
        p = pr.piece(pid)
        s = pr.sections[p.seccao_id]
        rp = page_rotation([shapes[q] for q in s.cells_local if shapes.get(q) is not None])
        th0 = rp + wrap_deg(body_beta_deg(sh) - rp) + rot
        cr = R.corner_register(sh, prof, cell, th0)
        rows = []
        for d, (dl, dc) in (("N", (-1, 0)), ("E", (0, 1)), ("S", (1, 0)), ("W", (0, -1))):
            q = (cell[0] + dl, cell[1] + dc)
            b = pr.board[q] if 1 <= q[0] <= prof.rows and 1 <= q[1] <= prof.cols else None
            if b is None:
                continue
            npid = b.get("peca_id") if b["estado"] == "colocada" else None
            i = (R.DIRS.index(d) - cr["k"]) % 4
            row = dict(dir=d, cell=list(q), estado=b["estado"], piece=npid, my_kind=sh.sides[i].kind, my_chord=float(sh.sides[i].chord_mm))
            if npid and npid in PL:
                ii = facing_side(PL, npid, OPP[d])
                if ii is not None and shapes[npid].ok:
                    r = side_compat(sh.sides[i], shapes[npid].sides[ii])
                    row.update(nb_kind=shapes[npid].sides[ii].kind, ok=bool(r["ok"]), why=r["why"], rms=float(r["rms"]),
                               dl=float(abs(sh.sides[i].chord_mm - shapes[npid].sides[ii].chord_mm)))
            rows.append(row)
        return dict(piece=pid, cell=list(cell), rot=rot, theta=cr["theta_deg"], k=cr["k"], residual=cr["residual_mm"], sides=rows)
    fits = []
    for gid in ("G0044", "G0049"):
        s = pr.sections[gid]
        if not s.candidates:
            continue
        cand = s.candidates[0]
        an = dict(l0=cand["cell0"][0], c0=cand["cell0"][1], rot=cand["rot"], mirror=cand["mirror"])
        for pid, rc in s.cells_local.items():
            fits.append(dict(section=gid, **fit_in_cell(pid, section_cell(an, rc), cand["rot"])))
    res["empty_cells"] = empty
    res["sections"] = sect
    res["section_fits"] = fits
    T["vazias_s"] = time.time() - t2
    print("vazias:", {k: (v["mould_n"], [c["piece"] for c in v["mould_top"][:5]]) for k, v in empty.items()})

    # ---- ponto 4: junta (25,1)-(26,1) e par S0020
    j = [s for s in seams if s["cells"] == [[25, 1], [26, 1]]]
    res["seam_25_26_c1"] = j[0] if j else None

    # ---- tabelas geradas
    write_tables(pr, res, os.path.join(OUT_DIR, f"{TAG}_tabelas.md"))
    res["timing_s"] = T
    with open(os.path.join(OUT_DIR, f"{TAG}.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1, default=R._json_default)

    # ---- figuras
    if not args.no_figs:
        t5 = time.time()
        figs(pr, PL, PL_lines, PL_nb, res, scratch, PL_F)
        T["figuras_s"] = time.time() - t5
    if not args.no_holes:
        t6 = time.time()
        import verde_tabuleiro as VT
        res["holes"] = {"gui": VT.holes(pr, PL, True), "lados": VT.holes(pr, PL_lines, True),
                        "vizinhas": VT.holes(pr, PL_nb, True), "image": VT.holes(pr, PLimg, True),
                        "F": VT.holes(pr, PL_F, True)}
        T["buracos_s"] = time.time() - t6
        print("buracos:", res["holes"])
    res["timing_s"] = T
    with open(os.path.join(OUT_DIR, f"{TAG}.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1, default=R._json_default)
    print("tempos:", {k: round(v, 1) for k, v in T.items()}, f"total {time.time() - t0:.0f} s")
    return 0


def f2(v, n=2):
    return "—" if v is None else (f"{v:.{n}f}" if isinstance(v, (float, np.floating)) else str(v))


def write_tables(pr, res, path):
    L = [f"# {TAG}: tabelas geradas por `tools/diagnostico/reports/triagem_r3.py`", "",
         "Gerado; não editar à mão. Conclusões em `TRIAGEM-2026-11-07.md`.", ""]
    L += ["## Pose e juntas das peças focadas (pose da GUI = cantos, sem imagem)", "",
          "| peça | célula | método | θ | dev 90° | inclinação corda / ombros | resíduo / forma mm | juntas: dir vizinha folga [p10,p90] rot.rel. lados dE | θ lados | θ vizinhas |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for pid, d in res["focus"].items():
        js = "; ".join(f"{s['dir']} {s['other']} {s['gap']:+.2f} [{s['gap_p10']:+.1f},{s['gap_p90']:+.1f}] {s['rel']:+.1f}° "
                       f"{s['side'].get('kinds', '')}{'' if s['side'].get('ok') else ' ' + str(s['side'].get('why'))} "
                       f"rms {f2(s['side'].get('rms'))} dE {f2(s['img']['de_med'], 1)}" for s in d["seams"])
        tag = "**" if pid in res["control"] else ""
        L.append(f"| {pid}{' (ctrl)' if pid in res['control'] else ''} | {tuple(pr.piece(pid).celula)} | {d['method']} | {d['theta']:.2f} | {d['dev90']:.1f} | "
                 f"{f2(d.get('tilt_chord_mean'))} / {f2(d.get('tilt_line'))} | {f2(d['residual'])} / {f2(d['shape_residual'])} | {js} | "
                 f"{f2(d.get('theta_lados'))} | {f2(d.get('theta_vizinhas'))} |")
    L += ["", "## Silhueta (S0009, S0020 e focadas)", "",
          "| peça | folha nº | célula | cls | área mm² | área/classe | cordas | desvio face ao passo+0,4 | F mm | papel % |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for pid, m in sorted(res["silhouette"].items(), key=lambda kv: (kv[1]["scan"], kv[1]["n"] or 0)):
        L.append(f"| {pid} | {m['scan']} #{m['n']} | {tuple(m['cell']) if m['cell'] else '—'} | {m['cls']} | {f2(m['area'], 0)} | "
                 f"{f2(m.get('area_vs_cls'))} | {' '.join(f'{c:.1f}' for c in m.get('chords', []))} | "
                 f"{' '.join(f'{c:+.1f}' for c in m.get('chord_dev', []))} | {' '.join(f'{c:.1f}' for c in m.get('f_len', []))} | "
                 f"{f2(100 * m['paper_frac'] if m.get('paper_frac') is not None else None, 0)} |")
    L += ["", "## Células sem peça: molde (lados das vizinhas montadas; forma só, fraco)", ""]
    for cell, e in res["empty_cells"].items():
        nb = ", ".join(f"{n['dir']} {tuple(n['cell'])} {n['piece'] or n['estado']}{(' ' + n['side']['kind']) if n['side'] else ''}" for n in e["neighbours"])
        top = ", ".join(f"{c['piece']} ({c['scan']} #{c['n_no_lote']}, {c['seccao'] or c['estado']}, custo {c['cost']:.2f}, {c['n']} lados)" for c in e["mould_top"][:6])
        L.append(f"- **{cell}** vizinhas: {nb}. Compatíveis {e['mould_n']}/{e['n_pool']}: {top}")
    L += ["", "## Peças das secções candidatas nas células propostas", ""]
    for f in res["section_fits"]:
        sd = "; ".join(f"{r['dir']} {tuple(r['cell'])} {r['piece'] or r['estado']} {r['my_kind']}{'↔' + r['nb_kind'] if 'nb_kind' in r else ''}"
                       f"{(' ok' if r.get('ok') else ' ' + str(r.get('why'))) if 'ok' in r else ''}{(' rms %.2f dL %.2f' % (r['rms'], r['dl'])) if 'rms' in r and np.isfinite(r['rms']) else ''}"
                       for r in f["sides"])
        L.append(f"- {f['section']} {f['piece']} → {tuple(f['cell'])} rot {f['rot']}: {sd}")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(L) + "\n")


def figs(pr, PL, PL_lines, PL_nb, res, scratch, PL_F):
    out = {}
    red, cyan, mag = (0, 0, 255), (255, 255, 0), (255, 0, 255)
    # 1) mal colocadas + P0590 + P0657: vista 3x3 com contorno GUI (vermelho), lados (ciano), vizinhas (magenta)
    tiles = []
    for pid in MAL_COLOCADAS + ["P0657", "P0590"]:
        img = cell_view(pr, PL, pid, [("gui", PL[pid], red), ("lados", PL_lines[pid], cyan)]
                        + ([("F", PL_F[pid], (0, 220, 0))] if PL_F is not None and PL_F[pid]["theta_deg"] != PL[pid]["theta_deg"] else []))
        cv2.imwrite(os.path.join(scratch, f"pose_{pid}.png"), img)
        d = res["focus"][pid]
        tiles.append(label(cv2.resize(img, (img.shape[1] // 2, img.shape[0] // 2), interpolation=cv2.INTER_AREA),
                           f"{pid} {tuple(pr.piece(pid).celula)} th {d['theta']:.1f} ombros {f2(d.get('tilt_line'), 1)}", scale=0.42))
    big = grid([hcat(tiles[:3]), hcat(tiles[3:])])
    out["pose"] = save_jpg(os.path.join(OUT_DIR, f"{TAG}_pose.jpg"), big)
    # 1b) cantos no scan original das mal colocadas (contorno vermelho, cantos amarelos)
    tiles = []
    for pid in MAL_COLOCADAS + ["P0862", "P0590"]:
        raw, ann = scan_view(pr, [pid])
        cv2.imwrite(os.path.join(scratch, f"scan_{pid}.png"), np.hstack([raw, ann]))
        tiles.append(label(ann, f"{pid} {pr.piece(pid).scan_id} #{pr.piece(pid).n_no_lote} {pr.piece(pid).cls}", scale=0.45))
    out["cantos"] = save_jpg(os.path.join(OUT_DIR, f"{TAG}_cantos.jpg"), hcat(tiles))
    # 2) recorte comido: scan original vs contorno (P0198, P0218, P0204, P0196)
    tiles = []
    for pid in ["P0198", "P0218", "P0204", "P0196"]:
        raw, ann = scan_view(pr, [pid])
        cv2.imwrite(os.path.join(scratch, f"scan_{pid}.png"), np.hstack([raw, ann]))
        tiles.append(label(hcat([raw, ann]), f"{pid} {pr.piece(pid).scan_id} #{pr.piece(pid).n_no_lote}: scan | contorno", scale=0.45))
    big = grid([hcat(tiles[:2]), hcat(tiles[2:])])
    out["silhueta"] = save_jpg(os.path.join(OUT_DIR, f"{TAG}_silhueta.jpg"), big)
    # 3) vistas da célula R0018/R0020/R0001/R0019/R0023 (o que a GUI desenha)
    tiles = []
    for pid in ["P0196", "P0198", "P0204", "P0218", "P0778"]:
        img = cell_view(pr, PL, pid, [], draw=False)
        cv2.imwrite(os.path.join(scratch, f"celula_{pid}.png"), img)
        tiles.append(label(cv2.resize(img, (img.shape[1] // 2, img.shape[0] // 2), interpolation=cv2.INTER_AREA),
                           f"{pid} {tuple(pr.piece(pid).celula)}", scale=0.45))
    big = grid([hcat(tiles[:3]), hcat(tiles[3:])])
    out["celulas"] = save_jpg(os.path.join(OUT_DIR, f"{TAG}_celulas.jpg"), big)
    # 4) S0020 #24/#30: scan original com os dois contornos; vista (44..45,1)
    raw, ann = scan_view(pr, ["P0651", "P0657"], colours=[(0, 0, 255), (255, 0, 255)])
    cv2.imwrite(os.path.join(scratch, "scan_S0020_24_30.png"), np.hstack([raw, ann]))
    v = cell_view(pr, PL, "P0651", [("gui", PL["P0651"], red)], region=(43, 1, 46, 2))
    v = cell_view(pr, PL, "P0657", [("gui", PL["P0657"], mag)], region=(43, 1, 46, 2)) if False else v
    sh = pr.shape("P0657")
    ppm = float(pr.profile.cell_mm["w"]) / (25.4 / 300.0) / float(pr.profile.cell_mm["w"])
    pts = R._apply(R.placement_matrix(PL["P0657"], pr.profile), sh.c) * ppm - [0, 42 * float(pr.profile.cell_mm["h"]) * ppm]
    cv2.polylines(v, [np.round(pts).astype(np.int32).reshape(-1, 1, 2)], True, mag, 1, cv2.LINE_AA)
    cv2.imwrite(os.path.join(scratch, "celula_S0020_44_45_c1.png"), v)
    s = 0.5
    t1 = label(cv2.resize(hcat([raw, ann]), None, fx=s, fy=s, interpolation=cv2.INTER_AREA), "S0020 #24 P0651 (vermelho) / #30 P0657 (magenta): scan | contornos", scale=0.42)
    t2 = label(cv2.resize(v, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), "tabuleiro filas 43-46, colunas 1-2", scale=0.42)
    out["s0020"] = save_jpg(os.path.join(OUT_DIR, f"{TAG}_S0020.jpg"), hcat([t1, t2]))
    # 5) junta (25,1)-(26,1): prioridade de profundidade ligada / desligada
    a = cell_view(pr, PL, "P0" + "000", [], region=(24, 1, 27, 2), draw=False) if False else None
    imgs = []
    for dp in (True, False):
        img = R.compose_board(pr, float(pr.profile.cell_mm["w"]) / (25.4 / 300.0), region=(24, 1, 27, 2),
                              layers=("art", "pieces", "grid"), placements=PL, depth_priority=dp)
        cv2.imwrite(os.path.join(scratch, f"junta_25_26_c1_dp{int(dp)}.png"), img)
        imgs.append(label(cv2.resize(img, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA), f"filas 24-27 col 1-2, depth_priority={dp}", scale=0.42))
    out["junta_25_26"] = save_jpg(os.path.join(OUT_DIR, f"{TAG}_junta_25_26_c1.jpg"), hcat(imgs))
    # 6) secções candidatas das células vazias: scan original
    tiles = []
    for pids in (["P0501", "P0506"], ["P0573"]):
        raw, ann = scan_view(pr, pids)
        cv2.imwrite(os.path.join(scratch, f"scan_{'_'.join(pids)}.png"), ann)
        tiles.append(label(cv2.resize(ann, None, fx=0.6, fy=0.6, interpolation=cv2.INTER_AREA),
                           f"{pr.piece(pids[0]).scan_id} {pr.model.scans[pr.piece(pids[0]).scan_id]['file'].split('/')[-1]}", scale=0.42))
    out["vazias"] = save_jpg(os.path.join(OUT_DIR, f"{TAG}_vazias.jpg"), hcat(tiles))
    res["figures_bytes"] = out
    print("figuras:", out)


if __name__ == "__main__":
    sys.exit(main())
