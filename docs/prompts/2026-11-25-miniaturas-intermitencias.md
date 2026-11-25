# 2026-11-25 — miniaturas dos grupos por visibilidade, cache em JPEG, intermitências de GUI

## Porquê
A ronda `215158e`/`f5439cf` pôs miniaturas de todos os grupos a descarregar depois do «pronto», e viram-se duas falhas intermitentes de GUI (`test_phone_layout_panels`, «initPointer is not defined»). O Tiago decidiu cinco pontos.

## Decisões
1. Miniaturas: só quando a linha do grupo entra na área visível da lista (`IntersectionObserver`), em fundo, detalhe primeiro; teste com a lista fechada.
2. Cache do tabuleiro fica em JPEG; a perda entre arranques é aceite (só a vista geral).
3. `CLAUDE.md`: linhas de `src/server.py` e `src/web/novo/` com a correção da cache e as miniaturas.
4. `Claude outputs/` no `.gitignore`, sem apagar.
5. 20 corridas de `tests/test_gui*.py` com a saída completa em ficheiro; causa e correção se reproduzir, senão [NT] e as assinaturas.

## Prompt verbatim
Decisões do Tiago sobre a ronda 215158e/f5439cf:
1. Miniaturas dos grupos: carregar só quando a linha do grupo entra na área visível da lista (IntersectionObserver), em fundo, com a regra do detalhe primeiro. Teste Playwright: com a lista fechada, 0 pedidos de PNG.
2. Cache do tabuleiro: fica em JPEG; regista em docs/decisoes.md que a perda entre arranques é aceite (só a vista geral; o detalhe compõe-se sempre).
3. CLAUDE.md: atualiza a linha de src/server.py e src/web/novo/ com a correção da cache (snapshot inclui placements) e as miniaturas.
4. «Claude outputs/» na raiz do repositório: não é do projeto; acrescenta-a ao .gitignore e não a apagues.
5. Testes intermitentes (test_phone_layout_panels e o carregamento do board.js): corre os testes de GUI 20 vezes com a saída completa em ficheiro; se reproduzires a falha, causa e correção; se não, regista [NT] e as duas assinaturas da falha em docs/decisoes.md.

Suite completa antes de cada commit. Relatório palavra por palavra no ficheiro da ronda antes de responderes; decisões pendentes no fim.

## Resultado
Relatório final (palavra por palavra):

**Commits:** `831ba65` (código e teste: miniaturas por visibilidade, `.gitignore`) e o commit dos documentos desta ronda (a seguir). Sem push.

**Ficheiros alterados:** `src/web/novo/grupos.js`, `tests/test_gui_novo_f4.py`, `.gitignore`, `CLAUDE.md`, `docs/decisoes.md`, `docs/HANDOFF.md`, este ficheiro.

**1. Miniaturas [V]:** `carregarPngs` só descarrega os PNG dos grupos mostrados no tabuleiro e os das miniaturas visíveis (`observarThumbs`, `IntersectionObserver` sobre `img.grp-thumb`, conjunto `thumbsVis`; chamado no fim do desenho da lista); a regra «pronto + 1.º detalhe» mantém-se. Teste novo `test_miniaturas_so_quando_a_linha_entra_na_area_visivel`: lista fechada, 0 pedidos do PNG do grupo que não está no tabuleiro (o do grupo mostrado vem na mesma, a camada precisa dele; por isso não é «0 PNG» absoluto); ao abrir a lista chega o PNG; ao fechar, nenhum pedido novo. O teste das miniaturas anterior continua verde.
**2. Cache JPEG [V]:** registado em `docs/decisoes.md` (2026-11-25).
**3. CLAUDE.md [V]:** frase datada 2026-11-25 no fim das células `src/server.py, src/web/` e `src/web/novo/` (editada com Edit).
**4. `.gitignore` [V]:** `Claude outputs/` acrescentada; a pasta não foi apagada.
**5. 20 corridas [V]:** `.venv/Scripts/python.exe -m pytest tests/test_gui*.py -p no:cacheprovider -q -rfE`, 316 testes por corrida, uma de cada vez. Saídas completas em `C:\Users\tiago\AppData\Local\Temp\claude\011f846714d7d8db\509bf5d1-dd03-4d32-b468-0575f4db7177\scratchpad\gui20\run01.log` … `run20.log` e `summary.txt` (corridas 1–3 também em `C:\Users\tiago\AppData\Local\Temp\claude\55f1d168c984626f\509bf5d1-dd03-4d32-b468-0575f4db7177\scratchpad\gui20\`; o ciclo morreu a meio da 4.ª e retomou-se com o mesmo código).
- 13 corridas verdes (316 passed): 3, 5, 6, 7, 10, 11, 12, 13, 14, 16, 17, 19, 20. 7 corridas com 1 falha (315 passed): 1, 2, 4, 8, 9, 15, 18.
- Falhas, todas em testes diferentes: corrida 1 `test_gui_novo_f2f.py::test_atual_forte_…` e corrida 8 `test_gui_novo_toque.py::test_pointercancel_in_the_middle_of_a_pinch_…` com «initPointer / initVista is not defined» em `novo.js:1486/1487` e `data-ready` nunca a chegar (um `<script>` não executou: é a assinatura do `board.js`); corridas 2 e 9 `test_gui_layout.py::test_search_in_top_bar[…]` com `wait_for_selector body[data-ready='1']` 60 s na GUI antiga; corridas 4 e 18 `test_gui_layout.py::test_tabs_in_top_bar[1024-768]` e `test_gui_detalhe_prioridade.py::…[cancel]` com `Page.goto: net::ERR_NO_BUFFER_SPACE`; corrida 15 `test_gui_holes.py::test_hole_block_layout[1366-768]` com `assert 21 >= 28`.
- `test_phone_layout_panels` não falhou em nenhuma das 20 corridas [NT].
- Causa [NT, não provada]: 2 das 7 falhas são `ERR_NO_BUFFER_SPACE` do Windows (buffers/portas do loopback); os scripts em falta e os 60 s sem `data-ready` são compatíveis com o mesmo erro num pedido de `board.js`/`grupos.js`, mas não há `requestfailed` registado para o confirmar. Correção: nenhuma (sem causa provada); proposta abaixo. Registado em `docs/decisoes.md`.

**Suite completa [V]:** 907 passed, 1 skipped, 15 min 10 s (antes: 906 passed, 1 skipped; +1 teste novo), sem falhas. `graphify update .` feito.
**Vigilância [V]:** `projects/alpes/pieces` 39 e `overlays` 39 no início e no fim; `git status` só com as alterações listadas.

**Decisões pendentes (Tiago):**
- Intermitências: aceitar a proposta de o `conftest` registar `requestfailed` por página e imprimi-los quando `wait_for_selector` falha, e só depois escolher entre repetir o `goto` e abrir menos servidores/páginas; ou deixar como está (7 em 20 corridas dos testes de GUI falham 1 teste, sempre diferente).
- Pendente de antes: texto do Montar «N grupos sem lugar: ver na interface completa»; teste físico dos grupos.
