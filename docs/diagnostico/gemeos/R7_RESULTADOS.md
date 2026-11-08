# Ronda 7 (2026-11-08) — resultados: as 6 propostas que não encaixam, velocidade, continuidade

_Critérios fixados antes em `R7_CRITERIOS.md` (`8af95b2`). Scripts: `tools/diagnostico/gemeos/r7_gt.py` (Parte 1, H5, H6(a); replay do log à data numa cópia), `r7_hipoteses.py` (H1–H4, H6(b)), `r7_tempo.py` (Parte 4). Dados: `r7_gt.json`, `r7_hipoteses.json`; figuras `r7_h2_forma.png`, `r7_h3_imagem.png`. Tudo medido numa **cópia** de `projects/alpes` (`$PPF_SCRATCH/alpes_r7`) com os ativos dos lotes 4–8 refeitos por `render.rebuild_stale` (esta máquina não tinha os `pieces/`/`crops/` desses lotes: 383 peças em 16 folhas; 0 silhuetas diferentes do log, fora as 17 com contorno manual, §1.3). Etiquetas: **[V]** verificado (n, Wilson 95 %), **[NT]** não testado, **[F]** testado e falhou._

## 0. Resumo

| caso | o que falhou | causa medida | o que muda |
|---|---|---|---|
| 1 · P1014 → (41,62), relva, âncora P0826 (7,3) | proposta **já era `ambigua`** (d1 0,514 > t95; margem 1,40; ΔE 70,9 > 50) e foi cartão em «Vai buscar» | H5 [V]: encaixe contra a única vizinha (P0071 a S) custo **9,14** ≫ T_abs 2,67 (tira ΔE 85,9); H1 [F] (âncora rank 1 `alta` no seu buraco, sem suspeita; a secção G0066 tem margem 1,07 < 1,5, único sinal fraco) | 3.1: `encaixe incompatível`, chip; decisão de produto sobre `ambigua` em «Vai buscar» é do Tiago |
| 2 · P1238 → (35,2), vale, âncora P0125 (13,63) | `aceite`: d1 0,477 (3 passam), margem 1,70, ΔE 41,7 «≤ 50 (ceu)» | H3 [V]: o rótulo «ceu» é o *fallback* (zona nunca passada) e o limiar 50 deixa passar 71 % das células aleatórias do vale; H5 [V]: encaixe contra P0638 (W) custo **4,56** > 2,67 (tira ΔE 40,6); H1 [F] (P0125 rank 1 `alta` em (13,63), P0954 em 7.º); H2 [F] (d1 0,477 está dentro da distribuição dos gémeos verdadeiros do vale; 0/1003 pares não-gémeos da mesma classe abaixo de t95) | 3.1 (incompatível) + 3.2 parcial: zona verdadeira no rótulo e «zona sem p90 calibrado → não `aceite`» |
| 3 · T0003 (P0987+P1110) → (4,63) | célula errada (a peça certa, P1181, gémea de P0061 (44,2), foi colocada lá às 16:57) | H6(a) [V]: twin((4,63)) = (44,2) estava **ocupada** à data do registo; (4,64) tinha X e twin(X) ocupadas; `pair_locate` com 1 rotação arbitrária (θ = 0) | 3.1: células com X ou twin(X) ocupadas excluídas; 4 rotações + forma |
| 4 · T0004 (P1060+P1163) → (4,62) | idem (P1114, gémea de P0055 (44,3), colocada às 16:59) | H6(a) [V]: twin((4,62)) = (44,3) ocupada; (44,2) e (45,7) ocupadas | idem |

A relação de gémeas dentro de cada par (d1 0,398 / 0,497, margens 2,49 / 2,01, nunca testada pela imagem) **não foi refutada** pelos reports (R0030–R0032, R0034 falam da posição); `pair_rejected` apaga o par para sempre: decisão do Tiago (HANDOFF).

## 1. Verdade de terreno (Parte 1; `r7_gt.py`, 425 s, 44 + 2 + 5 reaberturas do log à data)

