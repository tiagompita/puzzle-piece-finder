# GUI "mesa de montagem" — o que está construído

Atualizado em 2026-11-02 (ronda «GUI não aprovada»; substitui a proposta da ronda anterior e a maquete estática, que não foi aprovada). Etiquetas: **[V]** verificado (teste ou captura vista), **[NT]** não testado, **[F]** testado e a falhar. Como correr e o que mostram as capturas: [`docs/gui/README.md`](gui/README.md).

## 1. Objetivo

Uma pessoa (Tiago) junto ao tapete, com sacos numerados. A GUI é a **vista do estado do projeto** e a **lista do que fazer a seguir**: o tabuleiro tem de parecer o puzzle físico; cada sugestão diz de que saco e com que número vem a peça, como fica rodada e onde vai; um toque confirma e a lista regenera-se.

## 2. Stack (decidido e construído)

Web local: `python -m src.server` (FastAPI + uvicorn) + `src/web/` (`index.html`, `app.js`, `app.css`; JS sem framework nem build). Por omissão escuta em `127.0.0.1:8765`; `--lan` abre a `0.0.0.0` com aviso escrito na consola (**sem login**). O Tkinter (`src/gui.py`) fica como está até ser removido; não conhece lotes, mapa nem gémeas.

```
 browser (PC / telemóvel)  --HTTP + SSE-->  src/server.py (Gui + rotas)  -->  src/confirm.py / Project (src/state.py)
   src/web (estático)                         caches: raster do tabuleiro,       log.jsonl (fonte de verdade)
                                              fantasmas, folhas, recortes        render.compose_board / query / ingest
```

- **Escritas**: só por `src.confirm.confirm` (colocar, rejeitar, posição conhecida, ancorar, desancorar, descartar, `cell_full`/`cell_empty`; a mesma reconsulta incremental da CLI), `Project.unplace` (+ reconsulta da célula e da gémea) e `ingest.ingest_scan` + `query.run_query` completo. Um lock (`Gui.wlock`) serializa-as; uma escrita durante um trabalho em curso (importação, preparação) responde 409. Depois de cada escrita: invariantes verificadas por `confirm` (`check_invariants(disk=True)`), recorte limpo e registo fino (com a imagem) das peças acabadas de colocar escritos em `render/clean/` e `render/placements.json`, eventos SSE `board_changed` e `fetch_changed` [V: `tests/test_server.py`].
- **Leituras**: sem lock; uma leitura que apanhe um dicionário a mudar é repetida. Se o `log.jsonl` mudar por fora (CLI), o projeto é reaberto no pedido seguinte.
- **Regra do arranque**: se `pieces/`, `crops/`, `overlays/` ou `render/` faltarem ou estiverem vazias (não estão no git), `render.rebuild_assets` corre numa thread com progresso na consola e na página "A preparar o projeto" (SSE `prepare_progress`, `ready`); a API de dados responde 503 até acabar [V: teste com `rebuild_assets` substituído; NT: num clone real — a regeneração completa do `projects/alpes` não foi cronometrada nesta ronda]. As folhas com a peça destacada (`render/sheets`, também fora do git) são geradas a pedido.

## 3. Endpoints (implementados)

| Endpoint | Devolve / faz |
|---|---|
| `GET /api/status` | `{estado: pronto\|a_preparar, job, prep_log, job_log, versao}` |
| `GET /api/board` | grelha `cells[l][c] = {estado, peca_id, fonte}`, posições conhecidas, borda em falta, progresso, `stats`, `legend` (a tabela da §5), calibração (t95, margem mínima), `hr = h/w` |
| `GET /api/board.jpg?ppc=60[&region=l0,c0,l1,c1]` | raster `compose_board` (camadas `art` + `pieces`). Tabuleiro inteiro a 60 px/célula em cache (memória + `render/gui/board_60.jpg`), invalidada pelo tamanho do log; abaixo de 60 é reduzido dessa imagem; com `region=` é composto a pedido até 240 px/célula (LRU). Inteiro acima de 80 → 400 |
| `GET /api/cell/{l}/{c}` | estado, peça (e como chegou), gémea (célula + peça), fantasma, propostas para a célula, posições conhecidas, vizinhas N/E/S/O, URLs do zoom |
| `GET /api/cell/{l}/{c}/zoom.jpg?side=render\|art\|both&dpi=300` | 3 × 3 células a 300 dpi: o render, a arte, ou `compose_zone_vs_art` |
| `GET /api/pieces/{id}` | resumo da peça, pose no tabuleiro e a sua origem, propostas, URLs |
| `GET /api/pieces/{id}.png?pose=board\|scan&size=220` | recorte limpo (RGBA) centrado no corpo, 1,8 células de lado; `pose=board`: colocada → θ do registo; proposta → `theta_deg` do `fetch.json`; posição conhecida → θ do log; senão como digitalizada. Cabeçalho `X-Pose` diz qual foi usada |
| `GET /api/fetch` | entradas do `fetch.json` + `razoes_txt` (frases simples), `origem_txt`, `estado_atual`; `suprimidas`, `notes` |
| `GET /api/sheets/{scan}.jpg?highlight=P####&max=1400` | `ingest.sheet_overlay` (folha numerada, peça a âmbar), cache em `render/gui/sheets/` até a numeração do scan mudar |
| `GET /api/ghosts` | fantasma de cada gémea pendente: `{cell (alvo), piece (colocada), from, path}`; `path` = `query.ghost_contour` em unidades de célula em torno do centro da célula alvo, com `profile.twin_rotation_deg()` |
| `GET /api/lots` | saco → folhas (scans) → peças com `n_no_lote`, estado, célula; `lote = null` = legado/GT |
| `GET /api/sections`, `GET /api/sections/{G}.png` | grupos por ancorar com o top-3 (`cell0`, rot, espelho, margem, pegada em células, "fora da grelha", células já colocadas) e miniatura (recortes nas posições do scan) |
| `POST /api/confirm` | `{acao: place\|reject\|position_known\|anchor\|unanchor\|discard\|unplace\|cell_full\|cell_empty, piece, cell, section, rot, mirror, reason, origin}` → `{ok, mensagens, invariantes, n_propostas, segundos, celulas_mudadas}` ou 400 `{error}` / 409 |
| `POST /api/ingest` | multipart `file` + `lote` + `dpi` → grava em `images/pieces/lotes/loteNN_<data>_<nome>`, trabalho em fundo (segmentar → `run_query` completo), progresso por SSE `ingest_progress` |
| `POST /api/report` | `{tipo: mal_lida\|mal_colocada\|nao_encaixa\|outro, texto, piece, cell, vista}` → o servidor grava a captura (zoom 3×3 da célula, ou o recorte da peça) em `projects/<id>/reports/R####.jpg\|png` e acrescenta o relatório a `reports.jsonl` (§11); SSE `report_added` |
| `GET /api/reports[?todos=1&eliminados=1]` | relatórios abertos (ou todos); os eliminados só com `eliminados` |
| `POST /api/report/{id}/estado` | `{acao: close\|reopen\|delete\|restore, nota?}` → o report dobrado; 404 se desconhecido, 400 numa transição inválida (§17); SSE `report_changed` |
| `GET /api/reports/{id}/captura` | a captura do report (`reports/R####.jpg\|png`); 404 se não existe |
| `GET /api/pieces/{id}/contorno` | editor de contorno (§18): recorte do scan (bbox + 3 mm), `denso` (contorno atual em px do recorte), `contour` (pegas ≈ 1 mm) + `indices`, `origem`, `tamanho`, `mmpp`, `manual_override`, `nota`, `limites`, `tracos` (do último override por traços, traduzidos para o recorte atual), `banda_mm`, `solver_omissao`, `solvers` |
| `GET /api/pieces/{id}/contorno.png` | o recorte do scan (RGB, sem alfa) por baixo do editor |
| `POST /api/pieces/{id}/contorno/resolver` | `{tracos, origem, tamanho, solver?, iter?}` → `{contour (px do recorte), area_mm2, valido, erro, solver, params, mascara_rle, n_pontos, ms_solver, ms}`; não escreve nada nem usa o lock de escrita; 200 com `valido: false` e a razão quando o gravar recusaria; 400 / 404 / 503 (contrato em `docs/diagnostico/editor/TRACOS.md` §7.3) |
| `POST /api/pieces/{id}/contorno/preview` | `{contour, origem, tamanho}` → PNG RGBA do recorte com alfa = polígono; nada gravado; 400 com a razão se inválido |
| `POST /api/pieces/{id}/contorno` | `{contour, origem, tamanho, nota?, tracos?, solver?}` → valida, `overrides.jsonl` +1, `render.rebuild_piece`, reconsulta; `{ok, piece, antes, mensagens, invariantes, celulas_mudadas}`; 400 / 409 |
| `GET /api/pieces/{id}/pose` | editor de posicionamento (§20), só peças `colocada` (400 se não): `cell`, `w_mm`, `h_mm`, `hr`, `pivot_mm`, `efetiva` / `automatica` / `manual` (θ, dx, dy), `limites` (±0,5 célula), `contorno` (≤ 300 pontos, unidades de largura de célula em torno do pivô, sem rotação) e `vizinhas` N/E/S/W (contorno + `svg.transform`); contrato em `docs/diagnostico/render/POSE_MANUAL.md` |
| `POST /api/pieces/{id}/pose/avaliar` | `{theta_deg, dx_mm, dy_mm}` → `{juntas:{N\|E\|S\|W:{piece, gap_mm, gap_sil_mm}\|null}, pior_mm, pior_dir, consistencia:{grau, falhas, texto}, ms}`; não escreve nem usa o lock de escrita (13–26 ms); 400 fora dos limites |
| `POST /api/pieces/{id}/pose` | `{theta_deg, dx_mm, dy_mm, nota?}` → evento `pose_set`, reconsulta; `{ok, antes, depois, juntas, invariantes, segundos, celulas_mudadas}` (≈ 4–9 s); SSE `board_changed` / `fetch_changed` / `suspeitas_changed` / `piece_changed` |
| `POST /api/pieces/{id}/pose/repor` | sem corpo → evento `pose_cleared`; `{ok, antes, automatica, …}` (≈ 4 s); 400 se a peça não tem pose manual |
| `GET /api/suspeitas` | `{summary, items, falsos_alarmes, n_em_reports}` (§12): cada item traz `report_aberto` (`"R####"` ou `null`) e a assinatura; `summary` com `n_recorte`, `n_falsos_alarmes`, `n_falsos_alarmes_obsoletos` |
| `POST /api/suspeitas/{piece}/falso-alarme` | `{grau, nota?}` → `{ok, piece, grau, summary}`; 400 `{error}` se a suspeita não está sinalizada, 409 ocupado; SSE `suspeitas_changed` |
| `POST /api/suspeitas/{piece}/restaurar` | `{grau}` → `{ok}`; SSE `suspeitas_changed` |
| `GET /api/events` | SSE: `hello`, `board_changed`, `fetch_changed`, `piece_changed`, `ingest_progress`, `prepare_progress`, `report_added`, `report_edited`, `report_changed`, `suspeitas_changed`, `ready` |

