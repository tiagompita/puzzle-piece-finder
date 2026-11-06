"""E-fit, passo 4: o mesmo E4/E5 com pool pequeno (lote de 32-200 peças), vizinho ausente e direção inversa.

Critérios fixados ANTES de correr em ``docs/diagnostico/fit/RESULTADOS.md`` §8; este ficheiro só os implementa.
Só leitura (nem ``src/`` nem ``projects/alpes`` são escritos). Reutiliza as peças de ``fit_eval.py``.
Correr da raiz: ``python tools/diagnostico/fit/pool.py`` (``FIT_SHRINK=0.48`` para a condição com erosão).
Saída: ``docs/diagnostico/fit/pool{,_encolhido}.json``.
"""

import json
import math
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fit_eval as fe  # noqa: E402
from common import REPO  # noqa: E402

from src.shape import corner_dist, f_adjacent, _neg_inv  # noqa: E402

SEED = 20261106
NS = (32, 64, 100, 200)
DRAWS = 200
TAUS = (1.0, 1.1, 1.25, 1.5, 2.0, 3.0, 5.0)
TAU_OP = 1.5
PI = (0.01, 0.10, 0.50)
M_FRONT, K_SLOTS = 50, 8
NS_INV = (32, 100)
OUT = os.path.join(REPO, "docs", "diagnostico", "fit", f"pool{fe.SUFFIX}.json")


def prepare():
    """Por consulta: custos E4/E5 sobre TODOS os lados candidatos (inf = não passa), lados aceites, dono (índice de rep)."""
    pr, t95, chord, sh, cl, members, reps = fe.build()
    g = json.load(open(fe.GT, encoding="utf-8"))
    queries = [q for q in g["queries"] if {q["kind_a"], q["kind_b"]} == {"T", "B"}]
    tw = fe.twin_map(pr, sh, reps, t95)
    SIDES = {}

    def sides_of(pid):
        if pid not in SIDES:
            base = list(sh[pid].sides)
            if fe.SHRINK_MM > 0:
                alt = fe.shrink_sides(sh[pid], fe.SHRINK_MM)
                if alt is not None:
                    base = alt
            SIDES[pid] = base
        return SIDES[pid]

    rkeys = sorted(reps)
    rindex = {r: i for i, r in enumerate(rkeys)}
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
    kind, chordv, PN, fadj = np.array(kind), np.array(chordv), np.array(prof), np.array(fadj)
    owner, sidx = np.array(owner), np.array(sidx)
    ri = np.array([rindex[o] for o in owner])
    index_of = {(o, i): n for n, (o, i) in enumerate(zip(owner, sidx))}

    z = np.load(fe.CACHE, allow_pickle=True)
    cache = {k: z[k] for k in z.files}
    todo = [p for p in {reps[r] for r in rkeys} | {q["a"] for q in queries} if p not in cache]
    for p in sorted(todo):
        cache[p] = fe.piece_strips(pr, p)
    S_cand = np.stack([cache[reps[o]][i] for o, i in zip(owner, sidx)])

    Q = []
    for q in queries:
        a = q["a"]
        sda = sides_of(a)
        sa = sda[q["side_a"]]
        fa_a = f_adjacent([x.kind for x in sda])[q["side_a"]]
        ca = cl[a]
        rms = np.sqrt(np.mean(np.sum((sa.profile[None] - PN) ** 2, -1), -1)) * (sa.chord_mm + chordv) / 2.0
        comp = ((kind == "T") & (sa.kind == "B")) | ((kind == "B") & (sa.kind == "T"))
        own = owner == ca
        dl = np.abs(sa.chord_mm - chordv)
        tol = np.where(fa_a | fadj, chord["f_adj_mm"], chord["normal_mm"])
        passed = comp & ~own & (dl <= tol)
        Sq = cache[a][q["side_a"]]
        diff = np.linalg.norm(Sq[None] - S_cand[:, ::-1], axis=-1)
        valid = np.isfinite(diff).sum(1)
        de = np.where(valid >= fe.MIN_VALID, np.nanmedian(np.where(np.isfinite(diff), diff, np.nan), axis=1), np.nan)
        e5 = rms / fe.RMS_SCALE + de / fe.DE_SCALE
        s4 = np.where(passed & np.isfinite(rms), rms, np.inf).astype(np.float32)
        s5 = np.where(passed & np.isfinite(e5), e5, np.inf).astype(np.float32)
        # aceites (como em fit_eval.accepted_for)
        b = q["b"]
        rb = cl[b]
        acc_s, acc_t, ex_reps = [], [], []
        k = 0
        if rb in reps:
            k = corner_dist(sh[b], sh[reps[rb]])[1] if b != reps[rb] else 0
            acc_s.append(index_of[(rb, (q["side_b"] + k) % 4)])
            ex_reps.append(rindex[rb])
            for rt in tw.get(rb, []):
                kt = corner_dist(sh[reps[rb]], sh[reps[rt]])[1]
                acc_t.append(index_of[(rt, (((q["side_b"] + k) % 4) + kt) % 4)])
                ex_reps.append(rindex[rt])
        xs = ((q["side_b"] + k) % 4) if rb in reps else None       # lado do alvo no referencial do representante (buracos, passo 5)
        Q.append(dict(a=a, xs=xs, prov=q["prov"], kind_a=q["kind_a"], side_a=q["side_a"], cluster_b=rb, own=rindex.get(ca, -1), rb=rindex.get(rb, -1) if rb in reps else -1,
                      s4=s4, s5=s5, acc_len=np.array(acc_s + acc_t, int), acc_str=np.array(acc_s, int),
                      ex=np.array(ex_reps, int), zone=q["zone"]))
    return dict(Q=Q, ri=ri, R=len(rkeys), N_all=len(kind), no_true=sum(1 for x in Q if x["rb"] < 0),
                rkeys=rkeys, reps=reps, sh=sh, pr=pr, cl=cl, tw=tw, sides_of=sides_of)


