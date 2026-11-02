# Render do tabuleiro: registo fino, franja verde, composição (2026-11-01)

Objetivo (prioridade 1 do Tiago): o render do tabuleiro parecer o puzzle físico a 100 % (1 px do scan = 1 px do ecrã, 300 dpi), sem folgas entre peças colocadas e sem franja verde, numa zona de relva e numa de céu.
Código: `src/render.py` (`python -m src.render`); reprodução: `python tools/diagnostico/render/run_render.py` (≈ 2 min; números em `render_resultados.json`, figuras pequenas aqui, zonas a 300 dpi em `$PPF_SCRATCH/render/`); testes: `tests/test_render.py` (10, sintéticos).
Etiquetas: **[V]** verificado (com evidência), **[NT]** não testado, **[F]** testado e falha.

## Resumo

| | antes (`make_mock`: média do contorno no centro da célula, rotação 0/90/180/270 da secção, recorte cru) | depois (cantos + limpeza + prioridade por profundidade + sangria; banda 1,2 mm nas peças claras) |
|---|---|---|
| junta, mediana \|gap\| (todas, 849) | 0,44 mm | **0,19 mm** |
| junta, p95 \|gap\| | 1,22 mm | **0,59 mm** |
| relva, píxeis de folga / verdes (células interiores) | 6,5 ‰ / 96 ‰ | **0 ‰ / 52 ‰** (≈ 50 ‰ é relva desenhada abaixo do limiar, por calibração) |
| céu, píxeis de folga / verdes | 15,3 ‰ / 58 ‰ | **3,2 ‰ / 0 ‰** |

Alvo do pedido: mediana \|gap\| ≤ 0,3 mm e p95 ≤ 0,8 mm → **cumprido só com os cantos** [V]. Sem franja verde visível nas duas zonas a 100 % [V]. Custo da banda de 1,2 mm no céu: folga 0,8 → 3,2 ‰ (§2.5).

## 1. Registo

**Método.** Os 4 cantos detetados (`Shape`, mm do scan) são emparelhados com os 4 cantos da célula alargada pelo desvio da silhueta (`offset_mm` = 0,48) por Kabsch 2D rígido. A atribuição cíclica tem de pôr os lados F nas direções de borda (`flat_directions`) e é a mais próxima da pose inicial (θ do log; nas secções do legado, rotação da secção + ângulo do corpo + `anchor.rot`). O Kabsch alinha os centróides, por isso a solução dos cantos põe sempre o centro do corpo no centro da célula (dx = dy = 0). O ganho face ao `make_mock` vem do pivô (média dos 4 cantos e não do contorno, que as patilhas puxam) e da rotação fina.

**Resultados [V]** (542 colocadas, todas com 4 cantos):

- Resíduo dos cantos contra a célula nominal (+0,48 mm): mediana 0,82, p95 1,35 mm; **154/542 > 1,0 mm**. Contra o retângulo livre (largura/altura livres, só consistência dos cantos): mediana 0,41, p95 0,75, p99 0,93 mm; 3/542 > 1,0 mm. Figura: `residuo_cantos.png`.
- O resíduo nominal mede sobretudo a dispersão do tamanho das células do cortante: corda horizontal 18,75 mm e vertical 18,12 mm na pose do tabuleiro, contra 18,98 × 18,38 da célula alargada. A pose dos cantos continua boa com resíduo nominal de 1,0–2,0 mm (mediana por peça do \|gap\| 0,23–0,29 mm, contra 0,17–0,19 abaixo de 1,0).
- **Desvio ao pedido:** a porta `CORNER_RESIDUAL_MAX_MM = 1,0` aplica-se ao resíduo contra o retângulo livre (`shape_residual_mm`). O resíduo nominal é reportado (`residual_mm`) mas não decide. Com a porta nominal, 28 % das peças cairiam no método só-imagem, que falha (abaixo).
- Rotação dos cantos vs pose inicial: \|Δθ\| mediana 0,02°, p99 0,24°, máx 0,28°. A atribuição F foi válida nas 542.
- Métodos: `corners` 539, `image` 1, `none` 2 (sem 4 cantos fiáveis e imagem não confiante: fica a pose dos cantos).

### 1.1 Afinação pela imagem: [F] nesta arte

