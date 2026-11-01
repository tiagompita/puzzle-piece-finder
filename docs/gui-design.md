# Desenho da GUI — "mesa de montagem" (proposta para aprovação do Tiago)

Escrito em 2026-11-01. É só desenho: nenhum código da GUI nova existe. Etiqueta **[V]** = visto no código/ficheiros hoje; **[NT]** = não testado; **[P]** = proposta. Fontes: `CLAUDE.md`, `docs/estado-e-plano.md` §0 e §10, `docs/plano-m10-m12.md`, `src/gui.py`, `src/profile.py`, `projects/alpes/puzzle.json`.

## 1. Objetivo e utilizador

Uma só pessoa (Tiago), junto ao tapete, com sacos numerados de ≈ 32 peças. O programa não é "um matcher com botões": é a **vista do estado do projeto** e a **lista do que fazer a seguir**. Fluxo do §0 do plano:

1. Importa um scan de um saco (lote N) no PC.
2. O programa sugere, por força do sinal: gémea colocada, par de soltas, buraco, caixa (só textura).
3. Vai ao saco, pega na peça pela imagem ("lote 3, peça 17"), coloca, toca **Coloquei**.
4. O mapa atualiza-se e a lista regenera-se.

Estado de hoje: `src/gui.py` [V] é uma janela Tkinter para uma foto/scan de peças contra a imagem da caixa (Load / Segment / Match / Match All / Export JSON...). Não conhece lotes, mapa, gémeas nem confirmação. `src/state.py` ainda **não existe** [V: ausente em `src/`]; `src/profile.py` existe e expõe `twin(l, c)` e `twin_rotation_deg()` [V], e `projects/alpes/puzzle.json` tem a arte (`art.bbox`) e a calibração [V].

## 2. Tkinter vs PySide vs web local

| Critério | Tkinter (hoje) | PySide6 | Web local (FastAPI + browser) |
|---|---|---|---|
| Zoom/pan com 3008 recortes | `Canvas` redesenha em Python; PIL a reamostrar por nível de zoom; fluidez fraca [NT] | `QGraphicsView` bom | SVG/CSS no browser, com GPU; zoom por `viewBox` [NT, alvo 60 fps] |
| Alfa (arte a 20 %, fantasmas) | Canvas sem alfa real; só compondo bitmaps PIL à mão | Nativo | Nativo (`opacity`, `stroke-opacity`) |
| Toque / telemóvel | Sem toque, sem telemóvel | Só no PC | Pinça e toque nativos; o telemóvel fica junto ao saco |
| Dependências | Já cá estão | +~200 MB | `fastapi`, `uvicorn` (leves); frontend sem build |
| Empacotamento | Trivial | Pesado (PyInstaller, licença LGPL a ler) | Nenhum: `python -m src.server` |
| Reutiliza `state.py` | Sim | Sim | Sim (processo Python único) |
| Esforço | Médio, resultado fraco | Alto | Médio; duas linguagens |
| Risco | Qualidade visual e desempenho não chegam | Complexidade/empacotamento para um só utilizador | Sem autenticação (LAN), browser moderno, JS a manter |

**Recomendação [P]: interface web local.** Razões: o ecrã mais importante (tabuleiro 64 × 47 com arte translúcida, recortes e fantasmas) é composição com alfa + zoom/pan, onde o browser é nativo e o Tkinter penoso; a lista "vai buscar" é útil **no telemóvel ao lado do saco**, o que nenhum toolkit desktop dá; o servidor reutiliza `Project` diretamente e o telemóvel não precisa de instalação.

**Contra-argumentos honestos:**
- Dois idiomas (Python + JS); o JS fica pequeno e sem framework, mas é mais uma coisa a manter.
- **Sem autenticação**: quem estiver na tua Wi-Fi vê e altera o estado. Por omissão escuta em `127.0.0.1`; `--lan` abre à rede e fica documentado com este aviso.
- Precisa de browser moderno (Safari/Chrome recentes).
- SVG com 3008 `<image>` pode engasgar [NT]; mitigação no §7 (miniaturas, só montar no DOM o que está no viewBox).

**Fallback:** se recusares a web, um Tkinter mínimo (lista "vai buscar" + Coloquei / Não encaixa + importar) sobre o mesmo `state.py`; o tabuleiro fica como imagem estática gerada com PIL. Perde-se zoom suave, fantasmas interativos e o telemóvel.

## 3. Arquitetura

