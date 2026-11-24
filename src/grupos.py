"""Loose groups on the board of the new GUI (F4, B2): pure logic over the project, no file written.

A loose group is a section without a place (:class:`src.state.Section` with ``anchor.anchored`` false) that is not
made only of re-scans. Its free position on the board lives in ``mesa.jsonl`` (:mod:`src.mesa`, B1); this module
holds what the server needs around it (``docs/gui/redesenho/F4_PLANO.md`` §1 «Falta» 2–3, §3):

* :func:`footprint`, :func:`effective_position`, :func:`valid`: the ones of :mod:`src.mesa` (one rule, one place);
* :func:`initial_position` (Q3): where «Mostrar no tabuleiro» puts a group never shown: candidate 1 when its
  margin is >= ``margin_min`` and its position is valid, else the valid position whose footprint centre is nearest
  the centre of the view the browser sends (ties: row, then column of the anchor);
* :func:`likely_place` (Q4 b, corrected in B2b): the first stored candidate that is valid now and that the
  neighbours do not contradict, with the margin recomputed among those and >= ``margin_min``; none when a member is
  ``impossivel`` in every rotation at a valid candidate met before it;
* :func:`rotate` (Q5 b): a quarter turn about the centre of the footprint's box; never slides: when the turned group
  does not fit, «Não cabe aqui rodado: move primeiro.»;
* :func:`sobreposto`: the stored position is no longer valid (a «Encaixa» under the shown group): derived on every
  read, never written; the group never jumps by itself;
* :func:`count_loose`: groups and pieces of the visible loose groups (the «N em grupos soltos» of the top);
* :func:`rotation_check` (lesson P0833, correction C2; one criterion since B2b): before «Fixar» writes the anchor,
  each piece that «Fixar» places (not a re-scan ``same_as``, not a piece already placed) is graded with
  :func:`src.consistency.grade_at`, the function of the suspects, on the board as it would be (the group's own
  pieces count as neighbours, the ``explicada`` rule applies); only the words confirmam / inconclusivas / discordam
  are this module's; never :func:`src.consistency.evaluate` over the board; an invalid position is refused before;
* :func:`verdict`, :func:`confidence` (decisions 1 and 2 of Tiago, C1): the global word of the neighbours and the
  ``confianca`` of the anchor;
* :func:`group_rgba`: the image of the assembled group in its local frame (fixed scale per cell; poses of
  :func:`src.render.initial_theta` with a hypothetical anchor at (0, 0); crops of :func:`src.render.piece_ready`).
"""

from __future__ import annotations

import math
import time
from typing import Optional

import numpy as np

from src import mesa
from src.state import section_cell

__all__ = [
	"footprint", "effective_position", "valid", "initial_position", "likely_place", "rotate", "sobreposto",
	"count_loose", "place_calibrated", "auto_positions", "AUTO_ORIGEM", "margin_min", "rotation_check", "verdict", "confidence", "VIZINHAS", "NAO_CABE_RODADO",
	"AVISO_DISCORDAM", "aviso_discordam", "MARGIN_ROUND", "group_theta", "group_frame", "group_rgba", "PNG_MARGIN_CELLS",
]

footprint = mesa.footprint
effective_position = mesa.effective_position

VIZINHAS = ("confirmam", "discordam", "inconclusivas", "sem_vizinhas")
NAO_CABE_RODADO = "Não cabe aqui rodado: move primeiro."
AVISO_DISCORDAM = "As peças ao lado dizem outra rotação."
MARGIN_ROUND = 0.002            # likely_place: a stored candidate set the stored margin if its score ratio is this close
								# (the stored margins and scores are rounded to 3 decimals)
PNG_MARGIN_CELLS = 0.5          # transparent margin of the group image around its cells (the tabs stick out ≈ 0.3)


def margin_min(profile) -> float:
	return float((profile.calibration or {}).get("margin_min", 1.5))


