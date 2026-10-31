# E-real: célula das linhas de corte → gémeo entre as soltas (2026-10-31)

Script: `tools/diagnostico/gemeos/ereal.py` (≈ 36 s; usa `seccao.py` como biblioteca, `segment_scan` de `src/` e `$PPF_SCRATCH/gemeos/esym.pkl`). Não houve alterações em `src/`, `tests/` nem em `seccao.py`. Números completos em `results.json` → chave `ereal`; GT legível por máquina em `ereal_gt.json`.
Etiquetas: **[V]** verificado (com n e fonte), **[NT]** não testado, **[F]** testado e falhou. Métrica principal: free (`esym.free_vec` + `dist.free_dist`, mm RMS); corner (`shape_dist`) como controlo.

## Resumo

1. **A cadeia real funciona quando a célula é boa, mas o critério do M10 não fecha: veredicto inconclusivo [V, n = 25].** UL (céu) → 28 soltas BD: top-1 **22/25 = 88 %** com filtro de classe (pool de 28 e de 68). Nas 21 células UL interiores ao bloco o top-1 é **20/21**. A margem falha: em 9/25 consultas fica abaixo de 1,5 (pool de 68 com classe). Não chega ao "passa" (≥ 95 % e margem ≥ 1,5) nem ao "mata" (< 80 %).
2. **As falhas vêm da extração das células, não da forma [V].** As 3 falhas são células UL más:
   - 2 têm um lado no contorno do bloco, (2,7) e (5,7);
   - 1 está na nuvem, (5,5), com a classe errada.
3. **O desvio da modalidade é isotrópico e não é sombra [V, n = 25].** A silhueta de `segment_scan` fica ≈ **+0,48 mm para fora** da célula da linha de corte nos quatro lados (escala 1,048). Por isso o RMS gémeo célula↔silhueta é 0,76 mm (o dobro do E-sym). A assimetria do lado da sombra é pequena: baixo − cima 0,09 mm e esq − dir 0,05 mm.
   - **Decisão: o modelo de sombra do M3 continua adiado.**
   - **Item novo para o M10:** calibrar o desvio isotrópico célula↔silhueta. Com essa correção a margem melhora: < 1,5 em 3/25 em vez de 9/25, mas esta estimativa é circular.
4. **A extração das linhas de corte na relva (bloco BD) falha [F].**
   - O método do `seccao.py` (vale de L\*) dá 1–3/41.
   - A minha variante `branco` dá 26–29/41 por área, mas só 2 e 1 células passam o controlo de qualidade sem GT.
   - Frente contra rot180: RMS mediano 3,0 mm, contra 0,12 mm no céu.
   - Por isso (a), (c1-própria) e (c2) medem a falha da extração, não a forma. O alvo do M3 de ≥ 90 % sem prior está longe neste tipo de arte.

## 1. Dados e GT

- **Bloco BD**:
  - frente: `gt_canto_BD_frente_300dpi.jpg`, canto em baixo à direita;
  - re-scan rodado 180°: `..._rot180.jpg`;
  - coordenadas (k, j): k = linha a contar de baixo, j = coluna a contar da direita; (l, c) = (48 − k, 65 − j); o gémeo de BD(k, j) é a célula UL (k, j);
  - 41 casas: k 1–5 × j 1–7, k = 6 só j ≤ 5, k = 7 só j = 1.
- **Rotação para a extração.** A frente roda 90° no sentido horário e a rot180 90° no anti-horário, para pôr o canto em baixo à esquerda. Fica k = iu + 1 e j = iw + 1.
  - **Verificado [V]:** a ocupação da grelha dá exatamente as 41 casas esperadas nos 2 scans (o padrão é assimétrico, por isso um engano de eixo seria detetado).
  - Os lados retos detetados são 'left' e 'bottom' nos 2 scans. O lado de baixo (borda j = 1) só tem suporte de 0,26–0,28 na reta: a borda montada não é perfeitamente reta.
