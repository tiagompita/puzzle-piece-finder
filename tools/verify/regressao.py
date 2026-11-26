"""Passos 1–3 de ``tools.verify`` (2026-11-26, «fecho»): a segmentação e o matching voltam a correr sobre o golden.

Até aqui o verify lia os contornos guardados no projeto: uma alteração que estragasse ``segment_scan``,
``shape.analyse``, ``twin.find_twin`` ou ``fit`` passava. Este módulo corre o código de ``src/`` outra vez:

1. **Segmentação** (``ingest.segment_sheet``, o mesmo caminho da importação) das folhas do golden; por folha o n.º de
   peças contra o guardado; por peça do golden (sem as de contorno manual, D5) a distância máxima de fronteira
   (``maskcmp.mask_metrics``, ``d_max``) e o IoU contra o contorno guardado em ``pieces/<scan>.npz``.
2. **Classificação** das peças segmentadas de novo: ``cls``, cordas dos 4 lados, n.º de lados F contra o esperado
   pela célula (``profile.flat_directions``).
3. **Matching**:
   * E-sym (``segment_scan`` dos scans A1/A2/B2, ``shape.free_dist``): mediana da distância gémea A2/B2 e top-1 das
     três direções (o mesmo desenho de ``tests/test_segment_scan_esym.py``);
   * E-real-2 (``twin.find_twin`` sobre a memória de ``tests/data/ereal2_memoria.npz``, só forma): decisões por relação
     de verdade de terreno (EREAL2 §4), sem nenhum ``aceite`` em pares negativos;
   * quadrados 2×2 (``fit.side_costs``, as 40 peças dos 10 quadrados confirmados fisicamente): cada uma das 40
     ligações tem de ser a melhor mútua entre os lados das 40 peças;
   * molde do buraco em leave-one-out (``fit.hole_queries(exclude_piece=)`` + ``fit.rank_hole``): cada peça colocada do
     golden com ≥ 2 vizinhas colocadas sai do tabuleiro e é procurada entre as peças do golden; acerto = ela ou a gémea.
4. **Imagens de prova** das piores peças da segmentação (contorno guardado a verde, novo a vermelho).

Os limiares vêm de ``tests/golden/limiares.json`` (bloco ``regressao``, constantes com fonte) e nunca do resultado.
Nada aqui importa de ``tools/diagnostico/`` (ajuste 4 do Tiago, 2026-11-26): o que o E-sym e o E-real-2 precisam
(ordem em grelha, leitura da memória, relação de verdade de terreno) está reescrito aqui.

``--rapido``: E-sym + as 3 folhas do golden com mais peças do golden (regra, não ids; mais as folhas do E-sym que são do
golden) + E-real-2 + quadrados; sem o leave-one-out do molde (≈ 100 s). O completo corre tudo e é o único que congela."""
import hashlib
import os
import time

import numpy as np

from tools.verify.ambiente import REPO

__all__ = ["ESYM_SCANS", "EREAL2_MEMORIA", "N_FOLHAS_RAPIDO", "LIMIARES_REGRESSAO", "folhas_do_golden",
		   "segmentacao", "esym", "ereal2", "quadrados", "molde_loo", "medir", "comparar", "provas"]

ESYM_SCANS = {
	"A1": "images/pieces/coluna5-24_300dpi_folhaA.jpg",
	"A2": "images/pieces/colunas5-24_300dpi_rot180_folhaA.jpg",
	"B2": "images/pieces/coluna5-24_folhaB_300dpi_rot180.jpg",
}
EREAL2_MEMORIA = "tests/data/ereal2_memoria.npz"
N_FOLHAS_RAPIDO = 3
N_PROVAS = 6

