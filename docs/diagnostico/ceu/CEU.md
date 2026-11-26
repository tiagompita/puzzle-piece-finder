# Céu: porque há tão poucas sugestões? (medição, 2026-11-26)

Só medição, numa cópia de `projects/alpes` (`tools/diagnostico/gui/guarda.py`, `copytree`). Nada escrito em `projects/alpes`, `src/`, `tools/`, `tests/`. Estado medido: 1433 peças, 699 colocadas, `fit_version m11-1`, calibração do perfil (erosão 0,60 mm, corte de corda 2×, `t_abs` 2,6656, `margin_min` 1,5). Scripts no scratchpad da sessão (fora do repositório). Rótulos: [V] verificado com número, [NT] não testado, [F] testado e falha.

## 0. Resposta curta

1. **A falta de sugestões é estrutural, não um defeito do código** [V] para o que o código decide: nas 78 células vazias do céu com vizinha, 59 têm 1 vizinha e a regra do programa nunca dá «alta» com 1 vizinha (`fit.confidence`); só 3 holes são `alta`, e a «Vai buscar» mostra 1.
2. **Mas há dois achados que o contexto não previa:**
   - O ranking acerta muito quando a peça verdadeira está no pool (leave-one-out, 1 vizinha: top-3 94 % com peças digitalizadas soltas, 97,5 % no total) [V]. O critério fixado antes (top-3 ≥ 80 % com 1 vizinha) **cumpre-se** [V], **condicionado a a peça estar no pool**.
   - Só que os buracos reais comportam-se como se a peça verdadeira estivesse **no pool em cerca de metade dos casos ou menos** [V nos três estimadores, estimativa grosseira, [NT] fisicamente]: margens e custos reais piores do que no leave-one-out; 17 quadrados 2×2 entre soltas contra 328 esperados com o pool completo; 3 de 14 gémeas de peças colocadas com gémea vazia no céu encontradas no pool. Isto contradiz «quase todas as peças do céu digitalizadas», ou então muitas das ~513 soltas «de cor céu» não são das células vazias do céu (hipóteses em §5).
3. **Recomendação:** ver §6. Resumo: mostrar como «a verificar» só as células com 1 vizinha, margem ≥ 1,5 e `d1 ≤ t_abs` (hoje 15 buracos; precisão prevista 91–99 % para π 0,25–0,75, nunca testada fisicamente); não mostrar top-3 em todas as células de 1 vizinha (24–71 % de verdadeira no top-3 para π 0,25–0,75) nem as `media` de 2+ vizinhas (7–41 %); e perceber, com uma contagem física, quantas peças do céu faltam mesmo digitalizar.

## 1. Inventário

**O programa não tem zona por peça solta** [V]: `zone_of` (`src/fit.py`, `src/profile.py`) e `profile.zone_of(l, c)` são por **célula**; `query.py`, `montar.py` e `server.py` usam a zona da célula da gémea ou da proposta. Proxy usado, explícito: o **«zona provável» de `tools/diagnostico/grupos_soltos/loose.py`** (kNN, k = 15, sobre a mediana Lab das tiras, treinado nas colocadas com zona conhecida), mais um segundo proxy de cor (mean_lab, kNN k = 7) e um terceiro (célula da arte com cor média mais próxima, −5 L\*). Validação do kNN mean_lab em leave-one-out nas 706 colocadas com cor: céu detetado 347/353 (recall 98,3 %), 9 falsos céu em 353 não-céu (precisão 97,5 %) [V]; o do arte-proxy: 296/353 céu, 0 falsos [V]. **Limite do proxy:** o treino só tem 56 colocadas de montanha/vale, por isso peças claras de montanha com nuvem tendem a sair «céu» [NT].