A afinação pela imagem (Lab + gradiente contra a arte) **não funciona com a arte do projeto e não contribui para nenhum resultado**. Razões medidas:

1. **Resolução da arte.** A arte tem 1600 px de largura: 25 × 23,7 px por célula, ou seja 0,75 mm/px. O que se quer corrigir (≤ 0,5 mm) é menos de 1 px da arte.
2. **Não há sinal de alinhamento** [V]. Com uma procura de ±0,5 célula (RMS ΔE Lab + 5 × (1 − NCC da magnitude do gradiente)), o mínimo cai no bordo da janela em 540/542 peças, com deslocamento mediano de 8,9 mm. Só com o NCC do gradiente, nas 99 peças de relva GT e das páginas p05–p06: 99/99 no bordo, NCC mediano 0,30. Na célula certa, a relva GT dá ΔE 18–30 e NCC 0,16: a impressão física e a arte digital não coincidem ao pormenor, e o céu nem sequer tem textura.
3. **A rotação não é observável, nem em arte sintética.** 1° desloca o bordo do corpo 0,16 mm ≈ 0,2 px da arte, e a curva de score em ±5° é ruído.

O código está verificado em arte sintética: recupera uma translação de 1,2/−0,8 mm com erro < 0,2 mm (`test_image_refine_synthetic_art`) [V]. O falhanço é da arte, não do código.

Consequência no programa: com cantos, a imagem só afina a translação e só é aceite com deslocamento ≤ 0,5 mm, mínimo fora do bordo e score mais baixo. **0 aceites:** «depois cantos+imagem» = «depois cantos» em todas as métricas. Sem cantos fica a procura com ±5°, aceite só com NCC ≥ 0,5 (`IMG_NCC_MIN`). P0147, a única colocada sem θ no log e sem secção, recebeu a rotação pela imagem entre 4 atribuições válidas (−90°): **[NT]**, a confirmar (por exemplo pela pose da gémea).

### 1.2 Juntas

`seam_gap_mm`: mediana da distância assinada entre o lado de A virado para B e o contorno de B, e vice-versa; somam-se 2 × 0,48 para estimar a linha de corte; > 0 é folga. [V]

| zona | n | antes mediana \|gap\| / p95 | cantos mediana \|gap\| / p95 | mediana assinada antes → depois |
|---|---|---|---|---|
| todas | 849 | 0,44 / 1,22 | 0,19 / 0,59 | +0,12 → +0,01 |
| céu (filas 1–7) | 349 | 0,42 / 1,19 | 0,18 / 0,55 | +0,07 → −0,05 |
| relva (filas 41–47) | 455 | 0,46 / 1,24 | 0,19 / 0,59 | +0,15 → +0,06 |
| bordas | 295 | 0,46 / 1,35 | 0,22 / 0,60 | +0,25 → 0,00 |

Figura: `junta_antes_depois.png`. A mediana assinada ≈ 0 confirma a calibração isotrópica de +0,48 mm do E-real com outro método. \|gap\| > 0,8 mm em 2,0 % das juntas, abaixo do limiar de 10 % do passo de relaxação, por isso a relaxação não correu. Está implementada (`relax`) mas **[NT]** em dados reais.

## 2. Franja verde

**2.1 Calibração [V].** Distância ao fundo `sqrt(0,5 dL² + da² + db²)` (CIE) a `background_lab`. Nas 53 peças de relva GT (BE/BD), o interior (> 1,5 mm do bordo) tem p1 24,3, **p5 29,5** e mediana 50,7, e o anel exterior (≤ 1,5 px) tem mediana 25,0. Daí `BG_DIST_MAX = 29.5`. Limiar por peça: `max(29,5; 0,8 × p5 do interior da própria peça)`. A relva fica no limiar global (mediana 29,5, máximo 37–43), o céu sobe (mediana 66,6).

**2.2 Regras.**

- Só remove componentes ligadas ao bordo, dentro da banda.
- Banda de **0,7 mm**, exceto nas **peças claras**, que têm **1,2 mm** (§2.5).
- **Peça clara** (`is_light`): p5 da distância ao fundo no seu interior > `LIGHT_PIECE_P5_MIN = 44,25` (= 1,5 × `BG_DIST_MAX`). Pelo menos 95 % da peça está longe do verde do papel, por isso não há verde desenhado para comer. «Clara» quer dizer longe do verde do papel, não necessariamente com L\* alto.
- Nas peças claras, os píxeis da banda que ficam são separados por matting: cor sem a componente de papel e alfa × (1 − fração de papel), com a mesma regra de ligação ao exterior.

