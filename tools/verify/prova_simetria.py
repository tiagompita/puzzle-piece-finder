"""Imagens de prova dos pares gémeos (4.2): peça e gémea alinhada (rotação + deslocamento de ``shape.free_dist``, que
num par rot180 é a gémea rodada 180° no tabuleiro), lado a lado, com os dois contornos sobrepostos.

``python -m tools.verify.prova_simetria [--project projects/alpes] [--out docs/diagnostico/verify/simetria]
[--pares P0140|P0499 ...]`` (por omissão: a lista «por rever» de ``tests/golden/simetria_por_rever.json`` + um par da
exceção c32|c33 e o par de menor ``nn_max`` como referência). Corre sobre uma cópia; só escreve JPEG em ``--out``.

Painéis (20 px/mm, janela de 30 mm à volta do centro): (1) a peça, (2) a gémea alinhada à peça, (3) os dois contornos
(verde = peça, magenta = gémea alinhada) com o ponto de ``nn_max`` marcado (círculo amarelo) e os pontos da peça a
mais de ``TWIN_LOCAL_MAX_MM`` da gémea a vermelho."""
import argparse
import json
import os
import sys

import cv2
import numpy as np

from tools.verify import ambiente as AMB

__all__ = ["painel_par", "main"]

PX_MM = 20.0
JANELA_MM = 30.0


def _media_z(contour_px, mm: float) -> complex:
	"""Centro que :func:`src.shape._free_vec` subtrai (média dos ``N_FREE`` pontos do contorno alisado, em mm)."""
	from src import shape as SH
	c = np.asarray(contour_px, float).reshape(-1, 2) * mm
	z = SH._resample_closed(SH._smooth_closed(c, SH.FREE_SMOOTH_SIGMA), SH.N_FREE)
	m = z.mean(0)
	return complex(m[0], m[1]) if np.ndim(m) else complex(m)


def _contorno(pr, pid):
	p = pr.piece(pid)
	with np.load(pr.p("pieces", f"{p.scan_id}.npz"), allow_pickle=False) as z:
		return z[f"{pid}__contour_px"].astype(float).reshape(-1, 2)


def _warp(rgb, mm, centro: complex, rot: complex) -> np.ndarray:
	"""Imagem no referencial da peça: ponto ``u`` (mm, centro da janela = 0) ← píxel ``(u · rot⁻¹ + centro) / mm``."""
	n = int(JANELA_MM * PX_MM)
	ys, xs = np.mgrid[0:n, 0:n].astype(np.float32)
	u = ((xs - n / 2) + 1j * (ys - n / 2)) / PX_MM
	w = u / rot + centro
	mx = (w.real / mm).astype(np.float32)
	my = (w.imag / mm).astype(np.float32)
	return cv2.remap(rgb, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))


def _pts(z) -> np.ndarray:
	n = int(JANELA_MM * PX_MM)
	return np.stack([z.real * PX_MM + n / 2, z.imag * PX_MM + n / 2], 1).round().astype(np.int32).reshape(-1, 1, 2)


