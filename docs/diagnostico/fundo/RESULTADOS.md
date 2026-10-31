# E-fundo: cor do fundo e método de contorno (2026-10-31)

Dados: os 12 scans de julho, com as mesmas peças (11 papéis de cor e o scan da impressora, que é um enquadramento diferente). Os 3 scans a 600 dpi (rosa, azul_claro, impressora) foram reamostrados a 300 dpi **antes** de qualquer método (`cv2.resize`, `INTER_AREA`, ×0,5). O dpi lê-se do cabeçalho JPEG e confere com o tamanho (A4: 210 × 297 mm; impressora 215 × 297 mm). Depois da reamostragem, 1 px = 0,0847 mm em todos.
Script: `tools/diagnostico/fundo/efundo.py` (≈ 4,5 min do zero; `--cache` reutiliza as segmentações). Números em `results.json`. O E-sym com a variante `sombra` está em `docs/diagnostico/gemeos/results.json` (chave `esym`).
Etiquetas: **[V]** verificado aqui (com n); **[NT]** não testado ou inferido; **[F]** testado e falha.

## Resumo

1. **N = 61 peças físicas [V, contagem à vista].** Inclui um par encaixado (ids 54 + 60, separado corretamente por `segment_pieces`) e várias peças encostadas. Não há peças empilhadas. A estimativa "≈ 63–65 por croma" do plano estava errada.
2. **Fundo vencedor pela regra pré-registada: verde [V].** É o único fundo que passa as duas portas (recall 61/61 e rugosidade p95 1,095 < 1,1). Também tem o menor RMS free mediano entre fundos em pose diferente: 0,44 mm com o método (c), n = 86 pares. Seguem-se azul (0,55) e vermelho (0,60), que falham as portas (rugosidade p95 1,14 e recall 53/61, respetivamente). Como o vencedor é o verde, **não há scan de confirmação a pedir.**
3. **Método vencedor pelo critério M3 no E-sym: (b) `simples`/híbrido, não (c) [V].** O (c) `sombra` falha o M3 nos gémeos [F]: A2/B2 mediano 0,77 mm, top-1 15/20. A causa é que (c) apaga parte das peças de prado escuro sobre o papel verde. Numa peça (B2 (0,4)) o contorno entra vários mm (RMS 4,7 mm ao gémeo), o que é exatamente o limite conhecido "relva sobre verde". O híbrido cumpre o M3 (0,38 mm, 20/20, rugosidade p95 B2 1,085), mas inclui a sombra projetada.
4. **Nas peças claras de julho, (c) é o melhor contorno entre fundos [V].** Pose diferente no verde: (a) 0,76, (b) 0,66, (c) 0,44 mm (n = 86–88). Mesma pose, só contra o verde: no laranja (a) 0,51, (b) 0,40, (c) **0,24** mm (n = 61), já ao nível do re-scan híbrido A1/A2 (0,27). A corda mediana do verde com (c) é **18,20 mm**, igual ao nominal 18,2; (a) dá 18,12 e (b) 18,87, este último por incluir a sombra.
5. **Fundos acromáticos** (azul_claro e bege saturam a branco no scanner; preto; impressora): a rejeição por tonalidade não se aplica (C_fundo < 8), por isso (c) = (b). Nos brancos, a sombra cinzenta larga fica dentro do contorno de (b)/(c), e o (a) morde as peças claras.
6. **Não há proposta `segment_scan`:** o (c) não cumpre o M3. O que falhou e o próximo passo de desenho estão no fim deste documento.

## N físico no `scan_verde` [V]

Contei à vista sobre o scan com os contornos de `segment_pieces` numerados (61 deteções, 0 clusters) e percorri o scan em duas metades sobrepostas: cada peça visível tem exatamente um número e nenhum número cobre duas peças. Casos particulares:
- **Par encaixado 54 + 60** (canto inferior direito; a patilha de uma entra no encaixe da outra): são 2 peças e saem como 2 deteções.
- Peças encostadas mas separadas: 27/31, 35/36, 42/43, 3/4. Não há peças empilhadas nem escondidas no bordo (S1 corrigido; 0 peças com `touches_frame` em todos os 12 scans).
- **N = 61.** Coincide com o número do Tiago. Os "≈ 63–65 por croma" (§3.3 do plano) eram uma sobre-estimativa da contagem por área.