### 1.1 Os 6 casos à data da proposta

| peça | lote nº | scan | célula · zona | âncora (estado, θ) | decisão listada | d1 mm | margem | ΔE | vizinhas colocadas à data | encaixe na pose prevista (H5) |
|---|---|---|---|---|---|---|---|---|---|---|
| P1014 | 4 · 56 | S0028 | (41,62) relva | P0826 (7,3), secção G0066, θ log None (initial_theta 94,2°) | `ambigua` | 0,514 | 1,40 | 70,9 | 1: S = P0071 | lado B↔T compatível, rms 0,60, dl 0,39, **tira ΔE 85,9 → custo 9,14** |
| P1238 | 7 · 55 | S0034 | (35,2) vale | P0125 (13,63), colocada por buraco `alta` 02:30, θ −7,1° | `aceite` | 0,477 | 1,70 | 41,7 | 1: W = P0638 | T↔B compatível, rms 0,55, dl 0,01, **tira ΔE 40,6 → custo 4,56** |
| P0987 + P1110 (T0003) | 4 · 29 + 6 · 2 | S0028, S0032 | (4,63) céu | — | `proposto` | 0,398 | 2,49 | — | (4,63) livre, **twin (44,2) ocupada**; (14,49) livre/livre; (4,64) ocupada/ocupada | par: pose desconhecida |
| P1060 + P1163 (T0004) | 5 · 27 + 6 · 55 | S0030, S0032 | (4,62) céu | — | `proposto` | 0,497 | 2,01 | — | (4,62) livre, **twin (44,3) ocupada**; (44,2) ocupada; (45,7) ocupada | idem |

Os outros 3 pares (T0001, T0002, T0005) tinham as 3 células livres dos dois lados à data; continuam `proposto`, por confirmar.

### 1.2 Conjunto etiquetado e reprodução

- **Positivos:** 44 colocações por gémea (43 com entrada em `fetch_listed`: 33 `aceite`, 10 `ambigua`; P0147 sem entrada), todas **céu** (filas 2–5); 38 `hole_confirmed` (37 céu, 1 montanha (15,62)); **negativos:** 2 gémeas (relva, vale) + 2 pares (células de céu). Fora do céu só há 1 positivo (buraco) e 2 negativos (gémea).
- **Reprodução à data** (`find_twin` com os limiares de hoje, pool de soltas reconstruído do log, sem o conjunto `proposed`): **34/43** coincidem na decisão e no top-1. As **9 divergências são todas peças a que o Tiago deu contorno manual hoje (17:10–17:58), depois de as colocar** (`piece_resegmented` motivo `manual`: P0098, P0999, P1064, P1114, P1245, P1203, P0105, P0165, P0935): com a silhueta manual o d1 passa para 0,69–0,85 mm (`sem`) ou a própria peça deixa de ser top-1 (P1064, P1114, P0165, P0935). Nas 34 peças com silhueta inalterada a reprodução é **34/34** [V]. O critério «≥ 40/43» não é cumprido à letra; a causa é externa ao motor (ver §1.3).
- Nas 34 reproduzidas: d1 mediana 0,377 mm, máx. 0,614 (uma `ambigua`); margem mediana 2,45, mín. 1,59; ΔE mediana 8,3, máx. 14,5. **34 das 44 âncoras têm `theta_deg` None** (peças de secção legada) → «melhor das 4 rotações».
- **Encaixe das aceites (controlo de H5):** 42 das 44 tinham ≥ 1 vizinha colocada à data; `side_costs` na pose confirmada: 0 lados impossíveis, **J máximo 2,08** (P1245, contorno manual), todos ≤ T_abs 2,666. As 2 falsas: 9,14 e 4,56. Separação 2/2 vs 0/42 [V, n pequeno nos negativos].

### 1.3 Achado lateral: os 17 contornos manuais de hoje inflam a silhueta

