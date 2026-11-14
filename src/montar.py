"""Ecrã «Montar» da GUI nova (ESPEC §4.1–§4.3, §8.2–§8.4): a fila «próxima peça», as palavras de confiança e os
traços do «Porquê esta peça?». Puro: recebe as entradas de ``/api/fetch`` (gémeas, borda, pares, posições
conhecidas) e as sugestões ``alta`` do molde do buraco (``Gui.alta_json``), o log e o perfil; não lê ficheiros.

Regras (decididas pelo Tiago em 2026-11-11, ESPEC §8):

* **Fila (§8.2).** Primeiro as peças com vizinha montada (``grupo == 'coloca_agora'``) e ainda soltas. Começa pelo saco
  ``saco_atual`` (o que o browser está a esgotar) enquanto tiver peças; senão pelo saco do último scan importado;
  senão pelo saco com mais «quase certo». Os outros sacos seguem por nº de «quase certo», depois nº de peças, depois
  número do saco. Dentro do saco: «quase certo» primeiro, depois gémea/borda/fundida, par, posição guardada e molde
  do buraco, e por fim a ``ordem`` da consulta. «Saltar» é do browser (só na sessão).
* **«Guardar à parte» (F1c, Tiago 2026-11-14).** Depois de esgotadas as «coloca agora», as propostas com peça sem
  vizinha montada (``grupo == 'guarda_posicao'``: gémea, borda ou par) entram na fila como cartões ``tipo ==
  'guardar'``: sempre «a confirmar por ti», sem «Encaixa» (não há vizinha para verificar), com «Guardei à parte»
  (``position_known``) e «Não é esta» (``reject``). Uma peça que já está na fila como «coloca agora» não volta como
  «guardar». O ecrã vazio diz o que ficou de fora (:func:`resumo`).
* **«quase certo» (§8.3).** Só com a decisão do motor ``aceite`` / ``colocavel`` / ``alta``, sem encaixe
  incompatível nem traço a falhar, e com o histórico físico da origem × zona com n >= :data:`QUASE_CERTO_N` decisões e limite inferior
  de Wilson 95 % >= :data:`QUASE_CERTO_WILSON`. Decisões desfeitas não contam (:func:`src.state.undone_decisions`).
  Tudo o resto é «a confirmar por ti». Um cartão fundido (gémea + buraco) é «quase certo» se uma das duas origens
  o for.
* **Traços (§8.4).** 3 = passa com folga, 2 = passa, 1 = falha, 0 = não testado («não verificado»). Folga =
  metade do limite (forma: ``d1 <= t95 / 2`` ou custo do encaixe ``<= t_abs / 2``; imagem: ``ΔE <= p90 / 2``) ou
  margem >= 2 × ``margin_min``. Estes fatores (½ e 2×) são do ecrã, não calibrados: só mudam 2 ↔ 3 traços.
"""

from __future__ import annotations

import math
from typing import Optional

__all__ = ["QUASE_CERTO_N", "QUASE_CERTO_WILSON", "PENDING_STATES", "GUARDAR_STATES", "track_record", "confidence",
		   "tracos", "fila", "resumo", "progress"]

QUASE_CERTO_N = 10                  # §8.3: decisões físicas mínimas por origem × zona
QUASE_CERTO_WILSON = 0.80           # §8.3: limite inferior de Wilson 95 % mínimo
FOLGA_LIMITE = 0.5                  # «passa com folga»: valor <= FOLGA_LIMITE × limite (forma, encaixe, imagem)
FOLGA_MARGEM = 2.0                  # «passa com folga»: margem >= FOLGA_MARGEM × margin_min
PENDING_STATES = ("solta", "emparelhada", "posicao_conhecida")
GUARDAR_STATES = ("solta", "emparelhada")    # «Guardar à parte»: uma peça já guardada (posicao_conhecida) não volta
_GOOD = ("aceite", "colocavel", "alta")
_KIND_ORDER = {"gemea": 0, "fundida": 0, "borda": 0, "par": 1, "guardada": 2, "buraco": 3}
_GUARDAR_ORIGINS = ("gemeo", "borda", "par")


