"""Aba «Mesa» em lista compacta (alternativa B), rótulo «É aqui» e botão «Sugestões» no tabuleiro (slow).

Os grupos são injetados na página (``S.sections``) sobre o projeto sintético (grelha 4 × 6): o que se testa é a GUI.
"""

import os
import re

import pytest

pytestmark = pytest.mark.slow
pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("uvicorn")
pytest.importorskip("playwright.sync_api")

from test_gui_layout import base, browser  # noqa: E402,F401  (fixtures)

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "web")

# G0012 segura em (2,2)-(2,3) (+ 2 zonas na mesma célula (3,5) que só diferem na rotação);
# G0021 e G0044 a confirmar; G0021 sobrepõe G0012 na célula (2,3).
FAKE = """() => {
  const cand = (rank, l, c, rot, margin, fp) => ({ rank, cell0: [l, c], rot, mirror: false, margin, score: 5, fora: false, ocupadas: 0, footprint: fp });
  if (!S.board.calibracao) S.board.calibracao = {};
  S.board.calibracao.margin_min = 1.5;
  S.sections = [
    { id: 'G0012', kind: 'montado', n: 2, scan_id: 'S0011', notes: 'nota técnica', thumb: '', pecas: [{ id: 'P0194', rc: [0, 0] }, { id: 'P0195', rc: [0, 1] }],
      candidatos: [cand(1, 2, 2, 0, 3.0, [[2, 2], [2, 3]]), cand(2, 3, 5, 90, 3.0, [[3, 5], [3, 6]]), cand(3, 3, 5, 180, 3.0, [[3, 5], [3, 6]])] },
    { id: 'G0021', kind: 'blocos', n: 2, scan_id: 'S0024', notes: '', thumb: '', pecas: [{ id: 'P0291', rc: [0, 0] }, { id: 'P0294', rc: [0, 1] }],
      candidatos: [cand(1, 2, 3, 0, 1.0, [[2, 3], [2, 4]])] },
    { id: 'G0044', kind: 'montado', n: 1, scan_id: 'S0016', notes: '', thumb: '', pecas: [{ id: 'P0501', rc: [0, 0] }],
      candidatos: [cand(1, 3, 1, 0, 0.9, [[3, 1]])] },
  ];
  S.mesaQuery = ''; S.mesaFilter = null; S.mesaOpen = null; S.mesa = null;
  renderMesa();
}"""

CLIENT_XY = """([l, c]) => { const r = svgRect(); return [r.left + (c - 0.5 - S.vb.x) / S.vb.w * r.width, r.top + ((l - 0.5) * S.hr - S.vb.y) / S.vb.h * r.height]; }"""


def _open(browser, base, **kw):
    pg = browser.new_page(**kw)
    pg.goto(base + "/")
    pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
    pg.evaluate("showTab('mesa')")
    pg.evaluate(FAKE)
    return pg


def _rows(pg):
    return pg.eval_on_selector_all("#mesa-list .mrow", "els => els.map((e) => e.dataset.g)")


