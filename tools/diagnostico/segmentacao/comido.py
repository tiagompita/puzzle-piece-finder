"""Peça «comida» (R0011/R0012): silhuetas contra a máscara manual do Tiago e detetor sem verdade de terreno.

Uso (a partir da raiz do repositório; só lê o projeto)::

	python tools/diagnostico/segmentacao/comido.py --project projects/alpes antigo --copia <cópia do índice de 2026-11-01>
	python tools/diagnostico/segmentacao/comido.py --project projects/alpes gt
	python tools/diagnostico/segmentacao/comido.py --project projects/alpes detetor [--force]
	python tools/diagnostico/segmentacao/comido.py --project projects/alpes alcance

``antigo``: copia de uma cópia antiga do projeto (a de 2026-11-01, anterior ao passo dos contactos S5) os contornos
de P0651/P0657 para ``docs/diagnostico/segmentacao/comido_antigo.npz`` e mede quantas peças mudaram de área entre
essa cópia e o projeto. ``gt``: P0651/P0657 contra ``docs/diagnostico/reports/R0011_R0012_manual/manual_{A,B}_photoshop.png``
(alfa > 127): índice, limpa (``render.clean_crop``), exibida (``render.piece_rgba_for_display`` sem pose), tabuleiro
(``render.compose_board`` 300 dpi com a pose ``register_piece(image=False)``, trazido ao scan pela pose inversa), e o
índice antigo; métricas de ``src.maskcmp``, por lado (N/E/S/W na pose do scan), o que cada regra de exibição tira e
quanto disso é peça (dentro da GT); as miniaturas da GUI do Tiago (``atual_*_gui.png``) contra cada silhueta; as gémeas
P0233/P0234; figura ``COMIDO_gt.jpg``. ``detetor``: os 4 sinais (gémea local, perda de exibição, baía no limiar,
folga local por lado) no conjunto de calibração (positivos: P0651/P0657 antigas, P0218/P0223/P0199 sem
``recover_bays``; controlos: P0156, P0195, P0445 e as 60 peças E-sym A1/A2/B2). ``alcance``: o detetor nas peças do
projeto (fora ``manual_override``), JSON ``comido_resultados.json`` e figura ``COMIDO_alcance.jpg``.

Caches (limiar por folha, segmentações) em ``$PPF_SCRATCH/comido/``. Relatório: docs/diagnostico/segmentacao/COMIDO.md.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import pickle
import sys
from collections import Counter, defaultdict

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

from PIL import Image                                                   # noqa: E402

from src import render as R                                             # noqa: E402
from src import segmentation as SEG                                     # noqa: E402
from src.maskcmp import (best_shift, boundary, crop_union, fill_contour,  # noqa: E402
						 mask_metrics, nearest_side)
from src.overrides import is_manual                                     # noqa: E402
from src.shape import analyse, free_dist                                # noqa: E402
from src.state import Project                                           # noqa: E402

OUT_DIR = os.path.join(ROOT, "docs", "diagnostico", "segmentacao")
GT_DIR = os.path.join(ROOT, "docs", "diagnostico", "reports", "R0011_R0012_manual")
ANTIGO = os.path.join(OUT_DIR, "comido_antigo.npz")
GT_PIECES = (("A", "P0651"), ("B", "P0657"))
TWINS = {"P0651": "P0233", "P0657": "P0234"}
POSITIVOS = (("P0651", "antigo"), ("P0657", "antigo"), ("P0218", "sem_baias"), ("P0223", "sem_baias"), ("P0199", "sem_baias"))
CONTROLOS = ("P0156", "P0195", "P0445")
ESYM_A2 = "images/pieces/colunas5-24_300dpi_rot180_folhaA.jpg"
LIT = ("N", "E")                       # a sombra projeta-se para S e W no scan (verde_tabuleiro.py:90)
NEIGH_EXCL_MM = 1.0                    # baía: fora do que fica a < 1,0 mm de outra peça (zona do corte de contacto)
GUI_PX_PER_MM = 3.35                   # miniatura da GUI capturada: quadrado tracejado de 62 x 60 px = 18,5 x 17,9 mm

# Limiares do detetor (calibrados no conjunto pequeno de `detetor`; justificação em COMIDO.md §5)
T_TWIN_MAX_MM = 1.75                   # (a) máx. da distância ao ponto mais próximo da gémea alinhada (meio de 1,31 / 2,17)
T_DISP_EXTRA_MM = 0.15                 # (b) a exibição tira mais fundo do que a banda + 0,4 mm de sombra + isto (só bolsas o fazem)
T_POCKET_MM2 = 1.0                     # (b) ... e as bolsas somam pelo menos isto (as 6 do índice: 0,04-0,19 mm², grãos)
T_BAY_RIN_MM = 1.2                     # (c) raio inscrito da maior baía no limiar (PRADO: falsas <= 0,96, reais >= 1,34)
T_GAP_MAX_MM = 1.5                     # (d) máx. da folga assinada num lado com vizinha montada


def scratch() -> str:
	base = os.environ.get("PPF_SCRATCH") or r"C:\Users\Tiago\AppData\Local\Temp\claude\5927c0d9acbb3c52\57a98839-c371-4aca-b363-cbdee77bf72f\scratchpad"
	d = os.path.join(base, "comido")
	os.makedirs(d, exist_ok=True)
	return d


def guard(path: str, proj: str) -> str:
	"""Refuse to write inside the project folder."""
	a, b = os.path.abspath(path), os.path.abspath(proj)
	if os.path.commonpath([a, b]) == b:
		raise SystemExit(f"recusado: {path} fica dentro do projeto {proj}")
	return path


def save_jpg(img_rgb: np.ndarray, path: str, proj: str, q: int = 88) -> None:
	Image.fromarray(np.ascontiguousarray(img_rgb)).save(guard(path, proj), quality=q)


# ---------------------------------------------------------------- contexto
class Ctx:
	def __init__(self, proj: str):
		self.proj = proj
		self.pr = Project.open(proj)
		print(R.manual_pose_note(self.pr))   # as poses manuais não entram nas métricas
		self.prof = self.pr.profile
		self.mm = 25.4 / float(self.prof.dpi or 300)
		self.bg = self.prof.background_lab
		self.cell2pid = {tuple(p.celula): p.id for p in self.pr.pieces.values() if p.celula is not None}
		self._rgb = {}
		self._thr = {}
		self._pl = None

	def scan_file(self, sid: str) -> str:
		f = self.pr.model.scans[sid]["file"]
		return f if os.path.isabs(f) else os.path.join(ROOT, f)

	def rgb(self, key: str) -> np.ndarray:
		"""Scan RGB by scan id or by file path (2 kept)."""
		if key not in self._rgb:
			fp = self.scan_file(key) if key in self.pr.model.scans else os.path.join(ROOT, key)
			with Image.open(fp) as im:
				self._rgb[key] = np.asarray(im.convert("RGB"))
			while len(self._rgb) > 2:
				self._rgb.pop(next(iter(self._rgb)))
		return self._rgb[key]

	def thr(self, key: str) -> np.ndarray:
		"""Full-res threshold mask of segment_scan (d > 28, opening 0.42 mm, closing 0.76 mm, paper strip out), bool."""
		if key in self._thr:
			return self._thr[key]
		fp = os.path.join(scratch(), f"thr_{os.path.basename(key)}.npz")
		if os.path.exists(fp):
			with np.load(fp) as z:
				m = np.unpackbits(z["m"])[: int(z["n"])].reshape(tuple(z["shape"])).astype(bool)
		else:
			rgb = self.rgb(key)
			lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
			bg = SEG._rim_background(lab, self.mm)
			op, cp = SEG._odd_kernel(0.42, self.mm), SEG._odd_kernel(0.76, self.mm)
			t = SEG._scan_open_mask(lab, bg, 28.0, op)
			t = cv2.morphologyEx(t, cv2.MORPH_CLOSE, np.ones((cp, cp), np.uint8))
			strip, _ = SEG._frame_strip_mask(lab, t, dilate_px=8)
			if strip is not None:
				t[strip > 0] = 0
				t = cv2.morphologyEx(t, cv2.MORPH_OPEN, np.ones((op, op), np.uint8))
			m = t > 0
			np.savez_compressed(fp, m=np.packbits(m), n=m.size, shape=np.array(m.shape))
		self._thr = {key: m}
		return m

	def sheet_contours(self, sid: str) -> dict:
		"""{pid: contour_px} of every piece of the scan (current index)."""
		return {p.id: self.pr.contour_px(p.id) for p in self.pr.pieces.values()
				if p.scan_id == sid and self.pr.contour_px(p.id) is not None}

	def placements(self) -> dict:
		"""GUI pose (register_piece(image=False)) of every placed piece; cached in scratch per log length."""
		if self._pl is not None:
			return self._pl
		n = len(self.pr.events())
		fp = os.path.join(scratch(), f"placements_{n}.pkl")
		if os.path.exists(fp):
			with open(fp, "rb") as f:
				self._pl = pickle.load(f)
			return self._pl
		pl = {}
		for pid in R.placed_ids(self.pr):
			r = R.register_piece(self.pr, pid, image=False, manual=False)
			if "error" not in r:
				pl[pid] = r
		with open(fp, "wb") as f:
			pickle.dump(pl, f)
		self._pl = pl
		return pl


# ---------------------------------------------------------------- silhuetas (puro)
def crop_of(rgb: np.ndarray, contour, pad: int = 7) -> tuple:
	"""RGBA crop (bbox of the contour + ``pad`` px, clipped) with alpha = filled contour, as the ingest crop; and (x0, y0)."""
	c = np.asarray(contour).reshape(-1, 2).astype(np.int32)
	x, y, w, h = cv2.boundingRect(c)
	H, W = rgb.shape[:2]
	x0, y0, x1, y1 = max(0, x - pad), max(0, y - pad), min(W, x + w + pad), min(H, y + h + pad)
	a = fill_contour(c - [x0, y0], (y1 - y0, x1 - x0))
	rgba = np.dstack([rgb[y0:y1, x0:x1], a.astype(np.uint8) * 255])
	return rgba, (x0, y0)


def display_layers(rgba: np.ndarray, bg, mm: float) -> dict:
	"""Every mask of the display pipeline (render.piece_rgba_for_display without pose), in the crop frame."""
	idx = rgba[..., 3] > 0
	m = R.fringe_masks(rgba, bg, mm, band_mm=R.BAND_MM)
	light = R.is_light(m)
	band = R.BAND_MM
	if light and R.LIGHT_BAND_MM and R.LIGHT_BAND_MM > R.BAND_MM:
		band = min(R.LIGHT_BAND_MM, R.LIGHT_BAND_MAX_MM)
		m = R.fringe_masks(rgba, bg, mm, band_mm=band)
	cl = R.clean_crop(rgba, bg, mm)
	ca = cl[..., 3] > 127
	z = np.zeros_like(idx)
	sh = R.shadow_paper_mask(cl, bg, mm) if R.DISPLAY_SHADOW else z
	pk = R.paper_pocket_mask(cl, bg, mm) if R.PAPER_POCKETS else z
	disp = ca & ~sh & ~pk
	return {"index": idx, "green": m["removed"] & idx, "decont": idx & ~m["removed"] & ~ca, "clean": ca,
			"shadow": sh & ca, "pocket": pk & ca, "display": disp, "light": light, "band_mm": band,
			"thr": m["thr"], "p5": m["p5"], "clean_rgba": cl}


def full(mask_local: np.ndarray, xy, shape) -> np.ndarray:
	out = np.zeros(shape[:2], bool)
	x, y = xy
	h, w = mask_local.shape
	out[y:y + h, x:x + w] = mask_local
	return out


def compass(sh) -> list:
	"""N/E/S/W (scan frame) of each of the 4 sides of a Shape, by the chord midpoint around the corner mean."""
	ctr = sh.c[sh.corners].mean(0)
	out = []
	for s in sh.sides:
		v = 0.5 * (s.p0_mm + s.p1_mm) - ctr
		out.append(("E" if v[0] > 0 else "W") if abs(v[0]) > abs(v[1]) else ("S" if v[1] > 0 else "N"))
	return out


def per_side(diff: np.ndarray, ref: np.ndarray, sh, mm: float) -> dict:
	"""{N/E/S/W: {mm2, depth_mm}} of the pixels of ``diff`` charged to their nearest side; depth = distance to ``ref``."""
	out = {k: {"mm2": 0.0, "depth_mm": 0.0} for k in "NESW"}
	ys, xs = np.nonzero(diff)
	if len(ys) == 0 or sh is None or not sh.ok:
		return out
	lab = nearest_side(np.c_[xs, ys] * mm, sh.c, sh.corners)
	names = compass(sh)
	sl = crop_union(diff, ref, pad=40)
	d = cv2.distanceTransform((~ref[sl]).astype(np.uint8), cv2.DIST_L2, 5)
	dv = d[ys - sl[0].start, xs - sl[1].start] * mm
	for i in range(4):
		k = lab == i
		o = out[names[i]]
		o["mm2"] += float(k.sum()) * mm * mm
		o["depth_mm"] = max(o["depth_mm"], float(dv[k].max()) if k.any() else 0.0)
	return out


def board_silhouette(ctx: Ctx, pid: str, pl: dict, rgba_crop_origin, pad: int = 12) -> np.ndarray:
	"""Alpha (> 0.5) of ``pid`` drawn alone by compose_board at 300 dpi (bleed 0 and default), brought back to the
	scan frame by the inverse pose; returns {bleed0, bleed} full-scan masks."""
	p = ctx.pr.piece(pid)
	l, c = pl["cell"]
	rows, cols = ctx.prof.rows, ctx.prof.cols
	region = (max(1, l - 1), max(1, c - 1), min(rows, l + 1), min(cols, c + 1))
	w_mm, h_mm = float(ctx.prof.cell_mm["w"]), float(ctx.prof.cell_mm["h"])
	ppc = w_mm / ctx.mm
	ppm = ppc / w_mm
	ox, oy = (region[1] - 1) * w_mm * ppm, (region[0] - 1) * h_mm * ppm
	x0, y0, w, h = p.bbox
	out = {}
	for name, bleed in (("bleed0", 0.0), ("bleed", R.BLEED_MM)):
		imgs = [R.compose_board(ctx.pr, ppc, region=region, layers=("pieces",), placements={pid: pl}, piece_ids={pid},
								bleed_mm=bleed, base_bgr=b) for b in ((0, 0, 0), (255, 255, 255))]
		alpha = 1.0 - (imgs[1].astype(np.float32) - imgs[0].astype(np.float32)).mean(2) / 255.0
		A = R._crop_to_out(pl["theta_deg"], pl["pivot_mm"], R.cell_centre_mm(ctx.prof, l, c), (pl["dx_mm"], pl["dy_mm"]),
						   (x0 - pad, y0 - pad), ctx.mm, (ppm, ppm), (ox, oy))
		back = cv2.warpAffine(alpha, A, (w + 2 * pad, h + 2 * pad), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
		out[name] = full(back > 0.5, (x0 - pad, y0 - pad), ctx.rgb(p.scan_id).shape)
	return out


# ---------------------------------------------------------------- sinais do detetor (puro + contexto)
def sig_twin(sh, tsh) -> dict:
	"""(a) local residual against the twin aligned by free_dist: point-to-point |dz| and nearest-point distances (mm)."""
	if sh is None or tsh is None or not sh.ok or not tsh.ok:
		return {}
	rms, s, phi = free_dist(sh, tsh)
	zb = np.roll(tsh.z, -s) * np.exp(1j * np.radians(phi))
	d_pt = np.abs(sh.z - zb)
	d_nn = np.abs(sh.z[:, None] - zb[None, :]).min(1)
	return {"rms": rms, "pt_p95": float(np.percentile(d_pt, 95)), "pt_max": float(d_pt.max()),
			"nn_p95": float(np.percentile(d_nn, 95)), "nn_max": float(d_nn.max())}


def sig_display(L: dict, sh, xy, mm: float) -> dict:
	"""(b) what the display takes off the index: mm2, %, deepest point, largest component, part on the lit sides."""
	idx, rem = L["index"], L["index"] & ~L["display"]
	a = float(idx.sum())
	out = {"mm2": float(rem.sum()) * mm * mm, "pct": 100.0 * float(rem.sum()) / max(1.0, a), "depth_mm": 0.0,
		   "limit_mm": float(L["band_mm"]) + R.DISPLAY_SHADOW_BAND_MM,
		   "comp_mm2": 0.0, "lit_mm2": 0.0, "lit_pct": 0.0, "pocket_mm2": float(L["pocket"].sum()) * mm * mm}
	if not rem.any():
		return out
	dep = R._depth_px(idx) * mm
	out["depth_mm"] = float(dep[rem].max())
	n, lab, st, _ = cv2.connectedComponentsWithStats(rem.astype(np.uint8), connectivity=8)
	out["comp_mm2"] = float(st[1:, cv2.CC_STAT_AREA].max()) * mm * mm
	if sh is not None and sh.ok:
		ys, xs = np.nonzero(rem)
		names = compass(sh)
		side = nearest_side(np.c_[xs + xy[0], ys + xy[1]] * mm, sh.c, sh.corners)
		lit = np.isin(side, [i for i in range(4) if names[i] in LIT])
		out["lit_mm2"] = float(lit.sum()) * mm * mm
		out["lit_pct"] = 100.0 * float(lit.sum()) / max(1.0, a)
	return out


def sig_bay(thr: np.ndarray, contour, others: list, mm: float) -> dict:
	"""(c) threshold pixels connected to the piece, in its own Voronoi cell, outside its contour and >= 1.0 mm from any
	other piece (no opening filter, contact pieces included): total area, largest inscribed radius and its area/depth."""
	c = np.asarray(contour).reshape(-1, 2).astype(np.int32)
	x, y, w, h = cv2.boundingRect(c)
	pad = int(round(4.0 / mm))
	H, W = thr.shape
	x0, y0, x1, y1 = max(0, x - pad), max(0, y - pad), min(W, x + w + pad), min(H, y + h + pad)
	shp = (y1 - y0, x1 - x0)
	me = fill_contour(c - [x0, y0], shp)
	oth = np.zeros(shp, bool)
	for o in others:
		o = np.asarray(o).reshape(-1, 2).astype(np.int32)
		ox, oy, ow, oh = cv2.boundingRect(o)
		if ox > x1 or oy > y1 or ox + ow < x0 or oy + oh < y0:
			continue
		oth |= fill_contour(o - [x0, y0], shp)
	# own Voronoi cell (window): nearer to me than to any other piece
	d_me = cv2.distanceTransform((~me).astype(np.uint8), cv2.DIST_L2, 5)
	d_ot = cv2.distanceTransform((~oth).astype(np.uint8), cv2.DIST_L2, 5) if oth.any() else np.full(shp, 1e9, np.float32)
	cand = thr[y0:y1, x0:x1] & ~me & (d_me <= d_ot) & (d_ot * mm >= NEIGH_EXCL_MM)
	out = {"mm2": 0.0, "rin_mm": 0.0, "rin_mm2": 0.0, "depth_mm": 0.0}
	if not cand.any():
		return out
	n, lab = cv2.connectedComponents(cand.astype(np.uint8), connectivity=8)
	touch = cv2.dilate(me.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool) & cand
	keep = np.unique(lab[touch])
	keep = keep[keep > 0]
	if len(keep) == 0:
		return out
	sel = np.isin(lab, keep)
	out["mm2"] = float(sel.sum()) * mm * mm
	dt = cv2.distanceTransform(np.pad(sel, 1).astype(np.uint8), cv2.DIST_L2, 5)[1:-1, 1:-1]
	best = None
	for k in keep:
		comp = lab == k
		r = float(dt[comp].max())
		if best is None or r > best[0]:
			best = (r, comp)
	out["rin_mm"] = best[0] * mm
	out["rin_mm2"] = float(best[1].sum()) * mm * mm
	out["depth_mm"] = float(d_me[best[1]].max()) * mm
	return out


_EDGE = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}


def sig_gap(ctx: Ctx, pid: str, sh, pls: dict) -> dict:
	"""(d) signed gap (render._signed_gap, mm, + = outside the neighbour) of the points of each side of ``pid`` facing a
	placed neighbour, with the GUI pose; per side p90 and max, and the worst over the sides."""
	pl = pls.get(pid)
	if pl is None or sh is None:
		return {}
	l, c = pl["cell"]
	w, h = float(ctx.prof.cell_mm["w"]), float(ctx.prof.cell_mm["h"])
	A = R.placement_matrix(pl, ctx.prof)
	out = {"sides": {}}
	for d, (dc, dl) in _EDGE.items():
		nb = ctx.cell2pid.get((l + dl, c + dc))
		if nb is None or nb not in pls or nb == pid:
			continue
		nsh = ctx.pr.shape(nb)
		if nsh is None:
			continue
		mid = np.array([(c - 0.5 + 0.5 * dc) * w, (l - 0.5 + 0.5 * dl) * h])
		ed = np.array([1.0, 0.0]) if d in "NS" else np.array([0.0, 1.0])
		half = w / 2 if d in "NS" else h / 2
		q = R._facing_points(sh, A, mid, ed, half)
		if len(q) < 3:
			continue
		poly = R._apply(R.placement_matrix(pls[nb], ctx.prof), nsh.c)
		g = R._signed_gap(q, poly)
		out["sides"][d] = {"p90": float(np.percentile(g, 90)), "max": float(g.max()), "nb": nb}
	if out["sides"]:
		out["p90"] = max(v["p90"] for v in out["sides"].values())
		out["max"] = max(v["max"] for v in out["sides"].values())
	return out


def signals(ctx: Ctx, item: dict, pls: dict) -> dict:
	"""All 4 signals of one silhouette. ``item``: pid, key (scan id or file), contour, others, cell, twin_pid,
	placed (bool), shape_override (re-register with this shape)."""
	mm = ctx.mm
	rgb = ctx.rgb(item["key"])
	contour = np.asarray(item["contour"]).reshape(-1, 2)
	sh = analyse(contour, mm)
	tsh = ctx.pr.shape(item["twin_pid"]) if item.get("twin_pid") else None
	rgba, xy = crop_of(rgb, contour)
	L = display_layers(rgba, ctx.bg, mm)
	out = {"pid": item["pid"], "var": item.get("var", "atual"), "cls": sh.cls if sh.ok else None,
		   "area_mm2": float(L["index"].sum()) * mm * mm, "light": bool(L["light"]),
		   "twin": item.get("twin_pid"), "a": sig_twin(sh, tsh), "b": sig_display(L, sh, xy, mm),
		   "c": sig_bay(ctx.thr(item["key"]), contour, item["others"], mm)}
	if item.get("placed"):
		if item.get("var", "atual") != "atual":
			ctx.pr.shape(item["pid"])                     # make sure the stored shape is cached before swapping it
			saved = ctx.pr._shape_cache[item["pid"]]
			ctx.pr._shape_cache[item["pid"]] = sh
			try:
				pl = R.register_piece(ctx.pr, item["pid"], image=False, manual=False)
			finally:
				ctx.pr._shape_cache[item["pid"]] = saved
			p2 = dict(pls)
			if "error" not in pl:
				p2[item["pid"]] = pl
			out["d"] = sig_gap(ctx, item["pid"], sh, p2)
		else:
			out["d"] = sig_gap(ctx, item["pid"], sh, pls)
	else:
		out["d"] = {}
	return out


def fires(s: dict) -> dict:
	"""Which signals fire (thresholds T_*)."""
	f = {"a": (bool(s["a"]) and s["a"]["nn_max"] > T_TWIN_MAX_MM) or (bool(s.get("twin")) and s["cls"] is None),
		 "b": s["b"]["depth_mm"] > s["b"]["limit_mm"] + T_DISP_EXTRA_MM and s["b"]["pocket_mm2"] >= T_POCKET_MM2,
		 "c": s["c"]["rin_mm"] > T_BAY_RIN_MM,
		 "d": bool(s["d"].get("sides")) and s["d"]["max"] > T_GAP_MAX_MM}
	f["any"] = any(f.values())
	return f


def score(s: dict) -> float:
	v = [s["b"]["depth_mm"] / (s["b"]["limit_mm"] + T_DISP_EXTRA_MM), s["c"]["rin_mm"] / T_BAY_RIN_MM]
	if s["a"]:
		v.append(s["a"]["nn_max"] / T_TWIN_MAX_MM)
	if s["d"].get("sides"):
		v.append(s["d"]["max"] / T_GAP_MAX_MM)
	return float(max(v))


def item_for(ctx: Ctx, pid: str, var: str = "atual", contour=None, sheet=None) -> dict:
	p = ctx.pr.piece(pid)
	sheet = sheet if sheet is not None else ctx.sheet_contours(p.scan_id)
	contour = contour if contour is not None else sheet[pid]
	others = [c for q, c in sheet.items() if q != pid]
	tw = None
	if p.celula is not None:
		tw = ctx.cell2pid.get(tuple(ctx.prof.twin(*p.celula)))
	return {"pid": pid, "var": var, "key": p.scan_id, "contour": contour, "others": others, "twin_pid": tw,
			"placed": p.estado == "colocada"}


# ---------------------------------------------------------------- variantes antigas
def load_antigo() -> dict:
	if not os.path.exists(ANTIGO):
		raise SystemExit(f"falta {ANTIGO}: corre primeiro o subcomando «antigo --copia <cópia de 2026-11-01>»")
	with np.load(ANTIGO) as z:
		return {k.split("__")[0]: z[k] for k in z.files if k.endswith("__contour_px")}


def seg_cached(name: str, path: str, **kw) -> list:
	fp = os.path.join(scratch(), f"seg_{name}.pkl")
	if os.path.exists(fp):
		with open(fp, "rb") as f:
			return pickle.load(f)
	with Image.open(os.path.join(ROOT, path)) as im:
		photo = im.convert("RGB")
	res = SEG.segment_scan(photo, dpi=300, normalize_rotation=False, **kw)
	out = [{"index": int(p["index"]), "contour": np.asarray(p["contour"]).reshape(-1, 2).astype(np.int32),
			"bbox": tuple(int(v) for v in p["bbox"])} for p in res["pieces"]]
	with open(fp, "wb") as f:
		pickle.dump(out, f)
	return out


def positives(ctx: Ctx) -> list:
	old = load_antigo()
	items = []
	s20 = ctx.sheet_contours("S0020")
	for pid in ("P0651", "P0657"):
		sheet = dict(s20)
		sheet.update({q: old[q] for q in ("P0651", "P0657")})
		items.append(item_for(ctx, pid, "antigo", contour=old[pid], sheet=sheet))
	s9 = seg_cached("S0009_sem_baias", ctx.pr.model.scans["S0009"]["file"], recover_bays=False)
	by_idx = {p["index"]: p["contour"] for p in s9}
	cur = ctx.sheet_contours("S0009")
	sheet = {}
	for q in cur:
		sheet[q] = by_idx.get(int(ctx.pr.piece(q).index_in_scan), cur[q])
	for pid in ("P0218", "P0223", "P0199"):
		items.append(item_for(ctx, pid, "sem_baias", contour=sheet[pid], sheet=sheet))
	return items


def controls(ctx: Ctx) -> list:
	items = [item_for(ctx, pid) for pid in CONTROLOS]
	for sid in ("S0001", "S0002"):
		for pid in sorted(q for q, p in ctx.pr.pieces.items() if p.scan_id == sid):
			items.append(item_for(ctx, pid))
	# A2: the A1 pieces turned 180 in place; cell (hence twin) from the nearest A1 piece
	a2 = seg_cached("esym_A2", ESYM_A2)
	a1 = {pid: ctx.pr.contour_px(pid).reshape(-1, 2).mean(0) for pid, p in ctx.pr.pieces.items() if p.scan_id == "S0001"}
	conts = [p["contour"] for p in a2]
	for i, p in enumerate(a2):
		ctr = p["contour"].mean(0)
		q, d = min(((q, float(np.hypot(*(v - ctr)))) for q, v in a1.items()), key=lambda t: t[1])
		cell = ctx.pr.piece(q).celula
		tw = ctx.cell2pid.get(tuple(ctx.prof.twin(*cell))) if cell else None
		items.append({"pid": f"A2#{p['index']}({q})", "var": "esym_A2", "key": ESYM_A2, "contour": p["contour"],
					  "others": [c for j, c in enumerate(conts) if j != i], "twin_pid": tw, "placed": False,
					  "match_mm": d * ctx.mm})
	return items


# ---------------------------------------------------------------- subcomandos
def cmd_antigo(ctx: Ctx, a) -> int:
	cp = a.copia
	if not cp or not os.path.isdir(cp):
		raise SystemExit("--copia <pasta do projeto antigo> obrigatório")
	with np.load(os.path.join(cp, "pieces", "S0020.npz")) as z:
		d = {f"{pid}__contour_px": z[f"{pid}__contour_px"] for pid in ("P0651", "P0657")}
	np.savez_compressed(guard(ANTIGO, ctx.proj), **d)
	print(f"escrito {os.path.relpath(ANTIGO, ROOT)}")
	# how much of the index changed since that copy (by id, same scan)
	rows = []
	for fp in sorted(glob.glob(os.path.join(cp, "scans", "S*.json"))):
		with open(fp, encoding="utf-8") as f:
			sc = json.load(f)
		for p in sc["pieces"]:
			if p["id"] not in ctx.pr.pieces:
				continue
			q = ctx.pr.piece(p["id"])
			if q.scan_id != sc["id"] or not q.area_mm2 or not p.get("area_mm2"):
				continue
			rows.append((p["id"], sc["id"], float(p["area_mm2"]), float(q.area_mm2)))
	ch = [(pid, sid, a0, a1, 100 * (a1 - a0) / a1) for pid, sid, a0, a1 in rows]
	print(f"peças comparadas: {len(ch)}")
	for lim in (1, 3, 5, 10):
		n = sum(1 for r in ch if r[4] > lim)
		print(f"  área antiga menor do que a atual em > {lim} %: {n}")
	by = Counter(r[1] for r in ch if r[4] > 5)
	print("  por folha (> 5 %):", dict(sorted(by.items())))
	for r in sorted(ch, key=lambda r: -r[4])[:25]:
		print(f"    {r[0]} {r[1]} {r[2]:.1f} -> {r[3]:.1f} mm2 ({r[4]:+.1f} %)")
	return 0


def _gui_mask(tag: str) -> np.ndarray:
	im = np.asarray(Image.open(os.path.join(GT_DIR, f"atual_{tag}_gui.png")).convert("RGB"))
	hsv = cv2.cvtColor(im, cv2.COLOR_RGB2HSV)
	pm = (hsv[..., 1] > 60) & (hsv[..., 2] > 25) & ~((hsv[..., 0] < 10) | (hsv[..., 0] > 170))
	n, lab, st, _ = cv2.connectedComponentsWithStats(pm.astype(np.uint8), connectivity=8)
	k = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
	return cv2.morphologyEx((lab == k).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)) > 0


def _gui_iou(gui: np.ndarray, alpha_scan: np.ndarray, mm: float) -> tuple:
	"""Best IoU (rotation +-30 deg, translation) of a scan-resolution silhouette resized to the screenshot scale."""
	g = np.pad(gui, 30)
	s = GUI_PX_PER_MM * mm
	a = cv2.resize(alpha_scan.astype(np.float32), None, fx=s, fy=s, interpolation=cv2.INTER_AREA) > 0.5
	a = np.pad(a, 30).astype(np.uint8)
	gy, gx = np.nonzero(g)
	best = (0.0, 0)
	for th in range(-30, 31):
		M = cv2.getRotationMatrix2D((a.shape[1] / 2, a.shape[0] / 2), th, 1.0)
		ys, xs = np.nonzero(cv2.warpAffine(a, M, (a.shape[1], a.shape[0])))
		for dy in range(-4, 5):
			for dx in range(-4, 5):
				ty, tx = int(round(gy.mean() - ys.mean())) + dy, int(round(gx.mean() - xs.mean())) + dx
				cv = np.zeros_like(g)
				yy, xx = ys + ty, xs + tx
				ok = (yy >= 0) & (yy < g.shape[0]) & (xx >= 0) & (xx < g.shape[1])
				cv[yy[ok], xx[ok]] = True
				iou = float((cv & g).sum()) / max(1, int((cv | g).sum()))
				if iou > best[0]:
					best = (iou, th)
	return best


def _tile(rgb: np.ndarray, sl, scale: float, title: str) -> np.ndarray:
	t = rgb[sl]
	t = cv2.resize(t, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
	t = np.ascontiguousarray(t)
	cv2.rectangle(t, (0, 0), (t.shape[1], 22), (0, 0, 0), -1)
	cv2.putText(t, title, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
	return t


def _diff_img(rgb: np.ndarray, gt: np.ndarray, cand: np.ndarray) -> np.ndarray:
	out = (rgb.astype(np.float32) * 0.55).astype(np.uint8)
	out[gt & cand] = (rgb[gt & cand] * 0.9).astype(np.uint8)
	out[gt & ~cand] = (255, 0, 255)
	out[cand & ~gt] = (0, 255, 255)
	return out


def _alpha_img(rgb: np.ndarray, m: np.ndarray) -> np.ndarray:
	out = np.full_like(rgb, 40)
	out[m] = rgb[m]
	return out


def _contour_img(rgb: np.ndarray, m: np.ndarray, col=(255, 0, 0)) -> np.ndarray:
	out = rgb.copy()
	b = cv2.dilate(boundary(m).astype(np.uint8), np.ones((2, 2), np.uint8)) > 0
	out[b] = col
	return out


def _fmt(m: dict) -> str:
	return (f"IoU {m['iou']:.3f} | área {m['cand_mm2']:.1f} | falta {m['missing_mm2']:.1f} (prof. {m['missing_depth_mm']:.2f}) | "
			f"a mais {m['excess_mm2']:.1f} (prof. {m['excess_depth_mm']:.2f}) | d_p95 {m['d_p95']:.2f} | d_max {m['d_max']:.2f}")


def cmd_gt(ctx: Ctx, a) -> int:
	mm = ctx.mm
	pr = ctx.pr
	old = load_antigo()
	res = {}
	fig_rows = []
	for tag, pid in GT_PIECES:
		p = pr.piece(pid)
		g = np.asarray(Image.open(os.path.join(GT_DIR, f"manual_{tag}_photoshop.png")))
		gt = g[..., 3] > 127
		rgb = ctx.rgb(p.scan_id)
		if g.shape[:2] != rgb.shape[:2]:
			raise SystemExit(f"{tag}: GT {g.shape[:2]} != scan {rgb.shape[:2]}")
		part = (g[..., 3] > 0) & (g[..., 3] < 255)
		perim = int(boundary(gt).sum())
		# registration: GT RGB vs scan RGB at integer shifts (opaque pixels)
		ys, xs = np.nonzero(g[..., 3] == 255)
		rs = np.random.default_rng(0).choice(len(ys), min(4000, len(ys)), replace=False)
		ys, xs = ys[rs], xs[rs]
		reg = min(((float(np.abs(g[ys, xs, :3].astype(int) - rgb[ys + dy, xs + dx].astype(int)).mean()), dx, dy)
				   for dy in range(-3, 4) for dx in range(-3, 4)))
		idx = fill_contour(pr.contour_px(pid), gt.shape)
		crop = pr.crop_rgba(pid)
		x0, y0 = p.bbox[:2]
		crop_idx = full(crop[..., 3] > 0, (x0, y0), gt.shape)
		mine, xy = crop_of(rgb, pr.contour_px(pid))
		same_rgb = bool(np.array_equal(mine[..., :3][mine[..., 3] > 0], crop[..., :3][crop[..., 3] > 0])) and tuple(xy) == (x0, y0)
		L = display_layers(crop, ctx.bg, mm)
		disp_ref = R.piece_rgba_for_display(pr, pid)
		same_disp = bool(np.array_equal(disp_ref[..., 3] > 127, L["display"]))
		sh = analyse(pr.contour_px(pid), mm)
		pl = R.register_piece(pr, pid, image=False, manual=False)
		bs = board_silhouette(ctx, pid, pl, None)
		oidx = fill_contour(old[pid], gt.shape)
		orgba, oxy = crop_of(rgb, old[pid])
		OL = display_layers(orgba, ctx.bg, mm)
		sil = {"indice": idx, "limpa": full(L["clean"], (x0, y0), gt.shape), "exibida": full(L["display"], (x0, y0), gt.shape),
			   "tabuleiro": bs["bleed0"], "tabuleiro_sangria": bs["bleed"],
			   "indice_antigo": oidx, "exibida_antiga": full(OL["display"], oxy, gt.shape)}
		r = {"pid": pid, "cls": p.cls, "cell": p.celula, "gt_mm2": float(gt.sum()) * mm * mm,
			 "orla_px": int(part.sum()), "orla_largura_px": float(part.sum()) / max(1, perim),
			 "registo_rgb": {"dx": reg[1], "dy": reg[2], "dif_media": reg[0]},
			 "best_shift_indice": list(map(float, best_shift(gt, idx, 3))),
			 "crop_igual_contorno": bool(np.array_equal(crop_idx, idx)) and same_rgb, "exibida_igual_render": same_disp,
			 "pose": {k: pl.get(k) for k in ("theta_deg", "method", "rotation")}, "lados": compass(sh), "silhuetas": {}}
		for k, m in sil.items():
			met = mask_metrics(gt, m, mm)
			met["por_lado_falta"] = per_side(gt & ~m, m, sh, mm)
			met["por_lado_a_mais"] = per_side(m & ~gt, gt, sh, mm)
			r["silhuetas"][k] = met
		# what each display rule takes off (crop frame -> scan), and how much of it is piece (inside the GT)
		gtl = gt[y0:y0 + crop.shape[0], x0:x0 + crop.shape[1]]
		a_idx = float(L["index"].sum())
		r["regras"] = {}
		for k in ("green", "decont", "shadow", "pocket"):
			mk = L[k]
			r["regras"][k] = {"mm2": float(mk.sum()) * mm * mm, "pct": 100 * float(mk.sum()) / a_idx,
							  "dentro_gt_mm2": float((mk & gtl).sum()) * mm * mm, "fora_gt_mm2": float((mk & ~gtl).sum()) * mm * mm,
							  "dentro_gt_por_lado": per_side(full(mk & gtl, (x0, y0), gt.shape), ~full(L["index"], (x0, y0), gt.shape), sh, mm)}
		r["light"], r["band_mm"], r["thr"], r["p5"] = bool(L["light"]), L["band_mm"], float(L["thr"]), float(L["p5"])
		# the GUI screenshot vs each silhouette
		gm = _gui_mask(tag)
		r["gui"] = {"mm2": float(gm.sum()) / GUI_PX_PER_MM ** 2}
		for k, m in (("exibida", L["display"]), ("exibida_antiga", OL["display"]), ("indice_antigo", OL["index"])):
			iou, th = _gui_iou(gm, m, mm)
			r["gui"][k] = {"iou": iou, "theta": th, "mm2": float(m.sum()) * mm * mm}
		res[pid] = r
		print(f"\n== {tag} = {pid} {p.celula} {p.cls}: GT {r['gt_mm2']:.1f} mm2, orla {r['orla_px']} px "
			  f"(largura média {r['orla_largura_px']:.2f} px), registo RGB {reg}, best_shift(índice) {r['best_shift_indice']}")
		print(f"   recorte = contorno: {r['crop_igual_contorno']}; exibida = render.piece_rgba_for_display: {same_disp}; "
			  f"pose {r['pose']}; lados {r['lados']}; light {r['light']} banda {r['band_mm']} thr {r['thr']:.1f} p5 {r['p5']:.1f}")
		for k, met in r["silhuetas"].items():
			print(f"   {k:18s} {_fmt(met)}")
			print(f"   {'':18s} falta por lado " + " ".join(f"{s}:{v['mm2']:.1f}/{v['depth_mm']:.2f}" for s, v in met["por_lado_falta"].items())
				  + " | a mais " + " ".join(f"{s}:{v['mm2']:.1f}/{v['depth_mm']:.2f}" for s, v in met["por_lado_a_mais"].items()))
		for k, v in r["regras"].items():
			print(f"   regra {k:7s} {v['mm2']:.2f} mm2 ({v['pct']:.2f} %): dentro da GT {v['dentro_gt_mm2']:.2f}, fora {v['fora_gt_mm2']:.2f}; "
				  "dentro por lado " + " ".join(f"{s}:{x['mm2']:.2f}" for s, x in v["dentro_gt_por_lado"].items()))
		print(f"   GUI (captura) {r['gui']['mm2']:.1f} mm2; IoU com exibida atual {r['gui']['exibida']['iou']:.3f}, "
			  f"exibida antiga {r['gui']['exibida_antiga']['iou']:.3f}, índice antigo {r['gui']['indice_antigo']['iou']:.3f}")
		# figure row
		sl = crop_union(gt, idx, oidx, pad=int(round(3.0 / mm)))
		R_ = rgb
		row = [_tile(R_, sl, 1.0, f"{pid} scan"), _tile(_alpha_img(R_, gt), sl, 1.0, "GT (alfa>127)"),
			   _tile(_contour_img(R_, idx), sl, 1.0, "indice (contorno)"), _tile(_alpha_img(R_, sil["exibida"]), sl, 1.0, "exibida (hoje)"),
			   _tile(_diff_img(R_, gt, sil["exibida"]), sl, 1.0, "exibida vs GT"), _tile(_diff_img(R_, gt, idx), sl, 1.0, "indice vs GT"),
			   _tile(_alpha_img(R_, sil["exibida_antiga"]), sl, 1.0, "exibida antiga (GUI)"), _tile(_diff_img(R_, gt, oidx), sl, 1.0, "ind. antigo vs GT")]
		fig_rows.append(row)
	# twins: no GT; display vs index
	twin_row = []
	for pid, tw in TWINS.items():
		p = pr.piece(tw)
		rgb = ctx.rgb(p.scan_id)
		crop = pr.crop_rgba(tw)
		L = display_layers(crop, ctx.bg, mm)
		sh = analyse(pr.contour_px(tw), mm)
		s = sig_display(L, sh, p.bbox[:2], mm)
		res[tw] = {"pid": tw, "gemea_de": pid, "light": bool(L["light"]), "band_mm": L["band_mm"], "perda": s,
				   "regras_mm2": {k: float(L[k].sum()) * mm * mm for k in ("green", "decont", "shadow", "pocket")},
				   "free_dist_atual": free_dist(analyse(pr.contour_px(pid), mm), sh)[0],
				   "free_dist_antigo": free_dist(analyse(old[pid], mm), sh)[0]}
		print(f"\n== gémea {tw} de {pid}: light {L['light']} banda {L['band_mm']}; exibida tira {s['mm2']:.1f} mm2 ({s['pct']:.2f} %), "
			  f"prof. {s['depth_mm']:.2f} mm, maior comp. {s['comp_mm2']:.2f} mm2, lados iluminados {s['lit_mm2']:.2f} mm2 ({s['lit_pct']:.2f} %); "
			  f"regras {({k: round(v, 2) for k, v in res[tw]['regras_mm2'].items()})}; free_dist à peça atual {res[tw]['free_dist_atual']:.3f}, "
			  f"à antiga {res[tw]['free_dist_antigo']:.3f}")
		idx = fill_contour(pr.contour_px(tw), rgb.shape)
		disp = full(L["display"], p.bbox[:2], rgb.shape)
		sl = crop_union(idx, pad=int(round(3.0 / mm)))
		twin_row += [_tile(_contour_img(rgb, idx), sl, 1.0, f"{tw} indice"), _tile(_alpha_img(rgb, disp), sl, 1.0, f"{tw} exibida"),
					 _tile(_diff_img(rgb, idx, disp), sl, 1.0, "exibida vs indice")]
	fig_rows.append(twin_row)
	# compose figure
	H = max(t.shape[0] for row in fig_rows for t in row)
	lines = []
	for row in fig_rows:
		row = [np.pad(t, ((0, H - t.shape[0]), (0, 4), (0, 0)), constant_values=255) for t in row]
		ln = np.hstack(row)
		lines.append(ln)
	Wd = max(ln.shape[1] for ln in lines)
	fig = np.vstack([np.pad(ln, ((0, 6), (0, Wd - ln.shape[1]), (0, 0)), constant_values=255) for ln in lines])
	save_jpg(fig, os.path.join(OUT_DIR, "COMIDO_gt.jpg"), ctx.proj)
	with open(guard(os.path.join(scratch(), "gt.json"), ctx.proj), "w", encoding="utf-8") as f:
		json.dump(res, f, ensure_ascii=False, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
	print(f"\nfigura {os.path.relpath(os.path.join(OUT_DIR, 'COMIDO_gt.jpg'), ROOT)}")
	return 0


def _row(s: dict) -> str:
	a = s["a"]
	d = s["d"]
	f = fires(s)
	ta = "%.2f / %.2f / %.2f" % (a["rms"], a["nn_p95"], a["nn_max"]) if a else "—"
	td = "%.2f / %.2f" % (d["p90"], d["max"]) if d.get("sides") else "—"
	b, c = s["b"], s["c"]
	return (f"| {s['pid']} | {s['var']} | {s['cls']} | {s['area_mm2']:.1f} | {ta} | "
			f"{b['pct']:.1f} / {b['depth_mm']:.2f} / {b['comp_mm2']:.1f} / {b['lit_pct']:.1f} | "
			f"{c['mm2']:.1f} / {c['rin_mm']:.2f} / {c['depth_mm']:.2f} | {td} | "
			f"{''.join(k for k in 'abcd' if f[k]) or '—'} |")


HEAD = ("| peça | variante | classe | área mm² | (a) gémea RMS / nn p95 / nn máx (mm) | (b) exibição % / prof. mm / maior comp. mm² / "
		"% lados ilum. | (c) baía mm² / r_in mm / prof. mm | (d) folga p90 / máx (mm) | dispara |\n|---|---|---|---|---|---|---|---|---|")


def cmd_detetor(ctx: Ctx, a) -> int:
	fp = os.path.join(scratch(), "detetor.pkl")
	if os.path.exists(fp) and not a.force:
		with open(fp, "rb") as f:
			pos, neg, extra = pickle.load(f)
	else:
		pls = ctx.placements()
		pos = [signals(ctx, it, pls) for it in positives(ctx)]
		neg = [signals(ctx, it, pls) for it in controls(ctx)]
		extra = [signals(ctx, item_for(ctx, pid), pls) for pid in ("P0651", "P0657", "P0218", "P0223", "P0199", "P0233", "P0234")]
		with open(fp, "wb") as f:
			pickle.dump((pos, neg, extra), f)
	print("positivos (silhueta comida)\n" + HEAD)
	for s in pos:
		print(_row(s))
	print("\ncontrolos\n" + HEAD)
	for s in neg:
		print(_row(s))
	print("\nas mesmas peças hoje (fora da calibração)\n" + HEAD)
	for s in extra:
		print(_row(s))
	for k in "abcd":
		tp = sum(fires(s)[k] for s in pos)
		fp_ = sum(fires(s)[k] for s in neg)
		print(f"sinal {k}: {tp}/{len(pos)} positivos, {fp_}/{len(neg)} controlos")
	tp = sum(fires(s)["any"] for s in pos)
	fpn = sum(fires(s)["any"] for s in neg)
	prec = tp / max(1, tp + fpn)
	print(f"detetor (qualquer sinal): recall {tp}/{len(pos)}, falsos {fpn}/{len(neg)}, precisão {prec:.2f}")
	# margins: worst control and weakest positive per signal
	for s in pos + neg:
		s["b"]["over_mm"] = s["b"]["depth_mm"] - s["b"]["limit_mm"]
	for k, key in (("a", "nn_max"), ("b", "over_mm"), ("c", "rin_mm"), ("d", "max")):
		pv = [s[k][key] for s in pos if s[k] and key in s[k]]
		nv = [s[k][key] for s in neg if s[k] and key in s[k]]
		print(f"  {k}.{key}: positivos {sorted(round(v, 2) for v in pv)}; controlos máx {max(nv) if nv else float('nan'):.2f}, "
			  f"p95 {np.percentile(nv, 95) if nv else float('nan'):.2f} (n={len(nv)})")
	return 0


CAMPOS = ("scan", "n", "estado", "cell", "cls", "area_mm2", "twin", "a_rms", "a_nn_max", "b_pct", "b_depth_mm", "b_lit_pct",
		  "b_pocket_mm2", "c_mm2", "c_rin_mm", "c_depth_mm", "d_p90", "d_max", "dispara", "score")


def _short(s: dict, p) -> list:
	"""One compact row (``CAMPOS``) of a piece's signals; None where a signal does not apply."""
	r = lambda v: None if v is None else round(float(v), 2)
	a, b, c, d = s["a"], s["b"], s["c"], s["d"]
	f = fires(s)
	return [p.scan_id, p.n_no_lote, p.estado, list(p.celula) if p.celula else None, s["cls"], r(s["area_mm2"]), s["twin"],
			r(a.get("rms")), r(a.get("nn_max")), r(b["pct"]), r(b["depth_mm"]), r(b["lit_pct"]), r(b["pocket_mm2"]),
			r(c["mm2"]), r(c["rin_mm"]), r(c["depth_mm"]), r(d.get("p90")), r(d.get("max")),
			"".join(k for k in "abcd" if f[k]), r(score(s))]


