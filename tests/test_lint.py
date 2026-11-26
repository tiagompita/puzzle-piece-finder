"""Lint barato (2026-11-26, docs/prompts/2026-11-26-verificacao-integracao.md, bloco 4). Três regras, cada uma com a
sua lista branca para o legado e um caso sintético que a faz falhar:

1. **Esperas fixas novas em ``tests/``.** Uma espera fixa é uma CHAMADA (AST) cujo nome é ``sleep`` ou
   ``wait_for_timeout`` (``time.sleep``, ``asyncio.sleep``, ``page.wait_for_timeout``, ``sleep`` importado). Lista
   branca = as 172 chamadas de 2026-11-26 por ficheiro e contagem, exata: um ficheiro acima da contagem falha (espera
   nova), abaixo também (baixar a contagem aqui, para a folga não ser reaproveitada). As «175» do ``grep -rnoE
   "sleep\\(|wait_for_timeout\\("`` incluem 3 que não são chamadas neste código: um comentário
   (``tests/test_server.py``), uma docstring (``tests/test_server_queue.py``) e código dentro de uma string que o
   ``pytester`` corre (``tests/test_net_log.py``).
2. **Regra da gémea escrita à mão** fora de ``src/profile.py`` (a única implementação: ``PuzzleProfile.twin``), do
   ``puzzle.json`` e dos testes, em todos os ``.py`` versionados: ``R - x`` ou ``K - x`` com ``R``/``K`` = linhas + 1 /
   colunas + 1 do perfil (hoje ``48 - l``, ``65 - c``), ou ``<grelha> + 1 - x`` com ``<grelha>`` um nome de linhas,
   colunas ou grelha (``rows``, ``NCOL``, ``GRID[0]``, ``L``, ``C``…). Lista branca por (ficheiro, expressão) e
   contagem, com o motivo.
3. **Módulo de ``src/`` sem ``__all__`` ou indentado a espaços** (``CLAUDE.md``, «Conventions»). Lista branca por
   ficheiro, com o motivo."""
import ast
import collections
import glob
import io
import json
import os
import subprocess
import sys
import tokenize
import warnings

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PERFIL = os.path.join(REPO, "projects", "alpes", "puzzle.json")


def _parse(fonte: str):
	with warnings.catch_warnings():
		warnings.simplefilter("ignore", SyntaxWarning)
		return ast.parse(fonte)


def _ler(fp: str) -> str:
	with open(fp, encoding="utf-8") as f:
		return f.read()


# ---------------------------------------------------------------------------------------------- 1. esperas fixas
ESPERAS = ("sleep", "wait_for_timeout")

# Lista branca (Tiago, 2026-11-26: as atuais, por ficheiro e contagem; contadas como chamadas, ver o docstring).
ESPERAS_BRANCA = {
	"tests/test_board_interface.py": 3,
	"tests/test_ceder.py": 5,
	"tests/test_concorrencia.py": 1,
	"tests/test_detalhe_prioridade.py": 5,
	"tests/test_gui_atividade.py": 5,
	"tests/test_gui_buscar_buracos.py": 3,
	"tests/test_gui_contorno.py": 2,
	"tests/test_gui_detalhe_escrita.py": 1,
	"tests/test_gui_detalhe_prioridade.py": 3,
	"tests/test_gui_f2c.py": 7,
	"tests/test_gui_fila.py": 2,
	"tests/test_gui_flows.py": 1,
	"tests/test_gui_guardadas.py": 1,
	"tests/test_gui_holes.py": 3,
	"tests/test_gui_layout.py": 8,
	"tests/test_gui_novo.py": 11,
	"tests/test_gui_novo_b_grupos_png.py": 1,
	"tests/test_gui_novo_f2.py": 4,
	"tests/test_gui_novo_f2b.py": 6,
	"tests/test_gui_novo_f2c.py": 9,
	"tests/test_gui_novo_f2e.py": 7,
	"tests/test_gui_novo_f2f.py": 10,
	"tests/test_gui_novo_f4.py": 19,
	"tests/test_gui_novo_p0.py": 13,
	"tests/test_gui_novo_toque.py": 2,
	"tests/test_gui_pose.py": 4,
	"tests/test_gui_reports.py": 1,
	"tests/test_gui_search.py": 1,
	"tests/test_gui_suspeitas.py": 2,
	"tests/test_net_log.py": 1,
	"tests/test_placements_completo.py": 3,
	"tests/test_remendo_concorrencia.py": 6,
	"tests/test_seqlock.py": 1,
	"tests/test_seqlock_leitores.py": 4,
	"tests/test_server.py": 7,
	"tests/test_server_idle.py": 5,
	"tests/test_server_queue.py": 4,
	"tests/test_server_shutdown.py": 1,
}


