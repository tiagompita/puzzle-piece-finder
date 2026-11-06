"""E-fit, passo 5: buracos virtuais a partir do GT de adjacências (só leitura).

Um buraco = uma peça física X (o «alvo») com >= 2 vizinhas ortogonais cuja adjacência vem do GT (proveniência a, b ou d:
layout explodido, GT manual, confirmada; nunca encaixe/arte/gémea). A peça é «retirada por código»: só se usam os lados
das vizinhas (que ficam como estão) e o lado de X que olha para cada uma (no referencial do representante de X).

``python tools/diagnostico/fit/buracos.py`` imprime a contagem (a porta do passo 5) e escreve ``buracos.json``.
"""

import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pool  # noqa: E402
from common import REPO  # noqa: E402

OUT = os.path.join(REPO, "docs", "diagnostico", "fit", "buracos.json")


def build(P):
    """{rb: dict(queries=[índices em P['Q']], xs=[...], n=...)} para os buracos válidos; mais as contagens de descarte."""
    Q = P["Q"]
    g = json.load(open(pool.fe.GT, encoding="utf-8"))
    zone_of = {}
    for r in g["queries"]:
        zone_of.setdefault(r["cluster_a"], r["zone"])
    # cluster (chave de representante) -> índice de rep: Q[i]['rb'] é o índice; precisamos da chave para a zona
    by = collections.defaultdict(list)
    for i, q in enumerate(Q):
        if q["rb"] >= 0 and q["xs"] is not None:
            by[q["rb"]].append(i)
    holes, drop = {}, collections.Counter()
    for rb, idx in by.items():
        # uma vizinha por cluster (o mesmo par pode estar em duas proveniências: já vem fundido no GT)
        seen_nb, seen_side, keep = set(), set(), []
        bad = False
        for i in idx:
            q = Q[i]
            nb = q["own"]
            if nb < 0 or nb in seen_nb:
                continue
            if q["xs"] in seen_side:                       # dois vizinhos no mesmo lado: GT inconsistente
                bad = True
                break
            seen_nb.add(nb)
            seen_side.add(q["xs"])
            keep.append(i)
        if bad:
            drop["conflito: dois vizinhos no mesmo lado"] += 1
            continue
        if len(keep) < 2:
            drop["< 2 vizinhas"] += 1
            continue
        holes[rb] = dict(queries=keep, n=len(keep), prov=sorted({p for i in keep for p in Q[i]["prov"]}),
                         zone=collections.Counter(Q[i]["zone"] for i in keep).most_common(1)[0][0])
    return holes, drop


def main():
    P = pool.prepare()
    holes, drop = build(P)
    by_n = collections.Counter(h["n"] for h in holes.values())
    by_z = collections.Counter(h["zone"] for h in holes.values())
    by_nz = collections.Counter((h["n"], h["zone"]) for h in holes.values())
    indep = collections.Counter("b/d presente" if any(p in ("b", "d") for p in h["prov"]) else "só layout (a)" for h in holes.values())
    print("buracos válidos (>= 2 vizinhas GT):", len(holes), "| descartados:", dict(drop))
    print("por nº de vizinhas:", dict(sorted(by_n.items())))
    print("por zona:", dict(by_z))
    print("por (n, zona):", dict(sorted(by_nz.items())))
    print("proveniência:", dict(indep))
    json.dump(dict(n=len(holes), by_n={str(k): v for k, v in by_n.items()}, by_zone=dict(by_z),
                   by_n_zone={f"{k[0]}|{k[1]}": v for k, v in by_nz.items()}, prov=dict(indep), dropped=dict(drop)),
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
