"""Critério 11 da F4 (F4_PLANO.md §4): um grupo solto não toca no que o tabuleiro desenha.

Numa cópia do projeto (``shutil.copytree`` da base; nunca o projeto real), servidor real (``python -m src.server``):

1. código novo (este checkout), servidor a abrir: instantâneo S0 (sem grupos mostrados);
2. «Mostrar no tabuleiro» de todos os grupos soltos e 10 «Mover» com êxito no maior grupo; instantâneos S1 (depois
   de mostrar) e S2 (depois dos 10 «Mover»), no mesmo servidor;
3. o mesmo servidor reiniciado sobre a mesma cópia (composição a frio): S3; e outra vez com o ``mesa.jsonl`` cortado
   às linhas dos «Mostrar» (S1, as regiões do grupo só se conhecem depois dos «Mover»). Antes de cada reinício volta
   o ``render/gui/board_60.*`` da base (cada arranque re-codifica esse JPEG: ver ``restore_board_cache``);
4. código antigo (``--repo``, por omissão um ``git worktree`` de ``cc68ad4``) sobre outra cópia da mesma base: S_old.

Um instantâneo: sha1 dos bytes de ``log.jsonl`` e de ``render/placements.json``, o tamanho do log e o ``mtime_ns`` de
``placements.json`` (= ``Gui.render_version()``), o ``versao`` de ``/api/status``, e o sha1 das bytes servidas de
``/api/board.jpg`` (tabuleiro inteiro, ppc 60) e das regiões de detalhe (céu, vale, relva e a caixa por onde o grupo
andou, ppc 100; e as mesmas a ppc 40). Iguais: S0 = S_old (sem grupos mostrados, código antigo) e S1 = S2 = S3 = S_old
em tudo (as regiões do grupo só existem de S1 em diante). Também conta os ``board_changed`` recebidos durante os
«Mostrar» e «Mover» (esperado: 0).

Uso: ``python tools/diagnostico/gui/f4_iguais.py <base> <trabalho> <saída.json> --repo <checkout antigo>``."""
import argparse
import hashlib
import json
import os
import shutil
import guarda  # noqa: E402 (tools/diagnostico/gui/guarda.py)
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "tools", "diagnostico", "gui"))
import gil_intervalo as G  # noqa: E402

G.PORT = 8794
G.BASE_URL = f"http://127.0.0.1:{G.PORT}"
FIXAS = {"ceu": (1, 20, 14, 40), "vale": (20, 1, 33, 21), "relva": (34, 30, 47, 50)}
PPCS = (100, 40)
DELTAS = [(0, 1), (1, 0), (0, -1), (-1, 0), (0, 2), (2, 0), (0, -2), (-2, 0), (1, 1), (-1, -1), (0, 3), (3, 0),
		  (0, -3), (-3, 0), (2, 2), (-2, -2)]


def sha(b):
	return hashlib.sha1(b).hexdigest()


def start(repo, proj, up, logf):
	f = open(logf, "w", encoding="utf-8")
	p = subprocess.Popen([sys.executable, "-m", "src.server", "--project", proj, "--port", str(G.PORT), "--uploads", up,
						  "--ui", "novo"], cwd=repo, stdout=f, stderr=subprocess.STDOUT, env=dict(os.environ, PPF_REPO=repo))
	t0 = time.time()
	while True:
		if p.poll() is not None:
			f.close()
			raise RuntimeError(f"o servidor saiu com {p.returncode}: ver {logf}")
		try:
			st = G._json("/api/status", 30)
			if st.get("estado") == "pronto" and not st.get("job"):
				break
		except Exception:  # noqa: BLE001 - not up yet
			pass
		if time.time() - t0 > 900:
			raise RuntimeError("servidor não ficou pronto")
		time.sleep(0.5)
	G._wait_holes()          # the placements fill (if any) ends before the hole ranking starts
	G._wait_ready()
	return p, f


