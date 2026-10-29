import numpy as np, cv2
from shapelib import MM, NS, shape_dist


def free_dist(a, b):
	"""Corner-free: min over cyclic start shift and rotation of RMS (mm) between arclength-resampled contours."""
	za, zb = a['z'], b['z']
	corr = np.fft.ifft(np.conj(np.fft.fft(za)) * np.fft.fft(zb))  # sum_i conj(a_i) b_{i+s}
	ea = np.sum(np.abs(za) ** 2); eb = np.sum(np.abs(zb) ** 2)
	m = np.abs(corr); s = int(np.argmax(m))
	rms2 = (ea + eb - 2 * m[s]) / len(za)
	return float(np.sqrt(max(rms2, 0))) * MM, s, -np.angle(corr[s])


def aligned_b(a, b):
	d, s, phi = free_dist(a, b)
	zb = np.roll(b['z'], -s) * np.exp(1j * phi)
	return a['z'], zb, d


def hu(a, b):
	return cv2.matchShapes(a['hu_c'], b['hu_c'], cv2.CONTOURS_MATCH_I1, 0)


def corner_dist(a, b):
	return shape_dist(a, b)[0]


def mat(PA, PB, f):
	M = np.zeros((len(PA), len(PB)))
	for i, a in enumerate(PA):
		for j, b in enumerate(PB):
			M[i, j] = f(a, b)
	return M