- **Soltas.** `segment_scan` em `gt_canto_BD_soltas_300dpi.jpg` devolve **28 peças, 0 clusters, 0 junto ao bordo**. A faixa em L não aparece de todo na saída; não houve nada a excluir [V].
- **Grelha das soltas.** Filas por quebras no y do centro; colunas contadas da DIREITA; j = r + 1, k = s + 1. Verificações automáticas que passaram [V]:
  - filas [5, 5, 5, 5, 4, 4];
  - as 4 peças das filas 5–6 alinham com as colunas s = 1..4 (x 1890 / 1488 / 1086 / 682; s = 5 está em 295);
  - as 28 têm 4 cantos e nenhum lado F;
  - a faixa do caminho está na coluna k = 6:
    - cinzento claro (L\* > 55, C\* < 22): 0,085 / 0,117 / 0,205 nas linhas j = 3, 4, 5, contra um máximo de 0,024 nas outras;
    - preto acromático máximo em (6,2): 0,296 contra 0,222.
  - Nota: o critério "L\* mediano mais baixo" do pedido está ao contrário. As peças k = 6 têm L\* 46–58 contra 36 nas outras, porque o caminho é mais claro do que a relva. A fração de C\* < 15 também não serve: as sombras escuras da relva são acromáticas.
- **Confirmação independente da disposição [V].** As soltas dão top-1 20/21 contra as células UL interiores, e a classe topológica concorda em 22/24. Com uma GT trocada o top-1 seria ao acaso.
- **Secção UL.** Re-extraída com o código do `seccao.py` e o passo do `seccao_celulas.json`. Reproduz o JSON: 40 células, as mesmas casas, |Δárea| ≤ 5 mm² [V].
- **Pares testáveis:**
  - (a): 38 casas em UL ∩ BD, das quais 26 têm célula nas duas secções;
  - (b): 25 das 28 soltas;
  - (c1): 28 casas, das quais 20 com célula BD;
  - (c2): 41 casas, das quais 25 com célula nos dois scans.

## 2. Extração das linhas de corte

Passo usado: **18,39 × 18,97 mm**, o da secção UL, medido no céu e confirmado por centróides no SECCAO.md; é o mesmo puzzle. Medido no BD por autocorrelação:
- vale de L\*: 17,55 × 18,84 (frente) e 17,47 × 19,72 (rot180), **não fiável**: a textura domina;
- `branco`: 18,02 × 19,25 e 18,29 × 18,97;
- na UL: 18,41 × 18,96 (L\*) e 18,33 × 19,05 (`branco`).

Células recuperadas (exatamente uma célula válida na casa):

| scan | hessiana / histerese (sem prior) | hessiana / watershed (prior) | branco / histerese (sem prior) | branco / watershed (prior) | passam o QC |
|---|---|---|---|---|---|
| UL frente 300 (/44) | 30 | **40** (= JSON) | 10 | 39 | 32/40 |
| BD frente (/41) | 2 | 1 | 0 | **26** | **2**/26 |
| BD rot180 (/41) | 3 | 2 | 0 | **29** | **1**/29 |

[V, `results.json` → `ereal.extracao`, `ereal.celulas`.]

- **`hessiana/*`** é o método do `seccao.py`, sem alterações.
- **`branco`** é meu:
  - resposta: crista clara da Hessiana de W = L\* − 1,5·C\*, com σ = 0,15 mm. Ao ver a relva a 2,5×, o corte aparece como uma orla branca-acinzentada acromática ao lado de um vale preto, enquanto a relva é saturada;
  - `branco/watershed` = o watershed do `seccao.py` **sem** lhe somar as linhas da histerese. Na relva a histerese marca a textura e parte todas as células em fragmentos.
- **Células "até à linha central"** (minha alteração, usada em todas as comparações). As células do `seccao.py` são componentes do complemento das linhas dentro do bloco erodido 1 mm, por isso ficam ≈ 0,5 mm para dentro em cada lado. Cada píxel do bloco fora das componentes (linha ou orla de 1 mm) vai para a componente mais próxima (Voronoi, até 1,4 mm), e a fronteira fica no eixo médio da linha.
  - Efeito em (b): gémeo de 1,20 para **0,76 mm**, top-1 de 17 para 22/25.
  - Nas soltas: corda UL 17,96 × 17,44 → 18,53 × 17,94 mm, contra 19,09 × 18,45 nas silhuetas.
