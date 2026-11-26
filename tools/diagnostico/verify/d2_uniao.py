"""D2, opção A (2026-11-26): efeito de ler o índice de um contorno manual como ``contour_px`` ∪ aresta.

Numa cópia de ``projects/alpes`` (``tools.verify.ambiente.copiar_projeto``, feita e apagada com ``guarda.py``):

1. antes: para cada contorno manual ativo com aresta (``aresta_px``), o índice guardado (``pieces/<scan>.npz``),
   os píxeis da aresta fora dele, a área e ``shape.analyse`` (classe, cordas, cantos); ``consistency.evaluate``;
2. o arranque do servidor na cópia (``render.stale_assets`` + ``render.rebuild_stale``, via
   ``tools.verify.invariantes.arranque``): peças desatualizadas, motivos, eventos escritos (só na cópia);
3. depois: o mesmo que em 1, com Δárea (mm²), Δcordas (mm), deslocamento máximo dos cantos (mm) e as suspeitas;
4. imagens antes/depois ampliadas 8× nas maiores zonas de aresta que estava fora do índice, em ``--out`` (as
   ``--imagens`` peças com mais píxeis fora e as 2 cujos cantos mais se deslocam), com a peça inteira e os cantos.

Uso: ``.venv/Scripts/python.exe tools/diagnostico/verify/d2_uniao.py [--project projects/alpes]
[--out docs/diagnostico/verify/D2] [--imagens 3]``. Nunca escreve no projeto real."""
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
JAN = 24          # meia janela (px do scan) de cada zoom


def _fill(poly, shape, org):
	m = np.zeros(shape, np.uint8)
	cv2.fillPoly(m, [np.round(np.asarray(poly, float).reshape(-1, 2) - org).astype(np.int32).reshape(-1, 1, 2)], 1)
	return m > 0


def _estado(pr, rgb_cache):
	"""``{pid: {...}}`` dos contornos manuais com aresta, na janela da linha (``origem``/``tamanho``)."""
	from src import overrides as OV
	from src.shape import analyse
	out = {}
	for pid, o in sorted(OV.latest_overrides(pr).items()):
		if not o.get("aresta_px"):
			continue
		p = pr.piece(pid)
		sid = o["scan_id"]
		mm = OV._mmpp(pr, sid)
		x0, y0 = o["origem"]
		w, h = o["tamanho"]
		org = np.array([x0, y0], float)
		with np.load(pr.p("pieces", f"{p.scan_id}.npz"), allow_pickle=False) as z:
			cnt = z[f"{pid}__contour_px"].reshape(-1, 2)
		E, I = _fill(o["aresta_px"], (h, w), org), _fill(cnt, (h, w), org)
		sh = analyse(cnt.astype(float), mm)
		out[pid] = {"aresta_fora_px": int((E & ~I).sum()), "area_mm2": round(float(I.sum()) * mm * mm, 3),
					"cls": sh.cls, "cordas_mm": [round(float(s.chord_mm), 3) for s in sh.sides],
					"cantos_mm": [s.p0_mm.tolist() for s in sh.sides], "ok": bool(sh.ok),
					"_E": E, "_I": I, "_org": org, "_sid": sid, "_mm": mm, "_o": o}
	return out


def _suspeitas(pr):
	from src import consistency as CS, render
	pl = dict(render.load_placements(pr).get("placements") or {})
	ev = CS.evaluate(pr, pl)
	return sorted(f"{it['piece']}|{it['grau']}" for it in ev["items"])


def _zonas(O, n=3):
	k = cv2.dilate(O.astype(np.uint8), np.ones((9, 9), np.uint8))
	nn, cc, st, cen = cv2.connectedComponentsWithStats(k, connectivity=8)
	comps = sorted(range(1, nn), key=lambda i: -int((O & (cc == i)).sum()))
	return [(int(cen[i][0]), int(cen[i][1]), int((O & (cc == i)).sum())) for i in comps[:n]]


