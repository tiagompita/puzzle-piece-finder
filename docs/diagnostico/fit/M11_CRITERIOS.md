# M11 — molde do buraco como RANKING: critérios fixados ANTES de correr

_2026-11-07. Escrito e commitado antes de existir `src/fit.py` e antes de qualquer afinação ou avaliação. Fontes: `RESULTADOS.md` §10, §13, §15.6 (E-fit passos 4–6), `GT.md`, `docs/estado-e-plano.md` §6/§7 (M11), `docs/plano-m10-m12.md`. Etiquetas: **[V]** verificado, **[NT]** não testado, **[F]** falha. Nada do que está abaixo se ajusta depois de ver os números de validação; qualquer variante extra fica marcada pós-hoc._

## 0. O que se vai construir e o que já se sabe

`src/fit.py` (1.ª metade do M11) dá, para uma célula vazia com ≥ 1 vizinha montada, **as 3 melhores soltas** («candidatas para este buraco»), com custo conjunto, margem e confiança em 3 níveis (`alta` / `media` / `sem` candidata fiável). É um **ranking**, não uma proposta autónoma: o passo 5 mediu E5 estrito top-1 87,8 % (N = 32) / 84,6 % (N = 100) sem erosão e 93,0 / 91,2 % com erosão 0,48 mm em 467 buracos virtuais [V], e **[F]** para propor sem a peça garantida (10–14 % de falsas por buraco a τ = 1,5; precisão 4–5 % a π = 1 %). O piloto real (15 casos, todos céu) é [NT]. Blocos medidos: (a) a certa falha o filtro **duro** de cordas (5,6–9,6 % dos buracos; as 6 piores falhas), (b) sem calibração absoluta a melhor propõe-se sempre, (c) 1 vizinha fica em 2.º, (d) cor entre scans [NT].

Componentes novos a medir, **isolados e juntos**: (1) filtro de cordas **mole** (penalização graduada em vez de ∞), (2) erosão **calibrada** por validação cruzada (o 0,48 veio do E-real, outro GT), (3) **rejeição absoluta** (d1 compatível com o custo de um verdadeiro), (4) **afetação conjunta** buracos × peças. Mede-se o **código de produto**: as ferramentas chamam `src.fit`; a porta de sanidade (§5) reproduz primeiro o passo 5.

## 1. Partição afinação / validação (por folha e por zona)

**Regra (implementada em `tools/diagnostico/fit/m11_particao.py`, só leitura):**
- folhas de um buraco = {scan(s) da peça-alvo} ∪ {scans das vizinhas do GT};
- S_T (folhas de afinação) = páginas `montado` cuja zona dominante é céu ou relva, em posição **ímpar** (1.ª, 3.ª, …) na ordem por id dentro de cada zona;
- buraco ∈ **afinação** ⇔ todas as folhas ⊂ S_T; ∈ **validação** ⇔ nenhuma folha ∈ S_T; caso contrário **descartado** (contado, não usado);
- **reservados só para validação** (nunca afinam, mesmo que as folhas o permitissem): buracos com proveniência b/d (GT independente do layout), buracos de montanha/floresta e vale/aldeia; os **15 casos reais** do passo 6 (`real.py`, GT do log por critério) e a **direção inversa no tabuleiro real** (207–208 buracos, 134 soltas).

Nenhuma folha aparece dos dois lados. A validação tem folhas E zonas que não entraram na afinação (b/d, montanha, vale) e também folhas de céu/relva fora de S_T.

**Conteúdo exato (impresso por `m11_particao.py` em `m11_particao.json`, colado aqui antes de correr qualquer avaliação):**

Corrido em 2026-11-07 sobre o estado atual de `projects/alpes` (`gt.py` regenerado: 1550 lados, 775 pares, GT primário T↔B 1466 consultas; o GT cresceu desde o passo 5 porque o log tem mais 9 confirmações `d` e 50 peças). **478 buracos** com ≥ 2 vizinhas GT (descartados na construção: 103 com < 2 vizinhas, 3 com dois vizinhos no mesmo lado).

