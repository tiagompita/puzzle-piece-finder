# HANDOFF — 2026-11-08 (ronda 7: 6 propostas que não encaixam, velocidade da consulta, continuidade; fechada)

Lê isto primeiro numa sessão nova; no fim, atualiza-o e fecha o ficheiro do prompt em `docs/prompts/`.

## Estado
- **Commits desta ronda** (em `main`): `8af95b2` critérios antes de medir (`docs/diagnostico/gemeos/R7_CRITERIOS.md`); `32b918c` GT à data + H1–H5 + tempo; `2f68664` H6(b); `65389d5` plano; `bab495a` efeito da validação cruzada; `b0bf748` decisões/revisão; **`be82a34` código** (validação cruzada gémea/par × encaixe, zonas no perfil, pares, percentil opt-in, θ das âncoras, `fetch_listed` com `encaixe`); docs finais. Relatório: `docs/diagnostico/gemeos/R7_RESULTADOS.md`. Prompt fechado: `docs/prompts/2026-11-08-r7-falhas-fora-do-ceu.md`.
- **Os 6 casos (causa medida):** P1014 → (41,62) já era `ambigua` (forma e imagem a falhar) e era cartão; P1238 → (35,2) `aceite` com rótulo «(ceu)» de *fallback*; as duas têm encaixe contra a vizinha na pose prevista com custo 9,14 e 4,56 > T_abs 2,67 (máximo das 42 aceites 2,08). T0003/T0004: a célula proposta tinha a célula gémea já ocupada por peças GT (as gémeas certas foram colocadas lá a seguir) e `pair_locate` corria com 1 rotação arbitrária. Âncoras OK (H1 [F]); limiar de forma OK (H2 [F]: 0/59 100 falsos de forma); imagem com limiar 50 quase vazia (61–97 % das células aleatórias passam) embora discrimine (AUC 0,96–0,99).
- **O que mudou no produto:** proposta com vizinha montada é testada com `fit.side_costs` na pose prevista → `encaixe incompatível` → `ambigua` (nunca apagada; chip vermelho no cartão, coluna no `fetch.md`); zona verdadeira na razão e «zona sem p90 calibrado → a imagem não decide → nunca `aceite`» (montanha/vale/relva); pares só em células com X e twin(X) livres, com forma e 4 rotações (a peça B do par passa a mostrar twin(X)); percentil fora do caminho de produto (passo «gémeas» 341,5 → 6,5 s com pool ≤ 300; propostas idênticas); âncoras de secção com θ (`initial_theta`). Efeito medido: 0/44 colocações aceites perdem `aceite`, 2/2 rejeitadas `incompatível`; na lista real só P1109 (33,4) muda (`aceite` → `ambigua` pela zona).
- **Testes:** suite completa com o código novo: **410 passed, 1 failed, 1 skipped (323 s, OpenCV 4.11)**. Novos: 23 testes em 4 ficheiros. **Testes existentes alterados (declarado): 3 linhas** (`tests/test_twin.py` passa `pctl=True`; o stub `pair_locate` de `tests/test_state.py` ganha `allowed=None`); nenhuma asserção mudou. A falha é `tests/test_gui_guardadas.py::test_real_board_cells_without_orthogonal_neighbour_are_not_in_vai_buscar`, que já falhava antes desta ronda: usa `projects/alpes` cortado no evento 2045 e espera propostas em (4,43), (4,53), (3,54), (3,55), (3,59) — as peças dessas células (P0105, P0176, P0165, P0935, P0909) estão entre as 17 com **contorno manual de hoje** (`overrides.jsonl`, aplicado pelo rebuild), e com a silhueta manual a gémea deixa de ser encontrada (R7_RESULTADOS §1.3). É dado, não código; não tocado (decisão 4 abaixo).
- **Interpretador:** `C:/Users/Tiago/AppData/Local/Temp/claude/c--Users-Tiago-Desktop-puzzle-piece-finder/f748cb5c-95ce-4ca7-bb40-feccfde7cc64/scratchpad/venv4/Scripts/python.exe` (`PYTHONIOENCODING=utf-8`; matplotlib instalado nesta ronda).
- **Projeto `projects/alpes`:** só `puzzle.json` tocado (`image_zones` com as 4 zonas; `git status` limpo antes). **Esta máquina não tem os `pieces/`/`crops/` dos lotes 4–8** (ignorados pelo git): foram refeitos numa cópia com `render.rebuild_stale` (383 peças, 16 folhas; 17 silhuetas com contorno manual aplicadas). No portátil da GUI, depois do `git pull`, o arranque do servidor refaz os ativos como sempre.
- **Reports:** 6 abertos (R0029–R0034, os 6 casos; **não fechados**: decisão do Tiago depois de ver as razões novas). Suspeitas inalteradas.

## O que o Tiago tem de ver na GUI
1. **«Vai buscar»**: cada cartão de gémea/borda/par traz agora um chip de encaixe («encaixe ok (N viz.)» discreto; «encaixe incompatível» vermelho, com a razão no título) ou nada quando a célula não tem vizinha montada. As razões dizem a zona verdadeira («zona vale/aldeia sem p90 calibrado: a imagem não decide») em vez de «(ceu)». P1109 (33,4) aparece `ambigua` por isso.
2. **Pares**: a peça A mostra a célula X e a peça B a célula gémea twin(X); as células já ocupadas (ou com a gémea ocupada) aparecem nas razões como excluídas.
3. **Pesquisa `P1014`, `P1238`** (gaveta da peça): as rejeições de hoje continuam registadas; os reports R0029–R0034 continuam abertos.
4. O servidor regista «encaixe X s» na linha da consulta (painel «Atividade»).

