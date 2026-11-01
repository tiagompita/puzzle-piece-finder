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

``src.twin`` / ``src.locate`` are imported lazily (other milestone); tests replace them in
``sys.modules``. :func:`run_query` is the callable entry point (future GUI).
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
		   "load_fetch", "render_fetch_md", "main"]

ORIGIN_STEP = {"borda": 0, "gemeo": 1, "par": 2, "posicao_conhecida": 3, "seccao": 4}
_DECISION_RANK = {"aceite": 0, "colocavel": 0, "ambigua": 1, "proposto": 1, "confirmado": 0, "candidata": 2,
				  "por_ancorar": 2}
MAX_MISSING_BORDER = 8        # step 0 runs only when few border cells are missing (else it lists the whole pool)
MAX_BORDER_CANDIDATES = 12    # listed candidates per missing border cell without a twin silhouette
MODALITY = "silhueta_silhueta"
TOPK = 3
THUMB = 200                   # px, tile of fetch_<lote>.jpg
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
		self.art = None
		self.TwinItem, self.find_twin = _twin_api()
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
		 "reasons": [], "query": None, "pair": None, "rank": None, "score": None}
	e.update(kw)
	return e


def _from_candidate(pr, origin: str, res: dict, cell, query_id: Optional[str]) -> Optional[dict]:
	cands = res.get("candidates") or []
	if not cands or res.get("decision") not in ("aceite", "ambigua"):
		return None
	c0 = cands[0]
	img = c0.get("image") or {}
	return _entry(pr, origin, c0["id"], cell, res["decision"], margin=res.get("margin"), dE=img.get("dE"),
				  d1_mm=c0.get("d1_mm"), reasons=list(res.get("reasons") or []), query=query_id, rank=1,
				  score=c0.get("d1_mm"))


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
	listed = {e["piece"] for e in uniq if e.get("piece")}
	rest = [p.id for p in loose if p.id not in listed]
	if write:
		write_fetch(pr, uniq, rest, ctx.notes)
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


def _fmt(v, nd=2):
	if v is None:
		return "—"
	if isinstance(v, float):
		return f"{v:.{nd}f}"
	return str(v)


def render_fetch_md(project, entries: list, rest: list, notes: list) -> str:
	"""Markdown of the "go fetch" list (table + stats with the p_twin_placed formula)."""
	st = project.stats()
	L = [f"# Lista «ir buscar» — {_dt.datetime.now().isoformat(timespec='seconds')}", "",
		 f"Projeto `{project.meta['id']}`; {st['pecas']} peças; por estado {st['por_estado']}; tabuleiro "
		 f"{st['celulas_ocupadas']} ocupadas / {project.profile.cell_count()}.",
		 f"p_twin_placed = {st['p_twin_placed']:.3f} ({st['p_twin_placed_formula']}).", "",
		 "| ordem | lote | nº no lote | id | célula | origem | decisão | margem | ΔE | razões |",
		 "|---:|---:|---:|---|---|---|---|---:|---:|---|"]
	for e in entries:
		pid = e.get("piece") or e.get("section") or "—"
		cell = f"({e['cell'][0]},{e['cell'][1]})" if e.get("cell") else "—"
		why = "; ".join(str(r) for r in (e.get("reasons") or [])).replace("|", "/")
		L.append(f"| {e['ordem']} | {_fmt(e.get('lote'))} | {_fmt(e.get('n_no_lote'))} | {pid} | {cell} | "
				 f"{e['origin']} | {e['decision']} | {_fmt(e.get('margin'))} | {_fmt(e.get('dE'), 1)} | {why} |")
	L += ["", f"Ficam na memória: {len(rest)} soltas sem proposta."]
	for n in notes:
		L.append(f"- nota: {n}")
	return "\n".join(L) + "\n"


def _fetch_sheet(project, lote, rows: list) -> np.ndarray:
	import cv2
	n = len(rows)
	cols = min(6, max(1, n))
	nr = (n + cols - 1) // cols
	cap = 64
	W, H = cols * THUMB, nr * (THUMB + cap)
	sheet = np.full((H + 50, W, 3), 255, np.uint8)
	cv2.putText(sheet, f"lote {lote}: {n} pecas a ir buscar", (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2,
				cv2.LINE_AA)
	for k, e in enumerate(rows):
		r, c = divmod(k, cols)
		x0, y0 = c * THUMB, 50 + r * (THUMB + cap)
		rgba = project.crop_rgba(e["piece"])
		if rgba is not None:
			h, w = rgba.shape[:2]
			s = (THUMB - 10) / max(h, w)
			im = cv2.resize(rgba, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)
			a = im[..., 3:4].astype(float) / 255.0
			bgr = im[..., 2::-1].astype(float)
			yy, xx = y0 + (THUMB - im.shape[0]) // 2, x0 + (THUMB - im.shape[1]) // 2
			roi = sheet[yy:yy + im.shape[0], xx:xx + im.shape[1]].astype(float)
			sheet[yy:yy + im.shape[0], xx:xx + im.shape[1]] = (a * bgr + (1 - a) * roi).astype(np.uint8)
		cell = f"({e['cell'][0]},{e['cell'][1]})" if e.get("cell") else "?"
		t1 = f"{e['ordem']}. #{e.get('n_no_lote')} {e['piece']}"
		t2 = f"-> {cell} {e['origin']} {e['decision']}"
		cv2.putText(sheet, t1, (x0 + 4, y0 + THUMB + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2, cv2.LINE_AA)
		cv2.putText(sheet, t2, (x0 + 4, y0 + THUMB + 48), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 160), 1, cv2.LINE_AA)
	return sheet


def write_fetch(project, entries: list, rest: list, notes: list) -> None:
	"""Write ``fetch.md``, ``fetch.json`` and one ``fetch_<lote>.jpg`` per bag with entries."""
	import cv2
	with open(project.p("fetch.md"), "w", encoding="utf-8", newline="\n") as f:
		f.write(render_fetch_md(project, entries, rest, notes))
	with open(project.p("fetch.json"), "w", encoding="utf-8", newline="\n") as f:
		json.dump({"t": _dt.datetime.now().isoformat(timespec="seconds"), "entries": entries, "rest": rest,
				   "notes": notes}, f, ensure_ascii=False, indent=1, default=float)
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
		print(f"{e['ordem']:>3}. lote {_fmt(e.get('lote'))} #{_fmt(e.get('n_no_lote'))} {who} → {cell} "
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
