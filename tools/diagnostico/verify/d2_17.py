"""CONVENCAO.md §3 (17/17 no automático exato), medido de novo depois da união aresta ∪ índice na gravação (4.1 (c) = A).

Os 17 registos do editor gravados antes de 2026-11-09 (na aresta verdadeira: ``metodo: "tracos"`` sem ``convencao``)
foram depois repostos (``metodo: "reposicao"``, ``motivo: "renormalizacao"``). Para cada um, como
``tools/diagnostico/editor/renormalizar.py`` (``plan``): os traços originais contra o ``auto_contour_px`` original
(a segmentação), ``strokes.resolver(..., normalizar_indice=True)``; mede se o índice é o automático bit a bit, a
identidade (sem traços efetivos), a aresta fora do índice e a profundidade máxima da diferença ao automático, com a
união (código atual) e sem ela (``indice_com_aresta`` = identidade: a derivação de 2026-11-09).

Uso: ``.venv/Scripts/python.exe tools/diagnostico/verify/d2_17.py [--project projects/alpes] [--json out.json]``.
Corre sobre uma cópia; só lê."""
import argparse
import json
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO)

from tools.verify import ambiente as AMB  # noqa: E402


def medir(pr) -> list:
	from src import maskcmp as MC, overrides as OV, render, strokes as ST
	recs = OV.read_overrides(pr)
	rows, cache = [], {}
	for rec in sorted(recs, key=lambda o: (o.get("piece"), o.get("t"))):
		# os registos originais: traços sem ``convencao`` (gravados na aresta verdadeira, antes de 2026-11-09)
		if rec.get("metodo") != "tracos" or rec.get("convencao") or not rec.get("origem") or not rec.get("auto_contour_px"):
			continue
		pid = rec["piece"]
		base = next((o for o in recs if o.get("piece") == pid and o.get("auto_contour_px")
					 and (o.get("auto_origem") or "segmentacao") == "segmentacao"), rec)
		sid = rec["scan_id"]
		if sid not in cache:
			cache[sid] = OV.load_scan_rgb(pr, sid)
		x0, y0 = rec["origem"]
		w, h = rec["tamanho"]
		mm = render._scan_mmpp(pr, sid)
		rgb = np.ascontiguousarray(cache[sid][y0:y0 + h, x0:x0 + w])
		auto = MC.fill_contour(np.asarray(base["auto_contour_px"], float) - [x0, y0], (h, w))
		tr, err = ST.validar_tracos(rec.get("tracos"), w, h)
		if err:
			rows.append({"peca": pid, "erro": err})
			continue
		sv = rec.get("solver") or {}
		row = {"peca": pid, "tracos": len(tr)}
		real = ST.indice_com_aresta
		for nome, f in (("sem_uniao", lambda i, a: np.asarray(i, bool)), ("com_uniao", real)):
			ST.indice_com_aresta = f
			try:
				r = ST.resolver(rgb, auto, tr, mm, solver=sv.get("nome", ST.SOLVER_OMISSAO), params=sv.get("params"),
								normalizar_indice=True)
			finally:
				ST.indice_com_aresta = real
			if "error" in r:
				row[nome] = {"erro": r["error"]}
				continue
			m = MC.mask_metrics(auto, r["mask"], mm)
			row[nome] = {"automatico_exato": bool(np.array_equal(r["mask"], auto)), "identidade": bool(r["identidade"]),
						 "tracos_ignorados": len(r["tracos_ignorados"]),
						 "aresta_fora_px": int((r["mask_aresta"] & ~r["mask"]).sum()),
						 "a_mais_mm2": round(m["excess_mm2"], 3), "a_mais_prof_mm": round(m["excess_depth_mm"], 3),
						 "falta_mm2": round(m["missing_mm2"], 3), "falta_prof_mm": round(m["missing_depth_mm"], 3)}
		rows.append(row)
	return rows


def main(argv=None):
	from src.state import Project
	ap = argparse.ArgumentParser()
	ap.add_argument("--project", default=os.path.join(REPO, "projects", "alpes"))
	ap.add_argument("--json", default=os.path.join(REPO, "docs", "diagnostico", "verify", "D2", "convencao17.json"))
	a = ap.parse_args(argv)
	raiz, copia = AMB.copiar_projeto(a.project)
	try:
		rows = medir(Project.open(copia))
	finally:
		AMB.apagar_copia(raiz)
	for r in rows:
		print(json.dumps(r, ensure_ascii=False))
	for nome in ("sem_uniao", "com_uniao"):
		ok = sum(1 for r in rows if (r.get(nome) or {}).get("automatico_exato"))
		rep = sum(1 for r in rows if max((r.get(nome) or {}).get("a_mais_prof_mm", 9), (r.get(nome) or {}).get("falta_prof_mm", 9)) <= 0.5)
		print(f"{nome}: automático exato {ok}/{len(rows)}; reposição pelo critério de renormalizar.py "
			  f"(prof. max. <= 0,5 mm -> contorno guardado = automático exato) {rep}/{len(rows)}")
	with open(a.json, "w", encoding="utf-8", newline="\n") as f:
		json.dump(rows, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
	main()
