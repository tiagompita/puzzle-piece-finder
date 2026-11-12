# Verificação de um grupo solto largado junto ao montado: junções, falsos «encaixa» e falsos «não encaixa»

_2026-11-12. Só leitura do programa: `src/` e `projects/alpes` não foram alterados; a medição corre numa **cópia** do projeto (a árvore de trabalho de hoje). Script: `tools/diagnostico/fit/grupos_juncoes.py`. Critérios abaixo escritos e commitados **antes** de correr a medição._

## 1. Critérios (fixados antes de olhar para resultados)

**Pergunta.** Ao largar um grupo solto de peças encostado a peças colocadas (F4c do ESPEC §4.9), o programa verifica as junções e responde «encaixa», «não encaixa» ou «não sei». Com que taxa de erro, em função do número de junções e da zona?

**Grupos de teste.** Blocos retangulares de peças **colocadas** (2×2 = 4, 2×3 e 3×2 = 6, 3×3 = 9 células), todas com forma, pose e 4 lados mapeados (`board_dirs`). Escolhidos sem peças partilhadas dentro de cada tamanho, por ordem aleatória com semente fixa (0). O bloco é retirado do montado (as suas células ficam livres) e tratado como grupo solto: o que mexe é só a posição.

**Posições.**
- **Certa:** a rotação 0 e a translação 0 (onde o bloco está).
- **Gémea:** rotação 180° e as células (l, c) → (L+1−l, C+1−c) (L, C = linhas e colunas da grelha). Tratada à parte; encaixa por forma por construção do corte.
- **Erradas:** todas as outras (rotação 0–3 × translação) em que **todas** as células do grupo estão livres (`Board.occupied` falso: célula de foto conta como livre; dentro da grelha) e há **pelo menos uma junção** com uma peça colocada (fronteira do montado). Inclui deslocar o bloco uma célula ao longo da fronteira e sobre o seu lugar original.

**Junção.** Lado de uma peça do grupo que olha, na posição testada, para uma célula ocupada por uma peça **colocada** (fora do bloco) com forma e pose. Peças vizinhas sem forma/pose, ou células ocupadas sem peça (dica do Tiago, legado sem peça), não são junções. O nº de junções n_j conta as junções existentes, testáveis ou não.

**Custo de uma junção.** `fit.side_costs` (o mesmo do molde do buraco, com a calibração `calibration.buraco` do `puzzle.json`: erosão, corte de corda, `t_abs`): a vizinha entra como `HoleSide` (o lado dela que olha o grupo, erodido, com a sua tira Lab), o lado do grupo que olha a vizinha é o candidato. Custo infinito por «impossível» = tipo incompatível (T com T, B com B, F com qualquer) ou corda acima do corte (`hard`); infinito por falta de imagem (NaN) = junção **não testada**.

**Regra F do grupo.** Em cada célula do grupo, o lado que olha para fora da grelha tem de ser F e só esse (`profile.flat_directions`, mesma regra de `_f_mask`). Violação = impossível.

**Resposta (critério A, o principal).** Seja J a média dos custos das junções testadas.
- **não encaixa:** alguma junção impossível, ou a regra F violada, ou J > `t_abs`.
- **encaixa:** nenhuma junção impossível, regra F cumprida, **todas** as junções testadas (custo finito), n_j ≥ 1 e J ≤ `t_abs`.
- **não sei:** o resto (há junção não testada e J ≤ `t_abs`, ou nenhuma junção testável).

**Critério B (mais estrito, registado em paralelo).** «encaixa» exige também o **máximo** do custo de uma junção ≤ `t_abs`; «não encaixa» é igual a A. Os limiares são os que já existem (`t_abs` calibrado no molde do buraco, para a média de um buraco); **nenhum limiar novo**.

