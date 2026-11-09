"""Renormalização dos contornos manuais para a convenção do índice (CONVENCAO.md; só-acrescentar, reversível).

Para cada peça com registo em ``overrides.jsonl`` cujo último registo é do editor por traços SEM
``convencao: "indice"`` (gravado antes de 2026-11-09, na aresta verdadeira), volta a correr o pipeline do
editor com os traços originais contra o ``auto_contour_px`` original (a segmentação), agora com a
normalização (:func:`src.strokes.resolver` ``normalizar_indice=True``), e classifica:

* **reposição**: o resultado difere do automático por profundidade máxima <= ``--prof-mm`` (0,5) em falta
  e a mais -> registo ``metodo: "reposicao"`` com ``contour_px`` = contorno automático exato
  (:func:`src.overrides.latest_overrides` ignora-o: a peça volta à segmentação, sem ``manual_override``);
* **renormalizado**: senão, registo ``metodo: "tracos"`` com o contorno normalizado (a correção real fica,
  na convenção do índice) e a peça entra na lista «a confirmar pelo Tiago».

Os dois registos levam ``derivado_de`` (o ``t`` do registo substituído), ``motivo: "renormalizacao"``,
``convencao: "indice"``, ``delta_mm`` e a nota. Sem ``--aplicar`` nada é escrito (tabela + figura).
Com ``--aplicar``: acrescenta os registos e aplica-os por folha (``render.rebuild_assets``: reposições por
re-segmentação da folha com ``force_scans`` e ``motivo="reposicao"``, depois de um ``dry_run`` que tem de
mudar SÓ as peças repostas; renormalizados por ``render.rebuild_piece``). Servidor da GUI parado.

	python tools/diagnostico/editor/renormalizar.py --project <cópia> [--aplicar] [--fig out.jpg] [--json out.json]
"""

import argparse
import json
import os
import sys

import cv2
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO)

from src import maskcmp as MC  # noqa: E402
from src import overrides as OV  # noqa: E402
from src import render  # noqa: E402
from src import strokes as ST  # noqa: E402
from src.state import Project  # noqa: E402

MOTIVO = "renormalizacao"


def _scan_cache():
	c = {}

	def get(pr, sid):
		if sid not in c:
			c.clear()
			c[sid] = OV.load_scan_rgb(pr, sid)
		return c[sid]
	return get


def plan(pr, prof_mm: float, refazer: bool = False) -> list:
	"""One row per piece to renormalise: the new contour (scan px), its class and the metrics vs the automatic.
	``refazer``: also the pieces whose latest line is a renormalisation (``motivo: "renormalizacao"``,
	``metodo: "tracos"``), recomputed from the strokes of the line it derives from (``derivado_de``)."""
	scan = _scan_cache()
	rows = []
	allrecs = OV.read_overrides(pr)
	for pid, latest in OV.latest_overrides(pr, incluir_reposicao=True).items():
		rec = latest
		if refazer and latest.get("motivo") == MOTIVO and latest.get("metodo") == "tracos" and latest.get("derivado_de"):
			rec = next((o for o in allrecs if o.get("piece") == pid and o.get("t") == latest["derivado_de"]), None)
			if rec is None:
				rows.append({"piece": pid, "erro": f"registo de origem {latest['derivado_de']} não encontrado"})
				continue
		if rec.get("metodo") != "tracos" or rec.get("convencao") == "indice" or not rec.get("auto_contour_px") or not rec.get("origem"):
			continue
		# the ORIGINAL automatic contour: the first line of the piece with auto_origem segmentacao (else this one)
		base = next((o for o in OV.read_overrides(pr) if o.get("piece") == pid and o.get("auto_contour_px")
					 and (o.get("auto_origem") or "segmentacao") == "segmentacao"), rec)
		sid = rec["scan_id"]
		x0, y0 = rec["origem"]
		w, h = rec["tamanho"]
		mmpp = render._scan_mmpp(pr, sid)
		rgb = scan(pr, sid)[y0:y0 + h, x0:x0 + w]
		auto_px = np.asarray(base["auto_contour_px"], float)
		auto = MC.fill_contour(auto_px - [x0, y0], (h, w))
		tr, err = ST.validar_tracos(rec.get("tracos"), w, h)
		if err:
			rows.append({"piece": pid, "erro": err})
			continue
		sv = rec.get("solver") or {}
		res = ST.resolver(rgb, auto, tr, mmpp, solver=sv.get("nome", ST.SOLVER_OMISSAO), params=sv.get("params"),
						  normalizar_indice=True)
		if "error" in res:
			rows.append({"piece": pid, "erro": res["error"]})
			continue
		m = MC.mask_metrics(auto, res["mask"], mmpp)
		depth = max(m["missing_depth_mm"], m["excess_depth_mm"])
		cls = "reposicao" if depth <= prof_mm else "renormalizado"
		p = pr.piece(pid)
		rows.append({"piece": pid, "scan_id": sid, "celula": list(p.celula) if p.celula else None, "t_anterior": latest["t"],
					 "classe": cls, "identidade": bool(res["identidade"]), "delta_mm": round(res["delta_mm"], 3),
					 "tracos": len(tr), "tracos_ignorados": len(res.get("tracos_ignorados", [])),
					 "iou": round(m["iou"], 4), "falta_mm2": round(m["missing_mm2"], 2), "falta_prof_mm": round(m["missing_depth_mm"], 2),
					 "a_mais_mm2": round(m["excess_mm2"], 2), "a_mais_prof_mm": round(m["excess_depth_mm"], 2),
					 "pose_manual": p.pose_manual is not None,
					 "_auto_px": auto_px, "_novo_px": res["contour"] + np.array([x0, y0], float),
					 "_fig": (rgb, auto, res["mask"], MC.fill_contour(np.asarray(rec["contour_px"], float) - [x0, y0], (h, w)))})
	return rows