class Events(threading.Thread):
	def __init__(self):
		super().__init__(daemon=True)
		self.seen = []

	def run(self):
		try:
			with urllib.request.urlopen(G.BASE_URL + "/api/events", timeout=3600) as r:
				name = None
				for raw in r:
					line = raw.decode("utf-8", "replace").rstrip("\r\n")
					if line.startswith("event: "):
						name = line[7:]
					elif line == "" and name:
						self.seen.append(name)
						name = None
		except Exception:  # noqa: BLE001 - the server went away
			pass


def post(path, body):
	rq = urllib.request.Request(G.BASE_URL + path, data=json.dumps(body).encode(), method="POST",
								headers={"Content-Type": "application/json"})
	try:
		with urllib.request.urlopen(rq, timeout=300) as r:
			return r.status, json.loads(r.read())
	except urllib.error.HTTPError as e:
		return e.code, json.loads(e.read())


def snapshot(proj, regions):
	log = os.path.join(proj, "log.jsonl")
	pl = os.path.join(proj, "render", "placements.json")
	out = {"log_sha": sha(open(log, "rb").read()), "log_bytes": os.stat(log).st_size,
		   "placements_sha": sha(open(pl, "rb").read()), "placements_mtime_ns": os.stat(pl).st_mtime_ns,
		   "versao": G._json("/api/status", 60).get("versao")}
	out["render_version"] = [out["log_bytes"], out["placements_mtime_ns"]]
	out["board_jpg_60"] = sha(G._get("/api/board.jpg?ppc=60&v=x")[0])
	for nome, (l0, c0, l1, c1) in sorted(regions.items()):
		for ppc in PPCS:
			out[f"regiao_{nome}_{ppc}"] = sha(G._get(f"/api/board.jpg?ppc={ppc}&region={l0},{c0},{l1},{c1}&v=x")[0])
	return out


def restore_board_cache(base, proj):
	"""Put back the base's ``render/gui/board_60.*``: every server start decodes that JPEG and writes it re-encoded
	(``Gui._base``, anterior à F4), so a restart alone changes the bytes of the full board (perda por geração). The
	restarts below compare like with like."""
	for n in ("board_60.jpg", "board_60.json"):
		shutil.copy2(os.path.join(base, "render", "gui", n), os.path.join(proj, "render", "gui", n))


