# Estado e plano — Puzzle Piece Finder

_2026-10-29. Diagnóstico feito sobre HEAD `c35442f`, sem alterar `src/`. Evidência em `docs/diagnostico/` (imagens, `RESULTADOS.md` e `results.json` por área). Mapa do código em [`ARCHITECTURE.md`](../ARCHITECTURE.md). Atualizado 2026-10-30: grelha 64 × 47 confirmada por contagem; simetria de rotação de 180° (1504 pares de gémeos, fisicamente intercambiáveis) verificada à mão e medida (E-sym rigoroso, `docs/diagnostico/gemeos/`); objetivo principal passa a "encontrar o gémeo"; lado como unidade ("memória de cortes", molde do buraco); secção montada: linhas de corte e fotometria; marcos reordenados. Atualizado 2026-10-31: 8.2.9 resolvida (seleção), §0 fluxo de uso, E-fundo/E-real, M12 estado persistente. Atualizado 2026-10-31 (2): `segment_scan`, E-real (canto BD), E-real-2, §11 generalização, M13._

Convenção de etiquetas usada em todo o documento:
- **[V]** verificado nesta sessão, com evidência apontada;
- **[NT]** não testado;
- **[F]** testado e falha;
- **[fonte]** afirmação externa com link; **[S]** só vista em resumo de pesquisa, não lida na página.

---

## 0. Fluxo de uso (visão do produto — Tiago, 2026-10-31)

O Tiago digitaliza peças soltas **aos poucos** (um A4 ≈ 60 peças, 300 dpi, papel de cor saturada, espaçadas ≥ 5 mm). O programa mantém um **índice persistente de peças** (forma, lados, classe, imagem, estado) e um **mapa do tabuleiro** (célula (l, c) → peça ou vazio; 64 × 47). Para cada scan novo:

1. Segmenta e mede as peças (mm, classe, 4 lados, assinatura de imagem); cada uma entra no índice como `solta`.
2. Sugere posições, **por ordem de força do sinal**:
   1. **Gémeo de peça colocada** — para cada peça colocada em (l, c) cuja célula gémea (48 − l, 65 − c) está vazia, procura o gémeo entre as soltas: classe + cordas + forma (free), **imagem obrigatória** no desempate (M10). É um teste 1-contra-1, o sinal mais forte.
   2. **Molde de buraco** — células vazias com ≥ 2 vizinhos colocados: os lados dos vizinhos definem o molde; ranking das soltas (M11). Sai a peça certa ou a sua gémea; a imagem decide.
   3. **Imagem contra a caixa** — só para peças com textura, com confiança honesta (M9). Prior fraco.
   4. **Encaixe entre soltas** — por último (M6): cada lado tem ≥ 2 parceiros físicos e a imagem local de duas soltas é pouca.
3. O Tiago **monta fisicamente** e confirma na GUI ("colocada em (l, c)") ou rejeita. A confirmação atualiza o mapa, tira a peça do pool e **gera novas consultas**: cada colocação desbloqueia a gémea e muda os moldes dos buracos vizinhos. Cada confirmação/rejeição fica no histórico e é **verdade de terreno gratuita** para as métricas do §6 (taxa de aceitação por tipo de sugestão e por rank).
4. **Secções montadas** registam-se por scan da frente a 300 dpi (linhas de corte → células com forma e imagem; M3/M7). Só ganham coordenadas (l, c) quando (a) estão **ligadas à moldura** (lado reto → canto ou linha/coluna conhecida) ou (b) o Tiago **indica a posição** de uma célula. Até lá são um grupo com coordenadas locais; os seus lados livres entram na memória de cortes e servem de molde.

**Regra de produto (2026-10-31).** Toda a peça passa pelo scanner **solta** antes de ser colocada, por isso o índice já tem a silhueta das peças colocadas. As linhas de corte servem só para **secções de céu** e para o **legado**; a relva legada (montada à mão, fora do índice) digitaliza-se solta por blocos (vista explodida, como nos cantos BD e BE). Linhas de corte em arte texturada: não atacar agora (decisão do Tiago, 2026-10-31).

**O que isto exige dos marcos:** M3 (fronteira fiável em scans; linhas de corte em secções de céu e legado) → M4 (lados e classe) → **M12 (estado persistente: índice, mapa, histórico, lotes e pares de gémeas)** → M10 (gémeo) → M11 (buraco) → M7 (ancorar secções) → M6 (encaixe) → M8 (GUI com confirmação e lista "ir buscar") → M9 (caixa). **M13 (perfil do puzzle)** entra com o M12 (esquema e pasta por puzzle) e fecha depois do M10 (rotina de calibração); ver §11. M2 (referência = arte) é pré-requisito do desempate pela imagem no M10. A ordem da tabela do §7 reflete isto.

**Oportunidade principal.** A tira de relva montada (as linhas de baixo, largura inteira) tem os gémeos no céu (linhas de cima, colunas espelhadas, (l, c) ↔ (48 − l, 65 − c)). O primeiro uso real do programa é: digitalizar peças soltas de céu e **colocá-las através dos gémeos de relva** já montados (teste 1-contra-1 com imagem obrigatória, M10). Isto é o **E-real-2** (§5), depois do M10.

