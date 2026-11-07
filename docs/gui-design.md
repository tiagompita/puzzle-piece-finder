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
| `GET /api/reports[?todos=1]` | relatórios abertos (ou todos) |
| `GET /api/events` | SSE: `hello`, `board_changed`, `fetch_changed`, `ingest_progress`, `prepare_progress`, `report_added`, `ready` |

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
- **CLI** (`src/reports.py`): `python -m src.reports --project projects/alpes --list` e `--close R0001 --nota "..."`.
- **"Vai buscar" em dois grupos** (item 6): `fetch.json` ganha, só na resposta de `/api/fetch`, `vizinhas_montadas` (vizinhas 4-conexas `colocada` ou `ocupada_legado` com fonte `tiago`; `foto` não conta) e `grupo` (`coloca_agora` com ≥ 1, ou posição conhecida que passou a colocável; senão `guarda_posicao`, cujo botão é "Guardei num saquinho (l, c)" = `position_known` com `nota: "saquinho"`, ainda não guardada no log).

## 12. Abas «Guardadas» e «Reports» (2026-11-05)

«Vai buscar» só mostra peças com ≥ 1 vizinha ortogonal montada (`fetch_group`: diagonais e moldura não contam; borda colocada conta; sem exceção para `posicao_conhecida`). As restantes estão na aba **Guardadas**: aviso «Não procurar ainda» e a secção «Guardadas com posição, ainda sem vizinha» recolhida por omissão; saem também do realce do tabuleiro. A aba **Reports** é só de leitura (`GET /api/reports?todos=true`): ID, estado (aberto / resolvido), tipo, peça e célula, texto; filtro aberto/resolvido e contagem de abertos no separador. Os reports fecham-se no ficheiro (`python -m src.reports --close`).

**Linhas clicáveis (2026-11-07):** cada linha da aba Reports é um botão (`role=button`, `tabindex=0`; clique ou Enter) que localiza o que o report aponta: com peça, o mesmo caminho da pesquisa por peça (§13); só com célula, a gaveta dessa célula. Mostra a miniatura da peça (`/api/pieces/{id}.png?pose=scan&size=64`) e chips visíveis com o ID da peça e a célula, antes do estado e do tipo. Continua só leitura: o clique não chama `/api/confirm` nem `/api/report` e o `log.jsonl` não ganha eventos (testado).

## 13. Abas no topo e «Editar report» (2026-11-05)

As 6 abas estão na barra de topo (`header#top > nav#tabs`), ao lado do nome e do progresso; abaixo de 1181 px ocupam uma 2.ª linha e abaixo de 900 px usam rótulos curtos (sem scroll horizontal; testado de 360 a 1920 px). O botão de report de um cartão, da célula ou da peça passa a **«Editar report»** quando já existe um report **aberto** dessa peça (ou dessa célula, se o report não tem peça): abre o mesmo diálogo preenchido («Editar R####», «Guardar edição»). `reports.jsonl` é append-only: editar acrescenta uma linha `{"evento": "edicao", "id", "t", "tipo"?, "texto"?}` (`POST /api/report/{id}/edit`; evento de log `report_edited`); a lista de Reports marca «editado N×». Só se editam reports abertos.

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
