"""Anti-regression test for :func:`src.segmentation.segment_pieces`.

A synthetic scene of N well-separated, saturated-colour rectangles on a neutral
light-grey background is fed to the real segmentation pipeline. The pipeline is
chroma-dominated (``luma_weight`` 0.075 vs ``chroma_weight`` 1.0), so saturated
patches on a neutral surface are the case it separates most reliably; the
rectangles are sized well above the dust floor, inset from the frame margin, near
1:1 aspect and all equal-area, so none is pruned, split or flagged as a cluster.

The test asserts the pipeline finds exactly N pieces (all non-cluster) and that
every placed rectangle is recovered as one detected bbox with a matching centre
and near-equal size (a few px of symmetric padding is expected and tolerated).
"""

import os

import numpy as np
import pytest
from PIL import Image

from src.segmentation import segment_pieces, segment_scan


# Placed rectangles as (x, y, w, h, (r, g, b)); equal area, well separated, inset.
_BG = (205, 205, 205)  # neutral light grey -> large chroma distance to colours
_RECTS = [
    (80, 90, 150, 120, (200, 40, 40)),    # red
    (400, 70, 150, 120, (40, 160, 40)),   # green
    (650, 100, 150, 120, (40, 60, 200)),  # blue
    (120, 380, 150, 120, (210, 170, 30)),  # amber
    (500, 400, 150, 120, (150, 40, 170)),  # purple
]
_IMG_W, _IMG_H = 900, 700

# Padding (segment_pieces pad_ratio=0.02) plus contour rounding shifts each bbox
# outward by only a couple of px, so a small centre/size tolerance is expected.
_CENTER_TOL = 8.0
_SIZE_TOL = 14


def _make_scene():
    bg = np.full((_IMG_H, _IMG_W, 3), _BG, dtype=np.uint8)
    placed = []
    for (x, y, w, h, colour) in _RECTS:
        bg[y:y + h, x:x + w] = colour
        placed.append((x, y, w, h))
    return Image.fromarray(bg), placed


def test_segment_recovers_all_rectangles():
    img, placed = _make_scene()
    result = segment_pieces(img)

    assert "error" not in result, result.get("error")
    assert result["count"] == len(placed)

    pieces = result["pieces"]
    non_clusters = [p for p in pieces if not p["is_cluster"]]
    assert len(non_clusters) == len(placed)

    # Every placed rectangle must map to exactly one detected bbox (centre + size).
    remaining = list(non_clusters)
    for (px, py, pw, ph) in placed:
        pcx, pcy = px + pw / 2.0, py + ph / 2.0
        matches = []
        for piece in remaining:
            bx, by, bw, bh = piece["bbox"]
            bcx, bcy = bx + bw / 2.0, by + bh / 2.0
            if abs(bcx - pcx) <= _CENTER_TOL and abs(bcy - pcy) <= _CENTER_TOL:
                matches.append(piece)
        assert len(matches) == 1, (
            f"rectangle at ({px},{py}) matched {len(matches)} detections"
        )
        matched = matches[0]
        bx, by, bw, bh = matched["bbox"]
        # Detected bbox should be the placed size plus at most a few px of padding.
        assert abs(bw - pw) <= _SIZE_TOL
        assert abs(bh - ph) <= _SIZE_TOL
        assert bw >= pw - 2 and bh >= ph - 2
        remaining.remove(matched)

    assert remaining == []


