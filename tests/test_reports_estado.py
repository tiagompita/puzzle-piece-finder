"""Report states as events (``src.reports.set_state``): every change appends exactly ONE line to
``reports.jsonl`` and ONE event to ``log.jsonl``; nothing is ever rewritten; deleted reports are hidden by
default and restore to their previous state; the log replays."""

import json

import pytest

from test_query import _project

from src import reports
from src.state import Project


def _raw(pr):
    with open(reports.reports_path(pr), "rb") as f:
        return f.read()


def _nlog(pr):
    with open(pr.log_path, encoding="utf-8") as f:
        return len(f.read().splitlines())


@pytest.fixture
def pr(tmp_path):
    p, placed, tw, dec = _project(tmp_path)
    reports.add_report(p, tipo="mal_lida", texto="um", piece=placed, cell=(2, 3))
    reports.add_report(p, tipo="outro", texto="dois", cell=(1, 1))
    return p


def _step(pr, rid, acao, nota=""):
    before, nl = _raw(pr), _nlog(pr)
    n_lines = len(before.splitlines())
    r = reports.set_state(pr, rid, acao, nota)
    after = _raw(pr)
    if "error" in r:
        assert after == before and _nlog(pr) == nl            # a refused transition writes nothing
        return r
    assert after.startswith(before) and len(after.splitlines()) == n_lines + 1
    assert _nlog(pr) == nl + 1
    return r


def test_valid_transitions_and_fold(pr):
    r = _step(pr, "R0001", "close", "feito")
    assert r["estado"] == "fechado" and r["nota"] == "feito" and r["fechado_em"] and r["n_estados"] == 1
    r = _step(pr, "R0001", "reopen")
    assert r["estado"] == "aberto" and r["reaberto_em"] and r["n_estados"] == 2
    r = _step(pr, "R0001", "delete")
    assert r["estado"] == "eliminado" and r["estado_anterior"] == "aberto" and r["eliminado_em"]
    r = _step(pr, "R0001", "restore")
    assert r["estado"] == "aberto" and r["restaurado_em"] and r["n_estados"] == 4
    assert [h["estado"] for h in r["historico"]] == ["fechado", "aberto", "eliminado", "aberto"]
    acts = [e["action"] for e in pr.events()]
    for a in ("report_closed", "report_reopened", "report_deleted", "report_restored"):
        assert a in acts
    ev = json.loads(_raw(pr).splitlines()[-1])
    assert ev["evento"] == "estado" and ev["id"] == "R0001" and ev["estado"] == "aberto" and ev["acao"] == "restore"


def test_invalid_transitions(pr):
    assert "error" in _step(pr, "R0001", "reopen")                                  # open: nothing to reopen
    assert "error" in _step(pr, "R0001", "restore")
    _step(pr, "R0001", "close")
    assert "R0001 já está fechado" in _step(pr, "R0001", "close")["error"]
    assert "error" in _step(pr, "R0001", "restore")
    _step(pr, "R0001", "delete")
    for acao in ("close", "reopen", "delete"):
        assert "error" in _step(pr, "R0001", acao), acao
    assert "desconhecido" in _step(pr, "R0099", "close")["error"]
    assert "ação desconhecida" in _step(pr, "R0001", "explodir")["error"]
    assert "error" in reports.edit_report(pr, "R0001", texto="x")                 # deleted: no edits


def test_deleted_hidden_by_default_and_restore_to_closed(pr):
    _step(pr, "R0001", "close", "ok")
    _step(pr, "R0001", "delete")
    _step(pr, "R0002", "delete")
    assert reports.list_reports(pr) == []
    assert reports.list_reports(pr, only_open=False) == []
    assert [r["id"] for r in reports.list_reports(pr, eliminados=True)] == ["R0001", "R0002"]
    r = _step(pr, "R0001", "restore")
    assert r["estado"] == "fechado" and r["nota"] == "ok"                           # back to the previous state
    assert [r["id"] for r in reports.list_reports(pr, only_open=False)] == ["R0001"]
    assert reports.list_reports(pr) == []
    assert reports.next_report_id(reports.read_reports(pr)) == "R0003"            # state lines are not reports


def test_legacy_rewritten_closed_line_still_valid(pr):
    """The old format (a line rewritten with ``estado: fechado``) folds and can be reopened without conversion."""
    rows = [json.loads(x) for x in _raw(pr).decode("utf-8").splitlines()]
    rows[0].update(estado="fechado", fechado_em="2026-11-01T10:00:00", nota="antigo")
    with open(reports.reports_path(pr), "w", encoding="utf-8", newline="\n") as f:
        for x in rows:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    cur = reports.read_reports(pr)[0]
    assert cur["estado"] == "fechado" and cur["nota"] == "antigo"
    r = _step(pr, "R0001", "reopen")
    assert r["estado"] == "aberto"
    assert [h["estado"] for h in r["historico"]] == ["fechado", "aberto"]       # the old closing is kept in the history


def test_edit_events_and_states_combine_and_replay(pr):
    reports.edit_report(pr, "R0001", texto="novo")
    _step(pr, "R0001", "close")
    _step(pr, "R0001", "delete")
    _step(pr, "R0001", "restore")
    r = reports.read_reports(pr)[0]
    assert r["texto"] == "novo" and r["n_edicoes"] == 1 and r["estado"] == "fechado"
    pr2 = Project.open(pr.path)                                                    # replay of the whole log
    assert pr2.check_invariants(disk=True) == []
    assert reports.read_reports(pr2)[0]["estado"] == "fechado"
    assert reports.close_report(pr2, "R0002", "x")["estado"] == "fechado"           # compat wrapper
