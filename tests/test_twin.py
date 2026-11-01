"""Synthetic tests for :mod:`src.twin` (fast; contours from tests/test_shape.py, art from tests/synth.py)."""

import numpy as np
import pytest

import synth
from src.locate import snap_theta
from src.shape import free_dist, transform_contour
from src.twin import TwinItem, find_twin, offset_shape, same_shape, shape_distances
from test_shape import MMPP

ROWS, COLS = 6, 8
KINDS = "TBFT"
DELTAS = (0.8, -0.5, 0.0, 0.3)


def _shape_from_mm(pts_mm):
    return synth.shape_of(pts_mm / MMPP)


def _decoys(n, rng, kinds=KINDS):
    out = []
    for k in range(n):
        deltas = tuple(rng.uniform(-2.0, 2.0, 4))
        radii = tuple(rng.uniform(2.5, 3.5, 4))
        s = _shape_from_mm(synth.body_mm(kinds, deltas=deltas, radii=radii))
        if s.ok:
            out.append(TwinItem(id=f"D{k}", shape=s))
    return out


@pytest.fixture(scope="module")
def alpes_like():
    return synth.profile(ROWS, COLS, symmetry={"type": "rot180"})


def test_shape_distances_matches_free_dist():
    rng = np.random.default_rng(0)
    q = _shape_from_mm(synth.body_mm(KINDS, deltas=DELTAS))
    others = [d.shape for d in _decoys(6, rng)]
    d, phi = shape_distances(q, others)
    for k, s in enumerate(others):
        d0, _, p0 = free_dist(q, s)
        assert d[k] == pytest.approx(d0, abs=1e-9)
        assert ((phi[k] - p0 + 180) % 360 - 180) == pytest.approx(0, abs=1e-6)


def test_twin_rot180_accepted_among_30(alpes_like):
    rng = np.random.default_rng(1)
    cont = synth.body_mm(KINDS, deltas=DELTAS)
    q = TwinItem(id="Q", shape=_shape_from_mm(cont))
    twin_mm = transform_contour(cont, 180, center=(0, 0)) + rng.normal(0, 0.1, cont.shape)
    t = TwinItem(id="T", shape=_shape_from_mm(transform_contour(twin_mm, 33.0)))   # any scan pose
    cands = _decoys(30, rng) + [t]
    res = find_twin(q, cands, profile=alpes_like)
    assert "error" not in res, res
    assert res["candidates"][0]["id"] == "T", res
    assert res["decision"] == "aceite", res["reasons"]
    assert res["margin"] >= 1.5
    assert res["candidates"][0]["d1_mm"] < 0.3
    assert res["twin_cell"] is None          # query cell unknown
    assert any("imagem não testada" in r for r in res["reasons"])


def test_altered_side_not_accepted(alpes_like):
    rng = np.random.default_rng(2)
    cont = synth.body_mm(KINDS, deltas=DELTAS)
    q = TwinItem(id="Q", shape=_shape_from_mm(cont))
    alt = synth.body_mm(KINDS, deltas=(DELTAS[0] + 1.5,) + DELTAS[1:])
    alt = transform_contour(alt, 180, center=(0, 0)) + rng.normal(0, 0.1, cont.shape)
    t = TwinItem(id="T", shape=_shape_from_mm(alt))
    res = find_twin(q, _decoys(30, rng) + [t], profile=alpes_like)
    assert res["decision"] != "aceite", res
    # chord altered 1.5 mm on a side opposite the F side (tolerance 1 mm): rejected by the chord filter
    long_top = synth.make_piece(KINDS, corners=[(0, 0), (synth.L0 + 1.5, 0), (synth.L0, synth.L0), (0, synth.L0)],
                                deltas=DELTAS) * MMPP
    e = TwinItem(id="E", shape=_shape_from_mm(long_top))
    res2 = find_twin(q, [e], profile=alpes_like)
    assert res2["decision"] == "sem" and res2["n_pass"] == 0
    assert any("corda lado" in r for r in res2["reasons"]), res2["reasons"]
    # different class
    other = TwinItem(id="C", shape=_shape_from_mm(synth.body_mm("TTFT")))
    res3 = find_twin(q, [other], profile=alpes_like)
    assert res3["decision"] == "sem" and any("classe diferente" in r for r in res3["reasons"]), res3["reasons"]


