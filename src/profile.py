"""Puzzle profile (``puzzle.json``): everything puzzle-specific lives here, not in code.

A profile describes one physical puzzle: grid, nominal cell, die symmetry, scan
background and dpi, the reference artwork, and the per-modality calibration of the
twin search (docs/plano-m10-m12.md §2.2, §11 of docs/estado-e-plano.md).

Cell convention: ``(l, c)`` with ``l`` = row 1..rows counted from the top and ``c`` =
column 1..cols counted from the left. Directions: ``'N'`` = row 1 side, ``'S'`` = row
``rows``, ``'W'`` = column 1, ``'E'`` = column ``cols``.

:meth:`PuzzleProfile.twin` is the ONLY implementation of the die symmetry in the code
base; nothing else may hard-code a twin formula.

Only :meth:`PuzzleProfile.load` / :meth:`PuzzleProfile.save` do I/O.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

__all__ = ["PuzzleProfile", "SCHEMA_VERSION", "SYMMETRY_TYPES"]

SCHEMA_VERSION = 1
SYMMETRY_TYPES = ("rot180", "none", "translate")
_KEY_ORDER = ("id", "name", "schema_version", "grid", "cell_mm", "symmetry", "background_lab", "dpi", "art",
			  "calibration", "image_zones", "modalities")


def _default_calibration() -> dict:
	return {
		"silhueta_silhueta": {"t95": None, "tmax": None},
		"celula_silhueta": {"t95": None, "tmax": None, "offset_mm": 0.0},
		"chord": {"normal_mm": 1.0, "f_adj_mm": 2.0},
		"margin_min": 1.5,
	}


@dataclass
class PuzzleProfile:
	"""Puzzle profile (schema version 1). See the module docstring for the cell convention.

	Fields mirror ``puzzle.json``: ``grid`` = ``{'cols', 'rows'}``, ``cell_mm`` =
	``{'w', 'h'}``, ``symmetry`` = ``{'type': 'rot180'|'none'|'translate', 'cols': N}``
	(``cols`` only for ``translate``), ``background_lab`` = ``[L, a, b]`` (CIE Lab,
	L in 0..100), ``dpi`` (scan resolution), ``art`` = ``{'file', 'bbox': [x, y, w, h]}``
	(file relative to the repository root, bbox in art-file pixels; optional
	``registration`` = ``{'matrix': [[a, b, tx], [c, d, ty]], 'units': 'board_mm->art_px', ...}``
	written by :mod:`src.artreg`, see :meth:`art_matrix`), ``calibration``
	(twin-search thresholds per modality, chord tolerances, minimum margin d2/d1),
	``image_zones`` (per-zone image-consistency distributions), ``modalities``
	(documentation only).
	"""

	id: str
	name: str = ""
	grid: dict = field(default_factory=lambda: {"cols": 1, "rows": 1})
	cell_mm: dict = field(default_factory=lambda: {"w": 1.0, "h": 1.0})
	symmetry: dict = field(default_factory=lambda: {"type": "none"})
	background_lab: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
	dpi: float = 300.0
	art: dict = field(default_factory=lambda: {"file": None, "bbox": None})
	calibration: dict = field(default_factory=_default_calibration)
	image_zones: dict = field(default_factory=dict)
	modalities: list = field(default_factory=list)
	schema_version: int = SCHEMA_VERSION

	def __post_init__(self) -> None:
		t = self.symmetry.get("type")
		if t not in SYMMETRY_TYPES:
			raise ValueError(f"unknown symmetry type {t!r} (expected one of {SYMMETRY_TYPES})")
		if t == "translate" and int(self.symmetry.get("cols", 0)) <= 0:
			raise ValueError("symmetry 'translate' needs a positive 'cols'")
		if int(self.grid["cols"]) <= 0 or int(self.grid["rows"]) <= 0:
			raise ValueError("grid cols/rows must be positive")
		if int(self.schema_version) != SCHEMA_VERSION:
			raise ValueError(f"unsupported schema_version {self.schema_version} (expected {SCHEMA_VERSION})")
		if float(self.dpi) <= 0:
			raise ValueError("dpi must be positive")

	# ------------------------------------------------------------ (de)serialisation
	@classmethod
	def from_dict(cls, d: dict) -> "PuzzleProfile":
		"""Build from a ``puzzle.json`` dict (unknown keys are rejected, ``id`` is required)."""
		d = copy.deepcopy(d)
		extra = set(d) - set(_KEY_ORDER)
		if extra:
			raise ValueError(f"unknown profile keys: {sorted(extra)}")
		if "id" not in d:
			raise ValueError("profile needs an 'id'")
		return cls(**d)

	def to_dict(self) -> dict:
		"""Plain JSON-serialisable dict (key order = ``puzzle.json`` order)."""
		return {k: copy.deepcopy(getattr(self, k)) for k in _KEY_ORDER}

	@classmethod
	def load(cls, path: str) -> "PuzzleProfile":
		"""Read a ``puzzle.json`` (UTF-8)."""
		with open(path, encoding="utf-8") as f:
			return cls.from_dict(json.load(f))

	def save(self, path: str) -> None:
		"""Write a ``puzzle.json`` (UTF-8, indented, non-ASCII kept)."""
		with open(path, "w", encoding="utf-8", newline="\n") as f:
			json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
			f.write("\n")

	# ------------------------------------------------------------ grid geometry
	@property
	def cols(self) -> int:
		return int(self.grid["cols"])

	@property
	def rows(self) -> int:
		return int(self.grid["rows"])

	def in_grid(self, l: int, c: int) -> bool:
		"""True if ``(l, c)`` is a cell of the grid (1-based)."""
		return 1 <= l <= self.rows and 1 <= c <= self.cols

	def cell_count(self) -> int:
		return self.rows * self.cols

	def flat_directions(self, l: int, c: int) -> set:
		"""Sides of cell ``(l, c)`` on the puzzle border, a subset of ``{'N', 'E', 'S', 'W'}``."""
		self._check(l, c)
		out = set()
		if l == 1:
			out.add("N")
		if l == self.rows:
			out.add("S")
		if c == 1:
			out.add("W")
		if c == self.cols:
			out.add("E")
		return out

	def n_flat_sides(self, l: int, c: int) -> int:
		return len(self.flat_directions(l, c))

	def is_border(self, l: int, c: int) -> bool:
		return self.n_flat_sides(l, c) > 0

	def is_corner(self, l: int, c: int) -> bool:
		return self.n_flat_sides(l, c) >= 2

	def mm_per_px(self) -> float:
		"""Scan scale from the profile dpi (``25.4 / dpi``)."""
		return 25.4 / float(self.dpi)

	# ------------------------------------------------------------ symmetry (the only implementation)
	def twin(self, l: int, c: int) -> Optional[tuple]:
		"""Twin cell of ``(l, c)`` under the die symmetry, or None if there is none.

		``rot180``: ``(rows + 1 - l, cols + 1 - c)``. ``translate`` (N = ``symmetry['cols']``):
		``(l, c + N)`` if inside the grid, else ``(l, c - N)`` (None if neither is). ``none``: None.
		"""
		self._check(l, c)
		t = self.symmetry["type"]
		if t == "rot180":
			return (self.rows + 1 - l, self.cols + 1 - c)
		if t == "translate":
			n = int(self.symmetry["cols"])
			for cc in (c + n, c - n):
				if self.in_grid(l, cc):
					return (l, cc)
			return None
		return None

	def art_matrix(self) -> Optional[np.ndarray]:
		"""2x3 affine board mm -> art-file px (continuous: pixel ``i`` covers ``[i, i+1)``), or None.

		Board mm: cell ``(l, c)`` spans ``[(c-1) w, c w] x [(l-1) h, l h]`` (``w, h`` = ``cell_mm``).
		From ``art['registration']['matrix']`` when present (measured by :mod:`src.artreg`), else
		derived from ``art['bbox'] = [x, y, bw, bh]`` (the bbox spans the whole grid):
		``x = bbox.x + mm_x * bw / (cols * w)``, ``y = bbox.y + mm_y * bh / (rows * h)``.
		None if the profile has neither.
		"""
		art = self.art or {}
		reg = art.get("registration")
		if reg and reg.get("matrix") is not None:
			M = np.asarray(reg["matrix"], np.float64)
			if M.shape != (2, 3):
				raise ValueError(f"art.registration.matrix must be 2x3, got {M.shape}")
			return M
		bb = art.get("bbox")
		if bb is None:
			return None
		x, y, bw, bh = (float(v) for v in bb)
		sx = bw / (self.cols * float(self.cell_mm["w"]))
		sy = bh / (self.rows * float(self.cell_mm["h"]))
		return np.array([[sx, 0.0, x], [0.0, sy, y]])

	def twin_rotation_deg(self) -> float:
		"""Rotation (deg) that maps a piece onto its twin's pose: 180 for ``rot180``, 0 otherwise."""
		return 180.0 if self.symmetry["type"] == "rot180" else 0.0

	def _check(self, l: int, c: int) -> None:
		if not self.in_grid(l, c):
			raise ValueError(f"cell ({l}, {c}) outside the {self.rows}x{self.cols} grid")
