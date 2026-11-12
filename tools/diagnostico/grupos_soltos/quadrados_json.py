"""Os 17 quadrados 2×2 entre soltas (2026-11-10, testados pelo Tiago: 17/17) num JSON do repositório.

Fonte: ``loose_res.pkl`` escrito por ``loose.py`` em 2026-11-10 (scratchpad dessa sessão, fora do git): para cada
quadrado, ``m`` (margem, a mais fraca das 4 ligações), ``lay`` (peça -> ((linha, coluna) local com a 1.ª peça em
(0, 0), N = cima; rot)) e ``lk`` (as 4 ligações: peça a, lado i, peça b, lado j, margem). ``rot``: o lado ``k`` da
peça (índice em ``Project.shape(pid).sides``) olha a direção ``DIRS[(k - rot) % 4]`` (``loose.py``, l. 74).

A ordem (#1..#17) é a de ``QUADRADOS.md``: margem decrescente (``sorted(..., key=-m)``, como ``loose.py`` e
``quadrados_11_17.py``). O script confere as peças e as margens com as tabelas de ``QUADRADOS.md``, as ligações com
o ``lay``, e as peças com uma CÓPIA do projeto (só leitura): existem, têm 4 lados, saco e nº iguais às tabelas.

uso: python quadrados_json.py <loose_res.pkl> <projeto-copia> <saida.json>
"""
import collections
import datetime
import io
import json
import os
import pickle
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from src.fit import DIRS, STEP  # noqa: E402
from src.state import Project  # noqa: E402

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
MD = os.path.join(REPO, "docs", "diagnostico", "grupos_soltos", "QUADRADOS.md")


def md_tables():
	"""{n: (margem, [(lote, n_no_lote, pid), ...])} das duas tabelas de QUADRADOS.md."""
	out = {}
	for line in open(MD, encoding="utf-8"):
		m = re.match(r"^\| (\d+) \| ([\d,]+)[^|]*\| (.+?) \|", line)
		if not m:
			continue
		pcs = re.findall(r"Saco (\d+) · nº (\d+) \((P\d{4})\)", m.group(3))
		out[int(m.group(1))] = (float(m.group(2).replace(",", ".")), [(int(a), int(b), c) for a, b, c in pcs])
	return out


