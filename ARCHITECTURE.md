# ARCHITECTURE — Puzzle Piece Finder

_Gerado em 2026-10-29 a partir do código real (HEAD `c35442f`; atualizado após o M0) e **atualizado em 2026-11-01** (módulos do M4/M10/M12 e do legado, projeto `projects/alpes/` regenerado por `tools/diagnostico/legado/ingest_all.py`), não da documentação. A skill `project-cartographer` referida no pedido não existe em `.claude/skills/`; este ficheiro segue o mesmo espírito (mapa de módulos, fluxo de dados, contratos, pontos de entrada, dados, testes) feito à mão._

## 1. O que o sistema faz hoje (fluxo real)

```
foto/scan de várias peças ──► segmentation.segment_pieces (fotos) | segment_scan (scans) ──► lista de peças
                                                               {image, mask, contour, bbox, angle, is_cluster}
                                                                      │
                                                     edges.classify_pieces (in place)
                                                                      │ piece_type ∈ {interior, edge, corner, suspect, cluster}
                                                                      ▼
imagem de referência (caixa) ──► matching.multi_scale_template_match(ref, piece, num_pieces, piece_mask, piece_edges)
                                        │  assinatura zonal Lab 4×4 + textura (texture.gradient_signature) + prior de borda
                                        ▼
                               {best_position, size, rotation, candidates[≤5], confidence 'high'|'ambiguous', confidence_gap}
                                        │
                     gui.py (overlay no canvas, Export JSON)  /  visualization.annotate_results (ponto vermelho)
```

Só a GUI liga as etapas de ponta a ponta. A CLI (`src/main.py`) usa apenas o comparador ingénuo `matching.compare_images` (diferença média de pixels redimensionados), que não localiza nada.

**Fluxo das gémeas (2026-11-01, objetivo atual; não passa pela GUI):**

```
scan 300 dpi ──► ingest (segment_scan → shape.analyse → peça P#### no índice, n_no_lote, recorte) ──► projects/<id>/log.jsonl
foto do tabuleiro ──► photo (mapa M14 1/0/−1) ──► células ocupada_legado / vazia
página do legado ──► legacy.ingest_page (componentes por lados → Section) ──► solve_project_sections (gémeas entre páginas) ──► colocada/legado_scan
query ──► (0) borda em falta (1) gémea colocada: twin.find_twin(colocada, soltas) + imagem 1-contra-1 na célula gémea
          (2) pares soltas↔soltas + locate.pair_locate (3) posição conhecida (4) secções por ancorar ──► fetch.md, fetch_<lote>.jpg
confirm ──► log (placed / position_known / anchor) ──► query incremental
```

## 2. Mapa de módulos (`src/`, ≈ 9 800 linhas)

