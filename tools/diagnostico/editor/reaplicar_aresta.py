"""A2 (ronda 10): reaplicar os contornos por traços como «aresta oficial + índice derivado» (só-acrescentar, reversível).

Para cada peça com registo por traços em ``overrides.jsonl`` que ainda não está na convenção
``aresta+indice``, toma o ÚLTIMO registo com traços (os 17 de 2026-11-07/08 e os de 2026-11-09 do Tiago),
volta a correr o editor com esses traços (:func:`src.strokes.resolver`, ``normalizar_indice=True``) contra o
contorno automático da segmentação (``auto_contour_px`` do último registo da peça com ``auto_origem``
``segmentacao``) e obtém:

* a **aresta** = o caminho bruto com TODOS os traços (o «não é peça» sobre a sombra respeitado); nos registos
  antigos (sem ``convencao``) tem de ser o ``contour_px`` gravado (verificado: IoU e píxeis diferentes);
* o **índice derivado** (convenção do índice). Classe ``automatico`` quando difere do automático por
  profundidade máxima <= ``--prof-mm`` (0,5; a mesma regra de ``renormalizar.py``) em falta e a mais: o
  registo leva ``indice: "automatico"`` e ``contour_px`` = o automático exato (só muda o desenho); senão
  ``derivado``: ``contour_px`` = o índice derivado (o contorno manual do índice fica ativo).

Registo novo: ``metodo: "tracos"`` (traços, origem, tamanho e solver do registo de origem),
``convencao: "aresta+indice"``, ``aresta_px``, ``derivado_de`` (``t`` do registo de origem),
``motivo: "aresta_oficial"``, ``delta_mm``, ``auto_contour_px`` / ``auto_origem: "segmentacao"`` e a nota de
origem. Sem ``--aplicar`` nada é escrito (tabela, figura, JSON). Com ``--aplicar`` (servidor da GUI parado):
acrescenta os registos e aplica-os por folha: ``automatico`` numa peça que tinha contorno manual ->
re-segmentação da folha (``force_scans``, ``motivo="reposicao"``) depois de um dry-run que só pode mudar
essas peças; ``derivado`` -> ``render.rebuild_assets(scans=[sid])``; ``automatico`` numa peça sem contorno
manual -> nada a refazer (0 eventos).

Figura (``--fig``): por peça, vermelho = automático, laranja = aresta, ciano = índice derivado, magenta = GT
do Photoshop quando existe (``convencao.gt_files``: P0651/P0657 e ``--gt DIR/P####.png``), com a tabela
por lado (E/S/N/W no referencial do scanner) de ``convencao.side_offsets``.

	python tools/diagnostico/editor/reaplicar_aresta.py --project <cópia> [--aplicar] [--gt DIR] [--fig f.jpg] [--json f.json]
"""

import argparse
import json
import os
import sys

import cv2
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import convencao as CV  # noqa: E402
from src import maskcmp as MC  # noqa: E402
from src import overrides as OV  # noqa: E402
from src import render  # noqa: E402
from src import strokes as ST  # noqa: E402
from src.state import Project  # noqa: E402

MOTIVO = "aresta_oficial"


def _scan_cache():
	c = {}

	def get(pr, sid):
		if sid not in c:
			c.clear()
			c[sid] = OV.load_scan_rgb(pr, sid)
		return c[sid]
	return get


def _source(recs: list, pid: str):
	"""``(origem, base)``: o último registo da peça com traços (não vazio) e o último com ``auto_contour_px`` da
	segmentação; None quando a peça já tem um registo ``aresta+indice`` depois do de origem."""
	mine = [o for o in recs if o.get("piece") == pid]
	src = next((o for o in reversed(mine) if o.get("metodo") == "tracos" and o.get("tracos") and o.get("origem")), None)
	if src is None:
		return None, None
	after = mine[mine.index(src):]
	if any(o.get("convencao") == OV.CONVENCAO_ARESTA for o in after):
		return None, None
	base = next((o for o in reversed(mine) if o.get("auto_contour_px") and (o.get("auto_origem") or "segmentacao") == "segmentacao"), None)
	return src, base


