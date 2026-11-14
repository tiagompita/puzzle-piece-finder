# Tabuleiro: o detalhe demora depois de um salto (lupa / «localizar» / «Ver no tabuleiro»)

2026-11-14. Plano aprovado: `C:\Users\tiago\.claude\plans\agente-implementer-skills-systematic-deb-witty-pelican.md`
(condições do Tiago no topo). Medido numa **cópia** de `projects/alpes` no scratchpad (698 peças colocadas), Chromium
headless (Playwright) com CDP `Network`, Windows 11, `.venv` (Python 3.13). Dados em bruto: `dados/*.json`.
Guiões: `tools/diagnostico/gui/salto_detalhe.py` (browser), `tempo_regiao.py` (servidor: fases e bloqueio),
`gil_buracos.py` (GIL), `tabela.py` (tabelas a partir dos JSON).

Etiquetas: **[V]** medido aqui; **[NT]** não testado; **[F]** testado e falha o critério.

## 0. Resumo

- **O problema é anterior à F1 [V].** Worktree em `8fedf87^` (`d9c8165`, só a GUI antiga), mesma cópia do projeto:
  salto frio céu 2,11 s / relva 1,88 s / 5 saltos 4,79 s, contra 2,14 / 1,95 / 4,80 s na GUI antiga de HEAD
  (`dados/pref1_antiga_1920.json`, `antes_antiga_1920.json`). A GUI nova pede uma região maior (lupa l±5 c±8:
  14 × 21 células a ppc 100 = 2,8 MP, contra 11 × 15 a ppc 140 na antiga), por isso demora ≈ 0,5 s a mais.
- **O fio principal do browser nunca bloqueou [V]:** 0 long tasks e batimento `requestAnimationFrame` ≤ 17 ms em
  todos os cenários, antes e depois. O que «não responde» é o servidor de imagens.
- **Hipótese (a) confirmada [V]:** com o `rlock`, um `board.jpg` **já em cache** esperou 1,78–1,81 s (uma composição
  inteira) enquanto outra região se compunha. As outras rotas (`/api/status`, `/api/montar`, `/api/cell`) não usam o
  lock e responderam em ≤ 77 ms.
- **Hipótese (b) confirmada em parte [V]:** sem cancelamento, 5 saltos seguidos mandam 5 pedidos que o servidor compõe
  todos, em série (pico 4–5 em voo; o último detalhe chega aos 7,6–9,1 s). A fila de ligações apareceu (sondas em
  `queued`/`stalled` até 113–490 ms em 3 das 5 corridas de 5 saltos), mas com 6 ligações e 5 pedidos não chegou a
  bloquear a GUI durante segundos.
- **Achado fora das hipóteses [V]: o ranking dos buracos a frio rouba o GIL.** Logo depois de abrir `/novo/`, o
  1.º `/api/montar` arranca o ranking (≈ 30–40 s num fio). Durante esse tempo um detalhe que sozinho demora 2,3–2,9 s
  demora **26–34 s** (efeito «comboio» do GIL: cada chamada OpenCV/numpy que liberta o GIL espera até 5 ms para o
  voltar a ter). É o cenário mais provável do relato do Tiago (primeira lupa depois de abrir). A + B não o resolvem.
- **Implementado: só A e B** (§3). Depois deles: o `board.jpg` em cache responde em 1 ms (máx. 21 ms) durante uma
  composição; 5 saltos seguidos deixam 1 composição útil (os pedidos obsoletos são abortados no browser e descartados
  no servidor antes de compor) e o detalhe final chega em 3,3–3,9 s em vez de 4,8–8,2 s. **O tempo frio de um salto
  não muda** (2,2–2,8 s em céu/relva): o critério 1 continua **[F]**.

## 1. Servidor, sem browser: onde vai o tempo de uma composição [V]

`tempo_regiao.py --project <cópia>` (`dados/fases_servidor.json`); região = vista + 1 célula de margem, como o cliente
a pede. Fases por monkeypatch de `src.render` (soma do tempo dentro de cada função):

