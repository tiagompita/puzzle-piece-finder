"""Re-evaluate the loose-piece memory and write the "go fetch" list (``python -m src.query``).

Usage::

	python -m src.query [--lote N] [--no-image] [--project projects/alpes]

Order of signals (docs/estado-e-plano.md §0, docs/plano-m10-m12.md §3.2):

0. missing border cells: loose pieces with the right number of flat sides (corner: two
   adjacent F); if the twin cell holds a placed piece with a silhouette, ``find_twin``
   1-against-those candidates, else they are listed as ``candidata`` (only when at most
   ``MAX_MISSING_BORDER`` border cells are missing);
1. pending twins (``Project.pending_twins``): ``find_twin(placed piece, loose pieces)``;
2. pairs among loose pieces: ``find_twin`` loose↔loose for each loose piece without a
   proposal; only a mutual ``aceite`` becomes a pair (``register_pair`` + ``pair_locate``);
   already registered pairs are listed again;
3. known positions that became placeable;
4. sections not anchored (their stored top-3; sections made only of ``same_as`` re-scans are skipped);
5. the rest stays in memory (only counted).

A twin query whose only surviving candidate is a lone one (``find_twin`` ->
``single_candidate``, decision ``sem`` since 2026-11-01) is not listed; it is kept for
review in ``fetch.json`` -> ``suprimidas`` and counted in the footer of ``fetch.md``.

Every entry with a piece also carries what the GUI / the printed sheet need to fetch it and
put it down (:func:`_enrich`): ``theta_deg`` (board pose of the loose piece, complex
convention of :mod:`src.shape`, positive = clockwise on screen, wrapped to (-180, 180]) and
``pose_known`` / ``pose_reason``; for a twin proposal the pose is the chain of
``src/twin.py`` (``tests/test_twin_real.py`` "orientation chain"): registered board pose of
the placed query piece (:func:`src.render.registered_theta`; fallback the log
``theta_deg``) + ``phi_deg`` of the candidate + ``profile.twin_rotation_deg()``. Also
``scan_id``, ``crop_path``, ``clean_path`` (``render/clean/P####.png`` when it exists),
``twin_id`` / ``twin_cell`` (the placed piece in ``profile.twin(*cell)``), ``sheet``
(``render/sheets/S####_P####.jpg``: the numbered scan sheet with the piece highlighted,
rewritten only when its numbering changes) and ``ghost`` (the twin's contour as it will
look in the target cell: ``[[x, y], ...]`` in cell units, origin at the target cell centre,
x right / y down, <= ``GHOST_MAX_PTS`` points). Paths are relative to the project folder.

``src.twin`` / ``src.locate`` / ``src.render`` are imported lazily (other milestone); tests
replace them in ``sys.modules``. :func:`run_query` is the callable entry point (future GUI).
``--lote N`` restricts the loose pieces examined to bag N (step 2 still searches the
partner among all loose pieces: a pair rarely shares a bag).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import glob
import json
import os
import sys
from typing import Optional

import numpy as np

__all__ = ["ORIGIN_STEP", "MAX_MISSING_BORDER", "MAX_BORDER_CANDIDATES", "run_query", "write_fetch",
		   "load_fetch", "render_fetch_md", "ghost_contour", "wrap180", "GHOST_MAX_PTS", "main"]

ORIGIN_STEP = {"borda": 0, "gemeo": 1, "par": 2, "posicao_conhecida": 3, "seccao": 4}
_DECISION_RANK = {"aceite": 0, "colocavel": 0, "ambigua": 1, "proposto": 1, "confirmado": 0, "candidata": 2,
				  "por_ancorar": 2}
MAX_MISSING_BORDER = 8        # step 0 runs only when few border cells are missing (else it lists the whole pool)
MAX_BORDER_CANDIDATES = 12    # listed candidates per missing border cell without a twin silhouette
MODALITY = "silhueta_silhueta"
TOPK = 3
THUMB = 210                   # px, main image of a tile of fetch_<lote>.jpg (the twin beside it at half size)
TILE_CELLS = 1.8              # cells across THUMB (a piece with its tabs spans <= ~1.6 cells)
GHOST_MAX_PTS = 120           # points of the twin ghost contour in a fetch entry
SHEET_MAX_PX = 1400           # long side of render/sheets/*.jpg
SHEET_QUALITY = 80            # JPEG quality of the sheets (lowered in steps of 10 down to 50 if > SHEET_MAX_BYTES)
SHEET_MAX_BYTES = 250_000
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------- helpers
def _twin_api():
	from src.twin import TwinItem, find_twin
	return TwinItem, find_twin


def _cl(v):
	return None if v is None else (int(v[0]), int(v[1]))


class _Ctx:
	"""Per-run caches: TwinItems (shape + crop), art, call counters."""

	def __init__(self, project, use_image: bool):
		self.pr = project
		self.use_image = use_image
		self.items = {}
		self.notes = []
		self.suppressed = []
		self.art = None
		self.TwinItem, self.find_twin = _twin_api()
		self.poses = {}
		self.placements = None
		self.sheet_index = None
		self.sheet_index_dirty = False
		if use_image:
			try:
				from src.locate import CellArt
				self.art = CellArt.load(project.profile, REPO)
			except Exception as e:  # noqa: BLE001 - image is optional for the list, reported
				self.notes.append(f"arte indisponível ({type(e).__name__}: {e}); sem desempate pela imagem")

	def item(self, p):
		if p.id not in self.items:
			sh = self.pr.shape(p.id)
			rgba = self.pr.crop_rgba(p.id) if self.use_image else None
			cell = p.celula if p.estado == "colocada" else None
			self.items[p.id] = self.TwinItem(id=p.id, shape=sh, rgba=rgba, theta_deg=p.theta_deg, cell=cell)
		return self.items[p.id]


def _usable(pr, p) -> bool:
	return not p.flags.get("objeto_duplo") and pr.shape(p.id) is not None


def _rejected(pr) -> set:
	return {(pid, cell) for pid, cell, _ in pr.model.rejections}


def _corner_ok(cls: str) -> bool:
	return "FF" in (cls + cls[:1])


def _entry(pr, origin: str, piece_id: Optional[str], cell, decision: str, **kw) -> dict:
	p = pr.piece(piece_id) if piece_id else None
	e = {"origin": origin, "piece": piece_id, "lote": p.lote if p else None, "n_no_lote": p.n_no_lote if p else None,
		 "cell": list(cell) if cell else None, "decision": decision, "margin": None, "dE": None, "d1_mm": None,
		 "reasons": [], "query": None, "pair": None, "rank": None, "score": None, "phi_deg": None}
	e.update(kw)
	return e


def _suppressed(pr, origin: str, res: dict, cell, query_id: Optional[str]) -> Optional[dict]:
	"""Review record of a twin query not proposed because it had a lone candidate (None otherwise)."""
	sc = res.get("single_candidate")
	if not sc:
		return None
	p = pr.piece(sc["id"]) if sc["id"] in pr.pieces else None
	reason = next((r for r in res.get("reasons") or [] if r.startswith("candidata única")), "candidata única")
	return {"origin": origin, "query": query_id, "piece": sc["id"], "lote": p.lote if p else None,
			"n_no_lote": p.n_no_lote if p else None, "cell": list(cell) if cell else None, "candidate": dict(sc),
			"d1_mm": sc.get("d1_mm"), "decision_shape": res.get("decision_shape"), "reason": reason}


def _from_candidate(pr, origin: str, res: dict, cell, query_id: Optional[str]) -> Optional[dict]:
	cands = res.get("candidates") or []
	if not cands or res.get("decision") not in ("aceite", "ambigua"):
		return None
	c0 = cands[0]
	img = c0.get("image") or {}
	return _entry(pr, origin, c0["id"], cell, res["decision"], margin=res.get("margin"), dE=img.get("dE"),
				  d1_mm=c0.get("d1_mm"), reasons=list(res.get("reasons") or []), query=query_id, rank=1,
				  score=c0.get("d1_mm"), phi_deg=None if c0.get("phi_deg") is None else float(c0["phi_deg"]))


# ---------------------------------------------------------------- steps
def _step_border(ctx, loose, only_cells, proposed, rej) -> list:
	pr = ctx.pr
	missing = pr.missing_border_cells()
	if only_cells is not None:
		missing = [m for m in missing if m in only_cells]
	elif len(missing) > MAX_MISSING_BORDER:
		ctx.notes.append(f"passo 0 ignorado: {len(missing)} células de borda vazias (> {MAX_MISSING_BORDER})")
		return []
	out = []
	for m in missing:
		nf = pr.profile.n_flat_sides(*m)
		cands = [p for p in loose if _usable(pr, p) and p.n_flat == nf and (p.id, m) not in rej
				 and p.id not in proposed and (nf < 2 or _corner_ok(p.cls))]
		if not cands:
			continue
		tw = pr.profile.twin(*m)
		occ = pr.board[tw] if tw else None
		q = pr.piece(occ["peca_id"]) if occ and occ["estado"] == "colocada" else None
		if q is not None and pr.shape(q.id) is not None:
			res = ctx.find_twin(ctx.item(q), [ctx.item(p) for p in cands], profile=pr.profile, modality=MODALITY,
								art=ctx.art, topk=TOPK)
			if "error" in res:
				ctx.notes.append(f"find_twin borda {m}: {res['error']}")
				continue
			s_ = _suppressed(pr, "borda", res, m, q.id)
			if s_:
				ctx.suppressed.append(s_)
			e = _from_candidate(pr, "borda", res, m, q.id)
			if e:
				out.append(e)
				proposed.add(e["piece"])
		else:
			why = f"{nf} lado(s) F; gémea {tw} sem silhueta no índice"
			for p in cands[:MAX_BORDER_CANDIDATES]:
				out.append(_entry(pr, "borda", p.id, m, "candidata", reasons=[why]))
			if len(cands) > MAX_BORDER_CANDIDATES:
				ctx.notes.append(f"borda {m}: {len(cands)} candidatas, listadas {MAX_BORDER_CANDIDATES}")
	return out


def _step_twins(ctx, loose, only_cells, only_pieces, proposed, rej) -> list:
	pr = ctx.pr
	out = []
	for q, tw in pr.pending_twins():
		if only_cells is not None or only_pieces is not None:
			if not ((only_cells and tw in only_cells) or (only_pieces and q.id in only_pieces)):
				continue
		if pr.shape(q.id) is None:
			continue
		cands = [p for p in loose if _usable(pr, p) and p.id not in proposed and (p.id, tw) not in rej]
		if not cands:
			continue
		res = ctx.find_twin(ctx.item(q), [ctx.item(p) for p in cands], profile=pr.profile, modality=MODALITY,
							art=ctx.art, topk=TOPK)
		if "error" in res:
			ctx.notes.append(f"find_twin {q.id}: {res['error']}")
			continue
		s_ = _suppressed(pr, "gemeo", res, tw, q.id)
		if s_:
			ctx.suppressed.append(s_)
		e = _from_candidate(pr, "gemeo", res, tw, q.id)
		if e:
			out.append(e)
			proposed.add(e["piece"])
	return out


def _pair_entries(pr, t, lote) -> list:
	out = []
	cell = _cl(t.cells[0]["cell"]) if t.cells else None
	img = t.image or {}
	for a, b in ((t.a, t.b), (t.b, t.a)):
		if lote is not None and pr.piece(a).lote != lote and pr.piece(b).lote != lote:
			continue
		out.append(_entry(pr, "par", a, cell, t.estado, margin=t.margin, dE=img.get("dE"), d1_mm=t.d1_mm, query=b,
						  pair=t.id, score=t.d1_mm, reasons=[f"par com {b}"] + ([f"células {[c['cell'] for c in t.cells]}"]
																			   if t.cells else [])))
	return out


def _step_pairs(ctx, loose, only_pieces, proposed, lote) -> list:
	pr = ctx.pr
	in_pair = {x for t in pr.pairs.values() if t.estado != "rejeitado" for x in (t.a, t.b)}
	rej_pairs = {frozenset((t.a, t.b)) for t in pr.pairs.values() if t.estado == "rejeitado"}
	pool = [p for p in pr.loose_pieces() if _usable(pr, p) and p.id not in in_pair]
	pool_ids = {p.id for p in pool}
	queries = [p for p in loose if p.id in pool_ids and p.id not in proposed and (only_pieces is None or p.id in only_pieces)]
	res = {}

	def run(p):
		if p.id not in res:
			others = [q for q in pool if q.id != p.id and q.id not in proposed]
			res[p.id] = ctx.find_twin(ctx.item(p), [ctx.item(q) for q in others], profile=pr.profile,
									  modality=MODALITY, art=ctx.art, topk=TOPK) if others else {"decision": "sem"}
		return res[p.id]

	out = []
	done = set()
	for a in queries:
		if a.id in done:
			continue
		ra = run(a)
		if "error" in ra:
			ctx.notes.append(f"find_twin {a.id}: {ra['error']}")
			continue
		if ra.get("decision") != "aceite" or not ra.get("candidates"):
			continue
		bid = ra["candidates"][0]["id"]
		if bid in done or frozenset((a.id, bid)) in rej_pairs:
			continue
		rb = run(pr.piece(bid))
		if rb.get("decision") != "aceite" or not rb.get("candidates") or rb["candidates"][0]["id"] != a.id:
			continue
		c0 = ra["candidates"][0]
		cells = []
		if ctx.art is not None:
			from src.locate import pair_locate
			ia, ib = ctx.item(a), ctx.item(pr.piece(bid))
			loc = pair_locate({"rgba": ia.rgba, "theta_deg": 0.0, "phi_deg": 0.0},
							  {"rgba": ib.rgba, "theta_deg": 0.0, "phi_deg": float(c0.get("phi_deg") or 0.0)},
							  pr.profile, ctx.art, topk=TOPK)
			cells = [{"cell": list(c["cell"]), "score": c.get("score"), "rank": c.get("rank")}
					 for c in (loc.get("cells") or [])] if isinstance(loc, dict) else []
		tid = pr.register_pair(a.id, bid, d1=c0.get("d1_mm"), margin=ra.get("margin"), image=c0.get("image"),
							   cells=cells)
		done.update((a.id, bid))
		proposed.update((a.id, bid))
	for t in sorted(pr.pairs.values(), key=lambda t: t.id):
		if t.estado != "rejeitado" and all(pr.piece(x).estado == "emparelhada" for x in (t.a, t.b)):
			out += _pair_entries(pr, t, lote)
	return out


def _step_known(pr, lote) -> list:
	return [_entry(pr, "posicao_conhecida", p.id, cell, "colocavel", reasons=["vizinha ocupada"])
			for p, cell in pr.placeable_known_positions() if lote is None or p.lote == lote]


def _step_sections(pr) -> list:
	out = []
	for s in sorted(pr.sections.values(), key=lambda s: s.id):
		if s.anchor.get("anchored"):
			continue
		if s.cells_local and all(pr.piece(pid).same_as for pid in s.cells_local):
			continue  # re-scan of pieces already in the project (page scanned twice): nothing to anchor
		cands = s.candidates[:3]
		cell = _cl(cands[0].get("cell0")) if cands and cands[0].get("cell0") else None
		out.append(_entry(pr, "seccao", None, cell, "por_ancorar", section=s.id, candidates=cands,
						  margin=cands[0].get("margin") if cands else None,
						  reasons=[f"{len(s.cells_local)} peças; top-3 {[(c.get('cell0'), c.get('rot')) for c in cands]}"]))
	return out


# ---------------------------------------------------------------- pose, ghost, sheet of an entry
def wrap180(a: float) -> float:
	"""Angle in degrees wrapped to (-180, 180]."""
	w = float(a) % 360.0
	return w - 360.0 if w > 180.0 else w


def _pose(ctx, pid: str) -> Optional[dict]:
	"""Board pose of a placed piece ``{theta_deg, pivot_mm, dx_mm, dy_mm, source}`` (None if unknown).

	Same source as :func:`src.render.registered_theta` (the ``render/placements.json`` entry
	when its key still matches, else a corner registration without the image), plus the
	translation needed by the ghost; fallback: the log ``theta_deg`` about the body centre.
	"""
	if pid in ctx.poses:
		return ctx.poses[pid]
	pr = ctx.pr
	p = pr.piece(pid)
	out = None
	try:
		from src import render
		if p.estado == "colocada" and p.celula is not None:
			if ctx.placements is None:
				ctx.placements = render.load_placements(pr)["placements"]
			e = ctx.placements.get(pid)
			if e is None or e.get("key") != render._entry_key(pr, pid):
				e = render.register_piece(pr, pid, art=None, image=False)
				how = "registo (cantos, sem imagem)"
			else:
				how = "registo"
			if "error" not in e:
				out = {"theta_deg": float(e["theta_deg"]), "pivot_mm": [float(v) for v in e["pivot_mm"]],
					   "dx_mm": float(e.get("dx_mm") or 0.0), "dy_mm": float(e.get("dy_mm") or 0.0), "source": how}
	except Exception as ex:  # noqa: BLE001 - render is optional for the list; fall back to the log, reported
		ctx.notes.append(f"registo de {pid} indisponível ({type(ex).__name__}: {ex})")
	if out is None and p.theta_deg is not None:
		sh = pr.shape(pid)
		piv = _body_center(sh)
		out = {"theta_deg": float(p.theta_deg), "pivot_mm": None if piv is None else [float(v) for v in piv],
			   "dx_mm": 0.0, "dy_mm": 0.0, "source": "log"}
	ctx.poses[pid] = out
	return out


def _body_center(sh):
	"""Body centre (mean of the 4 corners) of a Shape, else its contour mean; None without a shape."""
	if sh is None:
		return None
	if getattr(sh, "ok", False) and len(getattr(sh, "corners", [])) == 4:
		return np.asarray(sh.c, float)[np.asarray(sh.corners, int)].mean(0)
	return np.asarray(sh.c, float).mean(0)


def ghost_contour(shape, pose: dict, profile, max_pts: int = GHOST_MAX_PTS) -> Optional[list]:
	"""Contour of a placed piece moved to its twin cell, in cell units about that cell's centre.

	Board pose of the placed piece: ``R(theta) (c - pivot) + d`` about its own cell centre;
	the twin cell sees it turned by ``profile.twin_rotation_deg()`` about the centre, so the
	ghost is ``R(rot) (R(theta) (c - pivot) + d)``, divided by ``cell_mm`` (x by w, y by h).
	Returns ``[[x, y], ...]`` (<= ``max_pts`` points, 4 decimals) or None.
	"""
	from src.shape import transform_contour
	if shape is None or pose is None:
		return None
	c = np.asarray(shape.c, float).reshape(-1, 2)
	if len(c) < 3:
		return None
	piv = np.asarray(pose["pivot_mm"], float) if pose.get("pivot_mm") is not None else _body_center(shape)
	rot = float(profile.twin_rotation_deg())
	g = transform_contour(c - piv, float(pose["theta_deg"]) + rot, center=(0.0, 0.0))
	d = transform_contour(np.array([[pose.get("dx_mm") or 0.0, pose.get("dy_mm") or 0.0]]), rot, center=(0.0, 0.0))
	g = g + d
	idx = np.unique(np.linspace(0, len(g), min(max_pts, len(g)), endpoint=False).astype(int))
	g = g[idx] / np.array([float(profile.cell_mm["w"]), float(profile.cell_mm["h"])])
	return [[round(float(x), 4), round(float(y), 4)] for x, y in g]


def _sheet_signature(pr, scan_id: str, pid: str) -> str:
	from src.ingest import piece_label
	labs = sorted((p.id, piece_label(p)) for p in pr.pieces.values() if p.scan_id == scan_id)
	return json.dumps([pid, SHEET_MAX_PX, labs], separators=(",", ":"))


def _sheet(ctx, pid: str, write: bool) -> Optional[str]:
	"""``render/sheets/<scan>_<pid>.jpg`` (project-relative): the numbered sheet of the piece's scan with
	the piece highlighted; written only when missing or when the scan's numbering changed."""
	pr = ctx.pr
	p = pr.piece(pid)
	rel = f"render/sheets/{p.scan_id}_{pid}.jpg"
	fp = pr.p(*rel.split("/"))
	if ctx.sheet_index is None:
		ix = pr.p("render", "sheets", "index.json")
		ctx.sheet_index = {}
		if os.path.exists(ix):
			try:
				with open(ix, encoding="utf-8") as f:
					ctx.sheet_index = json.load(f)
			except (OSError, ValueError):
				ctx.sheet_index = {}
	sig = _sheet_signature(pr, p.scan_id, pid)
	if os.path.exists(fp) and ctx.sheet_index.get(rel) == sig:
		return rel
	if not write:
		return rel if os.path.exists(fp) else None
	import cv2
	from src.ingest import sheet_overlay
	try:
		img = sheet_overlay(pr, p.scan_id, highlight=pid, max_px=SHEET_MAX_PX)
	except (ValueError, OSError) as ex:
		ctx.notes.append(f"folha de {pid} ({p.scan_id}) não gerada: {ex}")
		return None
	q = SHEET_QUALITY
	while True:
		ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
		if not ok or len(buf) <= SHEET_MAX_BYTES or q <= 50:
			break
		q -= 10
	if not ok:
		ctx.notes.append(f"folha de {pid}: falha a codificar")
		return None
	os.makedirs(os.path.dirname(fp), exist_ok=True)
	buf.tofile(fp)
	ctx.sheet_index[rel] = sig
	ctx.sheet_index_dirty = True
	return rel


