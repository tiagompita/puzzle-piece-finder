"""E-fit, passo 6: piloto do caso real (soltas de lote contra o tabuleiro). Só leitura.

Critérios fixados ANTES de correr em ``docs/diagnostico/fit/RESULTADOS.md`` §14; este ficheiro só os implementa.
O GT lê-se do log por critério (nada de lista fixa): ``python tools/diagnostico/fit/real.py`` volta a correr sem
alterações quando houver mais confirmações físicas (eventos ``placed`` com ``origin = "gemeo"``).
Saída: ``docs/diagnostico/fit/real{,_encolhido}.json`` (``FIT_SHRINK=0.48`` para a condição com erosão).
"""

import collections
import json
import math
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import buraco as B  # noqa: E402
import pool  # noqa: E402
import fit_eval as fe  # noqa: E402
from common import REPO  # noqa: E402
from gt import DIRS, OPP, STEP, board_dirs  # noqa: E402

from src import render  # noqa: E402

LOT_KIND = "soltas"
IDX = {"N": 0, "E": 1, "S": 2, "W": 3}
OUT = os.path.join(REPO, "docs", "diagnostico", "fit", f"real{fe.SUFFIX}.json")
MIN_FOR_VERDICT = 20
TARGET = 0.85


def scan_kind(pr, sid):
    return (pr.model.scans.get(sid) or {}).get("kind")


def dirs_of(pr, sh, pid, cache):
    if pid not in cache:
        th = render.initial_theta(pr, pid)
        sd = sh.get(pid)
        cache[pid] = board_dirs(sd, th) if (th is not None and sd is not None and sd.ok) else None
    return cache[pid]


def neighbours(pr, sh, cell, exclude, dcache):
    """Vizinhas ortogonais ``colocada`` de ``cell`` com forma e pose: [{d, piece, side}] (side = o lado dela que olha para ``cell``)."""
    out = []
    for d in DIRS:
        c = (cell[0] + STEP[d][0], cell[1] + STEP[d][1])
        if not (1 <= c[0] <= pr.profile.rows and 1 <= c[1] <= pr.profile.cols):
            continue
        b = pr.board[c]
        pid = b.get("peca_id")
        if b["estado"] != "colocada" or not pid or pid == exclude:
            continue
        dr = dirs_of(pr, sh, pid, dcache)
        if dr is None:
            continue
        out.append(dict(d=d, piece=pid, side=dr[OPP[d]], scan=pr.piece(pid).scan_id))
    return out


def gt_cases(pr, sh, dcache):
    """Confirmações físicas (d): ``placed`` com origem ``gemeo`` de peças de scans de lote, ainda colocadas ali, com >= 1 vizinha."""
    seen, cases = {}, []
    for e in pr.events():
        if e["action"] == "placed" and e.get("origin") == "gemeo":
            seen[e["piece"]] = tuple(e["cell"])
    for pid, cell in seen.items():
        p = pr.piece(pid)
        if p.estado != "colocada" or p.celula is None or tuple(p.celula) != cell:
            continue
        if scan_kind(pr, p.scan_id) != LOT_KIND or sh.get(pid) is None or not sh[pid].ok:
            continue
        nbs = neighbours(pr, sh, cell, pid, dcache)
        if nbs:
            cases.append(dict(piece=pid, cell=cell, nbs=nbs))
    return sorted(cases, key=lambda c: c["piece"])


def orientation(pr, sh, dcache):
    """σ = +1 se o índice do lado cresce com o ângulo N→E→S→W no tabuleiro (medido nas peças colocadas)."""
    cnt = collections.Counter()
    for pid, p in pr.pieces.items():
        if p.estado == "colocada":
            dr = dirs_of(pr, sh, pid, dcache)
            if dr:
                cnt[(dr["E"] - dr["N"]) % 4] += 1
    return (1 if cnt[1] >= cnt[3] else -1), dict(cnt)


def joint_one(C, xs):
    """C (m, 4) custos dos 4 lados de UMA candidata; xs (m,) -> min_r média."""
    m = C.shape[0]
    best = math.inf
    for r in range(4):
        v = float(np.mean(C[np.arange(m), (xs + r) % 4]))
        best = min(best, v)
    return best


def rank_among(J, acc, members):
    """1 + nº de membros (fora de ``acc``) com custo estritamente menor que o melhor de ``acc``; None se ∞."""
    best = min(J[a] for a in acc)
    if not np.isfinite(best):
        return None
    mem = [x for x in members if x not in set(acc)]
    return int(1 + (J[mem] < best).sum())


def quartiles(v):
    v = np.asarray([x for x in v if x is not None and np.isfinite(x)], float)
    if len(v) == 0:
        return None
    return dict(n=int(len(v)), q1=float(np.percentile(v, 25)), med=float(np.median(v)), q3=float(np.percentile(v, 75)))