# Limiares fixos, cada um com a fonte (constantes já medidas; nenhum vem de um resultado desta ferramenta).
LIMIARES_REGRESSAO = {
	"n_pecas_folha": {"valor": "igual ao guardado e à baseline",
					  "fonte": "a contagem exata foi o 1.º sinal de fusão e de perda (S1, S3; levantamento §3)"},
	"contorno_d_max_delta_mm": {"valor": 0.3,
								"fonte": "repetibilidade do comprimento de lado ≤ 0,3 mm (M3, CLAUDE.md; E-sym)"},
	"contorno_iou": {"valor": "não desce (arredondamento a 3 casas)",
					 "fonte": "levantamento §3: IoU < baseline falha"},
	"cls": {"valor": "igual à baseline", "fonte": "a classe F/T/B é o que o encaixe e a borda leem"},
	"corda_delta_mm": {"valor": 0.3, "fonte": "repetibilidade do comprimento de lado ≤ 0,3 mm (M3, CLAUDE.md; E-sym)"},
	"f_por_celula": {"valor": "n.º de lados F = n.º de lados da célula fora da grelha; não desce",
					 "fonte": "borda completa 218/218 confirmada (D6, 2026-11-25)"},
	"esym_twin_mediana_mm": {"valor": 0.5, "fonte": "E-sym, RESULTADOS.md 2026-10-31 (tests/test_segment_scan_esym.py)"},
	"esym_top1": {"valor": 20, "fonte": "E-sym 20/20 nas 3 direções (tests/test_segment_scan_esym.py)"},
	"ereal2_aceite_negativos": {"valor": 0, "fonte": "E-real-2: 0 falsos positivos em 10 608 pares (EREAL2.md §8)"},
	"ereal2_pos_aceite": {"valor": "não desce", "fonte": "E-real-2: 15 aceite + 0 ambígua nos 20 pares E-sym (2026-11-01)"},
	"quadrados_ligacoes": {"valor": "não desce; 10/10 quadrados com as 4 ligações",
						   "fonte": "17/17 quadrados encaixam fisicamente (2026-11-11, quadrados_17.json)"},
	"molde_top1": {"valor": "não desce", "fonte": "M11: top-1 do molde do buraco (levantamento §3)"},
	"molde_alta_errada": {"valor": "não sobe", "fonte": "M11_CRITERIOS §8: «alta» errada é o custo para o Tiago"},
}


def _sha256(fp: str) -> str:
	h = hashlib.sha256()
	with open(fp, "rb") as f:
		for b in iter(lambda: f.read(1 << 20), b""):
			h.update(b)
	return h.hexdigest()


def _abs(rel: str) -> str:
	return rel if os.path.isabs(rel) else os.path.join(REPO, *rel.split("/"))


# ------------------------------------------------------------------ passo 1 e 2: segmentação e classificação
def folhas_do_golden(pr, man: dict, rapido: bool = False) -> list:
	"""Ids dos scans com peças do golden; ``rapido``: as que o E-sym já segmenta mais as :data:`N_FOLHAS_RAPIDO` com
	mais peças do golden (desempate pelo id)."""
	n = {}
	for e in man["pecas"].values():
		n[e["scan_id"]] = n.get(e["scan_id"], 0) + 1
	todas = sorted(n)
	if not rapido:
		return todas
	esym = {os.path.normcase(os.path.normpath(_abs(v))) for v in ESYM_SCANS.values()}
	com_esym = [sid for sid in todas if os.path.normcase(os.path.normpath(_abs(pr.model.scans[sid]["file"]))) in esym]
	mais = sorted((sid for sid in todas if sid not in com_esym), key=lambda s: (-n[s], s))[:N_FOLHAS_RAPIDO]
	return sorted(com_esym + mais)


def _guardados(pr, sid: str) -> dict:
	"""``{pid: contour_px}`` do ``pieces/<sid>.npz`` (o contorno que o índice usa)."""
	fp = pr.p("pieces", f"{sid}.npz")
	out = {}
	with np.load(fp, allow_pickle=False) as d:
		for k in d.files:
			if k.endswith("__contour_px"):
				out[k[:-len("__contour_px")]] = np.asarray(d[k], float).reshape(-1, 2)
	return out


