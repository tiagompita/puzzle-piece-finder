"""Correção de orientações e âncoras (2026-11-07, ORIENTACOES-2026-11-07.md): medição só de leitura.

Uso, da raiz (sempre com uma CÓPIA de ``projects/alpes`` se a seguir se vai alterar o projeto)::

    python tools/diagnostico/reports/orientacoes.py measure <proj> <saida.json> P0083 P0333 ...
    python tools/diagnostico/reports/orientacoes.py view <proj> <saida.png> P0083 P0333 ...
    python tools/diagnostico/reports/orientacoes.py fig <antes.png> <depois.png> <saida.jpg> "P0083 (44,60)" "P0333 (6,22)"
    python tools/diagnostico/reports/orientacoes.py block <proj> <saida.json>

Pose de todas as peças: ``render.register_piece(image=False)`` (a pose da GUI; o ``k`` dos cantos dá o lado
virado para cada direção). Por peça e direção N/E/S/W: vizinha montada (tipo dos dois lados, ``legacy.side_compat``:
T<->B, RMS do perfil, |dCorda|; folga com sinal de ``render.seam_gaps``) ou borda (o lado tem de ser F). Imagem:
``locate.de_cell`` (dE, NCC de L*) com a peça desenhada na pose atual e nas outras 3 rotações (+90, 180, -90 no
sentido dos ponteiros no ecrã, como ``theta_deg``).

``block``: bloco (1..3, 32..33) contra o gémeo (45..47, 32..33): ``shape.free_dist`` por par gémeo (o mínimo
de ``free_dist`` já percorre as rotações relativas; aqui mede-se também a distância contra as outras 5 peças
do bloco gémeo), classes, e os lados de cada peça contra as vizinhas montadas.
"""

import json
import os
import sys

import cv2
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO)

from src import render as R  # noqa: E402
from src import shape as SH  # noqa: E402
from src.legacy import side_compat  # noqa: E402
from src.locate import CellArt, render_item, de_cell  # noqa: E402
from src.state import Project  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import triagem_r3 as T3  # noqa: E402

OPP = {"N": "S", "S": "N", "E": "W", "W": "E"}
STEP = {"N": (-1, 0), "E": (0, 1), "S": (1, 0), "W": (0, -1)}


def _f(v, n=2):
	return None if v is None or not np.isfinite(v) else round(float(v), n)


def mounted(pr):
	return {tuple(p.celula): pid for pid, p in pr.pieces.items() if p.estado == "colocada" and p.celula is not None}


class Poses:
	"""Pose sem imagem (a da GUI) registada a pedido."""

	def __init__(self, pr):
		self.pr, self.pl, self.cache = pr, {}, {}

	def get(self, pid):
		if pid not in self.pl:
			e = R.register_piece(self.pr, pid, art=None, image=False, _cache=self.cache)
			self.pl[pid] = None if "error" in e else e
		return self.pl[pid]

	def k(self, pid):
		e = self.get(pid)
		c = (e or {}).get("corner") or {}
		return None if c.get("k") is None else int(c["k"])


def side_facing(pr, poses, pid, d):
	"""Lado de ``pid`` virado para ``d`` (objeto ``Side``) ou None."""
	sh = pr.shape(pid)
	k = poses.k(pid)
	if sh is None or not sh.ok or len(sh.sides) != 4 or k is None:
		return None
	return sh.sides[(R.DIRS.index(d) - k) % 4]


