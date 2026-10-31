# E-sym rigoroso e cortes repetidos (2026-10-30)

Dados: scans de 30-out a 300 dpi (1 px = 0,08467 mm), papel verde, imagem virada para o vidro. A1 = borda de cima c5–24 (4 filas × 5, lado reto para cima); A2 = as mesmas, cada uma rodada 180° na sua casa; B2 = os gémeos (borda de baixo), cada um rodado 180° na casa de B1; B1 só como diagnóstico. Para a extrapolação e os cortes usam-se ainda `scan_verde` e `scan_laranja` de julho (61 peças, mesmo layout, por isso há GT por posição).
Scripts: `tools/diagnostico/gemeos/segcache.py`, `esym.py` e `cortes.py`. Não houve alterações em `src/` nem em `tests/`. Todos os números estão em `results.json` (chaves `esym` e `cortes`).
Etiquetas: **[V]** = verificado aqui (com n e a fonte); **[NT]** = não testado ou extrapolação.

## Resumo

1. **Os gémeos de 180° são o mesmo recorte [V].** Com um contorno sem mordidelas, a forma encontra o gémeo em **20/20** nas duas direções e com as duas poses. O RMS gémeo é igual ao ruído de re-digitalização da própria peça: A2/B2 dá 0,39 mm (free) e o re-scan A1/A2 dá 0,27–0,36 mm. O não-gémeo mais próximo nunca fica abaixo de 0,60 mm (n = 20 consultas; 581 pares não-gémeos da mesma classe).
2. **Com o pipeline do produto (`segment_pieces`) o teste falha [V]:** RMS gémeo mediano de 1,0–1,8 mm e top-1 de 8–13/20. A causa é a fronteira da segmentação, não a métrica nem o puzzle. Nos lados de sombra a fronteira fica serrilhada e, nas peças escuras de prado (B2), entra até cerca de 1 mm dentro da peça (`esym_franjas_contorno.png`).
3. **Os números rápidos do Tiago (0,28 / 0,34 / 0,56) reproduzem-se [V]**, mas o 0,28 é otimista. A1 e B2 estão na mesma pose no vidro, e o limiar simples inclui a sombra projetada (0,5–1 mm nos lados de baixo e da esquerda), que nessa pose se anula. Para pose arbitrária, o número honesto é A2/B2: **0,39–0,52 mm**.
4. **Veredicto do M5: viável quanto ao puzzle [V]; não viável com a segmentação atual [V]** (detalhe na secção do veredicto). Antes do M10 é obrigatório arranjar a fronteira no M3.
5. **Margem em 3008 [NT, extrapolação]:** com o contorno híbrido, a métrica free e o filtro de classe, o número esperado de falsos candidatos abaixo de t = p95 dos gémeos (0,505 mm) é ≈ 0,02–0,04 com N = 60, ≈ 0,16–0,30 com N = 500 e ≈ 0,9–1,8 com N = 3008. Em 3008 a forma sozinha não chega, como se esperava. A zona da imagem é necessária.
6. **Cortes repetidos [V]:** não há excesso de pares de lados "iguais" acima do acaso. A contagem direta (20) é igual à invertida (20), que serve de linha de base. Daqui sai D ≳ 600–1200 cortes distintos (95 %), compatível com "todos diferentes salvo a simetria" (≈ 2953). O poder é baixo acima de D ≈ 1000.

## Segmentação (A1, A2, B2, B1)

| Scan | Peças `segment_pieces` | Clusters | Notas |
|---|---|---|---|
| A1 | 20 | 0 | |
| A2 | 20 | 0 | |
| B2 | **19 → 20** | 0 | A peça (3,4) está a cerca de 12 px do bordo direito do scan e é descartada pelo filtro de "toca na moldura" (`_extract_components`, `_FRAME_MARGIN_FRAC = 0,004`, ≈ 14 px). **Contornei-o sem tocar em `src/`:** antes de segmentar, junto aos 4 scans uma moldura de 64 px com a cor mediana da orla e depois desfaço o deslocamento (`segcache.py`). |
| B1 | 20 | 0 | As 2 peças encostadas da fila 3 foram separadas pelo seam-carve: não houve cluster. Mesmo assim, B1 fica fora das métricas. |

