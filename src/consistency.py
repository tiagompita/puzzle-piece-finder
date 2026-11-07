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

A piece is also a suspect, grade ``recorte`` (its silhouette, not its pose), when

* its twin (:meth:`src.profile.PuzzleProfile.twin`) is on the board and the twin's shape, aligned by
  :func:`src.shape.free_dist`, leaves a contour point of the piece farther than :data:`TWIN_LOCAL_MAX_MM`
  from it (``nn_max``: a local bite or a lost tab that the global RMS hides), or the piece has no 4
  corners while its twin is there (signal (a) of docs/diagnostico/segmentacao/COMIDO.md §5);
* the segmentation flagged it with ``flags.suspeita_recorte.razoes`` containing ``baia`` (a tab / bay
  outside the contour).

Cells of a known exception of the die symmetry (:data:`TWIN_EXCEPTIONS`, or ``symmetry.excecoes`` of the
profile) are still listed, with the exception as text. Pieces with a manual contour (``manual_override``)
are left out of ``recorte``.

Nothing is corrected: the output says which rotation would fit (``rot_alt_deg``, clockwise on the
screen like ``theta_deg``: the pose that fits is ``theta_deg + rot_alt_deg``). The rotation fix
itself is a data change (log / section anchor) after a physical check.

Poses: ``placements`` (``{pid: entry}`` as :func:`src.render.register_piece` returns, e.g. the
server's cache of ``render/placements.json``); a piece missing from it is registered on the fly
without the image (``register_piece(image=False)``, about 30 ms each) and added to the dict.

False alarms (docs/diagnostico/reports/FALSOS_ALARMES.md): the user can mark a suspect ``(piece, grau)`` as a
false alarm (:meth:`src.state.Project.dismiss_suspect`, event ``suspect_dismissed``). The mark carries the
:func:`suspect_signature` of the item it was made on (cell, 90° class ``k0``, shape class and chords, manual
contour / pose, mounted neighbours, twin and its residual for ``recorte``); while the current item has the same
signature it is left out of ``items`` and of the counts, and as soon as any of those changes the mark is
``obsoleto`` and the suspect is reported again. The marks are the only thing this module ever writes (CLI
``--falso-alarme`` / ``--restaurar``), through the log.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from typing import Optional

from src.state import SUSPECT_GRAUS

__all__ = ["BETTER_FEWER_FAILS", "BETTER_COST_RATIO", "BETTER_COST_MM", "BETTER_COST_MIN_SIDES", "FAIL_COST_MM", "GRAUS",
		   "TWIN_LOCAL_MAX_MM", "TWIN_EXCEPTIONS", "SIGNATURE_HEX", "twin_local_residual", "twin_exception", "suspect_signature",
		   "checked_ids", "evaluate", "suspects", "summary", "suspects_near", "suspects_lines", "rot_text", "format_item",
		   "format_falso", "main"]

BETTER_FEWER_FAILS = 1      # an alternative is better with at least this many fewer failing sides ...
BETTER_COST_RATIO = 0.6     # ... or, else, with a total cost at most this share of the current one ...
BETTER_COST_MM = 0.5        # ... and at least this much lower (mm): both, so a small cost on few sides does not flip
BETTER_COST_MIN_SIDES = 2   # ... the cost-only rule needs at least this many mounted neighbours: with one side, a
							# T-B piece always has another T-B option and the cost of one side is no evidence
							# (P0147 (2,61), 1 neighbour, 0 failures, 2,2 -> 1,3 mm: the only cost-only hit of the 607)
FAIL_COST_MM = 5.0          # cost (mm) of a side that cannot fit at all (F facing a neighbour, T-T / B-B) in the totals;
							# above any T-B cost seen (RMS + 0.5 dL, failing T-B sides of the 607 placed: <= 3.2)
TWIN_LOCAL_MAX_MM = 1.75   # recorte: max distance of a contour point to the aligned twin (COMIDO.md §5: 63 controls
							# <= 1.31, 5 eaten silhouettes >= 2.17; midpoint)
# Known exceptions of the die symmetry, by profile id, until they move to ``symmetry.excecoes`` of puzzle.json:
# the c32|c33 cut of rows 1-3 / 45-47 of the Alpes is not symmetric (ORIENTACOES-2026-11-07 §D; pending 6).
TWIN_EXCEPTIONS = {"alpes": [{"cols": [32, 33], "rows": [[1, 3], [45, 47]],
							  "texto": "corte c32|c33 não simétrico (exceção por confirmar)"}]}
GRAUS = SUSPECT_GRAUS               # ("impossivel", "melhor_rotacao", "recorte"), also validated by the state
SIGNATURE_HEX = 12                 # suspect_signature: leading hex digits of the sha1
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


def twin_local_residual(a, b) -> Optional[dict]:
	"""``{rms_mm, nn_p95_mm, nn_max_mm}`` of shape ``a`` against shape ``b`` aligned by :func:`src.shape.free_dist`
	(cyclic shift + rotation of the 512-point ``z``): distance of each point of ``a`` to the nearest point of the
	aligned ``b``. None if a shape is missing or has no ``z``."""
	import numpy as np
	from src.shape import free_dist
	if a is None or b is None or getattr(a, "z", None) is None or getattr(b, "z", None) is None:
		return None
	rms, s, phi = free_dist(a, b)
	zb = np.roll(b.z, -s) * np.exp(1j * np.radians(phi))
	nn = np.abs(a.z[:, None] - zb[None, :]).min(1)
	return {"rms_mm": float(rms), "nn_p95_mm": float(np.percentile(nn, 95)), "nn_max_mm": float(nn.max())}


def twin_exception(profile, cell) -> Optional[str]:
	"""Text of the known symmetry exception covering ``cell`` (profile ``symmetry.excecoes``, else
	:data:`TWIN_EXCEPTIONS` by profile id), or None."""
	exc = (getattr(profile, "symmetry", None) or {}).get("excecoes")
	if exc is None:
		exc = TWIN_EXCEPTIONS.get(getattr(profile, "id", None), [])
	l, c = int(cell[0]), int(cell[1])
	for e in exc or []:
		if c in [int(v) for v in e.get("cols", [])] and any(int(a) <= l <= int(b) for a, b in e.get("rows", [])):
			return str(e.get("texto") or "exceção da simetria")
	return None


def _bay_mm2(flag: dict) -> Optional[float]:
	"""Area of the ``baia`` reason of a ``suspeita_recorte`` flag (key not fixed yet: ``baia_mm2`` or ``baia.mm2``)."""
	v = flag.get("baia_mm2")
	if v is None and isinstance(flag.get("baia"), dict):
		v = flag["baia"].get("mm2")
	return None if v is None else float(v)


def _step(v: float, step: float) -> float:
	"""``v`` rounded to a multiple of ``step`` (4 decimals, so 0.05 steps print stably)."""
	return round(round(float(v) / step) * step, 4)


def _pose_manual(p):
	"""The piece's manual pose (``Piece.pose_manual``, :meth:`src.state.Project.set_pose`) for
	:func:`suspect_signature`: ``{theta_deg (0.1°), dx_mm, dy_mm (0.05 mm)}``, or None (its time stamp, note and
	pivot are left out: setting the same pose again keeps the signature)."""
	pm = getattr(p, "pose_manual", None)
	if not isinstance(pm, dict):
		return None
	return {"theta_deg": _step(pm.get("theta_deg") or 0.0, 0.1), "dx_mm": _step(pm.get("dx_mm") or 0.0, 0.05),
			"dy_mm": _step(pm.get("dy_mm") or 0.0, 0.05)}


def suspect_signature(item: dict, project, *, k0: Optional[int] = None) -> str:
	"""Short sha1 (:data:`SIGNATURE_HEX` hex) of what a suspect was seen with, for the false-alarm marks.

	Canonical JSON of ``{cell, k0, grau, cls, chords (0.1 mm), contorno_manual, pose_manual, vizinhas, gemea,
	nn_max_mm (0.1 mm)}``: ``vizinhas`` = the ``colocada`` piece id (or null) on N / E / S / W of the cell;
	``gemea`` / ``nn_max_mm`` only for ``recorte`` (null otherwise). ``k0`` is the 90° class of the corner
	registration: a small change of ``theta_deg`` keeps it, a quarter turn does not. ``k0`` (keyword) overrides
	``item['k0']`` (``recorte`` items carry ``k0 = None``; :func:`evaluate` passes the registration's ``k``).
	Pure: reads the project, never writes."""
	from src.legacy import _STEP
	from src.overrides import is_manual
	p = project.piece(item["piece"])
	l, c = int(item["cell"][0]), int(item["cell"][1])
	k = item.get("k0") if k0 is None else k0
	viz = {}
	for d in ("N", "E", "S", "W"):
		dl, dc = _STEP[d]
		q = None
		if project.profile.in_grid(l + dl, c + dc):
			cellv = project.board[(l + dl, c + dc)]
			q = cellv["peca_id"] if cellv["estado"] == "colocada" else None
		viz[d] = q
	rec = item["grau"] == "recorte"
	nn = item.get("nn_max_mm") if rec else None
	data = {"cell": [l, c], "k0": None if k is None else int(k), "grau": item["grau"], "cls": p.cls or "",
			"chords": [round(float(x), 1) for x in (p.chords_mm or [])], "contorno_manual": bool(is_manual(p)),
			"pose_manual": _pose_manual(p), "vizinhas": viz, "gemea": item.get("gemea") if rec else None,
			"nn_max_mm": None if nn is None else round(float(nn), 1)}
	js = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
	return hashlib.sha1(js.encode("utf-8")).hexdigest()[:SIGNATURE_HEX]


def _recorte_items(project, ids: list) -> list:
	"""``recorte`` suspects among ``ids`` (see the module docstring); pure reads of the project."""
	from src.overrides import is_manual
	by_cell = {tuple(p.celula): pid for pid, p in project.pieces.items() if p.estado in _STATES and p.celula is not None}
	out = []
	for pid in ids:
		p = project.piece(pid)
		if is_manual(p):
			continue
		falhas, extra = [], {}
		sh = project.shape(pid)
		tc = project.profile.twin(*p.celula)
		tw = by_cell.get(tuple(tc)) if tc is not None else None
		tsh = project.shape(tw) if tw is not None and tw != pid else None
		if tsh is not None and tsh.ok:
			if sh is None or not sh.ok or len(sh.corners) != 4:
				falhas.append("silhueta sem 4 cantos")
			else:
				r = twin_local_residual(sh, tsh)
				if r is not None and r["nn_max_mm"] > TWIN_LOCAL_MAX_MM:
					falhas.append(f"gémea local {_num(r['nn_max_mm'])} mm")
					extra = {"nn_max_mm": round(r["nn_max_mm"], 3), "rms_mm": round(r["rms_mm"], 3)}
		sr = (p.flags or {}).get("suspeita_recorte") or {}
		bay = "baia" in (sr.get("razoes") or [])
		if bay:
			a = _bay_mm2(sr)
			falhas.append("tab/baía fora do contorno" + (f" ({_num(a, 1)} mm²)" if a is not None else ""))
		if not falhas:
			continue
		exc = twin_exception(project.profile, p.celula)
		if exc and not bay:
			texto = exc
		elif bay and len(falhas) == 1:
			texto = falhas[0]
		else:
			texto = "silhueta longe da gémea: recorte a rever (scan/contorno)"
		item = dict(piece=pid, cell=list(p.celula), estado=p.estado, grau="recorte", falhas=falhas, texto=texto,
					gemea=tw, nn_max_mm=None, rms_mm=None, excecao=exc, k0=None, k_alt=None, rot_alt_deg=None,
					n_falhas0=len(falhas), n_falhas_alt=None, custo0=None, custo_alt=None, n_vizinhas=None, falhas_alt=[])
		item.update(extra)
		out.append(item)
	return out


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


def evaluate(project, placements: Optional[dict] = None, *, pieces=None, dismissed: Optional[dict] = None,
			 incluir_falsos: bool = False, incluir_pose_manual: bool = False) -> dict:
	"""``{summary, items, falsos_alarmes}``: :func:`summary` and :func:`suspects` of one pass (see the module
	docstring).

	``pieces``: only these are checked and reported (their mounted neighbours are registered too,
	for their ``k``); default every piece of :func:`checked_ids`.

	A T-T / B-B side is a conflict of two pieces. A piece whose only fault is such a conflict with a
	neighbour that is itself ``impossivel`` and fixed by its own rotation (and that no rotation of its
	own fixes) is not reported: the neighbour's rotation removes the conflict (``n_explicadas``).

	Every item carries ``assinatura`` (:func:`suspect_signature`). ``dismissed``: the false-alarm marks
	``{(piece, grau): {assinatura, cell, nota, t}}``, default ``project.falsos_alarmes``. An item whose mark has
	the same signature gets ``falso_alarme = {t, nota}`` and leaves ``items`` (kept, marked, with
	``incluir_falsos``); it never counts in ``summary`` (the summary does not depend on ``incluir_falsos``).
	``falsos_alarmes``: one row per mark (of the checked pieces when ``pieces`` is given)
	``{piece, grau, cell, t, nota, assinatura, assinatura_atual, estado, obsoleto}``; ``estado``: ``ativo``
	(hides the current item), ``obsoleto`` (the piece is flagged with that grade under another signature: it
	is reported again) or ``sem_suspeita`` (not flagged with that grade now; the mark waits).
	``summary`` adds ``n_falsos_alarmes`` (active) and ``n_falsos_alarmes_obsoletos``.

	Manual pose (``Piece.pose_manual``, :func:`src.render.manual_pose`): the user placed the piece by hand, so
	by default its orientation grades (``impossivel`` / ``melhor_rotacao``) are not reported nor counted (as
	``recorte`` leaves out manual contours); ``n_pose_manual`` counts the checked pieces with one. With
	``incluir_pose_manual`` they are graded with the ``k`` of the manual pose (``corner.k`` of its entry) and
	reported. Every item of such a piece carries ``pose_manual: True``. As a neighbour, a piece always counts
	with its effective pose (the manual one).
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

	from src.render import manual_pose
	with_pm = {pid for pid in ids if manual_pose(project, pid) is not None}
	items, n_ok, n_none, n_nb, n_expl = [], 0, 0, 0, 0
	for pid in ids:
		g = grade(pid)
		if g is None:
			n_none += 1
			continue
		n_ok += 1
		k0, res, grau, ka = g
		n_nb += res[k0]["n"] > 0
		if grau is None or (pid in with_pm and not incluir_pose_manual):
			continue
		if grau == "impossivel" and ka is None and explained(pid, k0, res):
			n_expl += 1
			continue
		items.append(_item(project, pid, k0, res, grau, ka))
	items += _recorte_items(project, ids)
	for it in items:
		if it["piece"] in with_pm:
			it["pose_manual"] = True
		it["assinatura"] = suspect_signature(it, project, k0=k_of(it["piece"]) if it["grau"] == "recorte" else None)
	items, falsos = _apply_dismissed(items, getattr(project, "falsos_alarmes", {}) if dismissed is None else dismissed,
									 None if pieces is None else set(ids))
	shown = items if incluir_falsos else [it for it in items if "falso_alarme" not in it]
	counted = [it for it in items if "falso_alarme" not in it]

	def order(it):
		if it["grau"] == "recorte":     # real bites first, then the known exceptions; larger residual first
			return (GRAUS.index("recorte"), it.get("excecao") is not None, -(it.get("nn_max_mm") or 0.0), it["piece"])
		return (GRAUS.index(it["grau"]), False,
				-(it["custo0"] - (it["custo_alt"] if it["custo_alt"] is not None else it["custo0"])), it["piece"])
	shown.sort(key=order)
	summ = dict(n_colocadas=len(ids), n_verificadas=n_ok, n_sem_cantos=n_none, n_com_vizinhas=n_nb,
				n_impossivel=sum(it["grau"] == "impossivel" for it in counted),
				n_melhor_rotacao=sum(it["grau"] == "melhor_rotacao" for it in counted), n_explicadas=n_expl,
				n_recorte=sum(it["grau"] == "recorte" for it in counted),
				n_falsos_alarmes=sum(f["estado"] == "ativo" for f in falsos),
				n_falsos_alarmes_obsoletos=sum(f["obsoleto"] for f in falsos), n_pose_manual=len(with_pm))
	return {"summary": summ, "items": shown, "falsos_alarmes": falsos}


def _apply_dismissed(items: list, dismissed: dict, only: Optional[set]):
	"""Mark the items hidden by a false-alarm mark (``falso_alarme``) and list the marks (see :func:`evaluate`).
	``only``: the checked pieces when :func:`evaluate` got ``pieces`` (marks of other pieces are not listed)."""
	cur = {(it["piece"], it["grau"]): it for it in items}
	falsos = []
	for (pid, grau), rec in sorted((dismissed or {}).items()):
		if only is not None and pid not in only:
			continue
		it = cur.get((pid, grau))
		if it is None:
			estado = "sem_suspeita"
		elif it["assinatura"] == rec.get("assinatura"):
			estado = "ativo"
			it["falso_alarme"] = {"t": rec.get("t"), "nota": rec.get("nota") or ""}
		else:
			estado = "obsoleto"
		falsos.append(dict(piece=pid, grau=grau, cell=rec.get("cell"), t=rec.get("t"), nota=rec.get("nota") or "",
						   assinatura=rec.get("assinatura"), assinatura_atual=None if it is None else it["assinatura"],
						   estado=estado, obsoleto=estado == "obsoleto"))
	return items, falsos


def suspects(project, placements: Optional[dict] = None, *, pieces=None) -> list:
	"""Suspect pieces ``[{piece, cell, grau, falhas, k0, k_alt, rot_alt_deg, n_falhas0, n_falhas_alt, custo0,
	custo_alt, n_vizinhas, texto, ...}]``, ``impossivel`` first, then by cost gain (see :func:`evaluate`)."""
	return evaluate(project, placements, pieces=pieces)["items"]


def summary(project, placements: Optional[dict] = None, *, pieces=None) -> dict:
	"""``{n_colocadas, n_verificadas, n_sem_cantos, n_com_vizinhas, n_impossivel, n_melhor_rotacao, n_explicadas,
	n_recorte, n_falsos_alarmes, n_falsos_alarmes_obsoletos, n_pose_manual}``."""
	return evaluate(project, placements, pieces=pieces)["summary"]


def _near_ids(project, cells) -> list:
	"""Pieces on the board in ``cells`` and in their 4-neighbours (sorted)."""
	want = set()
	by_cell = {tuple(p.celula): pid for pid, p in project.pieces.items() if p.estado in _STATES and p.celula is not None}
	for c in cells:
		c = (int(c[0]), int(c[1]))
		for x in [c] + project.board.neighbours(c):
			if x in by_cell:
				want.add(by_cell[x])
	return sorted(want)


def suspects_near(project, cells, placements: Optional[dict] = None) -> list:
	"""Suspects among the pieces in ``cells`` and in their 4-neighbours (the check after a confirmation)."""
	want = _near_ids(project, cells)
	return suspects(project, placements, pieces=want) if want else []


def _falsos_text(s: dict) -> str:
	return f"{s['n_falsos_alarmes']} falsos alarmes ativos, {s['n_falsos_alarmes_obsoletos']} obsoletos"


def suspects_lines(project, cells) -> list:
	"""Text lines of :func:`suspects_near` for the confirmation CLI (never raises: a failure is one line); the
	false-alarm counts of those pieces are appended to the first line when not zero.

	Arrows and the minus sign are written in ASCII (``<->``, ``->``, ``-``): the confirmation CLI prints to
	the console as it is (cp1252 on Windows)."""
	try:
		want = _near_ids(project, cells)
		r = evaluate(project, pieces=want) if want else None
	except Exception as e:  # noqa: BLE001 - the check is informative, it must not break a confirmation
		return [f"Suspeitas novas: verificação falhou ({e})"]
	items = r["items"] if r else []
	s = r["summary"] if r else None
	fa = f" ({_falsos_text(s)})" if s and (s["n_falsos_alarmes"] or s["n_falsos_alarmes_obsoletos"]) else ""
	if not items:
		return [f"Suspeitas novas: nenhuma (peças afetadas e vizinhas){fa}"]
	lines = ([f"Suspeitas novas: {len(items)} (peças afetadas e vizinhas; nada foi alterado){fa}"]
			 + ["  " + format_item(it) for it in items])
	return [ln.replace("↔", "<->").replace("→", "->").replace("−", "-").replace("—", "-").replace("Δ", "d") for ln in lines]


def format_falso(f: dict) -> str:
	"""One false-alarm mark (a row of ``evaluate(...)['falsos_alarmes']``) as a line of text."""
	cell = f"({f['cell'][0]},{f['cell'][1]})" if f.get("cell") else "(?)"
	nota = f" — «{f['nota']}»" if f.get("nota") else ""
	return f"{f['piece']} {cell} {f['grau']}: {f['estado']} (assinatura {f['assinatura']}, {f.get('t') or '?'}){nota}"


def format_item(it: dict) -> str:
	"""One suspect as a line of text."""
	cell = f"({it['cell'][0]},{it['cell'][1]})"
	if it["grau"] == "recorte":
		tw = f"; gémea {it['gemea']}" if it.get("gemea") else ""
		return f"{it['piece']} {cell} recorte: {'; '.join(it['falhas'])} — {it['texto']}{tw}"
	extra = ""
	if "custo" not in it["texto"]:
		extra = f"; custo {_num(it['custo0'], 1)}" + (f" → {_num(it['custo_alt'], 1)}" if it["custo_alt"] is not None else "") + " mm"
	return (f"{it['piece']} {cell} {it['grau']}: {'; '.join(it['falhas']) or 'sem falhas'} — {it['texto']}{extra} "
			f"({it['n_vizinhas']} vizinhas)")


# ---------------------------------------------------------------- CLI
def main(argv=None) -> int:
	from src.ingest import DEFAULT_PROJECT
	from src.state import Project, StateError
	ap = argparse.ArgumentParser(prog="python -m src.consistency",
								 description="Peças colocadas com uma orientação impossível ou claramente pior que outra, ou com a "
											 "silhueta longe da gémea. Só leitura, exceto --falso-alarme / --restaurar (um evento no log).")
	ap.add_argument("--project", default=DEFAULT_PROJECT, help="pasta do projeto (projects/<id>)")
	ap.add_argument("--json", action="store_true", help="saída JSON {summary, items, falsos_alarmes}")
	ap.add_argument("--pieces", nargs="+", default=None, metavar="P", help="só estas peças")
	ap.add_argument("--list", action="store_true", help="lista as suspeitas (o comportamento por omissão)")
	ap.add_argument("--falsos", action="store_true", help="com --list: lista os falsos alarmes registados e o estado de cada um")
	ap.add_argument("--falso-alarme", dest="falso", metavar="P####",
					help="marca a suspeita atual desta peça (grau --grau) como falso alarme")
	ap.add_argument("--restaurar", metavar="P####", help="retira a marca de falso alarme (grau --grau)")
	ap.add_argument("--grau", choices=GRAUS, help="grau da suspeita (com --falso-alarme / --restaurar)")
	ap.add_argument("--nota", default="", help="nota do falso alarme")
	args = ap.parse_args(argv)
	if hasattr(sys.stdout, "reconfigure"):
		sys.stdout.reconfigure(encoding="utf-8")      # ↔, −, → on a cp1252 console
	if (args.falso or args.restaurar) and not args.grau:
		ap.error("--falso-alarme / --restaurar precisam de --grau")
	if args.falso and args.restaurar:
		ap.error("--falso-alarme e --restaurar são exclusivos")
	pr = Project.open(args.project)
	t0 = time.time()
	from src import render
	pl = dict(render.load_placements(pr).get("placements") or {})
	pl = {pid: e for pid, e in pl.items() if pid in pr.pieces and e.get("key") == render._entry_key(pr, pid)}
	if args.falso or args.restaurar:
		pid = args.falso or args.restaurar
		try:
			if pid not in pr.pieces:
				raise StateError(f"peça desconhecida {pid}")
			if args.falso:
				r = evaluate(pr, pl, pieces=[pid], incluir_falsos=True)
				it = next((x for x in r["items"] if x["piece"] == pid and x["grau"] == args.grau), None)
				if it is None:
					raise StateError(f"{pid} não está sinalizada como {args.grau}")
				ev = pr.dismiss_suspect(pid, args.grau, it["assinatura"], cell=it["cell"], nota=args.nota)
				msg = f"{pid} {args.grau}: falso alarme registado (assinatura {ev['assinatura']})"
			else:
				pr.restore_suspect(pid, args.grau)
				msg = f"{pid} {args.grau}: falso alarme retirado (volta a ser sinalizada se ainda for suspeita)"
		except StateError as e:
			print(f"erro: {e}", file=sys.stderr)
			return 1
		pr.save()
		bad = pr.check_invariants(disk=True)
		print(msg)
		if bad:
			print("invariantes violados: " + "; ".join(bad), file=sys.stderr)
			return 1
		return 0
	r = evaluate(pr, pl, pieces=args.pieces)
	dt = time.time() - t0
	if args.json:
		print(json.dumps(r, ensure_ascii=False, indent=1))
		return 0
	s = r["summary"]
	print(f"{s['n_colocadas']} peças no tabuleiro, {s['n_verificadas']} verificadas ({s['n_com_vizinhas']} com vizinhas montadas), "
		  f"{s['n_sem_cantos']} sem cantos; suspeitas: {s['n_impossivel']} impossível, {s['n_melhor_rotacao']} melhor rotação, "
		  f"{s['n_recorte']} recorte ({_falsos_text(s)}) ({dt:.1f} s)")
	if args.falsos:
		print(f"Falsos alarmes registados: {len(r['falsos_alarmes'])}")
		for f in r["falsos_alarmes"]:
			print("  " + format_falso(f))
		return 0
	for it in r["items"]:
		print("  " + format_item(it))
	return 0


if __name__ == "__main__":
	sys.exit(main())