**Taxas.**
- **Falso «encaixa»** = fração das posições **erradas** com resposta «encaixa». **Falso «não encaixa»** = fração das posições **certas** com resposta «não encaixa»; a fração de «não sei» também se reporta nos dois.
- Por n_j ∈ {1, 2, 3, ≥ 4} e por zona (`fit.zone_of` com o perfil: céu / montanha-floresta / vale-aldeia / relva).
- A zona é a do **bloco** (linha mediana das suas células) para ambas as taxas; para as erradas há também a tabela pela zona do lugar testado.
- Posição certa com n_j natural = 1, 2, 3: **subconjuntos** de junções do lugar certo (todos os de tamanho k, ou 60 sorteados com semente fixa, se forem mais), para simular o grupo largado junto de poucas peças. A fração por bloco é a média dos subconjuntos; ≥ 4 = o lugar certo inteiro com n_j ≥ 4.
- Intervalos de Wilson 95 % (`fit.wilson`). Nas certas, n = nº de blocos (contagem fracionária nos subconjuntos, aproximada). Nas erradas, n = nº de posições, **que não são independentes** (as mesmas peças em posições vizinhas): o intervalo é otimista, por isso reporta-se também o nº de blocos com ≥ 1 falso «encaixa».

**Mínimo de junções.** Propõe-se o menor n_j a partir do qual, nos dados, o limite superior de Wilson do falso «encaixa» fica abaixo de 5 % **e** o falso «não encaixa» fica abaixo de 10 % no céu; **estes 5 % e 10 % não saem de dados: são os valores que o Tiago ou a regra do «quase certo» (§8.3 do ESPEC) terão de aceitar ou mudar.** Se nenhum n_j cumprir, diz-se.

**Limites assumidos à partida.**
- O GT são as posições do tabuleiro (colocadas): só o céu tem confirmações físicas do molde (38/38, 37 no céu); relva e vale não têm GT físico, só as posições automáticas do legado.
- Um bloco no meio do montado tem a fronteira cheia; blocos junto ao bordo têm menos junções certas.
- A 180° o corte repete-se: a posição gémea fica de fora das erradas.

## 2. Resultados (medição de 2026-11-12, cópia de `projects/alpes` com as alterações locais do Tiago)

Reproduz-se com `PPF_SCRATCH=<dir> .venv/Scripts/python.exe tools/diagnostico/fit/grupos_juncoes.py <cópia> <raw.json>` e `grupos_juncoes_tabelas.py <raw.json> <resumo.json>`. Saída completa: [`grupos_juncoes_tabelas.txt`](grupos_juncoes_tabelas.txt), resumo [`grupos_juncoes.json`](grupos_juncoes.json). Calibração lida do `puzzle.json`: erosão 0,60 mm, corte de corda 2×, `t_abs` 2,6656.

**Amostra [V].** 696 peças colocadas com forma e pose; 115 blocos sem peças partilhadas dentro de cada tamanho (50 de 4, 40 de 6, 25 de 9); **63 do céu e 52 da relva, nenhum da montanha nem do vale** (não há blocos colocados nessas zonas). 86 840 posições erradas com ≥ 1 junção (755 por bloco em média) e 115 certas.

**Validação do código de rotação e da posição gémea [V].**
- 0 inconsistências geométricas em 20 blocos × 4 rotações (deslocamento rodado = passo da direção rodada).
- 1 922 casos de «peça (ou bloco pequeno) X posta a 180° no lugar da sua gémea Y colocada, com Y retirada»: o custo **só de forma** por junção é p50 0,54 / p90 0,76, igual ao das junções certas (0,53 / 0,73), contra 1,49 / 2,38 (mediana / p90 da média por posição) nas posições erradas sem junção impossível. A diferença está na imagem: dE por junção p50 53,8 (gémeas) contra 6,4 (certas).
- A primeira versão da medição já mostrava custos de ≈ 6 nas gémeas: era a imagem, não a forma, e por isso se separaram os dois custos.

