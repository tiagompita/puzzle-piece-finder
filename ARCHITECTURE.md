# ARCHITECTURE — Puzzle Piece Finder

_Gerado em 2026-10-29 a partir do código real (HEAD `c35442f`), não da documentação. A skill `project-cartographer` referida no pedido não existe em `.claude/skills/`; este ficheiro segue o mesmo espírito (mapa de módulos, fluxo de dados, contratos, pontos de entrada, dados, testes) feito à mão._

## 1. O que o sistema faz hoje (fluxo real)

```
foto/scan de várias peças ──► segmentation.segment_pieces ──► lista de peças
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

## 2. Mapa de módulos (`src/`, 4 900 linhas)

| Módulo | Linhas | Papel | Depende de | Estado observado (2026-10-29) |
|---|---|---|---|---|
| `segmentation.py` | 1750 | Deteção/recorte de peças numa foto: distância Lab ao fundo (modelo de fundo pela margem ou global), histerese + conetividade, limpeza morfológica, seam-carve/watershed para peças encostadas, bisect forçado, encolhimento de sombra, refinamento de fronteira, rejeição de franja de fundo, normalização de rotação (`minAreaRect`). Também `piece_to_rgba`, `save_pieces`, `segment_pieces_from_file`. | cv2, numpy, PIL | Funciona bem em scans de flatbed com fundo saturado (≈60/64 peças, 0 clusters). Degrada em fundo pálido e em fotos de telemóvel com peças juntas. **O teste sintético `tests/test_segmentation.py` falha desde `f6cc2b7`** (um retângulo é devolvido com bbox inflada). |
| `edges.py` | 194 | Classifica a peça pelo nº de lados retos do `minAreaRect` (`_STRAIGHT_RATIO=0.09`). Não extrai perfis de lado nem tab/blank. | cv2, numpy | Funciona; o teste `test_two_adjacent_flat_sides_is_corner` falha com OpenCV 5 porque a ordem de `cv2.boxPoints` mudou (o tipo continua `corner`; só a indexação dos lados muda). |
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
`index, image (PIL RGB, fundo preenchido com a cor média), mask (PIL L), bbox (x,y,w,h em coords da foto), area_px, angle, contour (N×2 em coords da foto), is_cluster, piece_type, straight_sides, sides[4], side_deviations[4], min_area_box`.

**Resultado de matching**: `best_position (x,y)`, `piece_size_final (w,h)`, `rotation ∈ {0,90,180,270}`, `scale`, `refined_similarity ∈ [0,1]`, `candidates` (até 5: `position, size, rotation, similarity, score, cost_comb, d_grad, edge_penalized`), `confidence`, `confidence_reason`, `confidence_gap`, `piece_structure`. Coordenadas no referencial da imagem de referência passada. Erro → `{'error': str}`.

**JSON de exportação** (GUI): `timestamp, puzzle_info{size,mode}, pixels_per_cm?, pieces[{id, position, size, similarity, scale, path, confidence, confidence_reason, candidates[]}]`.

## 4. Pontos de entrada e ferramentas

| Comando | Faz | Estado |
|---|---|---|
| `python -m src.gui` | GUI completa | funciona (precisa de Tk) |
| `python -m src.main` | CLI ingénua (`compare_images`) | corre, mas não localiza peças |
| `python eval_matching.py` | Harness A/B do motor em `images/pieces/IMG_2114.DNG` (64 peças, foto de telemóvel) | corre; `SCRATCH` aponta para um diretório de sessão antigo (cria-o se não existir) |
| `pytest tests/` | 6 testes sintéticos | 5/6 com OpenCV 4.11; 4/6 com OpenCV 5.0 |
| `examples/basic_usage.py` | 4 exemplos sobre `.DNG` | parse OK; não corrido ponta a ponta |
| `test_scales.py`, `gpu_test.py`, `temp_import_test.py` | scripts soltos | órfãos (GPU nunca é usada pelo motor) |

Dependências reais: `Pillow`, `opencv-python`, `numpy` (+ `pytest` para testes). `requirements-dev.txt` lista muito mais do que é usado (sphinx, jupyter, mypy, …). Python 3.13 na máquina do utilizador; sem venv no repositório.

## 5. Dados de teste no repositório

| Conjunto | O que é | Uso |
|---|---|---|
| `images/puzzles/PuzzleOriginal.jpeg` | 8064×6048, **foto da caixa** do Clementoni 3000 "Os Alpes" (margem branca, texto, ligeira perspetiva) | referência default do harness e dos testes |
| `images/puzzles/1186441_1.jpg` | 1600×1200, arte limpa do mesmo puzzle (imagem de produto) | não usada pelo código |
| `images/puzzles/pexels-…jpg` | 7552×5037, foto de stock sem relação | lixo |
| `images/pieces/digitalização_fundo_*.jpg` | 11 scans A4 a 300 dpi (2480×3504; dois a 600 dpi) das **mesmas ~64 peças** em 11 fundos; `*_grupoN` são outros conjuntos, alguns já montados em grupos | segmentação / forma (escala absoluta conhecida: 1 px = 0,0847 mm a 300 dpi) |
| `images/pieces/segmented_pieces_<fundo>/` | recortes PNG gerados pelo Save Pieces | ground-truth parcial de segmentação (feito pelo programa, não à mão) |
| `images/pieces/IMG_21xx.DNG` (12, ignorados pelo git) | fotos de telemóvel, 64 peças em papel branco + fotos de grupos | harness de matching |
| `images/pieces/Phone Link/*.jpeg` | 5 fotos de telemóvel: caixa (2100), tapete com centenas de peças soltas e secções montadas (2108–2111) | nenhum ainda |

Não existe ground truth de posição (peça → célula da grelha) para nenhuma peça.

## 6. Desalinhamentos documentação ↔ código

- `README.md` descreve `piece_0.png…piece_23.png`, `puzzle.json`, `data/`, segmentação "in development", GPU/CUDA, overlap detection: tudo desatualizado.
- `CLAUDE.md` fala em "métodos duplicados na GUI", "caminhos partidos em acquisition.py" e "imports relativos que impedem os comandos documentados": não se reproduz em HEAD.
- `docs/RELATORIO.md`/`ROADMAP.md` descrevem a arte como "deserto/areia"; a arte é a paisagem alpina (Val di Funes) — as peças creme/cinza são céu e nuvens.
- A skill `cv-visual-verification` afirma que a suite pytest "tem de ficar verde"; não está verde em HEAD.
