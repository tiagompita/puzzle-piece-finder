"""Tests for :mod:`src.mesa` (F4, B1): the free position of the loose groups in ``projects/<id>/mesa.jsonl``.

Synthetic: a 8 x 6 rot180 profile written to ``tmp_path`` (same helpers as ``tests/test_state.py``). Covers writing and
reading (the last valid line of each group wins), the tolerant read (broken / incomplete lines, unknown or anchored
groups, invalid positions are skipped and counted, never an error), the ``log_n`` rule (move -> anchor -> unanchor
leaves the group where it was anchored; a line written after the unanchor counts again), the validation on write
(outside the grid, over a placed piece, over a cell the user marked full, over another shown group; «full in the
photo» passes) and that writing never touches the log, the board, nor the two ingredients of ``render_version()``.
"""

import json
import os
import threading

import numpy as np
import pytest

from src import mesa
from src.profile import PuzzleProfile
from src.shape import analyse
from src.state import Photo, Project

MMPP = 25.4 / 300
_RECT = analyse(np.array([[0, 0], [220, 0], [220, 210], [0, 210]]), MMPP)


# ---------------------------------------------------------------- fixtures / helpers
def _profile_path(tmp_path, cols=8, rows=6):
	pp = tmp_path / "puzzle.json"
	PuzzleProfile(id="t", grid={"cols": cols, "rows": rows}, symmetry={"type": "rot180"}).save(str(pp))
	return str(pp)


@pytest.fixture
def proj(tmp_path):
	return Project.create(str(tmp_path / "proj"), _profile_path(tmp_path))


def _add(pr, n, lote=1):
	sid = pr.add_scan(None, dpi=300, lote=lote)
	return [pr.add_piece(sid, {"index_in_scan": i, "n_no_lote": i + 1, "shape": _RECT}) for i in range(n)]


def _photo(pr, full=()):
	m = [[0] * pr.profile.cols for _ in range(pr.profile.rows)]
	for l, c in full:
		m[l - 1][c - 1] = 1
	return Photo(id=None, file="foto.jpg", map=m)


@pytest.fixture
def groups(proj):
	"""Two loose groups: G1 = L of 3 pieces {(0,0), (0,1), (1,0)}, G2 = 1 piece; plus one loose piece X."""
	a, b, c, d, x = _add(proj, 5)
	g1 = proj.register_section(None, "blocos", {a: (0, 0), b: (0, 1), c: (1, 0)})
	g2 = proj.register_section(None, "blocos", {d: (0, 0)})
	return proj, g1, g2, x


def _w(pr, gid, l0, c0, rot=0, **kw):
	return mesa.write_position(pr, gid, l0, c0, rot, wlock=None, **kw)


def _raw(pr, text):
	with open(mesa.mesa_path(pr), "a", encoding="utf-8", newline="\n") as f:
		f.write(text)


# ---------------------------------------------------------------- write + read
def test_write_and_read_last_line_wins(groups):
	pr, g1, g2, _ = groups
	assert not os.path.exists(mesa.mesa_path(pr))
	pos, aviso = mesa.read_positions(pr)
	assert pos == {} and aviso == {}
	r = _w(pr, g1, 2, 2)
	assert "error" not in r
	assert r["gid"] == g1 and (r["l0"], r["c0"], r["rot"]) == (2, 2, 0) and r["log_n"] == len(pr.events())
	assert _w(pr, g1, 3, 4, 90).get("error") is None
	assert _w(pr, g2, 5, 7).get("error") is None
	pos, aviso = mesa.read_positions(pr)
	assert set(pos) == {g1, g2}
	assert (pos[g1]["l0"], pos[g1]["c0"], pos[g1]["rot"]) == (3, 4, 90)
	assert (pos[g2]["l0"], pos[g2]["c0"]) == (5, 7)
	assert aviso == {}
	eff = mesa.effective_position(pr, g1)
	assert (eff["l0"], eff["c0"], eff["rot"], eff["origem"]) == (3, 4, 90, "mesa")
	with open(mesa.mesa_path(pr), encoding="utf-8") as f:
		lines = [json.loads(s) for s in f]
	assert len(lines) == 3 and set(lines[0]) == {"gid", "l0", "c0", "rot", "t", "log_n"}


