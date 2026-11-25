# 2026-11-25 — cache do tabuleiro (relva em falta), P0395, painel e lista dos grupos

## Porquê
`render/gui/board_60.jpg` (24/11 23:55) não tinha as peças da relva (filas 42–44, colunas 47–57, entre outras) embora os dados estivessem certos (699/699 colocadas com placement). O Tiago pediu a prova da causa, a correção, o veredicto sobre P0395 e duas melhorias no ecrã dos grupos soltos.

## Decisões
- Cache do tabuleiro: o snapshot passa a incluir a entrada de `placements.json` de cada peça (`placement_digest`); uma entrada nova ou uma pose mudada refaz a célula mesmo sem evento no log. Uma vez, depois de atualizar, o 1.º arranque recompõe o tabuleiro inteiro (≈ 20 s) porque os snapshots guardados passam a ter outro formato.
- P0395: dados não mexidos (decisão do Tiago).
- Miniaturas da lista: as de todos os grupos, descarregadas em fundo (os mostrados primeiro), com a mesma regra do detalhe primeiro.

## Prompt verbatim
(ver o pedido do gestor da ronda; pontos 1 a 4: cache do tabuleiro, P0395, painel do grupo com «Algo está errado» e «Corrigir recorte» + miniaturas na lista, apagar `.tmp_diag/`.)

## Resultado
Ver o relatório final abaixo (palavra por palavra).

**Commits:** `215158e` (código e testes) e o commit dos documentos desta ronda (a seguir). Sem push.

**1. Cache do tabuleiro**
- Causa provada [V]: `render/gui/board_60.jpg` vs `compose_board` inteiro por célula (`tools/diagnostico/gui/cache_vs_inteiro.py`, só lê): 254 células com diferença média > 6, até 56 níveis nas filas 42–44, colunas 47–57 (sem peças na cache, com peças no compose; capturas lado a lado vistas). O registo de 24/11 (`logs/servidor-20261124.log`): às 10:12 o tabuleiro compôs-se com 57 peças «sem registo» (642 gravadas, 57 em falta) e não as desenhou; às 10:45 foram registadas («57 entradas gravadas, 0 poses mudadas»). O snapshot da cache só tinha o log (estado, peça, θ do log, pose manual, aresta); a entrada nova de `placements.json` não mudava nada nele, e `commit_placements` só conta `pose_mudou` quando já havia entrada (ou regra «imagem»), por isso `_board_after_fill` só actualizou o `pl_mtime` e a imagem sem as peças ficou. Não é a hipótese «não escreveu eventos» sozinha: é essa mais a ausência das entradas no snapshot.
- Correção (`src/server.py`): `board_snapshot(..., placements=)` acrescenta `placement_digest` (célula, θ, pivô, dx, dy da entrada válida), `Gui._raster_snapshot()` usado por `_base`, e `_board_after_fill` compara o snapshot novo com o guardado (diferente → `ver=None` → remenda/recompõe; igual → só o `pl_mtime`). Cobre entrada nova, pose e chave (a entrada só vale se a chave valer, `placements()`); `entry_token` (contorno/recorte) não entra no snapshot: mantém-se como estava, o caminho do recorte já invalida pelos eventos de re-segmentação [NT que cubra todos os casos de token].
- Detalhe com zoom [V por leitura do código, NT por teste dedicado]: a chave das regiões é de conteúdo (`_region_parts`: pose da entrada ou «na_hora», `ReadyCache.key`), por isso uma entrada nova muda a chave e recompõe; não tem este problema.
- Testes (`tests/test_placements_completo.py`, 3 novos): snapshot distingue entrada nova/pose; cache em disco escrita como o arranque de 24/11 (imagem sem a peça X, snapshot sem a entrada de X) → o servidor volta a desenhar X (diferença média na célula < 2, resto igual a menos de perda JPEG); sem cache em disco o JPEG servido é byte a byte o do `compose_board` inteiro. O teste falha no código antigo (diferença 92 na célula) [V]. Nota: byte a byte só vale numa sessão; entre arranques a cache em disco é descodificada e recodificada (perda JPEG até ≈ 34 níveis na imagem toda, comportamento antigo, o «achado antigo» do HANDOFF).
- Projeto real [V]: sem servidor a correr (porta 8777 livre; o 8080 é o Docker), apaguei só `render/gui/board_60.*`, arranquei o servidor (tabuleiro completo em 20,0 s), `cache_vs_inteiro.py` dá 0 células > 12 (antes 254 > 6; o resto ≈ 6 é a diferença entre desenhar com `ready` e sem, igual em toda a imagem), captura Playwright de `/novo/` com a relva das filas 36–47 desenhada (`scratchpad/novo_relva.png`, não guardada no repositório). Servidor parado no fim.
- Consequência para o Tiago: no 1.º arranque depois de atualizar, o tabuleiro recompõe-se uma vez (≈ 20 s), porque os snapshots guardados têm outro formato.