def cmd_alcance(ctx: Ctx, a) -> int:
	pr = ctx.pr
	fp = os.path.join(scratch(), f"alcance_{len(pr.events())}.pkl")
	if os.path.exists(fp) and not a.force:
		with open(fp, "rb") as f:
			allsig = pickle.load(f)
	else:
		pls = ctx.placements()
		allsig = {}
		by_scan = defaultdict(list)
		for pid, p in pr.pieces.items():
			by_scan[p.scan_id].append(pid)
		for sid in sorted(by_scan):
			sheet = ctx.sheet_contours(sid)
			for pid in sorted(by_scan[sid]):
				p = pr.piece(pid)
				if pid not in sheet or is_manual(p) or p.estado == "descartada":
					continue
				allsig[pid] = signals(ctx, item_for(ctx, pid, sheet=sheet), pls)
			print(f"  {sid}: {len(by_scan[sid])} peças", flush=True)
		with open(fp, "wb") as f:
			pickle.dump(allsig, f)
	excluded = [pid for pid, p in pr.pieces.items() if is_manual(p)]
	out = {"limiares": {"a_nn_max_mm": T_TWIN_MAX_MM, "b_extra_mm": T_DISP_EXTRA_MM, "b_pocket_mm2": T_POCKET_MM2, "c_rin_mm": T_BAY_RIN_MM, "d_gap_max_mm": T_GAP_MAX_MM},
		   "excluidas_manual": excluded, "campos": list(CAMPOS), "pecas": {}}
	F = {}
	for pid, s in allsig.items():
		p = pr.piece(pid)
		out["pecas"][pid] = _short(s, p)
		F[pid] = fires(s)
	print(f"peças avaliadas: {len(allsig)} (fora: {len(excluded)} manual_override, descartadas)")
	n_by = {k: sum(f[k] for f in F.values()) for k in ("a", "b", "c", "d", "any")}
	n_has = {"a": sum(1 for s in allsig.values() if s["a"]), "b": len(allsig), "c": len(allsig),
			 "d": sum(1 for s in allsig.values() if s["d"].get("sides")), "any": len(allsig)}
	print("| sinal | avaliadas | disparam |\n|---|---|---|")
	for k in ("a", "b", "c", "d", "any"):
		print(f"| {k} | {n_has[k]} | {n_by[k]} |")
	for lim in (1.0, 1.2):
		n = sum(1 for s in allsig.values() if s["d"].get("sides") and s["d"]["max"] > lim)
		print(f"(d) com limiar {lim} mm em vez de {T_GAP_MAX_MM}: {n}")
	print("\n| folha | peças | a | b | c | d | total |\n|---|---|---|---|---|---|---|")
	for sid in sorted({pr.piece(q).scan_id for q in allsig}):
		ids = [q for q in allsig if pr.piece(q).scan_id == sid]
		print(f"| {sid} | {len(ids)} | " + " | ".join(str(sum(F[q][k] for q in ids)) for k in ("a", "b", "c", "d", "any")) + " |")
	placed = [q for q in allsig if pr.piece(q).estado == "colocada"]
	rows = Counter(pr.piece(q).celula[0] for q in placed)
	rows_f = Counter(pr.piece(q).celula[0] for q in placed if F[q]["any"])
	cols = Counter(pr.piece(q).celula[1] for q in placed)
	cols_f = Counter(pr.piece(q).celula[1] for q in placed if F[q]["any"])
	print("\ncolocadas por fila (disparam/colocadas): " + ", ".join(f"{l}: {rows_f[l]}/{rows[l]}" for l in sorted(rows)))
	print("colocadas por coluna (disparam/colocadas): " + ", ".join(f"{c}: {cols_f[c]}/{cols[c]}" for c in sorted(cols)))
	print("\nfilas 41–47, colocadas que disparam\n" + HEAD)
	for q in sorted((q for q in placed if pr.piece(q).celula[0] >= 41 and F[q]["any"]), key=lambda q: tuple(pr.piece(q).celula)):
		print(_row(allsig[q]).replace(f"| {q} |", f"| {q} {tuple(pr.piece(q).celula)} |", 1))
	print("\nP0198 (28,64), R0019\n" + HEAD)
	if "P0198" in allsig:
		print(_row(allsig["P0198"]))
	tj = os.path.join(ROOT, "docs", "diagnostico", "reports", "TRIAGEM-2026-11-07.json")
	try:
		with open(tj, encoding="utf-8") as f:
			tri = json.load(f)
		paper = _find_paper(tri)
	except (OSError, ValueError):
		paper = {}
	s20 = sorted((q for q, v in paper.items() if v > 0.05 and q in allsig and pr.piece(q).scan_id == "S0020"))
	print(f"\nS0020 com > 5 % de cor de papel (TRIAGEM §5): {len(s20)}\n" + HEAD)
	for q in s20:
		print(_row(allsig[q]))
	print("\ntodas as que disparam (por pontuação)\n" + HEAD)
	for q in sorted((q for q in allsig if F[q]["any"]), key=lambda q: -score(allsig[q])):
		print(_row(allsig[q]))
	jp = os.path.join(OUT_DIR, "comido_resultados.json")
	with open(guard(jp, ctx.proj), "w", encoding="utf-8", newline="\n") as f:
		json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
	print(f"\nescrito {os.path.relpath(jp, ROOT)}")
	# figure: top 8 by score outside the known positives
	known = {"P0651", "P0657", "P0218", "P0223", "P0199"}
	# the c32|c33 block of rows 1-3 / 45-47 is a known identity/cut exception (ORIENTACOES §D), not segmentation
	blk = lambda q: pr.piece(q).celula is not None and pr.piece(q).celula[1] in (32, 33) and (pr.piece(q).celula[0] <= 3 or pr.piece(q).celula[0] >= 45)
	top = [q for q in sorted(allsig, key=lambda q: -score(allsig[q])) if q not in known and not blk(q)][:8]
	print("pontuação das 8 da figura: " + ", ".join(f"{q} {score(allsig[q]):.2f}" for q in top))
	print("(b) bolsas nas que disparam b: " + ", ".join(f"{q} bolsa {allsig[q]['b']['pocket_mm2']:.2f} mm2 prof {allsig[q]['b']['depth_mm']:.2f} lim {allsig[q]['b']['limit_mm']:.2f}" for q in allsig if F[q]['b']))
	tiles = []
	for q in top:
		p = pr.piece(q)
		rgb = ctx.rgb(p.scan_id)
		c = pr.contour_px(q)
		rgba, xy = crop_of(rgb, c)
		L = display_layers(rgba, ctx.bg, ctx.mm)
		idx = full(L["index"], xy, rgb.shape)
		disp = full(L["display"], xy, rgb.shape)
		sl = crop_union(idx, pad=int(round(3.0 / ctx.mm)))
		f = fires(allsig[q])
		lab = f"{q} {p.scan_id}#{p.n_no_lote} {tuple(p.celula) if p.celula else ''} [{''.join(k for k in 'abcd' if f[k])}]"
		t = np.hstack([_tile(rgb, sl, 1.0, lab), _tile(_contour_img(rgb, idx), sl, 1.0, "indice"),
					   _tile(_diff_img(rgb, idx, disp), sl, 1.0, "exibida vs indice")])
		thr = ctx.thr(p.scan_id)
		bay = thr & ~idx
		tb = _tile(np.where(bay[..., None], np.array([255, 160, 0], np.uint8), rgb), sl, 1.0, "limiar fora do indice")
		tiles.append(np.hstack([t, tb]))
	if tiles:
		Wd = max(t.shape[1] for t in tiles)
		fig = np.vstack([np.pad(t, ((0, 6), (0, Wd - t.shape[1]), (0, 0)), constant_values=255) for t in tiles])
		save_jpg(fig, os.path.join(OUT_DIR, "COMIDO_alcance.jpg"), ctx.proj)
		print(f"figura COMIDO_alcance.jpg: {top}")
	return 0


