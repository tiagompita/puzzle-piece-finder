"""Tests for the web GUI server (:mod:`src.server`) on a synthetic project (fast).

The project is the one of ``tests/test_query.py`` (a placed piece, its loose twin scanned
at another angle and a decoy; the real ``find_twin`` without the image proposes the twin).
Writes go through ``POST /api/confirm`` and must keep ``board == replay(log)`` and the
invariants. The legend test checks that every ``b-*`` class used by ``src/web`` (the SVG
overlay of the board) has a row in :data:`src.server.LEGEND` and vice versa.
"""

import os
import re
import time

import cv2
import numpy as np
import pytest
from PIL import Image

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from src import server as S  # noqa: E402
from src.state import Project, replay  # noqa: E402
from test_query import _project  # noqa: E402

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "web")


@pytest.fixture
def env(tmp_path):
    from src.query import run_query
    pr, placed, tw, dec = _project(tmp_path)
    run_query(pr, use_image=False)
    gui = S.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "uploads"), log=None)
    return gui, TestClient(S.create_app(gui)), placed, tw, dec


def _ok_on_disk(path):
    pr = Project.open(path)
    assert pr.check_invariants(disk=True) == []
    rb, _ = replay(pr.log_path, pr.profile)
    assert rb == pr.board
    return pr


def _jpeg_shape(content):
    assert content[:2] == b"\xff\xd8"
    img = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
    return img.shape


# ---------------------------------------------------------------- pure helpers
def test_changed_cells_and_patch_regions():
    a = [("vazia", None)] * 12
    b = list(a)
    b[0] = ("colocada", "P0001")
    b[7] = ("ocupada_legado", None)
    assert S.changed_cells(a, b, cols=4) == [(1, 1), (2, 4)]
    assert S.patch_regions([(1, 1), (2, 4)], rows=3, cols=4) == [(1, 1, 2, 2), (1, 3, 3, 4)]


# ---------------------------------------------------------------- reads
def test_board_json_and_raster(env):
    gui, cl, placed, tw, dec = env
    r = cl.get("/api/board")
    assert r.status_code == 200
    b = r.json()
    assert (b["rows"], b["cols"]) == (4, 6) and len(b["cells"]) == 4 and len(b["cells"][0]) == 6
    assert b["cells"][1][2] == {"estado": "colocada", "peca_id": placed, "fonte": "log"}
    assert b["progresso"]["colocadas"] == 1 and b["progresso"]["total"] == 24
    assert {row["id"] for row in b["legend"]} >= {"peca", "vazia", "fantasma", "buscar", "borda", "selecao"}
    assert len(b["borda_em_falta"]) == 16                      # 4 x 6 grid: every border cell is empty
    r = cl.get("/api/board.jpg?ppc=60")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert _jpeg_shape(r.content)[:2] == (240, 360)
    small = cl.get("/api/board.jpg?ppc=10")
    assert _jpeg_shape(small.content)[:2] == (40, 60)
    reg = cl.get("/api/board.jpg?ppc=120&region=2,2,3,4")
    assert _jpeg_shape(reg.content)[:2] == (240, 360)
    assert cl.get("/api/board.jpg?ppc=200").status_code == 400          # full board above MAX_FULL_PPC
    assert os.path.exists(gui.pr.p("render", "gui", "board_60.jpg"))


