"""P-b correção, passo 0 b): o que os leitores de placements.json decidem, antes e depois de completar as entradas.

Uso: python leitores.py <base> <cópia> <saída.json> [--completar]
--completar: antes de medir, grava para cada peça colocada sem entrada válida register_piece(image=False) (regra cantos)
e refaz as válidas com a mesma regra (o que o servidor novo fará)."""
import sys, os, json, re, glob, hashlib, shutil, time, random
import guarda  # noqa: E402 (tools/diagnostico/gui/guarda.py)
REPO = r"D:\DEKSTOP\puzzle_piece_finder"
sys.path.insert(0, REPO)
base, work, out = sys.argv[1:4]
completar = "--completar" in sys.argv
guarda.rmtree(work, ignore_errors=True)
guarda.copytree(base, work)
from src.state import Project
from src import render, consistency, fit as F
from src import server as S
from src.query import run_query

def h(fp):
	return hashlib.sha1(open(fp, "rb").read()).hexdigest()

pr = Project.open(work)
res = {"completar": completar}
if completar:
	t0 = time.time()
	d = render.load_placements(pr)
	n = 0
	for pid in render.placed_ids(pr):
		r = render.register_piece(pr, pid, art=None, image=False)
		if "error" in r:
			continue
		r["key"] = render._entry_key(pr, pid)
		r["image_used"] = False
		d["placements"][pid] = r
		n += 1
	d["log_len"] = render._log_len(pr)
	render.save_placements(pr, d)
	res["completadas"] = n
	print("completadas", n, round(time.time() - t0, 1), "s")
pr = Project.open(work)
t0 = time.time()
r = run_query(pr, use_image=True)
print("query", round(time.time() - t0, 1), "s")
fj = json.load(open(pr.p("fetch.json"), encoding="utf-8")); fj.pop("t", None)
res["fetch_json"] = fj
res["fetch_md"] = re.sub(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?", "<t>", open(pr.p("fetch.md"), encoding="utf-8").read())
res["fetch_jpg"] = {os.path.basename(fp): h(fp) for fp in sorted(glob.glob(pr.p("fetch_*.jpg")))}
# suspeitas: as poses do servidor (_susp_placements = placements com chave válida)
pl = {pid: e for pid, e in (render.load_placements(pr).get("placements") or {}).items()
	  if pid in pr.pieces and e.get("key") == render._entry_key(pr, pid)}
res["suspeitas"] = consistency.evaluate(pr, dict(pl))
# buracos
t0 = time.time()
rk = F.rank_all(pr)
res["buracos"] = [{"cell": hh["cell"], "conf": hh["confidence"], "d1": hh["d1"], "cands": [(c["id"], c["rank"], c["J"], c["rot"]) for c in hh["candidates"]]}
				  for hh in rk.get("holes", [])]
print("buracos", len(res["buracos"]), round(time.time() - t0, 1), "s")
# verificar: amostra fixa (12 buracos, 3 soltas cada, theta None e 0)
gui = S.Gui(work, prepare=False, use_image=False, log=None, queue=False)
rng = random.Random(20261115)
holes = sorted(tuple(x["cell"]) for x in res["buracos"])
soltas = sorted(pid for pid, p in pr.pieces.items() if p.estado == "solta")
amostra = [(l, c, pid, th) for (l, c) in rng.sample(holes, 12) for pid in rng.sample(soltas, 3) for th in (None, 0.0)]
ver = []
for l, c, pid, th in amostra:
	v = gui.verify_json(l, c, pid, th)
	v.pop("ms", None); v.pop("segundos", None)
	ver.append(v)
res["verificar"] = ver
gui.stop()
json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, default=str, indent=0)
print("ok")
