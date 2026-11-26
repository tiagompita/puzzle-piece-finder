# 2026-11-26: fecho da verificação determinística (agentes com skills, D3 = A, regressão da segmentação e do matching, prova da GUI)

## Porquê

O `tools.verify` já verifica os invariantes, os contornos guardados e o golden por hashes. Ficam três lacunas:
- Os subagentes do projeto nunca carregaram as skills, porque o `tools:` deles não tem `Skill`.
- A D3 foi decidida (opção A) e falta aplicá-la ao perfil.
- Uma alteração que estrague a segmentação ou o matching ainda passa no verify.

## Decisões

**Do Tiago (2026-11-26)**
- D3 = A: os 3 pares P0140/P0499, P0495/P0938 e P0500/P1178 são o corte c32|c33. A exceção alarga-se às filas [1,5] e [43,47].
- O plano foi aprovado com estes ajustes:
  1. A prova de regressão corre numa worktree temporária, sobre uma cópia do projeto real que tem `pieces/` e `overlays/`. O exit ≠ 0 tem de vir das métricas, e o relatório diz o código de saída de cada caso.
  2. Nesta ronda o implementer lê as duas `SKILL.md` à mão logo no arranque, porque as definições dos agentes só são lidas quando a sessão começa.
  3. Nos `emp-*` acrescenta-se `Skill` só a `emp-qa` e `emp-revisor`, que ficam fora do repositório.
  4. O verify não importa de `tools/diagnostico/`.
  5. O molde do buraco mede-se em leave-one-out, com peças do golden que tenham ≥ 2 vizinhas.
  6. O relatório explica o «+1 falso alarme».
- Antes da ronda, os 8 eventos `piece_resegmented` (motivo `manual`) que o arranque do servidor escreveu às 15:24 entraram num commit à parte, `a6e2c73`, aprovado pelo Tiago. O pre-commit correu o verify nesse commit (código 0, 15,6 s): foi a 1.ª vez que o hook correu num commit real.

**Do gestor**
- A prova da Parte 0, um helper a invocar uma skill, é feita pelo gestor com `claude -p` no fim, porque um subagente não lança subagentes.

## Prompt (verbatim)

