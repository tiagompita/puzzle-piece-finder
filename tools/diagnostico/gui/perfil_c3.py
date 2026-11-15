"""Perfil do critério 3 (detalhe depois de um «Encaixa»), sem otimizar: a linha do tempo de cada «Encaixa» perto /
longe, do servidor (``linha_tempo.py``, todos os fios) e do browser (SSE recebidos, ``fetch``, temporizadores e funções
do Montar, recursos, momento em que o detalhe aparece), na mesma base de tempo (relógio do sistema).

Protocolo = ``desempenho.py --so a`` (cópia nova e servidor novo por corrida; abrir ``/novo/``, 1.º salto ao céu, esperar
os buracos, saltos frios relva/vale e regiões frias por HTTP, depois «Encaixa» perto e longe com a vista fixa no céu e o
separador Peças, cada um desfeito com ``unplace`` + ``desfaz``). Depois de o detalhe aparecer espera ``--cauda`` s para
ver o que ainda corre (ranking, suspeitas, pré-aquecimento).

Uso: ``python tools/diagnostico/gui/perfil_c3.py --base <projeto> --out <json> [--n 5]``."""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import desempenho as D  # noqa: E402

G = D.G
D.FASES = os.path.join(HERE, "linha_tempo.py")

INIT_JS = r"""
(() => {
  window.__tl = [];
  const T = () => performance.timeOrigin + performance.now();
  const P = (o) => { o.t = T(); window.__tl.push(o); };
  try { performance.setResourceTimingBufferSize(20000); } catch (e) {}
  const ES = window.EventSource;
  window.EventSource = function (u, o) {
    const es = new ES(u, o);
    const add = es.addEventListener.bind(es);
    es.addEventListener = function (type, fn, opt) {
      return add(type, function () { if (type !== 'atividade' && type !== 'holes_progress') P({ ev: 'sse recebido', name: type }); return fn.apply(this, arguments); }, opt);
    };
    return es;
  };
  window.EventSource.prototype = ES.prototype;
  const F = window.fetch;
  window.fetch = function (u, o) {
    const url = String((u && u.url) || u);
    P({ ev: 'fetch b', url });
    return F.apply(this, arguments).then((r) => { P({ ev: 'fetch h', url, st: r.status }); return r; },
      (e) => { P({ ev: 'fetch err', url, err: String(e && e.name) }); throw e; });
  };
  new MutationObserver((ms) => { for (const m of ms) if (m.attributeName === 'data-detail' || m.attributeName === 'data-raster')
    P({ ev: m.attributeName, v: document.body.getAttribute(m.attributeName) }); })
    .observe(document.documentElement, { attributes: true, subtree: true, attributeFilter: ['data-detail', 'data-raster'] });
})();
"""

WRAP_JS = r"""
() => {
  const T = () => performance.timeOrigin + performance.now();
  const P = (o) => { o.t = T(); window.__tl.push(o); };
  for (const n of ['scheduleReload', 'scheduleDetail', 'loadDetail', 'loadBoard', 'loadMontar', 'drawRaster', 'setView', 'refreshPainel']) {
    const f = window[n];
    if (typeof f !== 'function' || f.__w) continue;
    const w = function () {
      P({ ev: n + ' b' });
      let r;
      try { r = f.apply(this, arguments); } catch (e) { P({ ev: n + ' e', err: String(e) }); throw e; }
      if (r && typeof r.then === 'function') r.then(() => P({ ev: n + ' e' }), (e) => P({ ev: n + ' e', err: String(e) }));
      else P({ ev: n + ' e' });
      return r;
    };
    w.__w = true;
    window[n] = w;
  }
  return Object.keys(window).filter((k) => window[k] && window[k].__w);
}
"""

COLLECT_JS = r"""
(t0) => ({ tl: window.__tl.filter((e) => e.t >= t0),
  res: performance.getEntriesByType('resource').filter((e) => performance.timeOrigin + e.startTime >= t0)
    .map((e) => ({ url: e.name, b: performance.timeOrigin + e.startTime, req: performance.timeOrigin + e.requestStart,
                   resp0: performance.timeOrigin + e.responseStart, e: performance.timeOrigin + e.responseEnd, kind: e.initiatorType })) })
"""