| estado | n | notas |
|---|---|---|
| `colocada` | 699 | céu 353 (233 `legado_scan`, 120 `log`), relva 290, montanha 30, vale 26 |
| `solta` | 523 | + 1 `emparelhada` = **524 no pool** de `loose_pieces()` |
| `em_seccao` | 205 | **132 duplicadas (`same_as`)** + **73 não duplicadas**; fora do pool |
| `descartada` | 5 | P0053, P0058, P0059, P0064, P0065 (nenhuma céu) |
| total | 1433 | |

- `same_as`: 132, **todas** em `em_seccao` (131 apontam para uma `colocada`, 1 para outra `em_seccao`) [V]. Das 132: céu 65 (kNN) ou 63 (arte).
- **Do céu, por colocar e não duplicadas** (proxy kNN / proxy arte): soltas 514 / 426; em secção não duplicadas 51 / 32; **total 565 / 458**; 5 descartadas fora do céu.
- **Contra as 543 células vazias do céu:** diferença 543 − 458 = **85 no máximo em falta** (proxy mais conservador) ou **≤ 0** (kNN, mais soltas do que células). [V como conta; [NT] como verdade física.]
- **Duplicados por forma dentro do pool céu** (`shape.free_dist`; re-scan da mesma peça 0,27 mm, mínimo entre peças distintas colocadas 0,52 mm, nenhum par distinto < 0,40): 5 soltas de cor céu com d < 0,40 a uma colocada do céu (20 com d < 0,60); 1 par solta-solta com d < 0,40 (16 com d < 0,60) [V]. Isto reduz ligeiramente as únicas.
- **Contradição com a contagem simples:** ver §5 (π).

## 2. Frente atual

`rank_all` completo na cópia (a frio: 198 s, 738 tiras; 524 soltas; 203 buracos no total; tabuleiro todo). Dos 203 buracos, **78 estão no céu** (não 79: a célula (6,60) tem 1 vizinha, P0099, que só está `posicao_conhecida` e sem pose, por isso `hole_queries` não a conta como vizinha [V]).

| n.º vizinhas | alta | média | sem | total |
|---|---|---|---|---|
| 1 | 0 (nunca) | 15 | 44 | 59 |
| 2 | 0 | 12 | 1 | 13 |
| 3 | 2 | 2 | 0 | 4 |
| 4 | 1 | 0 | 1 | 2 |
| **total** | **3** | **29** | **46** | **78** |

**Motivo dos 46 «sem»** [V]: 44 de 1 vizinha: **margem < `margin_min` 1,5** com candidata única improvável (`n_finite` mediana 478 de 524: o filtro de tipo/cordas quase não corta, o que decide é o custo); os 2 restantes (m = 2 e m = 4): **`d1 > t_abs`** (2,6656). Nenhum «sem» por «nenhuma finita» nem «sem 2.ª candidata».

**«Alta» → «Vai buscar»:** das 3 `alta` só **1 sobrevive** a `alta_suggestions` (a candidata 1 tem de coincidir com a afetação conjunta): (9,2) P1036 fica; (6,15) tem candidata P1342 mas a afetação dá P1100; (3,47) tem P0103 e a afetação dá P1372 [V]. A afetação gananciosa tira 2 de 3.

**O que o «Vai buscar» mostra** [V por leitura do código]: `montar.fila` recebe `buracos_alta` (só `alta` coerente com a afetação, `fit.alta_suggestions`) mais as propostas de gémea/borda/par; `média`/`sem` não entram. **O que a GUI nova mostra ao tocar numa célula vazia com `média`:** o painel do lugar (`novo.js` ~838–853) só usa `propostas` (as entradas do `fetch` para essa célula); sem proposta diz «Sem sugestão por agora.». A `média` só aparece na página «Buracos» da GUI antiga (`/`, `holes.js`; `media` com 1 vizinha rotulada «baixa (1 vizinha)»), sem ligação a partir da GUI nova [V, leitura].

## 3. Leave-one-out (precisão)

