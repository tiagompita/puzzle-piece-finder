"""Marca do índice de que ``quadrados_17.json`` depende (F1c, pedido do Tiago de 2026-11-14).

Os lados (``lado``, ``lado_por_direcao``, ``rot``) do JSON são índices em ``Project.shape(pid).sides`` do índice de
2026-11-10: uma re-segmentação posterior de uma das 62 peças pode renumerá-los. A marca guarda, por peça, o que o
LOG diz da forma (os campos estáticos que ``piece_resegmented`` muda e que :func:`src.render.stale_assets` compara do
lado do log: ``cls``, ``chords_mm``, ``area_mm2``, ``bbox``) num sha1, mais o número de eventos ``piece_resegmented``
dessa peça e o comprimento do log de referência. Escolhido o log e não o contorno do ``npz`` porque o log viaja com o
git e o ``npz`` não (``pieces/`` é ignorado): a marca confere-se em qualquer checkout. ``tests/test_quadrados_json.py``
avisa (``warnings.warn``, não falha) quando uma peça mudou desde a marca.

uso: python quadrados_marca.py <projeto> [<quadrados_17.json>]   (só lê o projeto; reescreve a secção
``marca_indice`` do JSON)
"""
import datetime
import hashlib
import io
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
JS = os.path.join(REPO, "docs", "diagnostico", "grupos_soltos", "quadrados_17.json")
CAMPOS = ("cls", "chords_mm", "area_mm2", "bbox")


def _r(v):
	if isinstance(v, float):
		return round(v, 3)
	if isinstance(v, (list, tuple)):
		return [_r(x) for x in v]
	return v


def assinatura(piece) -> str:
	"""sha1 (12 hex) dos campos de forma da peça no log (arredondados a 0,001)."""
	d = {k: _r(getattr(piece, k, None)) for k in CAMPOS}
	return hashlib.sha1(json.dumps(d, sort_keys=True, ensure_ascii=True).encode("ascii")).hexdigest()[:12]


def n_resegmentacoes(events: list, pid: str) -> int:
	return sum(1 for e in events if e.get("action") == "piece_resegmented" and e.get("piece") == pid)


def marca(pr, pids) -> dict:
	"""``{log_eventos, campos, pecas: {pid: {assinatura, n_resegmentacoes}}}`` do projeto aberto ``pr``."""
	evs = pr.events()
	return {"log_eventos": len(evs), "campos": list(CAMPOS),
			"pecas": {pid: {"assinatura": assinatura(pr.piece(pid)), "n_resegmentacoes": n_resegmentacoes(evs, pid)}
					  for pid in sorted(pids)}}


def diferencas(ref: dict, pr) -> list:
	"""Peças da marca ``ref`` que mudaram em ``pr``: ``[(pid, motivo)]``."""
	evs = pr.events()
	out = []
	for pid, m in sorted(ref["pecas"].items()):
		if pid not in pr.pieces:
			out.append((pid, "não existe no projeto"))
			continue
		n = n_resegmentacoes(evs, pid)
		if n != m["n_resegmentacoes"]:
			out.append((pid, f"re-segmentada ({m['n_resegmentacoes']} → {n} eventos piece_resegmented)"))
		elif assinatura(pr.piece(pid)) != m["assinatura"]:
			out.append((pid, "forma no log diferente (cls / cordas / área / bbox)"))
	return out


def main(argv):
	from src.state import Project
	sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
	proj = argv[1]
	js = argv[2] if len(argv) > 2 else JS
	with open(js, encoding="utf-8") as f:
		data = json.load(f)
	pr = Project.open(proj)
	pids = {q["peca"] for g in data["grupos"] for q in g["pecas"]}
	m = marca(pr, pids)
	m["gerada_em"] = datetime.date.today().isoformat()
	m["gerada_por"] = "tools/diagnostico/grupos_soltos/quadrados_marca.py"
	m["nota"] = ("assinatura = sha1 (12 hex) de cls, chords_mm, area_mm2 e bbox da peça no log (arredondados a 0,001); "
				 "n_resegmentacoes = eventos piece_resegmented da peça até log_eventos. O teste avisa se mudarem.")
	data["marca_indice"] = m
	with open(js, "w", encoding="utf-8", newline="\n") as f:
		json.dump(data, f, ensure_ascii=False, indent=1)
		f.write("\n")
	print(f"{len(m['pecas'])} peças, log com {m['log_eventos']} eventos; "
		  f"re-segmentadas alguma vez: {sum(1 for v in m['pecas'].values() if v['n_resegmentacoes'])}")


if __name__ == "__main__":
	main(sys.argv)