| Módulo | Linhas | Papel | Depende de | Estado observado (2026-10-29) |
|---|---|---|---|---|
| `segmentation.py` | 1750 | Deteção/recorte de peças numa foto: distância Lab ao fundo (modelo de fundo pela margem ou global), histerese + conetividade, limpeza morfológica, seam-carve/watershed para peças encostadas, bisect forçado, encolhimento de sombra, refinamento de fronteira, rejeição de franja de fundo, normalização de rotação (`minAreaRect`). Também `piece_to_rgba`, `save_pieces`, `segment_pieces_from_file`. **`segment_scan`** (2026-10-31, caminho oficial para scans de flatbed): separação de `segment_pieces` + fronteira por limiar Lab a resolução total (fundo pela orla, d > 28, abertura/fecho 0,42/0,76 mm) no Voronoi das peças e numa banda de 1,5 mm; sem encolhimento de sombra, refinamento nem rejeição de franja (mordiam as peças escuras). | cv2, numpy, PIL | Funciona bem em scans de flatbed com fundo saturado (≈60/64 peças, 0 clusters). Degrada em fundo pálido e em fotos de telemóvel com peças juntas. O teste sintético falhava desde `f6cc2b7` (Otsu do OpenCV no topo de um vazio do histograma + histerese); corrigido no M0 com `_otsu_plateau_threshold`. |
| `edges.py` | 194 | Classifica a peça pelo nº de lados retos do `minAreaRect` (`_STRAIGHT_RATIO=0.09`). Não extrai perfis de lado nem tab/blank. | cv2, numpy | **Obsoleto** (substituído por `shape.py`; só a GUI antiga o chama). Falha 2/3 peças de bordo reais e marca 8/20 nos scans dos gémeos. A remover com a GUI nova. |
| `profile.py` | 177 | `PuzzleProfile` (`projects/<id>/puzzle.json`): grelha, célula nominal, regra de simetria (`twin`, `twin_rotation_deg`: a única implementação), lados F por célula, fundo, dpi, arte + bbox, `calibration` (t95/tmax por modalidade, cordas por tipo, `margin_min`). | — | Verificado 2026-11-01: perfil `alpes` (64 × 47, rot180) usado por toda a ingestão; `tests/test_profile.py`. |
| `shape.py` | 498 | Forma em mm a partir do contorno: 4 cantos, lados (corda, tipo F/T/B, perfil), classe canónica, vetor free; `analyse`, `free_dist`, `corner_dist`, `chord_pass` (2 mm no F e adjacentes, 1 mm nos outros), `side_complement`, `transform_contour`. Puro. | numpy, cv2 | Verificado: E-sym com `src.shape` = protótipo (A2/B2 0,383 mm, 20/20, commit `2dd8a37`); 2026-11-01: rotação dos 4 conjuntos GT decidida pelos lados (F 20/20 + T↔B 19/19 em A1 e B2, T↔B 30/30 em BE, 43/45 em BD). |
| `locate.py` | 538 | Imagem contra a arte, célula a célula: `CellArt` (arte recortada, Lab, desvio L\* do scanner), `render_item`, `de_cell`, `cell_scores`, `locate_group` (bloco com células relativas, 4 rotações, regras F, prior M14), `pair_locate`, `snap_theta`. | cv2, numpy | Teste de consistência de cor, não identidade. 2026-11-01 [V]: o ΔE médio na célula conhecida **não separa** as 4 rotações dos conjuntos GT (diferenças ≤ 0,6 ΔE; escolhe a errada em A1, B2 e BD). |
| `twin.py` | 309 | `find_twin(query, candidates, profile, modality, art)`: classe → cordas por tipo → `free_dist` (d₁, margem d₂/d₁) → decisão por modalidade (t95/tmax) → imagem obrigatória 1-contra-1 na célula gémea; `TwinItem`, `shape_distances`, `same_shape`, `offset_shape`. | `shape`, `locate`, `profile` | E-real-2 reproduzido (2 propostas, 0 aceites em 10 608 negativos; `tests/test_twin_real.py`, `slow`). 2026-11-01 em `projects/alpes/`: 104 gémeas pendentes × 99 soltas do lote 1 → 20 propostas (14 `aceite`, 6 `ambigua`) **[NT: por confirmar fisicamente]**. |
| `state.py` | 1005 | Estado persistente do projeto: `Project` (create/open/save), `log.jsonl` só-acrescentar (a fonte de verdade; `apply` = `replay`), `Board` 47 × 64, `Piece`/`Pair`/`Section`/`Photo`, operações (`place`, `set_position_known`, `register_section`, `anchor_section`, `register_photo`, `mark_same_as`, `discard`…), derivados (`pending_twins`, `holes`, `stats` com `p_twin_placed`), `check_invariants`. | `profile`, numpy | Verificado 2026-11-01: 908 peças, 26 scans, invariantes OK (`board == replay(log)`, também em disco), reabrir → a mesma lista; `tests/test_state.py` (15). |
| `legacy.py` | 1355 | Páginas do legado em vista explodida: componentes por arestas validadas (T↔B, `side_complement`), registo contra a arte (`locate_group`), consistência entre páginas por gémeas + células partilhadas + M14 (`solve_pages`), página duplicada, `match_gt` (só medição); integração: `ingest_page`, `solve_project_sections`. | `shape`, `locate`, `twin`, `ingest`, `state` | 2026-11-01 [V]: 39 secções ancoradas (540 peças: 453 colocadas + 87 que são as próprias peças GT; o LEGADO.md tinha 538), 30 secções `montado` ambíguas (+ a p13, toda `same_as` da p04), 32 grupos `blocos` por ancorar; `tests/test_legacy.py`. |
| `ingest.py` | 307 | `python -m src.ingest`: `segment_scan` → fragmentos < 150 mm² fora → `objeto_duplo` → `shape.analyse` → `grid_order` (`n_no_lote` contínuo por lote) → recorte RGBA → overlay numerado; `--known-cells` (GT pelo nº do overlay), `--montado/--blocos pNN [--no-auto-anchor]`. | `segmentation`, `shape`, `state`, `legacy` | 2026-11-01 [V]: 26 scans; lote 1 = 35 + 15 + 42 + 8 = 100 peças, 0 fragmentos. |
| `photo.py` | 157 | `python -m src.photo`: mapa de ocupação (M14) a partir da foto ou de `--from-json`, `--fix L,C=V`, reconciliação com o tabuleiro. | `state`, `tools/diagnostico/ocupacao` | 2026-11-01 [V]: F0001 = `ocupacao_2026-10-31.json` + (1,29)=0, (1,34)=1 → 582 células ocupadas. |
| `query.py` | 468 | `python -m src.query`: borda em falta → gémea colocada (`find_twin`) → pares entre soltas (+ `pair_locate`) → posições conhecidas → secções por ancorar (as feitas só de re-scans `same_as` são omitidas); `fetch.md`, `fetch.json`, `fetch_<lote>.jpg`, evento `fetch_listed`. | `twin`, `locate`, `state` | 2026-11-01 [V]: 151 s no projeto `alpes`; determinista (reabrir → o mesmo `fetch.md`). |
| `confirm.py` | 191 | `python -m src.confirm`: `--cell`, `--reject`, `--position-known`, `--anchor/--unanchor`, `--discard`; regra do par; re-consulta incremental. | `state`, `query` | 2026-11-01 [V]: as 2 confirmações físicas do E-real-2 gravadas (P0147 em (2,61), P0099 posição conhecida (5,60)). |
| `matching.py` | 1087 | Motor principal `multi_scale_template_match` (linhas 645–1082): downscale da referência para ≈46 px/peça, assinatura zonal Lab 4×4 por janela via imagens integrais, varrimento em banda de escalas derivada de `num_pieces` × 4 rotações, mínimos locais + NMS, refinamento a stride 1, re-rank por textura e prior de borda, gap diferencial → `confidence`. Mantém também o legado: `compare_images`, `basic_metrics`, `sliding_window_search`, `estimate_piece_scale_factors`. | numpy, PIL, cv2 (import local), `features`, `texture` | Funciona como desenhado; a sua utilidade depende da arte (ver `docs/estado-e-plano.md`). O prior de borda assume que **a arte preenche a referência**, o que é falso para `images/puzzles/PuzzleOriginal.jpeg` (foto da caixa com margem branca). |
| `texture.py` | 233 | Assinatura de orientação de gradiente (Sobel em L, 8 bins, por célula 4×4, normalização L2, células planas a zero) e distância entre assinaturas. | cv2, numpy | Funciona; usado pelo motor quando `use_texture=True` (default). |
| `visualization.py` | 185 | `annotate_results` (ponto vermelho + rótulo no centro provável) e `save_annotated_image`. Puro, PIL. | PIL | Funciona. |
| `gui.py` | 1268 | Tkinter: Load Puzzle, Load Pieces, Segment Photo, Compute Metrics, Match, Match All, Cancel, Clear Overlay, Export Results (JSON), Save Annotated Image, Save Pieces; entradas W/H em cm e nº total de peças; overlays alta-confiança vs ambíguo. Threads para segmentação e matching. | todos os anteriores (imports locais) | Funciona. **Não passa `piece_edges` ao motor** (o prior de borda só é exercido pelo harness `eval_matching.py`). Sem métodos duplicados (a nota do CLAUDE.md está desatualizada). |
| `features.py` | 48 | Helpers puros: tamanho, área, cor dominante por frequência, distância de cor, px/cm. | PIL | Funciona; o "scoring" referido no CLAUDE.md como crítico não existe aqui (o scoring vive em `matching.py`). |
| `acquisition.py` | 112 | Seleção interativa de ficheiros por `input()` para a CLI. | PIL | Funciona; caminhos default `images/puzzles` e `images/pieces` existem. |
| `main.py` | 19 | CLI mínima: `load_puzzle` + `load_piece` + `compare_images`. | `acquisition`, `matching` | Corre com `python -m src.main` (documentado); `python src/main.py` falha por import relativo (esperado). |

