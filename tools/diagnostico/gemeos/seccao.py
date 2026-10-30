"""Secção montada (canto, céu + nuvem): linhas de corte, localização na arte e fotometria.

Diagnóstico (não é código de produção). Correr a partir da raiz do repositório:

	PowerShell:  $env:PPF_SCRATCH = "C:\\caminho\\scratchpad"
	bash:        export PPF_SCRATCH=/caminho/scratchpad
	python tools/diagnostico/gemeos/seccao.py

Entrada: images/pieces/{frente,traseira}_{300,600}dpi.jpg (secção montada, frente e verso;
a traseira está espelhada), images/puzzles/1186441_1.jpg (arte limpa), images/puzzles/
PuzzleOriginal.jpeg (foto da caixa; bbox da arte por matching/common.detect_artwork),
images/pieces/digitalização_fundo_verde.jpg, coluna5-24_300dpi_folhaA.jpg (A1),
coluna5-24_folhaB_300dpi_rot180.jpg (B2) e $PPF_SCRATCH/seg/scan_verde.npz (61 peças de julho).

Saída: docs/diagnostico/gemeos/seccao_*.png, seccao_results.json, seccao_celulas.json. Só cv2/numpy/PIL.

Partes:
  A. linhas de corte por black-hat e por Hessiana em L*, células = componentes do complemento;
     frente vs traseira (registo pela silhueta, ICP) -> RMS de forma entre células homólogas.
  B. localização da secção num dos 4 cantos da arte (Lab/NCC com jitter), SIFT como controlo,
     (l, c) de cada célula.
  C. Lab mediano do céu (scan / arte / caixa), do fundo verde e das peças de julho vs hoje.
"""
import os
import sys
import json
import time

import numpy as np
import cv2

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools", "diagnostico", "forma"))
sys.path.insert(0, os.path.join(REPO, "tools", "diagnostico", "matching"))
sys.path.insert(0, os.path.join(REPO, "tools", "diagnostico"))

from src.segmentation import _weighted_distance, _otsu_plateau_threshold, _border_background  # noqa: E402
from shapelib import analyse_v2, shape_dist  # noqa: E402
from gemeos_quick import desc as free_desc, dist as free_dist  # noqa: E402

S = os.environ.get("PPF_SCRATCH", "scratch")
WORK = os.path.join(S, "seccao")
OUT = os.path.join(REPO, "docs", "diagnostico", "gemeos")
PIECES = os.path.join(REPO, "images", "pieces")
CLEAN = os.path.join(REPO, "images", "puzzles", "1186441_1.jpg")
ORIG = os.path.join(REPO, "images", "puzzles", "PuzzleOriginal.jpeg")
os.makedirs(WORK, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

SCANS = ["frente_300", "traseira_300", "frente_600", "traseira_600"]
METHODS = ["blackhat", "hessiana"]
MODES = ["otsu", "histerese", "watershed"]
CELL_MM = (18.5, 17.9)          # nominal (horizontal, vertical do puzzle)
CELL_AREA_MM2 = CELL_MM[0] * CELL_MM[1]
GRID = (64, 47)                 # colunas, linhas
EXPECTED_BY_EYE = 44            # contado a olho na traseira e na frente (ver SECCAO.md)
RNG = np.random.default_rng(0)
LOG = []


def log(*a):
	s = " ".join(str(x) for x in a)
	LOG.append(s)
	print(s, flush=True)


def ell(d):
	d = max(1, int(d))
	return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (d, d))


def odd(x):
	return int(2 * round((x - 1) / 2.0) + 1)


def lab_f(rgb_u8):
	"""Lab em vírgula flutuante (L* 0..100, a*, b* reais) a partir de RGB uint8."""
	return cv2.cvtColor(rgb_u8.astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB)


def read_rgb(path):
	# IGNORE_ORIENTATION: PuzzleOriginal.jpeg tem EXIF orientation=3, mas os píxeis já estão direitos
	# (o PIL, usado pelo motor e por matching/common, também ignora o EXIF); os scans não têm a etiqueta.
	im = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
	return cv2.cvtColor(im, cv2.COLOR_BGR2RGB)


# ----------------------------------------------------------------------------- máscaras
def fg_mask(rgb, open_px=5, de_min=20.0):
	"""Máscara de primeiro plano: distância Lab (L* com peso 0,25) à cor do papel (mediana da moldura, como em
	segmentation._border_background) acima de max(de_min, 0,5·Otsu). O Otsu de patamar sozinho
	(segment_pieces) cortava a peça creme da nuvem, mais próxima do verde do que o céu."""
	lab = lab_f(rgb)
	bg = _border_background(lab, 0.03)
	# L* com peso 0,25: a sombra da aresta do cartão (L* mais baixo, mesma cor) não entra
	dd = lab - bg.reshape(1, 1, 3)
	D = np.sqrt(0.25 * dd[:, :, 0] ** 2 + dd[:, :, 1] ** 2 + dd[:, :, 2] ** 2)
	D8 = np.clip(D * 2, 0, 255).astype(np.uint8)
	t = _otsu_plateau_threshold(D8) / 2.0
	m = (D > min(max(de_min, 0.5 * t), t)).astype(np.uint8)
	m = cv2.morphologyEx(m, cv2.MORPH_OPEN, ell(open_px))
	return m


