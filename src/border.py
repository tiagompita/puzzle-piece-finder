"""Border completion: put the border pieces of the unanchored legacy sections on the free border cells.

Tiago's fact (2026-11-01): the physical border is complete except one cell, so every free
border cell (``ocupada_legado`` = full in the occupancy photo, no piece known) holds one of
the scanned border pieces that the legacy solve left unanchored. This module finds which,
with the shape first and the image only as a weak term (border art is grass / sky / rock).

Pipeline of :func:`solve_border`:

1. **inventory** (:func:`inventory`): pieces with ``n_flat >= 1`` (not ``same_as``, not
   ``descartada``) by state, plus F-suspects (:func:`f_suspects`): a side labelled F whose
   profile is not straight (``F_SUSPECT_DEV``), or an F count that makes no sense (3-4 F,
   two opposite F, two F while no corner cell is free). A suspect side is treated as
   *unknown* (neutral cost), never as F: the F labels of unanchored pieces are soft evidence;
2. **free cells** = border cells ``ocupada_legado`` / ``vazia``; **free pieces** = border
   pieces in unanchored sections (they move with their section mates, *blocks* with a fixed
   internal order) and loose legacy pieces without a 4-corner shape (neutral sides);
3. **twin step** (:func:`twin_pins`): for each free cell whose twin cell
   (:meth:`src.profile.PuzzleProfile.twin`) holds a placed piece with a shape, the free
   distance (:func:`src.shape.free_dist`) to every free piece that passes the class and
   chord filters of :func:`src.twin.find_twin` (no image: border art does not discriminate);
   ``d1 <= tmax`` with ``d2 / d1 >= margin_min``, or ``d1 <= t95`` with a single candidate
   passing, *pins* the piece to the cell (hard constraint). A piece pinned to two cells
   keeps neither;
4. **chain step** (:func:`solve_cover`): exact cover of the free cells by block placements
   (4 rotations, no mirror) by branch and bound, cost = sum over the sides of every covered
   cell: facing sides of neighbouring pieces (new against new or against an anchored piece,
   :func:`side_cost`: T<->B ``side_complement`` RMS + ``SIDE_DL_W`` x chord difference; F
   facing a piece ``SIDE_P_F``; T-T / B-B ``SIDE_P_KIND``; a side of unknown kind
   ``SIDE_NEUTRAL``) + ``F_OUT_W`` per border direction of the cell whose side is not F +
   ``TWIN_W`` x free distance to the placed twin (or to the piece chosen for the twin cell,
   capped at ``TWIN_CAP_MM``) + ``DE_W`` x dE of the rendered piece on the cell
   (:func:`src.locate.de_cell`); the terms of an interior piece that moves with its section
   are centred on their typical true value (:func:`unary_cost`). (1,29)-like cells that are ``vazia`` are not covered (the
   piece is missing); unused blocks cost nothing (there are more F pieces than cells);
5. **margins**: per block of the solution, the best solution where one of its pieces is
   not on its cell (``margin = (C2 - C1 + c_B) / c_B``, ``c_B`` = the cost terms that involve
   the block); per segment, the best solution with another assignment on the segment. The
   alternative solves are bounded at ``margin = MARGIN_CAP`` (exact below, ">= cap" above).
   ``alta`` = twin-pinned or margin >= ``margin_min``; ``media`` >= ``CONF_MEDIA``; else
   ``baixa``; capped by the evidence: a placed twin farther than ``TWIN_CONTRA_MM`` from an
   undamaged piece -> ``baixa``; a damaged piece on a cell with a placed twin -> at most
   ``media`` (the twin cannot test it);
6. **decision** (:func:`apply_solution`): every block of the solution is anchored
   (:meth:`src.state.Project.anchor_section`, ``fonte='legado_scan'``) or placed
   (:meth:`src.state.Project.place`, ``origin='borda'``) with its confidence: the constraint
   "the border is complete" decides, the confidence says what to check physically.

Report and figure: :func:`write_report` (``docs/diagnostico/legado/BORDA.md``),
:func:`draw_board` (``borda_tabuleiro.jpg``). CLI::

	python -m src.border --project projects/alpes [--apply] [--report docs/diagnostico/legado/BORDA.md]

Nothing puzzle-specific: grid, twin rule, thresholds and art come from the profile.
Pure functions except :func:`solve_border` (reads the project), :func:`apply_solution`,
:func:`write_report`, :func:`draw_board` and :func:`main`.
"""

from __future__ import annotations

import argparse
import itertools
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from src.shape import Shape, chord_pass, free_dist, side_complement

__all__ = [
	"BPiece", "Block", "Placement", "BorderSolution", "side_cost", "f_suspects", "piece_from_shape",
	"enumerate_placements", "solve_cover", "twin_pins", "inventory", "solve_border", "apply_solution",
	"write_report", "draw_board", "main",
	"TWIN_W", "TWIN_CAP_MM", "TWIN_TYPICAL_MM", "SIDE_P_F", "SIDE_P_KIND", "SIDE_NEUTRAL", "SIDE_DL_W", "SIDE_COST_MAX", "F_OUT_W",
	"DE_W", "TWIN_CONTRA_MM", "MARGIN_CAP", "F_SUSPECT_DEV", "DAMAGE_CHORD_MM", "DAMAGE_AREA", "CONF_MEDIA", "K_BEST",
	"MAX_STATES", "damage", "border_runs", "unary_cost", "pair_cost",
]

# ---------------------------------------------------------------- constants
TWIN_W = 4.0              # cost per mm of free distance to the twin (twin 0.29-0.39 mm, nearest non-twin >= 0.60 mm)
TWIN_CAP_MM = 1.5         # free distances above this all mean "not the twin"
TWIN_TYPICAL_MM = 0.31    # median free distance of the 83 placed border twin pairs (BORDA.md)
SIDE_DL_W = 0.5           # chord-difference weight of a T<->B side cost (legacy.side_compat)
SIDE_COST_MAX = 4.0       # a T<->B side cost is capped here (worse = simply not a mate)
SIDE_P_KIND = 4.0         # T facing T or B facing B
SIDE_P_F = 2.5            # an F side facing a piece (soft: some F labels are wrong)
SIDE_NEUTRAL = 1.4        # side of unknown kind (no 4 corners, suspect F, damaged): median of 178 true border mates 1.37 (BORDA.md)
F_OUT_W = 3.0             # per border direction of the cell whose side is not F
DE_W = 0.03               # per dE unit of the piece on the cell (weak: border art is uniform)
F_SUSPECT_DEV = 0.12      # max |deviation| / chord of a side labelled F; 189 true F of the placed border: p99 0.083, max 0.111
DAMAGE_CHORD_MM = 3.3     # a chord outside [min cell - this, max cell + this] = damaged shape (placed border: 15.06..21.72 mm)
DAMAGE_AREA = (0.8, 1.4)  # area / nominal cell area outside this = damaged shape (placed border: 0.89..1.34)
CONF_MEDIA = 1.2          # margin of a 'media' decision ('alta' = profile margin_min)
MARGIN_CAP = 1.5          # margins are measured up to this (alternative solves bounded there; = margin_min of alpes)
TWIN_CONTRA_MM = 1.0      # placed twin farther than this from an undamaged piece = contradiction -> at most 'baixa'
						  # (placed border twin pairs: 1 of 83 above 1 mm, BORDA.md)
K_BEST = 4                # orderings kept per block set of a run (solve_cover)
MAX_STATES = 3_000_000    # DP state budget per run
_DIRS = ("N", "E", "S", "W")
_STEP = {"N": (-1, 0), "E": (0, 1), "S": (1, 0), "W": (0, -1)}
_OPP = {"N": "S", "S": "N", "E": "W", "W": "E"}


def _rotate_dir(d: str, rot: int) -> str:
	"""Local direction -> board direction under a clockwise rotation (src.locate.rotate_dir, no mirror)."""
	return _DIRS[(_DIRS.index(d) + int(round(rot / 90.0))) % 4]


def _rot_rc(rc, rot: int) -> tuple:
	"""Local offset after a clockwise rotation (src.state.section_cell, no mirror)."""
	dr, dc = int(rc[0]), int(rc[1])
	for _ in range((int(round(rot / 90.0))) % 4):
		dr, dc = dc, -dr
	return dr, dc


def _fmt_m(m) -> str:
	"""A margin, ``>= cap`` when the alternative solve found nothing below the cap."""
	if m is None:
		return "pino"
	return f"≥ {_fmt(MARGIN_CAP)}" if m >= MARGIN_CAP else _fmt(m)


def _fmt(x, nd: int = 2) -> str:
	if x is None or (isinstance(x, float) and not np.isfinite(x)):
		return "—"
	return f"{x:.{nd}f}".replace(".", ",")


# ---------------------------------------------------------------- data
@dataclass
class BPiece:
	"""A piece for the border solve.

	dirs: direction in the piece's *local* frame (the page frame of its section, or the
	board frame for a placed piece) -> :class:`src.shape.Side` (``None`` for a side of unknown
	kind: suspect F, or no 4 corners). theta_deg: rotation crop -> local frame (rendering).
	suspect: readable reasons the F labels are not trusted.
	"""

	id: str
	shape: Optional[Shape]
	dirs: dict = field(default_factory=dict)
	n_flat: int = 0
	theta_deg: float = 0.0
	rgba: Optional[np.ndarray] = field(default=None, repr=False)
	suspect: list = field(default_factory=list)
	section: Optional[str] = None
	label: str = ""
	frame_deg: float = 0.0
	damaged: bool = False

	def side(self, d: str):
		return self.dirs.get(d)

	@property
	def has_sides(self) -> bool:
		return bool(self.dirs)


