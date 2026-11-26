"""Métricas das peças do golden e comparação com a baseline (decisão 2 do planeamento, 2026-11-26).

A baseline (``tests/golden/baseline.json``) só tem métricas das peças do manifesto; nada que conte o projeto vivo
inteiro (que muda a cada scan e colocação). Os limiares (``tests/golden/limiares.json``) são valores fixos com fonte
(``LIMIARES_INICIAIS``); nenhuma opção do comando os ajusta a partir de um resultado.

Por peça: existência e estado (não descartada), célula (peças de borda: tem de ser a do manifesto), ``cls``, cordas dos
4 lados. Contornos manuais: área da aresta fora do índice e o proxy de papel na coroa interior (informativos; a
4.1 (c) é desde 2026-11-26 uma regra absoluta, 0 px, em ``invariantes.manual_aresta_no_indice``: opção A do Tiago). Simetria: pares gémeos com as duas peças no golden e colocadas, e
o conjunto dos que passam ``TWIN_LOCAL_MAX_MM``. Suspeitas: o conjunto ``(peça, grau)`` de ``consistency.evaluate``
restrito às peças do golden; falha só uma suspeita NOVA (decisão 2)."""
import numpy as np

__all__ = ["LIMIARES_INICIAIS", "medir", "comparar"]

LIMIARES_INICIAIS = {
	"versao": 1,
	"corda_delta_mm": {"valor": 0.3, "fonte": "repetibilidade do comprimento de lado ≤ 0,3 mm (M3, CLAUDE.md; E-sym)"},
	"cls": {"valor": "igual", "fonte": "a classe F/T/B é o que o encaixe e a borda leem"},
	"celula_borda": {"valor": "igual ao manifesto", "fonte": "célula física confirmada, 218/218 (D6, 2026-11-25)"},
	"aresta_fora_do_indice_delta_mm2": {"valor": 0.05, "fonte": "tolerância de 4.1 (c) no levantamento; regra final por "
																 "decidir (D2): até lá, só não piorar"},
	"simetria": {"valor": "nenhum par novo acima de TWIN_LOCAL_MAX_MM", "fonte": "consistency.TWIN_LOCAL_MAX_MM (COMIDO.md §5)"},
	"suspeitas": {"valor": "nenhuma (peça, grau) nova em peças do golden", "fonte": "decisão 2 do planeamento, 2026-11-26"},
	"informativas": ["papel_coroa_pct", "simetria.rms_mm", "simetria.nn_max_mm", "aresta_fora_do_indice_mm2 (absoluto)"],
}


def _papel_coroa(rgb, ma, mm, bg) -> float:
	"""% de papel (distância ao fundo < ``strokes.PAPEL_LIMIAR``) numa coroa de 0,5 mm dentro da aresta (proxy)."""
	import cv2
	from src import strokes as ST
	d_in = cv2.distanceTransform(ma.astype(np.uint8), cv2.DIST_L2, 5)
	ring = ma & (d_in <= 0.5 / mm)
	L = cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
	L = L * np.array([100 / 255, 1, 1], np.float32) - np.array([0, 128, 128], np.float32)
	dd = np.sqrt(0.5 * (L[..., 0] - bg[0]) ** 2 + (L[..., 1] - bg[1]) ** 2 + (L[..., 2] - bg[2]) ** 2)
	return round(float((dd[ring] < ST.PAPEL_LIMIAR).mean() * 100), 2) if ring.any() else 0.0


