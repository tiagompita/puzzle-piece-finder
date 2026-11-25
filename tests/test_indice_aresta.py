"""R0036 (P0395): the index silhouette of an ``aresta+indice`` override read against the painted edge.

The edge the user painted (``aresta_px``) is exact (D5, 2026-11-25). The index stored with it (``contour_px``) is
derived by the editor (``src.strokes.normalizar``) and, for P0395, kept the automatic contour's mistakes: a 37 mm
wide silhouette with the scanner's dark strip at the bottom of the sheet and the paper between them (13.9 mm away
from the edge; on the 34 other edited pieces the index stays within 1.94 mm of the edge). The index used by the
program must be the edge plus the shadow halo of the index convention, never more than the halo band."""

import json
import os

import cv2
import numpy as np
from PIL import Image

from src import overrides as OV
from src import render as R
from src import shape as SH
from src import strokes as ST
from src.state import Project
from test_query import _project

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "data", "p0395_r0036_override.json")
MMPP = 25.4 / 300


def _p0395():
    with open(FIX, encoding="utf-8") as f:
        ov = json.load(f)
    rgb = np.asarray(Image.open(os.path.join(ROOT, ov["scan_file"])).convert("RGB"))
    return ov, rgb


def _beyond_mm2(index_pts, edge_pts, band_mm, shape_hw):
    """Area (mm²) of the filled ``index_pts`` farther than ``band_mm`` from the filled ``edge_pts``."""
    H, W = shape_hw
    mi = np.zeros((H, W), np.uint8)
    ma = np.zeros((H, W), np.uint8)
    cv2.fillPoly(mi, [np.round(np.asarray(index_pts, float)).astype(np.int32).reshape(-1, 1, 2)], 1)
    cv2.fillPoly(ma, [np.round(np.asarray(edge_pts, float)).astype(np.int32).reshape(-1, 1, 2)], 1)
    d = cv2.distanceTransform((1 - ma).astype(np.uint8), cv2.DIST_L2, 5) * MMPP
    return float(((mi > 0) & (d > band_mm)).sum()) * MMPP * MMPP


def test_p0395_index_is_the_painted_edge_plus_the_halo():
    ov, rgb = _p0395()
    H, W = rgb.shape[:2]
    # the stored index is far outside the painted edge (the bug's input, unchanged)
    assert _beyond_mm2(ov["contour_px"], ov["aresta_px"], 2.0, (H, W)) > 10.0
    idx, info = OV.index_contour_from(ov, rgb, MMPP)
    assert info["limitado"] is True
    assert _beyond_mm2(idx, ov["aresta_px"], ST.INDICE_HALO_MAX_MM, (H, W)) == 0.0
    # the painted edge is inside the index, whole (nothing of it is cut away)
    ma = np.zeros((H, W), np.uint8)
    mi = np.zeros((H, W), np.uint8)
    cv2.fillPoly(ma, [np.round(np.asarray(ov["aresta_px"])).astype(np.int32).reshape(-1, 1, 2)], 1)
    cv2.fillPoly(mi, [np.round(np.asarray(idx)).astype(np.int32).reshape(-1, 1, 2)], 1)
    assert int(((ma > 0) & (mi == 0)).sum()) == 0
    # the scanner strip is gone: nothing within 0.5 mm of the bottom of the sheet
    assert np.asarray(idx)[:, 1].max() < H - 1 - 0.5 / MMPP
    # a border piece of nominal size: one F side, chords 17.5-19.5 mm (nominal 18.5 x 17.9, index +0.3-0.5)
    sh = SH.analyse(idx, MMPP)
    assert sh.ok and sh.n_flat == 1, (sh.cls, sh.lens)
    assert all(17.5 <= L <= 19.5 for L in sh.lens), sh.lens
    # the line itself is untouched
    with open(FIX, encoding="utf-8") as f:
        assert json.load(f)["contour_px"] == ov["contour_px"]


def test_index_within_the_band_is_used_verbatim():
    """A line without ``aresta_px``, or whose index stays within the halo band of its edge, gives back
    ``contour_px`` exactly (the 34 other edited pieces of projects/alpes are of this kind)."""
    ov, rgb = _p0395()
    old = {"contour_px": ov["contour_px"]}
    idx, info = OV.index_contour_from(old, rgb, MMPP)
    assert info["limitado"] is False and idx is old["contour_px"]
    ok = {"contour_px": ov["aresta_px"], "aresta_px": ov["aresta_px"], "convencao": OV.CONVENCAO_ARESTA}
    idx, info = OV.index_contour_from(ok, rgb, MMPP)
    assert info["limitado"] is False and idx is ok["contour_px"]


def _strip_index(pr, pid):
    """The piece's contour plus a 'scanner strip' joined to it by a paper bridge (the P0395 defect), and the
    piece's contour itself as the painted edge."""
    c = np.asarray(pr.contour_px(pid), float)
    x0, y0 = np.floor(c.min(0)).astype(int)
    x1, y1 = np.ceil(c.max(0)).astype(int)
    m = np.zeros((800, 2000), np.uint8)
    cv2.fillPoly(m, [np.round(c).astype(np.int32).reshape(-1, 1, 2)], 1)
    cx = int(round(c[np.argmax(c[:, 1]), 0]))           # under the lowest point of the piece
    m[y1 - 5:y1 + 45, cx - 6:cx + 6] = 1                  # bridge over the paper, 4 mm long
    m[y1 + 40:y1 + 60, cx - 10:cx + 150] = 1              # the strip, 13 mm long
    return ST.mascara_poligono(m > 0).astype(float), c


def test_rebuild_reads_the_index_within_the_edge_band(tmp_path):
    pr, placed, tw, dec = _project(tmp_path)
    sid = pr.piece(tw).scan_id
    idx, edge = _strip_index(pr, tw)
    before = OV.read_overrides(pr)
    rec = OV.append_override(pr, tw, idx, extra={"metodo": "tracos", "aresta_px": edge,
                                                 "convencao": OV.CONVENCAO_ARESTA})
    assert "error" not in rec
    line = OV.read_overrides(pr)[-1]
    out = R.rebuild_piece(pr, tw)
    assert out["errors"] == [] and [x["piece"] for x in out["changed"]] == [tw]
    q = Project.open(pr.path)
    with np.load(q.p("pieces", f"{sid}.npz")) as z:
        cnt = z[f"{tw}__contour_px"]
    assert _beyond_mm2(cnt, edge, ST.INDICE_HALO_MAX_MM, (800, 2000)) == 0.0
    m = np.zeros((800, 2000), np.uint8)                   # the bridge and the strip are paper: only the piece is left
    cv2.fillPoly(m, [np.round(edge).astype(np.int32).reshape(-1, 1, 2)], 1)
    assert abs(q.piece(tw).area_mm2 - m.sum() * MMPP * MMPP) < 0.5
    # the override line is what was written, untouched, and still the latest one
    assert OV.read_overrides(pr)[:len(before)] == before and OV.read_overrides(pr)[-1] == line
    assert OV.latest_overrides(pr)[tw]["contour_px"] == line["contour_px"]
    # applied once: nothing pending, a second rebuild changes nothing
    n = len(q.events())
    assert R.rebuild_piece(q, tw)["changed"] == [] and len(q.events()) == n
