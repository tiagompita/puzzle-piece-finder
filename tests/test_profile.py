"""Tests for :mod:`src.profile` (puzzle profile and the only symmetry implementation)."""

import os

import numpy as np
import pytest

from conftest import REPO_ROOT
from src.profile import PuzzleProfile

ALPES = os.path.join(REPO_ROOT, "projects", "alpes", "puzzle.json")


@pytest.fixture(scope="module")
def alpes():
    return PuzzleProfile.load(ALPES)


def test_load_alpes(alpes):
    assert alpes.id == "alpes"
    assert (alpes.cols, alpes.rows) == (64, 47)
    assert alpes.cell_count() == 3008
    assert alpes.twin_rotation_deg() == 180
    assert alpes.mm_per_px() == pytest.approx(25.4 / 300)
    assert alpes.calibration["silhueta_silhueta"]["t95"] == pytest.approx(0.507)


def test_rot180_twin(alpes):
    assert alpes.twin(1, 29) == (47, 36)
    rng = np.random.default_rng(0)
    for _ in range(20):
        l, c = int(rng.integers(1, 48)), int(rng.integers(1, 65))
        t = alpes.twin(l, c)
        assert alpes.in_grid(*t)
        assert t != (l, c)
        assert alpes.twin(*t) == (l, c)
    with pytest.raises(ValueError):
        alpes.twin(0, 1)


def test_translate_and_none():
    p = PuzzleProfile(id="t", grid={"cols": 64, "rows": 47}, symmetry={"type": "translate", "cols": 32})
    assert p.twin(1, 5) == (1, 37)
    assert p.twin(1, 40) == (1, 8)
    assert p.twin_rotation_deg() == 0
    q = PuzzleProfile(id="n", grid={"cols": 4, "rows": 3}, symmetry={"type": "none"})
    assert q.twin(2, 2) is None
    with pytest.raises(ValueError):
        PuzzleProfile(id="x", symmetry={"type": "mirror"})


def test_border_geometry(alpes):
    assert alpes.flat_directions(1, 1) == {"N", "W"}
    assert alpes.flat_directions(47, 64) == {"S", "E"}
    assert alpes.n_flat_sides(47, 36) == 1
    assert alpes.is_border(2, 2) is False
    assert alpes.is_corner(1, 64) and not alpes.is_corner(1, 2)
    n_border = sum(alpes.is_border(l, c) for l in range(1, 48) for c in range(1, 65))
    assert n_border == 2 * 64 + 2 * 47 - 4  # 218


def test_save_load_round_trip(alpes, tmp_path):
    out = tmp_path / "puzzle.json"
    alpes.save(str(out))
    again = PuzzleProfile.load(str(out))
    assert again == alpes
    assert again.to_dict() == alpes.to_dict()
    assert PuzzleProfile.from_dict(alpes.to_dict()) == alpes
    # the art registration (src/artreg.py) survives the round trip and is what art_matrix() returns
    assert np.allclose(again.art_matrix(), alpes.art_matrix())
    if "registration" in alpes.art:
        assert np.allclose(alpes.art_matrix(), alpes.art["registration"]["matrix"])
