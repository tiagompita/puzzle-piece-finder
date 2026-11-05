"""E-fit, passo 1: GT de adjacências internas SEM circularidade, com proveniência por par.

Só leitura (``projects/alpes`` e ``src/`` não são alterados). Saída: ``docs/diagnostico/fit/gt_pairs.json``
e o resumo impresso que alimenta ``docs/diagnostico/fit/GT.md``. Correr da raiz: ``python tools/diagnostico/fit/gt.py``.

Proveniências que entram no GT (as únicas):
  a  layout da vista explodida feito à mão pelo Tiago (páginas ``montado_pNN``): vizinhas por posição na
     página (centros dos corpos), sem olhar para o encaixe dos lados. Os lados que se encaram saem da direção
     da normal exterior no referencial da página (``legacy.label_sides``: só usa os cantos).
  b  GT manual (88 peças: canto BE, canto BD, E-sym): células conhecidas à mão; adjacência = células
     vizinhas; o lado que olha para o vizinho vem do ``theta_deg`` do log (decidido pelos lados F e pelo tipo
     T/B, nunca pelo RMS do perfil: ver GT.md).
  d  confirmada fisicamente pelo Tiago: ``placed`` com origin ``gemeo`` e secções ancoradas com fonte ``manual``.

NÃO entram como GT: ``legado_scan`` / ``legado_scan+pista`` (decididas por imagem, gémeas, encaixe), ``foto``.
Essas posições só servem para etiquetar a zona de um par e para medir o ruído do layout (nunca para o decidir).
"""

import collections
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DIRS, DUP_PAGE_SCANS, REPO, open_project, physical_clusters  # noqa: E402

from src.legacy import label_sides, page_rotation  # noqa: E402
from src.locate import body_center_mm  # noqa: E402
from src import render  # noqa: E402

OUT = os.path.join(REPO, "docs", "diagnostico", "fit", "gt_pairs.json")

# layout (a): fixado antes de correr. Vizinha em E / S = a mais próxima ao longo do eixo, vizinhança mútua
A_ALONG = (0.9, 2.0)        # células ao longo do eixo (espaçamento típico da vista explodida ≈ 1,6 células)
A_ACROSS = 0.35             # células de desvio transversal (mais apertado que o 0,7 da src/legacy.py)
SIDE_TOL_DEG = 25.0
# zonas por faixa de linhas do tabuleiro (fixas, só para fatiar): ver GT.md
ZONES = (("céu", 1, 14), ("montanha/floresta", 15, 27), ("vale/aldeia", 28, 40), ("relva", 41, 47))
NORMAL_DEG = {"N": -90.0, "E": 0.0, "S": 90.0, "W": 180.0}
STEP = {"N": (-1, 0), "E": (0, 1), "S": (1, 0), "W": (0, -1)}
OPP = {"N": "S", "S": "N", "E": "W", "W": "E"}


def zone_of(cell):
    if cell is None:
        return "sem posição"
    for name, a, b in ZONES:
        if a <= cell[0] <= b:
            return name
    return "?"


def wrap(a):
    return (a + 180.0) % 360.0 - 180.0


def board_dirs(shape, theta_deg):
    """Direção no tabuleiro de cada lado (ângulo da normal exterior + theta), ou None se não for 1-para-1."""
    ctr = body_center_mm(shape)
    out = {}
    for i, s in enumerate(shape.sides):
        v = 0.5 * (s.p0_mm + s.p1_mm) - ctr
        a = float(np.degrees(np.arctan2(v[1], v[0]))) + float(theta_deg)
        d = min(DIRS, key=lambda k: abs(wrap(a - NORMAL_DEG[k])))
        if abs(wrap(a - NORMAL_DEG[d])) > SIDE_TOL_DEG or d in out:
            return None
        out[d] = i
    return out if len(out) == 4 else None