def _pos(pos: dict) -> dict:
	return {"l0": int(pos["l0"]), "c0": int(pos["c0"]), "rot": int(pos.get("rot") or 0) % 360,
			"mirror": bool(pos.get("mirror"))}


def valid(project, gid: str, pos: dict, shown: Optional[dict] = None) -> Optional[dict]:
	"""None when ``gid`` may sit at ``pos`` now, else the refusal of :func:`src.mesa.check_position`."""
	p = _pos(pos)
	return mesa.check_position(project, gid, p["l0"], p["c0"], p["rot"], p["mirror"], shown)


def _box(cells) -> tuple:
	ls = [c[0] for c in cells]
	cs = [c[1] for c in cells]
	return min(ls), min(cs), max(ls), max(cs)


def _round(x: float) -> int:
	return int(math.floor(x + 0.5))


# ---------------------------------------------------------------- likely place / initial position (Q3, Q4 b)
def _cand_pos(cd: dict) -> dict:
	return {"l0": int(cd["cell0"][0]), "c0": int(cd["cell0"][1]), "rot": int(cd.get("rot") or 0) % 360,
			"mirror": bool(cd.get("mirror"))}


def _cheb(section, a: dict, b: dict) -> float:
	"""Mean Chebyshev distance (cells) between the members' cells at ``a`` and at ``b`` (the distance of
	:func:`src.legacy.distinct_margin`)."""
	fa, fb = footprint(section, a), footprint(section, b)
	return float(np.mean([max(abs(x[0] - y[0]), abs(x[1] - y[1])) for x, y in zip(fa, fb)])) if fa else 0.0


def likely_place(project, gid: str, shown: Optional[dict] = None, placements: Optional[dict] = None) -> Optional[dict]:
	"""The likely place of a loose group (Q4 b; rules of Tiago 2026-11-18, F4 B2b, ``docs/decisoes.md``), or None.

	Over the stored candidates (``Section.candidates``, top 3 of the legacy solve, in its order):

	1. a candidate not valid now (:func:`valid`: off the grid, a placed or marked cell, another shown group) is
	   dropped before anything is evaluated;
	2. each valid candidate gets :func:`rotation_check`; a candidate the neighbours contradict (``discordam``) is
	   dropped; when a member is ``impossivel`` in every rotation (``impossiveis``: not ``explicada``) at a valid
	   candidate met before the place (in the solve's order), the group gets no place at all (the image put it where
	   it cannot be); after the place, such a candidate is only dropped from the alternatives;
	3. the first candidate left is the place; the image only breaks the tie among the ones left, through the margin
	   recomputed among them: U = lowest score of a candidate left at a mean Chebyshev distance >= ``DISTINCT_CELLS``
	   of :mod:`src.legacy` from the place / score of the place. When the place is the solve's candidate 1, the
	   stored margin stands (the solve measured it over all its placements, not only the 3 stored; dropping
	   alternatives can only raise it), unless the alternative that set it is a stored candidate dropped now (its
	   score ratio equals the stored margin within :data:`MARGIN_ROUND`): then U. When the place is a later
	   candidate, U. No U: no margin, no place;
	4. the margin must be >= ``margin_min``.

	Only the 3 stored candidates are seen (the legacy solve keeps no more; they are not in score order, so U alone
	could overstate the margin of candidate 1). ``shown``: :func:`src.mesa.effective_positions`
	in hand; ``placements``: the server's cache (neighbours' ``k``). Returns ``{cell0, rot, mirror, margin, footprint,
	candidato (1-based), vizinhas}``.
	"""
	from src.legacy import DISTINCT_CELLS
	s = project.sections.get(gid)
	if s is None or not s.candidates:
		return None
	if shown is None:
		shown = mesa.effective_positions(project)
	placements = {} if placements is None else placements
	left = []
	for i, cd in enumerate(s.candidates):
		if not cd.get("cell0"):
			continue
		p = _cand_pos(cd)
		if valid(project, gid, p, shown) is not None:
			continue
		chk = rotation_check(project, gid, p, placements, shown=shown, checked=True)
		if chk["impossiveis"] and not left:
			return None
		if chk["vizinhas"] == "discordam":
			continue
		left.append((i, cd, p, chk))
	if not left:
		return None
	i0, best, p0, chk0 = left[0]
	s0 = float(best.get("score") or 0.0)
	kept = {i for i, _, _, _ in left}
	alts = [cd for _, cd, p, _ in left[1:] if _cheb(s, p0, p) >= DISTINCT_CELLS]
	u = (min(float(cd.get("score") or 0.0) for cd in alts) / s0 if s0 > 0 else float("inf")) if alts else None
	m = None
	if i0 == 0 and best.get("margin") is not None:
		# the solve's margin is over all its placements (not only the 3 stored): it stands unless the alternative
		# that set it is a stored candidate dropped now; then the margin among the stored ones left
		mm = float(best["margin"])
		culprit = s0 > 0 and any(j not in kept and _cheb(s, p0, _cand_pos(cd)) >= DISTINCT_CELLS
								 and abs(float(cd.get("score") or 0.0) / s0 - mm) <= MARGIN_ROUND
								 for j, cd in enumerate(s.candidates) if cd.get("cell0"))
		m = u if culprit else mm
	elif i0 > 0:
		m = u
	if m is None or not m >= margin_min(project.profile):
		return None
	return {"cell0": [p0["l0"], p0["c0"]], "rot": p0["rot"], "mirror": p0["mirror"],
			"margin": round(m, 3) if math.isfinite(m) else m, "footprint": [list(c) for c in footprint(s, p0)],
			"candidato": i0 + 1, "vizinhas": chk0["vizinhas"]}


