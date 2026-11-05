"""Reports from the GUI ("Reportar"): problems Tiago flags while using the program.

Each report is one JSON line in ``projects/<id>/reports.jsonl`` (ids ``R0001``...), with a
capture of what he was looking at in ``projects/<id>/reports/``. The log gets an
informative ``report`` / ``report_closed`` event (no state change). At the start of each
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

__all__ = ["TIPOS", "reports_path", "read_reports", "next_report_id", "add_report", "list_reports", "close_report", "edit_report"]

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


def read_reports(project) -> list:
	"""The reports with their edit events applied in order (``tipo`` / ``texto`` replaced, ``editado_em`` and
	``n_edicoes`` set); the edit events themselves are not reports."""
	out, by_id = [], {}
	for r in _read_raw(project):
		if r.get("evento") == "edicao":
			t = by_id.get(r.get("id"))
			if t is None:
				continue
			for k in ("tipo", "texto"):
				if r.get(k) is not None:
					t[k] = r[k]
			t["editado_em"] = r.get("t")
			t["n_edicoes"] = int(t.get("n_edicoes") or 0) + 1
		else:
			by_id[r.get("id")] = r
			out.append(r)
	return out


def _write_all(project, rows: list) -> None:
	fp = reports_path(project)
	tmp = fp + ".tmp"
	with open(tmp, "w", encoding="utf-8", newline="\n") as f:
		for r in rows:
			f.write(json.dumps(r, ensure_ascii=False) + "\n")
	os.replace(tmp, fp)


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


def list_reports(project, only_open: bool = True) -> list:
	return [r for r in read_reports(project) if not only_open or r.get("estado") == "aberto"]


def close_report(project, report_id: str, nota: str = "") -> dict:
	"""Mark a report closed (rewrites its line, the edit events are kept) and log ``report_closed``."""
	raw = _read_raw(project)
	for r in raw:
		if r.get("id") == report_id and r.get("evento") != "edicao":
			if r.get("estado") == "fechado":
				return {"error": f"{report_id} já está fechado"}
			r.update(estado="fechado", fechado_em=_now(), nota=nota or "")
			_write_all(project, raw)
			project.log_event("report_closed", report_id=report_id, nota=nota or "")
			return next(x for x in read_reports(project) if x.get("id") == report_id)
	return {"error": f"relatório desconhecido {report_id}"}


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
		return {"error": f"{report_id} já está fechado"}
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
	ap.add_argument("--close", metavar="R####")
	ap.add_argument("--nota", default="")
	a = ap.parse_args(argv)
	from src.state import Project
	pr = Project.open(a.project)
	if a.close:
		r = close_report(pr, a.close, a.nota)
		print(json.dumps(r, ensure_ascii=False))
		return 1 if "error" in r else 0
	for r in list_reports(pr, only_open=not a.all):
		where = f"célula {tuple(r['cell'])}" if r.get("cell") else "-"
		pc = f"{r['piece']} (saco {r.get('lote')} nº {r.get('n_no_lote')})" if r.get("piece") else "-"
		print(f"{r['id']} [{r['estado']}] {TIPOS.get(r['tipo'], r['tipo'])} · {pc} · {where} · vista {r.get('vista')}")
		if r.get("texto"):
			print(f"    {r['texto']}")
		if r.get("captura"):
			print(f"    captura: {r['captura']}")
	return 0


if __name__ == "__main__":
	sys.exit(main())