def plan(pr, prof_mm: float, gts: dict) -> list:
	"""Uma linha por peça a reaplicar (máscaras, classe, métricas). Só leitura."""
	scan = _scan_cache()
	recs = OV.read_overrides(pr)
	rows = []
	for pid in sorted({o["piece"] for o in recs if o.get("piece")}):
		src, base = _source(recs, pid)
		if src is None:
			continue
		if base is None:
			rows.append({"piece": pid, "erro": "sem auto_contour_px da segmentação"})
			continue
		sid = src["scan_id"]
		x0, y0 = src["origem"]
		w, h = src["tamanho"]
		org = np.array([x0, y0], float)
		mmpp = render._scan_mmpp(pr, sid)
		rgb = scan(pr, sid)[y0:y0 + h, x0:x0 + w]
		auto_px = np.asarray(base["auto_contour_px"], float)
		auto = MC.fill_contour(auto_px - org, (h, w))
		tr, err = ST.validar_tracos(src.get("tracos"), w, h)
		if err:
			rows.append({"piece": pid, "erro": err})
			continue
		sv = src.get("solver") or {}
		res = ST.resolver(rgb, auto, tr, mmpp, solver=sv.get("nome", ST.SOLVER_OMISSAO), params=sv.get("params"),
						  normalizar_indice=True)
		if "error" in res:
			rows.append({"piece": pid, "erro": res["error"]})
			continue
		aresta, idx = res["mask_aresta"], res["mask"]
		gravado = MC.fill_contour(np.asarray(src["contour_px"], float) - org, (h, w))
		m_idx = MC.mask_metrics(auto, idx, mmpp)
		depth = max(m_idx["missing_depth_mm"], m_idx["excess_depth_mm"])
		cls = "automatico" if (res["indice_automatico"] or depth <= prof_mm) else "derivado"
		s0 = ST.resolver(rgb, auto, [], mmpp, solver=sv.get("nome", ST.SOLVER_OMISSAO), params=sv.get("params"))["mask"]
		p = pr.piece(pid)
		cur = pr.contour_px(pid)
		cur_m = None if cur is None else MC.fill_contour(np.asarray(cur, float) - org, (h, w))
		row = {"piece": pid, "scan_id": sid, "celula": list(p.celula) if p.celula else None,
			   "zona": pr.profile.zone_of(*p.celula) if p.celula and hasattr(pr.profile, "zone_of") else None,
			   "t_origem": src["t"], "convencao_origem": src.get("convencao"), "classe": cls,
			   "indice_bit_a_bit": bool(res["indice_automatico"]), "delta_mm": round(res["delta_mm"], 3),
			   "tracos": len(tr), "tracos_sombra_indice": len(res["tracos_ignorados"]),
			   "manual_ativo": bool(OV.is_manual(p)), "pose_manual": p.pose_manual is not None,
			   "aresta_vs_gravado_iou": round(float(MC.mask_metrics(gravado, aresta, mmpp)["iou"]), 4),
			   "aresta_vs_gravado_px": int((gravado ^ aresta).sum()),
			   "indice_vs_gravado_iou": round(float(MC.mask_metrics(gravado, idx, mmpp)["iou"]), 4),
			   "indice_vs_auto": {"iou": round(m_idx["iou"], 4), "falta_mm2": round(m_idx["missing_mm2"], 2),
								  "a_mais_mm2": round(m_idx["excess_mm2"], 2), "prof_mm": round(depth, 2)},
			   "auto_igual_atual": None if cur_m is None else bool(np.array_equal(cur_m, auto)),
			   "lados": {"aresta_menos_auto": CV.side_offsets(auto, aresta, mmpp),
						 "aresta_menos_s0": CV.side_offsets(s0, aresta, mmpp),
						 "indice_menos_auto": CV.side_offsets(auto, idx, mmpp)},
			   "_auto_px": auto_px, "_aresta_px": res["aresta"] + org, "_indice_px": res["contour"] + org,
			   "_src": src, "_fig": {"rgb": rgb, "auto": auto, "aresta": aresta, "indice": idx, "gt": None}}
		gfp = gts.get(pid)
		if gfp:
			gt = CV.load_gt_mask(gfp)[y0:y0 + h, x0:x0 + w]
			row["_fig"]["gt"] = gt
			row["gt"] = os.path.relpath(gfp, REPO)
			for nome, m in (("aresta", aresta), ("indice", idx), ("auto", auto), ("s0", s0)):
				row["lados"][f"{nome}_menos_gt"] = CV.side_offsets(gt, m, mmpp)
				row[f"{nome}_iou_gt"] = round(float(MC.mask_metrics(gt, m, mmpp)["iou"]), 4)
		rows.append(row)
	return rows


