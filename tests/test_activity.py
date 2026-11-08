"""Registo de atividade (:mod:`src.activity`): ficheiro por dia (``logs/servidor-AAAAMMDD.log``, muda com a data),
anel em memória com callback (SSE), tipos / níveis no formato, ``timed``, ``Throttle`` e a regra dos pedidos lentos
(nada abaixo de 1 s). Também o caminho do servidor: ``Gui.log`` por omissão vai para o logger; ``/api/atividade``."""

import datetime as _dt
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src import activity as A  # noqa: E402


@pytest.fixture(autouse=True)
def _clean():
	A.teardown()
	yield
	A.teardown()


def _rec(msg, tipo="evento", level=logging.INFO, when=None):
	r = logging.LogRecord(f"{A.LOGGER}.{tipo}", level, __file__, 1, msg, None, None)
	if when is not None:
		r.created = when.timestamp()
	return r


def test_daily_file_rotates_with_the_record_date(tmp_path):
	hd = A.DailyFileHandler(str(tmp_path / "logs"))
	d1, d2 = _dt.datetime(2026, 11, 8, 10, 0, 0), _dt.datetime(2026, 11, 9, 0, 0, 1)
	hd.emit(_rec("placed P0001 (1,1) origem gemeo", when=d1))
	hd.emit(_rec("aviso qualquer", tipo="buracos", level=logging.WARNING, when=d1))
	hd.emit(_rec("dia seguinte", when=d2))
	hd.close()
	f1, f2 = tmp_path / "logs" / "servidor-20261108.log", tmp_path / "logs" / "servidor-20261109.log"
	assert f1.exists() and f2.exists()
	l1 = f1.read_text(encoding="utf-8").splitlines()
	assert len(l1) == 2 and l1[0].startswith("10:00:00 info  evento    placed P0001") and l1[1].startswith("10:00:00 aviso buracos   aviso qualquer")
	assert f2.read_text(encoding="utf-8").splitlines() == ["00:00:01 info  evento    dia seguinte"]
	# append, never truncate
	hd2 = A.DailyFileHandler(str(tmp_path / "logs"))
	hd2.emit(_rec("mais uma", when=d1))
	hd2.close()
	assert len(f1.read_text(encoding="utf-8").splitlines()) == 3


def test_ring_keeps_last_n_and_calls_back():
	seen = []
	ring = A.RingHandler(n=3, callback=seen.append)
	for k in range(5):
		ring.emit(_rec(f"linha {k}", tipo="consulta" if k % 2 else "cache"))
	recs = ring.last()
	assert [r["msg"] for r in recs] == ["linha 2", "linha 3", "linha 4"] and recs[0]["seq"] == 3 and recs[-1]["seq"] == 5
	assert recs[0]["tipo"] == "cache" and recs[1]["tipo"] == "consulta" and recs[0]["nivel"] == "info" and len(recs[0]["t"]) == 19
	assert [r["seq"] for r in ring.after(3)] == [4, 5] and len(seen) == 5 and seen[-1]["seq"] == 5


def test_setup_routes_to_console_file_and_ring(tmp_path, capsys):
	ring = A.RingHandler()
	A.setup(str(tmp_path), console=True, ring=ring, stream=sys.stdout)
	A.get("arranque").info("tabuleiro pronto (1,2 s)")
	A.get("pedido").warning("pedido lento GET /x 12,0 s")
	A.get("erro").error("ERRO: qualquer")
	out = capsys.readouterr().out.splitlines()
	assert len(out) == 3 and " info  arranque  tabuleiro pronto" in out[0] and " aviso pedido    pedido lento" in out[1] and " erro  erro      ERRO" in out[2]
	today = _dt.date.today()
	fp = tmp_path / "logs" / f"servidor-{today:%Y%m%d}.log"
	A.teardown()
	assert fp.exists() and len(fp.read_text(encoding="utf-8").splitlines()) == 3
	assert [r["nivel"] for r in ring.last()] == ["info", "aviso", "erro"] and ring.last()[0]["tipo"] == "arranque"
	# without setup: silent (no lastResort noise for info)
	A.get("evento").info("silêncio")
	assert capsys.readouterr().out == ""


def test_timed_throttle_and_slow_request(capsys):
	ring = A.RingHandler()
	A.setup(console=False, ring=ring)
	with A.timed("consulta completa", "consulta") as box:
		box["extra"] = "958 peças"
	assert ring.last()[-1]["tipo"] == "consulta" and ring.last()[-1]["msg"].startswith("consulta completa: 0.0 s 958 peças")
	assert box["s"] is not None and box["s"] < 1.0
	th = A.Throttle(every_n=20, every_s=1e9)
	assert [th(n, 100) for n in (1, 19, 20, 21, 39, 40, 100)] == [False, False, True, False, False, True, True]
	n0 = ring.seq
	assert A.slow_request("GET", "/api/board", 0.4) is False and ring.seq == n0
	assert A.slow_request("GET", "/api/holes", 2.3, 200) is True
	assert ring.last()[-1]["tipo"] == "pedido" and ring.last()[-1]["nivel"] == "info" and "GET /api/holes 2.3 s → 200" in ring.last()[-1]["msg"]
	assert A.slow_request("POST", "/api/confirm", 12.0) is True and ring.last()[-1]["nivel"] == "aviso"


def test_server_default_log_goes_to_activity_and_api(tmp_path):
	pytest.importorskip("httpx")
	from fastapi.testclient import TestClient
	from src import server as S
	from test_consistency import _row_project
	pr, ids = _row_project(tmp_path)
	ring = A.RingHandler()
	gui = S.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "uploads"), ring=ring)   # log="activity" by default
	gui.activity_setup(console=False, file=True)
	client = TestClient(S.create_app(gui))
	seq0 = gui.seq
	gui.log("[preparar] tabuleiro pronto (0,1 s)")
	gui.log("[servidor] qualquer coisa")
	recs = ring.last()
	assert recs[-2]["tipo"] == "arranque" and recs[-2]["msg"] == "tabuleiro pronto (0,1 s)" and recs[-1]["tipo"] == "servidor"
	assert [e[1] for e in gui.events_after(seq0)] == ["atividade", "atividade"]            # one SSE event per line
	# an event written to the log is a line too (state._activity_line)
	pr2 = gui.pr
	pr2.log_event("twin_confirmed", piece=ids["A"], cell=(2, 3), origin="gemeo")
	assert ring.last()[-1]["tipo"] == "evento" and ring.last()[-1]["msg"] == f"twin_confirmed {ids['A']} (2,3) origem gemeo"
	d = client.get("/api/atividade").json()
	assert d["seq"] == ring.seq and [r["msg"] for r in d["linhas"]][-1].startswith("twin_confirmed") and "evento" in d["tipos"] and d["niveis"] == ["info", "aviso", "erro"]
	assert d["ficheiro"] and d["ficheiro"].endswith(f"servidor-{_dt.date.today():%Y%m%d}.log")
	assert client.get(f"/api/atividade?desde={ring.seq - 1}").json()["linhas"][0]["seq"] == ring.seq
	assert client.get("/api/status").json()["atividade_seq"] == ring.seq
	# a trivial request leaves no line
	n = ring.seq
	client.get("/api/status")
	assert ring.seq == n
	A.teardown()
