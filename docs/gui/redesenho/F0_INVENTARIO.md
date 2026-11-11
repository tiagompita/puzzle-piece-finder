# F0 — Inventário da GUI atual → destino no redesenho

_2026-11-11. Feito por leitura de `src/web/index.html`, `app.js`, `holes.js`, `queue.js`, `activity.js`, `pose.js`, `editor.js`, `src/server.py` (`LEGEND`, `confirm`, `cell_json`, `fetch_json`, `alta_json`, `hole_action`, `_unplace`, `pose_*`), `src/state.py`, `src/confirm.py`, `src/query.py`, e dos testes `tests/test_gui_*`/`tests/test_server*.py`. Destinos já ajustados às respostas do Tiago de 2026-11-11 (ESPEC §8)._

Estado das afirmações: a tabela é o resultado da leitura do código **[V por leitura]**; nenhuma linha foi testada no browser nesta fase.

## 1. Elementos e textos → destino

Legenda:
- **Destino:** M = Montar; P = Peças; I = Importar scan; C = painel da Célula (peça no tabuleiro); V = Lugar vazio; G = Grupos soltos; E = Corrigir recorte; D = Diagnóstico (no «⋯»); R = removido.
- **F** = fase em que o elemento nasce no ecrã novo.

### 1.1 Barra de topo (`index.html` `#top`)

| # | Elemento / texto (origem) | Destino | F | Justificação |
|---|---|---|---|---|
| T1 | `<title>` e `#puzzle-name` «Mesa de montagem» (`drawProgress`) | Topo: nome do puzzle («Os Alpes») | 1b | ESPEC §3 |
| T2 | `#progress-txt` «N colocadas · X por confirmar (foto) · Y marcadas por ti · Z por colocar (de T)» | Topo: «N de 3008 peças», em que N = colocadas + lugares marcados cheios pelo Tiago; «cheia na foto, por confirmar» não conta (P12). A partir de F4, mais «K em grupos soltos». O detalhe foto/pista vai para D › Números | 1b | §3, §8.7 (P12) |
| T3 | Barra `#pb-placed`/`#pb-legacy` + `title` | A barra fica (P12), com o mesmo N de T2; a parte «foto» vai para D | 1b | §8.7 |
| T4 | Aba «Vai buscar»/«Buscar» + `#n-buscar` (+ classe `aviso`) | Aba **Montar** (contador = total na fila) | 1b | §2, §4.1 |
| T5 | Aba «Guardadas» + `#n-guardadas` | P, filtro «À espera» | 3 | §2, §4.7, P9/P13 |
| T6 | Aba «Lotes» | **Peças** | 3 | §2, §4.7 |
| T7 | Aba «Mesa» + `#n-mesa` | **Grupos soltos** (tabuleiro + lista) | 4 | §2, §4.9 |
| T8 | Aba «Importar» | **Importar scan** | 3 (na F1b, o formulário de hoje adaptado) | §3, §4.8 |
| T9 | Aba «Reports» + `#n-reports` | D › Problemas reportados + Peças suspeitas | 5 | §4.11 |
| T10 | Pesquisa `#search-btn`/`#q`, placeholder «P0778 · 4,10 · R0019 · S0020 · buracos» (`parseQuery`/`locateQuery`) | Lupa «procurar peça ou lugar»: aceita «7 20», «saco 7 nº 20», «4,57», «linha 4 coluna 57» e também P####. R####, S#### e «buracos» abrem D | 1b (peça/lugar), 5 (D) | §3 |
| T11 | `#job-pill` («fila: n · a importar saco 9 (folha 1/2)») | Chip discreto «a importar saco 9…» em Importar scan; detalhe em D › Atividade | 1b | Útil ao utilizador; texto simplificado |
| T12 | Interruptores «Fantasmas» e «Grelha» (`#tg-ghost`, `#tg-grid`, localStorage) | «⋯» › Definições (fantasmas desligados por omissão; grelha automática pelo zoom) | 1b | §3 |
| T13 | Interruptor «Sugestões» (`#tg-sug`, `drawSuggestions`) | R no Montar; substituído pelo «Lugar provável» tracejado dos grupos | 4 | §4.9 |
| T14 | Botões «Atividade» (`#tg-act`) e «≣» (`#z-act`) | D › Atividade do programa | 5 (na F1b, «⋯» › «Atividade» abre a gaveta de hoje) | §4.11 |

### 1.2 Tabuleiro (`#board-wrap`, `app.js`)

