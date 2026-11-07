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
    # the hand-made pieces of _project (bbox +10 px, polygon area) are not what an ingest writes: keep the
    # stale-asset check of the start-up (test_prepare_rebuilds_stale_assets_after_pull) out of this test
    monkeypatch.setattr(render, "stale_assets", lambda project: {"sheets": {}, "pecas": {}, "n_pecas": 0, "n_folhas": 0})
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


def test_report_edit_endpoint(env):
    """``POST /api/report/{id}/edit`` appends an edit event (append-only) and returns the edited report."""
    gui, client, placed, tw, dec = env
    rep = client.post("/api/report", json={"tipo": "outro", "texto": "primeiro", "piece": tw}).json()
    with open(os.path.join(gui.path, "reports.jsonl"), encoding="utf-8") as f:
        before = f.read().splitlines()
    r = client.post(f"/api/report/{rep['id']}/edit", json={"tipo": "nao_encaixa", "texto": "segundo"})
    assert r.status_code == 200, r.text
    assert r.json()["texto"] == "segundo" and r.json()["tipo"] == "nao_encaixa" and r.json()["n_edicoes"] == 1
    with open(os.path.join(gui.path, "reports.jsonl"), encoding="utf-8") as f:
        after = f.read().splitlines()
    assert after[:len(before)] == before and len(after) == len(before) + 1
    assert gui._known_stat == gui._log_stat()                                   # our own write: no reopen
    assert client.post("/api/report/R9999/edit", json={"texto": "x"}).status_code == 404
    assert client.post(f"/api/report/{rep['id']}/edit", json={"tipo": "xx"}).status_code == 400


def test_report_edit_endpoint_rejects_bad_types(env):
    """A body that is not an object, or ``tipo`` / ``texto`` that are not strings, answer 400 (never 500) and
    write nothing."""
    gui, client, placed, tw, dec = env
    rep = client.post("/api/report", json={"tipo": "outro", "texto": "x", "piece": tw}).json()
    path = os.path.join(gui.path, "reports.jsonl")
    n0 = open(path, encoding="utf-8").read()
    url = f"/api/report/{rep['id']}/edit"
    bad = [["tipo", "texto"], "texto", 3, None,                       # body not an object
           {"tipo": ["mal_lida"]}, {"tipo": {"a": 1}}, {"tipo": 3},   # tipo not a string (a list used to be a 500)
           {"texto": 3}, {"texto": ["a"]}, {"texto": {"a": 1}}]       # texto not a string
    for body in bad:
        r = client.post(url, json=body)
        assert r.status_code == 400, (body, r.status_code, r.text)
    assert open(path, encoding="utf-8").read() == n0


def test_report_estado_endpoint(env):
    """``POST /api/report/{id}/estado``: close / reopen / delete / restore, each one a single appended line in
    ``reports.jsonl`` and one in the log; 404 for unknown, 400 for invalid transitions."""
    gui, client, placed, tw, dec = env
    rep = client.post("/api/report", json={"tipo": "outro", "texto": "x", "piece": tw}).json()
    rid, path = rep["id"], os.path.join(gui.path, "reports.jsonl")

    def lines():
        with open(path, encoding="utf-8") as f:
            return f.read().splitlines()

    def go(acao, nota=None):
        before, ver = lines(), gui.version()
        body = {"acao": acao} if nota is None else {"acao": acao, "nota": nota}
        r = client.post(f"/api/report/{rid}/estado", json=body)
        if r.status_code == 200:
            after = lines()
            assert after[:len(before)] == before and len(after) == len(before) + 1
            assert gui._known_stat == gui._log_stat()                               # our own write: no reopen
        return r

    r = go("close", "feito")
    assert r.status_code == 200 and r.json()["estado"] == "fechado" and r.json()["nota"] == "feito"
    assert go("close").status_code == 400
    assert go("reopen").json()["estado"] == "aberto"
    assert go("delete").json()["estado"] == "eliminado"
    assert client.get("/api/reports?todos=true").json()["reports"] == []
    assert [x["id"] for x in client.get("/api/reports?todos=true&eliminados=true").json()["reports"]] == [rid]
    assert go("restore").json()["estado"] == "aberto"
    assert go("restore").status_code == 400
    assert go("explodir").status_code == 400
    assert client.post("/api/report/R9999/estado", json={"acao": "close"}).status_code == 404
    for bad in (["close"], 3, {"acao": 3}, {}, {"acao": "close", "nota": 3}):
        assert client.post(f"/api/report/{rid}/estado", json=bad).status_code == 400, bad
    acts = [ev["action"] for ev in gui.pr.events()]
    for a in ("report_closed", "report_reopened", "report_deleted", "report_restored"):
        assert a in acts
    _ok_on_disk(gui.path)


