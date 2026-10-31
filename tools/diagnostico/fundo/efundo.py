"""E-fundo: que cor de fundo e que método de contorno dão a fronteira mais consistente (12 scans de julho).

Uso (a partir da raiz do repositório, venv com OpenCV 4.11):
	$env:PPF_SCRATCH = "...\\scratchpad"; $env:PYTHONIOENCODING = "utf-8"
	python tools/diagnostico/fundo/efundo.py            # --cache reutiliza $PPF_SCRATCH/fundo/efundo_scans.pkl
Entrada: images/pieces/digitalização_fundo_{11 cores}.jpg e "digitalizado com impressora.jpg". Os 3 scans a 600 dpi
(rosa, azul_claro, impressora) são reamostrados a 300 dpi (cv2.INTER_AREA, x0,5) ANTES de qualquer método; o dpi
lê-se do cabeçalho JPEG e confere-se com o tamanho (A4).
Métodos (parâmetros fixos para os 12 fundos; fundo estimado pela orla, esym.rim_bg):
	seg     (a) segment_pieces (produto, sem moldura: S1 corrigido em bc124d2)
	simples (b) limiar Lab simples (esym.simple_mask) com separação por segment_pieces + Voronoi, banda 1,5 mm
	sombra  (c) (b) + rejeição da sombra por tonalidade (esym.shadow_mask; TAU_H, KAPPA fixados no verde)
Saída: docs/diagnostico/fundo/results.json, fundo_matriz.png, fundo_overlays_{seg,simples,sombra}.png,
fundo_sombra_mascara.png, fundo_<cor>__contours.jpg (método vencedor); $PPF_SCRATCH/seg/fundo_<cor>.npz.
O método vencedor lê-se do critério M3 do E-sym (docs/diagnostico/gemeos/results.json, chave esym.M3):
correr gemeos/esym.py antes.
"""
import os
import sys
import json
import time
import pickle

import numpy as np
import cv2
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "gemeos"))
import segcache as sc  # noqa: E402  (insere a raiz e tools/diagnostico/forma no sys.path)
import esym  # noqa: E402
from esym import st, r3, prep, free_d, imread_bgr  # noqa: E402
from shapelib import MM, load  # noqa: E402
from cortes import position_gt  # noqa: E402
from dist import free_dist  # noqa: E402

OUT = os.path.join(sc.REPO, "docs", "diagnostico", "fundo")
COLORS = ["verde", "laranja", "azul", "amarelo", "amarelo_claro", "azul_claro", "bege", "preto", "rosa",
		  "verde_claro", "vermelho", "impressora"]
PALE = {"amarelo", "amarelo_claro", "verde_claro"}   # pré-registados: ficam na tabela, não podem ganhar
METHODS = ["seg", "simples", "sombra"]
MCOL = {"seg": (40, 40, 220), "simples": (200, 90, 0), "sombra": (0, 160, 0)}   # BGR: vermelho, azul, verde
N_PHYS = 61          # contado à vista no scan_verde (ver RESULTADOS.md)
PAIR_T = 0.7         # mm: emparelhamento por forma (NN mútuo + classe igual)
POS_TOL = 40         # px: GT por posição (cortes.position_gt)
POSE_DEG = 15.0      # graus: só para o relatório da rotação das peças mexidas (pose_check)
CAL_TAU = [10.0, 12.0, 15.0, 20.0]
CAL_KAPPA = [0.4, 0.5, 0.6]
CAL_FP = 1e-4        # regra: máxima captura de sombra com falsos positivos no interior das peças < 0,01 %

__all__ = ["scan_path", "load_300", "layout_match", "shape_pairing", "calibrate_shadow", "main"]


def scan_path(cor):
	f = "digitalizado com impressora.jpg" if cor == "impressora" else f"digitalização_fundo_{cor}.jpg"
	return os.path.join(sc.REPO, "images", "pieces", f)