def _wilson_lo(k: int, n: int, z: float = 1.96) -> float:
	if n <= 0:
		return 0.0
	p = k / n
	d = 1 + z * z / n
	c = (p + z * z / (2 * n)) / d
	h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
	return max(0.0, c - h)


def _zone(profile, cell) -> Optional[str]:
	if profile is None or not cell:
		return None
	try:
		return profile.zone_of(int(cell[0]), int(cell[1]))
	except (ValueError, TypeError):
		return None


def track_record(events: list, profile) -> dict:
	"""Decisões físicas por ``(origem, zona)``: ``{(origem, zona): {n, acertos, falhas, wilson_lo}}``.

	Gémea / borda: ``twin_confirmed`` / ``twin_rejected`` (pela ``origin`` do evento). Buraco: só as decisões das
	sugestões ``alta`` de rank 1 (as que chegam ao Montar; as mesmas do contador de :func:`src.fit.alta_counter`).
	Par: ``pair_confirmed`` / ``pair_rejected`` (sem célula: zona None). Decisões desfeitas não contam."""
	from src.state import undone_decisions
	gone = undone_decisions(events)
	acc: dict = {}

	def add(key, ok):
		r = acc.setdefault(key, {"n": 0, "acertos": 0, "falhas": 0})
		r["n"] += 1
		r["acertos" if ok else "falhas"] += 1

	for i, e in enumerate(events):
		if i in gone:
			continue
		a = e.get("action")
		if a in ("twin_confirmed", "twin_rejected") and e.get("origin") in ("gemeo", "borda"):
			add((e["origin"], _zone(profile, e.get("cell"))), a == "twin_confirmed")
		elif a in ("hole_confirmed", "hole_rejected") and e.get("origin") == "buraco":
			if e.get("confianca") == "alta" and e.get("rank") is not None and int(e["rank"]) == 1:
				add(("buraco", _zone(profile, e.get("cell"))), a == "hole_confirmed")
		elif a in ("pair_confirmed", "pair_rejected"):
			add(("par", None), a == "pair_confirmed")
	for r in acc.values():
		r["wilson_lo"] = round(_wilson_lo(r["acertos"], r["n"]), 4)
	return acc


def _record_ok(record: dict, origin: str, zone) -> bool:
	r = record.get((origin, zone))
	return bool(r and r["n"] >= QUASE_CERTO_N and r["wilson_lo"] >= QUASE_CERTO_WILSON)


def confidence(item: dict, record: dict, profile=None) -> str:
	"""``'quase_certo'`` ou ``'a_confirmar'`` (§8.3) para um item da fila (ver :func:`fila`). Um item com um traço
	que falha (``item['tracos']``, ver :func:`tracos`) nunca é «quase certo»."""
	if item["tipo"] == "guardar":
		return "a_confirmar"          # sem vizinha montada o encaixe não se verifica: nunca «quase certo» (F1c)
	zone = _zone(profile, item.get("cell"))
	enc = (item.get("encaixe") or {}).get("estado")
	if enc == "incompativel" or any(t.get("estado") == "falha" for t in item.get("tracos") or []):
		return "a_confirmar"
	sources = []
	if item["tipo"] in ("gemea", "borda", "fundida", "par"):
		sources.append((item.get("origin"), item.get("decision")))
	if item["tipo"] in ("buraco", "fundida"):
		sources.append(("buraco", "alta"))
	for org, dec in sources:
		if dec in _GOOD and _record_ok(record, org, zone if org != "par" else None):
			return "quase_certo"
	return "a_confirmar"


def _trace(chave: str, n: int, frase: str, estado: str) -> dict:
	return {"chave": chave, "tracos": n, "estado": estado, "frase": frase}


