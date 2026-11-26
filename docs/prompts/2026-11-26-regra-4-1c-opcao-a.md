# 2026-11-26: regra 4.1 (c), opção A (a aresta pintada fica sempre dentro do índice)

## Porquê

A medição D2 (`docs/prompts/2026-11-26-verificacao-implementacao-1.md` §7) mostrou que, nas linhas manuais gravadas com traços, 8 de 10 contornos têm píxeis da aresta pintada pelo Tiago fora do contorno do índice (`contour_px`). São 1086 px, até 0,27 mm. As causas medidas foram três:
- 86 %: fora da região de influência dos traços, `strokes.normalizar` repõe o automático;
- 13 %: os ganhos abaixo de `GANHO_MIN_MM2` são descartados;
- 1 %: a limpeza.

Pela regra D5, o contorno manual do Tiago é exato, por isso o erro está no código.

## Decisões

- Tiago, 2026-11-26: «Sim, opção A». A regra do teste 4.1 (c) é aresta ⊆ índice, exata (0 px).
- O gestor fixou o âmbito da correção a partir da tabela de opções do D2:
  - índice = derivado ∪ aresta, aplicado em `strokes.normalizar` (gravações novas) e na leitura de `overrides.index_contour_from` (linhas já gravadas; o `overrides.jsonl` é só-acrescentar e não se reescreve);
  - o teste 4.1 (c) passa de «não piora» (C) a absoluto;
  - a baseline das peças afetadas volta a ser congelada num commit próprio.
- Restrição: não escrever em `projects/alpes`. O re-registo (`piece_resegmented`) mede-se numa cópia; no projeto real acontece no próximo arranque do servidor (`rebuild_stale`), que é o caminho normal depois de uma mudança de código.

## Prompt (verbatim)

> Sim, opção A

## Resultado

**Resumo.** O que ficou feito: a aresta pintada fica sempre inteira dentro do índice que o programa lê (nas 8 peças medidas numa cópia: 1086 px → 0) e a 4.1 (c) passou a ser uma regra absoluta de 0 px [V].

O que ficou por fazer: a união na gravação (`strokes.normalizar`). Dois testes antigos afirmam o contrário da regra D5, por isso parei aí, como o prompt manda, e não os alterei.

Uma correção extra que não estava pedida: o arranque do servidor não aplicava a mudança ao projeto real; agora aplica.

### Commits (sem push)

| hash | assunto |
|---|---|
| `fa22099` | 4.1 (c) opção A: o índice lido contém a aresta pintada inteira |
| `5a90dc1` | D2: medição da união aresta ∪ índice numa cópia (antes/depois, arranque, suspeitas) |
| `2752876` | tools.verify: git status sem perder o espaço inicial da 1.ª linha (falha «arvore» ao congelar) |
| `fad2964` | baseline do golden congelada de novo depois da 4.1 (c) = A (só `tests/golden/baseline.json`) |
| `0643f74` | docs: decisão 4.1 (c) = A e linhas de strokes/overrides no CLAUDE.md |

### Ficheiros alterados

**Código**
- `src/overrides.py`: `index_contour_from` e `index_contour` fazem a união; `info` ganha `unido` e `aresta_fora_px`.
- `src/strokes.py`: `indice_com_aresta`, nova. `normalizar` não mudou.
- `src/render.py`: `_manual_stale`, que dá o motivo `manual` em `stale_assets`. `rebuild_stale` não re-segmenta as folhas que só têm esse motivo.

**Verificação**
- `tools/verify/invariantes.py`: `manual_aresta_no_indice` (a regra) e `arranque`.
- `tools/verify/__main__.py`: simula o arranque na cópia antes das regras.
- `tools/verify/metricas.py`: sai o «não piora» da aresta.
- `tools/verify/ambiente.py`: a cópia leva `crops/`; `_git` passa de `strip` a `rstrip`.

**Testes**
- `tests/test_indice_aresta.py`: +4 testes.
- `tests/test_invariantes_projeto.py`: +2 testes; a fixture passa a fazer o arranque.
- `tests/test_verify.py`: 1 parâmetro trocado e +2 testes.

**Medição**
- `tools/diagnostico/verify/d2_uniao.py`, `docs/diagnostico/verify/D2/uniao.json`, `docs/diagnostico/verify/D2/uniao_{P0071,P0198,P0407,P0754,P1064}.jpg`.

**Documentação**
- `docs/decisoes.md`: a entrada «4.1 (c) = A» e a entrada automática da congelação.
- `CLAUDE.md`: as linhas de `src/strokes.py` e `src/overrides.py`.
- `tests/golden/baseline.json`.

