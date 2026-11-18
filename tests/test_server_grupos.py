"""Tests for the loose groups in the server (F4, B2): ``/api/grupos*`` on a synthetic board.

The board (4 x 6 synthetic profile of ``tests/test_query.py``, pieces made by ``tests/synth.py``, kinds top, right,
bottom, left in the board pose):

* A ``TBTB`` placed at (2,3);
* G1 = one piece X ``BBBT``: at (2,4) rot 0 its W side (T) meets A's E side (B), so the neighbour confirms rot 0;
  at rot 90 / 180 it puts a B on A's B: the neighbour disagrees;
* G2 = Y ``BTTT`` at local (0,0) + Z ``TTTB`` at local (0,1): at (3,3) rot 0 Y sits under A (B under T) and Z has
  no neighbour outside the group;
* W ``TBTB`` loose (the «Encaixa» of the concurrency test).

The groups' pieces are scanned at the same angle (a legacy page), so their board pose comes from the section
rotation (``render.initial_theta``). Covers: ``GET /api/grupos`` (likely place only with margin >= ``margin_min``),
«Mostrar» / «Mover» without re-query and without ``board_changed`` (only ``grupos_changed``), criterion 11 byte for
byte after 10 «Mover», the PNG of the group and the count of the top.
"""

import os

import cv2
import numpy as np
import pytest
from PIL import Image

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

import synth  # noqa: E402
from src import mesa  # noqa: E402
from src import server as S  # noqa: E402
from src.shape import analyse  # noqa: E402
from src.state import Project, replay  # noqa: E402
from test_query import BG, _piece_px  # noqa: E402
from test_shape import MMPP  # noqa: E402

PSI_A, PSI_W, PSI_G = 23.0, 50.0, 12.0


def _board_project(tmp_path, cand1=None, cand2=None):
	"""``(project, ids)``; ``cand1`` / ``cand2``: candidate dicts of G1 / G2 (None = no candidate)."""
	prof = synth.profile(rows=4, cols=6, p90=None)
	pp = tmp_path / "puzzle.json"
	prof.save(str(pp))
	pr = Project.create(str(tmp_path / "proj"), str(pp))
	spec = [("A", "TBTB", PSI_A), ("W", "TBTB", PSI_W), ("X", "BBBT", PSI_G), ("Y", "BTTT", PSI_G), ("Z", "TTTB", PSI_G)]
	pts_all = [_piece_px(synth.body_mm(k, deltas=(0.3 * i, -0.2, 0.1, 0.2 * i)), psi, (400 + 600 * i, 400))
			   for i, (_, k, psi) in enumerate(spec)]
	img = np.full((800, 600 * len(spec) + 200, 3), BG, np.uint8)
	cols = [(200, 40, 40), (40, 60, 200), (210, 170, 30), (60, 200, 200), (170, 60, 190)]
	for pts, col in zip(pts_all, cols):
		cv2.fillPoly(img, [np.round(pts).astype(np.int32).reshape(-1, 1, 2)], col)
	scan = tmp_path / "scan.png"
	Image.fromarray(img).save(scan)
	sid = pr.add_scan(str(scan), dpi=300, lote=4)
	os.makedirs(pr.p("crops"), exist_ok=True)
	ids = {}
	for i, ((name, _, _), pts) in enumerate(zip(spec, pts_all)):
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
	ids["G1"] = pr.register_section(sid, "blocos", {ids["X"]: (0, 0)}, candidates=[cand1] if cand1 else [])
	ids["G2"] = pr.register_section(sid, "blocos", {ids["Y"]: (0, 0), ids["Z"]: (0, 1)}, candidates=[cand2] if cand2 else [])
	pr.save()
	return pr, ids


def _cand(cell0, rot=0, margin=2.0):
	return {"cell0": list(cell0), "rot": rot, "mirror": False, "score": 1.0, "margin": margin}


def _env(tmp_path, **kw):
	from src.query import run_query
	pr, ids = _board_project(tmp_path, **kw)
	run_query(pr, use_image=False)
	gui = S.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "uploads"), log=None)
	return gui, TestClient(S.create_app(gui)), ids


@pytest.fixture
def env(tmp_path):
	return _env(tmp_path, cand1=_cand((2, 4)), cand2=_cand((3, 3), margin=1.0))


def _ok_on_disk(path):
	pr = Project.open(path)
	assert pr.check_invariants(disk=True) == []
	rb, _ = replay(pr.log_path, pr.profile)
	assert rb == pr.board
	return pr