**2.3 Números [V]** (542 peças; 259 claras; das de relva GT/p05–p11, só 4 são claras: P0049, P0431, P0500, P0582):

- removidos além da banda da peça: **0**;
- fração removida: mediana 8,3 %, p95 17,2 %;
- ΔE removidos↔interior: mediana 45,3; removidos↔fundo: mediana 28.

Por grupo:

| grupo | banda | removido da banda | limiar mediano |
|---|---|---|---|
| relva GT | 0,7 mm (exceto 1 peça clara) | 36,2 % | 29,5 |
| relva p05–p11 | 0,7 mm (exceto 3 peças claras) | 35,2 % | 29,5 |
| céu p14–p15 | 1,2 mm | 47,1 % (≈ 0,57 mm), mais matting nos restantes | 66,6 |

**Figuras vistas.**

- `verde_gt_BE_BD.jpg` e `verde_paginas_p05_p11.jpg` (as 4 peças mais verdes de cada conjunto): o magenta é um aro fino exterior, mais largo nos lados esquerdo/inferior do scan (sombra). O verde desenhado no interior fica intacto e o contorno não mostra mordidelas, incluindo em P0564 (47,14), a mais verde.
- `verde_relva_clara_banda12.jpg` (as 4 peças de relva classificadas claras, peças escuras cinzento-esverdeadas): mesmo com a banda de 1,2 mm, só sai o aro exterior; as pontas amarelas e a relva desenhada ficam.
- `verde_detalhe.jpg` (4×): o removido é o verde vivo exterior.
- `verde_ceu_p14_p15.jpg`: aro uniforme, o azul não é comido.

**2.4 Sombra (2.ª passagem) [V], desligada.** Removidos por lado do scan (a sombra projeta-se para S e W):

| grupo | iluminados/sombra |
|---|---|
| relva GT | 0,24 |
| céu | 0,14 |
| páginas p05–p11 | **0,85** |

Nas páginas remove quase tanto nos lados iluminados como nos de sombra, ou seja, come relva escura. Por isso `SHADOW_DEFAULT = False`.

### 2.5 Decisão desta ronda: banda de 1,2 mm nas peças claras (desvio à regra «≈ 0,5–0,7 mm»)

A regra do Tiago limitava a banda a cerca de 0,5–0,7 mm. Nesta ronda o coordenador decidiu, à vista das figuras, passar a 1,2 mm **só nas peças claras**, mantendo 0,7 mm em todas as outras.

Evidência:

1. Com 0,7 mm, nas peças de céu examinadas ((3,13), (3,14), (3,15)), **todos** os píxeis esverdeados que restavam estavam a 0,74–1,17 mm do bordo da silhueta (0 % dentro da banda). Em 507/542 peças há píxeis abaixo do limiar ligados ao removido entre 0,7 e 1,2 mm. O desfocado verde do scan passa dos 0,7 mm em alguns lados, e a 100 % via-se uma linha verde de 1–2 px em cerca de metade das juntas do céu.
2. `ceu_banda_07_vs_12.jpg` (esquerda 0,7 mm em todas, direita o padrão novo): à direita não há verde e as juntas parecem cortes.
3. Métrica de píxeis no céu (57 células interiores):

   | banda | folga | verde |
   |---|---|---|
   | 0,7 mm em todas | 0,78 ‰ | 0,67 ‰ |
   | 1,2 mm nas claras (padrão) | 3,18 ‰ | 0 ‰ |

   **Custo:** a folga sobe de 0,8 para 3,2 ‰, porque a sangria de 0,3 mm já não tapa tudo. Fica uma linha fina cinzento-azulada em algumas juntas, em vez de verde.
4. A relva não muda: as peças de relva escura não são claras (limiar 29,5). A zona de relva dá folga 0 ‰ e verde 51,5 ‰ tanto com 0,7 mm em todas como com o padrão novo. As 4 peças de relva classificadas claras foram vistas (figura acima).

