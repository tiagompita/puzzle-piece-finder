# Legado digitalizado: onde está cada página (2026-11-01)

Ponto 2 da revisão. Código: `src/legacy.py` (análise de uma página, consistência entre páginas, ingestão no projeto), `tools/diagnostico/legado/run_legado.py` (reprodução, figuras, `legado_resultados.json`), `tests/test_legacy.py` (sintético). Dados: `images/pieces/legado/` (15 páginas `montado`, 3 `blocos`, 300 dpi, papel verde). Etiquetas: **[V]** verificado (com evidência), **[NT]** não testado, **[F]** testado e falha.

## Resumo

- **Montado: 538 peças em componentes `alta`, 57 `ambígua`, 44 numa página duplicada** **[V, `legado_resultados.json`]**. 38 componentes `alta`; as perguntas para o Tiago estão no fim.
- **GT automática (forma + cor contra E-sym A1/B2, BE e BD): 71/74 peças verificáveis na célula certa; 71/71 nas `alta`**; os 3 erros estão todos em componentes `ambígua` (nenhuma veto da GT foi preciso) **[V]**. Sem a consistência entre páginas (só imagem + lados F): 49/77 **[V]**.
- **`montado_p13` é a `montado_p04` digitalizada outra vez** (as mesmas 44 peças, mesma disposição) **[V: 38 pares mesma-peça com ΔE ≤ 10 entre as duas páginas, e visto nas figuras]**. O total do README (633) conta-a duas vezes: peças montadas únicas ≈ 595 (538 + 57), contra 581 cheias + 56 incertas no M14.
- **As páginas não são todas blocos 2D na orientação do tabuleiro** **[V]**: p01 é a borda direita (coluna 64) dobrada em colunas da página + a fila de baixo da página = filas 1–6 dessa borda rodadas; p12 é a borda esquerda (coluna 1) dobrada; p02 tem 3 sub-blocos lado a lado; as páginas do céu de cima estão rodadas 90° (o lado F à esquerda na página é o N do puzzle) e as da relva de baixo 270° (F à esquerda = S). A hipótese "orientação preservada" é **[F]** para a maioria; p07 tem 9 lados F (à esquerda na página = fila 47), não 0 **[F]**.
- **Gémeas entre páginas: 196 pares** (silhueta↔silhueta); na solução final, 180 de 193 com as duas peças colocadas caem na célula gémea, e **os 180 também na rotação gémea** (desvio ≤ ~2°): a convenção de rotação está certa **[V]**.
- **Blocos: 21 grupos com ≥ 2 peças + 11 peças isoladas, todos `ambígua`** (arte de rocha/creme, 25 px por célula, sem gémeas no legado) **[NT: não há GT dos blocos]**.

## Método (curto)

Por página (`legacy.analyse_page`): `segment_scan` (300 dpi, `normalize_rotation=False`), fragmentos < 150 mm² rejeitados, `objeto_duplo` se `is_cluster` ou área > 1,6 × mediana (uma tentativa de separação com `segment_pieces`); `shape.analyse`; rotação da página = média circular 4-fold dos ângulos do corpo; cada lado é N/E/S/W pela normal (±25°).

**Grelha local por arestas, não por filas (desvio ao plano).** Arestas candidatas entre vizinhas na página (à direita ou abaixo, 0,6–2,0 células ao longo, ≤ 0,7 célula de través), válidas só se os lados que se encaram são T↔B (F nunca, T–T/B–B nunca), `side_complement` RMS ≤ 1,6 mm e |ΔL| ≤ 2 mm; juntam-se da mais barata para a mais cara (Kruskal) em **componentes** com células locais (r, c), recusando a junção que ponha duas peças na mesma célula ou que deixe os lados F de uma direção fora da mesma fila/coluna extrema. Motivo: p01/p12 são tiras dobradas e p02 tem sub-blocos, onde a programação dinâmica por filas do plano junta peças que não são vizinhas. Num bloco 2D dá o mesmo que a PD (incluindo filas deslocadas meia célula, teste sintético). A unidade passa a ser o componente (uma `Section` por componente).

Registo (por componente): `locate.locate_group` (4 rotações, espelho só como verificação, regras F duras, prior M14), top-40.

