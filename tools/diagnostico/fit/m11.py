"""M11 — molde do buraco como ranking: porta de sanidade, afinação (S_T) e validação (S_V) ATRAVÉS de ``src.fit``.

Critérios fixados ANTES de correr em ``docs/diagnostico/fit/M11_CRITERIOS.md``; este ficheiro só os implementa. Só leitura
do projeto (a única escrita em ``projects/alpes`` é a de ``--escrever-perfil``, que grava os 3 parâmetros afinados em
``calibration.buraco`` do ``puzzle.json``; nada no log).

Passos (``python tools/diagnostico/fit/m11.py <passo>``):

* ``sanidade``  — a configuração «passo 5» (erosão 0 e 0,48, corte 1×, sem regra F, sem rejeição) calculada por ``src.fit``
  reproduz ``buraco.py`` (custos por lado iguais e os mesmos agregados com ``buraco.eval_hole``) contra a corrida de hoje
  guardada em ``$PPF_SCRATCH/buraco_base{,_encolhido}.json``.
* ``afinar``    — grelha erosão × corte × quantil em S_T (144 buracos), N = 32; escreve ``m11_afinacao.json``.
* ``validar``   — uma passagem em S_V (214) com a configuração escolhida + ablação; escreve ``m11_validacao.json``.
* ``real``      — os 15 casos reais e a direção inversa no tabuleiro real (``src.fit.hole_queries`` / ``pool_items``);
  escreve ``m11_real.json``.
* ``figs``      — 6 melhores, 6 piores, 6 «sem candidata fiável» de S_V (N = 100, configuração final).
"""

import collections
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import buraco as B  # noqa: E402
import buracos  # noqa: E402
import fit_eval as fe  # noqa: E402
import pool  # noqa: E402
from common import REPO  # noqa: E402

from src import fit as F  # noqa: E402
from src.shape import f_adjacent  # noqa: E402

DOC = os.path.join(REPO, "docs", "diagnostico", "fit")
PART = os.path.join(DOC, "m11_particao.json")
SCRATCH = os.environ.get("PPF_SCRATCH", DOC)
SEED = 20261106
NS = (32, 100)
DRAWS = 200
EROSIONS = (0.0, 0.12, 0.24, 0.36, 0.48, 0.60, 0.72)
CUTS = (1.0, 2.0, 3.0, None)
QS = (0.90, 0.95, 0.99)
PI = (0.01, 0.10)
TIE_PT = 0.5                    # pontos percentuais: empate na afinação → o valor mais conservador
COV_MIN = 0.30
STRICT = True


# ---------------------------------------------------------------- construção (reps + vizinhas) por erosão
class Built:
    """Pool de representantes (PoolArrays) e lados das vizinhas para uma erosão ``e``."""

    def __init__(self, P, e):
        self.P, self.e = P, e
        pr, sh, reps, rkeys = P["pr"], P["sh"], P["reps"], P["rkeys"]
        z = np.load(fe.CACHE, allow_pickle=True)
        self.strips = {k: z[k] for k in z.files}
        self.sides = {}
        items = []
        for r in rkeys:
            pid = reps[r]
            items.append(F.FitItem(id=r, shape=sh[pid], sides=self.sides_of(pid), strips=self.strips[pid]))
        self.pa = F.pool_arrays(items)
        self.R = len(rkeys)

    def sides_of(self, pid):
        if pid not in self.sides:
            sh = self.P["sh"][pid]
            alt = F.eroded_sides(sh, self.e) if self.e > 0 else None
            self.sides[pid] = alt if alt is not None else list(sh.sides)
        return self.sides[pid]

    def hole(self, rb, h):
        """HoleQuery virtual: as vizinhas do GT (lado que olha para X), direção pseudo = DIRS[xs] com σ = +1."""
        Q = self.P["Q"]
        sides = []
        for i in h["queries"]:
            q = Q[i]
            a, sa = q["a"], q["side_a"]
            sds = self.sides_of(a)
            fa = f_adjacent([s.kind for s in sds])[sa]
            sides.append(F.HoleSide(piece_id=a, direction=F.DIRS[q["xs"]], side=sds[sa], f_adj=bool(fa),
                                    strip=self.strips[a][sa], scan_id=self.P["pr"].piece(a).scan_id))
        return F.HoleQuery(cell=None, sides=sides, zone=h["zone"], f_required=())


def calib(e=0.0, cut=1.0, t_abs=None):
    return F.FitCalibration(erosion_mm=e, chord_cut=cut, t_abs=t_abs, margin_min=1.5, f_rule=False, calibrated=True)


