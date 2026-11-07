# Peça «comida» (R0011/R0012): segmentação contra a máscara manual do Tiago e detetor sem verdade de terreno (2026-11-07)

Script: `tools/diagnostico/segmentacao/comido.py` (só lê o projeto; recusa escrever dentro dele; caches em `$PPF_SCRATCH/comido/`). Figuras: `COMIDO_gt.jpg`, `COMIDO_alcance.jpg`. Dados: `comido_resultados.json` (sinais por peça, colunar), `comido_antigo.npz` (contornos de P0651/P0657 no índice de 2026-11-01). Métrica: `src/maskcmp.py` (`mask_metrics`, `best_shift`, e `nearest_side`, acrescentada nesta tarefa com teste). Etiquetas: **[V]** verificado, **[NT]** não testado, **[F]** testado e falha. Áreas em mm², distâncias em mm, 1 px = 0,0847 mm.

**Resumo.** A «mordida» que o Tiago vê nas miniaturas da GUI **não está no índice atual nem na limpeza de exibição atual**. A captura `atual_*_gui.png` coincide com a silhueta de P0651/P0657 no **índice de 2026-11-01**, anterior ao passo dos contactos (S5, 2026-11-02): IoU 0,971 / 0,955 com essa silhueta, 0,822 / 0,751 com a exibida de hoje **[V]**. Essa silhueta antiga perdia 69 / 60 mm² de peça, com 4,1–4,2 mm de profundidade **[V]**. A GUI do Tiago corre noutra cópia do repositório: `projects/alpes/erro_terminal.txt` mostra o uvicorn em `D:\DEKSTOP\puzzle_piece_finder`. Nessa cópia, `crops/`, `pieces/` e `render/` não vêm pelo git (`.gitignore:115-118`), mas `log.jsonl` vem. É a explicação mais provável **[NT: a pasta D: não foi inspecionada]**.

No índice atual (C:), P0651/P0657 só perdem 6,8 / 1,2 mm² contra a GT. Em P0651 a parte mais funda (1,13 mm) é a ponta do tab S, no corte de contacto com P0657. A exibição atual tira mais 4,5 / 1,7 mm² de relva real, em tiras de ≤ 0,56 mm nos lados N/E **[V]**.

O detetor sem GT (gémea local, baía no limiar, folga por lado) apanha os 5 positivos e não dispara em nenhum dos 63 controlos [V; calibração num conjunto pequeno, NT fora dele]. Nas 953 peças do projeto, a baía no limiar encontrou **3 peças com um tab inteiro fora do contorno** (P0844, P0879, P0852; blocos S0024/S0025) **[V visual]**.

## 1. Verdade de terreno e alinhamento

- **Quem é quem [V].**
  - `manual_A_photoshop.png` = **P0651** (44,1), S0020 `index_in_scan` 23, nº 24, FTTT. GT: 54 297 px = **389,2 mm²**.
  - `manual_B_photoshop.png` = **P0657** (45,1), `index_in_scan` 25, nº 30, BFBT. GT: 39 946 px = **286,4 mm²**.
  - As duas folhas têm 2544×3504 px, o tamanho exato de `montado_p12_300dpi.jpg` (S0020).
- **Registo [V].** O RGB opaco da GT é o próprio scan, píxel a píxel:
  - em (0,0), diferença média 0,08 (A) e 0,07 (B) em 0–255;
  - com qualquer deslocamento de 1 px, ≥ 17,9.
  - O deslocamento é portanto **(0,0)** e não se aplicou nenhum.
- **`best_shift` (±3 px) do índice contra a GT** dá (3,−2) com IoU 0,889 (A) e (3,−3) com IoU 0,830 (B), no limite do raio. Não é desalinhamento: é o halo de sombra projetada do índice nos lados W/S (§2). Não se aplicou.
- **Orla do alfa.**
  - A: 6388 px parciais, largura média 5,2 px ≈ 0,44 mm (pena do Photoshop).
  - B: 1993 px, 1,8 px ≈ 0,15 mm.
  - Usa-se alfa > 127. Com a orla de A, a fronteira da GT tem uma incerteza de cerca de ±0,2 mm.
- **Coerência das silhuetas reconstruídas [V]:**
  - o alfa do recorte do projeto é igual ao contorno `contour_px` preenchido (XOR 0 px nas duas);
  - a «exibida» do script é bit a bit `render.piece_rgba_for_display` (alfa > 127) em P0651, P0657, P0001, P0218, P0233, P0156 e P0445;
  - `projects/alpes/render/clean/` está vazio, logo a limpeza é calculada na hora.

## 2. As silhuetas contra a GT

Silhuetas, todas no referencial do scan:
- **índice** = `contour_px`;
- **limpa** = alfa de `clean_crop`;
- **exibida** = `piece_rgba_for_display` sem pose, a miniatura;
- **tabuleiro** = a peça desenhada sozinha por `compose_board` a 300 dpi, com a pose `register_piece(image=False)` (P0651 −1,66°, P0657 +11,66°, `corners`/F). O alfa obtém-se de dois fundos (preto e branco) e volta ao scan pela pose inversa. «Sangria» é o mesmo com `BLEED_MM` 0,3, como a GUI;
- **índice antigo** = o contorno da cópia de 2026-11-01 (`comido_antigo.npz`), e **exibida antiga** = a mesma limpeza aplicada a ele.