Constantes afinadas que importam ao ler resultados: `_SEARCH_TARGET_PIECE_PX=46`, `_ZONAL_GRID=4`, `_CONF_GAP_HIGH=0.12`, `_CONF_STRUCT_HIGH=4.0`, `_TEXTURE_LAMBDA=0.5`, `_EDGE_PRIOR_PENALTY=0.10` (matching); `_STRAIGHT_RATIO=0.09` (edges); `luma_weight=0.075`, `chroma_weight=1.0`, `max_working_dim=1600` (segmentation).

## 3. Contratos de dados

**Peça** (saída de `segment_pieces`, enriquecida por `classify_pieces`):
`index, image (PIL RGB, fundo preenchido com a cor média), mask (PIL L), bbox (x,y,w,h em coords da foto), area_px, angle, contour (N×2 em coords da foto), is_cluster, touches_frame, piece_type, straight_sides, sides[4], side_deviations[4], min_area_box`.

**`segment_scan`** devolve o mesmo dict que `segment_pieces` (mesmas peças, ordem e índices) mais `mm_per_px = 25,4/dpi`, `method = 'scan'` e `scan_background_lab`; cada peça ganha `refined` (False se o limiar não tinha píxeis na banda, e nos clusters, que mantêm o contorno de `segment_pieces`) e `roughness` (perímetro / perímetro suavizado, como `rough` do `shapelib`; só diagnóstico, nunca filtro). Enviesamento conhecido: o contorno inclui a sombra projetada (corda mediana 18,6 mm contra 18,2 nominal; E-sym em `docs/diagnostico/gemeos/RESULTADOS.md`).

