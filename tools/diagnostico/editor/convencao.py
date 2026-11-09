"""Convenção da silhueta: índice (``segment_scan``, com sombra/penumbra) contra o editor por traços (só leitura).

Mede, por peça, o desvio assinado entre a fronteira do resultado do solver do editor e a do contorno
automático do índice (positivo = fora do automático, negativo = dentro), em mm:

* nos registos de ``overrides.jsonl``: solver com 0 traços (``δ0``) e com os traços gravados (o contorno
  gravado, reproduzido bit a bit), contra o ``auto_contour_px`` do registo (a segmentação);
  decomposição do desvio gravado em parte **uniforme** (mediana) e **local** (resíduo): «correção real»
  = componente da diferença entre o gravado e o automático deslocado pela mediana com profundidade
  > ``--prof-mm`` (0,5) e área >= ``--area-mm2`` (3);
* numa amostra ao acaso de peças sem contorno manual, por zona do perfil: ``δ0`` apenas (o δ depende da
  cor da peça?);
* em P0651/P0657 (S0020) contra as máscaras do Photoshop (``R0011_R0012_manual``): índice vs GT,
  solver vs GT, solver vs índice;
* ``--lados`` (ronda 10): por lado no referencial do scanner (E / S / N / W pela normal exterior; a sombra
  cai a W e a S), o desvio assinado mediano de S0 (solver sem traços) contra o índice, da aresta pintada
  (A2, ``aresta_px``) contra S0 e, com GT, de índice / S0 / aresta contra a GT (+ IoU), para as peças com
  aresta pintada e as que têm GT; ``--gt DIR`` junta as máscaras ``DIR/P####.png`` (PNG com alfa na grelha
  do scan inteiro, como R0011/R0012) às duas de origem; ``--pecas`` restringe a lista.

Nada é escrito no projeto. Uso::

	python tools/diagnostico/editor/convencao.py --project projects/alpes \
		--json docs/diagnostico/editor/convencao.json --fig docs/diagnostico/editor/CONVENCAO_17.jpg
"""

import argparse
import json
import os
import sys
from typing import Optional

import cv2
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO)

from src import maskcmp as MC  # noqa: E402
from src import overrides as OV  # noqa: E402
from src import render  # noqa: E402
from src import strokes as ST  # noqa: E402
from src.state import Project  # noqa: E402

GT_DIR = os.path.join(REPO, "docs", "diagnostico", "reports", "R0011_R0012_manual")
GT = (("P0651", "manual_A_photoshop.png"), ("P0657", "manual_B_photoshop.png"))


# ---------------------------------------------------------------- medidas puras
def signed_offset(ref: np.ndarray, cand: np.ndarray, mm_per_px: float) -> np.ndarray:
	"""Desvio assinado (mm) de cada píxel da fronteira de ``cand`` à fronteira de ``ref``: > 0 fora de ``ref``."""
	b = MC.boundary(cand)
	dout = cv2.distanceTransform((~ref).astype(np.uint8), cv2.DIST_L2, 5)
	din = cv2.distanceTransform(ref.astype(np.uint8), cv2.DIST_L2, 5)
	return np.where(ref, -din, dout)[b] * mm_per_px


def stats(s: np.ndarray) -> dict:
	return {"mediana": float(np.median(s)), "media": float(np.mean(s)), "p5": float(np.percentile(s, 5)),
			"p95": float(np.percentile(s, 95)), "abs_media": float(np.mean(np.abs(s)))}


def shift_mask(mask: np.ndarray, delta_mm: float, mm_per_px: float) -> np.ndarray:
	"""``mask`` deslocada ``delta_mm`` ao longo da normal (> 0 dilata, < 0 erode), pela transformada de distância."""
	d = delta_mm / mm_per_px
	if abs(d) < 1e-6:
		return mask.copy()
	if d > 0:
		return cv2.distanceTransform((~mask).astype(np.uint8), cv2.DIST_L2, 5) <= d
	return cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 5) > -d


