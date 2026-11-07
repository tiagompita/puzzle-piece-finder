# Peças encaixadas ou encostadas na mesma folha de scan (BUG 3), 2026-11-01

Script: `tools/diagnostico/segmentacao/contactos.py` (correr a partir da raiz; cache em `$PPF_SCRATCH/contactos/`). Resultados: `contactos_resultados.json`. Figura: `contactos_antes_depois.jpg`.

## 1. O defeito

Na folha S0023 (`images/pieces/legado/montado_p15_300dpi.jpg`) a peça #3 tem uma saliência dentro da boca do encaixe da #4. A separação a baixa resolução (`segment_pieces`) deu a saliência à #4. Depois, o contorno de `segment_scan`, restrito à célula de Voronoi de cada peça, manteve essa atribuição. Resultado: a #4 ficou com a saliência alheia e com um buraco verde, e a #3 ficou com um corte reto lido como lado F falso (corda 15,96 mm, classe BFTT). [V] (recortes P0777/P0778; overlay; `shape.analyse`)

## 2. A correção (`src/segmentation.py`, dentro de `segment_scan`, depois do refinamento de Voronoi; `segment_pieces` não muda)

Faz-se só com `split_contacts=True` (valor por omissão). Com `split_contacts=False` o resultado é bit a bit igual ao código anterior. [V] (S0023: 59 contornos e bbox idênticos ao resultado gravado antes da alteração)

1. **Grupos de contacto.** Junta peças cujas bbox do contorno ficam a menos de 1 mm uma da outra, ou cujos contornos ficam a ≤ 1,2 mm (as máscaras dilatadas 0,6 mm sobrepõem-se). Entram todas as peças, incluindo as `is_cluster`.
2. **Janela.** É a união das células de Voronoi dos membros. Usa o limiar de primeiro plano *só aberto*, porque o fecho de 0,76 mm fazia ponte sobre frestas submilimétricas. Os componentes são 4-conexos.
   - (a) **Conectividade.** Se há tantos componentes com área ≥ 0,3 × a mediana como membros, cada componente vai para o membro cuja máscara antiga mais sobrepõe (melhor bijeção). Senão, cada componente é tratado contra os *núcleos* dos membros. O núcleo é a máscara antiga ∩ primeiro plano, com os furos < 4 mm² preenchidos, erodida 2 mm, e fica-se com o maior componente. Um componente que toca um só núcleo vai inteiro para esse membro. Um que não toca nenhum fica com a atribuição de Voronoi.
   - (b) **Sem fresta visível** (o componente toca ≥ 2 núcleos). Aplica-se uma bacia hidrográfica por inundação prioritária a partir dos núcleos, sobre black-hat(L\*, 1,5 mm) + gradiente Lab, cada um normalizado pelo seu p99. Não se usa a transformada de distância, que cortaria no pescoço da saliência. Depois retiram-se as espículas finas (abertura 0,5 mm). Isto evita que a inundação corra pela linha de sombra encostada à vizinha, e os píxeis retirados vão para a região mantida mais próxima.
   - Por fim, cada região é fechada (0,76 mm) e recortada pela faixa habitual de 1,5 mm à volta dos contornos de baixa resolução. O recorte só se aplica se mantiver ≥ 95 % da região; se cortar mais, os contornos de baixa resolução falharam parte da peça e a faixa não é usada. Fica-se com o maior contorno externo, preenchido.
3. **Validação por forma** (`src/shape.analyse`). Conta como violação:
   - não ter 4 cantos (conta 3);
   - uma corda fora de [15,5; 21] mm;
   - um lado F com corda < 17 mm;
   - quando foi preciso a bacia, os lados frente a frente não serem T↔B (`side_complement`).

   A nova partição só é adotada se algum membro mudou (IoU < 0,98) e se a soma das violações não aumenta. Os membros que não mudaram guardam o registo antigo bit a bit. Um `is_cluster` cujo novo contorno não tem violações deixa de ser cluster.
4. **Marca.** Todos os membros de um grupo levam `contacto = {com: [index dos outros], confianca: alta|baixa, metodo: conectividade|watershed|nenhum, alterado}`. A confiança é `baixa` quando houve bacia ou mudança e a partição final ainda tem violações. `src/ingest.py` copia `contacto` para `flags`, e o overlay da folha desenha a vermelho as peças com `baixa`. O número de peças nunca muda: o passo só redistribui píxeis entre peças existentes.