`unplace` não estava na lista pedida; foi acrescentado porque um toque errado em "Coloquei" precisa de desfazer (só para peças colocadas pelo log; as de secções desfazem-se com "Desancorar grupo").

## 4. Ecrãs

Uma página: tabuleiro à esquerda, painel compacto de 360 px à direita; as 6 abas (**Vai buscar · Guardadas · Lotes · Mesa · Importar · Reports**, §12–§13) e a caixa de pesquisa (§13) estão na barra de topo; o painel **Célula** que abre ao tocar numa célula (botão "← voltar"). A legenda é um rodapé recolhível (`<details>`), aberta por omissão só com viewport de altura ≥ 900 px; o estado fica lembrado no browser. **Nota de viewport:** a escala do Windows a 125/150 % encolhe o viewport CSS (1366×768 → 1093×614 → 911×512), por isso o CSS tem regras para alturas ≤ 740 e ≤ 650 px; abaixo de 900 px de largura o painel passa a folha inferior. Cabeçalho com o contador «N por confirmar (foto) · M marcadas por ti» [V: capturas Playwright 1366×768 e 1920×1080 a 100/125/150 % + telemóvel, `tests/test_gui_layout.py` (slow)].

- **Tabuleiro**: `<img>` raster + overlay SVG no mesmo `viewBox` (unidades de célula: x = coluna, y = linha × h/w); zoom/pan por roda simples e pinça **só dentro do tabuleiro** (Ctrl/Meta+roda fica para o browser, que faz zoom à página), arrasto; duplo clique aproxima; botões + / − / ajustar. Com zoom acima de ~66 px/célula reais, a região visível é pedida de novo ao servidor a mais resolução (até 240 px/célula ≈ 300 dpi) e sobreposta: com zoom, vê-se o recorte real a alta resolução [V: `progresso_zoom_relva.jpg`]. A grelha só aparece a partir de ~22 px/célula; os fantasmas a partir de ~7 px/célula (e com o interruptor ligado).
- **Vai buscar**: cartões agrupados por saco, pela ordem do `fetch.json`. Cada cartão: "Saco N · nº X" grande; célula alvo e decisão em palavra (aceite / ambígua); a peça **rodada como fica** (`theta_deg`), com ▲ = topo do tabuleiro, quadrado tracejado = célula e o fantasma da gémea por cima; minimapa com a célula; a folha do saco com a peça a âmbar (toque amplia); razões em frases (forma: diferença X mm (limite t95); margem para a 2.ª candidata (mínimo); imagem: ΔE); botões **Coloquei / Não encaixa / Guardar posição / Ver no tabuleiro / Reportar**; "razões técnicas" recolhidas. A lista tem duas partes: **«Coloca agora (n)»** (≥ 1 vizinha 4-conexa montada, isto é, `colocada` ou marcada pelo Tiago; «só foto» não conta), onde o encaixe é verificável à mão, e a seguir **«Guarda com posição (n)»**, cujo botão é **«Guardei num saquinho (l, c)»** (→ `posicao_conhecida`, sem «Coloquei»); quando uma posição guardada passa a colocável aparece um aviso (toast) e um emblema. «Ver no tabuleiro» só faz zoom e realça a célula: não muda de separador, a lista fica ao lado. A peça nos cartões, nas folhas e nas miniaturas da Mesa vem de um só pipeline de exibição (§6.8). Estado vazio: "Nada a ir buscar agora" + botão Importar. Sugestões suprimidas (candidata única) numa nota recolhida.
- **Célula**: o tabuleiro a 300 dpi (3 × 3) ao lado da arte, com o fantasma e as marcas da célula; estado, gémea (clicável), peça e como chegou; propostas com os mesmos cartões; vizinhas; "Desfazer colocação" ou "Desancorar grupo"; botões **«Está montada» / «Está vazia»** (pista do Tiago: `cell_full`/`cell_empty`, com desfazer) e **Reportar**. Textos de estado: «cheia na foto, por confirmar» (só foto) e «marcada por ti» (pista).
- **Lotes**: um bloco por saco com as folhas (miniaturas, toque amplia) e a grelha de peças (miniatura como digitalizada, nº, célula ou estado; chave de cores dos estados no topo). Tocar numa peça colocada/posição conhecida abre a célula; numa solta abre o painel da peça (propostas, folha, "Descartar", "Reportar").
- **Mesa** (lista compacta desde 2026-11-06, §15): uma linha por grupo com selo segura / a confirmar, pesquisa, filtros «Seguras» / «A confirmar», «Ver» (abre a linha e desenha a pegada a violeta) e só depois «É aqui em (l, c)» (com confirmação) que usa `confirm(anchor=…)`; botão «Sugestões» na barra do tabuleiro. Candidatos com peças fora da grelha ficam desativados; células já colocadas são avisadas.
- **Importar** (pensado para o PC): ficheiro, nº do saco (proposta: o seguinte ao maior), dpi; progresso em linhas; no fim, ligações para "Vai buscar" e para o saco.
- **Telemóvel** (`max-width: 900px`): tabuleiro em cima (40 % da altura), legenda compacta (só rótulos, em várias linhas, sempre visível), painel como folha inferior com pega; tocar na pega expande a folha e reduz o tabuleiro. Alvos de toque ≥ 44 px (botões de zoom 40 px no telemóvel).

## 5. Legenda (tabela única)

A tabela `LEGEND` de `src/server.py` é a única fonte: o servidor devolve-a em `/api/board`, a página desenha a legenda a partir dela com amostras que usam **as mesmas classes CSS** do tabuleiro (as linhas "raster" mostram um pedaço real do raster), e `tests/test_server.py` falha se alguma classe `b-*` usada em `src/web` não tiver linha ou se alguma linha não tiver estilo.

| Símbolo | Classe | Significa |
|---|---|---|
| peça com imagem | (raster) | Peça colocada: recorte real do scan, limpo da franja e registado na célula |
| arte esbatida | (raster) | Célula vazia: só a arte da caixa a 34 % |
| tracejado cinza-azulado | `b-legado` | Cheia na foto, por confirmar (dúvida: não bloqueia gémeas, buracos nem borda). Uma célula marcada pelo Tiago tem o mesmo tracejado e o painel diz «marcada por ti» |
| quadrado vermelho | `b-borda-falta` | Borda em falta: célula de borda vazia |
| quadrado âmbar cheio | `b-buscar` | Vai buscar: peça proposta, aceite |
| âmbar tracejado | `b-buscar-ambigua` | Vai buscar com dúvida: confirmar pela imagem |
| âmbar pontilhado | `b-buscar-par` | Par de soltas: célula só provável |
| quadrado ciano | `b-conhecida` | Posição conhecida: peça guardada à espera de vizinha |
| contorno branco tracejado com a forma da peça | `b-fantasma` | Fantasma: contorno da gémea colocada rodado por `profile.twin_rotation_deg()` (180° neste puzzle) |
| violeta cheio | `b-sug` | Sugestão segura: melhor zona de um grupo (botão Sugestões) |
| violeta ténue tracejado | `b-sug-fraca` | Sugestão a confirmar: o programa não decidiu |
| violeta tracejado | `b-mesa` | Onde um grupo solto ficaria (pré-visualização da Mesa) |
| linhas finas | `b-grelha` | Grelha (com zoom) |
| quadrado branco grosso | `b-selecionada` | Célula aberta no painel |

Dentro dos cartões há três marcas próprias (▲ topo, quadrado tracejado = célula, contorno claro = fantasma), explicadas numa frase no topo da lista e do painel da célula.

## 6. Decisões desta ronda

