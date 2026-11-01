# GUI "mesa de montagem" — o que está construído

Atualizado em 2026-11-01 (substitui a proposta da ronda anterior e a maquete estática, que não foi aprovada). Etiquetas: **[V]** verificado (teste ou captura vista), **[NT]** não testado, **[F]** testado e a falhar. Como correr e o que mostram as capturas: [`docs/gui/README.md`](gui/README.md).

## 1. Objetivo

Uma pessoa (Tiago) junto ao tapete, com sacos numerados. A GUI é a **vista do estado do projeto** e a **lista do que fazer a seguir**: o tabuleiro tem de parecer o puzzle físico; cada sugestão diz de que saco e com que número vem a peça, como fica rodada e onde vai; um toque confirma e a lista regenera-se.

## 2. Stack (decidido e construído)

Web local: `python -m src.server` (FastAPI + uvicorn) + `src/web/` (`index.html`, `app.js`, `app.css`; JS sem framework nem build). Por omissão escuta em `127.0.0.1:8765`; `--lan` abre a `0.0.0.0` com aviso escrito na consola (**sem login**). O Tkinter (`src/gui.py`) fica como está até ser removido; não conhece lotes, mapa nem gémeas.

```
 browser (PC / telemóvel)  --HTTP + SSE-->  src/server.py (Gui + rotas)  -->  src/confirm.py / Project (src/state.py)
   src/web (estático)                         caches: raster do tabuleiro,       log.jsonl (fonte de verdade)
                                              fantasmas, folhas, recortes        render.compose_board / query / ingest
```

- **Escritas**: só por `src.confirm.confirm` (colocar, rejeitar, posição conhecida, ancorar, desancorar, descartar; a mesma reconsulta incremental da CLI), `Project.unplace` (+ reconsulta da célula e da gémea) e `ingest.ingest_scan` + `query.run_query` completo. Um lock (`Gui.wlock`) serializa-as; uma escrita durante um trabalho em curso (importação, preparação) responde 409. Depois de cada escrita: invariantes verificadas por `confirm` (`check_invariants(disk=True)`), recorte limpo e registo fino (com a imagem) das peças acabadas de colocar escritos em `render/clean/` e `render/placements.json`, eventos SSE `board_changed` e `fetch_changed` [V: `tests/test_server.py`].
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
| `POST /api/confirm` | `{acao: place\|reject\|position_known\|anchor\|unanchor\|discard\|unplace, piece, cell, section, rot, mirror, reason, origin}` → `{ok, mensagens, invariantes, n_propostas, segundos, celulas_mudadas}` ou 400 `{error}` / 409 |
| `POST /api/ingest` | multipart `file` + `lote` + `dpi` → grava em `images/pieces/lotes/loteNN_<data>_<nome>`, trabalho em fundo (segmentar → `run_query` completo), progresso por SSE `ingest_progress` |
| `GET /api/events` | SSE: `hello`, `board_changed`, `fetch_changed`, `ingest_progress`, `prepare_progress`, `ready` |

`unplace` não estava na lista pedida; foi acrescentado porque um toque errado em "Coloquei" precisa de desfazer (só para peças colocadas pelo log; as de secções desfazem-se com "Desancorar grupo").

## 4. Ecrãs

Uma página: tabuleiro à esquerda, painel à direita com separadores **Vai buscar · Lotes · Mesa · Importar**, e o painel **Célula** que abre ao tocar numa célula (botão "← voltar"). Legenda fixa em baixo.