def medir(pr, man: dict) -> dict:
	"""Métricas das peças do manifesto ``man`` num projeto aberto sobre uma CÓPIA."""
	from src import consistency as CS, render
	from tools.verify import invariantes as INV
	ids = sorted(man["pecas"])
	pecas = {}
	for pid in ids:
		p = pr.pieces.get(pid)
		if p is None:
			pecas[pid] = {"existe": False}
			continue
		pecas[pid] = {"existe": True, "estado": p.estado,
					  "celula": [int(p.celula[0]), int(p.celula[1])] if p.celula is not None else None,
					  "cls": p.cls or "", "cordas_mm": [round(float(x), 3) for x in (p.chords_mm or [])]}
	# contornos manuais
	bg = np.asarray(pr.profile.background_lab, float)
	manual = {}
	for pid, _o, rgb, mm, _g, mi, ma in INV._manuais(pr):
		if pid not in man["pecas"] or ma is None:
			continue
		manual[pid] = {"aresta_fora_do_indice_mm2": round(float((ma & ~mi).sum()) * mm * mm, 3),
					   "papel_coroa_pct": _papel_coroa(rgb, ma, mm, bg)}
	# simetria nos pares gémeos com as duas peças no golden e colocadas
	prof = pr.profile
	cel = {tuple(e["celula"]): pid for pid, e in pecas.items() if e.get("existe") and e.get("estado") == "colocada"
		   and e.get("celula")}
	pares = {}
	for lc, pid in sorted(cel.items()):
		tc = prof.twin(*lc)
		if tc is None or tuple(tc) not in cel or tuple(tc) < lc:
			continue
		qid = cel[tuple(tc)]
		r = CS.twin_local_residual(pr.shape(pid), pr.shape(qid))
		if r is not None:
			pares[f"{pid}|{qid}"] = {"rms_mm": round(r["rms_mm"], 3), "nn_max_mm": round(r["nn_max_mm"], 3)}
	acima = sorted(k for k, v in pares.items() if v["nn_max_mm"] > CS.TWIN_LOCAL_MAX_MM)
	# suspeitas das peças do golden
	pl = dict(render.load_placements(pr).get("placements") or {})
	ev = CS.evaluate(pr, pl)
	sus = sorted({f"{it['piece']}|{it['grau']}" for it in ev["items"] if it["piece"] in man["pecas"]})
	return {"pecas": pecas, "manual": manual, "simetria": {"pares": pares, "acima_do_limiar": acima,
			"limiar_mm": CS.TWIN_LOCAL_MAX_MM}, "suspeitas": sus, "suspeitas_total_informativo": len(ev["items"])}


def comparar(atual: dict, base: dict, lim: dict, man: dict) -> list:
	"""Lista de regressões ``[texto]`` de ``atual`` contra ``base`` (vazia = sem regressão)."""
	out = []
	dc = float(lim["corda_delta_mm"]["valor"])
	for pid, b in sorted(base["pecas"].items()):
		a = atual["pecas"].get(pid) or {"existe": False}
		if not a.get("existe"):
			out.append(f"{pid}: peça do golden desapareceu")
			continue
		if a.get("estado") == "descartada":
			out.append(f"{pid}: peça do golden descartada")
		cel_man = (man["pecas"].get(pid) or {}).get("celula")
		if cel_man is not None and (a.get("estado") != "colocada" or a.get("celula") != cel_man):
			out.append(f"{pid}: borda fora da célula do golden {cel_man} (estado {a.get('estado')}, célula {a.get('celula')})")
		if a.get("cls") != b.get("cls"):
			out.append(f"{pid}: cls {b.get('cls')} -> {a.get('cls')}")
		ca, cb = a.get("cordas_mm") or [], b.get("cordas_mm") or []
		if len(ca) != len(cb):
			out.append(f"{pid}: n.º de cordas {len(cb)} -> {len(ca)}")
		else:
			d = max((abs(x - y) for x, y in zip(ca, cb)), default=0.0)
			if d > dc + 1e-9:
				out.append(f"{pid}: corda muda {d:.3f} mm (> {dc})")
	for pid in sorted(base["manual"]):
		if pid not in atual["manual"]:
			out.append(f"{pid}: contorno manual com aresta deixou de ser medido")
	# 4.1 (c): sem «não piora» contra a baseline; é a regra absoluta invariantes.manual_aresta_no_indice (2026-11-26)
	novos = sorted(set(atual["simetria"]["acima_do_limiar"]) - set(base["simetria"]["acima_do_limiar"]))
	if novos:
		out.append(f"simetria: pares novos acima de {atual['simetria']['limiar_mm']} mm: {novos}")
	sn = sorted(set(atual["suspeitas"]) - set(base["suspeitas"]))
	if sn:
		out.append(f"suspeitas novas em peças do golden: {sn}")
	return out
