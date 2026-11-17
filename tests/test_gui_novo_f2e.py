"""F2e da GUI nova (teste do Tiago no iPhone, 2026-11-17), escrito ANTES do código:

1. transições: o menu e o painel do lugar entram em ≈ 180 ms (ease-out), sem animação com ``prefers-reduced-motion``;
   o estado lógico não espera pela animação;
2. «Fechar» (390 px) passa a um ícone X com ``aria-label`` «Fechar»;
3. toque duplo no tabuleiro (só ``pointerType`` touch): o toque simples espera ≈ 250 ms; o duplo aproxima 2× no ponto tocado
   até uma célula ocupar ≈ ⅓ da menor dimensão do ecrã (no limite não faz nada) e nunca abre o painel nem escolhe cartão;
   o rato continua imediato; o arrasto com o dedo não muda; o iOS não faz o seu zoom (``touch-action``);
4. «Ver lugar» vindo do cartão: o painel do lugar mostra a sugestão do cartão ao lado da arte, com o mesmo «Encaixa», e
   «Voltar ao cartão»; aberto de outra forma fica como antes.

Browser (Chromium headless, ``slow``) sobre o projeto sintético de ``tests/test_query.py``.
"""

import json

import pytest

pytestmark = pytest.mark.slow
pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")
pytest.importorskip("httpx")
sync_api = pytest.importorskip("playwright.sync_api")

from test_gui_novo import base, guarda, browser, _open_any  # noqa: E402,F401

VP_PC, VP_TEL = (1366, 768), (390, 844)

# pontos de ecrã de uma célula (l, c), a partir da vista atual
XY = """([l, c]) => { const r = document.querySelector('#board').getBoundingClientRect();
  return { x: r.left + (c - 0.5 - S.vb.x) / S.vb.w * r.width, y: r.top + ((l - 0.5) * S.hr - S.vb.y) / S.vb.h * r.height }; }"""
# o ponto do tabuleiro (unidades da viewBox) sob um ponto de ecrã
BOARDPT = """({x, y}) => { const r = document.querySelector('#board').getBoundingClientRect();
  return { x: S.vb.x + (x - r.left) / r.width * S.vb.w, y: S.vb.y + (y - r.top) / r.height * S.vb.h }; }"""
SPY = """(() => { window.__taps = []; window.__up = 0;
  document.querySelector('#board').addEventListener('pointerup', () => { window.__up = performance.now(); }, true);
  const f = S.onBoardTap; S.onBoardTap = (l, c, e) => { window.__taps.push({ l, c, dt: performance.now() - window.__up, tipo: e && e.pointerType }); return f(l, c, e); }; })()"""


def _open(browser, url, vp, **kw):
	ctx = browser.new_context(viewport={"width": vp[0], "height": vp[1]}, **kw)
	pg = ctx.new_page()
	errs = []
	pg.on("pageerror", lambda e: errs.append(str(e)))
	pg.goto(url + "/novo/")
	pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
	pg.wait_for_selector("#tab-montar .card[data-piece]", timeout=60_000)
	pg.wait_for_function("S.vb.w < 30", timeout=10_000)
	pg.wait_for_timeout(500)
	pg.evaluate(SPY)
	return pg, errs


def _outra_celula(pg):
	"""Um lugar que não é o alvo do cartão, dentro da grelha."""
	return pg.evaluate("(() => { const [l, c] = current().cell; return [l, c === S.cols ? c - 1 : c + 1]; })()")


def _ppc(pg):
	return pg.evaluate("pxPerCell()")


def _vista_para_ppc(pg, ppc_alvo, cell):
	"""Põe a vista com ``ppc_alvo`` px por célula, centrada em ``cell``."""
	pg.evaluate(f"""(() => {{ const r = svgRect(), w = r.width / {ppc_alvo}, h = w * r.height / r.width;
	  setView({{ x: {cell[1]} - 0.5 - w / 2, y: ({cell[0]} - 0.5) * S.hr - h / 2, w }}, true); }})()""")
	pg.wait_for_timeout(100)


