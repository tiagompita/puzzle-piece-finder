"""M14 (protótipo): mapa de ocupação do tabuleiro a partir de uma foto de telemóvel.

Diagnóstico (não é código de produção). Correr a partir da raiz do repositório:

	PowerShell:  $env:PYTHONIOENCODING = "utf-8"
	python tools/diagnostico/ocupacao/ocupacao.py [a] [b]

Entrada: images/board/mapa_2026-10-31_{a,b}.jpg (puzzle inteiro sobre o tapete de feltro, borda completa segundo
images/board/README.md). Saídas em docs/diagnostico/ocupacao/ e a chave "ocupacao" de
docs/diagnostico/gemeos/results.json (só essa chave; o ficheiro é relido imediatamente antes de escrever). Ver OCUPACAO.md.

Passo 1 (moldura), imagem a FRAME_W px de largura:
  máscara "não feltro" = ΔE ao feltro depois de dividir (RGB linear) por um fundo de feltro de máximo local (≈ 4
  células); por lado, primeira transição feltro -> peça vinda de fora (>= RUN_FELT px de feltro, >= RUN_PIECE px de
  peça: a madeira para lá do tapete e o texto impresso não passam); correção da sombra projetada (o ponto anda para
  dentro até à primeira peça cromática, <= SHADOW_MAX px); RANSAC + mínimos quadrados -> 4 retas -> 4 cantos ->
  homografia para a imagem canónica 64 x 47 células. Resíduos às retas e curvatura (parábola) em px e células.
  Refinamento da grelha: energia de linhas escuras (black-hat) projetada SÓ no anel de borda (filas 1/47 -> x,
  colunas 1/64 -> y), pico por linha de corte, desvio à grelha uniforme; a correção linear (fase + passo) interpolada
  entre perfis opostos só é usada num eixo se baixar o RMS leave-one-out.
Passo 2 (classificação), imagem retificada a CLS_W px/célula (a partir da foto a 50 %) com orla de CLS_MARGIN células:
  modelo LOCAL do feltro (polinómio 2-D em RGB linear, ajuste robusto a 2σ): 1.ª passagem grau 2 só na orla exterior
  (como pedido); 2.ª passagem grau FELT_DEG2 na orla + células interiores que a 1.ª passagem dá como feltro limpo
  (a luz da janela faz o feltro do centro até ~2x mais claro que o grau 2 da orla prevê; medido, ver OCUPACAO.md).
  Imagem dividida pelo feltro (o feltro fica neutro, o gradiente sai). Por célula, região central CENTRE_FRAC:
  mediana Lab, σ L*, fração de píxeis iguais ao feltro (ft); ΔE_feltro (dEs: só escurecimento + croma, porque as peças
  são sempre mais escuras ou mais saturadas que o feltro); ΔE_arte (desvio fotométrico global nas 218 de borda).
  Regra A (enunciado): d = ΔE_feltro - ΔE_arte contra ±MARGEM -> 76-78 % na GT (falha; ver OCUPACAO.md).
  Regra B (usada): ver decide().
Limite: a foto dá OCUPAÇÃO, não forma; não substitui digitalizar soltas as peças de relva legadas.
"""
import os
import sys
import json
import time

import numpy as np
import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUT = os.path.join(REPO, "docs", "diagnostico", "ocupacao")
RESULTS = os.path.join(REPO, "docs", "diagnostico", "gemeos", "results.json")
F_PHOTO = {k: os.path.join(REPO, "images", "board", f"mapa_2026-10-31_{k}.jpg") for k in ("a", "b")}
F_ART = os.path.join(REPO, "images", "puzzles", "1186441_1.jpg")

# --- perfil do puzzle (M13: virá de puzzle.json) ---
NCOL, NROW = 64, 47                     # célula (l, c): l = 1..47 de cima, c = 1..64 da esquerda
CELL_MM = (18.5, 17.9)                  # célula nominal (largura, altura) em mm
ART_Y0, ART_W, ART_H = 42, 1600, 1115   # a arte limpa ocupa as linhas 42-1156 do ficheiro (≈ 25,0 x 23,72 px/célula)

# --- passo 1: moldura ---
FRAME_W = 2000          # largura de trabalho (px)
RB_SUB, RB_KERNEL = 8, 15   # fundo de máximo local: subamostragem 8, núcleo 15 (≈ 120 px ≈ 4,4 células)
FRAME_DE = 15.0         # ΔE ao feltro normalizado acima do qual o píxel é "não feltro"
RUN_FELT = 6            # px de feltro antes da transição
RUN_PIECE = 14          # px de não feltro depois (≈ 0,5 célula)
SHADOW_MAX = 14         # px: procura para dentro da primeira peça cromática (sombra projetada à frente da peça)
SHADOW_CHROMA = 10.0    # croma (a*, b* normalizados) acima do qual o píxel é peça e não sombra
SHADOW_RUN = 4
RANSAC_TOL = 1.5        # px
RESID_POLY_CELLS = 0.25 # acima disto corrigir-se-ia por polinómio de 2.ª ordem por lado (não foi preciso)
SIDES = ("top", "right", "bottom", "left")
CAN_W = 40.0            # imagem canónica da grelha: px por célula
CAN_H = CAN_W * CELL_MM[1] / CELL_MM[0]
PEAK_CONTRAST = 1.5     # pico da projeção / mediana da janela: abaixo disto a linha de corte não se vê
PEAK_EDGE = 0.28        # |desvio| >= 0,28 célula = pico encostado ao limite da janela (±0,3) = falso pico

