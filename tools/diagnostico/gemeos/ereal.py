"""E-real: a cadeia real (célula das linhas de corte de uma secção montada -> gémeo entre as peças soltas digitalizadas).

Diagnóstico (não é código de produção). Correr a partir da raiz do repositório:

	PowerShell:  $env:PPF_SCRATCH = "C:\\caminho\\scratchpad"; $env:PYTHONIOENCODING = "utf-8"
	python tools/diagnostico/gemeos/ereal.py

Entrada (300 dpi, papel verde):
  images/pieces/gt_canto_BD_frente_300dpi.jpg         bloco BD montado, canto em baixo à direita (41 peças)
  images/pieces/gt_canto_BD_frente_300dpi_rot180.jpg  o mesmo bloco rodado 180° (re-scan com mudança de pose)
  images/pieces/gt_canto_BD_soltas_300dpi.jpg          as 28 interiores soltas (vista explodida, bloco rodado 90° anti-horário)
  images/pieces/frente_300dpi.jpg                      secção UL (canto superior esquerdo), a mesma de seccao.py
  docs/diagnostico/gemeos/seccao_celulas.json          (l, c) e passo da secção UL (controlo da re-extração)
  $PPF_SCRATCH/gemeos/esym.pkl                         peças do E-sym, variante "scan" (A1, B2) para o pool de 68
Saída: docs/diagnostico/gemeos/ereal_*.png/jpg, ereal_gt.json, results.json (só a chave "ereal").

Coordenadas: BD local (k, j) = (linha a contar de baixo, coluna a contar da direita), global (l, c) = (48 - k, 65 - j);
o gémeo de BD(k, j) é a célula global (k, j) da secção UL. Ver images/pieces/gt_canto_BD.md.
Extração das linhas de corte: as funções de seccao.py (Hessiana em L*, 'histerese' sem prior, 'watershed' com prior
da grelha), com a imagem rodada para pôr o canto em baixo à esquerda (lados retos 'left' e 'bottom').
Métricas de forma: "free" = esym.free_vec + dist.free_dist (mm RMS; principal); "corner" = shapelib.shape_dist (controlo).
"""
import os
import sys
import json
import time
import pickle

import numpy as np
import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import segcache as sc  # noqa: E402  (insere a raiz e tools/diagnostico/forma no sys.path)
import seccao as sx  # noqa: E402  (main() só corre como script)
import esym as es  # noqa: E402
from shapelib import MM, analyse_v2, shape_dist, ccw, resample_closed  # noqa: E402
from dist import free_dist  # noqa: E402

REPO = sc.REPO
OUT = sc.OUT
PIECES = os.path.join(REPO, "images", "pieces")
WORK = os.path.join(sc.S, "ereal")
F_FRENTE = os.path.join(PIECES, "gt_canto_BD_frente_300dpi.jpg")
F_ROT180 = os.path.join(PIECES, "gt_canto_BD_frente_300dpi_rot180.jpg")
F_SOLTAS = os.path.join(PIECES, "gt_canto_BD_soltas_300dpi.jpg")
F_UL = os.path.join(PIECES, "frente_300dpi.jpg")
DPI = 300
PX_MM = 25.4 / DPI
KEYS = ("hessiana/histerese", "hessiana/watershed", "branco/histerese", "branco/watershed")
PRIOR = {"hessiana/histerese": False, "hessiana/watershed": True, "branco/histerese": False, "branco/watershed": True}
REGROW_MM = 1.4         # orla da silhueta devolvida às células (a máscara 'inner' de seccao.py está erodida 1 mm)
GRID_L, GRID_C = 47, 64
T95_ESYM = 0.507        # p95 do RMS free dos gémeos no E-sym (results.json -> esym.extrapolation.hibrido.free.t_p95)
LOG = []

# disposição esperada do bloco BD (k, j): k = 1..5 completas para j = 1..7; k = 6 só j <= 5; k = 7 só j = 1
BD_EXPECTED = sorted([(k, j) for k in range(1, 6) for j in range(1, 8)] + [(6, j) for j in range(1, 6)] + [(7, 1)])


def log(*a):
	s = " ".join(str(x) for x in a)
	LOG.append(s)
	print(s, flush=True)


def r3(v):
	return None if v is None else round(float(v), 3)


def st(x):
	"""mediana / p90 / máx (e n) de uma série em mm."""
	x = np.asarray([v for v in x if v is not None], float)
	if len(x) == 0:
		return dict(n=0)
	return dict(n=int(len(x)), median=r3(np.median(x)), p90=r3(np.percentile(x, 90)), max=r3(x.max()),
				min=r3(x.min()), mean=r3(x.mean()), p95=r3(np.percentile(x, 95)))


# ----------------------------------------------------------------------------- rotações (puras)
def rot_back(pts, rotate, shape0):
	"""Pontos (x, y) na imagem rodada por cv2.rotate(img, rotate) -> coordenadas da imagem original (H0, W0)."""
	p = np.asarray(pts, float)
	H0, W0 = shape0[:2]
	if rotate is None:
		return p.copy()
	if rotate == cv2.ROTATE_90_CLOCKWISE:          # xr = H0-1-y, yr = x
		return np.c_[p[:, 1], H0 - 1 - p[:, 0]]
	if rotate == cv2.ROTATE_90_COUNTERCLOCKWISE:   # xr = y, yr = W0-1-x
		return np.c_[W0 - 1 - p[:, 1], p[:, 0]]
	if rotate == cv2.ROTATE_180:
		return np.c_[W0 - 1 - p[:, 0], H0 - 1 - p[:, 1]]
	raise ValueError(rotate)


# ----------------------------------------------------------------------------- linhas de corte (seccao.py como biblioteca)
def cells_of_scan(path, rotate, pitch=None, name=""):
	"""Mesmo corpo que seccao.part_A, para um único scan a 300 dpi. rotate: código cv2.ROTATE_* que põe o canto do
	bloco em baixo à esquerda (lados retos 'left' e 'bottom'). pitch: (pu, pw) em mm; None = autocorrelação deste scan.
	Devolve o dict de cache (como em seccao) com d['per']['hessiana/<modo>'] e d['res'][modo] (contagens)."""
	t0 = time.time()
	rgb0 = sx.read_rgb(path)
	rgb = cv2.rotate(rgb0, rotate) if rotate is not None else rgb0
	H0, W0 = rgb.shape[:2]
	m = sx.fg_mask(rgb, open_px=sx.odd(0.4 / PX_MM))
	block, outer = sx.fill_largest(m)
	fr = sx.corner_frame(block)
	if fr["straight"] != ["bottom", "left"]:
		raise SystemExit(f"[E-real] {name}: lados retos detetados {fr['straight']} (frac {fr['fracs']}); esperava "
						 f"['bottom', 'left'] depois da rotação. Rotação errada?")
	ys, xs = np.nonzero(block)
	pad = int(2 / PX_MM)
	y0, y1 = max(0, ys.min() - pad), min(H0, ys.max() + pad)
	x0, x1 = max(0, xs.min() - pad), min(W0, xs.max() + pad)
	crop = rgb[y0:y1, x0:x1]
	blk = block[y0:y1, x0:x1]
	inner = cv2.erode(blk.astype(np.uint8), sx.ell(sx.odd(2 * 1.0 / PX_MM))).astype(bool)
	L = sx.lab_f(crop)[:, :, 0]
	fr_c = dict(fr)
	fr_c["corner"] = (fr["corner"][0] - x0, fr["corner"][1] - y0)
	R8 = sx.response_u8(L, inner, DPI, "hessiana")
	pa = sx.pitch_autocorr(R8, inner, fr_c, PX_MM)
	d = dict(name=name, path=path, rotate=rotate, shape_orig=rgb0.shape[:2], rgb=crop, block=blk, inner=inner, fr=fr_c,
			 off=(x0, y0), dpi=DPI, px_mm=PX_MM, R8s={"hessiana": R8}, per={}, res={}, pitch_ac=pa,
			 nom=sx.CELL_AREA_MM2 / PX_MM ** 2, phi_deg=float(np.degrees(fr["phi"])), fracs=fr["fracs"])
	log(f"[ext] {name}: bloco {blk.sum() * PX_MM ** 2:.0f} mm2, lados retos {fr['straight']} frac {fr['fracs']}, "
		f"phi {d['phi_deg']:.2f} deg; passo por autocorrelação u {pa[0]:.2f} w {pa[1]:.2f} mm ({time.time() - t0:.1f} s)")
	if pitch is not None:
		extract(d, pitch)
	return d


