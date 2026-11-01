"""Legacy scans (``images/pieces/legado/``): where on the board is each page of the exploded view?

The legacy is what Tiago assembled by hand before the project existed, scanned piece by
piece in an exploded view (``montado_pNN``: on the board; ``blocos_pNN``: groups assembled
off the board). Nothing on a page says which zone of the puzzle it is, how it is turned,
or where the holes are. This module infers it, and asks when it cannot decide.

Per page (:func:`analyse_page` -> :class:`PageResult`):

1. ``segment_scan`` (300 dpi, crops in the scan frame); fragments (< ``MIN_PIECE_MM2``)
   rejected; ``is_cluster`` or area > ``DOUBLE_AREA_FACTOR`` x median -> ``objeto_duplo``
   (one split attempt with ``segment_pieces``; if it does not split, the object is left out
   and listed);
2. :func:`src.shape.analyse`; page orientation = 4-fold circular mean of the body angles;
   every side is labelled N/E/S/W in the page frame by the direction of its outward normal
   (tolerance ``SIDE_TOL_DEG``);
3. **local grid**: candidate edges between page neighbours (to the right / below, within
   ``NEIGH_ALONG`` x ``NEIGH_ACROSS`` cells), validated by the facing sides (T with B only,
   never F, :func:`src.shape.side_complement` RMS <= ``SIDE_RMS_MAX``, chord difference <=
   ``SIDE_DL_MAX``); edges are merged cheapest first (Kruskal) into **components** with
   integer local cells ``(r, c)``; a merge is refused if two pieces would share a cell or if
   the F sides of the merged component are inconsistent (all F sides of one direction on the
   same extreme row/column). This replaces the planned per-row dynamic programming: the
   pages are not all 2D blocks (p01 and p12 are border strips folded into page columns,
   several pages hold 2-3 sub-blocks side by side), so the unit is the component, not the
   page;
4. **registration** of each component against the artwork with
   :func:`src.locate.locate_group` (4 rotations, mirror only as a check, hard F rules, weak
   occupancy prior); ``margin`` = score of the best *distinct* placement (member cells at
   a mean Chebyshev distance >= ``DISTINCT_CELLS``) / best score.

Across pages (:func:`solve_pages`): pages that are re-scans of an earlier page are set
aside (``duplicada``). Silhouette twins between all pieces (same class, chord filter, free
distance <= ``profile.calibration['silhueta_silhueta']['t95']``, mutual nearest neighbours)
tie components together: a placement of one component predicts the cell and the board
rotation of the twin in another. Every component gets candidates (its image top-``TOPK`` +
the placements implied by its partners' candidates) and one is chosen per component by
minimising image score - ``W_TWIN`` x (satisfied - violated pairs) + ``W_OVERLAP`` x (cells
shared by two components) + ``W_PRIOR`` x (cells the occupancy map contradicts), moving a
component together with the components tied to it by twins (otherwise a twin-linked pair of
sections can sit jointly shifted in uniform sky/grass). Decision, largest components first:
``alta`` needs an image margin >= ``profile.calibration['margin_min']`` with a positive energy
gap, or an energy gap >= ``TWIN_GAP_MIN`` x ``W_TWIN``, no conflict with components already
``alta``, the mirror not better, and (when given) the GT all right; otherwise ``ambigua`` with
the top-3 and a concrete question. Never guess: ``ambigua`` does not anchor.

Project side (:func:`ingest_page`, :func:`solve_project_sections`). Order of calls::

	python -m src.ingest montado_p01.jpg --montado p01      # each page: scan + pieces + sections
	...                                                     # (anchors its own 'alta' components)
	python -m src.ingest montado_p15.jpg --montado p15
	python -m src.ingest blocos_p01.jpg --blocos p01        # groups: sections, never anchored
	legacy.solve_project_sections(project)                  # once all pages are in: twins between
	                                                        # sections, anchors what became 'alta'

Ground truth is only ever used to *measure* (:func:`match_gt`), never to decide, except in
:func:`ingest_page` where a page piece that is the same physical piece as a project piece
with a known cell is marked ``same_as`` (the GT entry prevails).

Nothing puzzle-specific: grid, symmetry, thresholds and the art come from the
:class:`src.profile.PuzzleProfile`. Pure functions except :func:`analyse_page`,
:func:`load_prior`, :func:`ingest_page` and :func:`solve_project_sections`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from src.locate import (PRIOR_WEIGHT, body_beta_deg, body_center_mm, de_cell, locate_group, piece_mean_lab,
						render_item, wrap_deg)
from src.shape import Shape, analyse, chord_pass, side_complement

__all__ = [
	"PagePiece", "Component", "PageResult", "SIDE_TOL_DEG", "SIDE_RMS_MAX", "SIDE_DL_MAX", "NEIGH_ALONG",
	"NEIGH_ACROSS", "TOPK", "DISTINCT_CELLS", "W_TWIN", "TWIN_GAP_MIN", "GROUP_GAP_MM", "SAME_PIECE_DE",
	"TWIN_ROT_TOL", "MIN_PLACE_PIECES", "N_IMPLY", "W_OVERLAP", "MIRROR_WIN", "MIN_LINK", "DUP_FRAC", "W_PRIOR",
	"duplicate_pages", "page_rotation", "label_sides", "side_compat", "build_components", "group_by_proximity",
	"crop_rgba", "analyse_pieces", "analyse_page", "placement_score", "distinct_margin", "twin_pairs",
	"solve_pages", "match_gt", "load_prior", "ingest_page", "solve_project_sections", "component_cells",
]

# ---------------------------------------------------------------- constants
SIDE_TOL_DEG = 25.0         # a side is N/E/S/W if its outward normal is within this of the page axis
SIDE_RMS_MAX = 1.6          # side_complement RMS (mm) of a valid edge; true BE adjacencies: 0.77..1.58 (LEGADO.md)
SIDE_DL_MAX = 2.0           # |chord difference| (mm) of a valid edge
NEIGH_ALONG = (0.6, 2.0)    # centre distance (cells) along the edge direction of a page-neighbour candidate
NEIGH_ACROSS = 0.7          # max centre offset (cells) across the edge direction
W_ACROSS = 0.5              # edge cost per cell of offset across (prefers the geometrically aligned neighbour)
TOPK = 40                   # image placements kept per component
N_IMPLY = 10                # candidates of a partner unit that propose twin-implied placements
W_OVERLAP = 2.0             # dE units per cell shared with another section
MIRROR_WIN = 1.1            # the mirror 'wins' if image-best non-mirror score / best mirror score >= this
MIN_LINK = 2                # twin pairs that tie two units into one move in solve_pages
DUP_FRAC = 0.5              # share of same-piece matches that makes a page a re-scan of another
W_PRIOR = 2.0               # solve_pages: dE units per member on a cell the occupancy map contradicts (0 for montado, 1 for blocos)
DISTINCT_CELLS = 1.0        # placements count as distinct if member cells move >= this (mean Chebyshev); 1, not 2: p14 was off by 1 column
W_TWIN = 3.0                # dE units per net satisfied twin pair in the cross-page solve
TWIN_GAP_MIN = 2            # an energy gap of this many twin pairs (x W_TWIN) decides without the image margin
TWIN_ROT_TOL = 45.0         # deg: a twin pair agrees on the rotation if the board poses differ by < this
GROUP_GAP_MM = 3.0          # blocos: proximity groups (contour to contour), reported only: the groups come from the sides
SAME_PIECE_DE = 10.0        # mean-Lab dE below which a shape match between two scans is the same piece
MIN_PLACE_PIECES = 1        # components smaller than this are not located
SPLIT_PAD_MM = 6.0          # padding of the objeto_duplo split attempt
_DIRS = ("N", "E", "S", "W")
_NORMAL_DEG = {"E": 0.0, "S": 90.0, "W": 180.0, "N": -90.0}  # image frame, y down
_STEP = {"E": (0, 1), "S": (1, 0), "W": (0, -1), "N": (-1, 0)}


# ---------------------------------------------------------------- data
@dataclass
class PagePiece:
	"""One piece of a legacy page.

	n: reading-order number on the overlay (1-based). index: index in the segmentation.
	contour: px, scan frame. theta_deg: rotation (complex convention, clockwise on screen)
	that takes the crop to the page-aligned frame. dirs: page direction -> side index.
	flat_dirs: page directions of the F sides (None if the sides could not be labelled).
	center_mm: body centre in the page-aligned frame. comp: component id (-1 = none).
	rc: local cell in the component. excluded: reason the piece is left out ('' = in).
	"""

	n: int
	index: int
	contour: np.ndarray
	bbox: list
	area_mm2: float
	shape: Optional[Shape]
	flags: dict = field(default_factory=dict)
	theta_deg: float = 0.0
	dirs: dict = field(default_factory=dict)
	dirs_ok: bool = False
	flat_dirs: Optional[tuple] = None
	center_mm: np.ndarray = field(default_factory=lambda: np.zeros(2))
	mean_lab: Optional[list] = None
	rgba: Optional[np.ndarray] = field(default=None, repr=False)
	comp: int = -1
	rc: Optional[tuple] = None
	excluded: str = ""


@dataclass
class Component:
	"""Connected local grid (an assembled block, a strip, or one piece) and its placements.

	members: indices into ``PageResult.pieces``. rc: member -> local (r, c), r down, c right
	in the page-aligned frame, min r = min c = 0. edges: accepted edges ``(i, j, dir, rms,
	dl)``. rejected: candidate edges refused (reason). placements: dicts ``{cell0, rot, mirror,
	score, cells: {member: (l, c)}, origin, twin_sat, twin_viol, adj}`` best first.
	"""

	id: int
	members: list
	rc: dict
	edges: list = field(default_factory=list)
	rejected: list = field(default_factory=list)
	placements: list = field(default_factory=list)
	margin: float = float("nan")
	mirror_best: bool = False
	decision: str = "ambigua"
	reasons: list = field(default_factory=list)
	questions: list = field(default_factory=list)
	energy_gap: float = float("nan")
	mirror_ratio: float = 0.0

	@property
	def best(self) -> Optional[dict]:
		return self.placements[0] if self.placements else None


@dataclass
class PageResult:
	"""Result of :func:`analyse_pieces` / :func:`analyse_page` for one page."""

	name: str
	kind: str
	path: Optional[str]
	mm_per_px: float
	angle_deg: float
	n_segmented: int
	pieces: list
	components: list
	rejected: list = field(default_factory=list)
	double: list = field(default_factory=list)
	notes: list = field(default_factory=list)

	def comp_of(self, i: int) -> Optional[Component]:
		k = self.pieces[i].comp
		return self.components[k] if k >= 0 else None


# ---------------------------------------------------------------- geometry of a page (pure)
def page_rotation(shapes) -> float:
	"""Rotation (deg, complex convention) that aligns the page with the axes, in (-45, 45].

	4-fold circular mean of the per-piece :func:`src.locate.body_beta_deg` (pieces without 4
	corners use their contour orientation).
	"""
	b = [body_beta_deg(s) for s in shapes if s is not None]
	if not b:
		return 0.0
	z = np.sum(np.exp(4j * np.radians(b)))
	a = float(np.degrees(np.angle(z)) / 4.0)
	return a - 90.0 if a > 45.0 else (a + 90.0 if a <= -45.0 else a)


def _rot(v, deg: float) -> np.ndarray:
	t = np.radians(deg)
	R = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
	return np.asarray(v, float) @ R.T


def label_sides(shape: Shape, rot_deg: float):
	"""Page directions of the 4 sides: ``(dirs {dir: side index}, ok, flat_dirs tuple | None)``.

	The outward normal of side i (body centre -> chord midpoint), turned by ``rot_deg``, is
	matched to the nearest of N/E/S/W; ``ok`` is False if a side is more than
	``SIDE_TOL_DEG`` off or two sides get the same direction.
	"""
	if shape is None or not shape.ok:
		return {}, False, None
	ctr = body_center_mm(shape)
	dirs, ok = {}, True
	for i, s in enumerate(shape.sides):
		v = 0.5 * (s.p0_mm + s.p1_mm) - ctr
		a = float(np.degrees(np.arctan2(v[1], v[0]))) + rot_deg
		best = min(_DIRS, key=lambda d: abs(float(wrap_deg(a - _NORMAL_DEG[d]))))
		if abs(float(wrap_deg(a - _NORMAL_DEG[best]))) > SIDE_TOL_DEG or best in dirs:
			ok = False
		dirs.setdefault(best, i)
	if len(dirs) != 4:
		ok = False
	flat = tuple(sorted(d for d, i in dirs.items() if shape.sides[i].kind == "F")) if ok else None
	return dirs, ok, flat


def side_compat(sa, sb) -> dict:
	"""Facing sides ``sa`` (of the first piece) and ``sb``: ``{ok, why, rms, dl, cost}``.

	``why``: '' (ok), 'F' (a flat side faces a neighbour), 'kind' (T-T or B-B), 'rms' / 'dl'
	(T-B but the profiles or the chords disagree).
	"""
	if sa.kind == "F" or sb.kind == "F":
		return dict(ok=False, why="F", rms=np.inf, dl=np.inf, cost=np.inf)
	if sa.kind == sb.kind:
		return dict(ok=False, why="kind", rms=np.inf, dl=np.inf, cost=np.inf)
	rms, dl = side_complement(sa, sb)
	why = "rms" if rms > SIDE_RMS_MAX else ("dl" if dl > SIDE_DL_MAX else "")
	return dict(ok=not why, why=why, rms=float(rms), dl=float(dl), cost=float(rms + 0.5 * dl))


def _f_consistent(rc: dict, pieces: list) -> bool:
	"""All F sides of one page direction lie on the same extreme row/column of the component."""
	if not rc:
		return True
	R = np.array(list(rc.values()))
	ext = {"N": R[:, 0].min(), "S": R[:, 0].max(), "W": R[:, 1].min(), "E": R[:, 1].max()}
	for i, (r, c) in rc.items():
		for d in pieces[i].flat_dirs or ():
			coord = r if d in ("N", "S") else c
			if coord != ext[d]:
				return False
	return True


def build_components(pieces: list, cell_mm: float, *, allowed_pairs=None) -> tuple:
	"""Local grid of a page: ``(components, candidate_edges)``.

	``pieces``: :class:`PagePiece` with ``center_mm``, ``dirs``, ``dirs_ok`` and ``shape``.
	Candidate edges: j to the right of i (E/W) or below (S/N) at ``NEIGH_ALONG`` cells along
	and <= ``NEIGH_ACROSS`` across; valid if :func:`side_compat` is ok. Valid edges are merged
	cheapest first (cost = side cost + ``W_ACROSS`` x offset across); a merge that puts two
	pieces on one cell, or breaks :func:`_f_consistent`, is refused. ``allowed_pairs``:
	optional ``set`` of frozensets that edges must belong to (blocos: same proximity group).
	Every candidate edge is returned with its verdict (``'accepted'`` or the reason).
	"""
	idx = [i for i, p in enumerate(pieces) if not p.excluded]
	C = {i: np.asarray(pieces[i].center_mm, float) / float(cell_mm) for i in idx}
	cands = []
	for i in idx:
		for j in idx:
			if i == j:
				continue
			if allowed_pairs is not None and frozenset((i, j)) not in allowed_pairs:
				continue
			dv = C[j] - C[i]
			for d, along, across in (("E", dv[0], dv[1]), ("S", dv[1], dv[0])):
				if NEIGH_ALONG[0] <= along <= NEIGH_ALONG[1] and abs(across) <= NEIGH_ACROSS:
					cands.append((i, j, d, float(abs(across)), float(along)))
	edges = []
	for i, j, d, across, along in cands:
		pi, pj = pieces[i], pieces[j]
		opp = "W" if d == "E" else "N"
		if not (pi.dirs_ok and pj.dirs_ok):
			edges.append(dict(i=i, j=j, dir=d, ok=False, why="lados", rms=np.inf, dl=np.inf, cost=np.inf,
							  across=across, along=along))
			continue
		sc = side_compat(pi.shape.sides[pi.dirs[d]], pj.shape.sides[pj.dirs[opp]])
		edges.append(dict(i=i, j=j, dir=d, across=across, along=along, **sc))
	comp_of = {i: i for i in idx}
	rc_of = {i: {i: (0, 0)} for i in idx}
	order = sorted([e for e in edges if e["ok"]], key=lambda e: (e["cost"] + W_ACROSS * e["across"], e["along"]))
	# a piece takes at most one neighbour per direction
	used = set()
	for e in order:
		i, j, d = e["i"], e["j"], e["dir"]
		opp = "W" if d == "E" else "N"
		if (i, d) in used or (j, opp) in used:
			e["verdict"] = "lado já usado"
			continue
		a, b = comp_of[i], comp_of[j]
		ri, rj = rc_of[a][i], rc_of[b][j]
		step = _STEP[d]
		want = (ri[0] + step[0], ri[1] + step[1])
		if a == b:
			if rj == want:
				used.add((i, d))
				used.add((j, opp))
				e["verdict"] = "accepted"
			else:
				e["verdict"] = "ciclo inconsistente"
			continue
		off = (want[0] - rj[0], want[1] - rj[1])
		moved = {k: (r + off[0], c + off[1]) for k, (r, c) in rc_of[b].items()}
		cells_a = set(rc_of[a].values())
		if any(v in cells_a for v in moved.values()):
			e["verdict"] = "célula ocupada"
			continue
		merged = dict(rc_of[a])
		merged.update(moved)
		if not _f_consistent(merged, pieces):
			e["verdict"] = "F incoerente"
			continue
		for k in rc_of[b]:
			comp_of[k] = a
		rc_of[a] = merged
		del rc_of[b]
		used.add((i, d))
		used.add((j, opp))
		e["verdict"] = "accepted"
	for e in edges:
		e.setdefault("verdict", e.get("why") or "")
	comps = []
	roots = sorted(rc_of, key=lambda r: (-len(rc_of[r]), min(pieces[k].n for k in rc_of[r])))
	for cid, root in enumerate(roots):
		rc = rc_of[root]
		r0 = min(v[0] for v in rc.values())
		c0 = min(v[1] for v in rc.values())
		rc = {k: (v[0] - r0, v[1] - c0) for k, v in rc.items()}
		members = sorted(rc, key=lambda k: rc[k])
		acc = [e for e in edges if e.get("verdict") == "accepted" and comp_of[e["i"]] == root]
		comps.append(Component(id=cid, members=members, rc=rc, edges=acc))
	return comps, edges


def group_by_proximity(contours_mm: list, gap_mm: float = GROUP_GAP_MM) -> list:
	"""Groups (lists of indices) of pieces whose contours come within ``gap_mm`` of each other (union-find)."""
	n = len(contours_mm)
	P = [np.asarray(c, float).reshape(-1, 2)[::2] for c in contours_mm]
	lo = [p.min(0) for p in P]
	hi = [p.max(0) for p in P]
	parent = list(range(n))

	def find(x):
		while parent[x] != x:
			parent[x] = parent[parent[x]]
			x = parent[x]
		return x

	for i in range(n):
		for j in range(i + 1, n):
			if np.any(lo[j] - hi[i] > gap_mm) or np.any(lo[i] - hi[j] > gap_mm):
				continue
			d2 = ((P[i][:, None, :] - P[j][None, :, :]) ** 2).sum(-1).min()
			if d2 <= gap_mm * gap_mm:
				parent[find(i)] = find(j)
	groups = {}
	for i in range(n):
		groups.setdefault(find(i), []).append(i)
	return sorted(groups.values(), key=lambda g: min(g))


def crop_rgba(rgb: np.ndarray, contour_px, pad: int = 12) -> tuple:
	"""RGBA crop of a piece (scan frame, translated only) and its offset ``(x0, y0)``."""
	import cv2
	c = np.asarray(contour_px, float).reshape(-1, 2)
	x0, y0 = np.maximum(np.floor(c.min(0)).astype(int) - pad, 0)
	x1, y1 = np.ceil(c.max(0)).astype(int) + pad
	x1, y1 = min(x1, rgb.shape[1]), min(y1, rgb.shape[0])
	a = np.zeros((y1 - y0, x1 - x0), np.uint8)
	cv2.fillPoly(a, [np.round(c - [x0, y0]).astype(np.int32).reshape(-1, 1, 2)], 255)
	return np.dstack([rgb[y0:y1, x0:x1], a]), (int(x0), int(y0))


# ---------------------------------------------------------------- placement
def component_cells(comp: Component, cell0, rot: int, mirror: bool = False) -> dict:
	"""Board cell of every member for a placement (same convention as :func:`src.state.section_cell`)."""
	from src.state import section_cell
	anchor = {"l0": int(cell0[0]), "c0": int(cell0[1]), "rot": int(rot), "mirror": bool(mirror)}
	return {k: section_cell(anchor, rc) for k, rc in comp.rc.items()}


def _items(comp: Component, pieces: list) -> list:
	out = []
	for k in comp.members:
		p = pieces[k]
		it = {"mean_lab": p.mean_lab, "rc": comp.rc[k], "rgba": p.rgba, "theta_deg": p.theta_deg, "shape": p.shape}
		if p.dirs_ok:
			it["flat_dirs"] = set(p.flat_dirs or ())
		elif p.shape is not None and p.shape.ok:
			it["n_flat"] = int(p.shape.n_flat)
		out.append(it)
	return out


def _valid_placement(comp: Component, pieces: list, profile, cells: dict, rot: int, mirror: bool) -> bool:
	from src.locate import rotate_dir
	for k, (l, c) in cells.items():
		if not profile.in_grid(l, c):
			return False
		p = pieces[k]
		fd = profile.flat_directions(l, c)
		if p.dirs_ok:
			if {rotate_dir(d, rot, mirror) for d in (p.flat_dirs or ())} != fd:
				return False
		elif p.shape is not None and p.shape.ok and p.shape.n_flat != len(fd):
			return False
	return True


def placement_score(comp: Component, pieces: list, profile, art, cells: dict, rot: int, mirror: bool, *,
					prior=None, prior_expect: int = 1, mm_per_px: Optional[float] = None, cache: Optional[dict] = None) -> float:
	"""Image score of one placement, the formula of :func:`src.locate.locate_group` with ``refine``.

	Median over members of :func:`src.locate.de_cell` of the rendered crop on its cell (the
	mean-Lab dE when a member has no crop) + ``PRIOR_WEIGHT`` x fraction of members on cells
	whose prior is ``1 - prior_expect``.
	"""
	mmpp = float(mm_per_px if mm_per_px is not None else profile.mm_per_px())
	cache = {} if cache is None else cache
	vals = []
	shift = np.array([art.l_shift, 0.0, 0.0])
	for k, (l, c) in cells.items():
		p = pieces[k]
		if p.rgba is None:
			vals.append(float(np.linalg.norm(art.cell_lab_mean[l - 1, c - 1] - (np.asarray(p.mean_lab, float) - shift))))
			continue
		key = (k, int(rot) % 360, bool(mirror))
		if key not in cache:
			cache[key] = render_item(p.rgba, p.shape, float(p.theta_deg) + rot, art, mmpp, mirror=mirror)
		vals.append(de_cell(cache[key], l, c, art)["dE"])
	sc = float(np.median(vals))
	if prior is not None:
		pr = np.asarray(prior)
		sc += PRIOR_WEIGHT * float(np.mean([pr[l - 1, c - 1] == (1 - prior_expect) for (l, c) in cells.values()]))
	return sc


def _placement_dist(a: dict, b: dict) -> float:
	ks = list(a["cells"])
	return float(np.mean([max(abs(a["cells"][k][0] - b["cells"][k][0]), abs(a["cells"][k][1] - b["cells"][k][1]))
						  for k in ks]))


def distinct_margin(placements: list, key: str = "score") -> tuple:
	"""``(margin, index)``: ``placements[index][key] / placements[0][key]`` for the first placement at a
	mean Chebyshev distance >= ``DISTINCT_CELLS`` from the best (non-mirror only); ``(inf, None)`` if none."""
	if not placements:
		return float("nan"), None
	b = placements[0]
	for k, p in enumerate(placements[1:], 1):
		if p.get("mirror"):
			continue
		if _placement_dist(b, p) >= DISTINCT_CELLS:
			s1, s2 = float(b[key]), float(p[key])
			return (s2 / s1 if s1 > 0 else float("inf")), k
	return float("inf"), None


def _locate_component(comp: Component, pieces: list, profile, art, prior, prior_expect: int, mm_per_px: float) -> None:
	"""Fill ``comp.placements`` (top ``TOPK``, mirror placements tested and flagged)."""
	items = _items(comp, pieces)
	if any(it["mean_lab"] is None for it in items):
		comp.reasons.append("sem cor média")
		return
	res = locate_group(items, profile, art, prior=prior, topk=TOPK, mirror=True, refine=True,
					   prior_expect=prior_expect, mm_per_px=mm_per_px)
	pl = []
	for r in res:
		cells = {comp.members[i]: tuple(v) for i, v in r["cells"].items()}
		pl.append(dict(cell0=tuple(r["cell0"]), rot=int(r["rot"]), mirror=bool(r["mirror"]), score=float(r["score"]),
					   cells=cells, origin="cor", twin_sat=0, twin_viol=0, adj=float(r["score"])))
	comp.placements = pl
	if not pl:
		comp.reasons.append("nenhuma colocação respeita os lados F")


def _decide(comp: Component, margin_min: float, gt: Optional[dict] = None, gap: Optional[float] = None) -> None:
	"""``alta`` / ``ambigua`` for the first placement (the chosen one; energy in ``adj``).

	Image margin = lowest image score among the distinct alternatives (mean Chebyshev
	distance >= ``DISTINCT_CELLS``) / image score of the chosen one; energy gap = ``gap`` when
	given (:func:`solve_pages`: the cheapest move, tied partners following, to a distinct
	placement), else the lowest energy among them - energy of the chosen one. ``alta`` needs (margin >= ``margin_min`` and
	gap > 0) or gap >= ``TWIN_GAP_MIN`` x ``W_TWIN``; no violated twin pair; no cell shared
	with another section (both counted, when :func:`solve_pages` provides them, only against
	units already decided ``alta``: ``twin_viol_fixed`` / ``overlap_fixed``); the best mirror
	placement not better than the image-best non-mirror one by ``MIRROR_WIN`` or more; more
	than one piece unless a twin supports it; and the GT (if given) all right.
	"""
	comp.reasons = [r for r in comp.reasons if r.startswith("sem ") or r.startswith("nenhuma")]
	comp.questions = []
	nonmir = [p for p in comp.placements if not p["mirror"] and np.isfinite(p["score"])]
	if not nonmir:
		comp.decision = "ambigua"
		return
	best = nonmir[0]
	alts = [p for p in nonmir[1:] if _placement_dist(best, p) >= DISTINCT_CELLS]
	if alts:
		m = min(p["score"] for p in alts) / best["score"] if best["score"] > 0 else float("inf")
		g = min(p["adj"] for p in alts) - best["adj"]
	else:
		m, g = float("inf"), float("inf")
	gap = g if gap is None else float(gap)
	comp.margin = float(m)
	comp.energy_gap = float(gap)
	mirrors = [p for p in comp.placements if p["mirror"]]
	img_best = min(p["score"] for p in nonmir)
	comp.mirror_ratio = float(img_best / min(p["score"] for p in mirrors)) if mirrors else 0.0
	comp.mirror_best = comp.mirror_ratio >= MIRROR_WIN
	ok = (m >= margin_min and gap > 0) or gap >= TWIN_GAP_MIN * W_TWIN
	viol = best.get("twin_viol_fixed", best.get("twin_viol", 0))
	ov = best.get("overlap_fixed", best.get("overlap", 0))
	why = []
	if len(comp.members) < 2 and best.get("twin_sat", 0) == 0:
		why.append("1 peça sem gémea")
	if not ok:
		why.append(f"margem {m:.2f}, ganho {gap:.1f}")
	if viol:
		why.append(f"{viol} par(es) de gémeas violado(s)")
	if ov:
		why.append(f"{ov} célula(s) partilhada(s) com outra secção")
	if comp.mirror_best:
		why.append(f"o espelho ganha (×{comp.mirror_ratio:.2f})")
	if gt and gt.get("n") and gt.get("ok") != gt.get("n"):
		why.append(f"GT {gt['ok']}/{gt['n']}")
	comp.decision = "ambigua" if why else "alta"
	comp.reasons += why


def _question(name: str, comp: Component, pieces: list) -> str:
	top = [p for p in comp.placements if not p["mirror"]]
	opts, seen = [], []
	for p in top:
		if any(_placement_dist(p, q) < DISTINCT_CELLS for q in seen):
			continue
		seen.append(p)
		ls = [v[0] for v in p["cells"].values()]
		cs = [v[1] for v in p["cells"].values()]
		opts.append(f"filas {min(ls)}–{max(ls)}, colunas {min(cs)}–{max(cs)} (rot {p['rot']}°)")
		if len(opts) == 3:
			break
	ns = sorted(pieces[k].n for k in comp.members)
	who = f"peças {ns[0]}–{ns[-1]}" if len(ns) > 1 else f"peça {ns[0]}"
	return f"{name} ({who}, {len(ns)} peças): " + " ou ".join(f"{chr(65 + i)} {o}" for i, o in enumerate(opts)) + "?"


# ---------------------------------------------------------------- one page
def _split_double(rgb: np.ndarray, contour_px, mm_per_px: float) -> list:
	"""Try to split an objeto_duplo with ``segment_pieces`` on its masked crop; contours (scan px) or []."""
	import cv2
	from PIL import Image
	from src.segmentation import segment_pieces
	pad = int(round(SPLIT_PAD_MM / mm_per_px))
	c = np.asarray(contour_px, float).reshape(-1, 2)
	x0, y0 = np.maximum(np.floor(c.min(0)).astype(int) - pad, 0)
	x1, y1 = np.ceil(c.max(0)).astype(int) + pad
	sub = rgb[y0:y1, x0:x1].copy()
	m = np.zeros(sub.shape[:2], np.uint8)
	cv2.fillPoly(m, [np.round(c - [x0, y0]).astype(np.int32).reshape(-1, 1, 2)], 255)
	m = cv2.dilate(m, np.ones((7, 7), np.uint8))
	bg = np.median(sub[m == 0].reshape(-1, 3), axis=0) if (m == 0).any() else np.array([90, 200, 90])
	sub[m == 0] = bg.astype(np.uint8)
	res = segment_pieces(Image.fromarray(sub), split_touching=True, normalize_rotation=False)
	if "error" in res:
		return []
	out = [np.asarray(p["contour"]).reshape(-1, 2) + [x0, y0] for p in res["pieces"]
		   if not p.get("is_cluster") and float(p["area_px"]) * mm_per_px ** 2 >= _min_piece_mm2()]
	return out if len(out) >= 2 else []


def _min_piece_mm2() -> float:
	from src.ingest import MIN_PIECE_MM2
	return float(MIN_PIECE_MM2)


def _double_factor() -> float:
	from src.ingest import DOUBLE_AREA_FACTOR
	return float(DOUBLE_AREA_FACTOR)


def analyse_pieces(raw: list, profile, art, prior, kind: str, mm_per_px: float, *, name: str = "",
				   path: Optional[str] = None, n_segmented: Optional[int] = None, rejected=None, double=None) -> PageResult:
	"""Local grid + registration of one page from already segmented pieces (pure).

	``raw``: dicts ``{'contour' (px), 'rgba' (crop, translated only; optional), 'index',
	'bbox', 'area_mm2', 'flags', 'excluded' (optional reason)}``. ``kind``: ``'montado'``
	(components should sit on occupied cells of ``prior``) or ``'blocos'`` (off the board:
	prior expects empty cells; the groups are the components found by the sides, proximity
	groups within ``GROUP_GAP_MM`` are only reported in ``notes``). ``art``:
	:class:`src.locate.CellArt` or None (no registration).
	"""
	from src.ingest import grid_order
	cell_mm = float(np.mean([profile.cell_mm["w"], profile.cell_mm["h"]]))
	order = grid_order([r["bbox"] for r in raw]) if raw else []
	pieces = []
	for r, n in zip(raw, order):
		sh = None
		if not r.get("excluded"):
			sh = analyse(r["contour"], mm_per_px)
		ml = None
		if r.get("rgba") is not None:
			ml = [float(v) for v in piece_mean_lab(r["rgba"])]
		pieces.append(PagePiece(n=int(n), index=int(r.get("index", len(pieces))), contour=np.asarray(r["contour"]).reshape(-1, 2),
								bbox=list(r["bbox"]), area_mm2=float(r["area_mm2"]), shape=sh, flags=dict(r.get("flags") or {}),
								mean_lab=ml, rgba=r.get("rgba"), excluded=r.get("excluded") or ""))
	rot = page_rotation([p.shape for p in pieces if p.shape is not None])
	for p in pieces:
		if p.shape is None:
			continue
		b = body_beta_deg(p.shape)
		p.theta_deg = float(rot + wrap_deg(b - rot))   # body-aligned, the nearest to the page rotation
		p.dirs, p.dirs_ok, p.flat_dirs = label_sides(p.shape, rot)
		p.center_mm = _rot(body_center_mm(p.shape), rot)
		if not p.shape.ok:
			p.excluded = p.excluded or "sem 4 cantos"
	notes = []
	comps, edges = build_components(pieces, cell_mm)
	if kind == "blocos":
		live = [i for i, p in enumerate(pieces) if p.shape is not None]
		groups = group_by_proximity([pieces[i].contour * mm_per_px for i in live])
		notes.append(f"{len(groups)} grupos por proximidade (≤ {GROUP_GAP_MM:g} mm); "
					 f"{sum(1 for c in comps if len(c.members) > 1)} componentes com ≥ 2 peças pelos lados")
		gid = {live[k]: g for g, members in enumerate(groups) for k in members}
		for c in comps:
			gs = {gid.get(k, -1) for k in c.members}
			c.group = gs.pop() if len(gs) == 1 else -1
	for comp in comps:
		for k in comp.members:
			pieces[k].comp = comp.id
			pieces[k].rc = comp.rc[k]
	res = PageResult(name=name, kind=kind, path=path, mm_per_px=float(mm_per_px), angle_deg=float(rot),
					 n_segmented=int(n_segmented if n_segmented is not None else len(raw)), pieces=pieces,
					 components=comps, rejected=list(rejected or []), double=list(double or []), notes=notes)
	res.edges = edges
	if art is not None:
		pe = 0 if kind == "blocos" else 1
		for comp in comps:
			if all(pieces[k].excluded for k in comp.members) or len(comp.members) < MIN_PLACE_PIECES:
				comp.reasons.append("sem peças utilizáveis")
				continue
			_locate_component(comp, pieces, profile, art, prior, pe, mm_per_px)
			_decide(comp, float(profile.calibration.get("margin_min", 1.5)))
			if comp.decision != "alta" and comp.placements:
				comp.questions.append(_question(name, comp, pieces))
	return res


def analyse_page(path: str, profile, art, prior, kind: str, *, seg: Optional[dict] = None, rgb: Optional[np.ndarray] = None,
				 name: Optional[str] = None) -> PageResult:
	"""Segment (unless ``seg`` is given), crop and analyse one legacy page (see the module docstring).

	``seg``: a ``segment_scan`` result or a light dict ``{'mm_per_px', 'pieces': [{contour,
	bbox, area_px, index, is_cluster, touches_strip, touches_frame}]}`` (cache). Returns a
	:class:`PageResult` or ``{'error': str}``.
	"""
	from PIL import Image
	if rgb is None:
		if not os.path.exists(path):
			return {"error": f"página não encontrada: {path}"}
		with Image.open(path) as im:
			rgb = np.asarray(im.convert("RGB"))
	if seg is None:
		from src.segmentation import segment_scan
		seg = segment_scan(Image.fromarray(rgb), dpi=profile.dpi, normalize_rotation=False)
		if "error" in seg:
			return {"error": f"segment_scan: {seg['error']}"}
	mmpp = float(seg.get("mm_per_px") or profile.mm_per_px())
	minA, fac = _min_piece_mm2(), _double_factor()
	raw, rejected, double = [], [], []
	kept = []
	for p in seg["pieces"]:
		a = float(p["area_px"]) * mmpp * mmpp
		if a < minA:
			rejected.append({"index": int(p["index"]), "area_mm2": round(a, 1), "touches_strip": bool(p.get("touches_strip")),
							 "reason": f"área < {minA:g} mm²"})
			continue
		kept.append((p, a))
	med = float(np.median([a for _, a in kept])) if kept else 0.0
	for p, a in kept:
		flags = {k: bool(p.get(k)) for k in ("touches_frame", "touches_strip", "is_cluster")}
		dup = flags["is_cluster"] or a > fac * med
		flags["objeto_duplo"] = dup
		contours = [np.asarray(p["contour"]).reshape(-1, 2)]
		if dup:
			parts = _split_double(rgb, contours[0], mmpp)
			double.append({"index": int(p["index"]), "area_mm2": round(a, 1), "split": len(parts),
						   "bbox": [int(v) for v in p["bbox"]]})
			if parts:
				contours = parts
		for k, cnt in enumerate(contours):
			rgba, _ = crop_rgba(rgb, cnt)
			x, y = cnt.min(0)
			w, h = cnt.max(0) - cnt.min(0)
			area = a if len(contours) == 1 else float(abs(_shoelace(cnt))) * mmpp * mmpp
			raw.append({"contour": cnt, "rgba": rgba, "index": int(p["index"]) if len(contours) == 1 else int(p["index"]) * 100 + k,
						"bbox": [int(x), int(y), int(w), int(h)], "area_mm2": area, "flags": dict(flags),
						"excluded": "objeto_duplo" if (dup and len(contours) == 1) else ""})
	return analyse_pieces(raw, profile, art, prior, kind, mmpp, name=name or os.path.splitext(os.path.basename(path))[0],
						  path=path, n_segmented=len(seg["pieces"]), rejected=rejected, double=double)


def _shoelace(c) -> float:
	x, y = c[:, 0].astype(float), c[:, 1].astype(float)
	return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


# ---------------------------------------------------------------- twins across pages
def twin_pairs(shapes: list, profile, *, d_max: Optional[float] = None) -> list:
	"""Silhouette twin pairs among ``shapes`` (list of Shape or None): ``[(a, b, d_mm, phi_ab_deg, margin)]``.

	Same class, :func:`src.shape.chord_pass` (profile tolerances), free distance <= ``d_max``
	(default ``calibration['silhueta_silhueta']['t95']``) and mutual nearest neighbours among
	the candidates that pass class + chords. ``phi_ab_deg`` rotates ``a`` onto ``b``
	(``free_dist(b, a)``); ``margin`` = second-nearest / nearest distance of ``a``.
	"""
	from src.twin import shape_distances
	cal = profile.calibration
	d_max = float(d_max if d_max is not None else cal["silhueta_silhueta"]["t95"])
	ch = cal.get("chord") or {}
	nmm, fmm = float(ch.get("normal_mm", 1.0)), float(ch.get("f_adj_mm", 2.0))
	ok = [i for i, s in enumerate(shapes) if s is not None and s.ok]
	by_cls = {}
	for i in ok:
		by_cls.setdefault(shapes[i].cls, []).append(i)
	nn = {}
	for cls, ids in by_cls.items():
		if len(ids) < 2:
			continue
		for i in ids:
			others = [j for j in ids if j != i]
			d, phi = shape_distances(shapes[i], [shapes[j] for j in others])
			o = np.argsort(d)
			best, second = None, None
			for k in o:
				if d[k] > 1.5 * d_max:
					break
				j = others[int(k)]
				if not chord_pass(shapes[i], shapes[j], normal_mm=nmm, f_adj_mm=fmm)[0]:
					continue
				if best is None:
					best = (j, float(d[k]), float(phi[k]))
				else:
					second = float(d[k])
					break
			if best is not None:
				nn[i] = (best[0], best[1], best[2], (second / best[1]) if (second and best[1] > 0) else float("inf"))
	pairs = []
	for i, (j, d, phi, m) in nn.items():
		if i < j and nn.get(j, (None,))[0] == i and d <= d_max:
			# shape_distances(query=i, [j]) gives phi aligning j onto i; a = i, b = j -> phi_ab rotates i onto j
			pairs.append((i, j, d, float(-phi), m))
	return pairs


def _units(results: list) -> list:
	"""Every located component of every page as ``(page index, component)``."""
	return [(pi, c) for pi, r in enumerate(results) for c in r.components if c.placements]


def _board_pose(piece: PagePiece, rot: int) -> float:
	return float(piece.theta_deg) + float(rot)


def _pair_status(profile, pa: PagePiece, ca, pb: PagePiece, cb, phi_ab: float) -> int:
	"""+1 satisfied, -1 violated, 0 unknown, for placements ``ca``/``cb`` = (cell, rot) of a and b.

	Satisfied = ``cb`` is the twin cell of ``ca`` and the board poses differ by the profile's
	twin rotation (``phi_ab`` rotates the crop of a onto the crop of b) within ``TWIN_ROT_TOL``.
	"""
	if ca is None or cb is None:
		return 0
	t = profile.twin(*ca[0])
	if t is None or tuple(t) != tuple(cb[0]):
		return -1
	d = wrap_deg(phi_ab - profile.twin_rotation_deg() - _board_pose(pa, ca[1]) + _board_pose(pb, cb[1]))
	return 1 if abs(float(d)) < TWIN_ROT_TOL else -1


def _implied(profile, comp: Component, pa: PagePiece, ka: int, pb: PagePiece, cb, phi_ab: float):
	"""Placement ``(cell0, rot)`` of ``comp`` that puts piece ``ka`` (``pa``) on the twin of b's placement ``cb``."""
	from src.locate import _rot_rc
	t = profile.twin(*cb[0])
	if t is None:
		return None
	want = float(phi_ab) - profile.twin_rotation_deg() + _board_pose(pb, cb[1]) - float(pa.theta_deg)
	rot = int(round(float(want) / 90.0)) % 4 * 90
	if abs(float(wrap_deg(want - rot))) >= TWIN_ROT_TOL:
		return None
	dr, dc = _rot_rc(comp.rc[ka][0], comp.rc[ka][1], rot, False)
	return (int(t[0] - dr), int(t[1] - dc)), rot