def test_footprint_rot_and_mirror(groups):
	pr, g1, _, _ = groups
	s = pr.sections[g1]
	assert sorted(mesa.footprint(s, {"l0": 2, "c0": 2, "rot": 0})) == [(2, 2), (2, 3), (3, 2)]
	# 90° clockwise: (0,1) -> (1,0), (1,0) -> (0,-1)  (state.section_cell)
	assert sorted(mesa.footprint(s, {"l0": 2, "c0": 2, "rot": 90})) == [(2, 1), (2, 2), (3, 2)]
	assert sorted(mesa.footprint(s, {"l0": 2, "c0": 2, "rot": 0, "mirror": True})) == [(2, 1), (2, 2), (3, 2)]


# ---------------------------------------------------------------- tolerant read
def test_tolerant_read_skips_and_counts(groups):
	pr, g1, g2, _ = groups
	_w(pr, g1, 2, 2)
	_w(pr, g2, 5, 7)
	n = len(pr.events())
	_raw(pr, "{isto não é json\n")                                                           # broken line
	_raw(pr, json.dumps({"gid": "G9999", "l0": 1, "c0": 1, "rot": 0, "t": "x", "log_n": n}) + "\n")   # unknown group
	_raw(pr, json.dumps({"gid": g1, "l0": 6, "c0": 8, "rot": 0, "t": "x", "log_n": n}) + "\n")       # outside the grid
	_raw(pr, json.dumps({"gid": g1, "l0": 2, "c0": 2, "rot": 45, "t": "x", "log_n": n}) + "\n")      # rot not ×90
	_raw(pr, json.dumps({"gid": g1, "l0": "2", "c0": 2, "rot": 0, "t": "x", "log_n": n}) + "\n")     # wrong type
	_raw(pr, json.dumps([1, 2, 3]) + "\n")                                                    # not an object
	_raw(pr, '{"gid": "' + g1 + '", "l0": 4, "c0"')                                            # incomplete last line
	pos, aviso = mesa.read_positions(pr)
	assert (pos[g1]["l0"], pos[g1]["c0"]) == (2, 2) and (pos[g2]["l0"], pos[g2]["c0"]) == (5, 7)
	assert aviso == {"linha_partida": 2, "grupo_desconhecido": 1, "posicao_invalida": 3, "linha_incompleta": 1}


def test_tolerant_read_anchored_group_and_append_after_incomplete(groups):
	pr, g1, g2, _ = groups
	_w(pr, g1, 2, 2)
	_w(pr, g2, 5, 7)
	pr.anchor_section(g2, 1, 1)
	pos, aviso = mesa.read_positions(pr)
	assert set(pos) == {g1} and aviso == {"grupo_fixado": 1}
	assert mesa.effective_position(pr, g2) is None                     # anchored: on the board, not on the table
	# a write after an incomplete last line (a crash mid-append) starts on a line of its own
	_raw(pr, '{"gid": "' + g1 + '", "l0"')
	assert _w(pr, g1, 4, 4).get("error") is None
	pos, aviso = mesa.read_positions(pr)
	assert (pos[g1]["l0"], pos[g1]["c0"]) == (4, 4)
	assert aviso == {"grupo_fixado": 1, "linha_partida": 1}


def test_read_tolerates_missing_and_empty_file(groups):
	pr, g1, _, _ = groups
	open(mesa.mesa_path(pr), "w").close()
	assert mesa.read_positions(pr) == ({}, {})
	assert mesa.effective_position(pr, g1) is None


# ---------------------------------------------------------------- log_n
def test_log_n_show_move_anchor_unanchor(groups):
	pr, g1, _, _ = groups
	_w(pr, g1, 1, 1)                     # «Mostrar»
	_w(pr, g1, 2, 5)                     # «Mover»
	pr.anchor_section(g1, 4, 3, rot=90)  # «Fixar» somewhere else (as the server will: at the effective position)
	pr.unanchor_section(g1)              # «Tirar o grupo inteiro do lugar»
	n_log = len(pr.events())
	eff = mesa.effective_position(pr, g1)
	assert (eff["l0"], eff["c0"], eff["rot"], eff["origem"]) == (4, 3, 90, "fixacao")
	pos, aviso = mesa.read_positions(pr)
	assert g1 not in pos and aviso == {"anterior_a_fixacao": 2}
	assert len(pr.events()) == n_log      # no extra write
	with open(mesa.mesa_path(pr), encoding="utf-8") as f:
		assert len(f.readlines()) == 2
	# a line written AFTER the unanchor counts again
	r = _w(pr, g1, 5, 6)
	assert r["log_n"] == n_log
	eff = mesa.effective_position(pr, g1)
	assert (eff["l0"], eff["c0"], eff["rot"], eff["origem"]) == (5, 6, 0, "mesa")


