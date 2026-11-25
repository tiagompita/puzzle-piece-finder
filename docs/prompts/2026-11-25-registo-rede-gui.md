# 2026-11-25 — registo de rede das páginas nos testes de GUI

## Porquê
20 corridas de `tests/test_gui*.py` tiveram 7 falhas intermitentes (scripts em falta, `data-ready` a 60 s, `ERR_NO_BUFFER_SPACE`, 1 asserção). Hipótese [NT]: esgotamento de buffers do loopback do Windows.

## Decisões
«Sim, regista»: o conftest regista os pedidos falhados por página e imprime-os quando um teste falha; depois 10 corridas; correção só proposta.

## Prompt verbatim
Ver o pedido da ronda (agente helper): registar `requestfailed`, HTTP >= 400, `pageerror`/`console` de erro por página no conftest e anexá-los ao relatório de falhas; teste do registo; suite completa verde e commit; 10 corridas de `tests/test_gui*.py` com saída em ficheiro, mostrar o que o registo apanhou em cada falha; sem correção; registar em decisoes, HANDOFF e este ficheiro.

## Resultado
Relatório final (palavra por palavra):

**Commit:** `13a1d95` (conftest, `pytest.ini`, `tests/test_net_log.py`) e o commit dos documentos desta ronda. Sem push.

**Ficheiros alterados:** `tests/conftest.py`, `pytest.ini`, `tests/test_net_log.py`, `docs/decisoes.md`, `docs/HANDOFF.md`, este ficheiro.

**Registo [V]:** fixture autouse `_net_log` embrulha `Browser.new_page` e `BrowserContext.new_page` e liga `requestfailed`, `response` (>= 400), `pageerror`, `console` (error); `pytest_runtest_makereport` junta a lista à secção «Registo de rede das paginas» quando falha setup, call ou teardown. Teste verde: nada. Sem repetições nem esperas. `tests/test_net_log.py`: um teste com `page.route` a abortar um script (aparece `requestfailed GET .../x.js` com `net::ERR_FAILED`) e um com pytester em subprocesso (secção impressa uma vez, só no teste que falha). `pytest.ini` com `addopts = -p pytester`.

**Suite completa [V]:** 1.ª corrida 909 passed, 1 skipped, 1 erro de teardown (`tests/test_gui_suspeitas.py::test_suspeitas_block_filter_and_locate`: `assert errs == []` com `Failed to load resource: net::ERR_NO_BUFFER_SPACE`; o registo ainda só cobria setup/call, estendido a teardown). 2.ª corrida, código final: 909 passed, 1 skipped, 16 min 3 s.

**Vigilância [V]:** `projects/alpes/pieces` 39 e `overlays` 39 no início, a meio e no fim; `git status` limpo depois do commit do código.

**10 corridas [V]** (`...\scratchpad\gui10b\run01.log` … `run10.log`, `summary.txt`): 10 × 316 passed (≈ 9 min 48 s a 10 min 10 s), 0 falhas. Não houve nenhuma falha para o registo analisar: não se sabe, portanto, se há `requestfailed` num script. A hipótese do loopback continua [NT]. Única evidência nova: o erro de teardown acima, `ERR_NO_BUFFER_SPACE` num recurso (sem URL no texto do `console`; a lista da fixture não o tem), que mostra o erro do Windows também fora de um `goto`.

**Proposta (não implementada):** deixar o registo ligado e esperar a próxima falha; só com um `requestfailed`/`ERR_NO_BUFFER_SPACE` num script, repetir o `goto` uma vez nas fixtures ou reduzir servidores/páginas abertos.

**Decisões pendentes:** (1) manter o registo ligado e esperar mais suites completas, ou repetir o `goto` já; (2) o erro de teardown de `test_gui_suspeitas.py` vem de uma fixture própria com `errs`, fora do registo comum: aceitar assim.