Como anular: `python -m src.render --clean --force --light-band 0` (0,7 mm em todas) ou `clean_crop(..., light_band_mm=None)`.

**2.6 Limites [V].**

1. Na relva, o aro que fica depois da limpeza tem a cor da relva: Lab mediano (50, −20, 25) contra interior (40, −14, 25). Nenhum peso de luminância nem teste de tom o separa (tirar 17 % do aro custa 3 % do interior). É o limite já documentado no E-fundo. Na composição resolve-se com a prioridade por profundidade (§3).
2. Defeito de segmentação: 1 peça, P0778 (4,10), tem um encaixe preenchido com papel verde (12,7 mm², a > 1,2 mm do bordo). Fica intocado por desenho e vê-se em `tabuleiro_ppc60.jpg` como um ponto verde. É um item do M3.

## 3. Composição

Camadas: arte (bbox, 0,34 sobre cinzento), peças, legado tracejado, borda vazia a vermelho, grelha. As peças usam três mecanismos:

- **Prioridade por profundidade:** onde duas silhuetas se sobrepõem, cada píxel mostra a peça em que está mais fundo, e a junta cai na linha média da sobreposição, que é a linha de corte quando as duas silhuetas estão 0,48 mm para fora.
- **Sangria de 0,3 mm:** cada peça é desenhada primeiro por baixo de todas, com a cor do píxel mais próximo mais fundo do que a banda, e só aparece em folgas finas.
- **Ordem por fila**, como pedido.

Métrica de píxeis nas células com as 8 vizinhas colocadas, renderizadas sobre magenta [V]:

| variante | relva folga / verde ‰ (10 células) | céu folga / verde ‰ (57 células) |
|---|---|---|
| antes (`make_mock`) | 6,5 / 96,0 | 15,3 / 58,3 |
| cantos + limpeza | 3,3 / 51,3 | 38,6 / 0 |
| + prioridade por profundidade | 3,3 / 51,0 | 38,6 / 0 |
| + sangria (final) | **0,0 / 51,5** | **3,2 / 0** |

«Verde» = distância < 29,5, por isso conta ≈ 50 ‰ de relva desenhada. No céu, a limpeza aumenta a folga, como esperado (tira até 1,2 mm de silhueta), e a sangria fecha a maior parte.

**O que vi a 100 %** (`zona_grass_100pc_antes_depois_arte.jpg`, `zona_sky_100pc_antes_depois_arte.jpg`; painéis: antes | cantos + limpeza | final | arte):

- **Antes:** aros verdes de 0,5–1 mm em todas as juntas e buracos escuros em vários encaixes.
- **Relva final:** as juntas parecem cortes escuros finos. Resta verde escuro só na fronteira da zona, onde a vizinha não está colocada (topo da zona, linha 41 quase vazia).
- **Céu final:** sem verde e sem buracos. Juntas finas cinzento-azuladas com um leve realce claro; num encaixe, no topo à esquerda, há uma linha dupla fina.

`tabuleiro_ppc60.jpg`: céu em cima e relva em baixo, no sítio. Legado tracejado, (1,29) com contorno vermelho, o ponto verde de P0778.

## 4. Reconstrução dos ficheiros pesados (outro PC)

`rebuild_assets` volta a segmentar cada scan do log com a mesma chamada que `ingest_scan`. As páginas do legado também entram por `ingest_scan` (`legacy.ingest_page` passa-lhe a mesma segmentação), por isso a ordem e o `index_in_scan` são os mesmos. O sha256 e a bbox de cada peça são verificados e o processo aborta sem escrever se divergirem. As folhas numeradas `overlays/S####.jpg` em falta são reescritas com `src.ingest.write_overlay`.

Teste numa cópia de `projects/alpes` sem `pieces/` nem `crops/` de S0003 (GT BE, 25 peças), S0005 (lote 1 céu, 35) e S0013 (montado p05, 51) [V]:

- 6,6 / 6,3 / 8,0 s por scan;
- chaves e valores do npz iguais aos originais;
- 111/111 recortes idênticos byte a byte;
- `log.jsonl` intacto;
- depois `clean_all` 11 s + `register_all` 21 s.

Overlays: apagados os de S0003 e S0013 (e o npz de S0013), foram os dois regenerados [V]. A folha S0003 vista tem as 25 peças numeradas, com os contornos e as cores de `objeto_duplo` e borda.