Defeitos de `src/segmentation.py` encontrados (registados aqui, não corrigidos):
- **(S1) Peça perto do bordo do scan é descartada em silêncio** se estiver a menos de cerca de 1,2 mm do bordo da imagem [V, B2 (3,4)]. Num scanner de mesa é um caso normal. Basta dar um aviso ou alargar a imagem antes do filtro.
- **(S2) A fronteira nos lados de sombra fica serrilhada e morde peças escuras** [V, `esym_franjas_contorno.png`, `gemeos_B2__contours.jpg`]. Nas peças de prado (escuras e esverdeadas sobre verde) o contorno entra até cerca de 1 mm. Nas azuis (A1) exclui corretamente a sombra, mas deixa dentes de 0,2–0,4 mm no lado de baixo. Rugosidade mediana (perímetro / perímetro suavizado): `segment_pieces` A1 1,095, A2 1,086, B2 1,135 (máx. 1,217); híbrido 1,066–1,067 nos três [V, n = 20 cada]. Corda mediana dos lados: `segment_pieces` 17,6–18,0 mm; híbrido 18,6 mm (inclui a sombra). O nominal é √(18,5·17,9) = 18,2 mm. **Nenhum dos dois contornos é a verdade**: um come e o outro inclui sombra.
- **(S3) `edges.py`** marca como `edge` só 8 das 20 peças de borda em cada scan (A1, A2 e B2) [V]. Com `shapelib`, as 20 têm exatamente 1 lado F (ver Topologia).

### Variantes de contorno usadas

| Variante | Separação das peças | Fronteira | Para quê |
|---|---|---|---|
| `seg` | `segment_pieces` | `segment_pieces` | Pipeline do produto (o que o plano pede) |
| `simples` | limiar Lab do `gemeos_quick.py` | o mesmo limiar (Lab ponderado, d > 28, abertura 5, fecho 9) | Separar o efeito da segmentação do efeito da métrica |
| `hibrido` | `segment_pieces` (Voronoi das máscaras) | limiar simples, até 1,5 mm do contorno `seg` | Igual a `simples` nas folhas A/B; necessário nos scans de julho, onde o limiar simples junta peças (37 e 41 componentes em vez de 61) |

Nas três variantes, a forma é medida com `shapelib.analyse_v2` (cantos por quadrilátero ótimo) e duas métricas: **corner** (`shape_dist`: 4 rotações cíclicas × Kabsch) e **free** (`dist.free_dist`: contorno suavizado com σ = 1,5 amostras, 512 pontos, FFT cíclica + rotação). Ambas em mm RMS. Os cantos foram encontrados em 20/20 peças em todos os scans e variantes.

## E-sym: gémeos A1/B2 e A2/B2, re-scan A1/A2

GT só para avaliar: A1(f,k) ↔ A2(f,k) e A1(f,k) ↔ B2(f, 4−k). O emparelhamento sai da forma (argmin por linha + NN mútuo). n = 20 em todas as linhas. Formato: mediana / p90 / máx., em mm.

| Variante, métrica | Re-scan A1/A2 | Gémeo A1/B2 | Gémeo A2/B2 | Não-gémeo mais próximo (B2 ∪ A1), mediana / mín. | Top-1 A1→B2 / B2→A1 / A2→B2 | NN mútuo (corretos) | Margem mín. / mediana | Margem < 1,5 |
|---|---|---|---|---|---|---|---|---|
| seg, corner | 0,68 / 0,87 / 0,94 | **1,01** / 1,38 / 1,55 | 1,15 / 1,52 / 2,00 | 0,83 / 0,54 | **13** / 16 / 13 | 12 (10) | 0,48 / 0,85 | 17 |
| seg, free | 0,96 / 1,24 / 1,27 | **1,42** / 2,04 / 2,46 | 1,81 / 2,58 / 2,68 | 0,90 / 0,64 | **8** / 12 / 8 | 10 (7) | 0,33 / 0,64 | 17 |
| simples, corner | 0,45 / 0,63 / 0,79 | 0,28 / 0,45 / 0,65 | 0,52 / 0,72 / 0,88 | 0,72 / 0,45 | 20 / 20 / 19 | 20 (20) | 1,10 / 2,60 | 3 |
| simples, free | 0,33 / 0,46 / 0,61 | 0,23 / 0,37 / 0,39 | 0,41 / 0,55 / 0,66 | 0,82 / 0,58 | 20 / 20 / 20 | 20 (20) | 2,14 / 3,55 | 0 |
| **híbrido, corner** | 0,36 / 0,51 / 0,53 | **0,34** / 0,62 / 0,67 | 0,49 / 0,69 / 0,77 | 0,75 / 0,57 | **20** / 20 / 18 | 20 (20) | 0,89 / 2,27 | 4 |
| **híbrido, free** | 0,27 / 0,39 / 0,49 | **0,29** / 0,43 / 0,45 | **0,39** / 0,51 / 0,64 | 0,83 / 0,60 | **20** / 20 / 20 | 20 (20) | 1,53 / 2,83 | 0 |

