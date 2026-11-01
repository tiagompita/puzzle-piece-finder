"""Persistent project state (M12 minimum): piece index, board map, append-only log.

A project lives in ``projects/<id>/`` (docs/estado-e-plano.md §10, docs/plano-m10-m12.md §3)::

	project.json          {id, schema_version, created, puzzle, next_ids}
	puzzle.json           copy of the puzzle profile (src/profile.py)
	log.jsonl             append-only event log; THE source of truth
	board.json            view of the board (== replay(log))
	scans/S0001.json      scan metadata + its pieces (view)
	pieces/S0001.npz      per-scan arrays: contour px, Shape.to_arrays (key prefix ``P0001__``)
	crops/P0001.png       RGBA crop of each piece, in the scan frame (not rotated)
	sections/G0001.json   sections (view); photos/F0001.json photos (map 1/0/-1)
	pairs.json            twin pairs between loose pieces (view)
	fetch.md / fetch.json "go fetch" list written by src.query

Every state change is an event ``{t, action, ...}`` appended to the log and applied to
the in-memory model by :func:`apply`, the same function :func:`replay` uses, so
``board == replay(log)`` holds by construction (checked by
:meth:`Project.check_invariants`). Events carry everything replay needs (piece static
metadata, previous cell states for undo), so the JSON views are rebuildable caches.

Cell convention: ``(l, c)``, 1-based, row ``l`` from the top. The die symmetry is only
ever obtained from :meth:`src.profile.PuzzleProfile.twin`. Ids (``S``, ``P``, ``T``,
``G``, ``F`` + 4 digits) are allocated once and never reused.

Model methods of :class:`Project` raise :class:`StateError` on invalid operations
(nothing is logged in that case); the CLIs turn it into a message and exit code 1.
Only :meth:`Project.create`, :meth:`Project.open`, :meth:`Project.save`, the log
append and the npz/crop helpers do I/O.
"""

from __future__ import annotations

import copy
import datetime as _dt
import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass, field, fields
from typing import Optional

import numpy as np

from src.profile import PuzzleProfile

__all__ = [
	"SCHEMA_VERSION", "PIECE_STATES", "PAIR_STATES", "SECTION_KINDS", "CELL_STATES", "CELL_SOURCES", "ACTIONS",
	"StateError", "Piece", "Pair", "Section", "Photo", "Board", "Model", "apply", "replay", "read_log",
	"Project", "file_sha256", "section_cell",
]

SCHEMA_VERSION = 1
REPLACE_RETRIES = 20          # _write_json: attempts of the atomic rename (transient Windows locks by readers/indexers)
REPLACE_WAIT_S = 0.1
PIECE_STATES = ("solta", "emparelhada", "posicao_conhecida", "colocada", "em_seccao", "descartada")
PAIR_STATES = ("proposto", "confirmado", "rejeitado")
SECTION_KINDS = ("montado", "blocos", "seccao")
CELL_STATES = ("vazia", "ocupada_legado", "colocada")
CELL_SOURCES = ("log", "foto", "legado_scan")
ACTIONS = (
	"scan_added", "piece_added", "placed", "unplaced", "twin_confirmed", "twin_rejected", "hole_confirmed",
	"hole_rejected", "pair_registered", "pair_confirmed", "pair_rejected", "fetch_listed", "section_registered",
	"section_anchored", "section_unanchored", "piece_discarded", "photo_registered", "cell_occupied_by_photo",
	"cell_cleared_by_photo", "position_known", "position_placeable", "same_as", "lote_changed",
)
ID_PREFIXES = ("S", "P", "T", "G", "F")
LOOSE_STATES = ("solta", "emparelhada")
_PLACEABLE_FROM = ("solta", "emparelhada", "posicao_conhecida")


class StateError(ValueError):
	"""Invalid operation on the project state (nothing was logged)."""


def _now() -> str:
	return _dt.datetime.now().isoformat(timespec="seconds")


def _cell(v) -> Optional[tuple]:
	return None if v is None else (int(v[0]), int(v[1]))


def _cell_list(v) -> Optional[list]:
	return None if v is None else [int(v[0]), int(v[1])]


def file_sha256(path: str) -> str:
	"""SHA-256 hex digest of a file."""
	h = hashlib.sha256()
	with open(path, "rb") as f:
		for chunk in iter(lambda: f.read(1 << 20), b""):
			h.update(chunk)
	return h.hexdigest()


# ---------------------------------------------------------------- entities
@dataclass
class Piece:
	"""One scanned piece. ``celula`` = (l, c) when ``colocada`` or ``posicao_conhecida``.

	``theta_deg``: orientation on the board when known. ``flags``: ``touches_frame``,
	``touches_strip``, ``is_cluster``, ``objeto_duplo``. ``chords_mm``: the 4 side chords
	(empty if the shape has no 4 corners). ``bbox``: crop box in scan px (x, y, w, h).
	``shape``: :class:`src.shape.Shape`, loaded on demand (:meth:`Project.shape`), never
	serialised here.
	"""

	id: str
	scan_id: str
	index_in_scan: int
	lote: Optional[int] = None
	n_no_lote: Optional[int] = None
	estado: str = "solta"
	celula: Optional[tuple] = None
	theta_deg: Optional[float] = None
	seccao_id: Optional[str] = None
	same_as: Optional[str] = None
	flags: dict = field(default_factory=dict)
	area_mm2: Optional[float] = None
	cls: str = ""
	n_flat: int = 0
	chords_mm: list = field(default_factory=list)
	shape_ok: bool = False
	bbox: Optional[list] = None
	crop_path: Optional[str] = None
	mean_lab: Optional[list] = None
	shape: object = field(default=None, repr=False, compare=False)

	def to_dict(self) -> dict:
		d = {f.name: copy.deepcopy(getattr(self, f.name)) for f in fields(self) if f.name != "shape"}
		d["celula"] = _cell_list(self.celula)
		return d

	@classmethod
	def from_dict(cls, d: dict) -> "Piece":
		d = {k: copy.deepcopy(v) for k, v in d.items() if k != "shape"}
		d["celula"] = _cell(d.get("celula"))
		return cls(**d)

	@property
	def dynamic(self) -> dict:
		"""The part of the piece the log changes (compared by the invariants)."""
		return {"estado": self.estado, "celula": self.celula, "theta_deg": self.theta_deg,
				"seccao_id": self.seccao_id, "same_as": self.same_as, "lote": self.lote, "n_no_lote": self.n_no_lote}


