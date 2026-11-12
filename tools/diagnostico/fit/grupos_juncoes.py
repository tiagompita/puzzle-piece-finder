"""Verificação das junções de um grupo solto largado junto ao montado (só leitura de src/).

Critérios fixados ANTES de correr em ``docs/diagnostico/fit/GRUPOS_JUNCOES.md`` §1; este ficheiro só os implementa.
Uso (sobre uma CÓPIA do projeto; ela escreve a cache de tiras na cópia):

    .venv/Scripts/python.exe tools/diagnostico/fit/grupos_juncoes.py <projeto_copia> <saida_raw.json> [<saida_resumo.json>]
"""

import collections
import itertools
import json
import math
import os
import random
import sys
import time

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO)

from src import fit, render  # noqa: E402
from src.fit import (DIRS, DIR_IDX, OPP, STEP, HoleSide, board_dirs, pool_arrays, pool_items, side_costs,  # noqa: E402
                     wilson, zone_of, _Cache)
from src.shape import f_adjacent  # noqa: E402
from src.state import Project  # noqa: E402

SEED = 0
CAPS = {4: 50, 6: 40, 9: 25}
SHAPES = [(2, 2), (2, 3), (3, 2), (3, 3)]
MAX_SUBSETS = 60


def main(argv):
    proj_dir, out_raw = argv[1], argv[2]
    out_sum = argv[3] if len(argv) > 3 else None
    t0 = time.time()
    pr = Project.open(proj_dir)
    calib = fit.calibration(pr)
    cache = _Cache(pr, calib)
    prof = pr.profile
    L, C = prof.rows, prof.cols
    t_abs = calib.t_abs
    assert t_abs is not None, "sem t_abs calibrado"
    print("calib", calib.to_dict())

    # ---- peças colocadas utilizáveis (forma, pose, 4 lados mapeados)
    dirs, cellp = {}, {}
    for lc, cell in pr.board.iter_cells():
        pid = cell.get("peca_id")
        if cell["estado"] != "colocada" or not pid:
            continue
        p = pr.piece(pid)
        if p is None or p.same_as:
            continue
        sh = cache.shape(pid)
        th = render.initial_theta(pr, pid)
        if sh is None or not sh.ok or th is None:
            continue
        dr = board_dirs(sh, th)
        if dr is None or cache.eroded(pid) is None:
            continue
        dirs[pid] = dr
        cellp[lc] = pid
    ids = sorted(dirs)
    print("colocadas utilizáveis", len(ids), "t", round(time.time() - t0))
    items = pool_items(pr, pieces=ids, cache=cache)
    pa = pool_arrays(items)
    idx = {pid: k for k, pid in enumerate(pa.ids)}
    cache.save()
    print("pool", len(pa.ids), "t", round(time.time() - t0))

    memo = {}

    def jcost(nb, d, k, j):
        """Custo da junção: vizinha nb (na direção d da célula do grupo) contra o lado j da peça k do grupo.
        Devolve ('imp'|'nt'|'ok', custo)."""
        key = (nb, d)
        if key not in memo:
            sds = cache.eroded(nb)
            i = dirs[nb][OPP[d]]
            fa = f_adjacent([s.kind for s in sds])
            hs = HoleSide(piece_id=nb, direction=d, side=sds[i], f_adj=bool(fa[i]), strip=cache.strip(nb)[i])
            r = side_costs(hs, pa, calib)
            memo[key] = (r["cost"].astype(np.float32), r["comp"], r["hard"],
                         (r["rms"] / fit.RMS_SCALE + r["pen"]).astype(np.float32), r["dE"].astype(np.float32))
        cost, comp, hard, shp, de = memo[key]
        sc, d_e = float(shp[k, j]), float(de[k, j])
        if (not comp[k, j]) or hard[k, j]:
            return "imp", math.inf, sc, d_e
        c = float(cost[k, j])
        return ("ok", c, sc, d_e) if math.isfinite(c) else ("nt", math.inf, sc, d_e)

    # ---- blocos
    def free_cell(lc, gone):
        return lc in gone or not pr.board.occupied(lc)

    def all_usable(l0, c0, h, w):
        return all((l0 + i, c0 + j) in cellp for i in range(h) for j in range(w))

    rng = random.Random(SEED)
    blocks_all = []
    for (h, w) in SHAPES:
        for l0 in range(1, L - h + 2):
            for c0 in range(1, C - w + 2):
                if all_usable(l0, c0, h, w):
                    blocks_all.append((h, w, l0, c0))
    print("blocos possíveis", collections.Counter(h * w for h, w, _, _ in blocks_all))
    chosen = []
    for n in (4, 6, 9):
        cand = [b for b in blocks_all if b[0] * b[1] == n]
        rng.shuffle(cand)
        used, got = set(), []
        for (h, w, l0, c0) in cand:
            cells = [(l0 + i, c0 + j) for i in range(h) for j in range(w)]
            if any(c in used for c in cells):
                continue
            used.update(cells)
            got.append((h, w, l0, c0))
            if len(got) >= CAPS[n]:
                break
        chosen += got
    print("blocos escolhidos", collections.Counter(h * w for h, w, _, _ in chosen), "t", round(time.time() - t0))

    def rot_cell(i, j, h, w, r):
        if r == 0:
            return i, j
        if r == 1:
            return j, h - 1 - i
        if r == 2:
            return h - 1 - i, w - 1 - j
        return w - 1 - j, i

    def classify(juncs, fviol):
        """juncs: lista de (estado, custo). Devolve (A, B) em {'E','X','ns'}."""
        imp = any(s == "imp" for s, _ in juncs)
        fin = [c for s, c in juncs if s == "ok"]
        if imp or fviol:
            return "X", "X"
        if not fin:
            return "ns", "ns"
        J = float(np.mean(fin))
        if J > t_abs:
            return "X", "X"
        allfin = len(fin) == len(juncs) and len(juncs) >= 1
        a = "E" if allfin else "ns"
        b = "E" if (allfin and max(fin) <= t_abs) else "ns"
        return a, b

    def place(blk, r, tl, gone):
        """Avalia o bloco rodado r com o canto (0,0) rodado em tl. None se inadmissível."""
        h, w, l0, c0 = blk
        nh, nw = (h, w) if r in (0, 2) else (w, h)
        juncs, fviol, cellsb = [], False, []
        for i in range(h):
            for j in range(w):
                pid = cellp[(l0 + i, c0 + j)]
                a, b = rot_cell(i, j, h, w, r)
                x = (tl[0] + a, tl[1] + b)
                if not prof.in_grid(*x) or not free_cell(x, gone):
                    return None
                cellsb.append(x)
                k = idx[pid]
                dr = dirs[pid]
                req = prof.flat_directions(*x)
                for d in DIRS:
                    side = dr[DIRS[(DIR_IDX[d] - r) % 4]]
                    if (pa.kind[k, side] == "F") != (d in req):
                        fviol = True
                    y = (x[0] + STEP[d][0], x[1] + STEP[d][1])
                    if y in cellp and y not in gone and prof.in_grid(*y):
                        s, c, sc, d_e = jcost(cellp[y], d, k, side)
                        juncs.append((s, c, sc, d_e, pid, cellp[y], d))
        return juncs, fviol, cellsb

    recs_true, recs_wrong, recs_twin = [], [], []
    for bn, blk in enumerate(chosen):
        h, w, l0, c0 = blk
        gone = {(l0 + i, c0 + j) for i in range(h) for j in range(w)}
        bz = zone_of((l0 + h // 2, c0), prof)
        name = f"B{bn:03d}_{h}x{w}_{l0}_{c0}"
        # certa
        res = place(blk, 0, (l0, c0), gone)
        assert res is not None, name
        juncs, fviol, _ = res
        jj = [(s, c) for s, c, *_ in juncs]; shp = [round(q[2], 3) for q in juncs]; dee = [None if not math.isfinite(q[3]) else round(q[3], 2) for q in juncs]
        rec = dict(shape_costs=shp, dE=dee, block=name, n=h * w, zone=bz, nj=len(juncs), fviol=fviol, A=classify(jj, fviol)[0], B=classify(jj, fviol)[1],
                   costs=[round(c, 3) if math.isfinite(c) else None for _, c in jj], states=[s for s, _ in jj], subsets={})
        for k in (1, 2, 3, 4):
            if len(jj) < k:
                continue
            combos = list(itertools.combinations(range(len(jj)), k))
            if len(combos) > MAX_SUBSETS:
                combos = rng.sample(combos, MAX_SUBSETS)
            cnt = collections.Counter()
            for cb in combos:
                a, b = classify([jj[q] for q in cb], fviol)
                cnt[f"A_{a}"] += 1
                cnt[f"B_{b}"] += 1
            rec["subsets"][str(k)] = dict(cnt, total=len(combos))
        recs_true.append(rec)
        # candidatos a translação: cada célula do grupo rodado sobre cada célula livre vizinha de uma peça fora do bloco
        frontier = set()
        for y, pid in cellp.items():
            if y in gone:
                continue
            for d in DIRS:
                f = (y[0] + STEP[d][0], y[1] + STEP[d][1])
                if prof.in_grid(*f) and free_cell(f, gone):
                    frontier.add(f)
        twin_tl = (L + 1 - l0 - (h - 1), C + 1 - c0 - (w - 1))
        for r in range(4):
            cand = set()
            for i in range(h):
                for j in range(w):
                    a, b = rot_cell(i, j, h, w, r)
                    for f in frontier:
                        cand.add((f[0] - a, f[1] - b))
            for tl in sorted(cand):
                if r == 0 and tl == (l0, c0):
                    continue
                res = place(blk, r, tl, gone)
                if res is None:
                    continue
                juncs, fviol, cellsb = res
                if not juncs:
                    continue
                jj = [(s, c) for s, c, *_ in juncs]; shp = [round(q[2], 3) for q in juncs]; dee = [None if not math.isfinite(q[3]) else round(q[3], 2) for q in juncs]
                A, B = classify(jj, fviol)
                imp = any(s == "imp" for s, _ in jj)
                tz = zone_of((int(round(np.mean([c[0] for c in cellsb]))), cellsb[0][1]), prof)
                row = dict(shape_costs=shp if (r == 2 and tl == twin_tl) else None, dE=dee if (r == 2 and tl == twin_tl) else None, Jshape=(float(np.mean([x for x, q in zip(shp, juncs) if q[0] != 'imp'])) if any(q[0] != 'imp' for q in juncs) else None), block=name, r=r, tl=list(tl), nj=len(jj), zone=bz, tzone=tz, fviol=fviol, imp=imp, A=A, B=B)
                if r == 2 and tl == twin_tl:
                    row["costs"] = [round(c, 3) if math.isfinite(c) else None for _, c in jj]
                    recs_twin.append(row)
                else:
                    recs_wrong.append(row)
        if (bn + 1) % 10 == 0:
            print(f"  {bn + 1}/{len(chosen)} blocos, certas {len(recs_true)}, erradas {len(recs_wrong)}, gémeas {len(recs_twin)}, t {round(time.time() - t0)}")

    # ---- validação do código de rotação / posição gémea: blocos cuja gémea também está colocada (a gémea sai e o bloco entra a 180°)
    recs_val = []
    for (h, w) in [(1, 1), (1, 2), (2, 1), (2, 2)]:
        for l0 in range(1, L - h + 2):
            for c0 in range(1, C - w + 2):
                if not all_usable(l0, c0, h, w):
                    continue
                tl = (L + 1 - l0 - (h - 1), C + 1 - c0 - (w - 1))
                if not prof.in_grid(*tl) or tl[0] + h - 1 > L or tl[1] + w - 1 > C or not all_usable(tl[0], tl[1], h, w):
                    continue
                own = {(l0 + i, c0 + j) for i in range(h) for j in range(w)}
                twinc = {(tl[0] + i, tl[1] + j) for i in range(h) for j in range(w)}
                if own & twinc:
                    continue
                res = place((h, w, l0, c0), 2, tl, own | twinc)
                if res is None:
                    continue
                juncs, fviol, _ = res
                jj = [(s, c) for s, c, *_ in juncs]; shp = [round(q[2], 3) for q in juncs]; dee = [None if not math.isfinite(q[3]) else round(q[3], 2) for q in juncs]
                A, B = classify(jj, fviol)
                recs_val.append(dict(shape_costs=shp, dE=dee, shape=f"{h}x{w}", cell=[l0, c0], nj=len(jj), A=A, B=B, fviol=fviol, zone=zone_of((l0, c0), prof),
                                     costs=[round(c, 3) if math.isfinite(c) else None for _, c in jj], states=[s for s, _ in jj]))
    # consistência geométrica da rotação: para cada par interno adjacente, o deslocamento rodado == passo da direção rodada
    bad_rot = 0
    for blk in chosen[:20]:
        h, w, l0, c0 = blk
        for r in range(4):
            for i in range(h):
                for j in range(w):
                    for d in DIRS:
                        ii, jj2 = i + STEP[d][0], j + STEP[d][1]
                        if not (0 <= ii < h and 0 <= jj2 < w):
                            continue
                        a = rot_cell(i, j, h, w, r)
                        b = rot_cell(ii, jj2, h, w, r)
                        dd = DIRS[(DIR_IDX[d] + r) % 4]
                        if (b[0] - a[0], b[1] - a[1]) != STEP[dd]:
                            bad_rot += 1
    print("rotação: pares internos inconsistentes", bad_rot)
    cache.save()
    json.dump(dict(valid=recs_val, true=recs_true, wrong=recs_wrong, twin=recs_twin, t_abs=t_abs, calib=calib.to_dict()), open(out_raw, "w"))
    print("feito", len(recs_true), len(recs_wrong), len(recs_twin), "t", round(time.time() - t0))


if __name__ == "__main__":
    main(sys.argv)