def _grupo(cl, gid):
	r = cl.get("/api/grupos")
	assert r.status_code == 200, r.text
	return next(g for g in r.json()["grupos"] if g["id"] == gid)


def _names(gui, seq0):
	return [n for _, n, _ in gui.events_after(seq0)]


# ---------------------------------------------------------------- GET
def test_get_lists_loose_groups_with_likely_place_only_with_margin(env):
	gui, cl, ids = env
	d = cl.get("/api/grupos").json()
	assert [g["id"] for g in d["grupos"]] == [ids["G1"], ids["G2"]]
	assert d["n_grupos"] == 2 and d["n_pecas"] == 3
	g1, g2 = d["grupos"]
	assert g1["n"] == 1 and g2["n"] == 2
	assert g1["mostrado"] is False and g1["posicao"] is None and g1["footprint"] is None and g1["sobreposto"] is None
	assert g1["lugar_provavel"]["cell0"] == [2, 4] and g1["lugar_provavel"]["footprint"] == [[2, 4]]
	assert g2["lugar_provavel"] is None                            # margin 1.0 < margin_min 1.5
	assert [p["id"] for p in g2["pecas"]] == sorted([ids["Y"], ids["Z"]])
	assert all(p["lote"] == 4 and p["n_no_lote"] for p in g2["pecas"])
	assert g2["imagem"]["url"].startswith(f"/api/grupos/{ids['G2']}.png")


# ---------------------------------------------------------------- mostrar / mover: no re-query, no board_changed
def test_mostrar_and_mover_no_requery_no_board_changed(env, monkeypatch):
	gui, cl, ids = env
	import src.query as Q
	calls = []
	monkeypatch.setattr(Q, "run_query", lambda *a, **k: calls.append(1) or [])
	seq0 = gui.seq
	r = cl.post(f"/api/grupos/{ids['G1']}/mostrar", json={"centro": [3.0, 3.0]})
	assert r.status_code == 200, r.text
	g = r.json()["grupo"]
	assert g["mostrado"] and g["posicao"]["l0"] == 2 and g["posicao"]["c0"] == 4 and g["posicao"]["origem"] == "mesa"
	r = cl.post(f"/api/grupos/{ids['G1']}/mover", json={"l0": 4, "c0": 6, "rot": 0})
	assert r.status_code == 200, r.text
	assert r.json()["grupo"]["footprint"] == [[4, 6]]
	names = _names(gui, seq0)
	assert names.count("grupos_changed") == 2
	assert "board_changed" not in names and "fetch_changed" not in names
	assert calls == []
	# an invalid move goes back with a phrase; nothing written
	n0 = sum(1 for _ in open(mesa.mesa_path(gui.pr), encoding="utf-8"))
	r = cl.post(f"/api/grupos/{ids['G1']}/mover", json={"l0": 2, "c0": 3, "rot": 0})
	assert r.status_code == 409 and r.json()["motivo"] == "colocada" and "já tem uma peça" in r.json()["error"]
	r = cl.post(f"/api/grupos/{ids['G1']}/mover", json={"l0": 5, "c0": 1, "rot": 0})
	assert r.status_code == 409 and r.json()["motivo"] == "fora_da_grelha"
	assert sum(1 for _ in open(mesa.mesa_path(gui.pr), encoding="utf-8")) == n0
	# a second «Mostrar» of a shown group writes nothing and answers where it is
	r = cl.post(f"/api/grupos/{ids['G1']}/mostrar", json={})
	assert r.status_code == 200 and r.json()["grupo"]["posicao"]["c0"] == 6
	assert sum(1 for _ in open(mesa.mesa_path(gui.pr), encoding="utf-8")) == n0


def test_mover_rodar_and_refusal_rotated(env):
	gui, cl, ids = env
	assert cl.post(f"/api/grupos/{ids['G2']}/mostrar", json={"centro": [4.0, 5.5]}).status_code == 200
	r = cl.post(f"/api/grupos/{ids['G2']}/mover", json={"l0": 4, "c0": 5, "rot": 0})
	assert r.status_code == 200, r.text
	# turning the 1 x 2 bar on the bottom row leaves the board: no sliding
	r = cl.post(f"/api/grupos/{ids['G2']}/mover", json={"rodar": 90})
	assert r.status_code == 409 and r.json()["error"] == "Não cabe aqui rodado: move primeiro."
	r = cl.post(f"/api/grupos/{ids['G2']}/mover", json={"l0": 3, "c0": 5, "rot": 0})
	assert r.status_code == 200
	r = cl.post(f"/api/grupos/{ids['G2']}/mover", json={"rodar": 90})
	assert r.status_code == 200, r.text
	g = r.json()["grupo"]
	assert g["posicao"]["rot"] == 90 and g["rodado"] is True
	assert sorted(map(tuple, g["footprint"])) in ([(3, 5), (4, 5)], [(3, 6), (4, 6)], [(2, 5), (3, 5)], [(2, 6), (3, 6)])


