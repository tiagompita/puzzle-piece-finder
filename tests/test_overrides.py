"""Manual contour overrides (:mod:`src.overrides`, :func:`src.render.rebuild_piece`): the append-only
``overrides.jsonl``, the polygon validation, and applying an override to the synthetic project
(npz / crop / ``piece_resegmented`` with ``motivo: manual``, replay and invariants), also through a
forced re-segmentation of the sheet (the manual contour wins over the segmented one)."""

import json
import os

import numpy as np
import pytest

from src import overrides as OV
from src import render as R
from src.state import Project, replay
from test_query import _project


# ---------------------------------------------------------------- pure helpers
def _circle(n=60, r=100.0, cx=500.0, cy=400.0):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.stack([cx + r * np.cos(t), cy + r * np.sin(t)], 1)


def test_polygon_helpers():
    sq = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
    assert len(OV.clean_polygon(sq)) == 4 and OV.polygon_area(sq) == 100.0
    assert OV.is_simple(sq)
    assert not OV.is_simple([[0, 0], [10, 10], [10, 0], [0, 10]])          # bow tie
    assert not OV.is_simple([[0, 0], [10, 0], [5, 0], [5, 5]])              # collinear fold-back
    c = _circle()
    assert OV.is_simple(c)
    rs = OV.resample_closed(c, 12.0)
    assert abs(len(rs) - round(2 * np.pi * 100 / 12)) <= 2
    mask, (ox, oy, ow, oh), cnt = OV.rasterize_polygon(c, 1000, 800)
    assert abs(mask.astype(bool).sum() - np.pi * 100 ** 2) / (np.pi * 100 ** 2) < 0.02
    assert cnt.dtype == np.int32 and cnt[:, 0].min() >= ox and cnt[:, 1].max() < oy + oh


def test_editor_polygon_roundtrip_is_exact():
    """Stored pixel-chain contour -> handles (~1 mm, corners kept) -> expanded back with
    nothing edited = the same polygon and the same raster; moving one handle only straightens its two
    stretches."""
    blob = np.array([[300, 300], [420, 300], [430, 340], [470, 330], [470, 380], [430, 370], [420, 420],
                     [360, 420], [370, 460], [330, 470], [320, 420], [300, 420]], float)
    _, _, cnt = OV.rasterize_polygon(blob, 1000, 800)                     # the pixel chain a segmentation stores
    d = OV.clean_polygon(cnt)
    idx = OV.editor_indices(d, 12.0)
    assert 20 <= len(idx) < len(d) and list(idx) == sorted(idx)
    arc = np.hypot(*np.diff(np.vstack([d[idx], d[idx][:1]]), axis=0).T)
    assert arc.max() <= 12.0 + 1.5                                        # handles about every step
    for corner in ([420, 300], [470, 330], [330, 470]):                   # corners stay handles
        assert np.min(np.hypot(*(d[idx] - corner).T)) <= 1.5
    e = OV.expand_polygon(d, d[idx], list(idx), [True] * len(idx))
    assert np.array_equal(e, d)
    m0, b0, c0 = OV.rasterize_polygon(cnt, 1000, 800)
    m1, b1, c1 = OV.rasterize_polygon(e, 1000, 800)
    assert b0 == b1 and np.array_equal(m0, m1) and np.array_equal(c0, c1)
    assert np.array_equal(OV.editor_polygon(cnt, 12.0), d[idx])
    v = d[idx].copy()
    k = 5
    v[k] += [4.0, 0.0]
    oi = list(idx)
    oi[k] = None
    keep = [True] * len(idx)
    keep[k] = keep[k - 1] = False
    e2 = OV.expand_polygon(d, v, oi, keep)
    lost = idx[k + 1] - idx[k - 1] - 1                                    # dense points between the neighbours
    assert len(e2) == len(d) - lost + 1 and any(np.array_equal(p, v[k]) for p in e2)


