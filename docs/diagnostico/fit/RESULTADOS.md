# E-fit — resultados do E4 (geometria) e E5 (geometria + imagem)

_2026-11-05. Medição, não produto: `src/` e `projects/alpes` não foram alterados (só leitura). GT e critérios: [`GT.md`](GT.md) (commit `5f8bcaa`, escritos **antes** de correr). Código: `tools/diagnostico/fit/` (`common.py`, `gt.py`, `fit_eval.py`, `analise.py`, `causas.py`, `figs.py`, `sanidade.py`). Dados commitados: `analise.json`, `causas.json`, `exemplos.json` e a variante pós-hoc `*_encolhido.json`; **regeneráveis e não commitados** (grandes): `gt_pairs.json`, `resultados.json`, `resultados_encolhido.json`, `strips_cache.npz`. Etiquetas: **[V]** verificado, **[NT]** não testado, **[F]** falha. Reproduzir: `gt.py` → `fit_eval.py` → `analise.py` → `causas.py` → `figs.py` (≈ 4 min, a 1.ª vez calcula as tiras de imagem; correr de novo reproduz os mesmos números)._

## Veredicto

**E4 [F] e E5 [F], com margem enorme.** No critério fixado (sem otimizar nada): E4 top-1 **1,8 %** (alvo ≥ 60 %), top-3 **4,6 %** (alvo ≥ 90 %; falha: < 60 %); E5 top-1 **19,8 %** (alvo ≥ 85 %; falha: < 60 %). A forma + a continuidade de imagem **não chegam** para ordenar os parceiros de um lado entre ≈ 3260 lados candidatos. Há ganho real sobre o acaso, mas de ordem de grandeza insuficiente para o produto. **[V]**

## 1. Números contra os alvos (n = 1442 lados, 721 pares; GT primário T↔B)

Acerto = lado do vizinho verdadeiro **ou** do gémeo do vizinho (`lenient`); `strict` = só o vizinho. Wilson 95 %.

| métrica | lenient | strict | alvo / falha |
|---|---|---|---|
| **E4** top-1 | **1,8 %** (26/1442; 1,2–2,6) | 1,3 % (0,8–2,0) | ≥ 60 % |
| **E4** top-3 | **4,6 %** (3,6–5,8) | 3,4 % (2,6–4,5) | ≥ 90 % / falha < 60 % |
| E4 top-10 | 12,0 % (10,4–13,8) | 9,5 % | — |
| E4 custo `rms + 0,5 \|ΔL\|` (declarado, não escolhido) top-1 / top-3 | 2,1 % / 5,7 % | 1,6 % / 4,2 % | — |
| **E5** top-1 | **19,8 %** (286/1442; 17,9–22,0) | 19,8 % | ≥ 85 % / falha < 60 % |
| E5 top-3 | 38,1 % (35,6–40,6) | 38,1 % | — |
| só imagem (`ΔE_img`) top-1 / top-3 | 12,7 % / 25,5 % | idem | — |

**Baselines** [V]: acaso sobre todos os lados do pool (814 peças físicas, 3256 lados): **0,07 %** de top-1; sobre os T/B compatíveis (≈ 1517 por consulta): 0,15 %; **filtro de cordas sozinho** (≈ 951 candidatos passam): top-1 **0,29 %**, top-3 **0,87 %**. Ganho do E4 sobre as cordas: ≈ 6× em top-1, ≈ 5× em top-3; do E5 sobre o E4: ≈ 11× em top-1 — é a imagem que carrega, e carrega pouco. As cordas deixam passar 63 % dos compatíveis e só deitam fora o vizinho verdadeiro em 3,1 % dos casos (lenient; 4,1 % strict).

**Porquê (diagnóstico direto) [V, `sanidade.py`]:** o RMS do perfil do **vizinho verdadeiro** tem mediana **1,11 mm** (p10 0,87, p90 1,44; igual em (a) e em (b)/(d)), enquanto pares T–B aleatórios têm mediana 1,79 (p10 1,02, p90 2,83). Reproduz o LEGADO.md (1,09 vs 1,71). O verdadeiro está, em média, à frente de ≈ 90 candidatos (rank E4 mediano 90,5): a distribuição do RMS verdadeiro cai por cima da cauda baixa da dos pares aleatórios. Só 29 % dos verdadeiros têm RMS < 1,0 mm e 4,6 % < 0,8 mm. O ruído de re-scan é 0,27 mm: **a forma lida da silhueta tem um viés sistemático de ≈ 1 mm nos lados** (hipótese já do LEGADO.md; ver §4).

## 2. Fatias (as piores, não só a média)

Fatias com n ≥ 20 (E4 top-1 / top-3 | E5 top-1):

| fatia | n | E4 t1 / t3 | E5 t1 |
|---|---|---|---|
| **b/d (GT independente do layout)** | 244 | 0,8 % / 2,5 % | **11,1 %** |
| a (só layout) | 1198 | 2,0 % / 5,0 % | 21,6 % |
| zona céu | 622 | 1,3 % / 5,0 % | 26,0 % |
| zona relva | 735 | 2,0 % / 4,2 % | **13,1 %** |
| vale/aldeia (n 45) · montanha/floresta (n 38) | — | 4,4 % / 4,4 % · 2,6 % / 5,3 % | 33,3 % · 34,2 % |
| classe B / T | 721 / 721 | 1,0 % / 2,9 % · 2,6 % / 6,2 % | 20,5 % · 19,1 % |
| (b, céu) | 53 | **0 % / 0 %** | 11 % |
| (b, relva) | 190 | 1 % / 3 % | 11 % |
| (B, relva) | 367 | 0,8 % / 2,2 % | **12,8 %** |
| página S0017 (`montado_p09`) | 94 | 1,1 % / 2,1 % | **4,3 %** |
| página S0019 (`montado_p11`) · S0013 (`p05`) | 52 · 36 | 1,9 / 3,8 % · 2,8 / 2,8 % | 9,6 % · 11,1 % |

**As 3 piores fatias:** (1) a **GT independente do layout** (b/d, n = 244): E4 top-3 2,5 %, E5 top-1 11,1 %; (2) **a página `montado_p09` (S0017)**: E5 top-1 4,3 %; (3) **relva** (n = 735): E5 top-1 13 % (a imagem de relva quase não discrimina: textura uniforme). Nenhuma fatia chega perto dos alvos; a melhor (vale/aldeia, montanha) tem n pequeno (45 / 38). **O GT não cobre o meio do puzzle** (83 lados): conclusões fora de céu e relva são [NT]. (b/d é pior que a: a escala/condições de digitalização são outras; uma explicação possível mas não testada é o recorte limpo e a cor entre scans diferentes [NT].)

## 3. Causas das falhas (regras fixas de GT.md §5)

