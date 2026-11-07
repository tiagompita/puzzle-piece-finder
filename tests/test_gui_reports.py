"""GUI: painel de Reports, só leitura (slow): lista (ID, célula/peça, texto, estado), filtro
aberto/resolvido, contagem de abertos."""

import pytest

pytestmark = pytest.mark.slow
pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("uvicorn")
sync_api = pytest.importorskip("playwright.sync_api")

from test_gui_guardadas import _page, _serve  # noqa: E402
from test_query import _project  # noqa: E402


@pytest.fixture(scope="module")
def synth(tmp_path_factory):
    from src import reports
    from src.query import run_query
    tmp = tmp_path_factory.mktemp("synth")
    pr, placed, tw, dec = _project(tmp)
    run_query(pr, use_image=False)
    reports.add_report(pr, tipo="mal_lida", texto="recorte comido", piece=placed, cell=(3, 4), vista="celula")
    reports.add_report(pr, tipo="outro", texto="segundo problema", cell=(1, 1), vista="celula")
    reports.add_report(pr, tipo="nao_encaixa", texto="este já foi tratado", piece=tw, vista="cartao")
    reports.close_report(pr, "R0003", nota="feito")
    gui, server, th, base = _serve(pr.path, str(tmp / "uploads"))
    yield base, gui
    server.should_exit = True
    th.join(10)


def test_reports_panel(synth):
    base, gui = synth
    with sync_api.sync_playwright() as pw:
        br, pg = _page(pw)
        pg.goto(base + "/")
        pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
        pg.evaluate("showTab('reports')")
        pg.wait_for_selector("#tab-reports .report-row", timeout=30_000)
        assert pg.inner_text("#n-reports") == "2"
        assert "2 abertos" in pg.inner_text("#reports-count") and "1 resolvido" in pg.inner_text("#reports-count")
        rows = pg.eval_on_selector_all("#tab-reports .report-row", "els => els.map((e) => e.innerText)")
        assert [r.split()[0] for r in rows] == ["R0001", "R0002"]            # só os abertos por omissão
        assert "recorte comido" in rows[0] and "(3, 4)" in rows[0].replace("(3,4)", "(3, 4)")
        assert "segundo problema" in rows[1]
        pg.click("#reports-filter [data-filter=fechado]")
        rows = pg.eval_on_selector_all("#tab-reports .report-row", "els => els.map((e) => e.innerText)")
        assert len(rows) == 1 and rows[0].startswith("R0003") and "resolvido" in rows[0] and "feito" in rows[0]
        pg.click("#reports-filter [data-filter=aberto]")
        assert pg.locator("#tab-reports .report-row").count() == 2
        # a lista não muda estados: só a seta «→» (abre o detalhe), exatamente uma por linha
        assert pg.locator("#tab-reports .report-row button").count() == 2
        assert pg.locator("#tab-reports .report-row button.rgo").count() == 2
        br.close()
    from src import reports
    assert [r["estado"] for r in reports.read_reports(gui.pr)] == ["aberto", "aberto", "fechado"]


def _nlines(path):
    with open(path, encoding="utf-8") as f:
        return len(f.read().splitlines())


def _fresh(tmp_path):
    from src import reports
    from src.query import run_query
    pr, placed, tw, dec = _project(tmp_path)
    run_query(pr, use_image=False)
    reports.add_report(pr, tipo="mal_lida", texto="recorte comido", piece=placed, cell=(3, 4), vista="celula")
    reports.add_report(pr, tipo="outro", texto="geral", vista="celula")
    return pr


def test_arrow_opens_detail(tmp_path):
    pr = _fresh(tmp_path)
    gui, server, th, base = _serve(pr.path, str(tmp_path / "uploads"))
    errs = []
    try:
        with sync_api.sync_playwright() as pw:
            br, pg = _page(pw)
            pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(base + "/")
            pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
            pg.evaluate("showTab('reports')")
            pg.wait_for_selector("#tab-reports .report-row", timeout=30_000)
            assert pg.locator("#tabs button").count() == 6                       # o detalhe não tem botão de aba
            pg.click("#tab-reports [aria-label='Abrir report R0001']")
            pg.wait_for_selector("#tab-report.on", timeout=15_000)
            assert "R0001" in pg.inner_text("#tab-report")
            assert pg.evaluate("S.tab") == "report"
            assert pg.locator("#tab-report .rthumbs img").count() == 2
            # os chips da célula realçam no tabuleiro sem mudar de aba
            pg.click("#tab-report .chip-btn >> text=(3, 4)")
            assert pg.evaluate("S.sel") == [3, 4] and pg.evaluate("S.tab") == "report"
            pg.click("#tab-report >> text=← Reports")
            pg.wait_for_selector("#tab-reports.on", timeout=5_000)
            br.close()
        assert errs == []
    finally:
        server.should_exit = True
        th.join(10)