## Espera pelo Tiago (decisões que são dele)
1. **`ambigua` em «Vai buscar»:** hoje é cartão (10 das 43 colocações certas estavam `ambigua`; 1 errada, P1014). Manter, ou só `aceite` + `ambigua` com encaixe `ok`, ou lista «fracas» à parte?
2. **p90 da imagem por zona:** medidos céu 10,6 e relva 16,1 (cobertura 85,5 % / 95,1 % em validação; 4,7 % / 3,5 % de negativos passam); ativá-los despromoveria ≈ 15 % de gémeas certas no céu para `ambigua`. Não ativados (critério ≤ 2/43 falhou). Ativar ou não?
3. **Pares T0003/T0004:** os reports dizem que a **célula** estava errada; a relação de gémeas entre P0987↔P1110 e P1060↔P1163 não foi testada (forma mútua `aceite`, margens 2,49/2,01). Vale a pena confirmar fisicamente (uma rodada 180° sobre a outra)? Se forem gémeas, convém um estado «par certo, célula errada» em vez de `rejeitado` para sempre (mudança de estado por fazer).
4. **Os 17 contornos manuais de hoje** (editor por traços) ficaram ≈ 1,3 mm fora da aresta (52–68 mm² a mais): as gémeas dessas 17 âncoras deixam de ser encontradas pela forma (9/9 medido). Refazer, retirar os overrides, ou o editor avisar quando a área sobe > 10 %?
5. **Pares já registados (T0001, T0002, T0005):** as células guardadas vêm do `pair_locate` antigo (1 rotação); T0002 e T0005 reclamam as mesmas células. Relocalizar (evento novo no log) ou deixar até serem confirmados/rejeitados?
6. **Ficheiro `projects/alpes/logs/servidor-20261108.log`:** enviar as linhas `consulta` para a explicação dos 202–320 s ficar [V] no portátil (hoje [V na cópia]).
7. Pendentes anteriores: P0343 (5,20) e P0833 (8,2) por confirmar; P0844/P0879/P0852; c32|c33; `erro_terminal.txt` no git.

## Pendentes técnicos (por ordem)
1. **GT fora do céu** (passo seguinte proposto em `docs/estado-e-plano.md` §7): digitalizar sacos de montanha/vale/relva e colocar pelas gémeas montadas; alvo ≥ 20 gémeas e ≥ 20 buracos confirmados fora do céu antes de ativar limiares por zona. `--relatorio`: 38/38 (37 céu + 1 montanha); §15.6 por atingir (faltam 22, 15 com ≥ 2 vizinhas).
2. **Passo «pares»** é agora o maior da consulta completa (19,5 s com 451 soltas: `find_twin` de cada solta contra todas, O(N²)); não otimizado.
3. **Arranque do servidor:** `GET /api/suspeitas` durante «a compor o tabuleiro» leva 10,6 s (2,3 s depois): disputa do GIL com a composição; POST de confirmação 8–13 s enquanto a thread das tiras calcula a frio (reconsulta incremental 4–8 s). Medido, não corrigido.
4. `fetch_listed` passa a registar `encaixe`/`decision_antes_encaixe`: a GT do efeito da regra acumula-se a partir de agora.
5. Chip de encaixe no browser [NT] (só testes de servidor/unidade); pares: sem deduplicação entre pares que reclamam as mesmas células.
6. Anteriores: pose manual 4–9 s, falso alarme, PNG, editor (p95 0,54–0,68), detetor de peça comida, (26,1)/(25,1).

## Convenções que mordem
- `tools/diagnostico/gemeos/r7_*.py` precisam de `PPF_SCRATCH` e de uma **cópia** do projeto com os ativos refeitos (`render.rebuild_stale` numa cópia; nunca em `projects/alpes`).
- Nunca correr o servidor nem ferramentas de render sobre `projects/alpes` para medir: cópia (o servidor escreve `render/gui`, `placements.json`, `logs/`).
- Escrita no log só por `src.confirm`/`src.reports`/`src.consistency --falso-alarme`/`rebuild_scans`/o servidor; `ingest_all.py` refaz o log e perde as colocações: não usar.
- Em `Bash`, heredocs com muitas aspas falham: ficheiro `.py` com Write; consola cp1252: `PYTHONIOENCODING=utf-8`; saída redirecionada só aparece no fim (`python -u`). Nunca `taskkill //IM python.exe` (mata a suite em curso): só pelo PID do servidor (porta 8765).
- Commits em português, sem co-author. Suite completa > 300 s: em segundo plano.

## Links
- Ronda 7: `docs/diagnostico/gemeos/R7_CRITERIOS.md`, `R7_RESULTADOS.md` (+ `r7_gt.json`, `r7_hipoteses.json`, `r7_efeito.json`, `r7_h2_forma.png`, `r7_h3_imagem.png`), `docs/decisoes.md` (2026-11-08, ronda 7), `docs/revisao.md`, `docs/estado-e-plano.md` §7 (M10/M11 + passo seguinte), `docs/README_proposta.md` (rascunho para aprovar), prompt `docs/prompts/2026-11-08-r7-falhas-fora-do-ceu.md`.
- Comandos: `python -m src.reports --project projects/alpes --list`; `python -m src.consistency --project projects/alpes`; `python -m src.fit --project projects/alpes --relatorio`; `python -m src.overrides --project projects/alpes --pares`; `python -m src.server --project projects/alpes`.
