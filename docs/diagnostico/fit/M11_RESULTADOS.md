# M11 — molde do buraco como ranking: resultados (critérios de `M11_CRITERIOS.md`, nada afinado depois de ver S_V)

_2026-11-07. Código de produto: `src/fit.py` (medido diretamente: as ferramentas chamam-no). Ferramentas: `tools/diagnostico/fit/m11_particao.py`, `m11.py` (`sanidade` | `afinar` | `validar` | `real` | `figs`). Dados commitados: `m11_particao.json`, `m11_sanidade.json`, `m11_afinacao.json`, `m11_validacao.json`, `m11_real.json`, `m11_figs.json`, `m11_{melhores,piores,sem_fiavel}.jpg`. Etiquetas: **[V]** verificado, **[NT]** não testado, **[F]** falha. Reproduzir: `gt.py` → `fit_eval.py` (cache de tiras em `$PPF_SCRATCH`) → `buraco.py` (referência do dia) → `m11_particao.py` → `m11.py sanidade` → `afinar` → `validar` → `real` → `figs` (≈ 20 min)._

## Veredicto

**Alvo principal [V]:** em S_V (214 buracos de 12 folhas que não entraram na afinação, com todos os b/d, montanha e vale), a configuração final dá **E5 estrito top-1 98,1 % (IC 95,3–99,3) a N = 32 e 96,2 % (92,8–98,1) a N = 100**, IC inteiro acima de 85 %; top-3 99,8 / 99,0 % [V]. O passo 5 reproduzido nos mesmos buracos dava 93,4 / 90,4 %. O filtro mole e a erosão calibrada explicam o ganho (cada um +3 pontos; juntos +4,7 / +5,8); a rejeição não mexe no top-1 (só decide quando propor). **Peça ausente [F] no critério de utilidade:** com confiança `alta` as falsas por buraco são 0,091 (alvo ≤ 0,05; fronteira de falha 0,2 não atingida), cobertura 79 %, precisão derivada 49 % a π = 10 % (alvo ≥ 90 %; falha clara < 50 %: fica no limite) e 8 % a π = 1 %. **Direção inversa no tabuleiro real [V]:** 0,06 propostas `alta` por solta (alvo ≤ 0,2), 8 em 212 buracos × 134 soltas. **Casos reais [NT] por construção (n = 15):** 15/15 top-1 no pool do lote (Wilson 80–100 %), 14/15 a célula certa entre 212 buracos. É um **ranking com confiança honesta**, não uma proposta: a GUI (Parte 4) liga-se.

## 1. Porta de sanidade [V]

`src.fit` com a configuração «passo 5» (erosão 0 / 0,48, corte 1× duro, sem regra F, sem rejeição) reproduz o `buraco.py` corrido hoje sobre os 478 buracos atuais: custos por lado iguais a 4,8·10⁻⁷ (float32 vs float64) e **Δ = 0,00 pontos** nas 8 comparações (E5 estrito top-1 e top-3 a N = 32 / 64 / 100 / completo, nas duas erosões; `m11_sanidade.json`). Depois de promover `shrink_sides`/`piece_strips`/`wilson` para `src.fit`, `buraco.py` dá o JSON **byte a byte igual** nas duas condições. A substituição de `np.nanmedian` por uma mediana ordenada (mesmos valores, verificada em sintético) foi feita depois da afinação; a porta foi re-corrida (ver HANDOFF).

## 2. Afinação (só S_T: 144 buracos de 8 folhas, N = 32; `m11_afinacao.json`)

| passo | grelha → E5 estrito top-1 | escolha (regra do §4 dos critérios) |
|---|---|---|
| erosão `e` (corte duro) | 0: 79,6 %; 0,12: 83,1; 0,24: 87,5; 0,36: 88,9; **0,48: 88,7**; **0,60: 92,0**; 0,72: 89,1 | **0,60 mm** (máximo; o 0,48 do E-real não era o melhor em S_T) |
| corte do filtro mole `cut` (e = 0,60) | 1× (duro): 92,0 % (10 certas a ∞); **2×: 98,3 %** (0 a ∞, top-3 100 %); 3×: 98,2; ∞: 98,2 | **2×** (máximo; empates → o mais apertado) |
| rejeição `T_abs` = quantil q do J da certa em S_T (e = 0,60, cut = 2×; mediana 1,84) | q = 0,90 → 2,666: cobertura 88 %, falsas 0,256/buraco, precisão π = 10 % 27,5 %; 0,95 → 2,857: 93 %, 0,344, 22,9 %; 0,99 → 3,111: 97 %, 0,478, 18,1 % | **q = 0,90** (nenhum cumpre a utilidade ≥ 90 % a π = 10 %; escolhido o de maior precisão com cobertura ≥ 30 %) |