def esperas(fonte: str) -> list:
	"""Linhas das chamadas de espera fixa (``sleep``/``wait_for_timeout``, por nome ou atributo)."""
	out = []
	for n in ast.walk(_parse(fonte)):
		if isinstance(n, ast.Call):
			f = n.func
			nome = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
			if nome in ESPERAS:
				out.append(n.lineno)
	return sorted(out)


def violacoes_esperas(fontes: dict, branca: dict) -> list:
	"""``fontes`` = {caminho relativo: código}. Devolve ``[(ficheiro, contagem, permitidas, linhas)]`` dos ficheiros
	cuja contagem difere da lista branca (acima = espera nova; abaixo = baixar a lista)."""
	out = []
	for rel in sorted(set(fontes) | set(branca)):
		ln = esperas(fontes[rel]) if rel in fontes else []
		if len(ln) != branca.get(rel, 0):
			out.append((rel, len(ln), branca.get(rel, 0), ln))
	return out


def _fontes_testes() -> dict:
	return {os.path.relpath(fp, REPO).replace(os.sep, "/"): _ler(fp)
			for fp in sorted(glob.glob(os.path.join(REPO, "tests", "**", "*.py"), recursive=True))}


def test_sem_esperas_fixas_novas_em_tests():
	v = violacoes_esperas(_fontes_testes(), ESPERAS_BRANCA)
	assert not v, ("esperas fixas fora da lista branca (ficheiro, contagem, permitidas, linhas); acima: esperar por "
				   "uma condição em vez de dormir; abaixo: baixar ESPERAS_BRANCA em tests/test_lint.py: " + repr(v))
	assert sum(ESPERAS_BRANCA.values()) == 172


def test_esperas_sintetico_falha():
	fonte = ("import time, asyncio\nfrom time import sleep\n"
			 "# time.sleep(9) num comentário não conta\n"
			 "def test_x(page):\n\t\"\"\"nem numa docstring: sleep(1)\"\"\"\n"
			 "\ttime.sleep(0.1)\n\tsleep(1)\n\tpage.wait_for_timeout(200)\n\tasyncio.sleep(0)\n")
	assert esperas(fonte) == [6, 7, 8, 9]
	v = violacoes_esperas({"tests/test_novo.py": fonte}, {})
	assert v == [("tests/test_novo.py", 4, 0, [6, 7, 8, 9])]
	# um ficheiro da lista com uma espera a mais falha; com uma a menos também (lista exata)
	assert violacoes_esperas({"tests/a.py": fonte}, {"tests/a.py": 3}) == [("tests/a.py", 4, 3, [6, 7, 8, 9])]
	assert violacoes_esperas({"tests/a.py": fonte}, {"tests/a.py": 5}) == [("tests/a.py", 4, 5, [6, 7, 8, 9])]
	assert violacoes_esperas({"tests/a.py": fonte}, {"tests/a.py": 4}) == []


# ------------------------------------------------------------------------------------- 2. regra da gémea à mão
NOMES_GRELHA = {"rows", "cols", "nrow", "ncol", "nrows", "ncols", "n_rows", "n_cols", "grid"}
NOMES_GRELHA_EXATOS = {"L", "C"}

# (ficheiro, expressão de ast.unparse) -> (contagem, motivo)
GEMEA_BRANCA = {
	("tools/diagnostico/gemeos/ereal.py", "48 - p['k']"): (2, "referencial local do canto BD (k = linha a contar de "
															  "baixo) -> linha global; não é a regra da gémea"),
	("tools/diagnostico/gemeos/ereal.py", "65 - p['j']"): (2, "referencial local do canto BD (j = coluna a contar da "
															  "direita) -> coluna global; não é a regra da gémea"),
	("tools/diagnostico/gemeos/ereal.py", "48 - k"): (1, "idem, BD (k de baixo) -> linha global"),
	("tools/diagnostico/gemeos/ereal.py", "65 - j"): (1, "idem, BD (j da direita) -> coluna global"),
	("tools/diagnostico/gemeos/ereal2.py", "48 - p['k']"): (2, "referencial local dos cantos BE e BD (k = linha a "
															   "contar de baixo) -> linha global"),
	("tools/diagnostico/gemeos/ereal2.py", "65 - p['j']"): (1, "referencial local do canto BD (j da direita) -> coluna"),
	("tools/diagnostico/gemeos/seccao.py", "GRID[0] + 1 - c"): (1, "espelho horizontal do scan da traseira da secção "
																	"(mirror=True); não é a regra da gémea"),
	("tools/diagnostico/gemeos/seccao.py", "GRID[0] + 1 - ca"): (1, "GT das folhas B do E-sym (gémeas da fila de topo) "
																	 "num guião de 2026-10-30, anterior ao perfil e sem "
																	 "ele; congelado, não se corrige"),
}


