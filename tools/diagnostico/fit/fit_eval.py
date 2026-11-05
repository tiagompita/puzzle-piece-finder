"""E-fit, passos 2-3: E4 (geometria) e E5 (geometria + continuidade de imagem) contra o GT de ``gt.py``.

Critérios fixados ANTES de correr em ``docs/diagnostico/fit/GT.md`` §5; este ficheiro só os implementa.
Só leitura. Saída: ``docs/diagnostico/fit/resultados.json`` (e ``strips.npz`` em cache local).
Correr da raiz: ``python tools/diagnostico/fit/fit_eval.py``.
"""

import collections
import json
import math
import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import REPO, open_project, physical_clusters  # noqa: E402

from src import render  # noqa: E402
from src.shape import chord_pass, corner_dist, f_adjacent, free_dist, side_complement, _neg_inv  # noqa: E402

SHRINK_MM = float(os.environ.get("FIT_SHRINK", "0"))      # exploratório (pós-hoc): erosão da silhueta em mm; 0 = critério fixado
SUFFIX = "" if SHRINK_MM == 0 else "_encolhido"
GT = os.path.join(REPO, "docs", "diagnostico", "fit", "gt_pairs.json")
OUT = os.path.join(REPO, "docs", "diagnostico", "fit", f"resultados{SUFFIX}.json")
CACHE = os.path.join(os.environ.get("PPF_SCRATCH", os.path.join(REPO, "docs", "diagnostico", "fit")), "strips_cache.npz")

# constantes fixadas em GT.md §5 (não se ajustam)
RMS_SCALE = 1.1          # mm
DE_SCALE = 10.0
N_STRIP = 12             # pontos ao longo do arco
T0, T1 = 0.08, 0.92
BAND_MM = (1.0, 2.5)     # profundidade da tira a partir da silhueta
HALF_WIN = 1.0 / 24.0    # meia-largura da janela (fração do arco)
MIN_VALID = 6
FAIL_RMS = 2.0           # "forma mal lida" se o RMS do lado verdadeiro >= isto
GEMEO_NEAR = 0.15        # mm
EQUIV_RMS = 0.5          # mm


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def shrink_sides(shape, d):
    """Lados da silhueta erodida ``d`` mm, alinhados ao índice dos lados da forma original (ou None).

    Exploratório e pós-hoc (``FIT_SHRINK``): o desvio de 0,48 mm vem do E-real (cantos BD, EREAL.md), não deste GT; o
    valor não se ajusta. A erosão desloca cada ponto do contorno ``d`` mm ao longo da normal interior.
    """
    from src.shape import analyse, _smooth_closed
    c = np.asarray(shape.c, float)
    cs = _smooth_closed(c, 3.0)
    t = np.roll(cs, -1, 0) - np.roll(cs, 1, 0)
    t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)
    nrm = np.stack([t[:, 1], -t[:, 0]], 1)

    def area(p):
        return 0.5 * np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1])
    a0 = abs(area(c))
    cand = c + d * nrm
    if abs(area(cand)) > a0:
        cand = c - d * nrm
    sh2 = analyse(cand, 1.0)                    # contorno já em mm
    if not sh2.ok:
        return None
    k = corner_dist(shape, sh2)[1]
    return [sh2.sides[(i + k) % 4] for i in range(4)]


