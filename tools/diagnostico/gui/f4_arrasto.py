"""Critério 14 da F4 (F4_PLANO.md §4): Ctrl+arrastar um grupo 60 passos com todos os grupos soltos mostrados, em
Chromium headless a 1366 × 768: duração de cada frame (``requestAnimationFrame``), alvo 0 frames acima de 25 ms.

Promovido do guião do helper do B4 (etapa 2). Numa cópia da base (nunca o projeto real), ``Gui`` no próprio processo
(uvicorn num fio, como os testes Playwright); «Mostrar» de todos os grupos; o maior grupo escolhido e a vista nele; 60
passos grandes de rato (±300 × ±200 px, senos) com Ctrl premido; o POST final do arrasto é intercetado (409) para não
gravar e o grupo voltar atrás. ``--n`` corridas.

Uso: ``python tools/diagnostico/gui/f4_arrasto.py <base> <trabalho> <saída.json> [--n 3]``."""
import argparse
import json
import math
import os
import shutil
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

FRAMES_JS = """() => { window.__ft = []; window.__stop = false; let last = 0;
  const loop = (t) => { if (last) window.__ft.push(t - last); last = t; if (!window.__stop) requestAnimationFrame(loop); };
  requestAnimationFrame(loop); }"""
CELL_JS = """([l, c]) => { const r = svgRect(), v = S.vb;
  return { x: r.left + ((c - 0.5) - v.x) / v.w * r.width, y: r.top + (((l - 0.5) * S.hr) - v.y) / v.h * r.height }; }"""


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("base")
	ap.add_argument("work")
	ap.add_argument("out")
	ap.add_argument("--n", type=int, default=3)
	ap.add_argument("--passos", type=int, default=60)
	a = ap.parse_args()
	from playwright.sync_api import sync_playwright
	from src import server as SV
	from test_gui_novo import _serve
	proj = os.path.join(a.work, "proj_arrasto")
	shutil.rmtree(proj, ignore_errors=True)
	shutil.copytree(a.base, proj)
	gui = SV.Gui(proj, prepare=False, use_image=False, uploads=os.path.join(a.work, "up"), log=None)
	url, server, th = _serve(gui)

	def post(path, body):
		rq = urllib.request.Request(url + path, data=json.dumps(body).encode(), method="POST",
									headers={"Content-Type": "application/json"})
		try:
			with urllib.request.urlopen(rq, timeout=120) as r:
				return r.status
		except urllib.error.HTTPError as e:
			return e.code

	res = {"corridas": []}
	try:
		d = json.loads(urllib.request.urlopen(url + "/api/grupos").read())
		for i, g in enumerate(d["grupos"]):
			post(f"/api/grupos/{g['id']}/mostrar", {"centro": [5 + (i % 8) * 5, 5 + (i // 8) * 14]})
		d = json.loads(urllib.request.urlopen(url + "/api/grupos").read())
		res["n_grupos"], res["n_mostrados"] = d["n_grupos"], d["n_mostrados"]
		gid = max(d["grupos"], key=lambda g: g["n"])["id"]
		res["grupo"] = gid
		with sync_playwright() as pw:
			br = pw.chromium.launch()
			pg = br.new_page(viewport={"width": 1366, "height": 768})
			pg.goto(url + "/novo/")
			pg.wait_for_selector("body[data-ready='1']", timeout=120000)
			pg.click("#vista-grupos")
			pg.wait_for_selector("#lyr-grupos .grupo", timeout=20000)
			res["desenhados"] = pg.locator("#lyr-grupos > .grupo").count()
			pg.evaluate("(gid) => { escolherGrupo(gid); const g = grupo(gid); showCell(g.footprint[0][0], g.footprint[0][1]); }", gid)
			pg.wait_for_timeout(2500)
			cel = pg.evaluate("(gid) => grupo(gid).footprint[0]", gid)
			p0 = pg.evaluate(CELL_JS, cel)
			res["px_por_celula"] = pg.evaluate("pxPerCell()")
			pg.route("**/api/grupos/*/mover", lambda r: r.fulfill(status=409, content_type="application/json",
																  body=json.dumps({"error": "medição"})))
			for _ in range(a.n):
				pg.evaluate(FRAMES_JS)
				pg.keyboard.down("Control")
				pg.mouse.move(p0["x"], p0["y"])
				pg.mouse.down()
				for i in range(1, a.passos + 1):
					pg.mouse.move(p0["x"] + 300 * math.sin(i * 0.5), p0["y"] + 200 * math.sin(i * 0.37))
				moved = pg.evaluate("(g) => { const e = document.querySelector(`#lyr-grupos [data-grupo=\"${g}\"]`); return !!(e && e.getAttribute('transform')); }", gid)
				pg.mouse.up()
				pg.keyboard.up("Control")
				pg.wait_for_timeout(150)
				ft = pg.evaluate("(() => { window.__stop = true; return window.__ft; })()")
				s = sorted(ft)
				res["corridas"].append({"frames": len(ft), "max_ms": round(max(ft), 1), "mediana_ms": round(s[len(s) // 2], 1),
										"p95_ms": round(s[int(len(s) * 0.95)], 1), "acima_25ms": [round(x, 1) for x in ft if x > 25],
										"grupo_deslocado": moved})
				pg.wait_for_timeout(300)
			br.close()
	finally:
		server.should_exit = True
		th.join(10)
		shutil.rmtree(proj, ignore_errors=True)
	res["max_ms"] = max(r["max_ms"] for r in res["corridas"])
	res["n_acima_25ms"] = sum(len(r["acima_25ms"]) for r in res["corridas"])
	with open(a.out, "w", encoding="utf-8") as fh:
		json.dump(res, fh, indent=1, ensure_ascii=False)
	print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
	main()
