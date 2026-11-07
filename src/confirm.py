"""Confirm or reject a suggestion and re-query only what it affects (``python -m src.confirm``).

Usage::

	python -m src.confirm P0123 --cell L C [--origin gemeo] [--theta DEG]
	python -m src.confirm P0123 --unplace
	python -m src.confirm P0123 --reject
	python -m src.confirm P0123 --position-known L C
	python -m src.confirm --anchor G0003 L C --rot R [--mirror]
	python -m src.confirm --unanchor G0003
	python -m src.confirm P0123 --discard
	python -m src.confirm --relot S0007 S0008 --lote 2
	python -m src.confirm --cheia L,C [L,C ...]      # the user says these cells are assembled
	python -m src.confirm --vazia L,C [L,C ...]      # the user says these cells are empty
	python -m src.confirm P0123 --pose THETA DX DY [--nota TXT]   # manual board pose of a placed piece
	python -m src.confirm P0123 --pose-repor                      # back to the automatic pose

``--cheia`` / ``--vazia`` (also ``python -m src.photo --cheia/--vazia``) log
``cell_occupied_by_user`` / ``cell_cleared_by_user`` (ground truth, ``fonte='tiago'``; see the
doubt policy in :mod:`src.state`) and re-query the cells and their twins.

After the change the invariants are checked and :func:`src.query.run_query` is re-run
incrementally on the affected cells (the changed cells, their twins and the free 4-neighbours
of both) and pieces (the piece and its pair partner); ``fetch.md`` is rewritten. The twin /
border queries whose candidates left the loose pool are re-run by ``run_query`` itself
(``cand_ids``). Neighbour cells are also reported (``neighbour_cells``) for the hole step (M11).

Pair rule: placing a piece of an active pair confirms the pair and gives the partner its
cell (``profile.twin`` of the new cell) as ``posicao_conhecida``, origin ``par``.

Pose rule: placing (or keeping aside) a piece for a cell the list proposed stores the list's
board pose (``theta_deg`` of the fetch entry, only when ``pose_known``) in the ``placed`` /
``position_known`` event, so the board render starts from it (:func:`src.render.initial_theta`).
A pair partner gets a pose only if the list has one for it in the twin cell (pair entries carry
no pose today).

``--theta DEG`` (with ``--cell``) gives the board pose when the list has none for that cell (e.g. a
correction of a wrong orientation: ``--unplace`` then ``--cell L C --theta DEG``); with a list pose for the
cell it is refused (the list pose is the measured one). ``--unplace`` (:meth:`src.state.Project.unplace`)
takes a placed loose piece back to the pool (its cell gets back its previous state); a piece of a
section is refused (use ``--unanchor``).

``--pose THETA DX DY`` (:meth:`src.state.Project.set_pose`, event ``pose_set``): the board pose of a
``colocada`` piece (a loose one, or a piece of an anchored section: both are ``colocada``) set by hand,
``x_board = R(theta) (x_scan - pivot) + centre(cell) + (dx, dy)`` (degrees clockwise on the screen, board mm,
y down; the pivot is the one of the pose shown now); ``--pose-repor`` (``pose_cleared``) goes back to the
automatic registration. Both re-query the cell, its twin cell and their free neighbours (the twin's proposal
pose and ghost follow this pose).

``--relot`` (:func:`relot`) moves whole sheets to another bag (``Project.set_lote``: continuous
renumbering in the target bag, the sheets left behind keep their numbers) and rewrites their
numbered overlays. It does not re-query: the twin/pair steps do not depend on the bag, only the
``lote`` / ``n_no_lote`` printed in ``fetch.md`` do, so re-run ``python -m src.query`` to refresh it.
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional


AQUI_TXT = "É aqui"          # visible label of the action "this group goes here" (code/log ids keep "anchor")
__all__ = ["confirm", "relot", "parse_cells", "main"]

_CONFIRM_ACTION = {"gemeo": "twin_confirmed", "borda": "twin_confirmed", "par": "twin_confirmed",
				   "buraco": "hole_confirmed", "fronteira": "hole_confirmed"}
_REJECT_ACTION = {"gemeo": "twin_rejected", "borda": "twin_rejected", "buraco": "hole_rejected",
				  "fronteira": "hole_rejected"}


def _fetch_entries(pr, pid: str) -> list:
	from src.query import load_fetch
	return [e for e in load_fetch(pr).get("entries", []) if e.get("piece") == pid]


def _entry_theta(e: dict):
	"""Board pose of a fetch entry (``theta_deg``) when the list knows it, else None (never invented)."""
	if e and e.get("pose_known") and e.get("theta_deg") is not None:
		return float(e["theta_deg"])
	return None


def _cell_entry(pr, pid: str, cell) -> dict:
	"""The fetch entry of ``pid`` proposed for ``cell`` ({} if none)."""
	ent = [e for e in _fetch_entries(pr, pid) if e.get("cell") and tuple(e["cell"]) == tuple(cell)]
	return ent[0] if ent else {}


def _active_pair(pr, pid: str):
	for t in sorted(pr.pairs.values(), key=lambda t: t.id):
		if t.estado != "rejeitado" and pid in (t.a, t.b):
			return t
	return None


def _around(pr, cell) -> set:
	"""The changed cell, its twin cell and their free 4-neighbours (what the twin / border steps re-query:
	a pending twin or a missing border cell next to the change is re-evaluated, not carried over)."""
	out = {tuple(cell)}
	tw = pr.profile.twin(*cell)
	if tw:
		out.add(tuple(tw))
	for c in list(out):
		for nb in pr.board.neighbours(c):
			if not pr.board.occupied(nb):
				out.add(tuple(nb))
	return out


def parse_cells(items) -> list:
	"""``["3,10", "7,2"]`` (or ``"3,10 7,2"``) -> ``[(3, 10), (7, 2)]``."""
	out = []
	for s in items:
		for tok in str(s).replace(";", " ").split():
			try:
				l, c = tok.split(",")
				out.append((int(l), int(c)))
			except ValueError:
				raise ValueError(f"célula inválida {tok!r} (formato L,C)") from None
	return out


def confirm(pr, piece_id: Optional[str] = None, *, cell=None, origin: Optional[str] = None, reject: bool = False,
			position_known=None, anchor=None, rot: int = 0, mirror: bool = False, unanchor: Optional[str] = None,
			discard: bool = False, reason: str = "", cell_full=None, cell_empty=None, requery: bool = True,
			use_image: bool = True, unplace: bool = False, theta_deg: Optional[float] = None, pose=None,
			pose_repor: bool = False, nota: str = "", hole=None, hole_reject=None) -> dict:
	"""Apply one confirmation; returns ``{messages, affected_cells, affected_pieces, entries, invariants}``
	or ``{'error': str}`` (nothing applied in that case, except steps already logged before the error).

	``cell_full`` / ``cell_empty``: a list of cells the user marks assembled / empty
	(:meth:`src.state.Project.mark_cell_full` / ``mark_cell_empty``).

	``theta_deg`` (with ``cell``): board pose when the fetch entry of that cell has none (refused
	otherwise). ``unplace``: undo the placement of a loose piece (not of a section piece).

	``pose`` = ``(theta_deg, dx_mm, dy_mm)``: manual board pose of a placed piece (``nota`` stored with it);
	``pose_repor``: drop it (see the module docstring)."""
	msgs, cells, pieces = [], set(), set()
	try:
		if cell_full is not None or cell_empty is not None:
			for lst, full in ((cell_full or [], True), (cell_empty or [], False)):
				for cl in lst:
					cl = (int(cl[0]), int(cl[1]))
					ev = pr.mark_cell_full(cl) if full else pr.mark_cell_empty(cl)
					what = "cheia" if full else "vazia"
					msgs.append(f"{cl} já estava marcada {what}" if ev.get("action") == "noop"
								else f"{cl} marcada {what} (pista do utilizador)")
					cells |= _around(pr, cl)
		elif cell is not None:
			cell = (int(cell[0]), int(cell[1]))
			e0 = _cell_entry(pr, piece_id, cell)
			org = origin or e0.get("origin") or "manual"
			pair = _active_pair(pr, piece_id)
			th = _entry_theta(e0)
			if theta_deg is not None:
				if th is not None:
					return {"error": f"a lista já tem a pose {th:.2f}° de {piece_id} em {cell}: --theta não se aplica"}
				th = float(theta_deg)
			pr.place(piece_id, cell, origin=org, rank=e0.get("rank"), score=e0.get("score"), theta_deg=th)
			msgs.append(f"{piece_id} colocada em {cell} (origem {org}"
						+ (f", pose {th:.2f}°)" if th is not None else ")"))
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
				if tw and not pr.board.occupied(tw) and pr.piece(other).estado in ("solta", "emparelhada"):
					pr.set_position_known(other, tw, origin="par", theta_deg=_entry_theta(_cell_entry(pr, other, tw)))
					msgs.append(f"par {pair.id}: {other} fica com posição conhecida {tw}")
					cells |= _around(pr, tw)
		elif hole is not None or hole_reject is not None:
			# M11: a candidate of the «candidatas para este buraco» list, confirmed or refused physically.
			# ``hole`` / ``hole_reject`` = (cell, meta) with meta from src.fit (rank, custo, margem, confianca, m,
			# fit_version, theta_deg); the only write path for the CLI and the server.
			hc, meta = (hole if hole is not None else hole_reject)
			hc = (int(hc[0]), int(hc[1]))
			meta = dict(meta or {})
			if hole is not None:
				th = meta.get("theta_deg")
				pr.hole_confirm(piece_id, hc, meta=meta, theta_deg=(None if th is None else float(th)))
				msgs.append(f"{piece_id} colocada em {hc} (origem buraco, rank {meta.get('rank')}, confiança {meta.get('confianca')}"
							+ (f", pose {float(th):.2f}°)" if th is not None else ")"))
				cells |= _around(pr, hc)
			else:
				pr.hole_reject(piece_id, hc, meta=meta)
				msgs.append(f"{piece_id} rejeitada para o buraco {hc} (rank {meta.get('rank')}, confiança {meta.get('confianca')})")
				cells.add(hc)
			pieces.add(piece_id)
		elif unplace:
			p = pr.piece(piece_id)
			if p.seccao_id is not None:
				return {"error": f"{piece_id} é da secção {p.seccao_id}: usa --unanchor {p.seccao_id}"}
			if p.estado != "colocada" or p.celula is None:
				return {"error": f"{piece_id} está '{p.estado}': não está colocada"}
			c0 = tuple(p.celula)
			ev = pr.unplace(piece_id)
			msgs.append(f"{piece_id} retirada de {c0} (volta a '{ev['to']}'; a célula volta a '{ev['restore']['estado']}')")
			cells |= _around(pr, c0)
			pieces.add(piece_id)
		elif pose is not None or pose_repor:
			from src import render
			p = pr.piece(piece_id)
			if p.estado != "colocada" or p.celula is None:
				return {"error": f"{piece_id} está '{p.estado}': não está colocada"}
			e0 = render.effective_pose(pr, piece_id)
			if "error" in e0:
				return {"error": e0["error"]}
			antes = render.pose_brief(e0)
			if pose is not None:
				ev = pr.set_pose(piece_id, float(pose[0]), float(pose[1]), float(pose[2]), nota=nota, antes=antes,
								 pivot_mm=e0["pivot_mm"])
				msgs.append(f"{piece_id} em {tuple(p.celula)}: pose manual θ {ev['theta_deg']:.2f}°, "
							f"dx {ev['dx_mm']:+.2f} mm, dy {ev['dy_mm']:+.2f} mm (antes θ {antes['theta_deg']:.2f}°, "
							f"dx {antes['dx_mm']:+.2f}, dy {antes['dy_mm']:+.2f}, {antes['method']})")
			else:
				pr.clear_pose(piece_id, antes={k: antes[k] for k in ("theta_deg", "dx_mm", "dy_mm")})
				a = render.pose_brief(render.effective_pose(pr, piece_id))
				msgs.append(f"{piece_id} em {tuple(p.celula)}: pose manual retirada (θ {antes['theta_deg']:.2f}° → "
							f"automática θ {a['theta_deg']:.2f}°, {a['method']})")
			cells |= _around(pr, p.celula)
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
			pr.set_position_known(piece_id, pc, origin=origin or "manual", theta_deg=_entry_theta(_cell_entry(pr, piece_id, pc)))
			msgs.append(f"{piece_id} posição conhecida {pc}")
			pieces.add(piece_id)
			cells |= _around(pr, pc)
		elif anchor is not None:
			gid, l0, c0 = anchor[0], int(anchor[1]), int(anchor[2])
			ev = pr.anchor_section(gid, l0, c0, rot=rot, mirror=mirror, fonte="manual", confianca="confirmado")
			msgs.append(f"{gid}: «{AQUI_TXT}» em ({l0},{c0}) rot {rot} mirror {mirror}: {len(ev['placements'])} peças colocadas")
			for c in ev["conflicts"]:
				msgs.append(f"CONFLITO: {c['piece']} → {tuple(c['cell'])} já tem {c['occupant']} (não sobrescrito)")
			for pl in ev["placements"]:
				cells |= _around(pr, tuple(pl["cell"]))
		elif unanchor is not None:
			ev = pr.unanchor_section(unanchor)
			msgs.append(f"{unanchor}: «{AQUI_TXT}» desfeito, {len(ev['placements'])} peças voltam a ficar sem lugar")
			for pl in ev["placements"]:
				cells |= _around(pr, tuple(pl["cell"]))
		elif discard:
			pr.discard(piece_id, reason)
			msgs.append(f"{piece_id} descartada")
			pieces.add(piece_id)
		else:
			return {"error": "nada a fazer (indica --cell, --unplace, --reject, --position-known, --anchor, --unanchor, --discard, --buraco ou --buraco-rejeitar)"}
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


def _hole_meta_for(pr, piece_id: str, cell) -> dict:
	"""Rank / custo / margem / confiança / m / fit_version / theta_deg of ``piece_id`` for the hole ``cell`` from
	:func:`src.fit.rank_all` (the same numbers the GUI shows), or ``{'error'}``."""
	from src import fit as F
	if piece_id is None:
		return {"error": "falta a peça"}
	res = F.rank_all(pr, cells=[tuple(cell)], top=10 ** 6)
	if "error" in res:
		return {"error": res["error"]}
	if not res["holes"]:
		return {"error": f"célula {tuple(cell)} não é um buraco (ocupada ou sem vizinha montada com forma e pose)"}
	r = res["holes"][0]
	c = next((x for x in r["candidates"] if x["id"] == piece_id), None)
	meta = {"m": r["m"], "confianca": r["confidence"], "fit_version": r["version"], "margem": r.get("margin")}
	if c is None:
		meta.update(rank=None, custo=None, nota="fora do ranking (custo infinito)")
	else:
		meta.update(rank=c["rank"], custo=c["J"], theta_deg=c["theta_deg"])
	return meta


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
	g.add_argument("--unplace", action="store_true", help="retira a peça colocada (volta a solta; a célula ao estado anterior)")
	g.add_argument("--reject", action="store_true")
	g.add_argument("--position-known", nargs=2, type=int, metavar=("L", "C"))
	g.add_argument("--anchor", nargs=3, metavar=("G", "L", "C"))
	g.add_argument("--unanchor", metavar="G")
	g.add_argument("--discard", action="store_true")
	g.add_argument("--relot", nargs="+", metavar="S", help="scans (folhas) a mudar de lote; exige --lote")
	g.add_argument("--cheia", nargs="+", metavar="L,C", help="células que o utilizador diz estarem montadas")
	g.add_argument("--vazia", nargs="+", metavar="L,C", help="células que o utilizador diz estarem vazias")
	g.add_argument("--pose", nargs=3, type=float, metavar=("THETA", "DX", "DY"),
				   help="pose manual da peça colocada: graus (sentido dos ponteiros no ecrã), dx e dy em mm (y para baixo)")
	g.add_argument("--pose-repor", action="store_true", help="retira a pose manual (volta ao registo automático)")
	g.add_argument("--buraco", nargs=2, type=int, metavar=("L", "C"),
				   help="M11: coloca a peça no buraco (L, C) a partir da lista «candidatas para este buraco» (rank/custo/margem/confiança do src.fit)")
	g.add_argument("--buraco-rejeitar", nargs=2, type=int, metavar=("L", "C"), help="M11: a peça não encaixa no buraco (L, C)")
	ap.add_argument("--lote", type=int, default=None, help="lote de destino de --relot")
	ap.add_argument("--origin", default=None, help="gemeo | par | borda | buraco | gt | manual (omissão: a da lista)")
	ap.add_argument("--theta", type=float, default=None, metavar="DEG",
					help="com --cell: pose no tabuleiro (graus, sentido dos ponteiros no ecrã) quando a lista não a tem")
	ap.add_argument("--rot", type=int, default=0)
	ap.add_argument("--mirror", action="store_true")
	ap.add_argument("--reason", default="")
	ap.add_argument("--nota", default="", help="nota da pose manual (--pose)")
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
	needs_piece = args.cell or args.unplace or args.reject or args.position_known or args.discard or args.pose or args.pose_repor
	if needs_piece and not args.piece_id:
		print("erro: falta o id da peça")
		return 1
	if args.theta is not None and not args.cell:
		print("erro: --theta só se usa com --cell")
		return 1
	try:
		full = parse_cells(args.cheia) if args.cheia else None
		empty = parse_cells(args.vazia) if args.vazia else None
	except ValueError as e:
		print(f"erro: {e}")
		return 1
	try:
		pr = open_project(args)
		hole = hole_rej = None
		if args.buraco or args.buraco_rejeitar:
			hc = tuple(args.buraco or args.buraco_rejeitar)
			meta = _hole_meta_for(pr, args.piece_id, hc)
			if "error" in meta:
				print(f"erro: {meta['error']}")
				return 1
			if args.buraco:
				hole = (hc, meta)
			else:
				hole_rej = (hc, meta)
		r = confirm(pr, args.piece_id, cell=args.cell, origin=args.origin, reject=args.reject, hole=hole, hole_reject=hole_rej,
					position_known=args.position_known, anchor=args.anchor, rot=args.rot, mirror=args.mirror,
					unanchor=args.unanchor, discard=args.discard, reason=args.reason, cell_full=full, cell_empty=empty,
					requery=not args.no_requery, use_image=not args.no_image, unplace=args.unplace, theta_deg=args.theta,
					pose=args.pose, pose_repor=args.pose_repor, nota=args.nota)
	except ImportError as e:
		print(f"aplicado, mas a nova consulta falhou: {e}")
		return 1
	if "error" in r:
		print(f"erro: {r['error']}")
		return 1
	for m in r["messages"]:
		print(m)
	if args.cell or args.unplace or args.position_known or args.anchor or args.unanchor or args.pose or args.pose_repor or args.buraco:
		from src.consistency import suspects_lines   # orientation check of the changed area (read-only, never blocks)
		print("\n".join(suspects_lines(pr, r["affected_cells"])))
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
