"""Free position of the loose groups on the board (F4, B1): ``projects/<id>/mesa.jsonl``.

A loose group (a section without a place, :class:`src.state.Section` with ``anchor.anchored`` false) can be shown on
the board of the new GUI and moved / turned freely (``docs/gui/redesenho/F4_PLANO.md`` §1 «Falta» 1, §3). That
position is NOT state of the puzzle: the engine never reads it (not a mould, not a neighbour, no twin proposals, not
in the progress), so it lives outside the log, in an APPEND-ONLY file like ``overrides.jsonl``, one line per write::

	{"gid", "l0", "c0", "rot", "t", "log_n"}         (+ "mirror": true only for a mirrored group)

``(l0, c0, rot[, mirror])`` is an anchor dict as :func:`src.state.section_cell` reads it (local (0, 0) on the board
cell ``(l0, c0)``, ``rot`` degrees clockwise, multiple of 90). ``log_n`` = number of events of ``log.jsonl`` when the
line was written.

**Which line counts.** A line counts only if its group exists, is visible (not every piece a re-scan, ``same_as``),
has no place now, and ``log_n`` is greater than the 0-based index of the group's last ``section_anchored`` /
``section_unanchored`` event (a line written before the last anchor / unanchor is stale). The last counting line of
each group wins (file order). Broken lines, an incomplete last line, lines of unknown or anchored groups and invalid
positions (outside the grid, ``rot`` not ×90, wrong types) are skipped and counted per reason
(:func:`read_positions`), never an error.

**Effective position** (:func:`effective_position`): the counting line → else, if the group was anchored and then
unanchored, the position of that last anchor (Q10 a: «Tirar o grupo inteiro do lugar» leaves it where it was, with
no extra write) → else None: a group never shown does not appear on the board (Q3).

**Writing** (:func:`write_position`, «Mostrar» / «Mover»): validated, then appended. Refused (``{'error', 'motivo'}``,
nothing written) for an unknown / invisible group, an anchored group, ``rot`` not ×90, a cell outside the grid, over
a ``colocada`` piece, over a cell occupied for the engine without a piece (``ocupada_legado`` confirmed, in practice
a cell the user marked full) or over another shown group (its effective position). «Full in the photo»
(``fonte='foto'``) does not block (Q7 a). The caller holds the server's write lock (``Gui.wlock``): a «Encaixa» can
then never cross the validation. A group already shown may later sit over a placed piece (a «Encaixa» under it): that
is the derived ``sobreposto`` of :mod:`src.grupos` (B2), never written here.

Nothing here touches ``log.jsonl``, the :class:`~src.state.Board` or ``render/placements.json``, so
``Gui.render_version()`` does not change.

**The ``log_n`` index** (:func:`last_anchor_index`): one pass over the log bytes, ``json.loads`` only on the lines
that mention ``section_anchored`` / ``section_unanchored``, cached per log path and extended incrementally (only the
bytes appended since the last call are read; a log that shrank or whose last read bytes changed is read again from
the start). Measured on a copy of ``projects/alpes`` (3118 events, 2,3 MB): see ``docs/decisoes.md`` (2026-11-18,
F4 B1).
"""

import datetime as _dt
import json
import os
import threading
from typing import Optional

from src.state import read_retry, section_cell

__all__ = [
	"MESA_FILE", "MOTIVOS_LEITURA", "mesa_path", "last_anchor_index", "is_loose", "footprint", "read_positions",
	"effective_position", "effective_positions", "check_position", "write_position",
]

MESA_FILE = "mesa.jsonl"
MOTIVOS_LEITURA = ("linha_partida", "linha_incompleta", "grupo_desconhecido", "grupo_fixado", "posicao_invalida",
				   "anterior_a_fixacao")
_ANCHOR_ACTIONS = ("section_anchored", "section_unanchored")
_ANCHOR_MARKS = tuple(f'"{a}"'.encode() for a in _ANCHOR_ACTIONS)
_TAIL = 64                      # bytes before the cached offset compared to tell an append from a rewritten log

_index_cache: dict = {}         # abs log path -> {"offset", "tail", "n", "last"}
_index_lock = threading.Lock()


def mesa_path(project) -> str:
	return project.p(MESA_FILE)