def main():
    t0 = time.time()
    P = pool.prepare(prefer_kinds=(LOT_KIND,), with_queries=False)
    pr, sh, reps, rkeys, rindex, cl, tw = P["pr"], P["sh"], P["reps"], P["rkeys"], P["rindex"], P["cl"], P["tw"]
    R = P["R"]
    dcache = {}
    sigma, ocount = orientation(pr, sh, dcache)
    cases = gt_cases(pr, sh, dcache)
    byn = collections.Counter(len(c["nbs"]) for c in cases)
    cross = sum(1 for c in cases if any(scan_kind(pr, n["scan"]) != LOT_KIND for n in c["nbs"]))
    print(f"GT (d, scans de lote): {len(cases)} casos; por nº de vizinhas {dict(sorted(byn.items()))}; com vizinhas de outro tipo de scan (página montada/blocos): {cross}")
    print("veredicto possível" if len(cases) >= MIN_FOR_VERDICT else f"n < {MIN_FOR_VERDICT}: SEM veredicto (piloto)")
    print(f"orientação σ = {sigma:+d} (contagem (E-N) mod 4 nas peças colocadas: {ocount})  ({time.time() - t0:.0f}s)")

    costs = P["costs"]
    ccache = {}

    def cost_vec(pid, side):
        k = (pid, side)
        if k not in ccache:
            ccache[k] = costs(pid, side)
        return ccache[k]

    lot_idx = np.array([i for i, k in enumerate(rkeys) if scan_kind(pr, pr.piece(reps[k]).scan_id) == LOT_KIND])
    # buracos reais: células vazias com >= 1 vizinha colocada (por caso, sem a própria peça)
    empty = [(l, c) for l in range(1, pr.profile.rows + 1) for c in range(1, pr.profile.cols + 1) if pr.board[(l, c)]["estado"] == "vazia"]
    out_cases = []
    for ci, cs in enumerate(cases):
        Z, cell = cs["piece"], cs["cell"]
        zi = rindex[cl[Z]]
        assert reps[rkeys[zi]] == Z, ("a representante não é a cópia do lote", Z, reps[rkeys[zi]])
        acc_str = [zi]
        acc_len = [zi] + [rindex[t] for t in tw.get(cl[Z], [])]
        nbs = cs["nbs"]
        forbid = {rindex[cl[n["piece"]]] for n in nbs if cl[n["piece"]] in rindex}
        forbid = {x for x in forbid if x != zi}
        xs = np.array([(sigma * IDX[n["d"]]) % 4 for n in nbs])
        rec = dict(piece=Z, cell=list(cell), m=len(nbs), scan=pr.piece(Z).scan_id, nb_scans=[n["scan"] for n in nbs],
                   nb_kinds=[scan_kind(pr, n["scan"]) for n in nbs], nb=[dict(piece=n["piece"], d=n["d"], side=n["side"]) for n in nbs])
        # --- a) peça -> candidatos para a célula certa
        C4 = np.stack([cost_vec(n["piece"], n["side"])["s4"].reshape(R, 4) for n in nbs])
        C5 = np.stack([cost_vec(n["piece"], n["side"])["s5"].reshape(R, 4) for n in nbs])
        for nm, C in (("e4", C4), ("e5", C5)):
            J, arg = B.joint(C, xs, R)
            pools = {"lote": [int(i) for i in lot_idx if int(i) not in forbid], "completo": [i for i in range(R) if i not in forbid]}
            for pn, mem in pools.items():
                mem_a = np.array(mem)
                rec[f"a_{nm}_{pn}_str"] = rank_among(J, acc_str, mem_a)
                rec[f"a_{nm}_{pn}_len"] = rank_among(J, acc_len, mem_a)
                rec[f"a_pool_{pn}"] = len(mem)
            w = np.where(np.isin(np.arange(R), pools["lote"]) & (np.arange(R) != zi), J, np.inf)
            wi = int(np.argmin(w))
            rec[f"a_{nm}_winner"] = reps[rkeys[wi]] if np.isfinite(w[wi]) else None
            rec[f"a_{nm}_winner_rot"] = int(arg[wi]) if np.isfinite(w[wi]) else None
            rec[f"a_{nm}_J_true"] = float(J[zi]) if np.isfinite(J[zi]) else None
            rec[f"a_{nm}_rot_true"] = int(arg[zi]) if np.isfinite(J[zi]) else None
        # --- b) peça -> buracos reais do tabuleiro (a própria peça tirada)
        for nm, key in (("e4", "s4"), ("e5", "s5")):
            allJ, trueJ = {}, None
            for hc in empty + [cell]:
                nb_h = neighbours(pr, sh, hc, Z, dcache)
                if not nb_h:
                    continue
                Ch = np.stack([cost_vec(n["piece"], n["side"])[key].reshape(R, 4)[zi] for n in nb_h])
                xh = np.array([(sigma * IDX[n["d"]]) % 4 for n in nb_h])
                allJ[hc] = (joint_one(Ch, xh), len(nb_h))
            trueJ = allJ.get(cell)
            others = {h: v for h, v in allJ.items() if h != cell}
            for tag, sel in (("todos", lambda v: True), ("m2", lambda v: v[1] >= 2)):
                if trueJ is None or not np.isfinite(trueJ[0]) or (tag == "m2" and trueJ[1] < 2):
                    rec[f"b_{nm}_{tag}"] = None
                else:
                    rec[f"b_{nm}_{tag}"] = 1 + sum(1 for h, v in others.items() if sel(v) and v[0] < trueJ[0])
                rec[f"b_n_buracos_{tag}"] = sum(1 for h, v in others.items() if sel(v)) + (1 if trueJ else 0)
        # --- lados verdadeiros (para o §14.4): rotação real de Z pela pose do log
        thz = pr.piece(Z).theta_deg
        dz = board_dirs(sh[Z], thz) if thz is not None else None
        if dz is None and rec.get("a_e5_rot_true") is not None:          # sem pose no log: a rotação que o custo escolheu (marcado)
            dz = {d: (sigma * IDX[d] + rec["a_e5_rot_true"]) % 4 for d in DIRS}
            rec["rot_from_cost"] = True
        rec["true_sides"] = []
        if dz:
            rz = {(dz[n["d"]] - sigma * IDX[n["d"]]) % 4 for n in nbs}
            rec["rot_consistent"] = len(rz) == 1
            for n in nbs:
                cv = cost_vec(n["piece"], n["side"])
                j = 4 * zi + dz[n["d"]]
                rec["true_sides"].append(dict(piece=n["piece"], kind=scan_kind(pr, n["scan"]), rms=float(cv["rms"][j]), dl=float(cv["dl"][j]),
                                              de=(float(cv["de"][j]) if np.isfinite(cv["de"][j]) else None), valid=int(cv["valid"][j]),
                                              passed=bool(cv["passed"][j])))
        out_cases.append(rec)
        print(f"  {Z} {cell} m={len(nbs)}: a) lote E5 {rec['a_e5_lote_str']} E4 {rec['a_e4_lote_str']} | completo E5 {rec['a_e5_completo_str']} | b) E5 {rec['b_e5_todos']}/{rec['b_n_buracos_todos']} ({time.time() - t0:.0f}s)")
    P["save_cache"]()

    # ---- agregação (n pequeno: Wilson, sem veredicto)
    def agg(rows, key):
        v = [r[key] for r in rows]
        n = len(v)
        k1 = sum(1 for x in v if x == 1)
        k3 = sum(1 for x in v if x is not None and x <= 3)
        lo, hi = fe.wilson(k1, n) if n else (float("nan"), float("nan"))
        fin = sorted(x for x in v if x is not None)
        return dict(n=n, top1=k1, top3=k3, wilson1=[lo, hi], none=sum(1 for x in v if x is None), median_rank=(float(np.median(fin)) if fin else None))

    groups = {"todos": out_cases, "m1": [r for r in out_cases if r["m"] == 1], "m2": [r for r in out_cases if r["m"] == 2],
              "m3": [r for r in out_cases if r["m"] == 3], "m4": [r for r in out_cases if r["m"] == 4], "m>=2": [r for r in out_cases if r["m"] >= 2]}
    keys = ["a_e5_lote_str", "a_e5_lote_len", "a_e4_lote_len", "a_e5_completo_str", "a_e4_completo_len", "b_e5_todos", "b_e5_m2", "b_e4_todos"]
    agg_out = {g: {k: agg(rows, k) for k in keys} for g, rows in groups.items() if rows}
    for g, d in agg_out.items():
        a, b = d["a_e5_lote_str"], d["b_e5_todos"]
        print(f"{g:<6} n={a['n']:<2} a) E5 lote top-1 {a['top1']}/{a['n']} (Wilson {100 * a['wilson1'][0]:.0f}-{100 * a['wilson1'][1]:.0f} %), top-3 {a['top3']} | b) E5 tabuleiro top-1 {b['top1']}/{b['n']}, mediana do rank {b['median_rank']}")
    res = dict(shrink_mm=fe.SHRINK_MM, n_cases=len(cases), by_m={str(k): v for k, v in byn.items()}, verdict_possible=len(cases) >= MIN_FOR_VERDICT,
               sigma=sigma, orientation_count={str(k): v for k, v in ocount.items()}, agg=agg_out, cases=out_cases, target=TARGET,
               n_holes_total=len(empty))
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("escrito", OUT, f"({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