### Testes primeiro [V]

Antes da correção falhavam 5 testes novos; depois passam todos:
- os testes sintéticos da leitura:
  - os 3 casos do D2 (fora da influência, ganho abaixo de `GANHO_MIN_MM2`, limpeza);
  - o índice que já contém a aresta continua tal e qual;
  - ponta a ponta no prado sintético, com `resolver(..., normalizar_indice=True)`;
- `test_manual_aresta_dentro_do_indice`, que falhava com os mesmos 8 valores do D2 (P0045 85, P0071 210, …);
- `test_arranque_aplica_a_leitura_nova_de_uma_linha_ja_gravada`.

O parâmetro «aresta fora» de `test_comparar_apanha_regressao` testava a regra antiga (C), que a decisão do Tiago substitui. Foi trocado por `test_comparar_aresta_fora_ja_nao_e_baseline`, que verifica que a regra saiu da baseline e passou a absoluta.

### Bloqueio: a união na gravação (`strokes.normalizar`) [V]

Testei a união com um protótipo no `resolver` (`idx |= mask_aresta`, só com traços efetivos) e depois retirei-o. Com ele falham dois testes antigos:
- `tests/test_strokes.py::test_normalizar_keeps_auto_outside_influence_and_the_peca_gain`;
- `tests/test_strokes.py::test_deep_fundo_cut_survives_normalisation`.

Os dois afirmam `mask[~influencia] == auto[~influencia]`. No prado sintético a aresta fica 9 px fora do automático fora da influência: é a causa de 86 % do D2, o contrário da regra D5. Por isso não os alterei e não mexi na gravação.

Efeito prático: o `contour_px` gravado continua a ser o derivado, e é a leitura que lhe junta a aresta. O render, o npz, o shape, o twin e o fit leem todos pelo `index_contour`, por isso usam sempre o índice certo [V]. Os testes do servidor passavam com o protótipo.

### Identidade e CONVENCAO §3

- **Identidade:** uma gravação sem traços efetivos continua a dar o automático exato. É uma linha só de desenho (`indice: "automatico"`, fora de `latest_overrides`) e a leitura não lhe toca. `test_normalizar_no_stroke_is_identity`, `test_a2_no_stroke_edge_is_s0_and_index_is_auto` e `test_contorno_save_edge_only_is_display_only` passam [V].
- **17/17 do CONVENCAO §3:** não voltei a correr esta medição [NT]. Ela mede a derivação (`normalizar`), que é igual por construção: o diff não toca em `normalizar` nem em `resolver` [V]. Esses 17 registos são hoje reposições.

### Medição numa cópia (`d2_uniao.py`, cópia feita com `guarda.py`) [V]

| Peça | aresta fora (px) antes → depois | Δárea do índice (mm²) | classe | Δcordas máx (mm) | maior deslocamento de um canto (mm) |
|---|---|---|---|---|---|
| P0045 | 85 → 0 | +0,609 | TTTT = | 0,107 | 0,106 |
| P0071 | 210 → 0 | +1,505 | BTTT = | 0,228 | 0,200 |
| P0139 | 70 → 0 | +0,502 | BBBT = | 0 | 0 |
| P0198 | 222 → 0 | +1,591 | FTTT = | 0,146 | 0,187 |
| P0315 | 0 → 0 | 0 | = | 0 | 0 |
| P0395 | 0 → 0 | 0 | = | 0 | 0 |
| P0407 | 200 → 0 | +1,434 | BTBT = | 0,137 | 0,146 |
| P0620 | 145 → 0 | +1,039 | BBBT = | 0,057 | 0,068 |
| **P0754** | 30 → 0 | +0,215 | BBBT = | **1,028** | **1,335** |
| **P1064** | 124 → 0 | +0,888 | BBTT = | **0,587** | **0,771** |

- **Δárea:** é exatamente a área que estava fora no D2. A união não acrescenta mais nada [V].
- **P0754 e P1064: o canto NO muda de sítio** ao longo do chanfro de sombra do índice (linha «canto» de `uniao_P0754.jpg` e `uniao_P1064.jpg`). Os lados opostos ficam mais desiguais (P0754: 19,69 / 18,25 e 17,17 / 19,16 mm). O código dos cantos não mudou; o que se vê é uma instabilidade que já existia em `shape.analyse`: em cantos chanfrados, 1–2 px bastam para o canto saltar [V nas imagens]. Nas imagens:
  - antes, o canto estava a meio do chanfro, a ≈ 1 mm do canto da aresta;
  - depois, está a 2–3 px do canto verdadeiro da aresta;
  - o canto SO continua dentro do halo.
