"""Ctrl+C fecha o servidor logo, com um separador (ligação SSE ``/api/events``) aberto ou não (F2b, item 2).

Causa [V]: o uvicorn, ao parar, espera que as ligações abertas terminem; o gerador de ``/api/events`` nunca termina
sozinho (só ao fim de um ``keep-alive`` de 15 s, e só se o cliente já tiver saído), por isso com um separador aberto o
processo ficava vivo (medido: > 20 s, sem sair) até o separador fechar. Correção: ``Gui.begin_shutdown`` (chamado pelo
tratador do sinal) acaba os fluxos SSE e ``timeout_graceful_shutdown`` limita o resto.

O servidor corre num subprocesso (``python -m src.server``) sobre o projeto sintético de ``test_query``; o sinal é o
Ctrl+Break num grupo de processos novo no Windows (o que o uvicorn trata como Ctrl+C) e SIGINT no resto.
"""

import http.client
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")

from test_query import _project  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIMIT_S = 8.0           # medido: 0,2 s; antes da correção > 20 s (nunca saía)


def _free_port() -> int:
	s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
	return port


def _start(project_path: str, port: int) -> subprocess.Popen:
	kw = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {}
	p = subprocess.Popen([sys.executable, "-m", "src.server", "--project", project_path, "--port", str(port), "--no-prepare", "--no-image"],
						 cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kw)
	t0 = time.time()
	while time.time() - t0 < 60:
		if p.poll() is not None:
			raise AssertionError("o servidor saiu ao arrancar: " + p.stdout.read().decode("utf8", "replace"))
		try:
			urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=1).read()
			return p
		except OSError:
			time.sleep(0.2)
	p.kill()
	raise AssertionError("o servidor não arrancou em 60 s")


def _interrupt(p: subprocess.Popen) -> float:
	"""Ctrl+C ao servidor; devolve os segundos até sair (``inf`` se não saiu em ``LIMIT_S``; mata-o nesse caso)."""
	t0 = time.time()
	p.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT)
	try:
		p.wait(LIMIT_S)
		return time.time() - t0
	except subprocess.TimeoutExpired:
		p.kill()
		p.wait(10)
		return float("inf")


def _sse(port: int, **headers) -> http.client.HTTPResponse:
	c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
	c.request("GET", "/api/events", headers=headers)
	r = c.getresponse()
	assert r.status == 200
	return r


@pytest.fixture
def proj(tmp_path):
	pr, *_ = _project(tmp_path)
	return pr.path


def test_ctrl_c_closes_with_sse_clients_open(proj):
	port = _free_port()
	p = _start(proj, port)
	clients = [_sse(port) for _ in range(2)]          # dois separadores abertos
	for r in clients:
		assert r.readline().startswith(b"retry")   # ligados: já receberam o início do fluxo
	secs = _interrupt(p)
	out = p.stdout.read().decode("utf8", "replace")
	assert secs < LIMIT_S, f"o servidor não fechou com os separadores abertos (> {LIMIT_S} s)\n{out[-800:]}"
	assert "Traceback" not in out and "CancelledError" not in out, out[-1500:]


def test_ctrl_c_closes_without_clients(proj):
	port = _free_port()
	p = _start(proj, port)
	assert _interrupt(p) < LIMIT_S


def test_sse_after_server_restart_ignores_old_last_event_id(proj):
	"""Um browser que se religa a um servidor REINICIADO traz o ``Last-Event-ID`` do contador antigo (aqui 99999):
	os eventos novos têm de lhe chegar na mesma (antes eram todos ignorados até o contador passar esse número)."""
	port = _free_port()
	p = _start(proj, port)
	try:
		r = _sse(port, **{"Last-Event-ID": "99999"})
		urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/api/confirm", method="POST",
							   data=json.dumps({"acao": "cell_full", "cell": [4, 6]}).encode(), headers={"Content-Type": "application/json"}), timeout=60).read()
		t0 = time.time()
		seen = False
		while time.time() - t0 < 15 and not seen:
			line = r.readline()
			seen = line.startswith(b"event: board_changed")
		assert seen, "o evento novo não chegou ao cliente com um Last-Event-ID de um servidor anterior"
	finally:
		_interrupt(p)


# ---------------------------------------------------------------- F2c, item 6: uma linha só, código 0, sem traceback
def _stop_output(proj, with_sse: bool):
	port = _free_port()
	p = _start(proj, port)
	r = _sse(port) if with_sse else None
	if r is not None:
		assert r.readline().startswith(b"retry")
	t0 = time.time()
	p.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT)
	try:
		p.wait(LIMIT_S)
	except subprocess.TimeoutExpired:
		p.kill(); p.wait(10)
		raise AssertionError("não fechou")
	out = p.stdout.read().decode("utf8", "replace")
	return p.returncode, out


def _after_start(out: str) -> list:
	"""As linhas escritas depois das do arranque (`abre http://…`): o que o Ctrl+C acrescentou."""
	lines = [x for x in out.splitlines() if x.strip()]
	i = max((k for k, x in enumerate(lines) if "abre http://" in x or "registo em" in x), default=-1)
	return lines[i + 1:]


@pytest.mark.parametrize("with_sse", [False, True])
def test_ctrl_c_prints_one_line_and_exits_zero(proj, with_sse):
	code, out = _stop_output(proj, with_sse)
	assert "Traceback" not in out and "CancelledError" not in out and "KeyboardInterrupt" not in out, out[-1500:]
	assert _after_start(out) == ["Servidor parado."], out[-1500:]
	assert code == 0, (code, out[-800:])
