# 2026-11-18 — F2f: as sugestões aparecem sempre no tabuleiro (GUI nova)

## Porquê
Teste do Tiago à GUI nova (`/novo/`): com outro lugar selecionado ou o painel de um lugar aberto, os alvos da fila desapareciam do tabuleiro, e só as 3 peças seguintes tinham alvo. Pediu que as sugestões estejam sempre à vista.

## Decisões
- OK do Tiago da F1b à F2e (ESPEC §7, `docs/decisoes.md`).
- Alvos de todas as entradas da fila sempre desenhados; atual forte com rótulo, outros ténues sem rótulo; os ténues somem abaixo de um zoom (escolhido: célula < 16 px no ecrã); tocar num ténue à vista escolhe o cartão; seleção de um lugar distinta; os alvos acompanham a fila.
- Decisões minhas (limiar 16 px, ténues escondidos não roubam o toque, atual forte também com painel aberto, estilo da seleção): `docs/decisoes.md` (2026-11-18, F2f).

## Prompt verbatim
Decisões do Tiago (2026-11-18):
(1) OK da F1b à F2e (registar no ESPEC §7 e em docs/decisoes.md);
(2) ronda F2f: as sugestões aparecem sempre no tabuleiro.

F2f, GUI nova (/novo/):
- Os alvos de TODAS as entradas da fila do Montar (incluindo os cartões «Colocar aqui») ficam desenhados sempre, mesmo com outro lugar selecionado ou com o painel de um lugar aberto.
- O alvo do cartão atual fica como hoje (forte, com o rótulo e o limiar de zoom da F2d); os outros ficam ténues, sem rótulo.
- Os alvos ténues desaparecem abaixo de um zoom em que deixam de ser úteis (por exemplo, célula < 12 px no ecrã; diz qual ficou), para não encher o ecrã com o tabuleiro inteiro à vista.
- Tocar num alvo ténue escolhe esse cartão (regra de hoje). A seleção de um lugar continua visível e distinta dos alvos.
- Os alvos acompanham a fila: um cartão que sai da fila (Encaixa, Não pertence, desfazer) tira ou repõe o seu alvo sem recarregar a página.

Regras:
- Testes Playwright antes do código (a falhar antes): alvos de vários cartões visíveis com outro lugar selecionado; atual forte e outros ténues; limiar de zoom; tocar num ténue escolhe o cartão; o alvo some depois de Encaixa e volta com o desfazer.
- Capturas a 1366×768 e 390×844, antes e depois, em docs/gui/screenshots/redesenho/F2f_*.
- Suite completa com `.venv/Scripts/python.exe -m pytest tests/`, sem nenhum outro agente a editar a pasta ao mesmo tempo.
- Lista no commit os testes existentes alterados, com o motivo.
- Commit sem co-author.
- Se ainda não estiver registada, regista a regra «nunca correr a suite ou medições enquanto outro agente edita a mesma árvore; em paralelo só com worktrees separados» em CLAUDE.md e em decisoes.md.

Fecho:
- docs/decisoes.md (2026-11-18, F2f; escolhas que não vieram do Tiago marcadas «decisão minha»);
- ESPEC;
- HANDOFF;
- docs/prompts/;
- `graphify update .`.

(Notas do gestor ao helper: a regra da árvore de trabalho já estava registada no commit `a684a45`; o ficheiro de prompt e o relatório final curto.)

## Resultado
- `src/web/novo/novo.js` (`drawTarget`, `celulaPx`, `FRACO_MIN_PX`, `updateAlvoTag`, `S.onBoardTap`), `novo.css`, legenda em `src/server.py`; `board.js` não mudou.
- Testes novos `tests/test_gui_novo_f2f.py`: 7 (5 falhavam antes do código); testes existentes alterados: nenhum. Suite completa: 723 passed, 1 skipped.
- Capturas `F2f_{antes,depois}_{cartao,painel,inteiro}_{1366,390}.png`; desempenho (60 cartões extra): `drawTarget` 0,45 ms, 0 frames perdidos num arrasto [V, Chromium headless].
- Por fazer / [NT]: telemóvel real, fila real de dezenas de cartões, o Tiago confirmar o limiar de 16 px.
