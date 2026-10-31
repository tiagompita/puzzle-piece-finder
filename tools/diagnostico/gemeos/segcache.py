"""Segmentação dos scans dos gémeos (2026-10-30) com cache em .npz (formato de segmentacao_diag.py).

Uso (a partir da raiz do repositório, com PPF_SCRATCH definido):
	python tools/diagnostico/gemeos/segcache.py [--force]
Corre segment_pieces(debug=True) + classify_pieces em A1, A2, B2, B1; grava
$PPF_SCRATCH/seg/gemeos_{A1,A2,B2,B1}.npz e docs/diagnostico/gemeos/gemeos_*__contours.jpg.
Também é importado por esym.py e cortes.py (load_grid, ordenação 4 filas x 5).
"""
import os
import sys
import time

import numpy as np
from PIL import Image, ImageDraw

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools", "diagnostico", "forma"))

S = os.environ.get("PPF_SCRATCH", "scratch")
SEG = os.path.join(S, "seg")
OUT = os.path.join(REPO, "docs", "diagnostico", "gemeos")
PAD = 0  # S1 corrigido em 2026-10-31 (segment_pieces já não descarta peças junto ao bordo); PAD = 64 repõe a moldura antiga
SCANS = {
	"A1": "images/pieces/coluna5-24_300dpi_folhaA.jpg",
	"A2": "images/pieces/colunas5-24_300dpi_rot180_folhaA.jpg",
	"B2": "images/pieces/coluna5-24_folhaB_300dpi_rot180.jpg",
	"B1": "images/pieces/coluna5-24_folhaB_300dpi.jpg",
}


def npz_path(name):
	return os.path.join(SEG, f"gemeos_{name}.npz")


def segment(name, force=False):
	"""Segmenta um scan e grava .npz + overlay; devolve um dict de estatísticas."""
	from src.segmentation import segment_pieces
	from src.edges import classify_pieces
	os.makedirs(SEG, exist_ok=True)
	os.makedirs(OUT, exist_ok=True)
	f = os.path.join(REPO, SCANS[name])
	if os.path.exists(npz_path(name)) and not force:
		d = np.load(npz_path(name), allow_pickle=True)
		return {"name": name, "file": SCANS[name], "count": int(len(d["contours"])),
				"clusters": int(np.sum(d["is_cluster"])), "cached": True}
	im = Image.open(f)
	im.load()
	im = im.convert("RGB")
	# Moldura opcional de PAD px com a cor mediana da orla (contorno do defeito S1, antes de
	# 2026-10-31: o filtro de "toca na moldura" descartava peças a < 1,2 mm do bordo do scan,
	# B2 fila 4, k=4). Contornos e bbox voltam às coordenadas originais.
	if PAD > 0:
		a = np.asarray(im)
		fr = np.concatenate([a[:20].reshape(-1, 3), a[-20:].reshape(-1, 3), a[:, :20].reshape(-1, 3), a[:, -20:].reshape(-1, 3)])
		fill = np.median(fr, axis=0).astype(np.uint8)
		ap = np.empty((a.shape[0] + 2 * PAD, a.shape[1] + 2 * PAD, 3), np.uint8)
		ap[:] = fill
		ap[PAD:-PAD, PAD:-PAD] = a
		im_in = Image.fromarray(ap)
	else:
		im_in = im
	t = time.time()
	res = segment_pieces(im_in, debug=True)
	dt = time.time() - t
	if "error" in res:
		return {"name": name, "file": SCANS[name], "error": res["error"]}
	pieces = res["pieces"]
	for p in pieces:
		x, y, w, h = p["bbox"]
		p["bbox"] = (x - PAD, y - PAD, w, h)
		p["contour"] = np.asarray(p["contour"]).reshape(-1, 2) - PAD
	classify_pieces(pieces)
	for p in pieces:
		if p.get("is_cluster"):
			p["piece_type"] = "cluster"
	# overlay (mesmo estilo de segmentacao_diag.py)
	ann = im.copy()
	d = ImageDraw.Draw(ann)
	W, H = ann.size
	lw = max(2, W // 800)
	colors = {"interior": (0, 200, 0), "edge": (255, 160, 0), "corner": (255, 0, 0), "suspect": (255, 0, 255), "cluster": (0, 0, 0)}
	for p in pieces:
		x, y, w, h = p["bbox"]
		c = colors.get(p["piece_type"], (255, 255, 255))
		d.rectangle([x, y, x + w, y + h], outline=c, width=lw)
		cnt = np.asarray(p["contour"]).reshape(-1, 2)
		if len(cnt) > 2:
			d.line([tuple(map(int, q)) for q in cnt] + [tuple(map(int, cnt[0]))], fill=(255, 255, 0), width=lw)
		d.text((x + 4, y + 4), f"{p['index'] + 1}:{p['piece_type'][:3]}", fill=c)
	ann.thumbnail((1800, 1800))
	ann.save(os.path.join(OUT, f"gemeos_{name}__contours.jpg"), quality=80)
	np.savez_compressed(npz_path(name),
		images=np.array([np.asarray(p["image"].convert("RGB")) for p in pieces], dtype=object),
		masks=np.array([np.asarray(p["mask"]) for p in pieces], dtype=object),
		contours=np.array([np.asarray(p["contour"]).reshape(-1, 2) for p in pieces], dtype=object),
		bboxes=np.array([p["bbox"] for p in pieces]), angles=np.array([p["angle"] for p in pieces]),
		types=np.array([p["piece_type"] for p in pieces]), is_cluster=np.array([p["is_cluster"] for p in pieces]),
		straight=np.array([p["straight_sides"] for p in pieces]),
		sides=np.array([p["sides"] for p in pieces]), devs=np.array([p["side_deviations"] for p in pieces]))
	types = {}
	for p in pieces:
		types[p["piece_type"]] = types.get(p["piece_type"], 0) + 1
	return {"name": name, "file": SCANS[name], "count": int(res["count"]),
			"clusters": int(sum(bool(p["is_cluster"]) for p in pieces)), "types": types,
			"seconds": round(dt, 1), "bg_model": res.get("background_model"),
			"background_lab": [round(float(v), 1) for v in res.get("background_lab", (0, 0, 0))]}


def grid_order(bboxes, cols=5):
	"""Ordena por filas (quebras no y do centro maiores que 0,5 x altura mediana) e por x dentro da fila.
	Devolve lista de (fila, k, índice)."""
	b = np.asarray(bboxes, float)
	cy = b[:, 1] + b[:, 3] / 2
	cx = b[:, 0] + b[:, 2] / 2
	o = np.argsort(cy)
	hmed = np.median(b[:, 3])
	rows, cur = [], [o[0]]
	for i in o[1:]:
		if cy[i] - cy[cur[-1]] > 0.5 * hmed:
			rows.append(cur)
			cur = [i]
		else:
			cur.append(i)
	rows.append(cur)
	out = []
	for f, r in enumerate(rows):
		for k, i in enumerate(sorted(r, key=lambda j: cx[j])):
			out.append((f, k, int(i)))
	return out


def load_grid(name):
	"""Carrega o .npz e devolve as peças (sem cluster) com p['fk'] = (fila, k), pela ordem (f, k)."""
	from shapelib import load
	P = load(npz_path(name))
	g = grid_order([p["bbox"] for p in P])
	out = []
	for f, k, i in g:
		P[i]["fk"] = (f, k)
		out.append(P[i])
	return out


if __name__ == "__main__":
	force = "--force" in sys.argv
	for n in SCANS:
		print(segment(n, force), flush=True)