_FRASES = {
	"forma": {3: "A forma bate. O recorte é quase igual ao do lugar.", 2: "A forma passa, mas sem folga.",
			  1: "A forma não bate bem com o lugar.", 0: "Forma: não verificado."},
	"imagem": {3: "A imagem é parecida. As cores continuam as do lugar.", 2: "A imagem passa, mas sem folga.",
			   1: "A imagem não bate com o lugar.", 0: "Imagem: não verificado."},
	"distancia": {3: "Não há outra parecida. A segunda melhor fica bem atrás.", 2: "A segunda melhor fica atrás, mas perto.",
				  1: "Há outra quase tão parecida.", 0: "Segunda candidata: não verificado."},
}
_ESTADO = {3: "folga", 2: "passa", 1: "falha", 0: "nao_testado"}


def _level(v, limit) -> int:
	if v is None or limit is None or not math.isfinite(float(v)) or not limit:
		return 0
	v = float(v)
	if v <= FOLGA_LIMITE * float(limit):
		return 3
	return 2 if v <= float(limit) else 1


def _margin_level(m, mmin) -> int:
	if m is None or mmin is None:
		return 0
	m = float(m)
	if not math.isfinite(m) or m >= FOLGA_MARGEM * float(mmin):
		return 3
	return 2 if m >= float(mmin) else 1


def tracos(item: dict, profile=None) -> list:
	"""Os 3 traços do «Porquê esta peça?» (§4.3, §8.4): forma, imagem, distância para a 2.ª candidata."""
	if item["tipo"] == "guardar":
		return tracos(dict(item, tipo=item.get("tipo_base") or "gemea"), profile)
	cal = (getattr(profile, "calibration", None) or {}) if profile is not None else {}
	t95 = (cal.get("silhueta_silhueta") or {}).get("t95")
	t_abs = (cal.get("buraco") or {}).get("t_abs")
	mmin = cal.get("margin_min", 1.5)
	if isinstance(mmin, dict):
		mmin = mmin.get("valor", 1.5)
	tipo = item["tipo"]
	enc = item.get("encaixe") or {}
	hole = item.get("hole") or {}
	forma = 0
	if tipo in ("gemea", "borda", "fundida", "par"):
		forma = _level(item.get("d1_mm"), t95)
	if tipo in ("buraco", "fundida"):
		f2 = _level(hole.get("J"), t_abs)
		forma = f2 if not forma else (min(forma, f2) if f2 else forma)
	if enc.get("estado") == "ok":
		f2 = _level(enc.get("J"), enc.get("t_abs") or t_abs)
		forma = f2 if not forma else (min(forma, f2) if f2 else forma)
	elif enc.get("estado") == "incompativel":
		forma = 1
	imagem = 0
	zone = _zone(profile, item.get("cell"))
	p90 = None
	if zone is not None and profile is not None:
		try:
			p90 = (profile.zones().get(zone) or {}).get("dE_p90")
		except AttributeError:
			p90 = None
	if tipo in ("gemea", "borda", "fundida") and item.get("dE") is not None and p90:
		imagem = _level(item.get("dE"), p90)
	if tipo == "buraco":
		dist = _margin_level(hole.get("margem"), mmin)
	elif tipo == "guardada":
		dist = 0
	else:
		dist = _margin_level(item.get("margin"), mmin)
		if tipo == "fundida":
			d2 = _margin_level(hole.get("margem"), mmin)
			dist = max(dist, d2)
	out = []
	for k, n in (("forma", forma), ("imagem", imagem), ("distancia", dist)):
		out.append(_trace(k, n, _FRASES[k][n], _ESTADO[n]))
	if imagem == 0 and tipo in ("gemea", "borda", "fundida") and item.get("dE") is not None and not p90:
		out[1]["frase"] = "Imagem: não verificado (nesta zona a imagem ainda não decide)."
	return out


def _kind(e: dict) -> str:
	org = e.get("origin")
	if org == "buraco":
		return "buraco"
	if org == "par":
		return "par"
	if org == "posicao_conhecida":
		return "guardada"
	if org == "borda":
		return "borda"
	return "gemea"


