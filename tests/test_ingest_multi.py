"""Several sheets of one bag (:func:`src.ingest.ingest_sheets`), idempotent re-import by sha256, the scale and
background warnings, and :func:`src.ingest.segment_sheet` writing nothing (synthetic scans with tabbed pieces)."""

import os

import cv2
import numpy as np
import pytest
from PIL import Image

import synth
from src import ingest as I
from src.profile import PuzzleProfile
from src.sheets import expand_sources
from src.state import Project, replay
from test_shape import MMPP

BG = (40, 160, 60)
KINDS = ["TBTB", "BTBT", "TTBB", "BBTT", "TBBT", "BTTB"]


def _bg_lab(rgb):
	return [round(float(v), 1) for v in cv2.cvtColor(np.array([[rgb]], np.float32) / 255.0, cv2.COLOR_RGB2LAB)[0, 0]]


def _profile_path(tmp_path):
	pp = tmp_path / "puzzle.json"
	PuzzleProfile(id="t", grid={"cols": 6, "rows": 4}, cell_mm={"w": synth.PITCH_MM, "h": synth.PITCH_MM},
				  symmetry={"type": "rot180"}, background_lab=_bg_lab(BG), dpi=300).save(str(pp))
	return str(pp)


def _scan(path, n, *, scale=1.0, bg=BG, seed=0):
	"""``n`` tabbed pieces (``synth.body_mm``) in a row, drawn at ``scale`` x their real size at 300 dpi."""
	rng = np.random.default_rng(seed)
	w = 240 + int(n * 420 * scale)
	img = np.full((int(600 * max(scale, 0.6)), w, 3), bg, np.uint8)
	for i in range(n):
		# every piece its own cut (knob position / radius): no two identical shapes across sheets (an exact twin gives an
		# infinite margin, which /api/fetch would send as the non-JSON token Infinity)
		cut = dict(deltas=tuple(rng.uniform(-1.0, 1.0, 4)), radii=tuple(rng.uniform(2.6, 3.4, 4)))
		pts = synth.body_mm(KINDS[i % len(KINDS)], **cut) * scale / MMPP
		pts = pts + np.array([220 + i * 420 * scale, img.shape[0] / 2])
		col = tuple(int(x) for x in rng.integers(150, 230, 3)) if bg == BG else (180, 30, 30)   # seed -> other bytes
		cv2.fillPoly(img, [np.round(pts).astype(np.int32).reshape(-1, 1, 2)], col)
	Image.fromarray(img).save(path)
	return str(path)


@pytest.fixture
def proj(tmp_path):
	return Project.create(str(tmp_path / "proj"), _profile_path(tmp_path))


def _ok(pr):
	q = Project.open(pr.path)
	assert q.check_invariants(disk=True) == []
	rb, _ = replay(q.log_path, q.profile)
	assert rb == q.board
	return q


def test_three_sheets_continue_numbering_and_reimport_is_ignored(tmp_path, proj):
	files = [_scan(tmp_path / f"s{k}.png", n, seed=k) for k, n in enumerate((3, 2, 4))]
	sheets = expand_sources(files)
	calls = []
	res = I.ingest_sheets(proj, sheets, 9, progress=lambda k, n, sh, r: calls.append((k, n, r["estado"])))
	assert [r["estado"] for r in res] == ["ok", "ok", "ok"] and calls == [(1, 3, "ok"), (2, 3, "ok"), (3, 3, "ok")]
	nums = [sorted(r["numbers"].values()) for r in res]
	assert nums == [[1, 2, 3], [4, 5], [6, 7, 8, 9]]
	assert all(r["dpi"] == 300 for r in res)                  # PNG without density: the default
	pr = _ok(proj)
	assert sorted(p.n_no_lote for p in pr.pieces.values() if p.lote == 9) == list(range(1, 10))
	n_log = sum(1 for _ in open(pr.log_path, encoding="utf-8"))
	# the same sheets again (and one of them twice in the same call): all ignored, nothing logged
	again = I.ingest_sheets(pr, expand_sources(files + files[:1]), 9)
	assert [r["estado"] for r in again] == ["ignorada"] * 4
	assert [r["scan_id"] for r in again] == ["S0001", "S0002", "S0003", "S0001"]
	assert "já importada como S0002 (lote 9)" in again[1]["motivo"]
	assert sum(1 for _ in open(pr.log_path, encoding="utf-8")) == n_log
	pr = _ok(pr)
	assert len(pr.model.scans) == 3 and len(pr.pieces) == 9
	# the scan metadata keeps the checks: scale close to nominal, background close to the profile
	m = pr.model.scans["S0001"]["meta"]
	assert m["escala"]["aviso"] is None and 0.95 <= m["escala"]["razao"] <= 1.05 and m["escala"]["lados"] == "não-F"
	assert m["fundo"]["aviso"] is None and m["fundo"]["dE"] < 5
	assert m["fonte"]["origem"].endswith("s0.png") and m["fonte"]["dpi"] == 300


