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
        pg.wait_for_selector("#tab-buscar .card", timeout=30_000)
        pg.wait_for_timeout(500)
        assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth")
        r = pg.evaluate("(() => { const b = document.querySelector('#legend-box > summary').getBoundingClientRect();"
                        " return [b.left, b.top, b.right, b.bottom, innerWidth, innerHeight]; })()")
        assert r[0] >= 0 and r[1] >= 0 and r[2] <= r[4] and r[3] <= r[5], r
        pg.evaluate("document.querySelector('#tab-buscar .card').scrollIntoView({block: 'start'})")
        pg.wait_for_timeout(200)
        ok = pg.evaluate("""(() => { const p = document.querySelector('#panel').getBoundingClientRect();
          return [...document.querySelectorAll('#tab-buscar .card')].some((c) => { const b = c.getBoundingClientRect();
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
    finally:
        pg.close()