Método: para cada uma das 353 colocadas do céu, tira-se a peça da célula (`hole_queries(exclude_piece=)`), junta-se ao pool das 524 soltas (pool de 525), corre-se `rank_hole` na mesma pipeline (erosão, cortes, `t_abs`), com as outras 352 colocadas excluídas (`exclude=`). Em memória, nada gravado. Como só 3 peças ficam naturalmente com 1 vizinha (326 com ≥ 3), mede-se também com **subconjuntos de vizinhas** (cada vizinha sozinha: m = 1; cada par: m = 2); o custo é a média dos lados e o filtro é o mesmo, por isso as amostras são fiéis ao caso real, **mas correlacionadas por peça**; os IC por peça (n = peças) estão na tabela. Critério fixado antes: top-3 ≥ 80 % com 1 vizinha. «Presente» = a peça verdadeira está no pool.

| caso | n | top-1 | top-3 | top-5 |
|---|---|---|---|---|
| natural, m ≥ 3 | 326 | 0,997 [0,98; 1,00] | 0,997 | 0,997 |
| natural, m = 2 | 24 | 1,00 [0,86; 1,00] | 1,00 | 1,00 |
| natural, m = 1 | 3 | 3/3 | 3/3 | 3/3 |
| m = 1 (subconjuntos), todas | 1207 / 353 peças | 0,938 [0,91; 0,96] por peça | **0,975 [0,95; 0,99]** | 0,984 |
| m = 1, só peças `log` (digitalizadas soltas, mais realista) | 384 / 120 peças | 0,862 [0,78; 0,91] | **0,944 [0,88; 0,97]** | 0,966 |
| m = 1, só `legado_scan` (mesma folha das vizinhas) | 823 / 233 peças | 0,975 [0,94; 0,99] | 0,990 [0,97; 1,00] | 0,993 |
| m = 2 (subconjuntos), todas | 1536 | 0,995 | 0,999 | 0,999 |

[V] Critério **cumprido**: top-3 com 1 vizinha 94–97,5 %, com o limite inferior do IC (0,88 no caso mais fraco) acima de 0,80. Por confiança com 1 vizinha: `media` n = 664 amostras, top-1 100 %; `sem` n = 543, top-1 86,2 %, top-3 94,5 %. Com m = 2: `alta` 1161 amostras, 1161 certas. Efeito de fonte: a peça digitalizada solta (`log`) perde ~11 pontos de top-1 a 1 vizinha contra a do legado (vizinha e candidata na mesma folha) [V; fotometria e orla entre folhas, causa [NT]]. Filtros: 1 peça de 353 perde a verdadeira por «tipo» (J = ∞) no caso natural; 1 em 1207 a 1 vizinha [V].

### 3.1 O que o leave-one-out não diz: peça ausente

O critério mede-se **com a peça no pool**. No caso real a peça de uma célula pode não estar digitalizada. Simulação com a verdadeira também excluída (variante «ausente», mesmos buracos): com 1 vizinha, `media` aparece em 1,0 % dos casos (99 % são `sem`); com 2 vizinhas, `media` em 30,9 %, `alta` em 0,3 %.

Por isso a precisão real depende de π = P(peça no pool). Estimadores [V a medição; π é estimativa, [NT] fisicamente]:

| estimador | π |
|---|---|
| fração de `media` com 1 vizinha: 25,4 % atual (15/59) contra 55 % presente / 1 % ausente | 0,45 (Wilson de 15/59: 0,28–0,66) |
| margens atuais (m = 1 mediana 1,27; m = 2 mediana 1,04) contra leave-one-out presente (2,49; 3,03) | baixo, de ordem 0,5 ou menos |
| quadrados 2×2 entre soltas: 17 observados contra 464 blocos 2×2 vazios × 0,706 (recall medido) = 328 esperados | **0,48** (raiz quarta) |
| ligações melhor-mútuas: 524 contra 856 esperadas | ≤ 0,78 (inclui ligações falsas) |
| gémea: das colocadas com gémea vazia **no céu** (n = 14) só 3 têm uma solta com d < 0,50; entre colocadas com as duas gémeas colocadas, 82 % têm d < 0,50 (91 % < 0,60; 309 pares) | **0,21–0,23** (Wilson de 3/14: 0,08–0,48) |
| log antigo: 6 `media` confirmadas contra 17 rejeitadas no céu (todas m ≥ 2) | consistente com π ≈ 0,5 nessa data (a 8 de novembro o pool era menor) |

