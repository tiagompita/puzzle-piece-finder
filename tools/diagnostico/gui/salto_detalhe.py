"""Salto da lupa / «localizar» / «Ver no tabuleiro» no browser: tempo até ao raster de detalhe, bloqueio e pedidos.

Uso (o servidor tem de estar a correr sobre uma CÓPIA do projeto; ``--escrita`` grava e desfaz nessa cópia):

	.venv/Scripts/python.exe tools/diagnostico/gui/salto_detalhe.py --url http://127.0.0.1:8799 --ui novo \
		[--vw 1920 --vh 1080 --dpr 1] [--cenarios saltos,cinco,arrasto,escrita] [--out r.json] [--shot pasta]

Chromium (Playwright) com CDP ``Network`` ligado. Cenários:

- ``saltos``: vista inteira → salto para céu (5,30), relva (44,40), vazia (33,30): «frio» = primeira visita da região
  neste processo do servidor, «morno» = a mesma zona deslocada 1 célula, «quente» = voltar à vista exata. Na GUI nova
  o salto é ``showCell(l, c, true)`` (lupa / «localizar», l±5 c±8); na antiga ``zoomCells(l±3, c±5)`` («Ver no
  tabuleiro»). Tempo = do salto até ``body.dataset.detail`` = ``S.detailKey`` (a chave da vista final).
- ``cinco``: 5 saltos seguidos a 400 ms (lupa → lupa → …) para zonas ainda não vistas.
- ``arrasto``: 3 s a arrastar o tabuleiro com pausas de 350 ms (cada pausa passa o debounce de 280 ms).
- ``escrita``: «depois de um Encaixa»: com a vista parada numa zona, ``POST /api/confirm`` (``place`` de uma peça
  solta numa célula vazia, longe ou perto da vista) e tempo até o detalhe voltar na mesma viewBox; depois desfaz
  (``unplace`` com ``desfaz``) e espera que o projeto acalme.

Em cada cenário: long tasks (> 50 ms; conta as > 200 ms), maior intervalo do batimento ``requestAnimationFrame``,
latência de sondas ``fetch`` a ``/api/status`` / ``/api/montar`` / ``/api/cell`` a cada 200 ms (feitas no browser:
contam a fila de ligações), pedidos de detalhe (``/api/board.jpg?…region=``) enviados / mostrados / falhados /
cancelados, pico em voo, e por pedido: espera em fila + «stalled» (CDP), TTFB, duração e bytes. Descodificação: tempo
de ``img.decode()`` do URL final (já na cache HTTP) numa imagem nova.
"""
import argparse
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

INIT_JS = r"""
(() => {
  window.__lt = []; window.__gaps = []; window.__probes = [];
  try { new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__lt.push([e.startTime, e.duration]); })
        .observe({ type: "longtask", buffered: true }); } catch (e) {}
  let last = null;
  const beat = (t) => { if (last !== null) window.__gaps.push([last, t - last]); last = t; requestAnimationFrame(beat); };
  requestAnimationFrame(beat);
  window.__probeOn = (on) => {
    clearInterval(window.__probeTimer);
    if (!on) return;
    const urls = ["/api/status", "/api/montar", "/api/cell/20/20"]; let k = 0;
    window.__probeTimer = setInterval(() => {
      const u = urls[k++ % urls.length], t0 = performance.now();
      fetch(u + (u.includes("?") ? "&" : "?") + "sonda=" + k, { cache: "no-store" }).then((r) => r.arrayBuffer())
        .then(() => window.__probes.push([t0, u, performance.now() - t0])).catch(() => {});
    }, 200);
  };
  window.__waitDetail = (t0, minMs = 0, maxMs = 120000, notVer = null, notKey = null) => new Promise((res) => {
    const chk = () => {
      const dt = performance.now() - t0;
      if (dt >= minMs && (notVer === null || S.ver !== notVer) && (notKey === null || S.detailKey !== notKey)
          && S.detailKey && document.body.dataset.detail === S.detailKey) return res(dt);
      if (dt > maxMs) return res(null);
      setTimeout(chk, 10);
    };
    chk();
  });
  window.__win = (t0, t1) => ({
    longtasks: window.__lt.filter(([s]) => s >= t0 && s <= t1).map(([, d]) => Math.round(d)),
    raf_max_gap: Math.round(Math.max(0, ...window.__gaps.filter(([s]) => s >= t0 && s <= t1).map(([, g]) => g))),
    probes: window.__probes.filter(([s]) => s >= t0 && s <= t1).map(([, u, d]) => [u, Math.round(d)]),
  });
})();
"""