Entre páginas (`legacy.solve_pages`): (1) página duplicada posta de parte; (2) gémeas silhueta↔silhueta (classe + `chord_pass` + free ≤ t95 0,507 mm + NN mútuo); (3) candidatas = top-40 da imagem + colocações implicadas pelas gémeas das candidatas das parceiras; (4) energia = ΔE da imagem − 3·(pares satisfeitos − violados) + 2·(células partilhadas por dois componentes) + 2·(peças em células que o M14 diz vazias; nos `blocos`, cheias); minimizada movendo um componente **com os componentes presos a ele por ≥ 2 pares de gémeas** (as gémeas sozinhas não veem um deslocamento conjunto: se X anda +k colunas e a gémea Y −k, os pares continuam satisfeitos); (5) decisão por ordem de tamanho: `alta` se (margem da imagem ≥ 1,5 e ganho > 0) ou ganho ≥ 6 (= 2 pares), sem par violado nem célula partilhada com componentes já `alta`, espelho não melhor por ≥ 10 %, e GT (se houver) toda certa. Ganho = custo do movimento mais barato para uma colocação distinta (≥ 1 célula de distância, não 2: a p14 esteve a 1 coluna da certa).

GT automática (só para medir): cada peça GT casa com a peça da página da mesma classe, que passa nas cordas, com free ≤ t95 e NN mútuo; a cor decide se é a **mesma peça** (ΔE médio ≤ 10 → célula da GT) ou a **gémea** (ΔE > 10 → `profile.twin(célula)`).

## Tabela por página

Peças = objetos ≥ 150 mm² (entre parênteses o README; p12/p15 no README: 46/55 + 1 objeto duplo). Lados F por direção **na página**. "Maior comp." = componente com mais peças; margem = imagem; ganho = energia (ΔE); gémeas = pares satisfeitos/violados dessa colocação; GT = peças com GT na célula certa / verificáveis (a página toda).

| Página | peças (README) | componentes (tamanhos ≥ 2) | lados F (página) | maior comp.: top-1 (l0,c0) rot | margem | ganho | gémeas ✓/✗ | GT ✓/verif. | alta (peças) | ambígua (peças) |
|---|---|---|---|---|---|---|---|---|---|---|
| p01 | 43 (43) | 8 (9+7+7+6+5+4+3+2) | E:34, ES:1, S:5 | (14,62) 0° | 1.17 | 10.1 | 1/2 | 0/0 | 29 | 14 |
| p02 | 46 (46) | 7 (16+13+6+6+2+2) | W:27 | (1,45) 90° | 1.03 | 24.2 | 16/0 | 0/1 | 45 | 1 |
| p03 | 18 (18) | 11 (3+3+2+2+2) | W:7 | (1,36) 90° | 1.02 | 38.9 | 3/0 | 0/0 | 12 | 6 |
| p04 | 44 (44) | 4 (40+2) | W:9 | (1,28) 90° | 1.04 | 34.6 | 25/0 | 3/3 | 40 | 4 |
| p05 | 51 (50) | 3 (49) | ?:1, E:7, EN:1, N:5 | (42,64) 90° | 1.32 | 252.5 | 36/3 | 25/25 | 49 | 2 |
| p06 | 48 (48) | 8 (31+10+2) | ?:1, N:1, W:8 | (47,47) 270° | 0.99 | 34.6 | 31/0 | 6/7 | 41 | 7 |
| p07 | 36 (36) | 1 (36) | W:9 | (47,38) 270° | 0.88 | 34.6 | 28/1 | 6/6 | 36 | 0 |
| p08 | 37 (37) | 3 (33+2+2) | S:1, W:8 | (47,29) 270° | 0.93 | 38.9 | 10/1 | 0/0 | 33 | 4 |
| p09 | 34 (34) | 1 (34) | W:9 | (47,20) 270° | 0.87 | 24.2 | 22/0 | 0/0 | 34 | 0 |
| p10 | 39 (39) | 4 (35+2) | S:1, W:8 | (47,11) 270° | 0.92 | 37.2 | 10/0 | 0/0 | 37 | 2 |
| p11 | 38 (38) | 2 (34+4) | S:1, W:8 | (47,2) 270° | 0.86 | 39.1 | 9/0 | 5/5 | 38 | 0 |
| p12 | 48 (47) | 13 (7+7+7+5+5+4+3+2+2+2) | ?:1, NW:1, S:4, SW:2, W:39 | (13,1) 0° | 0.90 | 8.4 | 1/0 | 0/0 | 33 | 14 |
| p13 | 44 (44) | 1 (44) | W:9 | (1,28) 90° | – | – | – | – | 0 | 0 (duplicada de p04: 44) |
| p14 | 55 (55) | 1 (55) | W:9 | (1,19) 90° | 1.00 | 34.6 | 43/1 | 8/8 | 55 | 0 |
| p15 | 59 (56) | 4 (56) | E:1, W:9 | (1,10) 90° | 1.05 | 252.5 | 33/3 | 18/18 | 56 | 3 |
| blocos p01 | 28 (28) | 11 (5+4+4+3+2+2+2+2+2) | N:1 | (13,21) 180° | 1.01 | 0.3 | 0/0 | 0/0 | 0 | 28 |
| blocos p02 | 36 (36) | 12 (8+7+4+3+2+2+2+2+2+2) | N:1 | (18,22) 270° | 0.96 | 2.2 | 0/0 | 0/1 | 0 | 36 |
| blocos p03 | 11 (11) | 9 (2+2) | – | (16,59) 270° | 1.01 | 0.2 | 0/0 | 0/0 | 0 | 11 |

