"""Toque multi-dedo no tabuleiro (bug do iPhone, teste do Tiago 2026-11-18), escrito ANTES da correção.

Sintomas: (a) uma pinça para afastar às vezes aproxima (o 2.º dedo conta como toque duplo); (b) depois de uma pinça, um dedo
a arrastar faz zoom sozinho e os toques num lugar deixam de funcionar (um dedo ficou «pousado» no mapa de ponteiros).

Critérios:
- toque duplo = dois toques COMPLETOS sem movimento e com NENHUM outro dedo no ecrã; um 2.º dedo cancela o toque duplo
  pendente e o toque simples;
- ``pointercancel``, ``lostpointercapture`` e ``pointerup`` em qualquer sítio limpam o dedo;
- quando sai um dedo da pinça, o que fica passa a arrasto a partir da posição atual, sem salto;
- sem dedos no ecrã o estado volta ao inicial (``S.gesto`` falso, um arrasto de um dedo só translada, um toque abre o lugar).

Toque REAL multi-dedo: CDP ``Input.dispatchTouchEvent`` (Chromium headless, ``slow``) sobre o projeto sintético de
``tests/test_query.py``.
"""

import pytest

pytestmark = pytest.mark.slow
pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")
pytest.importorskip("httpx")
sync_api = pytest.importorskip("playwright.sync_api")

from test_gui_novo import base, guarda, browser, _open_any  # noqa: E402,F401
from test_gui_novo_f2e import XY, _open, _outra_celula, _vista_para_ppc, VP_PC, VP_TEL  # noqa: E402,F401


class Dedos:
	"""Dedos reais via CDP: cada evento leva todos os pontos ativos (como o dispositivo de toque)."""

	def __init__(self, pg):
		self.pg = pg
		self.cdp = pg.context.new_cdp_session(pg)
		self.pts = {}

	def _send(self, tipo, pts=None):
		pts = list(self.pts.items()) if pts is None else pts
		self.cdp.send("Input.dispatchTouchEvent", {
			"type": tipo, "touchPoints": [{"x": x, "y": y, "id": i} for i, (x, y) in pts]})

	def down(self, i, x, y):
		self.pts[i] = (x, y)
		self._send("touchStart")

	def move(self, i, x, y):
		self.pts[i] = (x, y)
		self._send("touchMove")

	def up(self, i):
		"""No CDP o ``touchEnd`` leva os pontos que terminam (não os que ficam)."""
		self._send("touchEnd", [(i, self.pts.pop(i))])

	def cancel(self):
		self.pts.clear()
		self._send("touchCancel", [])

	def wait(self, ms):
		self.pg.wait_for_timeout(ms)


def _centro(pg):
	return pg.evaluate("(() => { const r = document.querySelector('#board').getBoundingClientRect();"
	                   " return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; })()")


def _vb(pg):
	return pg.evaluate("({ ...S.vb })")


def _taps(pg):
	return pg.evaluate("window.__taps.length")


def _abre(browser, url, vp):
	pg, errs = _open(browser, url, vp, has_touch=True)
	cell = _outra_celula(pg)
	_vista_para_ppc(pg, min(vp) / 12, cell)      # longe do limite do toque duplo
	return pg, errs, cell, Dedos(pg)


def _pinca_afastar(f, cx, cy, d0=40, d1=70, passos=6):
	f.down(1, cx - d0, cy)
	f.down(2, cx + d0, cy)
	for k in range(1, passos + 1):
		d = d0 + (d1 - d0) * k / passos
		f.move(1, cx - d, cy)
		f.move(2, cx + d, cy)
	f.wait(30)


def _estado_limpo(pg, f, cell):
	"""Sem dedos: ``S.gesto`` falso; um dedo a arrastar só translada; um toque simples abre o lugar."""
	assert not pg.evaluate("S.gesto")
	c = _centro(pg)
	v0 = _vb(pg)
	f.down(7, c["x"], c["y"])
	for k in range(1, 7):
		f.move(7, c["x"] - 12 * k, c["y"] + 6 * k)
	f.up(7)
	f.wait(30)
	v1 = _vb(pg)
	assert v1["w"] == pytest.approx(v0["w"], rel=1e-6), "um dedo a arrastar não pode fazer zoom"
	assert v1["x"] > v0["x"] + 0.1 and v1["y"] < v0["y"] - 0.01, "o arrasto de um dedo translada"
	n = _taps(pg)
	p = pg.evaluate(XY, cell)
	f.down(8, p["x"], p["y"])
	f.up(8)
	pg.wait_for_function(f"window.__taps.length > {n}", timeout=2000)   # o toque simples chega (≈ 250 ms)
	assert not pg.evaluate("S.gesto")


