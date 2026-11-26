"""D2 (2026-11-26): de onde vem a área da aresta do Tiago que fica fora do índice guardado (4.1 c).

Para cada contorno manual ativo com aresta (``aresta_px``), na janela do editor (``origem``/``tamanho`` da linha):

* ``E`` = aresta (fillPoly de ``aresta_px``), ``I`` = índice guardado (``pieces/<scan>.npz``, ``contour_px``),
  ``A`` = contorno que a edição substituiu (``auto_contour_px``), ``R`` = máscara do índice no momento da gravação
  (``mascara_rle``); ``O = E & ~I`` (a aresta fora do índice).
* Profundidade de cada píxel de ``O`` (distância a ``I``, px): ≤ 1 px = fronteira de 1 píxel (convenção de
  rasterização); > 3 px (0,25 mm) = perda de aresta a sério.
* Repete a derivação do servidor (``strokes.resolver(..., normalizar_indice=True)`` sobre ``A`` com os traços, o
  solver e os parâmetros gravados) para obter a região de influência dos traços, os ganhos descartados (<
  ``GANHO_MIN_MM2``) e a aresta/índice recalculados (reprodução: iguais aos gravados?). Cada píxel de ``O`` cai numa
  causa: (1) fora da influência e ``I == A`` ali: a convenção do índice («automático bit a bit fora das regiões
  ganhas»); (2) dentro da influência, ganho descartado por ser < 2 mm²; (3) dentro da influência, o resto (limpeza
  0,3 mm, traços de sombra ignorados, bordo da influência).
* Imagem de prova por peça em ``--out`` (zoom 8× nas maiores zonas de ``O``).

Uso: ``.venv/Scripts/python.exe tools/diagnostico/verify/d2_aresta.py [--project projects/alpes]
[--out docs/diagnostico/verify/D2]``. Corre sobre uma cópia (``tools.verify.ambiente.copiar_projeto``)."""
import argparse
import json
import os
import sys

import cv2
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO)

from tools.verify import ambiente as AMB  # noqa: E402

ZOOM = 8
JAN = 28          # meia janela (px do scan) de cada zoom


def _fill(poly, shape, org):
	m = np.zeros(shape, np.uint8)
	cv2.fillPoly(m, [np.round(np.asarray(poly, float).reshape(-1, 2) - org).astype(np.int32).reshape(-1, 1, 2)], 1)
	return m > 0