def duplicate_pages(results: list, pairs: list, *, same_de: float = SAME_PIECE_DE, frac: float = DUP_FRAC) -> dict:
	"""Pages that are re-scans of an earlier page: ``{later name: earlier name}``.

	``pairs`` from :func:`twin_pairs` over the flattened pieces (keys ``(page, piece)``). A
	shape match whose two crops have the same mean colour (dE <= ``same_de``) is the same
	physical piece scanned twice (a twin is elsewhere in the art); two pages sharing at least
	``frac`` of the smaller page this way are the same block scanned twice.
	"""
	cnt = {}
	for a, b, d, phi, m in pairs:
		if a[0] == b[0]:
			continue
		la, lb = results[a[0]].pieces[a[1]].mean_lab, results[b[0]].pieces[b[1]].mean_lab
		if la is None or lb is None:
			continue
		if float(np.linalg.norm(np.asarray(la, float) - np.asarray(lb, float))) <= same_de:
			key = (min(a[0], b[0]), max(a[0], b[0]))
			cnt[key] = cnt.get(key, 0) + 1
	out = {}
	for (x, y), n in sorted(cnt.items()):
		nx = sum(1 for p in results[x].pieces if not p.excluded)
		ny = sum(1 for p in results[y].pieces if not p.excluded)
		if n >= frac * min(nx, ny) and results[y].name not in out:
			out[results[y].name] = results[x].name
	return out