@dataclass
class Block:
	"""Pieces that move together (a section, or one loose piece): ``members`` {piece id: local (r, c)}."""

	id: str
	members: dict
	section: Optional[str] = None


@dataclass
class Placement:
	"""A block on the board: ``cells`` {piece id: (l, c)}, ``req`` the free border cells it covers."""

	block: str
	rot: int
	l0: int
	c0: int
	cells: dict
	req: frozenset
	unary: float = 0.0
	terms: dict = field(default_factory=dict)

	def key(self) -> tuple:
		return (self.block, self.rot, self.l0, self.c0)


@dataclass
class BorderSolution:
	"""Result of :func:`solve_border` (see :func:`write_report` for the fields that are reported)."""

	inventory: dict
	free_cells: list
	missing_cells: list
	pieces: dict
	blocks: dict
	pins: dict
	twin_table: list
	chosen: list
	cost: float
	cell_info: dict
	segments: list
	leftover: list
	suspects: list
	calibration: dict
	notes: list = field(default_factory=list)
	unpinned_agrees: Optional[bool] = None
	pin_check: dict = field(default_factory=dict)
	elapsed_s: float = 0.0
	error: Optional[str] = None


# ---------------------------------------------------------------- pure helpers
def side_cost(sa, sb) -> float:
	"""Cost of two facing sides (``None`` = unknown kind -> ``SIDE_NEUTRAL``)."""
	if sa is None or sb is None:
		return SIDE_NEUTRAL
	if sa.kind == "F" or sb.kind == "F":
		return SIDE_P_F
	if sa.kind == sb.kind:
		return SIDE_P_KIND
	rms, dl = side_complement(sa, sb)
	return float(min(rms + SIDE_DL_W * dl, SIDE_COST_MAX))


def side_dev(side) -> float:
	"""Max |deviation| of a side profile from its chord, as a fraction of the chord."""
	return float(np.abs(np.asarray(side.profile)[:, 1]).max())


def _f_count_reason(types, corner_free: bool = True) -> str:
	"""Why the number / layout of F sides makes no sense ('' if it does)."""
	fs = [i for i, t in enumerate(types) if t == "F"]
	if len(fs) >= 3:
		return f"{len(fs)} lados F"
	if len(fs) == 2:
		if (fs[1] - fs[0]) % 2 == 0:
			return "dois lados F opostos"
		if not corner_free:
			return "dois lados F (canto) mas não há canto livre"
	return ""


def f_suspects(shape: Optional[Shape], *, corner_free: bool = True, dev_max: float = F_SUSPECT_DEV) -> tuple:
	"""``(suspect side indices, reasons)`` of a shape's F labels.

	A side labelled F is suspect if its profile deviates more than ``dev_max`` x chord from
	straight. The whole F labelling is suspect (every F side returned) if there are 3-4 F, two
	opposite F, or two F while no corner cell is free (``corner_free=False``).
	"""
	if shape is None or not shape.ok:
		return [], []
	types = shape.types
	fs = [i for i, t in enumerate(types) if t == "F"]
	bad, why = set(), []
	for i in fs:
		dv = side_dev(shape.sides[i])
		if dv > dev_max:
			bad.add(i)
			why.append(f"lado {i} F com desvio {_fmt(dv, 3)} da corda > {_fmt(dev_max, 3)}")
	r = _f_count_reason(types, corner_free)
	if r:
		bad.update(fs)
		why.append(r)
	return sorted(bad), why


def damage(shape: Optional[Shape], cell_mm: Optional[dict]) -> list:
	"""Reasons the shape is damaged by the segmentation (bites, merged fragments), [] if none.

	A chord outside ``[min(w, h) - DAMAGE_CHORD_MM, max(w, h) + DAMAGE_CHORD_MM]`` or an area
	outside ``DAMAGE_AREA`` x ``w * h`` of the nominal cell ``cell_mm`` = ``{'w', 'h'}``.
	"""
	if shape is None or not cell_mm:
		return []
	w, h = float(cell_mm["w"]), float(cell_mm["h"])
	out = []
	r = float(shape.area_mm2) / (w * h)
	if not DAMAGE_AREA[0] <= r <= DAMAGE_AREA[1]:
		out.append(f"área {_fmt(shape.area_mm2, 0)} mm² = {_fmt(r)} x célula nominal")
	if shape.ok:
		lo, hi = min(w, h) - DAMAGE_CHORD_MM, max(w, h) + DAMAGE_CHORD_MM
		bad = [x for x in shape.lens if not lo <= x <= hi]
		if bad:
			out.append(f"corda {', '.join(_fmt(x, 1) for x in bad)} mm fora de [{_fmt(lo, 1)}, {_fmt(hi, 1)}]")
	return out


def piece_from_shape(pid: str, shape: Optional[Shape], frame_rot_deg: float, *, rgba=None, theta_deg: float = 0.0,
					 corner_free: bool = True, section: Optional[str] = None, label: str = "",
					 cell_mm: Optional[dict] = None) -> BPiece:
	""":class:`BPiece` with its sides labelled N/E/S/W in the frame turned by ``frame_rot_deg``.

	Uses :func:`src.legacy.label_sides`; if the 4 sides cannot be labelled (or the shape has
	no 4 corners) the piece has no sides (neutral costs). Suspect F sides become ``None``; a
	damaged shape (:func:`damage`, needs ``cell_mm``) has every side ``None`` and
	``damaged = True`` (its free distances are not evidence either).
	"""
	from src.legacy import label_sides
	bp = BPiece(id=pid, shape=shape, rgba=rgba, theta_deg=float(theta_deg), section=section, label=label,
				frame_deg=float(frame_rot_deg), n_flat=int(shape.n_flat) if shape is not None and shape.ok else 0)
	dmg = damage(shape, cell_mm)
	if dmg:
		bp.damaged = True
		bp.suspect.append("forma danificada (" + "; ".join(dmg) + "): lados neutros")
	if shape is None or not shape.ok:
		bp.damaged = True
		bp.suspect.append("sem 4 cantos: lados neutros")
		return bp
	dirs, ok, _ = label_sides(shape, frame_rot_deg)
	if not ok:
		bp.suspect.append("lados não etiquetáveis N/E/S/W: lados neutros")
		return bp
	bad, why = f_suspects(shape, corner_free=corner_free)
	bp.suspect.extend(why)
	bp.dirs = {d: (None if (i in bad or dmg) else shape.sides[i]) for d, i in dirs.items()}
	if _f_count_reason(shape.types, corner_free):
		bp.damaged = True
	return bp


def _board_side(bp: BPiece, rot: int, board_dir: str):
	"""Side of ``bp`` facing ``board_dir`` when its local frame is turned by ``rot``."""
	if not bp.dirs:
		return None
	local = _DIRS[(_DIRS.index(board_dir) - int(round(rot / 90.0))) % 4]
	return bp.dirs.get(local)


def enumerate_placements(block: Block, profile, free_cells: set, interior_ok, *, n_flat_of: dict) -> list:
	"""Admissible placements of a block (4 rotations, every anchor that puts a member on a free cell).

	Admissible: every cell in the grid; border cells only among ``free_cells``; other cells
	only where ``interior_ok(cell)``; at least ``max(1, nF - 1)`` free border cells covered
	(``nF`` = members with ``n_flat >= 1``; one F label may be wrong).
	"""
	out, seen = [], set()
	nF = sum(1 for pid in block.members if n_flat_of.get(pid, 0) >= 1)
	need = max(1, nF - 1)
	for rot in (0, 90, 180, 270):
		offs = {pid: _rot_rc(rc, rot) for pid, rc in block.members.items()}
		for y in sorted(free_cells):
			for pid in sorted(block.members):
				l0, c0 = y[0] - offs[pid][0], y[1] - offs[pid][1]
				if (rot, l0, c0) in seen:
					continue
				seen.add((rot, l0, c0))
				cells = {q: (l0 + o[0], c0 + o[1]) for q, o in offs.items()}
				ok, req = True, set()
				for cell in cells.values():
					if not profile.in_grid(*cell):
						ok = False
						break
					if profile.is_border(*cell):
						if cell not in free_cells:
							ok = False
							break
						req.add(cell)
					elif not interior_ok(cell):
						ok = False
						break
				if ok and len(req) >= need:
					out.append(Placement(block=block.id, rot=rot, l0=l0, c0=c0, cells=cells, req=frozenset(req)))
	return out


def unary_cost(pl: Placement, pieces: dict, profile, fixed: dict, *, twin_d=None, de=None, required=None) -> dict:
	"""Cost terms of a placement that do not depend on the other new placements.

	``fixed`` {cell: (BPiece, rot) | None}: anchored pieces (None = full but unknown).
	``twin_d(pid, cell)`` -> free distance to the placed twin of ``cell`` or None.
	``de(pid, rot, cell)`` -> dE or None. Internal sides of the block are counted here too.
	Returns the block totals per term, ``total``, and ``por_peca`` {piece id: terms}.
	``required``: the cells every solution covers. A cell of the placement outside it (an
	interior piece moving with its section) is *optional*: its side and twin terms are
	centred on their typical true value (``SIDE_NEUTRAL``, ``TWIN_TYPICAL_MM``) and it has no
	dE term, so a block is neither rewarded nor punished for carrying extra pieces.
	"""
	keys = ("f_out", "lado_fixo", "lado_interno", "gemea", "dE")
	pp = {pid: dict.fromkeys(keys, 0.0) for pid in pl.cells}
	inv = {cell: pid for pid, cell in pl.cells.items()}
	opt = set() if required is None else {c for c in pl.cells.values() if c not in required}
	for pid, cell in pl.cells.items():
		bp = pieces[pid]
		t = pp[pid]
		fd = profile.flat_directions(*cell)
		if bp.has_sides:
			for d in fd:
				s = _board_side(bp, pl.rot, d)
				if s is not None and s.kind != "F":
					t["f_out"] += F_OUT_W
		for d in _DIRS:
			if d in fd:
				continue
			n = (cell[0] + _STEP[d][0], cell[1] + _STEP[d][1])
			if n in inv:
				if (cell, n) < (n, cell):   # each internal edge once
					q = pieces[inv[n]]
					t["lado_interno"] += side_cost(_board_side(bp, pl.rot, d), _board_side(q, pl.rot, _OPP[d])) 						- (SIDE_NEUTRAL if (cell in opt or n in opt) else 0.0)
			elif n in fixed and fixed[n] is not None:
				q, qrot = fixed[n]
				t["lado_fixo"] += side_cost(_board_side(bp, pl.rot, d), _board_side(q, qrot, _OPP[d])) 					- (SIDE_NEUTRAL if cell in opt else 0.0)
		if twin_d is not None:
			v = twin_d(pid, cell)
			if v is not None:
				t["gemea"] += TWIN_W * (min(float(v), TWIN_CAP_MM) - (TWIN_TYPICAL_MM if cell in opt else 0.0))
		if de is not None and cell not in opt:
			v = de(pid, pl.rot, cell)
			if v is not None and np.isfinite(v):
				t["dE"] += DE_W * float(v)
	out = {k: float(sum(pp[q][k] for q in pp)) for k in keys}
	out["total"] = float(sum(out.values()))
	out["por_peca"] = pp
	return out


