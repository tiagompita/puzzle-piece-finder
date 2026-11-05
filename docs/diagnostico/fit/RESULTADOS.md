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

**Próximos passos baratos [NT]:** varrimento por tamanho de pool (32/100/300/814) sobre o mesmo GT; E-buraco com 2–3 vizinhos; medir o RMS verdadeiro com o contorno por linha de corte (secções de céu e legado) em vez da silhueta; hold-out do desvio isotrópico com validação cruzada metade/metade.