def sides_report(pr, poses, pid, by_cell=None):
	"""Por direção: vizinha (tipos, ok, why, rms, dl, folga) ou borda (lado F?)."""
	by_cell = by_cell if by_cell is not None else mounted(pr)
	cell = tuple(pr.piece(pid).celula)
	flat = pr.profile.flat_directions(*cell)
	out = {}
	pl = {pid: poses.get(pid)}
	for d, (dl, dc) in STEP.items():
		sa = side_facing(pr, poses, pid, d)
		q = by_cell.get((cell[0] + dl, cell[1] + dc))
		if d in flat:
			out[d] = dict(kind="borda", side=None if sa is None else sa.kind, ok=None if sa is None else sa.kind == "F")
			continue
		if q is None or q == pid:
			out[d] = dict(kind="livre", side=None if sa is None else sa.kind)
			continue
		sb = side_facing(pr, poses, q, OPP[d])
		pl[q] = poses.get(q)
		if sa is None or sb is None:
			out[d] = dict(kind="vizinha", piece=q, ok=None, why="sem cantos")
			continue
		r = side_compat(sa, sb)
		out[d] = dict(kind="vizinha", piece=q, kinds=f"{sa.kind}<->{sb.kind}", ok=bool(r["ok"]), why=r["why"],
					  rms=_f(r["rms"]), dl=_f(r["dl"]))
	pl = {k: v for k, v in pl.items() if v is not None}
	for s in R.seam_gaps(pr, pl):
		if pid not in (s["a"], s["b"]):
			continue
		other = s["b"] if s["a"] == pid else s["a"]
		for d, v in out.items():
			if v.get("piece") == other:
				v["gap_mm"] = _f(s["gap_mm"])
	# continuidade da imagem na junta (dE Lab mediano das faixas de 0,3-1,3 mm de cada lado, triagem_r3)
	shapes = {q: pr.shape(q) for q in pl}
	crops = T3.Crops(pr)
	for s in T3.seam_list(pr, pl, shapes):
		if pid not in (s["a"], s["b"]):
			continue
		other = s["b"] if s["a"] == pid else s["a"]
		im = T3.seam_image(crops, pr, pl, shapes, s)
		for d, v in out.items():
			if v.get("piece") == other:
				v["de_seam"] = _f(im["de_med"], 1)
	return out


def image_report(pr, poses, art, pid):
	"""``de_cell`` na pose atual (rot 0) e +90 / 180 / -90."""
	p = pr.piece(pid)
	e = poses.get(pid)
	rgba = pr.crop_rgba(pid)
	mmpp = R._scan_mmpp(pr, p.scan_id)
	rows = []
	for m, lab in ((0, 0), (1, 90), (2, 180), (3, -90)):
		r = render_item(rgba, pr.shape(pid), e["theta_deg"] + 90 * m, art, mmpp)
		dd = de_cell(r, *p.celula, art)
		rows.append(dict(rot=lab, dE=_f(dd["dE"]), ncc=_f(dd["ncc"])))
	return dict(theta_deg=_f(e["theta_deg"]), k=poses.k(pid), rots=rows,
				best_ncc_rot=max(rows, key=lambda r: -9 if r["ncc"] is None else r["ncc"])["rot"])


def measure(proj, out, pids):
	pr = Project.open(proj)
	poses = Poses(pr)
	art = CellArt.load(pr.profile, REPO)
	by_cell = mounted(pr)
	res = {}
	for pid in pids:
		p = pr.piece(pid)
		if p.celula is None or p.estado != "colocada":
			res[pid] = dict(estado=p.estado, cell=None)
			continue
		sd = sides_report(pr, poses, pid, by_cell)
		res[pid] = dict(estado=p.estado, cell=list(p.celula), seccao=p.seccao_id, cls=pr.shape(pid).cls, sides=sd,
						image=image_report(pr, poses, art, pid))
		n_nb = sum(v["kind"] == "vizinha" for v in sd.values())
		n_ok = sum(v["kind"] == "vizinha" and v.get("ok") for v in sd.values())
		n_tb = sum(v["kind"] == "vizinha" and v.get("why") not in ("kind", "F", "sem cantos") for v in sd.values())
		n_f = sum(v["kind"] == "borda" for v in sd.values())
		n_fok = sum(v["kind"] == "borda" and v.get("ok") for v in sd.values())
		res[pid].update(n_vizinhas=n_nb, n_tb=n_tb, n_ok=n_ok, n_borda=n_f, n_borda_ok=n_fok)
		im = res[pid]["image"]
		print(f"{pid} {tuple(p.celula)} cls {res[pid]['cls']} theta {im['theta_deg']} k {im['k']}: "
			  f"T<->B {n_tb}/{n_nb} (passam {n_ok}), F {n_fok}/{n_f}; NCC máx a {im['best_ncc_rot']}")
		for d, v in sd.items():
			print(f"   {d}: {v}")
		print("   imagem: " + "; ".join(f"{r['rot']:+d}: dE {r['dE']} NCC {r['ncc']}" for r in im["rots"]))
	with open(out, "w", encoding="utf-8") as f:
		json.dump(res, f, ensure_ascii=False, indent=1)


