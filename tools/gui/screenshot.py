"""Screenshots of the web GUI (src/server.py + src/web) with headless Chromium (Playwright).

Usage::

    python tools/gui/screenshot.py [--project $PPF_SCRATCH/g_alpes] [--out docs/gui/screenshots]

Starts ``python -m src.server`` on a free port over ``--project`` (use a COPY of
projects/alpes: the server may write caches under ``render/gui/``; nothing is confirmed
here), waits until it is ready, and captures:

* ``progresso.png`` (1400 x 900, whole board), ``progresso_zoom_relva.png`` (rows 42-47, cols 1-8),
  ``progresso_zoom_ceu.png`` (rows 1-6, cols 5-24), ``celula.png`` (cell drawer of (3, 37)),
  ``vai_buscar.png`` (the sky rows with the proposals, list scrolled to the 2nd card), ``lotes.png``, ``mesa.png``, ``importar.png``;
* ``telemovel_progresso.png`` and ``telemovel_vai_buscar.png`` at 390 x 844.

Each file is kept <= 300 KB: PNG, else JPEG (same name, ``.jpg``; a 256-colour PNG was tried and
rejected: the quantisation shifts the legend colours).
Needs ``pip install -r requirements-dev.txt`` and ``python -m playwright install chromium``.
"""

import argparse
import io
import os
import socket
import subprocess
import sys
import time
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAX_BYTES = 300_000


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def wait_ready(base: str, timeout: float = 600.0) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(base + "/api/status", timeout=5) as r:
                if b'"pronto"' in r.read():
                    with urllib.request.urlopen(base + "/api/board.jpg?ppc=60", timeout=600) as r2:
                        if r2.status == 200:
                            return
        except OSError:
            pass
        time.sleep(1.0)
    raise RuntimeError("o servidor não ficou pronto")


def save_small(png: bytes, out_dir: str, name: str) -> str:
    """Write ``name`` (.png) under ``out_dir`` within MAX_BYTES; returns the path written."""
    from PIL import Image
    path = os.path.join(out_dir, name)
    for old in (path, path[:-4] + ".jpg"):
        if os.path.exists(old):
            os.remove(old)
    if len(png) <= MAX_BYTES:
        with open(path, "wb") as f:
            f.write(png)
        return path
    im = Image.open(io.BytesIO(png)).convert("RGB")   # JPEG, not a 256-colour PNG: quantising shifts the legend colours
    path = path[:-4] + ".jpg"
    for q in (88, 82, 76, 70, 62):
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=q, optimize=True, progressive=True)
        if buf.tell() <= MAX_BYTES:
            break
    with open(path, "wb") as f:
        f.write(buf.getvalue())
    return path


def settle(page, ms: int = 600) -> None:
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(ms)


def zoom_wait(page, js: str) -> None:
    """Run a zoom and wait until the high-resolution region raster of the new view has loaded."""
    prev = page.evaluate("document.body.dataset.detail || ''")
    page.evaluate(js)
    page.wait_for_timeout(400)
    if page.evaluate("pxPerCell() * (window.devicePixelRatio || 1) > S.ppc * 1.1"):
        page.wait_for_function(f"(document.body.dataset.detail || '') !== {prev!r}", timeout=120_000)
    settle(page, 800)


def main(argv=None) -> int:
    scratch = os.environ.get("PPF_SCRATCH", os.path.join(REPO, "scratch"))
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", default=os.path.join(scratch, "g_alpes"))
    ap.add_argument("--out", default=os.path.join(REPO, "docs", "gui", "screenshots"))
    ap.add_argument("--port", type=int, default=0)
    args = ap.parse_args(argv)
    from playwright.sync_api import sync_playwright

    os.makedirs(args.out, exist_ok=True)
    port = args.port or free_port()
    base = f"http://127.0.0.1:{port}"
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    srv = subprocess.Popen([sys.executable, "-m", "src.server", "--project", args.project, "--port", str(port)],
                           cwd=REPO, env=env)
    written = []
    try:
        wait_ready(base)
        with sync_playwright() as pw:
            br = pw.chromium.launch()

            def shot(page, name):
                written.append(save_small(page.screenshot(), args.out, name))
                print(f"  {written[-1]} ({os.path.getsize(written[-1]) // 1024} KB)")

            def open_page(w, h):
                pg = br.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
                pg.goto(base + "/")
                pg.wait_for_selector("body[data-ready='1']", timeout=120_000)
                pg.wait_for_selector("body[data-raster]", timeout=120_000)
                settle(pg, 800)
                return pg

            pg = open_page(1400, 900)
            shot(pg, "progresso.png")
            zoom_wait(pg, "zoomCells(42, 1, 47, 8, 0.02)")
            shot(pg, "progresso_zoom_relva.png")
            zoom_wait(pg, "zoomCells(1, 5, 6, 24, 0.02)")
            shot(pg, "progresso_zoom_ceu.png")
            pg.evaluate("openCell(3, 37, {zoom: true})")
            pg.wait_for_selector("#tab-celula .zoomrow", timeout=60_000)
            settle(pg, 1200)
            shot(pg, "celula.png")
            pg.evaluate("showTab('buscar')")
            zoom_wait(pg, "zoomCells(1, 26, 7, 58, 0.02)")
            pg.evaluate("document.querySelectorAll('#tab-buscar .card')[1].scrollIntoView({block: 'start'})")
            settle(pg, 1200)
            shot(pg, "vai_buscar.png")
            pg.evaluate("showTab('lotes')")
            pg.wait_for_selector("#tab-lotes details.lot", timeout=60_000)
            settle(pg, 1500)
            shot(pg, "lotes.png")
            pg.evaluate("showTab('mesa')")
            pg.wait_for_selector("#tab-mesa .cand button", timeout=60_000)
            pg.click("#tab-mesa .cand button")
            settle(pg, 1500)
            shot(pg, "mesa.png")
            pg.evaluate("showTab('importar'); fitBoard()")
            settle(pg, 600)
            shot(pg, "importar.png")
            pg.close()

            ph = open_page(390, 844)
            shot(ph, "telemovel_progresso.png")
            ph.evaluate("document.getElementById('app').classList.add('sheet-up'); setView(S.vb)")
            settle(ph, 1200)
            shot(ph, "telemovel_vai_buscar.png")
            ph.close()
            br.close()
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
    print(f"{len(written)} capturas em {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