## 3. Resultados nas 26 folhas de `projects/alpes/scans/`

| Folha | Ficheiro | Tipo | Peças antes → depois | Pares em contacto | sem fresta (watershed) | Alterados | `baixa` | Numeração igual | t antes / depois (s) |
|---|---|---|---|---|---|---|---|---|---|
| S0001 | `coluna5-24_300dpi_folhaA.jpg` | gt | 20 → 20 | 0 | 0 | 0 | 0 | sim | 1.9 / 1.8 |
| S0002 | `coluna5-24_folhaB_300dpi_rot180.jpg` | gt | 20 → 20 | 0 | 0 | 0 | 0 | sim | 1.9 / 1.9 |
| S0003 | `gt_canto_BE_soltas_300dpi.jpg` | gt | 25 → 25 | 5 | 5 | 5 | 5 | sim | 3.7 / 9.3 |
| S0004 | `gt_canto_BD_soltas_300dpi.jpg` | gt | 28 → 28 | 0 | 0 | 0 | 0 | sim | 2.2 / 2.2 |
| S0005 | `ereal2_ceu_f1p1_300dpi.jpg` | soltas | 35 → 35 | 0 | 0 | 0 | 0 | sim | 2.6 / 2.8 |
| S0006 | `ereal2_ceu_f1p2_300dpi.jpg` | soltas | 15 → 15 | 0 | 0 | 0 | 0 | sim | 1.9 / 2.0 |
| S0007 | `ereal2_ceu_f2p1_300dpi.jpg` | soltas | 42 → 42 | 0 | 0 | 0 | 0 | sim | 3.0 / 3.0 |
| S0008 | `ereal2_ceu_f2p2_300dpi.jpg` | soltas | 8 → 8 | 0 | 0 | 0 | 0 | sim | 1.6 / 1.7 |
| S0009 | `montado_p01_300dpi.jpg` | montado | 43 → 43 | 0 | 0 | 0 | 0 | sim | 2.6 / 2.6 |
| S0010 | `montado_p02_300dpi.jpg` | montado | 46 → 46 | 1 | 0 | 0 | 0 | sim | 2.7 / 2.9 |
| S0011 | `montado_p03_300dpi.jpg` | montado | 18 → 18 | 0 | 0 | 0 | 0 | sim | 2.0 / 2.0 |
| S0012 | `montado_p04_300dpi.jpg` | montado | 44 → 44 | 0 | 0 | 0 | 0 | sim | 3.0 / 2.9 |
| S0013 | `montado_p05_300dpi.jpg` | montado | 51 → 51 | 2 | 0 | 0 | 0 | sim | 2.9 / 3.0 |
| S0014 | `montado_p06_300dpi.jpg` | montado | 48 → 48 | 4 | 0 | 0 | 0 | sim | 2.9 / 3.2 |
| S0015 | `montado_p07_300dpi.jpg` | montado | 36 → 36 | 0 | 0 | 0 | 0 | sim | 2.4 / 2.4 |
| S0016 | `montado_p08_300dpi.jpg` | montado | 37 → 37 | 0 | 0 | 0 | 0 | sim | 3.5 / 3.0 |
| S0017 | `montado_p09_300dpi.jpg` | montado | 34 → 34 | 0 | 0 | 0 | 0 | sim | 2.4 / 2.4 |
| S0018 | `montado_p10_300dpi.jpg` | montado | 39 → 39 | 0 | 0 | 0 | 0 | sim | 2.6 / 2.7 |
| S0019 | `montado_p11_300dpi.jpg` | montado | 38 → 38 | 1 | 0 | 0 | 0 | sim | 2.7 / 2.8 |
| S0020 | `montado_p12_300dpi.jpg` | montado | 48 → 48 | 1 | 1 | 1 | 1 | sim | 2.8 / 3.9 |
| S0021 | `montado_p13_300dpi.jpg` | montado | 44 → 44 | 0 | 0 | 0 | 0 | sim | 2.8 / 2.7 |
| S0022 | `montado_p14_300dpi.jpg` | montado | 55 → 55 | 0 | 0 | 0 | 0 | sim | 2.9 / 3.0 |
| S0023 | `montado_p15_300dpi.jpg` | montado | 59 → 59 | 6 | 1 | 1 | 0 | sim | 3.2 / 4.6 |
| S0024 | `blocos_p01_300dpi.jpg` | blocos | 29 → 29 | 0 | 0 | 0 | 0 | sim | 2.2 / 2.3 |
| S0025 | `blocos_p02_300dpi.jpg` | blocos | 36 → 36 | 0 | 0 | 0 | 0 | sim | 2.4 / 2.4 |
| S0026 | `blocos_p03_300dpi.jpg` | blocos | 11 → 11 | 0 | 0 | 0 | 0 | sim | 1.7 / 1.7 |

