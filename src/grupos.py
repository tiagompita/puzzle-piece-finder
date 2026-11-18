"""Loose groups on the board of the new GUI (F4, B2): pure logic over the project, no file written.

A loose group is a section without a place (:class:`src.state.Section` with ``anchor.anchored`` false) that is not
made only of re-scans. Its free position on the board lives in ``mesa.jsonl`` (:mod:`src.mesa`, B1); this module
holds what the server needs around it (``docs/gui/redesenho/F4_PLANO.md`` §1 «Falta» 2–3, §3):

* :func:`footprint`, :func:`effective_position`, :func:`valid`: the ones of :mod:`src.mesa` (one rule, one place);
* :func:`initial_position` (Q3): where «Mostrar no tabuleiro» puts a group never shown: candidate 1 when its
  margin is >= ``margin_min`` and its position is valid, else the valid position whose footprint centre is nearest
  the centre of the view the browser sends (ties: row, then column of the anchor);
* :func:`likely_place` (Q4 b): candidate 1 only with margin >= ``margin_min``;
* :func:`rotate` (Q5 b): a quarter turn about the centre of the footprint's box; never slides: when the turned group
  does not fit, «Não cabe aqui rodado: move primeiro.»;
* :func:`sobreposto`: the stored position is no longer valid (a «Encaixa» under the shown group): derived on every
  read, never written; the group never jumps by itself;
* :func:`count_loose`: groups and pieces of the visible loose groups (the «N em grupos soltos» of the top);
* :func:`rotation_check` (lesson P0833, correction C2): before «Fixar» writes the anchor, each piece of the group
  that has a mounted neighbour OUTSIDE the group is checked piece by piece with the orientation test of
  :mod:`src.consistency` (4 cyclic assignments, :func:`src.legacy.side_compat`) at the cell and pose it is about to
  get; never :func:`src.consistency.evaluate` over the board;
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
	"count_loose", "margin_min", "rotation_check", "verdict", "confidence", "VIZINHAS", "NAO_CABE_RODADO",
	"AVISO_DISCORDAM", "group_theta", "group_frame", "group_rgba", "PNG_MARGIN_CELLS",
]

footprint = mesa.footprint
effective_position = mesa.effective_position

VIZINHAS = ("confirmam", "discordam", "inconclusivas", "sem_vizinhas")
NAO_CABE_RODADO = "Não cabe aqui rodado: move primeiro."
AVISO_DISCORDAM = "As peças ao lado dizem outra rotação."
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
def likely_place(project, gid: str) -> Optional[dict]:
	"""Candidate 1 of the group (``Section.candidates``) when its margin is >= ``margin_min``, else None:
	``{cell0, rot, mirror, margin, footprint}`` (cells may fall outside the grid: the browser draws what is in)."""
	s = project.sections.get(gid)
	if s is None or not s.candidates:
		return None
	cd = s.candidates[0]
	m = cd.get("margin")
	if not cd.get("cell0") or m is None or float(m) < margin_min(project.profile):
		return None
	p = {"l0": int(cd["cell0"][0]), "c0": int(cd["cell0"][1]), "rot": int(cd.get("rot") or 0) % 360,
		 "mirror": bool(cd.get("mirror"))}
	return {"cell0": [p["l0"], p["c0"]], "rot": p["rot"], "mirror": p["mirror"], "margin": float(m),
			"footprint": [list(c) for c in footprint(s, p)]}


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
	:func:`src.mesa.effective_position`); else candidate 1 when its margin is >= ``margin_min`` and the position is
	valid (``origem: "candidato"``); else the valid position (rotation 0, as scanned) whose footprint centre is
	nearest ``centro`` = (row, column) of the centre of the view, in cells (default the board centre; ties: anchor
	row, then column; ``origem: "perto_da_vista"``); None when the group fits nowhere."""
	s = project.sections.get(gid)
	if s is None or not mesa.is_loose(project, gid):
		return None
	if shown is None:
		shown = mesa.effective_positions(project)
	if gid in shown:
		return dict(shown[gid])
	lp = likely_place(project, gid)
	if lp is not None:
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


def _piece_verdict(res: dict, k0: int) -> str:
	from src import consistency as C
	grau, _ = C._grade(res, k0)
	if grau is not None:
		return "discordam"
	cur = res[k0]
	if cur["n_fail"] == 0 and cur["f_ok"] and all(res[k]["n_fail"] > 0 or not res[k]["f_ok"]
												  for k in range(4) if k != k0):
		return "confirmam"
	return "inconclusivas"


def rotation_check(project, gid: str, pos: dict, placements: Optional[dict] = None) -> dict:
	"""The neighbours' word on the rotation of ``gid`` at ``pos``, before it is anchored (correction C2).

	Only the pieces of the group with a mounted (``colocada``) orthogonal neighbour outside the group are checked, one
	by one: the piece's cyclic assignment ``k0`` at its future cell and pose (:func:`src.render.corner_register` with
	:func:`group_theta`), then the 4 assignments against those neighbours (``consistency._assignments``, each neighbour
	with its own ``k``; ``placements`` = the server's cache, a neighbour missing from it is registered on the fly).
	Per piece: ``discordam`` (a grade of :mod:`src.consistency`: ``impossivel`` / ``melhor_rotacao``), ``confirmam``
	(no failing side and every other assignment fails), ``inconclusivas`` (fits, but another assignment fits too, or
	the piece has no 4 corners), ``sem_vizinhas`` (no mounted neighbour outside the group, not checked).

	Returns ``{vizinhas: verdict, pecas: {pid: word}, rot_alt_deg: {pid: deg}, segundos}``."""
	from src import consistency as C
	from src import render
	from src.legacy import _STEP
	t0 = time.perf_counter()
	s = project.sections[gid]
	p = _pos(pos)
	placements = {} if placements is None else placements
	mine = {pid: section_cell(p, rc) for pid, rc in s.cells_local.items()}
	mounted = {tuple(q.celula): qid for qid, q in project.pieces.items()
			   if q.estado == "colocada" and q.celula is not None and qid not in mine}
	cache, kmap, theta_cache = {}, {}, {}
	pecas, alt = {}, {}
	for pid in sorted(mine):
		cell = mine[pid]
		nbs = [mounted[(cell[0] + dl, cell[1] + dc)] for dl, dc in _STEP.values()
			   if (cell[0] + dl, cell[1] + dc) in mounted]
		if not nbs:
			pecas[pid] = "sem_vizinhas"
			continue
		sh = project.shape(pid)
		if sh is None or not sh.ok or len(sh.corners) != 4:
			pecas[pid] = "inconclusivas"
			continue
		cr = render.corner_register(sh, project.profile, cell, group_theta(project, pid, p["rot"], theta_cache))
		if not cr.get("ok"):
			pecas[pid] = "inconclusivas"
			continue
		k0 = int(cr["k"])
		for q in nbs:
			if q not in kmap:
				sq = project.shape(q)
				kmap[q] = (C._k_of(project, q, placements, cache)
						   if sq is not None and sq.ok and len(sq.corners) == 4 else None)
		res = C._assignments(project, pid, k0, kmap, mounted, cell=cell)
		if res[k0]["n"] == 0:
			pecas[pid] = "inconclusivas"
			continue
		pecas[pid] = _piece_verdict(res, k0)
		if pecas[pid] == "discordam":
			_, ka = C._grade(res, k0)
			if ka is not None:
				alt[pid] = C._rot_deg(ka, k0)
	return {"vizinhas": verdict(pecas), "pecas": pecas, "rot_alt_deg": alt,
			"segundos": round(time.perf_counter() - t0, 4)}


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
