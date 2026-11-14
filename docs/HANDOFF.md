# HANDOFF — 2026-11-14 (detalhe do tabuleiro: A + B feitos; F1d à espera do OK; F2 não arrancou)

Lê isto primeiro numa sessão nova; no fim, atualiza-o e fecha o ficheiro do prompt em `docs/prompts/`.

## Última sessão (2026-11-14): `docs/prompts/2026-11-14-detalhe-tabuleiro.md` (fechado)
- **Problema:** depois de um salto da lupa o detalhe do tabuleiro demorava e a GUI «deixava de responder». Medições em `docs/diagnostico/gui/DETALHE.md`, todas feitas numa cópia de `projects/alpes`. Guiões em `tools/diagnostico/gui/` (`salto_detalhe.py`, `tempo_regiao.py`, `gil_buracos.py`, `tabela.py`).
- **Anterior à F1 [V]:** em `8fedf87^` o salto frio demora o mesmo (céu 2,11 s, contra 2,14 s em HEAD na GUI antiga).
- **Causas [V]:**
  - (a) composição de regiões dentro do `rlock`: um `board.jpg` já em cache esperava 1,8 s;
  - (b) sem cancelamento: 5 saltos seguidos davam 5 composições em série, com o detalhe final aos 7,6–8,2 s;
  - **novo:** o ranking dos buracos a frio (1.º `/api/montar` depois de abrir, ≈ 30–40 s) rouba o GIL, e um detalhe de 2,5 s passa a 26–34 s.
  - O fio do browser nunca bloqueou: 0 long tasks, rAF ≤ 17 ms.
- **Feito: só A + B.**
  - `Gui._region_jpg` compõe fora de qualquer lock, com `region_lock` só para a LRU e deduplicação dos pedidos em voo.
  - `loadDetail` usa `fetch` + `AbortController` + `img.decode()` + objectURL. Os cabeçalhos `X-Detail-Client` / `X-Detail-Seq` fazem o servidor descartar, antes de compor, um pedido ultrapassado (HTTP 409), com uma composição por cliente de cada vez.
  - Depois: `board.jpg` em cache 1 ms durante uma composição; 5 saltos → 1 composição útil, final em 3,3–3,9 s.
- **Critério [F] em 1a/1b:** frio 2,2–2,8 s (critério 1,5 s); quente 0,29–0,31 s (critério 0,3 s; o debounce de 280 ms sozinho gasta 0,28 s). 2b falha no arranque (sondas até 376 ms). 2a, 2c e 3 [V].
- **Recomendação** (DETALHE.md §5, nada disto implementado):
  - H: `sys.setswitchinterval(0.0005)` no servidor; em processo, a composição com o ranking a correr passou de 26 s para 4 s;
  - E: cache por peça do recorte pronto, estimativa frio ≈ 1 s;
  - C: mosaicos (longe e perto de uma escrita custam hoje o mesmo, 2,2–2,5 s);
  - D, G: não; F: só se H não chegar.
- **Testes:** 4 novos em `tests/test_server.py` e 1 Playwright em `tests/test_gui_novo.py`; um teste existente alterado: `tests/test_gui_novo.py::test_icons_local_aria_and_layout` passa a aceitar o `blob:` da mesma origem (o objectURL do detalhe) na verificação de «nenhum pedido fora do servidor».
- **Suite [V]:** 513 passed, 1 skipped, 0 failed (362 s, com os slow; +5 testes).
- **Scratchpad:** a cópia `alpes_det`, `alpes_pref1` e os worktrees `wt_head`/`wt_pref1` ficam lá para repetir as medições. Os worktrees aparecem em `git worktree list` e removem-se com `git worktree remove --force <caminho>`.

## Sessão anterior (2026-11-14): `docs/prompts/2026-11-14-f1d-correcoes-gui-nova.md` (fechado)
- **F1d [V em testes; NT com o Tiago]** (regras em `docs/decisoes.md` 2026-11-14 F1d, ESPEC §2 e §7):
  - desfazer: causa = só havia um aviso de 9 s que aparecia ≈ 3 s depois do clique (o `POST` demora 3,4 s no real); agora faixa «última ação» com «Desfazer» no topo do painel até à ação seguinte;
  - cartões sem vizinha montada: «Colocar aqui» / «Não pertence aqui» (por dentro `position_known` / `reject`, sem «Porquê?»); a peça fica no tabuleiro «por confirmar» (imagem ténue + contorno tracejado da própria peça); verificado no código que a célula continua vazia para o motor (não é molde, nem vizinha, nem conta no progresso);
  - «localizar» (só ícone) no cartão; ícones Lucide locais em `src/web/novo/icons/` (ISC + MIT); menu «⋯» a toda a largura a 390 px;
  - ecrã vazio: «N peças guardadas à parte, no tabuleiro «por confirmar»…» (a linha «para guardar» saiu).