`python -m src.overrides --project projects/alpes --pares`: 17 contornos manuais (16 de hoje), IoU 0,82–0,87 contra o automático, **«a mais» 52–68 mm² por peça, p95 1,22–1,52 mm** (o laço ficou ≈ 1,3 mm fora da aresta), «em falta» ≤ 3,8 mm². Consequência medida acima: a gémea dessas peças deixa de ser encontrada pela forma (9/9). Como estas 17 estão colocadas, o efeito é nas **suas gémeas pendentes** (as consultas que partem delas). Decisão do Tiago: refazer esses contornos (editor), ou retirar os overrides, ou ignorar a forma dessas âncoras. [NT: se eram para corrigir o desenho no tabuleiro, o índice de forma não devia ser o alvo.]

### 1.4 Partição por folha e zona (§3 dos critérios; peças colocadas com silhueta)

- céu: S_T = S0001, S0006, S0008, S0010, S0012, S0022, S0024, S0028, S0030, S0032, S0034; S_V = S0005, S0007, S0009, S0011, S0020, S0023, S0027, S0029, S0031, S0033, S0036.
- relva: S_T = S0002, S0004, S0013, S0015, S0017, S0019; S_V = S0003, S0009, S0014, S0016, S0018, S0020.
- montanha/floresta e vale/aldeia: folhas no JSON (`r7_gt.json` → `particao`); n pequeno (16 + 14 e 13 + 13 peças).
- Os pares gémeos de H2 são quase todos **mistos** (uma folha de cada lado: 132/146 no céu, 121/122 na relva): a partição por folha não serve para H2, que fica só como medição (não há afinação de forma nesta ronda).

## 2. Hipóteses (Parte 2; `r7_hipoteses.py`, 319 s; figuras vistas)