- Margem = (não-gémeo mais próximo em B2 ∪ A1∖própria) / (RMS ao gémeo).
- Com o híbrido e a métrica corner, as peças com margem < 1,5 são A1(0,4) c9 (1,11), A1(1,3) c13 (1,20), A1(2,4) c19 (0,89, confundida com A1(3,3) por 0,57 mm contra 0,64 ao gémeo; o argmin em B2 continua certo) e A1(3,3) c23 (1,49). Com o híbrido e a métrica free nenhuma peça fica abaixo de 1,5 (mínimo 1,53).
- Consulta A1 contra o pool de 39 (B2 ∪ A1∖própria): top-1 = 20/20 (híbrido free), 19/20 (híbrido corner), 6/20 (seg corner) e 4/20 (seg free) [V].
- B1 (só diagnóstico, híbrido free): B2(f,k) ↔ B1(f,k) é a mesma peça rodada; dá 20/20 top-1 com re-scan mediano de 0,37 mm. A1 → B1 dá 20/20 gémeos, mediana 0,31 mm. Com `seg`, B2 → B1 acerta poucas (ver `B1_diag` no JSON).
- Figuras: `esym_sobreposicoes.png` (seg, A1/B2), `esym_sobreposicoes_hibrido_A2B2.png`, `esym_rescan.png` e `esym_matriz.png`. Em todas, os pares A1/B2 são visivelmente o mesmo recorte; com `seg` as diferenças são dentes e mordidelas locais, não patilhas deslocadas.

### Comparação com os números rápidos do Tiago

| Medida | Tiago (`gemeos_quick.py`) | Réplica aqui do mesmo código [V] | `simples` + shapelib free | híbrido free | seg free |
|---|---|---|---|---|---|
| Gémeo A1/B2, mediana (máx.) | 0,28 (0,44) | 0,277 (0,435) | 0,23 (0,39) | 0,29 (0,45) | 1,42 (2,46) |
| Re-scan A1/A2, mediana (máx.) | 0,34 (0,65) | 0,339 (0,654) | 0,33 (0,61) | 0,27 (0,49) | 0,96 (1,27) |
| Gémeo A2/B2, mediana (máx.) | 0,43 (0,62) | 0,434 (0,622) | 0,41 (0,66) | 0,39 (0,64) | 1,81 (2,68) |
| Não-gémeo mais próximo, mediana / mín. | 0,83 / 0,56 | 0,831 / 0,574 | 0,82 / 0,58 | 0,83 / 0,60 | 0,90 / 0,64 |
| Top-1 | 20/20 | 20/20 | 20/20 | 20/20 | 8/20 |

