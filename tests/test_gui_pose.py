"""GUI: «Editar posicionamento» (pose manual de uma peça colocada) em Chromium headless (slow).

Projeto sintético de ``tests/test_consistency.py::_row_project``: C/A/B em (2,2)/(2,3)/(2,4), todas colocadas
com a rotação certa; a peça editada é A (2,3), com vizinhas W e E.
Capturas com ``PPF_SHOTS=1`` em ``docs/gui/screenshots/`` (``pose_1366.png``, ``pose_390.png``).
"""

import json
import os
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
from test_consistency import _row_project  # noqa: E402
from test_gui_layout import TAB_VIEWPORTS  # noqa: E402

SHOTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "gui", "screenshots")


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    import uvicorn
    tmp = tmp_path_factory.mktemp("pose")
    pr, ids = _row_project(tmp)
    gui = S.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp / "uploads"), log=None)
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    server = uvicorn.Server(uvicorn.Config(S.create_app(gui), host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    t0 = time.time()
    while not server.started and time.time() - t0 < 30:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", pr, ids["A"]
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


def _events(pr, nome):
    with open(pr.log_path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip() and json.loads(x).get("action") == nome]


def _open_mode(pg, base, pid):
    pg.goto(base + "/")
    pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
    pg.evaluate("openCell(2, 3, {zoom: true})")
    pg.wait_for_selector(f"[data-pose-btn='{pid}']", timeout=15_000)
    pg.click(f"[data-pose-btn='{pid}']")
    pg.wait_for_selector("#pose-layer #pose-img", timeout=15_000)
    pg.evaluate("document.activeElement && document.activeElement.blur()")


def _cand(pg):
    return pg.evaluate("({...S.pose.cand})")


def test_pose_mode_adjust_and_save(env, browser):
    base, pr, pid = env
    errs = []
    pg = browser.new_page(viewport={"width": 1366, "height": 768})
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))
    try:
        _open_mode(pg, base, pid)
        # layer: imagem + contornos (peça + vizinhas W e E)
        assert pg.locator("#pose-layer image").count() == 1
        assert pg.locator("#pose-layer path.pose-contour").count() == 1
        assert pg.locator("#pose-layer path.pose-neigh").count() == 2
        eff = pg.evaluate("S.pose.d.efetiva")
        c0 = _cand(pg)
        assert abs(c0["dx"] - round(eff["dx_mm"], 3)) < 1e-6 and abs(c0["dy"] - round(eff["dy_mm"], 3)) < 1e-6
        tr = pg.get_attribute("#pose-piece", "transform")
        assert tr.startswith("translate(") and "rotate(" in tr
        # sem snap: nada mudou sozinho
        pg.wait_for_selector("#pose-juntas .pose-gap", timeout=10_000)
        assert _cand(pg) == c0
        # teclas
        pg.keyboard.press("ArrowRight")
        c1 = _cand(pg)
        assert abs(c1["dx"] - (c0["dx"] + 0.1)) < 1e-6
        pg.keyboard.press("Shift+ArrowUp")
        c2 = _cand(pg)
        assert abs(c2["dy"] - (c0["dy"] - 0.5)) < 1e-6
        pg.keyboard.press("q")
        c3 = _cand(pg)
        assert abs(c3["theta"] - (c0["theta"] - 0.1)) < 1e-6 or abs(abs(c3["theta"] - c0["theta"]) - 359.9) < 1e-3
        # campo θ editado
        pg.fill("[data-pose-f='theta']", "12.3")
        assert abs(_cand(pg)["theta"] - 12.3) < 1e-6
        # Alinhar a 90°
        pg.click("[data-pose-act='r90']")
        assert _cand(pg)["theta"] == 0
        # Pose automática repõe
        pg.click("[data-pose-act='auto']")
        a = pg.evaluate("S.pose.d.automatica")
        ca = _cand(pg)
        assert abs(ca["dx"] - round(a["dx_mm"], 3)) < 1e-6 and abs(ca["dy"] - round(a["dy_mm"], 3)) < 1e-6
        # arrastar a peça: Δpx -> Δmm
        box = pg.locator("#pose-hit").bounding_box()
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        ppc = pg.evaluate("pxPerCell()")
        w = pg.evaluate("S.pose.d.w_mm")
        before = _cand(pg)
        pg.mouse.move(x, y)
        pg.mouse.down()
        pg.mouse.move(x + 20, y + 10, steps=4)
        pg.mouse.up()
        after = _cand(pg)
        assert abs((after["dx"] - before["dx"]) - 20 / ppc * w) < 0.02 + 0.01 * w
        assert abs((after["dy"] - before["dy"]) - 10 / ppc * w) < 0.02 + 0.01 * w
        # a pega de rotação roda
        hit = pg.locator("#pose-rot-hit").bounding_box()
        hx, hy = hit["x"] + hit["width"] / 2, hit["y"] + hit["height"] / 2
        t_before = _cand(pg)["theta"]
        pg.mouse.move(hx, hy)
        pg.mouse.down()
        pg.mouse.move(hx + 40, hy + 5, steps=4)
        pg.mouse.up()
        assert abs(_cand(pg)["theta"] - t_before) > 1.0
        # volta à pose automática, depois um deslocamento pequeno e legível
        pg.click("[data-pose-act='auto']")
        pg.keyboard.press("ArrowDown")
        # painel ao vivo: folgas em mm e ms
        pg.wait_for_function("document.querySelector('#pose-diff').textContent.includes(' ms')", timeout=10_000)
        assert "mm" in pg.inner_text("#pose-juntas")
        assert pg.locator("#pose-juntas .pose-j[data-dir='W'] .pose-gap").count() == 1
        assert pg.locator("#pose-juntas .pose-j[data-dir='N'] .pose-gap").count() == 0
        if os.environ.get("PPF_SHOTS"):
            os.makedirs(SHOTS, exist_ok=True)
            pg.screenshot(path=os.path.join(SHOTS, "pose_1366.png"))
        # Esc com alterações pede confirmação; recusar mantém o modo
        msgs = []
        pg.once("dialog", lambda dlg: (msgs.append(dlg.message), dlg.dismiss()))
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(200)
        assert msgs and pg.evaluate("S.pose !== null")
        # gravar (com nota)
        n_set = len(_events(pr, "pose_set"))
        final = _cand(pg)
        pg.fill("#pose-nota", "ensaio")
        pg.click("#pose-save")
        pg.wait_for_selector(f"[data-pose-badge='{pid}']", timeout=90_000)
        assert pg.evaluate("S.pose") is None
        assert pg.locator("#pose-layer *").count() == 0
        ev = _events(pr, "pose_set")
        assert len(ev) == n_set + 1 and ev[-1]["piece"] == pid and ev[-1]["nota"] == "ensaio"
        assert abs(ev[-1]["dx_mm"] - final["dx"]) < 1e-3 and abs(ev[-1]["dy_mm"] - final["dy"]) < 1e-3
        assert "pose manual" in pg.inner_text("#tab-celula")
        pm = pg.evaluate(f"fetch('/api/pieces/{pid}').then((r) => r.json())")["pose_manual"]
        assert pm and abs(pm["dy_mm"] - final["dy"]) < 1e-3
        # reabrir: «Repor automática»
        pg.wait_for_selector(f"[data-pose-btn='{pid}']:not([disabled])", timeout=15_000)
        pg.click(f"[data-pose-btn='{pid}']")
        pg.wait_for_selector("#pose-reset", timeout=15_000)
        eff2 = pg.evaluate("S.pose.d.efetiva")
        assert eff2["manual"] is True and abs(_cand(pg)["dy"] - final["dy"]) < 1e-3
        n_clear = len(_events(pr, "pose_cleared"))
        pg.once("dialog", lambda dlg: dlg.accept())
        pg.click("#pose-reset")
        pg.wait_for_function("S.pose === null", timeout=90_000)
        pg.wait_for_function("!document.querySelector('[data-pose-badge]')", timeout=30_000)
        assert len(_events(pr, "pose_cleared")) == n_clear + 1
        assert not errs, errs
    finally:
        pg.close()


