"""Ronda 7 — efeito da validação cruzada ``query._cross_check`` (R7_CRITERIOS §4.1) nas propostas de gémea
aceites pelo Tiago e nas 2 rejeitadas, à data de cada uma (log truncado, como ``r7_gt.py``).

Para cada caso reabre o projeto antes do evento, constrói a entrada como o ``query`` a escreve (peça, célula,
decisão listada, ``theta_deg`` da colocação ou da cadeia de pose) e chama ``_cross_check``; conta quantas
aceites perdem ``aceite`` e se as rejeitadas ficam ``incompativel``. Escreve ``r7_efeito.json``.

    python tools/diagnostico/gemeos/r7_efeito.py --project <cópia> [--tmp <dir>]
"""

import argparse
import collections
import json
import os
import sys
import time

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if REPO not in sys.path:
	sys.path.insert(0, REPO)

from src import query as Q  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import r7_gt as G  # noqa: E402

DOC = os.path.join(REPO, "docs", "diagnostico", "gemeos")


def main(argv=None):
	ap = argparse.ArgumentParser()
	ap.add_argument("--project", required=True)
	ap.add_argument("--tmp", default=None)
	ap.add_argument("--gt", default=os.path.join(DOC, "r7_gt.json"))
	ap.add_argument("--out", default=os.path.join(DOC, "r7_efeito.json"))
	args = ap.parse_args(argv)
	src = os.path.abspath(args.project)
	tmp = args.tmp or os.path.join(os.path.dirname(src), "alpes_r7_t")
	gt = json.load(open(args.gt, encoding="utf-8"))
	lines = open(os.path.join(src, "log.jsonl"), encoding="utf-8").readlines()
	if not os.path.isdir(tmp):
		G.make_tmp(src, tmp)
	t0 = time.time()
	rows = []
	cases = [(r, "aceite_colocada") for r in gt["gemeas"]] + [(r, "rejeitada") for r in gt["rejeitadas"]]
	for r, kind in cases:
		pr = G.open_at(tmp, lines, r["idx"])
		ctx = Q._Ctx(pr, use_image=False)      # a imagem não entra no encaixe; só forma, tiras e pose
		listed = r.get("listed") or (r.get("find_twin") or {}).get("decision")
		e = {"origin": "gemeo", "piece": r["piece"], "cell": list(r["cell"]), "decision": listed, "reasons": [],
			 "query": r.get("query"), "theta_deg": r.get("theta_pred")}
		Q._cross_check(ctx, e)
		enc = e.get("encaixe") or {}
		rows.append(dict(tipo=kind, piece=r["piece"], cell=r["cell"], zona=r["zona"], listed=listed, decision_depois=e["decision"],
						 perdeu_aceite=(listed == "aceite" and e["decision"] != "aceite"), encaixe=enc.get("estado"), pose=enc.get("pose"),
						 J=enc.get("J"), m=enc.get("m"), motivo=enc.get("motivo"), razao=next((x for x in e["reasons"] if str(x).startswith(Q.ENC_TAG)), None),
						 n_vizinhas=r.get("n_vizinhas")))
		print(f"{kind:16s} {r['piece']} {tuple(r['cell'])} {listed} -> {e['decision']} encaixe={enc.get('estado')} J={enc.get('J')} ({time.time() - t0:.0f} s)", flush=True)
	ac = [x for x in rows if x["tipo"] == "aceite_colocada"]
	rj = [x for x in rows if x["tipo"] == "rejeitada"]
	res = dict(n_aceites=len(ac), n_aceites_listadas_aceite=sum(1 for x in ac if x["listed"] == "aceite"),
			   perderam_aceite=[x["piece"] for x in ac if x["perdeu_aceite"]],
			   encaixe_aceites=dict(collections.Counter(x["encaixe"] for x in ac)),
			   J_max_aceites=max((x["J"] for x in ac if x["J"] is not None), default=None),
			   rejeitadas=[dict(piece=x["piece"], listed=x["listed"], depois=x["decision_depois"], encaixe=x["encaixe"], J=x["J"], razao=x["razao"]) for x in rj],
			   criterio_4_1=dict(aceites_perdidas_max_2=len([x for x in ac if x["perdeu_aceite"]]) <= 2,
								 rejeitadas_incompativeis=all(x["encaixe"] == "incompativel" for x in rj)),
			   segundos=round(time.time() - t0, 1), rows=rows)
	with open(args.out, "w", encoding="utf-8") as f:
		json.dump(res, f, ensure_ascii=False, indent=1, default=lambda o: None if (isinstance(o, float) and not np.isfinite(o)) else str(o))
	print(json.dumps({k: v for k, v in res.items() if k != "rows"}, ensure_ascii=False, indent=1))
	return 0


if __name__ == "__main__":
	sys.exit(main())
