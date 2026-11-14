# F2c — correções do uso real da GUI nova (2026-11-14)

## Porquê
Depois da F2b o Tiago usou a GUI nova a sério: o Saco 9 · nº 89 encaixou na linha 1 · coluna 29. Viu que o arranque só
mostrava «a carregar», um aviso vermelho na GUI antiga durante o arranque, que «Mostrar a borda em falta» não mostrava
nada e que a lupa com campos separados continuava pesada; o Ctrl+C acabava com um traceback.

## Decisões
Ver `docs/decisoes.md`, «2026-11-14 — F2c». Em resumo: preparação visível com n de N nas duas GUIs
(`status.preparacao`, `prepare_progress`); aviso vermelho = nunca a faixa com o servidor vivo (testado); reproduzido um
`core.js` velho em cache («watchConnection is not defined»), corrigido com `Cache-Control: no-cache`; a borda está completa
(nada a mostrar), agora diz-o; lupa de dois botões («Peça», «Posição») com uma caixa que desliza; destaque animado do
resultado até ao próximo toque; Ctrl+C só imprime «Servidor parado.» e sai com 0. Fase de desempenho não arrancada.

## Prompt verbatim
«F2c: correções do uso real da GUI nova. Não arranques a fase de desempenho.

1. Arranque: enquanto o servidor prepara o projeto, as duas GUIs mostram o que está a fazer e o progresso («A preparar o puzzle… refazer imagens n de N», «A preparar sugestões…»), em vez de ficarem só «a carregar».
2. Aviso vermelho na GUI antiga durante o arranque (o Tiago leu algo como «Watch Connection»): identifica qual é. Se for o «Ligação perdida» da F2b a disparar com o servidor ocupado mas vivo, só deve aparecer quando a ligação cair mesmo. Teste que o prove.
3. «Mostrar a borda em falta»: confirma se não mostra nada por não faltar nenhuma borda (a linha 1 · coluna 29 foi posta hoje). Nesse caso, diz «Não falta nenhuma peça de borda». Se for outra causa, corrige.
4. Resultado da lupa destacado no tabuleiro: contorno animado no lugar ou na peça encontrada, como o «vai aqui», até ao próximo toque. Teste.
5. Lupa redesenhada (substitui os separadores de campos da F2b): dois botões, «Peça» e «Posição». Cada um abre uma só caixa de texto com uma animação curta a deslizar (≤ 200 ms, desligada com prefers-reduced-motion); abrir um fecha o outro, sem tapar os botões. Posição aceita «1,29», «1 29», «1.29» e «1-29». Peça aceita «9 89», «9/89», «9,89» e «P1422». Mensagens claras para valores fora da grelha ou inexistentes. O modo escolhido fica guardado por aparelho.
6. Ctrl+C: trata a interrupção e sai com uma linha só, «Servidor parado.», código de saída 0, sem traceback.
7. Regista em docs/decisoes.md: Saco 9 · nº 89 na linha 1 · coluna 29 encaixa fisicamente [V, Tiago, 2026-11-14], primeiro caso real de «pôr à mão».

Fecho: suite completa com o .venv, capturas a 1366×768 e a 390×844 dos ecrãs mudados, lista dos testes existentes alterados na mensagem do commit. Usa `graphify query` antes de grep ou de ler ficheiros e corre `graphify update .` no fim. Commits sem Claude como co-author.»

## Resultado
- Os 7 pontos feitos (ver `docs/decisoes.md`). Causas: aviso vermelho = nunca a faixa com o servidor vivo (testado);
  reproduzido «watchConnection is not defined» com um `core.js` velho em cache (sem `Cache-Control`) [NT qual viu o Tiago];
  borda = `missing_border_cells()` vazio (218/218), não era defeito; Ctrl+C = o uvicorn re-levanta o sinal depois do
  encerramento gracioso (traceback + código ≠ 0).
- Testes novos: `tests/test_gui_f2c.py` (8), 2 em `tests/test_server_shutdown.py`, 7 na lupa de `tests/test_gui_novo_f2b.py`.
  Alterados: `tests/test_gui_novo_f2b.py` (lupa reescrita; `test_working_indicator_while_suggestions_recompute` diz «A preparar»
  na 1.ª vez), `tests/test_gui_novo.py` (helpers `_buscar_peca`/`_buscar_lugar`, `_abrir_lupa`), `tools/gui/f1c_capturas.py`,
  `f2_capturas.py`, `f2b_capturas.py` (a F2b ficou parcial: os erros já não são toasts).
- Suite `.venv`: 563 passed, 1 skipped, 2 failed: `test_jump_asks_detail_at_once_…` (pré-existente, 3/3 falhas isoladas) e
  `test_server_queue.py::test_failed_job_does_not_block_and_move` (espera pelo estado transitório `a_correr`; passou 4/4 isolado
  e a ficheiro inteiro 3/3: intermitente sob carga, não tocado por esta ronda).
- Capturas `docs/gui/screenshots/F2c_*` (1366 e 390; arranque real com 3 folhas por refazer). Por fazer: Firefox/Safari/telemóvel real,
  F4, fase de desempenho; `CLAUDE.md` (linhas de `server.py`/`web/novo`) por atualizar por quem pode.