| silhueta | P0651 IoU | área | em falta (prof.) | a mais (prof.) | d_p95 / d_max | P0657 IoU | área | em falta (prof.) | a mais (prof.) | d_p95 / d_max |
|---|---|---|---|---|---|---|---|---|---|---|
| índice | 0,869 | 433,4 | 6,8 (1,13) | 51,0 (1,47) | 1,28 / 1,86 | 0,824 | 345,0 | 1,2 (0,25) | 59,8 (1,74) | 1,42 / 1,74 |
| limpa | 0,908 | 404,7 | 11,3 (1,13) | 26,8 (1,25) | 1,10 / 1,73 | 0,885 | 317,3 | 2,9 (0,47) | 33,8 (1,05) | 0,91 / 1,08 |
| **exibida** | **0,928** | 395,4 | 11,6 (1,13) | 17,8 (1,13) | 0,98 / 1,73 | **0,919** | 305,6 | 2,9 (0,47) | 22,1 (0,93) | 0,73 / 0,93 |
| tabuleiro (sem sangria) | 0,928 | 395,4 | 11,6 (1,13) | 17,8 (1,13) | 0,98 / 1,73 | 0,919 | 305,6 | 2,9 (0,47) | 22,1 (0,93) | 0,73 / 0,93 |
| tabuleiro com sangria 0,3 | 0,882 | 438,3 | 1,3 (0,78) | 50,4 (1,49) | 1,35 / 1,88 | 0,819 | 349,6 | 0,1 (0,12) | 63,3 (1,39) | 1,25 / 1,47 |
| índice antigo (01-nov) | 0,760 | 352,2 | **69,2 (4,11)** | 32,2 (1,32) | 3,50 / 4,11 | 0,738 | 246,8 | **59,9 (4,20)** | 20,3 (1,27) | 2,96 / 4,20 |
| exibida antiga | 0,789 | 332,6 | **70,8 (4,11)** | 14,2 (1,17) | 3,49 / 4,11 | 0,760 | 236,1 | **60,8 (4,20)** | 10,5 (0,93) | 2,96 / 4,20 |

O **tabuleiro** sem sangria é igual à exibida até ao píxel. A pose e o warp não comem nada **[V]**. A sangria repõe 0,3 mm à volta, e por isso recobre quase toda a perda da limpeza e devolve o halo.

**Por lado** (pose do scan: P0651 tem o tab no N, E e S e o F no W; P0657 está rodada 12°). Em cada célula: mm² / profundidade máx. (mm).

| peça, silhueta | em falta N | E | S | W | a mais N | E | S | W |
|---|---|---|---|---|---|---|---|---|
| P0651 índice | 2,4 / 0,36 | 2,2 / 0,34 | **2,2 / 1,13** | 0 | 3,6 / 1,35 | 7,4 / 1,32 | **22,4 / 1,47** | **17,6 / 1,27** |
| P0651 exibida | 4,3 / 0,52 | 4,3 / 0,56 | 2,9 / 1,13 | 0,1 / 0,24 | 0,2 / 0,17 | 3,8 / 1,13 | 12,2 / 1,03 | 1,5 / 0,19 |
| P0651 índice antigo | **31,9 / 4,01** | **35,2 / 4,11** | 1,4 / 0,64 | 0,8 / 0,47 | 0 | 2,6 / 1,32 | 18,0 / 1,27 | 11,6 / 1,12 |
| P0657 índice | 0,6 / 0,25 | 0,2 / 0,19 | 0,3 / 0,25 | 0 | 8,2 / 1,74 | 8,1 / 1,27 | **23,1 / 1,62** | **20,3 / 1,52** |
| P0657 exibida | 2,0 / 0,47 | 0,5 / 0,24 | 0,4 / 0,37 | 0 | 2,4 / 0,68 | 4,7 / 0,93 | 10,9 / 0,88 | 4,1 / 0,46 |
| P0657 índice antigo | **20,6 / 4,20** | **15,6 / 2,72** | **17,2 / 3,69** | **6,4 / 3,13** | 1,1 / 0,74 | 3,5 / 1,27 | 8,2 / 1,23 | 7,5 / 1,18 |

**O que cada regra de exibição tira** (na peça atual). «Dentro da GT» é peça real tirada; «fora» é papel ou sombra bem tirados.

| regra | P0651 mm² (% do índice) | dentro da GT | fora | P0657 mm² (%) | dentro | fora |
|---|---|---|---|---|---|---|
| franja verde (`fringe_masks`, banda 0,7 mm; nenhuma das duas é «clara») | 28,75 (6,63 %) | **4,51** (N 1,75, E 2,12, S 0,60, W 0,04) | 24,24 | 27,75 (8,04 %) | **1,73** (N 1,33, E 0,26, S 0,14) | 26,02 |
| descontaminação | 0 | 0 | 0 | 0 | 0 | 0 |
| sombra 0,4 mm (`shadow_paper_mask`) | 9,20 (2,12 %) | 0,23 | 8,97 | 11,71 (3,39 %) | 0,03 | 11,68 |
| bolsas (`paper_pocket_mask`) | 0 | 0 | 0 | 0 | 0 | 0 |

- **Prado real comido pela exibição:** 4,7 mm² em P0651 e 1,8 mm² em P0657 **[V]**.
  - Quase tudo é a franja verde nos lados iluminados N/E, em tiras finas (≤ 0,56 mm).
  - A relva de P0651 está colada ao limiar: o p5 da distância ao papel no interior é 29,8 contra o limiar de 29,5.
  - 88 % (P0651) e 96 % (P0657) do que a exibição tira é sombra e papel fora da GT.
- **Captura da GUI.** A silhueta das miniaturas foi segmentada por saturação. A escala vem do quadrado tracejado da célula: 62 × 60 px = 18,5 × 17,9 mm, 3,35 px/mm. Procurou-se o melhor alinhamento em rotação (±30°) e translação.

