"""A1 (2026-11-25): ``GET /api/grupos`` traz, por grupo, os reports abertos das pecas do grupo (``reports_abertos``) e
``tem_report``; ``/api/grupos`` nao tem cache no servidor, por isso uma escrita em ``reports.jsonl`` (``POST /api/report``,
``reports.set_state``) reflecte-se no pedido seguinte; a escrita emite ``suspeitas_changed`` (a GUI nova recarrega os grupos nele)."""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from src import reports as RP  # noqa: E402
from test_server_grupos import _cand, _env  # noqa: E402


@pytest.fixture
def env(tmp_path):
	return _env(tmp_path, cand1=_cand((2, 4)), cand2=_cand((3, 3), margin=1.0))


def _by(cl):
	return {g["id"]: g for g in cl.get("/api/grupos").json()["grupos"]}


def test_sem_reports_tem_report_falso(env):
	gui, cl, ids = env
	for g in _by(cl).values():
		assert g["tem_report"] is False and g["reports_abertos"] == []


def test_report_aberto_da_peca_marca_o_grupo(env):
	gui, cl, ids = env
	r = cl.post("/api/report", json={"piece": ids["Z"], "cell": None, "tipo": "mal_lida", "texto": "torta", "vista": "novo/grupo"})
	assert r.status_code == 200, r.text
	rid = r.json()["id"]
	g = _by(cl)
	assert g[ids["G2"]]["tem_report"] is True
	assert g[ids["G2"]]["reports_abertos"] == [{"id": rid, "tipo": "mal_lida", "texto": "torta", "piece": ids["Z"]}]
	assert g[ids["G1"]]["tem_report"] is False and g[ids["G1"]]["reports_abertos"] == []


def test_fechar_pela_cli_limpa_no_pedido_seguinte(env):
	gui, cl, ids = env
	rid = cl.post("/api/report", json={"piece": ids["X"], "tipo": "outro", "texto": ""}).json()["id"]
	assert _by(cl)[ids["G1"]]["tem_report"] is True
	RP.set_state(gui.pr, rid, "close", "feito")
	g = _by(cl)[ids["G1"]]
	assert g["tem_report"] is False and g["reports_abertos"] == []


def test_a_escrita_do_report_emite_suspeitas_changed(env):
	gui, cl, ids = env
	seq0 = gui.seq
	cl.post("/api/report", json={"piece": ids["Y"], "tipo": "outro", "texto": ""})
	assert "suspeitas_changed" in [n for _, n, _ in gui.events_after(seq0)]