### 2.1 Posições erradas: falso «encaixa»

Por n_j (todas as zonas). Entre parênteses, nº de blocos (em 115) com ≥ 1 falso «encaixa».

| n_j | n posições | A: falsos | A: taxa [Wilson 95 %] (blocos) | B: falsos | B: taxa [Wilson] (blocos) |
|---|---|---|---|---|---|
| 1 | 16 768 | 68 | 0,4 % [0,3–0,5] (28) | 68 | 0,4 % [0,3–0,5] (28) |
| 2 | 41 809 | 87 | 0,2 % [0,2–0,3] (24) | 33 | 0,1 % [0,1–0,1] (15) |
| 3 | 23 530 | 14 | 0,1 % [0,0–0,1] (10) | 5 | 0,0 % [0,0–0,0] (3) |
| ≥ 4 | 4 733 | 3 | 0,1 % [0,0–0,2] (3) | 0 | 0,0 % [0,0–0,1] (0) |

Por zona do bloco (a das peças do grupo). Montanha e vale: **n = 0, sem dados**.

| zona (blocos) | n_j | n posições | A: falsos [Wilson] (blocos) | B: falsos [Wilson] (blocos) |
|---|---|---|---|---|
| céu (63) | 1 | 9 266 | 54 — 0,6 % [0,4–0,8] (18) | 54 — 0,6 % (18) |
| céu | 2 | 23 565 | 73 — 0,3 % [0,2–0,4] (15) | 28 — 0,1 % [0,1–0,2] (10) |
| céu | 3 | 12 248 | 14 — 0,1 % [0,1–0,2] (10) | 5 — 0,0 % [0,0–0,1] (3) |
| céu | ≥ 4 | 2 543 | 3 — 0,1 % [0,0–0,3] (3) | 0 — [0,0–0,2] (0) |
| relva (52) | 1 | 7 502 | 14 — 0,2 % [0,1–0,3] (10) | 14 — 0,2 % (10) |
| relva | 2 | 18 244 | 14 — 0,1 % [0,0–0,1] (9) | 5 — 0,0 % [0,0–0,1] (5) |
| relva | 3 | 11 282 | 0 — [0,0–0,0] (0) | 0 (0) |
| relva | ≥ 4 | 2 190 | 0 — [0,0–0,2] (0) | 0 (0) |

**Negativos difíceis** (posições erradas que cobrem o lugar original do bloco: deslocá-lo de 1 célula, ou rodá-lo no sítio; n pequeno):

| n_j | n | A: falsos [Wilson] | B: falsos [Wilson] |
|---|---|---|---|
| 1 | 28 | 4 — 14,3 % [5,7–31,5] | 4 — 14,3 % [5,7–31,5] |
| 2 | 58 | 2 — 3,4 % [1,0–11,7] | 1 — 1,7 % [0,3–9,1] |
| 3 | 28 | 0 — [0,0–12,1] | 0 — [0,0–12,1] |
| ≥ 4 | 307 | 2 — 0,7 % [0,2–2,3] | 0 — [0,0–1,2] |

Sem rodar (r = 0, o que o Tiago faria se arrastasse o grupo sem o rodar): A 0,3 / 0,2 / 0,1 / 0,0 % (n_j = 1 / 2 / 3 / ≥ 4; n = 4 186 / 10 460 / 5 876 / 1 123), sem diferença relevante.

**Porque é que as erradas falham [V].** A junção é «impossível» (T-T, B-B, F, corda acima do corte) em 64 % das posições com n_j = 1, 81 % com 2, 90 % com 3 e 97 % com ≥ 4; com a regra F do grupo, 76 / 87 / 94 / 98 %. O resto é custo acima de `t_abs`. Só 12,8 % das erradas passam sem junção impossível nem F violada.

Por zona do lugar testado (A), falsos «encaixa» em n posições: céu 127 / 33 243, montanha 1 / 13 240, vale 23 / 18 397, relva 21 / 21 960.

