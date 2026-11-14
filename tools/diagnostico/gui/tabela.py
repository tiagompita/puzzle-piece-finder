"""Tabela Markdown a partir dos JSON de ``salto_detalhe.py`` (um ou mais ficheiros, mesma ordem de cenários).

	.venv/Scripts/python.exe tools/diagnostico/gui/tabela.py antes_novo_1920.json depois_novo_1920.json
"""
import json
import sys


def linha(r: dict) -> str:
	d = r.get("detalhe") or []
	dur = [x["dur_ms"] for x in d if x.get("dur_ms") is not None]
	kb = [x["kb"] for x in d if x.get("ok")]
	pos = r.get("detalhe_depois_post_s")
	return (f"| {r['cenario']} | {r['detalhe_s'] if r['detalhe_s'] is not None else '—'}"
			+ (f" (POST {r.get('post_s')}, depois {pos})" if pos is not None else "")
			+ f" | {r['detalhe_enviados']} / {r['detalhe_terminados']} / {r['detalhe_cancelados'] + r['detalhe_falhados']}"
			f" | {r['pico_em_voo']} | {r['fila_max_ms']} | {max(dur) if dur else '—'} | {max(kb) if kb else '—'}"
			f" | {r['sondas_max_ms']} | {len(r['longtasks_ms'])} / {r['n_longtasks_200']} | {r['raf_max_gap_ms']} |")


def main(argv) -> int:
	for fp in argv:
		with open(fp, encoding="utf-8") as f:
			j = json.load(f)
		print(f"\n**{fp.split('/')[-1].split(chr(92))[-1]}** ({j['ui']}, {j['vw']}×{j['vh']}, dpr {j['dpr']})\n")
		print("| cenário | detalhe (s) | pedidos env. / mostrados+ok / cancel.+falh. | pico em voo | fila máx. (ms) "
			  "| pedido máx. (ms) | KB | sonda máx. (ms) | long tasks / > 200 ms | rAF máx. (ms) |")
		print("|---|---|---|---|---|---|---|---|---|---|")
		for r in j["rows"]:
			print(linha(r))
	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
