# M14 (protótipo): mapa de ocupação do tabuleiro a partir de uma foto de telemóvel

Script: `tools/diagnostico/ocupacao/ocupacao.py` (correr da raiz; cerca de 11 s por foto, 25 s as duas, com OpenCV 4.11).
Entradas: `images/board/mapa_2026-10-31_{a,b}.jpg` (iPhone 16 Pro, 8055 × 6041, ≈ 111 px por célula).
GT: `images/board/README.md` (218 de borda + (2,61) cheias; 25 vazias).
Números completos: `results.json` → chave `ocupacao`; log: `ocupacao_log.txt`.

Etiquetas: **[V]** verificado (com evidência), **[NT]** não testado, **[F]** testado e falha.

> **Limite registado:** a foto dá **ocupação, não forma**. Não substitui digitalizar soltas as peças de relva
> legadas (§8.1 (i) de `docs/estado-e-plano.md`).

## 1. Método

**Passo 1, moldura** (imagem a 2000 px de largura):
- A máscara "não feltro" é o ΔE ao feltro depois de dividir a imagem (RGB linear) por um fundo de feltro de máximo
  local (≈ 4 células). O polinómio de grau 2 na imagem toda **não serviu** para isto [F]: a luz da janela deixa o feltro
  do canto superior esquerdo fora do modelo, e a máscara juntava esse feltro ao exterior e à madeira.
- Por lado: a primeira transição feltro → peça vinda de fora, com ≥ 6 px de feltro antes e ≥ 14 px de peça depois.
  Isto deixa de fora a madeira para lá do tapete e o texto "3000" impresso no feltro.
- **Correção da sombra projetada.** Do lado de baixo, a sombra das peças (feltro escuro e neutro, 4 a 10 px) entrava
  na máscara e empurrava a reta de baixo ≈ 0,3 célula para fora no canto BD. Isto foi visto na imagem retificada:
  aparecia feltro e o "3000" por baixo da última fila. Agora cada ponto anda para dentro até à primeira série de píxeis
  cromáticos (no máximo 14 px). Deslocamento mediano: baixo 4 px, esquerda 2 a 3 px, cima e direita 0 px.
- Os pontos de cada lado são ajustados por RANSAC (tolerância 1,5 px) seguido de mínimos quadrados nos inliers. As 4
  retas dão os 4 cantos e uma homografia para a imagem canónica de 64 × 47 células.
- **Refinamento da grelha.** Na imagem retificada a 40 px por célula, a resposta black-hat 7×7 (linhas de corte escuras)
  é projetada só no anel de borda: filas 1 e 47 para as posições x, colunas 1 e 64 para as posições y. Em cada linha de
  corte procura-se o pico em ±0,3 célula. A correção linear (fase + passo), interpolada entre perfis opostos, só é
  aceite se baixar o RMS leave-one-out.

**Passo 2, classificação** (foto a 50 %, retificada a 55 px por célula, com 3 células de orla):
- Modelo local do feltro: polinómio 2-D em RGB linear, ajuste robusto a 2σ.
  - 1.ª passagem: **grau 2, só na orla exterior** (como pedido).
  - 2.ª passagem: **grau 4**, na orla mais as células interiores que a 1.ª passagem dá como feltro limpo (1270 sementes).
  - Motivo: com o grau 2 da orla, o feltro do interior fica até 2 vezes mais claro do que o modelo prevê (janela). O
    resíduo de L* nas sementes passa de p5/p50/p95 = −1,7 / **+7,0** / +13,8 para −3,2 / **+0,3** / +4,5 [V].
- A imagem é dividida pelo feltro: o feltro fica neutro e o gradiente de luz sai. Figura vista: o interior fica branco
  uniforme.
- Medidas por célula, na janela central de 60 % × 60 %:
  - mediana Lab menos a cor do feltro;
  - **dEs** = ΔE ao feltro contando só o escurecimento e a croma. As peças são sempre mais escuras ou mais saturadas
    que o feltro; feltro mais claro do que o modelo é resíduo de iluminação, não peça;
  - **ft** = fração de píxeis iguais ao feltro (|ΔL\*| < 8 e |a\*b\*| < 4);
  - ΔE_arte, depois de subtrair o desvio fotométrico global medido nas 218 células de borda.
