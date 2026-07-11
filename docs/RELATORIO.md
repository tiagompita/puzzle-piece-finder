# Relatório de Estado — Puzzle Piece Finder

_Atualizado: 2026-07-11_

Registo do que já está feito, do que falta, e dos problemas conhecidos ainda por resolver. Complementa o [ROADMAP.md](ROADMAP.md) (visão de features) com o estado técnico atual.

---

## 1. Estado atual — o que funciona

### Segmentação (`src/segmentation.py`)
- **Deteção de foreground** por distância ponderada em Lab ao fundo, com **limiar por HISTERESE + conetividade** (ancorado no Otsu, só cresce) — recupera manchas reflexivas/metálicas que a superfície espelha para a cor do fundo, sem readmitir sombra.
- **Separação de peças encostadas** por **seam-carve**: a costura física escura (gap + sombra entre duas peças) é detetada por black-hat e usada como sinal PRIMÁRIO de corte; os pixels da costura (que são fundo) são removidos e cada corpo conexo é atribuído por **conetividade** à sua peça (não por watershed de cor, que vazava). Fallback geométrico (watershed no distance-transform invertido) só para contacto pixel-a-pixel.
- **Guardas de solidez** (peça real ≈ 0.62–0.81; garbage ≤ 0.55) em 3 camadas — o lixo vazado é marcado `is_cluster` honesto em vez de emitido como peça deformada.
- **Limpeza de máscara**: maior componente, preenchimento de buracos, despeckle, refinamento de fronteira por perfil normal, e **rejeição de franja de cor-de-fundo** (remove slivers de fundo agarrados no contacto).
- **Classificação de bordas/cantos** flat/tab/blank (`src/edges.py`).
- **Cutout RGBA transparente** para visualização/exportação; botão **Save Pieces** (guarda todas as peças de uma vez).
- **Ingestão `.DNG`** diretamente via PIL.

### Motor de matching (`src/matching.py`)
- Motor de cor por **zonas em CIE-Lab** + máscara + varrimento de escala/rotação + **assinatura de textura por gradiente** (Sobel no L) + **prior de borda** + **gap de confiança diferencial**.
- **Resolução de busca adaptativa** (~46 px por peça, derivada de `num_pieces`) — deixou de deitar fora a resolução real da referência.
- Saída: shortlist de candidatos + **confiança honesta** (`alta`/`ambígua`): localiza onde a arte permite, assume ambiguidade onde não permite.

### GUI (`src/gui.py`)
- Segment Photo, Match, Match All, Export JSON, Save Annotated, **Save Pieces**.

### Qualidade
- Suite **pytest** anti-regressão (segmentação sintética, edges, self-recovery de matching).
- Harness de segmentação reprodutível sobre 11 fundos de cor.

---

## 2. O que foi feito nesta ronda

### Matching (fechado)
- Lote de correção B1–B3 (máscara + px/cm ao motor, `num_pieces` obrigatório, remove downscale duplo).
- Resolução de busca adaptativa (baseline honesto subiu de 3/64 → 5/64 na foto de teste IMG_2114).
- Color-twins Stage A (textura + re-rank + prior de borda) e **gap de confiança diferencial** (corrige a compressão do gap; 12/66 → 13/66 "alta").

### Segmentação (fechado nesta ronda)
- Encolhimento do halo de sombra nos rebordos; under-split (bisect geométrico) de peças fundidas.
- Glare/especular: **tentado com inpaint e REVERTIDO** (não se pagava no matching; o inpaint TELEA introduz artefactos próprios).
- Histerese + conetividade no foreground (recupera peças metálicas reflexivas).
- **Experimento dos 11 fundos** (mesmas peças, cores de fundo diferentes) — provou que a perda dominante era **código** (o watershed de cor vazava em peças encostadas da mesma cor), não contraste.
- **Seam-carve split** (costura como sinal de corte) + guardas de solidez → eliminou o garbage deformado.
- **Fronteira de contacto por conetividade** + rejeição de franja de fundo → resolveu as mordidas/grabs e os slivers de fundo (ex. peças #32/#37).

**Resultado medido (harness 11 fundos):** garbage = 0 em todos; nos fundos de melhor contraste (verde/laranja) recupera ~61 peças (o número real de peças aparenta ser ~61, a confirmar).

---

## 3. Por fazer (roadmap de features)

Ver [ROADMAP.md](ROADMAP.md) para o detalhe. Por ordem de valor:
1. **Encaixe entre peças / montar grupos** — a grande feature (usar uma secção montada como referência local de alta resolução; compatibilidade de bordas via `edges.py`).
2. **Escalar a referência** pelas secções montadas (liga-se à feature 1).
3. **Câmara live** (Wi-Fi/USB; Bluetooth para vídeo não é prático).
4. **Correção de perspetiva** (picker de 4 cantos → `getPerspectiveTransform`; dá px/cm calibrado). Prioridade baixa.
5. **Recalibração de confiança** do matching contra um conjunto rotulado à mão.

---

## 4. Problemas conhecidos — ainda por resolver

### Segmentação
- **Pares "mated" (encaixados)**: duas peças com um tab totalmente dentro do blank da outra, arestas flush, mesma cor, sem fio de fundo entre elas. É o **teto da visão clássica** — o contorno conjunto é um retângulo plausível, sem sinal de corte. **Solução: separar fisicamente e re-digitalizar.** (Detetadas como uma peça sobredimensionada; idealmente marcadas `is_cluster`.)
- **Bordas de contacto ligeiramente esfarrapadas** em algumas peças que tocavam vizinhas — resíduo menor.
- **Fundos de baixo contraste** (fundo pálido, OU fundo da mesma paleta da arte — ex. amarelo/bege num puzzle de deserto) perdem peças por física de contraste. Não é bug. **Solução de captura: fundo saturado de cor AUSENTE da arte (verde/magenta), e/ou ESPAÇAR as peças ≥5 mm** (elimina contactos e torna a separação desnecessária).
- **Glare/especular** dentro da máscara em peças brilhantes — removível só com um fill consciente de textura (não com inpaint simples).

### Matching
- **~1/3 das peças "alta" são soft** (creme sobre grandes zonas de areia uniforme): passam os gates mas a posição não está fortemente fixada. É o limite físico da paleta de deserto; melhora com **recalibração de confiança** contra rótulos.
- O 0.12 do gate de gap é herdado da escala de cor; a recalibração deve ser feita com um conjunto rotulado, não a chutar.

### Menor
- `DeprecationWarning` do Pillow (`Image.fromarray(arr, "L")`) em `segmentation.py` — cosmético.

---

## 5. Recomendações de captura (o que dá maior retorno, custo zero)

A captura já provou ser a maior alavanca (fundo branco → fundo colorido deu o maior salto). Para o melhor recorte:
- **Espaçar as peças** ≥ 5 mm — nenhuma peça a tocar outra elimina a classe de erros nº 1 (contactos) e o único caso insolúvel (pares mated).
- **Fundo saturado de uma cor ausente da arte** (para deserto quente: verde ou magenta vivo) — separa por croma, seja qual for o brilho da peça.
- Luz difusa (contra glare em peças brilhantes).