# ---------------------------------------------------------------- the log index (pure scan + cached I/O)
def _scan_lines(buf: bytes, n: int, last: dict) -> int:
	"""Count the events of ``buf`` (complete lines; blank lines are not events, as :func:`src.state.read_log`) from
	index ``n`` on, updating ``last`` {gid: {idx, action, anchor, anchor_idx}} in place; returns the new count."""
	for line in buf.split(b"\n"):
		if not line.strip():
			continue
		if any(m in line for m in _ANCHOR_MARKS):
			try:
				ev = json.loads(line)
			except ValueError:
				ev = None
			if isinstance(ev, dict) and ev.get("action") in _ANCHOR_ACTIONS:
				gid = ev.get("section")
				prev = last.get(gid) or {}
				rec = {"idx": n, "action": ev["action"], "anchor": prev.get("anchor"), "anchor_idx": prev.get("anchor_idx")}
				if ev["action"] == "section_anchored":
					rec["anchor"], rec["anchor_idx"] = dict(ev.get("anchor") or {}), n
				last[gid] = rec
		n += 1
	return n


def last_anchor_index(project) -> dict:
	"""``{"n": events in the log, "last": {gid: {idx, action, anchor, anchor_idx}}}``: for each group that was ever
	anchored, the 0-based index and action of its last ``section_anchored`` / ``section_unanchored`` event, plus the
	anchor dict (and index) of its last ``section_anchored``. Only complete lines count (an event being appended is
	not there yet). Cached per log path and extended with the appended bytes only (module docstring); the returned
	dict is a copy."""
	fp = os.path.abspath(project.log_path)

	def read_from(offset):
		if not os.path.exists(fp):
			return b"", 0
		with open(fp, "rb") as f:
			f.seek(0, os.SEEK_END)
			size = f.tell()
			if size < offset:
				return None, size
			f.seek(max(0, offset - _TAIL))
			return f.read(), size

	with _index_lock:
		c = _index_cache.get(fp)
		data = None
		if c is not None:
			data, _ = read_retry(lambda: read_from(c["offset"]))
			start = max(0, c["offset"] - _TAIL)
			if data is None or data[:c["offset"] - start] != c["tail"]:
				c, data = None, None
			else:
				data = data[c["offset"] - start:]
		if c is None:
			data, _ = read_retry(lambda: read_from(0))
			c = {"offset": 0, "tail": b"", "n": 0, "last": {}}
		cut = data.rfind(b"\n") + 1               # complete lines only
		if cut:
			c["n"] = _scan_lines(data[:cut], c["n"], c["last"])
			old = c["tail"]
			c["offset"] += cut
			c["tail"] = (old + data[:cut])[-_TAIL:]
		_index_cache[fp] = c
		return {"n": c["n"], "last": {g: dict(r, anchor=dict(r["anchor"]) if r["anchor"] else None)
									 for g, r in c["last"].items()}}


# ---------------------------------------------------------------- pure helpers
def is_loose(project, gid) -> bool:
	"""The group exists, has no place, and is visible (not every piece a re-scan: the rule of ``sections_json``)."""
	s = project.sections.get(gid) if isinstance(gid, str) else None
	if s is None or s.anchor.get("anchored"):
		return False
	return not (s.cells_local and all(project.piece(pid).same_as for pid in s.cells_local))


def footprint(section, pos: dict) -> list:
	"""Board cells ``[(l, c), ...]`` of the section's pieces at ``pos`` ({l0, c0, rot[, mirror]}), in piece-id order."""
	a = {"l0": pos["l0"], "c0": pos["c0"], "rot": pos.get("rot") or 0, "mirror": bool(pos.get("mirror"))}
	return [section_cell(a, rc) for _, rc in sorted(section.cells_local.items())]


def _is_int(v) -> bool:
	return isinstance(v, int) and not isinstance(v, bool)


def _shape_ok(d) -> bool:
	return isinstance(d, dict) and all(k in d for k in ("gid", "l0", "c0", "rot", "log_n")) and isinstance(d["gid"], str)


def _position_ok(project, section, d) -> bool:
	if not all(_is_int(d.get(k)) for k in ("l0", "c0", "rot", "log_n")) or d["rot"] % 90:
		return False
	if "mirror" in d and not isinstance(d["mirror"], bool):
		return False
	return all(project.profile.in_grid(l, c) for l, c in footprint(section, d))


# ---------------------------------------------------------------- read
def _read_text(fp: str) -> Optional[str]:
	def rd():
		if not os.path.exists(fp):
			return None
		with open(fp, encoding="utf-8", errors="replace", newline="") as f:
			return f.read()
	return read_retry(rd)


