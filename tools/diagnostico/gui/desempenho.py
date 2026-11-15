"""Os 5 critérios da fase de desempenho (DETALHE.md §11), numa cópia nova do projeto por corrida, servidor real.

Promovido de ``t0/baseline.py`` (passo 0 do plano da fase de desempenho). Cada corrida: ``shutil.copytree`` da base
(nunca ``cp -r``: muda o mtime de ``render/placements.json`` e invalida a cache do raster, DETALHE §6), servidor novo
(``python -m src.server``, GIL 0,5 ms), browser Chromium 1920 × 1080.

Modos (``--so``, combináveis):
- ``a``: abrir ``/novo/`` no «pronto» → 1.º salto (céu 5,30: critério 1); esperar os buracos; salto a frio na relva
  (44,40: critério 2, browser) e regiões frias só por HTTP (céu/relva); «Encaixa» perto / longe com a vista fixa no céu
  e o separador Peças (do fim do POST ao detalhe da versão nova: critério 3); pico do working set (critério 5).
- ``b``: «pronto» → ``GET /api/montar`` → 1 s → 1.º ``verificar`` a frio (critério 4) → 2.º.
- ``p``: o POST de um «Encaixa» sem browser (protocolo de §6.2: P0096 → (20,60), ``place`` + ``unplace`` com
  ``desfaz``, servidor parado e buracos acabados), 3 voltas, cronometrado por fase (``fases_post.py``).
- ``q``: o mesmo com ``/novo/`` aberto no céu (o browser recarrega durante o POST).
- ``r``: capturas céu (1,20–14,40) e relva (34,30–47,50) a ppc 100 (``--capturas DIR``, sufixo ``--sufixo``).

``--repo`` corre o servidor a partir de outro checkout (bisect em ``git worktree``); ``--sem-acoes A,B`` tira da cópia
do log as linhas dessas ações (um checkout antigo que não as conhece), e regista-o na saída.

Uso: ``python tools/diagnostico/gui/desempenho.py --base <projeto> --out <json> [--so ab] [--n 2]``."""
import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import shutil
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "tools", "diagnostico", "gui"))
sys.path.insert(0, ROOT)
import gil_intervalo as G  # noqa: E402

G.PORT = 8796
G.BASE_URL = f"http://127.0.0.1:{G.PORT}"
FASES = os.path.join(ROOT, "tools", "diagnostico", "gui", "fases_post.py")
CEU_REG, RELVA_REG = (1, 20, 14, 40), (34, 30, 47, 50)


