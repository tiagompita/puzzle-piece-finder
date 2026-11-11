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

## Interface do board.js e prova estrutural da F1a (2026-11-11)

`python tools/gui/f1_estrutura.py extrair|comparar`: em vez de píxeis, o `outerHTML` do `svg#board` (todas as camadas, números a 4 casas) e o `getBoundingClientRect` de todos os elementos de `#board-wrap` e `#legend-wrap` (e, informativo, de toda a página), nos mesmos 4 estados e 2 viewports, sobre a mesma cópia de `projects/alpes`.

| Comparação | SVG das camadas | Elementos do tabuleiro (por estado) | Página |
|---|---|---|---|
| `d9c8165` ↔ `d9c8165` (ruído) | igual nos 8 | 184 / 185 / 184 / 261, 0 diferenças | 0 diferenças |
| `d9c8165` ↔ `8fedf87` (F1a) | igual nos 8 | 184 / 185 / 184 / 261, 0 diferenças | só os 2 `<script>` novos (`core.js`, `board.js`) |
| `8fedf87` ↔ F1b (`/` antiga) | igual nos 8 | 184 / 185 / 184 / 261, 0 diferenças | 0 diferenças |

## F1b (2026-11-11): casca nova e «Montar» em `/novo/`

`python tools/gui/f1b_capturas.py --project <cópia> --out <dir> --vazio <outra cópia>`, PNG a 1366×768 e a 390×844 (`device_scale_factor` 1). A cópia é o estado de `projects/alpes` no commit `8fedf87` (10 peças na fila, todas do saco 9), para haver cartões; o estado vazio é a cópia do working tree do Tiago de 2026-11-11 (fila vazia: as 3 gémeas não têm vizinha montada, as 2 `alta` estão em conflito).

- `F1b_antes_*`: a GUI antiga em `/`, aba «Vai buscar» (as mesmas 10 peças).
- `F1b_montar_*`: o cartão «Próxima peça».
- `F1b_porque_*`: «Porquê esta peça?».
- `F1b_nao_*`: depois de «Não encaixa» (desfeito a seguir, na cópia).
- `F1b_vazio_*`: fila vazia.
- `F1b_contagens.json`: palavras e botões visíveis no ecrã principal (ESPEC §6).

| | palavras (topo + painel) | botões visíveis |
|---|---|---|
| antes, 1366 | 951 | 13 |
| depois, 1366 | 72 | 15 |
| antes, 390 | 949 | 15 |
| depois, 390 | 72 | 14 |

As palavras contam o texto do painel inteiro (também o que está abaixo da dobra). Os botões são os que estão à vista: no Montar são os 3 do zoom, as 3 abas, o «⋯», «Encaixa», «Não encaixa», as 2 ligações e as 3 linhas «A seguir».
