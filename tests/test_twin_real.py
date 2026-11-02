"""Real-scan regression of :func:`src.twin.find_twin` (marked ``slow``).

(a) E-sym: ``segment_scan`` of the A1 / A2 / B2 scans (20 top-border pieces, B = the 180 deg
    twins; images/pieces/gemeos_2026-10-30.md) -> ``analyse`` -> ``find_twin`` without image,
    ``modality='silhueta_silhueta'``: 20/20 ``aceite`` for A1 -> B2 and A2 -> B2, median twin
    distance <= 0.5 mm.
(b) E-real-2 (docs/diagnostico/gemeos/EREAL2.md §8): the 188 loose pieces of the E-real-2
    memory (contours from ``segment_scan``, cached in ``$PPF_SCRATCH/ereal2/memoria.pkl`` by
    ``tools/diagnostico/gemeos/ereal2.py``; the decisions here are all ``src.twin``'s):
    BE(2,4) -> f2p1 #4 ``aceite`` (d1 ~0.41, margin ~2.4) and BE(5,5) -> f1p1 #6 (d1 ~0.54,
    single candidate: ``ambigua`` until 2026-11-01, now ``sem`` with ``decision_shape``
    ``ambigua`` and ``single_candidate`` set, product decision 2026-11-01), both consistent
    with the art on the twin cells (2,61) / (5,60) (dE ~8.7 / ~10.8, pose by the orientation
    chain of EREAL2 §3; the lone candidate's image is computed here, find_twin skips it), the
    other 18 BE ``sem``, and 0 ``aceite`` among the known-negative pairs. The orientation chain
    is checked on the 20 E-sym pairs (A1 with its F side up -> predicted B2 pose has its F side down).

Numbers are printed (run with ``-s``) and written to ``$PPF_SCRATCH/twin/twin_real.json``.
Skips if the scans, ``PPF_SCRATCH`` or the memory are missing.
"""

import json
import os
import pickle
import time

import cv2
import numpy as np
import pytest
from PIL import Image

from conftest import REPO_ROOT
from src.locate import CellArt, body_center_mm, snap_theta, wrap_deg
from src.profile import PuzzleProfile
from src.shape import analyse
from src.twin import TwinItem, _image_test, find_twin

pytestmark = pytest.mark.slow

_SCANS = {
    "A1": "images/pieces/coluna5-24_300dpi_folhaA.jpg",
    "A2": "images/pieces/colunas5-24_300dpi_rot180_folhaA.jpg",
    "B2": "images/pieces/coluna5-24_folhaB_300dpi_rot180.jpg",
}
_PROFILE = os.path.join(REPO_ROOT, "projects", "alpes", "puzzle.json")
_SCRATCH = os.environ.get("PPF_SCRATCH")
_MEMORY = os.path.join(_SCRATCH, "ereal2", "memoria.pkl") if _SCRATCH else None
REPORT = {}


@pytest.fixture(scope="module")
def profile():
    return PuzzleProfile.load(_PROFILE)


@pytest.fixture(scope="module", autouse=True)
def _write_report():
    yield
    if _SCRATCH and REPORT:
        out = os.path.join(_SCRATCH, "twin")
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "twin_real.json"), "w", encoding="utf-8") as f:
            json.dump(REPORT, f, ensure_ascii=False, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))


def _read_rgb(path):
    im = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
    return cv2.cvtColor(im, cv2.COLOR_BGR2RGB)


def _crop(rgb, contour, pad=12):
    """RGBA crop of a piece (scan frame, translated only)."""
    c = np.asarray(contour, float).reshape(-1, 2)
    x0, y0 = np.maximum(np.floor(c.min(0)).astype(int) - pad, 0)
    x1, y1 = np.ceil(c.max(0)).astype(int) + pad
    x1, y1 = min(x1, rgb.shape[1]), min(y1, rgb.shape[0])
    a = np.zeros((y1 - y0, x1 - x0), np.uint8)
    cv2.fillPoly(a, [np.round(c - [x0, y0]).astype(np.int32).reshape(-1, 1, 2)], 255)
    return np.dstack([rgb[y0:y1, x0:x1], a])