Extrapolação para os 26 scans: ≈ 3 min + 32 s [NT]. O caminho de abortar por bbox divergente não foi exercitado [NT].

## 5. Não verificado

- OpenCV 5.0 [NT] (só 4.11).
- Relaxação em dados reais [NT].
- Pose de P0147 [NT].
- Banda de 1,2 mm fora das zonas vistas: só os 4 casos de relva clara e o céu das figuras foram vistos [NT].
- Render de peças `posicao_conhecida` (não desenhadas) [NT].

## 6. Orla verde nas miniaturas (2026-11-01)

(Pedido como «§3»; o §3 já é a composição, por isso fica aqui.)

**Causa [V].** O tabuleiro (`compose_board`) reamostra com alfa pré-multiplicado e não mostra orla; as miniaturas não: `query._piece_image` (cartões «vai buscar» via `/api/pieces/{pid}.png`, folhas `fetch_<lote>.jpg`, incluindo a gémea) rodava RGB e alfa em separado, e `_clean` deixava o verde do papel por baixo dos píxeis com alfa 0, que a interpolação puxava para a orla semitransparente; `Gui.section_png` (Mesa) usava o recorte cru (`crop_rgba`, sem limpeza nenhuma) com `cv2.resize` sem pré-multiplicar.

**Correção.** Um só caminho: `render.piece_rgba_for_display` (recorte limpo de `render/clean/` ou limpo na hora, cor sob alfa 0 = cor da peça mais próxima, rotação/escala com alfa pré-multiplicado via `warp_rgba` / `resize_rgba`); `query._piece_image` e `Gui.section_png` passam por ele (Mesa com LRU por grupo, tamanho e versão do log). `_clean` também neutraliza a cor dos píxeis removidos (os `render/clean/*.png` novos já não guardam verde sob alfa 0).

**Medido** (cópia de `projects/alpes` no scratch; cartão do GUI 220 px, 1,8 células, rodado 37°; script em scratch, não versionado). «ΔE<20» = píxeis visíveis a ΔE < 20 do `background_lab`; «esverdeado» = a\* < −30 e distância ao fundo < 40 (apanha também o verde escurecido pela sombra; nas peças de relva conta também a própria relva, por isso só é informativo no céu e na Mesa):

| peça / grupo | ΔE<20 antes → depois | esverdeado antes → depois | interior > 1,5 mm inalterado |
|---|---|---|---|
| P0100 (céu, solta) | 0 → 0 | 50 → 0 | 100 % |
| P0105 (céu, solta) | 0 → 0 | 69 → 0 | 100 % |
| P0131 (céu, solta) | 0 → 0 | 81 → 3 | 100 % |
| P0047 (relva, S0003) | 0 → 0 | 1002 → 955 | 100 % (14/14 px verdes do interior mantidos) |
| P0051 (relva, S0003) | 0 → 0 | 956 → 912 | 100 % |
| P0055 (relva, S0003) | 0 → 0 | 872 → 894 | 100 % |
| G0041 Mesa (1 peça, 360 px) | 186 → 0 | 5576 → 1962 | — |
| G0083 Mesa (8 peças, 360 px) | 0 → 0 | 1328 → 6 | — |

Figura: `orla_antes_depois.jpg` (cartões sobre branco, antes | depois | zoom 4× antes | depois; em baixo as miniaturas da Mesa sobre cinzento). **Visto:** na Mesa a orla verde clara desaparece (G0083: o rebordo verde do zoom 4× some por completo; G0041: a orla larga do lado da sombra fica muito mais fina). Nos cartões de céu a diferença é ténue (a orla era de 1 px misturado). **Resíduo (resolvido em §6.1 para a visualização):** nas peças de relva e no lado da sombra de G0041 continua visível um rebordo verde-escuro de ≈ 0,2–0,4 mm, antes e depois: em P0443 (G0041) os píxeis da faixa 0–0,2 mm têm L\* ≈ 55, a\* mediano −29 e distância ao fundo 28–34, acima do limiar `BG_DIST_MAX` = 29,5, ou seja papel escurecido pela sombra projetada (S2), que a limpeza não remove em lado nenhum (no tabuleiro fica tapado pelas vizinhas). Não é o defeito de reamostragem corrigido aqui; tirá-lo exige mexer no limiar ou no passe de sombra (medido OFF no §2 porque come relva escura), decisão a medir à parte.