**Modelo de uso real (Tiago, 2026-10-31).** O Tiago digitaliza **lotes de ≈ 32 peças ao acaso**, guarda cada lote num **saco numerado** (saco = lote = scan) e não filtra por zona. Por peça nova, por ordem: (1) **gémea já colocada** → posição exata; (2) **gémea entre as soltas** → par registado, com **localização conjunta pela imagem** (a célula (l, c) tem de bater com a peça A em (l, c) **e** com a B na célula gémea: um par céu + textura localiza o céu); (3) **buraco/fronteira**; (4) **imagem**, só com textura; (5) senão a peça **fica na memória**. Cada confirmação reavalia a memória e gera a lista **"vai buscar ao lote N, peça X"** (com a imagem da peça para a escolher no saco). **Legado:** as peças montadas à mão não estão no índice; a faixa de relva tem de ser digitalizada solta por blocos para desbloquear o céu (estimativa grosseira do Tiago **[NT]**: ≈ 1 em 4 peças de céu do saco com posição imediata). O E-real-2 com peças pré-filtradas é só a validação barata antes desse investimento. **Estado `posicao_conhecida` (2026-10-31):** uma gémea cuja célula é conhecida mas ainda não tem vizinha montada fica de lado, etiquetada com a célula (caso da f1p1 #6 → (5,60) no E-real-2), e o programa diz "podes colocar (l, c)" quando uma célula vizinha passa a estar ocupada; entra na ordem de sinais logo a seguir a (1)/(2). **Reconciliação com a foto do tabuleiro (M14):** antes das consultas de um scan novo, o estado é reconciliado com a última foto do tabuleiro: células ocupadas na foto sem entrada no log passam a `ocupada_legado`; uma célula `colocada` que a foto mostra vazia gera um aviso.

---

## 1. Resumo executivo

1. O código está mais avançado do que o README sugere: segmentação, classificação de bordas, motor de matching, textura, visualização, GUI e exportação JSON existem e correm **[V]**.
2. O que não existe é **verdade de terreno**: nenhuma peça tem posição conhecida. Todas as afinações anteriores foram feitas contra o próprio rótulo `high` do motor, que é um proxy, não um acerto **[V]**.
3. Em dados sintéticos (recortes da própria referência) o motor localiza 72 % top-1 / 82 % top-5 e o rótulo `high` é 100 % preciso (28/28) **[V]**. Com peças reais digitalizadas, as duas referências do repo **não concordam em 0/61 peças** e nenhum crop previsto se parece com a peça **[V]**. Causa (corrigida em 2026-10-30): o scanner é fiel à arte (L\* do scan ≈ 1,06·L\* da arte + 1,3, desvio uniforme ≈ +5 L\*) e as 61 peças de julho (L\* mediano 86,4) são mesmo claras, nuvens e pôr do sol: o 0/61 vem de **peças claras de céu e nuvem sem textura** (limite da arte) e de uma **referência que é foto da caixa com margem** **[V, `docs/diagnostico/gemeos/SECCAO.md` §C]**. A explicação anterior ("desfasamento de captura do scanner") é falsa **[F]**; a normalização fotométrica do M9 reduz-se a um deslocamento de ≈ −5 L\*. Resolvido 2026-10-31 **[V, Tiago]**: as 61 peças foram pré-filtradas (as que não conseguia localizar) — o L\* 86 é **seleção**. O 0/61 é o pior caso possível; o desempenho em peças aleatórias é **[NT]**.
4. A referência `PuzzleOriginal.jpeg` é uma **foto da caixa** com margem branca e texto; o motor procura nessa margem e o prior de borda assume o contrário **[V]**.
5. A suite pytest **não estava verde** a 29-10: o teste de segmentação falhava desde o commit `f6cc2b7` (10-jul), o mesmo dia em que foi escrito **[F]**; outro teste dependia da ordem de `cv2.boxPoints`, que mudou no OpenCV 5 **[F]**. Reposta no M0 (`7c9fa89`): 6/6 nos dois OpenCV, reconfirmado em 2026-10-30 **[V]**.
6. A documentação anterior descreve a arte como "deserto/areia"; é a paisagem alpina de Val di Funes; as peças claras são céu e nuvens **[V]**.
7. A ideia dos "moldes de recorte" tinha uma metade sólida e uma metade por verificar; a segunda ficou verificada em 2026-10-30. Sólida: com o scanner a 300 dpi medem-se lados a ±0,2 mm, a topologia (tab/blank/flat) é estável entre scans (100 % em 147 pares) e a forma identifica uma peça re-digitalizada em 83–91 % dentro de um conjunto de 61 **[V]**. Verificada: **o recorte repete-se por rotação de 180°**. A peça (l, c) tem o mesmo recorte que (48 − l, 65 − c) rodada 180° (64 é par: nenhuma peça é o próprio gémeo, logo 1504 pares), conferido à mão pelo Tiago (bordas; interior (2,2)↔(46,63)) e medido no E-sym rigoroso com 20 pares de borda: gémeo A1/B2 0,29 mm, A2/B2 0,39 mm (pose oposta), re-scan A1/A2 0,27 mm, não-gémeo mais próximo mínimo 0,60 mm, top-1 20/20 **[V, contorno híbrido + métrica free, `RESULTADOS.md`]**. Com a fronteira de `segment_pieces` o teste falha (gémeo 1,01 mm corner e 1,42 mm free, top-1 13/20 e 8/20): a causa é a segmentação, não o puzzle **[V]**. Grupos de 4 excluídos à mão (colunas 5, 10 e 12: nada coincide com os deslocamentos de 16 ou de 32 colunas nem com 33−c rodada), por isso só pares; o centro (colunas 32/33, linha 24) não é testável. A amostra de julho (mínimo 0,85 mm em 1830 pares) é consistente: esperados 0,61 pares, P(0) ≈ 0,54 (amostra **não aleatória**: pré-filtrada por dificuldade visual, logo o P(0) não é evidência sobre a frequência de gémeos).
8. A grelha é 64 × 47 = 3008 peças **[V, confirmada por contagem pelo Tiago, 2026-10-30]**; 218 de borda (= 2·(64+47) − 4), para os Clementoni 3000 de 118,4 cm [fonte jigsaw-wiki]. As células não são quadradas: razão ≈ 1,03 medida na secção montada (passos 18,4–18,5 × 18,9–19,0 mm), igual à de 64 × 47; 64 × 48 fica fechado **[V]**. Cortes internos: 63·47 + 64·46 = 5905, ≈ 2953 distintos sob a simetria.
9. Objetivo (revisto em 2026-10-30): **encontrar o gémeo**. Para uma peça colocada em (l, c), achar entre as soltas o seu gémeo, que pertence à célula (48 − l, 65 − c), por forma (cordas dos lados, métrica free, classe topológica) com **desempate obrigatório pela zona da imagem**. Os gémeos são **fisicamente intercambiáveis** (uma encaixa no lugar da outra; só a imagem as distingue; é também um modo de erro humano que o programa pode detetar). A seguir vêm o encaixe entre vizinhos e o **molde do buraco** (memória de cortes: o lado é a unidade). A localização na caixa fica como prior fraco para peças com textura. É o que a literatura faz com peças reais; ninguém localiza uma peça de céu entre 3000 por template matching.
10. Feito em 2026-10-30: E-sym rigoroso (M5, decidido) e secção montada (linhas de corte, localização, fotometria). Feito em 2026-10-31: E-fundo, S1, **`segment_scan`** (híbrido promovido: A2/B2 0,38 mm, 20/20/20, teste de regressão `slow`) e **E-real** (inconclusivo: top-1 22/25, 20/21 nas células interiores; desvio isotrópico célula↔silhueta +0,48 mm a calibrar no M10; sombra adiada; linhas de corte na relva **[F]**, `EREAL.md`). Próximo: M1 (GT com as 40 peças do E-sym e as células da secção) → M2 → M3 (E-fundo primeiro, S1) → M4 → M12 (+ perfil do puzzle, M13 i) → M10 (com E-real; E-real-2 é o primeiro uso real) → M13 ii (calibração) → M11 … M0 (base de medida) está feito. Generalização para outros puzzles: §11. Ordem completa na secção 7.

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
- Scans: 9 fundos a 300 dpi (2480×3504 = A4) e 3 a 600 dpi (rosa, azul_claro, impressora) **[V]**. O scanner dá escala absoluta (0,0847 mm/px), sem perspetiva, sem sombras, luz constante. **É a melhor câmara que o projeto tem e nunca foi explorada como tal.**
- A GUI pede W/H em cm e nº de peças; o motor recebe `pixels_per_cm` só para reportar, não para restringir escala **[V]**.

### 3.3 Segmentação (`segment_pieces`) — 23 imagens corridas, overlays em `diagnostico/segmentacao/*__contours.jpg`

| Imagem | Detetadas | Clusters | Observação (vi a imagem) |
|---|---|---|---|
| scan verde / laranja / azul | 61 / 61 / 60 | 0 / 0 / 1 | Contornos justos. Contagem física à vista (2026-10-31) **N = 61 [V]**: a estimativa anterior "≈ 63–65 por croma" estava errada; o par encaixado (ids 54 + 60) sai como 2 deteções. |
| scan preto / vermelho / bege / rosa | 56 / 58 / 56 / 59 | 1 / 0 / 3 / 3 | Bom. |
| scan amarelo / amarelo-claro / verde-claro | 46 / 43 / 42 | 3 / 6 / 4 | Peças creme invisíveis em fundo pálido; contornos errados em peças pálidas (#12, #13). Limite físico de contraste, já conhecido. |
| scan verde grupo2–5 | 59 / 53 / 54 / 52 | 0 | Bom. |
| scan verde grupo6 (secções já montadas) | 25 | 3 | Grupos montados corretamente marcados `is_cluster`; 3 peças soltas junto a um grupo ficam cortadas. |
| scan impressora (branco, 600 dpi) | 61 | 1 | Bom apesar do fundo branco. 13 s. |
| IMG_2114.DNG (telemóvel, papel branco) | 72 | 0 | 64 peças físicas → 8 sobra-detecções (fragmentos/sombras). |
| IMG_2108 / 2109 / 2111 (telemóvel, tapete, peças juntas) | 56 / 73 / 69 | 15 / 20 / 13 | Mau: metade das peças em cluster ou perdidas; modelo de fundo global falha no tapete com linhas impressas. |
| IMG_2110 (telemóvel, tapete, peças espaçadas) | 175 | 5 | Surpreendentemente razoável para peças espaçadas; perde as que estão junto às secções montadas. |
| IMG_2100 (foto da caixa) | erro | — | Esperado; não é foto de peças. |

Conclusões: funciona para scans com fundo saturado e peças espaçadas (**[V]**, ≈95 % recall estimado, sem GT manual); falha em fotos de telemóvel com peças encostadas **[V]**. Defeitos que importam a jusante: franjas e "dentadas" no contorno em 9/61 peças do scan verde (#2, #6, #11, #18, #26, #27, #44, #47, #52), que são a principal fonte de ruído de forma (correlação 0,69 entre rugosidade e distância de re-scan) **[V, forma]**; variação de área da mesma peça entre scans de −5,4 % a +1,6 % **[V]**. Métrica de IoU contra máscaras manuais: **[NT]** (não há máscaras manuais). Defeitos novos, vistos nos scans dos gémeos de 2026-10-30 **[V]**: (S1) uma peça a menos de ≈ 1,2 mm do bordo do scan é descartada em silêncio (`_FRAME_MARGIN_FRAC`) — **corrigido 2026-10-31 [V]**: as peças junto ao bordo ficam, com `touches_frame`; B2 passa a 20/20 sem moldura; o filtro antigo descartava também **18 peças reais em 7 scans de julho** (preto 56→60, verde_claro 42→43, verde_grupo2 59→60, grupo3 53→55, grupo4 54→62, vermelho 58→59, vermelho_grupo5 53→54; as contagens da tabela acima eram subcontagens), todas as peças já detetadas ficaram byte-idênticas, 7/7 testes verdes em OpenCV 4.11 e 5.0; (S2) a fronteira fica serrilhada no lado da sombra e morde até ≈ 1 mm nas peças escuras de prado. Detalhe em `docs/diagnostico/gemeos/RESULTADOS.md`. `segment_scan` (híbrido promovido, 2026-10-31) cumpre o critério de fronteira em scans; rugosidade passa a diagnóstico; modelo de sombra adiado (condição: E-real c1). Números da variante `scan`: ver a secção "Atualização 2026-10-31" de `docs/diagnostico/gemeos/RESULTADOS.md`. Viés conhecido: corda 18,6 mm contra 18,2 nominal (a sombra está incluída).
 **Linhas de corte em arte texturada (relva, bloco BD, E-real) [F]**: vale de L\* 1–3/41 sem/com prior; crista `branco` com prior 26–29/41 por área mas 1–2 no QC; frente vs rot180 3,0 mm contra 0,12 no céu (`EREAL.md`).

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

Causa medida: L\* mediano das peças digitalizadas 86 (p10 59, p90 95); só 1 % (caixa) a 6 % (arte limpa) dos blocos à escala da peça atingem L\* ≥ 86, e 8–14 % atingem ≥ 80, contra 43/61 peças **[V, recomputado por mim]**. O fundo não é a causa (Δ entre fundos ≈ 1 unidade Lab). Em 2026-10-29 o Tiago disse "ao acaso" (8.2.2) e concluí daí "desfasamento de captura" do scanner; **essa conclusão foi desmentida em 2026-10-30 [F]** (parágrafo seguinte); em 2026-10-31 o Tiago corrigiu: as peças foram **pré-filtradas (as que não conseguia localizar)**. O motor só remove a média de L por assinatura; não compensa um deslocamento de L\*, e o croma absoluto amarelo-esverdeado leva as peças para prados **[V]**.

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
- **Conclusão (i): seleção da amostra** (as 61 peças foram pré-filtradas pelo Tiago: as que não conseguia localizar), com um desvio pequeno e uniforme do scanner. As 61 peças de julho são claras de verdade (nuvens e pôr do sol). A causa do 0/61 fica: peças claras de céu e nuvem sem textura (limite da arte) e referência = foto da caixa com margem. A normalização fotométrica do M9 reduz-se a um deslocamento de ≈ −5 L\* mais um pequeno ajuste em b\*.
- Resolvido 2026-10-31 **[V, Tiago]**: as 61 peças foram pré-filtradas (as que não conseguia localizar) — o L\* 86 é **seleção**. O B (0/61) mede o motor na amostra mais difícil possível; não extrapola para peças aleatórias **[NT]**.
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
3. **Referência inadequada e peças sem textura.** Referência = foto da caixa com a margem incluída na pesquisa; escala assumida a partir do nº de peças em vez da célula física conhecida; peças claras de céu e nuvem sem textura (limite da arte). Corrigido em 2026-10-30: o fosso fotométrico (L\* 86 contra 50) **não** vem do scanner, que é fiel à arte (deslocamento uniforme ≈ +5 L\*); a hipótese anterior de "desfasamento de captura" é falsa **[F]** e as peças de julho eram mesmo claras (amostra pré-filtrada pelo Tiago: seleção). Nenhuma destas coisas era compensada pelo motor. **[V]**
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

**Atualização 2026-10-30: a repetição é por rotação de 180°, não por translação [V].** A simetria da matriz é pontual: (l, c) ↔ (48 − l, 65 − c), rodada 180° (bordas e interior (2,2)↔(46,63) conferidos à mão pelo Tiago). O teste da moldura original (colunas c, c+32, c+16) procurava translações e daria **falso negativo**; a ressalva da nota 2 da `revisao.md` ("blocos em posições irregulares ou espelhados escaparia") estava **certa**. A amostra de julho é consistente: 61 peças ao acaso dão 61·60/2/3007 ≈ 0,61 pares de gémeos esperados (P(0) ≈ 0,54; amostra **não aleatória**: pré-filtrada por dificuldade visual, logo o P(0) não é evidência sobre a frequência de gémeos) e o mínimo observado (0,85 mm em 1830 pares) exclui gémeos. Como 64 é par, nenhuma peça é o próprio gémeo: **1504 pares**. Grupos de 4 (sub-matrizes): excluídos à mão (colunas 5, 10 e 12; nada coincide com os deslocamentos de 16 ou de 32 colunas nem com 33−c rodada), por isso só pares; o centro (colunas 32/33, linha 24) não é testável. Os gémeos são **fisicamente intercambiáveis** (observação do Tiago): uma encaixa onde a outra pertence, só a imagem as distingue.

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
| **E-fundo** | Que fundo e que método de contorno dão a fronteira mais repetível e completa em scans? **Feito 2026-10-31 [V]** (`docs/diagnostico/fundo/RESULTADOS.md`): **verde vence** (RMS entre fundos em pose diferente 0,44 mm com (c), recall 61/61, rugosidade p95 1,095; azul 0,55, vermelho 0,60, laranja 0,62); sem scan de confirmação a pedir. **Método (c) falha o critério M3 [F]**: E-sym A2/B2 0,77 mm, top-1 15/20 — apaga relva verde-viva nas peças de prado de B2; é o contorno mais limpo nas peças claras (re-scan 0,42 mm, |ΔL| 0,13 mm, corda 18,2 mm). O híbrido (b) continua a ser o único que cumpre (0,38 mm, 20/20). N = 61 contado à vista (a estimativa "63–65" estava errada). | 12 scans de julho (mesmas peças; 600 dpi reamostrados a 300) × 3 métodos {(a) `segment_pieces`, (b) limiar simples (separação por `segment_pieces`), (c) limiar simples + rejeição da sombra por tonalidade}: RMS free da **mesma peça entre fundos** (mediana/p90; pares mesma pose vs pose diferente), **recall** (vs N contado à vista), **rugosidade** (p95), corda mediana vs 18,2 mm nominal. Ranking pré-registado: elegível se recall ≥ 95 %; ordena por RMS mediano entre fundos (pose diferente), desempate p90; porta rugosidade p95 < 1,1. **Método** vencedor confirmado no E-sym A2/B2 (verde). | método com gémeo A2/B2 ≤ 0,5 mm e top-1 20/20 (critério M3); fundo com recall ≥ 95 % e RMS entre fundos ≤ ruído de re-scan (≈ 0,4 mm) | nenhum método cumpre o E-sym com fundo algum → M3 precisa de outro desenho (não só limiar) |
| **E-real** | A cadeia real funciona: contorno de célula extraído das **linhas de corte de uma secção montada** → gémeo entre as soltas? **Critério de saída do M10.** **Feito 2026-10-31 [V, `docs/diagnostico/gemeos/EREAL.md`]: inconclusivo.** Células UL (céu, `seccao_celulas.json`) → 28 soltas do canto BD (`segment_scan`): top-1 **22/25 (88 %)** com filtro de classe, pools de 28 e de 68; **20/21** nas células interiores ao bloco; margem < 1,5 em 9/25. As 3 falhas são células UL más (lado no contorno do bloco (2,7), (5,7); nuvem (5,5)). RMS gémeo célula↔silhueta 0,76 mm: a silhueta fica **+0,48 mm para fora** nos 4 lados (isotrópico, escala 1,048), não é sombra (assimetria baixo−cima 0,09, esq−dir 0,05 mm) → modelo de sombra continua adiado; **calibrar o desvio isotrópico no `find_twin`** (estimativa circular: margem < 1,5 em 3/25). Linhas de corte na relva (bloco BD): vale de L\* 1–3/41 **[F]**; variante `branco` (crista de L\*−1,5C\*) com prior 26–29/41 por área, só 1–2 passam o QC; frente vs rot180 3,0 mm (céu 0,12). | Secção do canto sup. esq. (frente 300 dpi, 40 células com (l, c)) → gémeas no canto BD (28 soltas + bloco montado frente e rot180, `gt_canto_BD.md`). RMS free célula↔silhueta, top-1 entre as 28 e num pool de 68, margem, viés por lado, ruído das linhas de corte com mudança de pose. | top-1 ≥ 95 % das células testáveis, margem ≥ 1,5; RMS mediano reportado | top-1 < 80 % |
| **E-real-2** | Primeira medição do **desempate pela imagem** em uso real: peças soltas de céu ↔ gémeas de relva (BE → céu). Validação barata, com peças pré-filtradas, antes de digitalizar a relva legada por blocos. **Corrido 2026-10-31 [V, `docs/diagnostico/gemeos/EREAL2.md`]; aguarda confirmação física.** Memória de 186 soltas (f2p1 segmentou 40 das 42: 2 peças coladas à tira branca do papel perdem-se, defeito S3). Forma: **2 propostas** para as 20 BE (1 aceite: BE(2,4) → f2p1 #4, d₁ 0,41 mm, margem 2,39; 1 ambígua: BE(5,5) → f1p1 #6, d₁ 0,54, única a passar), ambas em céu e vizinhas mútuas; 18 sem gémeo (d₁ 0,81–1,95 mm, gama dos não-gémeos). **0 falsos positivos** pela forma em 10 472 pares negativos conhecidos (1 ambígua, nunca proposta). Controlo E-sym 17/20 aceites (os 3 falham só no filtro de cordas de 1 mm em peças de borda; com 2 mm 20/20 e nenhum falso positivo novo). Imagem (ΔE Lab contra a célula gémea da arte, L\* − 4,8): as 2 propostas têm ΔE 8,7 e 10,8 (percentil 1 das 98 de céu, p90 = 50); a imagem não muda nem contradiz nenhuma proposta; separação fraca em geral (célula certa em 1.º em 3/20 para os top-1; a rotação prevista ganha às 3 restantes em 9/20). Localização conjunta de um par pela imagem nos 20 pares E-sym: célula certa na posição mediana 26 de 3008 (4 entre as 214 de borda; top-10 17/20); o par BE(2,4) + f2p1 #4 põe (46,4) em 1.º entre as 2790 interiores (n = 1). Ficheiros para o Tiago: `ereal2_propostas.txt` e `ereal2_<folha>_propostas.jpg`. Confirmação física 2026-10-31: 2/2 **[V]** (f2p1 #4 em (2,61) encaixa; f1p1 #6 forma confirmada, (5,60) sem vizinhas → `posicao_conhecida`). Re-executado com S3 corrigido (188 soltas): mesmas 2 propostas, 0 falsos positivos em 10 608 + 4 950 pares, cordas por tipo de lado (E-sym 20/20). `EREAL2.md` §7–§8. | Entrada real = `gt_canto_BE_soltas_300dpi.jpg` (20 interiores de relva do canto inferior esquerdo + borda em L; GT por célula, gémea de BE(k, j) = (k, 65 − j)) + 4 folhas de céu `ereal2_ceu_{f1p1,f1p2,f2p1,f2p2}_300dpi.jpg` (100 peças escolhidas pelo aspeto do canto superior direito); **não** a tira de relva em 6 mosaicos. Memória = 188 soltas (20 BE + 100 céu + 28 BD + 40 E-sym). Métrica = **precisão das propostas** (aceites / ambíguas / sem gémeo) confirmada fisicamente pelo Tiago, **sem recall** (não se sabe quantas gémeas estão nas 100); saídas em `ereal2_gt_BE.json`, `ereal2_propostas.txt` e `ereal2_<folha>_propostas.jpg`. | top-1 confirmado ≥ 90 % das gémeas testáveis (sobre as propostas aceites) | < 70 % (sobre as propostas aceites) |

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
| Estado persistente | round-trip (gravar → reabrir = mesmo mapa e mesmas consultas); confirmação → novas consultas | sem perdas; < 1 s |

Casos de uso reais e viáveis, por ordem (a do §0): (1) "coloquei esta peça em (l, c): qual das soltas é o gémeo?" (desempate pela imagem); (2) "quais destas 60 peças são pares gémeos entre si?" (pares no lote); (3) "que peça vai neste buraco?" (molde do buraco); (4) "onde está esta peça solta?" só para peças com textura e com aviso honesto; (5) "tenho esta secção montada e estas 60 peças no tabuleiro: quais encaixam, e em que lado?" (fronteira / encaixe entre soltas); (6) "onde na caixa está esta secção montada?" (fácil: NCC em L\* com canto e escala conhecidos deu 0,876 contra 0,408 na arte limpa **[V]**; SIFT falha no céu **[F]**). O primeiro uso real do (1) é a tira de relva montada: as soltas de céu são colocadas através dos gémeos de relva (E-real-2, depois do M10).

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
| M1 | **Dataset de validação v1** (secção 8) | Ficheiros em `images/gt/` + `gt.csv` com, por peça: id, (linha, coluna) ou casa (fila, k) nos scans dos gémeos, classe topológica manual, ficheiro/índice no scan. Conteúdo: as 40 peças do E-sym (A1/A2/B2, GT por casa) + as células da secção montada com (l, c) (`seccao_celulas.json`, só a frente a 300 dpi) + os pares interiores do canto (8.1.0 g, ≥ 31 com a secção do canto superior esquerdo) + os buracos do E-buraco (8.1.0 f); o bloco 5×8 fica para depois. **GT já disponível (2026-10-31)**: 41 células do canto BD (bloco montado, `gt_canto_BD.md`) + 28 soltas interiores + 40 células do canto superior esquerdo. | fotos do utilizador | médio (depende do utilizador) | P |
| M2 | **Referência = arte** | Função que recorta a referência à bbox da arte (manual por 4 cantos ou automática), guarda a homografia e expõe `cell_px = (W/64, H/47)` (e a célula do gémeo (48 − l, 65 − c)); o motor passa a usar escala fixa ±5 % quando a célula é conhecida; o prior de borda usa a bbox da arte. Ler `PuzzleOriginal.jpeg` ignorando o EXIF (secção 9). Reportar E6 sobre M1. | M0, M1 | baixo | P–M (implementer) |
| M3 | **Segmentação ao serviço da geometria** | **E-fundo ✅** (verde vence; (c) rejeição da sombra por tonalidade falha o E-sym em peças de prado: 0,77 mm, 15/20) → **S1 ✅** → **próximo passo [NT]**: modelo de sombra só numa faixa exterior de ≈ 1,2 mm ligada ao fundo e só nos lados virados para a sombra (lado inferior e esquerdo no referencial do scanner), linha preta da aresta como marcador do lado da sombra, fundos acromáticos fora de âmbito; `segment_scan` ✅ (2026-10-31: híbrido promovido, cumpre o E-sym). Em scans: **fronteira sem mordidelas nas peças escuras e com a sombra projetada tratada** (critério: E-sym com o contorno de `segment_pieces` ≥ o híbrido, isto é, gémeo ≤ 0,5 mm e top-1 20/20); **peça junto ao bordo não descartada** (S1 ✅; S3 ✅ 2026-10-31: tira branca do papel removida antes da rotulagem, `touches_strip`, teste sintético); franjas/dentadas removidas (rugosidade < 1,1 em ≥ 95 % das peças); peças "mated" sinalizadas por área/lados F; IoU ≥ 0,97 em 20 máscaras manuais; dp de lado ≤ 0,3 mm entre re-scans; **extração de linhas de corte em secções montadas pela frente a 300 dpi** (Hessiana + histerese/watershed; **regra de produto (2026-10-31): as linhas de corte servem só para secções de céu e para o legado**, por isso o alvo "≥ 90 % de células sem prior" deixa de ser exigido para arte texturada; para o céu mantém-se o que há: 68 % sem prior e 91 % com prior da grelha); contorno do buraco em blocos com peças retiradas. `segment_scan` (híbrido promovido, 2026-10-31) cumpre o critério de fronteira em scans; rugosidade passa a diagnóstico; modelo de sombra adiado (condição: E-real c1). Números: secção "Atualização 2026-10-31" de `docs/diagnostico/gemeos/RESULTADOS.md`. **Linhas de corte em arte texturada: [F] no E-real** (relva: 1–3/41 com o vale de L\*; `branco` + prior 26–29/41 por área, 1–2 no QC) — o alvo histórico ≥ 90 % sem prior exigiria outro detetor (por testar: fusão frente + rot180, detetor de crista + prior forte, `EREAL.md` §limites); **o detetor para arte texturada fica fora do M3 e não se escala ao planner agora** [decisão 1, 2026-10-31]; a relva legada digitaliza-se solta por blocos (§0). | M1 | médio | M (implementer) |
| M4 | **`src/shape.py`** (cantos, lados, classe, ID de forma) | E1 ≥ 95 %, E2 ≥ 95 %; lado como unidade (perfil, corda, tipo) e dicionário de cortes; substitui a classificação de `edges.py` (que marca só 8/20 bordas nos scans dos gémeos); testes sintéticos + GT. | M1, M3 | médio (cantos é o passo frágil; método já prototipado) | M (implementer) |
| M12 | **`src/state.py`: estado persistente** | índice de peças, mapa do tabuleiro (célula → peça), histórico só-acrescentar, formato em disco do §10; critério: round-trip gravar→reabrir sem perdas, replay do `log.jsonl` reconstrói `board.json`, cada confirmação gera as consultas novas (gémea pendente, buracos vizinhos); o índice guarda o **lote/saco (= scan) e o nº no lote**; entidade **par de gémeas** (duas soltas) com células candidatas conjuntas; lista "ir buscar"; a confirmação **reavalia a memória**; estados `posicao_conhecida` (peça) e `ocupada_legado` (célula, por foto); reconciliação com a foto do tabuleiro; `ingest --bloco` para os blocos de relva legada; plano mínimo em `docs/plano-m10-m12.md` §3 | M4 | baixo | P–M (helper com revisão do implementer) |
| M14 | **Mapa de ocupação por foto de telemóvel** | Protótipo 2026-10-31 (`tools/diagnostico/ocupacao/ocupacao.py`, `docs/diagnostico/ocupacao/OCUPACAO.md`): moldura por 4 retas robustas + homografia (borda completa), grelha 64 × 47, classificação cheia/vazia por célula (modelo local do feltro + arte como apoio), GT 244 células (218 de borda + (2,61) cheia + 25 vazias conhecidas), concordância entre as fotos a e b (`images/board/mapa_2026-10-31_{a,b}.jpg`). Resultado: GT corrigida ((1,29) vazia) 99,6 % nas duas fotos: 0 trocas cheia↔vazia em 244 células, 1 incerta por foto ((42,58) em a, (1,34) em b); moldura RMS ≤ 0,03 célula (sem distorção mensurável), grelha refinada pelo anel de borda (desvio 0,15 → 0,12 célula); concordância a/b 2993/3008 (15 discordâncias, todas certa↔incerta); 581 células cheias na fusão (filas 41–47: 2, 9, 23, 55, 61, 64, 64). Achado: (1,29) está vazia nas duas fotos — a borda NÃO está completa (217/218), a confirmar fisicamente pelo Tiago. Promoção a `src/board.py` no M12 (fonte `foto` do mapa; reconciliação). Limite: dá ocupação, não forma — não substitui digitalizar a relva legada solta. Critério: ≥ 99 % na GT e concordância a/b ≥ 99 %. | M12 (promoção); protótipo independente | médio (luz, reflexos, feltro) | M (implementer) |
| M13 | **Perfil do puzzle e calibração** (§11) | (i) esquema do perfil `puzzle.json` e pasta por puzzle `projects/<id>/` entram **com o M12** (o `project.json` do §10 inclui/referencia o `puzzle.json`); (ii) rotina de calibração (grelha + simetria a partir das 4 bordas) **depois do M10** (usa `find_twin`). Aceitação: a calibração sobre os scans deste puzzle devolve 64 × 47 e rot180 sem ajuda. | M12, M10 | baixo | P–M (helper + implementer) |
| M10 | **`src/twin.py`: encontrar o gémeo** | `find_twin(peça, pool, índice)`: filtro de classe, filtro de cordas (≈ 1 mm por lado), RMS free, gap (aceitar se d₁ ≤ 0,5 mm e d₂/d₁ ≥ 1,5), **imagem obrigatória** (teste 1-contra-1 na célula (48 − l, 65 − c)), rejeição calibrada, índice persistente. Alvo: top-1 ≥ 95 %, falsos gémeos ≤ 5 % com pool ≥ 500. **Condicionado ao M3** (fronteira). **Não fechar sem E-real** (§5). **E-real 2026-10-31: inconclusivo** (22/25, 20/21 interiores; `EREAL.md`): acrescentar ao `find_twin` a **calibração do desvio isotrópico célula↔silhueta (+0,48 mm, escala ≈ 1,048)** com `t` por modalidade (silhueta↔silhueta ≈ 0,5 mm; célula↔silhueta a calibrar fora da amostra) e um QC das células (4 cantos, lados F esperados, rugosidade, área) antes da consulta. O E-real-2 (tira de relva → céu) é o primeiro uso real, não o critério de saída. Leave-one-out do desvio isotrópico (2026-10-31): margem < 1,5 em **3/25** fora da amostra (era 9/25; gémeo mediano 0,76 → 0,40 mm com o desvio, 0,56 com a escala; `ereal.c1_loo`). **Filtro de cordas: 1 mm é apertado para peças de borda** (E-real-2: 3/20 pares E-sym falham só aí, |ΔL| 1,0–1,8 mm porque o canto do lado reto escorrega; com 2 mm 20/20 sem falso positivo novo) → `find_twin` usa ≈ 2 mm ou tolerância maior nos lados vizinhos de um F. E-real-2 (BE → céu, `EREAL2.md`) = primeira medição do desempate pela imagem. **Filtro de cordas por tipo de lado adotado** (2 mm no lado F e nos adjacentes, 1 mm nos outros; 0 falsos positivos em 10 608 negativos conhecidos, E-sym 20/20); plano de implementação em `docs/plano-m10-m12.md`. | M2, M3, M4, M12 | médio | M (implementer) |
| M11 | **Molde do buraco** (`src/fit.py`, 1.ª metade) | Dado um buraco num bloco, ranquear as soltas pelo molde dos lados dos vizinhos + imagem: ≥ 90 % certa-ou-gémea em top-1 e ≥ 85 % a certa com imagem (E-buraco). | M1, M3, M4 | médio | M (implementer) |
| M7 | **Secção montada como referência local** | Localizar a secção na arte pelo método de **canto e escala conhecidos** (os 2 lados retos dão o canto, o passo da célula dá a escala; NCC em L\* com jitter: 0,876 contra 0,408 na arte limpa e 0,82 contra 0,40 na caixa, canto superior esquerdo, 44 peças **[V]**); SIFT só em zonas com textura (falhou no céu: 0 inliers **[F]**). Extrair a fronteira (lados livres) com os seus perfis. Erro ≤ 1 célula. | M2, M4 | baixo | M |
| M6 | **Encaixe geométrico + imagem na fronteira** (`src/fit.py`, 2.ª metade) | E4 e E5 nos alvos (vizinho verdadeiro ou gémeo do vizinho); API `rank_partners(side, pieces) -> shortlist + confiança`, O(N) por consulta; testes sintéticos (par gerado = melhor custo; F rejeitado). | M4, M11 | médio | M (implementer) |
| M8 | **GUI de montagem assistida** | Carregar scan de peças + foto de secção; modo "ir buscar ao lote N, peça X" (com o recorte da peça; a confirmação gera as consultas novas); modos gémeo, buraco e fronteira: para cada consulta mostrar as 3 melhores peças com a peça recortada colocada no sítio; exportar JSON. Teste de uso: utilizador coloca 20 peças seguidas com ≤ 2 erros. | M10, M11, M6, M7, M12 | médio (GUI de 1268 linhas) | M–G |
| M9 | **Localização de peça solta na caixa, honesta** (terciário) | **Requisito**: normalização fotométrica scanner→referência reduzida a um deslocamento de ≈ −5 L\* (mais um pequeno ajuste em b\*; `SECCAO.md` §C), aplicada antes da assinatura; com M2: reportar top-1/top-5 por célula e acerto de zona no GT; `high` ≥ 90 % preciso ou não mostrar `high`. Nota: o 0/61 era amostra pré-filtrada; medir em peças aleatórias do M1. | M2, M1 | alto (limite da arte) | M |

**Cortar** (não fazer nesta ronda, nem em "futuro"): GPU/CUDA, REST API, ML de classificação, câmara live, correção de perspetiva por 4 cantos para as peças (o scanner resolve; volta **só** para a foto do tabuleiro do M14), mais experiências de fundos de cor (já provado: verde/laranja/preto/vermelho servem), solver global das 3000 peças, CLI `main.py` (manter só como smoke test ou apagar), `requirements-dev.txt` inchado.

**Dataset de validação com ground truth** — como criar: secção 8. Quantas peças: as 40 do E-sym (GT por casa, já digitalizadas) + as ≈ 40 células da secção montada com (l, c) + os pares interiores do canto (8.1.0 g) + ≈ 10 buracos chegam para E-sym, E4, E-buraco e E5 com intervalos de ±10 pontos percentuais; o bloco 5×8 contíguo (secção 8.1.1) acrescenta 40 posições na caixa conhecidas para o M9 (linha, coluna → célula → coordenadas na arte via M2).

---

## 8. Perguntas que preciso que respondas / fotos que preciso

### 8.1 Fotos para a experiência mínima (secção 5) e para M1

Material: o scanner que já usaste (digitalizações a 300 dpi, A4); papel verde saturado (o que usaste em `digitalização_fundo_verde.jpg`); uma régua ou um objeto de dimensão conhecida; o puzzle.

0. **Gémeos por rotação de 180° (E-sym, o mais barato e decisivo).**
   - (a) ✅ Contagem da grelha (64 × 47) e simetria (l, c) ↔ (48 − l, 65 − c), verificadas à mão pelo Tiago.
   - (b)(c) ✅ Scans A1 `coluna5-24_300dpi_folhaA.jpg` (borda de cima, c5–24, 4 filas de 5), A2 `colunas5-24_300dpi_rot180_folhaA.jpg` (as mesmas rodadas 180° na casa), B1 `coluna5-24_folhaB_300dpi.jpg` (gémeos da borda de baixo) e B2 `coluna5-24_folhaB_300dpi_rot180.jpg` (B1 com cada peça rodada 180°). Correspondência A(fila, k) ↔ B(fila, 4 − k). B1 é inutilizável (na fila 3 há 2 peças encostadas); usar B2. Descrição em `images/pieces/gemeos_2026-10-30.md`.
   - (d) substituído pelo (g).
   - (e) ✅ Secção montada de canto, frente e traseira a 300 e 600 dpi (`{frente,traseira}_{300,600}dpi.jpg`). Para secções montadas: **a frente a 300 dpi chega; a traseira é opcional; 600 dpi é desnecessário** (a traseira não fecha células sem prior e 600 dpi não acrescenta nada, `SECCAO.md` §A).
   - (f) **E-buraco (a fazer)**: bloco montado ≥ 5×5 sobre papel verde com 3–5 peças interiores não adjacentes retiradas; scan da frente a 300 dpi (traseira opcional); as peças retiradas misturadas num lote de 40–60 soltas e digitalizadas; GT num txt (buraco (l, c) → índice da peça no lote). ≈ 10 buracos. Nomes: `gt_buraco_<zona>_bloco_frente_300dpi.jpg`, `gt_buraco_<zona>_soltas_300dpi.jpg`, `gt_buraco_<zona>.txt`.
   - (g) ✅ **Feito 2026-10-31 (canto inferior direito)**: bloco montado pela frente + rot180 + 28 interiores soltas em vista explodida; faltam 8 peças; ficheiros `images/pieces/gt_canto_BD*.jpg` e ficha `images/pieces/gt_canto_BD.md`; disposição (bloco rodado 90° no sentido anti-horário) verificada contra a imagem em 2026-10-31. O E-real corre sobre estes dados (`tools/diagnostico/gemeos/ereal.py`, relatório `docs/diagnostico/gemeos/EREAL.md`, GT `docs/diagnostico/gemeos/ereal_gt.json`). Pedido original, para registo: **E-real + pares interiores num só trabalho.** Montar à mão o **canto inferior direito** (interior l41–46 × c58–63 = 36 peças; a borda já está). Antes de encaixar, **digitalizar as 36 soltas por ordem numa grelha 6 × 6** (fila = l, coluna = c, anotar a ordem num txt), papel do fundo canónico, 300 dpi, espaçadas ≥ 5 mm: `gt_canto_ID_soltas_300dpi.jpg` + `gt_canto_ID.txt`. Depois de montado, **digitalizar o canto montado pela frente** a 300 dpi: `gt_canto_ID_frente_300dpi.jpg` (segunda secção para linhas de corte; dá também ≥ 31 pares interiores de gémeos com a secção do canto superior esquerdo — substitui o pedido (d)). Se alguma dessas 36 já estiver colocada, não a tirar: anotar a célula.
   - (h) **E-real-2 — superado em 2026-10-31.** O pedido original (frente da tira de relva em ≈ 6 mosaicos A4 + lotes de céu) foi substituído, pela regra de produto do §0, por scans de peças **soltas**: `gt_canto_BE_soltas_300dpi.jpg` (20 interiores de relva do canto inferior esquerdo, GT por célula) e `ereal2_ceu_{f1p1,f1p2,f2p1,f2p2}_300dpi.jpg` (100 peças de céu), já entregues (`images/pieces/gt_canto_BE.md`). A relva legada da tira digitaliza-se solta por blocos (vista explodida) quando o E-real-2 justificar o investimento; as linhas de corte da frente não servem na relva (E-real).
   - (i) **Relva legada por blocos (protocolo, 2026-10-31).** Objetivo: pôr no índice a silhueta das peças de relva que já estão montadas (regra de produto do §0), para que as suas gémeas de céu (filas 2–7) passem a ter posição. Usa o mapa de ocupação (M14, `docs/diagnostico/ocupacao/ocupacao_2026-10-31.json`) para saber que células estão cheias.
     - **O que digitalizar:** só as células **interiores** da tira de relva (filas 41–46 conforme o mapa; a fila 47 e as colunas 1 e 64 são borda). **Não desmontar a borda**: as gémeas das peças de borda são borda e já estão colocadas (217/218: falta (1,29), segundo o mapa) — não dão céu. O céu legado (filas 2–3 e as secções de cima) também não se desmonta: as gémeas são relva já montada e as linhas de corte funcionam no céu.
     - **Bloco** = 8 colunas × todas as filas interiores montadas nessas colunas (≤ 6 filas) → ≤ 48 peças por folha. Cabe em A4 com ≥ 1 cm de margem: área útil 190 × 277 mm; em vista explodida com 6 mm entre peças o passo é ≈ 24,5 × 24 mm → 8 colunas = 196 mm no eixo longo do papel, 6 filas = 144 mm no eixo curto. Blocos de colunas: `c02–09`, `c10–17`, `c18–25`, `c26–33`, `c34–41`, `c42–49`, `c50–57`, `c58–63` (o último tem 6 colunas) → **8 blocos**. Ordem: da esquerda para a direita, a começar no canto BE (as 100 peças de céu já digitalizadas foram escolhidas pelo aspeto do canto superior direito, cujas gémeas são a relva do canto inferior esquerdo). Estimativa pelo mapa: **202 células interiores de relva cheias (mais 18 incertas) nas filas 41–46 → 8 folhas**, 20–31 peças por bloco (c02–09: 25, c10–17: 27, c18–25: 21, c26–33: 23, c34–41: 20, c42–49: 27, c50–57: 31, c58–63: 28; fusão a/b de 2026-10-31) (fórmula: Σ células cheias por bloco de colunas; 1 folha por bloco se ≤ 48, senão 2).
     - **Como (uma sessão = um bloco, ≈ 10–15 min):** 1) tirar uma foto do bloco ainda montado com o telemóvel (controlo); 2) levantar peça a peça e pousar no papel verde **na mesma disposição e orientação** (sem rodar), espaçadas ≥ 5 mm, imagem para cima, **≥ 1 cm de margem a toda a volta** (nada encostado ao bordo do vidro nem à tira branca do papel — defeito S3); células vazias (buracos) ficam **vazias no papel**, na posição correspondente; 3) tampa fechada, 300 dpi, JPEG; 4) repor as peças no tabuleiro; 5) preencher a ficha.
     - **Nomes:** `images/pieces/relva/relva_bloco_c02-09_300dpi.jpg` e ficha `images/pieces/relva/relva_bloco_c02-09.md`. Ficha (modelo):
       ```
       # Bloco c02–09 (relva legada) — 2026-11-__
       Filas presentes por coluna: c2: l43–46 | c3: l43–46 | c4: l44–46 | … | c9: l42–46
       Células vazias dentro do bloco (l, c): (43,4), …
       Nº de peças na folha: __   Disposição: igual ao tabuleiro, sem rotação, fila 41 em cima
       Observações: peça (44,7) tem a aba partida; …
       ```
       O script de ingestão (`ingest --bloco`, M12, `docs/plano-m10-m12.md` §3.2) converte a posição na folha em (l, c) pela grelha e pelas contagens da ficha, como o `loose_pieces` do E-real; a ficha é a verdade de terreno se houver desacordo.
     - **Depois de cada bloco:** o índice passa essas células de `ocupada_legado` (foto) a `colocada` com silhueta; a partir daí qualquer lote de céu pode receber propostas "vai buscar" para as gémeas dessas células.
