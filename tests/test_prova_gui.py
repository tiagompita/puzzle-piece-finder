"""``python -m tools.gui.prova`` (levantamento §5, 2026-11-26, «fecho»).

Rápidos: as verificações puras que decidem a falha (ecrã em branco, scroll horizontal, erro de consola, HTTP ≥ 500,
passo que falhou), o ``indice.html`` e que o módulo corre com ``-m``. ``slow``: a prova inteira sobre uma cópia de
``projects/alpes`` (servidor real + Chromium), com as capturas fora do repositório e código 0."""
import json
import os
import subprocess
import sys

import pytest
from PIL import Image

from tools.gui import prova as PV

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_em_branco(tmp_path):
	a = tmp_path / "a.png"
	Image.new("RGB", (40, 30), (250, 250, 250)).save(a)
	assert PV.em_branco(a)
	im = Image.new("RGB", (40, 30), (250, 250, 250))
	im.putpixel((3, 4), (0, 0, 0))
	im.save(a)
	assert not PV.em_branco(a)


def test_scroll_horizontal():
	assert not PV.scroll_horizontal(390, 390)
	assert not PV.scroll_horizontal(391, 390)       # 1 px de arredondamento
	assert PV.scroll_horizontal(420, 390)


def test_falhas_de():
	assert PV.falhas_de({"consola": [], "respostas": [], "scroll": (390, 390), "branco": False}) == []
	f = PV.falhas_de({"consola": ["TypeError: x"], "respostas": [("http://h/api/x", 500), ("http://h/b", 404)],
					  "scroll": (500, 390), "branco": True, "erro": "Timeout"})
	assert len(f) == 5
	assert any("consola: TypeError" in t for t in f) and any("HTTP 500" in t for t in f)
	assert not any("404" in t for t in f)
	assert any("scroll horizontal" in t for t in f) and any("em branco" in t for t in f)
	assert any("passo falhou: Timeout" in t for t in f)


def test_indice_html_tem_as_capturas_e_as_falhas():
	caps = [{"ecra": "montar", "vp": "1366", "png": "montar_1366.png", "segundos": 1.0, "falhas": []},
			{"ecra": "montar", "vp": "390", "png": "montar_390.png", "segundos": 1.0, "falhas": ["HTTP 500: /api/x"]}]
	h = PV.indice_html(caps, "t")
	assert "montar_1366.png" in h and "montar_390.png" in h and "HTTP 500" in h


def test_corre_com_menos_m():
	r = subprocess.run([sys.executable, "-m", "tools.gui.prova", "--help"], cwd=REPO, capture_output=True, text=True,
					   encoding="utf-8", errors="replace")
	assert r.returncode == 0, r.stderr
	assert "--base" in r.stdout


@pytest.mark.slow
def test_prova_inteira_numa_copia(tmp_path):
	if not os.path.isdir(os.path.join(REPO, "projects", "alpes", "pieces")):
		pytest.skip("projects/alpes sem pieces/ (ativos fora do git)")
	pytest.importorskip("playwright")
	out = tmp_path / "prova"
	r = subprocess.run([sys.executable, "-m", "tools.gui.prova", "--out", str(out), "--porto", "8797"], cwd=REPO,
					   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
	assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
	res = json.loads((out / "capturas.json").read_text(encoding="utf-8"))
	assert res["codigo"] == 0 and res["falhas"] == []
	assert {(c["ecra"], c["vp"]) for c in res["capturas"]} == {(e, v) for e in PV.ECRAS for v in PV.VPS}
	assert all((out / c["png"]).exists() for c in res["capturas"])
	assert (out / "indice.html").exists()