def extract(d, pitch):
	"""Ocupação da grelha e células para cada chave de KEYS: 'hessiana/*' = seccao.extract_cells sem alterações
	(vale de L*); 'branco/histerese' = seccao.extract_cells sobre a resposta 'branco'; 'branco/watershed' =
	watershed_puro sobre 'branco'. 'histerese' = sem prior; 'watershed' = sementes nos centros da grelha (prior)."""
	t0 = time.time()
	pu, pw = pitch
	d["pitch"] = (float(pu), float(pw))
	fr = d["fr"]
	occ = sx.occupancy(d["block"], fr, PX_MM, pu, pw)
	d["occ"] = occ
	c_, s_ = np.cos(fr["phi"]), np.sin(fr["phi"])
	seeds = []
	for iu, iw in occ:
		u = (iu + 0.5) * pu / PX_MM
		w = -(iw + 0.5) * pw / PX_MM
		seeds.append((fr["corner"][0] + u * c_ - w * s_, fr["corner"][1] + u * s_ + w * c_, 0.15 * pu / PX_MM))
	block_area = float(d["inner"].sum())
	if "branco" not in d["R8s"]:
		d["R8s"]["branco"] = branco_response(d["rgb"], d["inner"])
		d["pitch_ac_branco"] = sx.pitch_autocorr(d["R8s"]["branco"], d["inner"], fr, PX_MM)
	for key in KEYS:
		resp, mode = key.split("/")
		if key == "branco/watershed":
			ex = watershed_puro(d["R8s"][resp], d["inner"], seeds)
		else:
			ex = sx.extract_cells(d["R8s"][resp], d["inner"], DPI, mode, seeds)
		st_, cen = ex["stats"], ex["cen"]
		cells = []
		for i in range(1, ex["n"]):
			a = int(st_[i, cv2.CC_STAT_AREA])
			k = sx.classify_area(a / d["nom"])
			if k == "speck":
				continue
			uw = sx.to_uw([(float(cen[i, 0]), float(cen[i, 1]))], fr, PX_MM)[0]
			cells.append(dict(i=i, area_px=a, ratio=a / d["nom"], kind=k, cen=(float(cen[i, 0]), float(cen[i, 1])),
							  iu=int(np.floor(uw[0] / pu)), iw=int(np.floor(-uw[1] / pw))))
		hits = {}
		for c in cells:
			if c["kind"] == "valid":
				hits.setdefault((c["iu"], c["iw"]), []).append(c)
		rec = {o: hits[o][0] for o in occ if len(hits.get(o, [])) == 1}
		kinds = [c["kind"] for c in cells]
		d["per"][key] = dict(ex=ex, cells=cells, rec=rec)
		d["res"][key] = dict(recovered=len(rec), expected=len(occ), n_valid=kinds.count("valid"),
							  n_double=kinds.count("double"), n_multi=kinds.count("multi"), n_frag=kinds.count("frag"),
							  pct_area_valid=r3(100.0 * sum(c["area_px"] for c in cells if c["kind"] == "valid") / block_area),
							  support=r3(ex.get("support")) if ex.get("support") is not None else None)
		log(f"[ext] {d['name']} {key}: válidas {kinds.count('valid')}, recuperadas {len(rec)}/{len(occ)}, "
			f"2x {kinds.count('double')}, multi {kinds.count('multi')}, frag {kinds.count('frag')}")
	log(f"    {d['name']}: {time.time() - t0:.1f} s")
	return d


