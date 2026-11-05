# Ronda 2026-11-05 (2.ª): abas no topo, «Editar report», triagem de reports

*Fechado em 2026-11-05.*

## Porquê
Na GUI, as 6 abas não cabiam na barra lateral e «Reports» ficava fora do ecrã; o Tiago também quer evitar reports duplicados ao clicar numa peça que já tem um, e há 22 reports abertos que a ronda anterior não resolveu.

## Decisões
- Abas na **barra de topo**, junto ao nome/progresso; sem scroll horizontal; 2.ª linha abaixo de 1181 px (à largura de 911 px a linha única fazia as abas cobrir os botões «Fantasmas/Grelha»: apanhado pelo teste), rótulos curtos abaixo de 900 px.
- «Editar report» substitui «Reportar» quando há um report **aberto** da peça (ou da célula, se o report não tem peça). `reports.jsonl` fica **append-only**: editar = acrescentar uma linha de evento `edicao`; `close_report` mantém essas linhas.
- A lista «Guardadas» não colapsa ao re-renderizar (reports, nova lista).
- Triagem: propor, **não fechar** (só o Tiago aprova).

## Prompt (verbatim)
> Lê CLAUDE.md, docs/HANDOFF.md e docs/decisoes.md. Primeiro corre a suite completa em segundo plano (na ronda anterior só se correram 3 testes depois de dividir os ficheiros de teste) e diz-me o resultado. Depois faz a secção "Próxima sessão" do HANDOFF: (1) abas na barra de topo, (2) "Editar report" em vez de "Reportar" quando a peça já tem report, (3) triagem dos reports abertos. Mostra-me o diff antes de commitar. Commits sem co-author.

## Resultado
- Suite completa antes de mexer: 160 passed, 1 skipped (64 s).
- Implementado: abas no topo (`tests/test_gui_layout.py::test_tabs_in_top_bar`, 7 larguras), `edit_report` + endpoint + botão (`tests/test_reports_edit.py`, `tests/test_server.py`, `tests/test_gui_reports.py`).
- Triagem em `docs/HANDOFF.md`: 3 duplicados a fechar, 3 grupos a explicar, restantes a corrigir (pose/recorte). Nada foi fechado.
- Revisão do Tiago: o diff parecia reescrita de fins de linha; no repo `core.autocrlf=true` e 119 ficheiros intocados já estão `i/lf w/crlf`. Convertidos para LF os ficheiros desta ronda e acrescentado `.gitattributes` (`* text=auto eol=lf`). Endurecimento: tipos inválidos no endpoint/`edit_report` → 400. Teste de sobreposição da barra de topo com job-pill (apanhou um defeito real a 1181–1280 px).
- Commits: `b894749`, `fb487de`, `1b5c21e` + docs. Suite: 179 passed, 1 skipped.