Intervalo prático **π ∈ [0,25; 0,75]**, central 0,5.

### 3.2 Precisão prevista por regra, em função de π

Peças do `log` como «presente» (mais realista); «ausente» da simulação acima. `P(mostra)` é a fração dos casos presentes que a regra mostra.

| regra (m = 1, `d1 ≤ t_abs`) | buracos atuais | P(mostra \| presente) | precisão top-1/top-3 π = 0,25 | π = 0,5 | π = 0,75 |
|---|---|---|---|---|---|
| margem ≥ 1,5 (hoje «média») | 15 | 0,31 | 0,91 / 0,91 | 0,97 / 0,97 | 0,99 / 0,99 |
| margem ≥ 1,3 | 25 | 0,46 | 0,81 / 0,82 | 0,92 / 0,93 | 0,97 / 0,98 |
| margem ≥ 1,2 | 36 | 0,53 | 0,68 / 0,69 | 0,85 / 0,86 | 0,93 / 0,94 |
| margem ≥ 1,1 | 44 | 0,65 | 0,50 / 0,52 | 0,72 / 0,75 | 0,84 / 0,88 |
| margem ≥ 1,0 (todas) | 59 | 0,84 | 0,33 / 0,37 | 0,55 / 0,62 | 0,71 / 0,80 |
| top-3 sempre (sem regra) | 59 | 1,00 | verdadeira no top-3: 0,24 | 0,47 | 0,71 |

Com m = 2: `alta` mantém ≥ 0,99 de precisão para qualquer π; `media` (12 buracos atuais) fica em 0,07 / 0,19 / 0,41 (π 0,25 / 0,5 / 0,75) e 0,97 só com π = 1; confere com o 6/23 do log.

## 4. Grupos soltos do céu

Critério dos quadrados 2×2 (`tools/diagnostico/grupos_soltos/loose.py`, código copiado sem alterar): ligações melhor-mútuas entre lados T/B de soltas, 4 ligações coerentes num 2×2, margem = a mais fraca.

**Hoje, entre as 524 soltas (513 de cor céu)** [V]: 531 ligações melhor-mútuas (524 em peças de cor céu), das quais 413 com margem ≥ 1,05, 196 com ≥ 1,2, 35 com ≥ 1,5; **17 quadrados** (todos com margem ≥ 1,0; 7 com ≥ 1,05), todos de cor céu e **os mesmos 17 que o Tiago já testou fisicamente (17/17, Wilson 0,82–1,00)**; 13 grupos (11 de 4 peças, 1 de 7, 1 de 11); 477 das 513 soltas céu têm ≥ 1 ligação melhor-mútua, mas só 62 estão num quadrado. Descer a margem não acrescenta quadrados (já são todos com margem ≥ 1,0).

**O que impede de encontrar mais:** (1) o pool tem pouco do céu **vizinho**: com o pool completo esperavam-se 328 quadrados (recall medido 0,706 × 464 blocos vazios); observam-se 17, o que dá π ≈ 0,48 (§3.1); (2) mesmo com as 4 peças presentes só 70,6 % dos blocos dão um quadrado coerente (173/245 [0,65; 0,76]; 166/245 com margem ≥ 1,05); (3) o método só usa lados T/B (nenhuma das 513 soltas céu tem F: são interiores).

**Precisão com pares de colocadas vizinhas (finge soltas)**, pool = 524 soltas + as 2 (ou 4) peças, 597 pares vizinhos T/B-T/B no céu:

| medida | resultado |
|---|---|
| ligação melhor-mútua verdadeira | 515/597 = 0,863 [0,83; 0,89] (`legado` 0,908 [0,88; 0,93]; `log` 0,762 [0,70; 0,82]) |
| a verdadeira é a 1.ª de A | 537/597 = 0,899 [0,87; 0,92] |
| verdadeira no top-3 de A | 579/597 = 0,970 [0,95; 0,98]; no top-3 de A e de B: 565/597 = 0,946 [0,93; 0,96] |
| ligação com margem ≥ 1,05 / 1,2 | 502/542 = 0,926 [0,90; 0,95] / 432/439 = 0,984 [0,97; 0,99] |
| quadrado 2×2 (4 ligações melhor-mútuas) | 173/245 = 0,706 [0,65; 0,76] |

Estimativa [NT, inferida de π ≈ 0,5]: das 196 ligações atuais com margem ≥ 1,2 esperavam-se ~165 verdadeiras (196 observadas): precisão incondicional da ordem de 0,8; abaixo de 1,05 as ligações isoladas serão em boa parte falsas (524 observadas contra ≤ ~200 verdadeiras esperadas).

## 5. Anomalias

1. **Peça ausente, não defeito do filtro** [V]: o leave-one-out mostra que o filtro (tipo, cordas, F) e o pool corretos devolvem a peça no top-3 quase sempre (§3). Nenhuma peça do céu é excluída do pool por zona (o pool não tem zona) [V].
2. **π baixo contra «quase todas digitalizadas»** [V nos 3 estimadores; causa [NT]]: hipóteses que a medição não separa: (a) muitas das ~513 soltas de cor céu são de filas 15+ (nuvem/céu na montanha; o proxy tem só 56 colocadas de montanha/vale); (b) duplicados não marcados (`same_as`) — só ≥ 5–20 por forma; (c) peças do céu já montadas fisicamente mas não marcadas no programa (as 543 «vazias» incluiriam células já cheias; a foto de ocupação é de 2026-11-01); (d) peças do céu por digitalizar. A contagem física (ou uma foto de ocupação nova do céu) separa (c) de (d).
3. **Afetação conjunta suprime 2 das 3 `alta`** (§2) [V]; é o desenho de M11_CRITERIOS §8, mas explica a quase ausência de «alta» na «Vai buscar».
4. **(6,60) fora do ranking** [V]: vizinha P0099 `posicao_conhecida` sem pose; `hole_queries` ignora vizinhas sem pose.
5. **As 73 não duplicadas em secção (51 de cor céu) fora do pool não explicam nada** [V]: com elas no pool, os 78 buracos têm exatamente as mesmas confianças; só 1 buraco passa a ter uma delas como candidata 1.
6. **Penalização entre folhas** [V]: a 1 vizinha, `log` perde 11 pontos de top-1 contra `legado` (0,862 contra 0,975 por peça). O ranking real (soltas digitalizadas em lotes) está mais perto do `log`.
7. **Restringir o pool às soltas de cor céu não melhora** [F]: top-3 a 1 vizinha 0,966 contra 0,975 (a verdadeira sai do pool em 12 de 1207 casos).
8. **Defeito de medição conhecido:** `rank_all` a frio na cópia levou 198 s (a cópia não trazia a cache de tiras utilizável: `em_cache` 0 e 738 tiras calculadas); sem relação com o resultado.

## 6. Opções

Precisões previstas no §3.2 (π ∈ [0,25; 0,75]); todas [NT] fisicamente fora do que o log já tem.