Leituras:
- **Contagens** **[V]**: 14 de 18 páginas batem certo com o README. p05 51 (README 50), p12 48 (47 = 46 + 1 duplo), p15 59 (56 = 55 + 1 duplo): vistas as figuras, os 59 de p15 são 59 peças distintas; nenhum objeto tem área > 1,6 × mediana (máximo 1,23×) nem `is_cluster` em nenhuma página, por isso **os 2 objetos duplos do README não foram encontrados** (se existiram, o `segment_scan` separou-os) **[NT]**. 1 fragmento rejeitado (blocos p01, 117 mm²).
- **A margem da imagem sozinha quase nunca chega** (≤ 1,32 nos componentes grandes; céu e relva uniformes, arte a ≈ 25 px por célula) **[V]**. O que decide são as gémeas, as células partilhadas, os lados F e o M14: o ganho dos componentes grandes é 24–252 ΔE.
- Banda de cima (filas 1–7): p15 colunas 2–10, p14 11–19, p04 20–28, (1,29) vazia, p03 30–36, p02 37–63, p01 (filas 1–6 da coluna 64); banda de baixo (filas 42–47): p11 2–9 (zona do canto BE), p10 11–18, p09 20–28, p08 29–36, p07 38–46, p06 47–54, p05 56–64 (canto BD); bordas: p12 = coluna 1, `alta` nas filas 1–30 e 46–47, `ambígua` 32–44; p01 = coluna 64, `alta` nas filas 1–6, 14–27 e 35–41, `ambígua` 6–12 e 33–34 (+ 5 peças sem colocação válida) **[V para p04, p05, p06, p07, p11, p14, p15 pela GT (71/72; a errada é um par `ambígua` da p06); NT para as outras]**. As colunas 10, 19, 37 e 55 da banda de baixo ficam entre páginas: a 10 é o grupo de 4 da p11 (`alta`), a 55 tem a peça GT (47,55) num par `ambígua` da p06, a 37 e a (47,19) estão por explicar (pares/isoladas `ambígua` da p08?) **[NT]**.
- Sem GT na página (p01, p03, p08, p09, p10, p12): a colocação só tem apoio de gémeas, lados F e M14 **[NT contra GT]**.

## Lados: primeira medição E-fit (barata)

`side_complement` (perfis normalizados, RMS em mm), **[V, `legado_resultados.json` → `lados`]**:

| conjunto | n | p10 | p50 | p90 | máx |
|---|---|---|---|---|---|
| adjacências verdadeiras do canto BE (GT; lados pela orientação conhecida do scan solto) | 30 (30 T↔B) | 0,85 | 1,09 | 1,35 | 1,58 |
| arestas aceites nas páginas | 821 | 0,85 | 1,10 | 1,39 | 1,60 |
| pares T–B aleatórios das páginas | 3000 | 0,99 | 1,71 | 2,70 | 5,2 |

