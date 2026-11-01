# E-real-2: solta → solta com desempate pela imagem (2026-10-31)

Script: `tools/diagnostico/gemeos/ereal2.py`. Usa `segment_scan` de `src/`, `ereal.py` e `esym.py` como bibliotecas, e precisa de `$PPF_SCRATCH/gemeos/esym.pkl`. Não houve alterações em `src/` nem em `tests/`.
- **Tempo:** 131 s com a memória em cache, ≈ 170 s com `--force`, que volta a segmentar as 6 folhas (OpenCV 4.11).
- **Onde estão os resultados:** números completos em `results.json` → `ereal2`; GT legível por máquina em `ereal2_gt_BE.json`; o modelo para o Tiago anotar está em `ereal2_propostas.txt`.

Etiquetas: **[V]** verificado (com n e fonte), **[NT]** não testado, **[F]** testado e falhou.

## Resumo

1. **Há 2 propostas BE → céu, ambas passam o teste da imagem e ambas foram confirmadas fisicamente pelo Tiago: precisão 2/2 [V, n = 20 consultas, 2 propostas; §7].**
   - **BE(2,4) → f2p1 #4:** gémea na célula (2,61). Forma **ACEITE**: d1 0,408 mm, margem 2,39. ΔE 8,7, a 2.ª melhor cor das 98 peças de céu para essa célula. Vizinho mútuo. **ACERTO (2026-10-31):** encaixa na borda e coincide com BE(2,4) rodada 180°.
   - **BE(5,5) → f1p1 #6:** gémea na célula (5,60). Forma **AMBÍGUA**: d1 0,539 mm, única candidata que passa classe + cordas. ΔE 10,8, também a 2.ª melhor de 98. Vizinho mútuo. **Forma confirmada (2026-10-31):** coincide com BE(5,5) rodada 180°; a posição não é verificável (zona vazia), a peça ficou à parte etiquetada (5,60).
   - Re-execução com o defeito S3 corrigido (188 soltas, cordas por tipo de lado): as mesmas 2 propostas, com os mesmos números de peça [V, §8].
   - As outras 18 BE ficam **SEM**: d1 entre 0,81 e 1,95 mm, na gama dos não-gémeos da mesma classe do E-sym (p5 0,85, mediana 1,48).
   - É consistente com a maioria das 20 gémeas não estar entre as 100 peças, que foram escolhidas pelo aspeto. Não se mede recall.
2. **Zero falsos positivos da forma nos negativos conhecidos [V].** Entre 10 472 pares negativos conhecidos há 0 ACEITE e 1 AMBÍGUA. Essa AMBÍGUA é A1(3,3) × B2(1,3), com margem 0,50: o gémeo verdadeiro de A1(3,3) está mais perto, por isso uma consulta nunca a proporia.
   - Entre os 4 753 pares céu × céu (que se esperam negativos): 0.
   - Controlo positivo E-sym: 17/20 ACEITE, d mediana 0,303 mm, margem mínima 1,67. **Os 3 que falham, falham na regra 2 (cordas):** |ΔL| de 1,0 a 1,8 mm nos lados vizinhos do lado F, porque o canto do lado reto escorrega.
   - Com |ΔL| ≤ 2 mm passam 20/20 sem nenhum falso positivo novo nos negativos (aparece 1 AMBÍGUA céu × céu) [V].
3. **A imagem contra a arte limpa (25 px por célula) serve como consistência de cor no céu, não como identidade nem orientação [V].**
   - Nas 20 BE em relva: a rotação prevista ganha 7/20 e a própria célula fica na posição mediana 430 de 3008 [F como localizador].
   - Nas 20 A1 (céu, borda de cima) a rotação certa ganha 0/20: céu uniforme.
   - Mas os dois pares propostos têm a melhor cor quase absoluta para a sua célula, ambos em pct 1 % das 98.
4. **A localização conjunta de um par pela imagem funciona por banda, não por célula [V, n = 20 pares E-sym + 1 par BE↔céu].**
   - Pares E-sym:
     - célula certa entre as 3008: posição mediana 26 (top-1 0/20, top-10 3/20);
     - entre as 214 células de borda: posição mediana 4 (top-1 1/20, top-10 17/20).
   - Par BE(2,4) + f2p1 #4: a célula GT (46,4) fica na posição **1 entre as 2790 interiores** (4 entre as 3008). A BE sozinha fica na posição 429.
