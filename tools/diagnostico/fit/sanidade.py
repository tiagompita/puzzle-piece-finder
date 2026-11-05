import sys, json, numpy as np
sys.path.insert(0, 'tools/diagnostico/fit')
sys.path.insert(0, '.')
from common import open_project
from src.shape import side_complement
R = json.load(open('docs/diagnostico/fit/resultados.json', encoding='utf-8'))
pr = open_project()
rows = R['results']
direct, mapped, prov = [], [], []
for r in rows:
    q = r['q']
    a, b = pr.shape(q['a']), pr.shape(q['b'])
    rms, dl = side_complement(a.sides[q['side_a']], b.sides[q['side_b']])
    direct.append(rms)
    mapped.append(r.get('true_rms'))
    prov.append('bd' if any(p in ('b', 'd') for p in q['prov']) else 'a')
direct = np.array(direct, float)
mapped = np.array([np.nan if m is None else m for m in mapped], float)
prov = np.array(prov)
print('direct vs mapped: |diff|>0.05 in', int(np.sum(np.abs(direct - mapped) > 0.05)), 'of', len(rows))
for pv in ('bd', 'a'):
    m = prov == pv
    print(pv, 'direct rms pct 10/50/90:', np.percentile(direct[m], [10, 50, 90]).round(2), ' mapped:', np.nanpercentile(mapped[m], [10, 50, 90]).round(2))
# aleatórios T-B das mesmas peças (linha de base)
rng = np.random.default_rng(0)
vals = []
for r in rows[:300]:
    q = r['q']
    a = pr.shape(q['a'])
    other = rows[rng.integers(len(rows))]['q']
    b = pr.shape(other['b'])
    rms, dl = side_complement(a.sides[q['side_a']], b.sides[other['side_b']])
    if np.isfinite(rms):
        vals.append(rms)
print('aleatório T-B (mesmos tipos compatíveis) pct 10/50/90:', np.percentile(vals, [10, 50, 90]).round(2), len(vals))
tr = np.array([r.get('true_dl', np.nan) for r in rows], float)
print('true |dL| pct 50/90/max', np.nanpercentile(tr, [50, 90]).round(2), np.nanmax(tr).round(2))
print('rank e4 mediana', np.median([r['e4_lenient'] for r in rows if r['e4_lenient']]), ' e5 mediana', np.median([r['e5_lenient'] for r in rows if r['e5_lenient']]))
print('verdadeiro com RMS < 1.0:', float(np.mean(direct < 1.0)).__round__(3), ' < 0.8', float(np.mean(direct < 0.8)).__round__(3))
