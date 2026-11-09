"""GUI: editor de contorno por traços (slow; docs/gui-design.md §18). Reescrito em 2026-11-07 (o editor
ponto a ponto da primeira versão foi substituído por laço / pincel / borracha + resolução no servidor).

* ``test_contour_strokes_flow`` (1366x768): abre o editor a partir da gaveta da célula, sobreposição de
  janela inteira, pincel «fundo» + laço «peca», desfazer / refazer / cortar a cauda, Shift força «peca»,
  resolução ao vivo (área em mm²), «Afinar vértices», gravar (``overrides.jsonl`` +1 com
  ``metodo: "tracos"``, ``piece_resegmented`` +1, selo «contorno manual»), reabrir carrega os traços, Esc
  com alterações pede confirmação; consola sem erros.
* ``test_contour_overlay_layout`` (``TAB_VIEWPORTS``): sem overflow, janela inteira, canvas com área, barra
  de ferramentas visível, botões >= 40 px; toque real por CDP desenha um traço nos telemóveis.

``PPF_SHOTS`` = pasta das capturas (``contorno_tracos_1366.png``, ``_1920.png``, ``_390.png``), opcional."""

import json
import os

import pytest

pytestmark = pytest.mark.slow
pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("uvicorn")
sync_api = pytest.importorskip("playwright.sync_api")

from src import overrides as OV  # noqa: E402
from src.state import Project  # noqa: E402
from test_gui_guardadas import _serve  # noqa: E402
from test_gui_layout import TAB_VIEWPORTS  # noqa: E402
from test_query import _project  # noqa: E402

SHOTS = os.environ.get("PPF_SHOTS")


def _launch(pw):
    try:
        return pw.chromium.launch()
    except Exception as e:  # chromium not installed
        pytest.skip(f"chromium indisponível: {e}")


def _open_editor(pg, base, cell=(2, 3)):
    pg.goto(base + "/")
    pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
    pg.evaluate(f"openCell({cell[0]}, {cell[1]}, {{zoom: true}})")
    pg.wait_for_selector("#tab-celula [data-contorno]", timeout=30_000)
    pg.click("#tab-celula [data-contorno]")
    pg.wait_for_selector("#ced:not([hidden]) #ced-canvas", timeout=30_000)
    _settled(pg)


def _settled(pg):
    """first (or latest) resolution arrived: S.ced.res set, nothing pending."""
    pg.wait_for_function("S.ced && S.ced.res && !S.ced.busy && !S.ced.inflight", timeout=30_000)


def _corner(pg):
    """point of the current outline (crop px) with the largest x + y, pulled 14 px towards the centroid."""
    return pg.evaluate("""(() => { const D = S.ced.d.denso; let b = D[0]; let cx = 0, cy = 0;
      for (const p of D) { cx += p[0]; cy += p[1]; if (p[0] + p[1] > b[0] + b[1]) b = p; }
      cx /= D.length; cy /= D.length; const dx = cx - b[0], dy = cy - b[1], L = Math.hypot(dx, dy) || 1;
      return [[b[0] + dx / L * 14, b[1] + dy / L * 14], [b[0] + dx / L * 2, b[1] + dy / L * 2], [cx, cy]]; })()""")


def _stroke(pg, pts, steps=3):
    """pointer down at pts[0], move through the rest, up (points in crop px)."""
    pp = [pg.evaluate(f"cedPagePoint({json.dumps(p)})") for p in pts]
    pg.mouse.move(*pp[0])
    pg.mouse.down()
    for q in pp[1:]:
        pg.mouse.move(q[0], q[1], steps=steps)
    pg.mouse.up()


def _set_tool(pg, tool, marca=None):
    pg.click(f"[data-ferr='{tool}']")
    if marca:
        pg.click(f"[data-marca='{marca}']")


def _nlines(fp):
    if not os.path.exists(fp):
        return 0
    with open(fp, encoding="utf-8") as f:
        return len([ln for ln in f if ln.strip()])