| H | resultado | etiqueta |
|---|---|---|
| **H1** âncora mal colocada | P0826 (7,3): `consistency` sem suspeita (3 peças verificadas, 0 impossível / melhor rotação); no seu buraco com `exclude_piece` (m 2, pool 452 + ela): **rank 1, J 0,95, margem 2,10, `alta`**; secção G0066 margem 1,07 (< 1,5: sinal fraco). P0125 (13,63): sem suspeita; **rank 1, J 1,03, margem 1,65, `alta`**; P0954 em 7.º. Nenhuma âncora cumpre os critérios de «suspeita» pelo próprio buraco | **[F]** (não explica os casos) |
| **H2** limiar de forma largo fora do céu | GT nova: **294 pares gémeos entre peças colocadas** (céu 146, montanha 13, vale 13, relva 122; 6 pares da exceção c32\|c33 fora). d1 verdadeiro mediana / p95 / máx.: céu 0,28 / 0,58 / 2,10; montanha 0,39 / 0,58 / 0,58; vale 0,44 / 0,57 / 0,59; relva 0,37 / **0,89** / 1,08. Fração de gémeos ≤ t95: céu 90 % (84–94), montanha 77 % (50–92), vale 77 % (50–92), relva 75 % (66–81). **Não-gémeos da mesma classe abaixo de t95: 0 / 29 872 (céu), 0 / 1 188, 0 / 1 003, 0 / 27 037** (limites superiores 0,01–0,38 %). O limiar não é largo: é apertado para a relva (recall) e os falsos de forma são raríssimos; P1238 (0,477) cai dentro da distribuição dos verdadeiros do vale. Fig. `r7_h2_forma.png` | **[F]** (3.3 não se faz) |
| **H3** imagem vazia fora do céu | 672 peças colocadas com recorte e θ (céu 324, montanha 30, vale 26, relva 226) × 8 células aleatórias da mesma zona (semente 20261108). **AUC**: céu 0,974 (0,969–0,978), montanha 0,960 (0,938–0,982), vale 0,994 (0,985–0,999), relva 0,989 (0,984–0,993) — a imagem **discrimina** em todas as zonas. Mas com o **limiar 50** passam **61 % (59–63) das células aleatórias no céu, 84 % (79–88) na montanha, 71 % (64–76) no vale e 97 % (97–98) na relva**; os positivos passam a 100 %. p90 dos positivos: céu 10,9, montanha 10,0, vale 13,0, relva 16,0. Critério «vazia» (≥ 80 % dos negativos passam): montanha e relva; céu e vale ficam perto. O rótulo «(ceu)» em (33,3)/(35,2) é o *fallback* de `_image_threshold` (zona nunca passada). Fig. `r7_h3_imagem.png` | **[V]** (teste quase vazio; o rótulo é falso) |
| **H3 — calibração por zona (S_T → S_V)** | p90 dos positivos em S_T: céu **10,6** (n 186), relva **16,1** (n 103), montanha 8,2 (n 16), vale 10,2 (n 13). Em S_V: céu cobertura 85,5 % (79–90), negativos que passam 4,7 % (3,6–6,1), AUC 0,980; relva cobertura 95,1 % (90–98), negativos 3,5 %; montanha cobertura 36 % (16–61, n 14) e vale 46 % (23–71, n 13): n insuficiente para fixar um p90 [NT]. **Efeito nas 34 aceites reproduzidas:** 6 têm ΔE > 10,6 (P0923 14,5; P1181 13,5; P1065 13,3; P1132 13,1; P1272 11,6; P0909 11,5: todas nas colunas 59–63, céu de pôr do sol) → perderiam `aceite`; o critério fixado (≤ 2) **falha** | limiares novos **não ativados** [F no critério de efeito] |
| **H4** θ desconhecido infla a concordância | mínimo das 4 rotações baixa o ΔE dos negativos 0,7 (céu) a 1,6 (relva) e dos positivos ≤ 0,14; negativos a passar 50: +1 ponto em todas as zonas; AUC −0,002 a −0,008. 55 das 72 gémeas pendentes têm âncora com `theta_deg` None e **55/55 têm θ por `render.initial_theta`** | **[F]** (não material; corrige-se por coerência) |
| **H5** forma certa, vizinhas incompatíveis | ver §1.2: 2/2 negativos com J 9,14 e 4,56 > T_abs (lados compatíveis; é a tira de imagem das vizinhas que rejeita); 0/42 aceites acima de 2,08 | **[V]** (explica os casos 1 e 2) |
| **H6(a)** pares: ocupação | T0003 (4,63): twin ocupada; (4,64): X e twin ocupadas. T0004 (4,62): twin ocupada; (44,2), (45,7): X ocupada. T0001/T0002/T0005: 9 células livres dos dois lados | **[V]** |
| **H6(b)** pares: 1 rotação vs 4 | ver §2.1 | — |

### 2.1 H6(b): localização conjunta de um par, 1 rotação (chamada atual) vs 4 rotações + forma (`r7_h6b.py`)

- Os 20 pares E-sym A1↔B2 previstos nos critérios **não são medíveis**: a gémea está na fila 47, fora do ficheiro da arte (`rows_with_art [1, 46]`), e `score(X) = dE(A, X) + dE(B, twin(X))` fica inf nas duas variantes (medido: 20/20 inf). GT substituta (declarada): **66 pares gémeos entre peças colocadas** da GT de H2 com arte nas duas células (20 céu, 20 relva, 13 montanha, 13 vale; semente 20261108), cada par localizado como se as duas fossem soltas.

| variante | top-1 | top-3 | top-10 | posição mediana da célula certa (3008) |
|---|---|---|---|---|
| atual (`theta_deg: 0.0`, sem `shape`: 1 rotação arbitrária) | **30/66** (céu 4/20, relva 1/20, montanha 13/13, vale 12/13) | 39/66 | 50/66 | 2 |
| **4 rotações + `shape`** (protótipo EREAL2) | **64/66** (19/20, 19/20, 13/13, 13/13) | 65/66 | 65/66 | 1 |