def test_mover_requires_a_shown_group(env):
	gui, cl, ids = env
	r = cl.post(f"/api/grupos/{ids['G1']}/mover", json={"l0": 4, "c0": 6, "rot": 0})
	assert r.status_code == 409 and r.json()["motivo"] == "nao_mostrado"
	assert cl.post("/api/grupos/G9999/mover", json={"l0": 1, "c0": 1, "rot": 0}).status_code == 404


# ---------------------------------------------------------------- criterion 11: byte for byte after 10 «Mover»
def test_criterion_11_ten_moves_change_no_byte(env):
	gui, cl, ids = env
	pl = gui.pr.p("render", "placements.json")
	cl.get("/api/board.jpg?ppc=60")                                 # the raster and the placements exist
	cl.post(f"/api/grupos/{ids['G2']}/mostrar", json={"centro": [4.0, 2.0]})

	def snap():
		with open(gui.pr.log_path, "rb") as f:
			log = f.read()
		with open(pl, "rb") if os.path.exists(pl) else open(os.devnull, "rb") as f:
			plb = f.read()
		return (log, gui.render_version(), cl.get("/api/board.jpg?ppc=60").content,
				cl.get("/api/board.jpg?ppc=100&region=1,1,4,6").content,
				cl.get("/api/board.jpg?ppc=120&region=2,2,3,4").content, plb)
	before = snap()
	moves = [(4, 1, 0), (4, 2, 0), (3, 1, 0), (4, 4, 0), (3, 4, 0), (3, 5, 0), (4, 5, 0), (4, 4, 0), (4, 1, 0), (3, 1, 0)]
	for l0, c0, rot in moves:
		r = cl.post(f"/api/grupos/{ids['G2']}/mover", json={"l0": l0, "c0": c0, "rot": rot})
		assert r.status_code == 200, (l0, c0, r.text)
	after = snap()
	for k, (a, b) in enumerate(zip(before, after)):
		assert a == b, f"item {k} mudou"


# ---------------------------------------------------------------- PNG
def test_group_png(env):
	gui, cl, ids = env
	r = cl.get(f"/api/grupos/{ids['G2']}.png?rot=0")
	assert r.status_code == 200 and r.headers["content-type"] == "image/png"
	im = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_UNCHANGED)
	assert im.ndim == 3 and im.shape[2] == 4
	info = _grupo(cl, ids["G2"])["imagem"]
	ppc, m = info["ppc"], info["margem"]
	prof = gui.pr.profile
	w = (2 + 2 * m) * ppc
	h = (1 + 2 * m) * ppc * prof.cell_mm["h"] / prof.cell_mm["w"]
	assert abs(im.shape[1] - w) <= 1 and abs(im.shape[0] - h) <= 1
	a = im[..., 3] > 127
	assert 0.25 < a.mean() < 0.9                                       # two pieces, transparent around them
	# both cells are covered (the two pieces, side by side)
	cx = [int((m + 0.5) * ppc), int((m + 1.5) * ppc)]
	cy = int((m + 0.5) * ppc * prof.cell_mm["h"] / prof.cell_mm["w"])
	assert a[cy, cx[0]] and a[cy, cx[1]]
	r90 = cl.get(f"/api/grupos/{ids['G2']}.png?rot=90")
	im90 = cv2.imdecode(np.frombuffer(r90.content, np.uint8), cv2.IMREAD_UNCHANGED)
	assert im90.shape[0] > im90.shape[1]                               # turned: one column, two rows
	assert cl.get(f"/api/grupos/{ids['G2']}.png?rot=0").content == r.content
	assert cl.get(f"/api/grupos/{ids['G2']}.png?rot=45").status_code == 400
	assert cl.get("/api/grupos/G9999.png").status_code == 404


# ---------------------------------------------------------------- montar
def test_montar_counts_pieces_in_loose_groups(env):
	gui, cl, ids = env
	m = cl.get("/api/montar").json()
	assert m["fora_da_fila"]["grupos_soltos"] == {"grupos": 2, "pecas": 3}