Nota: nesta tabela «proposta» = confiança ≠ `sem` (inclui `media`), por isso as falsas por buraco são mais altas do que as do passo 5 (que só contava margem ≥ 1,5 = o nosso `alta`). A comparação com o passo 5 está na coluna «só alta» do §3. Os três valores foram gravados em `calibration.buraco` do `projects/alpes/puzzle.json` (`erosion_mm 0.6, chord_cut 2.0, t_abs 2.6656`).

## 3. Validação em S_V (214 buracos; Wilson 95 % com n = buracos; sorteios 200, sementes 20261106 + N) — ablação

| configuração | e | cut | T_abs | E5 estrito top-1 N = 32 | N = 100 | pool completo | top-3 32 / 100 | E4 certa-ou-gémea 32 / 100 | **só `alta`:** cobertura / falsas por buraco / precisão π = 10 % / π = 1 % (N = 32) | ≠ `sem`: cobertura / falsas / π = 10 % |
|---|---|---|---|---|---|---|---|---|---|---|
| passo 5 (reproduzido) | 0 | 1× | — | 93,4 % (89,3–96,1) | 90,4 % (85,5–93,5) | 80,8 % | 95,7 / 94,9 | 70,7 / 56,6 | 59 % / 0,128 / 33 % / 4,4 % | 88 % / 0,766 / 11 % |
| passo 5 + erosão 0,48 | 0,48 | 1× | — | 96,0 % (92,2–97,8) | 94,3 % (90,5–96,8) | 86,9 % | 97,1 / 96,7 | 89,2 / 83,0 | 72 % / 0,150 / 35 % / 4,6 % | 89 % / 0,777 / 11 % |
| + filtro mole | 0 | 2× | — | 96,3 % (92,8–98,1) | 92,4 % (88,2–95,3) | 79,9 % | **99,5 / 98,3** | 70,7 / 56,6 | 60 % / 0,117 / 36 % / 4,9 % | 99 % / 0,975 / 10 % |
| + erosão calibrada | 0,60 | 1× | — | 96,1 % (92,8–98,1) | 94,7 % (91,0–97,1) | 87,4 % | 97,2 / 96,8 | **91,3 / 85,8** | 73 % / 0,151 / 35 % / 4,6 % | 89 % / 0,779 / 11 % |
| + rejeição (só) | 0 | 1× | 3,168* | 93,4 % | 90,4 % | 80,8 % | 95,7 / 94,9 | 70,7 / 56,6 | 58 % / **0,081** / 44 % / 6,8 % | 84 % / 0,305 / 22 % |
| mole + erosão | 0,60 | 2× | — | **98,1 % (95,3–99,3)** | **96,2 % (92,8–98,1)** | 88,8 % | **99,8 / 99,0** | 91,3 / 85,8 | 79 % / 0,135 / 40 % / 5,6 % | 99 % / 0,977 / 10 % |
| **final** | 0,60 | 2× | 2,666 | **98,1 % (95,3–99,3)** | **96,2 % (92,8–98,1)** | 88,8 % (83,9–92,3) | **99,8 / 99,0** | 91,3 / 85,8 | **79 % / 0,091 / 49 % / 8,1 %** | 95 % / 0,356 / 23 % |

(*) na ablação a rejeição é recalibrada em S_T para cada configuração (q = 0,90 do J da certa dessa configuração). E4 = só forma, filtro duro, referência do plano (alvo ≥ 90 % certa-ou-gémea): 91,3 % a N = 32 com a erosão [NT contra o alvo: IC não calculado neste bloco], 85,8 % a N = 100.

**Leitura.** (1) **Top-1 [V]:** o alvo ≥ 85 % é cumprido com o IC inteiro a N = 32 e N = 100; no pool completo (813 peças, fora do caso de uso) 88,8 % (83,9–92,3) [NT]. (2) **Ganhos isolados:** filtro mole +2,9 / +2,0 pontos; erosão calibrada +2,7 / +4,3; juntos +4,7 / +5,8; a rejeição 0 (não ordena). O top-3 com o filtro mole é 99,5–99,8 %: a certa quase nunca fica fora dos 3 cartões. (3) **Peça ausente:** a rejeição absoluta reduz as falsas `alta` de 0,135 para 0,091 por buraco e sobe a precisão a π = 10 % de 40 para 49 % ao custo de 0 pontos de cobertura `alta` (79 % nas duas); comparado com o passo 5 (0,128 / 33 %, cobertura 59 %), a configuração final é melhor em tudo, mas **não cumpre a utilidade** (falsas ≤ 0,05 ∧ precisão π = 10 % ≥ 90 % ∧ cobertura ≥ 30 %): precisão 49 % < 50 % = fronteira de falha clara → **[F]** para «propor sem saber que a peça está no lote», como no passo 5. Compromisso em números (N = 32, só `alta`): a π = 1 % (lote ao acaso) 8 % de precisão ≈ 11 falsas por certa; a π = 10 % ≈ 1 falsa por certa; a π = 50 % (peça sabidamente no lote) ≈ 10 certas por falsa. A `media` não é proposta: com ela a cobertura sobe para 95 % mas as falsas vão a 0,36 por buraco.