Páginas `montado` por zona dominante dos seus buracos: céu S0009, S0010, S0011, S0012, S0021, S0022, S0023; relva S0013, S0014, S0015, S0016, S0017, S0018, S0019; vale/aldeia S0020 (não entra em S_T).

- **S_T (afinação, 8 folhas):** S0009, S0011, S0021, S0023 (céu; S0021 é a página duplicada de S0004, só entra por partilhar peças físicas) e S0013, S0015, S0017, S0019 (relva).
- **Folhas dos buracos de validação (12):** S0001, S0002, S0005, S0006, S0007 (scans de GT manual / lotes), S0010, S0014, S0016, S0018, S0020, S0022, S0024.

| zona | afinação | validação | descartado (misto) | descartado (reservado com folha em S_T) | total |
|---|---|---|---|---|---|
| céu | 63 | 92 | 32 | 11 | 198 |
| montanha/floresta | 0 | 5 | 0 | 8 | 13 |
| relva | 81 | 107 | 0 | 58 | 246 |
| vale/aldeia | 0 | 10 | 0 | 11 | 21 |
| **total** | **144** | **214** | 32 | 88 | 478 |

| nº de vizinhas | afinação | validação | desc. misto | desc. reservado | total |
|---|---|---|---|---|---|
| 2 | 56 | 97 | 3 | 28 | 184 |
| 3 | 53 | 87 | 18 | 32 | 190 |
| 4 | 35 | 30 | 11 | 28 | 104 |

| proveniência | afinação | validação | desc. misto | desc. reservado | total |
|---|---|---|---|---|---|
| só layout (a) | 144 | 188 | 32 | 19 | 383 |
| b/d presente | 0 | 26 | 0 | 69 | 95 |

Por (nº, zona) na validação: 2·céu 39, 2·relva 43, 2·montanha 5, 2·vale 10, 3·céu 40, 3·relva 47, 4·céu 13, 4·relva 17. Os 88 «reservados» descartados são b/d ou montanha/vale cujas vizinhas têm uma cópia numa folha de S_T (a regra «nenhuma folha partilhada» manda; ficam fora dos dois lados). A lista por buraco (id da peça-alvo, zona, m, proveniência, folhas, lado) está em `m11_particao.json`.

**Referência da porta de sanidade (§5), corrida hoje com `buraco.py` sobre o projeto atual, guardada fora do repo (`$PPF_SCRATCH/buraco_base{,_encolhido}.json`), 478 buracos, N = 32 / 64 / 100 / completo:** sem erosão E5 estrito top-1 **87,9 / 86,2 / 84,6 / 74,7 %**, E4 certa-ou-gémea 68,9 / 61,1 / 56,1 / 35,8 %; com erosão 0,48 E5 **93,4 / 92,4 / 91,6 / 85,6 %**, E4 88,5 / 85,0 / 82,3 / 66,1 %; peça ausente a τ = 1,5: falsas/buraco 0,119 / 0,109 / 0,101 (sem erosão) e 0,136 / 0,126 / 0,116 (com). São os números que `src.fit` tem de reproduzir na configuração «passo 5» antes de afinar (sobre os 478, não só sobre S_T).

## 2. Métricas e alvos (todos em S_V, o conjunto de validação; Wilson 95 % com n = nº de buracos, nunca buracos × sorteios)

Sorteios como no passo 5: 200 por buraco e por N, semente `numpy.random.default_rng(20261106 + N)`, N ∈ {32, 100} (lote real) e pool completo (1 sorteio determinístico); as vizinhas e as suas cópias físicas nunca entram no pool; a peça-alvo entra como Z* (presente) ou é excluída com as suas gémeas (ausente).