```
 telemóvel / PC  --HTTP + SSE-->  FastAPI (src/server.py)  -->  Project (src/state.py)
   HTML/CSS/JS estático                :8765                      log.jsonl (append-only)
   (maquete em docs/gui/)                                         board == replay(log)
```
Servidor: `python -m src.server --project projects/alpes [--lan]`, em `http://<pc>:8765`. Frontend estático, sem build. O servidor é **fino**: valida, chama `Project`, devolve JSON. Nenhuma regra do puzzle no frontend.

| Endpoint | Devolve / faz |
|---|---|
| `GET /api/board` | 47 × 64 células: `estado` (`vazia`/`ocupada_legado`/`colocada`), `peca_id`, `fonte` (`log`/`foto`/`legado_scan`); progresso (n/3008, por origem) |
| `GET /api/pieces/{id}` | contorno em mm, 4 lados (tipo, corda), estado, lote, `n_no_lote`, célula; recorte PNG em `/api/pieces/{id}.png` |
| `GET /api/fetch` | lista "vai buscar" ordenada por sinal: `{peca, lote, n_no_lote, celula, origem, confianca, razoes}` |
| `GET /api/ghosts` | gémeas pendentes: `{celula_gemea, peca_origem, path_mm}` com o contorno já transformado pelo perfil (§5) |
| `GET /api/holes` | buracos (≥ 2 vizinhas colocadas) com o molde (lados livres das vizinhas) |
| `GET /api/lots` | por lote: nº de peças, colocadas, pendentes, folha numerada (overlay PNG) |
| `GET /api/sections` | grupos soltos (`blocos_pNN`, secções por ancorar): miniatura, top-3 de zona com confiança |
| `GET /api/cell/{l}/{c}` | tudo do popup: estado, peça, gémea (célula/peça), fantasma, molde, recorte da arte |
| `POST /api/confirm` | `{acao: place \| reject \| position_known \| anchor, peca, celula, origem, rank}` |
| `POST /api/ingest` | multipart: scan + `lote` + `dpi`; devolve `job_id`; progresso por SSE |
| `GET /api/events` | SSE: `board_changed`, `fetch_changed`, `ingest_progress` → o cliente refresca só o que mudou |

Escritas: **todas** passam por `Project` e acabam em `log.jsonl`; o servidor nunca edita `board.json` diretamente (invariante `board == replay(log)`, §10 do plano). Um lock simples serializa as escritas (utilizador único).

## 4. Ecrãs

Navegação (barra de cima; em telemóvel, barra de baixo): **Progresso · Vai buscar · Lotes · Mesa · Importar**. A célula é um popup sobre qualquer vista.

### (a) Progresso (`index.html`)
```
+- Progresso ------------------------------------ 641/3008 [###.......] -+
| gémea 212 · buraco 18 · par 6 · legado 405     [x] fantasmas [x] legado |
|                                                [x] vai buscar [ ] arte |
| +------------------------------------------------------------------+ |
| | arte da caixa a ~20 % de opacidade                               | |
| |  ... ... ... ... . . . ┈┈┈ ┈┈┈ . . .      (┈ = fantasma da gémea)| |
| |  ... ... ... ... . . . . . [O] . . . .     ([O] = vai buscar)    | |
| |  ### ### ### ### ### ### ### ### ###       (# = recorte real)     | |
| |  /// /// /// ///                          (/ = legado, hachura)   | |
| +------------------------------------------------------------------+ |
| roda/pinça: zoom · arrastar: pan · toque/clique numa célula: popup    |
+-----------------------------------------------------------------------+
```
- Camadas SVG, de baixo para cima: arte (opacidade ajustável), hachura do legado, recortes das colocadas, fantasmas, realce "vai buscar", grelha só com zoom suficiente.
- `ocupada_legado` = ocupada por foto/legado sem silhueta: hachura fina, sem recorte (honesto: não há forma).
- Barra de progresso n/3008 e por origem (gémea / buraco / par / legado / manual).
- Toggles guardados em `localStorage`.

### (b) Vai buscar (`fetch.html`)
```
+- Vai buscar (14) --------------------------------------------------+
| +--------+ Lote 3, peça 17            origem: gémea de (44,3)      |
| | recorte| -> célula (4, 62)          confiança: ●●●○ aceite       |
| | peça   | forma 0,31 mm · margem 2,4 · imagem ΔE 38 ≤ p90 50       |
| +--------+ [ Coloquei ] [ Não encaixa ] [ Guardar (posição conhecida) ] |
| +--------+ Lote 5, peça 02  -> (5, 60) ...                          |
+--------------------------------------------------------------------+
```
Ordem = força do sinal (gémea → par → buraco → caixa). Tocar no cartão realça a célula no tabuleiro e abre o popup. Alvos ≥ 44 px. Lista vazia: "Nada a ir buscar. Importa um scan para começar."