def test_pinch_apart_zooms_in_by_the_finger_ratio(base, browser):
	url, gui, tw = base
	pg, errs, cell, f = _abre(browser, url, VP_TEL)
	try:
		c = _centro(pg)
		w0 = _vb(pg)["w"]
		_pinca_afastar(f, c["x"], c["y"])
		w1 = _vb(pg)["w"]
		assert w0 / w1 == pytest.approx(70 / 40, rel=0.1)
		f.up(1); f.up(2)
		f.wait(400)
		assert _taps(pg) == 0
		_estado_limpo(pg, f, cell)
	finally:
		pg.close()


def test_two_fingers_landing_within_250ms_and_30px_are_a_pinch_not_a_double_tap(base, browser):
	url, gui, tw = base
	pg, errs, cell, f = _abre(browser, url, VP_TEL)
	try:
		c = _centro(pg)
		w0 = _vb(pg)["w"]
		f.down(1, c["x"] - 10, c["y"])          # 20 px um do outro, 40 ms depois
		f.wait(40)
		f.down(2, c["x"] + 10, c["y"])
		for k in range(1, 9):
			f.move(1, c["x"] - 10 - 8 * k, c["y"])
			f.move(2, c["x"] + 10 + 8 * k, c["y"])
		f.wait(30)
		w1 = _vb(pg)["w"]
		assert w0 / w1 == pytest.approx(148 / 20, rel=0.1)    # a pinça, não um 2× de toque duplo
		f.up(1); f.up(2)
		f.wait(400)
		assert _taps(pg) == 0
		_estado_limpo(pg, f, cell)
	finally:
		pg.close()


def test_a_tap_followed_within_250ms_by_a_second_finger_cancels_the_pending_tap(base, browser):
	"""Toque completo, e logo dois dedos a pousar: o toque pendente morre (nem simples nem duplo) e a pinça é só pinça."""
	url, gui, tw = base
	pg, errs, cell, f = _abre(browser, url, VP_TEL)
	try:
		p = pg.evaluate(XY, cell)
		w0 = _vb(pg)["w"]
		f.down(1, p["x"], p["y"])
		f.up(1)
		f.wait(60)
		f.down(2, p["x"] - 10, p["y"])           # 2.º toque, a < 30 px, mas com outro dedo no ecrã
		f.down(3, p["x"] + 10, p["y"])
		for k in range(1, 7):
			f.move(2, p["x"] - 10 - 6 * k, p["y"])
			f.move(3, p["x"] + 10 + 6 * k, p["y"])
		f.wait(30)
		w1 = _vb(pg)["w"]
		assert w0 / w1 == pytest.approx(92 / 20, rel=0.15)
		f.up(2); f.up(3)
		f.wait(500)
		assert _taps(pg) == 0, "o 1.º toque ficou pendente depois de a pinça começar"
		_estado_limpo(pg, f, cell)
	finally:
		pg.close()


def test_second_finger_tapping_while_one_is_down_is_not_a_double_tap(base, browser):
	url, gui, tw = base
	pg, errs, cell, f = _abre(browser, url, VP_TEL)
	try:
		p = pg.evaluate(XY, cell)
		w0 = _vb(pg)["w"]
		f.down(1, p["x"], p["y"])
		f.up(1)
		f.wait(60)
		f.down(2, p["x"], p["y"])               # 2.º toque a pousar...
		f.wait(30)
		f.down(3, p["x"] - 120, p["y"] + 100)   # ...com outro dedo longe (não é toque duplo)
		f.up(3)
		f.up(2)
		f.wait(500)
		assert _vb(pg)["w"] == pytest.approx(w0, rel=1e-6), "o toque duplo não pode aproximar com 2 dedos no ecrã"
		_estado_limpo(pg, f, cell)
	finally:
		pg.close()


