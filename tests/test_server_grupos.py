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
byte after 10 «Mover», «Fixar» = anchor with ``fonte manual``, ``rot_fonte`` decided by the server from the
``rodado`` lines of ``mesa.jsonl`` (C1) and the neighbours' check piece by piece (C2), the 2 refusals of C3,
«Tirar o grupo inteiro do lugar» leaving the group where it was anchored (Q10 a), the PNG of the group, and a
«Encaixa» racing a «Mover» (20 runs).
"""

import os
import threading

import cv2
import numpy as np
import pytest
from PIL import Image

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

import synth  # noqa: E402
from src import consistency as C  # noqa: E402
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


# ---------------------------------------------------------------- fixar: rot_fonte (C1) x vizinhas (C2)
SCEN = {
	# name: (candidate of G1, «Rodar» deltas before «Fixar», rot_fonte, vizinhas, confianca)
	"sem_rodar_confirmam": (_cand((2, 4), 0), [], "programa", "confirmam", "confirmado"),
	"sem_rodar_discordam": (_cand((2, 4), 90), [], "programa", "discordam", "a_confirmar"),
	"sem_rodar_sem_vizinhas": (_cand((4, 1), 0), [], "programa", "sem_vizinhas", "a_confirmar"),
	"rodar_confirmam": (_cand((2, 4), 90), [-90], "tiago", "confirmam", "confirmado"),
	"rodar_discordam": (_cand((2, 4), 0), [90], "tiago", "discordam", "a_confirmar"),
	"rodar_sem_vizinhas": (_cand((4, 1), 0), [90], "tiago", "sem_vizinhas", "confirmado"),
}


def _no_board_wide_evaluate(monkeypatch):
	"""C2: ``consistency.evaluate`` never runs inside the check of «Fixar» (the background suspects pass that follows
	every write still may)."""
	from src import grupos as GR
	inside, seen = threading.local(), []
	orig_check, orig_eval = GR.rotation_check, C.evaluate

	def check(*a, **k):
		inside.on = True
		try:
			return orig_check(*a, **k)
		finally:
			inside.on = False

	def evaluate(*a, **k):
		if getattr(inside, "on", False):
			seen.append(1)
			raise AssertionError("consistency.evaluate dentro da verificação do «Fixar»")
		return orig_eval(*a, **k)
	monkeypatch.setattr(GR, "rotation_check", check)
	monkeypatch.setattr(C, "evaluate", evaluate)
	return seen


@pytest.mark.parametrize("name", list(SCEN))
def test_fixar_rot_fonte_and_neighbours(tmp_path, name, monkeypatch):
	cand, turns, rot_fonte, vizinhas, confianca = SCEN[name]
	gui, cl, ids = _env(tmp_path, cand1=cand)
	g1, x = ids["G1"], ids["X"]
	assert cl.post(f"/api/grupos/{g1}/mostrar", json={}).status_code == 200
	for t in turns:
		r = cl.post(f"/api/grupos/{g1}/mover", json={"rodar": t})
		assert r.status_code == 200, r.text
	_no_board_wide_evaluate(monkeypatch)
	seq0 = gui.seq
	r = cl.post(f"/api/grupos/{g1}/fixar", json={"rodado": False if turns else True})   # the browser has no say (C1)
	assert r.status_code == 200, r.text
	d = r.json()
	assert d["ok"] and d["rot_fonte"] == rot_fonte and d["vizinhas"] == vizinhas and d["confianca"] == confianca
	assert d["verificacao_s"] >= 0
	assert ("aviso" in d and "outra rotação" in d["aviso"]) == (vizinhas == "discordam")
	if vizinhas == "sem_vizinhas":
		assert d["vizinhas_pecas"] == {x: "sem_vizinhas"}
	else:
		assert d["vizinhas_pecas"] == {x: vizinhas}
	names = _names(gui, seq0)
	assert "grupos_changed" in names and "board_changed" in names
	pr = _ok_on_disk(gui.path)
	ev = [e for e in pr.events() if e["action"] == "section_anchored"][-1]
	a = ev["anchor"]
	assert a["fonte"] == "manual" and a["rot_fonte"] == rot_fonte and a["vizinhas"] == vizinhas
	assert a["confianca"] == confianca
	eff_cell = tuple(cand["cell0"])
	assert pr.piece(x).estado == "colocada" and tuple(pr.piece(x).celula) == eff_cell
	assert all(g["id"] != g1 for g in cl.get("/api/grupos").json()["grupos"])


def test_fixar_after_reload_keeps_rot_fonte_tiago(tmp_path):
	"""C1: «Rodar» → a new Gui on the same project (a page reload, a request with no state) → «Fixar»: tiago."""
	gui, cl, ids = _env(tmp_path, cand1=_cand((2, 4), 90))
	g1 = ids["G1"]
	cl.post(f"/api/grupos/{g1}/mostrar", json={})
	assert cl.post(f"/api/grupos/{g1}/mover", json={"rodar": -90}).status_code == 200
	gui.stop()
	gui2 = S.Gui(gui.path, prepare=False, use_image=False, uploads=str(tmp_path / "uploads"), log=None)
	cl2 = TestClient(S.create_app(gui2))
	assert _grupo(cl2, g1)["rodado"] is True
	d = cl2.post(f"/api/grupos/{g1}/fixar", json={}).json()
	assert d["rot_fonte"] == "tiago" and d["confianca"] == "confirmado"


def test_fixar_only_checks_pieces_with_an_outside_neighbour(tmp_path, monkeypatch):
	"""C2: G2 at (3,3): Y has A above it (outside the group); Z has no neighbour outside the group (Y is inside)."""
	gui, cl, ids = _env(tmp_path, cand2=_cand((3, 3), 0))
	checked = []
	orig = C._assignments

	def spy(project, pid, *a, **k):
		if k.get("cell") is not None:                                 # the check of «Fixar» (not the suspects pass)
			checked.append(pid)
		return orig(project, pid, *a, **k)
	monkeypatch.setattr(C, "_assignments", spy)
	cl.post(f"/api/grupos/{ids['G2']}/mostrar", json={})
	d = cl.post(f"/api/grupos/{ids['G2']}/fixar", json={}).json()
	assert checked == [ids["Y"]]
	assert d["vizinhas_pecas"] == {ids["Y"]: "confirmam", ids["Z"]: "sem_vizinhas"}
	assert d["vizinhas"] == "confirmam" and d["rot_fonte"] == "programa" and d["confianca"] == "confirmado"


# ---------------------------------------------------------------- C3: refusals
def test_fixar_refuses_a_group_not_shown(env):
	gui, cl, ids = env
	n0 = len(gui.pr.events())
	r = cl.post(f"/api/grupos/{ids['G1']}/fixar", json={})
	assert r.status_code == 409 and r.json()["motivo"] == "nao_mostrado" and r.json()["error"]
	assert len(Project.open(gui.path).events()) == n0


def test_fixar_refuses_a_group_sobreposto(env):
	gui, cl, ids = env
	g1 = ids["G1"]
	cl.post(f"/api/grupos/{g1}/mostrar", json={})                     # candidate (2,4)
	r = cl.post("/api/confirm", json={"acao": "place", "piece": ids["W"], "cell": [2, 4], "theta_deg": -PSI_W,
									  "origin": "manual"})
	assert r.status_code == 200, r.text
	g = _grupo(cl, g1)
	assert g["sobreposto"]["motivo"] == "colocada" and g["sobreposto"]["celula"] == [2, 4]
	n0 = len(Project.open(gui.path).events())
	r = cl.post(f"/api/grupos/{g1}/fixar", json={})
	assert r.status_code == 409 and r.json()["motivo"] == "sobreposto" and r.json()["error"]
	assert len(Project.open(gui.path).events()) == n0


# ---------------------------------------------------------------- soltar (Q10 a)
def test_soltar_leaves_the_group_where_it_was_anchored(env):
	gui, cl, ids = env
	g1 = ids["G1"]
	cl.post(f"/api/grupos/{g1}/mostrar", json={})
	cl.post(f"/api/grupos/{g1}/mover", json={"l0": 4, "c0": 4, "rot": 0})
	assert cl.post(f"/api/grupos/{g1}/fixar", json={}).status_code == 200
	seq0 = gui.seq
	r = cl.post("/api/confirm", json={"acao": "unanchor", "section": g1})
	assert r.status_code == 200, r.text
	assert "grupos_changed" in _names(gui, seq0)
	g = _grupo(cl, g1)
	assert g["mostrado"] and g["posicao"]["origem"] == "fixacao" and g["footprint"] == [[4, 4]]
	assert g["rodado"] is False
	_ok_on_disk(gui.path)


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


# ---------------------------------------------------------------- concurrency
def test_encaixa_racing_mover_never_leaves_a_group_over_a_placed_piece_unmarked(env):
	gui, cl, ids = env
	g1, w = ids["G1"], ids["W"]
	cl.post(f"/api/grupos/{g1}/mostrar", json={})
	assert cl.post(f"/api/grupos/{g1}/mover", json={"l0": 1, "c0": 1, "rot": 0}).status_code == 200
	outcomes = set()
	for run in range(20):
		res = {}
		go = threading.Barrier(2)

		def place():
			go.wait()
			res["place"] = cl.post("/api/confirm", json={"acao": "place", "piece": w, "cell": [4, 6],
														 "theta_deg": -PSI_W, "origin": "manual"})

		def move():
			go.wait()
			res["move"] = cl.post(f"/api/grupos/{g1}/mover", json={"l0": 4, "c0": 6, "rot": 0})
		ts = [threading.Thread(target=place), threading.Thread(target=move)]
		for t in ts:
			t.start()
		for t in ts:
			t.join(60)
		assert res["place"].status_code == 200, res["place"].text
		g = _grupo(cl, g1)
		pr = Project.open(gui.path)
		over = [c for c in g["footprint"] if pr.board[tuple(c)]["estado"] == "colocada"]
		if over:
			assert g["sobreposto"] and g["sobreposto"]["motivo"] == "colocada"
		if res["move"].status_code == 200:
			# the move was validated before the placement: its line predates the «place» event
			line = res["move"].json()["linha"]
			k = max(i for i, e in enumerate(pr.events()) if e["action"] == "placed" and e["piece"] == w)
			assert line["log_n"] <= k
			outcomes.add("mover_primeiro")
		else:
			assert res["move"].status_code == 409 and res["move"].json()["motivo"] == "colocada"
			outcomes.add("encaixa_primeiro")
		# reset: W loose again, G1 back to (1,1)
		assert cl.post("/api/confirm", json={"acao": "unplace", "piece": w}).status_code == 200
		assert cl.post(f"/api/grupos/{g1}/mover", json={"l0": 1, "c0": 1, "rot": 0}).status_code == 200
	_ok_on_disk(gui.path)
	assert outcomes


def test_only_rodar_marks_rodado(env):
	"""C1: a «Mover» that carries another rotation (e.g. to the likely place) is not a «Rodar»."""
	gui, cl, ids = env
	g1 = ids["G1"]
	cl.post(f"/api/grupos/{g1}/mostrar", json={})
	r = cl.post(f"/api/grupos/{g1}/mover", json={"l0": 4, "c0": 6, "rot": 180})
	assert r.status_code == 200 and r.json()["grupo"]["posicao"]["rot"] == 180
	assert r.json()["grupo"]["rodado"] is False and "rodado" not in r.json()["linha"]
	r = cl.post(f"/api/grupos/{g1}/mover", json={"rodar": 90})
	assert r.json()["grupo"]["rodado"] is True and r.json()["linha"]["rodado"] is True