def _save_sheet_index(ctx) -> None:
	if getattr(ctx, "sheet_index_dirty", False):
		with open(ctx.pr.p("render", "sheets", "index.json"), "w", encoding="utf-8", newline="\n") as f:
			json.dump(ctx.sheet_index, f, ensure_ascii=False, indent=0, sort_keys=True)


def _enrich(ctx, e: dict, write: bool) -> dict:
	"""Add the pose / image / sheet / ghost fields to entry ``e`` (in place; see the module docstring)."""
	pr = ctx.pr
	prof = pr.profile
	pid = e.get("piece")
	p = pr.piece(pid) if pid and pid in pr.pieces else None
	cell = _cl(e.get("cell"))
	tw_cell = prof.twin(*cell) if cell is not None else None
	twin_id = None
	if e.get("origin") in ("gemeo", "borda") and e.get("query") and e["query"] in pr.pieces:
		twin_id = e["query"]
	elif tw_cell is not None:
		occ = pr.board[tw_cell]
		if occ.get("estado") == "colocada" and occ.get("peca_id"):
			twin_id = occ["peca_id"]
	tp = pr.piece(twin_id) if twin_id else None
	if tp is not None and tp.celula is not None:
		tw_cell = tuple(tp.celula)
	e.update(scan_id=p.scan_id if p else None, crop_path=p.crop_path if p else None, clean_path=None,
			 twin_id=twin_id, twin_cell=list(tw_cell) if tw_cell else None, sheet=None, ghost=None)
	if p is not None and os.path.exists(pr.p("render", "clean", f"{pid}.png")):
		e["clean_path"] = f"render/clean/{pid}.png"
	# pose of the loose piece on the board
	theta, why = None, None
	tpose = _pose(ctx, twin_id) if tp is not None and tp.estado == "colocada" else None
	if p is None:
		why = "sem peça"
	elif e.get("origin") in ("gemeo", "borda") and e.get("query"):
		if e.get("phi_deg") is None:
			why = "pose desconhecida: phi da candidata em falta"
		elif tpose is None:
			why = f"pose desconhecida: {twin_id} sem registo nem theta no log"
		else:
			theta = tpose["theta_deg"] + float(e["phi_deg"]) + float(prof.twin_rotation_deg())
			why = f"theta {twin_id} ({tpose['source']}) + phi + rotação do gémeo"
	elif p.theta_deg is not None:
		theta, why = float(p.theta_deg), "theta do log"
	elif e.get("origin") == "par":
		why = "pose desconhecida: par entre soltas (célula por confirmar)"
	else:
		why = "pose desconhecida"
	e["theta_deg"] = None if theta is None else round(wrap180(theta), 2)
	e["pose_known"] = theta is not None
	e["pose_reason"] = why
	if p is not None:
		e["sheet"] = _sheet(ctx, pid, write)
	if tp is not None and tpose is not None and cell is not None:
		e["ghost"] = ghost_contour(pr.shape(twin_id), tpose, prof)
	return e


