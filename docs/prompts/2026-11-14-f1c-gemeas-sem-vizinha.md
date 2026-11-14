# 2026-11-14 — F1c: gémeas sem vizinha montada no Montar, marca do índice nos quadrados, ordem das fases

## Porquê

No projeto real o Montar da GUI nova saía vazio («Nada para ir buscar») com 3 gémeas `ambigua` e 32 grupos por ancorar no `fetch.json`: as gémeas sem vizinha montada (`guarda_posicao`) só existiam na GUI antiga. Na sessão de 2026-11-12 ficou a proposta (a)(b)(c) no `HANDOFF.md`; o Tiago aprovou-a com ajustes, antes da F2.

## Decisões

- (a) Cartões «Guardar à parte» só depois de esgotadas as «coloca agora»; sempre «a confirmar por ti», sem «Encaixa», alvo tracejado; «Não é esta» grava a rejeição e desfaz-se como as outras (aviso e Ctrl+Z). (Tiago)
- (b) O ecrã vazio diz quantas há para guardar / guardadas à parte e quantos grupos sem lugar, com ligação à interface completa até à F4. (Tiago)
- (c) A lupa mostra as propostas da peça e do lugar. (Tiago)
- «Guardei à parte» também se desfaz (aviso e Ctrl+Z), com a ação nova `position_cleared`; Enter não faz nada num cartão «Guardar à parte». (minhas, coerentes com a F1b; `docs/decisoes.md` 2026-11-14)
- Marca do índice em `quadrados_17.json`: assinatura do LOG (sha1 de `cls`, `chords_mm`, `area_mm2`, `bbox`) + nº de `piece_resegmented` por peça + comprimento do log; o teste avisa com `UserWarning`, não falha. Escolhido o log e não o contorno do `npz` porque o log viaja com o git e o `npz` não. (minha)
- ESPEC: ordem das fases F2, F4, F4b, F4c, F3, F5, F6. (Tiago)
- **Não** se arrancou a F2.

## Prompt verbatim

«F1c, antes da F2. Aprovo a proposta (a), (b) e (c) para as gémeas «ambigua», com estes ajustes:
- (a) Os cartões «Guardar à parte» só entram na fila depois de esgotadas as peças «coloca agora». Mantêm-se sempre «a confirmar por ti», sem «Encaixa», com alvo tracejado no tabuleiro. «Não é esta» grava a rejeição e pode ser desfeita como as outras (aviso e Ctrl+Z).
- (b) O ecrã vazio diz a verdade: quantas há para guardar à parte e quantos grupos sem lugar, com ligação à interface completa até à F4.
- (c) A lupa mostra as propostas da peça e do lugar.
Testes novos para os três, incluindo um que falha se o Montar disser «Nada para ir buscar» havendo propostas no fetch.json.

Também:
1. Corre a suite completa, incluindo os slow, com o .venv, e reporta os números.
2. quadrados_17.json: acrescenta uma marca do índice de que depende (por exemplo, um hash do contorno de cada peça) e um teste que avisa se uma peça dos quadrados foi re-segmentada desde então.
3. ESPEC: a ordem das fases fica F2, F4, F4b, F4c, F3, F5, F6.
4. Apaga a cópia do projeto de 394 MB no scratchpad, depois de confirmares pelo caminho que é a cópia e não projects/alpes.
5. Capturas da F1c a 1366×768 e a 390×844, com o estado atual do projeto (as 3 gémeas visíveis).

Para aqui. Não arranques a F2: o Tiago ainda vai ver a GUI nova no PC e no telemóvel. Corre graphify update . no fim. Commits sem Claude como co-author.»

## Resultado

- **Código:** `src/montar.py` (cartões `guardar`, `resumo`), `src/state.py` (`position_cleared`, `clear_position_known`), `src/confirm.py` (`clear_position`), `src/server.py` (`position_clear`, `fora_da_fila`, legenda `alvo_guardar`, `grupo` nas propostas), `src/web/novo/*` e `src/web/board.css` (cartão, alvo tracejado, ecrã vazio, caixa da lupa).
- **Testes novos** em `tests/test_montar.py` (fila, resumo, guardar + desfazer, «Não é esta» + desfazer, só grupos, `grupo` nas propostas, `position_cleared` com replay, e o guarda com o `fetch.json` real) e `tests/test_gui_novo.py` (7, Chromium); `tests/test_quadrados_json.py` (marca: esquema, mecanismo do aviso, conferência com o projeto). Testes alterados: legenda curta 2 → 3 entradas (ESPEC §4.1), a fila do teste puro ganha o cartão «guardar» no fim, e as esperas depois de desfazer passam a apontar para o cartão principal (`.card[data-tipo]`; o cartão «Não encaixou» também tem `data-piece` e a espera passava antes de o desfazer acabar).
- **Quadrados:** `marca_indice` gerada por `tools/diagnostico/grupos_soltos/quadrados_marca.py` sobre uma cópia mínima do projeto (log de 3086 eventos): 62 peças, nenhuma re-segmentada alguma vez.
- **Capturas:** `docs/gui/screenshots/redesenho/F1c_*` (README atualizado), com `tools/gui/f1c_capturas.py`.
- **Scratchpad:** `alpes_copia` apagada depois de verificada (caminho resolvido no scratchpad, drive C: contra D: de `projects/alpes`, 2457 entradas sem links nem junções, `log.jsonl` não é o mesmo ficheiro); a cópia das capturas (`alpes_f1c`) apagada da mesma forma. Ficam `alpes_base` e `proj` (394 MB cada, de sessões anteriores, não pedidos).
- Suite, commits e o que ficou por ver: `docs/HANDOFF.md`.
