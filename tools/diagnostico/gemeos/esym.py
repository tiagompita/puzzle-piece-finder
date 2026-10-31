"""E-sym rigoroso: gémeos por rotação de 180° (scans de 2026-10-30) com segment_pieces + shapelib.

Uso (a partir da raiz do repositório):
	$env:PPF_SCRATCH = "...\\scratchpad"            # PowerShell (bash: export PPF_SCRATCH=...)
	python tools/diagnostico/gemeos/esym.py
Entrada: images/pieces/coluna5-24_*.jpg (A1, A2, B2, B1) -> $PPF_SCRATCH/seg/gemeos_{A1,A2,B2,B1}.npz
(gerados por segcache.py se faltarem; segcache.py --force para refazer) e $PPF_SCRATCH/seg/scan_verde.npz (julho).
Saída: docs/diagnostico/gemeos/esym_*.png, gemeos_*__contours.jpg e results.json (chave "esym");
$PPF_SCRATCH/gemeos/esym.pkl (peças analisadas, usado por cortes.py).

GT de avaliação (NÃO usado para emparelhar): A1(f,k) <-> A2(f,k) (re-scan); A1(f,k) <-> B2(f,4-k) (gémeo).
Métricas de forma: "corner" = shapelib.shape_dist (4 rotações cíclicas de cantos x Kabsch),
"free" = dist.free_dist (contorno suavizado, 512 pts, FFT cíclica + rotação). Ambas em mm RMS.
Variantes de contorno: "seg" = segment_pieces (pipeline do produto); "simples" = limiar Lab de
gemeos_quick.py (referência para separar o efeito da segmentação do efeito da métrica);
"hibrido" = separação de segment_pieces + fronteira do limiar simples numa banda de 1,5 mm (fundo pela faixa
de baixo); "sombra" = híbrido com fundo pela orla e rejeição da sombra por tonalidade; "scan" =
src.segmentation.segment_scan (o híbrido promovido a produto, fundo pela orla) chamado diretamente no scan.
"""
import os
import sys
import json
import pickle

import numpy as np
import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import segcache as sc  # noqa: E402  (insere a raiz e tools/diagnostico/forma no sys.path)
sys.path.insert(0, os.path.join(sc.REPO, "tools", "diagnostico"))
from shapelib import MM, NS, analyse_v2, smooth_closed, resample_closed, shape_dist, load  # noqa: E402
from dist import free_dist  # noqa: E402

OUT = sc.OUT
WORK = os.path.join(sc.S, "gemeos")
NF = 512
NAMES = ["A1", "A2", "B2"]
RNG = np.random.default_rng(0)

__all__ = ["free_vec", "prep", "twin", "fk", "st", "r3", "corner_d", "free_d", "METRICS", "quick_pieces", "per_side",
		   "imread_bgr", "simple_mask", "rim_bg", "shadow_mask", "hybrid_pieces", "sombra_pieces", "scan_pieces", "TAU_H", "KAPPA",
		   "C_ACH"]


# ---------------------------------------------------------------- utilitários puros
def free_vec(c):
	"""Igual a forma/run_all.py: contorno suavizado (sigma 1,5 amostras), 512 pts, centrado, complexo."""
	cs = smooth_closed(c, 1.5)
	z = resample_closed(cs, NF)
	z = z - z.mean(0)
	return z[:, 0] + 1j * z[:, 1]


def prep(P):
	"""analyse_v2 + vetor 'free' em cada peça (in place); devolve a lista."""
	for p in P:
		analyse_v2(p)
		p["z"] = free_vec(p["c"])
		p.pop("image", None)
	return P


def twin(i):
	"""Índice em B2 do gémeo de A1[i]: (f,k) -> (f,4-k)."""
	f, k = divmod(i, 5)
	return 5 * f + (4 - k)


def fk(i):
	return [int(i // 5), int(i % 5)]


def col_A(i):
	"""Coluna (contada da esquerda) da peça A(f,k) na borda de cima: fila 1 = c5-9, ..."""
	return 5 + i


def r3(v):
	return round(float(v), 3)


def st(x):
	x = np.asarray(x, float)
	if len(x) == 0:
		return dict(n=0)
	return dict(n=int(len(x)), mean=r3(x.mean()), std=r3(x.std(ddof=1)) if len(x) > 1 else 0.0, min=r3(x.min()),
				p5=r3(np.percentile(x, 5)), p10=r3(np.percentile(x, 10)), median=r3(np.median(x)),
				p90=r3(np.percentile(x, 90)), p95=r3(np.percentile(x, 95)), max=r3(x.max()))


def corner_d(a, b):
	return shape_dist(a, b)[0]


def free_d(a, b):
	return free_dist(a, b)[0]


METRICS = {"corner": corner_d, "free": free_d}


def mat(PA, PB, f):
	return np.array([[f(a, b) for b in PB] for a in PA])


def pearson(x, y):
	return r3(np.corrcoef(x, y)[0, 1])


def spearman(x, y):
	rx = np.argsort(np.argsort(x))
	ry = np.argsort(np.argsort(y))
	return r3(np.corrcoef(rx, ry)[0, 1])


# ---------------------------------------------------------------- contornos "simples" (gemeos_quick)
def imread_bgr(path):
	"""cv2.imread não abre caminhos não-ASCII no Windows (digitalização_*); lê com PIL."""
	from PIL import Image
	with Image.open(path) as im:
		return cv2.cvtColor(np.asarray(im.convert("RGB")), cv2.COLOR_RGB2BGR)


def quick_pieces(path):
	"""Máscara de gemeos_quick.pieces (limiar Lab 28, abertura 5, fecho 9); dicts como shapelib.load, ordem (f,k)."""
	im = imread_bgr(path)
	lab = cv2.cvtColor(im, cv2.COLOR_BGR2LAB).astype(np.float32)
	h, w = lab.shape[:2]
	bg = np.median(lab[h - 300:h - 50, 50:w - 50].reshape(-1, 3), axis=0)
	d = np.sqrt(((lab - bg) ** 2 * np.array([0.5, 1, 1])).sum(-1))
	m = (d > 28).astype(np.uint8) * 255
	m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
	m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
	cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
	cs = [c for c in cs if cv2.contourArea(c) > 20000]
	P = [dict(idx=i, contour=c.reshape(-1, 2).astype(np.float64), type="-", straight=-1,
			  bbox=np.array(cv2.boundingRect(c))) for i, c in enumerate(cs)]
	out = []
	for f, k, i in sc.grid_order([p["bbox"] for p in P]):
		P[i]["fk"] = (f, k)
		out.append(P[i])
	return out


def simple_mask(bgr, bg=None, shadow=None):
	"""Máscara binária do gemeos_quick (Lab ponderado [0,5; 1; 1], d > 28, abertura 5, fecho 9).
	bg: Lab de referência do fundo em unidades 8 bits do OpenCV (por omissão, mediana das linhas h-300..h-50,
	como no gemeos_quick). shadow: máscara booleana de píxeis a forçar para fundo antes da abertura/fecho
	(variante "sombra")."""
	lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
	h, w = lab.shape[:2]
	if bg is None:
		bg = np.median(lab[h - 300:h - 50, 50:w - 50].reshape(-1, 3), axis=0)
	d = np.sqrt(((lab - np.asarray(bg, np.float32)) ** 2 * np.array([0.5, 1, 1])).sum(-1))
	fg = d > 28
	if shadow is not None:
		fg &= ~shadow
	m = fg.astype(np.uint8) * 255
	m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
	return cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))


