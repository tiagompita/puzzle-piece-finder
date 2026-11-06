"""E-fit, passo 5: buracos virtuais (2-4 vizinhas do GT) contra E4 / E5 conjuntos. Só leitura.

Critérios fixados ANTES de correr em ``docs/diagnostico/fit/RESULTADOS.md`` §11; este ficheiro só os implementa.
Custo conjunto = média dos custos de lado das vizinhas, J(Z) = min sobre as 4 rotações da solta; ordem por peça.
Saída: ``docs/diagnostico/fit/buraco{,_encolhido}.json``. Correr da raiz: ``python tools/diagnostico/fit/buraco.py``
(``FIT_SHRINK=0.48`` para a condição com erosão).
"""

import collections
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import buracos  # noqa: E402
import pool  # noqa: E402
import fit_eval as fe  # noqa: E402
from common import REPO  # noqa: E402

SEED = 20261106
NS = (32, 64, 100)
DRAWS = 200
TAUS = pool.TAUS
TAU_OP = pool.TAU_OP
PI = (0.01, 0.10)
BOOT = 1000
OUT = os.path.join(REPO, "docs", "diagnostico", "fit", f"buraco{fe.SUFFIX}.json")
HIT_FRAC = 0.5                  # um buraco conta como «acerto» nos exemplos se o top-1 sai em >= 50 % dos sorteios


# ---------------------------------------------------------------- custo conjunto
def joint(C, xs, R):
    """C (m, R, 4) custos por lado; xs (m,) lado de X que olha para a vizinha k. -> J (R,), rotação que o dá (R,)."""
    m = C.shape[0]
    best = np.full(R, np.inf)
    arg = np.zeros(R, int)
    ar_m, ar_r = np.arange(m)[:, None], np.arange(R)[None, :]
    for r in range(4):
        cols = ((xs + r) % 4)[:, None]
        J = C[ar_m, ar_r, cols].mean(0)
        upd = J < best
        best = np.where(upd, J, best)
        arg = np.where(upd, r, arg)
    return best, arg


def rank_of(sm, acc):
    best = sm[:, acc].min(1)
    return np.where(np.isfinite(best), (sm < best[:, None]).sum(1) + 1, 10 ** 9)


def rank_avg(x):
    x = np.asarray(x, float)
    order = np.argsort(x, kind="stable")
    r = np.empty(len(x))
    r[order] = np.arange(len(x))
    u, inv, cnt = np.unique(x, return_inverse=True, return_counts=True)
    s = np.bincount(inv, weights=r)
    return (s / cnt)[inv]


def spearman(a, b):
    ra, rb = rank_avg(a), rank_avg(b)
    if ra.std() == 0 or rb.std() == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


# ---------------------------------------------------------------- buracos
def hole_table(P, holes):
    Q, R = P["Q"], P["R"]
    H = []
    for rb, h in sorted(holes.items()):
        idx = h["queries"]
        xs = np.array([Q[i]["xs"] for i in idx])
        H.append(dict(
            rb=rb, m=h["n"], zone=h["zone"], prov=h["prov"], idx=idx, xs=xs,
            C4=np.stack([Q[i]["s4"].reshape(R, 4) for i in idx]), C5=np.stack([Q[i]["s5"].reshape(R, 4) for i in idx]),
            nb=sorted({Q[i]["own"] for i in idx}), acc_len=np.array(sorted(set(Q[idx[0]]["ex"].tolist()) | {rb})), acc_str=np.array([rb]),
            twins=[x for x in Q[idx[0]]["ex"].tolist() if x != rb], kinds=[Q[i]["kind_a"] for i in idx],
        ))
    return H


def true_cost_pools(H):
    """custos do lado do verdadeiro (E4 e E5) por tipo da vizinha, de TODOS os lados de TODOS os buracos (inclui inf)."""
    out = {"e4": collections.defaultdict(list), "e5": collections.defaultdict(list)}
    for h in H:
        for k in range(h["m"]):
            out["e4"][h["kinds"][k]].append(h["C4"][k, h["rb"], h["xs"][k]])
            out["e5"][h["kinds"][k]].append(h["C5"][k, h["rb"], h["xs"][k]])
    return {s: {k: np.array(v) for k, v in d.items()} for s, d in out.items()}


