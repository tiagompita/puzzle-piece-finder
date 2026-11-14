"""Passo 0a da F2 (DETALHE.md §8): salto a frio com o servidor parado, intervalo do GIL 5 ms contra 0,5 ms.

	.venv/Scripts/python.exe tools/diagnostico/gui/salto_frio_gil.py --base <cópia> --work <pasta> --out <json>
		[--ordem 5,0.5,0.5,5,5,0.5] [--preparar] [--protocolo-r2]

«Parado» = nada do arranque a correr por baixo da medida: cada corrida faz uma cópia nova de ``--base`` com
``shutil.copytree`` (o mtime de ``render/placements.json`` fica; ver DETALHE.md §6), arranca um servidor novo
(``--gil-intervalo 0`` = 5 ms do Python, ou ``0.0005``), espera por ``/api/status`` pronto, pede o tabuleiro inteiro
(da cache do disco), arranca o ranking dos buracos e espera que acabe, e só então mede:

1. **browser** (``salto_detalhe.py --cenarios saltos``, GUI nova 1920 × 1080): céu (5,30) e relva (44,40) a frio, o mesmo
   gesto e a mesma região (l±5 c±8 + margem, ppc 100) das rondas 1 e 2;
2. **só o servidor** (HTTP, sem browser): uma região fria de céu e uma de relva do mesmo tamanho, deslocadas 3 colunas
   (``CEU3``/``RELVA3``), o tempo do pedido.

``--protocolo-r2``: uma corrida extra com o protocolo dos saltos da ronda 2 (o browser abre ``/novo/`` logo que o
estado diz «pronto», sem esperar pelos buracos; a abertura arranca o ranking) para ver se explica os 2,9–3,5 s.

Nunca sobre ``projects/alpes``.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
PY = sys.executable
PORT = 8796
BASE_URL = f"http://127.0.0.1:{PORT}"
CEU3, RELVA3 = "1,23,14,43", "34,33,47,53"


def _get(path, timeout=900):
	t0 = time.perf_counter()
	with urllib.request.urlopen(BASE_URL + path, timeout=timeout) as r:
		body = r.read()
	return body, time.perf_counter() - t0


def _json(path, timeout=900):
	return json.loads(_get(path, timeout)[0])


def _wait_ready(timeout=900):
	t0 = time.time()
	while time.time() - t0 < timeout:
		try:
			st = _json("/api/status", 30)
			if st.get("estado") == "pronto" and not st.get("job"):
				return time.time() - t0
		except Exception:  # noqa: BLE001 - not up yet
			pass
		time.sleep(0.5)
	raise RuntimeError("servidor não ficou pronto")


def _wait_holes(timeout=900):
	t0 = time.time()
	while time.time() - t0 < timeout:
		h = _json("/api/holes", 600)
		if not h.get("a_calcular"):
			return time.time() - t0
		time.sleep(0.5)
	raise RuntimeError("buracos não acabaram")


def _start(project, switch, log_path):
	f = open(log_path, "w", encoding="utf-8")
	p = subprocess.Popen([PY, "-m", "src.server", "--project", project, "--port", str(PORT), "--ui", "novo",
						  "--gil-intervalo", str(switch)], cwd=ROOT, stdout=f, stderr=subprocess.STDOUT)
	return p, f


def _stop(p, f):
	p.terminate()
	try:
		p.wait(30)
	except subprocess.TimeoutExpired:
		p.kill()
		p.wait(30)
	f.close()


def _browser(out_json):
	cmd = [PY, os.path.join(ROOT, "tools", "diagnostico", "gui", "salto_detalhe.py"), "--url", BASE_URL, "--ui", "novo",
		   "--cenarios", "saltos", "--out", out_json]
	subprocess.run(cmd, cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
	with open(out_json, encoding="utf-8") as fh:
		rows = json.load(fh)["rows"]
	return {r["cenario"]: r["detalhe_s"] for r in rows}


def run_once(base, work, switch_ms, tag, *, r2=False):
	proj = os.path.join(work, f"proj_{tag}")
	if os.path.exists(proj):
		shutil.rmtree(proj)
	t0 = time.time()
	shutil.copytree(base, proj)
	r = {"tag": tag, "intervalo_ms": switch_ms, "copia_s": round(time.time() - t0, 1), "protocolo": "r2" if r2 else "parado"}
	sw = 0 if abs(switch_ms - 5) < 1e-9 else switch_ms / 1000.0
	p, f = _start(proj, sw, os.path.join(work, f"srv_{tag}.log"))
	try:
		r["arranque_s"] = round(_wait_ready(), 1)
		r["tabuleiro_s"] = round(_get("/api/board.jpg?ppc=60&v=x")[1], 2)
		if not r2:
			_get("/api/montar", 600)
			r["buracos_s"] = round(_wait_holes(), 1)
			_wait_ready()
			time.sleep(3)
		b = _browser(os.path.join(work, f"browser_{tag}.json"))
		r["browser_ceu_frio_s"] = b.get("salto ceu frio")
		r["browser_relva_frio_s"] = b.get("salto relva frio")
		r["browser_ceu_morno_s"] = b.get("salto ceu morno (+1 col)")
		r["browser_relva_morno_s"] = b.get("salto relva morno (+1 col)")
		if r2:
			r["buracos_s_depois"] = round(_wait_holes(), 1)
		_wait_ready()
		time.sleep(2)
		r["servidor_ceu_s"] = round(_get(f"/api/board.jpg?ppc=100&region={CEU3}&v=x")[1], 2)
		r["servidor_relva_s"] = round(_get(f"/api/board.jpg?ppc=100&region={RELVA3}&v=x")[1], 2)
		with open(os.path.join(work, f"srv_{tag}.log"), encoding="utf-8", errors="replace") as fh:
			r["linha_gil"] = next((ln.strip()[-80:] for ln in fh if "intervalo do GIL" in ln), None)
	finally:
		_stop(p, f)
		shutil.rmtree(proj, ignore_errors=True)
	print(json.dumps(r), flush=True)
	return r


def main(argv=None) -> int:
	ap = argparse.ArgumentParser()
	ap.add_argument("--base", required=True)
	ap.add_argument("--work", required=True)
	ap.add_argument("--out", required=True)
	ap.add_argument("--ordem", default="5,0.5,0.5,5,5,0.5")
	ap.add_argument("--preparar", action="store_true")
	ap.add_argument("--protocolo-r2", action="store_true")
	a = ap.parse_args(argv)
	base = os.path.abspath(a.base)
	if os.path.abspath(os.path.join(ROOT, "projects")) in base:
		raise SystemExit("--base tem de ser uma cópia fora de projects/")
	os.makedirs(a.work, exist_ok=True)
	if a.preparar:
		p, f = _start(base, 0.0005, os.path.join(a.work, "srv_preparar.log"))
		try:
			_wait_ready()
			_get("/api/board.jpg?ppc=60&v=x")
			_get("/api/montar", 600)
			_wait_holes()
			_wait_ready()
		finally:
			_stop(p, f)
	rows = []
	for k, s in enumerate(a.ordem.split(",")):
		rows.append(run_once(base, a.work, float(s), f"{k + 1}"))
	if a.protocolo_r2:
		rows.append(run_once(base, a.work, 0.5, "r2", r2=True))
	with open(a.out, "w", encoding="utf-8") as fh:
		json.dump({"ordem": a.ordem, "rows": rows}, fh, ensure_ascii=False, indent=1)
	return 0


if __name__ == "__main__":
	sys.exit(main())