# --- passo 2: classificação ---
CLS_SCALE = 0.5         # foto a 50 %
CLS_W = 55.0            # px por célula na imagem retificada de classificação
CLS_H = CLS_W * CELL_MM[1] / CELL_MM[0]
CLS_MARGIN = 3          # células de orla exterior na imagem retificada
CENTRE_FRAC = 0.6       # região central usada (evita as abas das vizinhas)
FELT_BAND = (0.3, 2.6)  # orla exterior (células) usada no modelo do feltro
POLY_DEG = 2            # 1.ª passagem (enunciado)
FELT_DEG2 = 4           # 2.ª passagem
FELT_SIGMA = 2.0        # rejeição iterativa a 2σ
NORM_GAIN = 0.3         # feltro normalizado -> RGB linear 0,3 (L* ≈ 62): folga até 3,3x
FELT_PIX_AB = 6.0       # píxel de feltro: |a*b*| ao feltro < 6 ...
FELT_PIX_L = 12.0       # ... e |ΔL*| < 12
SEED_CHROMA, SEED_SL, SEED_DL = 2.5, 7.0, 40.0   # célula semente de feltro para a 2.ª passagem
DEF_EMPTY = 6.0         # regra B: ΔE_feltro (só escurecimento + croma) <= isto -> vazia
DEF_FULL = 10.0         # regra B: >= isto -> cheia (se não se vir feltro, FT_MAX)
ART_OK = 15.0           # regra B, zona intermédia: ΔE_arte <= isto -> cheia
FT_L, FT_AB = 8.0, 4.0  # píxel "igual ao feltro": |ΔL*| < 8 e |a*b*| < 4
FT_MAX = 0.06           # fração de píxeis iguais ao feltro acima da qual a janela central não é uma peça inteira
FT_EMPTY = 0.5          # metade da janela central igual ao feltro: nenhuma peça a cobre (uma aba vizinha ou um
                        # desalinhamento de 0,2 célula cobrem no máximo ≈ 1/3 da janela) -> vazia
MARGEM = 10.0           # regra A: |ΔE_feltro - ΔE_arte| < MARGEM -> incerta

LOG = []


def log(*a):
	s = " ".join(str(x) for x in a)
	LOG.append(s)
	print(s, flush=True)


# ----------------------------------------------------------------------------- utilitários
def read_bgr(path):
	return cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)


def imwrite(path, img, q=90):
	ok, buf = cv2.imencode(os.path.splitext(path)[1], img, [cv2.IMWRITE_JPEG_QUALITY, q])
	buf.tofile(path)


def ell(d):
	return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (int(d), int(d)))


def srgb_to_lin(x):
	x = x.astype(np.float32) / 255.0
	return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4).astype(np.float32)


def lin_to_lab(lin_bgr):
	"""RGB linear (BGR; satura em 1) -> Lab float (L* 0..100) via sRGB."""
	x = np.clip(lin_bgr, 0, 1.0).astype(np.float32)
	s = np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055).astype(np.float32)
	return cv2.cvtColor(s, cv2.COLOR_BGR2LAB)


def poly_design(x, y, deg=POLY_DEG):
	return np.stack([x ** i * y ** j for i in range(deg + 1) for j in range(deg + 1 - i)], 1)


def fit_felt(x, y, vals, keep0, iters=15, sig=FELT_SIGMA, deg=POLY_DEG):
	"""Polinómio 2-D por canal com rejeição iterativa a sig·σ (em qualquer canal). Devolve (coef, keep, σ)."""
	A = poly_design(x, y, deg)
	keep = keep0.copy()
	for _ in range(iters):
		coef = np.linalg.lstsq(A[keep], vals[keep], rcond=None)[0]
		r = vals - A @ coef
		s = r[keep].std(0)
		new = keep0 & np.all(np.abs(r) < sig * s, 1)
		if np.array_equal(new, keep):
			break
		keep = new
	return coef, keep, s


# ----------------------------------------------------------------------------- verdade de terreno e arte
def gt_cells():
	"""images/board/README.md: {(l, c): 1 cheia / 0 vazia} -> 218 de borda + (2,61) cheias, 25 vazias."""
	gt = {}
	for c in range(1, NCOL + 1):
		gt[(1, c)] = 1; gt[(NROW, c)] = 1
	for l in range(1, NROW + 1):
		gt[(l, 1)] = 1; gt[(l, NCOL)] = 1
	gt[(2, 61)] = 1
	empty = [(42, 58), (42, 59)] + [(41, c) for c in range(58, 64)]
	empty += [(44, 6), (44, 7), (43, 6), (43, 7)] + [(42, c) for c in range(2, 8)] + [(41, c) for c in range(2, 8)]
	empty += [(5, 60)]
	for k in empty:
		gt[k] = 0
	return gt


# Correções à GT do README vistas nas duas fotos (1.º mosaico de ocupacao_<a|b>_celulas.jpg: feltro à vista em toda
# a largura da célula); a confirmar fisicamente pelo Tiago.
GT_VISUAL = {(1, 29): 0}


def border_mask():
	B = np.zeros((NROW, NCOL), bool)
	B[0, :] = B[-1, :] = B[:, 0] = B[:, -1] = True
	return B


def art_cells():
	"""Mediana Lab da região central (CENTRE_FRAC) de cada célula da arte limpa -> 47 x 64 x 3
	(mesma convenção de ereal2.py: x0 = (c-1)·25,0, y0 = 42 + (l-1)·23,72)."""
	art = read_bgr(F_ART)
	if art.shape[:2] != (1200, 1600):
		raise SystemExit(f"[ocupacao] arte limpa com tamanho inesperado {art.shape}")
	lab = cv2.cvtColor(art[ART_Y0:ART_Y0 + ART_H, :ART_W].astype(np.float32) / 255.0, cv2.COLOR_BGR2LAB)
	cw, ch = ART_W / NCOL, ART_H / NROW
	h = (1 - CENTRE_FRAC) / 2
	out = np.zeros((NROW, NCOL, 3), np.float32)
	for l in range(NROW):
		for c in range(NCOL):
			x0, x1 = int(round((c + h) * cw)), int(round((c + 1 - h) * cw))
			y0, y1 = int(round((l + h) * ch)), int(round((l + 1 - h) * ch))
			out[l, c] = np.median(lab[y0:y1, x0:x1].reshape(-1, 3), 0)
	return out