def _janela(a: np.ndarray, b: np.ndarray, pad: int = 6):
	lo = np.floor(np.minimum(a.min(0), b.min(0))).astype(int) - pad
	hi = np.ceil(np.maximum(a.max(0), b.max(0))).astype(int) + pad
	return lo, (int(hi[1] - lo[1]) + 1, int(hi[0] - lo[0]) + 1)


def _contorno_vs(guardado: np.ndarray, novo: np.ndarray, mmpp: float) -> dict:
	from src import maskcmp
	lo, shp = _janela(guardado, novo)
	g = maskcmp.fill_contour(guardado - lo, shp)
	c = maskcmp.fill_contour(novo - lo, shp)
	m = maskcmp.mask_metrics(g, c, mmpp, window=False)
	return {"iou": round(float(m["iou"]), 3), "d_max_mm": round(float(m["d_max"]), 3)}


def _centro(c: np.ndarray) -> np.ndarray:
	return np.asarray(c, float).reshape(-1, 2).mean(0)


def segmentacao(pr, man: dict, sids: list) -> dict:
	"""Passos 1 e 2 sobre as folhas ``sids``. ``{folhas: {sid: {n_pecas, n_guardadas, segundos}},
	pecas: {pid: {sid, iou, d_max_mm, cls, cordas_mm, n_f, f_esperado}}, excluidas_manual: [pid]}``."""
	from src.ingest import segment_sheet
	from src.overrides import is_manual
	prof = pr.profile
	folhas, pecas, manuais, novos = {}, {}, [], {}
	golden_por_folha = {}
	for pid, e in man["pecas"].items():
		golden_por_folha.setdefault(e["scan_id"], []).append(pid)
	n_guard = {}
	for p in pr.pieces.values():
		n_guard[p.scan_id] = n_guard.get(p.scan_id, 0) + 1
	for sid in sids:
		sc = pr.model.scans[sid]
		t0 = time.time()
		res = segment_sheet(_abs(sc["file"]), dpi=float(sc.get("dpi") or 300), profile=prof)
		if res.error:
			folhas[sid] = {"erro": res.error, "n_pecas": 0, "n_guardadas": n_guard.get(sid, 0)}
			continue
		folhas[sid] = {"n_pecas": len(res.pieces), "n_guardadas": n_guard.get(sid, 0), "segundos": round(time.time() - t0, 1)}
		guard = _guardados(pr, sid)
		cents = np.array([_centro(p["contour"]) for p in res.pieces]) if res.pieces else np.zeros((0, 2))
		for pid in sorted(golden_por_folha.get(sid, [])):
			p = pr.pieces.get(pid)
			if p is None or pid not in guard:
				pecas[pid] = {"sid": sid, "existe": False}
				continue
			if is_manual(p):
				manuais.append(pid)            # D5: o contorno manual não é uma métrica de segmentação
				continue
			if not len(cents):
				pecas[pid] = {"sid": sid, "existe": True, "sem_par": True}
				continue
			g = guard[pid]
			k = int(np.argmin(np.linalg.norm(cents - _centro(g), axis=1)))
			q = res.pieces[k]
			sh = q["shape"]
			e = {"sid": sid, "existe": True, **_contorno_vs(g, np.asarray(q["contour"], float).reshape(-1, 2), res.mm_per_px),
				 "cls": sh.cls if sh.ok else "", "cordas_mm": [round(float(s.chord_mm), 3) for s in sh.sides] if sh.ok else [],
				 "n_f": int(sh.n_flat)}
			if p.celula is not None and p.estado == "colocada":
				e["f_esperado"] = len(prof.flat_directions(int(p.celula[0]), int(p.celula[1])))
			pecas[pid] = e
			novos[pid] = (sid, g, np.asarray(q["contour"], float).reshape(-1, 2))
	return {"folhas": folhas, "pecas": pecas, "excluidas_manual": sorted(manuais), "_contornos": novos}


