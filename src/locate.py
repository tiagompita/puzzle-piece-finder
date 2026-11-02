"""Image side of the twin search: a piece crop against the reference artwork, cell by cell.

Promotion of the E-real-2 prototype (``tools/diagnostico/gemeos/ereal2.py``: ``load_art``,
``cell_tl``, ``render``, ``de_cell``, ``cell_scores``, ``joint_locate``, ``body_center``,
``body_beta``, ``snap``). The algorithm is unchanged; what was hard-coded there (grid,
artwork bbox, twin formula) now comes from :class:`src.profile.PuzzleProfile`.

What the image is for (docs/diagnostico/gemeos/EREAL2.md §3, §4): a **colour-consistency
test**, not an identity. On uniform sky the right cell is first only 3/20 times; the
image never promotes a shape decision. A pair of loose twins (one textured, one sky)
localises to a band of rows and +/- 1 column (:func:`pair_locate`).

Conventions:
	* cells ``(l, c)`` are 1-based (row from the top, column from the left), as in the profile;
	* rotations follow the complex convention of :mod:`src.shape` (``z * exp(1j * theta)``
	  with ``z = x + iy``, y down): a positive angle turns **clockwise on screen**;
	* ``theta_deg`` of a piece is the rotation that takes its scan crop to its pose on the board;
	* piece crops are RGBA ``uint8`` in the scan frame (only translated, never rotated);
	  alpha > 0 is the piece;
	* scan Lab is compared to art Lab after subtracting a uniform L* shift (``l_shift``,
	  scanner ~ art + 4.8 L*, docs/diagnostico/gemeos/SECCAO.md §C); a*/b* are not corrected.

Pure module except :func:`load_art_rectified_masked` / :func:`load_art_rectified` /
:meth:`CellArt.load` (read the artwork file).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

__all__ = [
	"CellArt", "rectify_art", "rectified_size", "load_art_rectified", "load_art_rectified_masked", "piece_render", "render_item", "de_cell", "cell_scores", "piece_mean_lab", "locate_group",
	"pair_locate", "body_center_mm", "body_beta_deg", "snap_theta", "wrap_deg", "rotate_dir",
	"CANVAS", "CANVAS_CELLS", "JIT", "ERODE_PX", "L_SHIFT", "MASK_FULL", "MIN_OVERLAP", "MIN_CELL_ART", "PRIOR_WEIGHT",
	"REFINE_TOP", "DIRS",
]

# ---------------------------------------------------------------- constants (E-real-2, EREAL2.md §3)
CANVAS = (43, 41)           # (W, H) art px of a crop window for the Alpes art (25 x 23.7 px cells): cell + ~0.36 cell of rim
CANVAS_CELLS = (43 / 25.0, 41 / (1115 / 47.0))   # the same window in cells, for other art resolutions
JIT = 2                     # +/- art px of jitter of the art window
ERODE_PX = 1                # piece mask eroded by 1 art px (~0.76 mm): removes the shadow/background rim
L_SHIFT = 4.8               # L*scan ~ L*art + 4.8 (subtracted from the scan)
MASK_FULL = 0.99            # an art px belongs to the mask if >= 99 % of it is piece
MIN_OVERLAP = 0.6           # a window position counts if >= 60 % of the mask falls inside the art
MIN_CELL_ART = 0.5          # a cell has art if >= 50 % of its px fall inside the art file (else cell_lab_mean NaN)
PRIOR_WEIGHT = 2.0          # locate_group: dE units added per unit fraction of items on cells against the occupancy prior
REFINE_TOP = 20             # locate_group: placements re-scored with the full crops (de_cell)
DIRS = ("N", "E", "S", "W")  # clockwise order; a +90 deg (clockwise) rotation maps N->E->S->W->N


# ---------------------------------------------------------------- small geometry helpers (pure)
def wrap_deg(a):
	"""Angle(s) wrapped to [-180, 180)."""
	return (np.asarray(a, float) + 180.0) % 360.0 - 180.0


def rotate_dir(d: str, rot_deg: int, mirror: bool = False) -> str:
	"""Direction ``d`` in a local frame after an optional E<->W mirror and a clockwise rotation (multiple of 90)."""
	if mirror and d in ("E", "W"):
		d = "W" if d == "E" else "E"
	return DIRS[(DIRS.index(d) + int(round(rot_deg / 90.0))) % 4]


def _rot_rc(r, c, rot_deg: int, mirror: bool = False):
	"""Local (row, col) offset after an optional column mirror and a clockwise rotation (multiple of 90)."""
	r = np.asarray(r)
	c = -np.asarray(c) if mirror else np.asarray(c)
	for _ in range(int(round(rot_deg / 90.0)) % 4):
		r, c = c, -r     # clockwise on screen: N (-1, 0) -> E (0, +1)
	return r, c


def body_center_mm(shape) -> np.ndarray:
	"""Centre of the body of a :class:`src.shape.Shape` (mean of its 4 corners; area centroid if not ok), mm."""
	if shape.ok and len(shape.corners) == 4:
		return shape.c[shape.corners].mean(0)
	return np.asarray(shape.centroid_mm, float)


def body_beta_deg(shape) -> float:
	"""Rotation (deg, complex convention) that aligns the body sides with the axes, in (-45, 45].

	From the polygon of the 4 corners (prototype ``ereal2.body_beta``); from
	``shape.body_angle_deg`` if the shape is not ok.
	"""
	if shape.ok and len(shape.corners) == 4:
		P = shape.c[shape.corners]
		v = np.roll(P, -1, 0) - P
		a = np.angle(np.sum(np.exp(4j * np.arctan2(v[:, 1], v[:, 0])))) / 4
		return float(-np.degrees(a))
	b = -float(shape.body_angle_deg) % 90.0
	return b - 90.0 if b > 45.0 else b


def snap_theta(shape, theta_deg: float):
	"""Nearest body-aligned rotation to ``theta_deg``: ``(beta + 90 m, m, residual_deg)``, ``m`` in 0..3."""
	b = body_beta_deg(shape)
	m = int(np.round((theta_deg - b) / 90.0)) % 4
	return float(b + 90.0 * m), m, float(wrap_deg(theta_deg - (b + 90.0 * m)))


def _finite_median(a, axis=None):
	"""Median over the finite values (NaN / inf = no art evidence); inf where there is none."""
	b = np.asarray(a, float)
	ok = np.isfinite(b)
	if axis is None:
		return float(np.median(b[ok])) if ok.any() else float("inf")
	srt = np.sort(np.where(ok, b, np.inf), axis=axis)
	n = ok.sum(axis=axis)
	lo = np.take_along_axis(srt, np.expand_dims(np.maximum((n - 1) // 2, 0), axis), axis).squeeze(axis)
	hi = np.take_along_axis(srt, np.expand_dims(np.maximum(n // 2, 0), axis), axis).squeeze(axis)
	return np.where(n > 0, 0.5 * (lo + hi), np.inf)


def _lab(rgb_u8: np.ndarray) -> np.ndarray:
	"""Float Lab (L* 0..100) of an RGB uint8 image."""
	return cv2.cvtColor(np.ascontiguousarray(rgb_u8).astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB)


# ---------------------------------------------------------------- art -> cell grid (the single board -> art transform)
def rectified_size(matrix, rows: int, cols: int, cell_mm) -> tuple:
	"""Raster size ``(W, H)`` that keeps the art's native resolution along each grid axis.

	``W = cols * w * |column x of the matrix|`` (art px per board mm along x), same for ``H``;
	for a bbox-derived matrix this is exactly ``(bbox.w, bbox.h)``.
	"""
	M = np.asarray(matrix, np.float64)
	W = int(round(cols * float(cell_mm[0]) * float(np.hypot(M[0, 0], M[1, 0]))))
	H = int(round(rows * float(cell_mm[1]) * float(np.hypot(M[0, 1], M[1, 1]))))
	return max(W, 1), max(H, 1)


def rectify_art(art_rgb: np.ndarray, matrix, rows: int, cols: int, cell_mm, size=None, content_bbox=None, *,
				return_valid: bool = False):
	"""Art image -> raster that covers exactly ``rows x cols`` cells (pure).

	``matrix`` = 2x3 affine board mm -> art px (continuous, pixel ``i`` covers ``[i, i+1)``);
	``cell_mm`` = ``(w, h)``; ``size`` = output ``(W, H)`` (default :func:`rectified_size`).
	Raster pixel ``(u, v)`` samples the art at ``matrix @ ((u + 0.5) kx, (v + 0.5) ky, 1) - 0.5``
	with ``kx = cols w / W``, ``ky = rows h / H`` (bilinear; outside the art: replicated edge).
	A matrix that is an integer translation of a pure per-axis scale whose output size equals
	the scaled grid (the ``bbox`` case) reproduces the plain bbox crop exactly.
	``content_bbox`` = ``[x, y, w, h]`` region of the file that holds the art (the rest is a
	margin): the file is cropped to it first, so grid cells the art does not reach get the
	replicated edge of the art, never the margin colour. ``return_valid``: also return the
	``(H, W)`` bool mask of raster px that fall inside the art (False = no art there: the
	replicated colour is filler, never evidence).
	"""
	M = np.asarray(matrix, np.float64)
	if content_bbox is not None:
		x, y, w, h = (int(v) for v in content_bbox)
		art_rgb = art_rgb[y:y + h, x:x + w]
		M = M.copy()
		M[:, 2] -= (x, y)
	W, H = size if size is not None else rectified_size(M, rows, cols, cell_mm)
	kx, ky = cols * float(cell_mm[0]) / W, rows * float(cell_mm[1]) / H
	# raster index -> board mm: mm = (idx + 0.5) * k ; art index = M @ mm - 0.5
	S = np.array([[kx, 0.0, 0.5 * kx], [0.0, ky, 0.5 * ky], [0.0, 0.0, 1.0]])
	A = M @ S
	A[:, 2] -= 0.5
	if np.allclose(A[:, :2], np.eye(2), atol=1e-9) and np.allclose(A[:, 2], np.round(A[:, 2]), atol=1e-6):
		x0, y0 = int(round(A[0, 2])), int(round(A[1, 2]))
		h, w = art_rgb.shape[:2]
		if 0 <= x0 and 0 <= y0 and x0 + W <= w and y0 + H <= h:
			out = np.ascontiguousarray(art_rgb[y0:y0 + H, x0:x0 + W])
			return (out, np.ones((int(H), int(W)), bool)) if return_valid else out
	out = cv2.warpAffine(np.ascontiguousarray(art_rgb), A, (int(W), int(H)), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
						 borderMode=cv2.BORDER_REPLICATE)
	if not return_valid:
		return out
	ones = np.ones(art_rgb.shape[:2], np.float32)
	v = cv2.warpAffine(ones, A, (int(W), int(H)), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
					   borderMode=cv2.BORDER_CONSTANT, borderValue=0)
	return out, v >= 0.5


def load_art_rectified_masked(profile, repo_root) -> tuple:
	"""``(rgb, valid)``: the art of ``profile`` rectified to the cell grid and the mask of raster px that have art.

	The single entry point for "the art under the board" (:meth:`CellArt.load`,
	:func:`load_art_rectified`, :func:`src.render._art_rgb`): :func:`rectify_art` with
	``profile.art_matrix()``, the file first cropped to ``art['bbox']`` (its art content,
	without the white margin). Grid px beyond the art (row 47 of the Alpes: the digital file
	stops ~1 row short of the print, docs/diagnostico/arte/ARTREG.md) are ``valid = False``
	(their colour is the replicated edge, filler only). Raises ``ValueError`` / ``FileNotFoundError``.
	"""
	art = profile.art or {}
	if not art.get("file"):
		raise ValueError("profile has no art file")
	path = Path(repo_root) / art["file"]
	if not path.exists():
		raise FileNotFoundError(str(path))
	im = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
	if im is None:
		raise ValueError(f"cannot decode {path}")
	rgb = cv2.cvtColor(im, cv2.COLOR_BGR2RGB)
	M = profile.art_matrix()
	cell = (float(profile.cell_mm["w"]), float(profile.cell_mm["h"]))
	if M is None:
		M = np.array([[rgb.shape[1] / (profile.cols * cell[0]), 0.0, 0.0], [0.0, rgb.shape[0] / (profile.rows * cell[1]), 0.0]])
	bb = art.get("bbox")
	if bb is not None:     # the bbox = the art content of the file (prior of the registration and the crop margin)
		x, y, w, h = (int(v) for v in bb)
		if x < 0 or y < 0 or x + w > rgb.shape[1] or y + h > rgb.shape[0]:
			raise ValueError(f"art bbox {bb} outside the {rgb.shape[1]}x{rgb.shape[0]} image")
	return rectify_art(rgb, M, profile.rows, profile.cols, cell, content_bbox=bb, return_valid=True)


def load_art_rectified(profile, repo_root, *, fill=None) -> np.ndarray:
	"""RGB uint8 art rectified to the cell grid (:func:`load_art_rectified_masked`); px without art are
	painted ``fill`` (RGB) if given, else keep the replicated edge of the art."""
	rgb, valid = load_art_rectified_masked(profile, repo_root)
	if fill is not None and not valid.all():
		rgb = rgb.copy()
		rgb[~valid] = np.asarray(fill, np.uint8)
	return rgb


# ---------------------------------------------------------------- the artwork
@dataclass
class CellArt:
	"""Reference artwork rectified to the puzzle grid (profile ``art_matrix``), in Lab, with the cell grid.

	lab: ``(H, W, 3)`` float32 Lab. cell_px: ``(w, h)`` art px per cell (``W / cols``,
	``H / rows``). cell_lab_mean: ``(rows, cols, 3)`` mean Lab per cell. pitch_mm: physical
	``(w, h)`` mm per cell used to bring scan crops to the art scale (default: the profile's
	``cell_mm``). l_shift: L* subtracted from scan crops. rgb: the art crop (uint8, for figures).
	valid: ``(H, W)`` bool, px that have art (None = all). Px without art stay finite in ``lab``
	(replicated filler, so whole-raster filters never see NaN) but are NaN in the padded art used
	by :meth:`cell_crop`, :func:`de_cell` and :func:`cell_scores` (they never count); a cell with
	less than ``MIN_CELL_ART`` of its px valid has ``cell_lab_mean`` NaN (:meth:`has_art` False).
	"""

	lab: np.ndarray
	cell_px: tuple
	cell_lab_mean: np.ndarray
	pitch_mm: tuple = (1.0, 1.0)
	l_shift: float = L_SHIFT
	rgb: np.ndarray | None = None
	valid: np.ndarray | None = None
	_pad: dict = field(default=None, init=False, repr=False)

	@classmethod
	def from_rgb(cls, rgb: np.ndarray, rows: int, cols: int, *, pitch_mm=(1.0, 1.0), l_shift: float = L_SHIFT,
				 valid=None) -> "CellArt":
		"""Build from an RGB uint8 art crop that covers exactly ``rows x cols`` cells (``valid``: px with art, None = all)."""
		rgb = np.ascontiguousarray(rgb[..., :3]).astype(np.uint8)
		lab = _lab(rgb)
		H, W = lab.shape[:2]
		if valid is not None:
			valid = np.asarray(valid, bool)
			if valid.shape != (H, W):
				raise ValueError(f"valid mask {valid.shape} != art {(H, W)}")
			if valid.all():
				valid = None
		cw, ch = W / float(cols), H / float(rows)
		mean = np.zeros((rows, cols, 3), np.float64)
		for i in range(rows):
			y0, y1 = int(round(i * ch)), max(int(round((i + 1) * ch)), int(round(i * ch)) + 1)
			for j in range(cols):
				x0, x1 = int(round(j * cw)), max(int(round((j + 1) * cw)), int(round(j * cw)) + 1)
				px = lab[y0:y1, x0:x1].reshape(-1, 3)
				if valid is None:
					mean[i, j] = px.mean(0)
					continue
				v = valid[y0:y1, x0:x1].reshape(-1)
				mean[i, j] = px[v].mean(0) if v.mean() >= MIN_CELL_ART else np.nan
		return cls(lab=lab, cell_px=(cw, ch), cell_lab_mean=mean, pitch_mm=(float(pitch_mm[0]), float(pitch_mm[1])),
				   l_shift=float(l_shift), rgb=rgb, valid=valid)

	@classmethod
	def load(cls, profile, repo_root, *, pitch_mm=None, l_shift: float = L_SHIFT) -> "CellArt":
		"""Read ``profile.art['file']`` (relative to ``repo_root``) rectified to the cell grid.

		The art is mapped to a raster that covers exactly ``rows x cols`` cells through
		:meth:`src.profile.PuzzleProfile.art_matrix` (the measured ``art.registration`` if the
		profile has one, else the ``bbox``; see :func:`load_art_rectified`), so every consumer
		of the cell grid uses the same board -> art transform. EXIF orientation is ignored.
		``pitch_mm`` defaults to ``(profile.cell_mm['w'], profile.cell_mm['h'])``.
		Raises ``FileNotFoundError`` / ``ValueError`` (loader, not a pipeline step).
		"""
		rgb, valid = load_art_rectified_masked(profile, repo_root)
		if pitch_mm is None:
			pitch_mm = (float(profile.cell_mm["w"]), float(profile.cell_mm["h"]))
		return cls.from_rgb(rgb, profile.rows, profile.cols, pitch_mm=pitch_mm, l_shift=l_shift, valid=valid)

	@property
	def rows(self) -> int:
		return int(self.cell_lab_mean.shape[0])

	@property
	def cols(self) -> int:
		return int(self.cell_lab_mean.shape[1])

	@property
	def canvas(self) -> tuple:
		"""Crop window ``(W, H)`` for this art: ``CANVAS_CELLS`` cells (equals ``CANVAS`` for the Alpes art)."""
		return (int(round(self.cell_px[0] * CANVAS_CELLS[0])), int(round(self.cell_px[1] * CANVAS_CELLS[1])))

	def scan_scale(self, mm_per_px: float) -> tuple:
		"""Art px per scan px ``(fx, fy)`` for a scan of ``mm_per_px``."""
		return (self.cell_px[0] * mm_per_px / self.pitch_mm[0], self.cell_px[1] * mm_per_px / self.pitch_mm[1])

	def _padded(self) -> dict:
		if self._pad is None:
			W, H = self.canvas
			pad = int(max(W, H) + 2 * JIT + 4)
			h, w = self.lab.shape[:2]
			labp = np.full((h + 2 * pad, w + 2 * pad, 3), np.nan)
			labp[pad:pad + h, pad:pad + w] = self.lab
			if self.valid is not None:
				labp[pad:pad + h, pad:pad + w][~self.valid] = np.nan     # no art there: never evidence
			V = (~np.isnan(labp[..., 0])).astype(np.float64)
			A0 = np.nan_to_num(labp)
			self._pad = dict(pad=pad, labp=labp, V=V, AV=[A0[..., ch] * V for ch in range(3)], A2V=(A0 ** 2).sum(-1) * V)
		return self._pad

	def has_art(self, l: int, c: int) -> bool:
		"""True if cell ``(l, c)`` has art (>= ``MIN_CELL_ART`` of its px inside the art file)."""
		return bool(np.isfinite(self.cell_lab_mean[int(l) - 1, int(c) - 1]).all())

	def cell_tl(self, l, c, canvas=None):
		"""Top-left corner (padded-art px) of the window ``canvas`` centred on cell ``(l, c)`` (arrays allowed)."""
		W, H = canvas or self.canvas
		pad = self._padded()["pad"]
		return (np.round((np.asarray(c) - 0.5) * self.cell_px[0] - W / 2).astype(int) + pad,
				np.round((np.asarray(l) - 0.5) * self.cell_px[1] - H / 2).astype(int) + pad)

	def cell_crop(self, l: int, c: int, canvas=None) -> np.ndarray:
		"""Lab ``(H, W, 3)`` window centred on cell ``(l, c)``; NaN outside the art."""
		W, H = canvas or self.canvas
		x0, y0 = self.cell_tl(l, c, (W, H))
		return self._padded()["labp"][y0:y0 + H, x0:x0 + W].copy()

	def cell_crop_rgb(self, l: int, c: int, canvas=None, off=(0, 0)) -> np.ndarray:
		"""RGB uint8 window centred on cell ``(l, c)`` shifted by ``off`` (white outside the art); for figures."""
		W, H = canvas or self.canvas
		pad = self._padded()["pad"]
		h, w = self.rgb.shape[:2]
		big = np.full((h + 2 * pad, w + 2 * pad, 3), 255, np.uint8)
		big[pad:pad + h, pad:pad + w] = self.rgb
		x0, y0 = self.cell_tl(l, c, (W, H))
		return big[y0 + off[1]:y0 + off[1] + H, x0 + off[0]:x0 + off[0] + W].copy()


# ---------------------------------------------------------------- piece crops
def _alpha_centroid(alpha: np.ndarray) -> np.ndarray:
	m = cv2.moments((alpha > 0).astype(np.uint8), binaryImage=True)
	if m["m00"] <= 0:
		return np.array([alpha.shape[1] / 2.0, alpha.shape[0] / 2.0])
	return np.array([m["m10"] / m["m00"], m["m01"] / m["m00"]])


def piece_render(rgba: np.ndarray, theta_deg: float, canvas=CANVAS, *, scale=(1.0, 1.0), center_px=None,
				 l_shift: float = L_SHIFT, erode_px: int = ERODE_PX, mirror: bool = False) -> dict:
	"""Piece crop turned to its board pose and reduced to the art scale (prototype ``ereal2.render``).

	The crop is rotated by ``theta_deg`` (complex convention, clockwise on screen) about
	``center_px`` (crop px; default: the alpha centroid — pass the body centre for real
	pieces, see :func:`render_item`), placed at the centre of a ``canvas`` window and
	resampled by ``scale`` = art px per scan px. ``mirror`` flips x before rotating.
	Returns ``{'lab': (H, W, 3) Lab with L* - l_shift, 'mask': (H, W) bool (strict
	interior, eroded erode_px), 'rgb': (H, W, 3) uint8, 'theta_deg'}``.
	"""
	rgba = np.asarray(rgba)
	rgb = np.ascontiguousarray(rgba[..., :3]).astype(np.uint8)
	alpha = rgba[..., 3] if rgba.shape[-1] == 4 else np.full(rgba.shape[:2], 255, np.uint8)
	cb = _alpha_centroid(alpha) if center_px is None else np.asarray(center_px, float).reshape(2)
	W, H = int(canvas[0]), int(canvas[1])
	fx, fy = float(scale[0]), float(scale[1])
	Wc, Hc = max(1, int(round(W / fx))), max(1, int(round(H / fy)))
	t = np.radians(theta_deg)
	R = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
	if mirror:
		R = R @ np.diag([-1.0, 1.0])
	off = np.array([Wc / 2.0, Hc / 2.0]) - R @ cb
	A = np.c_[R, off]
	big = cv2.warpAffine(rgb, A, (Wc, Hc), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
	mk = cv2.warpAffine((alpha > 0).astype(np.float32), A, (Wc, Hc), flags=cv2.INTER_LINEAR,
						borderMode=cv2.BORDER_CONSTANT, borderValue=0) >= 0.5
	sm = cv2.resize(big, (W, H), interpolation=cv2.INTER_AREA)
	msk = cv2.resize(mk.astype(np.float32), (W, H), interpolation=cv2.INTER_AREA) > MASK_FULL
	if erode_px:
		k = 2 * int(erode_px) + 1
		msk = cv2.erode(msk.astype(np.uint8), np.ones((k, k), np.uint8)).astype(bool)
	lab = _lab(sm).astype(np.float64)
	lab[..., 0] -= l_shift
	return dict(lab=lab, mask=msk, rgb=sm, theta_deg=float(theta_deg))


def render_item(rgba: np.ndarray, shape, theta_deg: float, art: CellArt, mm_per_px: float, *, mirror: bool = False) -> dict:
	""":func:`piece_render` of a scanned piece at the art scale, rotated about its body centre.

	The body centre (mean of the 4 corners of ``shape``) is mapped into the crop by the
	offset between the shape's area centroid and the alpha centroid, so the crop frame and
	the contour frame need not be the same (only a translation apart). ``shape`` may be None
	(rotation about the alpha centroid).
	"""
	alpha = rgba[..., 3] if rgba.shape[-1] == 4 else np.full(rgba.shape[:2], 255, np.uint8)
	ctr = _alpha_centroid(alpha)
	if shape is not None:
		ctr = ctr + (body_center_mm(shape) - np.asarray(shape.centroid_mm, float)) / float(mm_per_px)
	return piece_render(rgba, theta_deg, art.canvas, scale=art.scan_scale(mm_per_px), center_px=ctr,
						l_shift=art.l_shift, mirror=mirror)


def de_cell(render: dict, l: int, c: int, art: CellArt, jit: int = JIT) -> dict:
	"""Mean dE (Lab) between a rendered crop and the window of cell ``(l, c)``, minimum over +/- ``jit`` px.

	NCC of L* at the same offset. Art px outside the art do not count (needs >= ``MIN_OVERLAP``
	of the mask inside). ``{'dE': float, 'ncc': float, 'off': (dx, dy)}``; dE = inf if no
	position qualifies or the mask is empty.
	"""
	m = render["mask"]
	S = render["lab"][m]
	H, W = m.shape
	out = dict(dE=float("inf"), ncc=float("nan"), off=(0, 0))
	if len(S) == 0:
		return out
	labp = art._padded()["labp"]
	x0, y0 = art.cell_tl(l, c, (W, H))
	for dy in range(-jit, jit + 1):
		for dx in range(-jit, jit + 1):
			win = labp[y0 + dy:y0 + dy + H, x0 + dx:x0 + dx + W][m]
			ok = ~np.isnan(win[:, 0])
			if ok.sum() < MIN_OVERLAP * len(S):
				continue
			de = float(np.sqrt(((S[ok] - win[ok]) ** 2).sum(1)).mean())
			if de < out["dE"]:
				a, b = S[ok, 0] - S[ok, 0].mean(), win[ok, 0] - win[ok, 0].mean()
				ncc = float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-9))
				out = dict(dE=de, ncc=ncc, off=(dx, dy))
	return out


def cell_scores(render: dict, art: CellArt, jit: int = JIT) -> np.ndarray:
	"""RMS dE of the crop at every cell, minimum over +/- ``jit`` px -> ``(rows, cols)`` (inf where invalid).

	Correlation by ``filter2D`` over the whole art (prototype ``ereal2.cell_scores``); used to
	localise, while the 1-against-1 test uses the mean dE of :func:`de_cell`.
	"""
	P = art._padded()
	M = render["mask"].astype(np.float64)
	S = render["lab"]
	if M.sum() == 0:
		return np.full((art.rows, art.cols), np.inf)
	fk = dict(ddepth=-1, anchor=(0, 0), borderType=cv2.BORDER_CONSTANT)
	t1 = cv2.filter2D(P["V"], kernel=M * (S ** 2).sum(-1), **fk)
	t2 = sum(cv2.filter2D(P["AV"][ch], kernel=M * S[..., ch], **fk) for ch in range(3))
	t3 = cv2.filter2D(P["A2V"], kernel=M, **fk)
	den = cv2.filter2D(P["V"], kernel=M, **fk)
	sc = np.sqrt(np.maximum(t1 - 2 * t2 + t3, 0) / np.maximum(den, 1e-9))
	sc[den < MIN_OVERLAP * M.sum()] = np.inf
	mn = sc.copy()
	for dy in range(-jit, jit + 1):
		for dx in range(-jit, jit + 1):
			if dx or dy:
				mn = np.minimum(mn, np.roll(sc, (-dy, -dx), (0, 1)))
	Lg, Cg = np.mgrid[1:art.rows + 1, 1:art.cols + 1]
	x0, y0 = art.cell_tl(Lg, Cg, (M.shape[1], M.shape[0]))
	return mn[y0, x0]


def piece_mean_lab(rgba: np.ndarray, erode_px: int = 1) -> np.ndarray:
	"""Mean Lab (raw scan, no L* shift) of the piece interior, mask eroded by ``erode_px`` scan px."""
	rgba = np.asarray(rgba)
	m = (rgba[..., 3] > 0).astype(np.uint8) if rgba.shape[-1] == 4 else np.ones(rgba.shape[:2], np.uint8)
	if erode_px:
		k = 2 * int(erode_px) + 1
		e = cv2.erode(m, np.ones((k, k), np.uint8))
		m = e if e.any() else m
	lab = _lab(rgba[..., :3].astype(np.uint8))
	return lab[m > 0].reshape(-1, 3).mean(0).astype(np.float64)


# ---------------------------------------------------------------- a group of pieces with known relative cells
def _flat_code(dirs) -> int:
	return sum(1 << DIRS.index(d) for d in dirs)


def locate_group(items, profile, art: CellArt, *, constraints=None, prior=None, topk: int = 5, mirror: bool = False,
				 refine: bool = True, prior_expect: int = 1, mm_per_px: float | None = None) -> list:
	"""Place a group of pieces with known relative cells (an assembled block) on the grid by colour.

	items: dicts ``{'mean_lab': (3,) raw scan Lab, 'rc': (r, c) local cell (r down, c right),
	'rgba': optional crop, 'theta_deg': optional rotation of the crop to the group's local
	frame, 'shape': optional Shape (body centre for the crop), 'n_flat': optional int,
	'flat_dirs': optional set of local directions of its F sides}``.

	Every placement = global rotation ``rot`` in {0, 90, 180, 270} (clockwise, local frame
	-> board) x cell ``cell0`` of local ``(0, 0)`` (x the E<->W mirror if ``mirror``).
	Hard rules: every item inside the grid; an item with ``flat_dirs`` goes to a cell whose
	border directions are exactly its rotated F directions; an item with only ``n_flat``
	goes to a cell with that many border sides (``constraints={'use_flat': False}``
	disables both; ``constraints['allowed']``: ``(rows, cols)`` bool, cells an item may
	use). Score = median over items of dE(mean_lab - l_shift, cell mean) + ``PRIOR_WEIGHT``
	x fraction of items on cells where ``prior`` (occupancy map ``(rows, cols)`` in
	{1, 0, -1}) is ``1 - prior_expect`` (``prior_expect=1``: the group is an assembled
	section and should sit on occupied cells; ``0``: loose pieces, on empty cells; -1 =
	unknown costs nothing). With ``refine``, the best ``REFINE_TOP`` placements are
	re-scored with :func:`de_cell` of the items that carry ``rgba`` (median over items).

	Returns up to ``topk`` dicts ``{'cell0', 'rot', 'mirror', 'score', 'margin', 'cells':
	{idx: (l, c)}}`` sorted by score (mirror placements lose ties); ``margin`` =
	score of the next placement / score (inf if score is 0). ``[]`` if nothing fits.
	"""
	if not items:
		return []
	cons = dict(constraints or {})
	use_flat = bool(cons.get("use_flat", True))
	allowed = cons.get("allowed")
	rows, cols = profile.rows, profile.cols
	Lg, Cg = np.mgrid[1:rows + 1, 1:cols + 1]
	fcode = np.zeros((rows, cols), np.int64)
	nfl = np.zeros((rows, cols), np.int64)
	for l in range(1, rows + 1):
		for c in range(1, cols + 1):
			fd = profile.flat_directions(l, c)
			fcode[l - 1, c - 1] = _flat_code(fd)
			nfl[l - 1, c - 1] = len(fd)
	shift = np.array([art.l_shift, 0.0, 0.0])
	E = [np.linalg.norm(art.cell_lab_mean - (np.asarray(it["mean_lab"], float) - shift)[None, None, :], axis=-1)
		 for it in items]
	rc = np.array([it["rc"] for it in items], int)
	cands = []
	for mir in ((False, True) if mirror else (False,)):
		for rot in (0, 90, 180, 270):
			dr, dc = _rot_rc(rc[:, 0], rc[:, 1], rot, mir)
			L = Lg[None] + dr[:, None, None]
			C = Cg[None] + dc[:, None, None]
			valid = np.all((L >= 1) & (L <= rows) & (C >= 1) & (C <= cols), axis=0)
			Li, Ci = np.clip(L, 1, rows) - 1, np.clip(C, 1, cols) - 1
			per = np.stack([E[i][Li[i], Ci[i]] for i in range(len(items))])
			for i, it in enumerate(items):
				if use_flat and it.get("flat_dirs") is not None:
					req = _flat_code(rotate_dir(d, rot, mir) for d in it["flat_dirs"])
					valid &= fcode[Li[i], Ci[i]] == req
				elif use_flat and it.get("n_flat") is not None:
					valid &= nfl[Li[i], Ci[i]] == int(it["n_flat"])
				if allowed is not None:
					valid &= np.asarray(allowed, bool)[Li[i], Ci[i]]
			score = _finite_median(per, axis=0)     # members on cells without art do not count
			if prior is not None:
				pr = np.asarray(prior)
				bad = np.mean(np.stack([pr[Li[i], Ci[i]] == (1 - prior_expect) for i in range(len(items))]), axis=0)
				score = score + PRIOR_WEIGHT * bad
			for o in np.flatnonzero(valid.ravel()):
				cands.append((float(score.flat[o]), mir, rot, int(Lg.flat[o]), int(Cg.flat[o])))
	if not cands:
		return []
	cands.sort(key=lambda t: (t[0], t[1]))

	def cells_of(mir, rot, l0, c0):
		dr, dc = _rot_rc(rc[:, 0], rc[:, 1], rot, mir)
		return {i: (int(l0 + dr[i]), int(c0 + dc[i])) for i in range(len(items))}

	with_img = [i for i, it in enumerate(items) if it.get("rgba") is not None]
	if refine and with_img:
		top = cands[:max(REFINE_TOP, topk + 1)]
		mmpp = float(mm_per_px if mm_per_px is not None else profile.mm_per_px())
		ref, cache = [], {}
		for s0, mir, rot, l0, c0 in top:
			cells = cells_of(mir, rot, l0, c0)
			vals = []
			for i, it in enumerate(items):
				if i not in with_img:
					vals.append(float(E[i][cells[i][0] - 1, cells[i][1] - 1]))
					continue
				key = (i, rot, mir)
				if key not in cache:
					cache[key] = render_item(it["rgba"], it.get("shape"), float(it.get("theta_deg") or 0.0) + rot, art, mmpp,
											 mirror=mir)
				vals.append(de_cell(cache[key], cells[i][0], cells[i][1], art)["dE"])
			sc = float(_finite_median(np.asarray(vals, float)))
			if prior is not None:
				pr = np.asarray(prior)
				sc += PRIOR_WEIGHT * float(np.mean([pr[cells[i][0] - 1, cells[i][1] - 1] == (1 - prior_expect) for i in cells]))
			ref.append((sc, mir, rot, l0, c0))
		ref.sort(key=lambda t: (t[0], t[1]))
		cands = ref
	out = []
	for k, (sc, mir, rot, l0, c0) in enumerate(cands[:topk]):
		nxt = cands[k + 1][0] if k + 1 < len(cands) else np.inf
		out.append(dict(cell0=(l0, c0), rot=int(rot), mirror=bool(mir), score=float(sc),
						margin=float(nxt / sc) if sc > 0 else float("inf"), cells=cells_of(mir, rot, l0, c0)))
	return out


# ---------------------------------------------------------------- a pair of loose twins
def _twin_index(profile):
	"""Arrays (rows, cols) of the twin cell (0-based row, col) of every cell; -1 where there is none."""
	Lt = np.full((profile.rows, profile.cols), -1, np.int64)
	Ct = np.full((profile.rows, profile.cols), -1, np.int64)
	for l in range(1, profile.rows + 1):
		for c in range(1, profile.cols + 1):
			t = profile.twin(l, c)
			if t is not None:
				Lt[l - 1, c - 1], Ct[l - 1, c - 1] = t[0] - 1, t[1] - 1
	return Lt, Ct


def pair_locate(a: dict, b: dict, profile, art: CellArt, *, topk: int = 3) -> dict:
	"""Joint localisation of two loose twins by the image (prototype ``ereal2.joint_locate``).

	a, b: ``{'rgba', 'shape' (optional, body centre and axis snapping), 'theta_deg' (board
	pose of A; None -> 4 global rotations), 'phi_deg' (from ``free_dist(A, B)``, aligns B to
	A; read from ``b`` or else ``a``), 'n_flat' (optional, else from the shape)}``. For each
	global rotation, A is rendered at cell X and B (rotation ``theta_A + phi +
	profile.twin_rotation_deg()``) at ``profile.twin(X)``; score(X) = RMS dE(A, X) + RMS
	dE(B, twin(X)), minimum over rotations. Cells are restricted to those with a twin and,
	if A's number of F sides is known, with that many border sides.

	``{'cells': [{'cell', 'score', 'rank', 'rot_deg'}] (top-k, rank 1-based),
	'n_cells_tested', 'score_map': (rows, cols) array}`` or ``{'error': str}``.
	"""
	for name, p in (("a", a), ("b", b)):
		if p.get("rgba") is None:
			return {"error": f"pair_locate: piece {name} has no rgba crop"}
	phi = b.get("phi_deg", a.get("phi_deg"))
	if phi is None:
		return {"error": "pair_locate: phi_deg missing (free_dist of the pair)"}
	mmpp = profile.mm_per_px()
	sa, sb = a.get("shape"), b.get("shape")

	def snapped(shape, th):
		return snap_theta(shape, th)[0] if shape is not None else float(th)

	if a.get("theta_deg") is not None:
		thetas = [snapped(sa, float(a["theta_deg"]))]
	else:
		base = body_beta_deg(sa) if sa is not None else 0.0
		thetas = [base + 90.0 * g for g in range(4)]
	Lt, Ct = _twin_index(profile)
	has_twin = Lt >= 0
	tot = np.full((len(thetas), profile.rows, profile.cols), np.inf)
	for g, ta in enumerate(thetas):
		tb = snapped(sb, ta + float(phi) + profile.twin_rotation_deg())
		sa_map = cell_scores(render_item(a["rgba"], sa, ta, art, mmpp), art)
		sb_map = cell_scores(render_item(b["rgba"], sb, tb, art, mmpp), art)
		tot[g] = np.where(has_twin, sa_map + sb_map[np.maximum(Lt, 0), np.maximum(Ct, 0)], np.inf)
	best = tot.min(0)
	gbest = tot.argmin(0)
	nF = a.get("n_flat", sa.n_flat if (sa is not None and sa.ok) else None)
	comp = has_twin.copy()
	if nF is not None:
		Lg, Cg = np.mgrid[1:profile.rows + 1, 1:profile.cols + 1]
		comp &= np.vectorize(lambda l, c: profile.n_flat_sides(int(l), int(c)))(Lg, Cg) == int(nF)
	bc = np.where(comp, best, np.inf)
	order = np.argsort(bc, axis=None)
	cells = []
	for r, o in enumerate(order[:topk], 1):
		if not np.isfinite(bc.flat[o]):
			break
		l, c = divmod(int(o), profile.cols)
		cells.append(dict(cell=(l + 1, c + 1), score=float(bc.flat[o]), rank=r,
						  rot_deg=float(thetas[int(gbest.flat[o])])))
	return dict(cells=cells, n_cells_tested=int(comp.sum()), score_map=bc)