| # | métrica | alvo | falha | etiqueta |
|---|---|---|---|---|
| A | **E5 estrito top-1** (a certa, não a gémea), N = 32 e N = 100 | ≥ 85 % (IC inteiro acima) | **limite superior do IC < 60 %** → [F], e a Parte 4 (GUI) **não se faz** | principal |
| A' | E5 estrito top-3, N = 32 e 100 | ≥ 90 % | < 60 % | secundária |
| A'' | E4 (só forma) certa-ou-gémea top-1 | ≥ 90 % (referência do plano) | — | reportar |
| B | **peça ausente**: propostas falsas por buraco, N = 32 e 100, por nº de vizinhas; proposta = confiança ≠ `sem` (e, à parte, só `alta`) | ≤ 0,05 falsas/buraco | — | com cobertura (presente), precisão (presente) e precisão derivada a π = 1 % e 10 % |
| B' | utilidade (fixa, como §11.4): falsas/buraco ≤ 0,05 **e** precisão π = 10 % ≥ 90 % **e** cobertura (presente) ≥ 30 % | cumprir as 3 | precisão π = 10 % < 50 % | se só se cumpre à custa da cobertura, reporta-se o compromisso em números, sem escolher |
| C | **direção inversa, tabuleiro real**: cada confirmado (15) retirado e posto no pool: rank da célula certa entre os buracos reais; nº de **outros** buracos onde fica `alta`/`media` | ≤ 0,2 falsas `alta` por peça | > 1,0 | n = 15 → só IC |
| C' | as 134 soltas contra os 207–208 buracos: propostas `alta` por peça (majorante das falsas: quase nenhuma tem lugar entre esses buracos), com e sem afetação | ≤ 0,2 | > 1,0 | majorante, declarado |
| D | casos reais (15): E5 estrito top-1 no pool do lote (≈ 150) e entre os buracos do tabuleiro | ≥ 85 % | < 60 % | **[NT] por construção** (n < 20) |
| E | ablação nos mesmos sorteios: passo 5 reproduzido → +mole → +erosão calibrada → +rejeição → +afetação; isolados e juntos | — | — | ganho por componente, em pontos |

Precisão derivada: `π·cob / (π·cob + (1−π)·falsas)` com `cob` = cobertura com a peça presente (fração com proposta) e `falsas` = fração de buracos com proposta com a peça ausente (como §9.2/§12.7).

Fatias (n ≥ 20): nº de vizinhas (1 só na direção inversa; 2/3/4), zona, proveniência (b/d vs só layout), (nº, zona); as **3 piores** reportam-se sempre.

## 3. Custo e regras fixas (não se afinam)

- Lado: E5 = `rms/1,1 + ΔE_img/10` (+ penalização de corda, §4), `rms` = RMS (mm) do `side_complement` do perfil, `ΔE_img` = mediana de 12 pontos da tira interior (1,0–2,5 mm) do recorte limpo contra a tira espelhada da candidata, ≥ 6 pontos válidos senão ∞ (constantes de GT.md §5 e §11); T↔B duro (F com nada, T–T e B–B impossíveis).
- Buraco: `J_r(Z) = média_k custo(lado da vizinha k, lado (σ·d_k + r) mod 4 de Z)`, `J(Z) = min_r J_r(Z)` (rotação desconhecida, igual para todas as vizinhas); ordem por peça; d1 = melhor J finito, d2 = segundo, margem = d2/d1.
- Lados F exigidos pela célula (`profile.flat_directions`): a rotação `r` tem de pôr um lado F em cada direção de borda da célula e nenhum F nas outras (regra dura; desligada só na reprodução do passo 5, que não a tinha).
- Mapa de lados: σ = sentido em que o índice do lado cresce N→E→S→W, **único em todas as peças colocadas** (hoje +1 em 603/603, §15 do RESULTADOS); `src/fit.py` verifica a unanimidade e devolve erro se falhar (invariante em código).
- **Confiança (fixa):** `alta` ⇔ m ≥ 2 ∧ d1 ≤ T_abs ∧ margem ≥ 1,5; `media` ⇔ d1 ≤ T_abs ∧ ((m = 1 ∧ margem ≥ 1,5) ∨ (m ≥ 2 ∧ margem < 1,5)); `sem` nos restantes (d1 > T_abs, sem 2.ª candidata finita, m = 1 com margem < 1,5). 1,5 = `calibration.margin_min` do perfil (já calibrado no gémeo). **Vizinha única nunca é `alta`** (§15.1: fica em 2.º 2/6 vezes). O top-3 mostra-se sempre; a confiança diz o que vale.
- **Afetação conjunta:** gulosa global sobre todos os pares (buraco, peça) com J finito, por J crescente; cada peça fica num só buraco e cada buraco com uma só peça; as candidatas desalojadas ficam no top-3 com a nota «é a melhor para (l, c)».
- Filtro mole: penalização `1,0 unidade de custo por mm` acima da tolerância por tipo de lado (1,0 mm; 2,0 mm em lados F ou adjacentes a F), somada ao E5; declive **fixo**.
- Erosão: aplicada da mesma forma às vizinhas e às candidatas (silhueta deslocada `e` mm pela normal interior, lados re-analisados, como `fit_eval.shrink_sides`).

