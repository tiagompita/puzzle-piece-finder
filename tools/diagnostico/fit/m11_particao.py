"""M11 (molde do buraco): partição afinação / validação dos 467+ buracos virtuais por FOLHA e por zona. Só leitura.

Regra (fixada em ``docs/diagnostico/fit/M11_CRITERIOS.md`` antes de qualquer avaliação; este ficheiro só a implementa):

* folhas de um buraco = {scan da peça-alvo} ∪ {scans das vizinhas do GT};
* S_T (afinação) = páginas ``montado`` cuja zona dominante é céu ou relva, em posição ÍMPAR (1.ª, 3.ª, …) na ordem
  por id dentro de cada zona;
* buraco ∈ afinação ⇔ todas as suas folhas ⊂ S_T; ∈ validação ⇔ nenhuma folha ∈ S_T; senão descartado (contado);
* reservados só para validação, mesmo que as folhas o permitissem: buracos com proveniência b/d (GT independente do
  layout) e buracos de montanha/floresta e vale/aldeia.

Correr da raiz (depois de ``gt.py`` e com a cache de tiras do ``fit_eval.py``):
``python tools/diagnostico/fit/m11_particao.py`` → ``docs/diagnostico/fit/m11_particao.json`` e o resumo impresso.
"""

import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import buracos  # noqa: E402
import pool  # noqa: E402
from common import REPO  # noqa: E402

OUT = os.path.join(REPO, "docs", "diagnostico", "fit", "m11_particao.json")
TUNE_ZONES = ("céu", "relva")
RESERVED_ZONES = ("montanha/floresta", "vale/aldeia")


def hole_sheets(P, holes):
    """{rb: (sheets, prov_bd, zone, m)} — folhas do alvo (todas as cópias físicas) e das vizinhas."""
    pr, Q, reps, rkeys, cl = P["pr"], P["Q"], P["reps"], P["rkeys"], P["cl"]
    members = collections.defaultdict(set)
    for pid, r in cl.items():
        members[r].add(pr.piece(pid).scan_id)
    out = {}
    for rb, h in holes.items():
        sheets = set(members[rkeys[rb]])
        for i in h["queries"]:
            sheets.add(pr.piece(Q[i]["a"]).scan_id)
        bd = any(p in ("b", "d") for p in h["prov"])
        out[rb] = (frozenset(sheets), bd, h["zone"], h["n"])
    return out


def choose_tuning_sheets(P, info):
    """Páginas ``montado`` com zona dominante céu/relva, posição ímpar por id dentro da zona."""
    pr = P["pr"]
    zone_votes = collections.defaultdict(collections.Counter)
    for rb, (sheets, bd, zone, m) in info.items():
        for s in sheets:
            if (pr.model.scans.get(s) or {}).get("kind") == "montado":
                zone_votes[s][zone] += 1
    by_zone = collections.defaultdict(list)
    page_zone = {}
    for s, votes in zone_votes.items():
        z = votes.most_common(1)[0][0]
        page_zone[s] = z
        by_zone[z].append(s)
    tuning = set()
    for z in TUNE_ZONES:
        pages = sorted(by_zone.get(z, []))
        tuning.update(pages[0::2])
    return tuning, page_zone, {z: sorted(v) for z, v in by_zone.items()}


def split(info, tuning):
    part = {}
    for rb, (sheets, bd, zone, m) in info.items():
        if bd or zone in RESERVED_ZONES:
            part[rb] = "validacao" if not (sheets & tuning) else "descartado_reservado"
        elif sheets <= tuning:
            part[rb] = "afinacao"
        elif not (sheets & tuning):
            part[rb] = "validacao"
        else:
            part[rb] = "descartado_misto"
    return part


def main():
    P = pool.prepare()
    holes, drop = buracos.build(P)
    info = hole_sheets(P, holes)
    tuning, page_zone, pages_by_zone = choose_tuning_sheets(P, info)
    part = split(info, tuning)
    reps, rkeys = P["reps"], P["rkeys"]
    rows = []
    for rb in sorted(holes):
        sheets, bd, zone, m = info[rb]
        rows.append(dict(rb=int(rb), piece=reps[rkeys[rb]], zone=zone, m=int(m), prov="bd" if bd else "a",
                         sheets=sorted(sheets), part=part[rb]))
    cnt = collections.Counter(r["part"] for r in rows)
    print("buracos:", len(rows), "| descartados na construção:", dict(drop))
    print("páginas por zona dominante:", pages_by_zone)
    print("S_T (afinação):", sorted(tuning))
    print("partição:", dict(cnt))

    def table(key):
        t = collections.defaultdict(collections.Counter)
        for r in rows:
            t[r[key]][r["part"]] += 1
        return {k: dict(v) for k, v in sorted(t.items(), key=lambda kv: str(kv[0]))}

    tabs = {k: table(k) for k in ("zone", "m", "prov")}
    for k, t in tabs.items():
        print(f"por {k}:", t)
    mz = collections.defaultdict(collections.Counter)
    for r in rows:
        mz[f"{r['m']}|{r['zone']}"][r["part"]] += 1
    sheets_val = sorted({s for r in rows if r["part"] == "validacao" for s in r["sheets"]})
    json.dump(dict(regra=__doc__.strip().split("\n\n")[1], tuning_sheets=sorted(tuning), validation_sheets=sheets_val,
                   page_zone=page_zone, pages_by_zone=pages_by_zone, counts=dict(cnt), by_zone=tabs["zone"], by_m=tabs["m"],
                   by_prov=tabs["prov"], by_m_zone={k: dict(v) for k, v in sorted(mz.items())}, dropped_build=dict(drop),
                   holes=rows),
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("escrito", OUT)


if __name__ == "__main__":
    main()
