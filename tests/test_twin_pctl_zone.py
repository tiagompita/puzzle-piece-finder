"""``find_twin``: the informative percentile is opt-in (``pctl``) and the image threshold follows the zone of the
twin cell (R7_CRITERIOS §4.2, §5). Same synthetic world as ``tests/test_twin.py`` (solid-colour art, 6 x 8)."""

import pytest

from src.profile import PuzzleProfile
from src.twin import _image_threshold, find_twin
from test_twin import _decoys_img, _image_world, _item

import numpy as np


def _world():
    prof, rgb, art, q, tw, tcell = _image_world({"type": "rot180"})
    rng = np.random.default_rng(9)
    pool = [_item(rgb, "T", tw, tcell, 90.0)] + _decoys_img(rgb, 20, rng, [(3, 3), (4, 5), (5, 2)])
    return prof, art, q, tcell, pool


def _zoned(prof, vale_p90=None):
    d = prof.to_dict()
    d["image_zones"] = {"ceu": {"rows": [1, 3], "dE_p90": 15.0, "rotulo": "céu"},
                        "vale": {"rows": [4, 6], "dE_p90": vale_p90, "rotulo": "vale/aldeia"},
                        "nota": "teste"}
    return PuzzleProfile.from_dict(d)


def test_pctl_off_by_default():
    prof, art, q, tcell, pool = _world()
    res = find_twin(q, pool, profile=prof, art=art)
    assert res["decision"] == "aceite", res["reasons"]
    im = res["candidates"][0]["image"]
    assert im["dE"] < 3.0 and im["pctl"] is None
    assert not any("pct" in r for r in res["reasons"]), res["reasons"]


def test_pctl_on_request():
    prof, art, q, tcell, pool = _world()
    res = find_twin(q, pool, profile=prof, art=art, pctl=True)
    assert res["candidates"][0]["image"]["pctl"] == pytest.approx(0.0)
    assert any("pct 0,0 %" in r for r in res["reasons"]), res["reasons"]


def test_zone_without_p90_never_accepts():
    prof, art, q, tcell, pool = _world()
    zp = _zoned(prof)
    assert tcell == (5, 7) and zp.zone_of(*tcell) == "vale"
    res = find_twin(q, pool, profile=zp, art=art, zone="vale")
    assert res["decision_shape"] == "aceite" and res["decision"] == "ambigua", res["reasons"]
    assert res["candidates"][0]["image"]["dE"] < 3.0          # the image agrees, but it does not decide here
    assert any(r.startswith("zona vale/aldeia sem p90 calibrado: a imagem não decide") for r in res["reasons"]), res["reasons"]
    # a calibrated zone decides and the reason names the true zone
    zp2 = _zoned(prof, vale_p90=15.0)
    res2 = find_twin(q, pool, profile=zp2, art=art, zone="vale")
    assert res2["decision"] == "aceite"
    assert any(r.startswith("imagem consistente:") and "(vale/aldeia)" in r for r in res2["reasons"]), res2["reasons"]


def test_zone_none_keeps_largest_p90_fallback():
    prof, art, q, tcell, pool = _world()
    zp = _zoned(prof)
    res = find_twin(q, pool, profile=zp, art=art)              # caller without zones: legacy fallback (céu 15)
    assert res["decision"] == "aceite", res["reasons"]
    assert any("(céu)" in r for r in res["reasons"]), res["reasons"]


def test_image_threshold_rules():
    prof, *_ = _world()
    zp = _zoned(prof)
    assert _image_threshold(zp, "ceu") == (15.0, "ceu")
    assert _image_threshold(zp, "vale") == (None, "vale")
    assert _image_threshold(zp, "inexistente") == (None, "inexistente")
    assert _image_threshold(zp, None) == (15.0, "ceu")           # the 'nota' string is skipped
    assert _image_threshold(_zoned(prof, vale_p90=40.0), None) == (40.0, "vale")
