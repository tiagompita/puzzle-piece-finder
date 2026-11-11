"""board.js carregado SÓ com a interface declarada no seu cabeçalho (F1b, 2026-11-11).

A página de teste tem core.js, um ``S`` de stub e board.js, mais os elementos do tabuleiro; nenhum outro ficheiro da GUI.
O ``S`` é um ``Proxy`` que regista qualquer campo lido ou escrito fora da interface; um nome global da GUI antiga usado
por board.js dá ``ReferenceError`` (apanhado como ``pageerror``). Também se verifica, sem browser, que board.js não
menciona nenhum nome de topo das cascas e dos outros módulos da GUI (app.js, pose.js, …).
"""

import io
import json
import os
import re

import pytest

pytestmark = pytest.mark.slow
sync_api = pytest.importorskip("playwright.sync_api")

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "web")
HOST = "http://board.test"

# o cabeçalho de board.js: dados + 3 estados + função + gancho, e os campos que o próprio board.js escreve
INTERFACE = {"board", "showGrid", "showGhost", "pose", "onPoseWheel", "onBoardTap"}
OWNED = {"rows", "cols", "hr", "ppc", "ver", "rotGemea", "vb", "detailKey"}

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<style>html,body{margin:0;height:100%} #board{width:800px;height:600px;display:block}</style></head><body>
<svg id="board" xmlns="http://www.w3.org/2000/svg">
  <rect id="board-bg" x="0" y="0" width="1" height="1"></rect>
  <image id="raster" x="0" y="0" preserveAspectRatio="none"></image>
  <image id="detail" x="0" y="0" preserveAspectRatio="none" visibility="hidden"></image>
  <g id="lyr-fantasma"></g><g id="lyr-grelha"></g>
</svg>
<button id="z-in">+</button><button id="z-out">-</button><button id="z-fit">fit</button>
<script src="core.js"></script>
<script>
  const ALLOWED = new Set(__ALLOWED__);
  window.violations = []; window.taps = []; window.wheels = 0;
  const S = new Proxy({
    board: { rows: 47, cols: 64, hr: 0.97, board_ppc: 20, versao: 7, rotacao_gemea_deg: 180,
             legend: [{ id: "grelha", classe: "b-grelha" }] },
    showGrid: true, showGhost: true, pose: null,
    onPoseWheel: () => { window.wheels += 1; },
    onBoardTap: (l, c) => { window.taps.push([l, c]); },
    vb: { x: 0, y: 0, w: 64, h: 47 },
  }, {
    get(t, k) { if (typeof k === "string" && !ALLOWED.has(k)) window.violations.push("ler " + k); return t[k]; },
    set(t, k, v) { if (!ALLOWED.has(k)) window.violations.push("escrever " + k); t[k] = v; return true; },
    has(t, k) { if (!ALLOWED.has(k)) window.violations.push("has " + String(k)); return k in t; },
  });