class PMC(ctypes.Structure):
	_fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
				("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
				("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
				("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
				("PeakPagefileUsage", ctypes.c_size_t)]


class PE(ctypes.Structure):
	_fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
				("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD),
				("th32ParentProcessID", wt.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD),
				("szExeFile", ctypes.c_char * 260)]


def real_pid(pid):
	"""The venv ``python.exe`` is a launcher: the server runs in its child process."""
	k = ctypes.windll.kernel32
	k.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
	snap = k.CreateToolhelp32Snapshot(2, 0)
	e = PE()
	e.dwSize = ctypes.sizeof(PE)
	kids = []
	ok = k.Process32First(ctypes.c_void_p(snap), ctypes.byref(e))
	while ok:
		if e.th32ParentProcessID == pid:
			kids.append(e.th32ProcessID)
		ok = k.Process32Next(ctypes.c_void_p(snap), ctypes.byref(e))
	k.CloseHandle(ctypes.c_void_p(snap))
	return kids[0] if kids else pid


def mem(pid):
	"""Peak / current working set and peak private bytes (MB) of the server process."""
	pid = real_pid(pid)
	h = ctypes.windll.kernel32.OpenProcess(0x1000 | 0x0010, False, pid)
	if not h:
		return None
	try:
		c = PMC()
		c.cb = ctypes.sizeof(PMC)
		if not ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(c), c.cb):
			return None
		return {"peak_ws_mb": round(c.PeakWorkingSetSize / 2**20), "ws_mb": round(c.WorkingSetSize / 2**20),
				"peak_private_mb": round(c.PeakPagefileUsage / 2**20)}
	finally:
		ctypes.windll.kernel32.CloseHandle(h)


def pick(project):
	"""The loose piece and the near (céu, with a placed neighbour) / far (20,60) empty cells of the protocol."""
	from src.state import Project
	pr = Project.open(project)
	loose = sorted(pid for pid, p in pr.pieces.items() if p.estado == "solta")

	def near_cell(rows, cols):
		for l in rows:
			for c in cols:
				if pr.board[(l, c)]["estado"] != "vazia":
					continue
				if any(pr.board[n]["estado"] == "colocada" for n in pr.board.neighbours((l, c))):
					return [l, c]
	far = [20, 60] if pr.board[(20, 60)]["estado"] == "vazia" else near_cell(range(18, 30), range(50, 64))
	return loose[0], near_cell(range(2, 10), range(23, 38)), far


WAIT_SHOWN = """(k0) => new Promise((res) => { const t0 = performance.now();
  const f = () => { const d = document.body.dataset.detail;
    if (S.detailKey && d === S.detailKey && (!k0 || !S.detailKey.endsWith('#' + k0))) return res({ s: (performance.now() - t0) / 1000, key: S.detailKey });
    if (performance.now() - t0 > 300000) return res({ s: null, key: S.detailKey });
    requestAnimationFrame(f); }; f(); })"""


def jump(pg, l, c):
	"""``showCell`` and the time until the detail of the new view is on screen."""
	t0 = time.perf_counter()
	pg.evaluate(f"showCell({l}, {c}, true)")
	k = pg.evaluate("S.detailKey")
	r = pg.evaluate(WAIT_SHOWN, None)
	return {"s": round(time.perf_counter() - t0, 2), "key_at_jump": k, "key_shown": r["key"], "yanked": r["key"] != k}


class Events(threading.Thread):
	"""SSE listener (``/api/events``): arrival time (``perf_counter``) of each event, to measure when the suggestions
	(``holes_changed``) and the suspects (``suspeitas_changed``) reach the GUI (DETALHE.md §11, (b))."""

	def __init__(self):
		super().__init__(daemon=True)
		self.seen = []
		self.stop = False

	def run(self):
		import urllib.request
		try:
			with urllib.request.urlopen(G.BASE_URL + "/api/events", timeout=3600) as r:
				name = None
				for raw in r:
					if self.stop:
						return
					line = raw.decode("utf-8", "replace").rstrip("\r\n")
					if line.startswith("event: "):
						name = line[7:]
					elif line == "" and name:
						self.seen.append((name, time.perf_counter()))
						name = None
		except Exception:  # noqa: BLE001 - the server went away
			pass

	def first(self, name, t0, timeout=120.0):
		"""Seconds from ``t0`` to the first ``name`` at or after it (waits up to ``timeout``), or None."""
		end = time.perf_counter() + timeout
		while time.perf_counter() < end:
			for n, t in list(self.seen):
				if n == name and t >= t0:
					return round(t - t0, 2)
			time.sleep(0.05)
		return None


class Run:
	"""One fresh copy + one server; ``with Run(...) as r:``."""

	def __init__(self, a, tag, fases=None):
		self.a, self.tag, self.fases = a, tag, fases
		self.proj = os.path.join(a.work, f"proj_{tag}")
		self.up = os.path.join(a.work, f"up_{tag}")
		self.out = {"tag": tag, "repo": a.repo or ROOT}

	def __enter__(self):
		shutil.rmtree(self.proj, ignore_errors=True)
		shutil.copytree(self.a.base, self.proj)
		if self.a.sem_acoes:
			self.out["linhas_tiradas"] = strip_actions(self.proj, self.a.sem_acoes.split(","))
		os.makedirs(self.up, exist_ok=True)
		self.out["piece"], self.out["near"], self.out["far"] = pick(self.proj)
		repo = self.a.repo or ROOT
		srv = ["--project", self.proj, "--port", str(G.PORT), "--uploads", self.up, "--ui", "novo", "--gil-intervalo",
			   "0.0005"]
		cmd = [sys.executable, FASES, self.fases, "--"] + srv if self.fases else [sys.executable, "-m", "src.server"] + srv
		env = dict(os.environ, PPF_REPO=repo)
		self.f = open(os.path.join(self.a.work, f"srv_{self.tag}.log"), "w", encoding="utf-8")
		self.p = subprocess.Popen(cmd, cwd=repo, stdout=self.f, stderr=subprocess.STDOUT, env=env)
		t0 = time.time()
		while True:                                   # «pronto», or the server died (an old checkout, a bad option)
			if self.p.poll() is not None:
				self.f.close()
				raise RuntimeError(f"o servidor saiu com {self.p.returncode}: ver srv_{self.tag}.log")
			try:
				st = G._json("/api/status", 30)
				if st.get("estado") == "pronto" and not st.get("job"):
					break
			except Exception:  # noqa: BLE001 - not up yet
				pass
			if time.time() - t0 > 900:
				raise RuntimeError("servidor não ficou pronto")
			time.sleep(0.5)
		self.out["pronto_s"] = round(time.time() - t0, 1)
		self.t_pronto = time.perf_counter()
		self.ev = Events()
		self.ev.start()
		return self

	def __exit__(self, *exc):
		self.out["mem_fim"] = mem(self.p.pid)
		G._stop(self.p, self.f)
		shutil.rmtree(self.proj, ignore_errors=True)
		shutil.rmtree(self.up, ignore_errors=True)
		print(json.dumps(self.out), flush=True)


def strip_actions(proj, actions):
	"""Remove the log lines of ``actions`` (an old checkout cannot replay them); returns the count per action."""
	fp = os.path.join(proj, "log.jsonl")
	keep, n = [], {}
	with open(fp, encoding="utf-8") as f:
		for line in f:
			try:
				a = json.loads(line).get("action")
			except ValueError:
				a = None
			if a in actions:
				n[a] = n.get(a, 0) + 1
				continue
			keep.append(line)
	with open(fp, "w", encoding="utf-8", newline="") as f:
		f.writelines(keep)
	return n


def open_novo(browser):
	pg = browser.new_page(viewport={"width": 1920, "height": 1080})
	t0 = time.perf_counter()
	pg.goto(G.BASE_URL + "/novo/")
	pg.wait_for_selector("body[data-ready='1']", timeout=300_000)
	pg.wait_for_function("!!document.body.dataset.raster", timeout=300_000)
	return pg, round(time.perf_counter() - t0, 2)


def run_a(a, k, browser):
	with Run(a, f"a{k}") as r:
		out = r.out
		pg, out["abrir_s"] = open_novo(browser)
		out["salto1_ceu"] = jump(pg, 5, 30)
		tb = time.perf_counter()
		G._wait_holes()
		G._wait_ready()
		out["buracos_desde_salto_s"] = round(time.perf_counter() - tb, 1)
		out["sugestoes_desde_pronto_s"] = r.ev.first("holes_changed", r.t_pronto, 5)
		time.sleep(2)
		out["mem_apos_buracos"] = mem(r.p.pid)
		out["salto_frio_relva"] = jump(pg, 44, 40)
		out["salto_frio_vale"] = jump(pg, 33, 12)
		out["srv_frio_ceu_s"] = round(G._get("/api/board.jpg?ppc=100&region=1,23,14,43&v=x")[1], 2)
		out["srv_frio_relva_s"] = round(G._get("/api/board.jpg?ppc=100&region=34,33,47,53&v=x")[1], 2)
		out["mem_apos_saltos"] = mem(r.p.pid)
		for kind, cell in (("perto", out["near"]), ("longe", out["far"])):
			jump(pg, 5, 30)                                   # the view: céu, cached
			pg.evaluate("showTab('pecas')")                   # the view stays (no card target drawn / followed)
			time.sleep(1)
			ver0 = pg.evaluate("S.ver")
			t1 = time.perf_counter()
			G._post("/api/confirm", {"acao": "place", "piece": out["piece"], "cell": cell, "origin": "manual"})
			post_s = time.perf_counter() - t1
			t_post = time.perf_counter()
			w = pg.evaluate(WAIT_SHOWN, str(ver0))
			det_s = round(time.perf_counter() - t1 - post_s, 2)
			out[f"encaixa_{kind}"] = {"cell": cell, "post_s": round(post_s, 2),
									  "detalhe_desde_post_s": det_s, "browser": w,
									  "remendo": G._json("/api/status", 60).get("remendo"),   # None before the patch (2026-11-15)
									  "sugestoes_desde_post_s": r.ev.first("holes_changed", t_post),
									  "suspeitas_desde_post_s": r.ev.first("suspeitas_changed", t_post)}
			G._wait_ready()
			G._wait_holes()
			G._post("/api/confirm", {"acao": "unplace", "piece": out["piece"], "desfaz": True})
			G._wait_ready()
			G._wait_holes()
		pg.close()
	return r.out


def run_b(a, k):
	with Run(a, f"b{k}") as r:
		out = r.out
		near = out["near"]
		G._get("/api/board.jpg?ppc=60&v=x")
		G._get("/api/montar", 600)
		time.sleep(1.0)
		out["a_calcular"] = bool(G._json("/api/holes", 600).get("a_calcular"))
		res, s = G._post(f"/api/cell/{near[0]}/{near[1]}/verificar", {"piece": out["piece"]})
		out["verificar1_s"] = round(s, 2)
		out["verificar1_srv_s"] = res.get("segundos")
		res, s = G._post(f"/api/cell/{near[0]}/{near[1]}/verificar", {"piece": out["piece"], "theta_deg": res.get("theta_deg")})
		out["verificar2_s"] = round(s, 2)
		G._wait_holes()
	return r.out


def run_p(a, k, browser=None, voltas=3):
	"""POST of a «Encaixa» far from the view, timed by phase; ``browser`` = with ``/novo/`` open on the céu."""
	tag = f"{'q' if browser else 'p'}{k}"
	fases = os.path.join(a.work, f"fases_{tag}.jsonl")
	if os.path.exists(fases):
		os.remove(fases)
	with Run(a, tag, fases=fases) as r:
		out = r.out
		G._json("/api/montar", 900)
		G._wait_holes()
		G._wait_ready()
		pg = None
		if browser:
			pg, _ = open_novo(browser)
			jump(pg, 5, 30)
			pg.evaluate("showTab('pecas')")
		time.sleep(3)
		cell = out["far"]
		out["voltas"] = []
		for _ in range(voltas):
			res, s1 = G._post("/api/confirm", {"acao": "place", "piece": out["piece"], "cell": cell, "origin": "manual"})
			err = res.get("error")
			G._wait_ready()
			G._wait_holes()
			time.sleep(1)
			res2, s2 = G._post("/api/confirm", {"acao": "unplace", "piece": out["piece"], "desfaz": True})
			G._wait_ready()
			G._wait_holes()
			time.sleep(1)
			out["voltas"].append({"place_s": round(s1, 2), "place_srv_s": res.get("segundos"), "erro": err,
								  "unplace_s": round(s2, 2), "unplace_erro": res2.get("error")})
		if pg:
			pg.close()
	with open(fases, encoding="utf-8") as f:
		r.out["fases"] = [json.loads(x) for x in f if x.strip()]
	return r.out


def run_r(a, k):
	"""Captures of the céu and relva regions at ppc 100 (``--capturas``), for the before / after comparison."""
	with Run(a, f"r{k}") as r:
		os.makedirs(a.capturas, exist_ok=True)
		for nome, (l0, c0, l1, c1) in (("ceu", CEU_REG), ("relva", RELVA_REG)):
			body, s = G._get(f"/api/board.jpg?ppc=100&region={l0},{c0},{l1},{c1}&v=x")
			fp = os.path.join(a.capturas, f"desempenho_{nome}_{a.sufixo}.jpg")
			with open(fp, "wb") as f:
				f.write(body)
			r.out[nome] = {"ficheiro": fp, "s": round(s, 2), "bytes": len(body)}
	return r.out


def resumo(rows):
	"""The table line of the 5 criteria (min–max over the runs)."""
	def rng(vals):
		v = [x for x in vals if x is not None]
		return None if not v else (round(min(v), 2), round(max(v), 2))
	a = [r for r in rows if r["tag"].startswith("a")]
	b = [r for r in rows if r["tag"].startswith("b")]
	out = {}
	if a:
		out["1_salto1_s"] = rng([r["salto1_ceu"]["s"] for r in a])
		out["2_frio_browser_s"] = rng([r["salto_frio_relva"]["s"] for r in a])
		out["2_frio_http_s"] = rng([r["srv_frio_ceu_s"] for r in a] + [r["srv_frio_relva_s"] for r in a])
		out["3_perto_s"] = rng([r["encaixa_perto"]["browser"]["s"] for r in a])
		out["3_longe_s"] = rng([r["encaixa_longe"]["browser"]["s"] for r in a])
		out["post_s"] = rng([r[f"encaixa_{k}"]["post_s"] for r in a for k in ("perto", "longe")])
		out["5_pico_ws_mb"] = rng([(r.get("mem_fim") or {}).get("peak_ws_mb") for r in a])
		out["sugestoes_desde_pronto_s"] = rng([r.get("sugestoes_desde_pronto_s") for r in a])
		out["sugestoes_desde_post_s"] = rng([r[f"encaixa_{k}"].get("sugestoes_desde_post_s") for r in a for k in ("perto", "longe")])
		out["suspeitas_desde_post_s"] = rng([r[f"encaixa_{k}"].get("suspeitas_desde_post_s") for r in a for k in ("perto", "longe")])
		out["5_pico_privada_mb"] = rng([(r.get("mem_fim") or {}).get("peak_private_mb") for r in a])
	if b:
		out["4_verificar1_s"] = rng([r["verificar1_s"] for r in b])
	return out


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("--base", required=True, help="projeto de partida (copiado de novo em cada corrida)")
	ap.add_argument("--work", default=os.path.join(os.environ.get("PPF_SCRATCH") or os.environ.get("TEMP", "."), "desempenho"))
	ap.add_argument("--out", required=True)
	ap.add_argument("--n", type=int, default=2)
	ap.add_argument("--so", default="ab")
	ap.add_argument("--repo", default=None, help="checkout de onde corre o servidor (bisect)")
	ap.add_argument("--sem-acoes", default="", help="ações a tirar da cópia do log (checkout antigo)")
	ap.add_argument("--capturas", default=os.path.join(ROOT, "docs", "diagnostico", "gui", "capturas"))
	ap.add_argument("--sufixo", default="antes")
	a = ap.parse_args()
	os.makedirs(a.work, exist_ok=True)
	rows = []
	need_browser = any(m in a.so for m in "aq")
	pw = br = None
	if need_browser:
		from playwright.sync_api import sync_playwright
		pw = sync_playwright().start()
		br = pw.chromium.launch()
	try:
		for k in range(1, a.n + 1):
			if "a" in a.so:
				rows.append(run_a(a, k, br))
			if "b" in a.so:
				rows.append(run_b(a, k))
			if "p" in a.so:
				rows.append(run_p(a, k))
			if "q" in a.so:
				rows.append(run_p(a, k, browser=br))
			if "r" in a.so:
				rows.append(run_r(a, k))
	finally:
		if br:
			br.close()
			pw.stop()
	res = {"corridas": rows, "resumo": resumo(rows)}
	with open(a.out, "w", encoding="utf-8") as fh:
		json.dump(res, fh, indent=1, ensure_ascii=False)
	print(json.dumps(res["resumo"], ensure_ascii=False))


if __name__ == "__main__":
	main()
