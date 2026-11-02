"""Twin search (M10): for a piece, find its die twin among loose pieces; shape first, image mandatory.

Pipeline of :func:`find_twin` (docs/plano-m10-m12.md §2.2, order = increasing cost):

1. same topological class (``Shape.cls``), both shapes ``ok``;
2. chord filter on homologous sides (:func:`src.shape.chord_pass`, tolerances from
   ``profile.calibration['chord']``);
3. corner-free distance :func:`src.shape.free_dist` -> d1, d2, margin = d2 / d1 among the
   candidates that pass 1-2;
4. shape decision per modality (``profile.calibration[modality]``): ``aceite`` if
   d1 <= t95 and margin >= ``margin_min``; ``ambigua`` if d1 <= tmax; else ``sem``. A
   single candidate (no d2, margin undefined) is never proposed (product decision
   2026-11-01): ``decision = 'sem'``, ``decision_shape`` keeps what it would have been with
   margin = inf (``aceite`` if d1 <= t95, else ``ambigua``) and ``single_candidate`` keeps
   the row for later review; its image is not tested. ``celula_silhueta`` (cut-line cell
   against a loose silhouette) first shrinks each silhouette by ``offset_mm`` along its
   normal (EREAL.md: +0.48 mm isotropic), and never accepts while its t95 is uncalibrated;
5. image, mandatory when the query cell and the art are known: each top candidate is
   rendered in the pose ``query.theta_deg + phi + profile.twin_rotation_deg()`` (phi from
   ``free_dist(query, candidate)``; sign verified in EREAL2.md §3 and in
   ``tests/test_twin_real.py``) against the twin cell ``profile.twin(*query.cell)``. It is a
   colour-consistency test: dE above the zone's p90 demotes ``aceite`` to ``ambigua``, the
   image never promotes, and it may reorder the shortlist only when d1 and d2 are both
   <= t95 (EREAL2.md §8: "only the shape puts #4 in front");
6. readable reasons.

Nothing puzzle-specific: the twin cell and the twin rotation come from the profile.
Cost O(N) per query. Pure module (no I/O).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from src.locate import CellArt, de_cell, render_item, snap_theta, body_beta_deg
from src.shape import Shape, chord_pass, f_adjacent, free_dist, homologous_k, N_FREE, FREE_SMOOTH_SIGMA, _smooth_closed, _resample_closed

__all__ = [
	"TwinItem", "find_twin", "same_shape", "shape_distances", "offset_shape", "decide",
	"RESCAN_MM", "MODALITIES", "PCTL_MAX_N", "IMAGE_TOPK", "OFFSET_SMOOTH_SIGMA",
]

RESCAN_MM = 0.27            # free RMS of a re-scan of the same piece (E-sym A1/A2)
MODALITIES = ("silhueta_silhueta", "celula_silhueta")
PCTL_MAX_N = 300            # percentile of the candidate's dE among all crops only up to this many candidates
IMAGE_TOPK = 3              # candidates tested against the art
OFFSET_SMOOTH_SIGMA = 3.0   # contour smoothing (samples) for the normals of the isotropic offset (ereal.offset_z)


@dataclass
class TwinItem:
	"""One piece in a twin query.

	id: stable piece id. shape: :class:`src.shape.Shape` (mm). rgba: crop ``(H, W, 4)``
	uint8 in the scan frame (only translated). theta_deg: rotation that takes the crop to
	its board pose (known for placed pieces; None for loose ones). cell: ``(l, c)`` if
	placed / position known.
	"""

	id: str
	shape: Shape
	rgba: np.ndarray | None = None
	theta_deg: float | None = None
	cell: tuple | None = None


# ---------------------------------------------------------------- shape helpers (pure)
def _fmt(x: float, nd: int = 2) -> str:
	"""Number with a decimal comma (reports are in Portuguese)."""
	return f"{x:.{nd}f}".replace(".", ",")


def shape_distances(query: Shape, shapes: list):
	"""Free distance (mm) and alignment rotation (deg) of every shape to ``query``, vectorised.

	Same as ``[free_dist(query, s)[0::2] for s in shapes]`` (``phi`` aligns the shape to the
	query). Returns ``(d, phi)`` arrays of length ``len(shapes)``.
	"""
	if not shapes:
		return np.zeros(0), np.zeros(0)
	Z = np.array([s.z for s in shapes])
	za = np.asarray(query.z)
	corr = np.fft.ifft(np.conj(np.fft.fft(za))[None, :] * np.fft.fft(Z, axis=1), axis=1)
	m = np.abs(corr)
	k = m.argmax(1)
	ar = np.arange(len(shapes))
	n = Z.shape[1]
	rms2 = (np.sum(np.abs(za) ** 2) + np.sum(np.abs(Z) ** 2, 1) - 2 * m[ar, k]) / n
	return np.sqrt(np.maximum(rms2, 0.0)), np.degrees(-np.angle(corr[ar, k]))


def same_shape(a: Shape, b: Shape, *, max_mm: float = RESCAN_MM) -> bool:
	"""True if ``a`` and ``b`` look like two scans of the same piece (same class if both ok, free <= max_mm)."""
	if a.ok and b.ok and a.cls != b.cls:
		return False
	return free_dist(a, b)[0] <= max_mm


def offset_shape(shape: Shape, delta_mm: float) -> Shape:
	"""Copy of ``shape`` with the contour moved ``delta_mm`` along the outward normal (negative = shrink).

	The free vector ``z`` is recomputed from the offset contour (``ereal.offset_z``) and every
	side chord changes by ``2 * delta_mm`` (each corner moves ``delta_mm`` along both sides);
	side profiles, corners and class are kept.
	"""
	c = shape.c
	cs = _smooth_closed(c, OFFSET_SMOOTH_SIGMA)
	t = np.roll(cs, -1, 0) - np.roll(cs, 1, 0)
	nrm = np.c_[t[:, 1], -t[:, 0]] / (np.linalg.norm(t, axis=1)[:, None] + 1e-12)
	if np.mean(np.sum(nrm * (c - c.mean(0)), 1)) < 0:
		nrm = -nrm
	c2 = c + float(delta_mm) * nrm
	z = _resample_closed(_smooth_closed(c2, FREE_SMOOTH_SIGMA), N_FREE)
	z = z - z.mean(0)
	sides = [replace(s, chord_mm=float(s.chord_mm) + 2.0 * float(delta_mm)) for s in shape.sides]
	return replace(shape, c=c2, z=z[:, 0] + 1j * z[:, 1], sides=sides)


def decide(d1, margin, t95, tmax, margin_min) -> str:
	"""Shape decision: ``'aceite'`` / ``'ambigua'`` / ``'sem'`` (``margin`` None = single candidate)."""
	if d1 is None or not np.isfinite(d1) or tmax is None or d1 > tmax:
		return "sem"
	if t95 is not None and margin is not None and d1 <= t95 and margin >= margin_min:
		return "aceite"
	return "ambigua"


# ---------------------------------------------------------------- image helpers
def _image_threshold(profile, zone):
	"""p90 of dE for ``zone``; unknown zone -> the largest p90 available; None if the profile has none."""
	zones = getattr(profile, "image_zones", None) or {}
	if zone is not None and zone in zones and zones[zone].get("dE_p90") is not None:
		return float(zones[zone]["dE_p90"]), zone
	vals = [(float(v["dE_p90"]), k) for k, v in zones.items() if v.get("dE_p90") is not None]
	return max(vals) if vals else (None, None)


def _image_test(cand: TwinItem, theta_q, phi, cell, profile, art, mmpp):
	"""dE of a candidate on ``cell``: predicted pose if ``theta_q`` is known, else the best of 4 body-aligned poses."""
	if theta_q is not None:
		th, _, resid = snap_theta(cand.shape, theta_q + phi + profile.twin_rotation_deg())
		thetas = [th]
	else:
		b = body_beta_deg(cand.shape)
		thetas, resid = [b + 90.0 * m for m in range(4)], None
	best = None
	for th in thetas:
		r = de_cell(render_item(cand.rgba, cand.shape, th, art, mmpp), cell[0], cell[1], art)
		if best is None or r["dE"] < best["dE"]:
			best = dict(r, theta_deg=float(th))
	best["resid_deg"] = resid
	return best


# ---------------------------------------------------------------- the query
def find_twin(query: TwinItem, candidates: list, *, profile, modality: str = "silhueta_silhueta",
			  art: CellArt | None = None, topk: int = 3, zone: str | None = None) -> dict:
	"""Find the twin of ``query`` among ``candidates`` (see the module docstring for the pipeline).

	Returns ``{'candidates': [{'id', 'd1_mm', 'phi_deg', 'chord_ok', 'image': {'dE', 'ncc',
	'pctl', 'theta_deg', 'p90'} | None, 'twin_cell'}] (top-k of those passing class + chords,
	best first), 'decision': 'aceite' | 'ambigua' | 'sem', 'decision_shape', 'margin':
	d2/d1 | None, 'twin_cell': (l, c) | None, 'n_class', 'n_pass', 'modality', 'reasons':
	[str], 'single_candidate': {'id', 'd1_mm', 'phi_deg', 'chord_ok', 'image'} | None}`` or
	``{'error': str}``. ``single_candidate`` is set when exactly one candidate passes class +
	chords with d1 <= tmax: the decision is then ``'sem'`` (not proposed, 2026-11-01) and
	``decision_shape`` holds the shape decision without that rule. ``zone`` selects the image
	p90 in ``profile.image_zones`` (unknown -> the largest p90).
	"""
	if modality not in MODALITIES:
		return {"error": f"modalidade desconhecida: {modality!r} (use {MODALITIES})"}
	cal_all = getattr(profile, "calibration", None) or {}
	cal = cal_all.get(modality)
	if cal is None:
		return {"error": f"perfil sem calibração para {modality}"}
	if query.shape is None or not query.shape.ok:
		return {"error": f"consulta {query.id}: forma sem 4 cantos"}
	reasons = []
	t95, tmax = cal.get("t95"), cal.get("tmax")
	if tmax is None:
		tmax = (cal_all.get("silhueta_silhueta") or {}).get("tmax")
		if tmax is None:
			return {"error": f"{modality}: tmax por calibrar e sem tmax de silhueta_silhueta"}
		reasons.append(f"{modality}: tmax por calibrar, usado o de silhueta_silhueta ({_fmt(tmax, 3)} mm)")
	if t95 is None:
		reasons.append(f"{modality}: t95 por calibrar, nunca 'aceite'")
	margin_min = float(cal_all.get("margin_min", 1.5))
	ch = cal_all.get("chord") or {}
	normal_mm, f_adj_mm = float(ch.get("normal_mm", 1.0)), float(ch.get("f_adj_mm", 2.0))
	offset = float(cal.get("offset_mm") or 0.0) if modality == "celula_silhueta" else 0.0

	# (1) class, (2) chords
	pool = [c for c in candidates if c.id != query.id]
	n_ok = sum(1 for c in pool if c.shape is not None and c.shape.ok)
	same_cls = [c for c in pool if c.shape is not None and c.shape.ok and c.shape.cls == query.shape.cls]
	shp = {c.id: (offset_shape(c.shape, -offset) if offset else c.shape) for c in same_cls}
	passed, failed_chord = [], []
	for c in same_cls:
		ok, worst, dl = chord_pass(query.shape, shp[c.id], normal_mm=normal_mm, f_adj_mm=f_adj_mm)
		(passed if ok else failed_chord).append((c, worst, dl))
	reasons.append(f"{len(pool)} candidatas; {len(pool) - n_ok} sem 4 cantos; {n_ok - len(same_cls)} de classe diferente "
				   f"(consulta {query.shape.cls}); {len(failed_chord)} falham as cordas; {len(passed)} passam")
	# readable reason for the nearest-by-shape candidates that were filtered out
	ok_pool = [c for c in pool if c.shape is not None and c.shape.ok]
	if ok_pool:
		d_all, _ = shape_distances(query.shape, [c.shape for c in ok_pool])
		pass_ids = {c.id for c, _, _ in passed}
		fail_info = {c.id: (w, dl) for c, w, dl in failed_chord}
		for o in np.argsort(d_all)[:2]:
			c = ok_pool[int(o)]
			if c.id in pass_ids:
				break
			if c.shape.cls != query.shape.cls:
				reasons.append(f"mais próxima pela forma {c.id} ({_fmt(d_all[o])} mm): classe diferente: "
							   f"{query.shape.cls} vs {c.shape.cls}")
			else:
				w, dl = fail_info[c.id]
				t = (w + homologous_k(query.shape, shp[c.id])) % 4
				tol = f_adj_mm if (f_adjacent(query.shape.types)[w] or f_adjacent(shp[c.id].types)[t]) else normal_mm
				reasons.append(f"mais próxima pela forma {c.id} ({_fmt(d_all[o])} mm): corda lado {w}: {_fmt(dl, 1)} mm "
							   f"> {_fmt(tol, 1)}")
	# (3) free distance among those that pass
	twin_cell = profile.twin(*query.cell) if query.cell is not None else None
	if not passed:
		reasons.append("sem candidata que passe classe + cordas")
		return dict(candidates=[], decision="sem", decision_shape="sem", margin=None, twin_cell=twin_cell,
					n_class=len(same_cls), n_pass=0, modality=modality, reasons=reasons, single_candidate=None)
	cl = [c for c, _, _ in passed]
	d, phi = shape_distances(query.shape, [shp[c.id] for c in cl])
	order = np.argsort(d, kind="stable")
	d1 = float(d[order[0]])
	d2 = float(d[order[1]]) if len(order) > 1 else None
	margin = (d2 / d1 if d1 > 0 else float("inf")) if d2 is not None else None
	# (4) shape decision
	dec = decide(d1, margin, t95, tmax, margin_min)
	single = margin is None and dec != "sem"
	if single:
		# product decision 2026-11-01: a lone candidate is not proposed; decision_shape keeps the
		# decision with margin = inf (the prototype's rule) so the case can be reviewed later
		dec = decide(d1, float("inf"), t95, tmax, margin_min)
		reasons.append(f"candidata única {cl[order[0]].id}: d1 {_fmt(d1, 3)} mm, não proposta (decisão 2026-11-01)")
	elif dec == "ambigua":
		why = []
		if t95 is None or d1 > t95:
			why.append(f"d1 {_fmt(d1, 3)} > t95 {_fmt(t95, 3) if t95 is not None else 'por calibrar'}")
		if margin is not None and margin < margin_min:
			why.append(f"margem {_fmt(margin)} < {_fmt(margin_min, 1)}")
		reasons.append("forma ambígua: " + "; ".join(why))
	elif dec == "sem":
		reasons.append(f"d1 {_fmt(d1, 3)} mm > tmax {_fmt(tmax, 3)}")
	else:
		reasons.append(f"forma aceite: d1 {_fmt(d1, 3)} mm <= t95 {_fmt(t95, 3)}, margem {_fmt(margin)} >= {_fmt(margin_min, 1)}")
	dec_shape = dec
	top = [int(o) for o in order[:max(topk, IMAGE_TOPK)]]
	rows = [dict(id=cl[o].id, d1_mm=float(d[o]), phi_deg=float(phi[o]), chord_ok=True, image=None, twin_cell=twin_cell)
			for o in top]

	# (5) image, mandatory when the query cell and the art are known (skipped for a lone candidate: never proposed)
	if single:
		reasons.append("imagem não testada: candidata única, não proposta")
	elif twin_cell is None:
		reasons.append("imagem não testada: célula da consulta desconhecida" if query.cell is None
					   else "imagem não testada: o perfil não tem gémea para esta célula")
	elif art is None:
		reasons.append("imagem não testada: sem arte")
	elif hasattr(art, "has_art") and not art.has_art(*twin_cell):
		# the art file does not reach this cell (e.g. row 47 of the Alpes): no image evidence, never a bogus dE;
		# the image tie-break is mandatory (project rule, decided 2026-11-02): the shape alone never gives 'aceite'
		reasons.append(f"imagem não testada: sem arte na célula {tuple(twin_cell)} (fora do ficheiro da arte)")
		if dec == "aceite":
			dec = "ambigua"
	else:
		mmpp = profile.mm_per_px()
		if query.theta_deg is None:
			reasons.append("theta_unknown: orientação da consulta desconhecida, melhor das 4 rotações")
		p90, zname = _image_threshold(profile, zone)
		with_img = [c for c in pool if c.rgba is not None and c.shape is not None]
		dist_all = None
		if len(with_img) <= PCTL_MAX_N:
			dw, pw = shape_distances(query.shape, [c.shape for c in with_img])
			dist_all = np.array([_image_test(c, query.theta_deg, float(pw[k]), twin_cell, profile, art, mmpp)["dE"]
								 for k, c in enumerate(with_img)])
		for r, o in zip(rows[:IMAGE_TOPK], top[:IMAGE_TOPK]):
			c = cl[o]
			if c.rgba is None:
				continue
			im = _image_test(c, query.theta_deg, float(phi[o]), twin_cell, profile, art, mmpp)
			pct = None
			if dist_all is not None and np.isfinite(im["dE"]):
				pct = float(100.0 * np.mean(dist_all[np.isfinite(dist_all)] < im["dE"]))
			r["image"] = dict(dE=float(im["dE"]), ncc=float(im["ncc"]), pctl=pct, theta_deg=im["theta_deg"],
							  off=tuple(int(v) for v in im["off"]), resid_deg=im["resid_deg"], p90=p90)
		img_rows = [r for r in rows[:IMAGE_TOPK] if r["image"] is not None and np.isfinite(r["image"]["dE"])]
		if not img_rows:
			reasons.append("imagem não testada: candidatas sem recorte")
		else:
			# reorder by image only when d1 and d2 are both <= t95 (shape cannot separate them)
			if (t95 is not None and d2 is not None and d1 <= t95 and d2 <= t95):
				short = [r for r in img_rows if r["d1_mm"] <= tmax]
				pick = min(short, key=lambda r: r["image"]["dE"]) if short else None
				if pick is not None and pick is not rows[0]:
					reasons.append(f"imagem reordena: {pick['id']} (ΔE {_fmt(pick['image']['dE'], 1)}) à frente de "
								   f"{rows[0]['id']} (ΔE {_fmt(rows[0]['image']['dE'], 1) if rows[0]['image'] else '-'}), "
								   "d1 e d2 ambos <= t95")
					rows.remove(pick)
					rows.insert(0, pick)
					if dec == "aceite":
						dec = "ambigua"
			im0 = rows[0]["image"]
			if im0 is None or not np.isfinite(im0["dE"]):
				reasons.append(f"imagem da proposta {rows[0]['id']} não testada")
				if dec == "aceite":
					dec = "ambigua"
			elif p90 is None:
				reasons.append(f"ΔE {_fmt(im0['dE'], 1)} (perfil sem p90 de zona: não despromove)")
			elif im0["dE"] > p90:
				reasons.append(f"ΔE {_fmt(im0['dE'], 1)} > p90 {_fmt(p90, 0)} ({zname})")
				if dec == "aceite":
					dec = "ambigua"
			else:
				reasons.append(f"imagem consistente: ΔE {_fmt(im0['dE'], 1)} <= p90 {_fmt(p90, 0)} ({zname})"
							   + (f", pct {_fmt(im0['pctl'], 1)} %" if im0["pctl"] is not None else ""))
	single_row = None
	if single:
		r0 = rows[0]
		single_row = dict(id=r0["id"], d1_mm=r0["d1_mm"], phi_deg=r0["phi_deg"], chord_ok=r0["chord_ok"],
						  image=r0["image"])
		dec = "sem"
	return dict(candidates=rows[:topk], decision=dec, decision_shape=dec_shape, margin=margin,
				twin_cell=twin_cell, n_class=len(same_cls), n_pass=len(passed),
				modality=modality, reasons=reasons, single_candidate=single_row)