# ---------------------------------------------------------------- main entry point
def _valid_prior(pr, e, only_cells, only_pieces, rej) -> bool:
	if ORIGIN_STEP.get(e["origin"], 9) >= 3:
		return False  # steps 3-4 are always recomputed
	pid, cell = e.get("piece"), _cl(e.get("cell"))
	if pid is None or pid not in pr.pieces or pr.piece(pid).estado not in ("solta", "emparelhada"):
		return False
	if e["origin"] == "par":
		t = pr.pairs.get(e.get("pair"))
		return t is not None and t.estado != "rejeitado"
	if cell is not None and (pr.board[cell]["estado"] != "vazia" or (pid, cell) in rej):
		return False
	if pid in only_pieces or (e.get("query") in only_pieces) or (cell is not None and cell in only_cells):
		return False
	return True


def _valid_prior_suppressed(pr, s, only_cells, only_pieces, rej) -> bool:
	"""A previous ``suprimidas`` record still stands if nothing it depends on was re-queried or changed."""
	pid, cell = s.get("piece"), _cl(s.get("cell"))
	if pid is None or pid not in pr.pieces or pr.piece(pid).estado not in ("solta", "emparelhada"):
		return False
	if cell is not None and (pr.board[cell]["estado"] != "vazia" or (pid, cell) in rej or cell in only_cells):
		return False
	return pid not in only_pieces and s.get("query") not in only_pieces