def load_part():
    d = json.load(open(PART, encoding="utf-8"))
    return {r["rb"]: r["part"] for r in d["holes"]}, d


def conf_vec(m, d1, d2, cal):
    """Confiança vetorizada (regra de src.fit.confidence) sobre sorteios: 0 alta, 1 media, 2 sem."""
    out = np.full(d1.shape, 2, int)
    ok1 = np.isfinite(d1) & (cal.t_abs is None or True)
    if cal.t_abs is not None:
        ok1 &= d1 <= cal.t_abs
    ok2 = ok1 & np.isfinite(d2)
    mar = np.where(ok2, d2 / np.maximum(d1, F.MIN_D1), np.nan)
    hi = ok2 & (mar >= cal.margin_min)
    lo = ok2 & ~(mar >= cal.margin_min)
    if m >= 2:
        out[hi] = 0
        out[lo] = 1
    else:
        out[hi] = 1
    return out


def evaluate(built, holes, part_sel, cal, N, seed, *, e4=False):
    """Para os buracos de ``part_sel`` (lista de rb): top-1/top-3 (estrito e leniente), presente/ausente com confiança.

    Sorteios: ``default_rng(seed)``, buracos por rb crescente, ``pool.draw_members`` como no passo 5."""
    P, pa, R = built.P, built.pa, built.R
    rng = np.random.default_rng(seed)
    rows = []
    for rb in sorted(part_sel):
        h = holes[rb]
        hq = built.hole(rb, h)
        J, rot, per, xs = F.joint_costs(hq, pa, cal, 1)
        acc_str = np.array([rb])
        acc_len = np.array(sorted(set(P["Q"][h["queries"][0]]["ex"].tolist()) | {rb}))
        nb = sorted({P["Q"][i]["own"] for i in h["queries"]})
        forbid = set(nb) | {rb}
        if N == "full":
            M = np.ones((1, R), bool)
            M[:, list(forbid - {rb})] = False
        else:
            M = pool.draw_members(rng, R, forbid, [rb], N, DRAWS)
        sm = np.where(M, J[None], np.inf)
        rk_s = B.rank_of(sm, acc_str)
        rk_l = B.rank_of(sm, acc_len)
        d1, d2, bi = pool.margin_top(sm)
        cv = conf_vec(h["n"], d1, d2, cal)
        prop = cv < 2
        alta = cv == 0
        ok = (bi == rb) & np.isfinite(d1)
        row = dict(rb=rb, m=h["n"], zone=h["zone"], prov=("bd" if any(p in ("b", "d") for p in h["prov"]) else "a"),
                   s1=float((rk_s <= 1).mean()), s3=float((rk_s <= 3).mean()), l1=float((rk_l <= 1).mean()), l3=float((rk_l <= 3).mean()),
                   J_true=float(J[rb]), rot_true=int(rot[rb]), rank_full=(int(rk_s[0]) if N == "full" else None),
                   cov=float(prop.mean()), ok_prop=float((prop & ok).mean()), cov_alta=float(alta.mean()), ok_alta=float((alta & ok).mean()),
                   conf_true=int(cv[0]) if N == "full" else None, d1_full=float(d1[0]) if N == "full" else None,
                   margin_full=(float(d2[0] / max(d1[0], F.MIN_D1)) if N == "full" and np.isfinite(d2[0]) and np.isfinite(d1[0]) else None),
                   winner_full=(int(bi[0]) if N == "full" and np.isfinite(d1[0]) else None), winner_rot=(int(rot[int(bi[0])]) if N == "full" and np.isfinite(d1[0]) else None))
        if e4:
            # só forma (referência): rms com o filtro duro das cordas (como o E4 do passo 5), média/min como J
            C4 = []
            for k, c in enumerate(per):
                hard = c["dl"] > np.where(pa.fadj | bool(hq.sides[k].f_adj), cal.chord_f_adj_mm, cal.chord_normal_mm)
                C4.append(np.where(c["comp"] & ~hard & np.isfinite(c["rms"]), c["rms"], np.inf))
            J4, _ = B.joint(np.stack(C4), xs, R)
            sm4 = np.where(M, J4[None], np.inf)
            row["e4_l1"] = float((B.rank_of(sm4, acc_len) <= 1).mean())
        if N != "full":
            forbid_a = forbid | set(x for x in acc_len.tolist() if x != rb)
            Mb = pool.draw_members(rng, R, forbid_a, [], N, DRAWS)
            smb = np.where(Mb, J[None], np.inf)
            b1, b2, _ = pool.margin_top(smb)
            cb = conf_vec(h["n"], b1, b2, cal)
            row["fp"] = float((cb < 2).mean())
            row["fp_alta"] = float((cb == 0).mean())
        rows.append(row)
    return rows