| peça | área da captura | IoU com a exibida de hoje | IoU com a exibida antiga | IoU com o índice antigo |
|---|---|---|---|---|
| P0651 | 332,5 mm² | 0,822 | **0,971** (332,6 mm²) | 0,930 |
| P0657 | 232,6 mm² | 0,751 | **0,955** (236,1 mm²) | 0,922 |

Reproduzi a miniatura com o código e o projeto de hoje (`piece_rgba_for_display`, pose `register_piece`, tamanho do cartão): sai uma peça inteira, sem a «casa com topo em picos» **[V]**.

## 3. Diagnóstico: onde está a mordida

1. **A mordida do report é a silhueta antiga, servida pela GUI do Tiago [V para a forma; NT para a causa na máquina D:].**
   - A captura coincide com a exibida do índice de 2026-11-01: IoU 0,971 / 0,955, áreas iguais a 0,1 / 3,5 mm².
   - Esse índice perdia em P0651 o tab N e o canto NE até ao tab E (N 31,9 + E 35,2 mm², 4,1 mm de fundo).
   - Em P0657 perdia o canto W, o tab NE e o canto S: 60 mm² e uma classe sem 4 cantos (área guardada 246,75 mm², `cls` vazio).
   - Nesse índice as duas peças não estavam marcadas como `contacto`. Foram re-segmentadas no rebuild de 2026-11-02 (passo dos contactos S5) e outra vez em 2026-11-07 05:46 (`piece_resegmented`, motivo `contactos`, log 2095–2096).
   - **Mecanismo provável [NT]:** a cópia D: recebe o `log.jsonl` pelo git, com as bbox novas, mas mantém `crops/` e `pieces/*.npz` antigos, que o git ignora.
   - Como `piece_rgba_for_display` usa a bbox do log como origem, o recorte antigo seria também desenhado deslocado (origem nova 2199,1101 contra a antiga 2202,1146: 3,8 mm na vertical) **[NT]**.
   - A pose também não bate com a de hoje: na captura de P0657 o melhor ajuste é rodado 0°, a pose atual é 11,7°. Isto é coerente com uma forma antiga no `npz` de D: **[NT]**.
   - `render._clean_or_crop` usa `render/clean/P####.png` se existir, sem comparar com o recorte. Numa cópia sem rebuild, esse ficheiro também pode estar velho **[V no código; NT em D:]**.
   - **Quantas peças mudaram desde esse índice** (por id, mesma folha, `antigo`): 9 de 908 com área > 1 % maior hoje.

     | peça | folha | mudança de área |
     |---|---|---|
     | P0657 | S0020 | +28,5 % |
     | P0651 | S0020 | +18,7 % |
     | P0064 | S0003 | +18,1 % |
     | P0065 | S0003 | +17,5 % |
     | P0058 | S0003 | +15,9 % |
     | P0777 | S0023 | +5,3 % |
     | P0218 | S0009 | +5,0 % |
     | P0223 | S0009 | +3,5 % |
     | P0199 | S0009 | +3,4 % |

     Se D: estiver nesse estado, são estas as peças que lá aparecem velhas **[NT]**.

2. **Índice atual (C:): sem mordida relevante [V].**
   - Contra a GT faltam 6,8 / 1,2 mm².
   - A única parte funda (1,13 mm, 2,2 mm² no lado S) é a ponta do tab S de P0651, na zona do corte de contacto com o ombro de P0657 (figura, «índice vs GT», magenta no tab).
   - Fica dentro da zona de 1,0 mm de `_CONTACT_TRIM_ZONE_MM`. Não verifiquei se vem do watershed ou do aparo de 0,8 mm **[NT]**.
   - O resto do erro do índice é **a mais**: o halo de sombra de 51 / 60 mm² nos lados S/W, com profundidade de 1,47 / 1,74 mm. É o viés conhecido da modalidade scan (+0,48 mm), não uma mordida.
3. **Limpeza de exibição atual: perda fina, não mordida [V].**
   - Tira 4,5 / 1,7 mm² de relva real (franja verde na banda de 0,7 mm, lados N/E, ≤ 0,56 mm).
   - Sombra 0,4 mm: 0,23 / 0,03 mm² de peça.
   - Bolsas: 0.
   - É a perda nos lados iluminados da porta §6.1 (TRIAGEM §4, opções A/B por decidir). Não explica a captura.
4. **`_RECOVER_BAYS` e o índice antigo [V].**
   - O índice antigo tinha a peça no limiar e o contorno fora dele: a baía no limiar (sinal c) tem 88,9 / 92,9 mm², raio inscrito 2,05 / 2,23 mm e 4,2–4,4 mm de profundidade.
   - O passo de baías de hoje não a recuperaria por duas razões:
     - salta peças `contacto`;
     - só aceita candidatos dentro do `minAreaRect` do contorno alargado 0,3 mm, e 42 % / 35 % da baía caem fora dele (são tabs).
   - Hoje a baía de P0651/P0657 é 1,6 / 0,1 mm², com raio 0,54 / 0,08: não há nada a recuperar.
5. **Porque é que a medida contra a gémea (0,55 / 0,37 mm) não detetou nada [V].**
   - Foi feita sobre o índice atual, que está certo: `free_dist` P0651–P0233 0,554 e P0657–P0234 0,366, os mesmos números.
   - O índice antigo, que é o que a GUI de D: mostra, está a **2,18 / 2,51 mm** das gémeas.
   - O RMS global esconde mesmo uma mordida local: P0651 atual tem RMS 0,55 mas distância máxima ao ponto mais próximo da gémea 1,37 mm, coerente com a ponta do tab de 1,13 mm (localização não confirmada **[NT]**). Não chega ao limiar do detetor.

