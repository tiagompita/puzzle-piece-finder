"""E-real-2: a cadeia real solta -> solta com desempate pela imagem (protótipo do find_twin do M10).

Diagnóstico (não é código de produção). Correr a partir da raiz do repositório:

	PowerShell:  $env:PPF_SCRATCH = "C:\\caminho\\scratchpad"; $env:PYTHONIOENCODING = "utf-8"
	python tools/diagnostico/gemeos/ereal2.py [--force]

--force refaz a memória (segment_scan em todas as folhas); por omissão usa $PPF_SCRATCH/ereal2/memoria.pkl.
Precisa de $PPF_SCRATCH/gemeos/esym.pkl (esym.py).

Memória de 188 soltas, todas por src.segmentation.segment_scan:
  BE    images/pieces/gt_canto_BE_soltas_300dpi.jpg                 20 interiores do canto BE, GT (k, j) pela grelha
  céu   images/pieces/ereal2_ceu_{f1p1,f1p2,f2p1,f2p2}_300dpi.jpg   100 peças de céu SEM GT (o Tiago confirma)
  BD    ereal.loose_pieces()                                        28 interiores do canto BD (gémeas = células UL, fora)
  E-sym ereal.esym_pool()                                           40 peças de borda A1 / B2, 20 pares gémeos no pool
Coordenadas BE (images/pieces/gt_canto_BE.md): k = linha a contar de baixo, j = coluna a contar da esquerda;
(l, c) = (48 - k, j); gémea de BE(k, j) = célula global (k, 65 - j). A simetria está isolada em twin_cell().

Consulta (regras 1-4 = forma; 5 = imagem):
  1 classe topológica (analyse_v2 cls) igual; 2 cordas dos lados homólogos (best_k de shape_dist) |ΔL| <= 1 mm;
  3 RMS free (dist.free_dist) -> d1, d2, margem d2/d1; 4 ACEITE se d1 <= t95 e margem >= 1,5, AMBÍGUA se d1 <= tmax,
  senão SEM (t95 0,507 / tmax 0,637 mm: E-sym, results.json -> esym.extrapolation.hibrido.free);
  5 imagem 1-contra-1: recorte Lab da candidata (L* - 4,8), rodado para a orientação prevista pela forma, à escala da
  arte limpa (images/puzzles/1186441_1.jpg, arte nas linhas 42-1156), contra a célula gémea: ΔE médio mascarado.
Saídas em docs/diagnostico/gemeos/: ereal2_*.jpg/png/txt/json, results.json (só a chave "ereal2"). Ver EREAL2.md.
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
import esym as es  # noqa: E402
import ereal as er  # noqa: E402  (main() só corre como script)
from shapelib import MM, shape_dist  # noqa: E402
from dist import free_dist, aligned_b  # noqa: E402

sx = er.sx
REPO, OUT = sc.REPO, sc.OUT
PIECES = os.path.join(REPO, "images", "pieces")
WORK = os.path.join(sc.S, "ereal2")
F_BE = os.path.join(PIECES, "gt_canto_BE_soltas_300dpi.jpg")
SHEETS = ("f1p1", "f1p2", "f2p1", "f2p2")
F_CEU = {s: os.path.join(PIECES, f"ereal2_ceu_{s}_300dpi.jpg") for s in SHEETS}
CEU_EXPECTED = {"f1p1": 35, "f1p2": 15, "f2p1": 42, "f2p2": 8}
F_ART = os.path.join(REPO, "images", "puzzles", "1186441_1.jpg")

AREA_MM2 = (250.0, 650.0)   # peça isolada plausível (célula ≈ 349 mm²; silhuetas 340-480)
ADJ_MM = 1.5                # BE: peça a < 1,5 mm de outra = fragmento da faixa em L montada (soltas ficam >= 5 mm)
DL_MAX = 1.0                # regra 2: |ΔL| máximo por lado homólogo (mm)
MARGIN_MIN = 1.5            # regra 4: margem d2/d1
L_SHIFT = 4.8               # L*scan ≈ L*arte + 4,8 (SECCAO.md §C): subtrai-se ao scan
NROW, NCOL = 47, 64         # grelha do puzzle (perfil do puzzle, M13)
ART_Y0, ART_W, ART_H = 42, 1600, 1115   # a arte ocupa as linhas 42-1156 do ficheiro (SECCAO.md)
CELL_W, CELL_H = ART_W / NCOL, ART_H / NROW
CANVAS = (43, 41)           # (W, H) do recorte à escala da arte: célula + ≈ 0,35 célula de orla (abas)
JIT = 2                     # jitter ±2 px da arte na comparação com a célula
ERODE_PX = 1                # máscara do recorte erodida 1 px da arte (≈ 0,76 mm): tira a orla de sombra/fundo do contorno
PAD = 48                    # orla NaN à volta da arte
LOG = []


def log(*a):
	s = " ".join(str(x) for x in a)
	LOG.append(s)
	print(s, flush=True)


r3 = er.r3
st = er.st


def fin(v):
	"""Número finito arredondado ou None (JSON)."""
	return None if v is None or not np.isfinite(v) else r3(v)


def twin_cell(l, c):
	"""Célula gémea por rotação de 180° da peça (l, c) (1-based). Perfil do puzzle (M13): aqui fixa para o
	Clementoni 3000 64 x 47, (48 - l, 65 - c). Aceita escalares ou arrays."""
	return NROW + 1 - l, NCOL + 1 - c


def thresholds():
	"""t95 / tmax do RMS free dos gémeos no E-sym (híbrido; a modalidade silhueta<->silhueta é a mesma aqui)."""
	try:
		J = json.load(open(os.path.join(OUT, "results.json"), encoding="utf-8"))
		f = J["esym"]["extrapolation"]["hibrido"]["free"]
		return float(f["t_p95"]), float(f["t_max"])
	except Exception:   # noqa: BLE001
		return 0.507, 0.637


T95, TMAX = thresholds()


def pitch_mm():
	"""Passo medido da grelha montada (seccao_celulas.json): (horizontal, vertical) do puzzle em mm (w, u)."""
	J = json.load(open(os.path.join(OUT, "seccao_celulas.json"), encoding="utf-8"))
	return float(J["passo_mm"]["w"]), float(J["passo_mm"]["u"])


PITCH_X, PITCH_Y = pitch_mm()


# ----------------------------------------------------------------------------- memória (segmentação)
def seg_sheet(path):
	"""segment_scan numa folha -> (registos, forma da imagem)."""
	from PIL import Image
	from src.segmentation import segment_scan
	with Image.open(path) as im:
		im.load()
		shp = (im.size[1], im.size[0])
		r = segment_scan(im)
	if "error" in r:
		raise SystemExit(f"[E-real-2] segment_scan falhou em {path}: {r['error']}")
	out = []
	for p in r["pieces"]:
		c = np.asarray(p["contour"]).reshape(-1, 2).astype(float)
		out.append(dict(index=int(p["index"]), contour=c, bbox=[int(v) for v in p["bbox"]], is_cluster=bool(p["is_cluster"]),
						touches_frame=bool(p.get("touches_frame")),
						area_mm2=float(cv2.contourArea(c.astype(np.float32).reshape(-1, 1, 2))) * MM ** 2))
	return out, shp


def gaps_mm(raw, shp, f=0.5):
	"""Distância (mm) de cada peça à peça mais próxima (máscaras a meia resolução)."""
	H, W = int(shp[0] * f), int(shp[1] * f)
	lab = np.zeros((H, W), np.int32)
	for q, p in enumerate(raw):
		cv2.fillPoly(lab, [np.round(p["contour"] * f).astype(np.int32).reshape(-1, 1, 2)], q + 1)
	out = []
	for q, p in enumerate(raw):
		other = (lab > 0) & (lab != q + 1)
		if not other.any():
			out.append(float("inf"))
			continue
		dt = cv2.distanceTransform((~other).astype(np.uint8), cv2.DIST_L2, 5)
		pts = np.clip(np.round(p["contour"] * f).astype(int), 0, [W - 1, H - 1])
		out.append(float(dt[pts[:, 1], pts[:, 0]].min()) / f * MM)
	return out


def lmed(rgb, contour):
	"""L* mediano (Lab float) dentro do contorno."""
	x, y, w, h = cv2.boundingRect(np.round(contour).astype(np.int32).reshape(-1, 1, 2))
	m = np.zeros((h, w), np.uint8)
	cv2.fillPoly(m, [np.round(contour - [x, y]).astype(np.int32).reshape(-1, 1, 2)], 1)
	L = sx.lab_f(np.ascontiguousarray(rgb[y:y + h, x:x + w]))[..., 0]
	return float(np.median(L[m > 0]))


def rows_by_y(cy, hmed, from_bottom=False):
	"""Filas por quebras no y do centro maiores que 0,5 x altura mediana (de cima, ou de baixo)."""
	o = np.argsort(-cy if from_bottom else cy)
	rows, cur = [], [o[0]]
	for i in o[1:]:
		if abs(cy[i] - cy[cur[-1]]) > 0.5 * hmed:
			rows.append(cur)
			cur = [i]
		else:
			cur.append(i)
	rows.append(cur)
	return rows


BE_EXPECTED = sorted([(k, j) for k in (2, 3) for j in range(2, 8)] + [(k, j) for k in (4, 5) for j in range(2, 6)])


def be_pieces():
	"""BE: segment_scan, exclusões, grelha (filas de BAIXO para cima -> j = r + 1; colunas da DIREITA -> k = s + 1),
	verificações automáticas (aborta se falharem)."""
	t0 = time.time()
	raw, shp = seg_sheet(F_BE)
	gaps = gaps_mm(raw, shp)
	keep, excl = [], []
	for p, g in zip(raw, gaps):
		why = []
		if p["is_cluster"]:
			why.append("cluster")
		if p["touches_frame"]:
			why.append("touches_frame")
		if not AREA_MM2[0] <= p["area_mm2"] <= AREA_MM2[1]:
			why.append(f"área {p['area_mm2']:.0f} mm²")
		if g < ADJ_MM:
			why.append(f"a {g:.1f} mm de outra peça (faixa em L montada)")
		if not why:
			q = er.mkpiece(p["contour"])
			if not q.get("ok"):
				why.append("sem 4 cantos (fragmento da faixa em L)")
		if why:
			excl.append(dict(index=p["index"], razao="; ".join(why), area_mm2=r3(p["area_mm2"]), bbox=p["bbox"]))
		else:
			keep.append(dict(p, gap_mm=g))
	log(f"[BE] segment_scan: {len(raw)} objetos, {len(keep)} peças isoladas, excluídos {len(excl)}: "
		+ "; ".join(f"#{e['index']} {e['razao']}" for e in excl) + f" ({time.time() - t0:.1f} s)")
	if len(keep) != 20:
		raise SystemExit(f"[E-real-2] BE: esperava 20 peças (não cluster, longe do bordo, 250-650 mm², isoladas, 4 cantos), "
						 f"obtive {len(keep)}")
	b = np.array([p["bbox"] for p in keep], float)
	cx, cy = b[:, 0] + b[:, 2] / 2, b[:, 1] + b[:, 3] / 2
	rows = rows_by_y(cy, np.median(b[:, 3]), from_bottom=True)   # r = 1 em baixo
	counts = [len(rw) for rw in rows]
	if counts != [4, 4, 4, 4, 2, 2]:
		raise SystemExit(f"[E-real-2] BE: filas de baixo para cima {counts}; esperava [4, 4, 4, 4, 2, 2]")
	col_x = {}
	for rw in rows[:4]:
		for s, i in enumerate(sorted(rw, key=lambda q: -cx[q]), 1):
			col_x.setdefault(s, []).append(cx[i])
	col_x = {s: float(np.median(v)) for s, v in col_x.items()}
	rgb = sx.read_rgb(F_BE)
	out = []
	for r_, rw in enumerate(rows, 1):
		for s, i in enumerate(sorted(rw, key=lambda q: -cx[q]), 1):
			near = min(col_x, key=lambda q: abs(col_x[q] - cx[i]))
			if near != s:
				raise SystemExit(f"[E-real-2] BE fila {r_}: peça {keep[i]['index']} (x {cx[i]:.0f}) mais perto da coluna "
								 f"s={near} do que da s={s}; colunas {col_x}")
			k, j = s + 1, r_ + 1
			p = er.mkpiece(keep[i]["contour"], index=keep[i]["index"], r=r_, s=s, k=k, j=j, bbox=keep[i]["bbox"],
						   cx=float(cx[i]), cy=float(cy[i]), area_mm2=keep[i]["area_mm2"], gap_mm=keep[i]["gap_mm"])
			p["L_med"] = lmed(rgb, p["contour"])
			out.append(p)
	kj = sorted((p["k"], p["j"]) for p in out)
	if kj != BE_EXPECTED:
		raise SystemExit(f"[E-real-2] BE: casas {kj} != esperadas {BE_EXPECTED}")
	bad = [(p["k"], p["j"], "".join(p.get("types", "?"))) for p in out if not p.get("ok") or "F" in p["types"]]
	if bad:
		raise SystemExit(f"[E-real-2] BE: peças sem 4 cantos ou com lado F (deviam ser interiores): {bad}")
	colL = {k: float(np.median([p["L_med"] for p in out if p["k"] == k])) for k in (2, 3, 4, 5)}
	if min(colL, key=colL.get) != 5:
		raise SystemExit(f"[E-real-2] BE: a coluna k=5 (banda escura) devia ter o L* mediano mais baixo: {colL}")
	ncol = [sum(1 for p in out if p["s"] == s) for s in (1, 2, 3, 4)]
	log(f"[BE] grelha verificada: filas (de baixo) {counts}, colunas (da direita) {ncol}, x das colunas "
		f"{dict((s, round(v)) for s, v in col_x.items())}; 20 com 4 cantos e sem F; L* mediano por coluna "
		f"{dict((k, round(v, 1)) for k, v in colL.items())} (k=5 o mais baixo); áreas {min(p['area_mm2'] for p in out):.0f}-"
		f"{max(p['area_mm2'] for p in out):.0f} mm²; menor distância entre peças {min(p['gap_mm'] for p in out):.1f} mm")
	chk = dict(n_segment_scan=len(raw), excluidos=excl, filas_de_baixo=counts, colunas_da_direita=ncol,
			   col_x={str(s): r3(v) for s, v in col_x.items()}, L_med_por_coluna_k={str(k): r3(v) for k, v in colL.items()},
			   area_mm2=st([p["area_mm2"] for p in out]), menor_distancia_mm=r3(min(p["gap_mm"] for p in out)),
			   todas_4_cantos_sem_F=True)
	for p in out:
		p.update(src="BE", lab=f"BE({p['k']},{p['j']})", img=F_BE, cell=(48 - p["k"], p["j"]))
	return sorted(out, key=lambda p: (p["k"], p["j"])), chk


def ceu_pieces(sheet):
	"""Céu: segment_scan, exclusões registadas, numeração 1-based por segcache.grid_order (filas por y, x na fila).
	Numeram-se todas as peças físicas plausíveis (área/cluster/bordo ok), mesmo as sem 4 cantos (ficam fora da memória)."""
	t0 = time.time()
	raw, shp = seg_sheet(F_CEU[sheet])
	gaps = gaps_mm(raw, shp)
	cand, excl = [], []
	for p, g in zip(raw, gaps):
		why = []
		if p["is_cluster"]:
			why.append("cluster")
		if p["touches_frame"]:
			why.append("touches_frame")
		if not AREA_MM2[0] <= p["area_mm2"] <= AREA_MM2[1]:
			why.append(f"área {p['area_mm2']:.0f} mm²")
		if why:
			excl.append(dict(index=p["index"], razao="; ".join(why), area_mm2=r3(p["area_mm2"]), bbox=p["bbox"], contour=p["contour"]))
		else:
			cand.append(dict(p, gap_mm=g))
	out = []
	if cand:
		for n, (f, k, i) in enumerate(sc.grid_order([p["bbox"] for p in cand]), 1):
			q = cand[i]
			p = er.mkpiece(q["contour"], index=q["index"], bbox=q["bbox"], area_mm2=q["area_mm2"], gap_mm=q["gap_mm"],
						   sheet=sheet, num=n, fila=f + 1)
			b = q["bbox"]
			p.update(src="ceu", lab=f"{sheet} #{n}", img=F_CEU[sheet], cell=None, cx=b[0] + b[2] / 2, cy=b[1] + b[3] / 2)
			out.append(p)
	for p in out:
		if not p.get("ok"):
			excl.append(dict(index=p["index"], razao=f"sem 4 cantos (numerada {p['lab']})", area_mm2=r3(p["area_mm2"]),
							 bbox=p["bbox"], contour=p["contour"], num=p["num"]))
	ok = [p for p in out if p.get("ok")]
	n_exp = CEU_EXPECTED[sheet]
	log(f"[céu {sheet}] segment_scan {len(raw)} objetos; peças numeradas {len(out)} (esperadas {n_exp}"
		f"{'' if len(out) == n_exp else ' -> NÃO BATE'}); na memória {len(ok)}; excluídos: "
		+ ("; ".join(f"#{e['index']} {e['razao']} bbox {e['bbox']}" for e in excl) or "nenhum")
		+ f"; menor distância entre peças {min([p['gap_mm'] for p in out] or [float('nan')]):.1f} mm ({time.time() - t0:.1f} s)")
	return out, dict(n_segment_scan=len(raw), numeradas=len(out), esperadas=n_exp, na_memoria=len(ok),
					 excluidos=[{k: v for k, v in e.items() if k != "contour"} for e in excl]), excl


def build_memory(force):
	pk = os.path.join(WORK, "memoria.pkl")
	if os.path.exists(pk) and not force:
		with open(pk, "rb") as f:
			D = pickle.load(f)
		log(f"[memória] cache {pk} (usar --force para refazer)")
		for line in D.get("log", []):
			log("  (cache) " + line)
		return D
	n0 = len(LOG)
	BE, chk_be = be_pieces()
	CEU, chk_ceu, excl_ceu = [], {}, {}
	for s in SHEETS:
		P, chk, ex = ceu_pieces(s)
		CEU += P
		chk_ceu[s] = chk
		excl_ceu[s] = ex
	L, chk_bd = er.loose_pieces()
	for line in er.LOG:
		log("  (ereal) " + line)
	er.LOG.clear()
	for p in L:
		p.update(src="BD", lab=f"BD({p['k']},{p['j']})", img=er.F_SOLTAS, cell=(48 - p["k"], 65 - p["j"]))
	E = er.esym_pool()
	for p in E:
		name, i = p["key"]
		cA = es.col_A(i) if name == "A1" else es.col_A(es.twin(i))
		p.update(src="ES", lab=f"{name}({i // 5},{i % 5})", img=os.path.join(REPO, sc.SCANS[name]),
				 cell=(1, cA) if name == "A1" else (NROW, NCOL + 1 - cA), esym_i=i, esym_name=name)
	D = dict(BE=sorted(BE, key=lambda p: (p["k"], p["j"])), CEU=CEU, BD=sorted(L, key=lambda p: (p["k"], p["j"])), ES=E,
			 chk=dict(BE=chk_be, ceu=chk_ceu, BD=chk_bd), excl_ceu=excl_ceu, log=LOG[n0:])
	os.makedirs(WORK, exist_ok=True)
	with open(pk, "wb") as f:
		pickle.dump(D, f)
	return D


# ----------------------------------------------------------------------------- forma (puras)
def shape_matrices(M):
	"""D[i, j] = RMS free (mm) e PHI[i, j] = rotação (rad) que alinha M[j] a M[i] (= dist.free_dist(M[i], M[j]),
	vectorizado; verificado contra free_dist em main)."""
	Z = np.array([p["z"] for p in M])
	F = np.fft.fft(Z, axis=1)
	E = np.sum(np.abs(Z) ** 2, 1)
	N, n = Z.shape
	D = np.zeros((N, N))
	PHI = np.zeros((N, N))
	ar = np.arange(N)
	for i in range(N):
		corr = np.fft.ifft(np.conj(F[i])[None, :] * F, axis=1)
		m = np.abs(corr)
		s = m.argmax(1)
		D[i] = np.sqrt(np.maximum(E[i] + E - 2 * m[ar, s], 0) / n) * MM
		PHI[i] = -np.angle(corr[ar, s])
	np.fill_diagonal(D, np.inf)
	return D, PHI


def chord_matrix(M):
	"""DL[i, j] = máx |ΔL| (mm) dos 4 lados homólogos (best_k de shape_dist), só para a mesma classe; inf noutros casos."""
	N = len(M)
	DL = np.full((N, N), np.inf)
	for i in range(N):
		for j in range(i + 1, N):
			a, b = M[i], M[j]
			if not (a.get("ok") and b.get("ok")) or a["cls"] != b["cls"]:
				continue
			_, k, _ = shape_dist(a, b)
			DL[i, j] = DL[j, i] = max(abs(a["lens"][s] - b["lens"][(s + k) % 4]) for s in range(4))
	return DL


def decide(d1, margin):
	if d1 is None or not np.isfinite(d1) or d1 > TMAX:
		return "SEM"
	if d1 <= T95 and margin >= MARGIN_MIN:
		return "ACEITE"
	return "AMBÍGUA"


def query(i, D, PASS):
	"""Consulta da peça i contra as outras: candidatos que passam 1-2 ordenados pela RMS free; decisão 4."""
	js = sorted([j for j in range(len(D)) if j != i and PASS[i, j]], key=lambda j: D[i, j])
	d1 = D[i, js[0]] if js else None
	d2 = D[i, js[1]] if len(js) > 1 else None
	margin = (d2 / d1 if d2 is not None else float("inf")) if d1 is not None else None
	return dict(i=i, top=js[:3], n_pass=len(js), d1=d1, d2=d2, margin=margin, dec=decide(d1, margin))


# ----------------------------------------------------------------------------- orientação (puras)
def body_center(p):
	return p["c"][p["corners"]].mean(0)


def body_beta(p):
	"""Rotação (graus, convenção complexa z = x + iy com y para baixo: + = horário à vista) que põe os lados do corpo
	(polígono dos 4 cantos) alinhados com os eixos, em (-45, 45]."""
	P = p["c"][p["corners"]]
	v = np.roll(P, -1, 0) - P
	a = np.angle(np.sum(np.exp(4j * np.arctan2(v[:, 1], v[:, 0])))) / 4
	return float(-np.degrees(a))


def wrap(a):
	return (a + 180.0) % 360.0 - 180.0


def snap(p, theta):
	"""Rotação prevista theta (graus) -> m em 0..3 tal que beta + 90 m é a rotação alinhada mais próxima; resíduo."""
	b = body_beta(p)
	m = int(np.round((theta - b) / 90.0)) % 4
	return m, float(wrap(theta - (b + 90 * m)))


def f_normal(p):
	"""Ângulo (graus) da normal exterior do 1.º lado F (do centro do corpo ao meio da corda), no referencial do scan."""
	cb = body_center(p)
	for s, t in zip(p["sides"], p["types"]):
		if t == "F":
			v = 0.5 * (s[0] + s[-1]) - cb
			return float(np.degrees(np.arctan2(v[1], v[0])))
	return None


# ----------------------------------------------------------------------------- imagem
class Imgs:
	def __init__(self):
		self.c = {}

	def __call__(self, path):
		if path not in self.c:
			self.c[path] = sx.read_rgb(path)
		return self.c[path]


def load_art():
	rgb = sx.read_rgb(F_ART)
	if rgb.shape[:2] != (1200, 1600):
		raise SystemExit(f"[E-real-2] arte limpa com tamanho inesperado {rgb.shape}")
	art = np.ascontiguousarray(rgb[ART_Y0:ART_Y0 + ART_H, :ART_W])
	lab = sx.lab_f(art).astype(np.float64)
	H, W = lab.shape[:2]
	labp = np.full((H + 2 * PAD, W + 2 * PAD, 3), np.nan)
	labp[PAD:PAD + H, PAD:PAD + W] = lab
	rgbp = np.full((H + 2 * PAD, W + 2 * PAD, 3), 255, np.uint8)
	rgbp[PAD:PAD + H, PAD:PAD + W] = art
	V = (~np.isnan(labp[..., 0])).astype(np.float64)
	A0 = np.nan_to_num(labp)
	return dict(rgb=art, labp=labp, rgbp=rgbp, V=V, AV=[A0[..., ch] * V for ch in range(3)], A2V=(A0 ** 2).sum(-1) * V)


def cell_tl(l, c):
	"""Canto superior esquerdo (px da arte com orla PAD) da janela CANVAS centrada na célula (l, c)."""
	W, H = CANVAS
	return (np.round((np.asarray(c) - 0.5) * CELL_W - W / 2).astype(int) + PAD,
			np.round((np.asarray(l) - 0.5) * CELL_H - H / 2).astype(int) + PAD)


def render(p, theta, imgs):
	"""Recorte da peça rodado de theta graus (convenção complexa) à volta do centro do corpo e reamostrado à escala da
	arte (passo medido PITCH_X x PITCH_Y mm = 1 célula). Lab float com L* - L_SHIFT; máscara = interior estrito."""
	rgb = imgs(p["img"])
	cb = body_center(p)
	W, H = CANVAS
	fx, fy = CELL_W * MM / PITCH_X, CELL_H * MM / PITCH_Y     # px da arte por px do scan
	Wc, Hc = int(round(W / fx)), int(round(H / fy))
	t = np.radians(theta)
	R = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
	off = np.array([Wc / 2.0, Hc / 2.0]) - R @ cb
	A = np.c_[R, off]
	big = cv2.warpAffine(rgb, A, (Wc, Hc), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
	cont = p["contour"] @ R.T + off
	mk = np.zeros((Hc, Wc), np.uint8)
	cv2.fillPoly(mk, [np.round(cont).astype(np.int32).reshape(-1, 1, 2)], 255)
	sm = cv2.resize(big, (W, H), interpolation=cv2.INTER_AREA)
	msk = cv2.resize(mk.astype(np.float32) / 255.0, (W, H), interpolation=cv2.INTER_AREA) > 0.99
	if ERODE_PX:
		msk = cv2.erode(msk.astype(np.uint8), np.ones((2 * ERODE_PX + 1, 2 * ERODE_PX + 1), np.uint8)).astype(bool)
	lab = sx.lab_f(sm).astype(np.float64)
	lab[..., 0] -= L_SHIFT
	return dict(lab=lab, mask=msk, rgb=sm, theta=theta)


def de_cell(R, l, c, art, jit=JIT):
	"""ΔE médio (Lab, L* do scan - 4,8) entre o recorte mascarado e a janela da célula (l, c), mínimo em ±jit px;
	NCC em L* no mesmo deslocamento. Píxeis fora da arte não contam (exige >= 60 % da máscara dentro)."""
	m = R["mask"]
	S = R["lab"][m]
	W, H = CANVAS
	x0, y0 = cell_tl(l, c)
	best = (np.inf, np.nan, (0, 0))
	for dy in range(-jit, jit + 1):
		for dx in range(-jit, jit + 1):
			win = art["labp"][y0 + dy:y0 + dy + H, x0 + dx:x0 + dx + W][m]
			ok = ~np.isnan(win[:, 0])
			if ok.sum() < 0.6 * len(S):
				continue
			de = float(np.sqrt(((S[ok] - win[ok]) ** 2).sum(1)).mean())
			if de < best[0]:
				a, b = S[ok, 0] - S[ok, 0].mean(), win[ok, 0] - win[ok, 0].mean()
				ncc = float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-9))
				best = (de, ncc, (dx, dy))
	return best


def cell_scores(R, art):
	"""RMS ΔE do recorte em TODAS as posições da arte (correlação por filter2D) e, por célula, o mínimo em ±JIT px
	à volta da posição da célula -> array 47 x 64. (Localização; o 1-contra-1 usa o ΔE médio de de_cell.)"""
	M = R["mask"].astype(np.float64)
	S = R["lab"]
	fk = dict(ddepth=-1, anchor=(0, 0), borderType=cv2.BORDER_CONSTANT)
	t1 = cv2.filter2D(art["V"], kernel=M * (S ** 2).sum(-1), **fk)
	t2 = sum(cv2.filter2D(art["AV"][ch], kernel=M * S[..., ch], **fk) for ch in range(3))
	t3 = cv2.filter2D(art["A2V"], kernel=M, **fk)
	den = cv2.filter2D(art["V"], kernel=M, **fk)
	sc_ = np.sqrt(np.maximum(t1 - 2 * t2 + t3, 0) / np.maximum(den, 1e-9))
	sc_[den < 0.6 * M.sum()] = np.inf
	mn = sc_.copy()
	for dy in range(-JIT, JIT + 1):
		for dx in range(-JIT, JIT + 1):
			if dx or dy:
				mn = np.minimum(mn, np.roll(sc_, (-dy, -dx), (0, 1)))
	Lg, Cg = np.mgrid[1:NROW + 1, 1:NCOL + 1]
	x0, y0 = cell_tl(Lg, Cg)
	return mn[y0, x0]


class Renders:
	"""Cache de recortes e mapas de células por (peça, m): rotação = beta + 90 m (m = 0..3)."""
	def __init__(self, M, imgs, art):
		self.M, self.imgs, self.art = M, imgs, art
		self.r, self.s = {}, {}

	def get(self, i, m):
		if (i, m) not in self.r:
			p = self.M[i]
			self.r[(i, m)] = render(p, body_beta(p) + 90 * m, self.imgs)
		return self.r[(i, m)]

	def scores(self, i, m):
		if (i, m) not in self.s:
			self.s[(i, m)] = cell_scores(self.get(i, m), self.art)
		return self.s[(i, m)]


def n_frame_cell(L, C):
	return (L == 1).astype(int) + (L == NROW) + (C == 1) + (C == NCOL)


def joint_locate(a, b, PHI, sign, RS, gt_cell=None):
	"""Localização conjunta do par (a, b): para as 4 rotações globais g, a na célula X com rotação beta_a + 90 g e b
	na célula gémea com a rotação relativa da forma (phi + 180). Score = RMS ΔE(a em X) + RMS ΔE(b em gémea(X)).
	Devolve top-3, rank da célula GT (entre as 3008 e entre as de classe compatível pelo nº de lados F)."""
	M = RS.M
	Lg, Cg = np.mgrid[1:NROW + 1, 1:NCOL + 1]
	Lt, Ct = twin_cell(Lg, Cg)
	tot = np.full((4, NROW, NCOL), np.inf)
	for g in range(4):
		ta = body_beta(M[a]) + 90 * g
		mb, _ = snap(M[b], ta + sign * np.degrees(PHI[a, b]) + 180.0)
		tot[g] = RS.scores(a, g) + RS.scores(b, mb)[Lt - 1, Ct - 1]
	best = tot.min(0)
	gbest = tot.argmin(0)
	nF = M[a]["types"].count("F")
	comp = n_frame_cell(Lg, Cg) == nF
	order = np.argsort(best, axis=None)
	top = [(int(Lg.flat[o]), int(Cg.flat[o]), r3(best.flat[o]), int(gbest.flat[o])) for o in order[:3]]
	bc = np.where(comp, best, np.inf)
	oc = np.argsort(bc, axis=None)
	topc = [(int(Lg.flat[o]), int(Cg.flat[o]), r3(bc.flat[o]), int(gbest.flat[o])) for o in oc[:3]]
	out = dict(top3=top, top3_compat=topc, n_compat=int(comp.sum()))
	if gt_cell is not None:
		l, c = gt_cell
		v = best[l - 1, c - 1]
		out.update(gt=list(gt_cell), score_gt=r3(v), rank_3008=int(np.sum(best < v)), rank_compat=int(np.sum(best[comp] < v)),
				   g_gt=int(gbest[l - 1, c - 1]))
	return out


# ----------------------------------------------------------------------------- figuras
def asc(t):
	"""Texto para cv2.putText (só ASCII): tira acentos e troca símbolos."""
	import unicodedata
	t = str(t).replace("Δ", "d").replace("²", "2").replace("°", " graus").replace("→", "->").replace("≤", "<=")
	return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")


def put(img, t, xy, s=0.45, c=es.BLK, th=1):
	es.put(img, asc(t), xy, s, c, th)


def label(img, txt, xy, s=0.6, col=(255, 255, 255), th=1):
	txt = asc(txt)
	cv2.putText(img, txt, (int(xy[0]), int(xy[1])), cv2.FONT_HERSHEY_SIMPLEX, s, (0, 0, 0), th + 3, cv2.LINE_AA)
	cv2.putText(img, txt, (int(xy[0]), int(xy[1])), cv2.FONT_HERSHEY_SIMPLEX, s, col, th, cv2.LINE_AA)


DEC_COL = {"ACEITE": (0, 200, 0), "AMBÍGUA": (0, 220, 255), "SEM": None}


def fig_contours(path, kept, excl, fname, title, lab_fn):
	"""Overlay a 50 %: contornos das peças numeradas (amarelo), excluídas (vermelho, com razão), número de cada peça."""
	bgr = cv2.cvtColor(sx.read_rgb(path), cv2.COLOR_RGB2BGR)
	for p in kept:
		cv2.polylines(bgr, [np.round(p["contour"]).astype(np.int32).reshape(-1, 1, 2)], True, (0, 255, 255), 4, cv2.LINE_AA)
	for e in excl:
		if e.get("contour") is not None:
			cv2.polylines(bgr, [np.round(e["contour"]).astype(np.int32).reshape(-1, 1, 2)], True, (0, 0, 255), 6, cv2.LINE_AA)
		else:
			x, y, w, h = e["bbox"]
			cv2.rectangle(bgr, (x, y), (x + w, y + h), (0, 0, 255), 6)
	f = 0.5
	img = cv2.resize(bgr, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
	for p in kept:
		x, y, w, h = p["bbox"]
		label(img, lab_fn(p), ((x + w / 2) * f - 30, (y + h / 2) * f + 6), 0.7, (255, 255, 255), 2)
	for e in excl:
		x, y, w, h = e["bbox"]
		label(img, f"EXCL #{e['index']}: {e['razao'][:40]}", (min(max(5, x * f - 40), img.shape[1] - 330), (y + h / 2) * f),
			  0.5, (80, 80, 255), 1)
	img = es.with_title(img, title)
	cv2.imwrite(os.path.join(OUT, fname), img, [cv2.IMWRITE_JPEG_QUALITY, 85])


def fig_hist(panels, fname, title):
	"""panels: [(título, xlabel, bins, [(rótulo, valores, cor)], vline ou None)]."""
	imgs = []
	for tit, xl, bins, ss, vline in panels:
		W, H = 760, 420
		img = np.full((H, W, 3), 255, np.uint8)
		hs = [np.histogram(np.clip(v, bins[0], bins[-1] - 1e-6), bins)[0] / max(1, len(v)) for _, v, _ in ss]
		ymax = max([h.max() for h in hs] + [1e-6])
		x0, bw = 50, (W - 70) / (len(bins) - 1)
		for k in range(len(bins) - 1):
			for q, (h, (_, _, c)) in enumerate(zip(hs, ss)):
				xa = int(x0 + k * bw + q * bw / len(ss))
				xb = int(x0 + k * bw + (q + 1) * bw / len(ss)) - 1
				cv2.rectangle(img, (xa, H - 50 - int(h[k] / ymax * (H - 170))), (xb, H - 50), c, -1)
			if k % 2 == 0:
				put(img, f"{bins[k]:g}", (int(x0 + k * bw), H - 32), 0.38)
		cv2.line(img, (x0, H - 50), (W - 20, H - 50), es.BLK, 1)
		if vline is not None:
			xv = int(x0 + (vline[0] - bins[0]) / (bins[-1] - bins[0]) * (W - 70))
			cv2.line(img, (xv, 110), (xv, H - 50), (0, 0, 0), 2)
			put(img, vline[1], (xv + 4, 120), 0.42)
		put(img, tit, (8, 18), 0.48)
		put(img, xl + "; altura = fracao de cada serie; ultimo bin inclui o resto", (8, H - 10), 0.4)
		for q, (lab_, v, c) in enumerate(ss):
			med = np.median(v) if len(v) else float("nan")
			put(img, f"{lab_} (n={len(v)}, mediana {med:.1f})", (8, 40 + 18 * q), 0.43, c, 1)
		imgs.append(img)
	cv2.imwrite(os.path.join(OUT, fname), es.with_title(np.hstack(imgs), [title]))


def fig_matrix(M, D, acc, amb, es_pairs, groups, fname):
	"""Matriz 188 x 188 da RMS free (amarelo 0 .. violeta >= 2 mm); blocos por origem; branco = par ACEITE, preto =
	AMBÍGUA; quadrado vermelho = par gémeo E-sym (GT)."""
	N = len(M)
	c = 4
	o = 90
	img = np.full((o + N * c + 20, o + N * c + 20, 3), 255, np.uint8)
	v = np.clip(np.where(np.isfinite(D), D, 2.0), 0, 2.0) / 2.0
	col = cv2.applyColorMap(np.uint8(255 * (1 - v)), cv2.COLORMAP_VIRIDIS)
	col[np.arange(N), np.arange(N)] = (200, 200, 200)
	img[o:o + N * c, o:o + N * c] = cv2.resize(col, (N * c, N * c), interpolation=cv2.INTER_NEAREST)
	for lst, cl in ((acc, (255, 255, 255)), (amb, (0, 0, 0))):
		for (i, j) in lst:
			for a, b in ((i, j), (j, i)):
				cv2.rectangle(img, (o + b * c, o + a * c), (o + b * c + c - 1, o + a * c + c - 1), cl, -1)
	for (i, j) in es_pairs:
		for a, b in ((i, j), (j, i)):
			cv2.rectangle(img, (o + b * c - 2, o + a * c - 2), (o + b * c + c + 1, o + a * c + c + 1), (0, 0, 255), 1)
	for name, a, b in groups:
		for t in (a, b):
			cv2.line(img, (o + t * c, o), (o + t * c, o + N * c), (0, 0, 0), 1)
			cv2.line(img, (o, o + t * c), (o + N * c, o + t * c), (0, 0, 0), 1)
		put(img, name, (o + (a + b) // 2 * c - 15, o - 8), 0.45)
		put(img, name, (5, o + (a + b) // 2 * c + 5), 0.45)
	put(img, f"E-real-2: RMS free (mm) entre as {N} soltas (todos os pares, sem filtro); amarelo 0 .. violeta >= 2 mm", (5, 20), 0.42)
	put(img, "branco = par ACEITE, preto = AMBIGUA (regras 1-4, decisao simetrica); vermelho = gemeo E-sym (GT)", (5, 40), 0.42)
	cv2.imwrite(os.path.join(OUT, fname), img)


def up(img, f=6):
	return cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_NEAREST)


def panel_be(M, rec, RS, art):
	"""Painel de uma BE: forma (BE vermelho, candidata top-1 azul, alinhadas pela free) | recorte da candidata na
	orientação prevista | janela da célula gémea na arte (contorno da máscara) | texto."""
	T = 300
	p = M[rec["i"]]
	if not rec["top"]:
		t = np.full((T, 3 * T, 3), 255, np.uint8)
		put(t, f"{p['lab']}: sem candidata (classe + cordas)", (5, 20), 0.5)
		return t
	j = rec["top"][0]
	za, zb, d = aligned_b(p, M[j])
	tl = es.tile_pair(er.zpx(za), er.zpx(zb), [f"{p['lab']} vs {M[j]['lab']}", f"free {d:.2f} mm marg {rec['margin']:.2f}",
											   f"{p['cls']} / {M[j]['cls']}"], T=T)
	R = RS.get(j, rec["m_top"])
	f = 6
	cr = up(cv2.cvtColor(R["rgb"], cv2.COLOR_RGB2BGR), f)
	mk = up(R["mask"].astype(np.uint8) * 255, f)
	cs, _ = cv2.findContours(mk, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
	cv2.drawContours(cr, cs, -1, (0, 0, 255), 1)
	l2, c2 = rec["twin_cell"]
	x0, y0 = cell_tl(l2, c2)
	dx, dy = rec["img"]["off"]
	W, H = CANVAS
	aw = up(cv2.cvtColor(np.ascontiguousarray(art["rgbp"][y0 + dy:y0 + dy + H, x0 + dx:x0 + dx + W]), cv2.COLOR_RGB2BGR), f)
	cv2.drawContours(aw, cs, -1, (0, 0, 255), 1)
	cw, ch = int(CELL_W * f), int(CELL_H * f)
	cxc, cyc = aw.shape[1] // 2 - dx * f, aw.shape[0] // 2 - dy * f
	cv2.rectangle(aw, (cxc - cw // 2, cyc - ch // 2), (cxc + cw // 2, cyc + ch // 2), (255, 255, 255), 1)
	tw = np.full((T, 300, 3), 255, np.uint8)
	ii = rec["img"]
	lines = [f"{p['lab']} = ({p['cell'][0]},{p['cell'][1]})", f"gemea -> celula ({l2},{c2})", f"proposta {M[j]['lab']}",
			 f"forma: {rec['dec']}", f"dE {ii['dE']:.1f} (p90 ceu {rec['p90']:.1f})", f"NCC L* {ii['ncc']:.2f}",
			 f"rot. prevista vence: {'sim' if ii['rot_wins'] else 'NAO'}", f"residuo de orientacao {rec['resid']:.0f} graus",
			 f"forma+imagem: {rec['dec_fi']}", f"  -> {M[rec['pick_fi']]['lab'] if rec['pick_fi'] is not None else '-'}"]
	for k, s in enumerate(lines):
		put(tw, s, (6, 22 + 27 * k), 0.5)
	pad = lambda im: np.vstack([im, np.full((T - im.shape[0], im.shape[1], 3), 255, np.uint8)])  # noqa: E731
	row = np.hstack([tl, pad(cr), np.full((T, 6, 3), 255, np.uint8), pad(aw), tw])
	cv2.rectangle(row, (0, 0), (row.shape[1] - 1, row.shape[0] - 1), es.GREY, 1)
	return row


def fig_sheet(sheet, P, info, fname):
	"""Folha de céu a 50 %: número de cada peça; por cima das propostas, destino (l,c) e d1/margem; cor por decisão."""
	bgr = cv2.cvtColor(sx.read_rgb(F_CEU[sheet]), cv2.COLOR_RGB2BGR)
	for p in P:
		inf = info.get(p["lab"], {})
		colr = DEC_COL.get(inf.get("dec")) if inf.get("dest") else None
		cv2.polylines(bgr, [np.round(p["contour"]).astype(np.int32).reshape(-1, 1, 2)], True,
					  colr if colr else (255, 255, 255), 10 if colr else 3, cv2.LINE_AA)
	f = 0.5
	img = cv2.resize(bgr, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
	for p in P:
		x, y, w, h = p["bbox"]
		cx_, cy_ = (x + w / 2) * f, (y + h / 2) * f
		label(img, f"#{p['num']}", (cx_ - 18, cy_ + 8), 0.8, (255, 255, 255), 2)
		inf = info.get(p["lab"], {})
		if inf.get("dest"):
			colr = DEC_COL.get(inf["dec"]) or (255, 255, 255)
			ty = max(y * f - 22, 22)
			label(img, f"({inf['dest'][0]},{inf['dest'][1]}){'*' if inf.get('mutual') else ''}", (x * f - 5, ty), 0.65, colr, 2)
			label(img, f"{inf['d1']:.2f}/{inf['margin']:.1f}", (x * f - 5, ty + 18), 0.55, colr, 1)
		elif inf.get("fp"):
			label(img, f"FP? {inf['fp']}", (x * f - 5, y * f - 4), 0.5, (255, 0, 255), 1)
	img = es.with_title(img, [f"E-real-2, folha {sheet}: numero da peca (grid_order: filas por y, x na fila); por cima: destino "
							  "(l,c) proposto (gemea de uma BE) e d1 mm / margem", "verde = ACEITE (forma), amarelo = AMBIGUA; "
							  "* = vizinho mutuo com a BE; magenta = melhor candidata fora das BE (falso positivo)"])
	cv2.imwrite(os.path.join(OUT, fname), img, [cv2.IMWRITE_JPEG_QUALITY, 85])


# ----------------------------------------------------------------------------- principal
def main():
	t0 = time.time()
	force = "--force" in sys.argv
	os.makedirs(WORK, exist_ok=True)
	R = dict(descricao="E-real-2 (2026-10-31): BE (relva, GT) -> gémea entre 100 soltas de céu (sem GT) numa memória de 188 "
			 "soltas; forma (regras 1-4) + imagem 1-contra-1 contra a arte limpa. Ver docs/diagnostico/gemeos/EREAL2.md.",
			 limiares=dict(t95=T95, tmax=TMAX, margem=MARGIN_MIN, dL_max_mm=DL_MAX, L_shift=L_SHIFT, erode_px=ERODE_PX,
						   passo_mm=dict(x=r3(PITCH_X), y=r3(PITCH_Y)), canvas_px=list(CANVAS), jitter_px=JIT,
						   celula_arte_px=[r3(CELL_W), r3(CELL_H)], arte_linhas=[ART_Y0, ART_Y0 + ART_H - 1]))
	MEMD = build_memory(force)
	BE, CEU, BD, ES = MEMD["BE"], MEMD["CEU"], MEMD["BD"], MEMD["ES"]
	CEUm = [p for p in CEU if p.get("ok")]
	M = BE + CEUm + BD + ES
	N = len(M)
	gidx = {g: [i for i, p in enumerate(M) if p["src"] == g] for g in ("BE", "ceu", "BD", "ES")}
	groups = [(g, gidx[g][0], gidx[g][-1] + 1) for g in ("BE", "ceu", "BD", "ES")]
	log(f"[memória] {N} soltas: BE {len(BE)}, céu {len(CEUm)} (numeradas {len(CEU)}), BD {len(BD)}, E-sym {len(ES)} "
		f"(4 cantos {sum(1 for p in ES if p.get('ok'))}/40)")
	R["memoria"] = dict(n=N, BE=len(BE), ceu=len(CEUm), ceu_numeradas=len(CEU), BD=len(BD), ES=len(ES), checks=MEMD["chk"],
						ceu_por_folha={s: sum(1 for p in CEU if p["sheet"] == s) for s in SHEETS})
	# --- overlays de segmentação
	fig_contours(F_BE, BE, MEMD["chk"]["BE"]["excluidos"], "ereal2_BE__contours.jpg",
				 ["E-real-2: segment_scan nas soltas BE (amarelo); BE(k,j): k = s+1 (coluna s da DIREITA), j = r+1 (fila r de BAIXO)",
				  "excluidos (retangulo e texto vermelhos): cluster / fora de 250-650 mm2 / a < 1,5 mm de outra peca (faixa em L)"],
				 lambda p: f"BE({p['k']},{p['j']})")
	for s in SHEETS:
		fig_contours(F_CEU[s], [p for p in CEU if p["sheet"] == s], MEMD["excl_ceu"][s], f"ereal2_{s}__contours.jpg",
					 [f"E-real-2: segment_scan na folha de ceu {s} (amarelo = peca numerada; vermelho = excluido, com razao)",
					  "numeracao 1-based por segcache.grid_order (filas por y, x dentro da fila)"], lambda p: f"#{p['num']}")
	# --- forma
	t1 = time.time()
	D, PHI = shape_matrices(M)
	for (i, j) in ((0, 5), (3, N - 1), (gidx["ES"][0], gidx["ES"][-1]), (gidx["ceu"][7], gidx["BD"][3])):
		d_, _, ph = free_dist(M[i], M[j])
		assert abs(d_ - D[i, j]) < 1e-6 and abs(wrap(np.degrees(ph - PHI[i, j]))) < 1e-6, "free_dist vectorizado difere"
	DL = chord_matrix(M)
	PASS = DL <= DL_MAX
	log(f"[forma] matrizes {N}x{N} (free + cordas) em {time.time() - t1:.1f} s; pares que passam classe+cordas "
		f"{int(np.triu(PASS, 1).sum())} de {N * (N - 1) // 2}")
	# --- controlo E-sym da cadeia de orientação (sinal de phi)
	iA = {M[i]["esym_i"]: i for i in gidx["ES"] if M[i]["esym_name"] == "A1"}
	iB = {M[i]["esym_i"]: i for i in gidx["ES"] if M[i]["esym_name"] == "B2"}
	es_pairs = [(iA[i], iB[es.twin(i)]) for i in range(20)]
	ori = {}
	for sign in (+1, -1):
		okB, okA, rows = 0, 0, []
		for a, b in es_pairs:
			nuA, nuB = f_normal(M[a]), f_normal(M[b])
			mA, _ = snap(M[a], -90.0 - nuA)                 # A1: lado F para cima (linha 1)
			thA_s = body_beta(M[a]) + 90 * mA
			mB, res = snap(M[b], thA_s + sign * np.degrees(PHI[a, b]) + 180.0)
			thB_s = body_beta(M[b]) + 90 * mB
			upA = abs(wrap(nuA + thA_s + 90.0)) < 45
			dnB = abs(wrap(nuB + thB_s - 90.0)) < 45
			okA += upA
			okB += dnB
			rows.append(dict(A1=M[a]["lab"], B2=M[b]["lab"], mA=mA, mB=mB, resid=r3(res), A_F_cima=bool(upA), B_F_baixo=bool(dnB)))
		ori[sign] = dict(A1_F_em_cima=int(okA), B2_F_em_baixo=int(okB), n=len(es_pairs),
						 resid_abs=st([abs(r["resid"]) for r in rows]), por_par=rows)
	SIGN = +1 if ori[+1]["B2_F_em_baixo"] >= ori[-1]["B2_F_em_baixo"] else -1
	log(f"[orientação E-sym] +phi: A1 F em cima {ori[1]['A1_F_em_cima']}/20, B2 F em baixo {ori[1]['B2_F_em_baixo']}/20 "
		f"(resíduo |θ| mediana {ori[1]['resid_abs'].get('median')}°, máx {ori[1]['resid_abs'].get('max')}°); -phi: B2 F em baixo "
		f"{ori[-1]['B2_F_em_baixo']}/20 -> sinal usado {'+' if SIGN > 0 else '-'}phi{'' if SIGN > 0 else ' (INVERTIDO)'}")
	# --- imagem: arte e recortes
	t2 = time.time()
	art = load_art()
	RS = Renders(M, Imgs(), art)

	def rot_test(i, m, cell):
		"""ΔE nas 4 rotações; devolve (ΔE da prevista, ncc, offset, vence?, lista dos 4)."""
		v = [de_cell(RS.get(i, mm), cell[0], cell[1], art) for mm in range(4)]
		des = [x[0] for x in v]
		return v[m][0], v[m][1], v[m][2], bool(int(np.argmin(des)) == m), [r3(x) for x in des]

	es_img = []
	for (a, b), rr in zip(es_pairs, ori[SIGN]["por_par"]):
		ca, cb = M[a]["cell"], M[b]["cell"]
		da = rot_test(a, rr["mA"], ca)
		db = rot_test(b, rr["mB"], cb)
		es_img.append(dict(A1=M[a]["lab"], cell_A=list(ca), dE_A=r3(da[0]), A_rot_vence=da[3], dE_A_4rot=da[4], B2=M[b]["lab"],
						   cell_B=list(cb), dE_B=r3(db[0]), B_rot_vence=db[3], dE_B_4rot=db[4]))
	log(f"[imagem E-sym] A1 na sua célula (F em cima): ΔE mediana {np.median([r['dE_A'] for r in es_img]):.1f}, rotação "
		f"prevista vence {sum(r['A_rot_vence'] for r in es_img)}/20; B2 com a rotação prevista pela forma: ΔE mediana "
		f"{np.median([r['dE_B'] for r in es_img]):.1f}, vence {sum(r['B_rot_vence'] for r in es_img)}/20")
	be_own = []
	for i in gidx["BE"]:
		m, res = snap(M[i], 90.0)
		dd = rot_test(i, m, M[i]["cell"])
		be_own.append(dict(BE=M[i]["lab"], cell=list(M[i]["cell"]), m=m, resid=r3(res), dE=r3(dd[0]), ncc=r3(dd[1]),
						   rot_vence=dd[3], dE_4rot=dd[4]))
	log(f"[imagem BE própria] BE na sua célula (relva) com rotação 90°: ΔE mediana {np.median([r['dE'] for r in be_own]):.1f}, "
		f"rotação prevista vence {sum(r['rot_vence'] for r in be_own)}/20; resíduo de orientação máx "
		f"{max(abs(r['resid']) for r in be_own):.1f}°")
	# --- A.2 BE -> memória
	recs = []
	for q in gidx["BE"]:
		rec = query(q, D, PASS)
		mq, _ = snap(M[q], 90.0)
		thq = body_beta(M[q]) + 90 * mq
		rec.update(m_q=mq, thq=thq, twin_cell=twin_cell(*M[q]["cell"]), cand_img=[])
		for j in rec["top"]:
			mj, resj = snap(M[j], thq + SIGN * np.degrees(PHI[q, j]) + 180.0)
			de, ncc, off, wins, l4 = rot_test(j, mj, rec["twin_cell"])
			rec["cand_img"].append(dict(j=j, m=mj, resid=resj, dE=de, ncc=ncc, off=off, rot_wins=wins, dE_4rot=l4))
		if rec["top"]:
			c0 = rec["cand_img"][0]
			rec.update(m_top=c0["m"], resid=c0["resid"], img=dict(dE=c0["dE"], ncc=c0["ncc"], off=c0["off"], rot_wins=c0["rot_wins"]))
		recs.append(rec)
	# (ii) todas as candidatas de céu contra a célula gémea de cada BE (orientação prevista pela forma)
	sky_de = {}
	for rec in recs:
		q = rec["i"]
		for j in gidx["ceu"]:
			mj, _ = snap(M[j], rec["thq"] + SIGN * np.degrees(PHI[q, j]) + 180.0)
			sky_de[(q, j)] = de_cell(RS.get(j, mj), *rec["twin_cell"], art)[0]
	all_sky = np.array(list(sky_de.values()))
	P90 = float(np.percentile(all_sky, 90))
	# (i) candidata top-1 contra as 20 células gémeas das BE (a certa vs as 19 erradas)
	right, wrong, ranks_i = [], [], []
	for rec in recs:
		if not rec["top"]:
			continue
		R_ = RS.get(rec["top"][0], rec["m_top"])
		v = {r2["i"]: de_cell(R_, *r2["twin_cell"], art)[0] for r2 in recs}
		right.append(v[rec["i"]])
		wrong += [x for k, x in v.items() if k != rec["i"]]
		rec["rank_i"] = int(sum(x < v[rec["i"]] for k, x in v.items() if k != rec["i"]))
		ranks_i.append(rec["rank_i"])
	# forma + imagem
	for rec in recs:
		rec["p90"] = P90
		q = rec["i"]
		if rec["top"]:
			allq = np.array([sky_de[(q, j)] for j in gidx["ceu"]])
			rec["pct_ii"] = r3(100.0 * np.mean(allq < rec["img"]["dE"]))
		short = [ci for ci in rec["cand_img"] if D[q, ci["j"]] <= TMAX]
		if not short:
			rec.update(dec_fi="SEM", pick_fi=None, nota_fi="sem candidata com d <= tmax", mudou=False)
			continue
		pick = min(short, key=lambda ci: ci["dE"])
		changed = pick["j"] != rec["top"][0]
		if rec["dec"] == "ACEITE" and not changed and pick["dE"] <= P90:
			rec.update(dec_fi="ACEITE", pick_fi=pick["j"], nota_fi="forma ACEITE e ΔE <= p90")
		elif pick["dE"] <= P90:
			rec.update(dec_fi="AMBÍGUA", pick_fi=pick["j"], nota_fi="imagem muda a proposta" if changed else
					   ("forma ACEITE mas a imagem prefere outra" if rec["dec"] == "ACEITE" else "forma AMBÍGUA, ΔE <= p90"))
		else:
			rec.update(dec_fi="AMBÍGUA", pick_fi=pick["j"], nota_fi="imagem contradiz (ΔE > p90 em todas as candidatas)")
		rec["mudou"] = changed
	cnt = lambda key: {d: sum(1 for r in recs if r.get(key) == d) for d in ("ACEITE", "AMBÍGUA", "SEM")}  # noqa: E731
	acc_src = {}
	for r in recs:
		if r["dec"] != "SEM":
			acc_src.setdefault(r["dec"], {}).setdefault(M[r["top"][0]]["src"], 0)
			acc_src[r["dec"]][M[r["top"][0]]["src"]] += 1
	log(f"[BE -> memória] forma: {cnt('dec')}; origem da top-1 das ACEITE/AMBÍGUA {acc_src}")
	log(f"[BE -> memória] forma+imagem: {cnt('dec_fi')}; propostas que a imagem muda {sum(1 for r in recs if r.get('mudou'))}; "
		f"imagem contradiz {sum(1 for r in recs if 'contradiz' in r.get('nota_fi', ''))}")
	log(f"[imagem] (i) top-1 na célula certa vs nas 19 erradas: ΔE mediana {np.median(right):.1f} vs {np.median(wrong):.1f}; "
		f"rank da certa entre 20 = 0 em {sum(r == 0 for r in ranks_i)}/{len(ranks_i)}, mediana {np.median(ranks_i):.0f}; "
		f"(ii) céu x célula gémea: n={len(all_sky)}, mediana {np.median(all_sky):.1f}, p90 {P90:.1f}; "
		f"(iii) rotação prevista vence nas top-1: {sum(r['img']['rot_wins'] for r in recs if r['top'])}/{sum(1 for r in recs if r['top'])} "
		f"({time.time() - t2:.1f} s)")
	for r in recs:
		tops = ", ".join(f"{M[ci['j']]['lab']} {D[r['i'], ci['j']]:.3f} ΔE {ci['dE']:.1f} res {ci['resid']:.0f}°" for ci in r["cand_img"])
		log(f"   {M[r['i']]['lab']} -> gémea {r['twin_cell']}: {r['dec']:7s} d1 {fin(r['d1'])} margem {fin(r['margin'])} | "
			f"forma+imagem {r.get('dec_fi')} {M[r['pick_fi']]['lab'] if r.get('pick_fi') is not None else ''} ({r.get('nota_fi')}) "
			f"| pct(ii) {r.get('pct_ii')} rank(i) {r.get('rank_i')} | top3: {tops} | passam {r['n_pass']}")
	# --- A.3 céu -> memória
	be_choice = {r["top"][0]: r["i"] for r in recs if r["top"]}
	sky_recs = []
	for i in gidx["ceu"]:
		rec = query(i, D, PASS)
		b = rec["top"][0] if rec["top"] else None
		rec["best_src"] = M[b]["src"] if b is not None else None
		rec["mutual"] = bool(b is not None and M[b]["src"] == "BE" and be_choice.get(i) == b)
		if b is not None and M[b]["src"] == "BE":
			rec["dest"] = twin_cell(*M[b]["cell"])
			rec["dE"] = sky_de.get((b, i))
		sky_recs.append(rec)
	sc_cnt = {}
	for r in sky_recs:
		sc_cnt.setdefault(r["dec"], {}).setdefault(str(r["best_src"]), 0)
		sc_cnt[r["dec"]][str(r["best_src"])] += 1
	n_mut = sum(r["mutual"] for r in sky_recs)
	log(f"[céu -> memória] decisão x origem da melhor: {sc_cnt}; vizinhos mútuos com a BE que a escolheu: {n_mut}")
	for r in sky_recs:
		if r["dec"] != "SEM":
			log(f"   {M[r['i']]['lab']} -> {M[r['top'][0]]['lab']} {r['dec']} d1 {fin(r['d1'])} margem {fin(r['margin'])}"
				f"{' destino ' + str(r['dest']) if r.get('dest') else ''}{' (mútuo)' if r['mutual'] else ''}")
	# --- todos contra todos (regras 1-4, decisão simétrica de par)
	Dp = np.where(PASS, D, np.inf)
	np.fill_diagonal(Dp, np.inf)

	def pair_margin(i, j):
		ri = Dp[i].copy()
		ri[j] = np.inf
		rj = Dp[j].copy()
		rj[i] = np.inf
		comp = min(ri.min(), rj.min())
		return comp / D[i, j] if np.isfinite(comp) else float("inf")
	pairs = []
	for i in range(N):
		for j in range(i + 1, N):
			if PASS[i, j]:
				mg = pair_margin(i, j)
				dec = decide(D[i, j], mg)
				if dec != "SEM":
					pairs.append(dict(i=i, j=j, d=D[i, j], margin=mg, dec=dec))

	def gt_rel(i, j):
		"""'pos' (gémeos pela GT), 'neg' (negativo conhecido), 'ceuceu' (esperado negativo), 'BExceu' (desconhecido)."""
		a, b = M[i], M[j]
		if a["cell"] is not None and b["cell"] is not None:
			return "pos" if tuple(int(v) for v in twin_cell(*a["cell"])) == tuple(b["cell"]) else "neg"
		s = {a["src"], b["src"]}
		if s == {"ceu"}:
			return "ceuceu"
		if "BE" in s:
			return "BExceu"
		return "neg"
	rel_all = {}
	for i in range(N):
		for j in range(i + 1, N):
			k = gt_rel(i, j)
			rel_all[k] = rel_all.get(k, 0) + 1
	by_rel = {}
	for pr in pairs:
		k = gt_rel(pr["i"], pr["j"])
		by_rel.setdefault(k, {}).setdefault(pr["dec"], 0)
		by_rel[k][pr["dec"]] += 1
	es_rec = []
	for a, b in es_pairs:
		pr = next((x for x in pairs if {x["i"], x["j"]} == {a, b}), None)
		es_rec.append(dict(A1=M[a]["lab"], B2=M[b]["lab"], d=r3(D[a, b]), passa_1_2=bool(PASS[a, b]),
						   margin=fin(pair_margin(a, b)), dec=pr["dec"] if pr else "SEM"))
	log(f"[pares] {N * (N - 1) // 2} pares; por relação GT {rel_all}; ACEITE/AMBÍGUA por relação: {by_rel}")
	mgs = [r["margin"] for r in es_rec if r["margin"] is not None]
	log(f"[pares] controlo E-sym: ACEITE {sum(r['dec'] == 'ACEITE' for r in es_rec)}/20, AMBÍGUA "
		f"{sum(r['dec'] == 'AMBÍGUA' for r in es_rec)}, passam 1-2 {sum(r['passa_1_2'] for r in es_rec)}/20, d mediana "
		f"{np.median([r['d'] for r in es_rec]):.3f} máx {max(r['d'] for r in es_rec):.3f}, margem mín {min(mgs) if mgs else None} "
		f"mediana {np.median(mgs) if mgs else None}")
	for pr in pairs:
		if gt_rel(pr["i"], pr["j"]) in ("neg", "ceuceu"):
			log(f"   falso positivo ({gt_rel(pr['i'], pr['j'])}): {M[pr['i']]['lab']} x {M[pr['j']]['lab']} {pr['dec']} d {pr['d']:.3f} "
				f"margem {pr['margin']:.2f}")
	# --- sensibilidade à tolerância das cordas (regra 2)
	sens = {}
	for dlm in (1.0, 1.5, 2.0, None):
		PS = (DL <= dlm) if dlm is not None else np.isfinite(DL)
		Dq = np.where(PS, D, np.inf)
		np.fill_diagonal(Dq, np.inf)

		def mg_(i, j):
			ri = Dq[i].copy()
			ri[j] = np.inf
			rj = Dq[j].copy()
			rj[i] = np.inf
			comp = min(ri.min(), rj.min())
			return comp / D[i, j] if np.isfinite(comp) else float("inf")
		cntp = {}
		for i in range(N):
			for j in range(i + 1, N):
				if PS[i, j]:
					dec = decide(D[i, j], mg_(i, j))
					if dec != "SEM":
						k = gt_rel(i, j)
						cntp.setdefault(k, {}).setdefault(dec, 0)
						cntp[k][dec] += 1
		beq = [query(q, D, PS) for q in gidx["BE"]]
		sens[str(dlm)] = dict(pares=cntp, BE=dict((d, sum(r["dec"] == d for r in beq)) for d in ("ACEITE", "AMBÍGUA", "SEM")),
							  BE_propostas=[f"{M[r['i']]['lab']}->{M[r['top'][0]]['lab']} {r['dec']} {r['d1']:.3f}" for r in beq if r["dec"] != "SEM"])
		log(f"[sensibilidade cordas] |ΔL| <= {dlm}: pares {cntp}; BE {sens[str(dlm)]['BE']} {sens[str(dlm)]['BE_propostas']}")
	# --- localização conjunta pela imagem
	t3 = time.time()
	loc_es = []
	for a, b in es_pairs:
		r_ = joint_locate(a, b, PHI, SIGN, RS, gt_cell=M[a]["cell"])
		r_.update(A1=M[a]["lab"], B2=M[b]["lab"])
		loc_es.append(r_)
	rk = [r["rank_3008"] for r in loc_es]
	rkc = [r["rank_compat"] for r in loc_es]
	log(f"[localização E-sym] rank da célula certa entre 3008: mediana {np.median(rk):.0f}, top-1 {sum(x == 0 for x in rk)}/20, "
		f"top-10 {sum(x < 10 for x in rk)}/20; entre as {loc_es[0]['n_compat']} de borda: mediana {np.median(rkc):.0f}, top-1 "
		f"{sum(x == 0 for x in rkc)}/20, top-10 {sum(x < 10 for x in rkc)}/20 ({time.time() - t3:.1f} s)")
	for r_ in loc_es:
		log(f"   {r_['A1']} GT {r_['gt']}: rank {r_['rank_3008']}/3008, {r_['rank_compat']}/{r_['n_compat']} borda; top-3 {r_['top3']}")
	Lg, Cg = np.mgrid[1:NROW + 1, 1:NCOL + 1]
	interior = n_frame_cell(Lg, Cg) == 0
	loc_be = []
	for i in gidx["BE"]:
		s = np.min([RS.scores(i, mm) for mm in range(4)], axis=0)
		l, c = M[i]["cell"]
		v = s[l - 1, c - 1]
		loc_be.append(dict(BE=M[i]["lab"], cell=[l, c], rank_3008=int(np.sum(s < v)), rank_interior=int(np.sum(s[interior] < v))))
	rb = [r["rank_3008"] for r in loc_be]
	log(f"[localização BE sozinha, controlo] rank da própria célula (relva) entre 3008: mediana {np.median(rb):.0f}, top-1 "
		f"{sum(x == 0 for x in rb)}/20, top-10 {sum(x < 10 for x in rb)}/20")
	loc_acc = []
	for pr in [p for p in pairs if p["dec"] == "ACEITE"][:80]:
		a, b = pr["i"], pr["j"]
		if M[b]["cell"] is not None and M[a]["cell"] is None:
			a, b = b, a
		if gt_rel(a, b) == "pos":
			continue
		r_ = joint_locate(a, b, PHI, SIGN, RS, gt_cell=M[a]["cell"])
		r_.update(a=M[a]["lab"], b=M[b]["lab"], d=r3(pr["d"]), margin=fin(pr["margin"]), rel=gt_rel(a, b))
		loc_acc.append(r_)
	log(f"[localização pares ACEITE] {len(loc_acc)} pares (sem os E-sym) ({time.time() - t3:.1f} s)")
	for r_ in loc_acc:
		log(f"   {r_['a']} + {r_['b']} ({r_['rel']}): d {r_['d']} margem {r_['margin']}; top-3 {r_['top3']}"
			+ f"; top-3 compat. {r_['top3_compat']}"
			+ (f"; GT {r_['gt']} rank {r_['rank_3008']}/3008, {r_['rank_compat']}/{r_['n_compat']} compat." if "gt" in r_ else ""))
	# --- figuras
	info = {}
	for r in sky_recs:
		d = dict(dec=r["dec"], d1=r["d1"] or 0, margin=min(r["margin"] or 0, 99), mutual=r["mutual"])
		if r.get("dest") and r["dec"] != "SEM":
			d["dest"] = r["dest"]
		elif r["dec"] != "SEM" and r["top"]:
			d["fp"] = M[r["top"][0]]["lab"]
		info[M[r["i"]]["lab"]] = d
	for s in SHEETS:
		fig_sheet(s, [p for p in CEUm if p["sheet"] == s], info, f"ereal2_{s}_propostas.jpg")
	rows = [panel_be(M, r, RS, art) for r in recs]
	Wm = max(x.shape[1] for x in rows)
	rows = [np.hstack([x, np.full((x.shape[0], Wm - x.shape[1], 3), 255, np.uint8)]) for x in rows]
	grid2 = [np.hstack([rows[k], rows[k + 1] if k + 1 < len(rows) else np.full_like(rows[k], 255)]) for k in range(0, len(rows), 2)]
	cv2.imwrite(os.path.join(OUT, "ereal2_be_propostas.png"), es.with_title(np.vstack(grid2), [
		"E-real-2: BE (vermelho) vs candidata top-1 (azul) alinhadas pela free | recorte da candidata na orientacao prevista "
		"(BE direita + phi + 180), escala da arte, mascara a vermelho | janela da celula gemea na arte limpa (retangulo branco = celula)",
		f"dE = Delta E medio Lab mascarado (L* do scan - {L_SHIFT}), jitter +-{JIT} px; p90 = percentil 90 de todas as pecas de ceu "
		"contra as celulas gemeas das BE (consistencia de imagem, nao identidade)"]))
	fig_hist([("(i) candidata top-1: celula gemea certa vs as 19 erradas", "Delta E medio", np.arange(0, 42, 2),
			   [("celula da BE que a propos", np.array(right), es.RED), ("as outras 19 celulas gemeas", np.array(wrong), es.GREY)], None),
			  ("(ii) todas as pecas de ceu x celula gemea de cada BE", "Delta E medio", np.arange(0, 42, 2),
			   [("ceu x celula (orientacao pela forma)", all_sky, es.BLUE),
				("propostas top-1 de ceu", np.array([r["img"]["dE"] for r in recs if r["top"] and M[r["top"][0]]["src"] == "ceu"]), es.RED)],
			   (P90, f"p90 {P90:.1f}")),
			  ("controlos: E-sym e BE na propria celula", "Delta E medio", np.arange(0, 42, 2),
			   [("A1 na sua celula (F em cima)", np.array([r["dE_A"] for r in es_img]), es.RED),
				("B2 com a rotacao prevista", np.array([r["dE_B"] for r in es_img]), es.BLUE),
				("BE na sua celula (relva)", np.array([r["dE"] for r in be_own]), es.GRN)], None)],
			 "ereal2_imagem_hist.png", f"E-real-2: Delta E medio (Lab, L* do scan - {L_SHIFT}) recorte vs celula da arte limpa")
	fig_matrix(M, D, [(p["i"], p["j"]) for p in pairs if p["dec"] == "ACEITE"], [(p["i"], p["j"]) for p in pairs if p["dec"] == "AMBÍGUA"],
			   es_pairs, groups, "ereal2_matriz.png")
	# --- GT BE
	gt = dict(descricao="GT do canto BE (31-out-2026), soltas. (k, j): k = linha a contar de baixo, j = coluna a contar da esquerda; "
			  "(l, c) = (48 - k, j); gémea = célula global (k, 65 - j). Disposição: bloco rodado 90° anti-horário; coluna s do scan "
			  "(da direita) -> k = s + 1, fila r (de baixo) -> j = r + 1; verificada por ereal2.py (contagens, 4 cantos sem F, "
			  "banda escura em k = 5). Cordas em mm pela ordem dos lados de analyse_v2; contorno em px do ficheiro (≈ 400 pontos).",
			  ficheiro="images/pieces/gt_canto_BE_soltas_300dpi.jpg", verificacoes=MEMD["chk"]["BE"],
			  soltas=[dict(indice_segment_scan=p["index"], fila_r_de_baixo=p["r"], coluna_s_da_direita=p["s"], k=p["k"], j=p["j"],
						   l=p["cell"][0], c=p["cell"][1], gemea=list(twin_cell(*p["cell"])), classe=p["cls"], tipos="".join(p["types"]),
						   cordas_mm=[r3(v) for v in p["lens"]], area_mm2=r3(p["area_mm2"]), L_mediano=r3(p["L_med"]), bbox=p["bbox"],
						   contorno_px=p["contour"][::max(1, len(p["contour"]) // 400)].round().astype(int).tolist()) for p in BE])
	with open(os.path.join(OUT, "ereal2_gt_BE.json"), "w", encoding="utf-8") as f:
		json.dump(er.clean(gt), f, ensure_ascii=False)
	# --- propostas.txt
	fmt = lambda v, n=2: "-" if v is None or not np.isfinite(v) else f"{v:.{n}f}"  # noqa: E731
	L_ = ["E-real-2: propostas para verificação física (gerado por tools/diagnostico/gemeos/ereal2.py)",
		  f"Regras: classe igual; |ΔL| <= {DL_MAX} mm nos 4 lados; ACEITE se d1 <= {T95} mm e d2/d1 >= {MARGIN_MIN}; AMBÍGUA se d1 <= {TMAX}; "
		  f"forma+imagem: ACEITE se forma ACEITE, a imagem escolhe a mesma entre as top-3 com d <= {TMAX} e ΔE <= p90 ({P90:.1f}).",
		  "dE = ΔE médio (Lab, L* do scan - 4,8) contra a célula gémea da arte limpa: consistência de imagem, não identidade.",
		  "Numeração das folhas de céu: ver ereal2_<folha>__contours.jpg / ereal2_<folha>_propostas.jpg (#n)."]
	for s_ in SHEETS:
		ck = MEMD["chk"]["ceu"][s_]
		if ck["numeradas"] != ck["esperadas"]:
			L_.append(f"ATENÇÃO {s_}: {ck['numeradas']} peças numeradas, {ck['esperadas']} esperadas; as que faltam não foram segmentadas "
					  "(ver ereal2_" + s_ + "__contours.jpg: peças sem número) e não estão na memória.")
	L_ += ["",
		  f"== Secção 1: as 20 BE (relva, GT) -> gémea entre as {N - 1} outras soltas ==", ""]
	for r in recs:
		p = M[r["i"]]
		l2, c2 = (int(v) for v in r["twin_cell"])
		head = f"BE({p['k']},{p['j']}) global ({p['cell'][0]},{p['cell'][1]}) → gémea ({l2},{c2})"
		if r["top"]:
			pk = M[r["pick_fi"]]["lab"] if r.get("pick_fi") is not None else "-"
			L_.append(f"{head} | proposta: {M[r['top'][0]]['lab']} | d1 {fmt(r['d1'], 3)} mm | d2/d1 {fmt(r['margin'])} | "
					  f"dE {fmt(r['img']['dE'], 1)} | forma: {r['dec']} | forma+imagem: {r['dec_fi']} ({pk}; {r['nota_fi']}) | ACERTO/ERRO: ____")
			L_.append("      top-3: " + "; ".join(f"{M[ci['j']]['lab']} d {D[r['i'], ci['j']]:.3f} dE {ci['dE']:.1f}" for ci in r["cand_img"]))
		else:
			L_.append(f"{head} | sem candidata (classe + cordas) | forma: SEM | ACERTO/ERRO: ____")
	L_ += ["", f"== Secção 2: as peças de céu, por folha e número (consulta céu -> as outras {N - 1}) ==", ""]
	srec = {M[r["i"]]["lab"]: r for r in sky_recs}
	for p in CEU:
		if not p.get("ok"):
			L_.append(f"{p['lab']}: fora da memória (sem 4 cantos)")
			continue
		r = srec[p["lab"]]
		if r["dec"] == "SEM" or not r["top"]:
			L_.append(f"{p['lab']} → sem gémeo" + (f" (melhor {M[r['top'][0]]['lab']} d {fmt(r['d1'], 3)})" if r["top"] else " (nenhuma passa classe+cordas)"))
			continue
		b = r["top"][0]
		if M[b]["src"] == "BE":
			dl, dc = (int(v) for v in r["dest"])
			L_.append(f"{p['lab']} → ({dl},{dc}) [{M[b]['lab']}] d1 {fmt(r['d1'], 3)} margem {fmt(r['margin'])} dE {fmt(r.get('dE'), 1)} "
					  f"{r['dec']}{' (mútuo)' if r['mutual'] else ''}")
		else:
			L_.append(f"{p['lab']} → melhor {M[b]['lab']} (fora das BE: falso positivo) d1 {fmt(r['d1'], 3)} margem {fmt(r['margin'])} {r['dec']}")
	L_ += ["", "== Secção 3: colocações (preencher) ==", "", "folha #n → colocada em (l,c) | encaixa? | imagem bate? | notas", ""]
	L_ += ["____ #__ → (__,__) | ___ | ___ | ____________"] * 15
	with open(os.path.join(OUT, "ereal2_propostas.txt"), "w", encoding="utf-8") as f:
		f.write("\n".join(L_) + "\n")
	# --- results.json
	R.update(
		orientacao_esym={("+phi" if s > 0 else "-phi"): {k: v for k, v in ori[s].items() if k != "por_par"} for s in (1, -1)},
		sinal_phi_usado="+phi" if SIGN > 0 else "-phi", orientacao_esym_por_par=ori[SIGN]["por_par"],
		imagem_esym=dict(dE_A1=st([r["dE_A"] for r in es_img]), dE_B2=st([r["dE_B"] for r in es_img]),
						 A1_rot_vence=sum(r["A_rot_vence"] for r in es_img), B2_rot_vence=sum(r["B_rot_vence"] for r in es_img), por_par=es_img),
		imagem_BE_propria=dict(dE=st([r["dE"] for r in be_own]), rot_vence=sum(r["rot_vence"] for r in be_own), por_peca=be_own),
		be_consultas=[dict(BE=M[r["i"]]["lab"], cell=list(M[r["i"]]["cell"]), gemea=[int(v) for v in r["twin_cell"]], n_passam=r["n_pass"],
						   top3=[dict(lab=M[ci["j"]]["lab"], src=M[ci["j"]]["src"], d=r3(D[r["i"], ci["j"]]), dE=r3(ci["dE"]), ncc=r3(ci["ncc"]),
									  rot_vence=ci["rot_wins"], resid_graus=r3(ci["resid"]), dE_4rot=ci["dE_4rot"]) for ci in r["cand_img"]],
						   d1=fin(r["d1"]), margem=fin(r["margin"]), forma=r["dec"], forma_imagem=r.get("dec_fi"),
						   pick_fi=M[r["pick_fi"]]["lab"] if r.get("pick_fi") is not None else None, nota_fi=r.get("nota_fi"),
						   rank_i=r.get("rank_i"), pct_ii=r.get("pct_ii")) for r in recs],
		be_resumo=dict(forma=cnt("dec"), forma_imagem=cnt("dec_fi"), origem_top1=acc_src, mudam=sum(1 for r in recs if r.get("mudou")),
					   contradiz=sum(1 for r in recs if "contradiz" in r.get("nota_fi", ""))),
		imagem_baseline=dict(i_certa=st(right), i_erradas=st(wrong), i_rank_certa_entre_20=ranks_i,
							 ii_ceu_x_celula=st(all_sky), p90=r3(P90),
							 iii_rot_prevista_vence=sum(r["img"]["rot_wins"] for r in recs if r["top"]), iii_n=sum(1 for r in recs if r["top"])),
		ceu_consultas=dict(decisao_x_origem=sc_cnt, mutuos=n_mut,
						   por_peca=[dict(peca=M[r["i"]]["lab"], dec=r["dec"], melhor=M[r["top"][0]]["lab"] if r["top"] else None,
										  d1=fin(r["d1"]), margem=fin(r["margin"]), destino=[int(v) for v in r["dest"]] if r.get("dest") else None,
										  mutuo=r["mutual"]) for r in sky_recs]),
		pares=dict(n_pares=N * (N - 1) // 2, por_relacao_GT=rel_all, decisoes_por_relacao=by_rel, esym=es_rec,
				   aceites=[dict(a=M[p["i"]]["lab"], b=M[p["j"]]["lab"], d=r3(p["d"]), margem=fin(p["margin"]), rel=gt_rel(p["i"], p["j"]))
							for p in pairs if p["dec"] == "ACEITE"],
				   ambiguas=[dict(a=M[p["i"]]["lab"], b=M[p["j"]]["lab"], d=r3(p["d"]), margem=fin(p["margin"]), rel=gt_rel(p["i"], p["j"]))
							 for p in pairs if p["dec"] == "AMBÍGUA"]),
		sensibilidade_cordas=sens,
		localizacao=dict(esym=loc_es, esym_resumo=dict(rank_3008=st(rk), top1=sum(x == 0 for x in rk), top10=sum(x < 10 for x in rk),
														rank_borda=st(rkc), top1_borda=sum(x == 0 for x in rkc), top10_borda=sum(x < 10 for x in rkc),
														n_borda=loc_es[0]["n_compat"]),
						 BE_sozinha=loc_be, BE_sozinha_resumo=dict(rank_3008=st(rb), top1=sum(x == 0 for x in rb), top10=sum(x < 10 for x in rb)),
						 pares_aceites=loc_acc, score="RMS ΔE (filter2D) de a em X + b na gémea de X, mínimo em ±2 px e nas 4 rotações globais"))
	R["segundos"] = r3(time.time() - t0)
	R["log"] = LOG
	jp = os.path.join(OUT, "results.json")
	Jr = json.load(open(jp, encoding="utf-8"))
	Jr["ereal2"] = er.clean(R)
	json.dump(Jr, open(jp, "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=lambda o: o.item() if hasattr(o, "item") else str(o))
	log(f"total {time.time() - t0:.0f} s")


if __name__ == "__main__":
	main()
