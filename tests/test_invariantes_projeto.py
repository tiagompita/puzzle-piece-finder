"""Regras absolutas sobre o projeto vivo (4.1 b/d e 4.3 do levantamento de 2026-11-26; decisão 2 do planeamento).

Correm sobre uma CÓPIA leve de ``projects/alpes`` (``tools.verify.ambiente.copiar_projeto``, feita e apagada com
``tools/diagnostico/gui/guarda.py``), depois do arranque simulado (``invariantes.arranque``: o ``rebuild_stale`` que o
servidor corre ao arrancar); nada é escrito no projeto real. Sem ``projects/alpes/pieces`` (checkout sem os
ativos, que estão no ``.gitignore``) são saltados. Cada regra tem também um teste que a faz falhar numa perturbação
em memória (o teste tem de conseguir falhar)."""
import os

import numpy as np
import pytest

from tools.verify import ambiente as AMB
from tools.verify import invariantes as INV

PROJ = os.path.join(AMB.REPO, "projects", "alpes")

pytestmark = pytest.mark.skipif(not os.path.isdir(os.path.join(PROJ, "pieces")),
								reason="projects/alpes sem pieces/ (ativos fora do git)")


@pytest.fixture(scope="module")
def copia():
	from src.state import Project
	raiz, dst = AMB.copiar_projeto(PROJ)
	try:
		arr = INV.arranque(Project.open(dst))        # o projeto como o programa o vê depois de arrancar (como o verify)
		assert not arr["erros"] and arr["restantes"] == 0, arr
		yield dst
	finally:
		AMB.apagar_copia(raiz)


@pytest.fixture
def pr(copia):
	from src.state import Project
	return Project.open(copia)


@pytest.fixture(scope="module")
def manuais(copia):
	from src.state import Project
	p = Project.open(copia)
	return p, INV._manuais(p)


# ------------------------------------------------------------------ 4.3 coerência do tabuleiro (passam hoje)
def test_check_invariants(pr):
	r = INV.estado(pr)
	assert r["n"] == 0, r["violacoes"][:5]


def test_mesma_celula(pr):
	r = INV.mesma_celula(pr)
	assert r["n"] == 0, r["violacoes"][:5]
	assert r["celulas_com_peca"] > 0


def test_borda_completa(pr):
	r = INV.borda_completa(pr)
	assert r["n"] == 0, r["violacoes"][:5]
	assert r["celulas_borda"] == 2 * (pr.profile.rows + pr.profile.cols) - 4


def test_f_por_celula(pr):
	r = INV.f_por_celula(pr)
	assert r["n"] == 0, r["violacoes"][:5]


def test_grupos_sem_sobreposicao(pr):
	r = INV.grupos_sobrepostos(pr)
	assert r["n"] == 0, r["violacoes"][:5]


# ------------------------------------------------------------------ 4.1 contornos manuais (b), (c) e (d)
def test_manual_indice_igual_ao_da_linha(manuais):
	p, man = manuais
	r = INV.manual_indice_da_linha(p, man)
	assert r["manuais"] > 0
	assert r["n"] == 0, r["violacoes"]


def test_manual_aresta_dentro_do_indice(manuais):
	"""4.1 (c), opção A (Tiago, 2026-11-26; regra D5): a aresta pintada fica inteira dentro do índice, 0 px fora.
	Substitui o «não piora» contra a baseline (C) que estava em ``tools.verify.metricas``."""
	p, man = manuais
	r = INV.manual_aresta_no_indice(p, man)
	assert r["com_aresta"] > 0
	assert r["n"] == 0, r["violacoes"]


def test_manual_indice_na_banda(manuais):
	p, man = manuais
	r = INV.manual_indice_na_banda(p, man)
	assert r["com_aresta"] > 0
	assert r["n"] == 0, r["violacoes"]