- **`test_twin_real` corre:** memória em `tests/data/ereal2_memoria.npz` (53 KB), refaz-se com `tools/diagnostico/gemeos/ereal2_fixture.py`.
- **Máscaras do Photoshop:** recortes do editor (caixa + 3 mm) de P1203, P0045, P1245, P0198 em `docs/diagnostico/editor/gt_photoshop/` com `LEIAME.md` e `recortes.json` (origem na folha); falta o Tiago fazer as máscaras.
- **Capturas:** `docs/gui/screenshots/redesenho/F1d_*` (cópia do estado atual: P0980 por confirmar em 38 · 3, 2 cartões sem vizinha).
- **Suite [V]:** 508 passed, 1 skipped, 0 failed (430 s, com os slow; +9 testes desde a F1c); o único skip é o PyMuPDF real no `test_sheets` (o `test_twin_real` já corre).
- **Scratchpad:** `alpes_base` e `proj` apagadas (nenhum teste/ferramenta as referia; caminhos verificados); cópias desta sessão também apagadas.
- Sessão anterior (2026-11-12): `test_sheets` nos dois caminhos, quadrados em JSON, negativos difíceis por zona (`docs/prompts/2026-11-12-test-sheets-montar-quadrados-json.md`).

## Estado (F1b, sessão anterior)
- **Prompt da sessão:** `docs/prompts/2026-11-11-f1b-casca-nova-montar.md` (fechado).
- **Commits** (em `main`, sem `projects/alpes`):
  - `c241ca0`: interface do `board.js` + prova estrutural da F1a;
  - `7524053`: F1b (código e testes);
  - `3578ad4`: docs e capturas;
  - `graphify update .` corrido no fim (`graphify-out/` está fora do git).
- **Suite [V]:** corre-se com `.venv/Scripts/python.exe -m pytest tests/`, não com o `python` do PATH.
  - O Python do sistema (3.12.6) tem PyMuPDF 1.28; desde `d24cb57` o `test_sheets` passa nos dois.
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

## Grupos soltos (sessão de 2026-11-12, só docs e ferramentas, sem `src/` nem `projects/`)
- **Prompt:** `docs/prompts/2026-11-12-quadrados-17-e-juncoes-de-grupos.md` (fechado).
- **Quadrados 17/17 [V, Tiago, 2026-11-11]:** o Tiago testou os 11–17 e encaixam todos; 10/10 + 7/7 = 17/17, todos no céu, Wilson inferior 0,82. A margem não discriminou (encaixou até 1,008); o método dos quadrados está esgotado nas soltas atuais. Registado em `docs/decisoes.md`, `docs/estado-e-plano.md` §3.9, `QUADRADOS.md` e ESPEC §8.6.
- **ESPEC:** «já no grupo N» nas figuras, listas e cartões de grupo; F4c (verificar as junções ao largar um grupo: encaixa com «Fixar», não encaixa com X, não sei sem marca; «Onde encaixa este grupo?»), pendente de medição (§4.9 e §7).
- **Medição das junções [V na amostra, ver limites]** (`docs/diagnostico/fit/GRUPOS_JUNCOES.md`, `tools/diagnostico/fit/grupos_juncoes*.py`): 115 blocos colocados (63 céu, 52 relva; montanha e vale sem dados) como grupos soltos, 86 840 posições erradas. Com 1 junção não se afirma nada (deslocados: falso «encaixa» 14 %, falso «não encaixa» 10 %, relva 20 %); com ≥ 4 junções o «encaixa» (critério B) teve 0 falsos em 4 733 posições e 0 em 115 blocos; na relva as junções custam o dobro do céu e `t_abs` falha mais; a posição gémea encaixa por forma (custo 0,54 contra 0,53) e só a imagem a separa (15 % de falhas na montanha e no vale).
- **O que falta para propor peças que façam crescer um grupo solto:** lista de 9 pontos no §4 do mesmo relatório (layout e rotação por peça guardados, regra F sem posição, pool sem peças de grupos, células virtuais, calibração por zona, eventos, pose no referencial do grupo, zona do grupo). Não implementado.
- **Decisão do Tiago por tomar:** aceitar (ou mudar) o mínimo de junções do relatório §3 (≥ 4 para afirmar «encaixa»; 1 não afirma; fora do céu só ≥ 5 para «não encaixa»). Os cortes de 5 % e 10 % foram escolhas minhas.