- O limiar inicial de 0,6 mm do plano **[F]**: nenhuma adjacência verdadeira passa. Usado 1,6 mm (máximo verdadeiro 1,58); 43 % dos pares T–B aleatórios também passam, ou seja **quem separa vizinhas é o tipo (T↔B, F nunca), não o RMS** (os tipos são 30/30 T↔B nas adjacências BE com a orientação certa, e 12–19/30 nas outras três).
- Veredictos das 905 arestas candidatas: 821 aceites, 40 com F, 7 T–T/B–B, 33 RMS/ΔL, 2 sem lados, 2 "F incoerente".
- |ΔL| das adjacências verdadeiras: mediana 0,34 mm, máx 1,07 mm.
- O RMS verdadeiro ≈ 1,1 mm é muito maior que o ruído de re-scan (0,27 mm): suspeita (não testada) de que é o viés da sombra no contorno (tab inchado, blank encolhido) e o desalinhamento dos cantos; é trabalho do E-fit, não deste commit **[NT]**.

## Gémeas entre páginas

196 pares (depois de tirar a p13). Por pares de páginas: p06↔p14 41, p05↔p15 34, p01↔p12 29, p04↔p07 26, p02↔p09 22, p02↔p10 12, p03↔p08 11, p02↔p11 10, p05↔p12 3, p07↔p14 3, blocos p02↔p05 3, p06↔p15 2. Na solução final: 193 com as duas peças colocadas, 180 na célula gémea e na rotação gémea, 13 violados, todos com pelo menos um componente `ambígua` (por construção: um conflito com um componente já `alta` impede o `alta`) **[V]**. Os 3 pares blocos p02↔p05 põem peças creme/rocha nas filas 2–6 do céu azul: **provavelmente falsos positivos de forma** **[NT]**.

Distribuição de d (free, mm) nos casamentos GT↔página **[V]**: mesma peça p50 0,38 / p90 0,47 (ΔE p50 2,6, máx 8,7); gémea p50 0,44 / p90 0,50 (ΔE p50 50, p5 26). O corte de cor ΔE 10 separa os dois com folga.

## GT por conjunto

74 peças das páginas com GT (A1 28, B2 22, BE 6, BD 37 casamentos; algumas peças casam com A1 e com a gémea B2 ao mesmo tempo e dão a mesma célula). Certas: p05 25/25, p15 18/18, p14 8/8, p07 6/6, p11 5/5, p04 3/3, p06 6/7, p02 0/1, blocos p02 0/1. Erradas (todas `ambígua`): p06 #7 (verdade (47,55), top-1 (47,48)), p02 #10 (verdade (2,61): é a peça que o E-real-2 colocou em 31-out; top-1 (43,56), peça isolada), blocos p02 #11 (verdade por gémea (4,3), top-1 (15,44)) **[V]**.

## Blocos

Os grupos **não** saem da proximidade: a distância mínima contorno-a-contorno à vizinha mais próxima vai de 2,2 a 10,1 mm sem patamar (p01: 3 mm → 27 grupos, 10 mm → 13, 20 mm → 5) **[V]**; a pista "1–2 mm dentro do grupo, ≥ 10 mm entre grupos" **[F]**. Os grupos saem das arestas (mesmos critérios das páginas montado): p01 9 grupos (5, 4, 4, 3, 2×5) + 2 isoladas, p02 10 grupos (8, 7, 4, 3, 2×6) + 2 isoladas, p03 2 pares + 7 isoladas. Em `blocos_p02_grupos.jpg` os grupos coincidem com os que se veem a olho (pares 1–2, 6–7, 11–12, 16–17, 13–14; 2×2 3-4-8-9; coluna 5-10-15-19-20-24-29; bloco 21…35) **[V, figura vista]**; nos blocos p01/p03 **[NT]**. Colocação: top-3 de cada grupo nas filas 8–18 (zona das Odle, rocha creme) e margens 0,8–1,2 — **nenhuma decisão**; top-3 completos em `legado_resultados.json` **[NT]**.

## Comparação com o M14 (componentes `alta`)

