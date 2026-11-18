"""F4 B2b: one rotation criterion for the suspects and «Fixar», and a likely place that is valid (decisions of Tiago,
2026-11-18, ``docs/decisoes.md``; diagnosis ``docs/diagnostico/gui/F4_ROTACAO.md``).

Synthetic board: the 4 x 6 profile of ``tests/test_query.py``, pieces of ``tests/synth.py`` (kinds top, right, bottom,
left in the board pose). Placed: A ``TBTB`` at (2,3) (its E side is B); optionally P ``TTBT`` at (1,3) (its S side B
meets A's N side T and pins A: any turn of A puts a B against P's B). Loose: W ``TBTB`` (to fill a cell), and the
groups, all scanned at the same angle (a legacy page):

* G1 = X ``BBBT``: at (2,4) rot 0 its W side (T) meets A's B: the neighbour confirms; at rot 90 a B meets A's B;
* GQ = Q ``BBBB``: at (2,4) every rotation puts a B on A's B (impossible in every rotation when P pins A; with A free
  the conflict is A's, ``explicada``);
* GR = R ``BTTT`` at local (0,0), a re-scan (``same_as`` W), + Y ``BTTT`` at (0,1): at (3,3) R sits under A;
* G2 = Y2 ``BTTT`` + Z ``TTTB`` side by side.

Cases equivalent to the B2½ findings (``F4_ROTACAO.md``): G0095 / G0096 (candidate on a placed cell, every rotation),
G0093 (2 pieces, one on a placed cell), G0094 (a member impossible in every rotation), G0098 (the neighbours disagree
with the candidate's rotation, nothing else valid), P0615 (a re-scan in a group).
"""

import os

import cv2
import numpy as np
import pytest
from PIL import Image

import synth
from src import consistency as C
from src import grupos as GR
from src.shape import analyse
from src.state import Project
from test_consistency import _row_project
from test_query import BG, _piece_px
from test_shape import MMPP

PSI_A, PSI_P, PSI_W, PSI_G = 23.0, -35.0, 50.0, 12.0
SPEC = [("A", "TBTB", PSI_A), ("P", "TTBT", PSI_P), ("W", "TBTB", PSI_W), ("X", "BBBT", PSI_G), ("Q", "BBBB", PSI_G),
		("R", "BTTT", PSI_G), ("Y", "BTTT", PSI_G), ("Y2", "BTTT", PSI_G), ("Z", "TTTB", PSI_G)]


def _cand(cell0, rot=0, margin=2.0, score=10.0):
	return {"cell0": list(cell0), "rot": rot, "mirror": False, "score": score, "margin": margin}