1. **Bloco contíguo montado, 5 linhas × 8 colunas = 40 peças** (depois do E-buraco e dos pares interiores), numa zona com textura (ex.: a aldeia com a igreja, ou a árvore amarela com o prado — não o céu). Inclui pelo menos **uma fila de borda** (idealmente um canto do puzzle: assim há 2 cantos-de-borda e ~12 peças de borda) para testar F.
   - Foto 1: o bloco **montado**, de cima, com uma régua ao lado, luz difusa (sem flash), telemóvel o mais paralelo possível à mesa, bloco a ocupar ≥ 60 % do enquadramento. Serve para GT de adjacência e para M7. Se couber no scanner (um bloco 8×5 mede ≈ 15 × 9 cm — cabe num A4), **digitaliza-o também montado** a 300 dpi: melhor ainda.
   - Antes de desmontar: **anota a grelha** — uma foto do bloco com post-its ou um esquema em papel com os números 1–40 por (linha, coluna), e os números das linhas/colunas no puzzle se souberes (contando a partir do canto).
   - Depois desmonta e **digitaliza as 40 peças soltas** em papel verde, imagem para cima, **espaçadas ≥ 5 mm**, sem tocar, a 300 dpi, tampa fechada. Precisas de saber que peça é que: digitaliza-as **por ordem numa grelha regular** (5 filas de 8, mesma ordem do bloco) para que a posição no scan dê o id. Faz **dois scans**: um por ordem, outro com as peças baralhadas e rodadas (para E2); do segundo não precisas de GT.