# ---------------------------------------------------------------- 3. toque duplo
@pytest.mark.parametrize("vp", [VP_PC, VP_TEL])
def test_double_tap_zooms_2x_at_the_touched_point_without_opening_the_panel(base, browser, vp):
	url, gui, tw = base
	pg, errs = _open(browser, url, vp, has_touch=True)
	try:
		cell = _outra_celula(pg)
		cap = min(vp) / 3
		_vista_para_ppc(pg, cap / 4, cell)                                # longe do limite: 2× cabe
		antes_ppc = _ppc(pg)
		p = pg.evaluate(XY, cell)
		sob = pg.evaluate(BOARDPT, p)
		pick = pg.evaluate("[S.pick, S.modo, S.tab]")
		pg.touchscreen.tap(p["x"], p["y"])
		pg.touchscreen.tap(p["x"], p["y"])
		pg.wait_for_timeout(700)                                          # bem depois dos 250 ms: nada pode abrir
		assert abs(_ppc(pg) / antes_ppc - 2.0) < 0.05, (antes_ppc, _ppc(pg))
		depois = pg.evaluate(BOARDPT, p)
		assert abs(depois["x"] - sob["x"]) < 0.02 and abs(depois["y"] - sob["y"]) < 0.02, (sob, depois)   # o ponto tocado fica quieto
		assert pg.locator("#painel").count() == 0 and pg.evaluate("[S.pick, S.modo, S.tab]") == pick
		assert pg.evaluate("window.__taps") == []                         # o gancho de toque nunca correu
		assert not errs, errs
	finally:
		pg.context.close()


@pytest.mark.parametrize("vp", [VP_PC, VP_TEL])
def test_double_tap_stops_at_the_limit_of_a_third_of_the_screen(base, browser, vp):
	url, gui, tw = base
	pg, errs = _open(browser, url, vp, has_touch=True)
	try:
		cell = _outra_celula(pg)
		cap = min(vp) / 3
		_vista_para_ppc(pg, cap * 0.7, cell)                              # 2× passaria do limite: aproxima só até ao limite
		p = pg.evaluate(XY, cell)
		pg.touchscreen.tap(p["x"], p["y"])
		pg.touchscreen.tap(p["x"], p["y"])
		pg.wait_for_timeout(500)
		assert abs(_ppc(pg) - cap) / cap < 0.03, (cap, _ppc(pg))
		fixa = pg.evaluate("S.vb")
		p = pg.evaluate(XY, cell)
		pg.touchscreen.tap(p["x"], p["y"])
		pg.touchscreen.tap(p["x"], p["y"])
		pg.wait_for_timeout(700)
		assert pg.evaluate("S.vb") == fixa                                # já no limite: não faz nada
		assert pg.locator("#painel").count() == 0 and pg.evaluate("window.__taps") == []
		assert not errs, errs
	finally:
		pg.context.close()


def test_double_tap_on_the_current_target_does_not_blink_or_pick(base, browser):
	url, gui, tw = base
	pg, errs = _open(browser, url, VP_PC, has_touch=True)
	try:
		cell = pg.evaluate("current().cell")
		_vista_para_ppc(pg, 40, cell)
		p = pg.evaluate(XY, cell)
		pg.touchscreen.tap(p["x"], p["y"])
		pg.touchscreen.tap(p["x"], p["y"])
		pg.wait_for_timeout(700)
		assert pg.locator("#b-localizar.pisca").count() == 0 and pg.locator("#painel").count() == 0
		assert pg.evaluate("window.__taps") == []
		assert not errs, errs
	finally:
		pg.context.close()


def test_single_touch_tap_waits_about_250ms_then_opens_the_panel(base, browser):
	url, gui, tw = base
	pg, errs = _open(browser, url, VP_PC, has_touch=True)
	try:
		cell = _outra_celula(pg)
		p = pg.evaluate(XY, cell)
		pg.touchscreen.tap(p["x"], p["y"])
		pg.wait_for_selector("#painel", timeout=20_000)
		taps = pg.evaluate("window.__taps")
		assert len(taps) == 1 and taps[0]["tipo"] == "touch", taps
		assert 230 <= taps[0]["dt"] <= 700, taps                          # esperou ≈ 250 ms pelo segundo toque
		assert pg.evaluate("S.painel.cell") == cell
		assert not errs, errs
	finally:
		pg.context.close()


