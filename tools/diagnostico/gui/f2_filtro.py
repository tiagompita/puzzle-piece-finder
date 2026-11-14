"""F2 (9): o ajuste de cor (filtro CSS ``brightness`` + ``saturate``) no tabuleiro atrasa o arrastar e o zoom?

	.venv/Scripts/python.exe tools/diagnostico/gui/f2_filtro.py --url http://127.0.0.1:PORT --out <json> [--voltas 3]

Chromium (Playwright) na GUI nova, servidor a correr sobre uma CÓPIA do projeto. Para cada tamanho (1366 × 768 dpr 1 e
390 × 844 dpr 3) e cada volta, alterna filtro LIGADO (o valor inicial, brilho 0,92) e DESLIGADO (sem a classe
``cor-tabuleiro``), e mede durante (a) 3 s de arrastar o tabuleiro aproximado (60 movimentos de rato a 50 ms) e (b) 12
voltas da roda a 120 ms: intervalos do ``requestAnimationFrame`` (média, p95, máximo), long tasks > 50 ms, e o tempo de
cada movimento até ao frame seguinte. O detalhe não é pedido durante o gesto (espera de 280 ms), por isso o que se
mede é a imagem do fundo e o SVG.

O rAF do Chromium headless fica preso a 16,7 ms (não vê o custo de rasterizar no compositor), por isso cada gesto é
também gravado num trace (``devtools.timeline`` + ``frame``): soma e máximo das tarefas de pintura/rasterização
(``Paint``, ``RasterTask``, ``GPUTask``, ``DrawFrame``…) e o nº de frames perdidos (``DroppedFrame``).
"""
RASTER = ("Paint", "RasterTask", "PaintImage", "GPUTask", "Layerize", "UpdateLayerTree", "CompositeLayers",
		  "DecodeImage", "ImageDecodeTask", "Rasterize")


def _trace_stats(path):
	with open(path, encoding="utf-8") as fh:
		evs = json.load(fh)
	evs = evs.get("traceEvents", evs) if isinstance(evs, dict) else evs
	dur = {}
	dropped = 0
	frames = 0
	for e in evs:
		n = e.get("name")
		if n == "DroppedFrame":
			dropped += 1
		elif n in ("DrawFrame", "BeginFrame"):
			frames += 1
		if n in RASTER and e.get("ph") == "X":
			d = dur.setdefault(n, [0.0, 0.0])
			d[0] += e.get("dur", 0) / 1000.0
			d[1] = max(d[1], e.get("dur", 0) / 1000.0)
	return {"pintura_ms": round(sum(v[0] for v in dur.values()), 1), "pintura_max_ms": round(max([v[1] for v in dur.values()] or [0]), 1),
			"por_tipo_ms": {k: round(v[0], 1) for k, v in sorted(dur.items())}, "frames": frames, "frames_perdidos": dropped}
import argparse
import json
import os
import statistics as st
import tempfile

JS = r"""
(() => {
  window.__gaps = []; window.__lt = [];
  try { new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__lt.push(e.duration); }).observe({ type: "longtask", buffered: false }); } catch (e) {}
  let last = null;
  const beat = (t) => { if (last !== null && window.__on) window.__gaps.push(t - last); last = t; requestAnimationFrame(beat); };
  requestAnimationFrame(beat);
})();
"""


def _stats(v):
	if not v:
		return {"n": 0}
	s = sorted(v)
	return {"n": len(v), "media_ms": round(st.mean(v), 2), "p95_ms": round(s[int(0.95 * (len(s) - 1))], 2), "max_ms": round(s[-1], 2)}


