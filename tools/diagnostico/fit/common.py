"""E-fit: carregamento só de leitura do projeto, identidade física das peças, gémeas por forma.

Nada aqui escreve em ``projects/alpes`` nem em ``src/``. Ver ``docs/diagnostico/fit/GT.md``.
"""

import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from src.shape import free_dist  # noqa: E402
from src.state import Project  # noqa: E402

PROJECT = os.path.join(REPO, "projects", "alpes")
DUP_PAGE_SCANS = {"S0021"}          # montado_p13 = montado_p04 digitalizada outra vez (LEGADO.md, [V])
SAME_PIECE_DE = 10.0                # mesmo limiar da src/legacy.py: ΔE médio <= 10 = mesma peça, > 10 = gémea
DIRS = ("N", "E", "S", "W")


def open_project():
    return Project.open(PROJECT)


class Unionfind:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def physical_clusters(pr, pids, t95):
    """Identidade física: ``same_as`` do log + (mesma classe, cordas, free <= t95, ΔE médio <= 10).

    Devolve ``(cluster_of {pid: rep}, extra_pairs)``; ``extra_pairs`` = as ligações que NÃO vinham do ``same_as``
    (para reportar). A gémea (free <= t95 mas ΔE > 10) fica à parte e sai em :func:`twin_clusters`.
    """
    uf = Unionfind()
    for pid in pids:
        uf.find(pid)
        p = pr.piece(pid)
        if p.same_as and p.same_as in pr.pieces:
            uf.union(pid, p.same_as)
    extra = []
    sh = {pid: pr.shape(pid) for pid in pids}
    ok = [pid for pid in pids if sh[pid] is not None and sh[pid].ok]
    labs = {pid: np.asarray(pr.piece(pid).mean_lab, float) if pr.piece(pid).mean_lab is not None else None for pid in ok}
    Z = np.array([sh[pid].z for pid in ok])
    F = np.fft.fft(Z, axis=1)
    n = len(ok)
    for i in range(n):
        corr = np.fft.ifft(np.conj(F[i])[None, :] * F, axis=1)
        m = np.abs(corr).max(1)
        rms2 = (np.sum(np.abs(Z[i]) ** 2) + np.sum(np.abs(Z) ** 2, 1) - 2 * m) / Z.shape[1]
        d = np.sqrt(np.maximum(rms2, 0))
        for j in np.nonzero(d <= t95)[0]:
            if j <= i:
                continue
            a, b = ok[i], ok[j]
            if sh[a].cls != sh[b].cls or labs[a] is None or labs[b] is None:
                continue
            de = float(np.linalg.norm(labs[a] - labs[b]))
            if de <= SAME_PIECE_DE and uf.find(a) != uf.find(b):
                uf.union(a, b)
                extra.append((a, b, float(d[j]), de))
    return {pid: uf.find(pid) for pid in pids}, extra