2. **20 peças de uma zona distante** do bloco (opcional, baixa prioridade): só para ter peças de céu no GT de M9 e de M1. O E3 original (repetição entre zonas por translação) foi substituído pelo E-sym. Por ordem conhecida num scan de papel verde; se forem de um grupo já montado, foto montada antes, como em 1.
3. **Um scan de calibração**: o mesmo papel verde com uma régua metálica ou uma folha quadriculada, a 300 dpi, para confirmar que 1 px = 0,0847 mm nos dois eixos (resposta a "não sei qual eixo é horizontal" e a ±0,25 mm de incerteza). Opcional mas barato: uma peça junto a um cartão cinzento neutro (ou um papel branco e um preto) para medir a curva de tom do scanner (a causa do L\* 86 ficou respondida em 2026-10-31: seleção da amostra, ver 3.6).
3b. **Scan de uma secção montada de prado ou floresta** (um A4, pela frente, a 300 dpi). A secção de canto de céu e nuvem já serve de curva fotométrica (scan ≈ arte + 5 L\*, `SECCAO.md` §C); falta uma de prado/floresta para confirmar o desvio fora do céu. Serve também ao M7 e às linhas de corte do M3.
3c. **Scan de confirmação do fundo (condicional)**: só se o vencedor do E-fundo (§5) for diferente de verde: a folha B (peças de relva, mesma disposição de B2) nesse fundo, 300 dpi, nome `confirmacao_fundo_<cor>_folhaB_300dpi.jpg`. Se o vencedor for verde, não é preciso.
4. **Não precisas** de: mais fundos de cor, DNG de telemóvel, fotos com sombra, fotos de peças encostadas.