def load_300(cor):
	"""BGR a 300 dpi; confere o dpi do cabeçalho com o tamanho (A4 ou enquadramento próximo)."""
	p = scan_path(cor)
	with Image.open(p) as im:
		dpi = im.info.get("dpi")
		W, H = im.size
	assert dpi is not None, p
	dpi = float(dpi[0])
	wmm, hmm = W / dpi * 25.4, H / dpi * 25.4
	assert abs(wmm - 210) < 10 and abs(hmm - 297) < 5, (p, dpi, W, H)
	bgr = imread_bgr(p)
	if abs(dpi - 600) < 1:
		bgr = cv2.resize(bgr, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
	else:
		assert abs(dpi - 300) < 1, (p, dpi)
	return bgr, dict(dpi=dpi, size=[W, H], size_300=[bgr.shape[1], bgr.shape[0]], mm=[round(wmm, 1), round(hmm, 1)])


def npz_path(cor):
	return os.path.join(sc.SEG, f"fundo_{cor}.npz")


def segment(cor, bgr):
	"""segment_pieces a 300 dpi; grava fundo_<cor>.npz no formato de segmentacao_diag.py."""
	from src.segmentation import segment_pieces
	os.makedirs(sc.SEG, exist_ok=True)
	t = time.time()
	res = segment_pieces(Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)))
	dt = time.time() - t
	if "error" in res:
		return dict(error=res["error"])
	pcs = res["pieces"]
	np.savez_compressed(npz_path(cor),
		images=np.array([np.asarray(p["image"].convert("RGB")) for p in pcs], dtype=object),
		masks=np.array([np.asarray(p["mask"]) for p in pcs], dtype=object),
		contours=np.array([np.asarray(p["contour"]).reshape(-1, 2) for p in pcs], dtype=object),
		bboxes=np.array([p["bbox"] for p in pcs]), angles=np.array([p["angle"] for p in pcs]),
		types=np.array(["-"] * len(pcs)), is_cluster=np.array([p["is_cluster"] for p in pcs]),
		straight=np.array([-1] * len(pcs)), touches_frame=np.array([bool(p.get("touches_frame", False)) for p in pcs]))
	return dict(count=int(res["count"]), clusters=int(sum(bool(p["is_cluster"]) for p in pcs)),
				touches_frame=int(sum(bool(p.get("touches_frame", False)) for p in pcs)), seconds=round(dt, 1),
				background_lab=[round(float(v), 1) for v in res.get("background_lab", (0, 0, 0))])


def bg_info(bg):
	ab = np.asarray(bg[1:], float) - 128
	return dict(lab_cv8=[round(float(v), 1) for v in bg], L=round(float(bg[0]) * 100 / 255, 1), a=round(float(ab[0]), 1),
				b=round(float(ab[1]), 1), C=round(float(np.hypot(*ab)), 1), h_deg=round(float(np.degrees(np.arctan2(ab[1], ab[0]))), 1),
				achromatic=bool(np.hypot(*ab) < esym.C_ACH))


def centres(P):
	return np.array([np.asarray(p["bbox"][:2], float) + np.asarray(p["bbox"][2:], float) / 2 for p in P])


def layout_match(PA, PB):
	"""GT por posição tolerante a uma translação da folha: moda 2D (bins de 20 px) dos deslocamentos entre todos os
	centros, refinada pela mediana; depois cortes.position_gt(tol=40). Devolve (pares (iA, jB), shift, fração)."""
	cA, cB = centres(PA), centres(PB)
	off = (cB[None] - cA[:, None]).reshape(-1, 2)
	q = np.round(off / 20).astype(int)
	keys, cnt = np.unique(q, axis=0, return_counts=True)
	m = keys[np.argmax(cnt)] * 20.0
	for _ in range(3):
		near = off[np.linalg.norm(off - m, axis=1) < POS_TOL]
		if len(near):
			m = np.median(near, axis=0)
	PBs = [dict(bbox=np.r_[np.asarray(p["bbox"][:2], float) - m, np.asarray(p["bbox"][2:], float)]) for p in PB]
	pairs = position_gt(PA, PBs, tol=POS_TOL)
	return pairs, m, len(pairs) / max(1, min(len(PA), len(PB)))


def shape_pairing(PV, PX):
	"""NN mútuo em RMS free entre peças ok de PV (verde) e PX, aceite se < PAIR_T mm e classe igual. -> [(i, j, d)]."""
	iv = [i for i, p in enumerate(PV) if p is not None]
	ix = [j for j, p in enumerate(PX) if p is not None]
	if not iv or not ix:
		return []
	M = np.array([[free_d(PV[i], PX[j]) for j in ix] for i in iv])
	a, b = M.argmin(1), M.argmin(0)
	out = []
	for r, i in enumerate(iv):
		c = a[r]
		if b[c] == r and M[r, c] < PAIR_T and PV[i]["cls"] == PX[ix[c]]["cls"]:
			out.append((i, ix[c], float(M[r, c])))
	return out