O recall usa N = 61 em todos os fundos. Assume-se que os 12 scans têm as mesmas 61 peças. Isto é plausível pela sobreposição de posições (abaixo), mas não foi contado à vista fora do verde [NT].

## Métodos (parâmetros fixos para os 12 fundos)

| Método | Separação das peças | Fronteira |
|---|---|---|
| (a) `seg` | `segment_pieces` a 300 dpi, sem moldura (S1 corrigido em `bc124d2`) | `segment_pieces` |
| (b) `simples` | `segment_pieces` + Voronoi (`esym.hybrid_pieces`, banda 1,5 mm) | `esym.simple_mask`: Lab ponderado [0,5; 1; 1], d > 28, abertura 5, fecho 9; **fundo pela orla** (`esym.rim_bg`: faixa a 100–250 px de cada bordo, moda robusta) |
| (c) `sombra` | idem | (b), mas antes da abertura/fecho os píxeis de sombra passam a fundo: `L < L_fundo` **e** `|h − h_fundo| < τ_h` **e** `C ≥ κ·C_fundo` (`esym.shadow_mask`). Não se aplica se `C_fundo < 8` (fundo acromático: tonalidade indefinida) |

**Calibração da sombra, uma só vez no `scan_verde` [V]:**
- Candidatos a sombra: píxeis que o limiar dá como peça fora da máscara `segment_pieces` dilatada (5×5) e a < 1,5 mm dela (n = 367 993).
- Interior das peças: máscara `segment_pieces` erodida 11×11 (n = 2 368 379).
- Regra, fixada antes de olhar para os resultados por fundo: grelha do plano τ_h ∈ {10, 12, 15, 20}°, κ ∈ {0,4; 0,5; 0,6}; escolhe-se a maior captura de candidatos com falsos positivos no interior < 0,01 %.
- **Escolha: τ_h = 10°, κ = 0,4.** Captura 73,3 % dos candidatos, com 0,0024 % de falsos positivos no interior. τ_h = 12° dá a mesma captura com mais falsos positivos (0,0040 %); τ_h = 15° com κ = 0,4 ultrapassa a porta (0,0106 %).
- Os 27 % não capturados são sobretudo o **núcleo preto da sombra** junto à aresta: 20 % dos candidatos têm L\* < 15, sem tonalidade mensurável. Em menor parte são píxeis de peça onde `segment_pieces` mordeu.
- Aplicado sem alteração aos 12 fundos e aos scans dos gémeos.
- Figura: `fundo_sombra_mascara.png` (verde, laranja, vermelho; magenta = píxeis que o limiar daria como peça e o modelo rejeita).

## Identidade da peça e pose

- **Identidade (id = índice no verde):**
  - GT por posição: translação da folha estimada pela moda dos deslocamentos e depois `cortes.position_gt`, tol 40 px.
  - As peças que não casam por posição emparelham-se por forma: NN mútuo em RMS free < 0,7 mm **e** mesma classe topológica, com união dos 3 métodos e descarte dos conflitos.
  - Peças emparelhadas (por posição + por forma): laranja 61 (60 + 1), azul 59 (59 + 0), amarelo 37, amarelo_claro 31, azul_claro 50 (48 + 2), bege 51, preto 55 (43 + 12), rosa 53 (46 + 7), verde_claro 34 (32 + 2), vermelho 53 (4 + 49), impressora 24 (7 + 17).
- **Correção ao plano [V]:** o layout não é só verde/laranja/azul. bege (96 %), azul_claro (94 %), amarelo, amarelo_claro, rosa e verde_claro (82–84 %) e preto (73 %) têm as mesmas posições que o verde. Só vermelho (7 %) e impressora (12 %) foram rearranjados.
- **Pose por par de observações:** "mesma pose" quando a peça está no mesmo sítio nos dois scans, depois da translação da folha (peça não mexida) e só se os dois scans tiverem layout comum (≥ 30 % de peças casadas). Senão conta como "pose diferente".
- **A rotação da peça entre poses não foi medida de forma fiável [NT].** O ângulo do alinhamento free tem mediana de 10,5° nas peças emparelhadas por forma, mas é ruidoso nas peças mal segmentadas: p95 de 110° mesmo em peças não mexidas. Por isso, "pose diferente" quer dizer "peça mexida" e não "rodada mais do que X°".
- **Viés de seleção (declarado):**
  - O emparelhamento por forma só aceita pares com RMS < 0,7 mm, o que favorece as peças bem segmentadas e trunca as distâncias.
  - Para não favorecer o verde, as métricas do verde usam identidades obtidas com o **laranja** como referência. O laranja está na mesma pose do verde, por isso a ligação laranja → verde é por posição. Todos os outros fundos usam o verde como referência.
  - O vermelho e a impressora continuam favorecidos nos pares que envolvem as suas próprias peças: foram emparelhadas por forma contra o verde.
  - O recall do vermelho, preto e impressora mede também o emparelhamento, não só a deteção (ver "recall de deteção" no ranking).

