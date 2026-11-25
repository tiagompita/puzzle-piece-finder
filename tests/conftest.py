"""Shared pytest configuration for the anti-regression suite.

Puts the repository root on ``sys.path`` so ``import src.<module>`` resolves no
matter how pytest is invoked (``python -m pytest`` already prepends the CWD, but
this keeps a plain ``pytest`` working too). Also exposes ``REPO_ROOT`` for tests
that need to locate example data on disk.
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


import weakref  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _stop_test_guis(monkeypatch):
    """Stop (``Gui.stop()``) every ``src.server.Gui`` a test creates, at the end of that test.

    The import-queue worker (``queue=True`` by default) is a thread per ``Gui``; without ``stop()`` the suite kept
    ~116 ``fila-importacao`` threads alive and timing-sensitive tests competed with them (2026-11-15, P0 of the
    performance phase, approved by Tiago as the way for the fixtures to call ``gui.stop()``). One autouse fixture
    instead of editing every fixture: it wraps ``Gui.__init__`` for the duration of the test and keeps weak
    references. Guis of module/session-scoped fixtures are created before this function-scoped fixture is active,
    so they are not stopped between tests."""
    try:
        from src import server as SV
    except Exception:  # noqa: BLE001 - server deps missing: those tests are skipped anyway
        yield
        return
    made = []
    orig = SV.Gui.__init__

    def init(self, *a, **k):
        made.append(weakref.ref(self))
        orig(self, *a, **k)
    monkeypatch.setattr(SV.Gui, "__init__", init)
    yield
    for ref in made:
        g = ref()
        if g is not None:
            try:
                g.stop(timeout=5)
            except Exception:  # noqa: BLE001 - a half-built Gui (its __init__ raised)
                pass


# ---------------------------------------------------------------------------------------------------------------
# Registo de rede das páginas Playwright (2026-11-25, intermitências de GUI)
#
# Cada ``Browser.new_page`` / ``BrowserContext.new_page`` ligado durante um teste regista, por página, os pedidos
# falhados (``requestfailed``: url, método, ``failure``), as respostas HTTP >= 400 e os ``pageerror`` / ``console``
# de erro. Só quando o teste falha (setup, call ou teardown) o registo vai para o relatório do pytest, numa secção
# própria; um teste verde não imprime nada. Não muda o comportamento dos testes (sem repetições nem esperas).
# ---------------------------------------------------------------------------------------------------------------

_NET_LOG_KEY = "_ppf_net_log"


def _attach_net_log(page, log):
    """Liga os ouvintes de rede/erros de ``page`` à lista ``log`` (de strings). Nunca levanta."""
    def stamp():
        try:
            return page.url
        except Exception:  # noqa: BLE001
            return "?"

    def on_failed(req):
        try:
            fail = req.failure
        except Exception:  # noqa: BLE001
            fail = "?"
        log.append(f"requestfailed {req.method} {req.url} -> {fail} (pagina {stamp()})")

    def on_response(resp):
        try:
            if resp.status >= 400:
                log.append(f"HTTP {resp.status} {resp.request.method} {resp.url} (pagina {stamp()})")
        except Exception:  # noqa: BLE001
            pass

    def on_pageerror(err):
        log.append(f"pageerror {err} (pagina {stamp()})")

    def on_console(msg):
        try:
            if msg.type == "error":
                log.append(f"console.error {msg.text} (pagina {stamp()})")
        except Exception:  # noqa: BLE001
            pass

    try:
        page.on("requestfailed", on_failed)
        page.on("response", on_response)
        page.on("pageerror", on_pageerror)
        page.on("console", on_console)
    except Exception:  # noqa: BLE001
        pass


@pytest.fixture(autouse=True)
def _net_log(request, monkeypatch):
    """Instala o registo de rede nas páginas criadas durante o teste e guarda-o em ``item``."""
    log = []
    setattr(request.node, _NET_LOG_KEY, log)
    try:
        from playwright import sync_api
    except Exception:  # noqa: BLE001 - sem playwright: nada a registar
        yield log
        return

    def wrap(cls, name):
        orig = getattr(cls, name)

        def new_page(self, *a, **k):
            page = orig(self, *a, **k)
            _attach_net_log(page, log)
            return page
        monkeypatch.setattr(cls, name, new_page)

    wrap(sync_api.Browser, "new_page")
    wrap(sync_api.BrowserContext, "new_page")
    yield log


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.failed and rep.when in ("setup", "call", "teardown"):
        log = getattr(item, _NET_LOG_KEY, None)
        if log:
            rep.sections.append(("Registo de rede das paginas (pedidos falhados, HTTP >= 400, erros)", "\n".join(log)))
