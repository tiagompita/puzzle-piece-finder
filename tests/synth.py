"""Synthetic artwork and scanned pieces for the tests of :mod:`src.locate` and :mod:`src.twin`.

The piece contours come from the generator of ``tests/test_shape.py`` (``make_piece``, mm,
nominal 18.5 mm square with round knobs/sockets). The artwork is a grid of solid random
colours (``cell_px`` art px per cell, ``PITCH_MM`` mm per cell). A "scan" of a piece is
the artwork upsampled to 300 dpi, cut by the piece contour placed on its cell in its board
pose, then rotated by ``psi`` (complex convention, clockwise on screen) to its scan pose,
so the rotation that brings the crop back to the board is ``theta = -psi``.
"""

import cv2
import numpy as np

from src.locate import CellArt
from src.profile import PuzzleProfile
from src.shape import analyse, transform_contour
from test_shape import L0, MMPP, make_piece

PITCH_MM = 18.5
CELL_PX = 25
PAD_COLOUR = (128, 128, 128)

ALPES_CAL = {
    "silhueta_silhueta": {"t95": 0.507, "tmax": 0.637},
    "celula_silhueta": {"t95": None, "tmax": None, "offset_mm": 0.48},
    "chord": {"normal_mm": 1.0, "f_adj_mm": 2.0},
    "margin_min": 1.5,
}


def profile(rows=6, cols=8, symmetry=None, p90=15.0, cal=None):
    """Synthetic profile: square cells of ``PITCH_MM``, 300 dpi, the Alpes calibration."""
    return PuzzleProfile(id="syn", grid={"cols": cols, "rows": rows}, cell_mm={"w": PITCH_MM, "h": PITCH_MM},
                         symmetry=symmetry or {"type": "rot180"}, dpi=300,
                         calibration=cal or {k: dict(v) if isinstance(v, dict) else v for k, v in ALPES_CAL.items()},
                         image_zones={"ceu": {"dE_p90": p90}} if p90 is not None else {})


def art_rgb(rows, cols, seed=0, cell_px=CELL_PX, min_sep=60.0):
    """Solid random colours per cell, each at least ``min_sep`` (RGB distance) from the others when possible."""
    rng = np.random.default_rng(seed)
    cols_rgb = []
    while len(cols_rgb) < rows * cols:
        c = rng.integers(20, 236, 3)
        if all(np.linalg.norm(c - q) >= min_sep for q in cols_rgb) or rng.random() < 0.02:
            cols_rgb.append(c)
    A = np.array(cols_rgb, np.uint8).reshape(rows, cols, 3)
    return np.kron(A, np.ones((cell_px, cell_px, 1), np.uint8)).astype(np.uint8)


def make_art(rgb, rows, cols):
    """CellArt without the scanner L* shift (synthetic crops come from the art itself)."""
    return CellArt.from_rgb(rgb, rows, cols, pitch_mm=(PITCH_MM, PITCH_MM), l_shift=0.0)


def body_mm(kinds="TBTB", deltas=(0, 0, 0, 0), radii=(3, 3, 3, 3), noise=0.0, rng=None):
    """Contour (mm) of a piece in its board pose, body centre at the origin."""
    pts = make_piece(kinds, deltas=deltas, radii=radii, noise=noise, rng=rng) * MMPP
    return pts - (np.array([40.0, 30.0]) + L0 / 2)


def scan_piece(art, contour_mm, cell, psi=0.0, pad_mm=4.0):
    """Scan of a piece whose board-pose contour (mm, body centre at 0) sits on ``cell`` of the RGB ``art``.

    Returns ``(contour_px, rgba)`` both in the frame of the crop (scan pose = board pose
    rotated by ``psi``).
    """
    f = (PITCH_MM / CELL_PX) / MMPP          # scan px per art px
    l, c = cell
    ctr_art = np.array([(c - 0.5) * CELL_PX, (l - 0.5) * CELL_PX])
    pts_board = contour_mm / MMPP + ctr_art * f                       # scan px in the upsampled art
    lo = np.floor(pts_board.min(0) - pad_mm / MMPP).astype(int)
    hi = np.ceil(pts_board.max(0) + pad_mm / MMPP).astype(int)
    # upsample only the needed window of the art (pad outside the art)
    H, W = art.shape[:2]
    xs = np.clip((np.arange(lo[0], hi[0]) / f).astype(int), -1, W)
    ys = np.clip((np.arange(lo[1], hi[1]) / f).astype(int), -1, H)
    big = np.full((len(ys), len(xs), 3), PAD_COLOUR, np.uint8)
    okx, oky = (xs >= 0) & (xs < W), (ys >= 0) & (ys < H)
    big[np.ix_(oky, okx)] = art[np.ix_(ys[oky], xs[okx])]
    pts = pts_board - lo
    alpha = np.zeros(big.shape[:2], np.uint8)
    cv2.fillPoly(alpha, [np.round(pts).astype(np.int32).reshape(-1, 1, 2)], 255)
    rgba = np.dstack([big, alpha])
    if psi:
        h, w = alpha.shape
        side = int(np.ceil(np.hypot(h, w))) + 4
        ctr = np.array([w / 2.0, h / 2.0])
        t = np.radians(psi)
        R = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
        off = np.array([side / 2.0, side / 2.0]) - R @ ctr
        A = np.c_[R, off]
        rgb = cv2.warpAffine(np.ascontiguousarray(big), A, (side, side), flags=cv2.INTER_NEAREST,
                             borderMode=cv2.BORDER_CONSTANT, borderValue=PAD_COLOUR)
        pts = pts @ R.T + off
        alpha = np.zeros((side, side), np.uint8)
        cv2.fillPoly(alpha, [np.round(pts).astype(np.int32).reshape(-1, 1, 2)], 255)
        rgba = np.dstack([rgb, alpha])
    return pts, rgba


def twin_board_contour(contour_mm, profile):
    """Board-pose contour of the twin: the piece turned by the profile's twin rotation."""
    return transform_contour(contour_mm, profile.twin_rotation_deg(), center=(0.0, 0.0))


def shape_of(pts_px):
    return analyse(pts_px, MMPP)
