"""Shared pytest configuration for the anti-regression suite.

Puts the repository root on ``sys.path`` so ``import src.<module>`` resolves no
matter how pytest is invoked (``python -m pytest`` already prepends the CWD, but
this keeps a plain ``pytest`` working too). Also exposes ``REPO_ROOT`` for tests
that need to locate example data on disk.
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


import weakref  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _stop_test_guis(monkeypatch):
    """Stop (``Gui.stop()``) every ``src.server.Gui`` a test creates, at the end of that test.

    The import-queue worker (``queue=True`` by default) is a thread per ``Gui``; without ``stop()`` the suite kept
    ~116 ``fila-importacao`` threads alive and timing-sensitive tests competed with them (2026-11-15, P0 of the
    performance phase, approved by Tiago as the way for the fixtures to call ``gui.stop()``). One autouse fixture
    instead of editing every fixture: it wraps ``Gui.__init__`` for the duration of the test and keeps weak
    references. Guis of module/session-scoped fixtures are created before this function-scoped fixture is active,
    so they are not stopped between tests."""
    try:
        from src import server as SV
    except Exception:  # noqa: BLE001 - server deps missing: those tests are skipped anyway
        yield
        return
    made = []
    orig = SV.Gui.__init__

    def init(self, *a, **k):
        made.append(weakref.ref(self))
        orig(self, *a, **k)
    monkeypatch.setattr(SV.Gui, "__init__", init)
    yield
    for ref in made:
        g = ref()
        if g is not None:
            try:
                g.stop(timeout=5)
            except Exception:  # noqa: BLE001 - a half-built Gui (its __init__ raised)
                pass
