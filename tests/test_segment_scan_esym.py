"""Regression test for :func:`src.segmentation.segment_scan` on the E-sym twin scans.

Three real 300 dpi scans of the same 20 border pieces of the top edge (2026-10-30,
see images/pieces/gemeos_2026-10-30.md): A1 (sheet A), A2 (sheet A rotated 180 deg on
the glass) and B2 (sheet B = the 180 deg twins, rotated). Ground truth by grid
position: A(f, k) <-> B2(f, 4 - k) are twins; A1(f, k) <-> A2(f, k) is a re-scan.

The shape metric is the corner-free distance :func:`src.shape.free_dist` (promoted
from the E-sym diagnostic tools/diagnostico/forma/dist.free_dist): contour smoothed
with a circular Gaussian (sigma 1.5 samples), resampled to 512 equidistant points,
centred, as complex numbers; RMS (mm) minimised over cyclic shift and rotation via
FFT. Contours are converted to mm with ``segment_scan(...)['mm_per_px']``.

Thresholds (docs/diagnostico/gemeos/RESULTADOS.md, update 2026-10-31): median
free RMS of the opposite-pose twins A2/B2 <= 0.5 mm (measured 0.38) and top-1
20/20 for A1->B2, A2->B2 and B2->A2.
"""

import os

import numpy as np
import pytest
from PIL import Image

from conftest import REPO_ROOT
from src.segmentation import segment_scan
from src.shape import analyse, free_dist

pytestmark = pytest.mark.slow

_SCANS = {
    "A1": "images/pieces/coluna5-24_300dpi_folhaA.jpg",
    "A2": "images/pieces/colunas5-24_300dpi_rot180_folhaA.jpg",
    "B2": "images/pieces/coluna5-24_folhaB_300dpi_rot180.jpg",
}
_MISSING = [p for p in _SCANS.values() if not os.path.exists(os.path.join(REPO_ROOT, p))]
if _MISSING:
    pytest.skip(f"E-sym scans missing: {_MISSING}", allow_module_level=True)

_TWIN_MEDIAN_MAX_MM = 0.5


def _grid_order(bboxes):
    """Indices in (row, x) order: rows split where the centre-y gap > 0.5 x median height."""
    b = np.asarray(bboxes, float)
    cy = b[:, 1] + b[:, 3] / 2
    cx = b[:, 0] + b[:, 2] / 2
    o = np.argsort(cy)
    hmed = np.median(b[:, 3])
    rows, cur = [], [o[0]]
    for i in o[1:]:
        if cy[i] - cy[cur[-1]] > 0.5 * hmed:
            rows.append(cur)
            cur = [i]
        else:
            cur.append(i)
    rows.append(cur)
    return [int(i) for r in rows for i in sorted(r, key=lambda j: cx[j])], [len(r) for r in rows]


@pytest.fixture(scope="module")
def scans():
    out = {}
    for name, rel in _SCANS.items():
        with Image.open(os.path.join(REPO_ROOT, rel)) as im:
            im.load()
            res = segment_scan(im)
        assert "error" not in res, (name, res.get("error"))
        assert res["method"] == "scan"
        pieces = res["pieces"]
        order, rows = _grid_order([p["bbox"] for p in pieces])
        pieces = [pieces[i] for i in order]
        shapes = [analyse(p["contour"], res["mm_per_px"]) for p in pieces]
        out[name] = dict(res=res, pieces=pieces, shapes=shapes, rows=rows)
    return out


def _twin(i):
    f, k = divmod(i, 5)
    return 5 * f + (4 - k)


def test_counts_and_grid(scans):
    for name, s in scans.items():
        pieces = s["pieces"]
        assert len(pieces) == 20, (name, len(pieces))
        assert sum(p["is_cluster"] for p in pieces) == 0, name
        assert s["rows"] == [5, 5, 5, 5], (name, s["rows"])
        assert all(p["refined"] for p in pieces), name
        assert all("touches_frame" in p and "roughness" in p for p in pieces), name


def test_twins_by_free_shape(scans):
    Z = {n: scans[n]["shapes"] for n in _SCANS}
    M = {(a, b): np.array([[free_dist(x, y)[0] for y in Z[b]] for x in Z[a]])
         for a, b in [("A1", "B2"), ("A2", "B2"), ("A1", "A2")]}
    T = np.array([_twin(i) for i in range(20)])
    ar = np.arange(20)
    tw22 = M[("A2", "B2")][ar, T]
    top_a1 = int(np.sum(M[("A1", "B2")].argmin(1) == T))
    top_a2 = int(np.sum(M[("A2", "B2")].argmin(1) == T))
    # B2 j -> its twin in A2 is A2[_twin(j)] (the map is an involution)
    top_b2 = int(np.sum(M[("A2", "B2")].argmin(0) == T))
    rough = {n: float(np.median([p["roughness"] for p in scans[n]["pieces"]])) for n in _SCANS}
    chords = []
    for n in _SCANS:
        for s in scans[n]["shapes"]:
            if s.ok:
                chords += s.lens
    diag = (f"twin A2/B2 median {np.median(tw22):.3f} mm, A1/B2 {np.median(M[('A1', 'B2')][ar, T]):.3f}, "
            f"rescan A1/A2 {np.median(M[('A1', 'A2')][ar, ar]):.3f}; top-1 A1->B2 {top_a1}, A2->B2 {top_a2}, "
            f"B2->A2 {top_b2}; roughness medians {rough}; side chord median {np.median(chords):.2f} mm")
    print(diag)
    assert np.median(tw22) <= _TWIN_MEDIAN_MAX_MM, diag
    assert top_a1 == 20, diag
    assert top_a2 == 20, diag
    assert top_b2 == 20, diag
