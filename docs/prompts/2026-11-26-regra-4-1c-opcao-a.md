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
