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

(por preencher)
