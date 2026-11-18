"""Tests for :mod:`src.grupos` (F4, B2): the pure logic of the loose groups on the board.

Synthetic: the 8 x 6 rot180 profile and the groups of ``tests/test_mesa.py`` (G1 = L of 3 pieces
{(0,0), (0,1), (1,0)}, G2 = 1 piece, X = a loose piece). Covers the effective position (delegated to
:mod:`src.mesa`), the initial position of «Mostrar no tabuleiro» (Q3: candidate 1 with margin >= ``margin_min``
and free, else the valid position nearest the centre of the view), the validation, «Rodar» (Q5 b: no sliding,
«Não cabe aqui rodado: move primeiro»), ``sobreposto`` (derived, never written), the count of the pieces in loose
groups, the likely place (Q4 b), the confidence rule (decisions 1 and 2 of Tiago) and determinism.
"""

import os

import pytest

from src import grupos as GR
from src import mesa
from test_mesa import _add, _photo, _w, groups, proj  # noqa: F401 - fixtures


def _cand(cell0, rot=0, margin=2.0, mirror=False):
	return {"cell0": list(cell0), "rot": rot, "mirror": mirror, "score": 1.0, "margin": margin}


@pytest.fixture
def cgroups(proj):
	"""G1 (L of 3) with candidate 1 at (2,2) rot 0 margin 2.0; G2 (1 piece) with candidate 1 at (4,4) margin 1.0
	(below margin_min 1.5); G3 (2 pieces in a row) without candidates; X loose."""
	a, b, c, d, e, f, x = _add(proj, 7)
	g1 = proj.register_section(None, "blocos", {a: (0, 0), b: (0, 1), c: (1, 0)}, candidates=[_cand((2, 2))])
	g2 = proj.register_section(None, "blocos", {d: (0, 0)}, candidates=[_cand((4, 4), margin=1.0)])
	g3 = proj.register_section(None, "blocos", {e: (0, 0), f: (0, 1)})
	return proj, g1, g2, g3, x


# ---------------------------------------------------------------- re-exports / validation
def test_footprint_and_effective_position_are_mesas(groups):
	pr, g1, g2, _ = groups
	assert GR.footprint is mesa.footprint
	assert GR.effective_position(pr, g1) is None
	_w(pr, g1, 2, 2, 90)
	assert GR.effective_position(pr, g1) == mesa.effective_position(pr, g1)


def test_valid_matches_check_position(groups):
	pr, g1, g2, x = groups
	pr.place(x, (3, 3))
	for pos in ({"l0": 2, "c0": 2, "rot": 0}, {"l0": 2, "c0": 3, "rot": 0}, {"l0": 6, "c0": 1, "rot": 0},
				{"l0": 2, "c0": 2, "rot": 90}, {"l0": 1, "c0": 1, "rot": 180}):
		assert GR.valid(pr, g1, pos) == mesa.check_position(pr, g1, pos["l0"], pos["c0"], pos["rot"])


# ---------------------------------------------------------------- initial position (Q3)
def test_initial_position_candidate_with_margin(cgroups):
	pr, g1, g2, g3, x = cgroups
	p = GR.initial_position(pr, g1, centro=(5.0, 7.0))
	assert (p["l0"], p["c0"], p["rot"], p["origem"]) == (2, 2, 0, "candidato")


def test_initial_position_candidate_below_margin_goes_near_the_view(cgroups):
	pr, g1, g2, g3, x = cgroups
	p = GR.initial_position(pr, g2, centro=(5.0, 7.0))
	assert (p["l0"], p["c0"], p["rot"], p["origem"]) == (5, 7, 0, "perto_da_vista")


def test_initial_position_candidate_taken_goes_near_the_view(cgroups):
	pr, g1, g2, g3, x = cgroups
	pr.place(x, (2, 3))                                           # under the candidate's footprint
	p = GR.initial_position(pr, g1, centro=(2.0, 3.0))
	assert p["origem"] == "perto_da_vista"
	assert GR.valid(pr, g1, p) is None
	assert (2, 3) not in GR.footprint(pr.sections[g1], p)


