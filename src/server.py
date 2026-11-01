"""Local web GUI ("mesa de montagem"): a thin FastAPI server over :class:`src.state.Project`.

Usage::

	python -m src.server --project projects/alpes [--port 8765] [--lan] [--no-image]

Then open ``http://127.0.0.1:8765``. ``--lan`` binds 0.0.0.0 so a phone on the same Wi-Fi
can open ``http://<pc>:8765``; there is **no login**: anyone on that network can read and
change the project (a warning is printed).

Design (docs/gui-design.md):

* **Writes** go through :func:`src.confirm.confirm` (place / reject / position known /
  anchor / unanchor / discard, then the incremental re-query), :meth:`Project.unplace`
  and :func:`src.ingest.ingest_scan` + :func:`src.query.run_query`, all under one lock
  (``Gui.wlock``). The log stays the source of truth (``board == replay(log)``). A write
  while a background job (import, preparation) runs answers 409.
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
  ``prepare_progress``); the data endpoints answer 503 until it ends.
* **Events** (SSE ``/api/events``): ``board_changed``, ``fetch_changed``,
  ``ingest_progress``, ``prepare_progress``, ``ready``.

Pure helpers (legend, cell diff, patch regions, plain-language reasons) are separate from
the :class:`Gui` state object and from :func:`create_app` (routes).
"""

import argparse
import asyncio
import collections
import datetime as _dt
import json
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

from src.state import Project, StateError

__all__ = [
	"LEGEND", "legend_for", "BOARD_PPC", "DEFAULT_PORT", "SPAN_CELLS", "missing_assets", "changed_cells", "patch_regions",
	"plain_reasons", "Gui", "create_app", "main",
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
EVENTS_KEEP = 500
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
	{"id": "legado", "tipo": "svg", "classe": "b-legado", "rotulo": "Ocupada sem silhueta", "texto": "cheia na foto, sem scan solto",
	 "detalhe": "cheia na foto do tabuleiro, mas a peça ainda não passou solta pelo scanner (não há recorte)"},
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
	{"id": "mesa", "tipo": "svg", "classe": "b-mesa", "rotulo": "Grupo da mesa", "texto": "onde um grupo solto ficaria",
	 "detalhe": "pré-visualização (separador Mesa) de onde um grupo solto ficaria se for ancorado"},
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
			  "em_seccao": "num grupo por ancorar", "descartada": "descartada"}
CELL_TXT = {"vazia": "vazia", "ocupada_legado": "ocupada (sem silhueta)", "colocada": "colocada"}
ORIGIN_TXT = {"gemeo": "gémea colocada", "borda": "borda", "par": "par de soltas",
			  "posicao_conhecida": "posição conhecida", "seccao": "grupo por ancorar"}


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


