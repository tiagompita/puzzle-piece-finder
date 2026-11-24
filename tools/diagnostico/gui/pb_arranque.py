"""P-b: arranque com preenchimento de render/placements.json e 2.º arranque, servidor real (código do repositório).

Uso: python arranque.py <base> <work> <saída.json>
1.º arranque numa cópia nova (copytree) de <base>: linha do tempo de /api/status (50 ms), 1.ª resposta de uma região de
detalhe pedida logo que o preenchimento começa (e do /api/status nesse instante), tempo do preenchimento, gravações do
ficheiro, linhas «tabuleiro …» do registo do servidor (recomposição) e quando aparecem em relação ao preenchimento, ao
ranking dos buracos e ao pré-aquecimento. 2.º arranque na MESMA cópia: nada a preencher, nada recomposto."""
import json
import os
import re
import shutil
import guarda  # noqa: E402 (tools/diagnostico/gui/guarda.py)
import subprocess
import sys
import time

ROOT = r"D:\DEKSTOP\puzzle_piece_finder"
sys.path.insert(0, os.path.join(ROOT, "tools", "diagnostico", "gui"))
import gil_intervalo as G  # noqa: E402

G.PORT = 8798
G.BASE_URL = f"http://127.0.0.1:{G.PORT}"
base, work, out = sys.argv[1:4]
proj = os.path.join(work, "proj")
up = os.path.join(work, "up")


def start(tag):
	f = open(os.path.join(work, f"srv_{tag}.log"), "w", encoding="utf-8")
	cmd = [os.path.join(ROOT, ".venv", "Scripts", "python.exe"), "-m", "src.server", "--project", proj, "--port", str(G.PORT),
		   "--uploads", up, "--ui", "novo", "--gil-intervalo", "0.0005"]
	p = subprocess.Popen(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT)
	return p, f, time.perf_counter()


def run(tag):
	p, f, t0 = start(tag)
	res = {"tag": tag, "linha": []}
	asked = False
	pronto = None
	while time.perf_counter() - t0 < 600:
		try:
			st, s = G._get("/api/status", 30)
			st = json.loads(st)
		except Exception:  # noqa: BLE001
			time.sleep(0.05)
			continue
		t = round(time.perf_counter() - t0, 2)
		pl = st.get("placements") or {}
		res["linha"].append([t, st.get("estado"), pl.get("a_preencher"), pl.get("preenchidas"), round(s, 3)])
		if pl.get("a_preencher") and not asked:
			asked = True
			res["status_durante_preenchimento_s"] = round(s, 3)
			res["preenchimento_visto_em_s"] = t
			while True:                              # the data endpoints answer 503 until «pronto»
				try:
					_, sr = G._get("/api/board.jpg?ppc=100&region=1,23,14,43&v=x", 120)
					break
				except Exception:  # noqa: BLE001
					time.sleep(0.1)
			t2 = round(time.perf_counter() - t0, 2)
			st2 = G._json("/api/status")
			res["regiao_s"] = round(sr, 2)
			res["regiao_respondida_em_s"] = t2
			res["preenchimento_ainda_a_correr_na_resposta"] = (st2.get("placements") or {}).get("a_preencher")
			continue
		if pronto is None and st.get("estado") == "pronto":
			pronto = t
		if pronto is not None and not pl.get("a_preencher") and time.perf_counter() - t0 > pronto + 1:
			break
		time.sleep(0.05)
	res["pronto_s"] = pronto
	res["placements"] = G._json("/api/status")["placements"]
	G._wait_holes()
	time.sleep(25)                                   # the warm-up after the ranking
	res["placements_fim"] = G._json("/api/status")["placements"]
	G._stop(p, f)
	txt = open(os.path.join(work, f"srv_{tag}.log"), encoding="utf-8", errors="replace").read()
	res["linhas_tabuleiro"] = [ln for ln in txt.splitlines() if "tabuleiro" in ln]
	res["linhas_registo"] = [ln for ln in txt.splitlines() if "registo em falta" in ln or "sem registo" in ln]
	res["linhas_buracos_pre"] = [ln for ln in txt.splitlines() if ("buracos:" in ln and " em " in ln) or "pré-aquec" in ln
								or "pre-aquec" in ln or "aquecid" in ln]
	return res


guarda.rmtree(work, ignore_errors=True)
os.makedirs(up, exist_ok=True)
guarda.copytree(base, proj)
fp = os.path.join(proj, "render", "placements.json")
r = {"mtime0": os.stat(fp).st_mtime_ns}
r["arranque1"] = run("1")
r["mtime1"] = os.stat(fp).st_mtime_ns
bj = os.path.join(proj, "render", "gui", "board_60.json")
r["board_meta_pl_mtime1"] = json.load(open(bj))["pl_mtime"]
r["arranque2"] = run("2")
r["mtime2"] = os.stat(fp).st_mtime_ns
r["board_meta_pl_mtime2"] = json.load(open(bj))["pl_mtime"]
json.dump(r, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
for k in ("arranque1", "arranque2"):
	a = r[k]
	print(k, "pronto", a["pronto_s"], "placements", a["placements"], "regiao", a.get("regiao_durante_preenchimento_s"))
	for ln in a["linhas_tabuleiro"] + a["linhas_registo"]:
		print("   ", ln[:200])
print("mtime mudou 0→1", r["mtime0"] != r["mtime1"], "1→2", r["mtime1"] != r["mtime2"], "meta=ficheiro", r["board_meta_pl_mtime1"] == r["mtime1"])