def test_initial_position_nearest_is_valid_and_deterministic(cgroups):
	pr, g1, g2, g3, x = cgroups
	pr.place(x, (3, 4))
	_w(pr, g2, 3, 5)
	ps = [GR.initial_position(pr, g3, centro=(3.2, 4.4)) for _ in range(3)]
	assert ps[0] == ps[1] == ps[2]
	p = ps[0]
	assert GR.valid(pr, g3, p) is None
	cells = GR.footprint(pr.sections[g3], p)
	# brute force: no valid position has its footprint centre nearer the view centre
	def d(pos):
		fp = GR.footprint(pr.sections[g3], pos)
		cl = sum(c[0] for c in fp) / len(fp)
		cc = sum(c[1] for c in fp) / len(fp)
		return (cl - 3.2) ** 2 + (cc - 4.4) ** 2
	best = min(d({"l0": l, "c0": c, "rot": 0}) for l in range(1, 7) for c in range(1, 9)
			   if GR.valid(pr, g3, {"l0": l, "c0": c, "rot": 0}) is None)
	assert d(p) == pytest.approx(best)
	assert all(pr.board[c]["estado"] != "colocada" for c in cells)


def test_initial_position_default_centre_and_no_room(cgroups):
	pr, g1, g2, g3, x = cgroups
	p = GR.initial_position(pr, g3)                               # the board centre (3.5, 4.5)
	assert p is not None and GR.valid(pr, g3, p) is None
	# fill every cell but one: a 2-piece group has no room
	for l in range(1, 7):
		for c in range(1, 9):
			if (l, c) != (6, 8):
				pr.mark_cell_full((l, c))
	assert GR.initial_position(pr, g3, centro=(1.0, 1.0)) is None
	q = GR.initial_position(pr, g2, centro=(1.0, 1.0))
	assert (q["l0"], q["c0"]) == (6, 8)


def test_initial_position_already_shown_is_the_effective_one(cgroups):
	pr, g1, g2, g3, x = cgroups
	_w(pr, g3, 5, 2, 90)
	p = GR.initial_position(pr, g3, centro=(1.0, 1.0))
	assert (p["l0"], p["c0"], p["rot"], p["origem"]) == (5, 2, 90, "mesa")


# ---------------------------------------------------------------- likely place (Q4 b)
def test_likely_place_only_with_margin(cgroups):
	pr, g1, g2, g3, x = cgroups
	lp = GR.likely_place(pr, g1)
	assert lp["cell0"] == [2, 2] and lp["rot"] == 0 and lp["margin"] == 2.0
	assert sorted(map(tuple, lp["footprint"])) == [(2, 2), (2, 3), (3, 2)]
	assert GR.likely_place(pr, g2) is None
	assert GR.likely_place(pr, g3) is None


# ---------------------------------------------------------------- «Rodar» (Q5 b)
def test_rotate_keeps_the_group_in_place(groups):
	pr, g1, g2, _ = groups
	s = pr.sections[g1]
	pos = {"l0": 3, "c0": 4, "rot": 0}
	r = GR.rotate(pr, g1, pos, 90)
	assert "error" not in r and r["rot"] == 90
	before, after = GR.footprint(s, pos), GR.footprint(s, r)
	bb = lambda fp: (min(c[0] for c in fp), min(c[1] for c in fp), max(c[0] for c in fp), max(c[1] for c in fp))  # noqa: E731
	assert bb(before) == bb(after) == (3, 4, 4, 5)               # the 2 x 2 box of the L stays where it was
	# four quarter turns come back to the start
	p = dict(pos)
	for _ in range(4):
		p = GR.rotate(pr, g1, p, 90)
	assert (p["l0"], p["c0"], p["rot"]) == (3, 4, 0)
	q = GR.rotate(pr, g1, pos, -90)
	assert q["rot"] == 270 and bb(GR.footprint(s, q)) == (3, 4, 4, 5)


def test_rotate_does_not_slide(groups):
	pr, g1, g2, x = groups
	pr.place(x, (4, 5))                                           # the cell the L would take when turned
	pos = {"l0": 3, "c0": 4, "rot": 0}
	assert GR.valid(pr, g1, pos) is None
	r = GR.rotate(pr, g1, pos, 90)
	assert r["error"] == "Não cabe aqui rodado: move primeiro." and r["motivo"] == "colocada"
	# a 3 x 1 bar at the edge: turning it leaves the board
	a, b, c = _add(pr, 3)
	g = pr.register_section(None, "blocos", {a: (0, 0), b: (0, 1), c: (0, 2)})
	r = GR.rotate(pr, g, {"l0": 1, "c0": 3, "rot": 0}, 90)
	assert r["error"] == "Não cabe aqui rodado: move primeiro." and r["motivo"] == "fora_da_grelha"


