"""Regras absolutas sobre o projeto vivo (decisão 2 do planeamento, 2026-11-26): sem baseline, 0 violações exigidas.

Cada função recebe um :class:`src.state.Project` aberto sobre uma CÓPIA e devolve ``{n, violacoes, ...}`` (só leitura;
nada é escrito). Usadas por ``python -m tools.verify`` e pelos testes ``tests/test_invariantes_projeto.py``.

* :func:`estado` — ``Project.check_invariants()`` vazio (tabuleiro == replay do log, ≤ 1 peça por célula, ``n_no_lote``
  único, lote da peça = lote do scan, …);
* :func:`mesma_celula` — duas peças (``colocada``/``posicao_conhecida``) nunca na mesma célula;
* :func:`borda_completa` — todas as células de borda (pelo perfil) com uma peça ``colocada`` (D6 de 2026-11-25);
* :func:`f_por_celula` — cada peça colocada tem tantos lados F quantos os lados da célula fora da grelha;
* :func:`grupos_sobrepostos` — grupos soltos mostrados: nenhum recusado por ``grupos.sobreposto``, nenhuma célula com
  dois grupos, nenhum grupo sobre uma peça colocada (contado de forma independente de ``mesa.check_position``);
* :func:`manual_indice_da_linha` — 4.1 (b): o ``contour_px`` guardado de um contorno manual é, bit a bit, o que o
  programa lê da linha do Tiago (``rasterize_polygon(index_contour(...))``);
* :func:`manual_aresta_no_indice` — 4.1 (c), opção A (Tiago, 2026-11-26): a aresta pintada de um contorno manual fica
  inteira dentro do índice guardado (0 px fora; regra D5);
* :func:`manual_indice_na_banda` — 4.1 (d): índice a ≤ ``INDICE_HALO_MAX_MM`` da aresta (área fora da banda ≤
  ``INDICE_FORA_MIN_MM2``; R0036)."""
import collections

import numpy as np


def arranque(pr) -> dict:
	"""O que o arranque do servidor faz (``Gui._check_stale``: :func:`src.render.rebuild_stale`) na CÓPIA ``pr``,
	antes das regras: as regras e as métricas leem o projeto como o programa o verá depois de arrancar. Devolve
	``{desatualizados, folhas, pecas, motivos, eventos: [(acao, peca, motivo)], erros, aviso, restantes}``; um
	projeto real com contornos manuais por aplicar (p. ex. depois de mudar a leitura de uma linha) não é uma falha,
	fica registado aqui. Escreve só na cópia."""
	from src import render
	n0 = len(pr.events())
	r = render.rebuild_stale(pr, progress=None)
	ev = [(e.get("action"), e.get("piece"), e.get("motivo")) for e in pr.events()[n0:]]
	st = r["antes"]
	return {"desatualizados": st["n_pecas"], "folhas": r["folhas"], "pecas": r["pecas"],
			"motivos": {pid: why for pid, why in sorted(st["pecas"].items())}, "eventos": ev,
			"erros": list(r["errors"]), "aviso": r["aviso"],
			"restantes": (r["depois"] or {}).get("n_pecas", st["n_pecas"])}

__all__ = ["arranque", "estado", "mesma_celula", "borda_completa", "f_por_celula", "grupos_sobrepostos", "manual_indice_da_linha",
		   "manual_aresta_no_indice", "manual_indice_na_banda", "f_esperados", "REGRAS", "todas", "pares_gemeos", "simetria"]


def _res(viol: list, **kw) -> dict:
	return {"n": len(viol), "violacoes": viol, **kw}


def estado(pr) -> dict:
	return _res(list(pr.check_invariants()))


def mesma_celula(pr) -> dict:
	por = collections.defaultdict(list)
	for pid, p in sorted(pr.pieces.items()):
		if p.estado in ("colocada", "posicao_conhecida") and p.celula is not None:
			por[(int(p.celula[0]), int(p.celula[1]))].append(pid)
	viol = [{"celula": list(k), "pecas": v} for k, v in sorted(por.items()) if len(v) > 1]
	return _res(viol, celulas_com_peca=len(por))


def borda_completa(pr) -> dict:
	prof = pr.profile
	bordas = [lc for lc, _ in pr.board.iter_cells() if prof.is_border(*lc)]
	viol = [{"celula": list(lc), "estado": pr.board[lc]["estado"]} for lc in bordas
			if pr.board[lc]["estado"] != "colocada"]
	falta = [list(x) for x in pr.missing_border_cells()]
	if falta and not viol:
		viol = [{"celula": c, "estado": "missing_border_cells"} for c in falta]
	return _res(viol, celulas_borda=len(bordas))


