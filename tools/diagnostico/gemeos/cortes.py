"""Cortes repetidos: o mesmo recorte de lado reaparece em peças diferentes (fora da simetria de 180°)?

Uso (a partir da raiz do repositório):
	$env:PPF_SCRATCH = "...\\scratchpad"            # PowerShell (bash: export PPF_SCRATCH=...)
	python tools/diagnostico/gemeos/cortes.py
Entrada: $PPF_SCRATCH/seg/scan_verde.npz e scan_laranja.npz (julho; mesmo layout -> GT por posição),
images/pieces/digitalização_fundo_{verde,laranja}.jpg (variante híbrida) e $PPF_SCRATCH/seg/gemeos_{A1,B2}.npz.
Saída: docs/diagnostico/gemeos/cortes_pares_mais_parecidos.png e results.json (chave "cortes").

Por lado: perfil normalizado de 64 pts (shapelib.normalise_side: corda -> [0,1], para fora = +y) x corda média
do par -> RMS em mm; |dL| = diferença das cordas. Ruído = mesmo lado verde <-> laranja (GT por posição, lados
homólogos pelo best_k do shape_dist). Pares de lados do mesmo tipo (T-T, B-B) de peças diferentes: direto e
invertido (x -> 1-x, ordem invertida); controlo: T contra B invertido e negado (o encaixe complementar).
Variantes de contorno "seg" (segment_pieces) e "hibrido" (ver esym.py).
"""
import os
import sys
import json

import numpy as np
import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import segcache as sc  # noqa: E402
import esym  # noqa: E402
from shapelib import MM, load, shape_dist  # noqa: E402

OUT = sc.OUT
JULY = {"scan_verde": "digitalização_fundo_verde.jpg", "scan_laranja": "digitalização_fundo_laranja.jpg"}
r3, st = esym.r3, esym.st

__all__ = ["side_table", "pair_rms", "position_gt"]


def position_gt(PV, PL, tol=40):
	"""Pares (i verde, j laranja) com centro do bbox a < tol px (mesmo layout de julho)."""
	cv_ = np.array([np.asarray(p["bbox"][:2], float) + np.asarray(p["bbox"][2:], float) / 2 for p in PV])
	out = []
	for j, q in enumerate(PL):
		c = np.asarray(q["bbox"][:2], float) + np.asarray(q["bbox"][2:], float) / 2
		dd = np.linalg.norm(cv_ - c, axis=1)
		i = int(np.argmin(dd))
		if dd[i] < tol:
			out.append((i, j))
	return out


def side_table(P, group, piece_offset=0):
	"""Lista de lados não-F: (peça global, lado, tipo, perfil 64x2, corda mm, grupo)."""
	rows = []
	for pi, p in enumerate(P):
		for s in range(4):
			if p["types"][s] == "F":
				continue
			rows.append(dict(piece=pi + piece_offset, s=s, t=p["types"][s], prof=p["profs"][s], L=p["lens"][s], g=group))
	return rows


def pair_rms(A, LA, B, LB):
	"""RMS (mm) entre todos os perfis de A (n,64,2) e B (m,64,2), escalados pela corda média do par."""
	d = np.sqrt(np.mean(np.sum((A[:, None] - B[None]) ** 2, -1), -1))
	return d * (LA[:, None] + LB[None]) / 2, np.abs(LA[:, None] - LB[None])


def inv(pr):
	q = pr[::-1].copy()
	q[:, 0] = 1 - q[:, 0]
	return q


def neg_inv(pr):
	q = inv(pr)
	q[:, 1] = -q[:, 1]
	return q


