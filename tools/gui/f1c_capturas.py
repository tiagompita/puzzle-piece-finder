"""Capturas da F1c do redesenho («Guardar à parte», ecrã vazio com contagens, lupa) em /novo/.

Uso::

    python tools/gui/f1c_capturas.py --project COPIA_DE_ALPES --out DIR

Arranca ``python -m src.server`` sobre ``--project`` (uma CÓPIA de projects/alpes: os passos ``nao`` e ``vazio``
gravam rejeições e posições guardadas e desfazem-nas a seguir) e, a 1366x768 e a 390x844, guarda em PNG:

* ``F1c_guardar_<vp>.png``: o cartão «Guardar à parte» com o alvo tracejado e «A seguir»;
* ``F1c_nao_<vp>.png``: depois de «Não é esta» (desfeito a seguir);
* ``F1c_lupa_peca_<vp>.png``: a lupa sobre a peça do cartão (saco e nº);
* ``F1c_lupa_lugar_<vp>.png``: a lupa sobre o lugar provável dessa peça;
* ``F1c_vazio_<vp>.png``: o ecrã vazio com as contagens, depois de «Guardei à parte» em todos os cartões (desfeito a
  seguir pela API, ``position_clear`` com ``desfaz``).

Escreve ``F1c_contagens.json``: palavras e botões visíveis em ``#top`` + painel em cada estado, e a fila.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from f1b_capturas import _COUNT, VIEWPORTS, _novo, _server, _settle, _stop  # noqa: E402

HIDE = "#toast, #job-pill { visibility: hidden !important; } * { caret-color: transparent !important; }"


def _shot(pg, out, name, hide_toast=True):
	if hide_toast:
		pg.add_style_tag(content=HIDE)
	_settle(pg)
	pg.screenshot(path=os.path.join(out, name))
	print("  ", name)


def _search(pg, txt):
	pg.fill("#q", txt)
	pg.press("#q", "Enter")
	pg.wait_for_selector("#lupa-res:not([hidden])", timeout=60_000)


def capture(project, out):
	from playwright.sync_api import sync_playwright
	os.makedirs(out, exist_ok=True)
	counts = {}
	srv, base = _server(project)
	try:
		with sync_playwright() as pw:
			br = pw.chromium.launch()
			for tag, (w, h) in VIEWPORTS.items():
				ctx = br.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
				pg = ctx.new_page()
				msgs = []
				pg.on("console", lambda msg: msgs.append(f"{msg.type}: {msg.text}"))
				pg.on("pageerror", lambda e: msgs.append(f"pageerror: {e}"))
				_novo(pg, base)
				pg.wait_for_selector("#tab-montar .card[data-tipo='guardar']", timeout=120_000)
				m = pg.evaluate("S.montar")
				first = m["itens"][0]
				counts[f"fila_{tag}"] = {"total": m["total"], "n_coloca": m["n_coloca"], "n_guardar": m["n_guardar"],
										"fora_da_fila": m["fora_da_fila"],
										"itens": [(it["piece"], it["tipo"], it["lote"], it["n_no_lote"], it["cell"]) for it in m["itens"]]}
				_shot(pg, out, f"F1c_guardar_{tag}.png")
				counts[f"guardar_{tag}"] = pg.evaluate(_COUNT, ["#top", "#tab-montar"])
				pg.click("#b-nao")
				pg.wait_for_selector("#m-motivos", timeout=120_000)
				_shot(pg, out, f"F1c_nao_{tag}.png")
				pg.click("#b-desfazer")
				pg.wait_for_selector(f"#tab-montar .card[data-tipo][data-piece='{first['piece']}']", timeout=120_000)
				_search(pg, f"saco {first['lote']} nº {first['n_no_lote']}")
				_shot(pg, out, f"F1c_lupa_peca_{tag}.png")
				pg.click("#lupa-fechar")
				_search(pg, f"{first['cell'][0]},{first['cell'][1]}")
				pg.wait_for_selector("#lupa-res[data-kind=lugar]", timeout=60_000)
				_shot(pg, out, f"F1c_lupa_lugar_{tag}.png")
				pg.click("#lupa-fechar")
				guardadas = []
				for _ in range(m["n_guardar"]):
					pid = pg.locator("#tab-montar .card").get_attribute("data-piece")
					pg.click("#b-guardar")
					guardadas.append(pid)
					try:
						pg.wait_for_function("(pid) => !(S.montar.itens || []).some((it) => it.piece === pid) && !S.busy", arg=pid,
											 timeout=180_000)
					except Exception:
						print("fila:", pg.evaluate("S.montar.itens.map((it) => it.piece)"), "busy:", pg.evaluate("S.busy"))
						print(chr(10).join(msgs[-20:]))
						raise
				pg.wait_for_selector("#tab-montar [data-estado^=vazio]", timeout=120_000)
				_shot(pg, out, f"F1c_vazio_{tag}.png")
				counts[f"vazio_{tag}"] = pg.evaluate(_COUNT, ["#top", "#tab-montar"])
				counts[f"vazio_{tag}"]["fora_da_fila"] = pg.evaluate("S.montar.fora_da_fila")
				for pid in guardadas:                 # desfaz na cópia, para o viewport seguinte partir do mesmo estado
					r = pg.evaluate("""async (pid) => { const r = await fetch('/api/confirm', { method: 'POST',
						headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ acao: 'position_clear', piece: pid, desfaz: true }) });
						return r.status; }""", pid)
					assert r == 200, (pid, r)
				ctx.close()
			br.close()
	finally:
		_stop(srv)
	with open(os.path.join(out, "F1c_contagens.json"), "w", encoding="utf-8") as f:
		json.dump(counts, f, ensure_ascii=False, indent=1)
	print(json.dumps(counts, ensure_ascii=False))


def main(argv=None) -> int:
	ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	ap.add_argument("--project", required=True)
	ap.add_argument("--out", required=True)
	a = ap.parse_args(argv)
	capture(os.path.abspath(a.project), a.out)
	return 0


if __name__ == "__main__":
	sys.exit(main())