def _build(tmp_path, pin=False, cands=None):
	"""``(project, ids)``: A placed at (2,3) (+ P at (1,3) when ``pin``); groups G1 {X}, GQ {Q}, GR {R (re-scan of W),
	Y}, G2 {Y2, Z}; ``cands``: {group name: [candidate dicts]}."""
	cands = cands or {}
	os.makedirs(tmp_path, exist_ok=True)
	prof = synth.profile(rows=4, cols=6, p90=None)
	pp = tmp_path / "puzzle.json"
	prof.save(str(pp))
	pr = Project.create(str(tmp_path / "proj"), str(pp))
	pts_all = [_piece_px(synth.body_mm(k, deltas=(0.3 * (i % 3), -0.2, 0.1, 0.2 * (i % 4))), psi, (400 + 600 * i, 400))
			   for i, (_, k, psi) in enumerate(SPEC)]
	img = np.full((800, 600 * len(SPEC) + 200, 3), BG, np.uint8)
	for i, pts in enumerate(pts_all):
		cv2.fillPoly(img, [np.round(pts).astype(np.int32).reshape(-1, 1, 2)], (40 + 20 * i, 200 - 15 * i, 90))
	scan = tmp_path / "scan.png"
	Image.fromarray(img).save(scan)
	sid = pr.add_scan(str(scan), dpi=300, lote=4)
	os.makedirs(pr.p("crops"), exist_ok=True)
	ids = {}
	for i, ((name, _, _), pts) in enumerate(zip(SPEC, pts_all)):
		x0, y0 = np.floor(pts.min(0)).astype(int) - 10
		x1, y1 = np.ceil(pts.max(0)).astype(int) + 10
		al = np.zeros(img.shape[:2], np.uint8)
		cv2.fillPoly(al, [np.round(pts).astype(np.int32).reshape(-1, 1, 2)], 255)
		rel = f"crops/P{i + 1:04d}.png"
		Image.fromarray(np.ascontiguousarray(np.dstack([img, al])[y0:y1, x0:x1])).save(pr.p(rel))
		ids[name] = pr.add_piece(sid, {"index_in_scan": i, "n_no_lote": i + 1, "shape": analyse(pts, MMPP),
									   "contour": pts, "bbox": [int(x0), int(y0), int(x1 - x0), int(y1 - y0)],
									   "crop_path": rel})
	pr.place(ids["A"], (2, 3), theta_deg=-PSI_A)
	if pin:
		pr.place(ids["P"], (1, 3), theta_deg=-PSI_P)
	ids["G1"] = pr.register_section(sid, "blocos", {ids["X"]: (0, 0)}, candidates=cands.get("G1", []))
	ids["GQ"] = pr.register_section(sid, "blocos", {ids["Q"]: (0, 0)}, candidates=cands.get("GQ", []))
	ids["GR"] = pr.register_section(sid, "blocos", {ids["R"]: (0, 0), ids["Y"]: (0, 1)}, candidates=cands.get("GR", []))
	ids["G2"] = pr.register_section(sid, "blocos", {ids["Y2"]: (0, 0), ids["Z"]: (0, 1)}, candidates=cands.get("G2", []))
	pr.mark_same_as(ids["R"], ids["W"])
	pr.save()
	return pr, ids


# ---------------------------------------------------------------- «Fixar»: the members it places, nothing else
def test_rescan_in_a_group_is_not_graded(tmp_path):
	"""P0615 in G0051: a re-scan (``same_as``) is not placed by «Fixar», so it is not graded (nor a neighbour)."""
	pr, ids = _build(tmp_path)
	r, y = ids["R"], ids["Y"]
	chk = GR.rotation_check(pr, ids["GR"], {"l0": 3, "c0": 3, "rot": 0})
	assert r not in chk["pecas"]
	assert chk["nao_avaliadas"] == {r: "re_scan"}
	assert chk["pecas"] == {y: "sem_vizinhas"}                    # R is not mounted: Y has no neighbour
	assert chk["vizinhas"] == "sem_vizinhas"


def test_occupied_place_never_confirms(tmp_path):
	"""A member on a placed cell: the position is refused before anything is evaluated (never «confirmam»)."""
	pr, ids = _build(tmp_path)
	pr.place(ids["W"], (2, 4), theta_deg=-PSI_W)
	chk = GR.rotation_check(pr, ids["G1"], {"l0": 2, "c0": 4, "rot": 0})
	assert chk.get("vizinhas") != "confirmam"
	assert chk["motivo"] == "colocada" and chk["celula"] == [2, 4] and chk["error"]


def test_same_group_free_place_still_confirms(tmp_path):
	"""Control: the same group on the free cell is confirmed by A (the criterion did not get blind)."""
	pr, ids = _build(tmp_path)
	chk = GR.rotation_check(pr, ids["G1"], {"l0": 2, "c0": 4, "rot": 0})
	assert chk["pecas"] == {ids["X"]: "confirmam"} and chk["vizinhas"] == "confirmam"
	chk = GR.rotation_check(pr, ids["G1"], {"l0": 2, "c0": 4, "rot": 90})
	assert chk["pecas"] == {ids["X"]: "discordam"} and chk["rot_alt_deg"] == {ids["X"]: -90}
	assert chk["impossiveis"] == []