def pair_cost(a: Placement, b: Placement, pieces: dict, profile, *, pair_d=None) -> float:
	"""Cost between two new placements: facing sides of adjacent members + twin cells held by both."""
	cost = 0.0
	ib = {cell: pid for pid, cell in b.cells.items()}
	for pid, cell in a.cells.items():
		fd = profile.flat_directions(*cell)
		for d in _DIRS:
			if d in fd:
				continue
			n = (cell[0] + _STEP[d][0], cell[1] + _STEP[d][1])
			if n in ib:
				cost += side_cost(_board_side(pieces[pid], a.rot, d), _board_side(pieces[ib[n]], b.rot, _OPP[d]))
		if pair_d is not None:
			tw = profile.twin(*cell)
			if tw is not None and tw in ib:
				v = pair_d(pid, ib[tw])
				if v is not None:
					cost += TWIN_W * min(float(v), TWIN_CAP_MM)
	return float(cost)


def border_runs(cells, profile) -> list:
	"""Free border cells split into runs, each ordered along the border (end to end).

	A run is a connected set of 4-adjacent cells; it is walked from an end (a cell with one
	neighbour in the run). A run that closes on itself is walked from its smallest cell.
	"""
	out = []
	for comp in _segments(sorted(cells), profile):
		S = set(comp)

		def nb(x):
			return [(x[0] + _STEP[d][0], x[1] + _STEP[d][1]) for d in _DIRS if (x[0] + _STEP[d][0], x[1] + _STEP[d][1]) in S]

		ends = sorted(x for x in comp if len(nb(x)) <= 1)
		cur = ends[0] if ends else comp[0]
		order, seen = [cur], {cur}
		while True:
			nxt = sorted(n for n in nb(cur) if n not in seen)
			if not nxt:
				break
			cur = nxt[0]
			order.append(cur)
			seen.add(cur)
		out.append(order)
	return out


def _segment_options(order: list, pls: list, idx: list, pieces: dict, profile, pc, k_best: int, max_states: int,
					 lb_cell: Optional[dict] = None, budget: float = float("inf")) -> tuple:
	"""Exact DP along one run: every cover of ``order`` by placements ``idx`` (contiguous intervals).

	State (position, used blocks, last placement); the k best paths are kept per state.
	A path whose cost + the per-cell lower bounds ``lb_cell`` of the rest of the run exceeds
	``budget`` is dropped (exact when ``budget`` is a valid upper bound). Returns
	``(options, complete)``: options = [(cost, used frozenset, tuple of placement indices)]
	with the ``k_best`` best per block set, sorted by cost.
	"""
	pos = {x: i for i, x in enumerate(order)}
	n = len(order)
	starts = {}
	for i in idx:
		p = pls[i]
		ix = sorted(pos[c] for c in p.req)
		if ix != list(range(ix[0], ix[0] + len(ix))):
			continue
		starts.setdefault(ix[0], []).append((i, ix[0] + len(ix)))
	lb_cell = lb_cell or {}
	rest = [sum(lb_cell.get(x, 0.0) for x in order[i:]) for i in range(n + 1)]
	layer = {0: {(frozenset(), -1): [(0.0, ())]}}
	complete = True
	nstates = 0
	for i in range(n):
		cur = layer.pop(i, {})
		for (used, last), paths in cur.items():
			for j, end in starts.get(i, ()):
				p = pls[j]
				if p.block in used:
					continue
				occ = set(p.cells.values())
				ok = True
				for _, path in paths[:1]:
					for q in path:
						if occ & set(pls[q].cells.values()):
							ok = False
							break
				if not ok:
					continue
				add = p.unary + (pc(last, j) if last >= 0 else 0.0)
				if paths[0][0] + add + rest[end] > budget:
					continue
				key = (used | {p.block}, j)
				bucket = layer.setdefault(end, {}).setdefault(key, [])
				for cost, path in paths:
					if cost + add + rest[end] <= budget:
						bucket.append((cost + add, path + (j,)))
				nstates += 1
		for e, d in layer.items():
			for key in d:
				d[key] = sorted(d[key])[:k_best]
		if nstates > max_states:
			complete = False
			break
	fin = {}
	for (used, last), paths in layer.get(n, {}).items():
		for cost, path in paths:
			fin.setdefault(used, []).append((cost, path))
	opts = []
	for used, paths in fin.items():
		for cost, path in sorted(paths)[:k_best]:
			opts.append((cost, used, path))
	opts.sort(key=lambda o: (o[0], o[2]))
	return opts, complete


def solve_cover(required: set, placements: list, pieces: dict, profile, *, pair_d=None, forbid=None, reject=None,
				k_best: int = K_BEST, max_states: int = MAX_STATES, upper: float = float("inf"),
				_cache: Optional[dict] = None) -> dict:
	"""Minimum-cost exact cover of ``required`` by placements of distinct blocks.

	The required cells split into runs along the border (:func:`border_runs`); each run is
	solved exactly by a DP over (position, used blocks, last placement) keeping the
	``k_best`` best orderings per block set (:func:`_segment_options`); the runs are then
	combined by branch and bound (disjoint blocks and cells, + the pairwise terms between
	runs, e.g. twin cells held by new pieces in two runs). Exact except that only the
	``k_best`` best orderings of each block set of a run reach the combination (the terms
	between runs are the only ones that could prefer another ordering).

	``placements`` carry their ``unary``; pairwise costs come from :func:`pair_cost`.
	``forbid(pl) -> bool`` drops placements; ``reject(chosen) -> bool`` drops complete
	solutions. ``upper``: a known upper bound of the optimum (prunes the DP exactly). Returns
	``{'cost', 'chosen': [Placement], 'nodes', 'complete': bool}`` (``cost`` = inf,
	``chosen`` = [] if no cover exists).
	"""
	pls = [p for p in placements if not (forbid and forbid(p))]
	lb_cell = {c: float("inf") for c in required}
	for p in pls:
		for c in p.req:
			if c in lb_cell:
				lb_cell[c] = min(lb_cell[c], p.unary / len(p.req))
	runs = border_runs(sorted(required), profile)
	pcache = {} if _cache is None else _cache.setdefault("pair", {})

	def pc(i, j):
		a, b = pls[i], pls[j]
		k = (a.key(), b.key()) if a.key() < b.key() else (b.key(), a.key())
		if k not in pcache:
			pcache[k] = pair_cost(a, b, pieces, profile, pair_d=pair_d)
		return pcache[k]

	run_of = {}
	for r, order in enumerate(runs):
		for x in order:
			run_of[x] = r
	idx_by_run = [[] for _ in runs]
	for i, p in enumerate(pls):
		rs = {run_of.get(c) for c in p.req}
		if len(rs) == 1 and None not in rs:
			idx_by_run[rs.pop()].append(i)
	complete = True
	options = []
	tot_lb = sum(lb_cell.values())
	for r, order in enumerate(runs):
		others = tot_lb - sum(lb_cell[x] for x in order)
		opts, ok = _segment_options(order, pls, idx_by_run[r], pieces, profile, pc, k_best, max_states, lb_cell,
									upper + 1e-6 - others)
		complete &= ok
		if not opts:
			return {"cost": float("inf"), "chosen": [], "nodes": 0, "complete": complete}
		options.append(opts)
	seq = sorted(range(len(runs)), key=lambda r: len(options[r]))
	lbs = [min(o[0] for o in options[r]) for r in seq]
	tail = [sum(lbs[k:]) for k in range(len(seq) + 1)]
	best = {"cost": float(upper) + 1e-6 if np.isfinite(upper) else float("inf"), "chosen": []}
	nodes = [0]

	def rec(k, used, occupied, chosen, cost):
		nodes[0] += 1
		if cost + tail[k] >= best["cost"] - 1e-9:
			return
		if k == len(seq):
			sol = [pls[i] for i in chosen]
			if not (reject and reject(sol)):
				best["cost"], best["chosen"] = cost, sol
			return
		for c0, u, path in options[seq[k]]:
			if cost + c0 + tail[k + 1] >= best["cost"] - 1e-9:
				break
			if u & used:
				continue
			occ = set()
			for i in path:
				occ |= set(pls[i].cells.values())
			if occ & occupied:
				continue
			add = c0 + sum(pc(i, j) for i in path for j in chosen)
			rec(k + 1, used | u, occupied | occ, chosen + list(path), cost + add)

	rec(0, frozenset(), frozenset(), [], 0.0)
	return {"cost": float(best["cost"]), "chosen": best["chosen"], "nodes": nodes[0], "complete": complete}


