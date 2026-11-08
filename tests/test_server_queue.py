"""The import queue of the GUI server (:mod:`src.server` + :mod:`src.import_queue`), with the TestClient.

Jobs run in the worker thread ``fila-importacao`` in order; a cancelled job never runs; ``POST /api/confirm`` during a
job waits for the write lock instead of answering 409 and the log stays ordered and replayable; a server restart puts
a job left running back at the head of the queue, and a sheet already imported is ``ignorada``."""

import json
import os
import threading
import time

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from src import server as S  # noqa: E402
from src.import_queue import ImportQueue  # noqa: E402
from src.state import Project, replay  # noqa: E402
from test_ingest_multi import _scan  # noqa: E402
from test_query import _project  # noqa: E402


def _slow_segment(delay):
	from src.segmentation import segment_scan

	def seg(photo, **k):
		time.sleep(delay)
		return segment_scan(photo, **k)
	return seg


@pytest.fixture
def env(tmp_path):
	from src.query import run_query
	pr, placed, tw, dec = _project(tmp_path)
	run_query(pr, use_image=False)
	gui = S.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "uploads"), log=None, queue=True)
	yield gui, TestClient(S.create_app(gui)), tw, tmp_path
	gui.stop()


def _post(cl, files, lote, dpi=None):
	fs = [("files", (os.path.basename(f), open(f, "rb"), "image/png")) for f in files]
	try:
		data = {"lote": str(lote)}
		if dpi is not None:
			data["dpi"] = str(dpi)
		return cl.post("/api/ingest", files=fs, data=data)
	finally:
		for _, (_, fh, _) in fs:
			fh.close()


def _wait_idle(gui, timeout=120):
	t0 = time.time()
	while time.time() - t0 < timeout:
		q = gui.queue_json()
		if not any(j["estado"] in ("em_fila", "a_correr") for j in q["fila"]) and gui.job is None:
			return q
		time.sleep(0.1)
	raise AssertionError(f"fila não terminou: {gui.queue_json()}")


def _wait_state(gui, jid, estado, timeout=60):
	t0 = time.time()
	while time.time() - t0 < timeout:
		j = next((x for x in gui.queue_json()["fila"] if x["id"] == jid), None)
		if j and j["estado"] == estado:
			return j
		time.sleep(0.05)
	raise AssertionError(f"{jid} não chegou a {estado}: {gui.queue_json()}")


def _ok_on_disk(path):
	pr = Project.open(path)
	assert pr.check_invariants(disk=True) == []
	rb, _ = replay(pr.log_path, pr.profile)
	assert rb == pr.board
	return pr


def test_two_jobs_in_order_with_events_and_status(env):
	gui, cl, tw, tmp = env
	a = _scan(tmp / "a.png", 2, seed=1)
	b1, b2 = _scan(tmp / "b1.png", 3, seed=2), _scan(tmp / "b2.png", 1, seed=3)
	gui.ingest_segment = _slow_segment(0.3)
	r1 = _post(cl, [a], 5)
	assert r1.status_code == 200, r1.text
	r2 = _post(cl, [b1, b2], 6, dpi=300)                        # no 409 while the first runs
	assert r2.status_code == 200, r2.text
	assert (r1.json()["job"], r1.json()["folhas"], r2.json()["job"], r2.json()["folhas"]) == ("Q0001", 1, "Q0002", 2)
	assert os.path.basename(r1.json()["ficheiro"]).startswith("lote05_")
	st = cl.get("/api/status").json()
	assert st["fila"]["n_em_fila"] + (1 if st["fila"]["a_correr"] else 0) >= 1 and st["job"]
	q = _wait_idle(gui)
	jobs = {j["id"]: j for j in q["fila"]}
	assert jobs["Q0001"]["estado"] == "concluido" and jobs["Q0002"]["estado"] == "concluido"
	assert jobs["Q0002"]["progresso"] == "2/2" and jobs["Q0002"]["n_pecas"] == 4
	with open(gui.iq.path, encoding="utf-8") as f:
		evs = [json.loads(x) for x in f]
	started = [e["id"] for e in evs if e["action"] == "job_started"]
	assert started == ["Q0001", "Q0002"]
	names = [n for _, n, _ in gui.events_after(0)]
	assert "queue_changed" in names and names.count("fetch_changed") >= 2
	prog = [d for _, n, d in gui.events_after(0) if n == "ingest_progress"]
	assert prog[0]["etapa"] == "segmentar" and prog[-1]["etapa"] == "pronto" and prog[-1]["fim"]
	lots = {x["lote"]: x for x in cl.get("/api/lots").json()}
	assert [p["n_no_lote"] for p in lots[6]["pecas"]] == [1, 2, 3, 4]
	assert cl.get("/api/import_queue").json()["resumo"] == {"n_em_fila": 0, "a_correr": None}
	assert gui.job is None and cl.get("/api/status").json()["job"] is None
	_ok_on_disk(gui.path)


def test_cancel_second_job_and_retry(env):
	gui, cl, tw, tmp = env
	gui.ingest_segment = _slow_segment(1.0)
	j1 = _post(cl, [_scan(tmp / "a.png", 1, seed=4)], 7).json()["job"]
	j2 = _post(cl, [_scan(tmp / "b.png", 1, seed=5)], 8).json()["job"]
	_wait_state(gui, j1, "a_correr")
	assert cl.post(f"/api/import_queue/{j1}/cancelar").status_code == 400        # running: cannot cancel
	r = cl.post(f"/api/import_queue/{j2}/cancelar")
	assert r.status_code == 200 and next(j for j in r.json()["fila"] if j["id"] == j2)["estado"] == "cancelado"
	assert cl.post("/api/import_queue/Q0099/cancelar").status_code == 404
	q = _wait_idle(gui)
	assert {j["id"]: j["estado"] for j in q["fila"]} == {j1: "concluido", j2: "cancelado"}
	assert not [p for p in Project.open(gui.path).pieces.values() if p.lote == 8]
	gui.ingest_segment = None
	assert cl.post(f"/api/import_queue/{j2}/repetir").status_code == 200
	q = _wait_idle(gui)
	assert {j["id"]: j["estado"] for j in q["fila"]}[j2] == "concluido"
	assert len([p for p in Project.open(gui.path).pieces.values() if p.lote == 8]) == 1


