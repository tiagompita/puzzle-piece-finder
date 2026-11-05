"""E-fit: refina a causa das falhas (GT.md §5). Divide «gémeo/ambiguidade» em equivalente geométrico real e
quase-empate por acaso. Uso: ``python tools/diagnostico/fit/causas.py [sufixo]`` (sufixo ``_encolhido`` para a variante).
"""

import collections
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import REPO  # noqa: E402
from fit_eval import EQUIV_RMS, FAIL_RMS, GEMEO_NEAR, build  # noqa: E402

suffix = sys.argv[1] if len(sys.argv) > 1 else ""
R = json.load(open(os.path.join(REPO, "docs", "diagnostico", "fit", f"resultados{suffix}.json"), encoding="utf-8"))
rows = R["results"]
pr, t95, chord, sh, cl, members, reps = build()
rkeys = sorted(reps)


def cand(n):
    return reps[rkeys[n // 4]], n % 4


def eq_dist(pb, ib, pc, ic):
    a, b = sh[pb].sides[ib], sh[pc].sides[ic]
    return float(np.sqrt(np.mean(np.sum((a.profile - b.profile) ** 2, -1))) * (a.chord_mm + b.chord_mm) / 2)


def causa(r, which):
    if r.get("no_true_in_pool") or r.get(f"{which}_lenient") is None:
        if r.get("true_chord_pass") is False or r.get("true_kind_ok") is False or r.get("no_true_in_pool"):
            return "forma mal lida: cordas/tipo"
        return "forma mal lida: fora do filtro"
    if (not r.get("true_kind_ok")) or (not r.get("true_chord_pass")) or (r.get("true_rms") or 0) >= FAIL_RMS:
        return "forma mal lida: RMS >= 2 mm"
    w = r.get("best_e5" if which == "e5" else "best_e4")
    if w is None:
        return "inconcluso"
    pc, ic = cand(w)
    q = r["q"]
    d = eq_dist(q["b"], q["side_b"], pc, ic)
    if d <= EQUIV_RMS:
        return "gémeo/equivalente geométrico (lado vencedor ≈ verdadeiro, <= 0,5 mm)"
    if r.get("rms_best") is not None and r["true_rms"] is not None and r["rms_best"] <= r["true_rms"] + GEMEO_NEAR:
        # o vencedor tem RMS <= verdadeiro + 0,15 mas NÃO é equivalente ao lado verdadeiro
        if which == "e5" and (r.get("e4_lenient") or 999) <= 3:
            return "imagem enganadora"
        return "quase-empate por acaso (vencedor melhor/igual em RMS, lado diferente do verdadeiro)"
    if which == "e5" and (r.get("e4_lenient") or 999) <= 3:
        return "imagem enganadora"
    return "inconcluso"


out = {}
for which in ("e4", "e5"):
    for thr in (1, 3):
        fails = [r for r in rows if r.get(f"{which}_lenient") is None or r[f"{which}_lenient"] > thr]
        c = collections.Counter(causa(r, which) for r in fails)
        out[f"{which}_top{thr}"] = dict(n=len(fails), causas=dict(c))
        print(f"{which} top-{thr}: {len(fails)} falhas")
        for k, v in c.most_common():
            print(f"   {v:5d} ({100 * v / len(fails):.0f} %)  {k}")
json.dump(out, open(os.path.join(REPO, "docs", "diagnostico", "fit", f"causas{suffix}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
