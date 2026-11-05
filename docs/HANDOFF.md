# HANDOFF — 2026-11-05

Lê isto primeiro numa sessão nova; no fim, atualiza-o e fecha o ficheiro do prompt em `docs/prompts/`.

## Estado
- **Último commit de código:** `25df1a9` (painel de Reports). Antes: `2c15ef6` (aba «Guardadas»), `d5cc1a7` (interface), `e6ce712` (reconsulta incremental + `docs/decisoes.md`). Os commits dos docs desta ronda vêm a seguir (`git log`).
- **Testes:** 160 passed, 1 skipped (`pytest tests/`, inclui Playwright `slow`). `tools/gui/screenshot.py` corre (17 capturas, exit 0).
- **GUI** (`python -m src.server`): «Vai buscar» só com peças que têm ≥ 1 vizinha **ortogonal** montada (diagonal e moldura não contam; borda colocada conta); as outras estão na aba «Guardadas» (recolhida, aviso «Não procurar ainda»). Aba «Reports» só de leitura (lista, filtro aberto/resolvido, contagem). Tiago confirmou na GUI.
- **Item 2 (trim 0,48 mm) refutado e removido:** piora 44 células, melhora 0 (`docs/decisoes.md`). A cor ficou adiada.
- **Reports:** R0013–R0017 fechados (nota «verificado pelo Tiago na GUI, 2026-11-05, + testes»). **22 abertos:** R0001–R0012, R0018–R0027. Nenhum outro foi fechado.
- **Dados do Tiago por commitar:** `projects/alpes/` (log, reports, fetch, board, capturas R0021–R0027…) mudou por uso da GUI; não foi commitado por mim.

## Espera pelo Tiago
- **Confirmação física de (3,32) e (3,33).** P0291 (G0021) e P0294 (G0023) estão digitalizadas, mas só como pista (`ocupada_legado`, fonte `tiago`). Indício do encaixe dos lados: **P0294 em (3,32) e P0291 em (3,33)**; o score do programa diz o contrário por 0,3 (7,25 vs 8,10), por isso decide a peça física. Escala não calibrada [NT]. Depois: `python -m src.confirm` para colocar.

## Próxima sessão (pedidos do Tiago, ainda não feitos)
1. **Abas na barra de topo.** As abas (Vai buscar, Guardadas, Lotes, Mesa, Importar, Reports) não cabem na barra lateral e «Reports» fica fora do ecrã (visível em `desktop_1366_100`). Mover as abas para a barra de topo, junto ao nome do puzzle/peças/progresso (estilo barra de homepage); sem scroll horizontal; testar a 1366×768 e à largura de telemóvel (`tests/test_gui_layout.py`, `tools/gui/screenshot.py`).
2. **«Editar report» em vez de «Reportar»** ao clicar numa peça que já tem report (evitar duplicados). `reports.jsonl` é append-only: editar = acrescentar um evento de edição, não reescrever.
3. **Triagem dos reports abertos** que esta ronda não resolveu: corrigir, explicar ou fechar (cada um com `--close R#### --nota`).
4. **Pendentes (a)–(e) do `CLAUDE.md`**, por ordem: recorte «comido» (3,64) P0234 / (4,64) P0233 (R0018–R0020); baseline de buracos (131 células > 5 %, 39 > 10 %) e erro de pose ~1 mm / rotação 363/588 > 1,5°; (26,1)/(25,1) a 0,06 mm mas (26,1) parece por baixo (ordem de desenho dos tabs); (1,63) e (47,2) inclinadas; coordenadas dos reports (usar IDs P0xxx; (44,55) e (40,63) não existem, P0778 está em (4,10)).
5. **Confirmação física (3,32)/(3,33):** ver acima.

## Convenções que mordem
- Interpretador: `.venv\Scripts\python.exe` (o `python` do PATH não tem numpy).
- Commits em português, sem co-author. Item 2 já não existe no código.
- Suite completa passa dos 120 s: corre-a em segundo plano.
- Testes sobre o Alpes real usam uma cópia com o `log.jsonl` cortado a 2045 eventos (`tests/test_fetch_group_real.py`); nada se escreve em `projects/alpes`.

## Links
- Estado e plano: `docs/estado-e-plano.md`; arquitetura: `ARCHITECTURE.md`; GUI: `docs/gui-design.md`; decisões: `docs/decisoes.md`.
- Prompts por ronda: `docs/prompts/` (formato em `docs/prompts/README.md`); a desta ronda: `docs/prompts/2026-11-02-cor-recorte-coloca-agora.md`.
- Reports: `python -m src.reports --project projects/alpes --list`.
