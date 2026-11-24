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

Desvios ao pedido: (1) suite completa não corrida, pelo motivo acima; (2) os passos 3–6 da tarefa 2 não se aplicaram; (3) o `_loop.sh` (script que corre as N corridas) ficou em docs/diagnostico/gui/intermitente/ para reprodução.

Decisões pendentes:
1. A falha é de uma suite completa (900+ testes), não só dos testes de GUI: a causa pode depender da ordem ou do estado deixado por testes anteriores. Queres que se corra a suite completa N vezes com `-rf` e saída gravada, para apanhar o nome do teste (cerca de 1 h por 10 corridas)?
2. Até lá, queres uma marca [NT] genérica a registar que existe uma falha intermitente sem nome? Recomendo não marcar nada.

## Verificação do gestor (relatório final ao Tiago)

As duas tarefas estão feitas. A falha intermitente não se reproduziu em 20 corridas, por isso nenhum teste foi corrigido nem marcado.

**Regra no CLAUDE.md** [V]
- Commit `7c32cd4`. O texto é exatamente o teu e está na lista «Routing» da secção «Subagents & Model Routing».

**Teste intermitente** [V]
- 10 corridas de `tests/test_gui_novo*.py` + `tests/test_gui_layout.py`: todas com 218 passed, entre 377 e 388 s cada.
- Mais 10 corridas só de `tests/test_gui_layout.py`: todas com 32 passed, cerca de 36 s cada.
- Contei eu as 20 saídas completas: nenhuma tem «failed» e todas acabam com rc=0.
- As saídas estão em `docs/diagnostico/gui/intermitente/`, no commit `3b797af`.
- Causa: não provada. A suspeita sobre `test_phone_layout_panels` continua por provar [NT].
- Não pus marca nem retry: sem saber o nome do teste, uma marca seria inventada.
- A suite completa não correu, porque não houve mudanças de código nem de testes.

**Correções minhas a esta ronda**
- O «Resultado» acima é um resumo do relatório do helper, não o texto palavra por palavra. Este bloco é o relatório que te dei.
- Corrigi uma frase sem sentido no desvio (3).

**Commits** (sem co-autor e sem push)
- `7c32cd4`, `3b797af` e `dfb9325`.
- Mais o commit deste fecho, «docs: verificação do gestor na ronda regra/intermitente».
- `pieces/` e `overlays/` mantêm-se em 39 e 39.

**Decisões pendentes**
1. A falha original apareceu numa suite completa de 901 testes. Estas 20 corridas só cobriram os testes de GUI, por isso pode depender da ordem ou do estado deixado por outros ficheiros. Recomendo não gastar 1 h a correr a suite completa 10 vezes. Em vez disso, de agora em diante a suite completa corre sempre com `-rf` e a saída gravada sem cortes, e assim a próxima falha já traz o nome. Se quiseres a caça ativa, diz e corre-se.