def _grelha_e(vals: tuple):
	def e(n) -> str:
		"""Motivo se ``n`` (BinOp Sub) é a regra da gémea escrita à mão, senão ''."""
		if not (isinstance(n, ast.BinOp) and isinstance(n.op, ast.Sub)):
			return ""
		a = n.left
		if isinstance(a, ast.Constant) and type(a.value) is int and a.value in vals:
			return "literal"
		if (isinstance(a, ast.BinOp) and isinstance(a.op, ast.Add) and isinstance(a.right, ast.Constant)
				and a.right.value == 1):
			b = a.left.value if isinstance(a.left, ast.Subscript) else a.left
			nome = b.id if isinstance(b, ast.Name) else b.attr if isinstance(b, ast.Attribute) else None
			if nome and (nome in NOMES_GRELHA_EXATOS or nome.lower() in NOMES_GRELHA):
				return "grelha+1"
		return ""
	return e


def _vals_perfil() -> tuple:
	with open(PERFIL, encoding="utf-8") as f:
		g = json.load(f)["grid"]
	return (int(g["rows"]) + 1, int(g["cols"]) + 1)


def gemea_a_mao(fonte: str, vals: tuple) -> list:
	"""``[(linha, expressão)]`` das subtrações que escrevem a regra da gémea à mão (ver o docstring do módulo)."""
	e = _grelha_e(vals)
	return sorted((n.lineno, ast.unparse(n)) for n in ast.walk(_parse(fonte)) if e(n))


def _dentro(rel: str) -> bool:
	return not (rel.startswith("tests/") or rel == "src/profile.py")


def violacoes_gemea(fontes: dict, branca: dict, vals: tuple) -> list:
	"""``[(ficheiro, expressão, contagem, permitidas, linhas)]`` fora da lista branca, e entradas já sem uso."""
	cont = collections.defaultdict(list)
	for rel, fonte in fontes.items():
		if _dentro(rel):
			for ln, ex in gemea_a_mao(fonte, vals):
				cont[(rel, ex)].append(ln)
	out = []
	for k in sorted(set(cont) | set(branca)):
		perm = branca.get(k, (0, ""))[0]
		if len(cont.get(k, [])) != perm:
			out.append((k[0], k[1], len(cont.get(k, [])), perm, cont.get(k, [])))
	return out


def _py_versionados() -> list:
	r = subprocess.run(["git", "-C", REPO, "ls-files", "-z", "*.py"], capture_output=True, check=True)
	return [p.decode("utf-8") for p in r.stdout.split(b"\0") if p]


def test_regra_gemea_so_no_perfil():
	vals = _vals_perfil()
	assert vals == (48, 65)
	fontes = {rel: _ler(os.path.join(REPO, rel)) for rel in _py_versionados() if _dentro(rel)}
	v = violacoes_gemea(fontes, GEMEA_BRANCA, vals)
	assert not v, ("regra da gémea escrita à mão (usar profile.twin()); ou entrada da lista branca sem uso "
				   "(ficheiro, expressão, contagem, permitidas, linhas): " + repr(v))


def test_gemea_sintetico_falha():
	vals = (48, 65)
	fonte = ("NROW, NCOL = 47, 64\nGRID = (64, 47)\n"
			 "def twin(l, c):\n\treturn 48 - l, 65 - c\n"
			 "def twin2(l, c, prof):\n\treturn NROW + 1 - l, prof.cols + 1 - c\n"
			 "def twin3(c):\n\treturn GRID[0] + 1 - c\n"
			 "# 48 - l num comentário não conta\n"
			 "def nao(i, n, deg):\n\treturn n - i, deg + 1 - i, 47 - i\n")
	assert gemea_a_mao(fonte, vals) == [(4, "48 - l"), (4, "65 - c"), (6, "NROW + 1 - l"), (6, "prof.cols + 1 - c"),
										(8, "GRID[0] + 1 - c")]
	v = violacoes_gemea({"tools/x.py": fonte}, {}, vals)
	assert [x[:2] for x in v] == [("tools/x.py", "48 - l"), ("tools/x.py", "65 - c"), ("tools/x.py", "GRID[0] + 1 - c"),
								  ("tools/x.py", "NROW + 1 - l"), ("tools/x.py", "prof.cols + 1 - c")]
	# nos sítios permitidos não conta; uma entrada da lista branca já sem uso falha
	assert violacoes_gemea({"src/profile.py": fonte, "tests/test_y.py": fonte}, {}, vals) == []
	assert violacoes_gemea({}, {("tools/x.py", "48 - l"): (1, "motivo")}, vals) == [("tools/x.py", "48 - l", 0, 1, [])]


