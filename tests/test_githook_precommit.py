"""Hook ``tools/githooks/pre-commit`` (2026-11-26) num repositório temporário, com ``git commit`` real.

O hook corre ``python -m tools.verify`` só quando o stage toca ``src/``, ``tools/verify/``, ``tests/golden/`` ou
``projects/``. Aqui o ``tools.verify`` é um falso, por pôr no repositório temporário (fora do índice, em
``.git/info/exclude``): grava ``marca.txt`` quando corre e sai com o código escrito em ``rc.txt``. Assim mede-se que o
hook bloqueia (exit != 0), deixa passar (exit 0) e não paga o verify num commit só de docs."""
import os
import shutil
import subprocess

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(REPO, "tools", "githooks")
HOOK = os.path.join(HOOKS, "pre-commit")

pytestmark = pytest.mark.skipif(shutil.which("git") is None or shutil.which("python") is None,
								reason="sem git ou sem python no PATH (o repositório temporário não tem .venv)")

FALSO = ("import pathlib, sys\n"
		 "pathlib.Path('marca.txt').write_text('correu')\n"
		 "sys.exit(int(pathlib.Path('rc.txt').read_text().strip() or 0))\n")


class Repo:
	def __init__(self, d):
		self.d = d
		self.n = 0

	def git(self, *a):
		return subprocess.run(["git", "-C", str(self.d), *a], capture_output=True, text=True, encoding="utf-8")

	def escreve(self, rel, txt="x\n"):
		fp = self.d / rel
		fp.parent.mkdir(parents=True, exist_ok=True)
		fp.write_text(txt, encoding="utf-8")

	def rc(self, codigo: int):
		(self.d / "rc.txt").write_text(str(codigo))
		(self.d / "marca.txt").unlink(missing_ok=True)

	def correu(self) -> bool:
		return (self.d / "marca.txt").exists()

	def head(self) -> str:
		return self.git("rev-parse", "HEAD").stdout.strip()

	def commit(self, *rels, txt=None):
		self.n += 1
		for r in rels:
			self.escreve(r, txt if txt is not None else f"{self.n}\n")
		self.git("add", "-f", *rels)
		return self.git("commit", "-q", "-m", f"teste {self.n}")


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
	r.escreve(".git/info/exclude", "tools/\nrc.txt\nmarca.txt\n")
	r.rc(0)
	assert r.commit("README.md").returncode == 0       # primeiro commit, sem caminhos relevantes
	assert not r.correu()
	return r


@pytest.mark.parametrize("rel", ["src/a.py", "tools/verify/regra.py", "tests/golden/manifesto.json",
								 "projects/p/log.jsonl"])
def test_bloqueia_quando_o_verify_falha(repo, rel):
	repo.rc(4)
	h0 = repo.head()
	r = repo.commit(rel)
	assert r.returncode != 0, (r.stdout, r.stderr)
	assert repo.correu()
	assert "tools.verify saiu com código 4: commit parado" in r.stderr
	assert repo.head() == h0


@pytest.mark.parametrize("rel", ["src/a.py", "tools/verify/regra.py", "tests/golden/manifesto.json",
								 "projects/p/log.jsonl"])
def test_deixa_passar_quando_o_verify_passa(repo, rel):
	repo.rc(0)
	h0 = repo.head()
	r = repo.commit(rel)
	assert r.returncode == 0, (r.stdout, r.stderr)
	assert repo.correu()
	assert repo.head() != h0


@pytest.mark.parametrize("rel", ["docs/nota.md", "CLAUDE.md", "tests/test_x.py", "tools/diagnostico/a.py",
								 "srcx/a.py", "docs/src/a.py", "tools/githooks/x", "tests/goldenx.json"])
def test_sem_caminhos_relevantes_nao_corre_o_verify(repo, rel):
	repo.rc(5)                                            # se corresse, bloqueava
	r = repo.commit(rel)
	assert r.returncode == 0, (r.stdout, r.stderr)
	assert not repo.correu()


def test_remocao_e_rename_contam(repo):
	repo.rc(0)
	assert repo.commit("src/a.py", "src/b.py").returncode == 0
	repo.rc(3)
	repo.git("rm", "-q", "src/a.py")
	r = repo.git("commit", "-q", "-m", "remove")
	assert r.returncode != 0 and repo.correu(), r.stderr
	repo.git("reset", "-q", "--hard")
	repo.rc(3)
	(repo.d / "docs").mkdir(exist_ok=True)
	repo.git("mv", "src/b.py", "docs/b.py")
	r = repo.git("commit", "-q", "-m", "move para docs")
	assert r.returncode != 0 and repo.correu(), r.stderr     # o rename conta pela origem


def test_commit_misto_corre_o_verify(repo):
	repo.rc(2)
	r = repo.commit("docs/nota.md", "src/a.py")
	assert r.returncode != 0 and repo.correu()


def test_hook_versionado_com_lf_e_executavel():
	with open(HOOK, "rb") as f:
		b = f.read()
	assert b.startswith(b"#!/bin/sh\n") and b"\r" not in b
	r = subprocess.run(["git", "-C", REPO, "ls-files", "-s", "tools/githooks/pre-commit"], capture_output=True, text=True)
	assert r.stdout.startswith("100755 "), r.stdout
