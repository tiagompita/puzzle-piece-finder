"""Synthetic tests for the "go fetch" entries of :mod:`src.query` (pose, ghost, sheet; fast).

A placed piece with a known board pose and its loose twin (same die cut turned by the
profile's twin rotation, scanned at another angle) plus a decoy of the same class: the real
``find_twin`` (shape only, no art) proposes the twin, and the entry must carry the pose at
which the twin sits on the board (``theta = -psi`` of its scan), the ghost, the sheet and
the pose column of ``fetch.md``.
"""

import json
import os

import cv2
import numpy as np
import pytest
from PIL import Image

import synth
from src.locate import body_center_mm
from src.shape import analyse, transform_contour
from src.state import Project
from test_shape import MMPP

KINDS = "TBTB"
BG = (40, 160, 60)


def _piece_px(board_mm, psi, offset_px):
    """Scan contour (px) of a piece whose board-pose contour is ``board_mm``, turned by ``psi``."""
    return transform_contour(board_mm, psi, center=(0.0, 0.0)) / MMPP + np.asarray(offset_px, float)


def _project(tmp_path, psi_p=23.0, psi_t=-61.0, psi_d=140.0):
    prof = synth.profile(rows=4, cols=6, p90=None)
    pp = tmp_path / "puzzle.json"
    prof.save(str(pp))
    pr = Project.create(str(tmp_path / "proj"), str(pp))
    board = synth.body_mm(KINDS, deltas=(0.8, -0.5, 0.4, 0.3))
    decoy = synth.body_mm(KINDS, deltas=(-0.9, 0.7, -0.6, -0.8))
    twin = synth.twin_board_contour(board, prof)
    pieces = [(_piece_px(board, psi_p, (400, 400)), (200, 40, 40)),
              (_piece_px(twin, psi_t, (1000, 400)), (40, 60, 200)),
              (_piece_px(decoy, psi_d, (1600, 400)), (210, 170, 30))]
    img = np.full((800, 2000, 3), BG, np.uint8)
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
        rgba = np.dstack([img, al])[y0:y1, x0:x1]
        rel = f"crops/P{i + 1:04d}.png"
        Image.fromarray(np.ascontiguousarray(rgba)).save(pr.p(rel))
        ids.append(pr.add_piece(sid, {"index_in_scan": i, "n_no_lote": i + 1, "shape": analyse(pts, MMPP),
                                      "contour": pts, "bbox": [int(x0), int(y0), int(x1 - x0), int(y1 - y0)],
                                      "crop_path": rel}))
    placed, loose_twin, dec = ids
    assert rel.endswith(f"{dec}.png")
    pr.place(placed, (2, 3), theta_deg=-psi_p)       # twin cell (3, 4)
    pr.save()
    return pr, placed, loose_twin, dec


def test_twin_entry_pose_ghost_sheet(tmp_path):
    from src.query import run_query, wrap180
    psi_t = -61.0
    pr, placed, tw, dec = _project(tmp_path, psi_t=psi_t)
    entries = run_query(pr, use_image=False)
    e = next(x for x in entries if x["origin"] == "gemeo")
    assert e["piece"] == tw and e["cell"] == [3, 4] and e["decision"] == "aceite"
    assert e["query"] == placed and e["twin_id"] == placed and e["twin_cell"] == [2, 3]
    # pose: the twin was scanned turned by psi_t, so it goes back to the board with -psi_t
    assert e["pose_known"] is True and e["phi_deg"] is not None
    assert abs(wrap180(e["theta_deg"] - (-psi_t))) < 1.5
    assert e["scan_id"] == pr.piece(tw).scan_id and e["crop_path"] == f"crops/{tw}.png" and e["clean_path"] is None
    # ghost: the placed piece turned into the twin cell matches the loose piece in its predicted pose
    g = np.asarray(e["ghost"], float)
    assert 20 <= len(g) <= 120
    sh = pr.shape(tw)
    mine = transform_contour(sh.c - body_center_mm(sh), e["theta_deg"], center=(0.0, 0.0)) / synth.PITCH_MM
    d = np.sqrt(((g[:, None, :] - mine[None, :, :]) ** 2).sum(-1)).min(1)
    assert np.median(d) < 0.03                        # cells (~0.55 mm)
    # sheet written once, highlighted piece; index records it
    fp = pr.p(*e["sheet"].split("/"))
    assert e["sheet"] == f"render/sheets/{pr.piece(tw).scan_id}_{tw}.jpg" and os.path.exists(fp)
    assert os.path.getsize(fp) <= 250_000
    m0 = os.path.getmtime(fp)
    with open(pr.p("render", "sheets", "index.json"), encoding="utf-8") as f:
        assert e["sheet"] in json.load(f)
    # fetch.md has the pose column, fetch.json the new fields, the bag sheet exists
    md = open(pr.p("fetch.md"), encoding="utf-8").read()
    assert "| ordem | lote | nº no lote | id | célula | pose | origem |" in md
    assert f"| {tw} | (3,4) | {e['theta_deg']:.0f}° | gemeo | aceite |" in md
    js = json.load(open(pr.p("fetch.json"), encoding="utf-8"))
    je = next(x for x in js["entries"] if x["piece"] == tw)
    assert je["theta_deg"] == e["theta_deg"] and je["ghost"] == e["ghost"]
    assert os.path.exists(pr.p("fetch_3.jpg"))
    # incremental re-query (nothing affected): the retained entry keeps its fields, the sheet is not rewritten
    again = run_query(pr, use_image=False, only_cells=[], only_pieces=[])
    e2 = next(x for x in again if x["origin"] == "gemeo")
    assert e2["theta_deg"] == e["theta_deg"] and e2["ghost"] == e["ghost"] and e2["sheet"] == e["sheet"]
    assert os.path.getmtime(fp) == m0


def test_unknown_pose_when_placed_twin_has_no_theta(tmp_path):
    from src.query import _Ctx, _enrich
    pr, placed, tw, dec = _project(tmp_path)
    ctx = _Ctx(pr, use_image=False)
    ctx.poses[placed] = None                          # neither registration nor log theta
    e = {"origin": "gemeo", "piece": tw, "cell": [3, 4], "query": placed, "phi_deg": 10.0, "decision": "aceite"}
    _enrich(ctx, e, write=False)
    assert e["pose_known"] is False and e["theta_deg"] is None and "pose desconhecida" in e["pose_reason"]
    assert e["ghost"] is None and e["twin_id"] == placed


def test_ghost_contour_uses_profile_rotation():
    from src.query import ghost_contour
    sq = analyse(np.array([[0, 0], [218, 0], [218, 218], [0, 218]], float) + 100, MMPP)
    pose = {"theta_deg": 0.0, "pivot_mm": list(body_center_mm(sq)), "dx_mm": 0.5, "dy_mm": 0.0}
    rot = ghost_contour(sq, pose, synth.profile())                                   # rot180: d -> -d
    tra = ghost_contour(sq, pose, synth.profile(symmetry={"type": "translate", "cols": 2}))   # 0 deg
    assert np.mean(np.asarray(rot)[:, 0]) == pytest.approx(-0.5 / synth.PITCH_MM, abs=0.01)
    assert np.mean(np.asarray(tra)[:, 0]) == pytest.approx(0.5 / synth.PITCH_MM, abs=0.01)