@dataclass
class Pair:
	"""Twin pair proposed between two loose pieces (``cells`` = joint top-3 of pair_locate)."""

	id: str
	a: str
	b: str
	d1_mm: Optional[float] = None
	margin: Optional[float] = None
	image: Optional[dict] = None
	cells: list = field(default_factory=list)
	estado: str = "proposto"

	def to_dict(self) -> dict:
		return {f.name: copy.deepcopy(getattr(self, f.name)) for f in fields(self)}

	@classmethod
	def from_dict(cls, d: dict) -> "Pair":
		return cls(**copy.deepcopy(d))


def _default_anchor() -> dict:
	return {"anchored": False, "l0": None, "c0": None, "rot": 0, "mirror": False, "fonte": None,
			"confianca": None, "margin": None}


@dataclass
class Section:
	"""Assembled group with local cell coordinates ``cells_local`` {piece_id: (r, c)}.

	``anchor``: {anchored, l0, c0, rot, mirror, fonte, confianca, margin}; see
	:func:`section_cell` for the local→board mapping. ``candidates``: top-3 of
	``locate_group`` (``cell0``, ``rot``, ``mirror``, ``score``, ``margin``).
	"""

	id: str
	scan_id: Optional[str]
	kind: str = "seccao"
	cells_local: dict = field(default_factory=dict)
	anchor: dict = field(default_factory=_default_anchor)
	candidates: list = field(default_factory=list)
	notes: str = ""

	def to_dict(self) -> dict:
		d = {f.name: copy.deepcopy(getattr(self, f.name)) for f in fields(self)}
		d["cells_local"] = {k: _cell_list(v) for k, v in self.cells_local.items()}
		return d

	@classmethod
	def from_dict(cls, d: dict) -> "Section":
		d = copy.deepcopy(d)
		d["cells_local"] = {k: _cell(v) for k, v in d.get("cells_local", {}).items()}
		a = _default_anchor()
		a.update(d.get("anchor") or {})
		d["anchor"] = a
		return cls(**d)


@dataclass
class Photo:
	"""Board photo (M14): ``map`` rows x cols of 1 (full) / 0 (empty) / -1 (uncertain)."""

	id: Optional[str]
	file: Optional[str]
	sha256: Optional[str] = None
	date: Optional[str] = None
	map: list = field(default_factory=list)
	homography: Optional[list] = None
	residual: Optional[dict] = None

	def to_dict(self) -> dict:
		return {f.name: copy.deepcopy(getattr(self, f.name)) for f in fields(self)}

	@classmethod
	def from_dict(cls, d: dict) -> "Photo":
		return cls(**copy.deepcopy(d))

	def value(self, l: int, c: int) -> int:
		return int(self.map[l - 1][c - 1])


def _empty_cell() -> dict:
	return {"estado": "vazia", "peca_id": None, "fonte": None, "foto_id": None}


class Board:
	"""Board map: ``rows`` x ``cols`` cells ``{estado, peca_id, fonte, foto_id}``.

	Index with ``board[(l, c)]`` (1-based); the returned dict is the live cell.
	"""

	def __init__(self, rows: int, cols: int, cells: Optional[list] = None):
		self.rows, self.cols = int(rows), int(cols)
		self.cells = cells if cells is not None else [[_empty_cell() for _ in range(self.cols)] for _ in range(self.rows)]

	@classmethod
	def empty(cls, profile: PuzzleProfile) -> "Board":
		return cls(profile.rows, profile.cols)

	def __getitem__(self, lc) -> dict:
		l, c = lc
		if not (1 <= l <= self.rows and 1 <= c <= self.cols):
			raise StateError(f"célula ({l}, {c}) fora da grelha {self.rows}x{self.cols}")
		return self.cells[l - 1][c - 1]

	def set(self, lc, value: dict) -> None:
		cell = self[lc]
		cell.clear()
		cell.update(_empty_cell())
		cell.update(copy.deepcopy(value))

	def occupied(self, lc) -> bool:
		return self[lc]["estado"] != "vazia"

	def iter_cells(self):
		"""Yield ``((l, c), cell)`` row by row."""
		for i in range(self.rows):
			for j in range(self.cols):
				yield (i + 1, j + 1), self.cells[i][j]

	def neighbours(self, lc) -> list:
		l, c = lc
		return [(a, b) for a, b in ((l - 1, c), (l + 1, c), (l, c - 1), (l, c + 1))
				if 1 <= a <= self.rows and 1 <= b <= self.cols]

	def n_occupied_neighbours(self, lc) -> int:
		return sum(self.occupied(n) for n in self.neighbours(lc))

	def to_dict(self) -> dict:
		return {"rows": self.rows, "cols": self.cols, "cells": copy.deepcopy(self.cells)}

	@classmethod
	def from_dict(cls, d: dict) -> "Board":
		return cls(d["rows"], d["cols"], copy.deepcopy(d["cells"]))

	def __eq__(self, other) -> bool:
		return isinstance(other, Board) and self.to_dict() == other.to_dict()

	def counts(self) -> dict:
		out = {}
		for _, cell in self.iter_cells():
			k = cell["estado"] if cell["estado"] == "vazia" else f"{cell['estado']}/{cell['fonte']}"
			out[k] = out.get(k, 0) + 1
		return out


def section_cell(anchor: dict, rc) -> tuple:
	"""Board cell of local cell ``rc = (r, c)`` under ``anchor``.

	Local (0, 0) maps to ``(l0, c0)``. ``mirror`` negates the local column first; then the
	offset is rotated by ``rot`` degrees clockwise on the board (r down, c right):
	90° maps (dr, dc) to (dc, -dr).
	"""
	dr, dc = int(rc[0]), int(rc[1])
	if anchor.get("mirror"):
		dc = -dc
	k = (int(round(float(anchor.get("rot") or 0) / 90.0)) % 4)
	for _ in range(k):
		dr, dc = dc, -dr
	return (int(anchor["l0"]) + dr, int(anchor["c0"]) + dc)


