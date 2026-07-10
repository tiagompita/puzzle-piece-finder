"""Feature extraction utilities (pure functions, no I/O)."""

from __future__ import annotations
from typing import Tuple
from PIL import Image
import math


def get_image_size(img: Image.Image) -> tuple[int, int]:
	return img.size


def compute_area(size: tuple[int, int]) -> int:
	w, h = size
	return w * h


def dominant_color(img: Image.Image) -> tuple[int, int, int]:
	"""Approximate dominant color by downscaling and taking most common pixel.

	Simple + fast approach (no k-means yet)."""
	small = img.convert("RGB").resize((50, 50))
	pixels = list(small.getdata())
	freq = {}
	for p in pixels:
		freq[p] = freq.get(p, 0) + 1
	return max(freq.items(), key=lambda kv: kv[1])[0]


def color_distance(c1: tuple[int, int, int], c2: tuple[int, int, int]) -> float:
	return math.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2)))


def estimate_scale(puzzle_width_px: int, real_width_cm: float) -> float:
	"""Return pixels-per-cm scale."""
	if real_width_cm <= 0:
		raise ValueError("real_width_cm must be > 0")
	return puzzle_width_px / real_width_cm


__all__ = [
	"get_image_size",
	"compute_area",
	"dominant_color",
	"color_distance",
	"estimate_scale",
]

