"""Capturas da F2b da GUI nova (/novo/), numa CÓPIA do projeto, a 1366x768 e a 390x844 (``F2b_<ecrã>_<vp>.png``).

Uso::

    python tools/gui/f2b_capturas.py --project COPIA_DE_ALPES --out docs/gui/screenshots

Ecrãs: ``lupa_peca`` (separador «Peça» com o resultado de Saco + nº), ``lupa_lugar`` (separador «Lugar» com o
resultado), ``lupa_erro_linha`` («Linha 1 a 47») e ``lupa_erro_saco`` («Saco 9 não tem nº 200») com o aviso à vista,
``trabalho_gravar`` («A gravar…»), ``trabalho_sugestoes`` («A atualizar sugestões…»; no 1.º ecrã é o recálculo real do
arranque a frio, nos outros o estado é forçado no browser por ``S.pendente`` / ``S.montar.a_preparar``: o desenho é o
mesmo código) e ``ligacao`` (o servidor pára com a página aberta: faixa «Ligação perdida, a tentar religar…»).
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from f1b_capturas import VIEWPORTS, _server, _settle, _stop  # noqa: E402

HIDE = "* { caret-color: transparent !important; }"        # os avisos (toast) ficam à vista


def _shot(pg, out, name, settle=600):
	pg.add_style_tag(content=HIDE)
	_settle(pg, settle)
	pg.screenshot(path=os.path.join(out, name))
	print("  ", name, flush=True)


def _peca(pg, saco, n):
	pg.click("#s-peca")
	pg.fill("#q-saco", str(saco))
	pg.fill("#q-n", str(n))
	pg.press("#q-saco", "Enter")


def _lugar(pg, l, c):
	pg.click("#s-lugar")
	pg.fill("#q-linha", str(l))
	pg.fill("#q-coluna", str(c))
	pg.press("#q-coluna", "Enter")


def capture(project, out, saco, n, cell):
	from playwright.sync_api import sync_playwright
	os.makedirs(out, exist_ok=True)
	rec = {}
	srv, base = _server(project)
	try:
		with sync_playwright() as pw:
			br = pw.chromium.launch()
			for k, (vp, (w, h)) in enumerate(VIEWPORTS.items()):
				ctx = br.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
				pg = ctx.new_page()
				pg.goto(base + "/novo/")
				pg.wait_for_selector("body[data-ready='1']", timeout=300_000)
				if k == 0:      # recálculo real das sugestões pelo encaixe (arranque a frio), se ainda estiver a correr
					pg.wait_for_timeout(1500)
					if pg.locator(".trabalho[data-trabalho=sugestoes]").count():
						rec["sugestoes_real"] = pg.inner_text("#board-wrap .trabalho")
						_shot(pg, out, f"F2b_trabalho_sugestoes_{vp}.png")
				for _ in range(300):
					if pg.evaluate("!!(S.montar && !(S.montar.a_preparar||{}).buracos)"):
						break
					pg.wait_for_timeout(3000)
					pg.evaluate("loadMontar()")
				_settle(pg, 1200)
				if k > 0 or "sugestoes_real" not in rec:       # estado forçado (mesmo desenho)
					pg.evaluate("S.montar.a_preparar = { buracos: true, progresso: { n: 40, N: 212, segundos: 12 } }; renderMontar()")
					_shot(pg, out, f"F2b_trabalho_sugestoes_{vp}.png")
					pg.evaluate("S.montar.a_preparar = { buracos: false }; renderMontar()")
				pg.evaluate("S.pendente = 'A gravar…'; renderMontar()")
				_shot(pg, out, f"F2b_trabalho_gravar_{vp}.png")
				pg.evaluate("S.pendente = null; renderMontar()")
				_peca(pg, saco, n)
				pg.wait_for_selector("#lupa-res[data-kind=peca]:not([hidden])", timeout=60_000)
				_shot(pg, out, f"F2b_lupa_peca_{vp}.png", 1500)
				rec.setdefault(vp, {})["peca"] = pg.inner_text("#lupa-res")
				pg.click("#lupa-fechar")
				_lugar(pg, cell[0], cell[1])
				pg.wait_for_selector("#lupa-res[data-kind=lugar]:not([hidden])", timeout=60_000)
				_shot(pg, out, f"F2b_lupa_lugar_{vp}.png", 1500)
				rec[vp]["lugar"] = pg.inner_text("#lupa-res")
				pg.click("#lupa-fechar")
				_lugar(pg, 99, 3)
				pg.wait_for_selector("#toast .err", timeout=10_000)
				_shot(pg, out, f"F2b_lupa_erro_linha_{vp}.png", 300)
				rec[vp]["erro_linha"] = pg.inner_text("#toast")
				pg.wait_for_function("!document.querySelector('#toast .err')", timeout=15_000)
				_peca(pg, saco, 200)
				pg.wait_for_selector("#toast .err", timeout=10_000)
				_shot(pg, out, f"F2b_lupa_erro_saco_{vp}.png", 300)
				rec[vp]["erro_saco"] = pg.inner_text("#toast")
				if k == len(VIEWPORTS) - 1:        # servidor para com a página aberta
					pass
				ctx.close()
			# ligação perdida: um contexto por ecrã; o servidor pára no fim do último
			for vp, (w, h) in VIEWPORTS.items():
				ctx = br.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
				pg = ctx.new_page()
				pg.goto(base + "/novo/")
				pg.wait_for_selector("body[data-ready='1']", timeout=300_000)
				pg.wait_for_timeout(1000)
				_stop(srv)
				pg.wait_for_selector("#ligacao", state="visible", timeout=30_000)
				rec[vp]["ligacao"] = pg.inner_text("#ligacao")
				_shot(pg, out, f"F2b_ligacao_{vp}.png", 300)
				ctx.close()
				srv, base = _server(project)         # volta para o ecrã seguinte
			br.close()
	finally:
		_stop(srv)
	with open(os.path.join(out, "F2b_capturas.json"), "w", encoding="utf-8") as f:
		json.dump(rec, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
	ap = argparse.ArgumentParser()
	ap.add_argument("--project", required=True)
	ap.add_argument("--out", default=os.path.join("docs", "gui", "screenshots"))
	ap.add_argument("--saco", type=int, default=9)
	ap.add_argument("--n", type=int, default=89)
	ap.add_argument("--cell", default="1,29")
	a = ap.parse_args()
	capture(a.project, a.out, a.saco, a.n, [int(x) for x in a.cell.split(",")])