def _find_paper(tri) -> dict:
	"""{pid: paper_frac} from the TRIAGEM json (any nesting)."""
	out = {}

	def walk(o):
		if isinstance(o, dict):
			pid = o.get("piece") or o.get("pid") or o.get("id")
			if isinstance(pid, str) and pid.startswith("P") and "paper_frac" in o:
				out[pid] = float(o["paper_frac"])
			for k, v in o.items():
				if isinstance(k, str) and k.startswith("P0") and isinstance(v, dict) and "paper_frac" in v:
					out[k] = float(v["paper_frac"])
				walk(v)
		elif isinstance(o, list):
			for v in o:
				walk(v)
	walk(tri)
	return out


def main(argv=None) -> int:
	ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
	ap.add_argument("--project", required=True)
	ap.add_argument("--force", action="store_true")
	sub = ap.add_subparsers(dest="cmd", required=True)
	s = sub.add_parser("antigo")
	s.add_argument("--copia", required=True)
	sub.add_parser("gt")
	sub.add_parser("detetor")
	sub.add_parser("alcance")
	a = ap.parse_args(argv)
	proj = a.project if os.path.isabs(a.project) else os.path.join(ROOT, a.project)
	ctx = Ctx(proj)
	return {"antigo": cmd_antigo, "gt": cmd_gt, "detetor": cmd_detetor, "alcance": cmd_alcance}[a.cmd](ctx, a)


if __name__ == "__main__":
	sys.exit(main())
