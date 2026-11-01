"""Gera a maquete estática da GUI (docs/gui/) a partir do estado real de um projeto.

Uso: python tools/gui_mock/make_mock.py --project <pasta> --out docs/gui

Escreve board.svg, art.jpg, crops/*.png, groups/*.png, overlays/*.jpg, mock_data.json,
preview.png e substitui os marcadores (<!--BOARD-->..., <script id="mock-data">) nos HTML já
existentes em --out. Idempotente. Unidade do SVG: largura de uma célula (altura da célula =
cell_h / cell_w), para os recortes e fantasmas (em mm) não ficarem deformados.
"""

import argparse
import glob
import json
import os
import re
import shutil
import sys

import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from src.shape import transform_contour  # noqa: E402
from src.state import Project  # noqa: E402

THUMB = 48
MAX_PIECES = 600
PX = 40  # px por unidade (largura de célula) no SVG
PREVIEW_W = 1280
GROUP_CELL = 40

ORIGIN_LABEL = {"gemea": "gémea colocada", "twin": "gémea colocada", "par": "par", "pair": "par",
				"buraco": "buraco", "hole": "buraco", "posicao_conhecida": "posição conhecida",
				"known": "posição conhecida", "borda": "borda", "seccao": "secção"}


def _f(v):
	return f"{v:.3f}".rstrip("0").rstrip(".")


def thumb(img, size=THUMB):
	im = img.copy()
	im.thumbnail((size, size), Image.LANCZOS)
	return im


def save_thumb(pr, pid, out_dir):
	"""Escreve crops/<pid>.png (<= THUMB px); devolve (caminho relativo, tamanho original) ou None."""
	p = pr.piece(pid)
	if not p.crop_path:
		return None
	fp = pr.p(p.crop_path)
	if not os.path.exists(fp):
		return None
	with Image.open(fp) as im:
		im = im.convert("RGBA")
		full = im.size
		t = thumb(im)
	os.makedirs(os.path.join(out_dir, "crops"), exist_ok=True)
	t.quantize(colors=96, method=Image.FASTOCTREE).save(os.path.join(out_dir, "crops", f"{pid}.png"), optimize=True)
	return f"crops/{pid}.png", full


def piece_rot(pr, p):
	"""Rotação (graus, sentido horário no ecrã) da peça no tabuleiro: theta_deg, senão a rot da secção."""
	if p.theta_deg is not None:
		return float(p.theta_deg)
	if p.seccao_id and p.seccao_id in pr.sections:
		return float(pr.sections[p.seccao_id].anchor.get("rot") or 0)
	return 0.0


def contour_path(pts_u, closed=True, step=1):
	pts = pts_u[::step]
	d = "M" + " L".join(f"{_f(x)} {_f(y)}" for x, y in pts)
	return d + (" Z" if closed else "")


def load_fetch(pr, pending):
	fp = pr.p("fetch.json")
	if os.path.exists(fp):
		with open(fp, encoding="utf-8") as f:
			return json.load(f).get("entries", []), False
	ex = []
	for i, (p, tw) in enumerate(pending[:5], 1):
		ex.append({"ordem": i, "origin": "gemea", "piece": None, "lote": None, "n_no_lote": None,
				   "cell": list(tw), "decision": "exemplo", "margin": None, "from": p.id,
				   "reasons": ["exemplo da maquete: gémea pendente de " + p.id]})
	return ex, True