# ----------------------------------------------------------------------------- passo 1: moldura
def rolling_bg(lin):
	"""Fundo do feltro não paramétrico (só para a moldura): máximo local por canal em RGB linear, suavizado.
	Válido junto ao feltro; no interior de blocos grandes de peças não (por isso não serve para classificar)."""
	H, W = lin.shape[:2]
	sm = cv2.resize(lin, (W // RB_SUB, H // RB_SUB), interpolation=cv2.INTER_AREA)
	sm = cv2.GaussianBlur(sm, (0, 0), 1.0)
	bg = cv2.blur(cv2.dilate(sm, ell(RB_KERNEL)), (RB_KERNEL, RB_KERNEL))
	return cv2.resize(bg, (W, H), interpolation=cv2.INTER_LINEAR)


def frame_mask(img):
	"""Máscara "não feltro" (bool), ΔE e croma no espaço normalizado pelo fundo de feltro local."""
	lin = srgb_to_lin(img)
	lab = lin_to_lab(lin / np.maximum(rolling_bg(lin), 1e-3) * 0.9)
	d = lab - np.median(lab.reshape(-1, 3), 0)
	dE = np.sqrt((d ** 2).sum(-1))
	m = (dE > FRAME_DE).astype(np.uint8)
	m = cv2.morphologyEx(m, cv2.MORPH_OPEN, ell(3))
	m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, ell(5))
	return m.astype(bool), dE, np.hypot(d[..., 1], d[..., 2])


def orient(m, side):
	"""Vista da máscara com o lado pedido à esquerda (varrimento ao longo do eixo 1 a partir de 0)."""
	return {"left": m, "right": m[:, ::-1], "top": m.T, "bottom": m[::-1, :].T}[side]


def outer_points(mask, side):
	"""Primeira transição feltro -> não feltro vinda de fora, por linha/coluna. Devolve (t, d) com t o índice da
	linha (left/right) ou coluna (top/bottom) e d a coordenada da transição na imagem."""
	m = orient(mask.astype(np.int32), side)
	n, L = m.shape
	cs = np.concatenate([np.zeros((n, 1), np.int32), np.cumsum(m, 1)], 1)
	j = np.arange(RUN_FELT, L - RUN_PIECE)
	ok = ((cs[:, j] - cs[:, j - RUN_FELT]) == 0) & ((cs[:, j + RUN_PIECE] - cs[:, j]) == RUN_PIECE)
	t = np.nonzero(ok.any(1))[0]
	d = j[ok[t].argmax(1)].astype(float)
	if side == "right":
		d = mask.shape[1] - 1 - d
	elif side == "bottom":
		d = mask.shape[0] - 1 - d
	return t.astype(float), d


def shadow_refine(t, d, chroma, side):
	"""Desloca cada ponto para dentro, até SHADOW_MAX px, para o início da primeira série de SHADOW_RUN px com croma
	> SHADOW_CHROMA: a sombra projetada é feltro escurecido (neutro) e a máscara de ΔE inclui-a. Pontos sem peça
	cromática na janela ficam onde estavam. Devolve (d corrigido, deslocamento)."""
	c = orient(chroma, side)
	j0 = (c.shape[1] - 1 - d) if side in ("right", "bottom") else d
	shift = np.zeros(len(t))
	for i, (ti, ji) in enumerate(zip(t.astype(int), j0.astype(int))):
		seg = c[ti, ji:ji + SHADOW_MAX + SHADOW_RUN] > SHADOW_CHROMA
		run = np.convolve(seg.astype(int), np.ones(SHADOW_RUN, int), "valid") == SHADOW_RUN
		if run.any():
			shift[i] = int(np.argmax(run))
	return (d - shift if side in ("right", "bottom") else d + shift), shift


def ransac_line(t, d, tol=RANSAC_TOL, iters=3000, seed=0):
	"""d = s·t + d0 robusto: RANSAC (2 pontos) + mínimos quadrados nos inliers."""
	rng = np.random.default_rng(seed)
	best = (-1, None)
	for _ in range(iters):
		i, j = rng.choice(len(t), 2, replace=False)
		if abs(t[j] - t[i]) < 20:
			continue
		s = (d[j] - d[i]) / (t[j] - t[i])
		inl = np.abs(d - (d[i] + s * (t - t[i]))) < tol
		if inl.sum() > best[0]:
			best = (int(inl.sum()), inl)
	inl = best[1]
	for _ in range(3):
		s, d0 = np.polyfit(t[inl], d[inl], 1)
		inl = np.abs(d - (s * t + d0)) < tol
	s, d0 = np.polyfit(t[inl], d[inl], 1)
	return float(s), float(d0), inl


def to_xy(side, t, d):
	return np.c_[d, t] if side in ("left", "right") else np.c_[t, d]


def line_hom(side, s, d0):
	if side in ("left", "right"):
		return np.array([1.0, -s, -d0])      # x = s y + d0
	return np.array([-s, 1.0, -d0])          # y = s x + d0


def intersect(l1, l2):
	p = np.cross(l1, l2)
	return p[:2] / p[2]


def fit_frame(mask, chroma):
	"""4 retas robustas -> cantos TL, TR, BR, BL (px da imagem da moldura) + diagnóstico por lado."""
	lines, info = {}, {}
	for side in SIDES:
		t, d = outer_points(mask, side)
		d, shift = shadow_refine(t, d, chroma, side)
		s, d0, inl = ransac_line(t, d)
		lines[side] = line_hom(side, s, d0)
		info[side] = dict(t=t, d=d, inl=inl, r=d - (s * t + d0), shift=shift)
	C = np.array([intersect(lines["top"], lines["left"]), intersect(lines["top"], lines["right"]),
		intersect(lines["bottom"], lines["right"]), intersect(lines["bottom"], lines["left"])])
	return C, info


def side_residuals(C, info, cell_px):
	"""Por lado, só entre os dois cantos: inliers, RMS dos inliers, p90 |r| de todos os pontos, curvatura = desvio
	máximo da parábola ajustada aos inliers em relação à reta (px e células), deslocamento mediano da sombra."""
	span = {"top": (C[0, 0], C[1, 0]), "bottom": (C[3, 0], C[2, 0]), "left": (C[0, 1], C[3, 1]), "right": (C[1, 1], C[2, 1])}
	out = {}
	for side in SIDES:
		i = info[side]
		lo, hi = sorted(span[side])
		w = (i["t"] >= lo) & (i["t"] <= hi)
		inl = i["inl"] & w
		r = i["r"]
		pc = np.polyfit(i["t"][inl], r[inl], 2)
		curv = float(np.abs(np.polyval(pc, np.linspace(lo, hi, 200))).max())
		rms = float(np.sqrt((r[inl] ** 2).mean()))
		out[side] = dict(n_pontos=int(w.sum()), frac_inliers=round(float(inl.sum() / max(w.sum(), 1)), 3),
			rms_inliers_px=round(rms, 2), rms_inliers_celulas=round(rms / cell_px, 3),
			p90_todos_px=round(float(np.percentile(np.abs(r[w]), 90)), 2),
			curvatura_px=round(curv, 2), curvatura_celulas=round(curv / cell_px, 3),
			sombra_mediana_px=float(np.median(i["shift"][inl])))
	return out


def homography(C, cw, ch, margin=0.0):
	"""Homografia dos cantos (TL, TR, BR, BL) para o retângulo 64·cw x 47·ch com orla de margin células."""
	ox, oy = margin * cw, margin * ch
	dst = np.array([[ox, oy], [ox + NCOL * cw, oy], [ox + NCOL * cw, oy + NROW * ch], [ox, oy + NROW * ch]], np.float32)
	return cv2.getPerspectiveTransform(C.astype(np.float32), dst)


def fig_frame(img, C, info, path):
	vis = img.copy()
	for side in SIDES:
		i = info[side]
		P = to_xy(side, i["t"], i["d"])
		for (x, y), ok in zip(P[::2].astype(int), i["inl"][::2]):
			cv2.circle(vis, (int(x), int(y)), 1, (0, 255, 0) if ok else (0, 0, 255), -1)
	for k in range(4):
		a, b = C[k], C[(k + 1) % 4]
		cv2.line(vis, tuple(np.round(a).astype(int)), tuple(np.round(b).astype(int)), (255, 255, 0), 1, cv2.LINE_AA)
		cv2.circle(vis, tuple(np.round(a).astype(int)), 10, (255, 0, 255), 2)
	cv2.putText(vis, "verde = inliers, vermelho = outliers, ciano = retas, magenta = cantos", (20, img.shape[0] - 20),
		cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
	imwrite(path, vis)


# ----------------------------------------------------------------------------- refinamento da grelha
def peak_positions(P, pitch, n, win=0.3):
	"""Para k = 1..n-1, pico de P em ±win·pitch da posição nominal k·pitch (sub-píxel) e contraste pico/mediana."""
	out = []
	for k in range(1, n):
		x = k * pitch
		a, b = int(np.floor(x - win * pitch)), int(np.ceil(x + win * pitch))
		seg = P[a:b + 1]
		j = int(np.argmax(seg))
		off = 0.0
		if 0 < j < len(seg) - 1:
			den = seg[j - 1] - 2 * seg[j] + seg[j + 1]
			off = 0.5 * (seg[j - 1] - seg[j + 1]) / den if den != 0 else 0.0
		out.append((a + j + off - x, float(seg[j] / (np.median(seg) + 1e-6))))
	return np.array(out)


def loo_linear(k, dev):
	e = []
	for i in range(len(k)):
		m = np.ones(len(k), bool); m[i] = False
		e.append(dev[i] - np.polyval(np.polyfit(k[m], dev[m], 1), k[i]))
	return float(np.sqrt(np.mean(np.square(e))))


def grid_refine(rect_bgr, cw, ch):
	"""Linhas de corte no anel de borda contra a grelha uniforme (px da imagem canónica de CAN_W px/célula)."""
	L = cv2.cvtColor(rect_bgr, cv2.COLOR_BGR2LAB)[..., 0].astype(np.float32)
	R = cv2.morphologyEx(L, cv2.MORPH_BLACKHAT, ell(7))
	prof = {"fila1": ("x", 0), "fila47": ("x", NROW - 1), "col1": ("y", 0), "col64": ("y", NCOL - 1)}
	res = {}
	for nm, (ax, band) in prof.items():
		if ax == "x":
			P = R[int((band + 0.15) * ch):int((band + 0.85) * ch)].mean(0); pitch, n = cw, NCOL
		else:
			P = R[:, int((band + 0.15) * cw):int((band + 0.85) * cw)].mean(1); pitch, n = ch, NROW
		pk = peak_positions(P, pitch, n)
		dev, con = pk[:, 0], pk[:, 1]
		good = (con > PEAK_CONTRAST) & (np.abs(dev) < PEAK_EDGE * pitch)
		k = np.arange(1, n)[good].astype(float)
		d = dev[good]
		c = np.polyfit(k, d, 1)
		res[nm] = dict(eixo=ax, n_linhas=int(good.sum()), de=int(n - 1),
			rms_uniforme_px=round(float(np.sqrt((d ** 2).mean())), 2), mediana_px=round(float(np.median(d)), 2),
			fase_px=round(float(c[1]), 2), erro_passo_px_por_celula=round(float(c[0]), 4),
			rms_linear_loo_px=round(loo_linear(k, d), 2), coef=[float(c[0]), float(c[1])],
			desvios_px=[round(float(x), 2) if g else None for x, g in zip(dev, good)])
	dec = {}
	for ax, (p1, p2) in {"x": ("fila1", "fila47"), "y": ("col1", "col64")}.items():
		u = (res[p1]["rms_uniforme_px"] + res[p2]["rms_uniforme_px"]) / 2
		l = (res[p1]["rms_linear_loo_px"] + res[p2]["rms_linear_loo_px"]) / 2
		dec[ax] = dict(usar=bool(l < u), rms_uniforme_px=round(u, 2), rms_refinado_loo_px=round(l, 2),
			rms_uniforme_celulas=round(u / (cw if ax == "x" else ch), 3))
	return res, dec


def boundaries(cw, ch, refine=None, dec=None):
	"""Fronteiras da grelha (imagem canónica sem orla) como funções: xb(k, y), k = 0..64; yb(k, x), k = 0..47.
	Uniforme, ou com a correção linear de grid_refine interpolada entre perfis opostos nos eixos aceites
	(coeficientes medidos a CAN_W px/célula, reescalados). Os lados exteriores ficam presos à moldura."""
	use = {ax: refine is not None and dec[ax]["usar"] for ax in ("x", "y")}
	sx, sy = cw / CAN_W, ch / CAN_H

	def corr(p1, p2, n, k, f, s):
		k = np.asarray(k, float)
		c1, c2 = np.polyval(refine[p1]["coef"], k), np.polyval(refine[p2]["coef"], k)
		return np.where((k > 0) & (k < n), s * ((1 - f) * c1 + f * c2), 0.0)

	def xb(k, y):
		f = np.clip(y / (NROW * ch), 0, 1)
		return k * cw + (corr("fila1", "fila47", NCOL, k, f, sx) if use["x"] else 0.0)

	def yb(k, x):
		f = np.clip(x / (NCOL * cw), 0, 1)
		return k * ch + (corr("col1", "col64", NROW, k, f, sy) if use["y"] else 0.0)
	return xb, yb


# ----------------------------------------------------------------------------- passo 2: classificação
def rectify_cls(half, C_half):
	Hc = homography(C_half, CLS_W, CLS_H, margin=CLS_MARGIN)
	W = int(round((NCOL + 2 * CLS_MARGIN) * CLS_W)); H = int(round((NROW + 2 * CLS_MARGIN) * CLS_H))
	rect = cv2.warpPerspective(half, Hc, (W, H), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0))
	valid = cv2.warpPerspective(np.full(half.shape[:2], 255, np.uint8), Hc, (W, H), flags=cv2.INTER_NEAREST) > 0
	return rect, valid, Hc


def felt_model(lin, valid, extra=None, deg=POLY_DEG, st=3):
	"""Modelo LOCAL do feltro (RGB linear, polinómio de grau deg, 2σ) na orla exterior FELT_BAND (+ máscara extra).
	Devolve a imagem normalizada em Lab (feltro -> NORM_GAIN), a cor de referência do feltro e diagnóstico."""
	H, W = lin.shape[:2]
	mx, my = CLS_MARGIN * CLS_W, CLS_MARGIN * CLS_H
	ys, xs = np.mgrid[0:H:st, 0:W:st]
	u = np.maximum(np.maximum(mx - xs, xs - (W - mx)) / CLS_W, np.maximum(my - ys, ys - (H - my)) / CLS_H)
	band = (u > FELT_BAND[0]) & (u < FELT_BAND[1]) & valid[::st, ::st]
	if extra is not None:
		band = band | extra[::st, ::st]
	v = lin[::st, ::st].reshape(-1, 3)
	coef, keep, sig = fit_felt(xs.ravel() / W, ys.ravel() / H, v, band.ravel(), deg=deg)
	q = 4
	yq, xq = np.mgrid[0:H:q, 0:W:q]
	pred = (poly_design(xq.ravel() / W, yq.ravel() / H, deg) @ coef).reshape(yq.shape + (3,)).astype(np.float32)
	pred = cv2.resize(pred, (W, H), interpolation=cv2.INTER_LINEAR)
	norm = lin_to_lab(lin / np.maximum(pred, 1e-3) * NORM_GAIN)
	ref = np.median(norm[::st, ::st].reshape(-1, 3)[keep], 0)
	return norm, ref, dict(grau=deg, n_pix=int(band.sum()), frac_mantida=round(float(keep.sum() / max(band.sum(), 1)), 3),
		sigma_rel=[round(float(x), 4) for x in sig / np.median(v[keep], 0)])


def cell_boxes(xb, yb):
	"""Região central (CENTRE_FRAC) de cada célula na imagem de classificação (px com orla): [x0, x1, y0, y1]."""
	mx, my = CLS_MARGIN * CLS_W, CLS_MARGIN * CLS_H
	h = (1 - CENTRE_FRAC) / 2
	boxes = np.zeros((NROW, NCOL, 4), int)
	for l in range(NROW):
		for c in range(NCOL):
			yc, xc = (l + 0.5) * CLS_H, (c + 0.5) * CLS_W
			xa, xz = xb(c, yc), xb(c + 1, yc)
			ya, yz = yb(l, xc), yb(l + 1, xc)
			boxes[l, c] = [int(round(mx + xa + h * (xz - xa))), int(round(mx + xz - h * (xz - xa))),
				int(round(my + ya + h * (yz - ya))), int(round(my + yz - h * (yz - ya)))]
	return boxes


def cell_features(norm, ref, boxes):
	"""Por célula: mediana Lab - feltro (ΔL, Δa, Δb), σ L*, fração de píxeis de feltro (largo, FELT_PIX_*) e fração
	de píxeis iguais ao feltro (apertado, FT_*: numa peça inteira é ≈ 0; texto impresso sobre feltro deixa-o ver)."""
	med = np.zeros((NROW, NCOL, 3)); sL = np.zeros((NROW, NCOL)); ff = np.zeros((NROW, NCOL)); ft = np.zeros((NROW, NCOL))
	for l in range(NROW):
		for c in range(NCOL):
			x0, x1, y0, y1 = boxes[l, c]
			q = norm[y0:y1, x0:x1].reshape(-1, 3) - ref
			med[l, c] = np.median(q, 0)
			sL[l, c] = q[:, 0].std()
			ab = np.hypot(q[:, 1], q[:, 2])
			ff[l, c] = float(((ab < FELT_PIX_AB) & (np.abs(q[:, 0]) < FELT_PIX_L)).mean())
			ft[l, c] = float(((ab < FT_AB) & (np.abs(q[:, 0]) < FT_L)).mean())
	return med, sL, ff, ft


def seed_mask(shape, boxes, med, sL):
	"""Píxeis das células interiores com aspeto de feltro limpo na 1.ª passagem (sementes da 2.ª passagem)."""
	ex = np.zeros(shape, bool)
	seed = (np.hypot(med[..., 1], med[..., 2]) < SEED_CHROMA) & (sL < SEED_SL) & (np.abs(med[..., 0]) < SEED_DL)
	for l, c in zip(*np.nonzero(seed)):
		x0, x1, y0, y1 = boxes[l, c]
		ex[y0:y1, x0:x1] = True
	return ex, int(seed.sum())


def decide(dEs, ft, dEf, dEa):
	"""Regra B (usada): dEs = ΔE ao feltro contando só o escurecimento e a croma (as peças são sempre mais escuras ou
	mais saturadas que o feltro; feltro mais claro que o modelo é resíduo de iluminação, não peça).
	dEs <= DEF_EMPTY, ou ft >= FT_EMPTY com dEs < DEF_FULL -> vazia; dEs >= DEF_FULL e ft < FT_MAX -> cheia; zona intermédia sem feltro visível e
	ΔE_arte <= ART_OK -> cheia; o resto (escuro mas com feltro visível: texto impresso, aba de vizinha, desalinhamento;
	ou intermédio sem apoio da arte) -> incerta.
	Regra A (enunciado): d = ΔE_feltro - ΔE_arte contra ±MARGEM. 1 cheia, 0 vazia, -1 incerta; confiança 0..1 (B)."""
	B = np.full(dEs.shape, -1, int)
	nofelt = ft < FT_MAX
	B[(dEs >= DEF_FULL) & nofelt] = 1
	B[dEs <= DEF_EMPTY] = 0
	B[(ft >= FT_EMPTY) & (dEs < DEF_FULL)] = 0
	mid = (dEs > DEF_EMPTY) & (dEs < DEF_FULL)
	B[mid & nofelt & (dEa <= ART_OK)] = 1
	confB = np.where(B == 1, np.clip(0.5 + (dEs - DEF_FULL) / (2 * DEF_FULL), 0.5, 1) * np.clip(1 - ft / FT_MAX, 0, 1) ** 0.5,
		np.where(B == 0, np.maximum(np.clip(0.5 + (DEF_EMPTY - dEs) / (2 * DEF_EMPTY), 0.5, 1), np.clip(ft, 0, 1)), 0.0))
	d = dEf - dEa
	A = np.where(d > MARGEM, 1, np.where(d < -MARGEM, 0, -1))
	return B, np.round(confB, 2), A, d


def confusion(pred, gt):
	cm = {"cheia->cheia": 0, "cheia->vazia": 0, "cheia->incerta": 0, "vazia->vazia": 0, "vazia->cheia": 0, "vazia->incerta": 0}
	wrong = []
	for (l, c), g in sorted(gt.items()):
		p = int(pred[l - 1, c - 1])
		key = ("cheia" if g else "vazia") + "->" + {1: "cheia", 0: "vazia", -1: "incerta"}[p]
		cm[key] += 1
		if p != g:
			wrong.append([l, c, g, p])
	n = len(gt)
	ok = cm["cheia->cheia"] + cm["vazia->vazia"]
	return dict(matriz=cm, n=n, certas=ok, exatidao=round(ok / n, 4), erradas_lcgp=wrong)


# ----------------------------------------------------------------------------- figuras
def cell_polys(Hinv_can, xb, yb, scale):
	"""Polígono de cada célula (4 cantos) na foto à escala 'scale' (Hinv_can: canónica CLS sem orla -> foto 50 %)."""
	P = np.zeros((NROW, NCOL, 4, 2), np.float32)
	for l in range(NROW):
		for c in range(NCOL):
			ya, yz = (l) * CLS_H, (l + 1) * CLS_H
			xa, xz = c * CLS_W, (c + 1) * CLS_W
			pts = [(xb(c, ya), yb(l, xa)), (xb(c + 1, ya), yb(l, xz)), (xb(c + 1, yz), yb(l + 1, xz)), (xb(c, yz), yb(l + 1, xa))]
			P[l, c] = np.array(pts, np.float32)
	Q = cv2.perspectiveTransform(P.reshape(-1, 1, 2), Hinv_can).reshape(NROW, NCOL, 4, 2)
	return Q * scale


def fig_overlay(img, polys, occ, path, gt=None):
	col = {1: (0, 200, 0), 0: (0, 0, 230), -1: (0, 220, 255)}
	fill = img.copy()
	for l in range(NROW):
		for c in range(NCOL):
			cv2.fillPoly(fill, [np.round(polys[l, c]).astype(np.int32)], col[int(occ[l, c])])
	vis = cv2.addWeighted(fill, 0.25, img, 0.75, 0)
	for l in range(NROW):
		for c in range(NCOL):
			cv2.polylines(vis, [np.round(polys[l, c]).astype(np.int32)], True, (60, 60, 60), 1)
	if gt is not None:
		for (l, c), g in gt.items():
			if int(occ[l - 1, c - 1]) != g:
				cv2.polylines(vis, [np.round(polys[l - 1, c - 1]).astype(np.int32)], True, (255, 0, 255), 3)
	cv2.putText(vis, "verde = cheia, vermelho = vazia, amarelo = incerta, magenta = erro contra a GT", (20, img.shape[0] - 20),
		cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
	imwrite(path, vis)


def fig_cells(rect, boxes, cells, labels, path):
	"""Mosaico de células (imagem retificada de classificação, 3,4 x a janela central; retângulo vermelho = janela)."""
	tiles = []
	for (l, c), lab in zip(cells, labels):
		x0, x1, y0, y1 = boxes[l - 1, c - 1]
		w, h = x1 - x0, y1 - y0
		X0, Y0 = max(x0 - int(1.2 * w), 0), max(y0 - int(1.2 * h), 0)
		t = rect[Y0:Y0 + int(3.4 * h), X0:X0 + int(3.4 * w)].copy()
		cv2.rectangle(t, (x0 - X0, y0 - Y0), (x1 - X0, y1 - Y0), (0, 0, 255), 1)
		t = cv2.resize(t, (240, 230))
		cv2.rectangle(t, (0, 0), (240, 34), (255, 255, 255), -1)
		cv2.putText(t, f"({l},{c}) {lab[0]}", (3, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
		cv2.putText(t, lab[1], (3, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
		tiles.append(t)
	rows = [np.hstack(tiles[i:i + 6] + [np.full((230, 240, 3), 255, np.uint8)] * (6 - len(tiles[i:i + 6]))) for i in range(0, len(tiles), 6)]
	imwrite(path, np.vstack(rows))


def fig_rect(rect40, xb40, yb40, path):
	vis = rect40.copy()
	H, W = vis.shape[:2]
	for k in range(NCOL + 1):
		pts = np.array([[xb40(k, y), y] for y in np.linspace(0, H, 30)], np.int32)
		cv2.polylines(vis, [pts], False, (0, 0, 255), 1)
	for k in range(NROW + 1):
		pts = np.array([[x, yb40(k, x)] for x in np.linspace(0, W, 40)], np.int32)
		cv2.polylines(vis, [pts], False, (0, 0, 255), 1)
	imwrite(path, vis)


# ----------------------------------------------------------------------------- pipeline
def run(name, art, gt):
	t0 = time.time()
	full = read_bgr(F_PHOTO[name])
	if full is None:
		return {"error": f"não consegui ler {F_PHOTO[name]}"}
	sc = FRAME_W / full.shape[1]
	img = cv2.resize(full, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA)
	mask, _, chroma = frame_mask(img)
	C, info = fit_frame(mask, chroma)
	cell_px = float(np.mean([np.linalg.norm(C[1] - C[0]) / NCOL, np.linalg.norm(C[2] - C[3]) / NCOL,
		np.linalg.norm(C[3] - C[0]) / NROW, np.linalg.norm(C[2] - C[1]) / NROW]))
	sr = side_residuals(C, info, cell_px)
	worst = max(v["rms_inliers_celulas"] for v in sr.values())
	worst_curv = max(v["curvatura_celulas"] for v in sr.values())
	log(f"[{name}] cantos (px da foto): {np.round(C / sc, 1).tolist()}; célula ≈ {cell_px / sc:.1f} px na foto")
	for s in SIDES:
		log(f"[{name}]   {s:6s} {sr[s]}")
	if max(worst, worst_curv) > RESID_POLY_CELLS:
		log(f"[{name}] AVISO: resíduo/curvatura > {RESID_POLY_CELLS} célula: faltaria a correção polinomial por lado")
	fig_frame(img, C, info, os.path.join(OUT, f"ocupacao_{name}_moldura.jpg"))

	half = cv2.resize(full, None, fx=CLS_SCALE, fy=CLS_SCALE, interpolation=cv2.INTER_AREA)
	C_half = C / sc * CLS_SCALE
	r40 = cv2.warpPerspective(half, homography(C_half, CAN_W, CAN_H), (int(round(NCOL * CAN_W)), int(round(NROW * CAN_H))),
		flags=cv2.INTER_AREA)
	refine, dec = grid_refine(r40, CAN_W, CAN_H)
	for k, v in refine.items():
		log(f"[{name}] grelha {k}: {{{', '.join(f'{a}: {b}' for a, b in v.items() if a not in ('desvios_px', 'coef'))}}}")
	log(f"[{name}] refinamento: {dec}")
	xb40, yb40 = boundaries(CAN_W, CAN_H, refine, dec)
	fig_rect(r40, xb40, yb40, os.path.join(OUT, f"ocupacao_{name}_retificada.jpg"))

	rect, valid, Hc = rectify_cls(half, C_half)
	lin = srgb_to_lin(rect)
	xb_u, yb_u = boundaries(CLS_W, CLS_H)
	box_u = cell_boxes(xb_u, yb_u)
	norm1, ref1, f1 = felt_model(lin, valid, deg=POLY_DEG)
	med1, sL1, _, _ = cell_features(norm1, ref1, box_u)
	ex, nseed = seed_mask(rect.shape[:2], box_u, med1, sL1)
	norm, ref, f2 = felt_model(lin, valid, ex, deg=FELT_DEG2)
	# resíduo de L* do feltro nas células-semente: 1.ª passagem (grau 2, só orla) vs 2.ª passagem
	seed = (np.hypot(med1[..., 1], med1[..., 2]) < SEED_CHROMA) & (sL1 < SEED_SL) & (np.abs(med1[..., 0]) < SEED_DL)
	xb, yb = boundaries(CLS_W, CLS_H, refine, dec)
	boxes = cell_boxes(xb, yb)
	med, sL, ff, ft = cell_features(norm, ref, boxes)
	med_u2, _, _, _ = cell_features(norm, ref, box_u)
	felt_res = dict(n_sementes=nseed,
		passagem1_dL_p5_p50_p95=[round(float(x), 1) for x in np.percentile(med1[..., 0][seed], [5, 50, 95])],
		passagem2_dL_p5_p50_p95=[round(float(x), 1) for x in np.percentile(med_u2[..., 0][seed], [5, 50, 95])])
	log(f"[{name}] feltro: 1.ª {f1}; 2.ª {f2}; {felt_res}")
	dEf = np.sqrt((med ** 2).sum(-1))
	dEs = np.sqrt(np.minimum(med[..., 0], 0) ** 2 + med[..., 1] ** 2 + med[..., 2] ** 2)
	lab = med + ref
	Bm = border_mask()
	off = np.median((lab - art)[Bm], 0)
	dEa = np.sqrt(((lab - off - art) ** 2).sum(-1))
	occ, conf, occA, d = decide(dEs, ft, dEf, dEa)
	cmB, cmA = confusion(occ, gt), confusion(occA, gt)
	gtc = dict(gt); gtc.update(GT_VISUAL)
	cmBc, cmAc = confusion(occ, gtc), confusion(occA, gtc)
	log(f"[{name}] regra B, GT corrigida pela inspeção visual {GT_VISUAL}: {cmBc}")
	log(f"[{name}] regra A, GT corrigida: exatidão {cmAc['exatidao']}")
	log(f"[{name}] desvio fotométrico (foto normalizada - arte, 218 de borda): {np.round(off, 1).tolist()}")
	log(f"[{name}] regra B (usada): {cmB}")
	log(f"[{name}] regra A (ΔE_feltro - ΔE_arte, MARGEM {MARGEM}): {cmA}")
	tex = dict(sL_vazias_GT=[round(float(x), 1) for x in np.percentile([sL[l - 1, c - 1] for (l, c), g in gt.items() if g == 0], [50, 95])],
		sL_cheias_GT=[round(float(x), 1) for x in np.percentile([sL[l - 1, c - 1] for (l, c), g in gt.items() if g == 1], [5, 50])])

	# figuras
	Hinv = np.linalg.inv(homography(C_half, CLS_W, CLS_H))
	so = FRAME_W / half.shape[1]
	polys = cell_polys(Hinv, xb, yb, so)
	fig_overlay(img, polys, occ, os.path.join(OUT, f"ocupacao_{name}_overlay.jpg"), gtc)
	sym = {1: "cheia", 0: "vazia", -1: "incerta"}
	show = [(1, 29), (1, 32), (1, 54), (1, 55), (2, 61), (5, 60), (42, 58), (42, 59), (41, 3), (43, 6), (44, 7), (24, 58)]
	show += [(int(l) + 1, int(c) + 1) for l, c in np.argwhere(occ == -1) if 6 <= l <= 44][:12]
	fig_cells(rect, boxes, show, [(f"{sym[int(occ[l - 1, c - 1])]} GT {gt.get((l, c), '-')}",
		f"dEs {dEs[l - 1, c - 1]:.1f} ft {ft[l - 1, c - 1]:.2f} dEa {dEa[l - 1, c - 1]:.0f}") for l, c in show],
		os.path.join(OUT, f"ocupacao_{name}_celulas.jpg"))
	H_full = homography(C / sc, CAN_W, CAN_H)
	dt = time.time() - t0
	log(f"[{name}] tempo {dt:.1f} s")
	out = {"grelha": [NCOL, NROW], "convencao": "celulas[l-1][c-1], l = fila 1..47 de cima, c = coluna 1..64 da esquerda; 1 cheia, 0 vazia, -1 incerta",
		"celulas": occ.tolist(), "confianca": conf.tolist(),
		"homografia": {"de": "foto original (px)", "para": f"canónica {CAN_W:g} x {CAN_H:.2f} px por célula", "H": np.round(H_full, 9).tolist()},
		"cantos_px": np.round(C / sc, 1).tolist(),
		"residual_px": {s: {"rms_inliers_px_foto": round(sr[s]["rms_inliers_px"] / sc, 2), "rms_inliers_celulas": sr[s]["rms_inliers_celulas"],
			"curvatura_celulas": sr[s]["curvatura_celulas"]} for s in SIDES},
		"dE_feltro_escurecimento": np.round(dEs, 1).tolist(), "fracao_feltro": np.round(ft, 3).tolist(),
		"dE_arte": np.round(dEa, 1).tolist()}
	with open(os.path.join(OUT, f"ocupacao_{name}.json"), "w", encoding="utf-8") as fh:
		json.dump(out, fh, ensure_ascii=False)
	return dict(occ=occ, occA=occA, dEf=dEf, dEa=dEa, ff=ff, sL=sL, img=img, polys=polys,
		summary=dict(cantos_px=np.round(C / sc, 1).tolist(), celula_px_foto=round(cell_px / sc, 1), lados=sr,
			grelha={k: {a: b for a, b in v.items() if a != "coef"} for k, v in refine.items()}, refinamento=dec,
			feltro=dict(passagem1=f1, passagem2=f2, **felt_res), desvio_fotometrico_lab=np.round(off, 2).tolist(),
			textura=tex, regraB=cmB, regraA=cmA, regraB_GT_corrigida=cmBc, regraA_GT_corrigida=cmAc, tempo_s=round(dt, 1)))


def counts(occ):
	full = (occ == 1)
	return dict(n_cheias=int(full.sum()), n_vazias=int((occ == 0).sum()), n_incertas=int((occ == -1).sum()),
		cheias_por_fila=full.sum(1).astype(int).tolist(), cheias_por_coluna=full.sum(0).astype(int).tolist())


def main(names):
	os.makedirs(OUT, exist_ok=True)
	gt = gt_cells()
	art = art_cells()
	R = {n: run(n, art, gt) for n in names}
	for n in names:
		if "error" in R[n]:
			log(f"[{n}] ERRO: {R[n]['error']}")
			return
	res = {"metodo": "tools/diagnostico/ocupacao/ocupacao.py", "fotos": {n: R[n]["summary"] for n in names},
		"contagens": {n: counts(R[n]["occ"]) for n in names}}
	for n in names:
		c = res["contagens"][n]
		log(f"[{n}] cheias {c['n_cheias']}, vazias {c['n_vazias']}, incertas {c['n_incertas']}")
		log(f"[{n}]   filas 1-6: {c['cheias_por_fila'][:6]}; filas 41-47: {c['cheias_por_fila'][40:]}")
		log(f"[{n}]   colunas 1-3: {c['cheias_por_coluna'][:3]}; colunas 62-64: {c['cheias_por_coluna'][61:]}")
	if len(names) == 2:
		a, b = R["a"]["occ"], R["b"]["occ"]
		dis = np.argwhere(a != b)
		agree = dict(n_discordantes=int(len(dis)), discordantes_lc_a_b=[[int(l) + 1, int(c) + 1, int(a[l, c]), int(b[l, c])] for l, c in dis],
			n_discordantes_ignorando_incertas=int(((a != b) & (a != -1) & (b != -1)).sum()))
		log(f"concordância a/b: {agree}")
		fused = np.where((a == 1) & (b == 1), 1, np.where((a == 0) & (b == 0), 0, -1))
		cf = counts(fused)
		fus = {"grelha": [NCOL, NROW], "fontes": ["mapa_2026-10-31_a.jpg", "mapa_2026-10-31_b.jpg"],
			"regra": "1 se ambas cheia, 0 se ambas vazia, -1 se discordam ou alguma incerta",
			"convencao": "celulas[l-1][c-1], l = fila 1..47 de cima, c = coluna 1..64 da esquerda",
			"celulas": fused.tolist(), **cf}
		with open(os.path.join(OUT, "ocupacao_2026-10-31.json"), "w", encoding="utf-8") as fh:
			json.dump(fus, fh, ensure_ascii=False)
		res["concordancia_ab"] = agree
		gtc = dict(gt); gtc.update(GT_VISUAL)
		res["fusao"] = dict(confusao_GT=confusion(fused, gt), confusao_GT_corrigida=confusion(fused, gtc), **cf)
		log(f"fusão: {res['fusao']['confusao_GT']}; GT corrigida: {res['fusao']['confusao_GT_corrigida']}; cheias {cf['n_cheias']}, incertas {cf['n_incertas']}")
		log(f"fusão filas 41-47: {cf['cheias_por_fila'][40:]}; filas 1-6: {cf['cheias_por_fila'][:6]}")
		fig_overlay(R["a"]["img"], R["a"]["polys"], fused, os.path.join(OUT, "ocupacao_2026-10-31_fusao_overlay.jpg"), gt)
	# results.json: reler imediatamente antes de escrever, mudar só a chave "ocupacao"
	with open(RESULTS, encoding="utf-8") as fh:
		allres = json.load(fh)
	allres["ocupacao"] = res
	with open(RESULTS, "w", encoding="utf-8") as fh:
		json.dump(allres, fh, ensure_ascii=False, indent=1)
	with open(os.path.join(OUT, "ocupacao_log.txt"), "w", encoding="utf-8") as fh:
		fh.write("\n".join(LOG) + "\n")


if __name__ == "__main__":
	main([a for a in sys.argv[1:] if a in ("a", "b")] or ["a", "b"])
