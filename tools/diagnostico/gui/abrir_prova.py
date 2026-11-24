"""Prova de que o sinal «pronto» de ``desempenho.PRONTO_JS`` não dispara antes de a página estar utilizável.

Servidor real do checkout dado, página com atrasos artificiais nos pedidos de que o «pronto» depende (route do Playwright,
atraso em ``asyncio``, sem bloquear o resto):
  A) raster do tabuleiro (``/api/board.jpg?ppc=60&v=…``, sem ``region``) +1,5 s e ``/api/montar`` +1,0 s, e ``/api/grupos`` +2,5 s:
     o sinal tem de vir >= 1,5 s (>= 2,5 s num commit que espera pelos grupos);
  B) ecrã com ``device_scale_factor`` 3 (o tabuleiro pede logo um detalhe) e o detalhe (``region=``) +4 s: o sinal tem de
     vir depois de o detalhe estar no ecrã (``data-detail`` = ``S.detailKey``, ``#detail`` visível, decodificado);
  C) sem atrasos: o estado completo no instante do sinal, e interação imediata (zoom + separador) a funcionar.
Em cada caso verifica, no instante em que o sinal chega, as condições uma a uma (``verif``). Sai com 1 se alguma falhar.

Uso: ``python abrir_prova.py <repo> <base> [<out.json>]``."""
import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import desempenho as D  # noqa: E402

G = D.G


async def caso(browser, nome, atrasos, dsf=1):
	"""``atrasos`` = [(substring do URL, s, só_sem_region|só_com_region|None)]; devolve o resumo do caso."""
	ctx = await browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=dsf)
	pg = await ctx.new_page()
	chegadas = {}

	async def rota(route):
		u = route.request.url
		for sub, s, modo in atrasos:
			if sub in u and (modo is None or (modo == "sem_region") == ("region=" not in u)):
				await asyncio.sleep(s)
				break
		await route.continue_()

	await pg.route("**/api/**", rota)
	pg.on("response", lambda r: chegadas.setdefault(r.url.split("?")[0].replace(G.BASE_URL, "") + ("?region" if "region=" in r.url else ""), None))
	await pg.add_init_script(D.PRONTO_JS)
	await pg.goto(G.BASE_URL + "/novo/")
	r = await pg.evaluate("window.__pronto")
	# interação imediata: zoom e separador
	antes = await pg.evaluate("S.vb.w")
	await pg.click("#z-in")
	await pg.click("#tabs button[data-tab=pecas]")
	depois = await pg.evaluate("[S.vb.w, document.querySelector('#tabs button[data-tab=pecas]').getAttribute('aria-selected')]")
	det = await pg.evaluate("({key: S.detailKey, data: document.body.dataset.detail, vis: document.querySelector('#detail').getAttribute('visibility')})")
	out = {"caso": nome, "t_s": round(r["t_ms"] / 1000, 3), "verif": r["verif"], "zoom_mudou": depois[0] != antes and depois[1] == "true", "zoom_antes_depois": [antes, depois[0]]}
	await ctx.close()
	return out


async def main_async(repo, base):
	import argparse as ap
	a = ap.Namespace(base=os.path.abspath(base), work=os.path.join(os.environ.get("TEMP", "."), "abrir_prova"), repo=os.path.abspath(repo), sem_acoes="")
	os.makedirs(a.work, exist_ok=True)
	from playwright.async_api import async_playwright
	res = []
	with D.Run(a, "prova") as r:
		async with async_playwright() as pw:
			br = await pw.chromium.launch()
			res.append(await caso(br, "A_raster+1.5_montar+1.0_grupos+2.5", [("/api/board.jpg", 1.5, "sem_region"), ("/api/montar", 1.0, None), ("/api/grupos", 2.5, None)]))
			res.append(await caso(br, "B_detalhe+4.0_dsf3", [("/api/board.jpg", 4.0, "com_region")], dsf=3))
			res.append(await caso(br, "C_sem_atrasos", []))
			await br.close()
	return res


def main():
	res = asyncio.run(main_async(sys.argv[1], sys.argv[2]))
	falhas = []
	for c in res:
		v = c["verif"]
		e = v["estado_no_sinal"] or {}
		cond = {k: e.get(k) for k in ("ready", "raster", "sem_prep", "tratadores", "detalhe", "ok")}
		cond["raster_decodificado"] = v["raster_decodificado"]
		cond["zoom_respondeu"] = c["zoom_mudou"]
		c["condicoes"] = cond
		if not all(cond.values()):
			falhas.append((c["caso"], "condicao", cond))
	A, B = res[0], res[1]
	if A["t_s"] < 1.5:
		falhas.append(("A", "sinal antes do raster atrasado", A["t_s"]))
	if not B["verif"]["estado_no_sinal"]["detalhe_pedido"]:
		falhas.append(("B", "o detalhe não foi pedido (a prova não exercita o ramo do detalhe)", None))
	elif B["t_s"] < 4.0:
		falhas.append(("B", "sinal antes do detalhe atrasado", B["t_s"]))
	print(json.dumps(res, indent=1, ensure_ascii=False))
	print("FALHAS:", falhas if falhas else "nenhuma")
	if len(sys.argv) > 3:
		json.dump({"casos": res, "falhas": falhas}, open(sys.argv[3], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
	sys.exit(1 if falhas else 0)


if __name__ == "__main__":
	main()