### 3.1 Fatias (configuração final; E5 estrito top-1 N = 32 / N = 100 / completo; falsas `alta` por buraco a N = 32)

| fatia | n | N = 32 | N = 100 | completo | falsas `alta` / cobertura |
|---|---|---|---|---|---|
| 2 vizinhas | 97 | 96,9 % (91,3–98,9) | 94,6 % (88,5–97,8) | 86,6 % | 0,062 / 79 % |
| 3 vizinhas | 87 | 98,9 % (93,8–99,8) | 96,9 % (90,3–98,8) | 88,5 % | 0,108 / 80 % |
| 4 vizinhas | 30 | 99,8 % (88,6–100) | 99,7 % (88,6–100) | 96,7 % | 0,131 / 77 % |
| céu | 92 | 99,8 % (96,0–100) | 99,6 % (96,0–100) | 96,7 % | **0,179** / 95 % |
| relva | 107 | 96,6 % (90,8–98,5) | 93,2 % (87,1–96,8) | 82,2 % | 0,024 / 66 % |
| montanha/floresta | 5 | 100 % (57–100) | 100 % | 100 % | 0,008 / 99 % |
| vale/aldeia | 10 | 98,2 % (72–100) | 95,6 % | 80,0 % | 0,026 / 66 % |
| só layout (a) | 188 | 98,5 % (95,4–99,5) | 97,2 % (93,9–98,9) | 92,0 % | 0,085 / 82 % |
| **b/d (GT independente)** | 26 | 95,3 % (81,1–99,3) | 89,4 % (71,0–96,0) | 65,4 % | 0,130 / 61 % |
| 2 · relva | 43 | **93,7 %** (81,4–97,6) | **89,3 %** (75,5–94,9) | 79,1 % | 0,027 / 66 % |
| 3 · céu | 40 | 99,9 % | 99,7 % | 97,5 % | 0,208 / 97 % |

**As 3 piores (n ≥ 20):** 2 vizinhas · relva (93,7 % / 89,3 %), b/d (95,3 % / 89,4 %), relva (96,6 % / 93,2 %). Todas acima da fronteira de falha; a N = 100 o IC de «2 · relva» e de «b/d» cruza os 85 % [NT nessas fatias]. **Padrão novo:** no céu a rejeição quase não corta (cobertura 95 %) e as falsas `alta` são as maiores (0,18–0,27 por buraco com 3–4 vizinhas): o custo de um céu liso é baixo para muitas candidatas; na relva a rejeição corta um terço das certas (cobertura 66 %) mas quase não há falsas `alta` (0,02). Um `T_abs` por zona é a mudança óbvia, **não feita** (seria afinar depois de ver S_V; fica de reserva). No pool completo a certa fica em 1.º em 190/214, 2.º em 9, 3.º em 5, ≥ 4.º em 10; a sua confiança é `alta` em 85, `media` em 126, `sem` em 3.

### 3.2 Figuras (cv-visual-verification; S_V, N = 100, configuração final; vistas)

- [`m11_melhores.jpg`](m11_melhores.jpg): 6 acertos (1 em cada ⌊n/6⌋, não escolhidos: P0007, P0256, P0418, P0504, P0581, P0727; 3 céu, 3 relva; 2–4 vizinhas). Em todos os painéis o contorno ciano da certa coincide com as vizinhas (amarelo). Dois são `alta` (P0256 margem 2,17; P0727 1,87), três `media` (margens 1,06–1,42) e **um `sem`** (P0581, relva, 4 vizinhas: J 2,84 > T_abs 2,67 apesar de top-1 em 90 % dos sorteios): é a face da rejeição, uma certa não proposta.
- [`m11_piores.jpg`](m11_piores.jpg): 6 falhas pelo pior rank no pool completo (P0502, P0493, P0021, P0034, P0492, P0481), **todas relva** com 2–3 vizinhas, J da certa 2,70–2,91 (perto do T_abs) e margens 1,00–1,32: quase-empates em textura de relva. À esquerda a certa **encaixa à vista**; à direita a vencedora (P0544, P0575, P0084, P0434, P0579, P0082) sobrepõe-se ou deixa folga. **Nenhuma das 6 ficou `alta`** (todas `media`): a confiança fez o seu trabalho.
- [`m11_sem_fiavel.jpg`](m11_sem_fiavel.jpg): os 3 «sem candidata fiável» com a peça presente (P0581 relva; P0643 e P0649 vale/aldeia, J 3,6–3,8): nas duas de vale a certa está bem acima do T_abs calibrado em céu + relva, e em P0649 a vencedora (P0202, escura) visivelmente não pertence à faixa amarela. A rejeição é demasiado apertada fora de céu/relva (n = 15 em S_V) [NT].