> Agente: implementer. Skills: cv-visual-verification, piece-fit-matching.
>
> Antes de grep ou leitura de ficheiros, consulta o grafo do Graphify. No fim, corre `graphify update .`.
>
> OBJETIVO: fechar a adaptação da verificação determinística (docs/prompts/2026-11-26-verificacao-deterministica.md). Três partes, por esta ordem, cada uma com os seus commits.
>
> PARTE 0 — AGENTES SEM ACESSO A SKILLS
> Os agentes em .claude/agents/ (helper, implementer, planner) têm `tools:` explícito sem `Skill`, por isso nunca carregaram as skills pedidas nos prompts. Documentação: https://code.claude.com/docs/en/sub-agents (com `tools` explícito, `Skill` tem de estar na lista; o campo `skills:` pré-carrega skills no arranque).
> - Acrescenta `Skill` ao `tools:` dos três.
> - Implementer e helper: `skills:` com cv-visual-verification, piece-fit-matching e graphify (pré-carregadas). Planner: só `Skill` no `tools:`.
> - Verifica se a skill /empresa usa outros agentes (emp-* ou outros, no projeto ou em ~/.claude/agents/). Se usar, aplica a mesma correção e lista os ficheiros alterados. Os que ficarem fora do repositório não vão no commit: diz-me quais são.
> - Prova: lança um subagente de teste (helper) que invoque uma skill e confirma no relatório que carregou [V].
>
> PARTE 1 — D3 (decisão do Tiago, 2026-11-26: opção A)
> Nas imagens de docs/diagnostico/verify/simetria/, os 3 pares P0140/P0499, P0495/P0938 e P0500/P1178 têm contornos que seguem as peças e recortes mesmo diferentes. É o corte c32|c33, não recortes maus.
> 1. projects/alpes/puzzle.json: alargar symmetry.excecoes c32|c33 de filas [1,3] e [45,47] para [1,5] e [43,47]. Só esta alteração em projects/alpes, num commit próprio.
> 2. tests/golden/simetria_por_rever.json fica com a lista vazia (ou sai, se o teste o permitir sem perder a regra «par novo acima do limiar falha»).
> 3. Medir antes e depois numa cópia: consistency.evaluate deve passar de 18 para 12 itens, e os 6 que saem têm de ser exatamente P0140, P0499, P0495, P0938, P0500 e P1178. Se sair ou entrar outra coisa, para e reporta.
> 4. Congelar de novo a baseline com `python -m tools.verify --congelar-baseline` (commit só com baseline.json) e registar a D3 = A em docs/decisoes.md, com os números.
>
> PARTE 2 — REGRESSÃO DA SEGMENTAÇÃO E DO MATCHING
> Hoje o tools.verify lê os contornos guardados; uma alteração que estrague a segmentação ou o matching ainda passa.
> 1. Passos 1–3 do tools.verify sobre o golden (secção 3 do levantamento):
>    - segmentação de novo das folhas do golden e comparação com o guardado (n.º de peças por folha, distância máxima e IoU por peça);
>    - classificação (cls, cordas ±0,3 mm, F por célula);
>    - matching (E-sym top-1 e RMS, E-real-2 sem falsos positivos, ligações dos quadrados 2×2, molde do buraco top-1);
>    - imagens de prova das piores peças.
> 2. Modo rápido e completo: se o completo passar de ~10 min, `--rapido` (E-sym + 3 folhas) no pre-commit, e o completo antes de commits que toquem segmentation.py, shape.py, fit.py ou twin.py. Mede os tempos.
> 3. Nova congelação da baseline com as métricas dos passos 1–3, com `--congelar-baseline`, ANTES de qualquer outra alteração a src/; registo em docs/decisoes.md. Limiares fixos a partir das constantes já medidas, nunca a partir do resultado.
> 4. Prova de que apanha regressões: numa cópia, estraga de propósito um parâmetro da segmentação e um do matching; o tools.verify tem de sair ≠ 0 nos dois casos. Repõe e confirma exit 0.
> 5. Prova da GUI (secção 5 do levantamento): `python -m tools.gui.prova`, com capturas a 1366×768 e 390×844 dos ecrãs principais, indice.html, e falha com erro de consola, resposta ≥ 500, scroll horizontal a 390 px ou ecrã em branco. Reaproveita tools/gui/d1_capturas.py.
> 6. Atualiza o CLAUDE.md e as skills para apontarem para os passos novos e para tools.gui.prova.
>
> REGRAS
> - Medições numa cópia, nunca em projects/alpes (exceto o commit do puzzle.json da Parte 1).
> - Testes que falham primeiro; não alteres testes existentes sem OK.
> - Suite completa com .venv e tools.verify exit 0 no fim; [V]/[NT]/[F].
> - Um commit por bloco, sem Claude como co-author; push no fim.
> - Paragem: se a Parte 1 mudar mais do que os 6 itens, se não der para congelar a baseline antes de mexer em src/, ou se o ponto 4 da Parte 2 não fizer o verify falhar, para e reporta.
> - Relatório palavra por palavra no «Resultado» de docs/prompts/2026-11-26-verificacao-fecho.md.

## Resultado

Etiquetas: [V] verificado com evidência, [NT] não testado, [F] testado e falha.

**Resumo.**
- Partes 0 e 2: feitas.
- Parte 1: parou na medição, por duas paragens da ronda. O `puzzle.json` e a lista «por rever» não mudaram.
- Ambas as paragens estão nas decisões pendentes.

Antes de começar li à mão as duas `SKILL.md` (cv-visual-verification, piece-fit-matching) e segui-as: olhei para as imagens de prova, medi contra a verdade de terreno e usei o verify antes de cada commit [V].

### Commits (sem push; um por bloco, todos passaram pelo hook `commit-msg`)

| hash | assunto |
|---|---|
| `b3e4b10` | agentes: Skill no tools: dos três e skills pré-carregadas no helper e no implementer (inclui o prompt da ronda) |
| `fe0dcd5` | tools.verify: passos 1–3 (segmentação, classificação, matching sobre o golden), --rapido e pre-commit com modo |
| `4da9695` | golden: baseline com os passos 1–3 congelada com tools.verify (src/ igual a a6e2c73) |
| `c292802` | prova da GUI: python -m tools.gui.prova (cópia, 11 ecrãs a 1366 e 390 px, indice.html, falha com consola, HTTP >= 500, scroll ou branco) |
| `d8f7978` | D3: medição numa cópia do alargamento da exceção c32\|c33 (consistency.evaluate 19 -> 19; simetria 3 -> 0) |
| `fc7fa91` | docs: passos 1–3 do verify, --rapido, prova da GUI no CLAUDE.md e nas skills; decisões da ronda «fecho» |
| (este) | docs: resultado da ronda «fecho» |

