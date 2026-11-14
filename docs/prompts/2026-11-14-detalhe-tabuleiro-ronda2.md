# 2026-11-14 — Detalhe do tabuleiro, ronda 2: saltos sem espera, intervalo do GIL, causa do 1.º `/api/montar`

## Porquê

A ronda 1 (`2026-11-14-detalhe-tabuleiro.md`, commit `e252dc1`) fez A + B e deixou três pontas com números
(`docs/diagnostico/gui/DETALHE.md` §5): o quente falhava o critério por 10 ms por causa da espera de 280 ms também nos
saltos; o 1.º salto logo depois de abrir demorava 30–34 s porque o ranking dos buracos a frio rouba o GIL (H,
`sys.setswitchinterval`, medido só em processo); e o próprio ranking a frio (30–40 s em cada arranque) não tinha causa.

## Decisões

- **Saltos sem espera:** `zoomCells` (lupa / `showCell`, «localizar», «Ver no tabuleiro», «Localizar peça», o cartão
  seguinte depois de um «Encaixa») pede o detalhe na mesma tarefa; arrastar, roda, pinça, botões +/−, duplo clique,
  «ajustar» e redimensionar mantêm os 280 ms.
- **H adotado** contra o critério fixado pelo Tiago (detalhe melhora; reconsulta e importação não pioram > 10 %): 6
  corridas alternadas no servidor real, detalhe durante o ranking a frio 20,3 / 23,3 → 7,6 / 6,6 s (céu / relva),
  reconsulta −3 % / −5 %, importação +1,4 %. Ligado por omissão no servidor (`GIL_SWITCH_S = 0.0005`), com
  `--gil-intervalo 0` para voltar ao valor do Python. Só o servidor; CLI e testes não mudam.
- **Uma 1.ª bateria foi deitada fora:** a cópia com `cp -r` invalidava a cache do raster em disco e o arranque recompunha
  o tabuleiro inteiro por baixo das medidas (dava à reconsulta um falso −28 %). Refeita com `shutil.copytree`.
- **Achado corrigido fora do pedido:** corrida entre fios em `render._clean_or_crop` (FileNotFoundError) exposta pela
  composição de regiões fora do lock (A, ronda 1); 1 `try` + teste. Pequeno e ligado à ronda 1, por isso feito aqui.
- **Item 3 só análise** (DETALHE.md §7): o ranking em si custa < 1 s; os 24 s a frio (sozinho; 43–50 s no servidor)
  são lados erodidos (18 s) e formas (5 s) que só vivem em memória. Recomendado: lados erodidos em disco + formas lidas
  por folha, depois calcular em segundo plano ao arrancar; o ranking em disco por versão do log só se ainda fizer falta.
- E, C, D, F e G não foram tocados (ficam para depois da F2).

## Prompt verbatim

Pedido do Tiago (passado pelo gestor, com o cabeçalho `Agente: implementer. Skills: systematic-debugging,
verification-before-completion, graphify.` e notas de execução: suite com o `.venv`, tabela das 6 corridas,
verificação de caminhos antes de apagar, fechar este ficheiro e o HANDOFF, commit sem as alterações do Tiago em
`projects/alpes`):

«Segunda ronda do detalhe do tabuleiro. Trabalha sempre numa cópia do projeto.

1. Tira a espera de 280 ms nos saltos (lupa e «localizar»). Mantém-na ao arrastar e na roda. Teste que o prove.
2. Experiência com sys.setswitchinterval, sem a deixar ligada por omissão: mede com e sem ela, 3 corridas cada, o tempo do detalhe durante o cálculo a frio dos buracos, o tempo de uma reconsulta e o tempo de uma importação. Só a adotas se o detalhe melhorar e a reconsulta e a importação não piorarem mais de 10 %. Reporta os números das 6 corridas.
3. Causa de fundo, sem implementar: porque é que o primeiro /api/montar calcula 30 a 40 s a frio em cada arranque? Diz o que já fica em cache em disco e o que não fica, e propõe como evitar esse cálculo no caminho do primeiro pedido (guardar em disco com a versão do log, ou calcular em segundo plano ao arrancar com «A preparar sugestões… n de N» e o Montar utilizável entretanto). Ganho esperado e risco de cada opção.
4. Não implementes E, C, D, F nem G. Ficam para depois da F2.
5. Remove as duas cópias do projeto e os dois worktrees do scratchpad, com as mesmas verificações de caminho de antes.

Fecho: suite completa com o .venv, DETALHE.md atualizado, lista de testes existentes alterados na mensagem do commit. Usa `graphify query` antes de grep ou de ler ficheiros e corre `graphify update .` no fim. Commits sem Claude como co-author.»

## Resultado

- **Medições:** `docs/diagnostico/gui/DETALHE.md` §6 (saltos, 6 corridas do GIL, arranque, achado) e §7 (causa de
  fundo); dados em `docs/diagnostico/gui/dados/r2_*.json`; guiões novos `tools/diagnostico/gui/gil_intervalo.py` e
  `buracos_frio.py`.
- **Código:** `src/web/board.js` (`setView(vb, now)`, `fitRect(…, now)`, `zoomCells` imediato), `src/server.py`
  (`GIL_SWITCH_S`, `apply_gil_interval`, `_parser`, `--gil-intervalo`, linha do registo com o intervalo),
  `src/render.py` (`_clean_or_crop` tolera o ficheiro apagado por outro fio).
- **Testes novos:** `tests/test_gui_novo.py::test_jump_asks_detail_at_once_drag_and_wheel_keep_debounce` (Playwright,
  `slow`; falha com o `board.js` de HEAD), `tests/test_server.py::test_gil_interval_on_by_default_and_zero_keeps_python_default`,
  `tests/test_render.py::test_clean_or_crop_survives_clean_file_deleted_by_another_thread` (falha com o `render.py` de
  HEAD). Nenhum teste existente alterado.
- **Critério da ronda 1 depois desta:** 1b passa a [V] (quente 0,01–0,02 s); 1a continua [F] (frio 2,9–3,5 s neste
  projeto); 2b no arranque continua [F] (sondas 311–336 ms); o 1.º salto depois de abrir passou de ≈ 37 s para ≈ 11 s.
- **Scratchpad:** removidos os worktrees `wt_head` (com `--force`: tinha um `tests/test_server_novo_tmp.py` não seguido)
  e `wt_pref1` (+ `git worktree prune`; `git worktree list` só mostra o repositório) e as cópias `alpes_det` e
  `alpes_pref1` do scratchpad da ronda 1, depois de verificar que cada caminho resolvido estava dentro de um scratchpad,
  fora do repositório e sem ligações; a cópia desta ronda (`gil/alpes_base`) também foi apagada.
- **Suite [V]:** `.venv/Scripts/python.exe -m pytest tests/`: 516 passed, 1 skipped (PyMuPDF real no `test_sheets`), 0 failed, 437 s com os slow.
- **Commit:** ver `git log` (mensagem «Tabuleiro ronda 2: …»).
- **Por fazer:** §7 (lados erodidos em disco, formas por folha, segundo plano ao arrancar), depois E e C (após a F2).
