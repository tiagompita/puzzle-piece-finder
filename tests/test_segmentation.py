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


def test_segment_scan_recovers_eaten_meadow_corner():
    """A paper-like patch at a body corner, cut by the band without the step, is grown back with it.

    tests/synth.meadow_scan: the low-res separation sees the light patch as background and the
    1.5 mm band keeps only a rim of it (IoU < 0.97, the top chord short); with ``recover_bays``
    the piece matches its GT (IoU >= 0.99), carries ``recuperado_mm2`` and keeps its 4 sides.
    """
    from synth import meadow_scan
    from src.shape import analyse
    img, gts, patch = meadow_scan()
    off = segment_scan(img, dpi=300, normalize_rotation=False, recover_bays=False)
    on = segment_scan(img, dpi=300, normalize_rotation=False, recover_bays=True)
    assert off["count"] == on["count"] == 4
    (pa_off, ia_off), = _match_gt(off, gts[:1])
    (pa_on, ia_on), = _match_gt(on, gts[:1])
    assert pa_off["index"] == pa_on["index"]
    assert ia_off < 0.97, ia_off
    assert "recuperado_mm2" not in pa_off
    assert ia_on >= 0.99, ia_on
    patch_mm2 = float(patch.sum()) * on["mm_per_px"] ** 2
    assert 0.5 * patch_mm2 <= pa_on["recuperado_mm2"] <= 1.2 * patch_mm2, (pa_on["recuperado_mm2"], patch_mm2)
    s = analyse(pa_on["contour"], on["mm_per_px"])
    assert s.ok and s.cls == analyse(_match_gt(on, gts[1:2])[0][0]["contour"], on["mm_per_px"]).cls
    assert min(s.lens) > 17.5, s.lens


def test_segment_scan_recover_bays_keeps_blanks():
    """Real blanks are background in the threshold: pieces without a patch are not touched."""
    import cv2
    from synth import meadow_scan
    img, gts, _ = meadow_scan()
    off = segment_scan(img, dpi=300, normalize_rotation=False, recover_bays=False)
    on = segment_scan(img, dpi=300, normalize_rotation=False, recover_bays=True)
    for (p_off, _), (p_on, i_on) in zip(_match_gt(off, gts[1:]), _match_gt(on, gts[1:])):
        assert "recuperado_mm2" not in p_on
        assert np.array_equal(np.asarray(p_off["contour"]), np.asarray(p_on["contour"]))
        assert i_on >= 0.99, i_on
    # The patched piece keeps its two blanks open: nothing outside its GT mask is added.
    (pa, _), = _match_gt(on, gts[:1])
    m = np.zeros(gts[0].shape, np.uint8)
    cv2.drawContours(m, [np.asarray(pa["contour"]).astype(np.int32).reshape(-1, 1, 2)], -1, 1, thickness=cv2.FILLED)
    outside_mm2 = float(((m > 0) & ~gts[0]).sum()) * on["mm_per_px"] ** 2
    assert outside_mm2 < 2.0, outside_mm2


def test_segment_scan_recover_bays_module_switch(monkeypatch):
    """``recover_bays=None`` follows the module switch ``_RECOVER_BAYS``."""
    from synth import meadow_scan
    import src.segmentation as SEG
    img, gts, _ = meadow_scan()
    monkeypatch.setattr(SEG, "_RECOVER_BAYS", False)
    (p, _), = _match_gt(segment_scan(img, dpi=300, normalize_rotation=False), gts[:1])
    assert "recuperado_mm2" not in p
    monkeypatch.setattr(SEG, "_RECOVER_BAYS", True)
    (p, _), = _match_gt(segment_scan(img, dpi=300, normalize_rotation=False), gts[:1])
    assert p.get("recuperado_mm2", 0) > 0