## Tabela fundos × métodos [V]

RMS free (mm; `dist.free_dist`, 512 pts, σ = 1,5) da mesma peça entre o fundo X e os outros 11, no formato mediana / p90 [n pares]. "Não pálidos" = parceiros fora de {amarelo, amarelo_claro, verde_claro}. "vs verde" = só pares com o verde. Rugosidade = perímetro / perímetro suavizado, em todas as peças com cantos (mediana / p95). Corda = mediana dos lados (nominal 18,2). Área = mediana da diferença relativa à mesma peça no verde, com o mesmo método.

| Fundo | Método | Pose diferente | Pose dif., não pálidos | Mesma pose | Mesma pose, não pálidos | vs verde | Recall (emparelhadas com cantos / 61) | Rugosidade | Corda | Área vs verde |
|---|---|---|---|---|---|---|---|---|---|---|
| verde | seg | 0,76 / 2,32 [88] | 0,77 [86] | 0,93 / 2,34 [390] | 0,88 [301] | — | 61 | 1,09 / 1,17 | 18,12 | — |
| verde | simples | 0,66 / 1,73 [86] | 0,66 [83] | 0,57 / 3,06 [350] | 0,54 [274] | — | 61 | 1,09 / 1,11 | 18,87 | — |
| verde | **sombra** | **0,44** / 1,57 [86] | 0,44 [83] | 0,57 / 2,75 [332] | 0,48 [273] | — | 61 | 1,08 / **1,09** | **18,20** | — |
| laranja | seg | 0,69 / 2,67 [104] | 0,69 [100] | 0,73 / 2,23 [391] | 0,69 [303] | 0,51 [61] | 61 | 1,08 / 1,16 | 17,94 | −2,0 % |
| laranja | simples | 0,76 / 2,70 [101] | 0,76 [97] | 0,68 / 3,31 [350] | 0,55 [275] | 0,40 [61] | 61 | 1,10 / 1,14 | 18,59 | −4,3 % |
| laranja | sombra | 0,62 / 2,87 [101] | 0,62 [97] | 0,68 / 3,00 [332] | 0,60 [274] | **0,24** [61] | 61 | 1,09 / 1,14 | 18,15 | −2,6 % |
| azul | seg | 0,78 / 2,91 [95] | 0,78 [93] | 0,70 / 2,20 [384] | 0,68 [296] | 0,66 [58] | 58 | 1,10 / 1,19 | 17,91 | −2,7 % |
| azul | simples | 0,68 / 1,98 [89] | 0,68 [87] | 0,57 / 3,06 [348] | 0,51 [272] | 0,30 [58] | 58 | 1,09 / 1,13 | 18,82 | −2,0 % |
| azul | sombra | 0,55 / 1,91 [88] | 0,55 [87] | 0,61 / 2,84 [331] | 0,54 [271] | 0,35 [58] | 58 | 1,11 / 1,14 | 18,41 | +3,0 % |
| amarelo \* | seg | 1,18 / 3,45 [53] | 1,18 [49] | 1,11 / 2,77 [247] | 1,13 [214] | 0,95 [35] | 35 | 1,09 / 1,17 | 17,99 | −1,3 % |
| amarelo \* | simples | 1,72 / 3,79 [45] | 1,70 [40] | 1,33 / 5,24 [203] | 1,42 [171] | 0,70 [32] | 32 | 1,10 / 1,21 | 18,80 | −3,8 % |
| amarelo \* | sombra | 1,92 / 4,70 [32] | 2,14 [31] | 1,55 / 5,18 [147] | 1,67 [126] | 1,35 [25] | 25 | 1,20 / 1,33 | 18,19 | −0,2 % |
| amarelo_claro \* | seg | 2,13 / 3,31 [53] | 2,01 [48] | 1,39 / 3,10 [184] | 1,49 [148] | 1,45 [27] | 27 | 1,11 / 1,21 | 17,59 | −9,2 % |
| amarelo_claro \* | simples | 2,13 / 4,49 [45] | 2,16 [40] | 1,36 / 3,27 [153] | 1,53 [120] | 1,39 [23] | 23 | 1,11 / 1,22 | 17,99 | −11,2 % |
| amarelo_claro \* | sombra | 2,15 / 6,63 [29] | 2,15 [27] | 1,45 / 3,07 [117] | 1,47 [92] | 1,31 [17] | 17 | 1,13 / 1,24 | 17,43 | −14,0 % |
| azul_claro (branco) | seg | 0,96 / 2,98 [86] | 0,90 [79] | 0,96 / 2,61 [316] | 0,83 [254] | 1,12 [48] | 48 | 1,12 / 1,21 | 17,82 | −5,7 % |
| azul_claro (branco) | simples = sombra | 1,84 / 4,03 [65] | 1,35 [60] | 1,22 / 4,15 [207] | 1,14 [169] | 1,15 [33] | 33 | 1,14 / 1,33 | 18,12 | −9,6 % |
| bege (branco) | seg | 0,96 / 3,04 [85] | 0,93 [81] | 0,96 / 2,67 [340] | 0,80 [266] | 1,07 [51] | 51 | 1,12 / 1,19 | 17,77 | −7,1 % |
| bege (branco) | simples = sombra | 0,94 / 3,50 [74] | 0,93 [72] | 0,83 / 3,82 [294] | 0,69 [231] | 0,64 [47] | 47 | 1,11 / 1,23 | 18,44 | −7,1 % |
| preto | seg | 0,68 / 2,28 [149] | 0,67 [135] | 0,79 / 2,31 [292] | 0,73 [232] | 0,75 [55] | 55 | 1,09 / 1,16 | 17,75 | −3,9 % |
| preto | simples = sombra | 0,69 / 2,36 [139] | 0,69 [125] | 0,98 / 3,11 [259] | 0,86 [212] | 0,71 [55] | 55 | 1,10 / 1,15 | 18,51 | −7,0 % |
| rosa | seg | 0,70 / 2,60 [121] | 0,66 [109] | 0,85 / 2,30 [323] | 0,78 [255] | 0,97 [53] | 53 | 1,11 / 1,18 | 17,95 | −3,2 % |
| rosa | simples | 0,77 / 3,77 [95] | 0,71 [87] | 0,98 / 4,64 [252] | 0,90 [208] | 0,60 [44] | 44 | 1,12 / 1,27 | 18,42 | −6,4 % |
| rosa | sombra | 0,84 / 3,53 [92] | 0,81 [86] | 1,06 / 3,80 [235] | 0,96 [203] | 0,72 [43] | 43 | 1,13 / 1,28 | 18,49 | +6,8 % |
| verde_claro \* | seg | 1,14 / 3,26 [64] | 1,24 [59] | 1,19 / 2,78 [204] | 1,19 [167] | 1,12 [30] | 30 | 1,11 / 1,19 | 17,74 | −9,5 % |
| verde_claro \* | simples | 1,63 / 4,33 [49] | 1,87 [45] | 1,06 / 3,88 [161] | 1,08 [128] | 1,00 [24] | 24 | 1,12 / 1,23 | 18,13 | −8,7 % |
| verde_claro \* | sombra | 1,13 / 3,32 [41] | 1,19 [38] | 1,12 / 2,99 [131] | 1,11 [107] | 0,72 [20] | 20 | 1,13 / 1,18 | 17,64 | −9,6 % |
| vermelho | seg | 0,88 / 3,07 [438] | 0,86 [358] | — | — | 0,79 [53] | 53 | 1,07 / 1,13 | 18,12 | +1,8 % |
| vermelho | simples | 0,76 / 3,44 [399] | 0,67 [331] | — | — | 0,53 [53] | 53 | 1,08 / 1,10 | 18,73 | −2,6 % |
| vermelho | sombra | 0,60 / 3,32 [381] | 0,53 [330] | — | — | 0,26 [53] | 53 | 1,08 / 1,10 | 18,41 | +1,5 % |
| impressora (branco) | seg | 0,88 / 3,25 [200] | 0,77 [170] | — | — | 0,76 [24] | 24 | 1,12 / 1,22 | 17,45 | −5,6 % |
| impressora (branco) | simples = sombra | 1,25 / 2,96 [167] | 1,13 [148] | — | — | 1,12 [21] | 21 | 1,13 / 1,30 | 18,20 | −7,1 % |