def test_report_captura_endpoint(env):
    gui, client, placed, tw, dec = env
    r1 = client.post("/api/report", json={"tipo": "outro", "cell": [2, 3]}).json()        # jpg capture of the cell
    r2 = client.post("/api/report", json={"tipo": "outro", "texto": "geral"}).json()      # no capture
    c = client.get(f"/api/reports/{r1['id']}/captura")
    assert c.status_code == 200 and c.headers["content-type"] == "image/jpeg"
    with open(gui.pr.p(r1["captura"]), "rb") as f:
        assert c.content == f.read()
    assert client.get(f"/api/reports/{r2['id']}/captura").status_code == 404
    assert client.get("/api/reports/R9999/captura").status_code == 404
    # a capture file that vanished is a 404, not a 500
    os.remove(gui.pr.p(r1["captura"]))
    assert client.get(f"/api/reports/{r1['id']}/captura").status_code == 404


def test_suspeitas_endpoint_and_event(env):
    gui, client, placed, tw, dec = env
    r = client.get("/api/suspeitas")
    assert r.status_code == 200, r.text
    d = r.json()
    assert isinstance(d["items"], list) and d["items"] == []
    assert d["summary"]["n_colocadas"] == 1 and d["summary"]["n_verificadas"] == 1 and d["summary"]["n_impossivel"] == 0
    seq0 = gui.seq
    assert client.post("/api/confirm", json={"acao": "place", "piece": tw, "cell": [3, 4]}).status_code == 200
    ev = [data for _, n, data in gui.events_after(seq0) if n == "suspeitas_changed"]
    assert ev and ev[-1]["n_colocadas"] == 2
    assert client.get("/api/suspeitas").json()["summary"]["n_colocadas"] == 2


# ---------------------------------------------------------------- contour editor (manual overrides, §18)
def _editor_contour(d, dx=6.0):
    """What the editor saves (crop px) after pushing its rightmost handles out by ``dx`` px: the handles,
    with the untouched stretches expanded back to ``denso`` (as the JS ``cedExpanded``)."""
    from src import overrides as OV
    c = np.asarray(d["contour"], float)
    x = c[:, 0]
    moved = x > x.min() + 0.8 * (x.max() - x.min())
    c[moved, 0] += dx
    n = len(c)
    oi = [None if moved[i] else d["indices"][i] for i in range(n)]
    keep = [not (moved[i] or moved[(i + 1) % n]) for i in range(n)]
    return OV.expand_polygon(d["denso"], c, oi, keep).tolist()


