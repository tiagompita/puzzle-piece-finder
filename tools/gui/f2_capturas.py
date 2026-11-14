"""Capturas da F2 da GUI nova (/novo/) e o guião da peça da borda (linha 1 · coluna 29, Saco 9 · nº 89), numa CÓPIA.

Uso::

    python tools/gui/f2_capturas.py --project COPIA_DE_ALPES --out DIR [--cell 1,29] [--saco 9 --n 89]

Arranca ``python -m src.server`` sobre ``--project`` (uma cópia de ``projects/alpes``: o guião grava e desfaz) e, a
1366x768 e a 390x844, percorre o guião do plano da F2 (§5) até ao passo 7 e guarda em PNG (``F2_<ecrã>_<vp>.png``):

* ``cartao``: o cartão do Montar «Ainda sem peças ao lado» (se a fila tiver um);
* ``marcado``: o lugar marcado por ti (a borda que falta), passo 1;
* ``pormao1`` / ``pormao1_folha``: «Pôr uma peça à mão», passo 1 (saco e nº; a grelha da folha);
* ``pormao2_averificar``: o passo 2 com as três linhas «a verificar…» e «Pôr aqui» ativo (o pedido fica retido);
* ``pormao2_falha``: uma rotação errada: o lado liso falha e o botão passa a «Pôr na mesma»;
* ``pormao2``: a rotação certa, as três verificações;
* ``peca``: o painel da peça depois de «Pôr aqui» (folha com a peça marcada, saco, nº, linha · coluna, P#### pequeno);
* ``tirar``: depois de «Tirar do lugar», a faixa «Desfazer» e o lugar outra vez «marcado por ti»;
* ``errado``: «Algo está errado» aberto; ``grupo``: uma peça de grupo; ``porconfirmar``: uma peça «por confirmar»;
* ``vazio`` / ``vazio_sugestao``: lugar vazio sem e com sugestão; ``definicoes``: «⋯ › Definições › Cor das peças».

Escreve ``F2_guiao.json``: o que cada verificação disse em cada rotação, os tempos do «verificar» (o 1.º a frio, os
seguintes a quente, ``segundos`` do servidor e o tempo no browser) e o estado do lugar em cada passo.
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from f1b_capturas import VIEWPORTS, _novo, _server, _settle, _stop  # noqa: E402

HIDE = "#toast { visibility: hidden !important; } * { caret-color: transparent !important; }"


def _shot(pg, out, name, settle=700):
	pg.add_style_tag(content=HIDE)
	_settle(pg, settle)
	pg.screenshot(path=os.path.join(out, name))
	print("  ", name, flush=True)


def _api(pg, path, body=None):
	return pg.evaluate("""async ([p, b]) => { const r = await fetch(p, b ? { method: 'POST', headers: { 'Content-Type':
		'application/json' }, body: JSON.stringify(b) } : {}); return { status: r.status, body: await r.json() }; }""", [path, body])


def _lines(pg):
	return pg.eval_on_selector_all("#pm-ver li", "els => els.map(e => ({chave: e.dataset.chave, estado: e.dataset.estado, frase: e.innerText}))")


def _wait_checks(pg, timeout=600_000):
	pg.wait_for_function("document.querySelector('#pm-ver') && !document.querySelector('#pm-ver li[data-estado=\"a_verificar\"]')",
						 timeout=timeout)


def guiao(pg, out, vp, cell, saco, n, rec):
	l, c = cell
	steps = rec.setdefault(vp, {})
	# 1. a lupa vai ao lugar; tocar abre «Lugar marcado por ti»
	pg.fill("#q", f"{l} {c}")
	pg.press("#q", "Enter")
	pg.wait_for_timeout(800)
	pg.evaluate("closeLupa()")
	pg.evaluate(f"S.onBoardTap({l}, {c})")
	pg.wait_for_selector("#painel[data-kind]:not([data-kind='a_carregar'])", timeout=60_000)
	steps["1_painel"] = pg.get_attribute("#painel", "data-kind")
	_shot(pg, out, f"F2_marcado_{vp}.png")
	# 2. «Pôr a peça digitalizada aqui» → saco e nº
	pg.click("#p-por")
	pg.fill("#pm-saco", str(saco))
	pg.fill("#pm-n", str(n))
	pg.wait_for_selector("#pm-frase[data-estado]:not([data-estado=''])", timeout=30_000)
	steps["2_frase"] = pg.inner_text("#pm-frase")
	_shot(pg, out, f"F2_pormao1_{vp}.png")
	pg.click("#pm-folha")
	pg.wait_for_selector("#pm-grade button, #pm-grade p", timeout=30_000)
	_shot(pg, out, f"F2_pormao1_folha_{vp}.png")
	# 3. passo 2: o 1.º «verificar» fica retido para a captura «a verificar…», depois segue
	held = []
	pg.route("**/verificar", lambda route: held.append(route))
	t0 = time.perf_counter()
	pg.click("#pm-continuar")
	pg.wait_for_selector("#por-mao[data-passo='2']", timeout=30_000)
	while not held and time.perf_counter() - t0 < 30:
		pg.wait_for_timeout(50)
	_shot(pg, out, f"F2_pormao2_averificar_{vp}.png", settle=300)
	steps["3_por_ativo_a_verificar"] = pg.is_enabled("#pm-por")
	t1 = time.perf_counter()
	for r in held:
		r.continue_()
	pg.unroute("**/verificar")
	_wait_checks(pg)
	v = pg.evaluate("S.porMao.verif")
	steps["3_verificar"] = [{"theta": v["theta_deg"], "segundos_servidor": v["segundos"],
							  "segundos_browser": round(time.perf_counter() - t1, 2), "linhas": _lines(pg), "falha": v["falha"],
							  "botao": pg.inner_text("#pm-por").strip(), "estado": pg.inner_text("#pm-estado")}]
	best = v["theta_deg"]
	# rotações: uma errada para a captura da falha, e de volta à melhor
	shot_fail = False
	for k in range(4):
		t1 = time.perf_counter()
		pg.click("#pm-rodar")
		_wait_checks(pg)
		v = pg.evaluate("S.porMao.verif")
		steps["3_verificar"].append({"theta": v["theta_deg"], "segundos_servidor": v["segundos"],
									 "segundos_browser": round(time.perf_counter() - t1, 2), "linhas": _lines(pg),
									 "falha": v["falha"], "botao": pg.inner_text("#pm-por").strip()})
		if v["falha"] and not shot_fail:
			_shot(pg, out, f"F2_pormao2_falha_{vp}.png")
			shot_fail = True
	assert abs(((pg.evaluate("S.porMao.theta") - best) + 180) % 360 - 180) < 0.05      # 4 × 90° = de volta à melhor
	_shot(pg, out, f"F2_pormao2_{vp}.png")
	# 4. «Pôr aqui» → painel da peça
	pg.click("#pm-por")
	pg.wait_for_selector("#painel[data-kind='peca']", timeout=120_000)
	steps["4_painel"] = pg.inner_text("#painel")
	_shot(pg, out, f"F2_peca_{vp}.png")
	# 6. «Tirar do lugar» e «Desfazer»
	pg.click("#p-tirar")
	pg.wait_for_selector("#painel[data-kind='marcado']", timeout=120_000)
	pg.wait_for_selector("#m-ultimo[data-tipo='tirar']", timeout=60_000)
	steps["6_depois_de_tirar"] = pg.get_attribute("#painel", "data-kind")
	_shot(pg, out, f"F2_tirar_{vp}.png")
	pg.click("#b-desfazer-ultimo")
	pg.wait_for_selector("#painel[data-kind='peca']", timeout=120_000)
	steps["6_depois_de_desfazer"] = pg.get_attribute("#painel", "data-kind")
	# 7. recarregar, tocar e tirar pelo painel: volta a «marcado por ti» (não a vazio)
	pg.reload()
	pg.wait_for_selector("body[data-ready='1']", timeout=300_000)
	pg.evaluate(f"S.onBoardTap({l}, {c})")
	pg.wait_for_selector("#painel[data-kind='peca']", timeout=60_000)
	pg.click("#p-tirar")
	pg.wait_for_selector("#painel[data-kind='marcado']", timeout=120_000)
	steps["7_depois_de_recarregar_e_tirar"] = pg.get_attribute("#painel", "data-kind")
	pg.evaluate("voltarFila()")


def outros(pg, out, vp, base, rec):
	steps = rec.setdefault(vp, {})
	b = _api(pg, "/api/board")["body"]
	cells = [(i + 1, j + 1, x) for i, row in enumerate(b["cells"]) for j, x in enumerate(row)]
	# peça de grupo e peça «por confirmar»
	sec = next(((l, c) for l, c, x in cells if x["estado"] == "colocada" and x["peca_id"]
				and _api(pg, f"/api/pieces/{x['peca_id']}")["body"].get("seccao_id")), None)
	if sec:
		pg.evaluate(f"S.onBoardTap({sec[0]}, {sec[1]})")
		pg.wait_for_selector("#painel[data-kind='peca']", timeout=60_000)
		_shot(pg, out, f"F2_grupo_{vp}.png")
		pg.click("#p-errado")
		_shot(pg, out, f"F2_errado_{vp}.png")
	k = (b.get("posicoes_conhecidas") or [None])[0]
	if k:
		pg.evaluate(f"S.onBoardTap({k['cell'][0]}, {k['cell'][1]})")
		pg.wait_for_selector("#painel[data-kind='por_confirmar']", timeout=60_000)
		_shot(pg, out, f"F2_porconfirmar_{vp}.png")
	# lugar vazio sem sugestão: o primeiro vazio sem proposta nem peça guardada
	m = pg.evaluate("S.montar")
	q = {tuple(it["cell"]) for it in m["itens"] if it.get("cell")}
	for l, c, x in cells:
		if x["estado"] == "vazia" and (l, c) not in q and 10 < l < 40:
			d = _api(pg, f"/api/cell/{l}/{c}")["body"]
			if not d["propostas"] and not d["conhecidas"]:
				pg.evaluate(f"S.onBoardTap({l}, {c})")
				pg.wait_for_selector("#painel[data-kind='vazio']", timeout=60_000)
				_shot(pg, out, f"F2_vazio_{vp}.png")
				steps["vazio"] = [l, c]
				break
	# lugar vazio com sugestão: o alvo do cartão atual, tocado duas vezes
	pg.evaluate("voltarFila()")
	cur = pg.evaluate("(() => { const c = current(); return c && c.cell; })()")
	if cur:
		pg.evaluate(f"S.onBoardTap({cur[0]}, {cur[1]})")
		pg.wait_for_selector("#painel[data-kind]:not([data-kind='a_carregar'])", timeout=60_000)
		_shot(pg, out, f"F2_vazio_sugestao_{vp}.png")
		steps["vazio_sugestao"] = cur
	pg.evaluate("voltarFila()")
	pg.click("#menu-btn")
	pg.click("#m-definicoes")
	pg.wait_for_selector("#definicoes")
	_shot(pg, out, f"F2_definicoes_{vp}.png")
	pg.click("#def-fechar")


def capture(project, out, cell, saco, n):
	from playwright.sync_api import sync_playwright
	os.makedirs(out, exist_ok=True)
	rec = {}
	srv, base = _server(project)
	try:
		with sync_playwright() as pw:
			br = pw.chromium.launch()
			for vp, (w, h) in VIEWPORTS.items():
				ctx = br.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
				pg = ctx.new_page()
				_novo(pg, base)
				print(vp, flush=True)
				if pg.evaluate("(() => { const c = current(); return !!c && c.tipo === 'guardar'; })()"):
					_shot(pg, out, f"F2_cartao_{vp}.png")
				guiao(pg, out, vp, cell, saco, n, rec)
				outros(pg, out, vp, base, rec)
				ctx.close()
			br.close()
	finally:
		_stop(srv)
	with open(os.path.join(out, "F2_guiao.json"), "w", encoding="utf-8") as f:
		json.dump(rec, f, ensure_ascii=False, indent=1)
	print(json.dumps(rec, ensure_ascii=False, indent=1)[:4000])


def main(argv=None) -> int:
	ap = argparse.ArgumentParser()
	ap.add_argument("--project", required=True)
	ap.add_argument("--out", required=True)
	ap.add_argument("--cell", default="1,29")
	ap.add_argument("--saco", type=int, default=9)
	ap.add_argument("--n", type=int, default=89)
	a = ap.parse_args(argv)
	if os.path.abspath(a.project).startswith(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "projects"))):
		raise SystemExit("--project tem de ser uma cópia (fora de projects/)")
	capture(a.project, a.out, tuple(int(x) for x in a.cell.split(",")), a.saco, a.n)
	return 0


if __name__ == "__main__":
	sys.exit(main())