**Resultado de matching**: `best_position (x,y)`, `piece_size_final (w,h)`, `rotation ∈ {0,90,180,270}`, `scale`, `refined_similarity ∈ [0,1]`, `candidates` (até 5: `position, size, rotation, similarity, score, cost_comb, d_grad, edge_penalized`), `confidence`, `confidence_reason`, `confidence_gap`, `piece_structure`. Coordenadas no referencial da imagem de referência passada. Erro → `{'error': str}`.

**JSON de exportação** (GUI): `timestamp, puzzle_info{size,mode}, pixels_per_cm?, pieces[{id, position, size, similarity, scale, path, confidence, confidence_reason, candidates[]}]`.

**`Shape`** (`shape.analyse(contour_px, mm_per_px)`, tudo em mm): `ok` (4 cantos), `corners`, `c` (contorno reamostrado, ccw), `sides[4]` (`Side`: `kind` ∈ F/T/B, `chord_mm`, `p0_mm`, `p1_mm`, perfil), `cls` (classe canónica, p. ex. `BTBT`), `vec`, `z` (vetor free complexo), `area_mm2`, `n_flat`, `roughness`, `centroid_mm`, `body_angle_deg`; `to_arrays`/`from_arrays` (npz sem pickle). Rotações na convenção complexa `z·e^{iθ}` (y para baixo: θ > 0 roda no sentido horário no ecrã).

**`TwinItem` / `find_twin`** (`src/twin.py`): `TwinItem(id, shape, rgba=None, theta_deg=None, cell=None)`; `theta_deg` é a rotação que leva o recorte (referencial do scan) à pose no tabuleiro (conhecida nas GT; `None` nas soltas e, por agora, nas peças colocadas pelo legado). `find_twin(query, candidates, *, profile, modality='silhueta_silhueta'|'celula_silhueta', art=None, topk=3)` → `{candidates: [{id, d1_mm, phi_deg, chord_ok, image: {dE, ncc, pctl, theta_deg, p90} | None, twin_cell}], decision: 'aceite'|'ambigua'|'sem', decision_shape, margin, twin_cell, n_class, n_pass, modality, reasons}` ou `{'error'}`.

