"""GUI: «Guardadas» (peças sem vizinha ortogonal montada, fora de «Vai buscar») (slow).

* Projeto sintético: a única proposta não tem vizinha montada -> «Vai buscar» vazio, «Guardadas» com o cartão,
  recolhido por omissão e com o aviso «Não procurar ainda».
* Projeto real (cópia com o log cortado, como ``test_fetch_group_real``): as células de R0013-R0017 e as
  outras que o Tiago viu em «Vai buscar» ((3, 55), (3, 59)) não estão em «Vai buscar»; estão em «Guardadas».
"""

import json
import os
import shutil
import socket
import threading
import time

import pytest

pytestmark = pytest.mark.slow
pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("uvicorn")
sync_api = pytest.importorskip("playwright.sync_api")

from src import server as S  # noqa: E402
from test_query import _project  # noqa: E402

ALPES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "projects", "alpes")
LOG_EVENTS = 2045                  # log.jsonl no commit bc6b772 (o mesmo estado de test_fetch_group_real)
TIAGO_CELLS = {(4, 43), (4, 49), (4, 50), (4, 53), (3, 54), (3, 55), (3, 59)}


def _serve(path, uploads):
    import uvicorn
    gui = S.Gui(path, prepare=False, use_image=False, uploads=uploads, log=None)
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    server = uvicorn.Server(uvicorn.Config(S.create_app(gui), host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    t0 = time.time()
    while not server.started and time.time() - t0 < 30:
        time.sleep(0.05)
    return gui, server, th, f"http://127.0.0.1:{port}"


def _page(pw):
    try:
        br = pw.chromium.launch()
    except Exception as e:  # chromium not installed
        pytest.skip(f"chromium indisponível: {e}")
    return br, br.new_page(viewport={"width": 1400, "height": 900})


@pytest.fixture(scope="module")
def synth(tmp_path_factory):
    from src.query import run_query
    tmp = tmp_path_factory.mktemp("synth")
    pr, placed, tw, dec = _project(tmp)
    run_query(pr, use_image=False)
    gui, server, th, base = _serve(pr.path, str(tmp / "uploads"))
    yield base, gui
    server.should_exit = True
    th.join(10)


def test_vai_buscar_empty_and_guardadas_collapsed(synth):
    base, _ = synth
    with sync_api.sync_playwright() as pw:
        br, pg = _page(pw)
        pg.goto(base + "/")
        pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
        pg.wait_for_selector("#tab-buscar .empty", timeout=30_000)
        assert pg.locator("#tab-buscar .card").count() == 0
        assert pg.inner_text("#n-guardadas") == "1"
        pg.evaluate("showTab('guardadas')")
        assert "Não procurar ainda" in pg.inner_text("#tab-guardadas .aviso-box")
        assert pg.evaluate("document.querySelector('#tab-guardadas details.guardadas').open") is False
        assert pg.locator("#tab-guardadas details.guardadas .card").count() == 1
        br.close()


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    if not os.path.exists(os.path.join(ALPES, "log.jsonl")) or not os.path.exists(os.path.join(ALPES, "fetch.json")):
        pytest.skip("projects/alpes não está presente")
    with open(os.path.join(ALPES, "log.jsonl"), encoding="utf-8") as f:
        lines = f.readlines()
    if len(lines) < LOG_EVENTS:
        pytest.skip("log.jsonl mais curto do que o estado fixado")
    d = tmp_path_factory.mktemp("alpes_real")
    for name in ("project.json", "puzzle.json", "fetch.json"):
        shutil.copy(os.path.join(ALPES, name), d / name)
    if os.path.isdir(os.path.join(ALPES, "photos")):
        shutil.copytree(os.path.join(ALPES, "photos"), d / "photos")
    with open(d / "log.jsonl", "w", encoding="utf-8") as f:
        f.writelines(lines[:LOG_EVENTS])
    gui, server, th, base = _serve(str(d), str(d / "uploads"))
    yield base, gui
    server.should_exit = True
    th.join(10)


def test_real_board_cells_without_orthogonal_neighbour_are_not_in_vai_buscar(real):
    base, gui = real
    with sync_api.sync_playwright() as pw:
        br, pg = _page(pw)
        pg.goto(base + "/")
        pg.wait_for_selector("body[data-ready='1']", timeout=120_000)
        pg.wait_for_selector("#tab-guardadas .aviso-box", state="attached", timeout=60_000)
        entries = pg.evaluate("fetch('/api/fetch').then((r) => r.json())")["entries"]
        shown = {tuple(e["cell"]) for e in entries if e.get("piece") and e.get("cell") and e.get("grupo") == "coloca_agora"}
        stored = {tuple(e["cell"]) for e in entries if e.get("piece") and e.get("cell") and e.get("grupo") == "guarda_posicao"}
        assert TIAGO_CELLS <= stored and not (TIAGO_CELLS & shown)
        # o que o separador mostra de facto
        buscar = pg.evaluate("Array.from(document.querySelectorAll('#tab-buscar .card')).map((c) => c.innerText)")
        guardadas = pg.evaluate("Array.from(document.querySelectorAll('#tab-guardadas .card')).map((c) => c.innerText)")
        for (l, c) in TIAGO_CELLS:
            assert not any(f"({l}, {c})" in t for t in buscar), (l, c)
            assert any(f"({l}, {c})" in t for t in guardadas), (l, c)
        # só aparece em «Vai buscar» o que tem vizinha ortogonal montada
        from src.query import mounted_neighbours
        for e in entries:
            if e.get("piece") and e.get("cell") and e.get("estado_atual") in ("solta", "emparelhada", "posicao_conhecida"):
                grupo = "coloca_agora" if mounted_neighbours(gui.pr, e["cell"]) >= 1 else "guarda_posicao"
                assert e["grupo"] == grupo
        assert pg.evaluate("document.querySelector('#tab-guardadas details.guardadas').open") is False
        br.close()