def local_corrections(manual: np.ndarray, auto: np.ndarray, delta_mm: float, mm_per_px: float,
					  prof_mm: float, area_mm2: float) -> list:
	"""Componentes de ``manual xor auto_deslocado(delta)`` com profundidade > ``prof_mm`` e área >= ``area_mm2``."""
	ref = shift_mask(auto, delta_mm, mm_per_px)
	out = []
	for kind, region in (("a_mais", manual & ~ref), ("em_falta", ref & ~manual)):
		if not region.any():
			continue
		n, cc, st, _ = cv2.connectedComponentsWithStats(region.astype(np.uint8), connectivity=8)
		dist = cv2.distanceTransform(region.astype(np.uint8), cv2.DIST_L2, 5)  # distância à fronteira da região
		for i in range(1, n):
			comp = cc == i
			area = float(st[i, cv2.CC_STAT_AREA]) * mm_per_px * mm_per_px
			depth = float(dist[comp].max()) * 2 * mm_per_px          # espessura ≈ 2 × raio inscrito
			if depth > prof_mm and area >= area_mm2:
				ys, xs = np.nonzero(comp)
				out.append({"tipo": kind, "area_mm2": round(area, 2), "profundidade_mm": round(depth, 2),
							"bbox_px": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]})
	return out


# ---------------------------------------------------------------- dados
class Ctx:
	def __init__(self, project):
		self.pr = project
		self._scan = (None, None)

	def scan(self, sid):
		if self._scan[0] != sid:
			self._scan = (sid, OV.load_scan_rgb(self.pr, sid))
		return self._scan[1]

	def mmpp(self, sid):
		return render._scan_mmpp(self.pr, sid)


def measure_override(ctx: Ctx, rec: dict, prof_mm: float, area_mm2: float) -> dict:
	sid, pid = rec["scan_id"], rec["piece"]
	x0, y0 = rec["origem"]
	w, h = rec["tamanho"]
	mmpp = ctx.mmpp(sid)
	rgb = ctx.scan(sid)[y0:y0 + h, x0:x0 + w]
	auto = MC.fill_contour(np.asarray(rec["auto_contour_px"], float) - [x0, y0], (h, w))
	manual = MC.fill_contour(np.asarray(rec["contour_px"], float) - [x0, y0], (h, w))
	z = ST.resolver(rgb, auto, [], mmpp)
	tr, err = ST.validar_tracos(rec.get("tracos"), w, h)
	rep = ST.resolver(rgb, auto, tr, mmpp) if tr else None
	s0 = signed_offset(auto, z["mask"], mmpp)
	sm = signed_offset(auto, manual, mmpp)
	med = float(np.median(sm))
	p = ctx.pr.piece(pid)
	marcas = {}
	for t in rec.get("tracos") or []:
		k = f"{t['ferramenta']}/{t['marca']}"
		marcas[k] = marcas.get(k, 0) + 1
	return {
		"piece": pid, "scan_id": sid, "celula": list(p.celula) if p.celula else None, "t": rec["t"],
		"zona": ctx.pr.profile.zone_of(*p.celula) if p.celula and hasattr(ctx.pr.profile, "zone_of") else None,
		"marcas": marcas,
		"auto_mm2": round(float(auto.sum()) * mmpp * mmpp, 1),
		"zero_tracos": {"desvio": stats(s0), **{k: round(v, 2) for k, v in MC.mask_metrics(auto, z["mask"], mmpp).items()
												 if k in ("iou", "missing_mm2", "excess_mm2", "d_mean", "d_p95")}},
		"gravado": {"desvio": stats(sm), **{k: round(v, 2) for k, v in MC.mask_metrics(auto, manual, mmpp).items()
											if k in ("iou", "missing_mm2", "excess_mm2", "d_mean", "d_p95")}},
		"reproducao_iou": None if rep is None else round(float(MC.mask_metrics(manual, rep["mask"], mmpp)["iou"]), 4),
		"uniforme_mm": round(med, 3),
		"residuo": stats(sm - med),
		"correcoes_locais": local_corrections(manual, auto, med, mmpp, prof_mm, area_mm2),
		"_masks": (rgb, auto, z["mask"], manual),
	}


