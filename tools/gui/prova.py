"""Prova da GUI (levantamento §5, 2026-11-26): capturas dos ecrãs principais numa cópia do projeto, com falhas automáticas.

Uso::

	.venv/Scripts/python.exe -m tools.gui.prova [--base projects/alpes] [--out DIR] [--porto 8796]

* copia ``--base`` para uma pasta temporária (``guarda.copytree``; nunca o projeto real) e arranca
  ``python -m src.server --ui novo`` sobre a cópia; espera pelo «pronto» e pelo fim do ranking dos buracos;
* guarda PNG a 1366 × 768 e 390 × 844 de: Montar, tabuleiro geral, detalhe com zoom, painel da peça, painel do lugar,
  lupa, «Grupos soltos» (lista e painel do grupo), menu, definições e Reports com as Suspeitas (GUI antiga, ``/``);
* escreve ``indice.html`` (capturas lado a lado) e ``capturas.json`` (sha256, tempos, falhas) na pasta de saída: por
  omissão ``$PPF_SCRATCH/prova_gui/<data>`` ou ``<temp>/ppf_prova_gui/<data>`` (fora do repositório);
* **falha** (código 1) com: erro de consola do browser (``console.error``, exceção da página, linha ``erro_cliente``
  no registo do servidor), resposta HTTP ≥ 500, scroll horizontal a 390 px, ou ecrã em branco (todos os píxeis
  iguais). O código 2 é um erro de ambiente (servidor não arrancou, Playwright em falta).

Reaproveita ``tools/gui/d1_capturas.py`` (cópia com ``guarda``, servidor num porto, Playwright). Não compara píxeis:
a data, o tabuleiro e o texto mudam; a revisão estética continua humana, mas sobre imagens."""
import argparse
import datetime
import hashlib
import html
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.request

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "tools" / "diagnostico" / "gui")]
import guarda  # noqa: E402  (único caminho permitido para copiar/apagar cópias do projeto)

__all__ = ["VPS", "ECRAS", "em_branco", "scroll_horizontal", "falhas_de", "indice_html", "main"]

VPS = {"1366": (1366, 768), "390": (390, 844)}
ECRAS = ("montar", "tabuleiro", "detalhe", "peca", "lugar", "lupa", "grupos", "grupo", "menu", "definicoes", "reports")
_PRONTO_S = 900


# ------------------------------------------------------------------ verificações puras (testadas sem servidor)
def em_branco(png_path) -> bool:
	"""Ecrã em branco: todos os píxeis iguais (qualquer cor)."""
	from PIL import Image
	with Image.open(png_path) as im:
		ex = im.convert("RGB").getextrema()
	return all(lo == hi for lo, hi in ex)


def scroll_horizontal(scroll_w: int, client_w: int) -> bool:
	"""Há scroll horizontal se a largura do conteúdo passa a da janela (1 px de folga para arredondamentos)."""
	return int(scroll_w) > int(client_w) + 1


def falhas_de(ev: dict) -> list:
	"""Lista de falhas ``[texto]`` dos eventos de uma captura: ``consola`` (erros), ``respostas`` (``[(url, status)]``),
	``scroll`` (``(scrollWidth, clientWidth)`` a 390 px ou None), ``branco`` (bool), ``erro`` (exceção do passo)."""
	out = [f"consola: {t}" for t in ev.get("consola") or []]
	out += [f"HTTP {st}: {u}" for u, st in ev.get("respostas") or [] if int(st) >= 500]
	sc = ev.get("scroll")
	if sc is not None and scroll_horizontal(*sc):
		out.append(f"scroll horizontal: scrollWidth {sc[0]} > clientWidth {sc[1]}")
	if ev.get("branco"):
		out.append("ecrã em branco (todos os píxeis iguais)")
	if ev.get("erro"):
		out.append(f"passo falhou: {ev['erro']}")
	return out