def main(argv=None):
	ap = argparse.ArgumentParser(description=__doc__)
	ap.add_argument("--project", required=True)
	ap.add_argument("--out", default=os.path.join(ROOT, "docs", "gui"))
	a = ap.parse_args(argv)
	out = a.out
	os.makedirs(out, exist_ok=True)
	pr = Project.open(a.project)
	prof = pr.profile
	R, C = prof.rows, prof.cols
	cw, ch = float(prof.cell_mm["w"]), float(prof.cell_mm["h"])
	rowh = ch / cw
	W, H = float(C), R * rowh
	mmpx = prof.mm_per_px()
	twin_rot = prof.twin_rotation_deg()

	def centre(lc):
		return (lc[1] - 0.5, (lc[0] - 0.5) * rowh)

	# ---- arte
	art_ref = None
	art_im = None
	art = prof.art or {}
	afile = os.path.join(ROOT, art["file"]) if art.get("file") else None
	if afile and os.path.exists(afile):
		with Image.open(afile) as im:
			im = im.convert("RGB")
			if art.get("bbox"):
				x, y, w, h = art["bbox"]
				im = im.crop((x, y, x + w, y + h))
			if im.width > 1024:
				im = im.resize((1024, round(im.height * 1024 / im.width)), Image.LANCZOS)
			im.save(os.path.join(out, "art.jpg"), quality=70, optimize=True)
			art_ref = "art.jpg"
			art_im = im.copy()

	# ---- peças
	placed = [p for p in sorted(pr.pieces.values(), key=lambda q: q.id) if p.estado == "colocada" and p.celula]
	loose = pr.loose_pieces()
	for d in ("crops", "groups", "overlays"):
		shutil.rmtree(os.path.join(out, d), ignore_errors=True)
	truncated = max(0, len(placed) - MAX_PIECES)
	thumbs = {}
	for p in placed[:MAX_PIECES] + loose[:MAX_PIECES]:
		t = save_thumb(pr, p.id, out)
		if t:
			thumbs[p.id] = t

	pieces_info, piece_svg = {}, []
	for p in placed[:MAX_PIECES]:
		cx, cy = centre(p.celula)
		info = {"cell": list(p.celula), "lote": p.lote, "n": p.n_no_lote, "estado": p.estado,
				"img": thumbs.get(p.id, [None])[0], "theta": piece_rot(pr, p)}
		pieces_info[p.id] = info
		if p.id not in thumbs or not p.bbox:
			continue
		cpx = pr.contour_px(p.id)
		x0, y0, bw, bh = p.bbox
		bc = np.array([x0 + bw / 2.0, y0 + bh / 2.0])
		mean = cpx.reshape(-1, 2).mean(0) if cpx is not None else bc
		dx, dy = (bc - mean) * mmpx / cw
		wu, hu = bw * mmpx / cw, bh * mmpx / cw
		piece_svg.append(
			f'<g transform="translate({_f(cx)} {_f(cy)}) rotate({_f(info["theta"])})">'
			f'<image href="{info["img"]}" x="{_f(dx - wu / 2)}" y="{_f(dy - hu / 2)}" width="{_f(wu)}" height="{_f(hu)}"/></g>')
	for p in loose[:MAX_PIECES]:
		pieces_info[p.id] = {"cell": None, "lote": p.lote, "n": p.n_no_lote, "estado": p.estado,
							 "img": thumbs.get(p.id, [None])[0], "theta": None}

	# ---- fantasmas
	pending = pr.pending_twins()
	ghosts, ghost_svg, ghost_pts = {}, [], {}
	for p, tw in pending:
		sh = pr.shape(p.id)
		if sh is None or len(sh.c) == 0:
			continue
		c = np.asarray(sh.c, float)
		m = c.mean(0)
		g = transform_contour(c, piece_rot(pr, p) + twin_rot, center=m) - m
		local = [(x / cw, y / cw) for x, y in g]
		tx, ty = centre(tw)
		step = max(1, len(local) // 90)
		absd = contour_path([(x + tx, y + ty) for x, y in local], step=step)
		locd = contour_path(local, step=step)
		key = f"{tw[0]},{tw[1]}"
		ghosts[key] = {"src": p.id, "src_cell": list(p.celula), "dl": locd}
		ghost_pts[key] = [(x + tx, y + ty) for x, y in local]
		ghost_svg.append(f'<path vector-effect="non-scaling-stroke" class="ghost" data-src="{p.id}" data-cell="{key}" d="{absd}"/>')

	# ---- vai buscar
	entries, example = load_fetch(pr, pending)
	if len(entries) < 5:
		have = {tuple(e["cell"]) for e in entries if e.get("cell")}
		for p, tw in pending:
			if len(entries) >= 5:
				break
			if tw not in have:
				entries.append({"origin": "gemea", "piece": None, "cell": list(tw), "decision": "exemplo", "from": p.id,
								"reasons": ["exemplo da maquete: gémea pendente de " + p.id]})
				example = True
	fetch_cells, fetch_out = [], []
	for e in entries:
		cell = e.get("cell")
		if cell:
			fetch_cells.append(tuple(cell))
		pid = e.get("piece")
		reasons = e.get("reasons") or []
		if isinstance(reasons, str):
			reasons = [reasons]
		fetch_out.append({"ordem": e.get("ordem"), "origin": e.get("origin"),
						  "origin_label": ORIGIN_LABEL.get(str(e.get("origin")), str(e.get("origin"))),
						  "piece": pid, "img": thumbs.get(pid, [None])[0] if pid else None,
						  "from": e.get("from"), "from_img": thumbs.get(e.get("from"), [None])[0],
						  "lote": e.get("lote"), "n": e.get("n_no_lote"), "cell": cell,
						  "decision": e.get("decision"), "margin": e.get("margin"), "dE": e.get("dE"),
						  "reasons": [str(r) for r in reasons]})

	# ---- células
	cells, rects, legacy_svg = {}, [], []
	counts = {"colocada": {}, "ocupada_legado": 0, "vazia": 0}
	fcells = set(fetch_cells)
	for (l, c), cell in pr.board.iter_cells():
		st = cell["estado"]
		tw = prof.twin(l, c)
		cells[f"{l},{c}"] = [st, cell["peca_id"], f"{tw[0]},{tw[1]}" if tw else None]
		if st == "colocada":
			counts["colocada"][cell["fonte"]] = counts["colocada"].get(cell["fonte"], 0) + 1
		else:
			counts[st] += 1
		cls = "cell " + st + (" fetch" if (l, c) in fcells else "")
		x, y = c - 1, (l - 1) * rowh
		rects.append(f'<rect class="{cls}" data-cell="{l},{c}" x="{x}" y="{_f(y)}" width="1" height="{_f(rowh)}"/>')
		if st == "ocupada_legado":
			legacy_svg.append(f'<rect x="{x}" y="{_f(y)}" width="1" height="{_f(rowh)}"/>')

	fetch_svg = [f'<rect vector-effect="non-scaling-stroke" class="fetchbox" data-cell="{l},{c}" x="{_f(c - 1 + 0.04)}" '
				 f'y="{_f((l - 1) * rowh + 0.04)}" width="0.92" height="{_f(rowh - 0.08)}"/>' for (l, c) in fetch_cells]

	grid = "".join(f'<path vector-effect="non-scaling-stroke" d="M{i} 0V{_f(H)}"/>' for i in range(C + 1)) + \
		"".join(f'<path vector-effect="non-scaling-stroke" d="M0 {_f(i * rowh)}H{C}"/>' for i in range(R + 1))
	svg = (f'<svg xmlns="http://www.w3.org/2000/svg" id="board" viewBox="0 0 {_f(W)} {_f(H)}" '
		   f'width="{int(W * PX)}" height="{int(H * PX)}" preserveAspectRatio="xMidYMid meet">\n'
		   '<defs><pattern id="hatch" patternUnits="userSpaceOnUse" width="0.22" height="0.22" patternTransform="rotate(45)">'
		   '<line x1="0" y1="0" x2="0" y2="0.22" stroke="#7d8fa6" stroke-width="0.05"/></pattern></defs>\n'
		   f'<rect id="bg" width="{_f(W)}" height="{_f(H)}" fill="#14161a"/>\n')
	if art_ref:
		svg += (f'<image id="layer-art" href="{art_ref}" x="0" y="0" width="{_f(W)}" height="{_f(H)}" '
				f'preserveAspectRatio="none" opacity="0.34"/>\n')
	svg += (f'<g id="layer-grid" fill="none" stroke="#ffffff" stroke-opacity="0.12" stroke-width="1">{grid}</g>\n'
			f'<g id="layer-legacy" fill="url(#hatch)">{"".join(legacy_svg)}</g>\n'
			f'<g id="layer-pieces">{"".join(piece_svg)}</g>\n'
			f'<g id="layer-ghosts" fill="#ffffff" fill-opacity="0.04" stroke="#ffffff" stroke-opacity="0.85" '
			f'stroke-width="1.5">{"".join(ghost_svg)}</g>\n'
			f'<g id="layer-fetch" fill="#ffb000" fill-opacity="0.10" stroke="#ffb000" stroke-width="2.5">{"".join(fetch_svg)}</g>\n'
			f'<g id="layer-cells" fill="transparent">{"".join(rects)}</g>\n</svg>\n')
	with open(os.path.join(out, "board.svg"), "w", encoding="utf-8", newline="\n") as f:
		f.write(svg)

	# ---- lotes + overlays
	lotes = {}
	for p in pr.pieces.values():
		key = p.lote if p.lote is not None else 0
		L = lotes.setdefault(key, {"lote": p.lote, "n": 0, "colocadas": 0, "pendentes": 0, "scans": set()})
		L["n"] += 1
		L["colocadas"] += p.estado == "colocada"
		L["pendentes"] += p.estado in ("solta", "emparelhada", "posicao_conhecida")
		L["scans"].add(p.scan_id)
	lotes_out = []
	os.makedirs(os.path.join(out, "overlays"), exist_ok=True)
	for k in sorted(lotes):
		L = lotes[k]
		ov = None
		for sid in sorted(L["scans"]):
			fp = pr.p("overlays", f"{sid}.jpg")
			if os.path.exists(fp):
				with Image.open(fp) as im:
					im = im.convert("RGB")
					im.thumbnail((900, 900), Image.LANCZOS)
					im.save(os.path.join(out, "overlays", f"{sid}.jpg"), quality=70, optimize=True)
				ov = f"overlays/{sid}.jpg"
				break
		lotes_out.append({"lote": L["lote"], "n": L["n"], "colocadas": L["colocadas"], "pendentes": L["pendentes"],
						  "scans": sorted(L["scans"]), "overlay": ov})

	# ---- grupos soltos
	groups = []
	os.makedirs(os.path.join(out, "groups"), exist_ok=True)
	for s in sorted(pr.sections.values(), key=lambda q: q.id):
		if s.anchor.get("anchored") or not s.cells_local:
			continue
		rr = [rc[0] for rc in s.cells_local.values()]
		cc = [rc[1] for rc in s.cells_local.values()]
		r0, c0 = min(rr), min(cc)
		cvs = Image.new("RGBA", ((max(cc) - c0 + 1) * GROUP_CELL, (max(rr) - r0 + 1) * GROUP_CELL), (28, 31, 36, 255))
		for pid, rc in s.cells_local.items():
			cp = pr.piece(pid).crop_path
			fp = pr.p(cp) if cp else None
			if fp and os.path.exists(fp):
				with Image.open(fp) as im:
					t = thumb(im.convert("RGBA"), GROUP_CELL - 2)
				cvs.alpha_composite(t, ((rc[1] - c0) * GROUP_CELL + (GROUP_CELL - t.width) // 2,
										(rc[0] - r0) * GROUP_CELL + (GROUP_CELL - t.height) // 2))
		cvs.convert("RGB").save(os.path.join(out, "groups", f"{s.id}.png"), optimize=True)
		groups.append({"id": s.id, "kind": s.kind, "n": len(s.cells_local), "img": f"groups/{s.id}.png",
					   "candidates": [{"cell0": c.get("cell0"), "rot": c.get("rot"), "mirror": c.get("mirror"),
									   "score": c.get("score"), "margin": c.get("margin")} for c in (s.candidates or [])[:3]]})

	# ---- progresso
	n_col = sum(counts["colocada"].values())
	progress = {"total": prof.cell_count(), "colocadas": n_col, "por_fonte": counts["colocada"],
				"legado": counts["ocupada_legado"], "vazias": counts["vazia"],
				"ocupadas": n_col + counts["ocupada_legado"], "soltas": len(loose),
				"gemeas_pendentes": len(pending), "buracos": len(pr.holes())}
	data = {"maquete": True, "example_fetch": example,
			"grid": {"rows": R, "cols": C}, "board": {"w": W, "h": H, "rowh": rowh},
			"nota_miniaturas": (f"limitado a {MAX_PIECES} peças colocadas ({truncated} sem recorte)" if truncated else ""),
			"progress": progress, "cells": cells, "pieces": pieces_info, "ghosts": ghosts,
			"fetch": fetch_out, "lotes": lotes_out, "grupos": groups}
	with open(os.path.join(out, "mock_data.json"), "w", encoding="utf-8", newline="\n") as f:
		json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

	# ---- preview.png
	S = PREVIEW_W / W
	pw, ph = PREVIEW_W, int(round(H * S))
	base = Image.new("RGB", (pw, ph), (20, 22, 26))
	if art_im is not None:
		base = Image.blend(base, art_im.resize((pw, ph), Image.LANCZOS), 0.34)
	base = base.convert("RGBA")
	ov = Image.new("RGBA", base.size, (0, 0, 0, 0))
	dr = ImageDraw.Draw(ov)
	for i in range(C + 1):
		dr.line([(i * S, 0), (i * S, ph)], fill=(255, 255, 255, 30))
	for i in range(R + 1):
		dr.line([(0, i * rowh * S), (pw, i * rowh * S)], fill=(255, 255, 255, 30))
	for (l, c), cell in pr.board.iter_cells():
		if cell["estado"] == "ocupada_legado":
			x0, y0, x1, y1 = (c - 1) * S, (l - 1) * rowh * S, c * S, l * rowh * S
			dr.rectangle([x0, y0, x1, y1], fill=(125, 143, 166, 40))
			wcell = x1 - x0
			for j in np.arange(0, 2 * wcell, max(3.0, wcell / 3)):
				# diagonais a 45 graus recortadas à célula
				xa, ya = x0 + j, y0
				xb, yb = x0, y0 + j
				if xa > x1:
					ya, xa = ya + (xa - x1), x1
				if yb > y1:
					xb, yb = xb + (yb - y1), y1
				dr.line([(xa, ya), (xb, yb)], fill=(125, 143, 166, 170))
	base.alpha_composite(ov)
	for p in placed[:MAX_PIECES]:
		if p.id not in thumbs or not p.bbox:
			continue
		with Image.open(os.path.join(out, thumbs[p.id][0])) as t:
			t = t.convert("RGBA")
		bw, bh = p.bbox[2], p.bbox[3]
		cpx = pr.contour_px(p.id)
		bc = np.array([p.bbox[0] + bw / 2.0, p.bbox[1] + bh / 2.0])
		mean = cpx.reshape(-1, 2).mean(0) if cpx is not None else bc
		d = (bc - mean) * mmpx / cw
		wpx, hpx = max(2, int(bw * mmpx / cw * S)), max(2, int(bh * mmpx / cw * S))
		t = t.resize((wpx, hpx), Image.LANCZOS)
		pad = int(np.hypot(wpx, hpx)) + 4
		cv = Image.new("RGBA", (2 * pad, 2 * pad), (0, 0, 0, 0))
		cv.alpha_composite(t, (int(pad + d[0] * S - wpx / 2), int(pad + d[1] * S - hpx / 2)))
		cv = cv.rotate(-piece_rot(pr, p), resample=Image.BICUBIC)
		cx, cy = centre(p.celula)
		base.paste(cv, (int(cx * S) - pad, int(cy * S) - pad), cv)
	q = base.convert("RGB").quantize(colors=96, method=Image.MEDIANCUT, dither=Image.Dither.NONE)
	pal = q.getpalette()[:96 * 3] + [255, 176, 0, 255, 255, 255]  # índices 96 = âmbar, 97 = branco
	q.putpalette(pal)
	dr = ImageDraw.Draw(q)
	for key, pts in ghost_pts.items():
		pp = [(x * S, y * S) for x, y in pts]
		dr.line(pp + [pp[0]], fill=97, width=2)
	for (l, c) in fetch_cells:
		dr.rectangle([(c - 1) * S + 1, (l - 1) * rowh * S + 1, c * S - 1, l * rowh * S - 1], outline=96, width=3)
	q.save(os.path.join(out, "preview.png"), optimize=True)

	# ---- substituição nos HTML
	def blob_for(keys):
		sub = {k: v for k, v in data.items() if not keys or k in keys}
		return json.dumps(sub, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

	for fp in glob.glob(os.path.join(out, "*.html")):
		with open(fp, encoding="utf-8") as f:
			txt = f.read()
		new = re.sub(r'(<script id="mock-data" type="application/json"(?: data-keys="([^"]*)")?>).*?(</script>)',
					 lambda m: m.group(1) + blob_for([k for k in (m.group(2) or "").split(",") if k]) + m.group(3),
					 txt, flags=re.S)
		new = re.sub(r"(<!--BOARD-->).*?(<!--/BOARD-->)", lambda m: m.group(1) + svg + m.group(2), new, flags=re.S)
		if new != txt:
			with open(fp, "w", encoding="utf-8", newline="\n") as f:
				f.write(new)

	tot = sum(os.path.getsize(os.path.join(dp, fn)) for dp, _, fns in os.walk(out) for fn in fns)
	print(f"{out}: {tot / 1e6:.2f} MB; colocadas {n_col} (recortes {len(piece_svg)}), legado {counts['ocupada_legado']}, "
		  f"fantasmas {len(ghost_svg)}, vai buscar {len(fetch_out)}{' (exemplo)' if example else ''}, grupos {len(groups)}")


if __name__ == "__main__":
	main()