def _actions(item: dict) -> tuple:
	"""(encaixa, nao_encaixa): ``{url, body}`` dos pedidos que o botão faz (o servidor diz qual)."""
	pid, cell = item["piece"], item["cell"]
	l, c = int(cell[0]), int(cell[1])
	if item["tipo"] == "guardar":
		return None, {"url": "/api/confirm", "body": {"acao": "reject", "piece": pid}}
	if item["tipo"] == "fundida":
		return ({"url": f"/api/holes/{l}/{c}/confirmar", "body": {"piece": pid, "gemea": True}},
				{"url": f"/api/holes/{l}/{c}/rejeitar", "body": {"piece": pid, "gemea": True}})
	if item["tipo"] == "buraco":
		return ({"url": f"/api/holes/{l}/{c}/confirmar", "body": {"piece": pid}},
				{"url": f"/api/holes/{l}/{c}/rejeitar", "body": {"piece": pid}})
	enc = {"url": "/api/confirm", "body": {"acao": "place", "piece": pid, "cell": [l, c], "origin": item.get("origin")}}
	if item["tipo"] == "guardada":
		return enc, None                  # a posição guardada não tem proposta a rejeitar (como hoje)
	return enc, {"url": "/api/confirm", "body": {"acao": "reject", "piece": pid}}


def _item(e: dict, tipo: str) -> dict:
	keep = ("piece", "lote", "n_no_lote", "cell", "origin", "decision", "margin", "dE", "d1_mm", "theta_deg", "pose_known",
			"scan_id", "ordem", "encaixe", "pair", "twin_id", "twin_cell", "reasons", "razoes_txt", "hole", "gemea_decision")
	it = {k: e.get(k) for k in keep}
	it["tipo"] = tipo
	return it


def _guardar_action(item: dict) -> dict:
	"""«Guardei à parte»: a posição fica conhecida (como o «Guardei num saquinho» da interface completa)."""
	return {"url": "/api/confirm", "body": {"acao": "position_known", "piece": item["piece"], "cell": list(item["cell"]),
											"origin": item.get("origin"), "nota": "saquinho"}}