- **Controlo de qualidade (QC) sem GT:**
  - 4 cantos;
  - nº de lados F = nº de lados retos esperados;
  - rugosidade ≤ p95 das células UL (1,099);
  - área em [0,85; 1,2] × a mediana UL (335 mm²).
  - Rugosidade mediana: UL 1,065; BD 1,115 / 1,117.

**O que vi nas figuras:**
- `ereal_bd_linhas_frente.jpg` e `_rot180.jpg`:
  - na linha `hessiana` a resposta é textura por todo o lado e as células são manchas amarelas (fragmentos);
  - na linha `branco` a resposta mostra os cortes nítidos e quase sem textura;
  - o watershed dá peças com patilhas no centro do bloco, por exemplo (4,2), (5,2), (4,3) e (5,3), que seguem o corte ao píxel (vi um recorte a 1:1). Muitas outras células seguem o corte em 2–3 lados e atravessam a peça vizinha onde a linha falha.
- Uma grelha desenhada com o canto e o passo cai em cima dos cortes reais, por isso o prior está certo. Uma tentativa de deslocar a grelha pelo mapa de distâncias às linhas piorou as coisas e foi abandonada.
- **Conclusão [F]:** na relva, nem o vale de L\* nem a minha crista `branco` dão células fiáveis. Sem prior: 0–3/41. Com prior: 1–2 células passam o QC.

## 3. Tabelas

### (a) secção ↔ secção: UL(l, c) contra BD(k = l, j = c), ambas das linhas de corte

| subconjunto | n | gémeo free mediana / p90 / máx (mm) | não-gémeo mais próximo, mediana | top-1 UL→BD / BD→UL | margem < 1,5 | classe igual |
|---|---|---|---|---|---|---|
| todas | 26 | 2,93 / 3,63 / 5,35 | 1,97 | 3/26 / 5/26 | 24 | 8/19 |
| borda | 6 | 3,14 / 3,45 / 3,56 | 2,09 | 0/6 / 1/6 | 6 | 0/1 |
| interior | 20 | 2,83 / 3,71 / 5,35 | 1,75 | 3/20 / 4/20 | 18 | 8/18 |
| só células BD com QC | 2 | 0,42 / — / 1,88 | 2,04 | 1/2 / 2/2 | 1 | 2/2 |

- NN mútuo: 9, dos quais 3 corretos.
- **[F] como medida do gémeo:** o resultado reflete as células BD más.
- Onde as duas células são boas, o gémeo célula↔célula dá **0,42 mm em (4,2) e 0,55 mm em (5,2)**. É a ordem de grandeza do E-sym, porque não há diferença de modalidade (`ereal_pares_seccao_seccao.png`). Com n = 2 é só indicativo.

### (b) secção UL ↔ soltas BD (= E-real)

Mesmo conjunto de consultas em todas as linhas (n = 25, salvo indicação): gémeo free mediana **0,76**, p90 2,57, máx 3,43 mm.