**2. P0395 (G0033, S0013, `montado_p05_300dpi.jpg`, 2544 × 3504, bbox x 2032, y 3227, 459 × 277)**
- Decisão relida (`docs/decisoes.md` 2026-11-07 §3): o Tiago concordou que a flag `suspeita_recorte` apanhou uma linha escura real; nada a corrigir.
- Veredicto [V com imagem]: a peça está inteira dentro do scan (os 4 lados e as duas pontas visíveis; o canto inferior direito acaba ≈ 11 px, ≈ 1 mm, acima da faixa escura do fundo da folha). Não está cortada. A bbox acaba no limite inferior da folha (3504) e a flag é `touches_frame`: apanhada pela faixa escura do fundo, não por a peça sair do scan. Imagem: `docs/diagnostico/reports/P0395-2026-11-25.png` (recorte a 2× com margem de 200 px). Dados não mexidos; o recorte é decisão do Tiago (se a bbox/contorno incluir a faixa escura, corrigir o recorte; não é preciso digitalizar de novo).

**3. Painel e lista dos grupos (`src/web/novo/grupos.js`, `novo.css`)**
- Painel do grupo: cada peça tem «Corrigir recorte» (`/?peca=P####&contorno=1`, `target=_blank`, como no painel da peça) e «Algo está errado» (formulário dos 4 tipos, `POST /api/report` com a peça e sem célula, `vista: "novo/grupo"`); sem `P####` visível (o texto continua «Saco · nº»). Alvos ≥ 44 px (corrigido depois de os testes de layout apanharem 36 px).
- Lista: miniatura de 56 px por grupo, a mesma imagem `/api/grupos/{gid}.png` do tabuleiro; carregada em fundo por `carregarPngs` (só depois do «pronto» e do 1.º detalhe, os mostrados primeiro, os outros a seguir; o `src` só entra depois de descarregada). Mudança de comportamento a saber: antes só se descarregavam os grupos mostrados, agora todos (32 PNG, LRU de 48 no servidor); o custo no projeto real (PNG de 8 peças ≈ 0,4 s, +45 MB) não foi medido aqui [NT].
- Testes Playwright novos (2, `tests/test_gui_novo_f4.py`): linhas, hrefs, report gravado em `reports.jsonl` com peça/tipo/texto/vista e sem célula; miniaturas (2 `img`, ambas com `src` e `naturalWidth > 0`, ≤ 64 px).

**4.** `.tmp_diag/` apagada.

**Vigilância:** início 39 / 39, depois do servidor no projeto real 39 / 39, fim 39 / 39 (pieces / overlays; 39 folhas em `scans/`). `git status` no fim: só `Claude outputs/` por seguir (não é meu).

**Suite:** `-m pytest tests/` completa com os `slow`: 1.ª corrida (-x) parou em `test_gui_novo_f2.py::test_phone_layout_panels` (`#pm-grade button` sem caixa; passa 6/6 no código antigo, 2/3 depois e 6/6 a seguir, intermitente: o teste é o das animações do painel, sem ligação a grupos); 2.ª completa 901 passed, 1 skipped, 5 failed: 4 eram o meu botão de 36 px (corrigido) e 1 `test_m2_segundo_dedo…` com «initPointer is not defined» (o `board.js` não carregou: intermitente, passa isolado). Depois das correções: `test_gui_novo*`, `test_placements_completo`, `test_server*` → 2 falhas numa corrida (não identifiquei quais: só guardei o fim da saída) e 295 passed na repetição [V]. Não repeti a suite inteira de 16 min depois da última correção de CSS [NT].

**Decisões pendentes**
1. As miniaturas descarregam todos os grupos (antes só os mostrados): aceitas, ou só os da lista visível / só os de 1.º plano?
2. Entre arranques a cache em disco do tabuleiro é recodificada (perda JPEG); gravá-la sem passar pelo JPEG (PNG/npy) ou aceitar a perda.
3. As duas intermitências de GUI (`test_phone_layout_panels`, falha de carregamento do `board.js`) pedem uma ronda de estabilidade se continuarem a aparecer.
4. P0395: nada a fazer nos dados, a menos que o Tiago ainda veja o recorte mal.