| zona | zoom | células | MP | KB | frio (s) | morno, +1 col. (s) | quente (s) | fases do frio (s) |
|---|---|---|---|---|---|---|---|---|
| céu (5,30) | lupa, ppc 120 | 209 | 2,91 | 432 | 2,61 | 2,06 | 0,000 | sombra 0,75 · resto 0,43 · ler recorte 0,38 · registar 0,38 · bleed 0,33 · warp 0,16 · profundidade 0,15 · arte 0,03 · JPEG 0,005 |
| céu | perto, ppc 240 | 63 | 3,51 | 686 | 1,39 | 1,35 | 0,000 | resto 0,49 · sombra 0,35 · bleed 0,18 · ler 0,16 · warp 0,08 · prof. 0,08 |
| relva (44,40) | lupa, ppc 120 | 190 | 2,65 | 622 | 2,30 | 1,91 | 0,000 | sombra 0,71 · registar 0,44 · resto 0,37 · bleed 0,28 · ler 0,19 · prof. 0,14 · warp 0,14 |
| relva | perto, ppc 240 | 63 | 3,51 | 997 | 1,22 | 1,20 | 0,000 | resto 0,43 · sombra 0,35 · bleed 0,14 · ler 0,10 |
| vazia (33,30) | lupa, ppc 120 | 247 | 3,44 | 197 | 0,085 | 0,084 | 0,000 | arte 0,03 · resto 0,05 |
| vazia | perto, ppc 240 | 63 | 3,51 | 106 | 0,085 | 0,090 | 0,000 | arte 0,03 · resto 0,05 |

- O custo é **por peça, não por píxel**: 3,4 MP vazios custam 0,085 s, 2,9 MP no céu custam 2,6 s.
- «sombra» (`_display_masks` + `_fill_transparent`, a regra de visualização da orla de sombra) é a maior fase:
  29–31 % do frio. «registar» só pesa na 1.ª vez (registo de cantos sem cache: 0,38–0,44 → 0,04 s no morno).
- «morno» (vista deslocada 1 coluna) **é um frio**: a cache é por região exata, nada se reaproveita.
- O JPEG (0,005 s) e a arte (0,03 s) não pesam.

**Bloqueio no servidor** (`tempo_regiao.py --bloqueio`, servidor real, 5 composições frias de relva a ppc 120
2,0–2,1 s, outras rotas disparadas 0,15 s depois do início; `dados/{antes,depois}_bloqueio.json`):

| rota | sem composição, mediana / máx. (ms) | durante uma composição, antes (A) | durante, depois (A) |
|---|---|---|---|
| `/api/status` | 1 / 18 | 2 / 19 | 19 / 25 |
| `/api/montar` | 37 / 51 | 58 / 77 | 61 / 64 |
| `/api/cell/5/30` | 22 / 35 | 46 / 59 | 55 / 77 |
| `board.jpg` **já em cache** | 14 / 18 | **1779 / 1807** | **1 / 21** |

O GIL, com o servidor estável, custa 20–40 ms às outras rotas; o `rlock` custava a composição inteira aos pedidos de
imagem.

**GIL com o ranking dos buracos a frio** (`gil_buracos.py`, em processo, `dados/gil_buracos.json`): região céu/relva a
ppc 100, sozinha 2,31–2,85 s; com `Gui._compute_holes` a correr noutro fio (o que o 1.º `/api/montar` faz):

| `sys.setswitchinterval` | composição com o ranking a correr (s) | ranking (s) |
|---|---|---|
| 0,005 (omissão do Python) | 26,16 · 9,53 · 2,15 (este já depois do ranking acabar) | 39,8 |
| 0,0005 | 4,09 · 3,85 · 4,08 | 28,7 |

Não implementado (fora de A e B); ver §5.

## 2. Browser: antes e depois de A + B

Um servidor novo por linha de medição (LRU vazia; ranking dos buracos já calculado, exceto em «arranque»). Tempo =
do salto até `body.dataset.detail` = `S.detailKey` (chave da vista final). Na GUI nova o salto é
`showCell(l, c, true)` (lupa / «localizar»), na antiga `zoomCells(l±3, c±5)` («Ver no tabuleiro»). «frio» = 1.ª visita
da região neste processo; «morno» = a mesma zona +1 coluna; «quente» = voltar à vista exata depois da vista inteira.
Tabelas completas: `tabela.py dados/antes_*.json dados/depois_*.json`.

### 2.1 Tempo até ao detalhe (s), antes → depois [V]