AUTO_ORIGEM = "provavel"


def auto_positions(project, shown: dict, placements: Optional[dict] = None) -> tuple:
	"""F4b (a), decision of Tiago 2026-11-24: the loose groups that have no position of their own (``shown``: the
	``mesa.jsonl`` / fixation ones, :func:`src.mesa.effective_positions`) but have a served likely place
	(:func:`likely_place` valid now, margin >= ``margin_min``, :func:`place_calibrated`) are shown at that place, with
	its rotation. Derived on every call, NEVER written (only «Mover», «Rodar» and «Fixar» write). Groups are taken in
	id order and each one is validated against ``shown`` plus the ones already taken, so two never overlap.
	Returns ``(auto, lps)``: ``auto`` = {gid: {l0, c0, rot, mirror, rodado: False, origem: "provavel"}} and ``lps`` =
	{gid: the served likely place or None} for every loose group evaluated (those not in ``shown``)."""
	acc = dict(shown)
	auto, lps = {}, {}
	for gid in sorted(project.sections):
		if gid in shown or not mesa.is_loose(project, gid):
			continue
		lp = likely_place(project, gid, acc, placements)
		if lp is not None and not place_calibrated(project.profile, lp["footprint"]):
			lp = None
		lps[gid] = lp
		if lp is None:
			continue
		p = {"l0": lp["cell0"][0], "c0": lp["cell0"][1], "rot": lp["rot"], "mirror": lp["mirror"]}
		if valid(project, gid, p, acc) is not None:
			continue
		pos = dict(p, rodado=False, origem=AUTO_ORIGEM)
		acc[gid] = pos
		auto[gid] = pos
	return auto, lps


def place_calibrated(profile, footprint) -> bool:
	"""True when the likely place may be served (decision 1 of Tiago, F4 B4): every cell of ``footprint`` lies in an
	``image_zones`` zone with a calibrated ``dE_p90`` (``profile.zone_of``); a profile with no zone rows has no zones to
	calibrate, so nothing is filtered. A filter on what is served, not on the shape or the rotation."""
	if not profile.has_zone_rows():
		return True
	zones = profile.zones()
	for l, c in footprint:
		z = profile.zone_of(int(l), int(c))
		if z is None or zones[z].get("dE_p90") is None:
			return False
	return True


