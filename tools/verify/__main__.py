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
from tools.verify import invariantes as INV
from tools.verify import metricas as MT

__all__ = ["CODIGOS", "BASELINE", "LIMIARES", "codigo_saida", "main"]

BASELINE = os.path.join(AMB.REPO, "tests", "golden", "baseline.json")
LIMIARES = os.path.join(AMB.REPO, "tests", "golden", "limiares.json")

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
	if res.get("regressoes") is not None:
		L += ["## Regressões contra a baseline", ""] + ([f"- {t}" for t in res["regressoes"]] or ["Nenhuma."]) + [""]
	if res.get("regras"):
		L += ["## Regras absolutas (0 violações exigidas)", "", "| regra | violações |", "|---|---|"]
		L += [f"| {k} | {r['n']} |" for k, r in res["regras"].items()] + [""]
	if res.get("arranque"):
		a = res["arranque"]
		L += ["## Arranque simulado na cópia (`render.rebuild_stale`)", "",
			  f"- desatualizadas no projeto real: {a['desatualizados']} ({', '.join(a['pecas']) or 'nenhuma'}); "
			  f"eventos na cópia: {len(a['eventos'])}; restantes: {a['restantes']}", ""]
		L += [f"  - {pid}: {', '.join(why)}" for pid, why in a["motivos"].items()] + ([""] if a["motivos"] else [])
	for k in ("ambiente", "golden", "vigilancia_inicio", "vigilancia_fim"):
		L += [f"## {k}", "", "```json", json.dumps(res.get(k), ensure_ascii=False, indent=1), "```", ""]
	return "\n".join(L)


def _ler(fp):
	if not os.path.exists(fp):
		return None
	with open(fp, encoding="utf-8") as f:
		return json.load(f)


def _escrever(fp, obj) -> None:
	os.makedirs(os.path.dirname(fp), exist_ok=True)
	with open(fp, "w", encoding="utf-8", newline="\n") as f:
		json.dump(obj, f, ensure_ascii=False, indent=1)
		f.write("\n")


def _congelar(atual: dict, man_sha: str, res: dict, porque) -> None:
	"""Grava a baseline (e os limiares fixos, só se ainda não existirem: nunca a partir de um resultado)."""
	ja = os.path.exists(BASELINE)
	_escrever(BASELINE, {"versao": 1, "congelada_em": res["quando"], "head": res["git_inicio"]["head"],
						 "manifesto_sha256": man_sha, "metricas": atual})
	if not os.path.exists(LIMIARES):
		_escrever(LIMIARES, MT.LIMIARES_INICIAIS)
	if ja:
		GD.registar_decisao("baseline do golden congelada de novo (`tools.verify --congelar-baseline`)", porque.strip(),
							[f"HEAD `{res['git_inicio']['head'][:7]}`; limiares inalterados"])
	res["baseline_congelada"] = BASELINE
	print(f"baseline congelada: {BASELINE}")


def main(argv=None) -> int:
	ap = argparse.ArgumentParser(prog="python -m tools.verify", description=__doc__.splitlines()[0])
	ap.add_argument("--project", default=os.path.join("projects", "alpes"))
	ap.add_argument("--out", default=None, help="pasta das saídas (métricas, comparação)")
	ap.add_argument("--refresh-golden", action="store_true",
					help="reescreve tests/golden/manifesto.json a partir de uma cópia do projeto (exige --porque)")
	ap.add_argument("--congelar-baseline", action="store_true",
					help="grava tests/golden/baseline.json (e limiares.json se não existir, com os valores fixos do "
						 "código); só com tudo o resto verde; se a baseline já existir, exige --porque")
	ap.add_argument("--porque", default=None, help="motivo, escrito em docs/decisoes.md")
	args = ap.parse_args(argv)
	if args.refresh_golden and not (args.porque or "").strip():
		ap.error("--refresh-golden exige --porque \"...\" (fica em docs/decisoes.md)")
	if args.congelar_baseline and os.path.exists(BASELINE) and not (args.porque or "").strip():
		ap.error("a baseline já existe: voltar a congelá-la exige --porque \"...\" (fica em docs/decisoes.md)")
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
		res["arranque"] = arr = INV.arranque(pr)          # o que o arranque do servidor faria (só na cópia)
		if arr["erros"] or arr["restantes"]:
			falhas.append(("erro", f"arranque simulado na cópia: {arr['restantes']} peças ainda desatualizadas, "
								   f"erros {arr['erros'][:3]}"))
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
		# regras absolutas (projeto vivo, sem baseline)
		res["regras"] = regras = INV.todas(pr)
		for k, r in regras.items():
			if r["n"]:
				falhas.append(("regras", f"{k}: {r['n']} violações, p. ex. {json.dumps(r['violacoes'][:3], ensure_ascii=False)}"))
		# métricas das peças do golden contra a baseline
		if man is not None:
			res["metricas_golden"] = atual = MT.medir(pr, man)
			man_sha = GD.sha256_ficheiro(GD.MANIFESTO)
			if args.congelar_baseline:
				if falhas:
					falhas.append(("baseline", "baseline NÃO congelada: há falhas antes da comparação"))
				else:
					_congelar(atual, man_sha, res, args.porque)
			else:
				base = _ler(BASELINE)
				lim = _ler(LIMIARES)
				if base is None or lim is None:
					falhas.append(("baseline", "sem tests/golden/baseline.json ou limiares.json: --congelar-baseline"))
				elif base.get("manifesto_sha256") != man_sha:
					falhas.append(("baseline", "a baseline foi congelada com outro manifesto: voltar a congelar (--porque)"))
				else:
					res["regressoes"] = reg = MT.comparar(atual, base["metricas"], lim, man)
					falhas += [("baseline", t) for t in reg]
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
	escritos = ()
	if args.refresh_golden:
		escritos += ("tests/golden/manifesto.json", "docs/decisoes.md")
	if args.congelar_baseline:
		escritos += ("tests/golden/baseline.json", "tests/golden/limiares.json", "docs/decisoes.md")
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
