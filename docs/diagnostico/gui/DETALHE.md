# Tabuleiro: o detalhe demora depois de um salto (lupa / «localizar» / «Ver no tabuleiro»)

2026-11-14. Plano aprovado: `C:\Users\tiago\.claude\plans\agente-implementer-skills-systematic-deb-witty-pelican.md`
(condições do Tiago no topo). Medido numa **cópia** de `projects/alpes` no scratchpad (698 peças colocadas), Chromium
headless (Playwright) com CDP `Network`, Windows 11, `.venv` (Python 3.13). Dados em bruto: `dados/*.json`.
Guiões: `tools/diagnostico/gui/salto_detalhe.py` (browser), `tempo_regiao.py` (servidor: fases e bloqueio),
`gil_buracos.py` (GIL), `tabela.py` (tabelas a partir dos JSON). **Ronda 2** (mesmo dia, §6–§7): `gil_intervalo.py`
(intervalo do GIL no servidor real, com e sem), `buracos_frio.py` (fases do 1.º ranking dos buracos); dados `dados/r2_*`.
**Passo 0 da F2** (§8): `salto_frio_gil.py` (salto a frio com o servidor parado, 5 contra 0,5 ms), dados `dados/r3_p0a_*`;
teste de esforço `tests/test_concorrencia.py`.

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

- **Ronda 2 (§6–§7) [V]:**
  - um salto (lupa, «localizar», «Ver no tabuleiro») pede o detalhe sem a espera de 280 ms; arrastar e a roda mantêm-na.
    O quente passa de 0,30 para 0,01–0,02 s (1b passa a [V]);
  - **H adotado:** `sys.setswitchinterval(0.0005)` no servidor (`--gil-intervalo`, 0 = o do Python). Em 6 corridas,
    o detalhe durante o ranking a frio passou de 20,3 / 23,3 s para 7,6 / 6,6 s (céu / relva); a reconsulta ficou igual
    (−3 %) e a importação +1,4 % (critério: ≤ 10 %). O 1.º salto logo depois de abrir passou de ≈ 37 s para ≈ 11 s;
  - causa de fundo do 1.º `/api/montar` (§7): o ranking em si custa < 1 s; os 24 s (sozinho; 43–50 s no servidor) são
    lados erodidos (18 s) e formas (5 s) que só vivem em memória. Proposta: guardá-los em disco como as tiras;
  - corrigida uma corrida entre fios em `render._clean_or_crop` que a composição fora do lock (A) expôs (§6.3).

- **Passo 0 da F2 (§8) [V]:**
  - com o servidor parado, o intervalo de 0,5 ms não piora a composição sozinha (3 + 3 corridas: +6,6 % a +9,3 % na média
    por causa de uma corrida suspeita, medianas +1,0 % a +5,8 %; 4 corridas de controlo iguais nos dois intervalos);
    a diferença ronda 1 (2,0–2,8 s) / ronda 2 (2,9–3,5 s) é a forma de medir: parado dá os números da ronda 1, e o
    protocolo da ronda 2 (abrir a página arranca o ranking dos buracos) dá 4,6–7,8 s;
  - auditoria da composição fora dos bloqueios e teste de esforço novo (`tests/test_concorrencia.py`): na HEAD de então
    falhou 21 em 22 corridas (escritas não atómicas de recortes, `placements.json`, `npz`; apagar ficheiros que outro fio
    lê; a forma e a pose em cache guardadas a meio de uma escrita); corrigido, 20/20.

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
| 1b | detalhe ≤ 0,3 s a quente | **[F] por 10 ms**: 0,29–0,31 s (p95 0,31 s). O debounce de 280 ms de `scheduleDetail` sozinho gasta 0,28 s; o pedido vem da cache HTTP em 0–1 ms. **Ronda 2: [V]** 0,01–0,02 s (os saltos já não esperam, §6.1). |
| 2a | browser: nenhuma long task > 200 ms, nenhum intervalo rAF > 250 ms | **[V]** 0 long tasks, rAF ≤ 17 ms (já era assim antes). |
| 2b | servidor: `/api/status`, `/api/montar`, `/api/cell`, `board.jpg` em cache ≤ 300 ms durante uma composição | **[V] com o servidor estável:** máx. 25 / 64 / 77 / 21 ms. **[F] no arranque:** sondas no browser até 376 ms enquanto o ranking dos buracos corre a frio (antes: 224–390 ms). |
| 2c | nenhum pedido da GUI > 100 ms em `queued`/`stalled` por falta de ligação | **[V]** máx. 4 ms (antes até 490 ms em 5 saltos). |
| 3 | 5 saltos: no máximo 1 detalhe em voo no cliente e 1 composição no servidor por cliente | **[V]** no browser 1 pedido em voo no JS (no CDP 2 durante ≤ 0,2 ms); no servidor 1 composição por cliente de cada vez (teste Playwright com `_compose` lento). Na corrida real: 4 de 5 pedidos abortados. |

## 5. Recomendação (C–G e o que apareceu fora do plano), com números

1. **(novo, H) Intervalo de troca do GIL no servidor.** *Feito na ronda 2 (§6.2), com as medidas pedidas.* `sys.setswitchinterval(0.0005)` no arranque do servidor:
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
7. **Debounce de 280 ms:** *feito na ronda 2 para os saltos (§6.1), a pedido do Tiago.* é o que separa o quente do critério 1b (0,31 contra 0,30). Com B, um salto (lupa,
   «localizar») podia pedir sem debounce, mantendo-o só no arrasto/roda. Fica para decidir com o Tiago, por ser
   uma mudança de comportamento.

