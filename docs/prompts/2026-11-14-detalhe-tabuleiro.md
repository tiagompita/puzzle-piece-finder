# 2026-11-14 — Tabuleiro: o detalhe demora e a GUI bloqueia depois de um salto (lupa / localizar)

## Porquê

Na GUI nova (`/novo/`), o Tiago usou a lupa para procurar uma peça fora da vista. O tabuleiro saltou para lá e o
raster de detalhe (`loadDetail` → `/api/board.jpg?region=` → `Gui.board_jpg`) demorou muito. Durante esse tempo a GUI
deixou de responder. O plano (em modo de plano, sem implementar) foi aprovado com condições: medir primeiro numa cópia
e implementar só A e B se os números confirmassem as hipóteses.

## Decisões

- Plano: `C:\Users\tiago\.claude\plans\agente-implementer-skills-systematic-deb-witty-pelican.md`. As condições do
  Tiago estão no topo e mandam sobre o resto.
- Os números confirmaram as duas hipóteses (`docs/diagnostico/gui/DETALHE.md` §1–§2):
  - (a) composição dentro do `rlock`: um `board.jpg` em cache esperou 1,8 s;
  - (b) sem cancelamento: 5 saltos davam 5 composições em série e o detalhe final chegava aos 7,6–8,2 s.
  - Por isso implementei A e B.
- O problema é anterior à F1 (worktree em `8fedf87^`).
- Achado fora do plano: o ranking dos buracos a frio rouba o GIL e o 1.º salto depois de abrir demora 30–34 s. Não
  corrigido (fora de A e B). Recomendado H (`sys.setswitchinterval`) com números.
- C, D, E, F e G não foram implementados. A recomendação está no §5 do DETALHE.md:
  - H → E → C;
  - D e G não;
  - F só se H não chegar.
- O critério não foi ajustado:
  - 1a (frio ≤ 1,5 s) e 1b (quente ≤ 0,3 s) ficam [F];
  - 2b fica [F] no arranque;
  - 2a, 2c e 3 ficam [V].
- O debounce de 280 ms ficou igual: tirá-lo nos saltos é uma decisão para o Tiago.

## Prompt verbatim

Skills: systematic-debugging, verification-before-completion, graphify (carrega-as com a ferramenta Skill antes de começar, se as tiveres).

Projeto: d:\DEKSTOP\puzzle_piece_finder (lê CLAUDE.md, docs/HANDOFF.md). Regra graphify: antes do primeiro grep, pesquisa ou leitura de código-fonte, corre `graphify query "<pergunta>"`; lê ficheiros só nas linhas que o grafo ou uma leitura anterior já localizaram; no fim corre `graphify update .`.

PLANO APROVADO (lê-o inteiro primeiro): C:\Users\tiago\.claude\plans\agente-implementer-skills-systematic-deb-witty-pelican.md. As «Condições de aprovação do Tiago» no topo mandam sobre o resto. Em resumo:

Problema: na GUI nova (/novo/), o Tiago usou a lupa para procurar uma peça fora da vista. O tabuleiro saltou para lá, o raster de detalhe (`loadDetail` em src/web/board.js, que chama `/api/board.jpg?region=`, servido por `Gui.board_jpg` em src/server.py) demorou muito e a GUI deixou de responder durante esse tempo. Hipóteses, a partir da leitura do código:
- (a) `board_jpg` compõe a região dentro de `with self.rlock`, por isso os pedidos de imagem ficam em série;
- (b) não há cancelamento (`new Image()`): os pedidos obsoletos esgotam as 6 ligações HTTP/1.1 do browser, uma das quais já está ocupada pelo SSE;
- cache por região exata (LRU 24), invalidada por qualquer escrita.

