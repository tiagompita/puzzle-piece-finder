"""«Coloca agora» rule on the REAL Alpes board (:func:`src.query.fetch_group` / ``mounted_neighbours``).

Rule (Tiago): a cell is ``coloca_agora`` only with >= 1 ORTHOGONAL neighbour holding a placed piece;
the frame (sides outside the grid) is not a neighbour; placed border pieces count; no exception for
``posicao_conhecida``. The project is opened with the real loader from a copy in ``tmp_path`` whose
``log.jsonl`` is cut at a fixed length (the log is append-only), so the board is pinned to the state
of the open reports R0013-R0017 and later placements by Tiago do not change the test. Nothing is
written to ``projects/alpes``.
"""

import os
import shutil

import pytest

from src.query import fetch_group, mounted_neighbours
from src.state import Project

ALPES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "projects", "alpes")
LOG_EVENTS = 2045                    # log.jsonl length at commit bc6b772 (board of R0013-R0017)
REPORT_CELLS = {"R0013": (4, 43), "R0014": (4, 49), "R0015": (4, 50), "R0016": (4, 53), "R0017": (3, 54)}


@pytest.fixture(scope="module")
def alpes(tmp_path_factory):
    if not os.path.exists(os.path.join(ALPES, "log.jsonl")):
        pytest.skip("projects/alpes não está presente")
    with open(os.path.join(ALPES, "log.jsonl"), encoding="utf-8") as f:
        lines = f.readlines()
    if len(lines) < LOG_EVENTS:
        pytest.skip("log.jsonl mais curto do que o estado fixado")
    d = tmp_path_factory.mktemp("alpes")
    for name in ("project.json", "puzzle.json"):
        shutil.copy(os.path.join(ALPES, name), d / name)
    if os.path.isdir(os.path.join(ALPES, "photos")):
        shutil.copytree(os.path.join(ALPES, "photos"), d / "photos")
    with open(d / "log.jsonl", "w", encoding="utf-8") as f:
        f.writelines(lines[:LOG_EVENTS])
    return Project.open(str(d))


def _e(cell, origin="gemeo", decision="aceite"):
    return {"origin": origin, "decision": decision, "cell": list(cell)}


@pytest.mark.parametrize("rid", sorted(REPORT_CELLS))
def test_report_cells_have_no_placed_orthogonal_neighbour(alpes, rid):
    """R0013-R0017: no placed orthogonal neighbour (only a diagonal one, or none) -> never «coloca agora»,
    whatever the origin of the entry (a stored position included)."""
    cell = REPORT_CELLS[rid]
    pr = alpes
    assert pr.board[cell]["estado"] == "vazia"
    assert all(not pr.board.occupied(nb) for nb in pr.board.neighbours(cell))
    assert mounted_neighbours(pr, cell) == 0
    assert fetch_group(pr, _e(cell)) == "guarda_posicao"
    assert fetch_group(pr, _e(cell, "posicao_conhecida", "colocavel")) == "guarda_posicao"


def test_known_position_without_neighbour_is_kept_aside(alpes):
    """P0099 (``posicao_conhecida`` at (5, 60), no occupied neighbour): no exception for its origin."""
    pr = alpes
    p = pr.piece("P0099")
    assert p.estado == "posicao_conhecida" and tuple(p.celula) == (5, 60)
    assert mounted_neighbours(pr, (5, 60)) == 0
    assert fetch_group(pr, _e((5, 60), "posicao_conhecida", "colocavel")) == "guarda_posicao"


def test_placed_border_piece_counts(alpes):
    """(2, 59): its only placed orthogonal neighbour is the border piece at (1, 59) -> «coloca agora»."""
    pr = alpes
    assert pr.profile.is_border(1, 59) and pr.board[(1, 59)]["estado"] == "colocada"
    assert [nb for nb in pr.board.neighbours((2, 59)) if pr.board.occupied(nb)] == [(1, 59)]
    assert mounted_neighbours(pr, (2, 59)) == 1
    assert fetch_group(pr, _e((2, 59))) == "coloca_agora"
    assert fetch_group(pr, _e((2, 59), "posicao_conhecida", "colocavel")) == "coloca_agora"


def test_frame_is_not_a_neighbour(alpes):
    """(1, 29), the missing border cell: the frame side counts for nothing, the two placed border
    neighbours (1, 28) / (1, 30) do; (2, 29) is empty."""
    pr = alpes
    assert pr.board[(1, 29)]["estado"] == "vazia" and pr.board[(2, 29)]["estado"] == "vazia"
    assert sorted(pr.board.neighbours((1, 29))) == [(1, 28), (1, 30), (2, 29)]
    assert mounted_neighbours(pr, (1, 29)) == 2
    assert fetch_group(pr, _e((1, 29), "borda", "candidata")) == "coloca_agora"
