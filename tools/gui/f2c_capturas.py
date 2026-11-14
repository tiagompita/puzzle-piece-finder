"""Capturas da F2c da GUI nova (/novo/) e da antiga (/), numa CÓPIA do projeto, a 1366x768 e a 390x844
(``F2c_<ecrã>_<vp>.png``).

Uso::

    python tools/gui/f2c_capturas.py --project COPIA_DE_ALPES --out docs/gui/screenshots [--arranque]

Ecrãs: ``lupa_fechada``, ``lupa_peca`` (caixa «Peça» aberta), ``lupa_posicao`` (caixa «Posição» aberta),
``lupa_erro`` (valor fora da grelha), ``destaque`` (resultado da lupa com o contorno animado no tabuleiro),
``borda`` (menu com «Mostrar a borda em falta» e a nota «Não falta nenhuma peça de borda.»).

Com ``--arranque`` captura também os ecrãs de arranque das duas GUIs (``arranque_novo``, ``arranque_antiga``): o servidor
é lançado COM preparação num projeto onde faltam 3 recortes (``render.stale_assets`` vê 3 folhas desatualizadas e
re-segmenta-as a sério), por isso o texto e o n de N são os reais. Prepare a cópia apagando um recorte de cada uma das
folhas S0001 a S0003 (``crops/``).
"""

import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from f1b_capturas import REPO, VIEWPORTS, _server, _settle, _stop  # noqa: E402
from f1b_capturas import free_port  # noqa: E402

HIDE = "* { caret-color: transparent !important; }"


def _shot(pg, out, name, settle=500, full=False):
	pg.add_style_tag(content=HIDE)
	_settle(pg, settle)
	pg.screenshot(path=os.path.join(out, name), full_page=full)
	print("  ", name, flush=True)


def _abrir(pg, modo, txt=None):
	if not pg.locator(f"#lupa-c-{modo}").is_visible():
		pg.click(f"#lupa-b-{modo}")
	if txt is not None:
		pg.fill(f"#lupa-q-{modo}", txt)
		pg.press(f"#lupa-q-{modo}", "Enter")


def arranque(project, out):
	"""Os dois ecrãs de arranque com o servidor a refazer imagens a sério (3 folhas)."""
	from playwright.sync_api import sync_playwright
	port = free_port()
	env = dict(os.environ, PYTHONIOENCODING="utf-8")
	srv = subprocess.Popen([sys.executable, "-m", "src.server", "--project", project, "--port", str(port)], cwd=REPO, env=env,
						   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
	base = f"http://127.0.0.1:{port}"
	rec = {}
	try:
		t0 = time.time()
		while time.time() - t0 < 60:
			try:
				import urllib.request
				urllib.request.urlopen(base + "/api/status", timeout=1).read()
				break
			except OSError:
				time.sleep(0.1)
		with sync_playwright() as pw:
			br = pw.chromium.launch()
			for vp, (w, h) in VIEWPORTS.items():
				for nome, pagina, sel in (("novo", "/novo/", "#prep-texto"), ("antiga", "/", "#prep-now")):
					ctx = br.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
					pg = ctx.new_page()
					pg.goto(base + pagina)
					try:
						pg.wait_for_function(f"/folha [12] de 3/.test((document.querySelector('{sel}') || {{}}).textContent || '')", timeout=120_000)
						rec[f"{nome}_{vp}"] = pg.inner_text(sel)
						_shot(pg, out, f"F2c_arranque_{nome}_{vp}.png", 200)
					except Exception as e:  # noqa: BLE001
						rec[f"{nome}_{vp}"] = f"sem captura: {e}"
					ctx.close()
			br.close()
	finally:
		_stop(srv)
	return rec


def ecras(project, out, saco, n, cell):
	from playwright.sync_api import sync_playwright
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
				for _ in range(300):
					if pg.evaluate("!!(S.montar && !(S.montar.a_preparar||{}).buracos)"):
						break
					pg.wait_for_timeout(3000)
					pg.evaluate("loadMontar()")
				_settle(pg, 1200)
				r = rec.setdefault(vp, {})
				_shot(pg, out, f"F2c_lupa_fechada_{vp}.png")
				pg.click("#lupa-b-peca")
				pg.fill("#lupa-q-peca", f"{saco} {n}")
				_shot(pg, out, f"F2c_lupa_peca_{vp}.png", 450)
				pg.click("#lupa-b-pos")
				pg.fill("#lupa-q-pos", f"{cell[0]},{cell[1]}")
				_shot(pg, out, f"F2c_lupa_posicao_{vp}.png", 450)
				pg.fill("#lupa-q-pos", "99 3")
				pg.press("#lupa-q-pos", "Enter")
				pg.wait_for_selector("#lupa-m-pos:not([hidden])", timeout=10_000)
				r["erro"] = pg.inner_text("#lupa-m-pos")
				_shot(pg, out, f"F2c_lupa_erro_{vp}.png", 300)
				pg.fill("#lupa-q-pos", f"{cell[0]}-{cell[1]}")
				pg.press("#lupa-q-pos", "Enter")
				pg.wait_for_selector("#lupa-res[data-kind=lugar]:not([hidden])", timeout=60_000)
				pg.wait_for_selector("#lyr-achado rect.achado", timeout=10_000)
				r["destaque"] = pg.evaluate("[...document.querySelectorAll('#lyr-achado rect.achado')].map(r => [r.getAttribute('x'), r.getAttribute('y')])")
				pg.wait_for_timeout(1500)       # o detalhe do tabuleiro chega
				_shot(pg, out, f"F2c_destaque_{vp}.png", 400)
				pg.click("#lupa-fechar")
				pg.click("#menu-btn")
				pg.check("#m-borda")
				r["borda"] = pg.inner_text("#m-borda-nota")
				_shot(pg, out, f"F2c_borda_{vp}.png", 300)
				ctx.close()
			br.close()
	finally:
		_stop(srv)
	return rec


if __name__ == "__main__":
	ap = argparse.ArgumentParser()
	ap.add_argument("--project", required=True)
	ap.add_argument("--out", default=os.path.join("docs", "gui", "screenshots"))
	ap.add_argument("--saco", type=int, default=9)
	ap.add_argument("--n", type=int, default=89)
	ap.add_argument("--cell", default="1,29")
	ap.add_argument("--arranque", action="store_true", help="só os ecrãs de arranque (o projeto leva 3 recortes apagados)")
	a = ap.parse_args()
	os.makedirs(a.out, exist_ok=True)
	rec = arranque(a.project, a.out) if a.arranque else ecras(a.project, a.out, a.saco, a.n, [int(x) for x in a.cell.split(",")])
	with open(os.path.join(a.out, "F2c_capturas_arranque.json" if a.arranque else "F2c_capturas.json"), "w", encoding="utf-8") as f:
		json.dump(rec, f, ensure_ascii=False, indent=1)
