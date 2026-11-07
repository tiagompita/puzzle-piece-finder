# Prado comido: recuperação em `segment_scan` (2026-11-07)

Origem: `docs/diagnostico/reports/TRIAGEM-2026-11-07.md` §4 (R0023, P0218). Script: `tools/diagnostico/segmentacao/prado.py` (só lê o projeto; cache em `$PPF_SCRATCH/prado/`). Figura: `PRADO_antes_depois.jpg`. Etiquetas: **[V]** verificado, **[NT]** não testado, **[F]** testado e falha.

## 1. O defeito, medido

Em S0009 (`montado_p01_300dpi.jpg`), P0218 (#25), P0223 (#30) e P0199 (#6) têm um canto de prado claro, quase da cor do papel. O contorno corta-o: um entalhe dentro da peça (TRIAGEM §4).

**O [NT] da triagem («o entalhe fecha no limiar sem abertura?»), agora medido [V]:**

| peça | área recuperada | no limiar cru (d > 28) | depois da abertura | depois da abertura + fecho | fora da máscara de `segment_pieces` | a > 1,5 mm dela (fora da banda) |
|---|---|---|---|---|---|---|
| P0218 | 17,9 mm² | 98,1 % | 97,4 % | **100 %** | 100 % | **100 %** |
| P0223 | 13,2 mm² | 94,2 % | 89,1 % | **100 %** | 100 % | **100 %** |
| P0199 | 12,4 mm² | 94,5 % | 88,7 % | **100 %** | 100 % | **100 %** |

O limiar de resolução total já tem o prado; quem o corta é a **banda de 1,5 mm** à volta do contorno de baixa resolução de `segment_pieces`. Esse contorno (distância ao fundo dominada pela croma) vê o prado como papel e passa por dentro dele, até 3,5–4,7 mm. Por isso o desenho é mais simples do que o da proposta: não há componentes abaixo do limiar para recuperar. Recupera-se o que o limiar tem e a banda deixou de fora.

## 2. O passo (`src/segmentation.py`)

- `_recover_scan_bays` corre dentro de `segment_scan`, **depois** do passo dos contactos. Salta as peças com `contacto`, as `is_cluster` e as não refinadas, por isso os grupos de contacto de CONTACTOS.md ficam como estão.
- `_recover_bay_contour` é a geometria pura. Por peça, na janela da peça:
  1. **Candidatos:** limiar ∩ célula de Voronoi da peça (sem banda), fora do contorno atual, dentro do `minAreaRect` do contorno alargado 0,3 mm.
  2. **Abertura** com disco de raio `_BAY_OPEN_MM` = **1,1 mm**. Fica cada componente que, recrescida pelo mesmo disco (limitada aos candidatos, o que repõe os cantos arredondados pela abertura), toca a peça.
  3. **Lascas finas** do mesmo entalhe (ao longo do bordo, mais finas do que o disco) entram por conectividade, mas só dentro do fecho convexo de peça + entalhe. Uma faixa de sombra do lado de fora de um lado reto fica de fora.
- **Validação:** ganho entre `_BAY_MIN_MM2` = 2 mm² e `_BAY_MAX_GAIN` = 10 % da área; `shape.analyse` com 4 cantos; violações de forma (`_shape_violations`: cordas em [15,5; 21] mm, nenhum F < 17 mm) não aumentam. A regra é «não piora», não «todas as cordas em [15,5; 21]»: uma peça com um lado real fora da gama pode ser recuperada se não piorar.
- **Marca:** `recuperado_mm2` (área ganha) no registo da peça. `src/ingest.py` copia-a para `flags`.
- **Interruptor:**
  - `_RECOVER_BAYS = True` no módulo;
  - `segment_scan(recover_bays=None|True|False)`;
  - com `False` a saída é bit a bit a anterior **[V]**: as 27 folhas dão a numeração e a contagem guardadas no projeto, e os 3 alvos dão as formas guardadas (`free_dist` antes igual ao do índice).
- **Um blank não é candidato:** é fundo no limiar. Teste sintético e as 3 peças de controlo da figura **[V]**.

**Porque 1,1 mm.** A primeira versão (disco 0,8 mm, sem fecho convexo) mudava **12 peças** nas 27 folhas. Vistas uma a uma:
- 3 eram os alvos;
- 7 eram cantos de sombra projetada do lado da sombra (P0156, P0195, P0445, P0451, P0848, P0887, P0902; +3,7 a +8,1 mm², até +2,33 % em P0195);
- 1 era um tab cortado na junta de um bloco (P0852, S0024);
- 1 era a tira de papel no bordo do scan (P0395, S0013; mudava a classe BBFT → BBTT).

O raio inscrito destas 9 componentes é ≤ 0,96 mm; o dos 3 entalhes é ≥ 1,34 mm **[V]**. Com 1,1 mm ficam só os 3 alvos. A cor não separa: a mediana de dL vai de −36 a −48 no prado e de −44 a −98 nas falsas, e há sobreposição **[V]**. A margem do raio é curta (−15 % / +18 %), e o limite foi fixado neste conjunto, sem validação noutro **[NT]**.

## 3. Porta de regressão (antes = `recover_bays=False`, depois = por omissão)

**(a) E-sym** (`tests/test_segment_scan_esym.py`, `slow`): igual antes e depois **[V]**.
- gémea A2/B2 mediana 0,383 mm, A1/B2 0,304 mm, re-scan 0,257 mm;
- top-1 20/20 nos três sentidos;
- corda mediana 18,60 mm.

Os contornos de A1, A2 e B2 são bit a bit iguais com e sem o passo. Não se correu `tools/diagnostico/gemeos/esym.py`: reescreve `docs/diagnostico/gemeos/results.json` e as figuras, e o teste já cobre a variante `scan` com contornos idênticos.

**(b) Folhas** (`projects/alpes/scans/`, 27 folhas: as 26 de CONTACTOS §3 + S0027 do lote 3) **[V]**:

| Folha | Ficheiro | Tipo | Peças antes → depois | Numeração igual | Numeração = projeto | Alteradas | t antes / depois (s) |
|---|---|---|---|---|---|---|---|
| S0001 | `coluna5-24_300dpi_folhaA.jpg` | gt | 20 → 20 | sim | sim | 0 | 1.9 / 1.8 |
| S0002 | `coluna5-24_folhaB_300dpi_rot180.jpg` | gt | 20 → 20 | sim | sim | 0 | 1.8 / 1.8 |
| S0003 | `gt_canto_BE_soltas_300dpi.jpg` | gt | 25 → 25 | sim | sim | 0 | 8.3 / 8.5 |
| S0004 | `gt_canto_BD_soltas_300dpi.jpg` | gt | 28 → 28 | sim | sim | 0 | 2.1 / 2.2 |
| S0005 | `ereal2_ceu_f1p1_300dpi.jpg` | soltas | 35 → 35 | sim | sim | 0 | 2.4 / 2.5 |
| S0006 | `ereal2_ceu_f1p2_300dpi.jpg` | soltas | 15 → 15 | sim | sim | 0 | 1.8 / 1.8 |
| S0007 | `ereal2_ceu_f2p1_300dpi.jpg` | soltas | 42 → 42 | sim | sim | 0 | 2.6 / 2.7 |
| S0008 | `ereal2_ceu_f2p2_300dpi.jpg` | soltas | 8 → 8 | sim | sim | 0 | 1.5 / 1.6 |
| S0009 | `montado_p01_300dpi.jpg` | montado | 43 → 43 | sim | sim | **3** | 2.4 / 3.1 |
| S0010 | `montado_p02_300dpi.jpg` | montado | 46 → 46 | sim | sim | 0 | 2.7 / 2.8 |
| S0011 | `montado_p03_300dpi.jpg` | montado | 18 → 18 | sim | sim | 0 | 1.9 / 1.9 |
| S0012 | `montado_p04_300dpi.jpg` | montado | 44 → 44 | sim | sim | 0 | 2.7 / 3.0 |
| S0013 | `montado_p05_300dpi.jpg` | montado | 51 → 51 | sim | sim | 0 | 2.8 / 3.0 |
| S0014 | `montado_p06_300dpi.jpg` | montado | 48 → 48 | sim | sim | 0 | 3.0 / 3.2 |
| S0015 | `montado_p07_300dpi.jpg` | montado | 36 → 36 | sim | sim | 0 | 2.3 / 2.5 |
| S0016 | `montado_p08_300dpi.jpg` | montado | 37 → 37 | sim | sim | 0 | 2.4 / 2.5 |
| S0017 | `montado_p09_300dpi.jpg` | montado | 34 → 34 | sim | sim | 0 | 2.3 / 2.4 |
| S0018 | `montado_p10_300dpi.jpg` | montado | 39 → 39 | sim | sim | 0 | 2.7 / 2.8 |
| S0019 | `montado_p11_300dpi.jpg` | montado | 38 → 38 | sim | sim | 0 | 2.6 / 3.0 |
| S0020 | `montado_p12_300dpi.jpg` | montado | 48 → 48 | sim | sim | 0 | 4.1 / 4.3 |
| S0021 | `montado_p13_300dpi.jpg` | montado | 44 → 44 | sim | sim | 0 | 2.7 / 2.9 |
| S0022 | `montado_p14_300dpi.jpg` | montado | 55 → 55 | sim | sim | 0 | 3.0 / 3.2 |
| S0023 | `montado_p15_300dpi.jpg` | montado | 59 → 59 | sim | sim | 0 | 4.5 / 4.7 |
| S0024 | `blocos_p01_300dpi.jpg` | blocos | 29 → 29 | sim | sim | 0 | 2.3 / 2.4 |
| S0025 | `blocos_p02_300dpi.jpg` | blocos | 36 → 36 | sim | sim | 0 | 2.5 / 2.6 |
| S0026 | `blocos_p03_300dpi.jpg` | blocos | 11 → 11 | sim | sim | 0 | 1.7 / 2.0 |
| S0027 | `lote03_20261102_142833_lote_3.jpg` | soltas | 50 → 50 | sim | sim | 0 | 3.5 / 3.8 |

- Tempo total: 74,4 s antes, 78,5 s depois (+5,5 %; máquina partilhada, valores indicativos).
- A numeração compara o `grid_order` das peças ≥ 150 mm² com o `n_no_lote` guardado.
- A medição foi feita na cópia de referência `alpes_r3b` (log 2072). Repetida em `projects/alpes` (só leitura) com `prado.py`: as mesmas 27 linhas, as mesmas 3 peças alteradas e os mesmos números de (c), com tempo total 76,4 / 79,1 s **[V]**.

**(c) Os 3 alvos contra a gémea colocada** (`shape.analyse` + `shape.free_dist` contra a forma guardada da gémea) **[V]**:

| peça (célula) | gémea | classe antes → depois | cordas antes → depois (mm) | área (mm²) | `free_dist` antes → depois |
|---|---|---|---|---|---|
| P0218 (32,64) | P0647 (16,1), BFBT | BBBT → **BFBT** | [18,22; 18,55; 19,89; 17,41] → [**18,44 (F)**; 18,27; 19,95; 17,38] | 340,2 → 358,1 (+5,3 %) | 2,749 → **0,500** |
| P0223 (33,64) | P0641, BBTF | BBTF → BBTF | [15,96 (F); 18,66; 16,63; 19,08] → [**19,67 (F)**; 18,69; 16,67; 18,88] | 362,5 → 375,7 (+3,7 %) | 1,037 → **0,593** |
| P0199 (35,64) | P0629, BFBT | BFBT → BFBT | [19,23; 17,88; 18,21; 15,41] → [19,05; 17,95; 18,22; **18,53**] | 351,1 → 363,5 (+3,5 %) | 0,822 → **0,560** |

- Os três ficam ≤ 0,6 mm.
- P0223 passa à justa (0,593). O resíduo é sobretudo a sombra projetada em pose oposta: P0223 tem a sombra do lado W no scan, a gémea em S0020 tem-na do outro lado. Fica também um entalhe de < 0,5 mm no lado direito junto ao canto (visto na figura).
- P0218 volta a ter um lado F de 18,44 mm, e a classe passa a ser a da gémea.
- Que esse F fique no lado E do tabuleiro **não foi verificado** com a pose da secção G0005 **[NT]**. É coerente com a gémea, que tem o F no W de (16,1), e com o alinhamento a 0,50 mm.

**(d) Outras peças:** nenhuma das 27 folhas muda fora dos 3 alvos (0 peças com qualquer diferença de contorno, logo 0 com ganho > 2 %) **[V]**.

**(e) `pytest tests/`** (suite completa, testes `slow` incluídos, OpenCV 4.11, venv4): **227 passed, 1 skipped** (151,6 s) **[V]**. OpenCV 5.0 não corrido **[NT]**.

## 4. Figura (`PRADO_antes_depois.jpg`, vista)

Antes = contorno vermelho; depois = contorno ciano, com a área recuperada a magenta.
- **Alvos.** P0218: o entalhe retangular do prado de baixo à direita fecha. P0223: o triângulo de prado do canto superior direito volta, desde a base do tab até ao canto. P0199: volta o canto superior direito de prado.
- **Controlos**, peças com blanks viradas para o papel e arte clara: P0156 (céu, S0007), P0195 (creme/castanho, S0009) e P0445 (relva, S0015). Ficam iguais, com os blanks abertos.
  - São três das falsas recuperações da primeira versão (cantos de sombra), agora rejeitadas.

## 5. Testes e reprodução

- **Testes novos** em `tests/test_segmentation.py`, com `tests/synth.meadow_scan`: peça `BTBT` com um quadrado de 5 mm da cor do prado medido no canto superior direito, mais um controlo igual sem a mancha e duas peças.
  1. `test_segment_scan_recovers_eaten_meadow_corner`: sem o passo, IoU 0,959 e corda de cima 14,8 mm; com o passo, IoU 0,997, `recuperado_mm2` 13,3 e cordas 18,4–18,5 mm.
  2. `test_segment_scan_recover_bays_keeps_blanks`: os blanks continuam abertos e as peças sem mancha ficam bit a bit iguais.
  3. `test_segment_scan_recover_bays_module_switch`.
- **Com o passo desligado**, o primeiro teste falha (IoU 0,959 < 0,99) **[V]**.
- **Reprodução:** `python tools/diagnostico/segmentacao/prado.py --project projects/alpes`.

## 6. Limites

- **Peças em grupo de contacto** não são tratadas: o passo salta-as para não mexer na partição de CONTACTOS.md.
- **Prado comido abaixo do limiar**, se o limiar fechado não o tiver, não se recupera: o desenho da proposta para componentes abaixo do limiar não foi preciso nestes 3 casos e não foi implementado **[NT]**.
- **Limites fixados neste conjunto:** o raio de 1,1 mm e os outros limites vêm deste conjunto (12 candidatas, 3 verdadeiras). Peças fora destas 27 folhas **[NT]**.
- **`projects/alpes` não foi re-segmentado.** O índice continua com as formas antigas até `render.rebuild_assets` ou `ingest_all.py` (decisão do gestor/Tiago).