def indice_html(capturas: list, titulo: str) -> str:
	"""HTML com as capturas lado a lado (uma linha por ecrã, uma coluna por janela) e as falhas a vermelho."""
	por = {}
	for c in capturas:
		por.setdefault(c["ecra"], {})[c["vp"]] = c
	L = ["<!doctype html><meta charset='utf-8'>", f"<title>{html.escape(titulo)}</title>",
		 "<style>body{font:14px sans-serif;margin:16px}td{vertical-align:top;padding:6px}"
		 "img{border:1px solid #999;max-width:700px}.f{color:#b00}</style>", f"<h1>{html.escape(titulo)}</h1><table>"]
	for ecra in [e for e in ECRAS if e in por]:
		L.append(f"<tr><th>{html.escape(ecra)}</th>")
		for vp in VPS:
			c = por[ecra].get(vp)
			if c is None:
				L.append("<td>—</td>")
				continue
			fal = "".join(f"<div class='f'>{html.escape(t)}</div>" for t in c["falhas"])
			img = f"<img src='{html.escape(c['png'])}'>" if c.get("png") else ""
			L.append(f"<td><div>{vp} · {c['segundos']} s</div>{img}{fal}</td>")
		L.append("</tr>")
	L.append("</table>")
	return "\n".join(L)


# ------------------------------------------------------------------ servidor
def _json(url, timeout=30):
	with urllib.request.urlopen(url, timeout=timeout) as r:
		return json.loads(r.read().decode("utf-8"))


def _esperar(base, srv) -> None:
	t0 = time.time()
	while time.time() - t0 < _PRONTO_S:
		if srv.poll() is not None:
			raise RuntimeError(f"o servidor terminou (código {srv.returncode})")
		try:
			st = _json(base + "/api/status")
			if st.get("estado") == "pronto" and not st.get("job"):
				break
		except Exception:  # noqa: BLE001 - ainda a arrancar
			pass
		time.sleep(0.5)
	else:
		raise RuntimeError("o servidor não ficou pronto")
	while time.time() - t0 < _PRONTO_S:
		if not _json(base + "/api/holes", 120).get("a_calcular"):
			return
		time.sleep(0.5)
	raise RuntimeError("o ranking dos buracos não acabou")


def _parar(p, f) -> None:
	p.terminate()
	try:
		p.wait(30)
	except subprocess.TimeoutExpired:
		p.kill()
		p.wait(30)
	f.close()


def _celulas(proj: str) -> dict:
	"""Uma célula com peça colocada e uma vazia com vizinha colocada (determinísticas: a primeira por ordem)."""
	from src.state import Project
	pr = Project.open(proj)
	cheia = vazia = None
	for (l, c), b in pr.board.iter_cells():
		if cheia is None and b["estado"] == "colocada":
			cheia = (l, c)
		if vazia is None and b["estado"] == "vazia":
			viz = [(l + dl, c + dc) for dl, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)) if pr.profile.in_grid(l + dl, c + dc)]
			if any(pr.board[v]["estado"] == "colocada" for v in viz):
				vazia = (l, c)
		if cheia and vazia:
			break
	return {"cheia": cheia, "vazia": vazia}