def eval_hole(P, h, N, rng, tc, full=False):
    R, ri = P["R"], P["ri"]
    D = 1 if full else DRAWS
    forbid = set(h["nb"]) | {h["rb"]}
    if full:
        M = np.ones((1, R), bool)
        M[:, list(forbid - {h["rb"]})] = False
    else:
        M = pool.draw_members(rng, R, forbid, [h["rb"]], N, D)
    out = {}
    Js = {}
    for nm, C in (("e4", h["C4"]), ("e5", h["C5"])):
        J, arg = joint(C, h["xs"], R)
        Js[nm] = (J, arg)
        sm = np.where(M, J[None], np.inf)
        for suf, acc in (("len", h["acc_len"]), ("str", h["acc_str"])):
            rk = rank_of(sm, acc)
            out[f"{nm}_{suf}1"] = float((rk <= 1).mean())
            out[f"{nm}_{suf}3"] = float((rk <= 3).mean())
        # lado isolado (média das vizinhas) e oráculo (alguma vizinha sozinha põe Z* em top-1), peça a peça
        one, orc = [], np.zeros(D, bool)
        for k in range(h["m"]):
            Jk, _ = joint(C[k:k + 1], h["xs"][k:k + 1], R)
            rk = rank_of(np.where(M, Jk[None], np.inf), h["acc_len"])
            one.append(float((rk <= 1).mean()))
            orc |= rk <= 1
        out[f"{nm}_single1"] = float(np.mean(one))
        out[f"{nm}_oracle1"] = float(orc.mean())
        # independente: o custo do verdadeiro em cada lado vem de outro buraco (mesmo tipo de lado); concorrentes iguais
        comp = np.where(M, J[None], np.inf)
        comp[:, h["rb"]] = np.inf
        nul = np.zeros(D)
        draws = np.stack([rng.choice(tc[nm][h["kinds"][k]], size=D) for k in range(h["m"])])      # (m, D)
        Jn = draws.mean(0)
        out[f"{nm}_null1"] = float(np.mean([(np.isfinite(Jn[d]) and not (comp[d] < Jn[d]).any()) for d in range(D)]))
    if full:
        # diagnóstico por buraco no pool completo (exemplos): posição e vencedora
        for nm in ("e4", "e5"):
            J, arg = Js[nm]
            sm = np.where(M, J[None], np.inf)
            out[f"{nm}_rank_full_str"] = int(rank_of(sm, h["acc_str"])[0])
            w = int(np.argmin(sm[0])) if np.isfinite(sm[0]).any() else None
            out[f"{nm}_winner"] = w
            out[f"{nm}_winner_rot"] = int(arg[w]) if w is not None else None
    return out, M, Js


def present_absent(P, h, N, rng):
    """E5 conjunto: margem d2/d1 com a peça presente e com ela ausente; devolve por τ (cobertura, certas) e (falsas)."""
    R = P["R"]
    J, _ = joint(h["C5"], h["xs"], R)
    forbid = set(h["nb"]) | {h["rb"]}
    M = pool.draw_members(rng, R, forbid, [h["rb"]], N, DRAWS)
    sm = np.where(M, J[None], np.inf)
    d1, d2, bi = pool.margin_top(sm)
    mar = np.where(np.isfinite(d2) & (d1 > 1e-9), d2 / np.maximum(d1, 1e-9), np.nan)
    ok1 = np.isin(bi, h["acc_len"]) & np.isfinite(d1)
    pres = {t: (float((np.isfinite(mar) & (mar >= t)).mean()), float((np.isfinite(mar) & (mar >= t) & ok1).mean())) for t in TAUS}
    forbid_a = forbid | set(h["twins"])
    Mb = pool.draw_members(rng, R, forbid_a, [], N, DRAWS)
    smb = np.where(Mb, J[None], np.inf)
    b1, b2, _ = pool.margin_top(smb)
    marb = np.where(np.isfinite(b2) & (b1 > 1e-9), b2 / np.maximum(b1, 1e-9), np.nan)
    ab = {t: float((np.isfinite(marb) & (marb >= t)).mean()) for t in TAUS}
    return pres, ab