`fe0dcd5` e `4da9695` passaram pelo pre-commit com `tools.verify --rapido`: código 0 em 64,1 s e em 64,3 s [V]. Não usei `--no-verify`.

Ressalva sobre `fe0dcd5`: o pre-commit lê a árvore de trabalho. Quando o fiz, a baseline já estava congelada no disco, mas só entrou no commit seguinte. Por isso, `fe0dcd5` sozinho daria código 5, «sem o bloco regressao na baseline». O par `fe0dcd5` + `4da9695` é coerente.

### Parte 0: agentes com acesso a skills

**Repositório:**
- `.claude/agents/helper.md` e `implementer.md`: `Skill` no fim do `tools:`, e `skills:` com cv-visual-verification, piece-fit-matching e graphify.
- `.claude/agents/planner.md`: só `Skill` no `tools:`.
- As três skills existem em `.claude/skills/` com esse `name:` [V]:
  - `cv-visual-verification/SKILL.md`;
  - `piece-fit-matching/SKILL.md`;
  - `graphify/SKILL.md`.

**Fora do repositório** (não entram no commit), ajuste 3. Só estes dois; os outros `emp-*` ficaram como estavam.

```diff
--- C:\Users\tiago\.claude\agents\emp-qa.md
-tools: Read, Grep, Glob, Bash
+tools: Read, Grep, Glob, Bash, Skill
--- C:\Users\tiago\.claude\agents\emp-revisor.md
-tools: Read, Grep, Glob
+tools: Read, Grep, Glob, Skill
```

**Prova** (um helper a invocar uma skill): fica a fazer pelo gestor, com `claude -p` [NT]. Um subagente não lança subagentes, e as definições só são lidas quando a sessão arranca.

### Parte 1: D3 = A (PARADA; o perfil não mudou)

**Medição numa cópia** (`tools/diagnostico/verify/d3_excecao.py`, cópia com `copiar_projeto`/guarda, arranque simulado antes) [V]:

| | antes (filas [1,3] e [45,47]) | depois (filas [1,5] e [43,47]) |
|---|---|---|
| `consistency.evaluate(incluir_falsos=True)`, itens | 19 | 19 |
| dos quais suspeitas (sem falso alarme) | 18 | 18 |
| itens que saem / entram | — | 0 / 0 |
| resumo (`summary`) | — | igual |
| simetria 4.2 sem a lista «por rever», violações | 3 pares (P0140/P0499, P0938/P0495, P1178/P0500) | 0 |
| pares na exceção | 6 | 9 |

- Nas 6 peças (P0140, P0499, P0495, P0938, P0500, P1178) só mudam os campos `excecao` e `texto`: o texto passa de «silhueta longe da gémea: recorte a rever» para o da exceção. A assinatura e o grau não mudam [V].
- **Porque não sai nada:** `src/consistency.py` está assim de propósito: «Cells of a known exception of the die symmetry … are still listed, with the exception as text». As 12 peças da exceção antiga também continuam nas 18. A expectativa do prompt, «18 → 12», não corresponde ao código [V].
- **Paragens** (as duas regras da ronda):
  1. A Parte 1 não tira os 6 itens: «se sair ou entrar outra coisa, para e reporta». Aqui sai menos do que o esperado: nada.
  2. Mudar o perfil faz falhar um teste existente: `tests/test_simetria.py::test_perfil_alpes_declara_a_excecao_c32_c33`. O teste afirma as filas `[[1, 3], [45, 47]]` e o texto «(exceção por confirmar)». A regra é não alterar testes existentes; se for preciso, parar.
- **Ficou como estava:**
  - `projects/alpes/puzzle.json`;
  - `tests/golden/simetria_por_rever.json` (os 3 pares);
  - a baseline das métricas do golden.
- **Não fiz:** o commit do perfil e a congelação «só baseline» da Parte 1. Não houve nenhuma escrita em `projects/alpes` [V].