Leitura das diferenças:
- **A réplica reproduz o script rápido** em todos os números menos o mínimo do não-gémeo (0,574 contra 0,56). Não sei explicar essa diferença de 0,01 mm [NT].
- **A suavização e o pool fazem pouca diferença.** A métrica free suaviza o contorno (σ = 1,5 amostras); o script rápido não suaviza, e isso baixa cerca de 0,05 mm. Aqui o "não-gémeo mais próximo" exclui o gémeo do GT e inclui também A1∖própria, não só B2.
- **A segmentação faz a diferença toda: de ×3 a ×5.** Na mesma métrica free, passar do limiar simples para `segment_pieces` sobe o gémeo de 0,23 para 1,42 mm. A métrica free sofre mais do que a corner porque não ancora nos cantos e a suavização (≈ 0,2 mm) não apaga mordidelas de 1 mm. Correlação do RMS gémeo com a rugosidade máxima do par (seg free): Pearson 0,71, Spearman 0,82. Em seg corner é 0,45/0,49; em híbrido free é 0,33/0,38 [V, n = 20].
- **"Gémeo mais parecido do que o re-scan" é um efeito da pose, não da faca.** O limiar simples inclui a sombra projetada pela espessura da peça, sempre nos mesmos lados no referencial do scanner (zoom em `esym_franjas_contorno.png`, contorno azul). A1 e B2 têm a mesma pose (lado reto para cima), por isso a sombra cai nos lados homólogos e anula-se. A2 está rodada 180°, a sombra cai do lado oposto e o RMS sobe para 0,39–0,52 mm. **Para o M10 (pose arbitrária) o número a usar é A2/B2.**

### Por lado (20 pares, lados homólogos pelo `best_k` do `shape_dist`)

RMS global = bloco de 64 pontos depois do Kabsch da peça inteira. RMS perfil = perfil normalizado × corda média, com cada lado no seu referencial. Formato: mediana / p90, em mm.

| Variante | Comparação | Lados não-F (n = 60): RMS global | RMS perfil | \|ΔL\| | dp ΔL | Tipo T/B coincide | Lado F (n = 20): RMS perfil, \|ΔL\| |
|---|---|---|---|---|---|---|---|
| híbrido | gémeo A1/B2 | 0,34 / 0,52 | 0,33 / 0,60 | 0,21 / 0,75 | 0,50 | 60/60 | 0,11, 0,17 |
| híbrido | gémeo A2/B2 | 0,52 / 0,77 | 0,52 / 0,82 | 0,43 / 0,95 | 0,50 | 60/60 | 0,19, 0,43 |
| híbrido | re-scan A1/A2 | 0,39 / 0,60 | 0,40 / 0,60 | 0,25 / 0,66 | 0,41 | 60/60 | 0,23, 0,60 |
| seg | gémeo A1/B2 | 1,01 / 1,81 | 1,02 / 1,89 | 0,48 / 1,15 | 0,59 | 60/60 | 0,13, 0,22 |
| seg | re-scan A1/A2 | 0,62 / 1,15 | 0,74 / 1,10 | 0,30 / 0,66 | 0,41 | 60/60 | 0,63, 0,19 |

O \|ΔL\| mediano do gémeo com pose oposta (0,43 mm) está acima dos 0,2 mm previstos na proposta de filtro por cordas ("|ΔL| ≤ 0,5 mm por lado"). Com p90 = 0,95 mm, **um filtro de 0,5 mm por lado rejeitaria cerca de 1 em cada 3 lados de gémeos verdadeiros** [V, n = 60]. A corda depende da posição dos cantos e da sombra; o limiar tem de ser calibrado com pose oposta (≈ 1 mm).

### Topologia [V, n = 20 por scan, 3 variantes]

- **20/20 peças com exatamente 1 lado F** em A1, A2 e B2, nas três variantes. Desvio máximo dos lados F ≤ 0,058 L; o mínimo dos lados não-F é ≥ 0,179 L, portanto há um vazio claro.
- Classe coincide: A1/B2 20/20, A1/A2 20/20, A2/B2 20/20. Não houve casos em que F falhasse.
- Classes em A1: BTFT 8, BFBT 8, BBTF 1, BFTT 1, BBFT 1, FTTT 1. Na borda alternam BTFT e BFBT.

## Extrapolação da margem (ponto 6) — [V em 101 peças; NT em 3008]

Pool: as 40 peças de A1 ∪ B2 (borda, hoje) mais as 61 de `scan_verde` (julho, quase todas interiores; re-analisadas do `.npz` atual). Pares não-gémeos: 760 dentro das 40 (sem os 20 pares), 1830 dentro das 61 e 2440 cruzados, num total de 5030. Destes, 581 são da mesma classe topológica (224 dentro das 40, 337 dentro das 61 e 20 cruzados). Distribuição dos gémeos: 40 medidas (A1/B2 + A2/B2).

