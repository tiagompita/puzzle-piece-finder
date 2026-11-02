"""Register a board photo (occupancy map, M14) and reconcile the board (``python -m src.photo``).

Usage::

	python -m src.photo <foto.jpg> [--fix "1,29=0" "1,34=1"] [--project projects/alpes]
	python -m src.photo --from-json ocupacao.json [--fix ...]
	python -m src.photo --cheia 3,10 7,2 [--vazia 1,29] [--project projects/alpes]

With an image, the M14 prototype ``tools/diagnostico/ocupacao/ocupacao.py`` is loaded by
path and its ``run(name, art, gt)`` is called with the photo path injected in
``F_PHOTO`` and its output folder redirected to ``<project>/photos/`` (it never writes in
``docs/``). With ``--from-json`` the ``celulas`` matrix (``celulas[l-1][c-1]`` ∈ {1, 0, -1})
is read. ``--fix L,C=V`` overrides cells (manual confirmation). Then
:meth:`src.state.Project.register_photo` reconciles and the warnings are printed.

``--cheia`` / ``--vazia`` (without a photo) are the user's own word about cells: logged as
``cell_occupied_by_user`` / ``cell_cleared_by_user`` (``fonte='tiago'``, ground truth that
a later photo never overrides; same as ``python -m src.confirm --cheia/--vazia``), then the
cells and their twins are re-queried. A ``fonte='foto'`` cell (photo only, no piece) counts
as empty for the queries (doubt policy, :mod:`src.state`).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import importlib.util
import json
import os
import sys

__all__ = ["parse_fix", "apply_fixes", "photo_from_json", "photo_from_image", "register", "main"]

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OCUPACAO = os.path.join(REPO, "tools", "diagnostico", "ocupacao", "ocupacao.py")


def parse_fix(s: str) -> tuple:
	"""``"1,29=0"`` -> ``((1, 29), 0)``."""
	try:
		lc, v = s.split("=")
		l, c = lc.split(",")
		v = int(v)
	except ValueError:
		raise ValueError(f"--fix inválido {s!r} (formato L,C=V)") from None
	if v not in (1, 0, -1):
		raise ValueError(f"--fix {s!r}: valor tem de ser 1, 0 ou -1")
	return (int(l), int(c)), v


def apply_fixes(cells: list, fixes) -> list:
	"""Copy of ``cells`` with each ``((l, c), v)`` applied."""
	out = [list(r) for r in cells]
	for (l, c), v in fixes:
		out[l - 1][c - 1] = int(v)
	return out


def photo_from_json(path: str, fixes=()):
	""":class:`src.state.Photo` from an M14 JSON (``celulas`` [+ ``homografia``, ``residual_px``])."""
	from src.state import Photo, file_sha256
	with open(path, encoding="utf-8") as f:
		d = json.load(f)
	if "celulas" not in d:
		raise ValueError(f"{path}: falta 'celulas'")
	H = d.get("homografia")
	return Photo(id=None, file=",".join(d["fontes"]) if d.get("fontes") else os.path.basename(path),
				 sha256=file_sha256(path), date=_dt.date.fromtimestamp(os.path.getmtime(path)).isoformat(),
				 map=apply_fixes(d["celulas"], fixes), homography=(H.get("H") if isinstance(H, dict) else H),
				 residual=d.get("residual_px"))


def _load_ocupacao():
	spec = importlib.util.spec_from_file_location("ppf_ocupacao", OCUPACAO)
	mod = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(mod)
	return mod


def photo_from_image(path: str, out_dir: str, fixes=()):
	"""Run the M14 prototype on ``path`` (figures + JSON in ``out_dir``); returns a Photo or ``{'error'}``."""
	from src.state import Photo, file_sha256
	mod = _load_ocupacao()
	name = "foto"
	os.makedirs(out_dir, exist_ok=True)
	mod.F_PHOTO = dict(mod.F_PHOTO, **{name: os.path.abspath(path)})
	mod.OUT = out_dir
	r = mod.run(name, mod.art_cells(), mod.gt_cells())
	if "error" in r:
		return r
	with open(os.path.join(out_dir, f"ocupacao_{name}.json"), encoding="utf-8") as f:
		d = json.load(f)
	return Photo(id=None, file=os.path.abspath(path), sha256=file_sha256(path), date=None,
				 map=apply_fixes(d["celulas"], fixes), homography=d.get("homografia", {}).get("H"),
				 residual=d.get("residual_px"))


def register(project, photo) -> dict:
	"""Register ``photo`` in ``project`` and save; returns ``{photo_id, warnings, changes}`` or ``{'error'}``."""
	n0 = len(project.events())
	try:
		warnings = project.register_photo(photo)
	except ValueError as e:
		return {"error": str(e)}
	project.save()
	new = project.events()[n0:]
	ch = {}
	for ev in new:
		ch[ev["action"]] = ch.get(ev["action"], 0) + 1
	fid = next(ev["photo"]["id"] for ev in new if ev["action"] == "photo_registered")
	return {"photo_id": fid, "warnings": warnings, "changes": ch,
			"placeable": [(ev["piece"], ev["cell"]) for ev in new if ev["action"] == "position_placeable"]}


def main(argv=None) -> int:
	from src.ingest import add_project_args, open_project
	ap = argparse.ArgumentParser(prog="python -m src.photo", description="Regista uma foto do tabuleiro (mapa de ocupação).")
	ap.add_argument("image", nargs="?", default=None)
	ap.add_argument("--from-json", default=None)
	ap.add_argument("--fix", nargs="*", default=[], help='correções "L,C=V" (V = 1, 0 ou -1)')
	ap.add_argument("--cheia", nargs="+", default=None, metavar="L,C", help="células que sabes estarem montadas (sem foto)")
	ap.add_argument("--vazia", nargs="+", default=None, metavar="L,C", help="células que sabes estarem vazias (sem foto)")
	ap.add_argument("--no-requery", action="store_true")
	add_project_args(ap)
	args = ap.parse_args(argv)
	if (args.cheia or args.vazia) and not (args.image or args.from_json):
		return _hints_main(args)
	if bool(args.image) == bool(args.from_json):
		print("erro: indica uma foto OU --from-json (ou --cheia/--vazia)")
		return 1
	if args.cheia or args.vazia:
		print("erro: --cheia/--vazia vão sem foto (corre-os à parte)")
		return 1
	try:
		fixes = [parse_fix(s) for s in args.fix]
		pr = open_project(args)
		for (l, c), _ in fixes:
			if not pr.profile.in_grid(l, c):
				raise ValueError(f"--fix ({l},{c}) fora da grelha")
		if args.from_json:
			ph = photo_from_json(args.from_json, fixes)
		else:
			ph = photo_from_image(args.image, pr.p("photos", "ocupacao"), fixes)
			if isinstance(ph, dict):
				print(f"erro: {ph['error']}")
				return 1
	except (ValueError, OSError) as e:
		print(f"erro: {e}")
		return 1
	r = register(pr, ph)
	if "error" in r:
		print(f"erro: {r['error']}")
		return 1
	flat = [v for row in ph.map for v in row]
	print(f"{r['photo_id']}: cheias {flat.count(1)}, vazias {flat.count(0)}, incertas {flat.count(-1)}; "
		  f"correções {[f'{l},{c}={v}' for (l, c), v in fixes]}")
	print(f"eventos: {r['changes']}")
	for w in r["warnings"]:
		print(f"AVISO: {w}")
	for pid, cell in r["placeable"]:
		print(f"podes colocar {pid} em {tuple(cell)}")
	st = pr.stats()
	print(f"tabuleiro: {st['celulas']}; borda em falta {st['borda_em_falta']}")
	bad = pr.check_invariants(disk=True)
	if bad:
		print("INVARIANTES VIOLADAS: " + "; ".join(bad))
		return 1
	return 0


def _hints_main(args) -> int:
	from src.confirm import confirm, parse_cells
	from src.ingest import open_project
	try:
		full = parse_cells(args.cheia) if args.cheia else None
		empty = parse_cells(args.vazia) if args.vazia else None
		pr = open_project(args)
		for l, c in (full or []) + (empty or []):
			if not pr.profile.in_grid(l, c):
				raise ValueError(f"({l},{c}) fora da grelha")
	except (ValueError, OSError) as e:
		print(f"erro: {e}")
		return 1
	r = confirm(pr, cell_full=full, cell_empty=empty, requery=not args.no_requery)
	if "error" in r:
		print(f"erro: {r['error']}")
		return 1
	for m in r["messages"]:
		print(m)
	st = pr.stats()
	print(f"tabuleiro: {st['celulas']}; pistas {st['celulas_pista']}, só na foto {st['celulas_so_foto']}")
	if r["invariants"]:
		print("INVARIANTES VIOLADAS: " + "; ".join(r["invariants"]))
		return 1
	return 0


if __name__ == "__main__":
	sys.exit(main())
