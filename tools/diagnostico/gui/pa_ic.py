"""IC 95 % por bootstrap de pares (10 000 reamostragens) da diferença das medianas novo − antigo, como em §13.9."""
import json
import random
import statistics as st
import sys

M = {
	"perto": lambda r: r["encaixa_perto"]["detalhe_desde_post_s"],
	"longe": lambda r: r["encaixa_longe"]["detalhe_desde_post_s"],
	"cartao": lambda r: r["cartao"].get("s"),
	"post_perto": lambda r: r["encaixa_perto"]["post_s"],
	"post_longe": lambda r: r["encaixa_longe"]["post_s"],
	"salto_frio_relva_browser": lambda r: r["salto_frio_relva"]["s"],
	"srv_frio_relva_s": lambda r: r["srv_frio_relva_s"],
	"srv_frio_ceu_s": lambda r: r["srv_frio_ceu_s"],
	"salto1_ceu": lambda r: r["salto1_ceu"]["s"],
	"pico_ws_mb": lambda r: r["mem"]["peak_ws_mb"],
}


def main():
	rows = json.load(open(sys.argv[1], encoding="utf-8"))["corridas"]
	by = {}
	for r in rows:
		by.setdefault(r["par"], {})[r["lado"]] = r
	pares = [(v["old"], v["new"]) for k, v in sorted(by.items()) if "old" in v and "new" in v]
	rnd = random.Random(20261116)
	out = {"n_pares": len(pares)}
	for nm, f in M.items():
		o = [f(a) for a, b in pares]
		n = [f(b) for a, b in pares]
		d = st.median(n) - st.median(o)
		bs = []
		for _ in range(10000):
			idx = [rnd.randrange(len(pares)) for _ in pares]
			bs.append(st.median([n[i] for i in idx]) - st.median([o[i] for i in idx]))
		bs.sort()
		lo, hi = bs[249], bs[9749]
		out[nm] = {"antigo": [round(st.median(o), 3), round(max(o), 3)], "novo": [round(st.median(n), 3), round(max(n), 3)],
				   "dif": round(d, 3), "ic95": [round(lo, 3), round(hi, 3)], "exclui_+0.25": hi < 0.25,
				   "novo_por_corrida": [round(x, 2) for x in n], "antigo_por_corrida": [round(x, 2) for x in o]}
	out["remendo_perto_novo"] = [((b["encaixa_perto"].get("remendo") or {}).get("remendos")) for a, b in pares]
	print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
	main()