- **Imagens vistas** (P0198, P0071, P0407, P0754, P1064): o que entra no índice é a orla clara da peça, que estava fora; o resto não muda [V].
- **Arranque na cópia** (`stale_assets` + `rebuild_stale`) [V]:
  - 8 peças desatualizadas em 8 folhas (S0003, S0004, S0006, S0009, S0014, S0019, S0022, S0030), todas pelo motivo `manual`;
  - 8 eventos `piece_resegmented` com motivo `manual`; 0 restantes, 0 erros, 0 folhas re-segmentadas.
- **A correção extra:** o `stale_assets` antigo só comparava o npz com o log, e os dois continuam a concordar entre si; por isso o arranque não via nada a refazer. A premissa «acontece no próximo arranque» só passou a ser verdade com o motivo `manual` [V; teste `test_arranque_aplica_a_leitura_nova_de_uma_linha_ja_gravada`].
- **`consistency.evaluate`:** 18 suspeitas antes e 18 depois, iguais item a item [V].

### Baseline (`fad2964`) [V]

- **Cordas:** mudam em P0045, P0071, P0198, P0407, P0620, P0754 e P1064. Só P0754 (1,028 mm) e P1064 (0,587 mm) passam os 0,3 mm.
- **`aresta_fora_do_indice_mm2`:** passa a 0 nas 8.
- **Simetria:** só mudam os valores informativos de P0630|P0198 (rms 0,396 → 0,369, nn_max 0,548 → 0,552). Os pares acima do limiar são os mesmos.
- **Suspeitas:** iguais.
- **Limiares:** nenhum foi ajustado. `aresta_fora_do_indice_delta_mm2` continua em `limiares.json`, mas já não é usado.

### Suite, verify, graphify, vigilância

- **Suite** (`.venv/Scripts/python.exe -m pytest tests/`, uma corrida em `0643f74`): **999 passed, 1 skipped, 0 failed**, em 16 min 31 s [V].
- **`python -m tools.verify`:** código 0, em 24,0 s [V]. A primeira congelação deu código 6 («arvore») por um defeito antigo: o `_git` fazia `strip()` à saída inteira e comia o espaço inicial de « M docs/decisoes.md». Corrigido em `2752876`, com teste; a congelação foi refeita.
- **`graphify update .`:** corrido [V].
- **Vigilância:** `projects/alpes` com pieces/overlays/scans em 39/39/39 no início, a meio e no fim [V]. Nada foi escrito em `projects/alpes` [V].
- **Próximo arranque do servidor no projeto real:** vai escrever 8 eventos `piece_resegmented` com motivo `manual` [NT no projeto real; V na cópia].

### Decisões pendentes (Tiago)

1. **União na gravação:** mudar os dois testes de `test_strokes.py` para «fora da influência, índice = automático ∪ aresta» e pôr a união no `resolver`/`normalizar`? Sem isto, o `contour_px` gravado continua sem a aresta e só a leitura a junta. O resultado já está funcionalmente certo; a linha fina do índice no editor é que não mostra a união.
2. **P0754/P1064:** olhar para a procura de cantos em cantos chanfrados de sombra? Hoje o canto NO salta e as cordas mudam 1,03 e 0,59 mm.
3. **`tools.verify`:** aceitar que simule o arranque na cópia antes das regras (a cópia leva os recortes, +4 s)? Assim, um projeto real com linhas por aplicar aparece em «Arranque simulado» e não como falha da 4.1 (b).
4. **`limiares.json`:** retirar a entrada `aresta_fora_do_indice_delta_mm2`, que já não é usada?

### Ronda 2: união na gravação

O Tiago autorizou a decisão pendente 1 («Sim, muda-os»).

Resultado: com traços efetivos, o índice que se grava passa a conter a aresta inteira [V]. Sem traços efetivos, o índice continua exatamente igual ao automático [V]. A união na leitura fica como estava, para as linhas já gravadas.

**Commits (sem push)**

| hash | assunto |
|---|---|
| `618e6be` | testes: fora da influência o índice gravado é automático ∪ aresta (4.1 c = A; falham sem a união na gravação) |
| `c7045d2` | 4.1 (c) = A na gravação: com traços efetivos o índice gravado contém a aresta inteira |
| `43220cf` | D2: CONVENCAO §3 (17 registos) medido de novo com a união na gravação |
| `88203d4` | limiares: retira aresta_fora_do_indice_delta_mm2 (sem uso desde a 4.1 c absoluta) |

