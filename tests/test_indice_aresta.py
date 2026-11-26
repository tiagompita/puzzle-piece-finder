"""R0036 (P0395): the index silhouette of an ``aresta+indice`` override read against the painted edge.

The edge the user painted (``aresta_px``) is exact (D5, 2026-11-25). The index stored with it (``contour_px``) is
derived by the editor (``src.strokes.normalizar``) and, for P0395, kept the automatic contour's mistakes: a 37 mm
wide silhouette with the scanner's dark strip at the bottom of the sheet and the paper between them (13.9 mm away
from the edge; on the 34 other edited pieces the index stays within 1.94 mm of the edge). The index used by the
program must be the edge plus the shadow halo of the index convention, never more than the halo band."""

import json
import os

import cv2
import numpy as np
from PIL import Image

from src import overrides as OV
from src import render as R
from src import shape as SH
from src import strokes as ST
from src.state import Project
from test_query import _project

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "data", "p0395_r0036_override.json")
MMPP = 25.4 / 300


def _p0395():
    with open(FIX, encoding="utf-8") as f:
        ov = json.load(f)
    rgb = np.asarray(Image.open(os.path.join(ROOT, ov["scan_file"])).convert("RGB"))
    return ov, rgb


def _beyond_mm2(index_pts, edge_pts, band_mm, shape_hw):
    """Area (mm²) of the filled ``index_pts`` farther than ``band_mm`` from the filled ``edge_pts``."""
    H, W = shape_hw
    mi = np.zeros((H, W), np.uint8)
    ma = np.zeros((H, W), np.uint8)
    cv2.fillPoly(mi, [np.round(np.asarray(index_pts, float)).astype(np.int32).reshape(-1, 1, 2)], 1)
    cv2.fillPoly(ma, [np.round(np.asarray(edge_pts, float)).astype(np.int32).reshape(-1, 1, 2)], 1)
    d = cv2.distanceTransform((1 - ma).astype(np.uint8), cv2.DIST_L2, 5) * MMPP
    return float(((mi > 0) & (d > band_mm)).sum()) * MMPP * MMPP


def test_p0395_index_is_the_painted_edge_plus_the_halo():
    ov, rgb = _p0395()
    H, W = rgb.shape[:2]
    # the stored index is far outside the painted edge (the bug's input, unchanged)
    assert _beyond_mm2(ov["contour_px"], ov["aresta_px"], 2.0, (H, W)) > 10.0
    idx, info = OV.index_contour_from(ov, rgb, MMPP)
    assert info["limitado"] is True
    assert _beyond_mm2(idx, ov["aresta_px"], ST.INDICE_HALO_MAX_MM, (H, W)) == 0.0
    # the painted edge is inside the index, whole (nothing of it is cut away)
    ma = np.zeros((H, W), np.uint8)
    mi = np.zeros((H, W), np.uint8)
    cv2.fillPoly(ma, [np.round(np.asarray(ov["aresta_px"])).astype(np.int32).reshape(-1, 1, 2)], 1)
    cv2.fillPoly(mi, [np.round(np.asarray(idx)).astype(np.int32).reshape(-1, 1, 2)], 1)
    assert int(((ma > 0) & (mi == 0)).sum()) == 0
    # the scanner strip is gone: nothing within 0.5 mm of the bottom of the sheet
    assert np.asarray(idx)[:, 1].max() < H - 1 - 0.5 / MMPP
    # a border piece of nominal size: one F side, chords 17.5-19.5 mm (nominal 18.5 x 17.9, index +0.3-0.5)
    sh = SH.analyse(idx, MMPP)
    assert sh.ok and sh.n_flat == 1, (sh.cls, sh.lens)
    assert all(17.5 <= L <= 19.5 for L in sh.lens), sh.lens
    # the line itself is untouched
    with open(FIX, encoding="utf-8") as f:
        assert json.load(f)["contour_px"] == ov["contour_px"]