**Totais.**
- 20 pares em contacto direto; em 7 deles não há fresta visível e foi precisa a bacia.
- 7 pares alterados, 6 marcados `baixa`.
- **Contagem de peças igual nas 26 folhas.** [V]
- **Numeração (`grid_order` das peças ≥ 150 mm²) igual nas 26 folhas.** [V]
- Tempo total 66,5 s antes contra 75,2 s depois (+13 %). O pior caso é S0003, que passa de 3,7 s para 9,3 s por causa do grupo grande com o cluster #25. [V] (máquina partilhada, valores indicativos)

**Os 42 pares de bbox gravadas com folga < 1 mm** (bbox com margem `pad_ratio`):
- 20 cumprem o critério do grupo de contacto. Os outros 22 estão a ≥ 1,8 mm (contornos) e são vizinhos próximos, não contactos.
- Só 4 estão realmente encostados (contornos a ≤ 0,3 mm): S0003 #18/#19, #19/#24, #24/#25 e S0023 #3/#4.
- Juntando S0020 #24/#30 (1,3 mm entre contornos antigos, mas a partição antiga estava errada), houve 7 pares em que foi precisa a bacia, todos alterados.

## 4. O que se viu na figura (`contactos_antes_depois.jpg`: antes à esquerda, depois à direita; vermelho = 1.º membro, azul = 2.º)

- **S0023 #3/#4 (o caso do bug).** A saliência direita da #3 passa para a #3, e a #4 fica com o seu encaixe vazio. Classes: antes FTTB / TTTB (lado F falso de 15,96 mm), depois TTTB / TTBB, cordas [15,94; 18,25; 17,22; 18,80] e [18,41; 18,54; 16,44; 17,94] mm.
  - Já não há lado F, e todas as cordas estão em [15,5; 21] mm.
  - O lado de 15,9 mm mantém-se, agora como T. Medido na imagem, o lado direito da #3 tem ≈ 190 px ≈ 16,1 mm de canto a canto, por isso é a geometria real da peça e não um artefacto.
  - Confiança `alta`. [V]
  - **A conectividade sozinha NÃO resolve este par.** A sombra projetada liga a ponta da saliência à #4 no limiar (vê-se no `threshold_mask`), por isso o componente toca os dois núcleos e foi a bacia (passo b) que decidiu. [V] (`metodo = watershed`)
  - Resta um pequeno triângulo de fundo (≈ 1 mm) entre o topo da saliência e o lábio da #4, incluído no contorno da #3. [V, visto] Revisto em 2026-11-07 (§6): havia também a sombra debaixo da saliência dentro da #4; ambos corrigidos.
- **S0020 #24/#30** (P0651 colocada em (44,1), P0657 em (45,1); ordem corrigida 2026-11-07, TRIAGEM §5). Antes, a separação a baixa resolução cortou as duas peças à toa: TTFF com cordas 15,47/14,48, e a outra sem 4 cantos. Depois, as duas peças saem inteiras e plausíveis para peças da borda esquerda: TTFT e TBFB, com um F cada.
  - Fica `baixa` porque o F da #30 mede 16,39 mm (< 17).
  - Visualmente é claramente melhor. [V, visto]
