# Diagnóstico do motor de matching (`multi_scale_template_match`)

Data: 2026-10-29. Puzzle: Clementoni 3000 "The Alps" (grelha 64x47). Motor usado tal como está em `src/matching.py`
(sem alterações), `num_pieces=3000`, `use_texture=True`, `use_downscale=True`.
Scripts (fora do repo, scratchpad): `common.py`, `expA.py`, `expB.py`, `pairing.py`, `expC.py`, `analyze.py`.
Dados brutos por peça/crop: `results.json` (nesta pasta).

## Resumo

| Pergunta | Resposta curta |
|---|---|
| O motor consegue localizar uma peça quando as cores batem com a referência? (A) | Sim, na maioria: top-1 72 % (degradado), 90 % (limpo); top-5 82 % / 100 %. |
| O rótulo `high` é de confiança? (A) | Nos dados sintéticos sim: 28/28 `high` corretos (100 %). `ambiguous` está certo em 47 % (top-1). |
| E com peças reais digitalizadas? (B) | Não há evidência de que funcione: **0/61** concordâncias top-1 entre as duas referências (nem 0/4 com `high` em ambas); visualmente os crops previstos não se parecem com as peças. |
| Porquê (hipótese mais forte) | Desfasamento fotométrico: as peças digitalizadas têm L* mediano **86**, a arte tem L* mediano **50**; só **0,5 %** da arte tem L* >= 86. As peças pálidas amarelo-esverdeadas são atraídas para prados verde-oliva (17/61 caem no mesmo "atrator" na encosta esquerda). |
| O motor é estável entre fundos de digitalização? (C) | Parcialmente: 7/22 (32 %) top-1 no mesmo sítio (acaso ≈ 2 %), mas isso mede repetibilidade, não acerto. |

## Experiência A — teto do motor com auto-recortes sintéticos (verdade conhecida)

Configuração
- Arte detetada em `PuzzleOriginal.jpeg` (maior região não-branca): **bbox (x0,y0,x1,y1) = (306, 274, 7645, 5306)** -> 7339 x 5032 px
  (célula real da grelha ≈ 7339/64 = 115 px, 5032/47 = 107 px).
- Lado do crop = 127 px (sqrt(8064*6048/3000), o lado que o motor assume). Forma = máscara real aleatória de `scan_verde.npz`
  redimensionada para sqrt(w*h) = 127 px; fora da máscara preenchido com a média da peça; rotação aleatória k*90°.
- Degradação: blur gaussiano sigma 1,0 + desvio Lab uniforme ±6 L*, ±3 a*, ±3 b*. Sem degradação: 20 crops (teto).
- `piece_edges=None`. Correto = centro previsto a < 0,5 lado (63,5 px) do verdadeiro. "Céu" = centro no 40 % superior da arte.
- Tempo: média 9,1 s/crop (com outro processo a correr em paralelo; ver B para tempos sem concorrência).

| Conjunto | n | top-1 | top-5 (shortlist) | rotação certa | erro mediano | `high` | precisão `high` | `ambiguous` certo top-1 | `ambiguous` certo top-5 |
|---|---|---|---|---|---|---|---|---|---|
| Degradado (total) | 60 | 43 (72 %) | 49 (82 %) | 51 (85 %) | 0,07 lados | 28 | **28/28 (100 %)** | 15/32 (47 %) | 21/32 (66 %) |
| Degradado – céu | 27 | 19 (70 %) | 22 (81 %) | 24 (89 %) | 0,11 | 10 | 10/10 | 9/17 (53 %) | 12/17 (71 %) |
| Degradado – resto | 33 | 24 (73 %) | 27 (82 %) | 27 (82 %) | 0,04 | 18 | 18/18 | 6/15 (40 %) | 9/15 (60 %) |
| Limpo (total) | 20 | 18 (90 %) | 20 (100 %) | 19 (95 %) | 0,03 | 7 | 7/7 (100 %) | 11/13 (85 %) | 13/13 (100 %) |
| Limpo – céu | 7 | 6 | 7 | 7 | 0,03 | 1 | 1/1 | 5/6 | 6/6 |
| Limpo – resto | 13 | 12 | 13 | 12 | 0,03 | 6 | 6/6 | 6/7 | 7/7 |

