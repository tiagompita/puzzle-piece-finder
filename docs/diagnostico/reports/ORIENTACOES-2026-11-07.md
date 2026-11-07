# Orientações P0083 / P0333, âncoras da coluna 55 e de (44,37), bloco (1..3, 32..33) — 2026-11-07

Medido em cópias de `projects/alpes` (log 2076 linhas, `git status` limpo): `alpes_o` (B + C, pela ordem), `alpes_o2` (alternativas de P0333) e `alpes_o3` (ensaio da sequência recomendada, sem P0333, com reconsulta). **Nada foi escrito em `projects/alpes`**: P0333 falhou o critério de imagem de B. A regra da tarefa era parar nesse caso (ver §5).

- Script: `tools/diagnostico/reports/orientacoes.py` (`measure`, `view`, `fig`, `block`, `swap`). Usa as funções de `triagem_r3.py` para a imagem na junta.
- Números: `ORIENTACOES-2026-11-07.json`. Figura: `ORIENTACOES-2026-11-07.jpg`.
- **Pose:** `render.register_piece(image=False)`, a pose da GUI. O `k` dos cantos dá o lado virado para cada direção.
- **Lados:** `legacy.side_compat`. Passa com T↔B, RMS ≤ 1,6 mm e |ΔL| ≤ 2,0 mm.
- **Folga:** `render.seam_gaps`. Positivo = abertura, negativo = sobreposição.
- **ΔE junta:** dE Lab mediano nas faixas de 0,3–1,3 mm de cada lado da junta. Referência das 954 juntas da triagem: p50 21, p90 50. É fraco em relva.
- **Imagem da célula:** `locate.de_cell` (ΔE / NCC de L*) na pose e nas outras 3 rotações.
- **Rotações:** +90 é no sentido dos ponteiros no ecrã, como `theta_deg`.

## 1. B — P0083 (44,60) e P0333 (6,22)

### P0083, R0024: `--unplace` + `--cell 44 60 --theta 175.21 --origin gt` (+90°)

| lado | vizinha | ANTES (θ 85,2, k 2) | DEPOIS (θ 175,2, k 3) |
|---|---|---|---|
| N | P0082 | B↔T, RMS 1,83 ✗, ΔL 1,25, folga −0,91 | B↔T, RMS 1,04 ✓, ΔL 0,58, folga −0,34 |
| E | P0078 | **T↔T** ✗, folga −2,34 | B↔T, RMS 1,77 ✗ (rms), ΔL 0,11, folga −0,46 |
| S | P0084 | T↔B, RMS 1,26, ΔL 2,52 ✗ (dl), folga +0,13 | T↔B, RMS 1,28 ✓, ΔL 1,25, folga −0,19 |
| W | P0087 | **B↔B** ✗, folga +2,43 | T↔B, RMS 1,35 ✓, ΔL 0,50, folga −0,07 |
| total | | T↔B 2/4, passam 0/4 | **T↔B 4/4**, passam 3/4 |

| rotação face à pose | ANTES ΔE / NCC | DEPOIS ΔE / NCC |
|---|---|---|
| 0 | 17,18 / −0,02 | **14,35 / 0,70** |
| +90 | **14,33 / 0,70** | 16,86 / 0,03 |
| 180 | 16,83 / 0,03 | 17,36 / 0,07 |
| −90 | 17,35 / 0,07 | 17,19 / −0,02 |

- O sentido medido coincide com o do Tiago e com `consistency`: +90° a partir de θ 85,21.
- **Depois: 4/4 T↔B e NCC máxima na pose nova [V].** O lado E falha só por RMS (1,77 > 1,6). Já estava previsto na triagem.
- `python -m src.consistency --pieces P0083 P0082 P0078 P0084 P0087`: 0 suspeitas **[V]**.
- ΔE na junta (N/E/S/W): antes 20,7 / 22,4 / 19,0 / 23,3; depois 26,0 / 37,8 / 10,8 / 15,1. É relva texturada: não discrimina.

### P0333, R0010: `--unanchor G0030` + `--anchor G0030 6 22 --rot 90` (−90°)

| âncora (rotação face a hoje) | N com P0332 | E com P0327 | NCC (ΔE) na pose | ΔE junta N / E |
|---|---|---|---|---|
| rot 180 (hoje) | **B↔B**, folga +2,05 | **T↔T**, folga −1,76 | 0,08 (9,17) | 24,1 / 32,4 |
| **rot 90 (−90°)** | T↔B, RMS 1,07 ✓, ΔL 0,38, folga +0,04 | B↔T, RMS 1,68 ✗ (rms), folga −0,26 | **0,06** (9,60) | 13,2 / 58,2 |
| rot 270 (+90°) | **B↔B**, folga +2,75 | B↔T, RMS 1,68 ✗, folga −0,30 | **0,29** (10,40) | 11,0 / 27,5 |
| rot 0 (180°) | **B↔B**, folga +1,83 | B↔T, RMS 1,33 ✓, folga −0,10 | 0,02 (10,34) | 9,4 / 18,4 |

