"""Experiência H (DETALHE.md §6): ``sys.setswitchinterval`` no servidor, com e sem, no servidor real (HTTP).

	.venv/Scripts/python.exe tools/diagnostico/gui/gil_intervalo.py --base <cópia> --work <pasta> --out <json>
		[--switch 0.0005] [--ordem sem,com,sem,com,sem,com] [--preparar]

Cada corrida: cópia nova de ``--base`` (o estado de partida é igual em todas), um servidor novo
(``python -m src.server --gil-intervalo x``; «sem» = ``--gil-intervalo 0`` = omissão do Python, 0,005 s),
e três medidas:

1. **detalhe com os buracos a frio**: ``GET /api/montar`` (arranca o ranking dos buracos num fio, como o 1.º pedido da
   GUI nova), 2 s depois compõe uma região de céu e depois uma de relva a ppc 100 (``/api/board.jpg?region=``, LRU vazia),
   tempo de cada pedido; o tempo total do ranking (até ``/api/holes`` deixar de dizer ``a_calcular``) fica ao lado,
   e, como referência, as mesmas zonas deslocadas 1 coluna (também frias) depois de o ranking acabar;
2. **reconsulta**: com o servidor parado (pronto, buracos feitos), ``POST /api/confirm`` ``place`` de uma solta numa
   célula vazia longe e depois ``unplace`` com ``desfaz``; tempo de cada POST e o da consulta incremental (linha
   ``consulta incremental … em X s`` do registo de atividade);
3. **importação**: ``POST /api/ingest`` de uma folha de 10 peças (bytes acrescentados no fim, sha256 nova) num saco
   novo; tempo do trabalho (``segundos`` da fila) e o da consulta completa dentro dele (``wlock_consulta_s``).

Nunca sobre ``projects/alpes``: ``--base`` tem de ser uma cópia, feita com ``shutil.copytree`` (guarda o mtime ao
nanossegundo): com ``cp -r`` o ``render/placements.json`` muda de mtime, a cache do raster em disco
(``render/gui/board_60.json``, ``pl_mtime``) deixa de valer e cada arranque recompõe o tabuleiro inteiro por baixo
das medidas (``tabuleiro_s`` mostra-o). ``--preparar`` corre o servidor uma vez sobre a base
(ativos desatualizados refeitos e tiras dos buracos em disco) para que nenhuma corrida pague isso.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
PY = sys.executable
PORT = 8797
BASE_URL = f"http://127.0.0.1:{PORT}"
CEU, RELVA = "1,21,14,41", "34,31,47,51"
CEU2, RELVA2 = "1,22,14,42", "34,32,47,52"
FOLHA = os.path.join(ROOT, "images", "pieces", "lotes", "lote07_20261108_162220_lote7_2_.jpg")
LOTE = 99


def _get(path, timeout=600, headers=None):
	rq = urllib.request.Request(BASE_URL + path, headers=headers or {})
	t0 = time.perf_counter()
	with urllib.request.urlopen(rq, timeout=timeout) as r:
		body = r.read()
	return body, time.perf_counter() - t0


def _json(path, timeout=600):
	return json.loads(_get(path, timeout)[0])


def _post(path, body, timeout=900):
	rq = urllib.request.Request(BASE_URL + path, data=json.dumps(body).encode(), method="POST",
								headers={"Content-Type": "application/json"})
	t0 = time.perf_counter()
	with urllib.request.urlopen(rq, timeout=timeout) as r:
		out = json.loads(r.read())
	return out, time.perf_counter() - t0


def _post_file(path, fields, fname, data, timeout=900):
	b = uuid.uuid4().hex
	parts = []
	for k, v in fields.items():
		parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
	parts.append(f'--{b}\r\nContent-Disposition: form-data; name="files"; filename="{fname}"\r\n'
				 f'Content-Type: image/jpeg\r\n\r\n'.encode() + data + b"\r\n")
	parts.append(f"--{b}--\r\n".encode())
	rq = urllib.request.Request(BASE_URL + path, data=b"".join(parts), method="POST",
								headers={"Content-Type": f"multipart/form-data; boundary={b}"})
	with urllib.request.urlopen(rq, timeout=timeout) as r:
		return json.loads(r.read())


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
		h = _json("/api/holes", 120)
		if not h.get("a_calcular"):
			return h.get("resumo", {})
		time.sleep(0.5)
	raise RuntimeError("buracos não acabaram")


def _start(project, switch, log_path, uploads):
	# ``--gil-intervalo`` (src.server, desde esta ronda; omissão 0,0005; 0 = o do Python, 0,005). As 6 corridas do
	# DETALHE.md §6 foram feitas antes de a opção existir, com ``sys.setswitchinterval`` num ``python -c`` à volta de
	# ``runpy.run_module('src.server')``: o mesmo efeito (antes de qualquer fio arrancar). O servidor escreve o valor
	# em vigor na linha «mesa de montagem: … intervalo do GIL N ms» do registo.
	f = open(log_path, "w", encoding="utf-8")
	p = subprocess.Popen([PY, "-m", "src.server", "--project", project, "--port", str(PORT), "--uploads", uploads,
						  "--ui", "novo", "--gil-intervalo", str(switch or 0)], cwd=ROOT, stdout=f, stderr=subprocess.STDOUT)
	return p, f


def _stop(p, f):
	p.terminate()
	try:
		p.wait(30)
	except subprocess.TimeoutExpired:
		p.kill()
		p.wait(30)
	f.close()


def _pick_write(project):
	"""Uma solta e uma célula vazia longe das zonas medidas (a mesma em todas as corridas: a base é a mesma)."""
	sys.path.insert(0, ROOT)
	from src.state import Project
	pr = Project.open(project)
	loose = sorted(pid for pid, p in pr.pieces.items() if p.estado == "solta")
	for cell in ((20, 60), (22, 58), (25, 50)):
		if pr.board[cell]["estado"] == "vazia":
			return loose[0], list(cell)
	raise RuntimeError("sem célula vazia")


def _consultas(log_dir):
	out = []
	for fn in sorted(os.listdir(log_dir)) if os.path.isdir(log_dir) else []:
		with open(os.path.join(log_dir, fn), encoding="utf-8", errors="replace") as fh:
			for ln in fh:
				m = re.search(r"consulta (incremental|completa): .* em ([0-9.]+) s", ln)
				if m:
					out.append((m.group(1), float(m.group(2))))
	return out


def run_once(base, work, switch, tag, folha_bytes):
	proj = os.path.join(work, f"proj_{tag}")
	if os.path.exists(proj):
		shutil.rmtree(proj)
	t0 = time.time()
	shutil.copytree(base, proj)
	copy_s = time.time() - t0
	uploads = os.path.join(work, f"uploads_{tag}")
	os.makedirs(uploads, exist_ok=True)
	piece, cell = _pick_write(proj)
	n_log0 = len(_consultas(os.path.join(proj, "logs")))
	p, f = _start(proj, switch, os.path.join(work, f"srv_{tag}.log"), uploads)
	r = {"tag": tag, "switch": switch or 0.005, "copia_s": round(copy_s, 1)}
	try:
		r["arranque_s"] = round(_wait_ready(), 1)
		# o raster do tabuleiro inteiro, como a página ao abrir: com a cache em disco válida responde logo; se não, a
		# composição (35–60 s) correria por baixo das medidas («pronto» não espera por ela)
		r["tabuleiro_s"] = round(_get("/api/board.jpg?ppc=60&v=x")[1], 2)
		# 1. detalhe durante o ranking dos buracos a frio
		tb = time.perf_counter()
		_get("/api/montar", 120)
		h = _json("/api/holes", 120)
		r["buracos_a_frio"] = bool(h.get("a_calcular"))
		time.sleep(2)
		r["detalhe_ceu_s"] = round(_get(f"/api/board.jpg?ppc=100&region={CEU}&v=x")[1], 2)
		r["detalhe_relva_s"] = round(_get(f"/api/board.jpg?ppc=100&region={RELVA}&v=x")[1], 2)
		rs = _wait_holes()
		r["buracos_s"] = round(time.perf_counter() - tb, 1)
		r["buracos_resumo_s"] = rs.get("segundos")
		_wait_ready()
		# referência: as mesmas zonas deslocadas 1 coluna (frias), já sem o ranking a correr
		r["detalhe_ceu_sozinho_s"] = round(_get(f"/api/board.jpg?ppc=100&region={CEU2}&v=x")[1], 2)
		r["detalhe_relva_sozinho_s"] = round(_get(f"/api/board.jpg?ppc=100&region={RELVA2}&v=x")[1], 2)
		# 2. reconsulta (place + unplace desfaz), servidor parado
		out, s = _post("/api/confirm", {"acao": "place", "piece": piece, "cell": cell, "origin": "manual"})
		if out.get("error") or out.get("erro"):
			raise RuntimeError(f"place falhou: {out}")
		r["place_post_s"] = round(s, 2)
		_wait_ready()
		_wait_holes()
		out, s = _post("/api/confirm", {"acao": "unplace", "piece": piece, "desfaz": True})
		r["unplace_post_s"] = round(s, 2)
		_wait_ready()
		_wait_holes()
		cons = _consultas(os.path.join(proj, "logs"))[n_log0:]
		r["consultas_incrementais_s"] = [x for k, x in cons if k == "incremental"]
		# 3. importação de uma folha num saco novo
		n_cons = len(_consultas(os.path.join(proj, "logs")))
		ti = time.perf_counter()
		res = _post_file("/api/ingest", {"lote": LOTE}, "folha_gil.jpg", folha_bytes)
		jid = res.get("job")
		job = None
		while time.perf_counter() - ti < 1800:
			q = _json("/api/import_queue", 60)
			js = [j for j in q["fila"] if j["id"] == jid] if jid else q["fila"]
			if js and js[0]["estado"] in ("concluido", "falhado", "cancelado"):
				job = js[0]
				break
			time.sleep(0.5)
		r["importacao_parede_s"] = round(time.perf_counter() - ti, 1)
		r["importacao_estado"] = job and job["estado"]
		r["importacao_s"] = job and job.get("segundos") and round(job["segundos"], 1)
		r["importacao_consulta_s"] = job and job.get("wlock_consulta_s")
		r["importacao_pecas"] = job and job.get("n_pecas")
		cons = _consultas(os.path.join(proj, "logs"))[n_cons:]
		r["consultas_importacao_s"] = [x for k, x in cons if k == "completa"]
	finally:
		_stop(p, f)
		shutil.rmtree(proj, ignore_errors=True)
		shutil.rmtree(uploads, ignore_errors=True)
	return r


def main(argv=None) -> int:
	ap = argparse.ArgumentParser()
	ap.add_argument("--base", required=True)
	ap.add_argument("--work", required=True)
	ap.add_argument("--out", required=True)
	ap.add_argument("--switch", type=float, default=0.0005)
	ap.add_argument("--ordem", default="sem,com,sem,com,sem,com")
	ap.add_argument("--preparar", action="store_true")
	a = ap.parse_args(argv)
	base = os.path.abspath(a.base)
	if os.path.normcase(os.path.abspath(os.path.join(ROOT, "projects"))) in os.path.normcase(base):
		raise SystemExit("--base tem de ser uma cópia fora de projects/")
	os.makedirs(a.work, exist_ok=True)
	if a.preparar:
		up = os.path.join(a.work, "uploads_prep")
		p, f = _start(base, None, os.path.join(a.work, "srv_preparar.log"), up)
		try:
			print("preparar: pronto em", round(_wait_ready(), 1), "s", flush=True)
			_get("/api/montar", 120)
			print("preparar: buracos", _wait_holes().get("segundos"), "s", flush=True)
		finally:
			_stop(p, f)
	with open(FOLHA, "rb") as fh:
		data = fh.read() + b"\0gil-intervalo"           # sha256 nova: a folha não é «já importada»
	rows = []
	for i, w in enumerate(a.ordem.split(",")):
		sw = a.switch if w == "com" else None
		r = run_once(base, a.work, sw, f"{i + 1}_{w}", data)
		rows.append(r)
		print(json.dumps(r, ensure_ascii=False), flush=True)
		with open(a.out, "w", encoding="utf-8") as fh:
			json.dump(rows, fh, ensure_ascii=False, indent=1)
	return 0


if __name__ == "__main__":
	sys.exit(main())