def run_query(project, *, lote: Optional[int] = None, use_image: bool = True, only_cells=None, only_pieces=None,
			  write: bool = True, log: bool = True) -> list:
	"""Run the signal steps and (``write``) rewrite ``fetch.md``/``fetch.json``/``fetch_<lote>.jpg``.

	Full run when ``only_cells`` and ``only_pieces`` are None. Incremental run (after a
	confirmation): only the pending twins / border cells in ``only_cells`` and the loose
	pieces in ``only_pieces`` are re-queried; the previous list's still-valid entries are
	kept. Returns the ordered entries (dicts with ``ordem``, ``origin``, ``piece``, ``lote``,
	``n_no_lote``, ``cell``, ``decision``, ``margin``, ``dE``, ``reasons`` ...).
	"""
	pr = project
	incremental = only_cells is not None or only_pieces is not None
	oc = {tuple(c) for c in only_cells} if only_cells is not None else None
	op = set(only_pieces) if only_pieces is not None else None
	ctx = _Ctx(pr, use_image)
	rej = _rejected(pr)
	loose = pr.loose_pieces(lote)
	proposed = set()
	entries = []
	if incremental:
		prior = load_fetch(pr).get("entries", [])
		entries = [e for e in prior if _valid_prior(pr, e, oc or set(), op or set(), rej)
				   and (lote is None or e.get("lote") == lote)]
		proposed = {e["piece"] for e in entries if e["decision"] in ("aceite", "ambigua")}
		ctx.suppressed = [s for s in load_fetch(pr).get("suprimidas", [])
						  if _valid_prior_suppressed(pr, s, oc or set(), op or set(), rej)
						  and (lote is None or s.get("lote") == lote)]
	entries += _step_border(ctx, loose, oc if incremental else None, proposed, rej) if (not incremental or oc) else []
	entries += _step_twins(ctx, loose, oc, op, proposed, rej)
	if not incremental or op:
		entries = [e for e in entries if e["origin"] != "par"]
		entries += _step_pairs(ctx, loose, op if incremental else None, proposed, lote)
	else:
		entries = [e for e in entries if e["origin"] != "par"]
		entries += [x for t in sorted(pr.pairs.values(), key=lambda t: t.id)
					if t.estado != "rejeitado" and all(pr.piece(i).estado == "emparelhada" for i in (t.a, t.b))
					for x in _pair_entries(pr, t, lote)]
	entries += _step_known(pr, lote)
	entries += _step_sections(pr)
	seen, uniq = set(), []
	for e in entries:
		k = (e["origin"], e.get("piece"), tuple(e["cell"]) if e.get("cell") else None, e.get("section"))
		if k not in seen:
			seen.add(k)
			uniq.append(e)
	uniq.sort(key=lambda e: (ORIGIN_STEP.get(e["origin"], 9), _DECISION_RANK.get(e["decision"], 5),
							 -(e["margin"] if isinstance(e.get("margin"), (int, float)) else 0.0), e.get("piece") or ""))
	for i, e in enumerate(uniq, 1):
		e["ordem"] = i
		try:
			_enrich(ctx, e, write)
		except Exception as ex:  # noqa: BLE001 - the list must still be written; the entry keeps pose_known False
			e.setdefault("theta_deg", None)
			e["pose_known"], e["pose_reason"] = False, f"erro ao calcular a pose ({type(ex).__name__}: {ex})"
			ctx.notes.append(f"entrada {i}: {e['pose_reason']}")
	if write:
		_save_sheet_index(ctx)
	listed = {e["piece"] for e in uniq if e.get("piece")}
	rest = [p.id for p in loose if p.id not in listed]
	seen_s, suppressed = set(), []
	for s in ctx.suppressed:
		k = (s.get("origin"), s.get("query"), s.get("piece"), tuple(s["cell"]) if s.get("cell") else None)
		if k not in seen_s and s.get("piece") not in listed:
			seen_s.add(k)
			suppressed.append(s)
	if write:
		write_fetch(pr, uniq, rest, ctx.notes, suppressed)
	if log:
		pr.fetch_listed(uniq)
	pr.save()
	return uniq