def main():
    pr = open_project()
    prof = pr.profile
    t95 = float(prof.calibration["silhueta_silhueta"]["t95"])
    pids = [p for p, x in pr.pieces.items() if x.estado != "descartada"]
    sh = {p: pr.shape(p) for p in pids}
    cl, extra = physical_clusters(pr, pids, t95)
    log = pr.events()
    placed_origin = {}
    for ev in log:
        if ev["action"] == "placed":
            placed_origin[ev["piece"]] = ev.get("origin")

    # ---- proveniência da posição de cada peça (estado atual)
    prov = {}
    sec_fonte = {sid: s.anchor.get("fonte") for sid, s in pr.sections.items() if s.anchor.get("anchored")}
    for p in pids:
        x = pr.piece(p)
        if x.estado != "colocada" or x.celula is None:
            continue
        cell = pr.board[tuple(x.celula)]
        if cell["fonte"] == "log":
            o = placed_origin.get(p)
            prov[p] = "b" if o == "gt" else ("d" if o == "gemeo" else "?")
        elif x.seccao_id in sec_fonte:
            f = sec_fonte[x.seccao_id]
            prov[p] = "d" if f == "manual" else "c"
        else:
            prov[p] = "?"
    cnt = collections.Counter(prov.values())
    print("posições por proveniência (peças):", dict(cnt))

    rep_cell, rep_prov = {}, {}        # por cluster
    order = {"b": 0, "d": 1, "a": 2, "c": 3, "?": 4}
    for p, pv in prov.items():
        r = cl[p]
        if r not in rep_prov or order[pv] < order[rep_prov[r]]:
            rep_prov[r] = pv
            rep_cell[r] = tuple(pr.piece(p).celula)
    cell_any = {}                       # qualquer proveniência: só para a zona
    for p in pids:
        x = pr.piece(p)
        if x.celula is not None and x.estado == "colocada":
            cell_any.setdefault(cl[p], tuple(x.celula))

    records = {}                        # (clusterA, clusterB) ordenado -> registo
    skipped = collections.Counter()

    def add(prv, pa, ia, pb, ib, da, extra_info):
        ka, kb = cl[pa], cl[pb]
        if ka == kb:
            skipped["mesmo cluster"] += 1
            return
        for (x, ix, y, iy) in ((pa, ia, pb, ib), (pb, ib, pa, ia)):
            key = (cl[x], cl[y])
            rec = records.get(key)
            kind = sh[x].sides[ix].kind
            if rec is None:
                records[key] = dict(a=x, b=y, side_a=ix, side_b=iy, kind_a=kind, kind_b=sh[y].sides[iy].kind,
                                    prov=[prv], info=[extra_info])
            else:
                if prv not in rec["prov"]:
                    rec["prov"].append(prv)
                    rec["info"].append(extra_info)
                # a proveniência melhor manda no par de lados usado
                if order[prv] < order[rec["prov"][0]] and prv != rec["prov"][0]:
                    rec["prov"].insert(0, rec["prov"].pop(rec["prov"].index(prv)))
                    rec["a"], rec["b"], rec["side_a"], rec["side_b"] = x, y, ix, iy
                    rec["kind_a"], rec["kind_b"] = kind, sh[y].sides[iy].kind

    # ---- (b) e (d): células independentes vizinhas
    by_cell = {}
    for r, c in rep_cell.items():
        if rep_prov[r] in ("b", "d"):
            by_cell[c] = r
    # peça (do cluster) com a posição independente, para ler o theta
    holder = {}
    for p, pv in prov.items():
        if pv in ("b", "d") and rep_prov.get(cl[p]) == pv and tuple(pr.piece(p).celula) == rep_cell[cl[p]]:
            holder.setdefault(cl[p], p)
    for c, r in sorted(by_cell.items()):
        for d in ("E", "S"):
            nb = (c[0] + STEP[d][0], c[1] + STEP[d][1])
            r2 = by_cell.get(nb)
            if r2 is None:
                continue
            pa, pb = holder[r], holder[r2]
            ta = render.initial_theta(pr, pa)
            tb = render.initial_theta(pr, pb)
            if ta is None or tb is None or sh[pa] is None or sh[pb] is None or not sh[pa].ok or not sh[pb].ok:
                skipped["b/d sem theta ou forma"] += 1
                continue
            da, db = board_dirs(sh[pa], ta), board_dirs(sh[pb], tb)
            if da is None or db is None:
                skipped["b/d lados não 1-para-1"] += 1
                continue
            prv = "b" if (rep_prov[r] == "b" and rep_prov[r2] == "b") else "d"
            add(prv, pa, da[d], pb, db[OPP[d]], d, dict(cells=[list(c), list(nb)]))

    # ---- (a): layout das páginas montado
    pages = collections.defaultdict(list)
    for sid, sc in pr.model.scans.items():
        if sc.get("kind") == "montado" and sid not in DUP_PAGE_SCANS:
            pages[sid] = [p for p in pids if pr.piece(p).scan_id == sid and sh[p] is not None and sh[p].ok]
    cell_mm = float(np.mean([prof.cell_mm["w"], prof.cell_mm["h"]]))
    layout_pairs_total = 0
    a_noise = collections.Counter()
    for sid, ps in sorted(pages.items()):
        rot = page_rotation([sh[p] for p in ps])
        info = {}
        for p in ps:
            dirs, ok, flat = label_sides(sh[p], rot)
            t = np.radians(rot)
            R = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
            info[p] = (dirs, ok, body_center_mm(sh[p]) @ R.T / cell_mm)
        use = [p for p in ps if info[p][1]]
        skipped["a: peça sem 4 lados N/E/S/W"] += len(ps) - len(use)
        for d, (ax, cr) in (("E", (0, 1)), ("S", (1, 0))):
            nxt = {}
            prv_ = {}
            for i in use:
                best, bj = None, None
                for j in use:
                    if i == j:
                        continue
                    dv = info[j][2] - info[i][2]
                    along, across = dv[ax], dv[cr]
                    if A_ALONG[0] <= along <= A_ALONG[1] and abs(across) <= A_ACROSS:
                        if best is None or along < best:
                            best, bj = along, j
                if bj is not None:
                    nxt[i] = bj
            for j in use:
                best, bi = None, None
                for i in use:
                    if i == j:
                        continue
                    dv = info[j][2] - info[i][2]
                    along, across = dv[ax], dv[cr]
                    if A_ALONG[0] <= along <= A_ALONG[1] and abs(across) <= A_ACROSS:
                        if best is None or along < best:
                            best, bi = along, i
                if bi is not None:
                    prv_[j] = bi
            for i, j in nxt.items():
                if prv_.get(j) != i:
                    skipped["a: vizinhança não mútua"] += 1
                    continue
                layout_pairs_total += 1
                # ruído do layout: se as duas peças têm posição independente (b/d) e não são vizinhas, é falso
                ri, rj = cl[i], cl[j]
                if rep_prov.get(ri) in ("b", "d") and rep_prov.get(rj) in ("b", "d"):
                    ci, cj = rep_cell[ri], rep_cell[rj]
                    a_noise["adjacente" if abs(ci[0] - cj[0]) + abs(ci[1] - cj[1]) == 1 else "não adjacente"] += 1
                add("a", i, info[i][0][d], j, info[j][0][OPP[d]], d, dict(page=sid))

    # ---- zona, classes, saída
    out = []
    for (ka, kb), rec in sorted(records.items(), key=lambda kv: (kv[1]["prov"][0], kv[0])):
        cell = cell_any.get(ka)
        out.append(dict(a=rec["a"], b=rec["b"], side_a=rec["side_a"], side_b=rec["side_b"], kind_a=rec["kind_a"],
                        kind_b=rec["kind_b"], prov=rec["prov"], zone=zone_of(cell), cell_a=cell, cluster_a=ka, cluster_b=kb,
                        scan_a=pr.piece(rec["a"]).scan_id, scan_b=pr.piece(rec["b"]).scan_id))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(dict(t95=t95, queries=out, skipped=dict(skipped), n_clusters=len(set(cl.values())), a_noise=dict(a_noise),
                       layout_pairs_total=layout_pairs_total, extra_dups=len(extra)), f, ensure_ascii=False, indent=0)

    print("\nDESCARTADOS:", dict(skipped))
    print("pares de layout (a) mútuos:", layout_pairs_total, "| ruído medido onde há posição b/d nas duas:", dict(a_noise))
    print("\nlados (consultas dirigidas) =", len(out), "; pares físicos =", len(out) // 2)
    first = collections.Counter(r["prov"][0] for r in out)
    anyp = collections.Counter(p for r in out for p in r["prov"])
    print("por proveniência principal:", dict(first), "| presença (um par pode ter várias):", dict(anyp))
    print("por classe do lado consultado:", dict(collections.Counter(r["kind_a"] for r in out)))
    print("por tipo de par (consultado→vizinho):", dict(collections.Counter(r["kind_a"] + ">" + r["kind_b"] for r in out)))
    print("por zona:", dict(collections.Counter(r["zone"] for r in out)))
    print("por proveniência × zona:", dict(collections.Counter((r["prov"][0], r["zone"]) for r in out)))
    print("por página (a):", dict(collections.Counter(r["scan_a"] for r in out if r["prov"][0] == "a")))


if __name__ == "__main__":
    main()