Montanha/vale saem bem com 1 rotação porque as páginas do legado estão alinhadas com os eixos (θ ≈ 0 por acaso); nas soltas de lote (orientação ao acaso) a chamada atual é um sorteio. Critério «material» (posição mediana ≥ 2× menor ou top-10 ≥ +5/20): **cumprido** [V, n = 66]. Nota: em EREAL2 §4 a localização por célula dava posição mediana 26 nos pares E-sym; aqui 1 em 64/66 porque as duas peças vêm do mesmo scan calibrado e a GT é de células interiores com textura (céu de lote: 19/20).

## 3. Correções (Parte 3)

### 3.1 Validação cruzada gémea/par × encaixe (`query._cross_check`) — feita

Para toda a entrada final de origem `gemeo`/`borda`/`par` com célula e ≥ 1 vizinha montada: `fit.side_costs` das vizinhas contra os lados da candidata na **pose prevista** (cadeia de pose; sem pose → melhor das 4 rotações, declarado `min4`); lado impossível (T↔T, B↔B, F fora da borda, corda acima do corte) ou custo conjunto `J` > `calibration.buraco.t_abs` (2,666) → `encaixe.estado = incompativel`, `aceite` → `ambigua` com `decision_antes_encaixe`, razão legível; `ok` e `nao_testado` registados do mesmo modo. Nunca apaga a proposta; recalculado em todas as execuções (completa e incremental), porque as vizinhas mudam.

**Efeito medido à data de cada proposta (`r7_efeito.py`, `r7_efeito.json`; critério §4.1):**

| conjunto | n | `encaixe` | perdem `aceite` | J máx. |
|---|---|---|---|---|
| colocações por gémea aceites pelo Tiago | 44 (33 listadas `aceite`, 10 `ambigua`, 1 sem entrada) | **ok 42**, `nao_testado` 2 (sem vizinha montada à data: P0147, P1132) | **0** (critério ≤ 2 ✓) | 2,08 |
| gémeas rejeitadas | 2 | **incompatível 2/2** (P1014: «com a vizinha (42,62) P0071: custo 9,14 > T_abs 2,67 (ΔE da tira 85,9)»; P1238: «com a vizinha (35,1) P0638: custo 4,56 > 2,67 (ΔE da tira 40,6)») | P1238 `aceite` → `ambigua`; P1014 já era `ambigua` | — |

[V] no critério fixado (0/44 e 2/2), com a ressalva de que n = 2 negativos só explica, não mede precisão. Pares: células X com X ou twin(X) ocupadas excluídas antes do top-3 (`pair_locate(allowed=…)`), 4 rotações + forma (§2.1); as entradas de T0003/T0004 à data deixariam de propor (4,63)/(4,62) (twin ocupada) — verificável por replay; os 3 pares vivos mantêm as células (todas livres dos dois lados).

### 3.2 Imagem por zona — parcial

Feito: zonas no perfil (`image_zones[z] = {rows, dE_p90, rotulo}`, `PuzzleProfile.zone_of`/`zone_label`, `fit.zone_of(cell, profile)`), zona verdadeira passada a `find_twin` e mostrada na razão; **zona sem `dE_p90` calibrado → «a imagem não decide» → nunca `aceite`** (montanha, vale e relva ficam `null` até haver GT). O 50 do céu mantém-se. **Não feito (critério de efeito falhou):** os p90 por zona medidos (céu 10,6, relva 16,1; montanha/vale n < 20) despromoveriam 6 das 34 aceites reproduzidas (todas certas) → fica como medição e decisão do Tiago.

### 3.3 Limite de forma — não se faz (H2 [F]).

## 4. Velocidade (Parte 4; `r7_tempo.py`, consulta completa na cópia, estado reposto antes de cada variante, 1 corrida cada)

