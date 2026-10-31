# Canto inferior direito (BD) — scans de 31-out-2026, 300 dpi, papel verde

## Coordenadas

O Tiago usa coordenadas locais (k, j):
- k = linha contada **de baixo para cima** (k = 1 é a borda de baixo);
- j = coluna contada **da direita para a esquerda** (j = 1 é a borda da direita).

Conversão para coordenadas globais (l, c), com a grelha 64 × 47: **l = 48 − k, c = 65 − j**.

**Gémeo:** o gémeo de BD(k, j) é a peça global **(k, j)**, ou seja, a peça na linha k a contar de cima e na coluna j a contar da esquerda, no canto superior esquerdo. Exemplo: a peça (3, 4) do canto BD tem como gémea a peça (3, 4) do canto superior esquerdo. É por isso que se usam os mesmos índices locais, contados a partir do canto oposto.

**Peças em falta** (não estão no bloco nem nas soltas): (6,6), (6,7), (7,2), (7,3), (7,4), (7,5), (7,6), (7,7). Em coordenadas globais: (42,59), (42,58) e (41,58–63).

## Ficheiros

| Ficheiro | Conteúdo |
|---|---|
| `gt_canto_BD_frente_300dpi.jpg` | O bloco montado, pela frente, com o canto em baixo à direita na imagem (orientação direita). Inclui as linhas k = 1–6 (sem as peças em falta) e a peça (7,1). |
| `gt_canto_BD_frente_300dpi_rot180.jpg` | O mesmo bloco rodado 180°: re-scan com mudança de pose, útil para medir o ruído das linhas de corte. |
| `gt_canto_BD_soltas_300dpi.jpg` | As 28 peças interiores soltas, em "vista explodida": cada peça foi afastada sem rodar. A borda em L continua montada. |

## Disposição do scan das soltas

A disposição é o bloco **rodado 90° no sentido anti-horário**. Isto é inferido e bate com o que se vê na imagem.
- A faixa de cima é a borda da direita (j = 1). O canto fica em cima à direita e a peça escura (7,1) na ponta esquerda.
- A faixa da direita é a borda de baixo (k = 1).
- Na grelha das soltas:
  - a fila r do scan (1–6, de cima para baixo) corresponde a **j = r + 1**;
  - a coluna s do scan (1–5, da direita para a esquerda) corresponde a **k = s + 1**.
- As filas 5 e 6 do scan têm só 4 peças, porque faltam (6,6) e (6,7), as mais à esquerda.

**Verificado no Project:** com o limiar simples, a segmentação dá 28 peças soltas (áreas de 320 a 476 mm²) mais a faixa em L como um só objeto.