1. **Raster do servidor, não SVG com 3000 imagens.** O aspeto "puzzle físico" vem de `render.compose_board` (recortes limpos, registo fino, prioridade por profundidade, sangria), que o browser não consegue reproduzir. O SVG fica só para o que é símbolo (e por isso tem legenda). Tabuleiro inteiro a 60 px/célula: 3840 × 2729, ≈ 1,5 MB JPEG.
2. **Atualização incremental do raster.** Depois de uma escrita, as células cujo `(estado, peça)` mudou são recompostas com ±1 célula de margem e coladas na imagem em cache (mais de 40 → recomposição completa). O desalinhamento vertical máximo da colagem é meio píxel (a altura da célula a 60 px/célula não é inteira) [V: sem costura visível nas capturas; não medido].
3. **Fantasma.** Contorno da peça colocada com a pose do registo fino (`render/placements.json`), rodado por `profile.twin_rotation_deg()` em torno do centro da célula gémea (`query.ghost_contour`); nada da simetria está no JS. Mostrado no tabuleiro (interruptor "Fantasmas", lembrado no browser), no cartão (sobre a peça rodada) e no zoom da célula. É uma ajuda para procurar à mão; a prova continua a ser o `find_twin`.
4. **Pose das imagens.** Colocadas: θ do registo; propostas: `theta_deg` do `fetch.json` (cadeia do `twin.py`); sem pose: como digitalizada e o cartão diz "rotação desconhecida".
5. **Scans importados vão para `images/pieces/lotes/`** (dentro do repositório) para que o outro PC regenere os recortes a partir do git.
6. **Interface em português, só modo escuro**, âmbar reservado a "vai buscar".
7. **Pose de uma colocação confirmada** vem da proposta (`theta_deg`) e fica gravada no log (antes as duas colocações feitas pela GUI eram as únicas com `theta` nulo e o render usava a orientação do scan); o servidor re-regista e re-cola a célula quando só a pose muda; o cartão devolve `X-Pose-Theta` [V: testes de `test_state`/`test_server`/`test_render`].
8. **Um só pipeline de exibição das peças** (`render.piece_rgba_for_display`: recorte limpo, cor sob alfa 0 substituída pela da peça mais próxima, rotação/redimensionamento pré-multiplicados) para cartões, folhas `fetch_<lote>.jpg` e miniaturas da Mesa. Regra de orla de sombra só de exibição (`DISPLAY_SHADOW`, 0,4 mm), nunca no índice nem no tabuleiro (`RENDER.md` §6/§6.1).
9. **Arte registada contra as peças colocadas** (`art.registration` em `puzzle.json`; uma só transformação aplicada em `locate.load_art_rectified`). A fila 47 não tem arte no ficheiro: cinzento, «sem arte» (`ARTREG.md`).
10. **Ocupação só da foto é dúvida, não cheia**: não bloqueia propostas; as pistas do Tiago (`cell_full`/`cell_empty`) são a verdade e contam como ocupada sem silhueta.
11. **Ctrl/Meta+roda pertence ao browser**; a roda simples e a pinça só atuam dentro do tabuleiro.
12. **«Vai buscar» em duas listas** («Coloca agora» / «Guarda com posição»), §4 e §11.
13. **Relatórios** em `projects/<id>/reports.jsonl` como lista de trabalho para o Claude Code (§11).
14. **Escala/zoom.** Se a página abrir ampliada (p. ex. 133 %) é o zoom do browser guardado para `localhost:porta`: **Ctrl+0** repõe os 100 %.

## 7. Desempenho medido (cópia de `projects/alpes`, 575 colocadas, este PC)

[NT nesta ronda: não re-medido]

| Operação | Tempo |
|---|---|
| `/api/board.jpg?ppc=60` a frio (composição completa) | 8,4 s (uma vez; depois da cache em disco, arranque sem recompor) |
| `/api/board.jpg?ppc=60` em cache | 5 ms |
| região 8 × 10 células a 200 px/célula | 1,3 s |
| `/api/ghosts` a frio / em cache | 0,66 s / 12 ms |
| `POST /api/confirm` place P0100 → (3, 37), ida e volta (inclui reconsulta incremental com imagem e registo fino) | 2,7 s |
| raster depois da escrita (1 célula recomposta) | 0,25 s |
| `POST /api/confirm` unplace | 2,0 s |

## 8. Ainda não feito

- **M11**: molde do buraco e a **confirmação dupla** fantasma × molde (`/api/holes` não existe; o painel da célula não mostra o molde).
- Fronteira / encaixe solta-solta (M6) e localização na caixa: não aparecem na lista porque ainda não existem no `query`.
- Seleção manual de uma peça qualquer para uma célula ("escolher outra peça"), mudar uma folha de saco pela página (`confirm --relot`) e registar foto do tabuleiro (`src.photo`) continuam só na CLI.
- (3,32)/(3,33) por decidir (P0291 vs P0294, margem 1,12) **[NT físico]**.
- Verificação física das novas âncoras: P0807 → (7,2), P0833 → (8,2), P0297 → (3,31), P0333 → (6,22) **[NT]**.
- A nota do saquinho não é gravada no log (`set_position_known` não tem o campo).
- A reconsulta incremental pode deixar peças em `suprimidas` (§9).
- Estilo distinto para células marcadas pelo utilizador (hoje o mesmo tracejado de «cheia na foto»).
- Teste num telemóvel real pela LAN (Safari / Chrome) [NT]; regeneração completa num clone limpo [NT]; importação de um scan real pela página [NT] (testada só com um scan sintético).

## 9. Achado desta ronda (fora da GUI)

Depois de "Desfazer" P0100 de (3, 37), a reconsulta incremental (`run_query(only_cells=…)`) deixou P0100 como **suprimida** ("candidata única") em vez de voltar a "aceite": no modo incremental, as peças já propostas noutras células saem do conjunto de candidatas, por isso sobra uma só e a regra de 2026-11-01 suprime-a. O mesmo pode acontecer depois de "Não encaixa". É comportamento de `src/query.py` (não alterado aqui); uma reconsulta completa (`python -m src.query`) repõe a lista.

## 10. Perguntas ao Tiago

1. (3,32)/(3,33): é P0291 ou P0294?
2. A confirmação física das 6 células de borda e do par (1,33) ↔ (47,32) continua pendente.
3. As 4 âncoras novas (P0807 → (7,2), P0833 → (8,2), P0297 → (3,31), P0333 → (6,22)) conferem à mão?
4. A legenda recolhida por omissão em ecrãs baixos está bem?
5. A regra da orla de sombra nas miniaturas (`DISPLAY_SHADOW`) agrada?

## 11. Reportar

Botão "Reportar" em cada cartão, no painel da peça e no da célula: abre um `<dialog>` com 4 tipos (mal lida / mal recortada, mal colocada, não encaixa, outro) e texto opcional. Endpoints: `POST /api/report`, `GET /api/reports` (§3).

- **Ficheiro** `projects/<id>/reports.jsonl`, uma linha por relatório: `{id: "R0001", t, tipo, texto, piece, cell, scan_id, n_no_lote, lote, crop_path, captura, vista, estado: "aberto"}`; ao fechar: `estado: "fechado"`, `fechado_em`, `nota`. Capturas em `projects/<id>/reports/R####.jpg|png` (zoom 3×3 da célula se há célula, senão o recorte da peça).
- **Log**: eventos informativos `report` e `report_closed` (sem efeito no estado; o replay ignora-os). A escrita atualiza `_known_stat` e não emite `board_changed`/`fetch_changed`.
- **CLI** (`src/reports.py`): `python -m src.reports --project projects/alpes --list` e `--close R0001 --nota "..."`; também `--reopen`, `--delete`, `--restore` e `--list [--all] [--eliminados]` (§17).
- **"Vai buscar" em dois grupos** (item 6): `fetch.json` ganha, só na resposta de `/api/fetch`, `vizinhas_montadas` (vizinhas 4-conexas `colocada` ou `ocupada_legado` com fonte `tiago`; `foto` não conta) e `grupo` (`coloca_agora` com ≥ 1, ou posição conhecida que passou a colocável; senão `guarda_posicao`, cujo botão é "Guardei num saquinho (l, c)" = `position_known` com `nota: "saquinho"`, ainda não guardada no log).

## 12. Abas «Guardadas» e «Reports» (2026-11-05)

«Vai buscar» só mostra peças com ≥ 1 vizinha ortogonal montada (`fetch_group`: diagonais e moldura não contam; borda colocada conta; sem exceção para `posicao_conhecida`). As restantes estão na aba **Guardadas**: aviso «Não procurar ainda» e a secção «Guardadas com posição, ainda sem vizinha» recolhida por omissão; saem também do realce do tabuleiro. A aba **Reports** lista os reports (`GET /api/reports?todos=true&eliminados=true`; estados e detalhe em §17): ID, estado (aberto / resolvido), tipo, peça e célula, texto; filtro aberto/resolvido e contagem de abertos no separador. Os estados mudam-se na linha expandida ou pelo CLI (`python -m src.reports --close`).