def test_single_touch_tap_on_a_queue_target_still_centres_the_card_target(base, browser):
	"""O toque simples no alvo do cartão atual continua a centrar e a piscar «localizar» (depois da espera)."""
	url, gui, tw = base
	pg, errs = _open(browser, url, VP_PC, has_touch=True)
	try:
		cell = pg.evaluate("current().cell")
		_vista_para_ppc(pg, 40, cell)
		p = pg.evaluate(XY, cell)
		pg.touchscreen.tap(p["x"], p["y"])
		pg.wait_for_function("window.__taps.length === 1", timeout=5_000)
		assert pg.evaluate("window.__taps")[0]["dt"] >= 230
		assert pg.locator("#painel").count() == 0 and pg.evaluate("S.modo") == "cartao"
		assert pg.locator("#b-localizar").get_attribute("data-mudou") in ("pisca", "marca")
		assert not errs, errs
	finally:
		pg.context.close()


def test_mouse_click_is_immediate_and_unchanged(base, browser):
	url, gui, tw = base
	pg, errs = _open(browser, url, VP_PC)
	try:
		cell = _outra_celula(pg)
		p = pg.evaluate(XY, cell)
		pg.mouse.click(p["x"], p["y"])
		taps = pg.evaluate("window.__taps")
		assert len(taps) == 1 and taps[0]["tipo"] == "mouse" and taps[0]["dt"] < 60, taps      # sem espera
		pg.wait_for_selector("#painel", timeout=20_000)
		assert not errs, errs
	finally:
		pg.context.close()


def test_touch_drag_still_pans_and_is_not_a_tap(base, browser):
	url, gui, tw = base
	pg, errs = _open(browser, url, VP_PC, has_touch=True)
	try:
		cell = _outra_celula(pg)
		_vista_para_ppc(pg, 60, cell)
		p = pg.evaluate(XY, cell)
		x0 = pg.evaluate("S.vb.x")
		cdp = pg.context.new_cdp_session(pg)
		cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": p["x"], "y": p["y"], "id": 1}]})
		for i in range(1, 7):
			cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": p["x"] - 20 * i, "y": p["y"], "id": 1}]})
		cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
		pg.wait_for_timeout(600)
		assert pg.evaluate("S.vb.x") > x0 + 0.5                           # arrastou para a esquerda: a vista andou para a direita
		assert pg.evaluate("window.__taps") == [] and pg.locator("#painel").count() == 0
		assert not errs, errs
	finally:
		pg.context.close()


def test_board_blocks_ios_double_tap_zoom(base, browser):
	url, gui, tw = base
	pg, errs = _open(browser, url, VP_TEL, has_touch=True)
	try:
		ta = pg.evaluate("[document.querySelector('#board-wrap'), document.querySelector('#board')].map((e) => getComputedStyle(e).touchAction)")
		assert ta == ["none", "none"], ta
		assert not errs, errs
	finally:
		pg.context.close()


# ---------------------------------------------------------------- 2. «Fechar» com ícone X
@pytest.mark.parametrize("vp", [VP_TEL, VP_PC])
def test_fechar_is_an_x_icon_with_aria_label(base, browser, vp):
	url, gui, tw = base
	pg, errs = _open_any(browser, url, *vp)
	try:
		pg.click("#menu-btn")
		f = pg.locator("#menu #menu-fechar")
		assert f.is_visible() and f.get_attribute("aria-label") == "Fechar"
		assert f.inner_text().strip() == "" and f.locator(".ico.i-x").count() == 1
		bb = f.bounding_box()
		assert bb["height"] >= 44 - 0.5 and bb["width"] >= 44 - 0.5, bb
		f.click()
		assert not pg.locator("#menu").is_visible()
		assert not errs, errs
	finally:
		pg.close()


# ---------------------------------------------------------------- 1. transições
ANIM = """(sel) => { const e = document.querySelector(sel), cs = getComputedStyle(e);
  return { nome: cs.animationName, dur: cs.animationDuration, fn: cs.animationTimingFunction }; }"""


def _ms(dur):
	return float(dur.split(",")[0].strip().rstrip("s")) * 1000


