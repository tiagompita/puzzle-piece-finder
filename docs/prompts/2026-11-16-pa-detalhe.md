# 2026-11-16 — P-a: o detalhe sem disputa com /api/board, /api/ghosts e /api/montar depois de uma escrita (última ronda do critério 3)

## Porquê

Em `docs/diagnostico/gui/DETALHE.md` §13.9 o «perto» (do fim do POST de um «Encaixa» ao detalhe da versão nova no
ecrã) ficou em 1,21 s contra o alvo de 1,2 s [F]. A P-b tirou o registo na hora (`_piece_jobs` 1,21 → 0,24 s); o que
sobrava era a disputa do GIL com os três pedidos que o browser faz no `board_changed` (`/api/board`, `/api/ghosts`,
`/api/montar`), todos em `foreground()` desde `f85c092`: com eles retidos no lançador o «perto» ficava em 0,38 s.

## Decisões

- Comparar duas formas no lançador antes de escrever código de produto: (a) o browser atrasa os pedidos que não se
  veem até o detalhe chegar; (b) o servidor dá prioridade ao detalhe e os três cedem-lhe. Espera sempre limitada
  (≤ 1 s); um detalhe cancelado, 409 ou falhado nunca bloqueia o resto; nas duas GUIs.
- Correções do Tiago ao plano: regra de escolha completa (a mais simples, salvo a outra dar um «perto» melhor em mais
  de 0,1 s); X = 50 ms no teste da (b); paragem alargada sem commit do código (próximo cartão > +0,25 s, IC do POST ou
  do critério 2 sem excluir +0,25 s); GUI antiga só com o auxiliar comum em `core.js` e um teste; última ronda do
  critério 3 (se falhar, regista-se e não se abre outra).
- Plano aprovado: `C:\Users\tiago\.claude\plans\agente-implementer-skills-graphify-parsed-brook.md` (fora do repositório).

## Prompt verbatim

Agente: implementer. Skills: /graphify  /systematic-debugging  

Regra do grafo: `graphify query/path/explain` antes de qualquer grep ou leitura de ficheiros; `graphify update .` no fim de cada bloco. Se não tiveres a ferramenta de skills, segue estas regras tal como estão.

Objetivo: P-a (DETALHE §13.9). Tirar a disputa entre o detalhe e /api/board, /api/ghosts, /api/montar depois de uma escrita. Esta é a última ronda do critério 3.

Passo 0 (medir, sem mexer em src/):
- Quanto custa ao «perto» cada um dos 3 pedidos separadamente (atrasar só um de cada vez, no lançador de diagnóstico).
- Tempo até o próximo cartão do Montar aparecer depois de «Encaixa», hoje.

Plano:
- Compara duas formas: (a) o browser atrasa os pedidos; (b) o servidor dá prioridade ao detalhe (o f85c092 pôs os três em foreground()).
- Preferir atrasar só os pedidos que não se veem.
- Espera sempre limitada (por exemplo, ≤ 1 s): um detalhe cancelado, 409 ou falhado nunca bloqueia o resto.
- Tem de funcionar nas duas GUIs.

Critérios fixados antes (não ajustar):
- «perto» ≤ 1,2 s (mediana);
- o próximo cartão não pode atrasar mais do que +0,25 s (IC 95 %);
- POST «Encaixa» e critério 2 sem regressão (IC 95 % que exclua +0,25 s).
Medição: 10 pares alternados 8668365 | novo, cada versão numa cópia completada pelo seu próprio código (corrige o viés de §13.9). Reporta srv_frio_relva_s.

Testes: antes do código, um teste da espera limitada com um detalhe cancelado. Suite completa com `.venv/Scripts/python.exe -m pytest tests/`; test_concorrencia 20/20.

Regras: trabalha em cópias; nunca em projects/alpes. Um commit por bloco, sem co-author; lista no commit os testes existentes alterados (esperado: nenhum).

Paragem: se o «perto» ficar acima de 1,2 s, não afines nada e reporta.

Fecho: DETALHE §13.10, decisoes.md, HANDOFF, docs/prompts/.

### Correções do Tiago ao plano (verbatim)

Plano aprovado com estas correções:

1. Regra de escolha completa: se (a) e (b) cumprirem os critérios, fica a mais simples (menos ficheiros, sem bloqueios novos), a não ser que a outra dê um «perto» melhor em mais de 0,1 s (mediana).
2. Teste da (b): X = 50 ms.
3. Paragem alargada: parar sem commit do código também se o próximo cartão atrasar além de +0,25 s ou se o IC do POST ou do critério 2 não excluir +0,25 s.
4. GUI antiga: só o auxiliar comum em core.js e um teste; nenhum trabalho específico além disso (sai na F6).

Esta é a última ronda do critério 3: se falhar, regista-se em DETALHE e HANDOFF e não se abre outra.

O resto mantém-se.

## Resultado

Ver `docs/diagnostico/gui/DETALHE.md` §13.10 e `docs/diagnostico/gui/dados/r10_pa_*.json`. Resumo:

- **Passo 0 [V]:** «perto» com cada pedido retido em separado (normal 0,73 s nesta sessão): `/api/board` 0,66,
  `/api/ghosts` 0,51, `/api/montar` 0,43, os três 0,33 s. (a) 0,37 s, (b) 0,25 s, (b) sem `/api/montar` 0,43 s. Próximo
  cartão hoje 1,77 s. **Escolha: (b)** (melhor em 0,12 s > 0,1 s).
- **Bloco 1 (`a655066`) [V]:** só `src/server.py` (`DetailFirst`, `Gui.priority`, `Gui.after_detail`,
  `DETALHE_ESPERA_S` = 1,0 s). 12 testes novos (antes 11 falham, 1 passa; depois 12/12); testes existentes alterados:
  nenhum; suite 660 passed, 1 skipped; `test_concorrencia` 20/20.
- **10 pares `8668365 | novo` [V]:** «perto» 2,24 → 0,28 s (alvo 1,2); próximo cartão +0,02 s (IC [−0,02, +0,09]);
  POST «perto» −0,14 s (IC [−0,20, −0,12]); salto a frio no browser −0,05 s (IC [−0,09, −0,04]); `srv_frio_relva_s`
  1,07 → 1,02 s; memória +52 MB. **Critério 3 fechado**, sem paragem.
- **Por fazer:** o 1.º salto (critério 1).
