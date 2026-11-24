"""P0b (DETALHE.md §11.3): o que as escritas produzem fica igual antes/depois de A1-A4 + B, numa cópia.

Uso: ``python tools/diagnostico/gui/p0b_iguais.py <repo> <projeto base> <cópia> <saída.json>``: corre, com o código de
``<repo>`` (um ``git worktree`` do commit antigo, ou o checkout atual), a mesma sequência de escritas na cópia nova
(P0096 → (20,60), desfazer, P0096 → (5,33), desfazer, P0097 → (20,60)) e grava por passo: as entradas da reconsulta
devolvidas por ``confirm``, ``fetch.json`` sem o campo ``t``, ``fetch.md`` sem a hora, sha1 de cada ``fetch_*.jpg`` e de cada vista
JSON do projeto (``project.json``, ``board.json``, ``scans/``, ``sections/``, ``pairs.json``, ``photos/``) e
``consistency.evaluate``. Duas saídas comparam-se com ``--comparar a.json b.json``."""
import glob
import hashlib
import json
import os
import re
import shutil
import guarda  # noqa: E402 (tools/diagnostico/gui/guarda.py)
import sys


def _h(fp):
	with open(fp, "rb") as f:
		return hashlib.sha1(f.read()).hexdigest()


def snapshot(pr, consistency, render, r):
	fj = json.load(open(pr.p("fetch.json"), encoding="utf-8"))
	fj.pop("t", None)
	views = {}
	for pat in ("project.json", "board.json", "pairs.json", "scans/*.json", "sections/*.json", "photos/*.json"):
		for fp in sorted(glob.glob(pr.p(pat))):
			views[os.path.relpath(fp, pr.path).replace("\\", "/")] = _h(fp)
	pl = render.load_placements(pr).get("placements") or {}
	ev = consistency.evaluate(pr, dict(pl))
	return {"entries": r.get("entries"), "messages": r.get("messages"), "invariants": r.get("invariants"),
			"fetch_json": fj, "fetch_md": re.sub(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d", "<t>", open(pr.p("fetch.md"), encoding="utf-8").read()),
			"fetch_jpg": {os.path.basename(fp): _h(fp) for fp in sorted(glob.glob(pr.p("fetch_*.jpg")))},
			"views": views, "evaluate": ev}


def run(repo, base, work, out):
	sys.path.insert(0, repo)
	guarda.rmtree(work, ignore_errors=True)
	guarda.copytree(base, work)
	from src.state import Project
	from src.confirm import confirm
	from src import consistency, render
	pr = Project.open(work)
	steps = [("place", "P0096", (20, 60)), ("unplace", "P0096", None), ("place", "P0096", (5, 33)),
			 ("unplace", "P0096", None), ("place", "P0097", (20, 60))]
	res = []
	for acao, pid, cell in steps:
		if acao == "place":
			r = confirm(pr, pid, cell=cell, origin="manual", use_image=True)
		else:
			r = confirm(pr, pid, unplace=True, desfaz=True, use_image=True)
		res.append({"passo": [acao, pid, cell], **snapshot(pr, consistency, render, r)})
	with open(out, "w", encoding="utf-8") as f:
		json.dump(res, f, ensure_ascii=False, default=str, indent=0)


def comparar(a, b):
	A = json.load(open(a, encoding="utf-8"))
	B = json.load(open(b, encoding="utf-8"))
	ok = True
	for x, y in zip(A, B):
		for k in x:
			if json.dumps(x[k], sort_keys=True) != json.dumps(y.get(k), sort_keys=True):
				ok = False
				print(f"DIFERENTE passo {x['passo']}: {k}")
	print("IGUAIS" if ok and len(A) == len(B) else "DIFERENTES", len(A), "passos")
	return 0 if ok else 1


if __name__ == "__main__":
	if sys.argv[1] == "--comparar":
		sys.exit(comparar(sys.argv[2], sys.argv[3]))
	run(*sys.argv[1:5])
