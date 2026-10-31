# Fotos do tabuleiro (mapa de ocupação, M14)

| Ficheiro | Origem | Data | Dimensões | Notas |
|---|---|---|---|---|
| `mapa_2026-10-31_a.jpg` | iPhone 16 Pro (`IMG_3221.jpeg`) | 2026-10-31 | 8055 × 6041, EXIF orientation 1 | puzzle inteiro sobre o tapete de feltro Schmidt (branco-lavanda com linhas impressas), sem peças soltas, de cima |
| `mapa_2026-10-31_b.jpg` | iPhone 16 Pro (`IMG_3222.jpeg`) | 2026-10-31 | 8055 × 6041, EXIF orientation 1 | segunda foto do mesmo estado (enquadramento e exposição ligeiramente diferentes) |

Estado do tabuleiro nas duas fotos (verdade de terreno para `tools/diagnostico/ocupacao/ocupacao.py`):

- **Borda quase completa**: 217 das 218 células de borda estão cheias. **(1,29) está vazia nas duas fotos** (vê-se feltro entre dois blocos de céu da fila 1; `docs/diagnostico/ocupacao/ocupacao_a_celulas.jpg`) — a GT inicial dizia 218; **a confirmar fisicamente pelo Tiago**.
- **(2,61) cheia**: peça `f2p1 #4` do E-real-2 colocada em 2026-10-31 (gémea de BE(2,4) = global (46,4)).
- **(5,60) vazia**: a gémea de BE(5,5) tem a forma confirmada mas está guardada à parte (zona sem vizinhas montadas).
- **Canto inferior direito (BD)** vazias: (42,58), (42,59), (41,58)–(41,63) (`images/pieces/gt_canto_BD.md`).
- **Canto inferior esquerdo (BE)** vazias: (44,6), (44,7), (43,6), (43,7), (42,2)–(42,7), (41,2)–(41,7) (`images/pieces/gt_canto_BE.md`; l = 48 − k, c = j).
- Restantes células: sem GT; o mapa reporta a contagem. Iluminação com gradiente forte (canto superior esquerdo claro, inferior direito em sombra); dedos do fotógrafo no bordo inferior, fora do puzzle.

Limite: a foto dá **ocupação**, não forma — não substitui a digitalização solta da relva legada (§8.1 (i) de `docs/estado-e-plano.md`).