| # | Elemento | Destino | F | Justificação |
|---|---|---|---|---|
| B1 | Raster `#raster` + `#detail` (`drawBoard`, `loadDetail`) | Igual, código partilhado (`board.js`) | 1a | Reaproveitamento |
| B2 | Zoom «+», «−», «⤢» (`#z-in`, `#z-out`, `#z-fit`) | Ficam («⤢» com `aria-label` «Ver o tabuleiro inteiro») | 1b | Maquete Main |
| B3 | `#board-hint` «roda ou pinça: zoom · arrastar: mover · toque numa célula: abrir» | R no ecrã; gestos e atalhos listados em D | 1b | §4.1 |
| B4 | Camada `lyr-legado` (tracejado «ocupada sem silhueta») | Cinza muito ténue, sem entrada na legenda curta; legenda completa em D | 1b | §4.1 |
| B5 | `lyr-borda` («Borda em falta») | «⋯» › Camadas (desligada por omissão); legenda completa em D | 1b | Hoje é só (1,29) |
| B6 | `lyr-conhecida` («Posição conhecida») | «⋯» › Camadas; P, filtro «À espera» | 1b/3 | Não é a peça atual |
| B7 | `lyr-fantasma` (forma da gémea) | «⋯» › Definições › Fantasmas | 1b | Vocabulário técnico |
| B8 | `lyr-buscar` (células `b-buscar`, `b-buscar-ambigua`, `b-buscar-par`) | O alvo atual a âmbar com a etiqueta «vai aqui» (classe nova `b-alvo`); as 3 seguintes com contorno ténue | 1b | §4.1 |
| B9 | `lyr-sug` + `#sug-pick` «Sugestões em (l, c)» / «Abrir a célula (l, c)» | G: «Lugar provável» tracejado; tocar abre o painel do grupo | 4 | §4.9 |
| B10 | `lyr-mesa` (pré-visualização violeta) | G: o grupo desenhado na posição livre | 4 | §4.9 |
| B11 | `lyr-grelha` | Igual (automática pelo zoom) | 1a | — |
| B12 | `lyr-sel` («Selecionada») | Igual | 2 | — |
| B13 | `#hole-layer` (pré-visualização do encaixe com as vizinhas) | V: «ver como fica»; números em D | 2/5 | §4.5 |
| B14 | `#pose-layer` (editor de pose) | C › «Mais opções» › «Ajustar posição» | 5 | P8 |
| B15 | Gestos: roda (Ctrl+roda = zoom do browser, Alt+roda = rodar a pose), pinça, arrastar, duplo clique = zoom, toque = abrir célula | Iguais; o toque passa pelo gancho `S.onBoardTap` (F1a); no ecrã novo, uma peça abre C e um lugar vazio abre V | 1a/2 | §4.4–4.5 |
| B16 | Legenda `#legend-box` «Legenda» (14 linhas de `LEGEND` do servidor, `drawLegend`) | Legenda curta de 3 entradas («Onde vai a peça», «Grupo ainda sem ligação» a partir da F4, «Por montar»); a completa vai para D | 1b | §4.1 |
| B17 | `#sheet-handle` (folha deslizante no telemóvel) | Mantém-se o mecanismo | 1b | 390 px |

### 1.3 Aba «Vai buscar» (`renderBuscar`, `proposalCard`, `altaCard` em `holes.js`)