def figure(rows: list, path: str, cols: int = 4) -> None:
	tiles = []
	for r in rows:
		if "erro" in r:
			continue
		f = r["_fig"]
		img = np.ascontiguousarray(f["rgb"]).copy()
		for key, col in (("gt", (255, 0, 255)), ("auto", (255, 0, 0)), ("indice", (0, 230, 255)), ("aresta", (255, 150, 0))):
			m = f[key]
			if m is None:
				continue
			c, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
			cv2.drawContours(img, c, -1, col, 1)
		cv2.putText(img, f"{r['piece']} {r['zona'] or ''} {r['classe']}", (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.42,
					(255, 255, 255), 1, cv2.LINE_AA)
		cv2.putText(img, "ar-auto " + CV.fmt_lados(r["lados"]["aresta_menos_auto"]), (4, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.36,
					(255, 255, 255), 1, cv2.LINE_AA)
		if "aresta_menos_gt" in r["lados"]:
			cv2.putText(img, f"ar-GT {CV.fmt_lados(r['lados']['aresta_menos_gt'])} iou {r['aresta_iou_gt']:.3f}", (4, 44),
						cv2.FONT_HERSHEY_SIMPLEX, 0.36, (255, 120, 255), 1, cv2.LINE_AA)
		tiles.append(img)
	if not tiles:
		return
	H = max(t.shape[0] for t in tiles)
	W = max(t.shape[1] for t in tiles)
	pad = [cv2.copyMakeBorder(t, 0, H - t.shape[0], 0, W - t.shape[1], cv2.BORDER_CONSTANT, value=(30, 30, 30)) for t in tiles]
	while len(pad) % cols:
		pad.append(np.full((H, W, 3), 30, np.uint8))
	grid = np.vstack([np.hstack(pad[i:i + cols]) for i in range(0, len(pad), cols)])
	os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
	cv2.imwrite(path, grid[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, 90])


def apply(pr, rows, progress=print) -> dict:
	"""Acrescenta os registos e aplica-os por folha. ``{registos, eventos, erros}``."""
	out = {"registos": [], "eventos": [], "erros": []}
	by_sheet = {}
	for r in rows:
		if "erro" in r:
			continue
		src = r["_src"]
		W, H = OV.scan_size(pr, r["scan_id"])
		extra = {"metodo": "tracos", "tracos": src["tracos"], "origem": src["origem"], "tamanho": src["tamanho"],
				 "solver": src.get("solver"), "convencao": OV.CONVENCAO_ARESTA, "aresta_px": r["_aresta_px"],
				 "derivado_de": src["t"], "motivo": MOTIVO, "delta_mm": r["delta_mm"],
				 "auto_contour_px": np.round(r["_auto_px"]).astype(int).tolist(), "auto_origem": "segmentacao"}
		if r["classe"] == "automatico":
			_, _, cnt = OV.rasterize_polygon(r["_auto_px"], W, H)
			if cnt.shape != r["_auto_px"].shape or not np.array_equal(cnt, np.round(r["_auto_px"]).astype(np.int32)):
				out["erros"].append(f"{r['piece']}: o contorno automático não faz ida e volta exata; não aplicado")
				continue
			needs = r["manual_ativo"]
			if needs and r["pose_manual"]:
				out["erros"].append(f"{r['piece']}: tem pose manual (seria apagada pela re-segmentação); não aplicado")
				continue
			rec = OV.append_override(pr, r["piece"], r["_auto_px"], nota=src.get("nota") or "",
									 extra=dict(extra, indice=OV.INDICE_AUTOMATICO))
			kind = "reposicao" if needs else None
		else:
			if r["pose_manual"]:
				out["erros"].append(f"{r['piece']}: tem pose manual (seria apagada se o índice mudar); não aplicado")
				continue
			rec = OV.append_override(pr, r["piece"], r["_indice_px"], nota=src.get("nota") or "", extra=extra)
			kind = "derivado"
		if "error" in rec:
			out["erros"].append(f"{r['piece']}: {rec['error']}")
			continue
		out["registos"].append({"piece": r["piece"], "classe": r["classe"], "t": rec["t"]})
		if kind:
			by_sheet.setdefault(r["scan_id"], {"reposicao": [], "derivado": []})[kind].append(r["piece"])
	for sid, d in sorted(by_sheet.items()):
		if d["reposicao"]:
			dry = render.rebuild_assets(pr, progress=None, scans=[sid], force_scans=[sid], motivo="reposicao", clean=False,
										register=False, dry_run=True)
			changed = sorted(c["piece"] for c in dry["changed"] if c["scan_id"] == sid)
			if not set(changed) <= set(d["reposicao"]) | set(d["derivado"]) or dry["errors"]:
				out["erros"].append(f"{sid}: o dry-run mudaria {changed} (esperado ⊆ {d}); folha NÃO aplicada")
				continue
			res = render.rebuild_assets(pr, progress=progress, scans=[sid], force_scans=[sid], motivo="reposicao", clean=False, register=False)
		else:
			res = render.rebuild_assets(pr, progress=progress, scans=[sid], clean=False, register=False)
		out["eventos"].extend(c["piece"] for c in res["changed"])
		out["erros"].extend(res["errors"])
	pr.save()
	bad = pr.check_invariants(disk=True)
	if bad:
		out["erros"].extend(f"invariante: {b}" for b in bad)
	return out


def main(argv=None) -> int:
	ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
	ap.add_argument("--project", required=True)
	ap.add_argument("--aplicar", action="store_true")
	ap.add_argument("--prof-mm", type=float, default=0.5)
	ap.add_argument("--gt", default=None, help="pasta com P####.png (máscaras do Photoshop)")
	ap.add_argument("--fig", default=None)
	ap.add_argument("--json", default=None)
	a = ap.parse_args(argv)
	pr = Project.open(a.project)
	gts = CV.gt_files(a.gt)
	rows = plan(pr, a.prof_mm, gts)
	print("| peça | célula | zona | origem | classe | bit a bit | δ mm | traços (sombra p/ índice) | aresta vs gravado IoU (px) | "
		  "índice vs auto: IoU / falta / a mais / prof | aresta − auto E/S/N/W | aresta − GT E/S/N/W (IoU) | manual ativo |")
	print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
	for r in rows:
		if "erro" in r:
			print(f"| {r['piece']} | erro: {r['erro']} |")
			continue
		iv = r["indice_vs_auto"]
		gt = (f"{CV.fmt_lados(r['lados']['aresta_menos_gt'])} ({r['aresta_iou_gt']:.3f})" if "aresta_menos_gt" in r["lados"] else "—")
		print(f"| {r['piece']} | {r['celula']} | {r['zona']} | {r['t_origem']} {r['convencao_origem'] or 'antigo'} | {r['classe']} | "
			  f"{r['indice_bit_a_bit']} | {r['delta_mm']:.2f} | {r['tracos']} ({r['tracos_sombra_indice']}) | "
			  f"{r['aresta_vs_gravado_iou']:.4f} ({r['aresta_vs_gravado_px']}) | {iv['iou']:.4f} / {iv['falta_mm2']} / {iv['a_mais_mm2']} / {iv['prof_mm']} | "
			  f"{CV.fmt_lados(r['lados']['aresta_menos_auto'])} | {gt} | {r['manual_ativo']} |")
	n_auto = sum(1 for r in rows if r.get("classe") == "automatico")
	print(f"\n{len(rows)} peças: {n_auto} só visualização (índice = automático), {len(rows) - n_auto} com índice derivado "
		  f"({', '.join(r['piece'] for r in rows if r.get('classe') == 'derivado') or '-'})")
	if a.fig:
		figure(rows, a.fig)
		print(f"figura: {a.fig}")
	result = None
	if a.aplicar:
		result = apply(pr, rows)
		print(f"\naplicado: {len(result['registos'])} registos, {len(result['eventos'])} eventos piece_resegmented; "
			  f"erros: {result['erros'] or 'nenhum'}")
	if a.json:
		os.makedirs(os.path.dirname(os.path.abspath(a.json)), exist_ok=True)
		with open(a.json, "w", encoding="utf-8") as f:
			json.dump({"linhas": [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows], "aplicado": result,
					   "prof_mm": a.prof_mm}, f, ensure_ascii=False, indent=1)
		print(f"json: {a.json}")
	return 1 if (result and result["erros"]) else 0


if __name__ == "__main__":
	sys.exit(main())
