# 2026-11-26: verificação determinística, últimos ajustes (teste que sai, stage completo no pre-commit, código 7, molde)

## Porquê

A ronda «fecho» (`a733662`…`e299089`) deixou quatro pontos por decidir:
- com a lista «por rever» vazia, um teste de simetria passa sempre;
- com um stage parcial, o pre-commit verifica o disco em vez do commit;
- as regressões de CV saem com o mesmo código 5 das outras métricas;
- o molde do buraco só corre no modo completo.

O Tiago decidiu os quatro (prompt escrito em 2026-11-26 e corrido em 2026-11-28).

## Decisões

- Remover `test_simetria_sem_a_lista_por_rever_falha_nos_3_pares`. O teste novo `test_simetria_com_a_excecao_antiga_falha_nos_3_pares_da_d3` cobre o mesmo caso.
- O pre-commit recusa o commit quando um caminho vigiado tem alterações fora do stage ou ficheiros não rastreados. Não usa `git stash`. Os ficheiros que o `.gitignore` ignora não contam.
- As regressões de CV (passos 1–3) saem com o código 7; o 5 fica para as outras métricas. Autorizado mudar o teste dos códigos de saída.
- O molde do buraco fica só no modo completo, e isso fica escrito na skill piece-fit-matching.

## Prompt (verbatim)

> Agente: helper. Skills: cv-visual-verification.
>
> Antes de grep ou leitura de ficheiros, consulta o grafo do Graphify. No fim, corre `graphify update .`.
>
> DECISÕES DO TIAGO (2026-11-26), últimas da adaptação da verificação determinística. Regista-as em docs/decisoes.md.
>
> 1. Remover `test_simetria_sem_a_lista_por_rever_falha_nos_3_pares`: com a lista vazia passa sempre. O teste novo (exceção antiga + lista vazia → falha nos 3 pares) cobre o caso. Diz no commit qual teste saiu e porquê.
> 2. Pre-commit: antes de correr o verify, recusa o commit (exit ≠ 0, com uma mensagem clara a listar os ficheiros) se algum caminho vigiado (src/, tools/verify/, tests/golden/, projects/) tiver alterações por adicionar ao stage, ou ficheiros novos não rastreados. Sem git stash. Testes: recusa com uma alteração fora do stage; aceita com tudo em stage. Cada um falha primeiro.
> 3. Código de saída 7 no tools.verify para as regressões de CV (passos 1–3: segmentação, classificação, matching). O 5 fica para as outras métricas. Atualiza a tabela de códigos (CLAUDE.md e a skill cv-visual-verification) e o teste dos códigos de saída. Repete a prova de regressão (estragar um parâmetro da segmentação numa worktree com uma cópia do projeto real) e confirma que agora dá 7.
> 4. Molde do buraco só no modo completo: mantém; documenta-o na skill piece-fit-matching («Verificação»).
>
> REGRAS: tools.verify completo com exit 0 no fim; suite completa com .venv; vigilância 39/39/39; [V]/[NT]/[F]; um commit por ponto, sem Claude como co-author; push no fim. Relatório palavra por palavra no «Resultado» de docs/prompts/2026-11-26-verificacao-ultimos-ajustes.md.

## Resultado

Quatro pontos, um commit cada (sem Co-Authored-By); o 4.º leva também a entrada de `docs/decisoes.md`.

**Commits:**
- `33731fd` testes: sai `test_simetria_sem_a_lista_por_rever_falha_nos_3_pares` (com a lista vazia passa sempre; `..._excecao_antiga_falha_nos_3_pares_da_d3` cobre o caso). Leva o ficheiro do prompt.
- `7b80680` pre-commit: recusa o commit com alterações fora do stage ou ficheiros não rastreados nos caminhos vigiados.
- `f92f6ff` verify: código 7 para as regressões de CV dos passos 1-3; tabela de códigos no CLAUDE.md e na skill.
- `8fa2a4a` skill piece-fit-matching (molde só no modo completo) e `docs/decisoes.md`.

**Ficheiros:** `tests/test_simetria.py`; `tools/githooks/pre-commit`, `tests/test_githook_precommit_stage.py` (novo); `tools/verify/__main__.py`, `tests/test_verify.py` (2 casos acrescentados), `tests/test_verify_regressao.py` (teste autorizado, renomeado `test_codigo_de_saida_regressao_cv_e_7_e_metricas_e_5`), `CLAUDE.md`, `.claude/skills/cv-visual-verification/SKILL.md`; `.claude/skills/piece-fit-matching/SKILL.md`, `docs/decisoes.md`.

**Ponto 2:** os 5 testes de recusa falharam antes da regra (os 5 de aceitação já passavam); depois passam todos, e os 52 testes dos outros ficheiros do hook passam sem alterações [V]. Stage sem caminhos vigiados mas disco sujo em `src/`: NÃO recusa. Esse commit não corre o verify e não toca nos caminhos, e recusá-lo bloquearia commits de docs por trabalho em curso (teste `test_stage_sem_vigiados_nao_recusa_mesmo_com_o_disco_sujo`). Sem `git stash` (teste que o afirma).

**Ponto 3:** `RG.comparar` não mudou (`test_cada_regressao_e_apanhada` afirma o grupo `baseline` à saída); o remapeamento `baseline` → `regressao` é feito em `tools/verify/__main__.py` (`regressoes_cv`), código 7, prioridade 2, 3, 6, 4, 7, 5, 1. «Sem baseline» fica com 5. `test_codigo_saida_ordem` só ganhou casos.

**Prova (worktree temporária, cópia do projeto real só por `guarda.copytree`/`rmtree`, vigilância 39/39/39):**
| Caso | Código |
|---|---|
| `_SCAN_LAB_WEIGHTS` (0,5, 1, 1) → (2,0, 1, 1) | **7** (772 falhas, todas no grupo `regressao`) |
| reposto | **0** |
Worktree, junção do `.venv` e cópia removidas [V].

**Fim:** suite `.venv` 1081 passed, 1 skipped em 1267 s [V]; `python -m tools.verify` completo código 0 em 257,7 s [V]; `graphify update .` feito; vigilância 39/39/39 no início e no fim [V]. Nunca `--no-verify`, `--congelar-baseline` nem `--refresh-golden`; sem push.

**Decisões pendentes:** nenhuma. [NT] O hook novo só foi exercitado em repositórios temporários e nos 2 commits desta ronda (tools/verify, via `--rapido`), não em stages parciais reais.