def test_inside_neighbours_count_and_explained_rule(tmp_path):
	"""Decision 1: the group's own pieces are neighbours, and the ``explicada`` rule applies. GQ = Q at (2,4) with A
	free to turn: Q's B↔B is A's (A turned fixes it), so Q is not ``discordam``; with P pinning A it is, in every
	rotation (``impossiveis``)."""
	pr, ids = _build(tmp_path)
	chk = GR.rotation_check(pr, ids["GQ"], {"l0": 2, "c0": 4, "rot": 0})
	assert chk["pecas"][ids["Q"]] == "inconclusivas" and chk["impossiveis"] == []
	pr2, ids2 = _build(tmp_path / "pin", pin=True)
	chk = GR.rotation_check(pr2, ids2["GQ"], {"l0": 2, "c0": 4, "rot": 0})
	assert chk["pecas"][ids2["Q"]] == "discordam" and chk["impossiveis"] == [ids2["Q"]]
	# G2 at (3,3): Y2 under A (outside), Z beside Y2 only (inside): Z is graded but cannot confirm the place
	chk = GR.rotation_check(pr, ids["G2"], {"l0": 3, "c0": 3, "rot": 0})
	assert chk["pecas"] == {ids["Y2"]: "confirmam", ids["Z"]: "sem_vizinhas"}


def test_same_function_as_the_suspects(tmp_path, monkeypatch):
	"""«Fixar» grades through ``consistency.grade_at`` (the function of ``evaluate``), never ``evaluate`` itself."""
	pr, ids = _build(tmp_path)
	seen = []
	orig = C.grade_at

	def spy(project, pid, *a, **k):
		seen.append(pid)
		return orig(project, pid, *a, **k)
	monkeypatch.setattr(C, "grade_at", spy)
	monkeypatch.setattr(C, "evaluate", lambda *a, **k: (_ for _ in ()).throw(AssertionError("evaluate")))
	GR.rotation_check(pr, ids["G1"], {"l0": 2, "c0": 4, "rot": 0})
	assert seen == [ids["X"]]


def test_aviso_names_the_piece(tmp_path):
	pr, ids = _build(tmp_path)
	chk = GR.rotation_check(pr, ids["G1"], {"l0": 2, "c0": 4, "rot": 90})
	n = pr.piece(ids["X"]).n_no_lote
	a = GR.aviso_discordam(pr, chk["pecas"])
	assert a == f"Saco 4 · nº {n}: as peças ao lado dizem outra rotação."
	assert GR.aviso_discordam(pr, {ids["X"]: "confirmam"}) is None


# ---------------------------------------------------------------- lugar provável (decision 2)
OMIT = {
	# G0095: candidate 1 (margin 1.66) on a cell placed since
	"G0095_ocupado": ("G1", [_cand((2, 4), 0, 2.0, 10.0), _cand((4, 6), 0, 2.0, 30.0)], "W24", False),
	# G0096: the 3 candidates are the same cell in 3 rotations, placed since
	"G0096_ocupado_3_rot": ("G1", [_cand((2, 4), 0, 2.0, 10.0), _cand((2, 4), 90, 2.0, 10.5), _cand((2, 4), 180, 2.0, 11.0)],
							"W24", False),
	# G0093: 2 pieces, the other one on a placed cell
	"G0093_membro_ocupado": ("G2", [_cand((2, 2), 0, 2.0, 10.0)], None, False),
	# G0094: valid, but a member impossible in every rotation (A pinned by P)
	"G0094_impossivel_todas": ("GQ", [_cand((2, 4), 0, 2.0, 10.0), _cand((4, 6), 0, 2.0, 30.0)], None, True),
	# G0098: valid, the neighbours want another rotation; the other candidates are not valid
	"G0098_discordam": ("G1", [_cand((2, 4), 90, 2.0, 10.0), _cand((2, 3), 0, 2.0, 10.1), _cand((2, 3), 90, 2.0, 10.6)],
						None, False),
}


@pytest.mark.parametrize("name", list(OMIT))
def test_likely_place_is_omitted(tmp_path, name):
	g, cands, fill, pin = OMIT[name]
	pr, ids = _build(tmp_path, pin=pin, cands={g: cands})
	if fill == "W24":
		pr.place(ids["W"], (2, 4), theta_deg=-PSI_W)
	assert GR.likely_place(pr, ids[g]) is None