class Net:
	"""CDP Network: pedidos de detalhe e sondas, com tempos de fila / TTFB / duração / bytes."""

	def __init__(self, cdp):
		self.req = {}
		self.inflight = 0
		self.peak = 0
		cdp.on("Network.requestWillBeSent", self._sent)
		cdp.on("Network.responseReceived", self._resp)
		cdp.on("Network.loadingFinished", self._done)
		cdp.on("Network.loadingFailed", self._fail)
		cdp.send("Network.enable")
		cdp.send("Network.setCacheDisabled", {"cacheDisabled": False})

	@staticmethod
	def _kind(url):
		if "/api/board.jpg" in url and "region=" in url:
			return "detalhe"
		if "sonda=" in url:
			return "sonda"
		if "/api/board.jpg" in url:
			return "raster"
		return None

	def _sent(self, e):
		k = self._kind(e["request"]["url"])
		if k is None:
			return
		self.req[e["requestId"]] = {"k": k, "url": e["request"]["url"], "t": e["timestamp"], "wall": time.time()}
		if k == "detalhe":
			self.inflight += 1
			self.peak = max(self.peak, self.inflight)

	def _resp(self, e):
		r = self.req.get(e["requestId"])
		if r is None:
			return
		tm = e["response"].get("timing")
		r["cache"] = bool(e["response"].get("fromDiskCache") or e["response"].get("fromMemoryCache"))
		if tm:
			r["fila_ms"] = round((tm["requestTime"] - r["t"]) * 1000 + tm["sendStart"])
			r["ttfb_ms"] = round(tm["receiveHeadersEnd"] - tm["sendEnd"])

	def _end(self, e, ok):
		r = self.req.get(e["requestId"])
		if r is None or "fim" in r:
			return
		r["fim"] = e["timestamp"]
		r["dur_ms"] = round((e["timestamp"] - r["t"]) * 1000)
		r["ok"] = ok
		r["bytes"] = e.get("encodedDataLength")
		if not ok:
			r["erro"] = e.get("errorText")
			r["cancelado"] = bool(e.get("canceled"))
		if r["k"] == "detalhe":
			self.inflight -= 1

	def _done(self, e):
		self._end(e, True)

	def _fail(self, e):
		self._end(e, False)

	def reset(self):
		self.req = {k: v for k, v in self.req.items() if "fim" not in v}
		self.peak = self.inflight

	@staticmethod
	def _overlap(d):
		"""Maior tempo (ms, relógio do CDP) em que 2 pedidos de detalhe estiveram em voo ao mesmo tempo."""
		ev = sorted([(r["t"], 1) for r in d] + [(r["fim"], -1) for r in d if "fim" in r])
		n, best, since = 0, 0.0, None
		for t, k in ev:
			n += k
			if n >= 2 and since is None:
				since = t
			elif n < 2 and since is not None:
				best, since = max(best, t - since), None
		return round(best * 1000, 1)

	def summary(self):
		d = [r for r in self.req.values() if r["k"] == "detalhe"]
		t00 = min((r["t"] for r in d), default=0.0)
		s = [r for r in self.req.values() if r["k"] == "sonda"]
		fila = [r.get("fila_ms", 0) for r in d + s if "fila_ms" in r]
		return {
			"detalhe_enviados": len(d),
			"detalhe_terminados": sum(1 for r in d if r.get("ok")),
			"detalhe_falhados": sum(1 for r in d if r.get("ok") is False and not r.get("cancelado")),
			"detalhe_cancelados": sum(1 for r in d if r.get("cancelado")),
			"detalhe_por_acabar": sum(1 for r in d if "fim" not in r),
			"pico_em_voo": self.peak,
			"sobreposicao_ms": self._overlap(d),
			"detalhe": [{"url": r["url"].split("/api/board.jpg")[1][:60], "t_ms": round((r["t"] - t00) * 1000) if d else None,
						 "fim_ms": round((r["fim"] - t00) * 1000) if "fim" in r else None, "fila_ms": r.get("fila_ms"), "ttfb_ms": r.get("ttfb_ms"),
						 "dur_ms": r.get("dur_ms"), "kb": round((r.get("bytes") or 0) / 1024), "cache": r.get("cache"),
						 "ok": r.get("ok"), "erro": r.get("erro")} for r in d],
			"fila_max_ms": max(fila) if fila else None,
			"n_fila_mais_100ms": sum(1 for x in fila if x > 100),
		}