# ------------------------------------------------------------------ cada regra apanha uma violação
def test_estado_apanha_tabuleiro_diferente_do_log(pr):
	lc = next(lc for lc, c in pr.board.iter_cells() if c["estado"] == "colocada")
	pr.board[lc]["peca_id"] = "P9999"
	assert INV.estado(pr)["n"] > 0


def test_mesma_celula_apanha_duas_pecas(pr):
	a, b = [p for p in sorted(pr.pieces.values(), key=lambda q: q.id) if p.estado == "colocada"][:2]
	b.celula = a.celula
	r = INV.mesma_celula(pr)
	assert r["n"] == 1 and sorted(r["violacoes"][0]["pecas"]) == sorted([a.id, b.id])


def test_borda_completa_apanha_celula_vazia(pr):
	lc = next(lc for lc, _ in pr.board.iter_cells() if pr.profile.is_border(*lc))
	pr.board[lc]["estado"] = "vazia"
	pr.board[lc]["peca_id"] = None
	assert INV.borda_completa(pr)["n"] >= 1


def test_f_por_celula_apanha_classe_errada(pr):
	p = next(p for p in pr.pieces.values() if p.estado == "colocada" and p.celula is not None
			 and not pr.profile.is_border(*p.celula))
	p.cls = "FTBT"
	r = INV.f_por_celula(pr)
	assert r["n"] == 1 and r["violacoes"][0]["peca"] == p.id


def test_grupos_apanha_dois_grupos_na_mesma_celula(pr, monkeypatch):
	from src import mesa
	gids = [g for g in sorted(pr.sections) if mesa.is_loose(pr, g)][:2]
	if len(gids) < 2:
		pytest.skip("menos de 2 grupos soltos")
	livre = next(lc for lc, c in pr.board.iter_cells() if c["estado"] == "vazia" and 10 < lc[0] < 30 and 10 < lc[1] < 50)
	pos = {g: {"l0": livre[0], "c0": livre[1], "rot": 0} for g in gids}
	monkeypatch.setattr(mesa, "effective_positions", lambda project, index=None: dict(pos))
	r = INV.grupos_sobrepostos(pr)
	assert any(v.get("motivo") == "dois grupos" for v in r["violacoes"]) or r["n"] > 0


def test_manual_da_linha_apanha_contorno_guardado_mudado(manuais):
	p, man = manuais
	pid, o, rgb, mm, g, mi, ma = man[0]
	mexido = [(pid, o, rgb, mm, g + np.array([1, 0], np.int32), mi, ma)] + list(man[1:])
	r = INV.manual_indice_da_linha(p, mexido)
	assert [v["peca"] for v in r["violacoes"]] == [pid]


def test_manual_na_banda_apanha_indice_longe_da_aresta(manuais):
	p, man = manuais
	i = next(k for k, m in enumerate(man) if m[6] is not None)
	pid, o, rgb, mm, g, mi, ma = man[i]
	tudo = np.ones_like(mi)
	mexido = list(man)
	mexido[i] = (pid, o, rgb, mm, g, tudo, ma)
	r = INV.manual_indice_na_banda(p, mexido)
	assert [v["peca"] for v in r["violacoes"]] == [pid]


def test_manual_aresta_apanha_um_pixel_fora_do_indice(manuais):
	p, man = manuais
	i = next(k for k, m in enumerate(man) if m[6] is not None)
	pid, o, rgb, mm, g, mi, ma = man[i]
	ys, xs = np.nonzero(ma)
	k = int(np.argmin(xs))
	mexido = list(man)
	mi2 = mi.copy()
	mi2[ys[k], xs[k]] = False                                            # um píxel da aresta fora do índice
	mexido[i] = (pid, o, rgb, mm, g, mi2, ma)
	r = INV.manual_aresta_no_indice(p, mexido)
	assert [v["peca"] for v in r["violacoes"]] == [pid] and r["violacoes"][0]["aresta_fora_px"] >= 1
