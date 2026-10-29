# Estado e plano — Puzzle Piece Finder

_2026-10-29. Diagnóstico feito sobre HEAD `c35442f`, sem alterar `src/`. Evidência em `docs/diagnostico/` (imagens, `RESULTADOS.md` e `results.json` por área). Mapa do código em [`ARCHITECTURE.md`](../ARCHITECTURE.md)._

Convenção de etiquetas usada em todo o documento:
- **[V]** verificado nesta sessão, com evidência apontada;
- **[NT]** não testado;
- **[F]** testado e falha;
- **[fonte]** afirmação externa com link; **[S]** só vista em resumo de pesquisa, não lida na página.

---

## 1. Resumo executivo

1. O código está mais avançado do que o README sugere: segmentação, classificação de bordas, motor de matching, textura, visualização, GUI e exportação JSON existem e correm **[V]**.
2. O que não existe é **verdade de terreno**: nenhuma peça tem posição conhecida. Todas as afinações anteriores foram feitas contra o próprio rótulo `high` do motor, que é um proxy, não um acerto **[V]**.
3. Em dados sintéticos (recortes da própria referência) o motor localiza 72 % top-1 / 82 % top-5 e o rótulo `high` é 100 % preciso (28/28) **[V]**. Com peças reais digitalizadas, as duas referências do repo **não concordam em 0/61 peças** e nenhum crop previsto se parece com a peça **[V]**. Causa mais forte: as digitalizações têm L\* mediano 86 contra 50 da arte; só 1–6 % da arte é tão clara **[V]**. É um fosso fotométrico, não um bug de pesquisa.
4. A referência `PuzzleOriginal.jpeg` é uma **foto da caixa** com margem branca e texto; o motor procura nessa margem e o prior de borda assume o contrário **[V]**.
5. A suite pytest **não está verde**: o teste de segmentação falha desde o commit `f6cc2b7` (10-jul), o mesmo dia em que foi escrito **[F]**; outro teste depende da ordem de `cv2.boxPoints`, que mudou no OpenCV 5 **[F]**.
6. A documentação anterior descreve a arte como "deserto/areia"; é a paisagem alpina de Val di Funes; as peças claras são céu e nuvens **[V]**.
7. A ideia dos "moldes de recorte" tem uma metade sólida e uma metade não verificada. Sólida: com o scanner a 300 dpi medem-se lados a ±0,2 mm, a topologia (tab/blank/flat) é estável entre scans (100 % em 147 pares) e a forma identifica uma peça re-digitalizada em 83–91 % dentro de um conjunto de 61 **[V]**. Não verificada: que existam formas repetidas num puzzle de 3008 peças. Na amostra de 61 **não há duplicados** (par mais próximo 0,85 mm RMS, acima do ruído de re-scan 0,54 mm) **[V]**.
8. A grelha é 64 × 47 = 3008 peças, 218 de borda, para os Clementoni 3000 de 118,4 cm [fonte jigsaw-wiki]; as células não são quadradas (razão ≈1,05 medida) **[V]**, consistente com 64×47 (1,031) mas sem distinguir de 64×48.
9. Proposta: mudar o objetivo principal de "uma peça solta → posição na caixa" para **montagem assistida por encaixe** (scanner + secção montada como referência local), mantendo a localização na caixa como prior fraco e só para peças com textura. É o que a literatura faz com peças reais; ninguém localiza uma peça de céu entre 3000 por template matching.
10. Primeiro marco (uma sessão): repor a base de medida — testes verdes, referência recortada à arte, dependências fixadas. Segundo marco: o dataset com verdade de terreno de 40 peças descrito na secção 8, que valida ou mata a ideia dos moldes.

---

## 2. Mapa do projeto

Ver [`ARCHITECTURE.md`](../ARCHITECTURE.md) para módulos, contratos e pontos de entrada. Resumo do que importa aqui:

