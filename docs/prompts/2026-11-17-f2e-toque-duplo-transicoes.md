# 2026-11-17 — F2e: transições, «Fechar» com ícone, toque duplo, «Ver lugar» com a sugestão do cartão

## Porquê
O Tiago testou a GUI nova no iPhone (Brave): a interface do telemóvel está boa. Pediu quatro ajustes pequenos (transições, ícone de fechar, toque duplo no tabuleiro, sugestão do cartão no painel do lugar) e a renomeação da ronda anterior de «F2c, 2.ª ronda» para F2d.

## Decisões
- As regras do Tiago e as «decisões minhas» estão em `docs/decisoes.md` (2026-11-17, F2e).
- A ronda de 2026-11-16 passa a F2d nos documentos (decisoes.md, ESPEC, HANDOFF, este diretório de prompts); o código, `tests/test_gui_novo_f2c.py` e as capturas `F2c_*` da 2.ª ronda mantêm o nome.

## Prompt verbatim
> Agente: helper. Skills: graphify (regra abaixo), test-driven-development (testes antes do código).
>
> === Pedido do Tiago (verbatim) ===
> Teste do Tiago no iPhone (Brave, 2026-11-17): a UI do telemóvel está boa. Decisões do Tiago para a GUI nova (/novo/), ronda F2e:
>
> 1. Transições: o painel do menu e os painéis laterais deslizam/aparecem a abrir e a fechar em ≈ 180 ms (ease-out). Sem animação com `prefers-reduced-motion`. Nada pode ficar mais lento a responder: o conteúdo é o de hoje, só a entrada é animada.
> 2. O botão «Fechar» (390 px) passa a um ícone X (Lucide local `x`), com `aria-label` «Fechar».
> 3. Toque duplo no tabuleiro, só com `pointerType` touch (o rato e o clique no PC não mudam):
>    - o toque simples espera ≈ 250 ms para ver se vem um segundo toque;
>    - o toque duplo aproxima 2× no ponto tocado, até uma célula ocupar ≈ ⅓ da menor dimensão do ecrã; no limite, não faz nada;
>    - o toque duplo nunca abre o painel nem escolhe cartão;
>    - a pinça e o arrasto não mudam;
>    - garante que o WebKit do iOS não faz o seu próprio zoom (`touch-action`).
> 4. «Ver lugar» vindo do cartão: o painel do lugar mostra também a sugestão do cartão ao lado da arte (imagem da peça, saco e nº, com o botão «Encaixa» igual ao do cartão) e um botão «Voltar ao cartão». Aberto de outra forma (tocar num lugar vazio), o painel fica como hoje.
> 5. Documentos: a ronda de 2026-11-16 que ficou como «F2c, 2.ª ronda com este nome» passa a chamar-se F2d em decisoes.md, ESPEC, HANDOFF e no prompt em docs/prompts/. Esta ronda é a F2e.
>
> Regras:
> - Testes Playwright antes do código, a falhar antes: toque duplo com toque emulado (aproxima, respeita o limite, não abre o painel); toque simples continua a abrir o painel/escolher o cartão; o clique de rato continua imediato; X com aria-label; painel do «Ver lugar» com a sugestão, o «Encaixa» e o «Voltar ao cartão»; animação desligada com reduced-motion.
> - Capturas a 1366×768 e 390×844, antes e depois, em docs/gui/screenshots/redesenho/F2e_*.
> - Suite completa com `.venv/Scripts/python.exe -m pytest tests/`.
> - Lista no commit os testes existentes alterados, com o motivo.
> - Commit sem co-author.
> - docs/decisoes.md (2026-11-17, F2e; escolhas que não vieram do Tiago marcadas «decisão minha»), ESPEC, HANDOFF, docs/prompts/ e `graphify update .`.
> === fim do pedido ===

(O resto do prompt do gestor era o contexto de execução: ordem antes/testes/código/depois/suite/docs/graphify/commit, relatório curto com [V]/[NT]/[F].)

## Resultado
- Código: `src/web/board.js` (toque duplo, opção `S.toqueDuplo`), `src/web/board.css` (`touch-action` no `svg#board`), `src/web/novo/{index.html,novo.js,novo.css}` (X, transições, painel com a sugestão do cartão).
- Testes novos: `tests/test_gui_novo_f2e.py` (21 casos; 16 falhavam antes do código pelas razões certas, 21 passam depois). Testes existentes alterados: `tests/test_gui_novo_f2c.py::test_menu_fills_the_phone_screen_with_fechar` (o botão deixa de ter o texto «Fechar») e `tests/test_board_interface.py` (`toqueDuplo` passa a opção declarada da casca).
- Capturas: `docs/gui/screenshots/redesenho/F2e_{antes,depois}_{ver_lugar,menu}_{1366,390}.png` (`tools/gui/f2e_capturas.py`).
- Por fazer [NT]: o iPhone real (se o WebKit deixa de fazer zoom da página), a sensação dos 180 ms e da espera de 250 ms.