# ------------------------------------------------------------------ passo 3: matching
def _ordem_grelha(bboxes) -> list:
	"""Índices por filas (quebra no y do centro > 0,5 × altura mediana) e por x dentro da fila (E-sym, 4 × 5)."""
	b = np.asarray(bboxes, float)
	cy = b[:, 1] + b[:, 3] / 2
	cx = b[:, 0] + b[:, 2] / 2
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
	return [int(i) for r in rows for i in sorted(r, key=lambda j: cx[j])]


def _esym_gemea(i: int) -> int:
	"""GT do E-sym por posição na folha: A(f, k) ↔ B2(f, 4 − k) (5 colunas na folha; não é a regra do puzzle)."""
	f, k = divmod(i, 5)
	return 5 * f + (4 - k)


def esym() -> dict:
	"""``segment_scan`` de A1/A2/B2 → ``analyse`` → matriz ``free_dist``; contagens, mediana gémea A2/B2, top-1."""
	from PIL import Image
	from src.segmentation import segment_scan
	from src.shape import analyse, free_dist
	t0 = time.time()
	Z, cont = {}, {}
	for n, rel in ESYM_SCANS.items():
		with Image.open(_abs(rel)) as im:
			im.load()
			res = segment_scan(im)
		if "error" in res:
			return {"erro": f"{n}: {res['error']}"}
		ps = [res["pieces"][i] for i in _ordem_grelha([p["bbox"] for p in res["pieces"]])] if res["pieces"] else []
		cont[n] = {"n": len(ps), "clusters": int(sum(bool(p.get("is_cluster")) for p in ps))}
		Z[n] = [analyse(p["contour"], res["mm_per_px"]) for p in ps]
	if any(cont[n]["n"] != 20 for n in Z):
		return {"contagens": cont, "erro": "contagem diferente de 20", "segundos": round(time.time() - t0, 1)}
	M = {(a, b): np.array([[free_dist(x, y)[0] for y in Z[b]] for x in Z[a]])
		 for a, b in [("A1", "B2"), ("A2", "B2")]}
	T = np.array([_esym_gemea(i) for i in range(20)])
	ar = np.arange(20)
	return {"contagens": cont,
			"twin_mediana_mm": round(float(np.median(M[("A2", "B2")][ar, T])), 3),
			"top1": {"A1->B2": int(np.sum(M[("A1", "B2")].argmin(1) == T)),
					 "A2->B2": int(np.sum(M[("A2", "B2")].argmin(1) == T)),
					 "B2->A2": int(np.sum(M[("A2", "B2")].argmin(0) == T))},
			"segundos": round(time.time() - t0, 1)}


def _memoria_ereal2(fp: str) -> list:
	"""Peças da memória E-real-2 (formato de ``tests/data/ereal2_memoria.npz``: contornos em deltas inteiros)."""
	d = np.load(fp)
	n, first, step = d["n"], d["first"].astype(np.int64), d["step"].astype(np.int64)
	out, k = [], 0
	for i in range(len(n)):
		m = int(n[i])
		c = np.cumsum(np.vstack([first[i:i + 1], step[k:k + m - 1]]), axis=0).astype(np.float64)
		k += m - 1
		cell = tuple(int(v) for v in d["cell"][i]) if d["cell"][i][0] >= 0 else None
		out.append(dict(grupo=str(d["grupo"][i]), lab=str(d["lab"][i]), src=str(d["src"][i]), ok=bool(d["ok"][i]),
						cell=cell, contour=c))
	return out


def _relacao(a, b, src: dict, profile) -> str:
	"""Relação de verdade de terreno de um par (EREAL2 §4): pos / neg / ceuceu / BExceu."""
	if a.cell is not None and b.cell is not None:
		return "pos" if profile.twin(*a.cell) == tuple(b.cell) else "neg"
	s = {src[a.id], src[b.id]}
	if s == {"ceu"}:
		return "ceuceu"
	if "BE" in s:
		return "BExceu"
	return "neg"


