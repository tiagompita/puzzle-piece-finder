"""Lançador do servidor com uma linha do tempo de TODOS os fios (perfil do critério 3, DETALHE.md §12).

Uso: ``python tools/diagnostico/gui/linha_tempo.py <saída.jsonl> -- <argumentos de python -m src.server>``.

Cada linha JSON: ``{t (time.time(), s), th (nome do fio), ev, ph: b|e|i|x, dur?, ...}`` (b/e = início/fim de uma
fase, i = instante, x = fase completa com ``t0``). Fases: o POST (``Gui.confirm``, ``src.confirm.confirm``,
``run_query``, ``_after_write``, ``_refresh_render_assets``), as suspeitas (``_emit_suspeitas``,
``consistency.evaluate``), os buracos (``holes_json`` como instante, ``fit.rank_all``), o pré-aquecimento
(``_prewarm``), cada espera de um trabalho de fundo pela GUI (``yield_to_gui``, só quando espera), as regiões
(``_region_jpg``, acerto/falha da LRU, ``_compose``, ``placements``), o tabuleiro inteiro (``_base``), cada peça
preparada (``render.piece_ready`` = falha da E, com o fio), cada ``ReadyCache.forget``/``clear`` (com quem chamou),
cada evento SSE emitido e cada pedido HTTP (início/fim, caminho). Não muda ``src/`` (embrulhos em memória)."""
import functools
import json
import os
import sys
import threading
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ROOT = os.environ.get("PPF_REPO") or ROOT
sys.path.insert(0, ROOT)

_lock = threading.Lock()
_f = None


def rec(ev, **kw):
	row = {"t": time.time(), "th": threading.current_thread().name, "ev": ev, **kw}
	line = json.dumps(row, ensure_ascii=False, default=str)
	with _lock:
		_f.write(line + "\n")
		_f.flush()


def _caller(skip=2):
	st = traceback.extract_stack(limit=skip + 3)[:-skip]
	return " < ".join(f"{fr.name}:{fr.lineno}" for fr in reversed(st[-3:]))


def span(owner, name, label, extra=None):
	fn = getattr(owner, name, None)
	if fn is None:
		return

	@functools.wraps(fn)
	def inner(*a, **k):
		x = {}
		if extra is not None:
			try:
				x = extra(*a, **k)
			except Exception:  # noqa: BLE001 - only a label
				x = {}
		t0 = time.time()
		rec(label, ph="b", **x)
		ok = True
		try:
			return fn(*a, **k)
		except BaseException as e:
			ok = False
			x["erro"] = type(e).__name__
			raise
		finally:
			rec(label, ph="e", dur=round(time.time() - t0, 4), ok=ok, **x)
	setattr(owner, name, inner)


def install(out_path):
	global _f
	_f = open(out_path, "a", encoding="utf-8")
	from src import server as SV, confirm as C, query as Q, consistency as CO, fit as FI, render as R
	span(SV.Gui, "confirm", "POST confirm", lambda self, body, *a, **k: {"acao": body.get("acao"), "piece": body.get("piece"), "cell": body.get("cell")})
	span(C, "confirm", "confirm.confirm")
	span(Q, "run_query", "run_query")
	span(SV.Gui, "_after_write", "_after_write")
	span(SV.Gui, "_refresh_render_assets", "_refresh_render_assets", lambda self, pids: {"pids": list(pids)})
	span(SV.Gui, "_emit_suspeitas", "_emit_suspeitas")
	span(CO, "evaluate", "consistency.evaluate")
	span(FI, "rank_all", "fit.rank_all")
	span(SV.Gui, "_prewarm", "_prewarm")
	span(SV.Gui, "_region_jpg", "_region_jpg", lambda self, ppc, region, **k: {"ppc": ppc, "region": list(region), "seq": k.get("seq")})
	span(SV.Gui, "_compose", "_compose", lambda self, ppc, region=None: {"ppc": ppc, "region": list(region) if region else None})
	span(SV.Gui, "_base", "_base (tabuleiro inteiro)")
	span(SV.Gui, "placements", "placements()")
	span(R, "piece_ready", "piece_ready (falha E)", lambda pr, pid, *a, **k: {"pid": pid})

	orig_hj = SV.Gui.holes_json

	def holes_json(self, *a, **k):
		rec("holes_json", ph="i", wait=k.get("wait"), tem=getattr(self, "_holes", None) is not None)
		return orig_hj(self, *a, **k)
	SV.Gui.holes_json = holes_json

	orig_rc = SV.Gui._region_cached

	def _region_cached(self, key, ver):
		r = orig_rc(self, key, ver)
		c = self._regions.get(key)
		rec("região LRU", ph="i", key=str(key), ver=list(ver) if isinstance(ver, tuple) else ver, acerto=r is not None,
			ver_guardada=(list(c[0]) if c is not None and isinstance(c[0], tuple) else (c[0] if c else None)))
		return r
	SV.Gui._region_cached = _region_cached

	orig_y = SV.Gui.yield_to_gui

	def yield_to_gui(self):
		if not self._fg_n or self.closing:
			return orig_y(self)
		t0 = time.time()
		r = orig_y(self)
		rec("cede à GUI", ph="x", t0=t0, dur=round(time.time() - t0, 4))
		return r
	SV.Gui.yield_to_gui = yield_to_gui

	orig_emit = SV.Gui.emit

	def emit(self, name, data=None):
		if name != "atividade":
			rec("SSE emitido", ph="i", name=name)
		return orig_emit(self, name, data)
	SV.Gui.emit = emit

	orig_forget, orig_clear = SV.ReadyCache.forget, SV.ReadyCache.clear

	def forget(self, pid):
		rec("E forget", ph="i", pid=pid, por=_caller())
		return orig_forget(self, pid)

	def clear(self):
		rec("E clear", ph="i", n=len(self.d), por=_caller())
		return orig_clear(self)
	SV.ReadyCache.forget, SV.ReadyCache.clear = forget, clear

	orig_app = SV.create_app

	def create_app(gui):
		app = orig_app(gui)

		@app.middleware("http")
		async def timeline(request, call_next):
			path = request.url.path + ("?" + request.url.query if request.url.query else "")
			if request.url.path in ("/api/events", "/api/status"):
				return await call_next(request)
			t0 = time.time()
			rec("HTTP", ph="b", path=path)
			resp = await call_next(request)
			rec("HTTP", ph="e", path=path, dur=round(time.time() - t0, 4), status=resp.status_code)
			return resp
		return app
	SV.create_app = create_app


def main():
	i = sys.argv.index("--")
	install(os.path.abspath(sys.argv[1]))
	from src import server as SV
	sys.exit(SV.main(sys.argv[i + 1:]))


if __name__ == "__main__":
	main()
