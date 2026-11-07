"""GUI: editor de contorno (slow; docs/gui-design.md §18). Opens the editor from the cell drawer of the
placed piece of the synthetic project, drags a vertex, Ctrl+Z, drags again, previews, saves:
``overrides.jsonl`` +1 line, ``log.jsonl`` +1 ``piece_resegmented`` (motivo manual), the drawer shows
«contorno manual». Layout: no overflow with the editor open over the ``TAB_VIEWPORTS`` matrix; no
console errors. ``PPF_SHOTS`` = folder for screenshots (1366x768 and 360x640), optional."""

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
    pg.wait_for_selector("#tab-contorno.on #ced-canvas", timeout=30_000)
    pg.wait_for_function("S.ced && S.ced.view && document.querySelector('#ced-status').textContent.includes('vértices')",
                         timeout=15_000)


def _vertex_page_xy(pg, k):
    return pg.evaluate(f"""(() => {{ const r = document.querySelector('#ced-canvas').getBoundingClientRect();
      const [x, y] = cedToScreen(S.ced.pts[{k}]); return [r.left + x, r.top + y]; }})()""")


def _drag(pg, k, dx, dy=0):
    x, y = _vertex_page_xy(pg, k)
    pg.mouse.move(x, y)
    pg.mouse.down()
    pg.mouse.move(x + dx / 2, y + dy / 2, steps=3)
    pg.mouse.move(x + dx, y + dy, steps=3)
    pg.mouse.up()


def _nlines(fp):
    if not os.path.exists(fp):
        return 0
    with open(fp, encoding="utf-8") as f:
        return len([ln for ln in f if ln.strip()])


