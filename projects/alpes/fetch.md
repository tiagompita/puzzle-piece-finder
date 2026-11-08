# Lista «ir buscar» — 2026-11-08T18:44:33

Projeto `alpes`; 1333 peças; por estado {'solta': 445, 'emparelhada': 6, 'posicao_conhecida': 0, 'colocada': 672, 'em_seccao': 205, 'descartada': 5}; tabuleiro 672 ocupadas / 3008.
p_twin_placed = 0.031 (len(pending_twins) / n_por_colocar = 72 / 2336).

| ordem | lote | nº no lote | id | célula | pose | origem | decisão | margem | ΔE | razões |
|---:|---:|---:|---|---|---:|---|---|---:|---:|---|
| 1 | 1 | 20 | P0113 | (4,50) | 86° | gemeo | aceite | 3.05 | 5.0 | 476 candidatas; 0 sem 4 cantos; 338 de classe diferente (consulta BTBT); 101 falham as cordas; 37 passam; forma aceite: d1 0,271 mm <= t95 0,507, margem 3,05 >= 1,5; theta_unknown: orientação da consulta desconhecida, melhor das 4 rotações; imagem consistente: ΔE 5,0 <= p90 50 (ceu) |
| 2 | 1 | 19 | P0112 | (4,49) | -93° | gemeo | aceite | 2.43 | 4.5 | 475 candidatas; 0 sem 4 cantos; 338 de classe diferente (consulta BTBT); 123 falham as cordas; 14 passam; forma aceite: d1 0,489 mm <= t95 0,507, margem 2,43 >= 1,5; theta_unknown: orientação da consulta desconhecida, melhor das 4 rotações; imagem consistente: ΔE 4,5 <= p90 50 (ceu) |
| 3 | 6 | 1 | P1109 | (33,4) | 94° | gemeo | aceite | 1.78 | 32.1 | 454 candidatas; 0 sem 4 cantos; 367 de classe diferente (consulta BBBT); 84 falham as cordas; 3 passam; forma aceite: d1 0,503 mm <= t95 0,507, margem 1,78 >= 1,5; theta_unknown: orientação da consulta desconhecida, melhor das 4 rotações; imagem consistente: ΔE 32,1 <= p90 50 (ceu) |
| 4 | 2 | 21 | P0164 | (33,3) | 91° | gemeo | ambigua | 2.31 | 33.6 | 460 candidatas; 0 sem 4 cantos; 452 de classe diferente (consulta TTTT); 5 falham as cordas; 3 passam; forma ambígua: d1 0,514 > t95 0,507; imagem consistente: ΔE 33,6 <= p90 50 (ceu) |
| 5 | 7 | 17 | P1200 | (5,48) | 173° | gemeo | ambigua | 1.71 | 9.3 | 474 candidatas; 0 sem 4 cantos; 360 de classe diferente (consulta BTTT); 104 falham as cordas; 10 passam; forma ambígua: d1 0,622 > t95 0,507; theta_unknown: orientação da consulta desconhecida, melhor das 4 rotações; imagem consistente: ΔE 9,3 <= p90 50 (ceu) |
| 6 | 4 | 22 | P0980 | (13,13) | ? | par | proposto | 5.58 | — | par com P1113; células [[13, 13], [34, 16], [34, 15]] |
| 7 | 6 | 5 | P1113 | (13,13) | ? | par | proposto | 5.58 | — | par com P0980; células [[13, 13], [34, 16], [34, 15]] |
| 8 | 2 | 38 | P0181 | (36,57) | ? | par | proposto | 2.18 | — | par com P0968; células [[36, 57], [36, 55], [35, 53]] |
| 9 | 4 | 10 | P0968 | (36,57) | ? | par | proposto | 2.18 | — | par com P0181; células [[36, 57], [36, 55], [35, 53]] |
| 10 | 2 | 5 | P0148 | (35,52) | ? | par | proposto | 2.11 | — | par com P1030; células [[35, 52], [35, 53], [36, 55]] |
| 11 | 4 | 72 | P1030 | (35,52) | ? | par | proposto | 2.11 | — | par com P0148; células [[35, 52], [35, 53], [36, 55]] |
| 12 | — | — | G0071 | (17,35) | — | seccao | por_ancorar | 1.91 | — | 4 peças; top-3 [([17, 35], 90), ([15, 48], 90), ([15, 46], 90)] |
| 13 | — | — | G0088 | (17,29) | — | seccao | por_ancorar | 1.87 | — | 2 peças; top-3 [([17, 29], 90), ([15, 60], 90), ([18, 34], 90)] |
| 14 | — | — | G0096 | (2,63) | — | seccao | por_ancorar | 1.74 | — | 1 peças; top-3 [([2, 63], 0), ([2, 63], 90), ([2, 63], 180)] |
| 15 | — | — | G0095 | (2,63) | — | seccao | por_ancorar | 1.66 | — | 1 peças; top-3 [([2, 63], 0), ([42, 57], 90), ([42, 61], 90)] |
| 16 | — | — | G0085 | (17,31) | — | seccao | por_ancorar | 1.64 | — | 2 peças; top-3 [([17, 31], 90), ([17, 29], 90), ([15, 47], 90)] |
| 17 | — | — | G0080 | (17,25) | — | seccao | por_ancorar | 1.64 | — | 8 peças; top-3 [([17, 25], 270), ([15, 60], 270), ([16, 44], 270)] |
| 18 | — | — | G0086 | (17,30) | — | seccao | por_ancorar | 1.42 | — | 2 peças; top-3 [([17, 30], 90), ([17, 36], 90), ([17, 37], 90)] |
| 19 | — | — | G0073 | (17,36) | — | seccao | por_ancorar | 1.32 | — | 2 peças; top-3 [([17, 36], 90), ([17, 37], 90), ([14, 61], 90)] |
| 20 | — | — | G0089 | (17,38) | — | seccao | por_ancorar | 1.29 | — | 2 peças; top-3 [([17, 38], 270), ([13, 14], 0), ([13, 16], 90)] |
| 21 | — | — | G0084 | (14,61) | — | seccao | por_ancorar | 1.20 | — | 2 peças; top-3 [([14, 61], 90), ([14, 62], 90), ([15, 44], 90)] |
| 22 | — | — | G0079 | (24,1) | — | seccao | por_ancorar | 1.15 | — | 1 peças; top-3 [([24, 1], 270), ([33, 1], 270), ([32, 1], 270)] |
| 23 | — | — | G0099 | (10,10) | — | seccao | por_ancorar | 1.14 | — | 1 peças; top-3 [([10, 10], 90), ([10, 10], 0), ([8, 23], 0)] |
| 24 | — | — | G0091 | (16,48) | — | seccao | por_ancorar | 1.08 | — | 1 peças; top-3 [([16, 48], 270), ([16, 49], 270), ([16, 49], 180)] |
| 25 | — | — | G0090 | (3,64) | — | seccao | por_ancorar | 1.08 | — | 1 peças; top-3 [([3, 64], 90), ([14, 64], 90), ([28, 1], 270)] |
| 26 | — | — | G0092 | (19,34) | — | seccao | por_ancorar | 1.07 | — | 2 peças; top-3 [([19, 34], 270), ([16, 50], 180), ([16, 59], 270)] |
| 27 | — | — | G0074 | (10,8) | — | seccao | por_ancorar | 1.07 | — | 2 peças; top-3 [([10, 8], 0), ([11, 5], 0), ([2, 63], 180)] |
| 28 | — | — | G0100 | (8,23) | — | seccao | por_ancorar | 1.07 | — | 1 peças; top-3 [([8, 23], 0), ([8, 23], 270), ([9, 15], 0)] |
| 29 | — | — | G0076 | (15,45) | — | seccao | por_ancorar | 1.06 | — | 2 peças; top-3 [([15, 45], 90), ([15, 46], 90), ([15, 44], 90)] |
| 30 | — | — | G0087 | (19,24) | — | seccao | por_ancorar | 1.06 | — | 2 peças; top-3 [([19, 24], 270), ([18, 34], 90), ([15, 61], 0)] |
| 31 | — | — | G0093 | (15,63) | — | seccao | por_ancorar | 1.05 | — | 2 peças; top-3 [([15, 63], 180), ([15, 61], 90), ([15, 59], 270)] |
| 32 | — | — | G0078 | (35,58) | — | seccao | por_ancorar | 1.04 | — | 1 peças; top-3 [([35, 58], 180), ([46, 39], 0), ([35, 58], 0)] |
| 33 | — | — | G0094 | (42,59) | — | seccao | por_ancorar | 1.04 | — | 1 peças; top-3 [([42, 59], 0), ([42, 58], 90), ([42, 59], 270)] |
| 34 | — | — | G0097 | (16,57) | — | seccao | por_ancorar | 1.03 | — | 1 peças; top-3 [([16, 57], 0), ([16, 56], 0), ([16, 58], 0)] |
| 35 | — | — | G0069 | (13,20) | — | seccao | por_ancorar | 1.03 | — | 5 peças; top-3 [([13, 20], 180), ([13, 18], 180), ([8, 23], 180)] |
| 36 | — | — | G0033 | (34,64) | — | seccao | por_ancorar | 1.02 | — | 1 peças; top-3 [([34, 64], 270), ([37, 64], 270), ([46, 64], 270)] |
| 37 | — | — | G0081 | (14,16) | — | seccao | por_ancorar | 1.02 | — | 7 peças; top-3 [([14, 16], 90), ([14, 15], 90), ([14, 14], 90)] |
| 38 | — | — | G0070 | (8,14) | — | seccao | por_ancorar | 1.01 | — | 4 peças; top-3 [([8, 14], 0), ([8, 12], 0), ([8, 13], 0)] |
| 39 | — | — | G0072 | (10,37) | — | seccao | por_ancorar | 1.01 | — | 3 peças; top-3 [([10, 37], 90), ([9, 41], 90), ([11, 42], 180)] |
| 40 | — | — | G0098 | (42,59) | — | seccao | por_ancorar | 1.00 | — | 1 peças; top-3 [([42, 59], 180), ([42, 57], 180), ([42, 57], 90)] |
| 41 | — | — | G0082 | (29,55) | — | seccao | por_ancorar | 1.00 | — | 4 peças; top-3 [([29, 55], 0), ([33, 57], 0), ([36, 57], 0)] |
| 42 | — | — | G0083 | (16,56) | — | seccao | por_ancorar | 1.00 | — | 3 peças; top-3 [([16, 56], 270), ([16, 59], 270), ([20, 30], 270)] |
| 43 | — | — | G0049 | (44,37) | — | seccao | por_ancorar | 0.87 | — | 1 peças; top-3 [([44, 37], 180), ([45, 47], 180), ([28, 13], 0)] |

pose = rotação (graus, positiva no sentido dos ponteiros do relógio) que leva a peça, tal como está na folha do scan, à sua posição no tabuleiro; «?» = desconhecida (ver pose_reason em fetch.json).

Ficam na memória: 440 soltas sem proposta.
- nota: 1 propostas suprimidas por candidata única (ver fetch.json → suprimidas)