| opção | o que o Tiago vê | n atual | precisão prevista | risco |
|---|---|---|---|---|
| (a) manter só `alta` | 1 sugestão (3 `alta` − 2 por afetação) | 1 | ≥ 0,99 (log: 58/58 confirmadas, Wilson 0,94–1,00) | quase nada para fazer |
| (b) «a verificar» com top-3 nas células de 1 vizinha, margem ≥ 1,5 e `d1 ≤ t_abs` (as 15 `media` de 1 vizinha) | 15 células, cada uma com 3 candidatas, a 1.ª quase sempre a certa | 15 | 0,91 / 0,97 / 0,99 (π 0,25 / 0,5 / 0,75); top-1 = top-3 | nunca verificadas fisicamente a 1 vizinha; precisão alta porque a peça ausente quase nunca dá margem ≥ 1,5 |
| (b') o mesmo com margem ≥ 1,3 / ≥ 1,2 | 25 / 36 células | 25 / 36 | 0,81–0,97 / 0,68–0,93 | mais ruído se π < 0,5 |
| (b'') top-3 em todas as 59 células de 1 vizinha | 59 listas de 3 | 59 | verdadeira no top-3 em 0,24 / 0,47 / 0,71 (0,94 só com a peça presente) | **falha o critério de 80 %** com o π real [F] |
| (b''') incluir as `media` de 2 vizinhas | 12 células | 12 | 0,07 / 0,19 / 0,41 | **não recomendado** (log 6/23) [F] |
| (c) priorizar grupos soltos | 17 quadrados (todos já testados) + pares com margem ≥ 1,2 | 196 pares | quadrados 17/17 [0,82; 1,00]; pares ≥ 1,2: condicional 0,984, incondicional ~0,8 [NT] | os quadrados estão esgotados; mais grupos exigem mais peças no pool (π) |
| (d1) contagem física do céu (ou foto de ocupação do céu) | número real de peças em falta | — | resolve o π | trabalho do Tiago |
| (d2) mostrar «peça provavelmente por digitalizar» nos buracos com `d1` alto | informação em vez de ruído | 46 `sem` | — | só diz o que o ranking já sabe |

**Recomendação** (por esta ordem): (1) **(b)** com margem ≥ 1,5, rotulada «a verificar», como hoje se faz com a página «Buracos», mas ligada à GUI nova e com o top-3 (as 15 células atuais), medindo as confirmações no log; é o único passo com precisão prevista ≥ 0,9 em todo o intervalo de π e nunca foi testado fisicamente, por isso o log decide se se alarga a 1,3; (2) **(d1)** antes de qualquer mudança de código: se faltam muitas peças do céu, nenhuma regra cria sugestões que não existem, e o π muda tudo; (3) não mostrar top-3 em todas as células de 1 vizinha nem as `media` de 2+ vizinhas; (4) grupos: manter os quadrados e, depois do (d1), testar fisicamente 20–30 pares com margem ≥ 1,2 para medir a precisão incondicional (ver [NT] do §4). Alterar o código (mostrar média de 1 vizinha, ligar a GUI nova, afetação conjunta) é trabalho do implementer, sobre esta medição.

## Imagens de prova

Peça verdadeira marcada a verde, cada painel = vizinha(s) + candidata no lugar do buraco, rodadas à pose prevista; `J` = custo conjunto. Todas de células do céu em leave-one-out com 1 vizinha, peças `log`.

- `top3_01_certo_top1.jpg`, `top3_02_certo_top1.jpg`: top-1 certo, `media`, margens 6,36 e 1,89.
- `top3_03_certo_top2ou3.jpg`, `top3_04_certo_top2ou3.jpg`: certa em 2.º, `sem`, margens 1,09 e 1,11 (as três candidatas parecem possíveis a olho: peças pálidas de nuvem).
- `top3_05_errado.jpg`, `top3_06_errado.jpg`, `top3_07_errado.jpg`: a verdadeira fora do top-3 (posições 19, 34, 9), todas `sem`, margens 1,01–1,09: peças pálidas, sem textura, com muitas candidatas parecidas.
- `top3_atual_01_media_m1.jpg`, `top3_atual_02_media_m1.jpg`: o que o Tiago veria hoje em duas das 15 células `media` de 1 vizinha (sem verdade conhecida).