def main(pkl, proj, dst):
	R = pickle.load(open(pkl, "rb"))
	sq = sorted(R["sqs"].values(), key=lambda s: -s["m"])
	assert len(sq) == 17, len(sq)
	tab = md_tables()
	assert sorted(tab) == list(range(1, 18)), sorted(tab)
	pr = Project.open(proj)
	grupos = []
	for n, s in enumerate(sq, 1):
		lay = s["lay"]
		m_md, pcs_md = tab[n]
		assert round(s["m"], 3) == m_md, (n, s["m"], m_md)
		assert sorted(p for _, _, p in pcs_md) == sorted(lay), (n, sorted(lay), pcs_md)
		r0 = min(rc[0] for rc, _ in lay.values())
		c0 = min(rc[1] for rc, _ in lay.values())
		pecas = []
		for _, _, pid in pcs_md:                         # a ordem da tabela de QUADRADOS.md
			(r, c), rot = lay[pid]
			p = pr.piece(pid)
			sh = pr.shape(pid)
			assert len(sh.sides) == 4, (pid, len(sh.sides))
			lote_md, n_md = next((a, b) for a, b, q in pcs_md if q == pid)
			assert (p.lote, p.n_no_lote) == (lote_md, n_md), (pid, p.lote, p.n_no_lote, lote_md, n_md)
			pecas.append({"peca": pid, "saco": p.lote, "n_no_saco": p.n_no_lote, "scan_id": p.scan_id,
						  "linha": r - r0, "coluna": c - c0, "rot": rot,
						  "lado_por_direcao": {DIRS[(k - rot) % 4]: k for k in range(4)}})
		pos = {(q["linha"], q["coluna"]) for q in pecas}
		assert pos == {(0, 0), (0, 1), (1, 0), (1, 1)}, (n, pos)
		ligacoes = []
		for a, i, b, j, mg in s["lk"]:
			(ra, ca), rota = lay[a]
			(rb, cb), rotb = lay[b]
			da, db = DIRS[(i - rota) % 4], DIRS[(j - rotb) % 4]
			# a ligação tem de juntar as duas células pelo lado certo: b está em a + STEP[da] e os lados são opostos
			assert (rb - ra, cb - ca) == STEP[da], (n, a, b, da)
			assert DIRS.index(db) == (DIRS.index(da) + 2) % 4, (n, a, b, da, db)
			ligacoes.append({"a": a, "lado_a": i, "direcao_a": da, "b": b, "lado_b": j, "direcao_b": db,
							 "margem": round(float(mg), 4)})
		grupos.append({"n": n, "margem": round(float(s["m"]), 4),
					   "zona_provavel": collections.Counter(R["zone"][p] for p in lay).most_common(1)[0][0],
					   "pecas": pecas, "ligacoes": ligacoes,
					   "teste_fisico": {"resultado": "encaixa", "data": "2026-11-11", "fonte": "Tiago"}})
	# ligações entre grupos: peças em comum e ligações (pares de lados) em comum
	entre = []
	for g in grupos:
		for h in grupos:
			if h["n"] <= g["n"]:
				continue
			comuns = sorted({q["peca"] for q in g["pecas"]} & {q["peca"] for q in h["pecas"]})
			if not comuns:
				continue

			def keys(x):
				return {frozenset(((l["a"], l["lado_a"]), (l["b"], l["lado_b"]))) for l in x["ligacoes"]}
			lig = [sorted(f"{p}:{k}" for p, k in fs) for fs in keys(g) & keys(h)]
			lados = {}
			for p in comuns:
				lg = sorted({l["lado_a"] for l in g["ligacoes"] if l["a"] == p} | {l["lado_b"] for l in g["ligacoes"] if l["b"] == p})
				lh = sorted({l["lado_a"] for l in h["ligacoes"] if l["a"] == p} | {l["lado_b"] for l in h["ligacoes"] if l["b"] == p})
				lados[p] = {f"grupo_{g['n']}": lg, f"grupo_{h['n']}": lh}
			entre.append({"grupos": [g["n"], h["n"]], "pecas_comuns": comuns, "ligacoes_comuns": sorted(lig),
						  "lados_usados": lados})
	ids = {q["peca"] for g in grupos for q in g["pecas"]}
	reseg = set()
	for line in open(os.path.join(proj, "log.jsonl"), encoding="utf-8"):
		ev = json.loads(line)
		if ev.get("action") == "piece_resegmented" and str(ev.get("t", "")) >= "2026-11-10":
			reseg |= ids & set(re.findall(r"P\d{4}", json.dumps(ev)))
	out = {
		"pecas_resegmentadas_desde_2026_11_10": sorted(reseg),
		"descricao": "Os 17 quadrados 2×2 propostos entre peças soltas (ligações melhor-mútuas, 2026-11-10), "
					 "todos testados fisicamente pelo Tiago (17/17 encaixam, 2026-11-11). NÃO estão registados no projeto.",
		"proveniencia": {
			"medicao": "tools/diagnostico/grupos_soltos/loose.py, 2026-11-10, sobre uma cópia de projects/alpes",
			"ficheiro_original": "loose_res.pkl (scratchpad da sessão de 2026-11-10, fora do git)",
			"gerado_por": "tools/diagnostico/grupos_soltos/quadrados_json.py",
			"gerado_em": datetime.date.today().isoformat(),
			"conferido_com": ["docs/diagnostico/grupos_soltos/QUADRADOS.md (peças, saco, nº, margem)",
							  "uma cópia de projects/alpes (ids, 4 lados, saco e nº)"],
			"teste_fisico": "docs/decisoes.md 2026-11-11 e 2026-11-12; ESPEC §8.6",
		},
		"convencoes": {
			"linha_coluna": "posição local no grupo, (0, 0) = canto de cima à esquerda, linha cresce para baixo",
			"rot": "o lado k da peça olha a direção DIRS[(k - rot) % 4], DIRS = N, E, S, W (loose.py)",
			"lado": "índice do lado em Project.shape(pid).sides no índice de 2026-11-10; uma re-segmentação "
					"posterior pode renumerar os lados [NT]",
			"lado_por_direcao": "o mesmo que rot, explícito: direção no grupo -> índice do lado da peça",
			"margem": "custo da 2.ª / custo da 1.ª (fit.side_costs); a do grupo é a mais fraca das 4 ligações",
		},
		"grupos": grupos,
		"ligacoes_entre_grupos": entre,
	}
	with open(dst, "w", encoding="utf-8", newline="\n") as f:
		json.dump(out, f, ensure_ascii=False, indent=1)
		f.write("\n")
	print(f"{len(grupos)} grupos, {len(entre)} ligações entre grupos -> {dst}")
	for e in entre:
		print("  ", e["grupos"], e["pecas_comuns"], "ligações comuns:", e["ligacoes_comuns"])


if __name__ == "__main__":
	main(*sys.argv[1:4])
