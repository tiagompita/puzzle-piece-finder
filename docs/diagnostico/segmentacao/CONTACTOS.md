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
  - Resta um pequeno triângulo de fundo (≈ 1 mm) entre o topo da saliência e o lábio da #4, incluído no contorno da #3. [V, visto]
- **S0020 #24/#30** (P0651 colocada em (45,1), P0657 em (44,1)). Antes, a separação a baixa resolução cortou as duas peças à toa: TTFF com cordas 15,47/14,48, e a outra sem 4 cantos. Depois, as duas peças saem inteiras e plausíveis para peças da borda esquerda: TTFT e TBFB, com um F cada.
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

## 6. Limites (não resolvidos)

- **Par totalmente encaixado** (corpos encostados, `body_gap_mm=0` no sintético). `segment_pieces` funde-o numa só peça; como o passo nunca cria peças, continua a sair 1 objeto (defeito conhecido "pares encaixados saem como uma peça"). [V no sintético]
- **Contacto sem fresta e sem sombra entre peças da mesma cor.** A bacia não tem onde se apoiar; o resultado vem marcado `baixa`, não corrigido. [V no sintético]
- Os limiares (2 mm de núcleo, 1,5 mm de black-hat, 0,5 mm de espícula, 95 % de faixa) foram fixados a partir deste conjunto (7 pares alterados) e não foram validados noutro. [NT]
