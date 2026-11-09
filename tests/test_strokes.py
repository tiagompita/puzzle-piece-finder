"""Stroke editor solver (:mod:`src.strokes`): stroke raster, trimap, domain, cleaning, RLE, and the
solvers on the synthetic eaten-meadow scan (``tests/synth.meadow_scan``; fast).

The meadow case: ``segment_scan(recover_bays=False)`` cuts the paper-coloured corner patch out of
piece A. The default solver (chroma-only GrabCut) gets it back when the user paints the patch as
``peca``; an ``incerto`` lasso alone is not enough for a colour-model solver (the patch has no piece
colour to learn from) but is for the threshold baseline (docs/diagnostico/editor/TRACOS.md §4).
"""

import cv2
import numpy as np
import pytest

from src import maskcmp as M
from src import strokes as ST

MMPP = 25.4 / 300


def _norm(tr, w=None, h=None):
    out, err = ST.validar_tracos(tr, w, h)
    assert err is None, err
    return out


# ---------------------------------------------------------------- strokes
def test_validar_tracos_reasons():
    assert ST.validar_tracos(None) == ([], None)
    assert "lista" in ST.validar_tracos({"a": 1})[1]
    sq = [[10, 10], [50, 10], [50, 50]]
    assert "ferramenta" in ST.validar_tracos([{"ferramenta": "x", "marca": "peca", "pontos": sq}])[1]
    assert "marca" in ST.validar_tracos([{"ferramenta": "laco", "marca": None, "pontos": sq}])[1]
    assert "borracha" in ST.validar_tracos([{"ferramenta": "borracha", "marca": "peca", "raio_px": 3, "pontos": sq}])[1]
    assert "3" in ST.validar_tracos([{"ferramenta": "laco", "marca": "peca", "pontos": sq[:2]}])[1]
    assert "raio" in ST.validar_tracos([{"ferramenta": "pincel", "marca": "fundo", "pontos": sq}])[1]
    assert "raio" in ST.validar_tracos([{"ferramenta": "pincel", "marca": "fundo", "raio_px": 0, "pontos": sq}])[1]
    assert "finitos" in ST.validar_tracos([{"ferramenta": "laco", "marca": "peca", "pontos": [[0, 0], [1, np.nan], [2, 2]]}])[1]
    assert "fora" in ST.validar_tracos([{"ferramenta": "laco", "marca": "peca", "pontos": [[0, 0], [500, 0], [0, 9]]}], 100, 100)[1]
    ok = _norm([{"ferramenta": "borracha", "raio_px": 2, "pontos": [[1, 1]]}, {"ferramenta": "laco", "marca": "incerto", "pontos": sq}])
    assert ok[0]["marca"] is None and ok[1]["raio_px"] == 0.0 and ok[1]["pontos"] == [[10.0, 10.0], [50.0, 10.0], [50.0, 50.0]]


def test_rasterizar_tracos_tools_and_order():
    shape = (100, 120)
    lasso = {"ferramenta": "laco", "marca": "peca", "pontos": [[10, 10], [60, 10], [60, 60], [10, 60]]}
    lbl = ST.rasterizar_tracos(_norm([lasso]), shape)
    assert lbl.dtype == np.int8 and set(np.unique(lbl)) == {-1, ST.PECA_CERTA}
    assert abs(int((lbl == ST.PECA_CERTA).sum()) - 51 * 51) <= 51 * 2              # filled square, edges included
    dot = {"ferramenta": "pincel", "marca": "fundo", "raio_px": 6.0, "pontos": [[90, 80]]}
    d = ST.rasterizar_tracos(_norm([dot]), shape) == ST.FUNDO_CERTO
    assert abs(d.sum() - np.pi * 36) / (np.pi * 36) < 0.2                       # one point = a disc
    line = {"ferramenta": "pincel", "marca": "incerto", "raio_px": 3.0, "pontos": [[70, 20], [110, 20]]}
    ln = ST.rasterizar_tracos(_norm([line]), shape) == ST.INCERTO
    cols = ln[:, 70:111].sum(0)
    assert ln[20, 70:111].all() and 5 <= np.median(cols) <= 8                   # thickness 2 r (+1 px)
    # order: a later stroke wins; the eraser gives back "unmarked"
    over = {"ferramenta": "laco", "marca": "fundo", "pontos": [[30, 30], [80, 30], [80, 80], [30, 80]]}
    era = {"ferramenta": "borracha", "raio_px": 5.0, "pontos": [[40, 40]]}
    lb = ST.rasterizar_tracos(_norm([lasso, over, era]), shape)
    assert lb[15, 15] == ST.PECA_CERTA and lb[50, 50] == ST.FUNDO_CERTO and lb[40, 40] == -1 and lb[70, 75] == ST.FUNDO_CERTO
    assert ST.rasterizar_tracos(_norm([over, lasso]), shape)[50, 50] == ST.PECA_CERTA