\* fundo pálido: fica na tabela mas não pode ganhar (regra pré-registada).

Leitura:
- **Os p90 de 2–3 mm são dos parceiros, não do fundo X.** Cada linha compara X com os outros 11, e os fundos pálidos e brancos têm peças com contornos de vários mm de erro. A coluna "vs verde" (o verde é o fundo de melhor contorno, ver `fundo_matriz.png`, 4.º painel) é a comparação mais limpa.
  - Mesma pose com (c): laranja 0,24, vermelho 0,26 (este com viés de seleção), azul 0,35 mm.
  - Com (b): 0,40 / 0,53 / 0,30.
  - Com (a): 0,51 / 0,79 / 0,66.
- **A sombra explica a corda e a área.** (b) inclui a sombra: corda 18,4–18,9 mm, acima de 18,4. (a) morde: 17,4–18,0 mm, perto ou abaixo de 17,8 nos brancos e pálidos. (c) fica entre 18,15 e 18,41 nos fundos cromáticos bons. A área de (c) relativa ao verde sai positiva (+1,5 a +6,8 %) nos fundos onde (c) não remove a sombra tão bem como no verde (rosa, azul) e nos acromáticos (onde (c) = (b)).
- **Variação de área da mesma peça entre fundos** (CV por peça, mediana sobre as 61 peças com ≥ 3 fundos): (a) 5,3 %, (b) 7,4 %, (c) 7,3 % [V]. Esta métrica é dominada pelos fundos pálidos e brancos. Não distingue os métodos nos fundos bons.
- **Limiar puro (sem a separação de `segment_pieces`), só recall:** componentes do tamanho de uma peça (0,6–1,5 × área mediana) no verde: (b) 23, (c) 37 de 61. A rejeição da sombra corta pontes entre peças, mas o limiar sozinho continua a juntar peças (verde 36 → 48 componentes). A separação por `segment_pieces` continua necessária.