@pytest.mark.parametrize("segment", [segment_pieces, segment_scan], ids=["segment_pieces", "segment_scan"])
def test_piece_near_frame_is_kept(segment):
    """A piece next to (or touching) the image border is kept, not silently dropped (S1).

    One rectangle sits 2 px from the right border (kept, ``touches_frame`` False);
    another touches the bottom border (kept, ``touches_frame`` True, not a cluster).
    Runs on both the photo path and the scan path (which reuses segment_pieces'
    separation and must carry its ``touches_frame``; every scan piece is refined).
    """
    bg = np.full((_IMG_H, _IMG_W, 3), _BG, dtype=np.uint8)
    inset = [(80, 90, 150, 120, (200, 40, 40)), (400, 70, 150, 120, (40, 160, 40)),
             (120, 380, 150, 120, (210, 170, 30))]
    near = (_IMG_W - 2 - 150, 300, 150, 120, (40, 60, 200))   # bbox 2 px from the right edge
    touch = (450, _IMG_H - 120, 150, 120, (150, 40, 170))     # bbox reaches the bottom edge
    for (x, y, w, h, colour) in inset + [near, touch]:
        bg[y:y + h, x:x + w] = colour
    result = segment(Image.fromarray(bg))

    assert "error" not in result, result.get("error")
    assert result["count"] == 5
    if segment is segment_scan:
        assert result["method"] == "scan"
        assert all(p["refined"] for p in result["pieces"])
    assert all("touches_frame" in p for p in result["pieces"])

    def _find(rect):
        x, y, w, h = rect[:4]
        cx, cy = x + w / 2.0, y + h / 2.0
        hits = [p for p in result["pieces"]
                if abs(p["bbox"][0] + p["bbox"][2] / 2.0 - cx) <= _CENTER_TOL
                and abs(p["bbox"][1] + p["bbox"][3] / 2.0 - cy) <= _CENTER_TOL]
        assert len(hits) == 1, f"rectangle at ({x},{y}) matched {len(hits)} detections"
        return hits[0]

    p_near = _find(near)
    assert p_near["touches_frame"] is False
    assert p_near["is_cluster"] is False

    p_touch = _find(touch)
    assert p_touch["touches_frame"] is True
    assert p_touch["is_cluster"] is False

    for rect in inset:
        assert _find(rect)["touches_frame"] is False


@pytest.mark.parametrize("segment", [segment_pieces, segment_scan], ids=["segment_pieces", "segment_scan"])
def test_piece_touching_white_scan_strip_is_kept(segment):
    """A piece abutting the white paper strip at the scan edge is kept (defect S3).

    On a flatbed scan the coloured paper often does not cover the full glass, leaving
    a near-white strip along one edge. That strip is foreground against the green
    background; a piece touching it used to merge with it and the merged component was
    dropped (bbox aspect / frame-blob gates). Scene: green background, a full-height
    white band on the right, one rectangle abutting the band and four away from it.
    The abutting piece must be found with ``touches_strip`` True and ``touches_frame``
    False (it does not reach the real image border); the others ``touches_strip`` False.
    """
    green, white = (40, 160, 60), (245, 245, 245)
    band_w = 60
    bg = np.full((_IMG_H, _IMG_W, 3), green, dtype=np.uint8)
    bg[:, _IMG_W - band_w:] = white
    away = [(80, 90, 150, 120, (200, 40, 40)), (400, 70, 150, 120, (40, 60, 200)),
            (120, 380, 150, 120, (210, 170, 30)), (400, 420, 150, 120, (150, 40, 170))]
    abut = (_IMG_W - band_w - 150, 260, 150, 120, (200, 90, 40))   # right side touches the band
    for (x, y, w, h, colour) in away + [abut]:
        bg[y:y + h, x:x + w] = colour
    result = segment(Image.fromarray(bg))

    assert "error" not in result, result.get("error")
    assert result["count"] == 5, f"count {result['count']}"
    assert all("touches_strip" in p for p in result["pieces"])

    def _find(rect):
        x, y, w, h = rect[:4]
        cx, cy = x + w / 2.0, y + h / 2.0
        hits = [p for p in result["pieces"]
                if abs(p["bbox"][0] + p["bbox"][2] / 2.0 - cx) <= _CENTER_TOL
                and abs(p["bbox"][1] + p["bbox"][3] / 2.0 - cy) <= _CENTER_TOL]
        assert len(hits) == 1, f"rectangle at ({x},{y}) matched {len(hits)} detections"
        return hits[0]

    p_abut = _find(abut)
    assert p_abut["touches_strip"] is True
    assert p_abut["touches_frame"] is False
    assert p_abut["is_cluster"] is False
    for rect in away:
        p = _find(rect)
        assert p["touches_strip"] is False
        assert p["touches_frame"] is False
    assert result["frame_strip"] is not None
    assert result["frame_strip"]["side"] == "right"


# ---------------------------------------------------------------- contact groups (interlocked pieces)
def _match_gt(result, gts):
    """For each GT mask, the segment_scan piece with the highest IoU and that IoU."""
    from synth import mask_iou
    out = []
    for gt in gts:
        best = max(result["pieces"], key=lambda p: mask_iou(p["contour"], gt))
        out.append((best, mask_iou(best["contour"], gt)))
    return out