## 6. Ronda 2 (2026-11-14): sem espera nos saltos e intervalo do GIL (H)

Pedido do Tiago: (1) tirar a espera de 280 ms nos saltos (lupa e «localizar») e mantê-la ao arrastar e na roda;
(2) experiência com `sys.setswitchinterval`, 3 corridas com e 3 sem, adotada só se o detalhe melhorar e a reconsulta e
a importação não piorarem mais de 10 %; (3) causa de fundo dos 30–40 s do 1.º `/api/montar`, sem implementar (§7);
E, C, D, F e G ficam para depois da F2. Prompt: `docs/prompts/2026-11-14-detalhe-tabuleiro-ronda2.md`.

Todas as medições numa cópia nova de `projects/alpes` feita com `shutil.copytree` (1433 peças, versão do log 2299530).
**Atenção [V]:** uma cópia com `cp -r` muda o mtime de `render/placements.json`, a cache do raster em disco
(`render/gui/board_60.json`, campo `pl_mtime`) deixa de valer e cada arranque recompõe o tabuleiro inteiro (35–60 s)
por baixo das medidas, porque `/api/status` diz «pronto» antes disso. A 1.ª bateria desta ronda foi feita assim e foi
deitada fora (`dados/r2_gil_corridas_invalidas.json`): dava à reconsulta um ganho de −28 % que era só a composição do
tabuleiro a acabar mais cedo com o intervalo curto. Na ronda anterior a cópia `alpes_det` foi reutilizada entre
corridas, por isso a cache já tinha sido refeita.

### 6.1 Sem espera nos saltos [V]

`src/web/board.js`: `setView(vb, now)` e `fitRect(…, now)`; `zoomCells` (o caminho da lupa / `showCell`, de
«localizar», do «Ver no tabuleiro» e do «Localizar peça» da GUI antiga, e do cartão seguinte depois de um «Encaixa»)
passa `now = true` e pede o detalhe na mesma tarefa (`clearTimeout` + `loadDetail`). Arrastar, a roda, a pinça, os
botões +/−, o duplo clique, «ajustar» e o redimensionar continuam com `scheduleDetail` (280 ms depois da última vista).
Com B (ronda 1), um salto seguido de outro aborta o pedido anterior no browser e o servidor descarta-o antes de compor.

Teste novo: `tests/test_gui_novo.py::test_jump_asks_detail_at_once_drag_and_wheel_keep_debounce` (Playwright, `slow`):
- `zoomCells` e o botão «localizar»: o `fetch` do detalhe sai **na mesma tarefa** do salto (< 50 ms; medido ≈ 0 ms);
- arrastar (8 movimentos a 30 ms): nenhum pedido durante o arrasto, o pedido sai ≥ 250 ms depois do último movimento;
- roda (3 voltas a 40 ms): idem, ≥ 250 ms depois da última volta.
Com o `board.js` de HEAD o 1.º `assert` falha (`{'n': 1, 'sent': 1, 'dt': None}`: nenhum pedido no salto).

Browser (`salto_detalhe.py`, GUI nova 1920 × 1080, servidor novo por linha, ranking dos buracos já feito, intervalo
0,5 ms nos dois; «com espera» = o `board.js` de HEAD servido pelo mesmo código; `dados/r2_saltos_*.json`):

| cenário | com espera (HEAD) | sem espera nos saltos |
|---|---|---|
| céu frio / morno (+1 col.) | 4,01 / 3,65 | 3,51 / 3,02 |
| relva frio / morno | 3,76 / 3,42 | 3,18 / 2,85 |
| vazia frio / morno | 0,41 / 0,41 | 0,12 / 0,29 |
| **quente (céu / relva / vazia)** | **0,30 / 0,31 / 0,31** | **0,01 / 0,02 / 0,02** |
| 5 saltos seguidos (400 ms) | 5,11 (5 enviados, 4 cancelados) | 4,46 (5 enviados, 4 cancelados) |

- O quente passa de 0,30 s (quase só a espera) para 0,01–0,02 s: o critério 1b (≤ 0,3 s) passa a **[V]**.
- O frio desce 0,3–0,6 s (a espera mais ruído entre servidores); continua acima de 1,5 s em céu/relva (1a **[F]**:
  2,9–3,5 s neste projeto, que tem mais peças do que a cópia da ronda 1, 2,4–2,7 s). Só E ataca o frio.
- 0 long tasks e rAF ≤ 17 ms nas duas colunas (como antes).

### 6.2 Intervalo do GIL (H): 6 corridas [V]

`tools/diagnostico/gui/gil_intervalo.py` (`dados/r2_gil_corridas.json`). Cada corrida: cópia nova da base, servidor
novo (`python -m src.server --gil-intervalo 0` = 5 ms, ou `0.0005` = 0,5 ms; o valor em vigor confirmado na linha
«intervalo do GIL … ms» do registo de cada servidor), ordem alternada sem/com. Medidas:
- **detalhe durante o ranking a frio:** `GET /api/montar` (arranca o ranking, como o 1.º pedido da GUI nova), 2 s
  depois uma região de céu (1,21–14,41) e a seguir uma de relva (34,31–47,51) a ppc 100, LRU vazia; no arranque correm
  também a verificação de ativos e os fantasmas (como no uso real);