def test_likely_place_margin_recomputed_among_the_valid(tmp_path):
	"""Candidate 1 on a placed cell, 2 valid: the place is candidate 2, its margin against candidate 3 (distinct)."""
	cands = [_cand((3, 1), 0, 1.1, 10.0), _cand((2, 4), 0, 1.1, 11.0), _cand((4, 6), 0, 1.1, 20.0)]
	pr, ids = _build(tmp_path, cands={"G1": cands})
	pr.place(ids["W"], (3, 1), theta_deg=-PSI_W)
	lp = GR.likely_place(pr, ids["G1"])
	assert lp["cell0"] == [2, 4] and lp["candidato"] == 2 and lp["vizinhas"] == "confirmam"
	assert lp["margin"] == pytest.approx(20.0 / 11.0, abs=1e-3)
	# a second valid candidate too close (same cell, other rotation) is no alternative: no stored margin either
	cands = [_cand((3, 1), 0, 1.6, 10.0), _cand((2, 4), 0, 1.6, 11.0), _cand((2, 4), 180, 1.6, 12.0)]
	pr2, ids2 = _build(tmp_path / "b", cands={"G1": cands})
	pr2.place(ids2["W"], (3, 1), theta_deg=-PSI_W)
	assert GR.likely_place(pr2, ids2["G1"]) is None


def test_likely_place_kept_when_valid_and_confirmed(tmp_path):
	"""Candidate 1 valid, confirmed by A, no valid distinct alternative stored: the stored margin (a lower bound)."""
	pr, ids = _build(tmp_path, cands={"G1": [_cand((2, 4), 0, 2.0, 10.0)]})
	lp = GR.likely_place(pr, ids["G1"])
	assert lp["cell0"] == [2, 4] and lp["margin"] == 2.0 and lp["candidato"] == 1 and lp["footprint"] == [[2, 4]]


def test_likely_place_stored_margin_stands_unless_its_alternative_is_dropped(tmp_path):
	"""Candidate 1 valid: the solve's margin (over all its placements) stands; if the stored candidate that set it is
	no longer valid, the margin among the stored ones left."""
	cands = [_cand((2, 4), 0, 1.2, 10.0), _cand((4, 6), 0, 1.2, 12.0), _cand((4, 1), 0, 1.2, 18.0)]
	pr, ids = _build(tmp_path, cands={"G1": cands})
	assert GR.likely_place(pr, ids["G1"]) is None                  # 1.2 < 1.5
	pr.place(ids["W"], (4, 6), theta_deg=-PSI_W)                    # the alternative that set 1.2 is gone
	lp = GR.likely_place(pr, ids["G1"])
	assert lp["cell0"] == [2, 4] and lp["candidato"] == 1 and lp["margin"] == pytest.approx(1.8, abs=1e-3)
	# the stored margin set by an alternative that is not stored: it stands even with stored ones farther away
	cands = [_cand((2, 4), 0, 1.3, 10.0), _cand((4, 6), 0, 1.3, 20.0), _cand((4, 1), 0, 1.3, 25.0)]
	pr2, ids2 = _build(tmp_path / "b", cands={"G1": cands})
	assert GR.likely_place(pr2, ids2["G1"]) is None


# ---------------------------------------------------------------- the suspects did not change
def test_evaluate_is_grade_at_per_piece(tmp_path):
	"""``evaluate`` = ``grade_at`` on each placed piece at its cell (same grade, alternative and ``explicada``)."""
	pr, ids = _row_project(tmp_path, rot_b=90.0)
	pl = {}
	r = C.evaluate(pr, pl)
	mounted = {tuple(p.celula): pid for pid, p in pr.pieces.items() if p.estado == "colocada"}
	k_of = lambda q: int(pl[q]["corner"]["k"])                       # noqa: E731
	got = {pid: C.grade_at(pr, pid, cell, k_of(pid), mounted, k_of) for cell, pid in mounted.items()}
	reported = {it["piece"]: (it["grau"], it["k_alt"]) for it in r["items"]}
	assert reported == {pid: (g["grau"], g["k_alt"]) for pid, g in got.items() if g["grau"] and not g["explicada"]}
	assert r["summary"]["n_explicadas"] == sum(g["explicada"] for g in got.values()) == 1
	assert got[ids["A"]]["explicada"] and got[ids["B"]]["grau"] == "impossivel"