def total_cost(chosen: list, pieces: dict, profile, *, pair_d=None) -> float:
	return float(sum(p.unary for p in chosen) + sum(pair_cost(a, b, pieces, profile, pair_d=pair_d)
													 for a, b in itertools.combinations(chosen, 2)))


def involved_cost(pl: Placement, chosen: list, pieces: dict, profile, *, pair_d=None) -> float:
	"""Cost terms of a solution that involve ``pl`` (its unary + its pairwise terms)."""
	return float(pl.unary + sum(pair_cost(pl, q, pieces, profile, pair_d=pair_d) for q in chosen if q is not pl))


def twin_pins(free_cells: list, twin_of: dict, cand: dict, profile) -> tuple:
	"""Twin step: ``(pins {pid: cell}, table [dict])``.

	``twin_of`` {free cell: placed twin BPiece (shape ok)}; ``cand`` {pid: BPiece}. Class +
	chord filter as :func:`src.twin.find_twin`, then free distance; pin if ``d1 <= tmax`` and
	``d2 / d1 >= margin_min``, or ``d1 <= t95`` with a single candidate passing. A piece
	pinned to two cells is pinned to none.
	"""
	cal = profile.calibration or {}
	ss = cal.get("silhueta_silhueta") or {}
	t95, tmax = ss.get("t95"), ss.get("tmax")
	mmin = float(cal.get("margin_min", 1.5))
	ch = cal.get("chord") or {}
	nmm, fmm = float(ch.get("normal_mm", 1.0)), float(ch.get("f_adj_mm", 2.0))
	table, raw = [], {}
	for cell in free_cells:
		q = twin_of.get(cell)
		if q is None or q.shape is None or not q.shape.ok:
			continue
		rows = []
		for pid, bp in sorted(cand.items()):
			if bp.shape is None:
				continue
			d = free_dist(q.shape, bp.shape)[0]
			passed = bool(bp.shape.ok and bp.shape.cls == q.shape.cls
						  and chord_pass(q.shape, bp.shape, normal_mm=nmm, f_adj_mm=fmm)[0])
			rows.append((d, pid, passed))
		rows.sort()
		ps = [r for r in rows if r[2]]
		d1 = ps[0][0] if ps else None
		d2 = ps[1][0] if len(ps) > 1 else None
		margin = (d2 / d1 if d1 else np.inf) if d2 is not None else None
		pin = None
		if d1 is not None and tmax is not None:
			if margin is not None and d1 <= tmax and margin >= mmin:
				pin = ps[0][1]
			elif margin is None and t95 is not None and d1 <= t95:
				pin = ps[0][1]
		table.append({"cell": cell, "twin_cell": profile.twin(*cell), "twin_piece": q.id, "n_pass": len(ps),
					  "top": [(pid, round(d, 3), p) for d, pid, p in rows[:3]],
					  "d1": d1, "pid1": ps[0][1] if ps else None, "d2": d2, "margin": margin, "pin": pin})
		if pin:
			raw.setdefault(pin, []).append(cell)
	pins = {pid: cells[0] for pid, cells in raw.items() if len(cells) == 1}
	for row in table:
		if row["pin"] and row["pin"] not in pins:
			row["pin_conflito"] = raw[row["pin"]]
			row["pin"] = None
	return pins, table


# ---------------------------------------------------------------- project side
def _segments(cells: list, profile) -> list:
	"""Maximal runs of 4-adjacent free border cells (each a list, sorted along the border)."""
	left, out = set(cells), []
	while left:
		start = min(left)
		seg, stack = [], [start]
		left.discard(start)
		while stack:
			x = stack.pop()
			seg.append(x)
			for d in _DIRS:
				n = (x[0] + _STEP[d][0], x[1] + _STEP[d][1])
				if n in left:
					left.discard(n)
					stack.append(n)
		out.append(sorted(seg))
	return sorted(out, key=lambda s: (s[0][1], s[0][0]))


def _seg_name(seg: list) -> str:
	ls = sorted({x[0] for x in seg})
	cs = sorted({x[1] for x in seg})
	if len(seg) == 1:
		return f"({seg[0][0]},{seg[0][1]})"
	if len(cs) == 1:
		return f"coluna {cs[0]}, filas {ls[0]}–{ls[-1]}"
	if len(ls) == 1:
		return f"fila {ls[0]}, colunas {cs[0]}–{cs[-1]}"
	return ", ".join(f"({a},{b})" for a, b in seg)


def _section_frame(project, gid: str):
	"""Page rotation and per-piece crop->page rotation of a section (as legacy.solve_project_sections)."""
	from src.legacy import page_rotation
	from src.locate import body_beta_deg, wrap_deg
	s = project.sections[gid]
	shapes = {pid: project.shape(pid) for pid in s.cells_local}
	rot = page_rotation([sh for sh in shapes.values() if sh is not None])
	theta = {pid: float(rot + wrap_deg(body_beta_deg(sh) - rot)) if sh is not None else float(rot)
			 for pid, sh in shapes.items()}
	return rot, theta, shapes


def _fixed_piece(project, pid: str, cache: dict):
	"""(BPiece in its local frame, board rot) of a placed piece, or None if its pose is unknown."""
	if pid in cache:
		return cache[pid]
	p = project.piece(pid)
	out = None
	if p.seccao_id and project.sections[p.seccao_id].anchor.get("anchored"):
		a = project.sections[p.seccao_id].anchor
		if not a.get("mirror"):
			rot, theta, shapes = _section_frame(project, p.seccao_id)
			bp = piece_from_shape(pid, shapes[pid], rot, theta_deg=theta[pid])
			out = (bp, int(a.get("rot") or 0))
	elif p.theta_deg is not None:
		sh = project.shape(pid)
		bp = piece_from_shape(pid, sh, float(p.theta_deg), theta_deg=float(p.theta_deg))
		out = (bp, 0)
	cache[pid] = out
	return out


def _calibrate(project, fixed_cache: dict) -> dict:
	"""True mates and F sides on the placed border: side costs, F-dev, F-direction consistency."""
	prof = project.profile
	b = project.board
	mates, f_true, f_other, consist = [], [], [], [0, 0]
	for (l, c), cell in b.iter_cells():
		if cell["estado"] != "colocada" or not prof.is_border(l, c):
			continue
		fp = _fixed_piece(project, cell["peca_id"], fixed_cache)
		if fp is None or not fp[0].has_sides:
			continue
		bp, rot = fp
		sh = bp.shape
		fd = prof.flat_directions(l, c)
		consist[1] += 1
		kinds = {d: (_board_side(bp, rot, d).kind if _board_side(bp, rot, d) is not None else "?") for d in _DIRS}
		if {d for d, k in kinds.items() if k == "F"} == fd:
			consist[0] += 1
		from src.legacy import label_sides
		dirs, ok, _ = label_sides(sh, bp.frame_deg)
		for d, i in (dirs.items() if ok else ()):
			if sh.sides[i].kind == "F":
				(f_true if _rotate_dir(d, rot) in fd else f_other).append(side_dev(sh.sides[i]))
		for d in ("E", "S"):
			n = (l + _STEP[d][0], c + _STEP[d][1])
			if not prof.in_grid(*n) or not prof.is_border(*n) or b[n]["estado"] != "colocada":
				continue
			fq = _fixed_piece(project, b[n]["peca_id"], fixed_cache)
			if fq is None:
				continue
			sa, sb = _board_side(bp, rot, d), _board_side(fq[0], fq[1], _OPP[d])
			if sa is not None and sb is not None:
				mates.append(side_cost(sa, sb))
	tw, far = [], []
	for (l, c), cell in b.iter_cells():
		t = prof.twin(l, c) if prof.is_border(l, c) and cell["estado"] == "colocada" else None
		if t is None or t <= (l, c) or b[t]["estado"] != "colocada":
			continue
		sa, sb = project.shape(cell["peca_id"]), project.shape(b[t]["peca_id"])
		if sa is not None and sb is not None:
			tw.append(free_dist(sa, sb)[0])
			if tw[-1] > TWIN_CONTRA_MM:
				far.append(((l, c), t, cell["peca_id"], b[t]["peca_id"], float(tw[-1])))
	tw = np.array(tw)
	tmax = ((prof.calibration or {}).get("silhueta_silhueta") or {}).get("tmax")
	m = np.array(mates)
	return {"gemeas_n": int(len(tw)), "gemeas_mediana": float(np.median(tw)) if len(tw) else None,
			"gemeas_p90": float(np.percentile(tw, 90)) if len(tw) else None,
			"gemeas_frac_tmax": float(np.mean(tw <= tmax)) if len(tw) and tmax else None,
			"gemeas_n_acima_1mm": int(np.sum(tw > TWIN_CONTRA_MM)), "gemeas_acima_1mm": far,
			"n_pares": int(len(m)), "lado_mediana": float(np.median(m)) if len(m) else None,
			"lado_p90": float(np.percentile(m, 90)) if len(m) else None,
			"lado_frac_TB_ok": float(np.mean(m < SIDE_P_F)) if len(m) else None,
			"f_dev_borda_p99": float(np.percentile(f_true, 99)) if f_true else None,
			"f_dev_borda_max": float(np.max(f_true)) if f_true else None, "n_f_borda": len(f_true),
			"f_dev_fora": sorted(round(x, 3) for x in f_other), "f_dir_consistente": consist}


