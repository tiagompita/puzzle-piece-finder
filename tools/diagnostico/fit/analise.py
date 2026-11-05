"""E-fit, passo 3: números do E4 / E5 a partir de ``resultados.json`` (fit_eval.py). Critérios em GT.md §5."""

import collections
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import REPO  # noqa: E402
from fit_eval import FAIL_RMS, EQUIV_RMS, GEMEO_NEAR, wilson  # noqa: E402

SUF = sys.argv[1] if len(sys.argv) > 1 else ""
R = json.load(open(os.path.join(REPO, "docs", "diagnostico", "fit", f"resultados{SUF}.json"), encoding="utf-8"))
res = R["results"]
OUT = os.path.join(REPO, "docs", "diagnostico", "fit", f"analise{SUF}.json")


def topk(rows, key, k):
    n = len(rows)
    hit = sum(1 for r in rows if r.get(key) is not None and r[key] <= k)
    lo, hi = wilson(hit, n)
    return dict(n=n, hit=hit, p=hit / n if n else float("nan"), lo=lo, hi=hi)


def hyper_top(n_pass, m, k):
    """P(pelo menos um dos m aceites nas k primeiras de uma ordem aleatória de n_pass)."""
    if n_pass <= 0 or m <= 0:
        return 0.0
    k = min(k, n_pass)
    return 1.0 - math.comb(n_pass - m, k) / math.comb(n_pass, k) if n_pass - m >= k else 1.0


def baselines(rows, mode):
    n = len(rows)
    ma = [r[f"m_{mode}"] for r in rows]
    chance_all = sum(m / r["n_all"] for m, r in zip(ma, rows)) / n
    chance_comp = sum(m / r["n_comp"] for m, r in zip(ma, rows) if r["n_comp"]) / n
    out = dict(chance_all=chance_all, chance_comp=chance_comp)
    for k in (1, 3):
        out[f"chords_top{k}"] = sum(hyper_top(r["n_pass"], r[f"m_pass_{mode}"], k) for r in rows) / n
    out["mean_n_pass"] = sum(r["n_pass"] for r in rows) / n
    out["mean_n_comp"] = sum(r["n_comp"] for r in rows) / n
    out["frac_true_filtered_by_chords"] = sum(1 for r in rows if r[f"m_{mode}"] and not r[f"m_pass_{mode}"]) / n
    return out


def summary(rows, mode="lenient"):
    return dict(e4_top1=topk(rows, f"e4_{mode}", 1), e4_top3=topk(rows, f"e4_{mode}", 3), e4_top10=topk(rows, f"e4_{mode}", 10),
                e5_top1=topk(rows, f"e5_{mode}", 1), e5_top3=topk(rows, f"e5_{mode}", 3),
                cost_top1=topk(rows, f"e4_cost_{mode}", 1), cost_top3=topk(rows, f"e4_cost_{mode}", 3),
                img_top1=topk(rows, f"img_{mode}", 1), img_top3=topk(rows, f"img_{mode}", 3),
                base=baselines(rows, mode))


def classify(r, which):
    """causa provável (regras fixas de GT.md §5)."""
    if r.get("no_true_in_pool"):
        return "forma do lado mal lida (M3/M4): vizinha sem forma no pool"
    if (not r.get("true_kind_ok")) or (not r.get("true_chord_pass")) or (r.get("true_rms") is not None and r["true_rms"] >= FAIL_RMS):
        return "forma do lado mal lida (M3/M4)"
    if r.get("true_rms") is not None and r.get("rms_best") is not None and r["rms_best"] <= r["true_rms"] + GEMEO_NEAR:
        return "gémeo/ambiguidade genuína"
    if which == "e5":
        e4 = r.get("e4_lenient")
        if e4 is not None and e4 <= 3:
            return "imagem enganadora"
    return "inconcluso (pose/escala só via imagem; ou vencedor mais parecido sem ser equivalente)"