- **reconsulta:** com o servidor parado, `POST /api/confirm` `place` da solta P0096 em (20,60), a mesma da ronda 1, e depois `unplace` com
  `desfaz` (tempo do POST; dentro, a consulta incremental do registo de atividade);
- **importação:** `POST /api/ingest` de uma folha de 10 peças (saco 99) e espera pelo fim do trabalho na fila
  (`segundos` do trabalho; dentro, a consulta completa).

| corrida | intervalo | detalhe céu (s) | detalhe relva (s) | reconsulta: place / unplace (s) | consulta incremental (s) | importação (s) | consulta completa (s) | ranking dos buracos (s) | detalhe sozinho céu / relva (s) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 5 ms | 18,18 | 21,41 | 4,52 / 3,83 | 2,1 / 1,9 | 69,3 | 64,6 | 48,7 | 2,76 / 2,76 |
| 2 | 0,5 ms | 8,20 | 6,75 | 4,37 / 3,70 | 2,0 / 1,8 | 66,9 | 61,9 | 47,7 | 2,74 / 2,72 |
| 3 | 5 ms | 22,47 | 23,85 | 4,56 / 3,83 | 2,1 / 1,9 | 67,3 | 62,7 | 49,1 | 2,94 / 2,69 |
| 4 | 0,5 ms | 5,92 | 6,28 | 4,36 / 3,49 | 2,1 / 1,8 | 68,3 | 63,4 | 43,2 | 2,77 / 2,76 |
| 5 | 5 ms | 20,29 | 24,76 | 4,77 / 4,11 | 2,2 / 2,0 | 67,4 | 62,4 | 49,1 | 2,95 / 2,97 |
| 6 | 0,5 ms | 8,58 | 6,82 | 4,76 / 3,93 | 2,2 / 1,9 | 71,6 | 66,2 | 49,5 | 2,90 / 2,90 |
| **média 5 ms** | | **20,31** | **23,34** | **4,62 / 3,92** | 2,03 | **68,0** | 63,2 | 49,0 | 2,88 / 2,81 |
| **média 0,5 ms** | | **7,57** | **6,62** | **4,50 / 3,71** | 1,97 | **68,9** | 63,8 | 46,8 | 2,80 / 2,79 |
| **diferença** | | **−63 %** | **−72 %** | **−3 % / −5 %** | −3 % | **+1,4 %** | +0,9 % | −4 % | −3 % / −1 % |

**Decisão (critério fixado pelo Tiago antes de medir): adotado [V].**
- detalhe durante o ranking a frio: melhora (céu 18,2–22,5 → 5,9–8,6 s; relva 21,4–24,8 → 6,3–6,8 s);
- reconsulta: não piora (média −3 % / −5 %; pior corrida com 0,5 ms 4,76 s contra a melhor com 5 ms 4,52 s = +5 %);
- importação: +1,4 % na média (pior corrida 71,6 s = +5,3 % sobre a média com 5 ms), abaixo dos 10 %.

`src/server.py`: `GIL_SWITCH_S = 0.0005`, `apply_gil_interval()` chamado no início de `main()` (antes de qualquer fio:
a preparação do arranque é um) e a opção `--gil-intervalo S` (omissão 0,0005; `0` deixa o valor do Python, 0,005).
O registo diz o valor em vigor na linha «mesa de montagem: … intervalo do GIL 0.5 ms». Só o servidor: as CLI
(`query`, `confirm`, `ingest`, `fit`) e os testes não mudam. Teste: `tests/test_server.py::
test_gil_interval_on_by_default_and_zero_keeps_python_default`.

Notas:
- O detalhe durante o ranking continua 2–3 vezes mais lento do que sozinho (6,6–7,6 s contra 2,8 s): H reduz o
  efeito «comboio», não o elimina (o ranking em Python puro continua a ter o GIL metade do tempo). Isso é o §7.
- O arranque no browser (1.º salto logo depois de abrir `/novo/`): com a cópia válida (cache do raster em disco, como na máquina do
  Tiago), 2 corridas de cada, `dados/r2_arranque_{com,sem}{1,2}.json`:

  | intervalo | 1.º salto céu (s) | 1.º salto relva (s) | sonda mais lenta (ms) | ranking dos buracos (s) |
  |---|---|---|---|---|
  | 5 ms | 37,23 · 37,32 | 14,46 · 14,70 | 412 · 333 | 53,8 · 54,2 |
  | 0,5 ms | 11,34 · 11,04 | 5,85 · 5,87 | 336 · 311 | (não registado: o servidor parou antes de acabar) |

  O mau caso do relato do Tiago («primeira lupa depois de abrir») passa de ≈ 37 s para ≈ 11 s [V]; continua longe do
  critério 1a, e o 2b no arranque continua **[F]** (sondas até 311–336 ms, critério 300 ms).
- Fora do critério: o ranking a frio não ficou mais lento (49,0 → 46,8 s).

### 6.3 Achado: `_clean_or_crop` podia morrer com `FileNotFoundError` [V], corrigido