def _blocked(project, gid: str, shown: dict) -> set:
	"""Cells a group may not take (the rule of :func:`src.mesa.check_position`): placed pieces, cells occupied for
	the engine (marked full by the user), other shown groups."""
	board = project.board
	out = set()
	for cell, c in board.iter_cells():
		if c["estado"] == "colocada" or board.occupied(cell):
			out.add(tuple(cell))
	for other, opos in shown.items():
		if other != gid and other in project.sections:
			out.update(footprint(project.sections[other], opos))
	return out


def initial_position(project, gid: str, centro=None, shown: Optional[dict] = None) -> Optional[dict]:
	"""Where «Mostrar no tabuleiro» puts ``gid`` (Q3): its effective position if it has one (``origem`` of
	:func:`src.mesa.effective_position`); else the likely place (:func:`likely_place`) when it is valid and
	:func:`place_calibrated` (the same zone filter as the served likely place, decision of Tiago 2026-11-18;
	``origem: "candidato"``); else the valid position (rotation 0, as scanned) whose footprint centre is
	nearest ``centro`` = (row, column) of the centre of the view, in cells (default the board centre; ties: anchor
	row, then column; ``origem: "perto_da_vista"``); None when the group fits nowhere."""
	s = project.sections.get(gid)
	if s is None or not mesa.is_loose(project, gid):
		return None
	if shown is None:
		shown = mesa.effective_positions(project)
	if gid in shown:
		return dict(shown[gid])
	lp = likely_place(project, gid, shown)
	if lp is not None and place_calibrated(project.profile, lp["footprint"]):
		p = {"l0": lp["cell0"][0], "c0": lp["cell0"][1], "rot": lp["rot"], "mirror": lp["mirror"]}
		if valid(project, gid, p, shown) is None:
			return dict(p, origem="candidato")
	prof = project.profile
	if centro is None:
		centro = ((prof.rows + 1) / 2.0, (prof.cols + 1) / 2.0)
	cl, cc = float(centro[0]), float(centro[1])
	local = footprint(s, {"l0": 0, "c0": 0, "rot": 0})
	r0, q0, r1, q1 = _box(local)
	ml = sum(c[0] for c in local) / len(local)
	mc = sum(c[1] for c in local) / len(local)
	blocked = _blocked(project, gid, shown)
	best = None
	for l0 in range(1 - r0, prof.rows - r1 + 1):
		for c0 in range(1 - q0, prof.cols - q1 + 1):
			if any((l0 + dl, c0 + dc) in blocked for dl, dc in local):
				continue
			key = ((l0 + ml - cl) ** 2 + (c0 + mc - cc) ** 2, l0, c0)
			if best is None or key < best:
				best = key
	if best is None:
		return None
	return {"l0": best[1], "c0": best[2], "rot": 0, "mirror": False, "origem": "perto_da_vista"}


# ---------------------------------------------------------------- «Rodar» (Q5 b) / sobreposto
def rotate(project, gid: str, pos: dict, delta: int = 90, shown: Optional[dict] = None) -> dict:
	"""``pos`` turned by ``delta`` degrees (multiple of 90, clockwise) about the centre of its footprint's box (rounded
	to whole cells, half up): ``{l0, c0, rot, mirror}``, or the refusal ``{'error': NAO_CABE_RODADO, 'motivo',
	'celula'}`` when the turned group does not fit there (never slid elsewhere)."""
	s = project.sections[gid]
	p = _pos(pos)
	if int(delta) % 90:
		return {"error": "Rodar: só de 90 em 90 graus.", "motivo": "rot_invalida"}
	new_rot = (p["rot"] + int(delta)) % 360
	b = _box(footprint(s, p))
	z = _box(footprint(s, {"l0": 0, "c0": 0, "rot": new_rot, "mirror": p["mirror"]}))
	out = {"l0": _round((b[0] + b[2]) / 2.0 - (z[0] + z[2]) / 2.0),
		   "c0": _round((b[1] + b[3]) / 2.0 - (z[1] + z[3]) / 2.0), "rot": new_rot, "mirror": p["mirror"]}
	bad = valid(project, gid, out, shown)
	if bad:
		return dict(bad, error=NAO_CABE_RODADO)
	return out