def test_menu_and_place_panel_enter_in_180ms_ease_out(base, browser):
	url, gui, tw = base
	pg, errs = _open_any(browser, url, *VP_PC)
	try:
		pg.wait_for_selector("#tab-montar .card[data-piece]", timeout=60_000)
		pg.click("#menu-btn")
		a = pg.evaluate(ANIM, "#menu")
		assert a["nome"] != "none" and abs(_ms(a["dur"]) - 180) < 1 and "ease-out" in a["fn"], a
		assert pg.locator("#menu").is_visible()                                  # o estado lógico não espera
		pg.click("#menu-btn")
		assert not pg.locator("#menu").is_visible() and pg.locator("#tab-montar").is_visible()   # fechou logo
		pg.click("#b-ver-lugar")
		pg.wait_for_selector("#painel[data-kind]:not([data-kind='a_carregar'])", timeout=20_000)      # a entrada é a do conteúdo
		b = pg.evaluate(ANIM, "#painel")
		assert b["nome"] != "none" and abs(_ms(b["dur"]) - 180) < 1 and "ease-out" in b["fn"], b
		assert not errs, errs
	finally:
		pg.close()


def test_closing_is_logical_at_once_and_leaves_no_ghost(base, browser):
	"""A animação de saída é só visual: o painel já está fechado para o código e o clone some depois de ≈ 180 ms."""
	url, gui, tw = base
	pg, errs = _open_any(browser, url, *VP_PC)
	try:
		pg.wait_for_selector("#tab-montar .card[data-piece]", timeout=60_000)
		pg.click("#menu-btn")
		pg.keyboard.press("Escape")
		assert pg.evaluate("menuAberto()") is False and pg.locator("#menu").is_visible() is False
		assert pg.locator("#tab-montar .card").is_visible()
		pg.wait_for_function("document.querySelectorAll('.sai-fantasma').length === 0", timeout=2_000)
		pg.click("#b-ver-lugar")
		pg.wait_for_selector("#painel", timeout=20_000)
		pg.click("#p-voltar")
		assert pg.evaluate("S.modo") == "cartao" and pg.locator("#painel").count() == 0
		pg.wait_for_function("document.querySelectorAll('.sai-fantasma').length === 0", timeout=2_000)
		assert not errs, errs
	finally:
		pg.close()


def test_exit_animation_ghost_is_made_when_closing(base, browser):
	"""Sem reduced-motion, ao fechar há um clone de saída (``.sai-fantasma``) sem eventos de ponteiro."""
	url, gui, tw = base
	pg, errs = _open_any(browser, url, *VP_PC)
	try:
		pg.wait_for_selector("#tab-montar .card[data-piece]", timeout=60_000)
		pg.click("#menu-btn")
		pg.evaluate("setMenu(false); window.__g = document.querySelector('.sai-fantasma')")
		assert pg.evaluate("window.__g !== null && getComputedStyle(window.__g).pointerEvents === 'none' && window.__g.getAttribute('aria-hidden') === 'true'")
		assert not errs, errs
	finally:
		pg.close()


def test_no_animation_with_reduced_motion(base, browser):
	url, gui, tw = base
	ctx = browser.new_context(viewport={"width": VP_PC[0], "height": VP_PC[1]}, reduced_motion="reduce")
	pg = ctx.new_page()
	errs = []
	pg.on("pageerror", lambda e: errs.append(str(e)))
	try:
		pg.goto(url + "/novo/")
		pg.wait_for_selector("#tab-montar .card[data-piece]", timeout=60_000)
		pg.click("#menu-btn")
		a = pg.evaluate(ANIM, "#menu")
		assert a["nome"] == "none" or _ms(a["dur"]) == 0, a
		pg.click("#menu-btn")
		assert pg.evaluate("document.querySelectorAll('.sai-fantasma').length") == 0     # nem clone de saída
		pg.click("#b-ver-lugar")
		pg.wait_for_selector("#painel[data-kind]:not([data-kind='a_carregar'])", timeout=20_000)      # a entrada é a do conteúdo
		b = pg.evaluate(ANIM, "#painel")
		assert b["nome"] == "none" or _ms(b["dur"]) == 0, b
		assert not errs, errs
	finally:
		ctx.close()


