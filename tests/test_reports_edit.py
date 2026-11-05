"""Editing a report (``src.reports.edit_report``): ``reports.jsonl`` stays append-only (an edit is an event line,
the original line is never rewritten), reading folds the edits, closing keeps them, the log gets an
informative ``report_edited`` event and replays."""

import json

from test_query import _project

from src import reports
from src.state import Project


def _lines(pr):
    with open(reports.reports_path(pr), encoding="utf-8", newline="") as f:
        return f.read().splitlines()


def test_edit_appends_event_and_folds(tmp_path):
    pr, placed, tw, dec = _project(tmp_path)
    r1 = reports.add_report(pr, tipo="mal_lida", texto="recorte", piece=placed, cell=(2, 3), vista="celula")
    reports.add_report(pr, tipo="outro", texto="outro", cell=(1, 1))
    before = _lines(pr)
    e = reports.edit_report(pr, r1["id"], tipo="mal_colocada", texto="afinal está mal colocada")
    assert "error" not in e and e["tipo"] == "mal_colocada" and e["texto"] == "afinal está mal colocada"
    assert e["estado"] == "aberto" and e["n_edicoes"] == 1 and e["editado_em"]
    after = _lines(pr)
    assert after[:len(before)] == before and len(after) == len(before) + 1      # append-only, byte for byte
    ev = json.loads(after[-1])
    assert ev["evento"] == "edicao" and ev["id"] == r1["id"] and ev["tipo"] == "mal_colocada"
    rows = reports.read_reports(pr)
    assert [r["id"] for r in rows] == ["R0001", "R0002"]                          # the event is not a report
    assert reports.next_report_id(rows) == "R0003"
    assert "report_edited" in [x["action"] for x in pr.events()]
    # a second edit of only the text keeps the type
    e2 = reports.edit_report(pr, r1["id"], texto="mais um pormenor")
    assert e2["tipo"] == "mal_colocada" and e2["texto"] == "mais um pormenor" and e2["n_edicoes"] == 2
    pr2 = Project.open(pr.path)                                                    # replay with the new event
    assert reports.read_reports(pr2)[0]["texto"] == "mais um pormenor"


def test_edit_errors_and_close_keeps_events(tmp_path):
    pr, placed, tw, dec = _project(tmp_path)
    r1 = reports.add_report(pr, tipo="outro", texto="a", piece=placed)
    assert "error" in reports.edit_report(pr, "R0099", texto="x")
    assert "error" in reports.edit_report(pr, r1["id"], tipo="xx")
    assert "error" in reports.edit_report(pr, r1["id"])
    reports.edit_report(pr, r1["id"], texto="b")
    n = len(_lines(pr))
    c = reports.close_report(pr, r1["id"], "feito")
    assert c["estado"] == "fechado" and c["texto"] == "b" and c["n_edicoes"] == 1
    assert len(_lines(pr)) == n                                                    # the edit event survived the rewrite
    assert any(json.loads(x).get("evento") == "edicao" for x in _lines(pr))
    assert "error" in reports.edit_report(pr, r1["id"], texto="c")                # closed: no edits
    assert reports.list_reports(pr) == []


def test_edit_rejects_non_string_fields(tmp_path):
    """tipo / texto that are not strings return an error dict (a list used to raise TypeError: unhashable)."""
    pr, placed, tw, dec = _project(tmp_path)
    r1 = reports.add_report(pr, tipo="outro", texto="a", piece=placed)
    before = _lines(pr)
    for kw in ({"tipo": ["mal_lida"]}, {"tipo": 3}, {"tipo": {"a": 1}}, {"texto": 3}, {"texto": ["a"]}):
        e = reports.edit_report(pr, r1["id"], **kw)
        assert "error" in e, kw
    assert _lines(pr) == before
