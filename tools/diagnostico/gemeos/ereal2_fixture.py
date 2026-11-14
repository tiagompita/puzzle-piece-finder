"""Gera ``tests/data/ereal2_memoria.npz``: a memória do E-real-2 (188 soltas) usada por ``tests/test_twin_real.py``.

Uso (a partir da raiz do repositório)::

	python tools/diagnostico/gemeos/ereal2_fixture.py [--work PASTA] [--out tests/data/ereal2_memoria.npz]

Sem ``PPF_SCRATCH`` nem pickles de sessões antigas: numa pasta de trabalho temporária (``--work``, por omissão uma
pasta nova em ``%TEMP%``) faz o pool E-sym da variante «scan» (``esym.scan_pieces`` + ``esym.prep`` de A1 e B2, a única
chave de ``esym.pkl`` que ``ereal.esym_pool`` lê) e chama ``ereal2.build_memory(force=True)`` (``segment_scan`` nas
folhas BE, céu f1p1/f1p2/f2p1/f2p2, BD e E-sym). Do resultado guarda só o que o teste lê, por peça: ``lab``, ``src``,
``ok``, ``cell``, o contorno (px do scan, inteiro: 1.º ponto + passos int8, ≈ 50 KB) e o caminho da folha relativo à raiz do
repositório. :func:`load` (usada pelo teste) refaz os contornos.

Não escreve em ``docs/`` nem em ``projects/``. Refazer quando ``segment_scan`` mudar (o teste compara números medidos
com esta memória; se a segmentação mudar, a memória antiga continua a testar ``src.twin`` com os contornos antigos).
"""
import argparse
import os
import sys
import tempfile
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
GROUPS = ("BE", "CEU", "BD", "ES")


def build(work: str) -> dict:
	os.environ["PPF_SCRATCH"] = work           # antes de importar segcache (lê-o ao importar)
	sys.path.insert(0, HERE)
	import pickle

	import segcache as sc  # noqa: E402
	import esym as es  # noqa: E402
	scn = {name: es.prep(es.scan_pieces(os.path.join(sc.REPO, sc.SCANS[name]))) for name in ("A1", "B2")}
	os.makedirs(os.path.join(work, "gemeos"), exist_ok=True)
	with open(os.path.join(work, "gemeos", "esym.pkl"), "wb") as f:
		pickle.dump({"scan": scn}, f)
	import ereal2  # noqa: E402
	return ereal2.build_memory(True)


def export(D: dict, out: str) -> dict:
	rows, contours = [], []
	for g in GROUPS:
		for p in D[g]:
			img = os.path.relpath(os.path.abspath(p["img"]), REPO).replace("\\", "/")
			assert not img.startswith(".."), img
			cell = p.get("cell")
			rows.append((g, str(p["lab"]), str(p["src"]), bool(p.get("ok", True)), img,
						 -1 if cell is None else int(cell[0]), -1 if cell is None else int(cell[1])))
			contours.append(np.asarray(p["contour"], np.float64).reshape(-1, 2))
	lens = np.array([len(c) for c in contours], np.int32)
	allc = np.concatenate(contours, 0)
	assert np.array_equal(allc, np.round(allc)), "contornos não inteiros: o formato delta não serve"
	allc = allc.astype(np.int32)
	start = np.r_[0, np.cumsum(lens)[:-1]]
	step = np.diff(allc, axis=0, prepend=allc[:1])
	step = np.delete(step, start, axis=0)       # passos dentro de cada contorno (findContours: |passo| <= 1 px)
	assert np.abs(step).max() <= 127
	np.savez_compressed(out, grupo=np.array([r[0] for r in rows]), lab=np.array([r[1] for r in rows]),
						src=np.array([r[2] for r in rows]), ok=np.array([r[3] for r in rows]),
						img=np.array([r[4] for r in rows]), cell=np.array([[r[5], r[6]] for r in rows], np.int32),
						n=lens, first=allc[start].astype(np.int32), step=step.astype(np.int8))
	return {g: sum(r[0] == g for r in rows) for g in GROUPS}


def load(path: str) -> dict:
	"""``{grupo: [{lab, src, ok, img (relativo à raiz), cell (tuple | None), contour (N x 2 float64)}]}`` do ficheiro."""
	d = np.load(path)
	n, first, step = d["n"], d["first"].astype(np.int64), d["step"].astype(np.int64)
	out = {g: [] for g in GROUPS}
	k = 0
	for i in range(len(n)):
		m = int(n[i])
		c = np.cumsum(np.vstack([first[i:i + 1], step[k:k + m - 1]]), axis=0).astype(np.float64)
		k += m - 1
		cell = tuple(int(v) for v in d["cell"][i]) if d["cell"][i][0] >= 0 else None
		out[str(d["grupo"][i])].append(dict(lab=str(d["lab"][i]), src=str(d["src"][i]), ok=bool(d["ok"][i]),
											img=str(d["img"][i]), cell=cell, contour=c))
	return out


def main(argv=None) -> int:
	ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	ap.add_argument("--work", default=None, help="pasta de trabalho (por omissão uma pasta nova em %%TEMP%%)")
	ap.add_argument("--out", default=os.path.join(REPO, "tests", "data", "ereal2_memoria.npz"))
	a = ap.parse_args(argv)
	work = a.work or tempfile.mkdtemp(prefix="ereal2_fixture_")
	t0 = time.time()
	D = build(work)
	os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
	n = export(D, a.out)
	E = load(a.out)
	for g in GROUPS:                # ida e volta exata
		for p, q in zip(D[g], E[g]):
			assert np.array_equal(np.asarray(p["contour"], np.float64).reshape(-1, 2), q["contour"]) and q["lab"] == str(p["lab"])
	print(f"memória: {n} -> {a.out} ({os.path.getsize(a.out) / 1024:.0f} KB, {time.time() - t0:.0f} s; trabalho em {work})")
	return 0


if __name__ == "__main__":
	sys.exit(main())