| cenário | novo 1920×1080 dpr 1 | novo 1366×768 dpr 1,25 | antiga 1920×1080 dpr 1 |
|---|---|---|---|
| céu frio | 2,69 → 2,62 | 2,50 → 2,79 | 2,14 → 2,21 |
| céu morno | 2,66 → 2,62 | 2,44 → 2,51 | 2,08 → 2,14 |
| relva frio | 2,47 → 2,44 | 2,35 → 2,34 | 1,95 → 1,97 |
| relva morno | 2,50 → 2,44 | 2,46 → 2,35 | 1,99 → 1,99 |
| vazia frio / morno | 0,39 / 0,38 → 0,38 / 0,39 | 0,36 / 0,36 → 0,36 / 0,36 | 0,37 / 0,37 → 0,38 / 0,38 |
| quente (3 zonas) | 0,31 → 0,30–0,31 | 0,29–0,30 → 0,29–0,30 | 0,30 → 0,30–0,31 |
| **5 saltos seguidos (400 ms)** | **8,20 → 3,49 / 3,43** | **7,62 → 5,47 / 3,33** | **4,80 → 3,93 / 3,92** |
| arrasto 3 s com pausas (zona vazia) | 3,30 → 3,29 | — | 3,29 → 3,30 |
| **arranque** (1.º salto logo depois de abrir) | **29,96 → 32,70** (outras corridas: 34,16, 31,50 / 32,07) | — | — |

(Depois: 2 corridas de 5 saltos, a da bateria completa e uma repetida só para medir a sobreposição no CDP.)

- O «quente» é ≈ todo o debounce de 280 ms de `scheduleDetail`; o pedido vem da cache HTTP do browser (0–1 ms).
- A + B não mudam o tempo frio de um salto (o servidor compõe o mesmo; as fases do §1 não mudaram).

### 2.2 Pedidos, ligações e resposta [V]

| cenário | medida | antes | depois |
|---|---|---|---|
| 5 saltos (novo 1920) | pedidos de detalhe enviados / compostos e mostrados / cancelados | 5 / 5 / 0 | 5 / 1 / 4 |
| 5 saltos (novo 1366) | idem | 5 / 5 / 0 | 5 / 1 / 4 |
| 5 saltos (antiga) | idem | 5 / 5 / 0 | 5 / 2 / 3 (um destino quase vazio acabou antes do salto seguinte) |
| 5 saltos | pico em voo (CDP) | 4–5 | 2, sobreposição ≤ 0,2 ms (o CDP só dá o abortado como terminado depois de registar o pedido seguinte; no JS, 1) |
| 5 saltos | maior espera em `queued`+`stalled` (CDP), detalhe e sondas | 26 ms (outras corridas 113–490 ms) | ≤ 4 ms |
| todos (estável) | long tasks > 50 ms / maior intervalo rAF | 0 / 17 ms | 0 / 17 ms |
| todos (estável) | sonda mais lenta (`/api/status`, `/api/montar`, `/api/cell` a cada 200 ms, no browser) | ≤ 119 ms | ≤ 71 ms |
| arranque | sonda mais lenta | 224 ms (outras corridas 328, 390) | 376 ms (outra 318) |

### 2.3 «Depois de um Encaixa» [V]

Na cópia, GUI nova na aba «Peças» (na aba Montar a vista segue o cartão seguinte depois de cada escrita:
`drawTarget(move)` → `showCell`, ou seja, um salto novo), vista parada numa zona; `POST /api/confirm`
`{acao: place}` de uma solta numa célula longe ((20,60)) ou perto (dentro da vista); tempo até o detalhe voltar
**na mesma viewBox** com a nova versão do log; depois `unplace` com `desfaz`.

| vista | escrita | POST (s), antes / depois | detalhe depois de o POST responder (s), antes / depois |
|---|---|---|---|
| céu | longe (20,60) | 5,73 / 5,40 | 2,27 / 2,28 |
| céu | perto (6,30) | 4,93 / 5,02 | 2,49 / 2,46 |
| relva | longe (20,60) | 4,91 / 5,00 | 2,22 / 2,21 |
| relva | perto (41,40) | 5,10 / 5,04 | 2,20 / 2,18 |
| vazia | longe / perto | 4,86 / 4,88 | 0,01 / 0,00 |

- **Longe e perto custam o mesmo** (2,2–2,5 s): qualquer escrita muda a versão do log e invalida todas as regiões,
  mesmo quando nenhuma célula da vista mudou. O pedido do detalhe demora 3,2–3,5 s (contra 2,0–2,4 s sozinho) porque
  coincide com o remendo do raster de fundo, a reconsulta e o ranking dos buracos (1,1–2,0 s, já quente).
- A + B não mudam isto (é o C).
- Com o POST a demorar ≈ 5 s, o detalhe volta ≈ 7,2–8,0 s depois do clique em céu/relva.

## 3. O que foi implementado (só A e B)

**A — `src/server.py`.** `Gui.board_jpg` compõe o tabuleiro inteiro como antes (sob `rlock`). Uma região passa por
`Gui._region_jpg`:
- compõe **fora de qualquer lock**; um `region_lock` novo guarda só a LRU (`_region_cached` / `_region_store`) e a
  tabela de composições em voo;
