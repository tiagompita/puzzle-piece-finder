"""Diagnóstico: 1.º salto com /api/grupos normal (A) vs retido até depois do salto (B). Uso: diag_grupos.py N saida.json repo base"""
import argparse, json, os, sys
sys.path.insert(0, r"D:\DEKSTOP\puzzle_piece_finder\tools\diagnostico\gui")
import desempenho as D

RES_JS = r"""(t0) => performance.getEntriesByType('resource').filter(e => /api\/(grupos|board\.jpg|montar|board\b|ghosts)/.test(e.name))
  .map(e => ({n: e.name.replace(/^https?:\/\/[^/]+/, '').slice(0, 70), ini: +(e.startTime/1000).toFixed(3), fim: +(e.responseEnd/1000).toFixed(3), dur: +(e.duration/1000).toFixed(3)}))"""

def uma(a, br, tag, hold):
	held = []
	with D.Run(a, tag) as r:
		out = r.out
		pg = br.new_page(viewport={"width": 1920, "height": 1080})
		pg.add_init_script(D.PRONTO_JS)
		if hold:
			pg.route("**/api/grupos", lambda route: held.append(route))
		pg.goto(D.G.BASE_URL + "/novo/")
		pr = pg.evaluate("window.__pronto")
		out["abrir_s"] = round(pr["t_ms"] / 1000, 3)
		t_jump = pg.evaluate("performance.now()/1000")
		out["salto"] = D.jump(pg, 5, 30)
		out["t_jump"] = round(t_jump, 3)
		pg.wait_for_timeout(3000)
		out["res"] = pg.evaluate(RES_JS)
		out["held"] = len(held)
		for rt in held:
			try: rt.continue_()
			except Exception: pass
		pg.wait_for_timeout(1500)
		out["grupos_depois"] = pg.evaluate("!!S.grupos")
		pg.close()
	return out

def main():
	n, outp, repo, base = int(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
	from playwright.sync_api import sync_playwright
	pw = sync_playwright().start(); br = pw.chromium.launch()
	work = os.path.join(os.environ.get("TEMP", "."), "diag_grupos"); os.makedirs(work, exist_ok=True)
	rows = []
	try:
		for i in range(n):
			for hold in ((False, True) if i % 2 == 0 else (True, False)):
				a = argparse.Namespace(base=base, work=work, repo=repo, sem_acoes="", tag=("B" if hold else "A"))
				row = uma(a, br, f"{'B' if hold else 'A'}_{i}", hold)
				row["hold"] = hold; row["volta"] = i
				rows.append(row)
				json.dump(rows, open(outp, "w"), ensure_ascii=False, indent=1)
				print(f"volta {i} hold={hold}: abrir {row['abrir_s']} salto {row['salto']['s']} held={row['held']} grupos_depois={row['grupos_depois']}", flush=True)
	finally:
		br.close(); pw.stop()

main()