@pytest.mark.parametrize("sai, fica", [(1, 2), (2, 1)])
def test_one_finger_up_first_then_the_other_drags_without_jump(base, browser, sai, fica):
	"""Sai um dedo da pinça (o 1.º ou o 2.º); o que fica passa a arrasto a partir da posição atual."""
	url, gui, tw = base
	pg, errs, cell, f = _abre(browser, url, VP_TEL)
	try:
		c = _centro(pg)
		_pinca_afastar(f, c["x"], c["y"])
		f.up(sai)                                # sai um dedo; o outro fica pousado
		f.wait(30)
		v0 = _vb(pg)
		x2, y2 = f.pts[fica]
		f.move(fica, x2 + 1, y2)                 # primeiro movimento: sem salto
		f.wait(30)
		v1 = _vb(pg)
		assert v1["w"] == pytest.approx(v0["w"], rel=1e-6)
		assert abs(v1["x"] - v0["x"]) < 0.2 * v0["w"] / 390 * 6 and abs(v1["y"] - v0["y"]) < 0.2 * v0["w"] / 390 * 6
		for k in range(1, 6):
			f.move(fica, x2 + 1 + 15 * k, y2)
		f.wait(30)
		v2 = _vb(pg)
		assert v2["w"] == pytest.approx(v0["w"], rel=1e-6)
		assert v2["x"] < v0["x"] - 0.05, "arrastar para a direita move a vista para a esquerda"
		f.up(fica)
		f.wait(400)
		assert _taps(pg) == 0
		_estado_limpo(pg, f, cell)
	finally:
		pg.close()


def test_pointercancel_in_the_middle_of_a_pinch_resets_the_state(base, browser):
	url, gui, tw = base
	pg, errs, cell, f = _abre(browser, url, VP_TEL)
	try:
		c = _centro(pg)
		_pinca_afastar(f, c["x"], c["y"])
		f.cancel()                               # o iOS manda pointercancel
		f.wait(50)
		assert not pg.evaluate("S.gesto")
		_estado_limpo(pg, f, cell)
	finally:
		pg.close()


def test_pointercancel_of_one_finger_leaves_the_other_dragging(base, browser):
	url, gui, tw = base
	pg, errs, cell, f = _abre(browser, url, VP_TEL)
	try:
		c = _centro(pg)
		_pinca_afastar(f, c["x"], c["y"])
		f.up(1); f.up(2)
		f.wait(300)
		# um dedo pousa e um 2.º pousa e é cancelado (palma, gesto do sistema): fica um só
		f.down(1, c["x"], c["y"])
		f.down(2, c["x"] + 60, c["y"])
		f.cancel()
		f.wait(50)
		_estado_limpo(pg, f, cell)
	finally:
		pg.close()


STALE = """(id) => { const el = document.querySelector('#board');
  el.setPointerCapture = () => {};     // um ponteiro sintético não pode ser capturado
  el.dispatchEvent(new PointerEvent('pointerdown', { pointerId: id, pointerType: 'touch', clientX: 50, clientY: 50, bubbles: true }));
  delete el.setPointerCapture; }"""


@pytest.mark.parametrize("como", ["lostpointercapture", "pointerup_no_document", "pointercancel_no_document"])
def test_a_finger_is_cleared_by_lostpointercapture_or_an_event_outside_the_element(base, browser, como):
	"""O dedo 99 (sintético) pousa e nunca recebe pointerup no elemento: os três modos de o iOS o largar."""
	url, gui, tw = base
	pg, errs, cell, f = _abre(browser, url, VP_TEL)
	try:
		pg.evaluate(STALE, 99)
		fim = {
			"lostpointercapture": "document.querySelector('#board').dispatchEvent(new PointerEvent('lostpointercapture', { pointerId: 99, pointerType: 'touch', bubbles: false }))",
			"pointerup_no_document": "document.body.dispatchEvent(new PointerEvent('pointerup', { pointerId: 99, pointerType: 'touch', bubbles: true }))",
			"pointercancel_no_document": "document.body.dispatchEvent(new PointerEvent('pointercancel', { pointerId: 99, pointerType: 'touch', bubbles: true }))",
		}[como]
		pg.evaluate(fim)
		pg.wait_for_timeout(50)
		assert not pg.evaluate("S.gesto")
		_estado_limpo(pg, f, cell)
	finally:
		pg.close()


def test_a_stale_finger_does_not_survive_a_new_primary_touch(base, browser):
	"""Defesa: um toque primário (nenhum outro dedo no ecrã) limpa o que tenha ficado no mapa."""
	url, gui, tw = base
	pg, errs, cell, f = _abre(browser, url, VP_TEL)
	try:
		pg.evaluate(STALE, 99)                   # fica pousado, sem nenhum evento que o limpe
		pg.evaluate("S.gesto = false")
		_estado_limpo(pg, f, cell)
	finally:
		pg.close()