Na 1.ª bateria (cópia com `cp -r`), a composição do tabuleiro inteiro no arranque morreu com `FileNotFoundError` em
`os.path.getmtime` dentro de `render._clean_or_crop`: com A (ronda 1) uma região compõe-se fora do `rlock`, ao mesmo
tempo que o tabuleiro inteiro; os dois viram o mesmo `render/clean/P####.png` velho e um apagou-o entre o `exists` e o
`getmtime` do outro. Efeito: «ERRO na preparação» no arranque e o tabuleiro composto mais tarde pelo 1.º pedido
(o mesmo podia dar um 500 numa região). Só acontece com ficheiros `render/clean` velhos (uma folha re-segmentada
noutro checkout, ou uma cópia sem mtime). Correção (`src/render.py`): um ficheiro que desaparece a meio conta como
velho e a peça limpa-se na hora. Teste: `tests/test_render.py::
test_clean_or_crop_survives_clean_file_deleted_by_another_thread` (falha com o `render.py` de HEAD).

## 7. Causa de fundo: porque é que o 1.º `/api/montar` calcula 30–50 s em cada arranque (só análise)

`tools/diagnostico/gui/buracos_frio.py` (`dados/r2_buracos_frio.json`): `Gui._compute_holes` num processo novo, sozinho
(sem servidor nem pedidos), com as fases de `src.fit.rank_all` cronometradas (tempo inclusivo; uma fase pode conter
outra), e a seguir o mesmo cálculo no mesmo processo com a cache do ranking apagada (como depois de uma escrita):

| fase (inclusiva) | a frio, processo novo (s) | chamadas | depois de uma escrita, mesmo processo (s) |
|---|---|---|---|
| **total** | **24,0** | | **0,87** |
| `eroded_sides` (lados erodidos das soltas e das vizinhas, 0,60 mm) | **18,1** | 738 (≈ 24 ms cada) | 0 (em memória) |
| `pool_items` (soltas: formas, lados erodidos, tiras) | 15,1 | 1 | 0,00 |
| `hole_queries` (buracos, lados das vizinhas) | 5,1 | 1 | 0,01 |
| `Project.shape` (`pieces/<scan>.npz` → `Shape`) | 4,9 | 2926 (1222 peças diferentes, ≈ 4 ms cada a frio) | 0,00 |
| `board_sigma` (poses + formas das colocadas) | 2,9 | 1 | 0,04 |
| `render.initial_theta` (pose de 698 colocadas) | 2,0 | 698 | 0,01 |
| `rank_hole` (203 buracos × 524 soltas) | 0,8 | 203 | 0,77 |

No servidor o mesmo cálculo demora 43–50 s (§6.2: 43,2–49,5 s) porque divide o processo com a verificação de ativos,
os fantasmas e as composições do arranque.

**O que fica em disco e sobrevive a um arranque:**
- `render/fit/strips.npz`: as tiras de imagem de cada peça (chave: id + bbox); as 825 estavam lá, 0 calculadas;
- `pieces/<scan>.npz`: as formas (lidas peça a peça);
- `render/gui/board_60.{jpg,json}` (o raster do fundo, válido enquanto o log e o mtime de `placements.json` batem
  certo), `render/placements.json`, `fetch.json` (a fila do Montar lê-o).

**O que só existe em memória e se perde em cada arranque:**
- o resultado do ranking (`Gui._holes`, chave = (tamanho do log, `id(self.pr)`)): 0,9 s a refazer com o resto quente;
- os lados erodidos (`fit._Cache.sides`): **18 s, 75 % do frio**;
- as formas (`Project._shape_cache`, `_Cache.shapes`): 4,9 s;
- as poses das colocadas e os `board_dirs` (`dcache` local de `rank_all`, refeito em cada cálculo): 2 s, mas só a
  frio (`initial_theta` lê as formas, que ficam em memória).

Ou seja: o ranking em si custa < 1 s; os 24 s (sozinho) são preparação por peça que só vive na memória do processo.
Depois de uma escrita o servidor refaz o ranking em 1,3 s (registo de §6.2: «203 buracos × 523 soltas em 1,3 s»).

**Opções (nenhuma implementada):**

| opção | o que faz | ganho esperado | risco |
|---|---|---|---|
| **A. Lados erodidos em disco** | `render/fit/sides.npz` como as tiras: chave id + bbox + `erosion_mm` + `FIT_VERSION` + um hash dos arrays da forma | frio 24 → ≈ 6 s sozinho (−18 s) em **todos** os arranques, mesmo com o log mudado (CLI, importação com o servidor parado) [NT, estimativa pela tabela] | médio-baixo: lados velhos se a silhueta mudar sem mudar a bbox (contorno manual, re-segmentação) — por isso o hash da forma na chave, não só a bbox; ficheiro de ≈ 1–3 MB [NT] |
| **B. Formas lidas por folha** | `Project.shape` abre o `npz` da folha uma vez e guarda todas as peças dela, em vez de abrir o zip por peça | 4,9 s → < 1 s [NT] | baixo (só leitura; memória: as formas de todas as peças, já hoje em `_shape_cache` depois do 1.º ranking) |
| **C. Ranking em disco com a versão do log** | `render/fit/holes.json` com chave sha256 do log + `FIT_VERSION` + calibração + assinatura de `strips.npz` | arranque com o log igual ao da última sessão: 0 s; nada nos outros casos — e a 1.ª escrita depois do arranque volta a pagar os 24 s (as caches por peça continuam frias), ou seja só muda o momento do custo | médio: um resultado velho se mudar algo que o log não vê (código de `fit.py` sem subir `FIT_VERSION`, `puzzle.json`, ativos refeitos); a chave tem de os incluir todos |
| **D. Calcular em segundo plano ao arrancar** | no fim de `_prepare` (depois do tabuleiro e dos fantasmas) arrancar `holes_json(wait=False)`, com «A preparar sugestões… n de N» | o custo não diminui, mas acontece enquanto o Tiago abre o browser; com H, uma lupa nesse intervalo custa 6–8 s em vez de 20–25 s; o Montar já hoje funciona sem os buracos (`a_preparar.buracos`) e mostra as sugestões quando chegam | baixo; mas o «n de N» de hoje só conta tiras (0/1 o tempo todo neste projeto, ver o registo) — precisa de contar os lados erodidos; CPU gasto em cada arranque mesmo quando o Tiago só vai importar; a fila muda quando as sugestões `alta` chegam (já hoje) |

