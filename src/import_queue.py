"""Import queue of the GUI server: ``projects/<id>/import_queue.jsonl``, append-only, replayed on load (like ``log.jsonl``).

Pure bookkeeping (no threads, no segmentation): the server's worker (:mod:`src.server`, thread ``fila-importacao``)
asks :meth:`ImportQueue.next_job`, marks :meth:`~ImportQueue.start`, one :meth:`~ImportQueue.sheet` per sheet and
:meth:`~ImportQueue.done` / :meth:`~ImportQueue.fail`; the routes call :meth:`~ImportQueue.add`,
:meth:`~ImportQueue.cancel`, :meth:`~ImportQueue.move` and :meth:`~ImportQueue.retry`. The caller serialises the
calls (one lock); every call appends one event and applies it, so ``snapshot()`` of another :class:`ImportQueue` over
the same file is identical.

Events (``t`` = ISO time): ``job_added {id, lote, ficheiros, folhas: [{origem, pagina, caminho, ...}], dpi}``,
``job_started {id}``, ``job_sheet {id, k, n, caminho, estado: ok|ignorada|erro, scan_id, n_pecas, avisos, erro}``,
``job_done {id, n_folhas, n_pecas, propostas, segundos}``, ``job_failed {id, erro}``, ``job_cancelled {id}``,
``job_retried {id, motivo, cabeca}``, ``job_moved {id, posicao}``.

States: ``em_fila`` -> ``a_correr`` -> ``concluido`` | ``falhado``; ``em_fila`` -> ``cancelado``; ``falhado`` /
``cancelado`` -> (retry) ``em_fila``. :meth:`~ImportQueue.recover` (server start): a job left ``a_correr`` by a
crash / restart goes back to the head of the queue (``job_retried {motivo: reinicio, cabeca: true}``). Ids
``Q0001``… are monotonic over the file.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from typing import Optional

__all__ = ["ESTADOS", "EVENTOS", "QueueError", "ImportQueue", "apply_event"]

ESTADOS = ("em_fila", "a_correr", "concluido", "falhado", "cancelado")
EVENTOS = ("job_added", "job_started", "job_sheet", "job_done", "job_failed", "job_cancelled", "job_retried", "job_moved")


class QueueError(ValueError):
	"""Invalid queue operation (nothing was written)."""


def _now() -> str:
	return _dt.datetime.now().isoformat(timespec="seconds")


def _new_job(ev: dict) -> dict:
	return {"id": ev["id"], "lote": ev.get("lote"), "ficheiros": list(ev.get("ficheiros") or []),
			"folhas": [dict(f) for f in ev.get("folhas") or []], "dpi": ev.get("dpi"), "estado": "em_fila",
			"t_adicionado": ev.get("t"), "t_inicio": None, "t_fim": None, "resultados": [], "n_pecas": 0, "propostas": None,
			"segundos": None, "erro": None, "tentativas": 0, "avisos": list(ev.get("avisos") or [])}


def apply_event(state: dict, ev: dict) -> None:
	"""Apply one event to ``state = {"jobs": {id: job}, "order": [ids], "next": int}`` (pure)."""
	a, jobs, order = ev.get("action"), state["jobs"], state["order"]
	jid = ev.get("id")
	if a == "job_added":
		jobs[jid] = _new_job(ev)
		order.append(jid)
		try:
			state["next"] = max(state["next"], int(str(jid)[1:]) + 1)
		except ValueError:
			pass
		return
	j = jobs.get(jid)
	if j is None:
		return
	if a == "job_started":
		j.update(estado="a_correr", t_inicio=ev.get("t"), t_fim=None, resultados=[], n_pecas=0, erro=None)
		j["tentativas"] += 1
	elif a == "job_sheet":
		r = {k: ev.get(k) for k in ("k", "n", "caminho", "estado", "scan_id", "n_pecas", "avisos", "erro", "numeros", "t")}
		j["resultados"] = [x for x in j["resultados"] if x.get("k") != r["k"]] + [r]
		j["n_pecas"] = sum(int(x.get("n_pecas") or 0) for x in j["resultados"])
	elif a == "job_done":
		j.update(estado="concluido", t_fim=ev.get("t"), propostas=ev.get("propostas"), segundos=ev.get("segundos"),
				 wlock_folhas_s=ev.get("wlock_folhas_s"), wlock_consulta_s=ev.get("wlock_consulta_s"))
	elif a == "job_failed":
		j.update(estado="falhado", t_fim=ev.get("t"), erro=ev.get("erro"))
	elif a == "job_cancelled":
		j.update(estado="cancelado", t_fim=ev.get("t"))
	elif a == "job_retried":
		j.update(estado="em_fila", t_fim=None, erro=None)
		order.remove(jid)
		if ev.get("cabeca"):
			pend = [x for x in order if jobs[x]["estado"] == "em_fila"]
			order.insert(order.index(pend[0]) if pend else len(order), jid)
		else:
			order.append(jid)
	elif a == "job_moved":
		order.remove(jid)
		pend = [x for x in order if jobs[x]["estado"] == "em_fila"]
		pos = max(0, int(ev.get("posicao") or 0))
		if pos < len(pend):
			order.insert(order.index(pend[pos]), jid)
		elif pend:
			order.insert(order.index(pend[-1]) + 1, jid)
		else:
			order.append(jid)


class ImportQueue:
	"""The queue of one project (``path`` = its ``import_queue.jsonl``; created on the first event)."""

	def __init__(self, path: str):
		self.path = path
		self.load()

	# ------------------------------------------------------------ log
	def load(self) -> None:
		"""Replay the file (a missing file = an empty queue; an unreadable line is skipped)."""
		self.state = {"jobs": {}, "order": [], "next": 1}
		if not os.path.exists(self.path):
			return
		with open(self.path, encoding="utf-8") as f:
			for line in f:
				line = line.strip()
				if not line:
					continue
				try:
					ev = json.loads(line)
				except ValueError:
					continue
				apply_event(self.state, ev)

	def _emit(self, action: str, **data) -> dict:
		if action not in EVENTOS:
			raise QueueError(f"evento desconhecido {action!r}")
		ev = {"t": _now(), "action": action, **data}
		ev = json.loads(json.dumps(ev, ensure_ascii=False, default=str))
		apply_event(self.state, ev)
		os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
		with open(self.path, "a", encoding="utf-8", newline="\n") as f:
			f.write(json.dumps(ev, ensure_ascii=False) + "\n")
		return ev

	# ------------------------------------------------------------ reads
	def job(self, jid: str) -> dict:
		j = self.state["jobs"].get(jid)
		if j is None:
			raise QueueError(f"trabalho desconhecido {jid}")
		return j

	def pending(self) -> list:
		"""Ids ``em_fila`` in queue order."""
		return [x for x in self.state["order"] if self.state["jobs"][x]["estado"] == "em_fila"]

	def running(self) -> Optional[str]:
		return next((x for x in self.state["order"] if self.state["jobs"][x]["estado"] == "a_correr"), None)

	def next_job(self) -> Optional[dict]:
		"""The first ``em_fila`` job (None when the queue is empty)."""
		p = self.pending()
		return self.state["jobs"][p[0]] if p else None

	def snapshot(self) -> list:
		"""Jobs for the GUI: the running one, then the queue in order (``posicao`` 0..), then the finished ones (most
		recent first). Each: ``{id, lote, estado, posicao, folhas_total, folhas_feitas, progresso "k/n", n_pecas,
		propostas, avisos, erro, t_adicionado, t_inicio, t_fim, segundos, tentativas, ficheiros, folhas, resultados}``."""
		jobs, out = self.state["jobs"], []
		run = [x for x in self.state["order"] if jobs[x]["estado"] == "a_correr"]
		pend = self.pending()
		done = sorted((x for x in self.state["order"] if jobs[x]["estado"] in ("concluido", "falhado", "cancelado")),
					  key=lambda x: (jobs[x]["t_fim"] or "", x), reverse=True)
		for x in run + pend + done:
			j = jobs[x]
			n = len(j["folhas"])
			k = len(j["resultados"])
			av = list(j["avisos"]) + [a for r in j["resultados"] for a in (r.get("avisos") or [])]
			out.append({"id": x, "lote": j["lote"], "estado": j["estado"],
						"posicao": pend.index(x) if x in pend else None, "folhas_total": n, "folhas_feitas": k,
						"progresso": f"{k}/{n}", "n_pecas": j["n_pecas"], "propostas": j["propostas"], "avisos": av,
						"erro": j["erro"] or next((r.get("erro") for r in j["resultados"] if r.get("erro")), None),
						"t_adicionado": j["t_adicionado"], "t_inicio": j["t_inicio"], "t_fim": j["t_fim"],
						"segundos": j["segundos"], "tentativas": j["tentativas"], "ficheiros": j["ficheiros"],
						"folhas": j["folhas"], "resultados": j["resultados"]})
		return out

	def summary(self) -> dict:
		""" ``{n_em_fila, a_correr}`` (``GET /api/status``)."""
		return {"n_em_fila": len(self.pending()), "a_correr": self.running()}

	# ------------------------------------------------------------ writes
	def add(self, lote, ficheiros, folhas, *, dpi=None, avisos=None) -> str:
		"""Append a job at the end of the queue; returns its id."""
		jid = f"Q{self.state['next']:04d}"
		self._emit("job_added", id=jid, lote=lote, ficheiros=list(ficheiros), folhas=[dict(f) for f in folhas], dpi=dpi,
				   avisos=list(avisos or []))
		return jid

	def cancel(self, jid: str) -> dict:
		"""Cancel a job that has not started (only ``em_fila``)."""
		j = self.job(jid)
		if j["estado"] != "em_fila":
			raise QueueError(f"{jid} está {j['estado']}: só um trabalho em fila pode ser cancelado")
		return self._emit("job_cancelled", id=jid)

	def move(self, jid: str, posicao: int) -> dict:
		"""Move a queued job to position ``posicao`` (0 = next) among the queued ones."""
		j = self.job(jid)
		if j["estado"] != "em_fila":
			raise QueueError(f"{jid} está {j['estado']}: só um trabalho em fila pode mudar de posição")
		return self._emit("job_moved", id=jid, posicao=max(0, int(posicao)))

	def retry(self, jid: str, motivo: str = "utilizador", *, cabeca: bool = False) -> dict:
		"""Put a failed / cancelled job back in the queue (at the end, or at the head with ``cabeca``)."""
		j = self.job(jid)
		if j["estado"] not in ("falhado", "cancelado"):
			raise QueueError(f"{jid} está {j['estado']}: só um trabalho falhado ou cancelado pode ser repetido")
		return self._emit("job_retried", id=jid, motivo=motivo, cabeca=bool(cabeca))

	def start(self, jid: str) -> dict:
		j = self.job(jid)
		if j["estado"] != "em_fila":
			raise QueueError(f"{jid} está {j['estado']}: não pode começar")
		return self._emit("job_started", id=jid)

	def sheet(self, jid: str, k: int, n: int, *, caminho=None, estado: str, scan_id=None, n_pecas: int = 0, avisos=None,
			  erro=None, numeros=None) -> dict:
		if estado not in ("ok", "ignorada", "erro"):
			raise QueueError(f"estado de folha inválido {estado!r}")
		return self._emit("job_sheet", id=jid, k=int(k), n=int(n), caminho=caminho, estado=estado, scan_id=scan_id,
						  n_pecas=int(n_pecas or 0), avisos=list(avisos or []), erro=erro, numeros=numeros)

	def done(self, jid: str, *, n_folhas: int, n_pecas: int, propostas=None, segundos=None, **extra) -> dict:
		"""``extra``: measurements kept in the event (the server: ``wlock_folhas_s``, ``wlock_consulta_s``)."""
		return self._emit("job_done", id=jid, n_folhas=int(n_folhas), n_pecas=int(n_pecas), propostas=propostas,
						  segundos=None if segundos is None else round(float(segundos), 1), **extra)

	def fail(self, jid: str, erro: str) -> dict:
		return self._emit("job_failed", id=jid, erro=str(erro))

	def recover(self) -> list:
		"""Jobs left ``a_correr`` (the server stopped mid-job) go back to the head of the queue, in their order.
		Returns their ids. A sheet already committed is not imported again (the sha256 makes it ``ignorada``)."""
		run = [x for x in self.state["order"] if self.state["jobs"][x]["estado"] == "a_correr"]
		for x in reversed(run):                    # each to the head: the original order is kept
			self._emit("job_retried", id=x, motivo="reinicio", cabeca=True)
		return run
