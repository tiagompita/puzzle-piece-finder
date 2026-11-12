"""Tabelas de ``grupos_juncoes.py`` (critérios em ``docs/diagnostico/fit/GRUPOS_JUNCOES.md`` §1).
Uso: grupos_juncoes_tabelas.py <raw.json> <resumo.json>"""

import collections
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO)
from src.fit import wilson  # noqa: E402

raw = json.load(open(sys.argv[1]))
T, W, G = raw["true"], raw["wrong"], raw["twin"]


def band(nj):
    return "1" if nj == 1 else "2" if nj == 2 else "3" if nj == 3 else ">=4"


BANDS = ["1", "2", "3", ">=4"]
ZONES = ["céu", "montanha/floresta", "vale/aldeia", "relva"]


def fmt(k, n):
    if n == 0:
        return "—  (n=0)"
    lo, hi = wilson(round(k), n) if abs(k - round(k)) < 1e-9 else wilson(k, n)
    return f"{100 * k / n:.1f}% [{100 * lo:.1f}-{100 * hi:.1f}] n={n}"


def wil_frac(k, n):
    # Wilson com k fracionário (aproximado)
    import math
    z = 1.96
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0, c - h), min(1, c + h)


def fmtf(k, n):
    if n == 0:
        return "— (n=0)"
    lo, hi = wil_frac(k, n)
    return f"{100 * k / n:.1f}% [{100 * lo:.1f}-{100 * hi:.1f}] n={n}"


out = {}
print("== ERRADAS (posições): n =", len(W), "; blocos", len({w['block'] for w in W}))
for crit in ("A", "B"):
    print(f"-- critério {crit}: falso 'encaixa' / 'não sei' / 'não encaixa' por n_j")
    for b in BANDS:
        s = [w for w in W if band(w["nj"]) == b]
        c = collections.Counter(w[crit] for w in s)
        nb = len({w["block"] for w in s if w[crit] == "E"})
        print(f"  nj {b:>3}: n={len(s):6d}  E {fmt(c['E'], len(s))}  ns {100 * c['ns'] / max(1, len(s)):.1f}%  X {100 * c['X'] / max(1, len(s)):.1f}%  blocos com >=1 E: {nb}")
        out[f"wrong_{crit}_nj{b}"] = dict(n=len(s), E=c["E"], ns=c["ns"], X=c["X"], blocos_E=nb)
    print(f"-- critério {crit}: por zona do bloco x n_j (falso 'encaixa')")
    for z in ZONES:
        row = []
        for b in BANDS:
            s = [w for w in W if band(w["nj"]) == b and w["zone"] == z]
            k = sum(1 for w in s if w[crit] == "E")
            row.append(f"{b}: {k}/{len(s)}")
            out[f"wrong_{crit}_{z}_nj{b}"] = dict(n=len(s), E=k)
        print(f"  {z:18s} " + " | ".join(row))
print("-- por zona do lugar testado (A), n e E")
for z in ZONES:
    s = [w for w in W if w["tzone"] == z]
    print(f"  {z:18s} n={len(s)} E={sum(1 for w in s if w['A'] == 'E')}")
print("-- o que mata as erradas (A): impossível / regra F / só custo")
for b in BANDS:
    s = [w for w in W if band(w["nj"]) == b]
    n = max(1, len(s))
    print(f"  nj {b:>3}: impossível {100 * sum(1 for w in s if w['imp']) / n:.1f}%  F {100 * sum(1 for w in s if w['fviol']) / n:.1f}%  imp ou F {100 * sum(1 for w in s if w['imp'] or w['fviol']) / n:.1f}%")

print("\n== CERTAS (blocos): n =", len(T))
print("distribuição de n_j naturais:", sorted(collections.Counter(t["nj"] for t in T).items()))
for crit in ("A", "B"):
    print(f"-- critério {crit}")
    for b in BANDS:
        if b == ">=4":
            s = [t for t in T if t["nj"] >= 4]
            c = collections.Counter(t[crit] for t in s)
            n = len(s)
            kX, kns, kE = c["X"], c["ns"], c["E"]
        else:
            k = int(b)
            s = [t for t in T if str(k) in t["subsets"]]
            n = len(s)
            kX = sum(t["subsets"][str(k)].get(f"{crit}_X", 0) / t["subsets"][str(k)]["total"] for t in s)
            kns = sum(t["subsets"][str(k)].get(f"{crit}_ns", 0) / t["subsets"][str(k)]["total"] for t in s)
            kE = sum(t["subsets"][str(k)].get(f"{crit}_E", 0) / t["subsets"][str(k)]["total"] for t in s)
        print(f"  nj {b:>3}: blocos={n:3d}  X(falso não encaixa) {fmtf(kX, n)}  ns {fmtf(kns, n)}  E {fmtf(kE, n)}")
        out[f"true_{crit}_nj{b}"] = dict(n=n, X=kX, ns=kns, E=kE)
    print(f"-- critério {crit}: por zona (>=4 natural, subconjuntos k=2)")
    for z in ZONES:
        sz = [t for t in T if t["zone"] == z]
        s4 = [t for t in sz if t["nj"] >= 4]
        s2 = [t for t in sz if "2" in t["subsets"]]
        x4 = sum(1 for t in s4 if t[crit] == "X")
        n4 = sum(1 for t in s4 if t[crit] == "ns")
        x2 = sum(t["subsets"]["2"].get(f"{crit}_X", 0) / t["subsets"]["2"]["total"] for t in s2)
        print(f"  {z:18s} blocos={len(sz)} | >=4: n={len(s4)} X={x4} ns={n4} | k=2: n={len(s2)} X={x2:.2f}")
        out[f"true_{crit}_{z}"] = dict(blocos=len(sz), n4=len(s4), X4=x4, ns4=n4, n2=len(s2), X2=x2)