| variante | n | top-1 | margem mín / mediana | margem < 1,5 |
|---|---|---|---|---|
| pool de 28, sem classe | 25 | **22/25** | 0,56 / 1,54 | 12 |
| pool de 28, com classe | 25 | **22/25** (3 falham pela classe) | 1,06 / 1,58 | 9 |
| pool de 68 (+ 40 peças do E-sym), sem classe | 25 | 21/25 | 0,56 / 1,54 | 12 |
| pool de 68, com classe | 25 | **22/25** | 1,06 / 1,58 | 9 |
| inverso solta → 40 células UL | 25 | 21/25 (com classe 21/25) | 0,32 / 1,56 | 11 |
| corner, pool de 28 (controlo) | 25 | 22/25 (gémeo mediana 0,78) | 0,55 / 1,43 | 13 |
| células UL dentro do bloco (sem lado no contorno) | 21 | **20/21** (p90 0,93) | 0,56 / 1,61 | 8 |
| células UL no contorno do bloco (coluna c = 7) | 4 | 2/4 (gémeo mediana 2,57) | 0,76 / 0,96 | 4 |
| consultas UL que passam o QC, pool de 68 com classe | 22 | **21/22** (p90 1,32) | 1,06 / 1,61 | 8 |
| células "cruas" do `seccao.py` (sem eixo médio), pool de 28 | 25 | 17/25 (gémeo 1,20) | 0,59 / 1,06 | 23 |
| células UL sem prior (hessiana/histerese + eixo médio), pool de 28 | 23 | 22/23 (gémeo 0,75, p90 0,83, máx 0,91) | 0,93 / 1,60 | 7 |
| escala × 1,048 nas células (circular, ver c1), pool de 68 com classe | 25 | 22/25 (gémeo 0,56) | — / 2,08 | **3** |

- Fonte: [V] `results.json` → `ereal.b_seccao_soltas`.
- Classe topológica do gémeo: igual em 22/24.
- Por lado (24 pares, lados alinhados pelo `best_k` dos cantos): |ΔL| mediana 0,42 mm, p90 0,99; tipo de lado igual em 94/96.
- **Falhas:**
  - (2,7) e (4,7) (esta só no pool de 68): o lado direito da célula está no contorno do bloco UL e sai errado;
  - (5,5): célula da nuvem com uma fronteira a atravessar a peça (classe BBTT contra BTTT);
  - (5,7): contorno e nuvem, sem cantos.
- O pior não-gémeo das 40 peças do E-sym só entra no top-1 em (4,7). Com o filtro de classe, as peças de borda saem todas.
- **As células sem prior** (só as que fecham) são as mais limpas: p90 0,83 mm, top-1 22/23. A conclusão não muda: top-1 ≈ 90–96 %, com a margem abaixo de 1,5 em ≈ 30 % das consultas.

### (c1) célula da linha de corte vs silhueta (`segment_scan`)

| comparação | n | free mediana / p90 / máx | escala silhueta/célula (mediana) | RMS depois da escala | desvio por lado (mediana, mm): baixo / cima / esq / dir | assimetria baixo − cima / esq − dir (mediana, p90) | ΔL com sinal por lado: baixo / cima / esq / dir |
|---|---|---|---|---|---|---|---|
| **solta vs célula UL gémea (todas)** | 25 | 0,76 / 2,57 / 3,43 | **1,048** | 0,55 | **+0,52 / +0,42 / +0,51 / +0,47** | **+0,09 (0,20) / +0,05 (0,20)** | +0,56 / +0,13 / +0,37 / +0,38 |
| idem, célula dentro do bloco | 21 | 0,75 / 0,93 / 3,40 | 1,048 | 0,54 | +0,51 / +0,42 / +0,51 / +0,45 | +0,09 / +0,05 | +0,54 / +0,06 / +0,36 / +0,38 |
| solta vs a sua célula BD (relva) | 20 | 2,81 / 3,62 / 5,19 | 1,027 | 2,68 | +0,58 / +0,67 / +0,70 / +0,53 | +0,11 / +0,20 (p90 ≈ 1) | — |
| idem, só células BD com QC | 2 | 1,52 / — / 2,15 | 1,068 | 1,33 | — | — | — |

- Fonte: [V] `ereal.c1_celula_vs_silhueta`.
- Desvio = média, por lado da silhueta, da distância com sinal à célula alinhada sem escala (+ = silhueta fora). A orientação de cada lado é a do scanner das soltas. Lados da sombra: baixo e esquerda.
- **A medida própria (célula BD) não serve [F]:** é dominada pelas células más da relva. Por isso o viés mede-se pelo gémeo UL, que é o mesmo corte (E-sym: gémeo 0,29–0,39 mm).
- **Desvio isotrópico de ≈ +0,48 mm [V].** A silhueta envolve a célula a distância quase constante nos 4 lados (`ereal_vies_silhueta.png`). A área confirma:
  - silhueta: mediana ≈ 396 mm²;
  - passo × passo: 349 mm² (uma peça tem, em média, a área da casa);
  - célula UL: 335 mm²;
  - ou seja, ≈ +0,43 mm de silhueta para fora e ≈ 0,13 mm de célula para dentro, num perímetro de ≈ 110 mm.