def sobreposto(project, gid: str, pos: Optional[dict], shown: Optional[dict] = None) -> Optional[dict]:
	"""None when the stored position ``pos`` is still valid, else why not (the refusal of
	:func:`src.mesa.check_position`: ``{error, motivo, celula}``). Derived, never written."""
	if pos is None:
		return None
	return valid(project, gid, pos, shown)


def count_loose(project) -> dict:
	"""``{grupos, pecas}`` of the visible loose groups (shown or not)."""
	n_g = n_p = 0
	for gid, s in project.sections.items():
		if mesa.is_loose(project, gid):
			n_g += 1
			n_p += len(s.cells_local)
	return {"grupos": n_g, "pecas": n_p}


# ---------------------------------------------------------------- the rotation before «Fixar» (C2, decisions 1–2)
def group_theta(project, pid: str, rot: int, cache: Optional[dict] = None) -> Optional[float]:
	"""Board pose (deg) of the section piece ``pid`` under an anchor of rotation ``rot``: the rule of
	:func:`src.render.initial_theta` for an anchored section (page rotation + body angle + ``rot``), for a group that
	is not anchored (yet)."""
	from src.locate import body_beta_deg, wrap_deg
	from src.render import _section_rotation
	p = project.piece(pid)
	sh = project.shape(pid)
	if sh is None:
		return float(rot)
	srot = _section_rotation(project, p.seccao_id, cache if cache is not None else {})
	return float(srot + wrap_deg(body_beta_deg(sh) - srot) + float(rot))


def _piece_word(g: dict, outside: bool) -> str:
	"""The word of one graded piece (:func:`src.consistency.grade_at`): ``discordam`` = a suspect grade
	(``impossivel`` / ``melhor_rotacao``, not ``explicada``); ``confirmam`` = no failing side, F sides right and every
	other assignment fails, with at least one neighbour outside the group (the group's own pieces cannot confirm
	where the group sits); ``sem_vizinhas`` = only neighbours of the group and nothing against; else ``inconclusivas``."""
	if g["grau"] is not None and not g["explicada"]:
		return "discordam"
	if not outside:
		return "sem_vizinhas"
	res, k0 = g["res"], g["k0"]
	cur = res[k0]
	if cur["n_fail"] == 0 and cur["f_ok"] and all(res[k]["n_fail"] > 0 or not res[k]["f_ok"] for k in range(4) if k != k0):
		return "confirmam"
	return "inconclusivas"