### (c) Lotes / sacos (`lotes.html`)
```
 Lote   Peças  Colocadas  Pendentes  Folha
  1      32       9          23      [ver folha numerada]
  3      31       4          27      [ver folha numerada]
```
Clicar num lote lista as suas peças (miniatura, número, estado). A folha é o overlay numerado devolvido pelo `ingest`, para guardar com o saco.

### (d) Mesa de apoio (`mesa.html`)
```
+- Grupo blocos_p02 (14 peças) ---------------------------+
| [miniatura do grupo]   top-3 de zona:                    |
|                        1) (20..23, 31..35)  conf. 0,62   |
|                        2) ...                            |
| [ Ancorar em (l, c) ]  [ Ver na caixa ]  [ Descartar ]   |
+----------------------------------------------------------+
```
Grupos soltos ainda sem posição. Ancorar (`anchor`) é sempre confirmado por ti; o programa nunca ancora em silêncio com confiança baixa (§10 do plano: "perguntar, não adivinhar").

### (e) Célula (`celula.html`, popup)
```
+- Célula (4, 62) ------------------------------- [x] -+
| estado: vazia · gémea: (44, 3) colocada (P0187)       |
| +-- arte --+ +- fantasma -+ +- molde (vizinhas) -+     |
| | recorte  | | contorno   | | lados livres      |     |
| +----------+ +------------+ +-------------------+     |
| coincidência fantasma/molde: 0,31 mm  * dupla         |
| Sugestão: lote 3, peça 17 (gémea)                     |
| [ Colocar aqui ] [ escolher outra peça v ]            |
+-------------------------------------------------------+
```
Célula colocada mostra a peça (recorte, lote), a gémea e "Desfazer colocação" (`unplaced`).

### (f) Importar scan
```
+- Importar scan -----------------------------------+
| Ficheiro: [escolher...]  Lote: [ 4 ]  dpi: [300]  |
| [#######...] segmentar > forma > gémeas > pares   |
| Resultado: 31 peças, 3 propostas · [ver folha]    |
| (overlay numerado com os números do saco)         |
+---------------------------------------------------+
```
Só no PC (ficheiros grandes). No fim abre "Vai buscar".

## 5. O fantasma da gémea

**Ideia (Tiago):** para cada peça conhecida cuja gémea ainda não está montada, desenhar na célula da gémea o contorno exato do recorte rodado 180°, como pré-visualização para procurar a peça à mão (forma + imagem da célula).

- **Dados:** contorno em mm da peça colocada (campo da peça no §10 do plano), centrado na sua célula. O servidor calcula `celula_gemea = profile.twin(l, c)` [V] e roda o contorno por `profile.twin_rotation_deg()` [V] em torno do centro da célula gémea. **Nada fixo no código**: outro puzzle com outra simetria muda o perfil, não o frontend. O frontend recebe só `path_mm` já transformado.
- **Desenho:** `<path>` com traço claro de 1,5 px semitransparente (`vector-effect: non-scaling-stroke` para não engrossar com o zoom), preenchimento ≈ 0. Só existem fantasmas de gémeas pendentes (célula gémea vazia); ao colocar, o fantasma desaparece.
- **Molde do buraco:** quando a célula gémea tem vizinhas colocadas, o servidor calcula também o contorno-molde (lados livres das vizinhas, `GET /api/holes`). Se os dois contornos coincidem dentro de ≈ 0,5 mm (limiar vindo do perfil/calibração, não do frontend) → **confirmação dupla**: cor própria e estrela no popup. Se discordam, mostram-se ambos e a distância: sinal de peça mal colocada ou mal ancorada.
- **Toggle** no Progresso; por omissão só visível com zoom suficiente para se ver, para não poluir.
- **Ressalva [NT]:** o fantasma mostra a forma esperada, não prova que a peça existe; a prova continua a ser o `find_twin` (forma + imagem obrigatória). Depende também de a silhueta da peça estar no índice (regra de produto: toda a peça passa solta pelo scanner; o legado só ganha silhueta depois de ingerido).