def test_index_within_the_band_is_used_verbatim():
    """A line without ``aresta_px``, or whose index stays within the halo band of its edge, gives back
    ``contour_px`` exactly (the 34 other edited pieces of projects/alpes are of this kind)."""
    ov, rgb = _p0395()
    old = {"contour_px": ov["contour_px"]}
    idx, info = OV.index_contour_from(old, rgb, MMPP)
    assert info["limitado"] is False and idx is old["contour_px"]
    ok = {"contour_px": ov["aresta_px"], "aresta_px": ov["aresta_px"], "convencao": OV.CONVENCAO_ARESTA}
    idx, info = OV.index_contour_from(ok, rgb, MMPP)
    assert info["limitado"] is False and idx is ok["contour_px"]


def _strip_index(pr, pid):
    """The piece's contour plus a 'scanner strip' joined to it by a paper bridge (the P0395 defect), and the
    piece's contour itself as the painted edge."""
    c = np.asarray(pr.contour_px(pid), float)
    x0, y0 = np.floor(c.min(0)).astype(int)
    x1, y1 = np.ceil(c.max(0)).astype(int)
    m = np.zeros((800, 2000), np.uint8)
    cv2.fillPoly(m, [np.round(c).astype(np.int32).reshape(-1, 1, 2)], 1)
    cx = int(round(c[np.argmax(c[:, 1]), 0]))           # under the lowest point of the piece
    m[y1 - 5:y1 + 45, cx - 6:cx + 6] = 1                  # bridge over the paper, 4 mm long
    m[y1 + 40:y1 + 60, cx - 10:cx + 150] = 1              # the strip, 13 mm long
    return ST.mascara_poligono(m > 0).astype(float), c


def test_rebuild_reads_the_index_within_the_edge_band(tmp_path):
    pr, placed, tw, dec = _project(tmp_path)
    sid = pr.piece(tw).scan_id
    idx, edge = _strip_index(pr, tw)
    before = OV.read_overrides(pr)
    rec = OV.append_override(pr, tw, idx, extra={"metodo": "tracos", "aresta_px": edge,
                                                 "convencao": OV.CONVENCAO_ARESTA})
    assert "error" not in rec
    line = OV.read_overrides(pr)[-1]
    out = R.rebuild_piece(pr, tw)
    assert out["errors"] == [] and [x["piece"] for x in out["changed"]] == [tw]
    q = Project.open(pr.path)
    with np.load(q.p("pieces", f"{sid}.npz")) as z:
        cnt = z[f"{tw}__contour_px"]
    assert _beyond_mm2(cnt, edge, ST.INDICE_HALO_MAX_MM, (800, 2000)) == 0.0
    m = np.zeros((800, 2000), np.uint8)                   # the bridge and the strip are paper: only the piece is left
    cv2.fillPoly(m, [np.round(edge).astype(np.int32).reshape(-1, 1, 2)], 1)
    assert abs(q.piece(tw).area_mm2 - m.sum() * MMPP * MMPP) < 0.5
    # the override line is what was written, untouched, and still the latest one
    assert OV.read_overrides(pr)[:len(before)] == before and OV.read_overrides(pr)[-1] == line
    assert OV.latest_overrides(pr)[tw]["contour_px"] == line["contour_px"]
    # applied once: nothing pending, a second rebuild changes nothing
    n = len(q.events())
    assert R.rebuild_piece(q, tw)["changed"] == [] and len(q.events()) == n


# ---------------------------------------------------------------- 4.1 (c) = A (2026-11-26): aresta ⊆ índice, exata
def _square_poly(x0, y0, x1, y1):
    m = np.zeros((400, 400), bool)
    m[y0:y1, x0:x1] = True
    return m


def _poly(m):
    return ST.mascara_poligono(m) + 0.0


def _filled(pts, shape=(400, 400)):
    m = np.zeros(shape, np.uint8)
    cv2.fillPoly(m, [np.round(np.asarray(pts, float)).astype(np.int32).reshape(-1, 1, 2)], 1)
    return m > 0


