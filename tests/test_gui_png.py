"""GUI: clique direito numa miniatura -> menu «Copiar imagem (PNG)» / «Guardar PNG» (slow).

Fonte: ``/api/pieces/<id>.png?pose=board|scan&size=600`` (só a peça, fundo transparente). O PNG copiado
decodifica-se em Python: 600 px de lado e alfa 0 no canto.
"""

import base64
import io

import pytest

pytestmark = pytest.mark.slow
pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("uvicorn")
sync_api = pytest.importorskip("playwright.sync_api")
Image = pytest.importorskip("PIL.Image")

from test_gui_guardadas import _serve  # noqa: E402
from test_query import _project  # noqa: E402


@pytest.fixture()
def env(tmp_path):
    from src.query import run_query
    pr, placed, tw, dec = _project(tmp_path)
    run_query(pr, use_image=False)
    gui, server, th, base = _serve(pr.path, str(tmp_path / "uploads"))
    yield base, tw
    server.should_exit = True
    th.join(10)


def _ctx(pw, base, init_script=None, grant=True):
    try:
        br = pw.chromium.launch()
    except Exception as e:  # chromium not installed
        pytest.skip(f"chromium indisponível: {e}")
    ctx = br.new_context(viewport={"width": 1400, "height": 900}, accept_downloads=True)
    if grant:
        ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=base)
    if init_script:
        ctx.add_init_script(init_script)
    pg = ctx.new_page()
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(base + "/")
    pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
    return br, pg, errs


def test_context_menu_copy_and_save(env):
    base, tw = env
    with sync_api.sync_playwright() as pw:
        br, pg, errs = _ctx(pw, base)
        pg.evaluate(f"openPiece('{tw}')")
        pimg = "#tab-celula .card .pimg"
        pg.wait_for_selector(pimg, timeout=15_000)
        pg.click(pimg, button="right")                              # o SVG por cima do <img> também abre o menu
        pg.wait_for_selector("#ctx-menu", state="visible")
        assert pg.inner_text("#ctx-menu").splitlines() == ["Copiar imagem (PNG)", "Guardar PNG"]
        assert pg.get_attribute("#ctx-menu [data-act=copiar]", "aria-disabled") is None
        pg.click("#ctx-menu [data-act=copiar]")
        pg.wait_for_selector(f"#toast :text('Imagem de {tw} copiada')", timeout=15_000)
        assert pg.locator("#ctx-menu").count() == 0                 # fecha ao escolher
        b64 = pg.evaluate("""async () => {
          const items = await navigator.clipboard.read();
          const it = items.find((i) => i.types.includes('image/png'));
          if (!it) return null;
          const blob = await it.getType('image/png');
          const buf = new Uint8Array(await blob.arrayBuffer());
          let s = ''; for (const b of buf) s += String.fromCharCode(b);
          return btoa(s);
        }""")
        assert b64, "a área de transferência não tem image/png"
        im = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGBA")
        assert im.size == (600, 600), im.size
        assert im.getpixel((0, 0))[3] == 0                           # fundo transparente no canto
        assert any(im.getpixel((x, 300))[3] > 0 for x in range(0, 600, 10))   # e a peça lá dentro
        # guardar
        pg.click(pimg, button="right")
        pg.wait_for_selector("#ctx-menu", state="visible")
        with pg.expect_download() as dl:
            pg.click("#ctx-menu [data-act=guardar]")
        assert dl.value.suggested_filename == f"{tw}_board.png" or dl.value.suggested_filename == f"{tw}_scan.png"
        path = dl.value.path()
        im2 = Image.open(path).convert("RGBA")
        assert im2.size == (600, 600) and im2.getpixel((0, 0))[3] == 0
        # Esc fecha o menu; clicar fora também
        pg.click(pimg, button="right")
        pg.wait_for_selector("#ctx-menu", state="visible")
        pg.keyboard.press("Escape")
        assert pg.locator("#ctx-menu").count() == 0
        pg.click(pimg, button="right")
        pg.wait_for_selector("#ctx-menu", state="visible")
        pg.mouse.click(5, 5)
        assert pg.locator("#ctx-menu").count() == 0
        br.close()
    assert errs == []


def test_context_menu_pose_follows_the_image(env):
    """A pose do PNG é a da imagem clicada: miniatura do scan -> ``_scan.png``."""
    base, tw = env
    with sync_api.sync_playwright() as pw:
        br, pg, errs = _ctx(pw, base)
        pg.evaluate(f"""fetch('/api/report', {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ piece: '{tw}', tipo: 'outro', texto: 'png' }}) }}).then((x) => x.json())""")
        pg.evaluate("showTab('reports')")
        pg.wait_for_selector("#tab-reports details.report-row", timeout=15_000)
        pg.click("#tab-reports details.report-row > summary img.rthumb", button="right")
        pg.wait_for_selector("#ctx-menu", state="visible")
        with pg.expect_download() as dl:
            pg.click("#ctx-menu [data-act=guardar]")
        assert dl.value.suggested_filename == f"{tw}_scan.png"
        # figura «no tabuleiro» da linha expandida
        pg.click("#tab-reports details.report-row > summary")
        pg.wait_for_selector("#tab-reports .rthumbs img")
        pg.click("#tab-reports .rthumbs figure:first-child img", button="right")
        pg.wait_for_selector("#ctx-menu", state="visible")
        with pg.expect_download() as dl:
            pg.click("#ctx-menu [data-act=guardar]")
        assert dl.value.suggested_filename == f"{tw}_board.png"
        br.close()


def test_copy_unavailable_without_clipboard_item(env):
    base, tw = env
    with sync_api.sync_playwright() as pw:
        br, pg, errs = _ctx(pw, base, init_script="delete window.ClipboardItem;")
        pg.evaluate(f"openPiece('{tw}')")
        pimg = "#tab-celula .card .pimg"
        pg.wait_for_selector(pimg, timeout=15_000)
        pg.click(pimg, button="right")
        pg.wait_for_selector("#ctx-menu", state="visible")
        assert pg.get_attribute("#ctx-menu [data-act=copiar]", "aria-disabled") == "true"
        assert "localhost ou https" in pg.get_attribute("#ctx-menu [data-act=copiar]", "title")
        pg.click("#ctx-menu [data-act=copiar]", force=True)        # aria-disabled: o Playwright trata-o como desativado
        pg.wait_for_selector("#toast :text('Guardar PNG')", timeout=10_000)
        assert "Copiar não disponível" in pg.inner_text("#toast")
        # «Guardar PNG» continua a funcionar
        pg.click(pimg, button="right")
        with pg.expect_download() as dl:
            pg.click("#ctx-menu [data-act=guardar]")
        assert dl.value.suggested_filename.endswith(".png")
        br.close()
    assert errs == []
