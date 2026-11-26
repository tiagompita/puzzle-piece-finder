"""Passos 1–3 de ``tools.verify`` (``tools/verify/regressao.py``, 2026-11-26, «fecho»).

Sintéticos (rápidos): a comparação com a baseline apanha cada regressão e respeita as tolerâncias fixas; o modo rápido
só compara o que mediu; a regra das folhas do modo rápido; a métrica de contorno é exata em contornos iguais e vê uma
mordida local; o verify não importa de ``tools/diagnostico/`` (ajuste 4 do Tiago). Com o projeto real (``slow``): a
baseline versionada tem o bloco ``regressao`` e os critérios absolutos (E-sym, E-real-2, quadrados) passam nela."""
import ast
import copy
import json
import os

import numpy as np
import pytest

from tools.verify import __main__ as VM
from tools.verify import regressao as RG

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIM = RG.LIMIARES_REGRESSAO


def _base():
	return {
		"ficheiros": {"a.jpg": "h1"},
		"folhas": {"S1": {"n_pecas": 10, "n_guardadas": 10}, "S2": {"n_pecas": 5, "n_guardadas": 5}},
		"pecas": {"P1": {"sid": "S1", "existe": True, "iou": 1.0, "d_max_mm": 0.0, "cls": "FTBT",
						 "cordas_mm": [18.0, 18.1, 18.2, 18.3], "n_f": 1, "f_esperado": 1},
				  "P2": {"sid": "S2", "existe": True, "iou": 0.99, "d_max_mm": 0.2, "cls": "TBTB",
						 "cordas_mm": [18.0, 18.0, 18.0, 18.0], "n_f": 0}},
		"esym": {"contagens": {"A1": {"n": 20, "clusters": 0}}, "twin_mediana_mm": 0.383,
				 "top1": {"A1->B2": 20, "A2->B2": 20, "B2->A2": 20}},
		"ereal2": {"propostas": {"pos": {"aceite": 15}, "BExceu": {"aceite": 1}}, "aceite_negativos": []},
		"quadrados": {"ligacoes_ok": 40, "ligacoes": 40, "quadrados_ok": 10, "quadrados": 10, "falhas": []},
		"molde": {"n": 3, "top1": 2, "certas": ["P1", "P2"], "alta_errada": 0, "alta_errada_ids": [],
				  "falhas": ["P3 (1, 2): top-1 P9 (media)"]},
	}


def _cmp(a, b=None):
	return RG.comparar(a, b or _base(), LIM)


def test_igual_nao_e_regressao():
	assert _cmp(_base()) == []


def test_tolerancias_fixas_respeitadas():
	a = _base()
	a["pecas"]["P2"]["d_max_mm"] = 0.2 + 0.3                 # no limite de +0,3 mm
	a["pecas"]["P1"]["cordas_mm"] = [18.3, 17.8, 18.2, 18.3]  # |Δ| ≤ 0,3 mm
	a["pecas"]["P2"]["iou"] = 0.995                           # IoU que sobe não é regressão
	a["esym"]["twin_mediana_mm"] = 0.5
	assert _cmp(a) == []


@pytest.mark.parametrize("muda, texto", [
	(lambda a: a["folhas"]["S1"].update(n_pecas=9), "S1: 9 peças segmentadas, 10 no projeto"),
	(lambda a: a["pecas"]["P2"].update(d_max_mm=0.51), "P2: contorno d_max"),
	(lambda a: a["pecas"]["P2"].update(iou=0.989), "P2: IoU"),
	(lambda a: a["pecas"]["P1"].update(cls="FTTT"), "P1: cls FTBT -> FTTT"),
	(lambda a: a["pecas"]["P1"].update(cordas_mm=[18.0, 18.1, 18.2, 18.61]), "P1: corda muda 0.310"),
	(lambda a: a["pecas"]["P1"].update(n_f=0), "P1: 0 lados F, a célula pede 1"),
	(lambda a: a["pecas"]["P1"].update(sem_par=True), "P1: sem peça correspondente"),
	(lambda a: a["esym"].update(twin_mediana_mm=0.51), "E-sym: mediana gémea"),
	(lambda a: a["esym"]["top1"].update({"A2->B2": 19}), "E-sym: top-1 A2->B2 19/20"),
	(lambda a: a["esym"].update(erro="contagem diferente de 20"), "E-sym: contagem"),
	(lambda a: a["ereal2"].update(aceite_negativos=["x|y"]), "E-real-2: aceite em pares negativos"),
	(lambda a: a["ereal2"]["propostas"]["pos"].update(aceite=14), "E-real-2: pares gémeos aceites 15 -> 14"),
	(lambda a: a["quadrados"].update(ligacoes_ok=39, quadrados_ok=9, falhas=["q"]), "quadrados: ligações 40 -> 39"),
	(lambda a: a["molde"].update(certas=["P1"], top1=1, falhas=["P2 (1, 3): top-1 P7 (media)", "P3 (1, 2): x"]),
	 "molde (leave-one-out): top-1 perdido em ['P2']"),
	(lambda a: a["molde"].update(alta_errada=1, alta_errada_ids=["P3"]), "«alta» errada nova em ['P3']"),
])
def test_cada_regressao_e_apanhada(muda, texto):
	a = _base()
	muda(a)
	reg = _cmp(a)
	assert any(texto in t for g, t in reg), reg
	assert all(g == "baseline" for g, _ in reg)          # código 5: «métrica pior do que a baseline»