**Recomendação:** A + B primeiro (tiram ≈ 22 s dos 24 s em qualquer arranque, sem decisões de invalidação novas além
das que as tiras já têm), depois D (pouco código; a progressão passa a ser verdadeira); C só se ainda fizer falta
(ganha o arranque sem mudanças, mas é o que tem a invalidação mais frágil). Medir depois o 1.º `/api/montar` e a lupa
no arranque com o mesmo guião.

## 8. Passo 0 da F2 (2026-11-14): salto a frio com o servidor parado e auditoria de concorrência

Pedido do Tiago antes da F2: (a) medir o salto a frio sem nada do arranque a correr, com o intervalo do GIL a 5 ms e a
0,5 ms, e dizer porque é que a ronda 1 dava 2,0–2,8 s e a ronda 2 2,9–3,5 s (parar se 0,5 ms piorar > 10 %); (b) listar
o que a composição lê fora dos bloqueios e o que as escritas mudam entretanto, com um teste de esforço na suite.

### 8.1 Salto a frio, servidor parado: 5 ms contra 0,5 ms [V]

`tools/diagnostico/gui/salto_frio_gil.py` (`dados/r3_p0a_corridas.json`, `r3_p0a_controlo.json`). Cópia nova de
`projects/alpes` por corrida com `shutil.copytree` (1433 peças, versão do log 2299530), servidor novo
(`--gil-intervalo 0` = 5 ms ou `0.0005`, o valor confirmado na linha do registo de cada corrida); antes de medir: estado
«pronto», o tabuleiro inteiro da cache do disco (0,12–0,16 s em todas: a cache era válida), o ranking dos buracos
arrancado e acabado (30–35 s) e 3 s de folga. Depois: **browser** = `salto_detalhe.py --cenarios saltos` (GUI nova
1920 × 1080, o mesmo gesto e a mesma região das rondas 1 e 2: céu 1,20–14,40 e relva 34,30–47,50 a ppc 100);
**servidor** = o pedido HTTP de uma região fria do mesmo tamanho (3 colunas ao lado), sem browser.

| corrida | intervalo | browser céu (s) | browser relva (s) | servidor céu (s) | servidor relva (s) |
|---|---|---|---|---|---|
| 1 | 5 ms | 2,58 | 2,35 | 2,29 | 2,22 |
| 2 | 0,5 ms | 2,73 | 3,02 | 2,66 | 2,78 |
| 3 | 0,5 ms | 2,66 | 2,40 | 2,05 | 2,16 |
| 4 | 5 ms | 2,56 | 2,47 | 2,01 | 2,15 |
| 5 | 5 ms | 2,64 | 2,37 | 2,08 | 2,20 |
| 6 | 0,5 ms | 2,90 | 2,41 | 2,10 | 2,24 |
| **média 5 ms** | | **2,59** | **2,40** | **2,13** | **2,19** |
| **média 0,5 ms** | | **2,76 (+6,6 %)** | **2,61 (+8,9 %)** | **2,27 (+6,7 %)** | **2,39 (+9,3 %)** |
| mediana 5 ms → 0,5 ms | | 2,58 → 2,73 (+5,8 %) | 2,37 → 2,41 (+1,7 %) | 2,08 → 2,10 (+1,0 %) | 2,20 → 2,24 (+1,8 %) |
| controlo 7–10 (0,5 / 5 / 0,5 / 5 ms) | | 2,56 / 2,56 / 2,56 / 2,54 | 2,34 / 2,30 / 2,36 / 2,35 | 2,03 / 2,03 / 2,03 / 2,02 | 2,13 / 2,14 / 2,13 / 2,15 |

**Decisão: o intervalo de 0,5 ms não piora a composição sozinha mais de 10 % [V]; a F2 seguiu.** As 3 + 3 corridas
pedidas dão +6,6 % a +9,3 % na média, puxados pela corrida 2, a mais lenta nas 4 colunas ao mesmo tempo (incluindo a
medida só do servidor, feita depois do browser). Durante as corridas 1–2 corri no mesmo PC verificações de importação
(`python -c "import src.server"`), por isso a corrida 2 é suspeita de carga externa [NT: não o consigo provar]. Repeti
4 corridas de controlo alternadas sem tocar no PC: os dois intervalos dão o mesmo (céu 2,56 contra 2,55 s, relva 2,35
contra 2,33 s, servidor 2,03 contra 2,02 s). Com as 10 corridas: mediana +3,9 % / +2,1 % (browser) e +1,0 % / +0,5 %
(servidor).