Falhas do E4 top-1 (1416) **[V, `causas.py`]**: **93 % «quase-empate por acaso»** (o vencedor tem RMS ≤ ao do verdadeiro + 0,15 mm mas é outro lado: com ≈ 950 candidatos há muitos lados tão bons como o verdadeiro), 3 % forma mal lida (o lado verdadeiro falha as cordas ou o tipo), 3 % gémeo/equivalente geométrico (≤ 0,5 mm do verdadeiro, gémea que o mapa de gémeas não apanhou), 1 % RMS ≥ 2 mm. No E5 top-1 (1156 falhas): 87 % quase-empate, 6 % equivalente, 4 % forma, 2 % imagem enganadora (rank E4 ≤ 3 que o E5 piora), 1 % RMS ≥ 2 mm. **A causa dominante não é a gémea nem a pose**: é a falta de poder discriminativo do lado lido. (Pose/escala: os lados são em mm e independentes da pose; só entraria pela tira de imagem, e não se isolou — **[NT]**.)

## 4. Exploratório e pós-hoc: corrigir o viés da silhueta (NÃO é o resultado do critério)

Hipótese: a silhueta fica +0,48 mm fora da linha de corte (E-real, `EREAL.md`) ⇒ cada tab incha e cada blank encolhe, ≈ 2 × 0,48 mm num par T–B. Recalculando os lados com o contorno **erodido 0,48 mm** (valor do E-real, **não ajustado** a este GT; `FIT_SHRINK=0.48`, `*_encolhido.json`) [V como medição, **[NT]** como causa]:

| | critério (sem correção) | com erosão de 0,48 mm |
|---|---|---|
| E4 top-1 / top-3 | 1,8 % / 4,6 % | **8,1 % / 17,1 %** (strict 4,8 % / 12,8 %) |
| E5 top-1 / top-3 | 19,8 % / 38,1 % | **37,9 % / 58,7 %** |
| só 0,48 mm: E5 top-1 por zona | céu 26 %, relva 13 % | céu 53 %, relva 24 % |
| vizinho verdadeiro filtrado pelas cordas | 3,1 % | 1,5 % |

O viés da silhueta explica **uma parte grande** (E4 ×4, E5 ×2) mas **não chega**: continua [F] nos dois critérios (E4 top-3 17 % < 60 %; E5 top-1 38 % < 60 %), e 21 % das falhas do E4 passam a ser gémeas geométricas (o vencedor é um lado equivalente ao verdadeiro: com forma limpa, a gémea passa a competir de facto). Não se otimizou o valor (1 ponto, 0,48 mm); um varrimento seria otimizar sobre a amostra e exigiria hold-out.

## 5. Exemplos visuais (cv-visual-verification: prova visual + números)

Montagens: [`exemplos_acertos.jpg`](exemplos_acertos.jpg) (6 acertos do E5, um em cada ⌊N/6⌋ dos acertos, **sem escolher bonitos**) e [`exemplos_falhas.jpg`](exemplos_falhas.jpg) (6 falhas **pelo pior rank**: 3 com o lado verdadeiro fora do filtro — rank «None» —, ordenadas por RMS verdadeiro, e 3 com o pior rank finito). Cada painel põe a candidata **no sítio** (cantos do lado coincidentes); nas falhas, à esquerda o vizinho verdadeiro e à direita o vencedor do E5. Amarelo = contorno de A, ciano = candidata, vermelho = lado consultado.

| # | consulta → vizinho | zona / prov. | E4 / E5 | RMS verd. | causa (regra fixa) e leitura visual |
|---|---|---|---|---|---|
| 1 | P0796 s0 → P0797 s2 | céu / a | 9 / **1** | 1,11 | acerto; a imagem azul uniforme ajuda |
| 2 | P0254 s1 → P0260 s3 | céu / a | 87 / **1** | 1,57 | acerto **só por imagem** (a forma punha-o em 87.º) |
| 3 | P0320 s1 → P0326 s3 | céu / a | 18 / **1** | 1,03 | acerto por imagem |
| 4 | P0487 s1 → P0491 s3 | relva / a | 33 / **1** | 1,00 | acerto (textura de relva contínua) |
| 5 | P0663 s1 → P0664 s3 | montanha / a | 29 / **1** | 0,74 | acerto por imagem |
| 6 | P0797 s3 → P0790 s1 | céu / a | 26 / **1** | 0,93 | acerto por imagem |
| 7 | P0459 s0 → P0460 s2 | relva / a | — / — | 1,96 | **forma mal lida (M3/M4)**: \|ΔL\| 1,17 mm > 1,0 (corda); no painel a peça verdadeira encaixa à vista; o vencedor (P0027, 1,81 mm do lado verdadeiro) não |
| 8 | P0460 s2 → P0459 s0 | relva / a | — / — | 1,96 | idem (mesma aresta no sentido contrário) |
| 9 | P0083 s2 → P0082 s0 | relva / b+a | — / — | 1,83 | **forma mal lida**: \|ΔL\| 1,25 mm; o franja verde do contorno é visível; o vencedor está a 0,52 mm do lado verdadeiro (quase equivalente) |
| 10 | P0306 s2 → P0305 s0 | céu / a | 89 / 970 | **0,77** | RMS bom mas há 88 lados melhores (**quase-empate por acaso**); no E5 a **imagem** estraga (azul-acinzentado ao lado de creme: gradiente de céu) → rank 970 |
| 11 | P0082 s0 → P0083 s2 | relva / b+a | 833 / 943 | 1,83 | pela regra fixa: quase-empate (RMS 1,83 < 2 mm e passa as cordas, 2 mm por estar junto a F); **visualmente é forma mal lida** (franja verde): o verdadeiro cai em 833.º; o vencedor está a 2,03 mm do verdadeiro |
| 12 | P0636 s3 → P0630 s1 | montanha / a | 240 / 857 | 1,14 | **quase-empate por acaso** (240 lados melhores) + imagem escura de floresta sem contraste |

Nota visual: nos painéis 7–9 e 11 as duas peças verdadeiras **encaixam fisicamente** (o tab entra no blank) mas o perfil lido difere ≈ 1,8 mm — é a forma lida (franja de fundo, sombra), não a pose. **[V visual]**

## 6. Limitações do GT e do método (o que isto não prova)

- O layout (a) é a verdade física que o Tiago construiu à mão **[assumida]**; onde verificável (84 pares com posição b/d nas duas peças) 84/84 são vizinhas de célula **[V]**, e o RMS do verdadeiro é igual em (a) e em (b)/(d) — o que confirma que as etiquetas de lado do layout estão certas. O ruído não detetável (par T–B que não é vizinho) pessimiza as métricas: **[NT]** quanto.
- Pool = 814 peças físicas (3256 lados). Um lote real de M6 tem ≈ 32–100 peças (128–400 lados); com essa dimensão o rank sobe mas **não se mediu** o varrimento por tamanho de pool **[NT]**; é o próximo passo barato.
- A tira de imagem usa o recorte limpo (`render.piece_rgba_for_display`) e a cor entre scans diferentes pode enviesar o ΔE (a peça-representante do vizinho pode vir de outro scan que a consulta) **[NT]**. As constantes do E5 (1,1 mm, 10 ΔE, pesos iguais) estavam fixadas antes e não foram afinadas; outros pesos podem melhorar o E5, mas isso é otimizar sobre a amostra.
- O mapa de gémeas é por silhueta (mutual-NN, ΔE > 10) e cobre 412 das 814 peças; falhas dele aparecem como «equivalente geométrico».
- O GT só tem adjacências internas T↔B; cantos e bordas (F) ficam fora.

