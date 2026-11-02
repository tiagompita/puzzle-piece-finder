"""Figure of BUG 4 (art under the board): placed pieces vs the art, before (bbox) / after (``art.registration``).

	PPF_SCRATCH=... python tools/diagnostico/arte/artreg_figura.py [--project projects/alpes] [--out docs/diagnostico/arte/artreg_antes_depois.jpg]

Per zone, three panels at the same scale: the placed pieces only (corner registration, no image) |
pieces 50/50 over the art rectified with the bbox | the same with the registration. Misalignment
shows as a double image (ghost). Zones: grass BE (rows 42-47, cols 1-8), sky (rows 1-6, cols 28-50),
right column (rows 1-20, cols 60-64). Reads the project, writes only the figure.
"""

import argparse
import os
import sys

import cv2
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO)

from src import render  # noqa: E402
from src.locate import rectify_art  # noqa: E402
from src.profile import PuzzleProfile  # noqa: E402
from src.state import Project  # noqa: E402

ZONES = [("relva BE (filas 42-47, col. 1-8)", (42, 1, 47, 8), 48),
		 ("céu (filas 1-6, col. 28-50)", (1, 28, 6, 50), 30),
		 ("coluna direita (filas 1-20, col. 60-64)", (1, 60, 20, 64), 30)]


def label(img, text):
	out = np.vstack([np.full((22, img.shape[1], 3), 255, np.uint8), img])
	cv2.putText(out, text, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
	return out


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("--project", default=os.path.join(REPO, "projects", "alpes"))
	ap.add_argument("--out", default=os.path.join(REPO, "docs", "diagnostico", "arte", "artreg_antes_depois.jpg"))
	args = ap.parse_args()
	pr = Project.open(args.project)
	prof = pr.profile
	prior = dict(prof.art)
	prior.pop("registration", None)
	M0 = PuzzleProfile.from_dict({**prof.to_dict(), "art": prior}).art_matrix()
	M1 = prof.art_matrix()
	if "registration" not in prof.art:
		raise SystemExit("puzzle.json sem art.registration")
	im = cv2.imdecode(np.fromfile(os.path.join(REPO, prof.art["file"]), np.uint8), cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
	cell = (float(prof.cell_mm["w"]), float(prof.cell_mm["h"]))
	bb = prof.art.get("bbox")
	a0, v0 = rectify_art(im, M0, prof.rows, prof.cols, cell, content_bbox=bb, return_valid=True)
	a1, v1 = rectify_art(im, M1, prof.rows, prof.cols, cell, content_bbox=bb, return_valid=True)
	a0[~v0] = (40, 40, 40)     # no art in the file there: base grey, as render._art_rgb
	a1[~v1] = (40, 40, 40)
	pl = {}
	for pid in render.placed_ids(pr):
		r = render.register_piece(pr, pid, art=None, image=False)
		if "error" not in r:
			pl[pid] = r
	blocks = []
	for name, reg, ppc in ZONES:
		pcs = render.compose_board(pr, ppc, region=reg, layers=("pieces",), placements=pl)
		b0 = render.compose_board(pr, ppc, region=reg, layers=("art",), art_alpha=1.0, art_bgr=a0)
		b1 = render.compose_board(pr, ppc, region=reg, layers=("art",), art_alpha=1.0, art_bgr=a1)
		m0 = cv2.addWeighted(pcs, 0.5, b0, 0.5, 0)
		m1 = cv2.addWeighted(pcs, 0.5, b1, 0.5, 0)
		sep = np.full((pcs.shape[0], 6, 3), 255, np.uint8)
		row = np.hstack([pcs, sep, b0, sep, m0, sep, b1, sep, m1])
		blocks.append(label(row, f"{name}: pecas | arte bbox | 50/50 ANTES | arte registada | 50/50 DEPOIS"))
	W = max(b.shape[1] for b in blocks)
	blocks = [np.hstack([b, np.full((b.shape[0], W - b.shape[1], 3), 255, np.uint8)]) for b in blocks]
	fig = np.vstack(blocks)
	os.makedirs(os.path.dirname(args.out), exist_ok=True)
	q = 85
	while True:
		ok, buf = cv2.imencode(".jpg", fig, [cv2.IMWRITE_JPEG_QUALITY, q])
		if len(buf) <= 500_000 or q <= 40:
			break
		q -= 5
	buf.tofile(args.out)
	print(f"{args.out}: {fig.shape[1]}x{fig.shape[0]}, {len(buf) // 1024} KB (q={q})")


if __name__ == "__main__":
	main()