- Fluxo real: `segmentation.segment_pieces` → `edges.classify_pieces` → `matching.multi_scale_template_match` (assinatura Lab 4×4 a ≈46 px/peça, 4 rotações, textura, prior de borda, gap de confiança) → GUI/`visualization`. Só a GUI liga tudo.
- Cronologia (git) **[V]**: projeto criado 11-ago-2025 (CLI ingénua + docs em inglês). Silêncio até 9-jul-2026. Em **9–11 de julho de 2026** (≈48 h, 20 commits) foi escrito praticamente tudo: motor zonal Lab, textura, prior de borda, segmentação com seam-carve, suite pytest, ROADMAP, RELATORIO, scans dos 11 fundos. Último commit de código: 11-jul. Em 29-out: skills e 5 fotos de telemóvel. Sem branches, sem stash, árvore limpa.
- O que foi tentado e abandonado, segundo os próprios commits: inpaint de glare (revertido), watershed de cor (substituído por seam-carve), fundo branco (substituído por fundos de cor).
- Código morto/órfão **[V]**: `gpu_test.py`, `test_scales.py`, `temp_import_test.py`, `use_gpu` (aceite e ignorado), `compare_images`/`sliding_window_search` (só a CLI usa), `images/puzzles/pexels-*.jpg`, `requirements-dev.txt` com sphinx/jupyter/mypy nunca usados, `examples/README.md` lista 4 scripts dos quais só 1 existe.
- README vs código **[V]**: README promete `piece_0.png…23`, `puzzle.json`, `data/`, GPU/CUDA, "overlap detection", segmentação "in development". Nada disso corresponde. O CLAUDE.md fala em métodos duplicados na GUI e imports relativos partidos: não se reproduz (`python -m src.main` e `python -m src.gui` importam **[V]**).
- Skills pedidas: `cv-visual-verification` e `piece-fit-matching` existem e foram seguidas; `project-cartographer` e `systematic-debugging` **não existem** em `.claude/skills/` — o ARCHITECTURE.md e a fase 2 foram feitos à mão no mesmo espírito.

---

## 3. Estado por etapa, com evidência

Ambiente usado: Python 3.13; a máquina não tinha `cv2` instalado no interpretador global. Criei dois venvs no scratchpad: OpenCV 5.0.0 e OpenCV 4.11.0 (numpy 2.2, Pillow 11). `requirements.txt` não fixa versões.

### 3.1 Testes existentes **[F]**

| OpenCV | Resultado | Causa |
|---|---|---|
| 4.11 | 5/6 passam | `test_segment_recovers_all_rectangles` falha: o retângulo azul (650,100,150×120) sai com bbox (595,40,211×202), inflada. Bisseção por commit: passa em `78804c0`, falha a partir de `f6cc2b7` (histerese + refinamento de fronteira), i.e. **o teste foi quebrado no próprio dia em que foi adicionado e nunca voltou a correr**. Imagem: `diagnostico/segmentacao/teste_sintetico_retangulos__labels.png`. |
| 5.0 | 4/6 passam | Acima + `test_two_adjacent_flat_sides_is_corner`: `cv2.boxPoints` devolve os cantos noutra ordem no OpenCV 5; o tipo continua `corner`, só a indexação `sides[0]/[1]` muda. Brittleness do teste, não bug do classificador. |

O `RELATORIO.md` de 11-jul afirma "suite pytest anti-regressão" como feita. Não era verdade nessa data.

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