# ---------------------------------------------------------------- contact trim and suspect cuts (CONTACTOS.md §6)
def test_contact_trim_returns_shadow_tongue_to_the_tab():
    """The cast shadow under a tab, handed by the flood to the neighbour, goes back to the tab's piece.

    tests/synth.contact_tongue_labels: S0023 #3/#4 as a label image, the shadow under A's tab
    (1.2 mm thick) plus a dark thread of 0.2 mm x 4 mm leaving the junction, both labelled B.
    The spur step of the previous code (opening 0.5 mm) left 97 % of it to B; with the contact
    trim (_CONTACT_TRIM) at most 25 % stays with B (the part against B's side), most goes to A,
    and neither body loses more than 0.1 mm^2.
    """
    import src.segmentation as SEG
    from synth import MMPP, contact_tongue_labels
    lbl, tongue, (a, b) = contact_tongue_labels(tongue_mm=1.2, thread_mm=0.2)
    new, dropped = SEG._contact_trim(lbl, 2, MMPP)
    mm2 = MMPP * MMPP
    t = float(tongue.sum())
    in_b = float(((new == 2) & tongue).sum())
    in_a = float(((new == 1) & tongue).sum())
    assert in_b <= 0.25 * t, (in_b * mm2, t * mm2)
    assert in_a >= 0.6 * t, (in_a * mm2, t * mm2)
    assert float(((new != 1) & a).sum()) * mm2 < 0.1
    assert float(((new != 2) & b).sum()) * mm2 < 0.1
    assert not (dropped & (a | b)).any() or float((dropped & (a | b)).sum()) * mm2 < 0.1


def test_contact_trim_switch_off_is_previous_spur_step(monkeypatch):
    """With ``_CONTACT_TRIM`` off the step is the previous spur opening (_CONTACT_SPUR_MM), nothing dropped."""
    import src.segmentation as SEG
    from synth import MMPP, contact_tongue_labels
    lbl, _, _ = contact_tongue_labels()
    monkeypatch.setattr(SEG, "_CONTACT_TRIM", False)
    off, dropped = SEG._contact_trim(lbl, 2, MMPP)
    ref, _ = SEG._trim_contact_labels(lbl, 2, MMPP, SEG._CONTACT_SPUR_MM)
    assert np.array_equal(off, ref)
    assert not dropped.any()


