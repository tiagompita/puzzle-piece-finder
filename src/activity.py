"""Registo de atividade: linhas úteis no terminal, num ficheiro por dia e num anel em memória para a GUI.

Um só logger raiz ``ppf`` com um filho por **tipo** de linha (``ppf.<tipo>``): ``servidor``, ``arranque``,
``consulta``, ``cache``, ``ativos``, ``progresso``, ``evento``, ``pedido``, ``buracos``, ``erro``. Níveis
``info`` / ``aviso`` / ``erro`` (INFO / WARNING / ERROR do :mod:`logging`). Formato::

	HH:MM:SS info  evento    placed P0177 (2,37) origem buraco

:func:`setup` liga os destinos: consola (``stdout``), ficheiro ``<projeto>/logs/servidor-AAAAMMDD.log``
(:class:`DailyFileHandler`: muda de ficheiro quando a data muda, nunca apaga; a pasta ``logs/`` está no
``.gitignore``) e o anel :class:`RingHandler` (as últimas N linhas, com um ``callback`` por linha para o SSE
``atividade`` do servidor). Sem :func:`setup` as linhas ``info`` perdem-se em silêncio (os CLIs chamam
``setup(console=True)``; os testes do servidor não chamam nada). Nada por pedido HTTP trivial: o servidor só
regista pedidos lentos (:func:`slow_request`). Puro :mod:`logging` e stdlib; nada do puzzle vive aqui.
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import logging
import os
import sys
import threading
import time
from collections import deque
from typing import Callable, Optional

__all__ = [
	"LOGGER", "TIPOS", "NIVEIS", "SLOW_REQUEST_S", "SLOW_REQUEST_WARN_S", "get", "tipo_of", "nivel_of", "setup",
	"teardown", "DailyFileHandler", "RingHandler", "timed", "Throttle", "slow_request",
]

LOGGER = "ppf"
TIPOS = ("servidor", "arranque", "consulta", "cache", "ativos", "progresso", "evento", "pedido", "buracos", "importar", "erro")
NIVEIS = ("info", "aviso", "erro")
_NIVEL = {logging.DEBUG: "info", logging.INFO: "info", logging.WARNING: "aviso", logging.ERROR: "erro", logging.CRITICAL: "erro"}
SLOW_REQUEST_S = 1.0          # a request slower than this gets a line (tipo ``pedido``, nível info)
SLOW_REQUEST_WARN_S = 10.0    # ... and slower than this a warning


def get(tipo: str = "servidor") -> logging.Logger:
	"""The child logger of one line type (``ppf.<tipo>``)."""
	return logging.getLogger(f"{LOGGER}.{tipo}")


def tipo_of(record: logging.LogRecord) -> str:
	name = record.name
	return name.split(".", 1)[1] if "." in name else "servidor"


def nivel_of(record: logging.LogRecord) -> str:
	return _NIVEL.get(record.levelno, "aviso" if record.levelno > logging.INFO else "info")


class _Formatter(logging.Formatter):
	def format(self, r: logging.LogRecord) -> str:
		t = _dt.datetime.fromtimestamp(r.created).strftime("%H:%M:%S")
		msg = r.getMessage()
		if r.exc_info:
			msg += "\n" + self.formatException(r.exc_info)
		return f"{t} {nivel_of(r):<5} {tipo_of(r):<9} {msg}"


class DailyFileHandler(logging.Handler):
	"""``<folder>/<prefix>-AAAAMMDD.log`` (UTF-8, append); the file changes when the date of the record changes."""

	def __init__(self, folder: str, prefix: str = "servidor"):
		super().__init__()
		self.folder, self.prefix = folder, prefix
		self._date: Optional[_dt.date] = None
		self._f = None
		self._lock = threading.Lock()
		self.setFormatter(_Formatter())

	def path_for(self, d: _dt.date) -> str:
		return os.path.join(self.folder, f"{self.prefix}-{d:%Y%m%d}.log")

	@property
	def path(self) -> Optional[str]:
		return None if self._date is None else self.path_for(self._date)

	def _open(self, d: _dt.date) -> None:
		if self._f is not None:
			self._f.close()
		os.makedirs(self.folder, exist_ok=True)
		self._f = open(self.path_for(d), "a", encoding="utf-8", newline="\n")
		self._date = d

	def emit(self, record: logging.LogRecord) -> None:
		try:
			d = _dt.date.fromtimestamp(record.created)
			with self._lock:
				if self._f is None or d != self._date:
					self._open(d)
				self._f.write(self.format(record) + "\n")
				self._f.flush()
		except Exception:  # noqa: BLE001 - a log line must never take the server down
			self.handleError(record)

	def close(self) -> None:
		with self._lock:
			if self._f is not None:
				self._f.close()
				self._f = None
		super().close()


class RingHandler(logging.Handler):
	"""The last ``n`` lines as dicts ``{seq, t, nivel, tipo, msg}`` (for ``GET /api/atividade``) and a ``callback(rec)``
	per line (the server turns it into the SSE ``atividade``)."""

	def __init__(self, n: int = 300, callback: Optional[Callable[[dict], None]] = None):
		super().__init__()
		self.recs: deque = deque(maxlen=n)
		self.seq = 0
		self.callback = callback
		self._lock = threading.Lock()

	def emit(self, record: logging.LogRecord) -> None:
		try:
			with self._lock:
				self.seq += 1
				rec = {"seq": self.seq, "t": _dt.datetime.fromtimestamp(record.created).isoformat(timespec="seconds"),
					   "nivel": nivel_of(record), "tipo": tipo_of(record), "msg": record.getMessage()}
				self.recs.append(rec)
			cb = self.callback
			if cb is not None:
				cb(rec)
		except Exception:  # noqa: BLE001
			self.handleError(record)

	def after(self, seq: int) -> list:
		with self._lock:
			return [r for r in self.recs if r["seq"] > seq]

	def last(self, n: Optional[int] = None) -> list:
		with self._lock:
			out = list(self.recs)
		return out if n is None else out[-n:]


def _handlers() -> list:
	return list(logging.getLogger(LOGGER).handlers)


def teardown() -> None:
	"""Remove and close every handler of ``ppf`` (tests; a server shutting down)."""
	root = logging.getLogger(LOGGER)
	for hd in list(root.handlers):
		root.removeHandler(hd)
		try:
			hd.close()
		except Exception:  # noqa: BLE001
			pass


def setup(project_dir: Optional[str] = None, *, console: bool = True, ring: Optional[RingHandler] = None,
		  level: int = logging.INFO, stream=None) -> logging.Logger:
	"""Attach the destinations to ``ppf`` (replacing the ones a previous call attached): the console (``stream``,
	default ``sys.stdout``), the daily file under ``<project_dir>/logs/`` when ``project_dir`` is given, and
	``ring``. Returns the root logger."""
	teardown()
	root = logging.getLogger(LOGGER)
	root.setLevel(level)
	root.propagate = False
	if console:
		st = stream or sys.stdout
		if hasattr(st, "reconfigure"):
			try:
				st.reconfigure(errors="replace")      # cp1252 consoles: never a «Logging error» for a «»
			except (ValueError, AttributeError):
				pass
		ch = logging.StreamHandler(st)
		ch.setFormatter(_Formatter())
		root.addHandler(ch)
	if project_dir:
		root.addHandler(DailyFileHandler(os.path.join(project_dir, "logs")))
	if ring is not None:
		root.addHandler(ring)
	return root


@contextlib.contextmanager
def timed(msg: str, tipo: str = "consulta", level: int = logging.INFO):
	"""``with timed("consulta") as box: ...`` logs ``"{msg}: {s} s"`` on exit; ``box["extra"]`` (set inside) is
	appended after the time, ``box["s"]`` holds the seconds."""
	box = {"extra": "", "s": None}
	t0 = time.perf_counter()
	try:
		yield box
	finally:
		box["s"] = time.perf_counter() - t0
		extra = f" {box['extra']}" if box.get("extra") else ""
		get(tipo).log(level, f"{msg}: {box['s']:.1f} s{extra}")


class Throttle:
	"""``Throttle(every_n=20, every_s=5.0)(n, N)`` says whether a progress line is due (always at n = N)."""

	def __init__(self, every_n: int = 20, every_s: float = 5.0):
		self.every_n, self.every_s = every_n, every_s
		self.t0 = self.t_last = time.time()
		self.n_last = 0

	def __call__(self, n: int, N: int) -> bool:
		now = time.time()
		if n >= N or n - self.n_last >= self.every_n or now - self.t_last >= self.every_s:
			self.t_last, self.n_last = now, n
			return True
		return False

	@property
	def elapsed(self) -> float:
		return time.time() - self.t0


def slow_request(method: str, path: str, seconds: float, status: Optional[int] = None) -> bool:
	"""One line (tipo ``pedido``) when a request took >= :data:`SLOW_REQUEST_S`; a warning above
	:data:`SLOW_REQUEST_WARN_S`. Returns whether a line was written."""
	if seconds < SLOW_REQUEST_S:
		return False
	lvl = logging.WARNING if seconds >= SLOW_REQUEST_WARN_S else logging.INFO
	get("pedido").log(lvl, f"pedido lento {method} {path} {seconds:.1f} s" + (f" → {status}" if status is not None else ""))
	return True
