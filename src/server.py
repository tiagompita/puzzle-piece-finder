"""Local web GUI ("mesa de montagem"): a thin FastAPI server over :class:`src.state.Project`.

Usage::

	python -m src.server --project projects/alpes [--port 8765] [--lan] [--no-image]

Then open ``http://127.0.0.1:8765``. ``--lan`` binds 0.0.0.0 so a phone on the same Wi-Fi
can open ``http://<pc>:8765``; there is **no login**: anyone on that network can read and
change the project (a warning is printed).

Design (docs/gui-design.md):

* **Writes** go through :func:`src.confirm.confirm` (place / reject / position known /
  anchor / unanchor / discard, then the incremental re-query), :meth:`Project.unplace`
  and the import queue (:func:`src.ingest.commit_sheet` + :func:`src.query.run_query`), all under one lock
  (``Gui.wlock``). The log stays the source of truth (``board == replay(log)``). A write waits up to
  :data:`WRITE_WAIT_S` for the lock (an import holds it for the commit of one sheet, seconds, and for the one full
  re-query of a job) and answers 409 only after that, or while an *exclusive* job (``Gui.job`` set by anything but
  the import queue) runs.
* **Import queue** (:mod:`src.import_queue`, ``<project>/import_queue.jsonl``): ``POST /api/ingest`` takes one or
  more files (images, PDF = one sheet per page, :mod:`src.sheets`) for one bag and appends a job; the thread
  ``fila-importacao`` runs the jobs in order, waiting on ``Gui._qcond`` (no polling): per sheet
  :func:`src.ingest.segment_sheet` **outside** the lock (minutes), then :func:`src.ingest.commit_sheet` under it;
  one full :func:`src.query.run_query` per job. A sheet already imported (same sha256) is ``ignorada``. A job left
  running by a restart goes back to the head of the queue. ``GET /api/import_queue``,
  ``POST /api/import_queue/{id}/cancelar | repetir | mover``; SSE ``queue_changed``.
* **Reads** never take the write lock; a read that races a write (``dict changed size``)
  is retried. If ``log.jsonl`` changes behind the server's back (a CLI run), the project is
  re-opened on the next request.
* **Board raster**: :func:`src.render.compose_board` with the layers ``art`` + ``pieces``
  only; everything else (legacy hatch, missing border, "vai buscar", known positions,
  ghosts, grid, selection) is the SVG overlay the browser draws from ``/api/board`` with the
  classes of :data:`LEGEND`. The full board at ``BOARD_PPC`` is cached in memory and in
  ``render/gui/`` keyed by the log size; after a change only the changed cells +/- 1 are
  re-composed and pasted. Smaller boards are downscaled from it; zoomed regions are
  composed on demand (``region=``) and kept in a small LRU.
* **Start-up rule**: if ``pieces/``, ``crops/``, ``overlays/`` or ``render/`` is missing or
  empty (a fresh clone: they are git-ignored), :func:`src.render.rebuild_assets` runs in a
  background thread, with progress in the terminal and on the "a preparar" page (SSE
  ``prepare_progress``); the data endpoints answer 503 until it ends. Then (always) the assets are
  checked against the log (:func:`src.render.stale_assets`: the log comes with ``git pull``, the npz /
  crops do not); stale sheets are re-segmented (:func:`src.render.rebuild_stale`) the same way, and the
  summary is ``ativos`` in ``/api/status`` (``eventos`` > 0 = this code segments differently).
* **Contour editor** (``/api/pieces/{id}/contorno``, docs/gui-design.md §18): the scan around the
  piece, a preview of a drawn outline, the stroke solver (``POST …/contorno/resolver``: strokes ->
  trimap -> :mod:`src.strokes` -> polygon, read-only, no lock; contract in
  docs/diagnostico/editor/TRACOS.md) and the save (``overrides.jsonl`` via
  :func:`src.overrides.append_override`, then :func:`src.render.rebuild_piece`, under the same lock).
* **Events** (SSE ``/api/events``, delivered on :meth:`Gui.emit` by waking one ``asyncio.Event`` per client: an idle
  server does no work per client; a keep-alive comment every 15 s): ``board_changed``, ``fetch_changed``,
  ``piece_changed``, ``ingest_progress``, ``queue_changed``, ``prepare_progress``, ``report_added``, ``report_edited``, ``report_changed``,
  ``suspeitas_changed`` (summary of ``/api/suspeitas`` + ``n_em_reports``: after a board write, a report write
  or a false-alarm mark), ``holes_changed``, ``holes_progress`` (strips ``n/N`` of a cold hole ranking),
  ``atividade`` (one activity line, :mod:`src.activity`), ``ready``.
* **Activity** (:mod:`src.activity`, docs/gui-design.md §23): every ``Gui.log`` line, the start-up steps, the
  queries (time per step), the caches (board, holes, strips), the progress of the long operations, every event
  written to the log and the slow requests (> 1 s; never a line per trivial request) go to the terminal, to
  ``<project>/logs/servidor-AAAAMMDD.log`` and to a ring the GUI panel reads (``GET /api/atividade``).
* **Hole suggestions in «Vai buscar»** (M11_CRITERIOS §8, docs/gui-design.md §22): ``/api/fetch`` carries
  ``buracos_alta`` (the rank-1 candidate of every ``alta`` hole that agrees with the joint assignment, the counter
  of the ``alta`` decisions with Wilson 95 % and the pause state); ``POST /api/holes/alta/reativar`` logs
  ``holes_alta_resumed``; ``POST /api/holes/{l}/{c}/confirmar|rejeitar`` accept ``gemea: true`` (fused card).
* **Manual pose** («Editar posicionamento», docs/diagnostico/render/POSE_MANUAL.md): ``GET /api/pieces/{id}/pose``
  (contour in cell-width units about the pivot, not rotated, the neighbours, the SVG transform),
  ``POST …/pose/avaliar`` (seams + orientation of a candidate pose, read-only, no lock),
  ``POST …/pose`` and ``POST …/pose/repor`` (events ``pose_set`` / ``pose_cleared`` under the write lock,
  incremental re-query, ``board_changed`` / ``fetch_changed`` / ``suspeitas_changed`` / ``piece_changed``).
* **Suspects** (``/api/suspeitas``, :mod:`src.consistency`): items joined with the open reports
  (``report_aberto``); ``POST /api/suspeitas/{piece}/falso-alarme`` ``{grau, nota?}`` and
  ``POST …/restaurar`` ``{grau}`` log ``suspect_dismissed`` / ``suspect_restored`` under the write lock.

Pure helpers (legend, cell diff, patch regions, plain-language reasons) are separate from
the :class:`Gui` state object and from :func:`create_app` (routes).
"""

import argparse
import asyncio
import collections
import datetime as _dt
import json
import math
import logging
import os
import re
import socket
import sys
import threading
import time
import traceback
from typing import Optional

import cv2
import numpy as np

from src import activity
from src import overrides as OV
from src.import_queue import ImportQueue, QueueError
from src import strokes as ST
from src.query import fetch_group, mounted_neighbours
from src.state import Project, StateError

__all__ = [
	"LEGEND", "legend_for", "BOARD_PPC", "DEFAULT_PORT", "SPAN_CELLS", "missing_assets", "changed_cells", "patch_regions",
	"plain_reasons", "cell_text", "Gui", "create_app", "main",
]

DEFAULT_PORT = 8765
BOARD_PPC = 60                 # px per cell of the cached full-board raster (3840 x 2729 for the Alpes)
MAX_FULL_PPC = 80              # a full board above this is refused (use region=)
MAX_REGION_PPC = 240           # ~300 dpi is 218.5 px per cell
MAX_REGION_PX = 12_000_000     # output pixels of one region request
PATCH_MAX_CELLS = 40           # more changed cells than this -> full recompose instead of patches
SPAN_CELLS = 1.8               # piece PNG: the canvas spans this many cell widths, body centre in the middle
PIECE_PX_MAX = 600
SHEET_MAX_PX = 1400
JPEG_Q = 86
REGION_LRU = 24
PIECE_LRU = 600
SECTION_LRU = 64
EVENTS_KEEP = 500
WRITE_WAIT_S = 90.0            # a write waits this long for the lock (an import commit / re-query) before 409
SSE_KEEPALIVE_S = 15.0
QUEUE_DONE_KEEP = 30           # finished jobs in the queue snapshot (the file keeps all)
POSE_CONTOUR_PTS = 300         # GET /pose: points of each contour (cell-width units)
POSE_DIRS = {"N": (-1, 0), "E": (0, 1), "S": (1, 0), "W": (0, -1)}
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSET_DIRS = ("pieces", "crops", "overlays", "render")

# One row per symbol drawn on the board. ``classe`` = the CSS class of the SVG overlay
# element (prefix ``b-``; tests/test_server.py checks every ``b-`` class used by src/web has
# a row here); raster rows describe what the composed image itself shows.
LEGEND = [
	{"id": "peca", "tipo": "raster", "classe": None, "rotulo": "Peça colocada", "texto": "recorte real do scan",
	 "detalhe": "o recorte real do scan, limpo da franja verde e registado na sua célula"},
	{"id": "vazia", "tipo": "raster", "classe": None, "rotulo": "Célula vazia", "texto": "só a arte da caixa (34 %)",
	 "detalhe": "célula sem peça: vê-se a arte da caixa a 34 % de opacidade"},
	{"id": "legado", "tipo": "svg", "classe": "b-legado", "rotulo": "Ocupada sem silhueta", "texto": "cheia na foto, por confirmar",
	 "detalhe": "cheia na foto do tabuleiro, por confirmar: conta como vazia nas sugestões até a marcares; marcada por ti "
				"como montada (mesmo tracejado, o painel diz «marcada por ti») conta como ocupada; em ambos os casos a "
				"peça ainda não passou solta pelo scanner (não há recorte)"},
	{"id": "borda", "tipo": "svg", "classe": "b-borda-falta", "rotulo": "Borda em falta", "texto": "célula de borda vazia",
	 "detalhe": "célula de borda ainda vazia"},
	{"id": "buscar", "tipo": "svg", "classe": "b-buscar", "rotulo": "Vai buscar", "texto": "peça proposta (aceite)",
	 "detalhe": "há uma peça solta proposta para esta célula, com forma e imagem aceites"},
	{"id": "buscar_amb", "tipo": "svg", "classe": "b-buscar-ambigua", "rotulo": "Vai buscar (ambígua)",
	 "texto": "com dúvida", "detalhe": "proposta com dúvida: confirma pela imagem antes de colar"},
	{"id": "buscar_par", "tipo": "svg", "classe": "b-buscar-par", "rotulo": "Par de soltas", "texto": "célula só provável",
	 "detalhe": "duas peças soltas gémeas entre si; a célula vem só da imagem e é provável, não certa"},
	{"id": "conhecida", "tipo": "svg", "classe": "b-conhecida", "rotulo": "Posição conhecida", "texto": "guardada, à espera de vizinha",
	 "detalhe": "a peça já sabe a sua célula mas está guardada à parte, à espera de uma vizinha montada"},
	{"id": "fantasma", "tipo": "svg", "classe": "b-fantasma", "rotulo": "Fantasma", "texto": "forma da gémea, rodada {rot}°",
	 "detalhe": "contorno da gémea já colocada, rodado {rot}° (simetria do perfil): a forma exata da peça que falta nesta célula"},
	{"id": "sugestao", "tipo": "svg", "classe": "b-sug", "rotulo": "Sugestão segura", "texto": "melhor zona de um grupo (botão Sugestões)",
	 "detalhe": "melhor zona de um grupo solto cuja margem passa o mínimo do perfil; tocar abre o grupo na aba Mesa"},
	{"id": "sugestao_fraca", "tipo": "svg", "classe": "b-sug-fraca", "rotulo": "Sugestão a confirmar", "texto": "melhor zona de um grupo, por confirmar",
	 "detalhe": "melhor zona de um grupo solto cuja margem não passa o mínimo: o programa não decidiu"},
	{"id": "mesa", "tipo": "svg", "classe": "b-mesa", "rotulo": "Grupo da mesa", "texto": "onde um grupo solto ficaria",
	 "detalhe": "pré-visualização (separador Mesa) de onde um grupo solto ficaria se disseres «É aqui»"},
	{"id": "grelha", "tipo": "svg", "classe": "b-grelha", "rotulo": "Grelha", "texto": "linhas das células (com zoom)",
	 "detalhe": "linhas das células; aparecem quando há zoom suficiente"},
	{"id": "selecao", "tipo": "svg", "classe": "b-selecionada", "rotulo": "Selecionada", "texto": "célula aberta no painel",
	 "detalhe": "a célula aberta no painel da direita"},
]


def legend_for(profile):
	"""The legend table with the profile's symmetry rotation filled in (never a fixed 180°)."""
	rot = f"{profile.twin_rotation_deg():g}"
	return [{k: (v.replace("{rot}", rot) if isinstance(v, str) else v) for k, v in row.items()} for row in LEGEND]

ESTADO_TXT = {"solta": "solta", "emparelhada": "emparelhada (par de gémeas soltas)",
			  "posicao_conhecida": "posição conhecida (guardada à parte)", "colocada": "colocada",
			  "em_seccao": "num grupo sem lugar", "descartada": "descartada"}
CELL_TXT = {"vazia": "vazia", "ocupada_legado": "ocupada (sem silhueta)", "colocada": "colocada"}
CELL_SOURCE_TXT = {("ocupada_legado", "foto"): "cheia na foto, por confirmar (conta como vazia nas sugestões)",
				   ("ocupada_legado", "tiago"): "montada, marcada por ti (sem silhueta)",
				   ("vazia", "tiago"): "vazia, marcada por ti"}
HINT_ACTIONS = {"cell_full": "cell_full", "cell_empty": "cell_empty"}   # POST /api/confirm acao -> confirm() kwarg


def cell_text(cell: dict) -> str:
	"""Plain text of a board cell: state plus who says so (photo only vs the user)."""
	return CELL_SOURCE_TXT.get((cell["estado"], cell.get("fonte")), CELL_TXT.get(cell["estado"], cell["estado"]))
ORIGIN_TXT = {"gemeo": "gémea colocada", "borda": "borda", "par": "par de soltas",
			  "posicao_conhecida": "posição conhecida", "seccao": "grupo sem lugar", "buraco": "molde do buraco"}
_LOG_TIPO = {"servidor": "servidor", "preparar": "arranque", "importar": "importar"}
_LOG_TAG = re.compile(r"^\[(\w+)\]\s*")


def _activity_log(msg: str) -> None:
	"""Default ``Gui.log``: a ``[tag] text`` line goes to the activity logger of that tag (``[preparar]`` -> ``arranque``);
	a traceback is an error."""
	m = _LOG_TAG.match(str(msg))
	tipo = _LOG_TIPO.get(m.group(1), "servidor") if m else "servidor"
	text = str(msg)[m.end():] if m else str(msg)
	if text.startswith("Traceback") or text.startswith("ERRO"):
		activity.get("erro").error(text.rstrip())
	else:
		activity.get(tipo).info(text)


# ---------------------------------------------------------------- pure helpers
def _fmt(v, nd=2) -> str:
	return f"{v:.{nd}f}".replace(".", ",")


def missing_assets(project) -> list:
	"""Asset folders (``ASSET_DIRS``) missing or empty in a project that has pieces."""
	if not project.pieces:
		return []
	out = []
	for d in ASSET_DIRS:
		fp = project.p(d)
		if not os.path.isdir(fp) or not os.listdir(fp):
			out.append(d)
	return out


def board_snapshot(board, pieces: Optional[dict] = None) -> list:
	"""``[(estado, peca_id[, theta_deg, pose_manual_t]), ...]`` row-major: what the raster depends on per cell.

	With ``pieces`` (``Project.pieces``) each entry also carries the log pose of the cell's piece and the
	time stamp of its manual pose (``Piece.pose_manual['t']``, None without one), so a pose change alone
	(same piece, same cell) is a changed cell too (re-composed with its neighbours, :func:`patch_regions`)."""
	if pieces is None:
		return [(cell["estado"], cell["peca_id"]) for _, cell in board.iter_cells()]
	out = []
	for _, cell in board.iter_cells():
		p = pieces.get(cell["peca_id"]) if cell["peca_id"] else None
		pm = getattr(p, "pose_manual", None) if p is not None else None
		out.append((cell["estado"], cell["peca_id"], None if p is None else p.theta_deg,
					None if pm is None else pm.get("t")))
	return out


def changed_cells(old: list, new: list, cols: int) -> list:
	"""1-based cells whose snapshot entry differs."""
	return [(i // cols + 1, i % cols + 1) for i, (a, b) in enumerate(zip(old, new)) if a != b]


def patch_regions(cells, rows: int, cols: int) -> list:
	"""One region ``(l0, c0, l1, c1)`` per changed cell: the cell +/- 1, clamped, duplicates removed."""
	out = []
	for l, c in cells:
		r = (max(1, l - 1), max(1, c - 1), min(rows, l + 1), min(cols, c + 1))
		if r not in out:
			out.append(r)
	return out


def plain_reasons(e: dict, profile) -> list:
	"""Short Portuguese sentences for a "vai buscar" entry (shape distance, margin, image)."""
	cal = (profile.calibration or {}).get("silhueta_silhueta") or {}
	out = []
	if e.get("d1_mm") is not None:
		t = cal.get("t95")
		out.append(f"forma: diferença {_fmt(float(e['d1_mm']))} mm" + (f" (limite {_fmt(float(t))} mm)" if t else ""))
	if e.get("margin") is not None and e.get("origin") != "seccao":
		mm = (profile.calibration or {}).get("margin_min")
		out.append(f"margem para a 2.ª candidata: {_fmt(float(e['margin']), 1)}" + (f" (mínimo {_fmt(float(mm), 1)})" if mm else ""))
	if e.get("dE") is not None:
		out.append(f"imagem: ΔE {_fmt(float(e['dE']), 1)} contra a arte da célula")
	if e.get("origin") == "posicao_conhecida":
		out.append("tem agora uma vizinha montada: já pode ser colocada")
	if e.get("origin") == "borda" and e.get("decision") == "candidata":
		out.append("tem os lados lisos certos; a gémea desta célula não tem silhueta")
	if not e.get("pose_known") and e.get("piece"):
		out.append("rotação desconhecida: a imagem mostra a peça como foi digitalizada")
	return out


def _region_param(s: Optional[str], rows: int, cols: int) -> Optional[tuple]:
	if not s:
		return None
	v = [int(x) for x in re.split(r"[,\s]+", s.strip()) if x]
	if len(v) != 4:
		raise ValueError("region = l0,c0,l1,c1")
	l0, c0, l1, c1 = v
	l0, l1 = sorted((max(1, l0), min(rows, l1)))
	c0, c1 = sorted((max(1, c0), min(cols, c1)))
	return (l0, c0, l1, c1)


def _jpeg(img: np.ndarray, q: int = JPEG_Q) -> bytes:
	ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, int(q)])
	if not ok:
		raise ValueError("falha a codificar JPEG")
	return buf.tobytes()


def _finite(o):
	"""Copy of ``o`` with non-finite floats (inf / NaN, also numpy scalars) replaced by None, recursively in dicts,
	lists and tuples; everything else is returned as is (``_json_default`` handles the rest)."""
	if isinstance(o, float):
		return o if math.isfinite(o) else None
	if isinstance(o, dict):
		return {k: _finite(v) for k, v in o.items()}
	if isinstance(o, (list, tuple)):
		return [_finite(v) for v in o]
	if isinstance(o, np.floating):
		return float(o) if np.isfinite(o) else None
	return o


def _json_default(o):
	if isinstance(o, np.floating):
		return float(o)
	if isinstance(o, np.integer):
		return int(o)
	if isinstance(o, np.bool_):
		return bool(o)
	if isinstance(o, np.ndarray):
		return o.tolist()
	if isinstance(o, (set, tuple)):
		return list(o)
	raise TypeError(type(o).__name__)