def read_positions(project, index: Optional[dict] = None) -> tuple:
	"""``(positions, aviso)``: ``positions`` = {gid: {l0, c0, rot, mirror, t, log_n}} with the last counting line of
	each group (module docstring); ``aviso`` = {reason: count} of the skipped lines (reasons in
	:data:`MOTIVOS_LEITURA`; only the reasons seen). ``anterior_a_fixacao`` counts the normal stale lines (written
	before the group's last anchor / unanchor); the other reasons are anomalies. Never raises on the file's content.
	``index``: :func:`last_anchor_index` already in hand."""
	text = _read_text(mesa_path(project))
	pos, aviso = {}, {}
	if not text:
		return pos, aviso
	idx = index if index is not None else last_anchor_index(project)
	lines = text.split("\n")
	tail = lines.pop()                            # "" when the file ends with a newline
	if tail.strip():
		aviso["linha_incompleta"] = 1
	for raw in lines:
		if not raw.strip():
			continue
		try:
			d = json.loads(raw)
		except ValueError:
			d = None
		if not _shape_ok(d):
			why = "linha_partida"
		elif d["gid"] not in project.sections:
			why = "grupo_desconhecido"
		elif project.sections[d["gid"]].anchor.get("anchored"):
			why = "grupo_fixado"
		elif not is_loose(project, d["gid"]):
			why = "grupo_desconhecido"
		elif not _position_ok(project, project.sections[d["gid"]], d) or d["log_n"] > idx["n"]:
			why = "posicao_invalida"
		elif d["log_n"] <= (idx["last"].get(d["gid"]) or {"idx": -1})["idx"]:
			why = "anterior_a_fixacao"
		else:
			pos[d["gid"]] = {"l0": d["l0"], "c0": d["c0"], "rot": d["rot"] % 360, "mirror": bool(d.get("mirror")),
							 "t": d.get("t"), "log_n": d["log_n"]}
			continue
		aviso[why] = aviso.get(why, 0) + 1
	return pos, aviso


def effective_position(project, gid: str, positions: Optional[dict] = None, index: Optional[dict] = None) -> Optional[dict]:
	"""Where the loose group ``gid`` is drawn: its counting ``mesa.jsonl`` line (``origem: "mesa"``) → else the
	position of its last anchor when it was anchored and then unanchored (``origem: "fixacao"``, Q10 a) → else None
	(never shown, or not a loose group). ``positions`` / ``index``: :func:`read_positions` / :func:`last_anchor_index`
	already in hand (each is computed when omitted)."""
	if not is_loose(project, gid):
		return None
	if index is None:
		index = last_anchor_index(project)
	if positions is None:
		positions = read_positions(project, index)[0]
	if gid in positions:
		return dict(positions[gid], origem="mesa")
	last = index["last"].get(gid)
	if last and last["action"] == "section_unanchored" and last.get("anchor") and last["anchor"].get("l0") is not None:
		a = last["anchor"]
		return {"l0": int(a["l0"]), "c0": int(a["c0"]), "rot": int(a.get("rot") or 0) % 360,
				"mirror": bool(a.get("mirror")), "t": None, "log_n": None, "origem": "fixacao"}
	return None


def effective_positions(project, index: Optional[dict] = None) -> dict:
	"""{gid: effective position} of every shown loose group (groups with None are left out)."""
	if index is None:
		index = last_anchor_index(project)
	positions = read_positions(project, index)[0]
	out = {}
	for gid in sorted(project.sections):
		e = effective_position(project, gid, positions, index)
		if e is not None:
			out[gid] = e
	return out


# ---------------------------------------------------------------- validate + write
def _refuse(motivo: str, error: str, **kw) -> dict:
	return dict({"error": error, "motivo": motivo}, **kw)


