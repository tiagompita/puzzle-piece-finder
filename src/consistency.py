"""Orientation consistency of the placed pieces against their mounted neighbours (``python -m src.consistency``).

Read-only check, promoted from ``tools/diagnostico/reports/triagem_r3.py`` (``orientation_check``,
TRIAGEM-2026-11-07 §2). For every piece on the board (``colocada``, or ``posicao_conhecida`` with a
cell) whose shape has 4 corners and whose corner registration gives the cyclic assignment ``k``
(side ``i`` of the shape faces ``DIRS[(i + k) % 4]``, :func:`src.render.corner_register`), each of the
4 assignments ``k'`` is tested against the mounted orthogonal neighbours, which keep their own ``k``:
the side ``(DIRS.index(d) - k') % 4`` against the neighbour's side facing back
(:func:`src.legacy.side_compat`: F facing a neighbour, T-T / B-B, profile RMS, chord difference), and
the F sides against the cell's border directions (:func:`src.render._f_ok`).

A piece is a suspect when

* ``impossivel``: the current assignment has a T-T / B-B side (``why == 'kind'``) or an F side off
  the border while another assignment puts the F sides on it (the piece cannot sit like this);
* ``melhor_rotacao``: another assignment with the F sides right and no T-T / B-B is clearly better
  (fewer failing sides, or a much lower total cost; :data:`BETTER_FEWER_FAILS`,
  :data:`BETTER_COST_RATIO`, :data:`BETTER_COST_MM`).

Nothing is corrected: the output says which rotation would fit (``rot_alt_deg``, clockwise on the
screen like ``theta_deg``: the pose that fits is ``theta_deg + rot_alt_deg``). The rotation fix
itself is a data change (log / section anchor) after a physical check.

Poses: ``placements`` (``{pid: entry}`` as :func:`src.render.register_piece` returns, e.g. the
server's cache of ``render/placements.json``); a piece missing from it is registered on the fly
without the image (``register_piece(image=False)``, about 30 ms each) and added to the dict.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Optional

__all__ = ["BETTER_FEWER_FAILS", "BETTER_COST_RATIO", "BETTER_COST_MM", "BETTER_COST_MIN_SIDES", "FAIL_COST_MM", "GRAUS",
		   "checked_ids", "evaluate", "suspects", "summary", "suspects_near", "suspects_lines", "rot_text", "format_item", "main"]

BETTER_FEWER_FAILS = 1      # an alternative is better with at least this many fewer failing sides ...
BETTER_COST_RATIO = 0.6     # ... or, else, with a total cost at most this share of the current one ...
BETTER_COST_MM = 0.5        # ... and at least this much lower (mm): both, so a small cost on few sides does not flip
BETTER_COST_MIN_SIDES = 2   # ... the cost-only rule needs at least this many mounted neighbours: with one side, a
							# T-B piece always has another T-B option and the cost of one side is no evidence
							# (P0147 (2,61), 1 neighbour, 0 failures, 2,2 -> 1,3 mm: the only cost-only hit of the 607)
FAIL_COST_MM = 5.0          # cost (mm) of a side that cannot fit at all (F facing a neighbour, T-T / B-B) in the totals;
							# above any T-B cost seen (RMS + 0.5 dL, failing T-B sides of the 607 placed: <= 3.2)
GRAUS = ("impossivel", "melhor_rotacao")
_OPP = {"N": "S", "S": "N", "E": "W", "W": "E"}
_STATES = ("colocada", "posicao_conhecida")


# ---------------------------------------------------------------- helpers (pure)
def rot_text(deg: int) -> str:
	"""``90`` -> ``'+90°'``, ``-90`` -> ``'−90°'``, ``180`` -> ``'180°'``."""
	deg = int(deg)
	if deg == 180:
		return "180°"
	return f"+{deg}°" if deg > 0 else f"−{-deg}°" if deg < 0 else "0°"


def _rot_deg(k_alt: int, k0: int) -> int:
	"""Rotation (deg, clockwise on the screen) from assignment ``k0`` to ``k_alt``: +1 in ``k`` = +90°."""
	return {0: 0, 1: 90, 2: 180, 3: -90}[(int(k_alt) - int(k0)) % 4]


def _num(v: float, nd: int = 2) -> str:
	return f"{v:.{nd}f}".replace(".", ",")


def _fail_text(f: dict) -> str:
	"""One failing side as text: ``'W B↔B com P0087'``, ``'N RMS 2,17 mm com P0807'``."""
	d, q, why = f["dir"], f["piece"], f["why"]
	if why == "kind":
		return f"{d} {f['kinds']} com {q}"
	if why == "F":
		return f"{d} lado F contra {q} ({f['kinds']})"
	if why == "rms":
		return f"{d} RMS {_num(f['rms'])} mm com {q}"
	return f"{d} ΔL {_num(f['dl'])} mm com {q}"


def _side_cost(r: dict) -> float:
	return FAIL_COST_MM if r["why"] in ("F", "kind") else float(r["cost"])


def _is_better(alt: dict, cur: dict) -> bool:
	"""``alt`` clearly better than ``cur`` (see the module docstring)."""
	if alt["n_fail"] <= cur["n_fail"] - BETTER_FEWER_FAILS:
		return True
	return (cur["n"] >= BETTER_COST_MIN_SIDES and alt["n_fail"] <= cur["n_fail"]
			and alt["cost"] <= BETTER_COST_RATIO * cur["cost"] and cur["cost"] - alt["cost"] >= BETTER_COST_MM)


def _grade(res: dict, k0: int):
	"""``(grau | None, k_alt | None)`` from the per-assignment results ``res[k]``."""
	cur = res[k0]
	valid = [k for k in range(4) if k != k0 and res[k]["f_ok"] and not res[k]["n_kind"]]
	best = min(valid, key=lambda k: (res[k]["n_fail"], res[k]["cost"])) if valid else None
	f_fixable = any(res[k]["f_ok"] for k in range(4) if k != k0)
	if cur["n_kind"] or (not cur["f_ok"] and f_fixable):
		return "impossivel", best
	if best is not None and _is_better(res[best], cur):
		return "melhor_rotacao", best
	return None, best


# ---------------------------------------------------------------- project
def checked_ids(project) -> list:
	"""Pieces on the board: ``colocada`` or ``posicao_conhecida`` with a cell (sorted)."""
	return sorted(pid for pid, p in project.pieces.items() if p.estado in _STATES and p.celula is not None)


def _k_of(project, pid: str, placements: dict, cache: dict) -> Optional[int]:
	"""Cyclic assignment ``k`` of the corner registration (registered on the fly if missing), or None."""
	from src import render
	e = placements.get(pid)
	if e is None:
		e = render.register_piece(project, pid, art=None, image=False, _cache=cache)
		if "error" in e:
			return None
		e["key"] = render._entry_key(project, pid)
		e["image_used"] = False
		placements[pid] = e
	c = e.get("corner") or {}
	return None if c.get("k") is None else int(c["k"])


def _assignments(project, pid: str, k0: int, kmap: dict, mounted: dict) -> dict:
	"""Per assignment ``k``: ``{f_ok, fails, n_fail, n_kind, cost, n}`` against the mounted neighbours."""
	from src import render
	from src.legacy import _STEP, side_compat
	sh = project.shape(pid)
	cell = tuple(project.piece(pid).celula)
	flat = project.profile.flat_directions(*cell)
	nbs = []
	for d in render.DIRS:
		dl, dc = _STEP[d]
		q = mounted.get((cell[0] + dl, cell[1] + dc))
		if q is None or q == pid or kmap.get(q) is None:
			continue
		sq = project.shape(q)
		if sq is None or not sq.ok or len(sq.sides) != 4:
			continue
		nbs.append((d, q, sq.sides[(render.DIRS.index(_OPP[d]) - kmap[q]) % 4]))
	res = {}
	for k in range(4):
		fails, cost, n_kind = [], 0.0, 0
		for d, q, sq_side in nbs:
			sa = sh.sides[(render.DIRS.index(d) - k) % 4]
			r = side_compat(sa, sq_side)
			cost += _side_cost(r)
			if not r["ok"]:
				n_kind += r["why"] == "kind"
				fails.append(dict(dir=d, piece=q, why=r["why"], kinds=f"{sa.kind}↔{sq_side.kind}",
								  rms=float(r["rms"]), dl=float(r["dl"])))
		res[k] = dict(f_ok=bool(render._f_ok(sh, k, flat)), fails=fails, n_fail=len(fails), n_kind=n_kind,
					  cost=float(cost), n=len(nbs))
	return res


def _item(project, pid: str, k0: int, res: dict, grau: str, ka: Optional[int]) -> dict:
	"""Output row of one suspect."""
	cur = res[k0]
	falhas = [_fail_text(f) for f in cur["fails"]]
	if not cur["f_ok"]:
		falhas.insert(0, "lados F fora da borda")
	p = project.piece(pid)
	item = dict(piece=pid, cell=list(p.celula), estado=p.estado, grau=grau, falhas=falhas, k0=int(k0),
				k_alt=None if ka is None else int(ka), rot_alt_deg=None, n_falhas0=cur["n_fail"], n_falhas_alt=None,
				custo0=round(cur["cost"], 3), custo_alt=None, n_vizinhas=cur["n"], falhas_alt=[],
				texto="nenhuma rotação sem lados T↔T / B↔B")
	if ka is not None:
		alt = res[ka]
		rot = _rot_deg(ka, k0)
		item.update(rot_alt_deg=rot, n_falhas_alt=alt["n_fail"], custo_alt=round(alt["cost"], 3),
					falhas_alt=[_fail_text(f) for f in alt["fails"]])
		na, n0 = alt["n_fail"], cur["n_fail"] + (0 if cur["f_ok"] else 1)
		if na == 0:
			item["texto"] = f"{rot_text(rot)} fica sem falhas ({n0} → 0)"
		else:
			item["texto"] = f"{rot_text(rot)} fica com {na} falha{'s' if na > 1 else ''} ({n0} → {na})"
		if na == n0:
			item["texto"] += f", custo {_num(cur['cost'], 1)} → {_num(alt['cost'], 1)} mm"
	return item


def evaluate(project, placements: Optional[dict] = None, *, pieces=None) -> dict:
	"""``{summary, items}``: :func:`summary` and :func:`suspects` of one pass (see the module docstring).

	``pieces``: only these are checked and reported (their mounted neighbours are registered too,
	for their ``k``); default every piece of :func:`checked_ids`.

	A T-T / B-B side is a conflict of two pieces. A piece whose only fault is such a conflict with a
	neighbour that is itself ``impossivel`` and fixed by its own rotation (and that no rotation of its
	own fixes) is not reported: the neighbour's rotation removes the conflict (``n_explicadas``).
	"""
	placements = {} if placements is None else placements
	ids = checked_ids(project)
	if pieces is not None:
		want = set(pieces)
		ids = [pid for pid in ids if pid in want]
	from src.legacy import _STEP
	mounted = {tuple(p.celula): pid for pid, p in project.pieces.items() if p.estado == "colocada" and p.celula is not None}
	cache, kmap, graded = {}, {}, {}

	def k_of(pid):
		if pid not in kmap:
			sh = project.shape(pid)
			kmap[pid] = _k_of(project, pid, placements, cache) if sh is not None and sh.ok and len(sh.corners) == 4 else None
		return kmap[pid]

	def grade(pid):
		"""``(k0, res, grau, k_alt)`` or None (no corners / no ``k``)."""
		if pid not in graded:
			k0 = k_of(pid)
			if k0 is None:
				graded[pid] = None
			else:
				cell = tuple(project.piece(pid).celula)
				for dl, dc in _STEP.values():
					q = mounted.get((cell[0] + dl, cell[1] + dc))
					if q is not None:
						k_of(q)
				res = _assignments(project, pid, k0, kmap, mounted)
				graded[pid] = (k0, res) + _grade(res, k0)
		return graded[pid]

	def explained(pid, k0, res):
		cur = res[k0]
		kinds = [f for f in cur["fails"] if f["why"] == "kind"]
		if not cur["f_ok"] or not kinds:
			return False
		for f in kinds:
			g = grade(f["piece"]) if project.piece(f["piece"]).estado in _STATES else None
			if g is None or g[2] != "impossivel" or g[3] is None:
				return False
		return True

	items, n_ok, n_none, n_nb, n_expl = [], 0, 0, 0, 0
	for pid in ids:
		g = grade(pid)
		if g is None:
			n_none += 1
			continue
		n_ok += 1
		k0, res, grau, ka = g
		n_nb += res[k0]["n"] > 0
		if grau is None:
			continue
		if grau == "impossivel" and ka is None and explained(pid, k0, res):
			n_expl += 1
			continue
		items.append(_item(project, pid, k0, res, grau, ka))
	items.sort(key=lambda it: (GRAUS.index(it["grau"]),
							   -(it["custo0"] - (it["custo_alt"] if it["custo_alt"] is not None else it["custo0"])), it["piece"]))
	summ = dict(n_colocadas=len(ids), n_verificadas=n_ok, n_sem_cantos=n_none, n_com_vizinhas=n_nb,
				n_impossivel=sum(it["grau"] == "impossivel" for it in items),
				n_melhor_rotacao=sum(it["grau"] == "melhor_rotacao" for it in items), n_explicadas=n_expl)
	return {"summary": summ, "items": items}


def suspects(project, placements: Optional[dict] = None, *, pieces=None) -> list:
	"""Suspect pieces ``[{piece, cell, grau, falhas, k0, k_alt, rot_alt_deg, n_falhas0, n_falhas_alt, custo0,
	custo_alt, n_vizinhas, texto, ...}]``, ``impossivel`` first, then by cost gain (see :func:`evaluate`)."""
	return evaluate(project, placements, pieces=pieces)["items"]


def summary(project, placements: Optional[dict] = None, *, pieces=None) -> dict:
	"""``{n_colocadas, n_verificadas, n_sem_cantos, n_com_vizinhas, n_impossivel, n_melhor_rotacao}``."""
	return evaluate(project, placements, pieces=pieces)["summary"]


def suspects_near(project, cells, placements: Optional[dict] = None) -> list:
	"""Suspects among the pieces in ``cells`` and in their 4-neighbours (the check after a confirmation)."""
	want = set()
	by_cell = {tuple(p.celula): pid for pid, p in project.pieces.items() if p.estado in _STATES and p.celula is not None}
	for c in cells:
		c = (int(c[0]), int(c[1]))
		for x in [c] + project.board.neighbours(c):
			if x in by_cell:
				want.add(by_cell[x])
	if not want:
		return []
	return suspects(project, placements, pieces=sorted(want))


def suspects_lines(project, cells) -> list:
	"""Text lines of :func:`suspects_near` for the confirmation CLI (never raises: a failure is one line).

	Arrows and the minus sign are written in ASCII (``<->``, ``->``, ``-``): the confirmation CLI prints to
	the console as it is (cp1252 on Windows)."""
	try:
		items = suspects_near(project, cells)
	except Exception as e:  # noqa: BLE001 - the check is informative, it must not break a confirmation
		return [f"Suspeitas novas: verificação falhou ({e})"]
	if not items:
		return ["Suspeitas novas: nenhuma (peças afetadas e vizinhas)"]
	lines = [f"Suspeitas novas: {len(items)} (peças afetadas e vizinhas; nada foi alterado)"] + ["  " + format_item(it) for it in items]
	return [ln.replace("↔", "<->").replace("→", "->").replace("−", "-").replace("—", "-").replace("Δ", "d") for ln in lines]


def format_item(it: dict) -> str:
	"""One suspect as a line of text."""
	cell = f"({it['cell'][0]},{it['cell'][1]})"
	extra = ""
	if "custo" not in it["texto"]:
		extra = f"; custo {_num(it['custo0'], 1)}" + (f" → {_num(it['custo_alt'], 1)}" if it["custo_alt"] is not None else "") + " mm"
	return (f"{it['piece']} {cell} {it['grau']}: {'; '.join(it['falhas']) or 'sem falhas'} — {it['texto']}{extra} "
			f"({it['n_vizinhas']} vizinhas)")


# ---------------------------------------------------------------- CLI
def main(argv=None) -> int:
	from src.ingest import DEFAULT_PROJECT
	from src.state import Project
	ap = argparse.ArgumentParser(prog="python -m src.consistency",
								 description="Peças colocadas com uma orientação impossível ou claramente pior que outra (só leitura).")
	ap.add_argument("--project", default=DEFAULT_PROJECT, help="pasta do projeto (projects/<id>)")
	ap.add_argument("--json", action="store_true", help="saída JSON {summary, items}")
	ap.add_argument("--pieces", nargs="+", default=None, metavar="P", help="só estas peças")
	args = ap.parse_args(argv)
	if hasattr(sys.stdout, "reconfigure"):
		sys.stdout.reconfigure(encoding="utf-8")      # ↔, −, → on a cp1252 console
	pr = Project.open(args.project)
	t0 = time.time()
	from src import render
	pl = dict(render.load_placements(pr).get("placements") or {})
	pl = {pid: e for pid, e in pl.items() if pid in pr.pieces and e.get("key") == render._entry_key(pr, pid)}
	r = evaluate(pr, pl, pieces=args.pieces)
	dt = time.time() - t0
	if args.json:
		print(json.dumps(r, ensure_ascii=False, indent=1))
		return 0
	s = r["summary"]
	print(f"{s['n_colocadas']} peças no tabuleiro, {s['n_verificadas']} verificadas ({s['n_com_vizinhas']} com vizinhas montadas), "
		  f"{s['n_sem_cantos']} sem cantos; suspeitas: {s['n_impossivel']} impossível, {s['n_melhor_rotacao']} melhor rotação "
		  f"({dt:.1f} s)")
	for it in r["items"]:
		print("  " + format_item(it))
	return 0


if __name__ == "__main__":
	sys.exit(main())
