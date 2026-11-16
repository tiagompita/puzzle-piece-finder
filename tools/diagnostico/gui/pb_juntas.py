"""P-b correção, passo 0 a): juntas (|gap| de render.seam_gaps) das peças cuja pose muda entre cantos e imagem."""
import sys, os, json, time
import numpy as np
REPO = r"D:\DEKSTOP\puzzle_piece_finder"
sys.path.insert(0, REPO)
from src.state import Project
from src import render
from src.locate import CellArt

d = sys.argv[1]
pr = Project.open(d)
stored = render.load_placements(pr)["placements"]
ids = render.placed_ids(pr)
art = CellArt.load(pr.profile, render.REPO)
t0 = time.time()
valid = {pid for pid in ids if pid in stored and stored[pid].get("key") == render._entry_key(pr, pid)
		 and render._manual_entry_ok(pr, pid, stored[pid])}
cant, img = {}, {}
for pid in ids:
	cant[pid] = render.register_piece(pr, pid, art=None, image=False)
	img[pid] = render.register_piece(pr, pid, art=art, image=True)
print("registo", round(time.time() - t0, 1), "s; válidas", len(valid), "sem", len(ids) - len(valid))
hoje = {pid: (stored[pid] if pid in valid else cant[pid]) for pid in ids}

def differs(a, b):
	return (abs(float(render.wrap_deg(a["theta_deg"] - b["theta_deg"]))) > 1e-9 or abs(a["dx_mm"] - b["dx_mm"]) > 1e-9
			or abs(a["dy_mm"] - b["dy_mm"]) > 1e-9)

S24 = sorted(pid for pid in ids if pid not in valid and differs(cant[pid], img[pid]))
S79 = sorted(pid for pid in valid if not stored[pid].get("manual") and differs(cant[pid], stored[pid]))
print("24:", len(S24), S24)
print("79 que mudam para cantos:", len(S79), S79)
shapes = {}

def stats(pl, S):
	gs = [g for g in render.seam_gaps(pr, pl, shapes=shapes) if g["a"] in S or g["b"] in S]
	v = np.abs([g["gap_mm"] for g in gs])
	if not len(v):
		return {"n_juntas": 0}, {}
	return {"n_juntas": len(gs), "med": round(float(np.median(v)), 3), "p95": round(float(np.percentile(v, 95)), 3),
			"max": round(float(v.max()), 3), "frac_gt_0.8": round(float(np.mean(v > 0.8)), 3)}, {(g["a"], g["b"]): g["gap_mm"] for g in gs}

out = {}
for nome, S, alt in (("24", set(S24), img), ("79", set(S79), cant)):
	A = dict(hoje)                                  # hoje (24 cantos / 79 imagem)
	B = dict(hoje); B.update({p: alt[p] for p in S})
	sa, ga = stats(A, S)
	sb, gb = stats(B, S)
	dif = [abs(gb[k]) - abs(ga[k]) for k in ga if k in gb]
	out[nome] = {"pecas": sorted(S), "hoje": sa, "alternativa": sb,
				 "por_junta_melhora": int(sum(x < -1e-6 for x in dif)), "por_junta_piora": int(sum(x > 1e-6 for x in dif))}
	print(nome, "hoje", sa, "| alternativa", sb, "| melhora", out[nome]["por_junta_melhora"], "piora", out[nome]["por_junta_piora"])
# contexto: tabuleiro inteiro, tudo cantos vs tudo imagem (sem manual: as manuais ficam iguais)
allc = {p: (stored[p] if p in valid and stored[p].get("manual") else cant[p]) for p in ids}
alli = {p: (stored[p] if p in valid and stored[p].get("manual") else img[p]) for p in ids}
for nome, pl in (("todas_cantos", allc), ("todas_imagem", alli)):
	v = np.abs([g["gap_mm"] for g in render.seam_gaps(pr, pl, shapes=shapes)])
	out[nome] = {"n": len(v), "med": round(float(np.median(v)), 3), "p95": round(float(np.percentile(v, 95)), 3)}
	print(nome, out[nome])
json.dump(out, open(os.path.join(os.path.dirname(__file__), "juntas.json"), "w"), indent=1)