print("\n== GÉMEAS (180°, posição da gémea admissível com >=1 junção):", len(G))
for g in G:
    print("  ", g)
out["twin"] = G
print("\n== maiores custos por junção das certas (máx por bloco), percentis:")
import numpy as np
mx = [max(c for c in t["costs"] if c is not None) for t in T if any(c is not None for c in t["costs"])]
print("   p50 %.2f p90 %.2f p95 %.2f max %.2f (t_abs %.3f); blocos com junção impossível: %d; nt: %d" % (
    np.percentile(mx, 50), np.percentile(mx, 90), np.percentile(mx, 95), max(mx), raw["t_abs"],
    sum(1 for t in T if "imp" in t["states"]), sum(1 for t in T if "nt" in t["states"])))
print("   blocos certos com F violada:", sum(1 for t in T if t["fviol"]))


# ---------------------------------------------------------------- extras (tabelas do relatório)
def orig_of(name):
    _, hw, l0, c0 = name.split("_")
    h, w = map(int, hw.split("x"))
    return h, w, int(l0), int(c0)


def overlaps_orig(w):
    h, ww, l0, c0 = orig_of(w["block"])
    nh, nw = (h, ww) if w["r"] in (0, 2) else (ww, h)
    a0, a1, b0, b1 = w["tl"][0], w["tl"][0] + nh - 1, w["tl"][1], w["tl"][1] + nw - 1
    return not (a1 < l0 or a0 > l0 + h - 1 or b1 < c0 or b0 > c0 + ww - 1)


print("\n== EXTRAS: erradas por estrato (critério A e B), falso 'encaixa'")
strata = {"todas": W, "r=0 (sem rodar)": [w for w in W if w["r"] == 0],
          "sobre o lugar original (deslocadas)": [w for w in W if overlaps_orig(w)]}
for nm, S in strata.items():
    for crit in ("A", "B"):
        row = []
        for b in BANDS:
            s = [w for w in S if band(w["nj"]) == b]
            k = sum(1 for w in s if w[crit] == "E")
            row.append(f"{b}: {fmt(k, len(s))}")
        print(f"  {nm:38s} {crit}  " + " | ".join(row))
print("\n== por zona do bloco x n_j com Wilson (A)")
for z in ("céu", "relva"):
    for crit in ("A", "B"):
        row = []
        for b in BANDS:
            s = [w for w in W if band(w["nj"]) == b and w["zone"] == z]
            k = sum(1 for w in s if w[crit] == "E")
            nb = len({w["block"] for w in s if w[crit] == "E"}); nbt = len({w["block"] for w in s})
            row.append(f"{b}: {fmt(k, len(s))} blocos {nb}/{nbt}")
        print(f"  {z:6s} {crit}  " + " | ".join(row))
print("\n== certas por zona x k (A e B), X e ns")
for z in ("céu", "relva"):
    for crit in ("A", "B"):
        row = []
        for b in BANDS:
            if b == ">=4":
                s = [t for t in T if t["zone"] == z and t["nj"] >= 4]
                kX = sum(1 for t in s if t[crit] == "X"); kn = sum(1 for t in s if t[crit] == "ns")
            else:
                k = int(b)
                s = [t for t in T if t["zone"] == z and str(k) in t["subsets"]]
                kX = sum(t["subsets"][str(k)].get(f"{crit}_X", 0) / t["subsets"][str(k)]["total"] for t in s)
                kn = sum(t["subsets"][str(k)].get(f"{crit}_ns", 0) / t["subsets"][str(k)]["total"] for t in s)
            row.append(f"{b}: X {fmtf(kX, len(s))} ns {100 * kn / max(1, len(s)):.0f}%")
        print(f"  {z:6s} {crit}  " + " | ".join(row))
print("\n== certas: tamanho do bloco (n_j natural, X no lugar certo inteiro)")
for n in (4, 6, 9):
    s = [t for t in T if t["n"] == n]
    print(f"  {n} peças: blocos {len(s)}, n_j min/mediana/max {min(t['nj'] for t in s)}/{int(np.median([t['nj'] for t in s]))}/{max(t['nj'] for t in s)}, X(A) {sum(1 for t in s if t['A']=='X')}, X(B) {sum(1 for t in s if t['B']=='X')}, ns(B) {sum(1 for t in s if t['B']=='ns')}")