# ---------------------------------------------------------------- 4. «Ver lugar» com a sugestão do cartão
@pytest.mark.parametrize("vp", [VP_PC, VP_TEL])
def test_ver_lugar_shows_the_card_suggestion_beside_the_art(base, browser, vp):
	url, gui, tw = base
	pg, errs = _open_any(browser, url, *vp)
	try:
		pg.wait_for_selector("#tab-montar .card[data-piece]", timeout=60_000)
		it = pg.evaluate("(() => { const c = current(); return { piece: c.piece, lote: c.lote, n: c.n_no_lote, cell: c.cell }; })()")
		pg.click("#b-ver-lugar")
		pg.wait_for_selector("#painel[data-kind='vazio'] #p-arte", timeout=20_000)
		cartao = pg.locator("#painel #p-cartao")
		assert cartao.count() == 1
		assert cartao.locator("img").first.get_attribute("src").startswith(f"/api/pieces/{it['piece']}.png")
		txt = cartao.inner_text()
		assert f"Saco {it['lote']}" in txt and f"nº {it['n']}" in txt, txt
		enc = pg.locator("#painel #b-encaixa")
		assert enc.count() == 1 and enc.inner_text().strip() == "Encaixa" and enc.locator(".ico.i-check").count() == 1
		assert pg.locator("#painel #p-voltar").inner_text().strip() == "Voltar ao cartão"
		# ao lado da arte: as duas caixas partilham linha
		a, c = pg.locator("#painel .arte-box").bounding_box(), cartao.bounding_box()
		assert a["y"] < c["y"] + c["height"] and c["y"] < a["y"] + a["height"] and c["x"] >= a["x"] + a["width"] - 1, (a, c)
		assert not pg.evaluate("document.documentElement.scrollWidth > window.innerWidth")
		assert enc.bounding_box()["height"] >= 44 - 0.5
		assert not errs, errs
	finally:
		pg.close()


def test_encaixa_in_the_place_panel_posts_exactly_what_the_card_posts(base, browser):
	url, gui, tw = base
	pg, errs = _open_any(browser, url, *VP_PC)
	try:
		pg.wait_for_selector("#tab-montar .card[data-piece]", timeout=60_000)
		esperado = pg.evaluate("current().encaixa.body")
		posts = []
		pg.route("**/api/confirm", lambda r: (posts.append(r.request.post_data), r.continue_()))
		pg.click("#b-ver-lugar")
		pg.wait_for_selector("#painel #b-encaixa", timeout=20_000)
		pg.click("#painel #b-encaixa")
		pg.wait_for_function("S.undo && S.undo.tipo === 'encaixa'", timeout=30_000)
		assert len(posts) == 1 and json.loads(posts[0]) == esperado, posts
		assert not errs, errs
	finally:
		pg.close()


def test_voltar_ao_cartao_goes_back_to_the_same_card(base, browser):
	url, gui, tw = base
	pg, errs = _open_any(browser, url, *VP_PC)
	try:
		pg.wait_for_selector("#tab-montar .card[data-piece]", timeout=60_000)
		x = pg.locator("#tab-montar .card").get_attribute("data-piece")
		pg.click("#b-ver-lugar")
		pg.wait_for_selector("#painel #p-cartao", timeout=20_000)
		pg.click("#painel #p-voltar")
		pg.wait_for_selector("#tab-montar .card[data-piece]", timeout=20_000)
		assert pg.locator("#tab-montar .card").get_attribute("data-piece") == x and pg.evaluate("S.modo") == "cartao"
		assert not errs, errs
	finally:
		pg.close()


def test_place_panel_opened_by_tapping_an_empty_place_is_as_before(base, browser):
	"""Aberto de outra forma (tocar num lugar vazio): sem o bloco do cartão e com «Voltar à fila»."""
	url, gui, tw = base
	pg, errs = _open_any(browser, url, *VP_PC)
	try:
		pg.wait_for_selector("#tab-montar .card[data-piece]", timeout=60_000)
		l, c = pg.evaluate("(() => { const [l, c] = current().cell; return [l, c === S.cols ? c - 1 : c + 1]; })()")
		pg.evaluate(f"S.onBoardTap({l}, {c})")
		pg.wait_for_selector("#painel[data-kind]:not([data-kind='a_carregar'])", timeout=20_000)
		assert pg.locator("#painel #p-cartao").count() == 0
		assert pg.locator("#painel #p-voltar").inner_text().strip() == "Voltar à fila"
		assert not errs, errs
	finally:
		pg.close()