def solve_pages(results: list, profile, art=None, prior=None, *, pairs=None, max_iter: int = 30, log=None) -> dict:
	"""Cross-page consistency (step 5): image + silhouette twins + no two sections on one cell.

	Units = located components of every page (``montado`` and ``blocos``) except pages that
	are re-scans of an earlier page (:func:`duplicate_pages`: their components become
	``duplicada``). Candidates = the image top-``TOPK`` of each unit plus the placements
	implied by the twins of the top ``N_IMPLY`` candidates of every partner unit (scored with
	:func:`placement_score`). Energy of an assignment = sum of image scores - ``W_TWIN`` x
	(satisfied - violated twin pairs) + ``W_OVERLAP`` x (cells used by more than one unit) +
	``W_PRIOR`` x (members on cells the occupancy map ``prior`` contradicts: 0 for a
	``montado`` member, 1 for a ``blocos`` member).
	Optimised from the image best by moves of one unit **together with the units tied to it
	by >= ``MIN_LINK`` twin pairs** (their placements follow by the twin map), so a pair of
	sections cannot get stuck in a jointly shifted pose that the twins alone cannot see; then
	:func:`_decide` per unit with ``energy_gap`` = the cheapest such move to a distinct
	placement. A unit with a single candidate (an anchored section) never moves. Mutates
	the components (placements sorted with the chosen one first; ``adj`` = its share of the
	energy; ``twin_sat``, ``twin_viol``, ``overlap``). Returns ``{'pairs', 'duplicates',
	'iterations', 'moves'}``.
	"""
	allp = [(pi, k) for pi, r in enumerate(results) for k in range(len(r.pieces))]
	shapes = [results[pi].pieces[k].shape if not results[pi].pieces[k].excluded else None for pi, k in allp]
	if pairs is None:
		pairs = twin_pairs(shapes, profile)
	P0 = [(allp[a], allp[b], d, phi, m) for a, b, d, phi, m in pairs]
	dups = duplicate_pages(results, P0)
	dup_idx = {pi for pi, r in enumerate(results) if r.name in dups}
	for pi in dup_idx:
		for c in results[pi].components:
			c.decision = "duplicada"
			c.reasons = [f"página re-digitalizada: as mesmas peças de {dups[results[pi].name]}"]
			c.questions = []
	if dup_idx:
		shapes = [None if pi in dup_idx else s for (pi, _), s in zip(allp, shapes)]
		pairs = twin_pairs(shapes, profile)
	P = [(allp[a], allp[b], d, phi, m) for a, b, d, phi, m in pairs]
	margin_min = float(profile.calibration.get("margin_min", 1.5))
	units = [(pi, c) for pi, c in _units(results) if pi not in dup_idx]
	unit_of = {}
	for u, (pi, comp) in enumerate(units):
		for k in comp.members:
			unit_of[(pi, k)] = u
	inc = {u: [] for u in range(len(units))}     # u -> [(own piece key, other piece key, phi own -> other)]
	links = {}
	for a, b, d, phi, _ in P:
		ua, ub = unit_of.get(a), unit_of.get(b)
		if ua is None or ub is None:
			continue
		inc[ua].append((a, b, phi))
		if ub != ua:
			inc[ub].append((b, a, -phi))
			links[(ua, ub)] = links.get((ua, ub), 0) + 1
			links[(ub, ua)] = links.get((ub, ua), 0) + 1

	def piece(key):
		return results[key[0]].pieces[key[1]]

	caches = {}

	def make_placement(v, cell0, rot, origin):
		"""Existing or new (scored) placement of unit v; None if it breaks the grid or the F rules."""
		pi, comp = units[v]
		for p in comp.placements:
			if p["cell0"] == cell0 and p["rot"] == rot and not p["mirror"]:
				return p if np.isfinite(p["score"]) else None
		cells = component_cells(comp, cell0, rot)
		if not _valid_placement(comp, results[pi].pieces, profile, cells, rot, False):
			return None
		sc = float("inf")
		if art is not None:
			sc = placement_score(comp, results[pi].pieces, profile, art, cells, rot, False, prior=prior,
								 prior_expect=0 if results[pi].kind == "blocos" else 1, mm_per_px=results[pi].mm_per_px,
								 cache=caches.setdefault(v, {}))
		p = dict(cell0=cell0, rot=rot, mirror=False, score=float(sc), cells=cells, origin=origin, twin_sat=0, twin_viol=0,
				 adj=float(sc))
		comp.placements.append(p)
		return p if np.isfinite(sc) else None

	# (1) candidates implied by twins of the partners' image candidates
	for u, (pi, comp) in enumerate(units):
		if len(comp.placements) == 1 and comp.placements[0].get("origin") == "ancorada":
			continue
		for own, other, phi in inc[u]:
			uo = unit_of[other]
			if uo == u:
				continue
			for q in [p for p in units[uo][1].placements if not p["mirror"]][:N_IMPLY]:
				pl = _implied(profile, comp, piece(own), own[1], piece(other), (q["cells"][other[1]], q["rot"]), phi)
				if pl is not None:
					make_placement(u, pl[0], pl[1], "gémea")

	def cands(u):
		return [p for p in units[u][1].placements if not p["mirror"] and np.isfinite(p["score"])]

	pr = None if prior is None else np.asarray(prior)

	def prior_bad(u, p):
		"""Members on cells the occupancy map contradicts (montado on an empty cell, blocos on a full one)."""
		if pr is None:
			return 0
		bad = 0 if results[units[u][0]].kind == "blocos" else 1
		bad = 1 - bad
		return int(sum(1 for (l, c) in p["cells"].values() if pr[l - 1, c - 1] == bad))

	fixed = {u for u, (_, c) in enumerate(units) if len(c.placements) == 1 and c.placements[0].get("origin") == "ancorada"}
	choice = {u: (min(cands(u), key=lambda p: p["score"]) if cands(u) else None) for u in range(len(units))}
	occ = {}

	def occupy(p, s):
		for cell in p["cells"].values():
			occ[cell] = occ.get(cell, 0) + s

	for p in choice.values():
		if p is not None:
			occupy(p, 1)

	def cluster(u, p):
		"""Assignment {unit: placement} moving u to p and its strongly tied partners by the twin map."""
		conf = {u: p}
		todo = [u]
		while todo:
			x = todo.pop()
			for own, other, phi in inc[x]:
				v = unit_of[other]
				if v in conf or links.get((x, v), 0) < MIN_LINK or v in fixed:
					continue
				pl = _implied(profile, units[v][1], piece(other), other[1], piece(own),
							  (conf[x]["cells"][own[1]], conf[x]["rot"]), -phi)
				q = make_placement(v, pl[0], pl[1], "gémea") if pl is not None else None
				if q is None:
					return None
				conf[v] = q
				todo.append(v)
		return conf

	def pair_terms(S, get):
		"""- W_TWIN x (sat - viol) over pairs with an end in S (each pair once)."""
		e = 0.0
		for w in S:
			pw = get(w)
			if pw is None:
				continue
			for own, other, phi in inc[w]:
				v = unit_of[other]
				if v in S and (v < w or (v == w and own[1] > other[1])):
					continue
				pv = get(v)
				if pv is None:
					continue
				s = _pair_status(profile, piece(own), (pw["cells"][own[1]], pw["rot"]), piece(other),
								 (pv["cells"][other[1]], pv["rot"]), phi)
				e -= W_TWIN * s
		return e

	def delta(conf):
		"""Energy change of replacing the current choices of conf's units by conf."""
		S = set(conf)
		old = {w: choice[w] for w in S}
		e_img = sum(conf[w]["score"] - (old[w]["score"] if old[w] is not None else 0.0)
					+ W_PRIOR * (prior_bad(w, conf[w]) - (prior_bad(w, old[w]) if old[w] is not None else 0)) for w in S)
		e_pair = pair_terms(S, lambda w: conf.get(w, choice[w])) - pair_terms(S, lambda w: choice[w])
		touched = {}
		for w in S:
			if old[w] is not None:
				for cell in old[w]["cells"].values():
					touched[cell] = touched.get(cell, 0) - 1
			for cell in conf[w]["cells"].values():
				touched[cell] = touched.get(cell, 0) + 1
		f = lambda n: n if n > 1 else 0  # noqa: E731
		e_ov = sum(f(occ.get(cell, 0) + dn) - f(occ.get(cell, 0)) for cell, dn in touched.items())
		return e_img + e_pair + W_OVERLAP * e_ov

	def apply_conf(conf):
		for w, p in conf.items():
			if choice[w] is not None:
				occupy(choice[w], -1)
			choice[w] = p
			occupy(p, 1)

	order = sorted([u for u in range(len(units)) if choice[u] is not None and u not in fixed],
				   key=lambda u: -len(units[u][1].members))
	it, moves = 0, []
	for it in range(1, max_iter + 1):
		changed = False
		for u in order:
			best, best_d = None, -1e-9
			for p in cands(u):
				if p is choice[u]:
					continue
				conf = cluster(u, p)
				if conf is None:
					continue
				dE = delta(conf)
				if dE < best_d:
					best, best_d = conf, dE
			if best is not None:
				moves.append((results[units[u][0]].name, units[u][1].id, choice[u]["cell0"], best[u]["cell0"],
							  len(best), round(best_d, 2)))
				apply_conf(best)
				changed = True
		if not changed:
			break
	# (3) decide with the final neighbourhood, largest units first: a conflict (violated twin
	# pair, shared cell) counts against a unit only if the other unit is already 'alta' (or is
	# the unit itself); conflicts with undecided units are kept as information
	decided = set(fixed)
	dorder = sorted(range(len(units)), key=lambda u: (u not in fixed, -len(units[u][1].members)))
	for u in dorder:
		pi, comp = units[u]
		ch = choice.get(u)
		if ch is None:
			_decide(comp, margin_min)
			continue
		alta_cells = {}
		for w in decided:
			if w != u and choice.get(w) is not None:
				for cell in choice[w]["cells"].values():
					alta_cells[cell] = True
		for p in comp.placements:
			p["twin_sat"] = p["twin_viol"] = p["overlap"] = p["twin_viol_fixed"] = p["overlap_fixed"] = 0
			if p["mirror"] or not np.isfinite(p["score"]):
				p["adj"] = float("inf")
				continue
			sat = viol = vfix = 0
			for own, other, phi in inc[u]:
				v = unit_of[other]
				pv = p if v == u else choice.get(v)
				if pv is None or (v == u and own[1] > other[1]):
					continue
				s = _pair_status(profile, piece(own), (p["cells"][own[1]], p["rot"]), piece(other),
								 (pv["cells"][other[1]], pv["rot"]), phi)
				sat += s > 0
				viol += s < 0
				vfix += s < 0 and (v == u or v in decided)
			mine = set(ch["cells"].values())
			ov = sum(1 for cell in p["cells"].values() if occ.get(cell, 0) - (cell in mine) > 0)
			pb = prior_bad(u, p)
			p.update(twin_sat=sat, twin_viol=viol, overlap=ov, prior_bad=pb, twin_viol_fixed=vfix,
					 overlap_fixed=sum(1 for cell in p["cells"].values() if cell in alta_cells))
			p["adj"] = float(p["score"]) - W_TWIN * (sat - viol) + W_OVERLAP * ov + W_PRIOR * pb
		# cheapest move (with the tied partners) to a distinct placement
		gap = float("inf")
		if u not in fixed:
			for p in cands(u):
				if p is ch or _placement_dist(ch, p) < DISTINCT_CELLS:
					continue
				conf = cluster(u, p)
				if conf is not None:
					gap = min(gap, delta(conf))
		comp.placements.sort(key=lambda p: (p is not ch, p["adj"], p["mirror"]))
		_decide(comp, margin_min, gap=gap)
		if comp.decision == "alta":
			decided.add(u)
			if log:
				b = comp.best
				log(f"{results[pi].name} c{comp.id}: alta {b['cell0']} rot {b['rot']} (gémeas {b['twin_sat']}/{b['twin_viol']}, "
					f"ganho {gap:.1f})")
	for u, (pi, comp) in enumerate(units):
		if comp.decision != "alta" and comp.placements:
			comp.questions = [_question(results[pi].name, comp, results[pi].pieces)]
	return {"pairs": P, "duplicates": dups, "iterations": it, "moves": moves}


