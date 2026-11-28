"""Hook ``tools/githooks/pre-commit`` (2026-11-28): stage completo nos caminhos vigiados.

O verify lê a árvore de trabalho, não o índice. Com um stage parcial verificaria o disco e não o commit. Por isso,
quando o commit corre o verify (o stage toca ``src/``, ``tools/verify/``, ``tests/golden/`` ou ``projects/``), o hook
recusa se um caminho vigiado tiver alterações fora do stage (``git diff``) ou ficheiros não rastreados que o
``.gitignore`` não ignora. Sem ``git stash``. Um commit que não corre o verify não é afetado. Mesmo padrão de
``tests/test_githook_precommit.py``: repositório temporário e ``tools.verify`` falso."""
import os
import shutil
import subprocess

import pytest

from tests.test_githook_precommit import FALSO, HOOKS, Repo

pytestmark = pytest.mark.skipif(shutil.which("git") is None or shutil.which("python") is None,
								reason="sem git ou sem python no PATH (o repositório temporário não tem .venv)")


@pytest.fixture
def repo(tmp_path):
	r = Repo(tmp_path)
	r.git("init", "-q")
	r.git("config", "user.name", "Teste")
	r.git("config", "user.email", "teste@example.com")
	r.git("config", "commit.gpgsign", "false")
	r.git("config", "core.hooksPath", HOOKS.replace(os.sep, "/"))
	r.escreve("tools/__init__.py", "")
	r.escreve("tools/verify/__init__.py", "")
	r.escreve("tools/verify/__main__.py", FALSO)
	r.escreve(".git/info/exclude", "tools/\nrc.txt\nmarca.txt\nsrc/ignorado.py\n")
	r.rc(0)
	assert r.commit("README.md", "src/a.py").returncode == 0
	return r


def _commit_em_stage(repo, *rels):
	for rel in rels:
		repo.escreve(rel, "novo\n")
	repo.git("add", "-f", *rels)
	repo.rc(0)
	return repo.git("commit", "-q", "-m", "teste")


@pytest.mark.parametrize("fora", ["src/a.py", "projects/p/log.jsonl", "tests/golden/manifesto.json"])
def test_recusa_com_alteracao_fora_do_stage(repo, fora):
	repo.escreve("projects/p/log.jsonl", "base\n")
	repo.escreve("tests/golden/manifesto.json", "base\n")
	repo.git("add", "-f", "projects/p/log.jsonl", "tests/golden/manifesto.json")
	assert repo.git("commit", "-q", "-m", "base").returncode == 0
	repo.escreve(fora, "alterado fora do stage\n")
	h0 = repo.head()
	r = _commit_em_stage(repo, "src/b.py")
	assert r.returncode != 0, (r.stdout, r.stderr)
	assert not repo.correu()
	assert fora in r.stderr
	assert repo.head() == h0


def test_recusa_com_ficheiro_nao_rastreado(repo):
	repo.escreve("src/novo.py", "por adicionar\n")
	h0 = repo.head()
	r = _commit_em_stage(repo, "src/b.py")
	assert r.returncode != 0, (r.stdout, r.stderr)
	assert not repo.correu()
	assert "src/novo.py" in r.stderr
	assert repo.head() == h0


def test_a_mensagem_lista_todos_os_ficheiros(repo):
	repo.escreve("src/a.py", "alterado\n")
	repo.escreve("src/novo.py", "novo\n")
	r = _commit_em_stage(repo, "src/b.py")
	assert r.returncode != 0
	assert "src/a.py" in r.stderr and "src/novo.py" in r.stderr and "src/b.py" not in r.stderr


def test_aceita_com_tudo_em_stage(repo):
	r = _commit_em_stage(repo, "src/b.py", "src/c.py")
	assert r.returncode == 0, (r.stdout, r.stderr)
	assert repo.correu()


def test_ignorados_nao_contam(repo):
	repo.escreve("src/ignorado.py", "ignorado pelo exclude\n")
	r = _commit_em_stage(repo, "src/b.py")
	assert r.returncode == 0, (r.stdout, r.stderr)
	assert repo.correu()


def test_alteracao_fora_de_caminhos_vigiados_nao_conta(repo):
	repo.escreve("docs/rascunho.md", "por adicionar\n")
	repo.escreve("README.md", "alterado fora do stage\n")
	r = _commit_em_stage(repo, "src/b.py")
	assert r.returncode == 0, (r.stdout, r.stderr)
	assert repo.correu()


def test_stage_sem_vigiados_nao_recusa_mesmo_com_o_disco_sujo(repo):
	"""Sem caminho vigiado no stage o verify não corre e o commit não o afeta: não há nada a proteger."""
	repo.escreve("src/a.py", "alterado fora do stage\n")
	repo.escreve("src/novo.py", "por adicionar\n")
	repo.rc(5)
	repo.escreve("docs/nota.md", "nota\n")
	repo.git("add", "docs/nota.md")
	r = repo.git("commit", "-q", "-m", "so docs")
	assert r.returncode == 0, (r.stdout, r.stderr)
	assert not repo.correu()


def test_nao_usa_git_stash():
	with open(os.path.join(HOOKS, "pre-commit"), encoding="utf-8") as f:
		linhas = [l for l in f.read().splitlines() if not l.lstrip().startswith("#")]
	assert not any("stash" in l for l in linhas)
