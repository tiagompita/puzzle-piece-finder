# HANDOFF — 2026-11-05 (2.ª ronda, fechada)

Lê isto primeiro numa sessão nova; no fim, atualiza-o e fecha o ficheiro do prompt em `docs/prompts/`.

## Estado
- **Commits:** `b894749` (.gitattributes), `fb487de` (abas no topo), `1b5c21e` («Editar report»); antes, até `bdbbfef` (aba «Guardadas», painel de Reports, docs).
- **Testes:** suite completa: **179 passed, 1 skipped** (75 s). Antes desta ronda: 160 passed, 1 skipped.
- **GUI** (`python -m src.server`): as 6 abas estão na **barra de topo** (Vai buscar, Guardadas, Lotes, Mesa, Importar, Reports) ao lado do nome/progresso; abaixo de 1181 px ficam numa 2.ª linha (rótulos curtos abaixo de 900 px); sem scroll horizontal. «Vai buscar» só tem peças com ≥ 1 vizinha ortogonal montada; as outras estão em «Guardadas». «Reports» é só de leitura; o botão do cartão/célula/peça é **«Editar report»** quando já há um report aberto para essa peça (ou célula sem peça), senão «Reportar».
- **Editar report = evento:** `reports.jsonl` é append-only; editar acrescenta uma linha `{"evento": "edicao", "id", "t", "tipo"?, "texto"?}` (`src.reports.edit_report`, `POST /api/report/{id}/edit`, evento de log `report_edited`). `read_reports` aplica as edições (`editado_em`, `n_edicoes`); `close_report` preserva as linhas de edição. Só reports abertos se editam.
- **Reports:** 22 abertos (R0001–R0012, R0018–R0027); R0013–R0017 fechados. Triagem abaixo; **nenhum fechado nesta ronda** (espera do Tiago).
- **Dados do Tiago por commitar:** `projects/alpes/` (log, reports, fetch, board, capturas) muda por uso da GUI; não é commitado por mim.
- **Item 2 (trim 0,48 mm)** refutado e removido (`docs/decisoes.md`); a cor ficou adiada.

## Espera pelo Tiago
- **Confirmação física de (3,32) e (3,33).** P0291 (G0021) e P0294 (G0023) estão digitalizadas, só como pista (`ocupada_legado`, fonte `tiago`). Indício do encaixe dos lados: **P0294 em (3,32) e P0291 em (3,33)**; o score do programa diz o contrário por 0,3 (7,25 vs 8,10), por isso decide a peça física. Escala não calibrada [NT]. Depois: `python -m src.confirm`.
- **Aprovar a triagem** (abaixo): fechar os 3 duplicados e dizer o que fazer com as secções por ancorar.

## Triagem dos 22 reports abertos (medido em 2026-11-05 sobre `projects/alpes`; nada foi fechado)
| Reports | O que é | Proposta |
|---|---|---|
| R0021, R0025, R0026 | duplicados exatos de R0010 (P0333 (6,22)), R0012 (P0657 (45,1)), R0011 (P0651 (44,1)): mesma peça, mesmo tipo, sem texto | **fechar como duplicado** (`--close … --nota "duplicado de R00xx"`) |
| R0002, R0003 | (3,32)/(3,33): digitalizadas, não ancoradas (secções de 1 peça G0021/G0023); células só com pista do Tiago | **explicar**; espera pela confirmação física |
| R0004–R0007 ((45,55) (44,55) (43,55) (42,55)), R0008, R0009 ((44,37) (45,37)) | células `ocupada_legado` só por foto (dúvida). Só G0044 (2 peças, melhor (44,55), score 21,7) e G0049 (P0573, (44,37), 17,7) propõem alguma; nenhuma secção propõe (45,55), (43,55), (42,55), (45,37). As peças estão digitalizadas mas não ancoradas | **explicar**; ancorar na aba Mesa se o Tiago concordar; ver o overlay `montado_p06`/`p07` para as células sem candidata [NT] |
| R0018–R0020 ((14,64) (28,64) (36,64)), R0001 (P0778 (4,10)) | recorte/verde («comida», verde visível); R0001 tem ainda rotação −3,9° | **corrigir** (pendente a) |
| R0011/R0012 (+R0025/R0026): P0651 (44,1), P0657 (45,1) | pose sem solução por cantos (método `image` / `none`), folgas de 1,3–2,5 mm com as vizinhas: defeito real de pose no canto inferior esquerdo | **corrigir** (pendente b) |
| R0022 (P0240 (1,63)) | inclinada (rotação 3,9°, lado reto 4,6°) | **corrigir** (pendente d) |
| R0023 (P0218 (32,64)), R0024 (P0083 (44,60)), R0027 (P0862 (14,61)) | rotação −6,8°, −4,8°, −4,4° (corners); R0024 com folgas até 2,4 mm | **corrigir** (pendente b: erro de rotação por cantos) |
| R0010 (+R0021): P0333 (6,22) | pose registada boa (rotação −2,0°, resíduo 0,53 mm, sem entrada em `placements.json`: registada na hora). **Hipótese [NT]:** se está «mal colocada» será identidade/posição e não desenho; só a confirmação física decide | **explicar**; confirmar fisicamente (já estava [NT] em CLAUDE.md) |