# ---------------------------------------------------------------- ground truth (measurement only)
def match_gt(gt_items: list, page_items: list, profile, *, same_de: float = SAME_PIECE_DE) -> list:
	"""Shape matches between GT pieces and page pieces (measurement only, never a decision).

	``gt_items`` / ``page_items``: dicts ``{'key', 'shape', 'mean_lab', 'cell' (GT only)}``.
	For every GT piece, the page pieces of the same class that pass the chord filter with
	free distance <= t95 are split by colour (mean-Lab dE <= ``same_de``: the same physical
	piece; above: its twin, whose cell is ``profile.twin(cell)``) and the nearest of each kind
	is kept if the match is mutual. Returns ``[{'gt', 'page', 'kind': 'mesma'|'gemea', 'd_mm',
	'dE', 'cell'}]``.
	"""
	from src.twin import shape_distances
	cal = profile.calibration
	t95 = float(cal["silhueta_silhueta"]["t95"])
	ch = cal.get("chord") or {}
	nmm, fmm = float(ch.get("normal_mm", 1.0)), float(ch.get("f_adj_mm", 2.0))
	ok_pages = [q for q in page_items if q["shape"] is not None and q["shape"].ok]
	best = {}   # (gt key, kind) -> (page key, d, dE)
	back = {}   # (page key, kind) -> (gt key, d)
	for g in gt_items:
		if g["shape"] is None or not g["shape"].ok:
			continue
		cand = [q for q in ok_pages if q["shape"].cls == g["shape"].cls]
		if not cand:
			continue
		d, _ = shape_distances(g["shape"], [q["shape"] for q in cand])
		for k in np.argsort(d):
			if d[k] > t95:
				break
			q = cand[int(k)]
			if not chord_pass(g["shape"], q["shape"], normal_mm=nmm, f_adj_mm=fmm)[0]:
				continue
			de = float(np.linalg.norm(np.asarray(g["mean_lab"], float) - np.asarray(q["mean_lab"], float)))
			kind = "mesma" if de <= same_de else "gemea"
			if (g["key"], kind) not in best:
				best[(g["key"], kind)] = (q["key"], float(d[k]), de)
			bk = (q["key"], kind)
			if bk not in back or back[bk][1] > float(d[k]):
				back[bk] = (g["key"], float(d[k]))
	gmap = {g["key"]: g for g in gt_items}
	out = []
	for (gk, kind), (qk, d, de) in best.items():
		if back.get((qk, kind), (None,))[0] != gk:
			continue
		cell = tuple(gmap[gk]["cell"])
		if kind == "gemea":
			t = profile.twin(*cell)
			if t is None:
				continue
			cell = tuple(t)
		out.append({"gt": gk, "page": qk, "kind": kind, "d_mm": d, "dE": de, "cell": cell})
	return out