- dois pedidos iguais (mesma região, ppc e versão do log) partilham uma composição (`threading.Event`);
- o `zoom_jpg` usa o mesmo `region_lock` só para a cache.

**B — `src/web/board.js` + servidor.**
- `loadDetail`: `fetch` com `AbortController` → `blob` → `img.decode()` → `href` com objectURL; o objectURL anterior é
  revogado. Uma vista nova aborta o pedido anterior. `body.dataset.detail` continua a ser escrito quando o detalhe
  aparece.
- O cliente manda `X-Detail-Client` (id aleatório por separador) e `X-Detail-Seq`. No servidor, as composições de um
  cliente correm uma de cada vez. Um pedido com `seq` menor do que o maior já visto desse cliente é descartado antes
  de compor (`Superseded` → HTTP 409; se outro cliente esperava pela mesma região, tenta de novo).
- Sem os cabeçalhos (outros chamadores, testes antigos) nada é descartado.
- O URL não muda: a cache HTTP do browser (`max-age=3600`, `v=` = versão do log) continua a servir o quente.

**Testes novos:**
- `tests/test_server.py`:
  - `test_region_pixels_identical_to_compose_board`: a matriz BGR entregue ao JPEG é igual, com diferença máxima 0, a
    `render.compose_board(region)` em 5 regiões (inteiro, interior, cantos, uma célula) × ppc 120 e 240. Os bytes
    também são iguais, e a 2.ª chamada vem da LRU.
  - `test_region_composition_does_not_block_other_routes`: com `_compose` a dormir 2 s, `/api/status`, um
    `board.jpg` em cache e `/api/cell` respondem em < 200 ms. Falha no código de HEAD.
  - `test_equal_region_requests_share_one_composition`.
  - `test_superseded_detail_request_is_dropped_before_composing`: seq 2 → 409, 3 composições, o outro cliente não é
    afetado. Falha no código de HEAD.
- `tests/test_gui_novo.py::test_five_jumps_leave_one_detail_in_flight` (Playwright, `slow`): 5 saltos a 400 ms com
  composição lenta (0,7 s) dão no browser no máximo 1 pedido em voo, nunca 2 composições do mesmo cliente ao mesmo
  tempo, a chave final é a da última vista e o `href` é `blob:`.
- Um teste existente foi alterado: `tests/test_gui_novo.py::test_icons_local_aria_and_layout` passa a aceitar o `blob:` da mesma origem (o objectURL do detalhe) na verificação «nenhum pedido fora do servidor».

**Regressão visual [V].** Capturas Playwright na mesma viewBox, já com o detalhe, antes (worktree de HEAD) e depois:
- GUI nova: diferença 0 em céu/relva/vazia a 1920. A 1366 dpr 1,25, máx. 1 nível em 9 píxeis (relva).
- GUI antiga: máx. 6 níveis em 70 píxeis, num retângulo de 9 × 13 px no canto inferior esquerdo (x 27–35, y 1036–1048),
  fora do tabuleiro e igual nas 3 zonas.
- Ficheiros: `novo_ceu_1920_{antes,depois}.png` e
  `antiga_ceu_1920_{antes,depois}.png` nesta pasta.

## 4. Critério de sucesso (fixado antes de medir), depois de A + B

| # | critério | resultado |
|---|---|---|
| 1a | detalhe p95 ≤ 1,5 s a frio | **[F]** 2,2–2,8 s em céu/relva (máx. 2,79 s, 1366 dpr 1,25); só a zona vazia cumpre (0,36–0,39 s). A + B não mexem no tempo de composição. |
| 1b | detalhe ≤ 0,3 s a quente | **[F] por 10 ms**: 0,29–0,31 s (p95 0,31 s). O debounce de 280 ms de `scheduleDetail` sozinho gasta 0,28 s; o pedido vem da cache HTTP em 0–1 ms. |
| 2a | browser: nenhuma long task > 200 ms, nenhum intervalo rAF > 250 ms | **[V]** 0 long tasks, rAF ≤ 17 ms (já era assim antes). |
| 2b | servidor: `/api/status`, `/api/montar`, `/api/cell`, `board.jpg` em cache ≤ 300 ms durante uma composição | **[V] com o servidor estável:** máx. 25 / 64 / 77 / 21 ms. **[F] no arranque:** sondas no browser até 376 ms enquanto o ranking dos buracos corre a frio (antes: 224–390 ms). |
| 2c | nenhum pedido da GUI > 100 ms em `queued`/`stalled` por falta de ligação | **[V]** máx. 4 ms (antes até 490 ms em 5 saltos). |
| 3 | 5 saltos: no máximo 1 detalhe em voo no cliente e 1 composição no servidor por cliente | **[V]** no browser 1 pedido em voo no JS (no CDP 2 durante ≤ 0,2 ms); no servidor 1 composição por cliente de cada vez (teste Playwright com `_compose` lento). Na corrida real: 4 de 5 pedidos abortados. |

