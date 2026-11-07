"""Reports from the GUI ("Reportar"): problems Tiago flags while using the program.

Each report is one JSON line in ``projects/<id>/reports.jsonl`` (ids ``R0001``...), with a
capture of what he was looking at in ``projects/<id>/reports/``. The log gets an
informative ``report`` / ``report_closed`` / ``report_reopened`` / ``report_deleted`` / ``report_restored`` event
(no state change). ``reports.jsonl`` is append-only (state changes are ``{"evento": "estado"}`` lines). At the start of each
working session the open reports are the work list::

	python -m src.reports --project projects/alpes --list
	python -m src.reports --project projects/alpes --close R0001 --nota "corrigido em ..."
"""

import argparse
import datetime
import json
import os
import sys
from typing import Optional

__all__ = ["TIPOS", "reports_path", "read_reports", "next_report_id", "add_report", "list_reports", "close_report", "edit_report", "set_state"]

TIPOS = {"mal_lida": "mal lida / mal recortada", "mal_colocada": "mal colocada",
		 "nao_encaixa": "não encaixa", "outro": "outro"}


# ---------------------------------------------------------------- pure helpers
def next_report_id(rows: list) -> str:
	"""``R####`` following the highest id in ``rows``."""
	n = 0
	for r in rows:
		try:
			n = max(n, int(str(r.get("id", ""))[1:]))
		except ValueError:
			pass
	return f"R{n + 1:04d}"


def _now() -> str:
	return datetime.datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- I/O
def reports_path(project) -> str:
	return os.path.join(project.path, "reports.jsonl")


def _read_raw(project) -> list:
	"""Every line of ``reports.jsonl``: the reports and the edit events (``evento == "edicao"``)."""
	fp = reports_path(project)
	if not os.path.exists(fp):
		return []
	out = []
	with open(fp, encoding="utf-8") as f:
		for line in f:
			line = line.strip()
			if line:
				out.append(json.loads(line))
	return out


# (action) -> (allowed current states, log action)
_ACOES = {"close": (("aberto",), "report_closed"), "reopen": (("fechado",), "report_reopened"),
		  "delete": (("aberto", "fechado"), "report_deleted"), "restore": (("eliminado",), "report_restored")}


def read_reports(project) -> list:
	"""The reports with their edit events and state events applied in order (``tipo`` / ``texto`` replaced,
	``editado_em`` / ``n_edicoes``; ``estado`` / ``nota`` / ``fechado_em`` / ``reaberto_em`` / ``eliminado_em`` /
	``restaurado_em`` / ``estado_anterior`` / ``n_estados`` / ``historico``); the events themselves are not reports."""
	out, by_id = [], {}
	for r in _read_raw(project):
		ev = r.get("evento")
		if ev in ("edicao", "estado"):
			t = by_id.get(r.get("id"))
			if t is None:
				continue
		if ev == "edicao":
			for k in ("tipo", "texto"):
				if r.get(k) is not None:
					t[k] = r[k]
			t["editado_em"] = r.get("t")
			t["n_edicoes"] = int(t.get("n_edicoes") or 0) + 1
		elif ev == "estado":
			novo = r.get("estado")
			t.setdefault("historico", [])
			if not t["historico"] and t.get("estado") == "fechado" and t.get("fechado_em"):
				t["historico"].append({"estado": "fechado", "t": t["fechado_em"], "nota": t.get("nota", "")})
			t["historico"].append({"estado": novo, "t": r.get("t"), "nota": r.get("nota", "")})
			t["estado"] = novo
			if r.get("nota") or r.get("acao") == "close":     # a delete / restore without note keeps the closing note
				t["nota"] = r.get("nota") or ""
			if novo == "fechado":
				t["fechado_em"] = r.get("t")
			elif novo == "eliminado":
				t["eliminado_em"] = r.get("t")
				t["estado_anterior"] = r.get("estado_anterior")
			elif r.get("acao") == "restore":
				t["restaurado_em"] = r.get("t")
			else:
				t["reaberto_em"] = r.get("t")
			t["n_estados"] = int(t.get("n_estados") or 0) + 1
		else:
			by_id[r.get("id")] = r
			out.append(r)
	return out


def add_report(project, *, tipo: str, texto: str = "", piece: Optional[str] = None, cell=None,
			   scan_id: Optional[str] = None, vista: Optional[str] = None, captura_path: Optional[str] = None) -> dict:
	"""Append a report and log a ``report`` event; returns the report dict or ``{'error': str}``."""
	if tipo not in TIPOS:
		return {"error": f"tipo desconhecido {tipo!r} (um de {', '.join(TIPOS)})"}
	rows = read_reports(project)
	rid = next_report_id(rows)
	p = project.pieces.get(piece) if piece else None
	rep = {"id": rid, "t": _now(), "tipo": tipo, "texto": texto or "", "piece": piece,
		   "cell": list(cell) if cell else None, "scan_id": scan_id or (p.scan_id if p else None),
		   "n_no_lote": p.n_no_lote if p else None, "lote": p.lote if p else None,
		   "crop_path": getattr(p, "crop_path", None) if p else None,
		   "captura": captura_path, "vista": vista, "estado": "aberto"}
	with open(reports_path(project), "a", encoding="utf-8", newline="\n") as f:
		f.write(json.dumps(rep, ensure_ascii=False) + "\n")
	project.log_event("report", report_id=rid, tipo=tipo, piece=piece, cell=rep["cell"])
	return rep