def inventory(project) -> dict:
	"""Pieces with ``n_flat >= 1`` (not ``same_as`` / ``descartada``) by state, and the no-corner legacy pieces."""
	by = {}
	for p in project.pieces.values():
		if p.n_flat >= 1 and not p.same_as and p.estado != "descartada":
			by[p.estado] = by.get(p.estado, 0) + 1
	nocorner = [p.id for p in sorted(project.pieces.values(), key=lambda q: q.id)
				if not p.shape_ok and not p.same_as and p.estado in ("solta", "em_seccao") and p.lote is None
				and (p.seccao_id is None or not project.sections[p.seccao_id].anchor.get("anchored"))]
	return {"por_estado": by, "total": sum(by.values()), "sem_cantos_legado": nocorner,
			"esperado": project.profile.rows * 2 + project.profile.cols * 2 - 4}


def solve_border(project, profile=None, *, art=None, use_image: bool = True, max_states: int = MAX_STATES,
				 margins: bool = True, log=None) -> BorderSolution:
	"""Solve the free border cells of ``project`` (see the module docstring). Reads, never writes."""
	from src.locate import de_cell, render_item
	t0 = time.time()
	say = log or (lambda *a: None)
	prof = profile or project.profile
	b = project.board
	mmin = float((prof.calibration or {}).get("margin_min", 1.5))
	inv = inventory(project)
	border = [lc for lc, _ in b.iter_cells() if prof.is_border(*lc)]
	free = sorted(lc for lc in border if b[lc]["estado"] != "colocada")
	required = {lc for lc in free if b[lc]["estado"] == "ocupada_legado"}
	missing = sorted(lc for lc in free if b[lc]["estado"] == "vazia")
	corner_free = any(prof.is_corner(*lc) for lc in free)
	fixed_cache = {}
	calib = _calibrate(project, fixed_cache)

	# ---- free pieces: border pieces of unanchored sections (+ mates) and loose no-corner legacy pieces
	blocks, pieces = {}, {}
	for gid, s in sorted(project.sections.items()):
		if s.anchor.get("anchored"):
			continue
		live = {pid: rc for pid, rc in s.cells_local.items()
				if not project.piece(pid).same_as and project.piece(pid).estado == "em_seccao"}
		if not live or not any(project.piece(pid).n_flat >= 1 for pid in live):
			continue
		rot, theta, shapes = _section_frame(project, gid)
		for pid in live:
			q = project.piece(pid)
			pieces[pid] = piece_from_shape(pid, shapes[pid], rot, rgba=project.crop_rgba(pid), theta_deg=theta[pid],
										   corner_free=corner_free, section=gid, label=_label(project, pid),
										   cell_mm=prof.cell_mm)
		blocks[gid] = Block(id=gid, members=dict(live), section=gid)
	for pid in inv["sem_cantos_legado"]:
		q = project.piece(pid)
		if q.estado != "solta" or pid in pieces:
			continue
		sh = project.shape(pid)
		pieces[pid] = piece_from_shape(pid, sh, 0.0, rgba=project.crop_rgba(pid), corner_free=corner_free,
									   label=_label(project, pid), cell_mm=prof.cell_mm)
		blocks[pid] = Block(id=pid, members={pid: (0, 0)})
	suspects = [{"piece": pid, "label": bp.label, "section": bp.section, "n_flat": bp.n_flat, "reasons": bp.suspect}
				for pid, bp in sorted(pieces.items()) if bp.suspect]
	say(f"borda: {len(free)} células livres ({len(required)} a cobrir, em falta {missing}); "
		f"{len(blocks)} blocos, {len(pieces)} peças; {len(suspects)} suspeitas")

	# ---- fixed neighbours and placed twins
	fixed = {}
	for lc, cell in b.iter_cells():
		if cell["estado"] == "colocada":
			fixed[lc] = _fixed_piece(project, cell["peca_id"], fixed_cache)
	twin_of = {}
	for x in free:
		tw = prof.twin(*x)
		if tw is not None and b[tw]["estado"] == "colocada":
			q = project.piece(b[tw]["peca_id"])
			sh = project.shape(q.id)
			if sh is not None:
				twin_of[x] = BPiece(id=q.id, shape=sh, label=_label(project, q.id))
	cand = {pid: bp for pid, bp in pieces.items() if bp.shape is not None}
	pins, ttable = twin_pins(free, twin_of, cand, prof)
	pins = {pid: x for pid, x in pins.items() if x in required}
	say(f"gémeas: {len(twin_of)} células com gémea colocada, {len(pins)} pinos")
	dcache = {}

	def twin_d(pid, cell):
		q = twin_of.get(cell)
		if q is None:
			return None
		if pieces[pid].shape is None or pieces[pid].damaged:
			return TWIN_CAP_MM
		k = (pid, q.id)
		if k not in dcache:
			dcache[k] = free_dist(q.shape, pieces[pid].shape)[0]
		return dcache[k]

	def pair_d(a, bb):
		if pieces[a].shape is None or pieces[bb].shape is None or pieces[a].damaged or pieces[bb].damaged:
			return TWIN_CAP_MM
		k = (a, bb) if a < bb else (bb, a)
		if k not in dcache:
			dcache[k] = free_dist(pieces[k[0]].shape, pieces[k[1]].shape)[0]
		return dcache[k]

	if use_image and art is None:
		from src.legacy import _project_art
		art = _project_art(project, None)
	rcache, decache = {}, {}
	mmpp = prof.mm_per_px()

	def de(pid, rot, cell):
		if art is None or pieces[pid].rgba is None:
			return None
		k = (pid, rot, cell)
		if k not in decache:
			rk = (pid, rot)
			if rk not in rcache:
				bp = pieces[pid]
				rcache[rk] = render_item(bp.rgba, bp.shape, bp.theta_deg + rot, art, mmpp)
			decache[k] = de_cell(rcache[rk], cell[0], cell[1], art)["dE"]
		return decache[k]

	def interior_ok(cell):
		return b[cell]["estado"] != "colocada"

	nfl = {pid: bp.n_flat for pid, bp in pieces.items()}
	allp = []
	for bid, blk in sorted(blocks.items()):
		for pl in enumerate_placements(blk, prof, required, interior_ok, n_flat_of=nfl):
			pl.terms = unary_cost(pl, pieces, prof, fixed, twin_d=twin_d, de=de if use_image else None, required=required)
			pl.unary = pl.terms["total"]
			allp.append(pl)
	say(f"colocações admissíveis: {len(allp)}")

	def pin_forbid(pl, skip=None):
		for pid, cell in pl.cells.items():
			for q, x in pins.items():
				if q == skip:
					continue
				if (q == pid and x != cell) or (x == cell and q != pid):
					return True
		return False

	res = solve_cover(required, allp, pieces, prof, pair_d=pair_d, forbid=pin_forbid, max_states=max_states)
	chosen = sorted(res["chosen"], key=lambda p: min(p.req))
	notes = []
	if not res["complete"]:
		notes.append(f"orçamento de estados esgotado ({max_states}): solução pode não ser ótima")
	if not chosen:
		return BorderSolution(inventory=inv, free_cells=free, missing_cells=missing, pieces=pieces, blocks=blocks,
							  pins=pins, twin_table=ttable, chosen=[], cost=np.inf, cell_info={}, segments=[], leftover=[],
							  suspects=suspects, calibration=calib, notes=notes, elapsed_s=time.time() - t0,
							  error="sem cobertura das células livres com as peças disponíveis")
	C1 = res["cost"]
	say(f"ótimo: custo {C1:.2f} ({res['nodes']} nós)")
	# each pin left out in turn: does the chain alone put the piece on the same cell?
	pin_check = {}
	for q, x in (sorted(pins.items()) if margins else ()):
		r = solve_cover(required, allp, pieces, prof, pair_d=pair_d, max_states=max_states, upper=C1,
						forbid=lambda p, q=q: pin_forbid(p, skip=q))
		got = next((y for p in r["chosen"] for pid, y in p.cells.items() if pid == q), None)
		pin_check[q] = {"cell": x, "sem_pino": got, "custo": r["cost"], "acorda": got == x}
		say(f"  pino {q} -> {x}: sem o pino {got} ({time.time() - t0:.0f} s)")
	agrees = all(v["acorda"] for v in pin_check.values())

	# ---- margins per block
	cell_info = {}
	for pl in chosen:
		cB = involved_cost(pl, chosen, pieces, prof, pair_d=pair_d)
		pinned = any(pid in pins for pid in pl.cells)
		worst, alt_of = None, {}
		if margins and not pinned:
			# the best solution where the block's pieces are not on these cells (a rigid block moves as a whole;
			# the same cells in another rotation is not an alternative)
			alt = solve_cover(required, allp, pieces, prof, pair_d=pair_d, max_states=max_states,
							  upper=C1 + (MARGIN_CAP - 1.0) * cB,
							  forbid=lambda p, pl=pl: pin_forbid(p) or (p.block == pl.block and p.cells == pl.cells))
			C2 = alt["cost"]
			m = min((C2 - C1 + cB) / cB, MARGIN_CAP) if cB > 0 else MARGIN_CAP
			alt_of = {x: q for p in alt["chosen"] for q, x in p.cells.items()}
			worst = (m, C2)
			say(f"  {pl.block} {sorted(pl.cells.values())[0]}…: margem {m:.2f} ({time.time() - t0:.0f} s)")
		m = worst[0] if worst else None          # None: block fixed by a twin pin (no alternative solve)
		conf = "alta" if (pinned or (m is not None and m >= mmin)) else 			("media" if (m is not None and m >= CONF_MEDIA) else "baixa")
		why = {}
		# evidence caps: the placed twin contradicts the piece, or the piece's shape is no evidence. In a block fixed
		# by a pin the confidence stays (the rigid block decides) but the contradiction is reported
		for pid, cell in sorted(pl.cells.items()):
			if cell not in twin_of:
				continue
			if pieces[pid].damaged:
				why.setdefault(pid, []).append(f"{pid} em ({cell[0]},{cell[1]}): forma danificada, a gémea colocada não testa")
				if not pinned:
					conf = "media" if conf == "alta" else conf
			elif twin_d(pid, cell) > TWIN_CONTRA_MM:
				why.setdefault(pid, []).append(f"{pid} em ({cell[0]},{cell[1]}): gémea colocada a {_fmt(twin_d(pid, cell))} mm "
						   f"> {_fmt(TWIN_CONTRA_MM, 1)}" + (" (bloco fixado por pino)" if pinned else ""))
				if not pinned:
					conf = "baixa"
		for pid, cell in pl.cells.items():
			cell_info[cell] = {"piece": pid, "block": pl.block, "rot": pl.rot, "anchor": (pl.l0, pl.c0),
							   "confianca": conf, "why": why.get(pid, []), "margin": m, "pinned": pid in pins, "block_pinned": pinned,
							   "cost_block": cB, "C2": worst[1] if worst else None,
							   "alt_piece": alt_of.get(cell), "terms": pl.terms,
							   "twin_d": twin_d(pid, cell), "required": cell in required}
	# ---- margins per segment
	segs = []
	for seg in (border_runs(sorted(required), prof) if margins else []):
		S = set(seg)
		mine = {x: cell_info[x]["piece"] for x in seg}

		def rej(sol, S=S, mine=mine):
			got = {x: pid for p in sol for pid, x in p.cells.items() if x in S}
			return got == mine

		blk = [p for p in chosen if p.req & S]
		cS = sum(p.unary for p in blk) + sum(pair_cost(a, q, pieces, prof, pair_d=pair_d)
											 for a in blk for q in chosen if q is not a and not (q in blk and id(q) < id(a)))
		alt = solve_cover(required, allp, pieces, prof, pair_d=pair_d, forbid=pin_forbid, reject=rej, max_states=max_states,
						  upper=C1 + (MARGIN_CAP - 1.0) * cS)
		m = min((alt["cost"] - C1 + cS) / cS, MARGIN_CAP) if cS > 0 else MARGIN_CAP
		alt_assign = {x: pid for p in alt["chosen"] for pid, x in p.cells.items() if x in S}
		say(f"  segmento {_seg_name(seg)}: margem {m:.2f} ({time.time() - t0:.0f} s)")
		segs.append({"name": _seg_name(seg), "cells": seg, "blocks": [(p.block, p.rot, (p.l0, p.c0)) for p in blk],
					 "cost": cS, "C2": alt["cost"], "margin": m, "alt": alt_assign})
	# cells to check physically: the twin of their placed twin among ALL project pieces (is the right piece scanned?)
	from src.twin import shape_distances
	allq = [q for q in sorted(project.pieces.values(), key=lambda q: q.id) if not q.same_as and project.shape(q.id) is not None]
	for x, ci in cell_info.items():
		if x not in twin_of or (ci["confianca"] == "alta" and not ci["why"]):
			continue
		dd, _ = shape_distances(twin_of[x].shape, [project.shape(q.id) for q in allq])
		ci["gemea_no_projeto"] = [{"piece": allq[k].id, "d": float(dd[k]), "estado": allq[k].estado, "cell": allq[k].celula}
								  for k in np.argsort(dd, kind="stable") if allq[k].id != twin_of[x].id][:3]
	used = {p.block for p in chosen}
	placed = [(q.id, q.celula, project.shape(q.id)) for q in sorted(project.pieces.values(), key=lambda q: q.id)
			  if q.estado == "colocada" and q.celula is not None and project.shape(q.id) is not None]
	leftover = []
	for bid, blk in sorted(blocks.items()):
		if bid in used:
			continue
		near = {}
		for q in sorted(blk.members):
			sh = pieces[q].shape
			if sh is None or not placed:
				continue
			d = [free_dist(sh, s2)[0] for _, _, s2 in placed]
			k = int(np.argmin(d))
			tw = prof.twin(*placed[k][1])
			near[q] = {"placed": placed[k][0], "cell": placed[k][1], "d": float(d[k]), "twin_cell": tw,
					   "twin_estado": b[tw]["estado"] if tw else None}
		leftover.append({"block": bid, "pieces": sorted(blk.members), "labels": [pieces[q].label for q in sorted(blk.members)],
						 "best": _best_unused(bid, allp), "near": near,
						 "suspect": [r for q in sorted(blk.members) for r in pieces[q].suspect]})
	return BorderSolution(inventory=inv, free_cells=free, missing_cells=missing, pieces=pieces, blocks=blocks, pins=pins,
						  twin_table=ttable, chosen=chosen, cost=C1, cell_info=cell_info, segments=segs, leftover=leftover,
						  suspects=suspects, calibration=calib, notes=notes, unpinned_agrees=agrees, pin_check=pin_check,
						  elapsed_s=time.time() - t0)


