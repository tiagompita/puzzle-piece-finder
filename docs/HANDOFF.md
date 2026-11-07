# HANDOFF — 2026-11-07 (ronda 5: M11 «molde do buraco» como ranking, `src/fit.py`; fechada)

Lê isto primeiro numa sessão nova; no fim, atualiza-o e fecha o ficheiro do prompt em `docs/prompts/`.

## Estado
- **Commits desta ronda** (em `main`): `f6cc2b7` critérios antes de correr; `5a7b46c` `src/fit.py` + eventos + porta de sanidade; depois: afinação (`puzzle.json` `calibration.buraco`), validação + figuras (`docs/diagnostico/fit/M11_RESULTADOS.md`), GUI (`src/server.py` `/api/holes`, `src/web/holes.js`, secção «Buracos» (botão no fim de «Vai buscar», sem 7.ª aba)), docs. Ver `git log`.
- **Resultado do M11 (ranking):** validação em 214 buracos de folhas e zonas fora da afinação: **E5 estrito top-1 98,1 % (IC 95,3–99,3) a N = 32 e 96,2 % (92,8–98,1) a N = 100 [V]**; top-3 99,8 / 99,0 %. Peça ausente **[F]** na utilidade (falsas `alta` 0,091 por buraco, precisão 49 % a π = 10 %, 8 % a π = 1 %): é ranking, não proposta; nada entra em «Vai buscar». Tabuleiro real: 15/15 top-1 (n < 20, [NT]); 8 buracos `alta` em 212 (0,06 por solta [V]).
- **Testes:** suite completa **359 passed, 1 skipped (247 s)** (OpenCV 4.11, venv4), com os 20 testes novos (`test_fit` 9, `test_state_holes` 4, `test_server_holes` 3, `test_gui_holes` 4); OpenCV 5.0 [NT]. Nenhum teste existente alterado (uma 7.ª aba teria partido 10 testes de layout: por isso «Buracos» é uma secção com botão, não uma aba).
- **Interpretador:** `C:/Users/Tiago/AppData/Local/Temp/claude/c--Users-Tiago-Desktop-puzzle-piece-finder/f748cb5c-95ce-4ca7-bb40-feccfde7cc64/scratchpad/venv4/Scripts/python.exe` (`PYTHONIOENCODING=utf-8`). As ferramentas do E-fit/M11 precisam de `PPF_SCRATCH` (cache de tiras `strips_cache.npz`, `gt_pairs.json` regenerado por `gt.py`, `m11_validacao_rows.json`).
- **Projeto `projects/alpes`:** só `puzzle.json` mudou (bloco `calibration.buraco`); log intocado (2113 eventos, 958 peças, 614 colocadas, 134 `solta`). `render/fit/strips.npz` (cache ignorada) é criado na primeira abertura de `/api/holes` ou do `python -m src.fit` (≈ 3 min para as ≈ 600 peças montadas; depois segundos).
- **Reports:** 0 abertos (o Tiago fechou os últimos 7 em `971fa91`). Suspeitas inalteradas (P0343 melhor rotação, 12 recorte do bloco c32|c33).

## Espera pelo Tiago (decisões que são dele)
1. **Confirmar fisicamente os 8 buracos `alta` do tabuleiro real** (todos céu; abrir a célula na GUI → «Candidatas para este buraco», ou pesquisar `buracos` para a lista; o botão «Buracos: candidatas por confiança» no fim de «Vai buscar» faz o mesmo): (3,28) ← P0133 saco 1 nº 40 (**coincide com a proposta de gémea já aceite em «Vai buscar»**), (4,39) ← P0122 saco 1 nº 29, (6,21) ← P0123 saco 1 nº 30, (2,37) ← P0177 saco 2 nº 34, (5,26) ← P0179 saco 2 nº 36, (7,7) ← P0139 saco 1 nº 46, (3,46) ← P0135 saco 1 nº 42, (13,63) ← P0125 saco 1 nº 32 (a afetação conjunta dá esta célula a P0954: ver as duas). «Coloquei» / «Não encaixa» gravam `hole_confirmed`/`hole_rejected`: é a verdade de terreno que falta. Depois: `python -m src.fit --project projects/alpes --relatorio`.
2. **Peças fora do céu:** o GT real só tem céu. Para decidir o M11 (§15.6: n ≥ 60, ≥ 40 com ≥ 2 vizinhas, casos fora do céu) é preciso digitalizar lotes de relva/meio e confirmar buracos nessas zonas; o `T_abs` único corta certas na relva/vale (reserva: `T_abs` por zona, só com essa GT).
3. **Decisão de produto:** o ranking fica fora de «Vai buscar» (decisão desta ronda, por os números de peça ausente). Se o Tiago quiser os `alta` com ≥ 2 vizinhas no fluxo «Vai buscar» (precisão ≈ 49 % a π = 10 %), é uma decisão dele.
4. Pendentes anteriores (ronda 4): falsos alarmes do bloco c32|c33, P0343 (5,20) e P0833 (8,2) por confirmar; P0844/P0879/P0852 (tab recuperado); validação do editor de contorno (10–12 recortes).

