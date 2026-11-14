"""Recortes da folha para as máscaras feitas à mão no Photoshop (GT da fase 2 do editor, ronda 10).

Uso (a partir da raiz do repositório; ``--project`` pode ser projects/alpes: só lê)::

	python tools/diagnostico/editor/gt_photoshop_recortes.py --project projects/alpes [--out docs/diagnostico/editor/gt_photoshop] [P1203 P0045 ...]

Para cada peça grava ``P####.png``: o recorte da folha do scan que o editor de contornos mostra
(``overrides.crop_window``: caixa da peça + ``MARGIN_MM`` de margem, cortada à folha; o mesmo que
``GET /api/pieces/{id}/contorno.png``), RGB sem alfa, à resolução do scan. Em ``recortes.json`` fica, por peça, a folha
(``scan_id``), a origem e o tamanho do recorte em px do scan e os mm por px, para pôr a máscara devolvida de volta na
grelha do scan inteiro. Não liga nada ao índice nem ao projeto.
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO)
PIECES = ("P1203", "P0045", "P1245", "P0198")


def main(argv=None) -> int:
	from src import overrides as OV
	from src import render
	from src.state import Project
	ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	ap.add_argument("--project", required=True)
	ap.add_argument("--out", default=os.path.join(REPO, "docs", "diagnostico", "editor", "gt_photoshop"))
	ap.add_argument("pieces", nargs="*", default=list(PIECES))
	a = ap.parse_args(argv)
	pr = Project.open(a.project)
	os.makedirs(a.out, exist_ok=True)
	meta = {}
	for pid in a.pieces:
		p = pr.piece(pid)
		x0, y0, x1, y1, m = OV.crop_window(pr, pid)
		rgb = OV.load_scan_rgb(pr, p.scan_id)
		crop = np.ascontiguousarray(rgb[y0:y1, x0:x1, ::-1])
		ok, buf = cv2.imencode(".png", crop)
		assert ok
		with open(os.path.join(a.out, f"{pid}.png"), "wb") as f:
			f.write(buf.tobytes())
		meta[pid] = {"scan_id": p.scan_id, "lote": p.lote, "n_no_lote": p.n_no_lote, "origem_px": [int(x0), int(y0)],
					 "tamanho_px": [int(x1 - x0), int(y1 - y0)], "margem_px": int(m), "margem_mm": OV.MARGIN_MM,
					 "mm_por_px": float(render._scan_mmpp(pr, p.scan_id))}
		print(pid, meta[pid])
	with open(os.path.join(a.out, "recortes.json"), "w", encoding="utf-8") as f:
		json.dump({"fonte": "overrides.crop_window + overrides.load_scan_rgb (o recorte do editor de contornos)",
				   "pecas": meta}, f, ensure_ascii=False, indent=1)
	return 0


if __name__ == "__main__":
	sys.exit(main())