def test_fetch_cell_pieces_sheets_ghosts_lots(env):
    gui, cl, placed, tw, dec = env
    f = cl.get("/api/fetch").json()
    e = next(x for x in f["entries"] if x["piece"] == tw)
    assert e["cell"] == [3, 4] and e["decision"] == "aceite" and e["razoes_txt"]
    assert any("forma" in t for t in e["razoes_txt"])
    c = cl.get("/api/cell/3/4").json()
    assert c["estado"] == "vazia" and c["gemea"]["cell"] == [2, 3] and c["gemea"]["peca"]["id"] == placed
    assert [p["piece"] for p in c["propostas"]] == [tw]
    assert c["fantasma"] is not None and c["fantasma"]["piece"] == placed
    assert cl.get("/api/cell/9/9").status_code == 404
    z = cl.get("/api/cell/3/4/zoom.jpg?side=both&dpi=100")
    assert z.status_code == 200 and z.content[:2] == b"\xff\xd8"
    g = cl.get("/api/ghosts").json()
    assert [x["cell"] for x in g["fantasmas"]] == [[3, 4]] and g["rotacao_gemea_deg"] == 180.0
    assert len(g["fantasmas"][0]["path"]) >= 20
    p = cl.get(f"/api/pieces/{tw}").json()
    assert p["estado"] == "solta" and p["pose_origem"] == "proposta"
    assert abs(p["pose_tabuleiro"] - e["theta_deg"]) < 1e-6
    png = cl.get(f"/api/pieces/{tw}.png?pose=board&size=120")
    assert png.status_code == 200 and png.headers["x-pose"] == "board" and png.content[:4] == b"\x89PNG"
    png2 = cl.get(f"/api/pieces/{placed}.png?pose=scan&size=64")
    assert png2.headers["x-pose"] == "scan"
    assert cl.get("/api/pieces/P9999").status_code == 404
    sh = cl.get(f"/api/sheets/{gui.pr.piece(tw).scan_id}.jpg?highlight={tw}&max=400")
    assert sh.status_code == 200 and max(_jpeg_shape(sh.content)[:2]) <= 400
    lots = cl.get("/api/lots").json()
    assert [x["lote"] for x in lots] == [3]
    assert lots[0]["n"] == 3 and len(lots[0]["folhas"]) == 1
    assert {q["id"]: q["estado"] for q in lots[0]["pecas"]} == {placed: "colocada", tw: "solta", dec: "solta"}
    assert cl.get("/api/sections").json() == []
    st = cl.get("/api/status").json()
    assert st["estado"] == "pronto" and st["job"] is None