def fill_largest(m):
	n, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
	i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
	cs, _ = cv2.findContours((lab == i).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
	c = max(cs, key=cv2.contourArea)
	out = np.zeros_like(m)
	cv2.drawContours(out, [c], -1, 1, -1)
	return out.astype(bool), c.reshape(-1, 2)


# ----------------------------------------------------------------------------- lados retos
def edge_line(mask, side, max_deg=4.0):
	"""Linha de suporte de um lado do bloco. Perfil extremo (min x por linha para 'left', etc.),
	procura do ângulo cuja reta de suporte toca o maior número de pontos (|resíduo| < 3 px).
	Devolve dict(ang=declive, d0, frac=fração de pontos na reta, t0, t1)."""
	ys, xs = np.nonzero(mask)
	if side in ("left", "right"):
		t = np.arange(mask.shape[0]); has = mask.any(1)
		if side == "left":
			d = np.where(has, mask.argmax(1), 0).astype(float)
		else:
			d = -np.where(has, mask.shape[1] - 1 - mask[:, ::-1].argmax(1), 0).astype(float)
	else:
		t = np.arange(mask.shape[1]); has = mask.any(0)
		if side == "top":
			d = np.where(has, mask.argmax(0), 0).astype(float)
		else:
			d = -np.where(has, mask.shape[0] - 1 - mask[::-1, :].argmax(0), 0).astype(float)
	t = t[has].astype(float); d = d[has]
	best = None
	for a in np.radians(np.arange(-max_deg, max_deg + 1e-9, 0.05)):
		s = np.tan(a)
		r = d - s * t
		r0 = r.min()
		inl = r < r0 + 3.0
		if best is None or inl.sum() > best[0]:
			best = (int(inl.sum()), s, r0, inl)
	n, s, r0, inl = best
	# refina com mínimos quadrados nos inliers
	A = np.c_[t[inl], np.ones(inl.sum())]
	s2, r02 = np.linalg.lstsq(A, d[inl], rcond=None)[0]
	return dict(side=side, slope=float(s2), d0=float(r02), frac=float(n / len(t)),
		t0=float(t[inl].min()), t1=float(t[inl].max()), n=int(n), ntot=int(len(t)))


def corner_frame(mask):
	"""Deteta os 2 lados retos; exige que sejam 'left' e 'bottom' (imagem canónica).
	Devolve canto (x,y), ângulo phi (rad) e info dos 4 lados."""
	info = {s: edge_line(mask, s) for s in ("left", "right", "top", "bottom")}
	order = sorted(info, key=lambda s: -info[s]["frac"])
	straight = sorted(order[:2])
	L, B = info["left"], info["bottom"]
	# left: x = sL*y + x0 ; bottom: -y = sB*x + d0  ->  y = -sB*x - d0
	sL, x0 = L["slope"], L["d0"]
	sB, d0 = B["slope"], B["d0"]
	# intersecção
	y = (-sB * x0 - d0) / (1 + sB * sL)
	x = sL * y + x0
	phi_b = np.arctan(-sB)       # direção do lado de baixo (1, -sB)
	phi_l = -np.arctan(sL)       # lado esquerdo (sL, 1) -> rotação phi tem dx/dy = -tan(phi)
	return dict(corner=(float(x), float(y)), phi=float(0.5 * (phi_b + phi_l)),
		phi_b_deg=float(np.degrees(phi_b)), phi_l_deg=float(np.degrees(phi_l)),
		straight=straight, fracs={s: round(info[s]["frac"], 3) for s in info},
		straight_len_px={s: info[s]["t1"] - info[s]["t0"] for s in info})


def to_uw(pts, fr, px_mm):
	"""Coordenadas do scan (px) -> (u, w) em mm: u ao longo do lado de baixo (direita),
	w perpendicular para baixo (w < 0 dentro do bloco). Rotação própria (sem reflexão)."""
	c, s = np.cos(fr["phi"]), np.sin(fr["phi"])
	p = np.asarray(pts, float) - np.array(fr["corner"])
	u = p[:, 0] * c + p[:, 1] * s
	w = -p[:, 0] * s + p[:, 1] * c
	return np.c_[u, w] * px_mm


# ----------------------------------------------------------------------------- linhas de corte
def thin(m):
	"""Afinamento Zhang-Suen vetorizado (bool -> bool)."""
	img = m.astype(np.uint8).copy()
	while True:
		changed = 0
		for step in (0, 1):
			P = np.pad(img, 1)
			p2 = P[:-2, 1:-1]; p3 = P[:-2, 2:]; p4 = P[1:-1, 2:]; p5 = P[2:, 2:]
			p6 = P[2:, 1:-1]; p7 = P[2:, :-2]; p8 = P[1:-1, :-2]; p9 = P[:-2, :-2]
			Bn = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9
			seq = [p2, p3, p4, p5, p6, p7, p8, p9, p2]
			A = np.zeros_like(img)
			for i in range(8):
				A += ((seq[i] == 0) & (seq[i + 1] == 1)).astype(np.uint8)
			if step == 0:
				c1 = (p2 * p4 * p6) == 0; c2 = (p4 * p6 * p8) == 0
			else:
				c1 = (p2 * p4 * p8) == 0; c2 = (p2 * p6 * p8) == 0
			rm = (img == 1) & (Bn >= 2) & (Bn <= 6) & (A == 1) & c1 & c2
			k = int(rm.sum())
			if k:
				img[rm] = 0
				changed += k
		if not changed:
			break
	return img.astype(bool)


def valley_response(L, dpi, method):
	px_mm = 25.4 / dpi
	if method == "blackhat":
		k = 7 if dpi == 300 else 14
		return cv2.morphologyEx(L, cv2.MORPH_BLACKHAT, ell(k))
	s = 0.25 / px_mm
	G = cv2.GaussianBlur(L, (0, 0), s)
	dxx = cv2.Sobel(G, cv2.CV_32F, 2, 0, ksize=3)
	dyy = cv2.Sobel(G, cv2.CV_32F, 0, 2, ksize=3)
	dxy = cv2.Sobel(G, cv2.CV_32F, 1, 1, ksize=3)
	lam = 0.5 * (dxx + dyy) + np.sqrt(0.25 * (dxx - dyy) ** 2 + dxy ** 2)
	# vale escuro -> maior valor próprio positivo (= menor valor próprio da Hessiana de -L)
	return np.maximum(lam, 0) * s * s


def response_u8(L, inner, dpi, method):
	R = valley_response(L, dpi, method)
	hi = float(np.percentile(R[inner], 99.5)) + 1e-9
	return np.clip(R / hi * 255.0, 0, 255).astype(np.uint8)


def hysteresis(R8, inner, t, low_frac=0.5):
	core = (R8 > t) & inner
	cand = ((R8 > low_frac * t) & inner).astype(np.uint8)
	n, lab = cv2.connectedComponents(cand, connectivity=8)
	keep = np.unique(lab[core]); keep = keep[keep > 0]
	return np.isin(lab, keep)


def extract_cells(R8, inner, dpi, mode, seeds=None):
	"""mode 'otsu' (pedido): Otsu + fecho 0,3 mm. 'histerese': núcleo > Otsu, candidatos > 0,5·Otsu
	ligados ao núcleo, fecho 0,3 mm (sem prior). 'watershed': inundação da resposta a partir de
	sementes nos centros da grelha (prior: canto + passo); linhas = fronteiras da inundação."""
	px_mm = 25.4 / dpi
	t = _otsu_plateau_threshold(R8[inner])
	kc = odd(0.3 / px_mm)
	raw = (R8 > t) & inner
	if mode == "otsu":
		lines = cv2.morphologyEx(raw.astype(np.uint8), cv2.MORPH_CLOSE, ell(kc)).astype(bool) & inner
	elif mode == "histerese":
		h = hysteresis(R8, inner, t)
		# o fecho inclui o exterior do bloco, para ligar as pontas das linhas à silhueta erodida
		lines = cv2.morphologyEx((h | ~inner).astype(np.uint8), cv2.MORPH_CLOSE, ell(kc)).astype(bool) & inner
	else:
		mk = np.zeros(R8.shape, np.int32)
		mk[~cv2.dilate(inner.astype(np.uint8), ell(3)).astype(bool)] = 1
		for j, (x, y, r) in enumerate(seeds):
			cv2.circle(mk, (int(round(x)), int(round(y))), int(r), 2 + j, -1)
		mk[~inner & (mk > 1)] = 0
		relief = cv2.GaussianBlur(R8, (0, 0), 0.1 / px_mm)
		ws = cv2.watershed(cv2.cvtColor(relief, cv2.COLOR_GRAY2BGR), mk)
		lines = (ws == -1) & inner
		lines = cv2.dilate(lines.astype(np.uint8), np.ones((2, 2), np.uint8)).astype(bool) & inner
		# a fronteira da inundação fica num dos flancos do vale: o próprio vale (histerese) também é linha,
		# senão uma das células anexa uma tira de 1-3 px ao longo da linha do vizinho
		lines |= hysteresis(R8, inner, t)
	comp = (inner & ~lines).astype(np.uint8)
	if mode != "otsu":
		# variantes: abertura de 0,4 mm remove tiras/pontes de 1-3 px entre células
		comp = cv2.morphologyEx(comp, cv2.MORPH_OPEN, ell(odd(0.4 / px_mm)))
	n, lab, st, cen = cv2.connectedComponentsWithStats(comp, connectivity=4)
	out = dict(R8=R8, otsu=float(t), raw=raw, lines=lines, lab=lab, stats=st, cen=cen, n=n, close_px=kc)
	if mode == "watershed":
		# suporte: fração da fronteira (longe da silhueta) a ≤ 0,25 mm de um píxel de linha (histerese)
		h = hysteresis(R8, inner, t)
		near = cv2.dilate(h.astype(np.uint8), ell(odd(2 * 0.25 / px_mm))).astype(bool)
		deep = cv2.erode(inner.astype(np.uint8), ell(odd(2 * 0.5 / px_mm))).astype(bool)
		b = lines & deep
		out["support"] = float((b & near).sum() / max(1, b.sum()))
	return out


def pitch_autocorr(R8, inner, fr, px_mm):
	"""Passo (mm) ao longo de u e w: autocorrelação das projeções da resposta no referencial do bloco."""
	H, W = R8.shape
	cx, cy = fr["corner"]
	M = cv2.getRotationMatrix2D((cx, cy), np.degrees(fr["phi"]), 1.0)
	Rr = cv2.warpAffine((R8 * inner).astype(np.float32), M, (W, H))
	Ir = cv2.warpAffine(inner.astype(np.float32), M, (W, H))
	out = []
	for axis in (0, 1):     # 0: perfil ao longo de x (u), 1: ao longo de y (w)
		prof = Rr.sum(axis) / np.maximum(Ir.sum(axis), 1)
		ok = Ir.sum(axis) > 0.3 * Ir.sum(axis).max()
		p = np.where(ok, prof - prof[ok].mean(), 0)
		ac = np.correlate(p, p, "full")[len(p) - 1:]
		lo, hi = int(15 / px_mm), int(22 / px_mm)
		k = lo + int(np.argmax(ac[lo:hi]))
		# refinamento parabólico
		if 0 < k < len(ac) - 1:
			a, b, c = ac[k - 1], ac[k], ac[k + 1]
			k = k + 0.5 * (a - c) / (a - 2 * b + c + 1e-9)
		out.append(float(k * px_mm))
	return out


def classify_area(r):
	if r < 0.1:
		return "speck"
	if r < 0.6:
		return "frag"
	if r <= 1.4:
		return "valid"
	if r <= 2.6:
		return "double"
	return "multi"


# ----------------------------------------------------------------------------- grelha local
def fit_pitch(vals, lo, hi):
	"""Passo p tal que vals ≈ (k + 0.5)·p (centróides de células a partir do lado reto)."""
	best = None
	for p in np.arange(lo, hi, 0.02):
		x = vals / p - 0.5
		r = x - np.round(x)
		c = float(np.sum(r ** 2))
		if best is None or c < best[0]:
			best = (c, p)
	return float(best[1])


def occupancy(inner_full, fr, px_mm, pu, pw, nmax=10):
	"""Casas (iu, iw) ocupadas pelo bloco: ≥ 50 % do quadrado central (50 %) coberto pela máscara."""
	H, W = inner_full.shape
	occ = []
	c, s = np.cos(fr["phi"]), np.sin(fr["phi"])
	for iu in range(nmax):
		for iw in range(nmax):
			uu = np.linspace((iu + 0.25) * pu, (iu + 0.75) * pu, 9)
			ww = -np.linspace((iw + 0.25) * pw, (iw + 0.75) * pw, 9)
			U, Wm = np.meshgrid(uu, ww)
			u = U.ravel() / px_mm; w = Wm.ravel() / px_mm
			x = fr["corner"][0] + u * c - w * s
			y = fr["corner"][1] + u * s + w * c
			xi = np.round(x).astype(int); yi = np.round(y).astype(int)
			ok = (xi >= 0) & (xi < W) & (yi >= 0) & (yi < H)
			if ok.mean() < 1:
				continue
			if inner_full[yi, xi].mean() >= 0.5:
				occ.append((iu, iw))
	return occ


# ----------------------------------------------------------------------------- Parte A
def load_scan(name):
	side, dpi = name.split("_")
	dpi = int(dpi)
	rgb = read_rgb(os.path.join(PIECES, f"{side}_{dpi}dpi.jpg"))
	if side == "traseira":
		rgb = np.ascontiguousarray(rgb[:, ::-1])   # imagem canónica: traseira espelhada
	return rgb, dpi


def part_A():
	res = {}
	cache = {}
	for name in SCANS:
		t0 = time.time()
		rgb, dpi = load_scan(name)
		px_mm = 25.4 / dpi
		H0, W0 = rgb.shape[:2]
		m = fg_mask(rgb, open_px=odd(0.4 / px_mm))
		block, outer = fill_largest(m)
		fr = corner_frame(block)
		ys, xs = np.nonzero(block)
		pad = int(2 / px_mm)
		y0, y1 = max(0, ys.min() - pad), min(H0, ys.max() + pad)
		x0, x1 = max(0, xs.min() - pad), min(W0, xs.max() + pad)
		crop = rgb[y0:y1, x0:x1]
		blk = block[y0:y1, x0:x1]
		er = odd(2 * 1.0 / px_mm)       # erosão de 1 mm (raio)
		inner = cv2.erode(blk.astype(np.uint8), ell(er)).astype(bool)
		L = lab_f(crop)[:, :, 0]
		log(f"[A] {name}: {W0}x{H0}, bloco {blk.sum() * px_mm ** 2:.0f} mm2, lados retos {fr['straight']} "
			f"frac {fr['fracs']}, phi {np.degrees(fr['phi']):.2f} deg (baixo {fr['phi_b_deg']:.2f}, esq {fr['phi_l_deg']:.2f})")
		fr_c = dict(fr); fr_c["corner"] = (fr["corner"][0] - x0, fr["corner"][1] - y0)
		R8s = {meth: response_u8(L, inner, dpi, meth) for meth in METHODS}
		pa = pitch_autocorr(R8s["hessiana"], inner, fr_c, px_mm)
		log(f"    passo por autocorrelação (hessiana): u {pa[0]:.2f} mm, w {pa[1]:.2f} mm ({time.time() - t0:.1f} s)")
		cache[name] = dict(rgb=crop, block=blk, inner=inner, fr=fr_c, fr_full=fr, off=(x0, y0), dpi=dpi,
			px_mm=px_mm, R8s=R8s, per={}, outer=outer - np.array([x0, y0]), shape0=(H0, W0),
			nom=CELL_AREA_MM2 / px_mm ** 2, pitch_ac=pa)
	# só as frentes (linhas mais completas); com a máscara antiga, a traseira dava w ≈ 17,8 mm (período errado)
	pu = float(np.median([d["pitch_ac"][0] for n, d in cache.items() if n.startswith("frente")]))
	pw = float(np.median([d["pitch_ac"][1] for n, d in cache.items() if n.startswith("frente")]))
	log(f"[A] passo (mediana das frentes, autocorrelação): u {pu:.2f} mm, w {pw:.2f} mm")
	for name, d in cache.items():
		t0 = time.time()
		px_mm = d["px_mm"]; dpi = d["dpi"]; nom = d["nom"]
		occ = occupancy(d["block"], d["fr"], px_mm, pu, pw)
		d["occ"] = occ
		c_, s_ = np.cos(d["fr"]["phi"]), np.sin(d["fr"]["phi"])
		seeds = []
		for iu, iw in occ:
			u = (iu + 0.5) * pu / px_mm; w = -(iw + 0.5) * pw / px_mm
			seeds.append((d["fr"]["corner"][0] + u * c_ - w * s_, d["fr"]["corner"][1] + u * s_ + w * c_, 0.15 * pu / px_mm))
		block_area = float(d["inner"].sum())
		res[name] = dict(dpi=dpi, straight=d["fr"]["straight"], fracs=d["fr"]["fracs"], pitch_autocorr_mm=d["pitch_ac"],
			phi_deg=float(np.degrees(d["fr"]["phi"])), n_occupied=len(occ), methods={})
		for meth in METHODS:
			for mode in MODES:
				key = f"{meth}/{mode}"
				ex = extract_cells(d["R8s"][meth], d["inner"], dpi, mode, seeds)
				st = ex["stats"]; cen = ex["cen"]
				cells = []
				for i in range(1, ex["n"]):
					a = int(st[i, cv2.CC_STAT_AREA])
					r = a / nom
					k = classify_area(r)
					if k == "speck":
						continue
					cells.append(dict(i=i, area_px=a, ratio=r, kind=k, cen=(float(cen[i, 0]), float(cen[i, 1]))))
				lf = float(ex["lines"].sum() / block_area)
				line_mm = float(thin(ex["lines"]).sum() * px_mm) if lf < 0.15 else None
				P = dict(ex=ex, cells=cells, line_mm=line_mm)
				d["per"][key] = P
				hits = {}
				for c in cells:
					uw = to_uw([c["cen"]], d["fr"], px_mm)[0]
					iu, iw = int(np.floor(uw[0] / pu)), int(np.floor(-uw[1] / pw))
					c["iu"], c["iw"] = iu, iw
					if c["kind"] == "valid":
						hits.setdefault((iu, iw), []).append(c)
				rec = sum(1 for o in occ if len(hits.get(o, [])) == 1)
				kinds = [c["kind"] for c in cells]
				valid_area = sum(c["area_px"] for c in cells if c["kind"] == "valid")
				nv = kinds.count("valid")
				res[name]["methods"][key] = dict(
					n_cells=len(kinds), n_valid=nv, n_double=kinds.count("double"), n_multi=kinds.count("multi"),
					n_frag=kinds.count("frag"), recovered=rec, expected=len(occ),
					pct_area_valid=100.0 * valid_area / block_area, otsu=ex["otsu"], line_mm=line_mm,
					line_mm_per_expected_cell=(line_mm / max(1, len(occ))) if line_mm else None,
					line_frac_block=lf, support=ex.get("support"))
				log(f"[A] {name} {key}: válidas {nv}, recuperadas {rec}/{len(occ)}, 2x {kinds.count('double')}, "
					f"multi {kinds.count('multi')}, frag {kinds.count('frag')}, área válida {100.0 * valid_area / block_area:.1f}%, "
					f"linhas {lf * 100:.1f}% do bloco" + (f", suporte {ex['support'] * 100:.0f}%" if 'support' in ex else ""))
		log(f"    {name}: {time.time() - t0:.1f} s")
	# verificação do passo pelos centróides das células válidas sem prior (frentes, hessiana/histerese)
	U, Wv = [], []
	for n, d in cache.items():
		if not n.startswith("frente"):
			continue
		for c in d["per"]["hessiana/histerese"]["cells"]:
			if c["kind"] == "valid":
				uw = to_uw([c["cen"]], d["fr"], d["px_mm"])[0]
				U.append(uw[0]); Wv.append(-uw[1])
	pc = (fit_pitch(np.array(U), 15.0, 22.0), fit_pitch(np.array(Wv), 15.0, 22.0)) if U else (None, None)
	log(f"[A] passo pelos centróides (frentes, hessiana/histerese, sem prior, n={len(U)}): u {pc[0]}, w {pc[1]}")
	res["_pitch_centroids_mm"] = pc
	return res, cache, (pu, pw)


def cell_contour(d, meth, c, mm_units=False):
	lab = d["per"][meth]["ex"]["lab"]
	m = (lab == c["i"]).astype(np.uint8)
	cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
	cc = max(cs, key=cv2.contourArea).reshape(-1, 2).astype(float)
	return cc


def keys_all(prior=True):
	return [f"{m}/{o}" for m in METHODS for o in MODES if prior or o != "watershed"]


def best_method(res, name, prior=False):
	"""Melhor combinação resposta/modo por casas recuperadas; prior=False exclui o watershed com sementes."""
	m = res[name]["methods"]
	return max(keys_all(prior), key=lambda k: (m[k]["recovered"], m[k]["pct_area_valid"]))


def uw_to_px(uw, fr, px_mm):
	c, s = np.cos(fr["phi"]), np.sin(fr["phi"])
	u = uw[:, 0] / px_mm; w = uw[:, 1] / px_mm
	return np.c_[fr["corner"][0] + u * c - w * s, fr["corner"][1] + u * s + w * c]


def line_noise(da, db, M):
	"""Distância (mm) dos píxeis de esqueleto das linhas detetadas em b (hessiana/histerese, sem fecho)
	às linhas detetadas em a, após o registo pela silhueta. Não depende de as células fecharem."""
	sk = {}
	for key, d in (("a", da), ("b", db)):
		R8 = d["R8s"]["hessiana"]; t = _otsu_plateau_threshold(R8[d["inner"]])
		deep = cv2.erode(d["inner"].astype(np.uint8), ell(odd(2 * 1.0 / d["px_mm"]))).astype(bool)
		sk[key] = thin(hysteresis(R8, d["inner"], t)) & deep
	ys, xs = np.nonzero(sk["b"])
	uw = to_uw(np.c_[xs, ys], db["fr"], db["px_mm"]) @ M[:, :2].T + M[:, 2]
	pa = uw_to_px(uw, da["fr"], da["px_mm"])
	dt = cv2.distanceTransform((~sk["a"]).astype(np.uint8), cv2.DIST_L2, 5)
	xi = np.clip(np.round(pa[:, 0]).astype(int), 0, dt.shape[1] - 1); yi = np.clip(np.round(pa[:, 1]).astype(int), 0, dt.shape[0] - 1)
	dmm = dt[yi, xi] * da["px_mm"]
	near = dmm[dmm <= 1.0]
	# cobertura: fração do esqueleto de a com um píxel de b a ≤ 0,5 mm
	mb = np.zeros(dt.shape, np.uint8); mb[yi, xi] = 1
	dtb = cv2.distanceTransform(1 - mb, cv2.DIST_L2, 5) * da["px_mm"]
	cov = float((dtb[sk["a"]] <= 0.5).mean())
	return dict(n_b=int(len(dmm)), median_mm=float(np.median(near)) if len(near) else None,
		p90_mm=float(np.percentile(near, 90)) if len(near) else None, frac_within_0p5mm=float((dmm <= 0.5).mean()),
		frac_within_1mm=float((dmm <= 1.0).mean()), coverage_a_by_b=cov,
		skel_mm_a=float(sk["a"].sum() * da["px_mm"]), skel_mm_b=float(sk["b"].sum() * db["px_mm"]))


def icp(src, dst, iters=40):
	"""ICP ponto-a-ponto com estimateAffinePartial2D (semelhança). src, dst em mm."""
	M = np.eye(2, 3)
	cur = src.copy()
	for _ in range(iters):
		d2 = ((cur[:, None, :] - dst[None, :, :]) ** 2).sum(-1)
		j = d2.argmin(1); dd = np.sqrt(d2[np.arange(len(cur)), j])
		keep = dd < max(3 * np.median(dd), 0.2)
		A, _ = cv2.estimateAffinePartial2D(src[keep].astype(np.float32), dst[j[keep]].astype(np.float32),
			method=cv2.LMEDS)
		if A is None:
			break
		M = A
		cur = src @ M[:, :2].T + M[:, 2]
	d2 = ((cur[:, None, :] - dst[None, :, :]) ** 2).sum(-1)
	dd = np.sqrt(d2.min(1))
	return M, dd


def resample_pts(c, n):
	p = np.vstack([c, c[:1]])
	seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
	s = np.concatenate([[0], np.cumsum(seg)])
	t = np.linspace(0, s[-1], n, endpoint=False)
	return np.c_[np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])]