## Ranking pré-registado (aplicado tal como escrito) [V]

Regra (plano, Parte B):
- Elegível se recall ≥ 95 % com (a) ou (c), em que recall = peças detetadas, sem clusters, e emparelhadas / N = 61.
- Ordena por RMS mediano entre fundos em pose diferente, com o melhor método.
- Desempate pelo p90.
- Porta: rugosidade p95 < 1,1.
- Os fundos pálidos não ganham.

| # | Fundo | Melhor método | Pose dif., mediana / p90 | Recall (a) / (c) | Recall de deteção (a) | Rugosidade p95 | Elegível | Porta rugosidade | Qualifica |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **verde** | sombra | **0,44** / 1,57 | 61 / 61 | 61/61 | 1,095 | sim | sim | **sim** |
| 2 | azul | sombra | 0,55 / 1,91 | 58 / 58 (95,1 %) | 59/61 | 1,142 | sim | não | não |
| 3 | vermelho | sombra | 0,60 / 3,32 | 53 / 53 | 59/61 | 1,099 | não | sim | não (sim se o recall for só de deteção) |
| 4 | laranja | sombra | 0,62 / 2,87 | 61 / 61 | 61/61 | 1,135 | sim | não | não |
| 5 | preto | sombra (= simples) | 0,66 / 2,41 | 55 / 55 | 59/61 | 1,153 | não | não | não |
| 6 | rosa | seg | 0,70 / 2,60 | 53 / 43 | 56/61 | 1,177 | não | não | não |
| 7 | bege | sombra (= simples) | 0,83 / 3,48 | 51 / 47 | 53/61 | 1,227 | não | não | não |
| 8 | impressora | seg | 0,88 / 3,25 | 24 / 21 | 61/61 | 1,215 | não | não | não |
| 9 | azul_claro | seg | 0,96 / 2,98 | 48 / 33 | 51/61 | 1,210 | não | não | não |
| — | verde_claro, amarelo, amarelo_claro | — | 1,13 / 1,18 / 2,13 | ≤ 30 | ≤ 43 | ≥ 1,17 | pálidos | — | não |

