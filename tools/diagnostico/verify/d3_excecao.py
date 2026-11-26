"""D3 = A (2026-11-26): ``consistency.evaluate`` e a simetria 4.2 antes e depois de alargar ``symmetry.excecoes`` c32|c33
às filas [1, 5] e [43, 47], numa CÓPIA de ``projects/alpes`` (``tools.verify.ambiente.copiar_projeto``, guarda).

Só lê o projeto real; o ``puzzle.json`` alterado é o da cópia. Uso (raiz do repositório, com o .venv):
	.venv/Scripts/python.exe tools/diagnostico/verify/d3_excecao.py"""
import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, REPO)
from tools.verify import ambiente as AMB  # noqa: E402
from tools.verify import invariantes as INV  # noqa: E402


def avaliar(copia):
	from src import consistency as CS, render
	from src.state import Project
	pr = Project.open(copia)
	pl = dict(render.load_placements(pr).get("placements") or {})
	ev = CS.evaluate(pr, pl, incluir_falsos=True)
	return ev, INV.simetria(pr, ())


def main():
	raiz, copia = AMB.copiar_projeto(os.path.join(REPO, "projects", "alpes"))
	try:
		from src.state import Project
		INV.arranque(Project.open(copia))
		a, sa = avaliar(copia)
		fp = os.path.join(copia, "puzzle.json")
		with open(fp, encoding="utf-8") as f:
			d = json.load(f)
		d["symmetry"]["excecoes"][0]["rows"] = [[1, 5], [43, 47]]
		with open(fp, "w", encoding="utf-8") as f:
			json.dump(d, f, ensure_ascii=False, indent=1)
		b, sb = avaliar(copia)
		ia = {(it["piece"], it["grau"]): it for it in a["items"]}
		ib = {(it["piece"], it["grau"]): it for it in b["items"]}
		print(f"itens: antes {len(ia)} (falsos alarmes {a['summary']['n_falsos_alarmes']}), depois {len(ib)} "
			  f"(falsos alarmes {b['summary']['n_falsos_alarmes']}); saem {sorted(set(ia) - set(ib))}, "
			  f"entram {sorted(set(ib) - set(ia))}; resumo igual {a['summary'] == b['summary']}")
		for k in sorted(ia):
			dif = {f: (ia[k].get(f), ib[k].get(f)) for f in set(ia[k]) | set(ib[k]) if ia[k].get(f) != ib[k].get(f)}
			if dif:
				print(f"  {k[0]} {ia[k]['cell']}: {sorted(dif)}")
		print(f"simetria 4.2 sem lista «por rever»: antes {sa['n']} violações {[(v['a'], v['b']) for v in sa['violacoes']]}, "
			  f"{len(sa['na_excecao'])} na exceção; depois {sb['n']} violações, {len(sb['na_excecao'])} na exceção")
	finally:
		AMB.apagar_copia(raiz)


if __name__ == "__main__":
	main()
