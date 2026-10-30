"""Verificação rápida (preliminar) dos gémeos por rotação de 180°.

Uso: python tools/diagnostico/gemeos_quick.py A1.jpg A2.jpg B.jpg
  A1, A2: mesma folha A (A2 = cada peça rodada 180° na sua casa) -> ruído de re-scan
  B     : folha B (gémeos da borda de baixo)
Segmenta por distância Lab ao fundo verde, ordena as peças em 4 filas de 5 e compara
contornos com RMS mínimo sobre deslocamento cíclico e rotação (métrica "free" de
tools/diagnostico/forma, sem suavização). Escrito no Project, não é código de produção.
"""
import sys
import cv2
import numpy as np

MM = 25.4 / 300
N = 512


def desc(c):
	p = c[:, 0, :].astype(float)
	seg = np.sqrt((np.diff(np.vstack([p, p[:1]]), axis=0) ** 2).sum(1))
	s = np.concatenate([[0], np.cumsum(seg)])
	t = np.linspace(0, s[-1], N, endpoint=False)
	x = np.interp(t, s, np.append(p[:, 0], p[0, 0]))
	y = np.interp(t, s, np.append(p[:, 1], p[0, 1]))
	z = (x + 1j * y) * MM
	a = 0.5 * np.sum(z.real * np.roll(z.imag, -1) - np.roll(z.real, -1) * z.imag)
	if a < 0:
		z = z[::-1]
	return z - z.mean()


def pieces(path, cols=5):
	im = cv2.imread(path)
	lab = cv2.cvtColor(im, cv2.COLOR_BGR2LAB).astype(np.float32)
	h, w = lab.shape[:2]
	bg = np.median(lab[h - 300:h - 50, 50:w - 50].reshape(-1, 3), axis=0)
	d = np.sqrt(((lab - bg) ** 2 * np.array([0.5, 1, 1])).sum(-1))
	m = (d > 28).astype(np.uint8) * 255
	m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
	m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
	cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
	cs = [c for c in cs if cv2.contourArea(c) > 20000]
	items = sorted(((cv2.boundingRect(c), c) for c in cs), key=lambda t: t[0][1] + t[0][3] / 2)
	rows = [items[i:i + cols] for i in range(0, len(items), cols)]
	ordered = [c for r in rows for (_, c) in sorted(r, key=lambda t: t[0][0])]
	return [desc(c) for c in ordered]


def dist(z, w):
	c = np.fft.ifft(np.fft.fft(z) * np.conj(np.fft.fft(w)))
	v = (np.sum(np.abs(z) ** 2) + np.sum(np.abs(w) ** 2) - 2 * np.abs(c).max()) / N
	return float(np.sqrt(max(v, 0.0)))


def main(a1, a2, b):
	A1, A2, B = pieces(a1), pieces(a2), pieces(b)
	print("peças:", len(A1), len(A2), len(B))
	self_ = [dist(x, y) for x, y in zip(A1, A2)]
	M = np.array([[dist(x, y) for y in B] for x in A1])
	am = M.argmin(1)
	tw = M[np.arange(len(A1)), am]
	oth = [np.min(np.delete(M[i], am[i])) for i in range(len(A1))]
	print("ruído re-scan (A1 vs A2): mediana %.2f mm, máx %.2f" % (np.median(self_), max(self_)))
	print("casa do gémeo em B para cada casa de A:", am.tolist())
	print("gémeo: mediana %.2f mm, máx %.2f | não-gémeo mais próximo: mediana %.2f, mín %.2f"
		% (np.median(tw), tw.max(), np.median(oth), min(oth)))


if __name__ == "__main__":
	main(*sys.argv[1:4])
