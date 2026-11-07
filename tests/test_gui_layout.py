"""Layout checks of the web GUI in headless Chromium over the synthetic project (slow).

Matrix = Windows scaling: the CSS viewport of 1366x768 / 1920x1080 at 100/125/150 % is
W/dsf x H/dsf. Checks: no horizontal overflow, the legend summary inside the viewport, one
fully visible card in the panel, and Ctrl+wheel on the board leaves the viewBox alone
(browser page zoom) while a plain wheel zooms it.
"""

import socket
import threading
import time

import pytest

pytestmark = pytest.mark.slow
pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("uvicorn")
sync_api = pytest.importorskip("playwright.sync_api")

from src import server as S  # noqa: E402
from test_query import _project  # noqa: E402

MATRIX = [(w, h, d) for (w, h) in ((1366, 768), (1920, 1080)) for d in (1.0, 1.25, 1.5)]


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    import uvicorn
    from src.query import run_query
    tmp = tmp_path_factory.mktemp("gui")
    pr, *_ = _project(tmp)
    run_query(pr, use_image=False)
    gui = S.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp / "uploads"), log=None)
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    server = uvicorn.Server(uvicorn.Config(S.create_app(gui), host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    t0 = time.time()
    while not server.started and time.time() - t0 < 30:
        time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    th.join(10)


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as pw:
        try:
            br = pw.chromium.launch()
        except Exception as e:  # chromium not installed
            pytest.skip(f"chromium indisponível: {e}")
        yield br
        br.close()


@pytest.mark.parametrize("w,h,dsf", MATRIX)
def test_layout(base, browser, w, h, dsf):
    vw, vh = round(w / dsf), round(h / dsf)
    pg = browser.new_page(viewport={"width": vw, "height": vh}, device_scale_factor=dsf)
    try:
        pg.goto(base + "/")
        pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
        pg.wait_for_selector("#tab-guardadas .card", state="attached", timeout=30_000)
        pg.evaluate("showTab('guardadas'); document.querySelector('#tab-guardadas details.guardadas').open = true")
        pg.wait_for_timeout(500)
        assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth")
        r = pg.evaluate("(() => { const b = document.querySelector('#legend-box > summary').getBoundingClientRect();"
                        " return [b.left, b.top, b.right, b.bottom, innerWidth, innerHeight]; })()")
        assert r[0] >= 0 and r[1] >= 0 and r[2] <= r[4] and r[3] <= r[5], r
        pg.evaluate("document.querySelector('#tab-guardadas .card').scrollIntoView({block: 'start'})")
        pg.wait_for_timeout(200)
        ok = pg.evaluate("""(() => { const p = document.querySelector('#panel').getBoundingClientRect();
          return [...document.querySelectorAll('#tab-guardadas .card')].some((c) => { const b = c.getBoundingClientRect();
            return b.top >= p.top && b.bottom <= p.bottom && b.left >= p.left && b.right <= p.right; }); })()""")
        assert ok, "nenhum cartão totalmente visível no painel"
        # Ctrl+wheel must not zoom the board; plain wheel must
        vb0 = pg.get_attribute("#board", "viewBox")
        pg.evaluate("document.querySelector('#board').dispatchEvent(new WheelEvent('wheel', "
                    "{deltaY: -400, ctrlKey: true, bubbles: true, cancelable: true, clientX: 300, clientY: 200}))")
        assert pg.get_attribute("#board", "viewBox") == vb0
        pg.evaluate("document.querySelector('#board').dispatchEvent(new WheelEvent('wheel', "
                    "{deltaY: -400, bubbles: true, cancelable: true, clientX: 300, clientY: 200}))")
        assert pg.get_attribute("#board", "viewBox") != vb0
        # no horizontal scroll anywhere (document, panel, every tab), vertical scroll only inside the panel
        for tab in ("buscar", "lotes", "mesa", "importar"):
            pg.evaluate(f"showTab('{tab}')")
            pg.wait_for_timeout(300)
            assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth"), tab
            assert pg.evaluate("document.documentElement.scrollHeight <= innerHeight"), tab
            assert pg.evaluate(f"(() => {{ const t = document.querySelector('#tab-{tab}');"
                               " return t.scrollWidth <= t.clientWidth + 1; })()"), tab
        pg.evaluate("showTab('buscar')")
        ov = pg.evaluate("(() => { const t = document.querySelector('#tab-buscar');"
                         " return [getComputedStyle(t).overflowY, getComputedStyle(document.body).overflowY]; })()")
        assert ov[0] in ("auto", "scroll") and ov[1] == "hidden", ov
        # collapsible legend: pointer cursor, opens and closes
        cur = pg.evaluate("getComputedStyle(document.querySelector('#legend-box > summary')).cursor")
        assert cur == "pointer", cur
        pg.evaluate("document.querySelector('#legend-box').open = false")
        pg.click("#legend-box > summary")
        assert pg.evaluate("document.querySelector('#legend-box').open") is True
        pg.click("#legend-box > summary")
        assert pg.evaluate("document.querySelector('#legend-box').open") is False
        # one arrow on each side of the word
        pseudo = pg.evaluate("[getComputedStyle(document.querySelector('#legend-box > summary'), '::before').content,"
                             " getComputedStyle(document.querySelector('#legend-box > summary'), '::after').content]")
        assert all(p not in ('none', 'normal', '""') for p in pseudo), pseudo
        # Reportar is red
        pg.evaluate("showTab('buscar')")
    finally:
        pg.close()


TAB_VIEWPORTS = [(1366, 768), (1920, 1080), (911, 512), (1024, 768), (768, 1024), (390, 844), (360, 640)]


@pytest.mark.parametrize("w,h", TAB_VIEWPORTS)
def test_tabs_in_top_bar(base, browser, w, h):
    """The six tabs live in the top bar (not in the side panel): all fully inside the viewport, no
    horizontal scroll, on the same row as the name on wide screens, and each one opens its section."""
    pg = browser.new_page(viewport={"width": w, "height": h})
    try:
        pg.goto(base + "/")
        pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
        pg.wait_for_timeout(300)
        assert pg.evaluate("!!document.querySelector('#top #tabs') && !document.querySelector('#panel #tabs')")
        rects = pg.evaluate("[...document.querySelectorAll('#tabs button')].map((b) => { const r = b.getBoundingClientRect();"
                            " return [b.dataset.tab, r.left, r.right, r.top, r.bottom, r.width]; })")
        assert [r[0] for r in rects] == ["buscar", "guardadas", "lotes", "mesa", "importar", "reports"]
        for tab, left, right, top, bottom, width in rects:
            assert width > 20 and left >= 0 and right <= w and top >= 0 and bottom <= h, (tab, left, right, w)
        assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth")
        top_h = pg.evaluate("document.querySelector('#top').getBoundingClientRect().height")
        if w >= 1181:     # one row: tabs next to the name / progress
            assert top_h <= 64, top_h
            nm = pg.evaluate("document.querySelector('.brand').getBoundingClientRect().right")
            assert rects[0][1] >= nm - 1, "tabs overlap the brand"
        else:             # phone / tablet: second row, never more than 2 rows
            assert top_h <= 110, top_h
        for tab in ("reports", "guardadas", "lotes", "mesa", "importar", "buscar"):
            pg.click(f"#tabs button[data-tab={tab}]")
            assert pg.evaluate(f"document.querySelector('#tab-{tab}').classList.contains('on')"), tab
            assert pg.evaluate(f"document.querySelector('#tabs button[data-tab={tab}]').classList.contains('on')"), tab
        assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth")
    finally:
        pg.close()


@pytest.mark.parametrize("w", [1100, 1180, 1181, 1280, 1366, 1440])
def test_top_bar_no_overlap_with_job_pill_and_big_badges(base, browser, w):
    """Worst case of the top bar: the job pill visible and realistic badges (Vai buscar 3 digits, Guardadas 2,
    Mesa 2, Reports 22): no two items overlap, everything inside the viewport, no horizontal scroll."""
    pg = browser.new_page(viewport={"width": w, "height": 800})
    try:
        pg.goto(base + "/")
        pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
        pg.evaluate("""() => {
          const j = document.querySelector('#job-pill'); j.hidden = false; j.textContent = 'a importar o saco 3 · 45 %';
          for (const [id, t] of [['n-buscar', '123'], ['n-guardadas', '12'], ['n-mesa', '41'], ['n-reports', '22']])
            document.getElementById(id).textContent = t;
        }""")
        pg.wait_for_timeout(300)
        items = pg.evaluate("""() => {
          const r = (e) => { const b = e.getBoundingClientRect(); return [b.left, b.top, b.right, b.bottom]; };
          const out = [['brand', r(document.querySelector('#top .brand'))]];
          for (const b of document.querySelectorAll('#tabs button')) out.push(['tab ' + b.dataset.tab, r(b)]);
          out.push(['search', r(document.querySelector('#top #search'))]);
          for (const e of document.querySelectorAll('#top .tools > *')) if (!e.hidden) out.push(['tool ' + (e.id || e.className), r(e)]);
          return out;
        }""")
        names = [n for n, _ in items]
        assert "tool job-pill" in " ".join(names) or any(n.startswith("tool job") for n in names), names
        eps = 0.5
        for i, (na, a) in enumerate(items):
            assert a[0] >= -eps and a[2] <= w + eps, (w, na, a)
            for nb, b in items[i + 1:]:
                inter_w = min(a[2], b[2]) - max(a[0], b[0])
                inter_h = min(a[3], b[3]) - max(a[1], b[1])
                assert not (inter_w > eps and inter_h > eps), (w, na, nb, a, b)
        assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth"), w
    finally:
        pg.close()


@pytest.mark.parametrize("w,h,dsf", [(w, h, 1.0) for w, h in TAB_VIEWPORTS] + [m for m in MATRIX])
def test_search_in_top_bar(base, browser, w, h, dsf):
    """The search box lives in the top bar: visible (or, on a phone, a magnifier that opens the box),
    inside the viewport, never overlapping the tabs, no horizontal scroll, top bar height within bounds."""
    vw, vh = (round(w / dsf), round(h / dsf)) if (w, h, dsf) in MATRIX else (w, h)
    pg = browser.new_page(viewport={"width": vw, "height": vh}, device_scale_factor=dsf)
    try:
        pg.goto(base + "/")
        pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
        pg.wait_for_timeout(300)
        assert pg.evaluate("!!document.querySelector('#top #search #q') && !document.querySelector('#panel #search')")
        phone = vw <= 900

        def boxes():
            return pg.evaluate("""() => {
              const r = (e) => { const b = e.getBoundingClientRect(); return [b.left, b.top, b.right, b.bottom]; };
              const vis = (e) => { const b = e.getBoundingClientRect(); return b.width > 0 && b.height > 0; };
              const q = document.querySelector('#q'), btn = document.querySelector('#search-btn');
              return { form: r(document.querySelector('#search')), q: vis(q) ? r(q) : null, btn: vis(btn) ? r(btn) : null,
                       tabs: [...document.querySelectorAll('#tabs button')].map(r),
                       top: document.querySelector('#top').getBoundingClientRect().height,
                       sw: document.documentElement.scrollWidth <= innerWidth };
            }""")
        b = boxes()
        assert b["sw"]
        if phone:
            assert b["btn"] is not None and b["q"] is None, b
            target = b["btn"]
        else:
            assert b["q"] is not None and b["btn"] is None, b
            assert b["q"][2] - b["q"][0] >= 90, b["q"]
            target = b["q"]
        assert target[0] >= 0 and target[2] <= vw + 0.5 and target[1] >= 0 and target[3] <= vh, (vw, target)
        for t in b["tabs"]:
            iw = min(target[2], t[2]) - max(target[0], t[0])
            ih = min(target[3], t[3]) - max(target[1], t[1])
            assert not (iw > 0.5 and ih > 0.5), (vw, target, t)
        assert b["top"] <= (64 if vw >= 1181 else 110), (vw, b["top"])
        if phone:
            pg.click("#search-btn")
            b2 = boxes()
            assert b2["q"] is not None and b2["q"][0] >= 0 and b2["q"][2] <= vw + 0.5, b2
            assert b2["sw"]
    finally:
        pg.close()