def _gesture(pg, kind, w, h, br):
	tp = os.path.join(tempfile.gettempdir(), f"f2_filtro_{os.getpid()}.json")
	br.start_tracing(page=pg, path=tp, categories=["devtools.timeline", "disabled-by-default-devtools.timeline.frame",
												  "cc", "viz", "benchmark"])
	pg.evaluate("window.__gaps = []; window.__lt = []; window.__on = true;")
	cx, cy = w * (0.35 if w > 600 else 0.5), h * (0.45 if w > 600 else 0.2)
	if kind == "arrastar":
		pg.mouse.move(cx, cy)
		pg.mouse.down()
		for k in range(60):
			pg.mouse.move(cx + 120 * ((k % 20) / 20.0 - 0.5), cy + 60 * (((k // 20) % 2) - 0.5))
			pg.wait_for_timeout(50)
		pg.mouse.up()
	else:
		pg.mouse.move(cx, cy)
		for k in range(12):
			pg.mouse.wheel(0, -120 if k < 6 else 120)
			pg.wait_for_timeout(120)
	pg.wait_for_timeout(200)
	pg.evaluate("window.__on = false;")
	br.stop_tracing()
	tr = _trace_stats(tp)
	os.remove(tp)
	return {"raf": _stats(pg.evaluate("window.__gaps")), "longtasks": [round(x) for x in pg.evaluate("window.__lt")], "trace": tr}


def main(argv=None) -> int:
	ap = argparse.ArgumentParser()
	ap.add_argument("--url", required=True)
	ap.add_argument("--out", required=True)
	ap.add_argument("--voltas", type=int, default=3)
	a = ap.parse_args(argv)
	from playwright.sync_api import sync_playwright
	rows = []
	with sync_playwright() as pw:
		br = pw.chromium.launch()
		for (w, h, dpr) in ((1366, 768, 1), (390, 844, 3)):
			ctx = br.new_context(viewport={"width": w, "height": h}, device_scale_factor=dpr)
			ctx.add_init_script(JS)
			pg = ctx.new_page()
			pg.goto(a.url + "/novo/")
			pg.wait_for_selector("body[data-ready='1']", timeout=300_000)
			pg.evaluate("zoomCells(10, 18, 24, 42, 0.02)")
			pg.wait_for_timeout(4000)
			for v in range(a.voltas):
				for on in ((True, False) if v % 2 == 0 else (False, True)):
					pg.evaluate(f"document.body.classList.toggle('cor-tabuleiro', {str(on).lower()})")
					filt = pg.evaluate("getComputedStyle(document.querySelector('#raster')).filter")
					for kind in ("arrastar", "roda"):
						r = _gesture(pg, kind, w, h, br)
						row = {"tamanho": f"{w}x{h}@{dpr}", "volta": v + 1, "filtro": on, "filtro_css": filt, "gesto": kind, **r}
						rows.append(row)
						print(json.dumps(row), flush=True)
						pg.wait_for_timeout(600)
			ctx.close()
		br.close()
	summ = {}
	for r in rows:
		k = (r["tamanho"], r["gesto"], r["filtro"])
		summ.setdefault(k, []).append(r)
	out = {"linhas": rows, "resumo": [{"tamanho": k[0], "gesto": k[1], "filtro": k[2],
										"raf_media_ms": round(st.mean(x["raf"]["media_ms"] for x in v), 2),
										"raf_p95_ms": round(st.mean(x["raf"]["p95_ms"] for x in v), 2),
										"raf_max_ms": max(x["raf"]["max_ms"] for x in v),
										"pintura_ms": [x["trace"]["pintura_ms"] for x in v],
										"pintura_max_ms": max(x["trace"]["pintura_max_ms"] for x in v),
										"frames": [x["trace"]["frames"] for x in v],
										"frames_perdidos": [x["trace"]["frames_perdidos"] for x in v],
										"longtasks": sum(len(x["longtasks"]) for x in v)} for k, v in sorted(summ.items())]}
	with open(a.out, "w", encoding="utf-8") as fh:
		json.dump(out, fh, ensure_ascii=False, indent=1)
	for s in out["resumo"]:
		print(s)
	return 0


if __name__ == "__main__":
	import sys
	sys.exit(main())
