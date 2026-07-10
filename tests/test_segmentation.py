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

import numpy as np
from PIL import Image

from src.segmentation import segment_pieces


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