**O «+1 falso alarme»** [V, numa cópia]:
- `consistency.evaluate(pr, pl)` dá 18 itens.
- `evaluate(..., incluir_falsos=True)` dá 19: as mesmas 18 mais P0343 (5,20), grau `melhor_rotacao`, que o Tiago marcou como falso alarme em 2026-11-16 («confirmada fisicamente pelo Tiago 2026-11-16», `Project.falsos_alarmes`).
- As 18 são todas do grau `recorte`:
  - 12 da exceção c32|c33;
  - os 6 dos 3 pares acima.
- A GUI mostra o mesmo: «Suspeitas (18) · 1 falso alarme» (captura `reports_1366.png` da prova da GUI).

### Parte 2: regressão da segmentação e do matching

**O que o verify faz agora** (`tools/verify/regressao.py`; não importa nada de `tools/diagnostico/`, e há um teste AST que o verifica):

1. **Segmentação.**
   - `ingest.segment_sheet`, o mesmo caminho da importação, corre nas 31 folhas do golden.
   - Por folha compara o n.º de peças com o guardado e com a baseline.
   - Por peça do golden compara com o contorno de `pieces/<scan>.npz` (`maskcmp.mask_metrics`): `d_max` e IoU.
   - As 10 peças com contorno manual ficam fora (D5).
2. **Classificação** da segmentação nova:
   - `cls` igual;
   - cordas ±0,3 mm;
   - n.º de lados F igual ao pedido pela célula (`profile.flat_directions`).
3. **Matching:**
   - **E-sym:** `segment_scan` de A1/A2/B2 e `free_dist`. A lógica de `tests/test_segment_scan_esym.py` foi reescrita aqui.
   - **E-real-2:** `find_twin` só com forma sobre `tests/data/ereal2_memoria.npz`. O leitor da memória e a relação de verdade de terreno foram reescritos aqui.
   - **Quadrados 2×2:** `fit.side_costs` nas 40 peças dos 10 quadrados. Cada ligação tem de ser a melhor mútua.
   - **Molde do buraco em leave-one-out** (ajuste 5):
     - entram as peças colocadas do golden com ≥ 2 vizinhas colocadas, via `fit.hole_queries(exclude_piece=)` + `rank_hole`;
     - o pool são as 267 peças do golden;
     - conta como acerto a própria peça ou a gémea.
4. **Imagens de prova:** as 6 peças com maior `d_max`, contorno guardado a verde e novo a vermelho, em `<saída>/prova/seg_P####.png`.

**Limiares:** são fixos e vêm de constantes já medidas, nunca do resultado. Estão em `tests/golden/limiares.json`, bloco `regressao`, escrito a partir de `LIMIARES_REGRESSAO`, cada um com a fonte:

| Métrica | Falha se |
|---|---|
| n.º de peças por folha | diferente do guardado ou da baseline |
| `d_max` | > baseline + 0,3 mm |
| IoU | abaixo da baseline |
| `cls` | diferente |
| cordas | \|Δ\| > 0,3 mm |
| F por célula | a peça perde o F certo |
| E-sym | mediana > 0,5 mm ou top-1 < 20/20 |
| E-real-2 | algum `aceite` num par negativo, ou menos aceites nos pares gémeos do que na baseline |
| quadrados | menos ligações do que na baseline, ou < 10/10 |
| molde | uma peça que era top-1 deixa de o ser (as que deixam de ter 2 vizinhas não contam), ou aparece uma «alta» errada nova |

- A comparação do molde é peça a peça porque o tabuleiro muda com o uso.
- Um ficheiro do passo 3 alterado (scan A2, memória E-real-2) dá código 3.
- Uma métrica pior dá código 5.

**Baseline (passos 1–3)**, `4da9695`, congelada no modo completo com `src/` igual a `a6e2c73` (`git diff HEAD -- src` vazio) [V]:

| Métrica | Valor |
|---|---|
| folhas | 31, todas com a contagem guardada |
| peças do golden medidas | 257 (10 fora por contorno manual) |
| IoU | 1,000 em todas |
| `d_max` | 0,000 mm em todas |
| F certo | 217/217 |
| E-sym | 0,383 mm; top-1 20/20 em A1→B2, A2→B2 e B2→A2 |
| E-real-2 | 15 pares gémeos `aceite`, 1 proposta BE×céu, 0 em negativos |
| quadrados | 40/40 ligações, 10/10 |
| molde (leave-one-out) | top-1 214/226, «alta» 131, 0 erradas |

A entrada automática em `docs/decisoes.md` diz «limiares inalterados». Acrescentei, por baixo, uma linha que diz que o bloco `regressao` é novo nesta ronda.