**Porque é que a ronda 2 deu 2,9–3,5 s e a ronda 1 2,0–2,8 s: a forma de medir, não o intervalo [V em parte].**
- Com o servidor parado, a mesma região, o mesmo gesto e qualquer dos dois intervalos dá 2,5–2,9 s (céu) e 2,3–3,0 s
  (relva) no browser: os números da ronda 1 (2,62 / 2,44 s a 1920, já com os 280 ms de espera que a ronda 2 tirou).
- Uma corrida extra com o protocolo dos saltos da ronda 2 (`--protocolo-r2`: o `salto_detalhe.py` abre `/novo/` logo que
  o estado diz «pronto»; a abertura pede `/api/montar`, que arranca o ranking dos buracos a frio, e o 1.º salto sai
  ≈ 1,5 s depois) deu **céu 7,83 s, relva 4,61 s**, morno 4,6 s (`dados/r3_p0a_protocolo_r2_browser.json`): o salto
  passa a dividir o processo com o ranking (40 s neste projeto).
- A ronda 2 registou «ranking dos buracos já feito», mas o `_wait_idle` do guião só espera por «pronto» e não pelos
  buracos, e os ficheiros `r2_saltos_*.json` não guardam a hora: não sei quanto do ranking (ou da recomposição do
  tabuleiro de uma cópia `cp -r`, §6) ainda corria. Os 2,9–3,5 s ficam entre o parado (2,4–2,9) e o sobreposto
  (4,6–7,8), o que é consistente com uma sobreposição parcial [NT: não reproduzido exatamente].
- O intervalo não muda a composição sozinha (tabela acima), e na ronda 2 as duas colunas («com espera» e «sem
  espera») já corriam com 0,5 ms.

### 8.2 Auditoria: o que a composição lê fora dos bloqueios [V]

Caminhos de composição: `Gui._region_jpg` (detalhe, sem bloqueio desde a ronda 1), `Gui.zoom_jpg` (zoom 3 × 3 da
célula), `Gui.piece_png` (miniaturas), `Gui._base` (tabuleiro inteiro, sob `rlock`, que nenhuma escrita toma), todos
por `render.compose_board` / `compose_zone_vs_art` / `piece_rgba_for_display`. Escritas: `Gui.confirm` (sob `wlock`:
`place`, `unplace`, posições, pares, âncoras, marcas), o editor do contorno (`rebuild_piece`), a pose manual, a
importação (`commit_sheet`), `rebuild_stale` no arranque, e o `sync()` quando o log muda fora do servidor.

**Estado em memória**

| leitura | quem a muda entretanto | antes | agora |
|---|---|---|---|
| `Gui.pr` (o objeto `Project`) | `sync()` troca-o quando a CLI escreve | seguro: a composição usa o objeto que apanhou; a chave da cache é a versão de então | igual |
| `project.pieces` (dicionário; `placed_ids`) | a importação acrescenta peças | seguro: `RuntimeError` «changed size» repetido por `Gui.read` (até 4×) | igual |
| `Piece.celula` lida 3 vezes por peça (filtro, ordem, `celula[0]`) | `unplace`, `position_cleared`, `unanchor` põem `None` | **falha possível**: `TypeError` se a peça sair entre as leituras | **corrigido**: uma leitura por peça (`compose_board`) |
| `Piece.bbox`, `crop_path`, `theta_deg`, `pose_manual`, `seccao_id`, `anchor` | re-segmentação, pose manual, âncoras | transitório: a composição em curso pode misturar o antes e o depois; fica na cache com a chave da versão em que começou, que deixa de ser pedida quando o evento entra no log | igual (documentado) |
| `project._shape_cache` | re-segmentação (`forget`) | **falha possível**: quem leu o `npz` velho guardava a forma velha depois do `pop` do escritor, e ficava até ao fim do processo | **corrigido**: geração por peça (`Project.forget_shape`); uma leitura apanhada a meio não volta a guardar |
| `Gui._placements` e a LRU das regiões, do zoom e das miniaturas, chave = tamanho do log | `_refresh_render_assets` regrava `render/placements.json` **depois** do log | **falha possível**: uma composição nesse intervalo guardava, para toda a versão, a pose calculada na hora (sem o registo com imagem) | **corrigido**: chave = `render_version()` = (tamanho do log, mtime de `placements.json`); o tabuleiro inteiro volta a remendar as células dessas peças |
| `Gui._regions`, `_region_jobs`, `_detail_seq` | outros pedidos | seguro: `region_lock` | igual |
| `Gui._board` (tabuleiro inteiro) | `_base` noutro pedido; agora também o fim do `_refresh_render_assets` | seguro: `rlock` | igual (o refresh toma o `rlock` só para marcar as células) |
| `overrides._ARESTA_CACHE` | o editor acrescenta linhas | seguro: chave (tamanho, mtime) do ficheiro | igual |

**Ficheiros**

