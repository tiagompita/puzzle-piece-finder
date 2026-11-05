"""Static checks of the GUI sources (fast, no browser): feedback of 2026-11-05."""
import os
import re

WEB = os.path.join(os.path.dirname(__file__), "..", "src", "web")


def _read(name):
    with open(os.path.join(WEB, name), encoding="utf-8") as f:
        return f.read()


def test_centrar_renamed_to_localizar_peca():
    js = _read("app.js")
    assert "Centrar" not in js and "Centrar" not in _read("index.html") and "Centrar" not in _read("app.css")
    assert "Localizar peça" in js and "locateIcon" in js


def test_report_button_is_red_and_spaced():
    js, css = _read("app.js"), _read("app.css")
    assert 'class: "btn slim report"' in js and "⚠ Reportar" in js
    assert re.search(r"\.btn\.report\s*\{[^}]*background", css)
    assert re.search(r"\.card-top \+ \.actions[^{]*\{[^}]*margin-top:\s*1[4-9]px", css)


def test_legend_has_arrows_on_both_sides():
    css = _read("app.css")
    assert "#legend-box > summary::before" in css and "#legend-box > summary::after" in css
    assert "justify-content: center" in css