def shape_of(cc_mm):
	"""Contorno em mm -> dict analisado por analyse_v2 (em unidades de px a 300 dpi)."""
	p = dict(contour=cc_mm / (25.4 / 300.0))
	try:
		analyse_v2(p)
	except Exception as e:      # noqa: BLE001
		p["ok"] = False; p["err"] = str(e)
	return p


def compare_pair(cache, res, na, nb, ma=None, mb=None):
	"""Regista nb -> na pela silhueta (ICP) e compara células homólogas."""
	da, db = cache[na], cache[nb]
	ma = ma or best_method(res, na); mb = mb or best_method(res, nb)
	oa = to_uw(resample_pts(da["outer"].astype(float), 1500), da["fr"], da["px_mm"])
	ob = to_uw(resample_pts(db["outer"].astype(float), 1500), db["fr"], db["px_mm"])
	init = np.sqrt(((ob[:, None] - oa[None]) ** 2).sum(-1).min(1))
	M, dd = icp(ob, oa)
	sc = float(np.hypot(M[0, 0], M[1, 0])); ang = float(np.degrees(np.arctan2(M[1, 0], M[0, 0])))
	ln = line_noise(da, db, M)
	log(f"[A] {na} vs {nb}: linhas detetadas (hessiana/histerese, esqueleto) de {nb} -> {na}: "
		f"mediana {ln['median_mm']:.3f} mm, p90 {ln['p90_mm']:.3f} (px a ≤ 1 mm), {ln['frac_within_0p5mm'] * 100:.0f}% a ≤ 0,5 mm; "
		f"cobertura de {na} por {nb} {ln['coverage_a_by_b'] * 100:.0f}%")
	ca = [c for c in da["per"][ma]["cells"] if c["kind"] == "valid"]
	cb = [c for c in db["per"][mb]["cells"] if c["kind"] == "valid"]
	if not ca or not cb:
		log(f"[A] {na} vs {nb} ({ma}/{mb}): sem células válidas")
		return dict(a=na, b=nb, method_a=ma, method_b=mb, n_pairs=0, line_noise=ln), []
	cen_a = to_uw([c["cen"] for c in ca], da["fr"], da["px_mm"])
	cen_b = to_uw([c["cen"] for c in cb], db["fr"], db["px_mm"]) @ M[:, :2].T + M[:, 2]
	pairs = []
	for i, c in enumerate(ca):
		dist = np.linalg.norm(cen_b - cen_a[i], axis=1)
		j = int(dist.argmin())
		if dist[j] > 6.0:
			continue
		A = to_uw(cell_contour(da, ma, c), da["fr"], da["px_mm"])
		B = to_uw(cell_contour(db, mb, cb[j]), db["fr"], db["px_mm"]) @ M[:, :2].T + M[:, 2]
		# RMS "free" (sem cantos) e RMS de cantos (analyse_v2 + shape_dist)
		za = free_desc((A / (25.4 / 300.0)).reshape(-1, 1, 2)); zb = free_desc((B / (25.4 / 300.0)).reshape(-1, 1, 2))
		rf = free_dist(za, zb)
		# desvio direto (sem re-alinhar): média das distâncias ponto-a-contorno, após o registo global
		Ar = resample_pts(A, 400); Br = resample_pts(B, 400)
		dab = np.sqrt(((Ar[:, None] - Br[None]) ** 2).sum(-1).min(1))
		sa = shape_of(A); sb = shape_of(B)
		rc = None; tt = None
		if sa.get("ok") and sb.get("ok"):
			rc = float(shape_dist(sa, sb)[0])
			tt = sa["cls"] == sb["cls"]
		pairs.append(dict(a=c["i"], b=cb[j]["i"], iu=c["iu"], iw=c["iw"], cen_dist_mm=float(dist[j]),
			rms_free=rf, rms_corner=rc, direct_mean_mm=float(dab.mean()), direct_p95_mm=float(np.percentile(dab, 95)),
			ok_a=bool(sa.get("ok")), ok_b=bool(sb.get("ok")), cls_a=sa.get("cls"), cls_b=sb.get("cls"),
			same_cls=tt, A=A, B=B))
	rf = np.array([p["rms_free"] for p in pairs]); rc = np.array([p["rms_corner"] for p in pairs if p["rms_corner"] is not None])
	dm = np.array([p["direct_mean_mm"] for p in pairs])
	out = dict(a=na, b=nb, method_a=ma, method_b=mb, n_valid_a=len(ca), n_valid_b=len(cb), n_pairs=len(pairs), line_noise=ln,
		icp_scale=sc, icp_rot_deg=ang, icp_tx_mm=float(M[0, 2]), icp_ty_mm=float(M[1, 2]),
		silhouette_resid_init_median_mm=float(np.median(init)), silhouette_resid_median_mm=float(np.median(dd)),
		silhouette_resid_p95_mm=float(np.percentile(dd, 95)),
		rms_free_median=float(np.median(rf)) if len(rf) else None, rms_free_p90=float(np.percentile(rf, 90)) if len(rf) else None,
		rms_free_max=float(rf.max()) if len(rf) else None,
		n_corner=int(len(rc)), rms_corner_median=float(np.median(rc)) if len(rc) else None,
		rms_corner_p90=float(np.percentile(rc, 90)) if len(rc) else None, rms_corner_max=float(rc.max()) if len(rc) else None,
		direct_mean_median=float(np.median(dm)) if len(dm) else None,
		same_cls=int(sum(1 for p in pairs if p["same_cls"])), both_ok=int(sum(1 for p in pairs if p["ok_a"] and p["ok_b"])))
	log(f"[A] {na} vs {nb} ({ma}/{mb}): ICP escala {sc:.4f} rot {ang:.2f} deg; silhueta mediana {out['silhouette_resid_median_mm']:.3f} mm "
		f"(antes {out['silhouette_resid_init_median_mm']:.3f}); pares {len(pairs)}; RMS free mediana {out['rms_free_median']:.3f} "
		f"p90 {out['rms_free_p90']:.3f} máx {out['rms_free_max']:.3f}; corner n={len(rc)} mediana {out['rms_corner_median']}; "
		f"mesma classe {out['same_cls']}/{out['both_ok']}")
	return out, pairs


