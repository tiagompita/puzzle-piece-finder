"""Composição a frio do tabuleiro inteiro (ppc 60, a do raster) e de duas regiões de detalhe (ppc 100), com o código de
<repo>, numa cópia <proj>, sem escrever nada. Grava PNG sem perdas em <saída>_{inteiro,ceu,relva}.png e um JSON com
as entradas válidas que o servidor usa.

Uso: python compor.py <repo> <proj> <saída> [--preencher]
--preencher: antes de compor, corre o preenchimento do servidor novo (Gui._fill_placements) e grava o tempo."""
import json
import os
import sys
import time

repo, proj, out = sys.argv[1:4]
sys.path.insert(0, repo)
os.chdir(repo)
import cv2  # noqa: E402
from src import server as S  # noqa: E402
from src import render as R  # noqa: E402

g = S.Gui(proj, prepare=False, use_image=False, log=None, queue=False)
info = {}
if "--preencher" in sys.argv:
	t0 = time.time()
	info["fill"] = dict(g._fill_placements())
	info["fill_s"] = round(time.time() - t0, 2)
pl = g.placements()
info["validas"] = len(pl)
info["colocadas"] = len(R.placed_ids(g.pr))
for name, region, ppc in (("inteiro", None, 60), ("ceu", (1, 20, 14, 40), 100), ("relva", (34, 30, 47, 50), 100)):
	t0 = time.time()
	img = g._compose(ppc, region)
	info[f"{name}_s"] = round(time.time() - t0, 2)
	cv2.imwrite(f"{out}_{name}.png", img)
json.dump(info, open(f"{out}.json", "w"), indent=1, default=str)
print(json.dumps(info, default=str))
g.stop()