def list_reports(project, only_open: bool = True, eliminados: bool = False) -> list:
	"""Open reports (``only_open``) or all of them; the deleted ones only with ``eliminados=True``."""
	out = []
	for r in read_reports(project):
		e = r.get("estado")
		if e == "eliminado":
			if eliminados:
				out.append(r)
		elif not only_open or e == "aberto":
			out.append(r)
	return out


def set_state(project, report_id: str, acao: str, nota: str = "") -> dict:
	"""Change a report's state by appending ONE ``{"evento": "estado", ...}`` line to ``reports.jsonl`` and ONE
	event to the log. ``acao``: ``close`` (aberto -> fechado), ``reopen`` (fechado -> aberto), ``delete``
	(aberto|fechado -> eliminado, remembers ``estado_anterior``), ``restore`` (eliminado -> estado_anterior).
	Returns the folded report or ``{'error': str}``."""
	if acao not in _ACOES:
		return {"error": f"ação desconhecida {acao!r} (uma de {', '.join(_ACOES)})"}
	cur = next((r for r in read_reports(project) if r.get("id") == report_id), None)
	if cur is None:
		return {"error": f"relatório desconhecido {report_id}"}
	estado = cur.get("estado")
	permitidos, log_action = _ACOES[acao]
	if estado not in permitidos:
		if acao == "close" and estado == "fechado":
			return {"error": f"{report_id} já está fechado"}
		if acao == "close" and estado == "eliminado":
			return {"error": f"{report_id} está eliminado"}
		return {"error": f"{report_id} está {estado}: não se pode fazer {acao}"}
	ev = {"evento": "estado", "id": report_id, "t": _now(), "acao": acao, "nota": nota or ""}
	if acao == "close":
		ev["estado"] = "fechado"
	elif acao == "reopen":
		ev["estado"] = "aberto"
	elif acao == "delete":
		ev["estado"] = "eliminado"
		ev["estado_anterior"] = estado
	else:
		ev["estado"] = cur.get("estado_anterior") or "aberto"
	with open(reports_path(project), "a", encoding="utf-8", newline="\n") as f:
		f.write(json.dumps(ev, ensure_ascii=False) + "\n")
	project.log_event(log_action, report_id=report_id, nota=nota or "")
	return next(x for x in read_reports(project) if x.get("id") == report_id)


def close_report(project, report_id: str, nota: str = "") -> dict:
	"""Mark a report closed (compat: ``set_state(..., "close", nota)``)."""
	return set_state(project, report_id, "close", nota)


def edit_report(project, report_id: str, *, tipo: Optional[str] = None, texto: Optional[str] = None) -> dict:
	"""Edit an OPEN report: appends an edit event line (``{"evento": "edicao", "id", "t", "tipo"?, "texto"?}``)
	to ``reports.jsonl`` (append-only: the original line is never rewritten) and logs ``report_edited``.
	Returns the report as edited, or ``{'error': str}``."""
	if tipo is not None and not isinstance(tipo, str):
		return {"error": "tipo deve ser texto"}
	if texto is not None and not isinstance(texto, str):
		return {"error": "texto deve ser texto"}
	if tipo is not None and tipo not in TIPOS:
		return {"error": f"tipo desconhecido {tipo!r} (um de {', '.join(TIPOS)})"}
	cur = next((r for r in read_reports(project) if r.get("id") == report_id), None)
	if cur is None:
		return {"error": f"relatório desconhecido {report_id}"}
	if cur.get("estado") != "aberto":
		return {"error": f"{report_id} não está aberto (estado {cur.get('estado')})"}
	if tipo is None and texto is None:
		return {"error": "nada para editar"}
	ev = {"evento": "edicao", "id": report_id, "t": _now()}
	if tipo is not None:
		ev["tipo"] = tipo
	if texto is not None:
		ev["texto"] = texto
	with open(reports_path(project), "a", encoding="utf-8", newline="\n") as f:
		f.write(json.dumps(ev, ensure_ascii=False) + "\n")
	project.log_event("report_edited", report_id=report_id, campos=[k for k in ("tipo", "texto") if k in ev])
	return next(r for r in read_reports(project) if r.get("id") == report_id)


def main(argv=None) -> int:
	ap = argparse.ArgumentParser(prog="python -m src.reports", description=__doc__.split("\n")[0])
	ap.add_argument("--project", default="projects/alpes")
	ap.add_argument("--list", action="store_true", help="list the open reports")
	ap.add_argument("--all", action="store_true", help="with --list: include the closed ones")
	ap.add_argument("--eliminados", action="store_true", help="with --list: include the deleted ones")
	ap.add_argument("--close", metavar="R####")
	ap.add_argument("--reopen", metavar="R####")
	ap.add_argument("--delete", metavar="R####")
	ap.add_argument("--restore", metavar="R####")
	ap.add_argument("--nota", default="")
	a = ap.parse_args(argv)
	from src.state import Project
	pr = Project.open(a.project)
	for acao in ("close", "reopen", "delete", "restore"):
		rid = getattr(a, acao)
		if rid:
			r = set_state(pr, rid, acao, a.nota)
			print(json.dumps(r, ensure_ascii=False))
			return 1 if "error" in r else 0
	for r in list_reports(pr, only_open=not a.all, eliminados=a.eliminados):
		where = f"célula {tuple(r['cell'])}" if r.get("cell") else "-"
		pc = r["piece"] if r.get("piece") else "-"
		print(f"{r['id']} [{r['estado']}] {TIPOS.get(r['tipo'], r['tipo'])} · {pc} · {where}")
		if r.get("texto"):
			print(f"    {r['texto']}")
		if r.get("captura"):
			print(f"    captura: {r['captura']}")
	return 0


if __name__ == "__main__":
	sys.exit(main())