# ---------------------------------------------------------------- server state
class Busy(RuntimeError):
	"""A write was attempted while a background job holds the project."""


class Gui:
	"""Project + locks + caches + event queue shared by the routes.

	``prepare``: run the start-up rule (rebuild missing assets, then warm the board raster
	and the ghosts) in a background thread. ``use_image``: image tie-break in the
	re-queries (``--no-image`` turns it off). ``uploads``: folder where imported scans are
	saved (default ``images/pieces/lotes/`` in the repo, so they can be committed and the
	assets rebuilt on another PC). ``queue``: run the import-queue worker thread (``False`` in
	tests that do not import; :meth:`stop` ends it).
	"""

	def __init__(self, project_path: str, *, prepare: bool = True, use_image: bool = True,
				 uploads: Optional[str] = None, log="activity", ring=None, queue: bool = True):
		self.path = os.path.abspath(project_path)
		self.pr = Project.open(self.path)
		self.use_image = use_image
		self.uploads = uploads or os.path.join(REPO, "images", "pieces", "lotes")
		# ``log``: "activity" (default) routes every line to :mod:`src.activity` (silent until ``activity.setup``);
		# a callable gets the line as before; None = silent.
		self.log = _activity_log if log == "activity" else (log or (lambda *a, **k: None))
		self.ring = ring if ring is not None else activity.RingHandler()
		self.ring.callback = lambda rec: self.emit("atividade", rec)
		self._trigger = "pedido"     # who asked for the next board (re)composition: arranque | escrita | externo | pedido
		self._alta = None            # (version, fit.alta_counter)
		self._holes_progress = None  # {n, N, segundos} while the strips of a cold hole ranking are computed
		self._holes_hit_logged = None
		self.wlock = threading.RLock()
		self.rlock = threading.RLock()
		self.cond = threading.Condition()
		self.events = collections.deque(maxlen=EVENTS_KEEP)
		self.seq = 0
		self.state = "pronto"
		self.job = None
		self.prep_log = []
		self.job_log = []
		self._known_stat = self._log_stat()
		self._board = None            # {ver, img, snap}
		self._small = {}              # ppc -> (ver, bytes)
		self._regions = collections.OrderedDict()
		self._pieces = collections.OrderedDict()
		self._sections = collections.OrderedDict()
		self._ghosts = None           # (ver, list)
		self._fetch = None            # (mtime, dict)
		self._placements = None       # (ver, dict)
		self._sheets = {}
		self._art = None
		self.ingest_segment = None    # tests: replacement for segment_scan
		self.stale_info = None        # start-up check of the assets against the log (render.stale_assets)
		self._sse_waiters = set()     # one asyncio.Event per connected SSE client (set by emit, from any thread)
		self._loop = None             # the server's event loop (stored by the first /api/events)
		self._job_queue = False       # True while ``job`` is the import queue's label (writes wait instead of 409)
		self._qcond = threading.Condition()
		self._qstop = False
		self._qthread = None
		self.iq = None
		if queue:
			self.iq = ImportQueue(os.path.join(self.path, "import_queue.jsonl"))
			back = self.iq.recover()
			if back:
				activity.get("importar").warning(f"fila: {', '.join(back)} interrompido(s) pelo reinício; de volta à cabeça da fila")
			with self._qcond:
				self._queue_label_locked()
			self._qthread = threading.Thread(target=self._queue_worker, name="fila-importacao", daemon=True)
			self._qthread.start()
		if prepare:
			threading.Thread(target=self._prepare, name="preparar", daemon=True).start()

	def stop(self, timeout: float = 5.0) -> None:
		"""End the import-queue worker (after the sheet in progress) and wake the SSE clients."""
		with self._qcond:
			self._qstop = True
			self._qcond.notify_all()
		if self._qthread is not None and self._qthread is not threading.current_thread():
			self._qthread.join(timeout)

	# ------------------------------------------------------------ events
	def emit(self, name: str, data=None) -> None:
		with self.cond:
			self.seq += 1
			self.events.append((self.seq, name, data if data is not None else {}))
			self.cond.notify_all()
			waiters, loop = list(self._sse_waiters), self._loop
		if loop is None or not waiters:
			return
		for ev in waiters:                           # emit runs in worker threads: wake the clients in their loop
			try:
				loop.call_soon_threadsafe(ev.set)
			except RuntimeError:                     # loop closed (server stopping)
				return

	def sse_register(self, ev, loop) -> None:
		with self.cond:
			self._loop = loop
			self._sse_waiters.add(ev)

	def sse_unregister(self, ev) -> None:
		with self.cond:
			self._sse_waiters.discard(ev)

	def _exclusive(self) -> bool:
		"""An exclusive background job holds the project (``job`` set by anything but the import queue): writes get 409."""
		return bool(self.job) and not self._job_queue

	def events_after(self, n: int) -> list:
		with self.cond:
			return [e for e in self.events if e[0] > n]

	# ------------------------------------------------------------ versions / sync
	def _log_stat(self) -> tuple:
		try:
			st = os.stat(self.pr.log_path)
			return (st.st_size, st.st_mtime_ns)
		except OSError:
			return (0, 0)

	def version(self) -> int:
		return self._log_stat()[0]

	def _pl_mtime(self) -> int:
		fp = self.pr.p("render", "placements.json")
		return os.stat(fp).st_mtime_ns if os.path.exists(fp) else 0

	def sync(self) -> None:
		"""Re-open the project if ``log.jsonl`` changed outside the server (CLI run)."""
		st = self._log_stat()
		if st == self._known_stat:
			return
		if not self.wlock.acquire(blocking=False):
			return                       # our own write in progress
		try:
			st = self._log_stat()
			if st != self._known_stat:
				self.pr = Project.open(self.path)
				self._known_stat = st
				self._placements = None
				self._alta = None
				self._trigger = "externo"
				self.log(f"[servidor] log.jsonl mudou fora do servidor: projeto reaberto (versão {st[0]})")
				self.emit("board_changed", {"versao": st[0], "externo": True})
				self.emit("fetch_changed", {})
		finally:
			self.wlock.release()

	def read(self, fn, tries: int = 4):
		"""Run a read, retrying when a concurrent write changed a dict under it."""
		for k in range(tries):
			try:
				return fn()
			except RuntimeError as e:
				if "changed size" not in str(e) or k == tries - 1:
					raise
				time.sleep(0.05)

	# ------------------------------------------------------------ start-up rule
	def _prep(self, msg: str) -> None:
		line = f"[preparar] {msg}"
		self.log(line)
		self.prep_log.append(msg)
		self.emit("prepare_progress", {"msg": msg})

	def activity_setup(self, *, console: bool = True, file: bool = True, stream=None):
		""":func:`src.activity.setup` with this project's ``logs/`` folder and this GUI's ring (the server's ``main``)."""
		return activity.setup(self.path if file else None, console=console, ring=self.ring, stream=stream)

	def activity_json(self, desde: Optional[int] = None, n: int = 300) -> dict:
		"""``GET /api/atividade``: the ring lines after ``desde`` (or the last ``n``), the types and levels."""
		recs = self.ring.after(int(desde)) if desde is not None else self.ring.last(n)
		return {"linhas": recs, "seq": self.ring.seq, "tipos": list(activity.TIPOS), "niveis": list(activity.NIVEIS),
				"ficheiro": self._activity_file()}

	def _activity_file(self) -> Optional[str]:
		for hd in logging.getLogger(activity.LOGGER).handlers:
			if isinstance(hd, activity.DailyFileHandler):
				return hd.path or hd.path_for(_dt.date.today())
		return None

	def _check_stale(self) -> None:
		"""Assets (npz, crops) against the log; stale sheets re-segmented (:func:`src.render.rebuild_stale`).
		Sets :attr:`stale_info` = ``{desatualizados_antes, folhas, refeitos, eventos, restantes, segundos, aviso,
		erros}``."""
		from src import render
		t0 = time.time()
		st = render.stale_assets(self.pr)
		info = {"desatualizados_antes": st["n_pecas"], "folhas": sorted(st["sheets"]), "refeitos": 0, "eventos": 0,
				"restantes": st["n_pecas"], "segundos": None, "aviso": None, "erros": []}
		if st["n_pecas"]:
			self.state = "a_preparar"
			self._prep(f"{st['n_pecas']} peças em {st['n_folhas']} folhas desatualizadas (depois de um git pull?): "
					   f"a refazer {', '.join(info['folhas'])}…")
			with self.wlock:
				r = render.rebuild_stale(self.pr, progress=self._prep)
				self._known_stat = self._log_stat()       # our own events (if any) are not an outside change
			left = r["depois"]["n_pecas"] if r.get("depois") else st["n_pecas"]
			info.update(refeitos=st["n_pecas"] - left, restantes=left, eventos=int(r.get("eventos") or 0),
						aviso=r.get("aviso"), erros=list(r.get("errors") or []))
			self._placements = None
			for e in info["erros"]:
				self._prep(f"ERRO: {e}")
			self._prep(info["aviso"] or f"ativos refeitos: {info['refeitos']} peças, 0 eventos"
					   + (f"; {left} ainda desatualizadas" if left else ""))
		info["segundos"] = round(time.time() - t0, 1)
		self.stale_info = info

	def _prepare(self) -> None:
		miss = missing_assets(self.pr)
		try:
			if miss:
				self.state = "a_preparar"
				self.emit("prepare_progress", {"msg": f"em falta: {', '.join(miss)}"})
				self._prep(f"pastas em falta ou vazias: {', '.join(miss)}; a regenerar a partir dos scans "
						   "(segmentação, recortes, folhas numeradas, limpeza, registo: pode demorar vários minutos)")
				from src import render
				with self.wlock:
					r = render.rebuild_assets(self.pr, progress=self._prep)
				for e in r.get("errors", []):
					self._prep(f"ERRO: {e}")
				self._prep("recursos regenerados" + (" com erros (ver acima)" if r.get("errors") else ""))
			self._check_stale()
			self._prep("a compor o tabuleiro")
			t0 = time.time()
			self._trigger = "arranque"
			self.board_jpg(BOARD_PPC)
			self._prep(f"tabuleiro pronto ({time.time() - t0:.1f} s; versão do log {self.version()})")
			t1 = time.time()
			self.ghosts()
			activity.get("arranque").info(f"fantasmas prontos ({time.time() - t1:.1f} s)")
		except Exception as e:  # noqa: BLE001 - the server must still come up; reported on the page
			self._prep(f"ERRO na preparação: {type(e).__name__}: {e}")
			self.log(traceback.format_exc())
		finally:
			self.state = "pronto"
			self.emit("ready", {"versao": self.version()})
			with self._qcond:                      # the import queue waits for the start-up rule
				self._qcond.notify_all()

	# ------------------------------------------------------------ fetch list
	def fetch(self) -> dict:
		from src.query import load_fetch
		fp = self.pr.p("fetch.json")
		mt = os.path.getmtime(fp) if os.path.exists(fp) else None
		if self._fetch is None or self._fetch[0] != mt:
			self._fetch = (mt, load_fetch(self.pr))
		return self._fetch[1]

	def fetch_entries(self) -> list:
		return [e for e in self.fetch().get("entries", []) if isinstance(e, dict)]

	# ------------------------------------------------------------ placements / poses
	def placements(self) -> dict:
		from src import render
		ver = self.version()
		if self._placements is None or self._placements[0] != ver:
			raw = render.load_placements(self.pr).get("placements") or {}
			# an entry registered for another cell / pose (log changed outside the server) is dropped:
			# compose_board then registers the piece on the fly from its current log pose
			fresh = {pid: e for pid, e in raw.items()
					 if pid in self.pr.pieces and e.get("key") == render._entry_key(self.pr, pid)}
			self._placements = (ver, fresh)
		return self._placements[1]

	def board_pose(self, pid: str) -> tuple:
		"""``(theta_deg | None, why)`` of a piece as it sits / will sit on the board."""
		from src import render
		p = self.pr.piece(pid)
		if p.estado == "colocada" and p.celula is not None:
			e = self.placements().get(pid)
			if e is not None and e.get("key") == render._entry_key(self.pr, pid):
				return float(e["theta_deg"]), "registo"
			th = render.registered_theta(self.pr, pid)
			return th, "registo (cantos)" if th is not None else "sem registo"
		for e in self.fetch_entries():
			if e.get("piece") == pid and e.get("pose_known") and e.get("theta_deg") is not None:
				return float(e["theta_deg"]), "proposta"
		if p.theta_deg is not None:
			return float(p.theta_deg), "log"
		return None, "desconhecida"

	def _susp_placements(self) -> dict:
		"""Poses for :func:`src.consistency.evaluate`: :meth:`placements`, plus the pieces registered on the fly
		without the image by an earlier pass (``_susp_pl``) while their key (cell, pose, anchor) holds. The
		caller stores the dict back in ``_susp_pl`` (``evaluate`` adds what it registers)."""
		from src import render
		memo = getattr(self, "_susp_pl", {})
		pl = {pid: e for pid, e in memo.items() if pid in self.pr.pieces and e.get("key") == render._entry_key(self.pr, pid)}
		pl.update(self.placements())
		return pl

	def suspeitas_json(self) -> dict:
		"""``{summary, items, falsos_alarmes, n_em_reports}``: :func:`src.consistency.evaluate` (suspects of the
		placed pieces, read-only; false alarms with an unchanged signature left out) joined with the open
		reports: each item gets ``report_aberto`` (the most recent open report of the same piece, or of the
		same cell when the report has no piece; else null) and ``n_em_reports`` counts the items that have one.

		Cached per log version and project object (a reopened project recomputes). The evaluation itself is
		kept apart (``_susp_eval``) so a report write, which only appends informative events, re-joins the
		reports without re-evaluating (:meth:`_reports_changed`). Poses: :meth:`_susp_placements`."""
		from src import consistency
		key = (self.version(), id(self.pr))
		c = getattr(self, "_suspeitas", None)
		if c is not None and c[0] == key:
			return c[1]
		ev = getattr(self, "_susp_eval", None)
		if ev is not None and ev[0] == key:
			r = ev[1]
		else:
			pl = self._susp_placements()
			r = consistency.evaluate(self.pr, pl)
			self._susp_pl = pl
			self._susp_eval = (key, r)
		out = self._join_reports(r)
		self._suspeitas = (key, out)
		return out

	def _join_reports(self, r: dict) -> dict:
		"""``r`` (an :func:`src.consistency.evaluate` result, not modified) with ``report_aberto`` per item and
		``n_em_reports`` (rule of ``openReportsFor`` in the GUI: same piece, or a report without piece on the
		same cell)."""
		from src import reports
		try:
			abertos = reports.list_reports(self.pr, only_open=True)
		except Exception as e:  # noqa: BLE001 - a broken reports file must not hide the suspects
			self.log(f"[servidor] reports ilegíveis na junção com as suspeitas: {e}")
			abertos = []
		by_piece, by_cell = {}, {}
		for rep in abertos:
			rid = rep.get("id")
			if not rid:
				continue
			if rep.get("piece"):
				by_piece.setdefault(rep["piece"], []).append(rid)
			elif rep.get("cell"):
				by_cell.setdefault((int(rep["cell"][0]), int(rep["cell"][1])), []).append(rid)

		def newest(ids):
			return max(ids, key=lambda x: (int(x[1:]) if x[1:].isdigit() else -1, x)) if ids else None

		items = [dict(it, report_aberto=newest(by_piece.get(it["piece"], []) + by_cell.get(tuple(it["cell"]), [])))
				 for it in r["items"]]
		return dict(r, items=items, n_em_reports=sum(it["report_aberto"] is not None for it in items))

	def _emit_suspeitas(self) -> Optional[dict]:
		"""SSE ``suspeitas_changed`` with the summary of :meth:`suspeitas_json` plus ``n_em_reports``; never raises
		(the suspects are informative; a failure is logged and None returned)."""
		try:
			s = self.suspeitas_json()
			data = dict(s["summary"], n_em_reports=s["n_em_reports"])
		except Exception as e:  # noqa: BLE001
			self.log(f"[servidor] suspeitas não recalculadas: {e}")
			return None
		self.emit("suspeitas_changed", data)
		return data

	def _reports_changed(self, key_before: tuple) -> None:
		"""After a report write (informative log events only): carry the evaluation over to the new log version
		when it was current before the write, drop the joined cache, emit ``suspeitas_changed``."""
		ev = getattr(self, "_susp_eval", None)
		if ev is not None and ev[0] == key_before:
			self._susp_eval = ((self.version(), id(self.pr)), ev[1])
		self._suspeitas = None
		self._emit_suspeitas()

	# ------------------------------------------------------------ hole mould (M11, src/fit.py): «candidatas para este buraco»
	def _fit_cache(self):
		"""One :class:`src.fit._Cache` (strips on disk in ``render/fit/strips.npz``, eroded sides in memory) bound to the
		current project object and calibration."""
		from src import fit as F
		cal = F.calibration(self.pr)
		c = getattr(self, "_fitc", None)
		if c is None or c.calib != cal:
			c = F._Cache(self.pr, cal)
			self._fitc = c
			activity.get("cache").info(f"tiras das peças: {c.n_loaded} em cache (render/fit/strips.npz)"
									   + ("" if c.n_loaded else "; a primeira lista de buracos calcula-as (≈ 0,3 s por peça)"))
		elif c.pr is not self.pr:
			c.rebind(self.pr)
		return c

	def _alta_counter(self) -> dict:
		"""``fit.alta_counter`` of the current log (cached per version)."""
		from src import fit as F
		ver = self.version()
		c = self._alta
		if c is None or c[0] != ver:
			c = (ver, F.alta_counter(self.pr))
			self._alta = c
		return c[1]

	def alta_json(self) -> dict:
		"""The ``alta`` hole suggestions for «Vai buscar» (M11_CRITERIOS §8): ``{a_calcular, em_pausa, contador,
		progresso, entries, conflitos, n_alta}``. Each entry has the shape of a fetch entry (``origin='buraco'``,
		``decision='alta'``, ``grupo='coloca_agora'``) plus ``hole`` (rank, J, margem, m, d1, d2, zona, vizinhas),
		``desenho`` (as ``GET /api/holes/{l}/{c}``), ``fundida_com_gemea`` (the accepted twin proposal says the same
		piece and cell: one card, two chips) and ``conflito_gemea`` (the twin proposal sends the piece elsewhere).
		While paused the entries are still returned (the GUI moves them to the «Buracos» page)."""
		from src import fit as F
		hj = self.holes_json(wait=False)
		cnt = self._alta_counter()
		out = {"a_calcular": bool(hj.get("a_calcular")), "em_pausa": bool(cnt["em_pausa"]), "contador": cnt,
			   "progresso": self._holes_progress if hj.get("a_calcular") else None, "entries": [], "conflitos": [],
			   "n_alta": 0, "erro": hj.get("erro")}
		if hj.get("a_calcular") or hj.get("erro"):
			return out
		twins = {}
		for e in self.fetch_entries():
			if e.get("piece") and e.get("cell") and e.get("origin") in ("gemeo", "borda") and e.get("decision") in ("aceite", "ambigua"):
				twins.setdefault(e["piece"], []).append((tuple(e["cell"]), e))
		rows = []
		for h in hj.get("buracos", []):
			if h["confianca"] != "alta" or not h["candidatas"]:
				continue
			out["n_alta"] += 1
			c0 = h["candidatas"][0]
			if int(c0["rank"]) != 1:
				continue
			if h.get("atribuida") not in (None, c0["piece"]):
				out["conflitos"].append({"cell": h["cell"], "piece": c0["piece"], "atribuida": h["atribuida"]})
				continue
			pid = c0["piece"]
			p = self.pr.pieces.get(pid)
			tw = twins.get(pid, [])
			same = [e for cl, e in tw if cl == tuple(h["cell"])]
			other = [cl for cl, _ in tw if cl != tuple(h["cell"])]
			e = {"origin": "buraco", "piece": pid, "lote": c0.get("lote"), "n_no_lote": c0.get("n_no_lote"), "scan_id": c0.get("scan_id"),
				 "cell": list(h["cell"]), "decision": "alta", "margin": h.get("margem"), "dE": None, "d1_mm": None, "query": None, "pair": None,
				 "rank": c0["rank"], "score": c0["J"], "phi_deg": None, "theta_deg": c0.get("theta_deg"),
				 "pose_known": c0.get("theta_deg") is not None, "grupo": "coloca_agora", "origem_txt": ORIGIN_TXT["buraco"],
				 "estado_atual": (p.estado if p is not None else None), "crop_path": (p.crop_path if p is not None else None),
				 "vizinhas_montadas": h["m"], "reasons": list(h.get("razoes") or []),
				 "razoes_txt": [f"{h['m']} vizinhas montadas ({', '.join(v['dir'] + ' ' + v['piece'] for v in h['vizinhas'])}): a forma e a imagem "
								f"dos lados encaixam (custo {_fmt(c0['J'])})",
								f"a 2.ª candidata fica a {('> 999' if (h.get('margem') or 0) > 999 else _fmt(h['margem']))}× (margem ≥ 1,5 exigida)"
								+ (f"; {h['n_finitas']} de {h['n_pool']} soltas com custo finito" if h.get("n_pool") else "")],
				 "hole": {"rank": c0["rank"], "J": c0["J"], "custo": c0["J"], "margem": h.get("margem"), "m": h["m"], "d1": h.get("d1"),
						  "d2": h.get("d2"), "zona": h.get("zona"), "vizinhas": h["vizinhas"], "confianca": h["confianca"],
						  "fit_version": F.FIT_VERSION, "candidatas": h["candidatas"]},
				 "fundida_com_gemea": bool(same), "gemea_decision": (same[0].get("decision") if same else None),
				 "twin_id": (same[0].get("twin_id") if same else None), "twin_cell": (same[0].get("twin_cell") if same else None),
				 "conflito_gemea": (list(other[0]) if other else None), "desenho": self._hole_drawing(h)}
			rows.append(e)
		rows.sort(key=lambda e: (-(e["margin"] or 0.0), e["piece"]))
		for i, e in enumerate(rows, 1):
			e["ordem"] = i
		out["entries"] = rows
		return out

	def resume_alta(self, body: dict) -> dict:
		"""``POST /api/holes/alta/reativar`` ``{nota?}``: log ``holes_alta_resumed`` (the pause window restarts)."""
		if not self.wlock.acquire(timeout=WRITE_WAIT_S):
			raise Busy(self.job or "ocupado")
		try:
			if self._exclusive():
				raise Busy(self.job)
			self.sync_locked()
			nota = str((body or {}).get("nota") or "").strip()[:200]
			cnt = self._alta_counter()
			ev = self.pr.resume_alta(autor="tiago", nota=nota)
			self.pr.save()
			self._known_stat = self._log_stat()
			self._alta = None
			activity.get("buracos").info(f"sugestões alta reativadas (janela anterior: {cnt['janela']['falhas']} falhas em {cnt['janela']['n']})")
			self.emit("fetch_changed", {})
			self.emit("holes_changed", {"versao": self.version(), "reativado": True})
			return {"ok": True, "evento": ev, "contador": self._alta_counter()}
		finally:
			self.wlock.release()

	def _holes_empty(self, key, **extra) -> dict:
		return {"versao": key[0], "a_calcular": True, "buracos": [], "resumo": {}, **extra}

	def holes_json(self, *, wait: bool = False) -> dict:
		"""``GET /api/holes``: every hole of the board (empty cell with >= 1 mounted neighbour with shape and pose)
		ranked against the loose pool by :func:`src.fit.rank_all` (joint assignment on), ordered by confidence.
		Cached per log version and project object; the first computation takes minutes (strips of the mounted
		neighbours, ~0.3 s each, then cached on disk), so it runs in a background thread and the answer says
		``a_calcular`` until it is done (SSE ``holes_changed``); ``wait=True`` blocks (tests, CLI)."""
		key = (self.version(), id(self.pr))
		c = getattr(self, "_holes", None)
		if c is not None and c[0] == key:
			if self._holes_hit_logged != key:
				self._holes_hit_logged = key
				activity.get("cache").info(f"buracos: cache usada (versão {key[0]}, {c[1].get('resumo', {}).get('n_buracos', 0)} buracos)")
			return c[1]
		th = getattr(self, "_holes_thread", None)
		if th is not None and th.is_alive():
			if not wait:
				return self._holes_empty(key)
			th.join()
			c = getattr(self, "_holes", None)
			if c is not None and c[0] == key:
				return c[1]
		if wait:
			return self._compute_holes(key)
		th = threading.Thread(target=self._compute_holes, args=(key,), daemon=True, name="holes")
		self._holes_thread = th
		th.start()
		return self._holes_empty(key)

	def _holes_progress_cb(self, n: int, N: int, secs: float) -> None:
		self._holes_progress = {"n": n, "N": N, "segundos": round(secs, 1)}
		activity.get("progresso").info(f"tiras das peças montadas e soltas: {n}/{N} ({secs:.0f} s)")
		self.emit("holes_progress", dict(self._holes_progress))

	def _compute_holes(self, key) -> dict:
		from src import fit as F
		t0 = time.time()
		activity.get("buracos").info(f"buracos: a recalcular o ranking (versão {key[0]})")
		try:
			cache = self._fit_cache()
			r = self.read(lambda: F.rank_all(self.pr, calib=cache.calib, cache=cache, progress=self._holes_progress_cb))
		except Exception as e:  # noqa: BLE001 - the ranking is informative; the GUI shows the error
			self.log(f"[servidor] buracos não calculados: {e}")
			r = {"error": str(e)}
		self._holes_progress = None
		out = self._holes_payload(r, key, time.time() - t0)
		self._holes = (key, out)
		rs = out["resumo"]
		tiras = r.get("tiras") or {}
		if "erro" in rs:
			activity.get("buracos").warning(f"buracos: sem ranking ({rs['erro']}) em {time.time() - t0:.1f} s")
		else:
			activity.get("buracos").info(f"buracos: {rs['n_buracos']} buracos × {rs['n_soltas']} soltas em {rs['segundos']} s; "
										 f"alta {rs['por_confianca'].get('alta', 0)} ({rs['alta_m2']} com ≥ 2 viz.), média {rs['por_confianca'].get('media', 0)}, "
										 f"sem {rs['por_confianca'].get('sem', 0)}; tiras calculadas {tiras.get('calculadas', 0)}, em cache {tiras.get('em_cache', 0)}")
		self.emit("holes_changed", dict(out["resumo"], versao=key[0]))
		return out

	@staticmethod
	def _hole_row(h: dict) -> dict:
		return {"cell": list(h["cell"]), "m": h["m"], "zona": h.get("zone"), "confianca": h["confidence"], "d1": h["d1"],
				"d2": h["d2"], "margem": h["margin"], "n_finitas": h["n_finite"], "n_pool": h["n_pool"], "atribuida": h.get("assigned"),
				"razoes": h["reasons"], "f_exigidos": h.get("f_required", []),
				"vizinhas": [{"dir": x["direction"], "piece": x["piece"], "kind": x.get("kind"), "scan_id": x.get("scan_id")} for x in h.get("sides", [])],
				"candidatas": [{"piece": c["id"], "lote": c["lote"], "n_no_lote": c["n_no_lote"], "scan_id": c.get("scan_id"), "rank": c["rank"],
								"J": c["J"], "rot": c["rot"], "theta_deg": c["theta_deg"],
								"melhor_para": (list(c["melhor_para"]) if c.get("melhor_para") else None), "por_lado": c["per_side"]}
							   for c in h["candidates"]]}

	def _holes_payload(self, r: dict, key, secs: float) -> dict:
		from src import fit as F
		if "error" in r:
			return {"versao": key[0], "a_calcular": False, "erro": r["error"], "buracos": [],
					"resumo": {"erro": r["error"], "n_buracos": r.get("n_holes", 0), "sigma": r.get("sigma")}}
		holes = [self._hole_row(h) for h in r["holes"]]
		cnt = collections.Counter(h["confianca"] for h in holes)
		resumo = {"n_buracos": r["n_holes"], "n_soltas": r["n_pool"], "sigma": r["sigma"], "n_sigma": r.get("n_sigma"),
				  "por_confianca": {k: cnt.get(k, 0) for k in F.CONFIDENCES},
				  "alta_m2": sum(1 for h in holes if h["confianca"] == "alta" and h["m"] >= 2),
				  "calibrado": bool(r["calib"].get("calibrated")), "versao_fit": F.FIT_VERSION, "segundos": round(secs, 1)}
		return {"versao": key[0], "a_calcular": False, "buracos": holes, "resumo": resumo, "calib": r["calib"]}

	def hole_json(self, l: int, c: int) -> dict:
		"""``GET /api/holes/{l}/{c}``: the ranking of one hole plus the drawing (contours in board units, as
		:meth:`pose_json`). While the full list is still being computed the cell is ranked alone (``parcial``: no
		joint assignment yet). ``{'buraco': False}`` when the cell is not a hole."""
		from src import fit as F
		if not self.pr.profile.in_grid(l, c):
			raise FileNotFoundError(f"célula ({l},{c}) fora da grelha")
		hj = self.holes_json(wait=False)
		h = next((x for x in hj.get("buracos", []) if x["cell"] == [l, c]), None)
		parcial = False
		if h is None:
			if not hj.get("a_calcular"):
				return {"cell": [l, c], "buraco": False, "a_calcular": False}
			cache = self._fit_cache()
			r = self.read(lambda: F.rank_all(self.pr, calib=cache.calib, cache=cache, cells=[(l, c)], joint=False))
			if "error" in r:
				if not r.get("n_holes"):
					return {"cell": [l, c], "buraco": False, "a_calcular": True, "erro": r["error"]}
				return {"cell": [l, c], "buraco": False, "erro": r["error"]}
			if not r["holes"]:
				return {"cell": [l, c], "buraco": False, "a_calcular": True}
			h = self._hole_row(r["holes"][0])
			parcial = True
		return dict(h, buraco=True, parcial=parcial, desenho=self._hole_drawing(h))

	def _hole_drawing(self, h: dict) -> dict:
		"""Contours for the hole layer / cards: the mounted neighbours as in :meth:`pose_json` and each candidate about
		its body centre, placed on the hole cell with the pose ``theta_deg`` of the ranking."""
		from src.locate import body_center_mm
		pr = self.pr
		l, c = h["cell"]
		viz = {}
		for d, q in self._neighbours_placed((l, c)).items():
			if q is None:
				viz[d] = None
				continue
			eq = self._effective_entry(q)
			if "error" in eq:
				viz[d] = None
				continue
			cq = pr.piece(q).celula
			viz[d] = {"piece": q, "cell": list(cq), "contorno": self._pose_contour(q, eq["pivot_mm"]), "svg": self._svg_of(cq, eq)}
		cands = []
		for cd in h["candidatas"]:
			sh = pr.shape(cd["piece"])
			if sh is None or cd.get("theta_deg") is None:
				cands.append(None)
				continue
			piv = body_center_mm(sh)
			e = {"theta_deg": float(cd["theta_deg"]), "dx_mm": 0.0, "dy_mm": 0.0}
			cands.append({"piece": cd["piece"], "contorno": self._pose_contour(cd["piece"], piv), "svg": self._svg_of((l, c), e),
						  "img": f"/api/pieces/{cd['piece']}.png?pose=scan&size=600"})
		w, hh = float(pr.profile.cell_mm["w"]), float(pr.profile.cell_mm["h"])
		return {"hr": hh / w, "vizinhas": viz, "candidatas": cands}

	def hole_action(self, l: int, c: int, body: dict, *, confirm_it: bool) -> dict:
		"""``POST /api/holes/{l}/{c}/confirmar`` | ``rejeitar``: the user placed (or refused) a candidate of the hole
		ranking; the event carries rank, custo, margem, confianca, m and ``fit_version`` (ground truth of
		``python -m src.fit --relatorio``). One write path with the CLI: :func:`src.confirm.confirm`."""
		from src import fit as F
		from src.confirm import confirm
		pid = body.get("piece") if isinstance(body, dict) else None
		gemea = bool(body.get("gemea")) if isinstance(body, dict) else False
		if not self.wlock.acquire(timeout=WRITE_WAIT_S):
			raise Busy(self.job or "ocupado")
		try:
			if self._exclusive():
				raise Busy(self.job)
			self.sync_locked()
			pr = self.pr
			if not pid or pid not in pr.pieces:
				return {"error": f"peça desconhecida {pid}"}
			if not pr.profile.in_grid(l, c):
				return {"error": f"célula ({l},{c}) fora da grelha"}
			h = self.hole_json(l, c)
			if "error" in h:
				return {"error": h["error"]}
			if not h.get("buraco"):
				return {"error": f"a célula ({l},{c}) não é um buraco (ocupada ou sem vizinha montada com forma e pose)"}
			cd = next((x for x in h["candidatas"] if x["piece"] == pid), None)
			meta = {"m": h["m"], "confianca": h["confianca"], "fit_version": F.FIT_VERSION, "margem": h.get("margem"),
					"rank": (cd["rank"] if cd else None), "custo": (cd["J"] if cd else None),
					"theta_deg": (cd["theta_deg"] if cd else None)}
			nota = str(body.get("nota") or "").strip()
			if nota:
				meta["nota"] = nota[:200]
			if cd is None:
				meta["nota"] = (meta.get("nota", "") + " fora do top-3 mostrado").strip()
			before = board_snapshot(pr.board, pr.pieces)
			t0 = time.time()
			kw = {"use_image": self.use_image}
			r = confirm(pr, pid, hole=((l, c), meta) if confirm_it else None, hole_reject=None if confirm_it else ((l, c), meta),
						gemea=gemea, **kw)
			if "error" in r:
				self._known_stat = self._log_stat()
				return {"error": r["error"]}
			if meta.get("confianca") == "alta" and meta.get("rank") == 1:
				self._alta = None
				cnt = self._alta_counter()
				activity.get("buracos").info(f"decisão alta {'confirmada' if confirm_it else 'REJEITADA'}: {pid} → ({l},{c}); contador "
											 f"{cnt['acertos']}/{cnt['falhas']}/{cnt['total']}, janela {cnt['janela']['falhas']} falhas em {cnt['janela']['n']}"
											 + ("; SUGESTÕES ALTA EM PAUSA" if cnt["em_pausa"] else ""))
			now = board_snapshot(pr.board, pr.pieces)
			placed = [p.id for p in pr.pieces.values() if p.estado == "colocada"
					  and before[(p.celula[0] - 1) * pr.profile.cols + p.celula[1] - 1]
					  != now[(p.celula[0] - 1) * pr.profile.cols + p.celula[1] - 1]]
			extra = self._after_write(before, placed)
			if not confirm_it:
				self.emit("board_changed", {"versao": self.version(), "celulas": [[l, c]]})
			return {"ok": True, "mensagens": r.get("messages", []), "invariantes": r.get("invariants", []),
					"segundos": round(time.time() - t0, 2), "meta": meta, **extra}
		finally:
			self.wlock.release()

	# ------------------------------------------------------------ board raster
	def _compose(self, ppc: float, region=None) -> np.ndarray:
		from src import render
		return self.read(lambda: render.compose_board(self.pr, ppc, region=region, layers=("art", "pieces"),
													  placements=self.placements()))

	def _disk_cache(self, ppc: int) -> tuple:
		d = self.pr.p("render", "gui")
		return os.path.join(d, f"board_{ppc}.jpg"), os.path.join(d, f"board_{ppc}.json")

	def _base(self) -> dict:
		"""The full-board raster at ``BOARD_PPC`` for the current log (composed / patched / from disk)."""
		ver = self.version()
		plm = self._pl_mtime()
		snap = self.read(lambda: board_snapshot(self.pr.board, self.pr.pieces))
		b = self._board
		if b is not None and b["ver"] == ver:
			return b
		jp, mp = self._disk_cache(BOARD_PPC)
		from_disk = False
		if b is None and os.path.exists(jp) and os.path.exists(mp):
			try:
				with open(mp, encoding="utf-8") as f:
					meta = json.load(f)
				img = cv2.imdecode(np.fromfile(jp, np.uint8), cv2.IMREAD_COLOR)
				if img is not None and meta.get("snap") is not None and meta.get("pl_mtime") == plm:
					b = {"ver": meta.get("ver"), "img": img, "snap": [tuple(x) for x in meta["snap"]], "jpg": None}
					from_disk = True
			except (OSError, ValueError):
				b = None
		rows, cols = self.pr.profile.rows, self.pr.profile.cols
		t0 = time.time()
		how = "completo"
		ver0 = None if b is None else b.get("ver")
		ch = []
		if b is not None:
			ch = changed_cells(b["snap"], snap, cols)
			if not ch:
				how = "sem mudanças"
			elif len(ch) <= PATCH_MAX_CELLS:
				img = b["img"]
				w, h = float(self.pr.profile.cell_mm["w"]), float(self.pr.profile.cell_mm["h"])
				ppm = BOARD_PPC / w
				for (l0, c0, l1, c1) in patch_regions(ch, rows, cols):
					sub = self._compose(BOARD_PPC, (l0, c0, l1, c1))
					x0, y0 = int(round((c0 - 1) * w * ppm)), int(round((l0 - 1) * h * ppm))
					hh, ww = min(sub.shape[0], img.shape[0] - y0), min(sub.shape[1], img.shape[1] - x0)
					img[y0:y0 + hh, x0:x0 + ww] = sub[:hh, :ww]
				how = f"{len(ch)} células recompostas"
			else:
				b = None
		if b is None:
			b = {"img": self._compose(BOARD_PPC)}
		b.update(ver=ver, snap=snap, jpg=_jpeg(b["img"]))
		self._board = b
		self._small = {}
		try:
			os.makedirs(os.path.dirname(jp), exist_ok=True)
			with open(jp, "wb") as f:
				f.write(b["jpg"])
			with open(mp, "w", encoding="utf-8") as f:
				json.dump({"ver": ver, "ppc": BOARD_PPC, "pl_mtime": self._pl_mtime(), "snap": snap}, f)
		except OSError as e:
			self.log(f"[servidor] cache do tabuleiro não gravada: {e}")
		trig, self._trigger = self._trigger, "pedido"
		if how != "sem mudanças":
			cells = (" " + ", ".join(f"({l},{c})" for l, c in ch)) if 0 < len(ch) <= 5 else ""
			activity.get("cache").info(f"tabuleiro {how}{cells} em {time.time() - t0:.1f} s (versão do log {ver0} → {ver}, gatilho: {trig}"
									   + (", a partir da cache do disco render/gui" if from_disk else "") + ")")
		return b

	def board_jpg(self, ppc: float = BOARD_PPC, region: Optional[tuple] = None) -> bytes:
		"""JPEG of the board (``region`` = (l0, c0, l1, c1) inclusive) at ``ppc`` px per cell."""
		ppc = float(ppc)
		prof = self.pr.profile
		with self.rlock:
			if region is None:
				if ppc > MAX_FULL_PPC:
					raise ValueError(f"tabuleiro inteiro só até ppc {MAX_FULL_PPC}; usa region=")
				b = self._base()
				if abs(ppc - BOARD_PPC) < 1e-6:
					return b["jpg"]
				key = round(ppc, 2)
				c = self._small.get(key)
				if c is not None and c[0] == b["ver"]:
					return c[1]
				w, h = float(prof.cell_mm["w"]), float(prof.cell_mm["h"])
				W = int(round(prof.cols * ppc))
				H = int(round(prof.rows * h / w * ppc))
				interp = cv2.INTER_AREA if ppc < BOARD_PPC else cv2.INTER_CUBIC
				data = _jpeg(cv2.resize(b["img"], (W, H), interpolation=interp))
				self._small[key] = (b["ver"], data)
				return data
			n_cells = (region[2] - region[0] + 1) * (region[3] - region[1] + 1)
			ppc = min(ppc, MAX_REGION_PPC)
			if n_cells * ppc * ppc > MAX_REGION_PX:
				raise ValueError(f"região grande demais para ppc {ppc:.0f} ({n_cells} células)")
			ver = self.version()
			key = (round(ppc, 1), region)
			c = self._regions.get(key)
			if c is not None and c[0] == ver:
				self._regions.move_to_end(key)
				return c[1]
			data = _jpeg(self._compose(ppc, region))
			self._regions[key] = (ver, data)
			while len(self._regions) > REGION_LRU:
				self._regions.popitem(last=False)
			return data

	def zoom_jpg(self, l: int, c: int, side: str = "both", dpi: float = 300) -> bytes:
		"""3 x 3 cells around ``(l, c)`` at ``dpi``: the render, the art, or both side by side."""
		from src import render
		prof = self.pr.profile
		reg = (max(1, l - 1), max(1, c - 1), min(prof.rows, l + 1), min(prof.cols, c + 1))
		dpi = float(min(max(dpi, 50), 300))
		key = ("zoom", side, round(dpi), reg)
		ver = self.version()
		with self.rlock:
			cc = self._regions.get(key)
			if cc is not None and cc[0] == ver:
				return cc[1]
		ppc = float(prof.cell_mm["w"]) / (25.4 / dpi)
		if side == "render":
			img = self._compose(ppc, reg)
		elif side == "art":
			img = self.read(lambda: render.compose_board(self.pr, ppc, region=reg, layers=("art",), art_alpha=1.0))
		else:
			img = self.read(lambda: render.compose_zone_vs_art(self.pr, reg, dpi, placements=self.placements()))
		data = _jpeg(img, 88)
		with self.rlock:
			self._regions[key] = (ver, data)
			while len(self._regions) > REGION_LRU:
				self._regions.popitem(last=False)
		return data

	# ------------------------------------------------------------ ghosts
	def ghosts(self) -> list:
		"""Ghost of every pending twin: ``{cell (target), piece (placed), from (its cell), path}``.

		``path`` = :func:`src.query.ghost_contour` (cell units about the target cell centre, x by
		the cell width, y by the cell height), using the profile's twin rotation."""
		from src.query import _Ctx, _pose, ghost_contour
		ver = self.version()
		if self._ghosts is not None and self._ghosts[0] == ver:
			return self._ghosts[1]

		def run():
			ctx = _Ctx(self.pr, use_image=False)
			ctx.placements = self.placements()
			out = []
			for q, tw in self.pr.pending_twins():
				pose = _pose(ctx, q.id)
				g = ghost_contour(self.pr.shape(q.id), pose, self.pr.profile) if pose else None
				if g:
					out.append({"cell": list(tw), "piece": q.id, "from": list(q.celula), "path": g})
			return out

		out = self.read(run)
		self._ghosts = (ver, out)
		return out

	def ghost_for(self, cell) -> Optional[dict]:
		for g in self.ghosts():
			if tuple(g["cell"]) == tuple(cell):
				return g
		return None

	# ------------------------------------------------------------ images of pieces / sheets / sections
	def piece_png(self, pid: str, pose: str = "board", size: int = 220) -> tuple:
		"""PNG (RGBA) of the cleaned crop: ``pose='board'`` turned as it sits / will sit on the board
		(placed: its registration; proposed: ``theta_deg`` of the list), else as scanned. The canvas
		spans ``SPAN_CELLS`` cell widths with the body centre in the middle. Returns
		``(bytes, pose_used, why, theta_deg | None)``."""
		from src.query import _body_center, _piece_image
		size = int(min(max(size, 32), PIECE_PX_MAX))
		theta, why = (None, "scan")
		if pose == "board":
			theta, why = self.read(lambda: self.board_pose(pid))
		key = (pid, round(theta, 2) if theta is not None else None, size, self.version() if pose == "board" else 0)
		c = self._pieces.get(key)
		if c is not None:
			self._pieces.move_to_end(key)
			return c
		ppm = size / (SPAN_CELLS * float(self.pr.profile.cell_mm["w"]))
		im = self.read(lambda: _piece_image(self.pr, pid, theta or 0.0, _body_center(self.pr.shape(pid)), size, ppm))
		if im is None:
			raise FileNotFoundError(f"{pid}: recorte em falta")
		bgr, al = im
		rgba = np.dstack([np.clip(bgr + 0.5, 0, 255).astype(np.uint8), np.clip(al[..., 0] * 255 + 0.5, 0, 255).astype(np.uint8)])
		ok, buf = cv2.imencode(".png", rgba)
		out = (buf.tobytes(), "board" if theta is not None else "scan", why, theta)
		self._pieces[key] = out
		while len(self._pieces) > PIECE_LRU:
			self._pieces.popitem(last=False)
		return out

	def sheet_jpg(self, scan_id: str, highlight: Optional[str] = None, max_px: int = SHEET_MAX_PX) -> bytes:
		"""Numbered scan sheet (:func:`src.ingest.sheet_overlay`), the piece ``highlight`` in amber; cached
		in ``render/gui/sheets/`` until the numbering of the scan changes."""
		from src.ingest import sheet_overlay
		from src.query import _sheet_signature
		max_px = int(min(max(max_px, 200), SHEET_MAX_PX))
		if scan_id not in self.pr.model.scans:
			raise FileNotFoundError(f"scan desconhecido {scan_id}")
		sig = self.read(lambda: _sheet_signature(self.pr, scan_id, highlight or ""))
		name = f"{scan_id}_{highlight or 'todas'}_{max_px}.jpg"
		fp = self.pr.p("render", "gui", "sheets", name)
		if self._sheets.get(name) == sig and os.path.exists(fp):
			with open(fp, "rb") as f:
				return f.read()
		img = self.read(lambda: sheet_overlay(self.pr, scan_id, highlight=highlight, max_px=max_px))
		data = _jpeg(img, 80)
		os.makedirs(os.path.dirname(fp), exist_ok=True)
		with open(fp, "wb") as f:
			f.write(data)
		self._sheets[name] = sig
		return data

	def section_png(self, gid: str, max_px: int = 360) -> bytes:
		"""Thumbnail of a group: its pieces' crops at their scan positions (the exploded view), on dark grey.

		Crops through the same display pipeline as the cards (:func:`src.render.piece_rgba_for_display`:
		fringe cleaned, premultiplied resize); kept in a small LRU per (group, size, log version)."""
		s = self.pr.sections.get(gid)
		if s is None:
			raise FileNotFoundError(f"secção desconhecida {gid}")
		key = (gid, int(max_px), self.version())
		c = self._sections.get(key)
		if c is not None:
			self._sections.move_to_end(key)
			return c
		data = self.read(lambda: self._section_png(s, max_px))
		self._sections[key] = data
		while len(self._sections) > SECTION_LRU:
			self._sections.popitem(last=False)
		return data

	def _section_png(self, s, max_px: int) -> bytes:
		from src import render
		items = []
		for pid in s.cells_local:
			p = self.pr.piece(pid)
			if not p.bbox:
				continue
			rgba = render.piece_rgba_for_display(self.pr, pid)
			if rgba is not None:
				items.append((p.bbox, rgba))
		if not items:
			raise FileNotFoundError(f"{s.id}: sem recortes")
		x0 = min(b[0] for b, _ in items)
		y0 = min(b[1] for b, _ in items)
		x1 = max(b[0] + r.shape[1] for b, r in items)
		y1 = max(b[1] + r.shape[0] for b, r in items)
		s_ = min(1.0, float(max_px) / max(x1 - x0, y1 - y0))
		W, H = max(1, int((x1 - x0) * s_)), max(1, int((y1 - y0) * s_))
		canvas = np.full((H, W, 3), 38, np.float32)
		for (bx, by, _, _), rgba in items:
			hh, ww = rgba.shape[:2]
			nw, nh = max(1, int(round(ww * s_))), max(1, int(round(hh * s_))),
			r = render.resize_rgba(rgba, (nw, nh)).astype(np.float32)
			ox, oy = int((bx - x0) * s_), int((by - y0) * s_)
			nh, nw = min(nh, H - oy), min(nw, W - ox)
			a = r[:nh, :nw, 3:4] / 255.0
			canvas[oy:oy + nh, ox:ox + nw] = r[:nh, :nw, 2::-1] * a + canvas[oy:oy + nh, ox:ox + nw] * (1 - a)
		ok, buf = cv2.imencode(".png", np.clip(canvas + 0.5, 0, 255).astype(np.uint8))
		return buf.tobytes()

	# ------------------------------------------------------------ JSON views
	def piece_summary(self, pid: str) -> dict:
		p = self.pr.piece(pid)
		return {"id": p.id, "lote": p.lote, "n_no_lote": p.n_no_lote, "estado": p.estado,
				"estado_txt": ESTADO_TXT.get(p.estado, p.estado), "celula": list(p.celula) if p.celula else None,
				"scan_id": p.scan_id, "seccao_id": p.seccao_id, "same_as": p.same_as, "cls": p.cls, "n_flat": p.n_flat,
				"chords_mm": p.chords_mm, "area_mm2": p.area_mm2, "flags": {k: v for k, v in p.flags.items() if v},
				"theta_deg": p.theta_deg, "contorno_manual": bool(p.flags.get(OV.MANUAL_FLAG)),
				"contorno_nota": p.flags.get(OV.MANUAL_NOTE_FLAG) or "",
				"pose_manual": None if p.pose_manual is None else {k: p.pose_manual.get(k) for k in
																	("theta_deg", "dx_mm", "dy_mm", "t", "nota")}}

	def board_json(self) -> dict:
		pr = self.pr
		prof = pr.profile
		rows = [[{"estado": cell["estado"], "peca_id": cell["peca_id"], "fonte": cell["fonte"]}
				 for cell in row] for row in pr.board.cells]
		known = [{"piece": p.id, "cell": list(p.celula), "lote": p.lote, "n_no_lote": p.n_no_lote}
				 for p in sorted(pr.pieces.values(), key=lambda q: q.id) if p.estado == "posicao_conhecida" and p.celula]
		st = pr.stats()
		n_occ = st["celulas_ocupadas"]
		n_placed = sum(1 for _, c in pr.board.iter_cells() if c["estado"] == "colocada")
		return {
			"projeto": pr.meta.get("id"), "puzzle": prof.name or prof.id,
			"rows": prof.rows, "cols": prof.cols, "cell_mm": prof.cell_mm, "hr": float(prof.cell_mm["h"]) / float(prof.cell_mm["w"]),
			"versao": self.version(), "board_ppc": BOARD_PPC, "span_cells": SPAN_CELLS,
			"cells": rows, "posicoes_conhecidas": known, "borda_em_falta": [list(x) for x in pr.missing_border_cells()],
			"progresso": {"colocadas": n_placed, "ocupadas": n_occ, "total": prof.cell_count(),
						  "sem_silhueta": n_occ - n_placed},
			"stats": st, "legend": legend_for(prof), "rotacao_gemea_deg": prof.twin_rotation_deg(),
			"calibracao": {"t95": ((prof.calibration or {}).get("silhueta_silhueta") or {}).get("t95"),
						   "margin_min": (prof.calibration or {}).get("margin_min")},
		}

	def fetch_json(self) -> dict:
		f = self.fetch()
		prof = self.pr.profile
		entries = []
		for e in self.fetch_entries():
			e = dict(e)
			e["razoes_txt"] = plain_reasons(e, prof)
			e["origem_txt"] = ORIGIN_TXT.get(e.get("origin"), e.get("origin"))
			if e.get("cell"):
				e["vizinhas_montadas"] = mounted_neighbours(self.pr, e["cell"])
				e["grupo"] = fetch_group(self.pr, e)
			pid = e.get("piece")
			if pid and pid in self.pr.pieces:
				e["estado_atual"] = self.pr.piece(pid).estado
			entries.append(e)
		try:
			alta = self.alta_json()
		except Exception as e:  # noqa: BLE001 - the twin list must never depend on the hole ranking
			self.log(f"[servidor] sugestões de buraco indisponíveis: {e}")
			alta = {"a_calcular": False, "em_pausa": False, "contador": None, "entries": [], "conflitos": [], "erro": str(e)}
		return {"t": f.get("t"), "entries": entries, "suprimidas": f.get("suprimidas", []),
				"notes": f.get("notes", []), "rest": len(f.get("rest", []) or []), "buracos_alta": alta}

	def cell_json(self, l: int, c: int) -> dict:
		pr = self.pr
		prof = pr.profile
		cell = pr.board[(l, c)]
		pid = cell["peca_id"]
		tw = prof.twin(l, c)
		tcell = pr.board[tw] if tw else None
		tpid = tcell["peca_id"] if tcell and tcell["estado"] == "colocada" else None
		props = [dict(e, razoes_txt=plain_reasons(e, prof), origem_txt=ORIGIN_TXT.get(e.get("origin"), e.get("origin")))
				 for e in self.fetch_entries()
				 if e.get("cell") and tuple(e["cell"]) == (l, c) and e.get("piece")]
		known = [self.piece_summary(p.id) for p in pr.pieces.values() if p.estado == "posicao_conhecida" and p.celula == (l, c)]
		neigh = []
		for (a, b), d in zip(((l - 1, c), (l, c + 1), (l + 1, c), (l, c - 1)), ("N", "E", "S", "O")):
			if prof.in_grid(a, b):
				nc = pr.board[(a, b)]
				neigh.append({"dir": d, "cell": [a, b], "estado": nc["estado"], "peca_id": nc["peca_id"], "fonte": nc["fonte"],
							  "ocupada": pr.board.occupied((a, b))})
		origin = None
		if pid:
			for ev in reversed(pr.events()):
				if ev.get("action") == "placed" and ev.get("piece") == pid:
					origin = ev.get("origin")
					break
				if ev.get("action") == "section_anchored" and any(x.get("piece") == pid for x in ev.get("placements", [])):
					origin = f"secção {ev.get('section')}"
					break
		reg = (max(1, l - 1), max(1, c - 1), min(prof.rows, l + 1), min(prof.cols, c + 1))
		return {
			"cell": [l, c], "estado": cell["estado"], "estado_txt": cell_text(cell),
			"por_confirmar": pr.board.unconfirmed((l, c)), "pista": cell["fonte"] == "tiago",
			"fonte": cell["fonte"], "borda": prof.is_border(l, c), "peca": self.piece_summary(pid) if pid else None,
			"origem": origin, "pode_desfazer": bool(pid and origin and not str(origin).startswith("secção")),
			"gemea": {"cell": list(tw) if tw else None, "estado": tcell["estado"] if tcell else None,
					  "peca": self.piece_summary(tpid) if tpid else None},
			"fantasma": self.ghost_for((l, c)) if cell["estado"] == "vazia" else None,
			"propostas": props, "conhecidas": known, "vizinhas": neigh,
			"zoom": {"region": list(reg), "render": f"/api/cell/{l}/{c}/zoom.jpg?side=render",
					 "arte": f"/api/cell/{l}/{c}/zoom.jpg?side=art"},
		}

	def lots_json(self) -> list:
		pr = self.pr
		by = {}
		for p in sorted(pr.pieces.values(), key=lambda q: (q.n_no_lote or 0, q.id)):
			by.setdefault(p.lote, {}).setdefault(p.scan_id, []).append(p)
		out = []
		for lote in sorted(by, key=lambda x: (x is None, x if x is not None else 0)):
			scans = by[lote]
			pcs = [p for ps in scans.values() for p in ps]
			cnt = collections.Counter(p.estado for p in pcs)
			sheets = []
			for sid in sorted(scans):
				sc = pr.model.scans.get(sid) or {}
				sheets.append({"scan_id": sid, "ficheiro": os.path.basename(sc.get("file") or ""), "kind": sc.get("kind"),
							   "n": len(scans[sid]), "url": f"/api/sheets/{sid}.jpg"})
			out.append({"lote": lote, "n": len(pcs), "por_estado": dict(cnt), "folhas": sheets,
						"pecas": [{"id": p.id, "n_no_lote": p.n_no_lote, "estado": p.estado, "scan_id": p.scan_id,
								   "celula": list(p.celula) if p.celula else None, "seccao_id": p.seccao_id}
								  for p in sorted(pcs, key=lambda q: (q.n_no_lote or 10 ** 6, q.id))]})
		return out

	def sections_json(self) -> list:
		from src.state import section_cell
		pr = self.pr
		prof = pr.profile
		out = []
		for s in sorted(pr.sections.values(), key=lambda s: s.id):
			if s.anchor.get("anchored"):
				continue
			if s.cells_local and all(pr.piece(pid).same_as for pid in s.cells_local):
				continue
			cands = []
			for k, cd in enumerate(s.candidates[:3], 1):
				if not cd.get("cell0"):
					continue
				a = {"l0": int(cd["cell0"][0]), "c0": int(cd["cell0"][1]), "rot": int(cd.get("rot") or 0),
					 "mirror": bool(cd.get("mirror"))}
				fp = [list(section_cell(a, rc)) for rc in s.cells_local.values()]
				ins = [x for x in fp if prof.in_grid(*x)]
				occ = sum(1 for x in ins if pr.board[tuple(x)]["estado"] == "colocada")
				cands.append({"rank": k, "cell0": [a["l0"], a["c0"]], "rot": a["rot"], "mirror": a["mirror"],
							  "score": cd.get("score"), "margin": cd.get("margin"), "footprint": fp,
							  "fora": len(ins) < len(fp), "ocupadas": occ})
			out.append({"id": s.id, "kind": s.kind, "scan_id": s.scan_id, "notes": s.notes, "n": len(s.cells_local),
						"pecas": [{"id": pid, "rc": list(rc), "n_no_lote": pr.piece(pid).n_no_lote,
								   "lote": pr.piece(pid).lote} for pid, rc in sorted(s.cells_local.items())],
						"candidatos": cands, "thumb": f"/api/sections/{s.id}.png"})
		return out

	def status_json(self) -> dict:
		try:
			cnt = self._alta_counter()
		except Exception:  # noqa: BLE001
			cnt = None
		return {"estado": self.state, "job": self.job, "prep_log": self.prep_log[-60:], "job_log": self.job_log[-60:],
				"versao": self.version(), "seq": self.seq, "projeto": self.pr.meta.get("id"), "ativos": self.stale_info,
				"contador_alta": cnt, "atividade_seq": self.ring.seq, "fila": self.queue_summary()}

	# ------------------------------------------------------------ writes
	def _after_write(self, before_snap: list, placed: list) -> dict:
		"""Refresh render assets of newly placed pieces, bump caches, emit events."""
		self._known_stat = self._log_stat()
		self._placements = None
		self._alta = None
		self._trigger = "escrita"
		if placed:
			self._refresh_render_assets(placed)
		snap = board_snapshot(self.pr.board, self.pr.pieces)
		ch = changed_cells(before_snap, snap, self.pr.profile.cols)
		self.emit("board_changed", {"versao": self.version(), "celulas": [list(x) for x in ch]})
		self.emit("fetch_changed", {})
		self._suspeitas = None
		self._emit_suspeitas()           # orientation suspects (read-only); never fails a write
		self._holes = None               # hole moulds changed (new neighbour / piece out of the pool / rejection): recompute in the background
		try:
			self.holes_json(wait=False)
		except Exception as e:  # noqa: BLE001
			self.log(f"[servidor] buracos não relançados: {e}")
		return {"celulas_mudadas": [list(x) for x in ch]}

	def _refresh_render_assets(self, pids: list) -> None:
		"""Cleaned crop + fine registration (with the image when available) of newly placed pieces,
		written to ``render/clean/`` and ``render/placements.json`` (as :func:`src.render.register_all`
		would, without its global relaxation pass)."""
		from PIL import Image
		from src import render
		try:
			if self._art is None and self.use_image:
				from src.locate import CellArt
				self._art = CellArt.load(self.pr.profile, REPO)
		except Exception as e:  # noqa: BLE001 - registration falls back to the corners
			self.log(f"[servidor] arte indisponível para o registo: {e}")
			self._art = False
		d = render.load_placements(self.pr)
		for pid in pids:
			p = self.pr.piece(pid)
			if p.estado != "colocada":
				continue
			try:
				rgba = self.pr.crop_rgba(pid)
				if rgba is not None:
					out = render.clean_crop(rgba, self.pr.profile.background_lab, render._scan_mmpp(self.pr, p.scan_id))
					os.makedirs(self.pr.p("render", "clean"), exist_ok=True)
					Image.fromarray(out).save(self.pr.p("render", "clean", f"{pid}.png"))
				r = render.register_piece(self.pr, pid, art=self._art or None, image=bool(self._art))
				if "error" not in r:
					r["key"] = render._entry_key(self.pr, pid)
					r["image_used"] = bool(self._art)
					d["placements"][pid] = r
			except Exception as e:  # noqa: BLE001 - the board still renders with the on-the-fly fallback
				self.log(f"[servidor] registo de {pid} falhou: {e}")
		d["log_len"] = render._log_len(self.pr)
		render.save_placements(self.pr, d)

	def confirm(self, body: dict) -> dict:
		"""Apply one action of the GUI (see ``POST /api/confirm``)."""
		from src.confirm import _around, confirm
		acao = str(body.get("acao") or "")
		pid = body.get("piece")
		cell = body.get("cell")
		if not self.wlock.acquire(timeout=WRITE_WAIT_S):
			raise Busy(self.job or "ocupado")
		try:
			if self._exclusive():
				raise Busy(self.job)
			self.sync_locked()
			pr = self.pr
			before = board_snapshot(pr.board, pr.pieces)
			if pid is not None and pid not in pr.pieces:
				return {"error": f"peça desconhecida {pid}"}
			kw = {"use_image": self.use_image}
			t0 = time.time()
			if acao == "place":
				if not cell:
					return {"error": "falta a célula"}
				r = confirm(pr, pid, cell=cell, origin=body.get("origin"), **kw)
			elif acao == "reject":
				r = confirm(pr, pid, reject=True, **kw)
			elif acao == "position_known":
				if not cell:
					return {"error": "falta a célula"}
				r = confirm(pr, pid, position_known=cell, origin=body.get("origin"), **kw)
			elif acao == "anchor":
				sec, c0 = body.get("section"), cell or body.get("cell0")
				if not sec or not c0:
					return {"error": "falta o grupo ou a célula do «É aqui»"}
				r = confirm(pr, anchor=(sec, int(c0[0]), int(c0[1])), rot=int(body.get("rot") or 0),
							mirror=bool(body.get("mirror")), **kw)
			elif acao == "unanchor":
				if not body.get("section"):
					return {"error": "falta a secção"}
				r = confirm(pr, unanchor=body["section"], **kw)
			elif acao == "discard":
				r = confirm(pr, pid, discard=True, reason=str(body.get("reason") or "gui"), **kw)
			elif acao == "unplace":
				r = self._unplace(pid, _around)
			elif acao in HINT_ACTIONS:
				try:
					hc = (int(cell[0]), int(cell[1]))
				except (TypeError, ValueError, IndexError):
					return {"error": "falta a célula"}
				if not pr.profile.in_grid(*hc):
					return {"error": f"célula {hc} fora da grelha"}
				r = confirm(pr, **{HINT_ACTIONS[acao]: [hc]}, **kw)
			else:
				return {"error": f"ação desconhecida {acao!r}"}
			if "error" in r:
				self._known_stat = self._log_stat()
				return {"error": r["error"]}
			# newly placed pieces and placed pieces whose pose changed: re-clean and re-register
			now = board_snapshot(pr.board, pr.pieces)
			placed = [p.id for p in pr.pieces.values() if p.estado == "colocada"
					  and before[(p.celula[0] - 1) * pr.profile.cols + p.celula[1] - 1]
					  != now[(p.celula[0] - 1) * pr.profile.cols + p.celula[1] - 1]]
			extra = self._after_write(before, placed)
			if acao in HINT_ACTIONS:
				# the hatch may stay the same (photo -> user): tell the clients the cell changed anyway
				if list(hc) not in extra["celulas_mudadas"]:
					extra["celulas_mudadas"].append(list(hc))
					self.emit("board_changed", {"versao": self.version(), "celulas": [list(hc)]})
				extra["celula"] = self.cell_json(*hc)
				extra["vizinhas"] = extra["celula"]["vizinhas"]
			return {"ok": True, "mensagens": r.get("messages", []), "invariantes": r.get("invariants", []),
					"n_propostas": len([e for e in r.get("entries", []) if e.get("piece")]),
					"segundos": round(time.time() - t0, 2), **extra}
		finally:
			self.wlock.release()

	def add_report(self, body: dict) -> dict:
		"""``POST /api/report``: save a capture of what is on screen and append the report.

		The log grows by an informative event only, so ``_known_stat`` is refreshed here and no board / fetch
		cache is invalidated (no ``board_changed`` / ``fetch_changed``); the suspects are re-joined with the
		reports (``report_aberto``) and ``suspeitas_changed`` is emitted (:meth:`_reports_changed`)."""
		from src import reports
		piece, cell = body.get("piece"), body.get("cell")
		if piece is not None and piece not in self.pr.pieces:
			return {"error": f"peça desconhecida {piece}"}
		if cell is not None:
			try:
				cell = (int(cell[0]), int(cell[1]))
			except (TypeError, ValueError, IndexError):
				return {"error": "célula inválida"}
			if not self.pr.profile.in_grid(*cell):
				return {"error": f"célula {cell} fora da grelha"}
		if not self.wlock.acquire(timeout=WRITE_WAIT_S):
			raise Busy(self.job or "ocupado")
		try:
			self.sync_locked()
			kb = (self.version(), id(self.pr))
			rid = reports.next_report_id(reports.read_reports(self.pr))
			data, ext = None, "jpg"
			try:
				if cell:
					data = self.read(lambda: self.zoom_jpg(cell[0], cell[1], "both"))
				elif piece:
					data, ext = self.read(lambda: self.piece_png(piece, "scan", 400))[0], "png"
			except Exception as e:  # noqa: BLE001 - the report is worth more than its capture
				self.log(f"[servidor] captura do relatório falhou: {e}")
				data = None
			cap = None
			if data:
				os.makedirs(self.pr.p("reports"), exist_ok=True)
				cap = f"reports/{rid}.{ext}"
				with open(self.pr.p(cap), "wb") as f:
					f.write(data)
			rep = reports.add_report(self.pr, tipo=str(body.get("tipo") or ""), texto=str(body.get("texto") or ""),
									 piece=piece, cell=cell, scan_id=None, vista=body.get("vista"), captura_path=cap)
			self._known_stat = self._log_stat()
			if "error" not in rep:
				self.emit("report_added", {"id": rep["id"]})
				self._reports_changed(kb)
			return rep
		finally:
			self.wlock.release()

	def edit_report(self, rid: str, body: dict) -> dict:
		"""``POST /api/report/{rid}/edit``: append an edit event to an open report (``reports.jsonl`` stays
		append-only); like :meth:`add_report` it changes no board / fetch cache and re-joins the suspects."""
		from src import reports
		if not self.wlock.acquire(timeout=WRITE_WAIT_S):
			raise Busy(self.job or "ocupado")
		try:
			self.sync_locked()
			kb = (self.version(), id(self.pr))
			rep = reports.edit_report(self.pr, rid, tipo=body.get("tipo"), texto=body.get("texto"))
			self._known_stat = self._log_stat()
			if "error" not in rep:
				self.emit("report_edited", {"id": rid})
				self._reports_changed(kb)
			return rep
		finally:
			self.wlock.release()

	def set_report_state(self, rid: str, acao: str, nota: str = "") -> dict:
		"""``POST /api/report/{rid}/estado``: one state event (close / reopen / delete / restore); like
		:meth:`add_report` it changes no board / fetch cache and re-joins the suspects."""
		from src import reports
		if not self.wlock.acquire(timeout=WRITE_WAIT_S):
			raise Busy(self.job or "ocupado")
		try:
			self.sync_locked()
			kb = (self.version(), id(self.pr))
			rep = reports.set_state(self.pr, rid, acao, nota)
			self._known_stat = self._log_stat()
			if "error" not in rep:
				self.emit("report_changed", {"id": rid, "estado": rep.get("estado")})
				self._reports_changed(kb)
			return rep
		finally:
			self.wlock.release()

	def dismiss_suspect(self, pid: str, body: dict) -> dict:
		"""``POST /api/suspeitas/{pid}/falso-alarme`` ``{grau, nota?}``: mark the current suspect ``(pid, grau)`` as
		a false alarm with the signature of the item as it is now (:func:`src.consistency.suspect_signature`,
		event ``suspect_dismissed``), then save, check the invariants, SSE ``suspeitas_changed``.
		``{ok, piece, grau, assinatura, summary, invariantes}``; ``{error}`` when the piece is not flagged with
		that grade (nothing written); FileNotFoundError (404) for an unknown piece; Busy (409)."""
		from src import consistency
		grau, nota = body.get("grau"), body.get("nota")
		if grau not in consistency.GRAUS:
			return {"error": f"grau inválido {grau!r} (um de {', '.join(consistency.GRAUS)})"}
		if nota is not None and not isinstance(nota, str):
			return {"error": "nota deve ser texto"}
		if not self.wlock.acquire(timeout=WRITE_WAIT_S):
			raise Busy(self.job or "ocupado")
		try:
			if self._exclusive():
				raise Busy(self.job)
			self.sync_locked()
			pr = self.pr
			if pid not in pr.pieces:
				raise FileNotFoundError(f"peça desconhecida {pid}")
			pl = self._susp_placements()
			r = consistency.evaluate(pr, pl, pieces=[pid], incluir_falsos=True)
			self._susp_pl = pl
			it = next((x for x in r["items"] if x["piece"] == pid and x["grau"] == grau), None)
			if it is None:
				return {"error": f"{pid} não está sinalizada como {grau}"}
			try:
				pr.dismiss_suspect(pid, grau, it["assinatura"], cell=it["cell"], nota=(nota or "").strip())
			except StateError as e:
				return {"error": str(e)}
			return self._after_suspect_write({"piece": pid, "grau": grau, "assinatura": it["assinatura"]})
		finally:
			self.wlock.release()

	def restore_suspect(self, pid: str, body: dict) -> dict:
		"""``POST /api/suspeitas/{pid}/restaurar`` ``{grau}``: undo a false-alarm mark (event ``suspect_restored``).
		``{ok, piece, grau, summary, invariantes}``; ``{error}`` if there is no such mark; 404 / 409 as
		:meth:`dismiss_suspect`."""
		from src import consistency
		grau = body.get("grau")
		if grau not in consistency.GRAUS:
			return {"error": f"grau inválido {grau!r} (um de {', '.join(consistency.GRAUS)})"}
		if not self.wlock.acquire(timeout=WRITE_WAIT_S):
			raise Busy(self.job or "ocupado")
		try:
			if self._exclusive():
				raise Busy(self.job)
			self.sync_locked()
			if pid not in self.pr.pieces:
				raise FileNotFoundError(f"peça desconhecida {pid}")
			try:
				self.pr.restore_suspect(pid, grau)
			except StateError as e:
				return {"error": str(e)}
			return self._after_suspect_write({"piece": pid, "grau": grau})
		finally:
			self.wlock.release()

	# ------------------------------------------------------------ manual pose («Editar posicionamento»)
	def _effective_entry(self, pid: str) -> dict:
		"""The pose the board shows (:func:`src.render.effective_pose` over :meth:`placements` and the on-the-fly
		registrations kept in ``_susp_pl``)."""
		from src import render
		return render.effective_pose(self.pr, pid, self._susp_placements())

	def _pose_placed(self, pid: str):
		"""The placed piece ``pid`` (FileNotFoundError if unknown, ValueError if not ``colocada``)."""
		if pid not in self.pr.pieces:
			raise FileNotFoundError(f"peça desconhecida {pid}")
		p = self.pr.piece(pid)
		if p.estado != "colocada" or p.celula is None:
			raise ValueError(f"{pid} não está colocada (está '{p.estado}')")
		return p

	def _pose_limits(self) -> dict:
		from src.state import POSE_MAX_FRAC
		cm = self.pr.profile.cell_mm
		return {"dx_max_mm": round(POSE_MAX_FRAC * float(cm["w"]), 4), "dy_max_mm": round(POSE_MAX_FRAC * float(cm["h"]), 4)}

	def _pose_body(self, body: dict) -> tuple:
		"""``(theta_deg, dx_mm, dy_mm)`` of a request body (ValueError with the reason, limits included)."""
		if not isinstance(body, dict):
			raise ValueError("o corpo deve ser um objeto JSON")
		vals = []
		for k in ("theta_deg", "dx_mm", "dy_mm"):
			v = body.get(k)
			if isinstance(v, bool) or not isinstance(v, (int, float)) or not np.isfinite(v):
				raise ValueError(f"{k} deve ser um número")
			vals.append(float(v))
		lim = self._pose_limits()
		if abs(vals[1]) > lim["dx_max_mm"] + 1e-9 or abs(vals[2]) > lim["dy_max_mm"] + 1e-9:
			raise ValueError(f"deslocamento ({vals[1]:.2f}, {vals[2]:.2f}) mm fora dos limites "
							 f"(±{lim['dx_max_mm']:.2f} × ±{lim['dy_max_mm']:.2f} mm)")
		return tuple(vals)

	def _svg_of(self, cell, e: dict) -> dict:
		"""Transform of a contour of :meth:`pose_json` into the board SVG (cell-width units, y = row × hr)."""
		w, h = float(self.pr.profile.cell_mm["w"]), float(self.pr.profile.cell_mm["h"])
		tx = (int(cell[1]) - 0.5) + float(e.get("dx_mm") or 0.0) / w
		ty = (int(cell[0]) - 0.5) * (h / w) + float(e.get("dy_mm") or 0.0) / w
		th = float(e["theta_deg"])
		return {"translate": [round(tx, 5), round(ty, 5)], "rotate_deg": round(th, 4),
				"transform": f"translate({tx:.5f} {ty:.5f}) rotate({th:.4f})"}

	def _pose_contour(self, pid: str, pivot_mm) -> list:
		"""``Shape.c`` (scan mm) relative to ``pivot_mm``, not rotated, divided by the cell width, <= ``POSE_CONTOUR_PTS``."""
		sh = self.pr.shape(pid)
		if sh is None:
			return []
		c = np.asarray(sh.c, float).reshape(-1, 2)
		idx = np.unique(np.linspace(0, len(c), min(POSE_CONTOUR_PTS, len(c)), endpoint=False).astype(int))
		g = (c[idx] - np.asarray(pivot_mm, float)) / float(self.pr.profile.cell_mm["w"])
		return [[round(float(x), 4), round(float(y), 4)] for x, y in g]

	def _neighbours_placed(self, cell) -> dict:
		"""``{N|E|S|W: piece id | None}``: the ``colocada`` pieces around ``cell``."""
		out = {}
		for d, (dl, dc) in POSE_DIRS.items():
			lc = (int(cell[0]) + dl, int(cell[1]) + dc)
			q = None
			if self.pr.profile.in_grid(*lc):
				cv = self.pr.board[lc]
				q = cv["peca_id"] if cv["estado"] == "colocada" else None
			out[d] = q
		return out

	def pose_json(self, pid: str) -> dict:
		"""``GET /api/pieces/{pid}/pose`` (docs/diagnostico/render/POSE_MANUAL.md §Contrato)."""
		from src import render
		p = self._pose_placed(pid)
		pr = self.pr
		w, h = float(pr.profile.cell_mm["w"]), float(pr.profile.cell_mm["h"])
		e = self._effective_entry(pid)
		if "error" in e:
			raise ValueError(e["error"])
		auto = e if not e.get("manual") else render.register_piece(pr, pid, art=None, image=False, manual=False)
		viz = {}
		for d, q in self._neighbours_placed(p.celula).items():
			if q is None:
				viz[d] = None
				continue
			eq = self._effective_entry(q)
			if "error" in eq:
				viz[d] = None
				continue
			cq = pr.piece(q).celula
			viz[d] = {"piece": q, "cell": list(cq), "theta_deg": float(eq["theta_deg"]), "dx_mm": float(eq.get("dx_mm") or 0.0),
					  "dy_mm": float(eq.get("dy_mm") or 0.0), "manual": bool(eq.get("manual")),
					  "contorno": self._pose_contour(q, eq["pivot_mm"]), "svg": self._svg_of(cq, eq)}
		pm = p.pose_manual
		return {"piece": pid, "cell": list(p.celula), "w_mm": w, "h_mm": h, "hr": h / w,
				"pivot_mm": [float(v) for v in e["pivot_mm"]],
				"efetiva": render.pose_brief(e), "automatica": {k: v for k, v in render.pose_brief(auto).items() if k != "manual"},
				"manual": None if pm is None else {k: pm.get(k) for k in ("theta_deg", "dx_mm", "dy_mm", "pivot_mm", "t", "nota")},
				"limites": self._pose_limits(), "contorno": self._pose_contour(pid, e["pivot_mm"]),
				"svg": self._svg_of(p.celula, e), "vizinhas": viz}

	def pose_evaluate(self, pid: str, body: dict) -> dict:
		"""``POST /api/pieces/{pid}/pose/avaliar``: the seams and the orientation check of a candidate pose, nothing
		written, no lock. ``{juntas: {N|E|S|W: {piece, gap_mm, gap_sil_mm} | None}, pior_mm, pior_dir, consistencia:
		{grau, falhas, texto}, ms}``."""
		t0 = time.time()
		th, dx, dy = self._pose_body(body)
		self._pose_placed(pid)
		out = self._evaluate_pose(pid, th, dx, dy)
		out["ms"] = round(1000 * (time.time() - t0), 1)
		return out

	def _evaluate_pose(self, pid: str, th: float, dx: float, dy: float, *, effective: bool = False) -> dict:
		"""Seams of ``pid`` with its placed neighbours (their effective poses) and the orientation grade, with the
		candidate pose (or, ``effective``, the stored one)."""
		from src import consistency, render
		pr = self.pr
		p = pr.piece(pid)
		cur = self._effective_entry(pid)
		cand = cur if effective else render.candidate_entry(pr, pid, th, dx, dy, pivot_mm=cur.get("pivot_mm"))
		nb = self._neighbours_placed(p.celula)
		pl = {pid: cand}
		for q in nb.values():
			if q is not None:
				eq = self._effective_entry(q)
				if "error" not in eq:
					pl[q] = eq
		shapes = {q: pr.shape(q) for q in pl}
		gaps = render.seam_gaps(pr, pl, shapes=shapes)
		inv = {"E": "W", "S": "N"}
		juntas = {d: None for d in POSE_DIRS}
		for g in gaps:
			if pid not in (g["a"], g["b"]):
				continue
			d = g["dir"] if g["a"] == pid else inv[g["dir"]]
			q = g["b"] if g["a"] == pid else g["a"]
			juntas[d] = {"piece": q, "gap_mm": round(float(g["gap_mm"]), 3), "gap_sil_mm": round(float(g["gap_sil_mm"]), 3)}
		vals = [(abs(j["gap_mm"]), d, j["gap_mm"]) for d, j in juntas.items() if j is not None]
		worst = max(vals) if vals else None
		pl_all = dict(self._susp_placements())
		pl_all.update(pl)
		r = consistency.evaluate(pr, pl_all, pieces=[pid], dismissed={}, incluir_pose_manual=True)
		it = next((x for x in r["items"] if x["piece"] == pid and x["grau"] in ("impossivel", "melhor_rotacao")), None)
		cons = ({"grau": None, "falhas": [], "texto": "sem falhas de orientação"} if it is None
				else {"grau": it["grau"], "falhas": it["falhas"], "texto": it["texto"]})
		return {"juntas": juntas, "pior_mm": None if worst is None else worst[2], "pior_dir": None if worst is None else worst[1],
				"consistencia": cons}

	def _pose_write(self, pid: str, fn) -> dict:
		"""Common cycle of the pose writes (under ``wlock``): ``fn(p, entry_before) -> extra dict`` logs the event,
		then save, invariants on disk, caches, incremental re-query of the cell / twin cell / free neighbours (the
		twin's proposal pose and ghost come from this pose), :meth:`_after_write` (``board_changed`` /
		``fetch_changed`` / ``suspeitas_changed``, the placement re-registered into ``placements.json``),
		``piece_changed``."""
		from src.confirm import _around
		from src.query import run_query
		if not self.wlock.acquire(timeout=WRITE_WAIT_S):
			raise Busy(self.job or "ocupado")
		try:
			if self._exclusive():
				raise Busy(self.job)
			self.sync_locked()
			t0 = time.time()
			try:
				p = self._pose_placed(pid)
			except ValueError as e:
				return {"error": str(e)}
			pr = self.pr
			before = board_snapshot(pr.board, pr.pieces)
			e0 = self._effective_entry(pid)
			if "error" in e0:
				return {"error": e0["error"]}
			try:
				extra = fn(p, e0)
			except StateError as e:
				return {"error": str(e)}
			pr.save()
			bad = pr.check_invariants(disk=True)
			self._known_stat = self._log_stat()
			self._placements = None
			memo = getattr(self, "_susp_pl", None)
			if memo:
				memo.pop(pid, None)
			if not bad:
				run_query(pr, only_cells=_around(pr, p.celula), only_pieces=set(), use_image=self.use_image)
			w = self._after_write(before, [pid])
			self.emit("piece_changed", {"piece": pid})
			return dict(extra, ok=True, piece=pid, invariantes=bad, segundos=round(time.time() - t0, 2), **w)
		finally:
			self.wlock.release()

	def set_pose(self, pid: str, body: dict) -> dict:
		"""``POST /api/pieces/{pid}/pose`` ``{theta_deg, dx_mm, dy_mm, nota?}``: event ``pose_set`` (pivot = the one of the
		current effective pose) -> ``{ok, piece, antes, depois, juntas, invariantes, segundos, celulas_mudadas}``."""
		from src import render
		th, dx, dy = self._pose_body(body)
		nota = body.get("nota")
		if nota is not None and not isinstance(nota, str):
			raise ValueError("nota deve ser texto")

		def do(p, e0):
			antes = render.pose_brief(e0, full=True)      # the automatic pose, kept whole: the pair (auto, manual) is the GT of --pares
			self.pr.set_pose(pid, th, dx, dy, nota=(nota or "").strip(), antes=antes, pivot_mm=e0["pivot_mm"])
			return {"antes": antes}

		r = self._pose_write(pid, do)
		if "error" not in r:
			r["depois"] = render.pose_brief(self._effective_entry(pid))
			r["juntas"] = self._evaluate_pose(pid, 0.0, 0.0, 0.0, effective=True)["juntas"]
		return r

	def clear_pose(self, pid: str) -> dict:
		"""``POST /api/pieces/{pid}/pose/repor``: event ``pose_cleared`` -> ``{ok, piece, antes, automatica, juntas,
		invariantes, segundos, celulas_mudadas}`` (``{error}`` if the piece has no manual pose)."""
		from src import render

		def do(p, e0):
			antes = render.pose_brief(e0)
			self.pr.clear_pose(pid, antes={k: antes[k] for k in ("theta_deg", "dx_mm", "dy_mm")})
			return {"antes": antes}

		r = self._pose_write(pid, do)
		if "error" not in r:
			r["automatica"] = render.pose_brief(self._effective_entry(pid))
			r["juntas"] = self._evaluate_pose(pid, 0.0, 0.0, 0.0, effective=True)["juntas"]
		return r

	def _after_suspect_write(self, out: dict) -> dict:
		"""Save, invariants on disk, drop the suspects caches, SSE ``suspeitas_changed`` (under ``wlock``)."""
		self.pr.save()
		bad = self.pr.check_invariants(disk=True)
		self._known_stat = self._log_stat()
		self._suspeitas = None
		self._susp_eval = None
		summ = self._emit_suspeitas()
		return dict(out, ok=True, summary=summ, invariantes=bad)

	def report_capture(self, rid: str) -> Optional[str]:
		"""Absolute path of the capture of report ``rid`` (``None`` if there is none)."""
		from src import reports
		rep = next((r for r in reports.read_reports(self.pr) if r.get("id") == rid), None)
		cap = rep.get("captura") if rep else None
		if not cap:
			return None
		fp = os.path.abspath(self.pr.p(cap))
		root = os.path.abspath(self.pr.p("reports")) + os.sep
		return fp if fp.startswith(root) and os.path.isfile(fp) else None

	# ------------------------------------------------------------ contour editor (manual overrides, §18)
	def _scan_rgb(self, sid: str) -> np.ndarray:
		"""The scan as RGB, the last one kept in memory (the editor asks for the same sheet repeatedly)."""
		fp = OV.scan_file(self.pr, sid)
		key = (sid, fp, os.path.getmtime(fp) if fp and os.path.exists(fp) else None)
		c = getattr(self, "_scan_cache", None)
		if c is not None and c[0] == key:
			return c[1]
		rgb = OV.load_scan_rgb(self.pr, sid)
		self._scan_cache = (key, rgb)
		return rgb

	def contour_json(self, pid: str) -> dict:
		"""``GET /api/pieces/{pid}/contorno``: the editor's crop (bbox + ``MARGIN_MM``) and, in crop px,
		``denso`` = the current outline (the latest manual override, else the stored pixel chain),
		``contour`` = the handles (about every
		``RESAMPLE_MM``, corners kept) and ``indices`` = each handle's index in ``denso``. The client
		saves the handles with the untouched stretches expanded back to ``denso``
		(:func:`src.overrides.expand_polygon`), so an unchanged save keeps the shape exactly."""
		from src import render
		pr = self.pr
		p = pr.piece(pid)
		x0, y0, x1, y1, m = OV.crop_window(pr, pid)
		mmpp = render._scan_mmpp(pr, p.scan_id)
		ov = OV.latest_overrides(pr).get(pid)
		dense, _ = self._dense(pid)
		idx = OV.editor_indices(dense, OV.RESAMPLE_MM / mmpp)
		tracos = []
		if ov is not None and ov.get("metodo") == "tracos" and ov.get("tracos") and ov.get("origem"):
			# the strokes were drawn on the crop of that save; the bbox (hence the crop) may have changed since
			tracos = ST.traduzir_tracos(ov["tracos"], ov["origem"][0] - x0, ov["origem"][1] - y0)
		dloc = np.round(dense - np.array([x0, y0], float), 2)
		loc = dloc[idx]
		return {"scan_id": p.scan_id, "piece": pid, "lote": p.lote, "n_no_lote": p.n_no_lote, "estado": p.estado,
				"celula": list(p.celula) if p.celula else None,
				"bbox": p.bbox, "margem_px": int(m), "origem": [int(x0), int(y0)],
				"tamanho": [int(x1 - x0), int(y1 - y0)], "mmpp": mmpp, "passo_px": OV.RESAMPLE_MM / mmpp,
				"crop_png_url": f"/api/pieces/{pid}/contorno.png?v={self.version()}",
				"contour": loc.tolist(), "denso": dloc.tolist(), "indices": [int(i) for i in idx],
				"manual_override": bool(p.flags.get(OV.MANUAL_FLAG)),
				"override_pendente": ov is not None and not p.flags.get(OV.MANUAL_FLAG),
				"nota": (ov or {}).get("nota") or p.flags.get(OV.MANUAL_NOTE_FLAG) or "",
				"cls": p.cls, "chords_mm": p.chords_mm, "area_mm2": p.area_mm2,
				"limites": {"min_pontos": OV.MIN_POINTS, "area_min": OV.AREA_MIN_FRAC, "area_max": OV.AREA_MAX_FRAC},
				"tracos": tracos, "banda_mm": ST.BANDA_MM, "solver_omissao": ST.SOLVER_OMISSAO,
				"solvers": list(ST.SOLVERS)}

	def _dense(self, pid: str) -> tuple:
		"""``(polygon in scan px, origem)`` of the piece's current outline: the latest manual override
		(``"manual"``), else the stored pixel chain of the segmentation (``"segmentacao"``; exact, so an
		unchanged save keeps the shape)."""
		pr = self.pr
		ov = OV.latest_overrides(pr).get(pid)
		if ov is not None:
			return OV.clean_polygon(ov["contour_px"]), "manual"
		c = pr.contour_px(pid)
		if c is None:
			raise FileNotFoundError(f"{pid}: contorno em falta (pieces/{pr.piece(pid).scan_id}.npz)")
		return OV.clean_polygon(c), "segmentacao"

	def _bg_lab(self, sid: str) -> np.ndarray:
		"""Background colour of the scan (OpenCV 8-bit Lab, :func:`src.segmentation._rim_background`),
		the last one kept (only the ``limiar`` solver needs it)."""
		from src import render
		from src.segmentation import _rim_background
		c = getattr(self, "_bg_cache", None)
		rgb = self._scan_rgb(sid)
		if c is not None and c[0] == sid and c[1] is rgb:
			return c[2]
		bg = _rim_background(cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32), render._scan_mmpp(self.pr, sid))
		self._bg_cache = (sid, rgb, bg)
		return bg

	@staticmethod
	def _solver_spec(body: dict) -> tuple:
		"""``(name, params)`` from ``{solver?: name | {nome, params}, iter?}`` (ValueError if invalid)."""
		sv = body.get("solver")
		params = {}
		if isinstance(sv, dict):
			params = dict(sv.get("params") or {})
			sv = sv.get("nome")
		sv = sv or ST.SOLVER_OMISSAO
		if sv not in ST.SOLVERS:
			raise ValueError(f"solver desconhecido {sv!r} ({', '.join(ST.SOLVERS)})")
		it = body.get("iter")
		if it is not None:
			if isinstance(it, bool) or not isinstance(it, int) or not 1 <= it <= 10:
				raise ValueError("iter deve ser um inteiro entre 1 e 10")
			if sv == "grabcut":
				params["iters"] = it
		return sv, ST.parametros(sv, params)

	def _strokes_window(self, pid: str, body: dict) -> tuple:
		"""``(normalised strokes, (x0, y0, w, h))`` of a ``{tracos, origem?, tamanho?}`` body."""
		x0, y0, w, h = self._window(pid, body.get("origem"), body.get("tamanho"))
		tr, err = ST.validar_tracos(body.get("tracos"), w, h)
		if err:
			raise ValueError(err)
		return tr, (x0, y0, w, h)

	def contour_solve(self, pid: str, body: dict) -> dict:
		"""``POST /api/pieces/{pid}/contorno/resolver``: strokes -> trimap -> solver -> polygon on the
		editor crop (:func:`src.strokes.resolver`), validated as a save would be
		(:func:`src.overrides.check_override`). Writes nothing; no write lock. ValueError on a bad body."""
		from src import render
		t0 = time.perf_counter()
		pr = self.pr
		p = pr.piece(pid)
		tr, (x0, y0, w, h) = self._strokes_window(pid, body)
		name, params = self._solver_spec(body)
		mmpp = render._scan_mmpp(pr, p.scan_id)
		rgb = self._scan_rgb(p.scan_id)[y0:y0 + h, x0:x0 + w]
		dense, _ = self._dense(pid)
		auto = np.zeros((h, w), np.uint8)
		cv2.fillPoly(auto, [np.round(dense - np.array([x0, y0], float)).astype(np.int32).reshape(-1, 1, 2)], 1)
		bg = self._bg_lab(p.scan_id) if name == "limiar" else None
		delta = self._delta(pid, (x0, y0, w, h), name, params, rgb, auto > 0, mmpp, bg)
		r = ST.resolver(rgb, auto > 0, tr, mmpp, solver=name, params=params, bg_lab=bg, normalizar_indice=True, delta=delta)
		if "error" in r:
			return {"contour": [], "area_mm2": 0.0, "valido": False, "erro": r["error"], "solver": name,
					"params": params, "mascara_rle": None, "n_pontos": 0, "origem": [x0, y0], "tamanho": [w, h],
					"ms": round((time.perf_counter() - t0) * 1000.0, 1), "ms_solver": None,
					"aresta": [], "delta_mm": delta["delta_mm"], "identidade": False, "tracos_ignorados": []}
		cnt = r["contour"]
		_, err = OV.check_override(pr, pid, cnt + np.array([x0, y0], float))
		return {"contour": cnt.astype(int).tolist(), "area_mm2": round(r["area_mm2"], 3), "valido": err is None,
				"erro": err, "solver": name, "params": params, "mascara_rle": ST.rle_encode(r["mask"]),
				"n_pontos": int(len(cnt)), "origem": [int(x0), int(y0)], "tamanho": [int(w), int(h)],
				"ms_solver": round(r["ms"], 1), "ms": round((time.perf_counter() - t0) * 1000.0, 1),
				"aresta": np.asarray(r["aresta"]).astype(int).tolist(), "delta_mm": round(float(r["delta_mm"]), 3),
				"identidade": bool(r["identidade"]), "tracos_ignorados": [int(i) for i in r.get("tracos_ignorados", [])],
				"convencao": "indice"}

	def _delta(self, pid: str, win: tuple, name: str, params: dict, rgb, auto, mmpp: float, bg) -> dict:
		"""Cached :func:`src.strokes.delta_peca` of the piece's current outline on this crop / solver (the
		editor asks several times per session; one GrabCut run per key). Keyed by the log version, so a
		save (new outline) refreshes it."""
		key = (pid, tuple(int(v) for v in win), name, json.dumps(params, sort_keys=True), self.version())
		c = getattr(self, "_delta_cache", None)
		if c is None or c[0] != key:
			d = ST.delta_peca(rgb, auto, mmpp, name, params, bg)
			self._delta_cache = (key, d)
			return d
		return c[1]

	def _save_extra(self, pid: str, body: dict, pts: np.ndarray, win: tuple) -> dict:
		"""Extra fields of the ``overrides.jsonl`` line of a GUI save (:data:`src.overrides.EXTRA_KEYS`):
		the outline being replaced (``auto_contour_px``, ``auto_area_mm2``, ``auto_origem``), ``metodo``
		and, for a stroke save, the strokes (crop px), the crop, the solver and the RLE of the saved
		polygon filled in the crop (computed here; a client ``mascara_rle`` is only checked for size)."""
		from src import render
		mmpp = render._scan_mmpp(self.pr, self.pr.piece(pid).scan_id)
		dense, origem = self._dense(pid)
		extra = {"auto_contour_px": np.round(dense).astype(int).tolist(),
				 "auto_area_mm2": round(OV.polygon_area(dense) * mmpp * mmpp, 3), "auto_origem": origem,
				 "metodo": "vertices", "convencao": "indice"}
		dm = body.get("delta_mm")
		if isinstance(dm, (int, float)) and not isinstance(dm, bool) and np.isfinite(dm):
			extra["delta_mm"] = round(float(dm), 3)
		if body.get("tracos") is None:
			return extra
		tr, (x0, y0, w, h) = self._strokes_window(pid, body)
		name, params = self._solver_spec(body)
		cm = body.get("mascara_rle")
		if cm is not None:
			got = ST.rle_decode(cm)
			if got.shape != (h, w):
				raise ValueError(f"mascara_rle com {got.shape[1]} x {got.shape[0]} px; o recorte tem {w} x {h}")
		m = np.zeros((h, w), np.uint8)
		cv2.fillPoly(m, [np.round(np.asarray(pts, float) - np.array([x0, y0], float)).astype(np.int32).reshape(-1, 1, 2)], 1)
		extra.update(metodo="tracos", tracos=ST.traduzir_tracos(tr, 0.0, 0.0), origem=[int(x0), int(y0)],
					 tamanho=[int(w), int(h)], solver={"nome": name, "params": params}, mascara_rle=ST.rle_encode(m > 0))
		return extra

	def _window(self, pid: str, origem=None, tamanho=None) -> tuple:
		"""``(x0, y0, w, h)`` of the editor crop: the client's (validated) or the current one."""
		x0, y0, x1, y1, _ = OV.crop_window(self.pr, pid)
		if origem is None:
			return x0, y0, x1 - x0, y1 - y0
		W, H = OV.scan_size(self.pr, self.pr.piece(pid).scan_id)
		try:
			ox, oy = int(origem[0]), int(origem[1])
			w, h = (int(tamanho[0]), int(tamanho[1])) if tamanho is not None else (x1 - x0, y1 - y0)
		except (TypeError, ValueError, IndexError):
			raise ValueError("origem / tamanho inválidos")
		if ox < 0 or oy < 0 or w < 1 or h < 1 or ox + w > W or oy + h > H:
			raise ValueError(f"recorte ({ox}, {oy}, {w}, {h}) fora do scan ({W} x {H})")
		return ox, oy, w, h

	def contour_png(self, pid: str) -> bytes:
		"""``GET /api/pieces/{pid}/contorno.png``: the scan crop of the editor (RGB, no alpha)."""
		x0, y0, w, h = self._window(pid)
		rgb = self._scan_rgb(self.pr.piece(pid).scan_id)
		ok, buf = cv2.imencode(".png", np.ascontiguousarray(rgb[y0:y0 + h, x0:x0 + w, ::-1]))
		return buf.tobytes()

	def _scan_points(self, pid: str, body: dict) -> tuple:
		"""``(points in scan px, (x0, y0, w, h))`` from ``{contour (crop px), origem?, tamanho?}``."""
		cnt = body.get("contour")
		if not isinstance(cnt, list) or not cnt:
			raise ValueError("falta o contorno (lista de pontos [x, y])")
		x0, y0, w, h = self._window(pid, body.get("origem"), body.get("tamanho"))
		try:
			pts = np.asarray(cnt, float).reshape(-1, 2) + np.array([x0, y0], float)
		except (TypeError, ValueError):
			raise ValueError("contorno inválido: esperava uma lista de pontos [x, y]")
		return pts, (x0, y0, w, h)

	def contour_preview(self, pid: str, body: dict) -> bytes:
		"""``POST /api/pieces/{pid}/contorno/preview``: the crop as RGBA, alpha = the drawn outline (the
		same validation as the save; nothing is written)."""
		pts, (x0, y0, w, h) = self._scan_points(pid, body)
		clean, err = OV.check_override(self.pr, pid, pts)
		if err:
			raise ValueError(err)
		rgb = self._scan_rgb(self.pr.piece(pid).scan_id)
		al = np.zeros((h, w), np.uint8)
		cv2.fillPoly(al, [np.round(clean - np.array([x0, y0], float)).astype(np.int32).reshape(-1, 1, 2)], 255)
		bgra = np.dstack([np.ascontiguousarray(rgb[y0:y0 + h, x0:x0 + w, ::-1]), al])
		ok, buf = cv2.imencode(".png", bgra)
		return buf.tobytes()

	def save_contour(self, pid: str, body: dict) -> dict:
		"""``POST /api/pieces/{pid}/contorno``: validate, append to ``overrides.jsonl``, apply
		(:func:`src.render.rebuild_piece`: npz, crop, overlay, ``piece_resegmented`` motivo ``manual``),
		drop the server caches of the piece, re-clean / re-register it if placed, re-query what its
		shape feeds (a loose piece: itself; a placed one: its cell, twin cell and their free
		neighbours), SSE ``board_changed`` / ``fetch_changed`` / ``piece_changed``. ``{error}`` on a
		validation failure (nothing written)."""
		from src import render
		from src.confirm import _around
		from src.query import run_query
		from src.state import LOOSE_STATES
		nota = body.get("nota")
		if nota is not None and not isinstance(nota, str):
			return {"error": "nota deve ser texto"}
		if not self.wlock.acquire(timeout=WRITE_WAIT_S):
			raise Busy(self.job or "ocupado")
		try:
			if self._exclusive():
				raise Busy(self.job)
			self.sync_locked()
			pr = self.pr
			if pid not in pr.pieces:
				return {"error": f"peça desconhecida {pid}"}
			try:
				pts, win = self._scan_points(pid, body)
				extra = self._save_extra(pid, body, pts, win)
			except ValueError as e:
				return {"error": str(e)}
			before = board_snapshot(pr.board, pr.pieces)
			old = self.piece_summary(pid)
			t0 = time.time()
			rec = OV.append_override(pr, pid, pts, nota=(nota or "").strip(), extra=extra)
			if "error" in rec:
				return {"error": rec["error"]}
			r = render.rebuild_piece(pr, pid, progress=None)
			self._known_stat = self._log_stat()
			if r.get("error") or r.get("errors"):
				msg = r.get("error") or "; ".join(r["errors"])
				return {"error": f"contorno gravado em {OV.OVERRIDES_FILE} mas não aplicado: {msg}"}
			bad = pr.check_invariants(disk=True)
			# caches that hold this piece's crop / contour (the version-keyed ones follow the log by themselves)
			self._pieces.clear()
			self._sections.clear()
			self._sheets.clear()
			self._ghosts = None
			memo = getattr(self, "_susp_pl", None)
			if memo:
				memo.pop(pid, None)
			p = pr.piece(pid)
			cells = []
			if p.estado == "colocada" and p.celula is not None:
				cells = [list(p.celula)]
				b = self._board
				if b is not None and b.get("snap") is not None:     # force a re-composition of the cell
					k = (p.celula[0] - 1) * pr.profile.cols + p.celula[1] - 1
					b["snap"] = list(b["snap"])
					b["snap"][k] = ("__contorno_manual__", None)
			n_prop = None
			if not bad:
				if p.estado == "colocada" and p.celula is not None:
					entries = run_query(pr, only_cells=_around(pr, p.celula), only_pieces=set(), use_image=self.use_image)
				elif p.estado in LOOSE_STATES or p.estado == "posicao_conhecida":
					entries = run_query(pr, only_cells=set(), only_pieces={pid}, use_image=self.use_image)
				else:
					entries = None
				if entries is not None:
					n_prop = len([e for e in entries if e.get("piece")])
			extra = self._after_write(before, [pid] if p.estado == "colocada" else [])
			for c in cells:
				if c not in extra["celulas_mudadas"]:
					extra["celulas_mudadas"].append(c)
			if cells:
				self.emit("board_changed", {"versao": self.version(), "celulas": cells})
			new = self.piece_summary(pid)
			self.emit("piece_changed", {"piece": pid})
			ch = r["changed"][0] if r["changed"] else None
			msg = (f"{pid}: contorno manual aplicado (classe {old['cls']} → {new['cls']}, cordas "
				   + "/".join(f"{x:.1f}" for x in (new["chords_mm"] or [])) + " mm)") if ch else f"{pid}: contorno igual ao atual"
			slim = {k: v for k, v in rec.items() if k not in ("tracos", "mascara_rle", "auto_contour_px")}
			return {"ok": True, "piece": new, "antes": old, "mensagens": [msg], "invariantes": bad, "override": slim,
					"n_propostas": n_prop, "segundos": round(time.time() - t0, 2), **extra}
		finally:
			self.wlock.release()

	def sync_locked(self) -> None:
		st = self._log_stat()
		if st != self._known_stat:
			self.pr = Project.open(self.path)
			self._known_stat = st
			self._placements = None

	def _unplace(self, pid: str, around) -> dict:
		"""Undo a placement (the cell gets its previous state) and re-query the cell and its twin."""
		from src.query import run_query
		pr = self.pr
		try:
			p = pr.piece(pid)
			cell = p.celula
			pr.unplace(pid)
		except (StateError, ValueError) as e:
			return {"error": str(e)}
		pr.save()
		bad = pr.check_invariants(disk=True)
		entries = []
		if not bad:
			entries = run_query(pr, only_cells=around(pr, cell), only_pieces={pid}, use_image=self.use_image)
		return {"messages": [f"{pid} retirada de {tuple(cell)}"], "invariants": bad, "entries": entries}

	# ------------------------------------------------------------ import queue (src.import_queue; docs/gui-design.md §24)
	def queue_summary(self) -> Optional[dict]:
		if self.iq is None:
			return None
		with self._qcond:
			return self.iq.summary()

	def queue_json(self) -> dict:
		""" ``GET /api/import_queue``: ``{fila: snapshot (running, queued in order, the last finished), resumo}``."""
		if self.iq is None:
			return {"fila": [], "resumo": None, "ativa": False}
		with self._qcond:
			snap = self.iq.snapshot()
			summ = self.iq.summary()
		done = [j for j in snap if j["estado"] in ("concluido", "falhado", "cancelado")]
		keep = {j["id"] for j in done[:QUEUE_DONE_KEEP]}
		snap = [j for j in snap if j["estado"] not in ("concluido", "falhado", "cancelado") or j["id"] in keep]
		return {"fila": snap, "resumo": summ, "ativa": True, "job": self.job}

	def _emit_queue(self) -> None:
		self.emit("queue_changed", self.queue_json())

	def _queue_label_locked(self) -> None:
		"""``job`` while nothing runs: «na fila: saco N» for the next queued job, or None (under ``_qcond``). A job set
		by someone else (an exclusive one) is left alone."""
		if self.job and not self._job_queue:
			return
		nxt = self.iq.next_job() if self.iq is not None else None
		if nxt is None:
			self.job = None
			self._job_queue = False
		else:
			self._job_queue = True
			self.job = f"na fila: saco {nxt['lote']}"

	def _set_job_label(self, label: str) -> None:
		with self._qcond:
			self._job_queue = True                  # flag first: a reader never sees a queue label as exclusive
			self.job = label

	def enqueue(self, lote: int, ficheiros: list, sheets: list, dpi: Optional[float] = None) -> dict:
		"""Append an import job (one bag, its sheets in order); the worker is woken. ``{ok, job, folhas, avisos, erros}``."""
		if self.iq is None:
			raise Busy("fila de importação desligada")
		rel = [self._rel(f) for f in ficheiros]
		folhas = [dict(sh.to_dict(), caminho=sh.caminho) for sh in sheets]
		avisos = [f"{os.path.basename(sh.origem)}" + (f" p.{sh.pagina}" if sh.pagina else "") + f": {a}"
				  for sh in sheets for a in sh.avisos]
		erros = [sh.erro for sh in sheets if sh.erro]
		with self._qcond:
			jid = self.iq.add(int(lote), rel, folhas, dpi=dpi)
			if not self.iq.running():
				self._queue_label_locked()
			self._qcond.notify_all()
		activity.get("importar").info(f"{jid}: saco {lote} na fila ({len(sheets)} folha{'s' if len(sheets) != 1 else ''}"
									  f"{'; ' + str(len(erros)) + ' com erro' if erros else ''})")
		self._emit_queue()
		return {"ok": True, "job": jid, "folhas": len(sheets), "avisos": avisos, "erros": erros}

	def queue_action(self, jid: str, acao: str, body: Optional[dict] = None) -> dict:
		""" ``POST /api/import_queue/{id}/cancelar | repetir | mover {posicao}``."""
		if self.iq is None:
			raise Busy("fila de importação desligada")
		with self._qcond:
			if jid not in self.iq.state["jobs"]:
				raise FileNotFoundError(f"trabalho desconhecido {jid}")
			try:
				if acao == "cancelar":
					self.iq.cancel(jid)
				elif acao == "repetir":
					self.iq.retry(jid)
				elif acao == "mover":
					self.iq.move(jid, int((body or {}).get("posicao", 0)))
				else:
					raise ValueError(f"ação desconhecida {acao!r}")
			except QueueError as e:
				return {"error": str(e)}
			if not self.iq.running():
				self._queue_label_locked()
			self._qcond.notify_all()
		activity.get("importar").info(f"{jid}: {acao}")
		self._emit_queue()
		return dict(self.queue_json(), ok=True)

	def start_ingest(self, path: str, lote: Optional[int], dpi: Optional[float] = None) -> dict:
		"""One file for bag ``lote`` -> :meth:`enqueue` (kept for callers of the single-scan API)."""
		from src.sheets import expand_sources
		sheets = expand_sources([path], out_dir=os.path.dirname(os.path.abspath(path)))
		return self.enqueue(int(lote), [path], sheets, dpi)

	def _rel(self, fp: Optional[str]) -> Optional[str]:
		if not fp:
			return fp
		ap = os.path.abspath(fp)
		return os.path.relpath(ap, REPO).replace("\\", "/") if ap.lower().startswith(REPO.lower()) else ap

	def _jp(self, msg: str, **data) -> None:
		self.log(f"[importar] {msg}")
		self.job_log.append(msg)
		self.emit("ingest_progress", dict(data, msg=msg))

	def _queue_worker(self) -> None:
		"""Thread ``fila-importacao``: wait on ``_qcond`` (woken by add / retry / move / cancel / the end of the start-up
		rule / :meth:`stop`; no polling), run the first queued job, repeat."""
		while True:
			with self._qcond:
				while not self._qstop and (self.state != "pronto" or self.iq.next_job() is None):
					self._qcond.wait()
				if self._qstop:
					return
				job = self.iq.next_job()
				self.iq.start(job["id"])
				self.job_log = []
			self._set_job_label(f"a importar saco {job['lote']}")
			self._emit_queue()
			try:
				self._run_job(job)
			except Exception as e:  # noqa: BLE001 - the queue goes on
				self.log(traceback.format_exc())
				with self._qcond:
					if self.iq.job(job["id"])["estado"] == "a_correr":
						self.iq.fail(job["id"], f"{type(e).__name__}: {e}")
				self._jp(f"ERRO: {type(e).__name__}: {e}", etapa="erro", fim=True, job=job["id"])
			finally:
				with self._qcond:
					self.job = None                     # label first, then the flag (see _set_job_label)
					self._job_queue = False
					self._queue_label_locked()
				self._emit_queue()

	def _run_job(self, job: dict) -> None:
		"""One import job: each sheet segmented outside the lock, committed under it; one full re-query at the end."""
		from src.ingest import commit_sheet, prepare_sheet, sheet_outcome
		from src.query import run_query
		from src.sheets import Sheet
		jid, lote = job["id"], job["lote"]
		alog = activity.get("importar")
		keys = set(Sheet.__dataclass_fields__)
		sheets = [Sheet(**{k: v for k, v in f.items() if k in keys}) for f in job["folhas"]]
		n = len(sheets)
		t0 = time.time()
		alog.info(f"{jid}: saco {lote}, {n} folha{'s' if n != 1 else ''}: a começar")
		rows, lock_s = [], []
		for k, sh in enumerate(sheets, 1):
			self._set_job_label(f"a importar saco {lote} (folha {k}/{n})")
			name = os.path.basename(sh.caminho or sh.origem or "?")
			base = {"k": k, "n": n, "caminho": sh.caminho, "origem": sh.origem, "pagina": sh.pagina}
			self._jp(f"folha {k}/{n}: a segmentar {name} (saco {lote})", etapa="segmentar", job=jid, k=k, n=n)
			if sh.erro or not sh.caminho:
				r = dict(base, estado="erro", error=sh.erro or "folha sem imagem", avisos=list(sh.avisos))
			else:
				ts = time.time()
				res = prepare_sheet(sh, self.pr, dpi=job.get("dpi"), segment=self.ingest_segment)
				seg_s = time.time() - ts
				with self.wlock:
					self.sync_locked()
					tl = time.perf_counter()
					cr = commit_sheet(self.pr, res, lote)
					self._known_stat = self._log_stat()
					held = time.perf_counter() - tl
				r = sheet_outcome(base, res, cr)
				if r["estado"] == "ok":
					lock_s.append(held)
					r["segundos_segmentar"], r["segundos_wlock"] = round(seg_s, 1), round(held, 2)
			rows.append(r)
			nums = sorted(r.get("numbers", {}).values())
			with self._qcond:
				self.iq.sheet(jid, k, n, caminho=self._rel(sh.caminho), estado=r["estado"], scan_id=r.get("scan_id"),
							  n_pecas=len(r.get("pieces") or []), avisos=r.get("avisos"), erro=r.get("error") or r.get("motivo"),
							  numeros=[nums[0], nums[-1]] if nums else None)
			if r["estado"] == "ok":
				msg = (f"folha {k}/{n}: {r['scan_id']}, {len(r['pieces'])} peças no saco {lote} (números {nums[0]}–{nums[-1]}; "
					   f"{len(r['rejected'])} fragmentos rejeitados, {len(r['double'])} possivelmente duplas) em "
					   f"{r['segundos_segmentar']:.0f} s; gravada em {r['segundos_wlock']:.1f} s") if nums else \
					  f"folha {k}/{n}: {r['scan_id']} sem peças"
				self._jp(msg, etapa="segmentado", job=jid, k=k, n=n, scan_id=r["scan_id"], n_pecas=len(r["pieces"]))
				self.emit("board_changed", {"versao": self.version(), "celulas": []})
			elif r["estado"] == "ignorada":
				self._jp(f"folha {k}/{n}: ignorada, {r['motivo']}", etapa="ignorada", job=jid, k=k, n=n, scan_id=r["scan_id"])
			else:
				activity.get("importar").error(f"{jid} folha {k}/{n}: {r.get('error')}")
				self._jp(f"folha {k}/{n}: ERRO: {r.get('error')}", etapa="erro_folha", job=jid, k=k, n=n)
			for a in r.get("avisos") or []:
				alog.warning(f"{jid} folha {k}/{n}: {a}")
			self._emit_queue()
		ok = [r for r in rows if r["estado"] == "ok"]
		ign = [r for r in rows if r["estado"] == "ignorada"]
		n_pecas = sum(len(r["pieces"]) for r in ok)
		if not ok and not ign:
			err = next((r.get("error") for r in rows if r.get("error")), "nenhuma folha legível")
			with self._qcond:
				self.iq.fail(jid, err)
			alog.error(f"{jid}: falhou ({err})")
			self._jp(f"ERRO: {err}", etapa="erro", fim=True, job=jid)
			return
		propostas, q_s = None, None
		if ok or job.get("tentativas", 0) > 1:
			self._set_job_label(f"a importar saco {lote} (consulta)")
			self._jp("a procurar gémeas e pares para todas as peças soltas (lista completa; pode demorar alguns minutos)",
					 etapa="consultar", job=jid)
			with self.wlock:
				self.sync_locked()
				tq = time.perf_counter()
				entries = run_query(self.pr, use_image=self.use_image)
				self._known_stat = self._log_stat()
				q_s = time.perf_counter() - tq
			mine_ids = {pid for r in ok for pid in r["pieces"]}
			mine = [e for e in entries if e.get("piece") in mine_ids]
			propostas = len(mine)
			self._placements = None
			self._alta = None
			self._holes = None
			self._suspeitas = None
			self.emit("fetch_changed", {})
			self.emit("board_changed", {"versao": self.version(), "celulas": []})
			try:
				self.holes_json(wait=False)
			except Exception as e:  # noqa: BLE001
				self.log(f"[servidor] buracos não relançados: {e}")
			self._emit_suspeitas()
		secs = time.time() - t0
		with self._qcond:
			self.iq.done(jid, n_folhas=n, n_pecas=n_pecas, propostas=propostas, segundos=secs,
						 wlock_folhas_s=[round(x, 2) for x in lock_s], wlock_consulta_s=None if q_s is None else round(q_s, 1))
		lk = (f"wlock: {', '.join(f'{x:.1f}' for x in lock_s)} s por folha" if lock_s else "wlock: sem gravações") + \
			 (f", consulta {q_s:.1f} s" if q_s is not None else "")
		alog.info(f"{jid}: saco {lote} concluído em {secs:.0f} s: {len(ok)} folhas importadas, {len(ign)} ignoradas, "
				  f"{len(rows) - len(ok) - len(ign)} com erro; {n_pecas} peças; {lk}")
		txt = (f"saco {lote}: {n_pecas} peças em {len(ok)} folha{'s' if len(ok) != 1 else ''}"
			   + (f", {len(ign)} já importada{'s' if len(ign) != 1 else ''}" if ign else "")
			   + (f"; {propostas} propostas para estas peças" if propostas is not None else "") + f" ({secs:.0f} s)")
		self._jp(txt, etapa="pronto", fim=True, job=jid, n=n_pecas, propostas=propostas,
				 scan_id=(ok[-1]["scan_id"] if ok else None))


