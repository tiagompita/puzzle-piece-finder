"""Onde vão os 30–40 s do 1.º ranking dos buracos depois de arrancar o servidor (DETALHE.md §7, só diagnóstico).

	.venv/Scripts/python.exe tools/diagnostico/gui/buracos_frio.py --project <cópia> [--out <json>]

Num processo novo (como o arranque do servidor): ``Gui(prepare=False)`` e ``Gui._compute_holes`` com as fases de
``src.fit.rank_all`` cronometradas por monkeypatch (soma do tempo dentro de cada função), duas vezes:
1. a frio (processo novo; as tiras vêm de ``render/fit/strips.npz``);
2. a seguir, com o mesmo ``Gui`` mas a cache do ranking apagada (``_holes = None``), como depois de uma escrita.
Nada é escrito no projeto, exceto ``render/fit/strips.npz`` se faltar alguma tira.
"""
import argparse
import collections
import functools
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)
os.chdir(ROOT)


def main(argv=None) -> int:
	ap = argparse.ArgumentParser()
	ap.add_argument("--project", required=True)
	ap.add_argument("--out")
	a = ap.parse_args(argv)
	if os.path.normcase(os.path.abspath(os.path.join(ROOT, "projects"))) in os.path.normcase(os.path.abspath(a.project)):
		raise SystemExit("--project tem de ser uma cópia fora de projects/")
	t_imp = time.perf_counter()
	from src import fit as F, render, server as S, state
	imp_s = time.perf_counter() - t_imp
	acc = collections.defaultdict(float)
	cnt = collections.Counter()

	def wrap(mod, name, label):
		f = getattr(mod, name)

		@functools.wraps(f)
		def g(*args, **kw):
			t0 = time.perf_counter()
			try:
				return f(*args, **kw)
			finally:
				acc[label] += time.perf_counter() - t0        # inclusivo: uma fase pode conter outra
				cnt[label] += 1
		setattr(mod, name, g)

	# fases de rank_all (as chamadas internas de fit resolvem o nome no módulo, por isso o monkeypatch apanha-as)
	wrap(F, "board_sigma", "board_sigma (inclui poses + formas das colocadas)")
	wrap(F, "hole_queries", "hole_queries (buracos, lados das vizinhas, tiras)")
	wrap(F, "pool_items", "pool_items (soltas: formas, lados erodidos, tiras)")
	wrap(F, "pool_arrays", "pool_arrays")
	wrap(F, "rank_hole", "rank_hole (custo de cada buraco contra o pool)")
	wrap(F, "assign", "assign (afetação conjunta)")
	wrap(F, "piece_strips", "piece_strips (tira calculada, não em cache)")
	wrap(F, "eroded_sides", "eroded_sides")
	wrap(F, "board_dirs", "board_dirs")
	wrap(render, "initial_theta", "render.initial_theta")
	wrap(state.Project, "shape", "Project.shape (npz → Shape)")
	out = {"importar_s": round(imp_s, 2)}
	t0 = time.perf_counter()
	gui = S.Gui(a.project, prepare=False, log=None)
	out["gui_s"] = round(time.perf_counter() - t0, 2)
	for rodada in ("frio", "depois_de_escrita"):
		acc.clear(); cnt.clear()
		if rodada != "frio":
			gui._holes = None
		key = (gui.version(), id(gui.pr))
		t0 = time.perf_counter()
		r = gui._compute_holes(key)
		tot = time.perf_counter() - t0
		out[rodada] = {"total_s": round(tot, 2), "resumo": r.get("resumo"),
					   "fases_s": {k: round(v, 2) for k, v in sorted(acc.items(), key=lambda kv: -kv[1])},
					   "chamadas": dict(cnt)}
		if rodada == "frio":
			fc = gui._fit_cache()
			out["cache"] = {"tiras_em_disco": fc.n_loaded, "tiras": len(fc.strips), "lados_erodidos": len(fc.sides),
							"formas": len(fc.shapes)}
	s = json.dumps(out, ensure_ascii=False, indent=1)
	if a.out:
		with open(a.out, "w", encoding="utf-8") as fh:
			fh.write(s)
	print(json.dumps(out, indent=1))                       # ASCII: a consola do Windows pode ser cp1252
	return 0


if __name__ == "__main__":
	sys.exit(main())