- **Fundo vencedor: verde.** É também o vencedor com o recall só de deteção e com parceiros não pálidos (análises de sensibilidade em `results.json`, `ranking`).
- **Método vencedor (critério M3 no E-sym, Parte D): (b) `simples`/híbrido.** O (c) falha o M3 [F]. Há uma tensão a registar: com (b), o verde tem rugosidade p95 1,11 e não passaria a porta de rugosidade, que só passa com (c) (1,095). O ranking usa o melhor método por fundo, tal como foi escrito.
- Os overlays `fundo_<cor>__contours.jpg` mostram o método vencedor (b). Magenta = peça sem contorno ou sem cantos; número = id no verde; `?` = sem identidade.
- **Pedido ao Tiago: nenhum** (vencedor = verde).

## E-sym com a variante `sombra` (Parte D) [V, n = 20 por linha]

Os `.npz` dos gémeos foram regenerados sem moldura (`segcache.PAD = 0`, `--force`). Formato: mediana / p90 / máx. (mm). Não-gémeo mais próximo (em B2 ∪ A1) dado como mediana / mín.

| Variante, métrica | Re-scan A1/A2 | Gémeo A1/B2 | Gémeo A2/B2 | Não-gémeo, med / mín | Top-1 A1→B2 / B2→A1 / A2→B2 | NN mútuo (corretos) | Margem mín / mediana | Margem < 1,5 |
|---|---|---|---|---|---|---|---|---|
| seg, corner | 0,71 / 0,88 / 0,94 | 1,05 / 1,37 / 2,23 | 1,11 / 1,59 / 2,25 | 0,83 / 0,55 | 13 / 16 / 9 | 13 (11) | 0,48 / 0,91 | 16 |
| seg, free | 0,98 / 1,21 / 1,25 | 1,33 / 2,11 / 3,13 | 1,93 / 2,65 / 3,31 | 0,92 / 0,63 | 8 / 14 / 8 | 9 (7) | 0,34 / 0,69 | 18 |
| híbrido, corner | 0,37 / 0,48 / 0,51 | 0,34 / 0,48 / 0,67 | 0,51 / 0,66 / 0,70 | 0,74 / 0,58 | 20 / 20 / 20 | 20 (20) | 1,10 / 2,23 | 3 |
| **híbrido, free** | 0,27 / 0,40 / 0,50 | 0,29 / 0,43 / 0,45 | **0,38** / 0,51 / 0,64 | 0,83 / 0,60 | **20 / 20 / 20** | 20 (20) | 1,78 / 2,93 | 0 |
| sombra, corner | 0,40 / 0,51 / 0,61 | 0,43 / 1,05 / 2,42 | 0,66 / 1,17 / 2,52 | 0,72 / 0,43 | 16 / 18 / 15 | 16 (16) | 0,48 / 1,67 | 8 |
| **sombra, free** | 0,42 / 0,53 / 0,61 | 0,45 / 1,54 / 4,72 | **0,77** / 1,60 / 4,77 | 0,82 / 0,52 | **15 / 18 / 15** | 15 (15) | 0,36 / 2,10 | 8 |

Por lado (lados não-F, n = 60; mediana) e rugosidade (n = 20 por scan):

| Variante | Re-scan A1/A2: \|ΔL\| med / p90 | Gémeo A2/B2: RMS global, \|ΔL\| med / p90, dp ΔL | Tipo T/B coincide (A2/B2) | Rugosidade B2 med / p95 / máx. | Rugosidade A1 / A2 med | Corda mediana A1 / A2 / B2 |
|---|---|---|---|---|---|---|
| seg | 0,29 / 0,65 | 0,96, 0,51 / 0,79, 0,56 | 60/60 | 1,145 / 1,195 / 1,215 | 1,096 / 1,087 | 17,68 / 17,66 / 18,00 |
| híbrido | 0,25 / 0,65 | 0,53, 0,45 / 0,93, 0,49 | 60/60 | 1,068 / 1,085 / 1,092 | 1,067 / 1,065 | 18,62 / 18,61 / 18,65 |
| sombra | **0,13 / 0,29** | 0,57, 0,33 / 0,70, 0,44 | 60/60 | 1,095 / 1,139 / 1,201 | **1,056 / 1,054** | **18,08 / 18,03** / 17,91 |