def ereal2(profile) -> dict:
	"""``find_twin`` (só forma) de cada peça da memória contra todas; propostas por relação de verdade de terreno."""
	from src.shape import analyse
	from src.twin import TwinItem, find_twin
	t0 = time.time()
	M = [p for p in _memoria_ereal2(_abs(EREAL2_MEMORIA)) if p["grupo"] != "CEU" or p["ok"]]
	mmpp = profile.mm_per_px()
	items, src = [], {}
	for p in M:
		it = TwinItem(id=p["lab"], shape=analyse(p["contour"], mmpp), cell=p["cell"])
		items.append(it)
		src[it.id] = p["src"]
	by = {it.id: it for it in items}
	pares = {}
	for q in items:
		r = find_twin(q, items, profile=profile)
		if "error" in r:
			return {"erro": r["error"]}
		if r["decision"] != "sem" and r["candidates"]:
			key = frozenset((q.id, r["candidates"][0]["id"]))
			pares[key] = "aceite" if "aceite" in (pares.get(key), r["decision"]) else "ambigua"
	por = {}
	for key, d in pares.items():
		a, b = (by[x] for x in key)
		k = _relacao(a, b, src, profile)
		por.setdefault(k, {}).setdefault(d, []).append("|".join(sorted(key)))
	return {"n": len(items), "propostas": {k: {d: len(v) for d, v in dd.items()} for k, dd in sorted(por.items())},
			"aceite_negativos": sorted(por.get("neg", {}).get("aceite", []) + por.get("ceuceu", {}).get("aceite", [])),
			"segundos": round(time.time() - t0, 1)}


def _quadrados_json(man: dict) -> list:
	import json
	with open(_abs(man["quadrados"]["ficheiro"]), encoding="utf-8") as f:
		d = json.load(f)
	quero = set(man["quadrados"]["grupos"])
	return [g for g in d["grupos"] if g["n"] in quero]


def quadrados(pr, man: dict, cache=None) -> dict:
	"""Cada ligação dos quadrados do golden é a melhor mútua (``fit.side_costs``) entre os lados das peças deles?"""
	from src import fit
	from src.shape import f_adjacent
	t0 = time.time()
	grupos = _quadrados_json(man)
	ids = sorted({p["peca"] for g in grupos for p in g["pecas"]})
	calib = fit.calibration(pr)
	cache = cache or fit._Cache(pr, calib)
	items = fit.pool_items(pr, pieces=ids, cache=cache)
	pa = fit.pool_arrays(items)
	idx = {it.id: k for k, it in enumerate(items)}
	melhor = {}
	for k, it in enumerate(items):
		fa = f_adjacent([s.kind for s in it.sides])
		for i, s in enumerate(it.sides):
			if s.kind not in ("T", "B"):
				continue
			hs = fit.HoleSide(piece_id=it.id, direction="N", side=s, f_adj=bool(fa[i]), strip=it.strips[i])
			c = fit.side_costs(hs, pa, calib)["cost"].copy()
			c[k, :] = np.inf
			flat = np.argsort(c, axis=None)[:2]
			b1, j1 = np.unravel_index(flat[0], c.shape)
			c1, c2 = float(c[b1, j1]), float(c.flat[flat[1]])
			if np.isfinite(c1):
				melhor[(it.id, i)] = (items[int(b1)].id, int(j1), round(c2 / c1, 4) if c1 > 0 else None)
	lig, q_ok, falhas = 0, 0, []
	for g in grupos:
		ok_g = 0
		for l in g["ligacoes"]:
			a, la, b, lb = l["a"], int(l["lado_a"]), l["b"], int(l["lado_b"])
			ok = (a in idx and b in idx and melhor.get((a, la), (None, None))[:2] == (b, lb)
				  and melhor.get((b, lb), (None, None))[:2] == (a, la))
			ok_g += ok
			if not ok:
				falhas.append(f"quadrado {g['n']}: {a}[{la}]–{b}[{lb}]")
		lig += ok_g
		q_ok += ok_g == len(g["ligacoes"])
	return {"n_pecas": len(ids), "n_pecas_com_forma": len(items), "ligacoes_ok": lig,
			"ligacoes": sum(len(g["ligacoes"]) for g in grupos), "quadrados_ok": q_ok, "quadrados": len(grupos),
			"falhas": falhas, "segundos": round(time.time() - t0, 1)}