# ---------------------------------------------------------------- model + event application
class Model:
	"""In-memory state rebuilt from the log (board, pieces, pairs, sections, photos, scans)."""

	def __init__(self, profile: PuzzleProfile):
		self.profile = profile
		self.board = Board.empty(profile)
		self.scans: dict = {}
		self.pieces: dict = {}
		self.pairs: dict = {}
		self.sections: dict = {}
		self.photos: dict = {}            # id -> meta {id, file, sha256, date}
		self.rejections: set = set()       # (piece_id, (l, c) | None, origin)
		self.max_ids = {p: 0 for p in ID_PREFIXES}

	def _seen(self, ident: str) -> None:
		if ident and ident[0] in self.max_ids and ident[1:].isdigit():
			self.max_ids[ident[0]] = max(self.max_ids[ident[0]], int(ident[1:]))

	def pieces_state(self) -> dict:
		return {pid: p.dynamic for pid, p in self.pieces.items()}


def _piece(m: Model, pid: str) -> Piece:
	if pid not in m.pieces:
		raise StateError(f"peça desconhecida {pid}")
	return m.pieces[pid]


def _active_pair(m: Model, pid: str, exclude: Optional[str] = None) -> bool:
	return any(p.estado != "rejeitado" and pid in (p.a, p.b) and p.id != exclude for p in m.pairs.values())


def apply(m: Model, ev: dict) -> None:
	"""Apply one log event to the model (used both live and by :func:`replay`)."""
	a = ev["action"]
	if a == "scan_added":
		m.scans[ev["scan"]["id"]] = copy.deepcopy(ev["scan"])
		m._seen(ev["scan"]["id"])
	elif a == "piece_added":
		p = Piece.from_dict(ev["piece"])
		if p.id in m.pieces:
			raise StateError(f"id de peça repetido {p.id}")
		m.pieces[p.id] = p
		m._seen(p.id)
	elif a == "placed":
		p = _piece(m, ev["piece"])
		cell = _cell(ev["cell"])
		p.estado, p.celula = "colocada", cell
		if ev.get("theta_deg") is not None:
			p.theta_deg = float(ev["theta_deg"])
		m.board.set(cell, {"estado": "colocada", "peca_id": p.id, "fonte": ev.get("fonte", "log"), "foto_id": None})
	elif a == "unplaced":
		p = _piece(m, ev["piece"])
		m.board.set(_cell(ev["cell"]), ev["restore"])
		p.estado, p.celula = ev.get("to", "solta"), None
	elif a == "position_known":
		p = _piece(m, ev["piece"])
		p.estado, p.celula = "posicao_conhecida", _cell(ev["cell"])
		if ev.get("theta_deg") is not None:
			p.theta_deg = float(ev["theta_deg"])
	elif a == "pair_registered":
		pr = Pair.from_dict(ev["pair"])
		m.pairs[pr.id] = pr
		m._seen(pr.id)
		for pid in (pr.a, pr.b):
			if _piece(m, pid).estado == "solta":
				m.pieces[pid].estado = "emparelhada"
	elif a == "pair_confirmed":
		m.pairs[ev["pair"]].estado = "confirmado"
	elif a == "pair_rejected":
		pr = m.pairs[ev["pair"]]
		pr.estado = "rejeitado"
		for pid in (pr.a, pr.b):
			if m.pieces[pid].estado == "emparelhada" and not _active_pair(m, pid):
				m.pieces[pid].estado = "solta"
	elif a in ("twin_rejected", "hole_rejected"):
		m.rejections.add((ev["piece"], _cell(ev.get("cell")), ev.get("origin")))
	elif a == "section_registered":
		s = Section.from_dict(ev["section"])
		m.sections[s.id] = s
		m._seen(s.id)
		for pid in s.cells_local:
			p = _piece(m, pid)
			p.estado, p.seccao_id = "em_seccao", s.id
	elif a == "section_anchored":
		s = m.sections[ev["section"]]
		s.anchor = dict(_default_anchor(), **ev["anchor"])
		for pl in ev["placements"]:
			p = m.pieces[pl["piece"]]
			p.estado, p.celula = "colocada", _cell(pl["cell"])
			m.board.set(p.celula, {"estado": "colocada", "peca_id": p.id, "fonte": "legado_scan", "foto_id": None})
	elif a == "section_unanchored":
		s = m.sections[ev["section"]]
		s.anchor = _default_anchor()
		for pl in ev["placements"]:
			p = m.pieces[pl["piece"]]
			m.board.set(_cell(pl["cell"]), pl["restore"])
			p.estado, p.celula = "em_seccao", None
	elif a == "piece_discarded":
		p = _piece(m, ev["piece"])
		p.estado, p.celula = "descartada", None
	elif a == "photo_registered":
		m.photos[ev["photo"]["id"]] = copy.deepcopy(ev["photo"])
		m._seen(ev["photo"]["id"])
	elif a == "cell_occupied_by_photo":
		m.board.set(_cell(ev["cell"]), {"estado": "ocupada_legado", "peca_id": None, "fonte": "foto",
										"foto_id": ev["photo"]})
	elif a == "cell_cleared_by_photo":
		m.board.set(_cell(ev["cell"]), {"estado": "vazia", "peca_id": None, "fonte": "foto", "foto_id": ev["photo"]})
	elif a == "same_as":
		_piece(m, ev["piece"]).same_as = ev["other"]
	elif a == "lote_changed":
		lote = ev.get("lote")
		sids = set(ev["scan_ids"])
		for sid in sids:
			if sid not in m.scans:
				raise StateError(f"scan desconhecido {sid}")
			m.scans[sid]["lote"] = lote
		nums = ev.get("pieces") or {}
		for p in m.pieces.values():
			if p.scan_id in sids:
				p.lote = lote
				if p.id in nums:
					p.n_no_lote = None if nums[p.id] is None else int(nums[p.id])
	elif a in ("twin_confirmed", "hole_confirmed", "fetch_listed", "position_placeable"):
		pass  # informative events (metrics / notifications); no state change
	else:
		raise StateError(f"ação desconhecida no log: {a!r}")


def read_log(log_path: str) -> list:
	"""All events of a ``log.jsonl`` (empty list if the file does not exist)."""
	if not os.path.exists(log_path):
		return []
	with open(log_path, encoding="utf-8") as f:
		return [json.loads(line) for line in f if line.strip()]


