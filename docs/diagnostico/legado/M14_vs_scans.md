# M14 (foto) contra o tabuleiro dos scans — 2026-11-01

Estado final de `projects/alpes/` (regenerado por `tools/diagnostico/legado/ingest_all.py`) contra a foto F0001 (`docs/diagnostico/ocupacao/ocupacao_2026-10-31.json` + (1,29)=0, (1,34)=1 confirmadas pelo Tiago). Etiquetas: **[V]** verificado, **[NT]** não testado.

**Diferenças face ao LEGADO.md** (57 cheias sem peça `alta`: 30 em top-1 ambíguo + 27 sem explicação): (2,61) tem agora a peça confirmada P0147 (lote 1); as células das peças GT contam como colocadas; (5,20), (5,22), (6,20), (6,22) eram top-1 só da p13 (re-scan da p04, agora fora da solução) e passam a «sem explicação»; (45,6), incerta na foto, tem a peça GT P0043 (a p11 mostra-a montada) **[V]**.

**Não é independente:** o M14 entra na energia da solução conjunta do legado (2 ΔE por peça numa célula vazia no mapa).

| | células |
|---|---:|
| foto: cheias / vazias / incertas | 582 / 2371 / 55 |
| colocadas com silhueta (`legado_scan` 453 + GT 88 + confirmada 1) | 542 |
| colocadas que a foto tem **vazias** (0) | 0 |
| colocadas que a foto tem **incertas** (−1) | 13 |
| cheias na foto sem peça colocada | 53 |
| — no top-1 de uma secção `ambígua` por ancorar | 24 |
| — sem explicação | 29 |

## Colocadas sobre células incertas na foto (−1)

(3,30) P0300 montado_p03, (42,49) P0414 montado_p06, (42,52) P0431 montado_p06, (42,53) P0437 montado_p06, (42,57) P0385 montado_p05, (43,42) P0462 montado_p07, (43,47) P0400 montado_p06, (43,52) P0430 montado_p06, (44,23) P0531 montado_p09, (44,27) P0546 montado_p09, (44,41) P0457 montado_p07, (45,6) P0043 gt_canto_BE_soltas, (45,41) P0456 montado_p07 **[NT]**: 12 `legado_scan` + 1 GT ((45,6), P0043, que a p11 mostra montada), todas fora da borda; as mesmas 13 células do LEGADO.md (leitura provável: colocadas depois da foto ou incertas na foto).

## Cheias na foto sem peça colocada

No top-1 de secções ambíguas (por secção; a página entre parênteses):

- G0003 (montado_p01, 7 peças): (7,64), (8,64), (9,64), (10,64), (11,64), (12,64), (13,64)
- G0008 (montado_p01, 2 peças): (34,64)
- G0029 (montado_p04, 1 peça): (3,31)
- G0030 (montado_p04, 1 peça): (3,33)
- G0055 (montado_p12, 7 peças): (35,1), (36,1), (37,1), (38,1), (39,1), (40,1), (41,1)
- G0059 (montado_p12, 3 peças): (32,1), (33,1), (34,1)
- G0060 (montado_p12, 2 peças): (43,1), (44,1)
- G0063 (montado_p12, 1 peça): (42,1)
- G0070 (montado_p15, 1 peça): (8,2)

Sem explicação (29): (1,32), (2,31), (2,32), (3,10), (3,32), (5,20), (5,22), (6,20), (6,22), (7,2), (28,64), (29,64), (30,64), (31,1), (31,64), (32,64), (33,64), (42,54), (42,55), (42,56), (43,55), (44,37), (44,55), (45,1), (45,37), (45,55), (46,37), (47,19), (47,37) **[NT]**: peças isoladas `ambígua` cujo top-1 é outro, o componente de p01 sem colocação válida (coluna 64, filas 28–33), ou peças que não estão em nenhuma página.
