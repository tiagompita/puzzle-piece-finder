"""User flows of the web GUI in headless Chromium over the synthetic project (slow).

Checks: no console / page errors; the "Vai buscar" list is split in "Coloca agora" and
"Guarda com posição" (the stored-position card has no "Coloquei" and has "Guardei num saquinho");
the "Reportar" dialog creates ``R0001`` (listed by ``GET /api/reports``, capture on disk).
"""

import os
import socket
import threading
import time

import pytest

pytestmark = pytest.mark.slow
pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("uvicorn")
sync_api = pytest.importorskip("playwright.sync_api")

from src import server as S  # noqa: E402
from test_query import _project  # noqa: E402


@pytest.fixture(scope="module")
def srv(tmp_path_factory):
    import uvicorn
    from src.query import run_query
    tmp = tmp_path_factory.mktemp("flows")
    pr, *_ = _project(tmp)
    run_query(pr, use_image=False)
    gui = S.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp / "uploads"), log=None)
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    server = uvicorn.Server(uvicorn.Config(S.create_app(gui), host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    t0 = time.time()
    while not server.started and time.time() - t0 < 30:
        time.sleep(0.1)
    yield f"http://127.0.0.1:{port}", gui
    server.should_exit = True
    th.join(10)


def test_buscar_groups_and_report(srv):
    base, gui = srv
    errs = []
    with sync_api.sync_playwright() as pw:
        try:
            br = pw.chromium.launch()
        except Exception as e:  # chromium not installed
            pytest.skip(f"chromium indisponível: {e}")
        pg = br.new_page(viewport={"width": 1400, "height": 900})
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(base + "/")
        pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
        pg.wait_for_selector("#tab-buscar .card", timeout=30_000)
        heads = pg.eval_on_selector_all("#tab-buscar .grupo-head", "els => els.map((e) => e.dataset.grupo)")
        assert heads == ["guarda_posicao"]          # the only proposal has no mounted neighbour
        btns = pg.eval_on_selector_all("#tab-buscar .card .actions .btn", "els => els.map((e) => e.textContent)")
        assert not any("Coloquei" in b for b in btns)
        assert any(b.startswith("Guardei num saquinho") for b in btns)
        # report
        pg.click("#tab-buscar .card .btn:has-text('Reportar')")
        pg.wait_for_selector("#report-dlg[open]")
        pg.check("#report-form input[value=mal_lida]")
        pg.fill("#report-text", "teste")
        pg.click("#report-send")
        pg.wait_for_selector("#toast :text('Reportado R0001')", timeout=15_000)
        reps = pg.evaluate("fetch('/api/reports').then((r) => r.json())")["reports"]
        assert [r["id"] for r in reps] == ["R0001"] and reps[0]["tipo"] == "mal_lida"
        assert os.path.exists(gui.pr.p(reps[0]["captura"]))
        br.close()
    assert errs == []


def test_cell_hint_flow(srv):
    """"Está montada" marks an empty cell (hatch + "marcada por ti"); "Está vazia" undoes it."""
    base, gui = srv
    errs = []
    with sync_api.sync_playwright() as pw:
        try:
            br = pw.chromium.launch()
        except Exception as e:  # chromium not installed
            pytest.skip(f"chromium indisponível: {e}")
        pg = br.new_page(viewport={"width": 1400, "height": 900})
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(base + "/")
        pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
        pg.evaluate("openCell(1, 1)")
        pg.wait_for_selector("#tab-celula .btn:has-text('Está montada')", timeout=30_000)
        assert pg.locator("#tab-celula .btn:has-text('Está vazia')").count() == 0
        pg.click("#tab-celula .btn:has-text('Está montada')")
        pg.wait_for_selector("#tab-celula :text('marcada por ti')", timeout=30_000)
        assert pg.evaluate("S.board.cells[0][0].estado") == "ocupada_legado"
        assert pg.locator("#tab-celula .btn:has-text('Está montada')").count() == 0
        pg.click("#tab-celula .btn:has-text('Está vazia')")
        pg.wait_for_selector("#tab-celula .btn:has-text('Está montada')", timeout=30_000)
        assert pg.evaluate("S.board.cells[0][0].estado") == "vazia"
        br.close()
    assert errs == []