def calibrate_shadow(bgr, segP, bg):
	"""Candidatos a sombra = limiar simples fora da máscara segment_pieces dilatada (5x5) e a < 1,5 mm do contorno;
	interior = máscara segment_pieces erodida (11x11). Grelha (tau_h, kappa) do plano; devolve a tabela."""
	H, W = bgr.shape[:2]
	seg = np.zeros((H, W), np.uint8)
	for p in segP:
		cv2.fillPoly(seg, [np.round(p["contour"]).astype(np.int32).reshape(-1, 1, 2)], 255)
	lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
	d = np.sqrt(((lab - bg) ** 2 * np.array([0.5, 1, 1])).sum(-1))
	dil = cv2.dilate(seg, np.ones((5, 5), np.uint8)) > 0
	dist = cv2.distanceTransform((seg == 0).astype(np.uint8), cv2.DIST_L2, 5)
	cand = (d > 28) & ~dil & (dist < 1.5 / MM)
	inner = cv2.erode(seg, np.ones((11, 11), np.uint8)) > 0
	rows = []
	for t in CAL_TAU:
		for k in CAL_KAPPA:
			sm = esym.shadow_mask(bgr, bg, t, k)
			rows.append(dict(tau_h=t, kappa=k, shadow_captured=r3(sm[cand].mean()), interior_fp_pct=round(float(sm[inner].mean()) * 100, 4)))
	ok = [r for r in rows if r["interior_fp_pct"] < CAL_FP * 100]
	best = max(ok, key=lambda r: (r["shadow_captured"], -r["interior_fp_pct"]))
	Lc = lab[..., 0][cand] * 100 / 255
	return dict(n_candidates=int(cand.sum()), n_interior=int(inner.sum()), grid=rows, chosen=best,
				candidates_L_pct=dict(zip(["p5", "p25", "p50", "p75", "p95"], [r3(v) for v in np.percentile(Lc, [5, 25, 50, 75, 95])])),
				candidates_L_lt_15_frac=r3(np.mean(Lc < 15)),
				rule=f"máximo de captura com FP no interior < {CAL_FP * 100:.2f} %; tau_h em {CAL_TAU}, kappa em {CAL_KAPPA}")


def build_identity(D, L, ref):
	"""Identidade (id = índice no verde) de cada peça de cada scan, a partir da referência ref (verde ou laranja):
	GT por posição contra ref (translação da folha + position_gt) e, para as restantes, forma contra ref (NN mútuo
	< PAIR_T e classe igual, união dos 3 métodos, conflitos descartados). Devolve {cor: (idmap {j: id}, how {j: str})}."""
	if ref == "verde":
		to_v = {j: j for j in range(len(D["verde"]["segP"]))}
	else:
		to_v = {j: i for i, j in L[("verde", ref)]["pairs"]}
	out = {}
	for cor in COLORS:
		if cor == ref:
			out[cor] = ({j: to_v[j] for j in to_v}, {j: "identidade" for j in to_v})
			continue
		idm, how, used = {}, {}, set()
		for i, j in sorted(L[(ref, cor)]["pairs"], key=lambda t: t[1]):
			if i in to_v and i not in used and j not in idm:
				idm[j], how[j] = i, "posição"
				used.add(i)
		votes = {}
		for m in METHODS:
			PRr = [q if (i in to_v and i not in used) else None for i, q in enumerate(D[ref]["P"][m])]
			PXr = [q if j not in idm else None for j, q in enumerate(D[cor]["P"][m])]
			for i, j, _ in shape_pairing(PRr, PXr):
				votes.setdefault(j, set()).add(i)
		byi = {}
		for j, sv in votes.items():
			if len(sv) == 1:
				byi.setdefault(next(iter(sv)), []).append(j)
		for i, js in byi.items():
			if len(js) == 1:
				idm[js[0]], how[js[0]] = i, "forma"
		out[cor] = ({j: to_v[i] for j, i in idm.items()}, how)
	return out


def contour_area_mm2(p):
	return float(cv2.contourArea(np.asarray(p["contour"], np.float32).reshape(-1, 1, 2))) * MM * MM


def pure_components(mask, med_area):
	"""Componentes do limiar puro (sem separação) com área 0,6-1,5 x mediana das peças de segment_pieces."""
	n, _, stt, _ = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8), connectivity=8)
	a = stt[1:, cv2.CC_STAT_AREA]
	return dict(components=int(np.sum(a > 0.25 * med_area)), single_sized=int(np.sum((a > 0.6 * med_area) & (a < 1.5 * med_area))))


# ---------------------------------------------------------------- figuras
def save_png(path, bgr):
	"""PNG com paleta de 256 cores (as figuras fotográficas ficam ~3x mais pequenas)."""
	Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)).quantize(256, method=Image.Quantize.MEDIANCUT).save(path, optimize=True)


def put(img, t, xy, s=0.45, c=(0, 0, 0), th=1):
	cv2.putText(img, t, xy, cv2.FONT_HERSHEY_SIMPLEX, s, c, th, cv2.LINE_AA)


def heat(v, vmin=0.2, vmax=1.5):
	x = 1 - (min(max(v, vmin), vmax) - vmin) / (vmax - vmin)
	return cv2.applyColorMap(np.uint8([[255 * x]]), cv2.COLORMAP_VIRIDIS)[0, 0].tolist()