| ficheiro | quem o escreve / apaga | antes | agora |
|---|---|---|---|
| `render/placements.json` | `_refresh_render_assets`, `_drop_stale_caches`, `register_all` (`tmp` + `os.replace` sem repetição) | **falhou no teste**: `PermissionError [WinError 5]` no `os.replace` enquanto uma composição o lia: a escrita (`Gui.confirm`) rebentava depois de o log estar gravado | **corrigido**: `state.write_atomic` (temporário único por fio + `os.replace` repetido como o `_write_json`) |
| `crops/P####.png` | `rebuild_assets` (editor do contorno, re-segmentação), escrito no próprio sítio | **falhou no teste**: `UnidentifiedImageError` ao ler um PNG a meio (3–4 em 10 corridas) | **corrigido**: escrita atómica (`render.save_png`) |
| `render/clean/P####.png` | `_refresh_render_assets`, `clean_all` (no próprio sítio); apagado por `_drop_stale_caches` e pelo leitor quando velho | **falhou**: (1) `FileNotFoundError` da ronda 2 (já corrigido em `6399e31`; o teste novo apanha-o 5/5 com o `_clean_or_crop` de antes); (2) `PermissionError [WinError 32]` ao apagar um ficheiro que uma composição lia: a re-segmentação parava **entre** gravar o `npz`/recorte e escrever o evento no log (5–6 em 10 corridas); (3) um leitor podia apagar o ficheiro novo que outro fio acabava de gravar | **corrigido**: escrita atómica; `state.remove_file` (repete; se ficar, é mais velho do que o recorte e todos os leitores o tratam como velho); o leitor só apaga o ficheiro que julgou velho (mesmo mtime e tamanho) |
| `pieces/<scan>.npz` | `Project.save` (arrays pendentes: importação, re-segmentação) e `rebuild_assets`, no próprio sítio | **falha possível** (não apareceu no teste): `BadZipFile` / `EOFError` num `np.load` a meio | **corrigido**: escrita atómica |
| `overrides.jsonl` | o editor acrescenta uma linha | **falha possível**: `latest_arestas` lia uma última linha a meio → `JSONDecodeError` | **corrigido**: uma última linha incompleta (sem fim de linha) ainda não existe; uma linha completa partida continua a dar erro |
| `fetch.json` (lido por `piece_png` → `board_pose`, e por `/api/montar`, `/api/fetch`, `/api/cell`) | `run_query` no fim de cada escrita, no próprio sítio | **falha possível**: JSON a meio | **corrigido**: escrita atómica (`fetch.md` também); `fetch_*.jpg` apagados com `remove_file` |
| `render/fit/strips.npz` (não é a composição: o ranking dos buracos e o «verificar» da F2) | o ranking (`_Cache.save`, no próprio sítio) | **falha possível**: leitor sem `close` (no Windows impede a troca) e escrita a meio | **corrigido**: leitura com `with`, escrita atómica, cópia da lista antes de gravar |
| `render/gui/board_60.{jpg,json}` | `_base` (sob `rlock`); apagados por `_drop_stale_caches` | seguro na leitura; o apagar podia rebentar como o `render/clean` | `remove_file` |
| arte (`images/puzzles/…`), `log.jsonl` (`os.stat`) | ninguém / só acrescenta | seguro | igual |
| qualquer ficheiro trocado por `write_atomic` (visto com `render/placements.json`) | a escrita, no instante do `os.replace` | **falhou no teste** (com o «verificar» da F2 no ciclo, 1 em 10 corridas): no Windows o ficheiro antigo fica «delete pending» e abri-lo dá `PermissionError [Errno 13]` | **corrigido**: `state.read_retry` (até 25 × 20 ms) em `load_placements`, `crop_rgba`, `Project.shape` / `contour_px`, `load_fetch` e nas tiras; 20/20 depois |

**Teste de esforço** (`tests/test_concorrencia.py`, `slow`, ≈ 10 s): projeto sintético; 4 fios compõem em ciclo
(tabuleiro inteiro, regiões com e sem LRU, zoom 3 × 3, miniaturas), 1 pede regiões por HTTP e 1 deixa `render/clean`
velhos, enquanto o fio principal faz 12 voltas de colocar 2 peças, re-segmentar a peça colocada pelo editor do
contorno e tirar as 2. No fim: 0 exceções nos fios, invariantes e replay no disco, e o que o servidor serve para a
versão final (regiões, zoom, miniatura byte a byte; o tabuleiro inteiro em memória até às costuras dos remendos, medidas
sem fios: ≤ 4 níveis em ≤ 5 píxeis) igual a um servidor acabado de abrir.

| código | corridas | resultado |
|---|---|---|
| HEAD `6399e31`, sem as correções | 22 | 1 passou; `PermissionError` em `_drop_stale_caches` 11×, `UnidentifiedImageError` (recorte a meio) 7×, `PermissionError` em `save_placements` 1×, e 2× um 404 por `FileNotFoundError` num `render/clean` (pedido HTTP) cuja origem não encontrei: não voltou em mais 30 corridas instrumentadas [F] |
| HEAD com o `_clean_or_crop` de antes de `6399e31` (o resto corrigido) | 5 | 5 falham com `FileNotFoundError` (o erro da ronda 2) [V: o teste apanha esta classe] |
| este commit | 20 + as da suite | 20/20 sem erros [V] |