def slice_table(rows, keyf, mode="lenient", min_n=20):
    g = collections.defaultdict(list)
    for r in rows:
        g[keyf(r)].append(r)
    out = []
    for k, rs in sorted(g.items(), key=lambda kv: str(kv[0])):
        out.append(dict(slice=str(k), n=len(rs), e4_top1=topk(rs, f"e4_{mode}", 1), e4_top3=topk(rs, f"e4_{mode}", 3),
                        e5_top1=topk(rs, f"e5_{mode}", 1), small=len(rs) < min_n))
    return out


def main():
    rows = res
    out = dict(n=len(rows), N_all=R["N_all"], n_reps=R["n_reps"], n_twin_reps=R["n_twin_reps"])
    out["lenient"] = summary(rows, "lenient")
    out["strict"] = summary(rows, "strict")
    # por proveniência
    prov = lambda r: "b/d (independente do layout)" if any(p in ("b", "d") for p in r["q"]["prov"]) else "a (só layout)"
    zone = lambda r: r["q"]["zone"]
    kind = lambda r: r["q"]["kind_a"]
    out["slices"] = dict(prov=slice_table(rows, prov), zone=slice_table(rows, zone), kind=slice_table(rows, kind),
                         prov_zone=slice_table(rows, lambda r: (prov(r)[:1], r["q"]["zone"])),
                         page=slice_table([r for r in rows if r["q"]["prov"][0] == "a"], lambda r: r["q"]["scan_a"]))
    # fatias do tipo de lado × zona
    out["slices"]["kind_zone"] = slice_table(rows, lambda r: (r["q"]["kind_a"], r["q"]["zone"]))
    # causas das falhas (lenient)
    for which in ("e4", "e5"):
        fails = [r for r in rows if r.get(f"{which}_lenient") is None or r[f"{which}_lenient"] > 1]
        out[f"fail_{which}_top1"] = dict(n=len(fails), causes=dict(collections.Counter(classify(r, which) for r in fails)))
        f3 = [r for r in rows if r.get(f"{which}_lenient") is None or r[f"{which}_lenient"] > 3]
        out[f"fail_{which}_top3"] = dict(n=len(f3), causes=dict(collections.Counter(classify(r, which) for r in f3)))
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    def fmt(t):
        return f"{100 * t['p']:.1f} % ({t['hit']}/{t['n']}; Wilson {100 * t['lo']:.1f}–{100 * t['hi']:.1f})"

    for mode in ("lenient", "strict"):
        s = out[mode]
        b = s["base"]
        print(f"\n== {mode} (n={len(rows)}) ==")
        print("E4 top-1", fmt(s["e4_top1"]), "| top-3", fmt(s["e4_top3"]), "| top-10", fmt(s["e4_top10"]))
        print("E5 top-1", fmt(s["e5_top1"]), "| top-3", fmt(s["e5_top3"]))
        print("custo(rms+0.5dl) top-1", fmt(s["cost_top1"]), "| top-3", fmt(s["cost_top3"]))
        print("só imagem top-1", fmt(s["img_top1"]), "| top-3", fmt(s["img_top3"]))
        print("baselines: acaso(todos) %.5f  acaso(T/B) %.4f  cordas top-1 %.4f top-3 %.4f  (n_pass médio %.0f, n_comp médio %.0f)  verdadeiro filtrado pelas cordas %.1f %%"
              % (b["chance_all"], b["chance_comp"], b["chords_top1"], b["chords_top3"], b["mean_n_pass"], b["mean_n_comp"], 100 * b["frac_true_filtered_by_chords"]))
    for key in ("prov", "zone", "kind", "prov_zone", "kind_zone", "page"):
        print("\n--", key)
        for t in out["slices"][key]:
            print(f"  {t['slice']:<40} n={t['n']:<4} E4 top1 {100*t['e4_top1']['p']:.0f} % top3 {100*t['e4_top3']['p']:.0f} % | E5 top1 {100*t['e5_top1']['p']:.0f} %" + ("  (n<20)" if t["small"] else ""))
    for k in ("fail_e4_top1", "fail_e4_top3", "fail_e5_top1"):
        print(k, out[k])


if __name__ == "__main__":
    main()
