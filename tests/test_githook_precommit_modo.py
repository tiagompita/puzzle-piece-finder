"""Hook ``tools/githooks/pre-commit``: modo do ``tools.verify`` (2026-11-26, «fecho»).

``--rapido`` por omissão; o modo completo (sem ``--rapido``) quando o stage toca um módulo crítico da segmentação ou do
matching (``src/segmentation.py``, ``src/shape.py``, ``src/fit.py``, ``src/twin.py``). Repositório temporário com
``git commit`` real e um ``tools.verify`` falso que grava os argumentos com que correu (o mesmo desenho de
``tests/test_githook_precommit.py``)."""
import os
import shutil
import subprocess

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(REPO, "tools", "githooks")

pytestmark = pytest.mark.skipif(shutil.which("git") is None or shutil.which("python") is None,
								reason="sem git ou sem python no PATH (o repositório temporário não tem .venv)")

FALSO = ("import pathlib, sys\n"
		 "pathlib.Path('args.txt').write_text(' '.join(sys.argv[1:]) or '-')\n"
		 "sys.exit(0)\n")


@pytest.fixture
def repo(tmp_path):
	def git(*a):
		return subprocess.run(["git", "-C", str(tmp_path), *a], capture_output=True, text=True, encoding="utf-8")

	def escreve(rel, txt="x\n"):
		fp = tmp_path / rel
		fp.parent.mkdir(parents=True, exist_ok=True)
		fp.write_text(txt, encoding="utf-8")

	git("init", "-q")
	git("config", "user.name", "Teste")
	git("config", "user.email", "teste@example.com")
	git("config", "commit.gpgsign", "false")
	git("config", "core.hooksPath", HOOKS.replace(os.sep, "/"))
	escreve("tools/__init__.py", "")
	escreve("tools/verify/__init__.py", "")
	escreve("tools/verify/__main__.py", FALSO)
	escreve(".git/info/exclude", "tools/\nargs.txt\n")
	n = [0]

	def commit(*rels):
		n[0] += 1
		(tmp_path / "args.txt").unlink(missing_ok=True)
		for r in rels:
			escreve(r, f"{n[0]}\n")
		git("add", "-f", *rels)
		r = git("commit", "-q", "-m", f"teste {n[0]}")
		a = tmp_path / "args.txt"
		return r, (a.read_text().strip() if a.exists() else None)

	assert commit("README.md")[1] is None
	return commit


@pytest.mark.parametrize("rel", ["src/state.py", "src/server.py", "tools/verify/regra.py", "tests/golden/baseline.json",
								 "projects/p/puzzle.json", "src/segmentation_extra.py", "src/fitx.py"])
def test_rapido_por_omissao(repo, rel):
	r, args = repo(rel)
	assert r.returncode == 0, r.stderr
	assert args == "--rapido", (rel, args)


@pytest.mark.parametrize("rel", ["src/segmentation.py", "src/shape.py", "src/fit.py", "src/twin.py"])
def test_completo_quando_toca_um_modulo_critico(repo, rel):
	r, args = repo(rel)
	assert r.returncode == 0, r.stderr
	assert args == "-", (rel, args)          # sem argumentos = modo completo


def test_completo_num_commit_misto(repo):
	r, args = repo("docs/x.md", "src/state.py", "src/twin.py")
	assert r.returncode == 0, r.stderr
	assert args == "-"


def test_sem_caminho_relevante_nao_corre(repo):
	r, args = repo("docs/y.md")
	assert r.returncode == 0 and args is None
