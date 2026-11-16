"""Resumo de rodar_pa.py por condição: mediana · máximo (s) do «perto», «longe», cartão, POST, e a decomposição do
servidor no «perto» (parede de _region_jpg, _piece_jobs, _draw_jobs e dos três pedidos; espera da (b))."""
import json
import statistics as st
import sys


def med(v):
	v = [x for x in v if x is not None]
	return (round(st.median(v), 2), round(max(v), 2), len(v)) if v else None


def srv(row, kind, label):
	L = row[kind]["servidor"] if kind in row else row["cartao"]["servidor"]
	return sum(r.get("dur", 0) for r in L if r.get("name", r.get("what", "")) == label or r.get("label") == label)


def lab(r):
	return r.get("name") or r.get("what") or r.get("label") or r.get("ev")


def main():
	rows = json.load(open(sys.argv[1], encoding="utf-8"))["corridas"]
	conds = []
	for r in rows:
		if r["cond"] not in conds:
			conds.append(r["cond"])
	out = {}
	for c in conds:
		R = [r for r in rows if r["cond"] == c]
		o = {"n": len(R),
			 "perto": med([r["encaixa_perto"]["detalhe_desde_post_s"] for r in R]),
			 "longe": med([r["encaixa_longe"]["detalhe_desde_post_s"] for r in R]),
			 "cartao": med([r["cartao"].get("s") for r in R]),
			 "post_perto": med([r["encaixa_perto"]["post_s"] for r in R]),
			 "post_longe": med([r["encaixa_longe"]["post_s"] for r in R]),
			 "srv_frio_relva_s": med([r["srv_frio_relva_s"] for r in R]),
			 "salto_frio_relva": med([r["salto_frio_relva"]["s"] for r in R]),
			 "salto1": med([r["salto1_ceu"]["s"] for r in R]),
			 "pico_mb": med([r["mem"]["peak_ws_mb"] for r in R]),
			 "retidos_perto": [r["encaixa_perto"]["retidos"] for r in R],
			 "solto_por": [r["encaixa_perto"]["solto_por"] for r in R]}
		for nm in ("novo _region_jpg", "novo _piece_jobs", "novo _draw_jobs", "novo board_json", "novo ghosts",
				   "novo montar_json", "pa espera board_json", "pa espera ghosts", "pa espera montar_json"):
			o["perto " + nm] = med([sum(x.get("dur", 0) for x in r["encaixa_perto"]["servidor"] if lab(x) == nm) for r in R])
		out[c] = o
	print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
	main()
