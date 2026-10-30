# Secção montada: linhas de corte, localização na arte e fotometria

Dados: secção de canto montada (céu e nuvem), digitalizada pela frente e por trás a 300 e a 600 dpi (`images/pieces/{frente,traseira}_{300,600}dpi.jpg`; a traseira é cartão cinzento e está espelhada). Referências: `images/puzzles/1186441_1.jpg` (arte limpa; a arte ocupa as linhas 42–1156, 1600 × 1115 px) e `images/puzzles/PuzzleOriginal.jpeg` (foto da caixa; bbox da arte por `matching/common.detect_artwork`).
Script: `tools/diagnostico/gemeos/seccao.py`. Só cv2/numpy/PIL. Não houve alterações em `src/` nem em `tests/`. Os números completos estão em `seccao_results.json`, e as células com (l, c) em `seccao_celulas.json`. Tempo total ≈ 4,5 min.

Etiquetas: **[V]** verificado (com n e ficheiro), **[NT]** não testado, **[F]** testado e falhou.

## 0. Contagem esperada e referencial

- **Contagem a olho: 44 peças** [V, vi `traseira_300dpi.jpg` e `frente_300dpi.jpg`]. Na orientação da frente são 7 colunas por 7 filas: as colunas 1–5 estão completas, a coluna 6 não tem a 2.ª fila a contar de cima e a coluna 7 só tem as 3 filas de baixo.
- Os **2 lados retos** são detetados automaticamente: o esquerdo e o de baixo na frente, e também na traseira depois de espelhada. Em cada perfil extremo, a reta de suporte toca 47–90% dos pontos; nos outros lados toca 1–4% [V, 4 scans]. O bloco está rodado 0,66° (frente) e 1,4° (traseira) em relação ao vidro.
- A ocupação da grelha calculada pela máscara (≥ 50% do quadrado central de cada casa) dá **44 casas nos 4 scans**, iguais às da contagem a olho [V].
- **Passo medido da grelha** (autocorrelação da resposta Hessiana nas frentes; confirmado pelos centróides de 60 células sem prior):
  - ao longo do lado de baixo do scan, que é a vertical do puzzle: **18,39 mm** (centróides 18,54);
  - ao longo do lado esquerdo, que é a horizontal do puzzle: **18,97 mm** (centróides 18,88);
  - o nominal é 17,9 × 18,5 mm.
  
  A razão (1,03) bate com 64 × 47, mas as células montadas são ≈ 2,5–3% maiores do que o nominal [V, n=4 scans / 60 células]. A causa não foi testada [NT]: folga entre peças montadas, ou nominal subestimado.

## A. Linhas de corte

**Método pedido** (`otsu`):
- máscara do bloco erodida 1 mm;
- resposta de vale em L\* por black-hat (elipse de 7 px a 300 dpi, 14 px a 600) e pela Hessiana (maior valor próprio, isto é, o menor da Hessiana de −L\*, depois de uma gaussiana de σ = 0,25 mm);
- limiar de Otsu dentro do bloco, fecho de 0,3 mm e células = componentes 4-conexas do complemento.

**Duas variantes minhas**, porque o método pedido não fecha células (ver tabela):
- `histerese`, sem prior: núcleo acima do Otsu, candidatos acima de 0,5·Otsu ligados ao núcleo, o fecho também liga as linhas à silhueta, e abertura de 0,4 mm nas células.
- `watershed`, com prior: inundação da resposta a partir de sementes nos centros da grelha (canto e passo medidos). As fronteiras e as linhas da histerese são linha. As células são classificadas pela área: válida se estiver em [0,6; 1,4] × 331 mm²; "2×" se estiver em ]1,4; 2,6]. A célula só conta como **recuperada** se a sua casa tiver exatamente uma célula válida.