| Variante, métrica | t = p95 gémeos | t = máx. gémeos | Não-gémeos mesma classe: mín. / p5 / mediana | Abaixo de t95: mesma classe / todos | Gémeo top-1 no pool de 100 |
|---|---|---|---|---|---|
| **híbrido, free** | **0,505** | 0,641 | 0,600 / 0,852 / 1,48 | **0/581** / 0/5030 | **40/40** |
| híbrido, corner | 0,685 | 0,765 | 0,566 / 0,820 / 1,41 | 7/581 / 7/5030 | 39/40 |
| seg, corner | 1,551 | 2,003 | 0,540 / 0,982 / 1,57 | 275/581 / 297/5030 | 19/40 |
| seg, free | 2,574 | 2,678 | 0,644 / 1,063 / 1,83 | 482/581 / 810/5030 | 11/40 |

**Falsos candidatos esperados** abaixo de t num pool de N candidatos **da mesma classe**: E = N·p, com p da cauda inferior (5 % mais baixos, pelo menos 12 pontos), por ajuste exponencial e Weibull. Híbrido, métrica free:

| t | p (empírico / exp / Weibull) | N = 10 | N = 60 | N = 500 | N = 3008 |
|---|---|---|---|---|---|
| p95 gémeos (0,505 mm), mesma classe (n = 581) | 0 / 5,9·10⁻⁴ / 3,1·10⁻⁴ | 0,003–0,006 | **0,02–0,04** | **0,16–0,30** | **0,9–1,8** |
| p95 gémeos, só bordas (n = 224) | 0 / 6,7·10⁻⁴ / 3,9·10⁻⁴ | 0,004–0,007 | 0,02–0,04 | 0,20–0,34 | 1,2–2,0 |
| máx. gémeos (0,641 mm), mesma classe | 3,4·10⁻³ (os três) | 0,03 | 0,21 | 1,7 | 10 |
| híbrido corner, p95 (0,685 mm), mesma classe | 1,2·10⁻² | 0,12 | 0,7 | 5,5–6,0 | 33–36 |

Com `seg`, p chega a 0,47–0,83 na mesma classe e a métrica deixa de servir.

**Curva empírica do "mínimo não-gémeo" contra o tamanho do pool** (híbrido free, 200 subamostras):

| Pool | 10 | 20 | 40 | 61 | 99/101 | Ajuste log-linear → 500 | → 3008 |
|---|---|---|---|---|---|---|---|
| Consulta (cada uma das 40) → NN não-gémeo no pool, mediana | 1,29 | 1,07 | 0,90 | 0,85 | 0,83 | 0,44 | 0,07 |
| idem, p10 | 0,83 | 0,77 | 0,70 | 0,69 | 0,68 | 0,55 | 0,42 |
| Mínimo de todos os pares não-gémeos do subconjunto, mediana | 1,03 | 0,82 | 0,69 | 0,64 | 0,60 | 0,26 | <0 |

Leitura:
- O ajuste log-linear da mediana é demasiado pessimista. A curva achata (0,85 → 0,83 entre 61 e 99), porque a cauda é dominada pela classe, e com N grande dá valores sem sentido físico (< 0). A curva do p10 é mais estável: diz que, num pool sem filtro de classe, **cerca de 10 % das consultas terão um não-gémeo abaixo de 0,55 mm em N = 500 e de 0,42 mm em N = 3008**. Isto é da mesma ordem que o modelo de cauda (E ≈ 1–2 em 3008) [NT].
- A margem para a forma sozinha é boa até N ≈ 60 (E ≤ 0,04) e marginal com N = 500 por classe (P(≥ 1 falso) ≈ 15–26 %). Em 3008 o falso candidato passa a ser provável (60–83 %). Conclusão: **classe + forma (free, híbrido) + gap + zona da imagem**. A zona é obrigatória em 3008 e útil a partir de cerca de 500.
- Ressalvas: (i) as 61 de julho são quase todas interiores e as 40 de hoje são todas de borda, por isso a "mesma classe" mistura dois regimes e há só 20 pares cruzados da mesma classe; (ii) o t vem de 20 pares; (iii) o contorno híbrido inclui sombra, o que dá um viés dependente da pose que aumenta um pouco as distâncias não-gémeas de julho (pose arbitrária) e as distâncias gémeas A2/B2.