5. **Tarefa B: a calibração célula↔silhueta melhora a margem também fora da amostra [V, n = 25].** A margem fica abaixo de 1,5 em **9/25 → 3/25** (pool de 68 com classe), tanto com escala como com desvio isotrópico, estimados em leave-one-out. Detalhe em `EREAL.md`, linha nova em (b).

## 1. Memória (186 soltas, `segment_scan`)

| origem | n na memória | verificação |
|---|---|---|
| BE (`gt_canto_BE_soltas_300dpi.jpg`) | 20 | grelha verificada (abaixo) |
| céu f1p1 / f1p2 / f2p1 / f2p2 | 35 / 15 / **40** / 8 = **98** | esperadas 35 / 15 / **42** / 8 = 100 |
| BD (`ereal.loose_pieces`) | 28 | as verificações do `ereal.py` passaram |
| E-sym (A1 + B2, variante scan) | 40 | 4 cantos 40/40 |

**BE [V]:**
- `segment_scan` devolve 25 objetos; ficam 20 peças. Os 5 excluídos são todos a faixa em L montada:
  - #24: cluster de 2410 mm²;
  - #17, #18 (206 mm²) e #23: a 0,0 mm de outra peça;
  - #12: sem 4 cantos. É o topo da faixa e fica a 3,7 mm do vizinho, por isso a regra da distância de 1,5 mm não o apanha.
- A regra "a < 1,5 mm de outra peça" e a exclusão por falta de cantos são minhas. As soltas ficam a ≥ 3,3 mm umas das outras.
- Verificações automáticas, todas passaram:
  - filas, de baixo para cima: [4, 4, 4, 4, 2, 2];
  - colunas, da direita: [6, 6, 4, 4], com x 1880 / 1414 / 948 / 476 px;
  - casas iguais às esperadas;
  - 20/20 com 4 cantos e sem lado F;
  - L\* mediano por coluna: k=2 48,6; k=3 56,2; k=4 57,0; **k=5 25,4**, o mais baixo, como esperado;
  - áreas entre 346 e 473 mm².
- Na arte limpa, a linha l = 43 (k = 5) cai na banda escura de arbustos: confirmação independente da grelha [V, vi a arte com a grelha desenhada].

**Céu:**
- Nada foi excluído por cluster, `touches_frame`, área ou falta de cantos. A tira branca à direita **não sai como objeto** em nenhuma folha.
- **f2p1: 40 em vez de 42 [F, defeito de `segment_pieces`; corrigido depois, §8].** As 2 peças da coluna da direita (fila 3 e última fila), junto à tira branca do papel, não aparecem na saída.
  - Na `binary_mask` de debug do `segment_pieces` (vista) estão ambas, mas ligadas pela máscara à tira branca do bordo, que é primeiro plano.
  - O componente é descartado sem `touches_frame`. É uma variante do S1 e cai no critério do M3 "peça junto ao bordo do scan não perdida".
  - Não são numeradas e não entram na memória. O `ereal2_propostas.txt` avisa.

## 2. Consulta BE → as outras 185 (regras 1–4)

| decisão (forma) | n | proposta |
|---|---|---|
| ACEITE | 1 | BE(2,4) → f2p1 #4 (céu) |
| AMBÍGUA | 1 | BE(5,5) → f1p1 #6 (céu) |
| SEM | 18 | — |