# ---------------------------------------------------------------- correlação dos erros
def correlation(P, H):
    Q = P["Q"]
    per_hole = []                      # por buraco: (u (percentis), rms verdadeiro finito ou nan)
    for h in H:
        u, rms = [], []
        for k, i in enumerate(h["idx"]):
            s4 = Q[i]["s4"]
            fin = s4[np.isfinite(s4)]
            t = s4[4 * h["rb"] + h["xs"][k]]
            if not np.isfinite(t):
                u.append(1.0)
                rms.append(np.nan)
            else:
                u.append(float(((fin < t).sum() + 0.5 * (fin == t).sum()) / len(fin)))
                rms.append(float(t))
        per_hole.append((np.array(u), np.array(rms)))

    def pairs(sel, which):
        a, b = [], []
        for j in sel:
            v = per_hole[j][which]
            for k in range(len(v)):
                for l in range(len(v)):
                    if k != l:
                        a.append(v[k])
                        b.append(v[l])
        return np.array(a), np.array(b)

    def stat(sel):
        a, b = pairs(sel, 0)
        r = spearman(a, b)
        a2, b2 = pairs(sel, 1)
        m = np.isfinite(a2) & np.isfinite(b2)
        pe = float(np.corrcoef(a2[m], b2[m])[0, 1]) if m.sum() > 2 else float("nan")
        return r, pe, int(len(a) // 2), int(m.sum() // 2)

    allsel = list(range(len(H)))
    rho, pear, npairs, npairs_rms = stat(allsel)
    rng = np.random.default_rng(SEED + 5)
    boots = []
    boots_p = []
    for _ in range(BOOT):
        sel = rng.integers(0, len(H), len(H))
        r, p, _, _ = stat(list(sel))
        boots.append(r)
        boots_p.append(p)
    # controlo: o 2.º membro vem de OUTRO buraco
    a, _ = pairs(allsel, 0)
    ctrl = []
    for _ in range(200):
        perm = rng.permutation(len(a))
        ctrl.append(spearman(a, a[perm]))
    a2, b2 = pairs(allsel, 1)
    m = np.isfinite(a2) & np.isfinite(b2)
    ctrl_p = [float(np.corrcoef(a2[m], b2[m][rng.permutation(int(m.sum()))])[0, 1]) for _ in range(200)]
    byn = {}
    for nn in (2, 3, 4):
        sel = [j for j, h in enumerate(H) if h["m"] == nn]
        if len(sel) > 5:
            r, p, npn, _ = stat(sel)
            byn[str(nn)] = dict(spearman=r, pearson_rms=p, n_pairs=npn)
    return dict(spearman=rho, spearman_ci=[float(np.nanpercentile(boots, 2.5)), float(np.nanpercentile(boots, 97.5))],
                pearson_rms=pear, pearson_ci=[float(np.nanpercentile(boots_p, 2.5)), float(np.nanpercentile(boots_p, 97.5))],
                n_pairs=npairs, n_pairs_rms=npairs_rms, control_spearman=float(np.nanmean(ctrl)), control_spearman_sd=float(np.nanstd(ctrl)),
                control_pearson=float(np.mean(ctrl_p)), by_n=byn)


# ---------------------------------------------------------------- agregação
def wil(mean, n):
    lo, hi = fe.wilson(int(round(mean * n)), n)
    return dict(p=mean, lo=lo, hi=hi, n=n)


def aggregate(rows, keys):
    out = {}
    n = len(rows)
    for k in keys:
        v = [r[k] for r in rows if r.get(k) is not None]
        if v:
            out[k] = wil(float(np.mean(v)), len(v))
    out["n"] = n
    return out


def main():
    t0 = time.time()
    P = pool.prepare()
    holes, drop = buracos.build(P)
    H = hole_table(P, holes)
    tc = true_cost_pools(H)
    n_nan = sum(int(np.isnan(h["C5"]).sum()) for h in H)
    print(f"{len(H)} buracos ({time.time() - t0:.0f}s); NaN em custos E5: {n_nan}")
    KEYS = ["e4_len1", "e4_len3", "e4_str1", "e5_len1", "e5_str1", "e5_len3", "e5_str3", "e4_single1", "e5_single1",
            "e4_oracle1", "e5_oracle1", "e4_null1", "e5_null1"]
    res = dict(shrink_mm=fe.SHRINK_MM, n_holes=len(H), by_n_count={str(k): v for k, v in collections.Counter(h["m"] for h in H).items()},
               A={}, B={}, holes=[])
    per = {}
    for N in list(NS) + ["full"]:
        rng = np.random.default_rng(SEED + (0 if N == "full" else N))
        rows = []
        for h in H:
            r, _, _ = eval_hole(P, h, N if N != "full" else 0, rng, tc, full=(N == "full"))
            r.update(m=h["m"], zone=h["zone"], prov=("bd" if any(p in ("b", "d") for p in h["prov"]) else "a"), rb=h["rb"])
            rows.append(r)
        per[str(N)] = rows
        res["A"][str(N)] = dict(all=aggregate(rows, KEYS), by_m={str(m): aggregate([r for r in rows if r["m"] == m], KEYS) for m in (2, 3, 4)},
                                by_zone={z: aggregate([r for r in rows if r["zone"] == z], KEYS) for z in sorted({r["zone"] for r in rows})},
                                by_prov={p: aggregate([r for r in rows if r["prov"] == p], KEYS) for p in ("a", "bd")},
                                by_m_zone={f"{m}|{z}": aggregate([r for r in rows if r["m"] == m and r["zone"] == z], KEYS)
                                           for m in (2, 3, 4) for z in sorted({r["zone"] for r in rows}) if any(r["m"] == m and r["zone"] == z for r in rows)})
        a = res["A"][str(N)]["all"]
        print(f"N={N}: E4 len1 {100*a['e4_len1']['p']:.1f} str1 {100*a['e4_str1']['p']:.1f} t3 {100*a['e4_len3']['p']:.1f} | "
              f"E5 str1 {100*a['e5_str1']['p']:.1f} len1 {100*a['e5_len1']['p']:.1f} t3 {100*a['e5_str3']['p']:.1f} | "
              f"single E5 {100*a['e5_single1']['p']:.1f} oracle {100*a['e5_oracle1']['p']:.1f} null {100*a['e5_null1']['p']:.1f} ({time.time() - t0:.0f}s)")
    # tabela por buraco (exemplos): pool completo e taxa de acerto em N=100
    full, n100 = per["full"], {r["rb"]: r for r in per["100"]}
    for r in full:
        r["e5_hit100"] = n100[r["rb"]]["e5_str1"]
        res["holes"].append({k: r[k] for k in ("rb", "m", "zone", "prov", "e4_rank_full_str", "e5_rank_full_str", "e4_winner", "e5_winner",
                                              "e4_winner_rot", "e5_winner_rot", "e5_hit100")})
    # ausente
    for N in NS:
        rng = np.random.default_rng(SEED + 7 + N)
        acc = {t: dict(cov=[], ok=[], fp=[], m=[]) for t in TAUS}
        for h in H:
            pres, ab = present_absent(P, h, N, rng)
            for t in TAUS:
                acc[t]["cov"].append(pres[t][0])
                acc[t]["ok"].append(pres[t][1])
                acc[t]["fp"].append(ab[t])
                acc[t]["m"].append(h["m"])
        curve = []
        for t in TAUS:
            row = dict(tau=t)
            for grp, sel in (("all", slice(None)), ("m2", None), ("m3", None), ("m4", None)):
                if grp == "all":
                    ix = np.arange(len(H))
                else:
                    ix = np.nonzero(np.array(acc[t]["m"]) == int(grp[1]))[0]
                cov, ok, fp = (float(np.mean(np.array(acc[t][k])[ix])) for k in ("cov", "ok", "fp"))
                d = dict(cov=cov, ok=ok, fp=fp, prec_present=(ok / cov if cov > 0 else None))
                for pi in PI:
                    den = pi * cov + (1 - pi) * fp
                    d[f"prec_pi{int(pi * 100)}"] = (pi * ok / den) if den > 0 else None
                row[grp] = d
            curve.append(row)
        res["B"][str(N)] = curve
        r15 = next(r for r in curve if r["tau"] == TAU_OP)["all"]
        print(f"B N={N} tau=1.5: cov {r15['cov']:.3f} prec_pres {r15['prec_present']} fp/buraco {r15['fp']:.4f} prec π=1% {r15['prec_pi1']} π=10% {r15['prec_pi10']}")
    res["correlation"] = correlation(P, H)
    print("correlação:", {k: v for k, v in res["correlation"].items() if k != "by_n"}, res["correlation"]["by_n"])
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("escrito", OUT, f"({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