## 4. O que se afina (só isto, só em S_T, antes de olhar para S_V)

| parâmetro | grelha | regra de escolha |
|---|---|---|
| erosão `e` (mm) | {0; 0,12; 0,24; 0,36; 0,48; 0,60; 0,72} | máx. E5 estrito top-1 em S_T a N = 32 (filtro duro, sem rejeição); empate (≤ 0,5 ponto) → o menor `e` |
| corte do filtro mole `cut` (múltiplo da tolerância por tipo; acima dele o lado é ∞) | {1× (= duro, como hoje), 2×, 3×, ∞ (nunca ∞ por corda)} | máx. E5 estrito top-1 em S_T a N = 32 com o `e` escolhido; empate → o mais apertado |
| rejeição absoluta `T_abs` | quantil q ∈ {0,90; 0,95; 0,99} do J (E5 conjunto, `e` e `cut` escolhidos) **da peça certa** nos buracos de S_T | máx. precisão derivada a π = 10 % em S_T (N = 32) sujeita a cobertura ≥ 30 %; se nenhum cumpre, o de maior precisão, e diz-se |

A escolha fica registada com a tabela completa da grelha (`m11_afinacao.json`); os três valores entram em `calibration.buraco` do `projects/alpes/puzzle.json` (único toque em `projects/alpes` antes da GUI; `git status` limpo antes). Tudo o resto (§3) está fixo.

## 5. Porta de sanidade (antes de afinar)

A configuração «passo 5» (erosão 0 e 0,48, `cut` = 1× duro, sem regra F, sem rejeição, sem afetação) corrida **através de `src.fit`** tem de reproduzir, nos mesmos sorteios, o `buraco.py` corrido **hoje** sobre o projeto atual (o GT cresceu desde o passo 5: o log tem mais confirmações e peças, por isso a referência é a corrida de hoje, guardada fora do repo, e não os números commitados de 2026-11-06). Diferença admitida: 0,0 pontos (mesmos sorteios, mesma aritmética). Se não reproduzir, pára-se e percebe-se antes de qualquer afinação.

## 6. Condições de paragem e veredicto

- [V] se o IC de Wilson fica inteiro do lado certo do alvo; [F] se o limite superior fica abaixo da fronteira de falha; [NT] nos outros casos (e sempre que n < 20).
- **Se a métrica A der [F] em S_V, a Parte 4 (GUI) não se liga como «sugestão»**: `src/fit.py` fica como ferramenta de medição e o relatório diz porquê.
- Entre 60 % e 85 % (banda [NT]): a GUI liga-se com a etiqueta honesta («ranking, não verificado ao nível do alvo») e a confirmação física passa a ser a GT que falta (§15.6: n ≥ 60, ≥ 40 com ≥ 2 vizinhas, casos fora do céu).
- Nada se afina depois de ver S_V. Se alguma coisa mudar depois, fica marcada **pós-hoc** e não conta para o veredicto.

## 7. Figuras (cv-visual-verification)

De S_V, cenário N = 100, configuração final: 6 **melhores** (1 em cada ⌊n/6⌋ dos acertos, sem escolher), 6 **piores** (pior rank da certa no pool completo, desempate pelo id) e 6 **«sem candidata fiável»** com a peça presente (os de menor margem), cada painel com a candidata **colocada no buraco** e as vizinhas (reutiliza `figs_buraco.draw`/`same_for`); abertas e descritas no relatório.