**`Project`** (`src/state.py`, pasta `projects/<id>/`): `project.json` (id, `schema_version`, `next_ids`), `puzzle.json`, **`log.jsonl`** (só acrescentar, a fonte de verdade: `scan_added`, `piece_added`, `placed`/`unplaced`, `position_known`, `section_registered`/`section_anchored`/`section_unanchored`, `photo_registered`, `cell_occupied_by_photo`/`cell_cleared_by_photo`, `same_as`, `piece_discarded`, `pair_*`, `twin_confirmed`/`twin_rejected`, `fetch_listed`, `position_placeable`), vistas reconstruíveis (`board.json` = replay, `scans/S####.json`, `sections/G####.json`, `photos/F####.json`, `pairs.json`, `fetch.md`/`fetch.json`) e ficheiros pesados fora do git (`pieces/S####.npz` com `Shape` + contorno px, `crops/P####.png`, `overlays/`, `fetch_*.jpg`). Peça: `id, scan_id, index_in_scan, lote, n_no_lote, estado ∈ {solta, emparelhada, posicao_conhecida, colocada, em_seccao, descartada}, celula, theta_deg, seccao_id, same_as, flags, cls, n_flat, chords_mm, bbox, crop_path, mean_lab`. Célula: `{estado ∈ vazia|ocupada_legado|colocada, peca_id, fonte ∈ log|foto|legado_scan, foto_id}`. Operações inválidas levantam `StateError` (nada é gravado); invariantes em `check_invariants`.

## 4. Pontos de entrada e ferramentas

| Comando | Faz | Estado |
|---|---|---|
| `python -m src.gui` | GUI completa | funciona (precisa de Tk) |
| `python -m src.main` | CLI ingénua (`compare_images`) | corre, mas não localiza peças |
| `python eval_matching.py` | Harness A/B do motor em `images/pieces/IMG_2114.DNG` (64 peças, foto de telemóvel) | corre; escreve em `$PPF_SCRATCH/eval_matching` (default `./scratch`) |
| `pytest tests/` | testes sintéticos + reais com marcador `slow` (`test_segment_scan_esym.py`, `test_twin_real.py`; correm por omissão, `-m "not slow"` exclui) | 73 testes (69 rápidos + 4 `slow`), verdes em OpenCV 4.11 em 2026-11-01; OpenCV 5.0 só verificado até 2026-10-31 |
| `python -m src.ingest <scan> --lote N [--known-cells gt.json]`; `python -m src.ingest <página> --montado pNN` ou `--blocos pNN` (`--no-auto-anchor`) | ingere um scan de soltas ou uma página do legado no projeto | funciona (2026-11-01) |
| `python -m src.photo --from-json <mapa.json> --fix L,C=V …` (ou `<foto.jpg>`) | regista o mapa de ocupação M14 e reconcilia o tabuleiro | funciona |
| `python -m src.query [--lote N] [--no-image]` | reavalia a memória; escreve `fetch.md`, `fetch.json`, `fetch_<lote>.jpg` | funciona (151 s no projeto `alpes`) |
| `python -m src.confirm P#### --cell L C` (ou `--reject`, `--position-known L C`, `--anchor G#### L C --rot R`, `--unanchor G####`, `--discard`) | grava uma confirmação e re-consulta só o afetado | funciona |
| `python tools/diagnostico/legado/run_legado.py` | análise do legado sem tocar no projeto (`legado_resultados.json`, figuras) | funciona (cache `$PPF_SCRATCH/legado/*.npz`) |
| `python tools/diagnostico/legado/ingest_all.py` | **regenera `projects/alpes/`** (apaga tudo menos `puzzle.json`): foto F0001, GT (A1, B2, BE, BD), lote 1, 2 confirmações, 18 páginas do legado, solução conjunta, `query`, comparação com o M14, determinismo | funciona (11 min: ingestão 362 s, query 151 s, determinismo 153 s) |
| `examples/basic_usage.py` | 4 exemplos sobre `.DNG` | parse OK; não corrido ponta a ponta |
| `tools/diagnostico/` | scripts do diagnóstico de 2026-10-29 (segmentação, forma, matching); ver o README aí | correm com `PPF_SCRATCH`; regeneram `docs/diagnostico/` |