def fig_matrix(R, fname):
	cw, ch, x0, y0 = 120, 34, 130, 70
	panels = []
	for key, title in [("diff_pose", "pose diferente"), ("same_pose", "mesma pose"), ("good_diff_pose", "pose dif., parceiros nao palidos"), ("vs_verde", "so contra o verde")]:
		W, H = x0 + cw * 3 + 10, y0 + ch * len(COLORS) + 40
		img = np.full((H, W, 3), 255, np.uint8)
		put(img, f"RMS free mediano (mm), {title}", (8, 22), 0.55)
		put(img, "[n pares]  cor: 0,2 (amarelo) .. >=1,5 (violeta)", (8, 44), 0.42)
		for j, m in enumerate(METHODS):
			put(img, m, (x0 + j * cw + 30, y0 - 6), 0.5)
		for i, cor in enumerate(COLORS):
			put(img, cor + (" *" if cor in PALE else ""), (6, y0 + i * ch + 22), 0.45)
			for j, m in enumerate(METHODS):
				c = R["per"][cor][m]["consistency"][key]
				x, y = x0 + j * cw, y0 + i * ch
				if c.get("n", 0) == 0:
					cv2.rectangle(img, (x, y), (x + cw - 2, y + ch - 2), (220, 220, 220), -1)
					put(img, "-", (x + 50, y + 22), 0.5)
					continue
				col = heat(c["median"])
				cv2.rectangle(img, (x, y), (x + cw - 2, y + ch - 2), col, -1)
				put(img, f"{c['median']:.2f} [{c['n']}]", (x + 8, y + 22), 0.48, (255, 255, 255) if c["median"] > 0.8 else (0, 0, 0))
		put(img, "* fundo palido (nao pode ganhar)", (8, H - 12), 0.42)
		panels.append(img)
	H = max(p.shape[0] for p in panels)
	cv2.imwrite(os.path.join(OUT, fname), np.hstack([np.vstack([p, np.full((H - p.shape[0], p.shape[1], 3), 255, np.uint8)]) for p in panels]))