# ---------------------------------------------------------------- output
def load_fetch(project) -> dict:
	fp = project.p("fetch.json")
	if not os.path.exists(fp):
		return {"entries": []}
	with open(fp, encoding="utf-8") as f:
		return json.load(f)


def _pose_txt(e) -> str:
	return f"{e['theta_deg']:.0f}°" if e.get("pose_known") and e.get("theta_deg") is not None else "?"


def _fmt(v, nd=2):
	if v is None:
		return "—"
	if isinstance(v, float):
		return f"{v:.{nd}f}"
	return str(v)


def render_fetch_md(project, entries: list, rest: list, notes: list, suppressed: Optional[list] = None) -> str:
	"""Markdown of the "go fetch" list (table + stats with the p_twin_placed formula)."""
	st = project.stats()
	L = [f"# Lista «ir buscar» — {_dt.datetime.now().isoformat(timespec='seconds')}", "",
		 f"Projeto `{project.meta['id']}`; {st['pecas']} peças; por estado {st['por_estado']}; tabuleiro "
		 f"{st['celulas_ocupadas']} ocupadas / {project.profile.cell_count()}.",
		 f"p_twin_placed = {st['p_twin_placed']:.3f} ({st['p_twin_placed_formula']}).", "",
		 "| ordem | lote | nº no lote | id | célula | pose | origem | decisão | margem | ΔE | razões |",
		 "|---:|---:|---:|---|---|---:|---|---|---:|---:|---|"]
	for e in entries:
		pid = e.get("piece") or e.get("section") or "—"
		cell = f"({e['cell'][0]},{e['cell'][1]})" if e.get("cell") else "—"
		why = "; ".join(str(r) for r in (e.get("reasons") or [])).replace("|", "/")
		L.append(f"| {e['ordem']} | {_fmt(e.get('lote'))} | {_fmt(e.get('n_no_lote'))} | {pid} | {cell} | "
				 f"{_pose_txt(e) if e.get('piece') else '—'} | {e['origin']} | {e['decision']} | {_fmt(e.get('margin'))} | "
				 f"{_fmt(e.get('dE'), 1)} | {why} |")
	L += ["", "pose = rotação (graus, positiva no sentido dos ponteiros do relógio) que leva a peça, tal como está "
		  "na folha do scan, à sua posição no tabuleiro; «?» = desconhecida (ver pose_reason em fetch.json)."]
	L += ["", f"Ficam na memória: {len(rest)} soltas sem proposta."]
	for n in notes:
		L.append(f"- nota: {n}")
	if suppressed:
		L.append(f"- nota: {len(suppressed)} propostas suprimidas por candidata única (ver fetch.json → suprimidas)")
	return "\n".join(L) + "\n"


