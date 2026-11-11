"""Prova estrutural (sem píxeis) de que a GUI antiga não mudou: SVG das camadas do tabuleiro e caixas dos elementos.

Uso::

    python tools/gui/f1_estrutura.py extrair --repo DIR_DO_CHECKOUT --project COPIA_DE_ALPES --out estrutura.json
    python tools/gui/f1_estrutura.py comparar A.json B.json

``extrair`` arranca ``python -m src.server`` a partir de ``--repo`` (um checkout/worktree do commit a medir) sobre
``--project`` (uma CÓPIA de projects/alpes) e, a 1366x768 e a 390x844, passa pelos mesmos 4 estados de
``f1a_capturas.py`` (``inicio``, ``celula``, ``zoom``, ``sugestoes``). Em cada estado guarda:

* ``svg``: o ``outerHTML`` de ``#board`` (todas as camadas), com os números arredondados a 4 casas;
* ``board``: ``getBoundingClientRect`` de ``#board-wrap``, ``#legend-wrap`` e de todos os seus descendentes
  (incluindo os elementos SVG), por caminho ``tag:nth-child`` e arredondado a 0,01 px;
* ``pagina``: o mesmo para todos os elementos de ``body`` (informativo: inclui o painel, cujo texto pode
  depender da hora).

``comparar`` diz, por viewport e estado, quantos elementos foram comparados e lista as diferenças.
"""

import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from screenshot import free_port, wait_ready  # noqa: E402

VIEWPORTS = {"1366": (1366, 768), "390": (390, 844)}

_DUMP = r"""(() => {
    const path = (el) => {
        const out = [];
        for (let e = el; e && e !== document.body; e = e.parentElement) {
            const p = e.parentElement;
            const k = p ? Array.prototype.indexOf.call(p.children, e) + 1 : 1;
            out.push(e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + ':' + k);
        }
        return out.reverse().join('>');
    };
    const box = (el) => { const r = el.getBoundingClientRect();
        return [r.x, r.y, r.width, r.height].map((v) => Math.round(v * 100) / 100); };
    const vis = (el) => { const cs = getComputedStyle(el); return cs.display + '/' + cs.visibility; };
    const take = (els) => { const o = {}; for (const el of els) o[path(el)] = box(el).concat([vis(el)]); return o; };
    const roots = ['#board-wrap', '#legend-wrap'].map((s) => document.querySelector(s)).filter(Boolean);
    const board = [];
    for (const r of roots) { board.push(r); board.push(...r.querySelectorAll('*')); }
    return {
        svg: document.querySelector('#board').outerHTML,
        board: take(board),
        pagina: take(document.body.querySelectorAll('*')),
    };
})()"""

_NUM = re.compile(r"-?\d+\.\d+(?:e-?\d+)?")


def _norm_svg(s: str) -> str:
    return _NUM.sub(lambda m: f"{float(m.group(0)):.4f}".rstrip("0").rstrip("."), s)


def _settle(pg, ms=900):
    try:
        pg.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:  # noqa: BLE001 - o SSE mantém a rede ocupada
        pass
    pg.wait_for_timeout(ms)


def _dump(pg):
    _settle(pg)
    d = pg.evaluate(_DUMP)
    d["svg"] = _norm_svg(d["svg"])
    return d