def test_state_add_scan_unique_refuses_a_known_file(tmp_path, proj):
	from src.state import StateError
	f = _scan(tmp_path / "a.png", 1)
	sid = proj.add_scan(f, lote=1, unique=True)
	n = proj.meta["next_ids"]["S"]
	with pytest.raises(StateError, match=f"já importada como {sid}"):
		proj.add_scan(f, lote=2, unique=True)
	assert proj.meta["next_ids"]["S"] == n                    # no id consumed
	assert proj.add_scan(f, lote=2) != sid                     # the default keeps the old behaviour


def test_scale_warning_when_the_pieces_are_smaller(tmp_path, proj):
	f = _scan(tmp_path / "small.png", 4, scale=0.8)
	r = I.ingest_sheets(proj, expand_sources([f]), 1)[0]
	assert r["estado"] == "ok" and len(r["pieces"]) == 4
	esc = r["escala"]
	assert esc["razao"] == pytest.approx(0.8, abs=0.04) and esc["dpi_compativel"] == pytest.approx(240, abs=12)
	assert esc["aviso"] and "escala: corda mediana" in esc["aviso"] and "dpi compatível" in esc["aviso"]
	assert any(a.startswith("escala:") for a in r["avisos"])
	assert _ok(proj).model.scans[r["scan_id"]]["meta"]["escala"]["aviso"] == esc["aviso"]


def test_half_scale_scan_warns_even_when_every_piece_is_a_fragment(tmp_path, proj):
	f = _scan(tmp_path / "half.png", 4, scale=0.5)
	r = I.ingest_sheets(proj, expand_sources([f]), 1)[0]
	assert r["estado"] == "ok" and r["pieces"] == [] and len(r["rejected"]) == 4
	assert any("abaixo de" in a and "dpi" in a for a in r["avisos"]), r["avisos"]


def test_background_warning_on_white_paper(tmp_path, proj):
	f = _scan(tmp_path / "white.png", 3, bg=(245, 245, 245))
	res = I.segment_sheet(f, dpi=300, project=proj)
	assert res.error is None, res.error
	assert res.fundo["dE"] > 15 and res.fundo["aviso"].startswith("fundo: ΔE")
	r = I.commit_sheet(proj, res, 2)
	assert any(a.startswith("fundo:") for a in r["avisos"])


def test_segment_sheet_writes_nothing(tmp_path, proj):
	f = _scan(tmp_path / "x.png", 2)
	before = {fn: os.path.getmtime(os.path.join(dp, fn)) for dp, _, fns in os.walk(proj.path) for fn in fns}
	log0 = open(proj.log_path, encoding="utf-8").read()
	res = I.segment_sheet(f, dpi=300, project=proj)
	assert res.error is None and len(res.pieces) == 2 and res.sha256 and res.skipped is None
	after = {fn: os.path.getmtime(os.path.join(dp, fn)) for dp, _, fns in os.walk(proj.path) for fn in fns}
	assert after == before and open(proj.log_path, encoding="utf-8").read() == log0
	assert proj.meta["next_ids"].get("S", 1) == 1 and not proj.pieces
	r = I.commit_sheet(proj, res, 4)
	assert r["scan_id"] == "S0001" and sorted(r["numbers"].values()) == [1, 2]
	# a second segment_sheet of the same file is not segmented at all (the sha256 is known)
	res2 = I.segment_sheet(f, dpi=300, project=proj, segment=lambda *a, **k: pytest.fail("segmentou"))
	assert res2.skipped == "S0001"
	assert I.commit_sheet(proj, res2, 4)["skipped"] is True