def diff(a, b, keys=None):
	keys = keys or sorted(set(a) & set(b))
	return [k for k in keys if a.get(k) != b.get(k)]


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("base")
	ap.add_argument("work")
	ap.add_argument("out")
	ap.add_argument("--repo", required=True, help="checkout antigo (cc68ad4)")
	ap.add_argument("--n", type=int, default=10)
	a = ap.parse_args()
	os.makedirs(a.work, exist_ok=True)
	up = os.path.join(a.work, "up")
	pn, po = os.path.join(a.work, "proj_novo"), os.path.join(a.work, "proj_antigo")
	for p in (pn, po):
		guarda.rmtree(p, ignore_errors=True)
		guarda.copytree(a.base, p)
	res = {"base": a.base, "repo_antigo": a.repo, "repo_novo": ROOT}

	# 1–2: código novo
	p, f = start(ROOT, pn, up, os.path.join(a.work, "srv_novo.log"))
	ev = Events()
	ev.start()
	time.sleep(1)
	s0 = snapshot(pn, FIXAS)
	n0 = len(ev.seen)
	gr = G._json("/api/grupos")["grupos"]
	mostrados = 0
	for i, g in enumerate(gr):
		st, r = post(f"/api/grupos/{g['id']}/mostrar", {"centro": [5 + (i % 8) * 5, 5 + (i // 8) * 14]})
		mostrados += st == 200
	gr = {g["id"]: g for g in G._json("/api/grupos")["grupos"]}
	gid = max(sorted(gr), key=lambda k: gr[k]["n"])
	moves, tried, boxes = [], 0, [gr[gid]["footprint"]]
	for dl, dc in DELTAS * 4:
		if len(moves) >= a.n:
			break
		pos = G._json("/api/grupos")
		cur = next(g for g in pos["grupos"] if g["id"] == gid)["posicao"]
		tried += 1
		t = time.perf_counter()
		st, r = post(f"/api/grupos/{gid}/mover", {"l0": cur["l0"] + dl, "c0": cur["c0"] + dc, "rot": cur["rot"]})
		s = time.perf_counter() - t
		if st == 200:
			moves.append({"l0": cur["l0"] + dl, "c0": cur["c0"] + dc, "s": round(s, 4)})
			boxes.append(r["grupo"]["footprint"])
	cells = [c for fp in boxes for c in fp]
	regions = dict(FIXAS)
	regions["grupo"] = (max(1, min(c[0] for c in cells) - 1), max(1, min(c[1] for c in cells) - 1),
						min(47, max(c[0] for c in cells) + 1), min(64, max(c[1] for c in cells) + 1))
	time.sleep(1)
	n_ev_mover = ev.seen[n0:]
	# the group region is only known after the moves: S1 («depois de Mostrar, antes dos Mover») is taken below on the
	# same copy with the mesa.jsonl cut back to the Mostrar lines and a fresh server
	s2 = snapshot(pn, regions)
	res.update(grupo=gid, n_pecas=gr[gid]["n"], mostrados=mostrados, n_grupos=len(gr), moves=moves, tentativas=tried,
			   regioes=regions, eventos_depois_de_s0=n_ev_mover,
			   board_changed_durante=sum(1 for e in n_ev_mover if e == "board_changed"))
	G._stop(p, f)
	restore_board_cache(a.base, pn)
	# 3: same copy, fresh server (cold composition), and the mesa.jsonl cut back to the Mostrar lines (S1)
	p, f = start(ROOT, pn, up, os.path.join(a.work, "srv_novo2.log"))
	s3 = snapshot(pn, regions)
	G._stop(p, f)
	mesa = os.path.join(pn, "mesa.jsonl")
	lines = open(mesa, encoding="utf-8").read().splitlines(True)
	res["mesa_linhas"] = len(lines)
	with open(mesa, "w", encoding="utf-8", newline="") as fh:
		fh.writelines(lines[:len(lines) - len(moves)])
	restore_board_cache(a.base, pn)
	p, f = start(ROOT, pn, up, os.path.join(a.work, "srv_novo3.log"))
	s1 = snapshot(pn, regions)
	g1 = next(g for g in G._json("/api/grupos")["grupos"] if g["id"] == gid)["posicao"]
	res["posicao_s1"] = g1
	G._stop(p, f)

	# 4: código antigo
	p, f = start(a.repo, po, up, os.path.join(a.work, "srv_antigo.log"))
	so = snapshot(po, regions)
	G._stop(p, f)

	fix_keys = [k for k in s0 if not k.startswith("regiao_grupo")]
	res["instantaneos"] = {"S0": s0, "S1": s1, "S2": s2, "S3": s3, "S_old": so}
	res["diferencas"] = {"S0_vs_S_old": diff(s0, so, fix_keys), "S1_vs_S2": diff(s1, s2), "S2_vs_S3": diff(s2, s3),
						 "S1_vs_S_old": diff(s1, so), "S0_vs_S2": diff(s0, s2, fix_keys)}
	# the server's own versao is an int (log size): the same in all, the placements mtime is the copy's (copytree keeps it)
	res["iguais"] = all(not v for v in res["diferencas"].values()) and res["board_changed_durante"] == 0 \
		and len(moves) == a.n
	with open(a.out, "w", encoding="utf-8") as fh:
		json.dump(res, fh, indent=1, ensure_ascii=False)
	print(json.dumps({"iguais": res["iguais"], "diferencas": res["diferencas"], "moves": len(moves),
					  "mostrados": mostrados, "board_changed": res["board_changed_durante"]}, ensure_ascii=False))
	guarda.rmtree(po, ignore_errors=True)


if __name__ == "__main__":
	main()