## Limitações conhecidas (abas / «Editar report»)
- **Um report aberto por peça:** com um report aberto numa peça (ou célula sem peça) o botão passa a «Editar report» e **não se consegue criar um segundo** (só editar). A edição substitui `tipo`/`texto` na leitura; os valores anteriores só ficam nas linhas `edicao` do `reports.jsonl`.
- **SSE:** `app.js` **não trata** os eventos `report_added` / `report_edited` (só ouve `hello`, `board_changed`, `fetch_changed`, `ingest_progress`, `prepare_progress`, `ready`). A aba Reports e o botão «Editar report» só atualizam depois de uma ação do próprio utilizador ou ao abrir a aba; um report criado noutra janela não aparece sozinho. **Pendente, não implementado.**
- Com o job-pill visível, a barra de topo a 1181–1280 px corta o nome do puzzle com reticências (teste `test_top_bar_no_overlap_with_job_pill_and_big_badges`).

## Próxima sessão
1. **Corrigir pose/recorte** (pendentes do `CLAUDE.md`, por ordem): (a) recorte «comido» (3,64) P0234 / (4,64) P0233 + R0018–R0020; (b) baseline de buracos (131 células > 5 %, 39 > 10 %) e erro de pose ~1 mm / rotação 363/588 > 1,5° (a rotação sai dos 4 cantos, ruidosa; P0651/P0657 sem solução por cantos); (c) (26,1)/(25,1): contornos a 0,06 mm mas (26,1) parece por baixo (ordem de desenho dos tabs); (d) (1,63) e (47,2) inclinadas; (e) usar IDs P0xxx nos reports ((44,55) e (40,63) não têm peça; P0778 está em (4,10)).
2. **Depois da aprovação do Tiago:** fechar os duplicados R0021/R0025/R0026 e os reports que passem a estar resolvidos.
3. **(3,32)/(3,33):** colocar com `src.confirm` quando o Tiago confirmar fisicamente.
4. **SSE dos reports** (`report_added` / `report_edited` no `connectEvents` de `app.js`) — ver limitações.

## Convenções que mordem
- Interpretador: `.venv\Scripts\python.exe` (o `python` do PATH não tem numpy). Em `Bash`, heredocs com muitos `'''` falham: escrever o script com a ferramenta Write.
- Commits em português, sem co-author.
- Suite completa passa dos 120 s: corre-a em segundo plano.
- Testes sobre o Alpes real usam uma cópia com o `log.jsonl` cortado a 2045 eventos (`tests/test_fetch_group_real.py`); nada se escreve em `projects/alpes`.

## Links
- Estado e plano: `docs/estado-e-plano.md`; arquitetura: `ARCHITECTURE.md`; GUI: `docs/gui-design.md`; decisões: `docs/decisoes.md`.
- Prompts por ronda: `docs/prompts/` (formato em `docs/prompts/README.md`); esta ronda: `docs/prompts/2026-11-05-abas-topo-editar-report-triagem.md`.
- Reports: `python -m src.reports --project projects/alpes --list`.