def sample_pieces(ctx: Ctx, n_per_zone: int, seed: int) -> list:
	"""Até ``n_per_zone`` peças colocadas por zona, sem contorno manual, com recorte no scan."""
	pr = ctx.pr
	rng = np.random.default_rng(seed)
	by_zone = {}
	for p in pr.pieces.values():
		if p.estado != "colocada" or p.celula is None or OV.is_manual(p):
			continue
		z = pr.profile.zone_of(*p.celula) if hasattr(pr.profile, "zone_of") else "?"
		by_zone.setdefault(z or "?", []).append(p.id)
	rows = []
	for z, ids in sorted(by_zone.items()):
		ids = sorted(ids)
		pick = rng.choice(ids, size=min(n_per_zone, len(ids)), replace=False)
		for pid in sorted(pick):
			p = pr.piece(pid)
			try:
				x0, y0, x1, y1, _ = OV.crop_window(pr, pid)
			except FileNotFoundError:
				continue
			c = pr.contour_px(pid)
			if c is None:
				continue
			mmpp = ctx.mmpp(p.scan_id)
			rgb = ctx.scan(p.scan_id)[y0:y1, x0:x1]
			auto = MC.fill_contour(np.asarray(c, float) - [x0, y0], (y1 - y0, x1 - x0))
			z0 = ST.resolver(rgb, auto, [], mmpp)
			if "error" in z0:
				continue
			s0 = signed_offset(auto, z0["mask"], mmpp)
			m = MC.mask_metrics(auto, z0["mask"], mmpp)
			rows.append({"piece": pid, "zona": z, "celula": list(p.celula), "scan_id": p.scan_id,
						 "desvio": stats(s0), "missing_mm2": round(m["missing_mm2"], 1), "excess_mm2": round(m["excess_mm2"], 1)})
	return rows


def measure_gt(ctx: Ctx) -> list:
	out = []
	for pid, fn in GT:
		fp = os.path.join(GT_DIR, fn)
		if not os.path.exists(fp) or pid not in ctx.pr.pieces:
			continue
		p = ctx.pr.piece(pid)
		a = cv2.imread(fp, cv2.IMREAD_UNCHANGED)
		gt_full = a[..., 3] > 127
		n, cc, st, _ = cv2.connectedComponentsWithStats(gt_full.astype(np.uint8), connectivity=8)
		gt_full = cc == 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
		x0, y0, x1, y1, _ = OV.crop_window(ctx.pr, pid)
		w, h = x1 - x0, y1 - y0
		mmpp = ctx.mmpp(p.scan_id)
		rgb = ctx.scan(p.scan_id)[y0:y1, x0:x1]
		idx = MC.fill_contour(np.asarray(ctx.pr.contour_px(pid), float) - [x0, y0], (h, w))
		gt = gt_full[y0:y1, x0:x1]
		z = ST.resolver(rgb, idx, [], mmpp)
		pick = lambda m: {k: round(v, 2) for k, v in m.items() if k in ("iou", "missing_mm2", "excess_mm2", "d_mean", "d_p95")}
		out.append({"piece": pid, "celula": list(p.celula) if p.celula else None,
					"indice_vs_gt": {**pick(MC.mask_metrics(gt, idx, mmpp)), "desvio": stats(signed_offset(gt, idx, mmpp))},
					"solver0_vs_gt": {**pick(MC.mask_metrics(gt, z["mask"], mmpp)), "desvio": stats(signed_offset(gt, z["mask"], mmpp))},
					"solver0_vs_indice": {**pick(MC.mask_metrics(idx, z["mask"], mmpp)), "desvio": stats(signed_offset(idx, z["mask"], mmpp))}})
	return out


# ---------------------------------------------------------------- por lado (referencial do scanner)
LADOS = ("E", "S", "N", "W")


def normal_sides(mask: np.ndarray, sigma_px: float = 3.0) -> np.ndarray:
	"""Lado (0..3 = E, S, N, W; ``LADOS``) de cada píxel pela direção da normal exterior de ``mask`` suavizada,
	no referencial do scanner (x para a direita, y para baixo: a sombra cai a W e a S)."""
	g = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), sigma_px)
	gy, gx = np.gradient(g)
	ang = np.degrees(np.arctan2(-gy, -gx))                  # normal exterior = -gradiente; y para baixo
	side = np.full(mask.shape, 3, np.int8)                  # W (|ang| >= 135)
	side[(ang >= -45) & (ang < 45)] = 0                     # E
	side[(ang >= 45) & (ang < 135)] = 1                     # S
	side[(ang >= -135) & (ang < -45)] = 2                   # N
	return side