## 5. Recomendação (C–G e o que apareceu fora do plano), com números

1. **(novo, H) Intervalo de troca do GIL no servidor.** `sys.setswitchinterval(0.0005)` no arranque do servidor:
   - com o ranking dos buracos a frio, a composição passou de 26,2 s para 4,1 s;
   - o ranking em si não ficou mais lento (39,8 → 28,7 s, 1 corrida de cada).
   É uma linha, mas mexe em todo o processo: medir antes o ranking, a reconsulta e a importação com e sem o
   intervalo novo. Ataca diretamente o caso «primeira lupa depois de abrir» (30–34 s hoje).
2. **E — cache por peça dos recortes já prontos para desenhar.** Guardar o RGBA depois da regra da sombra, a
   profundidade e o registo:
   - «sombra» + «ler recorte» + «profundidade» + «registar» = 1,2–1,7 s dos 2,3–2,6 s frios na lupa (≈ 55–65 %);
   - estimativa: frio ≈ 0,9–1,2 s, abaixo do critério 1a (1,5 s) [NT];
   - é o único item que ataca o tempo frio de um salto;
   - memória: RGBA + RGBA do bleed + profundidade em float32 de um recorte de ≈ 350 × 350 px ≈ 1,5 MB por peça,
     ≈ 1 GB para as 700 colocadas: LRU obrigatório (as peças das vistas recentes) [NT].
3. **C — mosaicos.** O cenário «depois de um Encaixa» diz que vale a pena:
   - hoje longe e perto custam o mesmo (2,2–2,5 s depois do POST em céu/relva);
   - com mosaicos validados pelo `board_snapshot` das suas células, uma escrita longe da vista não recompõe nada (≈ o
     quente, 0,3 s) e uma escrita perto recompõe 1–2 mosaicos de 8 × 8 em vez das 294 células da vista;
   - o «morno» (arrastar 1 coluna), hoje um frio inteiro (2,4–2,6 s), passa a ≈ 0 para os mosaicos já feitos.
   Fazer depois de E (que baixa o custo de cada mosaico), com o teste de identidade de píxeis nas costuras.
4. **D — degrau intermédio: não.** À distância da lupa o detalhe pede ppc 80–100, e o fundo já é ppc 60. Um degrau a
   2× do fundo (120) é maior do que o pedido. Só ajudaria de perto (ppc 240), que já compõe em 1,2–1,4 s.
5. **G — teto de píxeis: não.** A lupa pede 2,2–2,9 MP, longe do teto de 11 MP, e o ppc já segue o dpr. O custo é
   por peça, não por píxel (3,4 MP vazios em 0,085 s).
6. **F — processo à parte:** só se H não chegar. Com o servidor estável, o GIL custa 20–40 ms às outras rotas. O mau
   caso é o ranking a frio, e H resolve-o em 1 linha (na medição em processo).
7. **Debounce de 280 ms:** é o que separa o quente do critério 1b (0,31 contra 0,30). Com B, um salto (lupa,
   «localizar») podia pedir sem debounce, mantendo-o só no arrasto/roda. Fica para decidir com o Tiago, por ser
   uma mudança de comportamento.

## 6. Limites

- Medido em Chromium headless numa máquina, sem rede real (localhost). Firefox, telemóvel e `--lan` ficam [NT]. O
  «deixou de responder» do Tiago não foi reproduzido como bloqueio do fio do browser: aqui o fio nunca bloqueou. A
  hipótese mais forte para o relato é o arranque (ranking a frio), mas é [NT] na máquina dele.
- A decomposição em fases (§1) soma o tempo dentro das funções embrulhadas e foi medida com o código de HEAD; o «resto»
  é a alocação e a mistura em float32 de `compose_board`.
- A medição pré-F1 (worktree `8fedf87^`) precisou de tirar 1 evento `rejection_undone` da cópia do log (ação que esse
  código não conhece). O tabuleiro e as peças colocadas ficaram iguais.
- «arranque» varia entre corridas (29,96 / 31,50 / 34,16 s antes; 32,07 / 32,70 s depois), conforme o salto cai mais
  cedo ou mais tarde no ranking.
