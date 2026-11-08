# HANDOFF — 2026-11-08 (ronda 8: ventoinhas em repouso, «pelo encaixe», importação PDF/multi-ficheiro, fila de importação; fechada)

Lê isto primeiro numa sessão nova; no fim, atualiza-o e fecha o ficheiro do prompt em `docs/prompts/`.

## Estado
- **Commits desta ronda** (em `main`): `15376ff` GUI («pelo encaixe», «Pré-visualizar encaixe»); `dbd2ecd` Parte 0 antes; `32fc4dc` código (sheets/PDF, ingest em duas fases, idempotência, fila, SSE por espera, inf/NaN → null); `7cf309f` decisões/ARCHITECTURE/CLAUDE; `45d10e2` **lote 9 importado no projeto real**; `c95c43c` Parte 0 depois; docs finais. Prompt fechado: `docs/prompts/2026-11-08-r8-ventoinhas-importacao-fila.md`. Relatório da Parte 0: `docs/diagnostico/servidor/REPOUSO.md`. GUI: `docs/gui-design.md` §24 (+ nota §22).
- **Ventoinhas [V]:** a causa era um `python.exe -` órfão de um `bash -c` de uma sessão anterior do Claude Code (heredoc mal fechado às 03:23 de 2026-11-08, ronda 6), a **100 % de um núcleo durante ≈ 17 h** (9 584 s de CPU); terminado por PID às 20:48 depois de listado e justificado. Não era o servidor. Servidor em repouso (cópia, janelas de 60 s): antes 0,18 % sem separador / 0,60–0,75 % com 1 / 1,07 % com 3 (SSE por polling de 0,4 s por cliente); **depois 0,10 / 0,34 / 0,29 %** (SSE por espera). Picos normais que acabam: tiras/buracos a seguir ao arranque quando a cache não serve (≈ 2,5 min a 100 %), consulta completa depois de uma importação (≈ 80 s com 550 soltas).
- **Importação:** `python -m src.ingest <ficheiros…> --lote N` aceita imagens e PDF (JPEG `DCTDecode` extraído tal como está, sem dependência nova); dpi pelo MediaBox validado pela corda mediana das peças (aviso fora de [0,95, 1,05]) e aviso de fundo (ΔE > 15); **idempotente por sha256** (repetição «ignorada»); `n_no_lote` continua por saco (esquema inalterado). **Lote 9 no projeto real:** S0038 65 peças (1–65) + S0039 35 (66–100), dpi 300 (MediaBox 299,88 / JFIF 300), escala 1,016 / 1,012, fundo ΔE 1,5 / 3,7, 0 avisos; lista regenerada: 543 soltas, 5 entradas do saco 9 (gémeas P1343 → (2,55) `aceite`; P1383 → (40,63) e P1368 → (3,61) `ambigua`; par P1389+P1425). Os `crops/`/`pieces/`/`overlays/` do lote 9 estão só nesta máquina (ignorados pelo git): no portátil da GUI o arranque refaz os ativos como sempre.
- **Fila de importação:** `projects/<id>/import_queue.jsonl` (só-acrescentar, replay), trabalhador único sem polling, segmentação fora do `wlock`, commit por folha (1,6–4,8 s) e **uma** consulta completa por trabalho (79 s na cópia com 551 soltas) sob o lock; `POST /api/ingest` com vários ficheiros já não dá 409; as escritas da GUI esperam até 90 s («a aguardar a importação…») em vez de falhar. Um trabalho interrompido por reinício volta à cabeça da fila (as folhas já gravadas ficam ignoradas pelo sha256).
- **Testes:** suite completa **440 passed, 1 failed, 1 skipped (339 s, OpenCV 4.11)**; a falha é `tests/test_gui_guardadas.py::test_real_board_cells_without_orthogonal_neighbour_are_not_in_vai_buscar` (pré-existente desde a ronda 7: dados dos 17 contornos manuais). Novos: `test_sheets` 8, `test_ingest_multi` 6, `test_import_queue` 6, `test_server_queue` 6, `test_server_idle` 1, `test_gui_fila` 3 (`slow`). **Testes existentes alterados (declarado):** `tests/test_state.py::test_ingest_synthetic` (a 2.ª importação do mesmo ficheiro passa a ser ignorada) e `::test_relot_cli_rewrites_overlays` (3 folhas com bytes diferentes), `tests/test_gui_holes.py` («Ver no tabuleiro» só localiza; «Pré-visualizar encaixe» desenha), docstring de `tests/test_gui_buscar_buracos.py`; `tests/test_server_idle.py` tem um limite de CPU mais largo quando o processo do pytest ainda tem threads de testes de servidor anteriores (o teste duro é o nº de despertares).
- **Interpretador:** venv4 (`…/f748cb5c-…/scratchpad/venv4/Scripts/python.exe`, `PYTHONIOENCODING=utf-8`; psutil e matplotlib instalados nesta ronda). Cópias usadas: `alpes_r8` (medições), `alpes_r8_impl*` (implementer).
- **Reports:** 6 abertos (R0029–R0034), não tocados.