def extract(repo: str, project: str) -> dict:
    from playwright.sync_api import sync_playwright
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    srv = subprocess.Popen([sys.executable, "-m", "src.server", "--project", project, "--port", str(port), "--no-prepare"],
                           cwd=repo, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    res = {}
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
                vp = res[tag] = {}
                vp["inicio"] = _dump(pg)
                r = pg.evaluate("(() => { const b = document.querySelector('#board').getBoundingClientRect(); return [b.left, b.top, b.width, b.height]; })()")
                pg.mouse.click(r[0] + r[2] * 0.5, r[1] + r[3] * (0.5 if w > 800 else 0.3))
                pg.wait_for_function("S.tab === 'celula' && !!document.querySelector('#tab-celula .cell-head')", timeout=60_000)
                vp["celula"] = _dump(pg)
                pg.evaluate("showTab('buscar'); fitBoard()")
                pg.mouse.move(r[0] + r[2] * 0.3, r[1] + r[3] * 0.25)
                for _ in range(4):
                    pg.mouse.wheel(0, -240)
                    pg.wait_for_timeout(120)
                pg.wait_for_timeout(600)
                if pg.evaluate("pxPerCell() * (window.devicePixelRatio || 1) > S.ppc * 1.1"):
                    pg.wait_for_function("!!document.body.dataset.detail", timeout=120_000)
                vp["zoom"] = _dump(pg)
                pg.evaluate("fitBoard()")
                pg.click("#tg-sug")
                pg.wait_for_timeout(300)
                pt = pg.evaluate("""(() => { const it = suggestionItems().sort((a, b) => Number(b.safe) - Number(a.safe))[0];
                    if (!it) return null; const [l, c] = it.cells[0]; const m = document.querySelector('#board').getScreenCTM();
                    const p = new DOMPoint(c - 0.5, (l - 0.5) * S.hr).matrixTransform(m); return [p.x, p.y, it.g.id]; })()""")
                if pt:
                    pg.mouse.click(pt[0], pt[1])
                    pg.wait_for_timeout(500)
                vp["sugestoes"] = _dump(pg)
                pg.click("#tg-sug")
                ctx.close()
            br.close()
    finally:
        srv.terminate()
        try:
            srv.wait(20)
        except subprocess.TimeoutExpired:
            srv.kill()
    return res


def _diff_boxes(a: dict, b: dict, limit: int = 20):
    ka, kb = set(a), set(b)
    only_a, only_b = sorted(ka - kb), sorted(kb - ka)
    changed = [(k, a[k], b[k]) for k in sorted(ka & kb) if a[k] != b[k]]
    return len(ka | kb), only_a[:limit], only_b[:limit], changed[:limit], len(only_a) + len(only_b) + len(changed)


def compare(pa: str, pb: str) -> int:
    with open(pa, encoding="utf-8") as f:
        A = json.load(f)
    with open(pb, encoding="utf-8") as f:
        B = json.load(f)
    bad = 0
    for vp in sorted(set(A) | set(B)):
        for st in ("inicio", "celula", "zoom", "sugestoes"):
            a, b = A.get(vp, {}).get(st), B.get(vp, {}).get(st)
            if a is None or b is None:
                print(f"{vp} {st}: falta num dos lados")
                bad += 1
                continue
            svg_eq = a["svg"] == b["svg"]
            n_svg = a["svg"].count("<")
            nb, oa, ob, ch, nd = _diff_boxes(a["board"], b["board"])
            npg, _, _, _, ndp = _diff_boxes(a["pagina"], b["pagina"])
            print(f"{vp} {st}: SVG {'igual' if svg_eq else 'DIFERENTE'} ({len(a['svg'])} car., {n_svg} etiquetas); "
                  f"tabuleiro {nb} elementos, {nd} diferenças; página {npg} elementos, {ndp} diferenças (informativo)")
            if not svg_eq:
                i = next(k for k in range(min(len(a["svg"]), len(b["svg"]))) if a["svg"][k] != b["svg"][k]) \
                    if a["svg"][:min(len(a["svg"]), len(b["svg"]))] != b["svg"][:min(len(a["svg"]), len(b["svg"]))] \
                    else min(len(a["svg"]), len(b["svg"]))
                print("   SVG A:", a["svg"][max(0, i - 120):i + 200])
                print("   SVG B:", b["svg"][max(0, i - 120):i + 200])
            for k in oa:
                print("   só em A:", k)
            for k in ob:
                print("   só em B:", k)
            for k, x, y in ch:
                print("   muda:", k, x, "->", y)
            bad += (not svg_eq) + (nd > 0)
    return bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    e = sp.add_parser("extrair")
    e.add_argument("--repo", required=True)
    e.add_argument("--project", required=True)
    e.add_argument("--out", required=True)
    c = sp.add_parser("comparar")
    c.add_argument("a")
    c.add_argument("b")
    args = ap.parse_args(argv)
    if args.cmd == "extrair":
        res = extract(os.path.abspath(args.repo), os.path.abspath(args.project))
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False)
        for vp, sts in res.items():
            print(vp, {k: len(v["board"]) for k, v in sts.items()})
        return 0
    return 1 if compare(args.a, args.b) else 0


if __name__ == "__main__":
    sys.exit(main())