- **Precisão:** das 2 propostas, 2 caem no céu (plausíveis) e 0 em BD/E-sym (falsos positivos certos) [V].
- Entre as SEM, a top-1 é muitas vezes uma peça BD ou BE (relva, d 1,0–1,5 mm). São negativos conhecidos, e a regra rejeita-os.
- **Sensibilidade das cordas:** com |ΔL| ≤ 1 / 1,5 / 2 mm ou sem limite, as decisões das BE são as mesmas [V].
- **Céu → as outras 185:**
  - SEM em 96: a melhor é outra peça de céu em 62, nenhuma passa classe + cordas em 16, uma BE em 12, uma BD em 6;
  - AMBÍGUA 1 (f1p1 #6 → BE(5,5)) e ACEITE 1 (f2p1 #4 → BE(2,4)), ambas vizinhas mútuas;
  - céu → céu e céu → BD/E-sym ACEITE: 0 [V].

## 3. Cadeia de orientação e imagem

**Orientação [V].**
- A BE fica direita rodando o scan 90° no sentido horário. A rotação prevista da candidata é BE direita + phi + 180°, ajustada ao eixo do corpo mais próximo.
- **Controlo E-sym:**
  - A1 com o lado F em cima: 20/20;
  - B2 previsto com o F em baixo: 20/20;
  - resíduo para o eixo: mediana 0,49°, máx 2,0°.
- **Mas o teste do lado F não distingue o sinal:** −phi também dá 20/20, porque as rotações relativas A1/B2 são ≈ 0°/180°. O sinal confirma-se pelo resíduo:
  - E-sym: +phi 0,49° contra −phi 9,2° (mediana);
  - nas 1 960 combinações BE × céu (peças rodadas ao acaso na folha): +phi 3,7° contra −phi 11,9°;
  - nas top-3 por forma: +phi 2,3° (p90 6,0°) contra −phi 12,0° (p90 33,9°).
  - **Usou-se +phi**, que também é o sinal definido por `dist.aligned_b`.

**Recorte:**
- Lab do scan, com **L\* − 4,8** (SECCAO.md §C, só L\*, sem corrigir a\*/b\*: o céu do scan tem Δb\* ≈ +6).
- Rodado à volta do centro do corpo e reamostrado ao passo medido de 18,97 × 18,39 mm por célula (`seccao_celulas.json`; 1 px de arte ≈ 0,76 / 0,78 mm, em vez dos 0,74 nominais).
- Máscara do interior estrito **erodida 1 px**.
- Comparado com a célula da arte limpa (bbox fixa nas linhas 42–1156, sem M2), numa janela de 43 × 41 px (célula + ≈ 0,35 célula de orla), com jitter de ±2 px.
- Mede-se o ΔE médio e a NCC em L\*.

**Antes/depois da erosão** (escolhida nos controlos, não nas propostas):

| variante | A1 ΔE / a rotação certa ganha | B2 | BE própria | posição mediana da BE na arte |
|---|---|---|---|---|
| sem erosão | 13,4 / 0 | 22,6 / 6 | 25,5 / 5 | 500 |
| **erosão 1 px** | **6,7 / 0** | 21,5 / 8 | 23,0 / 7 | 454 |
| erosão 2 px | 5,2 / 6 | 20,8 / 6 | 22,2 / 7 | 422 |
| erosão 1 px + blur σ 1 | 8,1 / 0 | 15,0 / 9 | 18,5 / 5 | 452 |

- A orla de sombra/fundo dominava o ΔE no céu.
- Nenhuma variante torna a relva localizável [F].

**Linhas de base (erosão 1 px) [V]:**
- (i) Candidata top-1 contra a célula gémea da sua BE e contra as 19 células gémeas das outras BE: ΔE mediana 32,9 (n = 20) contra 37,9 (n = 380). A célula certa fica em 1.º em 3/20, com posição mediana 9.
  - Só 2 das top-1 são candidatas plausíveis, por isso isto mede sobretudo não-gémeas.
  - As células (2–5, 58–63) são vizinhas e todas de céu de pôr do sol: a discriminação célula a célula é fraca.
- (ii) Todas as 98 peças de céu contra a célula gémea de cada BE (n = 1 960): mediana 27,6, **p90 50,0** (o limiar usado). O p90 é permissivo (passa 90 % do céu); por isso reporta-se também o percentil:
  - f2p1 #4: ΔE 8,7, 1,0 % (só 1 das 98 tem ΔE menor);
  - f1p1 #6: ΔE 10,8, 1,0 %.
- (iii) A rotação prevista ganha às outras 3 em 9/20 top-1 (ao acaso: 5).
  - Ganha nas duas propostas: f2p1 #4 com 8,7 contra a 2.ª rotação mais baixa; f1p1 #6 também.
  - Mas a imagem não identifica a orientação no céu uniforme [V, A1 0/20].
- **Forma + imagem:** 1 ACEITE + 1 AMBÍGUA, igual à forma só. A imagem não muda nenhuma proposta e não contradiz nenhuma.

## 4. Pares entre soltas (186 × 185 / 2 = 17 205)

| relação pela GT | n pares | ACEITE | AMBÍGUA |
|---|---|---|---|
| gémeos E-sym (positivos) | 20 | **17** | 0 |
| negativos conhecidos (BD × tudo, BE × BD, BE × E-sym, BE × BE, E-sym × céu, E-sym não-gémeos) | **10 472** | **0** | 1 |
| céu × céu (esperado negativo) | 4 753 | 0 | 0 |
| BE × céu (desconhecido) | 1 960 | 1 | 1 |

- 340 pares passam classe + cordas [V].
- Decisão do par: d ≤ t, e margem = (concorrente mais próximo de qualquer das duas peças) / d.
- Sensibilidade às cordas:

  | tolerância |ΔL| | E-sym ACEITE | negativos conhecidos | céu × céu |
  |---|---|---|---|
  | 1 mm | 17 | 1 AMBÍGUA | 0 |
  | 1,5 mm | 18 | 1 AMBÍGUA | 1 AMBÍGUA |
  | 2 mm | **20** | 1 AMBÍGUA | 1 AMBÍGUA |
  | sem limite | 20 | 1 AMBÍGUA | 2 AMBÍGUA |

  **Para o M10:** 1 mm é apertado para peças de borda (canto do lado F).

**Localização conjunta pela imagem** (score = RMS ΔE de A em X + RMS ΔE de B na gémea de X; rotação relativa fixa pela forma; 4 rotações globais):

| conjunto | n | posição da célula GT entre as 3008: mediana / top-1 / top-10 | entre as compatíveis |
|---|---|---|---|
| pares E-sym | 20 | 26 / 0 / 3 | 214 de borda: 4 / 1 / **17** |
| BE(2,4) + f2p1 #4 | 1 | 4 | 2790 interiores: **1** (top-3 compatíveis (46,2), **(46,4)**, (46,3)) |
| BE sozinha (controlo) | 20 | 429 / 0 / 0 | — |

- Leitura: a cor fixa a banda; a gémea de céu fixa o lado, e o par (relva + céu) localiza-se muito melhor do que a relva sozinha [V].
- A coluna fica incerta na faixa do céu uniforme (o top-3 dos E-sym fica quase sempre na linha 1).
- A posição 1 do par BE(2,4) + f2p1 #4 é **n = 1**; o par foi confirmado fisicamente (§7). Com o 2.º par confirmado, n = 2: ver §8.

## 5. Figuras (todas vistas)

| figura | o que se viu |
|---|---|
| `ereal2_BE__contours.jpg` | Rótulos BE(k,j) certos: coluna da direita k = 2; coluna esquerda escura k = 5; fila de baixo j = 2. A faixa em L sai em 5 objetos, todos a vermelho. |
| `ereal2_{f1p1,f1p2,f2p1,f2p2}__contours.jpg` | Contornos justos às peças, inclusive nas claras. f2p1: 2 peças à direita **sem contorno** (junto à tira branca). Peças rodadas ao acaso na folha. |
| `ereal2_{folha}_propostas.jpg` | f2p1 #4 a verde com (2,61)\* e 0,41/3,6; f1p1 #6 a amarelo com (5,60)\*. Nada mais está marcado. |
| `ereal2_be_propostas.png` | BE(2,4)/f2p1 #4: contornos sobrepostos; peça taupe-acinzentada contra nuvem castanho-acinzentada na célula (2,61). BE(5,5)/f1p1 #6: peça laranja contra céu laranja do pôr do sol. As outras: contornos visivelmente diferentes, ou top-1 de relva (BD/BE) com cor oposta à arte. A zona-alvo (linhas 2–5, colunas 58–63) é céu quente laranja/castanho, não azul. |
| `ereal2_imagem_hist.png` | (i) certa ≈ errada; (ii) as propostas top-1 espalhadas, 2 no bin mais baixo; controlos: A1 ≈ 6–7, relva ≈ 17–35. |
| `ereal2_matriz.png` | Bloco E-sym com as 20 diagonais do gémeo (vermelho) a amarelo; nos outros blocos, nenhum quadrado claro fora da diagonal, exceto os 2 pares BE↔céu (1 ponto branco = ACEITE, 1 preto = AMBÍGUA). |

## 6. Limites e o que NÃO foi verificado

- **Não há recall:** não se sabe quantas das 20 gémeas estão entre as 100 de céu. As 2 propostas foram depois confirmadas fisicamente (§7).
- A arte é usada por bbox fixa, sem M2. A fotometria corrige só L\* − 4,8. A imagem é consistência de cor, não identidade.
- A escolha da erosão de 1 px foi feita nos controlos (A1/B2/BE própria), não nas propostas.
- A ordem das propostas não depende dela [V: sem erosão dá as mesmas 2, com ΔE 12,5 / 14,7 e pct 0 %].
- "Negativos conhecidos" que dependem de suposições: BD × céu (supõe-se que as gémeas UL das BD não estão no saco do céu, porque a secção UL está montada) e E-sym × céu.
- f2p1 perde 2 peças (defeito de `segment_pieces` junto à tira branca) [F]. Corrigido depois em `src/segmentation.py` (§8).
- n pequenos: 20 consultas BE, 2 propostas, 1 par para localizar com GT.
- O t95/tmax e a margem vêm do E-sym (silhueta↔silhueta, a mesma modalidade).
- Não testado [NT]: corrigir a\*/b\*; a arte a resolução mais alta; ΔE por cima de uma descrição de textura; `pytest` (não houve alterações em `src/` nem em `tests/`).

## 7. Confirmação física (2026-10-31)

O Tiago verificou as 2 propostas com as peças na mão. O registo fica em `ereal2_confirmacoes.json` (manual, lido pelo `ereal2.py`; a peça é reconhecida pelo centro na folha em mm, por isso sobrevive a renumerações), e o `ereal2_propostas.txt` passa a mostrar o resultado em vez de `ACERTO/ERRO: ____`.

| peça | célula | resultado | nota |
|---|---|---|---|
| f2p1 #4 (gémea de BE(2,4)) | (2,61) | **ACERTO** | encaixa na borda; coincide com BE(2,4) rodada 180° |
| f1p1 #6 (gémea de BE(5,5)) | (5,60) | **forma confirmada, posição não verificável** | coincide com BE(5,5) rodada 180°; zona vazia, a peça ficou à parte etiquetada (5,60) |

- **Precisão das propostas: 2/2 [V].** Uma era ACEITE e a outra AMBÍGUA (d1 0,539 mm, única candidata). n = 2: não chega para calibrar o limiar da AMBÍGUA, mas é a primeira confirmação real da cadeia solta → solta.
- **Consequência para o produto (M12):** é preciso um estado novo de peça, `posicao_conhecida`. A célula é conhecida (pela gémea), mas a peça ainda não se pode colocar porque não há vizinho montado. O programa deve guardar estas peças e avisar quando uma vizinha da célula for colocada ("ir buscar f1p1 #6 / saco N, vai para (5,60)").

## 8. Re-execução com S3 corrigido (188 soltas, cordas por tipo de lado)

**O que mudou:**
- `src/segmentation.py`: `_frame_strip_mask` encontra a tira branca do papel ao longo do bordo do scan e tira-a da máscara antes da rotulagem (e do limiar de `segment_scan`). As peças perto dela levam `touches_strip`.
- `ereal2.py`: regra 2 com `--dl-mode` (por omissão `tipo`: |ΔL| ≤ 2 mm no lado F e nos dois adjacentes, ≤ 1 mm nos outros) e confirmações físicas.
- Comandos: `ereal2.py --force --dl-mode 1mm` (refaz a memória), depois `ereal2.py --dl-mode tipo` (é esta que fica nas saídas e em `results.json` → `ereal2`). A 1.ª execução fica em `results.json` → `ereal2_v1`.

**Segmentação [V]:**
- f2p1 dá 42, e as 2 peças recuperadas são as da coluna da direita junto à tira: **f2p1 #18** (fila 3, classe BBBT, 348 mm²) e **f2p1 #42** (última fila, BTTT, 398 mm²). Ambas têm `touches_strip`, não têm `touches_frame` e o contorno é justo (visto).
- Estavam a ≈ 1,9 mm da tira; foi o fecho morfológico que as colou a ela.
- Renumeração de f2p1: #1–#17 iguais; a antiga #n (n ≥ 18) passa a #n+1; as novas são #18 e #42.
- f1p1, f1p2 e f2p2: numeração idêntica.
- As 2 peças confirmadas mantêm o número (f2p1 #4, f1p1 #6).
- Todas as outras peças de todas as folhas (BE, BD, E-sym, céu) ficam com o contorno igual ao píxel (área igual).

| | 1.ª execução (`ereal2_v1`) | re-execução, `tipo` |
|---|---|---|
| memória | 186 (f2p1 40/42) | **188** (f2p1 42/42) |
| BE → memória (forma) | 1 ACEITE, 1 AMBÍGUA, 18 SEM | igual |
| BE(2,4) → f2p1 #4 | ACEITE, d1 0,408, margem 2,39, ΔE 8,7, pct 1,0 % (1 de 98 mais baixa) | ACEITE, d1 0,408, margem 2,395, ΔE 8,7, **pct 2,0 %** (2 de 100 mais baixas) |
| BE(5,5) → f1p1 #6 | AMBÍGUA, d1 0,539, única, ΔE 10,8, pct 1,0 % | igual (pct 1,0 % de 100) |
| (ii) céu × célula gémea | n 1 960, p90 50,0 | n 2 000, p90 49,9 |
| pares negativos conhecidos | 10 472: 0 ACEITE, 1 AMBÍGUA | **10 608: 0 ACEITE, 1 AMBÍGUA** (o mesmo par A1(3,3) × B2(1,3), margem 0,50) |
| céu × céu | 4 753: 0 | 4 950: 0 |
| BE × céu | 1 960: 1 ACEITE, 1 AMBÍGUA | 2 000: as mesmas 2 |
| controlo E-sym (pares) | 17/20 ACEITE | **20/20 ACEITE** (d mediana 0,303, margem mín 1,67) |

**Peças recuperadas [V]:**
- Nenhuma BE as propõe, e nenhuma passa classe + cordas contra outra peça (consulta SEM, sem candidata).
- f2p1 #18: entre as BE e as de céu, as mais próximas pela free são de céu (d ≥ 1,04 mm; f2p1 #42: ≥ 0,94 mm). Contra BE(2,2) a classe é diferente (BBTT) e a free dá 2,70 mm.
- Ambas têm um lado de corda ≈ 20,4 mm. Vi os cantos: o contorno e os cantos estão certos, e 20,4 mm é o p90 da corda máxima das 100 peças de céu. É um lado longo verdadeiro, não um artefacto da tira.
- **A imagem sozinha teria escolhido mal:**
  - f2p1 #18 tem ΔE 7,0 contra a célula (2,61), mais baixo do que a gémea confirmada f2p1 #4 (8,7). A #4 passa de 2.ª para **3.ª de 100** por imagem (depois de #18 e f2p2 #4).
  - f2p1 #18 é também a melhor cor de todas para a célula gémea de BE(2,2) (ΔE 6,8).
  - Só o filtro de forma põe a #4 à frente. Isto confirma que a imagem é consistência de cor no céu, não identidade.
- f2p1 #42: o ΔE mínimo é 14,7 (gémea de BE(2,6), pct 17 %).

**Modos de cordas na matriz completa (188 × 187 / 2 = 17 578 pares) [V]:**

| relação (n pares) | `1mm`: passam / ACEITE / AMBÍGUA | `tipo` | `2mm` |
|---|---|---|---|
| negativos conhecidos (10 608): BD × tudo, BE × BD, BE × BE, BE × E-sym, E-sym não-gémeos, E-sym × céu | 155 / **0** / 1 | 210 / **0** / 1 | 703 / **0** / 1 |
| céu × céu (4 950, esperado negativo) | 129 / 0 / 0 | 129 / 0 / 0 | 705 / 0 / **1** |
| BE × céu (2 000, desconhecido) | 39 / 1 / 1 | 39 / 1 / 1 | 255 / 1 / 1 |
| gémeos E-sym (20, positivos) | 17 / **17** / 0 | 20 / **20** / 0 | 20 / **20** / 0 |
| propostas BE → céu | BE(2,4) → f2p1 #4 ACEITE; BE(5,5) → f1p1 #6 AMBÍGUA | iguais | iguais (margem 2,388) |

- **Regra do Tiago cumprida:** com `tipo` continua a haver 0 ACEITE entre os negativos conhecidos (n = 10 608), e entre céu × céu 0 de 4 950. Por isso adota-se `tipo` (é o valor por omissão do script).
- O E-sym sobe de 17/20 para 20/20.
- Ao contrário de 2 mm uniforme, `tipo` não deixa passar mais pares entre peças interiores. As 98 + 2 de céu, as BE e as BD não têm lado F, por isso para elas `tipo` é igual a `1mm`. Os 55 pares a mais que passam entre os negativos são todos pares de borda E-sym, e nenhum chega a ACEITE.
- A AMBÍGUA céu × céu que aparece com 2 mm não aparece com `tipo`.
- **Limite:** `tipo` só foi posto à prova em peças de borda de uma só aresta (E-sym, borda de cima). Cantos e outras bordas não foram testados [NT].

**Localização conjunta dos pares confirmados (n = 2) [V]:**

| par | célula GT | posição entre as 3008 | entre as 2790 interiores | top-3 compatíveis |
|---|---|---|---|---|
| BE(2,4) + f2p1 #4 | (46,4) | 4 | **1** | (46,2), (46,4), (46,3) |
| BE(5,5) + f1p1 #6 | (43,5) | 14 | **13** | (43,4), (44,4), (44,5) |

- O 2.º par fica na banda certa (linhas 43–44, colunas 4–5). Falha a coluna por 1 e a GT fica na posição 13, mas o par continua muito melhor do que a BE sozinha (mediana 430).
- Leitura: com n = 2, a imagem do par localiza à banda e a ±1 coluna, não à célula. A cor das duas metades (relva + céu) não chega para fixar a coluna.

## 9. Regra da candidata única (2026-11-01)

Decisão do Tiago (2026-11-01): quando só uma candidata passa classe + cordas, a margem é indefinida e a consulta **não é proposta** (`sem`). Até aqui era «no máximo `ambigua`». `find_twin` guarda o caso em `single_candidate` e põe em `decision_shape` o que a margem infinita daria (`aceite` se d₁ ≤ t₉₅, senão `ambigua`). A imagem da candidata única deixa de ser testada.

Efeito medido com `tests/test_twin_real.py` (memória de 188 soltas, `$PPF_SCRATCH/ereal2/memoria.pkl`) [V]:

- **BE(5,5) → f1p1 #6 passa de AMBÍGUA a `sem`** (candidata única, d₁ 0,539 mm, `decision_shape` `ambigua`). É a proposta cuja forma foi confirmada fisicamente no §7. Com a regra nova, esse acerto já não aparece na lista. O ΔE na célula (5,60), calculado à parte pelo teste com a mesma pose, continua em 10,7.
- BE(2,4) → f2p1 #4 continua ACEITE (d₁ 0,408 mm, margem 2,39, ΔE 8,7). As outras 18 BE continuam `sem`, e nenhuma delas tinha candidata única dentro de t_max.
- Pares (consultas só por forma, 188 × 187): os 20 gémeos E-sym passam de 20 propostos a **15 `aceite` + 5 suprimidos**. Sem a regra (`decision_shape`), os 20 seriam `aceite`. Entre BE × céu ficam 1 `aceite` e 0 `ambigua` (era 1 + 1). Entre os negativos conhecidos (10 608) e céu × céu (4 950) continua a haver 0 `aceite`. Há 0 candidatas únicas com d₁ ≤ t₉₅ em pares negativos: a regra não estava a esconder nenhum falso positivo nesta amostra.
- E-sym isolado, com o pool das 20 B2 (4 das 5 classes têm um só membro): A1 → B2 dá **14 `aceite` + 6 suprimidas** (antes 14 + 6 `ambigua`), top-1 20/20. A2 → B2 dá 12 `aceite` + 2 `ambigua` + 5 suprimidas + 1 `sem` pelas cordas (antes 12 + 7 `ambigua` + 1). Não há propostas erradas, nem contando as suprimidas.
- Cadeia de orientação: continua 20/20. Em 5 dos 20 casos a pose da candidata única é calculada pelo teste, porque o `find_twin` já não a testa.

Leitura: nesta amostra a regra só retira acertos (1 confirmado fisicamente e os gémeos E-sym) e não retira nenhum erro. É um custo de recall assumido em troca de nunca propor sem margem. Os casos ficam em `fetch.json` → `suprimidas` para serem revistos.

## Reprodução

```powershell
$env:PPF_SCRATCH = "C:\...\scratchpad"; $env:PYTHONIOENCODING = "utf-8"   # precisa de gemeos/esym.pkl
python tools/diagnostico/gemeos/ereal2.py           # 131 s com a memória em cache ($PPF_SCRATCH/ereal2/memoria.pkl)
python tools/diagnostico/gemeos/ereal2.py --force   # ≈ 175 s, volta a segmentar as 6 folhas
python tools/diagnostico/gemeos/ereal2.py --dl-mode 1mm   # cordas: 1mm | tipo (omissão) | 2mm
```