def test_contour_editor_flow(tmp_path):
    from src.query import run_query
    pr, placed, tw, dec = _project(tmp_path)
    run_query(pr, use_image=False)
    gui, server, th, base = _serve(pr.path, str(tmp_path / "uploads"))
    errs = []
    try:
        with sync_api.sync_playwright() as pw:
            br = _launch(pw)
            pg = br.new_page(viewport={"width": 1366, "height": 768})
            pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
            pg.on("pageerror", lambda e: errs.append(str(e)))
            _open_editor(pg, base)
            n0 = pg.evaluate("S.ced.pts.length")
            assert n0 >= 20
            assert pg.evaluate("S.sel !== null && S.sel[0] === 2 && S.sel[1] === 3")      # opening keeps the selection
            k = pg.evaluate("S.ced.pts.reduce((b, p, i, a) => p[0] > a[b][0] ? i : b, 0)")   # rightmost vertex
            p0 = pg.evaluate(f"S.ced.pts[{k}].slice()")
            pg.evaluate(f"(() => {{ const [x, y] = cedToScreen(S.ced.pts[{k}]); cedZoom(2.5, x, y); }})()")   # vertices ~30 px apart
            _drag(pg, k, 24)
            p1 = pg.evaluate(f"S.ced.pts[{k}].slice()")
            assert p1[0] > p0[0] + 3 and abs(p1[1] - p0[1]) < 1.5, (p0, p1)
            assert pg.evaluate("S.ced.undo.length") == 1 and pg.evaluate("S.ced.pts.length") == n0
            pg.keyboard.press("Control+z")
            assert pg.evaluate(f"S.ced.pts[{k}]") == p0 and pg.evaluate("S.ced.undo.length") == 0
            # click on an edge adds a vertex; Delete removes it
            mid = pg.evaluate(f"""(() => {{ const r = document.querySelector('#ced-canvas').getBoundingClientRect();
              const a = cedToScreen(S.ced.pts[{k}]), b = cedToScreen(S.ced.pts[({k} + 1) % S.ced.pts.length]);
              return [r.left + (a[0] + b[0]) / 2, r.top + (a[1] + b[1]) / 2]; }})()""")
            pg.mouse.click(mid[0], mid[1])
            assert pg.evaluate("S.ced.pts.length") == n0 + 1 and pg.evaluate("S.ced.sel") == k + 1
            pg.keyboard.press("Delete")
            assert pg.evaluate("S.ced.pts.length") == n0
            _drag(pg, k, 24)
            assert pg.evaluate(f"S.ced.pts[{k}][0]") > p0[0] + 3
            if SHOTS:
                os.makedirs(SHOTS, exist_ok=True)
                pg.screenshot(path=os.path.join(SHOTS, "contorno_1366x768_editor.png"))
            pg.click("#ced-preview")
            pg.wait_for_selector("#ced-prev img", timeout=15_000)
            pg.wait_for_function("document.querySelector('#ced-prev img').naturalWidth > 0", timeout=15_000)
            assert not os.path.exists(OV.overrides_path(pr))
            n_ov = _nlines(OV.overrides_path(pr))
            n_res = len([e for e in Project.open(pr.path).events() if e["action"] == "piece_resegmented"])
            if SHOTS:
                pg.screenshot(path=os.path.join(SHOTS, "contorno_1366x768_preview.png"))
            pg.fill("#ced-nota", "lado direito comido")
            pg.click("#ced-save")
            pg.wait_for_selector("#tab-celula.on .chip.manual", timeout=60_000)
            assert "contorno manual" in pg.inner_text("#tab-celula")
            assert "lado direito comido" in pg.inner_text("#tab-celula")
            assert _nlines(OV.overrides_path(pr)) == n_ov + 1
            q = Project.open(pr.path)
            res = [e for e in q.events() if e["action"] == "piece_resegmented"]
            assert len(res) == n_res + 1 and res[-1]["motivo"] == "manual" and res[-1]["piece"] == placed
            assert res[-1]["nota"] == "lado direito comido" and q.piece(placed).flags["manual_override"] is True
            assert q.check_invariants(disk=True) == []
            assert pg.evaluate("S.ced") is None
            if SHOTS:
                pg.screenshot(path=os.path.join(SHOTS, "contorno_1366x768_gaveta.png"))
            # reopening shows the manual outline, cancel goes back without writing
            pg.click("#tab-celula [data-contorno]")
            pg.wait_for_selector("#tab-contorno.on .ced-who .chip.manual", timeout=30_000)
            pg.click("#ced-cancel")
            pg.wait_for_selector("#tab-celula.on", timeout=30_000)
            assert _nlines(OV.overrides_path(pr)) == n_ov + 1
            br.close()
    finally:
        server.should_exit = True
        th.join(10)
    assert not errs, errs


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
def test_contour_editor_layout(served, browser, w, h):
    """Editor open (from the drawer of the placed piece): no horizontal overflow of the document or of the
    tab, no document vertical scroll, the canvas has room and the save button exists; touch drag works on
    phones (pointer events)."""
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
        assert pg.evaluate("(() => { const t = document.querySelector('#tab-contorno'); return t.scrollWidth <= t.clientWidth + 1; })()"), (w, h)
        cv = pg.evaluate("(() => { const r = document.querySelector('#ced-canvas').getBoundingClientRect(); return [r.width, r.height, r.right]; })()")
        assert cv[0] >= 200 and cv[1] >= 150 and cv[2] <= w + 0.5, (w, h, cv)
        assert pg.locator("#ced-save").count() == 1 and pg.locator("#ced-cancel").count() == 1
        if phone:     # real touch (CDP touch events -> pointer events of type touch): drag the rightmost vertex
            k = pg.evaluate("S.ced.pts.reduce((b, p, i, a) => p[0] > a[b][0] ? i : b, 0)")
            x0 = pg.evaluate(f"S.ced.pts[{k}][0]")
            x, y = _vertex_page_xy(pg, k)
            cdp = ctx.new_cdp_session(pg)
            for typ, dx in (("touchStart", 0), ("touchMove", 6), ("touchMove", 12), ("touchEnd", 12)):
                pts = [] if typ == "touchEnd" else [{"x": x + dx, "y": y, "id": 1}]
                cdp.send("Input.dispatchTouchEvent", {"type": typ, "touchPoints": pts})
            pg.wait_for_timeout(100)
            assert pg.evaluate(f"S.ced.pts[{k}][0]") > x0 + 2
        if SHOTS and (w, h) in ((1366, 768), (360, 640)):
            os.makedirs(SHOTS, exist_ok=True)
            pg.screenshot(path=os.path.join(SHOTS, f"contorno_layout_{w}x{h}.png"))
    finally:
        ctx.close()
    assert not errs, errs