def wil(k, n):
    lo, hi = F.wilson(int(round(k)), n)
    return [lo, hi]


def aggregate(rows, N):
    n = len(rows)
    out = dict(n=n)
    for k in ("s1", "s3", "l1", "l3", "e4_l1"):
        v = [r[k] for r in rows if k in r]
        if v:
            p = float(np.mean(v))
            out[k] = dict(p=p, lo=wil(p * len(v), len(v))[0], hi=wil(p * len(v), len(v))[1])
    if N != "full":
        for pre, cov_k, ok_k, fp_k in (("", "cov", "ok_prop", "fp"), ("alta_", "cov_alta", "ok_alta", "fp_alta")):
            cov = float(np.mean([r[cov_k] for r in rows]))
            ok = float(np.mean([r[ok_k] for r in rows]))
            fp = float(np.mean([r[fp_k] for r in rows]))
            d = dict(cov=cov, ok=ok, prec_present=(ok / cov if cov > 0 else None), fp=fp)
            for pi in PI:
                den = pi * cov + (1 - pi) * fp
                d[f"prec_pi{int(pi * 100)}"] = (pi * ok / den) if den > 0 else None
            out[pre + "absent"] = d
    return out


def slices(rows, N):
    out = {"by_m": {}, "by_zone": {}, "by_prov": {}, "by_m_zone": {}}
    for m in (2, 3, 4):
        sel = [r for r in rows if r["m"] == m]
        if sel:
            out["by_m"][str(m)] = aggregate(sel, N)
    for z in sorted({r["zone"] for r in rows}):
        out["by_zone"][z] = aggregate([r for r in rows if r["zone"] == z], N)
    for p in ("a", "bd"):
        sel = [r for r in rows if r["prov"] == p]
        if sel:
            out["by_prov"][p] = aggregate(sel, N)
    for m in (2, 3, 4):
        for z in sorted({r["zone"] for r in rows}):
            sel = [r for r in rows if r["m"] == m and r["zone"] == z]
            if sel:
                out["by_m_zone"][f"{m}|{z}"] = aggregate(sel, N)
    worst = sorted([(k, a["s1"]["p"], a["n"]) for d in (out["by_m"], out["by_zone"], out["by_prov"], out["by_m_zone"])
                    for k, a in d.items() if a["n"] >= 20], key=lambda t: t[1])[:3]
    out["worst3"] = worst
    return out


