"""2026-11-25, bloco B: a imagem de um grupo mostrado e movido (sem Fixar) tem de aparecer no tabuleiro.

Defeito do Tiago (PC): grupo que ainda nao estava no tabuleiro -> «Grupos soltos» -> «Mostrar no tabuleiro» -> movido
(Ctrl+arrastar ou «Mover» … «Feito») -> so o contorno violeta e o fundo escuro, sem a imagem das pecas.

Assercao comum: o ``<image class="grupo-img">`` do grupo acaba com ``href`` igual a ``data-url`` e a imagem descodificada
(``naturalWidth`` > 0) em <= 5 s. Projeto sintetico de ``tests/test_server_grupos.py`` (G2 sem lugar provavel)."""

import json
import urllib.request

import pytest

pytestmark = pytest.mark.slow
pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")
pytest.importorskip("playwright.sync_api")

from test_gui_novo import browser, _serve  # noqa: E402,F401
from test_gui_novo_f4 import gr, _abrir, _arrastar, _post  # noqa: E402,F401

ESTADO = """(gid) => {
	const el = document.querySelector(`#lyr-grupos [data-grupo="${gid}"] image.grupo-img`);
	return el ? { href: el.getAttribute('href'), url: el.getAttribute('data-url') } : null;
}"""


def _imagem_ok(pg, gid, timeout=5_000):
	"""Espera que o ``<image>`` do grupo tenha ``href`` == ``data-url`` e que esse endereco se descodifique."""
	try:
		pg.wait_for_function("""(gid) => { const el = document.querySelector(`#lyr-grupos [data-grupo="${gid}"] image.grupo-img`);
			return !!el && !!el.getAttribute('href') && el.getAttribute('href') === el.getAttribute('data-url'); }""",
			arg=gid, timeout=timeout)
	except Exception:
		st = pg.evaluate("({ pngsP: !!pngsP, pngsDeNovo, gruposP: !!gruposP, ready: document.body.dataset.ready, livre: S.pngsLivre })")
		pedidos = [u.split('/api/')[1] for u in getattr(pg, "_b_reqs", []) if "/api/grupos" in u or "/api/board?" in u or u.endswith("/api/board")]
		raise AssertionError(f"sem imagem: {pg.evaluate(ESTADO, gid)}; ok={pg.evaluate('[...(S.pngs || [])]')}; "
							 f"ver={pg.evaluate('S.ver')}; estado={st} (pngsP preso em voo = H2); pedidos={pedidos}")
	w = pg.evaluate("""async (gid) => { const u = document.querySelector(`#lyr-grupos [data-grupo="${gid}"] image.grupo-img`).getAttribute('href');
		const im = new Image(); im.src = u; await im.decode(); return im.naturalWidth; }""", gid)
	assert w > 0


def _pronto(pg):
	pg.wait_for_function("S.pngsLivre === true", timeout=20_000)


def _pngs(reqs):
	return [u for u in reqs if "/api/grupos/" in u and ".png" in u]


def _abrir_g2(browser, url, ids):
	pg, errs = _abrir(browser, url)
	reqs = []
	pg._b_reqs = reqs
	pg.on("request", lambda r: reqs.append(r.url))
	_pronto(pg)
	pg.locator("#tab-montar .grp-row").nth(1).locator(".grp-mostrar").click()
	pg.wait_for_selector(f"#lyr-grupos [data-grupo='{ids['G2']}']", timeout=10_000)
	return pg, errs, reqs


def _livre(pg, gid):
	"""Uma celula onde o grupo de 1 linha cabe deslocado uma coluna (para a direita ou para a esquerda)."""
	return pg.evaluate("""(gid) => { for (const dc of [1, -1, 2, -2]) if (!motivoNaoCabe(gid, 0, dc)) return dc; return null; }""", gid)


def _ctrl_mover(pg, gid):
	fp = pg.evaluate("(gid) => grupo(gid).footprint", gid)
	dc = _livre(pg, gid)
	assert dc is not None
	l, c = fp[0]
	l0 = pg.evaluate("(gid) => grupo(gid).posicao.c0", gid)
	_arrastar(pg, (l, c), (l, c + dc), ctrl=True)
	pg.wait_for_function("([gid, c]) => grupo(gid).posicao.c0 === c && !S.busy", arg=[gid, l0 + dc], timeout=10_000)