Formato: JPEG do scanner (como até aqui) ou TIFF; nomes com a zona e a ordem (ex.: `gt_bloco_igreja_ordenado.jpg`, `gt_bloco_igreja_baralhado.jpg`, `gt_bloco_igreja_montado.jpg`, `gt_ceu_20_ordenado.jpg`, `calib_regua.jpg`).

### 8.2 Perguntas

Respondidas em 2026-10-29: **8.2.2** as 61 peças foram tiradas "ao acaso" (corrigido em 2026-10-31: pré-filtradas, ver 8.2.2/8.2.9); **8.2.6** objetivo principal = montagem assistida (revisto em 2026-10-30: encontrar o gémeo); **8.2.7** fixar OpenCV 4.11. Respondidas em 2026-10-30: a grelha é 64 × 47 (por contagem); a simetria de 180° e os grupos de 4 (à mão); a memória de cortes (o lado como unidade) foi adotada; fotometria: o scanner é fiel à arte e as peças de julho são mesmo claras (`SECCAO.md` §C; a explicação "composição do saco" foi corrigida em 2026-10-31: seleção). Respondidas em 2026-10-31: **8.2.2/8.2.9** (pré-filtradas: seleção), **8.2.4** (borda completa + um pouco de céu + um pedaço de relva), **8.2.8** (fluxo aceite e detalhado no §0). As restantes continuam abertas.

