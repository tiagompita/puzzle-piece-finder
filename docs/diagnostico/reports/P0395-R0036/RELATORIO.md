# R0036 / P0395 — «mal lida» depois do contorno manual (2026-11-25, bloco C)

Imagens nesta pasta; guiões em `tools/diagnostico/reports/p0395_r0036/` (correm na raiz do repositório; os de
identidade numa cópia do projeto feita com `tools/diagnostico/gui/guarda.py`).

## C1. Onde a leitura se estragava

A linha de 22:16:40 de `overrides.jsonl` é a que está em uso (`latest_overrides` → `t 2026-11-25T22:16:40`,
`convencao: "aresta+indice"`, sem `indice: "automatico"`). Leva duas silhuetas:

- `aresta_px`: a aresta que o Tiago pintou (laranja no editor). É a peça exata (`01_folha_contorno.png`, magenta).
  `shape.analyse` dela: **BFBT, cordas 17,90 / 17,71 / 17,12 / 18,22 mm, 304,2 mm²**. Nenhum passo a altera; o
  ecrã (`aresta_rgba`) usa-a tal e qual (`03_display_clean_*.png`).
- `contour_px`: o índice que o **código do editor derivou** dela no gravar (`strokes.normalizar`). Saiu igual ao
  contorno automático (374,12 contra 374,06 mm²): inclui a faixa escura do scanner no fundo da folha e o papel
  verde que a liga à peça, e enche a baía de baixo (`01_folha_contorno.png`, vermelho; `01b_zoom_fundo.png`).
  Chega a 13,85 mm da aresta (17,4 mm² a mais de 2 mm). Nas outras 34 linhas com aresta o índice fica sempre a
  ≤ 1,94 mm da aresta (0,00 mm² além de 2 mm).

Causa no código: o halo da convenção do índice é `H = (auto ∧ ¬S0) ∪ núcleo de sombra`, sem limite de distância.
Com um contorno automático estragado, a faixa do scanner e o papel contam como «halo»; os traços «fundo» do Tiago
nessa zona foram tratados como traços de sombra e ignorados, e `normalizar` repôs o automático.

Passo a passo, partindo da aresta como verdade:

| passo | estado | números |
|---|---|---|
| contorno lido para o índice (npz, forma, gémea, encaixe, pose) | **estragado aqui**: `contour_px` derivado | 37,3 × 22,6 mm |
| cantos/lados (`shape.analyse`) | consequência | um canto na faixa do scanner (`06_cantos_lados_antes.png`) |
| classe/cordas | consequência | BBFT 22,00 / 20,21 / 21,36 / 18,18 mm |
| rotação | consequência | θ do grupo +8,19° («torta»), centro do corpo deslocado 5,9 mm para a direita |
| bbox/recorte | consequência | bbox 459 × 277 px com a faixa (`02_recorte_crops_antes.png`) |
| PNG do grupo / captura | consequência | peça rodada e cortada à esquerda (`04_grupo_G0033_antes.png`, `05_captura_R0036.png`) |

## C2. Correção

`src/strokes.py`: `INDICE_HALO_MAX_MM` (= `SOMBRA_BANDA_MM`, 2,0 mm), `INDICE_FORA_MIN_MM2` (1,0 mm²),
`indice_fora_mm2`, `limitar_indice` (aresta ∪ pixels do índice a ≤ 2 mm dela que não são papel; maior componente,
buracos cheios; a aresta inteira fica sempre dentro). `src/overrides.py`: `index_contour_from` (puro) /
`index_contour` (com cache): devolve `contour_px` **o mesmo objeto** quando não há aresta ou o índice está dentro
da banda; só lê contra a aresta quando passa dela. Usado onde o índice de uma linha manual é aplicado
(`render.rebuild_assets`, `render._manual_pending`), no ponto de partida do editor (`server._dense`) e no gravar
(`server._solve_a2`: um índice novo nunca é gravado fora da banda). A linha do Tiago não muda e nada é acrescentado
a `overrides.jsonl`.

Depois (cópia do projeto): **BFBT, cordas 18,31 / 18,53 / 18,23 / 18,38 mm, 359,4 mm², bbox 321 × 267 px**, θ do
grupo −8,40° (o ângulo do corpo da aresta é 8,5°), PNG do grupo inteiro e direito (`*_depois.png`).

