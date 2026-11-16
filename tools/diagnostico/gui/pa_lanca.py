"""P-a, passo 0 (DETALHE.md §13.10): lançador do servidor com a linha do tempo (``linha_tempo.py``) e embrulhos de
parede/CPU em ``_region_parts``, ``_compose_region``, ``board_json``, ``ghosts``, ``montar_json``, ``_region_jpg``,
``_jpeg``, ``render.compose_patch``, ``_piece_jobs``, ``_draw_jobs`` (os de ``lanca_novo.py`` de §13.7), mais a
simulação da forma (b) quando ``PPF_PA_B`` está definido: os métodos aí listados (separados por vírgula) esperam, no
início, que nenhuma composição de detalhe (``_region_jpg``) esteja em curso, no máximo ``PPF_PA_LIM`` s. Só em memória.

Uso: ``python pa_lanca.py <linha_do_tempo.jsonl> -- <argumentos de src.server>`` (o corredor é ``pa_rodar.py``)."""
import os
import sys
import threading
import time

ROOT = os.environ.get("PPF_REPO") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import linha_tempo as LT  # noqa: E402


def wrap(owner, name, label):
	orig = getattr(owner, name)

	def f(*a, **k):
		w, c = time.perf_counter(), time.thread_time()
		try:
			return orig(*a, **k)
		finally:
			dw = time.perf_counter() - w
			LT.rec(label, ph="x", t0=time.time() - dw, dur=round(dw, 4), cpu=round(time.thread_time() - c, 4))
	setattr(owner, name, f)


def install(out):
	LT.install(out)
	from src import server as SV, render as R
	for nm in ("_region_parts", "_compose_region", "board_json", "ghosts", "montar_json"):
		wrap(SV.Gui, nm, f"novo {nm}")
	wrap(SV.Gui, "_region_jpg", "novo _region_jpg")
	wrap(SV, "_jpeg", "novo _jpeg")
	wrap(R, "compose_patch", "novo compose_patch")
	wrap(R, "_piece_jobs", "novo _piece_jobs")
	wrap(R, "_draw_jobs", "novo _draw_jobs")


def install_b(names, lim):
	from src import server as SV
	cond = threading.Condition()
	st = {"n": 0}
	orig = SV.Gui._region_jpg

	def region(self, *a, **k):
		with cond:
			st["n"] += 1
		try:
			return orig(self, *a, **k)
		finally:
			with cond:
				st["n"] -= 1
				if not st["n"]:
					cond.notify_all()
	SV.Gui._region_jpg = region
	for nm in names:
		o = getattr(SV.Gui, nm)

		def mk(o, nm):
			def f(self, *a, **k):
				t0 = time.perf_counter()
				with cond:
					cond.wait_for(lambda: st["n"] == 0, timeout=lim)
				dw = time.perf_counter() - t0
				LT.rec(f"pa espera {nm}", ph="x", t0=time.time() - dw, dur=round(dw, 4), cpu=0)
				return o(self, *a, **k)
			return f
		setattr(SV.Gui, nm, mk(o, nm))


def main():
	i = sys.argv.index("--")
	install(os.path.abspath(sys.argv[1]))
	b = os.environ.get("PPF_PA_B")
	if b:
		install_b([x for x in b.split(",") if x], float(os.environ.get("PPF_PA_LIM", "1.0")))
	from src import server as SV
	sys.exit(SV.main(sys.argv[i + 1:]))


if __name__ == "__main__":
	main()