def test_traduzir_tracos():
    tr = _norm([{"ferramenta": "laco", "marca": "peca", "pontos": [[1, 2], [3, 4], [5, 6]]}])
    t2 = ST.traduzir_tracos(tr, 10, -2)
    assert t2[0]["pontos"] == [[11.0, 0.0], [13.0, 2.0], [15.0, 4.0]] and tr[0]["pontos"][0] == [1.0, 2.0]


# ---------------------------------------------------------------- trimap / domain / cleaning
def _square(shape=(200, 200), a=50, b=150):
    m = np.zeros(shape, bool)
    m[a:b, a:b] = True
    return m


def test_trimap_bands_and_strokes():
    auto = _square()
    r = int(round(ST.BANDA_MM / MMPP))                                         # 12 px at 300 dpi
    t = ST.trimap(auto, [], MMPP)
    assert t.dtype == np.uint8 and set(np.unique(t)) == {ST.FUNDO_PROV, ST.INCERTO, ST.PECA_PROV}
    row = t[100]
    assert row[50 + r + 1] == ST.PECA_PROV and row[50 + r - 1] == ST.INCERTO and row[50] == ST.INCERTO
    assert row[50 - r + 1] == ST.INCERTO and row[50 - r - 1] == ST.FUNDO_PROV
    assert t[100, 100] == ST.PECA_PROV and t[5, 5] == ST.FUNDO_PROV
    tr = _norm([{"ferramenta": "laco", "marca": "fundo", "pontos": [[90, 90], [110, 90], [110, 110], [90, 110]]},
                {"ferramenta": "pincel", "marca": "peca", "raio_px": 3, "pontos": [[20, 20]]},
                {"ferramenta": "pincel", "marca": "incerto", "raio_px": 3, "pontos": [[180, 180]]}])
    t2 = ST.trimap(auto, tr, MMPP)
    assert t2[100, 100] == ST.FUNDO_CERTO and t2[20, 20] == ST.PECA_CERTA and t2[180, 180] == ST.INCERTO
    assert np.array_equal(t2[150:, :60], t[150:, :60])                         # untouched elsewhere


def test_dominio_reach():
    t = ST.trimap(_square(), [], MMPP)
    fg, bg, free = ST.dominio(t, 0)
    assert np.array_equal(free, t == ST.INCERTO) and np.array_equal(fg, t == ST.PECA_PROV)
    fg2, bg2, free2 = ST.dominio(t, 5)
    assert free2.sum() > free.sum() and (fg2 | bg2 | free2).all() and not (fg2 & free2).any() and not (bg2 & free2).any()


def test_limpar_and_polygon():
    m = _square()
    m[100, 50:150] = False                    # 1-px crack: closed
    m[80:90, 80:90] = False                   # hole: filled
    m[5:8, 5:8] = True                        # speck: dropped (largest component)
    c = ST.limpar(m, MMPP)
    assert c[100, 100] and c[85, 85] and not c[6, 6]
    assert abs(int(c.sum()) - 100 * 100) <= 40
    tri = np.full(m.shape, ST.FUNDO_PROV, np.uint8)
    tri[60:70, 60:70] = ST.FUNDO_CERTO
    tri[150:160, 100:110] = ST.PECA_CERTA     # touching the square: imposed and kept
    c2 = ST.limpar(_square(), MMPP, tri)
    assert c2[155, 105] and c2[65, 65]        # a certain-background hole is filled again (outer outline only)
    poly = ST.mascara_poligono(c)
    fill = np.zeros(c.shape, np.uint8)
    cv2.fillPoly(fill, [poly.astype(np.int32).reshape(-1, 1, 2)], 1)
    assert np.array_equal(fill > 0, c)
    assert ST.mascara_poligono(np.zeros((10, 10), bool)) is None


