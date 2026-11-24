"""Critério 12 da F4 (F4_PLANO.md §4): IC 95 % da diferença novo − antigo nos pares de ``pa_pares.py``.

Para «perto» (detalhe depois do POST de um «Encaixa» perto da vista) e «1.º salto» (céu, logo depois de abrir), e,
como contexto, as outras medidas de ``pa_ic.py``. Dois IC por medida, sobre as diferenças por par d_i = novo_i − antigo_i:
- t pareado: média(d) ± t(0,975; n − 1) · dp(d) / √n;
- bootstrap de pares (10 000 reamostragens, semente fixa): percentis 2,5 e 97,5 da média de d; e, como em ``pa_ic.py``,
  da diferença das medianas.
Passa se o limite superior dos IC (t e bootstrap da média) ficar abaixo de +0,25 s.

Uso: ``python tools/diagnostico/gui/f4_ic.py <pares.json> [<lado_base> <lado_novo>]`` (por omissão ``old`` e ``new``; os
lados de ``abrir_pares.py`` são os nomes dados na linha de comandos). Além do IC, escreve média ± desvio padrão de cada
lado (``medias``) para as medidas de abertura."""
import json
import math
import random
import statistics as st
import sys

T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
		11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131, 19: 2.093, 29: 2.045}
M = {
	"perto": lambda r: r["encaixa_perto"]["detalhe_desde_post_s"],
	"salto1_ceu": lambda r: r["salto1_ceu"]["s"],
	"longe": lambda r: r["encaixa_longe"]["detalhe_desde_post_s"],
	"cartao": lambda r: r["cartao"].get("s"),
	"post_perto": lambda r: r["encaixa_perto"]["post_s"],
	"salto_frio_relva_browser": lambda r: r["salto_frio_relva"]["s"],
	"srv_frio_relva_s": lambda r: r["srv_frio_relva_s"],
	"abrir_s": lambda r: r["abrir_s"],
	"abrir_mais_salto": lambda r: r["abrir_s"] + r["salto1_ceu"]["s"],
	"pico_ws_mb": lambda r: (r.get("mem") or {}).get("peak_ws_mb"),
}
CRIT = ("perto", "salto1_ceu")
# Critério da correção «abrir sem esperar pelos grupos» (2026-11-23): abrir + 1.º salto da árvore nova não pior do que
# a base: limite superior do IC 95 % t da diferença (nova − base) <= +0,10 s. abrir e 1.º salto só se reportam.
LIM_ABRIR_SALTO = 0.10


def main():
	rows = json.load(open(sys.argv[1], encoding="utf-8"))["corridas"]
	lb, ln = (sys.argv[2], sys.argv[3]) if len(sys.argv) >= 4 else ("old", "new")
	by = {}
	for r in rows:
		by.setdefault(r["par"], {})[r["lado"]] = r
	pares = [(v[lb], v[ln]) for k, v in sorted(by.items()) if lb in v and ln in v]
	out = {"n_pares": len(pares), "lados": [lb, ln]}
	medias = {}
	for lado in sorted({r["lado"] for r in rows}):
		medias[lado] = {}
		for nm in ("abrir_s", "salto1_ceu", "abrir_mais_salto"):
			v = [M[nm](r) for r in rows if r["lado"] == lado and r.get("salto1_ceu")]
			v = [x for x in v if x is not None]
			if len(v) >= 2:
				medias[lado][nm] = {"n": len(v), "media": round(st.mean(v), 3), "dp": round(st.stdev(v), 3)}
	out["medias"] = medias
	for nm, f in M.items():
		o, n = [], []
		for a, b in pares:
			try:
				x, y = f(a), f(b)
			except (KeyError, TypeError):
				continue
			if x is None or y is None:
				continue
			o.append(x)
			n.append(y)
		k = len(o)
		if k < 2:
			out[nm] = {"n": k}
			continue
		d = [y - x for x, y in zip(o, n)]
		md, sd = st.mean(d), st.stdev(d)
		half = T975.get(k - 1, 1.96) * sd / math.sqrt(k)
		rnd = random.Random(20261119)
		bm, bmed = [], []
		for _ in range(10000):
			idx = [rnd.randrange(k) for _ in range(k)]
			bm.append(st.mean([d[i] for i in idx]))
			bmed.append(st.median([n[i] for i in idx]) - st.median([o[i] for i in idx]))
		bm.sort()
		bmed.sort()
		lo, hi = int(0.025 * 10000) - 1, int(0.975 * 10000) - 1
		ic_t = [round(md - half, 3), round(md + half, 3)]
		ic_b = [round(bm[lo], 3), round(bm[hi], 3)]
		out[nm] = {"n": k, "antigo_mediana": round(st.median(o), 3), "novo_mediana": round(st.median(n), 3),
				   "dif_media": round(md, 3), "ic95_t": ic_t, "ic95_bootstrap_media": ic_b,
				   "dif_medianas": round(st.median(n) - st.median(o), 3), "ic95_bootstrap_medianas": [round(bmed[lo], 3), round(bmed[hi], 3)],
				   "antigo": [round(x, 2) for x in o], "novo": [round(x, 2) for x in n]}
		if nm in CRIT:
			out[nm]["exclui_+0.25"] = ic_t[1] < 0.25 and ic_b[1] < 0.25
	out["criterio_12"] = all(out[nm].get("exclui_+0.25") for nm in CRIT)
	if "ic95_t" in out.get("abrir_mais_salto", {}):
		out["criterio_abrir_mais_salto"] = out["abrir_mais_salto"]["ic95_t"][1] <= LIM_ABRIR_SALTO
	print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
	main()
