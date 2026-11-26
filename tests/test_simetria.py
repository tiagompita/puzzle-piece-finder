"""Simetria do corte (4.2 do levantamento de 2026-11-26) e conhecimento de um puzzle fora do código.

* A exceção conhecida da simetria vive no perfil (``symmetry.excecoes`` de ``puzzle.json``), nunca em ``src/``;
  ``PuzzleProfile`` preserva-a ao ler e ao gravar e valida a forma.
* «alpes» não aparece no código executável de ``src/`` (análise do AST: literais e nomes; comentários e docstrings
  não contam), exceto nos defaults de ``--project`` da lista branca abaixo, cada um com o motivo.
* Pares gémeos colocados: ``nn_max`` acima de ``TWIN_LOCAL_MAX_MM`` só nas exceções do perfil ou na lista «por rever»
  (D3 = C, ``tests/golden/simetria_por_rever.json``). Corre só se o perfil declarar simetria, sobre uma CÓPIA."""
import ast
import json
import os

import pytest

from src.profile import PuzzleProfile
from tools.verify import ambiente as AMB
from tools.verify import invariantes as INV

REPO = AMB.REPO
SRC = os.path.join(REPO, "src")
PROJ = os.path.join(REPO, "projects", "alpes")
POR_REVER = os.path.join(REPO, "tests", "golden", "simetria_por_rever.json")

# Lista branca (decisão 4 do planeamento, 2026-11-26): defaults de linha de comando que apontam para o único projeto
# do repositório. Não são conhecimento do puzzle (grelha, simetria, exceções); só poupam escrever --project.
LISTA_BRANCA = {
	("src/artreg.py", "--project"): "default de --project do registo da arte (CLI)",
	("src/fit.py", "--project"): "default de --project de `python -m src.fit --relatorio` (CLI)",
	("src/ingest.py", "DEFAULT_PROJECT"): "default de --project da importação de scans (CLI)",
	("src/ingest.py", "DEFAULT_PROFILE"): "default de --profile da importação (perfil a copiar num projeto novo)",
	("src/render.py", "--project"): "default de --project do render (CLI)",
	("src/reports.py", "--project"): "default de --project dos reports (CLI)",
	("src/server.py", "--project"): "default de --project do servidor da GUI (CLI)",
}


def _docstrings(tree) -> set:
	ids = set()
	for n in ast.walk(tree):
		if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body:
			b = n.body[0]
			if isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant) and isinstance(b.value.value, str):
				ids.add(id(b.value))
	return ids


def _contexto(node, parents) -> str:
	"""``'--project'`` dentro de ``add_argument('--project', ...)``; senão o nome atribuído; senão ``''``."""
	p = parents.get(id(node))
	while p is not None:
		if (isinstance(p, ast.Call) and isinstance(p.func, ast.Attribute) and p.func.attr == "add_argument" and p.args
				and isinstance(p.args[0], ast.Constant) and p.args[0].value == "--project"):
			return "--project"
		if isinstance(p, ast.Assign) and len(p.targets) == 1 and isinstance(p.targets[0], ast.Name):
			return p.targets[0].id
		p = parents.get(id(p))
	return ""


def ocorrencias(fonte: str, rel: str, palavra: str = "alpes") -> list:
	"""``[(rel, contexto, linha, texto)]`` de ``palavra`` em literais e nomes do código executável de ``fonte``."""
	tree = ast.parse(fonte)
	docs = _docstrings(tree)
	parents = {}
	for n in ast.walk(tree):
		for c in ast.iter_child_nodes(n):
			parents[id(c)] = n
	out = []
	for n in ast.walk(tree):
		txt = None
		if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs:
			txt = n.value
		elif isinstance(n, ast.Name):
			txt = n.id
		elif isinstance(n, ast.Attribute):
			txt = n.attr
		elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
			txt = n.name
		elif isinstance(n, ast.arg):
			txt = n.arg
		elif isinstance(n, ast.keyword) and n.arg:
			txt = n.arg
		elif isinstance(n, ast.alias):
			txt = n.asname or n.name
		if txt is not None and palavra in txt.lower():
			out.append((rel, _contexto(n, parents), getattr(n, "lineno", 0), txt))
	return out


def _todas():
	occ = []
	for d, _, fs in os.walk(SRC):
		for f in sorted(fs):
			if f.endswith(".py"):
				fp = os.path.join(d, f)
				rel = os.path.relpath(fp, REPO).replace(os.sep, "/")
				with open(fp, encoding="utf-8") as fh:
					occ += ocorrencias(fh.read(), rel)
	return occ


def test_alpes_nao_aparece_no_codigo_de_src():
	occ = _todas()
	fora = [o for o in occ if (o[0], o[1]) not in LISTA_BRANCA]
	assert not fora, f"«alpes» no código de src/ fora da lista branca: {fora}"
	usadas = {(o[0], o[1]) for o in occ}
	assert set(LISTA_BRANCA) <= usadas, f"entradas da lista branca já sem uso (tirar): {set(LISTA_BRANCA) - usadas}"


def test_detetor_apanha_a_excecao_por_id_no_codigo():
	"""O que havia em ``src/consistency.py`` até 2026-11-26 tem de falhar; comentários e docstrings não."""
	velho = ('"""Doc com alpes."""\n# comentário alpes\n'
			 'TWIN_EXCEPTIONS = {"alpes": [{"cols": [32, 33]}]}\n'
			 'def f(project):\n\t"""alpes na docstring."""\n\treturn project.id == "alpes"\n'
			 'alpes_rows = 47\n')
	occ = ocorrencias(velho, "src/x.py")
	assert sorted((o[1], o[3]) for o in occ) == sorted([("TWIN_EXCEPTIONS", "alpes"), ("", "alpes"),
														 ("alpes_rows", "alpes_rows")])


