"""F3½ (2026-11-18): a manual pose never hides the orientation suspects. Measurement on a COPY of a project.

Never writes to the project: it is copied to ``--scratch`` first (``alpes_a`` read-only, ``alpes_b`` for the
P0833 reproduction, which writes events to the copy's log).

	(a) suspects (piece, cell, grade) and counts with the ``src`` given by ``--src`` (use a worktree of the old
	    commit for «antes»): ``--a-out a_antes.json``; ``--comparar a_antes.json a_depois.json`` prints the new
	    (piece, grade) pairs with cell, manual θ, automatic θ, grade and ``rot_alt_deg`` (the PARAGEM list);
	(b) P0833 on a copy: G0068 unanchored and anchored at (8, 2) with rot 180 (the state before 2026-11-16) and a
	    manual pose +3° from the automatic one: flagged? With the right anchor (rot 90): +5° (expected quiet) and
	    +90° (expected flagged);
	(c) the pieces with a manual pose: manual θ, automatic θ, circular Δθ; Δθ ≥ 45° = «rotação automática
	    errada, tapada pela pose manual».

	python tools/diagnostico/reports/f3meio_pose_manual.py --scratch DIR --a-out DIR/a_depois.json --b --c
	python tools/diagnostico/reports/f3meio_pose_manual.py --src WORKTREE --scratch DIR --a-out DIR/a_antes.json
	python tools/diagnostico/reports/f3meio_pose_manual.py --comparar DIR/a_antes.json DIR/a_depois.json
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _copy(src: str, dst: str) -> str:
	if os.path.exists(dst):
		shutil.rmtree(dst)
	shutil.copytree(src, dst, ignore=shutil.ignore_patterns("logs", "*.bak-*"))
	return dst


def _dtheta(a: float, b: float) -> float:
	return abs((float(a) - float(b) + 180.0) % 360.0 - 180.0)


def part_a(proj: str, out: str) -> dict:
	from src import consistency as C
	from src import render as R
	from src.state import Project
	pr = Project.open(proj)
	pl = dict(R.load_placements(pr).get("placements") or {})
	t0 = time.time()
	r = C.evaluate(pr, pl)
	items = [{"piece": it["piece"], "cell": it["cell"], "grau": it["grau"], "rot_alt_deg": it.get("rot_alt_deg"),
			  "pose_manual": bool(it.get("pose_manual"))} for it in r["items"]]
	res = {"summary": r["summary"], "items": items, "s": round(time.time() - t0, 1)}
	with open(out, "w", encoding="utf-8") as f:
		json.dump(res, f, ensure_ascii=False, indent=1)
	print(f"(a) src = {os.path.dirname(C.__file__)}")
	print(f"(a) {len(items)} suspeitas, {r['summary']['n_pose_manual']} com pose manual, {res['s']} s -> {out}")
	for it in items:
		print(f"    {it['piece']} {tuple(it['cell'])} {it['grau']}" + (" [pose manual]" if it["pose_manual"] else ""))
	return res


def compare(a0: str, a1: str, proj: str) -> list:
	with open(a0, encoding="utf-8") as f:
		r0 = json.load(f)
	with open(a1, encoding="utf-8") as f:
		r1 = json.load(f)
	k0 = {(it["piece"], it["grau"]) for it in r0["items"]}
	k1 = {(it["piece"], it["grau"]) for it in r1["items"]}
	print(f"(a) antes {len(k0)}, depois {len(k1)}; só antes {sorted(k0 - k1)}; só depois {sorted(k1 - k0)}")
	new = [it for it in r1["items"] if (it["piece"], it["grau"]) not in k0]
	if not new:
		return []
	from src import render as R
	from src.state import Project
	pr = Project.open(proj)
	rows = []
	for it in new:
		pm = R.manual_pose(pr, it["piece"])
		auto = R.register_piece(pr, it["piece"], art=None, image=False, manual=False)
		rows.append(dict(it, theta_manual=None if pm is None else pm["theta_deg"], theta_auto=auto["theta_deg"]))
		print("    PARAGEM", rows[-1])
	return rows


def _flag(pr, pid):
	from src import consistency as C
	r = C.evaluate(pr, {}, pieces=[pid], dismissed={})
	it = next((x for x in r["items"] if x["piece"] == pid and x["grau"] in ("impossivel", "melhor_rotacao")), None)
	return None if it is None else {"grau": it["grau"], "rot_alt_deg": it["rot_alt_deg"], "texto": it["texto"],
									 "pose_manual": bool(it.get("pose_manual"))}


def part_b(proj: str) -> dict:
	from src import render as R
	from src.state import Project
	pid, sec = "P0833", "G0068"
	pr = Project.open(proj)
	anc = dict(pr.sections[sec].anchor)
	assert anc.get("anchored") and anc["rot"] == 90 and (anc["l0"], anc["c0"]) == (8, 2), anc
	out = {}

	def case(rot, dth):
		if pr.sections[sec].anchor.get("anchored"):
			pr.unanchor_section(sec)
		pr.anchor_section(sec, 8, 2, rot=rot)
		assert tuple(pr.piece(pid).celula) == (8, 2) and pr.piece(pid).estado == "colocada"
		e = R.register_piece(pr, pid, art=None, image=False, manual=False)
		pr.set_pose(pid, e["theta_deg"] + dth, 0.0, 0.0)
		f = _flag(pr, pid)
		key = f"rot{rot}_{dth:+g}"
		out[key] = {"theta_auto": round(e["theta_deg"], 2), "theta_manual": round(pr.piece(pid).pose_manual["theta_deg"], 2),
					"sinal": f}
		print(f"(b) {key}: θ auto {e['theta_deg']:.1f}°, manual {pr.piece(pid).pose_manual['theta_deg']:.1f}° -> "
			  + ("nada" if f is None else f"{f['grau']} {f['rot_alt_deg']:+d}° «{f['texto']}»"))

	case(180, 3.0)
	case(90, 5.0)
	case(90, 90.0)
	return out


def part_c(proj: str) -> list:
	from src import render as R
	from src.state import Project
	pr = Project.open(proj)
	rows = []
	for pid in sorted(pr.pieces):
		pm = R.manual_pose(pr, pid)
		if pm is None:
			continue
		auto = R.register_piece(pr, pid, art=None, image=False, manual=False)
		d = _dtheta(pm["theta_deg"], auto["theta_deg"])
		rows.append({"piece": pid, "cell": list(pr.piece(pid).celula), "theta_manual": round(pm["theta_deg"], 2),
					 "theta_auto": round(auto["theta_deg"], 2), "dtheta": round(d, 1), "tapada": d >= 45.0})
		print(f"(c) {pid} {tuple(pr.piece(pid).celula)}: manual {pm['theta_deg']:.1f}°, automática "
			  f"{auto['theta_deg']:.1f}°, Δθ {d:.1f}°" + ("  <- rotação automática errada, tapada pela pose manual" if d >= 45 else ""))
	return rows


def main(argv=None) -> int:
	ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
	ap.add_argument("--project", default=os.path.join(ROOT, "projects", "alpes"))
	ap.add_argument("--src", default=ROOT, help="repository root whose src/ is imported (a worktree for «antes»)")
	ap.add_argument("--scratch", default=os.environ.get("PPF_SCRATCH") or tempfile.gettempdir())
	ap.add_argument("--a-out")
	ap.add_argument("--b", action="store_true")
	ap.add_argument("--c", action="store_true")
	ap.add_argument("--comparar", nargs=2)
	ap.add_argument("--json-out")
	a = ap.parse_args(argv)
	if hasattr(sys.stdout, "reconfigure"):
		sys.stdout.reconfigure(encoding="utf-8")
	sys.path.insert(0, os.path.abspath(a.src))
	scratch = os.path.join(a.scratch, "f3meio")
	os.makedirs(scratch, exist_ok=True)
	res = {}
	proj_a = os.path.join(scratch, "alpes_a")
	if a.a_out or a.c or a.comparar:
		if not os.path.exists(os.path.join(proj_a, "log.jsonl")):
			_copy(a.project, proj_a)
	if a.a_out:
		res["a"] = part_a(proj_a, a.a_out)
	if a.comparar:
		res["paragem"] = compare(a.comparar[0], a.comparar[1], proj_a)
	if a.c:
		res["c"] = part_c(proj_a)
	if a.b:
		res["b"] = part_b(_copy(a.project, os.path.join(scratch, "alpes_b")))
	if a.json_out:
		with open(a.json_out, "w", encoding="utf-8") as f:
			json.dump(res, f, ensure_ascii=False, indent=1)
	return 1 if res.get("paragem") else 0


if __name__ == "__main__":
	sys.exit(main())