| scan | resposta / modo | recuperadas / 44 | 2× | % área do bloco em células válidas |
|---|---|---|---|---|
| frente 300 | black-hat / otsu | 4 | 1 | 6,6 |
| frente 300 | Hessiana / otsu | 4 | 0 | 7,3 |
| frente 300 | **Hessiana / histerese** | **30** | 7 | 62,4 |
| frente 300 | **Hessiana / watershed** | **40** | 0 | 81,1 |
| traseira 300 | black-hat e Hessiana / otsu e histerese | 0 | 0 | 0 |
| traseira 300 | Hessiana / watershed | 34 | 0 | 72,8 |
| frente 600 | Hessiana / otsu | 5 | 0 | 9,4 |
| frente 600 | Hessiana / histerese | 30 | 7 | 62,6 |
| frente 600 | Hessiana / watershed | 39 | 0 | 76,9 |
| traseira 600 | todas, sem prior | 0 | 0 | 0 |
| traseira 600 | Hessiana / watershed | 35 | 0 | 77,8 |

[V, n=44 casas por scan, `seccao_results.json` → `parteA`; figuras `seccao_linhas_{frente,traseira}_{300,600}.png`. Em cada figura: linhas = modos, colunas = resposta, limiar e células coloridas.]

**O que vi nas figuras:**
- **Frente, Hessiana e histerese.** As células coloridas são as peças. As 7 fusões "2×" são todas na coluna da esquerda e na fila de baixo: os cortes horizontais e verticais desvanecem nos últimos ≈ 1–2 mm antes dos lados retos. As outras falhas são na nuvem creme e cinzenta, onde a textura da nuvem faz ruído.
- **Frente, watershed.** As fronteiras seguem os cortes (94% dos píxeis de fronteira estão a ≤ 0,25 mm de uma linha detetada). Os erros ficam na nuvem, onde há fragmentos.
- **Black-hat na frente.** Falha: a textura "linen" do papel dá vales de 7 px por todo o lado (20–75% do bloco fica marcado como linha).
- **Traseira.** A linha escura só existe nos troços retos. O contorno das patilhas aparece em **relevo** (luz/sombra), não como vale escuro, e por isso nenhum detetor de vale o apanha. Sem prior, nenhuma célula fecha (0/44). Com a grelha, o watershed inventa a fronteira nos troços sem linha: o suporte é de 72% a 300 dpi e de 85% a 600.

Comprimento de linha (esqueleto) por casa esperada:
- frente, Hessiana / histerese: 53 mm;
- traseira, Hessiana / histerese: 37 mm, ou seja cerca de 70% da frente [V].

Calibração feita sobre os mesmos dados, por isso só indicativa: na frente a 300 dpi, a histerese com nível baixo de 0,35·Otsu e fecho de 0,6 mm sobe de 30 para 36/44. Na traseira continua em 0/44 [V, varrimento manual, não está no script].

### Frente vs traseira e 300 vs 600 (ruído da extração)

**Registo.** A traseira é espelhada, posta no referencial dos lados retos e afinada por ICP sobre o contorno exterior, com `estimateAffinePartial2D` (LMEDS).
- Resíduo mediano da silhueta: 0,23 mm entre frente e traseira, 0,14 mm entre 300 e 600 dpi.
- **A silhueta da traseira é 0,5% menor do que a da frente** (escala ICP de 0,995 aos dois dpi; cerca de 0,7 mm em 140 mm) [V]. A causa (bisel do corte?) não foi testada [NT].

| comparação | linhas detetadas de b → linhas de a: mediana / p90 (mm) | ≤ 0,5 mm | fração das linhas de a com linha de b a ≤ 0,5 mm | RMS de forma entre células homólogas |
|---|---|---|---|---|
| frente 300 ↔ traseira 300 | **0,25 / 0,49** | 89% | **65%** | watershed: mediana 2,76 mm (n=33), não utilizável (ver abaixo) |
| frente 600 ↔ traseira 600 | 0,24 / 0,49 | 89% | 70% | watershed: 2,08 mm (n=35) |
| frente 300 ↔ frente 600 | 0,00 / 0,085 (≤ 1 px) | 99,5% | 99,5% | **histerese: free 0,12 mm, corner 0,11 mm (n=28, p90 0,81), classe 28/28**; watershed: free 0,65 mm (n=38) |
| traseira 300 ↔ traseira 600 | 0,085 / 0,085 | 94% | 99,5% | watershed: 2,37 mm (n=34) |