def check_position(project, gid: str, l0, c0, rot, mirror: bool = False, shown: Optional[dict] = None) -> Optional[dict]:
	"""None when ``gid`` may be shown at ``(l0, c0, rot, mirror)`` now, else ``{'error': phrase, 'motivo': code,
	...}`` (codes: ``grupo_desconhecido``, ``grupo_fixado``, ``rot_invalida``, ``fora_da_grelha``, ``colocada``,
	``marcada``, ``outro_grupo``; ``celula`` = the first offending cell). ``shown``: :func:`effective_positions`
	already in hand (the group's own entry is ignored)."""
	s = project.sections.get(gid) if isinstance(gid, str) else None
	if s is not None and s.anchor.get("anchored"):
		return _refuse("grupo_fixado", "O grupo já tem lugar: tira-o do lugar primeiro.")
	if s is None or not is_loose(project, gid):
		return _refuse("grupo_desconhecido", "Grupo desconhecido.")
	if not (_is_int(l0) and _is_int(c0) and _is_int(rot)) or rot % 90:
		return _refuse("rot_invalida", "Posição inválida: a rotação tem de ser múltipla de 90°.")
	pos = {"l0": l0, "c0": c0, "rot": rot % 360, "mirror": bool(mirror)}
	cells = footprint(s, pos)
	prof, board = project.profile, project.board
	for cell in cells:
		if not prof.in_grid(*cell):
			return _refuse("fora_da_grelha", "Não cabe aqui: sai do tabuleiro.", celula=list(cell))
	for cell in cells:
		cur = board[cell]
		if cur["estado"] == "colocada":
			return _refuse("colocada", f"Não cabe aqui: a linha {cell[0]}, coluna {cell[1]} já tem uma peça.",
						   celula=list(cell))
		if board.occupied(cell):
			return _refuse("marcada", f"Não cabe aqui: a linha {cell[0]}, coluna {cell[1]} está marcada como montada.",
						   celula=list(cell))
	if shown is None:
		shown = effective_positions(project)
	mine = set(cells)
	for other, opos in sorted(shown.items()):
		if other == gid or other not in project.sections:
			continue
		hit = mine.intersection(footprint(project.sections[other], opos))
		if hit:
			cell = min(hit)
			return _refuse("outro_grupo", f"Não cabe aqui: fica por cima de outro grupo (linha {cell[0]}, coluna {cell[1]}).",
						   celula=list(cell))
	return None


def _holds(wlock) -> bool:
	"""True if the calling thread holds ``wlock``: ``src.server.SeqLock`` (owner thread), an ``RLock`` (``_is_owned``),
	else a plain lock that is at least locked (``locked()``)."""
	if hasattr(wlock, "_owner") and hasattr(wlock, "_depth"):
		return wlock._owner == threading.get_ident()
	if hasattr(wlock, "_is_owned"):
		return bool(wlock._is_owned())
	if hasattr(wlock, "locked"):
		return bool(wlock.locked())
	return False


def _append_line(fp: str, rec: dict) -> None:
	"""Append one JSON line, flushed and fsync'ed; a previous incomplete last line (a crash mid-append) is closed with a
	newline first, so the new line stays readable (the broken one is counted by :func:`read_positions`)."""
	lead = ""
	if os.path.exists(fp) and os.path.getsize(fp) > 0:
		def last_byte():
			with open(fp, "rb") as f:
				f.seek(-1, os.SEEK_END)
				return f.read(1)
		if read_retry(last_byte) != b"\n":
			lead = "\n"
	with open(fp, "a", encoding="utf-8", newline="\n") as f:
		f.write(lead + json.dumps(rec, ensure_ascii=False) + "\n")
		f.flush()
		os.fsync(f.fileno())


def write_position(project, gid: str, l0, c0, rot=0, *, wlock, mirror: bool = False,
				   shown: Optional[dict] = None) -> dict:
	"""«Mostrar no tabuleiro» / «Mover» / «Rodar»: validate (:func:`check_position`) and append one line to
	``mesa.jsonl``; returns the line, or ``{'error': phrase, 'motivo': code, ...}`` with nothing written.

	**The caller holds the write lock** (``Gui.wlock`` of the server, B2): the validation and the append must not be
	crossed by a write of the log (a «Encaixa» under the group). ``wlock`` is required: the lock object, checked to be
	held by this thread (motivo ``sem_bloqueio`` otherwise), or ``None`` for a single-writer caller with no server
	(tests, a CLI). This module never takes the lock itself. ``shown``: :func:`effective_positions` already in hand."""
	if wlock is not None and not _holds(wlock):
		return _refuse("sem_bloqueio", "Erro interno: escrita na mesa sem o bloqueio de escrita.")
	index = last_anchor_index(project)
	if shown is None:
		shown = effective_positions(project, index)
	bad = check_position(project, gid, l0, c0, rot, mirror, shown)
	if bad:
		return bad
	rec = {"gid": gid, "l0": int(l0), "c0": int(c0), "rot": int(rot) % 360,
		   "t": _dt.datetime.now().isoformat(timespec="seconds"), "log_n": int(index["n"])}
	if mirror:
		rec["mirror"] = True
	_append_line(mesa_path(project), rec)
	return rec