**Critério M3** (A2/B2 free ≤ 0,5 mm, top-1 20/20, rugosidade p95 B2 < 1,1):
- `sombra` **não cumpre** [F]: 0,77 mm, 15/20, 1,139.
- `hibrido` cumpre [V]: 0,38 mm, 20/20, 1,085.
- `seg` não cumpre [F]: 1,93 mm, 8/20, 1,195.

Os 6 pares gémeos com A2/B2 > 1 mm em `sombra` (A1 (0,0), (0,1), (0,3), (1,1), (1,2), (2,1)) estão todos nas filas 0–2. Que todos tenham peça de prado em B2 está confirmado só para o pior, A1 (0,0) ↔ B2 (0,4), com 4,7 mm (figura); os outros 5 não foram vistos um a um [NT].

Nas peças azuis/claras (A1/A2), o (c) é o melhor contorno medido até agora:
- re-scan \|ΔL\| mediano de 0,13 mm (contra 0,25 no híbrido e 0,29 no seg);
- rugosidade de 1,055;
- corda de 18,0–18,1 mm (nominal 18,2).

O RMS free do re-scan (0,42) é pior do que no híbrido (0,27): o (c) deixa o núcleo preto da sombra, cuja largura depende da pose [NT, inferido das figuras].

**`seg` e `hibrido` reproduzem os números publicados sem a moldura?**
- **híbrido: sim [V].** Free 0,27 / 0,29 / 0,38 contra 0,27 / 0,29 / 0,39; corner 0,37 / 0,34 / 0,51 contra 0,36 / 0,34 / 0,49; top-1 20/20/20 (corner A2→B2 passou de 18 para 20).
- **seg: sim dentro de ±0,12 mm [V].** Free 0,98 / 1,33 / 1,93 contra 0,96 / 1,42 / 1,81; corner 0,71 / 1,05 / 1,11 contra 0,68 / 1,01 / 1,15. Os top-1 do seg variam mais (corner A2→B2 passou de 13 para 9; free B2→A1 de 12 para 14): o seg é instável a 1–2 px de deslocamento. A conclusão não muda.
- **A extrapolação reproduz-se [V]:** t95 = 0,507 (era 0,505); mín. não-gémeo da mesma classe 0,600; 40/40 no pool de 100.

## Verificação visual (skill `cv-visual-verification`)

- `fundo_overlays_sombra.png` (e `_seg`, `_simples`; as mesmas 6 peças, ids do verde 59, 58, 2, 49, 46, 0, ordenadas da mais escura para a mais clara, nos 12 fundos, 2×, lado inferior-esquerdo):
  - **Verde:** o contorno verde (c) cola-se à aresta física, o azul (b) inclui a banda de sombra e o vermelho (a) fica próximo de (c), com dentes.
  - **Laranja e azul:** (c) deixa a parte preta da sombra (ex.: peça 49 no laranja e peça 0 no azul).
  - **Brancos** (azul_claro, bege, impressora): (b) = (c) incluem uma sombra cinzenta larga.
  - **Pálidos:** (a) e (b) mordem as peças claras em degraus.
- `fundo_sombra_mascara.png`: a rejeição (magenta) é uma faixa de 0,5–1 mm só nos lados inferior e esquerdo, e não toca na peça preta 59 no verde nem na peça creme no vermelho. A linha preta na aresta fica (fica fora do modelo por não ter croma).
- `esym_franjas_sombra_B2.png` (as 3 peças de prado mais escuras de B2):
  - Em (0,1) e (2,3), (c) segue a aresta entre o seg (que morde) e o híbrido (que inclui sombra).
  - **Em (0,4), (c) entra vários mm pela zona de relva verde-viva à esquerda**, que tem a mesma tonalidade do papel e croma ≥ 0,4·C_fundo. É a falha que faz o (c) chumbar o M3.
- `fundo_matriz.png`: os 4 painéis (pose diferente, mesma pose, pose dif. com parceiros não pálidos, só contra o verde) mostram o mesmo padrão. A coluna (c) é a mais clara nos fundos cromáticos bons, e as linhas dos fundos pálidos e brancos são as mais escuras.

