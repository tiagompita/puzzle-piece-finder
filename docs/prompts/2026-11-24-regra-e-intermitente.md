# 2026-11-24: regra «prompts até ao fim» e teste intermitente

## Porquê

Numa suite completa de 2026-11-24 houve 1 failed / 900 passed e o nome do teste perdeu-se; na corrida seguinte deu 901 passed. Suspeita, não provada, de `test_phone_layout_panels`. Além disso, o Tiago decidiu uma regra de funcionamento dos prompts.

## Decisões

- Regra nova no CLAUDE.md (Routing): prompts até ao fim, perguntas só no planeamento, decisões pendentes no fim do relatório; exceção: ação irreversível sobre dados (projects/alpes, images/).
- Teste intermitente: corrigir só se a causa ficar provada; senão marcar com [NT]; nunca retries.

## Prompt verbatim

Agente: helper. Skills: systematic-debugging.

1. Regra no CLAUDE.md (secção Subagents & Model Routing), decisão do Tiago: «Cada prompt faz-se até ao fim sem parar para perguntar; perguntas só no planeamento, antes de começar; decisões pendentes numa lista no fim do relatório. Exceção: uma ação irreversível sobre dados (projects/alpes, images/) para e pergunta.» Commit «docs: prompts até ao fim, decisões no fim».

2. Teste intermitente: corre tests/test_gui_novo*.py e tests/test_gui_layout.py 10 vezes com -x --tb=short e guarda a saída completa em ficheiro (sem cortes). Identifica o teste que falha e a causa (temporização, ordem, estado partilhado). Corrige se a causa ficar provada; senão marca-o com a razão [NT] e não o escondas com retries. Suite antes do commit.

Relatório palavra por palavra no ficheiro da ronda antes de responderes; decisões pendentes no fim.

## Resultado

Estado inicial: git status limpo; 39 ficheiros em projects/alpes/pieces e 39 em overlays [V]. Estado final: 39 e 39 [V].

Commits:
- 7c32cd4 docs: prompts até ao fim, decisões no fim [V] (só CLAUDE.md; bullet em «Routing», antes do da «Uma árvore de trabalho»).
- 3b797af diagnostico: 20 corridas dos testes de GUI sem falha [V] (saídas completas e resumo.md em docs/diagnostico/gui/intermitente/).

Corridas [V] (detalhe por corrida em docs/diagnostico/gui/intermitente/resumo.md):
- Lote 1, tests/test_gui_novo*.py + tests/test_gui_layout.py, 10 corridas: 10 × «218 passed», 377–388 s cada, 0 falhas.
- Lote 2, só tests/test_gui_layout.py, 10 corridas: 10 × «32 passed», ~35 s cada, 0 falhas.

Teste que falhou e causa: nenhum falhou em 20 corridas, por isso a causa NÃO ficou provada [V]. Não há prova de que seja test_phone_layout_panels; é só a suspeita inicial [NT].

Correção ou marca: nenhuma. Sem uma falha reproduzida não sei qual teste marcar, e marcar um teste às cegas seria inventar uma razão; os testes continuam todos a correr, sem retries [V].

Suite completa: não corri, porque não houve alteração de código nem de testes (só docs e saídas de diagnóstico).

Desvios ao pedido: (1) suite completa não corrida, pelo motivo acima; (2) os passos 3–6 da tarefa 2 não se aplicaram; (3) a ordem do ficheiro `_loop.sh` (script que corre as N corridas) ficou em docs/diagnostico/gui/intermitente/ para reprodução.

Decisões pendentes:
1. A falha é de uma suite completa (900+ testes), não só dos testes de GUI: a causa pode depender da ordem ou do estado deixado por testes anteriores. Queres que se corra a suite completa N vezes com `-rf` e saída gravada, para apanhar o nome do teste (cerca de 1 h por 10 corridas)?
2. Até lá, queres uma marca [NT] genérica a registar que existe uma falha intermitente sem nome? Recomendo não marcar nada.