_FONTS = {}


def _font(size: int):
	"""TrueType font (Arial / DejaVu Sans) at ``size`` px, else PIL's default font."""
	if size not in _FONTS:
		from PIL import ImageFont
		f = None
		for name in ("arial.ttf", "Arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
			try:
				f = ImageFont.truetype(name, size)
				break
			except OSError:
				continue
		if f is None:
			try:
				f = ImageFont.load_default(size=size)
			except TypeError:
				f = ImageFont.load_default()
		_FONTS[size] = f
	return _FONTS[size]


def _fit_text(draw, xy, text: str, width: int, size: int, fill) -> None:
	"""Draw ``text`` at ``xy`` with the largest font <= ``size`` that fits in ``width`` px (ellipsis below 10 px)."""
	s = size
	while s > 10 and draw.textlength(text, font=_font(s)) > width:
		s -= 1
	t = text
	while len(t) > 3 and draw.textlength(t, font=_font(s)) > width:
		t = t[:-2] + "…"
	draw.text(xy, t, font=_font(s), fill=fill)


def _piece_image(project, pid: str, theta_deg: float, pivot_mm, size: int, px_per_mm: float):
	"""The cleaned crop of ``pid`` turned by ``theta_deg`` about ``pivot_mm`` (scan mm), pivot at the
	centre of a ``size`` x ``size`` canvas: ``(rgb->bgr float, alpha float 0..1)`` or None."""
	from src import render
	rgba = render._clean_or_crop(project, pid)
	if rgba is None:
		return None
	p = project.piece(pid)
	mmpp = render._scan_mmpp(project, p.scan_id)
	origin = np.asarray(p.bbox[:2], float) if p.bbox else np.zeros(2)
	if pivot_mm is None:
		pivot_mm = (origin + np.array(rgba.shape[1::-1]) / 2.0) * mmpp
	ctr = np.full(2, (size / 2.0 + 0.5) / px_per_mm)
	A = render._crop_to_out(float(theta_deg), pivot_mm, ctr, (0.0, 0.0), origin, mmpp, (px_per_mm, px_per_mm), (0, 0))
	bgr = render._warp(np.ascontiguousarray(rgba[..., 2::-1]), A, (size, size)).astype(float)
	al = render._warp(rgba[..., 3].astype(np.float32) / 255.0, A, (size, size))[..., None]
	return bgr, np.clip(al, 0.0, 1.0)


def _paste(sheet: np.ndarray, x0: int, y0: int, im) -> None:
	if im is None:
		return
	bgr, al = im
	h, w = al.shape[:2]
	roi = sheet[y0:y0 + h, x0:x0 + w].astype(float)
	sheet[y0:y0 + h, x0:x0 + w] = (al * bgr + (1.0 - al) * roi).astype(np.uint8)


def _fetch_sheet(project, lote, rows: list) -> np.ndarray:
	"""Sheet of the pieces to fetch from bag ``lote`` (BGR).

	Each tile: the piece (cleaned crop) turned to its board pose (``theta_deg``; a small red
	triangle marks the top of the board, the twin ghost is a thin cyan line), the placed twin
	at half size as it sits on the board, and two label lines ("ordem. lote L · nº N → (l,c)"
	and origin / decision / pose). Without a known pose the crop is shown as scanned and the
	label says "pose ?".
	"""
	import cv2
	from PIL import Image, ImageDraw
	prof = project.profile
	cw, ch = float(prof.cell_mm["w"]), float(prof.cell_mm["h"])
	s = THUMB / (TILE_CELLS * max(cw, ch))          # px per mm of the main image
	half = THUMB // 2
	tw_w, lab_h, pad, head = THUMB + half + 16, 50, 6, 72
	n = len(rows)
	cols = min(5, max(1, n))
	nr = (n + cols - 1) // cols
	tile_h = THUMB + lab_h + 2 * pad
	W, H = cols * tw_w, head + nr * tile_h
	sheet = np.full((H, W, 3), 255, np.uint8)
	texts = []
	for k, e in enumerate(rows):
		r, c = divmod(k, cols)
		x0, y0 = c * tw_w, head + r * tile_h
		cv2.rectangle(sheet, (x0 + 2, y0 + 2), (x0 + tw_w - 3, y0 + tile_h - 3), (215, 215, 215), 1)
		known = bool(e.get("pose_known")) and e.get("theta_deg") is not None
		pid = e["piece"]
		try:
			im = _piece_image(project, pid, e["theta_deg"] if known else 0.0, _body_center(project.shape(pid)), THUMB, s)
		except Exception:  # noqa: BLE001 - a broken crop must not drop the sheet
			im = None
		_paste(sheet, x0 + pad, y0 + pad, im)
		if known:
			g = e.get("ghost")
			if g:
				P = np.asarray(g, float) * np.array([cw, ch]) * s + np.array([x0 + pad, y0 + pad]) + THUMB / 2.0
				cv2.polylines(sheet, [np.round(P * 4).astype(np.int32).reshape(-1, 1, 2)], True, (200, 160, 0), 1,
							  cv2.LINE_AA, shift=2)
			tx = x0 + pad + THUMB // 2
			cv2.fillPoly(sheet, [np.array([[tx, y0 + pad], [tx - 7, y0 + pad + 11], [tx + 7, y0 + pad + 11]], np.int32)],
						 (0, 0, 200), cv2.LINE_AA)
		tid = e.get("twin_id")
		if tid and tid in project.pieces:
			tim = None
			try:
				tp = project.piece(tid)
				tz = None
				if tp.estado == "colocada":
					from src import render
					tz = render.registered_theta(project, tid)
				tz = tz if tz is not None else tp.theta_deg
				tim = _piece_image(project, tid, tz if tz is not None else 0.0, _body_center(project.shape(tid)), half,
								   s / 2.0)
			except Exception:  # noqa: BLE001
				tim = None
			xt = x0 + pad + THUMB + 4
			_paste(sheet, xt, y0 + pad + 20, tim)
			texts.append(((xt, y0 + pad), "gémea colocada", half + 4, 13, (90, 90, 90)))
			tc = e.get("twin_cell")
			texts.append(((xt, y0 + pad + 24 + half), f"{tid}" + (f" ({tc[0]},{tc[1]})" if tc else ""), half + 4, 13,
						  (90, 90, 90)))
		cell = f"({e['cell'][0]},{e['cell'][1]})" if e.get("cell") else "?"
		t1 = f"{e['ordem']}. lote {_fmt(e.get('lote'))} · nº {_fmt(e.get('n_no_lote'))} → {cell}"
		t2 = f"{e['origin']} {e['decision']} · pose {_pose_txt(e)} · {pid}"
		ly = y0 + pad + THUMB + 2
		texts.append(((x0 + pad, ly), t1, tw_w - 2 * pad, 19, (0, 0, 0)))
		texts.append(((x0 + pad, ly + 24), t2, tw_w - 2 * pad, 15,
					  (0, 120, 0) if e["decision"] in ("aceite", "colocavel") else (170, 90, 0)))
	pil = Image.fromarray(np.ascontiguousarray(sheet[..., ::-1]))
	d = ImageDraw.Draw(pil)
	_fit_text(d, (10, 6), f"lote {lote}: {n} peças a ir buscar", W - 20, 24, (0, 0, 0))
	help_ = ("peça rodada como fica no tabuleiro (triângulo vermelho = topo do tabuleiro; contorno ciano = gémea "
			 "rodada para a célula); à direita, a gémea colocada como está no tabuleiro")
	if d.textlength(help_, font=_font(13)) <= W - 20:
		_fit_text(d, (10, 40), help_, W - 20, 13, (80, 80, 80))
	else:
		cut = help_.index("; à direita")
		_fit_text(d, (10, 36), help_[:cut + 1], W - 20, 13, (80, 80, 80))
		_fit_text(d, (10, 52), help_[cut + 2:], W - 20, 13, (80, 80, 80))
	for xy, t, w, size, col in texts:
		_fit_text(d, xy, t, w, size, col)
	return np.ascontiguousarray(np.asarray(pil)[..., ::-1])


def write_fetch(project, entries: list, rest: list, notes: list, suppressed: Optional[list] = None) -> None:
	"""Write ``fetch.md``, ``fetch.json`` and one ``fetch_<lote>.jpg`` per bag with entries.

	``suppressed``: twin queries not proposed because of a lone candidate (``fetch.json`` ->
	``suprimidas``, records ``{origin, query, piece, lote, n_no_lote, cell, candidate, d1_mm,
	decision_shape, reason}``); they get no tile in the sheets.
	"""
	import cv2
	suppressed = list(suppressed or [])
	with open(project.p("fetch.md"), "w", encoding="utf-8", newline="\n") as f:
		f.write(render_fetch_md(project, entries, rest, notes, suppressed))
	with open(project.p("fetch.json"), "w", encoding="utf-8", newline="\n") as f:
		json.dump({"t": _dt.datetime.now().isoformat(timespec="seconds"), "entries": entries, "rest": rest,
				   "notes": notes, "suprimidas": suppressed}, f, ensure_ascii=False, indent=1, default=float)
	for old in glob.glob(project.p("fetch_*.jpg")):
		os.remove(old)
	by_lote = {}
	for e in entries:
		if e.get("piece"):
			by_lote.setdefault(e.get("lote"), []).append(e)
	for lote, rows in by_lote.items():
		sheet = _fetch_sheet(project, lote, rows)
		cv2.imencode(".jpg", sheet, [cv2.IMWRITE_JPEG_QUALITY, 88])[1].tofile(project.p(f"fetch_{lote}.jpg"))


def print_summary(project, entries: list) -> None:
	for e in entries:
		cell = f"({e['cell'][0]},{e['cell'][1]})" if e.get("cell") else "—"
		who = e.get("piece") or e.get("section")
		pose = _pose_txt(e) if e.get("piece") else "—"
		print(f"{e['ordem']:>3}. lote {_fmt(e.get('lote'))} #{_fmt(e.get('n_no_lote'))} {who} → {cell} pose {pose} "
			  f"[{e['origin']}, {e['decision']}, margem {_fmt(e.get('margin'))}, ΔE {_fmt(e.get('dE'), 1)}]")
	st = project.stats()
	print(f"estados: {st['por_estado']}; pares {st['pares']}; buracos {st['buracos']}; borda em falta "
		  f"{st['borda_em_falta']}")
	print(f"p_twin_placed = {st['p_twin_placed']:.3f}  ({st['p_twin_placed_formula']})")
	print(f"lista: {project.p('fetch.md')}")


def main(argv=None) -> int:
	from src.ingest import add_project_args, open_project
	ap = argparse.ArgumentParser(prog="python -m src.query", description="Reavalia a memória e escreve a lista «ir buscar».")
	ap.add_argument("--lote", type=int, default=None)
	ap.add_argument("--no-image", action="store_true", help="sem desempate pela imagem (nem pair_locate)")
	add_project_args(ap)
	args = ap.parse_args(argv)
	try:
		pr = open_project(args)
		entries = run_query(pr, lote=args.lote, use_image=not args.no_image)
	except ImportError as e:
		print(f"erro: {e} (src/twin.py / src/locate.py ainda não disponíveis?)")
		return 1
	except ValueError as e:
		print(f"erro: {e}")
		return 1
	print_summary(pr, entries)
	bad = pr.check_invariants(disk=True)
	if bad:
		print("INVARIANTES VIOLADAS: " + "; ".join(bad))
		return 1
	return 0


if __name__ == "__main__":
	sys.exit(main())