**Linhas expandíveis (2026-11-07, 3.ª ronda; ver §17):** cada linha da aba Reports é um `details.card.report-row[data-report]` cujo `summary` mostra a miniatura da peça, o ID, os chips da peça e da célula (e o chip «suspeita · …» quando o report veio de uma suspeita), «estado · tipo · editado N×» e o texto curto, com o chevron do padrão `details.tech` (˅ / ˄). Clicar no resumo (ou Enter / Espaço, que o browser transforma em clique) faz duas coisas: **localiza** no tabuleiro **sem sair da aba Reports** (`locateReportInPlace` → `showCellOnBoard`: peça colocada ou com posição conhecida → realce e zoom na célula; peça pendente → toast «P#### está em Guardadas / Vai buscar»; só célula → realce da célula; sem peça nem célula → toast «report geral, sem localização») e **expande / recolhe** a linha (`toggle` nativo). Só uma linha está aberta de cada vez (ao abrir uma fecha-se a outra) e `S.reportOpen` sobrevive a `renderReports`/`loadReports`. A seta «→» e a secção `#tab-report` deixaram de existir. O clique não escreve nada (`log.jsonl` fica igual; testado). A pesquisa por `R####` abre a aba Reports com essa linha expandida, no filtro do seu estado, com scroll até ela e localizada no tabuleiro (`openReportDetail`).

**Suspeitas (topo de Reports):** `details.suspeitas`, resumo «Suspeitas (N)» com N = as visíveis. Uma suspeita com **report aberto** (`report_aberto` do servidor) sai da lista: o resumo acrescenta «+ M em reports» e, com `K` falsos alarmes, «K falsos alarmes (J obsoletos)» (`p.susp-extra`, e o mesmo texto ao lado do resumo enquanto o bloco está recolhido, via `summary[data-extra]::after`); a linha desse report ganha o chip `.chip.suspeita` («suspeita · impossível / melhor rotação / recorte», `title` = o texto da suspeita). Cada linha de suspeita tem o botão **«Falso alarme»** (não localiza; reutiliza `dialog#estado-dlg` com o título «Falso alarme P#### (grau)» e nota opcional → `POST /api/suspeitas/{piece}/falso-alarme`); a suspeita sai da lista e aparece em `details.falsos` «Falsos alarmes (K)» (peça, grau, célula, data, nota, chip «obsoleto» a âmbar quando a peça mudou desde a marcação) com o botão «Restaurar» (`POST …/restaurar`). O `EventSource` ouve `suspeitas_changed` (debounce de 300 ms → `loadSuspeitas`), que o servidor emite também depois de criar, editar ou mudar o estado de um report; fechar o report pela linha expandida devolve a suspeita à lista. A GUI tolera um servidor sem estes campos (`items` sem `report_aberto`, sem `falsos_alarmes`).

## 13. Abas no topo e «Editar report» (2026-11-05)

As 6 abas estão na barra de topo (`header#top > nav#tabs`), ao lado do nome e do progresso; abaixo de 1181 px ocupam uma 2.ª linha e abaixo de 900 px usam rótulos curtos (sem scroll horizontal; testado de 360 a 1920 px). O botão de report de um cartão, da célula ou da peça passa a **«Editar report»** quando já existe um report **aberto** dessa peça (ou dessa célula, se o report não tem peça): abre o mesmo diálogo preenchido («Editar R####», «Guardar edição»). **Na gaveta da peça / célula (2026-11-07)** o botão dá lugar a um `details.card.report-inline[open]` por report aberto (`reportDetailBody(r, {compacto: true})`: ID, estado, tipo, data, texto, nota e as ações Editar / Marcar resolvido / Eliminar; sem miniaturas, captura nem histórico); sem report aberto continua «⚠ Reportar». Nos cartões de proposta (Vai buscar, Guardadas) fica só o botão «✎ Editar report», para o cartão não crescer. A gaveta de uma peça solta (`openPiece`, `S.pieceOpen`) refresca quando os reports mudam (`loadReports`). `reports.jsonl` é append-only: editar acrescenta uma linha `{"evento": "edicao", "id", "t", "tipo"?, "texto"?}` (`POST /api/report/{id}/edit`; evento de log `report_edited`); a lista de Reports marca «editado N×». Só se editam reports abertos.

**Pesquisa (2026-11-07):** `form#search > input#q` na barra de topo (só cliente; nenhum endpoint novo; Enter pesquisa). Formatos: peça `P0778` / `p778` / `778`; report `R0019` / `r19`; folha `S0020` / `s20`; célula `4,10` / `4 10` / `(4,10)` / `l4 c10` (validada contra a grelha). Resolução (`locateQuery` em `app.js`): peça colocada ou com posição conhecida → gaveta da célula com zoom (`openCell`); peça em «Guardadas» ou «Vai buscar» → a aba abre, o cartão fica com a classe `sel` e fica à vista; peça solta sem proposta → toast com o estado real («P0003 existe: solta (saco 3, nº 3), sem proposta») e o painel da peça; célula vazia → gaveta mais toast «célula (l,c) vazia»; report → como o clique na linha; folha → aba Lotes com o saco aberto e um cartão no topo com a folha e as suas peças. Nunca falha em silêncio: o que não existe dá toast «… não encontrado». É só leitura. Posição: ≥ 1181 px na linha única (flex 0 1 220px, min 96px; a barra de progresso esconde-se até 1300 px para lhe dar espaço); de 901 a 1180 px na 1.ª linha ao lado das ferramentas (as 6 abas não deixam espaço na 2.ª linha a 911 px); ≤ 900 px só uma lupa (`#search-btn`) que abre o campo por cima do tabuleiro; ≤ 480 px os três interruptores ficam mais compactos para a lupa caber na 1.ª linha a 360 px.


## 14. Mesa — propostas (2026-11-05; decidido: B, implementada em §15)

O Tiago acha a aba «Mesa» confusa: «muita informação», muitos botões ver/ancorar, demasiado texto. Esta secção audita a aba com os dados reais do alpes e propõe duas alternativas **mais simples**. As alternativas são **protótipos descartáveis** desenhados por JavaScript injetado na página (`tools/gui/mesa_mockups.py`, nada em `src/`), sobre `S.sections` reais; as capturas e as métricas (`docs/gui/screenshots/mesa_*.jpg`, `mesa_metricas.json`) saem do mesmo script. A pesquisa por id/peça/célula (commit `70eae0a`) está feita e vale para qualquer das alternativas.

### 14.1 Auditoria da aba atual (38 grupos por ancorar: 31 blocos, 7 montados)

Captura: [`mesa_atual_1366.jpg`](screenshots/mesa_atual_1366.jpg), [`mesa_atual_390.jpg`](screenshots/mesa_atual_390.jpg).

Por grupo, hoje: miniatura (130 px) · título «Grupo G0077» · «blocos · 2 peças · folha S0024» · «notas da ingestão» (recolhido) · **3 linhas** de zona, cada uma com «1) (15, 59) rot 0° · margem 3,32», os avisos «parte fica fora da grelha» / «n célula(s) já colocadas» e **2 botões** («Ver» e «Ancorar aqui»). Mais um parágrafo de 3 linhas no topo da aba.

| medida (real) | 1366×768 | 390×844 |
|---|---|---|
| na aba inteira (38 grupos) | **228 botões**, ≈ 9 060 caracteres | idem |
| no ecrã sem fazer scroll | **2 grupos** (o 2.º cortado), **10 botões**, ≈ 540 caracteres | **1 grupo**, 6 botões, ≈ 380 caracteres |

Achados (dos dados, [V]):
1. **A «margem» é do grupo, não da zona**: em **38 de 38** grupos as 3 zonas têm exatamente a mesma margem (3,32, 3,32, 3,32 na captura). A coluna «margem» repete o mesmo número três vezes e não ajuda a escolher entre zonas.
2. **Só 7 de 38 grupos passam `margin_min` (1,5)**; a mediana da margem é 1,07. Para os outros 31 o próprio programa diz «ambígua, não ancora»: a aba oferece **93 botões «Ancorar aqui» a laranja** (3 por grupo) para decisões que o programa não fez. O botão mais forte do ecrã é o que menos deve ser carregado sem olhar.
3. **11 grupos têm 2 zonas na mesma célula e só muda a rotação** (ex.: (28, 57) rot 270° e rot 180°): a 2.ª e a 3.ª linhas parecem repetidas.
4. As **notas da ingestão** (38/38 têm, ≈ 205 caracteres) são técnicas («comp 2: ambigua; margem 1.02; 1 peça sem gémea; …»); já estão recolhidas, mas o cabeçalho «notas da ingestão ˅» ocupa uma linha em todos os cartões.
5. O texto de ajuda (3 linhas) repete-se sempre no topo; a miniatura ocupa 130 px × 130 px para 1–2 peças.
6. Falta uma pista de **qual ação é a principal**: «Ver» e «Ancorar aqui» têm o mesmo peso nas 3 linhas, e «Ancorar» não exige ter visto a zona.

### 14.2 Alternativa A — «Fila de decisão» (um grupo de cada vez)

Captura: [`mesa_a_fila_1366.jpg`](screenshots/mesa_a_fila_1366.jpg), [`mesa_a_fila_390.jpg`](screenshots/mesa_a_fila_390.jpg).

Um único cartão: miniatura (84 px), «G0077 · 2 peças», «Melhor zona: (15, 59)» com um selo (segura / a confirmar, pela margem do grupo), a zona **já pré-visualizada** no tabuleiro (violeta), e **duas ações**: **«Ancorar aqui»** (principal) e «Seguinte →». «Outras zonas (2)» e as notas ficam recolhidas. Ordem: das mais seguras às menos; contador «1 de 38». A caixa de pesquisa salta para um grupo.

| | |
|---|---|
| **Sai do ecrã** | os 38 cartões em lista, as 3 zonas em linha, os 6 botões por grupo, a margem repetida, o parágrafo de ajuda, as notas |
| **Fica** | miniatura, id, nº de peças, melhor zona + selo, Ancorar, Seguinte; zonas alternativas e pesquisa a 1 toque |
| **Métricas** | 4 botões e ≈ 120 caracteres (em vez de 228 e 9 060 no total / 10 e 540 no ecrã); 1 grupo em ecrã em ambos os tamanhos |
| **Custo** | pequeno em código (≈ 60–80 linhas JS no lugar de `renderMesa`/`mesaCard`; sem backend; reutiliza `/api/sections`, `drawMesa`, `zoomCells`); testes: reescrever o de pesquisa e acrescentar «Seguinte» e a pré-visualização; layout testado já cobre a aba |
| **Riscos** | perde-se a **visão geral** (não se vê que há 7 seguras e 31 duvidosas; não se compara grupos); «Seguinte» de 38 em 38 é lento se o Tiago quer procurar um grupo específico (a pesquisa ajuda); o botão Ancorar fica sempre à mão, é preciso decidir o que fazer nos grupos «a confirmar» (confirmação extra? esconder?) |

### 14.3 Alternativa B — «Lista compacta» (uma linha por grupo, abre-se uma de cada vez)

Captura: [`mesa_b_lista_1366.jpg`](screenshots/mesa_b_lista_1366.jpg), [`mesa_b_lista_aberta_1366.jpg`](screenshots/mesa_b_lista_aberta_1366.jpg) e as de 390 px.

Uma linha por grupo: miniatura 44 px, «G0071 · 4 peças», «melhor zona (17, 35)» com selo e **um só botão, «Ver»** (laranja). «Ver» pré-visualiza a zona no tabuleiro e **abre** a linha, onde aparece a ação principal **«Ancorar em (17, 35)»** e, em letra pequena, «ou (15, 48) · Ver», «ou (15, 46) · Ver». A pesquisa fica por cima. Só uma linha aberta de cada vez.

| | |
|---|---|
| **Sai do ecrã** | os 3 cartões abertos por grupo, 5 dos 6 botões, a margem repetida, as notas, o parágrafo de ajuda; «Ancorar» deixa de estar visível sem ter visto a zona |
| **Fica** | todos os grupos numa lista visível, a ordem por margem, pesquisa, selo, as 3 zonas (1 principal + 2 «ou»), pré-visualização |
| **Métricas** | 38 botões (1 por grupo) + 3 na linha aberta; ≈ 2 000 caracteres no total; **11 grupos no ecrã** a 1366×768 e **6** a 390 px (hoje 2 e 1) |
| **Custo** | pequeno a médio (≈ 80–100 linhas JS; sem backend; estado «linha aberta»; teste da pesquisa continua válido, acrescentar abrir/fechar e Ancorar só depois de Ver); layout a 390 px a verificar |
| **Riscos** | a linha aberta empurra a lista (scroll); o selo mostra só 2 níveis; precisa de uma regra para o «Ancorar» dos grupos «a confirmar» (ver 14.4) |

Nota sobre os protótipos: nas capturas as zonas alternativas mostram o selo do **grupo** (a margem é do grupo, achado 1); um desenho final não deve repetir o selo por zona.

### 14.4 O que as duas alternativas partilham (decisões pequenas, a confirmar)

- **Selo único por grupo** (segura se margem ≥ `margin_min` = 1,5; «a confirmar» caso contrário: 7 seguras / 31 a confirmar) em vez da «margem» em cada zona.
- **Zonas duplicadas só pela rotação juntam-se numa linha** («(28, 57), rot 270° ou 180°»): 11 grupos.
- **«Ancorar» só depois de «Ver»** (a zona tem de ter sido pré-visualizada) e, nos «a confirmar», o texto da confirmação avisa que o programa não decidiu.
- **Notas da ingestão** passam para um «ⓘ» no cabeçalho (já estão recolhidas), o parágrafo de ajuda passa a uma linha.
- Qualquer das duas mantém a pesquisa (`70eae0a`) e não mexe no backend nem no log.

### 14.5 Recomendação

**Recomendo a B (lista compacta).** Razões: (1) a **visão geral** é o que falta ao Tiago quando procura um grupo (acabou de pedir pesquisa por id/célula, o que pressupõe uma lista em que se navega), e a B mostra 11 grupos no ecrã em vez de 2; (2) corta o ruído tanto como a A (de 228 botões para 38 + 3, de ≈ 9 000 para ≈ 2 000 caracteres), com **uma ação por linha** («Ver») e a ação principal só depois de ver a zona, o que evita ancorar às cegas; (3) o custo é do mesmo tamanho da A e não perde nenhum caso de uso; (4) a A é melhor num único fluxo «despachar por ordem» (os 7 seguros), mas obriga a 38 passos para ver o resto, e na prática 31 dos 38 grupos são «a confirmar» e pedem comparação, não despacho em fila. Se o Tiago quiser só despachar os 7 seguros, a B com um filtro «só seguras (7)» dá-lhe a fila sem perder a lista.

**Por decidir (Tiago):** A ou B (ou outra); o que fazer com os 31 grupos «a confirmar» (escondidos atrás de um filtro, ou visíveis com «Ancorar» a pedir confirmação); se as zonas que só diferem na rotação se juntam. **Não implementado** até haver decisão.


## 15. Mesa — alternativa B implementada, «É aqui» e «Sugestões» (2026-11-06)

Decisão do Tiago: **B (lista compacta)** do §14. Código: `src/web/app.js` (secção «mesa de apoio» e «sugestões no tabuleiro»), `app.css`, `index.html`; testes `tests/test_gui_mesa_b.py` e `tests/test_gui_mesa.py`; capturas com dados reais do alpes (cópia) em `docs/gui/screenshots/mesa_b_impl_*.jpg` ([lista](screenshots/mesa_b_impl_lista_1366.jpg), [linha aberta](screenshots/mesa_b_impl_aberta_1366.jpg)), `sugestoes_*.jpg` ([botão ligado](screenshots/sugestoes_1366.jpg), [lista de escolha](screenshots/sugestoes_escolha_390.jpg)) (`tools/gui/mesa_b_capturas.py`, métricas em `mesa_b_metricas.json`).

### 15.1 A lista (desktop e telemóvel)
- **Uma linha por grupo:** miniatura 44 px, «G0071 · 4 peças», «melhor zona (17, 35)» e **selo único** (*segura* se a margem do melhor candidato ≥ `margin_min` do perfil, vindo de `/api/board` → `calibracao.margin_min`, 1,5 por omissão; *a confirmar* caso contrário) e **um só botão, «Ver»**. Ordem: pela margem. Os 31 grupos «a confirmar» ficam **visíveis**.
- **«Ver» abre a linha** (uma de cada vez), pré-visualiza a zona a violeta e só então aparece a ação principal **«É aqui em (l, c)»**; por baixo, as outras zonas como «ou (c, l) rot 90° · Ver». **Zonas que só diferem na rotação não se juntam** (decisão do Tiago): cada uma é uma linha. As notas da ingestão ficam num «ⓘ» recolhido.
- **Confirmação:** o diálogo do «É aqui» diz o grupo, a célula, a rotação e quantas peças passam a colocadas; num grupo «a confirmar» começa por «O programa não decidiu este grupo (margem x, mínimo y).» e a linha aberta mostra o mesmo aviso. Zonas com peças fora da grelha deixam o botão desativado (como antes).
- **Pesquisa e filtros rápidos:** a caixa mantém-se (placeholder «Grupo, peça ou célula: G0021, P0294, 3,32») e há dois botões «Seguras (7)» / «A confirmar (31)» (`aria-pressed`; tocar outra vez limpa; combinam com a pesquisa). Sem teclado.
- **Medido [V] (alpes, 38 grupos):** a 1366×768 cabem **10 linhas** no ecrã (eram 2 cartões) com 40 botões no total (eram 228); a 390 px, 4 linhas (era 1 cartão); sem scroll horizontal; botões ≥ 40 px de altura.

### 15.2 «Ancorar» → «É aqui»
Todos os textos **visíveis** passaram a «É aqui» (botão, confirmação, mensagens do servidor, título da legenda, estado «sem lugar» em vez de «por ancorar», «Desfazer «É aqui» do grupo G…»): constante única `LBL_AQUI` em `app.js` (e `AQUI_TXT` em `src/confirm.py` para as mensagens do servidor). Ficam como estavam os identificadores (`acao: "anchor"`, `por_ancorar`, `seccoes_por_ancorar`, eventos do log) e os docs antigos (§14 conta a história com o nome antigo). Teste: nenhum «ancor» (maiúsculas ou não) no texto, `title`/`aria-label`/`placeholder`/`alt` de todas as abas, na legenda do servidor, nos textos de estado e no diálogo de confirmação; e nenhum nas fontes `app.js`/`index.html`/`app.css` fora do identificador `por_ancorar`.

### 15.3 Botão «Sugestões» (barra do tabuleiro, ao lado de «Fantasmas» e «Grelha»; desligado por omissão)
- Mostra no tabuleiro a **melhor zona de cada grupo** (não as 3): **forte** (violeta cheio) se o grupo é *seguro*, **fraca** (tracejado ténue) se é *a confirmar*; 2 linhas novas na legenda (`sugestao`, `sugestao_fraca`; o teste de cobertura da legenda continua a passar). Com os dados do alpes: 38 grupos, 7 fortes, 81 células.
- **Tocar** numa sugestão abre a aba Mesa **na linha desse grupo, aberta, com a pré-visualização** dessa zona; se um filtro/pesquisa esconder o grupo, limpa-os. **Se várias se sobrepõem** no ponto tocado aparece uma lista curta (seguras primeiro, depois por margem) com alvos de **44 px** (medido a 1366 e a 390), mais «Abrir a célula (l, c)»; fecha com Esc, com outro toque ou ao escolher. (Medido no alpes: a célula (18, 34) dá 2 grupos + «Abrir a célula», os 3 botões com 44 px.) Com o botão ligado, um toque numa célula **sem** sugestão abre a célula como sempre; numa célula com **uma** sugestão abre o grupo (a célula só se abre desligando o botão ou pela lista, quando há várias).
- **Estado:** `localStorage` (`tg-sug`), com `try/catch` em todas as leituras/escritas (`lsGet`/`lsSet`, que passaram a servir também Fantasmas, Grelha e Legenda); sem armazenamento a página abre e o botão funciona, só não persiste (teste com `localStorage` a lançar erro).
- **Telemóvel (390 px):** a barra do topo leva os 3 botões sem rebentar (testes de layout existentes verdes); a lista de escolha fica dentro do ecrã.

### 15.4 Pendente, não pedido agora
Rótulo do grupo sobre a sugestão (só com zoom suficiente), ordenar a lista de escolha por distância ao toque, e a seleção sem escrever (§16, **só proposta**).

## 16. Mesa — selecionar sem escrever: propostas (2026-11-06; **nada implementado**)

Pedido: escolher **um ou vários grupos / peças / células** sem teclado (ex.: tocar no tabuleiro para filtrar a Mesa; caixas nas linhas; chips). Duas alternativas, ambas **protótipos injetados** sobre os dados reais (`tools/gui/mesa_b_capturas.py`, nada em `src/`); métricas em `mesa_b_metricas.json`. Hoje o filtro existente é «texto + Seguras/A confirmar».

### 16.1 Alternativa S1 — «Tocar no tabuleiro» (células → chips → filtro)
Captura: [`mesa_sel_a_celulas_1366.jpg`](screenshots/mesa_sel_a_celulas_1366.jpg), [`mesa_sel_a_celulas_390.jpg`](screenshots/mesa_sel_a_celulas_390.jpg).

Um modo «Selecionar» (botão na barra do tabuleiro, como «Sugestões»): cada toque numa célula a acrescenta/retira como **chip** «(15, 59) ✕» no topo da Mesa e a desenha a branco no tabuleiro. A Mesa mostra só os grupos cujas **zonas** (as 3 melhores) **cobrem alguma** das células (OU), com o contador «6 de 38 grupos · OU» e «Limpar». Peças: tocar na miniatura de uma peça dentro de uma linha aberta junta o chip «P0294» (filtra o grupo que a contém).

| | |
|---|---|
| **Filtra exatamente** | grupo aparece se **qualquer** das 3 zonas candidatas tem **uma** das células escolhidas na sua pegada (a mesma regra da pesquisa por célula, `mesaMatches`), **OU** o grupo contém uma das peças escolhidas; várias escolhas = união; opção «todas» (interseção) fica de fora da 1.ª versão |
| **Medido (alpes)** | 2 toques (células (15, 59) e (2, 63)) → **6 de 38** grupos; 1 botão novo («Selecionar») + chips; 6 linhas no ecrã |
| **Custo** | médio: ≈ 90–110 linhas JS (modo, estado, gancho no toque do tabuleiro em `initPointer`, chips, camada de seleção) e 1 linha nova na legenda (+ o teste de cobertura); sem backend; testes Playwright (toque, chips, remover, telemóvel) |
| **Bom** | é o único que responde a «o que cabe **aqui**» a olhar para o tabuleiro; zero teclado; funciona com várias células |
| **Riscos** | rouba o toque da célula (conflito com «abrir célula» e com «Sugestões»: só um modo de cada vez, com o botão a dizer qual); toque num ecrã pequeno falha a célula (zoom ou alvos grandes); só seleciona **onde**, não **quais** grupos |

### 16.2 Alternativa S2 — «Caixas nas linhas + barra de seleção» (grupos → «Só estes»)
Captura: [`mesa_sel_b_caixas_1366.jpg`](screenshots/mesa_sel_b_caixas_1366.jpg), [`mesa_sel_b_caixas_390.jpg`](screenshots/mesa_sel_b_caixas_390.jpg).

Cada linha ganha uma **caixa de seleção** (26 px de caixa dentro de um alvo de 44 px). Uma **barra fixa** no topo da lista diz «3 selecionados» com os chips das peças (P0850 ✕ …) e dois botões: **«Só estes»** (filtra a lista) e «Limpar». Os grupos escolhidos podem ser mostrados todos no tabuleiro (violeta) para comparar.

| | |
|---|---|
| **Filtra exatamente** | «Só estes» deixa **só** os grupos marcados (por id; as peças dos chips são apenas informação, vêm dos grupos); não depende da regra das zonas; pode combinar com Seguras/A confirmar (interseção) |
| **Medido (alpes)** | escolher 3 grupos = **3 toques + «Só estes» = 4**; 38 caixas + 2 botões novos (80 botões na aba, eram 40); 8 linhas no ecrã a 1366 e a 390 px |
| **Custo** | pequeno: ≈ 50–60 linhas JS (caixas, conjunto de escolhidos, barra, filtro), sem legenda nova, sem tocar no tabuleiro; testes Playwright simples |
| **Bom** | simples e previsível, não compete com os toques do tabuleiro; serve para «quero comparar estes 3» e para juntar a seleção a uma ação em lote no futuro |
| **Riscos** | 38 caixas acrescentam ruído visual à lista que acabámos de limpar (mitigação: caixas só depois de tocar «Selecionar» na barra); não responde a «o que cabe nesta célula» (para isso há a pesquisa por célula ou S1); «células» por chips só por pesquisa |

### 16.3 Recomendação
**S2 primeiro** (custo pequeno, não mexe no tabuleiro, resolve «escolher vários grupos» e não se pisa com «Sugestões»); **S1 depois, só se o Tiago sentir falta do «filtrar pelo tabuleiro»**, e já com a regra «um modo de toque de cada vez». As duas não se excluem: ambas acabam num conjunto de ids de grupos filtrado. **Por decidir (Tiago):** S1, S2 ou ambas; se as caixas aparecem sempre ou só depois de «Selecionar»; se a interseção (todas as células) é precisa. **Não implementado.**

## 17. Estados dos reports (2026-11-07)

Estados: `aberto`, `fechado` (na GUI «resolvido») e `eliminado` (escondido, restaurável). Transições (`src.reports.set_state(project, id, acao, nota="")`, o único caminho, usado pela GUI e pelo CLI): `close` aberto→fechado; `reopen` fechado→aberto; `delete` aberto|fechado→eliminado (guarda `estado_anterior`); `restore` eliminado→`estado_anterior`. Qualquer outra combinação devolve `{error}` (ex.: «R0001 já está fechado») e não escreve nada.

- **Append-only:** cada ação acrescenta UMA linha `{"evento": "estado", "id", "t", "acao", "estado", "nota", "estado_anterior"?}` a `reports.jsonl` e UM evento ao `log.jsonl` (`report_closed`, `report_reopened`, `report_deleted`, `report_restored`, informativos). Nenhuma linha anterior é reescrita (antes, fechar reescrevia o ficheiro). `read_reports` dobra os eventos `estado` (`estado`, `nota`, `fechado_em`/`reaberto_em`/`eliminado_em`/`restaurado_em`, `estado_anterior`, `n_estados`, `historico`); as linhas antigas reescritas com `estado: fechado` continuam válidas sem conversão.
- **Lista:** `list_reports(project, only_open=True, eliminados=False)` esconde os eliminados por omissão. CLI: `--close/--reopen/--delete/--restore R#### [--nota ...]`, `--list [--all] [--eliminados]` (mostra id, estado, tipo, peça, célula, texto).
- **GUI, lista:** filtro «Abertos / Resolvidos / Eliminados» e contagens no cabeçalho; cada linha é um `details` expansível (§12).
- **GUI, linha expandida** (`reportDetailBody(r)`; a seta «→» e `section#tab-report` foram retiradas): tipo · data · «editado N×», miniaturas `pose=board` e `pose=scan` a 160 px (`.rthumbs`), a captura (`/api/reports/{id}/captura`; só se o report tem `captura`; removida em erro), texto, nota, histórico de estados (`.rhist`) e as ações do estado (`div.actions.rdetail-actions`): «Ver no tabuleiro», «Editar» (aberto), «Marcar resolvido» (`dialog#estado-dlg`, nota opcional), «Reabrir», «Eliminar» (o mesmo diálogo em confirmação: «Eliminar R####? Fica escondido e pode ser restaurado.»), «Restaurar». Depois de cada ação: toast e `loadReports()`; a linha continua expandida e o filtro segue o estado novo do report (resolver a partir de «Abertos» passa a «Resolvidos»). O `EventSource` ouve `report_added`, `report_edited` e `report_changed` e recarrega a lista.
- **Testes:** `tests/test_reports_estado.py`, `tests/test_server.py` (`test_report_estado_endpoint`, `test_report_captura_endpoint`), `tests/test_gui_reports.py` (linha expandida, ações append-only, report em linha na gaveta), `tests/test_gui_suspeitas.py` (report aberto esconde a suspeita, «Falso alarme» / «Restaurar»); layout da linha expandida na matriz de `tests/test_gui_layout.py` (inclui 911 × 512 e telemóvel).

## 18. Editor de contorno (2026-11-07; reescrito por traços na mesma data)

Para peças mal recortadas (ex.: P0778 de S0023, P0651 / P0657 de S0020) o Tiago marca o scan com laço / pincel / borracha e o servidor resolve o contorno (backend em `docs/diagnostico/editor/TRACOS.md`). O contorno manual substitui o segmentado em tudo o que usa a forma (npz, recorte, folha, gémeas), mas **fica fora de todas as métricas de CV** (segmentação, E-sym, porta §6.1, cordas vs nominal): não é saída da segmentação. A primeira versão (arrastar vértices ponto a ponto num painel de 360 px) foi substituída; as pegas ficam só como retoque final opcional.

### 18.1 Ficheiros, gravação e aplicação (inalterados pelo editor novo)

- **`projects/<id>/overrides.jsonl`**, só-acrescentar, uma linha por gravação: `{t, autor: "manual", scan_id, piece, index_in_scan, contour_px (px do scan), nota, metodo: "tracos"|"vertices", auto_contour_px, auto_area_mm2, auto_origem, e, com traços, tracos (px do recorte), origem, tamanho, solver, mascara_rle}`; vale a última linha de cada peça (`src.overrides.latest_overrides`). Validação (`validate_polygon`): ≥ 20 pontos (≤ 5000), finitos dentro do scan, sem arestas que se cruzem (toques aceites), área entre 50 % e 150 % da atual. Gravação inválida: 400 com a razão, nada escrito.
- **Aplicação** (`render.rebuild_assets`, `rebuild_piece`) e **servidor** (`POST …/contorno`, lock de escrita, 409 durante um trabalho): como antes (npz / recorte / folha reescritos, evento `piece_resegmented` motivo `manual`, flags `manual_override`, reconsulta da peça ou da célula e vizinhas livres, SSE `board_changed` / `fetch_changed` / `piece_changed`). Ver TRACOS.md §4 para os campos extra.
- **Fora das métricas:** `src.overrides.is_manual(piece)`; `tools/diagnostico/gemeos/esym.py` e `segcache.py` não leem o projeto. Os scripts que leem o projeto e medem silhuetas (`triagem_r3_porta61.py`, `prado.py`, `recorte.py`, `contactos.py`, `tools/diagnostico/render/*`) ainda não filtram `manual_override` [NT: o Alpes não tinha nenhuma peça manual à data].

### 18.2 A janela

Botão **«✎ Editar contorno»** (gaveta da célula e painel da peça, ao lado de «Reportar») → `div#ced`, **sobreposição de janela inteira** (fixa a 100 vw × 100 vh, acima de tudo; `src/web/editor.js`, carregado antes de `app.js`; `S.ced`). Não troca de separador nem limpa `S.sel`; **Fechar** / **Esc** voltam à gaveta ou ao painel de onde veio (pede confirmação se há alterações por gravar). Redimensiona com a janela (resize → `cedOnResize`).

- **≥ 1200 px de largura: vistas lado a lado** = o canvas principal grande (2/3 da largura) e as 3 vistas só de leitura empilhadas à direita; **< 1200 px: uma vista de cada vez** (botões «Scan / Atual / Diferença / Final»; «Lado a lado» / «Uma vista» alterna à mão). O canvas principal é a única vista que recebe traços.
- **Barra de ferramentas** (`#ced-tools`, 300 px à direita; **faixa inferior de ≤ 42 vh em < 900 px**, rolável; botão ▾ recolhe-a; botões ≥ 40 px): ferramenta, marca, raio, ativo, desfazer / refazer / limpar, zoom, vistas, «Afinar vértices», estado, ajuda, nota, **Gravar** / Cancelar.

### 18.3 Traços e marcas

- **Ferramentas:** **laço** (L; segurar e arrastar à mão livre, ao largar fecha o polígono), **pincel** (P; polilinha de espessura 2·raio, raio 2–60 px por deslizador ou `[` / `]`), **borracha** (B; mesma geometria, `marca: null`, volta a valer o trimap automático). O pincel e a borracha mostram o círculo do raio.
- **Marcas:** **É peça** (branco, tecla 1), **Não é peça** (`fundo`, preto, 2), **Incerto** (cinzento, 3: o servidor decide ali). **Shift** força «peca» e **Alt** força «fundo» durante o traço. A barra mostra sempre «Ativo: ferramenta · marca».
- Cada traço é `{ferramenta: "laco"|"pincel"|"borracha", marca, raio_px, pontos}` em **px do recorte**, acrescentado a `S.ced.tracos`; `S.ced.pos` é o prefixo ativo. **Desfazer** (Ctrl+Z / botão) decrementa, **refazer** (Ctrl+Y, Ctrl+Shift+Z / botão) incrementa, um traço novo depois de desfazer **corta a cauda**; «Limpar traços» (com confirmação) esvazia. Os traços ativos desenham-se **já**, em local, semitransparentes nas cores das marcas por cima do recorte (camada própria; a borracha apaga as marcas por baixo).
- **Pan/zoom:** roda = zoom ao cursor, botão do meio ou espaço + arrasto = pan, pinça (dois dedos), −/+/Ajustar. Em toque, um dedo desenha, dois dedos fazem pinça / pan (o traço em curso é descartado); `touch-action: none` no canvas. As quatro vistas partilham a mesma transformação (`S.ced.view = {z, cx, cy}`: zoom relativo ao ajuste e o ponto da imagem no centro).
- **Ajuda no painel** (medido, TRACOS.md §2.4–2.5 / §7.2): «Não é peça» com pincel fino sobre a linha negra da sombra colada à peça; «É peça» sobre arte clara cor do papel que o automático cortou; «Incerto» onde quiser que o algoritmo decida.

### 18.4 Resolução ao vivo (contrato do servidor, TRACOS.md §7)

Ao abrir, depois de cada traço (`pointerup`), de desfazer / refazer / limpar: `POST /api/pieces/{id}/contorno/resolver` com `{tracos: tracos[0:pos], origem, tamanho}` (solver por omissão: GrabCut só croma, 2 iterações), **debounce de 150 ms**, **1 pedido em voo**, contador de pedidos (`S.ced.seq`): uma resposta que já não é a última é descartada e, se chegou outra alteração entretanto, volta a pedir no fim. Resposta guardada em `S.ced.res = {contour, area_mm2, valido, erro, n_pontos, ms, …}` e desenhada: polígono resolvido a **âmbar** (caminho a +0,5 px, preenchimento translúcido + traço de 1 px), contorno atual (`denso`) a **ciano tracejado**, «a resolver…» enquanto espera. Texto de estado: área em mm² e % da atual, nº de pontos, ms; quando `valido` é falso mostra o `erro` a vermelho e **Gravar fica desativado** (também enquanto há um pedido pendente, para nunca gravar um resultado desatualizado).

### 18.5 Vistas

1. **Scan** (principal): recorte + traços + polígono resolvido + contorno atual.
2. **Máscara atual**: o `denso` preenchido a branco sobre preto.
3. **Diferença**: o recorte escurecido com o resolvido contra o atual: **ganho magenta**, **perda ciano**, concordância cinzenta.
4. **Recorte final**: o recorte do scan recortado pelo polígono resolvido sobre quadriculado.

As vistas 2–4 são canvases só de leitura, redesenhadas quando `S.ced.res` (ou o retoque) muda.

### 18.6 Retoque por vértices (opcional) e gravar

- **«Afinar vértices»** alterna um modo em que o polígono resolvido aparece com pegas (≈ 1 por mm: `1 / mmpp` px de arco); arrastar uma pega, clicar numa aresta cria uma pega, Delete apaga a selecionada, Ctrl+Z desfaz (histórico local, 200 passos). Um troço entre duas pegas por tocar volta a ser o troço exato do polígono resolvido (a mesma lógica de `expand_polygon`). O retoque **não é enviado ao servidor** como traço: só o `contour` final gravado o inclui. **Mudar os traços depois de um retoque perde-o** (aviso por toast: o contorno resolve-se de novo). A validação do polígono retocado é feita no cliente (≥ 20 pontos, área 50–150 %, sem cruzamentos) e depois outra vez pelo servidor.
- **Gravar:** `POST /api/pieces/{id}/contorno` com `{contour (px do recorte, o resolvido ou o retocado), origem, tamanho, nota, tracos (prefixo ativo), solver: "grabcut"}`; depois toasts do servidor, `loadAll()` e volta à gaveta / painel (`cedLeave`); a gaveta e o painel mostram o selo violeta **«contorno manual»** + nota. Reabrir uma peça com override por traços carrega os `tracos` do GET (já traduzidos para o recorte atual) com `pos` no fim e resolve.

### 18.7 Testes e medições

- [V] `tests/test_gui_contorno.py` (Playwright, `slow`, reescrito): `test_contour_strokes_flow` a 1366×768 (sobreposição = janela, pincel «fundo», laço «peca», `res.valido` e «mm²» no estado, Ctrl+Z / Ctrl+Y / cortar a cauda, Shift força «peca», teclas L/P/B/1/2/3/`]`, «Afinar vértices» com pegas, gravar: `overrides.jsonl` +1 com `metodo: "tracos"` e os traços ativos, `piece_resegmented` +1, selo, invariantes OK, reabrir carrega os traços, Esc sem alterações fecha sem pedir, Esc com alterações pede confirmação, consola sem erros) e `test_contour_overlay_layout` nos `TAB_VIEWPORTS` (sem overflow, janela inteira, canvas ≥ 40 % da janela em «lado a lado» e ≥ 50 % em «uma vista», barra visível, botões ≥ 40 px, toque real por CDP desenha um traço nos ≤ 900 px). Capturas: `docs/gui/screenshots/contorno_tracos_{1366,1920,390}.png` e a do ensaio real `contorno_tracos_P0651.png`.
- [V] **Ensaio real** (cópia de `projects/alpes` no scratchpad; P0651 de S0020, 1366×768, 3 traços de pincel de raio 4 px, o servidor com o GrabCut por omissão) contra a GT `manual_A_photoshop.png` (maior componente, mesma grelha do scan), `src.maskcmp.mask_metrics`; os traços foram **gerados a partir da GT** (centro das 2 maiores zonas de excesso → «fundo», da maior zona em falta → «peca») e executados com o rato na GUI real:

| etapa | IoU | em falta mm² | a mais mm² | d_p95 mm |
|---|---|---|---|---|
| índice atual | 0,869 | 6,8 | 51,0 | 1,29 |
| resolvido, 0 traços | 0,941 | 11,5 | 12,4 | 0,76 |
| + «fundo» (sombra 1) | 0,945 | 14,0 | 7,8 | 0,72 |
| + «fundo» (sombra 2) | 0,949 | 15,2 | 4,9 | 0,68 |
| + «peca» (orla clara) = **gravado** | **0,954** | 12,1 | 6,1 | **0,54** |

  O polígono gravado (linha de `overrides.jsonl` da cópia: `metodo: "tracos"`, 3 traços, `solver.nome: "grabcut"`, 1121 pontos) dá exatamente estes números; o backend media 0,94 / 0,63 mm com traços sintéticos. A latência por pedido na GUI foi 300–315 ms (servidor, sem rede) neste PC.
- [F] p95 < 0,3 mm continua fora de alcance (TRACOS.md §2.4); [NT] só 1 peça e traços derivados da GT (não de um utilizador); [NT] nada em peças claras reais, noutros scans, nem em ecrã tátil físico (só toque simulado por CDP); [NT] ainda não foi usado pelo Tiago.
- **Limites desta versão:** «Afinar vértices» está completo (arrastar, inserir, apagar, Ctrl+Z) mas o histórico dos vértices é separado do dos traços (Ctrl+Z desfaz primeiro os vértices só com o modo ativo); não há «remover contorno manual» (voltar à segmentação) na GUI; editar uma peça de uma secção por ancorar reconsulta só a peça; o botão ▾ recolhe a barra mas não há atalho de teclado para isso.

## 19. Copiar / guardar PNG da miniatura (2026-11-07)

**Gesto:** botão direito (ou pressão longa onde o browser a traduz em `contextmenu`) numa miniatura de peça: a `div.pimg` dos cartões e das gavetas (o SVG por cima do `<img>` intercepta o clique, por isso o ouvinte está no contentor), as `img.rthumb` das linhas de Reports e de Suspeitas e as figuras `.rthumbs img` da linha expandida. O menu é próprio (`div#ctx-menu`, no cursor, dentro da janela; fecha com Esc, clique fora, scroll, resize ou perda de foco) e tem dois itens: «Copiar imagem (PNG)» e «Guardar PNG». Um único ouvinte delegado em `document` (`initPngMenu`) lê o id da peça e a pose do `src` da imagem clicada.

**Fonte:** `GET /api/pieces/{id}.png?pose=<board|scan, a da imagem clicada>&size=600&v=<versão>`: só a peça, fundo transparente, sem sobreposições (`size` máximo 600, o do servidor).

- **Copiar:** `navigator.clipboard.write([new ClipboardItem({"image/png": fetch(url).then((r) => r.blob())})])`. A Promise de Blob mantém a ativação do utilizador; se o browser não aceitar uma Promise, cai para `await blob` e tenta na mesma. Toast «Imagem de P#### copiada». Erro no `write` → toast com a mensagem e o «Guardar PNG» abre-se automaticamente.
- **Guardar:** `<a download="P####_board.png" href=URL.createObjectURL(blob)>` + `click()` + `revokeObjectURL`.
- **Limites:** a Clipboard API de imagens só existe em contexto seguro (`localhost`, `127.0.0.1` ou https) e com `ClipboardItem`. Com `--lan` (`http://<ip>:8765`) ou num browser sem suporte, o item «Copiar» fica desativado (`aria-disabled="true"`, `title` com a razão) e, ao clicar, o toast diz «Copiar não disponível neste browser/endereço (precisa de localhost ou https): usa Guardar PNG»; «Guardar PNG» funciona sempre.
- **Testes:** `tests/test_gui_png.py` (Chromium com permissões de área de transferência: menu, PNG copiado de 600 px com alfa 0 no canto, descarga `P####_board.png` / `_scan.png`, Esc e clique fora, cenário sem `ClipboardItem`). [NT] Firefox, Safari e telemóvel (pressão longa) não foram experimentados.

## 20. Editar posicionamento (2026-11-07)

Ajustar à mão a rotação e a posição de uma peça **colocada** quando o registo automático a desenha mal. O tabuleiro é o editor (nada de janela por cima): ficheiro `src/web/pose.js` (carregado antes de `app.js`), camada `#pose-layer` no SVG, painel `#pose-panel` na gaveta da célula. Backend e contrato: `docs/diagnostico/render/POSE_MANUAL.md`.

- **Entrada:** botão «⤧ Editar posicionamento» ao lado de «Editar contorno» na gaveta da célula (só `estado == colocada`). Abre `GET …/pose`, faz zoom à célula ±1,5 e desenha: o contorno das vizinhas colocadas (ciano, fixo), a peça (scan a 85 % de opacidade, `/api/pieces/{id}.png?pose=scan&size=600`, quadrado de 1,8 células centrado no pivô, rodado e deslocado com a pose candidata) e o contorno âmbar a 2 px. O raster do tabuleiro por baixo continua com a pose antiga até gravar (aviso no painel). Com o modo aberto, os cliques no tabuleiro deixam de abrir células e mudar de aba descarta a edição.
- **Transformação:** `transform="translate(tx ty) rotate(θ)"`, `tx = (c − 0,5) + dx/w`, `ty = (l − 0,5)·hr + dy/w`; θ positivo = sentido horário, como o render.
- **Sem encaixe automático (decisão de 2026-11-07):** θ, dx, dy só mudam por ação explícita do utilizador. Os botões «Pose automática» (repõe a pose automática nos campos, sem gravar) e «Alinhar a 90°» (θ ao múltiplo de 90° mais próximo, sem gravar) são as únicas exceções e têm rótulo. A GUI não converte folga em deslocamento: a folga não muda 1:1 com o deslocamento (num lado com tab, 1 mm de deslocamento ≈ 0,67 mm de folga).
- **Ajustes:** arrastar a peça (dx/dy = Δ em células × w; o pan continua fora da peça, com o botão do meio ou pinça); bola âmbar a 1,1 células do pivô (roda θ pelo ângulo ao pivô); Alt + roda do rato ±0,2°; teclas setas ±0,1 mm (Shift ±0,5 mm), Q/E ∓/± 0,1° (Shift ±1°), Enter grava, Esc cancela (com confirmação se houver alterações); campos numéricos θ (°), dx, dy (mm), passo 0,1. dx/dy ficam presos aos `limites` (±0,5 célula; o painel diz «no limite do deslocamento»).
- **Ao vivo:** a cada mudança, debounce de 120 ms, 1 pedido em voo, respostas antigas descartadas (contador `P.seq`), `POST …/pose/avaliar`. O painel mostra N/E/S/W com o `gap_mm`: verde |gap| ≤ 0,3 mm, âmbar ≤ 0,8, vermelho > 0,8; negativo = «sobrepõe», positivo = «folga»; «—» sem vizinha. Mais: pior junta (`pior_mm`, `pior_dir`), consistência de orientação (ok / «há melhor rotação» / «orientação impossível» + `texto`), a diferença à pose automática (Δθ, Δdx, Δdy) e os `ms`.
- **Gravar** (nota opcional): `POST …/pose`; os botões e campos ficam desativados com «a gravar…» (≈ 4–9 s); toast com os segundos e as folgas; sai do modo, mostra primeiro a gaveta com o chip violeta **«pose manual»** (θ, dx, dy, nota; também em `openPiece`) e depois recarrega o tabuleiro. **Repor automática** (só aparece se há pose manual; pede confirmação): `POST …/pose/repor` (≈ 4 s). Cancelar / Esc: sai sem gravar.
- **Telemóvel (≤ 900 px):** o painel sobe para logo abaixo do cabeçalho da gaveta (as folgas ficam visíveis sem deslizar), botões e campos ≥ 44 px, arrastar a peça com um dedo (`touch-action: none` no tabuleiro); a pega de rotação tem uma zona de toque de 0,64 células de diâmetro. Se a peça e a pega se sobrepõem, a pega ganha; pegar na peça pelo lado oposto.
- **Testes:** `tests/test_gui_pose.py` (Playwright, `slow`): `test_pose_mode_adjust_and_save` a 1366×768 (camada com imagem, 1 contorno da peça e 2 das vizinhas; `S.pose.cand` = pose efetiva e sem mudanças sozinho; setas, Shift+seta, Q, campo θ, «Alinhar a 90°», «Pose automática», arrastar com o rato ≈ Δpx convertido, pega de rotação; painel com «mm», folga W e `ms`; Esc com alterações pede confirmação e recusar mantém o modo; gravar: `pose_set` +1 com a nota e os valores, chip, `pose_manual` na API; reabrir mostra «Repor automática»; repor: `pose_cleared` +1 e o chip some; consola sem erros) e `test_pose_layout` nos `TAB_VIEWPORTS` (sem overflow horizontal, painel dentro da largura, botões ≥ 40 px no telemóvel, toque real por CDP arrasta a peça a 390×844). Capturas: `docs/gui/screenshots/pose_1366.png`, `pose_390.png` (projeto sintético) e `pose_P0240.png` (cópia dos Alpes).
- **Ensaio real (cópia de `projects/alpes`, P0240 em (1,63), borda N):** pose automática → E (P0236) −0,08 mm, W (P0245) −0,61 mm; com dy = −0,26 mm → E −0,09, W −0,70, pior −0,70 (Oeste), orientação sem falhas, 67–75 ms por avaliação [V] (bate com POSE_MANUAL.md). Gravar 4,3 s no servidor / 5,0 s até ao chip (uma corrida a frio demorou 20–28 s até ao chip, com a cache do raster fria); repor 3,3 s no servidor.
- **[NT]:** pinça de dois dedos com a peça debaixo de um dedo (o segundo dedo é tratado pelo tabuleiro só se pousar fora da peça); Firefox/Safari; telemóvel físico; o efeito da pose manual no raster inteiro com várias peças editadas.

## 21. Molde do buraco: «Candidatas para este buraco» e aba «Buracos» (2026-11-07, M11)

Ranking das peças soltas para uma célula **vazia com ≥ 1 vizinha montada** (`src/fit.py`, critérios e números em `docs/diagnostico/fit/M11_CRITERIOS.md` e `M11_RESULTADOS.md`). É um **ranking, não uma proposta**: nada entra em «Vai buscar»; «sem candidata fiável» é um resultado legítimo. Ficheiro `src/web/holes.js` (carregado antes de `app.js`), camada `#hole-layer` no SVG do tabuleiro, secção `#tab-buracos` **sem botão na barra do topo** (a barra está dimensionada e testada para 6 abas): entra-se pelo botão «Buracos: candidatas por confiança» no fim de «Vai buscar» ou pelo termo de pesquisa `buracos`; tem «← voltar».

- **Servidor:** `GET /api/holes` (todos os buracos × todas as soltas, afetação conjunta, ordenados por confiança; cache por versão do log; a primeira vez calcula em segundo plano — tiras de imagem das peças montadas, ≈ 0,3 s por peça, guardadas em `render/fit/strips.npz` — e responde `a_calcular: true` até acabar, SSE `holes_changed`), `GET /api/holes/{l}/{c}` (um buraco: ranking + `desenho` com os contornos das vizinhas e de cada candidata, como `GET …/pose`; enquanto a lista não está pronta calcula só essa célula, `parcial: true`), `POST /api/holes/{l}/{c}/confirmar | rejeitar {piece, nota?}` → `src.confirm.confirm(hole= | hole_reject=)` → eventos `hole_confirmed` (+ `placed` com origem `buraco`) / `hole_rejected`, ambos com `rank, custo, margem, confianca, m, fit_version` (a verdade de terreno de `python -m src.fit --relatorio`). Toda a escrita invalida a cache e relança o cálculo em segundo plano.
- **Gaveta da célula:** bloco «Candidatas para este buraco» depois das «Propostas»: chip de confiança (`alta` verde / `média` âmbar / `sem fiável` cinzento) com o nº de vizinhas e as soltas com custo finito; aviso destacado com **1 vizinha** («confiança baixa, nunca alta»); nota quando é «sem candidata fiável» (as 3 mais próximas ficam só para orientar); até 3 cartões, cada um com um **mini-SVG 3 × 3 células** da candidata (imagem do scan rodada por `theta_deg`, contorno âmbar) **no buraco** com os contornos das vizinhas (ciano), «Saco N · nº X», `#rank`, custo J, margem (só na 1.ª), «rodar θ°», chips «atribuída» / «é a melhor para (l, c)» (afetação conjunta), uma linha por vizinha (forma mm, ΔE, |ΔL|, penalização de corda), botões **Coloquei / Não encaixa / Ver no tabuleiro / Reportar**; «razões técnicas» recolhidas. «Ver no tabuleiro» desenha a candidata e as vizinhas em `#hole-layer` e aproxima; sair da gaveta limpa a camada.
- **Secção «Buracos»** (o botão de entrada traz o nº de buracos `alta` com ≥ 2 vizinhas): resumo (n buracos × n soltas, contagem por confiança, «parâmetros por calibrar» se o perfil não tiver `calibration.buraco`), filtro de texto (célula, peça, saco, zona, confiança), uma linha por buraco ordenada alta·≥ 2 viz. → alta → média → sem (margem dentro de cada grupo; buracos sem nenhuma solta de custo finito ficam fora, contados); clicar abre a célula. Pesquisa: o termo **`buracos`** abre a secção.
- **Testes:** `tests/test_server_holes.py` (TestClient: lista e cache, um buraco com desenho, rejeitar → evento com meta e peça fora do ranking dessa célula, confirmar → `hole_confirmed` + `placed`, 409 quando ocupado) e `tests/test_gui_holes.py` (Playwright, `slow`: bloco e cartões a 1366×768, 911×512 (= 1366×768 a 150 %) e 390×844 sem overflow, botões ≥ 40 px no telemóvel, «Ver no tabuleiro» desenha a camada, secção «Buracos» lista a célula, termo «buracos», fluxo rejeitar → confirmar com os eventos no log). Capturas `docs/gui/screenshots/buracos_gaveta.png`, `buracos_lista.png` (projeto sintético).