538 células com peça `alta`; **0 dessas estão vazias no M14** (o M14 entrou na energia, por isso isto não é independente), **13 estão incertas (−1)** no M14 — (3,30), (42,49), (42,52), (42,53), (42,57), (43,42), (43,47), (43,52), (44,23), (44,27), (44,41), (45,6), (45,41) —, todas fora da borda e sem as 4 vizinhas cheias nas duas fotos: leitura "provavelmente colocada depois da foto" ou incerta na foto **[NT]**. **57 células cheias no M14 sem peça `alta`**: 30 estão no top-1 de componentes `ambígua` (coluna 64 filas 7–12, coluna 1 filas 32–44, (42–47, 55)…); as outras 27 ((2,31), (2,32), (2,61), (3,10), (5,20), (5,22), (6,20), (6,22), (7,2), (13,64), (28–32,64), (31,1), (45,1), (42,54–56), (43–47,55), (44–47,37), (47,19)…) ficam por explicar: peças isoladas `ambígua`, o componente de p01 sem colocação válida, ou peças que não estão em nenhuma página **[NT]**. Figura: `tabuleiro_legado.jpg` (verde `alta`, laranja `ambígua` top-1, ponto vermelho = cheia no M14 sem `alta`).

## Figuras vistas (skill cv-visual-verification)