## Pendentes técnicos (por ordem)
1. **M11:** `T_abs` por zona / nº de vizinhas (céu propõe de mais: falsas `alta` 0,18–0,27 com 3–4 vizinhas; relva corta um terço das certas; vale fica fora); a grelha de erosão é não monótona em S_T (0,60 ganhou por 3 pt com n = 144); afetação conjunta errou 1/15 no tabuleiro real (P0129 → (3,50)); primeira abertura de `/api/holes` demora ≈ 3 min (tiras); `hole_json` de uma célula enquanto a lista calcula é `parcial` (sem afetação).
2. **Pose manual** (ronda 4): gravar/repor 4–9 s; `rebuild_stale` apaga poses manuais das folhas re-segmentadas; Firefox/Safari/toque físico [NT].
3. **Falso alarme:** calibração com os falsos alarmes; assinatura `k` CLI vs servidor.
4. **PNG:** copiar só em localhost/https.
5. **Editor de contorno:** sem «remover contorno manual»; p95 0,54–0,68 mm.
6. **Detetor de peça comida**, **(26,1)/(25,1)**, lados F com reta RMS > 0,15 mm: como antes.

## Convenções que mordem
- `tools/diagnostico/fit/*.py` precisam de `PPF_SCRATCH` fora do repo e correm pela ordem `gt.py` → `fit_eval.py` → (`buraco.py`) → `m11_particao.py` → `m11.py sanidade|afinar|validar|real|figs`; só leem o projeto (exceto o bloco `calibration.buraco` escrito à mão nesta ronda).
- Nunca correr `tools/diagnostico/render/run_render.py` nem `verde_tabuleiro.py` sem `--project` apontado a uma cópia.
- Escrita no log só por `src.confirm` (inclui `--buraco`/`--buraco-rejeitar`)/`src.reports`/`src.consistency --falso-alarme`/`rebuild_scans`/o servidor; `ingest_all.py` refaz o log e perde as colocações do Tiago: não usar.
- Em `Bash`, heredocs com muitas aspas falham: escrever um ficheiro `.py` com a ferramenta Write e correr; consola cp1252: `PYTHONIOENCODING=utf-8`; a saída de um processo redirecionada só aparece no fim (usar `python -u`).
- Commits em português, sem co-author. Suite completa > 200 s: em segundo plano.

## Links
- M11: `docs/diagnostico/fit/M11_CRITERIOS.md` (critérios, partição), `M11_RESULTADOS.md` (números, figuras, reserva), `docs/gui-design.md` §21 (GUI), `ARCHITECTURE.md` (`fit.py`, contrato de `rank_hole`), `docs/decisoes.md` (a acrescentar se houver decisão do Tiago sobre o ponto 3).
- Rondas anteriores: `docs/diagnostico/reports/FALSOS_ALARMES.md`, `docs/diagnostico/render/POSE_MANUAL.md`, `COMIDO.md`, `TRACOS.md`, `RENDER.md` §4.1.
- Prompt desta ronda: `docs/prompts/2026-11-07e-m11-molde-do-buraco.md` (fechado). Anterior: `docs/prompts/2026-11-07d-reports-em-linha-falso-alarme-pose-manual.md`.
- Reports: `python -m src.reports --project projects/alpes --list`; suspeitas: `python -m src.consistency --project projects/alpes`; buracos: `python -m src.fit --project projects/alpes [--cell L C] | --relatorio`.
