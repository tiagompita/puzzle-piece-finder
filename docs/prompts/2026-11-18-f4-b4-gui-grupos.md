# 2026-11-18 — F4 B4: a GUI nova dos grupos soltos (3 etapas)

## Porquê
Os grupos soltos (secções e blocos do legado sem lugar) só se viam na Mesa da GUI antiga. O B2 e o B2b deixaram o servidor pronto (`/api/grupos*`, `mesa.jsonl`, «Fixar» com o critério único de rotação); o B4 traz-os para a GUI nova (`/novo/`): mostrar, mover, rodar, fixar e soltar, em três etapas com um commit e uma revisão do implementer cada.

## Decisões
- Do Tiago (2026-11-18): (1) lugar provável só em zonas com `dE_p90` calibrado; (2) o aviso depois de fixar não nomeia a peça («Esta peça diz outra rotação», contorno âmbar, sem `P####`/`G####`/«âncora»); (3) os candidatos não são recalculados (backlog).
- Correções ao aprovar: C1 (`rodado` é o estado de cada linha do `mesa.jsonl`, feito pelo implementer no início da etapa 2) e C2 («Mostrar no tabuleiro» fora do desfazer).
- Q1 b, Q3, Q4 b, Q5 b, Q6 b, Q8 a, Q9 c, Q10 a e `sobreposto`: em `F4_PLANO.md` §1.
- Do implementer na revisão: M1–M4 (arrasto) e B1–B2 (recarga a meio, encaixe pela célula debaixo do ponteiro).

## Prompt verbatim
**Reconstrução.** O texto original dos prompts do gestor não ficou no repositório; o que segue resume o plano aprovado (`.claude/plans/agente-implementer-skills-graphify-logical-summit.md`) e os pedidos de cada etapa, não é o texto tal como foi enviado.

- **Etapa 1 (`8f50e28`):** `src/web/novo/grupos.js`, camada `#lyr-grupos` por baixo dos alvos, comutador «Peça a peça · N | Grupos soltos · N», lista com «Mostrar no tabuleiro» (Q3), painel do grupo (Q1 b, «Peças do grupo» Saco · nº, «Levar para o lugar provável» ou «Ainda sem lugar provável fiável»), «N em grupos soltos», legenda, vazio «Não há grupos soltos.», `sobreposto` visível; ponto 1 no servidor. Testes Playwright primeiro; 1366 e 390 px sem scroll horizontal; nenhum `P####`, `G####` ou «âncora» no texto visível.
- **Etapa 2 (`5a8c598`, `99d6c9c`):** Ctrl+arrastar com encaixe às células e volta atrás sem POST numa posição inválida; «Mover» … «Feito» com rato e toque CDP; «Rodar» (Q5 b); desfazer de mover e rodar pelo `mover` inverso com a `anterior` e o `rodado` explícito; «Ver no tabuleiro» sem POST; «Levar» com `rodado: false`; critério 14 (60 passos, 32 grupos, 0 frames > 25 ms). Depois, M1–M4 da revisão.
- **Etapa 3:** «Fixar aqui» (Q8 a) com desligado em `sobreposto`; aviso âmbar (Q9 c) com «Desfazer» = `unanchor`; «Tirar o grupo inteiro do lugar» (Q10 a); B1 e B2; capturas `F4_depois_*` a 1366×768 e 390 px; documentos.

## Resultado
Commits `8f50e28`, `9e8c4b6`, `584372a`, `5a8c598`, `99d6c9c` e o da etapa 3. `board.js`, servidor (exceto o ponto 1 e a C1, do implementer) e GUI antiga sem alterações. Testes: `tests/test_gui_novo_f4.py` (40), os 12 de `tests/test_gui_novo_toque.py` e `tests/test_board_interface.py` verdes; critério 14 [V] máx. 16,8 ms, 0 frames > 25 ms. Por fazer (B5): critérios 11–13 e 15, igualdade byte a byte, OK do Tiago (PC e iPhone, fixar fisicamente ≥ 3 grupos).