def test_ereal2_twin_cell_e_o_do_perfil():
	"""``tools/diagnostico/gemeos/ereal2.py`` usa ``PuzzleProfile.twin``: as mesmas células que a fórmula antiga
	(47 + 1 - l, 64 + 1 - c) nas 3008 células, em escalares e em arrays (``np.mgrid``, como em ``ereal2``)."""
	sys.path.insert(0, os.path.join(REPO, "tools", "diagnostico", "gemeos"))
	try:
		import ereal2 as E2
	finally:
		sys.path.pop(0)
	from src.profile import PuzzleProfile
	prof = PuzzleProfile.load(PERFIL)
	for l in range(1, prof.rows + 1):
		for c in range(1, prof.cols + 1):
			assert tuple(E2.twin_cell(l, c)) == prof.twin(l, c) == (48 - l, 65 - c)
	Lg, Cg = np.mgrid[1:E2.NROW + 1, 1:E2.NCOL + 1]
	a, b = E2.twin_cell(Lg, Cg)
	assert a.dtype == Lg.dtype and (a == 48 - Lg).all() and (b == 65 - Cg).all()


# ------------------------------------------------------------------------------- 3. módulos de src/: tabs e __all__
SRC_BRANCA = {
	"src/__init__.py": ({"sem_all"}, "marcador de pacote vazio"),
	"src/gui.py": ({"sem_all", "espacos"}, "GUI Tkinter legada (só matching; CLAUDE.md), escrita a espaços antes da "
										   "convenção; não se reescreve"),
	"src/main.py": ({"sem_all", "espacos"}, "CLI ingénuo legado (`python -m src.main`)"),
}


def problemas_modulo(fonte: str) -> set:
	"""``{'sem_all', 'espacos'}``: sem ``__all__`` ao nível do módulo; algum bloco indentado a espaços (tokens
	INDENT; linhas de continuação não contam)."""
	out = set()
	t = _parse(fonte)
	alvos = []
	for n in t.body:
		if isinstance(n, ast.Assign):
			alvos += n.targets
		elif isinstance(n, (ast.AnnAssign, ast.AugAssign)):
			alvos.append(n.target)
	if not any(isinstance(a, ast.Name) and a.id == "__all__" for a in alvos):
		out.add("sem_all")
	for tok in tokenize.generate_tokens(io.StringIO(fonte).readline):
		if tok.type == tokenize.INDENT and " " in tok.string:
			out.add("espacos")
			break
	return out


def violacoes_src(fontes: dict, branca: dict) -> list:
	out = []
	for rel in sorted(set(fontes) | set(branca)):
		p = problemas_modulo(fontes[rel]) if rel in fontes else set()
		perm = branca.get(rel, (set(), ""))[0]
		if p != perm:
			out.append((rel, sorted(p), sorted(perm)))
	return out


def test_modulos_src_com_tabs_e_all():
	fontes = {os.path.relpath(fp, REPO).replace(os.sep, "/"): _ler(fp)
			  for fp in sorted(glob.glob(os.path.join(REPO, "src", "**", "*.py"), recursive=True))}
	v = violacoes_src(fontes, SRC_BRANCA)
	assert not v, ("módulos de src/ sem __all__ ou indentados a espaços, ou lista branca desatualizada "
				   "(ficheiro, problemas, permitidos): " + repr(v))


def test_src_sintetico_falha():
	bom = '"""Doc."""\n__all__ = ["f"]\n\n\ndef f(x):\n\tif x:\n\t\treturn (1,\n\t\t        2)\n\treturn 0\n'
	sem_all = '"""Doc."""\n\n\ndef f():\n\treturn 1\n'
	espacos = '__all__ = ["f"]\n\n\ndef f():\n    return 1\n'
	assert problemas_modulo(bom) == set()
	assert problemas_modulo(sem_all) == {"sem_all"}
	assert problemas_modulo(espacos) == {"espacos"}
	assert problemas_modulo("__all__: list = []\n") == set()
	assert violacoes_src({"src/novo.py": sem_all, "src/outro.py": espacos, "src/bom.py": bom}, {}) == [
		("src/novo.py", ["sem_all"], []), ("src/outro.py", ["espacos"], [])]
	assert violacoes_src({}, {"src/velho.py": ({"sem_all"}, "m")}) == [("src/velho.py", [], ["sem_all"])]
