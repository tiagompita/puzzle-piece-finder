# HANDOFF — 2026-11-08 (ronda 6: buracos `alta` em «Vai buscar», registo de atividade, pares de pose; fechada)

Lê isto primeiro numa sessão nova; no fim, atualiza-o e fecha o ficheiro do prompt em `docs/prompts/`.

## Estado
- **Commits desta ronda** (em `main`): `af9f2a7` critérios antes do código (`M11_CRITERIOS.md` §8 + `decisoes.md`); depois: Partes 1 e 2 (fit/state/confirm/server/GUI + `src/activity.py` + testes), Parte 3 (`render.pose_brief(full)`, `overrides.pose_pairs`, `POSE_MANUAL.md`), docs. Ver `git log`.
- **Decisão do Tiago registada** (`docs/decisoes.md` 2026-11-08): os 10 buracos `alta` do M11 confirmados fisicamente (10/10 rank 1, Wilson 72–100 %, todos céu) → as sugestões `alta` entram em «Vai buscar»; média / baixa (= `media` com 1 vizinha) / sem numa página própria; rejeição em um clique; contador + **pausa a ≥ 3 rejeições nas últimas 20 decisões** desde a última reativação (sensibilidade: 7,5 % de falsos alarmes a 95 % de precisão, 32 % a 90 %, 79 % a 80 %; `ALTA_JANELA`/`ALTA_MAX_FALHAS` em `src/fit.py`).
- **Servidor real na cópia de `projects/alpes` [V]:** arranca com as linhas de atividade no terminal e em `logs/servidor-20261108.log`; `/api/status.contador_alta` 10/0/10; buracos 209 × 122 soltas em 27,9 s (366 tiras em cache); **0 buracos `alta` agora** (38 média, 171 sem): depois das colocações do Tiago a pool de soltas já não tem nenhuma sugestão `alta` → «Vai buscar» mostra a linha «por buraco · alta em pausa/0 sugestões · acertos 10 / falhas 0 / total 10 · precisão 100 % (IC 72–100 %)» e os cartões por buraco só voltam quando entrarem soltas novas (scan de um saco).
- **Testes:** suite completa: **388 passed, 1 skipped (284 s)** (OpenCV 4.11, venv4; uma primeira corrida deu 5 falhas de layout da barra do topo com o 4.º toggle «Atividade» a 360/390/1181 px, resolvidas pondo o botão nos controlos de zoom abaixo de 1300 px; OpenCV 5.0 [NT]). Novos: `test_fit_alta` 9, `test_server_alta` 5, `test_activity` 5, `test_overrides_poses` 3, `test_gui_buscar_buracos` 4 (3 viewports + fluxo rejeitar rank 2 → pausa → reativar), `test_gui_atividade` 3. **Nenhum teste existente alterado.** `test_gui_flows::test_cell_hint_flow` falhou uma vez a meio da ronda (corrida à gaveta da célula depois de `holes_changed`): corrigido na GUI (o `holes_changed` refaz só o bloco «Candidatas», não a gaveta inteira), passou depois.
- **Repetição de «tabuleiro 1 células recompostas» [NT na máquina do Tiago]:** não se reproduziu na cópia (pedido do browser durante o arranque + `rebuild_stale` a acrescentar `piece_resegmented`: 1 linha, porque re-segmentar uma solta não muda o snapshot do tabuleiro). Única via no código para duas linhas: duas versões do log diferentes (escrita entre elas ou `log.jsonl` mudado por fora). A linha traz agora as células, `versão do log a → b` e o gatilho (`arranque` / `escrita` / `externo` / `pedido`): a próxima ocorrência lê-se no ficheiro do dia.
- **Pares de pose (só medição):** `pose_set.antes` leva a pose automática inteira (pivô, resíduos, `corner_k`, `rotation`); `python -m src.overrides --project projects/alpes --pares` → secção «Poses manuais»: n = 4 (céu; dx 0,27/0,64/1,01/0,09, dy −0,37/0,55/0,00/0,82, Δθ 0/−4,1/0/0; |d| média 0,78 mm IC95 [0,41, 1,15]); por direção n = 1–2 (sem IC útil). Resposta ao (b) em `POSE_MANUAL.md` (última secção): ≈ 20–25 poses por zona (isotrópico) ou 60–100 no total (direcional) **com peças de reserva ao acaso** (as poses manuais são a cauda: viés de seleção); parâmetros candidatos listados; nada ligado.
- **Interpretador:** `C:/Users/Tiago/AppData/Local/Temp/claude/c--Users-Tiago-Desktop-puzzle-piece-finder/f748cb5c-95ce-4ca7-bb40-feccfde7cc64/scratchpad/venv4/Scripts/python.exe` (`PYTHONIOENCODING=utf-8`).
- **Projeto `projects/alpes`:** intocado nesta ronda (só leituras: `--relatorio`, `--pares`); o servidor correu numa cópia no scratchpad. `git status` limpo em `projects/alpes` antes e depois.
- **Reports:** 0 abertos. Suspeitas inalteradas (P0343 melhor rotação, 12 recorte do bloco c32|c33).