| # | Elemento / texto | Destino | F | Justificação |
|---|---|---|---|---|
| VB1 | Resumo «N peças para ir buscar em K saco(s): X aceites, Y com dúvida, Z pelo encaixe (alta). Pela ordem…» | M: contador «1 de 3 neste saco · 10 no total» | 1b | §4.1; «aceite» e «alta» proibidos |
| VB2 | `CARD_KEY` «Em cada peça: ▲ = topo…» | R (a imagem já vem rodada; o ▲ fica como marca sem texto) | 1b | §6 |
| VB3 | Cabeçalho «Coloca agora (N) · têm uma vizinha montada…» | R (implícito na fila) | 1b | §4.1 |
| VB4 | `lot-head` «Saco K · n peças» | M: contador por saco + lista «A seguir» | 1b | §4.1, §8.2 |
| VB5 | Vazio «Nada a ir buscar agora. Importa o scan…» + «Importar scan» | M: «Nada para ir buscar. Digitaliza mais um saco.» + botão «Importar scan» | 1b | §4.1 |
| VB6 | `altaBanner` «buracos: a calcular tiras n/N (s)» | M, estado a preparar: «A preparar sugestões… n de N» | 1b | §4.1 |
| VB7 | `altaBanner` «pelo encaixe · alta · acertos/falhas/total · precisão · IC 95 % · últimas 20» | D › Rejeições e acertos | 5 (na F1b, um painel provisório de números) | §4.11 |
| VB8 | Pausa «≥ 3 rejeições nas últimas 20…» + «Reativar sugestões alta» | M: uma linha «Algumas sugestões estão em pausa» com ligação para D; o botão «Reativar» fica em D | 1b/5 | Afeta a fila; números só em D |
| VB9 | `holesEntry` «Buracos: média, baixa e sem fiável N» | V («O programa acha que pode ser») + D › Números (página Buracos) | 2/5 | §4.5, §4.11 |
| VB10 | `details` «N sugestões não mostradas (candidata única, por política)» | D | 5 | Maquete Diagnóstico |
| VB11 | Imagem `pieceImage` + «rodada como fica (▲ = topo)» / «como foi digitalizada (rotação desconhecida)» | M: imagem rodada; tocar amplia-a e mostra a folha (P7); «rotação por confirmar» só quando é desconhecida | 1b | §4.1, §8.7 |
| VB12 | «Saco N · nº X» (`.who`) | M, em grande | 1b | §4.1 |
| VB13 | «→ célula (l, c)» + `tag` (aceite / ambígua / colocável / candidata / par proposto / confirmado / sem lugar) | M: «Linha l · coluna c» + «quase certo» / «a confirmar por ti» com 3 traços (regra §8.3) | 1b | §2, §8.3 |
| VB14 | Chips «gémea», «pelo encaixe · alta», «encaixe ok (n viz.)», «encaixe incompatível», «conflito: gémea diz (l,c)» | D › Números da sugestão; o efeito (incompatível passa a «a confirmar por ti») vai para as palavras | 1b/5 | §2 |
| VB15 | Linha `small muted` «origem P#### em (l,c) · P#### · rodar θ°» | D | 1b/5 | §2 |
| VB16 | `ul.reasons` (`plain_reasons`: «forma: diferença x mm (limite y)», «margem…», «imagem: ΔE…») | M › «Porquê esta peça?» (3 frases com traços, «não verificado» com traços vazios, §8.4) + D (números) | 1b | §4.3, §8.4 |
| VB17 | Mini-mapa `miniMap` + «linha · coluna» | R (o tabuleiro desloca-se até ao alvo) | 1b | §4.1 |
| VB18 | Miniatura da folha «folha S####: nº X a âmbar (toca para ampliar)» + lightbox | M: só ao tocar na imagem da peça (P7); C «Na folha que digitalizaste»; painel da peça em P | 1b/2/3 | §8.7 |
| VB19 | Botão «Coloquei» (`act place` / `holeAct confirmar` / fundido `gemea:true`) | M «**Encaixa**» (o servidor diz que pedido fazer) | 1b | §2, §6 |
| VB20 | «Não encaixa» (`reject` / `holes/rejeitar`) | M «**Não encaixa**» → ecrã §4.2 (motivo opcional, desfazer) | 1b | §4.2, §8.1 |
| VB21 | «Guardar posição» (`position_known`) | Painel da peça em P («Guardar à parte com o lugar») | 3 | P9 |
| VB22 | «Guardei num saquinho (l, c)» (cartões `guarda_posicao`) | P, filtro «À espera», painel da peça | 3 | P9 |
| VB23 | «⚠ Reportar» / «✎ Editar report» | C «Algo está errado»; a edição fica em D | 2/5 | §4.4 |
| VB24 | «Ver no tabuleiro» | R (automático) | 1b | §4.1 |
| VB25 | `details.tech` «razões técnicas» | D | 5 | §4.11 |
| VB26 | `altaCard` mini-SVG «no buraco, com as vizinhas (ciano)» + «Pré-visualizar encaixe» | M mostra a mesma imagem rodada; a pré-visualização vai para V e D | 2/5 | §6 |
| VB27 | Toast `warnPlaceable` «Peça P (saquinho (l,c)) já tem vizinha montada: vai buscar o saquinho» | M: «Saco N · nº X (guardada à parte) já pode ir para o lugar» | 1b | Mesmo aviso em palavras |

### 1.4 Aba «Guardadas» (`renderGuardadas`)

| # | Elemento | Destino | F |
|---|---|---|---|
| GU1 | Aviso «Não procurar ainda: estas peças têm posição provável mas nenhuma vizinha…» | P, filtro «À espera» (moldura + uma frase curta no filtro) | 3 |
| GU2 | `details.guardadas` «Guardadas com posição, ainda sem vizinha (N)» + cartões | P, grelha do saco (moldura «À espera») + painel da peça | 3 |
| GU3 | Vazio «Nenhuma peça guardada à espera de vizinha.» | P: estado vazio do filtro | 3 |

### 1.5 Aba «Lotes» (`renderLotes`)

