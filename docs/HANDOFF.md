# HANDOFF — 2026-11-11 (redesenho da GUI: F1b feita, à espera do OK do Tiago)

Lê isto primeiro numa sessão nova; no fim, atualiza-o e fecha o ficheiro do prompt em `docs/prompts/`.

## Estado
- **Prompt da sessão:** `docs/prompts/2026-11-11-f1b-casca-nova-montar.md` (fechado).
- **Commits** (em `main`, sem `projects/alpes`):
  - `c241ca0`: interface do `board.js` + prova estrutural da F1a;
  - F1b: código, testes, capturas e docs (ver `git log`).
- **Suite [V]:** corre-se com `.venv/Scripts/python.exe -m pytest tests/`, não com o `python` do PATH.
  - O Python do sistema (3.12.6) tem PyMuPDF 1.28 e faz falhar `test_sheets::test_pdf_page_without_image_or_with_flate_is_an_error`. Não é de nenhum commit (`docs/decisoes.md`, 2026-11-11).
  - Em `8fedf87`: 460 passed, 1 skipped, 0 failed.
  - Depois da F1b: 477 passed, 1 skipped, 0 failed (293 s, com os `slow`; +17 testes novos).
- **Prova estrutural da F1a [V]** (`tools/gui/f1_estrutura.py`): SVG das camadas e caixas de 184–261 elementos do tabuleiro iguais antes/depois, nos 4 estados × 1366/390. A GUI antiga depois da F1b também é igual a `8fedf87`, na página inteira.
- **Interface do `board.js` [V]:** `S.board`, estados `S.showGrid` / `S.showGhost` / `S.pose`, função `S.onPoseWheel` (era o `poseWheel` global de `pose.js`), gancho `S.onBoardTap`. Está documentada no cabeçalho e testada por `tests/test_board_interface.py`.
- **F1b [V em testes; NT com o Tiago]:** GUI nova em `/novo/` (também `/?ui=novo` e `python -m src.server --ui novo`); a antiga continua em `/`.
  - Topo: «N de 3008 peças» (colocadas + marcadas por ti), abas Montar · Peças · Importar scan, lupa, «⋯».
  - Montar: cartão «Próxima peça» (saco e nº em grande, linha · coluna, confiança em palavras com 3 traços), **Encaixa** / **Não encaixa**, «Saltar por agora», «Porquê esta peça?», «A seguir» (3).
  - Tabuleiro: alvo âmbar «vai aqui», 3 seguintes ténues, legenda curta (2 entradas: «Onde vai a peça», «Por montar»).
  - Fila por saco (§8.2). «quase certo» só por origem × zona com n ≥ 10 e Wilson ≥ 0,80 (§8.3).
  - Desfazer «Encaixa» e «Não encaixa» (toast, «Enganei-me, desfazer», Ctrl+Z); motivo opcional «Porquê?».
  - Teclas: Enter, N, S, Ctrl+Z.
  - Servidor: `src/montar.py`, `GET /api/montar`; eventos `rejection_undone`, `pair_unrejected`, `rejection_noted`, `unplaced desfaz`. As decisões desfeitas não contam (`state.undone_decisions`, também em `fit.alta_counter` / `--relatorio`).
  - Regras que o ESPEC não fixava: `docs/decisoes.md` (2026-11-11, F1b).
- **Capturas [V]:** `docs/gui/screenshots/redesenho/F1b_{antes,montar,porque,nao,vazio}_{1366,390}.png` e `F1b_contagens.json`. No ecrã principal, palavras 951 → 72 e botões visíveis 13 → 15 a 1366 px.
- **No projeto real hoje a fila está vazia [V]:** as 3 gémeas não têm vizinha montada e as 2 `alta` estão em conflito. As capturas com cartões são do estado de `8fedf87`.
- **Reports:** não foram consultados nem tocados nesta sessão.

## O que o Tiago tem de ver (pendente [NT])
1. Arrancar `python -m src.server --ui novo` e abrir `/novo/`. Num telemóvel, abrir `http://<ip>:8765/novo/` com `--lan`.
2. Montar: o cartão, «Encaixa» num clique, o toast «Desfazer», «Não encaixa» → «Porquê?» → «Próxima peça» / «Enganei-me, desfazer», Ctrl+Z.
3. As palavras: «quase certo» só aparece no céu (gémea 46/46 e buraco 57/57 no log de hoje). Fora do céu diz sempre «a confirmar por ti».
4. OK para a F2 (célula, lugar vazio, pôr e tirar à mão, desfazer global).