- A causa da parte da silhueta (orla escura do cartão, desfoque do limiar 28, sombra dos dois lados?) não foi testada [NT].
- **t calibrado** para a modalidade célula↔silhueta:
  - p95 do RMS gémeo: 3,23 mm (todas) e 1,32 mm (dentro do bloco), dominado pelas células más;
  - p90 dentro do bloco: 0,93 mm, contra o t95 de 0,507 mm do E-sym;
  - calibrado nos próprios pares de teste, por isso circular: só indicativo.
- **ΔL baixo +0,56 contra cima +0,13 (n = 24).** A diferença não é explicada por uma sombra só em baixo/esquerda, que alongaria por igual as cordas de cima e de baixo. Está confundida com a direção da extração no scan UL: as soltas estão todas na mesma rotação relativa à UL. Fica [NT].

### (c2) ruído das linhas de corte com mudança de pose (BD frente vs rot180, mesma casa)

| método | n nos dois | free mediana / p90 / máx (mm) | classe igual |
|---|---|---|---|
| hessiana / histerese | 2 | 3,57 / 4,56 / 4,80 | 1/2 |
| hessiana / watershed | 1 | 1,37 | 1/1 |
| branco / histerese | 0 | — | — |
| branco / watershed | 25 | 3,15 / 3,81 / 5,52 | 3/16 |
| branco / watershed + eixo médio | 25 | 3,02 / 3,87 / 5,48 | 1/17 |

- Fonte: [V] `ereal.c2_frente_vs_rot180`.
- No céu, o SECCAO.md dá 0,12 mm (frente 300 vs 600, mesma pose).
- **[F]:** na relva as duas extrações discordam célula a célula. O ruído aqui é o erro da extração, não o ruído de medida da linha.

## 4. Veredicto contra o critério do M10 (E-real)

- **Critério:** top-1 ≥ 95 % das testáveis e margem ≥ 1,5 → passa; top-1 < 80 % → mata.
- **Resultado: inconclusivo [V, n = 25].**
  - top-1 = 88 % (22/25, com filtro de classe, pools de 28 e de 68);
  - margem < 1,5 em 9/25.
- **Leitura:**
  - **A cadeia de forma está viável.** Com células boas o gémeo sai em 20/21 (dentro do bloco) e em 21/22 (consultas com QC, 95,5 %).
  - **A margem é o problema.** O RMS gémeo célula↔silhueta (0,76) é o dobro do silhueta↔silhueta (0,38) por causa do desvio isotrópico de 0,48 mm. O não-gémeo mais próximo (mediana 1,31) não se afasta na mesma proporção.
  - Uma correção da modalidade (escala 1,048 ou dilatação de ≈ 0,45 mm da célula) baixa o gémeo para 0,56 e deixa a margem < 1,5 em 3/25 [V, mas estimada nos mesmos pares: circular].
- **O que falta para fechar o M10:**
  1. extração de células fiável também no contorno do bloco e na nuvem;
  2. calibrar o desvio célula↔silhueta noutra secção e testar aqui;
  3. o desempate pela imagem, que é obrigatório e não foi testado aqui [NT].

## 5. Decisão sobre o modelo de sombra (regra combinada)

- **Regra:** se o viés da sombra em (c1) for sistemático acima de ≈ 0,2 mm, ou baixar a margem de (b) para menos de 1,5, o modelo de sombra do M3 volta à agenda; senão continua adiado.
- **Decisão: continua adiado.**
  - A parte assimétrica (lados da sombra contra os opostos) é +0,09 mm (baixo − cima) e +0,05 mm (esq − dir), com p90 0,20 (n = 25, via gémeo).
  - A margem mediana de (b) é 1,58 (pool de 68 com classe).
