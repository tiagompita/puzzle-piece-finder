"""Capturas da GUI antiga para a F1a do redesenho (extrair o tabuleiro sem mudar comportamento) e comparação píxel a píxel.

Uso::

    python tools/gui/f1a_capturas.py capturar --project $PPF_SCRATCH/g_alpes --out DIR
    python tools/gui/f1a_capturas.py comparar DIR_A DIR_B

``capturar`` arranca ``python -m src.server`` sobre ``--project`` (usar uma CÓPIA de projects/alpes) e, a 1366x768 e a
390x844, guarda PNG de 4 estados que passam pelo código do tabuleiro: ``inicio`` (abertura, «Vai buscar»), ``celula``
(toque no centro do tabuleiro → gaveta da célula, via o gancho de toque), ``zoom`` (roda do rato sobre o tabuleiro + raster
de detalhe) e ``sugestoes`` (botão «Sugestões» ligado + toque numa célula sugerida → linha do grupo na Mesa). Os toasts, a
pílula do trabalho e o cursor de texto ficam escondidos (variam entre corridas). ``comparar`` diz, por ficheiro, o número de
píxeis diferentes, quantos passam o ruído (``NOISE``) e a maior diferença por canal.
"""

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from screenshot import REPO, free_port, wait_ready  # noqa: E402

VIEWPORTS = {"1366": (1366, 768), "390": (390, 844)}
NOISE = 8                    # diferença por canal até aqui = ruído de descodificação/reamostragem do raster JPEG (medido: ≤ 5)
HIDE = "#toast, #job-pill { visibility: hidden !important; } * { caret-color: transparent !important; }"


def _settle(pg, ms=900):
    try:
        pg.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:  # noqa: BLE001 - the SSE stream keeps the network busy
        pass
    pg.wait_for_timeout(ms)


def _shot(pg, out, name):
    pg.add_style_tag(content=HIDE)
    # o aviso no botão «Atividade» depende de quando chega uma linha de aviso do servidor: varia entre corridas
    pg.evaluate("document.querySelectorAll('[data-act-toggle]').forEach((b) => b.classList.remove('warn', 'err'))")
    _settle(pg)
    pg.screenshot(path=os.path.join(out, name))
    print("  ", name)


def capture(project: str, out: str) -> None:
    from playwright.sync_api import sync_playwright
    os.makedirs(out, exist_ok=True)
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    srv = subprocess.Popen([sys.executable, "-m", "src.server", "--project", project, "--port", str(port), "--no-prepare"],
                           cwd=REPO, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_ready(base)
        with sync_playwright() as pw:
            br = pw.chromium.launch()
            for tag, (w, h) in VIEWPORTS.items():
                ctx = br.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
                pg = ctx.new_page()
                pg.goto(base + "/")
                pg.wait_for_selector("body[data-ready='1']", timeout=300_000)
                pg.wait_for_function("document.body.dataset.raster !== undefined", timeout=120_000)
                _shot(pg, out, f"inicio_{tag}.png")
                # toque no centro do tabuleiro (o painel tapa metade do ecrã no telemóvel: toca no terço de cima)
                r = pg.evaluate("(() => { const b = document.querySelector('#board').getBoundingClientRect(); return [b.left, b.top, b.width, b.height]; })()")
                pg.mouse.click(r[0] + r[2] * 0.5, r[1] + r[3] * (0.5 if w > 800 else 0.3))
                pg.wait_for_function("S.tab === 'celula' && !!document.querySelector('#tab-celula .cell-head')", timeout=60_000)
                _shot(pg, out, f"celula_{tag}.png")
                pg.evaluate("showTab('buscar'); fitBoard()")
                # roda do rato: zoom à volta de um ponto + raster de detalhe
                pg.mouse.move(r[0] + r[2] * 0.3, r[1] + r[3] * 0.25)
                for _ in range(4):
                    pg.mouse.wheel(0, -240)
                    pg.wait_for_timeout(120)
                pg.wait_for_timeout(600)
                if pg.evaluate("pxPerCell() * (window.devicePixelRatio || 1) > S.ppc * 1.1"):
                    pg.wait_for_function("!!document.body.dataset.detail", timeout=120_000)
                _shot(pg, out, f"zoom_{tag}.png")
                # «Sugestões» ligado + toque numa célula sugerida
                pg.evaluate("fitBoard()")
                pg.click("#tg-sug")
                pg.wait_for_timeout(300)
                pt = pg.evaluate("""(() => { const it = suggestionItems().sort((a, b) => Number(b.safe) - Number(a.safe))[0];
                    if (!it) return null; const [l, c] = it.cells[0]; const m = document.querySelector('#board').getScreenCTM();
                    const p = new DOMPoint(c - 0.5, (l - 0.5) * S.hr).matrixTransform(m); return [p.x, p.y, it.g.id]; })()""")
                if pt:
                    pg.mouse.click(pt[0], pt[1])
                    pg.wait_for_timeout(500)
                _shot(pg, out, f"sugestoes_{tag}.png")
                pg.click("#tg-sug")      # repõe (o estado fica em localStorage do contexto, que se deita fora)
                ctx.close()
            br.close()
    finally:
        srv.terminate()
        try:
            srv.wait(20)
        except subprocess.TimeoutExpired:
            srv.kill()


def compare(a: str, b: str) -> int:
    import numpy as np
    from PIL import Image
    bad = 0
    for name in sorted(f for f in os.listdir(a) if f.endswith(".png")):
        pb = os.path.join(b, name)
        if not os.path.exists(pb):
            print(f"{name}: falta em {b}")
            bad += 1
            continue
        x = np.asarray(Image.open(os.path.join(a, name)).convert("RGB")).astype(int)
        y = np.asarray(Image.open(pb).convert("RGB")).astype(int)
        if x.shape != y.shape:
            print(f"{name}: tamanhos diferentes {x.shape} vs {y.shape}")
            bad += 1
            continue
        d = np.abs(x - y).max(2)
        n = int((d > 0).sum())
        nb = int((d > NOISE).sum())
        print(f"{name}: {n} píxeis diferentes de {d.size} ({100 * n / d.size:.3f} %), {nb} com diferença > {NOISE}, "
              f"maior diferença {int(d.max())}")
        bad += nb > 0
    return bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("capturar")
    c.add_argument("--project", required=True)
    c.add_argument("--out", required=True)
    k = sp.add_parser("comparar")
    k.add_argument("a")
    k.add_argument("b")
    args = ap.parse_args(argv)
    if args.cmd == "capturar":
        capture(args.project, args.out)
        return 0
    return 1 if compare(args.a, args.b) else 0


if __name__ == "__main__":
    sys.exit(main())