Passos:
1. Trabalha numa CÓPIA de projects/alpes no scratchpad (C:\Users\tiago\AppData\Local\Temp\claude\011f846714d7d8db\7f3547bc-1159-4d1d-8d5b-3c677d19ba0d\scratchpad). Nunca corras o servidor sobre projects/alpes: tem alterações por commitar e o arranque pode escrever no log. Não comites nada de projects/alpes.
2. Medições dos §1 e §2 do plano:
   - reprodução em /novo/ e em /;
   - a GUI antiga num worktree em `8fedf87^`, para ver se o problema é anterior à F1;
   - tempos do servidor por fase, tamanho da resposta, descodificação no browser, bloqueio pelo rlock e pelo GIL, contagem de pedidos obsoletos e pico em voo;
   - 3 zonas (céu, relva, vazia), 2 zooms, frio/morno/quente;
   - o cenário extra «depois de um Encaixa»: tempo até o detalhe voltar na mesma vista depois de uma gravação, nas 3 zonas, com a escrita longe e perto da vista.

   Guiões em tools/diagnostico/gui/ (salto_detalhe.py com Playwright/CDP, tempo_regiao.py). Grava a tabela em docs/diagnostico/gui/DETALHE.md, com os números etiquetados [V]/[NT]/[F].
3. Se os números confirmarem (a) ou (b), implementa SÓ A e B do §4:
   - A: compor fora do rlock, com o lock só para a cache e deduplicação de pedidos iguais em voo;
   - B: um só detalhe em voo no cliente, fetch + AbortController + blob + img.decode() + objectURL, revogando o anterior; seq no servidor para descartar composições ultrapassadas. Mantém `body.dataset.detail`.

   Junta os testes do §5 que lhes dizem respeito: identidade de píxeis do caminho novo contra `compose_board(region)`, concorrência em test_server.py com `_compose` lento, e Playwright `slow` com 5 saltos seguidos. Depois volta a medir contra o critério de sucesso. Se os números NÃO confirmarem a hipótese, PÁRA sem implementar e reporta o que encontraste.
4. NÃO implementes C, D, E, F nem G. Dá uma recomendação com números, incluindo o que o cenário «depois de um Encaixa» diz sobre os mosaicos (C).
5. Se o critério de sucesso não for atingido só com A e B, reporta-o como [F] com os números. Não ajustes o critério.

Fecho:
- suite completa com `.venv/Scripts/python.exe -m pytest tests/` (nunca o python do PATH), incluindo os testes slow da GUI;
- capturas das duas GUIs antes e depois, na mesma viewBox, em docs/gui/screenshots/ ou docs/diagnostico/gui/;
- atualiza docs/HANDOFF.md, um ficheiro novo em docs/prompts/ (formato em docs/prompts/README.md) e a linha de server.py / src/web no CLAUDE.md;
- `graphify update .`;
- commit em português, SEM linha Co-Authored-By, que liste na mensagem os testes existentes que foram alterados.

Responde com:
- a tabela de medições (antes/depois);
- se o problema é anterior à F1;
- quais hipóteses se confirmaram;
- o que foi implementado;
- o critério de sucesso item a item, cada um [V] ou [F];
- o resultado da suite;
- a recomendação sobre C–G;
- os hashes dos commits.

## Resultado

- **Medições:** `docs/diagnostico/gui/DETALHE.md`, com os dados em bruto em `docs/diagnostico/gui/dados/` e as
  capturas antes/depois em `docs/diagnostico/gui/*_{antes,depois}.png`.
- **Implementado:**
  - A em `src/server.py` (`_region_jpg`, `region_lock`, `Superseded`);
  - B em `src/web/board.js` (`loadDetail`), mais os cabeçalhos `X-Detail-Client` / `X-Detail-Seq` na rota
    `/api/board.jpg`.
- **Testes novos:**
  - `tests/test_server.py`: identidade de píxeis, rotas durante a composição, deduplicação, seq ultrapassado;
  - `tests/test_gui_novo.py::test_five_jumps_leave_one_detail_in_flight`;
  - um teste existente alterado: `tests/test_gui_novo.py::test_icons_local_aria_and_layout` passa a aceitar o `blob:` da mesma origem (o objectURL do detalhe) na verificação de «nenhum pedido fora do servidor».
- **Suite [V]:** `.venv/Scripts/python.exe -m pytest tests/`: 513 passed, 1 skipped, 0 failed (362 s, com os slow).
- **Commit:** ver `docs/HANDOFF.md` / `git log`.
- **Por fazer** (pendente técnico 7 do HANDOFF): H, E e C, e a decisão sobre o debounce. O «não responde» do Tiago
  não foi reproduzido como bloqueio do browser [NT na máquina dele].