**Tempos** [V]:
- **completo:** 323,9 s, dos quais 307,7 s nos passos 1–3. Repartição medida numa corrida de teste do modo rápido: segmentação ≈ 3,7–6 s por folha; molde em leave-one-out ≈ 97 s; quadrados 11 s; E-real-2 10 s; E-sym 7 s.
- **`--rapido`:** 64,1 s e 64,3 s. Cobre o E-sym e 5 folhas: as 2 do E-sym que são do golden e as 3 com mais peças do golden (S0009, S0010, S0020), mais E-real-2 e quadrados, sem o molde.
- **Pre-commit:**
  - `--rapido` por omissão;
  - completo quando o stage toca `src/segmentation.py`, `src/shape.py`, `src/fit.py` ou `src/twin.py`.
- O completo fica abaixo dos 10 min. O `--rapido` existe na mesma porque o gestor o pediu para o pre-commit.

**Imagens vistas:**
- baseline: `seg_P0001.png`, guardado = novo, a sombra projetada dentro do contorno, que é o viés conhecido do `scan`;
- regressão de segmentação: `seg_P1360.png`, descrita abaixo;
- 3 capturas da GUI, descritas na prova da GUI.

**Prova de que apanha regressões** (ajuste 1). Feita numa worktree temporária (`git worktree add --detach D:/DEKSTOP/ppf_wt_regressao`, com `.venv` em junção para o `.venv` do repositório), sobre uma cópia completa do projeto real em `%TEMP%` (`guarda.copytree`, com `pieces/` e `overlays/`). Modo completo [V]:

| Caso | Alteração na worktree | Código | Grupos de falha | O que falhou |
|---|---|---|---|---|
| segmentação | `src/segmentation.py` `_SCAN_LAB_WEIGHTS` (0,5, 1, 1) → (2,0, 1, 1) | **5** | só `baseline` (772); ambiente ok, golden ok, vigilância 39/39/39 no início e no fim | IoU < 1 nas 257 peças, `d_max` até 1,76 mm (P1360), cordas até 1,42 mm, E-sym 0,601 mm > 0,5 |
| matching | `src/fit.py` `RMS_SCALE` 1,1 → 4,4 | **5** | só `baseline` | quadrados 37/40 ligações e 7/10 (3, 9, 10); molde: top-1 perdido em 18 peças (214 → 196) |
| reposto | nenhuma (`git checkout`) | **0** | — | 295,3 s |

- Imagem vista: `seg_P1360.png`. O contorno novo engole o fundo verde à volta da peça, até ≈ 1,8 mm, e o guardado segue a peça.
- No fim, a worktree, a junção e a cópia do projeto foram removidas (`git worktree remove`, `prune`, `guarda.rmtree`) [V].

**Prova da GUI** (`python -m tools.gui.prova`, `c292802`):
- O que faz:
  - copia o projeto sem `logs/`;
  - arranca `src.server --ui novo` sobre a cópia e espera pelo «pronto» e pelo ranking dos buracos;
  - faz 22 capturas: 11 ecrãs × 1366 × 768 e 390 × 844. Os ecrãs são Montar, tabuleiro geral, detalhe com zoom, painel da peça, painel do lugar, lupa, lista «Grupos soltos», painel do grupo, menu, definições e Reports com as Suspeitas (GUI antiga);
  - escreve `indice.html` e `capturas.json` fora do repositório (`%TEMP%/ppf_prova_gui/prova_gui/<data>`).
- Falha com código 1 nestes casos (código 2 = ambiente):
  - erro de consola, exceção da página ou linha `erro_cliente` no registo;
  - resposta ≥ 500;
  - scroll horizontal a 390 px;
  - ecrã em branco.
- **Resultado: código 0 em 64,0 s** [V].
- A primeira corrida deu código 1, por um defeito meu: a cópia levava `logs/` do projeto real. Esses logs têm 14 linhas `erro_cliente` antigas, de 2026-11-24/25, do Brave no iPhone: «window.ethereum.selectedAddress», que é um script injetado pela carteira do browser, não da app. Corrigi: a cópia passou a ir sem `logs/`.
- Capturas vistas: `grupo_390`, `peca_1366` e `reports_1366`. Sem problemas visíveis.
- Testes: `tests/test_prova_gui.py`, com 5 rápidos (verificações puras e `-m`) e 1 `slow` (a prova inteira).
- Reaproveita o desenho de `tools/gui/d1_capturas.py`. As esperas do servidor estão escritas no próprio módulo, sem importar `gil_intervalo`.