def test_segment_scan_interlocked_tab_with_gap():
    """A tab inside the neighbour's blank, 1 px of background around it, is given back to its piece.

    Synthetic 300 dpi scan on the project green (tests/synth.interlocked_scan): the low-res
    separation plus the Voronoi-cell boundary used to hand the tab to the neighbour (a false
    flat side on the owner). With the contact step both pieces are recovered (IoU >= 0.95),
    neither has an F side, and both carry ``contacto``.
    """
    from synth import interlocked_scan
    from src.shape import analyse
    img, gts = interlocked_scan(gap_px=1)
    result = segment_scan(img, dpi=300, normalize_rotation=False)
    assert "error" not in result, result.get("error")
    assert result["count"] == 4
    (pa, ia), (pb, ib) = _match_gt(result, gts[:2])
    assert pa["index"] != pb["index"]
    assert ia >= 0.95 and ib >= 0.95, (ia, ib)
    for p in (pa, pb):
        s = analyse(p["contour"], result["mm_per_px"])
        assert s.ok and s.n_flat == 0, (s.cls, s.lens)
        assert p["contacto"]["com"] == [(pb if p is pa else pa)["index"]]
        assert p["is_cluster"] is False


def test_segment_scan_interlocked_tab_touching():
    """Same pair with no gap at all: either recovered (IoU >= 0.95) or both flagged ``contacto`` baixa."""
    from synth import interlocked_scan
    img, gts = interlocked_scan(gap_px=0)
    result = segment_scan(img, dpi=300, normalize_rotation=False)
    assert "error" not in result, result.get("error")
    assert result["count"] == 4
    (pa, ia), (pb, ib) = _match_gt(result, gts[:2])
    good = pa["index"] != pb["index"] and ia >= 0.95 and ib >= 0.95
    flagged = all((p.get("contacto") or {}).get("confianca") == "baixa" for p in (pa, pb))
    assert good or flagged, (ia, ib, pa.get("contacto"), pb.get("contacto"))


def test_segment_scan_split_contacts_no_effect_when_separated():
    """Well-separated pieces: the contact step changes nothing and flags nothing."""
    from synth import interlocked_scan
    img, _ = interlocked_scan(gap_px=1, body_gap_mm=9.0)
    on = segment_scan(img, dpi=300, normalize_rotation=False)
    off = segment_scan(img, dpi=300, normalize_rotation=False, split_contacts=False)
    assert on["count"] == off["count"] == 4
    for a, b in zip(on["pieces"], off["pieces"]):
        assert "contacto" not in a
        assert np.array_equal(np.asarray(a["contour"]), np.asarray(b["contour"]))
        assert tuple(a["bbox"]) == tuple(b["bbox"])


def test_ingest_propagates_contacto(tmp_path):
    """``ingest_scan`` copies ``contacto`` into the piece flags (the overlay draws ``baixa`` in red)."""
    from synth import interlocked_scan
    from src.ingest import COL_CONTACT_LOW, _piece_colour, ingest_scan
    from src.profile import PuzzleProfile
    from src.state import Project
    img, _ = interlocked_scan(gap_px=0)
    scan = tmp_path / "scan.png"
    img.save(scan)
    pp = tmp_path / "puzzle.json"
    PuzzleProfile(id="t", grid={"cols": 6, "rows": 4}, symmetry={"type": "rot180"}).save(str(pp))
    pr = Project.create(str(tmp_path / "proj"), str(pp))
    r = ingest_scan(pr, str(scan), 1)
    assert "error" not in r, r
    pr = Project.open(str(tmp_path / "proj"))
    flagged = [p for p in pr.pieces.values() if p.flags.get("contacto")]
    assert len(flagged) == 2
    idx = {p.index_in_scan for p in flagged}
    for p in flagged:
        c = p.flags["contacto"]
        assert c["com"] == sorted(idx - {p.index_in_scan})
        assert c["confianca"] in ("alta", "baixa")
        if c["confianca"] == "baixa" and not p.flags.get("objeto_duplo"):
            assert _piece_colour(p) == COL_CONTACT_LOW
    assert os.path.exists(pr.p("overlays", "S0001.jpg"))