- **Tabuleiro**: `<img>` raster + overlay SVG no mesmo `viewBox` (unidades de célula: x = coluna, y = linha × h/w); zoom/pan por roda, arrasto e pinça; duplo clique aproxima; botões + / − / ajustar. Com zoom acima de ~66 px/célula reais, a região visível é pedida de novo ao servidor a mais resolução (até 240 px/célula ≈ 300 dpi) e sobreposta: com zoom, vê-se o recorte real a alta resolução [V: `progresso_zoom_relva.jpg`]. A grelha só aparece a partir de ~22 px/célula; os fantasmas a partir de ~7 px/célula (e com o interruptor ligado).
- **Vai buscar**: cartões agrupados por saco, pela ordem do `fetch.json`. Cada cartão: "Saco N · nº X" grande; célula alvo e decisão em palavra (aceite / ambígua); a peça **rodada como fica** (`theta_deg`), com ▲ = topo do tabuleiro, quadrado tracejado = célula e o fantasma da gémea por cima; minimapa com a célula; a folha do saco com a peça a âmbar (toque amplia); razões em frases (forma: diferença X mm (limite t95); margem para a 2.ª candidata (mínimo); imagem: ΔE); botões **Coloquei / Não encaixa / Guardar posição / Ver no tabuleiro**; "razões técnicas" recolhidas. Estado vazio: "Nada a ir buscar agora" + botão Importar. Sugestões suprimidas (candidata única) numa nota recolhida.
- **Célula**: o tabuleiro a 300 dpi (3 × 3) ao lado da arte, com o fantasma e as marcas da célula; estado, gémea (clicável), peça e como chegou; propostas com os mesmos cartões; vizinhas; "Desfazer colocação" ou "Desancorar grupo".
- **Lotes**: um bloco por saco com as folhas (miniaturas, toque amplia) e a grelha de peças (miniatura como digitalizada, nº, célula ou estado; chave de cores dos estados no topo). Tocar numa peça colocada/posição conhecida abre a célula; numa solta abre o painel da peça (propostas, folha, "Descartar").
- **Mesa**: grupos por ancorar (ordenados pela margem do 1.º candidato), miniatura, top-3; "Ver" desenha a pegada a violeta e aproxima; "Ancorar aqui" (com confirmação) usa `confirm(anchor=…)`. Candidatos com peças fora da grelha ficam desativados; células já colocadas são avisadas.
- **Importar** (pensado para o PC): ficheiro, nº do saco (proposta: o seguinte ao maior), dpi; progresso em linhas; no fim, ligações para "Vai buscar" e para o saco.
- **Telemóvel** (`max-width: 700px`): tabuleiro em cima (40 % da altura), legenda compacta (só rótulos, em várias linhas, sempre visível), painel como folha inferior com pega; tocar na pega expande a folha e reduz o tabuleiro. Alvos de toque ≥ 44 px (botões de zoom 40 px no telemóvel).

## 5. Legenda (tabela única)

A tabela `LEGEND` de `src/server.py` é a única fonte: o servidor devolve-a em `/api/board`, a página desenha a legenda a partir dela com amostras que usam **as mesmas classes CSS** do tabuleiro (as linhas "raster" mostram um pedaço real do raster), e `tests/test_server.py` falha se alguma classe `b-*` usada em `src/web` não tiver linha ou se alguma linha não tiver estilo.

| Símbolo | Classe | Significa |
|---|---|---|
| peça com imagem | (raster) | Peça colocada: recorte real do scan, limpo da franja e registado na célula |
| arte esbatida | (raster) | Célula vazia: só a arte da caixa a 34 % |
| tracejado cinza-azulado | `b-legado` | Ocupada sem silhueta: cheia na foto do tabuleiro, peça ainda não digitalizada solta |
| quadrado vermelho | `b-borda-falta` | Borda em falta: célula de borda vazia |
| quadrado âmbar cheio | `b-buscar` | Vai buscar: peça proposta, aceite |
| âmbar tracejado | `b-buscar-ambigua` | Vai buscar com dúvida: confirmar pela imagem |
| âmbar pontilhado | `b-buscar-par` | Par de soltas: célula só provável |
| quadrado ciano | `b-conhecida` | Posição conhecida: peça guardada à espera de vizinha |
| contorno branco tracejado com a forma da peça | `b-fantasma` | Fantasma: contorno da gémea colocada rodado por `profile.twin_rotation_deg()` (180° neste puzzle) |
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

## 7. Desempenho medido (cópia de `projects/alpes`, 575 colocadas, este PC)

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
- Teste num telemóvel real pela LAN (Safari / Chrome) [NT]; regeneração completa num clone limpo [NT]; importação de um scan real pela página [NT] (testada só com um scan sintético).

## 9. Achado desta ronda (fora da GUI)

Depois de "Desfazer" P0100 de (3, 37), a reconsulta incremental (`run_query(only_cells=…)`) deixou P0100 como **suprimida** ("candidata única") em vez de voltar a "aceite": no modo incremental, as peças já propostas noutras células saem do conjunto de candidatas, por isso sobra uma só e a regra de 2026-11-01 suprime-a. O mesmo pode acontecer depois de "Não encaixa". É comportamento de `src/query.py` (não alterado aqui); uma reconsulta completa (`python -m src.query`) repõe a lista.

## 10. Perguntas ao Tiago

1. O tabuleiro parece o puzzle físico nas capturas (`docs/gui/screenshots/`)? A arte a 34 % por baixo das células vazias está bem, ou preferes mais clara/escura?
2. Telemóvel: qual (Android / iPhone) e que browser? Consegues abrir `http://<pc>:8765` com `--lan` (firewall)?
3. Fantasmas ligados por omissão — ficam?
4. A lista deve agrupar por saco (como agora) ou seguir só a ordem de confiança?
5. "Ancorar aqui" na Mesa coloca o grupo todo de uma vez: queres um passo intermédio (ver as peças sobre a arte antes de confirmar)?
