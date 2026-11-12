"""Validação de ``docs/diagnostico/grupos_soltos/quadrados_17.json`` (os 17 quadrados 2×2 entre soltas, 17/17 encaixam).

Esquema e coerência interna (posições, rotações, ligações) e, se houver ``projects/alpes/log.jsonl``, que os ids
existem no projeto (só leitura do texto do log; nada é escrito)."""

import json
import os
import re

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = os.path.join(REPO, "docs", "diagnostico", "grupos_soltos", "quadrados_17.json")
LOG = os.path.join(REPO, "projects", "alpes", "log.jsonl")
DIRS = ("N", "E", "S", "W")
STEP = {"N": (-1, 0), "E": (0, 1), "S": (1, 0), "W": (0, -1)}


@pytest.fixture(scope="module")
def data():
	with open(JS, encoding="utf-8") as f:
		return json.load(f)


def test_schema_and_layout(data):
	assert {"descricao", "proveniencia", "convencoes", "grupos", "ligacoes_entre_grupos"} <= set(data)
	assert data["proveniencia"]["gerado_por"].endswith("quadrados_json.py")
	gs = data["grupos"]
	assert [g["n"] for g in gs] == list(range(1, 18))
	assert [g["margem"] for g in gs] == sorted((g["margem"] for g in gs), reverse=True)
	for g in gs:
		assert g["teste_fisico"]["resultado"] == "encaixa"
		assert len(g["pecas"]) == 4 and len(g["ligacoes"]) == 4
		pos = {}
		for q in g["pecas"]:
			assert re.fullmatch(r"P\d{4}", q["peca"])
			assert q["rot"] in (0, 1, 2, 3)
			assert q["lado_por_direcao"] == {DIRS[(k - q["rot"]) % 4]: k for k in range(4)}
			pos[q["peca"]] = (q["linha"], q["coluna"])
		assert sorted(pos.values()) == [(0, 0), (0, 1), (1, 0), (1, 1)]
		rot = {q["peca"]: q["rot"] for q in g["pecas"]}
		for l in g["ligacoes"]:
			assert l["direcao_a"] == DIRS[(l["lado_a"] - rot[l["a"]]) % 4]
			assert l["direcao_b"] == DIRS[(l["lado_b"] - rot[l["b"]]) % 4]
			(ra, ca), (rb, cb) = pos[l["a"]], pos[l["b"]]
			assert (rb - ra, cb - ca) == STEP[l["direcao_a"]]
			assert DIRS.index(l["direcao_b"]) == (DIRS.index(l["direcao_a"]) + 2) % 4
			assert l["margem"] >= g["margem"] - 1e-4
		# as 4 ligações cobrem as 4 adjacências do 2×2
		assert len({frozenset((l["a"], l["b"])) for l in g["ligacoes"]}) == 4


def test_links_between_groups(data):
	pairs = {tuple(e["grupos"]): e for e in data["ligacoes_entre_grupos"]}
	assert set(pairs) == {(1, 12), (7, 16), (8, 16), (8, 17), (16, 17)}
	assert pairs[(1, 12)]["pecas_comuns"] == ["P1128"]
	assert pairs[(7, 16)]["pecas_comuns"] == ["P1377"]
	assert pairs[(8, 16)]["pecas_comuns"] == ["P0161"]
	assert pairs[(8, 17)]["pecas_comuns"] == ["P0161", "P1193"]
	by_n = {g["n"]: {q["peca"] for q in g["pecas"]} for g in data["grupos"]}
	for (a, b), e in pairs.items():
		assert set(e["pecas_comuns"]) == by_n[a] & by_n[b]
	# os outros pares de grupos não partilham peças
	for a in by_n:
		for b in by_n:
			if a < b and (a, b) not in pairs:
				assert not (by_n[a] & by_n[b]), (a, b)
	assert len(set().union(*by_n.values())) == 62


def test_ids_exist_in_project(data):
	if not os.path.exists(LOG):
		pytest.skip("projects/alpes/log.jsonl não está nesta cópia")
	with open(LOG, encoding="utf-8") as f:
		txt = f.read()
	ids = {q["peca"] for g in data["grupos"] for q in g["pecas"]}
	missing = sorted(p for p in ids if f'"{p}"' not in txt)
	assert not missing, missing