## 4. Gémeas P0233 (4,64) e P0234 (3,64), céu claro, S0009

Não há GT. A comparação é entre a exibida e o índice **[V]**:
- **P0233:** a exibição tira 27,8 mm² (6,38 %), com profundidade máx. 1,07 mm (banda 0,7 + sombra 0,4) e maior componente 14,3 mm². Por regra: franja 24,0, sombra 3,9, bolsas 0. Nos lados iluminados N/E vão 9,2 mm² (2,11 %).
- **P0234:** 27,1 mm² (8,05 %), 1,02 mm, 11,4 mm²; franja 24,9, sombra 2,2; lados iluminados 9,7 mm² (2,87 %).
- Na figura, o que sai é a orla de sombra dos lados W/S. **Não estão comidas.**
- Nenhuma das duas é «clara» para a regra (`is_light` falso): o creme do céu fica abaixo de p5 44,25 de distância ao papel.

## 5. Detetor de peça comida sem GT

Sinais por peça, todos a partir do projeto, do npz e do scan:
- **(a) Gémea local.**
  - Alinha-se a gémea com o `shift`/`phi` de `shape.free_dist`; o sinal é o máximo da distância de cada um dos 512 pontos ao ponto mais próximo da gémea alinhada (`nn_max`).
  - Reporta-se também o p95, e o ponto a ponto `|Δz|` em `comido_resultados.json`.
  - **Dispara** com `nn_max` > **1,75 mm**, ou se a silhueta não tem 4 cantos e há gémea.
  - Só se aplica a peças com célula e gémea no índice: 512 de 953.
- **(b) Perda de exibição.** Mede-se o que `_display_masks` e a limpeza tiram ao índice: mm², %, profundidade máx., maior componente e % nos lados iluminados N/E.
  - Pela construção, a limpeza só chega a banda + 0,4 mm (1,1 / 1,6 mm). Só as bolsas vão mais fundo.
  - **Dispara** com profundidade > banda + 0,4 + **0,15 mm** e bolsas ≥ **1,0 mm²**.
- **(c) Baía no limiar.**
  - Candidatos: o limiar de resolução total do `segment_scan` (d > 28, abertura 0,42, fecho 0,76, tira de papel fora), na célula de Voronoi própria (pelos contornos do índice), fora do contorno e a ≥ **1,0 mm** de qualquer outra peça.
  - Ficam as componentes que tocam a peça. Sem a abertura de 1,1 mm nem o `minAreaRect` de `_recover_bay_contour`, e incluindo peças `contacto`.
  - O sinal é o raio inscrito da maior componente. **Dispara** com > **1,2 mm**.
- **(d) Folga local por lado.**
  - Com a pose da GUI (`register_piece(image=False)`), mede-se `render._signed_gap` dos pontos de cada lado virado para uma vizinha montada contra o polígono dela (positivo = fora da vizinha), com p90 e máx. por lado.
  - **Dispara** com máx. > **1,5 mm**.

**Conjunto de calibração.**
- Positivos:
  - P0651 e P0657 antigas;
  - P0218, P0223 e P0199 re-segmentadas com `recover_bays=False`. Reproduzem a PRADO §3: 340,2 / 362,5 / 351,1 mm², `free_dist` 2,75 / 1,04 / 0,82 **[V]**.
- Controlos:
  - P0156, P0195 e P0445 (as falsas baías da PRADO §2);
  - as 60 peças E-sym: A1 = S0001, B2 = S0002 e A2 = `colunas5-24_300dpi_rot180_folhaA.jpg`, segmentada com `segment_scan` e com a célula da peça A1 mais próxima.

| sinal | positivos (valor) | controlos: máx. / p95 (n) | dispara: positivos / controlos |
|---|---|---|---|
| (a) nn_max | 3,29 (P0651), sem 4 cantos (P0657), 5,29 / 2,17 / 2,66 (P0218 / P0223 / P0199) | 1,31 (P0445) / 0,94 (61) | 5/5 / 0/63 |
| (b) profundidade − limite | −0,08 … +0,12; bolsas 0 | −0,03 / −0,03 (63) | 0/5 / 0/63 |
| (c) r_in | 2,05 / 2,23 / 1,95 / 1,34 / 1,52 | 0,96 (P0445) / 0,59 (63) | 5/5 / 0/63 |
| (d) folga máx. | 1,96 / 4,61 / 0,21 / 1,10 / 0,26 | 0,92 / 0,35 (42) | 2/5 / 0/63 |
| **qualquer** | | | **recall 5/5, 0 falsos em 63, precisão 1,00** |

**Limiares e justificação.**
- **(a):** 1,75 é o ponto médio entre o máximo dos controlos (1,31) e o positivo mais fraco (2,17).
  - Um primeiro valor de 1,6 disparava também P0326 (1,64) e P0303 (1,63) no alcance.
  - Vistas, não são mordidas: o resíduo está na ponta de um canto e no ombro de um blank **[V visual]**.
- **(c):** entre 0,96 e 1,34. É a mesma separação da PRADO (falsas ≤ 0,96, reais ≥ 1,34).
  - Nas 953 peças do projeto, depois de 0,96 o valor seguinte é 1,79: há um vazio largo **[V]**.
