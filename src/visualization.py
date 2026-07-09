"""Result visualization utilities for the Puzzle Piece Finder.

Pure drawing helpers (plus a thin save wrapper) that render match
results onto a copy of the puzzle image using PIL. The original
project TODO asked for "a red dot where the piece probably goes";
this module fulfils that: for each matched piece it draws a filled
red dot at the piece's probable centre, together with a small label
(the piece id and, optionally, the similarity score).

Following the project convention, the drawing logic is kept pure
(no file I/O) in :func:`annotate_results`, and the only function that
touches the filesystem is :func:`save_annotated_image`.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence
from PIL import Image, ImageDraw, ImageFont


_RED = (255, 0, 0)
_WHITE = (255, 255, 255)


def _load_font(size: int) -> ImageFont.ImageFont:
	"""Return a TrueType font at ``size`` px, falling back to PIL's default.

	Tries a couple of common font files so the labels look consistent
	across platforms; if none are available the bitmap default is used.
	"""
	for name in ("arial.ttf", "DejaVuSans.ttf"):
		try:
			return ImageFont.truetype(name, size)
		except Exception:
			continue
	return ImageFont.load_default()


def _marker_radius(img_w: int, img_h: int, radius: Optional[int] = None) -> int:
	"""Compute a marker radius that scales with the image size.

	If ``radius`` is given it is used as-is (clamped to ``>= 1``); otherwise
	the radius is derived from the smaller image dimension so the dot stays
	visible on both small pieces and very large puzzle images.
	"""
	if radius is not None:
		return max(1, int(radius))
	return max(4, int(min(img_w, img_h) * 0.012))


def _result_center(result: Mapping[str, Any]) -> tuple[int, int]:
	"""Return the probable centre of a match result.

	The centre is ``position + size / 2``. Missing ``position``/``size``
	keys are tolerated and treated as ``(0, 0)``.
	"""
	pos = result.get("position") or (0, 0)
	size = result.get("size") or (0, 0)
	x, y = pos
	w, h = size
	return int(x + w / 2), int(y + h / 2)


def _draw_label(
	draw: ImageDraw.ImageDraw,
	text: str,
	x: int,
	y: int,
	font: ImageFont.ImageFont,
	img_w: int,
	img_h: int,
) -> None:
	"""Draw ``text`` at ``(x, y)`` with a white background box for legibility.

	The label is nudged so it stays within the image bounds.
	"""
	try:
		bbox = draw.textbbox((0, 0), text, font=font)
		tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
	except Exception:  # pragma: no cover - very old PIL without textbbox
		tw, th = draw.textsize(text, font=font)

	x = max(0, min(x, img_w - tw - 2))
	y = max(0, min(y, img_h - th - 2))
	pad = 2
	draw.rectangle([x - pad, y - pad, x + tw + pad, y + th + pad], fill=_WHITE)
	draw.text((x, y), text, fill=_RED, font=font)


def annotate_results(
	puzzle_img: Image.Image,
	results: Sequence[Mapping[str, Any]],
	radius: Optional[int] = None,
	show_similarity: bool = True,
	font_size: Optional[int] = None,
) -> Image.Image:
	"""Return a NEW annotated RGB copy of ``puzzle_img``.

	For every result a filled red dot is drawn at the piece's probable
	centre (``position + size / 2``) plus a small label with the piece id
	and, optionally, the similarity score.

	Parameters
	----------
	puzzle_img:
		The puzzle image to annotate. It is never modified in place; a
		fresh RGB copy is returned.
	results:
		An iterable of result dicts of the shape used by the GUI, i.e.
		``{'piece_id', 'position': (x, y), 'size': (w, h), 'similarity', ...}``.
		Optional keys may be missing and an empty sequence is handled
		gracefully (an unmodified RGB copy is returned).
	radius:
		Marker radius in pixels. When ``None`` it scales with the image size.
	show_similarity:
		When ``True`` (default) the similarity (if present) is appended to
		each label as a percentage.
	font_size:
		Label font size in pixels. When ``None`` it scales with the image size.
	"""
	annotated = puzzle_img.convert("RGB").copy()
	if not results:
		return annotated

	img_w, img_h = annotated.size
	draw = ImageDraw.Draw(annotated)
	r = _marker_radius(img_w, img_h, radius)
	fsize = int(font_size) if font_size else max(12, int(min(img_w, img_h) * 0.03))
	font = _load_font(fsize)
	outline_w = max(1, r // 4)

	for result in results:
		cx, cy = _result_center(result)

		# Filled red dot at the probable centre (white outline for contrast).
		draw.ellipse(
			[cx - r, cy - r, cx + r, cy + r],
			fill=_RED,
			outline=_WHITE,
			width=outline_w,
		)

		# Label: piece id, optionally with the similarity percentage.
		piece_id = result.get("piece_id", "?")
		label = str(piece_id)
		sim = result.get("similarity")
		if show_similarity and sim is not None:
			try:
				label = f"{piece_id} ({float(sim):.0%})"
			except (TypeError, ValueError):
				label = str(piece_id)

		_draw_label(draw, label, cx + r + 3, cy - r, font, img_w, img_h)

	return annotated


def save_annotated_image(
	puzzle_img: Image.Image,
	results: Sequence[Mapping[str, Any]],
	path: str,
	radius: Optional[int] = None,
	show_similarity: bool = True,
	font_size: Optional[int] = None,
) -> str:
	"""Render the red-dot annotation and write it to ``path``.

	This is the only function in the module that performs I/O; it delegates
	all drawing to :func:`annotate_results`. Returns the path written.
	"""
	annotated = annotate_results(
		puzzle_img,
		results,
		radius=radius,
		show_similarity=show_similarity,
		font_size=font_size,
	)
	annotated.save(path)
	return path


__all__ = [
	"annotate_results",
	"save_annotated_image",
]