def test_log_n_rule_is_per_group(groups):
	pr, g1, g2, _ = groups
	_w(pr, g1, 1, 1)
	_w(pr, g2, 5, 7)
	pr.anchor_section(g2, 6, 8)
	pr.unanchor_section(g2)
	assert (mesa.effective_position(pr, g1)["l0"], mesa.effective_position(pr, g1)["origem"]) == (1, "mesa")
	assert mesa.effective_position(pr, g2)["origem"] == "fixacao"


def test_never_anchored_without_line_not_shown(groups):
	pr, g1, g2, _ = groups
	assert mesa.effective_position(pr, g1) is None
	assert mesa.effective_positions(pr) == {}
	_w(pr, g2, 5, 7)
	assert set(mesa.effective_positions(pr)) == {g2}


def test_last_anchor_index(groups):
	pr, g1, g2, _ = groups
	idx = mesa.last_anchor_index(pr)
	assert idx["n"] == len(pr.events()) and idx["last"] == {}
	pr.anchor_section(g1, 2, 2, rot=180)
	ka = max(i for i, e in enumerate(pr.events()) if e["action"] == "section_anchored")
	pr.unanchor_section(g1)
	idx = mesa.last_anchor_index(pr)
	assert idx["n"] == len(pr.events())
	last = idx["last"][g1]
	assert last["idx"] == len(pr.events()) - 1 and last["action"] == "section_unanchored"
	assert last["anchor"]["l0"] == 2 and last["anchor"]["rot"] == 180 and last["anchor_idx"] == ka
	assert g2 not in idx["last"]


def test_last_anchor_index_follows_appends_and_rebuilds(groups):
	pr, g1, _, _ = groups
	a = mesa.last_anchor_index(pr)
	pr.anchor_section(g1, 2, 2)
	b = mesa.last_anchor_index(pr)                       # incremental: only the new bytes are read
	assert b["n"] == len(pr.events()) and b["last"][g1]["action"] == "section_anchored"
	assert a["n"] < b["n"]
	# the log rewritten shorter (a rebuild): the cache notices and starts over
	with open(pr.log_path, encoding="utf-8") as f:
		lines = f.readlines()
	with open(pr.log_path, "w", encoding="utf-8", newline="\n") as f:
		f.writelines(lines[:a["n"]])
	c = mesa.last_anchor_index(pr)
	assert c["n"] == a["n"] and c["last"] == {}


# ---------------------------------------------------------------- validation on write
def test_write_validation(groups):
	pr, g1, g2, x = groups
	pr.place(x, (3, 3))
	pr.mark_cell_full((5, 5))
	pr.register_photo(_photo(pr, full=[(1, 7), (1, 8), (2, 7)]))
	assert pr.board[(1, 7)]["fonte"] == "foto"
	before = os.path.getsize(mesa.mesa_path(pr)) if os.path.exists(mesa.mesa_path(pr)) else 0

	def motivo(r):
		assert "error" in r and isinstance(r["error"], str) and r["error"]
		return r["motivo"]

	assert motivo(_w(pr, g1, 6, 1)) == "fora_da_grelha"          # (7,1) outside a 6-row grid
	assert motivo(_w(pr, g1, 1, 8)) == "fora_da_grelha"          # (1,9)
	assert motivo(_w(pr, g1, 0, 3)) == "fora_da_grelha"
	assert motivo(_w(pr, g1, 2, 3)) == "colocada"                # (3,3) holds X
	assert motivo(_w(pr, g1, 4, 5)) == "marcada"                 # (5,5) marked full by Tiago
	assert motivo(_w(pr, g1, 1, 1, 45)) == "rot_invalida"
	assert motivo(_w(pr, "G9999", 1, 1)) == "grupo_desconhecido"
	after = os.path.getsize(mesa.mesa_path(pr)) if os.path.exists(mesa.mesa_path(pr)) else 0
	assert after == before                                       # a refusal writes nothing
	# «full in the photo» does not block
	assert _w(pr, g1, 1, 7).get("error") is None
	# over another shown group
	assert _w(pr, g2, 2, 8).get("error") is None
	assert motivo(_w(pr, g2, 1, 7)) == "outro_grupo"
	assert motivo(_w(pr, g2, 2, 7)) == "outro_grupo"
	# shown= (the effective positions the caller already has) gives the same answer
	assert motivo(_w(pr, g2, 2, 7, shown=mesa.effective_positions(pr))) == "outro_grupo"
	# the group's own old position never blocks it
	assert _w(pr, g1, 4, 1).get("error") is None
	assert _w(pr, g1, 4, 2).get("error") is None                 # overlaps its own previous footprint: fine
	# an anchored group is refused
	pr.anchor_section(g2, 6, 8)
	assert motivo(_w(pr, g2, 6, 1)) == "grupo_fixado"
	pos, aviso = mesa.read_positions(pr)
	assert set(pos) == {g1} and (pos[g1]["l0"], pos[g1]["c0"]) == (4, 2)