# ---------------------------------------------------------------- writes
def test_confirm_place_then_unplace(env):
    gui, cl, placed, tw, dec = env
    before = cl.get("/api/board.jpg?ppc=60").content
    seq0 = gui.seq
    r = cl.post("/api/confirm", json={"acao": "place", "piece": tw, "cell": [3, 4]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] and d["invariantes"] == [] and d["celulas_mudadas"] == [[3, 4]]
    names = [n for _, n, _ in gui.events_after(seq0)]
    assert "board_changed" in names and "fetch_changed" in names
    pr = _ok_on_disk(gui.path)
    assert pr.board[(3, 4)]["estado"] == "colocada" and pr.board[(3, 4)]["peca_id"] == tw
    assert any(ev["action"] == "twin_confirmed" and ev["piece"] == tw for ev in pr.events())
    assert cl.get("/api/board").json()["cells"][2][3]["peca_id"] == tw
    after = cl.get("/api/board.jpg?ppc=60").content                    # patched raster
    assert after != before and _jpeg_shape(after)[:2] == (240, 360)
    assert not [x for x in cl.get("/api/fetch").json()["entries"] if x["piece"] == tw]
    assert cl.get("/api/cell/3/4").json()["pode_desfazer"] is True
    # placing on an occupied cell is refused, nothing logged
    n_log = len(pr.events())
    r = cl.post("/api/confirm", json={"acao": "place", "piece": dec, "cell": [3, 4]})
    assert r.status_code == 400 and "já tem" in r.json()["error"]
    assert len(Project.open(gui.path).events()) == n_log
    # undo
    r = cl.post("/api/confirm", json={"acao": "unplace", "piece": tw})
    assert r.status_code == 200, r.text
    pr = _ok_on_disk(gui.path)
    assert pr.board[(3, 4)]["estado"] == "vazia" and pr.piece(tw).estado == "solta"


def test_confirm_place_applies_proposal_pose(env):
    """'Coloquei' keeps the list's pose: the log, the registration and the card all show it."""
    from src.query import wrap180
    gui, cl, placed, tw, dec = env
    e = next(x for x in cl.get("/api/fetch").json()["entries"] if x["piece"] == tw)
    assert e["pose_known"] and e["theta_deg"] is not None
    r = cl.post("/api/confirm", json={"acao": "place", "piece": tw, "cell": [3, 4]})
    assert r.status_code == 200, r.text
    pr = _ok_on_disk(gui.path)
    ev = [x for x in pr.events() if x["action"] == "placed" and x["piece"] == tw][-1]
    assert ev["theta_deg"] == pytest.approx(e["theta_deg"])
    png = cl.get(f"/api/pieces/{tw}.png?pose=board&size=120")
    assert png.headers["x-pose"] == "board"
    assert abs(wrap180(float(png.headers["x-pose-theta"]) - e["theta_deg"])) <= 2.0
    p = cl.get(f"/api/pieces/{tw}").json()
    assert p["pose_origem"] == "registo" and abs(wrap180(p["pose_tabuleiro"] - e["theta_deg"])) <= 2.0
    # undo: the pose goes with the placement
    assert cl.post("/api/confirm", json={"acao": "unplace", "piece": tw}).status_code == 200
    assert Project.open(gui.path).piece(tw).theta_deg is None


def test_confirm_reject_position_known_discard_and_errors(env):
    gui, cl, placed, tw, dec = env
    r = cl.post("/api/confirm", json={"acao": "position_known", "piece": tw, "cell": [3, 4]})
    assert r.status_code == 200, r.text
    pr = _ok_on_disk(gui.path)
    assert pr.piece(tw).estado == "posicao_conhecida" and pr.piece(tw).celula == (3, 4)
    assert cl.get("/api/board").json()["posicoes_conhecidas"][0]["piece"] == tw
    r = cl.post("/api/confirm", json={"acao": "discard", "piece": dec})
    assert r.status_code == 200 and Project.open(gui.path).piece(dec).estado == "descartada"
    assert cl.post("/api/confirm", json={"acao": "voar", "piece": tw}).status_code == 400
    assert cl.post("/api/confirm", json={"acao": "place", "piece": "P9999", "cell": [1, 1]}).status_code == 400
    assert cl.post("/api/confirm", json={"acao": "reject", "piece": dec}).status_code == 400   # no proposal
    gui.job = "importar x"
    assert cl.post("/api/confirm", json={"acao": "discard", "piece": tw}).status_code == 409
    gui.job = None
    _ok_on_disk(gui.path)


def test_confirm_cell_full_and_empty(env):
    """User hints: 'cell_full' blocks the twin proposal of that cell, 'cell_empty' gives it back."""
    gui, cl, placed, tw, dec = env
    assert any(e["piece"] == tw and e["cell"] == [3, 4] for e in cl.get("/api/fetch").json()["entries"])
    r = cl.post("/api/confirm", json={"acao": "cell_full", "cell": [3, 4]})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["celula"]["estado"] == "ocupada_legado" and j["celula"]["pista"] and not j["celula"]["por_confirmar"]
    assert "marcada por ti" in j["celula"]["estado_txt"]
    assert [3, 4] in j["celulas_mudadas"]
    assert {v["dir"] for v in j["vizinhas"]} == {"N", "E", "S", "O"}
    assert next(v for v in j["vizinhas"] if v["cell"] == [2, 4])["ocupada"] is False
    pr = _ok_on_disk(gui.path)
    assert pr.board[(3, 4)] == {"estado": "ocupada_legado", "peca_id": None, "fonte": "tiago", "foto_id": None}
    assert not any(e["piece"] == tw and e["cell"] == [3, 4] for e in cl.get("/api/fetch").json()["entries"])
    assert cl.get("/api/board").json()["cells"][2][3]["fonte"] == "tiago"
    # empty again (the user's word): the twin proposal comes back
    r = cl.post("/api/confirm", json={"acao": "cell_empty", "cell": [3, 4]})
    assert r.status_code == 200, r.text
    assert r.json()["celula"]["estado"] == "vazia" and "marcada por ti" in r.json()["celula"]["estado_txt"]
    assert any(e["piece"] == tw and e["cell"] == [3, 4] for e in cl.get("/api/fetch").json()["entries"])
    # errors: a placed cell cannot be marked empty; the cell is required and must be in the grid
    assert cl.post("/api/confirm", json={"acao": "cell_empty", "cell": [2, 3]}).status_code == 400
    assert cl.post("/api/confirm", json={"acao": "cell_full"}).status_code == 400
    assert cl.post("/api/confirm", json={"acao": "cell_full", "cell": [9, 9]}).status_code == 400
    _ok_on_disk(gui.path)


def test_legend_row_legado_says_unconfirmed():
    row = next(r for r in S.LEGEND if r["id"] == "legado")
    assert row["texto"] == "cheia na foto, por confirmar" and "marcada por ti" in row["detalhe"]
    assert S.cell_text({"estado": "ocupada_legado", "fonte": "foto"}).startswith("cheia na foto, por confirmar")
    assert S.cell_text({"estado": "ocupada_legado", "fonte": "tiago"}).startswith("montada, marcada por ti")


def test_section_png_no_green_fringe(tmp_path):
    """Mesa thumbnails: the crops of a group come cleaned (no 0.5 mm green rim of the scan)."""
    import json
    from src.render import _depth_px, _lab
    from test_query import BG
    from test_shape import MMPP
    pr, placed, tw, dec = _project(tmp_path)
    bg_lab = _lab(np.array([[BG]], np.uint8))[0, 0]
    fp = pr.p("puzzle.json")
    with open(fp, encoding="utf-8") as f:
        js = json.load(f)
    js["background_lab"] = [float(v) for v in bg_lab]                 # the paper of the synthetic scan
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(js, f)
    for pid in (tw, dec):                                             # scan fringe: 0.5 mm of paper inside alpha
        cp = pr.p(pr.piece(pid).crop_path)
        rgba = np.asarray(Image.open(cp).convert("RGBA")).copy()
        rim = (rgba[..., 3] > 0) & (_depth_px(rgba[..., 3] > 0) <= 0.5 / MMPP)
        rgba[rim, :3] = BG
        Image.fromarray(rgba).save(cp)
    pr = Project.open(pr.path)
    gid = pr.register_section(None, "blocos", {tw: (1, 1), dec: (1, 2)})
    pr.save()
    gui = S.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "uploads"), log=None)
    cl = TestClient(S.create_app(gui))
    r = cl.get(f"/api/sections/{gid}.png?max=1000")
    assert r.status_code == 200 and r.content[:4] == b"\x89PNG"
    img = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
    d = np.linalg.norm(_lab(img[..., ::-1]) - bg_lab, axis=-1)
    assert (d < 20).sum() == 0, f"{(d < 20).sum()} background-coloured pixels in the thumbnail"
    assert (img.max(-1) > 80).sum() > 1000                            # the pieces are there


