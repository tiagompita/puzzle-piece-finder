# Registo da arte contra o tabuleiro (BUG 4) — 2026-11-01

**Problema.** A arte por baixo do tabuleiro (GUI, `render.compose_board`) e todos os testes de imagem (`locate.CellArt`: ΔE do gémeo, legado, borda, query) usavam a regra "o `bbox` = a grelha inteira", `[0, 42, 1600, 1115]`, o que dá 1,351 px/mm em x e 1,325 px/mm em y. Os desvios por imagem em `render/placements.json` (ddy a crescer de ≈ +1 mm nas filas 1–12 até ≈ +7 mm nas filas 12–36) apontavam para um erro de escala vertical.

**Modelo.** Uma única afim 2×3, mm do tabuleiro → px do ficheiro da arte (contínuo), em `puzzle.json` → `art.registration`; `bbox` fica como prior e como região de conteúdo do ficheiro (margem branca fora). Ponto único de entrada: `PuzzleProfile.art_matrix()` → `locate.load_art_rectified()` (retifica a arte para um raster que cobre exatamente 47 × 64 células à resolução nativa) → `CellArt.load` e `render._art_rgb`.

**Medição** (`python -m src.artreg`, `src/artreg.py`): render só das peças colocadas (registo por cantos, sem imagem, por isso independente da arte), reamostrado para a grelha a 2× a resolução da arte; por célula colocada, NCC de média zero com máscara em L\* da célula (+0,25 célula de margem quando os vizinhos também são peça) contra a arte retificada numa janela de ±1,5 célula (1.º passo, prior = bbox) e ±0,35 célula (passos seguintes, à volta do modelo atual); ponto aceite se NCC ≥ 0,5, pico fora da borda da janela e desvio-padrão de L\* ≥ 2; afim por IRLS (peso NCC; Huber 0,1 célula e depois Tukey 0,5 célula). Saída completa: `artreg.json` (224 pontos com resíduos antes/depois).

## Números [V]

575 células colocadas tentadas, 224 pontos medidos, 224 inliers (resíduo ≤ 0,3 célula). Convergência: mudança nos cantos da grelha 1,032 célula no 1.º passo, 0,006 no 2.º.

| Resíduo (células) | n | antes (bbox) mediana / p95 | depois mediana / p95 / máx |
|---|---|---|---|
| todos | 224 | 0,901 / 0,968 | 0,045 / 0,101 / 0,283 |
| filas 1–6 (céu) | 28 | 0,097 / 0,305 | 0,081 / 0,217 / 0,283 |
| filas 7–40 | 50 | 0,509 / 0,810 | 0,038 / 0,086 / 0,168 |
| filas 41–47 (relva) | 146 | 0,930 / 0,970 | 0,045 / 0,080 / 0,119 |
| coluna 1 | 28 | 0,632 / 0,945 | 0,046 / 0,077 / 0,082 |
| coluna 64 | 24 | 0,534 / 0,779 | 0,027 / 0,075 / 0,092 |
| col. 60–64, filas 1–20 | 6 | 0,253 / 0,329 | 0,011 / 0,132 / 0,168 |

Decomposição da matriz (QR, L = R(rot)·[[sx, k], [0, sy]]):

| | sx (px/mm) | sy (px/mm) | rotação | cisalhamento | translação (px) |
|---|---|---|---|---|---|
| bbox (antes) | 1,3514 | 1,3253 | 0 | 0 | (0, 42) |
| registo (depois) | 1,3511 | 1,3537 | −0,11° | 0,0005 | (−2,25, 43,21) |

Leitura: a escala em x estava certa; em y o bbox comprimia 2,1 %. Com o registo a escala é isotrópica (1,351 vs 1,354 px/mm, diferença 0,2 %), como se espera de uma impressão da mesma imagem. A grelha ocupa na arte y = 43,2 … 1182,1 px, mas o conteúdo do ficheiro acaba em y = 1157 (o resto é margem branca): **o ficheiro digital `1186441_1.jpg` acaba ≈ 1 fila antes da impressão; a fila 47 não tem arte** (cobre ≈ 46,0 das 47 filas; 64 células sem arte, colunas 1–64 todas com arte). Fica registado em `puzzle.json` → `art.registration`: `content_bbox` = `[0, 42, 1600, 1115]`, `rows_with_art` = `[1, 46]`, `cols_with_art` = `[1, 64]`.