def fila(entries: list, alta: Optional[dict], record: dict, profile=None, *, saco_atual=None,
		 ultimo_saco=None) -> dict:
	"""A fila do Montar. ``entries``: entradas de ``/api/fetch`` (com ``grupo`` e ``estado_atual``); ``alta``: o
	``buracos_alta`` de ``/api/fetch`` (``em_pausa``, ``entries``). Devolve ``{itens, saco, ordem_sacos, total,
	em_pausa, n_coloca, n_guardar}``; cada item tem ``tipo`` (gemea | borda | fundida | par | guardada | buraco |
	guardar), ``confianca``, ``tracos``, ``encaixa`` / ``nao_encaixa`` / ``guardar`` (pedidos) e os campos da entrada
	de que o ecrã precisa. Os cartões ``guardar`` vêm sempre depois de todos os outros (F1c)."""
	alta = alta or {}
	paused = bool(alta.get("em_pausa"))
	fused = {}
	if not paused:
		for a in alta.get("entries") or []:
			if a.get("fundida_com_gemea"):
				fused[(a["piece"], tuple(a["cell"]))] = a
	items, seen = [], set()
	for e in entries:
		if not e.get("piece") or not e.get("cell") or e.get("grupo") != "coloca_agora":
			continue
		if e.get("estado_atual") and e["estado_atual"] not in PENDING_STATES:
			continue
		key = (e["piece"], tuple(e["cell"]))
		if key in seen:
			continue
		seen.add(key)
		tipo = _kind(e)
		h = fused.get(key) if tipo in ("gemea", "borda") else None
		it = _item(e, "fundida" if h else tipo)
		if h:
			it["hole"] = h.get("hole")
		items.append(it)
	if not paused:
		for a in alta.get("entries") or []:
			if a.get("fundida_com_gemea"):
				continue
			if a.get("estado_atual") and a["estado_atual"] not in PENDING_STATES:
				continue
			key = (a["piece"], tuple(a["cell"]))
			if key in seen:
				continue
			seen.add(key)
			items.append(_item(a, "buraco"))
	in_queue = {it["piece"] for it in items}
	keep = []
	for e in entries:
		if not e.get("piece") or not e.get("cell") or e.get("grupo") != "guarda_posicao":
			continue
		if e.get("origin") not in _GUARDAR_ORIGINS or e["piece"] in in_queue:
			continue
		if e.get("estado_atual") and e["estado_atual"] not in GUARDAR_STATES:
			continue
		in_queue.add(e["piece"])
		it = _item(e, "guardar")
		it["tipo_base"] = _kind(e)
		keep.append(it)
	for it in items + keep:
		it["tracos"] = tracos(it, profile)
		it["confianca"] = confidence(it, record, profile)
		it["encaixa"], it["nao_encaixa"] = _actions(it)
		it["guardar"] = _guardar_action(it) if it["tipo"] == "guardar" else None
	by: dict = {}
	for it in items:
		by.setdefault(it.get("lote"), []).append(it)
	for k, xs in by.items():
		xs.sort(key=lambda it: (it["confianca"] != "quase_certo", _KIND_ORDER.get(it["tipo"], 9),
								it.get("ordem") if it.get("ordem") is not None else 10 ** 6, it["piece"]))

	def nq(k):
		return sum(1 for it in by[k] if it["confianca"] == "quase_certo")

	rest = sorted(by, key=lambda k: (k is None, -nq(k), -len(by[k]), k if k is not None else 0))
	order = []
	if rest:
		start = next((k for k in (saco_atual, ultimo_saco) if k is not None and k in by), rest[0])
		order = [start] + [k for k in rest if k != start]
	out = [it for k in order for it in by.get(k, [])]
	n_coloca = len(out)
	rank = {k: i for i, k in enumerate(order)}
	keep.sort(key=lambda it: (rank.get(it.get("lote"), len(order)), it.get("lote") is None, it.get("lote") or 0,
							  it.get("ordem") if it.get("ordem") is not None else 10 ** 6, it["piece"]))
	out += keep
	for i, it in enumerate(out):
		it["posicao"] = i
	return {"itens": out, "saco": (order[0] if order else None), "ordem_sacos": order, "total": len(out),
			"n_coloca": n_coloca, "n_guardar": len(keep), "em_pausa": paused,
			"n_por_saco": {str(k): len(by[k]) for k in order}}


def resumo(entries: list, itens: list, guardadas: int = 0) -> dict:
	"""O que fica fora da fila, para o ecrã vazio dizer a verdade (F1c, Tiago 2026-11-14): ``guardar`` (cartões
	«Guardar à parte» na fila), ``guardadas`` (peças já guardadas à parte à espera de uma vizinha montada, contadas
	pelo chamador), ``grupos_sem_lugar`` (grupos por ancorar na consulta, ``origin == 'seccao'``) e ``propostas``
	(entradas da consulta com peça ou grupo). Até à F4, os grupos só se veem na interface completa."""
	n_sec = sum(1 for e in entries if e.get("origin") == "seccao")
	n_prop = sum(1 for e in entries if e.get("piece") or e.get("origin") == "seccao")
	return {"guardar": sum(1 for it in itens if it.get("tipo") == "guardar"), "guardadas": int(guardadas),
			"grupos_sem_lugar": n_sec, "propostas": n_prop}


def progress(board, user_source: str = "tiago") -> dict:
	"""Progresso do topo (P12): colocadas + lugares marcados cheios pelo Tiago; «cheia na foto» não conta."""
	n_placed = n_user = 0
	for _, cell in board.iter_cells():
		if cell["estado"] == "colocada":
			n_placed += 1
		elif cell["estado"] == "ocupada_legado" and cell.get("fonte") == user_source:
			n_user += 1
	return {"colocadas": n_placed, "marcadas": n_user, "n": n_placed + n_user}