def test_contour_strokes_flow(tmp_path):
    from src.query import run_query
    pr, placed, tw, dec = _project(tmp_path)
    run_query(pr, use_image=False)
    gui, server, th, base = _serve(pr.path, str(tmp_path / "uploads"))
    errs, dialogs = [], []
    try:
        with sync_api.sync_playwright() as pw:
            br = _launch(pw)
            pg = br.new_page(viewport={"width": 1366, "height": 768})
            pg.on("console", lambda m: errs.append(m.text) if m.type == "error" and "favicon" not in (m.location or {}).get("url", "") and "favicon" not in m.text else None)
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss() if len(dialogs) == 1 else d.accept()))
            _open_editor(pg, base)
            assert pg.evaluate("S.sel !== null && S.sel[0] === 2 && S.sel[1] === 3")          # opening keeps the selection
            # the overlay is the whole window
            bb = pg.evaluate("(() => { const r = document.querySelector('#ced').getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; })()")
            assert bb[0] == 0 and bb[1] == 0 and abs(bb[2] - 1366) <= 1 and abs(bb[3] - 768) <= 1, bb
            assert pg.evaluate("S.ced.tracos.length") == 0 and pg.evaluate("S.ced.res.valido") is True
            area0 = pg.evaluate("S.ced.res.area_mm2")
            assert area0 > 0
            # brush «fundo» over a corner of the piece
            c_in, c_edge, centre = _corner(pg)
            _set_tool(pg, "pincel", "fundo")
            _stroke(pg, [c_in, c_edge])
            assert pg.evaluate("S.ced.tracos.length") == 1
            t0 = pg.evaluate("S.ced.tracos[0]")
            assert t0["ferramenta"] == "pincel" and t0["marca"] == "fundo" and len(t0["pontos"]) >= 2 and t0["raio_px"] == 8
            _settled(pg)
            assert pg.evaluate("S.ced.res.valido") is True
            assert "mm²" in pg.inner_text("#ced-status")
            # lasso «peca» (5 points, closed on release)
            _set_tool(pg, "laco", "peca")
            cx, cy = centre
            _stroke(pg, [[cx - 20, cy - 20], [cx + 20, cy - 20], [cx + 25, cy], [cx + 20, cy + 20], [cx - 20, cy + 20]])
            assert pg.evaluate("S.ced.tracos.length") == 2 and pg.evaluate("S.ced.tracos[1].marca") == "peca"
            assert pg.evaluate("S.ced.pos") == 2
            _settled(pg)
            # undo / redo, and a new stroke after an undo cuts the tail
            pg.keyboard.press("Control+z")
            assert pg.evaluate("S.ced.pos") == 1 and pg.evaluate("S.ced.tracos.length") == 2
            pg.keyboard.press("Control+y")
            assert pg.evaluate("S.ced.pos") == 2
            pg.keyboard.press("Control+Shift+z")           # Ctrl+Shift+Z is undo+shift = redo: nothing to redo
            assert pg.evaluate("S.ced.pos") == 2
            pg.keyboard.press("Control+z")
            pg.keyboard.press("Control+z")
            assert pg.evaluate("S.ced.pos") == 0
            pg.keyboard.press("Control+Shift+z")
            assert pg.evaluate("S.ced.pos") == 1
            _set_tool(pg, "pincel", "incerto")
            pg.keyboard.down("Shift")                      # Shift forces «peca»
            _stroke(pg, [[cx - 5, cy], [cx + 5, cy]])
            pg.keyboard.up("Shift")
            assert pg.evaluate("S.ced.tracos.length") == 2 and pg.evaluate("S.ced.pos") == 2, "the redo tail must be cut"
            assert pg.evaluate("S.ced.tracos[1].marca") == "peca" and pg.evaluate("S.ced.tracos[1].ferramenta") == "pincel"
            pg.keyboard.press("l")                         # keyboard tools / marks
            assert pg.evaluate("S.ced.tool") == "laco"
            pg.keyboard.press("2")
            assert pg.evaluate("S.ced.marca") == "fundo"
            pg.keyboard.press("p")
            pg.keyboard.press("]")
            assert pg.evaluate("S.ced.raio") > 8
            _settled(pg)
            assert pg.evaluate("S.ced.res.valido") is True
            # optional vertex retouch: handles appear
            pg.click("#ced-vertices")
            assert pg.evaluate("S.ced.retouch && S.ced.vt && S.ced.vt.pts.length") >= 20
            if SHOTS:
                os.makedirs(SHOTS, exist_ok=True)
                pg.screenshot(path=os.path.join(SHOTS, "contorno_tracos_1366.png"))
            pg.click("#ced-vertices")
            assert pg.evaluate("S.ced.retouch") is False
            n_tr = pg.evaluate("S.ced.pos")
            # save
            assert not os.path.exists(OV.overrides_path(pr))
            n_res = len([e for e in Project.open(pr.path).events() if e["action"] == "piece_resegmented"])
            pg.fill("#ced-nota", "sombra no lado de baixo")
            pg.wait_for_function("!document.querySelector('#ced-save').disabled", timeout=10_000)
            pg.click("#ced-save")
            pg.wait_for_selector("#tab-celula.on .chip.manual", timeout=60_000)
            assert pg.evaluate("S.ced") is None and pg.evaluate("document.querySelector('#ced').hidden")
            assert _nlines(OV.overrides_path(pr)) == 1
            with open(OV.overrides_path(pr), encoding="utf-8") as f:
                rec = json.loads(f.readlines()[-1])
            assert rec["metodo"] == "tracos" and len(rec["tracos"]) == n_tr and rec["piece"] == placed
            assert rec["solver"]["nome"] == "grabcut" and rec["nota"] == "sombra no lado de baixo"
            q = Project.open(pr.path)
            res = [e for e in q.events() if e["action"] == "piece_resegmented"]
            assert len(res) == n_res + 1 and res[-1]["motivo"] == "manual" and res[-1]["piece"] == placed
            assert q.piece(placed).flags["manual_override"] is True
            assert q.check_invariants(disk=True) == []
            assert "contorno manual" in pg.inner_text("#tab-celula")
            # reopening loads the strokes; closing without changes needs no confirmation
            pg.click("#tab-celula [data-contorno]")
            pg.wait_for_selector("#ced:not([hidden]) #ced-canvas", timeout=30_000)
            _settled(pg)
            assert pg.evaluate("S.ced.tracos.length") == n_tr and pg.evaluate("S.ced.pos") == n_tr
            assert pg.evaluate("S.ced.res.valido") is True
            pg.keyboard.press("Escape")
            pg.wait_for_selector("#tab-celula.on", timeout=30_000)
            assert dialogs == []
            assert _nlines(OV.overrides_path(pr)) == 1
            # Esc with unsaved changes asks: dismiss keeps the editor, accept leaves without writing
            pg.click("#tab-celula [data-contorno]")
            pg.wait_for_selector("#ced:not([hidden]) #ced-canvas", timeout=30_000)
            _settled(pg)
            c_in, c_edge, centre = _corner(pg)
            _set_tool(pg, "pincel", "fundo")
            _stroke(pg, [c_in, c_edge])
            pg.keyboard.press("Escape")
            assert len(dialogs) == 1 and pg.evaluate("S.ced !== null")
            pg.keyboard.press("Escape")
            pg.wait_for_function("S.ced === null", timeout=10_000)
            assert len(dialogs) == 2 and _nlines(OV.overrides_path(pr)) == 1
            br.close()
    finally:
        server.should_exit = True
        th.join(10)
    assert not errs, errs