- **Regra B (usada):**
  - vazia: dEs ≤ 6, ou ft ≥ 0,5 com dEs < 10 (metade da janela é feltro; uma aba vizinha cobre no máximo ≈ 1/3 dela);
  - cheia: dEs ≥ 10 e ft < 0,06, ou 6 < dEs < 10 com ft < 0,06 e ΔE_arte ≤ 15;
  - incerta (−1): todos os outros casos.
- **Regra A (enunciado):** d = ΔE_feltro − ΔE_arte comparado com ±MARGEM. Fica registada como [F] (secção 4).

## 2. Moldura e grelha

| foto | lado | inliers | RMS inliers | p90 de todos os pontos | curvatura (parábola) |
|---|---|---|---|---|---|
| a | cima | 72 % | 0,76 px = 0,027 cél. | 2,9 px | 0,027 cél. |
| a | direita | 55 % | 0,66 px = 0,024 | 6,3 px | 0,000 |
| a | baixo | 68 % | 0,66 px = 0,024 | 6,3 px | 0,026 |
| a | esquerda | 67 % | 0,81 px = 0,029 | 3,3 px | 0,009 |
| b | cima | 73 % | 0,70 px = 0,025 | 3,8 px | 0,033 |
| b | direita | 57 % | 0,70 px = 0,025 | 6,0 px | 0,017 |
| b | baixo | 66 % | 0,71 px = 0,026 | 5,5 px | 0,018 |
| b | esquerda | 69 % | 0,75 px = 0,027 | 3,4 px | 0,016 |

Os px desta tabela são da imagem a 2000 px (1 célula ≈ 27,5 px).

- [V] O resíduo às retas e a curvatura ficam **≤ 0,035 célula** nos dois casos, muito abaixo do limiar de 0,25. A
  correção polinomial por lado não foi precisa: não se mede distorção residual da lente a esta escala.
- O p90 de todos os pontos (3 a 6 px) vem dos outliers: sombra, peças ligeiramente desalinhadas e fiapos do feltro.
- Cantos na foto (px): a = (513, 538), (7572, 451), (7759, 5694), (365, 5618); b = (426, 529), (7445, 477),
  (7623, 5657), (270, 5617).

**Grelha** (desvio das linhas de corte à grelha uniforme da homografia, em px a 40 px por célula):

| foto | perfil | linhas medidas | RMS uniforme | mediana | RMS linear (leave-one-out) |
|---|---|---|---|---|---|
| a | fila 1 (x) | 57/63 | 6,7 | +5,5 | 3,4 |
| a | fila 47 (x) | 24/63 | 6,8 | +3,6 | 7,2 |
| a | coluna 1 (y) | 31/46 | 5,4 | +4,1 | 4,7 |
| a | coluna 64 (y) | 28/46 | 7,8 | −7,3 | 4,6 |
| b | fila 1 (x) | 51/63 | 7,0 | +6,2 | 3,5 |
| b | fila 47 (x) | 25/63 | 6,3 | +3,2 | 6,6 |
| b | coluna 1 (y) | 33/46 | 4,6 | +3,3 | 4,1 |
| b | coluna 64 (y) | 32/46 | 7,0 | −6,4 | 4,5 |

- [V] As linhas de corte reais desviam-se da grelha uniforme ≈ **0,15 a 0,17 célula RMS** (≈ 3 mm), com sinal
  sistemático:
  - na fila 1 os cortes estão ≈ +6 px (0,15 cél.) à direita;
  - na coluna 64 os cortes estão ≈ −7 px acima, e a última célula da direita mede ≈ 32 px em vez de 40. Visto ao zoom.
- Leitura [NT]: folgas acumuladas na borda montada (peças empurradas) mais a variação de tamanho entre as células do
  cortante. Não parece erro da moldura, porque as retas assentam nas arestas (figura).
- O refinamento linear baixa o RMS leave-one-out de 6,7 → 5,3 px (x) e 6,6 → 4,7 px (y) na foto a, e de 6,6 → 5,0 e
  5,8 → 4,3 na b. Foi aceite nos dois eixos das duas fotos.
