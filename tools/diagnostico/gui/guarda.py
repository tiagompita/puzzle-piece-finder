"""Guarda das medições: nenhum apagar nem copiar para cima do projeto real.

Em 2026-11-24 o servidor encontrou ``projects/alpes/pieces`` e ``overlays`` vazias (causa não provada, ``docs/decisoes.md``
2026-11-24). Os guiões de medição copiam o projeto (``copytree``) e apagam a cópia (``rmtree``); estas duas funções são o
único caminho permitido para isso:

* o caminho é resolvido a sério (``os.path.realpath``: ``..``, ligações simbólicas, junções do Windows) antes de qualquer
  decisão;
* recusa-se um caminho que SEJA, esteja DENTRO ou CONTENHA um projeto real (``<repo>/projects`` do checkout em uso, do
  repositório principal quando o checkout é um ``git worktree``, e de ``PPF_REPO``; mais o que vier em
  ``PPF_PROTEGIDOS``, separado por ``os.pathsep``);
* ``rmtree`` recusa também uma pasta que tenha lá dentro uma ligação (simbólica ou junção) cujo destino é um projeto real;
* por omissão (``temporario=True``) só se apaga e só se copia para debaixo do diretório temporário do sistema ou de
  ``PPF_SCRATCH``. ``temporario=False`` mantém só a recusa do projeto real (ferramentas cujo destino fica no repositório).

Sem dependências do ``src/``: corre com qualquer checkout (os guiões também correm sobre worktrees antigos)."""
import os
import shutil
import tempfile

__all__ = ["Recusado", "protegidos", "protegido", "permitidos", "rmtree", "copytree"]

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class Recusado(RuntimeError):
	"""A operação tocaria no projeto real (ou fora das pastas temporárias permitidas)."""


def _real(p) -> str:
	return os.path.normcase(os.path.realpath(os.fspath(p)))


def _main_repo(root: str):
	"""``.git`` de um worktree é um ficheiro ``gitdir: <repo>/.git/worktrees/<nome>``: devolve ``<repo>``."""
	fp = os.path.join(root, ".git")
	if not os.path.isfile(fp):
		return None
	try:
		with open(fp, encoding="utf-8") as f:
			line = f.read().strip()
	except OSError:
		return None
	if not line.startswith("gitdir:"):
		return None
	gd = os.path.normpath(line.split(":", 1)[1].strip())
	marker = os.sep + ".git" + os.sep
	i = gd.replace("/", os.sep).find(marker)
	return gd[:i] if i > 0 else None


def protegidos() -> list:
	"""Raízes protegidas (caminhos reais): as pastas ``projects`` e cada projeto lá dentro."""
	repos = [ROOT]
	main = _main_repo(ROOT)
	if main:
		repos.append(main)
	if os.environ.get("PPF_REPO"):
		repos.append(os.environ["PPF_REPO"])
		m2 = _main_repo(os.environ["PPF_REPO"])
		if m2:
			repos.append(m2)
	out = set()
	for r in repos:
		pj = os.path.join(r, "projects")
		out.add(_real(pj))
		if os.path.isdir(pj):
			for n in os.listdir(pj):
				out.add(_real(os.path.join(pj, n)))
	for e in os.environ.get("PPF_PROTEGIDOS", "").split(os.pathsep):
		if e.strip():
			out.add(_real(e.strip()))
	return sorted(out)


def _dentro(a: str, b: str) -> bool:
	"""``a`` é ``b`` ou está debaixo de ``b`` (ambos já reais e normalizados)."""
	return a == b or a.startswith(b.rstrip(os.sep) + os.sep)


def protegido(path) -> bool:
	"""Verdadeiro se ``path`` é, está dentro de, ou contém um projeto real."""
	rp = _real(path)
	return any(_dentro(rp, p) or _dentro(p, rp) for p in protegidos())


def permitidos() -> list:
	"""Raízes onde se pode apagar/copiar com ``temporario=True``: o temporário do sistema e ``PPF_SCRATCH``."""
	out = [_real(tempfile.gettempdir())]
	if os.environ.get("PPF_SCRATCH"):
		out.append(_real(os.environ["PPF_SCRATCH"]))
	return out


def _verificar(path, operacao: str, temporario: bool) -> str:
	rp = _real(path)
	if protegido(rp):
		raise Recusado(f"{operacao} recusado: {path} (real: {rp}) é, está dentro de ou contém um projeto real")
	if temporario:
		raizes = permitidos()
		if not any(_dentro(rp, r) and rp != r for r in raizes):
			raise Recusado(f"{operacao} recusado: {path} (real: {rp}) não está debaixo de uma pasta temporária "
						   f"({raizes}); defina PPF_SCRATCH ou crie a pasta com tempfile.mkdtemp")
	return rp


def _ligacoes_para_protegidos(rp: str) -> list:
	"""Ligações (simbólicas ou junções) dentro de ``rp`` cujo destino é um projeto real."""
	prot = protegidos()
	bad = []
	isjunction = getattr(os.path, "isjunction", lambda p: False)
	for d, dirs, files in os.walk(rp, followlinks=False):
		for n in dirs + files:
			fp = os.path.join(d, n)
			if os.path.islink(fp) or isjunction(fp):
				t = _real(fp)
				if any(_dentro(t, p) or _dentro(p, t) for p in prot):
					bad.append(fp)
	return bad


def rmtree(path, *, temporario: bool = True, **kw) -> None:
	"""``shutil.rmtree`` só depois de ``path`` passar a guarda (ver o módulo). Um caminho inexistente é aceite."""
	rp = _verificar(path, "rmtree", temporario)
	if not os.path.lexists(rp):
		return
	bad = _ligacoes_para_protegidos(rp)
	if bad:
		raise Recusado(f"rmtree recusado: {path} tem ligações para um projeto real: {bad[:3]}")
	shutil.rmtree(path, **kw)


def copytree(src, dst, *, temporario: bool = True, **kw):
	"""``shutil.copytree`` só com ``dst`` fora do projeto real (e, por omissão, debaixo de uma pasta temporária);
	``src`` pode ser o projeto real (é só lido)."""
	_verificar(dst, "copytree", temporario)
	return shutil.copytree(src, dst, **kw)