def test_contour_convention_index(tmp_path):
    """Convenção do índice (§18): aresta bruta, identidade sem traços, traços «fundo» possivelmente ignorados."""
    from src.query import run_query
    pr, placed, tw, dec = _project(tmp_path)
    run_query(pr, use_image=False)
    gui, server, th, base = _serve(pr.path, str(tmp_path / "uploads"))
    try:
        with sync_api.sync_playwright() as pw:
            br = _launch(pw)
            pg = br.new_page(viewport={"width": 1366, "height": 768})
            pg.on("dialog", lambda d: d.accept())
            _open_editor(pg, base)
            _settled(pg)
            assert pg.evaluate("S.ced.res.identidade === true")
            assert pg.evaluate("S.ced.res.aresta.length") >= 20
            assert pg.evaluate("S.ced.res.convencao === 'indice'")
            assert "igual ao contorno atual" in pg.inner_text("#ced-status")
            c_in, c_edge, centre = _corner(pg)
            _set_tool(pg, "pincel", "fundo")
            _stroke(pg, [c_in, c_edge])
            _settled(pg)
            assert pg.evaluate("Array.isArray(S.ced.res.tracos_ignorados)")
            br.close()
    finally:
        server.should_exit = True
        th.join(10)


@pytest.fixture(scope="module")
def served(tmp_path_factory):
    from src.query import run_query
    tmp = tmp_path_factory.mktemp("ced")
    pr, placed, tw, dec = _project(tmp)
    run_query(pr, use_image=False)
    gui, server, th, base = _serve(pr.path, str(tmp / "uploads"))
    yield base
    server.should_exit = True
    th.join(10)


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as pw:
        br = _launch(pw)
        yield br
        br.close()


