# Estado e plano — Puzzle Piece Finder

_2026-10-29. Diagnóstico feito sobre HEAD `c35442f`, sem alterar `src/`. Evidência em `docs/diagnostico/` (imagens, `RESULTADOS.md` e `results.json` por área). Mapa do código em [`ARCHITECTURE.md`](../ARCHITECTURE.md). Atualizado 2026-10-30: grelha 64 × 47 confirmada por contagem; simetria de rotação de 180° (1504 pares de gémeos, fisicamente intercambiáveis) verificada à mão e medida (E-sym rigoroso, `docs/diagnostico/gemeos/`); objetivo principal passa a "encontrar o gémeo"; lado como unidade ("memória de cortes", molde do buraco); secção montada: linhas de corte e fotometria; marcos reordenados._

Convenção de etiquetas usada em todo o documento:
- **[V]** verificado nesta sessão, com evidência apontada;
- **[NT]** não testado;
- **[F]** testado e falha;
- **[fonte]** afirmação externa com link; **[S]** só vista em resumo de pesquisa, não lida na página.

---

## 1. Resumo executivo

1. O código está mais avançado do que o README sugere: segmentação, classificação de bordas, motor de matching, textura, visualização, GUI e exportação JSON existem e correm **[V]**.
2. O que não existe é **verdade de terreno**: nenhuma peça tem posição conhecida. Todas as afinações anteriores foram feitas contra o próprio rótulo `high` do motor, que é um proxy, não um acerto **[V]**.
3. Em dados sintéticos (recortes da própria referência) o motor localiza 72 % top-1 / 82 % top-5 e o rótulo `high` é 100 % preciso (28/28) **[V]**. Com peças reais digitalizadas, as duas referências do repo **não concordam em 0/61 peças** e nenhum crop previsto se parece com a peça **[V]**. Causa (corrigida em 2026-10-30): o scanner é fiel à arte (L\* do scan ≈ 1,06·L\* da arte + 1,3, desvio uniforme ≈ +5 L\*) e as 61 peças de julho (L\* mediano 86,4) são mesmo claras, nuvens e pôr do sol: o 0/61 vem de **peças claras de céu e nuvem sem textura** (limite da arte) e de uma **referência que é foto da caixa com margem** **[V, `docs/diagnostico/gemeos/SECCAO.md` §C]**. A explicação anterior ("desfasamento de captura do scanner") é falsa **[F]**; a normalização fotométrica do M9 reduz-se a um deslocamento de ≈ −5 L\*. Fica por explicar porque 43/61 peças são claras quando só 8–14 % da arte tem L\* ≥ 80 **[NT]** (pergunta 8.2.9).
4. A referência `PuzzleOriginal.jpeg` é uma **foto da caixa** com margem branca e texto; o motor procura nessa margem e o prior de borda assume o contrário **[V]**.
5. A suite pytest **não estava verde** a 29-10: o teste de segmentação falhava desde o commit `f6cc2b7` (10-jul), o mesmo dia em que foi escrito **[F]**; outro teste dependia da ordem de `cv2.boxPoints`, que mudou no OpenCV 5 **[F]**. Reposta no M0 (`7c9fa89`): 6/6 nos dois OpenCV, reconfirmado em 2026-10-30 **[V]**.
6. A documentação anterior descreve a arte como "deserto/areia"; é a paisagem alpina de Val di Funes; as peças claras são céu e nuvens **[V]**.
7. A ideia dos "moldes de recorte" tinha uma metade sólida e uma metade por verificar; a segunda ficou verificada em 2026-10-30. Sólida: com o scanner a 300 dpi medem-se lados a ±0,2 mm, a topologia (tab/blank/flat) é estável entre scans (100 % em 147 pares) e a forma identifica uma peça re-digitalizada em 83–91 % dentro de um conjunto de 61 **[V]**. Verificada: **o recorte repete-se por rotação de 180°**. A peça (l, c) tem o mesmo recorte que (48 − l, 65 − c) rodada 180° (64 é par: nenhuma peça é o próprio gémeo, logo 1504 pares), conferido à mão pelo Tiago (bordas; interior (2,2)↔(46,63)) e medido no E-sym rigoroso com 20 pares de borda: gémeo A1/B2 0,29 mm, A2/B2 0,39 mm (pose oposta), re-scan A1/A2 0,27 mm, não-gémeo mais próximo mínimo 0,60 mm, top-1 20/20 **[V, contorno híbrido + métrica free, `RESULTADOS.md`]**. Com a fronteira de `segment_pieces` o teste falha (gémeo 1,01 mm corner e 1,42 mm free, top-1 13/20 e 8/20): a causa é a segmentação, não o puzzle **[V]**. Grupos de 4 excluídos à mão (colunas 5, 10 e 12: nada coincide com os deslocamentos de 16 ou de 32 colunas nem com 33−c rodada), por isso só pares; o centro (colunas 32/33, linha 24) não é testável. A amostra de julho (mínimo 0,85 mm em 1830 pares) é consistente: esperados 0,61 pares, P(0) ≈ 0,54.
8. A grelha é 64 × 47 = 3008 peças **[V, confirmada por contagem pelo Tiago, 2026-10-30]**; 218 de borda (= 2·(64+47) − 4), para os Clementoni 3000 de 118,4 cm [fonte jigsaw-wiki]. As células não são quadradas: razão ≈ 1,03 medida na secção montada (passos 18,4–18,5 × 18,9–19,0 mm), igual à de 64 × 47; 64 × 48 fica fechado **[V]**. Cortes internos: 63·47 + 64·46 = 5905, ≈ 2953 distintos sob a simetria.
9. Objetivo (revisto em 2026-10-30): **encontrar o gémeo**. Para uma peça colocada em (l, c), achar entre as soltas o seu gémeo, que pertence à célula (48 − l, 65 − c), por forma (cordas dos lados, métrica free, classe topológica) com **desempate obrigatório pela zona da imagem**. Os gémeos são **fisicamente intercambiáveis** (uma encaixa no lugar da outra; só a imagem as distingue; é também um modo de erro humano que o programa pode detetar). A seguir vêm o encaixe entre vizinhos e o **molde do buraco** (memória de cortes: o lado é a unidade). A localização na caixa fica como prior fraco para peças com textura. É o que a literatura faz com peças reais; ninguém localiza uma peça de céu entre 3000 por template matching.
10. Feito em 2026-10-30: E-sym rigoroso (M5, decidido) e secção montada (linhas de corte, localização, fotometria). Próximo: M1 (GT com as 40 peças do E-sym e as células da secção) → M2 → M3/M4 → M10 (`src/twin.py`). M0 (base de medida) está feito. Ordem completa na secção 7.

---

## 2. Mapa do projeto

Ver [`ARCHITECTURE.md`](../ARCHITECTURE.md) para módulos, contratos e pontos de entrada. Resumo do que importa aqui:

- Fluxo real: `segmentation.segment_pieces` → `edges.classify_pieces` → `matching.multi_scale_template_match` (assinatura Lab 4×4 a ≈46 px/peça, 4 rotações, textura, prior de borda, gap de confiança) → GUI/`visualization`. Só a GUI liga tudo.
- Cronologia (git) **[V]**: projeto criado 11-ago-2025 (CLI ingénua + docs em inglês). Silêncio até 9-jul-2026. Em **9–11 de julho de 2026** (≈48 h, 20 commits) foi escrito praticamente tudo: motor zonal Lab, textura, prior de borda, segmentação com seam-carve, suite pytest, ROADMAP, RELATORIO, scans dos 11 fundos. Último commit de código: 11-jul. Em 29-out: skills e 5 fotos de telemóvel. Sem branches, sem stash, árvore limpa.
- O que foi tentado e abandonado, segundo os próprios commits: inpaint de glare (revertido), watershed de cor (substituído por seam-carve), fundo branco (substituído por fundos de cor).
- Código morto/órfão **[V]**: `gpu_test.py`, `test_scales.py`, `temp_import_test.py`, `use_gpu` (aceite e ignorado), `compare_images`/`sliding_window_search` (só a CLI usa), `images/puzzles/pexels-*.jpg`, `requirements-dev.txt` com sphinx/jupyter/mypy nunca usados, `examples/README.md` lista 4 scripts dos quais só 1 existe.
- README vs código **[V]**: README promete `piece_0.png…23`, `puzzle.json`, `data/`, GPU/CUDA, "overlap detection", segmentação "in development". Nada disso corresponde. O CLAUDE.md fala em métodos duplicados na GUI e imports relativos partidos: não se reproduz (`python -m src.main` e `python -m src.gui` importam **[V]**).
- Skills pedidas: `cv-visual-verification` e `piece-fit-matching` existem e foram seguidas; `project-cartographer` e `systematic-debugging` **não existem** em `.claude/skills/` nem na lista de skills visível ao Claude Code local nesta sessão (serão skills da conta claude.ai, nota 5 da `revisao.md`) — o ARCHITECTURE.md e a fase 2 foram feitos à mão no mesmo espírito.

---

## 3. Estado por etapa, com evidência

Ambiente usado: Python 3.13; a máquina não tinha `cv2` instalado no interpretador global. Criei dois venvs no scratchpad: OpenCV 5.0.0 e OpenCV 4.11.0 (numpy 2.2, Pillow 11). `requirements.txt` não fixa versões.

### 3.1 Testes existentes **[F]**

| OpenCV | Resultado | Causa |
|---|---|---|
| 4.11 | 5/6 passam | `test_segment_recovers_all_rectangles` falha: o retângulo azul (650,100,150×120) sai com bbox (595,40,211×202), inflada. Bisseção por commit: passa em `78804c0`, falha a partir de `f6cc2b7` (histerese + refinamento de fronteira), i.e. **o teste foi quebrado no próprio dia em que foi adicionado e nunca voltou a correr**. Imagem: `diagnostico/segmentacao/teste_sintetico_retangulos__labels.png`. |
| 5.0 | 4/6 passam | Acima + `test_two_adjacent_flat_sides_is_corner`: `cv2.boxPoints` devolve os cantos noutra ordem no OpenCV 5; o tipo continua `corner`, só a indexação `sides[0]/[1]` muda. Brittleness do teste, não bug do classificador. |

