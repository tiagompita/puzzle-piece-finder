"""``python -m tools.verify``: manifesto do golden, comparação com a baseline, códigos de saída e passo 0 (sintético,
rápido; a corrida inteira sobre a cópia do projeto fica para o comando)."""
import copy
import hashlib
import json
import os

import pytest

from tools.verify import __main__ as VM
from tools.verify import ambiente as AMB
from tools.verify import golden as GD
from tools.verify import invariantes as INV
from tools.verify import metricas as MT


def _sha(b: bytes) -> str:
	return hashlib.sha256(b).hexdigest()


@pytest.fixture
def proj(tmp_path):
	linhas = [b'{"a": 1}', b'{"b": 2}']
	(tmp_path / "overrides.jsonl").write_bytes(b"\n".join(linhas) + b"\n")
	man = {"scans": {}, "quadrados": {"ficheiro": GD.QUADRADOS,
									  "sha256": GD.sha256_ficheiro(os.path.join(AMB.REPO, GD.QUADRADOS))},
		   "overrides": {"ficheiro": "overrides.jsonl", "linhas": [_sha(l) for l in linhas]}}
	return tmp_path, man


def test_golden_igual(proj):
	d, man = proj
	r = GD.verificar(man, str(d))
	assert r["ok"] and r["linhas_novas"] == 0


def test_golden_linha_nova_nao_falha(proj):
	d, man = proj
	with open(d / "overrides.jsonl", "ab") as f:
		f.write(b'{"c": 3}\n')
	r = GD.verificar(man, str(d))
	assert r["ok"] and r["linhas_novas"] == 1


def test_golden_linha_alterada_falha(proj):
	d, man = proj
	(d / "overrides.jsonl").write_bytes(b'{"a": 1}\n{"b": 22}\n')
	r = GD.verificar(man, str(d))
	assert not r["ok"] and "linha 2 alterada" in r["diferencas"][0]


def test_golden_linha_removida_falha(proj):
	d, man = proj
	(d / "overrides.jsonl").write_bytes(b'{"a": 1}\n')
	assert not GD.verificar(man, str(d))["ok"]


def test_golden_scan_alterado_falha(proj, tmp_path):
	d, man = proj
	man = copy.deepcopy(man)
	man["scans"]["images/nao/existe.jpg"] = "0" * 64
	r = GD.verificar(man, str(d))
	assert not r["ok"] and "scan em falta" in r["diferencas"][0]


def test_golden_sem_manifesto_falha(tmp_path):
	assert not GD.verificar(None, str(tmp_path))["ok"]


def test_manifesto_e_baseline_versionados_e_coerentes():
	man = GD.ler()
	assert man is not None, "tests/golden/manifesto.json em falta"
	assert man["contagens"]["borda"] == len([p for p in man["pecas"].values() if "borda" in p["papeis"]])
	assert set(man["quadrados"]["grupos"]) == set(range(1, 11))
	with open(VM.BASELINE, encoding="utf-8") as f:
		base = json.load(f)
	assert base["manifesto_sha256"] == GD.sha256_ficheiro(GD.MANIFESTO), \
		"manifesto mudou sem voltar a congelar a baseline (--congelar-baseline --porque)"
	assert set(base["metricas"]["pecas"]) == set(man["pecas"])
	with open(VM.LIMIARES, encoding="utf-8") as f:
		assert json.load(f)["corda_delta_mm"]["valor"] == 0.3


def _base():
	return {"pecas": {"P1": {"existe": True, "estado": "colocada", "celula": [1, 1], "cls": "FFTB",
							 "cordas_mm": [18.0, 18.1, 18.2, 18.3]}},
			"manual": {"P1": {"aresta_fora_do_indice_mm2": 0.5, "papel_coroa_pct": 1.0}},
			"simetria": {"pares": {}, "acima_do_limiar": ["P8|P9"], "limiar_mm": 1.75},
			"suspeitas": ["P8|recorte"]}


MAN = {"pecas": {"P1": {"celula": [1, 1]}}}


def test_comparar_igual():
	assert MT.comparar(_base(), _base(), MT.LIMIARES_INICIAIS, MAN) == []