## Cortes repetidos (`cortes.py`)

Contexto: o 64 × 47 tem 63·47 + 64·46 = **5905 cortes internos**. Sob a simetria de 180°, todos os cortes formam pares exceto o central (entre c32 e c33 na linha 24), o que dá **2953 distintos**. Em 61 peças tiradas ao acaso, o número esperado de pares de gémeos é 61·60/2/3007 ≈ 0,61. O relatório de forma não encontrou nenhum.

### Ruído por lado

Lados homólogos verde ↔ laranja (GT por posição, 60 pares, classe coincide em 59/60; 236 lados T/B com o mesmo tipo). Mesma pose, ou seja, ruído otimista.

| Variante | RMS perfil, mediana / p90 / dp (mm) | \|ΔL\| mediana / p90 | dp ΔL (todos / peças com re-scan < 1 mm) | Pose oposta A1/A2 (n = 60): RMS / \|ΔL\| mediana |
|---|---|---|---|---|
| seg | 0,28 / 1,25 / 0,56 | 0,17 / 0,59 | 0,47 / **0,29** (n = 193) | 0,74 / 0,30 |
| híbrido | 0,34 / 1,08 / 0,58 | 0,24 / 0,79 | 0,62 / 0,47 (n = 213) | 0,40 / 0,25 |

O dp de ΔL de 0,285 mm do relatório de forma **reproduz-se** (0,29) no subconjunto limpo com `seg` [V]. Com todos os lados sobe para 0,47, por causa das franjas. O p90 do RMS (≈ 1,1–1,25 mm) é dominado por franjas e por isso é inútil como limiar de "mesmo corte". O critério útil é a mediana do ruído (≈ 0,3 mm), combinada com \|ΔL\| < p90.

### Pares de lados do mesmo tipo de peças diferentes

Contorno híbrido. Verde: 241 lados não-F (T 115, B 126) → 6477 pares T–T + 7779 pares B–B = 14 256. Com A1 ∪ B2: mais 120 lados não-F, gémeos excluídos → 32 090.

| Conjunto | Pares | RMS mín. / p5 / mediana (mm) | < mediana do ruído (0,339): direto / invertido | e \|ΔL\| < 0,79: direto / invertido | < p90 (1,08) e \|ΔL\|: direto / invertido |
|---|---|---|---|---|---|
| verde, T–T | 6477 | 0,24 / 0,69 / 1,54 | 9 / 10 | 2 / 5 | 565 / 581 |
| verde, B–B | 7779 | 0,29 / 0,71 / 1,64 | 11 / 10 | 5 / 5 | 597 / 613 |
| verde + A1B2, T–T | 15 419 | 0,24 / 0,63 / 1,43 | 31 / 29 | 10 / 19 | 1739 / 1665 |
| verde + A1B2, B–B | 16 671 | 0,20 / 0,67 / 1,52 | 27 / 17 | 16 / 8 | 1826 / 1821 |
| Controlo complementar: T contra B invertido e negado (verde) | 14 307 | 0,17 / 0,90 / 1,91 | 1 | 1 | 553 |
| **Controlo positivo: lados homólogos dos 20 gémeos** (A1/B2) | 60 | 0,14 / 0,16 / 0,33 | **31/60** | 31/60 | 54/60 |

