"""Ronda 8 — CPU do servidor da GUI em repouso (Parte 0.2 do prompt de 2026-11-08).

Arranca `python -m src.server` numa CÓPIA do projeto, espera `estado == pronto`, e mede o tempo de CPU do processo
(psutil, % de um núcleo) em janelas de 60 s sem nenhum pedido, nos cenários:

    a  sem nenhum separador aberto
    b  1 separador Chromium (Playwright) com a gaveta «Atividade» fechada
    c  1 separador com a gaveta «Atividade» aberta
    d  3 separadores
    e  1 separador sem EventSource (stub): isola o gerador SSE

Também regista o CPU por thread (psutil `threads()`), para atribuir a fonte. Nunca correr sobre `projects/alpes`.

    python tools/diagnostico/servidor/repouso.py --project <cópia> --tag antes [--port 8766] [--janela 60] [--espera 60]
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

import psutil

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DOC = os.path.join(REPO, "docs", "diagnostico", "servidor")
ES_STUB = """
window.__ppf_es_stub = true;
window.EventSource = class { constructor(u) { this.url = u; this.readyState = 1; } addEventListener() {} removeEventListener() {} close() {} };
"""


def wait_ready(base, timeout=300):
	t0 = time.time()
	while time.time() - t0 < timeout:
		try:
			with urllib.request.urlopen(base + "/api/status", timeout=5) as r:
				st = json.loads(r.read().decode("utf-8"))
			if st.get("estado") == "pronto" and not st.get("job"):
				return st
		except Exception:  # noqa: BLE001
			pass
		time.sleep(1)
	raise RuntimeError("servidor não ficou pronto")


def tree(proc):
	"""O processo e os filhos: no Windows o ``python.exe`` de um venv é um lançador que corre o interpretador real
	como filho, por isso o CPU que interessa está no filho."""
	return [proc] + proc.children(recursive=True)


def cpu_total(procs):
	tot = 0.0
	for p in procs:
		try:
			c = p.cpu_times()
			tot += c.user + c.system
		except psutil.Error:
			pass
	return tot


def cpu_window(proc, seconds):
	"""% de um núcleo da árvore do processo (e por thread do interpretador real) numa janela de ``seconds`` sem pedidos."""
	procs = tree(proc)
	main = max(procs, key=lambda p: (p.num_threads() if p.is_running() else 0))
	t0 = time.perf_counter()
	c0 = cpu_total(procs)
	th0 = {t.id: (t.user_time + t.system_time) for t in main.threads()}
	time.sleep(seconds)
	c1 = cpu_total(procs)
	th1 = {t.id: (t.user_time + t.system_time) for t in main.threads()}
	wall = time.perf_counter() - t0
	tot = c1 - c0
	per = {str(k): round(100.0 * (th1[k] - th0.get(k, 0.0)) / wall, 2) for k in th1}
	top = sorted(per.items(), key=lambda kv: -kv[1])[:4]
	return dict(wall_s=round(wall, 1), cpu_s=round(tot, 3), pct_core=round(100.0 * tot / wall, 2), n_threads=len(th1), top_threads=top,
				pids=[p.pid for p in procs])


def main(argv=None):
	ap = argparse.ArgumentParser()
	ap.add_argument("--project", required=True)
	ap.add_argument("--port", type=int, default=8766)
	ap.add_argument("--tag", default="antes")
	ap.add_argument("--janela", type=int, default=60)
	ap.add_argument("--espera", type=int, default=60, help="segundos de assentamento depois de montar o cenário")
	ap.add_argument("--cenarios", default="a,b,c,d,e")
	ap.add_argument("--python", default=sys.executable)
	args = ap.parse_args(argv)
	base = f"http://127.0.0.1:{args.port}"
	env = dict(os.environ, PYTHONIOENCODING="utf-8")
	log = open(os.path.join(DOC, f"repouso_{args.tag}_servidor.log"), "w", encoding="utf-8")
	srv = subprocess.Popen([args.python, "-u", "-X", "utf8", "-m", "src.server", "--project", args.project, "--port", str(args.port)],
						   cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT)
	out = dict(t=time.strftime("%Y-%m-%dT%H:%M:%S"), tag=args.tag, project=os.path.abspath(args.project), pid=srv.pid,
			   janela_s=args.janela, espera_s=args.espera, cenarios={})
	try:
		st = wait_ready(base)
		proc = psutil.Process(srv.pid)
		print(f"servidor pronto (pid {srv.pid}, árvore {[p.pid for p in tree(proc)]}, versão {st.get('versao')}); cpu acumulado {cpu_total(tree(proc)):.1f} s", flush=True)
		from playwright.sync_api import sync_playwright
		with sync_playwright() as pw:
			br = pw.chromium.launch()
			for sc in args.cenarios.split(","):
				ctx = br.new_context(viewport={"width": 1366, "height": 768})
				pages = []
				if sc == "a":
					n_pages, act, es = 0, False, True
				elif sc == "b":
					n_pages, act, es = 1, False, True
				elif sc == "c":
					n_pages, act, es = 1, True, True
				elif sc == "d":
					n_pages, act, es = 3, False, True
				elif sc == "e":
					n_pages, act, es = 1, False, False
				else:
					continue
				if not es:
					ctx.add_init_script(ES_STUB)
				for _ in range(n_pages):
					pg = ctx.new_page()
					pg.goto(base + "/", wait_until="load")
					pg.wait_for_selector("#top", timeout=60_000)
					pages.append(pg)
				if act and pages:
					pages[0].click("#tg-act")
					pages[0].wait_for_selector("#atividade:not([hidden])", timeout=10_000)
				# assentamento: as páginas pedem /api/fetch (buracos em thread) e o tabuleiro; esperar que o servidor sossegue
				time.sleep(args.espera)
				w = cpu_window(proc, args.janela)
				w.update(cenario=sc, paginas=n_pages, atividade_aberta=act, eventsource=es)
				out["cenarios"][sc] = w
				print(json.dumps(w, ensure_ascii=False), flush=True)
				ctx.close()
			br.close()
	finally:
		try:
			kids = psutil.Process(srv.pid).children(recursive=True)
		except psutil.Error:
			kids = []
		for p in kids + [psutil.Process(srv.pid)]:
			try:
				p.terminate()
			except psutil.Error:
				pass
		psutil.wait_procs(kids, timeout=10)
		try:
			srv.wait(timeout=10)
		except Exception:  # noqa: BLE001
			srv.kill()
		log.close()
	path = os.path.join(DOC, f"repouso_{args.tag}.json")
	os.makedirs(DOC, exist_ok=True)
	with open(path, "w", encoding="utf-8") as f:
		json.dump(out, f, ensure_ascii=False, indent=1)
	print("escrito", path)
	return 0


if __name__ == "__main__":
	sys.exit(main())