- **(b):** o limite é estrutural (banda + 0,4 mm de sombra).
  - As 6 peças do projeto que passam a profundidade têm bolsas de 0,04–0,19 mm²: P0070, P0467, P0551, P0555, P0564, P0670. São grãos de cor de papel no interior, já contados na TRIAGEM §4 (12 peças ≤ 0,093 mm² a > 0,4 mm do bordo). Daí o mínimo de 1 mm².
  - **No conjunto de calibração não há nenhum positivo do lado da exibição.** O sinal (b) fica sem calibração **[NT]**.
- **(d):** só vê lados com vizinha montada. P0218/P0199 têm a mordida no lado da borda (coluna 64), sem vizinha.
  - Fica como sinal auxiliar.
  - No alcance tem 1 falso positivo a 1,5 mm (P0251) e 5 a 1,0 mm. São juntas abertas entre pares: (1,61)/(2,61) a 1,54 / 1,38 mm e (46,36)/(47,36) a 1,08 / 1,26 mm. É pose/registo, não silhueta.
- **Âmbito:** calibração em 5 positivos e 63 controlos. Fora deste conjunto, **[NT]**.

## 6. Alcance: as 953 peças do projeto

958 peças, menos 5 `descartada`. Nenhuma tem `manual_override`.

| sinal | avaliadas | disparam |
|---|---|---|
| (a) gémea local | 512 | **12** |
| (b) exibição | 953 | 0 |
| (c) baía no limiar | 953 | **3** |
| (d) folga por lado | 613 | 1 (5 com 1,0 mm; 3 com 1,2 mm) |
| qualquer | 953 | **16** |

**Por folha.** S0011: 6 (a). S0016: 6 (a). S0024: 2 (c). S0025: 1 (c). S0010: 1 (d). As outras 22 folhas têm 0, incluindo S0009 e S0020.

**Colocadas.**
- Por fila (disparam / colocadas): 1: 3/63, 2: 2/54, 3: 2/45, 45: 2/63, 46: 2/64, 47: 2/64; as outras 0.
- Por coluna: 32: 6/7, 33: 6/8, 61: 1/10; as outras 0.

**O que é cada disparo.**
- **(a), 12 peças:** todas são o bloco c32|c33 das filas 1–3 / 45–47:
  - P0289–P0294;
  - P0492–P0494 e P0496–P0498.
  - `nn_max` 2,99–6,51 mm e RMS 2,4–3,1.
  - É a exceção de corte/identidade já conhecida (corte c32|c33 não simétrico, ORIENTACOES §D; TRIAGEM §3), não segmentação. A figura de alcance exclui-as.
- **(c), 3 peças, todas `em_seccao` em secções por ancorar:**

  | peça | folha / nº | classe | secção | baía | r_in | profundidade |
  |---|---|---|---|---|---|---|
  | **P0844** | S0024 #11 | BTFT | G0079 | 22,8 mm² | 2,17 mm | 4,55 mm |
  | **P0879** | S0025 #18 | BTTF | G0090 | 29,6 mm² | 2,13 mm | 4,30 mm |
  | **P0852** | S0024 #19 | BTBT | G0070 | 31,9 mm² | 1,79 mm | 3,57 mm |

  - **[V visual]** (figura e vista do limiar): em cada uma, um tab inteiro fica fora do contorno. Está dentro do limiar, rodeado de papel e ligado só a esta peça.
  - 39–70 % da baía cai fora do `minAreaRect` + 0,3 mm. É por isso que `_recover_scan_bays` não o recupera.
  - P0852 é o «tab cortado na junta de um bloco» que a PRADO §2 contou como falsa recuperação: estes números dizem que é peça.
  - **Por confirmar fisicamente [NT].** A classe e as cordas destas 3 estão provavelmente erradas no lado do tab.
- **(d), 1 peça:** P0251 (1,61), junta S com P0147 (2,61): 1,54 mm. A silhueta está intacta e a gémea a 0,26 / `nn_max` 0,53. É a junta (pose), não a silhueta **[V visual]**.

**Filas 41–47 colocadas.** Só disparam as 6 do bloco c32|c33 (P0492–P0494, P0496–P0498, por (a)). Nenhuma peça de relva dispara.

**P0198 (28,64), R0019 fechado: não dispara [V].**
- (a): RMS 0,44, `nn_max` 0,78.
- (b): 8,9 %, 1,07 mm, sem bolsas.
- (c): r_in 0,25.
- (d): máx. 0,01.
- Coerente com a TRIAGEM §4: silhueta certa, e o que se via era o prado da cor do papel tirado pela limpeza junto ao bordo.

**As 15 de S0020 com > 5 % de cor de papel (TRIAGEM §5): nenhuma dispara [V].**
- As peças: P0632, P0644, P0645, P0648, P0650, P0651, P0654, P0656, P0657, P0663, P0665, P0666, P0668, P0669, P0670.
- `nn_max` ≤ 1,55 (P0648), r_in ≤ 0,64, folga máx. ≤ 0,62, bolsas ≤ 0,05 mm².

**`COMIDO_alcance.jpg` (vista).** Por peça: scan | índice | exibida vs índice | limiar fora do índice (laranja; inclui vizinhas).
- **Filas 1–3** (P0844, P0879, P0852): o tab de cima aparece a laranja, fora do contorno vermelho. Em P0844 o contorno tem também um degrau no bordo de cima. O laranja à direita de P0844 e P0879 é outra peça.
- **Filas 4–7** (P0564, P0467, P0070, P0551): pontuação alta pela profundidade, mas não disparam. O magenta é a orla de sombra W/S e grãos. Não se vê mordida.
- **Fila 8** (P0251): contorno intacto.