@pytest.mark.parametrize("which", ["tw", "placed"])
def test_contorno_get_preview_save(env, which):
    from src import overrides as OV
    gui, cl, placed, tw, dec = env
    pid = tw if which == "tw" else placed
    d = cl.get(f"/api/pieces/{pid}/contorno").json()
    assert d["piece"] == pid and d["manual_override"] is False and d["nota"] == ""
    assert d["margem_px"] == round(3.0 / d["mmpp"]) and len(d["contour"]) >= 20
    x0, y0 = d["origem"]
    bx, by, bw, bh = d["bbox"]
    assert x0 == max(0, bx - d["margem_px"]) and y0 == max(0, by - d["margem_px"])
    png = cl.get(d["crop_png_url"])
    assert png.status_code == 200 and png.content[:4] == b"\x89PNG"
    im = cv2.imdecode(np.frombuffer(png.content, np.uint8), cv2.IMREAD_UNCHANGED)
    assert im.shape == (d["tamanho"][1], d["tamanho"][0], 3)
    c = _editor_contour(d)
    body = {"contour": c, "origem": d["origem"], "tamanho": d["tamanho"]}
    pv = cl.post(f"/api/pieces/{pid}/contorno/preview", json=body)
    assert pv.status_code == 200 and pv.headers["content-type"] == "image/png"
    rgba = cv2.imdecode(np.frombuffer(pv.content, np.uint8), cv2.IMREAD_UNCHANGED)
    assert rgba.shape == (d["tamanho"][1], d["tamanho"][0], 4)
    assert abs((rgba[..., 3] > 0).sum() - OV.polygon_area(c)) / OV.polygon_area(c) < 0.03
    n_log = len(Project.open(gui.path).events())
    assert not os.path.exists(OV.overrides_path(gui.pr))                 # preview writes nothing
    # invalid outlines: 400 with the reason, nothing written
    bow = c[: len(c) // 2] + c[len(c) // 2:][::-1]
    r = cl.post(f"/api/pieces/{pid}/contorno", json=dict(body, contour=bow))
    assert r.status_code == 400 and "cruza" in r.json()["error"]
    r = cl.post(f"/api/pieces/{pid}/contorno", json=dict(body, contour=c[:10]))
    assert r.status_code == 400 and "pelo menos" in r.json()["error"]
    assert cl.post(f"/api/pieces/{pid}/contorno/preview", json=dict(body, contour=bow)).status_code == 400
    assert cl.post(f"/api/pieces/{pid}/contorno", json={"origem": d["origem"]}).status_code == 400
    assert not os.path.exists(OV.overrides_path(gui.pr))
    assert len(Project.open(gui.path).events()) == n_log
    # save
    seq0 = gui.seq
    r = cl.post(f"/api/pieces/{pid}/contorno", json=dict(body, nota="comido à direita"))
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["ok"] and s["invariantes"] == [] and s["piece"]["contorno_manual"] is True
    assert s["piece"]["contorno_nota"] == "comido à direita" and s["piece"]["flags"]["manual_override"] is True
    assert s["piece"]["area_mm2"] > s["antes"]["area_mm2"]
    names = [n for _, n, _ in gui.events_after(seq0)]
    assert "board_changed" in names and "piece_changed" in names and "fetch_changed" in names
    pr = _ok_on_disk(gui.path)
    evs = [e for e in pr.events()[n_log:] if e["action"] == "piece_resegmented"]
    assert len(evs) == 1 and evs[0]["motivo"] == "manual" and evs[0]["piece"] == pid
    assert len(OV.read_overrides(pr)) == 1
    d2 = cl.get(f"/api/pieces/{pid}/contorno").json()
    assert d2["manual_override"] is True and d2["nota"] == "comido à direita"
    assert np.allclose(np.asarray(d2["denso"]) + d2["origem"], np.asarray(c) + d["origem"], atol=0.01)
    assert len(d2["contour"]) == len(d2["indices"]) < len(d2["denso"])
    assert cl.get(f"/api/pieces/{pid}").json()["contorno_manual"] is True
    assert cl.get(f"/api/pieces/{pid}.png?pose=scan&size=120").status_code == 200
    if which == "placed":
        assert cl.get("/api/cell/2/3").json()["peca"]["contorno_manual"] is True
        assert [2, 3] in s["celulas_mudadas"]
    assert cl.get("/api/pieces/P9999/contorno").status_code == 404


def test_contorno_busy_is_409(env):
    gui, cl, placed, tw, dec = env
    d = cl.get(f"/api/pieces/{tw}/contorno").json()
    gui.job = "importar x"
    try:
        r = cl.post(f"/api/pieces/{tw}/contorno", json={"contour": _editor_contour(d), "origem": d["origem"]})
        assert r.status_code == 409
    finally:
        gui.job = None


# ---------------------------------------------------------------- stroke editor (POST …/contorno/resolver, TRACOS.md)
def _bump_lasso(d, w=14):
    """A ``peca`` lasso (crop px) sticking ``w`` px out of the right side of the current outline."""
    c = np.asarray(d["denso"], float)
    x1 = c[:, 0].max()
    yc = float(np.median(c[:, 1]))
    return {"ferramenta": "laco", "marca": "peca",
            "pontos": [[x1 - 10, yc - 12], [x1 + w, yc - 12], [x1 + w, yc + 12], [x1 - 10, yc + 12]]}


def test_contorno_resolver(env):
    from src import overrides as OV
    from src import strokes as ST
    gui, cl, placed, tw, dec = env
    d = cl.get(f"/api/pieces/{tw}/contorno").json()
    assert d["tracos"] == [] and d["banda_mm"] == ST.BANDA_MM and d["solver_omissao"] in d["solvers"]
    w, h = d["tamanho"]
    body = {"tracos": [], "origem": d["origem"], "tamanho": d["tamanho"]}
    for solver in (None, "grabcut", "watershed", "limiar"):
        r = cl.post(f"/api/pieces/{tw}/contorno/resolver", json=dict(body, solver=solver) if solver else body)
        assert r.status_code == 200, r.text
        s = r.json()
        assert s["valido"] is True and s["erro"] is None and s["solver"] == (solver or ST.SOLVER_OMISSAO)
        assert s["n_pontos"] == len(s["contour"]) >= 20 and s["origem"] == d["origem"] and s["ms"] > 0
        m = ST.rle_decode(s["mascara_rle"])
        assert m.shape == (h, w)
        assert abs(m.sum() - OV.polygon_area(s["contour"])) / m.sum() < 0.05
        dense = _fill_poly(d["denso"], (h, w))
        assert (m & dense).sum() / (m | dense).sum() > 0.95                    # flat synthetic piece: the same outline
    r = cl.post(f"/api/pieces/{tw}/contorno/resolver", json=dict(body, tracos=[_bump_lasso(d)], iter=3)).json()
    assert r["valido"] and r["params"]["iters"] == 3 and r["area_mm2"] > d["area_mm2"]
    assert not os.path.exists(OV.overrides_path(gui.pr))                        # nothing written
    # an outline the save would refuse: valido false with the reason (still 200)
    huge = {"ferramenta": "laco", "marca": "peca", "pontos": [[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]]}
    r = cl.post(f"/api/pieces/{tw}/contorno/resolver", json=dict(body, tracos=[huge])).json()
    assert r["valido"] is False and "área" in r["erro"]


def _fill_poly(poly, shape):
    from src.maskcmp import fill_contour
    return fill_contour(poly, shape)


def test_contorno_resolver_errors(env):
    gui, cl, placed, tw, dec = env
    d = cl.get(f"/api/pieces/{tw}/contorno").json()
    url = f"/api/pieces/{tw}/contorno/resolver"
    base = {"tracos": [], "origem": d["origem"], "tamanho": d["tamanho"]}
    for bad, word in ((dict(base, tracos={"x": 1}), "lista"),
                      (dict(base, tracos=[{"ferramenta": "spray", "pontos": [[1, 1]]}]), "ferramenta"),
                      (dict(base, origem=[-5, 0]), "fora do scan"),
                      (dict(base, origem=[0, 0], tamanho=[99999, 10]), "fora do scan"),
                      (dict(base, solver="magia"), "solver"),
                      (dict(base, iter=0), "iter")):
        r = cl.post(url, json=bad)
        assert r.status_code == 400 and word in r.json()["error"], (bad, r.text)
    assert cl.post(url, json=[1, 2]).status_code == 400
    assert cl.post(url, content=b"{", headers={"content-type": "application/json"}).status_code == 400
    assert cl.post("/api/pieces/P9999/contorno/resolver", json=base).status_code == 404


def test_contorno_save_with_tracos(env):
    from src import overrides as OV
    from src import strokes as ST
    gui, cl, placed, tw, dec = env
    d = cl.get(f"/api/pieces/{tw}/contorno").json()
    lasso = _bump_lasso(d)
    body = {"tracos": [lasso], "origem": d["origem"], "tamanho": d["tamanho"], "solver": "grabcut", "iter": 2}
    s = cl.post(f"/api/pieces/{tw}/contorno/resolver", json=body).json()
    assert s["valido"]
    n_log = len(Project.open(gui.path).events())
    r = cl.post(f"/api/pieces/{tw}/contorno", json=dict(body, contour=s["contour"], mascara_rle=s["mascara_rle"],
                                                       nota="traços"))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] and "tracos" not in out["override"] and "auto_contour_px" not in out["override"]
    assert out["override"]["metodo"] == "tracos"
    pr = _ok_on_disk(gui.path)
    evs = [e for e in pr.events()[n_log:] if e["action"] == "piece_resegmented"]
    assert len(evs) == 1 and evs[0]["motivo"] == "manual" and evs[0]["piece"] == tw
    (line,) = OV.read_overrides(pr)
    assert line["metodo"] == "tracos" and line["auto_origem"] == "segmentacao" and line["nota"] == "traços"
    assert line["origem"] == d["origem"] and line["tamanho"] == d["tamanho"]
    assert line["solver"]["nome"] == "grabcut" and line["solver"]["params"]["iters"] == 2
    assert line["tracos"][0]["marca"] == "peca" and line["tracos"][0]["pontos"] == [[float(x), float(y)] for x, y in lasso["pontos"]]
    auto = np.asarray(line["auto_contour_px"])
    assert auto.dtype.kind == "i" and np.allclose(auto, np.round(np.asarray(d["denso"]) + d["origem"]))
    assert abs(line["auto_area_mm2"] - d["area_mm2"]) / d["area_mm2"] < 0.03
    m = ST.rle_decode(line["mascara_rle"])
    assert m.shape == (d["tamanho"][1], d["tamanho"][0])
    assert np.array_equal(m, _fill_poly(np.asarray(line["contour_px"]) - d["origem"], m.shape))
    # reopen: the strokes come back in the NEW crop (the bbox grew to the right, the origin may move)
    d2 = cl.get(f"/api/pieces/{tw}/contorno").json()
    assert d2["manual_override"] is True and len(d2["tracos"]) == 1
    p_new = np.asarray(d2["tracos"][0]["pontos"]) + d2["origem"]
    assert np.allclose(p_new, np.asarray(lasso["pontos"]) + d["origem"], atol=0.01)
    # the next save records the manual outline as the one it replaces
    s2 = cl.post(f"/api/pieces/{tw}/contorno/resolver", json={"tracos": d2["tracos"], "origem": d2["origem"],
                                                              "tamanho": d2["tamanho"]}).json()
    assert s2["valido"]
    assert cl.post(f"/api/pieces/{tw}/contorno", json={"contour": s2["contour"], "origem": d2["origem"],
                                                       "tamanho": d2["tamanho"], "tracos": d2["tracos"]}).status_code == 200
    last = OV.read_overrides(Project.open(gui.path))[-1]
    assert last["auto_origem"] == "manual" and last["solver"]["nome"] == ST.SOLVER_OMISSAO
    # bad stroke / mask size on save: 400, nothing more written
    n = len(OV.read_overrides(Project.open(gui.path)))
    bad = cl.post(f"/api/pieces/{tw}/contorno", json={"contour": s2["contour"], "origem": d2["origem"],
                                                      "tracos": [{"ferramenta": "x"}]})
    assert bad.status_code == 400 and "ferramenta" in bad.json()["error"]
    bad = cl.post(f"/api/pieces/{tw}/contorno", json={"contour": s2["contour"], "origem": d2["origem"], "tracos": [],
                                                      "mascara_rle": {"w": 2, "h": 2, "runs": [4]}})
    assert bad.status_code == 400 and "mascara_rle" in bad.json()["error"]
    assert len(OV.read_overrides(Project.open(gui.path))) == n