# ------------------------------------------------------------------ 1. alternativa B
def test_mesa_b_list_filters_and_action_only_after_ver(base, browser):  # noqa: F811
    pg = _open(browser, base, viewport={"width": 1400, "height": 900})
    try:
        assert pg.get_attribute("#mesa-q", "placeholder") == "Grupo, peça ou célula: G0021, P0294, 3,32"
        assert _rows(pg) == ["G0012", "G0021", "G0044"]                      # por margem
        assert pg.inner_text("#mesa-list .mrow[data-g='G0012'] .chip") == "segura"
        assert pg.inner_text("#mesa-list .mrow[data-g='G0021'] .chip") == "a confirmar"
        # uma só ação por linha, e a principal ainda não existe
        assert pg.locator("#mesa-list .mrow:not(.on) button").count() == 3
        assert pg.locator("[data-act='aqui']").count() == 0
        # filtros rápidos
        pg.click("button[data-filter='segura']")
        assert _rows(pg) == ["G0012"] and pg.get_attribute("button[data-filter='segura']", "aria-pressed") == "true"
        pg.click("button[data-filter='confirmar']")
        assert _rows(pg) == ["G0021", "G0044"] and pg.get_attribute("button[data-filter='segura']", "aria-pressed") == "false"
        pg.click("button[data-filter='confirmar']")                            # outra vez: limpa
        assert len(_rows(pg)) == 3
        # a pesquisa combina com o filtro
        pg.click("button[data-filter='confirmar']")
        pg.fill("#mesa-q", "P0294")
        assert _rows(pg) == ["G0021"]
        pg.fill("#mesa-q", "")
        pg.click("button[data-filter='confirmar']")
        # «Ver» abre a linha, pré-visualiza e só então aparece a ação principal
        pg.click("#mesa-list .mrow[data-g='G0012'] .mhead button")
        assert pg.locator("#mesa-list .mrow[data-g='G0012'].on").count() == 1
        assert pg.evaluate("S.mesa && S.mesa.id") == "G0012" and pg.locator("#lyr-mesa rect").count() == 2
        assert pg.inner_text("[data-act='aqui']") == "É aqui em (2, 2)"
        # zonas só diferentes na rotação NÃO se juntam
        others = pg.eval_on_selector_all("#mesa-list .mother span", "els => els.map((e) => e.textContent)")
        assert others == ["ou (3, 5) rot 90°", "ou (3, 5) rot 180°"], others
        pg.locator("#mesa-list .mother").nth(0).locator("button").click()                    # 2.ª alternativa
        assert pg.inner_text("[data-act='aqui']") == "É aqui em (3, 5)" and pg.evaluate("S.mesa.rank") == 2
        # uma linha aberta de cada vez
        pg.click("#mesa-list .mrow[data-g='G0021'] .mhead button")
        assert pg.locator("#mesa-list .mrow.on").count() == 1 and pg.locator("#mesa-list .mrow[data-g='G0012'].on").count() == 0
    finally:
        pg.close()


def test_mesa_b_confirm_says_program_did_not_decide(base, browser):  # noqa: F811
    pg = _open(browser, base, viewport={"width": 1400, "height": 900})
    try:
        msgs = []
        pg.on("dialog", lambda d: (msgs.append(d.message), d.dismiss()))
        pg.click("#mesa-list .mrow[data-g='G0021'] .mhead button")
        assert "não decidiu" in pg.inner_text("#mesa-list .mrow[data-g='G0021'] .mexp")
        pg.click("[data-act='aqui']")
        pg.click("#mesa-list .mrow[data-g='G0012'] .mhead button")
        pg.click("[data-act='aqui']")
        assert len(msgs) == 2
        assert "O programa não decidiu" in msgs[0] and "É aqui: G0021" in msgs[0], msgs[0]
        assert "não decidiu" not in msgs[1] and "É aqui: G0012" in msgs[1], msgs[1]
    finally:
        pg.close()