def molde_loo(pr, man: dict, cache=None) -> dict:
	"""Leave-one-out do molde do buraco nas peças colocadas do golden com ≥ 2 vizinhas colocadas; pool = as peças do
	golden com forma. Acerto = a própria peça ou a gémea (cada lado tem ≥ 2 parceiros físicos)."""
	from src import fit
	t0 = time.time()
	calib = fit.calibration(pr)
	cache = cache or fit._Cache(pr, calib)
	dcache = {}
	sigma = fit.board_sigma(pr, cache, dcache).get("sigma", 1)
	ids = sorted(man["pecas"])
	pa = fit.pool_arrays(fit.pool_items(pr, pieces=ids, cache=cache))
	cel = {tuple(p.celula): pid for pid, p in pr.pieces.items() if p.estado == "colocada" and p.celula is not None}
	n, top1, alta, alta_errada, falhas, certas, alta_err_ids = 0, 0, 0, 0, [], [], []
	for pid in ids:
		p = pr.pieces.get(pid)
		if p is None or p.estado != "colocada" or p.celula is None:
			continue
		lc = (int(p.celula[0]), int(p.celula[1]))
		hq = fit.hole_queries(pr, cells=[lc], min_neighbours=2, cache=cache, dcache=dcache, exclude_piece=pid)
		if not hq:
			continue
		r = fit.rank_hole(hq[0], pa, calib=calib, sigma=sigma, top=1)
		if "error" in r:
			continue
		n += 1
		tc = pr.profile.twin(*lc)
		certos = {pid} | ({cel[tuple(tc)]} if tc is not None and tuple(tc) in cel else set())
		top = r["candidates"][0]["id"] if r["candidates"] else None
		ok = top in certos
		top1 += ok
		if ok:
			certas.append(pid)
		if r["confidence"] == "alta":
			alta += 1
			alta_errada += not ok
			if not ok:
				alta_err_ids.append(pid)
		if not ok:
			falhas.append(f"{pid} {lc}: top-1 {top} ({r['confidence']})")
	return {"n": n, "top1": top1, "alta": alta, "alta_errada": alta_errada, "sigma": sigma, "n_pool": len(pa.ids),
			"certas": certas, "alta_errada_ids": alta_err_ids, "falhas": falhas, "segundos": round(time.time() - t0, 1)}


# ------------------------------------------------------------------ medir, comparar, provas
def medir(pr, man: dict, rapido: bool = False) -> dict:
	"""Passos 1–3. ``_contornos`` (privado, para :func:`provas`) não vai para a baseline."""
	from src import fit
	t0 = time.time()
	sids = folhas_do_golden(pr, man, rapido)
	seg = segmentacao(pr, man, sids)
	t1 = time.time()
	es = esym()
	er = ereal2(pr.profile)
	cache = fit._Cache(pr, fit.calibration(pr))
	qd = quadrados(pr, man, cache)
	lo = None if rapido else molde_loo(pr, man, cache)       # ≈ 100 s (tiras de ≈ 400 peças): só no modo completo
	ficheiros = {rel: _sha256(_abs(rel)) for rel in list(ESYM_SCANS.values()) + [EREAL2_MEMORIA]}
	return {"modo": "rapido" if rapido else "completo", "folhas": seg["folhas"], "pecas": seg["pecas"],
			"excluidas_manual": seg["excluidas_manual"], "esym": es, "ereal2": er, "quadrados": qd, "molde": lo,
			"ficheiros": ficheiros,
			"segundos": {"segmentacao": round(t1 - t0, 1), "matching": round(time.time() - t1, 1),
						 "total": round(time.time() - t0, 1)},
			"_contornos": seg["_contornos"]}


def _num(lim: dict, k: str) -> float:
	return float(lim[k]["valor"])