## 7. Candidatas de correção (a decidir pelo gestor; nenhuma implementada)

1. **Ativos desatualizados na máquina da GUI.**
   - Correção: depois de cada `git pull` com eventos `piece_resegmented`, correr `tools/rebuild_scans.py` ou `render.rebuild_assets` em D:.
   - Junta-se um teste de coerência ao abrir o servidor ou em `check_invariants(disk=True)`: bbox e área do alfa do recorte e do contorno do npz contra o registo do log. Avisa ou recusa servir peças incoerentes.
   - A `_clean_or_crop` passa a comparar `render/clean` com o recorte.
   - **Tem de provar:**
     - em D:, a verificação lista as peças velhas (espera-se ⊆ as 9 do §3.1);
     - depois do rebuild, as miniaturas de P0651/P0657 dão contra a GT o IoU deste relatório (0,928 / 0,919);
     - a captura nova bate com a exibida de hoje (IoU ≥ 0,95).
2. **Baías com tab inteiro e em peças de contacto.**
   - Correção: `_recover_scan_bays` aceita componentes fora do `minAreaRect` com raio inscrito ≥ 1,2 mm, ligadas só a esta peça. Também corre em peças `contacto`, fora de 1,0 mm da vizinha.
   - **Tem de provar:**
     - P0844, P0879 e P0852 ganham o tab (classe e cordas coerentes; secções ancoráveis ou gémea a ≤ 0,6 mm quando houver);
     - as 27 folhas só mudam nestas peças;
     - E-sym inalterado (teste `slow`);
     - S0023 dos contactos inalterado;
     - a GT de P0651/P0657 inalterada;
     - o projeto real só depois, com rebuild.
3. **Perda fina da exibição nos lados iluminados** (4,5 / 1,7 mm² de relva real em P0651/P0657). É a decisão da porta §6.1 (opções A/B da TRIAGEM §4).
   - **Tem de provar:** menos peça tirada contra a GT nos lados N/E, sem o halo voltar nos lados S/W (a mais ≤ 17,8 / 22,1 mm²).
   - A ponta do tab S de P0651 (1,13 mm) é do corte de contacto. Antes de mexer em `_CONTACT_TRIM`, é preciso medir de onde vem (watershed ou aparo).

## 8. Reprodução

```
python tools/diagnostico/segmentacao/comido.py --project projects/alpes antigo --copia <cópia do projeto de 2026-11-01>   # já feito: comido_antigo.npz
python tools/diagnostico/segmentacao/comido.py --project projects/alpes gt          # §1-§4, COMIDO_gt.jpg
python tools/diagnostico/segmentacao/comido.py --project projects/alpes detetor     # §5 (--force recalcula)
python tools/diagnostico/segmentacao/comido.py --project projects/alpes alcance     # §6, comido_resultados.json, COMIDO_alcance.jpg
pytest tests/test_maskcmp.py
```

- **Cópia antiga.** A cópia usada (`…/6da4480a…/scratchpad/g_alpes2`, log de 1905 linhas, 2026-11-01 23:51) é efémera. `comido_antigo.npz` guarda os 2 contornos necessários; o resto do subcomando `antigo` precisa da cópia.
- **Tempos.** `detetor` ≈ 50 s (com as poses de 613 peças em cache). `alcance` ≈ 7 min na primeira vez.
- **Estado do código.** Durante a medição, `src/segmentation.py` tinha no working tree uma alteração de outra sessão (extração de `_blackhat_gradient`, sem mudança de comportamento). As re-segmentações de S0009 e A2 correram com ela. Os números de S0009 reproduzem a PRADO **[V]**.
- **[NT]:**
  - a máquina D: (ativos, código, `render/clean`);
  - OpenCV 5.0;
  - a localização exata do resíduo de 1,37 mm de P0651 atual;
  - as 3 peças de (c) confirmadas na mão.

## 9. Correção, parte 1 (2026-11-07): ativos desatualizados e grau «recorte» nas Suspeitas

**T1. Ativos desatualizados** (`src/render.py`, `tools/rebuild_scans.py`; RENDER.md §4.1).
- `render.stale_assets(project)` compara o npz e os recortes com o log, peça a peça: npz ou contorno em falta, área do contorno preenchido, bbox com a margem de 2 % da segmentação, classe e cordas do npz, tamanho do recorte. Só lê o disco.
- Tolerâncias medidas em `projects/alpes` (958 peças) **[V]**:
  - área: diferença relativa máxima 2,3e-5, só arredondamento. O limite é 0,5 %. A `area_mm2` do npz (polígono) não serve: difere 1,2 % em mediana.
  - bbox: 0 diferenças; tamanho do recorte: 0; classe: 0.
  - cordas: diferença máxima 0,000 mm. O limite é 0,05 mm.
  - resultado: **0 peças em 1,1 s**.
- `render.rebuild_stale` re-segmenta só as folhas listadas e volta a verificar. `tools/rebuild_scans.py --stale [--dry-run]` usa-a.
- `_clean_or_crop` deixa de usar um `render/clean` mais antigo do que o recorte, ou de outro tamanho.
- **Cópia desatualizada** (npz, recortes e 161 `render/clean` de S0003/S0009/S0020/S0023 da cópia de 2026-11-01) **[V]**:
  - `check_invariants(disk=True)` dava **OK** antes: os invariantes não viam o problema.
  - `stale_assets` lista **11 peças em 4 folhas**, exatamente as 11 com eventos `piece_resegmented` no log: as 9 do §3.1 mais P0059 e P0778, com < 1 % de área.
  - Antes, a exibida de P0651/P0657 contra a GT dava IoU **0,678 / 0,661**. É mais baixo do que o 0,789 / 0,760 do §2 porque o recorte antigo é desenhado na origem da bbox nova (45 px acima).
  - `--stale` re-segmentou as 4 folhas em 39 s, com **0 eventos** (log 2109 → 2109). `check_invariants(disk=True)` OK; `stale_assets` depois: 0.
  - Depois, IoU **0,928 / 0,919**: os números do §2.