def test_validate_polygon_reasons():
    c = _circle()
    area = OV.polygon_area(c)
    assert OV.validate_polygon(c, 1000, 800, area) is None
    assert "pelo menos" in OV.validate_polygon(c[::4], 1000, 800, area)                       # 15 points
    assert "fora do scan" in OV.validate_polygon(c + [450, 0], 1000, 800, area)
    bow = np.vstack([c[:30], c[30:][::-1]])                                                    # self-crossing
    assert "cruza" in OV.validate_polygon(bow, 1000, 800, None)
    assert "área" in OV.validate_polygon(_circle(r=60), 1000, 800, area)                     # 36 %
    assert "área" in OV.validate_polygon(_circle(r=130), 1000, 800, area)                    # 169 %
    assert OV.validate_polygon(_circle(r=115), 1000, 800, area) is None                      # 132 %


# ---------------------------------------------------------------- project
def _moved_contour(pr, pid, dx=6.0):
    """The current contour resampled at ~1 mm with its rightmost vertices pushed out by ``dx`` px."""
    c = OV.resample_closed(pr.contour_px(pid), 12.0)
    x = c[:, 0]
    right = x > x.min() + 0.8 * (x.max() - x.min())
    c[right, 0] += dx
    return c


def _nlines(fp):
    if not os.path.exists(fp):
        return 0
    with open(fp, encoding="utf-8") as f:
        return len([ln for ln in f if ln.strip()])


def test_append_override_append_only_and_validation(tmp_path):
    pr, placed, tw, dec = _project(tmp_path)
    fp = OV.overrides_path(pr)
    bad = OV.append_override(pr, tw, [[0, 0], [10, 0], [10, 10]])
    assert "error" in bad and _nlines(fp) == 0
    out = OV.append_override(pr, tw, _circle(r=10, cx=-50), nota="x")
    assert "fora do scan" in out["error"] and _nlines(fp) == 0
    tiny = OV.resample_closed(pr.contour_px(tw), 12.0)
    tiny = (tiny - tiny.mean(0)) * 0.5 + tiny.mean(0)
    assert "área" in OV.append_override(pr, tw, tiny)["error"]
    assert "desconhecida" in OV.append_override(pr, "P9999", tiny)["error"]
    c1 = _moved_contour(pr, tw, 4.0)
    r1 = OV.append_override(pr, tw, c1, nota="primeira")
    assert "error" not in r1 and r1["autor"] == "manual" and r1["scan_id"] == pr.piece(tw).scan_id
    assert r1["index_in_scan"] == pr.piece(tw).index_in_scan and len(r1["contour_px"]) == len(c1)
    with open(fp, encoding="utf-8") as f:
        first = f.read()
    r2 = OV.append_override(pr, tw, _moved_contour(pr, tw, 8.0), nota="segunda")
    with open(fp, encoding="utf-8") as f:
        both = f.read()
    assert both.startswith(first) and _nlines(fp) == 2                       # append-only
    assert OV.latest_overrides(pr)[tw]["nota"] == "segunda" and OV.has_override(pr, tw)
    assert not OV.has_override(pr, dec)
    assert r2["t"] and json.loads(both.splitlines()[0])["nota"] == "primeira"


