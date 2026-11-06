"""Aba «Mesa»: caixa de pesquisa (filtra os grupos enquanto se escreve; por id Gxxxx, Pxxxx e célula) (slow).

Os grupos são injetados na página (``S.sections``) para não depender do projeto: o que se testa é o filtro.
"""

import pytest

pytestmark = pytest.mark.slow
pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("uvicorn")
pytest.importorskip("playwright.sync_api")

from test_gui_layout import base, browser  # noqa: E402,F401  (fixtures)

FAKE = """() => {
  const cand = (l, c) => ({ rank: 1, cell0: [l, c], rot: 0, mirror: false, margin: 1.2, score: 5, fora: false, ocupadas: 0,
                           footprint: [[l, c], [l, c + 1]] });
  S.sections = [
    { id: 'G0012', kind: 'montado', n: 2, scan_id: 'S0011', notes: '', thumb: '', pecas: [{ id: 'P0194', rc: [0, 0] }, { id: 'P0195', rc: [0, 1] }], candidatos: [cand(3, 32)] },
    { id: 'G0021', kind: 'blocos', n: 1, scan_id: 'S0024', notes: '', thumb: '', pecas: [{ id: 'P0291', rc: [0, 0] }], candidatos: [cand(10, 5)] },
    { id: 'G0044', kind: 'montado', n: 2, scan_id: 'S0016', notes: '', thumb: '', pecas: [{ id: 'P0501', rc: [0, 0] }, { id: 'P0506', rc: [1, 0] }], candidatos: [cand(44, 55)] },
  ];
  S.mesaQuery = '';
  renderMesa();
}"""


def test_mesa_search_filters_by_group_piece_and_cell(base, browser):  # noqa: F811
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    try:
        pg.goto(base + "/")
        pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
        pg.evaluate("showTab('mesa')")
        pg.evaluate(FAKE)
        assert pg.locator("#mesa-q").count() == 1
        ids = lambda: pg.eval_on_selector_all("#mesa-list .mrow .t", "els => els.map((e) => e.textContent)")  # noqa: E731
        assert ids() == ["G0012 · 2 peças", "G0021 · 1 peça", "G0044 · 2 peças"]
        pg.fill("#mesa-q", "g0021")                                   # id do grupo, sem maiúsculas
        assert ids() == ["G0021 · 1 peça"] and "1 de 3" in pg.inner_text("#mesa-info")
        pg.fill("#mesa-q", "P0506")                                    # peça do grupo
        assert ids() == ["G0044 · 2 peças"]
        pg.fill("#mesa-q", "3,32")                                     # célula da zona candidata
        assert ids() == ["G0012 · 2 peças"]
        pg.fill("#mesa-q", "(44, 56)")                                 # célula do footprint (a 2.ª peça do grupo)
        assert ids() == ["G0044 · 2 peças"]
        pg.fill("#mesa-q", "zzz")
        assert ids() == [] and "Nenhum grupo corresponde" in pg.inner_text("#mesa-list")
        pg.fill("#mesa-q", "")
        assert len(ids()) == 3
        # escrever não perde o foco nem a caixa (a lista refaz-se, a caixa não)
        pg.click("#mesa-q")
        pg.keyboard.type("G00")
        assert pg.evaluate("document.activeElement.id") == "mesa-q" and pg.input_value("#mesa-q") == "G00"
        assert len(ids()) == 3
    finally:
        pg.close()