- O CLI deu o mesmo, com `--dry-run` (nada escrito) e a sério.
- **[NT]:** a pasta D: do Tiago. Um `render/clean` mais novo do que o recorte mas feito com código de limpeza antigo não é detetado.

**T2. Grau `recorte`** (`src/consistency.py`; `src/web/app.js`: só o rótulo e a linha de texto do bloco).
- É o sinal (a) do §5: `nn_max` > `TWIN_LOCAL_MAX_MM` 1,75 mm contra a gémea no tabuleiro, ou a silhueta sem 4 cantos com a gémea presente.
- A razão `baia` de `flags.suspeita_recorte` já é lida, para quando o segmentador a puser, com o texto «tab/baía fora do contorno (X mm²)».
- Fora: peças `manual_override`.
- As células do bloco c32|c33 levam o texto «corte c32|c33 não simétrico (exceção por confirmar)». Fica em `TWIN_EXCEPTIONS` por id de perfil até passar para `symmetry.excecoes` do `puzzle.json`, que já é lido se existir.
- **Em `projects/alpes` [V]:**
  - 0 impossível, 2 melhor rotação (P0833, P0343, as de antes);
  - **12 recorte, exatamente o bloco c32|c33** (P0289–P0294, P0492–P0494, P0496–P0498; `nn_max` 2,99–6,51 mm), todas com o texto da exceção; nenhuma outra peça.
  - `evaluate`: **4,3 s antes, 5,4–5,7 s depois** (+1,1–1,4 s, o cálculo `nn_max` em 512 × 512 pontos para as peças com gémea no tabuleiro).

## 10. Correção, parte 2 (2026-11-07): tabs inteiros fora do contorno, peças de contacto, razão `baia` e verificação no arranque

### 10.1 Tabs inteiros (`src/segmentation.py`, `_recover_bay_contour` / `_recover_scan_bays`)

**O que mudou.** O passo das baías (PRADO §2) só aceitava candidatos dentro do `minAreaRect` do contorno, alargado 0,3 mm. Um tab perdido fica fora desse retângulo (39–70 % da área, §6), por isso nunca era recuperado.
- Há agora uma segunda passagem, `_recover_tab_components`, com o interruptor `_BAY_TABS` (ligado).
- Candidatos fora do contorno, no limiar e na célula de Voronoi da peça, sem o retângulo.
- Cada componente tem de cumprir quatro condições:
  - sobreviver à mesma abertura de 1,1 mm (`_BAY_OPEN_MM`);
  - sair do retângulo;
  - ter raio inscrito ≥ `_BAY_TAB_RIN_MM` = 1,2 mm (o sinal (c) do §5: controlos ≤ 0,96, reais ≥ 1,34);
  - tocar a peça ao longo de pelo menos `_BAY_TAB_THROAT_MM` = 2,5 mm (a base de um tab).
- A janela de procura cresce `_BAY_TAB_REACH_MM` = 6 mm.
- A validação continua a mesma: ganho entre 2 mm² e 10 % da área, 4 cantos, sem mais violações de forma (`_shape_violations`).

**Peças de contacto.** Com `_BAY_CONTACT` (ligado), os membros de grupos de contacto entram também no passo. Os candidatos ficam a ≥ 1,0 mm de qualquer outra peça (`_BAY_CONTACT_GAP_MM`). A partição de CONTACTOS não é tocada.

**Duas formas medidas nas 27 folhas** (`tools/diagnostico/segmentacao/baias.py`; antes = `off`, os três interruptores desligados) [V]:

| variante | peças alteradas | contagem e numeração | tempo das 27 folhas |
|---|---|---|---|
| `off` (código anterior) | **0**: igual ao índice, contorno a contorno | 27/27 iguais | 90,0 s |
| A: tabs (abertura + raio + garganta) | P0844, P0852, P0879 | 27/27 iguais | 98,4 s |
| B: retângulo alargado para 6 mm, a validação de forma decide | as mesmas 3 | 27/27 iguais | 173,7 s |
| **C = A + peças de contacto (por omissão)** | **as mesmas 3**; a extensão aos contactos não mudou nenhuma peça | 27/27 iguais | 98,9–103,1 s |

- **Escolhida A/C.**
- A é cirúrgica: só muda o lado do tab.
- B mexe também nas cordas dos outros lados, porque o retângulo de 6 mm apanha a sombra. Em P0879 a corda W passa de 16,86 para 16,39 mm. B é também 1,9 vezes mais lenta.

**Porta (antes → depois)** [V salvo indicação]:

1. **Os 3 alvos ganham o tab** (figura `COMIDO_baias.jpg`, vista: antes a vermelho, depois a ciano, área ganha a magenta; os rótulos mostram `index_in_scan`):

   | peça | área (mm²) | ganho | classe | lado N | cordas (mm) |
   |---|---|---|---|---|---|
   | P0844 (S0024 nº 11) | 378,0 → 398,5 | +20,5 mm², 5,4 % | BTFT → **BTTT** | F → T | [19,17; 17,61; 18,20; 15,74] → [18,85; 17,61; 18,16; 16,26] |
   | P0879 (S0025 nº 18) | 360,1 → 379,6 | +19,4 mm², 5,4 % | BTTF → **BTTT** | F → T | — |
   | P0852 (S0024 nº 19) | 361,6 → 380,5 | +18,9 mm², 5,2 % | BTBT, igual | já T (tab truncado); agora inteiro | — |

   - Nenhum fica à justa do limite de 10 %.
   - **P0852 na sua secção G0070:** o lado N fica contra o S da vizinha de cima P0849, T↔B, e o `side_complement` passa de 1,33 para 1,26 mm.
   - P0844 e P0879 estão em secções de uma só peça, sem gémea colocada: `legacy.solve` e `free_dist` **[NT]**.
2. **E-sym bit a bit igual.** Os contornos de A1, A2 e B2 são iguais com os interruptores desligados e por omissão, 20/20 em cada folha, e nenhuma tem a razão `baia`. `tests/test_segment_scan_esym.py` (`slow`) passa.
3. **As 27 folhas:** contagem e numeração iguais; só mudam os 3 alvos. S0023 e S0020 ficam inalteradas.
4. **GT de P0651/P0657 inalterada:** o contorno de S0020 é igual, logo as métricas do §2 são as mesmas (IoU 0,928 / 0,919 da exibida).
5. **Controlos** P0156, P0195 e P0445: iguais (na figura, sem magenta).
6. **Testes:** `pytest tests/test_segmentation.py tests/test_segment_scan_esym.py` dá 21 passed. Há 3 testes novos:
   - `_recover_bay_contour` direto: um quadrado sem o tab e um limiar com ele. Com `tabs=False` devolve `None`, ou seja, falha sem a extensão. Com `tabs=True` recupera o tab dentro de 3 % da área;
   - uma faixa de sombra de 0,6 mm ao longo de um lado não é recuperada;
   - a razão `baia` aparece com o tab e não aparece com a faixa.

### 10.2 Razão `baia` em `_flag_suspect_cuts` (só sinaliza)
- **Interruptor e regra:** `_FLAG_BAYS` (ligado). É o sinal (c) do §5 sobre o limiar de `segment_scan`, calculado depois do passo das baías (`_bay_signal`):
  - componentes do limiar fora do contorno, na célula própria (mais perto desta peça do que de qualquer outra), a ≥ 1,0 mm das outras e que tocam a peça;
  - janela de 7 mm;
  - raio inscrito > 1,2 mm → `razoes += ["baia"]`, com `baia_mm2` e `baia_r_mm`;
  - `src/ingest.py` copia `suspeita_recorte` inteira para `flags` (`SEG_FLAG_KEYS`, linha 170) [V].
- **Sem a recuperação** (variante `F`, em S0009/S0024/S0025) marca exatamente os 3 alvos: r 2,17 / 1,79 / 2,15 mm, 20,9 / 29,3 / 27,3 mm².
- **Com a recuperação** (por omissão), nas 27 folhas marca só 2 peças, ambas `descartada` em S0003:
  - P0053, 284 mm², sem classe: r 2,11 mm, 47,0 mm²;
  - P0058, 643 mm², objeto duplo de contacto: r 1,91 mm, 46,1 mm².
  - Nenhuma peça em uso fica marcada.
- **Custo:** 3,2 s nas 27 folhas, cerca de 0,12 s por folha.
- O grau `recorte` do `src/consistency.py` (§9) já lê `baia_mm2`.

### 10.3 Verificação no arranque do servidor (`src/server.py`, `Gui._check_stale`)
- **Quando corre:** em `_prepare`, depois da regra das pastas em falta e antes de compor o tabuleiro.
- **O que faz:**
  - corre `render.stale_assets`;
  - se houver folhas desatualizadas, passa o estado a «a preparar» e escreve no progresso «N peças em M folhas desatualizadas (depois de um git pull?): a refazer…»;
  - corre `render.rebuild_stale` e termina com «ativos refeitos: … 0 eventos» ou com o aviso de código diferente;
  - guarda `stale_info` = `{desatualizados_antes, folhas, refeitos, eventos, restantes, segundos, aviso, erros}`, exposto em `GET /api/status` como `ativos`.
- **Teste novo:** um projeto ingerido com o contorno de uma peça encolhido no npz. No arranque o npz é reposto, com 1 peça refeita, 0 eventos e o log igual. `/api/status` mostra `ativos`, e um segundo arranque não refaz nada.
- **Teste existente alterado (declarado):** `test_prepare_runs_rebuild_when_assets_missing` passa a desligar `render.stale_assets` com monkeypatch.
  - O projeto de `_project` é feito à mão: bbox com +10 px e área do polígono, não o que uma ingestão escreve.
  - A verificação considerava-o desatualizado e chamava o `rebuild_assets` falso uma segunda vez.
- **Tempo de arranque, cópia de `projects/alpes`** [V]:
  - coerente: sem a verificação 2,1–2,2 s, com ela 3,1–3,2 s (+1,0 s, `segundos` 1,0);
  - cópia desatualizada (a do §9), com o código final: 81,1 s no total, dos quais 48,5 s são o rebuild; 11 refeitas,
    0 eventos, log 2109 → 2109, `check_invariants(disk=True)` OK; o segundo arranque leva 3,5 s e não refaz nada.
- **Ordem a seguir [NT]:** refazer S0024/S0025 em C: (os 3 eventos `piece_resegmented`) e fazer push **antes** de a máquina D: correr este código.
  - Caso contrário, uma folha desatualizada em D: re-segmentada com o código novo gera lá eventos com motivo `stale`.
  - O log seria então escrito nas duas máquinas.