@pytest.mark.parametrize("mexe, texto", [
	(lambda a: a["pecas"]["P1"].update(cordas_mm=[18.0, 18.1, 18.2, 18.7]), "corda muda"),
	(lambda a: a["pecas"]["P1"].update(cls="FFTT"), "cls"),
	(lambda a: a["pecas"]["P1"].update(celula=[1, 2]), "fora da célula"),
	(lambda a: a["pecas"].pop("P1"), "desapareceu"),
	(lambda a: a["manual"].pop("P1"), "deixou de ser medido"),
	(lambda a: a["simetria"]["acima_do_limiar"].append("P1|P2"), "simetria"),
	(lambda a: a["suspeitas"].append("P1|melhor_rotacao"), "suspeitas novas"),
])
def test_comparar_apanha_regressao(mexe, texto):
	a = _base()
	mexe(a)
	reg = MT.comparar(a, _base(), MT.LIMIARES_INICIAIS, MAN)
	assert len(reg) == 1 and texto in reg[0], reg


def test_comparar_tolera_dentro_do_limiar():
	a = _base()
	a["pecas"]["P1"]["cordas_mm"][3] = 18.59          # 0,29 mm < 0,3
	a["manual"]["P1"]["aresta_fora_do_indice_mm2"] = 0.54
	a["suspeitas"] = []                               # uma suspeita que desaparece não falha
	assert MT.comparar(a, _base(), MT.LIMIARES_INICIAIS, MAN) == []


def test_comparar_aresta_fora_ja_nao_e_baseline():
	"""4.1 (c) = A (Tiago, 2026-11-26): a aresta fora do índice deixou de ser «não piora» contra a baseline (C); é a
	regra absoluta ``invariantes.manual_aresta_no_indice`` (0 px). O valor por peça fica nas métricas, informativo."""
	a = _base()
	a["manual"]["P1"]["aresta_fora_do_indice_mm2"] = 0.6
	assert MT.comparar(a, _base(), MT.LIMIARES_INICIAIS, MAN) == []
	assert "manual_aresta_no_indice" in INV.REGRAS


def test_codigo_saida_ordem():
	assert VM.codigo_saida([]) == 0
	assert VM.codigo_saida([("baseline", "x"), ("regras", "y")]) == 4
	assert VM.codigo_saida([("baseline", "x"), ("ambiente", "y"), ("golden", "z")]) == 2
	assert VM.codigo_saida([("arvore", "x"), ("baseline", "y")]) == 6


def test_vigilancia_conta_contra_scans(tmp_path):
	for sub in ("scans", "pieces", "overlays"):
		(tmp_path / sub).mkdir()
	for i in range(3):
		(tmp_path / "scans" / f"S{i}.json").write_text("{}")
		(tmp_path / "pieces" / f"S{i}.npz").write_bytes(b"")
		(tmp_path / "overlays" / f"S{i}.jpg").write_bytes(b"")
	assert AMB.vigilancia(str(tmp_path)) == {"ok": True, "scans": 3, "pieces": 3, "overlays": 3}
	os.remove(tmp_path / "overlays" / "S1.jpg")
	assert not AMB.vigilancia(str(tmp_path))["ok"]


def test_hooks_path_lido_do_git(monkeypatch):
	monkeypatch.setattr(AMB, "_git", lambda *a: "" if a[:2] == ("config", "core.hooksPath") else "x")
	r = AMB.hooks_path()
	assert not r["ok"] and r["ativar"] == "git config core.hooksPath tools/githooks"
	monkeypatch.setattr(AMB, "_git", lambda *a: "tools/githooks")
	assert AMB.hooks_path()["ok"]


def test_copia_recusa_o_projeto_real():
	with pytest.raises(AMB.guarda.Recusado):
		AMB.apagar_copia(os.path.join(AMB.REPO, "projects", "alpes"))


def test_git_status_mantem_o_espaco_inicial_da_primeira_linha(monkeypatch):
	"""``git status --porcelain`` começa por « M ficheiro» numa modificação não preparada: um ``strip()`` da saída
	inteira comia o espaço da 1.ª linha e o filtro dos ficheiros escritos por ``--congelar-baseline`` deixava de a
	reconhecer (falha «arvore» na congelação de 2026-11-26)."""
	import subprocess

	class R:
		returncode = 0
		stdout = " M docs/decisoes.md\n M tests/golden/baseline.json\n"
	monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
	st = AMB.git_estado()["status"]
	assert st == [" M docs/decisoes.md", " M tests/golden/baseline.json"]
	assert all(l[3:].endswith(("docs/decisoes.md", "tests/golden/baseline.json")) for l in st)