def test_appendage_measures_thread_not_corners():
    """``_appendage``: a square piece has none (corner tips < 2 mm); a 0.8 mm x 4 mm thread is measured."""
    import cv2
    import src.segmentation as SEG
    from synth import MMPP
    side = int(round(18.5 / MMPP))
    sq = np.array([(50, 50), (50 + side, 50), (50 + side, 50 + side), (50, 50 + side)], np.int32)
    length, _ = SEG._appendage(sq, MMPP)
    assert length < SEG._SUSPECT_SPUR_LEN_MM, length
    m = np.zeros((side + 200, side + 200), np.uint8)
    cv2.fillPoly(m, [sq.reshape(-1, 1, 2)], 1)
    tw, tl = int(round(0.8 / MMPP)), int(round(4.0 / MMPP))
    m[50 + side // 2:50 + side // 2 + tw, 50 + side:50 + side + tl] = 1
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    length, area = SEG._appendage(max(cnts, key=cv2.contourArea).reshape(-1, 2), MMPP)
    assert 3.5 <= length <= 4.6, length
    assert area > 2.0, area


@pytest.mark.slow
def test_segment_scan_s0023_pair_without_tongue():
    """Real sheet S0023 (montado_p15): #3/#4 (index 2/3, P0777/P0778) cut without tongue or wedge.

    Before the contact trim P0778 carried the shadow under P0777's tab (appendage 3.43 mm), P0777 a
    wedge of halo (2.90 mm) and the facing sides did not mate (side_complement RMS 3.76 mm); both
    are flagged ``suspeita_recorte`` with the trim off. With the trim: appendage < 2 mm, RMS < 2 mm,
    no flag.
    """
    import src.segmentation as SEG
    from conftest import REPO_ROOT
    fp = os.path.join(REPO_ROOT, "images", "pieces", "legado", "montado_p15_300dpi.jpg")
    if not os.path.exists(fp):
        pytest.skip("montado_p15 em falta")
    with Image.open(fp) as im:
        photo = im.convert("RGB")
    res = segment_scan(photo, dpi=300, normalize_rotation=False)
    a, b = res["pieces"][2], res["pieces"][3]
    assert a["contacto"]["metodo"] == "watershed" and a["contacto"]["com"] == [3]
    for p in (a, b):
        assert "suspeita_recorte" not in p, p.get("suspeita_recorte")
        assert SEG._appendage(p["contour"], res["mm_per_px"])[0] < SEG._SUSPECT_SPUR_LEN_MM
    _, info = SEG._shape_violations([a["contour"], b["contour"]], res["mm_per_px"], True)
    assert info[0]["face"]["kinds"] in ("TB", "BT") and info[0]["face"]["rms_mm"] < SEG._SUSPECT_FACE_RMS_MM


# ---------------------------------------------------------------- whole tab outside the contour (COMIDO.md §10)
_MM = 25.4 / 300


def _tab_scene(tab=True, strip=False):
    """Window masks: a 220 px square body (contour = body only) and the threshold = body + a tab
    (neck 50 px wide, head disc r 23 px) sticking 65 px (5.5 mm) out of the top side, beyond the minAreaRect;
    or a 7 px (0.6 mm) cast-shadow strip along the right side."""
    import cv2
    h = w = 500
    thr = np.zeros((h, w), np.uint8)
    x0, y0, s = 140, 160, 220
    thr[y0:y0 + s, x0:x0 + s] = 1
    if tab:
        cx = x0 + s // 2
        thr[y0 - 40:y0, cx - 25:cx + 25] = 1
        cv2.circle(thr, (cx, y0 - 42), 23, 1, -1)
    if strip:
        thr[y0 + 20:y0 + s - 20, x0 + s:x0 + s + 7] = 1
    c = np.array([[x0, y0], [x0 + s - 1, y0], [x0 + s - 1, y0 + s - 1], [x0, y0 + s - 1]], np.int32)
    return c, thr


def test_recover_bay_contour_takes_back_a_whole_tab_only_with_tabs():
    from src import segmentation as SEG
    c, thr = _tab_scene()
    assert SEG._recover_bay_contour(c, thr, (0, 0), _MM, tabs=False) is None          # the rectangle rule cannot
    out = SEG._recover_bay_contour(c, thr, (0, 0), _MM, tabs=True)
    assert out is not None
    new_c, gain = out
    tab_px = float(thr.sum()) - 220 * 220
    assert abs(gain - tab_px) <= 0.03 * tab_px
    assert new_c[:, 1].min() <= 160 - 65 + 2                                           # reaches the tab tip


def test_recover_bay_contour_tabs_leave_a_shadow_strip():
    from src import segmentation as SEG
    c, thr = _tab_scene(tab=False, strip=True)
    assert SEG._recover_bay_contour(c, thr, (0, 0), _MM, tabs=True) is None


def test_flag_suspect_cuts_reason_baia():
    from src import segmentation as SEG
    c, thr = _tab_scene()
    pieces = [{"index": 0, "contour": c, "is_cluster": False}]
    SEG._flag_suspect_cuts(pieces, _MM, thr * 255)
    fl = pieces[0]["suspeita_recorte"]
    assert "baia" in fl["razoes"] and fl["baia_r_mm"] > SEG._BAY_FLAG_RIN_MM and fl["baia_mm2"] > 15
    c2, thr2 = _tab_scene(tab=False, strip=True)
    pieces = [{"index": 0, "contour": c2, "is_cluster": False}]
    SEG._flag_suspect_cuts(pieces, _MM, thr2 * 255)
    assert "suspeita_recorte" not in pieces[0]
