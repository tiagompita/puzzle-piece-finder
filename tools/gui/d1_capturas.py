"""Capturas do D-1 (2026-11-25): o Montar aponta para «Grupos soltos» (sem «interface completa»), numa cópia do projeto.

Uso: .venv/Scripts/python.exe tools/gui/d1_capturas.py --base projects/alpes
"""
import argparse
import pathlib
import subprocess
import sys
import tempfile
import time

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "tools" / "diagnostico" / "gui")]
import guarda  # noqa: E402
OUT = REPO / "docs" / "gui" / "screenshots" / "2026-11-25"
VPS = {"1366": (1366, 768), "390": (390, 844)}


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("--base", required=True)
	a = ap.parse_args()
	import gil_intervalo as G
	from playwright.sync_api import sync_playwright
	G.PORT = 8794
	G.BASE_URL = f"http://127.0.0.1:{G.PORT}"
	tmp = pathlib.Path(tempfile.mkdtemp())
	proj = tmp / "proj"
	guarda.copytree(a.base, proj)
	f = open(tmp / "srv.log", "w", encoding="utf-8")
	p = subprocess.Popen([sys.executable, "-m", "src.server", "--project", str(proj), "--port", str(G.PORT),
						  "--uploads", str(tmp / "up"), "--ui", "novo"], cwd=str(REPO), stdout=f, stderr=subprocess.STDOUT)
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
				pg.screenshot(path=str(OUT / f"D_montar_{vp}.png"))
				print(vp, pg.inner_text("#m-grupos") if pg.locator("#m-grupos").count() else "(sem #m-grupos)")
				if pg.locator("#m-ver-grupos").count():
					pg.click("#m-ver-grupos")
					pg.wait_for_selector("#tab-montar [data-vista='grupos']", timeout=10_000)
					pg.wait_for_timeout(1500)
					pg.screenshot(path=str(OUT / f"D_grupos_soltos_{vp}.png"))
				pg.close()
			br.close()
	finally:
		G._stop(p, f)
		time.sleep(1)
		guarda.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
	main()