1. Confirmas que `PuzzleOriginal.jpeg` é a tua foto da caixa deste puzzle, e que `1186441_1.jpg` é a imagem de produto da mesma referência? (Assumi que sim: a homografia entre as duas tem 2597 inliers.)
2. ~~As 61 peças dos 11 scans de julho: de que zona do puzzle são?~~ — **Respondida 2026-10-31:** não eram aleatórias: foram pré-filtradas pelo Tiago (as que não conseguia localizar); o L\* 86 é seleção.
3. Que scanner/driver e definições usaste (300 dpi, "foto" ou "documento", correção automática de cor ligada)? Para a normalização fotométrica preciso de saber se a curva de tom é fixa. (Menos urgente desde 2026-10-30: o scanner é fiel à arte e o papel tem o mesmo Lab em julho e hoje.)
4. ~~Quanto do puzzle está montado hoje, e tens fotos das secções montadas de cima com régua?~~ — **Respondida 2026-10-31:** montada hoje a borda completa, um pouco de céu e um pedaço de relva.
5. Tens acesso a outro Clementoni 3000 da mesma coleção (New York 33546, San Francisco 33547, Coliseu 33548)? Um punhado de peças dele digitalizado responderia à reutilização de matriz entre referências, que nenhuma fonte confirma.
6. Qual é a tua tolerância de interação: aceitas um fluxo "digitalizo 60 peças → o programa diz, para cada lado da secção montada, as 3 melhores" (montagem assistida), ou insistes em "aponto uma peça → ponto vermelho na caixa"? A segunda só vai funcionar para peças com textura.
7. Python: ficas com 3.13 e OpenCV 5, ou preferes fixar OpenCV 4.x? (Vou fixar o que disseres em `requirements.txt` no M0.)
8. ~~Fluxo do gémeo e do buraco: aceitas o índice crescente?~~ — **Respondida 2026-10-31:** fluxo aceite; detalhado no §0.
9. ~~O saco estava misturado? Escolheste as peças à vista?~~ — **Respondida 2026-10-31:** as 61 peças foram pré-filtradas (as que não conseguia localizar); o L\* 86 é seleção; o 0/61 é o pior caso e o desempenho em peças aleatórias é **[NT]**.