Dependências: `opencv-python==4.11.0.86`, `numpy<2.3`, `Pillow<12` (fixadas no M0; decisão 8.2.7) e `pytest` em dev. Python 3.13 na máquina do utilizador; sem venv no repositório.

## 5. Dados de teste no repositório

| Conjunto | O que é | Uso |
|---|---|---|
| `images/puzzles/PuzzleOriginal.jpeg` | 8064×6048, **foto da caixa** do Clementoni 3000 "Os Alpes" (margem branca, texto, ligeira perspetiva) | referência default do harness e dos testes |
| `images/puzzles/1186441_1.jpg` | 1600×1200, arte limpa do mesmo puzzle (imagem de produto) | não usada pelo código |
| `images/pieces/digitalização_fundo_*.jpg` | 11 scans A4 a 300 dpi (2480×3504; dois a 600 dpi) das **mesmas ~64 peças** em 11 fundos; `*_grupoN` são outros conjuntos, alguns já montados em grupos | segmentação / forma (escala absoluta conhecida: 1 px = 0,0847 mm a 300 dpi) |
| `images/pieces/segmented_pieces_<fundo>/` | recortes PNG gerados pelo Save Pieces | ground-truth parcial de segmentação (feito pelo programa, não à mão) |
| `images/pieces/IMG_21xx.DNG` (12, ignorados pelo git) | fotos de telemóvel, 64 peças em papel branco + fotos de grupos | harness de matching |
| `images/pieces/Phone Link/*.jpeg` | 5 fotos de telemóvel: caixa (2100), tapete com centenas de peças soltas e secções montadas (2108–2111) | nenhum ainda |
| `images/pieces/legado/` | 15 páginas `montado_pNN` + 3 `blocos_pNN` a 300 dpi (o legado montado à mão, em vista explodida; `montado_p13` = `montado_p04` digitalizada outra vez) | `src/legacy.py`, `ingest_all.py` |
| `images/board/` | 2 fotos de telemóvel do tabuleiro (2026-10-31) | M14 (`docs/diagnostico/ocupacao/ocupacao_2026-10-31.json`) |
| `images/pieces/ereal2_ceu_*.jpg` | 100 peças de céu soltas (4 folhas) = lote 1 do projeto | E-real-2, `projects/alpes/` |
| `projects/alpes/` | o projeto real: perfil, log, tabuleiro, scans, secções, foto, lista «ir buscar» (só os JSON/MD versionados) | `src/state.py` e CLIs |

**Ground truth de posição que existe (2026-11-01):** E-sym A1 (borda de cima, c5–24) e B2 (borda de baixo, as gémeas): 40 peças, `images/pieces/gemeos_2026-10-30.md`; canto BE (20 interiores, `docs/diagnostico/gemeos/ereal2_gt_BE.json`) e BD (28 interiores, `ereal_gt.json`); a secção do canto superior esquerdo (`seccao_celulas.json`, só frente); as 2 confirmações físicas do E-real-2 (`ereal2_confirmacoes.json`). No projeto `projects/alpes/` estas 90 peças (88 GT + as 2 confirmadas) entram com silhueta (89 `colocada`, 1 `posicao_conhecida`). O legado (540 peças em secções ancoradas) **não** é GT: a precisão medida é 71/71 nas `alta` com GT (`docs/diagnostico/legado/LEGADO.md`).

## 6. Desalinhamentos documentação ↔ código

- `README.md` descreve `piece_0.png…piece_23.png`, `puzzle.json`, `data/`, segmentação "in development", GPU/CUDA, overlap detection: tudo desatualizado.
- `CLAUDE.md` fala em "métodos duplicados na GUI", "caminhos partidos em acquisition.py" e "imports relativos que impedem os comandos documentados": não se reproduz em HEAD.
- `docs/RELATORIO.md`/`ROADMAP.md` descrevem a arte como "deserto/areia"; a arte é a paisagem alpina (Val di Funes) — as peças creme/cinza são céu e nuvens.
- A skill `cv-visual-verification` exige a suite pytest verde: desde o M0 está (6/6 nos dois OpenCV).