def test_rle_roundtrip():
    rng = np.random.default_rng(1)
    for m in (rng.random((37, 53)) > 0.6, np.ones((4, 5), bool), np.zeros((4, 5), bool), _square((30, 40), 3, 20),
              np.zeros((0, 3), bool)):
        r = ST.rle_encode(m)
        assert r["w"] == m.shape[1] and r["h"] == m.shape[0] and sum(r["runs"]) == m.size
        assert np.array_equal(ST.rle_decode(r), m)
    assert ST.rle_encode(np.ones((2, 2), bool))["runs"] == [0, 4]
    with pytest.raises(ValueError):
        ST.rle_decode({"w": 3, "h": 3, "runs": [4, 4]})
    with pytest.raises(ValueError):
        ST.rle_decode({"w": 3})


def test_resolver_errors_and_params():
    rgb = np.zeros((60, 60, 3), np.uint8)
    auto = _square((60, 60), 20, 40)
    assert "solver" in ST.resolver(rgb, auto, [], MMPP, solver="x")["error"]
    assert "parâmetro" in ST.resolver(rgb, auto, [], MMPP, params={"nada": 1})["error"]
    all_bg = _norm([{"ferramenta": "laco", "marca": "fundo", "pontos": [[-1, -1], [61, -1], [61, 61], [-1, 61]]}])
    assert "error" in ST.resolver(rgb, auto, all_bg, MMPP)
    assert ST.parametros("grabcut", {"iters": 4})["iters"] == 4 and ST.parametros("grabcut") == ST.SOLVER_PARAMS["grabcut"]


# ---------------------------------------------------------------- solvers on the synthetic meadow scan
@pytest.fixture(scope="module")
def meadow():
    from synth import meadow_scan
    from src.segmentation import segment_scan
    img, gts, patch = meadow_scan()
    rgb = np.asarray(img)
    off = segment_scan(img, dpi=300, normalize_rotation=False, recover_bays=False)
    best = None
    for p in off["pieces"]:
        m = M.fill_contour(np.asarray(p["contour"]).reshape(-1, 2), gts[0].shape)
        iou = (m & gts[0]).sum() / (m | gts[0]).sum()
        if best is None or iou > best[0]:
            best = (iou, m)
    ys, xs = np.nonzero(gts[0] | best[1])
    pad = 36                                                                     # ~3 mm, as the editor crop
    sl = (slice(ys.min() - pad, ys.max() + pad), slice(xs.min() - pad, xs.max() + pad))
    return {"rgb": np.ascontiguousarray(rgb[sl]), "auto": best[1][sl], "gt": gts[0][sl], "patch": patch[sl],
            "auto_iou": float(best[0])}


def _outer(mask):
    cs, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    return [c.reshape(-1, 2).tolist() for c in cs]


def _iou(gt, m):
    return float((gt & m).sum()) / float((gt | m).sum())