def test_ingest_endpoint(env, tmp_path):
    gui, cl, placed, tw, dec = env
    bg = np.full((900, 1300, 3), (40, 160, 60), np.uint8)
    for x, y, col in ((300, 320, (200, 40, 40)), (700, 330, (40, 60, 200))):
        bg[y:y + 210, x:x + 220] = col
    fp = tmp_path / "saco5.png"
    Image.fromarray(bg).save(fp)
    with open(fp, "rb") as f:
        r = cl.post("/api/ingest", files={"file": ("saco 5.png", f, "image/png")}, data={"lote": "5", "dpi": "300"})
    assert r.status_code == 200, r.text
    assert os.path.basename(r.json()["ficheiro"]).startswith("lote05_")
    t0 = time.time()
    while gui.job and time.time() - t0 < 120:
        time.sleep(0.2)
    assert gui.job is None
    msgs = [d.get("etapa") for _, n, d in gui.events_after(0) if n == "ingest_progress"]
    assert msgs[0] == "segmentar" and msgs[-1] == "pronto", gui.job_log
    lots = {x["lote"]: x for x in cl.get("/api/lots").json()}
    assert lots[5]["n"] == 2 and [q["n_no_lote"] for q in lots[5]["pecas"]] == [1, 2]
    assert os.path.exists(os.path.join(gui.uploads, os.listdir(gui.uploads)[0]))
    _ok_on_disk(gui.path)


# ---------------------------------------------------------------- start-up rule
def test_prepare_runs_rebuild_when_assets_missing(env, monkeypatch):
    gui, cl, placed, tw, dec = env
    import shutil
    from src import render
    shutil.rmtree(gui.pr.p("render"), ignore_errors=True)
    assert "render" in S.missing_assets(gui.pr)
    calls = []

    def fake_rebuild(project, progress=print, **kw):
        calls.append(project.path)
        progress("regenerado (falso)")
        os.makedirs(project.p("render"), exist_ok=True)
        return {"scans": {}, "errors": [], "overlays": []}

    monkeypatch.setattr(render, "rebuild_assets", fake_rebuild)
    g2 = S.Gui(gui.path, prepare=True, use_image=False, log=None)
    t0 = time.time()
    while not any(n == "ready" for _, n, _ in g2.events_after(0)) and time.time() - t0 < 60:
        time.sleep(0.1)
    assert calls == [g2.path] and g2.state == "pronto"
    assert any("regenerado (falso)" in m for m in g2.prep_log)
    assert os.path.exists(g2.pr.p("render", "gui", "board_60.jpg"))


