"""Lançador do servidor com o POST de uma escrita (``Gui.confirm``) cronometrado por fase (DETALHE.md §11, P0b).

Uso: ``python tools/diagnostico/gui/fases_post.py <saída.jsonl> -- <argumentos de python -m src.server>``.

Embrulha, só no fio que está dentro de ``Gui.confirm`` (os outros fios não contam), as fases do POST:
``sync_locked``, ``board_snapshot``, ``src.confirm.confirm`` (escrita no log + invariantes + reconsulta incremental)
e, dentro dele, ``Project.save``, ``check_invariants``, ``run_query``; depois ``_refresh_render_assets``,
``_emit_suspeitas`` (``consistency.evaluate``), ``holes_json``, ``_written_since``, e as escritas/leituras
``state.write_atomic`` / ``state.read_retry``. Uma linha JSON por POST: ``{acao, total_s, fases: {nome: [n, s]}}``.
Não muda ``src/`` (embrulhos em memória, só neste processo)."""
import functools
import json
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ROOT = os.environ.get("PPF_REPO") or ROOT          # bisect: o código de um worktree
sys.path.insert(0, ROOT)

_tl = threading.local()
_out_lock = threading.Lock()


def _wrap(owner, name, label):
	"""Replace ``owner.name`` by a timer that counts only inside a timed POST (thread-local)."""
	fn = getattr(owner, name, None)
	if fn is None:                    # an older checkout (bisect) without this function: nothing to time
		return

	@functools.wraps(fn)
	def inner(*a, **k):
		acc = getattr(_tl, "acc", None)
		if acc is None:
			return fn(*a, **k)
		t0 = time.perf_counter()
		try:
			return fn(*a, **k)
		finally:
			n, s = acc.get(label, (0, 0.0))
			acc[label] = (n + 1, s + time.perf_counter() - t0)
	setattr(owner, name, inner)


def install(out_path):
	"""Patch the server phases; every ``Gui.confirm`` appends one JSON line to ``out_path``."""
	from src import server as SV, state as ST, query as Q, confirm as C, consistency as CO, render as R
	_wrap(SV.Gui, "sync_locked", "sync_locked")
	_wrap(SV, "board_snapshot", "board_snapshot")
	_wrap(C, "confirm", "confirm (escrita+reconsulta)")
	_wrap(ST.Project, "save", "  Project.save")
	_wrap(ST.Project, "check_invariants", "  check_invariants")
	_wrap(Q, "run_query", "  run_query")
	_wrap(SV.Gui, "_after_write", "_after_write")
	_wrap(SV.Gui, "_refresh_render_assets", "  _refresh_render_assets")
	_wrap(R, "register_piece", "    register_piece")
	_wrap(R, "clean_crop", "    clean_crop")
	_wrap(SV.Gui, "_emit_suspeitas", "  _emit_suspeitas")
	_wrap(CO, "evaluate", "    consistency.evaluate")
	_wrap(SV.Gui, "holes_json", "  holes_json")
	_wrap(SV.Gui, "_written_since", "_written_since")
	_wrap(ST, "write_atomic", "write_atomic")
	_wrap(R, "write_atomic", "write_atomic")
	_wrap(ST, "read_retry", "read_retry")
	_wrap(R, "read_retry", "read_retry")
	_wrap(SV.OV, "latest_arestas", "latest_arestas")
	orig = SV.Gui.confirm

	def confirm(self, body):
		_tl.acc = {}
		t0 = time.perf_counter()
		try:
			return orig(self, body)
		finally:
			acc, _tl.acc = _tl.acc, None
			row = {"acao": body.get("acao"), "piece": body.get("piece"), "cell": body.get("cell"),
				   "total_s": round(time.perf_counter() - t0, 3),
				   "fases": {k: [n, round(s, 3)] for k, (n, s) in acc.items()}}
			with _out_lock, open(out_path, "a", encoding="utf-8") as f:
				f.write(json.dumps(row, ensure_ascii=False) + "\n")
	SV.Gui.confirm = confirm


def main():
	i = sys.argv.index("--")
	install(os.path.abspath(sys.argv[1]))
	from src import server as SV
	sys.exit(SV.main(sys.argv[i + 1:]))


if __name__ == "__main__":
	main()