def comparar(atual: dict, base: dict, lim: dict) -> list:
	"""Regressões ``[texto]`` dos passos 1–3 contra a baseline completa (``atual`` pode ser só o modo rápido: compara as
	folhas e peças que mediu). Os critérios absolutos (E-sym, E-real-2 sem falsos positivos, quadrados 10/10) não
	dependem da baseline."""
	out = []
	# ficheiros fora do manifesto que o passo 3 lê (scans A2, memória E-real-2): mudança = golden alterado
	for rel, h in (base.get("ficheiros") or {}).items():
		if (atual.get("ficheiros") or {}).get(rel) != h:
			out.append(("golden", f"ficheiro do passo 3 alterado: {rel}"))
	dd, dc = _num(lim, "contorno_d_max_delta_mm"), _num(lim, "corda_delta_mm")
	for sid, a in sorted(atual["folhas"].items()):
		b = base["folhas"].get(sid)
		if a.get("erro"):
			out.append(("baseline", f"{sid}: segmentação falhou: {a['erro']}"))
			continue
		if a["n_pecas"] != a["n_guardadas"]:
			out.append(("baseline", f"{sid}: {a['n_pecas']} peças segmentadas, {a['n_guardadas']} no projeto"))
		if b is not None and a["n_pecas"] != b["n_pecas"]:
			out.append(("baseline", f"{sid}: {b['n_pecas']} -> {a['n_pecas']} peças"))
	for pid, a in sorted(atual["pecas"].items()):
		b = base["pecas"].get(pid)
		if b is None:
			continue
		if not a.get("existe") or a.get("sem_par"):
			out.append(("baseline", f"{pid}: sem peça correspondente na segmentação nova"))
			continue
		if a["d_max_mm"] > b["d_max_mm"] + dd + 1e-9:
			out.append(("baseline", f"{pid}: contorno d_max {b['d_max_mm']:.3f} -> {a['d_max_mm']:.3f} mm (> +{dd})"))
		if a["iou"] < b["iou"] - 1e-9:
			out.append(("baseline", f"{pid}: IoU {b['iou']:.3f} -> {a['iou']:.3f}"))
		if a["cls"] != b["cls"]:
			out.append(("baseline", f"{pid}: cls {b['cls']} -> {a['cls']}"))
		ca, cb = a.get("cordas_mm") or [], b.get("cordas_mm") or []
		if len(ca) != len(cb):
			out.append(("baseline", f"{pid}: n.º de cordas {len(cb)} -> {len(ca)}"))
		elif ca and max(abs(x - y) for x, y in zip(ca, cb)) > dc + 1e-9:
			out.append(("baseline", f"{pid}: corda muda {max(abs(x - y) for x, y in zip(ca, cb)):.3f} mm (> {dc})"))
		if "f_esperado" in a and a["n_f"] != a["f_esperado"] and b.get("n_f") == b.get("f_esperado"):
			out.append(("baseline", f"{pid}: {a['n_f']} lados F, a célula pede {a['f_esperado']}"))
	# E-sym (absoluto)
	es = atual["esym"]
	if es.get("erro"):
		out.append(("baseline", f"E-sym: {es['erro']} ({es.get('contagens')})"))
	else:
		if es["twin_mediana_mm"] > _num(lim, "esym_twin_mediana_mm"):
			out.append(("baseline", f"E-sym: mediana gémea A2/B2 {es['twin_mediana_mm']} mm > {_num(lim, 'esym_twin_mediana_mm')}"))
		for k, v in es["top1"].items():
			if v < _num(lim, "esym_top1"):
				out.append(("baseline", f"E-sym: top-1 {k} {v}/20"))
		if any(c["clusters"] for c in es["contagens"].values()):
			out.append(("baseline", f"E-sym: peças fundidas {es['contagens']}"))
	# E-real-2
	er, ber = atual["ereal2"], base.get("ereal2") or {}
	if er.get("erro"):
		out.append(("baseline", f"E-real-2: {er['erro']}"))
	else:
		if len(er["aceite_negativos"]) > _num(lim, "ereal2_aceite_negativos"):
			out.append(("baseline", f"E-real-2: aceite em pares negativos {er['aceite_negativos']}"))
		pa_ = er["propostas"].get("pos", {}).get("aceite", 0)
		pb_ = (ber.get("propostas") or {}).get("pos", {}).get("aceite", 0)
		if pa_ < pb_:
			out.append(("baseline", f"E-real-2: pares gémeos aceites {pb_} -> {pa_}"))
	# quadrados
	qa, qb = atual["quadrados"], base.get("quadrados") or {}
	if qa["ligacoes_ok"] < qb.get("ligacoes_ok", 0) or qa["quadrados_ok"] < qa["quadrados"]:
		out.append(("baseline", f"quadrados: ligações {qb.get('ligacoes_ok')} -> {qa['ligacoes_ok']}/{qa['ligacoes']}, "
								f"quadrados {qa['quadrados_ok']}/{qa['quadrados']}: {qa['falhas'][:4]}"))
	# molde do buraco (só no modo completo), peça a peça: o tabuleiro muda com o uso (mais vizinhas, mais buracos
	# medidos), por isso falha uma peça que estava certa e deixou de estar, ou uma «alta» errada nova; uma peça que
	# deixou de ter 2 vizinhas não conta
	ma, mb = atual.get("molde"), base.get("molde") or {}
	if ma is not None:
		medidas = set(ma["certas"]) | {f.split(" ")[0] for f in ma["falhas"]}
		perdidas = sorted(set(mb.get("certas") or []) & (medidas - set(ma["certas"])))
		if perdidas:
			out.append(("baseline", f"molde (leave-one-out): top-1 perdido em {perdidas[:8]} "
									f"({mb.get('top1')} -> {ma['top1']} de {ma['n']})"))
		novas = sorted(set(ma["alta_errada_ids"]) - set(mb.get("alta_errada_ids") or []))
		if novas:
			out.append(("baseline", f"molde (leave-one-out): «alta» errada nova em {novas[:8]}"))
	return out