## O que o Tiago tem de ver na GUI
1. **Portátil:** depois do `git pull` e de arrancar o servidor, o CPU em repouso deve ficar < 1 % (Gestor de Tarefas: processo `python` do servidor). Se voltar a aquecer sem nada a correr: `Get-CimInstance Win32_Process | ? { $_.Name -match 'python' }` e procurar um `python.exe -` (órfão de ferramenta): matar **só por PID**.
2. **«Importar»** (separador): escolher vários ficheiros (JPEG/PNG/TIFF e PDF), saco, «Pôr na fila»; o `#job-pill` mostra «fila: n · a importar saco N (folha k/n)».
3. **Botão «Atividade»/«≣»** → gaveta do fundo com os separadores «Atividade» | **«Fila de importação»** (estado, folhas k/n, peças, avisos, Cancelar/Repetir/▲▼).
4. **«Vai buscar»:** chip «pelo encaixe · alta» (era «por buraco»); nos cartões pelo encaixe, «Ver no tabuleiro» só localiza e «Pré-visualizar encaixe» desenha a candidata no buraco. Saco 9: pesquisa `P1343` (gémea `aceite` em (2,55)).
5. Enquanto uma importação corre, «Coloquei»/«Não encaixa» esperam pelo lock (até 90 s na consulta final) em vez de dar «ocupado».

## Espera pelo Tiago (decisões que são dele)
1. **PDF vetorial / outros filtros (JPX, Flate):** hoje dá erro claro na folha; rasterizar a 300 dpi exigiria instalar PyMuPDF (dependência nova).
2. **Lock entre processos:** `python -m src.confirm` em simultâneo com o servidor não está protegido (pré-existente). Fazer um ficheiro de lock em `state.py` ou só avisar?
3. **Pares já registados (T0001, T0002, T0005):** as células guardadas vêm do `pair_locate` antigo (1 rotação); T0002 e T0005 reclamam as mesmas células. Relocalizar (evento novo) ou deixar?
4. Anteriores (ronda 7): `ambigua` em «Vai buscar»; p90 por zona (céu 10,6 / relva 16,1) não ativados; T0003/T0004 são gémeas?; 17 contornos manuais que inflam a silhueta; linhas `consulta` do `servidor-20261108.log`; `docs/README_proposta.md` por aprovar; P0343/P0833; c32|c33; `erro_terminal.txt`.

## Pendentes técnicos (por ordem)
1. **Passo «pares» da consulta completa** cresce com N² (53,9 s com 551 soltas): é o maior custo da consulta depois de cada importação; não otimizado.
2. **Arranque do servidor:** tiras/buracos a frio ≈ 2,5 min a 100 % de um núcleo quando `strips.npz` não serve; `GET /api/suspeitas` durante a composição do tabuleiro 10,6 s. Medido, não corrigido.
3. **Fila:** sem deduplicação entre trabalhos; `main()` do servidor não chama `gui.stop()` (thread daemon; a retoma no arranque está testada em sintético, não no real); `/Rotate` ≠ 0 em PDF real [NT]; PDF com JPX/Flate reais [NT]; botão «a aguardar a importação…» só visto em código [NT]; Firefox/Safari/toque [NT].
4. **GT fora do céu** (ronda 7): 0 gémeas e 1 buraco confirmados fora do céu; passo seguinte proposto em `docs/estado-e-plano.md` §7.
5. Anteriores: pose manual 4–9 s, falso alarme, PNG, editor de contorno (p95 0,54–0,68), detetor de peça comida, (26,1)/(25,1).

## Convenções que mordem
- Nunca `taskkill //IM python.exe`: só por PID, listado e justificado (a suite, o servidor e os LSP do VS Code são todos `python3.13.exe`).
- Heredocs com muitas aspas no Bash desta máquina falham e podem deixar um `python -` pendurado a 100 %: escrever `.py` com Write; `PYTHONIOENCODING=utf-8`; `python -u`.
- O `python.exe` do venv é um lançador: para medir CPU usar a árvore de processos (`repouso.py` já o faz).
- Nunca correr servidor/render/ingest sobre `projects/alpes` para medir: cópias; a importação real do lote 9 foi a única escrita no projeto (com `git status` limpo antes e commit a seguir).
- `tools/diagnostico/**` precisam de `PPF_SCRATCH`. Commits em português, sem co-author. Suite completa > 300 s: em segundo plano.

## Links
- Ronda 8: `docs/diagnostico/servidor/REPOUSO.md` (+ `repouso_antes*.json`, `repouso_depois.json`, `tools/diagnostico/servidor/repouso.py`), `docs/gui-design.md` §24, `docs/decisoes.md` (2026-11-08, ronda 8), `docs/revisao.md`, `ARCHITECTURE.md` (`sheets.py`, `import_queue.py`, `ingest.py`), prompt `docs/prompts/2026-11-08-r8-ventoinhas-importacao-fila.md`.
- Ronda 7: `docs/diagnostico/gemeos/R7_RESULTADOS.md`, prompt `docs/prompts/2026-11-08-r7-falhas-fora-do-ceu.md`.
- Comandos: `python -m src.reports --project projects/alpes --list`; `python -m src.consistency --project projects/alpes`; `python -m src.fit --project projects/alpes --relatorio`; `python -m src.ingest <ficheiros…> --lote N --project projects/alpes`; `python -m src.server --project projects/alpes`.