Teste: `tests/test_indice_aresta.py` (3 testes; falharam antes: o caso P0395 e o caso sintético com a faixa
ligada por uma ponte de papel, 24,35 mm² do índice além da banda). E-sym: o caminho da segmentação não mudou
(nenhum ficheiro de segmentação tocado); `tests/test_segment_scan_esym.py` e `tests/test_twin_real.py` verdes.

Outras peças: na cópia, das 10 linhas manuais ativas (todas com aresta) as 9 que não são P0395 dão `contour_px` idêntico (mesmo objeto); `rebuild_piece`
de P0395 mudou só `S0013.npz` na peça P0395 e só `crops/P0395.png` (0 diferenças nas outras 50 peças de S0013 e
em todos os outros npz), 1 evento `piece_resegmented` motivo `manual`; invariantes OK.

## C3. Identidade

Forma corrigida contra as 266 peças com lado F ou em célula de borda (`shape.free_dist`), e imagem (NCC de L*
desfocado, P0395 registada sobre a candidata por `shape.register_rigid`, procura ±20 px e ±3°):

| # | peça | estado / célula | free (mm) | NCC imagem | nota |
|---|---|---|---|---|---|
| 1 | P0782 | em_seccao, sem célula | 0,390 | 0,25 | céu; já `same_as` P0005 (1,9) = gémea de (47,56) |
| 2 | **P0021** | colocada **(47,56)** | 0,470 | **0,965** | relva; scan E-sym `coluna5-24_folhaB` |
| 3 | P0005 | colocada (1,9) | 0,482 | 0,08 | céu; gémea de (47,56) |
| 4 | P0755 | em_seccao, sem célula | 0,790 | −0,26 | |
| 5 | P0820 | colocada (1,3) | 0,847 | −0,27 | |
| – | P0426 | em_seccao (`same_as` P0027 (47,52)) | 0,864 | 0,585 | melhor relva a seguir |

Pela forma sozinha não há margem (re-scan e gémea são iguais na forma, como esperado: 0,27 vs 0,29–0,39 mm).
Com a imagem, P0021 é única: NCC 0,965 contra ≤ 0,585; entre as peças de relva, d1 = 0,470 e d2 = 0,864 mm
(razão 1,84 ≥ `margin_min` 1,5). Arte: a fila 47 não tem arte (`rows_with_art [1, 46]`), por isso o teste contra
a arte na célula não se pode fazer. Figura: `07_identidade_top5.png`.

Hipóteses alternativas: troca (a peça em (47,56) é outra) — rejeitada: P0021 tem a mesma imagem que P0395
(0,965), é a mesma peça física. P0395 não ser de borda — rejeitada: com o índice corrigido é BFBT com um F
(18,31 mm), a aresta do Tiago também dá BFBT.

Conclusão: P0395 é um segundo scan de P0021 (47,56) numa folha de peças montadas. O ingest do legado marca estes
casos com `same_as` (132 no log, p. ex. P0782 → P0005, P0426 → P0027); P0395 escapou porque a forma estava estragada.

## C4. Dados

A ação de duplicado do estado é `same_as` (`Project.mark_same_as`), que **não tem desfazer** (não há evento que a
retire); ancorar G0033 em (47,56) poria uma segunda peça numa célula ocupada. Pela regra do prompt não mexi nos
dados para a identidade: decisão pendente.

## C5. R0036

Fica aberto: a leitura está corrigida e verificada, mas a identidade só fica resolvida nos dados com o
`same_as` P0395 → P0021, que espera pela decisão do Tiago (ação sem desfazer).

## C6. Outras peças com contorno manual

Nenhuma: as outras 34 linhas com aresta (9 ativas para o índice, 25 só de ecrã) têm o índice a ≤ 1,94 mm da
aresta; `index_contour` devolve-lhes `contour_px` sem alteração.

## Projeto real

Depois do commit `d2e49e9`: `render.rebuild_piece(P0395)` (o mesmo caminho que aplica um contorno manual pendente)
escreveu **1 evento** `piece_resegmented` (2026-11-25T23:38:59, P0395, motivo `manual`): BFBT, cordas 18,31 /
18,534 / 18,227 / 18,375 mm, bbox [2036, 3229, 321, 267], 359,43 mm² (igual à cópia). `overrides.jsonl` byte a
byte igual ao de antes; invariantes OK; `pieces`/`overlays` 39/39. Identidade (`same_as`) não aplicada.
