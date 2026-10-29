# Diagnóstico de forma: tamanho, topologia, duplicados e repetibilidade

Dados: peças segmentadas de digitalizações a 300 dpi (1 px = 0,08467 mm), lidas de `scratchpad/seg/*.npz`, sem registos `is_cluster`.
O conjunto principal é `scan_verde` (61 peças). Para repetibilidade usaram-se `scan_laranja`, `scan_azul`, `scan_preto`, `scan_bege` e `scan_vermelho`, que são as mesmas peças. O tamanho foi também medido nos conjuntos `_grupo2..5` e `vermelho_grupo5`.
Os scripts estão só no scratchpad (`.../scratchpad/forma/*.py`). Não houve alterações em `src/` nem em `tests/`. Os números completos estão em `results.json`.

## Método dos cantos (o passo frágil)

**Tentativa 1 (descartada): abertura morfológica.** Usei um disco de raio 3,5 mm e depois o `minAreaRect` do "corpo". Falha nesta coleção: as peças Clementoni têm encaixes fundos e o corpo entre dois encaixes fica estreito (cerca de 8 mm). A abertura destrói o corpo e dá "corpos" de 8 a 13 mm. Ver `falha_abertura_morfologica.png` (peça #14). Também falhou com o canto inicial no `minAreaRect` e ajuste ao contorno: os cantos iam parar ao pescoço das patilhas.

**Método final (usado em tudo):**
1. O contorno, em coordenadas originais, é reamostrado para 1200 pontos por comprimento de arco e orientado com área com sinal positiva. Depois é suavizado com uma gaussiana de σ = 2 amostras (cerca de 0,25 mm).
2. **Candidatos.** Para cada ponto mede-se o ângulo entre as cordas para os pontos a ±1,2 mm e a ±2,5 mm de arco. O custo é `|ang1−90| + |ang2−90|`, mais 1000 se o ponto não for convexo nas duas escalas. Aplica-se supressão de não-máximos numa janela de 2 mm e guardam-se até 20 candidatos com custo < 140. Uma cabeça de patilha (raio ≈ 3 mm) dá cerca de 150°/123° nas duas escalas, e um canto verdadeiro dá cerca de 90°/90°.
3. **Escolha do quadrilátero.** Testo todas as combinações de 4 candidatos em ordem no contorno. O quadrilátero tem de ser convexo e ter lados de corda entre 14 e 23 mm. Minimiza-se a soma de:
   - `Σ|ângulo−90|`;
   - `4·(|L0−L2|+|L1−L3|)` e `3·|A−B|`, em mm;
   - o desalinhamento (em graus) entre os braços do contorno, 2 mm para cada lado do canto, e as arestas do quadrilátero;
   - `0,3·custo dos candidatos`.
4. **Lados.** O contorno é cortado nos 4 cantos. Cada lado é transladado para a origem, rodado para que o canto final fique em +x e dividido pelo comprimento da corda. A seguir é reamostrado em 64 pontos e o sinal é escolhido de modo que "para fora" seja +y. Classificação: **T** se o máximo para fora for > 0,15, **B** se o máximo para dentro for > 0,15, **F** nos restantes casos.

**Verificação dos priors.** Os termos de prior de forma (`4·opp`, `3·|A−B|`) podiam enviesar o teste de tamanho. Repeti a escolha dos cantos sem eles: 276 de 278 peças ficam com os mesmos cantos.

**Inspeção visual de `montagem_cantos_scan_verde.png`:**
- Com o método final não vi cantos grosseiramente errados nas 61 peças. Os ângulos do quadrilátero dos cantos desviam-se de 90° em média 2,8° (p95 7,6°, máx. 11,4°).
- Os problemas que vi vêm da **segmentação**, não dos cantos: há contornos com "franjas" ou bocados comidos em #2, #6, #11, #18, #26, #27, #44, #47 e #52 (rugosidade > 1,14). Nas peças #6, #11 e #47 isso deixa lados com corda de 14 a 14,6 mm, que são provavelmente cantos deslocados pelo defeito.
- Na versão 1 (`minAreaRect` e abertura) as falhas eram massivas: cantos no pescoço das patilhas em cerca de 20 de 61 peças.

## 1. Tamanho

O "corpo" foi medido como a corda canto-a-canto de cada lado. A = média de L0 e L2, B = média de L1 e L3.

| scan_verde (n=61) | média | dp | mín | máx |
|---|---|---|---|---|
| todos os lados (n=244) | 18,06 | 1,07 | 14,09 | 20,67 |
| lado médio por peça | 18,06 | 0,56 | 16,97 | 19,29 |
| par maior, max(A,B) | 18,64 | 0,62 | 17,34 | 20,04 |
| par menor, min(A,B) | 17,48 | 0,79 | 15,32 | 18,96 |
| minAreaRect da máscara (com patilhas), maior × menor | 26,0 × 21,5 | | | |

O lado médio nos 11 scans vai de 17,69 mm (bege) a 18,14 mm. A diferença é viés da fronteira da segmentação: a área da mesma peça varia entre −5,4% e +1,6% de scan para scan. Conto por isso com uma incerteza absoluta de cerca de ±0,25 mm.

**Retangularidade.** Usei 278 peças distintas (verde e grupos 2 a 5), com cantos escolhidos sem prior:

| Indicador | Valor |
|---|---|
| Correlação dos desvios (Lᵢ − média da peça) entre lados **opostos** | **+0,20** (sob a hipótese "quadrado com ruído iid" esperar-se-ia −0,33; p99 do nulo por permutação = −0,22) |
| Correlação entre lados **adjacentes** | −0,60 |
| dp(A−B) | 1,37 mm (ruído esperado a partir de L0−L2 ≈ 0,79 mm) |
| Diferença sistemática estimada pelo método dos momentos | Δ ≈ 1,1 mm |
| Diferença sistemática estimada por mistura ±Δ | Δ ≈ 0,84 mm (ganho de log-verosimilhança de apenas 0,85, fraco) |
| Razão longo/curto | ≈ 1,05–1,06 |

Para comparação, a razão das células nominais por grelha é: 64×47 = 1,031; 64×48 = 1,053; 63×48 = 1,070.

**Conclusão:**
- O tamanho médio (18,0 ± 0,25 mm) é compatível com cerca de 3000 peças em 118,4 × 84,3 cm. O lado nominal médio para 64×47 é √(18,5·17,9) = 18,2 mm.
- As células **não são quadradas**: dois lados opostos partilham o comprimento, de forma muito significativa. A razão medida (cerca de 1,05) é um pouco maior do que 64×47 prevê (1,031). Não consigo distinguir 64×47 de 64×48 ou 63×48 com estes dados.
- **Não sei qual dos eixos é o horizontal** do puzzle (falta a orientação da imagem). Portanto "mais largas do que altas" fica por verificar.
- A precisão por lado é de cerca de 0,2 mm: a diferença do mesmo lado entre laranja e verde tem dp de 0,285 mm. A dispersão de cerca de 0,8 mm entre lados é sobretudo real, porque as linhas de corte são onduladas e os cantos não caem numa grelha perfeita.

## 2. Perfis de lado e topologia (scan_verde)

A classe é o tuplo cíclico, considerado igual a menos de rotação (sem espelho).

| Classe | BBBT | BTBT | BTTT | BBTT | BBBB | TTTT | BFTT | FTTT | BFBT |
|---|---|---|---|---|---|---|---|---|---|
| n | 18 | 13 | 11 | 10 | 3 | 3 | 1 | 1 | 1 |

- Tipos de lado: **B 126, T 115, F 3** (244 no total).
- O desvio máximo normalizado por lado é bimodal: 3 lados < 0,05, 1 lado em 0,15–0,20 e os restantes entre 0,20 e 0,46 (mediana 0,31). O limiar de 0,15 cai num vazio.
- **Peças com lado F: #42, #54 e #60.** O `edges.py` só marca #60 como `edge` e as outras 60 peças como `interior`. Na montagem, #42 e #54 têm de facto um lado longo perfeitamente reto, por isso o `edges.py` falha 2 de 3 peças de bordo neste scan.
- Entre scans a deteção de F **não é estável**:
  - laranja: #42, #54, #60, igual ao verde;
  - azul: só 1 peça;
  - preto: 6 peças, e aparece uma classe "FFFF", claramente espúria;
  - bege: 3 peças.
  
  Não inspecionei as montagens desses scans, por isso os F em preto e bege podem ser cantos mal colocados.
- Nos pares re-digitalizados emparelhados, a classe topológica coincide em 43/43 (laranja), 33/33 (azul), 28/28 (preto), 16/16 (bege) e 27/27 (vermelho).

## 3. Duplicados geométricos dentro do conjunto (scan_verde, 1830 pares)

**Métrica principal ("free").** Contorno suavizado, reamostrado a 512 pontos e centrado. Calcula-se o mínimo sobre todos os deslocamentos cíclicos e rotações (correlação circular complexa por FFT, validada por força bruta) do RMS ponto-a-ponto, em mm. Não depende dos cantos.

**Segunda métrica ("corner").** 4 lados × 64 pontos, 4 rotações cíclicas e Kabsch. Também calculei `cv2.matchShapes` (Hu I1).

| RMS de forma (mm) | mediana | p5 | mín | máx |
|---|---|---|---|---|
| vizinho mais próximo (NN), free | 1,21 | 0,99 | **0,85** | 2,57 |
| NN, corner | 1,24 | 0,77 | 0,74 | 1,80 |
| todos os pares | 3,08 | 1,52 | 0,85 | 5,09 |
| pares da mesma classe (n=337) | 1,84 | 1,16 | 0,85 | 3,78 |
| pares de classe diferente | 3,24 | 2,46 | 1,92 | 5,09 |

Os 8 pares mais parecidos (`t3_pares_mais_parecidos.png`): 38–39 (0,85), 38–43, 39–43, 31–43, 47–57, 31–38, 52–59 e 14–35. Todos são da mesma classe, quase todos BBBT. Na sobreposição as patilhas e os encaixes estão deslocados cerca de 0,5–1,5 mm ao longo do lado e as larguras diferem, ou seja, **é a mesma topologia mas não a mesma faca**.

O NN de Hu coincide com o NN "free" em apenas 10% das peças, e o NN "corner" em 44%. A distância de Hu é uma segunda opinião fraca.

**Perfis de lado (normalizados por L).**

| | n pares | mediana | p5 | mín |
|---|---|---|---|---|
| T–T | 6477 | 0,090 L | 0,039 L | 0,010 L |
| B–B | 7779 | 0,092 L | 0,040 L | 0,013 L |

Os pares T–T mais parecidos (`t3_perfis_TT_mais_parecidos.png`) mostram que a **forma** da patilha é quase sempre a mesma "cabeça redonda com pescoço". As diferenças estão na posição ao longo do lado, na altura e na largura. Um lado isolado é pouco discriminante.

**Resposta.** Nesta amostra de 61 peças não reaparece nenhuma forma idêntica: o par mais próximo (0,85 mm) fica acima de 78% das distâncias de re-digitalização da própria peça (laranja, ver 4). Duas peças da mesma classe diferem tipicamente em 1,8 mm RMS (mínimo 0,85). Peças de classes diferentes nunca ficam abaixo de 1,9 mm.

## 4. Repetibilidade entre scans (ruído de medida)

Verifiquei que `scan_laranja` e `scan_azul` **não têm layout diferente**: as peças estão nas mesmas posições que em `scan_verde` (mediana |Δbbox| de 4 px e 6,5 px). Isso dá ground truth por posição, mas também significa que estes pares **não testam mudança de pose**. Preto, bege e vermelho têm layout diferente.

| Comparação com verde | n | top-1 forma (free) | top-1 (corner) | RMS própria re-scan, mediana | p90 | NN outra peça, mediana | outra/própria > 1,5 |
|---|---|---|---|---|---|---|---|
| laranja (GT por posição) | 60 | 83% | 88% | **0,54 mm** | 1,96 | 1,19 mm | 72% |
| azul (GT por posição) | 58 | 79% | 91% | 0,66 mm | 1,97 | 1,24 mm | 62% |
| preto (GT por aparência, 41 confiantes) | 41 | 68% | – | 0,70 mm | 2,81 | 1,27 mm | 59% |

- Para bege e vermelho, o GT por aparência (histograma Lab) teve poucas correspondências confiantes (20 e 15), e com isso os números não são fiáveis. Ficam no JSON, não os uso.
- Sem GT, pelo critério do enunciado (NN mútuo e razão melhor/segundo < 0,6), laranja dá 43/61 correspondências "inequívocas" (70%); 40 dessas 43 apontam para a peça com o mesmo índice e a mesma posição.
- **Piso de ruído:** em mediana cerca de 0,5 mm RMS, contra cerca de 1,2 mm para a outra peça mais parecida (margem mediana ×2,5).
- A cauda (p90 de cerca de 2 mm) vem de defeitos da segmentação: correlação de 0,69 com a rugosidade do contorno. Exemplo: laranja #37 tem um bocado comido, em `t4_rescan_laranja_vs_verde.png`.
- **Dentro deste conjunto, a forma sozinha identifica cerca de 83–91% das peças** quando o contorno está limpo. As falhas são pares próximos (verde #47 e #34: própria 0,72 e 1,09 mm contra outra 0,59 e 0,83 mm).
- Com 3008 peças, a densidade de vizinhos da mesma classe será cerca de 50 vezes maior. Com uma margem de apenas ×2,5 sobre o ruído, a forma isolada **não** vai identificar univocamente uma peça no puzzle completo. Isto é uma extrapolação, não foi medido.

## 5. Teste de compatibilidade tab/blank (sanity check)

O perfil T foi comparado com o perfil B invertido (x→1−x, y→−y, ordem revertida). Score = RMS·L + |ΔL| (mm). Foram 14 307 pares; o score mediano é 2,8 mm.

Os 6 melhores estão em `t5_tab_blank_complementares.png`: 4s3/20s0 (0,43), 37s3/43s0, 7s2/28s0, 4s3/3s0, 49s0/18s3 e 0s3/17s1. Na sobreposição são todos casos de "cabeça standard" no mesmo sítio do lado, com RMS de 0,28–0,51 mm e ΔL ≤ 0,16 mm.

A patilha 4s3 aparece duas vezes, com encaixes diferentes, o que mostra que **a semelhança de perfil não discrimina encaixes reais**. As sobreposições parecem encaixes plausíveis, mas não há forma de confirmar. Não é evidência de vizinhança real.

## Imagens geradas

| Ficheiro | O que mostra |
|---|---|
| `montagem_cantos_scan_verde.png` | 61 peças: contorno colorido por tipo de lado (T vermelho, B azul, F verde), cantos (magenta; preto se o ângulo se desviar > 20°), candidatos (círculos cinza), id, classe, tipo do `edges.py`, A×B mm, rugosidade e score do quadrilátero |
| `falha_abertura_morfologica.png` | Porque é que a abertura com disco de 3,5 mm não serve para obter o "corpo" (peça #14) |
| `t3_pares_mais_parecidos.png` | Os 8 pares mais parecidos do conjunto, alinhados (rotação e início ótimos) |
| `t3_perfis_TT_mais_parecidos.png`, `t3_perfis_BB_mais_parecidos.png` | Os 8 pares de lados T–T e B–B mais parecidos, em mm |
| `t3t4_histograma_nn_vs_rescan.png` | Distância ao vizinho mais próximo dentro do verde contra distância à própria peça re-digitalizada (laranja) |
| `t4_rescan_laranja_vs_verde.png` | 6 pares verde/laranja: recortes e sobreposição. 4 corretos (do melhor ao pior) e 2 falhas da forma |
| `t5_tab_blank_complementares.png` | Os 6 melhores pares tab/blank (perfil T contra B invertido) |

## O que NÃO foi verificado

- A orientação (qual eixo é o horizontal no puzzle). Por isso não testei "mais largas do que altas", só que não são quadradas.
- O valor absoluto do tamanho com precisão abaixo de cerca de 0,25 mm: há viés da fronteira da segmentação entre scans e não houve calibração física (por exemplo, régua digitalizada).
- Os scans a 600 dpi (azul_claro, rosa, impressora_branco) e amarelo, amarelo_claro e verde_claro não foram usados.
- As montagens de cantos dos outros scans (só inspecionei verde, e os pares de laranja). A deteção de F em preto e bege é suspeita.
- O efeito de mudar a pose da peça: laranja e azul têm o mesmo layout que o verde. Só preto dá essa informação, e com GT por aparência.
- Se o ground truth por aparência está certo nos scans com layout diferente.
- Encaixes reais tab/blank (não há pares vizinhos conhecidos).
- A extrapolação para as 3008 peças (é só uma estimativa qualitativa).
- O espelhamento: as peças foram tratadas sem reflexão. Os Hu moments são quase invariantes a espelho.
- Os limiares (0,15 para T/B/F, 14–23 mm para os lados) não foram otimizados nem validados contra rótulos manuais.