# ------------------------------------------------------------------ capturas
def _passos(cel: dict) -> list:
	"""``[(ecra, url, ação)]``: a ação recebe a página e prepara o ecrã (cada ecrã parte de uma página nova)."""
	cl, cc = cel["cheia"]
	vl, vc = cel["vazia"]

	def montar(pg):
		pg.wait_for_timeout(2500)

	def tabuleiro(pg):
		pg.click("#z-fit")
		pg.wait_for_timeout(1500)

	def detalhe(pg):
		pg.evaluate(f"zoomCells({max(1, cl - 2)}, {max(1, cc - 3)}, {cl + 2}, {cc + 3}, 0.04)")
		pg.wait_for_timeout(4000)

	def peca(pg):
		pg.evaluate(f"openPainel({cl}, {cc})")
		pg.wait_for_selector("#painel[data-kind='peca']", timeout=60_000)
		pg.wait_for_timeout(1500)

	def lugar(pg):
		pg.evaluate(f"openPainel({vl}, {vc})")
		pg.wait_for_selector("#painel[data-kind='vazio']", timeout=60_000)
		pg.wait_for_timeout(1500)

	def lupa(pg):
		pg.evaluate("openLupa('peca')")
		pg.wait_for_timeout(800)

	def grupos(pg):
		pg.evaluate("setVista('grupos')")
		pg.wait_for_selector("#tab-montar [data-vista='grupos']", timeout=30_000)
		pg.wait_for_timeout(2000)

	def grupo(pg):
		grupos(pg)
		gid = pg.evaluate("(S.grupos && (S.grupos.grupos || []).length) ? S.grupos.grupos[0].gid : null")
		if gid:
			pg.evaluate(f"escolherGrupo({json.dumps(gid)})")
			pg.wait_for_timeout(1500)

	def menu(pg):
		pg.click("#menu-btn")
		pg.wait_for_timeout(800)

	def definicoes(pg):
		pg.evaluate("openDefinicoes()")
		pg.wait_for_selector("#definicoes", timeout=10_000)
		pg.wait_for_timeout(800)

	def reports(pg):
		pg.evaluate("showTab('reports')")
		pg.wait_for_timeout(3000)

	return [("montar", "/novo/", montar), ("tabuleiro", "/novo/", tabuleiro), ("detalhe", "/novo/", detalhe),
			("peca", "/novo/", peca), ("lugar", "/novo/", lugar), ("lupa", "/novo/", lupa), ("grupos", "/novo/", grupos),
			("grupo", "/novo/", grupo), ("menu", "/novo/", menu), ("definicoes", "/novo/", definicoes),
			("reports", "/", reports)]


def _capturar(br, base: str, out: pathlib.Path, cel: dict) -> list:
	caps = []
	for vp, (w, h) in VPS.items():
		for ecra, url, acao in _passos(cel):
			t0 = time.time()
			ev = {"consola": [], "respostas": []}
			pg = br.new_page(viewport={"width": w, "height": h})
			pg.on("console", lambda m, ev=ev: ev["consola"].append(m.text[:300]) if m.type == "error" else None)
			pg.on("pageerror", lambda e, ev=ev: ev["consola"].append(f"exceção: {str(e)[:300]}"))
			pg.on("response", lambda r, ev=ev: ev["respostas"].append((r.url, r.status)) if r.status >= 500 else None)
			png = out / f"{ecra}_{vp}.png"
			try:
				pg.goto(base + url)
				pg.wait_for_selector("body[data-ready='1']", timeout=300_000)
				acao(pg)
				if vp == "390":
					ev["scroll"] = tuple(pg.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]"))
				pg.screenshot(path=str(png))
				ev["branco"] = em_branco(png)
			except Exception as e:  # noqa: BLE001 - um passo que falha é uma falha da prova, não um erro da ferramenta
				ev["erro"] = f"{type(e).__name__}: {str(e).splitlines()[0][:300]}"
			finally:
				pg.close()
			caps.append({"ecra": ecra, "vp": vp, "png": png.name if png.exists() else None,
						 "sha256": hashlib.sha256(png.read_bytes()).hexdigest() if png.exists() else None,
						 "segundos": round(time.time() - t0, 1), "falhas": falhas_de(ev)})
			print(f"  {ecra:11s} {vp}: {caps[-1]['segundos']} s" + (f"  FALHA {caps[-1]['falhas']}" if caps[-1]["falhas"] else ""),
				  flush=True)
	return caps