## 7. O que bloquearia M11/M6 **[V só o que se mediu]**

1. **A forma lida da silhueta (M3/M4) não discrimina parceiros**: RMS verdadeiro 1,11 mm contra 1,79 de pares aleatórios; mesmo com a erosão de 0,48 mm o E4 só chega a top-3 17 % **[V]**. Sem lados com ruído ≲ 0,3–0,5 mm (as linhas de corte em vez da silhueta, ou o modelo de sombra adiado no M3) **[NT]** o `rank_partners` por forma não sai do chão.
2. **A imagem sozinha não chega e na relva é fraca** (E5 13 %, 24 % com erosão); no céu 26 % (53 % com erosão). A continuidade em Lab entre duas soltas dá pouco sinal local **[V]**.
3. **O molde do buraco (M11) combina ≥ 2 vizinhos**; não foi medido aqui (o E-buraco é outra experiência) — a restrição conjunta pode ser muito mais forte do que um lado isolado, mas **[NT]**: é a ordem natural do próximo passo (e o GT (a)/(b) já tem células com 2 e 3 vizinhos).
4. O M6 (encaixe entre soltas, um lado de cada vez) **não é viável com estes lados** em pool de ≈ 800; em pool de lote pequeno **[NT]**.

**Próximos passos baratos [NT]:** (o varrimento por tamanho de pool está feito no §9) E-buraco com 2–3 vizinhos; medir o RMS verdadeiro com o contorno por linha de corte (secções de céu e legado) em vez da silhueta; hold-out do desvio isotrópico com validação cruzada metade/metade.

## 8. Passo 4 — pool pequeno (o caso de uso real). **Critérios fixados em 2026-11-06, ANTES de correr**

Medição, não produto: `src/` e `projects/alpes` não são tocados. Código: `tools/diagnostico/fit/pool.py` (reutiliza `fit_eval.py`: mesmas lados, cordas, E4, E5, tiras, GT e mapa de gémeas). Motivo: o §1 usou um pool de 814 peças físicas; um lote real tem ≈ 32–100.

**Dados e sorteios (fixos).** GT primário T↔B (1442 consultas). «Pool de N» = N peças físicas (representantes de `physical_clusters`), nunca a do próprio lado consultado. Semente `numpy.random.default_rng(20261106)`, **200 sorteios por consulta e por N**, N ∈ {32, 64, 100, 200}. Erosão: **só** duas condições, 0 e 0,48 mm (o valor do §4, **não varrido**). Acerto: `lenient` (vizinho ou gémea dele, como no §1); `strict` também reportado.