## 4. Tabuleiro real: 15 casos confirmados e direção inversa (`m11_real.json`; pool = as 134 soltas de hoje; regra F ligada; σ = +1 em 612/612 [V])

**a) Peça → candidatas para a sua célula (peça retirada e posta no pool): 15/15 top-1** (Wilson 79,6–100 %; 9/9 com ≥ 2 vizinhas), 15/15 top-3. Confiança: `alta` 8 (todas com ≥ 2 vizinhas; margens 2,04–5,48), `media` 4 (2 com 1 vizinha, 2 com 2 vizinhas e margem 1,48–1,89), `sem` 3 (P0126, P0131, P0162: **1 vizinha** com margem 1,19–1,31, como a regra manda). Passo 6 nas mesmas 15: 10/15 sem erosão, 14/15 com 0,48. **[NT] por construção (n < 20)**; amostra otimista (entraram pelo gémeo).
**b) Peça → tabuleiro (célula certa entre 212–213 buracos reais): 14/15 em 1.º**; P0129 (2,49) fica em 2.º atrás de (3,50) e a afetação conjunta dá-a a (3,50) (o único caso em que a afetação erra; nos outros 14 a peça é atribuída à célula certa). **Falsas `alta` noutros buracos: 0 em 15** (0,0 por peça); `media` noutros buracos 0,6 por peça (P0106 e P0131, 1 vizinha, aparecem como top-1 `media` em 9 e 7 buracos: é o que se espera de uma única vizinha e por isso nunca é `alta`).
**c) As 134 soltas contra os 212 buracos reais:** confiança `alta` em **8 buracos** (4 com 2 vizinhas, 4 com 3), `media` 32, `sem` 172 (dos 153 buracos de 1 vizinha, 144 `sem` e 9 `media`, 0 `alta`); **0,060 propostas `alta` por solta** (alvo ≤ 0,2 [V]; máximo 1 por peça); com afetação conjunta 7 ficam atribuídas (0,052 por solta). As 8 são o GT que falta (confirmação física; lista no HANDOFF): uma delas, **(3,28) ← P0133 (saco 1 nº 40), coincide com a proposta de gémea já aceite em `fetch.json`** (duas vias independentes, forma das vizinhas e simetria, a apontar a mesma peça); as outras 7 são células sem proposta de gémea: (4,39) P0122, (6,21) P0123, (2,37) P0177, (5,26) P0179, (7,7) P0139, (13,63) P0125 (a afetação conjunta dá esta célula a P0954), (3,46) P0135; todas céu, sacos 1 e 2.
**d) Cor entre scans (só medida):** ΔE do lado verdadeiro, vizinha de página montada (outro scan) mediana 4,89 (n = 18) vs vizinha de lote 4,95 (n = 12); RMS da forma mediana 0,57 mm com a erosão de 0,60. Sem desvio detetável; igual ao §15.4 do passo 6 [NT com n = 18].

## 5. O que fica de reserva (não afinado; declarado)

- `T_abs` **por zona** (ou por nº de vizinhas): o céu propõe de mais (falsas `alta` 0,18–0,27), a relva corta certas (cobertura 66 %) e o vale fica fora (J da certa 3,6–3,8 > 2,67). Precisa de GT fora de céu/relva.
- A grelha de erosão é não monótona em S_T (88,9 → 88,7 → 92,0 → 89,1 entre 0,36 e 0,72): o 0,60 ganhou por 3 pontos com n = 144 (≈ 1 dp); em S_V o 0,60 e o 0,48 ficam a 0,1 / 0,4 pontos um do outro.
- O declive do filtro mole (1 por mm), a escala 1,1 mm / 10 ΔE e o τ = 1,5 ficaram fixos.
- Afetação conjunta: medida só no tabuleiro real (7 vs 8 `alta`; 1 caso errado em 15); nos buracos virtuais não se aplica (pools independentes).
- Confirmações físicas: **atualizado 2026-11-08**: 10 eventos `hole_confirmed` (todos rank 1, `alta`, céu; 3 com m = 3, 7 com m = 2) e 0 `hole_rejected`; `python -m src.fit --project projects/alpes --relatorio` dá top-1 10/10 (Wilson 72–100 %), e o contador das sugestões `alta` (§8 dos critérios) «acertos 10 / falhas 0 / total 10; precisão 100 % (72–100 %); janela 0 falhas em 10: ativas». O limiar do §15.6 (n ≥ 60, ≥ 40 com ≥ 2 vizinhas, casos fora do céu) continua por atingir [NT fora do céu].