def analyse_variant(var):
	"""Devolve dict de resultados + dados para a figura, para uma variante de contorno."""
	segV = load(os.path.join(sc.SEG, "scan_verde.npz"))
	segL = load(os.path.join(sc.SEG, "scan_laranja.npz"))
	gt = position_gt(segV, segL)
	if var == "seg":
		PV, PL = esym.prep([dict(p) for p in segV]), esym.prep([dict(p) for p in segL])
		A1, B2 = esym.prep(sc.load_grid("A1")), esym.prep(sc.load_grid("B2"))
	else:
		PV = esym.prep(esym.hybrid_pieces(os.path.join(sc.REPO, "images", "pieces", JULY["scan_verde"]), segV))
		PL = esym.prep(esym.hybrid_pieces(os.path.join(sc.REPO, "images", "pieces", JULY["scan_laranja"]), segL))
		A1 = esym.prep(esym.hybrid_pieces(os.path.join(sc.REPO, sc.SCANS["A1"]), sc.load_grid("A1")))
		B2 = esym.prep(esym.hybrid_pieces(os.path.join(sc.REPO, sc.SCANS["B2"]), sc.load_grid("B2")))
	gt = [(i, j) for i, j in gt if PV[i]["ok"] and PL[j]["ok"]]
	# ---- ruído por lado (verde <-> laranja, mesmo lado)
	S = {"V": PV, "L": PL}
	rows = esym.per_side(S, gt, ("V", "L"))
	same_cls = {(i, j): PV[i]["cls"] == PL[j]["cls"] for i, j in gt}
	noise = [r for r in rows if r["ta"] != "F" and r["tb"] != "F" and r["ta"] == r["tb"]]
	# pares cuja peça inteira tem re-scan limpo (corner < 1 mm) — exclui falhas de cantos/segmentação
	whole = {(i, j): shape_dist(PV[i], PL[j])[0] for i, j in gt}
	clean = [r for r in noise if whole[(r["i"], r["j"])] < 1.0]
	nz = np.array([r["rms_prof_mm"] for r in noise])
	ndl = np.array([r["dL"] for r in noise])
	nzc = np.array([r["rms_prof_mm"] for r in clean])
	ndlc = np.array([r["dL"] for r in clean])
	thr = dict(rms_median=float(np.median(nz)), rms_p90=float(np.percentile(nz, 90)), dL_p90=float(np.percentile(ndl, 90)))
	res = dict(n_gt_pairs=len(gt), class_agree=f"{sum(same_cls.values())}/{len(gt)}",
			   noise_sides=dict(n=len(noise), rms_prof_mm=st(nz), absdL_mm=st(ndl), dL_signed_sd=r3(np.std([r["dL_signed"] for r in noise], ddof=1)),
								rms_global_mm=st([r["rms_global_mm"] for r in noise])),
			   noise_sides_clean=dict(n=len(clean), criterion="peça inteira corner < 1 mm", rms_prof_mm=st(nzc), absdL_mm=st(ndlc),
									  dL_signed_sd=r3(np.std([r["dL_signed"] for r in clean], ddof=1))),
			   thresholds={k: r3(v) for k, v in thr.items()})
	# ---- pares de lados de peças diferentes
	sides_v = side_table([p for p in PV if p["ok"]], "verde")
	nV = len([p for p in PV if p["ok"]])
	sides_ab = side_table(A1 + B2, "AB", piece_offset=nV)
	twin_piece = {}
	for i in range(20):
		a, b = nV + i, nV + 20 + esym.twin(i)
		twin_piece[a], twin_piece[b] = b, a
	types_count = {t: sum(r["t"] == t for r in sides_v) for t in "TB"}

	def block(sides, label, exclude_twins=True):
		out = {}
		top = []
		for T_ in "TB":
			ss = [r for r in sides if r["t"] == T_]
			P_ = np.array([r["prof"] for r in ss])
			L_ = np.array([r["L"] for r in ss])
			pc = np.array([r["piece"] for r in ss])
			for mode, f in [("direto", lambda x: x), ("invertido", inv)]:
				Q = np.array([f(r["prof"]) for r in ss])
				D, dL = pair_rms(P_, L_, Q, L_)
				iu = np.triu_indices(len(ss), 1)
				valid = pc[iu[0]] != pc[iu[1]]
				if exclude_twins:
					valid &= np.array([twin_piece.get(a, -1) != b for a, b in zip(pc[iu[0]], pc[iu[1]])])
				d = D[iu][valid]
				l_ = dL[iu][valid]
				o = dict(n_pairs=int(valid.sum()), rms=st(d),
						 below_noise_median=int(np.sum(d < thr["rms_median"])), below_noise_p90=int(np.sum(d < thr["rms_p90"])),
						 below_median_and_dL_p90=int(np.sum((d < thr["rms_median"]) & (l_ < thr["dL_p90"]))),
						 below_p90_and_dL_p90=int(np.sum((d < thr["rms_p90"]) & (l_ < thr["dL_p90"]))))
				out[f"{T_}{T_}_{mode}"] = o
				order = np.argsort(d)[:8]
				a_idx, b_idx = iu[0][valid], iu[1][valid]
				for q in order:
					top.append((float(d[q]), float(l_[q]), ss[a_idx[q]], ss[b_idx[q]], mode, f"{T_}{T_}"))
		# controlo complementar: T contra B invertido e negado
		tt = [r for r in sides if r["t"] == "T"]
		bb = [r for r in sides if r["t"] == "B"]
		PT = np.array([r["prof"] for r in tt]); LT = np.array([r["L"] for r in tt])
		PB = np.array([neg_inv(r["prof"]) for r in bb]); LB = np.array([r["L"] for r in bb])
		D, dL = pair_rms(PT, LT, PB, LB)
		ptc = np.array([r["piece"] for r in tt]); pbc = np.array([r["piece"] for r in bb])
		valid = ptc[:, None] != pbc[None]
		d = D[valid]; l_ = dL[valid]
		out["TB_complementar"] = dict(n_pairs=int(valid.sum()), rms=st(d), below_noise_median=int(np.sum(d < thr["rms_median"])),
									  below_noise_p90=int(np.sum(d < thr["rms_p90"])),
									  below_median_and_dL_p90=int(np.sum((d < thr["rms_median"]) & (l_ < thr["dL_p90"]))),
									  below_p90_and_dL_p90=int(np.sum((d < thr["rms_p90"]) & (l_ < thr["dL_p90"]))))
		top.sort(key=lambda x: x[0])
		n_same = sum(out[f"{t}{t}_direto"]["n_pairs"] for t in "TB")
		k_med = sum(out[f"{t}{t}_direto"]["below_noise_median"] for t in "TB")
		k_j = sum(out[f"{t}{t}_direto"]["below_median_and_dL_p90"] for t in "TB")
		out["dictionary_estimate"] = dict(
			n_same_type_pairs_direct=n_same, k_below_noise_median=k_med, k_below_median_and_dL=k_j,
			D_hat_rms_only=(round(n_same / k_med, 1) if k_med else None),
			D_hat_joint=(round(n_same / k_j, 1) if k_j else None),
			D_lower_bound_95_if_zero=(round(n_same / 3.0, 1) if k_j == 0 else None),
			note="D ~ 1/f com f = fração de pares do mesmo tipo abaixo do ruído; com k = 0, f < 3/n (95 %) -> D > n/3. "
				 "Poder baixo: só se detetam dicionários com D << n_pares.")
		return out, top

	res["verde_only"], top_v = block(sides_v, "verde")
	res["verde_plus_A1B2"], top_all = block(sides_v + sides_ab, "verde+AB")
	res["thresholds_note"] = "limiares = mediana/p90 do RMS de perfil e p90 de |dL| do ruído verde<->laranja (mesma pose)"
	res["side_types_verde"] = types_count
	res["n_sides"] = dict(verde_nonF=len(sides_v), A1B2_nonF=len(sides_ab))
	# controlo positivo: lados homólogos dos 20 pares de gémeos (A1/B2), mesmo critério
	tw_rows = esym.per_side({"A1": A1, "B2": B2}, [(i, esym.twin(i)) for i in range(20)], ("A1", "B2"))
	tw = [r for r in tw_rows if r["ta"] != "F" and r["tb"] != "F"]
	twd = np.array([r["rms_prof_mm"] for r in tw]); twl = np.array([r["dL"] for r in tw])
	res["positive_control_twin_sides"] = dict(n=len(tw), rms_prof_mm=st(twd), absdL_mm=st(twl),
											  below_noise_median=int(np.sum(twd < thr["rms_median"])), below_noise_p90=int(np.sum(twd < thr["rms_p90"])),
											  below_p90_and_dL_p90=int(np.sum((twd < thr["rms_p90"]) & (twl < thr["dL_p90"]))),
											  below_median_and_dL_p90=int(np.sum((twd < thr["rms_median"]) & (twl < thr["dL_p90"]))))
	# estimativa corrigida pelo acaso: invertido (espelho, não pode ser o mesmo corte) = linha de base;
	# excesso = direto - invertido; limite superior 95 % ~ excesso + 1,96 sqrt(direto + invertido);
	# poder = fração dos lados gémeos (mesmo corte conhecido) que passam o mesmo critério.
	for blk in ["verde_only", "verde_plus_A1B2"]:
		b = res[blk]
		de = b["dictionary_estimate"]
		for crit, pk in [("below_noise_median", "below_noise_median"), ("below_median_and_dL_p90", "below_median_and_dL_p90")]:
			kd = sum(b[f"{t}{t}_direto"][crit] for t in "TB")
			ki = sum(b[f"{t}{t}_invertido"][crit] for t in "TB")
			power = res["positive_control_twin_sides"][pk] / max(1, res["positive_control_twin_sides"]["n"])
			ub = max(0.0, kd - ki) + 1.96 * np.sqrt(kd + ki)
			de[f"chance_corrected_{crit}"] = dict(direct=kd, inverted=ki, excess=kd - ki, excess_ub95=r3(ub), power=r3(power),
												  true_repeats_ub95=r3(ub / power) if power > 0 else None,
												  D_lower_bound_95=(round(de["n_same_type_pairs_direct"] * power / ub, 1) if ub > 0 else None))
	# ruído com mudança de pose (A1 <-> A2), para comparação
	A2 = esym.prep(sc.load_grid("A2")) if var == "seg" else esym.prep(esym.hybrid_pieces(os.path.join(sc.REPO, sc.SCANS["A2"]), sc.load_grid("A2")))
	rp = [r for r in esym.per_side({"A1": A1, "A2": A2}, [(i, i) for i in range(20)], ("A1", "A2")) if r["ta"] != "F"]
	res["noise_pose_change_A1A2"] = dict(n=len(rp), rms_prof_mm=st([r["rms_prof_mm"] for r in rp]), absdL_mm=st([r["dL"] for r in rp]))
	return res, top_all, dict(V=PV, AB=A1 + B2, nV=nV)


