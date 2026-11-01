"""Confirm or reject a suggestion and re-query only what it affects (``python -m src.confirm``).

Usage::

	python -m src.confirm P0123 --cell L C [--origin gemeo]
	python -m src.confirm P0123 --reject
	python -m src.confirm P0123 --position-known L C
	python -m src.confirm --anchor G0003 L C --rot R [--mirror]
	python -m src.confirm --unanchor G0003
	python -m src.confirm P0123 --discard
	python -m src.confirm --relot S0007 S0008 --lote 2

After the change the invariants are checked and :func:`src.query.run_query` is re-run
incrementally on the affected cells (the changed cells and their twins) and pieces
(the piece and its pair partner); ``fetch.md`` is rewritten. Neighbour cells are reported
(``neighbour_cells``) for the hole step (M11) but not re-queried yet.

Pair rule: placing a piece of an active pair confirms the pair and gives the partner its
cell (``profile.twin`` of the new cell) as ``posicao_conhecida``, origin ``par``.

``--relot`` (:func:`relot`) moves whole sheets to another bag (``Project.set_lote``: continuous
renumbering in the target bag, the sheets left behind keep their numbers) and rewrites their
numbered overlays. It does not re-query: the twin/pair steps do not depend on the bag, only the
``lote`` / ``n_no_lote`` printed in ``fetch.md`` do, so re-run ``python -m src.query`` to refresh it.
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional

__all__ = ["confirm", "relot", "main"]

_CONFIRM_ACTION = {"gemeo": "twin_confirmed", "borda": "twin_confirmed", "par": "twin_confirmed",
				   "buraco": "hole_confirmed", "fronteira": "hole_confirmed"}
_REJECT_ACTION = {"gemeo": "twin_rejected", "borda": "twin_rejected", "buraco": "hole_rejected",
				  "fronteira": "hole_rejected"}


def _fetch_entries(pr, pid: str) -> list:
	from src.query import load_fetch
	return [e for e in load_fetch(pr).get("entries", []) if e.get("piece") == pid]


def _active_pair(pr, pid: str):
	for t in sorted(pr.pairs.values(), key=lambda t: t.id):
		if t.estado != "rejeitado" and pid in (t.a, t.b):
			return t
	return None


def _around(pr, cell) -> set:
	"""The changed cell and its twin cell (what the twin / border steps re-query)."""
	out = {tuple(cell)}
	tw = pr.profile.twin(*cell)
	if tw:
		out.add(tw)
	return out


def confirm(pr, piece_id: Optional[str] = None, *, cell=None, origin: Optional[str] = None, reject: bool = False,
			position_known=None, anchor=None, rot: int = 0, mirror: bool = False, unanchor: Optional[str] = None,
			discard: bool = False, reason: str = "", requery: bool = True, use_image: bool = True) -> dict:
	"""Apply one confirmation; returns ``{messages, affected_cells, affected_pieces, entries, invariants}``
	or ``{'error': str}`` (nothing applied in that case, except steps already logged before the error)."""
	msgs, cells, pieces = [], set(), set()
	try:
		if cell is not None:
			cell = (int(cell[0]), int(cell[1]))
			ent = [e for e in _fetch_entries(pr, piece_id) if e.get("cell") and tuple(e["cell"]) == cell]
			e0 = ent[0] if ent else {}
			org = origin or e0.get("origin") or "manual"
			pair = _active_pair(pr, piece_id)
			pr.place(piece_id, cell, origin=org, rank=e0.get("rank"), score=e0.get("score"))
			msgs.append(f"{piece_id} colocada em {cell} (origem {org})")
			if org in _CONFIRM_ACTION:
				pr.log_event(_CONFIRM_ACTION[org], piece=piece_id, cell=cell, origin=org, query=e0.get("query"))
			cells |= _around(pr, cell)
			pieces.add(piece_id)
			if pair is not None:
				other = pair.b if pair.a == piece_id else pair.a
				pieces.add(other)
				if pair.estado == "proposto":
					pr.confirm_pair(pair.id)
				tw = pr.profile.twin(*cell)
				if tw and pr.board[tw]["estado"] == "vazia" and pr.piece(other).estado in ("solta", "emparelhada"):
					pr.set_position_known(other, tw, origin="par")
					msgs.append(f"par {pair.id}: {other} fica com posição conhecida {tw}")
					cells |= _around(pr, tw)
		elif reject:
			ents = _fetch_entries(pr, piece_id)
			if not ents:
				return {"error": f"{piece_id} não tem proposta na lista atual"}
			for e in ents:
				if e["origin"] == "par" and e.get("pair") in pr.pairs and pr.pairs[e["pair"]].estado != "rejeitado":
					t = pr.pairs[e["pair"]]
					pr.reject_pair(t.id)
					pieces.update((t.a, t.b))
					msgs.append(f"par {t.id} rejeitado")
				elif e["origin"] in _REJECT_ACTION:
					pr.log_event(_REJECT_ACTION[e["origin"]], piece=piece_id, cell=e.get("cell"), origin=e["origin"],
								 query=e.get("query"))
					msgs.append(f"{piece_id} rejeitada para {tuple(e['cell']) if e.get('cell') else '-'} ({e['origin']})")
					if e.get("cell"):
						cells.add(tuple(e["cell"]))
			pieces.add(piece_id)
		elif position_known is not None:
			pc = (int(position_known[0]), int(position_known[1]))
			pr.set_position_known(piece_id, pc, origin=origin or "manual")
			msgs.append(f"{piece_id} posição conhecida {pc}")
			pieces.add(piece_id)
			cells |= _around(pr, pc)
		elif anchor is not None:
			gid, l0, c0 = anchor[0], int(anchor[1]), int(anchor[2])
			ev = pr.anchor_section(gid, l0, c0, rot=rot, mirror=mirror, fonte="manual", confianca="confirmado")
			msgs.append(f"{gid} ancorada em ({l0},{c0}) rot {rot} mirror {mirror}: {len(ev['placements'])} peças colocadas")
			for c in ev["conflicts"]:
				msgs.append(f"CONFLITO: {c['piece']} → {tuple(c['cell'])} já tem {c['occupant']} (não sobrescrito)")
			for pl in ev["placements"]:
				cells |= _around(pr, tuple(pl["cell"]))
		elif unanchor is not None:
			ev = pr.unanchor_section(unanchor)
			msgs.append(f"{unanchor} desancorada: {len(ev['placements'])} peças voltam a em_seccao")
			for pl in ev["placements"]:
				cells |= _around(pr, tuple(pl["cell"]))
		elif discard:
			pr.discard(piece_id, reason)
			msgs.append(f"{piece_id} descartada")
			pieces.add(piece_id)
		else:
			return {"error": "nada a fazer (indica --cell, --reject, --position-known, --anchor, --unanchor ou --discard)"}
	except ValueError as e:
		pr.save()
		return {"error": str(e)}
	pr.save()
	bad = pr.check_invariants(disk=True)
	# 4-neighbours of the changed cells: their hole moulds change (M11, not built yet); the
	# known-position step (3) is recomputed in full on every run, so they are only reported.
	neigh = sorted({n for c in cells for n in pr.board.neighbours(c)} - cells)
	entries = []
	if requery and not bad:
		from src.query import run_query
		entries = run_query(pr, only_cells=cells, only_pieces=pieces, use_image=use_image)
	return {"messages": msgs, "affected_cells": sorted(cells), "neighbour_cells": neigh,
			"affected_pieces": sorted(pieces), "entries": entries, "invariants": bad}


def relot(pr, scan_ids, lote, *, overlays: bool = True) -> dict:
	"""Move ``scan_ids`` to bag ``lote`` (renumbered), save, rewrite their overlays.

	Returns ``{event, numbers: {pid: (old_lote, old_n, new_lote, new_n)}, overlays, invariants}``
	or ``{'error': str}`` (nothing logged).
	"""
	from src.ingest import write_overlay
	old = {p.id: (p.lote, p.n_no_lote) for p in pr.pieces.values() if p.scan_id in set(scan_ids)}
	try:
		ev = pr.set_lote(scan_ids, lote, renumber=True)
	except ValueError as e:
		return {"error": str(e)}
	pr.save()
	paths, errs = [], []
	if overlays:
		for sid in ev["scan_ids"]:
			try:
				paths.append(write_overlay(pr, sid))
			except ValueError as e:
				errs.append(f"overlay {sid}: {e}")
	nums = {pid: (*old[pid], pr.piece(pid).lote, pr.piece(pid).n_no_lote) for pid in sorted(old)}
	return {"event": ev, "numbers": nums, "overlays": paths, "overlay_errors": errs,
			"invariants": pr.check_invariants(disk=True)}


def main(argv=None) -> int:
	from src.ingest import add_project_args, open_project
	ap = argparse.ArgumentParser(prog="python -m src.confirm", description="Confirma/rejeita uma sugestão.")
	ap.add_argument("piece_id", nargs="?", default=None)
	g = ap.add_mutually_exclusive_group(required=True)
	g.add_argument("--cell", nargs=2, type=int, metavar=("L", "C"))
	g.add_argument("--reject", action="store_true")
	g.add_argument("--position-known", nargs=2, type=int, metavar=("L", "C"))
	g.add_argument("--anchor", nargs=3, metavar=("G", "L", "C"))
	g.add_argument("--unanchor", metavar="G")
	g.add_argument("--discard", action="store_true")
	g.add_argument("--relot", nargs="+", metavar="S", help="scans (folhas) a mudar de lote; exige --lote")
	ap.add_argument("--lote", type=int, default=None, help="lote de destino de --relot")
	ap.add_argument("--origin", default=None, help="gemeo | par | borda | buraco | manual (omissão: a da lista)")
	ap.add_argument("--rot", type=int, default=0)
	ap.add_argument("--mirror", action="store_true")
	ap.add_argument("--reason", default="")
	ap.add_argument("--no-image", action="store_true")
	ap.add_argument("--no-requery", action="store_true")
	add_project_args(ap)
	args = ap.parse_args(argv)
	if args.relot:
		if args.lote is None:
			print("erro: --relot exige --lote N")
			return 1
		pr = open_project(args)
		r = relot(pr, args.relot, args.lote)
		if "error" in r:
			print(f"erro: {r['error']}")
			return 1
		for sid in r["event"]["scan_ids"]:
			ns = [v[3] for pid, v in r["numbers"].items() if pr.piece(pid).scan_id == sid]
			print(f"{sid} -> lote {args.lote}: {len(ns)} peças #{min(ns)}-{max(ns)}" if ns else f"{sid}: sem peças")
		for pid, (l0, n0, l1, n1) in r["numbers"].items():
			print(f"  {pid}: lote {l0} #{n0} -> lote {l1} #{n1}")
		for pth in r["overlays"]:
			print(f"overlay: {pth}")
		for e in r["overlay_errors"]:
			print(f"AVISO: {e}")
		if r["invariants"]:
			print("INVARIANTES VIOLADAS: " + "; ".join(r["invariants"]))
			return 1
		print("fetch.md/fetch.json ainda têm os números antigos: corre `python -m src.query` para os atualizar")
		return 0
	needs_piece = args.cell or args.reject or args.position_known or args.discard
	if needs_piece and not args.piece_id:
		print("erro: falta o id da peça")
		return 1
	try:
		pr = open_project(args)
		r = confirm(pr, args.piece_id, cell=args.cell, origin=args.origin, reject=args.reject,
					position_known=args.position_known, anchor=args.anchor, rot=args.rot, mirror=args.mirror,
					unanchor=args.unanchor, discard=args.discard, reason=args.reason,
					requery=not args.no_requery, use_image=not args.no_image)
	except ImportError as e:
		print(f"aplicado, mas a nova consulta falhou: {e}")
		return 1
	if "error" in r:
		print(f"erro: {r['error']}")
		return 1
	for m in r["messages"]:
		print(m)
	if r["invariants"]:
		print("INVARIANTES VIOLADAS: " + "; ".join(r["invariants"]))
		return 1
	if not args.no_requery:
		from src.query import print_summary
		print(f"reconsulta: células {r['affected_cells']}, peças {r['affected_pieces']}")
		print_summary(pr, r["entries"])
	return 0


if __name__ == "__main__":
	sys.exit(main())