- `tabuleiro_legado.jpg`: banda de cima (filas 1–7) e de baixo (41–47) quase toda verde, bordas esquerda/direita verdes até ≈ fila 30, laranja nas filas 32–44 da coluna 1 e 6–12 da coluna 64, pontos vermelhos na coluna 64 filas 28–34 (as 5 peças de p01 sem colocação válida + o par 33–34); o padrão bate com o M14 (cheias por fila 62, 48, 37 … 64, 64).
- `montado_p01_overlay.jpg`: as colunas 2, 3 e 5 da página são segmentos da coluna 64 (filas 14–20, 21–27, 35–41), a fila de baixo é (6..1, 64) com o canto (1,64) no fim; as 3 peças de cima com a diagonal creme/castanho caem em (14, 62–64), onde a crista da montanha cruza a borda direita na arte; a coluna creme da esquerda (filas 7–13 prováveis) ficou `ambígua`.
- `montado_p12_overlay.jpg`: coluna 1 dobrada em colunas da página (6–12, 13–19, 20–26 …), a fila azul de baixo = (1..5, 1) rodada; **#30 sem 4 cantos e #24 mordido**: relva clara contra o papel verde, o contorno corta a peça (defeito de segmentação, não corrigido aqui) **[V, visto]**.
- `montado_p15_overlay.jpg`: fila da página k = coluna 10 − k do puzzle, colunas da página = filas 1–7; 2 lados vermelhos (#44/#45: lados quase direitos) **[V]**.
- `montado_p07_overlay.jpg`: filas da página = colunas 38–46, colunas = filas 47–43; buracos em (45,40) e (44,40); dois pares de lados internos a vermelho (#16/#17, #22/#27, relva clara) **[V]**.
- `blocos_p02_grupos.jpg`: ver Blocos **[V]**.

## Perguntas para o Tiago (componentes `ambígua` com ≥ 2 peças; 21 peças isoladas em `legado_resultados.json`)

- p01 peças 7–37 (coluna creme, 7 peças): filas 6–12, 7–13 ou 8–14 da coluna 64? (a arte e a vizinha (1–6) apontam para 7–13).
- p01 peças 5–25 (5 peças, coluna 4 da página): nenhuma colocação respeita os lados F (provavelmente um lado mal classificado): em que filas da coluna 64?
- p01 peças 30–35: filas 33–34 ou 34–35 da coluna 64?
- p03 peças 11–14: fila 2, colunas 45–46?  p04 peças 43–44: filas 2–3, coluna 46?
- p06 peças 7–13: filas 46–47 da coluna 48, 55 ou 52? (GT: #7 é (47,55)).
- p08 peças 22–27: filas 45–46 da coluna 55, 48 ou 53?  p08 peças 32–37: filas 46–47 da coluna 48, 34 ou 24?
- p12 peças 5–41 (7): filas 35–41, 34–40 ou 36–42 da coluna 1?  p12 peças 28–39 (3): filas 32–34, 31–33 ou 33–35?  p12 peças 12–18: filas 43–44 ou 42–43 da coluna 1?
- Confirmar que a p13 é mesmo a p04 digitalizada duas vezes.

## Limites e o que NÃO foi verificado

- Só ≈ 12 % das peças `alta` têm GT (74 casamentos em 538): as páginas p01, p03, p08–p10, p12 só têm apoio de gémeas/F/M14 **[NT contra GT]**. A precisão 71/71 vale para o céu de cima, a relva de baixo e os cantos BD/BE.
- O M14 está na energia (2 ΔE por peça numa célula vazia no mapa): a comparação com o M14 não é independente.
- A decisão por ordem de tamanho perdoa a um componente grande os conflitos com componentes ainda não decididos (p05 e p15 têm 3 pares violados cada contra componentes `ambígua`).
- `ingest_page` ancora o que é `alta` **na própria página** (imagem + F); com todas as páginas, a solução cruzada discordou de 2 desses componentes (p12 comp 6 e 7: pares de gémeas violados → `ambígua`) e `solve_project_sections` não mexe em secções já ancoradas **[V, smoke test num projeto temporário]**. Ver a nota no docstring.
- Peças de relva clara mordidas pela segmentação no papel verde (p12 #24, #30; 3 peças sem 4 cantos no total): forma e lados pouco fiáveis nessas **[V, visto]**.
- Blocos: nenhuma GT, nenhuma decisão **[NT]**.
- Só OpenCV 4.11 (venv4); OpenCV 5.0 **[NT]**.

## Desvios ao plano

1. Grelha local por arestas validadas (Kruskal) em vez de PD por filas: páginas dobradas e com sub-blocos **[V]**.
2. `SIDE_RMS_MAX` 1,6 mm em vez de 0,6 (medido acima).
3. Margem sobre colocações a ≥ 1 célula (não 2): o erro típico no céu/relva uniforme é 1 coluna.
4. Consistência entre páginas por minimização de energia com movimentos conjuntos (gémeas presas) + células partilhadas + M14 por célula, em vez de "+1/−1 por par com páginas fixas": a versão "fixar e propagar" ficou presa em deslocamentos conjuntos (GT 36/77 → 52/74 → 71/74 com estas mudanças).
5. Espelho: comparado com a melhor colocação não-espelhada pela imagem e só "ganha" com ≥ 10 % (na relva uniforme o espelho "ganhava" por ruído).
6. Blocos agrupados pelos lados, não pela proximidade (pista do README falsa).
7. Página duplicada detetada e posta de parte (não previsto).

## Reprodução

```
set PPF_SCRATCH=...   (fora do repo)
python tools/diagnostico/legado/segcache_legado.py --jobs 8     # segmentação em cache ($PPF_SCRATCH/legado/*.npz), ~1 min
python tools/diagnostico/legado/run_legado.py                    # análise, GT, M14, figuras e JSON, ~3 min
python -m pytest tests/test_legacy.py -q                         # sintético, ~10 s
```

Ingestão num projeto: `python -m src.ingest images/pieces/legado/montado_p01_300dpi.jpg --montado p01` (uma por página, depois `legacy.solve_project_sections(project)`). Saídas: `legado_resultados.json` (células por página, top-3, razões, perguntas, GT, pares, M14), `montado_pNN_overlay.jpg`, `montado_pNN_zona.jpg`, `blocos_pNN_grupos.jpg`, `tabuleiro_legado.jpg` (versões grandes em `$PPF_SCRATCH/legado/fig`).

## Ingestão no projeto (2026-11-01)

`tools/diagnostico/legado/ingest_all.py` regenera `projects/alpes/` com a foto F0001, a GT (A1, B2, BE, BD), o lote 1, as 2 confirmações do E-real-2 e as 18 páginas (`auto_anchor=False`, depois `solve_project_sections`): 39 secções ancoradas = 540 peças (453 colocadas `legado_scan` + 87 que são as próprias peças GT, que prevalecem: `same_as`, 56 já pela forma + cor, 30 pela ancoragem e 1 por a GT P0043 estar só como posição conhecida (célula (45,6) incerta na foto) e a p11 a mostrar montada; 0 em desacordo), 30 secções `montado` e 32 `blocos` por ancorar, p13 inteira `same_as` da p04 (44/44) **[V]**. Comparação do tabuleiro final com o M14 (0 colocadas em células vazias na foto, 13 em incertas, 53 cheias sem peça: 24 em top-1 ambíguo + 29 sem explicação): [`M14_vs_scans.md`](M14_vs_scans.md).
