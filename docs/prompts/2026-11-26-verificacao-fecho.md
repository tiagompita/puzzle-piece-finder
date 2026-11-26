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

(por preencher)