def side_offsets(ref: np.ndarray, cand: np.ndarray, mm_per_px: float) -> dict:
	"""``{lado: {mediana, p95_abs, n}}`` do desvio assinado (mm; + = ``cand`` fora de ``ref``) da fronteira de ``cand``,
	com o lado dado pela normal de ``ref`` (:func:`normal_sides`)."""
	b = MC.boundary(cand)
	dout = cv2.distanceTransform((~ref).astype(np.uint8), cv2.DIST_L2, 5)
	din = cv2.distanceTransform(ref.astype(np.uint8), cv2.DIST_L2, 5)
	s = np.where(ref, -din, dout)[b] * mm_per_px
	sd = normal_sides(ref)[b]
	out = {}
	for k, nome in enumerate(LADOS):
		v = s[sd == k]
		out[nome] = {"mediana": round(float(np.median(v)), 3) if len(v) else None,
					 "p95_abs": round(float(np.percentile(np.abs(v), 95)), 3) if len(v) else None, "n": int(len(v))}
	return out


def fmt_lados(d: dict) -> str:
	return " / ".join("—" if d[k]["mediana"] is None else f"{d[k]['mediana']:+.2f}" for k in LADOS)


def load_gt_mask(fp: str) -> np.ndarray:
	"""Máscara GT (PNG com alfa, na grelha de píxeis do scan inteiro): a maior componente de alfa > 127."""
	a = cv2.imread(fp, cv2.IMREAD_UNCHANGED)
	if a is None or a.ndim != 3 or a.shape[2] != 4:
		raise ValueError(f"{fp}: esperava um PNG RGBA (alfa = peça)")
	m = a[..., 3] > 127
	n, cc, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
	if n <= 1:
		raise ValueError(f"{fp}: alfa vazio")
	return cc == 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))


def gt_files(gt_dir: Optional[str]) -> dict:
	"""``{peça: ficheiro}``: P0651/P0657 (R0011/R0012) e, com ``gt_dir``, cada ``P####.png`` dessa pasta."""
	out = {pid: os.path.join(GT_DIR, fn) for pid, fn in GT if os.path.exists(os.path.join(GT_DIR, fn))}
	if gt_dir and os.path.isdir(gt_dir):
		for fn in sorted(os.listdir(gt_dir)):
			stem, ext = os.path.splitext(fn)
			if ext.lower() == ".png" and len(stem) == 5 and stem[0] == "P" and stem[1:].isdigit():
				out[stem] = os.path.join(gt_dir, fn)
	return out


def measure_sides(ctx: "Ctx", pid: str, gt_fp: Optional[str] = None) -> dict:
	"""Por lado (E/S/N/W, scanner), na janela do editor da peça: S0 (solver sem traços) contra o índice; e, quando
	a peça tem aresta pintada (A2), a aresta contra S0 e o índice gravado contra o automático; com GT, cada um
	contra a GT (+ IoU)."""
	pr = ctx.pr
	p = pr.piece(pid)
	x0, y0, x1, y1, _ = OV.crop_window(pr, pid)
	w, h = x1 - x0, y1 - y0
	mmpp = ctx.mmpp(p.scan_id)
	rgb = ctx.scan(p.scan_id)[y0:y1, x0:x1]
	org = np.array([x0, y0], float)
	idx = MC.fill_contour(np.asarray(pr.contour_px(pid), float) - org, (h, w))
	s0 = ST.resolver(rgb, idx, [], mmpp)["mask"]
	ar = OV.aresta_px(pr, pid)
	aresta = None if ar is None else MC.fill_contour(ar - org, (h, w))
	out = {"piece": pid, "celula": list(p.celula) if p.celula else None,
		   "zona": pr.profile.zone_of(*p.celula) if p.celula and hasattr(pr.profile, "zone_of") else None,
		   "s0_menos_indice": side_offsets(idx, s0, mmpp)}
	if aresta is not None:
		out["aresta_menos_s0"] = side_offsets(s0, aresta, mmpp)
	if gt_fp:
		gt = load_gt_mask(gt_fp)[y0:y1, x0:x1]
		out["gt"] = os.path.relpath(gt_fp, REPO)
		for nome, m in (("indice", idx), ("s0", s0), ("aresta", aresta)):
			if m is None:
				continue
			out[f"{nome}_menos_gt"] = side_offsets(gt, m, mmpp)
			out[f"{nome}_iou_gt"] = round(float(MC.mask_metrics(gt, m, mmpp)["iou"]), 4)
	out["_masks"] = {"rgb": rgb, "indice": idx, "s0": s0, "aresta": aresta,
					 "gt": None if not gt_fp else load_gt_mask(gt_fp)[y0:y1, x0:x1]}
	return out