def draw_members(rng, R, forbid, must, n, D):
    """(D, R) bool: ``n`` peças aleatórias fora de ``forbid`` + as de ``must`` (que contam dentro do n)."""
    r = rng.random((D, R))
    r[:, list(forbid)] = 2.0
    m = np.zeros((D, R), bool)
    k = n - len(must)
    if k > 0:
        idx = np.argpartition(r, k - 1, axis=1)[:, :k]
        np.put_along_axis(m, idx, True, axis=1)
    for x in must:
        m[:, x] = True
    return m


def margin_top(sm):
    """d1, d2 e índice do melhor (por linha) para scores com inf."""
    part = np.partition(sm, 1, axis=1)[:, :2]
    best = np.argmin(sm, axis=1)
    return part[:, 0], part[:, 1], best


def wilson_mean(p, n):
    return fe.wilson(int(round(p * n)), n)


def part_a_b(P, N, seed):
    Q, ri, R = P["Q"], P["ri"], P["R"]
    rng = np.random.default_rng(seed)
    nQ = len(Q)
    top = dict(e4_1=[], e4_3=[], e5_1=[], e5_3=[], e4_1s=[], e4_3s=[], e5_1s=[], e5_3s=[], ch1=[], ch3=[], npass=[])
    pres = {t: dict(cov=[], ok=[]) for t in TAUS}
    absn = {t: [] for t in TAUS}
    absn_cons = []
    for q in Q:
        # ---- A: presente
        if q["rb"] < 0 or len(q["acc_len"]) == 0:                      # vizinha sem forma no pool: falha certa
            for k in top:
                top[k].append(0.0)
            for t in TAUS:
                pres[t]["cov"].append(0.0)
                pres[t]["ok"].append(0.0)
            pres_none = True
        else:
            pres_none = False
            m = draw_members(rng, R, {q["own"], q["rb"]}, [q["rb"]], N, DRAWS)
            M = m[:, ri]
            for nm, s in (("e4", q["s4"]), ("e5", q["s5"])):
                sm = np.where(M, s[None], np.inf)
                for suf, acc in (("", q["acc_len"]), ("s", q["acc_str"])):
                    best = sm[:, acc].min(1) if len(acc) else np.full(DRAWS, np.inf)
                    rank = np.where(np.isfinite(best), (sm < best[:, None]).sum(1) + 1, 10 ** 9)
                    top[f"{nm}_1{suf}"].append(float((rank <= 1).mean()))
                    top[f"{nm}_3{suf}"].append(float((rank <= 3).mean()))
                if nm == "e5":
                    d1, d2, bi = margin_top(sm)
                    ok1 = np.isin(bi, q["acc_len"]) & np.isfinite(d1)
                    mar = np.where(np.isfinite(d2) & (d1 > 1e-9), d2 / np.maximum(d1, 1e-9), np.nan)
                    for t in TAUS:
                        c = np.isfinite(mar) & (mar >= t)
                        pres[t]["cov"].append(float(c.mean()))
                        pres[t]["ok"].append(float((c & ok1).mean()))
            sm4 = np.where(M, q["s4"][None], np.inf)
            npass = np.isfinite(sm4).sum(1).astype(float)
            macc = np.isfinite(sm4[:, q["acc_len"]]).sum(1).astype(float) if len(q["acc_len"]) else np.zeros(DRAWS)
            n = np.maximum(npass, 1)
            top["ch1"].append(float(np.mean(np.clip(macc / n, 0, 1))))
            noacc = ((n - macc) * np.maximum(n - macc - 1, 0) * np.maximum(n - macc - 2, 0)) / np.maximum(n * np.maximum(n - 1, 1) * np.maximum(n - 2, 1), 1)
            top["ch3"].append(float(np.mean(np.where(n >= 3, 1 - noacc, 1.0))))
            top["npass"].append(float(npass.mean()))
        # ---- B: ausente (sem a verdadeira nem as gémeas)
        forbid = {q["own"]} | set(q["ex"].tolist())
        forbid = {x for x in forbid if x >= 0}
        mb = draw_members(rng, R, forbid, [], N, DRAWS)
        Mb = mb[:, ri]
        smb = np.where(Mb, q["s5"][None], np.inf)
        d1, d2, _ = margin_top(smb)
        marb = np.where(np.isfinite(d2) & (d1 > 1e-9), d2 / np.maximum(d1, 1e-9), np.nan)
        for t in TAUS:
            absn[t].append(float((np.isfinite(marb) & (marb >= t)).mean()))
        absn_cons.append(float(np.isfinite(smb).any(1).mean()))
    out = dict(N=N, n_queries=nQ, no_true_in_pool=P["no_true"])
    for k in ("e4_1", "e4_3", "e5_1", "e5_3", "e4_1s", "e4_3s", "e5_1s", "e5_3s"):
        p = float(np.mean(top[k]))
        out[k] = dict(p=p, lo=wilson_mean(p, nQ)[0], hi=wilson_mean(p, nQ)[1])
    n_present = len(top["ch1"])
    out["chance_top1"] = float(np.mean(top["ch1"]))
    out["chords_top3"] = float(np.mean(top["ch3"]))
    out["mean_n_pass"] = float(np.mean(top["npass"]))
    curve = []
    for t in TAUS:
        cov = float(np.mean(pres[t]["cov"]))
        ok = float(np.mean(pres[t]["ok"]))
        fp = float(np.mean(absn[t]))
        row = dict(tau=t, cov_present=cov, correct_present=ok, wrong_present=cov - ok, prec_present=(ok / cov if cov > 0 else None),
                   false_per_query_absent=fp, with_candidates_absent=float(np.mean(absn_cons)))
        for pi in PI:
            den = pi * cov + (1 - pi) * fp
            row[f"prec_pi{int(pi * 100)}"] = (pi * ok / den) if den > 0 else None
        curve.append(row)
    out["curve"] = curve
    return out


