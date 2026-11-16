"""Capturas da ronda de 2026-11-16 da F2c (rótulo do alvo, grupo Procurar, toque no alvo, menu) da GUI nova (/novo/), numa CÓPIA do projeto, a 1366x768 e a 390x844.

Uso::

    python tools/gui/f2c_rotulo_menu_capturas.py --project COPIA_DE_ALPES --fase antes|depois --out docs/gui/screenshots/redesenho

Ficheiros ``F2c_<fase>_<ecrã>_<vp>.png``: ``cartao`` (cartão com o alvo e o rótulo, no zoom do cartão), ``inteiro`` (o tabuleiro
inteiro, «Ver o tabuleiro inteiro»: sem rótulo na fase «depois»), ``procurar`` (o grupo de pesquisa no topo) e ``menu`` (o
menu aberto). Escreve ``F2c_<fase>_medidas.json`` com a altura do texto do rótulo no ecrã (px) em cada caso.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from f1b_capturas import VIEWPORTS, _server, _settle, _stop  # noqa: E402

HIDE = "#toast { visibility: hidden !important; } * { caret-color: transparent !important; }"
# altura do texto do rótulo no ecrã = tamanho da fonte (unidades da viewBox) x px de ecrã por unidade
PX = """(() => { const t = document.querySelector('#lyr-alvo .alvo-tag text'); if (!t) return null;
  const fs = parseFloat(getComputedStyle(t).fontSize); const r = document.querySelector('#board').getBoundingClientRect();
  return { fonte_vb: fs, px_por_unidade: r.width / S.vb.w, altura_px: fs * r.width / S.vb.w,
           visivel: !!t.getBoundingClientRect().width && getComputedStyle(t.parentNode).display !== 'none' && getComputedStyle(t.parentNode).visibility !== 'hidden' }; })()"""


def _shot(pg, out, name, settle=700):
	pg.add_style_tag(content=HIDE)
	_settle(pg, settle)
	pg.screenshot(path=os.path.join(out, name))
	print("  ", name, flush=True)


def capture(project, out, fase):
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
				pg.goto(base + "/novo/")
				pg.wait_for_selector("body[data-ready='1']", timeout=300_000)
				pg.wait_for_selector("#tab-montar .card[data-piece]", timeout=120_000)
				_settle(pg, 2500)
				rec[vp] = {"cartao": pg.evaluate(PX)}
				_shot(pg, out, f"F2c_{fase}_cartao_{vp}.png")
				_shot(pg, out, f"F2c_{fase}_procurar_{vp}.png")
				pg.click("#z-fit")
				_settle(pg, 1500)
				rec[vp]["inteiro"] = pg.evaluate(PX)
				_shot(pg, out, f"F2c_{fase}_inteiro_{vp}.png")
				pg.click("#menu-btn")
				_shot(pg, out, f"F2c_{fase}_menu_{vp}.png", 500)
				ctx.close()
			br.close()
	finally:
		_stop(srv)
	with open(os.path.join(out, f"F2c_{fase}_medidas.json"), "w", encoding="utf-8") as f:
		json.dump(rec, f, ensure_ascii=False, indent=1)
	print(json.dumps(rec, ensure_ascii=False, indent=1))


if __name__ == "__main__":
	ap = argparse.ArgumentParser()
	ap.add_argument("--project", required=True)
	ap.add_argument("--fase", choices=("antes", "depois"), required=True)
	ap.add_argument("--out", default=os.path.join("docs", "gui", "screenshots", "redesenho"))
	a = ap.parse_args()
	capture(a.project, a.out, a.fase)