## 6. Linguagem visual

- **Fundo neutro escuro** (≈ #16181b): a arte colorida lê-se melhor.
- **Uma só cor de destaque** (âmbar ≈ #ffb000) reservada a "vai buscar"; confirmação dupla em ciano; avisos em vermelho discreto. Nada mais compete.
- Fantasmas em traço claro (branco ~60 %); legado com hachura fina a 45° em cinza-azulado; vazias sem cobertura (só a arte por baixo).
- Tipografia do sistema (`Inter, "Segoe UI", system-ui`), números tabulares em "lote N, peça X".
- Alvos de toque ≥ 44 px; zoom por roda (PC) e pinça (telemóvel); duplo toque ajusta à vista.
- Estados vazios com uma frase útil ("Importa um scan para começar.", "Nada a ir buscar: tudo colocado ou sem sugestões.").
- No telemóvel só **Vai buscar** e o tabuleiro em ecrã inteiro; importar fica no PC.

## 7. Plano de implementação (ronda seguinte)

Cada etapa fica utilizável sozinha.

| # | Etapa | Utilizável como |
|---|---|---|
| 1 | `src/server.py` + tabuleiro só leitura (arte, colocadas, legado, zoom/pan, popup simples) | ver o progresso |
| 2 | Vai buscar + `POST /api/confirm` (place / reject / position_known) + SSE | ciclo buscar, colocar, confirmar |
| 3 | Fantasmas + popup completo da célula (gémea, molde, confirmação dupla) | procurar peças à mão |
| 4 | Importar scan (`ingest`, progresso, overlay numerado) | dispensa a CLI |
| 5 | Lotes e mesa de apoio (`anchor`) | gestão de sacos e grupos |
| 6 | Layout estreito para telemóvel (barra inferior, cartões grandes) | usar ao lado do saco |

Dependências: as etapas 2 em diante precisam de `src/state.py` (M12) e `src/twin.py` (M10) do plano M10–M12; a etapa 1 pode arrancar com dados de `projects/alpes/` e a maquete (§8).

**Critérios de aceitação:**
- lista "vai buscar" regenera em **< 1 s** após uma confirmação;
- tabuleiro com 3008 recortes faz zoom a **≈ 60 fps** [NT, a medir]: recortes em miniatura ≤ 48 px, `<image href>` por peça, só os visíveis montados no DOM;
- **`board == replay(log)`** após cada ação (teste automático);
- funciona no **Safari e no Chrome do telemóvel** na LAN (teste manual teu);
- escuta em `127.0.0.1` por omissão; `--lan` documentado com o aviso de segurança.

## 8. Maquete estática em `docs/gui/` (a produzir noutro passo)

| Ficheiro | Mostra |
|---|---|
| `index.html` | Progresso: arte a 20 %, recortes, hachura, fantasmas, realce, barra, toggles funcionais, zoom/pan |
| `fetch.html` | Vai buscar com 4–6 cartões de exemplo; botões só demonstram o estado |
| `lotes.html` | Tabela de lotes e folha de exemplo |
| `mesa.html` | Dois grupos soltos de exemplo com top-3 |
| `celula.html` | Popup da célula (estado, arte, fantasma, molde, dupla) |
| `board.svg` | Tabuleiro gerado por `tools/gui_mock/make_mock.py` a partir de `projects/alpes/` (grelha 64 × 47, arte, células de exemplo) |
| `style.css`, `app.js` | Estilo e zoom/pan/toggles partilhados |

Dados reais onde existam (arte e grelha do `puzzle.json` [V]); o resto marcado "exemplo". Total ≤ 2 MB (miniaturas ≤ 48 px, arte reduzida). Abre-se com duplo clique, sem servidor.

## 9. Perguntas ao Tiago

1. **Web local aprovada?** Aceitas FastAPI + browser (porta 8765, só LAN, sem login)? Se não, avançamos com o fallback Tkinter mínimo.
2. **Telemóvel:** qual (Android/iPhone) e que browser? Importa para o layout estreito e para o teste Safari/Chrome.
3. **Rede:** PC e telemóvel na mesma Wi-Fi, e o firewall do Windows deixa abrir a porta 8765?
4. **Aspeto:** só modo escuro, ou queres também claro (útil à luz do dia junto ao tapete)?
5. **Fantasmas:** ligados por omissão ou só quando os ligas? E a confirmação dupla a 0,5 mm, concordas ou preferes mais estrito?
