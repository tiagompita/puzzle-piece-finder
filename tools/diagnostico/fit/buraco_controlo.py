"""E-fit, passo 5, CONTROLO pós-hoc (não é o resultado do critério): o viés «mesma digitalização».

A peça certa e as vizinhas do GT vêm da mesma folha de scan (a mesma página montada), as concorrentes do pool vêm de
folhas diferentes: se o E5 se apoiar numa diferença de cor/exposição entre scans (o §6 de RESULTADOS.md avisava), a
peça certa ganha por estar na mesma folha e não por encaixar. Controlo: o mesmo custo conjunto (E5 e E4), N = 32, mas com
o pool tirado (A) só da mesma folha da peça certa e (B) só de outras folhas, nos mesmos buracos.
Saída: ``docs/diagnostico/fit/buraco_controlo{,_encolhido}.json``. Correr da raiz.
"""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import buraco as B  # noqa: E402
import buracos  # noqa: E402
import pool  # noqa: E402
import fit_eval as fe  # noqa: E402
from common import REPO  # noqa: E402

N = 32
OUT = os.path.join(REPO, "docs", "diagnostico", "fit", f"buraco_controlo{fe.SUFFIX}.json")


def main():
    P = pool.prepare()
    holes, _ = buracos.build(P)
    H = B.hole_table(P, holes)
    R, pr, reps, rkeys = P["R"], P["pr"], P["reps"], P["rkeys"]
    scan = np.array([pr.piece(reps[k]).scan_id for k in rkeys])
    rng = np.random.default_rng(B.SEED + 99)
    res = {"A_mesma_folha": [], "B_outras_folhas": [], "aleatorio": []}
    kept = 0
    for h in H:
        forbid = set(h["nb"]) | {h["rb"]}
        same = np.array([z for z in range(R) if scan[z] == scan[h["rb"]] and z not in forbid])
        diff = np.array([z for z in range(R) if scan[z] != scan[h["rb"]] and z not in forbid])
        if len(same) < N - 1 or len(diff) < N - 1:
            continue
        kept += 1
        for name, cand in (("A_mesma_folha", same), ("B_outras_folhas", diff), ("aleatorio", np.array([z for z in range(R) if z not in forbid]))):
            M = np.zeros((B.DRAWS, R), bool)
            for d in range(B.DRAWS):
                M[d, rng.choice(cand, N - 1, replace=False)] = True
            M[:, h["rb"]] = True
            row = {}
            for nm, C in (("e4", h["C4"]), ("e5", h["C5"])):
                J, _ = B.joint(C, h["xs"], R)
                sm = np.where(M, J[None], np.inf)
                rk = B.rank_of(sm, h["acc_len"])
                row[nm] = float((rk <= 1).mean())
            row["m"] = h["m"]
            res[name].append(row)
    out = dict(N=N, holes_kept=kept, n_holes=len(H))
    for name, rows in res.items():
        out[name] = {nm: B.wil(float(np.mean([r[nm] for r in rows])), len(rows)) for nm in ("e4", "e5")}
        print(f"{name:<16} n={len(rows)}  E4 len1 {100 * out[name]['e4']['p']:.1f}  E5 len1 {100 * out[name]['e5']['p']:.1f}  "
              f"(E5 Wilson {100 * out[name]['e5']['lo']:.1f}-{100 * out[name]['e5']['hi']:.1f})")
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("buracos mantidos:", kept, "de", len(H))


if __name__ == "__main__":
    main()