- Efeito na GT [V]: quase nenhum. Com a grelha uniforme, a dá a mesma matriz e b tem mais 1 incerta ((42,58)). A
  janela central de 60 % absorve desvios de 0,17 célula.

## 3. Classificação contra a GT (244 células)

**GT tal como está no README** (regra B):

| foto | cheia→cheia | cheia→vazia | cheia→incerta | vazia→vazia | vazia→cheia | vazia→incerta | exatidão |
|---|---|---|---|---|---|---|---|
| a | 218 | **1** (1,29) | 0 | 24 | 0 | 1 (42,58) | 99,2 % |
| b | 217 | **1** (1,29) | 1 (1,34) | 25 | 0 | 0 | 99,2 % |
| fusão | 217 | 1 (1,29) | 1 (1,34) | 24 | 0 | 1 (42,58) | 98,8 % |

**A GT tem um erro.** A célula **(1,29) está vazia nas duas fotos**: o feltro vê-se em toda a largura da célula, entre
dois blocos da fila 1 (1.º mosaico de `ocupacao_a_celulas.jpg` e de `ocupacao_b_celulas.jpg`). Logo, a borda **não**
está completa. Por isso o script tem `GT_VISUAL = {(1,29): 0}` e reporta também a GT corrigida. **O Tiago tem de
confirmar fisicamente.**

**GT corrigida** ((1,29) vazia; regra B):

| foto | cheia→cheia | cheia→incerta | vazia→vazia | vazia→incerta | erros duros | exatidão |
|---|---|---|---|---|---|---|
| a | 218 | 0 | 25 | 1 (42,58) | 0 | **99,6 %** |
| b | 217 | 1 (1,34) | 26 | 0 | 0 | **99,6 %** |
| fusão | 217 | 1 | 25 | 1 | 0 | 99,2 % |

- [V] **Zero** cheia↔vazia trocadas. As únicas falhas são incertas:
  - **(42,58)** na foto a: a aba de (42,57) entra na janela e a grelha está ≈ 0,3 célula desviada naquele canto. Visto
    no mosaico e no recorte do canto BD. Na foto b sai vazia.
  - **(1,34)** na foto b: peça cheia, com 6,5 % de píxeis iguais ao feltro, mesmo acima de FT_MAX = 0,06.
- (5,60) sai vazia em a e b [V]; (2,61) sai cheia em a e b [V].
- As células do logótipo no centro e o texto impresso ("Panorama 1000", "1000", "500", o símbolo de peça impresso)
  saem **incertas**, nunca cheias (overlay e mosaico). As linhas finas tracejadas e pontilhadas saem vazias ou, nalgumas,
  incertas.

## 4. Regra A (ΔE_feltro − ΔE_arte, enunciado): [F]

- Exatidão na GT: 77,5 % (a) e 75,8 % (b); com a GT corrigida, 77,9 % e 76,2 %.
- Falha sobretudo na fila 1: 10 cheias dão vazia e 45 a 49 dão incerta.
- Diagnóstico [V]:
  - a fila de cima está sob reflexo especular da janela: as peças de céu ficam quase brancas (exemplos (1,32), (1,54),
    (1,55));
  - a fotometria varia com a posição, e o desvio global (−21 L\*, +3 a\*, −8 b\*, medido nas 218 de borda) não a
    corrige.
  - Assim, ΔE_arte fica grande em peças que estão lá. A arte serve, quando muito, de desempate na zona intermédia, e é
    assim que a regra B a usa.

## 5. Concordância a/b e contagens

- [V] Nas 3008 células, **15 discordâncias, todas cheia/vazia ↔ incerta**; **0** cheia ↔ vazia.
  - Lista: (1,34), (2,29), (2,58), (2,63), (3,30), (7,13), (10,32), (12,32), (27,58), (42,53), (42,58), (44,23),
    (44,27), (45,6), (45,41).
  - As de 42 a 45 são peças cheias de fronteira com o encaixe vazio da vizinha à vista: ft entre 0,06 e 0,085 (mosaico
    visto).

