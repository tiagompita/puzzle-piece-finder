"""Guarda das medições (``tools/diagnostico/gui/guarda.py``): nenhum ``rmtree``/``copytree`` sobre o projeto real.
Nunca toca em ``projects/``: tudo o que se apaga vive em ``tmp_path``; as recusas verificam-se antes de qualquer escrita."""
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools", "diagnostico", "gui"))
import guarda  # noqa: E402

REAL = os.path.join(ROOT, "projects", "alpes")


def _contagem(p):
	return sum(len(f) for _, _, f in os.walk(p))


def test_protegidos_inclui_o_projeto_real():
	prot = guarda.protegidos()
	assert os.path.normcase(os.path.realpath(REAL)) in prot
	assert os.path.normcase(os.path.realpath(os.path.join(ROOT, "projects"))) in prot


@pytest.mark.parametrize("rel", [
	os.path.join("projects", "alpes"),
	os.path.join("projects", "alpes", "pieces"),
	os.path.join("projects", "alpes", "overlays"),
	os.path.join("projects", "alpes", "pieces", ".."),
	os.path.join("projects", "alpes", "..", "alpes", "render"),
	"projects",
	".",
])
def test_rmtree_recusa_o_real_dentro_ou_acima(rel):
	alvo = os.path.join(ROOT, rel)
	antes = _contagem(os.path.join(ROOT, "projects")) if os.path.isdir(os.path.join(ROOT, "projects")) else 0
	for temporario in (True, False):
		with pytest.raises(guarda.Recusado):
			guarda.rmtree(alvo, temporario=temporario)
		with pytest.raises(guarda.Recusado):
			guarda.rmtree(alvo, temporario=temporario, ignore_errors=True)
	if antes:
		assert _contagem(os.path.join(ROOT, "projects")) == antes


def test_copytree_recusa_destino_real(tmp_path):
	origem = tmp_path / "o"
	origem.mkdir()
	(origem / "a.txt").write_text("x")
	for dst in (REAL, os.path.join(REAL, "pieces"), os.path.join(ROOT, "projects", "copia")):
		with pytest.raises(guarda.Recusado):
			guarda.copytree(str(origem), dst, temporario=False)
	assert not os.path.exists(os.path.join(ROOT, "projects", "copia"))


def test_origem_real_pode_ser_lida(tmp_path):
	"""Copiar O projeto real para um temporário é o uso previsto: só se lê."""
	if not os.path.isdir(os.path.join(REAL, "scans")):
		pytest.skip("sem projects/alpes")
	dst = tmp_path / "copia"
	guarda.copytree(os.path.join(REAL, "scans"), str(dst))
	assert _contagem(str(dst)) == _contagem(os.path.join(REAL, "scans"))
	guarda.rmtree(str(dst))
	assert not dst.exists()


def test_temporario_apaga_e_inexistente_e_aceite(tmp_path):
	d = tmp_path / "x" / "proj"
	d.mkdir(parents=True)
	(d / "f").write_text("1")
	guarda.rmtree(str(d))
	assert not d.exists()
	guarda.rmtree(str(d))                                      # já não existe: sem erro


def test_fora_do_temporario_recusado_por_omissao(tmp_path, monkeypatch):
	"""Uma pasta do repositório que não é o projeto real só se apaga com ``temporario=False``."""
	d = os.path.join(ROOT, "tests", "_guarda_nao_existe_")
	with pytest.raises(guarda.Recusado):
		guarda.rmtree(d)
	with pytest.raises(guarda.Recusado):
		guarda.copytree(str(tmp_path), d)
	assert not os.path.exists(d)
	monkeypatch.setenv("PPF_SCRATCH", os.path.join(ROOT, "tests"))
	guarda.rmtree(d)                                           # PPF_SCRATCH autoriza (e não existe)


def test_ppf_protegidos_acrescenta(tmp_path, monkeypatch):
	d = tmp_path / "meu"
	d.mkdir()
	guarda.rmtree(str(d / "nada"))
	monkeypatch.setenv("PPF_PROTEGIDOS", str(d))
	with pytest.raises(guarda.Recusado):
		guarda.rmtree(str(d))


def _junction(link, alvo):
	r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(alvo)], capture_output=True, text=True)
	return r.returncode == 0


def _ligacao(link, alvo):
	try:
		os.symlink(alvo, link, target_is_directory=True)
		return True
	except (OSError, NotImplementedError):
		return os.name == "nt" and _junction(link, alvo)


def test_ligacao_para_o_projeto_real_recusada(tmp_path):
	"""Uma «cópia» com uma junção/ligação para o projeto real: nem apagar a ligação em cadeia, nem passar por ela."""
	if not os.path.isdir(REAL):
		pytest.skip("sem projects/alpes")
	copia = tmp_path / "copia"
	copia.mkdir()
	if not _ligacao(str(copia / "pieces"), REAL):
		pytest.skip("o sistema não deixa criar ligações")
	antes = _contagem(REAL)
	with pytest.raises(guarda.Recusado):
		guarda.rmtree(str(copia / "pieces"))                   # o caminho resolve para o projeto real
	with pytest.raises(guarda.Recusado):
		guarda.rmtree(str(copia))                              # a pasta contém uma ligação para o projeto real
	assert _contagem(REAL) == antes
	assert (copia / "pieces").exists()
	os.rmdir(str(copia / "pieces"))                            # remove só a ligação (nunca o conteúdo)
	assert _contagem(REAL) == antes