def f_esperados(prof, l: int, c: int) -> int:
	"""Lados da célula ``(l, c)`` que ficam fora da grelha (canto 2, borda 1, interior 0)."""
	return sum(1 for dl, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)) if not prof.in_grid(l + dl, c + dc))


def f_por_celula(pr) -> dict:
	prof = pr.profile
	viol, n = [], 0
	for pid, p in sorted(pr.pieces.items()):
		if p.estado != "colocada" or p.celula is None:
			continue
		n += 1
		esp, got = f_esperados(prof, *p.celula), (p.cls or "").count("F")
		if esp != got:
			viol.append({"peca": pid, "celula": list(p.celula), "cls": p.cls, "esperado": esp, "obtido": got})
	return _res(viol, colocadas=n)


def grupos_sobrepostos(pr) -> dict:
	from src import grupos as GR, mesa
	shown = mesa.effective_positions(pr)
	viol = []
	for gid, pos in sorted(shown.items()):
		r = GR.sobreposto(pr, gid, pos, shown)
		if r:
			viol.append({"grupo": gid, "motivo": r.get("motivo"), "celula": r.get("celula")})
	occ = collections.defaultdict(list)
	for gid, pos in shown.items():
		for lc in mesa.footprint(pr.sections[gid], pos):
			occ[(int(lc[0]), int(lc[1]))].append(gid)
	colocadas = {(int(p.celula[0]), int(p.celula[1])) for p in pr.pieces.values()
				 if p.estado == "colocada" and p.celula is not None}
	for lc, gs in sorted(occ.items()):
		if len(set(gs)) > 1:
			viol.append({"celula": list(lc), "grupos": sorted(set(gs)), "motivo": "dois grupos"})
		if lc in colocadas:
			viol.append({"celula": list(lc), "grupos": sorted(set(gs)), "motivo": "sobre peça colocada"})
	return _res(viol, mostrados=len(shown))


def _manuais(pr):
	"""``[(pid, linha, rgb, mm_por_px, guardado, mascara_indice, mascara_aresta|None)]`` dos contornos manuais ativos."""
	import cv2
	from src import overrides as OV
	cache, out = {}, []
	for pid, o in sorted(OV.latest_overrides(pr).items()):
		sid = o["scan_id"]
		rgb = cache.get(sid)
		if rgb is None:
			rgb = cache[sid] = OV.load_scan_rgb(pr, sid)
		H, W = rgb.shape[:2]
		p = pr.piece(pid)
		with np.load(pr.p("pieces", f"{p.scan_id}.npz"), allow_pickle=False) as z:
			guardado = z[f"{pid}__contour_px"].astype(np.int32)

		def fill(c):
			m = np.zeros((H, W), np.uint8)
			cv2.fillPoly(m, [np.round(np.asarray(c, float)).astype(np.int32).reshape(-1, 1, 2)], 1)
			return m > 0
		ma = fill(np.asarray(o["aresta_px"], float).reshape(-1, 2)) if o.get("aresta_px") else None
		out.append((pid, o, rgb, OV._mmpp(pr, sid), guardado, fill(guardado), ma))
	return out


def manual_indice_da_linha(pr, manuais=None) -> dict:
	from src import overrides as OV
	viol, n = [], 0
	for pid, o, rgb, _mm, guardado, _mi, _ma in (manuais if manuais is not None else _manuais(pr)):
		n += 1
		H, W = rgb.shape[:2]
		_, _, esp = OV.rasterize_polygon(OV.index_contour(pr, o, rgb), W, H)
		if not (guardado.shape == esp.shape and np.array_equal(guardado, esp)):
			viol.append({"peca": pid})
	return _res(viol, manuais=n)


def manual_aresta_no_indice(pr, manuais=None) -> dict:
	"""4.1 (c): píxeis da aresta pintada fora do índice guardado (npz), por contorno manual com aresta; 0 exigido."""
	viol, n, vals = [], 0, {}
	for pid, _o, _rgb, _mm, _g, mi, ma in (manuais if manuais is not None else _manuais(pr)):
		if ma is None:
			continue
		n += 1
		px = int((ma & ~mi).sum())
		vals[pid] = px
		if px > 0:
			viol.append({"peca": pid, "aresta_fora_px": px})
	return _res(viol, com_aresta=n, valores_px=vals)