Leitura:
- **"Invertido" (x → 1−x) é a linha de base do acaso.** Um corte espelhado não é o mesmo corte físico, mas tem a mesma estatística de "lado parecido" (cabeça redonda standard). Contagens diretas iguais às invertidas (20 contra 20 no verde; 7 contra 10 com \|ΔL\|) querem dizer **nenhum excesso de cortes repetidos** [V].
- Os pares mais parecidos (`cortes_pares_mais_parecidos.png`) são cabeças standard no mesmo sítio, com RMS de 0,20–0,25 mm. Quase todos têm \|ΔL\| de 0,3–2 mm, o que os mostra como sósias e não como o mesmo corte.
- O controlo complementar dá menos pares (1) do que o mesmo tipo (20). Isto acontece porque o contorno híbrido inclui sombra: incha as patilhas e estreita os encaixes, e a comparação T contra −B fica com um desvio sistemático. Esse controlo não é comparável em valor absoluto [V, mecanismo inferido].
- **Estimativa do dicionário.** Poder = 31/60 = 0,52 (fração dos lados gémeos, o mesmo corte conhecido, que passa o critério). Excesso direto − invertido = 0 (verde, só RMS) e −3 (com \|ΔL\|). O limite superior de 95 % do excesso é ≈ 12 e ≈ 8, ou seja, ≤ 24 e ≤ 16 repetições verdadeiras corrigidas pelo poder. Daí **D ≥ 594** (só RMS) e **D ≥ 911** (com \|ΔL\|) cortes distintos por tipo [V, verde]. Com verde + A1B2: D ≥ 518 e D ≥ 1162. O D ≈ 1/f ingénuo (sem corrigir o acaso) dá 713 e 2037 (verde) e não é interpretável, porque f é quase todo acaso.
- **Poder baixo.** Só com a simetria, cada lado tem exatamente 1 parceiro idêntico em cerca de 5904 do mesmo tipo (D_eff ≈ 5904). Com D = 2953, esperar-se-iam cerca de 14 256 / 2953 ≈ 4,8 pares idênticos no verde, dos quais cerca de 2,5 detetáveis com o poder de 0,52. Isso está abaixo da flutuação do acaso (±6). Este teste **exclui dicionários pequenos (D ≲ 500–1000)** mas **não distingue** D ≈ 1000 de "todos distintos" [V/NT].
- Com `seg`, o controlo positivo falha: 0/60 lados gémeos abaixo da mediana do ruído. O ruído do verde ↔ laranja é de mesma pose, e os lados de B2 estão mordidos. Por isso a variante `seg` não serve para este teste (números no JSON).

## Veredicto do M5

Critério: RMS gémeo mediano ≤ 0,7 mm **e** top-1 ≥ 95 %.

| Contorno, métrica | A1/B2 (mesma pose) | A2/B2 (pose oposta) | Cumpre |
|---|---|---|---|
| seg, corner | 1,01 mm, 65 % | 1,15 mm, 65 % | **não** |
| seg, free | 1,42 mm, 40 % | 1,81 mm, 40 % | **não** |
| híbrido, corner | 0,34 mm, 100 % | 0,49 mm, 90 % | só em A1/B2 |
| **híbrido, free** | **0,29 mm, 100 %** | **0,39 mm, 100 %** | **sim** |
| simples, free | 0,23 mm, 100 % | 0,41 mm, 100 % | sim |

**M5 decidido: VIÁVEL quanto ao puzzle [V, 20 pares, 2 poses].** Os gémeos de 180° são o mesmo recorte, dentro do ruído de re-digitalização, e a forma encontra-os em 20/20 com NN mútuo, margem ≥ 1,5 e top-1 também no pool de 100. **Condição:** a fronteira do `segment_pieces` não cumpre [V]. O M10 depende do M3 dar uma fronteira sem mordidelas nas peças escuras e com um tratamento explícito da sombra projetada (por exemplo, a sombra cai sempre nos mesmos lados no referencial do scanner). Até lá, o contorno de referência para medir forma é o híbrido. Métrica recomendada: free, com t ≈ 0,5 mm e gap ≥ 1,5.

## Atualização 2026-10-31: sem moldura e variante `sombra` (E-fundo, método (c))

O S1 está corrigido em `src/` (`bc124d2`) e `segcache.PAD = 0`. Os `.npz` dos gémeos foram regenerados sem moldura, e `esym.py` voltou a correr com as quatro variantes. A variante nova `sombra` = híbrido com o fundo estimado pela orla e os píxeis de sombra rejeitados por tonalidade (`L < L_fundo`, `|h − h_fundo| < 10°`, `C ≥ 0,4·C_fundo`; parâmetros fixados no `scan_verde`, ver `docs/diagnostico/fundo/RESULTADOS.md`). Métrica free; n = 20 por linha; mediana / máx.

