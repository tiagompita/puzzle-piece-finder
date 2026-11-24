"""Abertura de ``/novo/`` e 1.º salto, três commits em rotação (cc68ad4 | ecc9444 | árvore nova), N voltas.

Protocolo de ``pa_pares.py`` reduzido ao que interessa: cópia nova da base do lado + servidor real por corrida (como
``desempenho.Run``), página nova, **abertura** = ``performance.now()`` desde o navigationStart até ao «pronto» de
``desempenho.PRONTO_JS`` (observação dentro do browser, sem marcas na página, igual em todos os commits), **1.º salto**
(céu 5,30) = ``showCell`` até ao detalhe decodificado e visível, medido dentro do browser; **abrir + 1.º salto** = soma.
A ordem dos três lados roda a cada volta (a, b, c / b, c, a / c, a, b) para não deixar viés de posição.

Uso: ``python abrir_pares.py <voltas> <saida.json> <nome=repo=base> [<nome=repo=base> ...]`` (ordem da 1.ª volta)."""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import desempenho as D  # noqa: E402


def uma(a, browser, volta):
	with D.Run(a, f"{a.tag}_{volta}") as r:
		out = r.out
		pg, out["abrir_s"] = D.open_novo(browser)
		out["prova_abrir"] = pg.pronto["verif"]
		out["salto1_ceu"] = D.jump(pg, 5, 30)
		pg.close()
	out["abrir_mais_salto"] = round(out["abrir_s"] + out["salto1_ceu"]["s"], 3)
	return out


def main():
	voltas, outp = int(sys.argv[1]), sys.argv[2]
	lados = [x.split("=", 2) for x in sys.argv[3:]]
	from playwright.sync_api import sync_playwright
	pw = sync_playwright().start()
	br = pw.chromium.launch()
	rows = json.load(open(outp, encoding="utf-8"))["corridas"] if os.path.exists(outp) else []
	done = {(r["par"], r["lado"]) for r in rows}
	work = os.path.join(os.environ.get("PPF_SCRATCH") or os.environ.get("TEMP", "."), "abrir_pares")
	os.makedirs(work, exist_ok=True)
	try:
		for i in range(1, voltas + 1):
			rot = (i - 1) % len(lados)
			for nome, repo, base in lados[rot:] + lados[:rot]:
				if (i, nome) in done:
					continue
				a = argparse.Namespace(base=os.path.abspath(base), work=work, repo=os.path.abspath(repo), sem_acoes="", tag=nome)
				try:
					row = uma(a, br, i)
				except Exception as e:  # noqa: BLE001
					print("ERRO", i, nome, repr(e), flush=True)
					continue
				row["par"], row["lado"] = i, nome
				rows.append(row)
				with open(outp, "w", encoding="utf-8") as fh:
					json.dump({"corridas": rows}, fh, ensure_ascii=False)
				print(f"volta {i} {nome}: abrir {row['abrir_s']} salto1 {row['salto1_ceu']['s']} soma {row['abrir_mais_salto']} "
					  f"(detalhe_pedido={row['prova_abrir']['estado_no_sinal']['detalhe_pedido']})", flush=True)
	finally:
		br.close()
		pw.stop()


if __name__ == "__main__":
	main()
