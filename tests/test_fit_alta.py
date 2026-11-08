"""Contador e regra de pausa das sugestões ``alta`` (M11_CRITERIOS §8, :func:`src.fit.alta_counter`) sobre eventos
sintéticos: só ``hole_confirmed`` / ``hole_rejected`` com origem ``buraco``, ``confianca alta`` e ``rank 1`` contam;
janela = as últimas 20 depois do último ``holes_alta_resumed``; ≥ 3 rejeições na janela = pausa."""

import math

from src import fit as F


def _ev(action, k, conf="alta", rank=1, origin="buraco"):
	return {"t": f"2026-11-08T00:00:{k:02d}", "action": action, "piece": f"P{k:04d}", "cell": [1, k % 60 + 1], "origin": origin,
			"rank": rank, "custo": 1.0, "margem": 2.0, "confianca": conf, "m": 2, "fit_version": "t"}


def _counter(events):
	return F.alta_counter(None, events=events)


def test_ten_out_of_ten_matches_wilson_and_no_pause():
	c = _counter([_ev("hole_confirmed", k) for k in range(10)])
	assert c["acertos"] == 10 and c["falhas"] == 0 and c["total"] == 10 and c["precisao"] == 1.0
	lo, hi = c["ic95"]
	assert abs(lo - F.wilson(10, 10)[0]) < 1e-12 and 0.71 < lo < 0.73 and hi == 1.0
	assert c["janela"] == {"n": 10, "falhas": 0, "acertos": 10, "tamanho": F.ALTA_JANELA, "max_falhas": F.ALTA_MAX_FALHAS, "em_pausa": False}
	assert c["em_pausa"] is False and c["reativado_em"] is None and c["ultima_decisao"] == "2026-11-08T00:00:09"


def test_empty_counter():
	c = _counter([])
	assert c["total"] == 0 and c["precisao"] is None and c["ic95"] is None and c["em_pausa"] is False and c["janela"]["n"] == 0


def test_two_rejections_in_twenty_do_not_pause_but_three_do():
	base = [_ev("hole_confirmed", k) for k in range(18)]
	assert _counter(base + [_ev("hole_rejected", 18), _ev("hole_rejected", 19)])["em_pausa"] is False
	c = _counter(base + [_ev("hole_rejected", 18), _ev("hole_rejected", 19), _ev("hole_rejected", 20)])
	assert c["em_pausa"] is True and c["janela"]["n"] == 20 and c["janela"]["falhas"] == 3 and c["falhas"] == 3 and c["total"] == 21


def test_three_rejections_in_five_pause_too():
	c = _counter([_ev("hole_confirmed", 0), _ev("hole_rejected", 1), _ev("hole_confirmed", 2), _ev("hole_rejected", 3), _ev("hole_rejected", 4)])
	assert c["em_pausa"] is True and c["janela"]["n"] == 5 and c["janela"]["falhas"] == 3


def test_window_slides_old_rejections_out():
	evs = [_ev("hole_rejected", k) for k in range(3)] + [_ev("hole_confirmed", k) for k in range(3, 23)]
	c = _counter(evs)
	assert c["falhas"] == 3 and c["janela"]["falhas"] == 0 and c["em_pausa"] is False       # the 3 old ones left the window of 20


def test_resume_restarts_the_window():
	evs = [_ev("hole_rejected", k) for k in range(3)]
	assert _counter(evs)["em_pausa"] is True
	evs2 = evs + [{"t": "2026-11-08T01:00:00", "action": "holes_alta_resumed", "autor": "tiago", "nota": ""}]
	c = _counter(evs2)
	assert c["em_pausa"] is False and c["janela"]["n"] == 0 and c["falhas"] == 3 and c["total"] == 3 and c["reativado_em"] == "2026-11-08T01:00:00"
	c = _counter(evs2 + [_ev("hole_rejected", 10), _ev("hole_rejected", 11)])
	assert c["em_pausa"] is False and c["janela"]["falhas"] == 2
	assert _counter(evs2 + [_ev("hole_rejected", k) for k in (10, 11, 12)])["em_pausa"] is True


def test_only_rank1_alta_buraco_decisions_count():
	evs = [_ev("hole_rejected", 0, rank=2), _ev("hole_rejected", 1, conf="media"), _ev("hole_rejected", 2, origin="fronteira"),
		   _ev("hole_rejected", 3, rank=3), _ev("hole_confirmed", 4, conf="sem"), _ev("hole_confirmed", 5)]
	c = _counter(evs)
	assert c["total"] == 1 and c["acertos"] == 1 and c["falhas"] == 0 and c["em_pausa"] is False


def test_format_counter_mentions_pause_and_window():
	txt = F.format_counter(_counter([_ev("hole_rejected", k) for k in range(3)]))
	assert "EM PAUSA" in txt and "3 falhas em 3" in txt and f"{F.ALTA_MAX_FALHAS} em {F.ALTA_JANELA}" in txt
	txt = F.format_counter(_counter([_ev("hole_confirmed", k) for k in range(10)]))
	assert "acertos 10 / falhas 0 / total 10" in txt and "100 %" in txt and "72–100 %" in txt and "ativas" in txt


def test_alta_suggestions_filter():
	holes = [
		{"confidence": "alta", "assigned": "A", "candidates": [{"id": "A", "rank": 1}, {"id": "B", "rank": 2}]},
		{"confidence": "alta", "assigned": "Z", "candidates": [{"id": "A", "rank": 1}]},        # assigned elsewhere: conflict
		{"confidence": "alta", "assigned": None, "candidates": [{"id": "C", "rank": 1}]},
		{"confidence": "media", "assigned": "D", "candidates": [{"id": "D", "rank": 1}]},
		{"confidence": "sem", "candidates": []},
	]
	out = F.alta_suggestions(holes)
	assert [s["candidate"]["id"] for s in out] == ["A", "C"]
	assert math.isclose(sum(1 for s in out if s["hole"]["confidence"] == "alta"), 2)
