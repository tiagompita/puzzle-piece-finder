"""E-fit, passo 6 (§14.4): o que muda nos lados verdadeiros entre «mesma folha» (passo 5) e «scans diferentes» (piloto).

Compara, por lado verdadeiro: RMS do perfil (forma), |ΔL| da corda (escala), ΔE da tira (cor) e nº de pontos de tira
válidos (recorte), em (A) vizinha de página montada/blocos, (B) vizinha também de scan de lote, (C) passo 5 (as 1442
adjacências do GT, mesma folha). Só mede; não corrige. Correr depois de ``real.py`` com a mesma condição (``FIT_SHRINK``).
Saída: ``docs/diagnostico/fit/real_compara{,_encolhido}.json``.
"""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pool  # noqa: E402
import fit_eval as fe  # noqa: E402
from common import REPO  # noqa: E402
from real import quartiles  # noqa: E402

OUT = os.path.join(REPO, "docs", "diagnostico", "fit", f"real_compara{fe.SUFFIX}.json")


def main():
    R = json.load(open(os.path.join(REPO, "docs", "diagnostico", "fit", f"real{fe.SUFFIX}.json"), encoding="utf-8"))
    sides = {"A": [], "B": []}
    for c in R["cases"]:
        for s in c["true_sides"]:
            sides["A" if s["kind"] != "soltas" else "B"].append(s)
    P = pool.prepare()
    costs = P["costs"]
    C = []
    for q in P["Q"]:
        if q["rb"] < 0 or q["xs"] is None:
            continue
        cv = costs(q["a"], q["side_a"])
        j = 4 * q["rb"] + q["xs"]
        C.append(dict(zone=q["zone"], rms=float(cv["rms"][j]), dl=float(cv["dl"][j]), de=(float(cv["de"][j]) if np.isfinite(cv["de"][j]) else None),
                      valid=int(cv["valid"][j]), passed=bool(cv["passed"][j])))
    P["save_cache"]()
    # C_ceu: controlo pós-hoc (as 15 confirmações são todas de céu, linhas 2-4; a cor do céu é lisa e a da relva não)
    groups = {"A_outro_scan": sides["A"], "B_scan_de_lote": sides["B"], "C_passo5_mesma_folha": C, "C_passo5_so_ceu": [r for r in C if r["zone"] == "céu"]}
    out = {}
    for g, rows in groups.items():
        out[g] = dict(n=len(rows), rms=quartiles([r["rms"] for r in rows]), dl=quartiles([r["dl"] for r in rows]),
                      de=quartiles([r["de"] for r in rows]), valid=quartiles([float(r["valid"]) for r in rows]),
                      passa_filtro=float(np.mean([r["passed"] for r in rows])) if rows else None)
        o = out[g]
        f = lambda d: "-" if d is None else f"{d['med']:.2f} [{d['q1']:.2f}-{d['q3']:.2f}]"  # noqa: E731
        print(f"{g:<22} n={o['n']:<5} RMS {f(o['rms'])} mm | |dL| {f(o['dl'])} mm | dE {f(o['de'])} | pts válidos {f(o['valid'])} | passa o filtro {100 * (o['passa_filtro'] or 0):.0f} %")
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