**Testes [V]**
- `test_normalizar_keeps_auto_outside_influence_and_the_peca_gain` e `test_deep_fundo_cut_survives_normalisation` mudaram numa só regra: fora da influência, `mask == auto | mask_aresta` (antes, `== auto`).
- Cada um ganhou também a asserção «aresta ⊆ índice».
- O resto mantém-se: o ganho da peça (IoU, 95 % do remendo) e o corte «fundo» com mais de 3 mm².
- No commit `618e6be`, só com estes testes, os dois falhavam sem a união: 2 failed, 21 passed.
- `test_indice_do_editor_lido_contem_a_aresta_fora_da_influencia` (de `tests/test_indice_aresta.py`, ronda 1) mudou de entrada. A linha antiga passou a ser reconstruída com `normalizar` sem união, e o teste verifica também que o `resolver` já grava a aresta dentro do índice.

**Código**
- `src/strokes.py`, `resolver(..., normalizar_indice=True)`: com influência não vazia (traços efetivos), `idx = indice_com_aresta(idx, mask_aresta)`. Na identidade (influência vazia) o índice continua a ser o automático.
- `src/server.py`, `_solve_a2`: nos caminhos de retoque de vértices e de base gémea, a aresta gravada (`am`) é unida ao índice quando há edição. A edição conta assim:
  - traços efetivos, um retoque que muda a aresta, ou base gémea;
  - um pedido sem traços em que o cliente reenvia a mesma aresta continua a ser identidade.
- Em consequência, a linha fina do índice no editor e o `mascara_rle` mostram a união.
- Testes do servidor e do editor: `tests/test_server.py` e `tests/test_gui_contorno.py` passam, 52 de 52 [V].

**CONVENCAO §3 (17 registos)**
Medido com `tools/diagnostico/verify/d2_17.py` sobre uma cópia; resultado em `docs/diagnostico/verify/D2/convencao17.json` [V]. Os 17 registos originais são as linhas de traços sem `convencao`, gravadas antes de 2026-11-09. Corri-os pelo `resolver` atual com e sem a união:

| | automático bit a bit | reposição pelo critério de `renormalizar.py` (profundidade ≤ 0,5 mm) |
|---|---|---|
| sem união | 14/17 | 17/17 |
| com união | 14/17 | 17/17 |

- **Os 14:** identidade (só traços de sombra, ignorados), por isso iguais nos dois casos.
- **P0045, P0071 e P1064:** já ficavam a 1 px (0,085 mm) do automático sem a união. Com a união passam a ter +0,67, +1,51 e +0,91 mm² a mais, com profundidade 0,169, 0,271 e 0,169 mm, e a aresta fica a 0 px fora do índice. Continuam abaixo de 0,5 mm, por isso continuam a dar «reposição».
- **O «17/17 no automático exato» do CONVENCAO** é o contorno guardado depois da reposição. Continua a valer, 17/17.
- **O bit a bit do `resolver`** nunca foi 17/17. Hoje dá 14/17, com e sem união [V].
- **Ponto a notar:** nos 14 casos de identidade a aresta fica fora do automático (4–523 px), porque a identidade mantém o índice igual ao automático, como pedido. Hoje essas linhas são só desenho (`indice: "automatico"`) ou reposições, e nenhuma tem `aresta_px` ativo no índice, por isso a regra 4.1 (c) não as apanha.

**Limiares (`88203d4`)**
- Sai `aresta_fora_do_indice_delta_mm2` de `tests/golden/limiares.json` e também da constante `LIMIARES_INICIAIS` em `tools/verify/metricas.py`, que só servia para escrever esse ficheiro.
- Nenhum limiar usado mudou. `tests/test_verify.py` passa, 22 de 22 [V].

**Fecho**
- **Suite completa** (`.venv/Scripts/python.exe -m pytest tests/`, uma corrida em `88203d4`): **999 passed, 1 skipped, 0 failed**, em 17 min 08 s [V].
- **`python -m tools.verify`:** exit 0, em 22,6 s [V]. As métricas do golden são iguais à baseline chave a chave, por isso a baseline não foi congelada outra vez [V]. É o esperado: as linhas gravadas não mudam e a leitura já fazia a união.
- **`graphify update .`:** corrido.
- **Vigilância:** `projects/alpes` com 39/39/39 (pieces/overlays/scans) no início e no fim. Nada foi escrito em `projects/alpes` [V].
- **`docs/decisoes.md`:** uma linha acrescentada à entrada «4.1 (c) = A».

**Decisões que continuam pendentes (não mexi)**
- **2:** a procura de cantos em cantos chanfrados de sombra (P0754, P1064).
- **3:** o `tools.verify` simular o arranque do servidor na cópia.
