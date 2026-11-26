"""Verificação determinística do projeto: ``python -m tools.verify`` (docs/prompts/2026-11-26-verificacao-*.md).

* passo 0 (:mod:`tools.verify.ambiente`): ``.venv``, OpenCV fixado, ``core.hooksPath``, HEAD e ``git status`` no início
  e no fim, vigilância (``pieces``/``overlays`` contra ``scans/*.json`` do projeto real, só contagem), hashes do golden;
* golden (:mod:`tools.verify.golden`): manifesto de hashes ``tests/golden/manifesto.json`` sobre os scans já no git;
* regras absolutas (:mod:`tools.verify.invariantes`), 0 violações, sobre uma CÓPIA do projeto vivo;
* métricas das peças do golden (:mod:`tools.verify.metricas`) contra ``tests/golden/baseline.json`` com os limiares
  fixos de ``tests/golden/limiares.json``.

Nunca escreve no projeto real: tudo corre sobre uma cópia temporária feita e apagada com
``tools/diagnostico/gui/guarda.py``."""