def rotation_check(project, gid: str, pos: dict, placements: Optional[dict] = None, shown: Optional[dict] = None,
				   checked: bool = False) -> dict:
	"""The neighbours' word on the rotation of ``gid`` at ``pos``, before it is anchored (correction C2; one
	criterion with the suspects since B2b, decision 1 of Tiago 2026-11-18).

	An invalid position (:func:`valid`) is refused before anything is evaluated: the refusal ``{error, motivo,
	celula}`` (``checked``: the caller has just validated it). Then the board as «Fixar» would leave it
	(:meth:`src.state.Project.anchor_section`): the placed pieces plus the members it places, i.e. ``em_seccao``,
	not a re-scan (``same_as``) and on a cell no piece holds; the others are not evaluated (``nao_avaliadas``:
	``re_scan`` / ``ja_colocada`` / ``celula_ocupada``). Each member it places that has a mounted orthogonal neighbour
	(of the group or not) is graded by :func:`src.consistency.grade_at` at its future cell and pose (cyclic assignment
	of :func:`src.render.corner_register` with :func:`group_theta`; the placed neighbours with their own ``k``,
	``placements`` = the server's cache); the word per piece is :func:`_piece_word`; a member without 4 corners or
	without a corner registration there is ``inconclusivas``, one without any neighbour ``sem_vizinhas``.

	Returns ``{vizinhas: verdict, pecas: {pid: word}, rot_alt_deg: {pid: deg}, impossiveis: [pid] (impossivel in every
	rotation, not explicada), nao_avaliadas: {pid: motivo}, segundos}``."""
	from src import consistency as C
	from src import render
	from src.legacy import _STEP
	t0 = time.perf_counter()
	if not checked:
		bad = valid(project, gid, pos, shown)
		if bad is not None:
			return dict(bad, segundos=round(time.perf_counter() - t0, 4))
	s = project.sections[gid]
	p = _pos(pos)
	placements = {} if placements is None else placements
	mounted = {tuple(q.celula): qid for qid, q in project.pieces.items() if q.estado == "colocada" and q.celula is not None}
	new, skipped = {}, {}
	for pid, rc in sorted(s.cells_local.items()):
		q = project.piece(pid)
		cell = tuple(section_cell(p, rc))
		if q.same_as:
			skipped[pid] = "re_scan"
		elif q.estado != "em_seccao":
			skipped[pid] = "ja_colocada"
		elif cell in mounted:
			skipped[pid] = "celula_ocupada"
		else:
			new[pid] = cell
	mounted.update({cell: pid for pid, cell in new.items()})
	cache, kmap, theta_cache, memo = {}, {}, {}, {}

	def k_of(q):
		if q not in kmap:
			sh = project.shape(q)
			if sh is None or not sh.ok or len(sh.corners) != 4:
				kmap[q] = None
			elif q in new:
				cr = render.corner_register(sh, project.profile, new[q], group_theta(project, q, p["rot"], theta_cache))
				kmap[q] = int(cr["k"]) if cr.get("ok") else None
			else:
				kmap[q] = C._k_of(project, q, placements, cache)
		return kmap[q]

	pecas, alt, imposs = {}, {}, []
	for pid in sorted(new):
		cell = new[pid]
		nbs = [mounted[(cell[0] + dl, cell[1] + dc)] for dl, dc in _STEP.values() if (cell[0] + dl, cell[1] + dc) in mounted]
		if not nbs:
			pecas[pid] = "sem_vizinhas"
			continue
		k0 = k_of(pid)
		if k0 is None:
			pecas[pid] = "inconclusivas"
			continue
		g = C.grade_at(project, pid, cell, k0, mounted, k_of, memo)
		if g["res"][k0]["n"] == 0:
			pecas[pid] = "inconclusivas"
			continue
		pecas[pid] = _piece_word(g, any(q not in new for q in nbs))
		if pecas[pid] == "discordam":
			if g["k_alt"] is not None:
				alt[pid] = C._rot_deg(g["k_alt"], k0)
			elif g["grau"] == "impossivel":
				imposs.append(pid)
	return {"vizinhas": verdict(pecas), "pecas": pecas, "rot_alt_deg": alt, "impossiveis": imposs,
			"nao_avaliadas": skipped, "segundos": round(time.perf_counter() - t0, 4)}


def aviso_discordam(project, pecas: dict) -> Optional[str]:
	"""The warning of «Fixar» when the neighbours disagree, naming the pieces (saco · nº), not the group:
	``'Saco 4 · nº 3: as peças ao lado dizem outra rotação.'``; None when no piece disagrees."""
	who = []
	for pid in sorted(pid for pid, w in pecas.items() if w == "discordam"):
		q = project.piece(pid)
		who.append(f"saco {q.lote} · nº {q.n_no_lote}" if q.lote is not None else f"peça {pid}")
	if not who:
		return None
	txt = ", ".join(who)
	return f"{txt[0].upper()}{txt[1:]}: {AVISO_DISCORDAM[0].lower()}{AVISO_DISCORDAM[1:]}"


def verdict(pecas: dict) -> str:
	"""Global word from the per-piece words: ``discordam`` if any piece disagrees, else ``confirmam`` if any
	confirms, else ``inconclusivas`` if any was checked, else ``sem_vizinhas``."""
	v = set(pecas.values())
	for w in ("discordam", "confirmam", "inconclusivas"):
		if w in v:
			return w
	return "sem_vizinhas"