@pytest.mark.parametrize("w,h", TAB_VIEWPORTS)
def test_contour_overlay_layout(served, browser, w, h):
    """Editor open: full-window overlay, no horizontal overflow, the canvas has most of the window, the tool
    bar is visible with buttons >= 40 px; a real touch (CDP) draws a stroke on phones."""
    phone = w <= 900
    ctx = browser.new_context(viewport={"width": w, "height": h}, has_touch=phone, is_mobile=phone and w < 500)
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    try:
        _open_editor(pg, served)
        pg.wait_for_timeout(300)
        assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth"), (w, h)
        assert pg.evaluate("document.documentElement.scrollHeight <= innerHeight"), (w, h)
        bb = pg.evaluate("(() => { const r = document.querySelector('#ced').getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; })()")
        assert bb[0] == 0 and bb[1] == 0 and abs(bb[2] - w) <= 1 and abs(bb[3] - h) <= 1, (w, h, bb)
        cv = pg.evaluate("(() => { const r = document.querySelector('#ced-canvas').getBoundingClientRect(); return [r.left, r.top, r.width, r.height, r.right, r.bottom]; })()")
        assert cv[4] <= w + 0.5 and cv[5] <= h + 0.5, (w, h, cv)
        frac = cv[2] * cv[3] / (w * h)
        grid = pg.evaluate("S.ced.mode") == "grid"
        assert grid == (w >= 1200)
        assert frac >= (0.4 if grid else 0.5), (w, h, frac)
        tb = pg.evaluate("(() => { const r = document.querySelector('#ced-tools').getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom, r.height]; })()")
        assert tb[2] <= w + 0.5 and tb[3] <= h + 0.5 and tb[4] > 60, (w, h, tb)
        small = pg.evaluate("""[...document.querySelectorAll('#ced-tools button')].filter(b => b.offsetParent && b.getBoundingClientRect().height < 39.5).map(b => b.textContent)""")
        assert small == [], (w, h, small)
        assert pg.locator("#ced-save").count() == 1 and pg.locator("#ced-close").count() == 1
        if not grid:      # one view at a time: the canvas takes the window next to the bar
            assert pg.evaluate("document.querySelectorAll('.ced-vw.show').length") == 1
        if phone:         # real touch (CDP -> pointer events of type touch): one finger draws
            c_in, c_edge, centre = _corner(pg)
            pts = [pg.evaluate(f"cedPagePoint({json.dumps(p)})") for p in (c_in, c_edge)]
            cdp = ctx.new_cdp_session(pg)
            (x0, y0), (x1, y1) = pts
            for typ, f in (("touchStart", 0), ("touchMove", 0.4), ("touchMove", 0.8), ("touchEnd", 1.0)):
                tp = [] if typ == "touchEnd" else [{"x": x0 + (x1 - x0) * f, "y": y0 + (y1 - y0) * f, "id": 1}]
                cdp.send("Input.dispatchTouchEvent", {"type": typ, "touchPoints": tp})
            pg.wait_for_timeout(150)
            assert pg.evaluate("S.ced.tracos.length") == 1
            assert pg.evaluate("S.ced.tracos[0].pontos.length") >= 2
            _settled(pg)
        elif SHOTS and w in (1366, 1920):
            c_in, c_edge, centre = _corner(pg)
            _set_tool(pg, "pincel", "fundo")
            _stroke(pg, [c_in, c_edge])
            _settled(pg)
        if SHOTS and w in (1366, 1920, 390):
            os.makedirs(SHOTS, exist_ok=True)
            pg.screenshot(path=os.path.join(SHOTS, f"contorno_tracos_{w}.png"))
    finally:
        ctx.close()
    assert not errs, errs

