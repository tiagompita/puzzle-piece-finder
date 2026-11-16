"""P-a, passo 0 e comparação (a)/(b) no lançador. Protocolo de rodar_novo.py (cópia nova + servidor novo por corrida,
1.º salto, buracos, salto a frio, «Encaixa» perto e longe com a vista no céu e o separador Peças), mais um passo
«cartão»: no separador Montar, clique no botão principal do cartão e tempo até o DOM mostrar o cartão seguinte.

Retenção no browser (não page.route): um embrulho de fetch segura os caminhos da condição desde antes do POST (ou do
clique) até o detalhe seguinte aparecer (data-detail muda) ou ao fim de ``lim`` ms. Forma (b): PPF_PA_B no servidor
(pa_lanca.py). Aqui sem lançador nem retenção: servidor real (``python -m src.server``), para os 10 pares
alternados ``8668365 | novo`` de DETALHE.md §13.10, cada lado com a sua base (a cópia completada pelo seu código).

Uso: ``python pa_pares.py <n_pares> <saida.json> <repo_antigo> <base_antiga> <repo_novo> <base_nova>`` (pasta de trabalho
``$PPF_SCRATCH/pa_pares``); IC com ``pa_ic.py``."""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import perfil_c3 as P  # noqa: E402

D, G = P.D, P.G
S = os.path.dirname(os.path.abspath(__file__))
D.FASES = None
B, GH, M = "/api/board", "/api/ghosts", "/api/montar"
COND = {
	"normal": ([], 20000, None),
	"board": ([B], 20000, None),
	"ghosts": ([GH], 20000, None),
	"montar": ([M], 20000, None),
	"tres": ([B, GH, M], 20000, None),
	"a_sim": ([B, GH], 1000, None),
	"b_sim": ([], 20000, "board_json,ghosts,montar_json"),
	"b2_sim": ([], 20000, "board_json,ghosts"),
	"nada": ([], 20000, None),
}

GATE_JS = r"""
(() => {
  window.__gate = { paths: [], armed: false, p: null, held: 0, why: null };
  window.__arm = (paths, lim) => {
    const g = window.__gate; g.paths = paths; g.held = 0; g.armed = paths.length > 0; g.why = null;
    const d0 = document.body.dataset.detail;
    g.p = new Promise((res) => {
      const mo = new MutationObserver(() => { if (document.body.dataset.detail !== d0) { mo.disconnect(); res('detalhe'); } });
      mo.observe(document.body, { attributes: true, attributeFilter: ['data-detail'] });
      setTimeout(() => { mo.disconnect(); res('limite'); }, lim);
    }).then((why) => { g.armed = false; g.why = why; });
  };
  // armado só quando chega o «board_changed» (o que a forma (a) faria: o detalhe da versão nova está em voo)
  window.__armSSE = (paths, lim) => { window.__gate.pend = paths.length ? { paths, lim } : null; window.__gate.held = 0; window.__gate.why = null; };
  const ES = window.EventSource;
  window.EventSource = function (u, o) {
    const es = new ES(u, o);
    const add = es.addEventListener.bind(es);
    es.addEventListener = function (type, fn, opt) {
      if (type !== 'board_changed') return add(type, fn, opt);
      return add(type, function () { const g = window.__gate; if (g.pend) { const q = g.pend; g.pend = null; window.__arm(q.paths, q.lim); } return fn.apply(this, arguments); }, opt);
    };
    return es;
  };
  window.EventSource.prototype = ES.prototype;
  const F0 = window.fetch;
  window.fetch = function (u, o) {
    const g = window.__gate;
    const path = new URL(String((u && u.url) || u), location.href).pathname;
    if (g.armed && g.paths.includes(path)) { g.held++; const args = arguments; return g.p.then(() => F0.apply(window, args)); }
    return F0.apply(this, arguments);
  };
})();
"""

CARD_JS = r"""
(a) => new Promise((res) => {
  const c0 = document.querySelector('#tab-montar .card[data-piece]'); const p0 = c0 && c0.dataset.piece;
  const b = document.querySelector('#b-encaixa') || document.querySelector('#b-guardar');
  if (!b) return res({ err: 'sem botao', p0 });
  const btn = b.id;
  window.__armSSE(a.paths, a.lim);
  const t0 = performance.now(); b.click();
  const f = () => { const c = document.querySelector('#tab-montar .card[data-piece]');
    if (c && c.dataset.piece !== p0 && !S.pendente) return res({ s: (performance.now() - t0) / 1000, p0, p1: c.dataset.piece, btn, held: window.__gate.held });
    if (performance.now() - t0 > 60000) return res({ s: null, p0, btn });
    requestAnimationFrame(f); }; f(); })
"""