def fig_top(top, thr, fname, nV):
	BLK = (0, 0, 0)
	tiles = []
	for d, dl, x, y, mode, tt in top[:8]:
		t = np.full((220, 320, 3), 255, np.uint8)
		py = y["prof"] if mode == "direto" else inv(y["prof"])
		for pr, L, col in [(x["prof"], x["L"], (40, 40, 220)), (py, y["L"], (200, 90, 0))]:
			pm = pr * L
			q = np.round(np.c_[(pm[:, 0] - L / 2) * (280 / 22.0) + 160, -pm[:, 1] * (280 / 22.0) + 140]).astype(np.int32).reshape(-1, 1, 2)
			cv2.polylines(t, [q], False, col, 2, cv2.LINE_AA)

		def nm(r):
			return (f"verde#{r['piece']}" if r["piece"] < nV else ("A1" if r["piece"] < nV + 20 else "B2") + str(tuple(esym.fk((r["piece"] - nV) % 20)))) + f"s{r['s']}"
		esym.put(t, f"{tt} {mode}: {nm(x)} vs {nm(y)}", (5, 16), 0.42)
		esym.put(t, f"RMS {d:.2f} mm  dL {dl:.2f} mm", (5, 34), 0.42)
		esym.put(t, f"ruido: mediana {thr['rms_median']:.2f}, p90 {thr['rms_p90']:.2f} mm", (5, 52), 0.38, (90, 90, 90))
		cv2.rectangle(t, (0, 0), (319, 219), (150, 150, 150), 1)
		tiles.append(t)
	img = esym.grid(tiles, 4)
	img = esym.with_title(img, ["Pares de lados do mesmo tipo de pecas diferentes mais parecidos (verde 61 + A1/B2 40, gemeos excluidos), contorno hibrido",
								"vermelho = 1.o lado, azul = 2.o (invertido x->1-x se 'invertido'); mm; corda escalada ao comprimento de cada lado"])
	cv2.imwrite(os.path.join(OUT, fname), img)