def test_ficheiro_do_passo_3_alterado_e_golden():
	a = _base()
	a["ficheiros"] = {"a.jpg": "outro"}
	assert ("golden", "ficheiro do passo 3 alterado: a.jpg") in _cmp(a)


def test_modo_rapido_so_compara_o_que_mediu():
	a = _base()
	del a["folhas"]["S2"], a["pecas"]["P2"]
	a["molde"] = None
	assert _cmp(a) == []


def test_molde_peca_que_deixou_de_ser_medida_nao_conta():
	a = _base()
	a["molde"].update(n=1, top1=1, certas=["P1"], falhas=[])      # P2 sem 2 vizinhas agora: não é regressão
	assert _cmp(a) == []


def test_codigo_de_saida_das_metricas_e_5():
	assert VM.codigo_saida([("baseline", "x")]) == 5
	assert VM.codigo_saida([("golden", "x"), ("baseline", "y")]) == 3


def test_contorno_igual_e_exato_e_mordida_local_aparece():
	t = np.linspace(0, 2 * np.pi, 400, endpoint=False)
	c = np.c_[200 + 100 * np.cos(t), 200 + 100 * np.sin(t)]
	assert RG._contorno_vs(c, c.copy(), 0.0847) == {"iou": 1.0, "d_max_mm": 0.0}
	m = c.copy()
	m[:20] = m[:20] - 0.25 * (m[:20] - 200)                   # mordida local de ≈ 25 px num arco
	r = RG._contorno_vs(c, m, 0.0847)
	assert r["iou"] > 0.97 and r["d_max_mm"] > 1.5            # o IoU quase não vê; a distância máxima vê


def test_folhas_do_modo_rapido_seguem_a_regra():
	class Pr:
		class model:
			scans = {"S1": {"file": RG.ESYM_SCANS["A1"]}, "S2": {"file": "b.jpg"}, "S3": {"file": "c.jpg"},
					 "S4": {"file": "d.jpg"}, "S5": {"file": "e.jpg"}}
	man = {"pecas": {f"P{i}": {"scan_id": s} for i, s in enumerate(["S1"] + ["S2"] * 3 + ["S3"] * 5 + ["S4"] * 3 + ["S5"])}}
	assert RG.folhas_do_golden(Pr, man) == ["S1", "S2", "S3", "S4", "S5"]
	assert RG.folhas_do_golden(Pr, man, rapido=True) == ["S1", "S2", "S3", "S4"]   # E-sym + 3 com mais peças (S2 < S4 no empate)


def test_verify_nao_importa_de_tools_diagnostico():
	"""Ajuste 4 (2026-11-26): a lógica do E-sym e do E-real-2 vive em ``tools/verify/regressao.py`` (só ``guarda`` é
	lido de ``tools/diagnostico/gui``, pelo ``ambiente``, como único caminho para copiar e apagar cópias)."""
	maus = []
	d = os.path.join(REPO, "tools", "verify")
	for nome in sorted(os.listdir(d)):
		if not nome.endswith(".py"):
			continue
		src = open(os.path.join(d, nome), encoding="utf-8").read()
		for no in ast.walk(ast.parse(src)):
			mods = []
			if isinstance(no, ast.Import):
				mods = [a.name for a in no.names]
			elif isinstance(no, ast.ImportFrom):
				mods = [no.module or ""]
			maus += [(nome, m) for m in mods if "diagnostico" in m or m in ("segcache", "esym", "ereal2", "ereal2_fixture",
																			 "shapelib", "loose")]
		assert "spec_from_file_location" not in src, nome
	assert maus == [], maus


def test_limiares_versionados_tem_o_bloco_regressao_igual_ao_codigo():
	with open(VM.LIMIARES, encoding="utf-8") as f:
		lim = json.load(f)
	assert lim["regressao"] == json.loads(json.dumps(RG.LIMIARES_REGRESSAO))
	assert lim["regressao"]["contorno_d_max_delta_mm"]["valor"] == 0.3
	assert lim["regressao"]["esym_twin_mediana_mm"]["valor"] == 0.5
	assert lim["regressao"]["ereal2_aceite_negativos"]["valor"] == 0


def test_rapido_nao_congela():
	with pytest.raises(SystemExit):
		VM.main(["--rapido", "--congelar-baseline", "--porque", "x"])


@pytest.mark.slow
def test_baseline_versionada_tem_os_passos_1_3_e_passa_os_criterios_absolutos():
	with open(VM.BASELINE, encoding="utf-8") as f:
		base = json.load(f)
	r = base.get("regressao")
	assert r is not None and r["modo"] == "completo"
	assert RG.comparar(copy.deepcopy(r), r, RG.LIMIARES_REGRESSAO) == []
	assert all(v["n_pecas"] == v["n_guardadas"] for v in r["folhas"].values())
	assert r["esym"]["twin_mediana_mm"] <= 0.5 and min(r["esym"]["top1"].values()) == 20
	assert r["ereal2"]["aceite_negativos"] == []
	assert r["quadrados"]["quadrados_ok"] == r["quadrados"]["quadrados"] == 10
	man = json.load(open(os.path.join(REPO, "tests", "golden", "manifesto.json"), encoding="utf-8"))
	assert set(r["pecas"]) | set(r["excluidas_manual"]) == set(man["pecas"])