Fora da composição, o «verificar» da F2 corre também sem o bloqueio de escrita: aplica-se-lhe a mesma regra (lê o
projeto por `Gui.read`, tem um bloqueio e uma cache de tiras próprios, e recomeça uma vez se uma escrita mudou o
tabuleiro a meio); entra no teste de esforço com a F2.

## 9. F2 (2026-11-14): tempo do «verificar» e custo do ajuste de cor no tabuleiro

### 9.1 «verificar» de «Pôr uma peça à mão» (plano da F2 §6 j) [V]

`tools/diagnostico/gui/verificar_tempo.py` (`dados/r3_f2_verificar.json`): cópia nova de `projects/alpes` por cenário,
servidor real (0,5 ms), `POST /api/cell/1/29/verificar` com Saco 9 · nº 89 (P1422), 2 repetições.

| cenário | 1.º pedido, sem θ (as 4 rotações), HTTP (s) | seguintes, com θ (s) |
|---|---|---|
| servidor parado, processo novo | 0,66 · 0,62 | 0,002–0,025 |
| durante o ranking dos buracos a frio (logo depois de `/api/montar`) | 4,46 · 3,20 | 0,012–0,050 |

- O 1.º pedido lê as tiras de `render/fit/strips.npz` e calcula os lados erodidos das 3 vizinhas e da peça; os
  seguintes reaproveitam a cache própria do «verificar».
- Parado fica abaixo dos 2 s do plano. Durante o ranking a frio passa (3,2–4,5 s: o ranking divide o processo, como no
  §6); a regra «não bloqueia» cumpre-se (as linhas dizem «a verificar…» e «Pôr aqui» está ativo, teste
  `test_por_mao_non_blocking_rodar_and_undo`). O que o encurta é o §7 (lados em disco), fora da F2.
- No guião (`F2_guiao.json`, no browser, depois do ranking): 0,17–0,19 s o 1.º, 0,02–0,07 s cada «Rodar».
- O resultado: na rotação −171° lado liso, forma e imagem com 3 traços; nas outras 3 o lado liso e a forma falham e a
  imagem fica «não verificado» [V no programa; o encaixe físico é NT, passo 8 do guião].

### 9.2 Ajuste de cor (filtro CSS) no tabuleiro [V em Chromium headless]

`tools/diagnostico/gui/f2_filtro.py` (`dados/r3_f2_filtro.json`): GUI nova sobre uma cópia, tabuleiro aproximado
(linhas 10–24, colunas 18–42), 3 voltas alternadas filtro ligado (brilho 0,92) / desligado, 3 s a arrastar
(60 movimentos) e 12 voltas da roda, com trace do Chromium.

| tamanho | gesto | frames (desl. / lig.) | frames perdidos | pintura e rasterização no gesto, ms (desl. → lig.) | maior tarefa (ms) | long tasks |
|---|---|---|---|---|---|---|
| 1366 × 768 | arrastar | 320–323 / 319–320 | 0 / 0 | 161–168 → 271–285 (+68 %) | 0,5 / 0,8 | 0 |
| 1366 × 768 | roda | 134–137 / 133–137 | 0 / 0 | 29–32 → 50–54 (+70 %) | 0,7 / 0,6 | 0 |
| 390 × 844 × 3 | arrastar | 317–322 / 320–321 | 0 / 0 | 43–58 → 58–62 (+20 %) | 0,7 / 0,5 | 0 |
| 390 × 844 × 3 | roda | 137–138 / 136–139 | 0 / 0 | 9–11 → 12–13 (+22 %) | 0,7 / 0,5 | 0 |

- O filtro custa ≈ 0,4 ms por frame a 1366 (de ≈ 0,5 para ≈ 0,9 ms, num orçamento de 16,7 ms); o batimento do
  `requestAnimationFrame` fica igual (16,7 ms, p95 16,8) e não se perde nenhum frame.
- **Decisão: fica também no tabuleiro.** Limite: Chromium headless rasteriza em software nesta máquina; GPU real,
  Firefox/Safari e o telemóvel ficam [NT].

## 10. Limites

- Medido em Chromium headless numa máquina, sem rede real (localhost). Firefox, telemóvel e `--lan` ficam [NT]. O
  «deixou de responder» do Tiago não foi reproduzido como bloqueio do fio do browser: aqui o fio nunca bloqueou. A
  hipótese mais forte para o relato é o arranque (ranking a frio), mas é [NT] na máquina dele.
- A decomposição em fases (§1) soma o tempo dentro das funções embrulhadas e foi medida com o código de HEAD; o «resto»
  é a alocação e a mistura em float32 de `compose_board`.
- A medição pré-F1 (worktree `8fedf87^`) precisou de tirar 1 evento `rejection_undone` da cópia do log (ação que esse
  código não conhece). O tabuleiro e as peças colocadas ficaram iguais.
- «arranque» varia entre corridas (29,96 / 31,50 / 34,16 s antes; 32,07 / 32,70 s depois), conforme o salto cai mais
  cedo ou mais tarde no ranking.
- Ronda 2: o intervalo do GIL foi medido nesta máquina (Windows 11, `.venv`) e só no servidor; a máquina do Tiago e
  `--lan` ficam [NT]. As medidas de reconsulta e importação são de uma escrita e de uma folha de 10 peças por corrida;
  importações grandes (PDF de várias folhas) ficam [NT]. O §7 é uma análise com estimativas [NT] para as opções.