O `RELATORIO.md` de 11-jul afirma "suite pytest anti-regressão" como feita. Não era verdade nessa data.

**M0 (2026-10-29, feito):** 6/6 testes passam com OpenCV 4.11 e 5.0. Causa raiz da regressão (implementer, com imagens intermédias): a inflação já estava na máscara bruta de `_foreground_from_bg`. O `_flatten_illumination` deixa um halo claro à volta do retângulo mais escuro (azul), e o Otsu do OpenCV, perante um histograma com um vazio entre os dois modos (bins 18–193 vazios), devolve o **primeiro** máximo (t = 17, o topo do modo de fundo); a histerese introduzida em `f6cc2b7` usa 0,85·t = 14,5 como nível baixo, que cai dentro do fundo e anexa o halo. Correção: `_otsu_plateau_threshold` (Otsu em numpy centrado no planalto de máximos empatados: t = 105,5 neste caso; idêntico ao OpenCV quando o histograma é contínuo). Verificado: as 23 imagens do diagnóstico dão contagens, clusters e tipos **idênticos** antes e depois; nos 3 scans de controlo a variação máxima de bbox e de área por peça é 0 px. O teste de edges passou a verificar adjacência cíclica dos lados retos em vez de índices fixos.

### 3.2 Pré-processamento / aquisição

- `.DNG` abre com PIL (lê a pré-visualização TIFF embutida: 6048×8064 para IMG_2114, mas **3024×4032** para IMG_2120 — nem todos os DNG trazem a mesma resolução) **[V]**.
- Scans: 11 fundos a 300 dpi (2480×3504 = A4) e 2 a 600 dpi **[V]**. O scanner dá escala absoluta (0,0847 mm/px), sem perspetiva, sem sombras, luz constante. **É a melhor câmara que o projeto tem e nunca foi explorada como tal.**
- A GUI pede W/H em cm e nº de peças; o motor recebe `pixels_per_cm` só para reportar, não para restringir escala **[V]**.

### 3.3 Segmentação (`segment_pieces`) — 23 imagens corridas, overlays em `diagnostico/segmentacao/*__contours.jpg`