### 2.2 Posições certas: falso «não encaixa» e «não sei»

n_j natural dos 115 blocos: 5 a 12 (mediana 8). Para n_j = 1 a 4 simulam-se grupos largados junto de poucas peças com **subconjuntos** das junções do lugar certo (todos, ou 60 sorteados, semente 0); «≥ 5» = o lugar certo inteiro. Contagem fracionária por bloco, Wilson aproximado. As colunas A e B têm o mesmo «não encaixa» (só o «encaixa» difere).

| zona (blocos) | n_j | falso «não encaixa» [Wilson] | A: «não sei» | B: «não sei» |
|---|---|---|---|---|
| todas (115) | 1 | 10,1 % [5,8–17,0] | 0 % | 0 % |
| todas | 2 | 7,3 % [3,8–13,6] | 0 % | 10,3 % |
| todas | 3 | 6,3 % [3,1–12,3] | 0 % | 17,3 % |
| todas | 4 | 5,1 % [2,3–10,7] | 0 % | 23,4 % |
| todas | ≥ 5 (natural) | 1,7 % [0,5–6,1] (2 blocos) | 0 % | 35,7 % |
| **céu (63)** | 1 | 1,7 % [0,3–8,7] | 0 % | 0 % |
| céu | 2 | 1,7 % [0,3–8,6] | 0 % | 0 % |
| céu | 3 | 1,6 % [0,3–8,5] | 0 % | 0 % |
| céu | 4 | 1,6 % [0,3–8,5] | 0 % | 0,6 % |
| céu | ≥ 5 | 1,6 % [0,3–8,5] (1 bloco) | 0 % | 2 % |
| **relva (52)** | 1 | 20,2 % [11,5–33,0] | 0 % | 0 % |
| relva | 2 | 14,2 % [7,2–26,1] | 0 % | 22 % |
| relva | 3 | 12,1 % [5,8–23,7] | 0 % | 38 % |
| relva | 4 | 9,2 % [4,0–20,2] | 0 % | 51 % |
| relva | ≥ 5 | 1,9 % [0,3–10,1] (1 bloco) | 0 % | 77 % |

- **Os 2 blocos «não encaixa» no lugar certo inteiro** têm cada um uma junção impossível: B004 (2×2 em (1,31)) viola a regra F num bloco da borda; B095 (3×3 em (44,45), relva) tem uma junção impossível. Podem ser posições do tabuleiro erradas ou silhuetas más [NT: não verificado fisicamente nem contra as Suspeitas].
- **Relva:** o custo por junção é mais alto: mediana 2,03 e 20 % das junções acima de `t_abs`, contra mediana 0,94 e 0,2 % no céu. `t_abs` foi afinado no céu, por isso com poucas junções «não encaixa» é falso em 1 de cada 5 grupos da relva, e com o critério B a maioria das respostas passa a «não sei».
- Nenhuma junção do lugar certo ficou sem imagem («não testada»): o «não sei» do critério A é 0 %.

### 2.3 Posição gémea (tratada à parte)

- **Só 1 dos 115 blocos tem a posição gémea admissível** com ≥ 1 junção (nos outros, as células caem sobre células ocupadas ou sem vizinha colocada): B032 (céu, (12,62)) → vale (35,2): custo só de forma 0,44 e 0,53 (encaixa por forma), dE 68 e 51 (a imagem rejeita); resposta A «não encaixa» [V, n = 1].
- Na validação (1 922 casos), A diz «não encaixa» em 99,1 % e «encaixa» em 18 casos (0,9 %): 10 na montanha, 6 no vale, 1 céu, 1 relva, quase todos com n_j = 2. A imagem separa a gémea **quando as duas células têm aspeto diferente** (céu ↔ relva/vale). Na zona do meio (montanha, vale), onde a gémea também fica na montanha ou no vale, 16 dos 104 casos (15 %) passam como «encaixa» [V, n pequeno]. Nesses casos a forma encaixa e a imagem não decide: a resposta devia ser «encaixa por forma, a imagem não separa a gémea», não «encaixa».