# ---------------------------------------------------------------- tiras de imagem
def lab_of(rgb):
    lab = cv2.cvtColor(np.ascontiguousarray(rgb, np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
    lab[..., 0] *= 100.0 / 255.0
    lab[..., 1:] -= 128.0
    return lab


def piece_strips(pr, pid):
    """(4, N_STRIP, 3) Lab das tiras interiores de cada lado (NaN onde não há pixéis)."""
    sh = pr.shape(pid)
    out = np.full((4, N_STRIP, 3), np.nan, np.float32)
    if sh is None or not sh.ok:
        return out
    rgba = render.piece_rgba_for_display(pr, pid)
    if rgba is None:
        return out
    p = pr.piece(pid)
    mmpp = render._scan_mmpp(pr, p.scan_id)
    origin = np.asarray(p.bbox[:2], float)
    alpha = rgba[..., 3] > 0
    depth = render._depth_px(alpha) * mmpp                     # mm (1 px na silhueta)
    band = alpha & (depth >= BAND_MM[0]) & (depth <= BAND_MM[1])
    ys, xs = np.nonzero(band)
    if len(xs) == 0:
        return out
    lab = lab_of(rgba[..., :3])[ys, xs]
    cpx = sh.c / mmpp - origin                                  # contorno em px do recorte
    n = len(cpx)
    # contorno -> ponto mais próximo de cada pixel da tira
    P = np.stack([xs, ys], 1).astype(np.float32)
    near = np.empty(len(P), np.int32)
    for s in range(0, len(P), 4000):
        d2 = ((P[s:s + 4000, None, :] - cpx[None, ::2, :].astype(np.float32)) ** 2).sum(-1)
        near[s:s + 4000] = np.argmin(d2, 1) * 2
    cor = list(sh.corners)
    for i in range(4):
        a, b = cor[i], cor[(i + 1) % 4]
        length = (b - a) % n
        if length <= 0:
            continue
        frac = ((near - a) % n) / float(length)
        inside = frac <= 1.0
        for k in range(N_STRIP):
            t = T0 + (T1 - T0) * k / (N_STRIP - 1)
            m = inside & (np.abs(frac - t) <= HALF_WIN)
            if m.sum() >= 5:
                out[i, k] = np.median(lab[m], 0)
    return out


# ---------------------------------------------------------------- pool
def build():
    pr = open_project()
    t95 = float(pr.profile.calibration["silhueta_silhueta"]["t95"])
    chord = pr.profile.calibration["chord"]
    pids = [p for p, x in pr.pieces.items() if x.estado != "descartada"]
    sh = {p: pr.shape(p) for p in pids}
    cl, _ = physical_clusters(pr, pids, t95)
    members = collections.defaultdict(list)
    for p in pids:
        members[cl[p]].append(p)
    reps = {}
    for r, ms in members.items():
        ok = sorted(p for p in ms if sh[p] is not None and sh[p].ok)
        if ok:
            reps[r] = ok[0]
    return pr, t95, chord, sh, cl, members, reps


def twin_map(pr, sh, reps, t95):
    """gémea por silhueta (mesma classe, cordas, free <= t95, ΔE > 10, vizinhança mútua): {rep: [rep gémea]}."""
    keys = sorted(reps)
    Z = np.array([sh[reps[k]].z for k in keys])
    F = np.fft.fft(Z, axis=1)
    n = len(keys)
    D = np.full((n, n), np.inf)
    for i in range(n):
        corr = np.fft.ifft(np.conj(F[i])[None, :] * F, axis=1)
        m = np.abs(corr).max(1)
        rms2 = (np.sum(np.abs(Z[i]) ** 2) + np.sum(np.abs(Z) ** 2, 1) - 2 * m) / Z.shape[1]
        D[i] = np.sqrt(np.maximum(rms2, 0))
        D[i, i] = np.inf
    cls = [sh[reps[k]].cls for k in keys]
    labs = [np.asarray(pr.piece(reps[k]).mean_lab, float) if pr.piece(reps[k]).mean_lab is not None else None for k in keys]
    nn = {}
    for i in range(n):
        ok = [j for j in range(n) if j != i and cls[j] == cls[i]]
        nn[i] = min(ok, key=lambda j: D[i, j]) if ok else None
    tw = collections.defaultdict(list)
    for i in range(n):
        j = nn[i]
        if j is None or nn[j] != i or D[i, j] > t95 or labs[i] is None or labs[j] is None:
            continue
        if float(np.linalg.norm(labs[i] - labs[j])) <= 10.0:
            continue
        if not chord_pass(sh[reps[keys[i]]], sh[reps[keys[j]]])[0]:
            continue
        tw[keys[i]].append(keys[j])
        tw[keys[j]].append(keys[i])
    return tw


def main():
    t_start = time.time()
    pr, t95, chord, sh, cl, members, reps = build()
    g = json.load(open(GT, encoding="utf-8"))
    queries = [q for q in g["queries"] if {q["kind_a"], q["kind_b"]} == {"T", "B"}]       # GT primário (T<->B)
    others = [q for q in g["queries"] if {q["kind_a"], q["kind_b"]} != {"T", "B"}]
    print(f"pool: {len(reps)} peças físicas; consultas T-B {len(queries)}; incompatíveis (estrato à parte) {len(others)}")
    tw = twin_map(pr, sh, reps, t95)
    print("peças físicas com gémea no pool:", len(tw))

    # lados em uso (originais, ou erodidos se FIT_SHRINK > 0), sempre com o índice dos lados originais
    SIDES = {}

    def sides_of(pid):
        if pid not in SIDES:
            base = list(sh[pid].sides)
            if SHRINK_MM > 0:
                alt = shrink_sides(sh[pid], SHRINK_MM)
                if alt is not None:
                    base = alt
            SIDES[pid] = base
        return SIDES[pid]

    # candidatos: todos os lados de todos os reps
    rkeys = sorted(reps)
    kind, chordv, prof, fadj, owner, sidx = [], [], [], [], [], []
    for r in rkeys:
        sds = sides_of(reps[r])
        fa = f_adjacent([x.kind for x in sds])
        for i, sd in enumerate(sds):
            kind.append(sd.kind)
            chordv.append(sd.chord_mm)
            prof.append(_neg_inv(sd.profile))
            fadj.append(fa[i])
            owner.append(r)
            sidx.append(i)
    kind = np.array(kind)
    chordv = np.array(chordv)
    PN = np.array(prof)
    fadj = np.array(fadj)
    owner = np.array(owner)
    sidx = np.array(sidx)
    index_of = {(o, i): n for n, (o, i) in enumerate(zip(owner, sidx))}
    N_all = len(kind)

    # tiras (cache)
    cache = {}
    if os.path.exists(CACHE):
        z = np.load(CACHE, allow_pickle=True)
        cache = {k: z[k] for k in z.files}
    need = {reps[r] for r in rkeys} | {q["a"] for q in queries} | {q["a"] for q in others}
    todo = [p for p in sorted(need) if p not in cache]
    print("tiras a calcular:", len(todo), "de", len(need))
    for n, p in enumerate(todo):
        cache[p] = piece_strips(pr, p)
        if n % 100 == 0:
            print("  ", n, f"{time.time() - t_start:.0f}s")
    if todo:
        np.savez_compressed(CACHE, **cache)
    S_cand = np.stack([cache[reps[o]][i] for o, i in zip(owner, sidx)])           # (N, 12, 3)

    def accepted_for(q):
        """índices (no vetor de candidatos) dos lados aceites: B e as gémeas de B, mapeados por homologous_k."""
        b = q["b"]
        rb = cl[b]
        acc_strict, acc_twin = [], []
        if rb in reps:
            k = corner_dist(sh[b], sh[reps[rb]])[1] if b != reps[rb] else 0
            acc_strict.append(index_of[(rb, (q["side_b"] + k) % 4)])
            for rt in tw.get(rb, []):
                kt = corner_dist(sh[reps[rb]], sh[reps[rt]])[1]
                # lado homólogo do rep de B no rep da gémea
                j = (((q["side_b"] + k) % 4) + kt) % 4
                acc_twin.append(index_of[(rt, j)])
        return acc_strict, acc_twin

    def rank_query(q):
        a = q["a"]
        sda = sides_of(a)
        sa = sda[q["side_a"]]
        fa_a = f_adjacent([x.kind for x in sda])[q["side_a"]]
        ca = cl[a]
        # rms vetorizado
        rms = np.sqrt(np.mean(np.sum((sa.profile[None] - PN) ** 2, -1), -1)) * (sa.chord_mm + chordv) / 2.0
        comp = ((kind == "T") & (sa.kind == "B")) | ((kind == "B") & (sa.kind == "T"))
        own = owner == ca
        dl = np.abs(sa.chord_mm - chordv)
        tol = np.where(fa_a | fadj, chord["f_adj_mm"], chord["normal_mm"])
        ok = comp & ~own
        passed = ok & (dl <= tol)
        # imagem
        Sq = cache[a][q["side_a"]]                                                   # (12, 3)
        diff = np.linalg.norm(Sq[None] - S_cand[:, ::-1], axis=-1)                    # (N, 12) posição espelhada
        valid = np.isfinite(diff).sum(1)
        de = np.where(valid >= MIN_VALID, np.nanmedian(np.where(np.isfinite(diff), diff, np.nan), axis=1), np.nan)
        acc_s, acc_t = accepted_for(q)
        out = dict(n_all=N_all, n_comp=int(ok.sum()), n_pass=int(passed.sum()))
        for name, acc in (("lenient", acc_s + acc_t), ("strict", acc_s)):
            acc = [x for x in acc if not own[x]]
            m_in = int(sum(1 for x in acc if passed[x]))
            out[f"m_{name}"] = len(acc)
            out[f"m_pass_{name}"] = m_in
        res = {}
        scores = {"e4": rms, "e4_cost": rms + 0.5 * dl, "e5": rms / RMS_SCALE + de / DE_SCALE, "img": de}
        for sname, sc in scores.items():
            s = np.where(passed & np.isfinite(sc), sc, np.inf)
            order = np.argsort(s, kind="stable")
            pos = np.empty(len(s), int)
            pos[order] = np.arange(len(s))
            for name, acc in (("lenient", acc_s + acc_t), ("strict", acc_s)):
                acc = [x for x in acc if not own[x] and np.isfinite(s[x])]
                res[f"{sname}_{name}"] = int(min(pos[x] for x in acc)) + 1 if acc else None
            if sname == "e4":
                top = order[0] if np.isfinite(s[order[0]]) else None
                res["best_e4"] = int(top) if top is not None else None
            if sname == "e5":
                top = order[0] if np.isfinite(s[order[0]]) else None
                res["best_e5"] = int(top) if top is not None else None
        # diagnóstico do lado verdadeiro
        accs = [x for x in (acc_s or []) if not own[x]]
        if accs:
            x = accs[0]
            res["true_rms"] = float(rms[x]) if np.isfinite(rms[x]) else None
            res["true_kind_ok"] = bool(comp[x])
            res["true_dl"] = float(dl[x])
            res["true_chord_pass"] = bool(passed[x])
            res["true_de"] = None if not np.isfinite(de[x]) else float(de[x])
        else:
            res["no_true_in_pool"] = True
        res.update(out)
        res["rms_best"] = float(rms[res["best_e4"]]) if res.get("best_e4") is not None else None
        # estrutura para a figura: melhor do E4 e do E5
        return res

    results = []
    for q in queries:
        r = rank_query(q)
        r["q"] = q
        results.append(r)
    print(f"consultas avaliadas: {len(results)} ({time.time() - t_start:.0f}s)")
    json.dump(dict(results=[dict(r, q=dict(r["q"])) for r in results], N_all=N_all, n_reps=len(reps),
                   n_twin_reps=len(tw), constants=dict(RMS_SCALE=RMS_SCALE, DE_SCALE=DE_SCALE)),
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=0, default=lambda o: float(o) if isinstance(o, np.floating) else int(o))
    print("escrito", OUT)


if __name__ == "__main__":
    main()
