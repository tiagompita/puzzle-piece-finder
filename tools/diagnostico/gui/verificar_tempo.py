"""F2 (plano §6 j): tempo do «verificar» de «Pôr uma peça à mão» no servidor real, numa cópia nova por cenário.

	.venv/Scripts/python.exe tools/diagnostico/gui/verificar_tempo.py --base <cópia> --work <pasta> --out <json>
		[--cell 1,29] [--piece P1422] [--repeticoes 2]

Cenários (cada um num servidor novo, intervalo do GIL por omissão, 0,5 ms):
- **parado**: «pronto», sem abrir a GUI (o ranking dos buracos não corre); 1.º ``verificar`` sem θ (as 4 rotações, a
  frio: o processo ainda não leu tiras nem lados) e depois 4 com θ (a quente);
- **com o ranking a frio**: ``GET /api/montar`` (o que a GUI nova faz ao abrir) e 1 s depois o 1.º ``verificar``, a
  frio, enquanto o ranking corre; depois um 2.º.
Tempo = do pedido à resposta (HTTP); ``segundos`` = o que o servidor mediu dentro do ``verify_json``.
"""
import argparse
import json
import os
import shutil
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import salto_frio_gil as G  # noqa: E402


def _post(path, body):
	rq = urllib.request.Request(G.BASE_URL + path, data=json.dumps(body).encode(), method="POST",
								headers={"Content-Type": "application/json"})
	t0 = time.perf_counter()
	with urllib.request.urlopen(rq, timeout=900) as r:
		out = json.loads(r.read())
	return out, round(time.perf_counter() - t0, 3)


def _one(cell, piece, theta):
	b = {"piece": piece} if theta is None else {"piece": piece, "theta_deg": theta}
	r, s = _post(f"/api/cell/{cell[0]}/{cell[1]}/verificar", b)
	return {"theta_pedido": theta, "theta": r.get("theta_deg"), "http_s": s, "servidor_s": r.get("segundos"),
			"linhas": [(x["chave"], x["estado"]) for x in r.get("verificacoes", [])], "falha": r.get("falha")}


def run(base, work, tag, cell, piece, ranking):
	proj = os.path.join(work, f"proj_{tag}")
	shutil.rmtree(proj, ignore_errors=True)
	shutil.copytree(base, proj)
	p, f = G._start(proj, 0.0005, os.path.join(work, f"srv_{tag}.log"))
	out = {"cenario": tag, "ranking_a_correr": ranking, "pedidos": []}
	try:
		G._wait_ready()
		G._get("/api/board.jpg?ppc=60&v=x")
		if ranking:
			G._get("/api/montar", 600)
			time.sleep(1.0)
			out["buracos_a_calcular"] = bool(G._json("/api/holes", 600).get("a_calcular"))
		r = _one(cell, piece, None)
		out["pedidos"].append(r)
		th = r["theta"]
		for k in range(4 if not ranking else 1):
			out["pedidos"].append(_one(cell, piece, ((th + 90 * (k + 1)) + 180) % 360 - 180))
	finally:
		G._stop(p, f)
		shutil.rmtree(proj, ignore_errors=True)
	print(json.dumps(out), flush=True)
	return out


def main(argv=None) -> int:
	ap = argparse.ArgumentParser()
	ap.add_argument("--base", required=True)
	ap.add_argument("--work", required=True)
	ap.add_argument("--out", required=True)
	ap.add_argument("--cell", default="1,29")
	ap.add_argument("--piece", default="P1422")
	ap.add_argument("--repeticoes", type=int, default=2)
	a = ap.parse_args(argv)
	cell = tuple(int(x) for x in a.cell.split(","))
	os.makedirs(a.work, exist_ok=True)
	rows = []
	for k in range(a.repeticoes):
		rows.append(run(a.base, a.work, f"parado{k + 1}", cell, a.piece, False))
		rows.append(run(a.base, a.work, f"ranking{k + 1}", cell, a.piece, True))
	with open(a.out, "w", encoding="utf-8") as fh:
		json.dump(rows, fh, ensure_ascii=False, indent=1)
	return 0


if __name__ == "__main__":
	sys.exit(main())