def view(proj, out, pids):
	"""Vistas 3x3 a 300 dpi lado a lado (arte a 0.34 + peças + grelha), com o contorno da peça em vermelho."""
	pr = Project.open(proj)
	poses = Poses(pr)
	prof = pr.profile
	ppc = float(prof.cell_mm["w"]) / (25.4 / 300.0)
	ppm = ppc / float(prof.cell_mm["w"])
	tiles = []
	for pid in pids:
		l, c = pr.piece(pid).celula
		reg = (max(1, l - 1), max(1, c - 1), min(prof.rows, l + 1), min(prof.cols, c + 1))
		pl = {}
		for q_cell, q in mounted(pr).items():
			if reg[0] <= q_cell[0] <= reg[2] and reg[1] <= q_cell[1] <= reg[3] and poses.get(q) is not None:
				pl[q] = poses.get(q)
		img = R.compose_board(pr, ppc, region=reg, layers=("art", "pieces", "grid"), placements=pl)
		ox, oy = (reg[1] - 1) * float(prof.cell_mm["w"]) * ppm, (reg[0] - 1) * float(prof.cell_mm["h"]) * ppm
		sh = pr.shape(pid)
		A = R.placement_matrix(pl[pid], prof)
		pts = R._apply(A, sh.c) * ppm - [ox, oy]
		cv2.polylines(img, [np.round(pts).astype(np.int32).reshape(-1, 1, 2)], True, (0, 0, 255), 2, cv2.LINE_AA)
		if sh.ok:
			for i, qq in enumerate(R._apply(A, sh.c[sh.corners]) * ppm - [ox, oy]):
				cv2.circle(img, (int(round(qq[0])), int(round(qq[1]))), 5, (0, 255, 255), -1, cv2.LINE_AA)
		tiles.append(img)
	h = max(t.shape[0] for t in tiles)
	tiles = [cv2.copyMakeBorder(t, 0, h - t.shape[0], 0, 6, cv2.BORDER_CONSTANT, value=(255, 255, 255)) for t in tiles]
	cv2.imwrite(out, np.hstack(tiles))


def fig(before, after, out, labels, max_bytes=300_000):
	a, b = cv2.imread(before), cv2.imread(after)
	n = len(labels)
	wa, wb = a.shape[1] // n, b.shape[1] // n
	rows = []
	for i, lab in enumerate(labels):
		ta, tb = a[:, i * wa:(i + 1) * wa], b[:, i * wb:(i + 1) * wb]
		h = max(ta.shape[0], tb.shape[0])
		row = np.hstack([cv2.copyMakeBorder(ta, 0, h - ta.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(255, 255, 255)),
						 cv2.copyMakeBorder(tb, 0, h - tb.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(255, 255, 255))])
		bar = np.full((34, row.shape[1], 3), 255, np.uint8)
		cv2.putText(bar, f"{lab}: ANTES", (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2, cv2.LINE_AA)
		cv2.putText(bar, "DEPOIS", (ta.shape[1] + 8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2, cv2.LINE_AA)
		rows.append(np.vstack([bar, row]))
	w = max(r.shape[1] for r in rows)
	img = np.vstack([cv2.copyMakeBorder(r, 0, 8, 0, w - r.shape[1], cv2.BORDER_CONSTANT, value=(255, 255, 255)) for r in rows])
	for scale in (1.0, 0.85, 0.7, 0.6, 0.5, 0.4):
		im = img if scale == 1.0 else cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
		for q in (88, 80, 72):
			ok, buf = cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, q])
			if len(buf) <= max_bytes:
				buf.tofile(out)
				print(f"{out}: {im.shape[1]}x{im.shape[0]}, q {q}, {len(buf) // 1024} KB")
				return