- **Mas há um desvio de modalidade que não é sombra:** +0,48 mm isotrópico. Esse sim baixa a margem em ≈ 1/3 das consultas. O remédio não é o modelo de sombra (que atua só nos lados de baixo/esquerda); é uma calibração célula↔silhueta no `find_twin` (M10), com dilatação ou escala medida noutra secção [NT].
- **Ressalva:** a assimetria está confundida com o viés de direção da extração UL (ver c1). Se os dois se cancelassem exatamente, a sombra real seria maior [NT, improvável mas não excluído].

## 6. Figuras (todas vistas)

| figura | o que mostra / o que vi |
|---|---|
| `ereal_bd_linhas_frente.jpg`, `ereal_bd_linhas_rot180.jpg` | Resposta e células (k, j) dos 2 métodos × sem/com prior, na orientação do ficheiro. Hessiana: textura por todo o lado, fragmentos. Branco: os cortes veem-se nítidos e o watershed dá peças no centro; muitas células atravessam a vizinha onde a linha falha. |
| `ereal_soltas__contours.jpg` | 28 contornos amarelos justos às peças, com rótulos BD(k, j), lc(l, c) e classe. A faixa em L não é segmentada. A coluna da esquerda (k = 6) tem a faixa cinzenta e preta do caminho. |
| `ereal_pares_seccao_solta.png` | 25 pares: nas boas, a silhueta (azul) envolve a célula (vermelho) a distância constante. Falhas: (2,7) e (4,7), lado do contorno errado; (5,5) e (5,7), fronteira a atravessar a peça na nuvem; (3,7) e (6,3), patilha cortada (mesmo assim top-1). |
| `ereal_pares_seccao_seccao.png` | 26 pares: (4,2) 0,42 e (5,2) 0,55 mm sobrepõem-se; a maioria das células BD tem lados errantes. |
| `ereal_vies_silhueta.png` | Solta vs célula UL gémea no referencial do scanner, lados da sombra a preto. Desvios de +0,4 a +0,6 mm nos 4 lados; os lados da sombra não estão visivelmente mais para fora. |
| `ereal_vies_silhueta_propria.png` | Solta vs a sua própria célula BD: células más da relva (só controlo). |
| `ereal_histogramas.png` | (a) gémeo ≈ não-gémeo (células BD más); (b) gémeo 0,6–0,9 separado da maioria dos não-gémeos, com cauda das células más; (c) c1 própria e c2 ≥ 1,9 mm, c1 via gémeo 0,6–0,9. |
| `ereal_matriz.png` | (b) diagonal clara do gémeo; (a) e (c1) dominadas por "atratores" ((4,2), (5,2)). A escala de cor satura a 2 mm. |

## 7. Limites e o que NÃO foi verificado

- **A relva é o pior caso para as linhas de corte e falhou**, por isso (a), (c1-própria) e (c2) não medem o que se queria. O céu (UL) funciona.
- n pequeno: 25 consultas e 28 soltas; pool de 68 (as 40 do E-sym são de borda e o filtro de classe tira-as); UL com 40/44 células; 25/28 testáveis.
- As células usadas são watershed com prior, mais o meu "eixo médio". As células cruas do `seccao_celulas.json` dão um resultado pior (17/25).
- No BD usa-se o passo da UL. A autocorrelação no BD com o vale de L\* não é fiável.
- A escala 1,048 e o t da modalidade foram estimados nos próprios pares de (b): circular [NT fora da amostra].
- Não testado [NT]: o desempate pela imagem (obrigatório no M10); a causa do desvio isotrópico de 0,48 mm; um detetor de cortes para arte texturada; a fusão frente + rot180; células no contorno do bloco feitas a partir da silhueta com o modelo da patilha; `pytest` (não houve alterações em `src/` nem em `tests/`).

## Reprodução

```powershell
$env:PPF_SCRATCH = "C:\...\scratchpad"; $env:PYTHONIOENCODING = "utf-8"   # precisa de gemeos/esym.pkl (esym.py)
python tools/diagnostico/gemeos/ereal.py   # ≈ 36 s (OpenCV 4.11)
```