## Espera pelo Tiago
1. **`test_sheets` e o PyMuPDF:** tornar o teste independente do ambiente exige mudar o teste. Não foi feito sem OK.
2. **Máscaras do Photoshop para a fase 2 do editor** (ronda 10): P1203, P0045, P1245, P0198 em `docs/diagnostico/editor/gt_photoshop/P####.png` (alfa = a peça, grelha do scan inteiro).
3. **Quadrados 11–17** entre soltas (`docs/diagnostico/grupos_soltos/QUADRADOS.md`).
4. Anteriores: PDF vetorial (PyMuPDF no `.venv`?), lock entre processos, pares T0001/T0002/T0005, T0003/T0004, p90 por zona, P0343/P0833, corte c32|c33.

## Pendentes técnicos (por ordem)
1. **F2** (ESPEC §7): painel da célula (C) e do lugar vazio (V), pôr à mão com verificações (§5.4), «Tirar do lugar», desfazer global.
   - Na F1b, tocar num lugar só escolhe a peça da fila desse lugar.
2. **Limites da F1b [NT]:**
   - desfazer «Encaixa» de um par não desfaz o `pair_confirmed` nem a posição conhecida da outra peça;
   - «Peças» é só uma ligação para a interface completa (F3);
   - «⋯ › Atividade» abre a interface antiga noutro separador (F5);
   - «Ver números» mostra as razões técnicas no painel (F5: Diagnóstico).
3. **Traços [NT]:** os fatores de folga (½ do limite, 2× a margem mínima) não estão calibrados.
4. **Ações novas no log** (`rejection_undone`, `pair_unrejected`, `rejection_noted`): checkouts anteriores à F1b deixam de ler um log que as tenha.
5. Da ronda 10: fase 2 do editor (condicional, por zona), possível sobre-corte no lado S, P0045/P0071/P1064 índice manual por 1 píxel, limiares `GANHO_MIN_MM2` / `GEMEA_RUIDO_MM`, cache das miniaturas `?v=`.
6. Anteriores: verificar ativos no arranque das CLI; `append_override` escreve CRLF; passo «pares» N²; arranque a frio; GT fora do céu; pose manual 4–9 s; detetor de peça comida; (26,1)/(25,1).

## Convenções que mordem
- **Testes com o `.venv`** (`.venv/Scripts/python.exe -m pytest tests/`); a suite completa demora ≈ 300 s: correr em segundo plano.
- Nunca `taskkill //IM python.exe`: só por PID, listado e justificado. No Git Bash, preferir scripts `.py` no scratchpad a `python -` com heredoc.
- Nunca correr servidor/render/ingest sobre `projects/alpes` para medir: usar cópias (`tools/rebuild_scans.py --stale --also-missing` antes das linhas de base). Escritas reais só com o servidor parado, cópia de segurança e commit a seguir.
- `projects/alpes` tem alterações locais do Tiago no working tree (board, log, scans, fetch, overrides, pairs, `log.jsonl.bak-20261109`): não as tocar nem incluir em commits; `git add` só com caminhos explícitos.
- **Duas silhuetas:** quem lê o índice lê `contour_px` / npz, nunca `aresta_px`.
- `tools/diagnostico/**` precisam de `PPF_SCRATCH`. Commits em português, sem co-author.
- GUI nova: os textos do Montar não podem ter (l, c), P#### (só no `.pid` pequeno), mm, margem, ΔE, aceite/alta/ambígua (`tests/test_gui_novo.py::FORBIDDEN`).

## Links
- Redesenho:
  - `docs/gui/redesenho/ESPEC.md` (§7 fases, §8 decisões);
  - `F0_INVENTARIO.md`;
  - capturas e prova estrutural: `docs/gui/screenshots/redesenho/README.md`;
  - ferramentas: `tools/gui/f1a_capturas.py`, `tools/gui/f1_estrutura.py`, `tools/gui/f1b_capturas.py`.
- Ronda 10: `docs/diagnostico/editor/CONVENCAO.md` §6; decisões em `docs/decisoes.md`.
- Comandos de início de sessão: `python -m src.reports --project projects/alpes --list`; `python -m src.consistency --project projects/alpes`.