def test_single_candidate_not_proposed(alpes_like):
    """Product decision 2026-11-01: a lone candidate is never proposed, but is kept for review."""
    rng = np.random.default_rng(3)
    cont = synth.body_mm(KINDS, deltas=DELTAS)
    q = TwinItem(id="Q", shape=_shape_from_mm(cont))
    t = TwinItem(id="T", shape=_shape_from_mm(transform_contour(cont, 180, center=(0, 0)) + rng.normal(0, 0.1, cont.shape)))
    # the only other candidate of the same class fails the chord filter (side 0 longer by 1.5 mm)
    long_top = synth.make_piece(KINDS, corners=[(0, 0), (synth.L0 + 1.5, 0), (synth.L0, synth.L0), (0, synth.L0)],
                                deltas=DELTAS) * MMPP
    e = TwinItem(id="E", shape=_shape_from_mm(long_top))
    res = find_twin(q, [t, e], profile=alpes_like)
    assert res["n_pass"] == 1 and res["margin"] is None, res
    assert res["decision"] == "sem", res
    assert res["decision_shape"] in ("aceite", "ambigua"), res
    assert res["decision_shape"] == "aceite"              # d1 ~0.1 mm <= t95: what margin = inf would give
    sc = res["single_candidate"]
    assert sc is not None and sc["id"] == "T" and sc["chord_ok"] is True
    assert sc["d1_mm"] == pytest.approx(res["candidates"][0]["d1_mm"]) and sc["d1_mm"] < 0.3
    assert sc["image"] is None
    assert res["candidates"][0]["id"] == "T"              # still listed
    assert any(r.startswith("candidata única T: d1 ") and "não proposta (decisão 2026-11-01)" in r
               for r in res["reasons"]), res["reasons"]
    # two candidates passing -> the rule does not apply
    res2 = find_twin(q, _decoys(30, rng) + [t], profile=alpes_like)
    assert res2["single_candidate"] is None and res2["decision"] == "aceite", res2["reasons"]
    # a lone candidate beyond tmax is a plain 'sem', not a suppressed proposal
    cal = alpes_like.calibration["silhueta_silhueta"]
    far = TwinItem(id="F", shape=_shape_from_mm(synth.body_mm(KINDS, deltas=(2.0, -2.0, 0.0, 2.0))))
    res3 = find_twin(q, [far], profile=alpes_like)
    assert res3["n_pass"] == 1 and res3["candidates"][0]["d1_mm"] > cal["tmax"], res3
    assert res3["decision"] == res3["decision_shape"] == "sem" and res3["single_candidate"] is None, res3
    # a lone candidate between t95 and tmax: decision_shape 'ambigua', still not proposed
    mid = TwinItem(id="M", shape=_shape_from_mm(synth.body_mm(KINDS, deltas=(1.6, -1.4, 0.0, 1.2))))
    res4 = find_twin(q, [mid], profile=alpes_like)
    assert cal["t95"] < res4["candidates"][0]["d1_mm"] <= cal["tmax"], res4
    assert res4["decision"] == "sem" and res4["decision_shape"] == "ambigua" and res4["single_candidate"]["id"] == "M"


def test_errors(alpes_like):
    q = TwinItem(id="Q", shape=_shape_from_mm(synth.body_mm(KINDS)))
    assert "error" in find_twin(q, [], profile=alpes_like, modality="xpto")
    t = np.linspace(0, 2 * np.pi, 400, endpoint=False)
    circle = synth.shape_of(np.c_[200 + 100 * np.cos(t), 200 + 100 * np.sin(t)])
    assert "error" in find_twin(TwinItem(id="O", shape=circle), [q], profile=alpes_like)


def test_same_shape():
    rng = np.random.default_rng(4)
    cont = synth.body_mm(KINDS, deltas=DELTAS)
    a = _shape_from_mm(cont)
    b = _shape_from_mm(transform_contour(cont, 71.0) + rng.normal(0, 0.05, cont.shape))
    c = _shape_from_mm(synth.body_mm(KINDS, deltas=(DELTAS[0] + 2.0,) + DELTAS[1:]))
    assert same_shape(a, b)
    assert not same_shape(a, c)


def test_celula_silhueta_offset():
    """A cut-line cell is the silhouette shrunk ~0.48 mm: the offset correction brings them together."""
    cal = {k: dict(v) if isinstance(v, dict) else v for k, v in synth.ALPES_CAL.items()}
    prof_nocal = synth.profile(ROWS, COLS, cal=cal)
    cal2 = {k: dict(v) if isinstance(v, dict) else v for k, v in synth.ALPES_CAL.items()}
    cal2["celula_silhueta"].update(t95=0.507, tmax=0.637)
    prof_cal = synth.profile(ROWS, COLS, cal=cal2)
    rng = np.random.default_rng(5)
    cont = synth.body_mm(KINDS, deltas=DELTAS)
    sil = _shape_from_mm(transform_contour(cont, 180, center=(0, 0)))
    cell = offset_shape(_shape_from_mm(cont), -0.48)          # the cut line sits 0.48 mm inside the silhouette
    q = TwinItem(id="Q", shape=cell)
    cands = [TwinItem(id="T", shape=sil)] + _decoys(30, rng)
    raw = free_dist(cell, sil)[0]
    res = find_twin(q, cands, profile=prof_cal, modality="celula_silhueta")
    assert res["candidates"][0]["id"] == "T"
    assert res["candidates"][0]["d1_mm"] < 0.5 * raw, (raw, res["candidates"][0])
    assert res["decision"] == "aceite", res["reasons"]
    # t95 not calibrated: never 'aceite'
    res2 = find_twin(q, cands, profile=prof_nocal, modality="celula_silhueta")
    assert res2["decision"] == "ambigua", res2["reasons"]
    assert any("t95 por calibrar" in r for r in res2["reasons"])