def _replay_model(events: list, profile: PuzzleProfile) -> Model:
	m = Model(profile)
	for ev in events:
		apply(m, ev)
	return m


def replay(log_path: str, profile: PuzzleProfile):
	"""Rebuild ``(Board, pieces_state)`` from a log; ``pieces_state`` = {id: dynamic dict}."""
	m = _replay_model(read_log(log_path), profile)
	return m.board, m.pieces_state()


# ---------------------------------------------------------------- project
class Project:
	"""A project folder: profile + log-backed model + JSON views (see the module docstring)."""

	def __init__(self, path: str, meta: dict, profile: PuzzleProfile, model: Model):
		self.path = os.path.abspath(path)
		self.meta = meta
		self.profile = profile
		self.model = model
		self.photo_maps: dict = {}        # photo id -> Photo (with map), loaded from photos/
		self._pending_arrays: dict = {}   # scan_id -> {key: array}
		self._shape_cache: dict = {}

	# ------------------------------------------------------------ files
	@property
	def log_path(self) -> str:
		return os.path.join(self.path, "log.jsonl")

	def p(self, *parts) -> str:
		return os.path.join(self.path, *parts)

	@classmethod
	def create(cls, path: str, profile_path: str, project_id: Optional[str] = None) -> "Project":
		"""New project in ``path`` (must not hold a ``project.json``); copies the profile."""
		path = os.path.abspath(path)
		if os.path.exists(os.path.join(path, "project.json")):
			raise StateError(f"já existe um projeto em {path}")
		profile = PuzzleProfile.load(profile_path)
		os.makedirs(path, exist_ok=True)
		dst = os.path.join(path, "puzzle.json")
		if not (os.path.exists(dst) and os.path.samefile(profile_path, dst)):
			shutil.copyfile(profile_path, dst)
		for sub in ("scans", "pieces", "crops", "sections", "photos", "overlays"):
			os.makedirs(os.path.join(path, sub), exist_ok=True)
		meta = {"id": project_id or os.path.basename(path.rstrip("/\\")), "schema_version": SCHEMA_VERSION,
				"created": _now(), "puzzle": "puzzle.json", "next_ids": {k: 1 for k in ID_PREFIXES}}
		pr = cls(path, meta, profile, Model(profile))
		open(pr.log_path, "a", encoding="utf-8").close()
		pr.save()
		return pr

	@classmethod
	def open(cls, path: str) -> "Project":
		"""Open an existing project: profile + replay of ``log.jsonl`` + photo maps."""
		path = os.path.abspath(path)
		mp = os.path.join(path, "project.json")
		if not os.path.exists(mp):
			raise StateError(f"não há project.json em {path}")
		with open(mp, encoding="utf-8") as f:
			meta = json.load(f)
		if int(meta.get("schema_version", 0)) != SCHEMA_VERSION:
			raise StateError(f"schema_version {meta.get('schema_version')} não suportada")
		profile = PuzzleProfile.load(os.path.join(path, meta.get("puzzle", "puzzle.json")))
		model = _replay_model(read_log(os.path.join(path, "log.jsonl")), profile)
		pr = cls(path, meta, profile, model)
		for k, v in model.max_ids.items():
			pr.meta["next_ids"][k] = max(int(pr.meta["next_ids"].get(k, 1)), v + 1)
		for fid in model.photos:
			fp = pr.p("photos", f"{fid}.json")
			if os.path.exists(fp):
				with open(fp, encoding="utf-8") as f:
					pr.photo_maps[fid] = Photo.from_dict(json.load(f))
		return pr

	@classmethod
	def open_or_create(cls, path: str, profile_path: str) -> "Project":
		if os.path.exists(os.path.join(path, "project.json")):
			return cls.open(path)
		return cls.create(path, profile_path)

	def _write_json(self, rel: str, obj) -> None:
		fp = self.p(rel)
		os.makedirs(os.path.dirname(fp), exist_ok=True)
		tmp = fp + ".tmp"
		with open(tmp, "w", encoding="utf-8", newline="\n") as f:
			json.dump(obj, f, ensure_ascii=False, indent=1)
			f.write("\n")
		for k in range(REPLACE_RETRIES):
			try:
				os.replace(tmp, fp)
				break
			except PermissionError:   # Windows: another process (indexer, antivirus, a reader) holds fp for a moment
				if k == REPLACE_RETRIES - 1:
					raise
				time.sleep(REPLACE_WAIT_S)

	def save(self) -> None:
		"""Write the JSON views and pending per-scan arrays (the log is already on disk)."""
		self._write_json("project.json", self.meta)
		self._write_json("board.json", self.model.board.to_dict())
		for sid, scan in self.model.scans.items():
			pcs = [p.to_dict() for p in self.model.pieces.values() if p.scan_id == sid]
			self._write_json(os.path.join("scans", f"{sid}.json"), dict(scan, pieces=pcs))
		for gid, s in self.model.sections.items():
			self._write_json(os.path.join("sections", f"{gid}.json"), s.to_dict())
		self._write_json("pairs.json", {pid: pr.to_dict() for pid, pr in self.model.pairs.items()})
		for fid, ph in self.photo_maps.items():
			self._write_json(os.path.join("photos", f"{fid}.json"), ph.to_dict())
		for sid, arrs in list(self._pending_arrays.items()):
			fp = self.p("pieces", f"{sid}.npz")
			os.makedirs(os.path.dirname(fp), exist_ok=True)
			old = {}
			if os.path.exists(fp):
				with np.load(fp, allow_pickle=False) as z:
					old = {k: z[k] for k in z.files}
			old.update(arrs)
			np.savez_compressed(fp, **old)
			del self._pending_arrays[sid]

	# ------------------------------------------------------------ ids + log
	def _new_id(self, prefix: str) -> str:
		n = int(self.meta["next_ids"].get(prefix, 1))
		self.meta["next_ids"][prefix] = n + 1
		return f"{prefix}{n:04d}"

	def _emit(self, action: str, **data) -> dict:
		if action not in ACTIONS:
			raise StateError(f"ação desconhecida {action!r}")
		ev = {"t": _now(), "action": action, **data}
		ev = json.loads(json.dumps(ev, ensure_ascii=False))  # normalise (tuples -> lists), as replay sees it
		apply(self.model, ev)
		with open(self.log_path, "a", encoding="utf-8", newline="\n") as f:
			f.write(json.dumps(ev, ensure_ascii=False) + "\n")
		return ev

	def log_event(self, action: str, **data) -> dict:
		"""Append an informative event (e.g. ``twin_confirmed``); state events use the operations."""
		return self._emit(action, **data)

	def events(self) -> list:
		return read_log(self.log_path)

	# ------------------------------------------------------------ accessors
	@property
	def board(self) -> Board:
		return self.model.board

	@property
	def pieces(self) -> dict:
		return self.model.pieces

	@property
	def pairs(self) -> dict:
		return self.model.pairs

	@property
	def sections(self) -> dict:
		return self.model.sections

	def piece(self, pid: str) -> Piece:
		return _piece(self.model, pid)

	def _check_cell(self, cell) -> tuple:
		cell = _cell(cell)
		if not self.profile.in_grid(*cell):
			raise StateError(f"célula {cell} fora da grelha {self.profile.rows}x{self.profile.cols}")
		return cell

	def shape(self, pid: str):
		"""The piece's :class:`src.shape.Shape` (from ``pieces/<scan>.npz``), or None."""
		if pid in self._shape_cache:
			return self._shape_cache[pid]
		from src.shape import Shape
		p = self.piece(pid)
		arrs = self._pending_arrays.get(p.scan_id)
		pre = f"{pid}__"
		d = None
		if arrs and any(k.startswith(pre) for k in arrs):
			d = {k[len(pre):]: v for k, v in arrs.items() if k.startswith(pre)}
		else:
			fp = self.p("pieces", f"{p.scan_id}.npz")
			if os.path.exists(fp):
				with np.load(fp, allow_pickle=False) as z:
					d = {k[len(pre):]: z[k] for k in z.files if k.startswith(pre)}
		sh = None
		if d and "c" in d:
			sh = Shape.from_arrays({k: v for k, v in d.items() if k not in ("contour_px", "mask")})
		self._shape_cache[pid] = sh
		return sh

	def contour_px(self, pid: str):
		p = self.piece(pid)
		key = f"{pid}__contour_px"
		arrs = self._pending_arrays.get(p.scan_id) or {}
		if key in arrs:
			return arrs[key]
		fp = self.p("pieces", f"{p.scan_id}.npz")
		if os.path.exists(fp):
			with np.load(fp, allow_pickle=False) as z:
				if key in z.files:
					return z[key]
		return None

	def crop_rgba(self, pid: str):
		"""RGBA crop as ``(h, w, 4)`` uint8 array, or None."""
		p = self.piece(pid)
		if not p.crop_path:
			return None
		fp = self.p(p.crop_path)
		if not os.path.exists(fp):
			return None
		from PIL import Image
		with Image.open(fp) as im:
			return np.asarray(im.convert("RGBA")).copy()

	def last_photo(self) -> Optional[Photo]:
		if not self.model.photos:
			return None
		fid = max(self.model.photos)
		return self.photo_maps.get(fid)

	# ------------------------------------------------------------ operations
	def add_scan(self, path: Optional[str], dpi: float = 300, lote: Optional[int] = None, kind: str = "soltas",
				 meta: Optional[dict] = None) -> str:
		"""Register a scan (``lote`` = numbered bag); returns the scan id."""
		sid = self._new_id("S")
		rel, sha = path, None
		if path and os.path.exists(path):
			sha = file_sha256(path)
			repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
			ap = os.path.abspath(path)
			rel = os.path.relpath(ap, repo).replace("\\", "/") if ap.lower().startswith(repo.lower()) else ap
		scan = {"id": sid, "file": rel, "sha256": sha, "dpi": float(dpi), "lote": lote, "kind": kind,
				"date": _now(), "meta": meta or {}}
		self._emit("scan_added", scan=scan)
		return sid

	def add_piece(self, scan_id: str, piece_dict: dict) -> str:
		"""Add a loose piece of ``scan_id``; returns the piece id.

		``piece_dict``: ``Piece`` fields (``index_in_scan`` required; ``lote`` defaults to
		the scan's) plus optional arrays ``shape`` (Shape), ``contour`` (px), ``mask``
		(uint8) kept in ``pieces/<scan>.npz``.
		"""
		if scan_id not in self.model.scans:
			raise StateError(f"scan desconhecido {scan_id}")
		pid = self._new_id("P")
		d = {k: v for k, v in piece_dict.items() if k not in ("shape", "contour", "mask")}
		d.setdefault("lote", self.model.scans[scan_id].get("lote"))
		shape = piece_dict.get("shape")
		if shape is not None:
			d.setdefault("cls", shape.cls)
			d.setdefault("n_flat", int(shape.n_flat))
			d.setdefault("chords_mm", [round(x, 3) for x in shape.lens])
			d.setdefault("area_mm2", round(float(shape.area_mm2), 2))
			d.setdefault("shape_ok", bool(shape.ok))
		d.update(id=pid, scan_id=scan_id, estado="solta", celula=None, seccao_id=None, same_as=None)
		piece = Piece.from_dict(d)
		arrs = self._pending_arrays.setdefault(scan_id, {})
		if shape is not None:
			for k, v in shape.to_arrays().items():
				arrs[f"{pid}__{k}"] = v
			self._shape_cache[pid] = shape
		if piece_dict.get("contour") is not None:
			arrs[f"{pid}__contour_px"] = np.asarray(piece_dict["contour"]).reshape(-1, 2).astype(np.int32)
		if piece_dict.get("mask") is not None:
			arrs[f"{pid}__mask"] = np.asarray(piece_dict["mask"], np.uint8)
		self._emit("piece_added", piece=piece.to_dict())
		return pid

	def set_lote(self, scan_ids, lote: Optional[int], *, renumber: bool = True) -> dict:
		"""Move whole scans (sheets) to bag ``lote``; logs ``lote_changed`` and returns the event.

		With ``renumber`` the pieces get continuous numbers in the target bag: scans in the
		given order, within each scan by the current ``n_no_lote`` (the ingest reading order,
		ties / missing by ``index_in_scan``), starting after the largest number already used in
		the target bag by scans not in ``scan_ids`` (same rule as :func:`src.ingest.ingest_scan`).
		``lote=None`` numbers each scan from 1. Scans left behind keep their numbers (stable).
		Without ``renumber`` the numbers are kept and a clash in the target bag is an error.
		"""
		sids = [str(s) for s in scan_ids]
		if not sids:
			raise StateError("set_lote: nenhum scan indicado")
		if len(set(sids)) != len(sids):
			raise StateError(f"set_lote: scans repetidos {sids}")
		for sid in sids:
			if sid not in self.model.scans:
				raise StateError(f"scan desconhecido {sid}")
		lote = None if lote is None else int(lote)
		inf = float("inf")
		by_scan = {sid: sorted((p for p in self.pieces.values() if p.scan_id == sid),
							   key=lambda q: (q.n_no_lote if q.n_no_lote is not None else inf, q.index_in_scan, q.id))
				   for sid in sids}
		nums = {}
		if renumber:
			n0 = 0
			if lote is not None:
				n0 = max([q.n_no_lote or 0 for q in self.pieces.values() if q.lote == lote and q.scan_id not in sids]
						 or [0])
			for sid in sids:
				if lote is None:
					n0 = 0
				for q in by_scan[sid]:
					n0 += 1
					nums[q.id] = n0
		else:
			nums = {q.id: q.n_no_lote for sid in sids for q in by_scan[sid]}
			if lote is not None:
				used = {q.n_no_lote for q in self.pieces.values()
						if q.lote == lote and q.scan_id not in sids and q.n_no_lote is not None}
				mine = [n for n in nums.values() if n is not None]
				clash = sorted((used & set(mine)) | {n for n in mine if mine.count(n) > 1})
				if clash:
					raise StateError(f"set_lote sem renumerar: números {clash} repetidos no lote {lote}")
		return self._emit("lote_changed", scan_ids=sids, lote=lote, pieces=nums)

	def place(self, piece_id: str, cell, *, origin: str = "manual", rank=None, score=None, fonte: str = "log",
			  theta_deg: Optional[float] = None) -> dict:
		"""Place a piece in ``cell`` (vazia or ocupada_legado; never over another piece)."""
		p = self.piece(piece_id)
		cell = self._check_cell(cell)
		if p.estado not in _PLACEABLE_FROM:
			raise StateError(f"{piece_id} está '{p.estado}': não pode ser colocada")
		if fonte not in CELL_SOURCES:
			raise StateError(f"fonte inválida {fonte!r}")
		cur = self.board[cell]
		if cur["estado"] == "colocada":
			raise StateError(f"célula {cell} já tem a peça {cur['peca_id']}")
		before = self._placeable_set()
		ev = self._emit("placed", piece=piece_id, cell=cell, origin=origin, rank=rank, score=score, fonte=fonte,
						theta_deg=theta_deg, prev=copy.deepcopy(cur), from_state=p.estado)
		self._emit_placeable(before)
		return ev

	def unplace(self, piece_id: str) -> dict:
		"""Undo a placement: the piece goes back to the loose pool (``emparelhada`` if it has an
		active pair, else ``solta``) and the cell gets back its previous state (e.g.
		``ocupada_legado``)."""
		p = self.piece(piece_id)
		if p.estado != "colocada":
			raise StateError(f"{piece_id} não está colocada")
		to = "emparelhada" if _active_pair(self.model, piece_id) else "solta"
		prev = _empty_cell()
		for ev in reversed(self.events()):
			if ev["action"] == "placed" and ev["piece"] == piece_id:
				prev = ev.get("prev") or prev
				break
		return self._emit("unplaced", piece=piece_id, cell=p.celula, restore=prev, to=to)

	def set_position_known(self, piece_id: str, cell, origin: str = "manual", theta_deg: Optional[float] = None) -> dict:
		"""The piece's cell is known but it is kept aside until a neighbour is assembled."""
		p = self.piece(piece_id)
		cell = self._check_cell(cell)
		if p.estado not in LOOSE_STATES + ("posicao_conhecida",):
			raise StateError(f"{piece_id} está '{p.estado}'")
		if self.board[cell]["estado"] == "colocada":
			raise StateError(f"célula {cell} já tem a peça {self.board[cell]['peca_id']}")
		other = [q.id for q in self.pieces.values() if q.estado == "posicao_conhecida" and q.celula == cell and q.id != piece_id]
		if other:
			raise StateError(f"célula {cell} já é a posição conhecida de {other[0]}")
		return self._emit("position_known", piece=piece_id, cell=cell, origin=origin, theta_deg=theta_deg)

	def register_pair(self, a: str, b: str, d1=None, margin=None, image=None, cells=None) -> str:
		"""Register a proposed twin pair between two loose pieces; returns the pair id."""
		if a == b:
			raise StateError("um par precisa de duas peças diferentes")
		for pid in (a, b):
			if self.piece(pid).estado not in LOOSE_STATES:
				raise StateError(f"{pid} não está solta")
		for pr in self.pairs.values():
			if {pr.a, pr.b} == {a, b} and pr.estado != "rejeitado":
				raise StateError(f"par {a}/{b} já registado ({pr.id})")
		tid = self._new_id("T")
		pr = Pair(id=tid, a=a, b=b, d1_mm=d1, margin=margin, image=image, cells=list(cells or []))
		self._emit("pair_registered", pair=pr.to_dict())
		return tid

	def confirm_pair(self, pair_id: str) -> dict:
		if pair_id not in self.pairs:
			raise StateError(f"par desconhecido {pair_id}")
		return self._emit("pair_confirmed", pair=pair_id)

	def reject_pair(self, pair_id: str) -> dict:
		if pair_id not in self.pairs:
			raise StateError(f"par desconhecido {pair_id}")
		return self._emit("pair_rejected", pair=pair_id)

	def register_section(self, scan_id: Optional[str], kind: str, cells_local: dict, candidates=None,
						 notes: str = "") -> str:
		"""Register a section; its pieces go to ``em_seccao``. Returns the section id."""
		if kind not in SECTION_KINDS:
			raise StateError(f"tipo de secção inválido {kind!r}")
		for pid in cells_local:
			if self.piece(pid).estado not in LOOSE_STATES:
				raise StateError(f"{pid} está '{self.piece(pid).estado}': não pode entrar numa secção")
		if len({tuple(v) for v in cells_local.values()}) != len(cells_local):
			raise StateError("duas peças com a mesma célula local")
		gid = self._new_id("G")
		s = Section(id=gid, scan_id=scan_id, kind=kind, cells_local={k: _cell(v) for k, v in cells_local.items()},
					candidates=list(candidates or []), notes=notes)
		self._emit("section_registered", section=s.to_dict())
		return gid

	def anchor_section(self, section_id: str, l0: int, c0: int, rot: int = 0, mirror: bool = False,
					   fonte: str = "manual", confianca=None, margin=None) -> dict:
		"""Give board coordinates to a section; places its pieces (``fonte='legado_scan'``).

		Cells already ``colocada`` by another piece are conflicts: reported in the
		returned event (``conflicts``), never overwritten (that piece stays ``em_seccao``).
		"""
		if section_id not in self.sections:
			raise StateError(f"secção desconhecida {section_id}")
		s = self.sections[section_id]
		if s.anchor.get("anchored"):
			raise StateError(f"{section_id} já está ancorada (unanchor primeiro)")
		if int(rot) % 90:
			raise StateError("rot tem de ser múltiplo de 90")
		anchor = {"anchored": True, "l0": int(l0), "c0": int(c0), "rot": int(rot) % 360, "mirror": bool(mirror),
				  "fonte": fonte, "confianca": confianca, "margin": margin}
		placements, conflicts = [], []
		for pid, rc in sorted(s.cells_local.items()):
			cell = section_cell(anchor, rc)
			if not self.profile.in_grid(*cell):
				raise StateError(f"{pid}: célula {cell} fora da grelha com esta ancoragem")
			if self.pieces[pid].estado != "em_seccao":
				continue
			cur = self.board[cell]
			if cur["estado"] == "colocada":
				conflicts.append({"piece": pid, "cell": list(cell), "occupant": cur["peca_id"]})
				continue
			placements.append({"piece": pid, "cell": list(cell), "restore": copy.deepcopy(cur)})
		before = self._placeable_set()
		ev = self._emit("section_anchored", section=section_id, anchor=anchor, placements=placements, conflicts=conflicts)
		self._emit_placeable(before)
		return ev

	def unanchor_section(self, section_id: str) -> dict:
		"""Undo :meth:`anchor_section` (cells get back their previous state)."""
		if section_id not in self.sections:
			raise StateError(f"secção desconhecida {section_id}")
		if not self.sections[section_id].anchor.get("anchored"):
			raise StateError(f"{section_id} não está ancorada")
		last = None
		for ev in reversed(self.events()):
			if ev["action"] == "section_anchored" and ev["section"] == section_id:
				last = ev
				break
		placements = []
		for pl in (last or {}).get("placements", []):
			p = self.pieces[pl["piece"]]
			if p.estado == "colocada" and p.celula == _cell(pl["cell"]):
				placements.append(pl)
		return self._emit("section_unanchored", section=section_id, placements=placements)

	def register_photo(self, photo: Photo) -> list:
		"""Register a board photo and reconcile the board with it; returns warnings (str).

		Full in the photo and ``vazia`` → ``ocupada_legado``; empty in the photo and
		``ocupada_legado`` → ``vazia``; ``colocada`` but empty in the photo → warning only;
		uncertain (-1) → nothing. A ``posicao_conhecida`` whose cell gains an occupied
		neighbour → ``position_placeable`` event.
		"""
		R, C = self.profile.rows, self.profile.cols
		if len(photo.map) != R or any(len(r) != C for r in photo.map):
			raise StateError(f"mapa da foto não é {R}x{C}")
		fid = self._new_id("F")
		photo = Photo.from_dict(dict(photo.to_dict(), id=fid))
		if photo.date is None:
			photo.date = _now()
		self.photo_maps[fid] = photo
		self._write_json(os.path.join("photos", f"{fid}.json"), photo.to_dict())
		before = self._placeable_set()
		warnings = []
		changes = []
		for (l, c), cell in self.board.iter_cells():
			v = photo.value(l, c)
			if v == 1 and cell["estado"] == "vazia":
				changes.append(("cell_occupied_by_photo", (l, c)))
				kn = [q.id for q in self.pieces.values() if q.estado == "posicao_conhecida" and q.celula == (l, c)]
				if kn:
					warnings.append(f"({l},{c}) cheia na foto mas é a posição conhecida de {kn[0]}")
			elif v == 0 and cell["estado"] == "ocupada_legado":
				changes.append(("cell_cleared_by_photo", (l, c)))
			elif v == 0 and cell["estado"] == "colocada":
				warnings.append(f"({l},{c}) colocada no log ({cell['peca_id']}) mas vazia na foto {fid}")
		self._emit("photo_registered", photo={"id": fid, "file": photo.file, "sha256": photo.sha256,
											  "date": photo.date}, n_changes=len(changes), warnings=warnings)
		for action, cell in changes:
			self._emit(action, cell=cell, photo=fid)
		self._emit_placeable(before)
		return warnings

	def discard(self, piece_id: str, reason: str = "") -> dict:
		p = self.piece(piece_id)
		if p.estado in ("colocada", "descartada"):
			raise StateError(f"{piece_id} está '{p.estado}' (unplace primeiro)")
		if p.estado == "em_seccao":
			raise StateError(f"{piece_id} está numa secção")
		return self._emit("piece_discarded", piece=piece_id, reason=reason)

	def mark_same_as(self, piece_id: str, other_id: str) -> dict:
		"""``piece_id`` is a re-scan of ``other_id`` (it leaves the loose pool)."""
		self.piece(piece_id)
		self.piece(other_id)
		if piece_id == other_id:
			raise StateError("same_as precisa de duas peças diferentes")
		return self._emit("same_as", piece=piece_id, other=other_id)

	def fetch_listed(self, entries: list) -> dict:
		"""Log a "go fetch" list (compact: order, piece, cell, origin, decision)."""
		keep = ("ordem", "piece", "cell", "origin", "decision", "pair")
		return self._emit("fetch_listed", entries=[{k: e.get(k) for k in keep if k in e} for e in entries])

	# ------------------------------------------------------------ derived (in memory)
	def _claimed_cells(self) -> set:
		return {p.celula for p in self.pieces.values() if p.estado == "posicao_conhecida" and p.celula}

	def pending_twins(self) -> list:
		"""[(placed Piece, twin cell)] with the twin cell ``vazia`` and not already a known position."""
		claimed = self._claimed_cells()
		out = []
		for p in sorted(self.pieces.values(), key=lambda q: q.id):
			if p.estado != "colocada" or p.celula is None:
				continue
			tw = self.profile.twin(*p.celula)
			if tw is None or tw in claimed or self.board[tw]["estado"] != "vazia":
				continue
			out.append((p, tw))
		return out

	def holes(self) -> list:
		"""Empty cells with >= 2 occupied 4-neighbours."""
		return [lc for lc, cell in self.board.iter_cells()
				if cell["estado"] == "vazia" and self.board.n_occupied_neighbours(lc) >= 2]

	def _placeable_set(self) -> set:
		return {(p.id, p.celula) for p, _ in self.placeable_known_positions()}

	def placeable_known_positions(self) -> list:
		"""[(Piece, cell)] for ``posicao_conhecida`` pieces whose empty cell has an occupied neighbour."""
		out = []
		for p in sorted(self.pieces.values(), key=lambda q: q.id):
			if p.estado == "posicao_conhecida" and p.celula and self.board[p.celula]["estado"] == "vazia" \
					and self.board.n_occupied_neighbours(p.celula) >= 1:
				out.append((p, p.celula))
		return out

	def _emit_placeable(self, before: set) -> None:
		for p, cell in self.placeable_known_positions():
			if (p.id, cell) not in before:
				self._emit("position_placeable", piece=p.id, cell=cell)

	def missing_border_cells(self) -> list:
		"""Empty border cells (flat sides from the profile)."""
		return [lc for lc, cell in self.board.iter_cells()
				if cell["estado"] == "vazia" and self.profile.is_border(*lc)]

	def loose_pieces(self, lote: Optional[int] = None) -> list:
		"""Pieces in the loose pool (``solta``/``emparelhada``, not a re-scan), optionally of one bag."""
		return [p for p in sorted(self.pieces.values(), key=lambda q: q.id)
				if p.estado in LOOSE_STATES and not p.same_as and (lote is None or p.lote == lote)]

	def stats(self) -> dict:
		"""Counts by piece state and by cell state/source, plus ``p_twin_placed``."""
		by_state = {s: 0 for s in PIECE_STATES}
		for p in self.pieces.values():
			by_state[p.estado] = by_state.get(p.estado, 0) + 1
		n_occ = sum(1 for _, c in self.board.iter_cells() if c["estado"] != "vazia")
		n_todo = self.profile.cell_count() - n_occ
		pend = len(self.pending_twins())
		return {
			"pecas": len(self.pieces), "por_estado": by_state, "celulas": self.board.counts(),
			"celulas_ocupadas": n_occ, "n_por_colocar": n_todo, "gemeas_pendentes": pend,
			"p_twin_placed": (pend / n_todo) if n_todo else 0.0,
			"p_twin_placed_formula": f"len(pending_twins) / n_por_colocar = {pend} / {n_todo}",
			"pares": {s: sum(1 for t in self.pairs.values() if t.estado == s) for s in PAIR_STATES},
			"buracos": len(self.holes()), "borda_em_falta": len(self.missing_border_cells()),
			"seccoes_por_ancorar": sum(1 for s in self.sections.values() if not s.anchor.get("anchored")),
		}

	# ------------------------------------------------------------ invariants
	def check_invariants(self, disk: bool = False) -> list:
		"""List of violated invariants (empty = all hold).

		board == replay(log); pieces' dynamic state == replay; a cell holds <= 1 piece; a
		``colocada`` piece has exactly one cell and that cell points back to it; ids unique;
		``n_no_lote`` unique within a bag; a piece's ``lote`` is its scan's ``lote``.
		With ``disk=True`` also ``board.json`` == replay (call after :meth:`save`).
		"""
		errs = []
		try:
			rb, rp = replay(self.log_path, self.profile)
		except Exception as e:  # noqa: BLE001 - a corrupt log is itself a violation
			return [f"replay falhou: {e}"]
		if rb != self.board:
			errs.append("board != replay(log)")
		if rp != self.model.pieces_state():
			errs.append("estado das peças != replay(log)")
		if disk:
			fp = self.p("board.json")
			if os.path.exists(fp):
				with open(fp, encoding="utf-8") as f:
					if Board.from_dict(json.load(f)) != rb:
						errs.append("board.json != replay(log)")
		seen = {}
		for lc, cell in self.board.iter_cells():
			if cell["estado"] == "colocada":
				pid = cell["peca_id"]
				if pid in seen:
					errs.append(f"{pid} em duas células {seen[pid]} e {lc}")
				seen[pid] = lc
				p = self.pieces.get(pid)
				if p is None or p.estado != "colocada" or p.celula != lc:
					errs.append(f"célula {lc} aponta para {pid} que não está lá colocada")
			elif cell["peca_id"] is not None:
				errs.append(f"célula {lc} '{cell['estado']}' com peca_id {cell['peca_id']}")
		for p in self.pieces.values():
			if p.estado == "colocada" and seen.get(p.id) != p.celula:
				errs.append(f"{p.id} colocada sem célula consistente ({p.celula})")
		ids = [ev["piece"]["id"] for ev in self.events() if ev["action"] == "piece_added"]
		if len(ids) != len(set(ids)):
			errs.append("ids de peça repetidos no log")
		num = {}
		for p in sorted(self.pieces.values(), key=lambda q: q.id):
			scan = self.model.scans.get(p.scan_id)
			if scan is None:
				errs.append(f"{p.id}: scan {p.scan_id} desconhecido")
			elif p.lote != scan.get("lote"):
				errs.append(f"{p.id}: lote {p.lote} != lote {scan.get('lote')} do scan {p.scan_id}")
			if p.lote is not None:
				k = (p.lote, p.n_no_lote)
				if k in num:
					errs.append(f"lote {p.lote} nº {p.n_no_lote} repetido ({num[k]}, {p.id})")
				num[k] = p.id
		return errs