def server_lines(fp, t0, t1):
	out = []
	with open(fp, encoding="utf-8") as f:
		for line in f:
			try:
				r = json.loads(line)
			except ValueError:
				continue
			t = r.get("t0", r["t"])
			if t0 <= r["t"] <= t1 or t0 <= t <= t1:
				out.append(r)
	return out


def run(a, k, browser):
	tl_path = os.path.join(a.work, f"tl_c3_{k}.jsonl")
	if os.path.exists(tl_path):
		os.remove(tl_path)
	big = {}
	with D.Run(a, f"c3_{k}", fases=tl_path) as r:
		out = r.out
		pg = browser.new_page(viewport={"width": 1920, "height": 1080})
		pg.add_init_script(INIT_JS)
		t = time.perf_counter()
		pg.goto(G.BASE_URL + "/novo/")
		pg.wait_for_selector("body[data-ready='1']", timeout=300_000)
		pg.wait_for_function("!!document.body.dataset.raster", timeout=300_000)
		out["abrir_s"] = round(time.perf_counter() - t, 2)
		out["embrulhadas"] = pg.evaluate(WRAP_JS)
		out["salto1_ceu"] = D.jump(pg, 5, 30)
		G._wait_holes()
		G._wait_ready()
		time.sleep(2)
		out["salto_frio_relva"] = D.jump(pg, 44, 40)
		out["salto_frio_vale"] = D.jump(pg, 33, 12)
		G._get("/api/board.jpg?ppc=100&region=1,23,14,43&v=x")
		G._get("/api/board.jpg?ppc=100&region=34,33,47,53&v=x")
		for kind, cell in (("perto", out["near"]), ("longe", out["far"])):
			D.jump(pg, 5, 30)
			pg.evaluate("showTab('pecas')")
			time.sleep(1)
			ver0 = pg.evaluate("S.ver")
			ta = time.time()
			t1 = time.perf_counter()
			G._post("/api/confirm", {"acao": "place", "piece": out["piece"], "cell": cell, "origin": "manual"})
			post_s = time.perf_counter() - t1
			tp = time.time()
			w = pg.evaluate(D.WAIT_SHOWN, str(ver0))
			tshown = time.time()
			time.sleep(a.cauda)
			tz = time.time()
			br = pg.evaluate(COLLECT_JS, (ta - 0.5) * 1000)
			out[f"encaixa_{kind}"] = {"cell": cell, "detalhe_desde_post_s": round(tshown - tp, 3), "post_s": round(post_s, 3)}
			big[f"encaixa_{kind}"] = {"cell": cell, "t_post_b": ta, "t_post_e": tp, "t_shown": tshown,
									  "post_s": round(post_s, 3), "detalhe_desde_post_s": round(tshown - tp, 3),
									  "browser_s": w["s"], "key": w["key"],
									  "browser": br, "servidor": server_lines(tl_path, ta - 0.5, tz)}
			G._wait_ready()
			G._wait_holes()
			G._post("/api/confirm", {"acao": "unplace", "piece": out["piece"], "desfaz": True})
			G._wait_ready()
			G._wait_holes()
		pg.close()
		out["mem"] = D.mem(r.p.pid)
	return {**out, **big}


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("--base", required=True)
	ap.add_argument("--work", default=os.path.join(os.environ.get("PPF_SCRATCH") or os.environ.get("TEMP", "."), "perfil_c3"))
	ap.add_argument("--out", required=True)
	ap.add_argument("--n", type=int, default=5)
	ap.add_argument("--cauda", type=float, default=8.0, help="segundos a registar depois de o detalhe aparecer")
	a = ap.parse_args()
	a.repo, a.sem_acoes = None, ""
	os.makedirs(a.work, exist_ok=True)
	from playwright.sync_api import sync_playwright
	pw = sync_playwright().start()
	br = pw.chromium.launch()
	rows = []
	try:
		for k in range(1, a.n + 1):
			rows.append(run(a, k, br))
			with open(a.out, "w", encoding="utf-8") as fh:
				json.dump({"corridas": rows}, fh, ensure_ascii=False)
			e = rows[-1]["encaixa_longe"]
			print(f"corrida {k}: longe {e['detalhe_desde_post_s']} s, perto {rows[-1]['encaixa_perto']['detalhe_desde_post_s']} s", flush=True)
	finally:
		br.close()
		pw.stop()


if __name__ == "__main__":
	main()