[V, `seccao_results.json` → `frente_vs_traseira`; figura `seccao_frente_vs_traseira.png`.]

**Leitura:**
- Onde as duas faces têm linha, as linhas coincidem a 0,25 mm (mediana). Nas sobreposições, as células com linha nas duas faces batem; por exemplo, a casa (2, 3) dá 0,39 mm.
- O RMS de 2–3 mm entre células homólogas **não é ruído de medida**. É o watershed a inventar fronteira nos 30–35% de corte sem linha na traseira, e na nuvem na frente.
- O ruído real da extração é 0,12 mm (frente 300 vs 600, células sem prior). Fica abaixo do ruído de re-scan das peças soltas (0,34 mm, `gemeos_2026-10-30.md`), porque aqui as duas digitalizações têm a mesma pose.

### Cantos e lados (analyse_v2)

| scan / modo | células válidas | 4 cantos | vizinhos coerentes T↔B | lados retos do bloco classificados F |
|---|---|---|---|---|
| frente 300 / histerese | 30 | **30** | **39/39** | 4/4 |
| frente 300 / watershed | 40 | 37 | 59/60 | 13/13 |
| frente 600 / watershed | 39 | 30 | 46/46 | 7/8 |
| traseira 300 / watershed | 36 | 28 | 33/40 | 5/7 |
| traseira 600 / watershed | 39 | 30 | 31/41 | 7/9 |

[V, `seccao_results.json` → `topologia`.] Nas células da frente, a classe topológica é coerente com a das vizinhas: cada patilha tem do outro lado um encaixe. Nas da traseira há 7–10 contradições, o que é consistente com fronteiras inventadas.

### Conclusão A

- **A hipótese "a traseira a 300 dpi chega" é falsa [F].** Na traseira só cerca de 65–70% do comprimento dos cortes aparece como linha escura; as patilhas aparecem em relevo. Sem prior fecham 0/44 células, a 300 e a 600 dpi.
- **A melhor fonte é a frente a 300 dpi com a Hessiana.**
  - Os 600 dpi não acrescentam nada mensurável: as mesmas células (30 = 30), linhas coincidentes a ≤ 1 px e RMS de forma de 0,12 mm entre resoluções [V].
  - O black-hat não serve na frente por causa da textura do papel [F].
- **Critério dos ≥ 90% na frente a 300 dpi:**
  - sem prior: 30/44 = 68% (36/44 = 82% com parâmetros afinados nos próprios dados), **não cumpre**;
  - com o prior da grelha (canto e passo, que numa secção montada se obtêm dos lados retos): **40/44 = 91%**, cumpre à justa, e os 4 que faltam estão na nuvem.
  
  A extração em secções montadas **deixa de ser risco onde há céu ou textura uniforme e o canto é conhecido**. Continua a ser risco na nuvem e sem prior. Os dois modos de falha concretos são: (1) os cortes desvanecem junto aos lados retos; (2) a textura da imagem compete com o vale do corte.
- **Não testado [NT]:**
  - um detetor de relevo para a traseira (par luz/sombra, por gradiente orientado);
  - a fusão frente + traseira, porque as linhas das duas faces coincidem a 0,25 mm e podem completar-se.

## B. Localização da secção na arte

**Método:**
- Os 2 lados retos fixam o canto do bloco. As 4 hipóteses de canto do puzzle (BL, TL, TR, BR) fixam a rotação; juntei 4 hipóteses espelhadas como controlo.
- O scan da frente a 300 dpi foi reduzido de modo que o passo medido coincida com o passo da arte (25,0 × 23,7 px por célula).
- Comparação: ΔE médio mascarado e NCC em L\*, com jitter de ±4 px e escala de 0,97/1,00/1,03.

| referência | melhor | NCC (L\*) | 2.ª hipótese de canto | gap NCC | ΔE melhor / 2.º | controlo espelhado mais alto |
|---|---|---|---|---|---|---|
| arte limpa | **TL (canto superior esquerdo)** | 0,876 | BR 0,408 | **0,468** | 8,6 / 59,2 | TR espelhado 0,635 |
| foto da caixa (bbox) | **TL** | 0,819 | BR 0,398 | **0,421** | 9,9 / 50,9 | TR espelhado 0,572 |