## 8. Sugestões `alta` em «Vai buscar»: regra fixada em 2026-11-08, antes do código

**Factos que levam à regra.** Em uso real (2026-11-08, `projects/alpes/log.jsonl`) os 10 buracos `alta` propostos pelo M11 foram confirmados fisicamente: 10 `hole_confirmed` com `rank 1`, `confianca alta`, `fit_version m11-1` (3 com m = 3, 7 com m = 2), 0 `hole_rejected`; todos céu. Precisão observada 10/10, Wilson 95 % 0,72–1,00. Decisão do Tiago (`docs/decisoes.md`): as `alta` entram em «Vai buscar»; o resto fica numa página própria.

**Definições (fixas).**
- **Sugestão `alta`** = a candidata **rank 1** de um buraco com `confianca == "alta"` (⇒ m ≥ 2, d1 ≤ T_abs, margem ≥ 1,5, §3) **e** coerente com a afetação conjunta (`atribuida == peça` ou `melhor_para` ausente). Um buraco `alta` cuja afetação dá a peça a outro buraco fica na página «Buracos» com a marca «afetação em conflito», não em «Vai buscar». Média / «baixa» / `sem` nunca entram em «Vai buscar».
- **Decisão `alta`** (o que conta no contador) = evento `hole_confirmed` ou `hole_rejected` com `origin == "buraco"`, `confianca == "alta"` e `rank == 1`. Rejeições de rank 2–3 (feitas na página «Buracos») não contam contra a sugestão: a sugestão era a rank 1.
- **Contador** = acertos (`hole_confirmed`) / falhas (`hole_rejected`) / total das decisões `alta` desde o início do projeto; precisão com IC de Wilson 95 % (`fit.wilson`).
- **Janela de pausa** = as últimas `ALTA_JANELA = 20` decisões `alta` **posteriores ao último evento `holes_alta_resumed`** (todas, se houver menos de 20). Se a janela tiver ≥ `ALTA_MAX_FALHAS = 3` rejeições, as sugestões `alta` saem de «Vai buscar» (ficam na página «Buracos», grupo «alta · em pausa») e aparece um aviso, até o Tiago reativar (`holes_alta_resumed {autor, nota}`), o que reinicia a janela. Sem reinício a mesma janela voltava a pausar logo. Tudo é derivado do log: nenhum estado novo fora de `log.jsonl`.
- **Rótulos da página «Buracos»** (GUI, não métrica): «média» = `media` com m ≥ 2; «baixa» = `media` com m = 1 (vizinha única nunca é alta); «sem candidata fiável» = `sem`. `fit.confidence` não muda.

**Porquê 3 em 20 (limiar do Tiago; justificação e sensibilidade, para ele ajustar).** 3/20 corresponde a uma precisão observada ≤ 85 % na janela. Probabilidade de a regra disparar numa janela cheia de 20 decisões, por precisão verdadeira (binomial, P[X ≥ 3]):

| precisão verdadeira | 95 % | 90 % | 85 % | 80 % | 70 % |
|---|---|---|---|---|---|
| P[pausa] | 7,5 % | 32 % | 60 % | 79 % | 96 % |

Ou seja: quase não incomoda enquanto a precisão for ≈ 95 % (a observada é 100 % em 10), apanha quase de certeza uma queda para 80 % e fica a meio nos 90 %. A amostra atual (10/10, IC 72–100 %) não distingue 90 de 100 %, por isso a regra é uma rede, não uma medição; a medição é o contador. Alternativas rejeitadas: 2/20 dispararia em 26 % das janelas a 95 % de precisão (ruído); 5/20 deixaria passar 80 % em metade dos casos. As duas constantes vivem em `src/fit.py`.

**O que fica por medir [NT].** Precisão fora do céu (0 decisões); a precisão a π real do lote (a janela mede a sugestão, não a peça ausente); n ≥ 60 do §15.6.