def test_failed_job_does_not_block_and_move(env):
	gui, cl, tw, tmp = env
	bad = tmp / "bad.png"
	bad.write_bytes(b"isto nao e um png")
	gui.ingest_segment = _slow_segment(0.8)
	j0 = _post(cl, [_scan(tmp / "z.png", 1, seed=9)], 3).json()["job"]
	jb = _post(cl, [str(bad)], 4).json()["job"]
	jg = _post(cl, [_scan(tmp / "g.png", 1, seed=6)], 5).json()["job"]
	_wait_state(gui, j0, "a_correr")
	r = cl.post(f"/api/import_queue/{jg}/mover", json={"posicao": 0})
	assert r.status_code == 200
	assert [j["id"] for j in r.json()["fila"] if j["estado"] == "em_fila"] == [jg, jb]
	assert cl.post(f"/api/import_queue/{jg}/mover", json={}).status_code == 400
	q = _wait_idle(gui)
	st = {j["id"]: j for j in q["fila"]}
	assert st[jb]["estado"] == "falhado" and "não é uma imagem legível" in st[jb]["erro"]
	assert st[jg]["estado"] == "concluido" and st[j0]["estado"] == "concluido"
	with open(gui.iq.path, encoding="utf-8") as f:
		started = [json.loads(x)["id"] for x in f if '"job_started"' in x]
	assert started == [j0, jg, jb]
	_ok_on_disk(gui.path)


def test_confirm_during_a_job_waits_for_the_lock(env):
	gui, cl, tw, tmp = env
	gui.ingest_segment = _slow_segment(2.0)
	jid = _post(cl, [_scan(tmp / "a.png", 2, seed=7)], 9).json()["job"]
	_wait_state(gui, jid, "a_correr")
	assert gui.job and gui.job.startswith("a importar saco 9")
	# the worker holds the lock for a commit: simulate a long one; the confirmation waits instead of 409
	held = threading.Event()

	def hold():
		with gui.wlock:
			held.set()
			time.sleep(1.5)
	th = threading.Thread(target=hold)
	th.start()
	held.wait(5)
	t0 = time.time()
	r = cl.post("/api/confirm", json={"acao": "place", "piece": tw, "cell": [3, 4]})
	waited = time.time() - t0
	th.join()
	assert r.status_code == 200, r.text
	assert waited >= 1.0
	_wait_idle(gui)
	pr = _ok_on_disk(gui.path)
	assert pr.piece(tw).estado == "colocada"
	acts = [e["action"] for e in pr.events()]
	k_place = max(i for i, a in enumerate(acts) if a == "placed")
	k_scan = max(i for i, a in enumerate(acts) if a == "scan_added")
	assert k_place < k_scan                                      # the confirmation went in while the sheet was segmented
	assert len([p for p in pr.pieces.values() if p.lote == 9]) == 2


def test_exclusive_job_still_409(env):
	gui, cl, tw, tmp = env
	gui.job = "importar x"                                     # an exclusive job set by hand, not the queue
	try:
		assert cl.post("/api/confirm", json={"acao": "discard", "piece": tw}).status_code == 409
	finally:
		gui.job = None


def test_restart_resumes_a_running_job_and_repeated_sheet_is_ignored(env, tmp_path):
	gui, cl, tw, tmp = env
	a = _scan(tmp / "a.png", 2, seed=8)
	assert _post(cl, [a], 4).status_code == 200
	q = _wait_idle(gui)
	up = os.path.join(S.REPO, q["fila"][0]["folhas"][0]["caminho"]) if not os.path.isabs(q["fila"][0]["folhas"][0]["caminho"]) \
		else q["fila"][0]["folhas"][0]["caminho"]
	gui.stop()
	# a job that was running when the server stopped: the same sheet again plus a new one
	b = _scan(tmp / "b.png", 1, seed=11)
	iq = ImportQueue(gui.iq.path)
	jid = iq.add(4, [up, b], [{"origem": up, "pagina": None, "caminho": up}, {"origem": b, "pagina": None, "caminho": b}])
	iq.start(jid)
	iq.sheet(jid, 1, 2, caminho=up, estado="ok", scan_id="S0002", n_pecas=2)
	gui2 = S.Gui(gui.path, prepare=False, use_image=False, uploads=gui.uploads, log=None, queue=True)
	try:
		q2 = _wait_idle(gui2)
		j = next(x for x in q2["fila"] if x["id"] == jid)
		assert j["estado"] == "concluido" and j["tentativas"] == 2
		assert [r["estado"] for r in sorted(j["resultados"], key=lambda r: r["k"])] == ["ignorada", "ok"]
		with open(gui2.iq.path, encoding="utf-8") as f:
			evs = [json.loads(x) for x in f]
		assert any(e["action"] == "job_retried" and e["id"] == jid and e["motivo"] == "reinicio" for e in evs)
		pr = _ok_on_disk(gui2.path)
		assert sorted(p.n_no_lote for p in pr.pieces.values() if p.lote == 4) == [1, 2, 3]
	finally:
		gui2.stop()