def _wait_idle(base, timeout=300):
	"""Espera que o servidor acabe consultas / buracos (``/api/status`` pronto, sem job)."""
	t0 = time.time()
	while time.time() - t0 < timeout:
		try:
			with urllib.request.urlopen(base + "/api/status", timeout=30) as r:
				st = json.loads(r.read())
			if st.get("estado") == "pronto" and not st.get("job"):
				return True
		except Exception:
			pass
		time.sleep(1)
	return False


def _post(base, body):
	rq = urllib.request.Request(base + "/api/confirm", data=json.dumps(body).encode(), method="POST",
								headers={"Content-Type": "application/json"})
	t0 = time.time()
	with urllib.request.urlopen(rq, timeout=300) as r:
		out = json.loads(r.read())
	return out, time.time() - t0


class Run:
	def __init__(self, pg, net, ui):
		self.pg, self.net, self.ui = pg, net, ui

	def jump(self, l, c):
		if self.ui == "novo":
			return self.pg.evaluate(f"(() => {{ const t = performance.now(); showCell({l}, {c}, true); return t; }})()")
		return self.pg.evaluate(f"(() => {{ const t = performance.now(); zoomCells(Math.max(1,{l}-3), Math.max(1,{c}-5), "
								f"Math.min(S.rows,{l}+3), Math.min(S.cols,{c}+5)); return t; }})()")

	def measure(self, label, action, wait=True, extra=None, min_ms=0, not_ver=None, new_key=True):
		"""``action()`` devolve o t0 (performance.now) do primeiro gesto; espera o detalhe da vista final.

		``min_ms``: não aceita o detalhe antes disto (depois de vários gestos, a chave da vista anterior ainda está
		em ``S.detailKey`` até o debounce de 280 ms correr); ``new_key``: a chave final tem de ser diferente da que
		estava em ``S.detailKey`` antes do gesto (falso para a escrita, onde só a versão muda)."""
		self.net.reset()
		nk = json.dumps(self.pg.evaluate("S.detailKey || null")) if new_key else "null"
		self.pg.evaluate("window.__probeOn(true)")
		t0 = action()
		nv = "null" if not_ver is None else json.dumps(not_ver)
		dt = self.pg.evaluate(f"window.__waitDetail({t0}, {min_ms}, 120000, {nv}, {nk})") if wait else None
		self.pg.wait_for_timeout(300)
		t1 = self.pg.evaluate("performance.now()")
		self.pg.evaluate("window.__probeOn(false)")
		self.pg.wait_for_timeout(250)
		w = self.pg.evaluate(f"window.__win({t0}, {t1})")
		key = self.pg.evaluate("S.detailKey")
		dec = self.pg.evaluate("""async () => { const h = document.querySelector('#detail').getAttribute('href');
			if (!h) return null; const i = new Image(); i.src = h; const t = performance.now(); await i.decode();
			return [Math.round(performance.now() - t), i.naturalWidth, i.naturalHeight]; }""")
		pr = [p[1] for p in w["probes"]]
		row = {"cenario": label, "ui": self.ui, "detalhe_s": None if dt is None else round(dt / 1000, 2), "chave": key,
			   "decode_ms": dec[0] if dec else None, "detalhe_px": dec[1:] if dec else None,
			   "longtasks_ms": w["longtasks"], "n_longtasks_200": sum(1 for x in w["longtasks"] if x > 200),
			   "raf_max_gap_ms": w["raf_max_gap"], "sondas_n": len(pr), "sondas_max_ms": max(pr) if pr else None,
			   "sondas_med_ms": sorted(pr)[len(pr) // 2] if pr else None, **self.net.summary(), **(extra or {})}
		print(json.dumps({k: v for k, v in row.items() if k != "detalhe"}, ensure_ascii=False), flush=True)
		return row


ZONAS = {"ceu": (5, 30), "relva": (44, 40), "vazia": (33, 30)}
CINCO = [(12, 8), (38, 58), (22, 50), (46, 12), (8, 44)]


def main(argv=None) -> int:
	ap = argparse.ArgumentParser()
	ap.add_argument("--url", default="http://127.0.0.1:8799")
	ap.add_argument("--ui", choices=("novo", "antiga"), default="novo")
	ap.add_argument("--vw", type=int, default=1920)
	ap.add_argument("--vh", type=int, default=1080)
	ap.add_argument("--dpr", type=float, default=1.0)
	ap.add_argument("--cenarios", default="saltos,cinco,arrasto")
	ap.add_argument("--escrita-peca", help="peça solta para o «Encaixa» do cenário escrita")
	ap.add_argument("--escrita-celulas", default="", help="l,c;l,c;… células vazias: uma por zona e distância (zona:dist:l,c|…)")
	ap.add_argument("--escrita-aba", default="", help="GUI nova: aba antes da escrita (pecas = a vista não segue o cartão)")
	ap.add_argument("--out")
	ap.add_argument("--shot", help="pasta para capturas (uma por zona, já com o detalhe)")
	ap.add_argument("--etiqueta", default="")
	a = ap.parse_args(argv)
	from playwright.sync_api import sync_playwright
	base = a.url.rstrip("/")
	if "arranque" not in a.cenarios:
		_wait_idle(base)
	rows = []
	with sync_playwright() as pw:
		br = pw.chromium.launch()
		ctx = br.new_context(viewport={"width": a.vw, "height": a.vh}, device_scale_factor=a.dpr)
		ctx.add_init_script(INIT_JS)
		pg = ctx.new_page()
		net = Net(ctx.new_cdp_session(pg))
		pg.goto(base + ("/novo/" if a.ui == "novo" else "/"))
		pg.wait_for_function("!!document.body.dataset.raster", timeout=120_000)
		R = Run(pg, net, a.ui)
		cen = a.cenarios.split(",")
		if "arranque" in cen:
			# logo depois de abrir (servidor acabado de arrancar: o 1.º /api/montar calcula os buracos a frio, ≈ 30 s)
			pg.wait_for_timeout(1500)
			rows.append(R.measure("arranque: salto ceu", lambda: R.jump(*ZONAS["ceu"])))
			rows.append(R.measure("arranque: salto relva", lambda: R.jump(*ZONAS["relva"]), min_ms=290))
		pg.wait_for_timeout(1500)
		_wait_idle(base)
		if "saltos" in cen:
			for zn, (l, c) in ZONAS.items():
				pg.evaluate("fitBoard()")
				pg.wait_for_timeout(700)
				rows.append(R.measure(f"salto {zn} frio", lambda: R.jump(l, c)))
				if a.shot:
					os.makedirs(a.shot, exist_ok=True)
					pg.screenshot(path=os.path.join(a.shot, f"{a.ui}_{zn}_{a.vw}{a.etiqueta}.png"))
				rows.append(R.measure(f"salto {zn} morno (+1 col)", lambda: R.jump(l, c + 1), min_ms=290))
				pg.evaluate("fitBoard()")
				pg.wait_for_timeout(700)
				rows.append(R.measure(f"salto {zn} quente", lambda: R.jump(l, c)))
		if "cinco" in cen:
			pg.evaluate("fitBoard()")
			pg.wait_for_timeout(700)

			def cinco():
				t0 = R.jump(*CINCO[0])
				for lc in CINCO[1:]:
					pg.wait_for_timeout(400)
					R.jump(*lc)
				return t0
			rows.append(R.measure("5 saltos seguidos (400 ms)", cinco, min_ms=4 * 400 + 290))
		if "arrasto" in cen:
			R.jump(25, 32)
			pg.wait_for_timeout(200)
			R.pg.evaluate("window.__waitDetail(performance.now(), 0)")
			box = pg.locator("#board").bounding_box()
			cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2

			def arrasto():
				t0 = pg.evaluate("performance.now()")
				pg.mouse.move(cx, cy)
				pg.mouse.down()
				x = cx
				t_end = time.time() + 3.0
				while time.time() < t_end:
					for _ in range(10):
						x -= 12
						pg.mouse.move(x, cy)
						pg.wait_for_timeout(25)
					pg.wait_for_timeout(350)
				pg.mouse.up()
				return t0
			rows.append(R.measure("arrasto 3 s com pausas", arrasto, min_ms=3290))
		if "escrita" in cen and a.escrita_peca:
			for spec in [s for s in a.escrita_celulas.split("|") if s]:
				zn, dist, lc = spec.split(":")
				l, c = (int(x) for x in lc.split(","))
				vl, vc = ZONAS[zn]
				if a.escrita_aba and a.ui == "novo":
					pg.evaluate(f"showTab('{a.escrita_aba}')")
				pg.evaluate("fitBoard()")
				pg.wait_for_timeout(500)
				R.jump(vl, vc)
				pg.evaluate("window.__waitDetail(performance.now(), 300)")
				vb0 = pg.evaluate("JSON.stringify(S.vb)")
				ver0 = pg.evaluate("S.ver")
				_wait_idle(base)
				box = {}

				def escrever():
					t0 = pg.evaluate("performance.now()")
					out, s = _post(base, {"acao": "place", "piece": a.escrita_peca, "cell": [l, c], "origin": "manual"})
					box.update(post_s=round(s, 2), erro=out.get("error"))
					return t0
				row = R.measure(f"escrita {zn} {dist} ({l},{c}){' aba ' + a.escrita_aba if a.escrita_aba else ''}", escrever, extra={},
								not_ver=ver0, new_key=False)
				row.update(box, vb_igual=pg.evaluate("JSON.stringify(S.vb)") == vb0)
				if row["detalhe_s"] is not None and box.get("post_s") is not None:
					row["detalhe_depois_post_s"] = round(row["detalhe_s"] - box["post_s"], 2)
				print(json.dumps({"post": box, "vb_igual": row["vb_igual"], "depois_post_s": row.get("detalhe_depois_post_s")}), flush=True)
				rows.append(row)
				_post(base, {"acao": "unplace", "piece": a.escrita_peca, "desfaz": True})
				pg.wait_for_timeout(1000)
				_wait_idle(base)
		br.close()
	if a.out:
		with open(a.out, "w", encoding="utf-8") as f:
			json.dump({"ui": a.ui, "vw": a.vw, "vh": a.vh, "dpr": a.dpr, "rows": rows}, f, ensure_ascii=False, indent=1)
	return 0


if __name__ == "__main__":
	sys.exit(main())
