# Capturas do redesenho da GUI

## F1a (2026-11-11): extrair o tabuleiro sem mudar comportamento

As capturas são da GUI antiga (`/`), sobre uma **cópia** de `projects/alpes`, com `python tools/gui/f1a_capturas.py capturar` a 1366×768 e a 390×844 (`device_scale_factor` 1).

Estados capturados, todos a passar pelo código que mudou de ficheiro:
- `inicio`: abertura.
- `celula`: toque no tabuleiro → gaveta da célula, pelo gancho `S.onBoardTap`.
- `zoom`: roda do rato + raster de detalhe.
- `sugestoes`: «Sugestões» ligado + toque numa célula sugerida → grupo aberto na Mesa.

Os toasts, a pílula do trabalho e o aviso do botão «Atividade» ficam escondidos, porque dependem de quando chegam as mensagens do servidor.

Ficheiros:
- `F1a_antes_*` e `F1a_depois_*`.
- A 1366 px estão em JPEG para caberem em 300 KB; a 390 px estão em PNG.
- A comparação foi feita sobre os PNG sem perdas (fora do git).

**Comparação píxel a píxel [V]** (`python tools/gui/f1a_capturas.py comparar`):

| | antes ↔ antes (2 corridas sem mudar código) | antes ↔ depois |
|---|---|---|
| `inicio_1366`, `celula_1366` | 19 411 píxeis diferentes (1,85 %), máx. 5 por canal | 12 536–23 517 (1,2–2,2 %), máx. 7 |
| `inicio_390`, `celula_390` | 3 201 (0,97 %), máx. 3 | 2 003–3 992 (0,6–1,2 %), máx. 5 |
| `zoom_*`, `sugestoes_*` | 0–10, máx. 1 | 0–10, máx. 1 |
| píxeis com diferença > 8 por canal | 0 em todos | **0 em todos** |

Leitura dos números:
- As diferenças pequenas ficam dentro do retângulo do raster do tabuleiro e aparecem também entre duas corridas sem mudar código. São ruído de descodificação ou reamostragem do JPEG do raster.
- O máximo antes ↔ depois (7) é um pouco maior do que o máximo medido entre as duas corridas «antes» (5). Não houve uma terceira corrida para medir melhor o ruído.
- Nenhum píxel difere mais do que 8 por canal.