| variante | soltas | gémeas pendentes | passo «gémeas» | «pares» | total | chamadas a `de_cell` | propostas |
|---|---|---|---|---|---|---|---|
| atual (pool de hoje, > 300) | 451 | 72 | 8,9 s | 19,5 s | 38,0 s | 630 | 11 |
| **pool ≤ 300** (lotes 6–8 fora do pool), código atual | 243 | 72 | **341,5 s** | 5,6 s | 350,3 s | **53 825** | 9 |
| pool ≤ 300, `PCTL_MAX_N = 0` | 243 | 72 | **6,5 s** | 5,6 s | 15,4 s | 580 | 9 |
| pool de hoje, `PCTL_MAX_N = 0` | 451 | 72 | 8,9 s | 20,2 s | 33,7 s | 630 | 11 |

- **Causa [V na cópia]:** `twin.PCTL_MAX_N = 300` (twin.py:47, 281–284): com ≤ 300 soltas com recorte, cada gémea pendente renderiza e mede o ΔE de **todas** as soltas (72 × ≈ 243 × 3 renders ≈ 53 000 chamadas) só para o percentil informativo `pctl`, que não entra na decisão. Acima de 300 o bloco é saltado e só as 3 melhores são medidas (≈ 630 chamadas). É uma **mudança de caminho de código dependente do tamanho do pool**, não uma cache a aquecer: não há nenhuma cache de ΔE (as únicas caches por execução são `_Ctx.items` e a arte), e o percentil é o único trabalho que desaparece. Reproduz a sessão do Tiago: lotes 4–5 (184–272 soltas) 202–320 s; lotes 6–7 (336–412) 6–9 s; e no git o texto «pct» está no `fetch.md` até 134 soltas e falta a partir de 487. **52×** aqui (341,5 → 6,5 s).
- **Invariante [V]:** `fetch.json` com e sem percentil: propostas (peça, célula, decisão, d1_mm, margin, dE) e `suprimidas` **idênticas** nas duas comparações (pool ≤ 300: 9 = 9; pool de hoje: 11 = 11; 0 diferenças).
- **Processos Python em segundo plano nesta máquina** durante as medições: 3 (`python3.13.exe`, 28–63 MB cada; extensões do editor) — sem efeito mensurável (a variante lenta e a rápida correram no mesmo ambiente). O CPU em repouso do portátil do Tiago é de outra sessão. O ficheiro `projects/alpes/logs/servidor-20261108.log` não está nesta máquina (ignorado pelo git): a correlação com os números do Tiago fica **[V na cópia, NT no portátil]** até ele enviar as linhas `consulta`.
- **Correção:** `find_twin(pctl=False)` por omissão (o percentil fica disponível para diagnóstico com `pctl=True`); nada muda nos limiares; a razão «imagem consistente» perde «, pct x %» (campo `image.pctl` = None). O passo «pares» (19,5 s com 451 soltas: `find_twin` de cada solta contra todas as outras, O(N²)) passa a ser o maior; não se otimiza nesta ronda (medido, declarado).
- `GET /api/suspeitas` (11,9 s no arranque) e POST de confirmação (3,5 s): §4.1.

### 4.1 Servidor na cópia

(preenchido depois da implementação)

## 5. Continuidade (Parte 5)

- `python -m src.fit --project projects/alpes --relatorio` (2026-11-08, antes desta ronda mexer em código): **n = 38** confirmações (38 com ≥ 2 vizinhas, **1 fora do céu**), 0 rejeições; top-1 38/38 (Wilson 91–100 %); por zona céu 37, montanha/floresta 1; por vizinhas 2: 25, 3: 12, 4: 1; todas `alta`. Limiar do §15.6 (n ≥ 60, ≥ 40 com ≥ 2 vizinhas, casos fora do céu): **não atingido** (faltam 22 confirmações no total, 15 com ≥ 2 vizinhas, e a GT fora do céu tem n = 1). Contador `alta`: 38/0/38, janela ativa.
- `python -m src.overrides --project projects/alpes --pares`: 17 contornos manuais (§1.3); **5 poses manuais** (todas céu): |d| média 0,77 mm IC95 [0,51, 1,02], Δx +0,53 [+0,09, +0,97], Δy +0,26 [−0,32, +0,83]; por direção n = 1–3 (sem IC útil). Nada calibrado.