### 6.1 Papel escurecido pela sombra: regra só de visualização, LIGADA (2026-11-01)

**Regra** (`render.shadow_paper_mask`, aplicada só em `piece_rgba_for_display`: cartões, folhas «vai buscar», Mesa; nunca nas silhuetas do índice, no `compose_board` nem nos `render/clean/` do `clean_all` / registo): na faixa exterior de `DISPLAY_SHADOW_BAND_MM` = 0,4 mm, descartar os píxeis com a\* < `DISPLAY_SHADOW_A_MAX` = −30, `bg_distance` ao `background_lab` < `DISPLAY_SHADOW_DIST_MAX` = 40 e L\* < `DISPLAY_SHADOW_L_MAX` = 62, em componentes ligadas ao bordo. Interruptor: `DISPLAY_SHADOW = True`. Teste: `test_display_drops_shadow_darkened_paper` (faixa de 0,3 mm verde-escura em dois lados, interior com textura de relva e verde tipo papel no fundo; falha com a regra desligada, passa ligada; verifica também que `clean_crop` não muda).

**Mudança de porta.** A primeira medição usava «nenhuma peça perde > 1,5 % dos píxeis visíveis». Essa porta nunca podia admitir uma orla de sombra real: 0,4 mm em dois lados valem ≈ 2–4 % da área de uma peça. Porta nova (decisão do coordenador, 2026-11-01), por peça: perda total ≤ 4,5 %, **e** ≥ 65 % do descartado na metade de sombra do scan (esquerda/baixo em relação ao centróide; não se aplica com < 50 px descartados), **e** perda nos lados iluminados ≤ 1,5 %, **e** interior (> 0,4 mm) 100 % igual (alfa e cor).

**Medido** (59 objetos: 53 de S0003/S0004, incluindo 5 `descartada`; 3 de céu; 3 de relva escura p05–p11) [V]:

| conjunto | resíduo «esverdeado» na faixa de 0,7 mm | perda total máx. / mediana | quota na sombra (mín. / mediana) | perda nos lados iluminados máx. | interior igual |
|---|---|---|---|---|---|
| relva GT (53) | 85 527 → 12 831 (−85 %) | 4,12 % / 2,82 % | 0,05 / 0,77 | 1,57 % | 100 % |
| céu (3) | 6 → 0 | 0,01 % / 0,00 % | — (< 50 px) | 0,01 % | 100 % |
| relva escura p05–p11 (P0604, P0609, P0563) | 2 344 → 59 | 2,00 % / 1,92 % | 0,80 / 0,81 | 0,38 % | 100 % |

**Falham a porta 4 de 59 [F]:**
- P0059, P0064, P0065 (`descartada`; quota na sombra 0,52 / 0,55 / 0,05; perda total ≤ 1,6 %). Não são peças: são blocos/tiras de várias peças cortados pela segmentação (vistos), sem cartão nem miniatura de peça.
- **P0087** (colocada): perda nos lados iluminados 1,57 % (porta 1,5 %), quota na sombra 0,58, perda total 3,73 %. Visto a 2×: o descartado do lado iluminado é a orla verde-clara do papel no lado direito da patilha direita, não relva. A porta falha à justa (+0,07 pp).

Regra ligada na mesma (decisão do coordenador). Desliga-se com `DISPLAY_SHADOW = False`.

**Figuras.** `orla_antes_depois.jpg` regenerada (antes = HEAD; depois = pipeline de visualização com a regra). Em P0047, P0051 e P0055 a faixa verde-escura dos lados esquerdo/inferior desaparece no zoom 4×. O «esverdeado» dos cartões desce 1002 → 195, 956 → 125 e 872 → 85; G0041 desce 5576 → 298 e o lado da sombra fica limpo; G0083 desce 1328 → 0. Fica um fio verde-claro (L\* > 62) no lado iluminado de algumas peças de relva, que a regra não visa. `orla_sombra_regra.jpg` (avaliação da regra: atual | descartado a magenta | regra | variante fraca) mantém-se. Não verificado [NT]: céu fora das 3 peças; cartões rodados e reduzidos (a porta foi medida à resolução do scan).