# ---------------------------------------------------------------- passos
def step_sanidade(P, holes):
    """Custos por lado de src.fit == pool.costs (e = 0) e agregados de buraco.eval_hole iguais à corrida de hoje."""
    out = {}
    for e, name in ((0.0, "buraco_base.json"), (0.48, "buraco_base_encolhido.json")):
        t0 = time.time()
        bt = Built(P, e)
        cal = calib(e, 1.0, None)
        H = []
        maxdiff = 0.0
        for rb, h in sorted(holes.items()):
            hq = bt.hole(rb, h)
            per = [F.side_costs(hs, bt.pa, cal)["cost"] for hs in hq.sides]
            for k, i in enumerate(h["queries"]):          # a própria vizinha nunca é candidata (pool.costs: ~own)
                per[k][P["Q"][i]["own"]] = np.inf
            C5 = np.stack(per)
            if e == 0.0:
                ref = np.stack([P["Q"][i]["s5"].reshape(bt.R, 4) for i in h["queries"]])
                fin = np.isfinite(C5) & np.isfinite(ref)
                assert np.array_equal(np.isfinite(C5), np.isfinite(ref)), f"padrão de infinitos diferente no buraco {rb}"
                maxdiff = max(maxdiff, float(np.max(np.abs(C5[fin] - ref[fin]))) if fin.any() else 0.0)
            idx = h["queries"]
            H.append(dict(rb=rb, m=h["n"], zone=h["zone"], prov=h["prov"], idx=idx, xs=np.array([P["Q"][i]["xs"] for i in idx]),
                          C4=C5, C5=C5, nb=sorted({P["Q"][i]["own"] for i in idx}),
                          acc_len=np.array(sorted(set(P["Q"][idx[0]]["ex"].tolist()) | {rb})), acc_str=np.array([rb]),
                          twins=[x for x in P["Q"][idx[0]]["ex"].tolist() if x != rb], kinds=[P["Q"][i]["kind_a"] for i in idx]))
        tc = B.true_cost_pools(H)
        res = {}
        for N in list(B.NS) + ["full"]:
            rng = np.random.default_rng(SEED + (0 if N == "full" else N))
            rows = []
            for h in H:
                r, _, _ = B.eval_hole(P, h, N if N != "full" else 0, rng, tc, full=(N == "full"))
                rows.append(r)
            res[str(N)] = dict(e5_str1=float(np.mean([r["e5_str1"] for r in rows])), e5_len1=float(np.mean([r["e5_len1"] for r in rows])),
                               e5_str3=float(np.mean([r["e5_str3"] for r in rows])))
        ref = json.load(open(os.path.join(SCRATCH, name), encoding="utf-8"))
        cmp = {}
        for N in list(B.NS) + ["full"]:
            a = ref["A"][str(N)]["all"]
            cmp[str(N)] = dict(fit=res[str(N)], base=dict(e5_str1=a["e5_str1"]["p"], e5_len1=a["e5_len1"]["p"], e5_str3=a["e5_str3"]["p"]),
                               diff_pt=100 * (res[str(N)]["e5_str1"] - a["e5_str1"]["p"]))
        out[str(e)] = dict(n_holes=len(H), max_abs_diff_side_cost=(maxdiff if e == 0.0 else None), compare=cmp, seconds=time.time() - t0)
        print(f"e={e}: {len(H)} buracos; |Δcusto| máx por lado {maxdiff:.2e}" + ("" if e == 0 else " (só agregados)"))
        for N, c in cmp.items():
            print(f"   N={N}: E5 estrito top-1 fit {100 * c['fit']['e5_str1']:.2f} % vs base {100 * c['base']['e5_str1']:.2f} % (Δ {c['diff_pt']:+.2f} pt); "
                  f"top-3 {100 * c['fit']['e5_str3']:.2f} vs {100 * c['base']['e5_str3']:.2f}")
    json.dump(out, open(os.path.join(DOC, "m11_sanidade.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ok = all(abs(c["diff_pt"]) < 1e-6 for e in out.values() for c in e["compare"].values())
    print("PORTA DE SANIDADE:", "reproduz" if ok else "NÃO reproduz")
    return ok


def step_afinar(P, holes, part):
    ST = [rb for rb, p in part.items() if p == "afinacao" and rb in holes]
    print(f"S_T: {len(ST)} buracos")
    out = dict(n_ST=len(ST), erosao={}, corte={}, rejeicao={})
    built = {}
    # 1. erosão (corte 1×, sem rejeição)
    best_e, best_p = None, -1
    for e in EROSIONS:
        built[e] = Built(P, e)
        rows = evaluate(built[e], holes, ST, calib(e, 1.0), 32, SEED + 32, e4=True)
        a = aggregate(rows, 32)
        out["erosao"][str(e)] = a
        p = a["s1"]["p"]
        print(f"  e={e:.2f}: E5 estrito top-1 {100 * p:.1f} % (E4 {100 * a['e4_l1']['p']:.1f} %), top-3 {100 * a['s3']['p']:.1f} %")
        if p > best_p + TIE_PT / 100:
            best_e, best_p = e, p
    out["e_escolhida"] = best_e
    print("erosão escolhida:", best_e)
    # 2. corte do filtro mole
    best_c, best_p = None, -1
    for cut in CUTS:
        rows = evaluate(built[best_e], holes, ST, calib(best_e, cut), 32, SEED + 32)
        a = aggregate(rows, 32)
        out["corte"][str(cut)] = a
        p = a["s1"]["p"]
        print(f"  cut={cut}: E5 estrito top-1 {100 * p:.1f} %, top-3 {100 * a['s3']['p']:.1f} %, certa ∞: {sum(1 for r in rows if not np.isfinite(r['J_true']))}")
        if p > best_p + TIE_PT / 100:
            best_c, best_p = cut, p
    out["cut_escolhido"] = best_c
    print("corte escolhido:", best_c)
    # 3. rejeição absoluta: quantis do J da certa em S_T
    rows0 = evaluate(built[best_e], holes, ST, calib(best_e, best_c), "full", SEED)
    jt = np.array([r["J_true"] for r in rows0 if np.isfinite(r["J_true"])])
    out["J_true_ST"] = dict(n=int(len(jt)), n_inf=int(len(rows0) - len(jt)), q=[float(np.quantile(jt, q)) for q in QS], med=float(np.median(jt)))
    best_q, best_prec, best_t = None, -1, None
    for q in QS:
        t = float(np.quantile(jt, q))
        rows = evaluate(built[best_e], holes, ST, calib(best_e, best_c, t), 32, SEED + 32)
        a = aggregate(rows, 32)
        out["rejeicao"][str(q)] = dict(t_abs=t, **a)
        ab = a["absent"]
        print(f"  q={q}: T_abs {t:.3f}: cobertura {100 * ab['cov']:.1f} %, falsas/buraco {ab['fp']:.3f}, precisão π=10 % {100 * (ab['prec_pi10'] or 0):.1f} %, π=1 % {100 * (ab['prec_pi1'] or 0):.1f} %")
        if ab["cov"] >= COV_MIN and (ab["prec_pi10"] or 0) > best_prec:
            best_q, best_prec, best_t = q, ab["prec_pi10"] or 0, t
    if best_q is None:
        best_q = max(QS, key=lambda q: out["rejeicao"][str(q)]["absent"]["prec_pi10"] or 0)
        best_t = out["rejeicao"][str(best_q)]["t_abs"]
        out["rejeicao_sem_cobertura"] = True
        print("nenhum q cumpre cobertura ≥ 30 %: escolhido o de maior precisão (reportado)")
    out["q_escolhido"], out["t_abs"] = best_q, best_t
    # sem rejeição, para comparação
    rows = evaluate(built[best_e], holes, ST, calib(best_e, best_c, None), 32, SEED + 32)
    out["rejeicao"]["sem"] = aggregate(rows, 32)
    out["final"] = dict(erosion_mm=best_e, chord_cut=best_c, t_abs=best_t, q=best_q)
    print("FINAL:", out["final"])
    json.dump(out, open(os.path.join(DOC, "m11_afinacao.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return out["final"]


def _t_abs_for(P, holes, part, e, cut, q):
    """Quantil q do J da certa em S_T para a configuração (e, cut) — recalibrado por configuração na ablação."""
    ST = [rb for rb, p in part.items() if p == "afinacao" and rb in holes]
    bt = Built(P, e)
    rows = evaluate(bt, holes, ST, calib(e, cut), "full", SEED)
    jt = np.array([r["J_true"] for r in rows if np.isfinite(r["J_true"])])
    return float(np.quantile(jt, q)), bt


def step_validar(P, holes, part, final):
    SV = [rb for rb, p in part.items() if p == "validacao" and rb in holes]
    print(f"S_V: {len(SV)} buracos")
    e, cut, t, q = final["erosion_mm"], final["chord_cut"], final["t_abs"], final["q"]
    configs = [("passo5", 0.0, 1.0, False), ("passo5_e048", 0.48, 1.0, False), ("+mole", 0.0, cut, False),
               ("+erosao", e, 1.0, False), ("+rejeicao", 0.0, 1.0, True), ("+mole+erosao", e, cut, False), ("final", e, cut, True)]
    out = dict(n_SV=len(SV), final=final, configs={})
    built = {}
    for name, ce, cc, rej in configs:
        if ce not in built:
            built[ce] = Built(P, ce)
        ta = None
        if rej:
            ta = t if (ce == e and cc == cut) else _t_abs_for(P, holes, part, ce, cc, q)[0]
        cal = calib(ce, cc, ta)
        res = dict(e=ce, cut=cc, t_abs=ta)
        for N in list(NS) + ["full"]:
            rows = evaluate(built[ce], holes, SV, cal, N, SEED + (0 if N == "full" else N), e4=True)
            res[str(N)] = dict(all=aggregate(rows, N), **slices(rows, N))
            if name == "final":
                res[str(N)]["rows"] = rows
        out["configs"][name] = res
        a32, a100 = res["32"]["all"], res["100"]["all"]
        line = f"{name:<13} e={ce:.2f} cut={cc} T_abs={ta}: E5 estrito top-1 N=32 {100 * a32['s1']['p']:.1f} % ({100 * a32['s1']['lo']:.1f}–{100 * a32['s1']['hi']:.1f}), N=100 {100 * a100['s1']['p']:.1f} % ({100 * a100['s1']['lo']:.1f}–{100 * a100['s1']['hi']:.1f}); top-3 {100 * a32['s3']['p']:.1f} / {100 * a100['s3']['p']:.1f}"
        ab = a32["absent"]
        line += f" | ausente N=32: cob {100 * ab['cov']:.0f} % falsas {ab['fp']:.3f} prec π10 {100 * (ab['prec_pi10'] or 0):.0f} % (só alta: cob {100 * a32['alta_absent']['cov']:.0f} % falsas {a32['alta_absent']['fp']:.3f} prec π10 {100 * (a32['alta_absent']['prec_pi10'] or 0):.0f} %)"
        print(line)
    json.dump(out, open(os.path.join(DOC, "m11_validacao.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1,
              default=lambda o: float(o) if isinstance(o, np.floating) else int(o))
    return out


# ---------------------------------------------------------------- tabuleiro real (15 casos + direção inversa)
def step_real(final):
    import real as RL
    from src.state import Project
    pr = Project.open(os.path.join(REPO, "projects", "alpes"))
    cal = F.FitCalibration(erosion_mm=final["erosion_mm"], chord_cut=final["chord_cut"], t_abs=final["t_abs"], margin_min=1.5, f_rule=True, calibrated=True)
    cache = F._Cache(pr, cal)
    dcache = {}
    sg = F.board_sigma(pr, cache, dcache)
    print("σ:", sg)
    assert "error" not in sg
    sh = {pid: cache.shape(pid) for pid in pr.pieces}
    dc2 = {}
    cases = RL.gt_cases(pr, sh, dc2)
    loose = [p.id for p in pr.loose_pieces()]
    print(f"{len(cases)} casos reais; {len(loose)} soltas")
    t0 = time.time()
    out = dict(final=final, n_cases=len(cases), n_loose=len(loose), cases=[], inverse=None)
    for cs in cases:
        Z, cell = cs["piece"], cs["cell"]
        holes = F.hole_queries(pr, cache=cache, dcache=dcache, exclude_piece=Z)
        items = F.pool_items(pr, pieces=loose + [Z], cache=cache)
        pa = F.pool_arrays(items)
        res = [F.rank_hole(h, pa, calib=cal, sigma=sg["sigma"]) for h in holes]
        by_cell = {tuple(r["cell"]): r for r in res if "error" not in r}
        r0 = by_cell.get(tuple(cell))
        rank = None
        if r0 is not None:
            ids = [x["id"] for x in r0["ranking"]]
            rank = ids.index(Z) + 1 if Z in ids else None
        # b) célula certa entre os buracos: J(Z) por buraco
        Jz = {c: next((x["J"] for x in r["ranking"] if x["id"] == Z), np.inf) for c, r in by_cell.items()}
        jt = Jz.get(tuple(cell), np.inf)
        rank_board = (1 + sum(1 for c, v in Jz.items() if c != tuple(cell) and v < jt)) if np.isfinite(jt) else None
        others = [(c, r["confidence"]) for c, r in by_cell.items() if c != tuple(cell) and r["candidates"] and r["candidates"][0]["id"] == Z]
        assigned = F.assign(res)
        ass_cells = [c for c, p in assigned.items() if p == Z]
        true_sides = r0["candidates"][0]["per_side"] if (r0 and rank == 1) else None
        rec = dict(piece=Z, cell=list(cell), m=(r0["m"] if r0 else 0), rank_lote=rank, conf=(r0["confidence"] if r0 else None),
                   margin=(r0["margin"] if r0 else None), d1=(r0["d1"] if r0 else None), J_true=(float(jt) if np.isfinite(jt) else None),
                   rank_board=rank_board, n_holes=len(by_cell), others_top1=len(others),
                   others_alta=sum(1 for _, c in others if c == "alta"), others_media=sum(1 for _, c in others if c == "media"),
                   assigned_cells=[list(c) for c in ass_cells], assigned_right=(ass_cells == [tuple(cell)]),
                   winner=(r0["candidates"][0]["id"] if r0 and r0["candidates"] else None),
                   nb_scans=[hs.scan_id for hs in next(h for h in holes if tuple(h.cell) == tuple(cell)).sides] if r0 else [],
                   scan=pr.piece(Z).scan_id,
                   dE_true=[s["dE"] for s in true_sides] if true_sides else None,
                   rms_true=[s["rms"] for s in true_sides] if true_sides else None)
        out["cases"].append(rec)
        print(f"  {Z} {cell} m={rec['m']}: rank lote {rank} ({rec['conf']}, margem {rec['margin'] and round(rec['margin'], 2)}) | tabuleiro {rank_board}/{len(by_cell)} | top-1 noutros {len(others)} (alta {rec['others_alta']}) | afetado a {rec['assigned_cells']} ({time.time() - t0:.0f}s)")
    cache.save()
    n = len(cases)
    k1 = sum(1 for r in out["cases"] if r["rank_lote"] == 1)
    k3 = sum(1 for r in out["cases"] if r["rank_lote"] is not None and r["rank_lote"] <= 3)
    kb = sum(1 for r in out["cases"] if r["rank_board"] == 1)
    m2 = [r for r in out["cases"] if r["m"] >= 2]
    out["agg"] = dict(n=n, top1=k1, top3=k3, wilson1=wil(k1, n), board_top1=kb, n_m2=len(m2), top1_m2=sum(1 for r in m2 if r["rank_lote"] == 1),
                      others_alta_per_piece=float(np.mean([r["others_alta"] for r in out["cases"]])),
                      others_media_per_piece=float(np.mean([r["others_media"] for r in out["cases"]])),
                      assigned_right=sum(1 for r in out["cases"] if r["assigned_right"]),
                      assigned_elsewhere=sum(1 for r in out["cases"] if r["assigned_cells"] and not r["assigned_right"]),
                      conf=dict(collections.Counter(r["conf"] for r in out["cases"])))
    print("casos reais:", out["agg"])
    # C') as 134 soltas contra os buracos reais, com e sem afetação
    allr = F.rank_all(pr, calib=cal, joint=False, cache=cache)
    assert "error" not in allr, allr
    per_piece_alta = collections.Counter()
    per_piece_media = collections.Counter()
    for r in allr["holes"]:
        if r["candidates"]:
            if r["confidence"] == "alta":
                per_piece_alta[r["candidates"][0]["id"]] += 1
            elif r["confidence"] == "media":
                per_piece_media[r["candidates"][0]["id"]] += 1
    joint = F.rank_all(pr, calib=cal, joint=True, cache=cache)
    conf_cnt = collections.Counter(r["confidence"] for r in allr["holes"])
    n_loose = allr["n_pool"]
    ass_alta = sum(1 for r in joint["holes"] if r["confidence"] == "alta" and r.get("assigned") == (r["candidates"][0]["id"] if r["candidates"] else None))
    out["inverse"] = dict(n_holes=allr["n_holes"], n_loose=n_loose, conf=dict(conf_cnt),
                          alta_per_piece=sum(per_piece_alta.values()) / n_loose, media_per_piece=sum(per_piece_media.values()) / n_loose,
                          pieces_with_alta=len(per_piece_alta), max_alta_one_piece=(max(per_piece_alta.values()) if per_piece_alta else 0),
                          alta_assigned=ass_alta, alta_assigned_per_piece=ass_alta / n_loose,
                          by_m={str(m): dict(collections.Counter(r["confidence"] for r in allr["holes"] if r["m"] == m)) for m in (1, 2, 3, 4)},
                          top_alta=[dict(cell=list(r["cell"]), m=r["m"], piece=r["candidates"][0]["id"], J=r["d1"], margin=r["margin"],
                                         lote=r["candidates"][0]["lote"], n=r["candidates"][0]["n_no_lote"], assigned=r.get("assigned"))
                                    for r in joint["holes"] if r["confidence"] == "alta"][:40])
    print("direção inversa:", {k: v for k, v in out["inverse"].items() if k != "top_alta"})
    json.dump(out, open(os.path.join(DOC, "m11_real.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1,
              default=lambda o: float(o) if isinstance(o, np.floating) else int(o))
    return out


# ---------------------------------------------------------------- figuras
def step_figs(P, holes, part, final):
    import cv2
    from figs import hstack_pad, rigid_for
    from figs_buraco import draw, same_for
    V = json.load(open(os.path.join(DOC, "m11_validacao.json"), encoding="utf-8"))
    rows100 = {r["rb"]: r for r in V["configs"]["final"]["100"]["rows"]}
    rowsF = {r["rb"]: r for r in V["configs"]["final"]["full"]["rows"]}
    sh, pr, reps, rkeys, Q = P["sh"], P["pr"], P["reps"], P["rkeys"], P["Q"]

    def panel(rb, z, rot, col, title, lines):
        X = reps[rkeys[rb]]
        nbs = [(Q[i]["a"], Q[i]["side_a"], Q[i]["xs"]) for i in holes[rb]["queries"]]
        placed = []
        for pid, sa, xs in nbs:
            Rn, tn = rigid_for((sh[X], xs), (sh[pid], sa))
            placed.append((pid, Rn, tn, (0, 215, 255)))
        pid0, sa0, xs0 = nbs[0]
        Rz, tz = same_for((sh[X], xs0), (sh[reps[rkeys[z]]], (xs0 + rot) % 4))
        placed.append((reps[rkeys[z]], Rz, tz, col))
        return draw(pr, sh, placed, title, lines)

    hits = sorted([r for r in rows100.values() if r["s1"] >= 0.5], key=lambda r: r["rb"])
    step = max(1, len(hits) // 6)
    sel_h = [hits[i * step] for i in range(min(6, len(hits)))]
    fails = sorted(rowsF.values(), key=lambda r: (-(r["rank_full"] or 10 ** 9), r["rb"]))[:6]
    sem = sorted([r for r in rowsF.values() if r["conf_true"] == 2], key=lambda r: ((r["margin_full"] or 0.0), r["rb"]))[:6]
    info = []

    def mk(r, kind):
        rb = r["rb"]
        rf = rowsF[rb]
        lines = [f"{r['zone']} | {r['m']} vizinhas | {'bd' if r['prov'] == 'bd' else 'layout'}",
                 f"E5 estrito top-1 em {100 * rows100[rb]['s1']:.0f} % dos sorteios (N=100); rank no pool completo {rf['rank_full']}",
                 f"J certa {rf['J_true']:.2f} | d1 {rf['d1_full'] and round(rf['d1_full'], 2)} margem {rf['margin_full'] and round(rf['margin_full'], 2)} | conf {['alta', 'media', 'sem'][rf['conf_true']]}"]
        left = panel(rb, rb, rf["rot_true"] if np.isfinite(rf["J_true"]) else 0, (255, 200, 0), f"{kind}: buraco de {reps[rkeys[rb]]}", lines)
        info.append(dict(kind=kind, hole=reps[rkeys[rb]], zone=r["zone"], m=r["m"], hit100=rows100[rb]["s1"], rank_full=rf["rank_full"], conf=rf["conf_true"], J_true=rf["J_true"], d1=rf["d1_full"], margin=rf["margin_full"]))
        w = rf["winner_full"]
        if kind != "acerto" and w is not None and w != rb:
            right = panel(rb, w, rf["winner_rot"], (0, 140, 255), f"vencedora: {reps[rkeys[w]]} rot {rf['winner_rot']}", [r["zone"], "colocada no buraco pelo lado da 1.a vizinha"])
            info[-1]["winner"] = reps[rkeys[w]]
            return hstack_pad([left, right])
        return left

    def montage(imgs, name, per_row):
        rs = [hstack_pad(imgs[i:i + per_row], gap=14) for i in range(0, len(imgs), per_row)]
        w = max(r.shape[1] for r in rs)
        rs = [np.hstack([r, np.full((r.shape[0], w - r.shape[1], 3), 25, np.uint8)]) if r.shape[1] < w else r for r in rs]
        big = np.vstack([np.vstack([r, np.full((10, w, 3), 255, np.uint8)]) for r in rs])
        cv2.imwrite(os.path.join(DOC, name), big, [cv2.IMWRITE_JPEG_QUALITY, 80])
        print(name, big.shape, os.path.getsize(os.path.join(DOC, name)) // 1024, "KB")

    montage([mk(r, "acerto") for r in sel_h], "m11_melhores.jpg", 3)
    montage([mk(r, "falha") for r in fails], "m11_piores.jpg", 1)
    if sem:
        montage([mk(r, "sem candidata fiavel") for r in sem], "m11_sem_fiavel.jpg", 1)
    json.dump(info, open(os.path.join(DOC, "m11_figs.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def main():
    step = sys.argv[1] if len(sys.argv) > 1 else "sanidade"
    t0 = time.time()
    if step == "real":
        final = json.load(open(os.path.join(DOC, "m11_afinacao.json"), encoding="utf-8"))["final"]
        step_real(final)
        return
    P = pool.prepare()
    holes, _ = buracos.build(P)
    part, _ = load_part()
    print(f"preparado: {len(holes)} buracos ({time.time() - t0:.0f}s)")
    if step == "sanidade":
        step_sanidade(P, holes)
    elif step == "afinar":
        step_afinar(P, holes, part)
    elif step == "validar":
        final = json.load(open(os.path.join(DOC, "m11_afinacao.json"), encoding="utf-8"))["final"]
        step_validar(P, holes, part, final)
    elif step == "figs":
        final = json.load(open(os.path.join(DOC, "m11_afinacao.json"), encoding="utf-8"))["final"]
        step_figs(P, holes, part, final)
    print(f"({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