def _best_unused(bid: str, allp: list):
	ps = sorted((p for p in allp if p.block == bid), key=lambda p: p.unary)
	if not ps:
		return None
	p = ps[0]
	return {"cells": sorted(p.cells.values()), "rot": p.rot, "unary": round(p.unary, 2)}


def _label(project, pid: str) -> str:
	"""Readable label: page + number (``montado_p12 #24``) or the piece id."""
	p = project.piece(pid)
	sc = project.model.scans.get(p.scan_id) or {}
	f = os.path.basename(str(sc.get("file") or sc.get("path") or ""))
	page = f.replace("_300dpi.jpg", "").replace(".jpg", "") if f else p.scan_id
	return f"{page} #{p.n_no_lote}" if p.n_no_lote is not None else f"{page} {pid}"


# ---------------------------------------------------------------- apply / report / figure
def apply_solution(project, sol: BorderSolution) -> list:
	"""Anchor / place every block of the solution; returns the events' summaries."""
	out = []
	for pl in sol.chosen:
		info = sol.cell_info[next(iter(pl.cells.values()))]
		conf, m = info["confianca"], info["margin"]
		mr = None if m is None or not np.isfinite(m) else round(float(m), 3)
		blk = sol.blocks[pl.block]
		if blk.section is not None:
			ev = project.anchor_section(blk.section, pl.l0, pl.c0, rot=pl.rot, fonte="legado_scan", confianca=conf, margin=mr)
			out.append({"section": blk.section, "anchor": (pl.l0, pl.c0, pl.rot), "conflicts": ev.get("conflicts", []),
						"confianca": conf})
		else:
			pid = next(iter(pl.cells))
			bp = sol.pieces[pid]
			ok = bp.shape is not None and bp.shape.ok      # without 4 corners the rotation is not known
			project.place(pid, pl.cells[pid], origin="borda", fonte="legado_scan", score=round(pl.unary, 3), rank=1,
						  theta_deg=float(bp.theta_deg + pl.rot) if ok else None)
			out.append({"piece": pid, "cell": pl.cells[pid], "confianca": conf})
	return out