def _casos_d2():
    """As 3 origens medidas no D2 (verificacao-implementacao-1 §7), em máscaras: o índice derivado e a aresta pintada.
    (1) fora da influência dos traços o índice é o automático e a aresta fica 1–3 px fora dele ao longo de um lado;
    (2) um ganho da aresta < ``GANHO_MIN_MM2`` descartado do índice; (3) um píxel de canto perdido na limpeza."""
    idx = _square_poly(100, 100, 300, 300)
    rim = idx.copy()
    rim[100:300, 300:302] = True                                         # 2 px fora ao longo do lado E
    gain = idx.copy()
    gain[180:190, 300:310] = True                                        # 100 px ≈ 0,72 mm² < GANHO_MIN_MM2
    corner = idx.copy()
    corner[99, 99] = True                                                # 1 px no canto NO
    return idx, {"fora_da_influencia": rim, "ganho_pequeno": gain, "limpeza": corner}


def test_indice_lido_contem_a_aresta_nos_3_casos_do_d2():
    """O índice que o programa lê de uma linha ``aresta+indice`` contém a aresta inteira (0 px fora) e não muda
    mais nada: é ``contour_px`` ∪ aresta. A linha guardada não é tocada."""
    idx, casos = _casos_d2()
    rgb = np.full((400, 400, 3), 200, np.uint8)
    for nome, ar in casos.items():
        ov = {"contour_px": _poly(idx).tolist(), "aresta_px": _poly(ar).tolist(), "convencao": OV.CONVENCAO_ARESTA}
        guardado = json.dumps(ov)
        for img in (None, rgb):                                          # a união é geométrica: não precisa do scan
            out, info = OV.index_contour_from(ov, img, MMPP)
            mo = _filled(out)
            assert int((ar & ~mo).sum()) == 0, nome
            assert np.array_equal(mo, idx | ar), nome
            assert info["aresta_fora_px"] == int((ar & ~idx).sum()) > 0 and info["unido"] is True, nome
        assert json.dumps(ov) == guardado


def test_indice_ja_com_a_aresta_continua_verbatim():
    idx, casos = _casos_d2()
    ov = {"contour_px": _poly(casos["fora_da_influencia"]).tolist(), "aresta_px": _poly(idx).tolist()}
    out, info = OV.index_contour_from(ov, None, MMPP)
    assert out is ov["contour_px"] and info["unido"] is False and info["aresta_fora_px"] == 0