def _f_normal_deg(shape):
    """Angle (deg, scan frame) of the outward normal of the first F side (body centre -> chord midpoint)."""
    cb = body_center_mm(shape)
    for s in shape.sides:
        if s.kind == "F":
            v = 0.5 * (s.p0_mm + s.p1_mm) - cb
            return float(np.degrees(np.arctan2(v[1], v[0])))
    return None


# ---------------------------------------------------------------- (a) E-sym
def _grid_order(bboxes):
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
    return [int(i) for r in rows for i in sorted(r, key=lambda j: cx[j])]


def _esym_twin(i):
    f, k = divmod(i, 5)
    return 5 * f + (4 - k)


def test_esym_find_twin(profile):
    missing = [p for p in _SCANS.values() if not os.path.exists(os.path.join(REPO_ROOT, p))]
    if missing:
        pytest.skip(f"E-sym scans missing: {missing}")
    from src.segmentation import segment_scan
    t0 = time.time()
    items = {}
    for name, rel in _SCANS.items():
        with Image.open(os.path.join(REPO_ROOT, rel)) as im:
            im.load()
            res = segment_scan(im)
        assert "error" not in res, (name, res.get("error"))
        pieces = [res["pieces"][i] for i in _grid_order([p["bbox"] for p in res["pieces"]])]
        assert len(pieces) == 20, (name, len(pieces))
        items[name] = [TwinItem(id=f"{name}#{i}", shape=analyse(p["contour"], res["mm_per_px"])) for i, p in enumerate(pieces)]
    out = {}
    t95 = profile.calibration["silhueta_silhueta"]["t95"]
    for qn in ("A1", "A2"):
        decs, d_twin, margins, top_ok, wrong, single_ok = [], [], [], 0, [], 0
        for i, q in enumerate(items[qn]):
            r = find_twin(q, items["B2"], profile=profile, modality="silhueta_silhueta")
            assert "error" not in r, r
            want = f"B2#{_esym_twin(i)}"
            top = r["candidates"][0]["id"] if r["candidates"] else None
            top_ok += top == want
            decs.append(r["decision"] if top == want else f"{r['decision']} (top {top})")
            if top != want and r["decision_shape"] != "sem":    # lone candidates included (now 'sem', 2026-11-01)
                wrong.append((q.id, top, r["decision_shape"]))
            if top == want:
                d_twin.append(r["candidates"][0]["d1_mm"])
                margins.append(r["margin"] if r["margin"] is not None else np.inf)
                # prototype semantics (ereal2.query): a single candidate has margin inf -> ACEITE if d1 <= t95;
                # since 2026-11-01 find_twin returns it as 'sem' with decision_shape 'aceite' and single_candidate set
                single_ok += r["single_candidate"] is not None and r["decision_shape"] == "aceite"
            assert r["single_candidate"] is None or r["decision"] == "sem", r
        n_acc = sum(d == "aceite" for d in decs)
        out[f"{qn}->B2"] = dict(aceite=n_acc, aceite_if_single_counted=n_acc + single_ok, single_suppressed=int(single_ok),
                                top1=top_ok, wrong_proposals=wrong,
                                d_twin_median=float(np.median(d_twin)), d_twin_max=float(np.max(d_twin)),
                                margin_min_finite=float(np.min([m for m in margins if np.isfinite(m)])), decisions=decs)
        print(f"[E-sym] {qn}->B2: aceite {n_acc}/20 (+{single_ok} lone candidates not proposed with d1 <= t95 = "
              f"{n_acc + single_ok}/20 with the prototype's margin=inf rule), top-1 {top_ok}/20, wrong proposals {wrong}, "
              f"twin d median {np.median(d_twin):.3f} max {np.max(d_twin):.3f} mm; decisions {decs}")
    REPORT["esym"] = dict(out, seconds=round(time.time() - t0, 1))
    # contract rule "a single candidate is never proposed" (plano §2.2, 2026-11-01; before: "at most ambigua"): in a
    # pool of only the 20 B2, 4 of the 5 classes have one member, so 20/20 'aceite' is not reachable; asserted: no
    # wrong proposal (lone candidates included), every A1 twin first, and every A1 non-aceite is a single candidate
    # with d1 <= t95
    for k, v in out.items():
        assert v["wrong_proposals"] == [], (k, v)
        assert v["d_twin_median"] <= 0.5, (k, v)
    a1 = out["A1->B2"]
    assert a1["top1"] == 20 and a1["aceite_if_single_counted"] == 20, a1
    a2 = out["A2->B2"]
    assert a2["top1"] >= 19 and a2["aceite"] >= 12, a2   # measured 2026-11-01: 19 / 12 (A2#12 fails the chord rule by 0.05 mm)