# ---------------------------------------------------------------- figura
def figure(rows: list, path: str, cols: int = 3) -> None:
	tiles = []
	for r in rows:
		rgb, auto, s0, man = r["_masks"]
		img = rgb.copy()
		for m, col in ((auto, (255, 0, 0)), (s0, (255, 255, 0)), (man, (255, 0, 255))):
			c, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
			cv2.drawContours(img, c, -1, col, 1)
		for lc in r["correcoes_locais"]:
			x0, y0, x1, y1 = lc["bbox_px"]
			cv2.rectangle(img, (x0 - 2, y0 - 2), (x1 + 2, y1 + 2), (0, 255, 255), 1)
		cv2.putText(img, f"{r['piece']} u={r['uniforme_mm']:+.2f} d0={r['zero_tracos']['desvio']['mediana']:+.2f}",
					(4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)
		tiles.append(img)
	if not tiles:
		return
	H = max(t.shape[0] for t in tiles)
	W = max(t.shape[1] for t in tiles)
	pad = [cv2.copyMakeBorder(t, 0, H - t.shape[0], 0, W - t.shape[1], cv2.BORDER_CONSTANT, value=(30, 30, 30)) for t in tiles]
	while len(pad) % cols:
		pad.append(np.full((H, W, 3), 30, np.uint8))
	grid = np.vstack([np.hstack(pad[i:i + cols]) for i in range(0, len(pad), cols)])
	os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
	cv2.imwrite(path, grid[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, 88])


# ---------------------------------------------------------------- relatório
def _d(s):
	return f"{s['mediana']:+.2f} ({s['p5']:+.2f}, {s['p95']:+.2f})"


def main(argv=None) -> int:
	ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
	ap.add_argument("--project", required=True)
	ap.add_argument("--json", default=None)
	ap.add_argument("--fig", default=None)
	ap.add_argument("--amostra", type=int, default=40, help="peças ao acaso por zona (0 = sem amostra)")
	ap.add_argument("--seed", type=int, default=9)
	ap.add_argument("--prof-mm", type=float, default=0.5)
	ap.add_argument("--area-mm2", type=float, default=3.0)
	ap.add_argument("--lados", action="store_true", help="só a medição por lado (peças com aresta pintada e com GT)")
	ap.add_argument("--gt", default=None, help="pasta com P####.png (máscaras GT do Photoshop, scan inteiro)")
	ap.add_argument("--pecas", default=None, help="lista de peças separadas por vírgulas (com --lados)")
	a = ap.parse_args(argv)
	pr = Project.open(a.project)
	ctx = Ctx(pr)
	if a.lados:
		return main_lados(ctx, a)
	recs = OV.read_overrides(pr)
	rows = [measure_override(ctx, r, a.prof_mm, a.area_mm2) for r in recs if r.get("auto_contour_px") and r.get("origem")]
	print(f"## Registos manuais ({len(rows)}): desvio assinado da fronteira ao automático, mm (mediana (p5, p95)); + = fora")
	print("| peça | célula | zona | marcas | 0 traços | gravado | uniforme | resíduo p5..p95 | reprod. | correções locais |")
	print("|---|---|---|---|---|---|---|---|---|---|")
	for r in rows:
		lc = "; ".join(f"{c['tipo']} {c['area_mm2']} mm² prof {c['profundidade_mm']}" for c in r["correcoes_locais"]) or "nenhuma"
		print(f"| {r['piece']} | {r['celula']} | {r['zona']} | {r['marcas']} | {_d(r['zero_tracos']['desvio'])} | "
			  f"{_d(r['gravado']['desvio'])} | {r['uniforme_mm']:+.2f} | {r['residuo']['p5']:+.2f}..{r['residuo']['p95']:+.2f} | "
			  f"{r['reproducao_iou']} | {lc} |")
	if rows:
		u = np.array([r["uniforme_mm"] for r in rows])
		d0 = np.array([r["zero_tracos"]["desvio"]["mediana"] for r in rows])
		print(f"\nuniforme (gravado): mediana {np.median(u):+.2f}, min {u.min():+.2f}, max {u.max():+.2f}; "
			  f"δ0 (0 traços): mediana {np.median(d0):+.2f}, min {d0.min():+.2f}, max {d0.max():+.2f}; "
			  f"com correções locais: {sum(1 for r in rows if r['correcoes_locais'])}/{len(rows)}")
	sample = sample_pieces(ctx, a.amostra, a.seed) if a.amostra > 0 else []
	if sample:
		print(f"\n## Amostra sem contorno manual ({len(sample)}): δ0 por zona")
		print("| zona | n | δ0 mediana das medianas | min | max | falta mm² mediana |")
		print("|---|---|---|---|---|---|")
		for z in sorted({s["zona"] for s in sample}, key=str):
			ss = [s for s in sample if s["zona"] == z]
			m = np.array([s["desvio"]["mediana"] for s in ss])
			print(f"| {z} | {len(ss)} | {np.median(m):+.2f} | {m.min():+.2f} | {m.max():+.2f} | {np.median([s['missing_mm2'] for s in ss]):.1f} |")
	gt = measure_gt(ctx)
	if gt:
		print("\n## P0651/P0657 contra a GT do Photoshop")
		print("| peça | índice vs GT: IoU / a mais / desvio | solver 0 traços vs GT | solver 0 traços vs índice |")
		print("|---|---|---|---|")
		for g in gt:
			f = lambda m: f"{m['iou']:.3f} / {m['excess_mm2']:.1f} / {_d(m['desvio'])}"
			print(f"| {g['piece']} {g['celula']} | {f(g['indice_vs_gt'])} | {f(g['solver0_vs_gt'])} | {f(g['solver0_vs_indice'])} |")
	if a.fig and rows:
		figure(rows, a.fig)
		print(f"\nfigura: {a.fig}")
	if a.json:
		out = {"registos": [{k: v for k, v in r.items() if k != "_masks"} for r in rows], "amostra": sample, "gt": gt,
			   "parametros": {"prof_mm": a.prof_mm, "area_mm2": a.area_mm2, "amostra": a.amostra, "seed": a.seed}}
		os.makedirs(os.path.dirname(os.path.abspath(a.json)), exist_ok=True)
		with open(a.json, "w", encoding="utf-8") as f:
			json.dump(out, f, ensure_ascii=False, indent=1)
		print(f"json: {a.json}")
	return 0


def main_lados(ctx: "Ctx", a) -> int:
	pr = ctx.pr
	gts = gt_files(a.gt)
	pids = sorted(set(OV.latest_arestas(pr)) | {g for g in gts if g in pr.pieces})
	if a.pecas:
		want = [x.strip() for x in a.pecas.split(",") if x.strip()]
		pids = [x for x in want if x in pr.pieces]
	rows = []
	for pid in pids:
		try:
			rows.append(measure_sides(ctx, pid, gts.get(pid)))
		except (FileNotFoundError, ValueError) as e:
			print(f"{pid}: {e}")
	print("## Por lado (E / S / N / W, scanner; desvio assinado mediano, mm, + = fora da referência)")
	print("| peça | célula | zona | S0 − índice | aresta − S0 | índice − GT | S0 − GT (IoU) | aresta − GT (IoU) | GT |")
	print("|---|---|---|---|---|---|---|---|---|")
	for r in rows:
		f = lambda k: fmt_lados(r[k]) if k in r else "—"
		iou = lambda k: f" ({r[k]:.3f})" if k in r else ""
		print(f"| {r['piece']} | {r['celula']} | {r['zona']} | {f('s0_menos_indice')} | {f('aresta_menos_s0')} | "
			  f"{f('indice_menos_gt')} | {f('s0_menos_gt')}{iou('s0_iou_gt')} | {f('aresta_menos_gt')}{iou('aresta_iou_gt')} | "
			  f"{r.get('gt', '—')} |")
	if a.json:
		os.makedirs(os.path.dirname(os.path.abspath(a.json)), exist_ok=True)
		with open(a.json, "w", encoding="utf-8") as fh:
			json.dump({"lados": [{k: v for k, v in r.items() if k != "_masks"} for r in rows], "gt": {k: os.path.relpath(v, REPO) for k, v in gts.items()}},
					  fh, ensure_ascii=False, indent=1)
		print(f"json: {a.json}")
	return 0


if __name__ == "__main__":
	sys.exit(main())
