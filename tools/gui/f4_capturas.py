"""Capturas da F4 (grupos soltos) que o B4 não fez: o «antes» (``cc68ad4``) e o «depois» dos mesmos ecrãs, numa cópia
de ``projects/alpes`` (nunca o projeto real), servidor real (``python -m src.server``) a partir de ``--repo``.

Ecrãs (``F4_<antes|depois>_<ecra>_<vp>.png``, 1366 × 768 e 390 × 844):
- ``montar``: o ecrã inicial do Montar (antes: «N grupos sem lugar: ver na interface completa»; depois: o comutador
  «Peça a peça | Grupos soltos» e «N em grupos soltos»);
- ``tirar_grupo``: o painel de uma peça de um grupo fixado (o maior), com «Tirar o grupo inteiro do lugar».

As capturas «depois» dos ecrãs novos da F4 (lista, grupo mostrado, mover, fixar, aviso) são do B4.

Uso::

    .venv/Scripts/python.exe tools/gui/f4_capturas.py antes --repo <worktree de cc68ad4> --base <cópia do projeto>
    .venv/Scripts/python.exe tools/gui/f4_capturas.py depois --base <cópia do projeto>
"""
import argparse
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "tools" / "diagnostico" / "gui")]
OUT = REPO / "docs" / "gui" / "screenshots" / "redesenho"
VPS = {"1366": (1366, 768), "390": (390, 844)}


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("prefixo", choices=("antes", "depois"))
	ap.add_argument("--repo", default=str(REPO))
	ap.add_argument("--base", required=True)
	a = ap.parse_args()
	import gil_intervalo as G
	from playwright.sync_api import sync_playwright
	from src.state import Project
	G.PORT = 8793
	G.BASE_URL = f"http://127.0.0.1:{G.PORT}"
	tmp = pathlib.Path(tempfile.mkdtemp())
	proj = tmp / "proj"
	shutil.copytree(a.base, proj)
	pr = Project.open(str(proj))
	fixadas = [s for s in pr.sections.values() if s.anchor.get("anchored")]
	sec = max(sorted(fixadas, key=lambda s: s.id), key=lambda s: len(s.cells_local))
	cell = next(c for pid, c in sorted(((pid, pr.piece(pid).celula) for pid in sec.cells_local)) if c)
	f = open(tmp / "srv.log", "w", encoding="utf-8")
	p = subprocess.Popen([sys.executable, "-m", "src.server", "--project", str(proj), "--port", str(G.PORT),
						  "--uploads", str(tmp / "up"), "--ui", "novo"], cwd=a.repo, stdout=f, stderr=subprocess.STDOUT)
	try:
		G._wait_ready()
		G._wait_holes()
		with sync_playwright() as pw:
			br = pw.chromium.launch()
			for vp, (w, h) in VPS.items():
				pg = br.new_page(viewport={"width": w, "height": h})
				pg.goto(G.BASE_URL + "/novo/")
				pg.wait_for_selector("body[data-ready='1']", timeout=120_000)
				pg.wait_for_timeout(3000)
				pg.screenshot(path=str(OUT / f"F4_{a.prefixo}_montar_{vp}.png"))
				pg.evaluate("([l, c]) => openPainel(l, c)", list(cell))
				pg.wait_for_selector("#p-tirar", timeout=30_000)
				pg.evaluate("([l, c]) => showCell(l, c)", list(cell))
				pg.wait_for_timeout(2500)
				pg.screenshot(path=str(OUT / f"F4_{a.prefixo}_tirar_grupo_{vp}.png"))
				print(vp, sec.id, cell, pg.inner_text("#p-tirar"))
				pg.close()
			br.close()
	finally:
		G._stop(p, f)
		time.sleep(1)
		shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
	main()