## 3. Mínimo de junções: o que se pode afirmar

**Fonte dos números:** as tabelas acima, e só elas. Os cortes de 5 % e 10 % do §1 são escolhas minhas, assinaladas como tal: o Tiago decide se as aceita.

1. **Regra literal do §1** (limite superior de Wilson do falso «encaixa» < 5 % sobre todas as posições erradas e falso «não encaixa» < 10 % no céu): cumpre-se **com 1 junção, no céu** (0,5 % e 8,7 %). É otimista por duas razões. Primeiro, as posições erradas não são independentes: 28 blocos de 115 têm algum falso «encaixa» entre as suas ~755 posições erradas já com n_j = 1 (3 com n_j ≥ 4). Segundo, os **negativos difíceis** (deslocar o grupo uma célula) dão 14,3 % [5,7–31,5] com 1 junção e 3,4 % [1,0–11,7] com 2.
2. **Regra proposta (a que sobrevive aos negativos difíceis):**
   - **n_j = 1: não afirmar nada.** Falso «encaixa» de 14 % nos deslocados e falso «não encaixa» de 10 % (20 % na relva).
   - **n_j = 2 ou 3: indicação, não afirmação.** Falso «encaixa» deslocado até 12 % (limite superior, n = 28 a 58); falso «não encaixa» na relva 12–14 %. No céu o falso «não encaixa» é 1,6 % (limite superior 8,5 %): serve de aviso, não de veredicto.
   - **n_j ≥ 4: afirmar «encaixa» com o critério B** (todas as junções testadas, máximo ≤ `t_abs`): 0 falsos em 4 733 posições erradas, 0 em 115 blocos (limite superior de Wilson por bloco 3,2 %) e 0 em 307 deslocadas [0,0–1,2]. No céu, falso «não encaixa» 1,6 % [0,3–8,5].
   - **Fora do céu** (relva medida; montanha e vale **sem dados**): «não encaixa» só com n_j ≥ 5 (1,9 % [0,3–10,1]; com 4 é 9,2 % [4,0–20,2]), e antes de afirmar na relva convém uma `t_abs` por zona (as junções da relva custam o dobro). Com B na relva, 77 % das respostas a n_j ≥ 5 ficam «não sei» enquanto isso não se fizer.
3. **O que isto não mede:**
   - o GT são as posições do tabuleiro (colocadas); o molde do buraco só tem confirmações físicas no céu (38/38 rank 1, 37 no céu, 1 na montanha); **na relva e no vale não há GT físico**, e na relva as posições são do legado e automáticas [NT];
   - os 115 blocos são retângulos cheios, sem buracos nem formas em L; um grupo largado à mão tem erro de colocação de poucos mm, aqui zero (cada peça está exatamente na sua célula) [NT];
   - só se mediu a fronteira do montado de hoje; o Tiago pode largar o grupo noutro sítio;
   - a pose das peças do grupo vem da pose do tabuleiro; num grupo solto vem da rotação do layout (`lay`/`rot` do `loose.py`), que não está guardada nas secções (`QUADRADOS.md`) [NT].

## 4. O que falta para propor peças que façam crescer um grupo solto pelos lados livres (não implementado)

Ideia: tratar cada lado livre de um grupo solto como um buraco virtual e reaproveitar `rank_hole` (`src/fit.py`), com o grupo no papel do montado e as soltas no do pool.

