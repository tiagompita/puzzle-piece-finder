"""Capturas de comparação da F1b do redesenho (GUI antiga «Vai buscar» em / contra «Montar» em /novo/) e contagem de
palavras e botões visíveis no ecrã principal (ESPEC §6).

Uso::

    python tools/gui/f1b_capturas.py --project COPIA_DE_ALPES --out DIR [--vazio OUTRA_COPIA]

Arranca ``python -m src.server`` sobre ``--project`` (uma CÓPIA de projects/alpes: o passo ``nao`` grava uma rejeição e
desfá-la) e, a 1366x768 e a 390x844, guarda em PNG:

* ``F1b_antes_<vp>.png``: a GUI antiga em ``/``, aba «Vai buscar»;
* ``F1b_montar_<vp>.png``: a GUI nova, cartão «Próxima peça»;
* ``F1b_porque_<vp>.png``: «Porquê esta peça?»;
* ``F1b_nao_<vp>.png``: depois de «Não encaixa» (a rejeição é desfeita a seguir, na cópia);
* com ``--vazio``: ``F1b_vazio_<vp>.png`` (fila vazia) sobre essa outra cópia.

Escreve ``contagens.json``: palavras e botões visíveis em ``#top`` + painel, antes e depois.
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from screenshot import REPO, free_port, wait_ready  # noqa: E402

VIEWPORTS = {"1366": (1366, 768), "390": (390, 844)}
HIDE = "#toast, #job-pill { visibility: hidden !important; } * { caret-color: transparent !important; }"
_COUNT = r"""((roots) => {
    const vis = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
        return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'
            && r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth; };
    let words = 0, buttons = 0;
    for (const sel of roots) { const el = document.querySelector(sel); if (!el) continue;
        words += (el.innerText || '').split(/\s+/).filter((w) => /[\p{L}\p{N}]/u.test(w)).length; }
    for (const b of document.querySelectorAll('button, [role=tab], a.btn, label.toggle')) if (vis(b)) buttons++;
    return { palavras: words, botoes: buttons };
})"""


def _settle(pg, ms=900):
    try:
        pg.wait_for_load_state("networkidle", timeout=10_000)
    except Exception:  # noqa: BLE001 - o SSE mantém a rede ocupada
        pass
    pg.wait_for_timeout(ms)


def _shot(pg, out, name):
    pg.add_style_tag(content=HIDE)
    _settle(pg)
    pg.screenshot(path=os.path.join(out, name))
    print("  ", name)


def _server(project):
    port = free_port()
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    srv = subprocess.Popen([sys.executable, "-m", "src.server", "--project", project, "--port", str(port), "--no-prepare"],
                           cwd=REPO, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    wait_ready(base)
    return srv, base


def _stop(srv):
    srv.terminate()
    try:
        srv.wait(20)
    except subprocess.TimeoutExpired:
        srv.kill()


def _novo(pg, base):
    pg.goto(base + "/novo/")
    pg.wait_for_selector("body[data-ready='1']", timeout=300_000)
    for _ in range(300):                       # as sugestões pelo encaixe calculam-se em segundo plano na 1.ª vez
        if pg.evaluate("!!(S.montar && !(S.montar.a_preparar||{}).buracos)"):
            break
        pg.wait_for_timeout(3000)
        pg.evaluate("loadMontar()")
    _settle(pg, 1500)


def capture(project, out, vazio=None):
    from playwright.sync_api import sync_playwright
    os.makedirs(out, exist_ok=True)
    counts = {}
    srv, base = _server(project)
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch()
            for tag, (w, h) in VIEWPORTS.items():
                ctx = br.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
                pg2 = ctx.new_page()
                _novo(pg2, base)                       # primeiro: espera pelas sugestões pelo encaixe (as duas GUIs mostram-nas)
                pg = ctx.new_page()
                pg.goto(base + "/")
                pg.wait_for_selector("body[data-ready='1']", timeout=300_000)
                pg.wait_for_function("document.body.dataset.raster !== undefined", timeout=120_000)
                _settle(pg, 3000)
                _shot(pg, out, f"F1b_antes_{tag}.png")
                counts[f"antes_{tag}"] = pg.evaluate(_COUNT, ["#top", "#tab-buscar"])
                pg.close()
                pg2.bring_to_front()
                _shot(pg2, out, f"F1b_montar_{tag}.png")
                counts[f"depois_{tag}"] = pg2.evaluate(_COUNT, ["#top", "#tab-montar"])
                counts[f"depois_{tag}"]["fila"] = pg2.evaluate("S.montar.total")
                if pg2.locator("#b-porque").count():
                    pg2.click("#b-porque")
                    _shot(pg2, out, f"F1b_porque_{tag}.png")
                    pg2.keyboard.press("Escape")
                if pg2.locator("#b-nao").count():
                    pg2.click("#b-nao")
                    pg2.wait_for_selector("#m-motivos", timeout=120_000)
                    _shot(pg2, out, f"F1b_nao_{tag}.png")
                    pg2.click("#b-desfazer")
                    pg2.wait_for_selector("#b-encaixa", timeout=120_000)
                ctx.close()
            br.close()
    finally:
        _stop(srv)
    if vazio:
        srv, base = _server(vazio)
        try:
            with sync_playwright() as pw:
                br = pw.chromium.launch()
                for tag, (w, h) in VIEWPORTS.items():
                    ctx = br.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
                    pg = ctx.new_page()
                    _novo(pg, base)
                    _shot(pg, out, f"F1b_vazio_{tag}.png")
                    ctx.close()
                br.close()
        finally:
            _stop(srv)
    with open(os.path.join(out, "contagens.json"), "w", encoding="utf-8") as f:
        json.dump(counts, f, ensure_ascii=False, indent=1)
    print(json.dumps(counts, ensure_ascii=False))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--vazio", default=None)
    a = ap.parse_args(argv)
    capture(os.path.abspath(a.project), a.out, os.path.abspath(a.vazio) if a.vazio else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