| | cheias | vazias | incertas |
|---|---|---|---|
| a | 587 | 2371 | 50 |
| b | 582 | 2379 | 47 |
| fusão (`ocupacao_2026-10-31.json`) | **581** | 2371 | 56 |

**Cheias por fila (fusão):**
- filas 1 a 6: 62, 48, 37, 28, 27, 22;
- filas 41 a 47: **2, 9, 23, 55, 61, 64, 64** (a: 2, 10, 23, 57, 63, 64, 64; b: 2, 9, 23, 55, 61, 64, 64);
- as filas 9 a 40 dão 2 a 4 (só a borda).

**Cheias por coluna (fusão):** colunas 1 a 3: 47, 14, 12; colunas 62 a 64: 8, 8, 47.

Para o protocolo da relva: as filas 46 e 47 estão completas. Na 45 faltam 3 células, na 44 faltam 9 (são incertas
ou vazias; lista em `ocupacao_2026-10-31.json`). A fila 41 só tem a borda.

## 6. Figuras vistas e o que se viu

- `ocupacao_{a,b}_moldura.jpg`: as 4 retas assentam nas arestas da borda. Os outliers (vermelho) estão na sombra do
  lado de baixo e da direita, na madeira e em fiapos. Antes da correção da sombra, o canto BD ficava abaixo da relva
  (ver Método).
- `ocupacao_{a,b}_retificada.jpg` (grelha refinada): a grelha bate com as peças a olho, a menos de ≈ 0,2 célula. O
  desvio sistemático da fila 1 e da coluna 64 vê-se ao zoom (secção 2).
- `ocupacao_{a,b}_overlay.jpg` e `ocupacao_2026-10-31_fusao_overlay.jpg`: todo o interior de feltro sai vermelho. Saem
  amarelos o logótipo, o texto impresso, algumas células com rugas na zona escura sob o bloco do céu (filas 7 a 13) e as
  células de fronteira com abas ou encaixes. A magenta só aparece em (42,58) na foto a.
- `ocupacao_{a,b}_celulas.jpg` (mosaico das células difíceis):
  - (1,29) mostra feltro;
  - (1,32), (1,54) e (1,55) são peças de céu com reflexo, cheias;
  - (24,58) é o símbolo de peça impresso, incerta;
  - as incertas das filas 7 a 13 são feltro com linhas impressas em zona escura.

## 7. Limites e o que NÃO está verificado

- **[NT]** Só duas fotos do mesmo estado e da mesma sessão. Outra luz, outro tapete ou peças soltas sobre o tapete não
  foram testados. O fundo de máximo local e as sementes supõem feltro claro e peças mais escuras.
- **[NT]** Fora das 244 células da GT, a classificação foi verificada só a olho nas figuras: não há GT das outras 2764.
  As 581 cheias e 56 incertas da fusão são contagens, não medições.
- **Limiares fixados à vista desta GT pequena:**
  - FT_MAX = 0,06: as cheias da GT ficam ≤ 0,04 e o texto impresso ≥ 0,08. A margem é estreita, e as cheias de fronteira
    com encaixe à vista caem em incerta.
  - DEF_EMPTY 6 e DEF_FULL 10: a GT corrigida tem as vazias ≤ 8,1 e as cheias ≥ 12,3.
  - Mexer-lhes pede números antes/depois.
- **Desvios ao enunciado:**
  - 2.ª passagem do feltro com grau 4 e sementes interiores, porque o grau 2 da orla deixa um resíduo de +7 L\*
    (mediana) [V];
  - distância ao feltro só com escurecimento e croma;
  - regra B no lugar da regra A, que falha [F].
- **Desvio da grelha.** O desvio de 0,15 a 0,17 célula em relação à grelha uniforme é real. Num canto (BD) chega a ≈ 0,3
  célula. A correção linear interpolada a partir do anel de borda **não sabe nada do interior** [NT].
- **(1,29)** pede confirmação física; o README deve ser atualizado se se confirmar.
- **Foto ≠ forma:** a foto não dá a silhueta, por isso não substitui o scanner (regra de produto).