# ---------------------------------------------------------------- (b) E-real-2
@pytest.fixture(scope="module")
def memory(profile):
    if not _MEMORY or not os.path.exists(_MEMORY):
        pytest.skip("PPF_SCRATCH/ereal2/memoria.pkl missing (run tools/diagnostico/gemeos/ereal2.py)")
    with open(_MEMORY, "rb") as f:
        D = pickle.load(f)
    M = D["BE"] + [p for p in D["CEU"] if p.get("ok")] + D["BD"] + D["ES"]
    paths = sorted({p["img"] for p in M})
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        pytest.skip(f"scans of the E-real-2 memory missing: {missing}")
    imgs = {p: _read_rgb(p) for p in paths}
    mmpp = profile.mm_per_px()
    items, src = [], {}
    for p in M:
        it = TwinItem(id=p["lab"], shape=analyse(p["contour"], mmpp), rgba=_crop(imgs[p["img"]], p["contour"]),
                      cell=tuple(int(v) for v in p["cell"]) if p["cell"] is not None else None)
        items.append(it)
        src[it.id] = p["src"]
    art = CellArt.load(profile, REPO_ROOT)
    return dict(items=items, src=src, art=art)


def _rel(a, b, src, profile):
    """GT relation of a pair (EREAL2 §4): pos / neg (known negative) / ceuceu (expected negative) / BExceu (unknown)."""
    if a.cell is not None and b.cell is not None:
        return "pos" if profile.twin(*a.cell) == tuple(b.cell) else "neg"
    s = {src[a.id], src[b.id]}
    if s == {"ceu"}:
        return "ceuceu"
    if "BE" in s:
        return "BExceu"
    return "neg"