def test_write_refuses_group_over_group_placed_by_fixation(groups):
	"""A group that was anchored and then unanchored stays shown at its anchor (no line): it blocks the others."""
	pr, g1, g2, _ = groups
	pr.anchor_section(g2, 3, 3)
	pr.unanchor_section(g2)
	assert mesa.effective_position(pr, g2)["origem"] == "fixacao"
	assert _w(pr, g1, 2, 3)["motivo"] == "outro_grupo"           # (3,3) under G2
	assert _w(pr, g1, 1, 1).get("error") is None


def test_invisible_group_is_unknown(proj):
	a, b = _add(proj, 2)
	g = proj.register_section(None, "blocos", {a: (0, 0)})
	proj.mark_same_as(a, b)
	assert _w(proj, g, 1, 1)["motivo"] == "grupo_desconhecido"


def test_write_requires_the_write_lock(groups):
	pr, g1, _, _ = groups
	lk = threading.RLock()
	r = mesa.write_position(pr, g1, 1, 1, 0, wlock=lk)
	assert r["motivo"] == "sem_bloqueio"
	assert not os.path.exists(mesa.mesa_path(pr))
	with lk:
		assert mesa.write_position(pr, g1, 1, 1, 0, wlock=lk).get("error") is None
	with pytest.raises(TypeError):
		mesa.write_position(pr, g1, 1, 1, 0)                     # wlock is a required keyword


def test_write_lock_held_by_another_thread_is_refused(groups):
	pr, g1, _, _ = groups
	lk = threading.RLock()
	got, done = threading.Event(), threading.Event()

	def hold():
		with lk:
			got.set()
			done.wait(5)
	t = threading.Thread(target=hold)
	t.start()
	got.wait(5)
	try:
		assert mesa.write_position(pr, g1, 1, 1, 0, wlock=lk)["motivo"] == "sem_bloqueio"
	finally:
		done.set()
		t.join()


# ---------------------------------------------------------------- nothing touches the log
def test_writes_never_touch_log_board_or_render_version(groups):
	pr, g1, g2, x = groups
	pr.place(x, (6, 1))
	pl = pr.p("render", "placements.json")
	os.makedirs(os.path.dirname(pl), exist_ok=True)
	with open(pl, "w", encoding="utf-8") as f:
		f.write("{}\n")
	with open(pr.log_path, "rb") as f:
		log0 = f.read()
	board0 = pr.board.to_dict()
	st0 = os.stat(pl)
	with open(pl, "rb") as f:
		pl0 = f.read()
	moves = [(g1, 1, 1, 0), (g1, 2, 2, 90), (g2, 5, 7, 0), (g1, 3, 3, 180), (g2, 5, 6, 0),
			 (g1, 3, 4, 270), (g1, 2, 4, 0), (g2, 4, 8, 0), (g1, 1, 2, 0), (g1, 2, 2, 0)]
	for gid, l0, c0, rot in moves:
		assert _w(pr, gid, l0, c0, rot).get("error") is None, (gid, l0, c0, rot)
	with open(pr.log_path, "rb") as f:
		assert f.read() == log0
	assert os.path.getsize(pr.log_path) == len(log0)            # Gui.version() = log size
	assert pr.board.to_dict() == board0
	assert Project.open(pr.path).board.to_dict() == board0
	st1 = os.stat(pl)
	assert st1.st_mtime_ns == st0.st_mtime_ns                   # Gui._pl_mtime()
	with open(pl, "rb") as f:
		assert f.read() == pl0
	with open(mesa.mesa_path(pr), encoding="utf-8") as f:
		assert len(f.readlines()) == len(moves)
