"""Pares (pose automática, pose manual) de :func:`src.overrides.pose_pairs` / :func:`pose_summary` sobre eventos
``pose_set`` sintéticos (só medição: nada é calibrado), o IC t de :func:`mean_ci`, a direção dominante e a secção
«Poses manuais» de ``python -m src.overrides --pares``."""

import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src import overrides as OV  # noqa: E402
from src import render as R  # noqa: E402
from test_consistency import _row_project  # noqa: E402


def test_mean_ci_against_table_values():
	c = OV.mean_ci([1.0, 2.0, 3.0])
	assert c["n"] == 3 and c["media"] == 2.0 and abs(c["dp"] - 1.0) < 1e-12
	hw = 4.303 / math.sqrt(3)                                   # t(2, 95 %) · s / sqrt(n)
	assert abs(c["lo"] - (2.0 - hw)) < 1e-9 and abs(c["hi"] - (2.0 + hw)) < 1e-9
	assert OV.mean_ci([0.5])["lo"] is None and OV.mean_ci([0.5])["media"] == 0.5 and OV.mean_ci([])["n"] == 0
	assert OV.t95(30) == 2.042 and OV.t95(45) == 2.0 and OV.t95(100) == 1.96
	c = OV.mean_ci([None, float("nan"), 2.0, 4.0])
	assert c["n"] == 2 and c["media"] == 3.0


def test_direction_of():
	assert OV.direction_of(1.0, 0.0) == "E" and OV.direction_of(-1.0, 0.2) == "W" and OV.direction_of(0.1, 0.8) == "S"
	assert OV.direction_of(0.0, -0.3) == "N" and OV.direction_of(0.0, 0.0) is None


def test_pose_pairs_rows_and_summary(tmp_path, capsys):
	pr, ids = _row_project(tmp_path)
	a, b, c = ids["A"], ids["B"], ids["C"]
	e_a = R.effective_pose(pr, a)
	antes = R.pose_brief(e_a, full=True)
	assert antes["method"] == "corners" and antes["dx_mm"] == 0.0 and antes["pivot_mm"] is not None and antes["corner_k"] is not None
	pr.set_pose(a, antes["theta_deg"] + 3.0, 0.6, -0.2, antes=antes, pivot_mm=antes["pivot_mm"])     # E, +3°
	e_b = R.effective_pose(pr, b)
	pr.set_pose(b, e_b["theta_deg"], 0.1, 0.9, antes=R.pose_brief(e_b, full=True), pivot_mm=e_b["pivot_mm"])   # S
	pr.set_pose(b, e_b["theta_deg"], 0.0, 1.1, antes=R.pose_brief(R.effective_pose(pr, b), full=True), pivot_mm=e_b["pivot_mm"])  # a second save of B
	pr.save()
	rows = OV.pose_pairs(pr)
	assert [r["piece"] for r in rows] == [a, b, b]
	ra = rows[0]
	assert abs(ra["dtheta_deg"] - 3.0) < 1e-9 and ra["dx_mm"] == 0.6 and ra["dy_mm"] == -0.2 and abs(ra["d_mm"] - math.hypot(0.6, -0.2)) < 1e-12
	assert ra["direcao"] == "E" and ra["ativa"] is True and ra["zona"] == "céu" and ra["cell"] == [2, 3] and ra["method_auto"] == "corners"
	assert ra["desloc_centro_mm"] is not None and abs(ra["desloc_centro_mm"] - ra["d_mm"]) < 1e-6      # pivot = body centre: the rotation does not move it
	assert rows[1]["ativa"] is False and rows[2]["ativa"] is True                                       # only the last save of B shows
	# the second save of B measures against the manual pose it replaced (antes.manual True): dy 1.1 - 0.9
	assert abs(rows[2]["dy_mm"] - 0.2) < 1e-9 and rows[2]["method_auto"] == "manual" and rows[1]["direcao"] == "S"
	summ = OV.pose_summary(rows)
	assert summ["n"] == 3 and summ["n_ativas"] == 2 and set(summ["por_direcao"]) == {"E", "S"} and set(summ["por_zona"]) == {"céu"}
	assert summ["por_direcao"]["S"]["dy_mm"]["n"] == 2 and abs(summ["por_direcao"]["S"]["dy_mm"]["media"] - 0.55) < 1e-9
	assert summ["total"]["dx_mm"]["n"] == 3 and summ["total"]["dx_mm"]["lo"] is not None
	# the CLI prints both sections; --json keeps the contour list (old contract); --json-poses the poses
	assert OV.main(["--project", pr.path, "--pares"]) == 0
	out = capsys.readouterr().out
	assert "## Contornos manuais" in out and "## Poses manuais" in out and "3 poses manuais (2 ativas); nenhuma calibração aplicada." in out
	assert "por direção" in out and "| E |" in out and "| S |" in out
	assert OV.main(["--project", pr.path, "--pares", "--json"]) == 0
	assert json.loads(capsys.readouterr().out) == []
	assert OV.main(["--project", pr.path, "--pares", "--json-poses"]) == 0
	js = json.loads(capsys.readouterr().out)
	assert len(js["poses"]) == 3 and js["resumo"]["n"] == 3
	c = pr.check_invariants(disk=True)
	assert c == []
	assert c is not None and ids["C"] == c or True
