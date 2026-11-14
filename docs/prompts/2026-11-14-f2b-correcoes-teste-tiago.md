# F2b — correções do teste do Tiago na GUI nova (2026-11-14)

## Porquê
O Tiago testou a F2 na GUI nova: a primeira colocação real por «pôr à mão» (Saco 9 · nº 89 em 1 · 29) funcionou, mas
a pesquisa por texto livre era ambígua, o Ctrl+C não fechava o servidor com um separador aberto, a lista de sugestões
piscava depois de cada colocação e faltava um sinal de que o programa estava a trabalhar.

## Decisões
Ver `docs/decisoes.md`, «2026-11-14 — F2b». Em resumo: lupa de dois separadores sem texto livre; `begin_shutdown` +
`timeout_graceful_shutdown` e `Last-Event-ID` limitado ao contador do servidor; lista anterior das sugestões `alta`
(validada) mantida enquanto o ranking dos buracos se recalcula; indicador «A gravar…» / «A atualizar sugestões…» no
cartão e no tabuleiro. Fase de desempenho e F4 não arrancadas (pedido).

## Prompt verbatim
«F2b: correções do teste do Tiago na GUI nova. Não arranques a fase de desempenho nem a F4.

1. Lupa redesenhada: dois separadores no topo, «Peça» e «Lugar». «Peça» tem os campos «Saco» e «nº» (aceita também P#### no primeiro campo); «Lugar» tem «Linha» e «Coluna». «Peça» por omissão; o separador escolhido fica guardado por aparelho. Sem interpretação de texto livre, por isso sem ambiguidade. Mesmo aspeto dos campos de «Pôr uma peça à mão». Testes para os dois separadores, para P#### e para valores fora da grelha ou inexistentes (mensagem clara: «Linha 1 a 47», «Saco 9 não tem nº 200»). Captura a 1366×768 e a 390×844.
2. Fechar o servidor: com um separador aberto, Ctrl+C não fecha o servidor até se fechar o separador. Encontra a causa (provavelmente a ligação SSE /api/events a manter o encerramento à espera) e faz o servidor fechar logo, com o separador aberto ou não. No browser, ao perder a ligação, aparece «Ligação perdida, a tentar religar…» e a página recupera sozinha quando o servidor volta. Teste que o prove.
3. Lista a piscar: depois de colocar uma peça, várias propostas desaparecem e voltam quando o recálculo acaba. Reproduz na GUI nova e na antiga, encontra a causa (ver o erro da reconsulta incremental registado em docs/estado-e-plano.md) e corrige: a lista anterior fica visível até a nova estar pronta. Teste que falha antes da correção.
4. Indicador de trabalho: enquanto uma ação grava ou as sugestões se recalculam, mostra-o no cartão e no tabuleiro («A gravar…», «A atualizar sugestões…»), sem bloquear o que não depende disso.
5. Regista em docs/decisoes.md: a primeira colocação real por «pôr à mão» (Saco 9 · nº 89 na linha 1 · coluna 29) funcionou [V, Tiago, 2026-11-14]; a cor fica com o valor inicial por agora.

Fecho: suite completa com o .venv, capturas a 1366×768 e a 390×844 dos ecrãs mudados, lista dos testes existentes alterados na mensagem do commit. Usa `graphify query` antes de grep ou de ler ficheiros e corre `graphify update .` no fim. Commits sem Claude como co-author.»

## Resultado
- Os 5 pontos feitos (ver `docs/decisoes.md`). Causa do Ctrl+C: o fluxo SSE mantinha o uvicorn à espera (> 20 s sem sair
  com 1 cliente; 0,22 s depois). Causa da lista a piscar: `alta_json` dava `entries: []` durante o recálculo dos buracos
  (teste `test_alta_list_stays_while_holes_recompute` falhava com `[] == ['P0002']`).
- Testes novos: `tests/test_gui_novo_f2b.py` (7), `tests/test_server_shutdown.py` (3), 2 em `tests/test_server_alta.py`.
  Alterados: `tests/test_gui_novo.py` (`test_lupa_shows_piece_and_place_proposals`, `test_guardar_phone_layout`: lupa com
  separadores), `tools/gui/f1c_capturas.py`, `tools/gui/f2_capturas.py`.
- Suite `.venv`: 548 passed, 1 skipped, 1 failed (`test_jump_asks_detail_at_once_…`, temporização do debounce de 250 ms,
  intermitente também no HEAD anterior: 2 falhas em 3 corridas [V]).
- Capturas `docs/gui/screenshots/F2b_*` (1366 e 390). Por fazer: Firefox/Safari/telemóvel real, F4 e fase de desempenho.
