"""Anti-regression test for :func:`src.matching.multi_scale_template_match`.

Self-recovery: a known textured region is cropped straight out of the reference
photo and handed back to the engine as the "piece". A correct engine must place
that crop back at (approximately) the coordinates it was taken from, and -- since
an exact self-crop of a detailed region has an overwhelmingly dominant match --
report ``confidence == 'high'``.

Region choice (documented): the autumn-foliage tree, a strongly multi-coloured,
high-detail area at full-res crop origin (4450, 3450) with side 700 px on the
8064x6048 reference. It clears both confidence gates comfortably (measured
structure ~6.8 vs the 4.0 gate, cost gap ~0.92 vs the 0.12 gate) and localises to
within ~17 px of truth. ``num_pieces`` is chosen so the expected piece side
(sqrt(W*H / num_pieces)) equals the crop side, i.e. num_pieces = W*H / side**2, so
the engine's ~1.0 scale band brackets the true scale.
"""

import os

import pytest
from PIL import Image

from src.matching import multi_scale_template_match


_PUZZLE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "images", "puzzles", "PuzzleOriginal.jpeg",
)

# Textured self-crop: origin (x, y) and side length, in full-res reference pixels.
_CROP_X = 4450
_CROP_Y = 3450
_CROP_SIDE = 700


@pytest.fixture(scope="module")
def puzzle_image():
    if not os.path.exists(_PUZZLE_PATH):
        pytest.skip(f"reference image not found: {_PUZZLE_PATH}")
    with Image.open(_PUZZLE_PATH) as im:
        return im.convert("RGB")


def test_self_crop_recovers_position_and_high_confidence(puzzle_image):
    puzzle = puzzle_image
    W, H = puzzle.size

    crop = puzzle.crop((_CROP_X, _CROP_Y, _CROP_X + _CROP_SIDE, _CROP_Y + _CROP_SIDE))
    num_pieces = round((W * H) / float(_CROP_SIDE * _CROP_SIDE))
    expected_side = (W * H / float(num_pieces)) ** 0.5

    result = multi_scale_template_match(
        puzzle, crop, num_pieces=num_pieces,
        use_texture=True, piece_mask=None, piece_edges=None,
    )

    assert "error" not in result, result.get("error")

    bx, by = result["best_position"]
    err = ((bx - _CROP_X) ** 2 + (by - _CROP_Y) ** 2) ** 0.5
    # The search runs on a heavy downscale (one piece ~46 px) then refines at
    # stride 1, so a few search-pixels of slack map back to some full-res px.
    # A quarter of a piece side is a generous-yet-meaningful bound (measured ~17 px).
    tol = 0.25 * expected_side
    assert err <= tol, f"position error {err:.0f}px exceeds tolerance {tol:.0f}px"

    # An exact self-crop of a detailed, multi-coloured region must be unambiguous.
    assert result["confidence"] == "high", result.get("confidence_reason")
    assert result["confidence_gap"] > 0.12
    assert result["piece_structure"] >= 4.0