[V, n=8 hipóteses × 243 posições por referência; `seccao_localizacao.png`. Vi a figura: na colocação TL, a nuvem branca e a nuvem cinzenta do scan caem por cima das da arte, nas duas referências.]

A rotação implicada (scan rodado 90° no sentido horário) põe o lado esquerdo do scan no topo do puzzle e o lado de baixo do scan à esquerda do puzzle. A secção ocupa as **linhas 1–7 e as colunas 1–7** do puzzle: as 49 casas menos (6, 6) e (7, 4)–(7, 7), ou seja 44 casas.

**SIFT + RANSAC: falha no céu [F].**
- À escala da arte (×1, ×2) há 1 correspondência boa e 0 inliers.
- A ×4 há 5 inliers, com o centro projetado em (496, 674), longe do canto.
- `expB.homography(scan, arte)`: 5 inliers e homografia degenerada.

**(l, c) por célula.** Ficaram em `seccao_celulas.json`:
- conteúdo: contorno em px do ficheiro original e (l, c) com base 1, por scan;
- modo usado: Hessiana / watershed, em todos os scans;
- células por scan: 40 na frente 300, 36 na traseira 300, 39 na frente 600, 39 na traseira 600;
- duplicados de (l, c): 1 na traseira 300 e 2 na traseira 600.

**Para GT, usar as células da frente a 300 dpi.** As da traseira têm fronteiras inventadas.

## C. Fotometria

L\*, a\*, b\* medianos (Lab CIE em vírgula flutuante):

| zona | scan | arte limpa | foto da caixa | scan − arte (L\*) |
|---|---|---|---|---|
| céu da secção (54% do bloco, sem linhas nem nuvem; a mesma zona registada, 9551 px de arte) | **52,3 / −4,6 / −33,5** | 47,5 / −5,1 / −37,9 | 49,2 / 2,5 / −34,0 | +4,8 |
| A1: borda de cima c5–24, céu (n=20 peças, casas (1, c) da arte) | 55,8 / −7,5 / −32,5 | 50,9 / −8,1 / −38,4 | 58,4 / 0,3 / −30,2 | +5,0 (IQR 4,8–5,2) |
| B2: borda de baixo c41–60, prado (n=20 peças, casas (47, c)) | 45,5 / −11,9 / 27,4 | 43,2 / −11,5 / 28,1 | 41,1 / −8,2 / 17,9 | +3,0 (IQR −3,6–6,5) |
| curva píxel a píxel no bloco registado (inclui nuvem creme e cinzenta), arte → scan | 39→44, 48→52, 57→63, 67→74, 78→84, 87→93 | | | **+4 a +6 em toda a gama 39–87** |
| ajuste por casa (n=80: 40 células + A1 + B2) | L\*scan ≈ 1,06·L\*arte + 1,3 (r = 0,76) | | | mediana +4,8 |
| arte inteira | — | 49,0 / −1,3 / 25,7 | 49,8 / 0,3 / 18,3 | |
| **peças de julho** (`scan_verde`, n=61) | **86,4 / −4,8 / 28,6** (p10 59,6, p90 94,5) | | | |

[V, `seccao_results.json` → `parteC`; `seccao_fotometria.png` (píxeis de céu usados e dispersão).]

- Na foto da caixa, a curva tem dois valores fora (arte 68–72 → scan 49–52). É desalinhamento na borda da nuvem, porque a bbox da caixa não corrige a perspetiva.
- A1 e B2 vêm de `$PPF_SCRATCH/seg/gemeos_{A1,B2}.npz` (`segment_pieces`, gerados pelo `esym.py`). A minha segmentação simples só encontrava 12/20 peças de prado sobre o verde.

**Fundo verde** (mediana do papel fora das peças dilatadas 6 mm):