**A. Vizinho presente.** Pool = peça do vizinho verdadeiro + N−1 aleatórias (se uma gémea do vizinho sair por acaso conta como acerto, convenção `lenient`). E4 e E5 top-1/top-3 (mesmos scores e constantes do §1). **Alvos (os de GT.md §5, aplicados a N = 32 e N = 100):** E4 top-1 ≥ 60 %, top-3 ≥ 90 % (falha se top-3 < 60 %); E5 top-1 ≥ 85 % (falha se < 60 %). Baselines por sorteio: acaso (1/#candidatos que passam) e filtro de cordas. **Intervalos de Wilson com n = nº de consultas (1442), não com consultas×sorteios** (os 200 sorteios de uma consulta não são independentes; usar 288 400 daria intervalos falsamente estreitos); p = média das taxas por consulta.

**B. Vizinho ausente.** Pool = N peças aleatórias **sem** a verdadeira nem as suas gémeas (um lote que contém a gémea também resolve). Confiança = **margem d2/d1 do custo E5** entre os candidatos que passam as cordas (d1 = melhor, d2 = segundo; com < 2 candidatos não há proposta, como a regra «sem margem» do `twin.py`). **Limiar de operação fixado: τ = 1,5** (o `margin_min` já calibrado no perfil, não escolhido aqui); a curva varre τ ∈ {1,0; 1,1; 1,25; 1,5; 2; 3; 5} só para mostrar o compromisso. Reporta-se por τ e N: **(i)** presente: cobertura (fração de consultas com proposta) e precisão (a proposta é um lado aceite); **(ii)** ausente: propostas falsas **por consulta** (qualquer proposta é falsa); **(iii)** precisão derivada para prevalências π ∈ {1 %, 10 %, 50 %} de o vizinho estar no lote (cálculo, não sorteio; o caso comum é π ≈ 1 %). **Critério de utilidade (fixo):** em τ = 1,5, propostas falsas/consulta ≤ 0,05 **e** precisão a π = 10 % ≥ 90 % **e** cobertura (presente) ≥ 30 %. Falha clara: falsas/consulta > 0,2 ou precisão a π = 10 % < 50 %.

**C. Direção inversa (a da GUI).** Fronteira de M = 50 lados livres (consultas do GT, de peças distintas), lote de N peças ∈ {32, 100} que contém o vizinho verdadeiro de K = 8 desses lados (os «lugares») e N−8 aleatórias; as outras 42 consultas têm o vizinho **fora** do lote (nem gémea). Por peça do lote: (i) peças com lugar: está no top-3 da consulta do seu lugar? (recall, alvo ≥ 90 % como o E4 top-3); (ii) **propostas falsas por peça**: nº de consultas **de outros lugares** onde a peça aparece (top-3 sem filtro; e top-1 com margem ≥ τ = 1,5). Alvo: ≤ 0,2 propostas falsas por peça com filtro; falha > 1,0. 200 sorteios por N.

**Veredicto:** por bloco, [V] se o intervalo de Wilson fica todo do lado certo do alvo, [F] se o limite superior fica abaixo da fronteira de falha, [NT] caso contrário. Se falhar: o bloqueio dominante e as mudanças que o atacariam, **sem implementar**. Nada será afinado depois de ver os números; qualquer variante extra fica marcada pós-hoc.

## 9. Passo 4 — resultados (2026-11-06; critérios do §8, nada afinado depois de ver os números)

Reprodução: `python tools/diagnostico/fit/pool.py` e `FIT_SHRINK=0.48 python tools/diagnostico/fit/pool.py` (≈ 2 min cada; `pool.json`, `pool_encolhido.json`). **Sanidade [V]:** com N = 805 o mesmo código reproduz o §1 (E4 1,8 % / 4,6 %, E5 19,9 % / 38,2 %), logo o varrimento mede o mesmo sistema; a única variável é o tamanho do pool. Suite antes de correr: 180 passed, 1 skipped (Python 3.12).

### 9.1 Vizinho presente (A). Wilson 95 % com n = 1442 consultas

| N (pool) | E4 top-1 | E4 top-3 | E5 top-1 | E5 top-3 | acaso top-1 / cordas top-3 |
|---|---|---|---|---|---|
| **sem erosão** | | | | | |
| 32 | 17,3 % (15,5–19,4) | 37,9 % (35,4–40,4) | **63,7 %** (61,2–66,2) | 85,2 % (83,2–86,9) | 3,4 % / 10,0 % |
| 64 | 10,7 % | 25,1 % | 54,3 % | 77,3 % | 1,8 % / 5,3 % |
| 100 | 7,7 % (6,4–9,2) | 18,7 % (16,8–20,8) | **47,9 %** (45,4–50,5) | 71,3 % (68,9–73,6) | 1,2 % / 3,6 % |
| 200 | 4,6 % | 11,5 % | 37,9 % | 60,8 % | 0,7 % / 2,0 % |
| **erosão 0,48 mm** (1 ponto, não varrida) | | | | | |
| 32 | 40,8 % (38,3–43,4) | 70,0 % (67,6–72,3) | **76,7 %** (74,4–78,8) | 91,4 % (89,9–92,8) | idem |
| 64 | 29,5 % | 54,6 % | 69,6 % | 86,4 % | |
| 100 | 23,4 % (21,3–25,7) | 45,3 % (42,7–47,9) | **64,6 %** (62,1–67,1) | 82,5 % (80,4–84,3) | |
| 200 | 16,3 % | 33,2 % | 56,2 % | 75,5 % | |

`strict` = `lenient` em E5 (a gémea do vizinho quase nunca sai no sorteio). **[V]** O pool pequeno ajuda muito (E5 top-1 19,9 % → 63,7 % de 805 para 32 peças; ≈ 19× o acaso), mas **só quando o vizinho está no lote**.

**Veredicto A contra os alvos fixados:** E4 [F] em N = 32 e 100, com e sem erosão (sem erosão top-3 de 37,9 % / 18,7 %, limite superior < 60 %; com erosão N = 100 top-3 45,3 %, também [F]; N = 32 com erosão 70,0 %, acima da falha mas longe dos 90 %). **E5 não atinge o alvo (≥ 85 % top-1) em nenhum ponto**: o melhor é 76,7 % (N = 32, com erosão). Fica na banda «abaixo do alvo, acima da falha» (≥ 60 %) em N = 32 (63,7 %; 76,7 %) e em N = 100 só com erosão (64,6 %); sem erosão em N = 100 (47,9 %) é [F]. Nenhum ponto é [V] contra o alvo.

### 9.2 Vizinho ausente (B): precisão–cobertura, não um número só

Confiança = margem d2/d1 do custo E5; τ de operação **1,5** (fixado). «cobertura» = fração de consultas com proposta quando o vizinho está presente; «falsas/consulta» = fração de consultas com proposta quando está ausente (uma proposta por consulta = nº de propostas falsas por consulta); precisão a π = P(vizinho no lote). Em cada célula: sem erosão / com erosão.

| N | τ | cobertura (presente) | precisão (presente) | **falsas/consulta (ausente)** | precisão π = 1 % | π = 10 % | π = 50 % |
|---|---|---|---|---|---|---|---|
| 32 | 1,0 | 99,9 / 99,9 % | 63,7 / 76,7 % | 0,997 / 0,998 | 0,6 / 0,8 % | 6 / 8 % | 32 / 38 % |
| 32 | 1,25 | 42,5 / 59,8 % | 87,2 / 93,7 % | 0,236 / 0,282 | 1,6 / 2,0 % | 15 / 18 % | 56 / 64 % |
| **32** | **1,5** | **19,9 / 38,6 %** | **95,9 / 98,2 %** | **0,067 / 0,095** | **2,8 / 3,9 %** | **24 / 31 %** | 72 / 79 % |
| 32 | 2,0 | 5,2 / 15,4 % | 98,9 / 99,6 % | 0,011 / 0,019 | 4,4 / 7,7 % | 34 / 48 % | 81 / 89 % |
| 100 | 1,25 | 26,7 / 44,2 % | 78,6 / 90,0 % | 0,150 / 0,193 | 1,4 / 2,0 % | 13 / 18 % | 50 / 63 % |
| **100** | **1,5** | **8,9 / 22,5 %** | **92,1 / 97,5 %** | **0,029 / 0,046** | **2,8 / 4,6 %** | **23 / 34 %** | 70 / 81 % |
| 100 | 2,0 | 1,2 / 5,8 % | 98,7 / 99,7 % | 0,003 / 0,005 | 4,4 / 10,4 % | 34 / 56 % | 81 / 92 % |

(Tabela completa, τ ∈ {1; 1,1; 1,25; 1,5; 2; 3; 5}, em `pool*.json`. Para τ ≥ 3 a cobertura é < 3 %, sem utilidade.)

**[V]** Em τ = 1,5 a proposta, **quando existe, é quase sempre certa** (92–98 %), mas **com o vizinho fora do lote o sistema propõe na mesma em 3–9,5 % das consultas**; como o vizinho está quase sempre ausente, a precisão efetiva desaba: **a π = 1 % (o caso comum) é 2,8–4,6 %, ≈ 21–35 propostas falsas por cada certa**; a π = 10 % é 23–34 %. Nenhum τ resolve: subir τ baixa as falsas mas a cobertura vai a zero primeiro (N = 100, τ = 2: 0,3–0,5 % de falsas, 1–6 % de cobertura). **Critério de utilidade (falsas/consulta ≤ 0,05 e precisão a π = 10 % ≥ 90 % e cobertura ≥ 30 %): não cumprido em nenhum ponto.** N = 100 cumpre o limite de falsas (0,029 / 0,046) mas não a precisão a π = 10 % nem (sem erosão) a cobertura (8,9 %); N = 32 cumpre a cobertura só com erosão (38,6 %) mas excede as falsas (0,067 / 0,095). **[F]** pela condição de falha clara: precisão a π = 10 % < 50 % em todos os pontos.

### 9.3 Direção inversa, a da GUI (C): 50 lados livres, lote de N com 8 lugares

| N | erosão | recall no lugar (top-3) | falsas por peça, top-3 sem filtro | **falsas por peça, top-1 com margem ≥ 1,5** (p95) |
|---|---|---|---|---|
| 32 | não / sim | 83,3 / 91,3 % | **4,12 / 4,11** | 0,089 / 0,122 (0,16 / 0,23) |
| 100 | não / sim | 72,2 / 81,9 % | **1,39 / 1,39** | 0,012 / 0,019 (0,03 / 0,04) |

(200 sorteios por N; recall sobre as 8 peças-com-lugar de cada sorteio; as outras 42 consultas têm o vizinho, nem a gémea, fora do lote. «Falsa» = a peça aparece para um lado cuja vizinha verdadeira não é ela.)

**[V]** A lista «top-3 por lado» enche-se sempre (≈ 3·M/N ≈ 4,7 aparições por peça com M = 50, N = 32): cada peça do lote aparece, em média, **em 4 lados livres errados** (N = 32) ou 1,4 (N = 100). **Com o filtro de margem ≥ 1,5 as falsas por peça caem para 0,01–0,12 (cumpre o alvo ≤ 0,2)**, mas o filtro custa a cobertura de 9.2: só ≈ 20–39 % (N = 32) e 9–23 % (N = 100) dos lugares chegam a ter proposta confiante. O recall do top-3 (alvo ≥ 90 %) só é atingido em N = 32 com erosão (91,3 %); sem erosão 83 % / 72 %. O recall **com** filtro não foi medido em C **[NT]**; o limite superior é a «cobertura» de 9.2.

## 10. Veredicto do passo 4 e o que diz sobre M6/M11

**[F] para propor sem o vizinho garantido; [NT] para o caso «o vizinho está no lote» com lista de ajuda.**

1. **Vizinho presente, pool de lote** (A): E4 [F]; E5 chega a 64–77 % em N = 32 e a 48–65 % em N = 100, abaixo do alvo de 85 % (e, sem erosão em N = 100, abaixo do limiar de falha). Dar «as 3 melhores» (E5 top-3 85 % sem erosão e 91 % com erosão em N = 32; 71 % / 83 % em N = 100) é o ponto em que a ferramenta começa a servir **como ajuda a quem já sabe que a peça está lá**, não como proposta.
2. **Vizinho ausente** (B): o caso comum (π ≈ 1 %) dá precisão de 3–5 % em τ = 1,5. **Um M6 que proponha encaixes solta–solta a partir de um lote aleatório com estes lados gera 20–35 falsas por cada certa [V]; não é viável.**
3. **Direção inversa** (C): sem filtro cada peça é sugerida a ≈ 4 lados errados (N = 32); com filtro quase nenhuma falsa, mas também poucos acertos.

**M6 (encaixe solta–solta): [F] com estes lados. M11 (molde do buraco):** o teste certo é com 2–3 vizinhos conhecidos, que este passo **não mediu [NT]**; o lado isolado dá o limite inferior (E5 top-3 85–91 % em N = 32 quando a peça está lá). Dois vizinhos podem ajudar (erros de acaso independentes), mas o viés da silhueta é comum aos dois lados do mesmo encaixe, por isso o ganho é incerto **[NT]**.

**Bloqueio dominante (medido):** não é o tamanho do pool (N = 32 já dá o melhor E5 e ainda falha o caso comum) nem as gémeas (§3: 3 % das falhas); é a **falta de poder discriminativo de um lado lido da silhueta** (RMS do vizinho verdadeiro 1,11 mm contra 1,79 de pares aleatórios, §1) **combinada com a baixa prevalência** (π ≈ 1 %): uma taxa de falsas de 3–9 % em 99 % das consultas (sem vizinho) afoga os poucos acertos. A erosão de 0,48 mm vale +13 pontos de E5 top-1 (N = 32) e ×2,4 no E4: o viés da silhueta é a parte tratável.

**Mudanças que o atacariam, SEM implementar [NT, nenhuma medida aqui]:**
1. **Forma sem viés** (M3/M4): contorno por linha de corte ou modelo de sombra, em vez de silhueta + erosão isotrópica; ordem de grandeza do ganho = a que a erosão já mostra (E4 top-1 em N = 32: 17 % → 41 %).
2. **Sinal ortogonal da arte:** o lugar de uma consulta é uma **célula conhecida** do tabuleiro (a arte está registada), logo cada candidato pode ser testado 1-contra-1 contra a arte dessa célula (`locate.de_cell`), como no gémeo; independe da forma.
3. **Restrição de lote fechado:** afetação conjunta lados × peças (cada peça num só lugar, cada lugar numa só peça) em vez de consultas isoladas; as falsas por peça (§9.3) caem porque uma peça sugerida a 4 lados só pode ficar com um.
4. **Imagem mais discriminativa:** a continuidade em Lab mediana (12 pontos, banda 1–2,5 mm) dá E5 de 13 % na relva; gradientes/textura através da aresta e calibração de cor entre scans.
5. **Molde do buraco com ≥ 2 vizinhos** (E-buraco) como o teste a fazer antes de decidir M11.

**Limitações [NT]:** os pools saem de 814 peças que só cobrem céu e relva (o meio do puzzle quase não tem GT); π ≈ 1 % é uma estimativa (lote de 32 em ≈ 2400 por colocar) e as precisões a π são **derivadas**, não sorteadas; K = 8 lugares em C é uma escolha fixa; o recall com filtro em C não foi medido; a erosão de 0,48 mm foi usada sem ajuste mas veio de outro GT (E-real).

## 11. Passo 5 — buracos virtuais (M11, medição). **Critérios fixados em 2026-11-06, ANTES de correr**

Medição, não produto: `src/` e `projects/alpes` não são tocados; não há `src/fit.py`. Código: `tools/diagnostico/fit/buracos.py` (definição dos buracos e porta), `buraco.py` (avaliação), reutilizam `pool.py` e `fit_eval.py` (mesmos lados, cordas, tiras, E4, E5, mapa de gémeas, GT).

**Pergunta.** O que falha com um lado isolado (E5 top-1 48–77 % com o vizinho presente, §9) fica resolvido com 2–4 vizinhos do mesmo buraco? Os erros dos lados de um mesmo buraco podem estar correlacionados (o viés da silhueta é sistemático), por isso a resposta não é óbvia.

**1. Buracos virtuais e porta (contagem feita antes de fixar o resto, não é resultado).** Buraco = peça física X com ≥ 2 vizinhas ortogonais cuja adjacência vem do GT (proveniência a layout explodido, b GT manual, d confirmada; **nunca** `legado_scan`, foto, gémea, imagem ou encaixe: são os mesmos pares de `gt_pairs.json`). X é «retirada por código»: só se usam os lados das vizinhas (como estão) e o lado de X que olha para cada uma (referencial do representante de X). Descartados: 3 buracos com duas vizinhas no mesmo lado de X (GT inconsistente) e 106 peças com < 2 vizinhas. **Porta (≥ 100 buracos): 467 buracos [V]** — por nº de vizinhas **2: 175, 3: 191, 4: 101**; por zona céu 196, relva 240, montanha/floresta 12, vale/aldeia 19; proveniência: 91 com pelo menos uma adjacência b/d, 376 só de layout (a). Vizinhas «presentes» = as que o GT tem (o layout não tem todas as 4 de uma peça interior; um buraco de 2 vizinhas é um buraco de 2 vizinhas conhecidas, não de 2 reais). O meio do puzzle quase não tem GT (31 buracos fora de céu e relva): conclusões fora delas são [NT].

**2. Alvos (do plano, E-buraco).** E4 (só forma): **certa-ou-gémea em top-1 ≥ 90 %**; E5 (forma + imagem): **a certa (estrita) em top-1 ≥ 85 %**; **falha** se qualquer dos dois < 60 %. Avaliados em **N = 32 e N = 100** (lote real) e, para referência, no pool completo; por nº de vizinhas (2/3/4) e no total.

**3. Custo conjunto (declarado, não se afina).** Para uma candidata Z (peça física do pool) e uma rotação r ∈ {0,1,2,3} (o lado de Z que olha para a vizinha k é o índice `(xs_k + r) mod 4`, onde `xs_k` é o lado de X que lhe olha), **J_r(Z) = média sobre as vizinhas k do custo do lado c_k**, e **J(Z) = min_r J_r(Z)** (a rotação da solta é desconhecida e tem de ser a mesma para todas as vizinhas). Custo de lado: E4 = `rms` (mm) do `side_complement`; E5 = `rms/1,1 + ΔE_img/10` (as constantes do §5 de GT.md). Um lado é **∞** se não passa o tipo (T↔B) ou as cordas, ou (E5) se não tem imagem válida (a convenção dos passos anteriores); então J_r = ∞. Média (não soma): mantém a escala comparável entre 2, 3 e 4 vizinhas e a margem d2/d1 interpretável. A ordem é por peça (não por lado). **Acertos:** `strict` = Z* (a peça de X); `lenient` = Z* ou uma gémea dela (o mapa de gémeas por silhueta de `fit_eval.twin_map`).

**Comparações (pares nos mesmos sorteios).** (a) **lado isolado, média das vizinhas**: o mesmo ranking por peça mas só com a vizinha k, média do top-1 sobre as k; (b) **melhor lado a posteriori (oráculo)**: o buraco conta como acerto se **alguma** vizinha sozinha põe Z* em top-1 (limite superior de «escolher o melhor lado»; não é implementável porque usa a verdade); (c) **o que se esperaria com erros independentes**: o mesmo conjunto de concorrentes, mas o custo de Z* em cada lado é substituído por um custo de verdadeiro tirado ao acaso do conjunto empírico dos custos de verdadeiro de **todos** os lados (inclui os ∞, com o tipo T/B da vizinha igual) — mantém as margens e rompe a correlação dentro do buraco; 200 sorteios por buraco e por pool, mesma semente. **Correlação dos erros:** por buraco e por par de vizinhas (k, l), a correlação de **Spearman** entre os percentis do custo E4 de Z* em cada lado (percentil entre os candidatos que passam no pool completo; ∞ = 1,0), com intervalo por bootstrap sobre os buracos (1000 reamostragens, semente fixa); controlo: a mesma estatística com pares de **buracos diferentes** (≈ 0 se a medida é limpa); secundária: Pearson do RMS verdadeiro (mm). **Regra de leitura (fixa):** ρ ≥ 0,30 com o IC inferior > 0 ⇒ erros correlacionados; ρ < 0,15 ⇒ não correlacionados; entre os dois, inconclusivo.

**Pools.** Z* + N−1 peças aleatórias, N ∈ {32, 64, 100} e o **pool completo** (todas as peças físicas), **200 sorteios por buraco** (1 no completo, determinístico), semente `numpy.random.default_rng(20261106 + N)` (a mesma nas duas condições). **As peças vizinhas (e as suas duplicadas físicas) nunca entram no pool**, nem a própria X salvo como Z*. **Erosão:** só 0 e 0,48 mm (o valor do §4, **não varrido**); as vizinhas e as candidatas usam a mesma condição.

**4. Peça ausente do lote.** Pool de N peças sem Z*, sem as gémeas de Z* e sem as vizinhas. Margem = **d2/d1 do J E5** entre as peças com J finito (< 2 candidatas ⇒ sem proposta). **Limiar de operação τ = 1,5** (o `margin_min` do perfil); curva em τ ∈ {1,0; 1,1; 1,25; 1,5; 2; 3; 5}. Por τ, N, nº de vizinhas: cobertura e precisão (presente), **propostas falsas por buraco** (ausente), precisão derivada a π ∈ {1 %, 10 %}. **Utilidade (fixa, como no passo 4):** falsas/buraco ≤ 0,05 **e** precisão a π = 10 % ≥ 90 % **e** cobertura (presente) ≥ 30 %; falha clara: precisão a π = 10 % < 50 %.

**5. Fatias e exemplos.** Wilson 95 % com n = nº de buracos (não buracos × sorteios). Fatias por nº de vizinhas, N, zona, proveniência (b/d vs só layout) e (nº, zona); as **3 piores** (≥ 20 buracos). **Doze exemplos visuais** (cv-visual-verification): do cenário **N = 100, E5 estrito, sem erosão**: 6 acertos (1 em cada ⌊H/6⌋, sem escolher bonitos) e 6 falhas pelo **pior rank no pool completo** (desempate pelo id), com a candidata (a melhor J) **colocada no buraco** e as vizinhas por perto.

**6. Veredicto:** [V] se o intervalo de Wilson fica todo do lado certo do alvo; [F] se o limite superior fica abaixo da fronteira de falha; [NT] caso contrário. Se falhar, diz-se se o bloqueio é o **viés sistemático** (erros correlacionados; leitura pela regra acima e por real vs independente) ou **falta de vizinhas** (por nº de vizinhas), e que mudanças o atacariam, **sem implementar**. Nada se afina depois de ver os números; qualquer variante extra fica marcada pós-hoc.

## 12. Passo 5 — resultados (2026-11-06; critérios do §11, nada afinado depois de ver os números)

Reprodução: `python tools/diagnostico/fit/buraco.py` e `FIT_SHRINK=0.48 python tools/diagnostico/fit/buraco.py` (≈ 1 min cada; `buraco.json`, `buraco_encolhido.json`), `buraco_controlo.py` (controlo pós-hoc, §12.5), `figs_buraco.py` (exemplos). **Sanidade [V]:** com 1 só vizinha o mesmo custo (por peça, mínimo das 4 rotações) dá no pool completo E5 top-1 21,9 % (sem erosão), o mesmo sistema do §1 (19,9 % por lado, N = 805); não houve custos de imagem em falta (NaN = 0). 467 buracos: 2 vizinhas 175, 3 vizinhas 191, 4 vizinhas 101 (zonas e proveniência no §11).

### 12.1 Vizinha presente (n = 467 buracos; Wilson 95 %)

| N | custo | E4 certa-ou-gémea top-1 | E5 certa (estrita) top-1 | E5 top-3 |
|---|---|---|---|---|
| **sem erosão** | | | | |
| 32 | conjunto | 69,4 % (65,1–73,4) | **87,8 %** (84,5–90,5) | 90,3 % |
| 64 | conjunto | 62,0 % | 86,1 % (82,6–88,9) | 89,9 % |
| 100 | conjunto | 56,9 % (52,4–61,4) | **84,6 %** (81,0–87,6) | 89,3 % |
| completo | conjunto | 36,2 % (32,0–40,6) | 74,5 % (70,4–78,3) | 83,1 % |
| **erosão 0,48 mm** (1 ponto) | | | | |
| 32 | conjunto | **88,3 %** (85,0–90,8) | **93,0 %** (90,2–94,9) | 94,4 % |
| 64 | conjunto | 85,0 % | 92,0 % (89,3–94,2) | 94,2 % |
| 100 | conjunto | 82,2 % (78,5–85,4) | **91,2 %** (88,3–93,5) | 93,8 % |
| completo | conjunto | 66,8 % (62,4–70,9) | 85,2 % (81,7–88,2) | 90,1 % |

**Contra um lado isolado (mesmos sorteios):** E5 top-1 em N = 32 / 100: lado isolado (média das vizinhas) **69,2 % / 51,7 %** sem erosão (80,0 % / 67,4 % com); conjunto **87,8 % / 84,6 %** (93,0 % / 91,2 %). E4: 18,1 % / 8,0 % → 69,4 % / 56,9 % (41,1 / 23,3 → 88,3 / 82,2 com erosão). O **melhor lado a posteriori (oráculo, não implementável)** dá 92,6 % / 81,6 % (96,4 / 90,9): o conjunto iguala ou aproxima o oráculo sem saber qual é o lado bom. **Se os erros fossem independentes** (custo do verdadeiro tirado de outros buracos): E5 84,2 % / 78,1 % (90,0 / 85,4) — o **real é ≥ ao independente** (+3 a +7 pontos), não pior.

### 12.2 Correlação dos erros entre os lados do mesmo buraco [V]
Spearman dos percentis do custo E4 do verdadeiro, 1354 pares não ordenados (175 + 3·191 + 6·101), por buraco: **ρ = −0,017** (IC bootstrap −0,069 a +0,034; com erosão −0,035, −0,088 a +0,018); controlo (2.º membro de outro buraco) −0,001 ± 0,017. Pearson do RMS verdadeiro (mm): 0,042 (−0,013 a 0,102; com erosão 0,055). Por nº de vizinhas (Spearman, sem erosão): 2 → −0,116; 3 → −0,027; 4 → +0,015. **Pela regra fixa (ρ < 0,15): não correlacionados.** Ou seja, **o viés da silhueta, sendo sistemático no nível absoluto (±1 mm), não se traduz em erros que se somem entre lados do mesmo buraco** quando se mede em ordem (percentil entre candidatos): os 2–4 lados trazem informação **independente**, e é isso que explica o salto de 69 % → 88 % (E5, N = 32).

### 12.3 Por nº de vizinhas, zona e proveniência (E4 certa-ou-gémea / E5 estrita, top-1, sem erosão → com erosão)

| fatia | n | N = 32 | N = 100 | pool completo |
|---|---|---|---|---|
| 2 vizinhas | 175 | 52 / 89 → 82 / 94 | **33 / 83** → 69 / 90 | 14 / 69 → 39 / 81 |
| 3 vizinhas | 191 | 78 / 88 → 94 / 94 | 66 / 85 → 91 / 93 | 42 / 75 → 83 / 87 |
| 4 vizinhas | 101 | 84 / 85 → 89 / 89 | 81 / 85 → 88 / 89 | 63 / 84 → 84 / 89 |
| céu · relva | 196 · 240 | 69 / 89 · 73 / 86 | 56 / 88 · 61 / 82 | 34 / 82 · 40 / 68 |
| b/d · só layout | 91 · 376 | 67 / 84 · 70 / 89 | 54 / 79 · 58 / 86 | 27 / 63 · 38 / 77 |

(montanha/floresta n = 12 e vale/aldeia n = 19 ficam abaixo do n ≥ 20 das fatias; no meio do puzzle o GT é quase inexistente: **[NT]**.)

**As 3 piores fatias (n ≥ 20; E5 estrito top-1):** sem erosão em N = 32: (1) **4 vizinhas · relva** 82,1 % (n = 56), (2) **GT independente do layout (b/d)** 83,9 % (n = 91), (3) **4 vizinhas** 85,1 % (n = 101); em N = 100: (1) **2 vizinhas · relva 76,7 %** (n = 77; E4 só 37 %), (2) b/d 78,7 %, (3) relva 81,5 %. Com erosão em N = 32: 4 vizinhas · relva 87,5 %, b/d 89,1 %, 4 vizinhas 89,1 %. **Mais vizinhas não melhoram sempre o E5**: 4 vizinhas não é melhor que 3 (85 % vs 88 %, sem erosão), porque cada lado a mais é mais uma ocasião de a peça certa falhar o filtro (§12.4). O E4 (só forma) com **2 vizinhas** é fraco (52 % em N = 32, 33 % em N = 100): com 2 lados a forma ainda não chega.

### 12.4 Onde falha (rank da certa no pool completo; sem erosão → com erosão)
**45 de 467 (9,6 %) → 26 (5,6 %) buracos têm a peça certa fora dos filtros** (algum lado falha as cordas/tipo ⇒ custo ∞): 2 vizinhas 5,7 %, 3 vizinhas 10,5 %, **4 vizinhas 14,9 %** (com erosão 2,9 / 5,2 / 10,9 %); mais 74 → 43 buracos com a certa a rank finito > 1. Nos exemplos (§12.6) as 6 piores falhas são **todas** deste tipo: a certa **encaixa à vista** mas o perfil lido falha uma corda; a «vencedora» é a de menor custo entre as que passam e visivelmente **não encaixa** (sobrepõe-se às vizinhas ou deixa folga). É a mesma causa raiz do §3: silhueta com viés ≈ 1 mm (M3/M4), agora amplificada por o filtro ser duro em cada lado.

### 12.5 Controlo pós-hoc: o viés «mesma digitalização» [V, limitado]
Preocupação: a peça certa e as vizinhas vêm da mesma folha de scan; se o E5 se apoiasse na diferença de cor entre scans, a certa ganhava por isso. Controlo (N = 32, 303 buracos com ≥ 31 concorrentes da mesma folha), concorrentes só da **mesma folha** / só de **outras folhas** / aleatórios: E5 certa top-1 **87,1 % / 91,4 % / 91,1 %** (com erosão 95,0 / 96,2 / 96,0); E4 71,7 / 70,6 / 70,4 (89,3 / 91,0 / 90,8). Concorrentes da mesma folha são ligeiramente **mais difíceis**, não mais fáceis: **não há atalho de folha [V]**. **Limite [NT]:** na vida real a peça certa é uma solta de **outro** scan que as vizinhas da tabuleiro; isto não se mediu (só 6 ligações físicas entre scans); a calibração de cor entre scans (M9) é o risco.

### 12.6 Exemplos visuais (cv-visual-verification)
[`exemplos_buraco_acertos.jpg`](exemplos_buraco_acertos.jpg): 6 acertos (1 em cada ⌊H/6⌋ dos 403 com top-1 em ≥ 50 % dos sorteios a N = 100; **não escolhidos**: P0002, P0087, P0279, P0440, P0555, P0733 — 3 céu, 3 relva, 2–4 vizinhas); os contornos amarelos (vizinhas) e ciano (a certa colocada no buraco) coincidem. [`exemplos_buraco_falhas.jpg`](exemplos_buraco_falhas.jpg): 6 falhas pelo pior rank no pool completo (empate pelo id): P0001, P0012 (céu), P0031, P0034, P0035, P0063 (relva), todas de 3 vizinhas e todas com a certa **fora dos filtros**; à esquerda a certa, à direita a vencedora do E5 conjunto (P0776 rot 3, P0763 rot 3, P0445 rot 0, P0398 rot 3, P0579 rot 2, P0089 rot 1): **a certa encaixa e a vencedora não** [V visual]. Dados em `exemplos_buraco.json`. Como todas as 6 piores têm rank ∞ (nenhuma «rank 2, 3…» em empate), a seleção «pior rank» mostra só o modo de falha dos filtros, não os quase-empates (74 buracos com a certa em rank finito > 1, ver 12.4).

### 12.7 Peça ausente do lote (curva precisão–cobertura; margem d2/d1 do E5 conjunto)
τ = 1,5 (fixo). Sem erosão / com erosão; falsas = propostas com a peça ausente por buraco.

| N | cobertura (presente) | precisão (presente) | **falsas/buraco** | precisão π = 1 % | π = 10 % |
|---|---|---|---|---|---|
| 32 | 50,1 / 63,4 % | 97,7 / 98,9 % | **0,122 / 0,138** | 3,9 / 4,4 % | 30,7 / 33,5 % |
| 64 | 48,0 / 64,8 % | 97,4 / 98,9 % | 0,111 / 0,127 | 4,1 / 4,8 % | 31,7 / 35,7 % |
| 100 | 44,2 / 63,2 % | 97,2 / 98,9 % | **0,103 / 0,118** | 4,0 / 5,1 % | 31,3 / 36,9 % |

Por nº de vizinhas (sem erosão, τ = 1,5, N = 32 → N = 100): falsas/buraco 2 vizinhas 0,112 → 0,043; 3 vizinhas 0,167 → 0,134; 4 vizinhas 0,053 → 0,150; precisão a π = 10 %: 36 → 51 % (2), 25 → 26 % (3), 39 → 25 % (4). Com τ = 2,0 (N = 100): falsas 0,010 (2 vizinhas) a 0,063 (4), cobertura 13–32 %, precisão a π = 10 % 28–60 %. **Critério de utilidade (falsas ≤ 0,05, precisão a π = 10 % ≥ 90 %, cobertura ≥ 30 %): não cumprido em nenhum ponto; precisão a π = 10 % < 50 % em quase todos [F].** A π = 1 % (o caso comum de um lote) a precisão é 4–5 %: ≈ 19–25 propostas falsas por cada certa.

## 13. Veredicto do passo 5 e o que diz sobre M11

**Pergunta:** com 2–4 vizinhas o que falhava com um lado isolado resolve-se? **Sim para «a peça está no lote»; não para «propor sem ela garantida».**

1. **E5 (forma + imagem), a certa em top-1, alvo ≥ 85 % [V com erosão]:** com a erosão de 0,48 mm: 93,0 % (N = 32, IC 90,2–94,9), 92,0 % (N = 64), 91,2 % (N = 100, IC 88,3–93,5): **cumprido, o IC inteiro acima de 85 %**. Sem erosão fica em 87,8 % (N = 32) e 84,6 % (N = 100) com IC a cruzar os 85 % **[NT]**. No pool completo 85,2 % (81,7–88,2, com erosão) [NT] e 74,5 % (sem). **Nunca abaixo da fronteira de falha (60 %)** nos pools de lote.
2. **E4 (só forma), certa-ou-gémea em top-1, alvo ≥ 90 % [não cumprido]:** o melhor é 88,3 % (N = 32, com erosão, IC 85,0–90,8: [NT]); em N = 100 82,2 % (78,5–85,4) abaixo do alvo; sem erosão 69,4 % / 56,9 %. No pool completo [F] (36,2 %, IC 32,0–40,6, abaixo dos 60 %). **A forma sozinha continua a precisar do contorno sem viés; é a imagem que fecha o alvo com 2–4 vizinhas.**
3. **Ganho do conjunto [V]:** E5 top-1 N = 32: 69,2 % (um lado) → 87,8 % (conjunto); sem erosão N = 100: 51,7 % → 84,6 %; o oráculo do melhor lado é 92,6 % / 81,6 %.
4. **Erros correlacionados? [V não]:** ρ = −0,02 (IC −0,07 a 0,03); o real bate ao «independente». **O bloqueio não é o viés sistemático a somar-se entre lados.**
5. **Peça ausente [F]:** 10–14 % de buracos com proposta falsa a τ = 1,5, precisão 4–5 % a π = 1 % e 31–37 % a π = 10 %; nenhum τ resolve (a cobertura cai antes). **Um M11 que «vá dizendo onde cada peça do lote cabe» sem saber que a peça existe gera ≈ 20 falsas por certa.** Para a **direção da GUI** (cada peça solta contra os N buracos da tabuleiro) as falsas por peça multiplicam-se pelo nº de buracos: **não medido [NT]** (era o passo seguinte).

**O que isto diz sobre M11/M6.** M11 (molde do buraco) com 2–4 vizinhas conhecidas é viável **como ranking** (top-3 do E5: 89–94 % em lotes de 32–100) para uma peça da qual **se sabe que está no lote** ou para o ecrã «candidatas para este buraco», e **não** como proposta autónoma. M6 (solta–solta, sem vizinhas fixas) continua [F] (§10).

**Bloqueio dominante (medido), por ordem:** (a) **a peça certa falha o filtro duro** (5,6–9,6 % dos buracos; 10,9–14,9 % com 4 vizinhas) por viés da silhueta nas cordas/tipo — causa de todas as 6 piores falhas; mais vizinhas = mais ocasiões de falhar; (b) **sem calibração absoluta, a melhor candidata propõe-se sempre** (10–14 % de falsas por buraco); (c) E4 sozinho a 2 vizinhas (52 %, N = 32) — a imagem faz o trabalho; (d) **cor entre scans [NT]**. Não é falta de vizinhas (2 vizinhas dão E5 89 % a N = 32, 94 % com erosão) nem correlação de erros.

**Mudanças que o atacariam, SEM implementar [NT, nenhuma medida aqui]:**
1. **Forma sem viés** (M3/M4: linha de corte ou modelo de sombra, ou a erosão calibrada por modalidade): a erosão de 0,48 mm já tira 42 % das falhas de filtro (45 → 26) e leva o E5 de 87,8 → 93,0 % a N = 32.
2. **Filtro mole em vez de duro** por lado: penalização graduada acima da corda em vez de ∞, para uma só corda mal lida não anular uma candidata que encaixa nas outras vizinhas (precisa de validação fora da amostra).
3. **Rejeição absoluta + margem:** exigir também que o custo conjunto d1 seja compatível com o de um verdadeiro (calibrado nos buracos com a certa, fora da amostra) antes de propor; hoje só a margem relativa.
4. **Afetação conjunta** buracos × peças do lote (cada peça num buraco, cada buraco numa peça): reduz as falsas por peça na direção da GUI.
5. **Normalização fotométrica entre scans** (M9) e medir com a certa de **outro** scan (os 6 pares físicos de §12.5 são poucos; vale um GT com re-digitalização).
6. Medir a **direção inversa** (cada solta contra todos os buracos da tabuleiro) e os **buracos reais** (as células vazias do tabuleiro com 2–4 vizinhas, sem GT da peça que lá vai).

**Limitações [NT]:** o GT cobre sobretudo céu e relva (31 buracos de outras zonas); 376 dos 467 buracos têm adjacências só do layout (84/84 verificadas onde havia b/d); os «buracos» são virtuais (a peça existe e vem da mesma folha das vizinhas); o oráculo e o «independente» são referências, não métodos; a erosão de 0,48 mm vem do E-real, não deste GT.
