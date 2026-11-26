"""``python -m tools.verify [--project projects/alpes] [--out DIR]``: verificação determinística (ver o pacote).

Códigos de saída (o primeiro desta ordem que falhar): 2 ambiente (``.venv``, OpenCV, ``core.hooksPath``);
3 golden alterado ou sem manifesto; 6 vigilância ou árvore de trabalho mudou durante a corrida; 4 regra absoluta
violada; 5 métrica de uma peça do golden pior do que a baseline (ou sem baseline); 1 erro inesperado; 0 tudo certo.

Saídas: ``<out>/metricas.json`` e ``<out>/comparacao.md`` (por omissão ``$PPF_SCRATCH/verify/<data>`` ou
``<temp>/ppf_verify_out/<data>``). Nunca escreve no projeto: as regras correm sobre uma cópia temporária."""
import argparse
import datetime
import json
import os
import sys
import tempfile
import time
import traceback

from tools.verify import ambiente as AMB
from tools.verify import golden as GD

__all__ = ["CODIGOS", "main"]

CODIGOS = {"ambiente": 2, "golden": 3, "vigilancia": 6, "arvore": 6, "regras": 4, "baseline": 5, "erro": 1}
_ORDEM = ("ambiente", "golden", "vigilancia", "arvore", "regras", "baseline", "erro")


def _out_dir(arg) -> str:
	if arg:
		d = arg
	else:
		base = os.environ.get("PPF_SCRATCH") or os.path.join(tempfile.gettempdir(), "ppf_verify_out")
		d = os.path.join(base, "verify", datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
	os.makedirs(d, exist_ok=True)
	return d


def codigo_saida(falhas: list) -> int:
	"""Código do primeiro grupo de :data:`_ORDEM` com falhas; 0 sem falhas."""
	grupos = {g for g, _ in falhas}
	for g in _ORDEM:
		if g in grupos:
			return CODIGOS[g]
	return 0


def _md(res: dict) -> str:
	L = [f"# tools.verify — {res['quando']}", "", f"- projeto: `{res['projeto']}`",
		 f"- HEAD: `{res['git_inicio']['head']}`", f"- código de saída: **{res['codigo_saida']}**", ""]
	if res["falhas"]:
		L += ["## Falhas", ""] + [f"- **{g}**: {t}" for g, t in res["falhas"]] + [""]
	else:
		L += ["Sem falhas.", ""]
	for k in ("ambiente", "golden", "vigilancia_inicio", "vigilancia_fim"):
		L += [f"## {k}", "", "```json", json.dumps(res.get(k), ensure_ascii=False, indent=1), "```", ""]
	return "\n".join(L)


def main(argv=None) -> int:
	ap = argparse.ArgumentParser(prog="python -m tools.verify", description=__doc__.splitlines()[0])
	ap.add_argument("--project", default=os.path.join("projects", "alpes"))
	ap.add_argument("--out", default=None, help="pasta das saídas (métricas, comparação)")
	ap.add_argument("--refresh-golden", action="store_true",
					help="reescreve tests/golden/manifesto.json a partir de uma cópia do projeto (exige --porque)")
	ap.add_argument("--porque", default=None, help="motivo, escrito em docs/decisoes.md")
	args = ap.parse_args(argv)
	if args.refresh_golden and not (args.porque or "").strip():
		ap.error("--refresh-golden exige --porque \"...\" (fica em docs/decisoes.md)")
	t0 = time.time()
	project = os.path.abspath(os.path.join(AMB.REPO, args.project) if not os.path.isabs(args.project) else args.project)
	out = _out_dir(args.out)
	falhas = []
	res = {"quando": datetime.datetime.now().isoformat(timespec="seconds"), "projeto": project, "saidas": out}

	res["ambiente"] = amb = AMB.ambiente()
	if not amb["python"]["ok"]:
		falhas.append(("ambiente", f"Python fora do .venv: {amb['python']['executavel']}"))
	if not amb["opencv"]["ok"]:
		falhas.append(("ambiente", f"OpenCV {amb['opencv']['versao']} != {amb['opencv']['esperado']} (requirements.txt)"))
	if not amb["hooks"]["ok"]:
		falhas.append(("ambiente", f"core.hooksPath = {amb['hooks']['valor']!r}, esperado {AMB.HOOKS_PATH!r}: "
								   f"{amb['hooks']['ativar']}"))
	res["git_inicio"] = AMB.git_estado()
	res["vigilancia_inicio"] = v0 = AMB.vigilancia(project)
	if not v0["ok"]:
		falhas.append(("vigilancia", f"início: pieces {v0['pieces']}, overlays {v0['overlays']}, scans {v0['scans']}"))

	raiz = None
	try:
		raiz, copia = AMB.copiar_projeto(project)
		res["copia"] = copia
		from src.state import Project
		pr = Project.open(copia)
		if args.refresh_golden:
			ant = GD.ler()
			novo = GD.construir(pr)
			GD.escrever(novo)
			dif = GD.diferenca(ant, novo)
			GD.registar_decisao("golden atualizado (`tools.verify --refresh-golden`)", args.porque.strip(),
								[f"HEAD `{res['git_inicio']['head'][:7]}`; contagens {json.dumps(novo['contagens'])}",
								 f"overrides.jsonl: {len(novo['overrides']['linhas'])} linhas"] + dif)
			res["refresh_golden"] = {"contagens": novo["contagens"], "diferencas": dif}
			print(f"manifesto escrito: {GD.MANIFESTO} ({novo['contagens']})")
		man = GD.ler()
		res["golden"] = g = GD.verificar(man, project)
		if not g["ok"]:
			falhas += [("golden", d) for d in g["diferencas"]]
	except Exception:  # noqa: BLE001 - o relatório tem de sair mesmo com um erro a meio
		falhas.append(("erro", traceback.format_exc(limit=5)))
	finally:
		if raiz:
			AMB.apagar_copia(raiz)
			res["copia_apagada"] = not os.path.exists(raiz)

	res["git_fim"] = AMB.git_estado()
	res["vigilancia_fim"] = v1 = AMB.vigilancia(project)
	if not v1["ok"]:
		falhas.append(("vigilancia", f"fim: pieces {v1['pieces']}, overlays {v1['overlays']}, scans {v1['scans']}"))
	escritos = ("tests/golden/manifesto.json", "docs/decisoes.md") if args.refresh_golden else ()
	def _sem_escritos(g):
		return {"head": g["head"], "status": [l for l in g["status"] if not (escritos and l[3:].strip('"').endswith(escritos))]}
	if _sem_escritos(res["git_fim"]) != _sem_escritos(res["git_inicio"]):
		falhas.append(("arvore", "HEAD ou git status mudou durante a corrida (outro agente/processo a escrever?)"))
	res["falhas"] = falhas
	res["codigo_saida"] = codigo_saida(falhas)
	res["segundos"] = round(time.time() - t0, 1)
	with open(os.path.join(out, "metricas.json"), "w", encoding="utf-8") as f:
		json.dump(res, f, ensure_ascii=False, indent=1, default=str)
	with open(os.path.join(out, "comparacao.md"), "w", encoding="utf-8") as f:
		f.write(_md(res))
	print(f"tools.verify: código {res['codigo_saida']} em {res['segundos']} s; saídas em {out}")
	for g, t in falhas:
		print(f"  FALHA {g}: {t}")
	return res["codigo_saida"]


if __name__ == "__main__":
	sys.exit(main())