def test_twin_exceptions_saiu_de_consistency():
	from src import consistency as CS
	assert not hasattr(CS, "TWIN_EXCEPTIONS")
	assert "TWIN_EXCEPTIONS" not in CS.__all__


# ------------------------------------------------------------------ perfil: symmetry.excecoes
EXC = [{"cols": [32, 33], "rows": [[1, 3], [45, 47]], "texto": "corte não simétrico (teste)"}]


def test_perfil_preserva_excecoes_ao_ler_e_gravar(tmp_path):
	p = PuzzleProfile(id="x", grid={"cols": 64, "rows": 47}, symmetry={"type": "rot180", "excecoes": EXC})
	fp = tmp_path / "puzzle.json"
	p.save(str(fp))
	q = PuzzleProfile.load(str(fp))
	assert q.symmetry["excecoes"] == EXC
	assert q.to_dict() == p.to_dict()


def test_excecao_so_vem_do_perfil():
	from src import consistency as CS
	sem = PuzzleProfile(id="alpes", grid={"cols": 64, "rows": 47}, symmetry={"type": "rot180"})
	com = PuzzleProfile(id="outro", grid={"cols": 64, "rows": 47}, symmetry={"type": "rot180", "excecoes": EXC})
	assert CS.twin_exception(sem, (2, 32)) is None            # o id «alpes» já não dá a exceção
	assert CS.twin_exception(com, (2, 32)) == "corte não simétrico (teste)"
	assert CS.twin_exception(com, (46, 33)) == "corte não simétrico (teste)"
	assert CS.twin_exception(com, (4, 32)) is None


@pytest.mark.parametrize("exc", [
	{"cols": [32]},
	[{"cols": [], "rows": [[1, 2]]}],
	[{"cols": [32], "rows": [[3, 1]]}],
	[{"cols": [32], "rows": [1, 3]}],
	["corte"],
])
def test_perfil_recusa_excecoes_mal_formadas(exc):
	with pytest.raises(ValueError):
		PuzzleProfile(id="x", grid={"cols": 64, "rows": 47}, symmetry={"type": "rot180", "excecoes": exc})


def test_perfil_alpes_declara_a_excecao_c32_c33():
	p = PuzzleProfile.load(os.path.join(PROJ, "puzzle.json"))
	assert p.symmetry["type"] == "rot180"
	assert p.symmetry["excecoes"] == [{"cols": [32, 33], "rows": [[1, 5], [43, 47]],
									   "texto": "corte c32|c33 não simétrico (confirmado pelas imagens, D3 = A)"}]


# ------------------------------------------------------------------ 4.2 pares gémeos colocados (cópia do projeto)
@pytest.fixture(scope="module")
def pr_copia():
	if not os.path.isdir(os.path.join(PROJ, "pieces")):
		pytest.skip("projects/alpes sem pieces/ (ativos fora do git)")
	raiz, dst = AMB.copiar_projeto(PROJ)
	try:
		from src.state import Project
		yield Project.open(dst)
	finally:
		AMB.apagar_copia(raiz)


def _por_rever():
	with open(POR_REVER, encoding="utf-8") as f:
		return json.load(f)["pares"]


def test_simetria_dos_pares_colocados(pr_copia):
	if pr_copia.profile.symmetry.get("type", "none") == "none":
		pytest.skip("o perfil não declara simetria")
	r = INV.simetria(pr_copia, _por_rever())
	assert r["aplicavel"] and r["medidos"] > 0
	assert r["n"] == 0, f"pares gémeos acima de {r['limiar_mm']} mm fora da exceção e da lista por rever: {r['violacoes']}"


def test_simetria_sem_a_lista_por_rever_falha_nos_3_pares(pr_copia):
	"""Sem a lista D3 o teste falha exatamente nos 3 pares conhecidos (o teste consegue falhar)."""
	r = INV.simetria(pr_copia, ())
	got = sorted("|".join(sorted((v["a"], v["b"]))) for v in r["violacoes"])
	assert got == sorted("|".join(sorted(x.split("|"))) for x in _por_rever())


def test_simetria_com_a_excecao_antiga_falha_nos_3_pares_da_d3(pr_copia, monkeypatch):
	"""Teste novo (D3 = A, 2026-11-26): com a exceção antiga (filas 1-3/45-47) e sem lista «por rever», o teste
	falha exatamente nos 3 pares que a D3 = A pôs na exceção (o teste continua a conseguir falhar)."""
	exc = [dict(e) for e in pr_copia.profile.symmetry["excecoes"]]
	exc[0]["rows"] = [[1, 3], [45, 47]]
	monkeypatch.setitem(pr_copia.profile.symmetry, "excecoes", exc)
	r = INV.simetria(pr_copia, ())
	got = sorted("|".join(sorted((v["a"], v["b"]))) for v in r["violacoes"])
	assert got == sorted("|".join(sorted(x.split("|"))) for x in ["P0140|P0499", "P0495|P0938", "P0500|P1178"])


def test_simetria_nao_se_aplica_sem_simetria_declarada(pr_copia, monkeypatch):
	monkeypatch.setitem(pr_copia.profile.symmetry, "type", "none")
	r = INV.simetria(pr_copia, ())
	assert r == {"n": 0, "violacoes": [], "aplicavel": False, "pares": 0}