- **Forma:** só −90° põe os dois lados em T↔B **[V]**. Os lados S e W estão livres; 2/2 é o máximo possível.
- `consistency` depois da −90°: 0 suspeitas em P0333, P0332 e P0327 **[V]**.
- **Imagem:** a NCC máxima (0,29) cai a +90°, que tem um B↔B no N. À −90°, a escolhida pela forma, a NCC é 0,06.
- **Conclusão: o critério «NCC máxima nessa rotação» falha [F].** Pela regra da tarefa, P0333 não se escreve no projeto.
- O ΔE das 4 rotações cobre só 9,2–10,4: o céu não tem poder de decisão.
- A arte de (6,22) tem uma nuvem cinzenta no quarto inferior direito. P0333 é azul-claro uniforme em todas as poses (figura). A identidade de P0333 em (6,22) continua **[NT]**: a gémea (42,43) está vazia.

### Figura `ORIENTACOES-2026-11-07.jpg` (vista)

Vistas 3 × 3 a 300 dpi: arte a 0,34, peças registadas sem imagem, contorno da peça a vermelho, cantos a amarelo.

- **Linha 1, P0083.** Antes: o buraco cinzento em haltere a W (B↔B) e a patilha de P0083 por cima da de P0078 a E. Depois: as 4 juntas fecham e a patilha W enche o encaixe de P0087. A mancha clara de P0083 fica no centro-baixo da célula, como o ponto claro da arte (44,60).
- **Linha 2, P0333.** Antes: buraco a N e sobreposição a E. Depois (−90°): a patilha N entra no encaixe de P0332 e o lado E fecha com a patilha de P0327. Ao lado está a arte de (6,22), azul em cima e nuvem cinzenta em baixo à direita.
- **Linha 3, alternativas de P0333.** +90° e 0° deixam o buraco B↔B no N, com a nota dos números de imagem.

## 2. C — âncoras na cópia (depois de B)

Comandos:

```
--anchor G0040 42 55 --rot 180
--anchor G0037 43 55 --rot 180
--anchor G0039 44 55 --rot 180
--anchor G0038 45 55 --rot 180
--anchor G0044 44 37 --rot 0
```

Resultado:
- Os 5 comandos passaram com 0 conflitos e `check_invariants(disk=True)` = [] **[V]**.
- `consistency` nas 6 peças e 12 vizinhas (18 peças): 0 `impossivel`, 0 `melhor_rotacao` **[V]**.
- `consistency` completo da cópia: só P0833 e P0343 (`melhor_rotacao`, não se corrigem) **[V]**.