## O que o Tiago tem de ver na GUI
1. **«Vai buscar»**: linha de estado no topo com o contador (`acertos 10 / falhas 0 / total 10 · precisão 100 % (IC 95 % 72–100 %) · últimas 10: 0 falhas`); hoje 0 cartões «por buraco · alta» (sem soltas `alta` na pool). Quando houver, aparecem depois dos cartões de gémea de cada saco, com o chip ciano, a candidata desenhada no buraco com as vizinhas, «Coloquei» / «Não encaixa» / «Ver no tabuleiro». Mesma peça e célula na gémea e no buraco = um só cartão com os dois chips.
2. **Pesquisa `buracos`** (ou o botão «Buracos: média, baixa e sem fiável» no fim de «Vai buscar»): grupos «média» (38), «baixa (1 vizinha)», «sem candidata fiável» (171); clicar numa linha abre as 3 melhores desenhadas no buraco, com «Não encaixa» em um clique (grava rank, custo, margem, confiança, versão) e «Abrir célula».
3. **Aviso de pausa**: só aparece se nas últimas 20 decisões `alta` houver ≥ 3 «Não encaixa»; o botão «Reativar sugestões alta» recomeça a janela.
4. **Botão «Atividade»** na barra (ao lado de «Sugestões»): gaveta no fundo com as linhas do servidor em tempo real, filtros por tipo e nível; o ficheiro do dia está em `projects/alpes/logs/`.

## Espera pelo Tiago (decisões que são dele)
1. **Fora do céu:** não há nenhuma decisão `alta` fora do céu; para medir a precisão em relva/vale/montanha é preciso digitalizar sacos novos (as soltas de hoje não dão `alta`). `T_abs` único fica de reserva até essa GT.
2. **`projects/alpes/erro_terminal.txt`** está no git (`81e43bb`) e é só o traceback de Ctrl+C do uvicorn: apagar do repositório é decisão do Tiago (não foi tocado).
3. **Limiar 3/20:** aceite como está; se quiseres menos falsos alarmes a 90 % de precisão, 4/20 dispara em 13 % das janelas a 90 % (e em 59 % a 80 %); está tudo em `M11_CRITERIOS.md` §8.
4. Pendentes anteriores (rondas 4–5): confirmar fisicamente P0343 (5,20) e P0833 (8,2); P0844/P0879/P0852 (tab recuperado); validação do editor de contorno (10–12 recortes); c32|c33.

## Pendentes técnicos (por ordem)
1. **M11 / sugestões `alta`:** precisão fora do céu [NT]; `T_abs` por zona (reserva); tempo das tiras a frio no projeto real com progresso n/N [NT: na cópia estavam todas em cache]; o cartão fundido só foi testado com um `fetch.json` sintético (a proposta de gémea e o buraco coincidirem no mesmo scan real [NT]).
2. **Atividade:** o `ppf.evento` escreve uma linha por evento também nos `ingest_all`/rebuilds longos (centenas de linhas: aceitável no ficheiro, ruidoso na consola; se incomodar, baixar o nível desse tipo nesses CLIs); o anel guarda 300 linhas; `--lan` sem login continua igual.
3. **Pose manual** (ronda 4): gravar/repor 4–9 s; `rebuild_stale` apaga poses manuais das folhas re-segmentadas; Firefox/Safari/toque físico [NT].
4. **Falso alarme**, **PNG**, **editor de contorno**, **detetor de peça comida**, **(26,1)/(25,1)**, lados F com reta RMS > 0,15 mm: como antes.

## Convenções que mordem
- `tools/diagnostico/fit/*.py` precisam de `PPF_SCRATCH` fora do repo; só leem o projeto.
- Nunca correr o servidor nem ferramentas de render sobre `projects/alpes` para medir: usar uma cópia (o servidor escreve `render/gui`, `placements.json` e pode acrescentar `piece_resegmented` ao arrancar).
- Escrita no log só por `src.confirm` (inclui `--buraco`/`--buraco-rejeitar`)/`src.reports`/`src.consistency --falso-alarme`/`rebuild_scans`/o servidor; `ingest_all.py` refaz o log e perde as colocações do Tiago: não usar.
- Em `Bash`, heredocs com muitas aspas falham: escrever um ficheiro `.py` com a ferramenta Write e correr; consola cp1252: `PYTHONIOENCODING=utf-8`; a saída de um processo redirecionada só aparece no fim (usar `python -u`).
- Commits em português, sem co-author. Suite completa > 200 s: em segundo plano.

## Links
- Ronda 6: `docs/diagnostico/fit/M11_CRITERIOS.md` §8 (regra e sensibilidade), `docs/decisoes.md` (2026-11-08), `docs/gui-design.md` §22–§23, `docs/diagnostico/render/POSE_MANUAL.md` (pares de pose), `ARCHITECTURE.md` (`activity.py`, `fit.py`, `server.py`), prompt `docs/prompts/2026-11-08-buracos-vai-buscar-atividade-poses.md` (fechado).
- Rondas anteriores: `M11_RESULTADOS.md`, `docs/diagnostico/reports/FALSOS_ALARMES.md`, `COMIDO.md`, `TRACOS.md`, `RENDER.md` §4.1; prompt anterior `docs/prompts/2026-11-07e-m11-molde-do-buraco.md`.
- Comandos: `python -m src.reports --project projects/alpes --list`; `python -m src.consistency --project projects/alpes`; `python -m src.fit --project projects/alpes --relatorio` (contador incluído); `python -m src.overrides --project projects/alpes --pares` (contornos + poses); `python -m src.server --project projects/alpes` (registo em `projects/alpes/logs/`).