def confidence(rot_fonte: str, vizinhas: str) -> str:
	"""``confianca`` of the anchor (decision 2 of Tiago): ``confirmado`` needs the rotation confirmed (``rot_fonte``
	``tiago`` or neighbours that confirm) and no neighbour that disagrees; else ``a_confirmar`` (any group size)."""
	if vizinhas == "discordam":
		return "a_confirmar"
	return "confirmado" if rot_fonte == "tiago" or vizinhas == "confirmam" else "a_confirmar"


# ---------------------------------------------------------------- image of the group
def group_frame(profile, section, rot: int, ppc: float) -> dict:
	"""Frame of :func:`group_rgba`: the local cells at ``rot`` with a hypothetical anchor at (0, 0) (``celulas``
	{pid: (dr, dc)}), their box ``origem_local`` (dr, dc of the top-left cell) and size ``celulas_n`` (rows, cols),
	the margin in cells, ``ppm`` (px per mm) and the output size ``W``, ``H``."""
	a = {"l0": 0, "c0": 0, "rot": int(rot) % 360, "mirror": False}
	cells = {pid: section_cell(a, rc) for pid, rc in section.cells_local.items()}
	r0, q0, r1, q1 = _box(cells.values())
	w_mm, h_mm = float(profile.cell_mm["w"]), float(profile.cell_mm["h"])
	ppm = float(ppc) / w_mm
	m = PNG_MARGIN_CELLS
	return {"celulas": cells, "origem_local": (r0, q0), "celulas_n": (r1 - r0 + 1, q1 - q0 + 1), "margem": m,
			"ppm": ppm, "W": int(round((q1 - q0 + 1 + 2 * m) * w_mm * ppm)),
			"H": int(round((r1 - r0 + 1 + 2 * m) * h_mm * ppm))}


def group_rgba(project, gid: str, rot: int, ppc: float, ready=None) -> np.ndarray:
	"""The assembled group as straight RGBA uint8 (RGB order) in its local frame (:func:`group_frame`), transparent
	around the pieces: each piece's crop (``ready(pid)`` = :func:`src.render.piece_ready`, e.g. the server's cache) at
	:func:`group_theta` about its body centre on its local cell centre, drawn in cell order with «over»."""
	from src import render
	from src.locate import body_center_mm
	s = project.sections[gid]
	prof = project.profile
	fr = group_frame(prof, s, rot, ppc)
	ppm, W, H, m = fr["ppm"], fr["W"], fr["H"], fr["margem"]
	r0, q0 = fr["origem_local"]
	w_mm, h_mm = float(prof.cell_mm["w"]), float(prof.cell_mm["h"])
	acc = np.zeros((H, W, 4), np.float32)              # premultiplied RGB + alpha
	cache = {}
	for pid, (dr, dc) in sorted(fr["celulas"].items(), key=lambda kv: (kv[1], kv[0])):
		rd = ready(pid) if ready is not None else render.piece_ready(project, pid)
		sh = project.shape(pid)
		if rd is None or sh is None:
			continue
		rgba, _, _, mmpp, origin = rd
		centre = np.array([(dc - q0 + m + 0.5) * w_mm, (dr - r0 + m + 0.5) * h_mm])
		A = render._crop_to_out(group_theta(project, pid, rot, cache), body_center_mm(sh), centre, (0.0, 0.0),
								origin, mmpp, (ppm, ppm), (0.0, 0.0))
		al = rgba[..., 3].astype(np.float32) / 255.0
		w = render._warp(np.dstack([rgba[..., :3].astype(np.float32) * al[..., None], al]), A, (W, H))
		acc = w + acc * (1.0 - w[..., 3:4])
	a = acc[..., 3:4]
	rgb = acc[..., :3] / np.maximum(a, 1e-6)
	out = np.dstack([np.clip(rgb + 0.5, 0, 255), np.clip(a * 255 + 0.5, 0, 255)]).astype(np.uint8)
	out[..., :3][out[..., 3] == 0] = 0
	return out