def test_mesa_b_phone(base, browser):  # noqa: F811
    pg = _open(browser, base, viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    try:
        assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert pg.evaluate("(() => { const t = document.querySelector('#tab-mesa'); return t.scrollWidth <= t.clientWidth + 1; })()")
        pg.tap("button[data-filter='confirmar']")
        assert _rows(pg) == ["G0021", "G0044"]
        pg.tap("#mesa-list .mrow[data-g='G0021'] .mhead button")
        assert pg.locator("[data-act='aqui']").is_visible()
        assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth")
        h = pg.locator("[data-act='aqui']").bounding_box()["height"]
        assert h >= 40, h
    finally:
        pg.close()


# ------------------------------------------------------------------ 2. «Ancorar» -> «É aqui»
def _visible_words(pg):
    return pg.evaluate("""() => {
      const root = document.body.cloneNode(true);
      root.querySelectorAll('script').forEach((e) => e.remove());
      const attrs = [...root.querySelectorAll('[title],[aria-label],[placeholder],[alt]')]
        .map((e) => [e.title, e.getAttribute('aria-label'), e.getAttribute('placeholder'), e.getAttribute('alt')].filter(Boolean).join(' ')).join(' ');
      return root.textContent + ' ' + attrs;
    }""")


def test_no_ancorar_visible_anywhere(base, browser):  # noqa: F811
    pg = _open(browser, base, viewport={"width": 1400, "height": 900})
    try:
        msgs = []
        pg.on("dialog", lambda d: (msgs.append(d.message), d.dismiss()))
        pg.click("#mesa-list .mrow[data-g='G0021'] .mhead button")
        pg.click("[data-act='aqui']")
        words = []
        for tab in ("buscar", "guardadas", "lotes", "mesa", "importar", "reports"):
            pg.evaluate(f"showTab('{tab}')")
            words.append(_visible_words(pg))
        pg.evaluate("document.querySelector('#legend-box').open = true")
        words.append(_visible_words(pg))
        words.extend(msgs)
        text = " ".join(words)
        assert "É aqui" in text
        assert not re.search(r"ancor", text, re.I), re.findall(r".{20}ancor.{20}", text, re.I)
        # servidor: legenda, estados e origens que a GUI mostra
        legend = pg.evaluate("fetch('/api/board').then((r) => r.json()).then((b) => JSON.stringify(b.legend))")
        assert not re.search(r"ancor", legend, re.I)
    finally:
        pg.close()


def test_no_ancorar_in_web_sources_or_server_texts():
    from src import confirm, server
    allowed = re.compile(r"por_ancorar")                                  # identificador de código (estado/CSS), nunca mostrado
    for name in ("app.js", "index.html", "app.css", "core.js", "board.js", "board.css"):   # + ficheiros da F1a (2026-11-11)
        src = allowed.sub("", open(os.path.join(WEB, name), encoding="utf-8").read())
        assert not re.search(r"ancor", src, re.I), name
    texts = [str(v) for row in server.LEGEND for v in row.values()] + list(server.ESTADO_TXT.values()) + list(server.ORIGIN_TXT.values())
    assert not [t for t in texts if re.search(r"ancor", t, re.I)]
    code = open(confirm.__file__, encoding="utf-8").read()
    assert not [ln for ln in code.splitlines() if "msgs.append" in ln and re.search(r"ancor", ln, re.I)]
    assert confirm.AQUI_TXT == "É aqui"


# ------------------------------------------------------------------ 3. botão «Sugestões»
def test_suggestions_layer_strong_weak_and_tap(base, browser):  # noqa: F811
    pg = _open(browser, base, viewport={"width": 1400, "height": 900})
    try:
        assert pg.is_checked("#tg-sug") is False and pg.locator("#lyr-sug rect").count() == 0       # desligado por omissão
        pg.check("#tg-sug")
        # a MELHOR zona de cada grupo: 2 + 2 + 1 células (nada de (3,5), que é a 2.ª zona de G0012)
        assert pg.locator("#lyr-sug rect.b-sug").count() == 2
        assert pg.locator("#lyr-sug rect.b-sug-fraca").count() == 3
        assert pg.locator("#lyr-sug rect[data-g='G0012']").count() == 2
        cells = pg.evaluate("[...document.querySelectorAll('#lyr-sug rect')].map((r) => r.dataset.g)")
        assert "G0012" in cells
        # tocar numa célula com uma só sugestão (G0044 em (3,1)) abre a Mesa nessa linha, aberta e pré-visualizada
        x, y = pg.evaluate(CLIENT_XY, [3, 1])
        pg.mouse.click(x, y)
        assert pg.evaluate("S.tab") == "mesa" and pg.locator("#mesa-list .mrow[data-g='G0044'].on").count() == 1
        assert pg.evaluate("S.mesa && S.mesa.id") == "G0044" and pg.locator("#sug-pick").count() == 0
        # sobreposição em (2,3): G0012 e G0021 -> lista curta com alvos grandes
        x, y = pg.evaluate(CLIENT_XY, [2, 3])
        pg.mouse.click(x, y)
        assert pg.locator("#sug-pick").count() == 1
        items = pg.locator("#sug-pick .sug-item[data-g]")
        assert items.count() == 2 and items.nth(0).get_attribute("data-g") == "G0012"          # segura primeiro
        assert all(items.nth(i).bounding_box()["height"] >= 44 for i in range(2))
        pg.keyboard.press("Escape")
        assert pg.locator("#sug-pick").count() == 0
        pg.mouse.click(*pg.evaluate(CLIENT_XY, [2, 3]))
        pg.click("#sug-pick .sug-item[data-g='G0021']")
        assert pg.locator("#mesa-list .mrow[data-g='G0021'].on").count() == 1 and pg.evaluate("S.mesa.id") == "G0021"
        assert pg.locator("#sug-pick").count() == 0
        # com um filtro que esconde o grupo, a sugestão limpa o filtro para o mostrar
        pg.click("button[data-filter='segura']")
        pg.mouse.click(*pg.evaluate(CLIENT_XY, [3, 1]))
        assert pg.locator("#mesa-list .mrow[data-g='G0044'].on").count() == 1
        # desligar apaga a camada e volta o toque normal (abre a célula)
        pg.uncheck("#tg-sug")
        assert pg.locator("#lyr-sug rect").count() == 0
        pg.mouse.click(*pg.evaluate(CLIENT_XY, [3, 1]))
        assert pg.evaluate("S.tab") == "celula"
    finally:
        pg.close()


def test_suggestions_state_persists_and_page_works_without_storage(base, browser):  # noqa: F811
    ctx = browser.new_context(viewport={"width": 1200, "height": 800})
    pg = ctx.new_page()
    try:
        pg.goto(base + "/")
        pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
        assert pg.is_checked("#tg-sug") is False
        pg.check("#tg-sug")
        pg.reload()
        pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
        assert pg.is_checked("#tg-sug") is True
    finally:
        pg.close(); ctx.close()
    ctx = browser.new_context(viewport={"width": 1200, "height": 800})
    ctx.add_init_script("Object.defineProperty(window, 'localStorage', { get() { throw new Error('sem armazenamento'); } });")
    pg = ctx.new_page()
    try:
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(base + "/")
        pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
        assert pg.is_checked("#tg-sug") is False
        pg.check("#tg-sug")                                                  # funciona na mesma, só não persiste
        assert pg.is_checked("#tg-sug") is True and not errors, errors
    finally:
        pg.close(); ctx.close()


def test_suggestions_phone_picker_inside_screen_and_big_targets(base, browser):  # noqa: F811
    pg = _open(browser, base, viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    try:
        pg.evaluate("document.querySelector('#tg-sug').click()")
        assert pg.evaluate("S.showSug") is True and pg.locator("#lyr-sug rect").count() == 5
        pg.evaluate("zoomCells(1, 1, 4, 6)")
        x, y = pg.evaluate(CLIENT_XY, [2, 3])
        pg.touchscreen.tap(x, y)
        assert pg.locator("#sug-pick").count() == 1
        box = pg.locator("#sug-pick").bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= 390 and box["y"] >= 0
        items = pg.locator("#sug-pick .sug-item")
        assert items.count() == 3
        assert all(items.nth(i).bounding_box()["height"] >= 44 for i in range(3))
        assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth")
        pg.tap("#sug-pick .sug-item[data-g='G0012']")
        assert pg.evaluate("S.tab") == "mesa" and pg.locator("#mesa-list .mrow[data-g='G0012'].on").count() == 1
        # a barra do topo não rebenta com o 3.º botão (390 px)
        assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth")
    finally:
        pg.close()
