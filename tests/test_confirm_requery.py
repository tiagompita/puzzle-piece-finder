"""Incremental re-query after a confirmation (:func:`src.confirm.confirm` -> :func:`src.query.run_query`).

Synthetic project (real :class:`src.state.Project` in ``tmp_path``, as ``tests/test_query.py``): a
placed piece Q at (2, 3) (twin cell (3, 4)), its loose twin T, a decoy D of the same class (the
runner-up of the twin query) and a loose piece E of another class (never a candidate of Q's query).
The real ``find_twin`` without the image proposes T for (3, 4).
"""

import json
import os

import cv2
import numpy as np
from PIL import Image

import synth
from src.shape import analyse
from src.state import Project
from test_query import BG, KINDS, _piece_px
from test_shape import MMPP


def _build(tmp_path):
    prof = synth.profile(rows=4, cols=6, p90=None)
    pp = tmp_path / "puzzle.json"
    prof.save(str(pp))
    pr = Project.create(str(tmp_path / "proj"), str(pp))
    board = synth.body_mm(KINDS, deltas=(0.8, -0.5, 0.4, 0.3))
    decoy = synth.body_mm(KINDS, deltas=(-0.9, 0.7, -0.6, -0.8))
    other = synth.body_mm("TTBB", deltas=(0.2, 0.1, -0.3, 0.5))
    twin = synth.twin_board_contour(board, prof)
    pieces = [(_piece_px(board, 23.0, (400, 400)), (200, 40, 40)),
              (_piece_px(twin, -61.0, (1000, 400)), (40, 60, 200)),
              (_piece_px(decoy, 140.0, (1600, 400)), (210, 170, 30)),
              (_piece_px(other, 10.0, (2200, 400)), (90, 30, 120))]
    img = np.full((800, 2600, 3), BG, np.uint8)
    for pts, col in pieces:
        cv2.fillPoly(img, [np.round(pts).astype(np.int32).reshape(-1, 1, 2)], col)
    scan = tmp_path / "scan.png"
    Image.fromarray(img).save(scan)
    sid = pr.add_scan(str(scan), dpi=300, lote=3)
    os.makedirs(pr.p("crops"), exist_ok=True)
    ids = []
    for i, (pts, _) in enumerate(pieces):
        x0, y0 = np.floor(pts.min(0)).astype(int) - 10
        x1, y1 = np.ceil(pts.max(0)).astype(int) + 10
        al = np.zeros(img.shape[:2], np.uint8)
        cv2.fillPoly(al, [np.round(pts).astype(np.int32).reshape(-1, 1, 2)], 255)
        rel = f"crops/P{i + 1:04d}.png"
        Image.fromarray(np.ascontiguousarray(np.dstack([img, al])[y0:y1, x0:x1])).save(pr.p(rel))
        ids.append(pr.add_piece(sid, {"index_in_scan": i, "n_no_lote": i + 1, "shape": analyse(pts, MMPP),
                                      "contour": pts, "bbox": [int(x0), int(y0), int(x1 - x0), int(y1 - y0)],
                                      "crop_path": rel}))
    q, t, d, e = ids
    assert pr.shape(e).cls != pr.shape(q).cls
    pr.place(q, (2, 3), theta_deg=-23.0)
    pr.save()
    return pr, q, t, d, e


def _fetch(pr):
    with open(pr.p("fetch.json"), encoding="utf-8") as f:
        return json.load(f)


def test_placing_next_to_a_free_cell_requeries_it(tmp_path):
    """E (no candidate of anything) placed at (3, 3): the free cell (3, 4) next to it (a pending twin
    cell) is in the re-queried set and its twin query runs again instead of being carried over from
    the previous list (a marker written into the old entry is gone, the real margin is back)."""
    from src.confirm import confirm
    from src.query import run_query
    pr, q, t, d, e = _build(tmp_path)
    run_query(pr, use_image=False)
    js = _fetch(pr)
    te = next(x for x in js["entries"] if x["origin"] == "gemeo" and x["cell"] == [3, 4])
    assert te["piece"] == t and te["decision"] == "aceite" and e not in te.get("cand_ids", [])
    m0 = te["margin"]
    te["margin"], te["reasons"] = 999.0, ["marcador do teste"]      # stale marker: survives only if not re-queried
    with open(pr.p("fetch.json"), "w", encoding="utf-8") as f:
        json.dump(js, f)
    r = confirm(pr, e, cell=(3, 3), origin="manual", use_image=False)
    assert "error" not in r and r["invariants"] == []
    assert (3, 4) in {tuple(c) for c in r["affected_cells"]}
    assert (2, 3) not in {tuple(c) for c in r["affected_cells"]}         # occupied neighbour (Q) not added
    te = next(x for x in _fetch(pr)["entries"] if x["origin"] == "gemeo" and x["cell"] == [3, 4])
    assert te["piece"] == t and te["query"] == q and te["decision"] == "aceite"
    assert "marcador do teste" not in te["reasons"] and abs(te["margin"] - m0) < 1e-9