def board_snapshot(board) -> list:
	"""``[(estado, peca_id), ...]`` row-major: what the raster depends on per cell."""
	return [(cell["estado"], cell["peca_id"]) for _, cell in board.iter_cells()]


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
	assets rebuilt on another PC).
	"""

	def __init__(self, project_path: str, *, prepare: bool = True, use_image: bool = True,
				 uploads: Optional[str] = None, log=print):
		self.path = os.path.abspath(project_path)
		self.pr = Project.open(self.path)
		self.use_image = use_image
		self.uploads = uploads or os.path.join(REPO, "images", "pieces", "lotes")
		self.log = log or (lambda *a, **k: None)
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
		self._ghosts = None           # (ver, list)
		self._fetch = None            # (mtime, dict)
		self._placements = None       # (ver, dict)
		self._sheets = {}
		self._art = None
		self.ingest_segment = None    # tests: replacement for segment_scan
		if prepare:
			threading.Thread(target=self._prepare, name="preparar", daemon=True).start()

	# ------------------------------------------------------------ events
	def emit(self, name: str, data=None) -> None:
		with self.cond:
			self.seq += 1
			self.events.append((self.seq, name, data if data is not None else {}))
			self.cond.notify_all()

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
				self.log(f"[servidor] log.jsonl mudou fora do servidor: projeto reaberto")
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
			self._prep("a compor o tabuleiro")
			t0 = time.time()
			self.board_jpg(BOARD_PPC)
			self._prep(f"tabuleiro pronto ({time.time() - t0:.1f} s)")
			self.ghosts()
		except Exception as e:  # noqa: BLE001 - the server must still come up; reported on the page
			self._prep(f"ERRO na preparação: {type(e).__name__}: {e}")
			self.log(traceback.format_exc())
		finally:
			self.state = "pronto"
			self.emit("ready", {"versao": self.version()})

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
			self._placements = (ver, render.load_placements(self.pr).get("placements") or {})
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
		snap = self.read(lambda: board_snapshot(self.pr.board))
		b = self._board
		if b is not None and b["ver"] == ver:
			return b
		jp, mp = self._disk_cache(BOARD_PPC)
		if b is None and os.path.exists(jp) and os.path.exists(mp):
			try:
				with open(mp, encoding="utf-8") as f:
					meta = json.load(f)
				img = cv2.imdecode(np.fromfile(jp, np.uint8), cv2.IMREAD_COLOR)
				if img is not None and meta.get("snap") is not None and meta.get("pl_mtime") == plm:
					b = {"ver": meta.get("ver"), "img": img, "snap": [tuple(x) for x in meta["snap"]], "jpg": None}
			except (OSError, ValueError):
				b = None
		rows, cols = self.pr.profile.rows, self.pr.profile.cols
		t0 = time.time()
		how = "completo"
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
		if how != "sem mudanças":
			self.log(f"[servidor] tabuleiro {how} em {time.time() - t0:.1f} s")
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
		``(bytes, pose_used)``."""
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
		out = (buf.tobytes(), "board" if theta is not None else "scan", why)
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
		"""Thumbnail of a group: its pieces' crops at their scan positions (the exploded view), on dark grey."""
		s = self.pr.sections.get(gid)
		if s is None:
			raise FileNotFoundError(f"secção desconhecida {gid}")
		items = []
		for pid in s.cells_local:
			p = self.pr.piece(pid)
			if not p.bbox:
				continue
			rgba = self.pr.crop_rgba(pid)
			if rgba is not None:
				items.append((p.bbox, rgba))
		if not items:
			raise FileNotFoundError(f"{gid}: sem recortes")
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
			r = cv2.resize(rgba, (nw, nh), interpolation=cv2.INTER_AREA).astype(np.float32)
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
				"theta_deg": p.theta_deg}

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
			pid = e.get("piece")
			if pid and pid in self.pr.pieces:
				e["estado_atual"] = self.pr.piece(pid).estado
			entries.append(e)
		return {"t": f.get("t"), "entries": entries, "suprimidas": f.get("suprimidas", []),
				"notes": f.get("notes", []), "rest": len(f.get("rest", []) or [])}

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
				neigh.append({"dir": d, "cell": [a, b], "estado": nc["estado"], "peca_id": nc["peca_id"]})
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
			"cell": [l, c], "estado": cell["estado"], "estado_txt": CELL_TXT.get(cell["estado"], cell["estado"]),
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
		return {"estado": self.state, "job": self.job, "prep_log": self.prep_log[-60:], "job_log": self.job_log[-60:],
				"versao": self.version(), "seq": self.seq, "projeto": self.pr.meta.get("id")}

	# ------------------------------------------------------------ writes
	def _after_write(self, before_snap: list, placed: list) -> dict:
		"""Refresh render assets of newly placed pieces, bump caches, emit events."""
		self._known_stat = self._log_stat()
		self._placements = None
		if placed:
			self._refresh_render_assets(placed)
		snap = board_snapshot(self.pr.board)
		ch = changed_cells(before_snap, snap, self.pr.profile.cols)
		self.emit("board_changed", {"versao": self.version(), "celulas": [list(x) for x in ch]})
		self.emit("fetch_changed", {})
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
		if not self.wlock.acquire(timeout=0.5):
			raise Busy(self.job or "ocupado")
		try:
			if self.job:
				raise Busy(self.job)
			self.sync_locked()
			pr = self.pr
			before = board_snapshot(pr.board)
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
					return {"error": "falta a secção ou a célula de ancoragem"}
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
			else:
				return {"error": f"ação desconhecida {acao!r}"}
			if "error" in r:
				self._known_stat = self._log_stat()
				return {"error": r["error"]}
			placed = [p.id for p in pr.pieces.values() if p.estado == "colocada"
					  and before[(p.celula[0] - 1) * pr.profile.cols + p.celula[1] - 1] != ("colocada", p.id)]
			extra = self._after_write(before, placed)
			return {"ok": True, "mensagens": r.get("messages", []), "invariantes": r.get("invariants", []),
					"n_propostas": len([e for e in r.get("entries", []) if e.get("piece")]),
					"segundos": round(time.time() - t0, 2), **extra}
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

	def start_ingest(self, path: str, lote: Optional[int], dpi: float) -> dict:
		"""Background job: ingest the scan, then a full re-query; progress by SSE ``ingest_progress``."""
		if not self.wlock.acquire(timeout=0.5):
			raise Busy(self.job or "ocupado")
		try:
			if self.job:
				raise Busy(self.job)
			self.job = f"importar {os.path.basename(path)}"
			self.job_log = []
		finally:
			self.wlock.release()
		threading.Thread(target=self._ingest, args=(path, lote, dpi), name="importar", daemon=True).start()
		return {"ok": True, "job": self.job}

	def _jp(self, msg: str, **data) -> None:
		self.log(f"[importar] {msg}")
		self.job_log.append(msg)
		self.emit("ingest_progress", dict(data, msg=msg))

	def _ingest(self, path: str, lote: Optional[int], dpi: float) -> None:
		from src.ingest import ingest_scan
		from src.query import run_query
		with self.wlock:
			try:
				self.sync_locked()
				t0 = time.time()
				self._jp(f"a segmentar {os.path.basename(path)} (lote {lote})", etapa="segmentar")
				r = ingest_scan(self.pr, path, lote, dpi=dpi, segment=self.ingest_segment)
				if "error" in r:
					self._jp(f"ERRO: {r['error']}", etapa="erro", fim=True)
					return
				self._known_stat = self._log_stat()
				n = len(r["pieces"])
				self._jp(f"{n} peças no lote {lote} ({r['scan_id']}; {len(r['rejected'])} fragmentos rejeitados, "
						 f"{len(r['double'])} possivelmente duplas) em {time.time() - t0:.0f} s", etapa="segmentado",
						 scan_id=r["scan_id"], n=n)
				self.emit("board_changed", {"versao": self.version(), "celulas": []})
				t1 = time.time()
				self._jp("a procurar gémeas e pares para todas as peças soltas (lista completa; pode demorar alguns minutos)",
						 etapa="consultar")
				entries = run_query(self.pr, use_image=self.use_image)
				self._known_stat = self._log_stat()
				mine = [e for e in entries if e.get("piece") in set(r["pieces"])]
				self._jp(f"lista atualizada em {time.time() - t1:.0f} s: {len(mine)} propostas para peças deste scan, "
						 f"{len([e for e in entries if e.get('piece')])} no total", etapa="pronto", fim=True,
						 scan_id=r["scan_id"], n=n, propostas=len(mine))
				self.emit("fetch_changed", {})
				self.emit("board_changed", {"versao": self.version(), "celulas": []})
			except Exception as e:  # noqa: BLE001 - reported to the page
				self.log(traceback.format_exc())
				self._jp(f"ERRO: {type(e).__name__}: {e}", etapa="erro", fim=True)
			finally:
				self.job = None