def block(proj, out):
	pr = Project.open(proj)
	prof = pr.profile
	poses = Poses(pr)
	by_cell = mounted(pr)
	A = [(l, c) for l in (1, 2, 3) for c in (32, 33)]
	pa = {cl: by_cell.get(cl) for cl in A}
	pb = {cl: by_cell.get(tuple(prof.twin(*cl))) for cl in A}
	pairs = []
	for cl in A:
		a, b = pa[cl], pb[cl]
		tw = tuple(prof.twin(*cl))
		if a is None or b is None:
			pairs.append(dict(cell=list(cl), twin=list(tw), a=a, b=b))
			continue
		sa, sb = pr.shape(a), pr.shape(b)
		fd = float(SH.free_dist(sa, sb)[0])
		# melhor peça do bloco gémeo para a (se os blocos estivessem trocados entre células)
		alt = sorted((float(SH.free_dist(sa, pr.shape(q))[0]), q, list(c2)) for c2, q in pb.items() if q is not None)
		# melhor gémea em todo o índice
		best = sorted((float(SH.free_dist(sa, pr.shape(q))[0]), q) for q in pr.pieces
					  if q != a and pr.shape(q) is not None and pr.shape(q).ok and pr.pieces[q].estado != "descartada")[:3]
		pairs.append(dict(cell=list(cl), twin=list(tw), a=a, b=b, cls_a=sa.cls, cls_b=sb.cls, free=_f(fd),
						  chords_a=[_f(s.chord_mm) for s in sa.sides], chords_b=[_f(s.chord_mm) for s in sb.sides],
						  best_in_twin_block=[(_f(d), q, c2) for d, q, c2 in alt[:2]],
						  best_index=[(_f(d), q, pr.piece(q).celula, pr.piece(q).scan_id) for d, q in best]))
	# vizinhas montadas fora do bloco: colunas 31/34 e filas 4 / 44
	sides = {}
	for name, cells in (("p03 (1..3,32..33)", A), ("G0043 (45..47,32..33)", [tuple(prof.twin(*cl)) for cl in A])):
		blk = set(cells)
		rows = []
		for cl in cells:
			pid = by_cell.get(cl)
			if pid is None:
				continue
			sd = sides_report(pr, poses, pid, by_cell)
			for d, v in sd.items():
				if v["kind"] != "vizinha":
					if v["kind"] == "borda":
						rows.append(dict(piece=pid, cell=list(cl), dir=d, ext=True, kind="borda", ok=v.get("ok"), side=v.get("side")))
					continue
				q_cell = (cl[0] + STEP[d][0], cl[1] + STEP[d][1])
				rows.append(dict(piece=pid, cell=list(cl), dir=d, ext=q_cell not in blk, **{k: v.get(k) for k in
							("kinds", "ok", "why", "rms", "dl", "gap_mm")}, other=v["piece"],
							other_scan=pr.piece(v["piece"]).scan_id))
		ext = [r for r in rows if r["ext"] and r.get("kind") != "borda"]
		sides[name] = dict(rows=rows, n_ext=len(ext), n_ext_ok=sum(bool(r["ok"]) for r in ext),
						   n_ext_kind=sum(r.get("why") == "kind" for r in ext),
						   n_int=sum(not r["ext"] for r in rows), n_int_ok=sum((not r["ext"]) and bool(r["ok"]) for r in rows),
						   borda=[(r["piece"], r["dir"], r["side"]) for r in rows if r.get("kind") == "borda"],
						   scans=sorted({pr.piece(by_cell[c]).scan_id for c in cells if by_cell.get(c)}),
						   seccoes=sorted({str(pr.piece(by_cell[c]).seccao_id) for c in cells if by_cell.get(c)}))
	res = dict(pairs=pairs, sides=sides)
	for p in pairs:
		print(p)
	for k, v in sides.items():
		print(k, {kk: vv for kk, vv in v.items() if kk != "rows"})
		for r in v["rows"]:
			print("   ", r)
	with open(out, "w", encoding="utf-8") as f:
		json.dump(res, f, ensure_ascii=False, indent=1, default=str)


if __name__ == "__main__":
	cmd = sys.argv[1]
	if cmd == "measure":
		measure(sys.argv[2], sys.argv[3], sys.argv[4:])
	elif cmd == "view":
		view(sys.argv[2], sys.argv[3], sys.argv[4:])
	elif cmd == "fig":
		fig(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5:])
	elif cmd == "block":
		block(sys.argv[2], sys.argv[3])