def medir_peca(pr, pid, o, rgb_cache):
	from src import overrides as OV, strokes as ST
	p = pr.piece(pid)
	sid = o["scan_id"]
	rgb = rgb_cache.get(sid)
	if rgb is None:
		rgb = rgb_cache[sid] = OV.load_scan_rgb(pr, sid)
	mm = OV._mmpp(pr, sid)
	x0, y0 = o["origem"]
	w, h = o["tamanho"]
	org = np.array([x0, y0], float)
	crop = np.ascontiguousarray(rgb[y0:y0 + h, x0:x0 + w])
	with np.load(pr.p("pieces", f"{p.scan_id}.npz"), allow_pickle=False) as z:
		guardado = z[f"{pid}__contour_px"]
	E = _fill(o["aresta_px"], (h, w), org)
	I = _fill(guardado, (h, w), org)
	A = _fill(o["auto_contour_px"], (h, w), org)
	Rm = ST.rle_decode(o["mascara_rle"]) if o.get("mascara_rle") else None
	O = E & ~I
	px2 = mm * mm
	dI = cv2.distanceTransform((~I).astype(np.uint8), cv2.DIST_L2, 5)
	prof = dI[O]
	# derivação do servidor repetida (mesmos traços, solver, parâmetros; auto = o contorno substituído)
	sol = o["solver"]["nome"]
	params = o["solver"]["params"]
	tr = o.get("tracos") or []
	delta = ST.delta_peca(crop, A, mm, sol, params, None)
	r = ST.resolver(crop, A, tr, mm, solver=sol, params=params, bg_lab=None, normalizar_indice=True, delta=delta)
	infl = r["influencia"]
	raw = r["mask_bruta"]
	gain = raw & ~A & infl
	drop = np.zeros_like(gain)
	if gain.any():
		n, cc, st, _ = cv2.connectedComponentsWithStats(gain.astype(np.uint8), connectivity=8)
		small = np.zeros(n, bool)
		small[1:] = st[1:, cv2.CC_STAT_AREA] * px2 < ST.GANHO_MIN_MM2
		drop = small[cc] & gain
	c1 = O & ~infl
	c1_auto = c1 & (I == A)
	c2 = O & infl & drop
	c3 = O & infl & ~drop
	E_rec, I_rec = r["mask_aresta"], r["mask"]
	n_cc, cc_o, st_o, _ = cv2.connectedComponentsWithStats(O.astype(np.uint8), connectivity=8)
	comps = []
	for k in range(1, n_cc):
		mk = cc_o == k
		comps.append({"area_mm2": round(float(mk.sum()) * px2, 3), "prof_max_mm": round(float(dI[mk].max()) * mm, 3),
					  "x": int(st_o[k, 0] + st_o[k, 2] // 2), "y": int(st_o[k, 1] + st_o[k, 3] // 2),
					  "fora_influencia": bool((mk & ~infl).sum() > (mk & infl).sum())})
	comps.sort(key=lambda c: -c["area_mm2"])
	res = {
		"peca": pid, "linha_t": o.get("t"), "derivado_de": o.get("derivado_de"), "motivo": o.get("motivo"),
		"O_mm2": round(float(O.sum()) * px2, 3), "O_px": int(O.sum()),
		"prof_px": {"<=1": int((prof <= 1.0).sum()), "1-2": int(((prof > 1.0) & (prof <= 2.0)).sum()),
					"2-3": int(((prof > 2.0) & (prof <= 3.0)).sum()), ">3": int((prof > 3.0).sum())},
		"prof_max_mm": round(float(prof.max()) * mm, 3) if prof.size else 0.0,
		"O_dentro_de_A_px": int((O & A).sum()), "O_fora_de_A_px": int((O & ~A).sum()),
		"causa_px": {"fora_influencia": int(c1.sum()), "fora_influencia_e_I_igual_A": int(c1_auto.sum()),
					 "ganho_descartado": int(c2.sum()), "dentro_influencia_resto": int(c3.sum())},
		"I_igual_A_fora_influencia": bool(np.array_equal(I & ~infl, A & ~infl)),
		"reproducao": {"E_recalc_diff_px": int((E_rec ^ E).sum()), "I_recalc_diff_px": int((I_rec ^ I).sum()),
					   "I_vs_mascara_rle_diff_px": None if Rm is None or Rm.shape != I.shape else int((Rm ^ I).sum()),
					   "influencia_px": int(infl.sum()), "tracos": len(tr), "tracos_ignorados": r["tracos_ignorados"]},
		"componentes": comps[:6], "n_componentes": len(comps),
	}
	return res, (crop, E, I, A, infl, O)


def imagem(res, masks, fp):
	crop, E, I, A, infl, O = masks
	bgr = cv2.cvtColor(crop, cv2.COLOR_RGB2BGR)

	def contorno(m):
		cs, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
		return cs
	tiles = []
	for c in res["componentes"][:4]:
		x, y = c["x"], c["y"]
		H, W = O.shape
		xa, ya = max(0, x - JAN), max(0, y - JAN)
		xb, yb = min(W, x + JAN), min(H, y + JAN)
		sub = cv2.resize(bgr[ya:yb, xa:xb], None, fx=ZOOM, fy=ZOOM, interpolation=cv2.INTER_NEAREST)
		ov = sub.copy()
		om = cv2.resize(O[ya:yb, xa:xb].astype(np.uint8), None, fx=ZOOM, fy=ZOOM, interpolation=cv2.INTER_NEAREST) > 0
		ov[om] = (0, 0, 255)
		sub = cv2.addWeighted(ov, 0.55, sub, 0.45, 0)
		for m, col in ((A, (255, 255, 255)), (infl, (0, 220, 255)), (I, (255, 200, 0)), (E, (0, 140, 255))):
			mm_ = cv2.resize(m[ya:yb, xa:xb].astype(np.uint8), None, fx=ZOOM, fy=ZOOM, interpolation=cv2.INTER_NEAREST)
			cv2.drawContours(sub, contorno(mm_), -1, col, 2)
		t = f"{c['area_mm2']} mm2, prof. max {c['prof_max_mm']} mm, {'fora' if c['fora_influencia'] else 'dentro'} da influencia"
		cv2.putText(sub, t, (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
		cv2.putText(sub, t, (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
		tiles.append(sub)
	# vista geral reduzida à mesma altura
	ger = bgr.copy()
	ger[O] = (0, 0, 255)
	cv2.drawContours(ger, contorno(E), -1, (0, 140, 255), 1)
	cv2.drawContours(ger, contorno(I), -1, (255, 200, 0), 1)
	side = 2 * JAN * ZOOM
	s = side / max(ger.shape[:2])
	ger = cv2.resize(ger, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
	pad = np.full((side, side, 3), 255, np.uint8)
	pad[:ger.shape[0], :ger.shape[1]] = ger
	tiles = [pad] + tiles
	tiles = [cv2.copyMakeBorder(t, 0, side - t.shape[0], 0, side - t.shape[1], cv2.BORDER_CONSTANT, value=(255, 255, 255))
			 for t in tiles]
	corpo = np.hstack(tiles)
	cab = np.full((54, corpo.shape[1], 3), 255, np.uint8)
	l1 = (f"{res['peca']}: aresta fora do indice {res['O_mm2']} mm2 ({res['O_px']} px), prof. max {res['prof_max_mm']} mm;"
		  f" causas (px): {res['causa_px']}")
	l2 = "laranja = aresta do Tiago, azul-claro = indice guardado, branco = contorno substituido, amarelo = influencia dos tracos, vermelho = aresta fora do indice"
	cv2.putText(cab, l1, (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
	cv2.putText(cab, l2, (6, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
	cv2.imwrite(fp, np.vstack([cab, corpo]), [cv2.IMWRITE_JPEG_QUALITY, 88])


def main(argv=None):
	from src.state import Project
	from src import overrides as OV
	ap = argparse.ArgumentParser()
	ap.add_argument("--project", default=os.path.join(REPO, "projects", "alpes"))
	ap.add_argument("--out", default=os.path.join(REPO, "docs", "diagnostico", "verify", "D2"))
	a = ap.parse_args(argv)
	os.makedirs(a.out, exist_ok=True)
	raiz, copia = AMB.copiar_projeto(a.project)
	try:
		pr = Project.open(copia)
		cache, todos = {}, []
		for pid, o in sorted(OV.latest_overrides(pr).items()):
			if not o.get("aresta_px"):
				continue
			res, masks = medir_peca(pr, pid, o, cache)
			if res["O_px"]:
				imagem(res, masks, os.path.join(a.out, f"{pid}.jpg"))
				res["imagem"] = os.path.relpath(os.path.join(a.out, f"{pid}.jpg"), REPO).replace(os.sep, "/")
			todos.append(res)
			print(json.dumps({k: res[k] for k in ("peca", "O_mm2", "prof_px", "prof_max_mm", "causa_px", "reproducao",
												   "O_fora_de_A_px")}, ensure_ascii=False))
		with open(os.path.join(a.out, "d2.json"), "w", encoding="utf-8", newline="\n") as f:
			json.dump(todos, f, ensure_ascii=False, indent=1)
	finally:
		AMB.apagar_copia(raiz)


if __name__ == "__main__":
	main()