# ---------------------------------------------------------------- routes
def create_app(gui: Gui):
	"""FastAPI app over ``gui`` (API under ``/api``, the static frontend ``src/web`` at ``/``)."""
	from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
	from fastapi.middleware.gzip import GZipMiddleware
	from fastapi.responses import JSONResponse, Response, StreamingResponse
	from fastapi.staticfiles import StaticFiles

	class JSON(JSONResponse):
		def render(self, content) -> bytes:
			return json.dumps(content, ensure_ascii=False, default=_json_default).encode("utf-8")

	app = FastAPI(title="Puzzle Piece Finder — mesa de montagem", docs_url="/api/docs", openapi_url="/api/openapi.json")
	app.add_middleware(GZipMiddleware, minimum_size=2000)
	app.state.gui = gui

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
		data, used, why = guard(lambda: gui.piece_png(pid, pose, size))
		r = img(data, "image/png", cache=v is not None)
		r.headers["X-Pose"] = used
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

	@app.post("/api/ingest")
	async def post_ingest(file: UploadFile = File(...), lote: int = Form(...), dpi: float = Form(300)):
		ready()
		if gui.job:
			raise HTTPException(409, detail=f"ocupado: {gui.job}")
		name = re.sub(r"[^A-Za-z0-9._-]+", "_", os.path.basename(file.filename or "scan.jpg"))
		os.makedirs(gui.uploads, exist_ok=True)
		stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
		dst = os.path.join(gui.uploads, f"lote{int(lote):02d}_{stamp}_{name}")
		with open(dst, "wb") as f:
			while True:
				chunk = await file.read(1 << 20)
				if not chunk:
					break
				f.write(chunk)
		r = guard(lambda: gui.start_ingest(dst, int(lote), float(dpi)))
		return JSON(dict(r, ficheiro=os.path.relpath(dst, REPO).replace("\\", "/") if dst.lower().startswith(REPO.lower()) else dst))

	@app.get("/api/events")
	async def events(request: Request):
		last = int(request.headers.get("last-event-id") or request.query_params.get("from") or gui.seq)

		async def gen():
			nonlocal last
			yield f"retry: 2000\nevent: hello\ndata: {json.dumps(gui.status_json(), default=_json_default)}\n\n"
			idle = 0.0
			while True:
				if await request.is_disconnected():
					break
				evs = gui.events_after(last)
				for n, name, data in evs:
					last = n
					yield f"id: {n}\nevent: {name}\ndata: {json.dumps(data, ensure_ascii=False, default=_json_default)}\n\n"
				if evs:
					idle = 0.0
				else:
					idle += 0.4
					if idle >= 15:
						idle = 0.0
						yield ": keep-alive\n\n"
				await asyncio.sleep(0.4)

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
	try:
		gui = Gui(args.project, prepare=not args.no_prepare, use_image=not args.no_image, uploads=args.uploads)
	except (StateError, ValueError) as e:
		print(f"erro: {e}")
		return 1
	app = create_app(gui)
	host = "0.0.0.0" if args.lan else "127.0.0.1"
	print(f"mesa de montagem: projeto {gui.path}")
	print(f"  abre http://127.0.0.1:{args.port}")
	if args.lan:
		for ip in _lan_ips():
			print(f"  na rede local: http://{ip}:{args.port}")
		print("  AVISO: sem login. Qualquer pessoa nesta rede Wi-Fi pode ver e alterar o projeto. "
			  "O firewall do Windows pode pedir autorização para a porta.")
	uvicorn.run(app, host=host, port=args.port, log_level="warning")
	return 0


if __name__ == "__main__":
	sys.exit(main())