def test_indice_do_editor_lido_contem_a_aresta_fora_da_influencia():
    """Ponta a ponta no prado sintético. Uma linha gravada antes da união na gravação (o índice = só a derivação
    ``normalizar``, que deixa píxeis da aresta fora dele fora da região de influência dos traços: a origem de 86 % no
    D2): o índice lido contém a aresta inteira. O caminho do servidor (``resolver(..., normalizar_indice=True)``)
    já grava um índice que a contém (ronda 2, 2026-11-26)."""
    from synth import meadow_scan
    from src import maskcmp as M
    from src.segmentation import segment_scan
    img, gts, patch = meadow_scan()
    rgb = np.asarray(img)
    off = segment_scan(img, dpi=300, normalize_rotation=False, recover_bays=False)
    best = max((M.fill_contour(np.asarray(p["contour"]).reshape(-1, 2), gts[0].shape) for p in off["pieces"]),
               key=lambda m: (m & gts[0]).sum() / (m | gts[0]).sum())
    ys, xs = np.nonzero(gts[0] | best)
    y0, x0 = ys.min() - 36, xs.min() - 36
    sl = (slice(y0, ys.max() + 36), slice(x0, xs.max() + 36))
    crop, auto, pt = np.ascontiguousarray(rgb[sl]), best[sl], patch[sl]
    inner = cv2.erode(pt.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    cs, _ = cv2.findContours(inner.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    tr, err = ST.validar_tracos([{"ferramenta": "laco", "marca": "peca", "pontos": c.reshape(-1, 2).tolist()} for c in cs])
    assert err is None
    r = ST.resolver(crop, auto, tr, MMPP, normalizar_indice=True)
    assert not (r["mask_aresta"] & ~r["mask"]).any()                    # gravação nova: a aresta já está dentro
    d = ST.delta_peca(crop, auto, MMPP)
    antigo = ST.normalizar(r["mask_bruta"], auto, d["halo"], r["influencia"], r["delta_mm"], MMPP, r["trimap_indice"])
    fora = r["mask_aresta"] & ~antigo
    assert (fora & ~r["influencia"]).sum() > 0                          # o defeito da linha antiga, à entrada
    org = np.array([x0, y0], float)
    ov = {"contour_px": (ST.mascara_poligono(antigo) + org).tolist(), "aresta_px": (r["aresta"] + org).tolist(),
          "convencao": OV.CONVENCAO_ARESTA}
    out, info = OV.index_contour_from(ov, rgb, MMPP)
    H, W = rgb.shape[:2]
    ma, mo, mi = _filled(ov["aresta_px"], (H, W)), _filled(out, (H, W)), _filled(ov["contour_px"], (H, W))
    assert int((ma & ~mo).sum()) == 0
    assert np.array_equal(mo, mi | ma)


def test_arranque_aplica_a_leitura_nova_de_uma_linha_ja_gravada(tmp_path, monkeypatch):
    """Uma linha gravada antes da opção A (npz e log com o índice tal como estava, aresta 2 px fora num lado):
    ``stale_assets`` lista a peça com o motivo ``manual`` e ``rebuild_stale`` (o arranque do servidor) aplica a leitura
    nova com um ``piece_resegmented`` motivo ``manual``, sem re-segmentar a folha; depois nada fica pendente."""
    pr, placed, tw, dec = _project(tmp_path)
    R.rebuild_stale(pr, progress=None)                                    # o projeto sintético nasce desatualizado
    pr = Project.open(pr.path)
    assert R.stale_assets(pr)["n_pecas"] == 0
    sid = pr.piece(tw).scan_id
    c = np.asarray(pr.contour_px(tw), float)
    m = np.zeros((800, 2000), np.uint8)
    cv2.fillPoly(m, [np.round(c).astype(np.int32).reshape(-1, 1, 2)], 1)
    ar = (m > 0) | np.roll(m > 0, 2, axis=1)                             # a aresta 2 px fora ao longo dos lados E
    rec = OV.append_override(pr, tw, c, extra={"metodo": "tracos", "aresta_px": ST.mascara_poligono(ar).astype(float),
                                               "convencao": OV.CONVENCAO_ARESTA})
    assert "error" not in rec
    with monkeypatch.context() as mp:                                     # o código antigo: índice = contour_px, tal e qual
        mp.setattr(OV, "index_contour", lambda project, ov, rgb=None: ov["contour_px"])
        assert R.rebuild_piece(pr, tw)["errors"] == []
    q = Project.open(pr.path)
    st = R.stale_assets(q)
    assert st["pecas"].get(tw) == ["manual"] and list(st["sheets"]) == [sid]
    n0 = len(q.events())
    calls = []
    real_seg = R.rebuild_assets
    monkeypatch.setattr(R, "rebuild_assets", lambda *a, **k: calls.append(k) or real_seg(*a, **k))
    r = R.rebuild_stale(q, progress=None)
    assert r["errors"] == [] and [x["piece"] for x in r["changed"]] == [tw]
    assert calls and not calls[0].get("force_scans")                     # só a linha manual: a folha não é re-segmentada
    ev = q.events()[n0:]
    assert [(e["action"], e.get("piece"), e.get("motivo")) for e in ev] == [("piece_resegmented", tw, "manual")]
    assert r["depois"]["n_pecas"] == 0
    with np.load(q.p("pieces", f"{sid}.npz")) as z:
        cnt = z[f"{tw}__contour_px"]
    mi = np.zeros((800, 2000), np.uint8)
    cv2.fillPoly(mi, [cnt.reshape(-1, 1, 2)], 1)
    assert int((ar & (mi == 0)).sum()) == 0