def test_ereal2_find_twin(profile, memory):
    items, src, art = memory["items"], memory["src"], memory["art"]
    N = len(items)
    assert N == 188 and all(it.shape.ok for it in items)
    t0 = time.time()
    # --- shape decisions for every piece as a query (the image can only demote, so this bounds 'aceite')
    res = {}
    for q in items:
        r = find_twin(q, items, profile=profile)
        assert "error" not in r, r
        res[q.id] = r
    t_shape = time.time() - t0
    by_id = {it.id: it for it in items}
    def pairs(field):
        out = {}
        for qid, r in res.items():
            if r[field] != "sem" and r["candidates"]:
                key = frozenset((qid, r["candidates"][0]["id"]))
                old = out.get(key)
                out[key] = "aceite" if "aceite" in (old, r[field]) else "ambigua"
        return out

    pair_dec = pairs("decision")
    # without the 2026-11-01 lone-candidate rule (decision_shape: a lone candidate gets margin = inf)
    pair_shape = pairs("decision_shape")
    n_rel, dec_rel = {}, {}
    for i in range(N):
        for j in range(i + 1, N):
            k = _rel(items[i], items[j], src, profile)
            n_rel[k] = n_rel.get(k, 0) + 1
    for key, d in pair_dec.items():
        a, b = (by_id[x] for x in key)
        k = _rel(a, b, src, profile)
        dec_rel.setdefault(k, {}).setdefault(d, []).append(sorted(key))
    counts = {k: {d: len(v) for d, v in dd.items()} for k, dd in dec_rel.items()}
    counts_shape = {}
    for key, d in pair_shape.items():
        a, b = (by_id[x] for x in key)
        k = _rel(a, b, src, profile)
        counts_shape.setdefault(k, {}).setdefault(d, 0)
        counts_shape[k][d] += 1
    print(f"[E-real-2] {N} queries (shape only) in {t_shape:.1f} s; pairs by GT relation {n_rel}; proposals by relation {counts}"
          f"; without the lone-candidate rule {counts_shape}")
    for k in ("neg", "ceuceu"):
        for d, lst in dec_rel.get(k, {}).items():
            print(f"   {k} {d}: {lst}")
    REPORT["ereal2_pairs"] = dict(n=n_rel, proposals=counts, proposals_without_single_rule=counts_shape, detail={k: {d: v for d, v in dd.items()} for k, dd in dec_rel.items()
                                                                    if k != "pos"}, seconds=round(t_shape, 1))
    assert dec_rel.get("neg", {}).get("aceite", []) == [], dec_rel["neg"]
    assert dec_rel.get("ceuceu", {}).get("aceite", []) == [], dec_rel["ceuceu"]
    # the 20 E-sym twin pairs are all found by shape; since 2026-11-01 those found only through lone candidates are 'sem'
    pos_shape = counts_shape.get("pos", {})
    assert pos_shape.get("aceite", 0) + pos_shape.get("ambigua", 0) == 20, pos_shape
    pos = counts.get("pos", {})
    assert pos.get("aceite", 0) == 15 and pos.get("ambigua", 0) == 0, pos   # measured 2026-11-01
    assert all(r["decision"] == "sem" for r in res.values() if r["single_candidate"] is not None)
    single_pos = [qid for qid, r in res.items() if r["single_candidate"] is not None and r["decision_shape"] == "aceite"
                  and src[qid] == "ES"]
    single_neg = [(qid, r["candidates"][0]["id"]) for qid, r in res.items() if r["single_candidate"] is not None
                  and r["decision_shape"] == "aceite"
                  and _rel(by_id[qid], by_id[r["candidates"][0]["id"]], src, profile) in ("neg", "ceuceu")]
    print(f"   lone candidates (not proposed) with d1 <= t95: E-sym queries {len(single_pos)}, on negative pairs {single_neg}")
    REPORT["ereal2_pairs"].update(single_candidate_esym=single_pos, single_candidate_negative=single_neg)

    # --- BE -> memory with the image (BE upright = scan turned 90 deg clockwise, EREAL2 §3)
    t1 = time.time()
    be = [it for it in items if src[it.id] == "BE"]
    rows = {}
    for q in be:
        qq = TwinItem(id=q.id, shape=q.shape, rgba=q.rgba, theta_deg=90.0, cell=q.cell)
        r = find_twin(qq, items, profile=profile, art=art, zone="ceu")
        rows[q.id] = r
        c0 = r["candidates"][0] if r["candidates"] else None
        im = c0["image"] if c0 else None
        print(f"   {q.id} -> twin {r['twin_cell']}: {r['decision']:8s} (shape {r['decision_shape']}"
              f"{', lone candidate' if r['single_candidate'] else ''}) "
              + (f"{c0['id']} d1 {c0['d1_mm']:.3f} margin {r['margin'] if r['margin'] is None else round(r['margin'], 3)}" if c0 else "-")
              + (f" dE {im['dE']:.1f} ncc {im['ncc']:.2f} pct {im['pctl']} theta {im['theta_deg']:.1f} resid {im['resid_deg']:.1f}"
                 if im else ""))
    t_img = time.time() - t1
    REPORT["ereal2_BE"] = {k: dict(decision=v["decision"], decision_shape=v["decision_shape"], margin=v["margin"],
                                   single_candidate=v["single_candidate"],
                                   twin_cell=v["twin_cell"], candidates=v["candidates"], reasons=v["reasons"]) for k, v in rows.items()}
    r24, r55 = rows["BE(2,4)"], rows["BE(5,5)"]
    assert r24["twin_cell"] == (2, 61) and r55["twin_cell"] == (5, 60)
    assert r24["decision"] == "aceite" and r24["candidates"][0]["id"] == "f2p1 #4", r24
    assert r24["candidates"][0]["d1_mm"] == pytest.approx(0.408, abs=0.01)
    assert r24["margin"] == pytest.approx(2.39, abs=0.05)
    assert r24["candidates"][0]["image"]["dE"] == pytest.approx(8.7, abs=1.0)
    # BE(5,5): lone candidate -> not proposed since 2026-11-01 (was 'ambigua'; physically confirmed as the right
    # shape, EREAL2.md); find_twin no longer computes its image, so it is checked here with the same pose rule
    assert r55["decision"] == "sem" and r55["decision_shape"] == "ambigua" and r55["margin"] is None, r55
    sc = r55["single_candidate"]
    assert sc is not None and sc["id"] == "f1p1 #6" and r55["candidates"][0]["id"] == "f1p1 #6", r55
    assert sc["d1_mm"] == pytest.approx(0.539, abs=0.01) and sc["image"] is None
    im55 = _image_test(by_id[sc["id"]], 90.0, sc["phi_deg"], r55["twin_cell"], profile, art, profile.mm_per_px())
    print(f"   BE(5,5) lone candidate {sc['id']}: dE {im55['dE']:.1f} (computed by the test)")
    assert im55["dE"] == pytest.approx(10.8, abs=1.0), im55
    others = {k: v["decision"] for k, v in rows.items() if k not in ("BE(2,4)", "BE(5,5)")}
    assert all(d == "sem" for d in others.values()), others
    others_single = {k: v["single_candidate"]["id"] for k, v in rows.items() if k not in ("BE(2,4)", "BE(5,5)")
                     and v["single_candidate"] is not None}
    print(f"   other BE with a lone candidate (not proposed): {others_single}")
    REPORT["ereal2_BE_other_single"] = others_single

    # --- orientation chain on the E-sym pairs: A1 with its F side up -> predicted B2 pose has its F side down
    t2 = time.time()
    a1 = [it for it in items if it.id.startswith("A1(")]
    ok_down, resid_p, resid_m, n, n_single, n_no_art = 0, [], [], 0, 0, 0
    for q in a1:
        nu = _f_normal_deg(q.shape)
        th_q = snap_theta(q.shape, -90.0 - nu)[0]          # F normal -> up (-90 deg)
        qq = TwinItem(id=q.id, shape=q.shape, rgba=q.rgba, theta_deg=th_q, cell=q.cell)
        r = find_twin(qq, items, profile=profile, art=art)
        c0 = r["candidates"][0]
        b = by_id[c0["id"]]
        assert profile.twin(*q.cell) == b.cell, (q.id, c0["id"])
        n += 1
        if c0["image"] is not None:
            th_b, res_b = c0["image"]["theta_deg"], c0["image"]["resid_deg"]
        else:   # image skipped: lone candidate (not proposed) or twin cell without art (row 47 is beyond the art
            # file, docs/diagnostico/arte/ARTREG.md): the same predicted pose as src.twin._image_test
            no_art = any("sem arte na célula" in x for x in r["reasons"])
            if no_art:      # mandatory image tie-break: a shape 'aceite' without art is 'ambigua'
                assert r["decision"] in ("ambigua", "sem") and r["decision_shape"] in ("aceite", "ambigua", "sem"), r
            assert no_art or (r["single_candidate"] is not None and r["single_candidate"]["id"] == c0["id"]), r
            n_single += r["single_candidate"] is not None
            n_no_art += no_art
            th_b, _, res_b = snap_theta(b.shape, th_q + c0["phi_deg"] + profile.twin_rotation_deg())
        ok_down += abs(wrap_deg(_f_normal_deg(b.shape) + th_b - 90.0)) < 45
        resid_p.append(abs(res_b))
        resid_m.append(abs(snap_theta(b.shape, th_q - c0["phi_deg"] + profile.twin_rotation_deg())[2]))
    print(f"[orientation] E-sym A1 F up -> B2 F down {ok_down}/{n} ({n_single} lone candidates, {n_no_art} twin cells without art); |residual to the body axis| median +phi "
          f"{np.median(resid_p):.2f} deg (max {np.max(resid_p):.2f}) vs -phi {np.median(resid_m):.2f} deg ({time.time() - t2:.1f} s)")
    REPORT["orientation"] = dict(F_down=int(ok_down), n=n, n_single=n_single, n_no_art=n_no_art, resid_plus_median=float(np.median(resid_p)),
                                 resid_plus_max=float(np.max(resid_p)), resid_minus_median=float(np.median(resid_m)))
    REPORT["seconds_image_BE"] = round(t_img, 1)
    assert ok_down == n == 20
    assert np.median(resid_p) < np.median(resid_m)