Conclusões: funciona para scans com fundo saturado e peças espaçadas (**[V]**, ≈95 % recall estimado, sem GT manual); falha em fotos de telemóvel com peças encostadas **[V]**. Defeitos que importam a jusante: franjas e "dentadas" no contorno em 9/61 peças do scan verde (#2, #6, #11, #18, #26, #27, #44, #47, #52), que são a principal fonte de ruído de forma (correlação 0,69 entre rugosidade e distância de re-scan) **[V, forma]**; variação de área da mesma peça entre scans de −5,4 % a +1,6 % **[V]**. Métrica de IoU contra máscaras manuais: **[NT]** (não há máscaras manuais).

### 3.4 Classificação de bordas (`edges.py`) **[V, parcialmente F]**

- Distribuição no scan verde: 60 `interior`, 1 `edge`. A análise de perfis de lado encontra 3 peças com um lado reto (#42, #54, #60; visível na montagem `diagnostico/forma/montagem_cantos_scan_verde.png`). **`edges.py` falha 2 das 3 peças de bordo** porque mede o desvio ao `minAreaRect` da peça inteira (com abas), que não é o corpo da peça.
- A GUI **não passa `piece_edges` ao motor**; o prior de borda só é exercido pelo harness `eval_matching.py` **[V]**.

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

Causa medida: L\* mediano das peças digitalizadas 86 (p10 59, p90 95); só 1 % (caixa) a 6 % (arte limpa) dos blocos à escala da peça atingem L\* ≥ 86, e 8–14 % atingem ≥ 80, contra 43/61 peças **[V, recomputado por mim]**. O fundo não é a causa (Δ entre fundos ≈ 1 unidade Lab). Isto é compatível com (a) resposta/gama do scanner sobre o acabamento "linen" brilhante e/ou (b) amostra dominada por céu. O motor só remove a média de L por assinatura; não compensa gama/contraste, e o croma absoluto amarelo-esverdeado leva as peças para prados **[V]**. Qual das causas domina: **[NT]** (teste: digitalizar um alvo de cinzentos, ou normalizar o histograma das peças para o da arte e repetir B).

**C. Repetibilidade entre fundos (laranja vs verde, 22 pares) [V]**: 32 % top-1 no mesmo sítio (acaso 2 %), 0 pares `high`/`high`. Repetível, não certo.

Não testado: escala real das peças com abas (≈1,4× a célula, no limite da banda 0,8–1,3 do motor) **[NT]**; busca a 24 px/peça na arte limpa **[NT]**; impacto do prior de borda **[NT]**; a foto de telemóvel IMG_2114 (usada pelo harness antigo) contra GT **[NT]** — nunca houve GT.

### 3.7 Visualização e exportação **[V]**

`annotate_results`/`save_annotated_image` e o Export JSON da GUI funcionam (contrato em ARCHITECTURE.md §3). O ponto vermelho é desenhado no centro de `position+size/2` mesmo quando `confidence='ambiguous'`; o JSON guarda a shortlist. Não há exportação de máscaras/contornos das peças (só PNG RGBA via Save Pieces).

---

## 4. Causa raiz do abandono

Sintoma: "nada funcionava como eu queria". Causas, por ordem de importância:

1. **Sem verdade de terreno, o ciclo de desenvolvimento otimizou um proxy.** Toda a afinação de 9–11 de julho mediu "quantas peças ficam `high`" em 64 peças de telemóvel. Hoje sei que `high` é 100 % preciso em dados sintéticos e 0/61 confirmável em peças reais. O ciclo não tinha como detetar isto. Sem GT não há como saber se um `high` é um acerto ou um atrator. **[V]**
2. **Formulação do problema no limite da informação.** Uma peça de 18 mm coberta por 16 células de cor média, procurada em 3008 células × 4 rotações de uma paisagem em que ~40 % é céu/nuvem e ~30 % prado: para a maioria das peças a resposta é "ambígua" por natureza, e o próprio ROADMAP já o admitia ("limites aceites"). Os pontos fortes do motor (porta de estrutura, shortlist honesta) não mudam isso. A experiência A dá o teto: 72–90 % top-1 **com recortes da própria referência**.
3. **Fosso fotométrico e geométrico entre captura e referência.** Scanner vs foto da caixa (L\* 86 vs 50), margem da caixa incluída na pesquisa, escala assumida a partir do nº de peças em vez da célula física conhecida. **[V]**
4. **Dívida de verificação.** Testes quebrados no dia em que nasceram, relatório que descreve outro puzzle, harness com caminho de sessão antigo, skill que exige "pytest verde" quando não está. Isto corrói a confiança e torna cada sessão uma re-descoberta. **[V]**
5. **Sprint de 48 h sem consolidação.** 20 commits em dois dias sobre módulos de 1000+ linhas; o seam-carve, a histerese e o refinamento de fronteira entraram em sequência sem re-correr a suite. Previsível que algo tenha partido. **[V, git log]**

O que **não** foi a causa: a arquitetura dos módulos (razoável), a GUI (funciona), a ausência de GPU (irrelevante), e a qualidade dos scans (boa).

---

## 5. Análise da ideia dos "moldes de recorte"

### a) A premissa é verdadeira?

**Classes topológicas** (padrão tab/blank/flat nos 4 lados): verdadeiro e trivial. Para peças interiores há 2⁴ = 16 rotulagens, 6 classes a menos de rotação (4T, 4B, 3+1, 1+3, 2+2 adjacentes, 2+2 opostos) [fonte: https://jigsawtogether.com/blog/jigsaw-piece-shapes-glossary ; Yao & Shao 2003 usam 18 modelos canónicos incluindo bordas e cantos: https://faculty.tnstate.edu/ToBeDeleted_2014_0227/fyao/MyPaper-PDF/2003/PRL-paper.pdf]. Medido no scan verde (61 peças) **[V]**: BBBT 18, BTBT 13, BTTT 11, BBTT 10, BBBB 3, TTTT 3, 3 peças com um lado F. A classe é estável entre re-scans em 147/147 pares emparelhados **[V]**.

**Classes geométricas** (forma exata): **não verificado, e a amostra aponta contra duplicados exatos.** Entre as 1830 combinações de pares do scan verde, o par mais parecido (38–39) difere 0,85 mm RMS, acima da distância mediana de uma peça à sua própria re-digitalização (0,54 mm, p90 1,96 mm). Na sobreposição (`t3_pares_mais_parecidos.png`) as abas estão deslocadas 0,5–1,5 mm ao longo do lado: mesma topologia, faca diferente **[V]**. As abas têm todas a mesma "cabeça redonda com pescoço" (mediana T–T 0,09 L) e diferem em posição, altura e largura — um lado isolado discrimina pouco **[V]**.

**Como os cortantes funcionam** (verificado em páginas lidas): corte por lâminas de aço numa matriz ("puzzle die"), prensa hidráulica ou rolo [fonte: https://en.wikipedia.org/wiki/Jigsaw_puzzle]; corte "ribbon/grid" com grelha definida e meia dúzia de formas-tipo vs "random cut" com peças únicas; a mesma matriz pode ser usada para vários puzzles [fonte: https://mindthepuzzle.com/puzzles/ribbon-cut-and-random-cut-puzzles]; a variação de tamanho, direção, inclinação e deslocamento das abas é deliberada para tornar as peças únicas; a folha desloca-se ≈1 mm no corte, daí a sangria [fonte: https://www.fabrykapuzzli.eu/blog/die-cutting-dies-for-jigsaw-puzzle]; uma matriz aguenta 20 000–100 000 cortes [fonte: http://www.jigscut.com/puzzle-dies.html]. Tolerâncias típicas de ferramentas de lâmina de aço ±0,1–0,4 mm [S: http://diecuttingengineer.blogspot.com/2010/05/dies-and-die-cutting-tolerances.html]. Afirmação de que matrizes grandes são compostas por sub-matrizes repetidas (ex. quatro de 500) [S: sparkspuzzles.com, não lida] — **é exatamente a hipótese que daria "moldes" repetidos dentro do mesmo puzzle, e não está verificada.**

**Clementoni 3000**: duas caixas 3000 listadas como corte "Grid", **64 × 47 = 3008 peças, 218 de borda**, 118,4 × 84,3 cm (3000a) [fonte: https://www.jigsaw-wiki.com/wiki/Boxes_Clementoni, lida]. O 33545 "Os Alpes" não está listado; o tamanho 118,4 × 84,4/84,5 cm nas listagens de Alpes, New York e San Francisco é igual ao 3000a [S: dateks.lv, ebay.de], o que é consistente com uma matriz partilhada entre referências da coleção, **mas nenhuma fonte o afirma**. Medido **[V]**: lado médio do corpo 18,06 ± 0,25 mm (nominal √(18,5·17,9) = 18,2 mm); lados opostos correlacionados (+0,20 contra −0,33 esperado para quadrado), razão longo/curto ≈ 1,05–1,06 — compatível com 64×47 (1,031) mas não distingue de 64×48 (1,053). Qual eixo é horizontal: **[NT]**.

**Quão diferentes são duas peças da mesma classe topológica?** Mediana 1,84 mm RMS, mínimo 0,85 mm; entre classes diferentes nunca abaixo de 1,92 mm **[V]**. Para contexto: ruído de re-scan 0,54 mm, lado medido a ±0,2 mm.

Veredicto: "não há 3000 recortes diferentes" é **plausível mas não demonstrado**, e a evidência disponível (61 de 3008, nenhum duplicado) não o apoia. Se a matriz for única com abas deliberadamente variadas (como o fabricante de matrizes descreve), há 3008 formas únicas e o "catálogo de moldes" é a própria matriz.

### b) O que o molde ganha, concretamente

| Ganho | Avaliação |
|---|---|
| Segmentação mais rigorosa (contorno exato) | Sim, mas só **depois** de o molde existir; antes disso o molde vem da segmentação. O ganho real é em re-identificação (contorno parcial → molde completo) e em rejeitar franjas: um contorno que se afasta > 0,5 mm do molde é defeito. |
| Escala real → tamanho da célula na caixa | **Já se tem sem molde**: a célula é 118,4/64 × 84,3/47 cm, e o scanner dá mm. O que falta é o motor usar isso (hoje deriva a escala de `num_pieces` e de uma imagem que inclui a margem da caixa). Ganho real: fixar a escala a ±2 % em vez de uma banda 0,8–1,3. |
| Orientação em múltiplos de 90° | Parcial. A classe topológica reduz as 4 rotações a 1 (BTTT, BBBT), 2 (BTBT, BBTT) ou 4 (BBBB, TTTT) hipóteses; o perfil exato não ajuda a distinguir rotações sem conhecer a matriz. |
| Restrição de posição: bordas e cantos | Sim: 218/3008 posições para peças com 1 lado F, 4 para 2 lados F. Hoje `edges.py` falha 2/3 bordas. |
| Restrição por classe topológica | ≈ ×6 (6 classes interiores, se a matriz as usar uniformemente — distribuição real **[NT]**). Só se for conhecida a classe de cada célula da matriz, o que exige um mapa da matriz (ver c). |
| Compatibilidade com vizinhos | O ganho grande, mas só quando já há vizinhos colocados (secção montada). Aí a posição da peça fica determinada a ±1 célula e o problema deixa de ser "procurar na caixa". |
| O que NÃO ganha | A forma não diz **onde na imagem** está a peça. Sem um mapa célula→forma da matriz, o molde reduz candidatos, não os elimina. E o mapa só se obtém digitalizando as 3008 peças ou montando o puzzle. |

### c) Como construir o catálogo sem fotografar as 3000 peças

| Abordagem | Custo | Benefício | Veredicto |
|---|---|---|---|
| Aprendizagem incremental: cada peça digitalizada entra numa base com forma + classe + lados; quando a mesma forma reaparece (re-scan), é re-identificada | Baixo (já há 83–91 % de re-identificação em 61 peças **[V]**) | Re-identificar peças, auditar segmentação, suportar encaixe | **Fazer.** É um índice por peça, não um catálogo de "tipos". |
| Clustering de descritores (Fourier, curvatura, perfil normalizado) para descobrir tipos | Médio | Só compensa se houver repetição real; na amostra os clusters seriam as 6 classes topológicas, que já se obtêm por regra | Não fazer até a experiência mínima mostrar duplicados. |
| Mapa da matriz (forma por célula) a partir de secções montadas: fotografar/digitalizar grupos montados dá a forma de cada célula e a adjacência de uma vez | Médio; escala com o puzzle montado | Dá o "catálogo" com posição — o único que serve para localizar | **Fazer de forma oportunista**: cada grupo montado digitalizado alimenta o mapa. |
| Obter a matriz do fabricante / de outro puzzle da coleção | Desconhecido | Se a matriz for partilhada, um puzzle montado da coleção dá o mapa inteiro | Pergunta 8.5. |

### d) Encaixes

Modelo de lado (já prototipado em `diagnostico/forma`, não em `src/`) **[V]**: 4 cantos por quadrilátero ótimo (ver método no RESULTADOS de forma), lado normalizado a 64 pontos, tipo {F,T,B} por desvio máximo (limiar 0,15 L cai num vazio da distribuição), comprimento da corda em mm. Compatibilidade: tipo (F com nada; T só com B), perfil A vs perfil B invertido e negado (RMS em mm), |ΔL| em mm, mais continuidade de imagem em Lab numa faixa fina (não prototipado). Resultado do sanity check **[V]**: os 6 melhores pares T–B diferem 0,28–0,51 mm com |ΔL| ≤ 0,16 mm e parecem encaixes plausíveis, mas a aba 4s3 encaixa em dois blanks diferentes: **a geometria sozinha não singulariza o vizinho mesmo entre 61 peças**; precisa da continuidade de imagem, como em toda a literatura.

Redução do espaço de procura na caixa: tipo tab/blank reduz ~½ por lado; |ΔL| ≤ 0,3 mm reduz talvez 5× (dp dos lados 1,07 mm, mas é extrapolação **[NT]**); combinado com a classe topológica do vizinho, uma peça adjacente a uma secção montada tem ≤ 8 células candidatas (fronteira) em vez de 3008. Isto é o que torna o problema tratável e é o que o `piece-fit-matching` já descreve.

### e) Contra-argumentos — onde a ideia falha

- **Perspetiva, iluminação, escala desconhecida**: desaparecem com o scanner (plano, luz constante, 300 dpi) **[V]**. Com fotos de telemóvel voltam todos; a correção de perspetiva por 4 cantos dá ±1 % de escala na melhor das hipóteses e não remove sombras. Conclusão: a ideia só é viável com scanner (ou câmara fixa calibrada).
- **Peças quase idênticas**: dentro de 61, o pior caso tem margem ×1,6 entre re-scan e vizinho mais próximo; em 3008 peças haverá colisões de forma com certeza (extrapolação, **[NT]**). A forma identifica dentro de um lote de dezenas, não entre milhares, a menos que se junte a cor.
- **Cortes não regulares**: a Clementoni 3000 é grelha **[fonte jigsaw-wiki]**, mas as linhas de corte são onduladas: dp dos lados 1,07 mm, cantos a 2,8° de 90° em média, 11° no pior caso **[V]**. "Grelha" não significa células retangulares exatas.
- **Franjas de segmentação** são hoje a maior fonte de erro de forma (9/61 peças) **[V]**: sem resolver isto, nenhum molde é fiável.
- **Peças "mated"** (encaixadas) saem como uma só peça **[V]**; o molde ajudaria a detetar (área 2× e lados F falsos), mas não a separar.
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

Dados: os da secção 8 (um bloco contíguo de 40 peças, 5 linhas × 8 colunas, com fotografia montado + scan individual; e 20 peças de uma zona distante). Métricas e critérios:

| # | Pergunta | Métrica | Passa | Mata |
|---|---|---|---|---|
| E1 | A topologia é fiável? | classe automática vs rótulo manual (60 peças) | ≥ 95 % | < 85 % |
| E2 | A forma identifica a peça? | re-scan top-1 entre as 60 (segundo scan em pose diferente) | ≥ 95 % | < 80 % |
| E3 | Há formas repetidas? | nº de pares com RMS < 0,6 mm (≈ ruído de re-scan) entre peças distintas, e entre o bloco e as 20 distantes | > 0 pares → há moldes repetidos | 0 pares em 1770 → sem evidência; abandonar "catálogo de tipos" |
| E4 | O encaixe por forma singulariza o vizinho? | para cada lado interno do bloco, posição do vizinho verdadeiro no ranking por geometria (todos os 240 lados como candidatos) | top-1 ≥ 60 %, top-3 ≥ 90 % | top-3 < 60 % |
| E5 | Com imagem? | E4 com continuidade Lab | top-1 ≥ 85 % | top-1 < 60 % |
| E6 | A célula conhecida chega para a caixa? | peça → posição na caixa com escala fixada pela célula e busca só na arte; top-1/top-5 a ≤ 1 célula | reporta-se; expectativa 30–70 % top-5 consoante textura | não mata nada: é o prior fraco |

Custo: uma sessão de fotografia (secção 8) + 2–3 sessões de implementação sobre os scripts já existentes no scratchpad (que devem ser promovidos a `src/shape.py` e `tools/`).

---

## 6. Objetivos propostos (e o que mudou)

| Antes (CLAUDE.md / ROADMAP) | Proposta | Porquê |
|---|---|---|
| Objetivo principal: localizar peças soltas na imagem da caixa por template matching, com confiança honesta | **Montagem assistida por encaixe**: dado um grupo montado (foto/scan) e um lote de peças soltas (scan), ranquear que peças encaixam em cada lado da fronteira e onde. A caixa é prior fraco para peças com textura. | É o único caso de uso com sinal suficiente (secção 5f) e é o que o utilizador já pedia no ROADMAP feature 1. |
| Captura por telemóvel, 11 fundos | **Scanner a 300 dpi, fundo verde/magenta, peças espaçadas ≥ 5 mm** como entrada canónica; telemóvel só para secções montadas grandes | Escala absoluta, sem perspetiva, sem sombra; 61/≈64 peças recuperadas **[V]**. |
| Métrica: nº de `high` | **Métricas com verdade de terreno** (abaixo) | Sem GT não há progresso mensurável. |
| Segmentação, bordas, textura como fins | Segmentação e bordas como **medidas** (mm, classe, perfis) ao serviço do encaixe | A precisão geométrica é o ativo do projeto. |

O que "funcionar" significa, em métricas:

| Etapa | Métrica | Alvo |
|---|---|---|
| Segmentação (scan) | recall/precision de peças vs contagem manual; IoU de máscara vs 20 máscaras manuais; dp do comprimento de lado entre re-scans | ≥ 98 % / ≥ 98 %; IoU ≥ 0,97; dp ≤ 0,3 mm |
| Topologia | exatidão de classe vs rótulos manuais | ≥ 95 % |
| Identidade de forma | re-scan top-1 | ≥ 95 % em lotes ≤ 100 |
| Encaixe | vizinho verdadeiro top-1 / top-3 (geometria + imagem) | ≥ 85 % / ≥ 97 % |
| Localização do grupo na caixa | erro do centro do grupo | ≤ 1 célula |
| Peça solta → caixa (secundário) | top-1 / top-5 a ≤ 1 célula no GT; precisão de `high` | reportar; `high` ≥ 90 % preciso |

Caso de uso real e viável, por ordem: (1) "tenho esta secção montada e estas 60 peças no tabuleiro: quais encaixam, e em que lado?"; (2) "onde na caixa está esta secção montada?" (fácil: SIFT deu 2597 inliers entre duas imagens inteiras); (3) "onde está esta peça solta?" só para peças com textura e com aviso honesto.

---

## 7. Plano por marcos

Esforço: P = pequeno (≤ 1 sessão), M = 2–3 sessões, G = > 3. Routing: helper (Sonnet) para P mecânicos, implementer (Opus) para tudo o que toca `matching.py`/`segmentation.py`/módulo novo; planner (Fable) não é necessário para nenhum marco abaixo.

| # | Marco | Critério de aceitação (mensurável) | Depende de | Risco | Esforço |
|---|---|---|---|---|---|
| M0 | **Repor a base de medida** | `pytest tests/` verde com OpenCV 4.11 **e** 5.0 (corrigir a regressão de `f6cc2b7` no teste sintético — pode ser ajuste da tolerância se a inflação for o refinamento de fronteira a trabalhar como desenhado, ou bug; decidir com evidência — e tornar o teste de edges independente da ordem de `boxPoints`); `requirements.txt` com versões; `eval_matching.py` sem caminho de sessão; `images/puzzles/pexels-*.jpg` e scripts órfãos removidos; README com aviso "desatualizado, ver ARCHITECTURE.md". | — | baixo | P (helper + implementer para o teste de segmentação) |
| M1 | **Dataset de validação v1** (secção 8) | Ficheiros em `images/gt/` + `gt.csv` com, por peça: id, (linha, coluna) no bloco, classe topológica manual, ficheiro/índice no scan; 60 peças; 2 scans por lote (poses diferentes). | fotos do utilizador | médio (depende do utilizador) | P |
| M2 | **Referência = arte** | Função que recorta a referência à bbox da arte (manual por 4 cantos ou automática), guarda a homografia e expõe `cell_px = (W/64, H/47)`; o motor passa a usar escala fixa ±5 % quando a célula é conhecida; o prior de borda usa a bbox da arte. Reportar E6 sobre M1. | M0, M1 | baixo | P–M (implementer) |
| M3 | **Segmentação ao serviço da geometria** | Em scans: franjas/dentadas removidas (rugosidade < 1,1 em ≥ 95 % das peças); peças "mated" sinalizadas por área/lados F; IoU ≥ 0,97 em 20 máscaras manuais; dp de lado ≤ 0,3 mm entre re-scans. | M1 | médio | M (implementer) |
| M4 | **`src/shape.py`** (cantos, lados, classe, ID de forma) | E1 ≥ 95 %, E2 ≥ 95 %; substitui a classificação de `edges.py` (que falha 2/3 bordas); testes sintéticos + GT. | M1, M3 | médio (cantos é o passo frágil; método já prototipado) | M (implementer) |
| M5 | **Decisão sobre moldes** | E3 reportado com números sobre as 60 peças (+ as 20 distantes). Se > 0 duplicados: abrir M5b "catálogo de tipos". Se 0: fechar a ideia de catálogo e manter só o índice por peça. | M4 | — | P |
| M6 | **Encaixe geométrico + imagem** (`src/fit.py`) | E4 e E5 nos alvos; API `rank_partners(side, pieces) -> shortlist + confiança`, O(N) por consulta; testes sintéticos (par gerado = melhor custo; F rejeitado). | M4 | médio | M (implementer) |
| M7 | **Secção montada como referência local** | Localizar uma foto de secção montada na caixa (homografia; erro ≤ 1 célula) e extrair a fronteira (lados livres) com os seus perfis. | M2, M4 | baixo (SIFT já funciona entre as duas referências) | M |
| M8 | **GUI de montagem assistida** | Carregar scan de peças + foto de secção; para cada lado da fronteira mostrar as 3 melhores peças com a peça recortada colocada no sítio; exportar JSON. Teste de uso: utilizador coloca 20 peças seguidas com ≤ 2 erros. | M6, M7 | médio (GUI de 1268 linhas) | M–G |
| M9 | **Localização de peça solta na caixa, honesta** (secundário) | Com normalização fotométrica (histograma L\*/croma das peças para o da arte) e M2: reportar top-1/top-5 no GT; `high` ≥ 90 % preciso ou não mostrar `high`. | M2, M1 | alto (limite da arte) | M |

**Cortar** (não fazer nesta ronda, nem em "futuro"): GPU/CUDA, REST API, ML de classificação, câmara live, correção de perspetiva por 4 cantos (o scanner resolve), mais experiências de fundos de cor (já provado: verde/laranja/preto/vermelho servem), solver global das 3000 peças, CLI `main.py` (manter só como smoke test ou apagar), `requirements-dev.txt` inchado.

**Dataset de validação com ground truth** — como criar: secção 8. Quantas peças: 60 (40 em bloco contíguo + 20 distantes) chega para E1–E5 com intervalos de ±10 pontos percentuais; para M9 o mesmo bloco dá 40 posições na caixa conhecidas (linha, coluna → célula → coordenadas na arte via M2).

---

## 8. Perguntas que preciso que respondas / fotos que preciso

### 8.1 Fotos para a experiência mínima (secção 5) e para M1

Material: o scanner que já usaste (digitalizações a 300 dpi, A4); papel verde saturado (o que usaste em `digitalização_fundo_verde.jpg`); uma régua ou um objeto de dimensão conhecida; o puzzle.

1. **Bloco contíguo montado, 5 linhas × 8 colunas = 40 peças**, numa zona com textura (ex.: a aldeia com a igreja, ou a árvore amarela com o prado — não o céu). Inclui pelo menos **uma fila de borda** (idealmente um canto do puzzle: assim há 2 cantos-de-borda e ~12 peças de borda) para testar F.
   - Foto 1: o bloco **montado**, de cima, com uma régua ao lado, luz difusa (sem flash), telemóvel o mais paralelo possível à mesa, bloco a ocupar ≥ 60 % do enquadramento. Serve para GT de adjacência e para M7. Se couber no scanner (um bloco 8×5 mede ≈ 15 × 9 cm — cabe num A4), **digitaliza-o também montado** a 300 dpi: melhor ainda.
   - Antes de desmontar: **anota a grelha** — uma foto do bloco com post-its ou um esquema em papel com os números 1–40 por (linha, coluna), e os números das linhas/colunas no puzzle se souberes (contando a partir do canto).
   - Depois desmonta e **digitaliza as 40 peças soltas** em papel verde, imagem para cima, **espaçadas ≥ 5 mm**, sem tocar, a 300 dpi, tampa fechada. Precisas de saber que peça é que: digitaliza-as **por ordem numa grelha regular** (5 filas de 8, mesma ordem do bloco) para que a posição no scan dê o id. Faz **dois scans**: um por ordem, outro com as peças baralhadas e rodadas (para E2); do segundo não precisas de GT.
2. **20 peças de uma zona distante** do bloco (ex.: outro canto do puzzle, ou céu), também por ordem conhecida num scan de papel verde, para E3 (repetição de formas entre zonas) e para ter peças de céu no GT de M9. Se forem de um grupo já montado, foto montada antes, como em 1.
3. **Um scan de calibração**: o mesmo papel verde com uma régua metálica ou uma folha quadriculada, a 300 dpi, para confirmar que 1 px = 0,0847 mm nos dois eixos (resposta a "não sei qual eixo é horizontal" e a ±0,25 mm de incerteza). Opcional mas barato: uma peça junto a um cartão cinzento neutro (ou um papel branco e um preto) para medir a curva de tom do scanner e responder à causa do L\* 86.
4. **Não precisas** de: mais fundos de cor, DNG de telemóvel, fotos com sombra, fotos de peças encostadas.

Formato: JPEG do scanner (como até aqui) ou TIFF; nomes com a zona e a ordem (ex.: `gt_bloco_igreja_ordenado.jpg`, `gt_bloco_igreja_baralhado.jpg`, `gt_bloco_igreja_montado.jpg`, `gt_ceu_20_ordenado.jpg`, `calib_regua.jpg`).

### 8.2 Perguntas

1. Confirmas que `PuzzleOriginal.jpeg` é a tua foto da caixa deste puzzle, e que `1186441_1.jpg` é a imagem de produto da mesma referência? (Assumi que sim: a homografia entre as duas tem 2597 inliers.)
2. As 61 peças dos 11 scans de julho: de que zona do puzzle são (foram escolhidas ou tiradas ao acaso do saco)? Isto decide se o L\* 86 é seleção ou scanner.
3. Que scanner/driver e definições usaste (300 dpi, "foto" ou "documento", correção automática de cor ligada)? Para a normalização fotométrica preciso de saber se a curva de tom é fixa.
4. Quanto do puzzle está montado hoje, e tens fotos das secções montadas de cima com régua? (As fotos IMG_2110/2111 mostram secções grandes de céu montadas.)
5. Tens acesso a outro Clementoni 3000 da mesma coleção (New York 33546, San Francisco 33547, Coliseu 33548)? Um punhado de peças dele digitalizado responderia à reutilização de matriz entre referências, que nenhuma fonte confirma.
6. Qual é a tua tolerância de interação: aceitas um fluxo "digitalizo 60 peças → o programa diz, para cada lado da secção montada, as 3 melhores" (montagem assistida), ou insistes em "aponto uma peça → ponto vermelho na caixa"? A segunda só vai funcionar para peças com textura.
7. Python: ficas com 3.13 e OpenCV 5, ou preferes fixar OpenCV 4.x? (Vou fixar o que disseres em `requirements.txt` no M0.)

---

## 9. Backlog

- **Atualizar o README para refletir os objetivos e a arquitetura novos (pendente).**
- M0 itens: corrigir/ajustar `tests/test_segmentation.py` (regressão `f6cc2b7`), tornar `tests/test_edges.py` independente da ordem de `boxPoints`, fixar versões em `requirements.txt`, remover `SCRATCH` fixo do `eval_matching.py`, apagar `gpu_test.py`/`test_scales.py`/`temp_import_test.py`/`pexels-*.jpg`, corrigir `examples/README.md`, `DeprecationWarning` do Pillow em `segmentation.py:1461`.
- GUI: passar `piece_edges` ao motor (ou remover a classificação da GUI até M4); não desenhar ponto vermelho único quando `ambiguous` (desenhar shortlist); mostrar classe topológica.
- Atualizar `CLAUDE.md` (status dos módulos, remover "métodos duplicados"/"caminhos partidos", apontar para ARCHITECTURE.md); atualizar `RELATORIO.md`/`ROADMAP.md` ou substituí-los por este documento; corrigir a skill `cv-visual-verification` (pytest "tem de ficar verde" → "está vermelho em HEAD; M0 repõe").
- Promover os scripts do scratchpad (`forma/shapelib.py`, `diag/expA.py` …) a `tools/` do repositório para que a experiência seja reprodutível (hoje vivem fora do repo).
- Segmentação: franjas/dentadas; sinalizar "mated"; opção `expected_pieces` realmente usada; modelo de fundo robusto a tapetes com linhas (fotos de telemóvel) — baixa prioridade se o scanner for a entrada canónica.
- Fotometria: medir curva de tom do scanner (8.1.3); normalização de histograma piece→arte antes do matching.
- Persistência de sessão na GUI; tabela de resultados clicável (já no ROADMAP antigo).
- Documentar o ambiente: venv, `pip install -r requirements.txt`, Tk.