# ---------------------------------------------------------------- sobreposto
def test_sobreposto_is_derived(groups):
	pr, g1, g2, x = groups
	_w(pr, g1, 2, 2)
	pos = GR.effective_position(pr, g1)
	assert GR.sobreposto(pr, g1, pos) is None
	pr.place(x, (2, 3))                                           # a «Encaixa» under the shown group
	s = GR.sobreposto(pr, g1, GR.effective_position(pr, g1))
	assert s["motivo"] == "colocada" and s["celula"] == [2, 3] and s["error"]
	pr.unplace(x)
	pr.mark_cell_full((3, 2))
	assert GR.sobreposto(pr, g1, GR.effective_position(pr, g1))["motivo"] == "marcada"
	# never written: the mesa line is unchanged
	with open(mesa.mesa_path(pr), encoding="utf-8") as f:
		assert len(f.readlines()) == 1


# ---------------------------------------------------------------- count
def test_count_loose(proj):
	a, b, c, d, e, f = _add(proj, 6)
	g1 = proj.register_section(None, "blocos", {a: (0, 0), b: (0, 1), c: (1, 0)})
	g2 = proj.register_section(None, "blocos", {d: (0, 0)})
	g3 = proj.register_section(None, "blocos", {e: (0, 0)})
	proj.mark_same_as(e, f)                                       # only re-scans: not visible
	assert GR.count_loose(proj) == {"grupos": 2, "pecas": 4}
	proj.anchor_section(g2, 1, 1)
	assert GR.count_loose(proj) == {"grupos": 1, "pecas": 3}
	proj.unanchor_section(g2)
	assert GR.count_loose(proj) == {"grupos": 2, "pecas": 4}
	assert g3 in proj.sections


# ---------------------------------------------------------------- confidence (decisions 1 and 2 of Tiago, C1)
@pytest.mark.parametrize("rot_fonte,vizinhas,esperado", [
	("tiago", "confirmam", "confirmado"),
	("tiago", "sem_vizinhas", "confirmado"),
	("tiago", "inconclusivas", "confirmado"),
	("tiago", "discordam", "a_confirmar"),
	("programa", "confirmam", "confirmado"),
	("programa", "sem_vizinhas", "a_confirmar"),
	("programa", "inconclusivas", "a_confirmar"),
	("programa", "discordam", "a_confirmar"),
])
def test_confidence_rule(rot_fonte, vizinhas, esperado):
	assert GR.confidence(rot_fonte, vizinhas) == esperado


def test_global_verdict():
	assert GR.verdict({}) == "sem_vizinhas"
	assert GR.verdict({"P1": "sem_vizinhas", "P2": "sem_vizinhas"}) == "sem_vizinhas"
	assert GR.verdict({"P1": "sem_vizinhas", "P2": "confirmam"}) == "confirmam"
	assert GR.verdict({"P1": "inconclusivas", "P2": "sem_vizinhas"}) == "inconclusivas"
	assert GR.verdict({"P1": "confirmam", "P2": "inconclusivas"}) == "confirmam"
	assert GR.verdict({"P1": "confirmam", "P2": "discordam"}) == "discordam"


def test_nothing_is_written_by_the_pure_functions(cgroups):
	pr, g1, g2, g3, x = cgroups
	with open(pr.log_path, "rb") as f:
		log0 = f.read()
	GR.initial_position(pr, g1)
	GR.rotate(pr, g1, {"l0": 2, "c0": 2, "rot": 0}, 90)
	GR.sobreposto(pr, g1, {"l0": 2, "c0": 2, "rot": 0})
	GR.count_loose(pr)
	GR.likely_place(pr, g1)
	with open(pr.log_path, "rb") as f:
		assert f.read() == log0
	assert not os.path.exists(mesa.mesa_path(pr))
