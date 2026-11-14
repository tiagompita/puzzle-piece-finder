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

## F1c (2026-11-14): gémeas sem vizinha montada no Montar

`python tools/gui/f1c_capturas.py --project <cópia> --out <dir>`, PNG a 1366×768 e a 390×844 (`device_scale_factor` 1), sobre uma **cópia** do estado atual de `projects/alpes` (log de 3086 eventos, igual ao do commit `596b7f6`). A fila tem as 3 gémeas `ambigua` sem vizinha montada, todas como «Guardar à parte» (saco 4 nº 22 → linha 38 · coluna 3; saco 7 nº 17 → 5 · 48; saco 8 nº 21 → 36 · 3), e 0 «coloca agora»; 32 grupos sem lugar.

- `F1c_guardar_*`: o cartão «Guardar à parte» (sem «Encaixa»), o alvo tracejado «lugar provável», «A seguir, para guardar à parte» e a linha «32 grupos sem lugar: ver na interface completa».
- `F1c_nao_*`: depois de «Não é esta» (desfeito a seguir, na cópia).
- `F1c_lupa_peca_*`: a lupa sobre «saco 4 nº 22»: a proposta da peça, com «Ver o cartão».
- `F1c_lupa_lugar_*`: a lupa sobre «38,3»: o lugar está vazio e tem a proposta da mesma peça.
- `F1c_vazio_*`: depois de «Guardei à parte» nas 3: o ecrã vazio diz «3 peças guardadas à parte» e «32 grupos sem lugar», com «Abrir a interface completa» (as 3 posições foram desfeitas a seguir pela API, na cópia). A 1366 vê-se também «A preparar mais sugestões… 0 de 1»: as sugestões pelo encaixe recalculam depois das escritas.
- `F1c_contagens.json`: a fila, `fora_da_fila`, e palavras e botões visíveis (topo + painel) no cartão e no vazio.

| | palavras (topo + painel) | botões visíveis |
|---|---|---|
| cartão «Guardar à parte», 1366 | 113 | 14 |
| cartão «Guardar à parte», 390 | 113 | 12 |
| vazio com contagens, 1366 / 390 | 58 | 9 |

## F1d (2026-11-14): correções do teste do Tiago

`python tools/gui/f1d_capturas.py --project <cópia> --out <dir>`, PNG a 1366×768 e a 390×844 (`device_scale_factor` 1), sobre uma **cópia** do estado atual de `projects/alpes` (log de 3092 eventos, com as alterações locais do Tiago: P0980, saco 4 nº 22, guardada à parte em 38 · 3). A fila tem 2 cartões sem vizinha montada (saco 7 nº 17 → 5 · 48; saco 8 nº 21 → 36 · 3), 0 «coloca agora»; 32 grupos sem lugar.

- `F1d_montar_*`: o cartão «Sem vizinha montada» com «Colocar aqui» / «Não pertence aqui», o «localizar» (só ícone) ao lado do lugar, e os ícones Lucide nas abas, botões e ligações.
- `F1d_menu_*`: o menu «⋯» aberto, com ícone e texto em cada entrada (a 390 abre a toda a largura).
- `F1d_colocar_*`: logo depois de «Colocar aqui»: a faixa «Saco 7 · nº 17 no lugar, por confirmar.» com «Desfazer» no topo do painel (fica até à ação seguinte) e, a 1366, também o aviso em baixo (a 390 o aviso não aparece: tapava «Colocar aqui»).
- `F1d_porconfirmar_*`: o tabuleiro aproximado a 5 · 48: a peça posta, ténue e com o contorno tracejado da própria peça.
- `F1d_vazio_*`: depois de «Colocar aqui» nas 2: «3 peças guardadas à parte, no tabuleiro «por confirmar» até uma vizinha encaixar.» e «32 grupos sem lugar»; no tabuleiro as 2 peças por confirmar da coluna 3 (36 e 38). O progresso continua «699 de 3008 peças». As 2 posições foram desfeitas a seguir pela API, na cópia.
- `F1d_contagens.json`: a fila, `fora_da_fila`, as peças por confirmar (com o contorno), e palavras e botões visíveis.

| | palavras (topo + painel) | botões visíveis |
|---|---|---|
| cartão sem vizinha montada, 1366 | 100 | 14 |
| cartão sem vizinha montada, 390 | 100 | 11 |
| menu «⋯» aberto (só o menu), 1366 / 390 | 30 | 15 / 12 |
| vazio com contagens, 1366 / 390 | 69 | 10 |

## F2 (2026-11-14): painel da peça e do lugar, pôr e tirar à mão, desfazer global, cor das peças

`python tools/gui/f2_capturas.py --project <cópia> --out <dir>`, PNG a 1366×768 e a 390×844 (`device_scale_factor` 1),
sobre uma **cópia** de `projects/alpes` (com as alterações locais do Tiago). O guião da borda (plano §5) corre até ao
passo 7 nas duas larguras; o que cada verificação disse está em `F2_guiao.json`.

- `F2_cartao_*`: o cartão «Ainda sem peças ao lado» (o título novo).
- `F2_marcado_*`: linha 1 · coluna 29 tocada: «Lugar marcado por ti», a arte da caixa, «Pôr a peça digitalizada aqui» e «Afinal está vazio».
- `F2_pormao1_*` / `F2_pormao1_folha_*`: «Pôr uma peça à mão», passo 1 (Saco 9 · nº 89 «está solta»; a grelha das soltas do saco).
- `F2_pormao2_averificar_*`: passo 2 com o pedido retido: as três linhas «a verificar…» e «Pôr aqui» já ativo.
- `F2_pormao2_falha_*`: a peça rodada 90°: lado liso e forma falham, imagem «não verificado», o aviso e «Pôr na mesma».
- `F2_pormao2_*`: na rotação certa (θ −171°): lado liso, forma e imagem com 3 traços; «Tem 3 peças montadas ao lado: fica no lugar.»
- `F2_peca_*`: depois de «Pôr aqui»: a faixa «Saco 9 · nº 89 no lugar.» com «Desfazer», o painel da peça (saco, nº, linha · coluna na borda de cima, «No lugar · posta por ti a 14 nov», a peça, a folha com a peça a âmbar, P1422 em pequeno, «Tirar do lugar», «Corrigir recorte», «Algo está errado»).
- `F2_tirar_*`: depois de «Tirar do lugar»: a faixa «… tirada do lugar.» e o lugar outra vez «marcado por ti» (não vazio).
- `F2_grupo_*` / `F2_errado_*`: uma peça de grupo («Veio do grupo (N peças)», «Tirar o grupo inteiro do lugar (N peças)») e «Algo está errado» aberto.
- `F2_porconfirmar_*`: uma peça «por confirmar» («Por confirmar · ainda sem peças ao lado»).
- `F2_vazio_*` / `F2_vazio_sugestao_*`: um lugar vazio sem sugestão (11 · 3) e com a sugestão do cartão atual (5 · 48, tocado duas vezes).
- `F2_definicoes_*`: «⋯ › Definições (cor das peças)» com os dois controlos e «Repor».
