"""Conjunto de referência («golden», D1 = A de 2026-11-26): manifesto de hashes sobre os ficheiros já no git.

``tests/golden/manifesto.json``:

* ``pecas``: as peças do golden, ``{pid: {scan_id, scan, celula, papeis}}``, com ``papeis`` ⊆ {``borda``,
  ``quadrado``, ``manual``}: as colocadas em células de borda (célula física confirmada, 218/218 em 2026-11-25), as dos
  quadrados 2×2 confirmados fisicamente em 2026-11-11 (grupos 1-10 de ``quadrados_17.json``) e as que têm um contorno
  manual ativo (verdade da silhueta, D5 de 2026-11-25);
* ``scans``: sha256 de cada ficheiro de scan dessas peças (``images/pieces/...``, rastreados no git);
* ``quadrados``: sha256 de ``quadrados_17.json`` e os grupos que entram;
* ``overrides``: sha256 de cada linha de ``overrides.jsonl`` (só acrescentar: as primeiras N têm de ficar iguais
  byte a byte; uma linha nova não falha, é contada).

O manifesto só muda com ``python -m tools.verify --refresh-golden --porque "..."``, que escreve uma entrada em
``docs/decisoes.md``. Os contornos derivados (``pieces/*.npz``) NÃO entram: saem do programa, não são verdade; o que
deles se mede fica na baseline (:mod:`tools.verify.metricas`)."""
import datetime
import hashlib
import json
import os

__all__ = ["MANIFESTO", "QUADRADOS", "GRUPOS_QUADRADOS", "sha256_ficheiro", "linhas_sha256", "construir",
		   "verificar", "escrever", "registar_decisao", "ler", "diferenca"]

from tools.verify.ambiente import REPO

MANIFESTO = os.path.join(REPO, "tests", "golden", "manifesto.json")
QUADRADOS = "docs/diagnostico/grupos_soltos/quadrados_17.json"
GRUPOS_QUADRADOS = list(range(1, 11))     # os 10 quadrados testados fisicamente em 2026-11-11 (decisoes.md)
DECISOES = os.path.join(REPO, "docs", "decisoes.md")


def sha256_ficheiro(fp: str) -> str:
	h = hashlib.sha256()
	with open(fp, "rb") as f:
		for b in iter(lambda: f.read(1 << 20), b""):
			h.update(b)
	return h.hexdigest()


def linhas_sha256(fp: str) -> list:
	"""sha256 de cada linha (sem o fim de linha) de um ficheiro só-acrescentar; ``[]`` se não existe."""
	if not os.path.exists(fp):
		return []
	with open(fp, "rb") as f:
		return [hashlib.sha256(l).hexdigest() for l in f.read().splitlines()]


def _rel(fp: str) -> str:
	return os.path.relpath(os.path.abspath(fp), REPO).replace(os.sep, "/")


def construir(pr) -> dict:
	"""Manifesto a partir de um :class:`src.state.Project` (aberto sobre uma CÓPIA do projeto)."""
	from src.overrides import latest_overrides, overrides_path
	prof = pr.profile
	pecas = {}

	def add(pid, papel):
		p = pr.piece(pid)
		e = pecas.setdefault(pid, {"scan_id": p.scan_id, "celula": None, "papeis": []})
		if papel not in e["papeis"]:
			e["papeis"].append(papel)

	for pid, p in sorted(pr.pieces.items()):
		if p.estado == "colocada" and p.celula is not None and prof.is_border(*p.celula):
			add(pid, "borda")
			pecas[pid]["celula"] = [int(p.celula[0]), int(p.celula[1])]
	with open(os.path.join(REPO, QUADRADOS), encoding="utf-8") as f:
		q = json.load(f)
	for g in q["grupos"]:
		if g["n"] in GRUPOS_QUADRADOS:
			for e in g["pecas"]:
				add(e["peca"], "quadrado")
	for pid in sorted(latest_overrides(pr)):
		add(pid, "manual")
	scans = {}
	for pid, e in pecas.items():
		s = pr.model.scans[e["scan_id"]]
		e["scan"] = s["file"]
		if s["file"] not in scans:
			scans[s["file"]] = sha256_ficheiro(os.path.join(REPO, s["file"]))
	ovp = overrides_path(pr)
	return {
		"versao": 1,
		"projeto_id": prof.id,
		"gerado_em": datetime.datetime.now().isoformat(timespec="seconds"),
		"contagens": {"pecas": len(pecas), "borda": sum("borda" in e["papeis"] for e in pecas.values()),
					  "quadrado": sum("quadrado" in e["papeis"] for e in pecas.values()),
					  "manual": sum("manual" in e["papeis"] for e in pecas.values()), "scans": len(scans)},
		"pecas": dict(sorted(pecas.items())),
		"scans": dict(sorted(scans.items())),
		"quadrados": {"ficheiro": QUADRADOS, "sha256": sha256_ficheiro(os.path.join(REPO, QUADRADOS)),
					  "grupos": GRUPOS_QUADRADOS},
		"overrides": {"ficheiro": os.path.basename(ovp), "linhas": linhas_sha256(ovp)},
	}


