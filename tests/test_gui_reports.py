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
        assert [r.split(" ")[0] for r in rows] == ["R0001", "R0002"]            # só os abertos por omissão
        assert "recorte comido" in rows[0] and "(3, 4)" in rows[0].replace("(3,4)", "(3, 4)")
        assert "segundo problema" in rows[1]
        pg.click("#reports-filter [data-filter=fechado]")
        rows = pg.eval_on_selector_all("#tab-reports .report-row", "els => els.map((e) => e.innerText)")
        assert len(rows) == 1 and rows[0].startswith("R0003") and "resolvido" in rows[0] and "feito" in rows[0]
        pg.click("#reports-filter [data-filter=aberto]")
        assert pg.locator("#tab-reports .report-row").count() == 2
        # só leitura: nenhum botão para fechar / alterar um report
        assert pg.locator("#tab-reports .report-row button").count() == 0
        br.close()
    from src import reports
    assert [r["estado"] for r in reports.read_reports(gui.pr)] == ["aberto", "aberto", "fechado"]