# ---------------------------------------------------------------- I/O helpers
def load_prior(path: str, profile, corrections: Optional[dict] = None) -> np.ndarray:
	"""Occupancy map (rows x cols in {1, 0, -1}) from an M14 json (``celulas[l-1][c-1]``) with ``{(l, c): v}`` fixes."""
	import json
	with open(path, encoding="utf-8") as f:
		d = json.load(f)
	m = np.array(d["celulas"], int)
	if m.shape != (profile.rows, profile.cols):
		raise ValueError(f"mapa {m.shape} não é {profile.rows}x{profile.cols}")
	for (l, c), v in (corrections or {}).items():
		m[l - 1, c - 1] = int(v)
	return m


# ---------------------------------------------------------------- project integration
def _project_art(project, art):
	if art is not None:
		return art
	from src.locate import CellArt
	repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
	try:
		return CellArt.load(project.profile, repo)
	except (FileNotFoundError, ValueError):
		return None


def _project_prior(project):
	ph = project.last_photo()
	return None if ph is None else np.array(ph.map, int)


def ingest_page(project, scan_path: str, kind: str, page, *, auto_anchor: bool = True, art=None, prior=None,
				segment=None) -> dict:
	"""Add a legacy page to ``project`` (called by ``python -m src.ingest --montado/--blocos pNN``).

	Segments once, reuses :func:`src.ingest.ingest_scan` for the scan, pieces, crops and
	overlay, then runs :func:`analyse_page` on the same segmentation and registers one
	:class:`src.state.Section` per component (``kind``; ``cells_local`` keyed by piece id;
	``candidates`` = top-3 placements; ``notes`` = page, decision, margin, reasons). Page
	pieces that are the same physical piece as a project piece with a known cell
	(``colocada`` / ``posicao_conhecida``) are marked ``same_as`` (the GT entry prevails). With
	``auto_anchor``, ``montado`` components decided ``alta`` are anchored (fonte
	``legado_scan``); ``blocos`` are never anchored. Cross-page twins need every page:
	call :func:`solve_project_sections` after the last page. Returns ``{scan_id, sections,
	anchored, same_as, double, n_pieces, questions}`` or ``{'error': str}``.

	Caveat (LEGADO.md): a component anchored here was decided on its own page (image + F
	rules); with every page in, the cross-page solve may disagree with it (twin pairs
	violated) and it never moves anchored sections: check the questions before anchoring the
	ambiguous ones by hand, and :meth:`src.state.Project.unanchor_section` if needed.
	"""
	from PIL import Image
	from src.ingest import ingest_scan
	from src.state import StateError
	if kind not in ("montado", "blocos"):
		return {"error": f"tipo de página inválido {kind!r} (montado | blocos)"}
	if not os.path.exists(scan_path):
		return {"error": f"scan não encontrado: {scan_path}"}
	profile = project.profile
	with Image.open(scan_path) as im:
		photo = im.convert("RGB")
	if segment is None:
		from src.segmentation import segment_scan as segment
	seg = segment(photo, dpi=profile.dpi, normalize_rotation=False)
	if "error" in seg:
		return {"error": f"segment_scan: {seg['error']}"}
	r = ingest_scan(project, scan_path, None, dpi=profile.dpi, kind=kind, segment=lambda *a, **k: seg)
	if "error" in r:
		return r
	art = _project_art(project, art)
	if prior is None:
		prior = _project_prior(project)
	name = f"{kind}_{page}"
	res = analyse_page(scan_path, profile, art, prior, kind, seg=seg, rgb=np.asarray(photo), name=name)
	if isinstance(res, dict):
		return res
	by_index = {project.piece(pid).index_in_scan: pid for pid in r["pieces"]}
	pid_of = {k: by_index.get(p.index) for k, p in enumerate(res.pieces)}
	same = _mark_same_as(project, res, pid_of, set(r["pieces"]))
	sections, anchored = [], []
	for comp in res.components:
		cl = {pid_of[k]: comp.rc[k] for k in comp.members if pid_of.get(k) and not res.pieces[k].excluded}
		if not cl:
			continue
		cands = [{"cell0": list(p["cell0"]), "rot": p["rot"], "mirror": p["mirror"], "score": round(p["score"], 3),
				  "margin": None if not np.isfinite(comp.margin) else round(comp.margin, 3)}
				 for p in comp.placements if not p["mirror"]][:3]
		notes = (f"{name} comp {comp.id}: {comp.decision}; margem {comp.margin:.2f}; " + "; ".join(comp.reasons)
				 + ("; " + " ".join(comp.questions) if comp.questions else ""))
		try:
			gid = project.register_section(r["scan_id"], kind, cl, candidates=cands, notes=notes)
		except StateError as e:
			sections.append({"component": comp.id, "error": str(e)})
			continue
		sections.append({"component": comp.id, "section": gid, "decision": comp.decision, "n": len(cl)})
		if kind == "montado" and auto_anchor and comp.decision == "alta" and comp.placements:
			b = comp.placements[0]
			ev = project.anchor_section(gid, b["cell0"][0], b["cell0"][1], rot=b["rot"], fonte="legado_scan",
										confianca="alta", margin=None if not np.isfinite(comp.margin) else round(comp.margin, 3))
			anchored.append({"section": gid, "conflicts": ev.get("conflicts", [])})
	return {"scan_id": r["scan_id"], "sections": sections, "anchored": anchored, "same_as": same,
			"double": r["double"], "n_pieces": len(r["pieces"]),
			"questions": [q for c in res.components for q in c.questions]}