- **S0003 (#18, #19, #24, #25).** É uma secção montada em L (fila de baixo + coluna da direita) da folha GT do canto BE. A #25 é um `is_cluster` que cobre a fila. A coluna estava partida em fragmentos antes e continua partida depois, de outra maneira (sem 4 cantos antes e depois, exceto a #24, que passa de FTFF lixo para sem 4 cantos).
  - Todas ficam `baixa` (honesto).
  - As quatro estão `descartada` no projeto, por isso não mexem em nada.
  - As vizinhas #21 e #23 (colocadas em (44,2) e (46,2)) ficam bit a bit iguais. [V]
- Nos 13 pares sem alteração, a partição já estava certa e ficou igual (IoU ≥ 0,98 com o registo antigo guardado). [V]

## 5. Testes

Em `tests/test_segmentation.py`, com `tests/synth.interlocked_scan`: verde do projeto, 300 dpi, saliência de A concêntrica com o encaixe de B, corpos a 1 mm, mais duas peças isoladas.
- Com 1 px de fresta: 2 peças com IoU 0,998 / 0,998 e nenhuma com F (conectividade).
- Com fresta 0: ambas `baixa` (a bacia sem linha escura corta mal a saliência, como se vê na figura sintética).
- Com peças afastadas: nada muda.
- `ingest_scan` propaga `contacto`.

Com o passo desligado, os dois primeiros testes falham (IoU 0,44 / 0,37). [V]

## 6. S0023 #3/#4 revisitado (2026-11-07)

Report R0001 do Tiago: «as peças 3 e 4 estão tão próximas que a segmentação as corta mal» (P0777 em (3,10), P0778 em (4,10)). Script: `tools/diagnostico/segmentacao/recorte.py` (`porta` = 27 folhas com o passo novo desligado/ligado; `indice` = detetores no índice). Figura: `contactos_s0023_antes_depois.jpg` (em cima o recorte do scan com os contornos antes/depois; ao meio a junta ×4; em baixo os recortes das duas peças antes/depois).

### 6.1 O que estava mal (visto no scan ×3 e na junta ×6)

- **P0778 levava a sombra da saliência da P0777.** A sombra quase preta debaixo da saliência (L\* 8 bits 0–20, 0,6–1,1 mm de espessura, 3,4 mm de comprido) estava dentro do contorno da P0778, mais a faixa verde-escura por baixo dela. É o «filamento escuro» no canto inferior esquerdo do recorte P0778. [V, visto]
- **P0777 levava uma cunha de halo da P0778.** Uma tira de 3 px a subir ao longo do halo do lado W da P0778 e um triângulo de ≈ 2 × 2 mm entre o topo da saliência e o lábio de cima da P0778, com a sombra desse lábio. É a «lasca» no canto superior direito do recorte P0777 e o «triângulo de fundo» já notado no §4. [V, visto]
- **O corte não estava fora do vale escuro por acaso.** A paisagem black-hat(L\*) faz da sombra fechada um planalto rodeado de um anel alto. Medido com a inundação a partir de cada núcleo, as duas chegam à sombra ao **mesmo nível** (mediana 1,29 a partir de cada um). Quem a leva é decidido pela ordem de chegada (empate); aqui ganhou a P0778, que entrou pelo seu halo liso. [V]
- **O «degrau» no lado W da P0778 é sobretudo a base da língua.** Fica um resto: o halo verde-escuro na metade de baixo do lado W tem 11–13 px (≈ 1,1 mm) até ao limiar, contra 7–9 px (≈ 0,7 mm) na metade de cima (perfis de L\*, b\* e distância ao papel em y = 130/150 contra 270/280). É o halo real da sombra projetada perto da junta; o passo novo não o mexe (§6.7). [V]

### 6.2 Porque a medida anterior não detetou

- **(i) Sem gémea colocada não houve comparação.** A célula gémea de (4,10) é (44,55), que estava vazia (só foto). Comparado agora com as gémeas propostas na TRIAGEM §3 (identidade física [NT]): `free_dist(P0778, P0425)` = **1,442 mm** e `free_dist(P0777, P0420)` = **1,714 mm**, contra o nível de gémea de 0,29–0,39 mm (E-sym) e ≥ 0,6 mm de uma não-gémea. A gémea teria detetado. Antes da correção as gémeas nem eram as peças mais parecidas do índice: as mais próximas eram P0461 (1,18) e P0876 (1,29). [V]
- **(ii) A métrica do verde é cega a isto.** O que a correção tira à P0778 (4,04 mm²) é 68 % quase preto (L\* CIE < 25, mediana 8,7) e só 14,9 % está à distância de papel (< 29,5). A cunha tirada à P0777 (3,09 mm²) tem 50,6 % de «verde» e já era limpa na vista. A métrica do verde só vê papel; uma mordidela (ou uma língua) de sombra não tem papel. [V]

### 6.3 Detetores, medidos no índice (908 peças com contorno, `recorte.py indice`)

**(a) Consistência do corte.** Os dois lados que nasceram da mesma linha de partição têm de ser complementares (T↔B, `side_complement`).
- **P0777 E ↔ P0778 W: RMS 3,758 mm**, |ΔL| 0,50 mm.
- **Referência:** as 950 juntas T↔B entre vizinhas colocadas no tabuleiro (pose `k` dos cantos). Mediana 1,124 mm, p90 1,435, p99 1,804. O máximo é precisamente P0777/P0778; a seguinte é P0218/P0223 (2,55, o prado comido de S0009, PRADO.md) e depois P0807/P0833 (2,17). [V]
- **Nos pares de contacto do índice:** os dois pares da bacia com 4 cantos dão S0020 P0651↔P0657 1,395 e S0023 3,758. Os grupos de S0003 não têm 4 cantos (descartadas). Os pares sem bacia (`conectividade`) não são encaixados: os lados frente a frente são T↔T ou estão a 8–36 mm, por isso (a) não se lhes aplica. [V]
- O |ΔL| não separa (0,50 contra p99 1,52).

**(b) Apêndices (fios, línguas, lascas).** Mede o maior componente que uma abertura por disco retira ao contorno cheio (diâmetro do invólucro convexo):

| raio da abertura | p50 | p95 | p99 | máx (sem S0023) | P0777 | P0778 |
|---|---|---|---|---|---|---|
| 0,3 mm | 0,32 | 0,52 | 0,65 | 1,45 (P0395) | 0,70 | 0,39 |
| 0,5 mm | 0,58 | 0,84 | 1,00 | 13,8 (P0395) | 1,12 | 0,58 |
| 0,8 mm | 0,93 | 1,22 | 1,46 | 14,5 (P0395) | **2,90** | **3,43** |

- A abertura de 0,3 mm pedida **não serve [F]**: a língua tem 0,6–1,1 mm de espessura e sobrevive-lhe (P0778 0,39 mm = mediana).
- Com 0,8 mm, P0778 e P0777 são a 2.ª e a 3.ª peça do índice. A 1.ª é **P0395** (S0013 #50, 14,5 mm): uma linha escura ao longo do lado de baixo, visível no recorte. É um defeito real que ninguém tinha reportado [V, visto]. Seguem-se P0064 (S0003, descartada) 2,33 e P0556 1,83 (um salpico claro no lado E).

*Índice vivo:* outros agentes acrescentaram peças durante a ronda. Uma segunda corrida de `recorte.py indice` no fim (958 peças, 970 juntas T↔B) dá os mesmos percentis em (b) e em (a): p50 1,124, p99 1,780, máximo P0777/P0778 3,758. P0218/P0223 já não aparece entre as piores. [V]

**(c) Degrau no perfil do lado.** Máximo da 2.ª diferença do perfil (64 pontos, mm) nos 3341 lados T/B: p50 0,416, p95 0,586, p99 0,678, máx 0,847. O lado de contacto da P0778 dá 0,628 e o da P0777 0,650: dentro da distribuição. **Não deteta [F]**: o perfil de 64 pontos alisa o degrau.

**Flag adotada em `segment_scan`: `suspeita_recorte`** (só marca, nunca muda contornos):
- `apendice`: (b) com raio 0,8 mm e comprimento > 2,0 mm (`_SUSPECT_SPUR_MM`, `_SUSPECT_SPUR_LEN_MM`). Fica acima do p99 do índice (1,46) e da peça seguinte sem queixa (1,83).
- `corte_de_contacto`: (a) num par `watershed` de exatamente 2 membros, com o lado frente a frente sem T↔B ou com RMS > 2,0 mm (`_SUSPECT_FACE_RMS_MM`, acima do p99 1,80 das juntas do tabuleiro).
- Em grupos maiores a membro mais próxima não é de certeza a que partilha o corte: na primeira corrida, os 6 membros de S0003 marcaram duas peças colocadas sem defeito (P0061, P0063), por isso ficam de fora.
- `ingest.py` ainda **não** copia a flag para `flags` (fora deste território): proposta de uma linha ao lado de `recuperado_mm2`.

### 6.4 A correção (`_CONTACT_TRIM`, em `_resolve_contact_group`, só na partição por bacia)

- **(1) Abertura dos espigões mais larga.** O raio passa de `_CONTACT_SPUR_MM` 0,5 para `_CONTACT_TRIM_MM` 0,8 mm.
  - Um disco de 1,6 mm de diâmetro retira a língua de sombra de 0,6–1,1 mm.
  - O pescoço de uma saliência, a parte real mais estreita de uma peça, tem ≥ 3 mm.
  - Os píxeis retirados vão, como antes, para a região mantida mais próxima: a sombra encostada à saliência volta à P0777, e um canto arredondado longe da vizinha volta ao dono.
- **(2) Aparar a junta.** Com a mesma abertura de 0,8 mm, o que cada membro perde a menos de `_CONTACT_TRIM_ZONE_MM` = 1,0 mm de outro membro fica sem dono (as cunhas e as tiras de halo partilhado), e o fecho final não o pode retomar.
  - A zona de 0,6 / 1,0 / 1,5 mm dá o mesmo resultado (gémea 0,618 / 0,615 / 0,614 mm na variante com o corte depois do fecho).
- **Variantes medidas em S0023** (`free_dist` à gémea P0777 / P0778; RMS (a)):

| variante | P0777 | P0778 | RMS (a) |
|---|---|---|---|
| espigão 0,5 mm (antes) | 1,714 | 1,442 | 3,758 |
| espigão 0,6 mm | 1,583 | 1,436 | 3,60 |
| espigão 0,7 mm | 1,156 | 1,423 | 3,22 |
| espigão 0,8 mm | 0,986 | 0,576 | 2,19 |
| espigão 0,5 mm + corte 0,8 mm | 0,914 | 0,868 | 2,30 |
| **espigão 0,8 mm + corte 0,8 mm (adotada)** | **0,591** | **0,426** | **1,157** |

- Não se mudaram os marcadores (transformada de distância dos núcleos) nem o corte pelo vale de L\* mínimo: a medida mostrou que o problema não é a linha do vale, mas o desempate do planalto e as tiras finas que ficam. [V]
- `_CONTACT_TRIM = False` reproduz bit a bit o código anterior: S0023 59/59 contornos iguais ao índice, e as 27 folhas idênticas à corrida «antes». [V]

### 6.5 Antes → depois em S0023 #3/#4 [V]

| | classe | cordas (mm) | área (mm²) | gémea `free_dist` | (a) RMS | (b) 0,8 mm |
|---|---|---|---|---|---|---|
| P0777 antes | BTTT | 15,94 / 18,25 / 17,22 / 18,80 | 398,7 | 1,714 (P0420) | 3,758 | 2,90 |
| P0777 depois | BTTT | 15,92 / 18,29 / 17,17 / 18,88 | 399,2 | **0,591** | **1,157** | 0,98 |
| P0778 antes | BBTT | 18,41 / 18,54 / 16,44 / 17,94 | 369,1 | 1,442 (P0425) | 3,758 | 3,43 |
| P0778 depois | BBTT | 18,36 / 18,66 / 16,34 / 17,97 | 367,2 | **0,426** | **1,157** | 0,62 |

- Depois da correção, a peça mais parecida de todo o índice é a gémea proposta: P0420 a 0,591 (a seguinte a 0,999) e P0425 a 0,426 (a seguinte a 0,722). Isto confirma pela forma as hipóteses da TRIAGEM §3 para (45,55) e (44,55); a identidade física fica [NT].
- P0778 fica ao nível de gémea. P0777 fica em 0,59: o resíduo está espalhado pelo contorno, sem picos locais (sobreposição alinhada vista), possivelmente da pose oposta (+0,1 mm em E-sym) [NT].
- **Na figura** vê-se:
  - a sombra debaixo da saliência passa a ser da P0777, como a sombra dos seus outros lados de baixo;
  - a língua e a cunha desaparecem dos recortes;
  - fica o halo de ≈ 1 mm na metade de baixo do lado W da P0778 (§6.1).

### 6.6 Porta [V]

- **E-sym:** os contornos das 3 folhas (A1, A2, B2) são bit a bit iguais com o passo ligado e desligado (sem grupos de contacto), por isso os números são os mesmos. O teste `slow` passa.
- **27 folhas:** contagem e numeração iguais em todas, antes contra depois e contra o projeto. Tempo total 109,8 → 109,9 s.
- **Contornos que mudam:**
  - S0023 #3/#4.
  - **S0020 #24/#30** (P0651 (44,1), P0657 (45,1)), para melhor:
    - (a) 1,395 → 1,193;
    - gémea P0233 0,567 → 0,554 e P0234 0,511 → 0,366;
    - áreas −1,9 / −0,8 mm²;
    - cordas a ≤ 0,07 mm.
  - **S0003** idx 17/18/23/24 (P0058, P0059, P0064, P0065, todas `descartada`): apêndice (b) 1,72 / 1,27 / 2,33 / 1,46 → 0,93 / 0,65 / 1,10 / 0,81. Continuam sem forma válida (P0064 passa a ter 4 cantos, BBBT com cordas de 21 mm, lixo como antes). As colocadas do grupo, P0061 e P0063, ficam bit a bit iguais.
  - Nenhuma outra peça muda.
- **Flags `suspeita_recorte` depois:** S0013 P0395 (`apendice` 14,5 mm, defeito real) e um fragmento < 150 mm² de S0024 (idx 10, 2,18 mm, não entra no índice). Antes da correção também marcava P0777/P0778 (`apendice` + `corte_de_contacto` 3,76) e P0064 (2,33).
- **Testes** (`tests/test_segmentation.py`):
  - `test_contact_trim_returns_shadow_tongue_to_the_tab`: sintético `tests/synth.contact_tongue_labels`, sombra de 1,2 mm debaixo da saliência mais um fio de 0,2 × 4 mm, entregues à vizinha. Com o passo desligado **falha**: 6,69 de 6,86 mm² ficam na vizinha. Com o passo ligado passa (≤ 25 % na vizinha, ≥ 60 % na dona, corpos intactos).
  - `test_contact_trim_switch_off_is_previous_spur_step`.
  - `test_appendage_measures_thread_not_corners`.
  - `test_segment_scan_s0023_pair_without_tongue` (`slow`, folha real). Com o passo desligado **falha** (flag `apendice` 2,90 + `corte_de_contacto` 3,76).
- **O teste sintético é ao nível dos rótulos, não do scan.** Seis variantes de cena sintética completa (meia-lua de sombra, halo em rampa, orla clara, fresta 0–0,2 mm, boca virada à saliência) não reproduziram a falha: ou a separação a baixa resolução já estava certa e a nova partição não era adotada, ou fundia as duas peças. Daí o teste sobre `_contact_trim`, mais a folha real como teste `slow`.
- **O fio de 0,2 mm pedido sozinho não chega ao passo de contacto:** a abertura de 0,42 mm (quadrado de 5 px) do limiar retira-o antes, porque o quadrado não cabe num fio de 2 px. No teste vai junto com a língua.

### 6.7 Fica por resolver

- O halo de ≈ 1,1 mm na metade de baixo do lado W da P0778 (0,4 mm mais largo do que na metade de cima) é a sombra projetada real perto da junta. Corrigi-lo pede o modelo de sombra adiado (M3). [NT]
- `suspeita_recorte` não chega ainda ao índice (falta a linha em `ingest.py`). O rebuild do índice (P0777/P0778 novas, S0020 P0651/P0657) fica para o gestor.
- Os limiares novos (0,8 mm, 1,0 mm, 2,0 mm, 2,0 mm) foram fixados com este índice (2 pares da bacia com 4 cantos). Não foram validados noutro conjunto. [NT]

## 7. Limites (não resolvidos)

- **Par totalmente encaixado** (corpos encostados, `body_gap_mm=0` no sintético). `segment_pieces` funde-o numa só peça; como o passo nunca cria peças, continua a sair 1 objeto (defeito conhecido "pares encaixados saem como uma peça"). [V no sintético]
- **Contacto sem fresta e sem sombra entre peças da mesma cor.** A bacia não tem onde se apoiar; o resultado vem marcado `baixa`, não corrigido. [V no sintético]
- Os limiares (2 mm de núcleo, 1,5 mm de black-hat, 0,5 mm de espícula, 95 % de faixa) foram fixados a partir deste conjunto (7 pares alterados) e não foram validados noutro. [NT]