## Porque não há "Proposta `segment_scan`" e qual é o próximo passo

**O que falhou [F]:** o modelo de sombra é só de cor e é aplicado em toda a imagem. Um píxel de peça com a tonalidade do papel e croma suficiente (relva sobre verde) é indistinguível de sombra, e a abertura/fecho propaga a remoção para dentro da peça. Nos dados de julho (peças claras de céu e nuvem) isto não aparece. Nos gémeos B2 (prado escuro) aparece em 6/20 pares.

**Próximo passo de desenho (M3), por ordem [NT; nada disto foi testado]:**
1. **Restringir a rejeição à geometria da sombra.** A sombra é uma faixa fina (≈ 0,5–1 mm) **fora** da peça e só nos lados virados para a direção da sombra, que é fixa no referencial do scanner (aqui, inferior e esquerdo; pode estimar-se por scan pela assimetria da faixa rejeitada). Aplicar o modelo de cor só a píxeis que estão: (i) a menos de ~1,2 mm da fronteira externa do limiar; (ii) ligados ao fundo; (iii) num lado cuja normal exterior aponta para a sombra. Assim, uma zona verde no interior ou no lado iluminado de uma peça de relva nunca é removida.
2. **Usar o núcleo preto como marcador da aresta.** No lado da sombra, a aresta física é o lado interior da linha preta (L\* < 15). Cortar por essa linha resolve os restos pretos que o (c) deixa no laranja e no azul.
3. **Fundos acromáticos ficam fora do âmbito.** O verde ganhou e os brancos não servem (sombra cinzenta indistinguível de peças cinzentas).
4. Critério de aceitação inalterado: E-sym A2/B2 ≤ 0,5 mm, top-1 20/20 e rugosidade p95 B2 < 1,1, e no E-fundo o verde com o novo método pelo menos tão bom como (c) (pose diferente 0,44 mm; vs laranja 0,24 mm).

Até lá, o contorno de referência para medir forma continua a ser o **híbrido** (b): cumpre o M3, mas com a ressalva conhecida de incluir a sombra (viés dependente da pose, ≈ +0,1 mm em A2/B2).

## Limites

- **As peças de julho são claras (céu e nuvem), escolhidas pelo Tiago entre as difíceis de localizar.** Não testam relva escura sobre verde, que é o pior caso para o verde e para o (c). Esse caso só foi visto nos 20 gémeos B2.
- O recall de vermelho, preto e impressora inclui a taxa de emparelhamento por forma (peças mexidas). O recall de deteção (sem clusters) é 59, 59 e 61 / 61.
- **Impressora:** só 24/61 peças têm identidade. A sombra é cinzenta, larga e cai noutro lado (outro scanner), (a) morde as peças claras e (b)/(c) incluem a sombra (ver `fundo_impressora__contours.jpg`). O emparelhamento por forma falha porque o contorno é mau, não por serem outras peças: não é escala (testei ×0,97–1,03) nem espelho [V].
- azul_claro e bege saturam a branco no scanner (L\* = 100, C = 0). Nestes scans não se mede a cor do papel.
- O núcleo preto da sombra (≈ 20 % dos píxeis candidatos) não é tratado por nenhum dos métodos.

## Ficheiros

| Ficheiro | Conteúdo |
|---|---|
| `results.json` | Por fundo: dpi, tamanho, fundo Lab, contagens, identidade; por fundo × método: consistência (pose dif., mesma pose, não pálidos, vs verde), recall, rugosidade, corda, área; calibração da sombra; layout; ranking e sensibilidades; método vencedor (M3) |
| `fundo_matriz.png` | Fundos × métodos, RMS mediano: pose diferente, mesma pose, pose dif. com parceiros não pálidos, só contra o verde |
| `fundo_overlays_{seg,simples,sombra}.png` | As mesmas 6 peças nos 12 fundos, 2×, com os 3 contornos (traço grosso = método do ficheiro) |
| `fundo_sombra_mascara.png` | Píxeis rejeitados como sombra por (c) no verde, laranja e vermelho |
| `fundo_<cor>__contours.jpg` | Contornos do método vencedor (b) em cada fundo, ×0,5 |