print("\n== certas: blocos 'X' no lugar certo inteiro:")
for t in T:
    if t["A"] == "X":
        print("  ", t["block"], t["zone"], "nj", t["nj"], "estados", collections.Counter(t["states"]), "F", t["fviol"], "custos", t["costs"])
print("\n== blocos certos: de onde vem o X nos subconjuntos k=1: junções com custo > t_abs (fração das junções)")
allc = [c for t in T for c in t["costs"] if c is not None]
print("  junções certas com custo finito:", len(allc), " > t_abs:", sum(1 for c in allc if c > raw["t_abs"]), " impossíveis:", sum(1 for t in T for s in t["states"] if s == "imp"))
for z in ("céu", "relva"):
    zc = [c for t in T if t["zone"] == z for c in t["costs"] if c is not None]
    print(f"  {z}: n={len(zc)} p50 {np.percentile(zc,50):.2f} p90 {np.percentile(zc,90):.2f} fração>t_abs {np.mean(np.array(zc)>raw['t_abs']):.3f}")
V = raw.get("valid", [])
vs = [c for v in V for c in v["shape_costs"]]; vd = [c for v in V for c in v["dE"] if c is not None]
ts = [c for t in T for c in t["shape_costs"]]; td = [c for t in T for c in t["dE"] if c is not None]
print("\n== VALIDAÇÃO DA ROTAÇÃO A 180° / GÉMEAS (peça X no lugar da sua gémea Y colocada, Y retirada):", len(V), "casos")
print("  custo só de forma (rms/1,1 + pen) por junção: certas p50 %.2f p90 %.2f | gémeas p50 %.2f p90 %.2f (n %d / %d)" % (
    np.percentile(ts, 50), np.percentile(ts, 90), np.percentile(vs, 50), np.percentile(vs, 90), len(ts), len(vs)))
print("  dE por junção: certas p50 %.1f p90 %.1f | gémeas p50 %.1f p90 %.1f" % (np.percentile(td, 50), np.percentile(td, 90), np.percentile(vd, 50), np.percentile(vd, 90)))
wj = [w["Jshape"] for w in W if w["Jshape"] is not None]
print("  forma média por posição errada sem junção impossível: p50 %.2f p90 %.2f (n %d de %d)" % (np.percentile(wj, 50), np.percentile(wj, 90), len(wj), len(W)))
print("  gémeas: % com forma+imagem 'encaixa' (A):", np.mean([v["A"] == "E" for v in V]), " J forma média <= 1,5:", np.mean([np.mean(v["shape_costs"]) <= 1.5 for v in V if v["shape_costs"]]))

print("\n== certas: subconjuntos de exatamente 4 junções (e natural >=5), por zona, A e B")
for z in ("céu", "relva", "todas"):
    for crit in ("A", "B"):
        s = [t for t in T if (z == "todas" or t["zone"] == z) and "4" in t["subsets"]]
        kX = sum(t["subsets"]["4"].get(f"{crit}_X", 0) / t["subsets"]["4"]["total"] for t in s)
        kn = sum(t["subsets"]["4"].get(f"{crit}_ns", 0) / t["subsets"]["4"]["total"] for t in s)
        print(f"  {z:6s} {crit}: k=4 X {fmtf(kX, len(s))}  ns {100 * kn / max(1, len(s)):.1f}%")


# ---------------------------------------------------------------- 2026-11-12: negativos difíceis por zona (só agregados)
def shifted_one(w):
    """Deslocado exatamente uma célula, sem rodar: r = 0 e o canto de cima à esquerda a distância de Manhattan 1."""
    _, _, l0, c0 = orig_of(w["block"])
    return w["r"] == 0 and abs(w["tl"][0] - l0) + abs(w["tl"][1] - c0) == 1


print("\n== NEGATIVOS DIFÍCEIS por zona do bloco x n_j, critérios A e B (falso 'encaixa', blocos com >=1 falso / blocos)")
HARD = {"sobre_lugar": ("sobre o lugar original (deslocado ou rodado no sítio)", overlaps_orig),
        "desloc1": ("deslocado exatamente 1 célula, sem rodar", shifted_one)}
for key, (nm, pred) in HARD.items():
    S = [w for w in W if pred(w)]
    print(f"-- {nm}: n = {len(S)}")
    for z in ZONES + ["todas"]:
        for crit in ("A", "B"):
            row = []
            for b in BANDS:
                s = [w for w in S if band(w["nj"]) == b and (z == "todas" or w["zone"] == z)]
                k = sum(1 for w in s if w[crit] == "E")
                nb = len({w["block"] for w in s if w[crit] == "E"}); nbt = len({w["block"] for w in s})
                row.append(f"{b}: {k}/{len(s)} {fmt(k, len(s))} blocos {nb}/{nbt}")
                lo, hi = wilson(k, len(s)) if s else (None, None)
                out[f"dificeis_{key}_{crit}_{z}_nj{b}"] = dict(n=len(s), E=k, wilson=[lo, hi], blocos_E=nb, blocos=nbt)
            print(f"  {z:18s} {crit}  " + " | ".join(row))
json.dump(out, open(sys.argv[2], "w"), ensure_ascii=False, indent=1)