| Variante | Re-scan A1/A2 | Gémeo A1/B2 | Gémeo A2/B2 | Top-1 A1→B2 / B2→A1 / A2→B2 | Margem < 1,5 | Rugosidade B2 p95 | Critério M3 |
|---|---|---|---|---|---|---|---|
| seg | 0,98 / 1,25 | 1,33 / 3,13 | 1,93 / 3,31 | 8 / 14 / 8 | 18 | 1,195 | não [F] |
| híbrido | 0,27 / 0,50 | 0,29 / 0,45 | 0,38 / 0,64 | 20 / 20 / 20 | 0 | 1,085 | **sim** [V] |
| sombra | 0,42 / 0,61 | 0,45 / 4,72 | 0,77 / 4,77 | 15 / 18 / 15 | 8 | 1,139 | não [F] |

- **Sem a moldura, `seg` e `hibrido` reproduzem os números de 30-out [V]:** híbrido free 0,27 / 0,29 / 0,38 contra 0,27 / 0,29 / 0,39; seg free 0,98 / 1,33 / 1,93 contra 0,96 / 1,42 / 1,81 (±0,12 mm, com os top-1 do seg a variarem 1–4 peças). A extrapolação também se reproduz (t95 0,507; 40/40 no pool de 100). A chave `cortes` do `results.json` **não** foi recalculada: ainda vem dos `.npz` com moldura.
- **`sombra` falha o M3 [F]** porque apaga zonas de relva verde-viva nas peças de prado de B2. O pior é B2 (0,4), com RMS de 4,7 mm ao gémeo (`esym_franjas_sombra_B2.png`). Nas peças claras (A1/A2) é o contorno mais limpo medido até agora: \|ΔL\| de re-scan 0,13 mm, rugosidade 1,055, corda 18,0–18,1 mm. O passo seguinte do M3 (rejeição restrita à faixa exterior no lado da sombra) está descrito no relatório do E-fundo.

## Figuras

| Ficheiro | O que mostra |
|---|---|
| `gemeos_{A1,A2,B2,B1}__contours.jpg` | Overlays da segmentação (`segment_pieces`, com moldura de 64 px) |
| `esym_sobreposicoes.png` | Os 20 pares de gémeos A1/B2 alinhados (cantos + Kabsch), contorno `seg`, com RMS corner e free e tipos de lado |
| `esym_sobreposicoes_hibrido_A2B2.png` | Os 20 pares A2/B2 (pose oposta), contorno híbrido |
| `esym_rescan.png` | Re-scan A1/A2 (mesma peça rodada 180°), contorno `seg` |
| `esym_histogramas.png`, `esym_histogramas_hibrido.png` | Re-scan contra gémeo contra não-gémeo, corner e free |
| `esym_matriz.png` | Matrizes 20×20 A1×B2 (seg e híbrido; corner e free): gémeo a vermelho, argmin marcado |
| `esym_franjas_sombra_B2.png` | (31-out) As 3 peças de prado mais escuras de B2, a 2×: seg vermelho, híbrido azul, sombra verde |
| `esym_franjas_contorno.png` | Recortes a 2× com o contorno `segment_pieces` (vermelho) e o do limiar simples (azul): mordidelas em B2 e sombra incluída pelo limiar |
| `cortes_pares_mais_parecidos.png` | Os 8 pares de lados do mesmo tipo de peças diferentes mais parecidos (verde + A1/B2, híbrido) |

## O que NÃO foi verificado

- Pares de gémeos interiores (só bordas; todas com 1 F, o que torna a classe pouco discriminante dentro das bordas: 224 pares da mesma classe em 40 peças).
- Qual dos contornos está mais perto da aresta física (sem régua nem GT de contorno). O nominal 18,2 mm fica entre `seg` (17,6–18,0) e o híbrido (18,6).
- A extrapolação para 3008 [NT]: assume que as 101 peças representam a distribuição de cada classe.
- A diferença de 0,01 mm no mínimo não-gémeo do script rápido (0,574 aqui contra 0,56 na nota).
- O efeito da cor do fundo nas mordidelas: prado sobre verde é o pior caso. Não testei outro fundo (fora de âmbito).