| célula | report | peça (folha #) | lados com vizinhas montadas (tipo, RMS mm, folga mm) | NCC / ΔE na pose (outras rotações) |
|---|---|---|---|---|
| (42,55) | R0007 | P0442 (p06 #47) | E P0391 T↔B 1,40, −0,19; S P0401 T↔B 1,24, −0,33; W P0443 B↔T 1,35, 0,00 (3/3) | **0,46** / 7,5 (−0,15, 0,07, 0,12) |
| (43,55) | R0006 | P0401 (p06 #6) | N P0442 B↔T 1,24, −0,33; S P0425 B↔T 0,69, +0,35 (2/2) | **0,72** / 11,0 (−0,19, 0,11, −0,12) |
| (44,55) | R0005 | P0425 (p06 #30) | N P0401 T↔B 0,69; E P0392 T↔B 1,34, +0,06; S P0420 B↔T 1,04, −0,16; W P0441 B↔T 0,80, +0,46 (4/4) | **0,76** / 8,5 (0,01, −0,23, 0,18) |
| (45,55) | R0004 | P0420 (p06 #25) | N P0425 T↔B 1,04; E P0393 T↔B 1,27, +0,03; S P0408 T↔B 1,45, +0,07; W P0440 B↔T 0,83, +0,53 (4/4) | **0,67** / 9,8 (−0,07, 0,18, −0,04) |
| (44,37) | R0008 | P0501 (p08 #22) | E P0447 T↔B 0,61, +0,21; S P0506 B↔T 1,17, +0,16; W P0515 T↔B 1,09, +0,06 (3/3) | **0,88** / 14,3 (−0,02, −0,58, 0,12) |
| (45,37) | R0009 | P0506 (p08 #27) | N P0501 T↔B 1,17; E P0446 B↔T 1,00, −0,22; S P0511 T↔B 1,15, +0,07; W P0514 B↔T 0,84, +0,01 (4/4) | **0,85** / 13,3 (0,08, −0,29, −0,06) |

- Todos os lados com vizinha montada são T↔B e passam: 20/20 contando as juntas internas duas vezes. A folga fica entre −0,33 e +0,53 mm. A NCC máxima está na pose ancorada nas 6 **[V]**.
- Vista (`view_C`, só no scratchpad):
  - a faixa cinzenta da estrada continua em (42,55);
  - a relva continua nas filas 43–45;
  - a faixa verde-escura do topo de P0501 continua a das vizinhas;
  - nenhuma junta aberta **[V visual]**.
- **Ensaio na `alpes_o3`** (P0083 + as 5 âncoras, reconsulta só no último comando):
  - o log passa de 2076 para 2084 linhas;
  - 6 células passam de `ocupada_legado/foto` a `colocada/legado_scan`: (42..45,55), (44,37), (45,37);
  - P0083 passa de θ 85,21 para 175,21;
  - `fetch.md` ganha 2 propostas gémeas novas, ambas `aceite`, das células gémeas de G0044: **P0133 (lote 1 #40) → (3,28)**, margem 2,53, ΔE 8,5, e **P0163 (lote 2 #20) → (4,28)**, margem 1,91, ΔE 6,6;
  - saem do `fetch.md` as linhas de secção por ancorar G0037, G0038, G0039, G0040 e G0044;
  - `p_twin_placed` passa de 104/2401 para 102/2395;
  - `consistency` completo: P0333 (`impossivel`, por corrigir), P0833 e P0343.
- Nota: G0049 continua listada como «por ancorar → (44,37)», uma célula agora ocupada. A candidata da secção não é filtrada pela ocupação; é inofensivo e fica como observação.

## 3. D — bloco (1..3, 32..33) da montado_p03 contra o gémeo (45..47, 32..33) de G0043 (montado_p08)

Os dados desta zona não mudaram. As medidas são as mesmas na cópia e em `projects/alpes`.

| célula | peça (classe) | gémea (célula, classe) | `free_dist` mm | lados com tipo diferente (peça vs gémea rodada 180°) |
|---|---|---|---|---|
| (1,32) | P0292 FTTT | P0496 (47,33) BTTF | 3,08 | só E (T vs B) |
| (1,33) | P0289 BFTT | P0492 (47,32) FTTT | 2,83 | só W (B vs T) |
| (2,32) | P0293 BBBT | P0497 (46,33) BBTT | 2,39 | só E (B vs T) |
| (2,33) | P0290 BTBT | P0493 (46,32) BBBT | 2,36 | só W (T vs B) |
| (3,32) | P0294 BTTT | P0498 (45,33) BBTT | 2,86 | só E (T vs B) |
| (3,33) | P0291 BTTT | P0494 (45,32) TTTT | 2,67 | só W (B vs T) |

- O `free_dist` já percorre as 4 rotações relativas. A melhor troca dentro do bloco gémeo dá ≥ 1,56 mm. No índice inteiro, nenhuma das 6 tem par a menos de 0,88 mm **[V]**.
- **Vizinhas montadas fora do bloco:**
  - bloco p03: 6 juntas externas, todas T↔B, 5 passam; P0290 E com P0287 falha por RMS 1,71. Os 2 lados F estão na borda.
  - G0043: 8/8 T↔B passam, F 2/2.
  - Juntas internas: 14/14 nos dois blocos **[V]**.
- **Taxa de base:**
  - juntas montadas do tabuleiro (970): passam 96,5 %, RMS p50 1,12 mm;
  - pares T/B ao acaso (20 000): passam 35,1 %, RMS p50 1,74 mm.
  - Com células erradas, 5/6 a passar teria probabilidade ≈ 0,02, e ≈ 3·10⁻⁴ com os 6 tipos certos **[V, estimativa binomial]**.
- **Teste da troca:** em cada junta externa comparou-se a peça do bloco com a gémea do outro bloco rodada 180°, contra a mesma vizinha. A gémea encaixa igual: a diferença de custo vai de −0,24 a +0,26 mm nas 14 juntas. O perímetro do buraco de cada bloco é o gémeo do perímetro do outro **[V]**.
- **Imagem:**
  - bloco p03: NCC na pose de 0,48 a 0,86 em 5/6; P0292 (céu, fila 1) dá 0,13 contra 0,48 a 180°, sem poder.
  - G0043: 0,69–0,81 nas 4 com arte; a fila 47 não tem arte.

**Hipóteses:**
1. **«bloco da montado_p03 em células erradas» [F, pelos números].** As 6 juntas externas são T↔B e 5 passam, contra 35 % ao acaso. A troca mostra que o buraco onde está é o buraco gémeo do de G0043.
2. **«G0043 da montado_p08 errada» [F].** G0043 é uma secção rígida de 33 peças, `alta`, margem 1,35. As colunas 30, 31 e 34–36 casam com as gémeas a 0,17–0,36 mm (TRIAGEM §3). O bloco passa 8/8 lados externos e 14/14 internos.
3. **«ambos certos e a faca não é simétrica aqui» — a que explica os números [V números, NT físico].**
   - As vizinhas dos dois blocos passam.
   - Das 24 posições de lado (6 pares × 4), 18 têm o mesmo tipo. As 6 diferentes são todas lados sobre o **corte vertical central, entre as colunas 32 e 33**. Nas filas 1–3 as patilhas desse corte apontam E, O, E (de cima para baixo). Pela simetria de 180°, nas filas 47, 46 e 45 deviam apontar O, E, O; apontam E, O, E.
   - Em todo o tabuleiro há 255 pares gémeos montados. Os 6 com células nas colunas 32/33 são exatamente estes, e todos falham só nesse lado.
   - Os outros 249 pares dão `free_dist` p50 0,31 mm. Só 2 têm tipos diferentes, ambos já conhecidos: P0218 (prado comido, rebuild pendente) e P0052/P0147 a 0,41 mm.
   - O plano (`docs/estado-e-plano.md`, notas da simetria e dos 2953 cortes) já dizia que o segmento central da fila 24 não pode ser simétrico, porque mapeia em si próprio. Os dados indicam que **todo o corte central c32|c33 mantém a direção das patilhas em vez de a inverter**, pelo menos nas filas 1–3 ↔ 45–47.
   - Consequência para o produto **[NT]**: nas colunas 32/33 a gémea difere no lado central (T↔B trocado), por isso `find_twin` a rejeita no filtro de classe. É uma exceção a pôr no perfil (`puzzle.json`) se se confirmar noutras filas.
   - Pergunta física para o Tiago: «nas filas 1–3 e 45–47, entre as colunas 32 e 33, as patilhas apontam para o mesmo lado em cima e em baixo?»

## 4. Reports

**Ficam verificáveis depois da escrita no projeto:**
- R0004 (45,55), R0005 (44,55), R0006 (43,55), R0007 (42,55), R0008 (44,37) e R0009 (45,37), com as âncoras de §2;
- R0024 (P0083, +90°).

**R0010 (P0333) fica sem correção:**
- forma −90° 2/2 T↔B **[V]**;
- imagem a favor de +90° **[F para o critério]**;
- identidade em (6,22) **[NT]**;
- precisa do Tiago: a peça física em (6,22) é a #? da montado_p0x e roda como na linha 2 da figura?

**R0002/R0003** (bloco 1..3, 32..33): os números apontam para «ambos certos» (§3). Falta a confirmação física do corte central.

Nenhum report foi fechado.

**[NT]:**
- a identidade física das 6 peças de C e a orientação física de P0083 (confirmadas pelo Tiago por palavras, não medidas aqui);
- P0333 em (6,22);
- a assimetria do corte central fora das filas 1–3 / 45–47.

## 5. Escrita no projeto

**Não executada.** Pela regra da tarefa: «se para alguma das duas o resultado DEPOIS não for 4/4 T↔B e NCC máxima nessa rotação, PARA (não escreves no projeto)».

A sequência sem P0333 foi ensaiada na `alpes_o3`:
- invariantes OK;
- `consistency`: só P0333, P0833 e P0343;
- log 2076 → 2084.

Fica pronta para o gestor autorizar, a correr pela ordem:

```
python -m src.confirm P0083 --unplace --no-requery
python -m src.confirm P0083 --cell 44 60 --theta 175.21 --origin gt --no-requery
python -m src.confirm --anchor G0040 42 55 --rot 180 --no-requery
python -m src.confirm --anchor G0037 43 55 --rot 180 --no-requery
python -m src.confirm --anchor G0039 44 55 --rot 180 --no-requery
python -m src.confirm --anchor G0038 45 55 --rot 180 --no-requery
python -m src.confirm --anchor G0044 44 37 --rot 0
```

Se o Tiago confirmar fisicamente P0333 a −90°, acrescentam-se `--unanchor G0030 --no-requery` e `--anchor G0030 6 22 --rot 90`. Esta parte foi verificada na `alpes_o`: 2/2 T↔B, 0 suspeitas.