Detalhe (degradado, n=60)
- Posição do crop correto na shortlist: rank 0 = 43, rank 1 = 2, rank 2 = 3, rank 4 = 1, ausente = 11.
- Porta de estrutura: peças com `piece_structure < 4` (27/60) acertam top-1 em 44 %; com `>= 4` acertam 94 % (31/33).
  Porta do gap: `gap >= 0,12` -> 78 % top-1 (40/51); `gap < 0,12` -> 33 % (3/9). A porta de estrutura discrimina mais que o gap.
- Erros (19): 8 são quase-acertos (1,1–2,9 lados, mesma zona); 11 são saltos longos (4–43 lados). 2 previsões caíram **fora da arte**
  (margem branca da caixa / para lá da borda direita), porque o motor procura na foto inteira da caixa.
- Céu vs resto: top-1 praticamente igual (70 % vs 73 %); o céu é mais vezes `ambiguous` (17/27 vs 15/33), ou seja a porta de
  estrutura está a fazer o seu trabalho e não a mascarar erros.

O que vi nas imagens (`A_montagem.png`): os `high` têm peça, crop previsto e crop verdadeiro visualmente idênticos (incluindo a
textura de tela impressa na caixa). Os erros são peças creme/bege lisas (céu junto ao sol), floresta escura quase uniforme
(#4) e uma peça escura (#1) que foi parar à margem branca. Em `A_referencia_anotada.png` os erros longos concentram-se no
céu amarelo à direita e na floresta escura; não há enviesamento evidente por zona fora disso.

## Experiência B — peças reais (`scan_verde`, 61 peças, 0 clusters) contra as duas referências

Homografia `1186441_1.jpg -> PuzzleOriginal.jpeg` (SIFT 8000 kp, ratio 0,75, RANSAC):

| keypoints limpa / orig | matches bons | inliers | erro reproj. médio / mediano / p95 (px na orig. 8064) |
|---|---|---|---|
| 8000 / 8001 | 3097 | **2597** | 4,45 / 4,34 / 8,49 |

A homografia é boa (≈ 0,04 lados de erro). Nota: `1186441_1.jpg` tem barras brancas em cima/baixo (≈ 40 px), por isso
também não é "arte que preenche a imagem" — o prior de borda e o `num_pieces->escala` contam com essas barras.

| Referência | `high` | `ambiguous` | tempo médio (mediano) por peça | lado da janela escolhida (mediana) |
|---|---|---|---|---|
| PuzzleOriginal.jpeg (8064x6048) | 10 | 51 | 8,6 s (8,2) | 122 px |
| 1186441_1.jpg (1600x1200) | 20 | 41 | 7,5 s (7,0) | 24 px |

Tempos medidos com A (e depois C) a correr em paralelo; as primeiras peças, quase sem concorrência, levaram 5,7–8,7 s (orig)
e 4,8–7,1 s (limpa).

Concordância (centro previsto na limpa, mapeado pela homografia, vs centro previsto na orig; limiar = 1 lado = 127 px):

| Métrica | Valor |
|---|---|
| Top-1 concordam (todas) | **0/61 (0 %)** |
| Top-1 concordam, `high` em ambas | **0/4** |
| Top-1 concordam, `high` em pelo menos uma | 0/26 |
| Alguma das 5 candidatas de cada lado concorda | 15/61 (25 %) (sem linha de base de acaso calculada para B) |
| Acaso (pares de peças diferentes, top-1) | 0,4 % |
| Distância mediana entre previsões | 13,8 lados |
| Mesma rotação nas duas refs | 27/61 (44 %) (acaso ≈ 25 %) |

A concordância é condição necessária, não suficiente, para acerto: duas refs podem concordar no sítio errado. Aqui nem a
condição necessária se verifica, logo **o `high` das peças reais não é fiável** (10 + 20 `high`, nenhum confirmado pela outra ref).

O que vi nas imagens (`B_montagem_10.png`, `B_montagem_todas_*.png`, `B_referencias_anotada.png`):
- As peças digitalizadas parecem muito claras/lavadas (creme, amarelo pálido, branco-esverdeado) com textura de tela; os crops
  previstos na orig são quase sempre prados verde-oliva ou floresta escura, e na limpa são zonas creme lisas do céu junto ao
  sol ou prados desfocados. Em nenhuma das 10 linhas da montagem curta eu diria que o crop previsto corresponde à peça.
- 17/61 previsões na orig caem num mesmo "atrator" (encosta iluminada à esquerda, ≈ (560, 2960) px); visível como o
  aglomerado de círculos vermelhos em `B_referencias_anotada.png`.
- Várias peças têm artefactos de segmentação visíveis: uma "bolha" branca saliente (#17/#37, uma saliência clara agarrada ao
  contorno), e uma orla escura/verde ao longo de alguns contornos (sombra do papel verde).

Medição de cor que explica o padrão (Lab, máscara erodida 9 px):

| Conjunto | L* mediano | a* mediano | b* mediano | croma mediano |
|---|---|---|---|---|
| Peças `scan_verde` (61) | 86,1 (p10 57,4 / p90 93,6) | −4,6 | +28,3 | 28,6 |
| Peças `scan_laranja` (61) | 86,6 | −3,5 | +28,7 | — |
| Peças `scan_preto` (55) | 87,0 | −4,2 | +28,5 | — |
| Arte em PuzzleOriginal (píxeis) | 50,2 (p10 15,7 / p90 80,8) | — | — | 22,1 |
| Arte em 1186441_1 (píxeis) | 49,0 (p10 16,5 / p90 83,1) | — | — | 30,4 |

- Só **0,5 %** dos blocos 32x32 da arte (orig) atingem o L* mediano das peças. Uma amostra de 61 peças com L* mediano 86 é
  incompatível com a arte, a menos que (a) a digitalização esteja sobre-exposta / com curva de tom diferente, ou (b) as 61 peças
  tenham sido escolhidas quase só do céu claro. As montagens mostram peças de floresta/prado também pálidas, o que favorece (a).
- O fundo da digitalização quase não muda a cor da peça (pares laranja−verde: ΔL* 0,1, Δa* 1,0, Δb* −0,1), por isso não é
  contaminação do fundo; é a resposta do scanner (ou da foto da caixa) que difere.
- O motor remove só o desvio médio de L por assinatura e mantém o croma absoluto. Isto compensa exposição constante, mas não
  compressão de contraste/gama: com L* comprimido no topo, o padrão espacial de luminância fica achatado, e o croma
  amarelo-esverdeado (a* −5, b* +28) é o que decide — e encaixa nos prados verde-oliva.

## Experiência C — estabilidade entre fundos (laranja vs verde)

Emparelhamento laranja->verde por área + Hu (4 primeiros, log) + média/desvio Lab dentro da máscara erodida:
61 peças, 56 vizinhos mútuos, **55 confiantes** (mútuo e razão 2.º/1.º >= 1,5), todos com alvos distintos. Em
`C_emparelhamento_verificacao.png` confirmei visualmente que os confiantes da amostra são a mesma peça (mesma forma e
manchas); os não-confiantes L12/L45/L54 estão errados, como esperado. (A ordem coincide L_i = V_i a partir do índice 5, ao
contrário do que se assumia.)

Por limite de tempo só corri **22 dos 55** pares (amostra a cada 2.º), contra PuzzleOriginal; as previsões verdes vêm de B.

| Métrica | Valor |
|---|---|
| Pares avaliados | 22 |
| Top-1 no mesmo sítio (< 1 lado) | 7/22 (32 %) — acaso ≈ 2,3 % |
| ... dos quais no "atrator" da encosta esquerda | 3/7 |
| Alguma candidata comum nas shortlists | 17/22 (77 %) — acaso ≈ 12 % |
| `high` em ambos | 0 |
| Mesmo rótulo de confiança | 14/22 (64 %) |
| Distribuição laranja | high 4, ambiguous 18 |
| Tempo médio (sozinho) | 8,2 s/peça |

Leitura: o motor é bastante repetível para a mesma peça física (muito acima do acaso), mas o rótulo `high` não é estável
(nenhum par `high`/`high`; 8/22 mudam de rótulo). Em `C_pares_montagem.png` os sítios onde laranja e verde concordam são,
outra vez, prados oliva que não se parecem com a peça — repetibilidade sem acerto.

## Imagens geradas

| Ficheiro | O que mostra |
|---|---|
| `A_montagem.png` | 12 casos sintéticos degradados: peça (rodada pela rotação prevista) / ref na posição prevista / ref na posição verdadeira; legenda com confiança, gap, estrutura, erro. |
| `A_referencia_anotada.png` | PuzzleOriginal a 25 %: bbox da arte (branco), linha dos 40 % (céu), centros verdadeiros (círculo verde) e previstos (ponto vermelho) ligados por linha (verde = acerto, vermelho = erro); "H" = `high`. |
| `B_referencias_anotada.png` | PuzzleOriginal a 25 %: previsão na orig (círculo vermelho, cheio = `high`) e previsão na limpa mapeada (quadrado azul, cheio = `high`), ligadas por linha; número = índice da peça em `scan_verde`. |
| `B_montagem_10.png` | 10 peças: peça rodada pela rotação da orig / crop previsto na orig / peça rodada pela rotação da limpa / crop previsto na limpa. |
| `B_montagem_todas_00/16/32/48.png` | O mesmo para as 61 peças (16 por imagem), para julgamento humano. |
| `C_emparelhamento_verificacao.png` | Pares laranja/verde (amostra + não-confiantes) para validar o emparelhamento. |
| `C_pares_montagem.png` | 14 pares: peça laranja / peça verde / crop previsto (laranja) / crop previsto (verde). |

## O que NÃO foi verificado

- **Acerto absoluto das peças reais.** Não há verdade de terreno para as peças digitalizadas; B e C só medem concordância e
  repetibilidade. A conclusão "não funciona com peças reais" assenta em 0 % de concordância + inspeção visual, não em erro medido.
- **Causa do desfasamento fotométrico.** Não confirmei se é sobre-exposição do scanner, gama, ou seleção das peças (só céu).
  Teste que falta: digitalizar um alvo de cor/cinzentos, ou uma peça de cor conhecida, ou normalizar o histograma (L* e croma)
  das peças para o da arte e voltar a correr B.
- A experiência A usa crops **da própria imagem de referência** (mesma textura de tela, mesma câmara): é um teto otimista. Não
  testei degradações de gama/contraste (que é exatamente o que B sugere), ruído de scanner, nem desfasamento de escala.
- O tamanho sintético (127 px de sqrt(w*h)) segue o pressuposto do motor; a peça real com abas na orig deve medir ≈ 1,4–1,5 x
  a célula (≈ 155–165 px), no limite superior da banda de escalas do motor (0,8–1,3). Não testei se a escala real é coberta. Na
  limpa (1600x1200) a pesquisa corre a ≈ 24 px por peça (célula da grelha ≈ 25 px; peça com abas ≈ 37 px), resolução baixa
  para a assinatura 4x4 — não isolei o efeito disso.
- O motor procura em toda a foto da caixa (margem branca e texto incluídos); o prior de borda assume arte = imagem, o que é falso
  para as duas referências (margem da caixa; barras brancas na limpa). Não medi o impacto (só 1 peça é `edge` em `scan_verde`).
- Experiência C só com 22 de 55 pares; `scan_preto` não foi usado para matching (só para estatística de cor).
- Não há linha de base de acaso para a concordância de shortlists em B (as candidatas da limpa não foram guardadas mapeadas).
- Tempos medidos com processos em paralelo (A, B, C partilharam CPU durante parte do tempo); valores indicativos.
- `use_texture=False` e `piece_edges` não foram comparados (não era o objetivo).