## O que o Tiago tem de ver (pendente [NT])
1. Arrancar `python -m src.server --ui novo` e abrir `/novo/`. Num telemóvel, abrir `http://<ip>:8765/novo/` com `--lan`.
2. Montar: o cartão, «Encaixa» num clique, o toast «Desfazer», «Não encaixa» → «Porquê?» → «Próxima peça» / «Enganei-me, desfazer», Ctrl+Z.
3. As palavras: «quase certo» só aparece no céu (gémea 46/46 e buraco 57/57 no log de hoje). Fora do céu diz sempre «a confirmar por ti».
4. F1c: o cartão «Guardar à parte» das 3 gémeas (alvo tracejado, «Guardei à parte» / «Não é esta» e o desfazer), o ecrã vazio com as contagens, a lupa («saco 4 nº 22», «38,3»).
   - Atenção [NT]: a peça do saco 4 nº 22 é clara (céu?) e o lugar 38 · 3 é verde (vale): a imagem pode estar a dizer «Não é esta».
5. F1d: depois de «Colocar aqui», a faixa «Desfazer» no topo do painel; a peça «por confirmar» no tabuleiro; o «localizar»; os ícones; a 390 px o menu «⋯».
6. OK para a F2 (célula, lugar vazio, pôr e tirar à mão, desfazer global).

## Espera pelo Tiago
1. **Gémeas sem vizinha montada na GUI nova:** feito na F1c (ver acima); falta o OK.
2. **Máscaras do Photoshop para a fase 2 do editor** (ronda 10): os recortes estão em `docs/diagnostico/editor/gt_photoshop/` (ver `LEIAME.md`); o Tiago grava por cima `P####.png` com transparência, mesmo tamanho; `recortes.json` dá a origem na folha.
3. Registar os 17 grupos montados no projeto (dados em `quadrados_17.json`; porta de escrita na F4b; `QUADRADOS.md`, «Como registar»). Não fazer sem ordem.
4. Anteriores: PDF vetorial (PyMuPDF no `.venv`?), lock entre processos, pares T0001/T0002/T0005, T0003/T0004, p90 por zona, P0343/P0833, corte c32|c33.

## Pendentes técnicos (por ordem)
1. **F2** (ESPEC §7; ordem F2, F4, F4b, F4c, F3, F5, F6): painel da célula (C) e do lugar vazio (V), pôr à mão com verificações (§5.4), «Tirar do lugar», desfazer global. Desfazer «Encaixa» de um par desfaz o par e a posição da outra (decidido 2026-11-12). Só com o OK do Tiago.
   - Na F1b, tocar num lugar só escolhe a peça da fila desse lugar.
2. **Limites da F1b [NT]:**
   - desfazer «Encaixa» de um par não desfaz o `pair_confirmed` nem a posição conhecida da outra peça (corrige-se na F2);
   - «Peças» é só uma ligação para a interface completa (F3);
   - «⋯ › Atividade» abre a interface antiga noutro separador (F5);
   - «Ver números» mostra as razões técnicas no painel (F5: Diagnóstico).
3. **Traços [NT]:** os fatores de folga (½ do limite, 2× a margem mínima) não estão calibrados.
4. **Ações novas no log** (`rejection_undone`, `pair_unrejected`, `rejection_noted`; F1c: `position_cleared`): checkouts anteriores deixam de ler um log que as tenha.
5. **Limites da F1d [NT]:** a faixa «Desfazer» só existe nesta sessão do browser (recarregar perde-a; Ctrl+Z também); não testado em Firefox/Safari nem no telemóvel real; a imagem «por confirmar» só aparece com rotação conhecida (sem ela, só o tracejado da célula).
6. Da ronda 10: fase 2 do editor (condicional, por zona), possível sobre-corte no lado S, P0045/P0071/P1064 índice manual por 1 píxel, limiares `GANHO_MIN_MM2` / `GEMEA_RUIDO_MM`, cache das miniaturas `?v=`.
7. **Detalhe do tabuleiro** (DETALHE.md §5, sem ordem do Tiago): H (intervalo do GIL, medir o ranking/reconsulta com e sem) → E (cache por peça) → C (mosaicos); decidir com o Tiago se um salto pede o detalhe sem o debounce de 280 ms.
8. Anteriores: verificar ativos no arranque das CLI; `append_override` escreve CRLF; passo «pares» N²; arranque a frio; GT fora do céu; pose manual 4–9 s; detetor de peça comida; (26,1)/(25,1).

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