def regrow_labels(d, key):
	"""Células até à linha central do corte e até à silhueta. As células de seccao.py são componentes do complemento
	das linhas (linha dilatada + abertura de 0,4 mm) dentro de 'inner' (bloco erodido 1 mm): o contorno fica no bordo
	interior da linha e 1 mm para dentro nos lados do contorno do bloco. Aqui cada píxel do bloco que não é de nenhuma
	componente vai para a componente mais próxima (Voronoi de todas as componentes, por isso a fronteira entre duas
	células fica no eixo médio da linha), se estiver a <= REGROW_MM dela; só se guardam as células recuperadas."""
	P = d["per"][key]
	lab = P["ex"]["lab"]
	ids = np.array([c["i"] for c in P["rec"].values()], np.int32)
	anyc = (lab > 0) & d["inner"]
	inv = (~anyc).astype(np.uint8)
	dist_, lbl = cv2.distanceTransformWithLabels(inv, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
	zero = np.where(inv.ravel() == 0)[0]
	lut = np.zeros(lbl.max() + 1, np.int32)
	lut[np.arange(1, len(zero) + 1)] = lab.ravel()[zero]
	near = lut[lbl]
	grow = d["block"] & ~anyc & (dist_ <= REGROW_MM / PX_MM)
	out = np.where(anyc, lab, 0)
	out[grow] = near[grow]
	out[~np.isin(out, ids)] = 0
	return out


def cell_contours(d, key, regrow):
	"""{(iu, iw): contorno (px, coordenadas do crop rodado)} das células recuperadas (uma célula válida na casa)."""
	P = d["per"][key]
	lab = regrow_labels(d, key) if regrow else P["ex"]["lab"]
	out = {}
	for o, c in P["rec"].items():
		m = (lab == c["i"]).astype(np.uint8)
		cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
		out[o] = max(cs, key=cv2.contourArea).reshape(-1, 2).astype(float)
	return out


def to_orig(d, cc):
	"""Contorno no crop rodado -> px da imagem original do ficheiro."""
	return rot_back(np.asarray(cc, float) + np.array(d["off"], float), d["rotate"], d["shape_orig"])


def frontier(occ, iu, iw):
	"""Lados da casa (iu, iw) no contorno do bloco: 'frame' = lado reto (iu = 0 ou iw = 0), 'free' = vizinho vazio."""
	S = set(occ)
	n_frame = int(iu == 0) + int(iw == 0)
	n_free = sum(1 for du, dw in ((1, 0), (-1, 0), (0, 1), (0, -1))
				 if iu + du >= 0 and iw + dw >= 0 and (iu + du, iw + dw) not in S)
	return n_frame, n_free


# ----------------------------------------------------------------------------- variante "branco" (minha; relva)
W_CHROMA = 1.5          # W = L* - 1,5·C*: o corte na frente é uma linha acromática (orla branca + vale preto)
W_SIGMA_MM = 0.15       # crista clara da Hessiana de W (σ 0,15 mm)


def branco_response(rgb, inner):
	"""Resposta 'branco': maior curvatura negativa (crista clara) de W = L* - W_CHROMA·C*, normalizada ao p99,5 dentro
	do bloco. Na relva o vale de L* (seccao.py) dispara na textura; o corte vê-se como orla clara e acromática."""
	lab = sx.lab_f(rgb)
	Wv = (lab[..., 0] - W_CHROMA * np.hypot(lab[..., 1], lab[..., 2])).astype(np.float32)
	s = W_SIGMA_MM / PX_MM
	G = cv2.GaussianBlur(Wv, (0, 0), s)
	dxx = cv2.Sobel(G, cv2.CV_32F, 2, 0, ksize=3)
	dyy = cv2.Sobel(G, cv2.CV_32F, 0, 2, ksize=3)
	dxy = cv2.Sobel(G, cv2.CV_32F, 1, 1, ksize=3)
	R = np.maximum(-(0.5 * (dxx + dyy) - np.sqrt(0.25 * (dxx - dyy) ** 2 + dxy ** 2)), 0)
	hi = float(np.percentile(R[inner], 99.5)) + 1e-9
	return np.clip(R / hi * 255.0, 0, 255).astype(np.uint8)


def watershed_puro(R8, inner, seeds):
	"""Como o 'watershed' de seccao.extract_cells, mas sem somar as linhas da histerese às fronteiras (na relva a
	histerese marca a textura e parte todas as células). Linhas = fronteiras da inundação dilatadas 2x2, abertura 0,4 mm."""
	mk = np.zeros(R8.shape, np.int32)
	mk[~cv2.dilate(inner.astype(np.uint8), sx.ell(3)).astype(bool)] = 1
	for j, (x, y, r) in enumerate(seeds):
		cv2.circle(mk, (int(round(x)), int(round(y))), int(r), 2 + j, -1)
	mk[~inner & (mk > 1)] = 0
	relief = cv2.GaussianBlur(R8, (0, 0), 0.1 / PX_MM)
	ws = cv2.watershed(cv2.cvtColor(relief, cv2.COLOR_GRAY2BGR), mk)
	lines = cv2.dilate(((ws == -1) & inner).astype(np.uint8), np.ones((2, 2), np.uint8)).astype(bool) & inner
	comp = cv2.morphologyEx((inner & ~lines).astype(np.uint8), cv2.MORPH_OPEN, sx.ell(sx.odd(0.4 / PX_MM)))
	n, lab, st_, cen = cv2.connectedComponentsWithStats(comp, connectivity=4)
	return dict(R8=R8, otsu=None, lines=lines, lab=lab, stats=st_, cen=cen, n=n, close_px=None)


# ----------------------------------------------------------------------------- peças de forma
def mkpiece(contour_px, **meta):
	"""Contorno (px, 300 dpi) -> dict analisado (analyse_v2 + vetor free de esym.free_vec)."""
	p = dict(contour=np.asarray(contour_px, float).reshape(-1, 2), **meta)
	try:
		analyse_v2(p)
	except Exception as e:      # noqa: BLE001
		p["ok"] = False
		p["err"] = str(e)
		if "c" not in p:
			p["c"] = ccw(resample_closed(p["contour"], 1200))
	p["z"] = es.free_vec(p["c"])
	return p


def section_cells(d, key, regrow, to_key):
	"""{chave GT: peça} das células recuperadas; to_key(iu, iw) -> chave (p.ex. (l, c) ou (k, j))."""
	occ = d["occ"]
	out = {}
	for (iu, iw), cc in cell_contours(d, key, regrow).items():
		nfr, nfree = frontier(occ, iu, iw)
		out[to_key(iu, iw)] = mkpiece(cc, iu=iu, iw=iw, n_frame=nfr, n_free=nfree, contour_orig=to_orig(d, cc))
	return out


def cell_area(p):
	return float(cv2.contourArea(p["contour"].astype(np.float32).reshape(-1, 1, 2))) * PX_MM ** 2


def qc_ref(cells):
	"""Referência do controlo de qualidade (sem GT): p95 da rugosidade e mediana da área das células UL (céu)."""
	return dict(rough_p95=float(np.percentile([p["rough"] for p in cells.values() if p.get("ok")], 95)),
				area_median=float(np.median([cell_area(p) for p in cells.values()])))


def qc_ok(p, ref):
	"""Célula aceitável sem olhar para a GT: 4 cantos, nº de lados F = nº de lados retos esperados, rugosidade <= p95
	das células UL e área em [0,85; 1,2] x a mediana UL."""
	return bool(p.get("ok") and p["types"].count("F") == p["n_frame"] and p["rough"] <= ref["rough_p95"]
				and 0.85 * ref["area_median"] <= cell_area(p) <= 1.2 * ref["area_median"])


def free_d(a, b):
	return free_dist(a, b)[0]


def corner_d(a, b):
	"""Métrica de cantos (simetrizada com o mínimo, como no E-sym); NaN se faltarem cantos."""
	if not (a.get("ok") and b.get("ok")):
		return np.nan
	return min(shape_dist(a, b)[0], shape_dist(b, a)[0])


def dmat(QA, CB, f=free_d):
	return np.array([[f(a, b) for b in CB] for a in QA], float)


# ----------------------------------------------------------------------------- peças soltas (GT por posição)
def loose_pieces():
	"""segment_scan no scan das soltas; (k, j) pela grelha 6 x 5 (fila r de cima, coluna s a contar da DIREITA):
	j = r + 1, k = s + 1. Verificações automáticas; aborta com mensagem clara se falharem."""
	from PIL import Image
	from src.segmentation import segment_scan
	t0 = time.time()
	with Image.open(F_SOLTAS) as im:
		im.load()
		r = segment_scan(im)
	if "error" in r:
		raise SystemExit(f"[E-real] segment_scan falhou nas soltas: {r['error']}")
	allp = r["pieces"]

	def area(p):
		return cv2.contourArea(np.asarray(p["contour"]).reshape(-1, 1, 2).astype(np.float32)) * PX_MM ** 2

	def bad_piece(p):
		return bool(p["is_cluster"] or p.get("touches_frame") or area(p) > 1200)
	excl = [dict(index=p["index"], is_cluster=bool(p["is_cluster"]), touches_frame=bool(p.get("touches_frame")),
				 area_mm2=r3(area(p))) for p in allp if bad_piece(p)]
	P = [p for p in allp if not bad_piece(p)]
	log(f"[soltas] segment_scan: {len(allp)} peças, excluídas {len(excl)} {excl}; {time.time() - t0:.1f} s")
	if len(P) != 28:
		raise SystemExit(f"[E-real] esperava 28 peças soltas (não cluster, longe do bordo), obtive {len(P)}")
	b = np.array([p["bbox"] for p in P], float)
	cx, cy = b[:, 0] + b[:, 2] / 2, b[:, 1] + b[:, 3] / 2
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
	counts = [len(rw) for rw in rows]
	if counts != [5, 5, 5, 5, 4, 4]:
		raise SystemExit(f"[E-real] filas das soltas: {counts}; esperava [5, 5, 5, 5, 4, 4]")
	col_x = {}
	for rw in rows[:4]:
		for s, i in enumerate(sorted(rw, key=lambda j: -cx[j]), 1):
			col_x.setdefault(s, []).append(cx[i])
	col_x = {s: float(np.median(v)) for s, v in col_x.items()}
	out = []
	for r_, rw in enumerate(rows, 1):
		for s, i in enumerate(sorted(rw, key=lambda j: -cx[j]), 1):
			near = min(col_x, key=lambda q: abs(col_x[q] - cx[i]))
			if near != s:
				raise SystemExit(f"[E-real] fila {r_}: a peça {P[i]['index']} (x {cx[i]:.0f}) está mais perto da coluna "
								 f"s={near} (x {col_x[near]:.0f}) do que da s={s}; colunas {col_x}")
			p = mkpiece(np.asarray(P[i]["contour"]).reshape(-1, 2), index=int(P[i]["index"]), r=r_, s=s, k=s + 1, j=r_ + 1,
						bbox=[int(v) for v in P[i]["bbox"]], cx=float(cx[i]), cy=float(cy[i]))
			out.append(p)
	bad = [(p["k"], p["j"], "".join(p.get("types", "?"))) for p in out if not p.get("ok") or "F" in p["types"]]
	if bad:
		raise SystemExit(f"[E-real] soltas sem 4 cantos ou com lado F (deviam ser todas interiores): {bad}")
	# a coluna k = 6 (s = 5) tem a faixa do caminho: cinzento claro pouco saturado (L* > 55, C* < 22) nas filas 2-4 e
	# preto acromático (L* < 12, C* < 12) na peça (6, 2) da fila 1 (vê-se no scan). O L* mediano e a fração de C* < 15
	# não servem: as sombras escuras da relva também são pouco saturadas.
	rgb = sx.read_rgb(F_SOLTAS)
	lab = sx.lab_f(rgb)
	for p in out:
		m = np.zeros(rgb.shape[:2], np.uint8)
		cv2.fillPoly(m, [np.round(p["contour"]).astype(np.int32).reshape(-1, 1, 2)], 1)
		px = lab[m > 0]
		C = np.hypot(px[:, 1], px[:, 2])
		p["L_med"] = float(np.median(px[:, 0]))
		p["road_frac"] = float(np.mean((px[:, 0] > 55) & (C < 22)))
		p["black_frac"] = float(np.mean((px[:, 0] < 12) & (C < 12)))
	top3 = sorted(out, key=lambda p: -p["road_frac"])[:3]
	blk = max(out, key=lambda p: p["black_frac"])
	if sorted((p["k"], p["j"]) for p in top3) != [(6, 3), (6, 4), (6, 5)] or (blk["k"], blk["j"]) != (6, 2):
		raise SystemExit("[E-real] a faixa do caminho devia estar na coluna k=6 (s=5): 3 mais cinzentas "
						 f"{[(p['k'], p['j'], round(p['road_frac'], 3)) for p in top3]}, mais preta {(blk['k'], blk['j'], round(blk['black_frac'], 3))}")
	k6 = [p["L_med"] for p in out if p["k"] == 6]
	oth = [p["L_med"] for p in out if p["k"] != 6]
	log(f"[soltas] grelha verificada: filas {counts}, colunas x {dict((s, round(v)) for s, v in col_x.items())}; faixa do caminho "
		f"na coluna k=6: cinzento {[round(p['road_frac'], 3) for p in out if p['k'] == 6]} (outras máx "
		f"{max(p['road_frac'] for p in out if p['k'] != 6):.3f}), preto em (6,2) {blk['black_frac']:.3f} (outras máx "
		f"{max(p['black_frac'] for p in out if (p['k'], p['j']) != (6, 2)):.3f})")
	chk = dict(n_segment_scan=len(allp), excluded=excl, rows=counts, col_x={str(s): r3(v) for s, v in col_x.items()},
			   road_frac={f"{p['k']},{p['j']}": r3(p["road_frac"]) for p in out},
			   black_frac={f"{p['k']},{p['j']}": r3(p["black_frac"]) for p in out},
			   Lmed_k6=[r3(v) for v in k6], Lmed_others_median=r3(np.median(oth)),
			   classes={f"{p['k']},{p['j']}": p["cls"] for p in out})
	return out, chk


def esym_pool():
	"""40 peças de borda do E-sym (variante 'scan' = segment_scan: A1 e B2) de $PPF_SCRATCH/gemeos/esym.pkl."""
	pk = os.path.join(sc.S, "gemeos", "esym.pkl")
	if not os.path.exists(pk):
		raise SystemExit(f"[E-real] falta {pk}; correr primeiro tools/diagnostico/gemeos/esym.py")
	with open(pk, "rb") as f:
		D = pickle.load(f)["scan"]
	out = []
	for name in ("A1", "B2"):
		for i, p in enumerate(D[name]):
			q = dict(p)
			q["key"] = (name, i)
			out.append(q)
	return out


# ----------------------------------------------------------------------------- estatísticas de consulta
def queries(QK, CK, D, gt, qcls=None, ccls=None):
	"""D[i, j] = distância da consulta QK[i] ao candidato CK[j]; gt: chave de consulta -> chave do verdadeiro.
	Só entram consultas com o verdadeiro no pool. Com qcls/ccls: filtro de classe (candidatos da mesma classe; se a
	classe do verdadeiro difere, a consulta falha). Margem = não-verdadeiro mais próximo / verdadeiro."""
	rows = []
	cidx = {k: j for j, k in enumerate(CK)}
	for i, q in enumerate(QK):
		t = gt.get(q)
		if t is None or t not in cidx:
			continue
		row = D[i].copy()
		jt = cidx[t]
		if qcls is not None:
			keep = np.array([ccls.get(c) is not None and ccls.get(c) == qcls.get(q) for c in CK])
			if not keep[jt]:
				rows.append(dict(q=q, t=t, d_true=r3(row[jt]), rank=None, top1=False, nn=None, nn_key=None, margin=None,
								 cls_ok=False, n_pool=int(keep.sum())))
				continue
			row = np.where(keep, row, np.inf)
		masked = row.copy()
		masked[jt] = np.inf
		jn = int(np.argmin(masked))
		nn = float(masked[jn])
		rank = int(np.sum(masked < row[jt]))
		fin = np.isfinite(nn)
		rows.append(dict(q=q, t=t, d_true=r3(row[jt]), rank=rank, top1=rank == 0, nn=r3(nn) if fin else None,
						 nn_key=CK[jn] if fin else None, margin=r3(nn / max(row[jt], 1e-9)) if fin else None,
						 cls_ok=True, n_pool=int(np.isfinite(row).sum())))
	n = len(rows)
	mg = [r["margin"] for r in rows if r["margin"] is not None]
	summ = dict(n=n, top1=int(sum(r["top1"] for r in rows)), top1_frac=r3(sum(r["top1"] for r in rows) / max(1, n)),
				d_true=st([r["d_true"] for r in rows]), nn_nontrue=st([r["nn"] for r in rows if r["nn"] is not None]),
				margin_min=r3(min(mg)) if mg else None, margin_median=r3(np.median(mg)) if mg else None,
				margin_lt_1_5=int(sum(m < 1.5 for m in mg)), class_fail=int(sum(not r["cls_ok"] for r in rows)),
				misses=[dict(q=list(r["q"]), true=list(r["t"]), rank=r["rank"], d_true=r["d_true"], nn=r["nn"],
							 nn_key=list(r["nn_key"]) if r.get("nn_key") is not None else None) for r in rows if not r["top1"]])
	return rows, summ


def mutual_nn(QK, CK, D, gt):
	am = D.argmin(1)
	amc = D.argmin(0)
	cidx = {k: j for j, k in enumerate(CK)}
	n_mut = n_mut_ok = 0
	for i, q in enumerate(QK):
		if amc[am[i]] == i:
			n_mut += 1
			n_mut_ok += int(gt.get(q) is not None and cidx.get(gt[q]) == am[i])
	return dict(mutual=n_mut, mutual_correct=n_mut_ok)


def side_pairs(pairs):
	"""Lados homólogos (best_k do shape_dist): |ΔL| e concordância do tipo T/B/F. pairs = [(pa, pb)]."""
	dl, agree, tot = [], 0, 0
	for pa, pb in pairs:
		if not (pa.get("ok") and pb.get("ok")):
			continue
		_, k, _ = shape_dist(pa, pb)
		for s in range(4):
			sb = (s + k) % 4
			dl.append(abs(pa["lens"][s] - pb["lens"][sb]))
			agree += pa["types"][s] == pb["types"][sb]
			tot += 1
	return dict(n_pairs=int(tot // 4), n_sides=tot, absdL=st(dl), type_agree=f"{agree}/{tot}")


# ----------------------------------------------------------------------------- (c1) viés célula de linha de corte vs silhueta
SIDE_DIRS = {"baixo": np.array([0.0, 1.0]), "cima": np.array([0.0, -1.0]), "esq": np.array([-1.0, 0.0]), "dir": np.array([1.0, 0.0])}


def side_dir(side, ctr):
	"""Orientação ('baixo', 'cima', 'esq', 'dir') da normal exterior de um lado, no referencial do scanner (y para baixo)."""
	mid = 0.5 * (side[0] + side[-1]) - ctr
	return max(SIDE_DIRS, key=lambda k: SIDE_DIRS[k] @ mid)


def bias_pair(sil, cell):
	"""Silhueta (segment_scan, referencial do scanner das soltas) contra a célula da linha de corte da MESMA peça.
	Alinhamento free (rotação + translação pelos centróides, correspondência cíclica): RMS rígido; escala ótima
	lambda (silhueta ≈ lambda·célula) e RMS depois da escala; desvio normal com sinal por lado da silhueta
	(+ = silhueta fora da célula), média por orientação (baixo/cima/esq/dir); ΔL com sinal por lado (cantos)."""
	from dist import aligned_b
	from shapelib import smooth_closed
	za, zb, d = aligned_b(sil, cell)
	lam = float(np.real(np.sum(np.conj(zb) * za)) / np.sum(np.abs(zb) ** 2))
	rms_sim = float(np.sqrt(np.mean(np.abs(za - lam * zb) ** 2))) * MM
	ctr = resample_closed(smooth_closed(sil["c"], 1.5), 512).mean(0)
	poly = (np.c_[zb.real, zb.imag] + ctr).astype(np.float32).reshape(-1, 1, 2)
	off = {k: [] for k in SIDE_DIRS}
	sdirs = []
	if sil.get("ok"):
		cc = sil["c"].mean(0)
		for side in sil["sides"]:
			k = side_dir(side, cc)
			sdirs.append(k)
			o = [-cv2.pointPolygonTest(poly, (float(x), float(y)), True) * MM for x, y in side]
			off[k].append(float(np.mean(o)))
	offm = {k: (float(np.mean(v)) if v else None) for k, v in off.items()}
	dl = {k: [] for k in SIDE_DIRS}
	if sil.get("ok") and cell.get("ok"):
		_, kk, _ = shape_dist(sil, cell)
		for s in range(4):
			dl[sdirs[s]].append(float(sil["lens"][s] - cell["lens"][(s + kk) % 4]))
	ok4 = all(offm[k] is not None for k in SIDE_DIRS)
	return dict(rms_free=float(d), scale=lam, rms_after_scale=rms_sim, off=offm, dL=dl, za=za, zb=zb, ctr=ctr, sdirs=sdirs,
				iso=float(np.mean([offm[k] for k in SIDE_DIRS])) if ok4 else None,
				asym_y=(offm["baixo"] - offm["cima"]) if ok4 else None,
				asym_x=(offm["esq"] - offm["dir"]) if ok4 else None)


def bias_summary(rows):
	out = dict(n=len(rows), rms_free=st([r["rms_free"] for r in rows]), scale=st([r["scale"] for r in rows]),
			   rms_after_scale=st([r["rms_after_scale"] for r in rows]),
			   t_p95_rms_free=r3(np.percentile([r["rms_free"] for r in rows], 95)) if rows else None,
			   offset_by_side={k: st([r["off"][k] for r in rows if r["off"][k] is not None]) for k in SIDE_DIRS},
			   dL_signed_by_side={k: st([v for r in rows for v in r["dL"][k]]) for k in SIDE_DIRS},
			   iso=st([r["iso"] for r in rows if r["iso"] is not None]),
			   asym_baixo_menos_cima=st([r["asym_y"] for r in rows if r["asym_y"] is not None]),
			   asym_esq_menos_dir=st([r["asym_x"] for r in rows if r["asym_x"] is not None]))
	return out


# ----------------------------------------------------------------------------- figuras
RED, BLUE, BLK, GRN, GREY = es.RED, es.BLUE, es.BLK, es.GRN, es.GREY


def unrot_img(img, rotate):
	inv = {cv2.ROTATE_90_CLOCKWISE: cv2.ROTATE_90_COUNTERCLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE: cv2.ROTATE_90_CLOCKWISE,
		   cv2.ROTATE_180: cv2.ROTATE_180}
	return img if rotate is None else cv2.rotate(img, inv[rotate])


def unrot_shape(shape, rotate):
	h, w = shape[:2]
	return (w, h) if rotate in (cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE) else (h, w)


def label(img, txt, xy, s=0.5, col=(255, 255, 255)):
	cv2.putText(img, txt, xy, cv2.FONT_HERSHEY_SIMPLEX, s, (0, 0, 0), 3, cv2.LINE_AA)
	cv2.putText(img, txt, xy, cv2.FONT_HERSHEY_SIMPLEX, s, col, 1, cv2.LINE_AA)


def fig_lines(d, fname, title):
	"""Linhas = resposta (hessiana de seccao.py; branco); colunas = resposta, células sem prior, células com prior.
	Painéis na orientação do ficheiro original; células recuperadas rotuladas (k, j)."""
	H = 520
	rows = []
	for resp in ("hessiana", "branco"):
		panels = []
		R = d["R8s"][resp]
		ims = [(cv2.cvtColor(255 - R, cv2.COLOR_GRAY2RGB), f"{resp}: resposta", None)]
		for mode in ("histerese", "watershed"):
			key = f"{resp}/{mode}"
			r = d["res"][key]
			ims.append((sx.colour_cells(d, key), f"{key}: recup. {r['recovered']}/{r['expected']}, validas {r['n_valid']}, "
						f"2x {r['n_double']}, frag {r['n_frag']}", key))
		for im, t, key in ims:
			im2 = unrot_img(im, d["rotate"])
			f = H / im2.shape[0]
			im2 = cv2.resize(im2, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
			if key:
				sh0 = unrot_shape(im.shape, d["rotate"])
				for (iu, iw), c in d["per"][key]["rec"].items():
					q = rot_back(np.array([c["cen"]]), d["rotate"], sh0)[0] * f
					label(im2, f"{iu + 1},{iw + 1}", (int(q[0]) - 12, int(q[1]) + 4), 0.38)
			label(im2, t, (6, 18), 0.45, (255, 255, 0))
			panels.append(im2)
		rows.append(np.hstack(panels))
	W = max(r.shape[1] for r in rows)
	rows = [np.hstack([r, np.full((r.shape[0], W - r.shape[1], 3), 255, np.uint8)]) for r in rows]
	fig = np.vstack(rows)
	fig = es.with_title(cv2.cvtColor(fig, cv2.COLOR_RGB2BGR), title)
	cv2.imwrite(os.path.join(OUT, fname), fig, [cv2.IMWRITE_JPEG_QUALITY, 85])


def fig_soltas(L, fname):
	bgr = cv2.cvtColor(sx.read_rgb(F_SOLTAS), cv2.COLOR_RGB2BGR)
	for p in L:
		cv2.polylines(bgr, [np.round(p["contour"]).astype(np.int32).reshape(-1, 1, 2)], True, (0, 255, 255), 3, cv2.LINE_AA)
	f = 1600 / bgr.shape[0]
	img = cv2.resize(bgr, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
	for p in L:
		x, y = int(p["cx"] * f), int(p["cy"] * f)
		label(img, f"#{p['index']} BD({p['k']},{p['j']})", (x - 48, y - 6), 0.4)
		label(img, f"lc({48 - p['k']},{65 - p['j']}) {p['cls']}", (x - 48, y + 10), 0.36, (200, 255, 200))
	img = es.with_title(img, ["E-real: segment_scan nas soltas (amarelo); BD(k,j) = (fila a contar de baixo, coluna da direita) "
							  "pela grelha; lc = (l,c) global", "fila r (de cima) -> j = r+1; coluna s (da direita) -> k = s+1; "
							  "classe topologica (analyse_v2)"])
	cv2.imwrite(os.path.join(OUT, fname), img, [cv2.IMWRITE_JPEG_QUALITY, 85])


def zpx(z):
	return np.c_[z.real, z.imag]


def fig_pairs(items, fname, title, cols=6):
	"""items: [(pa, pb, linhas)]; pb alinhada a pa pela métrica free."""
	from dist import aligned_b
	tiles = []
	for pa, pb, lines in items:
		za, zb, _ = aligned_b(pa, pb)
		tiles.append(es.tile_pair(zpx(za), zpx(zb), lines, cols=(RED, BLUE)))
	cv2.imwrite(os.path.join(OUT, fname), es.with_title(es.grid(tiles, cols), title))


def fig_bias(rows, fname, title, cols=7):
	"""Silhueta (vermelho) e célula da mesma peça alinhada sem escala (azul), no referencial do scanner das soltas;
	lados da silhueta virados para baixo/esquerda (sombra) a preto grosso."""
	tiles = []
	T = 300
	for r in rows:
		ca = zpx(r["za"])
		cb = zpx(r["zb"])
		t = np.full((T, T, 3), 255, np.uint8)
		allp = np.vstack([ca, cb])
		o = (allp.max(0) + allp.min(0)) / 2
		s_ = (T - 75) / max(np.ptp(allp[:, 0]), np.ptp(allp[:, 1]))
		q = lambda p: np.round((p - o) * s_ + [T / 2, T / 2 + 20]).astype(np.int32).reshape(-1, 1, 2)  # noqa: E731
		sil = r["sil"]
		if sil.get("ok"):
			for side, k in zip(sil["sides"], r["sdirs"]):
				if k in ("baixo", "esq"):
					cv2.polylines(t, [q(side - r["ctr"])], False, BLK, 4, cv2.LINE_AA)
		cv2.polylines(t, [q(ca)], True, RED, 1, cv2.LINE_AA)
		cv2.polylines(t, [q(cb)], True, BLUE, 1, cv2.LINE_AA)
		f = lambda v: "-" if v is None else f"{v:+.2f}"  # noqa: E731
		es.put(t, f"BD({r['k']},{r['j']}) free {r['rms_free']:.2f} escala {r['scale']:.3f}", (5, 15), 0.4)
		es.put(t, f"baixo {f(r['off']['baixo'])} cima {f(r['off']['cima'])}", (5, 30), 0.4)
		es.put(t, f"esq {f(r['off']['esq'])} dir {f(r['off']['dir'])} mm", (5, 45), 0.4)
		L5 = 5 / MM * s_
		cv2.line(t, (T - 10 - int(L5), T - 8), (T - 10, T - 8), BLK, 2)
		es.put(t, "5 mm", (T - 10 - int(L5), T - 14), 0.38)
		cv2.rectangle(t, (0, 0), (T - 1, T - 1), GREY, 1)
		tiles.append(t)
	cv2.imwrite(os.path.join(OUT, fname), es.with_title(es.grid(tiles, cols), title))


def fig_matrix(panels, fname):
	"""panels: [(título, M, rótulos linhas, rótulos colunas, gt: {i: j})]; vermelho = verdadeiro, ponto = argmin."""
	imgs = []
	for tit, M, rl, cl, gt in panels:
		c = 18
		W = 70 + c * len(cl)
		H = 90 + c * len(rl)
		img = np.full((H, W, 3), 255, np.uint8)
		am = np.nanargmin(np.where(np.isfinite(M), M, np.inf), 1)
		for i in range(len(rl)):
			for j in range(len(cl)):
				v = min(M[i, j], 2.0) / 2.0 if np.isfinite(M[i, j]) else 1.0
				col = cv2.applyColorMap(np.uint8([[255 * (1 - v)]]), cv2.COLORMAP_VIRIDIS)[0, 0].tolist()
				x, y = 60 + j * c, 60 + i * c
				cv2.rectangle(img, (x, y), (x + c - 1, y + c - 1), col, -1)
				if gt.get(i) == j:
					cv2.rectangle(img, (x, y), (x + c - 1, y + c - 1), (0, 0, 255), 2)
				if am[i] == j:
					cv2.circle(img, (x + c // 2, y + c // 2), 3, (255, 255, 255), -1)
					cv2.circle(img, (x + c // 2, y + c // 2), 3, BLK, 1)
		for i, s in enumerate(rl):
			es.put(img, s, (2, 60 + i * c + 13), 0.3)
		for j, s in enumerate(cl):
			es.put(img, s, (60 + j * c + 1, 55 - 12 * (j % 2)), 0.27)
		es.put(img, tit, (4, 14), 0.42)
		es.put(img, "cor: 0 (amarelo) .. >= 2 mm (violeta); vermelho = verdadeiro; ponto = argmin da linha", (4, H - 12), 0.36)
		imgs.append(img)
	Hm = max(i.shape[0] for i in imgs)
	imgs = [np.vstack([i, np.full((Hm - i.shape[0], i.shape[1], 3), 255, np.uint8)]) for i in imgs]
	cv2.imwrite(os.path.join(OUT, fname), np.hstack(imgs))


# ----------------------------------------------------------------------------- análises
def kname(k):
	return f"{k[0]},{k[1]}" if isinstance(k[0], (int, np.integer)) else f"{k[0]}{k[1]}"


def section_vs_section(UL, BD):
	"""(a) UL(l, c) contra BD(k = l, j = c), métrica free (e corner de controlo)."""
	QK, CK = sorted(UL), sorted(BD)
	Df = dmat([UL[k] for k in QK], [BD[k] for k in CK])
	Dc = dmat([UL[k] for k in QK], [BD[k] for k in CK], corner_d)
	gt = {k: k for k in QK}
	out = {}
	for tag, sel in (("todas", lambda k: True), ("borda", lambda k: k[0] == 1 or k[1] == 1),
					 ("interior", lambda k: k[0] > 1 and k[1] > 1)):
		g = {k: v for k, v in gt.items() if sel(k)}
		_, s1 = queries(QK, CK, Df, g)
		_, s2 = queries(CK, QK, Df.T, g)
		_, s3 = queries(QK, CK, Df, g, {k: UL[k].get("cls") for k in QK}, {k: BD[k].get("cls") for k in CK})
		_, s4 = queries(QK, CK, np.nan_to_num(Dc, nan=np.inf), g)
		pairs = [(UL[k], BD[k]) for k in g if k in BD]
		both = [(a, b) for a, b in pairs if a.get("ok") and b.get("ok")]
		out[tag] = dict(UL_to_BD=s1, BD_to_UL=s2, UL_to_BD_class_filter=s3, UL_to_BD_corner=s4,
						class_agree=f"{sum(a['cls'] == b['cls'] for a, b in both)}/{len(both)}", sides=side_pairs(pairs))
	out["mutual_nn"] = mutual_nn(QK, CK, Df, gt)
	out["n_UL"], out["n_BD"] = len(QK), len(CK)
	return out, (QK, CK, Df)


def section_vs_loose(UL, L, E, tag="", ref=None):
	"""(b) UL(l, c) contra as soltas BD(k = l, j = c) (o gémeo), pool de 28 e de 68 (+ 40 do E-sym); inverso."""
	QK = sorted(UL)
	LK = [(p["k"], p["j"]) for p in L]
	EK = [p["key"] for p in E]
	Lp = {k: p for k, p in zip(LK, L)}
	Ep = {k: p for k, p in zip(EK, E)}
	D28 = dmat([UL[k] for k in QK], L)
	DE = dmat([UL[k] for k in QK], E)
	D68 = np.hstack([D28, DE])
	CK68 = LK + EK
	gt = {k: k for k in QK if k in Lp}
	qcls = {k: UL[k].get("cls") for k in QK}
	ccls = {**{k: Lp[k].get("cls") for k in LK}, **{k: Ep[k].get("cls") for k in EK}}
	rows28, s28 = queries(QK, LK, D28, gt)
	_, s28c = queries(QK, LK, D28, gt, qcls, ccls)
	rows68, s68 = queries(QK, CK68, D68, gt)
	_, s68c = queries(QK, CK68, D68, gt, qcls, ccls)
	gtr = {k: k for k in LK if k in UL}
	_, srev = queries(LK, QK, D28.T, gtr)
	_, srevc = queries(LK, QK, D28.T, gtr, ccls, qcls)
	Dc = np.nan_to_num(dmat([UL[k] for k in QK], L, corner_d), nan=np.inf)
	_, s28corner = queries(QK, LK, Dc, gt)
	pairs = [(UL[k], Lp[k]) for k in gt]
	both = [(a, b) for a, b in pairs if a.get("ok") and b.get("ok")]
	fr = {k: (UL[k]["n_frame"], UL[k]["n_free"]) for k in gt}
	inner_q = {k: v for k, v in gt.items() if fr[k] == (0, 0)}
	_, s28_in = queries(QK, LK, D28, inner_q)
	front_q = {k: v for k, v in gt.items() if fr[k] != (0, 0)}
	_, s28_fr = queries(QK, LK, D28, front_q)
	qcs = {}
	if ref is not None:
		gq = {k: v for k, v in gt.items() if qc_ok(UL[k], ref)}
		qcs = dict(n=len(gq), pool28=queries(QK, LK, D28, gq)[1], pool68_class_filter=queries(QK, CK68, D68, gq, qcls, ccls)[1])
	out = dict(n_queries=len(gt), pool28=s28, pool28_class_filter=s28c, pool68=s68, pool68_class_filter=s68c,
			   so_consultas_UL_com_qc=qcs,
			   reverse_loose_to_UL=srev, reverse_class_filter=srevc, pool28_corner=s28corner,
			   class_agree=f"{sum(a['cls'] == b['cls'] for a, b in both)}/{len(both)}", sides=side_pairs(pairs),
			   pool28_cells_inside_block=s28_in, pool28_cells_on_block_outline=s28_fr,
			   per_query=[dict(UL=list(r["q"]), d_twin=r["d_true"], rank28=r["rank"], margin28=r["margin"],
							   nn28=r["nn"], nn28_key=list(r["nn_key"]) if r["nn_key"] else None,
							   rank68=r68["rank"], margin68=r68["margin"], cls_UL=qcls[r["q"]], cls_loose=ccls[r["t"]],
							   frame_free=list(fr[r["q"]]))
						  for r, r68 in zip(rows28, rows68)])
	log(f"[b{tag}] UL -> soltas: n={len(gt)}; gémeo free mediana {s28['d_true'].get('median')} p90 {s28['d_true'].get('p90')} "
		f"máx {s28['d_true'].get('max')}; top-1 pool28 {s28['top1']}/{s28['n']} (classe {s28c['top1']}), pool68 "
		f"{s68['top1']}/{s68['n']} (classe {s68c['top1']}); margem mín {s28['margin_min']} med {s28['margin_median']} "
		f"<1,5: {s28['margin_lt_1_5']}; inverso {srev['top1']}/{srev['n']}; classe {out['class_agree']}")
	return out, (QK, LK, D28, CK68, D68)


# ----------------------------------------------------------------------------- (c1) calibração fora da amostra (leave-one-out)
def offset_z(p, delta_mm):
	"""Vetor free do contorno da peça deslocado delta_mm ao longo da normal exterior (dilatação isotrópica)."""
	from shapelib import smooth_closed
	c = p["c"]
	cs = smooth_closed(c, 3)
	t = np.roll(cs, -1, 0) - np.roll(cs, 1, 0)
	n = np.c_[t[:, 1], -t[:, 0]] / (np.linalg.norm(t, axis=1)[:, None] + 1e-12)
	if np.mean(np.sum(n * (c - c.mean(0)), 1)) < 0:
		n = -n
	return es.free_vec(c + delta_mm / MM * n)


def c1_loo(UL, L, E, rows_t):
	"""Calibração célula -> silhueta fora da amostra: para cada consulta UL(k, j) de (b), a escala (mediana de
	'scale') e o desvio isotrópico (mediana de 'iso') vêm das OUTRAS 24 comparações c1 via gémeo; aplicam-se à célula
	retida (escala: z x lambda; desvio: contorno dilatado delta mm ao longo da normal) e recomputa-se d1 / margem contra
	o pool de 28 soltas e o de 68 (+ E-sym), com e sem filtro de classe. 'sem' = sem correção (deve dar os números de (b))."""
	Lp = {(p["k"], p["j"]): p for p in L}
	LK = sorted(Lp)
	EK = [p["key"] for p in E]
	Ep = dict(zip(EK, E))
	byk = {(r["k"], r["j"]): r for r in rows_t}
	QK = [k for k in sorted(UL) if k in Lp and k in byk]
	ccls = {**{k: Lp[k].get("cls") for k in LK}, **{k: Ep[k].get("cls") for k in EK}}
	pool28 = [Lp[k] for k in LK]
	pool68 = pool28 + [Ep[k] for k in EK]
	out = {}
	for var in ("sem", "escala", "desvio"):
		rows28, rows28c, rows68c, cal = [], [], [], []
		for q in QK:
			oth = [byk[k] for k in QK if k != q]
			lam = float(np.median([r["scale"] for r in oth]))
			dlt = float(np.median([r["iso"] for r in oth if r["iso"] is not None]))
			z = UL[q]["z"] * lam if var == "escala" else offset_z(UL[q], dlt) if var == "desvio" else UL[q]["z"]
			qp = dict(UL[q], z=z)
			d28 = np.array([[free_d(qp, b) for b in pool28]])
			d68 = np.array([[free_d(qp, b) for b in pool68]])
			g = {q: q}
			qc = {q: UL[q].get("cls")}
			rows28 += queries([q], LK, d28, g)[0]
			rows28c += queries([q], LK, d28, g, qc, ccls)[0]
			rows68c += queries([q], LK + EK, d68, g, qc, ccls)[0]
			cal.append(dict(k=list(q), scale=r3(lam), iso_mm=r3(dlt)))

		def sm(rows):
			mg = [r["margin"] for r in rows if r["margin"] is not None]
			return dict(n=len(rows), top1=int(sum(r["top1"] for r in rows)), d_true=st([r["d_true"] for r in rows]),
						margin_median=r3(np.median(mg)) if mg else None, margin_lt_1_5=int(sum(m < 1.5 for m in mg)))
		out[var] = dict(pool28=sm(rows28), pool28_class_filter=sm(rows28c), pool68_class_filter=sm(rows68c),
						calibracao=cal if var != "sem" else None,
						calibracao_resumo=dict(scale=st([c["scale"] for c in cal]), iso_mm=st([c["iso_mm"] for c in cal])))
		o = out[var]
		log(f"[c1 LOO] {var}: pool28 top-1 {o['pool28']['top1']}/{o['pool28']['n']} margem<1,5 {o['pool28']['margin_lt_1_5']}; "
			f"pool28 classe top-1 {o['pool28_class_filter']['top1']} margem<1,5 {o['pool28_class_filter']['margin_lt_1_5']}; "
			f"pool68 classe top-1 {o['pool68_class_filter']['top1']} margem<1,5 {o['pool68_class_filter']['margin_lt_1_5']}; "
			f"gémeo mediana {o['pool68_class_filter']['d_true'].get('median')}")
	out["descricao"] = ("leave-one-out: escala e desvio isotrópico estimados nas outras 24 comparações (c1 via gémeo) e aplicados "
						"à célula UL retida; 'sem' reproduz (b)")
	return out


def c2_noise(F, R):
	ks = sorted(set(F) & set(R))
	v = [free_d(F[k], R[k]) for k in ks]
	vc = [corner_d(F[k], R[k]) for k in ks]
	return dict(n_front=len(F), n_rot180=len(R), n_both=len(ks), rms_free=st(v), rms_corner=st([x for x in vc if np.isfinite(x)]),
				class_agree=f"{sum(F[k].get('cls') == R[k].get('cls') for k in ks if F[k].get('ok') and R[k].get('ok'))}/"
							f"{sum(1 for k in ks if F[k].get('ok') and R[k].get('ok'))}"), v


def clean(o):
	if isinstance(o, dict):
		return {(kname(k) if isinstance(k, tuple) else str(k)): clean(v) for k, v in o.items()}
	if isinstance(o, (list, tuple)):
		return [clean(v) for v in o]
	if isinstance(o, np.floating):
		return float(o)
	if isinstance(o, np.integer):
		return int(o)
	if isinstance(o, np.bool_):
		return bool(o)
	return o


# ----------------------------------------------------------------------------- principal
def main():
	t0 = time.time()
	os.makedirs(WORK, exist_ok=True)
	R = dict(descricao="E-real (2026-10-31): células das linhas de corte (secções UL e BD) e soltas BD (segment_scan); "
			 "métrica free principal, corner de controlo. Ver docs/diagnostico/gemeos/EREAL.md.")
	J = json.load(open(os.path.join(OUT, "seccao_celulas.json"), encoding="utf-8"))
	pitch = (float(J["passo_mm"]["u"]), float(J["passo_mm"]["w"]))
	# --- extração
	dU = cells_of_scan(F_UL, None, pitch, name="UL frente_300")
	dF = cells_of_scan(F_FRENTE, cv2.ROTATE_90_CLOCKWISE, pitch, name="BD frente")
	dR = cells_of_scan(F_ROT180, cv2.ROTATE_90_COUNTERCLOCKWISE, pitch, name="BD rot180")
	for d in (dF, dR):
		occ = sorted((iu + 1, iw + 1) for iu, iw in d["occ"])
		if occ != BD_EXPECTED:
			raise SystemExit(f"[E-real] ocupação de {d['name']} não bate com a disposição esperada: a mais "
							 f"{sorted(set(occ) - set(BD_EXPECTED))}, em falta {sorted(set(BD_EXPECTED) - set(occ))}")
	log(f"[ext] ocupação BD verificada nos 2 scans: 41 casas = k 1-5 x j 1-7, k=6 j 1-5, k=7 j 1 (k = iu+1, j = iw+1)")
	R["extracao"] = {d["name"]: dict(res=d["res"], phi_deg=r3(d["phi_deg"]), fracs=d["fracs"], n_occupied=len(d["occ"]),
									 pitch_autocorr_hessiana_mm=[r3(v) for v in d["pitch_ac"]],
									 pitch_autocorr_branco_mm=[r3(v) for v in d["pitch_ac_branco"]]) for d in (dU, dF, dR)}
	R["passo_usado_mm"] = dict(u=r3(pitch[0]), w=r3(pitch[1]), fonte="seccao_celulas.json (secção UL, céu; confirmado por "
							   "centróides em SECCAO.md); o mesmo puzzle, por isso o mesmo passo no BD")
	lc = lambda iu, iw: (iu + 1, iw + 1)  # noqa: E731  UL: canto TL -> l = iu+1, c = iw+1 (seccao.lc_of k=1); BD: k = iu+1, j = iw+1
	# controlo: a re-extração do UL reproduz seccao_celulas.json
	ULraw = section_cells(dU, "hessiana/watershed", False, lc)
	js = {(c["l"], c["c"]): c for c in J["scans"]["frente_300"]["celulas"]}
	da = [abs(cv2.contourArea(ULraw[k]["contour_orig"].astype(np.float32).reshape(-1, 1, 2)) * PX_MM ** 2 - js[k]["area_mm2"])
		  for k in ULraw if k in js]
	R["controlo_UL_json"] = dict(n_reextraido=len(ULraw), n_json=len(js), mesmas_casas=sorted(ULraw) == sorted(js),
								 dif_area_mm2_max=r3(max(da)) if da else None)
	log(f"[ext] UL re-extraído: {len(ULraw)} células, casas iguais ao JSON: {sorted(ULraw) == sorted(js)}, "
		f"|Δárea| máx {max(da):.2f} mm2")
	UL = section_cells(dU, "hessiana/watershed", True, lc)
	BD = section_cells(dF, "branco/watershed", True, lc)
	BDraw = section_cells(dF, "branco/watershed", False, lc)
	BDr = section_cells(dR, "branco/watershed", True, lc)
	R["celulas"] = dict(UL=len(UL), BD_frente=len(BD), BD_rot180=len(BDr),
						BD_frente_4cantos=int(sum(p.get("ok", False) for p in BD.values())),
						UL_4cantos=int(sum(p.get("ok", False) for p in UL.values())),
						regrow_mm=REGROW_MM, nota="células usadas: UL hessiana/watershed (= seccao_celulas.json), BD branco/"
						"watershed; 'orla' = a faixa de 1 mm da silhueta devolvida às células (regrow_labels)")
	ref = qc_ref(UL)
	for name, S in (("UL", UL), ("BD_frente", BD), ("BD_rot180", BDr)):
		ok = [p for p in S.values() if p.get("ok")]
		R["celulas"][f"qc_{name}"] = dict(n=len(S), n_4cantos=len(ok), n_qc=int(sum(qc_ok(p, ref) for p in S.values())),
										  rugosidade=st([p["rough"] for p in ok]), area_mm2=st([cell_area(p) for p in S.values()]),
										  F_igual_esperado=int(sum(p["types"].count("F") == p["n_frame"] for p in ok)))
	R["celulas"]["qc_ref"] = dict(rough_p95_UL=r3(ref["rough_p95"]), area_median_UL=r3(ref["area_median"]))
	log(f"[qc] células: " + "; ".join(f"{n}: n={R['celulas'][f'qc_{n}']['n']} 4 cantos {R['celulas'][f'qc_{n}']['n_4cantos']} "
									  f"QC {R['celulas'][f'qc_{n}']['n_qc']} rugosidade mediana {R['celulas'][f'qc_{n}']['rugosidade'].get('median')}"
									  for n in ("UL", "BD_frente", "BD_rot180")))
	# --- (a) secção <-> secção
	Ra, (QKa, CKa, Da) = section_vs_section(UL, BD)
	BDq = {k: p for k, p in BD.items() if qc_ok(p, ref)}
	Ra_q = section_vs_section(UL, BDq)[0] if len(BDq) >= 2 else dict(n_BD=len(BDq))
	Ra_raw, _ = section_vs_section(ULraw, BDraw)
	R["a_seccao_seccao"] = dict(orla=Ra, crua=dict((k, Ra_raw[k]) for k in ("todas", "mutual_nn")),
								so_celulas_BD_com_qc=dict((k, Ra_q[k]) for k in ("todas", "n_BD", "n_UL") if k in Ra_q))
	s = Ra["todas"]["UL_to_BD"]
	log(f"[a] UL<->BD: n={s['n']}, gémeo mediana {s['d_true'].get('median')} p90 {s['d_true'].get('p90')}; não-gémeo NN "
		f"mediana {s['nn_nontrue'].get('median')}; top-1 UL->BD {s['top1']}/{s['n']}, BD->UL "
		f"{Ra['todas']['BD_to_UL']['top1']}/{Ra['todas']['BD_to_UL']['n']}; margem<1,5 {s['margin_lt_1_5']}; {Ra['mutual_nn']}")
	# --- soltas e pool do E-sym
	L, chk = loose_pieces()
	E = esym_pool()
	R["soltas"] = chk
	# --- (c1) célula da linha de corte vs silhueta da mesma peça
	rows = []
	for p in L:
		k = (p["k"], p["j"])
		if k not in BD:
			continue
		b = bias_pair(p, BD[k])
		b.update(k=p["k"], j=p["j"], sil=p, inside=(BD[k]["n_frame"], BD[k]["n_free"]) == (0, 0))
		rows.append(b)
	# (c1 via gémeo) a mesma análise com a célula UL gémea (boa: céu) em vez da célula BD própria (relva)
	rows_t = []
	for p in L:
		k = (p["k"], p["j"])
		if k not in UL:
			continue
		b = bias_pair(p, UL[k])
		b.update(k=p["k"], j=p["j"], sil=p, inside=(UL[k]["n_frame"], UL[k]["n_free"]) == (0, 0), qc=qc_ok(UL[k], ref))
		rows_t.append(b)
	rows_r = []
	for p in L:
		k = (p["k"], p["j"])
		if k in BDr:
			rows_r.append(bias_pair(p, BDr[k]))
	rows_raw = [bias_pair(p, BDraw[(p["k"], p["j"])]) for p in L if (p["k"], p["j"]) in BDraw]
	R["c1_celula_vs_silhueta"] = dict(
		todas=bias_summary(rows), dentro_do_bloco=bias_summary([r for r in rows if r["inside"]]),
		no_contorno_do_bloco=bias_summary([r for r in rows if not r["inside"]]),
		rot180=bias_summary(rows_r), crua_sem_orla=bias_summary(rows_raw), t95_esym=T95_ESYM,
		so_celulas_BD_com_qc=bias_summary([r for r in rows if qc_ok(BD[(r["k"], r["j"])], ref)]),
		via_gemeo_UL=bias_summary(rows_t), via_gemeo_UL_dentro_do_bloco=bias_summary([r for r in rows_t if r["inside"]]),
		via_gemeo_UL_qc=bias_summary([r for r in rows_t if r["qc"]]),
		per_piece_via_gemeo=[dict(k=r["k"], j=r["j"], rms_free=r3(r["rms_free"]), scale=r3(r["scale"]),
								  off={a: r3(v) for a, v in r["off"].items()}, asym_baixo_cima=r3(r["asym_y"]),
								  asym_esq_dir=r3(r["asym_x"]), inside=r["inside"], qc=r["qc"]) for r in rows_t],
		per_piece=[dict(k=r["k"], j=r["j"], rms_free=r3(r["rms_free"]), scale=r3(r["scale"]), off={a: r3(v) for a, v in r["off"].items()},
						asym_baixo_cima=r3(r["asym_y"]), asym_esq_dir=r3(r["asym_x"]), inside=r["inside"]) for r in rows])
	c1 = R["c1_celula_vs_silhueta"]["todas"]
	log(f"[c1] solta vs a própria célula BD: n={c1['n']}, free mediana {c1['rms_free'].get('median')} p90 {c1['rms_free'].get('p90')} "
		f"t95 {c1['t_p95_rms_free']} (E-sym {T95_ESYM}); escala mediana {c1['scale'].get('median')}; RMS após escala "
		f"{c1['rms_after_scale'].get('median')}; desvio por lado {dict((k, v.get('median')) for k, v in c1['offset_by_side'].items())}; "
		f"assimetria baixo-cima {c1['asym_baixo_menos_cima'].get('median')}, esq-dir {c1['asym_esq_menos_dir'].get('median')}")
	c1t = R["c1_celula_vs_silhueta"]["via_gemeo_UL"]
	log(f"[c1 via gémeo] solta vs célula UL gémea: n={c1t['n']}, free mediana {c1t['rms_free'].get('median')}; escala mediana "
		f"{c1t['scale'].get('median')}; desvio por lado {dict((k, v.get('median')) for k, v in c1t['offset_by_side'].items())}; "
		f"assimetria baixo-cima {c1t['asym_baixo_menos_cima'].get('median')}, esq-dir {c1t['asym_esq_menos_dir'].get('median')}; "
		f"ΔL por lado {dict((k, v.get('median')) for k, v in c1t['dL_signed_by_side'].items())}")
	# --- (b) secção UL <-> soltas (= E-real)
	Rb, (QKb, LKb, D28, CK68, D68) = section_vs_loose(UL, L, E, ref=ref)
	Rb_raw, _ = section_vs_loose(ULraw, L, E, " crua")
	ULnp = section_cells(dU, "hessiana/histerese", True, lc)
	Rb_np, _ = section_vs_loose(ULnp, L, E, " sem prior")
	# escala da modalidade célula -> silhueta: da comparação c1 via gémeo (as células BD próprias não servem, ver qc)
	lam = float(np.median([r["scale"] for r in rows_t])) if rows_t else 1.0
	ULs = {k: dict(p, z=p["z"] * lam) for k, p in UL.items()}
	Rb_s, _ = section_vs_loose(ULs, L, E, f" escala x{lam:.3f}")
	R["b_seccao_soltas"] = dict(orla=Rb, crua=Rb_raw, sem_prior_histerese=dict(n_cells=len(ULnp), **Rb_np),
								escala_c1=dict(scale=r3(lam), **{k: Rb_s[k] for k in ("n_queries", "pool28", "pool68",
										"pool28_class_filter", "pool68_class_filter", "reverse_loose_to_UL")}))
	R["c1_loo"] = c1_loo(UL, L, E, rows_t)
	# --- (c2) ruído das linhas de corte com mudança de pose (frente vs rot180)
	c2 = {}
	vals_c2 = []
	for key in KEYS:
		F_ = section_cells(dF, key, False, lc)
		R_ = section_cells(dR, key, False, lc)
		c2[key], v = c2_noise(F_, R_)
		if key == "branco/watershed":
			vals_c2 = v
	c2["branco/watershed+orla"], vals_c2o = c2_noise(BD, BDr)
	R["c2_frente_vs_rot180"] = c2
	log(f"[c2] frente vs rot180: " + "; ".join(f"{k}: n={v['n_both']} med {v['rms_free'].get('median')} p90 {v['rms_free'].get('p90')}"
											  for k, v in c2.items()))
	# --- veredicto M10 e decisão da sombra
	b28, b68 = Rb["pool28_class_filter"], Rb["pool68_class_filter"]
	top1 = min(b28["top1_frac"], b68["top1_frac"])
	verdict = ("passa" if top1 >= 0.95 and b68["margin_lt_1_5"] == 0 else "mata" if top1 < 0.80 else "inconclusivo")
	asy = [c1t["asym_baixo_menos_cima"].get("median"), c1t["asym_esq_menos_dir"].get("median")]
	sh = max(abs(v) for v in asy if v is not None) if any(v is not None for v in asy) else None
	shadow_back = bool((sh is not None and sh > 0.2) or (b68["margin_median"] or 0) < 1.5)
	R["veredicto"] = dict(criterio_M10="top-1 >= 95 % das testáveis e margem >= 1,5 -> passa; top-1 < 80 % -> mata",
						  top1_pool28_classe=b28["top1_frac"], top1_pool68_classe=b68["top1_frac"],
						  top1_pool68_sem_classe=Rb["pool68"]["top1_frac"], margem_lt_1_5_pool68=b68["margin_lt_1_5"],
						  margem_min_pool68=b68["margin_min"], resultado=verdict,
						  sombra=dict(regra="viés sistemático da sombra > ~0,2 mm em (c1), ou margem de (b) < 1,5 -> o modelo de "
									  "sombra do M3 volta à agenda; senão continua adiado",
									  assimetria_mediana_mm=dict(baixo_menos_cima=asy[0], esq_menos_dir=asy[1]),
									  fonte="c1 via gémeo UL (as células BD próprias não passam o controlo de qualidade)",
									  margem_mediana_b_pool68_classe=b68["margin_median"],
									  volta_a_agenda=shadow_back))
	log(f"[veredicto] M10 / E-real: {verdict} (top-1 pool28 c/ classe {b28['top1_frac']}, pool68 c/ classe {b68['top1_frac']}, "
		f"margem<1,5 no pool68 {b68['margin_lt_1_5']}); sombra volta à agenda: {shadow_back} (assimetria {asy})")
	# --- figuras
	fig_lines(dF, "ereal_bd_linhas_frente.jpg", ["E-real: bloco BD, frente (orientacao do ficheiro). Linha 1: hessiana de L* (seccao.py); "
				"linha 2: branco (crista de L*-1,5C*, minha)", "colunas: resposta | sem prior (histerese) | com prior (watershed); "
				"rotulos k,j nas celulas recuperadas"])
	fig_lines(dR, "ereal_bd_linhas_rot180.jpg", ["E-real: bloco BD, re-scan rodado 180 graus (orientacao do ficheiro). Linha 1: "
				"hessiana de L* (seccao.py); linha 2: branco (minha)", "colunas: resposta | sem prior (histerese) | com prior "
				"(watershed); rotulos k,j"])
	fig_soltas(L, "ereal_soltas__contours.jpg")
	Lp = {(p["k"], p["j"]): p for p in L}
	pq = {tuple(r["UL"]): r for r in Rb["per_query"]}
	fig_pairs([(UL[k], Lp[k], [f"UL{k} <-> solta BD{k}", f"free {free_d(UL[k], Lp[k]):.2f}  rank28 {pq[k]['rank28']} rank68 {pq[k]['rank68']}",
							   f"{UL[k].get('cls', '?')} / {Lp[k].get('cls')}  marg {pq[k]['margin28']}"]) for k in sorted(pq)],
			  "ereal_pares_seccao_solta.png", ["E-real (b): celula UL das linhas de corte (vermelho) vs gemea solta BD, segment_scan "
											  "(azul), alinhadas pela metrica free", "rank = n. de candidatos mais proximos do que o "
											  "gemeo (0 = top-1); pool28 = soltas, pool68 = + 40 pecas do E-sym; classes UL / solta"])
	ka = sorted(set(UL) & set(BD))
	fig_pairs([(UL[k], BD[k], [f"UL{k} <-> BD{k}", f"free {free_d(UL[k], BD[k]):.2f} mm",
							   f"{UL[k].get('cls', '?')} / {BD[k].get('cls', '?')}"]) for k in ka],
			  "ereal_pares_seccao_seccao.png", ["E-real (a): celula UL (vermelho) vs celula gemea BD (azul), ambas das linhas de "
											   "corte (UL hessiana/watershed, BD branco/watershed, com orla)", "alinhadas pela metrica free"], cols=7)
	fig_bias(rows_t, "ereal_vies_silhueta.png", ["E-real (c1 via gemeo): solta (segment_scan, vermelho) vs a celula UL gemea das "
											  "linhas de corte (azul, alinhada sem escala), referencial do scanner das soltas",
											  "preto grosso = lados da silhueta virados para baixo/esquerda (lado da sombra); desvio "
											  "medio por lado em mm (+ = silhueta fora da celula); escala = silhueta/celula"])
	fig_bias(rows, "ereal_vies_silhueta_propria.png", ["E-real (c1): solta (segment_scan, vermelho) vs a sua propria celula BD das linhas de "
											  "corte (azul, alinhada sem escala), referencial do scanner das soltas",
											  "preto grosso = lados da silhueta virados para baixo/esquerda (lado da sombra); desvio "
											  "medio por lado em mm (+ = silhueta fora da celula); escala = silhueta/celula"])
	twin_a = [r["d_true"] for r in queries(QKa, CKa, Da, {k: k for k in QKa})[0]]
	nn_a = [r["nn"] for r in queries(QKa, CKa, Da, {k: k for k in QKa})[0]]
	allnt_a = [Da[i, j] for i, q in enumerate(QKa) for j, c in enumerate(CKa) if q != c]
	rb = queries(QKb, LKb, D28, {k: k for k in QKb if k in Lp})[0]
	allnt_b = [D28[i, j] for i, q in enumerate(QKb) for j, c in enumerate(LKb) if q != c]
	es.fig_hist([("free, (a) seccao<->seccao", [("gemeo UL/BD (celulas)", np.array(twin_a), RED),
												  ("nao-gemeo mais proximo", np.array(nn_a), GRN),
												  ("todos os nao-gemeos", np.array(allnt_a), GREY)]),
				 ("free, (b) seccao<->soltas", [("gemeo UL celula / solta", np.array([r["d_true"] for r in rb]), RED),
												  ("nao-gemeo mais proximo (28)", np.array([r["nn"] for r in rb]), GRN),
												  ("todos os nao-gemeos", np.array(allnt_b), GREY)]),
				 ("free, (c) mesma peca", [("(c1) solta vs a sua celula BD", np.array([r["rms_free"] for r in rows]), (160, 0, 160)),
										   ("(c1 via gemeo) solta vs celula UL gemea", np.array([r["rms_free"] for r in rows_t]), RED),
										   ("(c2) celula BD frente vs rot180", np.array(vals_c2o), (0, 140, 255))])],
				"ereal_histogramas.png", "E-real: RMS free (mm) gemeo vs nao-gemeo vs ruido; n por serie na legenda")
	fig_matrix([("(a) UL (linhas) x BD (colunas), free", Da, [kname(k) for k in QKa], [kname(k) for k in CKa],
				 {i: CKa.index(k) for i, k in enumerate(QKa) if k in CKa}),
				("(b) UL (linhas) x soltas (colunas), free", D28, [kname(k) for k in QKb], [kname(k) for k in LKb],
				 {i: LKb.index(k) for i, k in enumerate(QKb) if k in LKb}),
				("(c1) soltas x celulas BD, free", dmat(L, [BD[k] for k in sorted(BD)]), [kname((p["k"], p["j"])) for p in L],
				 [kname(k) for k in sorted(BD)], {i: sorted(BD).index((p["k"], p["j"])) for i, p in enumerate(L) if (p["k"], p["j"]) in BD})],
			   "ereal_matriz.png")
	# --- GT legível por máquina
	jsk = set(js)
	gt = dict(descricao="GT do canto BD (31-out-2026). (k, j) local: k = linha a contar de baixo, j = coluna a contar da "
			  "direita; (l, c) = (48 - k, 65 - j); gémeo de BD(k, j) = célula global (k, j) do canto UL. Disposição das soltas "
			  "verificada pela imagem e por verificações automáticas em ereal.py (bloco rodado 90° anti-horário: fila r -> j = r+1, "
			  "coluna s a contar da direita -> k = s+1). Contornos em px do ficheiro indicado, ≈ 600 pontos.",
			  ficheiros=dict(frente="images/pieces/gt_canto_BD_frente_300dpi.jpg", rot180="images/pieces/gt_canto_BD_frente_300dpi_rot180.jpg",
							 soltas="images/pieces/gt_canto_BD_soltas_300dpi.jpg", seccao_UL="docs/diagnostico/gemeos/seccao_celulas.json"),
			  soltas=[dict(indice_segment_scan=p["index"], fila_r=p["r"], coluna_s_da_direita=p["s"], k=p["k"], j=p["j"],
						   l=48 - p["k"], c=65 - p["j"], gemeo_UL=[p["k"], p["j"]], gemeo_em_seccao_celulas=(p["k"], p["j"]) in jsk,
						   classe=p["cls"], bbox=p["bbox"]) for p in L],
			  celulas_BD=[])
	for k, j in BD_EXPECTED:
		e = dict(k=k, j=j, l=48 - k, c=65 - j, gemeo_UL=[k, j], gemeo_em_seccao_celulas=(k, j) in jsk, solta=2 <= k and 2 <= j,
				 recuperada={f"{d['name']}:{key}": (k - 1, j - 1) in d["per"][key]["rec"] for d in (dF, dR) for key in KEYS})
		if (k, j) in BD:
			cc = BD[(k, j)]["contour_orig"]
			e["contorno_px_frente_branco_watershed_orla"] = cc[::max(1, len(cc) // 600)].round().astype(int).tolist()
		gt["celulas_BD"].append(e)
	with open(os.path.join(OUT, "ereal_gt.json"), "w", encoding="utf-8") as f:
		json.dump(clean(gt), f, ensure_ascii=False)
	R["segundos"] = r3(time.time() - t0)
	R["log"] = LOG
	jp = os.path.join(OUT, "results.json")
	Jr = json.load(open(jp, encoding="utf-8"))
	Jr["ereal"] = clean(R)
	json.dump(Jr, open(jp, "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=lambda o: o.item() if hasattr(o, "item") else str(o))
	log(f"total {time.time() - t0:.0f} s")


if __name__ == "__main__":
	main()