**Já serve tal como está [V por leitura do código].**
- `side_costs(hs, pool, calib)`, `pool_arrays` e `pool_items`: custo de um lado contra todos os lados das candidatas (a mesma conta que se usou acima).
- `joint_costs` e `rank_hole`: custo conjunto (média sobre as vizinhas, mínimo pelas 4 rotações da candidata), `d1`, `d2`, margem, rejeição absoluta `t_abs`, confiança `alta`/`media`/`sem` (`confidence`), `theta_for` e `exclude` (peças rejeitadas).
- `assign`: atribuição peças × buracos sem repetir peça.
- `eroded_sides`, `side_strips`, `_Cache`: as silhuetas erodidas e as tiras Lab de qualquer peça com forma (soltas e grupo).

**O que falta.**
1. **Layout do grupo como entrada.** `hole_queries` só constrói buracos a partir do `Board` e de `render.initial_theta`. Para um grupo solto é preciso construir `HoleQuery` a partir do layout local (célula local e rotação por peça): célula virtual vizinha de uma ou mais peças do grupo, `HoleSide` com o lado dessas peças que olha a célula (índice por `board_dirs` com a rotação do layout em vez da pose do tabuleiro), a tira e o `scan_id`. Esse layout (rotação por peça; `Section.cells_local` só guarda a célula) **não está guardado** (`QUADRADOS.md`, falta 3).
2. **Regra F sem posição.** `FitCalibration.f_rule` e `_f_mask` exigem F exatamente nas direções de borda da célula (`HoleQuery.f_required`) e proíbem F nas restantes. Um grupo sem posição não sabe onde é a borda: é preciso uma opção «F permitido nos lados que olham para fora do grupo» (ou desligar a regra).
3. **Pool sem as peças do grupo nem as de outros grupos.** `pool_items` devolve as soltas; falta excluir as peças já em grupos (a regra «já no grupo N» do ESPEC), as rejeitadas para este grupo e as descartadas.
4. **Células virtuais.** Enumerar as células livres à volta do grupo (incluindo as concavidades com ≥ 2 vizinhas, de maior confiança), não propor duas peças para a mesma célula nem a mesma peça para duas (usar `assign`), e impedir que a peça nova ocupe uma célula do grupo.
5. **Calibração e GT próprios.** `t_abs` 2,67 e `margin_min` 1,5 foram afinados em 144 buracos de 8 folhas do céu com 32–100 candidatas; aqui o pool são ~500 soltas e as vizinhas são soltas de outras folhas. Pelo que as tabelas acima mostram (relva com custos de junção ≈ 2× os do céu), o limiar tem de ser medido de novo, por zona. É o protocolo do `M11_CRITERIOS.md` (tomar um grupo colocado, retirar-lhe uma peça adjacente, ver se o ranking a devolve) com o pool das soltas atuais e m = nº de vizinhas no grupo. Não existe GT físico de «peça acrescentada a um grupo solto» (só os 17 quadrados).
6. **Evento e contador.** Não há evento para «peça acrescentada ao grupo X confirmada/rejeitada» (`hole_confirmed`/`hole_rejected` assumem uma célula do tabuleiro). Falta o análogo (`group_piece_confirmed`/`rejected`), com origem, rank, custo e margem, para o contador de acertos e falhas (ESPEC §8.3, F4b).
7. **Pose e saída.** `theta_for` devolve a pose no referencial do tabuleiro; para o grupo tem de ser no referencial do grupo, composta depois com a pose do grupo quando ele for fixado. A saída leva ainda saco e nº, a imagem e o desenho do grupo com a peça nova.
8. **Zona.** `HoleQuery.zone` e a confiança por zona precisam da zona do grupo; um grupo solto não a tem (a zona provável vem de um kNN de cor em `loose.py`, que não está no programa).
9. **Mínimo de junções.** As tabelas acima dizem que 1 junção não chega para afirmar nada. Para o crescimento isto traduz-se em: células virtuais com 1 vizinha dão no máximo «média/sem» (já é a regra de `confidence` para m = 1) e só as de ≥ 2 vizinhas podem ser `alta`, depois da calibração do ponto 5.