</script>
<script src="board.js"></script>
</body></html>"""


def _jpeg() -> bytes:
	from PIL import Image
	b = io.BytesIO()
	Image.new("RGB", (8, 8), (90, 120, 160)).save(b, "JPEG")
	return b.getvalue()


def _top_level_names(js: str) -> set:
	pat = re.compile(r"^(?:async\s+)?(?:function\s+([A-Za-z_$][\w$]*)|(?:const|let|var)\s+([A-Za-z_$][\w$]*))", re.M)
	return {a or b for a, b in pat.findall(js)}


def _strip_comments(js: str) -> str:
	js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
	return re.sub(r"//[^\n]*", "", js)


def test_board_js_names_only_core_and_itself():
	"""Nenhum nome de topo de outro ficheiro da GUI (exceto core.js) aparece no código de board.js."""
	rd = lambda n: open(os.path.join(WEB, n), encoding="utf-8").read()  # noqa: E731
	body = _strip_comments(rd("board.js"))
	own = _top_level_names(body) | _top_level_names(rd("core.js"))
	others = set()
	for n in sorted(os.listdir(WEB)):
		if n.endswith(".js") and n not in ("board.js", "core.js"):
			others |= _top_level_names(rd(n))
	used = set(re.findall(r"(?<![\w$.])([A-Za-z_$][\w$]*)\s*\(", body)) | set(re.findall(r"(?<![\w$.])([A-Za-z_$][\w$]*)\b", body))
	leak = sorted((others - own - {"S"}) & used)
	assert not leak, f"board.js usa nomes de fora da interface: {leak}"


@pytest.fixture(scope="module")
def browser():
	with sync_api.sync_playwright() as pw:
		try:
			br = pw.chromium.launch()
		except Exception as e:  # chromium not installed
			pytest.skip(f"chromium indisponível: {e}")
		yield br
		br.close()


def test_board_js_runs_with_only_the_declared_interface(browser):
	ctx = browser.new_context(viewport={"width": 900, "height": 700}, device_scale_factor=1)
	pg = ctx.new_page()
	errors = []
	pg.on("pageerror", lambda e: errors.append(str(e)))
	jpg = _jpeg()
	html = PAGE.replace("__ALLOWED__", json.dumps(sorted(INTERFACE | OWNED)))
	asked = []

	def route(r):
		url = r.request.url
		path = url[len(HOST):].split("?")[0]
		if path == "/":
			return r.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
		if path in ("/core.js", "/board.js"):
			with open(os.path.join(WEB, path[1:]), encoding="utf-8") as f:
				return r.fulfill(status=200, content_type="text/javascript; charset=utf-8", body=f.read())
		if path == "/api/board.jpg":
			asked.append(url)
			return r.fulfill(status=200, content_type="image/jpeg", body=jpg)
		return r.fulfill(status=404, body="fora da interface: " + path)

	pg.route(HOST + "/**", route)
	pg.goto(HOST + "/")
	pg.evaluate("drawRaster(); drawGrid(); initPointer(); fitBoard();")
	pg.wait_for_function("document.body.dataset.raster === '7'", timeout=10_000)
	assert pg.evaluate("document.querySelector('#lyr-grelha path').getAttribute('class')") == "b-grelha"
	assert pg.evaluate("S.rows") == 47 and pg.evaluate("S.cols") == 64
	box = pg.evaluate("(() => { const r = document.querySelector('#board').getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; })()")
	cx, cy = box[0] + box[2] * 0.5, box[1] + box[3] * 0.5
	# toque sem arrastar -> gancho com (linha, coluna)
	pg.mouse.click(cx, cy)
	assert pg.evaluate("window.taps.length") == 1
	l, c = pg.evaluate("window.taps[0]")
	assert 1 <= l <= 47 and 1 <= c <= 64
	# roda = zoom; muito perto -> raster de detalhe
	w0 = pg.evaluate("S.vb.w")
	pg.mouse.move(cx, cy)
	for _ in range(8):
		pg.mouse.wheel(0, -400)
		pg.wait_for_timeout(40)
	assert pg.evaluate("S.vb.w") < w0
	pg.wait_for_function("!!document.body.dataset.detail", timeout=10_000)
	assert any("region=" in u for u in asked)
	# arrastar desloca, não toca
	x0 = pg.evaluate("S.vb.x")
	pg.mouse.move(cx, cy); pg.mouse.down(); pg.mouse.move(cx - 80, cy - 40, steps=5); pg.mouse.up()
	assert pg.evaluate("S.vb.x") != x0 and pg.evaluate("window.taps.length") == 1
	# estados: grelha / fantasmas desligados escondem as camadas
	pg.evaluate("S.showGrid = false; S.showGhost = false; setView(S.vb)")
	assert pg.evaluate("document.querySelector('#lyr-grelha').classList.contains('off')")
	assert pg.evaluate("document.querySelector('#lyr-fantasma').classList.contains('off')")
	# pose ativa: Alt+roda vai para a função da casca, o toque não abre célula
	pg.evaluate("S.pose = {}")
	w1 = pg.evaluate("S.vb.w")
	pg.keyboard.down("Alt"); pg.mouse.wheel(0, -200); pg.keyboard.up("Alt")
	pg.wait_for_timeout(100)
	assert pg.evaluate("window.wheels") == 1 and pg.evaluate("S.vb.w") == w1
	pg.mouse.click(cx, cy)
	assert pg.evaluate("window.taps.length") == 1
	# sem a função opcional (casca nova sem editor de pose): Alt+roda não rebenta
	pg.evaluate("S.onPoseWheel = null")
	pg.keyboard.down("Alt"); pg.mouse.wheel(0, -200); pg.keyboard.up("Alt")
	pg.evaluate("S.pose = null")
	# botões e redimensionar
	pg.click("#z-in"); pg.click("#z-out"); pg.click("#z-fit")
	pg.evaluate("zoomCells(3, 4, 6, 9); window.dispatchEvent(new Event('resize'))")
	pg.mouse.dblclick(cx, cy)
	pg.wait_for_timeout(400)
	assert not errors, errors
	assert pg.evaluate("window.violations") == []
	ctx.close()