**Testes novos** (nenhum teste existente foi alterado [V]):
- `tests/test_githook_precommit_modo.py`: 13. Escritos primeiro: falharam 7 (os de `--rapido`) antes de mudar o hook, e depois passaram 13 [V]. Os 19 testes antigos de `test_githook_precommit.py` continuam a passar.
- `tests/test_verify_regressao.py`: 26 rápidos e 1 `slow`.
  - Os rápidos são: cada regressão apanhada, tolerâncias, modo rápido parcial, regra das folhas, mordida local que o IoU quase não vê, nenhum import de `tools/diagnostico`, limiares versionados e «`--rapido` não congela».
  - O `slow` falhou antes da congelação e passa depois [V].
  - Honestamente: a maior parte deste ficheiro foi escrita depois do código de `regressao.py`. A capacidade de falhar está demonstrada pelos testes de perturbação e pela prova na worktree.
- `tests/test_prova_gui.py`: 5 rápidos e 1 `slow`.

**Documentação:**
- `CLAUDE.md`, em «Conventions», na regra «Verificação antes de commit»: passos 1–3, `--rapido`, o modo do pre-commit e `tools.gui.prova`.
- `.claude/skills/cv-visual-verification/SKILL.md` e `piece-fit-matching/SKILL.md`: secção «Verificação».
- `docs/decisoes.md`: linha na entrada da congelação e entrada «fecho da verificação determinística».

### Fecho
- **Suite** (`.venv/Scripts/python.exe -m pytest tests/ -q -p no:cacheprovider`, uma corrida em `fc7fa91`): **1071 passed, 1 skipped, 0 failed** em 17 min 10 s, exit 0 [V] (inclui os `slow`: a prova da GUI inteira e a baseline dos passos 1–3).
- **`python -m tools.verify`:** código **0** em 262,5 s [V].
- **`python -m tools.verify --rapido`:** código **0** em 54,5 s [V].
- **`python -m tools.gui.prova`:** código 0 em 64,0 s [V]; a corrida final está em `%TEMP%/ppf_prova_gui/prova_gui/20261126-165228` (código 0, 63,0 s).
- **`graphify update .`:** corrido [V].
- **Vigilância** `projects/alpes` (pieces/overlays/scans): 39/39/39 no início, 39/39/39 no fim [V]. O verify também a conta no início e no fim de cada corrida. Nada foi escrito em `projects/alpes` [V].

### Decisões pendentes (Tiago)
1. **D3 = A no perfil.** O alargamento faz o que a D3 quer na simetria 4.2: 3 → 0 violações, e a lista «por rever» pode ficar vazia. Mas não tira as 6 peças das Suspeitas, porque as células de uma exceção continuam listadas, com o texto da exceção. Duas perguntas:
   - **(a)** Aplicar na mesma? Isso exige mudar uma linha de `tests/test_simetria.py::test_perfil_alpes_declara_a_excecao_c32_c33` para as filas `[[1, 5], [43, 47]]` e o texto novo («confirmado pelas imagens, D3 = A»), e esvaziar `simetria_por_rever.json`. `test_simetria_sem_a_lista_por_rever_falha_nos_3_pares` passa com a lista vazia.
   - **(b)** As células da exceção devem sair das Suspeitas, ou ficar com o texto da exceção, como hoje? Se devem sair, isso é uma mudança em `src/consistency.py`, e as 18 passam a 6 com o perfil antigo ou a 0 com o novo. Não as 12 que o prompt esperava.
2. **Molde em leave-one-out só no modo completo.** Custa ≈ 100 s por causa das tiras de imagem, porque a cópia vai sem `render/fit`. No `--rapido`, o matching de `fit.py` fica coberto só pelos quadrados. Com o pre-commit, uma mudança em `fit.py` corre sempre o completo.
3. **O pre-commit lê a árvore de trabalho:** um commit de código cuja baseline só entra no commit seguinte passa (o caso de `fe0dcd5`). Fica como estava; é a ressalva 4 da ronda anterior.
4. **Exit 5 para todas as regressões dos passos 1–3**, incluindo o E-sym (critério absoluto). Querem um código próprio, por exemplo 7 para «regressão de CV»?