def _mark_same_as(project, res: PageResult, pid_of: dict, new_ids: set) -> list:
	known = [q for q in project.pieces.values() if q.id not in new_ids and q.celula is not None
			 and q.estado in ("colocada", "posicao_conhecida")]
	if not known:
		return []
	gt = []
	for q in known:
		sh = project.shape(q.id)
		if sh is not None:
			gt.append({"key": q.id, "shape": sh, "mean_lab": q.mean_lab, "cell": q.celula})
	pages = [{"key": k, "shape": p.shape, "mean_lab": p.mean_lab} for k, p in enumerate(res.pieces)
			 if p.shape is not None and p.mean_lab is not None and not p.excluded]
	out = []
	for m in match_gt(gt, pages, project.profile):
		if m["kind"] != "mesma" or not pid_of.get(m["page"]):
			continue
		project.mark_same_as(pid_of[m["page"]], m["gt"])
		out.append({"piece": pid_of[m["page"]], "same_as": m["gt"], "d_mm": round(m["d_mm"], 3)})
	return out


def solve_project_sections(project, *, art=None, prior=None, auto_anchor: bool = True) -> dict:
	"""Re-evaluate the unanchored ``montado`` sections of ``project`` with cross-section twins.

	Rebuilds a :class:`PageResult` per section from the project (shapes, crops, local cells),
	locates it, treats anchored sections as fixed, runs :func:`solve_pages`, and anchors the
	sections that became ``alta`` (fonte ``legado_scan``). Sections whose pieces are all
	``same_as`` (a page scanned twice) are skipped. Returns ``{'anchored': [...],
	'ambiguous': [...], 'pairs': n}``.
	"""
	profile = project.profile
	art = _project_art(project, art)
	if prior is None:
		prior = _project_prior(project)
	results, sec_of = [], []
	for gid, s in sorted(project.sections.items()):
		if s.kind != "montado":
			continue
		if s.cells_local and all(project.piece(pid).same_as for pid in s.cells_local):
			continue  # every piece is a re-scan (``same_as``) of a project piece: nothing new to place
		pids = sorted(s.cells_local, key=lambda k: s.cells_local[k])
		pieces = []
		for k, pid in enumerate(pids):
			q = project.piece(pid)
			sh = project.shape(pid)
			rgba = project.crop_rgba(pid)
			pp = PagePiece(n=int(q.n_no_lote or k + 1), index=int(q.index_in_scan), contour=np.zeros((0, 2)), bbox=q.bbox or [0, 0, 0, 0],
						   area_mm2=float(q.area_mm2 or 0), shape=sh, mean_lab=q.mean_lab, rgba=rgba)
			pieces.append(pp)
		rot = page_rotation([p.shape for p in pieces if p.shape is not None])
		for p in pieces:
			if p.shape is None:
				p.excluded = "sem forma"
				continue
			p.theta_deg = float(rot + wrap_deg(body_beta_deg(p.shape) - rot))
			p.dirs, p.dirs_ok, p.flat_dirs = label_sides(p.shape, rot)
		comp = Component(id=0, members=list(range(len(pids))), rc={k: tuple(s.cells_local[pid]) for k, pid in enumerate(pids)})
		for k in comp.members:
			pieces[k].comp = 0
			pieces[k].rc = comp.rc[k]
		pr = PageResult(name=gid, kind="montado", path=None, mm_per_px=profile.mm_per_px(), angle_deg=rot, n_segmented=len(pids),
						pieces=pieces, components=[comp])
		if s.anchor.get("anchored"):
			a = s.anchor
			cells = component_cells(comp, (a["l0"], a["c0"]), a["rot"], a["mirror"])
			comp.placements = [dict(cell0=(a["l0"], a["c0"]), rot=int(a["rot"]), mirror=bool(a["mirror"]), score=0.0, cells=cells,
									origin="ancorada", twin_sat=0, twin_viol=0, adj=0.0)]
			comp.decision = "alta"
		elif art is not None:
			_locate_component(comp, pieces, profile, art, prior, 1, profile.mm_per_px())
			_decide(comp, float(profile.calibration.get("margin_min", 1.5)))
		results.append(pr)
		sec_of.append(gid)
	if not results:
		return {"anchored": [], "ambiguous": [], "pairs": 0}
	was = {gid for gid, s in project.sections.items() if s.anchor.get("anchored")}
	out = solve_pages(results, profile, art, prior)
	anchored, ambiguous = [], []
	for gid, r in zip(sec_of, results):
		comp = r.components[0]
		if gid in was:
			continue
		if comp.decision == "alta" and comp.placements and auto_anchor:
			b = comp.placements[0]
			project.anchor_section(gid, b["cell0"][0], b["cell0"][1], rot=b["rot"], fonte="legado_scan", confianca="alta",
								   margin=None if not np.isfinite(comp.margin) else round(comp.margin, 3))
			anchored.append(gid)
		else:
			ambiguous.append({"section": gid, "questions": comp.questions, "reasons": comp.reasons})
	return {"anchored": anchored, "ambiguous": ambiguous, "pairs": len(out["pairs"])}