def tile_piece(bgr, pcs, focus, T=260):
	"""Recorte a 2x da metade inferior-esquerda (lado da sombra) da peça; contornos dos 3 métodos."""
	x, y, w, h = map(int, pcs["seg"]["bbox"])
	x0, y0 = max(0, x - 14), max(0, y + int(0.45 * h))
	x1, y1 = min(bgr.shape[1], x + int(0.55 * w)), min(bgr.shape[0], y + h + 14)
	s = 2
	crop = cv2.resize(bgr[y0:y1, x0:x1], None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
	for m in METHODS:
		p = pcs.get(m)
		if p is None:
			continue
		q = np.round((p["contour"] - [x0, y0]) * s + s / 2).astype(np.int32).reshape(-1, 1, 2)
		cv2.polylines(crop, [q], True, MCOL[m], 2 if m == focus else 1, cv2.LINE_AA)
	t = np.full((T, T, 3), 255, np.uint8)
	hh, ww = min(T, crop.shape[0]), min(T, crop.shape[1])
	t[:hh, :ww] = crop[:hh, :ww]
	return t


def fig_overlays(D, picks, focus, fname):
	T = 260
	rows = []
	for cor in COLORS:
		bgr = D[cor]["bgr"]
		inv = {v: k for k, v in D[cor]["idmap"].items()}
		tiles = []
		for vid in picks:
			j = inv.get(vid)
			if j is None:
				t = np.full((T, T, 3), 225, np.uint8)
				put(t, "nao emparelhada", (40, T // 2), 0.5)
			else:
				pcs = {m: D[cor]["P"][m][j] for m in METHODS}
				pcs["seg"] = pcs["seg"] or D[cor]["segP"][j]
				t = tile_piece(bgr, pcs, focus, T)
			cv2.rectangle(t, (0, 0), (T - 1, T - 1), (150, 150, 150), 1)
			tiles.append(t)
		lab = np.full((T, 110, 3), 255, np.uint8)
		put(lab, cor, (4, T // 2), 0.5)
		rows.append(np.hstack([lab] + tiles))
	head = np.full((50, rows[0].shape[1], 3), 255, np.uint8)
	put(head, f"Mesmas 6 pecas (ids do verde {picks}) nos 12 fundos, 2x, lado da sombra (inferior-esquerdo). "
			  f"seg vermelho, simples azul, sombra verde; traco grosso = {focus}", (8, 20), 0.5)
	put(head, "pecas sem identidade nesse fundo: cinzento.", (8, 42), 0.45)
	save_png(os.path.join(OUT, fname), np.vstack([head] + rows))


def fig_shadow(D, cors, vid_by_cor, fname):
	panels = []
	for cor in cors:
		bgr, bg = D[cor]["bgr"], D[cor]["bg"]
		j = vid_by_cor[cor]
		x, y, w, h = map(int, D[cor]["segP"][j]["bbox"])
		x0, y0, x1, y1 = max(0, x - 30), max(0, y - 30), min(bgr.shape[1], x + w + 30), min(bgr.shape[0], y + h + 30)
		crop = bgr[y0:y1, x0:x1]
		sm = esym.shadow_mask(crop, bg)
		over = crop.copy()
		if sm is not None:
			lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).astype(np.float32)
			fg = np.sqrt(((lab - bg) ** 2 * np.array([0.5, 1, 1])).sum(-1)) > 28
			over[sm & fg] = (255, 0, 255)          # só os píxeis que o limiar daria como peça e a sombra rejeita
		p = D[cor]["P"]["sombra"][j]
		if p is not None:
			cv2.polylines(over, [np.round(p["contour"] - [x0, y0]).astype(np.int32).reshape(-1, 1, 2)], True, (0, 160, 0), 1, cv2.LINE_AA)
		pair = np.hstack([crop, over])
		pair = cv2.resize(pair, None, fx=1.25, fy=1.25, interpolation=cv2.INTER_CUBIC)
		top = np.full((26, pair.shape[1], 3), 255, np.uint8)
		info = bg_info(bg)
		put(top, f"{cor}: fundo L{info['L']} C{info['C']} h{info['h_deg']}; magenta = rejeitado como sombra (limiar d>28 E modelo de sombra; tau_h {esym.TAU_H}, kappa {esym.KAPPA})"
				 + ("  [acromatico: nao se aplica]" if sm is None else ""), (6, 18), 0.48)
		panels.append(np.vstack([top, pair]))
	Wm = max(p.shape[1] for p in panels)
	panels = [np.hstack([p, np.full((p.shape[0], Wm - p.shape[1], 3), 255, np.uint8)]) for p in panels]
	save_png(os.path.join(OUT, fname), np.vstack(panels))


def fig_contours(cor, D, m, fname):
	bgr = D[cor]["bgr"].copy()
	for j, p in enumerate(D[cor]["P"][m]):
		sp = D[cor]["segP"][j]
		x, y = int(sp["bbox"][0]), int(sp["bbox"][1])
		if p is None:
			cv2.polylines(bgr, [np.round(sp["contour"]).astype(np.int32).reshape(-1, 1, 2)], True, (255, 0, 255), 3)
		else:
			cv2.polylines(bgr, [np.round(p["contour"]).astype(np.int32).reshape(-1, 1, 2)], True, (0, 0, 255), 3)
		vid = D[cor]["idmap"].get(j)
		put(bgr, str(vid) if vid is not None else "?", (x + 10, y + 40), 1.4, (0, 0, 0), 3)
	small = cv2.resize(bgr, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
	put(small, f"{cor}: contorno {m} (vermelho); magenta = sem contorno/cantos; numero = id no verde, ? = sem identidade", (10, 30), 0.8, (0, 0, 0), 2)
	cv2.imwrite(os.path.join(OUT, fname), small, [cv2.IMWRITE_JPEG_QUALITY, 85])


# ---------------------------------------------------------------- principal
def main():
	t0 = time.time()
	os.makedirs(OUT, exist_ok=True)
	D, R = {}, {"N_phys": N_PHYS, "methods": {"seg": "(a) segment_pieces", "simples": "(b) limiar simples + Voronoi segment_pieces, banda 1,5 mm",
											   "sombra": "(c) (b) + rejeição da sombra por tonalidade"},
			   "shadow_params": dict(tau_h=esym.TAU_H, kappa=esym.KAPPA, C_ach=esym.C_ACH), "scans": {}, "per": {}}
	cache = os.path.join(sc.S, "fundo", "efundo_scans.pkl")
	if "--cache" in sys.argv and os.path.exists(cache):
		D, R["scans"] = pickle.load(open(cache, "rb"))
		for cor in COLORS:
			D[cor]["bgr"] = load_300(cor)[0]
	for cor in [c for c in COLORS if c not in D]:
		t = time.time()
		bgr, info = load_300(cor)
		bg = esym.rim_bg(bgr)
		info.update(segment(cor, bgr), background=bg_info(bg))
		segP = load(npz_path(cor))
		for p in segP:
			p.pop("image", None)
		sm_b = esym.simple_mask(bgr, bg=bg)
		shm = esym.shadow_mask(bgr, bg)
		sm_c = esym.simple_mask(bgr, bg=bg, shadow=shm) if shm is not None else sm_b
		med = float(np.median([cv2.contourArea(np.asarray(p["contour"], np.float32).reshape(-1, 1, 2)) for p in segP]))
		info["pure_threshold"] = dict(simples=pure_components(sm_b, med), sombra=pure_components(sm_c, med))
		info["shadow_frac_of_image"] = r3(shm.mean()) if shm is not None else None
		P = {"seg": [dict(p) for p in segP],
			 "simples": esym.hybrid_pieces(bgr, segP, mask=sm_b),
			 "sombra": esym.hybrid_pieces(bgr, segP, mask=sm_c)}
		for m in METHODS:
			P[m] = [None if (p.get("contour") is None or len(p["contour"]) < 50) else p for p in P[m]]
			prep([p for p in P[m] if p is not None])
			P[m] = [p if (p is not None and p["ok"]) else None for p in P[m]]
		info["n_ok"] = {m: int(sum(p is not None for p in P[m])) for m in METHODS}
		info["seconds_total"] = round(time.time() - t, 1)
		D[cor] = dict(bgr=bgr, bg=bg, segP=segP, P=P)
		R["scans"][cor] = info
		print(cor, info["count"], info["clusters"], info["n_ok"], info["background"]["C"], info["seconds_total"], "s", flush=True)
	os.makedirs(os.path.dirname(cache), exist_ok=True)
	pickle.dump(({c: {k: v for k, v in D[c].items() if k != "bgr"} for c in D}, R["scans"]), open(cache, "wb"))
	# --- calibração da sombra (só verde) e verificação de que as constantes do esym são as escolhidas
	cal = calibrate_shadow(D["verde"]["bgr"], D["verde"]["segP"], D["verde"]["bg"])
	R["shadow_calibration_verde"] = cal
	assert (cal["chosen"]["tau_h"], cal["chosen"]["kappa"]) == (esym.TAU_H, esym.KAPPA), cal["chosen"]
	# --- identidade da peça (via verde): GT por posição (translação da folha + position_gt) e, para as restantes,
	# forma (NN mútuo < 0,7 mm e classe igual, união dos 3 métodos, conflitos descartados)
	L = {}
	for a in COLORS:
		for b in COLORS:
			if a < b:
				pr, sh, fr = layout_match(D[a]["segP"], D[b]["segP"])
				L[(a, b)] = dict(pairs=pr, shift=sh, frac=fr)                                 # (i em a, j em b)
				L[(b, a)] = dict(pairs=[(j, i) for i, j in pr], shift=-sh, frac=fr)
	R["layout"] = {f"{a}|{b}": dict(frac_position_matched=r3(L[(a, b)]["frac"]), shift_px=[round(float(v), 1) for v in L[(a, b)]["shift"]])
				   for a in COLORS for b in COLORS if a < b}
	ID = {ref: build_identity(D, L, ref) for ref in ("verde", "laranja")}
	for cor in COLORS:
		D[cor]["idmap"], D[cor]["idhow"] = ID["verde"][cor]
		R["scans"][cor]["identity"] = dict(n_paired=len(D[cor]["idmap"]), by_position=sum(v == "posição" for v in D[cor]["idhow"].values()),
										   by_shape=sum(v == "forma" for v in D[cor]["idhow"].values()),
										   n_paired_ref_laranja=len(ID["laranja"][cor][0]), position_frac_vs_verde=r3(L[("verde", cor)]["frac"]) if cor != "verde" else 1.0)
	# --- métricas por fundo x método. Pose por par de observações (X, j) / (Y, k): mesma pose se a peça está no
	# mesmo sítio nos dois scans depois da translação da folha (|c_Y - (c_X + shift)| < POS_TOL: peça não mexida);
	# senão pose diferente (peça mexida; a rotação relativa medida está em pose_check_rotation_deg_vs_verde).
	cen = {c: centres(D[c]["segP"]) for c in COLORS}

	def same_pose(a, j, b, k):
		if L[(a, b)]["frac"] < 0.3:      # sem layout comum (deslocamento espúrio): peças mexidas
			return False
		return bool(np.linalg.norm(cen[b][k] - (cen[a][j] + L[(a, b)]["shift"])) < POS_TOL)
	area = {m: {} for m in METHODS}   # vid -> {cor: mm2}
	for m in METHODS:
		for cor in COLORS:
			for j, vid in D[cor]["idmap"].items():
				p = D[cor]["P"][m][j]
				if p is not None:
					area[m].setdefault(vid, {})[cor] = contour_area_mm2(p)
	pose_check = {"posição": [], "forma": []}
	for cor in COLORS:
		if cor == "verde":
			continue
		for j, vid in D[cor]["idmap"].items():
			a, b = D["verde"]["P"]["simples"][vid], D[cor]["P"]["simples"][j]
			if a is not None and b is not None:
				pose_check[D[cor]["idhow"][j]].append(abs((np.degrees(free_dist(a, b)[2]) + 180) % 360 - 180))
	R["pose_check_rotation_deg_vs_verde"] = {k: dict(st(v), n_lt_pose_deg=int(np.sum(np.array(v) < POSE_DEG))) for k, v in pose_check.items()}
	for cor in COLORS:
		R["per"][cor] = {}
		for m in METHODS:
			PX = D[cor]["P"][m]
			ok = [p for p in PX if p is not None]
			acc = {k: [] for k in ["same_pose", "diff_pose", "vs_verde", "good_same_pose", "good_diff_pose"]}
			ref = "laranja" if cor == "verde" else "verde"   # a identidade nunca é escolhida com o contorno do próprio X de referência
			inv_x = {v: k for k, v in ID[ref][cor][0].items()}
			for other in COLORS:
				if other == cor:
					continue
				inv_y = {v: k for k, v in ID[ref][other][0].items()}
				for vid in set(inv_x) & set(inv_y):
					a, b = PX[inv_x[vid]], D[other]["P"][m][inv_y[vid]]
					if a is None or b is None:
						continue
					d = free_d(a, b)
					same = same_pose(cor, inv_x[vid], other, inv_y[vid])
					acc["same_pose" if same else "diff_pose"].append(d)
					if other not in PALE:
						acc["good_same_pose" if same else "good_diff_pose"].append(d)
					if other == "verde":
						acc["vs_verde"].append(d)
			paired_ok = sum(1 for j in D[cor]["idmap"] if PX[j] is not None)
			rel = [100 * (area[m][v][cor] / area[m][v]["verde"] - 1) for v in area[m] if cor in area[m][v] and "verde" in area[m][v]]
			R["per"][cor][m] = dict(
				identity_reference=ref,
				consistency={k: st(v) for k, v in acc.items()},
				recall=dict(paired_ok=paired_ok, paired_ok_frac=r3(paired_ok / N_PHYS),
							detected_noncluster=R["scans"][cor]["count"] - R["scans"][cor]["clusters"],
							detected_frac=r3((R["scans"][cor]["count"] - R["scans"][cor]["clusters"]) / N_PHYS),
							ok_contours=len(ok)),
				roughness=st([p["rough"] for p in ok]),
				side_chord_mm=st([l for p in ok for l in p["lens"]]),
				area_mm2=st([contour_area_mm2(p) for p in ok]),
				area_rel_vs_verde_pct=st(rel) if cor != "verde" else None)
	R["area_cv_across_backgrounds_pct"] = {m: st([100 * np.std(list(v.values()), ddof=1) / np.mean(list(v.values())) for v in area[m].values() if len(v) >= 3]) for m in METHODS}
	# --- ranking pré-registado
	rk = []
	for cor in COLORS:
		pr = R["per"][cor]
		rec_a, rec_c = pr["seg"]["recall"]["paired_ok_frac"], pr["sombra"]["recall"]["paired_ok_frac"]
		det = pr["seg"]["recall"]["detected_frac"]
		cand = [(pr[m]["consistency"]["diff_pose"]["median"], pr[m]["consistency"]["diff_pose"]["p90"], m) for m in METHODS
				if pr[m]["consistency"]["diff_pose"].get("n", 0) > 0]
		best = min(cand) if cand else (None, None, None)
		rp95 = pr[best[2]]["roughness"]["p95"] if best[2] else None
		elig = (cor not in PALE) and max(rec_a, rec_c) >= 0.95
		elig_det = (cor not in PALE) and det >= 0.95
		cg = [(pr[m]["consistency"]["good_diff_pose"]["median"], pr[m]["consistency"]["good_diff_pose"]["p90"], m) for m in METHODS
			  if pr[m]["consistency"]["good_diff_pose"].get("n", 0) > 0]
		bg_ = min(cg) if cg else (None, None, None)
		rk.append(dict(cor=cor, good_best_method=bg_[2], good_diff_median=bg_[0], good_diff_p90=bg_[1],
					   good_rough_p95=pr[bg_[2]]["roughness"]["p95"] if bg_[2] else None, recall_a=rec_a, recall_c=rec_c, recall_detection_a=det, best_method=best[2], diff_median=best[0], diff_p90=best[1],
					   rough_p95=rp95, eligible_recall=elig, gate_rough=bool(rp95 is not None and rp95 < 1.1),
					   qualifies=bool(elig and rp95 is not None and rp95 < 1.1),
					   qualifies_detection_recall=bool(elig_det and rp95 is not None and rp95 < 1.1)))
	order = sorted([r for r in rk if r["diff_median"] is not None], key=lambda r: (r["diff_median"], r["diff_p90"]))
	R["ranking"] = dict(rule="elegível se recall >= 95 % com (a) ou (c) (recall = detetadas, sem clusters, e emparelhadas / N); ordena por RMS mediano "
							 "em pose diferente com o melhor método; desempate p90; porta rugosidade p95 < 1,1; fundos pálidos não ganham",
						table=order, winner=next((r["cor"] for r in order if r["qualifies"]), None),
						winner_if_recall_is_detection_only=next((r["cor"] for r in order if r["qualifies_detection_recall"]), None),
						sensitivity_good_partners=[r["cor"] for r in sorted([r for r in rk if r["good_diff_median"] is not None],
																			  key=lambda r: (r["good_diff_median"], r["good_diff_p90"]))
												   if r["eligible_recall"] and r["good_rough_p95"] is not None and r["good_rough_p95"] < 1.1])
	# --- método vencedor (critério M3 no E-sym)
	gj = os.path.join(sc.OUT, "results.json")
	m3 = json.load(open(gj, encoding="utf-8")).get("esym", {}).get("M3") if os.path.exists(gj) else None
	vmap = {"sombra": "sombra", "hibrido": "simples", "seg": "seg"}
	win_m = None
	if m3:
		win_m = next((vmap[v] for v in ["sombra", "hibrido", "seg"] if m3.get(v, {}).get("meets")), None)
	R["method_winner"] = dict(from_esym_M3=win_m, M3=m3)
	fig_m = win_m or "sombra"
	R["contours_figure_method"] = fig_m
	# --- figuras
	fig_matrix(R, "fundo_matriz.png")
	cover = {}
	for cor in COLORS:
		for j, vid in D[cor]["idmap"].items():
			if all(D[cor]["P"][m][j] is not None for m in METHODS):
				cover[vid] = cover.get(vid, 0) + 1
	PV = D["verde"]["segP"]
	Lmean = {}
	for vid in cover:
		x, y, w, h = map(int, PV[vid]["bbox"])
		Lmean[vid] = float(cv2.cvtColor(D["verde"]["bgr"][y + h // 3:y + 2 * h // 3, x + w // 3:x + 2 * w // 3], cv2.COLOR_BGR2LAB)[..., 0].mean())
	top = sorted(cover, key=lambda v: (-cover[v], v))[:18]
	top = sorted(top, key=lambda v: Lmean[v])
	picks = [top[int(round(q))] for q in np.linspace(0, len(top) - 1, 6)]
	R["overlay_picks"] = dict(verde_ids=picks, coverage={str(v): cover[v] for v in picks}, L_mean={str(v): round(Lmean[v], 1) for v in picks})
	for m in METHODS:
		fig_overlays(D, picks, m, f"fundo_overlays_{m}.png")
	vb = {}
	for cor in ["verde", "laranja", "vermelho"]:
		inv = {v: k for k, v in D[cor]["idmap"].items()}
		vb[cor] = inv.get(picks[0], next(iter(D[cor]["idmap"])))
	fig_shadow(D, ["verde", "laranja", "vermelho"], vb, "fundo_sombra_mascara.png")
	for cor in COLORS:
		fig_contours(cor, D, fig_m, f"fundo_{cor}__contours.jpg")
	R["runtime_s"] = round(time.time() - t0, 1)
	json.dump(R, open(os.path.join(OUT, "results.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False,
			  default=lambda o: o.item() if hasattr(o, "item") else (o.tolist() if hasattr(o, "tolist") else str(o)))
	summary(R)


def summary(R):
	print("calibração", R["shadow_calibration_verde"]["chosen"], "cand L<15:", R["shadow_calibration_verde"]["candidates_L_lt_15_frac"])
	for cor in COLORS:
		s = R["scans"][cor]
		print(f"{cor:14s} det {s['count']}/{s['clusters']}cl id {s['identity']['n_paired']} (pos {s['identity']['by_position']}) pure {s['pure_threshold']}")
		for m in METHODS:
			p = R["per"][cor][m]
			c = p["consistency"]
			print(f"   {m:8s} same {c['same_pose'].get('median')} p90 {c['same_pose'].get('p90')} n {c['same_pose'].get('n')} | diff {c['diff_pose'].get('median')} "
				  f"p90 {c['diff_pose'].get('p90')} n {c['diff_pose'].get('n')} | good-diff {c['good_diff_pose'].get('median')} n {c['good_diff_pose'].get('n')} | vsV {c['vs_verde'].get('median')} | rec {p['recall']['paired_ok']} | rough {p['roughness'].get('median')}/{p['roughness'].get('p95')} "
				  f"| chord {p['side_chord_mm'].get('median')} | area rel {None if p['area_rel_vs_verde_pct'] is None else p['area_rel_vs_verde_pct'].get('median')}")
	print("ranking:", [(r["cor"], r["best_method"], r["diff_median"], r["qualifies"]) for r in R["ranking"]["table"]])
	print("pose check", R["pose_check_rotation_deg_vs_verde"])
	print("sensitivity good partners", R["ranking"]["sensitivity_good_partners"])
	print("winner", R["ranking"]["winner"], "| detection-only", R["ranking"]["winner_if_recall_is_detection_only"], "| method", R["method_winner"]["from_esym_M3"])
	print("runtime", R["runtime_s"])


if __name__ == "__main__":
	main()
