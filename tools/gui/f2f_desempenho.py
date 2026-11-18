"""Desempenho da F2f: arrasto do tabuleiro com 0 e com N cartoes extra na fila (todos os alvos desenhados). Mede, em
Chromium headless, os intervalos entre frames (rAF) durante um arrasto de 60 passos e o custo de ``updateAlvoTag``.

Uso::

    .venv/Scripts/python.exe tools/gui/f2f_desempenho.py [N=60]
"""

import json
import statistics
import sys
import tempfile
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "tests")]


def main(n):
	from playwright.sync_api import sync_playwright
	import synth
	from src import server as SV
	from src.query import run_query, load_fetch
	from test_gui_novo import _serve
	from test_query import _project
	orig = synth.profile
	synth.profile = lambda rows=4, cols=6, **k: orig(rows=47, cols=64, **k)
	tmp = pathlib.Path(tempfile.mkdtemp())
	pr, placed, tw, dec = _project(tmp)
	run_query(pr, use_image=False)
	cell = [e for e in load_fetch(pr)["entries"] if e.get("piece")][0]["cell"]
	nb = [x for x in pr.board.neighbours(tuple(cell)) if pr.board[x]["estado"] == "vazia"][0]
	pr.mark_cell_full(nb)
	pr.save()
	gui = SV.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp / "uploads"), log=None)
	url, server, th = _serve(gui)
	l0, c0 = cell
	try:
		with sync_playwright() as pw:
			br = pw.chromium.launch()
			for k in (0, n):
				kk = k
				pg = br.new_page(viewport={"width": 1366, "height": 768})
				def handle(route):
					r = route.fetch(); m = r.json()
					if m.get("itens"):
						tpl = m["itens"][0]
						for i in range(kk):
							m["itens"].append(dict(tpl, piece=f"P9{i:03d}", n_no_lote=90 + i, cell=[max(1, l0 - 1 - (i % 9)), max(1, c0 - 2 - 2 * (i // 9) - (i % 2))]))
						m["total"] = len(m["itens"])
					route.fulfill(response=r, body=json.dumps(m), headers=dict(r.headers, **{"content-type": "application/json"}))
				pg.route("**/api/montar*", handle)
				pg.goto(url + "/novo/")
				pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
				pg.wait_for_selector("#tab-montar .card[data-piece]", timeout=60_000)
				pg.wait_for_timeout(800)
				pg.evaluate(f"zoomCells({l0 - 10}, {c0 - 20}, {l0}, {c0 + 2}, 0.04)")
				pg.wait_for_timeout(1500)
				info = pg.evaluate("[document.querySelectorAll('#lyr-seguinte rect').length, celulaPx()]")
				bb = pg.locator("#board").bounding_box()
				cx, cy = bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2
				pg.evaluate("""window.__fr = []; (function loop(t0) { requestAnimationFrame((t) => { if (t0) window.__fr.push(t - t0); window.__on && loop(t); }); })(0); window.__on = true;""")
				pg.evaluate("window.__on = true; (function loop(t0) { requestAnimationFrame((t) => { if (t0) window.__fr.push(t - t0); if (window.__on) loop(t); }); })(0)")
				pg.mouse.move(cx, cy); pg.mouse.down()
				for i in range(1, 61):
					pg.mouse.move(cx - 6 * i, cy + 2 * i)
				pg.mouse.up()
				pg.evaluate("window.__on = false")
				fr = pg.evaluate("window.__fr")
				ua = pg.evaluate("(() => { const t = performance.now(); for (let i = 0; i < 1000; i++) updateAlvoTag(); return (performance.now() - t) / 1000; })()")
				dr = pg.evaluate("(() => { const t = performance.now(); for (let i = 0; i < 50; i++) drawTarget(false); return (performance.now() - t) / 50; })()")
				print(f"extra={k} alvos_ténues={info[0]} px/cel={info[1]:.1f} frames={len(fr)} mediana={statistics.median(fr):.1f} ms "
					  f"p95={sorted(fr)[int(0.95 * len(fr))]:.1f} ms max={max(fr):.1f} ms >25ms={sum(x > 25 for x in fr)} "
					  f"updateAlvoTag={ua * 1000:.1f} us drawTarget={dr:.2f} ms")
				pg.close()
			br.close()
	finally:
		server.should_exit = True
		th.join(10)


if __name__ == "__main__":
	main(int(sys.argv[1]) if len(sys.argv) > 1 else 60)