@pytest.mark.parametrize("w,h", TAB_VIEWPORTS)
def test_pose_layout(env, browser, w, h):
    base, pr, pid = env
    phone = w <= 430
    ctx = browser.new_context(viewport={"width": w, "height": h}, has_touch=phone, is_mobile=phone)
    pg = ctx.new_page()
    try:
        _open_mode(pg, base, pid)
        pg.wait_for_selector("#pose-juntas .pose-gap", timeout=10_000)
        pg.wait_for_timeout(300)
        assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert pg.evaluate("(() => { const t = document.querySelector('#tab-celula'); return t.scrollWidth <= t.clientWidth + 1; })()")
        pg.evaluate("document.querySelector('#pose-panel').scrollIntoView({block: 'start'})")
        # o painel cabe na largura da gaveta e os botões têm alvo de toque razoável
        r = pg.evaluate("(() => { const b = document.querySelector('#pose-panel').getBoundingClientRect(); return [b.left, b.right, innerWidth]; })()")
        assert r[0] >= -1 and r[1] <= r[2] + 1, r
        heights = pg.evaluate("[...document.querySelectorAll('#pose-panel button')].map((b) => b.getBoundingClientRect().height)")
        assert heights and min(heights) >= (40 if phone else 28), heights
        if phone:
            # toque real por CDP: arrastar a peça com um dedo
            box = pg.locator("#pose-hit").bounding_box()
            assert box and box["x"] >= 0 and box["y"] >= 0 and box["x"] + box["width"] <= w, box
            x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] * 0.7   # lejos da pega de rotação (em cima)
            cdp = ctx.new_cdp_session(pg)
            before = _cand(pg)
            ppc = pg.evaluate("pxPerCell()")
            cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y, "id": 1}]})
            for i in range(1, 5):
                cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x + 6 * i, "y": y + 3 * i, "id": 1}]})
            cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
            after = _cand(pg)
            wmm = pg.evaluate("S.pose.d.w_mm")
            assert abs((after["dx"] - before["dx"]) - 24 / ppc * wmm) < 0.05 + 0.02 * wmm, (before, after, ppc)
            assert abs((after["dy"] - before["dy"]) - 12 / ppc * wmm) < 0.05 + 0.02 * wmm
            if os.environ.get("PPF_SHOTS") and w == 390:
                os.makedirs(SHOTS, exist_ok=True)
                pg.evaluate("document.querySelector('#tab-celula').scrollTop = 0")
                pg.screenshot(path=os.path.join(SHOTS, "pose_390.png"))
        pg.click("#pose-cancel", timeout=5000) if not pg.evaluate("poseIsDirty(S.pose)") else pg.evaluate("poseClose()")
    finally:
        ctx.close()
