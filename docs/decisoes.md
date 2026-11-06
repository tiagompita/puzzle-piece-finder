# Decisões

Registo curto de decisões e hipóteses refutadas, com os números que as sustentam.

## 2026-11-05 — trim de 0,48 mm no desenho do tabuleiro: refutado

**Decisão:** o trim de `calibration.celula_silhueta.offset_mm` (0,48 mm) aplicado às silhuetas no desenho do tabuleiro e nas miniaturas fica fora. O código foi removido do working tree (nunca foi commitado; guardado no bundle `D:\DEKSTOP\ppf-branches-teste.bundle`).

**Evidência:** trim 0,48 mm refutado: piora 44 células, melhora 0; causa dos buracos é pose/recorte, não escala. Medido em `projects/alpes` (589 peças colocadas, `compose_board` a 120 px/célula, fundo magenta, buraco = fração da célula, inset 0,4 mm):

| variante | células com buraco > 5 % | > 10 % | média |
|---|---|---|---|
| sem trim (referência) | 131 | 39 | 0,0309 |
| trim 0,48 mm | 179 | 73 | 0,0464 |
| trim 0,24 mm | 137 | 45 | 0,0335 |
| sem trim + lado reto alinhado (208 peças de borda) | 132 | 38 | 0,0312 |
| trim 0,48 mm + lado reto alinhado | 183 | 74 | 0,0470 |

O trim expõe o fundo nos tabs/blanks porque a pose tem erro de cerca de 1 mm; alinhar a rotação do lado reto das peças de moldura não melhora nada. Rotação dos 588 colocados face a múltiplos de 90°: 363 com desvio > 1,5° (mediana 2,1°); nas 215 de borda a inclinação mediana do lado reto é 0,9°. Folgas entre vizinhas (917 junções): 23 com |folga| > 0,8 mm, mediana 0,19 mm.

**Pendente (não corrigido):** melhorar a pose/recorte; baseline acima.

## 2026-11-06 — verde na borda no tabuleiro: regra do papel escurecido também no `compose_board`, encaixes de papel tirados

**Decisão:** `BOARD_SHADOW = True`: o tabuleiro aplica a regra das miniaturas (`shadow_paper_mask`, 0,4 mm, RENDER §6.1), e a sangria mantém a silhueta limpa com a orla pintada da cor funda, para os buracos não mudarem. `PAPER_POCKETS = True`: as componentes da própria cor do papel (d < 15) que chegam à banda de 0,7 mm saem das miniaturas e do tabuleiro, com um limite de 10 % da peça. Nada muda no índice, em `clean_crop` nem em `render/clean/`.

**Evidência** (RENDER §7):
- **6 peças reportadas:** contorno desenhado com verde 10–53 % → 0,5–21 %.
- **Amostra de 100:** nenhuma piora; esverdeado −80 %.
- **Buracos:** 70/10 iguais com e sem a regra.
- **Encaixe de P0778:** 1694 → 0 píxeis da cor do papel.

**Falha registada [F]:** a porta do §6.1 falha em 7/100 (5 de relva, perda nos lados iluminados 1,55–1,84 % contra 1,5 %, vistas: só sai a orla; P0199 com 62 px; P0555, onde B tira 0,09 mm² de papel do interior).

**Pendente:** as meias-luas a 0,4–0,8 mm dentro dos encaixes (alargar a faixa é outra decisão) e o prado de P0198 com a cor do papel (o «comido» do R0019, [NT]).