def test_rebuild_piece_applies_override(tmp_path):
    pr, placed, tw, dec = _project(tmp_path)
    sid = pr.piece(tw).scan_id
    n_log = len(pr.events())
    with np.load(pr.p("pieces", f"{sid}.npz")) as z:
        before = {k: z[k] for k in z.files}
    crop_before = pr.crop_rgba(tw)
    assert "error" in R.rebuild_piece(pr, tw)                                # no override yet
    c = _moved_contour(pr, tw, 6.0)
    assert "error" not in OV.append_override(pr, tw, c, nota="recorte comido à direita")
    out = R.rebuild_piece(pr, tw)
    assert out["errors"] == [] and [x["piece"] for x in out["changed"]] == [tw]
    rec = out["changed"][0]
    assert rec["motivo"] == "manual" and rec["area_new"] > rec["area_old"]
    evs = pr.events()[n_log:]
    assert [e["action"] for e in evs] == ["piece_resegmented"]
    ev = evs[0]
    assert ev["motivo"] == "manual" and ev["nota"] == "recorte comido à direita" and ev["piece"] == tw
    assert ev["flags"]["manual_override"] is True and ev["flags"]["manual_nota"] == "recorte comido à direita"
    q = Project.open(pr.path)
    assert q.piece(tw).flags["manual_override"] is True and OV.is_manual(q.piece(tw))
    assert q.piece(tw).bbox == rec["bbox_new"]
    assert q.check_invariants(disk=True) == []
    rb, _ = replay(q.log_path, q.profile)
    assert rb == q.board
    with np.load(q.p("pieces", f"{sid}.npz")) as z:
        after = {k: z[k] for k in z.files}
    assert not np.array_equal(after[f"{tw}__contour_px"], before[f"{tw}__contour_px"])
    for pid in (placed, dec):                                                # other pieces untouched
        assert np.array_equal(after[f"{pid}__contour_px"], before[f"{pid}__contour_px"])
    cnt = after[f"{tw}__contour_px"]
    assert abs(cnt[:, 0].max() - (c[:, 0].max())) <= 1.5                     # the drawn outline, not the old one
    crop = q.crop_rgba(tw)
    bx, by, bw, bh = rec["bbox_new"]
    assert crop.shape[:2] == (bh, bw) and crop.shape != crop_before.shape
    al = crop[..., 3] > 0
    assert abs(al.sum() - OV.polygon_area(c)) / OV.polygon_area(c) < 0.03
    assert q.shape(tw) is not None and q.shape(tw).ok
    # already applied: nothing more to do
    out2 = R.rebuild_piece(q, tw)
    assert out2["errors"] == [] and out2["changed"] == [] and len(q.events()) == n_log + 1


def test_force_rebuild_keeps_manual_contour(tmp_path):
    """``rebuild_assets(force_scans=[sid])`` after an override re-segments the sheet but keeps the manual
    contour of the overridden piece (no event when it is already applied); the other pieces follow the
    segmentation."""
    from test_render import _ingested
    pr, sid = _ingested(tmp_path)
    pid = sorted(pr.pieces)[1]
    c = _moved_contour(pr, pid, 10.0)
    assert "error" not in OV.append_override(pr, pid, c, nota="à mão")
    out = R.rebuild_piece(pr, pid)
    assert out["errors"] == [] and [x["piece"] for x in out["changed"]] == [pid]
    with np.load(pr.p("pieces", f"{sid}.npz")) as z:
        manual_cnt = z[f"{pid}__contour_px"].copy()
    n_log = len(pr.events())
    q = Project.open(pr.path)
    out = R.rebuild_assets(q, force_scans=[sid], clean=False, register=False, progress=None)
    assert out["errors"] == [] and out["changed"] == []                       # nothing differs from the log
    assert len(q.events()) == n_log
    with np.load(q.p("pieces", f"{sid}.npz")) as z:
        assert np.array_equal(z[f"{pid}__contour_px"], manual_cnt)
    assert q.piece(pid).flags["manual_override"] is True
    # a newer override is applied by the forced rebuild too (motivo manual, not the caller's)
    c2 = _moved_contour(q, pid, 5.0)
    assert "error" not in OV.append_override(q, pid, c2, nota="segunda")
    out = R.rebuild_assets(q, force_scans=[sid], clean=False, register=False, progress=None, motivo="recover_bays")
    assert out["errors"] == [] and [x["piece"] for x in out["changed"]] == [pid]
    ev = q.events()[-1]
    assert ev["action"] == "piece_resegmented" and ev["motivo"] == "manual" and ev["nota"] == "segunda"
    assert Project.open(q.path).check_invariants(disk=True) == []