---

## 9. Backlog

- **Atualizar o README** com o objetivo novo, a arquitetura, o perfil do puzzle e a generalização (§11) (pendente).
- **Armadilha EXIF:** `images/puzzles/PuzzleOriginal.jpeg` tem EXIF orientation = 3 com os píxeis já direitos. `cv2.imread` aplica a etiqueta e devolve a foto invertida; o PIL não. Usar `cv2.IMREAD_IGNORE_ORIENTATION` ou PIL (o motor e `matching/common.py` usam PIL). Os scans não têm a etiqueta.
- **M3 (explícito), defeitos de `segment_pieces` vistos nos gémeos:** (S1) ✅ corrigido 2026-10-31 (`touches_frame`; `_FRAME_BLOB_SPAN` rejeita só blobs de margem/tampa); fica no backlog: `_refine_boundary_band` rebenta (`cv2.remap`, limite 32767 px) se um blob enorme passar as guardas; em `scan_verde_grupo4` uma peça cinzenta no bordo esquerdo continua por detetar; os `gemeos_*.npz` do E-sym foram feitos com moldura de 64 px (contornos deslocam ≤ 2 px sem ela) — regenerar antes de reutilizar; (S3, 2026-10-31, E-real-2) ✅ corrigido 2026-10-31 (`touches_strip`): peça encostada à tira branca do papel (o papel verde não cobre a largura toda do scan) ficava ligada à tira na máscara e o componente era descartado sem `touches_frame` (2 das 42 peças de `ereal2_ceu_f2p1` perdidas); agora `_frame_strip_mask` tira a tira da máscara antes da rotulagem (e do limiar de `segment_scan`), f2p1 dá 42 e as outras contagens não mudam (`docs/diagnostico/gemeos/EREAL2.md` §8); (S2) fronteira serrilhada no lado da sombra e mordidelas até ≈ 1 mm em peças escuras de prado; (S4) `edges.py` marca borda só em 8/20 peças de borda. Critério do M3: E-sym com o contorno de `segment_pieces` ≥ o híbrido (gémeo ≤ 0,5 mm, top-1 20/20). O M10 fica condicionado a isto.
- Ler o dpi do cabeçalho JPEG e reamostrar 600→300 no carregamento (`shapelib.MM` assume 300 dpi).
- M12 estado persistente (`src/state.py`, §10); plano mínimo em `docs/plano-m10-m12.md`.
- M14 mapa de ocupação: GT corrigida ((1,29) vazia) 99,6 % nas duas fotos: 0 trocas cheia↔vazia em 244 células, 1 incerta por foto ((42,58) em a, (1,34) em b); moldura RMS ≤ 0,03 célula (sem distorção mensurável), grelha refinada pelo anel de borda (desvio 0,15 → 0,12 célula); concordância a/b 2993/3008 (15 discordâncias, todas certa↔incerta); 581 células cheias na fusão (filas 41–47: 2, 9, 23, 55, 61, 64, 64). Achado: (1,29) está vazia nas duas fotos — a borda NÃO está completa (217/218), a confirmar fisicamente pelo Tiago; falta a promoção a `src/board.py` e a reconciliação com o log.
- `segment_scan` feito (2026-10-31, híbrido promovido); viés da sombra (corda 18,6 contra 18,2 mm) registado; modelo de sombra adiado até o E-real mostrar viés.
- **Linhas de corte em blocos montados** (estado após `seccao.py`): frente a 300 dpi com Hessiana + histerese fecha 30/44 células (68 %) sem prior e 40/44 (91 %) com watershed e prior da grelha; a traseira não chega (0/44 sem prior); 600 dpi não acrescenta; black-hat falha pela textura "linen". Por testar **[NT]**: detetor de relevo para a traseira, fusão frente + traseira. Alvo do M3: ≥ 90 % sem prior.
 **E-real 2026-10-31 [F] em relva**: vale de L\* 1–3/41; resposta `branco` (crista de L\*−1,5C\*, `ereal.py`) com watershed puro e células crescidas até à linha média 26–29/41 por área, 1–2 no QC; frente vs rot180 3,0 mm. Por testar **[NT]**: fusão frente + rot180, prior forte (rede completa canto + passo) com refinamento local, detetor de crista/vale combinado.
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

