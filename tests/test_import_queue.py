"""Tests of :mod:`src.import_queue` (pure bookkeeping, append-only file replayed on load)."""

import json

import pytest

from src.import_queue import ImportQueue, QueueError


def _q(tmp_path):
	return ImportQueue(str(tmp_path / "import_queue.jsonl"))


def _add(q, lote, n=1):
	return q.add(lote, [f"f{lote}.jpg"], [{"origem": f"f{lote}.jpg", "pagina": None, "caminho": f"f{lote}.jpg"}] * n)


def _run(q, jid, ok=True):
	q.start(jid)
	q.sheet(jid, 1, 1, caminho="x.jpg", estado="ok" if ok else "erro", scan_id="S0001" if ok else None, n_pecas=3 if ok else 0,
			erro=None if ok else "imagem ilegível")
	if ok:
		q.done(jid, n_folhas=1, n_pecas=3, propostas=1, segundos=2.0)
	else:
		q.fail(jid, "imagem ilegível")


def _ids(q, estado=None):
	return [j["id"] for j in q.snapshot() if estado is None or j["estado"] == estado]


def test_fifo_and_ids(tmp_path):
	q = _q(tmp_path)
	a, b, c = _add(q, 9), _add(q, 10, 2), _add(q, 11)
	assert (a, b, c) == ("Q0001", "Q0002", "Q0003")
	assert q.next_job()["id"] == a and _ids(q, "em_fila") == [a, b, c]
	_run(q, a)
	assert q.next_job()["id"] == b
	snap = {j["id"]: j for j in q.snapshot()}
	assert snap[a]["estado"] == "concluido" and snap[a]["progresso"] == "1/1" and snap[a]["n_pecas"] == 3
	assert snap[b]["posicao"] == 0 and snap[c]["posicao"] == 1 and snap[b]["progresso"] == "0/2"
	assert q.summary() == {"n_em_fila": 2, "a_correr": None}
	# ids stay monotonic after a reload
	assert _add(ImportQueue(q.path), 12) == "Q0004"


def test_cancel_only_queued(tmp_path):
	q = _q(tmp_path)
	a, b = _add(q, 1), _add(q, 2)
	q.start(a)
	with pytest.raises(QueueError, match="só um trabalho em fila"):
		q.cancel(a)
	q.cancel(b)
	assert q.job(b)["estado"] == "cancelado" and q.next_job() is None
	with pytest.raises(QueueError):
		q.cancel(b)
	with pytest.raises(QueueError, match="desconhecido"):
		q.cancel("Q0099")


def test_failure_does_not_block_the_next_and_retry(tmp_path):
	q = _q(tmp_path)
	a, b = _add(q, 1), _add(q, 2)
	_run(q, a, ok=False)
	assert q.job(a)["estado"] == "falhado" and q.next_job()["id"] == b
	snap = {j["id"]: j for j in q.snapshot()}
	assert snap[a]["erro"] == "imagem ilegível"
	with pytest.raises(QueueError):
		q.retry(b)                                   # queued: nothing to retry
	q.retry(a)
	assert _ids(q, "em_fila") == [b, a]              # a user retry goes to the end
	_run(q, b)
	q.start(a)
	assert q.job(a)["tentativas"] == 2 and q.job(a)["resultados"] == [] and q.job(a)["erro"] is None


def test_move(tmp_path):
	q = _q(tmp_path)
	a, b, c, d = (_add(q, k) for k in (1, 2, 3, 4))
	q.move(d, 0)
	assert _ids(q, "em_fila") == [d, a, b, c]
	q.move(d, 2)
	assert _ids(q, "em_fila") == [a, b, d, c]
	q.move(a, 99)
	assert _ids(q, "em_fila") == [b, d, c, a]
	q.start(b)
	with pytest.raises(QueueError):
		q.move(b, 0)
	q.move(a, 0)
	assert _ids(q, "em_fila") == [a, d, c] and q.next_job()["id"] == a


def test_snapshot_equals_replay_of_the_file(tmp_path):
	q = _q(tmp_path)
	a, b, c, d = (_add(q, k) for k in (1, 2, 3, 4))
	_run(q, a)
	q.move(c, 0)
	q.cancel(d)
	_run(q, c, ok=False)
	q.retry(c)
	q.retry(d)
	q.start(b)
	q.sheet(b, 1, 1, caminho="b.jpg", estado="ignorada", scan_id="S0001", avisos=["escala: x"])
	other = ImportQueue(q.path)
	assert other.snapshot() == q.snapshot()
	assert json.dumps(other.state, sort_keys=True) == json.dumps(q.state, sort_keys=True)
	with open(q.path, encoding="utf-8") as f:
		acts = [json.loads(x)["action"] for x in f]
	assert acts[0] == "job_added" and set(acts) <= {"job_added", "job_started", "job_sheet", "job_done", "job_failed",
													 "job_cancelled", "job_retried", "job_moved"}


def test_recover_puts_running_back_at_the_head(tmp_path):
	q = _q(tmp_path)
	a, b, c = _add(q, 1), _add(q, 2), _add(q, 3)
	_run(q, a)
	q.start(b)
	q.sheet(b, 1, 2, caminho="b1.jpg", estado="ok", scan_id="S0002", n_pecas=5)
	# the server stops here; a new one replays the file
	q2 = ImportQueue(q.path)
	assert q2.running() == b
	assert q2.recover() == [b]
	assert q2.running() is None and _ids(q2, "em_fila") == [b, c] and q2.next_job()["id"] == b
	with open(q.path, encoding="utf-8") as f:
		last = json.loads(f.readlines()[-1])
	assert last["action"] == "job_retried" and last["motivo"] == "reinicio" and last["cabeca"] is True
	assert ImportQueue(q.path).snapshot() == q2.snapshot()
	assert q2.recover() == []
