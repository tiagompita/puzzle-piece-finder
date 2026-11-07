"""GUI: bloco «Suspeitas» no topo de Reports (slow), só leitura.

Projeto de ``test_consistency._row_project``: três peças em fila, B (2,4) colocada rodada +90°, por isso
``/api/suspeitas`` tem uma suspeita (``impossivel``). O bloco mostra «Suspeitas (1)», o filtro esconde e
mostra a linha, o clique localiza a célula no tabuleiro sem sair de Reports, e o ``log.jsonl`` não ganha
linhas.
"""

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
from test_consistency import _row_project  # noqa: E402


@pytest.fixture(scope="module")
def srv(tmp_path_factory):
    import uvicorn
    from src.query import run_query
    tmp = tmp_path_factory.mktemp("gui_suspeitas")
    pr, ids = _row_project(tmp, rot_b=90.0)
    run_query(pr, use_image=False)
    gui = S.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp / "uploads"), log=None)
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    server = uvicorn.Server(uvicorn.Config(S.create_app(gui), host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    t0 = time.time()
    while not server.started and time.time() - t0 < 30:
        time.sleep(0.1)
    yield f"http://127.0.0.1:{port}", gui, ids
    server.should_exit = True
    th.join(10)


@pytest.fixture()
def page(srv):
    base = srv[0]
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
        yield pg
        br.close()
    assert errs == []


def _log(gui):
    with open(gui.pr.log_path, encoding="utf-8") as f:
        return f.read()


def test_suspeitas_block_filter_and_locate(srv, page):
    _, gui, ids = srv
    log0 = _log(gui)
    page.evaluate("showTab('reports')")
    page.wait_for_selector("#tab-reports details.suspeitas .suspeita-row", state="attached", timeout=30_000)
    # first child of the Reports tab, with the count
    assert page.evaluate("document.querySelector('#tab-reports').firstElementChild.matches('details.suspeitas')")
    assert page.inner_text("#tab-reports details.suspeitas > summary") == "Suspeitas (1)"
    page.click("#tab-reports details.suspeitas > summary")
    row = page.locator(f"#tab-reports .suspeita-row[data-piece='{ids['B']}']")
    assert row.count() == 1 and row.get_attribute("data-grau") == "impossivel"
    txt = row.inner_text()
    assert ids["B"] in txt and "(2, 4)" in txt and "−90°" in txt and "impossível" in txt
    # filter: piece, cell, text; a miss hides the row
    for q, visible in (("xyz", False), (ids["B"].lower(), True), ("(2,4)", True), ("2,5", False), ("−90", True), ("", True)):
        page.fill("#tab-reports .susp-filter", q)
        assert row.is_visible() == visible, q
    # click: the cell is selected and zoomed, the Reports tab stays on
    row.click()
    page.wait_for_function("S.sel && S.sel[0] === 2 && S.sel[1] === 4", timeout=15_000)
    assert page.evaluate("document.querySelector('#tab-reports').classList.contains('on')")
    assert page.evaluate("S.tab") == "reports"
    # a re-render of Reports keeps the block (and the filter text)
    page.fill("#tab-reports .susp-filter", "2,4")
    page.evaluate("renderReports()")
    assert page.input_value("#tab-reports .susp-filter") == "2,4"
    assert page.locator("#tab-reports details.suspeitas").count() == 1
    assert _log(gui) == log0                            # read-only


# ------------------------------------------------------------ report aberto esconde a suspeita; «Falso alarme»
def _has_fa():
    from src import consistency
    return hasattr(consistency, "suspect_signature")


@pytest.fixture()
def fresh(tmp_path):
    """Servidor próprio (estado mutável: reports e falsos alarmes) + página, no projeto de uma fila com B rodada."""
    import uvicorn
    from src.query import run_query
    pr, ids = _row_project(tmp_path, rot_b=90.0)
    run_query(pr, use_image=False)
    gui = S.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "uploads"), log=None)
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    server = uvicorn.Server(uvicorn.Config(S.create_app(gui), host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    t0 = time.time()
    while not server.started and time.time() - t0 < 30:
        time.sleep(0.1)
    errs = []
    with sync_api.sync_playwright() as pw:
        try:
            br = pw.chromium.launch()
        except Exception as e:
            pytest.skip(f"chromium indisponível: {e}")
        pg = br.new_page(viewport={"width": 1400, "height": 900})
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://127.0.0.1:{port}/")
        pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
        yield pg, gui, ids
        br.close()
    server.should_exit = True
    th.join(10)
    assert errs == []


@pytest.mark.skipif(not _has_fa(), reason="backend de falso alarme ainda não disponível")
def test_open_report_hides_suspicion_and_close_brings_it_back(fresh):
    pg, gui, ids = fresh
    b = ids["B"]
    pg.evaluate("showTab('reports')")
    pg.wait_for_selector(f"#tab-reports .suspeita-row[data-piece='{b}']", state="attached", timeout=30_000)
    assert pg.inner_text("#tab-reports details.suspeitas > summary") == "Suspeitas (1)"
    r = pg.evaluate("""fetch('/api/report', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ piece: '%s', cell: [2, 4], tipo: 'mal_colocada', texto: 'rodada' }) }).then((x) => x.json())""" % b)
    assert r.get("id") == "R0001", r
    pg.wait_for_selector("#tab-reports details.report-row[data-report='R0001']", timeout=15_000)
    # a suspeita sai do bloco (summary a 0), fica o resumo «+ 1 em reports» e o chip na linha do report
    pg.wait_for_function("document.querySelector('#tab-reports details.suspeitas > summary').textContent === 'Suspeitas (0)'", timeout=15_000)
    assert pg.locator(f"#tab-reports .suspeita-row[data-piece='{b}']").count() == 0
    assert "+ 1 em reports" in pg.text_content("#tab-reports details.suspeitas .susp-extra")
    chip = pg.locator("#tab-reports details.report-row[data-report='R0001'] .chip.suspeita")
    pg.wait_for_selector("#tab-reports details.report-row[data-report='R0001'] .chip.suspeita", timeout=15_000)
    assert "suspeita · impossível" in chip.inner_text()
    # fechar o report pela linha expandida: a suspeita volta
    pg.click("#tab-reports details.report-row[data-report='R0001'] > summary")
    pg.click("#tab-reports details.report-row[data-report='R0001'] .btn >> text=Marcar resolvido")
    pg.wait_for_selector("#estado-dlg[open]")
    pg.click("#estado-ok")
    pg.wait_for_selector(f"#tab-reports .suspeita-row[data-piece='{b}']", state="attached", timeout=15_000)
    assert pg.inner_text("#tab-reports details.suspeitas > summary") == "Suspeitas (1)"


@pytest.mark.skipif(not _has_fa(), reason="backend de falso alarme ainda não disponível")
def test_falso_alarme_button_hides_and_restore_brings_back(fresh):
    pg, gui, ids = fresh
    b = ids["B"]
    pg.evaluate("showTab('reports')")
    row = f"#tab-reports .suspeita-row[data-piece='{b}']"
    pg.wait_for_selector(row, state="attached", timeout=30_000)
    pg.click("#tab-reports details.suspeitas > summary")
    pg.click(f"{row} .btn.fa")
    pg.wait_for_selector("#estado-dlg[open]")
    assert f"Falso alarme {b} (impossível)" in pg.inner_text("#estado-title")
    pg.fill("#estado-nota", "vi ao vivo: está bem")
    pg.click("#estado-ok")
    pg.wait_for_selector(f"#toast :text('{b}: falso alarme registado')", timeout=15_000)
    pg.wait_for_function(f"document.querySelectorAll(\"#tab-reports .suspeita-row[data-piece='{b}']\").length === 0", timeout=15_000)
    assert pg.inner_text("#tab-reports details.suspeitas > summary") == "Suspeitas (0)"
    assert "1 falso alarme" in pg.text_content("#tab-reports details.suspeitas .susp-extra")
    pg.click("#tab-reports details.falsos > summary")
    fr = pg.locator(f"#tab-reports details.falsos .falso-row[data-piece='{b}']")
    assert fr.count() == 1 and "vi ao vivo: está bem" in fr.inner_text() and "impossível" in fr.inner_text()
    fr.locator("text=Restaurar").click()
    pg.wait_for_selector(row, state="attached", timeout=15_000)
    assert pg.inner_text("#tab-reports details.suspeitas > summary") == "Suspeitas (1)"
    assert pg.locator("#tab-reports details.falsos").count() == 0
