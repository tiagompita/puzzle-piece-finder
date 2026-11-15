"""«Pôr uma peça à mão» quando o «verificar» volta sem veredicto (2026-11-15, seqlock; DETALHE.md §13.7), Chromium (slow).

O servidor devolve ``estado: nao_verificado`` (o tabuleiro mudou durante a verificação e não havia resultado anterior):
o painel continua «a verificar…» e o browser pede outra vez (500 ms, até 3 vezes); depois de 3 sem veredicto mostra
«Não consegui verificar». Projeto sintético de ``tests/test_query.py``.
"""
import threading

import pytest

pytestmark = pytest.mark.slow
pytest.importorskip("playwright.sync_api")

from test_gui_novo import browser  # noqa: E402,F401  (fixture do Chromium)
from test_gui_novo_f2 import _open, _tap, f2  # noqa: E402,F401


def _nao_verificado(gui, n_vezes):
	"""The first ``n_vezes`` «verificar» answer «não verificado»; the next ones are real. Returns the call log."""
	real = gui.verify_json
	calls = []
	lock = threading.Lock()

	def fake(l, c, pid, theta=None):
		with lock:
			k = len(calls)
			calls.append(theta)
		if k < n_vezes:
			n_viz = gui.placed_neighbours_with_shape(l, c)
			return {"piece": pid, "cell": [l, c], "theta_deg": theta, "verificacoes": [], "estado": "nao_verificado",
					"falha": False, "vizinhas_com_forma": n_viz, "modo": "colocar" if n_viz else "por_confirmar",
					"segundos": 0.0, "diagnostico": None}
		return real(l, c, pid, theta)
	gui.verify_json = fake
	return calls


def _to_step2(pg, gui, tw):
	_tap(pg, 2, 4)
	pg.wait_for_selector("#painel[data-kind='vazio']", timeout=20_000)
	pg.click("#p-por")
	p = gui.pr.piece(tw)
	pg.fill("#pm-saco", str(p.lote))
	pg.fill("#pm-n", str(p.n_no_lote))
	pg.wait_for_selector("#pm-frase[data-estado='ok']", timeout=10_000)
	pg.click("#pm-continuar")
	pg.wait_for_selector("#por-mao[data-passo='2']", timeout=10_000)


def test_nao_verificado_repete_e_mostra_o_veredicto(f2, browser):
	url, gui, placed, tw, dec = f2
	calls = _nao_verificado(gui, 2)
	pg, errs = _open(browser, url)
	try:
		_to_step2(pg, gui, tw)
		assert "a verificar…" in pg.locator("#pm-ver").inner_text()
		pg.wait_for_selector("#pm-ver li:not([data-estado='a_verificar'])", timeout=30_000)
		assert len(calls) == 3 and calls == [None, None, None], calls       # 2 without a verdict, then the real one
		keys = pg.eval_on_selector_all("#pm-ver li", "els => els.map(e => e.dataset.chave)")
		assert keys[-2:] == ["forma", "imagem"]
		assert pg.locator("#pm-preview").get_attribute("data-theta") not in ("", None)
		assert not errs, errs
	finally:
		pg.close()


def test_nao_verificado_quatro_vezes_desiste_com_aviso(f2, browser):
	url, gui, placed, tw, dec = f2
	calls = _nao_verificado(gui, 10)
	pg, errs = _open(browser, url)
	try:
		_to_step2(pg, gui, tw)
		pg.wait_for_selector("#pm-ver li[data-chave='erro']", timeout=30_000)
		assert len(calls) == 4, calls                                    # the first + 3 repeats
		assert "Não consegui verificar" in pg.locator("#pm-ver").inner_text()
		assert pg.locator("#pm-por").is_enabled()                          # never blocks
		assert not errs, errs
	finally:
		pg.close()