def _erros_cliente(log_dir: pathlib.Path) -> list:
	"""Linhas ``erro_cliente`` (``POST /api/cliente/erro``) do registo do servidor na cópia."""
	out = []
	for fp in sorted(log_dir.glob("servidor-*.log")) if log_dir.is_dir() else []:
		out += [l.strip()[:300] for l in fp.read_text(encoding="utf-8", errors="replace").splitlines() if "erro_cliente" in l]
	return out


def main(argv=None) -> int:
	ap = argparse.ArgumentParser(prog="python -m tools.gui.prova", description=__doc__.splitlines()[0])
	ap.add_argument("--base", default=os.path.join("projects", "alpes"), help="projeto a copiar (nunca é escrito)")
	ap.add_argument("--out", default=None, help="pasta das capturas (por omissão fora do repositório)")
	ap.add_argument("--porto", type=int, default=8796)
	a = ap.parse_args(argv)
	t0 = time.time()
	if a.out:
		out = pathlib.Path(a.out)
	else:
		raiz = os.environ.get("PPF_SCRATCH") or os.path.join(tempfile.gettempdir(), "ppf_prova_gui")
		out = pathlib.Path(raiz) / "prova_gui" / datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
	out.mkdir(parents=True, exist_ok=True)
	try:
		from playwright.sync_api import sync_playwright
	except ImportError as e:
		print(f"prova da GUI: Playwright em falta ({e})")
		return 2
	base_dir = a.base if os.path.isabs(a.base) else str(REPO / a.base)
	tmp = pathlib.Path(tempfile.mkdtemp(prefix="ppf_prova_gui_"))
	proj = tmp / "proj"
	url = f"http://127.0.0.1:{a.porto}"
	# sem logs/: o registo da cópia só pode ter as linhas desta corrida (as erro_cliente antigas do projeto não contam)
	guarda.copytree(base_dir, str(proj), ignore=lambda d, nomes: ["logs"] if os.path.normpath(d) == os.path.normpath(base_dir) else [])
	f = open(tmp / "srv.log", "w", encoding="utf-8")
	srv = subprocess.Popen([sys.executable, "-m", "src.server", "--project", str(proj), "--port", str(a.porto),
							"--uploads", str(tmp / "up"), "--ui", "novo"], cwd=str(REPO), stdout=f, stderr=subprocess.STDOUT)
	res = {"quando": datetime.datetime.now().isoformat(timespec="seconds"), "base": base_dir, "saidas": str(out)}
	codigo = 0
	try:
		try:
			_esperar(url, srv)
		except Exception as e:  # noqa: BLE001
			print(f"prova da GUI: {e}")
			return 2
		res["arranque_s"] = round(time.time() - t0, 1)
		cel = _celulas(str(proj))
		res["celulas"] = cel
		with sync_playwright() as pw:
			br = pw.chromium.launch()
			try:
				caps = _capturar(br, url, out, cel)
			finally:
				br.close()
		res["capturas"] = caps
		res["erro_cliente"] = _erros_cliente(proj / "logs")
		fal = [f"{c['ecra']} {c['vp']}: {t}" for c in caps for t in c["falhas"]]
		fal += [f"registo do servidor: {l}" for l in res["erro_cliente"]]
		res["falhas"] = fal
		codigo = 1 if fal else 0
	finally:
		_parar(srv, f)
		time.sleep(1)
		res["srv_log_cauda"] = (tmp / "srv.log").read_text(encoding="utf-8", errors="replace").splitlines()[-20:]
		guarda.rmtree(str(tmp), ignore_errors=True)
	res["codigo"] = codigo
	res["segundos"] = round(time.time() - t0, 1)
	(out / "capturas.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
	(out / "indice.html").write_text(indice_html(res.get("capturas", []), f"Prova da GUI — {res['quando']}"), encoding="utf-8")
	print(f"prova da GUI: código {codigo} em {res['segundos']} s; {len(res.get('capturas', []))} capturas em {out}")
	for t in res.get("falhas", []):
		print(f"  FALHA {t}")
	return codigo


if __name__ == "__main__":
	sys.exit(main())
