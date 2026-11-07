"""Barra de pesquisa da GUI (peça / célula / report / folha) e reports clicáveis (slow).

Projeto sintético 4×6 de ``test_query._project``: P0001 colocada em (2,3); P0002 (gémea) solta com uma
proposta em «Guardadas» para (3,4); P0003 solta sem proposta; as três na folha S0001 (saco 3).
A pesquisa e o clique num report são só leitura: o ``log.jsonl`` não ganha eventos.
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
from test_query import _project  # noqa: E402


@pytest.fixture(scope="module")
def srv(tmp_path_factory):
    import uvicorn
    from src.query import run_query
    tmp = tmp_path_factory.mktemp("gui_search")
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


@pytest.fixture()
def page(srv, request):
    base, _ = srv
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
        pg.wait_for_selector("#tab-guardadas .card", state="attached", timeout=30_000)
        yield pg
        br.close()
    if "not_found" in request.node.name:       # GET /api/pieces/P0999 -> 404 is the expected answer there
        errs = [e for e in errs if "404" not in e]
    assert errs == []


def _search(pg, q):
    pg.evaluate("document.querySelector('#toast').replaceChildren()")
    pg.fill("#q", q)
    pg.press("#q", "Enter")


def _toasts(pg):
    return pg.eval_on_selector_all("#toast > *", "els => els.map((e) => e.textContent)")


@pytest.mark.parametrize("q", ["P0001", "p1", "1", "2,3", "2 3", "(2,3)", "l2 c3", "  p0001 "])
def test_search_placed_piece_or_cell_opens_cell_drawer(page, q):
    _search(page, q)
    page.wait_for_function("S.sel && S.sel[0] === 2 && S.sel[1] === 3", timeout=15_000)
    assert page.evaluate("document.querySelector('#tab-celula').classList.contains('on')")
    page.wait_for_selector("#tab-celula h3", timeout=15_000)


def test_search_stored_piece_selects_card_in_guardadas(page):
    _search(page, "P0002")
    page.wait_for_selector("#tab-guardadas.on", timeout=15_000)
    assert page.evaluate("document.querySelector('#tab-guardadas details.guardadas').open")
    assert page.locator("#tab-guardadas .card[data-piece='P0002'].sel").count() == 1
    assert page.evaluate("S.tab") == "guardadas"


def test_search_loose_piece_without_proposal_reports_real_state(page):
    _search(page, "P0003")
    page.wait_for_selector("#toast :text('solta')", timeout=15_000)
    assert any("P0003" in t and "solta" in t for t in _toasts(page))
    page.wait_for_selector("#tab-celula.on", timeout=15_000)      # the piece panel opens


def test_search_empty_cell(page):
    _search(page, "1,1")
    page.wait_for_selector("#toast :text('vazia')", timeout=15_000)
    page.wait_for_function("S.sel && S.sel[0] === 1 && S.sel[1] === 1", timeout=15_000)
    assert page.evaluate("document.querySelector('#tab-celula').classList.contains('on')")


def test_search_sheet_lists_its_pieces(page):
    _search(page, "S0001")
    page.wait_for_selector("#tab-lotes.on .lot-hit", timeout=15_000)
    ids = page.eval_on_selector_all("#tab-lotes .lot-hit .ptile", "els => els.map((e) => e.title.split(' ')[0])")
    assert sorted(ids) == ["P0001", "P0002", "P0003"]
    assert page.evaluate("document.querySelector('#tab-lotes details.lot').open")
    _search(page, "s1")
    page.wait_for_selector("#tab-lotes .lot-hit[data-scan='S0001']", timeout=15_000)


@pytest.mark.parametrize("q,frag", [("P0999", "P0999"), ("R0099", "R0099"), ("S0099", "S0099"), ("xyz", "xyz"), ("99,99", "99,99")])
def test_search_not_found_always_says_so(page, q, frag):
    _search(page, q)
    page.wait_for_selector("#toast :text('não encontrado')", timeout=15_000)
    assert any(frag in t and "não encontrado" in t for t in _toasts(page))


def test_search_empty_input_gives_a_hint(page):
    _search(page, "   ")
    page.wait_for_selector("#toast :text('Escreve')", timeout=15_000)


def test_report_row_click_locates_without_writing(srv, page):
    base, gui = srv
    r = page.evaluate("""fetch('/api/report', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ piece: 'P0001', cell: [2, 3], tipo: 'outro', texto: 'pesquisa' }) }).then((x) => x.json())""")
    assert r.get("id") == "R0001", r
    page.evaluate("loadReports()")
    page.evaluate("showTab('reports')")
    page.wait_for_selector("#tab-reports .report-row[data-report='R0001']", timeout=15_000)
    row = page.locator("#tab-reports .report-row[data-report='R0001']")
    assert row.get_attribute("role") == "button" and row.get_attribute("tabindex") == "0"
    chips = row.locator(".chip").all_inner_texts()
    assert "P0001" in chips and "(2, 3)" in chips, chips
    assert row.locator("img.rthumb").count() == 1
    with open(gui.pr.log_path, encoding="utf-8") as f:
        before = sum(1 for _ in f)
    row.click()
    page.wait_for_function("S.sel && S.sel[0] === 2 && S.sel[1] === 3", timeout=15_000)
    # o clique já não muda de aba: realça a célula no tabuleiro e fica em «Reports»
    assert page.evaluate("document.querySelector('#tab-reports').classList.contains('on')")
    assert page.evaluate("S.tab") == "reports" and page.evaluate("S.sel") == [2, 3]
    page.evaluate("S.sel = null")
    page.focus("#tab-reports .report-row[data-report='R0001']")
    page.keyboard.press("Enter")
    page.wait_for_function("S.sel && S.sel[0] === 2 && S.sel[1] === 3", timeout=15_000)
    assert page.evaluate("S.tab") == "reports"
    with open(gui.pr.log_path, encoding="utf-8") as f:
        after = sum(1 for _ in f)
    assert after == before
    # search by report id reaches the same place
    page.evaluate("showTab('buscar')")
    _search(page, "r1")
    page.wait_for_function("S.tab === 'celula' && S.sel && S.sel[0] === 2", timeout=15_000)
    with open(gui.pr.log_path, encoding="utf-8") as f:
        assert sum(1 for _ in f) == before
