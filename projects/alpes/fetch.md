# Lista «ir buscar» — 2026-11-08T22:19:36

Projeto `alpes`; 1433 peças; por estado {'solta': 543, 'emparelhada': 8, 'posicao_conhecida': 0, 'colocada': 672, 'em_seccao': 205, 'descartada': 5}; tabuleiro 673 ocupadas / 3008.
p_twin_placed = 0.030 (len(pending_twins) / n_por_colocar = 71 / 2335).

| ordem | lote | nº no lote | id | célula | pose | origem | decisão | margem | ΔE | razões | encaixe |
|---:|---:|---:|---|---|---:|---|---|---:|---:|---|---|
| 1 | 9 | 10 | P1343 | (2,55) | -178° | gemeo | aceite | 3.63 | 4.0 | 205 candidatas; 0 sem 4 cantos; 159 de classe diferente (consulta BBBT); 40 falham as cordas; 6 passam; forma aceite: d1 0,305 mm <= t95 0,507, margem 3,63 >= 1,5; imagem consistente: ΔE 4,0 <= p90 50 (céu); encaixe com 4 vizinhas: custo 1,14 <= 2,67 (pose prevista) | ok 1,14 |
| 2 | 1 | 20 | P0113 | (4,50) | 86° | gemeo | aceite | 3.31 | 5.0 | 207 candidatas; 0 sem 4 cantos; 146 de classe diferente (consulta BTBT); 42 falham as cordas; 19 passam; forma aceite: d1 0,271 mm <= t95 0,507, margem 3,31 >= 1,5; imagem consistente: ΔE 5,0 <= p90 50 (céu) | — |
| 3 | 1 | 19 | P0112 | (4,49) | -93° | gemeo | aceite | 2.51 | 4.5 | 206 candidatas; 0 sem 4 cantos; 146 de classe diferente (consulta BTBT); 51 falham as cordas; 9 passam; forma aceite: d1 0,489 mm <= t95 0,507, margem 2,51 >= 1,5; imagem consistente: ΔE 4,5 <= p90 50 (céu) | — |
| 4 | 9 | 35 | P1368 | (3,61) | -180° | gemeo | ambigua | 2.05 | 11.8 | 208 candidatas; 0 sem 4 cantos; 146 de classe diferente (consulta BTBT); 58 falham as cordas; 4 passam; forma ambígua: d1 0,619 > t95 0,507; imagem consistente: ΔE 11,8 <= p90 50 (céu); encaixe com 3 vizinhas: custo 1,07 <= 2,67 (pose prevista) | ok 1,07 |
| 5 | 4 | 22 | P0980 | (13,13) | ? | par | proposto | 5.58 | — | par com P1113; células [[13, 13], [34, 16], [34, 15]] | — |
| 6 | 6 | 5 | P1113 | (35,52) | ? | par | proposto | 5.58 | — | par com P0980; células [[13, 13], [34, 16], [34, 15]] (de P0980; P1113 vai para a gémea) | — |
| 7 | 9 | 56 | P1389 | (12,10) | ? | par | proposto | 4.62 | — | par com P1425; células [[12, 10], [12, 8], [13, 7]] | — |
| 8 | 9 | 92 | P1425 | (36,55) | ? | par | proposto | 4.62 | — | par com P1389; células [[12, 10], [12, 8], [13, 7]] (de P1389; P1425 vai para a gémea) | — |
| 9 | 2 | 38 | P0181 | (36,57) | ? | par | proposto | 2.18 | — | par com P0968; células [[36, 57], [36, 55], [35, 53]] | — |
| 10 | 4 | 10 | P0968 | (12,8) | ? | par | proposto | 2.18 | — | par com P0181; células [[36, 57], [36, 55], [35, 53]] (de P0181; P0968 vai para a gémea) | — |
| 11 | 2 | 5 | P0148 | (35,52) | ? | par | proposto | 2.11 | — | par com P1030; células [[35, 52], [35, 53], [36, 55]] | — |
| 12 | 4 | 72 | P1030 | (13,13) | ? | par | proposto | 2.11 | — | par com P0148; células [[35, 52], [35, 53], [36, 55]] (de P0148; P1030 vai para a gémea) | — |
| 13 | — | — | G0071 | (17,35) | — | seccao | por_ancorar | 1.91 | — | 4 peças; top-3 [([17, 35], 90), ([15, 48], 90), ([15, 46], 90)] | — |
| 14 | — | — | G0088 | (17,29) | — | seccao | por_ancorar | 1.87 | — | 2 peças; top-3 [([17, 29], 90), ([15, 60], 90), ([18, 34], 90)] | — |
| 15 | — | — | G0096 | (2,63) | — | seccao | por_ancorar | 1.74 | — | 1 peças; top-3 [([2, 63], 0), ([2, 63], 90), ([2, 63], 180)] | — |
| 16 | — | — | G0095 | (2,63) | — | seccao | por_ancorar | 1.66 | — | 1 peças; top-3 [([2, 63], 0), ([42, 57], 90), ([42, 61], 90)] | — |
| 17 | — | — | G0085 | (17,31) | — | seccao | por_ancorar | 1.64 | — | 2 peças; top-3 [([17, 31], 90), ([17, 29], 90), ([15, 47], 90)] | — |
| 18 | — | — | G0080 | (17,25) | — | seccao | por_ancorar | 1.64 | — | 8 peças; top-3 [([17, 25], 270), ([15, 60], 270), ([16, 44], 270)] | — |
| 19 | — | — | G0086 | (17,30) | — | seccao | por_ancorar | 1.42 | — | 2 peças; top-3 [([17, 30], 90), ([17, 36], 90), ([17, 37], 90)] | — |
| 20 | — | — | G0073 | (17,36) | — | seccao | por_ancorar | 1.32 | — | 2 peças; top-3 [([17, 36], 90), ([17, 37], 90), ([14, 61], 90)] | — |
| 21 | — | — | G0089 | (17,38) | — | seccao | por_ancorar | 1.29 | — | 2 peças; top-3 [([17, 38], 270), ([13, 14], 0), ([13, 16], 90)] | — |
| 22 | — | — | G0084 | (14,61) | — | seccao | por_ancorar | 1.20 | — | 2 peças; top-3 [([14, 61], 90), ([14, 62], 90), ([15, 44], 90)] | — |
| 23 | — | — | G0079 | (24,1) | — | seccao | por_ancorar | 1.15 | — | 1 peças; top-3 [([24, 1], 270), ([33, 1], 270), ([32, 1], 270)] | — |
| 24 | — | — | G0099 | (10,10) | — | seccao | por_ancorar | 1.14 | — | 1 peças; top-3 [([10, 10], 90), ([10, 10], 0), ([8, 23], 0)] | — |
| 25 | — | — | G0091 | (16,48) | — | seccao | por_ancorar | 1.08 | — | 1 peças; top-3 [([16, 48], 270), ([16, 49], 270), ([16, 49], 180)] | — |
| 26 | — | — | G0090 | (3,64) | — | seccao | por_ancorar | 1.08 | — | 1 peças; top-3 [([3, 64], 90), ([14, 64], 90), ([28, 1], 270)] | — |
| 27 | — | — | G0092 | (19,34) | — | seccao | por_ancorar | 1.07 | — | 2 peças; top-3 [([19, 34], 270), ([16, 50], 180), ([16, 59], 270)] | — |
| 28 | — | — | G0074 | (10,8) | — | seccao | por_ancorar | 1.07 | — | 2 peças; top-3 [([10, 8], 0), ([11, 5], 0), ([2, 63], 180)] | — |
| 29 | — | — | G0100 | (8,23) | — | seccao | por_ancorar | 1.07 | — | 1 peças; top-3 [([8, 23], 0), ([8, 23], 270), ([9, 15], 0)] | — |
| 30 | — | — | G0076 | (15,45) | — | seccao | por_ancorar | 1.06 | — | 2 peças; top-3 [([15, 45], 90), ([15, 46], 90), ([15, 44], 90)] | — |
| 31 | — | — | G0087 | (19,24) | — | seccao | por_ancorar | 1.06 | — | 2 peças; top-3 [([19, 24], 270), ([18, 34], 90), ([15, 61], 0)] | — |
| 32 | — | — | G0093 | (15,63) | — | seccao | por_ancorar | 1.05 | — | 2 peças; top-3 [([15, 63], 180), ([15, 61], 90), ([15, 59], 270)] | — |
| 33 | — | — | G0078 | (35,58) | — | seccao | por_ancorar | 1.04 | — | 1 peças; top-3 [([35, 58], 180), ([46, 39], 0), ([35, 58], 0)] | — |
| 34 | — | — | G0094 | (42,59) | — | seccao | por_ancorar | 1.04 | — | 1 peças; top-3 [([42, 59], 0), ([42, 58], 90), ([42, 59], 270)] | — |
| 35 | — | — | G0097 | (16,57) | — | seccao | por_ancorar | 1.03 | — | 1 peças; top-3 [([16, 57], 0), ([16, 56], 0), ([16, 58], 0)] | — |
| 36 | — | — | G0069 | (13,20) | — | seccao | por_ancorar | 1.03 | — | 5 peças; top-3 [([13, 20], 180), ([13, 18], 180), ([8, 23], 180)] | — |
| 37 | — | — | G0033 | (34,64) | — | seccao | por_ancorar | 1.02 | — | 1 peças; top-3 [([34, 64], 270), ([37, 64], 270), ([46, 64], 270)] | — |
| 38 | — | — | G0081 | (14,16) | — | seccao | por_ancorar | 1.02 | — | 7 peças; top-3 [([14, 16], 90), ([14, 15], 90), ([14, 14], 90)] | — |
| 39 | — | — | G0070 | (8,14) | — | seccao | por_ancorar | 1.01 | — | 4 peças; top-3 [([8, 14], 0), ([8, 12], 0), ([8, 13], 0)] | — |
| 40 | — | — | G0072 | (10,37) | — | seccao | por_ancorar | 1.01 | — | 3 peças; top-3 [([10, 37], 90), ([9, 41], 90), ([11, 42], 180)] | — |
| 41 | — | — | G0098 | (42,59) | — | seccao | por_ancorar | 1.00 | — | 1 peças; top-3 [([42, 59], 180), ([42, 57], 180), ([42, 57], 90)] | — |
| 42 | — | — | G0082 | (29,55) | — | seccao | por_ancorar | 1.00 | — | 4 peças; top-3 [([29, 55], 0), ([33, 57], 0), ([36, 57], 0)] | — |
| 43 | — | — | G0083 | (16,56) | — | seccao | por_ancorar | 1.00 | — | 3 peças; top-3 [([16, 56], 270), ([16, 59], 270), ([20, 30], 270)] | — |
| 44 | — | — | G0049 | (44,37) | — | seccao | por_ancorar | 0.87 | — | 1 peças; top-3 [([44, 37], 180), ([45, 47], 180), ([28, 13], 0)] | — |

pose = rotação (graus, positiva no sentido dos ponteiros do relógio) que leva a peça, tal como está na folha do scan, à sua posição no tabuleiro; «?» = desconhecida (ver pose_reason em fetch.json).

encaixe = custo conjunto contra as vizinhas montadas (molde do buraco, pose prevista ou melhor das 4 rotações): «ok» <= T_abs, «incomp.» = lado impossível ou custo > T_abs (a decisão desce para ambígua); «—» = não testado (sem vizinha montada).

Ficam na memória: 539 soltas sem proposta.