def figure(rows, path, cols=3):
	tiles = []
	for r in rows:
		if "erro" in r:
			continue
		rgb, auto, novo, antigo = r["_fig"]
		img = rgb.copy()
		for m, col in ((antigo, (255, 0, 255)), (auto, (255, 0, 0)), (novo, (0, 255, 0))):
			c, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
			cv2.drawContours(img, c, -1, col, 1)
		cv2.putText(img, f"{r['piece']} {r['classe']} iou {r['iou']:.3f}", (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)
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
	cv2.imwrite(path, grid[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, 88])


def apply(pr, rows, progress=print) -> dict:
	"""Append the records and apply them per sheet. Returns ``{registos, eventos, erros}``."""
	out = {"registos": [], "eventos": [], "erros": []}
	by_sheet = {}
	for r in rows:
		if "erro" in r:
			continue
		if r["pose_manual"]:
			out["erros"].append(f"{r['piece']}: tem pose manual (seria apagada pelo piece_resegmented); não aplicado")
			continue
		extra = {"derivado_de": r["t_anterior"], "motivo": MOTIVO, "convencao": "indice", "delta_mm": r["delta_mm"]}
		if r["classe"] == "reposicao":
			# the automatic chain must round-trip exactly through rasterize_polygon (what rebuild_assets stores)
			W, H = OV.scan_size(pr, r["scan_id"])
			_, _, cnt = OV.rasterize_polygon(r["_auto_px"], W, H)
			if cnt.shape != r["_auto_px"].shape or not np.array_equal(cnt, np.round(r["_auto_px"]).astype(np.int32)):
				out["erros"].append(f"{r['piece']}: o contorno automático não faz ida e volta exata ({cnt.shape} vs {r['_auto_px'].shape}); não aplicado")
				continue
			rec = OV.append_override(pr, r["piece"], r["_auto_px"],
									 nota="reposição do contorno automático (renormalização 2026-11-09: os traços só marcavam a sombra, que pertence à silhueta do índice)",
									 extra=dict(extra, metodo="reposicao"))
		else:
			rec = OV.append_override(pr, r["piece"], r["_novo_px"],
									 nota="contorno manual renormalizado para a convenção do índice (2026-11-09); correção real mantida, a confirmar",
									 extra=dict(extra, metodo="tracos"))
		if "error" in rec:
			out["erros"].append(f"{r['piece']}: {rec['error']}")
			continue
		out["registos"].append({"piece": r["piece"], "metodo": rec["metodo"], "t": rec["t"]})
		by_sheet.setdefault(r["scan_id"], {"reposicao": [], "tracos": []})[rec["metodo"] if rec["metodo"] == "reposicao" else "tracos"].append(r["piece"])
	for sid, d in sorted(by_sheet.items()):
		if d["reposicao"]:
			# scans=[sid] AND force_scans=[sid]: only this sheet (with scans=None every sheet is walked)
			dry = render.rebuild_assets(pr, progress=None, scans=[sid], force_scans=[sid], motivo="reposicao", clean=False,
										register=False, dry_run=True)
			changed = sorted(c["piece"] for c in dry["changed"] if c["scan_id"] == sid)
			expected = sorted(set(d["reposicao"]) | set(d["tracos"]))
			if changed != expected or dry["errors"]:
				out["erros"].append(f"{sid}: o dry-run da re-segmentação mudaria {changed} (esperado {expected}); erros {dry['errors']}; folha NÃO aplicada")
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
	ap.add_argument("--refazer", action="store_true", help="refaz também as peças já renormalizadas (a partir dos traços originais)")
	ap.add_argument("--fig", default=None)
	ap.add_argument("--json", default=None)
	a = ap.parse_args(argv)
	pr = Project.open(a.project)
	rows = plan(pr, a.prof_mm, refazer=a.refazer)
	print("| peça | célula | classe | identidade | δ mm | traços (ignorados) | IoU vs auto | falta mm² (prof) | a mais mm² (prof) | pose manual |")
	print("|---|---|---|---|---|---|---|---|---|---|")
	for r in rows:
		if "erro" in r:
			print(f"| {r['piece']} | erro: {r['erro']} |")
			continue
		print(f"| {r['piece']} | {r['celula']} | {r['classe']} | {r['identidade']} | {r['delta_mm']:.2f} | {r['tracos']} ({r['tracos_ignorados']}) | "
			  f"{r['iou']:.4f} | {r['falta_mm2']} ({r['falta_prof_mm']}) | {r['a_mais_mm2']} ({r['a_mais_prof_mm']}) | {r['pose_manual']} |")
	n_rep = sum(1 for r in rows if r.get("classe") == "reposicao")
	print(f"\n{len(rows)} registos: {n_rep} reposição, {len(rows) - n_rep} renormalizados (a confirmar: "
		  f"{', '.join(r['piece'] for r in rows if r.get('classe') == 'renormalizado') or '-'})")
	if a.fig:
		figure(rows, a.fig)
		print(f"figura: {a.fig}")
	result = None
	if a.aplicar:
		result = apply(pr, rows)
		print(f"\naplicado: {len(result['registos'])} registos, {len(result['eventos'])} eventos piece_resegmented; erros: {result['erros'] or 'nenhum'}")
	if a.json:
		with open(a.json, "w", encoding="utf-8") as f:
			json.dump({"linhas": [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows], "aplicado": result,
					   "prof_mm": a.prof_mm}, f, ensure_ascii=False, indent=1)
		print(f"json: {a.json}")
	return 1 if (result and result["erros"]) else 0


if __name__ == "__main__":
	sys.exit(main())