---

## 10. Modelo de estado (esboço; sem código até o M12)

**Entidades**
- **Projeto** (`project.json`): referência ao **perfil do puzzle** (`puzzle.json`, §11: grelha, célula nominal em mm, regra de simetria, fundo e dpi canónicos), referência da arte (ficheiro, bbox/homografia do M2, `cell_px`), `schema_version`, datas.
- **Scan** (`S0001`): caminho relativo + sha256, dpi (lido do cabeçalho; reamostrar para 300 se 600), fundo (Lab mediano), data, método e versão de segmentação, lista de peças.
- **Peça** (`P0001`): scan_id + índice no scan; `lote` (id do scan = saco numerado) e `n_no_lote`; contorno em px do scan e em mm (centrado, CCW); bbox; recorte RGBA (`crops/P0001.png`); classe topológica; 4 lados {tipo F/T/B, corda mm, perfil 64 pontos}; vetor de forma (512 pontos complexos, métrica free) e assinatura Lab 4 × 4; **estado** ∈ {`solta`, `emparelhada` (par solta↔solta registado), `posicao_conhecida` (célula determinada, por gémea colocada ou por par, mas sem vizinha montada: a peça fica de lado etiquetada com a célula até haver onde a encaixar), `colocada`, `em_seccao`, `descartada`}; célula (l, c) se colocada; `seccao_id` se em secção; `same_as` (re-scan da mesma peça: detetado por forma, confirmado pelo Tiago).
- **Par** (`T0001`): peça A, peça B, d₁, margem, score de imagem, células candidatas conjuntas (l, c) com score (a célula tem de bater com A em (l, c) e com B em (48 − l, 65 − c)).
- **Secção** (`G0001`): scan(s) da frente, células locais {casa_local, contorno, imagem}, lados livres, **ancoragem** {ancorada: bool, (l, c) da origem local, rotação em múltiplos de 90°}. Só com ancoragem é que as células ganham (l, c) e as suas peças passam a `colocada`.
- **Mapa do tabuleiro** (`board.json`): 47 × 64; cada célula ∈ {`vazia`, `ocupada_legado` (por foto, sem `peça_id`), `colocada` (`peça_id`)}, com `fonte` ∈ {log, foto} e `foto_id`. Derivados em memória, não persistidos: células vazias, buracos (≥ 2 vizinhos colocados), **gémeas pendentes** (colocada cuja célula gémea está vazia), lados livres das secções.
- **Foto** (`F0001`): ficheiro, sha256, data, homografia, resíduo, mapa 47 × 64 de 1/0/−1 (cheia / vazia / incerta); gerada pelo M14.
- **Histórico** (`log.jsonl`, só acrescentar): `{t, ação, peça, célula, origem_da_sugestão ∈ {gémeo, buraco, caixa, encaixe, manual}, rank, score}` com ação ∈ {`placed`, `unplaced`, `twin_confirmed`, `twin_rejected`, `hole_confirmed`, `hole_rejected`, `pair_registered`, `pair_rejected`, `fetch_listed`, `section_registered`, `section_anchored`, `piece_discarded`, `photo_registered`, `cell_occupied_by_photo`, `cell_cleared_by_photo`, `position_known`, `position_placeable`}. `board.json` = replay(log); é a verdade de terreno das métricas (aceitação por origem e por rank).
- **Índice de consulta**: em memória, reconstruído ao abrir a partir das peças `solta` (N ≤ 3008; filtro por classe e por cordas é O(N) trivial). Não persistido além das peças.

**Formato em disco**: pasta `projeto/` com JSON legível (`project.json`, `scans/S0001.json`, `board.json`, `log.jsonl`) + `pieces/S0001.npz` para arrays (contornos, vetores de forma, máscaras). Sem base de dados: uma peça a cada poucos segundos, 3008 no total. Ids atribuídos uma vez, nunca reutilizados.

**Invariantes**: a regra de simetria nunca está escrita no código fora do perfil; **célula gémea = perfil.simetria(l, c)** (para este puzzle, (48 − l, 65 − c)); uma célula tem ≤ 1 peça; uma `colocada` tem exatamente uma célula; a gémea de uma `colocada` ou está em (48 − l, 65 − c) ou é uma consulta pendente; `board.json` == replay(`log.jsonl`) (teste de round-trip do M12).

**Consultas por scan novo** (ordem do §0; plano detalhado em `docs/plano-m10-m12.md`): (0) reconciliar o mapa com a última foto do tabuleiro (M14: ocupadas sem log → `ocupada_legado`; `colocada` vazia na foto → aviso); (1) gémea já colocada → `find_twin` sobre as soltas novas (posição exata); (2) pares entre soltas (`find_twin` solta↔solta) + localização conjunta pela imagem; (3) buracos e fronteira (molde → ranking); (4) caixa, só peças com textura; (5) o resto fica na memória. Cada confirmação **reavalia a memória** (reexecuta (1)–(3) só nas células e peças afetadas) e **regenera a lista "ir buscar"** (lote N, peça X).

---

## 11. Generalização (longevidade)

**Princípio:** nada específico deste puzzle no código. Os factos hoje fixos (64 × 47; gémea (48 − l, 65 − c); célula 18,5 × 17,9 mm; fundo verde; 300 dpi; `images/puzzles/1186441_1.jpg`) passam para um **perfil do puzzle**, `puzzle.json`:
- id/nome; `schema_version`;
- grelha (colunas, linhas); tamanho físico e célula nominal em mm;
- imagem de referência + bbox da arte/homografia (M2);
- **regra de simetria** ∈ {`none`, `rot180`, `translate(N colunas)`, …}, expressa como mapa célula → célula parametrizado;
- fundo canónico (Lab) e dpi.

**Pasta de estado por puzzle:** `projects/<id>/` com `puzzle.json`, `project.json`, `scans/`, `board.json`, `log.jsonl`.

**Calibração de um puzzle novo a partir das 4 bordas digitalizadas:**
1. Contar as peças de borda por lado e medir o passo a partir dos lados retos → grelha e célula.
2. Testar as simetrias candidatas (rotação de 180°, translação de N colunas com N = colunas/2 e colunas/4, nenhuma) com o **E-sym como rotina**: emparelhar as peças de borda por forma sob cada mapa candidato; aceitar se o RMS mediano do gémeo ≈ ruído de re-scan (≤ 0,5 mm) e top-1 ≥ 95 %.
3. Modo gémeo só se confirmado; sem simetria, o fluxo é buraco + imagem + encaixe (§0 sem o passo 2.1).

**Hipótese [NT]:** a matriz é partilhada pela coleção Clementoni 3000 (pergunta 8.2.5); sem teste.

**Fora de âmbito:** corte aleatório / sem grelha.

**Onde o código muda:** `twin.py` recebe o mapa de simetria do perfil; `state.py` cria a pasta por puzzle; `shape.py` lê célula e dpi do perfil; o `matching` lê a grelha do perfil em vez de `num_pieces`; `tools/diagnostico/` pode ficar fixo (são diagnósticos deste puzzle).

**Marco:** M13 (§7): o esquema e a pasta entram com o M12; a rotina de calibração fecha depois do M10 (aceitação: devolve 64 × 47 e rot180 sem ajuda neste puzzle).