Tratamento das células sem arte (seguimento, mesmo dia): `locate.rectify_art(..., return_valid=True)` devolve a máscara dos px com arte; `CellArt` guarda-a (`valid`): esses px ficam NaN na arte com margem (`cell_crop`, `de_cell` → dE = inf, `cell_scores` → inf), `cell_lab_mean` é NaN nas células com < 50 % de arte (`MIN_CELL_ART`) e `CellArt.has_art(l, c)` é False; `lab` continua finito (enchimento replicado) para os filtros de imagem inteira (`render.image_refine`). `twin.find_twin` com a célula da gémea sem arte dá a razão «imagem não testada: sem arte na célula (l, c) (fora do ficheiro da arte)», sem ΔE, e a decisão final nunca é `aceite` (regra do projeto: o desempate pela imagem é obrigatório, decidido de novo em 2026-11-02): `decision_shape` mantém-se, `aceite` → `ambigua`. Antes a fila 47 recebia um ΔE contra a fila 46 comprimida. `locate_group` e `legacy.placement_score` usam a mediana só dos membros com arte. No render (`render._art_rgb`) esses px são pintados no cinzento de fundo (40, 40, 40): sem riscas.

## O que se viu (`artreg_antes_depois.jpg`)

Três zonas, cada uma: peças colocadas | arte bbox | 50/50 ANTES | arte registada | 50/50 DEPOIS.

- **Relva BE (filas 42–47, col. 1–8):** ANTES dupla imagem clara: a fronteira arbustos/relva está ≈ 1 célula mais abaixo na arte do que nas peças (zoom a 80 px/célula com grelha: nas peças a relva começa na fila 44, na arte bbox a meio da fila 45, na arte registada na fila 44); o arbusto amarelo da col. 1 na fila 41 aparece na fila 42 na arte bbox e na 41 na registada. DEPOIS as texturas sobrepõem-se. A última fila na arte registada é cinzento de fundo (fila 47 fora da arte, ver acima; na primeira versão eram riscas da última linha replicada).
- **Céu (filas 1–6, col. 28–50):** sem diferença visível antes/depois (resíduo antes já 0,1 célula: o topo do bbox estava certo).
- **Coluna direita (filas 1–20, col. 60–64):** diferença pequena à escala da figura (a linha da montanha mexe ≈ 0,2–0,4 célula); os números da coluna 64 (0,53 → 0,03) é que a sustentam.

## Efeito na lista «ir buscar» [V]

`python -m src.query` em duas cópias de `projects/alpes` (mesmo código; só `puzzle.json` difere). As 18 propostas gémea colocada → solta (15 `aceite`, 3 `ambigua`) e as 3 suprimidas são as mesmas, com as mesmas decisões e margens (a forma decide; a imagem é teste 1-contra-1). O ΔE muda pouco (|Δ| ≤ 0,86, mediana ≈ 0) porque as células-alvo são todas do céu (filas 2–4), onde o bbox já estava alinhado. O efeito grande do registo é nas filas 7–47 (relva, legado, borda e GUI), que a lista atual não exercita.

## Limites e não verificado

- [V] fila 47 sem arte no ficheiro digital (≈ 1 fila em falta em baixo): tratada como «sem arte» (ver acima); as consultas da fila 1 (gémea na fila 47) só têm forma e por isso são `ambigua` por regra (a pose prevista não muda: E-sym A1→B2 20/20, resíduo mediano 0,49°). Isto não aparece na lista atual porque a fila 47 está toda colocada.
- [NT] efeito no legado (`legacy.solve_project_sections`), na borda (`border.py`) e no registo por imagem do render (`register_all`): só correm no próximo `ingest_all` / `render --register --force`; não re-executados nesta ronda.
- [NT] confirmação física: o registo assenta nas 575 peças colocadas tal como estão no índice; uma peça mal colocada só pesa como um ponto (IRLS), mas não foi verificado à mão.
- O canvas da janela de célula em `CellArt` passa de 43 × 41 para 43 × 42 px (a célula tem agora 25,0 × 24,23 px de arte em vez de 25,0 × 23,72; a janela em células é a mesma).

Reproduzir: `python -m src.artreg --report docs/diagnostico/arte` (escreve `puzzle.json`; `--dry-run` não escreve) e `python tools/diagnostico/arte/artreg_figura.py`.