def imagem(pid, a, d, rgb, fp):
	"""1.ª linha: a peça inteira com os cantos antes (azul-claro) e depois (verde). Depois, antes | depois por zona:
	laranja = aresta, azul-claro = índice antes, verde = índice depois, vermelho = aresta fora do índice."""
	o, org = a["_o"], a["_org"]
	x0, y0 = o["origem"]
	w, h = o["tamanho"]
	bgr = cv2.cvtColor(np.ascontiguousarray(rgb[y0:y0 + h, x0:x0 + w]), cv2.COLOR_RGB2BGR)
	E, I0, I1 = a["_E"], a["_I"], d["_I"]

	def cs(m):
		return cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0]

	def painel(I, x, y, rot):
		xa, ya, xb, yb = max(0, x - JAN), max(0, y - JAN), min(w, x + JAN), min(h, y + JAN)
		up = lambda m: cv2.resize(m[ya:yb, xa:xb].astype(np.uint8), None, fx=ZOOM, fy=ZOOM, interpolation=cv2.INTER_NEAREST)
		sub = cv2.resize(bgr[ya:yb, xa:xb], None, fx=ZOOM, fy=ZOOM, interpolation=cv2.INTER_NEAREST)
		ov = sub.copy()
		ov[up(E & ~I) > 0] = (0, 0, 255)
		sub = cv2.addWeighted(ov, 0.6, sub, 0.4, 0)
		cv2.drawContours(sub, cs(up(I)), -1, (255, 200, 0) if I is I0 else (0, 200, 0), 2)
		cv2.drawContours(sub, cs(up(E)), -1, (0, 140, 255), 1)
		t = f"{rot}: aresta fora {int((E & ~I)[ya:yb, xa:xb].sum())} px"
		cv2.putText(sub, t, (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3, cv2.LINE_AA)
		cv2.putText(sub, t, (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
		side = 2 * JAN * ZOOM
		return cv2.copyMakeBorder(sub, 0, side - sub.shape[0], 0, side - sub.shape[1], cv2.BORDER_CONSTANT,
								  value=(255, 255, 255))
	def geral():
		"""A peça inteira (2×) com os cantos de ``shape.analyse``: azul-claro antes, verde depois."""
		z = 2
		g = cv2.resize(bgr, None, fx=z, fy=z, interpolation=cv2.INTER_NEAREST)
		cv2.drawContours(g, cs(cv2.resize(E.astype(np.uint8), None, fx=z, fy=z, interpolation=cv2.INTER_NEAREST)), -1, (0, 140, 255), 1)
		for st, col, r in ((a, (255, 200, 0), 9), (d, (0, 200, 0), 5)):
			for (cx, cy) in st["cantos_mm"]:
				p = (np.array([cx, cy]) / st["_mm"] - org) * z
				cv2.circle(g, (int(round(p[0])), int(round(p[1]))), r, col, 2)
		side = 2 * JAN * ZOOM
		s = min(1.0, side / max(g.shape[:2]))
		g = cv2.resize(g, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
		return cv2.copyMakeBorder(g, 0, side - g.shape[0], 0, 2 * side + 6 - g.shape[1], cv2.BORDER_CONSTANT,
								  value=(255, 255, 255))
	def canto():
		"""Zoom 6× no canto que mais se desloca (círculo grande azul-claro = antes, pequeno verde = depois)."""
		k0 = np.array(a["cantos_mm"]) / a["_mm"] - org
		k1 = np.array(d["cantos_mm"]) / d["_mm"] - org
		if len(k0) != 4 or len(k1) != 4:
			return None
		i = int(np.argmax(np.hypot(*(k1 - k0).T)))
		if np.hypot(*(k1[i] - k0[i])) * a["_mm"] < 0.3:
			return None
		J, Z = 40, 6
		cx, cy = ((k0[i] + k1[i]) / 2).astype(int)
		xa, ya = max(0, cx - J), max(0, cy - J)
		up = lambda m: cv2.resize(m[ya:ya + 2 * J, xa:xa + 2 * J].astype(np.uint8), None, fx=Z, fy=Z, interpolation=cv2.INTER_NEAREST)
		sub = cv2.resize(bgr[ya:ya + 2 * J, xa:xa + 2 * J], None, fx=Z, fy=Z, interpolation=cv2.INTER_NEAREST)
		cv2.drawContours(sub, cs(up(I0)), -1, (255, 200, 0), 2)
		cv2.drawContours(sub, cs(up(I1)), -1, (0, 200, 0), 1)
		cv2.drawContours(sub, cs(up(E)), -1, (0, 140, 255), 1)
		for k, col, r in ((k0, (255, 200, 0), 14), (k1, (0, 200, 0), 8)):
			q = ((k[i] - [xa, ya]) * Z).astype(int)
			cv2.circle(sub, (int(q[0]), int(q[1])), r, col, 3)
		t = f"canto {i}: desloca {np.hypot(*(k1[i] - k0[i])) * a['_mm']:.2f} mm"
		cv2.putText(sub, t, (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3, cv2.LINE_AA)
		cv2.putText(sub, t, (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
		side = 2 * JAN * ZOOM
		return cv2.copyMakeBorder(sub, 0, max(0, side - sub.shape[0]), 0, 2 * side + 6 - sub.shape[1], cv2.BORDER_CONSTANT,
								  value=(255, 255, 255))[:side]
	linhas = [geral()] + ([canto()] if canto() is not None else []) + [np.hstack([painel(I0, x, y, "antes"), np.full((2 * JAN * ZOOM, 6, 3), 255, np.uint8), painel(I1, x, y, "depois")])
			  for x, y, _ in _zonas(E & ~I0)]
	corpo = np.vstack(linhas)
	cab = np.full((54, corpo.shape[1], 3), 255, np.uint8)
	l1 = (f"{pid}: aresta fora do indice {a['aresta_fora_px']} -> {d['aresta_fora_px']} px; area do indice "
		  f"{a['area_mm2']} -> {d['area_mm2']} mm2; {a['cls']} -> {d['cls']}")
	l2 = "laranja = aresta do Tiago, azul-claro = indice antes, verde = indice depois, vermelho = aresta fora do indice"
	cv2.putText(cab, l1, (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
	cv2.putText(cab, l2, (6, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
	cv2.imwrite(fp, np.vstack([cab, corpo]), [cv2.IMWRITE_JPEG_QUALITY, 88])


def main(argv=None):
	from src.state import Project
	from src import overrides as OV
	from tools.verify import invariantes as INV
	ap = argparse.ArgumentParser()
	ap.add_argument("--project", default=os.path.join(REPO, "projects", "alpes"))
	ap.add_argument("--out", default=os.path.join(REPO, "docs", "diagnostico", "verify", "D2"))
	ap.add_argument("--imagens", type=int, default=3)
	a = ap.parse_args(argv)
	os.makedirs(a.out, exist_ok=True)
	raiz, copia = AMB.copiar_projeto(a.project)
	try:
		pr = Project.open(copia)
		cache = {}
		antes = _estado(pr, cache)
		sus0 = _suspeitas(pr)
		arr = INV.arranque(pr)
		pr = Project.open(copia)
		depois = _estado(pr, cache)
		sus1 = _suspeitas(pr)
		pecas = {}
		for pid, b in antes.items():
			d = depois[pid]
			dc = [round(y - x, 3) for x, y in zip(b["cordas_mm"], d["cordas_mm"])] if len(b["cordas_mm"]) == len(d["cordas_mm"]) else None
			dk = (round(float(max(np.hypot(*(np.subtract(q, p))) for p, q in zip(b["cantos_mm"], d["cantos_mm"]))), 3)
				  if b["ok"] and d["ok"] and b["cls"] == d["cls"] else None)
			pecas[pid] = {"aresta_fora_px": [b["aresta_fora_px"], d["aresta_fora_px"]],
						  "area_mm2": [b["area_mm2"], d["area_mm2"]], "d_area_mm2": round(d["area_mm2"] - b["area_mm2"], 3),
						  "cls": [b["cls"], d["cls"]], "cordas_mm": [b["cordas_mm"], d["cordas_mm"]], "d_cordas_mm": dc,
						  "cantos_desloc_max_mm": dk}
			print(json.dumps({"peca": pid, **{k: v for k, v in pecas[pid].items() if k != "cordas_mm"}}, ensure_ascii=False))
		maiores = sorted(antes, key=lambda p: -antes[p]["aresta_fora_px"])[:a.imagens]
		maiores += [p for p in sorted(pecas, key=lambda q: -(pecas[q]["cantos_desloc_max_mm"] or 0))[:2] if p not in maiores]
		for pid in maiores:
			if antes[pid]["aresta_fora_px"]:
				rgb = OV.load_scan_rgb(pr, antes[pid]["_sid"])
				imagem(pid, antes[pid], depois[pid], rgb, os.path.join(a.out, f"uniao_{pid}.jpg"))
		res = {"pecas": pecas, "arranque": arr, "suspeitas": {"antes": sus0, "depois": sus1,
				"novas": sorted(set(sus1) - set(sus0)), "desaparecidas": sorted(set(sus0) - set(sus1))},
			   "imagens": [f"uniao_{p}.jpg" for p in maiores if antes[p]["aresta_fora_px"]]}
		print(json.dumps({"arranque": {k: arr[k] for k in ("desatualizados", "pecas", "motivos", "eventos", "erros", "restantes")},
						  "suspeitas": {k: res["suspeitas"][k] for k in ("novas", "desaparecidas")},
						  "n_suspeitas": [len(sus0), len(sus1)]}, ensure_ascii=False, indent=1))
		with open(os.path.join(a.out, "uniao.json"), "w", encoding="utf-8", newline="\n") as f:
			json.dump(res, f, ensure_ascii=False, indent=1)
	finally:
		AMB.apagar_copia(raiz)


if __name__ == "__main__":
	main()