def provas(pr, atual: dict, out_dir: str, n: int = N_PROVAS) -> list:
	"""PNG das ``n`` peças com maior ``d_max`` (contorno guardado a verde, novo a vermelho, recorte do scan)."""
	from PIL import Image, ImageDraw
	pecas = [(v["d_max_mm"], pid) for pid, v in atual["pecas"].items() if v.get("existe") and "d_max_mm" in v]
	pior = [pid for _, pid in sorted(pecas, key=lambda t: (-t[0], t[1]))[:n]]
	os.makedirs(os.path.join(out_dir, "prova"), exist_ok=True)
	feitos, abertos = [], {}
	for pid in pior:
		sid, g, c = atual["_contornos"][pid]
		fp = _abs(pr.model.scans[sid]["file"])
		if fp not in abertos:
			with Image.open(fp) as im:
				abertos[fp] = im.convert("RGB")
		im = abertos[fp]
		lo, shp = _janela(g, c, pad=30)
		crop = im.crop((int(lo[0]), int(lo[1]), int(lo[0]) + shp[1], int(lo[1]) + shp[0]))
		esc = 3
		crop = crop.resize((crop.width * esc, crop.height * esc), Image.NEAREST)
		d = ImageDraw.Draw(crop)
		for cc, cor in ((g, (0, 200, 0)), (c, (255, 0, 0))):
			pts = [tuple(((q - lo) * esc + esc / 2).tolist()) for q in cc]
			d.line(pts + [pts[0]], fill=cor, width=2)
		v = atual["pecas"][pid]
		d.rectangle([0, 0, crop.width, 22], fill=(255, 255, 255))
		d.text((4, 4), f"{pid} {sid}  d_max {v['d_max_mm']:.3f} mm  IoU {v['iou']:.3f}  cls {v['cls']}  "
					   f"(verde = guardado, vermelho = novo)", fill=(0, 0, 0))
		dst = os.path.join(out_dir, "prova", f"seg_{pid}.png")
		crop.save(dst)
		feitos.append(dst)
	return feitos