def main():
	R = {}
	tops = {}
	for var in ["seg", "hibrido"]:
		R[var], top, meta = analyse_variant(var)
		tops[var] = (top, meta)
		r = R[var]
		print(f"== {var}: GT {r['n_gt_pairs']} class {r['class_agree']} | ruído lado n={r['noise_sides']['n']} rms med {r['noise_sides']['rms_prof_mm']['median']} "
			  f"p90 {r['noise_sides']['rms_prof_mm']['p90']} |dL| med {r['noise_sides']['absdL_mm']['median']} p90 {r['noise_sides']['absdL_mm']['p90']} "
			  f"sd dL {r['noise_sides']['dL_signed_sd']} | limpo n={r['noise_sides_clean']['n']} rms med {r['noise_sides_clean']['rms_prof_mm']['median']} sd {r['noise_sides_clean']['dL_signed_sd']}")
		for blk in ["verde_only", "verde_plus_A1B2"]:
			b = r[blk]
			print("  ", blk, {k: (v["n_pairs"], v["rms"]["min"], v["below_noise_median"], v["below_noise_p90"], v["below_median_and_dL_p90"], v["below_p90_and_dL_p90"])
							   for k, v in b.items() if k != "dictionary_estimate"})
			print("    D:", b["dictionary_estimate"])
		print("   pos ctrl", r["positive_control_twin_sides"])
		print("   pose", r["noise_pose_change_A1A2"]["rms_prof_mm"]["median"], r["noise_pose_change_A1A2"]["absdL_mm"]["median"])
	top, meta = tops["hibrido"]
	fig_top(top, R["hibrido"]["thresholds"], "cortes_pares_mais_parecidos.png", meta["nV"])
	R["context"] = dict(internal_cuts_64x47=63 * 47 + 64 * 46, distinct_under_180_symmetry="(5905 + 1) / 2 = 2953 (o corte central c32|c33 da linha 24 é o seu próprio gémeo)",
						expected_twin_pairs_in_61=r3(61 * 60 / 2 / 3007))
	jp = os.path.join(OUT, "results.json")
	J = json.load(open(jp, encoding="utf-8")) if os.path.exists(jp) else {}
	J["cortes"] = R
	json.dump(J, open(jp, "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=lambda o: o.item() if hasattr(o, "item") else str(o))


if __name__ == "__main__":
	main()