def manual_indice_na_banda(pr, manuais=None) -> dict:
	from src import strokes as ST
	viol, n, vals = [], 0, {}
	for pid, _o, _rgb, mm, _g, mi, ma in (manuais if manuais is not None else _manuais(pr)):
		if ma is None:
			continue
		n += 1
		v = float(ST.indice_fora_mm2(mi, ma, mm))
		vals[pid] = round(v, 3)
		if v > ST.INDICE_FORA_MIN_MM2:
			viol.append({"peca": pid, "fora_da_banda_mm2": round(v, 3), "limite": ST.INDICE_FORA_MIN_MM2})
	return _res(viol, com_aresta=n, valores_mm2=vals)


REGRAS = ("estado", "mesma_celula", "borda_completa", "f_por_celula", "grupos_sobrepostos", "manual_indice_da_linha",
		  "manual_aresta_no_indice", "manual_indice_na_banda")


def todas(pr) -> dict:
	"""Todas as regras de :data:`REGRAS` (os contornos manuais lidos uma vez)."""
	man = _manuais(pr)
	return {"estado": estado(pr), "mesma_celula": mesma_celula(pr), "borda_completa": borda_completa(pr),
			"f_por_celula": f_por_celula(pr), "grupos_sobrepostos": grupos_sobrepostos(pr),
			"manual_indice_da_linha": manual_indice_da_linha(pr, man), "manual_aresta_no_indice": manual_aresta_no_indice(pr, man),
			"manual_indice_na_banda": manual_indice_na_banda(pr, man)}


def pares_gemeos(pr) -> list:
	"""Pares de células gémeas (``profile.twin``) com as duas peças ``colocada``: ``[{a, ca, b, cb, r, excecao}]``
	com ``r`` = :func:`src.consistency.twin_local_residual` (None sem forma) e ``excecao`` o texto de
	:func:`src.consistency.twin_exception` (de ``symmetry.excecoes`` do perfil) para qualquer das duas células."""
	from src import consistency as CS
	prof = pr.profile
	by_cell = {(int(p.celula[0]), int(p.celula[1])): pid for pid, p in pr.pieces.items()
			   if p.estado == "colocada" and p.celula is not None}
	out = []
	for lc, pid in sorted(by_cell.items()):
		tc = prof.twin(*lc)
		if tc is None:
			continue
		tc = (int(tc[0]), int(tc[1]))
		if tc not in by_cell or tc < lc:
			continue
		qid = by_cell[tc]
		r = CS.twin_local_residual(pr.shape(pid), pr.shape(qid))
		exc = CS.twin_exception(prof, lc) or CS.twin_exception(prof, tc)
		out.append({"a": pid, "ca": list(lc), "b": qid, "cb": list(tc), "r": r, "excecao": exc})
	return out


def simetria(pr, por_rever=()) -> dict:
	"""4.2: pares gémeos colocados com ``nn_max`` acima de :data:`src.consistency.TWIN_LOCAL_MAX_MM` que não estão numa
	exceção do perfil nem na lista «por rever» (D3 de 2026-11-26: pares ``"Pxxxx|Pyyyy"``, qualquer ordem).
	Sem simetria declarada no perfil (``type == 'none'``) não há pares: ``{n: 0, aplicavel: False}``."""
	from src import consistency as CS
	if (pr.profile.symmetry or {}).get("type", "none") == "none":
		return _res([], aplicavel=False, pares=0)
	rev = {frozenset(x.split("|")) for x in por_rever}
	pares = pares_gemeos(pr)
	acima = [x for x in pares if x["r"] is not None and x["r"]["nn_max_mm"] > CS.TWIN_LOCAL_MAX_MM]
	viol, conhecidos, excecao = [], [], []
	for x in acima:
		d = {"a": x["a"], "ca": x["ca"], "b": x["b"], "cb": x["cb"], "nn_max_mm": round(x["r"]["nn_max_mm"], 3)}
		if x["excecao"]:
			excecao.append(d)
		elif frozenset((x["a"], x["b"])) in rev:
			conhecidos.append(d)
		else:
			viol.append(d)
	return _res(viol, aplicavel=True, pares=len(pares), medidos=sum(x["r"] is not None for x in pares),
				na_excecao=excecao, por_rever=conhecidos, limiar_mm=CS.TWIN_LOCAL_MAX_MM)
