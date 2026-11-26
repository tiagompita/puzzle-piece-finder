"""Hook ``tools/githooks/commit-msg`` (D4 de 2026-11-26) num repositório temporário, com ``git commit`` real:
recusa Co-Authored-By e Claude como autor/co-autor; aceita mensagens que citam ``.claude/`` ou ``CLAUDE.md``."""
import os
import shutil
import subprocess

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(REPO, "tools", "githooks")

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="sem git")


@pytest.fixture
def repo(tmp_path):
	def git(*a, **kw):
		return subprocess.run(["git", "-C", str(tmp_path), *a], capture_output=True, text=True, encoding="utf-8", **kw)
	git("init", "-q")
	git("config", "user.name", "Teste")
	git("config", "user.email", "teste@example.com")
	git("config", "commit.gpgsign", "false")
	git("config", "core.hooksPath", HOOKS.replace(os.sep, "/"))
	n = [0]

	def commit(msg: str) -> subprocess.CompletedProcess:
		n[0] += 1
		(tmp_path / f"f{n[0]}.txt").write_text(str(n[0]))
		git("add", "-A")
		fp = tmp_path.parent / f"msg_{n[0]}.txt"
		fp.write_text(msg, encoding="utf-8")
		return git("commit", "-q", "-F", str(fp))
	return commit


@pytest.mark.parametrize("msg", [
	"corrige x\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n",
	"corrige x\n\nCo-authored-by: Fulano <fulano@example.com>\n",
	"corrige x\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)\n",
	"corrige x\n\nGerado com o Claude\n",
	"corrige x\n\nSigned-off-by: Claude <claude@example.com>\n",
	"corrige x\n\nAutor: Claude (Opus)\n",
	"corrige x\n\n— Claude\n",
	"corrige x\n\nClaude Code\n",
	"corrige x\n\nfeito por: noreply@anthropic.com\n",
])
def test_recusa(repo, msg):
	r = repo(msg)
	assert r.returncode != 0, (msg, r.stdout, r.stderr)
	assert "commit-msg: mensagem recusada" in r.stderr


@pytest.mark.parametrize("msg", [
	"docs: atualiza CLAUDE.md e .claude/agents/implementer.md\n",
	"regras: .claude/settings.json e o CLAUDE.md global\n\nAutor: Tiago\n",
	"tools.verify: passo 0 com hooksPath\n",
	"docs: o gestor do Claude Code passou a ler docs/HANDOFF.md\n",
	"corrige o caminho de C:/Users/x/.claude/projects/claude.md\n",
	"docs: decisões do Tiago\n\n# Co-Authored-By: comentário do git, ignorado\n",
])
def test_aceita(repo, msg):
	r = repo(msg)
	assert r.returncode == 0, (msg, r.stdout, r.stderr)