def block_swap(proj, out, seed=20261107, n_random=20000):
	"""Teste discriminante do bloco: em cada junta externa de cada bloco, custo ``side_compat`` da peça do bloco
	contra o da gémea do outro bloco rodada 180° (sob simetria encaixaria igual); taxas de base: juntas montadas
	de todo o tabuleiro e pares T/B ao acaso. Imagem: ``de_cell`` de cada peça na sua célula."""
	pr = Project.open(proj)
	prof = pr.profile
	poses = Poses(pr)
	art = CellArt.load(prof, REPO)
	by_cell = mounted(pr)
	A = [(l, c) for l in (1, 2, 3) for c in (32, 33)]
	B = [tuple(prof.twin(*cl)) for cl in A]
	res = dict(joints=[], image={})

	def side_in(pid, d, rotated=False):
		"""Lado de ``pid`` virado para ``d`` na sua célula (ou, ``rotated``, na célula gémea após 180°)."""
		return side_facing(pr, poses, pid, OPP[d] if rotated else d)

	for name, cells, other in (("p03", A, B), ("G0043", B, A)):
		blk = set(cells)
		for cl in cells:
			pid = by_cell[cl]
			twin_pid = by_cell[tuple(prof.twin(*cl))]
			for d, (dl, dc) in STEP.items():
				q_cell = (cl[0] + dl, cl[1] + dc)
				if q_cell in blk or q_cell not in by_cell:
					continue
				q = by_cell[q_cell]
				sq = side_facing(pr, poses, q, OPP[d])
				own = side_compat(side_in(pid, d), sq)
				sw = side_compat(side_in(twin_pid, d, rotated=True), sq)
				res["joints"].append(dict(bloco=name, cell=list(cl), dir=d, piece=pid, neighbour=q,
										  own=dict(kinds=side_in(pid, d).kind + sq.kind, ok=own["ok"], rms=_f(own["rms"]), dl=_f(own["dl"]), cost=_f(own["cost"])),
										  twin=twin_pid,
										  swap=dict(kinds=side_in(twin_pid, d, True).kind + sq.kind, ok=sw["ok"], rms=_f(sw["rms"]), dl=_f(sw["dl"]), cost=_f(sw["cost"]))))
		for cl in cells:
			pid = by_cell[cl]
			res["image"][pid] = dict(cell=list(cl), **image_report(pr, poses, art, pid))
	# taxas de base
	true_rms, true_ok = [], 0
	sides_T, sides_B = [], []
	for cl, pid in by_cell.items():
		for d in ("E", "S"):
			q = by_cell.get((cl[0] + STEP[d][0], cl[1] + STEP[d][1]))
			sa = side_facing(pr, poses, pid, d)
			if sa is not None:
				(sides_T if sa.kind == "T" else sides_B if sa.kind == "B" else []).append(sa)
			if q is None:
				continue
			sb = side_facing(pr, poses, q, OPP[d])
			if sa is None or sb is None:
				continue
			r = side_compat(sa, sb)
			if r["why"] in ("", "rms", "dl"):
				true_rms.append(r["rms"])
				true_ok += bool(r["ok"])
	rng = np.random.default_rng(seed)
	rnd_rms, rnd_ok = [], 0
	for _ in range(n_random):
		a, b = sides_T[rng.integers(len(sides_T))], sides_B[rng.integers(len(sides_B))]
		r = side_compat(a, b)
		rnd_rms.append(r["rms"])
		rnd_ok += bool(r["ok"])
	tr, rr = np.array(true_rms), np.array(rnd_rms)
	res["base"] = dict(n_true=len(tr), true_ok=true_ok / len(tr), true_rms_p50=_f(np.median(tr)), true_rms_p90=_f(np.percentile(tr, 90)),
					   n_random=len(rr), random_ok=rnd_ok / len(rr), random_rms_p10=_f(np.percentile(rr, 10)),
					   random_rms_p50=_f(np.median(rr)))
	for j in res["joints"]:
		print(j)
	for pid, v in res["image"].items():
		print(pid, v["cell"], "NCC", [(r["rot"], r["ncc"], r["dE"]) for r in v["rots"]])
	print(res["base"])
	with open(out, "w", encoding="utf-8") as f:
		json.dump(res, f, ensure_ascii=False, indent=1, default=str)


if __name__ == "__main__" and sys.argv[1] == "swap":
	block_swap(sys.argv[2], sys.argv[3])