def test_detail_state_actions_append_only(tmp_path):
    from src import reports
    pr = _fresh(tmp_path)
    gui, server, th, base = _serve(pr.path, str(tmp_path / "uploads"))
    rp, lp = reports.reports_path(pr), pr.log_path
    errs = []
    try:
        with sync_api.sync_playwright() as pw:
            br, pg = _page(pw)
            pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(base + "/")
            pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
            pg.evaluate("showTab('reports')")
            pg.wait_for_selector("#tab-reports .report-row", timeout=30_000)
            pg.click("#tab-reports [aria-label='Abrir report R0001']")
            pg.wait_for_selector("#tab-report.on")

            def step(click, toast_txt):
                with open(rp, "rb") as f:
                    prefix = f.read()
                r0, l0 = _nlines(rp), _nlines(lp)
                click()
                pg.wait_for_selector(f"#toast :text('{toast_txt}')", timeout=15_000)
                assert _nlines(rp) == r0 + 1 and _nlines(lp) == l0 + 1
                with open(rp, "rb") as f:
                    assert f.read().startswith(prefix)                              # nada reescrito

            # resolver com nota
            def resolve():
                pg.click("#tab-report .btn >> text=Marcar resolvido")
                pg.wait_for_selector("#estado-dlg[open]")
                pg.fill("#estado-nota", "corrigido")
                pg.click("#estado-ok")
            step(resolve, "marcado como resolvido")
            assert "resolvido" in pg.inner_text("#tab-report") and "corrigido" in pg.inner_text("#tab-report")
            step(lambda: pg.click("#tab-report .btn >> text=Reabrir"), "reaberto")
            assert pg.locator("#tab-report .btn", has_text="Marcar resolvido").count() == 1

            def delete():
                pg.click("#tab-report .btn >> text=Eliminar")
                pg.wait_for_selector("#estado-dlg[open]")
                assert "Eliminar R0001? Fica escondido e pode ser restaurado." in pg.inner_text("#estado-msg")
                pg.click("#estado-ok")
            step(delete, "eliminado")
            assert pg.locator("#tab-report .btn", has_text="Restaurar").count() == 1
            # filtro «Eliminados»
            pg.click("#tab-report >> text=← Reports")
            pg.click("#reports-filter [data-filter=aberto]")
            assert pg.locator("#tab-reports .report-row").count() == 1            # só R0002
            pg.click("#reports-filter [data-filter=eliminado]")
            rows = pg.eval_on_selector_all("#tab-reports .report-row", "els => els.map((e) => e.innerText)")
            assert len(rows) == 1 and rows[0].startswith("R0001") and "eliminado" in rows[0]
            pg.click("#tab-reports [aria-label='Abrir report R0001']")
            pg.wait_for_selector("#tab-report.on")
            step(lambda: pg.click("#tab-report .btn >> text=Restaurar"), "restaurado")
            assert pg.locator("#tab-report .btn", has_text="Marcar resolvido").count() == 1   # voltou a aberto
            br.close()
        assert errs == []
    finally:
        server.should_exit = True
        th.join(10)
    got = reports.read_reports(Project_open(pr.path))
    assert [r["estado"] for r in got] == ["aberto", "aberto"] and got[0]["n_estados"] == 4


def Project_open(path):
    from src.state import Project
    return Project.open(path)


def test_edit_report_button_instead_of_duplicate(tmp_path):
    """A piece that already has an open report shows «Editar report» (not «Reportar»); the dialog is prefilled
    and saving appends an edit event to ``reports.jsonl`` instead of creating a second report."""
    import os
    from src import reports
    from src.query import run_query
    pr, placed, tw, dec = _project(tmp_path)
    run_query(pr, use_image=False)
    # the proposal card of the twin piece (stored: no mounted neighbour) is in «Guardadas»
    gui, server, th, base = _serve(pr.path, str(tmp_path / "uploads"))
    try:
        with sync_api.sync_playwright() as pw:
            br, pg = _page(pw)
            pg.goto(base + "/")
            pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
            pg.wait_for_selector("#tab-guardadas .card", state="attached", timeout=30_000)
            pg.evaluate("showTab('guardadas'); document.querySelector('#tab-guardadas details.guardadas').open = true")
            assert pg.locator("#tab-guardadas .card .btn.report", has_text="Reportar").count() == 1
            assert pg.locator("#tab-guardadas .card .btn.report", has_text="Editar report").count() == 0
            pg.click("#tab-guardadas .card .btn.report")                        # first report
            pg.wait_for_selector("#report-dlg[open]")
            assert pg.inner_text("#report-title") == "Reportar um problema"
            pg.fill("#report-text", "primeira versão")
            pg.click("#report-send")
            pg.wait_for_selector("#toast :text('Reportado R0001')", timeout=15_000)
            pg.wait_for_selector("#tab-guardadas .card .btn.report:has-text('Editar report')", timeout=15_000)
            assert pg.locator("#tab-guardadas .card .btn.report", has_text="Reportar").count() == 0
            n_lines = len(open(reports.reports_path(gui.pr), encoding="utf-8").read().splitlines())
            pg.click("#tab-guardadas .card .btn.report")                        # now edits R0001
            pg.wait_for_selector("#report-dlg[open]")
            assert pg.inner_text("#report-title") == "Editar R0001"
            assert pg.input_value("#report-text") == "primeira versão"
            assert pg.inner_text("#report-send") == "Guardar edição"
            pg.fill("#report-text", "segunda versão")
            pg.click("#report-send")
            pg.wait_for_selector("#toast :text('Report R0001 editado')", timeout=15_000)
            got = pg.evaluate("fetch('/api/reports?todos=true').then((r) => r.json())")["reports"]
            assert [(r["id"], r["texto"], r.get("n_edicoes")) for r in got] == [("R0001", "segunda versão", 1)]
            assert len(open(reports.reports_path(gui.pr), encoding="utf-8").read().splitlines()) == n_lines + 1
            assert os.path.getsize(reports.reports_path(gui.pr)) > 0
            br.close()
    finally:
        server.should_exit = True
        th.join(10)