# ---------------------------------------------------------------- fundo pela orla e modelo de sombra (variante "sombra")
# Fixados UMA vez no scan_verde de julho (tools/diagnostico/fundo/efundo.py, regra de calibração no RESULTADOS.md
# de docs/diagnostico/fundo/) e aplicados sem alteração a todos os fundos e aos scans dos gémeos.
TAU_H = 10.0   # graus: |h - h_fundo| < TAU_H
KAPPA = 0.4    # croma: C >= KAPPA * C_fundo
C_ACH = 8.0    # fundo com croma < C_ACH é acromático: tonalidade indefinida, a rejeição da sombra não se aplica


def rim_bg(bgr, lo=100, hi=250):
	"""Lab (unidades 8 bits do OpenCV) do fundo estimado pela orla: faixa a lo..hi px de cada bordo (evita as
	margens brancas do scanner), mediana e 3 iterações de mediana dos píxeis a < 15 da estimativa (moda robusta)."""
	lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
	h, w = lab.shape[:2]
	pts = np.concatenate([lab[lo:hi, lo:w - lo].reshape(-1, 3), lab[h - hi:h - lo, lo:w - lo].reshape(-1, 3),
						  lab[lo:h - lo, lo:hi].reshape(-1, 3), lab[lo:h - lo, w - hi:w - lo].reshape(-1, 3)])
	m = np.median(pts, axis=0)
	for _ in range(3):
		m = np.median(pts[np.sqrt(((pts - m) ** 2).sum(1)) < 15], axis=0)
	return m


def shadow_mask(bgr, bg, tau_h=None, kappa=None):
	"""Sombra projetada = fundo escurecido na mesma direção a*/b*: L < L_fundo, |h - h_fundo| < tau_h e
	C >= kappa * C_fundo. bg em unidades 8 bits do OpenCV. Devolve None se o fundo for acromático (C < C_ACH)."""
	tau_h = TAU_H if tau_h is None else tau_h
	kappa = KAPPA if kappa is None else kappa
	bg = np.asarray(bg, np.float32)
	ab_bg = bg[1:] - 128
	C_bg = float(np.hypot(*ab_bg))
	if C_bg < C_ACH:
		return None
	lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
	a, b = lab[..., 1] - 128, lab[..., 2] - 128
	dh = np.abs((np.degrees(np.arctan2(b, a) - np.arctan2(ab_bg[1], ab_bg[0])) + 180) % 360 - 180)
	return (lab[..., 0] < bg[0]) & (dh < tau_h) & (np.hypot(a, b) >= kappa * C_bg)


def sombra_pieces(path, segP, band_mm=1.5):
	"""Variante "sombra" (método (c) do E-fundo): como hybrid_pieces, mas o limiar usa o fundo estimado pela orla
	(rim_bg) e os píxeis de sombra (shadow_mask) passam a fundo antes da abertura/fecho."""
	bgr = imread_bgr(path) if isinstance(path, str) else path
	bg = rim_bg(bgr)
	return hybrid_pieces(bgr, segP, band_mm, mask=simple_mask(bgr, bg=bg, shadow=shadow_mask(bgr, bg)))