def test_meadow_peca_mark_recovers_eaten_corner(meadow):
    """Eaten contour (auto IoU < 0.97) + a ``peca`` lasso inside the paper-coloured patch: the default
    solver gives IoU >= 0.99 against the synthetic GT, and at least the threshold baseline."""
    assert meadow["auto_iou"] < 0.97
    inner = cv2.erode(meadow["patch"].astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    tr = _norm([{"ferramenta": "laco", "marca": "peca", "pontos": c} for c in _outer(inner)])
    d = ST.resolver(meadow["rgb"], meadow["auto"], tr, MMPP)
    b = ST.resolver(meadow["rgb"], meadow["auto"], tr, MMPP, solver="limiar")
    assert d["solver"] == ST.SOLVER_OMISSAO
    iou_d, iou_b = _iou(meadow["gt"], d["mask"]), _iou(meadow["gt"], b["mask"])
    assert iou_d >= 0.99 and iou_d >= iou_b, (iou_d, iou_b)
    assert abs(d["area_mm2"] - meadow["gt"].sum() * MMPP * MMPP) < 3.0


def test_meadow_incerto_lasso_threshold_baseline(meadow):
    """An ``incerto`` lasso over the patch (dilated 1 mm) lets the threshold decide there: >= 0.99."""
    zone = cv2.dilate(meadow["patch"].astype(np.uint8), np.ones((25, 25), np.uint8)) > 0
    tr = _norm([{"ferramenta": "laco", "marca": "incerto", "pontos": c} for c in _outer(zone)])
    r = ST.resolver(meadow["rgb"], meadow["auto"], tr, MMPP, solver="limiar")
    assert _iou(meadow["gt"], r["mask"]) >= 0.99


def test_undo_prefix_gives_previous_result_and_deterministic(meadow):
    inner = cv2.erode(meadow["patch"].astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    a = {"ferramenta": "laco", "marca": "peca", "pontos": _outer(inner)[0]}
    ys, xs = np.nonzero(meadow["gt"])
    cut = {"ferramenta": "pincel", "marca": "fundo", "raio_px": 10.0,
           "pontos": [[float(xs.min()), float(ys.mean())], [float(xs.min()) + 40, float(ys.mean())]]}
    full = _norm([a, cut])
    r1 = ST.resolver(meadow["rgb"], meadow["auto"], full[:1], MMPP)
    r2 = ST.resolver(meadow["rgb"], meadow["auto"], full, MMPP)
    r3 = ST.resolver(meadow["rgb"], meadow["auto"], full[:1], MMPP)
    assert not np.array_equal(r1["mask"], r2["mask"])
    assert np.array_equal(r1["mask"], r3["mask"]) and np.array_equal(r1["contour"], r3["contour"])


@pytest.mark.parametrize("solver", ["grabcut", "watershed", "limiar"])
def test_every_solver_keeps_a_clean_piece(meadow, solver):
    """No stroke on a flat-colour piece: every solver returns one filled polygon close to the GT
    outside the eaten corner (the patch excluded from the comparison)."""
    r = ST.resolver(meadow["rgb"], meadow["auto"], [], MMPP, solver=solver)
    keep = ~(cv2.dilate(meadow["patch"].astype(np.uint8), np.ones((31, 31), np.uint8)) > 0)
    assert _iou(meadow["gt"] & keep, r["mask"] & keep) >= 0.98
    assert len(r["contour"]) >= 20 and r["ms"] > 0


# ---------------------------------------------------------------- convention of the index (normalizar_indice)
@pytest.fixture(scope="module")
def meadow_sombra():
    """The meadow scan with a 0.8 mm cast shadow down-left of every piece; the automatic contour is the
    segment_scan one (it includes the shadow, as the real index does)."""
    from synth import meadow_scan
    from src.segmentation import segment_scan
    img, gts, patch = meadow_scan(sombra_mm=0.8)
    rgb = np.asarray(img)
    off = segment_scan(img, dpi=300, normalize_rotation=False, recover_bays=False)
    best = None
    for p in off["pieces"]:
        m = M.fill_contour(np.asarray(p["contour"]).reshape(-1, 2), gts[1].shape)
        iou = (m & gts[1]).sum() / (m | gts[1]).sum()
        if best is None or iou > best[0]:
            best = (iou, m)
    ys, xs = np.nonzero(gts[1] | best[1])
    pad = 36
    sl = (slice(ys.min() - pad, ys.max() + pad), slice(xs.min() - pad, xs.max() + pad))
    return {"rgb": np.ascontiguousarray(rgb[sl]), "auto": best[1][sl], "gt": gts[1][sl], "auto_iou": float(best[0])}


def test_normalizar_no_stroke_is_identity(meadow, meadow_sombra):
    """Without strokes the saved mask IS the automatic one (bit for bit), whatever δ is; the raw path differs."""
    for mw in (meadow, meadow_sombra):
        r = ST.resolver(mw["rgb"], mw["auto"], [], MMPP, normalizar_indice=True)
        assert r["identidade"] is True and np.array_equal(r["mask"], mw["auto"])
        assert r["tracos_ignorados"] == []
        raw = ST.resolver(mw["rgb"], mw["auto"], [], MMPP)
        assert not np.array_equal(raw["mask"], mw["auto"])        # the solver finds the edge, not the convention


def test_delta_peca_measures_the_shadow(meadow, meadow_sombra):
    """δ ≈ 0 on the flat scan (dead-zone), > 0 with the shadow; the halo lies where the shadow is."""
    d0 = ST.delta_peca(meadow["rgb"], meadow["auto"], MMPP)
    ds = ST.delta_peca(meadow_sombra["rgb"], meadow_sombra["auto"], MMPP)
    assert d0["delta_mm"] == 0.0 and abs(d0["delta_bruto_mm"]) < 0.15
    assert 0.1 <= ds["delta_mm"] <= 0.6, ds
    halo_mm2 = ds["halo"].sum() * MMPP * MMPP
    assert halo_mm2 > 10.0                                           # the shadow band of two sides
    assert (ds["halo"] & meadow_sombra["gt"]).sum() <= 0.15 * ds["halo"].sum()  # ... and not the piece


def test_fundo_on_the_shadow_line_is_a_no_op(meadow_sombra):
    """A ``fundo`` brush along the shadow (inside the automatic, outside the true piece) is a shadow stroke:
    ignored, listed, and the saved mask stays the automatic one."""
    mw = meadow_sombra
    shadow = mw["auto"] & ~mw["gt"]
    ys, xs = np.nonzero(shadow)
    # the left shadow strip: a vertical brush through its middle
    x = float(np.percentile(xs, 5)) + 2
    sel = np.abs(xs - x) < 3
    tr = _norm([{"ferramenta": "pincel", "marca": "fundo", "raio_px": 4.0,
                 "pontos": [[x, float(ys[sel].min() + 10)], [x, float(ys[sel].max() - 10)]]}])
    r = ST.resolver(mw["rgb"], mw["auto"], tr, MMPP, normalizar_indice=True)
    assert r["tracos_ignorados"] == [0] and r["identidade"] is True
    assert np.array_equal(r["mask"], mw["auto"])
    raw = ST.resolver(mw["rgb"], mw["auto"], tr, MMPP)
    assert (mw["auto"] & ~raw["mask"]).sum() * MMPP * MMPP > 5.0    # the raw path does cut the shadow


def test_normalizar_keeps_auto_outside_influence_and_the_peca_gain(meadow):
    """A ``peca`` lasso in the eaten corner: the saved mask equals the automatic one outside the lasso's
    influence region and recovers the corner inside it (IoU vs GT as good as the raw path, ±0.01)."""
    inner = cv2.erode(meadow["patch"].astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    tr = _norm([{"ferramenta": "laco", "marca": "peca", "pontos": c} for c in _outer(inner)])
    n = ST.resolver(meadow["rgb"], meadow["auto"], tr, MMPP, normalizar_indice=True)
    raw = ST.resolver(meadow["rgb"], meadow["auto"], tr, MMPP)
    assert n["identidade"] is False and n["tracos_ignorados"] == []
    outside = ~n["influencia"]
    assert np.array_equal(n["mask"][outside], meadow["auto"][outside])
    assert _iou(meadow["gt"], n["mask"]) >= _iou(meadow["gt"], raw["mask"]) - 0.01
    assert (n["mask"] & meadow["patch"]).sum() >= 0.95 * meadow["patch"].sum()
    assert len(n["aresta"]) >= 20 and n["delta_mm"] == 0.0


def test_deep_fundo_cut_survives_normalisation(meadow):
    """A ``fundo`` brush carving a notch from the edge well into the piece colour (not shadow) still cuts:
    the convention protects the halo only. (A brush fully inside the piece is a hole: ``limpar`` fills it
    on both paths, by design.)"""
    ys, xs = np.nonzero(meadow["gt"])
    cy = float(np.median(ys))
    x0 = float(xs[np.abs(ys - cy) < 2].min())
    tr = _norm([{"ferramenta": "pincel", "marca": "fundo", "raio_px": 6.0, "pontos": [[x0 - 15, cy], [x0 + 45, cy]]}])
    n = ST.resolver(meadow["rgb"], meadow["auto"], tr, MMPP, normalizar_indice=True)
    assert n["tracos_ignorados"] == [] and n["identidade"] is False
    cut = meadow["auto"] & ~n["mask"]
    assert cut.sum() * MMPP * MMPP > 3.0
    assert np.array_equal(n["mask"][~n["influencia"]], meadow["auto"][~n["influencia"]])


def test_normalizar_drops_small_gains_instead_of_growing_them():
    """A sliver gained beyond the automatic (< GANHO_MIN_MM2) is edge noise: the saved mask keeps the
    automatic there and does not grow it by δ (P0045, 2026-11-09: 0.75 mm² would have become 4.2 mm² of
    paper); a large gain (a recovered bite) is kept and grown."""
    h, w = 200, 200
    auto = np.zeros((h, w), bool)
    auto[50:150, 50:150] = True
    infl = np.zeros((h, w), bool)
    infl[30:170, 120:170] = True
    halo = np.zeros((h, w), bool)
    sliver = auto.copy()
    sliver[90:94, 150:153] = True                                   # 12 px ≈ 0.09 mm²
    out = ST.normalizar(sliver, auto, halo, infl, 0.5, MMPP)
    base = ST.normalizar(auto, auto, halo, infl, 0.5, MMPP)        # the same region without the sliver
    assert np.array_equal(out, base) and not (out & ~auto).any()
    bite = auto.copy()
    bite[70:130, 150:160] = True                                    # 600 px ≈ 4.3 mm²
    out = ST.normalizar(bite, auto, halo, infl, 0.5, MMPP)
    gained = (out & ~auto).sum() * MMPP * MMPP
    assert gained > 4.3                                             # kept and grown by δ
    assert np.array_equal(out[~infl], auto[~infl])
