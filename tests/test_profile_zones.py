"""Image zones of the puzzle profile: row bands with a p90 and a label (R7_CRITERIOS §4.2)."""

import os

import pytest

from src import fit
from src.profile import PuzzleProfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _prof(zones, rows=10, cols=4):
    return PuzzleProfile(id="z", grid={"cols": cols, "rows": rows}, symmetry={"type": "rot180"}, image_zones=zones)


ZONES = {"a": {"rows": [1, 3], "dE_p90": 20.0, "rotulo": "alto"},
         "b": {"rows": [4, 10], "dE_p90": None},
         "nota": "texto livre"}


def test_zone_of_and_label():
    p = _prof(ZONES)
    assert p.has_zone_rows()
    assert p.zone_of(1, 1) == "a" and p.zone_of(3, 4) == "a" and p.zone_of(4, 1) == "b" and p.zone_of(10, 2) == "b"
    assert p.zone_label("a") == "alto" and p.zone_label("b") == "b" and p.zone_label(None) is None
    assert set(p.zones()) == {"a", "b"}                        # the 'nota' string is not a zone
    with pytest.raises(ValueError):
        p.zone_of(11, 1)


def test_zone_of_without_rows():
    p = _prof({"ceu": {"dE_p90": 50.0}})
    assert not p.has_zone_rows() and p.zone_of(1, 1) is None
    assert _prof({}).zone_of(5, 2) is None
    # a gap between bands -> None
    assert _prof({"a": {"rows": [1, 2]}, "b": {"rows": [5, 6]}}).zone_of(3, 1) is None


@pytest.mark.parametrize("zones", [
    {"a": {"rows": [1, 5]}, "b": {"rows": [5, 8]}},           # overlap
    {"a": {"rows": [0, 3]}},                                   # outside the grid
    {"a": {"rows": [3, 11]}},
    {"a": {"rows": [4, 2]}},                                   # reversed
    {"a": {"rows": [1, 2, 3]}},
    {"a": {"rows": [1.5, 3]}},
])
def test_rows_validation(zones):
    with pytest.raises(ValueError):
        _prof(zones)


def test_round_trip(tmp_path):
    p = _prof(ZONES)
    fp = tmp_path / "puzzle.json"
    p.save(str(fp))
    q = PuzzleProfile.load(str(fp))
    assert q.image_zones == ZONES and q.zone_of(2, 2) == "a"


def test_alpes_profile_zones_match_fit_bands():
    p = PuzzleProfile.load(os.path.join(REPO, "projects", "alpes", "puzzle.json"))
    assert p.zone_of(35, 2) == "vale" and p.zone_label("vale") == "vale/aldeia"
    assert p.zone_of(41, 62) == "relva" and p.zone_of(4, 63) == "ceu"
    assert p.image_zones["ceu"]["dE_p90"] == 50.0
    assert all(p.image_zones[z]["dE_p90"] is None for z in ("montanha", "vale", "relva"))
    for l in range(1, p.rows + 1):
        assert fit.zone_of((l, 10), p) == fit.zone_of((l, 10)), l     # same labels as the fixed ZONES
    assert fit.zone_of(None, p) == "sem posição"
    # a profile without row zones falls back to the fixed bands
    assert fit.zone_of((45, 2), _prof({"ceu": {"dE_p90": 50.0}}, rows=47, cols=64)) == "relva"
