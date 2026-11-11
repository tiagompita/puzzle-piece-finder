# 2026-11-11 — suite verde, prova estrutural da F1a, interface do board.js e F1b (casca nova + «Montar»)

## Porquê

O Tiago deu o OK à F1b do redesenho da GUI (`docs/gui/redesenho/ESPEC.md` §7), com três condições antes: a suite tinha uma falha herdada (`test_sheets`), a F1a só tinha sido provada por píxeis, e o `board.js` ainda dependia de estado e de uma função da GUI antiga sem o dizer.

## Decisões

- **Ponto 1:** a falha é do ambiente. O Python do sistema tem PyMuPDF 1.28 (desde 2026-06-29) e o `.venv` do projeto não tem. Nenhum commit a causou. A suite corre-se com `.venv/Scripts/python.exe`. O teste não foi alterado; torná-lo independente do PyMuPDF fica para o Tiago decidir (`docs/decisoes.md`).
- **Ponto 2:** prova sem píxeis com `tools/gui/f1_estrutura.py` (SVG das camadas + caixas de todos os elementos do tabuleiro): idêntica.
- **Ponto 3:** a interface do `board.js` é `S.board` + 3 estados (`S.showGrid`, `S.showGhost`, `S.pose`) + 1 função (`poseWheel` de `pose.js`, agora `S.onPoseWheel`) + o gancho `S.onBoardTap`.
- **F1b:** regras que o ESPEC não fixava (traços com folga, «quase certo» também sem traço a falhar, «importação recente», desfazer e motivo como eventos) estão em `docs/decisoes.md` (2026-11-11, F1b).

## Prompt verbatim

«OK para a F1b, depois destes três pontos, por esta ordem:

1. Suite verde. `test_sheets::test_pdf_page_without_image_or_with_flate_is_an_error` passava a 2026-11-09 (460 passed, 0 failed). Descobre em que commit começou a falhar, ou se é do ambiente (versão de uma biblioteca). Corrige a causa. Se a correção não for óbvia, para e diz-me o que encontraste: não alteres o teste para passar nem o marques como esperado sem o meu OK.

2. Prova da F1a sem píxeis. Compara, antes e depois da extração (commit anterior a 8fedf87 contra 8fedf87), a estrutura do tabuleiro: o SVG das camadas e as posições e tamanhos dos elementos, a 1366×768 e a 390×844. Tem de ser idêntica. Se não for, para e mostra as diferenças.

3. Interface do board.js. Lista os três estados e a função da GUI antiga de que ainda depende, e torna-os uma interface declarada (documentada no cabeçalho do ficheiro, definida pela casca antiga e pela nova), com um teste que carrega o board.js só com essa interface.

Depois arranca a F1b como no plano. No fecho da F1b: atualiza docs/HANDOFF.md e o ficheiro do prompt em docs/prompts/, e guarda as capturas de comparação em PNG.

Usa `graphify query` antes de grep ou de ler ficheiros e corre `graphify update .` no fim. Commits sem Claude como co-author.»

## Resultado

- **Ponto 1 [V]:** em `8fedf87`, com o `.venv`: 460 passed, 1 skipped, 0 failed (298 s). Com o Python do sistema: 1 failed (o mesmo teste).
- **Ponto 2 [V]:** `d9c8165` ↔ `8fedf87`, cópia de `projects/alpes`, 4 estados × 2 viewports.
  - SVG das camadas igual nos 8 casos.
  - 184 / 185 / 184 / 261 elementos do tabuleiro por estado, 0 diferenças.
  - Na página inteira, só os 2 `<script>` novos.
  - Duas corridas de `d9c8165` entre si: 0 diferenças.
- **Ponto 3 [V]:** cabeçalho de `src/web/board.js`; `app.js` define `S.onPoseWheel`; `tests/test_board_interface.py` (stub com `Proxy` + verificação estática dos nomes). O teste falha com o `board.js` da F1a e passa com o novo. Teste novo de Alt+roda em `tests/test_gui_pose.py`. Commit `c241ca0`.
- **F1b [V em testes e capturas; NT com o Tiago]:**
  - `/novo/` com o ecrã Montar.
  - `src/montar.py`, `GET /api/montar`.
  - Desfazer «Encaixa» / «Não encaixa», motivo.
  - Contadores sem as decisões desfeitas.
  - Capturas PNG em `docs/gui/screenshots/redesenho/F1b_*`.
  - A GUI antiga em `/` ficou estruturalmente igual: 0 diferenças contra `8fedf87` nos 8 casos, também na página inteira.
  - Commits e números finais em `docs/HANDOFF.md`.
- **Fica por fazer:** F2 em diante. Ver «Pendentes» em `docs/HANDOFF.md`.