# ---------------------------------------------------------------- legend coverage
def test_legend_covers_every_board_class():
    css = open(os.path.join(WEB, "app.css"), encoding="utf-8").read()
    js = open(os.path.join(WEB, "app.js"), encoding="utf-8").read()
    html = open(os.path.join(WEB, "index.html"), encoding="utf-8").read()
    pat = re.compile(r"(?<![\w-])b-[a-z][a-z-]*[a-z]")
    used = set(pat.findall(css)) | set(pat.findall(js)) | set(pat.findall(html))
    legend = {row["classe"] for row in S.LEGEND if row["classe"]}
    assert used, "no b-* class found in src/web"
    assert used <= legend, f"classes without a legend row: {sorted(used - legend)}"
    assert legend <= set(pat.findall(css)), f"legend rows without a style: {sorted(legend - set(pat.findall(css)))}"
    ids = {row["id"] for row in S.LEGEND}
    for i in re.findall(r'cls\("([a-z_]+)"\)', js):
        assert i in ids, f"app.js uses legend id {i!r} not in LEGEND"
    assert all(row["rotulo"] and row["texto"] for row in S.LEGEND)


# ---------------------------------------------------------------- item 6: coloca agora / guarda com posição
def _twin_entry(client):
    es = [e for e in client.get("/api/fetch").json()["entries"] if e.get("piece")]
    assert es
    return es[0]


def test_fetch_group_guarda_posicao_without_neighbour(env):
    gui, client, placed, tw, dec = env
    e = _twin_entry(client)
    assert e["vizinhas_montadas"] == 0
    assert e["grupo"] == "guarda_posicao"


def test_fetch_group_foto_neighbour_does_not_count(env):
    gui, client, placed, tw, dec = env
    e = _twin_entry(client)
    l, c = e["cell"]
    nb = gui.pr.board.neighbours((l, c))[0]
    gui.pr.log_event("cell_occupied_by_photo", cell=list(nb), photo="F0001")
    assert gui.pr.board[nb]["estado"] == "ocupada_legado"
    gui._known_stat = gui._log_stat()
    e = _twin_entry(client)
    assert e["vizinhas_montadas"] == 0 and e["grupo"] == "guarda_posicao"


def test_fetch_group_coloca_agora_with_placed_neighbour(env):
    gui, client, placed, tw, dec = env
    e = _twin_entry(client)
    l, c = e["cell"]
    nb = [n for n in gui.pr.board.neighbours((l, c)) if gui.pr.board[n]["estado"] == "vazia"][0]
    gui.pr.place(dec, nb, theta_deg=0.0)
    gui.pr.save()
    gui._known_stat = gui._log_stat()
    e = _twin_entry(client)
    assert e["vizinhas_montadas"] >= 1 and e["grupo"] == "coloca_agora"


# ---------------------------------------------------------------- item 9: reportar
def test_report_roundtrip(env):
    from src import reports
    gui, client, placed, tw, dec = env
    ver = gui.version()
    r = client.post("/api/report", json={"tipo": "mal_lida", "texto": "recorte cortado", "piece": placed,
                                         "cell": [2, 3], "vista": "celula"})
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["id"] == "R0001" and rep["estado"] == "aberto" and rep["piece"] == placed
    assert os.path.exists(gui.pr.p(rep["captura"]))
    assert os.path.exists(os.path.join(gui.path, "reports.jsonl"))
    acts = [ev["action"] for ev in gui.pr.events()]
    assert "report" in acts
    assert gui.version() > ver and gui._known_stat == gui._log_stat()     # our own write: no reopen
    got = client.get("/api/reports").json()["reports"]
    assert [x["id"] for x in got] == ["R0001"]
    assert client.post("/api/report", json={"tipo": "xx"}).status_code == 400
    # a second report of a piece without cell uses the piece crop
    r2 = client.post("/api/report", json={"tipo": "outro", "piece": tw}).json()
    assert r2["id"] == "R0002" and r2["captura"].endswith(".png")
    # close
    c = reports.close_report(gui.pr, "R0001", "feito")
    assert c["estado"] == "fechado" and c["nota"] == "feito"
    assert "report_closed" in [ev["action"] for ev in gui.pr.events()]
    assert [x["id"] for x in reports.list_reports(gui.pr)] == ["R0002"]
    assert "error" in reports.close_report(gui.pr, "R0001")
    # reopen and replay with report events
    pr = _ok_on_disk(gui.path)
    assert len(reports.list_reports(pr, only_open=False)) == 2