def ler(fp: str = MANIFESTO):
	if not os.path.exists(fp):
		return None
	with open(fp, encoding="utf-8") as f:
		return json.load(f)


def verificar(man, project_dir: str) -> dict:
	"""Hashes atuais contra o manifesto (só leitura; o projeto pode ser o real). ``{ok, diferencas, linhas_novas}``."""
	if man is None:
		return {"ok": False, "diferencas": ["sem manifesto: python -m tools.verify --refresh-golden --porque \"...\""],
				"linhas_novas": 0}
	dif = []
	for rel, h in man["scans"].items():
		fp = os.path.join(REPO, rel)
		if not os.path.exists(fp):
			dif.append(f"scan em falta: {rel}")
		elif sha256_ficheiro(fp) != h:
			dif.append(f"scan alterado: {rel}")
	qf = os.path.join(REPO, man["quadrados"]["ficheiro"])
	if not os.path.exists(qf) or sha256_ficheiro(qf) != man["quadrados"]["sha256"]:
		dif.append(f"quadrados alterado ou em falta: {man['quadrados']['ficheiro']}")
	atuais = linhas_sha256(os.path.join(project_dir, man["overrides"]["ficheiro"]))
	ant = man["overrides"]["linhas"]
	if len(atuais) < len(ant):
		dif.append(f"overrides.jsonl perdeu linhas: {len(atuais)} < {len(ant)}")
	for i, (a, b) in enumerate(zip(ant, atuais)):
		if a != b:
			dif.append(f"overrides.jsonl linha {i + 1} alterada (só acrescentar)")
	return {"ok": not dif, "diferencas": dif, "linhas_novas": max(0, len(atuais) - len(ant))}


def escrever(man: dict, fp: str = MANIFESTO) -> None:
	os.makedirs(os.path.dirname(fp), exist_ok=True)
	with open(fp, "w", encoding="utf-8", newline="\n") as f:
		json.dump(man, f, ensure_ascii=False, indent=1)
		f.write("\n")


def registar_decisao(titulo: str, porque: str, linhas: list) -> None:
	"""Acrescenta ``## <data> — <titulo>`` a ``docs/decisoes.md`` (só acrescentar)."""
	hoje = datetime.date.today().isoformat()
	txt = [f"\n## {hoje} — {titulo}\n", f"- **Porquê (`--porque`):** {porque}"] + [f"- {l}" for l in linhas]
	with open(DECISOES, "a", encoding="utf-8", newline="\n") as f:
		f.write("\n".join(txt) + "\n")


def diferenca(ant, novo) -> list:
	"""Resumo das diferenças entre dois manifestos (para a entrada em ``decisoes.md``)."""
	if ant is None:
		return ["manifesto novo"]
	out = []
	pa, pn = set(ant["pecas"]), set(novo["pecas"])
	if pn - pa:
		out.append(f"peças novas: {sorted(pn - pa)}")
	if pa - pn:
		out.append(f"peças que saíram: {sorted(pa - pn)}")
	mud = sorted(p for p in pa & pn if ant["pecas"][p] != novo["pecas"][p])
	if mud:
		out.append(f"peças com célula/scan/papéis mudados: {mud}")
	sm = sorted(k for k in set(ant["scans"]) | set(novo["scans"]) if ant["scans"].get(k) != novo["scans"].get(k))
	if sm:
		out.append(f"scans mudados: {sm}")
	if ant["quadrados"] != novo["quadrados"]:
		out.append("quadrados mudados")
	la, ln = ant["overrides"]["linhas"], novo["overrides"]["linhas"]
	if la != ln[:len(la)]:
		out.append("overrides.jsonl: linhas antigas diferentes")
	elif len(ln) > len(la):
		out.append(f"overrides.jsonl: +{len(ln) - len(la)} linhas")
	return out or ["sem diferenças de conteúdo (só a data)"]