def painel_par(pr, a: str, b: str, rgb_cache: dict) -> tuple:
	"""``(imagem BGR, números)`` do par ``a`` (peça) / ``b`` (gémea alinhada a ``a``)."""
	from src import consistency as CS
	from src import overrides as OV
	from src.shape import free_dist
	sa, sb = pr.shape(a), pr.shape(b)
	rms, s, phi = free_dist(sa, sb)
	rot = np.exp(1j * np.radians(phi))
	za = sa.z
	zb = np.roll(sb.z, -s) * rot
	nn = np.abs(za[:, None] - zb[None, :]).min(1)
	imgs = []
	for pid, r in ((a, 1.0 + 0j), (b, rot)):
		p = pr.piece(pid)
		rgb = rgb_cache.get(p.scan_id)
		if rgb is None:
			rgb = rgb_cache[p.scan_id] = OV.load_scan_rgb(pr, p.scan_id)
		mm = OV._mmpp(pr, p.scan_id)
		imgs.append(_warp(rgb, mm, _media_z(_contorno(pr, pid), mm), r))
	n = imgs[0].shape[0]
	pa, pb = _pts(za), _pts(zb)
	out = []
	for k, im in enumerate(imgs):
		im = cv2.cvtColor(im, cv2.COLOR_RGB2BGR)
		cv2.polylines(im, [pa], True, (0, 200, 0), 1, cv2.LINE_AA)
		cv2.polylines(im, [pb], True, (200, 0, 200), 1, cv2.LINE_AA)
		out.append(im)
	ov = np.full((n, n, 3), 255, np.uint8)
	cv2.polylines(ov, [pa], True, (0, 160, 0), 2, cv2.LINE_AA)
	cv2.polylines(ov, [pb], True, (200, 0, 200), 2, cv2.LINE_AA)
	for i in np.nonzero(nn > CS.TWIN_LOCAL_MAX_MM)[0]:
		cv2.circle(ov, tuple(int(v) for v in pa[i, 0]), 2, (0, 0, 255), -1)
	im_ = int(np.argmax(nn))
	cv2.circle(ov, tuple(int(v) for v in pa[im_, 0]), 9, (0, 200, 255), 2)
	out.append(ov)
	pa_, pb_ = pr.piece(a), pr.piece(b)
	num = {"a": a, "ca": list(pa_.celula), "b": b, "cb": list(pb_.celula), "rms_mm": round(float(rms), 3),
		   "nn_p95_mm": round(float(np.percentile(nn, 95)), 3), "nn_max_mm": round(float(nn.max()), 3),
		   "pontos_acima_limiar": int((nn > CS.TWIN_LOCAL_MAX_MM).sum()), "limiar_mm": CS.TWIN_LOCAL_MAX_MM,
		   "phi_deg": round(float(phi), 1), "cls": [pa_.cls, pb_.cls],
		   "excecao": CS.twin_exception(pr.profile, pa_.celula) or CS.twin_exception(pr.profile, pb_.celula)}
	cab = np.full((70, 3 * n + 20, 3), 255, np.uint8)
	t1 = f"{a} ({num['ca'][0]},{num['ca'][1]}) {pa_.cls}  |  gemea {b} ({num['cb'][0]},{num['cb'][1]}) {pb_.cls}, alinhada (rot {num['phi_deg']} graus)"
	t2 = (f"RMS {num['rms_mm']} mm   nn_p95 {num['nn_p95_mm']} mm   nn_max {num['nn_max_mm']} mm (limiar {CS.TWIN_LOCAL_MAX_MM})"
		  f"   verde = peca, magenta = gemea" + ("   [na excecao do perfil]" if num["excecao"] else ""))
	cv2.putText(cab, t1, (8, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)
	cv2.putText(cab, t2, (8, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)
	sep = np.full((n, 10, 3), 255, np.uint8)
	corpo = np.hstack([out[0], sep, out[1], sep, out[2]])
	return np.vstack([cab, corpo]), num


def main(argv=None) -> int:
	from tools.verify import invariantes as INV
	from src.state import Project
	ap = argparse.ArgumentParser(prog="python -m tools.verify.prova_simetria", description=__doc__.splitlines()[0])
	ap.add_argument("--project", default=os.path.join("projects", "alpes"))
	ap.add_argument("--out", default=os.path.join("docs", "diagnostico", "verify", "simetria"))
	ap.add_argument("--pares", nargs="*", default=None)
	args = ap.parse_args(argv)
	proj = os.path.join(AMB.REPO, args.project) if not os.path.isabs(args.project) else args.project
	out = os.path.join(AMB.REPO, args.out) if not os.path.isabs(args.out) else args.out
	os.makedirs(out, exist_ok=True)
	raiz, copia = AMB.copiar_projeto(proj)
	try:
		pr = Project.open(copia)
		if args.pares:
			pares = [x.split("|") for x in args.pares]
		else:
			with open(os.path.join(AMB.REPO, "tests", "golden", "simetria_por_rever.json"), encoding="utf-8") as f:
				pares = [x.split("|") for x in json.load(f)["pares"]]
			todos = [x for x in INV.pares_gemeos(pr) if x["r"] is not None]
			exc = sorted((x for x in todos if x["excecao"]), key=lambda x: -x["r"]["nn_max_mm"])
			if exc:
				pares.append([exc[0]["a"], exc[0]["b"]])
			ref = min(todos, key=lambda x: x["r"]["nn_max_mm"])
			pares.append([ref["a"], ref["b"]])
		cache, nums = {}, []
		for a, b in pares:
			img, num = painel_par(pr, a, b, cache)
			fp = os.path.join(out, f"{a}_{b}.jpg")
			cv2.imwrite(fp, img, [cv2.IMWRITE_JPEG_QUALITY, 88])
			num["imagem"] = os.path.relpath(fp, AMB.REPO).replace(os.sep, "/")
			nums.append(num)
			print(json.dumps(num, ensure_ascii=False))
		with open(os.path.join(out, "numeros.json"), "w", encoding="utf-8", newline="\n") as f:
			json.dump(nums, f, ensure_ascii=False, indent=1)
	finally:
		AMB.apagar_copia(raiz)
	return 0


if __name__ == "__main__":
	sys.exit(main())