def hybrid_pieces(path, segP, band_mm=1.5, mask=None):
	"""Variante "hibrido": separação das peças por segment_pieces (Voronoi das máscaras segP) e
	fronteira pelo limiar simples, limitada a band_mm à volta do contorno de segment_pieces.
	path: caminho do scan ou imagem BGR já carregada. mask: máscara do limiar a usar (por omissão simple_mask(bgr)).
	segP: peças de shapelib.load (contornos em coordenadas do scan). Devolve dicts na mesma ordem; uma peça sem
	píxeis do limiar dentro da banda fica com contour=None e missing=True."""
	bgr = imread_bgr(path) if isinstance(path, str) else path
	H, W = bgr.shape[:2]
	sm = (simple_mask(bgr) if mask is None else mask) > 0
	lab_img = np.zeros((H, W), np.int32)
	for q, p in enumerate(segP):
		cv2.fillPoly(lab_img, [np.round(p["contour"]).astype(np.int32).reshape(-1, 1, 2)], q + 1)
	inv = (lab_img == 0).astype(np.uint8)
	dist_, lbl = cv2.distanceTransformWithLabels(inv, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
	# lbl indexa pixels-zero de inv (=pixels de peça); mapear para o rótulo da peça
	zero = np.where(inv.ravel() == 0)[0]
	lut = np.zeros(lbl.max() + 1, np.int32)
	lut[np.arange(1, len(zero) + 1)] = lab_img.ravel()[zero]
	vor = lut[lbl]
	band = dist_ <= band_mm / MM
	out = []
	for q, p in enumerate(segP):
		x, y, w, h = map(int, p["bbox"])
		pad = 40
		x0, y0, x1, y1 = max(0, x - pad), max(0, y - pad), min(W, x + w + pad), min(H, y + h + pad)
		m = (sm[y0:y1, x0:x1] & (vor[y0:y1, x0:x1] == q + 1) & band[y0:y1, x0:x1]).astype(np.uint8)
		cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
		d = dict(p)
		for k in ("c", "z", "vec", "ok"):
			d.pop(k, None)
		if not cs:
			d.update(contour=None, missing=True)
			out.append(d)
			continue
		c = max(cs, key=cv2.contourArea).reshape(-1, 2).astype(np.float64) + [x0, y0]
		d.update(contour=c, bbox=np.array(cv2.boundingRect(c.astype(np.int32).reshape(-1, 1, 2))))
		out.append(d)
	return out


def scan_pieces(path):
	"""Variante "scan": src.segmentation.segment_scan sobre o scan (sem .npz). Dicts como shapelib.load (contorno em
	coordenadas do scan, sem clusters), ordem (f, k) por segcache.grid_order; guarda refined e roughness do produto."""
	from PIL import Image
	from src.segmentation import segment_scan
	with Image.open(path) as im:
		im.load()
		r = segment_scan(im)
	if "error" in r:
		return []
	P = [dict(idx=p["index"], contour=np.asarray(p["contour"]).reshape(-1, 2).astype(np.float64), type="-", straight=-1,
			  bbox=np.array(p["bbox"]), refined=bool(p["refined"]), roughness_prod=float(p["roughness"]))
		 for p in r["pieces"] if not p["is_cluster"]]
	out = []
	for f, k, i in sc.grid_order([p["bbox"] for p in P]):
		P[i]["fk"] = (f, k)
		out.append(P[i])
	return out


def quick_replica(paths):
	"""Corre as funções do gemeos_quick.py original (sem alterações) e devolve os seus números."""
	import gemeos_quick as gq
	A1, A2, B = gq.pieces(paths["A1"]), gq.pieces(paths["A2"]), gq.pieces(paths["B2"])
	T = [twin(i) for i in range(20)]
	self_ = np.array([gq.dist(x, y) for x, y in zip(A1, A2)])
	M = np.array([[gq.dist(x, y) for y in B] for x in A1])
	M2 = np.array([[gq.dist(x, y) for y in B] for x in A2])
	am = M.argmin(1)
	tw = M[np.arange(len(A1)), am]
	oth = np.array([np.min(np.delete(M[i], am[i])) for i in range(len(A1))])
	return dict(n=[len(A1), len(A2), len(B)], rescan=st(self_), twin_A1B2=st(tw), twin_A2B2=st(M2[np.arange(20), T]),
				nearest_nontwin=st(oth), argmin=am.tolist(), top1=int(np.sum(am == T)))


# ---------------------------------------------------------------- análise E-sym
def esym_metrics(S, mname):
	"""S: nome -> 20 peças analisadas (ordem f,k). Devolve (dict de métricas, matrizes) para uma métrica."""
	f = METRICS[mname]
	M = {}
	for a, b in [("A1", "A2"), ("A1", "B2"), ("A2", "B2"), ("A1", "A1"), ("B2", "B2")]:
		M[a + b] = mat(S[a], S[b], f)
	n = 20
	T = np.array([twin(i) for i in range(n)])
	ar = np.arange(n)
	rescan = M["A1A2"][ar, ar]
	tw12 = M["A1B2"][ar, T]
	tw22 = M["A2B2"][ar, T]
	nt_B2 = np.array([np.min(np.delete(M["A1B2"][i], T[i])) for i in ar])
	nt_A1 = np.array([np.min(np.delete(M["A1A1"][i], i)) for i in ar])
	nt_B2B2 = np.array([np.min(np.delete(M["B2B2"][j], j)) for j in ar])
	nt_any = np.minimum(nt_B2, nt_A1)
	am = M["A1B2"].argmin(1)
	amc = M["A1B2"].argmin(0)          # para cada B2 j, a melhor A1
	mutual = np.array([amc[am[i]] == i for i in ar])
	am2 = M["A2B2"].argmin(1)
	am_rs = M["A1A2"].argmin(1)
	srt = np.sort(M["A1B2"], 1)
	margin_B2 = nt_B2 / tw12
	margin_any = nt_any / tw12
	# pool conjunto: consulta A1 i contra B2 U (A1 \ i) = 39 candidatos; posição do gémeo
	rank_pool = np.array([int(np.sum(np.r_[np.delete(M["A1B2"][i], T[i]), np.delete(M["A1A1"][i], i)] < tw12[i])) for i in ar])

	def who(i):
		if nt_B2[i] <= nt_A1[i]:
			row = M["A1B2"][i].copy(); row[T[i]] = np.inf
			return "B2" + str(tuple(fk(int(np.argmin(row)))))
		row = M["A1A1"][i].copy(); row[i] = np.inf
		return "A1" + str(tuple(fk(int(np.argmin(row)))))

	res = dict(
		rescan_A1A2=st(rescan), twin_A1B2=st(tw12), twin_A2B2=st(tw22),
		nearest_nontwin_in_B2=st(nt_B2), nearest_other_in_A1=st(nt_A1), nearest_other_in_B2_from_B2=st(nt_B2B2),
		nearest_nontwin_any=st(nt_any),
		top1_A1_to_B2=int(np.sum(am == T)), top1_B2_to_A1=int(np.sum(amc == np.argsort(T))),
		top1_A2_to_B2=int(np.sum(am2 == T)), top1_rescan_A1_to_A2=int(np.sum(am_rs == ar)),
		top1_pool39=int(np.sum(rank_pool == 0)),
		mutual_nn=int(mutual.sum()), mutual_nn_correct=int(np.sum(mutual & (am == T))),
		pairing_from_shape=[dict(A1=fk(i), B2=fk(int(am[i])), mutual=bool(mutual[i]), correct=bool(am[i] == T[i])) for i in ar],
		margin_B2=st(margin_B2), margin_any=st(margin_any), ratio_second_over_best_row=st(srt[:, 1] / srt[:, 0]),
		pieces_margin_lt_1_5=[dict(A1=fk(i), col=col_A(i), twin=r3(tw12[i]), nearest_nontwin=r3(nt_any[i]), which=who(i),
								   margin=round(float(margin_any[i]), 2)) for i in ar if margin_any[i] < 1.5],
		per_piece=[dict(A1=fk(i), col=col_A(i), rescan=r3(rescan[i]), twin_A1B2=r3(tw12[i]), twin_A2B2=r3(tw22[i]),
						nearest_nontwin_B2=r3(nt_B2[i]), nearest_other_A1=r3(nt_A1[i]), nearest_which=who(i),
						margin_any=round(float(margin_any[i]), 2), argmin_B2=fk(int(am[i]))) for i in ar],
	)
	return res, M


def per_side(S, pairs, label):
	"""Lados homólogos (alinhados pelo best_k do shape_dist): RMS global (bloco de 64 pts após Kabsch da peça
	inteira), RMS do perfil normalizado x corda média (cada lado no seu referencial), |dL| da corda.
	pairs = [(i, j)] índices em S[a], S[b]."""
	a_name, b_name = label
	rows = []
	for i, j in pairs:
		pa, pb = S[a_name][i], S[b_name][j]
		d, k, R = shape_dist(pa, pb)
		A = (pa["vec"] - pa["vec"].mean(0)) @ R
		B = np.roll(pb["vec"], -k * NS, axis=0)
		B = B - B.mean(0)
		for s in range(4):
			sb = (s + k) % 4
			blk = slice(s * NS, (s + 1) * NS)
			g = float(np.sqrt(np.mean(np.sum((A[blk] - B[blk]) ** 2, 1)))) * MM
			Lm = (pa["lens"][s] + pb["lens"][sb]) / 2
			pr = float(np.sqrt(np.mean(np.sum((pa["profs"][s] - pb["profs"][sb]) ** 2, 1)))) * Lm
			rows.append(dict(i=i, j=j, s=s, sb=sb, ta=pa["types"][s], tb=pb["types"][sb], rms_global_mm=g, rms_prof_mm=pr,
							 dL=abs(pa["lens"][s] - pb["lens"][sb]), dL_signed=pa["lens"][s] - pb["lens"][sb]))
	return rows


def side_summary(rows):
	out = {}
	for key, sel in [("all", lambda r: True), ("non_F", lambda r: r["ta"] != "F" and r["tb"] != "F"),
					 ("F", lambda r: r["ta"] == "F" or r["tb"] == "F")]:
		rr = [r for r in rows if sel(r)]
		if not rr:
			out[key] = dict(n=0)
			continue
		out[key] = dict(rms_global_mm=st([r["rms_global_mm"] for r in rr]), rms_prof_mm=st([r["rms_prof_mm"] for r in rr]),
						absdL_mm=st([r["dL"] for r in rr]),
						dL_signed_sd=r3(np.std([r["dL_signed"] for r in rr], ddof=1)) if len(rr) > 1 else None,
						type_agree=f"{sum(r['ta'] == r['tb'] for r in rr)}/{len(rr)}")
	return out


# ---------------------------------------------------------------- figuras (cv2)
RED, BLUE, BLK, GRN, GREY = (40, 40, 220), (200, 90, 0), (0, 0, 0), (0, 150, 0), (150, 150, 150)  # BGR


def put(img, t, xy, s=0.45, c=BLK, th=1):
	cv2.putText(img, t, xy, cv2.FONT_HERSHEY_SIMPLEX, s, c, th, cv2.LINE_AA)


def aligned_corner(pa, pb):
	d, k, R = shape_dist(pa, pb)
	ca = (pa["c"] - pa["vec"].mean(0)) @ R
	cb = pb["c"] - pb["vec"].mean(0)
	return ca, cb, d


def tile_pair(ca, cb, lines, T=300, cols=(RED, BLUE)):
	t = np.full((T, T, 3), 255, np.uint8)
	allp = np.vstack([ca, cb])
	o = (allp.max(0) + allp.min(0)) / 2
	sc_ = (T - 75) / max(np.ptp(allp[:, 0]), np.ptp(allp[:, 1]))
	for p, c in zip([ca, cb], cols):
		q = np.round((p - o) * sc_ + [T / 2, T / 2 + 20]).astype(np.int32).reshape(-1, 1, 2)
		cv2.polylines(t, [q], True, c, 1, cv2.LINE_AA)
	for k, s in enumerate(lines):
		put(t, s, (5, 15 + 15 * k), 0.42)
	L = 5 / MM * sc_
	cv2.line(t, (T - 10 - int(L), T - 8), (T - 10, T - 8), BLK, 2)
	put(t, "5 mm", (T - 10 - int(L), T - 14), 0.38)
	cv2.rectangle(t, (0, 0), (T - 1, T - 1), GREY, 1)
	return t


def grid(tiles, cols):
	th, tw = tiles[0].shape[:2]
	rows = (len(tiles) + cols - 1) // cols
	M = np.full((rows * th, cols * tw, 3), 255, np.uint8)
	for i, t in enumerate(tiles):
		r, c = divmod(i, cols)
		M[r * th:(r + 1) * th, c * tw:(c + 1) * tw] = t
	return M


def with_title(img, lines):
	h = 22 * len(lines) + 8
	top = np.full((h, img.shape[1], 3), 255, np.uint8)
	for k, s in enumerate(lines):
		put(top, s, (8, 20 + 22 * k), 0.55)
	return np.vstack([top, img])


def fig_overlays(S, a, b, pairs, Mc, Mf, fname, title, cols_ab):
	tiles = []
	for i, j in pairs:
		ca, cb, d = aligned_corner(S[a][i], S[b][j])
		pa, pb = S[a][i], S[b][j]
		tiles.append(tile_pair(ca, cb, [f"{a}{tuple(fk(i))} c{col_A(i)} vs {b}{tuple(fk(j))}",
										 f"corner {Mc[i, j]:.2f}  free {Mf[i, j]:.2f} mm",
										 f"{''.join(pa['types'])} / {''.join(pb['types'])}"], cols=cols_ab))
	cv2.imwrite(os.path.join(OUT, fname), with_title(grid(tiles, 5), title))


def fig_hist(series, fname, title):
	"""series: [(métrica, [(rótulo, valores, cor), ...])] -> um painel por métrica."""
	panels = []
	for mname, ss in series:
		W, H = 780, 400
		img = np.full((H, W, 3), 255, np.uint8)
		bins = np.arange(0, 2.01, 0.1)
		hs = [np.histogram(np.clip(v, 0, 1.999), bins)[0] / max(1, len(v)) for _, v, _ in ss]
		ymax = max(h.max() for h in hs)
		bw = (W - 70) / (len(bins) - 1)
		x0 = 50
		for k in range(len(bins) - 1):
			for q, (h, (_, _, c)) in enumerate(zip(hs, ss)):
				xa = int(x0 + k * bw + q * bw / len(ss))
				xb = int(x0 + k * bw + (q + 1) * bw / len(ss)) - 1
				cv2.rectangle(img, (xa, H - 50 - int(h[k] / ymax * (H - 150))), (xb, H - 50), c, -1)
			if k % 2 == 0:
				put(img, f"{bins[k]:.1f}", (int(x0 + k * bw), H - 32), 0.38)
		cv2.line(img, (x0, H - 50), (W - 20, H - 50), BLK, 1)
		put(img, f"RMS de forma ({mname}), mm; altura = fracao de cada serie; ultimo bin = >= 1,9", (8, H - 10), 0.42)
		for q, (lab_, v, c) in enumerate(ss):
			put(img, f"{lab_} (n={len(v)}, mediana {np.median(v):.2f})", (8, 20 + 18 * q), 0.45, c, 1)
		panels.append(img)
	cv2.imwrite(os.path.join(OUT, fname), with_title(np.hstack(panels), [title]))


def fig_matrix(Ms, fname):
	panels = []
	for mname, M in Ms:
		c = 34
		W = 60 + 20 * c
		H = 60 + 20 * c + 30
		img = np.full((H, W, 3), 255, np.uint8)
		vmax = 2.0
		am = M.argmin(1)
		for i in range(20):
			for j in range(20):
				v = min(M[i, j], vmax) / vmax
				col = cv2.applyColorMap(np.uint8([[255 * (1 - v)]]), cv2.COLORMAP_VIRIDIS)[0, 0].tolist()
				x, y = 50 + j * c, 50 + i * c
				cv2.rectangle(img, (x, y), (x + c - 1, y + c - 1), col, -1)
				put(img, f"{M[i, j]:.1f}", (x + 3, y + 21), 0.33, (255, 255, 255) if v > 0.4 else BLK)
				if j == twin(i):
					cv2.rectangle(img, (x, y), (x + c - 1, y + c - 1), (0, 0, 255), 2)
				if j == am[i]:
					cv2.circle(img, (x + c - 6, y + 6), 3, (255, 255, 255), -1)
					cv2.circle(img, (x + c - 6, y + 6), 3, BLK, 1)
		for q in range(20):
			put(img, f"{q // 5}{q % 5}", (50 + q * c + 6, 44), 0.33)
			put(img, f"{q // 5}{q % 5}", (22, 50 + q * c + 21), 0.33)
		put(img, f"A1 (linhas) x B2 (colunas), {mname}, mm; vermelho = gemeo B2(f,4-k); ponto = argmin", (8, 18), 0.42)
		put(img, "cor: 0 mm (amarelo) ... >= 2 mm (violeta)", (8, H - 12), 0.42)
		panels.append(img)
	rows = [np.hstack(panels[k:k + 2]) for k in range(0, len(panels), 2)]
	cv2.imwrite(os.path.join(OUT, fname), np.vstack(rows))


def fig_fringes(seg, simp, picks, fname):
	"""Recortes a 2x com o contorno de segment_pieces (vermelho) e do limiar simples (azul)."""
	tiles = []
	for name, i in picks:
		ps, pq = seg[name][i], simp[name][i]
		im = imread_bgr(os.path.join(sc.REPO, sc.SCANS[name]))
		x, y, w, h = map(int, ps["bbox"])
		pad = 12
		x0, y0 = max(0, x - pad), max(0, y - pad)
		crop = im[y0:y + h + pad, x0:x + w + pad]
		s = 2
		crop = cv2.resize(crop, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
		for p, c in [(pq, BLUE), (ps, RED)]:
			cv2.polylines(crop, [np.round((p["contour"] - [x0, y0]) * s + s / 2).astype(np.int32).reshape(-1, 1, 2)], True, c, 1, cv2.LINE_AA)
		lab_ = f"{name} {tuple(fk(i))}: vermelho segment_pieces, azul limiar simples"
		put(crop, lab_, (6, 18), 0.5, (255, 255, 255), 3)
		put(crop, lab_, (6, 18), 0.5, BLK, 1)
		tiles.append(crop)
	H = max(t.shape[0] for t in tiles)
	tiles = [np.vstack([t, np.full((H - t.shape[0], t.shape[1], 3), 255, np.uint8)]) for t in tiles]
	cv2.imwrite(os.path.join(OUT, fname), np.hstack(tiles))


def fig_fringes3(V, idx, fname):
	"""B2: recortes a 2x das peças mais escuras (prado) com os contornos seg (vermelho), híbrido (azul), sombra (verde)
	e scan (magenta, desenhado primeiro: só se vê onde difere do híbrido)."""
	im = imread_bgr(os.path.join(sc.REPO, sc.SCANS["B2"]))
	tiles = []
	for i in idx:
		x, y, w, h = map(int, V["seg"][i]["bbox"])
		pad = 12
		x0, y0 = max(0, x - pad), max(0, y - pad)
		s = 2
		crop = cv2.resize(im[y0:y + h + pad, x0:x + w + pad], None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
		for var, c in [("scan", (200, 0, 200)), ("hibrido", BLUE), ("sombra", GRN), ("seg", RED)]:
			cv2.polylines(crop, [np.round((V[var][i]["contour"] - [x0, y0]) * s + s / 2).astype(np.int32).reshape(-1, 1, 2)], True, c, 1, cv2.LINE_AA)
		lab_ = f"B2 {tuple(fk(i))}: vermelho seg, azul hibrido, verde sombra, magenta scan (sob o azul)"
		put(crop, lab_, (6, 18), 0.5, (255, 255, 255), 3)
		put(crop, lab_, (6, 18), 0.5, BLK, 1)
		tiles.append(crop)
	H = max(t.shape[0] for t in tiles)
	tiles = [np.vstack([t, np.full((H - t.shape[0], t.shape[1], 3), 255, np.uint8)]) for t in tiles]
	cv2.imwrite(os.path.join(OUT, fname), np.hstack(tiles))


# ---------------------------------------------------------------- extrapolação da margem (ponto 6)
def tail_fit(x, t_list, frac=0.05, nmin=12):
	"""Cauda inferior da distribuição empírica (pontos com F <= frac, pelo menos nmin): exponencial
	ln F = a + b d  e  Weibull  ln(-ln(1-F)) = k ln d + c (mínimos quadrados). Devolve p(t) por modelo."""
	x = np.sort(np.asarray(x, float))
	n = len(x)
	F = (np.arange(1, n + 1) - 0.5) / n
	m = min(n, max(nmin, int(np.ceil(frac * n))))
	xs, Fs = x[:m], F[:m]
	be, ae = np.polyfit(xs, np.log(Fs), 1)
	kw, cw = np.polyfit(np.log(xs), np.log(-np.log(1 - Fs)), 1)
	out = dict(n=n, n_tail=int(m), tail_max_d=r3(xs[-1]), exp_slope_per_mm=r3(be), weibull_k=r3(kw))
	for tn, t in t_list:
		pe = float(min(1.0, np.exp(ae + be * t)))
		pw = float(1 - np.exp(-np.exp(cw + kw * np.log(t))))
		out[tn] = dict(t=r3(t), p_emp=float(np.mean(x < t)), n_below=int(np.sum(x < t)), p_exp=pe, p_weibull=pw)
	return out


def expected_false(p, Ns):
	return {str(N): dict(expected=round(N * p, 4), p_at_least_one=round(1 - (1 - p) ** N, 4)) for N in Ns}


def extrapolate(S, V, res_twins):
	"""S: A1, B2 (20+20, variante seg); V: 61 peças do scan_verde. Devolve (dict, matrizes 101x101)."""
	P = S["A1"] + S["B2"] + V
	n = len(P)
	grp = np.array([0] * 40 + [1] * (n - 40))
	cls = [p["cls"] for p in P]
	out = {"n_pieces": n, "note": "[V] em 101 peças (40 de borda de hoje, 61 de julho); valores para N grande são extrapolação [NT]"}
	is_twin = np.zeros((n, n), bool)
	for i in range(20):
		is_twin[i, 20 + twin(i)] = is_twin[20 + twin(i), i] = True
	iu = np.triu_indices(n, 1)
	ii, jj = iu
	kind = np.where((grp[ii] == 0) & (grp[jj] == 0), "w40", np.where((grp[ii] == 1) & (grp[jj] == 1), "w61", "x"))
	same = np.array([cls[a] == cls[b] for a, b in zip(ii, jj)])
	tw_mask = is_twin[ii, jj]
	nt = ~tw_mask
	Ns = [10, 60, 500, 3008]
	mats = {}
	for mname, f in METRICS.items():
		D = np.zeros((n, n))
		for a, b in zip(ii, jj):
			# corner não é exatamente simétrica (Kabsch sobre o vetor de A centrado); usa-se o mínimo
			D[a, b] = D[b, a] = f(P[a], P[b]) if mname == "free" else min(f(P[a], P[b]), f(P[b], P[a]))
		mats[mname] = D
		d = D[iu]
		twins = np.r_[res_twins[mname]["A1B2"], res_twins[mname]["A2B2"]]
		t95 = float(np.percentile(twins, 95))
		tmax = float(twins.max())
		tl = [("t_p95_twins", t95), ("t_max_twins", tmax)]
		o = dict(twins_used=st(twins), t_p95=r3(t95), t_max=r3(tmax),
				 nontwin_w40=st(d[nt & (kind == "w40")]), nontwin_w61=st(d[nt & (kind == "w61")]), nontwin_x=st(d[nt & (kind == "x")]),
				 nontwin_all=st(d[nt]), nontwin_same_class=st(d[nt & same]), nontwin_diff_class=st(d[nt & ~same]),
				 nontwin_same_class_w40=st(d[nt & same & (kind == "w40")]), nontwin_same_class_w61=st(d[nt & same & (kind == "w61")]),
				 nontwin_same_class_x=st(d[nt & same & (kind == "x")]), twin_pairs_check=st(d[tw_mask]))
		o["tail_all"] = tail_fit(d[nt], tl)
		o["tail_same_class"] = tail_fit(d[nt & same], tl)
		o["tail_same_class_w40"] = tail_fit(d[nt & same & (kind == "w40")], tl)
		exp = {}
		for key in ["tail_all", "tail_same_class", "tail_same_class_w40"]:
			exp[key] = {}
			for tn, _ in tl:
				q = o[key][tn]
				exp[key][tn] = {mod: expected_false(max(q[pk], 0.0), Ns) for mod, pk in [("emp", "p_emp"), ("exp", "p_exp"), ("weibull", "p_weibull")]}
		o["expected_false_candidates"] = exp
		# curvas por subamostragem (200 repetições)
		reps = 200
		curve_set, curve_q = {}, {}
		for m_ in [10, 20, 40, 61, 101]:
			vals = []
			for _ in range(reps if m_ < n else 1):
				s = RNG.choice(n, m_, replace=False) if m_ < n else np.arange(n)
				sub = D[np.ix_(s, s)].copy()
				sub[is_twin[np.ix_(s, s)]] = np.inf
				np.fill_diagonal(sub, np.inf)
				vals.append(sub.min())
			curve_set[str(m_)] = dict(median=r3(np.median(vals)), p10=r3(np.percentile(vals, 10)), p90=r3(np.percentile(vals, 90)))
		for m_ in [10, 20, 40, 61, 99]:
			vals = []
			for q in range(40):
				cand = np.array([j for j in range(n) if j != q and not is_twin[q, j]])
				for _ in range(reps if m_ < len(cand) else 1):
					s = RNG.choice(cand, m_, replace=False) if m_ < len(cand) else cand
					vals.append(D[q, s].min())
			curve_q[str(m_)] = dict(median=r3(np.median(vals)), p10=r3(np.percentile(vals, 10)), p90=r3(np.percentile(vals, 90)))
		for name_, cur in [("curve_set_min", curve_set), ("curve_query_nn", curve_q)]:
			xs = np.array([float(k) for k in cur])
			ys = np.array([cur[k]["median"] for k in cur])
			b, a = np.polyfit(np.log(xs), ys, 1)
			y10 = np.array([cur[k]["p10"] for k in cur])
			b10, a10 = np.polyfit(np.log(xs), y10, 1)
			cur["fit_median"] = dict(a=r3(a), b_per_ln=r3(b), pred={str(N): r3(a + b * np.log(N)) for N in [500, 3008]})
			cur["fit_p10"] = dict(a=r3(a10), b_per_ln=r3(b10), pred={str(N): r3(a10 + b10 * np.log(N)) for N in [500, 3008]})
			o[name_] = cur
		# gémeo dentro do pool de 100 (consulta = cada uma das 40 peças de borda)
		rk = []
		for q in range(40):
			tq = int(np.where(is_twin[q])[0][0])
			row = D[q].copy()
			row[q] = np.inf
			rk.append(int(np.sum(row < row[tq])))
		o["twin_rank_in_pool_100"] = dict(top1=int(np.sum(np.array(rk) == 0)), n=40, ranks=rk)
		out[mname] = o
	return out, mats


# ---------------------------------------------------------------- principal
def main():
	os.makedirs(OUT, exist_ok=True)
	os.makedirs(WORK, exist_ok=True)
	segstats = {name: sc.segment(name) for name in sc.SCANS}
	# --- variante seg (segment_pieces)
	seg = {name: prep(sc.load_grid(name)) for name in sc.SCANS}
	B1_rows = [len([p for p in seg["B1"] if p["fk"][0] == f]) for f in range(5)]
	for name in NAMES:
		assert len(seg[name]) == 20, (name, len(seg[name]))
		assert all(p["fk"] == (i // 5, i % 5) for i, p in enumerate(seg[name])), name
		assert all(p["ok"] for p in seg[name]), (name, [p["fk"] for p in seg[name] if not p["ok"]])
	# --- variante simples
	simp = {name: prep(quick_pieces(os.path.join(sc.REPO, sc.SCANS[name]))) for name in sc.SCANS}
	simp_ok = {n: [len(simp[n]), int(sum(p["ok"] for p in simp[n]))] for n in sc.SCANS}
	# --- variante híbrida (separação por segment_pieces, fronteira pelo limiar simples)
	hyb = {name: prep(hybrid_pieces(os.path.join(sc.REPO, sc.SCANS[name]), sc.load_grid(name))) for name in sc.SCANS}
	# --- variante sombra (método (c) do E-fundo: fundo pela orla + rejeição da sombra por tonalidade)
	sh = {name: prep(sombra_pieces(os.path.join(sc.REPO, sc.SCANS[name]), sc.load_grid(name))) for name in sc.SCANS}
	# --- variante scan (src.segmentation.segment_scan: o híbrido promovido, fundo pela orla)
	scn = {name: prep(scan_pieces(os.path.join(sc.REPO, sc.SCANS[name]))) for name in sc.SCANS}
	for name in sc.SCANS:
		for p, q in zip(hyb[name], seg[name]):
			p["fk"] = q["fk"]
		for p, q in zip(sh[name], seg[name]):
			p["fk"] = q["fk"]
	R = {"segmentation": segstats, "B1_rows": B1_rows, "simples_counts_ok": simp_ok,
		 "padding_note": (f"scans com moldura de {sc.PAD} px da cor mediana da orla antes de segment_pieces (ver segcache.py)" if sc.PAD > 0
						  else "sem moldura (segcache.PAD = 0; S1 corrigido em bc124d2); .npz dos gémeos regenerados em 2026-10-31"),
		 "scan_counts_refined": {n: [len(scn[n]), int(sum(p["refined"] for p in scn[n]))] for n in sc.SCANS},
		 "sombra_params": dict(tau_h=TAU_H, kappa=KAPPA, C_ach=C_ACH, bg={n: [round(float(v), 1) for v in rim_bg(imread_bgr(os.path.join(sc.REPO, sc.SCANS[n])))] for n in NAMES})}
	R["quick_replica"] = quick_replica({n: os.path.join(sc.REPO, sc.SCANS[n]) for n in sc.SCANS})
	T = [twin(i) for i in range(20)]
	Mall = {}
	VARS = [("seg", seg), ("simples", simp), ("hibrido", hyb), ("sombra", sh), ("scan", scn)]
	for var, S in VARS:
		if not all(len(S[n]) == 20 and all(p["ok"] for p in S[n]) for n in NAMES):
			R[var] = dict(error="contagem/cantos falharam", counts={n: [len(S[n]), int(sum(p["ok"] for p in S[n]))] for n in sc.SCANS})
			continue
		R[var] = {}
		for mname in METRICS:
			r, M = esym_metrics(S, mname)
			R[var][mname] = r
			Mall[(var, mname)] = M
		R[var]["sides_twin_A1B2"] = side_summary(per_side(S, list(zip(range(20), T)), ("A1", "B2")))
		R[var]["sides_twin_A2B2"] = side_summary(per_side(S, list(zip(range(20), T)), ("A2", "B2")))
		R[var]["sides_rescan_A1A2"] = side_summary(per_side(S, list(zip(range(20), range(20))), ("A1", "A2")))
		R[var]["topology"] = dict(
			classes={n: [S[n][i]["cls"] for i in range(20)] for n in NAMES},
			types={n: ["".join(S[n][i]["types"]) for i in range(20)] for n in NAMES},
			exactly_one_F={n: int(sum(S[n][i]["types"].count("F") == 1 for i in range(20))) for n in NAMES},
			class_agree_A1B2=int(sum(S["A1"][i]["cls"] == S["B2"][T[i]]["cls"] for i in range(20))),
			class_agree_A1A2=int(sum(S["A1"][i]["cls"] == S["A2"][i]["cls"] for i in range(20))),
			class_agree_A2B2=int(sum(S["A2"][i]["cls"] == S["B2"][T[i]]["cls"] for i in range(20))),
			mismatches_A1B2=[dict(A1=fk(i), a=S["A1"][i]["cls"], b=S["B2"][T[i]]["cls"],
								  maxdev_a=[r3(v) for v in S["A1"][i]["maxdev"]], maxdev_b=[r3(v) for v in S["B2"][T[i]]["maxdev"]])
							 for i in range(20) if S["A1"][i]["cls"] != S["B2"][T[i]]["cls"]],
			F_maxdev={n: st([S[n][i]["maxdev"][s] for i in range(20) for s in range(4) if S[n][i]["types"][s] == "F"]) for n in NAMES},
			min_nonF_maxdev={n: r3(min(S[n][i]["maxdev"][s] for i in range(20) for s in range(4) if S[n][i]["types"][s] != "F")) for n in NAMES},
			edgepy_types={n: [S[n][i]["type"] for i in range(20)] for n in NAMES})
		rough = {n: np.array([S[n][i]["rough"] for i in range(20)]) for n in NAMES}
		rc = {}
		for mname in METRICS:
			pp = R[var][mname]["per_piece"]
			tw_ = np.array([x["twin_A1B2"] for x in pp])
			rs_ = np.array([x["rescan"] for x in pp])
			rmax_t = np.maximum(rough["A1"], rough["B2"][T])
			rmax_r = np.maximum(rough["A1"], rough["A2"])
			rc[mname] = dict(twin_vs_maxrough_pearson=pearson(tw_, rmax_t), twin_vs_maxrough_spearman=spearman(tw_, rmax_t),
							 rescan_vs_maxrough_pearson=pearson(rs_, rmax_r), rescan_vs_maxrough_spearman=spearman(rs_, rmax_r))
		R[var]["roughness"] = dict(per_scan={n: st(rough[n]) for n in NAMES}, B1=st([p["rough"] for p in S["B1"] if p.get("ok")]),
								   corr=rc, per_piece={n: [r3(v) for v in rough[n]] for n in NAMES})
		R[var]["corner_quad"] = {n: dict(poly_ang_absdev=st([abs(a - 90) for p in S[n] for a in p["poly_ang"]]),
										 side_len=st([l for p in S[n] for l in p["lens"]])) for n in NAMES}
	# B1 (só diagnóstico): A1 -> B1 por forma (corner). Correspondência esperada também (f,4-k)? (B2 = B1 rodadas na casa)
	if len(seg["B1"]) == 20 and all(p["ok"] for p in seg["B1"]):
		Mb = mat(seg["A1"], seg["B1"], corner_d)
		Mbb = mat(seg["B2"], seg["B1"], corner_d)
		R["B1_diag"] = dict(argmin_A1_to_B1=[fk(int(j)) for j in Mb.argmin(1)], min_per_row_A1B1=[r3(v) for v in Mb.min(1)],
							argmin_B2_to_B1=[fk(int(j)) for j in Mbb.argmin(1)], min_per_row_B2B1=[r3(v) for v in Mbb.min(1)],
							note="B1 só diagnóstico; não entra nas métricas")
	if len(hyb["B1"]) == 20 and all(p["ok"] for p in hyb["B1"]):
		hb = {}
		for mname in METRICS:
			Mbb = mat(hyb["B2"], hyb["B1"], METRICS[mname])
			Mab = mat(hyb["A1"], hyb["B1"], METRICS[mname])
			ar_ = np.arange(20)
			hb[mname] = dict(rescan_B2B1_identity=st(Mbb[ar_, ar_]), top1_B2_to_B1=int(np.sum(Mbb.argmin(1) == ar_)),
							 twin_A1B1=st(Mab[ar_, [twin(i) for i in ar_]]), top1_A1_to_B1=int(np.sum(Mab.argmin(1) == np.array([twin(i) for i in ar_]))))
		R.setdefault("B1_diag", {})["hibrido"] = hb
	# --- figuras
	Mc, Mf = Mall[("seg", "corner")], Mall[("seg", "free")]
	fig_overlays(seg, "A1", "B2", list(zip(range(20), T)), Mc["A1B2"], Mf["A1B2"], "esym_sobreposicoes.png",
				 ["E-sym: gemeos A1(f,k) [vermelho] vs B2(f,4-k) [azul], alinhados por cantos + Kabsch (segment_pieces)",
				  "linha 3: tipos de lado A1 / B2 (T patilha, B encaixe, F reto) na ordem dos cantos de cada peca"], (RED, BLUE))
	fig_overlays(seg, "A1", "A2", list(zip(range(20), range(20))), Mc["A1A2"], Mf["A1A2"], "esym_rescan.png",
				 ["Re-scan com mudanca de pose: A1(f,k) [vermelho] vs A2(f,k) = mesma peca rodada 180 graus [verde]"], (RED, GRN))
	Hc, Hf = Mall[("hibrido", "corner")], Mall[("hibrido", "free")]
	fig_overlays(hyb, "A2", "B2", list(zip(range(20), T)), Hc["A2B2"], Hf["A2B2"], "esym_sobreposicoes_hibrido_A2B2.png",
				 ["Gemeos com pose oposta: A2(f,k) [vermelho] vs B2(f,4-k) [azul], contorno hibrido (limiar simples, inclui sombra)",
				  "A2 = A1 rodada 180 graus: a sombra projetada cai do lado oposto ao de B2 -> numero honesto para pose arbitraria"], (RED, BLUE))
	ser = []
	ar = np.arange(20)
	for mname, M, var in [("corner", Mc, "seg"), ("free", Mf, "seg"), ("corner", Hc, "hibrido"), ("free", Hf, "hibrido")]:
		ntp = [M["A1B2"][i, j] for i in ar for j in ar if j != T[i]] + [M["A1A1"][i, j] for i in ar for j in ar if j > i] + \
			[M["B2B2"][i, j] for i in ar for j in ar if j > i]
		nn = R[var][mname]["per_piece"]
		ser.append((f"{var} {mname}", [("re-scan A1/A2", M["A1A2"][ar, ar], (0, 140, 255)), ("gemeo A1/B2", M["A1B2"][ar, T], RED),
							 ("gemeo A2/B2", M["A2B2"][ar, T], (160, 0, 160)),
							 ("nao-gemeo mais proximo (B2 U A1)", np.array([min(x["nearest_nontwin_B2"], x["nearest_other_A1"]) for x in nn]), GRN),
							 ("todos os pares nao-gemeos das 40", np.array(ntp), GREY)]))
	fig_hist(ser[:2], "esym_histogramas.png", "E-sym segment_pieces: re-scan vs gemeo vs nao-gemeo, 20 pecas de borda (A1, A2, B2)")
	fig_hist(ser[2:], "esym_histogramas_hibrido.png", "E-sym contorno hibrido: re-scan vs gemeo vs nao-gemeo, 20 pecas de borda (A1, A2, B2)")
	fig_matrix([("seg corner", Mc["A1B2"]), ("seg free", Mf["A1B2"]), ("hibrido corner", Hc["A1B2"]), ("hibrido free", Hf["A1B2"])], "esym_matriz.png")
	rb = np.argsort([-p["rough"] for p in seg["B2"]])[:2]
	ra = int(np.argmax([p["rough"] for p in seg["A1"]]))
	fig_fringes(seg, simp, [("B2", int(rb[0])), ("B2", int(rb[1])), ("A1", ra)], "esym_franjas_contorno.png")
	# --- extrapolação (ponto 6): 61 peças de scan_verde (re-análise do .npz atual com analyse_v2), por variante
	vseg = load(os.path.join(sc.SEG, "scan_verde.npz"))
	Vv = {"seg": [p for p in prep([dict(p) for p in vseg]) if p["ok"]],
		  "hibrido": [p for p in prep(hybrid_pieces(os.path.join(sc.REPO, "images", "pieces", "digitalização_fundo_verde.jpg"), vseg)) if p["ok"]]}
	R["extrapolation"] = {}
	Dx = {}
	for var, S in [("seg", seg), ("hibrido", hyb)]:
		V = Vv[var]
		res_tw = {m: dict(A1B2=Mall[(var, m)]["A1B2"][ar, T], A2B2=Mall[(var, m)]["A2B2"][ar, T]) for m in METRICS}
		ext, Dx[var] = extrapolate(S, V, res_tw)
		ext["verde_n_ok"] = len(V)
		ext["verde_classes"] = {c: int(sum(p["cls"] == c for p in V)) for c in sorted(set(p["cls"] for p in V))}
		ext["border_classes_A1B2"] = {c: int(sum(p["cls"] == c for p in S["A1"] + S["B2"])) for c in sorted(set(p["cls"] for p in S["A1"] + S["B2"]))}
		R["extrapolation"][var] = ext
	# --- veredicto M5
	v = {}
	for var, _ in VARS:
		if "corner" not in R.get(var, {}):
			continue
		for mname in METRICS:
			r = R[var][mname]
			for pr, key, tk in [("A1B2", "twin_A1B2", "top1_A1_to_B2"), ("A2B2", "twin_A2B2", "top1_A2_to_B2")]:
				med = r[key]["median"]
				top1 = r[tk] / 20
				v[f"{var}_{mname}_{pr}"] = dict(twin_median_mm=med, top1=top1, viable=bool(med <= 0.7 and top1 >= 0.95))
	R["verdict_M5"] = dict(criterion="RMS gémeo mediano <= 0,7 mm E top-1 >= 95 %", by_variant_metric=v,
						   product_pipeline_seg_viable=bool(all(v[f"seg_{m}_{pr}"]["viable"] for m in METRICS for pr in ("A1B2", "A2B2"))),
						   hibrido_viable=bool(all(v[f"hibrido_{m}_{pr}"]["viable"] for m in METRICS for pr in ("A1B2", "A2B2"))))
	# --- critério M3 (fronteira do M3 pronta para o M10): métrica free, A2/B2 mediano <= 0,5 mm, top-1 20/20
	# (A1->B2, B2->A1, A2->B2) e rugosidade p95 < 1,1 em B2 (prado escuro sobre verde: o pior caso)
	m3 = {}
	for var, _ in VARS:
		if "free" not in R.get(var, {}):
			continue
		r = R[var]["free"]
		rp = R[var]["roughness"]["per_scan"]["B2"]["p95"]
		m3[var] = dict(twin_A2B2_median=r["twin_A2B2"]["median"], top1_A1_to_B2=r["top1_A1_to_B2"], top1_B2_to_A1=r["top1_B2_to_A1"],
					   top1_A2_to_B2=r["top1_A2_to_B2"], rough_p95_B2=rp,
					   meets=bool(r["twin_A2B2"]["median"] <= 0.5 and min(r["top1_A1_to_B2"], r["top1_B2_to_A1"], r["top1_A2_to_B2"]) == 20 and rp < 1.1))
	R["M3"] = m3
	gB2 = cv2.cvtColor(imread_bgr(os.path.join(sc.REPO, sc.SCANS["B2"])), cv2.COLOR_BGR2GRAY)

	def mean_grey(p):
		mk = np.zeros(gB2.shape, np.uint8)
		cv2.fillPoly(mk, [np.round(p["contour"]).astype(np.int32).reshape(-1, 1, 2)], 1)
		return float(gB2[mk > 0].mean())
	dark = np.argsort([mean_grey(p) for p in seg["B2"]])[:3]
	R["B2_darkest_pieces"] = [dict(fk=fk(int(i)), mean_grey=round(mean_grey(seg["B2"][int(i)]), 1)) for i in dark]
	fig_fringes3({"seg": seg["B2"], "hibrido": hyb["B2"], "sombra": sh["B2"], "scan": scn["B2"]}, [int(i) for i in dark], "esym_franjas_sombra_B2.png")
	# --- gravar
	jp = os.path.join(OUT, "results.json")
	J = json.load(open(jp, encoding="utf-8")) if os.path.exists(jp) else {}
	J["esym"] = R
	json.dump(J, open(jp, "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=lambda o: o.item() if hasattr(o, "item") else str(o))
	pickle.dump(dict(seg=seg, simp=simp, hyb=hyb, sombra=sh, scan=scn, V=Vv, D101=Dx), open(os.path.join(WORK, "esym.pkl"), "wb"))
	summary(R)


def summary(R):
	for var in ["seg", "simples", "hibrido", "sombra", "scan"]:
		if "corner" not in R.get(var, {}):
			print(var, R.get(var))
			continue
		for m in METRICS:
			r = R[var][m]
			print(f"[{var:7s} {m:6s}] rescan med {r['rescan_A1A2']['median']:.3f} max {r['rescan_A1A2']['max']:.3f} | "
				  f"twin A1B2 med {r['twin_A1B2']['median']:.3f} p90 {r['twin_A1B2']['p90']:.3f} max {r['twin_A1B2']['max']:.3f} | "
				  f"A2B2 med {r['twin_A2B2']['median']:.3f} max {r['twin_A2B2']['max']:.3f} | nontwin(any) med {r['nearest_nontwin_any']['median']:.3f} "
				  f"min {r['nearest_nontwin_any']['min']:.3f} | top1 {r['top1_A1_to_B2']}/20 A2 {r['top1_A2_to_B2']} B2->A1 {r['top1_B2_to_A1']} "
				  f"pool39 {r['top1_pool39']} mutual {r['mutual_nn']} margin<1.5: {len(r['pieces_margin_lt_1_5'])} margin min {r['margin_any']['min']}")
		cq = R[var]["corner_quad"]
		print(f"[{var:7s} geom  ] side chord median (mm) " + " ".join(f"{n} {cq[n]['side_len']['median']:.2f}" for n in NAMES) +
			  " | roughness p95 " + " ".join(f"{n} {R[var]['roughness']['per_scan'][n]['p95']:.3f}" for n in NAMES))
	print("quick replica", json.dumps(R["quick_replica"], default=str)[:700])
	print("verdict", R["verdict_M5"])
	for var, v in R.get("M3", {}).items():
		print("M3", var, v)


if __name__ == "__main__":
	main()
