"""Prova o registo de rede de ``tests/conftest.py``: um pedido falhado aparece no registo e na secção do relatório."""

import pytest

sync_api = pytest.importorskip("playwright.sync_api")


@pytest.mark.slow
def test_pedido_falhado_fica_no_registo(_net_log):
    with sync_api.sync_playwright() as pw:
        try:
            br = pw.chromium.launch()
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"chromium indisponivel: {e}")
        try:
            pg = br.new_page()
            pg.route("**/*.js", lambda r: r.abort())
            pg.route("**/pagina", lambda r: r.fulfill(
                status=200, content_type="text/html",
                body="<script src='http://localhost/x.js'></script><img src='http://localhost/nada.png'>"))
            pg.goto("http://localhost/pagina")
            pg.wait_for_timeout(200)
        finally:
            br.close()
    texto = "\n".join(_net_log)
    assert "requestfailed GET http://localhost/x.js" in texto
    assert "net::ERR_FAILED" in texto


@pytest.mark.slow
def test_secao_entra_no_relatorio_da_falha(pytester):
    pytester.makeconftest(open(__file__.replace("test_net_log.py", "conftest.py"), encoding="utf-8").read())
    pytester.makepyfile("""
        import pytest
        from playwright import sync_api

        def test_falha(_net_log):
            with sync_api.sync_playwright() as pw:
                br = pw.chromium.launch()
                pg = br.new_page()
                pg.route("**/pagina", lambda r: r.fulfill(status=200, content_type="text/html",
                    body="<script src='http://localhost/x.js'></script>"))
                pg.route("**/x.js", lambda r: r.abort())
                pg.goto("http://localhost/pagina")
                pg.wait_for_timeout(200)
                br.close()
            assert False

        def test_verde():
            pass
    """)
    res = pytester.runpytest_subprocess("-p", "no:cacheprovider")
    out = res.stdout.str()
    assert "Registo de rede das paginas" in out
    assert "requestfailed GET http://localhost/x.js" in out
    assert out.count("Registo de rede das paginas") == 1