def test_b1_mostrar_e_ctrl_arrastar(gr, browser):
	url, gui, ids = gr
	pg, errs, reqs = _abrir_g2(browser, url, ids)
	try:
		_imagem_ok(pg, ids["G2"])
		_ctrl_mover(pg, ids["G2"])
		_imagem_ok(pg, ids["G2"])
		assert not errs, errs
	finally:
		pg.close()


def test_b1_mostrar_e_mover_feito(gr, browser):
	url, gui, ids = gr
	pg, errs, reqs = _abrir_g2(browser, url, ids)
	try:
		g2 = ids["G2"]
		pg.wait_for_selector("#g-mover", timeout=10_000)
		dc = _livre(pg, g2)
		fp = pg.evaluate("(gid) => grupo(gid).footprint", g2)
		c0 = pg.evaluate("(gid) => grupo(gid).posicao.c0", g2)
		pg.click("#g-mover")
		pg.wait_for_selector("#g-feito", timeout=5_000)
		_arrastar(pg, tuple(fp[0]), (fp[0][0], fp[0][1] + dc))
		pg.click("#g-feito")
		pg.wait_for_function("([gid, c]) => grupo(gid).posicao.c0 === c && !S.busy", arg=[g2, c0 + dc], timeout=10_000)
		_imagem_ok(pg, g2)
		assert not errs, errs
	finally:
		pg.close()


def test_b1a_ver_muda_pelo_meio(gr, browser):
	"""(a) uma escrita no tabuleiro (S.ver muda) entre o «Mostrar» e o arrasto, e outra logo a seguir ao arrasto."""
	url, gui, ids = gr
	pg, errs, reqs = _abrir_g2(browser, url, ids)
	try:
		g2 = ids["G2"]
		v0 = pg.evaluate("S.ver")
		st, r = _post(url, "/api/confirm", {"acao": "cell_full", "cell": [4, 1]})
		assert st == 200, r
		pg.wait_for_function("(v) => S.ver !== v", arg=v0, timeout=10_000)
		_imagem_ok(pg, g2)
		_ctrl_mover(pg, g2)
		v1 = pg.evaluate("S.ver")
		st, r = _post(url, "/api/confirm", {"acao": "cell_empty", "cell": [4, 1]})
		assert st == 200, r
		pg.wait_for_function("(v) => S.ver !== v", arg=v1, timeout=10_000)
		_imagem_ok(pg, g2)
		assert not errs, errs
	finally:
		pg.close()


def test_b1b_rodar_muda_o_endereco(gr, browser):
	url, gui, ids = gr
	pg, errs, reqs = _abrir_g2(browser, url, ids)
	try:
		g2 = ids["G2"]
		_imagem_ok(pg, g2)
		u0 = pg.evaluate(ESTADO, g2)["url"]
		for d in (90, -90, 90):
			st, r = _post(url, f"/api/grupos/{g2}/mover", {"rodar": d})
			if st == 200:
				break
		assert st == 200, r
		pg.wait_for_function("([gid, u]) => { const el = document.querySelector(`#lyr-grupos [data-grupo=\"${gid}\"] image.grupo-img`); return el && el.getAttribute('data-url') !== u; }",
			arg=[g2, u0], timeout=10_000)
		_imagem_ok(pg, g2)
		assert not errs, errs
	finally:
		pg.close()


def test_b1c_dois_grupos_mostrados_seguidos(gr, browser):
	url, gui, ids = gr
	pg, errs = _abrir(browser, url)
	try:
		_pronto(pg)
		# G1 ja aparece sozinho (lugar provavel): tira-o e mostra-o pela lista, seguido do G2
		for i in (0, 1):
			b = pg.locator("#tab-montar .grp-row").nth(i).locator(".grp-mostrar")
			b.click()
			pg.click("#grp-voltar") if pg.locator("#grp-voltar").count() else None
			pg.wait_for_selector("#tab-montar .grp-row", timeout=10_000)
		for k in ("G1", "G2"):
			_imagem_ok(pg, ids[k])
		_ctrl_mover(pg, ids["G2"])
		for k in ("G1", "G2"):
			_imagem_ok(pg, ids[k])
		assert not errs, errs
	finally:
		pg.close()