def draw_board(project, sol: BorderSolution, path: str, *, before: Optional[dict] = None, cell_px: int = 22) -> str:
	"""Border ring figure: green = colocada before, blue = placed by this solve (shade by confidence), red = missing."""
	import cv2
	prof = project.profile
	R, C = prof.rows, prof.cols
	m = 34
	img = np.full((R * cell_px + 2 * m + 20, C * cell_px + 2 * m, 3), 255, np.uint8)
	col = {"antes": (60, 160, 60), "alta": (200, 90, 20), "media": (230, 170, 110), "baixa": (250, 220, 190),
		   "falta": (40, 40, 220), "interior": (235, 235, 235), "interior_cheio": (200, 200, 200), "novo_int": (200, 120, 60)}
	before = before or {}
	for (l, c), cell in project.board.iter_cells():
		x0, y0 = m + (c - 1) * cell_px, m + (l - 1) * cell_px
		info = sol.cell_info.get((l, c))
		if info is not None:
			k = info["confianca"] if prof.is_border(l, c) else "novo_int"
		elif prof.is_border(l, c):
			k = "falta" if (l, c) in sol.missing_cells else ("antes" if before.get((l, c), cell["estado"]) == "colocada" else "falta")
		else:
			k = "interior_cheio" if cell["estado"] != "vazia" else "interior"
		cv2.rectangle(img, (x0, y0), (x0 + cell_px - 1, y0 + cell_px - 1), col[k], -1)
		cv2.rectangle(img, (x0, y0), (x0 + cell_px - 1, y0 + cell_px - 1), (255, 255, 255), 1)
		if info is not None and info.get("pinned"):
			cv2.circle(img, (x0 + cell_px // 2, y0 + cell_px // 2), cell_px // 4, (255, 255, 255), -1)
	f = cv2.FONT_HERSHEY_SIMPLEX
	for c in range(1, C + 1, 7):
		cv2.putText(img, str(c), (m + (c - 1) * cell_px + 2, m - 8), f, 0.4, (0, 0, 0), 1, cv2.LINE_AA)
	for l in range(1, R + 1, 5):
		cv2.putText(img, str(l), (4, m + (l - 1) * cell_px + 15), f, 0.4, (0, 0, 0), 1, cv2.LINE_AA)
	for pl in sol.chosen:     # block outlines
		cs = list(pl.cells.values())
		ls, cc = [x[0] for x in cs], [x[1] for x in cs]
		cv2.rectangle(img, (m + (min(cc) - 1) * cell_px, m + (min(ls) - 1) * cell_px),
					  (m + max(cc) * cell_px - 1, m + max(ls) * cell_px - 1), (0, 0, 0), 2)
	ly = img.shape[0] - 30
	x = m
	for k, t in (("antes", "colocada antes"), ("alta", "nova alta"), ("media", "nova media"), ("baixa", "nova baixa"),
				 ("falta", "em falta"), ("novo_int", "interior da seccao"), ("interior_cheio", "interior ocupado"),
				 ("interior", "interior vazio")):
		cv2.rectangle(img, (x, ly - 10), (x + 12, ly + 2), col[k], -1)
		cv2.putText(img, t, (x + 16, ly), f, 0.42, (0, 0, 0), 1, cv2.LINE_AA)
		x += 24 + 8 * len(t)
	cv2.putText(img, "circulo branco = fixada pela gemea; contorno preto = bloco (seccao) ancorado por este solve",
				(m, ly + 20), f, 0.42, (0, 0, 0), 1, cv2.LINE_AA)
	os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
	cv2.imwrite(path, img, [cv2.IMWRITE_JPEG_QUALITY, 85])
	return path


def write_report(project, sol: BorderSolution, path: str, *, figure: Optional[str] = None, applied: Optional[list] = None,
				 after: Optional[dict] = None) -> str:
	"""Markdown report (Portuguese) of a :class:`BorderSolution`."""
	prof = project.profile
	inv = sol.inventory
	L = []
	a = L.append
	a("# Borda: colocação das peças de borda das secções por ancorar (`src/border.py`)\n")
	repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
	rel = os.path.relpath(project.path, repo).replace(os.sep, "/")
	where = rel if not rel.startswith("..") else "cópia de trabalho fora do repositório"
	a(f"Gerado por `python -m src.border{' --apply' if applied is not None else ''} --report ...` sobre o projeto "
	  f"`{project.meta.get('id')}` ({where}; {len(project.events())} eventos no log no fim) em {time.strftime('%Y-%m-%d %H:%M')} "
	  f"({_fmt(sol.elapsed_s, 0)} s). Etiquetas: **[V]** verificado com evidência, **[NT]** não testado, **[F]** testado e falha.\n")
	a("## Facto de partida\n")
	a("A borda física está completa exceto (1,29) (Tiago, 2026-11-01): cada célula de borda `ocupada_legado` tem uma das "
	  "peças digitalizadas que o solve do legado deixou por ancorar. O problema é de atribuição (cobertura exata), "
	  "não de localização livre.\n")
	a("## Inventário\n")
	by = inv["por_estado"]
	n_col = by.get("colocada", 0)
	a(f"- Peças com ≥ 1 lado F (sem `same_as`/`descartada`): **{inv['total']}** = " +
	  " + ".join(f"{v} `{k}`" for k, v in sorted(by.items())) + f"; esperado {inv['esperado']} − 1 = {inv['esperado'] - 1} "
	  f"(borda completa menos (1,29)) **[V]** (contagem).")
	a(f"- Células de borda livres: {len(sol.free_cells)} = {len(sol.free_cells) - len(sol.missing_cells)} `ocupada_legado` "
	  f"+ {len(sol.missing_cells)} `vazia` {sol.missing_cells}; peças candidatas: {len(sol.pieces)} em {len(sol.blocks)} blocos "
	  f"({sum(1 for p in sol.pieces.values() if p.n_flat >= 1)} com F + "
	  f"{', '.join(f'{q} ({p.label})' for q, p in sorted(sol.pieces.items()) if p.n_flat == 0)} sem F: interiores que se "
	  f"movem com a secção, ou peça solta do legado sem 4 cantos).")
	nF_free = sum(1 for p in sol.pieces.values() if p.n_flat >= 1)
	a(f"- {n_col} colocadas + {nF_free} livres com F = {n_col + nF_free} para {inv['esperado'] - 1} peças de borda reais: "
	  f"**pelo menos {n_col + nF_free - (inv['esperado'] - 1)} etiquetas F a mais** (lados quase retos ou mordidos; F é evidência fraca; a solução deixa de fora {len(sol.leftover)} blocos com F e usa as peças sem F acima) **[V]**.\n")
	cal = sol.calibration
	a("### Calibração na borda colocada\n")
	a(f"- Gémeas na borda já colocada (pares colocada↔colocada, {cal['gemeas_n']}): distância livre mediana "
	  f"{_fmt(cal['gemeas_mediana'], 3)} mm, p90 {_fmt(cal['gemeas_p90'], 3)}, {_fmt(100 * (cal['gemeas_frac_tmax'] or 0), 1)} % ≤ "
	  f"tmax, {cal['gemeas_n_acima_1mm']} acima de 1 mm **[V]**: a forma da gémea é evidência forte também nos scans do legado.")
	a(f"- Orientação: os lados F das peças colocadas (pose da secção ancorada ou `theta_deg` da GT) apontam para fora em "
	  f"{cal['f_dir_consistente'][0]}/{cal['f_dir_consistente'][1]} células de borda **[V]** (é o que valida o referencial "
	  "usado para os vizinhos fixos).")
	a(f"- Custo de lado de vizinhos verdadeiros ao longo da borda ({cal['n_pares']} pares colocados): mediana "
	  f"{_fmt(cal['lado_mediana'])}, p90 {_fmt(cal['lado_p90'])}; {_fmt(100 * (cal['lado_frac_TB_ok'] or 0), 0)} % são T↔B "
	  f"(o resto F/T-T/B-B por etiqueta errada) **[V]**; `SIDE_NEUTRAL` = {_fmt(SIDE_NEUTRAL)} ≈ mediana.")
	a(f"- Desvio máximo |y|/corda dos lados F que apontam para fora: p99 {_fmt(cal['f_dev_borda_p99'], 3)}, máx "
	  f"{_fmt(cal['f_dev_borda_max'], 3)} (n = {cal['n_f_borda']}); lados F que NÃO apontam para fora: {cal['f_dev_fora']} "
	  f"**[V]**; limiar de suspeita `F_SUSPECT_DEV` = {_fmt(F_SUSPECT_DEV, 3)}.\n")
	a("### Suspeitas de F\n")
	if sol.suspects:
		a("| peça | página | secção | n_F | razão |\n|---|---|---|---|---|")
		for s in sol.suspects:
			a(f"| {s['piece']} | {s['label']} | {s['section'] or '—'} | {s['n_flat']} | {'; '.join(s['reasons'])} |")
	else:
		a("Nenhuma.")
	a("")
	a("## Passo 1: gémeas (1 contra 1, só forma)\n")
	cs = prof.calibration.get("silhueta_silhueta", {})
	a(f"Para cada célula livre cuja gémea está colocada com silhueta: distância livre à peça colocada de todas as peças "
	  f"livres que passam classe + cordas; pino se d1 ≤ tmax {_fmt(cs.get('tmax'), 3)} e margem ≥ "
	  f"{_fmt(prof.calibration.get('margin_min'), 1)}, ou d1 ≤ t95 {_fmt(cs.get('t95'), 3)} com candidata única. "
	  "Sem imagem (a arte da borda não discrimina).\n")
	a("| célula | gémea | peça na gémea | passam | top-3 (peça, d mm, passa) | d1 | margem | pino |\n|---|---|---|---|---|---|---|---|")
	for r in sol.twin_table:
		top = "; ".join(f"{sol.pieces[p].label if p in sol.pieces else p} {_fmt(d, 3)}{'' if ok else ' ✗'}" for p, d, ok in r["top"])
		pin = (sol.pieces[r["pin"]].label if r["pin"] else ("conflito " + str(r.get("pin_conflito")) if r.get("pin_conflito") else "—"))
		a(f"| ({r['cell'][0]},{r['cell'][1]}) | ({r['twin_cell'][0]},{r['twin_cell'][1]}) | {r['twin_piece']} | {r['n_pass']} | "
		  f"{top} | {_fmt(r['d1'], 3)} | {_fmt(r['margin'])} | {pin} |")
	a(f"\n{len(sol.pins)} pinos (restrição dura na cadeia). Verificação: cada pino retirado à vez, a cadeia sozinha "
	  "(lados + restantes pinos + ΔE) põe a peça na mesma célula?")
	for q, v in sorted(sol.pin_check.items()):
		a(f"- {q} ({sol.pieces[q].label}) → ({v['cell'][0]},{v['cell'][1]}): sem o pino vai para "
		  f"{v['sem_pino']} — **{'concorda' if v['acorda'] else 'discorda'}** [V]")
	a("")
	a("## Passo 2: cadeia (cobertura exata com custo)\n")
	a("Colunas das tabelas, por peça: custo `F fora`, `lados fixos` (contra peças já ancoradas), `lados internos` (dentro "
	  "da secção), ΔE da peça na célula; os lados entre blocos novos entram no custo do segmento.\n")
	a(f"Custo = lados frente a frente (T↔B: RMS + {_fmt(SIDE_DL_W, 1)}·Δcorda, teto {_fmt(SIDE_COST_MAX, 1)}; F frente a peça "
	  f"{_fmt(SIDE_P_F, 1)}; T-T/B-B {_fmt(SIDE_P_KIND, 1)}; lado desconhecido {_fmt(SIDE_NEUTRAL)}) + {_fmt(F_OUT_W, 1)} por "
	  f"direção de borda sem F + {_fmt(TWIN_W, 1)}·d(gémea) (teto {_fmt(TWIN_CAP_MM, 1)} mm) + {_fmt(DE_W, 2)}·ΔE. "
	  f"Custo total ótimo {_fmt(sol.cost)}. Margem de um bloco = (C₂ − C₁ + c_B)/c_B, C₂ = melhor solução com uma peça do "
	  "bloco fora da sua célula, c_B = termos de custo que envolvem o bloco; margem de um segmento idem com outra atribuição "
	  "no segmento. `alta` = fixada pela gémea ou margem ≥ margin_min; `media` ≥ 1,2; `baixa` abaixo.\n")
	for sg in sol.segments:
		a(f"### {sg['name']} ({len(sg['cells'])} células)\n")
		a(f"Blocos: " + "; ".join(f"{bid} rot {rot}° em {anc}" for bid, rot, anc in sg["blocks"]) +
		  f". Custo do segmento {_fmt(sg['cost'])}, 2.ª melhor solução {_fmt(sg['C2'])} vs {_fmt(sol.cost)} → margem "
		  f"**{_fmt_m(sg['margin'])}**.\n")
		a("| célula | peça | página | bloco | rot | conf. | margem do bloco | gémea d mm | F fora | lados fixos | lados internos | ΔE | alternativa |")
		a("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
		for x in sg["cells"]:
			ci = sol.cell_info[x]
			t = ci["terms"]["por_peca"][ci["piece"]]
			alt = ci["alt_piece"]
			a(f"| ({x[0]},{x[1]}) | {ci['piece']}{' 📌' if ci['pinned'] else ''} | {sol.pieces[ci['piece']].label} | {ci['block']} | "
			  f"{ci['rot']} | {ci['confianca']} | {_fmt_m(ci['margin'])} | {_fmt(ci['twin_d'], 3)} | {_fmt(t['f_out'], 1)} | "
			  f"{_fmt(t['lado_fixo'])} | {_fmt(t['lado_interno'])} | {_fmt(t['dE'] / DE_W if DE_W else 0, 1)} | "
			  f"{(sol.pieces[alt].label if alt in sol.pieces else alt) if alt else '—'} |")
		a("")
	extra = [(x, ci) for x, ci in sol.cell_info.items() if not ci["required"]]
	if extra:
		a("Células interiores ocupadas pelas secções (peças sem F que se movem com o bloco): " +
		  ", ".join(f"({x[0]},{x[1]}) {ci['piece']} ({sol.pieces[ci['piece']].label})" for x, ci in sorted(extra)) + ".\n")
	a("## Resumo das decisões\n")
	req = {x: ci for x, ci in sol.cell_info.items() if ci["required"]}
	nconf = {k: sum(1 for ci in req.values() if ci["confianca"] == k) for k in ("alta", "media", "baixa")}
	by_how = {"gémea": sum(1 for ci in req.values() if ci["pinned"]),
			  "bloco com pino": sum(1 for ci in req.values() if ci["block_pinned"] and not ci["pinned"]),
			  "cadeia": sum(1 for ci in req.values() if not ci["block_pinned"])}
	a(f"- Células decididas: {len(req)} de {len(sol.free_cells) - len(sol.missing_cells)} a cobrir; por gémea {by_how['gémea']}, "
	  f"pelo bloco de uma peça fixada pela gémea {by_how['bloco com pino']}, pela cadeia/eliminação {by_how['cadeia']}.")
	a(f"- Confiança: alta {nconf['alta']}, media {nconf['media']}, baixa {nconf['baixa']}.")
	a(f"- (1,29): fica vazia ({'há' if len(sol.leftover) == 1 else 'não há exatamente'} uma sobra)." if (1, 29) in sol.missing_cells else "")
	a("- Peças/blocos que sobram (não colocados): peça interior com um lado quase reto etiquetado F, peça danificada, ou "
	  "a peça é a de outra célula e a escolhida está errada. Para cada peça, a forma colocada mais próxima (se for a gémea, "
	  "a peça pertence à célula gémea dessa):")
	for lo in sol.leftover:
		parts = []
		for p, lb in zip(lo["pieces"], lo["labels"]):
			n = lo["near"].get(p)
			if n:
				parts.append(f"{p} ({lb}): mais próxima {n['placed']} em ({n['cell'][0]},{n['cell'][1]}) a {_fmt(n['d'], 3)} mm"
							 + (f" → célula gémea ({n['twin_cell'][0]},{n['twin_cell'][1]}) `{n['twin_estado']}`"
								if n["twin_cell"] else ""))
			else:
				parts.append(f"{p} ({lb})")
		a(f"  - {lo['block']}: " + "; ".join(parts) + (f" [{'; '.join(lo['suspect'])}]" if lo["suspect"] else ""))
	if not sol.leftover:
		a("  - nenhuma")
	a("")
	a("## Verificar fisicamente\n")
	low = [(x, ci) for x, ci in sorted(req.items()) if ci["confianca"] != "alta" or ci.get("why")]
	if low:
		a("Última coluna: as 3 formas mais próximas da peça colocada na célula gémea entre **todas** as peças do projeto "
		  "(não só as candidatas): se nenhuma está perto (≤ tmax), a peça desta célula não tem gémea digitalizada com forma "
		  "fiável, ou a peça colocada na célula gémea está ela própria errada/danificada.\n")
		a("| célula | peça proposta | página | conf. | margem | porquê | alternativa (2.ª melhor) | gémea no projeto (top-3) |\n"
		  "|---|---|---|---|---|---|---|---|")
		for x, ci in low:
			alt = ci["alt_piece"]
			gp = ci.get("gemea_no_projeto") or []
			gps = "; ".join(f"{g['piece']} {_fmt(g['d'], 2)} mm ({g['estado']}{' ' + str(tuple(g['cell'])) if g['cell'] else ''})"
							for g in gp) or "—"
			a(f"| ({x[0]},{x[1]}) | {ci['piece']} | {sol.pieces[ci['piece']].label} | {ci['confianca']} | {_fmt_m(ci['margin'])} | "
			  f"{'; '.join(ci.get('why') or []) or 'margem'} | "
			  f"{(alt + ' (' + sol.pieces[alt].label + ')') if alt in sol.pieces else '—'} | {gps} |")
	else:
		a("Nada abaixo de `alta`.")
	a("")
	out = sol.calibration.get("gemeas_acima_1mm") or []
	if out:
		a("Pares de gémeas já colocados (fora deste solve) com distância > 1 mm, a rever: " +
		  "; ".join(f"({c1[0]},{c1[1]}) {p1} ↔ ({c2[0]},{c2[1]}) {p2} a {_fmt(d)} mm" for c1, c2, p1, p2, d in out) + " **[V]**.\n")
	if applied is not None:
		a("## Aplicação\n")
		a(f"{len(applied)} operações no log (`section_anchored` / `placed`, fonte `legado_scan`, origem `borda`). Depois: "
		  f"`missing_border_cells()` = {after.get('missing')}; borda `ocupada_legado` = {after.get('ocupada_legado')}; "
		  f"`check_invariants()` = {after.get('invariants')} **[V]**.\n")
	if figure:
		a("## Figura\n")
		a(f"![borda]({os.path.basename(figure)}) — `{os.path.basename(figure)}`: anel da borda; verde = colocada antes, azul = "
		  "colocada por este solve (escuro alta, médio media, claro baixa; círculo branco = fixada pela gémea; contorno preto = "
		  "bloco), vermelho = em falta, cinzento = interior.\n")
	if sol.notes:
		a("## Notas\n")
		for n in sol.notes:
			a(f"- {n}")
		a("")
	a("## O que não está verificado\n")
	a("- Nenhuma das colocações novas foi confirmada fisicamente **[NT]**: a lista acima é a ordem de verificação.")
	a("- A margem por custo depende de pesos escolhidos (não calibrados contra GT de borda colocada por este solve) **[NT]**.")
	os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
	with open(path, "w", encoding="utf-8", newline="\n") as f:
		f.write("\n".join(x for x in L if x is not None) + "\n")
	return path


def main(argv=None) -> int:
	ap = argparse.ArgumentParser(description="Completa a borda: peças de borda das secções por ancorar -> células livres.")
	ap.add_argument("--project", required=True)
	ap.add_argument("--apply", action="store_true", help="ancora/coloca a solução no projeto (log)")
	ap.add_argument("--report", default=None, help="relatório Markdown (a figura borda_tabuleiro.jpg vai para a mesma pasta)")
	ap.add_argument("--no-image", action="store_true", help="sem o termo de imagem (ΔE)")
	args = ap.parse_args(argv)
	from src.state import Project, StateError
	try:
		pr = Project.open(args.project)
	except StateError as e:
		print(f"erro: {e}", file=sys.stderr)
		return 1
	before = {lc: cell["estado"] for lc, cell in pr.board.iter_cells()}
	sol = solve_border(pr, use_image=not args.no_image, log=print)
	if sol.error:
		print(f"erro: {sol.error}", file=sys.stderr)
		return 1
	req = [ci for ci in sol.cell_info.values() if ci["required"]]
	print(f"solução: custo {sol.cost:.2f}; alta {sum(c['confianca'] == 'alta' for c in req)}, media "
		  f"{sum(c['confianca'] == 'media' for c in req)}, baixa {sum(c['confianca'] == 'baixa' for c in req)}; "
		  f"sobras {[lo['block'] for lo in sol.leftover]} ({sol.elapsed_s:.0f} s)")
	for sg in sol.segments:
		print(f"  {sg['name']}: {sg['blocks']} margem {sg['margin']:.2f}")
	applied, after = None, None
	if args.apply:
		try:
			applied = apply_solution(pr, sol)
		except StateError as e:
			print(f"erro ao aplicar: {e}", file=sys.stderr)
			return 1
		pr.save()
		after = {"missing": pr.missing_border_cells(),
				 "ocupada_legado": sum(1 for lc, c in pr.board.iter_cells() if pr.profile.is_border(*lc) and c["estado"] == "ocupada_legado"),
				 "invariants": pr.check_invariants(disk=True) or "OK"}
		print(f"aplicado: {len(applied)} operações; em falta {after['missing']}; invariantes {after['invariants']}")
	if args.report:
		fig = os.path.join(os.path.dirname(os.path.abspath(args.report)), "borda_tabuleiro.jpg")
		draw_board(pr, sol, fig, before=before)
		write_report(pr, sol, args.report, figure=fig, applied=applied, after=after)
		print(f"relatório: {args.report}; figura: {fig}")
	return 0


if __name__ == "__main__":
	sys.exit(main())
