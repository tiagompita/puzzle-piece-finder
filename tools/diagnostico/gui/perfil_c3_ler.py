"""Lê a saída de ``perfil_c3.py``: a linha do tempo de um «Encaixa» (ms desde o início do POST, servidor + browser) e,
para todas as corridas, os segmentos do caminho até ao detalhe (mediana e máximo).

Uso: ``python tools/diagnostico/gui/perfil_c3_ler.py <saída.json> [--tipo longe|perto] [--corrida K] [--segmentos]``."""
import argparse
import json
import statistics

SKIP_SRV = {"cede à GUI"}


def events(e):
	"""Merged list ``(ms, lado, texto)`` relative to the start of the POST."""
	t0 = e["t_post_b"]
	out = []
	for r in e["servidor"]:
		ev, ph = r["ev"], r.get("ph")
		if ev == "HTTP" and "/api/events" in r.get("path", ""):
			continue
		extra = {k: v for k, v in r.items() if k not in ("t", "th", "ev", "ph", "t0", "dur", "ok")}
		dur = r.get("dur")
		if ph == "x":
			out.append(((r["t0"] - t0) * 1000, "srv", f"[{r['th']}] {ev} {dur * 1000:.0f} ms"))
		elif ph == "b":
			continue
		elif ph == "e":
			start = (r["t"] - dur - t0) * 1000
			out.append((start, "srv", f"[{r['th']}] {ev} {extra} → {dur * 1000:.0f} ms" + ("" if r.get("ok", True) else " ERRO")))
		else:
			out.append(((r["t"] - t0) * 1000, "srv", f"[{r['th']}] {ev} {extra}"))
	b = e["browser"]
	for r in b["tl"]:
		x = {k: v for k, v in r.items() if k not in ("t", "ev")}
		out.append((r["t"] - t0 * 1000, "nav", f"{r['ev']} {x}"))
	for r in b["res"]:
		if "/api/events" in r["url"]:
			continue
		u = r["url"].split("127.0.0.1:8796")[-1]
		out.append((r["b"] - t0 * 1000, "nav", f"recurso {r['kind']} {u} → início resposta {r['resp0'] - r['b']:.0f} ms, fim {r['e'] - r['b']:.0f} ms"))
	out.append(((e["t_post_e"] - t0) * 1000, "cli", "POST respondido (cliente)"))
	out.append(((e["t_shown"] - t0) * 1000, "cli", "DETALHE NO ECRÃ"))
	return sorted(out, key=lambda x: x[0])


def segs(e):
	"""Key moments (ms from the POST end) of the path to the detail."""
	tp = e["t_post_e"]
	tl = e["browser"]["tl"]
	srv = e["servidor"]

	def first_nav(pred):
		for r in tl:
			if r["t"] / 1000 >= e["t_post_b"] and pred(r):
				return (r["t"] / 1000 - tp) * 1000
		return None
	d = {}
	d["sse board_changed recebido"] = first_nav(lambda r: r["ev"] == "sse recebido" and r.get("name") == "board_changed")
	d["loadBoard início"] = first_nav(lambda r: r["ev"] == "loadBoard b")
	d["loadBoard fim"] = first_nav(lambda r: r["ev"] == "loadBoard e")
	d["loadMontar fim"] = first_nav(lambda r: r["ev"] == "loadMontar e")
	d["pedido do detalhe (fetch)"] = first_nav(lambda r: r["ev"] == "fetch b" and "region=" in r.get("url", "") and "ppc=" in r["url"])
	d["detalhe: resposta"] = first_nav(lambda r: r["ev"] == "fetch h" and "region=" in r.get("url", ""))
	d["detalhe no ecrã"] = (e["t_shown"] - tp) * 1000
	rj = [r for r in srv if r["ev"] == "_region_jpg" and r.get("ph") == "e" and r["t"] >= e["t_post_b"]]
	if rj:
		j = rj[0]
		jb = j["t"] - j["dur"]
		d["servidor: _region_jpg (dur)"] = j["dur"] * 1000
		d["servidor: _region_jpg início"] = (jb - tp) * 1000
		comp = [r for r in srv if r["ev"] == "_compose" and r.get("ph") == "e" and r["th"] == j["th"] and jb <= r["t"] <= j["t"]]
		if comp:
			c = comp[0]
			d["servidor: compor região (dur)"] = c["dur"] * 1000
			misses = [r for r in srv if r["ev"] == "piece_ready (falha E)" and r.get("ph") == "e" and r["th"] == c["th"]
					  and c["t"] - c["dur"] <= r["t"] <= c["t"]]
			d["servidor: falhas E durante a composição"] = len(misses)
			d["servidor: ms em falhas E"] = sum(r["dur"] for r in misses) * 1000
	for path in ("/api/board?ui=novo", "/api/ghosts", "/api/montar"):
		h = [r for r in srv if r["ev"] == "HTTP" and r.get("ph") == "e" and r.get("path") == path and r["t"] >= e["t_post_e"]]
		if h:
			d[f"servidor: {path} (dur)"] = h[0]["dur"] * 1000
	for name, ev in (("ranking", "fit.rank_all"), ("suspeitas", "consistency.evaluate"), ("pré-aquecimento", "_prewarm")):
		ends = [r for r in srv if r["ev"] == ev and r.get("ph") == "e"]
		if ends:
			r = ends[0]
			d[f"{name}: início"] = (r["t"] - r["dur"] - tp) * 1000
			d[f"{name}: fim"] = (r["t"] - tp) * 1000
	ced = [r for r in srv if r["ev"] == "cede à GUI"]
	d["esperas de fundo pela GUI (n)"] = len(ced)
	d["esperas de fundo pela GUI (ms)"] = sum(r["dur"] for r in ced) * 1000
	d["E forget (n)"] = sum(1 for r in srv if r["ev"] == "E forget")
	d["E clear (n)"] = sum(1 for r in srv if r["ev"] == "E clear")
	return d


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("path")
	ap.add_argument("--tipo", default="longe")
	ap.add_argument("--corrida", type=int, default=None)
	ap.add_argument("--segmentos", action="store_true")
	a = ap.parse_args()
	runs = json.load(open(a.path, encoding="utf-8"))["corridas"]
	if a.corrida is not None:
		e = runs[a.corrida - 1][f"encaixa_{a.tipo}"]
		for ms, side, txt in events(e):
			print(f"{ms:8.0f}  {side}  {txt[:220]}")
	if a.segmentos or a.corrida is None:
		rows = [segs(r[f"encaixa_{a.tipo}"]) for r in runs]
		keys = list(dict.fromkeys(k for r in rows for k in r))
		print(f"{a.tipo}: {len(rows)} corridas (ms desde o fim do POST; mediana · máximo · todas)")
		for k in keys:
			v = [r.get(k) for r in rows]
			w = [x for x in v if x is not None]
			if not w:
				print(f"  {k:45s} —")
				continue
			print(f"  {k:45s} {statistics.median(w):8.0f} · {max(w):8.0f}   {[None if x is None else round(x) for x in v]}")


if __name__ == "__main__":
	main()