| ficheiro | L\* / a\* / b\* |
|---|---|
| `digitalização_fundo_verde.jpg` (julho) | 77,8 / −50,5 / 47,8 |
| `coluna5-24_300dpi_folhaA.jpg` (A1, hoje) | 77,9 / −52,3 / 44,6 |
| `coluna5-24_folhaB_300dpi_rot180.jpg` (B2, hoje; peças escuras) | 78,0 / −51,2 / 48,2 |
| `frente_300dpi.jpg` (hoje) | 78,4 / −53,0 / 45,1 |
| `traseira_300dpi.jpg` (hoje) | 78,6 / −52,5 / 49,0 |

O papel tem o mesmo Lab nos cinco (ΔL\* ≤ 0,8, Δa\* ≤ 2,5, Δb\* ≤ 4,4), seja qual for o conteúdo da folha (céu, prado escuro, cartão) [V, n=5]. A nota do utilizador confirma-se: L\* do céu = 52 e não há correção automática dependente do conteúdo.

**Conclusão C: (i), com um desvio pequeno e uniforme.**
- O scanner é fiel à arte: L\* do scan = L\* da arte + 4 a 6 em toda a gama medida (39–87), com o mesmo desvio no céu, na nuvem e no prado. Os desvios em a\*/b\* são pequenos (céu Δb\* +4).
- A referência é um pouco mais escura, mas por ≈ 5 unidades e de forma uniforme: corrige-se com um deslocamento e não explica o fosso de 86 vs 50.
- As 61 peças de julho (L\* 86, b\* +29: amarelo-claro) são, portanto, **peças claras de verdade**, provavelmente nuvens do pôr do sol.
- Isto **contradiz a explicação do §3.6 de `docs/estado-e-plano.md`** ("o L\* 86 é desfasamento de captura") [F para essa explicação].
- Fica por explicar a composição. Só 8–14% dos blocos da arte têm L\* ≥ 80 (§3.6), contra 43/61 peças. Ou o saco não está misturado ao acaso (as peças podem ir para os sacos por zonas), ou a amostra não foi aleatória [NT].
- Para o M9 basta um deslocamento de ≈ −5 em L\*, mais um pequeno ajuste em b\*.
- Para o desempate dos gémeos pela zona da imagem, o céu (L\* 52–56, b\* −33) e o prado (L\* 45, b\* +27) separam-se trivialmente.

## Problemas encontrados

1. **`PuzzleOriginal.jpeg` tem EXIF orientation = 3, mas os píxeis já estão direitos.**
   - `cv2.imread`/`imdecode` aplicam o EXIF e devolvem a foto **de pernas para o ar**. O PIL, usado pelo motor e por `matching/common.py`, não aplica o EXIF e dá a imagem certa.
   - Na 1.ª execução isto pôs a secção no canto BR da caixa. O script lê agora tudo com `IMREAD_IGNORE_ORIENTATION`.
   - Os scans não têm a etiqueta [V].
   - **Atenção a qualquer código que leia esta imagem com cv2.**
2. **A máscara de Otsu de patamar de `segment_pieces`** (`_otsu_plateau_threshold` sobre `_weighted_distance` normalizada) **cortava metade da peça creme da nuvem** e, com ΔE puro, anexava a sombra da aresta do cartão (≈ 0,4 mm). Usei ΔE com L\* a peso 0,25 e limiar de max(20, 0,5·Otsu) [V, vi `mask` nas duas versões]. O mesmo pode acontecer em `src/` com peças creme sobre verde [NT].
3. O pipeline pedido (Otsu + fecho de 0,3 mm) não fecha células em nenhum scan (≤ 5/44). As variantes histerese e watershed são minhas e estão marcadas como tal.
4. No watershed, a fronteira cai num dos flancos do vale e uma célula anexava uma tira de 1–3 px ao longo da linha do vizinho (RMS falso de ~3 mm entre 300 e 600 dpi). Corrigido somando a linha da histerese e abrindo as células a 0,4 mm.
5. Ficou de fora:
   - B e C correm só na frente a 300 dpi;
   - a caixa é alinhada por bbox, sem homografia, e daí os dois valores fora na curva.

## Reprodução

```powershell
$env:PPF_SCRATCH = "C:\...\scratchpad"     # precisa de seg/scan_verde.npz; usa seg/gemeos_{A1,B2}.npz se existirem
python tools/diagnostico/gemeos/seccao.py   # ≈ 4,5 min
```