| Imagem | Detetadas | Clusters | Observação (vi a imagem) |
|---|---|---|---|
| scan verde / laranja / azul | 61 / 61 / 60 | 0 / 0 / 1 | Contornos justos. Contagem física aproximada por limiar de croma ≈ 63–65 unidades, logo faltam 2–4 (incl. ≥1 par "mated" que sai como uma peça `edge`). |
| scan preto / vermelho / bege / rosa | 56 / 58 / 56 / 59 | 1 / 0 / 3 / 3 | Bom. |
| scan amarelo / amarelo-claro / verde-claro | 46 / 43 / 42 | 3 / 6 / 4 | Peças creme invisíveis em fundo pálido; contornos errados em peças pálidas (#12, #13). Limite físico de contraste, já conhecido. |
| scan verde grupo2–5 | 59 / 53 / 54 / 52 | 0 | Bom. |
| scan verde grupo6 (secções já montadas) | 25 | 3 | Grupos montados corretamente marcados `is_cluster`; 3 peças soltas junto a um grupo ficam cortadas. |
| scan impressora (branco, 600 dpi) | 61 | 1 | Bom apesar do fundo branco. 13 s. |
| IMG_2114.DNG (telemóvel, papel branco) | 72 | 0 | 64 peças físicas → 8 sobra-detecções (fragmentos/sombras). |
| IMG_2108 / 2109 / 2111 (telemóvel, tapete, peças juntas) | 56 / 73 / 69 | 15 / 20 / 13 | Mau: metade das peças em cluster ou perdidas; modelo de fundo global falha no tapete com linhas impressas. |
| IMG_2110 (telemóvel, tapete, peças espaçadas) | 175 | 5 | Surpreendentemente razoável para peças espaçadas; perde as que estão junto às secções montadas. |
| IMG_2100 (foto da caixa) | erro | — | Esperado; não é foto de peças. |

Conclusões: funciona para scans com fundo saturado e peças espaçadas (**[V]**, ≈95 % recall estimado, sem GT manual); falha em fotos de telemóvel com peças encostadas **[V]**. Defeitos que importam a jusante: franjas e "dentadas" no contorno em 9/61 peças do scan verde (#2, #6, #11, #18, #26, #27, #44, #47, #52), que são a principal fonte de ruído de forma (correlação 0,69 entre rugosidade e distância de re-scan) **[V, forma]**; variação de área da mesma peça entre scans de −5,4 % a +1,6 % **[V]**. Métrica de IoU contra máscaras manuais: **[NT]** (não há máscaras manuais). Defeitos novos, vistos nos scans dos gémeos de 2026-10-30 **[V]**: (S1) uma peça a menos de ≈ 1,2 mm do bordo do scan é descartada em silêncio (`_FRAME_MARGIN_FRAC`); (S2) a fronteira fica serrilhada no lado da sombra e morde até ≈ 1 mm nas peças escuras de prado. Detalhe em `docs/diagnostico/gemeos/RESULTADOS.md`.

### 3.4 Classificação de bordas (`edges.py`) **[V, parcialmente F]**

- Distribuição no scan verde: 60 `interior`, 1 `edge`. A análise de perfis de lado encontra 3 peças com um lado reto (#42, #54, #60; visível na montagem `diagnostico/forma/montagem_cantos_scan_verde.png`). **`edges.py` falha 2 das 3 peças de bordo** porque mede o desvio ao `minAreaRect` da peça inteira (com abas), que não é o corpo da peça.
- A GUI **não passa `piece_edges` ao motor**; o prior de borda só é exercido pelo harness `eval_matching.py` **[V]**.
- Nos scans dos gémeos (2026-10-30), `edges.py` marca como `edge` só 8 das 20 peças de borda em cada scan (A1, A2, B2) **[V]** (S3); com `shapelib` as 20 têm exatamente 1 lado F, classe igual à do gémeo.

### 3.5 Textura (`texture.py`) **[V]**

Corre e é usada (`use_texture=True` por omissão). O harness antigo media 12→13/64 `high` com textura num proxy sem GT. Na experiência A (GT sintético) o que mais discrimina acerto é a porta de **estrutura** (`piece_structure ≥ 4` → 94 % top-1; `< 4` → 44 %), mais do que o gap **[V]**. Contributo isolado da textura: **[NT]** (não corri `use_texture=False`).

### 3.6 Matching contra a imagem da caixa — `diagnostico/matching/RESULTADOS.md`

**A. Teto do motor (recortes sintéticos da própria referência, GT conhecido, n=60 degradados + 20 limpos) [V]**

| | top-1 | top-5 | precisão de `high` | `ambiguous` certo top-1 |
|---|---|---|---|---|
| degradado (blur 1 + ±6 L\*, ±3 a\*b\*) | 72 % | 82 % | 28/28 | 47 % |
| limpo | 90 % | 100 % | 7/7 | 85 % |

Céu vs resto: top-1 igual (70 % / 73 %); o céu é mais vezes `ambiguous`, como deve ser. 2/60 previsões caíram **fora da arte** (margem da caixa). O motor funciona quando as cores batem.

**B. Peças reais (scan verde, 61) contra as duas referências [V]**

| | `high` | `ambiguous` | s/peça |
|---|---|---|---|
| PuzzleOriginal.jpeg (caixa, 8064×6048) | 10 | 51 | 8,6 |
| 1186441_1.jpg (arte limpa, 1600×1200) | 20 | 41 | 7,5 |

Homografia limpa→caixa por SIFT+RANSAC: 2597 inliers, erro 4,5 px (0,04 lados) — as duas referências são comparáveis. **Concordância top-1 entre referências: 0/61** (acaso 0,4 %); 0/4 nas peças `high` em ambas. 17/61 previsões caem no mesmo "atrator" (encosta oliva à esquerda). Vi `B_montagem_10.png`: nenhum crop previsto se parece com a peça. **O rótulo `high` em peças reais não é fiável.**

Causa medida: L\* mediano das peças digitalizadas 86 (p10 59, p90 95); só 1 % (caixa) a 6 % (arte limpa) dos blocos à escala da peça atingem L\* ≥ 86, e 8–14 % atingem ≥ 80, contra 43/61 peças **[V, recomputado por mim]**. O fundo não é a causa (Δ entre fundos ≈ 1 unidade Lab). O Tiago disse que as 61 peças foram tiradas ao acaso do saco (8.2.2) e em 2026-10-29 concluí daí "desfasamento de captura" do scanner; **essa conclusão foi desmentida em 2026-10-30 [F]** (parágrafo seguinte). O motor só remove a média de L por assinatura; não compensa um deslocamento de L\*, e o croma absoluto amarelo-esverdeado leva as peças para prados **[V]**.

**2026-10-30 — fotometria medida na secção montada [V, `docs/diagnostico/gemeos/SECCAO.md` §C].** Secção de canto (44 peças) registada na arte; L\*/a\*/b\* medianos:

| Zona | Scan | Arte limpa | Foto da caixa | Scan − arte (L\*) |
|---|---|---|---|---|
| Céu da secção (mesma zona registada, 9551 px de arte) | 52,3 / −4,6 / −33,5 | 47,5 / −5,1 / −37,9 | 49,2 / 2,5 / −34,0 | +4,8 |
| A1, céu (20 peças, casas (1, c)) | 55,8 / −7,5 / −32,5 | 50,9 / −8,1 / −38,4 | 58,4 / 0,3 / −30,2 | +5,0 |
| B2, prado (20 peças, casas (47, c)) | 45,5 / −11,9 / 27,4 | 43,2 / −11,5 / 28,1 | 41,1 / −8,2 / 17,9 | +3,0 |
| Arte inteira | — | 49,0 / −1,3 / 25,7 | 49,8 / 0,3 / 18,3 | — |
| Peças de julho (`scan_verde`, 61) | 86,4 / −4,8 / 28,6 (p10 59,6; p90 94,5) | — | — | — |

- O scanner é **fiel à arte**: píxel a píxel a diferença é +4 a +6 L\* em toda a gama 39–87 (céu, nuvem, prado); ajuste por casa (n = 80, r = 0,76) L\*scan ≈ 1,06·L\*arte + 1,3. Os desvios em a\*/b\* são pequenos (céu: Δb\* +4).
- O papel verde tem o mesmo Lab em julho (77,8 / −50,5 / 47,8) e hoje (77,9–78,6 / −51,2 a −53,0 / 44,6–49,0), seja qual for o conteúdo da folha (n = 5): **não há correção automática dependente do conteúdo**.
- **Conclusão (i): composição do saco**, com um desvio pequeno e uniforme. As 61 peças de julho são claras de verdade (nuvens e pôr do sol). A causa do 0/61 fica: peças claras de céu e nuvem sem textura (limite da arte) e referência = foto da caixa com margem. A normalização fotométrica do M9 reduz-se a um deslocamento de ≈ −5 L\* mais um pequeno ajuste em b\*.
- Fica por explicar porque 43/61 peças são claras quando só 8–14 % da arte tem L\* ≥ 80 **[NT]**: o saco não estava misturado? A amostra não foi aleatória? (pergunta 8.2.9.)
- Para o desempate dos gémeos pela imagem, céu (L\* 52–56, b\* −33) e prado (L\* 45, b\* +27) separam-se trivialmente.

**C. Repetibilidade entre fundos (laranja vs verde, 22 pares) [V]**: 32 % top-1 no mesmo sítio (acaso 2 %), 0 pares `high`/`high`. Repetível, não certo.

Não testado: escala real das peças com abas (≈1,4× a célula, no limite da banda 0,8–1,3 do motor) **[NT]**; busca a 24 px/peça na arte limpa **[NT]**; impacto do prior de borda **[NT]**; a foto de telemóvel IMG_2114 (usada pelo harness antigo) contra GT **[NT]** — nunca houve GT.

### 3.7 Visualização e exportação **[V]**

`annotate_results`/`save_annotated_image` e o Export JSON da GUI funcionam (contrato em ARCHITECTURE.md §3). O ponto vermelho é desenhado no centro de `position+size/2` mesmo quando `confidence='ambiguous'`; o JSON guarda a shortlist. Não há exportação de máscaras/contornos das peças (só PNG RGBA via Save Pieces).

---

## 4. Causa raiz do abandono

Sintoma: "nada funcionava como eu queria". Causas, por ordem de importância:

1. **Sem verdade de terreno, o ciclo de desenvolvimento otimizou um proxy.** Toda a afinação de 9–11 de julho mediu "quantas peças ficam `high`" em 64 peças de telemóvel. Hoje sei que `high` é 100 % preciso em dados sintéticos e 0/61 confirmável em peças reais. O ciclo não tinha como detetar isto. Sem GT não há como saber se um `high` é um acerto ou um atrator. **[V]**
2. **Formulação do problema no limite da informação.** Uma peça de 18 mm coberta por 16 células de cor média, procurada em 3008 células × 4 rotações de uma paisagem em que ~40 % é céu/nuvem e ~30 % prado: para a maioria das peças a resposta é "ambígua" por natureza, e o próprio ROADMAP já o admitia ("limites aceites"). Os pontos fortes do motor (porta de estrutura, shortlist honesta) não mudam isso. A experiência A dá o teto: 72–90 % top-1 **com recortes da própria referência**.
3. **Referência inadequada e peças sem textura.** Referência = foto da caixa com a margem incluída na pesquisa; escala assumida a partir do nº de peças em vez da célula física conhecida; peças claras de céu e nuvem sem textura (limite da arte). Corrigido em 2026-10-30: o fosso fotométrico (L\* 86 contra 50) **não** vem do scanner, que é fiel à arte (deslocamento uniforme ≈ +5 L\*); a hipótese anterior de "desfasamento de captura" é falsa **[F]** e as peças de julho eram mesmo claras (composição do saco). Nenhuma destas coisas era compensada pelo motor. **[V]**
4. **Dívida de verificação.** Testes quebrados no dia em que nasceram, relatório que descreve outro puzzle, harness com caminho de sessão antigo, skill que exige "pytest verde" quando não está. Isto corrói a confiança e torna cada sessão uma re-descoberta. **[V]**
5. **Sprint de 48 h sem consolidação.** 20 commits em dois dias sobre módulos de 1000+ linhas; o seam-carve, a histerese e o refinamento de fronteira entraram em sequência sem re-correr a suite. Previsível que algo tenha partido. **[V, git log]**

O que **não** foi a causa: a arquitetura dos módulos (razoável), a GUI (funciona), a ausência de GPU (irrelevante), e a qualidade dos scans (boa).

---

## 5. Análise da ideia dos "moldes de recorte"

### a) A premissa é verdadeira?

**Classes topológicas** (padrão tab/blank/flat nos 4 lados): verdadeiro e trivial. Para peças interiores há 2⁴ = 16 rotulagens, 6 classes a menos de rotação (4T, 4B, 3+1, 1+3, 2+2 adjacentes, 2+2 opostos) [fonte: https://jigsawtogether.com/blog/jigsaw-piece-shapes-glossary ; Yao & Shao 2003 usam 18 modelos canónicos incluindo bordas e cantos: https://faculty.tnstate.edu/ToBeDeleted_2014_0227/fyao/MyPaper-PDF/2003/PRL-paper.pdf]. Medido no scan verde (61 peças) **[V]**: BBBT 18, BTBT 13, BTTT 11, BBTT 10, BBBB 3, TTTT 3, 3 peças com um lado F. A classe é estável entre re-scans em 147/147 pares emparelhados **[V]**.

**Classes geométricas** (forma exata): **não verificado, e a amostra aponta contra duplicados exatos.** Entre as 1830 combinações de pares do scan verde, o par mais parecido (38–39) difere 0,85 mm RMS, acima da distância mediana de uma peça à sua própria re-digitalização (0,54 mm, p90 1,96 mm). Na sobreposição (`t3_pares_mais_parecidos.png`) as abas estão deslocadas 0,5–1,5 mm ao longo do lado: mesma topologia, faca diferente **[V]**. As abas têm todas a mesma "cabeça redonda com pescoço" (mediana T–T 0,09 L) e diferem em posição, altura e largura — um lado isolado discrimina pouco **[V]**.

**Como os cortantes funcionam** (verificado em páginas lidas): corte por lâminas de aço numa matriz ("puzzle die"), prensa hidráulica ou rolo [fonte: https://en.wikipedia.org/wiki/Jigsaw_puzzle]; corte "ribbon/grid" com grelha definida e meia dúzia de formas-tipo vs "random cut" com peças únicas; a mesma matriz pode ser usada para vários puzzles [fonte: https://mindthepuzzle.com/puzzles/ribbon-cut-and-random-cut-puzzles]; a variação de tamanho, direção, inclinação e deslocamento das abas é deliberada para tornar as peças únicas; a folha desloca-se ≈1 mm no corte, daí a sangria [fonte: https://www.fabrykapuzzli.eu/blog/die-cutting-dies-for-jigsaw-puzzle]; uma matriz aguenta 20 000–100 000 cortes [fonte: http://www.jigscut.com/puzzle-dies.html]. Tolerâncias típicas de ferramentas de lâmina de aço ±0,1–0,4 mm [S: http://diecuttingengineer.blogspot.com/2010/05/dies-and-die-cutting-tolerances.html]. Afirmação de que matrizes grandes são compostas por sub-matrizes repetidas (ex. quatro de 500) [S: sparkspuzzles.com, não lida] — **é exatamente a hipótese que daria "moldes" repetidos dentro do mesmo puzzle, e não está verificada.**

**Clementoni 3000**: duas caixas 3000 listadas como corte "Grid", **64 × 47 = 3008 peças, 218 de borda**, 118,4 × 84,3 cm (3000a) [fonte: https://www.jigsaw-wiki.com/wiki/Boxes_Clementoni, lida]. O 33545 "Os Alpes" não está listado; o tamanho 118,4 × 84,4/84,5 cm nas listagens de Alpes, New York e San Francisco é igual ao 3000a [S: dateks.lv, ebay.de], o que é consistente com uma matriz partilhada entre referências da coleção, **mas nenhuma fonte o afirma**. Medido **[V]**: lado médio do corpo 18,06 ± 0,25 mm (nominal √(18,5·17,9) = 18,2 mm); lados opostos correlacionados (+0,20 contra −0,33 esperado para quadrado), razão longo/curto ≈ 1,05–1,06 — compatível com 64×47 (1,031). **Grelha 64 × 47 confirmada por contagem pelo Tiago (2026-10-30) [V]**; 64 × 48 fica fechado. Na secção montada medi células de 18,4–18,5 × 18,9–19,0 mm (razão 1,03, igual a 64 × 47), ≈ 2,5–3 % acima do nominal 17,9 × 18,5; a causa não foi testada **[NT]** (folga entre peças montadas, ou nominal subestimado) **[V, `SECCAO.md` §0]**. O passo maior (≈ 19,0 mm) corre ao longo da horizontal do puzzle.

**Quão diferentes são duas peças da mesma classe topológica?** Mediana 1,84 mm RMS, mínimo 0,85 mm; entre classes diferentes nunca abaixo de 1,92 mm **[V]**. Para contexto: ruído de re-scan 0,54 mm, lado medido a ±0,2 mm.

Veredicto (2026-10-29; ver a atualização de 2026-10-30 a seguir): "não há 3000 recortes diferentes" é **plausível mas não demonstrado**. A ausência de duplicados em 61 peças é evidência **fraca** (correção após `revisao.md`, nota 2): se a matriz fosse composta por 4 sub-matrizes iguais (período de 16 colunas), o nº esperado de pares repetidos em 61 peças aleatórias é 1830·3/3007 ≈ 1,8 e P(0 pares) ≈ 0,16; com 2 sub-matrizes (período 32) o esperado é ≈ 0,6 e P(0) ≈ 0,54. Logo a amostra só exclui repetição pesada (≥ ×4) e não diz nada sobre ×2. Nota estrutural: **47 é primo**, por isso uma repetição vertical por sub-matrizes iguais é impossível; o único período limpo é horizontal (32 ou 16 colunas). Se a matriz for única com abas deliberadamente variadas (como o fabricante de matrizes descreve), há 3008 formas únicas e o "catálogo de moldes" é a própria matriz. O teste da moldura por translação (E3: coluna c contra c+32 e c+16), que então parecia o decisivo e barato, ficou **substituído** pelo E-sym (rotação de 180°): daria falso negativo, ver a atualização a seguir.

**Atualização 2026-10-30: a repetição é por rotação de 180°, não por translação [V].** A simetria da matriz é pontual: (l, c) ↔ (48 − l, 65 − c), rodada 180° (bordas e interior (2,2)↔(46,63) conferidos à mão pelo Tiago). O teste da moldura original (colunas c, c+32, c+16) procurava translações e daria **falso negativo**; a ressalva da nota 2 da `revisao.md` ("blocos em posições irregulares ou espelhados escaparia") estava **certa**. A amostra de julho é consistente: 61 peças ao acaso dão 61·60/2/3007 ≈ 0,61 pares de gémeos esperados (P(0) ≈ 0,54) e o mínimo observado (0,85 mm em 1830 pares) exclui gémeos. Como 64 é par, nenhuma peça é o próprio gémeo: **1504 pares**. Grupos de 4 (sub-matrizes): excluídos à mão (colunas 5, 10 e 12; nada coincide com os deslocamentos de 16 ou de 32 colunas nem com 33−c rodada), por isso só pares; o centro (colunas 32/33, linha 24) não é testável. Os gémeos são **fisicamente intercambiáveis** (observação do Tiago): uma encaixa onde a outra pertence, só a imagem as distingue.

**Resultado do E-sym rigoroso [V, n = 20 pares de borda, `docs/diagnostico/gemeos/RESULTADOS.md`; `tools/diagnostico/gemeos/esym.py`].** Scans de 30-out a 300 dpi: A1 (borda de cima c5–24), A2 (as mesmas rodadas 180° na casa), B2 (gémeos da borda de baixo). O emparelhamento sai da forma; o GT só avalia. RMS de forma, mediana, em mm:

| Contorno, métrica | Re-scan A1/A2 | Gémeo A1/B2 (mesma pose) | Gémeo A2/B2 (pose oposta) | Não-gémeo mais próximo: mediana / mínimo | Top-1 A1→B2 | NN mútuo (corretos) |
|---|---|---|---|---|---|---|
| **híbrido, free** | 0,27 | 0,29 | 0,39 | 0,83 / 0,60 | 20/20 | 20 (20) |
| híbrido, corner | 0,36 | 0,34 | 0,49 | 0,75 / 0,57 | 20/20 | 20 (20) |
| `seg`, corner | 0,68 | 1,01 | 1,15 | 0,83 / 0,54 | 13/20 | 12 (10) |
| `seg`, free | 0,96 | 1,42 | 1,81 | 0,90 / 0,64 | 8/20 | 10 (7) |

- "Híbrido" = peças separadas por `segment_pieces`, fronteira pelo limiar Lab simples até 1,5 mm do contorno `seg`; `seg` = fronteira do `segment_pieces`. Métrica free = FFT cíclica + rotação; corner = 4 rotações de cantos × Kabsch.
- Com o híbrido e a métrica free: top-1 20/20 em A1→B2, B2→A1 e A2→B2; margem mínima (não-gémeo ÷ gémeo) 1,53; 40/40 gémeos em top-1 num pool de 100 peças. Com a métrica corner, 4 peças ficam com margem < 1,5 e A2→B2 acerta 18/20.
- **Veredicto do M5: viável quanto ao puzzle, não viável com a segmentação atual.** O critério (RMS gémeo mediano ≤ 0,7 mm e top-1 ≥ 95 %) cumpre-se com o híbrido + free e falha com `segment_pieces` (1,01–1,81 mm; 8–13/20). A causa é a fronteira (serrilhada no lado da sombra; mordida até ≈ 1 mm nas peças escuras de prado), não a métrica nem o puzzle. O M10 depende de o M3 dar uma fronteira equivalente.
- **Os números rápidos do Tiago reproduzem-se** (0,28 / 0,34 / 0,43 mm e mínimo 0,56; réplica 0,277 / 0,339 / 0,434 e 0,574). O 0,28 é otimista: A1 e B2 têm a mesma pose e a sombra projetada (0,5–1 mm) cai nos lados homólogos e anula-se. Para pose arbitrária o número honesto é o A2/B2: 0,39–0,52 mm.
- **Topologia**: 20/20 peças com exatamente 1 lado F em A1, A2 e B2, classe igual à do gémeo (20/20 em cada comparação). Cordas: |ΔL| entre lados de gémeos em pose oposta, mediana 0,43 e p90 0,95 mm (n = 60 lados não-F); um filtro de cordas tem de ser de ≈ 1 mm por lado.
- Dentro das bordas a classe discrimina pouco dentro das bordas (todas com 1 F); os pares interiores estão por testar (secção 8.1.0 d).

### a-bis) Memória de cortes (lado como unidade)

A grelha 64 × 47 tem 63·47 + 64·46 = **5905 cortes internos**. Sob a simetria de 180°, todos formam pares exceto o central (entre as colunas 32 e 33, linha 24): (5905 − 1)/2 + 1 = **2953 distintos**. Pergunta do E-cortes: há mais repetição do que a simetria, isto é, o mesmo recorte de lado em peças não gémeas? **[V, `tools/diagnostico/gemeos/cortes.py`, `RESULTADOS.md`]**:
- Ruído por lado, mesmo lado verde↔laranja (236 lados T/B): mediana 0,34 mm de RMS de perfil, |ΔL| mediana 0,24 mm.
- Pares de lados do mesmo tipo de peças diferentes (241 lados não-F do scan verde, 14 256 pares T–T e B–B) abaixo da mediana do ruído: **20 em direção direta e 20 em invertida** (x → 1−x). A invertida é a linha de base do acaso, logo **não há excesso de cortes repetidos**.
- Dicionário: D ≥ 594 (só RMS) a 911 (com |ΔL|) cortes distintos por tipo (95 %), compatível com "todos distintos salvo a simetria" (≈ 2953). **Poder baixo**: o teste exclui dicionários pequenos (D ≲ 500–1000) mas não distingue D ≈ 1000 de 2953 **[V/NT]**.
- Consequência: o lado é a unidade. Cada lado digitalizado entra numa memória de cortes (perfil, corda, tipo); o **molde do buraco** é definido pelos lados dos vizinhos já colocados, e a peça que o preenche é a certa ou a sua gémea (a imagem decide qual).

### b) O que o molde ganha, concretamente

| Ganho | Avaliação |
|---|---|
| Segmentação mais rigorosa (contorno exato) | Sim, mas só **depois** de o molde existir; antes disso o molde vem da segmentação. O ganho real é em re-identificação (contorno parcial → molde completo) e em rejeitar franjas: um contorno que se afasta > 0,5 mm do molde é defeito. |
| Escala real → tamanho da célula na caixa | **Já se tem sem molde**: a célula é 118,4/64 × 84,3/47 cm, e o scanner dá mm. O que falta é o motor usar isso (hoje deriva a escala de `num_pieces` e de uma imagem que inclui a margem da caixa). Ganho real: fixar a escala a ±2 % em vez de uma banda 0,8–1,3. |
| Orientação em múltiplos de 90° | Parcial. A classe topológica reduz as 4 rotações a 1 (BTTT, BBBT), 2 (BTBT, BBTT) ou 4 (BBBB, TTTT) hipóteses; o perfil exato não ajuda a distinguir rotações sem conhecer a matriz. |
| Restrição de posição: bordas e cantos | Sim: 218/3008 posições para peças com 1 lado F, 4 para 2 lados F. Hoje `edges.py` falha 2/3 bordas (e 12/20 nos scans dos gémeos). Com a simetria, a posição de uma peça de borda fica ligada à do gémeo em (48 − l, 65 − c). Cada lado tem **≥ 2 parceiros físicos** (o vizinho verdadeiro e o gémeo do vizinho encaixam ambos). |
| Restrição por classe topológica | ≈ ×6 (6 classes interiores, se a matriz as usar uniformemente — distribuição real **[NT]**). Só se for conhecida a classe de cada célula da matriz, o que exige um mapa da matriz (ver c). |
| Compatibilidade com vizinhos | O ganho grande, mas só quando já há vizinhos colocados (secção montada). Aí a posição da peça fica determinada a ±1 célula e o problema deixa de ser "procurar na caixa". |
| O que NÃO ganha | A forma não diz **onde na imagem** está a peça: os gémeos partilham o recorte e só a imagem os distingue (≥ 2 parceiros físicos por lado). Sem um mapa célula→forma da matriz, o molde reduz candidatos, não os elimina. Em 3008 a forma sozinha não chega (§6). |

### c) Como construir o catálogo sem fotografar as 3000 peças

| Abordagem | Custo | Benefício | Veredicto |
|---|---|---|---|
| Aprendizagem incremental: cada peça digitalizada entra numa base com forma + classe + lados; quando a mesma forma reaparece (re-scan), é re-identificada | Baixo (já há 83–91 % de re-identificação em 61 peças **[V]**) | Re-identificar peças, auditar segmentação, suportar encaixe | **Fazer.** É um índice por peça, não um catálogo de "tipos". |
| Clustering de descritores (Fourier, curvatura, perfil normalizado) para descobrir tipos | Médio | Só compensa se houver repetição real; na amostra os clusters seriam as 6 classes topológicas, que já se obtêm por regra | Não fazer até a experiência mínima mostrar duplicados. |
| Mapa da matriz (forma por célula) a partir de secções montadas: fotografar/digitalizar grupos montados dá a forma de cada célula e a adjacência de uma vez | Médio; escala com o puzzle montado | Dá o "catálogo" com posição — o único que serve para localizar | **Fazer de forma oportunista**: cada grupo montado digitalizado alimenta o mapa. |
| Obter a matriz do fabricante / de outro puzzle da coleção | Desconhecido | Se a matriz for partilhada, um puzzle montado da coleção dá o mapa inteiro | Pergunta 8.5. |

### d) Encaixes

Modelo de lado (já prototipado em `diagnostico/forma`, não em `src/`) **[V]**: 4 cantos por quadrilátero ótimo (ver método no RESULTADOS de forma), lado normalizado a 64 pontos, tipo {F,T,B} por desvio máximo (limiar 0,15 L cai num vazio da distribuição), comprimento da corda em mm. Compatibilidade: tipo (F com nada; T só com B), perfil A vs perfil B invertido e negado (RMS em mm), |ΔL| em mm, mais continuidade de imagem em Lab numa faixa fina (não prototipado). Resultado do sanity check **[V]**: os 6 melhores pares T–B diferem 0,28–0,51 mm com |ΔL| ≤ 0,16 mm e parecem encaixes plausíveis, mas a aba 4s3 encaixa em dois blanks diferentes: **a geometria sozinha não singulariza o vizinho mesmo entre 61 peças** (por construção: cada lado tem ≥ 2 parceiros físicos, ver 5b); precisa da continuidade de imagem, como em toda a literatura.

Redução do espaço de procura na caixa: tipo tab/blank reduz ~½ por lado; |ΔL| ≤ 0,3 mm reduz talvez 5× (dp dos lados 1,07 mm, mas é extrapolação **[NT]**); combinado com a classe topológica do vizinho, uma peça adjacente a uma secção montada tem ≤ 8 células candidatas (fronteira) em vez de 3008. Isto é o que torna o problema tratável e é o que o `piece-fit-matching` já descreve.

**Atualização 2026-10-30.** O E4 conta como acerto o vizinho verdadeiro **ou o gémeo do vizinho**, porque os dois encaixam fisicamente. A imagem é obrigatória para distinguir os dois. O **molde do buraco** (lados livres dos vizinhos colocados em torno de um buraco) identifica a peça certa ou a sua gémea; a imagem da zona decide qual. O lado é a unidade (memória de cortes, 5a-bis).

### e) Contra-argumentos — onde a ideia falha

- **Perspetiva, iluminação, escala desconhecida**: desaparecem com o scanner (plano, luz constante, 300 dpi) **[V]**. Com fotos de telemóvel voltam todos; a correção de perspetiva por 4 cantos dá ±1 % de escala na melhor das hipóteses e não remove sombras. Conclusão: a ideia só é viável com scanner (ou câmara fixa calibrada).
- **Peças quase idênticas**: dentro de 61, o pior caso tinha margem ×1,6 entre re-scan e vizinho mais próximo **[V]**. No E-sym (20 pares de borda, híbrido + free) a margem mínima é 1,53 e o não-gémeo mais próximo nunca fica abaixo de 0,60 mm **[V]**. Extrapolação **[V em 101 peças; NT em 3008]**: com t = p95 dos gémeos (0,505 mm), 0 de 581 pares não-gémeos da mesma classe ficam abaixo de t; falsos candidatos esperados ≈ 0,02–0,04 (N = 60), 0,16–0,30 (N = 500; P(≥ 1) 15–26 %) e 0,9–1,8 (N = 3008; P(≥ 1) 61–83 %). A forma chega até ≈ 60 candidatos; em 3008 a imagem é obrigatória. Os gémeos são, por definição, o caso extremo: o desempate é pela zona da imagem.
- **Cortes não regulares**: a Clementoni 3000 é grelha **[fonte jigsaw-wiki]**, mas as linhas de corte são onduladas: dp dos lados 1,07 mm, cantos a 2,8° de 90° em média, 11° no pior caso **[V]**. "Grelha" não significa células retangulares exatas.
- **Franjas de segmentação** são hoje a maior fonte de erro de forma (9/61 peças) **[V]**: sem resolver isto, nenhum molde é fiável.
- **Peças "mated"** (encaixadas) saem como uma só peça **[V]**. Em secções montadas, linhas de corte **[V, 44 casas, `SECCAO.md` §A]**: o pipeline Otsu + fecho não fecha células (≤ 5/44); na frente a 300 dpi, Hessiana + histerese fecha 30/44 (68 %) sem prior, e com watershed e prior da grelha (canto e passo dos lados retos) 40/44 (91 %; as 4 em falta estão na nuvem). 600 dpi não acrescenta (as mesmas 30; linhas coincidem a ≤ 1 px); o black-hat falha pela textura "linen" do papel. **A traseira não chega [F]**: 0/44 sem prior, porque só 65–70 % do comprimento dos cortes aparece como linha escura (o resto é relevo). Ruído real da extração (frente 300 contra 600): 0,11–0,12 mm RMS (n = 28). Conclusão: a melhor fonte é a frente a 300 dpi; a extração em secções montadas passa a **tarefa de M3** (alvo ≥ 90 % de células sem prior; risco na nuvem e sem prior); a traseira é opcional no protocolo.
- **Custo de digitalização**: um A4 leva ≈60 peças; 3008 peças são ≈50 scans. Não é proibitivo, mas é trabalho manual que o programa não substitui.

### f) Estado da arte com peças reais (forma + imagem)

| Trabalho | Entrada | Usa | Resultado | Aproveitável |
|---|---|---|---|---|
| Yao & Shao 2003 [lido: https://faculty.tnstate.edu/ToBeDeleted_2014_0227/fyao/MyPaper-PDF/2003/PRL-paper.pdf] | scanner flatbed 200–300 dpi, fundo branco, peças separadas, várias cores de fundo para a máscara | cantos por curvatura multi-escala, 18 classes, encaixe por forma + "image merging" | 16 peças 100 %, 25 peças 96 % das ligações; "cenas naturais dão soluções erradas" | O pipeline é quase o deste projeto (até os fundos de cor). Mostra o teto de "só forma + cor local". |
| Chung, Fleck, Forsyth 1998 [lido: https://mfleck.cs.illinois.edu/my-papers/puzzle-icsp98.pdf] | câmara fixa calibrada, fundo uniforme, 1 peça por imagem | forma + cor, moldura primeiro, passo global para corrigir erros locais | 6 puzzles reais até 54 peças | "Peças de forma parecida enganam o score local" → precisa de verificação global ou humana. |
| Hoff & Olver 2011/2014 [lido: https://www-users.cse.umn.edu/~olver/v_/puzzles.pdf] | fotos individuais, snakes + spline | **só forma**: assinatura de curvatura e derivada, "bivertex arcs", piece locking | puzzles de 50–100 peças em 30–60 min; 103/111 de um sub-puzzle de 1000 em 36 h | Prova que forma sozinha escala mal; precisa de contornos muito limpos. |
| Nielsen et al. 2008 [S] | imagem | só imagem | 54 reais | — |
| Zolver (GitHub) [README lido] | foto, threshold | 4 lados classificados, distância euclidiana + cor | sem números | Referência de implementação. |

Ninguém na literatura lida localiza uma peça solta na imagem da caixa a 3000 peças; todos resolvem por **encaixe entre peças com continuidade de imagem**, em lotes pequenos, com peças digitalizadas em condições controladas. É o caminho que este projeto deve seguir.

### Experiência mínima (valida ou mata a ideia)

O E3 original (teste da moldura por translação, colunas c / c+32 / c+16) foi **substituído** pelo **E-sym** (rotação de 180°, feito 2026-10-30) porque daria falso negativo; acrescentaram-se o **E-cortes** (feito) e o **E-buraco** (a fazer).

Dados: os da secção 8 (um bloco contíguo de 40 peças, 5 linhas × 8 colunas, com fotografia montado + scan individual; e 20 peças de uma zona distante). Métricas e critérios:

| # | Pergunta | Métrica | Passa | Mata |
|---|---|---|---|---|
| E1 | A topologia é fiável? | classe automática vs rótulo manual (60 peças) | ≥ 95 % | < 85 % |
| E2 | A forma identifica a peça? | re-scan top-1 entre as 60 (segundo scan em pose diferente) | ≥ 95 % | < 80 % |
| E-sym | As peças de 180° são o mesmo recorte e a forma encontra o gémeo? **Feito 2026-10-30**: passa com contorno híbrido + free (0,29 / 0,39 mm, top-1 20/20); falha com `segment_pieces` (1,01–1,81 mm, 8–13/20). | RMS de forma do gémeo (A1/B2 e A2/B2) contra re-scan (A1/A2) e contra o não-gémeo mais próximo; top-1 e NN mútuo (GT só para avaliar) | RMS gémeo mediano ≤ 0,7 mm e top-1 ≥ 95 % | RMS gémeo ≈ não-gémeo (≈ 0,8–1,8 mm) ou top-1 < 80 % |
| E4 | O encaixe por forma singulariza o vizinho? | para cada lado interno do bloco, posição do vizinho verdadeiro **ou do gémeo do vizinho** (ambos contam como acerto) no ranking por geometria (todos os 240 lados como candidatos) | top-1 ≥ 60 %, top-3 ≥ 90 % | top-3 < 60 % |
| E5 | Com imagem? | E4 com continuidade Lab | top-1 ≥ 85 % | top-1 < 60 % |
| E6 | A célula conhecida chega para a caixa? | peça → posição na caixa com escala fixada pela célula e busca só na arte; top-1/top-5 a ≤ 1 célula | reporta-se; expectativa 30–70 % top-5 consoante textura | não mata nada: é o prior fraco |
| E-cortes | Há cortes repetidos além da simetria de 180°? **Feito 2026-10-30**: sem excesso (20 diretos contra 20 invertidos), D ≥ 594–911. | pares de lados do mesmo tipo de peças diferentes abaixo da mediana do ruído (0,34 mm), direto contra invertido | excesso direto − invertido ≈ 0 | excesso claro (dicionário pequeno, D ≲ 500) |
| E-buraco | A forma dos lados dos vizinhos mais a imagem identificam a peça do buraco (certa ou gémea)? **A fazer** (secção 8.1.0 f). | bloco ≥ 5×5 com 3–5 buracos interiores não adjacentes; ranking das peças retiradas num lote de 40–60 soltas | ≥ 90 % certa-ou-gémea no top-1; ≥ 85 % a certa com imagem | < 60 % certa-ou-gémea |

Custo: uma sessão de fotografia (secção 8) + 2–3 sessões de implementação sobre os scripts já existentes no scratchpad (que devem ser promovidos a `src/shape.py` e `tools/`).

---

## 6. Objetivos propostos (e o que mudou)

| Antes (CLAUDE.md / ROADMAP) | Proposta | Porquê |
|---|---|---|
| Objetivo principal decidido em 2026-10-29 (montagem assistida por encaixe) | **Encontrar o gémeo**: peça colocada em (l, c) → o seu gémeo entre as soltas, que pertence à célula (48 − l, 65 − c). Os gémeos são fisicamente intercambiáveis; o desempate pela zona da imagem é **obrigatório**. | A simetria de 180° foi medida (E-sym) e dá um alvo 1-contra-1 em vez de uma procura entre 3008. |
| Objetivo principal: localizar peças soltas na imagem da caixa por template matching, com confiança honesta | **Segundo objetivo: encaixe e molde do buraco.** Dado um grupo montado (foto/scan) e um lote de peças soltas (scan), ranquear que peças encaixam em cada lado da fronteira e qual preenche cada buraco (a certa ou a sua gémea); **imagem obrigatória** para distinguir. A caixa é prior fraco para peças com textura. | É o único caso de uso com sinal suficiente (secção 5f) e é o que o utilizador já pedia no ROADMAP feature 1. |
| Captura por telemóvel, 11 fundos | **Scanner a 300 dpi, fundo verde/magenta, peças espaçadas ≥ 5 mm** como entrada canónica; telemóvel só para secções montadas grandes | Escala absoluta, sem perspetiva, sem sombra; 61/≈64 peças recuperadas **[V]**. |
| A peça como unidade | **O lado é a unidade**: memória de cortes (5905 cortes internos, ≈ 2953 distintos sob a simetria) e molde do buraco | Os cortes são partilhados por pares de peças; a simetria liga lados, não só peças. |
| Métrica: nº de `high` | **Métricas com verdade de terreno** (abaixo) | Sem GT não há progresso mensurável. |
| Segmentação, bordas, textura como fins | Segmentação e bordas como **medidas** (mm, classe, perfis) ao serviço do encaixe | A precisão geométrica é o ativo do projeto. |

O que "funcionar" significa, em métricas:

| Etapa | Métrica | Alvo |
|---|---|---|
| Segmentação (scan) | recall/precision de peças vs contagem manual; IoU de máscara vs 20 máscaras manuais; dp do comprimento de lado entre re-scans | ≥ 98 % / ≥ 98 %; IoU ≥ 0,97; dp ≤ 0,3 mm |
| Topologia | exatidão de classe vs rótulos manuais | ≥ 95 % |
| Gémeo | gémeo verdadeiro em top-1 num pool ≥ 500 da mesma classe, com imagem; RMS do gémeo; falsos gémeos aceites | top-1 ≥ 95 %; RMS ≤ 0,7 mm; falsos ≤ 5 % |
| Identidade de forma | re-scan top-1 | ≥ 95 % em lotes ≤ 100 |
| Encaixe (reformulado) | vizinho verdadeiro **ou gémeo do vizinho**, top-1 / top-3 (geometria + imagem) | ≥ 85 % / ≥ 97 % |
| Molde do buraco | peça retirada (certa ou gémea) em top-1 / só a certa, com imagem | ≥ 90 % / ≥ 85 % |
| Localização do grupo na caixa | erro do centro do grupo | ≤ 1 célula |
| Peça solta → caixa (secundário) | top-1 / top-5 a ≤ 1 célula no GT; precisão de `high`; **acerto de zona** top-1 / top-3 numa grelha de 8×6 zonas (útil para separar peças muito antes de o acerto por célula ser bom) | reportar; `high` ≥ 90 % preciso; zona top-3 ≥ 80 % |

Casos de uso reais e viáveis, por ordem: (1) "coloquei esta peça em (l, c): qual das soltas é o gémeo?" (desempate pela imagem); (2) "quais destas 60 peças são pares gémeos entre si?" (pares no lote); (3) "que peça vai neste buraco?" (molde do buraco); (4) "tenho esta secção montada e estas 60 peças no tabuleiro: quais encaixam, e em que lado?" (fronteira); (5) "onde na caixa está esta secção montada?" (fácil: NCC em L\* com canto e escala conhecidos deu 0,876 contra 0,408 na arte limpa **[V]**; SIFT falha no céu **[F]**); (6) "onde está esta peça solta?" só para peças com textura e com aviso honesto.

### Combinação forma + classe + zona e medição da margem

**Porque a forma sozinha não chega em 3008 [V em 101 peças; NT em 3008]** (`RESULTADOS.md`, extrapolação). Com o contorno híbrido e a métrica free: margem mínima 1,53 em 20 pares, e com t = p95 dos gémeos = 0,505 mm nenhum dos 581 pares não-gémeos da mesma classe fica abaixo de t. Falsos candidatos esperados abaixo de t num pool de N candidatos da mesma classe (cauda inferior ajustada por exponencial e Weibull):

| N | t = 0,505 mm (p95 dos gémeos) | t = 0,641 mm (máx. dos gémeos) |
|---|---|---|
| 10 | 0,003–0,006 | 0,03 |
| 60 | 0,02–0,04 | 0,21 |
| 500 | 0,16–0,30 (P(≥ 1) 15–26 %) | 1,7 |
| 3008 | 0,9–1,8 (P(≥ 1) 61–83 %) | 10 |

Sem filtro de classe, cerca de 10 % das consultas teriam um não-gémeo abaixo de 0,55 mm com N = 500 e de 0,42 mm com N = 3008. Ressalvas: as 61 peças de julho são quase todas interiores e as 40 de hoje são de borda (só 20 pares cruzados da mesma classe); o t vem de 20 pares; o contorno híbrido inclui sombra. **A forma chega até ≈ 60 candidatos; em 3008 a imagem é obrigatória.**

**Combinar, por ordem de custo:**
1. **Classe topológica** como filtro duro (147/147 estável entre re-scans; ≈ ×6 no interior; nas bordas, todas com 1 F, discrimina pouco). F com limiar 0,15 L (no E-sym: lados F ≤ 0,058 L, não-F ≥ 0,179 L); cuidado com F instável entre scans de fundos diferentes (preto, bege).
2. **Cordas dos 4 lados** como segundo filtro, com |ΔL| de **≈ 1 mm por lado**, não 0,5 mm: entre gémeos em pose oposta o |ΔL| tem mediana 0,43 e p90 0,95 mm, e um filtro de 0,5 mm rejeitaria cerca de 1 em cada 3 lados verdadeiros **[V, n = 60 lados]**.
3. **RMS de forma** (métrica free, contorno sem mordidelas) como score principal; aceitar se d₁ ≤ t (≈ 0,5 mm) e d₂/d₁ ≥ 1,5, calibrado no E-sym.
4. **Zona da imagem, obrigatória**: a célula do gémeo é conhecida, (48 − l, 65 − c). Comparar a assinatura Lab da peça (como o motor faz, 4×4) com a arte nessa célula e com a zona 8×6 à volta, depois de M2 e do deslocamento fotométrico de ≈ −5 L\*. É um teste 1-contra-1 com limiar, não uma procura: distância Lab à célula prevista contra a distribuição das distâncias a células aleatórias da mesma classe de luminância. Rejeitar o gémeo se a imagem o contradiz (prado onde devia haver céu).
5. **Pares dentro do lote** (NN mútuo abaixo de t) e **índice crescente**: cada peça digitalizada entra; as colocadas saem do pool; o pool efetivo de um gémeo são as soltas já digitalizadas da mesma classe, muito menos que 3008.

**Como medir a margem em 3008 sem digitalizar 3008:** (a) a extrapolação acima, atualizada com cada scan novo; (b) a curva empírica "mínimo não-gémeo contra tamanho do pool" a cada scan que entra no índice (monitorizar a distribuição das distâncias NN ao índice, o nº de pares gémeos NN-mútuos abaixo de t e o nº de pares abaixo de t que a imagem contradiz = falsos positivos reais); (c) GT barato: o E-sym (20 pares), os pares interiores (8.1.0 d) e as células da secção montada com (l, c) conhecidos (`seccao_celulas.json`): quando as gémeas dessas células aparecerem num scan, são GT de posição sem esforço extra. Alvo do M10: top-1 ≥ 95 %, falsos gémeos ≤ 5 % com pool ≥ 500.

---

## 7. Plano por marcos

Esforço: P = pequeno (≤ 1 sessão), M = 2–3 sessões, G = > 3. Routing: helper (Sonnet) para P mecânicos, implementer (Opus) para tudo o que toca `matching.py`/`segmentation.py`/módulo novo (incluindo análises que definem a métrica); planner (Fable) não é necessário para nenhum marco abaixo. **A ordem da tabela é a prioridade; os IDs são históricos.**

| # | Marco | Critério de aceitação (mensurável) | Depende de | Risco | Esforço |
|---|---|---|---|---|---|
| M0 ✅ | **Repor a base de medida** (feito 2026-10-29, commit M0) | **Feito**: scripts do diagnóstico em `tools/diagnostico/` (com `PPF_SCRATCH` em vez do caminho de sessão; os `.npz` regeneram-se com `segmentacao_diag.py`). `pytest tests/` verde com OpenCV 4.11 **e** 5.0 (corrigir a regressão de `f6cc2b7` no teste sintético — pode ser ajuste da tolerância se a inflação for o refinamento de fronteira a trabalhar como desenhado, ou bug; decidir com evidência — e tornar o teste de edges independente da ordem de `boxPoints`); `requirements.txt` com versões; `eval_matching.py` sem caminho de sessão; `images/puzzles/pexels-*.jpg` e scripts órfãos removidos; README com aviso "desatualizado, ver ARCHITECTURE.md". | — | baixo | P (helper + implementer para o teste de segmentação) |
| M5 ✅ | **E-sym: gémeos por rotação de 180°** (feito 2026-10-30, decidido: viável quanto ao puzzle, não viável com a segmentação atual) | **Feito [V]**: contorno híbrido + free: gémeo 0,29 / 0,39 mm (mesma pose / pose oposta), top-1 20/20, margem mínima 1,53, 40/40 num pool de 100; `segment_pieces`: 1,01–1,81 mm, top-1 8–13/20. Substitui o teste da moldura por translação. Evidência: `docs/diagnostico/gemeos/RESULTADOS.md`. | scans 8.1.0 ✅ | — | feito |
| M1 | **Dataset de validação v1** (secção 8) | Ficheiros em `images/gt/` + `gt.csv` com, por peça: id, (linha, coluna) ou casa (fila, k) nos scans dos gémeos, classe topológica manual, ficheiro/índice no scan. Conteúdo: as 40 peças do E-sym (A1/A2/B2, GT por casa) + as células da secção montada com (l, c) (`seccao_celulas.json`, só a frente a 300 dpi) + ≈ 10 pares interiores (8.1.0 d) + os buracos do E-buraco (8.1.0 f); o bloco 5×8 fica para depois. | fotos do utilizador | médio (depende do utilizador) | P |
| M2 | **Referência = arte** | Função que recorta a referência à bbox da arte (manual por 4 cantos ou automática), guarda a homografia e expõe `cell_px = (W/64, H/47)` (e a célula do gémeo (48 − l, 65 − c)); o motor passa a usar escala fixa ±5 % quando a célula é conhecida; o prior de borda usa a bbox da arte. Ler `PuzzleOriginal.jpeg` ignorando o EXIF (secção 9). Reportar E6 sobre M1. | M0, M1 | baixo | P–M (implementer) |
| M3 | **Segmentação ao serviço da geometria** | Em scans: **fronteira sem mordidelas nas peças escuras e com a sombra projetada tratada** (critério: E-sym com o contorno de `segment_pieces` ≥ o híbrido, isto é, gémeo ≤ 0,5 mm e top-1 20/20); **peça junto ao bordo não descartada** (S1); franjas/dentadas removidas (rugosidade < 1,1 em ≥ 95 % das peças); peças "mated" sinalizadas por área/lados F; IoU ≥ 0,97 em 20 máscaras manuais; dp de lado ≤ 0,3 mm entre re-scans; **extração de linhas de corte em secções montadas pela frente a 300 dpi** (Hessiana + histerese/watershed; alvo ≥ 90 % de células sem prior, hoje 68 % sem prior e 91 % com prior da grelha); contorno do buraco em blocos com peças retiradas. | M1 | médio | M (implementer) |
| M4 | **`src/shape.py`** (cantos, lados, classe, ID de forma) | E1 ≥ 95 %, E2 ≥ 95 %; lado como unidade (perfil, corda, tipo) e dicionário de cortes; substitui a classificação de `edges.py` (que marca só 8/20 bordas nos scans dos gémeos); testes sintéticos + GT. | M1, M3 | médio (cantos é o passo frágil; método já prototipado) | M (implementer) |
| M10 | **`src/twin.py`: encontrar o gémeo** | `find_twin(peça, pool, índice)`: filtro de classe, filtro de cordas (≈ 1 mm por lado), RMS free, gap (aceitar se d₁ ≤ 0,5 mm e d₂/d₁ ≥ 1,5), **imagem obrigatória** (teste 1-contra-1 na célula (48 − l, 65 − c)), rejeição calibrada, índice persistente. Alvo: top-1 ≥ 95 %, falsos gémeos ≤ 5 % com pool ≥ 500. **Condicionado ao M3** (fronteira). | M2, M3, M4 | médio | M (implementer) |
| M11 | **Molde do buraco** (`src/fit.py`, 1.ª metade) | Dado um buraco num bloco, ranquear as soltas pelo molde dos lados dos vizinhos + imagem: ≥ 90 % certa-ou-gémea em top-1 e ≥ 85 % a certa com imagem (E-buraco). | M1, M3, M4 | médio | M (implementer) |
| M7 | **Secção montada como referência local** | Localizar a secção na arte pelo método de **canto e escala conhecidos** (os 2 lados retos dão o canto, o passo da célula dá a escala; NCC em L\* com jitter: 0,876 contra 0,408 na arte limpa e 0,82 contra 0,40 na caixa, canto superior esquerdo, 44 peças **[V]**); SIFT só em zonas com textura (falhou no céu: 0 inliers **[F]**). Extrair a fronteira (lados livres) com os seus perfis. Erro ≤ 1 célula. | M2, M4 | baixo | M |
| M6 | **Encaixe geométrico + imagem na fronteira** (`src/fit.py`, 2.ª metade) | E4 e E5 nos alvos (vizinho verdadeiro ou gémeo do vizinho); API `rank_partners(side, pieces) -> shortlist + confiança`, O(N) por consulta; testes sintéticos (par gerado = melhor custo; F rejeitado). | M4, M11 | médio | M (implementer) |
| M8 | **GUI de montagem assistida** | Carregar scan de peças + foto de secção; modos gémeo, buraco e fronteira: para cada consulta mostrar as 3 melhores peças com a peça recortada colocada no sítio; exportar JSON. Teste de uso: utilizador coloca 20 peças seguidas com ≤ 2 erros. | M10, M11, M6, M7 | médio (GUI de 1268 linhas) | M–G |
| M9 | **Localização de peça solta na caixa, honesta** (terciário) | **Requisito**: normalização fotométrica scanner→referência reduzida a um deslocamento de ≈ −5 L\* (mais um pequeno ajuste em b\*; `SECCAO.md` §C), aplicada antes da assinatura; com M2: reportar top-1/top-5 por célula e acerto de zona no GT; `high` ≥ 90 % preciso ou não mostrar `high`. | M2, M1 | alto (limite da arte) | M |

**Cortar** (não fazer nesta ronda, nem em "futuro"): GPU/CUDA, REST API, ML de classificação, câmara live, correção de perspetiva por 4 cantos (o scanner resolve), mais experiências de fundos de cor (já provado: verde/laranja/preto/vermelho servem), solver global das 3000 peças, CLI `main.py` (manter só como smoke test ou apagar), `requirements-dev.txt` inchado.

**Dataset de validação com ground truth** — como criar: secção 8. Quantas peças: as 40 do E-sym (GT por casa, já digitalizadas) + as ≈ 40 células da secção montada com (l, c) + ≈ 10 pares interiores + ≈ 10 buracos chegam para E-sym, E4, E-buraco e E5 com intervalos de ±10 pontos percentuais; o bloco 5×8 contíguo (secção 8.1.1) acrescenta 40 posições na caixa conhecidas para o M9 (linha, coluna → célula → coordenadas na arte via M2).

---

## 8. Perguntas que preciso que respondas / fotos que preciso

### 8.1 Fotos para a experiência mínima (secção 5) e para M1

Material: o scanner que já usaste (digitalizações a 300 dpi, A4); papel verde saturado (o que usaste em `digitalização_fundo_verde.jpg`); uma régua ou um objeto de dimensão conhecida; o puzzle.

0. **Gémeos por rotação de 180° (E-sym, o mais barato e decisivo).**
   - (a) ✅ Contagem da grelha (64 × 47) e simetria (l, c) ↔ (48 − l, 65 − c), verificadas à mão pelo Tiago.
   - (b)(c) ✅ Scans A1 `coluna5-24_300dpi_folhaA.jpg` (borda de cima, c5–24, 4 filas de 5), A2 `colunas5-24_300dpi_rot180_folhaA.jpg` (as mesmas rodadas 180° na casa), B1 `coluna5-24_folhaB_300dpi.jpg` (gémeos da borda de baixo) e B2 `coluna5-24_folhaB_300dpi_rot180.jpg` (B1 com cada peça rodada 180°). Correspondência A(fila, k) ↔ B(fila, 4 − k). B1 é inutilizável (na fila 3 há 2 peças encostadas); usar B2. Descrição em `images/pieces/gemeos_2026-10-30.md`.
   - (d) **A fazer**: ≈ 10 pares interiores (l, c) / (48 − l, 65 − c): 4 filas × 5 peças em papel verde, 300 dpi, espaçadas ≥ 5 mm, com as filas 1–2 e as filas 3–4 (os gémeos) **na mesma ordem**; anotar a ordem.
   - (e) ✅ Secção montada de canto, frente e traseira a 300 e 600 dpi (`{frente,traseira}_{300,600}dpi.jpg`). Para secções montadas: **a frente a 300 dpi chega; a traseira é opcional; 600 dpi é desnecessário** (a traseira não fecha células sem prior e 600 dpi não acrescenta nada, `SECCAO.md` §A).
   - (f) **E-buraco (a fazer)**: bloco montado ≥ 5×5 sobre papel verde com 3–5 peças interiores não adjacentes retiradas; scan da frente a 300 dpi (traseira opcional); as peças retiradas misturadas num lote de 40–60 soltas e digitalizadas; GT num txt (buraco (l, c) → índice da peça no lote). ≈ 10 buracos. Nomes: `gt_buraco_<zona>_bloco_frente_300dpi.jpg`, `gt_buraco_<zona>_soltas_300dpi.jpg`, `gt_buraco_<zona>.txt`.
1. **Bloco contíguo montado, 5 linhas × 8 colunas = 40 peças** (depois do E-buraco e dos pares interiores), numa zona com textura (ex.: a aldeia com a igreja, ou a árvore amarela com o prado — não o céu). Inclui pelo menos **uma fila de borda** (idealmente um canto do puzzle: assim há 2 cantos-de-borda e ~12 peças de borda) para testar F.
   - Foto 1: o bloco **montado**, de cima, com uma régua ao lado, luz difusa (sem flash), telemóvel o mais paralelo possível à mesa, bloco a ocupar ≥ 60 % do enquadramento. Serve para GT de adjacência e para M7. Se couber no scanner (um bloco 8×5 mede ≈ 15 × 9 cm — cabe num A4), **digitaliza-o também montado** a 300 dpi: melhor ainda.
   - Antes de desmontar: **anota a grelha** — uma foto do bloco com post-its ou um esquema em papel com os números 1–40 por (linha, coluna), e os números das linhas/colunas no puzzle se souberes (contando a partir do canto).
   - Depois desmonta e **digitaliza as 40 peças soltas** em papel verde, imagem para cima, **espaçadas ≥ 5 mm**, sem tocar, a 300 dpi, tampa fechada. Precisas de saber que peça é que: digitaliza-as **por ordem numa grelha regular** (5 filas de 8, mesma ordem do bloco) para que a posição no scan dê o id. Faz **dois scans**: um por ordem, outro com as peças baralhadas e rodadas (para E2); do segundo não precisas de GT.
2. **20 peças de uma zona distante** do bloco (opcional, baixa prioridade): só para ter peças de céu no GT de M9 e de M1. O E3 original (repetição entre zonas por translação) foi substituído pelo E-sym. Por ordem conhecida num scan de papel verde; se forem de um grupo já montado, foto montada antes, como em 1.
3. **Um scan de calibração**: o mesmo papel verde com uma régua metálica ou uma folha quadriculada, a 300 dpi, para confirmar que 1 px = 0,0847 mm nos dois eixos (resposta a "não sei qual eixo é horizontal" e a ±0,25 mm de incerteza). Opcional mas barato: uma peça junto a um cartão cinzento neutro (ou um papel branco e um preto) para medir a curva de tom do scanner (a causa do L\* 86 já ficou respondida em 2026-10-30: composição do saco, ver 3.6).
3b. **Scan de uma secção montada de prado ou floresta** (um A4, pela frente, a 300 dpi). A secção de canto de céu e nuvem já serve de curva fotométrica (scan ≈ arte + 5 L\*, `SECCAO.md` §C); falta uma de prado/floresta para confirmar o desvio fora do céu. Serve também ao M7 e às linhas de corte do M3.
4. **Não precisas** de: mais fundos de cor, DNG de telemóvel, fotos com sombra, fotos de peças encostadas.

Formato: JPEG do scanner (como até aqui) ou TIFF; nomes com a zona e a ordem (ex.: `gt_bloco_igreja_ordenado.jpg`, `gt_bloco_igreja_baralhado.jpg`, `gt_bloco_igreja_montado.jpg`, `gt_ceu_20_ordenado.jpg`, `calib_regua.jpg`).

### 8.2 Perguntas

Respondidas em 2026-10-29: **8.2.2** as 61 peças foram tiradas ao acaso do saco (mas ver 8.2.9: a medição de 2026-10-30 não se concilia com isso sem uma explicação); **8.2.6** objetivo principal = montagem assistida (revisto em 2026-10-30: encontrar o gémeo); **8.2.7** fixar OpenCV 4.11. Respondidas em 2026-10-30: a grelha é 64 × 47 (por contagem); a simetria de 180° e os grupos de 4 (à mão); a memória de cortes (o lado como unidade) foi adotada; fotometria: o scanner é fiel à arte e as peças de julho eram mesmo claras (composição do saco, `SECCAO.md` §C). As restantes continuam abertas.

1. Confirmas que `PuzzleOriginal.jpeg` é a tua foto da caixa deste puzzle, e que `1186441_1.jpg` é a imagem de produto da mesma referência? (Assumi que sim: a homografia entre as duas tem 2597 inliers.)
2. As 61 peças dos 11 scans de julho: de que zona do puzzle são? Primeira resposta: ao acaso do saco. A conclusão de 2026-10-30 (são claras de verdade) reabre isto na pergunta 9.
3. Que scanner/driver e definições usaste (300 dpi, "foto" ou "documento", correção automática de cor ligada)? Para a normalização fotométrica preciso de saber se a curva de tom é fixa. (Menos urgente desde 2026-10-30: o scanner é fiel à arte e o papel tem o mesmo Lab em julho e hoje.)
4. Quanto do puzzle está montado hoje, e tens fotos das secções montadas de cima com régua? (As fotos IMG_2110/2111 mostram secções grandes de céu montadas.)
5. Tens acesso a outro Clementoni 3000 da mesma coleção (New York 33546, San Francisco 33547, Coliseu 33548)? Um punhado de peças dele digitalizado responderia à reutilização de matriz entre referências, que nenhuma fonte confirma.
6. Qual é a tua tolerância de interação: aceitas um fluxo "digitalizo 60 peças → o programa diz, para cada lado da secção montada, as 3 melhores" (montagem assistida), ou insistes em "aponto uma peça → ponto vermelho na caixa"? A segunda só vai funcionar para peças com textura.
7. Python: ficas com 3.13 e OpenCV 5, ou preferes fixar OpenCV 4.x? (Vou fixar o que disseres em `requirements.txt` no M0.)
8. Fluxo do gémeo e do buraco: aceitas "digitalizo o lote; o programa mantém um índice crescente (as peças colocadas saem do pool) e, para cada peça colocada, procura o gémeo; indica também pares dentro do lote, lados livres e buracos de bloco"? A traseira de blocos é opcional.
9. O saco estava misturado? 43 das 61 peças de julho são claras (L\* ≥ 80) quando só 8–14 % da arte o é **[NT]**. Escolheste as peças à vista (por exemplo, as mais fáceis de ver sobre o verde) ou o saco estava arrumado por zonas?

---

## 9. Backlog

- **Atualizar o README para refletir os objetivos e a arquitetura novos (pendente).**
- **Armadilha EXIF:** `images/puzzles/PuzzleOriginal.jpeg` tem EXIF orientation = 3 com os píxeis já direitos. `cv2.imread` aplica a etiqueta e devolve a foto invertida; o PIL não. Usar `cv2.IMREAD_IGNORE_ORIENTATION` ou PIL (o motor e `matching/common.py` usam PIL). Os scans não têm a etiqueta.
- **M3 (explícito), defeitos de `segment_pieces` vistos nos gémeos:** (S1) peça a menos de ≈ 1,2 mm do bordo do scan é descartada em silêncio (`_FRAME_MARGIN_FRAC`): avisar ou alargar a imagem antes do filtro; (S2) fronteira serrilhada no lado da sombra e mordidelas até ≈ 1 mm em peças escuras de prado; (S3) `edges.py` marca borda só em 8/20 peças de borda. Critério do M3: E-sym com o contorno de `segment_pieces` ≥ o híbrido (gémeo ≤ 0,5 mm, top-1 20/20). O M10 fica condicionado a isto.
- **Linhas de corte em blocos montados** (estado após `seccao.py`): frente a 300 dpi com Hessiana + histerese fecha 30/44 células (68 %) sem prior e 40/44 (91 %) com watershed e prior da grelha; a traseira não chega (0/44 sem prior); 600 dpi não acrescenta; black-hat falha pela textura "linen". Por testar **[NT]**: detetor de relevo para a traseira, fusão frente + traseira. Alvo do M3: ≥ 90 % sem prior.
- A máscara de Otsu de patamar de `segment_pieces` cortou metade de uma peça creme da nuvem e, com ΔE puro, anexava a sombra da aresta do cartão (≈ 0,4 mm) **[V no script `seccao.py`; NT em `src/` com peças creme sobre verde]**.
- Medidas por explicar **[NT]**: células montadas ≈ 2,5–3 % maiores que o nominal; silhueta da traseira 0,5 % menor que a da frente.
- Matriz partilhada na coleção (New York, San Francisco, Coliseu): não verificada (pergunta 8.2.5).
- M0 itens: corrigir/ajustar `tests/test_segmentation.py` (regressão `f6cc2b7`), tornar `tests/test_edges.py` independente da ordem de `boxPoints`, fixar versões em `requirements.txt`, remover `SCRATCH` fixo do `eval_matching.py`, apagar `gpu_test.py`/`test_scales.py`/`temp_import_test.py`/`pexels-*.jpg`, corrigir `examples/README.md`, `DeprecationWarning` do Pillow em `segmentation.py:1461`.
- GUI: passar `piece_edges` ao motor (ou remover a classificação da GUI até M4); não desenhar ponto vermelho único quando `ambiguous` (desenhar shortlist); mostrar classe topológica.
- Atualizar `CLAUDE.md` (status dos módulos, remover "métodos duplicados"/"caminhos partidos", apontar para ARCHITECTURE.md); atualizar `RELATORIO.md`/`ROADMAP.md` ou substituí-los por este documento; corrigir a skill `cv-visual-verification` (pytest "tem de ficar verde" → "está vermelho em HEAD; M0 repõe").
- Promover os scripts do scratchpad (`forma/shapelib.py`, `diag/expA.py` …) a `tools/` do repositório para que a experiência seja reprodutível (hoje vivem fora do repo).
- Segmentação: franjas/dentadas; sinalizar "mated"; opção `expected_pieces` realmente usada; modelo de fundo robusto a tapetes com linhas (fotos de telemóvel) — baixa prioridade se o scanner for a entrada canónica.
- Fotometria: deslocamento scanner→referência ≈ −5 L\* (medido em 2026-10-30; sem correção automática dependente do conteúdo); falta confirmar em prado/floresta (8.1.3b) e implementar a normalização do M9 como deslocamento.
- Persistência de sessão na GUI; tabela de resultados clicável (já no ROADMAP antigo).
- Documentar o ambiente: venv, `pip install -r requirements.txt`, Tk.