| # | Elemento | Destino | F |
|---|---|---|---|
| L1 | «Cada saco tem as suas folhas (scans)…» | R | 3 |
| L2 | `st-key` (solta, em par, posição conhecida, colocada, em grupo, descartada) | Filtros de P com legenda nas molduras: Todas, Para ir buscar, Em grupos soltos, Já no tabuleiro, À espera (= soltas sem sugestão + guardadas à parte + pares). Descartadas só em «Todas», com marca própria (P13) | 3 |
| L3 | `details.lot` «Saco N / Sem saco (legado e GT)» + contagens por estado | P: bloco por saco «32 peças · 3 para ir buscar»; «Sem saco» passa a «Peças antigas (sem saco)» | 3 |
| L4 | Folhas (`figure` «S#### · n peças», lightbox) | P: «Folhas (2)» no cabeçalho do bloco | 3 |
| L5 | `pgrid`/`ptile` (nº + célula ou estado, `title` P#### · estado) | P: grelha com nº e moldura por estado; tocar abre o painel da peça | 3 |

### 1.6 Aba «Mesa» (`renderMesa`, `mesaRow`)

| # | Elemento | Destino | F |
|---|---|---|---|
| ME1 | Pesquisa `#mesa-q` «Grupo, peça ou célula: G0021, P0294, 3,32» | G, lista: filtro por saco/nº e lugar; G#### em D | 4 |
| ME2 | Filtros «Seguras (n)» / «A confirmar (n)» | G: «quase certo» / «a confirmar por ti» (regra §8.3) | 4 |
| ME3 | `#mesa-info` «N grupos sem lugar. «Ver» mostra…» | R | 4 |
| ME4 | Linha: miniatura, «G0071 · 4 peças», «melhor zona (l,c)», selo, «Ver»/«Fechar» | G: «Grupo de 4 peças · sacos 3, 7» + «Levar para o lugar provável» | 4 |
| ME5 | «Zona k) (l,c) rot θ espelho · margem m» | D | 4/5 |
| ME6 | Avisos «parte fica fora da grelha», «n célula(s) já colocadas», «O programa não decidiu este grupo…» | G: o grupo não sai do tabuleiro nem se sobrepõe; aviso em palavras («ainda a confirmar por ti») | 4 |
| ME7 | «É aqui em (l,c)» + `confirm()` | G «**Fixar aqui**» (`anchor`); num grupo «a confirmar por ti», confirmação de um clique (P6) | 4 |
| ME8 | «ou (l,c) rot θ · Ver» (outras zonas) | G: «Lugar provável» seguinte | 4 |
| ME9 | «ⓘ notas da ingestão» | D | 5 |
| ME10 | Vazio «A mesa está vazia. Não há grupos soltos sem lugar.» | G: «Não há grupos soltos.» | 4 |

### 1.7 Página «Buracos» (`holes.js`: `renderHolesTab`, `holeRow`, `holeCard`, `holeActions`)

| # | Elemento | Destino | F |
|---|---|---|---|
| H1 | «← voltar», «Buracos: candidatas por confiança», resumo, ajuda, filtro, grupos (alta · em pausa, alta · em «Vai buscar», conflito, média, baixa (1 vizinha), sem fiável) | D › Números das sugestões › Buracos | 5 |
| H2 | Cartões com #rank, custo, margem, rodar θ, chips, «atribuída», «é a melhor para», linhas por lado (forma mm, ΔE, \|ΔL\|, penalização) | D | 5 |
| H3 | Ações «Coloquei», «Não encaixa», «Ver no tabuleiro», «Pré-visualizar encaixe», «Reportar», «Abrir célula» | V: 1.ª candidata com «Encaixa»/«Não encaixa»; o resto em D | 2/5 |
| H4 | `holesBlock` «Candidatas para este buraco» na gaveta | V «O programa acha que pode ser» + «ver outras» em D | 2 |

### 1.8 Gaveta da célula (`renderCell`) e da peça solta (`openPiece`)

| # | Elemento | Destino | F |
|---|---|---|---|
| C1 | «← voltar» | «Voltar à fila» | 2 |
| C2 | «Célula (l, c)» | «Linha l · coluna c» (+ «na borda de cima») | 2 |
| C3 | «Localizar peça» (`locateIcon`) | R (tocar já centra) | 2 (teste muda na F6) |
| C4 | `zoomFigure` «o teu tabuleiro (300 dpi)» / «a arte da caixa» | V mostra a arte (P10); o resto em D | 2/5 |
| C5 | `kv` estado («ocupada (sem silhueta)», «cheia na foto, por confirmar», «· borda», «· fonte X») | C: «No lugar · posta por ti a 9 nov» (precisa da data, `posta_em`); fonte em D | 2 |
| C6 | `kv` gémea (ligação à célula e estado) | D | 5 |
| C7 | `kv` peça «saco · nº · P#### · estado», «como chegou», «fantasma» | Saco/nº em grande + P#### pequeno; o resto em D | 2 |
| C8 | «Está montada» (`cell_full`) | V «**Já tem peça, mas não a digitalizei**» | 2 |
| C9 | «Está vazia» (`cell_empty` em `ocupada_legado`) | Painel do lugar ocupado sem peça: «Afinal está vazio», visível quando o lugar foi marcado pelo Tiago (P8) | 2 |
| C10 | `reportButton` / `reportInline` | C «**Algo está errado**» (diálogo simplificado); um report aberto aparece como «já reportaste: …»; edição completa em D | 2 |
| C11 | «✎ Editar contorno» + selo «contorno manual» | C «**Corrigir recorte**» → E; selo em D | 2 (porta) / 5 (E) |
| C12 | «⤧ Editar posicionamento» + selo «pose manual θ dx dy» | C › «Mais opções» › «Ajustar posição» (pose.js reaproveitado, P8); selo em D | 5 |
| C13 | Cartão «como está no tabuleiro», «classe X · n lado(s) liso(s)», «ver na folha do scan» | C: «Na folha que digitalizaste» (miniatura com a peça marcada, toca para ampliar); classe em D | 2 |
| C14 | «Desfazer colocação» (com `confirm()`) | C «**Tirar do lugar**» sem confirmação, com «Desfazer»; neutro para os contadores (P7b) | 2 |
| C15 | «Desfazer «É aqui» do grupo G####» | C de uma peça de grupo fixado: o botão diz «Tirar o grupo inteiro do lugar (N peças)» (`unanchor`, P6) | 2/4 |
| C16 | «Proposta(s) para esta célula» + `CARD_KEY` + cartões | V «O programa acha que pode ser: Saco N · nº X · a confirmar por ti / quase certo» + «Encaixa» | 2 |
| C17 | «Posição conhecida: … guardada à parte, à espera de uma vizinha» | V: «Guardada à parte: Saco N · nº X» | 2 |
| C18 | Nota «Ainda nenhuma pista para esta célula…» | V: «Sem sugestão por agora.» | 2 |
| C19 | «Vizinhas» N/E/S/O com ligações | R (o tabuleiro mostra-as); D | 2 |
| C20 | Peça solta: cabeçalho, «rodada como ficará / como foi digitalizada», «P#### · estado», «classe · lados lisos · grupo», «ver na folha do scan» | P › painel da peça (Saco/nº, folha, estado em palavras); o resto em D | 3 |
| C21 | Peça solta: «Sem proposta para esta peça por agora…» | P › painel: «À espera: ainda sem lugar» | 3 |
| C22 | Peça solta: «Descartar (não é peça / repetida)» + `confirm()` | P › painel › «Mais opções» › «Não é uma peça / está repetida» (P9) | 3 |

### 1.9 Pesquisa (mensagens de `locate*`)

| # | Texto | Destino | F |
|---|---|---|---|
| S1 | «P####: não encontrado (não existe)», «… está em Vai buscar / Guardadas», «… existe: estado (saco, nº), sem proposta», «célula (l,c) vazia / sem peça: estado», «(l,c): não encontrado (fora da grelha 47×64)», «Escreve uma peça (P0778)…», ««x»: não encontrado (usa …)» | Lupa: as mesmas respostas em palavras novas («Saco 7 · nº 20 está na fila», «Linha 4 · coluna 57 está vazia», «Não encontrei «x». Escreve o saco e o nº, ou a linha e a coluna») | 1b |

### 1.10 Aba «Importar» (`renderImportar`, `queue.js`)

| # | Elemento | Destino | F |
|---|---|---|---|
| I1 | «Importar scans» + resumo «Um saco pode ter várias folhas…» | I: «Junta um saco novo» + 3 passos numerados | 3 |
| I2 | Ficheiros «Scans do saco (JPEG/PNG/TIFF ou PDF…)» | Passo 1 «A folha digitalizada»: largar aqui ou clicar | 3 |
| I3 | «Número do saco (lote)» (`nextFreeLote`) | Passo 2 «Número do saco onde as guardas», − / + e «o seguinte ao último» | 3 |
| I4 | «Resolução (dpi, opcional…)» | I › «Mais opções» | 3 |
| I5 | «Pôr na fila» | Passo 3 «Importar» | 3 |
| I6 | `#joblog` + «abrir «Vai buscar»» · «ver o saco N» | I: «Encontrei N peças; K podes ir já buscar» + «Ir montar» / «Ver o saco» | 3 |
| I7 | `#import-queue` «Fila de importação» + «ver a fila inteira» + linhas (▲, ▼, Cancelar, Repetir, estados) | I: linha compacta por trabalho com Cancelar/Repetir; a fila inteira vai para D › Atividade | 3/5 |
| I8 | Nota «Os ficheiros ficam em images/pieces/lotes/… junta-os ao git…» | D › Manutenção | 5 |
| I9 | Regras de captura (hoje não existem) | I: 3 desenhos simples (fundo verde, peças afastadas, 300 dpi) (P11) | 3 |

### 1.11 Aba «Reports» (`renderReports`, `renderSuspeitas`, diálogos)

| # | Elemento | Destino | F |
|---|---|---|---|
| RP1 | «Suspeitas (N)», extra «+ n em reports · n falsos alarmes (obsoletos)», texto, filtro, linhas com chips de grau, «Falso alarme», «Falsos alarmes (N)», «Restaurar», `#estado-dlg` do falso alarme | D › Peças suspeitas | 5 |
| RP2 | Contagem, filtros Abertos/Resolvidos/Eliminados, linhas expandíveis (miniaturas «no tabuleiro»/«no scan», captura, texto, nota, Histórico, «Ver no tabuleiro», «Editar», «Marcar resolvido», «Eliminar», «Reabrir», «Restaurar»), `#estado-dlg` | D › Problemas reportados | 5 |
| RP3 | `#report-dlg` «Reportar um problema», tipos (mal lida / mal recortada, mal colocada, não encaixa, outro), «O que viste (opcional)», «Enviar»/«Guardar edição»/«Cancelar» | C «Algo está errado»: diálogo com os tipos em palavras simples («O recorte está mal», «Está no lugar errado», «Não encaixa», «Outra coisa»); os tipos internos mantêm-se | 2 |

### 1.12 Rejeições (novo)

| # | Elemento | Destino | F |
|---|---|---|---|
| RJ1 | (não existe hoje) Lista das rejeições (`twin_rejected`, `hole_rejected`, `pair_rejected`) com o motivo, quando houver | D › Rejeições e acertos, cada uma com «anular» (alteração 3 de 2026-11-11) | 5 |

### 1.13 Elementos globais

| # | Elemento | Destino | F |
|---|---|---|---|
| X1 | `#prep` «A preparar o projeto» + `#prep-log` | M, estado a preparar («A preparar o programa… isto só acontece depois de atualizar»); o registo vai para D | 1b |
| X2 | `#lightbox` «Fechar» | Igual | 1b |
| X3 | `#toast` com as `mensagens` do servidor («P0123 colocada em (4, 57) (origem gemeo, pose …)») | No ecrã novo **não** se mostram: têm «(l, c)», «origem» e P####, o que viola o §6. Toasts próprios («Saco 7 · nº 20 no lugar · Desfazer»); as mensagens vão para D › Atividade | 1b |
| X4 | Toast «INVARIANTES: …» | «Algo correu mal ao gravar (ver Diagnóstico)», com a lista em D | 1b |
| X5 | Menu de contexto das miniaturas «Copiar imagem (PNG)» / «Guardar PNG» (`initPngMenu`) | Fica em todas as imagens de peça (só com o botão direito) | 2 |
| X6 | Gaveta `#atividade`: abas «Atividade» / «Fila de importação», contagem, filtros por tipo e nível, «ficheiro: …», «limpar vista», «Fechar» | D › Atividade do programa | 5 (na F1b, acessível pelo «⋯») |
| X7 | Teclado: Esc (fecha lightbox, menu, picker; volta da célula), atalhos do editor e da pose | Mantém-se; novos no Montar (Enter, N, S, Ctrl+Z), listados em D | 1b |
| X8 | `confirm()` nativos («Retirar P de (l,c)?», «Descartar P…?», «Desfazer o É aqui…?», «É aqui: G…?») | Substituídos por desfazer. Exceção: «Fixar aqui» num grupo «a confirmar por ti» mantém uma confirmação de um clique (P6) | 2/4 |

### 1.14 Editor de contorno (`editor.js`, `#ced`) → E

| # | Elemento | Destino | F |
|---|---|---|---|
| ED1 | Ferramentas «Laço», «Pincel», «Borracha» (teclas) | Pincéis «**Tirar**» (sombra, fundo) e «**Acrescentar**» (peça cortada); laço e borracha em «Mais opções» | 5 |
| ED2 | Marcas «É peça», «Não é peça», «Incerto» | Acrescentar = `peca`; Tirar = `fundo`; Incerto em «Mais opções» (o motor A2 não muda) | 5 |
| ED3 | «Raio» | «Tamanho do pincel» | 5 |
| ED4 | «Desfazer», «Refazer», «Limpar traços» (`confirm`) | «Desfazer», «Recomeçar»; Refazer em «Mais opções» e com Ctrl+Y | 5 |
| ED5 | «Afastar», «Aproximar», «Ajustar» | «+», «−» (ajustar com duplo clique) | 5 |
| ED6 | Vistas «Scan», «Atual», «Diferença», «Final», «Lado a lado» | «**Como fica**» (Final); as outras em «Mais opções» › Vistas | 5 |
| ED7 | «Afinar vértices» | «Mais opções» | 5 |
| ED8 | `CED_AJUDA` (texto longo) e `CED_LEGENDA` | «Pinta por cima do que está errado» + «Só a peça, sem sombra»; o texto longo fica em «Mais opções» | 5 |
| ED9 | «Nota (opcional)» | «Mais opções» | 5 |
| ED10 | «Gravar», «Cancelar», «Descartar as alterações ao contorno?» | «Guardar», «Cancelar», a mesma pergunta | 5 |
| ED11 | Banner da gémea «Contorno sugerido pela gémea G (RMS x mm)», «Usar como ponto de partida», «Ignorar», «Voltar ao automático», «não utilizável: motivo» | «**Usar o recorte da peça gémea**» (recolhido); o RMS vai para D | 5 |
| ED12 | Chips «contorno manual», «contorno da segmentação», «por aplicar»; linha «P#### · S#### · (l,c) · classe» | D; cabeçalho «Corrigir recorte · Saco N · peça nº X» | 5 |
| ED13 | Toasts («sem contorno resolvido para afinar», «um contorno precisa de ≥ 3 vértices», …) | Iguais, em palavras simples | 5 |

### 1.15 Editor de pose (`pose.js`)

| # | Elemento | Destino | F |
|---|---|---|---|
| PO1 | Painel «Editar posicionamento · P em (l,c)», campos θ/dx/dy, «Pose automática», «Alinhar a 90°», juntas N/E/S/O «+x mm folga / sobrepõe», consistência, «face à automática: Δθ…», «nota (opcional)», «Gravar», «Repor automática», «Cancelar», ajuda de teclado, `confirm()` | C › «Mais opções» › «Ajustar posição», o mesmo painel; os números ficam, por ser uma ferramenta de afinação (P8) | 5 |

### 1.16 O que o servidor dá à GUI (`src/server.py`, `src/confirm.py`)

| # | Elemento | Destino | F |
|---|---|---|---|
| SV1 | `LEGEND` (14 linhas, rótulos «Vai buscar», «Vai buscar (ambígua)», «Par de soltas», «Sugestão segura», «Grupo da mesa»…) | Fica para D/legenda completa; linhas novas só da GUI nova (`alvo`, `grupo_solto`) marcadas para a legenda curta e filtradas de `/api/board` | 1b |
| SV2 | `ESTADO_TXT`, `CELL_TXT`, `CELL_SOURCE_TXT`, `ORIGIN_TXT`, `plain_reasons` | D; o ecrã novo usa textos próprios gerados em `src/montar.py` | 1b |
| SV3 | `AQUI_TXT = "É aqui"` (`src/confirm.py`) | «Fixar aqui» só na F6 (o teste `test_no_ancorar…` fixa «É aqui») | 6 |

## 2. Testes que dependem de textos, seletores ou estrutura que mudam

Regra: nas fases 1–5 a GUI antiga continua em `/` e **nenhum teste da GUI antiga muda de asserções**. Só mudam os testes que leem *ficheiros* que vão ser partidos (F1a) e, na F6, os testes da GUI antiga (reescritos para a nova ou apagados; cada um na mensagem do commit).

| Teste | O que verifica hoje | O que muda | Fase |
|---|---|---|---|
| `test_server.py::test_legend_covers_every_board_class` | As classes `b-*` de `app.css`/`app.js`/`index.html` têm linha em `LEGEND`; cada linha tem estilo em `app.css`; os `cls("id")` de `app.js` existem | A lista de ficheiros varridos passa a incluir `core.js`/`board.js`/`board.css` (o CSS e o JS do tabuleiro mudam de ficheiro) | 1a |
| `test_gui_mesa_b.py::test_no_ancorar_in_web_sources_or_server_texts` | Nenhum «ancor» em `app.js`/`index.html`/`app.css`; `AQUI_TXT == "É aqui"` | 1a: a varrida passa a incluir os ficheiros novos (asserções iguais). F6: `AQUI_TXT == "Fixar aqui"` | 1a, 6 |
| `test_gui_static.py` (3) | «Localizar peça»/`locateIcon` em `app.js`; `class: "btn slim report"` e «⚠ Reportar»; CSS da legenda com setas | Apagados ou reescritos para a GUI nova | 6 |
| `test_gui_layout.py` (`test_layout`, `test_tabs_in_top_bar`, `test_top_bar_no_overlap…`, `test_search_in_top_bar`) | 6 abas `["buscar","guardadas","lotes","mesa","importar","reports"]`, `#tab-*`, `#legend-box`, 1 cartão visível, Ctrl+roda, pílula do trabalho, pesquisa | Reescritos sobre a GUI nova (3 abas, «⋯», legenda curta, cartão do Montar) | 6 |
| `test_gui_flows.py` (2) | Grupos de «Vai buscar», `#tab-guardadas`, «Coloquei», «Reportar», «Está montada» | Montar → Encaixa; V «Já tem peça, mas não a digitalizei» | 6 |
| `test_gui_guardadas.py` (2) | `#tab-buscar` vazio, `#tab-guardadas details.guardadas` fechado | P filtro «À espera»; a regra «sem vizinha ortogonal» testada em `/api/montar` | 6 |
| `test_gui_mesa.py`, `test_gui_mesa_b.py` (8) | `#mesa-q`, `.mrow`, «G0044 · 2 peças», filtros, «É aqui», `#tg-sug`, `#sug-pick`, localStorage | Reescritos para G; os de `#tg-sug` apagados | 6 |
| `test_gui_search.py` (7, parametrizados) | Pesquisa P/R/S/célula, `#tab-lotes .lot-hit`, `#tab-guardadas .card.sel`, `#toast` | A lupa nova | 6 |
| `test_gui_reports.py` (5) | `#tab-reports`, `.report-row`, estados, report em linha, «✎ Editar report» | D › Problemas reportados e C «Algo está errado» | 5/6 |
| `test_gui_suspeitas.py` (3) | `#tab-reports details.suspeitas`, `.suspeita-row`, «Falso alarme», `.falsos` | D › Peças suspeitas | 5/6 |
| `test_gui_holes.py` (2) | `.holes-block`, `.hole-card`, `#hole-layer`, pesquisa «buracos», `#tab-buracos` | V + D › Buracos | 6 |
| `test_gui_buscar_buracos.py` (2) | `.card.hole-sug` em `#tab-buscar`, `.alta-count`, página de buracos, pausa/reativar | M (entrada `buraco` na fila) + D (contador, reativar) | 6 |
| `test_gui_png.py` (3) | `#ctx-menu` sobre `.pimg`, `img.rthumb`, `.rthumbs img` | Seletores das imagens novas | 6 |
| `test_gui_pose.py` (2) | `[data-pose-btn]`, `#pose-panel`, `#pose-layer` | Entrada por C › Mais opções | 5/6 |
| `test_gui_contorno.py` (4) | `#ced`, ids `ced-*`, `[data-contorno]`, traços, convenção, sugestão da gémea, layout | Os ids que o redesenho do editor mudar; a lógica fica | 5 |
| `test_gui_atividade.py` | `#tg-act`, `#atividade`, `#act-filters`, `.act-line` | D › Atividade | 5/6 |
| `test_gui_fila.py` | `#import-form`, `#joblog`, `#fila-pane`, `[data-job]` | I + D | 3/6 |
| `test_server.py::test_legend_row_legado_says_unconfirmed` | Texto da linha `legado` | Só se a F6 reescrever os rótulos | 6 (talvez) |
| `test_server.py::test_confirm_*`, `test_server_alta.py`, `test_server_holes.py` | Contrato de `/api/confirm` e `/api/holes/*` | **Não mudam** (campos novos aditivos) | — |
| `test_server_idle.py`, `test_server_queue.py` | SSE e fila | Não mudam | — |

## 3. Os 5 pontos do ESPEC §5: o que o servidor já faz e o que falta

| # | Já existe | Falta |
|---|---|---|
| 1. Desfazer uma rejeição | `twin_rejected`/`hole_rejected` acrescentam `(piece, cell, origin)` a `Model.rejections` (`state.apply`). Usam esse conjunto `query._rejected` e `fit._rejected_for`. `pair_rejected` muda o par para `rejeitado` e as peças para `solta`. `confirm(reject=True)` escreve 1 evento por entrada (gémea, borda ou par); o cartão fundido escreve `hole_rejected` + `twin_rejected`. **Nenhum evento anula uma rejeição.** | Ação nova `rejection_undone` {piece, cell, origin, ref_t} em `state.ACTIONS` + `apply` (retira de `rejections`) + `Project.undo_rejection`. `pair_unrejected` (par volta a `proposto`, peças a `emparelhada`). `confirm(undo_reject=…)` com reconsulta incremental; `/api/confirm` `acao: "undo_reject"`. `fit.alta_counter`/`report` ignoram decisões anuladas (§8.1: uma ação desfeita não conta). Custo conhecido: uma ação nova no log faz com que checkouts antigos deixem de o ler. |
| 2. Motivo da rejeição | Não existe. `_hole_meta` só aceita `HOLE_META` (inclui `nota`, texto livre). | Evento informativo `rejection_noted` {piece, cell, origin, motivo ∈ forma \| imagem \| nao_sei, ref_t} (decisão P1) + `acao: "reject_reason"`; contagem por motivo em `python -m src.fit --relatorio`. |
| 3. Posição livre de um grupo solto | `Section.anchor` só guarda o «Fixar aqui» real; `sections_json` dá `candidatos` (cell0, rot, mirror, footprint, margem). Não há posição livre. | Evento de estado `section_moved` {section, l0, c0, rot, mirror} → `Section.mesa`; `sections_json` devolve `mesa` (ou uma posição inicial proposta) e o seu `footprint`. Validação no servidor: dentro da grelha, sem colocadas por baixo, sem outro grupo. Não toca no `Board`. |
| 4. Verificações de uma peça escolhida à mão | `query._fit_check(ctx, pid, cell, theta)` (forma + tira de imagem por lado contra as vizinhas montadas, regra F, `t_abs`; privado, precisa de `_Ctx`); `fit.theta_for`, `board_dirs`; `POST /api/pieces/{pid}/pose/avaliar` (só peças colocadas); `locate.de_cell`. `POST /api/confirm` `place` **ignora** `theta_deg` do corpo, e `confirm()` recusa θ quando a lista já tem pose para a célula. | `POST /api/cell/{l}/{c}/verificar {piece, rot?}` (não bloqueante para a GUI: «a verificar…», «Pôr na mesma») → 4 rotações com {theta_deg, borda, forma, imagem ∈ ok \| falha \| nao_testado, frases}, a partir de `_fit_check` promovido a função pública (sem mudar a lógica). `place` aceita `theta_deg` do corpo e o θ do Tiago manda (P10b). `piece.png?theta=`. `bbox` das peças na folha para «Escolher na folha». |
| 5. Ordenação da fila por saco | O cliente agrupa por `lote` crescente e ordena por `ordem` (a ordem dos passos da consulta), com os `buraco` depois das gémeas. O servidor não ordena por saco. | `src/montar.py` (puro) `fila(...)` + `GET /api/montar`: filtra `coloca_agora` e estados pendentes, junta as `alta` (fundidas = 1 item), começa pelo saco do último scan importado (sem importação recente, o saco com mais «quase certo»), saco fixo até esgotar; dentro do saco, por confiança e depois `ordem`; «Saltar» = fim do saco, 2.ª vez = fim de tudo, só na sessão (§8.2). |

Extra, fora do §5 mas necessário:
- `posta_em` (data do `placed`) em `cell_json`, para «posta por ti a 9 nov».
- Na F2/F5, a regra P7b («Tirar do lugar» passa a falha se outra peça acabar nesse lugar) precisa de cruzar `unplaced` com o `placed` seguinte na mesma célula, no contador.
