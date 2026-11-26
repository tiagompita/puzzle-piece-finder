"""Passo 0 de ``tools.verify``: ambiente, git, vigilância e cópia do projeto (sem ``src/``: corre antes de o importar)."""
import os
import re
import subprocess
import sys
import tempfile

__all__ = ["REPO", "HOOKS_PATH", "guarda", "python_venv", "opencv_fixado", "ambiente", "git_estado", "hooks_path",
		   "vigilancia", "copiar_projeto", "apagar_copia", "IGNORAR_NA_COPIA"]

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOOKS_PATH = "tools/githooks"     # D4 (2026-11-26): core.hooksPath versionado
# A cópia leva o que as regras e as métricas leem (log, perfil, scans, pieces/*.npz, secções, mesa, overrides,
# render/placements.json); ficam de fora os ativos regeneráveis e pesados (≈ 260 de 309 MB).
IGNORAR_NA_COPIA = ("crops", "overlays", "logs", "reports", "gui", "clean", "fit", "sheets")

if REPO not in sys.path:
	sys.path.insert(0, REPO)        # ``src`` importável também fora da raiz do repositório
sys.path.insert(0, os.path.join(REPO, "tools", "diagnostico", "gui"))
import guarda  # noqa: E402  (único caminho permitido para copiar/apagar cópias do projeto)


def _norm(p: str) -> str:
	return os.path.normcase(os.path.realpath(p))


def python_venv() -> dict:
	"""``sys.executable`` tem de ser o Python do ``.venv`` do repositório (CLAUDE.md: a suite só com ``.venv``)."""
	venv = os.path.join(REPO, ".venv")
	ok = _norm(sys.executable).startswith(_norm(venv) + os.sep) or _norm(sys.prefix) == _norm(venv)
	return {"ok": bool(ok), "executavel": sys.executable, "prefixo": sys.prefix, "esperado": venv}


def opencv_fixado() -> dict:
	"""``cv2.__version__`` tem de coincidir com o ``opencv-python==X.Y.Z.B`` de ``requirements.txt`` (X.Y.Z)."""
	try:
		with open(os.path.join(REPO, "requirements.txt"), encoding="utf-8") as f:
			m = re.search(r"^opencv-python==([0-9.]+)", f.read(), re.M)
	except OSError:
		m = None
	esperado = ".".join(m.group(1).split(".")[:3]) if m else None
	try:
		import cv2
		v = cv2.__version__
	except Exception as e:  # noqa: BLE001 - sem OpenCV é uma falha do ambiente, não uma exceção
		return {"ok": False, "versao": None, "esperado": esperado, "erro": str(e)}
	return {"ok": esperado is not None and v == esperado, "versao": v, "esperado": esperado}


def _git(*args) -> str:
	r = subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True, encoding="utf-8")
	return r.stdout.strip() if r.returncode == 0 else ""


def git_estado() -> dict:
	"""``{head, status}`` (``git status --porcelain``, linhas ordenadas)."""
	st = _git("status", "--porcelain", "--untracked-files=all")
	return {"head": _git("rev-parse", "HEAD"), "status": sorted(l for l in st.splitlines() if l.strip())}


def hooks_path() -> dict:
	"""``git config core.hooksPath`` tem de ser :data:`HOOKS_PATH` (decisão 3 do planeamento, 2026-11-26)."""
	v = _git("config", "core.hooksPath")
	hook = os.path.join(REPO, *HOOKS_PATH.split("/"), "commit-msg")
	ok = v.replace("\\", "/").rstrip("/") == HOOKS_PATH
	return {"ok": bool(ok), "valor": v, "esperado": HOOKS_PATH, "hook_existe": os.path.isfile(hook),
			"ativar": f"git config core.hooksPath {HOOKS_PATH}"}


def ambiente() -> dict:
	py, cv, hp = python_venv(), opencv_fixado(), hooks_path()
	return {"ok": py["ok"] and cv["ok"] and hp["ok"], "python": py, "opencv": cv, "hooks": hp}


def vigilancia(project_dir: str) -> dict:
	"""Contagem (só leitura) de ``pieces/*.npz`` e ``overlays/*.jpg`` contra ``scans/*.json`` do projeto real
	(CLAUDE.md, «Vigilância»: as duas pastas estão no ``.gitignore``; uma contagem menor é um alarme)."""
	def n(sub, ext):
		d = os.path.join(project_dir, sub)
		return sum(1 for x in os.listdir(d) if x.lower().endswith(ext)) if os.path.isdir(d) else 0
	ns, npc, nov = n("scans", ".json"), n("pieces", ".npz"), n("overlays", ".jpg")
	return {"ok": ns > 0 and npc == ns and nov == ns, "scans": ns, "pieces": npc, "overlays": nov}


def copiar_projeto(project_dir: str) -> tuple:
	"""Cópia leve do projeto numa pasta temporária nova (``guarda.copytree``). Devolve ``(raiz_temporaria, copia)``."""
	base = os.environ.get("PPF_SCRATCH") or None
	if base:
		os.makedirs(base, exist_ok=True)
	raiz = tempfile.mkdtemp(prefix="ppf_verify_", dir=base)
	dst = os.path.join(raiz, os.path.basename(os.path.normpath(project_dir)))
	guarda.copytree(project_dir, dst, ignore=_ignorar)
	return raiz, dst


def _ignorar(d, nomes):
	"""``shutil.copytree(ignore=)``: :data:`IGNORAR_NA_COPIA` (na raiz: crops, overlays, logs, reports; em ``render``:
	gui, clean, fit, sheets)."""
	b = os.path.basename(os.path.normpath(d))
	if b == "render":
		return [n for n in nomes if n in ("gui", "clean", "fit", "sheets")]
	return [n for n in nomes if n in ("crops", "overlays", "logs", "reports") and os.path.isdir(os.path.join(d, n))]


def apagar_copia(raiz: str) -> None:
	guarda.rmtree(raiz)
