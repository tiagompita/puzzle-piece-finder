"""Re-segmenta folhas já ingeridas e regista as silhuetas que mudaram (``piece_resegmented``).

Corre :func:`src.render.rebuild_assets` com ``force_scans`` (sem ``placements.json``, sem ``render/clean``):
as peças cujo ``bbox``/classe/cordas/área mudam ganham um evento ``piece_resegmented`` no ``log.jsonl``
(motivo ``--motivo``), o npz, os recortes dessas peças e ``overlays/S####.jpg`` são reescritos, e as
caches de visualização dessas peças são apagadas. A folha é abortada (nada escrito) se a contagem ou a
ordem das peças mudar. Uso, da raiz::

    python tools/rebuild_scans.py --project projects/alpes --scans S0009 --motivo recover_bays --dry-run
    python tools/rebuild_scans.py --project projects/alpes --scans S0009 --motivo recover_bays

``--also-missing`` processa também as folhas sem npz/recortes (sem as forçar). Sai com 1 se houver erros.

``--stale`` (sem ``--scans``): noutro PC, depois de ``git pull``. O log vem pelo git, mas ``pieces/*.npz``,
``crops/`` e ``render/`` não; :func:`src.render.stale_assets` lista as peças cujos ativos não batem com o log
(bbox, área, classe/cordas, tamanho do recorte) e :func:`src.render.rebuild_stale` re-segmenta só essas folhas.
Com o mesmo código que escreveu o log não há eventos novos; se houver, o resumo avisa (código diferente)::

    python tools/rebuild_scans.py --project projects/alpes --stale --dry-run
    python tools/rebuild_scans.py --project projects/alpes --stale
"""

import argparse
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from src import render as R  # noqa: E402
from src.state import Project, StateError  # noqa: E402


def main(argv=None) -> int:
	ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	ap.add_argument("--project", default=os.path.join("projects", "alpes"))
	g = ap.add_mutually_exclusive_group(required=True)
	g.add_argument("--scans", help="folhas a re-segmentar, separadas por vírgulas (S0009,S0023)")
	g.add_argument("--stale", action="store_true", help="só as folhas cujos ativos (npz, recortes) não batem com o log")
	ap.add_argument("--motivo", default="recover_bays")
	ap.add_argument("--dry-run", action="store_true", help="só mostra o que mudaria; nada é escrito")
	ap.add_argument("--also-missing", action="store_true", help="processa também as folhas sem npz/recortes")
	args = ap.parse_args(argv)
	try:
		pr = Project.open(args.project)
	except (StateError, ValueError) as e:
		print(f"erro: {e}")
		return 1
	n0 = len(pr.events())
	t0 = time.time()
	if args.stale:
		r = R.rebuild_stale(pr, dry_run=args.dry_run)
		for pid, why in sorted(r["antes"]["pecas"].items()):
			print(f"  {pid} ({pr.piece(pid).scan_id}): {', '.join(why)}")
		for e in r["errors"]:
			print("ERRO", e)
		if r["aviso"]:
			print("AVISO", r["aviso"])
		if not args.dry_run and r["folhas"]:
			pr = Project.open(args.project)
			inv = pr.check_invariants(disk=True)
			left = r["depois"]["n_pecas"] if r["depois"] else 0
			print(f"log: {n0} -> {len(pr.events())} eventos; invariantes: {'OK' if not inv else inv}; "
				  f"peças ainda desatualizadas: {left}")
			if inv or left:
				return 1
		print(f"{len(r['pecas'])} peças desatualizadas em {len(r['folhas'])} folhas, {r['eventos']} eventos, "
			  f"{time.time() - t0:.1f} s" + (" [dry-run: nada escrito]" if args.dry_run else ""))
		return 1 if r["errors"] else 0
	force = [s.strip() for s in args.scans.split(",") if s.strip()]
	r = R.rebuild_assets(pr, force_scans=force, scans=None if args.also_missing else force, motivo=args.motivo,
						 clean=False, register=False, dry_run=args.dry_run)
	for c in r["changed"]:
		print(f"{c['piece']} ({c['scan_id']} índice {c['index_in_scan']}): {', '.join(c['diff'])}")
		print(f"   bbox {c['bbox_old']} -> {c['bbox_new']} | classe {c['cls_old']} -> {c['cls_new']}")
		print(f"   cordas {c['chords_old']} -> {c['chords_new']} | área {c['area_old']} -> {c['area_new']} mm2"
			  + (f" | recuperado {c['flags_new']['recuperado_mm2']} mm2" if c["flags_new"].get("recuperado_mm2") else ""))
	for e in r["errors"]:
		print("ERRO", e)
	if not args.dry_run:
		pr = Project.open(args.project)
		inv = pr.check_invariants(disk=True)
		print(f"log: {n0} -> {len(pr.events())} eventos; invariantes: {'OK' if not inv else inv}")
		if inv:
			return 1
	print(f"{len(r['changed'])} silhuetas mudadas em {len(r['scans'])} folhas, {time.time() - t0:.1f} s"
		  + (" [dry-run: nada escrito]" if args.dry_run else ""))
	return 1 if r["errors"] else 0


if __name__ == "__main__":
	sys.exit(main())