# ---------------------------------------------------------------- routes
def create_app(gui: Gui):
	"""FastAPI app over ``gui`` (API under ``/api``, the static frontend ``src/web`` at ``/``)."""
	from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
	from fastapi.middleware.gzip import GZipMiddleware
	from fastapi.responses import JSONResponse, Response, StreamingResponse
	from fastapi.staticfiles import StaticFiles

	class JSON(JSONResponse):
		def render(self, content) -> bytes:
			# inf / NaN are not JSON: ``json.dumps`` would write ``Infinity`` and the browser's JSON.parse would fail
			# (seen with ``margin`` when d1 = 0, ronda 8); they become null
			return json.dumps(_finite(content), ensure_ascii=False, default=_json_default).encode("utf-8")

	app = FastAPI(title="Puzzle Piece Finder — mesa de montagem", docs_url="/api/docs", openapi_url="/api/openapi.json")
	app.add_middleware(GZipMiddleware, minimum_size=2000)
	app.state.gui = gui

	@app.middleware("http")
	async def _slow_requests(request: Request, call_next):
		"""One activity line per request slower than :data:`src.activity.SLOW_REQUEST_S`; nothing for the rest."""
		t0 = time.perf_counter()
		resp = await call_next(request)
		path = request.url.path
		if path != "/api/events":
			activity.slow_request(request.method, path + (f"?{request.url.query}" if request.url.query else ""),
								  time.perf_counter() - t0, resp.status_code)
		return resp

	def ready():
		gui.sync()
		if gui.state != "pronto":
			raise HTTPException(503, detail={"a_preparar": True, "log": gui.prep_log[-20:]})

	def img(data: bytes, media: str, cache: bool = True) -> Response:
		return Response(data, media_type=media, headers={"Cache-Control": "private, max-age=3600" if cache else "no-store"})

	def guard(fn):
		try:
			return fn()
		except Busy as e:
			raise HTTPException(409, detail=f"ocupado: {e}")
		except FileNotFoundError as e:
			raise HTTPException(404, detail=str(e))
		except (ValueError, StateError) as e:
			raise HTTPException(400, detail=str(e))

	@app.get("/api/status")
	def status():
		gui.sync()
		return JSON(gui.status_json())

	@app.get("/api/board")
	def board():
		ready()
		return JSON(gui.read(gui.board_json))

	@app.get("/api/legend")
	def legend():
		return JSON(legend_for(gui.pr.profile))

	@app.get("/api/board.jpg")
	def board_jpg(ppc: float = BOARD_PPC, region: Optional[str] = None, v: Optional[str] = None):
		ready()
		prof = gui.pr.profile
		data = guard(lambda: gui.board_jpg(ppc, _region_param(region, prof.rows, prof.cols)))
		return img(data, "image/jpeg", cache=v is not None)

	@app.get("/api/cell/{l}/{c}")
	def cell(l: int, c: int):
		ready()
		if not gui.pr.profile.in_grid(l, c):
			raise HTTPException(404, detail=f"célula ({l}, {c}) fora da grelha")
		return JSON(gui.read(lambda: gui.cell_json(l, c)))

	@app.get("/api/cell/{l}/{c}/zoom.jpg")
	def cell_zoom(l: int, c: int, side: str = "both", dpi: float = 300, v: Optional[str] = None):
		ready()
		if not gui.pr.profile.in_grid(l, c):
			raise HTTPException(404, detail=f"célula ({l}, {c}) fora da grelha")
		return img(guard(lambda: gui.zoom_jpg(l, c, side, dpi)), "image/jpeg", cache=v is not None)

	@app.get("/api/pieces/{pid}.png")
	def piece_png(pid: str, pose: str = "board", size: int = 220, v: Optional[str] = None):
		ready()
		if pid not in gui.pr.pieces:
			raise HTTPException(404, detail=f"peça desconhecida {pid}")
		data, used, why, theta = guard(lambda: gui.piece_png(pid, pose, size))
		r = img(data, "image/png", cache=v is not None)
		r.headers["X-Pose"] = used
		if theta is not None:
			r.headers["X-Pose-Theta"] = f"{float(theta):.2f}"
		return r

	@app.get("/api/pieces/{pid}")
	def piece(pid: str):
		ready()
		if pid not in gui.pr.pieces:
			raise HTTPException(404, detail=f"peça desconhecida {pid}")

		def run():
			d = gui.piece_summary(pid)
			th, why = gui.board_pose(pid)
			d.update(pose_tabuleiro=th, pose_origem=why,
					 propostas=[dict(e, razoes_txt=plain_reasons(e, gui.pr.profile),
									 origem_txt=ORIGIN_TXT.get(e.get("origin"), e.get("origin"))) for e in gui.fetch_entries()
								if e.get("piece") == pid],
					 img=f"/api/pieces/{pid}.png?pose=board", img_scan=f"/api/pieces/{pid}.png?pose=scan",
					 folha=f"/api/sheets/{gui.pr.piece(pid).scan_id}.jpg?highlight={pid}")
			return d
		return JSON(gui.read(run))

	@app.get("/api/pieces/{pid}/pose")
	def piece_pose(pid: str):
		ready()
		if pid not in gui.pr.pieces:
			raise HTTPException(404, detail=f"peça desconhecida {pid}")
		try:
			return JSON(guard(lambda: gui.read(lambda: gui.pose_json(pid))))
		except HTTPException as e:
			if e.status_code == 400:
				return JSON({"error": str(e.detail)}, status_code=400)
			raise

	async def _pose_post(request: Request, fn, body_needed: bool = True):
		ready()
		body = {}
		if body_needed:
			try:
				body = await request.json()
			except ValueError:
				return JSON({"error": "corpo JSON inválido"}, status_code=400)
			if not isinstance(body, dict):
				return JSON({"error": "o corpo deve ser um objeto JSON"}, status_code=400)
		try:
			r = await asyncio.to_thread(lambda: guard(lambda: fn(body)))
		except HTTPException as e:
			if e.status_code == 400:
				return JSON({"error": str(e.detail)}, status_code=400)
			raise
		if "error" in r:
			return JSON(r, status_code=400)
		return JSON(r)

	@app.post("/api/pieces/{pid}/pose/avaliar")
	async def piece_pose_evaluate(pid: str, request: Request):
		return await _pose_post(request, lambda body: gui.read(lambda: gui.pose_evaluate(pid, body)))

	@app.post("/api/pieces/{pid}/pose")
	async def piece_pose_set(pid: str, request: Request):
		return await _pose_post(request, lambda body: gui.set_pose(pid, body))

	@app.post("/api/pieces/{pid}/pose/repor")
	async def piece_pose_clear(pid: str, request: Request):
		return await _pose_post(request, lambda body: gui.clear_pose(pid), body_needed=False)

	@app.get("/api/pieces/{pid}/contorno")
	def piece_contour(pid: str):
		ready()
		if pid not in gui.pr.pieces:
			raise HTTPException(404, detail=f"peça desconhecida {pid}")
		return JSON(guard(lambda: gui.read(lambda: gui.contour_json(pid))))

	@app.get("/api/pieces/{pid}/contorno.png")
	def piece_contour_png(pid: str, v: Optional[str] = None):
		ready()
		if pid not in gui.pr.pieces:
			raise HTTPException(404, detail=f"peça desconhecida {pid}")
		return img(guard(lambda: gui.contour_png(pid)), "image/png", cache=v is not None)

	@app.post("/api/pieces/{pid}/contorno/preview")
	async def piece_contour_preview(pid: str, request: Request):
		ready()
		if pid not in gui.pr.pieces:
			raise HTTPException(404, detail=f"peça desconhecida {pid}")
		try:
			body = await request.json()
		except ValueError:
			raise HTTPException(400, detail="corpo JSON inválido")
		if not isinstance(body, dict):
			return JSON({"error": "o corpo deve ser um objeto JSON"}, status_code=400)
		try:
			data = await asyncio.to_thread(lambda: gui.contour_preview(pid, body))
		except ValueError as e:
			return JSON({"error": str(e)}, status_code=400)
		except FileNotFoundError as e:
			raise HTTPException(404, detail=str(e))
		return img(data, "image/png", cache=False)

	@app.post("/api/pieces/{pid}/contorno/resolver")
	async def piece_contour_solve(pid: str, request: Request):
		ready()
		if pid not in gui.pr.pieces:
			raise HTTPException(404, detail=f"peça desconhecida {pid}")
		try:
			body = await request.json()
		except ValueError:
			raise HTTPException(400, detail="corpo JSON inválido")
		if not isinstance(body, dict):
			return JSON({"error": "o corpo deve ser um objeto JSON"}, status_code=400)
		try:
			r = await asyncio.to_thread(lambda: gui.contour_solve(pid, body))
		except ValueError as e:
			return JSON({"error": str(e)}, status_code=400)
		except FileNotFoundError as e:
			raise HTTPException(404, detail=str(e))
		return JSON(r)

	@app.post("/api/pieces/{pid}/contorno")
	async def piece_contour_save(pid: str, request: Request):
		ready()
		if pid not in gui.pr.pieces:
			raise HTTPException(404, detail=f"peça desconhecida {pid}")
		try:
			body = await request.json()
		except ValueError:
			raise HTTPException(400, detail="corpo JSON inválido")
		if not isinstance(body, dict):
			return JSON({"error": "o corpo deve ser um objeto JSON"}, status_code=400)
		r = await asyncio.to_thread(lambda: guard(lambda: gui.save_contour(pid, body)))
		if "error" in r:
			return JSON(r, status_code=400)
		return JSON(r)

	@app.get("/api/fetch")
	def fetch():
		ready()
		return JSON(gui.read(gui.fetch_json))

	@app.get("/api/sheets/{scan_id}.jpg")
	def sheet(scan_id: str, highlight: Optional[str] = None, max: int = SHEET_MAX_PX, v: Optional[str] = None):
		ready()
		if highlight and highlight not in gui.pr.pieces:
			raise HTTPException(404, detail=f"peça desconhecida {highlight}")
		return img(guard(lambda: gui.sheet_jpg(scan_id, highlight, max)), "image/jpeg", cache=v is not None)

	@app.get("/api/ghosts")
	def ghosts():
		ready()
		return JSON({"versao": gui.version(), "rotacao_gemea_deg": gui.pr.profile.twin_rotation_deg(),
					 "fantasmas": gui.ghosts()})

	@app.get("/api/lots")
	def lots():
		ready()
		return JSON(gui.read(gui.lots_json))

	@app.get("/api/sections")
	def sections():
		ready()
		return JSON(gui.read(gui.sections_json))

	@app.get("/api/sections/{gid}.png")
	def section_png(gid: str, max: int = 360):
		ready()
		return img(guard(lambda: gui.read(lambda: gui.section_png(gid, max))), "image/png")

	@app.post("/api/confirm")
	async def post_confirm(request: Request):
		ready()
		try:
			body = await request.json()
		except ValueError:
			raise HTTPException(400, detail="corpo JSON inválido")
		r = await asyncio.to_thread(lambda: guard(lambda: gui.confirm(body)))
		if "error" in r:
			return JSON(r, status_code=400)
		return JSON(r)

	@app.post("/api/report")
	async def post_report(request: Request):
		ready()
		try:
			body = await request.json()
		except ValueError:
			raise HTTPException(400, detail="corpo JSON inválido")
		r = await asyncio.to_thread(lambda: guard(lambda: gui.add_report(body)))
		if "error" in r:
			return JSON(r, status_code=400)
		return JSON(r)

	@app.post("/api/report/{rid}/edit")
	async def post_report_edit(rid: str, request: Request):
		ready()
		try:
			body = await request.json()
		except ValueError:
			raise HTTPException(400, detail="corpo JSON inválido")
		if not isinstance(body, dict):
			return JSON({"error": "o corpo deve ser um objeto JSON"}, status_code=400)
		for k in ("tipo", "texto"):
			if body.get(k) is not None and not isinstance(body[k], str):
				return JSON({"error": f"{k} deve ser texto"}, status_code=400)
		r = await asyncio.to_thread(lambda: guard(lambda: gui.edit_report(rid, body)))
		if "error" in r:
			return JSON(r, status_code=404 if "relatório desconhecido" in r["error"] else 400)
		return JSON(r)

	@app.post("/api/report/{rid}/estado")
	async def post_report_estado(rid: str, request: Request):
		ready()
		try:
			body = await request.json()
		except ValueError:
			raise HTTPException(400, detail="corpo JSON inválido")
		if not isinstance(body, dict):
			return JSON({"error": "o corpo deve ser um objeto JSON"}, status_code=400)
		nota = body.get("nota")
		if nota is not None and not isinstance(nota, str):
			return JSON({"error": "nota deve ser texto"}, status_code=400)
		acao = body.get("acao")
		if not isinstance(acao, str):
			return JSON({"error": "falta a acao"}, status_code=400)
		r = await asyncio.to_thread(lambda: guard(lambda: gui.set_report_state(rid, acao, nota or "")))
		if "error" in r:
			return JSON(r, status_code=404 if "relatório desconhecido" in r["error"] else 400)
		return JSON(r)

	@app.get("/api/reports")
	def get_reports(todos: bool = False, eliminados: bool = False):
		ready()
		from src import reports
		return JSON({"reports": reports.list_reports(gui.pr, only_open=not todos, eliminados=eliminados)})

	@app.get("/api/suspeitas")
	def get_suspeitas():
		ready()
		return JSON(gui.read(gui.suspeitas_json))

	async def _suspect_post(request: Request, fn):
		ready()
		try:
			body = await request.json()
		except ValueError:
			raise HTTPException(400, detail="corpo JSON inválido")
		if not isinstance(body, dict):
			return JSON({"error": "o corpo deve ser um objeto JSON"}, status_code=400)
		r = await asyncio.to_thread(lambda: guard(lambda: fn(body)))
		if "error" in r:
			return JSON(r, status_code=400)
		return JSON(r)

	@app.post("/api/suspeitas/{piece}/falso-alarme")
	async def post_falso_alarme(piece: str, request: Request):
		return await _suspect_post(request, lambda body: gui.dismiss_suspect(piece, body))

	@app.post("/api/suspeitas/{piece}/restaurar")
	async def post_restaurar_suspeita(piece: str, request: Request):
		return await _suspect_post(request, lambda body: gui.restore_suspect(piece, body))

	@app.get("/api/holes")
	def get_holes():
		ready()
		return JSON(gui.holes_json())

	@app.get("/api/holes/alta")
	def get_holes_alta():
		ready()
		return JSON(gui.read(gui.alta_json))

	@app.post("/api/holes/alta/reativar")
	async def post_holes_alta_reativar(request: Request):
		ready()
		try:
			body = await request.json()
		except ValueError:
			body = {}
		if not isinstance(body, dict):
			return JSON({"error": "o corpo deve ser um objeto JSON"}, status_code=400)
		r = await asyncio.to_thread(lambda: guard(lambda: gui.resume_alta(body)))
		if "error" in r:
			return JSON(r, status_code=400)
		return JSON(r)

	@app.get("/api/atividade")
	def get_atividade(desde: Optional[int] = None, n: int = 300):
		return JSON(gui.activity_json(desde, max(1, min(int(n), 1000))))

	@app.get("/api/holes/{l}/{c}")
	def get_hole(l: int, c: int):
		ready()
		if not gui.pr.profile.in_grid(l, c):
			raise HTTPException(404, detail=f"célula ({l},{c}) fora da grelha")
		r = guard(lambda: gui.read(lambda: gui.hole_json(l, c)))
		if "error" in r:
			return JSON(r, status_code=400)
		return JSON(r)

	async def _hole_post(l: int, c: int, request: Request, confirm_it: bool):
		ready()
		try:
			body = await request.json()
		except ValueError:
			raise HTTPException(400, detail="corpo JSON inválido")
		if not isinstance(body, dict):
			return JSON({"error": "o corpo deve ser um objeto JSON"}, status_code=400)
		r = await asyncio.to_thread(lambda: guard(lambda: gui.hole_action(l, c, body, confirm_it=confirm_it)))
		if "error" in r:
			return JSON(r, status_code=400)
		return JSON(r)

	@app.post("/api/holes/{l}/{c}/confirmar")
	async def post_hole_confirmar(l: int, c: int, request: Request):
		return await _hole_post(l, c, request, True)

	@app.post("/api/holes/{l}/{c}/rejeitar")
	async def post_hole_rejeitar(l: int, c: int, request: Request):
		return await _hole_post(l, c, request, False)

	@app.get("/api/reports/{rid}/captura")
	def get_report_captura(rid: str):
		ready()
		fp = gui.report_capture(rid)
		if not fp:
			raise HTTPException(404, detail="sem captura")
		with open(fp, "rb") as f:
			data = f.read()
		return img(data, "image/png" if fp.lower().endswith(".png") else "image/jpeg", cache=False)

	@app.post("/api/ingest")
	async def post_ingest(lote: int = Form(...), dpi: Optional[str] = Form(None),
						  files: Optional[list[UploadFile]] = File(None), file: Optional[UploadFile] = File(None)):
		"""One or more files (images / PDF) of bag ``lote`` -> one job at the end of the import queue (never 409 for an
		import in progress). ``dpi`` empty = the file decides (PDF MediaBox / JFIF), else 300."""
		from src.sheets import expand_sources, safe_stem
		ready()
		ups = [f for f in (files or []) if f is not None and (f.filename or "")] + ([file] if file is not None else [])
		if not ups:
			raise HTTPException(400, detail="nenhum ficheiro")
		try:
			d = float(str(dpi).replace(",", ".")) if dpi not in (None, "") else None
		except ValueError:
			raise HTTPException(400, detail=f"dpi inválido {dpi!r}")
		if d is not None and not (50 <= d <= 2400):
			raise HTTPException(400, detail=f"dpi fora do intervalo 50–2400: {d:g}")
		os.makedirs(gui.uploads, exist_ok=True)
		stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
		paths = []
		for up in ups:
			name = re.sub(r"[^A-Za-z0-9._-]+", "_", os.path.basename(up.filename or "scan.jpg"))
			dst = os.path.join(gui.uploads, f"lote{int(lote):02d}_{stamp}_{name}")
			k = 2
			while os.path.exists(dst) or dst in paths:
				dst = os.path.join(gui.uploads, f"lote{int(lote):02d}_{stamp}_{k}_{name}")
				k += 1
			with open(dst, "wb") as f:
				while True:
					chunk = await up.read(1 << 20)
					if not chunk:
						break
					f.write(chunk)
			paths.append(dst)
		sheets = await asyncio.to_thread(lambda: [sh for p in paths
												  for sh in expand_sources([p], out_dir=gui.uploads, prefix=safe_stem(p))])
		r = guard(lambda: gui.enqueue(int(lote), paths, sheets, d))
		rel = [gui._rel(p) for p in paths]
		return JSON(dict(r, ficheiro=rel[0], ficheiros=rel,
						 paginas=[{"origem": gui._rel(sh.origem), "pagina": sh.pagina, "caminho": gui._rel(sh.caminho),
								   "dpi": sh.dpi, "dpi_fontes": sh.dpi_fontes, "erro": sh.erro} for sh in sheets]))

	@app.get("/api/import_queue")
	def get_import_queue():
		return JSON(gui.queue_json())

	@app.post("/api/import_queue/{jid}/{acao}")
	async def post_import_queue(jid: str, acao: str, request: Request):
		if acao not in ("cancelar", "repetir", "mover"):
			raise HTTPException(404, detail=f"ação desconhecida {acao!r}")
		body = {}
		if acao == "mover":
			try:
				body = await request.json()
			except ValueError:
				raise HTTPException(400, detail="corpo JSON inválido")
			if not isinstance(body, dict) or not isinstance(body.get("posicao"), int):
				return JSON({"error": "falta posicao (inteiro, 0 = a seguir)"}, status_code=400)
		r = guard(lambda: gui.queue_action(jid, acao, body))
		if "error" in r:
			return JSON(r, status_code=400)
		return JSON(r)

	@app.get("/api/events")
	async def events(request: Request):
		"""SSE: the events after ``Last-Event-ID`` / ``?from=`` (else from now), delivered when :meth:`Gui.emit` wakes this
		client's ``asyncio.Event`` (no polling); ``: keep-alive`` after :data:`SSE_KEEPALIVE_S` without events."""
		last = int(request.headers.get("last-event-id") or request.query_params.get("from") or gui.seq)
		loop = asyncio.get_running_loop()
		wake = asyncio.Event()

		async def gen():
			nonlocal last
			gui.sse_register(wake, loop)
			try:
				yield f"retry: 2000\nevent: hello\ndata: {json.dumps(gui.status_json(), default=_json_default)}\n\n"
				while True:
					for n, name, data in gui.events_after(last):
						last = n
						yield f"id: {n}\nevent: {name}\ndata: {json.dumps(data, ensure_ascii=False, default=_json_default)}\n\n"
					try:
						await asyncio.wait_for(wake.wait(), timeout=SSE_KEEPALIVE_S)
					except asyncio.TimeoutError:
						yield ": keep-alive\n\n"
						if await request.is_disconnected():
							break
						continue
					wake.clear()                     # cleared before reading: an emit after this wakes the next wait
					if await request.is_disconnected():
						break
			finally:
				gui.sse_unregister(wake)

		return StreamingResponse(gen(), media_type="text/event-stream",
								 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

	app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
	return app


# ---------------------------------------------------------------- CLI
def _lan_ips() -> list:
	ips = set()
	try:
		s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		s.connect(("10.255.255.255", 1))
		ips.add(s.getsockname()[0])
		s.close()
	except OSError:
		pass
	return sorted(ips)


def main(argv=None) -> int:
	ap = argparse.ArgumentParser(prog="python -m src.server", description="Interface web local (mesa de montagem).")
	ap.add_argument("--project", default=os.path.join("projects", "alpes"))
	ap.add_argument("--port", type=int, default=DEFAULT_PORT)
	ap.add_argument("--lan", action="store_true", help="escuta em 0.0.0.0 (telemóvel na mesma rede; SEM login)")
	ap.add_argument("--no-image", action="store_true", help="reconsultas sem desempate pela imagem (mais rápidas)")
	ap.add_argument("--no-prepare", action="store_true", help="não regenera recursos em falta no arranque")
	ap.add_argument("--uploads", default=None, help="pasta onde os scans importados são gravados")
	args = ap.parse_args(argv)
	try:
		import uvicorn
	except ImportError:
		print("erro: falta o uvicorn (pip install -r requirements.txt)")
		return 1
	ring = activity.RingHandler()
	activity.setup(os.path.abspath(args.project), console=True, ring=ring)   # terminal + logs/servidor-AAAAMMDD.log + GUI ring
	log = activity.get("arranque")
	try:
		gui = Gui(args.project, prepare=not args.no_prepare, use_image=not args.no_image, uploads=args.uploads, ring=ring)
	except (StateError, ValueError) as e:
		log.error(f"erro: {e}")
		return 1
	app = create_app(gui)
	host = "0.0.0.0" if args.lan else "127.0.0.1"
	log.info(f"mesa de montagem: projeto {gui.path} ({len(gui.pr.pieces)} peças, versão do log {gui.version()})")
	log.info(f"abre http://127.0.0.1:{args.port}; registo em {gui._activity_file()}")
	if args.lan:
		for ip in _lan_ips():
			log.info(f"na rede local: http://{ip}:{args.port}")
		log.warning("sem login. Qualquer pessoa nesta rede Wi-Fi pode ver e alterar o projeto. "
					"O firewall do Windows pode pedir autorização para a porta.")
	uvicorn.run(app, host=host, port=args.port, log_level="warning")
	return 0


if __name__ == "__main__":
	sys.exit(main())
