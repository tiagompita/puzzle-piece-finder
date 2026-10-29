import sys, os, time, json
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont
REPO = "C:/Users/Tiago/Desktop/puzzle-piece-finder"
sys.path.insert(0, REPO)
from src.matching import multi_scale_template_match
S = os.environ.get("PPF_SCRATCH", "scratch")
OUT = REPO + "/docs/diagnostico/matching"
ORIG = REPO + "/images/puzzles/PuzzleOriginal.jpeg"
CLEAN = REPO + "/images/puzzles/1186441_1.jpg"
os.makedirs(OUT, exist_ok=True)

def log(*a):
	print(*a, flush=True)

def load_seg(name):
	return np.load(f"{S}/seg/scan_{name}.npz", allow_pickle=True)

def detect_artwork(arr):
	"""Largest non-white rectangle in the box photo (downscaled analysis)."""
	h, w = arr.shape[:2]
	f = 1000.0 / w
	sm = cv2.resize(arr, (int(w * f), int(h * f)), interpolation=cv2.INTER_AREA)
	hsv = cv2.cvtColor(sm, cv2.COLOR_RGB2HSV)
	white = (hsv[:, :, 1] < 40) & (hsv[:, :, 2] > 170)
	fg = (~white).astype(np.uint8) * 255
	fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
	n, lab, stats, _ = cv2.connectedComponentsWithStats(fg)
	i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
	ys, xs = np.where(lab == i)
	# robust bbox: 1st/99th percentile row/col coverage
	rows = (lab == i).mean(axis=1); cols = (lab == i).mean(axis=0)
	r = np.where(rows > 0.5)[0]; c = np.where(cols > 0.5)[0]
	x0, x1, y0, y1 = c[0], c[-1], r[0], r[-1]
	return tuple(int(round(v / f)) for v in (x0, y0, x1, y1))

def match(ref_pil, piece_rgb, mask, edges=None, num_pieces=3000):
	t = time.time()
	res = multi_scale_template_match(ref_pil, Image.fromarray(piece_rgb), num_pieces=num_pieces,
		piece_mask=mask, use_downscale=True, use_texture=True, piece_edges=edges)
	return res, time.time() - t

def centre(pos, size):
	return (pos[0] + size[0] / 2.0, pos[1] + size[1] / 2.0)

def cands_centres(res):
	return [centre(c["position"], c["size"]) for c in res.get("candidates", [])]

def fit_h(im, height):
	w, h = im.size
	return im.resize((max(1, int(round(w * height / h))), height), Image.Resampling.LANCZOS)

def crop_box(ref_pil, cx, cy, side):
	W, H = ref_pil.size
	x0 = int(max(0, cx - side / 2)); y0 = int(max(0, cy - side / 2))
	x1 = int(min(W, cx + side / 2)); y1 = int(min(H, cy + side / 2))
	return ref_pil.crop((x0, y0, max(x0 + 1, x1), max(y0 + 1, y1)))

def font(sz=18):
	try:
		return ImageFont.truetype("arial.ttf", sz)
	except Exception:
		return ImageFont.load_default()

def montage(rows, labels, header, height=160, path=None):
	"""rows: list of lists of PIL images; labels: list of str per row."""
	fnt = font(16)
	rimgs = []
	for ims, lab in zip(rows, labels):
		ims = [fit_h(i.convert("RGB"), height) for i in ims]
		w = sum(i.width for i in ims) + 10 * (len(ims) + 1)
		can = Image.new("RGB", (max(w, 900), height + 28), (25, 25, 25))
		d = ImageDraw.Draw(can); d.text((8, 4), lab, fill=(255, 255, 0), font=fnt)
		x = 10
		for i in ims:
			can.paste(i, (x, 26)); x += i.width + 10
		rimgs.append(can)
	W = max(r.width for r in rimgs)
	tot = Image.new("RGB", (W, 34 + sum(r.height + 4 for r in rimgs)), (0, 0, 0))
	ImageDraw.Draw(tot).text((8, 8), header, fill=(255, 255, 255), font=font(18))
	y = 34
	for r in rimgs:
		tot.paste(r, (0, y)); y += r.height + 4
	if path:
		tot.save(path)
	return tot