def test_contorno_save_vertices_records_auto(env):
    """A handle-editor save (no strokes) also records the outline it replaces (metodo vertices)."""
    from src import overrides as OV
    gui, cl, placed, tw, dec = env
    d = cl.get(f"/api/pieces/{placed}/contorno").json()
    r = cl.post(f"/api/pieces/{placed}/contorno", json={"contour": _editor_contour(d), "origem": d["origem"]})
    assert r.status_code == 200, r.text
    (line,) = OV.read_overrides(Project.open(gui.path))
    assert line["metodo"] == "vertices" and line["auto_origem"] == "segmentacao" and "tracos" not in line
    assert len(line["auto_contour_px"]) == len(d["denso"])


def test_prepare_rebuilds_stale_assets_after_pull(tmp_path):
    """A log pulled without its npz: the shrunk contour of one piece is re-segmented at start-up, 0 events."""
    from src import render
    from test_render import _ingested, _shrink_npz_contour
    pr, sid = _ingested(tmp_path)
    os.makedirs(pr.p("render", "gui"), exist_ok=True)         # assets present: only the stale check runs
    assert S.missing_assets(pr) == []
    pid = sorted(pr.pieces)[1]
    with np.load(pr.p("pieces", f"{sid}.npz")) as z:
        good = z[f"{pid}__contour_px"].copy()
    _shrink_npz_contour(pr, sid, pid)
    n_log = len(pr.events())
    g = S.Gui(pr.path, prepare=True, use_image=False, log=None)
    t0 = time.time()
    while not any(n == "ready" for _, n, _ in g.events_after(0)) and time.time() - t0 < 60:
        time.sleep(0.1)
    info = g.stale_info
    assert info["desatualizados_antes"] == 1 and info["refeitos"] == 1 and info["eventos"] == 0
    assert info["restantes"] == 0 and info["folhas"] == [sid] and info["erros"] == []
    with np.load(pr.p("pieces", f"{sid}.npz")) as z:
        assert np.array_equal(z[f"{pid}__contour_px"], good)
    assert len(Project.open(pr.path).events()) == n_log
    st = TestClient(S.create_app(g)).get("/api/status").json()
    assert st["ativos"]["refeitos"] == 1 and st["ativos"]["eventos"] == 0
    assert render.stale_assets(Project.open(pr.path))["n_pecas"] == 0
    # coherent start-up: nothing to redo
    g2 = S.Gui(pr.path, prepare=True, use_image=False, log=None)
    t0 = time.time()
    while not any(n == "ready" for _, n, _ in g2.events_after(0)) and time.time() - t0 < 60:
        time.sleep(0.1)
    assert g2.stale_info["desatualizados_antes"] == 0 and g2.stale_info["refeitos"] == 0