def run(a, k, browser, cond):
	paths, lim, bsrv = COND[cond]
	tl_path = os.path.join(a.work, f"tl_{k}.jsonl")
	if os.path.exists(tl_path):
		os.remove(tl_path)
	if bsrv:
		os.environ["PPF_PA_B"] = bsrv
	else:
		os.environ.pop("PPF_PA_B", None)
	try:
		with D.Run(a, f"{a.tag}_{k}", fases=None) as r:
			out = r.out
			pg = browser.new_page(viewport={"width": 1920, "height": 1080})
			pg.add_init_script(P.INIT_JS)
			pg.add_init_script(GATE_JS)
			t = time.perf_counter()
			pg.goto(G.BASE_URL + "/novo/")
			pg.wait_for_selector("body[data-ready='1']", timeout=300_000)
			pg.wait_for_function("!!document.body.dataset.raster", timeout=300_000)
			out["abrir_s"] = round(time.perf_counter() - t, 2)
			out["salto1_ceu"] = D.jump(pg, 5, 30)
			G._wait_holes()
			G._wait_ready()
			time.sleep(2)
			out["salto_frio_relva"] = D.jump(pg, 44, 40)
			out["srv_frio_ceu_s"] = round(G._get("/api/board.jpg?ppc=100&region=1,23,14,43&v=x")[1], 2)
			out["srv_frio_relva_s"] = round(G._get("/api/board.jpg?ppc=100&region=34,33,47,53&v=x")[1], 2)
			out["mem_apos_saltos"] = D.mem(r.p.pid)
			for kind, cell in (("perto", out["near"]), ("longe", out["far"])):
				D.jump(pg, 5, 30)
				pg.evaluate("showTab('pecas')")
				time.sleep(1)
				ver0 = pg.evaluate("S.ver")
				pg.evaluate("([p, l]) => window.__armSSE(p, l)", [paths, lim])
				ta = time.time()
				t1 = time.perf_counter()
				G._post("/api/confirm", {"acao": "place", "piece": out["piece"], "cell": cell, "origin": "manual"})
				post_s = time.perf_counter() - t1
				tp = time.time()
				pg.evaluate(D.WAIT_SHOWN, str(ver0))
				tshown = time.time()
				g = pg.evaluate("({held: window.__gate.held, why: window.__gate.why})")
				time.sleep(a.cauda)
				tz = time.time()
				out[f"encaixa_{kind}"] = {"cell": cell, "detalhe_desde_post_s": round(tshown - tp, 3), "post_s": round(post_s, 3),
										  "retidos": g["held"], "solto_por": g["why"],
										  "remendo": G._json("/api/status", 60).get("remendo")}
				G._wait_ready()
				G._wait_holes()
				G._post("/api/confirm", {"acao": "unplace", "piece": out["piece"], "desfaz": True})
				G._wait_ready()
				G._wait_holes()
			# cartão: separador Montar, botão principal do cartão, até o cartão seguinte aparecer
			pg.evaluate("showTab('montar')")
			pg.wait_for_selector("#tab-montar .card[data-piece]", timeout=60_000)
			time.sleep(1.5)
			ta = time.time()
			c = pg.evaluate(CARD_JS, {"paths": paths, "lim": min(lim, 5000)})
			time.sleep(3)
			c["solto_por"] = pg.evaluate("window.__gate.why")
			out["cartao"] = c
			G._wait_ready()
			pg.close()
			out["mem"] = D.mem(r.p.pid)
	finally:
		os.environ.pop("PPF_PA_B", None)
	out["cond"] = cond
	return out


def main():
	"""Uso: pa_pares.py <n_pares> <saida.json> <repo_old> <base_old> <repo_new> <base_new>"""
	n, outp, ro, bo, rn, bn = int(sys.argv[1]), sys.argv[2], *sys.argv[3:7]
	from playwright.sync_api import sync_playwright
	pw = sync_playwright().start()
	br = pw.chromium.launch()
	rows = json.load(open(outp, encoding="utf-8"))["corridas"] if os.path.exists(outp) else []
	done = {(r["par"], r["lado"]) for r in rows}
	try:
		for i in range(1, n + 1):
			for lado, repo, base in (("old", ro, bo), ("new", rn, bn)):
				if (i, lado) in done:
					continue
				a = argparse.Namespace(base=os.path.abspath(base), work=os.path.join(os.environ.get("PPF_SCRATCH") or os.environ.get("TEMP", "."), "pa_pares"), cauda=4.0,
									   repo=os.path.abspath(repo), sem_acoes="", tag=lado)
				os.makedirs(a.work, exist_ok=True)
				try:
					row = run(a, i, br, "nada")
				except Exception as e:  # noqa: BLE001
					print("ERRO", i, lado, repr(e), flush=True)
					continue
				row["par"], row["lado"] = i, lado
				rows.append(row)
				with open(outp, "w", encoding="utf-8") as fh:
					json.dump({"corridas": rows}, fh, ensure_ascii=False)
				c = row["cartao"]
				print(f"par {i} {lado}: perto {row['encaixa_perto']['detalhe_desde_post_s']} longe {row['encaixa_longe']['detalhe_desde_post_s']} "
					  f"cartao {c.get('s')} post {row['encaixa_perto']['post_s']} relva {row['salto_frio_relva']['s']} srv {row['srv_frio_relva_s']}", flush=True)
	finally:
		br.close()
		pw.stop()


if __name__ == "__main__":
	main()