def test_b2_carregar_sem_nada_a_pedir_nao_fica_em_voo(gr, browser):
	"""Causa provada (H2): com todas as imagens ja em cache, ``carregarPngs`` acabava antes de ``pngsP`` ser atribuido e
	``pngsP`` ficava preso; o pedido seguinte so marcava ``pngsDeNovo`` e nunca mais se pedia nada."""
	url, gui, ids = gr
	pg, errs = _abrir(browser, url)
	try:
		_pronto(pg)
		pg.wait_for_function("document.querySelectorAll('#lyr-grupos image.grupo-img[href]').length === 1", timeout=10_000)
		pg.evaluate("async () => { await (pngsP || null); await carregarPngs(); }")
		assert pg.evaluate("pngsP === null")
		assert not errs, errs
	finally:
		pg.close()


def test_b3_falha_da_descarga_tenta_de_novo_e_vai_para_o_registo(gr, browser):
	"""Uma falha nao e silenciosa: 2 novas tentativas com recuo; a 3.a falha vai para ``/api/cliente/erro``."""
	url, gui, ids = gr
	pg, errs = _abrir(browser, url)
	try:
		_pronto(pg)
		g2 = ids["G2"]
		falhas = {"n": 0, "todas": False}
		def rota(route):
			if falhas["todas"] or falhas["n"] < 2:
				falhas["n"] += 1
				route.fulfill(status=500, body="erro")
			else:
				route.continue_()
		pg.route(f"**/api/grupos/{g2}.png*", rota)
		erros = []
		pg.on("request", lambda r: erros.append(r.post_data) if r.url.endswith("/api/cliente/erro") else None)
		pg.locator("#tab-montar .grp-row").nth(1).locator(".grp-mostrar").click()
		pg.wait_for_selector(f"#lyr-grupos [data-grupo='{g2}']", timeout=10_000)
		_imagem_ok(pg, g2)                                                   # 2 falhas, a 3.a tentativa chega
		assert falhas["n"] == 2 and not erros
		falhas["todas"] = True                                               # agora falha sempre: outra versao, 3 tentativas, 1 erro
		v0 = pg.evaluate("S.ver")
		n0 = falhas["n"]
		st, r = _post(url, "/api/confirm", {"acao": "cell_full", "cell": [4, 1]})
		assert st == 200, r
		pg.wait_for_function("(v) => S.ver !== v", arg=v0, timeout=10_000)
		pg.wait_for_function("() => [...(S.pngsFalhou || [])].some((u) => u.includes('%s'))" % g2, timeout=10_000)
		assert falhas["n"] - n0 == 3
		pg.wait_for_timeout(300)
		assert any(g2 in (e or "") for e in erros), erros
		assert not errs, errs
	finally:
		pg.close()


def test_b1d_escrita_antes_do_mostrar_com_a_lista_aberta(gr, browser):
	"""A sequencia do Tiago: lista «Grupos soltos» aberta (miniaturas ja na cache: um ``carregarPngs`` sem nada a pedir),
	uma escrita qualquer (S.ver muda), depois «Mostrar no tabuleiro» e Ctrl+arrastar."""
	url, gui, ids = gr
	pg, errs = _abrir(browser, url)
	try:
		_pronto(pg)
		g2 = ids["G2"]
		pg.wait_for_selector(f"img.grp-thumb[data-grupo-thumb='{g2}'][src]", timeout=10_000)
		pg.evaluate("async () => { await (pngsP || null); carregarPngs(); }")       # o que o IntersectionObserver faz ao redesenhar
		v0 = pg.evaluate("S.ver")
		st, r = _post(url, "/api/confirm", {"acao": "cell_full", "cell": [4, 1]})
		assert st == 200, r
		pg.wait_for_function("(v) => S.ver !== v", arg=v0, timeout=10_000)
		pg.locator("#tab-montar .grp-row").nth(1).locator(".grp-mostrar").click()
		pg.wait_for_selector(f"#lyr-grupos [data-grupo='{g2}']", timeout=10_000)
		_imagem_ok(pg, g2)
		_ctrl_mover(pg, g2)
		_imagem_ok(pg, g2)
		_imagem_ok(pg, ids["G1"])
		assert not errs, errs
	finally:
		pg.close()
