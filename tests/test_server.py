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