def topology(cache, res, name, meth):
	"""Cantos/lados por analyse_v2 em cada célula válida; complementaridade T<->B entre vizinhos."""
	d = cache[name]
	cells = [c for c in d["per"][meth]["cells"] if c["kind"] == "valid"]
	info = {}
	for c in cells:
		A = to_uw(cell_contour(d, meth, c), d["fr"], d["px_mm"])
		s = shape_of(A)
		if not s.get("ok"):
			info[(c["iu"], c["iw"])] = dict(ok=False)
			continue
		ctr = s["c"].mean(0)
		dirs = []
		for side in s["sides"]:
			mid = 0.5 * (side[0] + side[-1]) - ctr
			dirs.append(mid / (np.linalg.norm(mid) + 1e-9))
		info[(c["iu"], c["iw"])] = dict(ok=True, types=s["types"], cls=s["cls"], dirs=dirs, lens=s["lens"])
	n_ok = sum(1 for v in info.values() if v["ok"])
	nF = sum(t == "F" for v in info.values() if v["ok"] for t in v["types"])
	# vizinhos: (iu+1, iw) está em +u (direita), (iu, iw+1) em -w (para cima, coordenadas em px y-down)
	good = bad = 0; bad_list = []
	for (iu, iw), v in info.items():
		for (du, dw, vec) in ((1, 0, np.array([1.0, 0.0])), (0, 1, np.array([0.0, -1.0]))):
			q = info.get((iu + du, iw + dw))
			if not (v["ok"] and q and q["ok"]):
				continue
			ta = v["types"][int(np.argmax([dd @ vec for dd in v["dirs"]]))]
			tb = q["types"][int(np.argmax([dd @ -vec for dd in q["dirs"]]))]
			if {ta, tb} == {"T", "B"}:
				good += 1
			else:
				bad += 1; bad_list.append(((iu, iw), (iu + du, iw + dw), ta, tb))
	# lados retos esperados: células com iu == 0 (lado esquerdo) e iw == 0 (lado de baixo)
	f_ok = f_tot = 0
	for (iu, iw), v in info.items():
		if not v["ok"]:
			continue
		for (cond, vec) in ((iu == 0, np.array([-1.0, 0.0])), (iw == 0, np.array([0.0, 1.0]))):
			if cond:
				f_tot += 1
				t = v["types"][int(np.argmax([dd @ vec for dd in v["dirs"]]))]
				f_ok += t == "F"
	out = dict(method=meth, n_valid=len(cells), n_4corners=n_ok, n_F_sides=int(nF), neigh_TB_ok=good, neigh_bad=bad,
		neigh_bad_list=[[list(a), list(b), x, y] for a, b, x, y in bad_list], straight_F_ok=f_ok, straight_F_tot=f_tot,
		classes={f"{k[0]},{k[1]}": v.get("cls") for k, v in info.items()})
	log(f"[A] topologia {name} ({meth}): 4 cantos {n_ok}/{len(cells)}, vizinhos T/B coerentes {good}/{good + bad}, "
		f"lados retos classificados F {f_ok}/{f_tot}")
	return out