# ---------------------------------------------------------------- image (synthetic art)
def _image_world(symmetry, psi_twin=90.0, seed=7):
    prof = synth.profile(ROWS, COLS, symmetry=symmetry, p90=15.0)
    rgb = synth.art_rgb(ROWS, COLS, seed=seed)
    art = synth.make_art(rgb, ROWS, COLS)
    qcell = (2, 2)
    tcell = prof.twin(*qcell)
    cont = synth.body_mm("TBTB", deltas=(0.8, -0.5, 0.4, 0.3))
    pq, rq = synth.scan_piece(rgb, cont, qcell, psi=0.0)
    sq = synth.shape_of(pq)
    q = TwinItem(id="Q", shape=sq, rgba=rq, theta_deg=snap_theta(sq, 0.0)[0], cell=qcell)
    tw = synth.twin_board_contour(cont, prof)
    return prof, rgb, art, q, tw, tcell


def _item(rgb, cid, contour, cell, psi):
    p, r = synth.scan_piece(rgb, contour, cell, psi=psi)
    return TwinItem(id=cid, shape=synth.shape_of(p), rgba=r)


def _decoys_img(rgb, n, rng, cells):
    out = []
    for k in range(n):
        cont = synth.body_mm("TBTB", deltas=tuple(rng.uniform(-2, 2, 4)), radii=tuple(rng.uniform(2.5, 3.5, 4)))
        it = _item(rgb, f"D{k}", cont, cells[k % len(cells)], float(rng.uniform(-180, 180)))
        if it.shape.ok:
            out.append(it)
    return out


def test_profile_translate_drives_twin_cell():
    prof = synth.profile(6, 8, symmetry={"type": "translate", "cols": 4})
    assert prof.twin(1, 2) == (1, 6)
    prof2, rgb, art, q, tw, tcell = _image_world({"type": "translate", "cols": 4})
    assert tcell == (2, 6)
    rng = np.random.default_rng(8)
    t = _item(rgb, "T", tw, tcell, 90.0)
    res = find_twin(q, [t] + _decoys_img(rgb, 12, rng, [(3, 3), (4, 5), (5, 2)]), profile=prof2, art=art)
    assert res["twin_cell"] == (2, 6)
    assert res["candidates"][0]["id"] == "T"
    assert res["candidates"][0]["twin_cell"] == (2, 6)
    assert res["decision"] == "aceite", res["reasons"]
    im = res["candidates"][0]["image"]
    assert im["dE"] < 3.0, im
    # translate symmetry: the twin rotation is 0, so the candidate pose is theta_q + phi (= -90 here)
    assert ((im["theta_deg"] + 90.0 + 180) % 360 - 180) == pytest.approx(0, abs=3.0)


def test_image_demotes_wrong_colour_and_never_promotes():
    prof, rgb, art, q, tw, tcell = _image_world({"type": "rot180"})
    rng = np.random.default_rng(9)
    decoys = _decoys_img(rgb, 20, rng, [(3, 3), (4, 5), (5, 2)])
    # right shape, right colour -> aceite, the image is consistent
    good = _item(rgb, "T", tw, tcell, 90.0)
    res = find_twin(q, [good] + decoys, profile=prof, art=art)
    assert res["twin_cell"] == tcell and res["candidates"][0]["id"] == "T"
    assert res["decision"] == "aceite", res["reasons"]
    assert res["candidates"][0]["image"]["dE"] < 3.0
    assert res["candidates"][0]["image"]["pctl"] == pytest.approx(0.0)
    # right shape, wrong colour (cut from another cell) -> demoted to ambigua
    bad = _item(rgb, "T", tw, (4, 4), 90.0)
    res2 = find_twin(q, [bad] + decoys, profile=prof, art=art)
    assert res2["decision_shape"] == "aceite"
    assert res2["candidates"][0]["image"]["dE"] > 15.0
    assert res2["decision"] == "ambigua", res2["reasons"]
    assert any("> p90" in r for r in res2["reasons"])
    # right shape, right colour, but alone -> not proposed and the image is not tested
    res1 = find_twin(q, [good], profile=prof, art=art)
    assert res1["decision"] == "sem" and res1["decision_shape"] == "aceite", res1["reasons"]
    assert res1["single_candidate"]["id"] == "T" and res1["single_candidate"]["image"] is None
    assert res1["candidates"][0]["image"] is None
    # wrong shape (sem), perfect colour -> stays sem
    far = synth.body_mm("TBTB", deltas=(2.8, 1.5, -1.5, 2.0))
    far = synth.twin_board_contour(far, prof)
    res3 = find_twin(q, [_item(rgb, "F", far, tcell, 90.0)], profile=prof, art=art)
    assert res3["decision"] == "sem", res3
    # unknown query pose: 4 rotations tested and flagged
    q2 = TwinItem(id=q.id, shape=q.shape, rgba=q.rgba, theta_deg=None, cell=q.cell)
    res4 = find_twin(q2, [good] + decoys, profile=prof, art=art)
    assert any(r.startswith("theta_unknown") for r in res4["reasons"])
    assert res4["candidates"][0]["image"]["dE"] < 3.0
