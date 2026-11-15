"""Critério 3 (2026-11-15, decisão do Tiago; DETALHE.md §13): depois de uma escrita o detalhe da versão nova pede-se
logo, em paralelo com a recarga, sem as esperas de 350 ms (``scheduleReload``) e 280 ms (``scheduleDetail``).

Antes: SSE ``board_changed`` → 350 ms → ``loadBoard`` (``/api/board`` + ``/api/ghosts``) → 280 ms → o pedido da região.
Agora: ``board_changed`` → ``boardChanged(v)`` → o pedido da região (com ``v``) na mesma tarefa, e a recarga ao lado; a
resposta de ``/api/board`` com a mesma versão não pede a região outra vez. Playwright, ``slow``."""
import json
import urllib.request

import pytest

pytestmark = pytest.mark.slow
sync_api = pytest.importorskip("playwright.sync_api")

from test_gui_novo import base, browser  # noqa: E402,F401 - fixtures
from test_gui_novo_p0 import _away, _open, _settle_on  # noqa: E402

TRACE = """(() => {
  window.__tr = [];
  const T = () => performance.now();
  const ES = window.EventSource;
  window.EventSource = function (u, o) {
    const es = new ES(u, o);
    const add = es.addEventListener.bind(es);
    es.addEventListener = function (t, fn, op) {
      return add(t, function (e) { if (t === 'board_changed') window.__tr.push({ ev: 'sse', t: T(), v: JSON.parse(e.data).versao }); return fn.apply(this, arguments); }, op);
    };
    return es;
  };
  window.EventSource.prototype = ES.prototype;
  const F = window.fetch;
  window.fetch = function (u, o) {
    const url = String((u && u.url) || u), t0 = T();
    const r = { ev: 'fetch', url, t0, t1: null };
    window.__tr.push(r);
    return F.apply(this, arguments).then((x) => { r.t1 = T(); return x; });
  };
})();"""


def _post(url, body):
	rq = urllib.request.Request(url + "/api/confirm", data=json.dumps(body).encode(), method="POST",
								headers={"Content-Type": "application/json"})
	with urllib.request.urlopen(rq, timeout=120) as r:
		return json.loads(r.read())


def test_a_write_asks_the_new_detail_at_once_in_parallel_with_the_reload(base, browser):
	url, gui, tw = base
	pg, errs, _ = _open(browser, url)
	try:
		pg.evaluate(TRACE.replace("(() => {", "(() => { if (window.__tr) return;", 1))   # also on this page, now
		pg.evaluate("(() => { const es = new EventSource('/api/events'); es.addEventListener('board_changed', (e) => window.__tr.push({ ev: 'sse2', t: performance.now(), v: JSON.parse(e.data).versao })); })()")
		_settle_on(pg, _away(pg))                         # zoomed in: a detail is on screen
		k0 = pg.evaluate("S.detailKey")
		pg.evaluate("window.__tr.length = 0")
		_post(url, {"acao": "place", "piece": tw, "cell": [3, 4]})
		v = gui.version()
		pg.wait_for_function(f"S.detailKey && S.detailKey.endsWith('#{v}') && document.body.dataset.detail === S.detailKey", timeout=30_000)
		pg.wait_for_timeout(900)                          # the reload ends (a second region request would show here)
		tr = pg.evaluate("window.__tr")
		sse = [e for e in tr if e["ev"] == "sse2" and e["v"] == v]
		assert sse, tr
		t_sse = sse[0]["t"]
		regions = [e for e in tr if e["ev"] == "fetch" and "/api/board.jpg" in e["url"] and "region=" in e["url"] and f"v={v}" in e["url"]]
		boards = [e for e in tr if e["ev"] == "fetch" and e["url"].startswith("/api/board?")]
		assert len(regions) == 1, regions                 # one request for the new version, not a second after /api/board
		assert regions[0]["t0"] - t_sse < 150, (regions[0], t_sse)      # before: ≥ 350 + /api/board + 280 ms
		assert boards and regions[0]["t0"] <= boards[0]["t1"], (regions[0], boards)   # in parallel with the reload
		assert k0 != pg.evaluate("S.detailKey")
		assert not errs, errs
	finally:
		pg.close()