# ----------------------------------------------------------------------------- figuras A
def colour_cells(d, meth):
	P = d["per"][meth]; lab = P["ex"]["lab"]
	g = cv2.cvtColor(cv2.cvtColor(d["rgb"], cv2.COLOR_RGB2GRAY), cv2.COLOR_GRAY2RGB).astype(np.float32)
	col = np.zeros((lab.max() + 1, 3), np.float32)
	for c in P["cells"]:
		if c["kind"] == "valid":
			col[c["i"]] = RNG.integers(60, 255, 3)
		elif c["kind"] == "double":
			col[c["i"]] = (255, 0, 0)
		elif c["kind"] == "multi":
			col[c["i"]] = (255, 0, 255)
		else:
			col[c["i"]] = (255, 255, 0)
	cm = col[lab]
	has = cm.sum(-1) > 0
	out = g.copy()
	out[has] = 0.45 * g[has] + 0.55 * cm[has]
	out[P["ex"]["lines"]] = (0, 0, 0)
	return out.clip(0, 255).astype(np.uint8)


def put(img, txt, y=40, scale=1.2, col=(255, 255, 0)):
	cv2.putText(img, txt, (10, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 5, cv2.LINE_AA)
	cv2.putText(img, txt, (10, y), cv2.FONT_HERSHEY_SIMPLEX, scale, col, 2, cv2.LINE_AA)


def fig_lines(cache, res, name):
	d = cache[name]
	rows = []
	H = 340
	for meth in keys_all():
		P = d["per"][meth]; r = res[name]["methods"][meth]
		a = cv2.cvtColor(255 - P["ex"]["R8"], cv2.COLOR_GRAY2RGB)
		b = np.full(d["rgb"].shape, 255, np.uint8); b[~d["inner"]] = (200, 230, 200); b[P["ex"]["lines"]] = (0, 0, 0)
		c = colour_cells(d, meth)
		panels = []
		for im, t in ((a, f"{meth}: resposta"), (b, f"limiar Otsu {P['ex']['otsu']:.0f} + fecho {P['ex']['close_px']} px"),
				(c, f"validas {r['n_valid']}, recup. {r['recovered']}/{r['expected']}, 2x {r['n_double']}")):
			f = H / im.shape[0]
			im2 = cv2.resize(im, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
			put(im2, t, 24, 0.5)
			panels.append(im2)
		rows.append(np.hstack(panels))
	fig = np.vstack(rows)
	side, dpi = name.split("_")
	cv2.imwrite(os.path.join(OUT, f"seccao_linhas_{side}_{dpi}.png"), cv2.cvtColor(fig, cv2.COLOR_RGB2BGR))


def fig_fvt(cache, res, cmp_pairs, path):
	"""Contornos de células: frente (verde) e traseira registada (magenta), em mm -> px 300 dpi."""
	na = "frente_300"; d = cache[na]
	pairs = cmp_pairs[("frente_300", "traseira_300", "watershed")]
	sc = 4.0
	allp = np.vstack([np.vstack([p["A"], p["B"]]) for p in pairs])
	mn = allp.min(0) - 3; mx = allp.max(0) + 3
	Wd, Hd = int((mx[0] - mn[0]) * sc * 2), int((mx[1] - mn[1]) * sc * 2)
	img = np.full((Hd, Wd, 3), 255, np.uint8)
	for p in pairs:
		for C, col in ((p["A"], (0, 150, 0)), (p["B"], (220, 0, 220))):
			q = np.round((C - mn) * sc * 2).astype(np.int32)
			cv2.polylines(img, [q.reshape(-1, 1, 2)], True, col, 2, cv2.LINE_AA)
		ctr = np.round((p["A"].mean(0) - mn) * sc * 2).astype(int)
		txt = f"{p['rms_free']:.2f}"
		cv2.putText(img, txt, (ctr[0] - 40, ctr[1] + 8), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2, cv2.LINE_AA)
	put(img, "frente 300 (verde) vs traseira 300 espelhada, registada por ICP (magenta); hessiana/watershed; RMS free (mm)", 40, 1.0, (0, 0, 0))
	# zoom de 4 células (melhor, mediana, 2 piores)
	srt = sorted(pairs, key=lambda p: p["rms_free"])
	pick = [srt[0], srt[len(srt) // 2], srt[-2], srt[-1]]
	zs = []
	for p in pick:
		C = np.vstack([p["A"], p["B"]]); m0 = C.min(0) - 1; m1 = C.max(0) + 1
		z = 20.0
		zi = np.full((int((m1[1] - m0[1]) * z), int((m1[0] - m0[0]) * z), 3), 255, np.uint8)
		for CC, col in ((p["A"], (0, 150, 0)), (p["B"], (220, 0, 220))):
			q = np.round((CC - m0) * z).astype(np.int32)
			cv2.polylines(zi, [q.reshape(-1, 1, 2)], True, col, 2, cv2.LINE_AA)
		put(zi, f"casa ({p['iu']},{p['iw']}) free {p['rms_free']:.2f} mm", 30, 0.7, (0, 0, 0))
		zi = cv2.resize(zi, (500, int(500 * zi.shape[0] / zi.shape[1])))
		zs.append(zi)
	hz = max(z.shape[0] for z in zs)
	zs = [np.vstack([z, np.full((hz - z.shape[0], z.shape[1], 3), 255, np.uint8)]) for z in zs]
	strip = np.hstack(zs)
	f = img.shape[1] / strip.shape[1]
	strip = cv2.resize(strip, None, fx=f, fy=f)
	fig = np.vstack([img, strip])
	f = 1800 / fig.shape[1]
	fig = cv2.resize(fig, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
	cv2.imwrite(path, cv2.cvtColor(fig, cv2.COLOR_RGB2BGR))


# ----------------------------------------------------------------------------- Parte B
def art_refs():
	from common import detect_artwork
	clean = read_rgb(CLEAN)
	g = clean.min(2)
	rows = np.where((g < 235).mean(1) > 0.5)[0]; cols = np.where((g < 235).mean(0) > 0.5)[0]
	cb = (int(cols[0]), int(rows[0]), int(cols[-1]), int(rows[-1]))
	art_c = clean[cb[1]:cb[3] + 1, cb[0]:cb[2] + 1]
	orig = read_rgb(ORIG)
	ob = detect_artwork(orig)
	art_o = orig[ob[1]:ob[3] + 1, ob[0]:ob[2] + 1]
	art_o = cv2.resize(art_o, (art_c.shape[1], art_c.shape[0]), interpolation=cv2.INTER_AREA)
	log(f"[B] arte limpa bbox {cb} -> {art_c.shape[1]}x{art_c.shape[0]}; caixa bbox {ob} "
		f"({ob[2] - ob[0] + 1}x{ob[3] - ob[1] + 1}) -> reamostrada para o mesmo tamanho")
	return dict(clean=art_c, box=art_o, clean_bbox=cb, box_bbox=ob, orig_shape=orig.shape[:2])


HYPS = {0: "BL (inferior esquerdo)", 1: "TL (superior esquerdo)", 2: "TR (superior direito)", 3: "BR (inferior direito)"}


def uw_to_art(u, v, k, mirror, sx_u, sx_v, sy_u, sy_v, Wa, Ha):
	"""(u, v) em px do scan (v = -w, para cima a partir do lado de baixo) -> (X, Y) na arte.
	k = rotações de 90 graus no sentido horário aplicadas ao scan; o canto dos lados retos vai
	para BL/TL/TR/BR. mirror: reflexão horizontal adicional (controlo)."""
	if k == 0:
		X, Y = u * sx_u, Ha - v * sy_v
	elif k == 1:
		X, Y = v * sx_v, u * sy_u
	elif k == 2:
		X, Y = Wa - u * sx_u, v * sy_v
	else:
		X, Y = Wa - v * sx_v, Ha - u * sy_u
	if mirror:
		X = Wa - X
	return X, Y


def affine_for(fr, px_mm, k, mirror, pu_mm, pw_mm, Wa, Ha, s=1.0, dx=0.0, dy=0.0):
	"""Matriz 2x3: px do scan (recorte) -> px da arte."""
	cw, sw = np.cos(fr["phi"]), np.sin(fr["phi"])
	ax_x = Wa / GRID[0]; ax_y = Ha / GRID[1]          # px de arte por célula
	# escala px_scan -> px_arte por eixo do scan (u, v), conforme o eixo do puzzle para onde vai
	pu_px = pu_mm / px_mm; pv_px = pw_mm / px_mm
	if k % 2 == 0:
		sx_u, sy_v = ax_x / pu_px * s, ax_y / pv_px * s; sx_v = sy_u = 0
	else:
		sx_v, sy_u = ax_x / pv_px * s, ax_y / pu_px * s; sx_u = sy_v = 0
	cx, cy = fr["corner"]
	pts = np.float32([[cx, cy], [cx + 100 * cw, cy + 100 * sw], [cx + 100 * sw, cy - 100 * cw]])
	dst = []
	for (x, y) in pts:
		p = np.array([x - cx, y - cy])
		u = p[0] * cw + p[1] * sw
		v = -(-p[0] * sw + p[1] * cw)
		X, Y = uw_to_art(u, v, k, mirror, sx_u, sx_v, sy_u, sy_v, Wa, Ha)
		dst.append([X + dx, Y + dy])
	return cv2.getAffineTransform(pts, np.float32(dst))


def ncc(a, b):
	a = a - a.mean(); b = b - b.mean()
	return float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-9))


def part_B(cache, pitch):
	pu, pw = pitch
	d = cache["frente_300"]
	refs = art_refs()
	Ha, Wa = refs["clean"].shape[:2]
	labs = {k: lab_f(refs[k]) for k in ("clean", "box")}
	# pré-redução do scan (anti-alias, INTER_AREA) para a escala final
	s0 = (Wa / GRID[0]) / (pu / d["px_mm"])
	sm = cv2.resize(d["rgb"], None, fx=s0, fy=s0, interpolation=cv2.INTER_AREA)
	smask = cv2.resize(d["inner"].astype(np.float32), None, fx=s0, fy=s0, interpolation=cv2.INTER_AREA)
	slab = lab_f(sm)
	fr_s = dict(d["fr"]); fr_s["corner"] = (d["fr"]["corner"][0] * s0, d["fr"]["corner"][1] * s0)
	pxs = d["px_mm"] / s0
	results = {}
	best_by_ref = {}
	for ref in ("clean", "box"):
		A = labs[ref]
		rows = []
		for mirror in (False, True):
			for k in range(4):
				best = None
				for s in (0.97, 1.0, 1.03):
					M0 = affine_for(fr_s, pxs, k, mirror, pu, pw, Wa, Ha, s)
					wl = cv2.warpAffine(slab, M0, (Wa, Ha), flags=cv2.INTER_LINEAR, borderValue=0)
					wm = cv2.warpAffine(smask, M0, (Wa, Ha), flags=cv2.INTER_LINEAR, borderValue=0)
					ys, xs = np.nonzero(wm > 0.99)
					for dy in range(-4, 5):
						for dx in range(-4, 5):
							yy = ys + dy; xx = xs + dx
							ok = (yy >= 0) & (yy < Ha) & (xx >= 0) & (xx < Wa)
							if ok.mean() < 0.9:
								continue
							a = wl[ys[ok], xs[ok]]; b = A[yy[ok], xx[ok]]
							de = float(np.sqrt(((a - b) ** 2).sum(-1)).mean())
							nc = ncc(a[:, 0], b[:, 0])
							if best is None or nc > best["ncc"]:
								best = dict(k=k, mirror=mirror, s=s, dx=dx, dy=dy, ncc=nc, dE=de, n=int(ok.sum()))
				# melhor dE por hipótese (independente do NCC): recalcula no ponto ótimo do NCC
				rows.append(best)
		for r in rows:
			r["name"] = ("espelho " if r["mirror"] else "") + HYPS[r["k"]]
		main = [r for r in rows if not r["mirror"]]
		srt = sorted(main, key=lambda r: -r["ncc"])
		srt_de = sorted(main, key=lambda r: r["dE"])
		results[ref] = dict(hyps=rows, best=srt[0]["name"], ncc_gap=srt[0]["ncc"] - srt[1]["ncc"],
			best_dE=srt_de[0]["name"], dE_gap=srt_de[1]["dE"] - srt_de[0]["dE"])
		best_by_ref[ref] = srt[0]
		for r in rows:
			log(f"[B] {ref}: {r['name']:32s} NCC(L*) {r['ncc']:+.3f}  dE {r['dE']:.1f}  s {r['s']} d=({r['dx']},{r['dy']}) n={r['n']}")
		log(f"[B] {ref}: melhor por NCC {results[ref]['best']} (gap {results[ref]['ncc_gap']:.3f}); "
			f"melhor por dE {results[ref]['best_dE']} (gap {results[ref]['dE_gap']:.1f})")
	# SIFT de controlo
	results["sift"] = sift_try(d, refs, pu)
	# figura de localização
	fig_loc(d, refs, labs, fr_s, pxs, s0, sm, smask, best_by_ref, pu, pw, results)
	return results, refs, best_by_ref, (fr_s, pxs, s0, sm, smask)


def sift_try(d, refs, pu):
	out = {}
	sift = cv2.SIFT_create(nfeatures=8000)
	art = cv2.cvtColor(refs["clean"], cv2.COLOR_RGB2GRAY)
	ka, da = sift.detectAndCompute(art, None)
	for f_mult in (1.0, 2.0, 4.0):
		f = f_mult * (refs["clean"].shape[1] / GRID[0]) / (pu / d["px_mm"])
		g = cv2.cvtColor(cv2.resize(d["rgb"], None, fx=f, fy=f, interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY)
		mk = cv2.resize(d["inner"].astype(np.uint8), (g.shape[1], g.shape[0]), interpolation=cv2.INTER_NEAREST)
		ks, ds = sift.detectAndCompute(g, mk)
		r = dict(scale=f, n_kp_scan=len(ks), n_kp_art=len(ka))
		if ds is None or len(ks) < 2:
			r.update(n_good=0, n_inliers=0)
			out[f"x{f_mult:g}"] = r
			continue
		m = cv2.BFMatcher().knnMatch(ds, da, k=2)
		good = [a for a, b in (mm for mm in m if len(mm) == 2) if a.distance < 0.75 * b.distance]
		r["n_good"] = len(good)
		if len(good) >= 4:
			src = np.float32([ks[x.queryIdx].pt for x in good]).reshape(-1, 1, 2)
			dst = np.float32([ka[x.trainIdx].pt for x in good]).reshape(-1, 1, 2)
			Hm, inl = cv2.findHomography(src, dst, cv2.RANSAC, 3.0)
			r["n_inliers"] = int(inl.sum()) if inl is not None else 0
			if Hm is not None:
				c = cv2.perspectiveTransform(np.float32([[[g.shape[1] / 2, g.shape[0] / 2]]]), Hm).ravel()
				r["centre_in_art"] = [float(c[0]), float(c[1])]
		else:
			r["n_inliers"] = 0
		out[f"x{f_mult:g}"] = r
		log(f"[B] SIFT escala x{f_mult:g}: kp scan {len(ks)}, bons {r['n_good']}, inliers {r['n_inliers']}, centro {r.get('centre_in_art')}")
	# também a função original de expB (foto -> arte), aplicada ao scan como 'orig'
	try:
		from expB import homography
		_, info = homography(d["rgb"], refs["clean"])
		out["expB_homography"] = {k: v for k, v in info.items() if k != "H"}
		log(f"[B] expB.homography(scan, arte): {out['expB_homography']}")
	except Exception as e:     # noqa: BLE001
		out["expB_homography"] = dict(error=f"{type(e).__name__}: {e}")
		log(f"[B] expB.homography falhou: {type(e).__name__}: {e}")
	return out


def fig_loc(d, refs, labs, fr_s, pxs, s0, sm, smask, best_by_ref, pu, pw, results):
	Ha, Wa = refs["clean"].shape[:2]
	panels = []
	for ref in ("clean", "box"):
		b = best_by_ref[ref]
		M = affine_for(fr_s, pxs, b["k"], b["mirror"], pu, pw, Wa, Ha, b["s"], b["dx"], b["dy"])
		w = cv2.warpAffine(sm, M, (Wa, Ha), flags=cv2.INTER_LINEAR)
		wm = cv2.warpAffine(smask, M, (Wa, Ha)) > 0.5
		ys, xs = np.nonzero(wm)
		x0, x1 = max(0, xs.min() - 60), min(Wa, xs.max() + 60); y0, y1 = max(0, ys.min() - 60), min(Ha, ys.max() + 60)
		art = refs[ref][y0:y1, x0:x1].copy()
		ov = art.copy(); sub = w[y0:y1, x0:x1]; mm = wm[y0:y1, x0:x1]
		ov[mm] = sub[mm]
		edge = cv2.morphologyEx(mm.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
		ov2 = art.copy(); ov2[edge] = (255, 0, 0)
		f = 4
		row = [cv2.resize(x, None, fx=f, fy=f, interpolation=cv2.INTER_NEAREST) for x in (ov2, ov)]
		put(row[0], f"{'arte limpa' if ref == 'clean' else 'caixa'}: {b['name']} (contorno do bloco)", 30, 0.8)
		put(row[1], f"scan colado; NCC {b['ncc']:.2f} gap {results[ref]['ncc_gap']:.2f}", 30, 0.8)
		panels.append(np.hstack(row))
	# miniaturas das 4 hipóteses na arte limpa
	thumbs = []
	for k in range(4):
		M = affine_for(fr_s, pxs, k, False, pu, pw, Wa, Ha)
		w = cv2.warpAffine(sm, M, (Wa, Ha), flags=cv2.INTER_LINEAR)
		wm = cv2.warpAffine(smask, M, (Wa, Ha)) > 0.5
		t = refs["clean"].copy(); t[wm] = w[wm]
		t = cv2.resize(t, None, fx=0.45, fy=0.45, interpolation=cv2.INTER_AREA)
		r = [x for x in results["clean"]["hyps"] if x["k"] == k and not x["mirror"]][0]
		put(t, f"{HYPS[k][:2]} NCC {r['ncc']:+.2f} dE {r['dE']:.0f}", 30, 0.8)
		thumbs.append(t)
	trow = np.hstack(thumbs)
	Wmax = max(p.shape[1] for p in panels + [trow])
	def padw(x):
		return np.hstack([x, np.zeros((x.shape[0], Wmax - x.shape[1], 3), np.uint8)]) if x.shape[1] < Wmax else x
	fig = np.vstack([padw(p) for p in panels] + [padw(trow)])
	f = min(1.0, 2000 / fig.shape[1])
	fig = cv2.resize(fig, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
	cv2.imwrite(os.path.join(OUT, "seccao_localizacao.png"), cv2.cvtColor(fig, cv2.COLOR_RGB2BGR))


def lc_of(iu, iw, k, mirror):
	"""Casa local (iu ao longo do lado de baixo, iw para cima) -> (linha, coluna) 1-based."""
	if k == 0:
		c, l = iu + 1, GRID[1] - iw
	elif k == 1:
		l, c = iu + 1, iw + 1
	elif k == 2:
		c, l = GRID[0] - iu, iw + 1
	else:
		l, c = GRID[1] - iu, GRID[0] - iw
	if mirror:
		c = GRID[0] + 1 - c
	return int(l), int(c)


def save_cells_json(cache, res, best, pitch, cmp_pairs):
	k, mirror = best["k"], best["mirror"]
	out = dict(descricao="Células extraídas das linhas de corte na secção montada (canto). Contornos em px "
		"do ficheiro original indicado (a traseira está nas coordenadas do ficheiro original, não espelhada). "
		"(l, c) 1-based na grelha 64 colunas x 47 linhas, contados a partir do canto identificado em B.",
		canto=HYPS[k], espelho=mirror, passo_mm=dict(u=pitch[0], w=pitch[1]), scans={})
	for name, d in cache.items():
		meth = best_method(res, name, prior=True)
		x0, y0 = d["off"]; W0 = d["shape0"][1]
		cells = []
		for c in d["per"][meth]["cells"]:
			if c["kind"] != "valid":
				continue
			cc = cell_contour(d, meth, c) + np.array([x0, y0])
			if name.startswith("traseira"):
				cc[:, 0] = W0 - 1 - cc[:, 0]
			step = max(1, len(cc) // 600)
			l, cl = lc_of(c["iu"], c["iw"], k, mirror)
			cells.append(dict(l=l, c=cl, casa_local=[c["iu"], c["iw"]], area_mm2=round(c["area_px"] * d["px_mm"] ** 2, 1),
				contorno_px=cc[::step].round().astype(int).tolist()))
		out["scans"][name] = dict(ficheiro=f"images/pieces/{name.split('_')[0]}_{name.split('_')[1]}dpi.jpg",
			dpi=d["dpi"], metodo=meth, n=len(cells), celulas=cells)
	with open(os.path.join(OUT, "seccao_celulas.json"), "w", encoding="utf-8") as f:
		json.dump(out, f, ensure_ascii=False)
	occ = cache["frente_300"]["occ"]
	return sorted(lc_of(iu, iw, k, mirror) for iu, iw in occ)


# ----------------------------------------------------------------------------- Parte C
def med(lab_px):
	return [round(float(x), 1) for x in np.median(lab_px.reshape(-1, 3), axis=0)]


def bg_lab(path, flip=False):
	rgb = read_rgb(path)
	m = fg_mask(rgb)
	m = cv2.dilate(m, ell(odd(6 / (25.4 / 300))))
	bgm = m == 0
	bgm[:60] = bgm[-60:] = False; bgm[:, :60] = bgm[:, -60:] = False
	lab = lab_f(rgb)
	return med(lab[bgm]), float(bgm.mean())


def pieces_simple(path, rows=4, cols=5):
	"""Peças por distância Lab ao fundo, ordenadas por filas (como gemeos_quick); máscara erodida 0,5 mm."""
	rgb = read_rgb(path)
	m = fg_mask(rgb)
	m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, ell(9))
	n, lab, st, cen = cv2.connectedComponentsWithStats(m, connectivity=8)
	idx = [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] > 20000]
	idx = sorted(idx, key=lambda i: cen[i, 1])
	groups = [idx[r * cols:(r + 1) * cols] for r in range(rows)]
	L = lab_f(rgb)
	out = []
	for r, g in enumerate(groups):
		for k, i in enumerate(sorted(g, key=lambda i: cen[i, 0])):
			mk = cv2.erode((lab == i).astype(np.uint8), ell(odd(1.0 / (25.4 / 300)))) > 0
			out.append(dict(fila=r + 1, k=k, area=int(st[i, cv2.CC_STAT_AREA]), lab=med(L[mk])))
	return out, len(idx)


def pieces_npz(key, rows=4, cols=5):
	"""Peças de $PPF_SCRATCH/seg/gemeos_{A1,B2}.npz (segment_pieces, gerado pelo esym.py), ordenadas por filas."""
	p = os.path.join(S, "seg", f"gemeos_{key}.npz")
	if not os.path.exists(p):
		return None, 0
	z = np.load(p, allow_pickle=True)
	bb = np.array([np.asarray(b, float) for b in z["bboxes"]])
	cx = bb[:, 0] + bb[:, 2] / 2; cy = bb[:, 1] + bb[:, 3] / 2
	idx = [i for i in np.argsort(cy) if not bool(z["is_cluster"][i])]
	if len(idx) != rows * cols:
		log(f"[C] {p}: {len(idx)} peças (esperadas {rows * cols}); uso a segmentação simples")
		return None, 0
	out = []
	for r in range(rows):
		g = sorted(idx[r * cols:(r + 1) * cols], key=lambda i: cx[i])
		for k, i in enumerate(g):
			L = lab_f(np.asarray(z["images"][i], np.uint8))
			mk = cv2.erode((np.asarray(z["masks"][i]) > 0).astype(np.uint8), ell(odd(1.0 / (25.4 / 300)))) > 0
			out.append(dict(fila=r + 1, k=k, area=int(mk.sum()), lab=med(L[mk])))
	return out, len(idx)


def art_cell_lab(art_lab, l, c, inset=0.2):
	Ha, Wa = art_lab.shape[:2]
	cw, ch = Wa / GRID[0], Ha / GRID[1]
	x0, x1 = int(round((c - 1 + inset) * cw)), int(round((c - inset) * cw))
	y0, y1 = int(round((l - 1 + inset) * ch)), int(round((l - inset) * ch))
	return med(art_lab[y0:y1, x0:x1])


def part_C(cache, res, refs, best_by_ref, bctx, pitch):
	pu, pw = pitch
	d = cache["frente_300"]
	meth = best_method(res, "frente_300", prior=True)
	lab = lab_f(d["rgb"])
	lines = cv2.dilate(d["per"][meth]["ex"]["lines"].astype(np.uint8), ell(odd(0.6 / d["px_mm"]))) > 0
	base = d["inner"] & ~lines
	bvals = lab[base]
	log(f"[C] b* no bloco: p5 {np.percentile(bvals[:, 2], 5):.1f} p25 {np.percentile(bvals[:, 2], 25):.1f} "
		f"p50 {np.percentile(bvals[:, 2], 50):.1f} p75 {np.percentile(bvals[:, 2], 75):.1f} p95 {np.percentile(bvals[:, 2], 95):.1f}")
	sky = base & (lab[:, :, 2] < -20) & (lab[:, :, 1] < 5)
	sky = cv2.erode(sky.astype(np.uint8), ell(odd(1.0 / d["px_mm"]))) > 0
	out = dict(sky_scan=med(lab[sky]), sky_frac_block=float(sky.sum() / d["inner"].sum()))
	# mesma zona na arte limpa e na caixa
	fr_s, pxs, s0, sm, smask = bctx
	Ha, Wa = refs["clean"].shape[:2]
	sky_s = cv2.resize(sky.astype(np.float32), (sm.shape[1], sm.shape[0]), interpolation=cv2.INTER_AREA)
	for ref in ("clean", "box"):
		b = best_by_ref["clean"]       # mesma colocação (a da arte limpa) para as duas referências
		M = affine_for(fr_s, pxs, b["k"], b["mirror"], pu, pw, Wa, Ha, b["s"], b["dx"], b["dy"])
		wsky = cv2.warpAffine(sky_s, M, (Wa, Ha)) > 0.95
		alab = lab_f(refs[ref])
		out[f"sky_{ref}"] = med(alab[wsky])
		out[f"sky_{ref}_npx"] = int(wsky.sum())
		out[f"whole_{ref}"] = med(alab)
		# curva píxel a píxel no bloco registado (inclui nuvem creme e cinzenta): L* do scan por classe de L* da arte
		wl = cv2.warpAffine(lab_f(sm), M, (Wa, Ha), flags=cv2.INTER_LINEAR)
		wm = cv2.warpAffine(smask, M, (Wa, Ha)) > 0.99
		a_ = alab[wm]; s_ = wl[wm]
		curve = []
		for lo in range(0, 100, 5):
			sel = (a_[:, 0] >= lo) & (a_[:, 0] < lo + 5)
			if sel.sum() >= 30:
				curve.append(dict(art_L=[lo, lo + 5], n=int(sel.sum()), scan=med(s_[sel]), art=med(a_[sel])))
		out[f"curve_{ref}"] = curve
		log(f"[C] curva {ref}: " + "; ".join(f"arte {c['art'][0]:.0f} -> scan {c['scan'][0]:.0f} (n={c['n']})" for c in curve))
		# por célula da secção: scan vs arte
	# células: mediana Lab no scan (sem linhas) vs célula (l, c) da arte
	k, mirror = best_by_ref["clean"]["k"], best_by_ref["clean"]["mirror"]
	pairs = []
	alab_c = lab_f(refs["clean"]); alab_b = lab_f(refs["box"])
	for c in d["per"][meth]["cells"]:
		if c["kind"] != "valid":
			continue
		mk = (d["per"][meth]["ex"]["lab"] == c["i"]) & ~lines
		mk = cv2.erode(mk.astype(np.uint8), ell(odd(1.5 / d["px_mm"]))) > 0
		l, cl = lc_of(c["iu"], c["iw"], k, mirror)
		pairs.append(dict(l=l, c=cl, scan=med(lab[mk]), art=art_cell_lab(alab_c, l, cl), box=art_cell_lab(alab_b, l, cl)))
	out["section_cells"] = pairs
	# fundo verde
	greens = {}
	for key, fn in (("julho_digitalizacao_fundo_verde", "digitalização_fundo_verde.jpg"),
			("hoje_A1_coluna5-24_300dpi_folhaA", "coluna5-24_300dpi_folhaA.jpg"),
			("hoje_B2_coluna5-24_folhaB_300dpi_rot180", "coluna5-24_folhaB_300dpi_rot180.jpg"),
			("hoje_frente_300dpi", "frente_300dpi.jpg"), ("hoje_traseira_300dpi", "traseira_300dpi.jpg")):
		v, fr_ = bg_lab(os.path.join(PIECES, fn))
		greens[key] = dict(lab=v, frac_px=round(fr_, 3))
		log(f"[C] fundo verde {key}: Lab {v} (fração de px usada {fr_:.2f})")
	out["green"] = greens
	# peças de julho
	z = np.load(os.path.join(S, "seg", "scan_verde.npz"), allow_pickle=True)
	jl = []; pool = []
	for im, mk, cl_ in zip(z["images"], z["masks"], z["is_cluster"]):
		if bool(cl_):
			continue
		L = lab_f(np.asarray(im, np.uint8))
		m = cv2.erode((np.asarray(mk) > 0).astype(np.uint8), ell(odd(1.0 / (25.4 / 300)))) > 0
		jl.append(med(L[m])); pool.append(L[m][::7])
	jl = np.array(jl); pool = np.vstack(pool)
	out["julho"] = dict(n=len(jl), median_of_piece_medians=[round(float(x), 1) for x in np.median(jl, 0)],
		pooled_median=med(pool), L_p10=float(np.percentile(jl[:, 0], 10)), L_p90=float(np.percentile(jl[:, 0], 90)))
	log(f"[C] julho n={len(jl)}: L* mediano das medianas {out['julho']['median_of_piece_medians']}, "
		f"p10 {out['julho']['L_p10']:.1f} p90 {out['julho']['L_p90']:.1f}")
	# A1 e B2 de hoje, com a casa da arte correspondente
	alab = {"clean": alab_c, "box": alab_b}
	for key, fn, row in (("A1", "coluna5-24_300dpi_folhaA.jpg", "top"), ("B2", "coluna5-24_folhaB_300dpi_rot180.jpg", "bottom")):
		ps, n = pieces_npz(key)
		if ps is None:
			ps, n = pieces_simple(os.path.join(PIECES, fn))
		for p in ps:
			if row == "top":
				col = 5 + 5 * (p["fila"] - 1) + p["k"]; l = 1
			else:
				ca = 5 + 5 * (p["fila"] - 1) + (4 - p["k"]); col = GRID[0] + 1 - ca; l = GRID[1]
			p["l"], p["c"] = l, col
			p["art"] = art_cell_lab(alab["clean"], l, col)
			p["box"] = art_cell_lab(alab["box"], l, col)
		Ls = np.array([p["lab"] for p in ps])
		out[key] = dict(n_obj=n, pieces=ps, median_of_piece_medians=[round(float(x), 1) for x in np.median(Ls, 0)],
			art_cells_median=[round(float(x), 1) for x in np.median(np.array([p["art"] for p in ps]), 0)],
			box_cells_median=[round(float(x), 1) for x in np.median(np.array([p["box"] for p in ps]), 0)])
		log(f"[C] {key}: {n} objetos; Lab peças {out[key]['median_of_piece_medians']}; casas na arte {out[key]['art_cells_median']}; "
			f"na caixa {out[key]['box_cells_median']}")
	# regressão L* scan vs arte (todas as amostras emparelhadas)
	sc, ar, bx = [], [], []
	for p in pairs:
		sc.append(p["scan"][0]); ar.append(p["art"][0]); bx.append(p["box"][0])
	for key in ("A1", "B2"):
		for p in out[key]["pieces"]:
			sc.append(p["lab"][0]); ar.append(p["art"][0]); bx.append(p["box"][0])
	sc, ar, bx = map(np.array, (sc, ar, bx))
	for nm, ref in (("clean", ar), ("box", bx)):
		A = np.c_[ref, np.ones_like(ref)]
		g, o = np.linalg.lstsq(A, sc, rcond=None)[0]
		out[f"fit_scan_vs_{nm}"] = dict(gain=float(g), offset=float(o), n=int(len(sc)),
			median_diff=float(np.median(sc - ref)), r=float(np.corrcoef(ref, sc)[0, 1]))
		log(f"[C] L*scan ≈ {g:.2f}·L*{nm} + {o:.1f} (n={len(sc)}, r={out[f'fit_scan_vs_{nm}']['r']:.2f}, "
			f"mediana scan−{nm} {np.median(sc - ref):+.1f})")
	fig_photo(d, sky, sc, ar, bx, out)
	return out


def fig_photo(d, sky, sc, ar, bx, out):
	img = d["rgb"].copy()
	img[sky] = (0.5 * img[sky] + 0.5 * np.array([255, 0, 0])).astype(np.uint8)
	f = 700 / img.shape[0]
	img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
	put(img, "pixeis de ceu usados (vermelho)", 30, 0.8)
	P = np.full((700, 700, 3), 255, np.uint8)
	def xy(a, b):
		return int(60 + a / 100 * 600), int(640 - b / 100 * 600)
	cv2.line(P, xy(0, 0), xy(100, 100), (150, 150, 150), 1)
	cv2.rectangle(P, xy(0, 0), xy(100, 100), (0, 0, 0), 1)
	n_sec = len(out["section_cells"]); nA = len(out["A1"]["pieces"])
	for i, (a, s_, b) in enumerate(zip(ar, sc, bx)):
		col = (0, 0, 255) if i < n_sec else ((0, 150, 255) if i < n_sec + nA else (0, 160, 0))
		cv2.circle(P, xy(a, s_), 4, col, -1)
		cv2.drawMarker(P, xy(b, s_), (255, 0, 0), cv2.MARKER_TILTED_CROSS, 7, 1)
	cv2.putText(P, "x: L* arte (pontos) / caixa (x)  y: L* scan", (40, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)
	cv2.putText(P, "azul escuro: seccao; azul claro: A1; verde: B2", (40, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)
	for v in (0, 25, 50, 75, 100):
		cv2.putText(P, str(v), (xy(v, 0)[0] - 10, 665), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
		cv2.putText(P, str(v), (20, xy(0, v)[1] + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
	fig = np.hstack([img, P])
	cv2.imwrite(os.path.join(OUT, "seccao_fotometria.png"), cv2.cvtColor(fig, cv2.COLOR_RGB2BGR))


# ----------------------------------------------------------------------------- main
def clean_json(o):
	if isinstance(o, dict):
		return {str(k): clean_json(v) for k, v in o.items()}
	if isinstance(o, (list, tuple)):
		return [clean_json(v) for v in o]
	if isinstance(o, (np.floating,)):
		return float(o)
	if isinstance(o, (np.integer,)):
		return int(o)
	if isinstance(o, np.bool_):
		return bool(o)
	return o


def main():
	t0 = time.time()
	resA, cache, pitch = part_A()
	for name in SCANS:
		fig_lines(cache, resA, name)
	cmp_res = {}; cmp_pairs = {}
	for tag in ("semprior", "watershed"):
		for na, nb in (("frente_300", "traseira_300"), ("frente_600", "traseira_600"),
				("frente_300", "frente_600"), ("traseira_300", "traseira_600")):
			ka = kb = None
			if tag == "watershed":
				ka = kb = "hessiana/watershed"
			o, p = compare_pair(cache, resA, na, nb, ka, kb)
			cmp_res[f"{na}__{nb}__{tag}"] = o; cmp_pairs[(na, nb, tag)] = p
	fig_fvt(cache, resA, cmp_pairs, os.path.join(OUT, "seccao_frente_vs_traseira.png"))
	topo = {}
	for name in SCANS:
		for key in sorted({best_method(resA, name), "hessiana/watershed"}):
			topo[f"{name}__{key}"] = topology(cache, resA, name, key)
	resB, refs, best_by_ref, bctx = part_B(cache, pitch)
	lc = save_cells_json(cache, resA, best_by_ref["clean"], pitch, cmp_pairs)
	log(f"[B] casas ocupadas (l,c): {lc}")
	resC = part_C(cache, resA, refs, best_by_ref, bctx, pitch)
	pairs_small = {f"{a}__{b}__{t}": [dict(iu=p["iu"], iw=p["iw"], rms_free=p["rms_free"], rms_corner=p["rms_corner"],
		direct_mean_mm=p["direct_mean_mm"], cls_a=p["cls_a"], cls_b=p["cls_b"]) for p in v] for (a, b, t), v in cmp_pairs.items()}
	out = dict(expected_by_eye=EXPECTED_BY_EYE, pitch_mm=dict(u=pitch[0], w=pitch[1]),
		parteA=resA, frente_vs_traseira=cmp_res, pares=pairs_small, topologia=topo, parteB=resB,
		casas_lc=lc, parteC=resC, segundos=time.time() - t0, log=LOG)
	with open(os.path.join(OUT, "seccao_results.json"), "w", encoding="utf-8") as f:
		json.dump(clean_json(out), f, ensure_ascii=False, indent=1)
	log(f"total {time.time() - t0:.0f} s")


if __name__ == "__main__":
	main()