def part_c(P, N, seed, D=DRAWS):
    Q, ri, R = P["Q"], P["ri"], P["R"]
    rng = np.random.default_rng(seed)
    cand = [i for i, q in enumerate(Q) if q["rb"] >= 0 and len(q["acc_len"]) and q["own"] >= 0]
    rec, fp3, fp1, n_slot = 0, 0.0, 0.0, 0
    fp3_list, fp1_list, rec_list = [], [], []
    done = 0
    attempts = 0
    while done < D and attempts < D * 20:
        attempts += 1
        sel = rng.choice(cand, size=M_FRONT * 3, replace=False)
        chosen, own_used, rb_used = [], set(), set()
        for i in sel:
            q = Q[i]
            if q["own"] in own_used:
                continue
            chosen.append(i)
            own_used.add(q["own"])
            if len(chosen) == M_FRONT:
                break
        if len(chosen) < M_FRONT:
            continue
        slots, rest = chosen[:K_SLOTS], chosen[K_SLOTS:]
        must = []
        for i in slots:
            if Q[i]["rb"] in own_used or Q[i]["rb"] in must:
                break
            must.append(Q[i]["rb"])
        if len(must) < K_SLOTS:
            continue
        forbid = set(own_used) | {x for i in rest for x in Q[i]["ex"].tolist()}
        forbid |= {x for x in must if False}
        if any(x in forbid for x in must):                              # a vizinha de um lugar é também gémea/vizinha de outro lado da fronteira
            continue
        m = draw_members(rng, R, forbid, must, N, 1)[0]
        lot_sides = np.nonzero(m[ri])[0]
        owner_of = ri[lot_sides]
        fa3 = np.zeros(R)                                                # aparições falsas (top-3 sem filtro) por peça
        fa1 = np.zeros(R)
        got = 0
        for j, i in enumerate(chosen):
            q = Q[i]
            s = q["s5"][lot_sides]
            order = np.argsort(s, kind="stable")[:3]
            order = [o for o in order if np.isfinite(s[o])]
            accs = set(q["acc_len"].tolist())
            pieces3 = {int(owner_of[o]) for o in order if int(lot_sides[o]) not in accs}
            for pce in pieces3:
                fa3[pce] += 1
            if len(order) >= 1:
                two = np.partition(s, 1)[:2]
                mar = two[1] / two[0] if np.isfinite(two[1]) and two[0] > 1e-9 else np.nan
                if np.isfinite(mar) and mar >= TAU_OP and int(lot_sides[order[0]]) not in accs:
                    fa1[int(owner_of[order[0]])] += 1
            if j < K_SLOTS:
                got += int(any(int(lot_sides[o]) in accs for o in order))
        rec_list.append(got / K_SLOTS)
        fp3_list.append(float(fa3[m].mean()))
        fp1_list.append(float(fa1[m].mean()))
        done += 1
    return dict(N=N, frontier=M_FRONT, slots=K_SLOTS, draws=done, recall_top3_slot=float(np.mean(rec_list)),
                false_top3_per_piece=float(np.mean(fp3_list)), false_top1_tau_per_piece=float(np.mean(fp1_list)),
                false_top1_tau_p95=float(np.percentile(fp1_list, 95)))


def main():
    t0 = time.time()
    P = prepare()
    print(f"preparado: {len(P['Q'])} consultas, {P['R']} peças físicas, {P['N_all']} lados ({time.time() - t0:.0f}s); sem forma no pool: {P['no_true']}")
    res = dict(shrink_mm=fe.SHRINK_MM, A_B={}, C={})
    for N in NS:
        res["A_B"][str(N)] = part_a_b(P, N, SEED + N)
        a = res["A_B"][str(N)]
        print(f"N={N:<4} E4 t1 {100*a['e4_1']['p']:.1f} % t3 {100*a['e4_3']['p']:.1f} % | E5 t1 {100*a['e5_1']['p']:.1f} % t3 {100*a['e5_3']['p']:.1f} % "
              f"| acaso t1 {100*a['chance_top1']:.1f} % cordas t3 {100*a['chords_top3']:.1f} % (n_pass {a['mean_n_pass']:.0f}) ({time.time() - t0:.0f}s)")
    for N in NS_INV:
        res["C"][str(N)] = part_c(P, N, SEED + 1000 + N)
        print("C", res["C"][str(N)])
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("escrito", OUT)


if __name__ == "__main__":
    main()
