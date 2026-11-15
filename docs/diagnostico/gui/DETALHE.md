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
- **Pendente: 404 por `FileNotFoundError` num `render/clean` sem origem encontrada.** No teste de esforço
  (`tests/test_concorrencia.py`, §8.2), na HEAD `6399e31` antes das correções do passo 0, 2 das 22 corridas deram um 404
  num pedido HTTP por um `FileNotFoundError` num `render/clean/P####.png`. Não encontrei a origem [F]: não voltou em mais
  30 corridas instrumentadas, nem depois das correções (20/20 sem erros [V]). As causas conhecidas de um `render/clean`
  a desaparecer (re-segmentação que o apaga, leitor que apaga o que julgou velho) estão corrigidas (`state.remove_file`,
  escrita atómica, `_clean_or_crop` que trata um ficheiro desaparecido como velho), por isso não se sabe se o 404 já
  não existe ou só ficou mais raro. Reabrir se voltar a aparecer no teste de esforço (`pytest tests/test_concorrencia.py
  -m slow`) ou no registo do servidor (`projects/alpes/logs/servidor-AAAAMMDD.log`, linhas `erro`/`pedido` com 404 em
  `/api/pieces/…/png` ou `/api/board.jpg`). Onde procurar: o caminho que serve a miniatura/região (`Gui.piece_png`,
  `Gui._region_jpg`) e quem lê `render/clean` (`render._clean_or_crop`, `render.piece_rgba_for_display`) entre o
  `exists` e a leitura, e quem apaga (`Gui._drop_stale_caches`, `rebuild_assets`); instrumentar com o traceback do 404.

## 11. Fase de desempenho (2026-11-15): P0, P0b e P1

Plano aprovado: «Fase de desempenho (antes da F4)», com as decisões e os acrescentos do Tiago de 2026-11-15. Duas linhas
do plano antigo mudam com os acrescentos: o POST de um «Encaixa» deixa de estar «fora do plano» e passa a ser o **P0b**
(critério ≤ 2,0 s); a ordem dos blocos é **P0 → P0b → P1a/P1b → 1a → 1b+1c → 1d → E → C**, um commit por bloco
(P0+P0b+P1, parte 1, E, C).

Guião: `tools/diagnostico/gui/desempenho.py` (promovido de `t0/baseline.py`): cópia `shutil.copytree` nova por corrida,
servidor real (GIL 0,5 ms), Chromium 1920 × 1080, 2 corridas; `--repo` corre o servidor de outro checkout (bisect em
`git worktree`), `--so p|q` cronometra o POST por fase (`fases_post.py`: embrulhos só no fio de `Gui.confirm`), `--so r`
grava as capturas (`capturas/desempenho_{ceu,relva}_antes.jpg`, região a ppc 100). Base: cópia de `projects/alpes`
(1433 peças, 699 colocadas, versão do log 2307663).

### 11.1 Os 5 critérios, «hoje» (9f672c0) [V]

`dados/r4_base_9f672c0.json` (servidor do worktree de 9f672c0, a mesma cópia de partida):

| # | critério | alvo | hoje (9f672c0), 2 corridas | depois de P0+P1 |
|---|---|---|---|---|
| 1 | 1.º salto depois de abrir (céu) | ≤ 4,0 s | 14,07 · 13,76 s | igual (P0/P1 não mexem no servidor) |
| 2 | salto a frio, relva (browser) / HTTP céu·relva | ≤ 2,0 s browser | 4,09 · 3,79 s / 3,62–3,83 s | igual |
| 3 | detalhe depois de um «Encaixa», perto / longe | ≤ 1,2 / ≤ 0,6 s | 3,34 · 3,30 / 4,09 · 3,60 s (POST 5,77–7,63 s) | igual |
| 4 | 1.º «verificar» logo após o arranque | ≤ 1,0 s | 2,17 · 1,56 s | igual |
| 5 | pico do working set do servidor | ≤ 1,6 GB | 738 · 733 MB (privada 1,23 GB) | igual |

P0 e P1 só mudam o browser (`novo.js`, `board.js`, `novo.css`) e os testes: a coluna «depois» não foi medida de novo,
porque nenhum dos 5 critérios passa por código alterado no servidor (o critério 3 mede com a vista fixa no separador
Peças, onde `drawTarget` não corre).

### 11.2 P0: a vista não salta sozinha; testes estáveis [V]

- `src/web/novo/novo.js`: `followTarget` (chave `peça@célula` em `S.alvoMostrado`): a vista segue o cartão na 1.ª carga
  e com `S.alvoAcao` (Encaixa / Não encaixa / Colocar aqui / Saltar / «A seguir» / toque num alvo / lupa / Desfazer);
  um cartão que muda sozinho não mexe na vista e, com o lugar fora dela, `#b-localizar` ganha `data-mudou="pisca"`
  (animação `loc-pisca`, uma vez) ou, com `prefers-reduced-motion`, `data-mudou="marca"` + classe `mudou` até ao próximo
  clique ou ação; o mesmo cartão numa recarga não mexe em nada. `cellInView` (a regra de `showCell`).
- `src/web/board.js`: `S.gesto` (entre o 1.º `pointerdown` e o último `pointerup`/`pointercancel`) e `S.saltoPendente`: um
  `zoomCells` durante um gesto faz-se no fim dele.
- Testes novos `tests/test_gui_novo_p0.py` (Playwright, `slow`): recarga por `holes_changed`/`fetch_changed` sem ação →
  vista igual e 0 pedidos; recarga a meio de um arrasto → o pedido só ≥ 250 ms depois do último movimento; salto durante
  o gesto espera pelo `pointerup`; «Saltar» e «Encaixa» movem a vista; cartão que muda sozinho: pisca com o lugar fora,
  nada com ele dentro, marca estática sem animação com `reduced_motion`. Com o `novo.js` de 9f672c0, 8 dos 15 falham
  (os 3 da recarga incluídos).
- Fila: `test_failed_job_does_not_block_and_move` com um portão (`threading.Event`) em vez do `sleep(0.8)`;
  `tests/conftest.py` com um fixture `autouse` que para (`gui.stop()`) cada `Gui` criada pelo teste (antes ficavam ~116
  fios `fila-importacao` vivos na suite).
- Repetição dos dois testes que falhavam ao acaso (`test_jump_asks_detail_at_once_drag_and_wheel_keep_debounce`, sem
  alteração, e `test_failed_job_does_not_block_and_move`): ver 11.5.

### 11.3 P0b: o POST de um «Encaixa» [V] — não é uma regressão de código

Protocolo de §6.2 (P0096 → (20,60), `place` + `unplace` com `desfaz`, buracos acabados, 3 voltas), a mesma cópia em
todos os commits, servidor de cada `git worktree` (`dados/r4_p0b_fases.json`):

| commit | place, s (1.ª / seguintes) | unplace, s |
|---|---|---|
| 6399e31 (§6.2) | 5,99 / 5,36–5,46 | 4,84–4,94 |
| 6345154 | 5,92 / 5,17–5,34 | 4,95–5,07 |
| 32c5f5c | 6,37 / 5,62–5,83 | 5,01–5,15 |
| c0741af | 6,87 / 5,38–5,95 | 4,95–5,68 |
| 9f672c0 | 6,74 / 5,28 | 4,99–5,02 |
| 9f672c0 com `/novo/` aberto no céu | 7,44 / 6,44–6,76 | 6,19–6,33 |

- Os 5 commits dão o mesmo (dentro do ruído): **nenhum commit culpado**. Os 4,4 s de §6.2 eram de outra cópia (versão do
  log 2299530, menos peças colocadas): o resto é **crescimento dos dados** (H2) e, com a GUI aberta, a recarga do browser
  a competir pelo GIL com o fim do POST (H1: as suspeitas passam de 1,6 para 2,6–3,6 s).
- Por fase, 9f672c0, place (voltas 2–3) sem browser / com browser (s):

| fase | sem browser | com browser |
|---|---|---|
| `src.confirm.confirm` (log + `Project.save` + invariantes + reconsulta incremental) | 3,51 | 3,50–3,89 |
| · `Project.save` (2 ×, 144 ficheiros JSON reescritos em cada uma) | 0,69–0,73 | 0,66–0,79 |
| · `check_invariants` (replay do log) | 0,24–0,25 | 0,23–0,39 |
| · `run_query` incremental | 2,91–2,92 | 2,92–3,06 |
| `_refresh_render_assets` (limpar + registar a peça) | 0,14 | 0,13–0,30 |
| `_emit_suspeitas` (`consistency.evaluate`, 699 colocadas) | 1,62 | 2,57–3,63 |
| `holes_json(wait=False)`, `_written_since`, `board_snapshot` × 3 | < 0,01 | < 0,01 |
| **total** | **5,28** | **6,44–7,44** |

- Perfil (cProfile em processo, com sobrecarga): dentro da reconsulta, ≈ 1,0 s a reler 524 recortes (`crop_rgba`: um
  `_Ctx` novo por consulta relê as peças do passo das gémeas) e ≈ 0,9 s a reescrever `fetch.*` (≈ 0,5 s a medir texto
  com `ImageFont.getlength` para as folhas `fetch_<lote>.jpg`); nas suspeitas, 1,27 dos 1,66 s em `twin_local_residual`
  (o grau «recorte» recalculado para as 613 peças com gémea em cada escrita).

**Opções para chegar a ≤ 2,0 s (nenhuma implementada; paragem obrigatória: decisão do Tiago):**

| opção | o que faz | muda o comportamento? | ganho estimado [NT] |
|---|---|---|---|
| A1 | `Project.save` só reescreve os JSON que mudaram | não (mesmos ficheiros) | −0,6 s |
| A2 | recortes em cache entre consultas (chave: tamanho + mtime do ficheiro) | não | −0,9 s |
| A3 | medidas de texto das folhas `fetch_*.jpg` em cache; só refazer a folha do saco que mudou | não | −0,4 a −0,8 s |
| A4 | `twin_local_residual` em cache por peça (chave: formas, poses e células das duas gémeas) | não | −1,2 s |
| B | as suspeitas (`_emit_suspeitas`) num fio depois da resposta | sim: o painel «Suspeitas» e o SSE `suspeitas_changed` chegam depois da resposta | −1,6 s (−2,6 a −3,6 s com a GUI aberta) |
| C | responder logo depois de gravar no log; a reconsulta e o resto em segundo plano | sim: o Montar pode mostrar a lista antiga por 3–5 s | POST ≈ 0,4 s |

Só A1–A4 (sem mudar o comportamento) dariam ≈ 5,3 → ≈ 1,6–2,3 s sem browser e ≈ 2,5–3,5 s com a GUI aberta (a
competição do browser fica); ≤ 2,0 s com a GUI aberta exige B ou C. A1–A4 também não são «corrigir uma regressão»: são
otimizações novas em `state`, `query` e `consistency`, fora do plano aprovado. **Parei aqui, como o plano manda**; a
parte 1 (1a, 1b+1c, 1d) e E estão escritas e por medir num ramo à parte (ver `docs/HANDOFF.md`).

### 11.4 P1a e P1b [V em Chromium headless; NT no telemóvel]

- **P1a:** `saltoLupa` (`findPiece`/`findPlace`): tira o foco da caixa, salta 2 frames depois e, se o tabuleiro tiver
  < 40 % da altura normal (`S.boardRefH`, a altura sem nada a escrever), refaz o salto (forçado) no redimensionar
  seguinte, até 2 s. Medido: 390 × 844 → teclado 390 × 330 (tabuleiro 264 → 69 px) → fecha: `S.vb.w` 18 (o limite,
  3 × o tabuleiro sintético) → 6,18, igual ao salto sem teclado. Teste
  `test_lupa_jump_at_390_with_keyboard_ends_around_the_place`.
- **P1b:** nenhuma caixa da lupa aberta nem com foco depois de carregar, a 1366 e a 390, sem modo guardado e com «pos» /
  «peca» (`test_lupa_box_never_opens_by_itself`, 6 casos; já passavam em 9f672c0). Linha em `docs/decisoes.md`.

### 11.5 Verificação do bloco P0 + P0b + P1 [V]

- `test_jump_asks_detail_at_once_drag_and_wheel_keep_debounce` (sem alteração) e `test_failed_job_does_not_block_and_move`:
  20/20 corridas seguidas, as duas juntas.
- `tests/test_concorrencia.py`: 20/20.
- Suite `.venv/Scripts/python.exe -m pytest tests/` (614 s): 579 passed, 1 skipped (PyMuPDF real), 1 failed:
  `test_board_interface.py::test_board_js_runs_with_only_the_declared_interface`, porque os campos novos que o
  `board.js` escreve (`gesto`, `saltoPendente`) não estavam na lista `OWNED`. Acrescentados; esse ficheiro passa (2
  passed). A suite inteira não foi repetida depois desta mudança (só de teste).
- Testes existentes alterados: `tests/test_server_queue.py` (portão), `tests/conftest.py` (fixture `autouse`),
  `tests/test_board_interface.py` (`OWNED`).

### 11.6 P0b implementado: A1–A4 + B (decisão do Tiago, 2026-11-15) [V]

Decisão: A1–A4 e B; C (responder antes da reconsulta) não. O que mudou:

- **A1** `src/state.py` `Project._write_json`: uma vista JSON só se reescreve quando o conteúdo (JSON compacto do
  codificador em C, a mesma estrutura dá o mesmo ficheiro indentado) é outro, ou o ficheiro no disco já não é o que este
  objeto escreveu (tamanho + mtime). `save` agrupa as peças por folha uma vez.
- **A2** `Project.crop_rgba`: recortes decodificados em cache entre consultas (LRU de 128 MB, `CROP_CACHE_BYTES`, chave =
  tamanho + mtime do ficheiro do recorte; devolve uma cópia); `src/query.py`: os `TwinItem` leem o recorte só quando o
  usam (`_lazy_item_cls`), em vez de ler os ≈ 500 recortes de cada consulta.
- **A3** `src/query.py`: `_textlen` memoriza as medidas de texto das folhas; `write_fetch` só redesenha a folha
  `fetch_<lote>.jpg` cuja assinatura (`_sheet_sig`: as linhas, e por peça e gémea `render.piece_asset_sig`, estado, pose
  e o registo em `placements.json`) mudou; apaga só as folhas de sacos que saíram da lista.
- **A4** `src/consistency.py`: `twin_local_residual_cached` (chave = sha1 do `z` das duas formas; o limiar
  `TWIN_LOCAL_MAX_MM` aplica-se depois, por isso uma mudança de calibração vale logo).
- **B** `src/server.py` `_suspeitas_bg`: depois de uma escrita as suspeitas calculam-se num fio («suspeitas») depois da
  resposta, com as escritas seguintes juntas numa só passagem; o painel e o SSE `suspeitas_changed` chegam depois.
  `wait_suspeitas()` para os testes. As outras escritas que devolvem o resumo (falso alarme, reports) ficam síncronas.
- `render.piece_asset_sig` / `display_params` (da parte 1c) entram já aqui, para a assinatura das folhas.

**Iguais antes/depois [V]** (`tools/diagnostico/gui/p0b_iguais.py`, `dados/r4_p0b_iguais_{antes,depois}.json`): a mesma
sequência de 5 escritas (P0096 → (20,60), desfazer, → (5,33), desfazer, P0097 → (20,60)) numa cópia nova com o código de
825c6eb e com este: as entradas devolvidas pela reconsulta, `fetch.json` (sem `t`), `fetch.md` (sem a hora), o sha1 de
cada `fetch_*.jpg`, o sha1 de cada vista JSON (`project`, `board`, `scans/`, `sections/`, `pairs`, `photos/`) e
`consistency.evaluate` são iguais nos 5 passos («IGUAIS 5 passos»).

**POST de um «Encaixa» [V]** (`desempenho.py --so pq`, `dados/r4_p0b_depois.json`; critério ≤ 2,0 s):

| | place (1.ª / 2.ª / 3.ª) | unplace | antes (9f672c0) |
|---|---|---|---|
| sem browser | 1,70 / 0,67 / 0,67 s | 0,46–0,61 s | 6,74 / 5,28 / 5,28 · 4,99–5,02 s |
| com `/novo/` aberto | 1,70 / 1,01 / 1,27 s | 0,82–1,04 s | 7,44 / 6,76 / 6,44 · 6,19–6,33 s |

Por fase (place, voltas 2–3, sem / com browser): `confirm` 0,56 / 0,84–1,11 s (`save` 0,10 / 0,17–0,22,
`check_invariants` 0,14–0,16 / 0,22–0,33, `run_query` 0,35 / 0,52–0,66), `_refresh_render_assets` 0,10 / 0,15 s,
suspeitas 0 s no POST. A 1.ª escrita depois de abrir é a mais lenta (1,70 s): grava todas as vistas uma vez (147
ficheiros) e lê os recortes que a consulta usa. **Critério cumprido nas duas condições.**

Testes: `tests/test_recorte_refaz.py` (novo: cada cache de P0b segue o recorte corrigido pelo editor e fica igual a um
processo novo; as outras peças não são relidas; o limiar das suspeitas vale sem limpar a cache), `tests/test_concorrencia.py`
(um ramo novo lê recortes e suspeitas a meio das re-segmentações; no fim, iguais a um processo novo).

**Os 5 critérios depois do P0b [V]** (`dados/r4_criterios_p0b.json`, 2 corridas):

| # | critério | alvo | 9f672c0 | depois do P0b |
|---|---|---|---|---|
| 1 | 1.º salto depois de abrir | ≤ 4,0 s | 14,07 · 13,76 s | 10,11 · 10,95 s |
| 2 | salto a frio, relva browser / HTTP | ≤ 2,0 s browser | 4,09 · 3,79 / 3,62–3,83 s | 3,13 · 3,20 / 2,84–3,00 s |
| 3 | detalhe depois de um «Encaixa», perto / longe (do fim do POST) | ≤ 1,2 / ≤ 0,6 s | 3,34 · 3,30 / 4,09 · 3,60 s | 6,89 · 7,83 / 5,67 · 5,51 s |
| | POST desse «Encaixa» (perto / longe) | | 7,63 · 6,18 / 7,04 · 5,77 s | 1,57 · 1,66 / 0,86 · 0,89 s |
| 4 | 1.º «verificar» | ≤ 1,0 s | 2,17 · 1,56 s | 1,93 · 2,29 s |
| 5 | pico do working set | ≤ 1,6 GB | 738 · 733 MB | 551 · 552 MB |

O critério 3 mede do fim do POST ao detalhe novo: com B, o trabalho que o POST fazia antes de responder (as suspeitas,
1,6–3,6 s) passa a correr depois da resposta, ao mesmo tempo que a composição do detalhe e o ranking dos buracos; o tempo
do clique ao detalhe desceu (perto 7,63 + 3,34 = 10,97 → 1,57 + 6,89 = 8,46 s; longe 7,04 + 4,09 = 11,13 → 0,86 + 5,67 =
6,53 s), mas o «depois do POST» subiu. O critério 3 é o alvo de C (mosaicos), não do P0b. Verificação: suite 586
passed, 1 skipped, 0 failed; `test_concorrencia` 20/20.

### 11.7 Parte 1: formas por folha, lados em disco, chave das tiras, ranking ao arrancar [V] — critérios 1 e 4 [F]: paragem

O que mudou (escrito no ramo `wip/desempenho-parte1`, testado e medido antes de entrar em `main`):

- **1a** `src/state.py` `Project.shape`: na 1.ª falha de uma folha lê o `pieces/<scan>.npz` uma vez e guarda as formas de
  todas as peças dela (sem `contour_px`/`mask`); as gerações lidas antes de abrir o ficheiro (uma `forget_shape` a meio
  não volta à cache); arrays por gravar (`_pending_arrays`) continuam a ganhar.
- **1b** `src/fit.py` `SidesStore`: lados erodidos partilhados por todos os `_Cache` do projeto (ranking, «verificar»,
  validação cruzada da reconsulta) e em disco (`render/fit/sides.npz`, `write_atomic` / `read_retry`); chave `side_key` =
  sha1 do contorno e dos cantos da forma + `erosion_mm`, `ERODE_SMOOTH_SIGMA`, `N_SIDE`, `FIT_VERSION`, sha1 do
  `puzzle.json`. `_Cache.shape` passa a ser `Project.shape`.
- **1c** chave das tiras `strip_key` = `render.piece_asset_sig` (bbox, ficheiro do recorte, aresta pintada, mm/px da folha,
  fundo) + `render.display_params()` + `BAND_MM`, `N_STRIP`, `HALF_WIN` + sha1 do `puzzle.json`; `rebind` compara a
  chave. Formato antigo (`bbox__P`) **convertido uma vez** quando a bbox é a mesma, o recorte não é mais novo do que o
  ficheiro e a peça não tem aresta pintada; os outros medem-se de novo.
- **1d** `src/server.py` `_prepare`: o ranking dos buracos arranca em segundo plano no fim (depois do tabuleiro e dos
  fantasmas); o «n de N» do progresso soma tiras e lados por calcular (`sides_todo`).

**Achado (1c) [V]:** na cópia, 23 das 825 tiras de `strips.npz` eram velhas — todas de peças com **aresta pintada** (a
chave antiga, id + bbox, não a via); as outras 802 são iguais às medidas de novo, bit a bit.

**Ranking igual [V]** (`tools/diagnostico/gui/rank_iguais.py`, `dados/r4_p1_rank_*.json`): o código antigo (825c6eb)
com todas as tiras medidas de novo e o novo (802 tiras convertidas + 16 medidas) dão o mesmo `rank_all` (203 buracos,
JSON igual sem o campo `tiras`), a frio e numa 2.ª corrida com os lados lidos do disco. Contra o código antigo com o
`strips.npz` antigo, 21 de 203 buracos mudam o custo das candidatas: são as tiras velhas das 23 peças com aresta.
Tempo de `rank_all` sozinho na cópia: 1.º arranque depois de atualizar 41,8 s (calcula e grava os 738 lados), seguintes
5,9 s (antes 33–46 s em todos os arranques); no servidor 4,2–5,1 s.

A partir daqui as medições usam uma base com `sides.npz` e o `strips.npz` já convertido (o estado depois do 1.º
arranque), porque cada corrida copia a base de novo.

| # | critério | alvo | 9f672c0 | P0b | parte 1 |
|---|---|---|---|---|---|
| 1 | 1.º salto depois de abrir | ≤ 4,0 s | 14,07 · 13,76 | 10,11 · 10,95 | **7,75 · 7,38 [F]** |
| 2 | salto a frio, relva browser / HTTP | ≤ 2,0 s browser | 4,09 · 3,79 / 3,62–3,83 | 3,13 · 3,20 / 2,84–3,00 | 3,01 · 3,05 / 2,83–2,95 |
| 3 | detalhe depois de um «Encaixa», perto / longe | ≤ 1,2 / ≤ 0,6 s | 3,34 · 3,30 / 4,09 · 3,60 | 6,89 · 7,83 / 5,67 · 5,51 | 7,59 · 7,63 / 5,38 · 5,57 |
| 4 | 1.º «verificar» | ≤ 1,0 s | 2,17 · 1,56 | 1,93 · 2,29 | **1,42 · 1,10 [F]** |
| 5 | pico do working set | ≤ 1,6 GB | 738 · 733 MB | 551 · 552 MB | 549 · 550 MB |

(`dados/r4_criterios_p1.json`.) Suite 596 passed, 1 skipped, 0 failed; `test_concorrencia` 20/20 (com um ramo novo:
ranking com os lados partilhados e formas por folha a meio das re-segmentações; no fim formas, lados e tiras iguais a um
processo novo). `tests/test_desempenho_cache.py` (novo, 8) e `tests/test_recorte_refaz.py` (+2: formas, lados e tiras
seguem o recorte corrigido; mudar a erosão em `puzzle.json` refaz lados e tiras).

**Porque falham 1 e 4 (do registo do servidor):** o ranking já não é o problema (4,2–4,8 s em vez de 30 s), mas não é
zero e corre ao mesmo tempo que o que se mede:
- critério 1: ao abrir `/novo/`, o browser pede **duas** regiões frias ao mesmo tempo (a do cartão, 31,1–45,19: 3,9 s; e a
  do salto ao céu: 7,7 s), com o ranking a correr. Uma região fria sozinha custa ≈ 3 s (critério 2): o critério 1 fica
  preso ao custo da composição a frio, que é o alvo de E;
- critério 4: o 1.º «verificar» (0,6 s sozinho, §9.1) sai 1 s depois de `/api/montar`, a meio do ranking (4,2 s):
  1,1–1,4 s.

**Paragem obrigatória** (critério de sucesso falha depois da parte que o devia cumprir). E e C não começaram em `main`;
o código de E (`render.piece_ready`, `compose_board(ready=)`) continua no ramo `wip/desempenho-parte1` e a cache do
servidor está escrita mas não aplicada. Opções para o Tiago: (a) seguir para E (ataca a composição a frio, o que
domina o critério 1; o critério 4 só desce se o «verificar» não competir com o ranking); (b) baixar a prioridade do
ranking ao arrancar (adiá-lo até a GUI estar parada alguns segundos, ou pausá-lo durante um pedido de detalhe /
«verificar»); (c) aceitar 1 e 4 como estão.

### 11.8 E: peças prontas a desenhar em memória [V] (decisão do Tiago: E, depois (b) alargada, depois C)

- `src/render.py` `piece_ready(project, pid)` → `(rgba, ext, pad, mmpp, origem)`: a parte de desenhar uma peça que não
  depende da pose (recorte limpo, orla de sombra e bolsas de papel tiradas, sangria); `compose_board(..., ready=)` passa
  sempre por ela (com ou sem cache), por isso o resultado é o mesmo; `ready_nbytes`.
- `src/server.py` `ReadyCache`: LRU por bytes (`--cache-pecas-mb`, omissão 600), cálculo fora do lock, um por peça em
  voo, arrays só de leitura; chave = `render.piece_asset_sig` (recorte, aresta, mm/px, fundo) + `display_params` + sha1
  do `puzzle.json`; `forget` em `_refresh_render_assets` e no contorno gravado pelo editor, `clear` depois de
  `rebuild_assets` / `rebuild_stale` no arranque. `Gui._prewarm`: depois do ranking do arranque, as colocadas ficam prontas
  (as mais perto da última região pedida primeiro) até 95 % do orçamento (na cópia: 500 peças em 8,6 s, 512 MB).
  `/api/status` traz `cache_pecas`.

**Igual byte a byte [V]** (`tools/diagnostico/gui/e_iguais.py`, `dados/r4_e_iguais_*.json`): céu (1,20–14,40) e relva
(34,30–47,50) a ppc 100 e o tabuleiro inteiro a ppc 60 na cópia, com o código de antes de E e com o novo sem cache, com a
cache fria, quente e com orçamento de 1 MB: 12 composições, o mesmo sha1 dos píxeis. Tempo (céu / relva a ppc 100):
sem cache 2,81 / 2,28 s, cache fria 2,26 / 2,17, **quente 0,84 / 0,72 s**. Testes: `tests/test_ready_cache.py` (novo, 6:
igual com e sem cache a 3 ppc, orçamento minúsculo com expulsões e saída igual, só leitura, um cálculo por peça entre
fios, chave segue o recorte e o `puzzle.json`), `test_recorte_refaz` (+1: a entrada da peça corrigida sai, as outras não
se recalculam, região = processo novo), `test_concorrencia` (orçamento de ~1 peça: expulsões contínuas).

| # | critério | alvo | 9f672c0 | parte 1 | E |
|---|---|---|---|---|---|
| 1 | 1.º salto depois de abrir | ≤ 4,0 s | 14,07 · 13,76 | 7,75 · 7,38 | 4,27 · 4,93 |
| 2 | salto a frio, relva browser / HTTP | ≤ 2,0 s browser | 4,09 · 3,79 / 3,62–3,83 | 3,01 · 3,05 / 2,83–2,95 | 2,90 · 3,00 / 0,81–1,16 |
| 3 | detalhe depois de um «Encaixa», perto / longe | ≤ 1,2 / ≤ 0,6 s | 3,34 · 3,30 / 4,09 · 3,60 | 7,59 · 7,63 / 5,38 · 5,57 | 5,08 · 5,46 / 3,32 · 3,71 |
| 4 | 1.º «verificar» | ≤ 1,0 s | 2,17 · 1,56 | 1,42 · 1,10 | 1,18 · 0,97 |
| 5 | pico do working set | ≤ 1,6 GB | 738 · 733 MB | 549 · 550 MB | 1109 · 1107 MB |

Chegada (novo em `desempenho.py`, ouvinte SSE): sugestões «pelo encaixe» (`holes_changed`) 2,8 · 3,5 s depois do «pronto»;
depois de um «Encaixa» (perto / longe) sugestões 4,9 · 5,3 / 3,0 · 3,4 s e suspeitas 5,4 · 5,9 / 1,6 · 1,9 s.
(`dados/r4_criterios_e.json`.) O salto a frio na relva no browser (2,9–3,0 s) cai durante o pré-aquecimento (8,6 s de CPU,
registo do servidor): o mesmo pedido por HTTP, com as peças já prontas, demora 0,8–1,2 s; é o que (b) trata. Suite 603
passed, 1 skipped; `test_concorrencia` 20/20.

### 11.9 (b) alargada: prioridade à interação [V]

- `src/server.py`: `Gui.foreground()` (contexto à volta da composição de uma região de detalhe e de um «verificar») e
  `Gui.yield_to_gui()`: o trabalho de fundo, entre peças / buracos, espera enquanto houver um desses pedidos em curso
  (no máximo `YIELD_MAX_S` = 30 s por espera, para uma sequência de pedidos não o parar de vez) e continua onde estava
  (nada do que já fez se perde). Cedem: o ranking dos buracos (`fit.rank_all(pause=)`, só quando corre no fio de
  fundo), as suspeitas depois de uma escrita (`consistency.evaluate(pause=)` via `_suspeitas_bg`) e o pré-aquecimento
  das peças. `Gui.yields` conta as cedências; a linha «suspeitas recalculadas depois da escrita (n s)» vai para o registo.
- `src/fit.py` `rank_all(pause=)` e `_Cache.pause` (antes de cada forma, lados, tiras e buraco); `src/consistency.py`
  `evaluate(pause=)` / `_recorte_items(pause=)` (antes de cada peça). Só esperam: o resultado não muda.

**Igual, só mais tarde [V]:** `tests/test_ceder.py` (novo, 6): `rank_all` e `evaluate` com cedências forçadas (pausas
aleatórias) = sem cedências (JSON igual); o ranking e as suspeitas de fundo esperam enquanto um pedido está em curso e
acabam iguais a um processo novo; `yield_to_gui` sem pedidos não custa nada (1000 chamadas < 50 ms); pedidos encaixados
contados. `test_concorrencia` (o ranking relançado em cada volta, a ceder às regiões compostas pelos fios; no fim igual
ao de um processo novo): 20/20.

| # | critério | alvo | E (antes de (b)) | depois de (b) |
|---|---|---|---|---|
| 1 | 1.º salto depois de abrir | ≤ 4,0 s | 4,27 · 4,93 | 4,41 · 3,76 |
| 2 | salto a frio, relva browser / HTTP | ≤ 2,0 s browser | 2,90 · 3,00 / 0,81–1,16 | 2,28 · 2,15 / 0,78–1,08 |
| 3 | detalhe depois de um «Encaixa», perto / longe | ≤ 1,2 / ≤ 0,6 s | 5,08 · 5,46 / 3,32 · 3,71 | 3,41 · 3,26 / 2,72 · 2,71 |
| 4 | 1.º «verificar» | ≤ 1,0 s | 1,18 · 0,97 | **0,21 · 0,21** |
| 5 | pico do working set | ≤ 1,6 GB | 1109 · 1107 MB | 1106 · 1107 MB |

Quanto atrasa a chegada (ouvinte SSE em `desempenho.py`, `dados/r4_criterios_b.json`):

| | E | (b) |
|---|---|---|
| sugestões «pelo encaixe» (`holes_changed`) depois do «pronto» | 2,8 · 3,5 s | 6,1 · 5,9 s |
| sugestões depois de um «Encaixa», perto / longe | 4,9 · 5,3 / 3,0 · 3,4 s | 4,9 · 4,7 / 3,4 · 3,4 s |
| suspeitas (`suspeitas_changed`) depois de um «Encaixa», perto / longe | 5,4 · 5,9 / 1,6 · 1,9 s | 5,1 · 4,9 / 1,5 · 1,5 s |

No arranque as sugestões chegam ≈ 3 s mais tarde (o ranking cede ao 1.º salto e à região do cartão: 6,6 s em vez de
3,3 s no registo); depois de uma escrita ficam iguais (± 0,5 s). O pré-aquecimento também cede (386 peças em 11,2 s).

Teste existente alterado: `tests/test_gui_novo_f2.py::test_phone_layout_panels` media os botões do passo 2 de «Pôr uma
peça à mão» antes de o «verificar» responder e voltar a desenhar o painel (elemento substituído → `bounding_box` None);
falha sozinho também em 9f672c0 (2 em 3) e em 244a1cf (3 em 3) [V]: corrida do teste, não de (b). Agora espera pela
resposta (6/6).

### 11.10 C (mosaicos): condições confirmadas, mas PARADO antes de fundir [V]

O código está no ramo `wip/desempenho-c` (`043435c`, sobre `983ae98`), **não em `main`**:
- `render.compose_board(px_box=)` na grelha global de píxeis (arte por `cv2.remap` com mapas absolutos; cada peça
  deformada na sua caixa inteira em píxeis absolutos e cortada depois), `board_px_size`, `cell_px_box`;
- `server.MosaicCache` (8 × 8 células, LRU por bytes, `--cache-mosaicos-mb` 256), chave por peça a ± 2 células (célula,
  registo, chave da `ReadyCache`), arte e grelha; a região de ppc inteiro cola os mosaicos; a LRU das regiões fica
  válida enquanto as chaves dos mosaicos não mudam;
- `tests/test_mosaicos.py` (10) e `tools/diagnostico/gui/mosaicos_iguais.py`.

**As duas condições do Tiago, confirmadas antes de fundir [V]:**
1. Mosaicos colados = composição única do mesmo `px_box`: metades em x, metades em y, 2 × 2 e os mosaicos de 8 × 8 do
   servidor — **0 píxeis diferentes** no sintético (céu e relva, ppc 60/100/140/217) e na cópia real (céu 1,20–14,40 e
   relva 34,30–47,50, ppc 100 e 240; `dados/r4_c_mosaicos_copia.json`).
2. (a) `compose_board`, as regiões e `render/gui/board_*` só são usados por `src/server.py` e `src/render.py` (e pelo CLI
   `src/artreg.py`, fora do motor); `fit`, `twin`, `query`, `consistency`, `legacy`, `border` e `state`: 0 referências
   (grep; `graphify path compose_board rank_all` só liga por imports genéricos). O caminho sem `px_box` não mudou.
   (b) Na cópia, código de `983ae98` contra o de C: `p0b_iguais.py` «IGUAIS 5 passos» (reconsulta, `fetch.*`, vistas
   JSON, `consistency.evaluate`) e `rank_iguais.py` «IGUAIS» (`rank_all`).

**Porque parei:** a decisão do Tiago para C aceitava a grelha nova «deslocada < 0,5 px na vertical e com ≤ 5 níveis
em ≤ 0,06 % dos píxeis». Medido na cópia (região inteira, código de hoje contra a grelha nova, `y` arredondado para o
deslocamento ser ≤ 0,5 px; com `floor` a relva a ppc 100 ficava deslocada 0,97 px):

| região | píxeis diferentes | máx. níveis | píxeis > 5 níveis |
|---|---|---|---|
| céu, ppc 100 | 0,07 % | 13 | 1 |
| céu, ppc 240 | 0,08 % | 8 | 3 |
| relva, ppc 100 | **24 %** | **33** | 521 |
| relva, ppc 240 | **38 %** | **55** | 857 687 |

No céu (arte lisa) fica perto do que foi aceite; na relva (arte com textura) uma reamostragem com outra fase sub-píxel
(e `remap` em vez de `warpAffine` na arte) muda muitos píxeis em poucos níveis. À vista não se distingue (recorte
ampliado da relva: `capturas/desempenho_relva_depois_C.jpg` contra `desempenho_relva_antes.jpg`; a diferença ×8 são faixas
horizontais ténues), mas excede os números aceites, e os 0,06 % do plano vinham de outra medição (costuras entre regiões
vizinhas, não a região inteira). **Decisão do Tiago:** aceitar esta mudança (ou um limite novo) para C.

Medido também com C (ramo, 2 corridas, `dados/r4_criterios_c_wip.json`), contra (b):

| # | critério | alvo | (b) em `main` | com C (ramo) |
|---|---|---|---|---|
| 1 | 1.º salto depois de abrir | ≤ 4,0 s | 4,41 · 3,76 | 7,18 · 7,66 |
| 2 | salto a frio relva, browser / HTTP | ≤ 2,0 s | 2,28 · 2,15 / 0,78–1,08 | 4,19 · 4,19 / 0,06–0,44 |
| 3 | detalhe depois de um «Encaixa», perto / longe | ≤ 1,2 / ≤ 0,6 s | 3,41 · 3,26 / 2,72 · 2,71 | 2,64 · 3,82 / 2,39 · 2,35 |
| 4 | 1.º «verificar» | ≤ 1,0 s | 0,21 · 0,21 | 0,21 · 0,32 |
| 5 | pico do working set | ≤ 1,6 GB | 1106 · 1107 MB | 1147 · 1148 MB |

Com C, o frio piora (uma região de 21 × 14 células toca até 12 mosaicos de 8 × 8 e compõe ≈ 24 × 16 células), o
quente melhora (0,06–0,44 s por HTTP) e o critério 3 desce pouco: depois de uma escrita longe, o servidor já não
compõe nada (nenhum pedido lento no registo), mas o browser só pede o detalhe depois de recarregar o tabuleiro (350 ms
de espera + `/api/board` + fantasmas + raster): é esse encadeamento, não a composição, que fica nos 2,4 s. **C2 não
medido** (depende de C).

### 11.11 Estado final dos critérios (código em `main`, `983ae98`) — o que fica [F]

| # | critério | alvo | 9f672c0 | `main` (E + (b)) | |
|---|---|---|---|---|---|
| 1 | 1.º salto depois de abrir | ≤ 4,0 s | 14,07 · 13,76 | 4,41 · 3,76 | **[F]** numa das 2 corridas |
| 2 | salto a frio relva, browser | ≤ 2,0 s | 4,09 · 3,79 | 2,28 · 2,15 | **[F]** |
| 3 | detalhe depois de um «Encaixa», perto / longe | ≤ 1,2 / ≤ 0,6 s | 3,34 · 3,30 / 4,09 · 3,60 | 3,41 · 3,26 / 2,72 · 2,71 | **[F]** (o alvo era de C) |
| 4 | 1.º «verificar» | ≤ 1,0 s | 2,17 · 1,56 | 0,21 · 0,21 | [V] |
| 5 | pico do working set | ≤ 1,6 GB | 738 · 733 MB | 1106 · 1107 MB | [V] |
| — | POST de um «Encaixa» (P0b) | ≤ 2,0 s | 5,3–7,4 | 0,6–1,8 | [V] |

Capturas antes / depois (região a ppc 100 do servidor, cópia): `capturas/desempenho_{ceu,relva}_antes.jpg` e
`..._depois_E_b.jpg` são **iguais byte a byte** (E e (b) não mudam a composição); `..._depois_C.jpg` = o ramo de C.

### 11.12 Verificação final e uma corrida encontrada no fim [V]

- `test_concorrencia` no fim deu **19/20**. Capturada a falha (1 em 45 corridas): `consistency.evaluate`, chamada fora do
  bloqueio de escrita (desde o P0b B, e no `GET /api/suspeitas` já antes), lia `celula` de uma peça que uma escrita
  tirava do tabuleiro a meio (`TypeError: 'NoneType' object is not subscriptable` em `twin_exception`). No servidor o fio
  das suspeitas apanhava o erro e as suspeitas ficavam por recalcular até à escrita seguinte. Correção
  (`Gui.suspeitas_json`): com um `TypeError`/`KeyError`/`AttributeError`, espera que a escrita acabe e avalia outra vez
  (até 3 vezes; sem uma escrita pelo meio, o erro sobe). Depois: 40/40 corridas.
- Suite completa com o `.venv` (incl. slow): antes desta correção 609 passed, 1 skipped, 0 failed; depois dela 609
  passed, 1 skipped, 0 failed.
- **Adenda (2026-11-15, depois do commit):** 40/40 não prova a correção: com o erro ainda a 1/45, passar 40 seguidas
  tem P ≈ 0,41. Prova determinística (escrita noutro fio dentro do gancho `pause` de `evaluate`, projeto sintético de
  `test_query._project`, 3 posições × 3 escritas) [V]: tirar uma peça do lugar repete e acerta (3/3); re-segmentar
  acerta (3/3); **mover uma peça devolve um resultado rasgado sem exceção** (3/3): `n_com_vizinhas` antes 0, depois 3,
  devolvido 1. A correção só apanha exceções. Corrige-se sozinho (o resultado fica guardado com a versão antiga e a
  passagem seguinte recalcula), mas o painel/SSE pode mostrá-lo uma vez; o `test_concorrencia` não o vê (compara só o
  estado final). Causa: `evaluate` lê o modelo vivo sem bloqueio (tira `ids`/`mounted` no início, lê `celula` e a forma
  em direto) e `Project._emit` aplica cada evento antes de o escrever no log. Fecho proposto (por aprovar): contador
  de escritas que sobe ao tomar e ao largar o `wlock`; um resultado só é aceite se o contador não mudou e é par; senão
  (resultado ou exceção) repete, e à 3.ª vez avalia sob o `wlock`; mais um teste determinístico com o cenário «mover».

## 12. Perfil do critério 3 (2026-11-15, `9d59717`): linha do tempo de um detalhe depois de um «Encaixa» [V]

Sem otimizar. Guião `tools/diagnostico/gui/perfil_c3.py` (protocolo de `desempenho.py --so a`, 5 corridas, cópia nova
e servidor novo em cada uma) com o servidor lançado por `linha_tempo.py` (início/fim de cada fase em todos os fios,
cada pedido HTTP, cada evento SSE, cada falha e `forget` da `ReadyCache`, cada espera de um trabalho de fundo pela GUI;
embrulhos só em memória) e o browser instrumentado (SSE recebidos, `fetch`, `loadBoard`/`loadMontar`/`loadDetail`,
recursos, momento em que o detalhe aparece). Leitura: `perfil_c3_ler.py`. Dados: `dados/r5_perfil_c3.json`. Base:
cópia de `projects/alpes` (versão do log 2307663) depois de um arranque completo. Vista fixa no céu (1,20–14,40, ppc
100), separador Peças; longe = (20,60), perto = (5,33).

**Longe, ms desde a resposta do POST (mediana · máximo de 5):**

| momento | mediana · máx. | o que o determina |
|---|---|---|
| POST | 557 · 571 | reconsulta 285 ms, `_refresh_render_assets` 85 ms |
| SSE `board_changed` recebido | −2 · 0 | emitido antes de a resposta sair |
| `loadBoard` começa | 354 · 359 | temporizador de 350 ms do `scheduleReload` |
| `loadBoard` acaba | 701 · 808 | espera por `/api/ghosts` (340 · 444 ms no servidor) e `/api/board` (232 · 312) |
| pedido do detalhe | 988 · 1091 | temporizador de 280 ms do `scheduleDetail`, armado no fim do `loadBoard` (`loadMontar` corre em paralelo: `/api/montar` 157 · 176) |
| composição da região | 834 · 838 | 0 falhas da E: só composição com as peças já prontas |
| detalhe no ecrã | **1854 · 1956** | transferência + `decode` ≈ 20 ms |

- **O que invalida:** a cache da E não. O único `forget` é o da peça colocada, em `_refresh_render_assets`, e a
  composição do céu tem 0 falhas nas 5 corridas. Quem obriga a recompor é **a LRU das regiões**: a chave é
  `render_version()` (tamanho do log, mtime de `placements.json`), por isso qualquer escrita invalida todas as regiões,
  mesmo as que não mudaram. A região do céu é recomposta inteira (834 ms) sem nenhuma peça diferente.
- **O que corre ao mesmo tempo:** o ranking dos buracos começa com o POST e acaba a 2,4 s. Cede durante a composição
  inteira: 1 espera de 836 ms, igual à composição. As suspeitas correm de 9 a 398 ms (`evaluate` ≈ 0,39 s), em cima
  do `loadBoard`. O pré-aquecimento já tinha acabado. `/api/board`, `/api/ghosts` e `/api/montar` não são pedidos de
  primeiro plano (o fundo não lhes cede); quanto do seu tempo é disputa do GIL não está medido [NT].
- **Soma:** 350 (temporizador) + ≈ 350 (`loadBoard`) + 280 (temporizador) + 835 (composição) + ≈ 40 ≈ 1,85 s. Os
  temporizadores fixos são 630 ms (34 %); a composição de uma região que não mudou, 835 ms (45 %).
- Estas 5 corridas dão 1,80–1,96 s, abaixo dos 2,71–2,72 s da tabela §11.11 (2 corridas, outra base, sem
  instrumentação). A diferença não está explicada [NT].

**Perto (5,33), para comparar:** detalhe no ecrã 2636 · 2694 ms; POST 1344 ms. O `loadBoard` acaba a 1439 ms, porque
`/api/ghosts` leva 1062 · 1141 ms e `/api/board` 635 · 684 ms. Ao mesmo tempo correm as suspeitas, com `evaluate` de
≈ 4,0 s (a peça tem vizinhas montadas; longe são 0,39 s), o ranking (3,5 s) e o fim do pré-aquecimento (até ≈ 1,1 s
depois do POST; o «perto» é o 1.º «Encaixa» da corrida). A composição é igual: 852 ms, 0 falhas da E.

**Correção (2026-11-15, mais tarde):** os 1,85 s das 5 corridas acima não se repetiram (ver §13.1). Nessas corridas,
as suspeitas levaram 0,39 s; em todas as seguintes levaram 1,7–2,2 s, com o mesmo código, a mesma base e registos do
servidor iguais linha a linha. A decomposição (o que invalida, o que corre ao mesmo tempo) mantém-se; os tempos
absolutos não.

## 13. Critério 3: chave das regiões por conteúdo, detalhe logo depois de uma escrita, seqlock (2026-11-15) [V]

### 13.1 Passo 0: 1,85 s contra 2,7 s

- 5 corridas sem instrumentação em `987f175` (`desempenho.py --so a`, base de §12): «longe» **3,13 · 3,53 s**
  (mediana · máximo), «perto» 3,77 · 3,88 s.
- Para separar a instrumentação da altura em que se mede: 5 pares alternados (sem, com). Sem: 3,08 · 3,52 s; com:
  3,10 · 3,50 s. **A instrumentação não pesa.** Código num worktree em `D:` contra `C:` (3 + 3, alternados):
  3,27 · 3,32 contra 3,31 · 3,56 s. **O disco também não pesa.**
- Os 1,85 s de §12 não se repetiram em 13 corridas posteriores. A diferença é uniforme em todo o trabalho de CPU do
  servidor: suspeitas 0,39 → 1,7–2,2 s, `/api/ghosts` 0,34 → 1,5 s, `/api/board` 0,23 → 1,2 s, ranking 2,4 → 3,8 s,
  pré-aquecimento 10,0 → 11,7 s. Os registos do servidor são iguais, tirando os tempos. Logo, é a máquina e não o
  código; os 2,7 s de §11.11 ficam entre os dois. A causa concreta (outro processo, energia, antivírus) não está
  isolada [NT]. **Regra daqui em diante:** antes/depois só em pares alternados na mesma sessão, com o código antigo
  por `--repo` num worktree.

### 13.2 O que mudou

- **Chave da cache das regiões = conteúdo** (`Gui._region_sig`): sha1 das peças com célula na região ± 1 (a margem
  da própria composição). Cada peça entra com a célula, a pose com que é desenhada (a entrada de `placements` válida,
  senão o registo na hora, por `_entry_key`) e `ReadyCache.key` (recorte, aresta pintada, mm/px, fundo, constantes,
  sha1 do `puzzle.json`); entra também o ficheiro da arte. Custa 30–40 ms por pedido (≈ 100 `os.stat`). Uma
  composição só fica guardada se nenhuma escrita a cruzou (seqlock, sem esperar); se alguma cruzou, é servida mas não
  guardada.
- **Browser** (`novo.js`, `board.js`):
  - o SSE `board_changed` (`boardChanged`) muda `S.ver` e pede logo o detalhe da versão nova, em paralelo com a
    recarga (`reloadNow`: tabuleiro + Montar), sem os 350 ms do `scheduleReload` nem os 280 ms do `scheduleDetail`;
  - a resposta de `/api/board` com a mesma versão não pede a região outra vez;
  - no fim de uma escrita feita pela própria página, aproveita-se a recarga já lançada por esse SSE;
  - um `fetch_changed` logo a seguir não recarrega outra vez;
  - durante um gesto, o detalhe espera pelo fim, como antes.
- **`/api/board`, `/api/ghosts` e `/api/montar` correm dentro de `foreground()`**: o ranking, as suspeitas e o
  pré-aquecimento cedem-lhes. Isto revelou um defeito na página «Buracos» da GUI antiga, já corrigido. A página
  desenhava o banner com `S.fetch.buracos_alta`, mas só se redesenhava quando chegava `/api/holes`; com a nova ordem
  das respostas ficava presa em «a calcular». O teste `test_reject_rank2_from_page_then_pause_and_resume` passou de
  0/8 falhas para ≈ 50 %; com a correção, 0/10. `refreshAltaBanners` troca só o banner quando chega `/api/fetch`.

### 13.3 Medido (5 pares alternados, código antigo `987f175` | novo; mediana · máximo; `dados/r5_criterio3_ab.json`)

| critério | alvo | antigo | novo |
|---|---|---|---|
| 3 longe (20,60) | ≤ 0,6 s | 3,94 · 4,05 | **0,28 · 0,28 [V]** |
| 3 perto (5,33) | ≤ 1,2 s | 4,83 · 4,97 | **2,74 · 3,05 [F]** |
| POST longe / perto | ≤ 2,0 s | 0,90 / 2,21 | 0,90 / 2,26 |
| 1 1.º salto | ≤ 4,0 s | 5,69 · 6,43 | 5,97 · 6,86 |
| 2 salto a frio, relva browser / HTTP | ≤ 2,0 s | 3,02 / 1,46 | 3,28 / 1,49 |
| sugestões desde o «pronto» | — | 8,51 | 8,41 |
| 5 pico do working set | ≤ 1,6 GB | 1106 MB | 1105 MB |

- Nesta sessão a máquina estava mais lenta do que em §11.11 (o código antigo deu 3,94 s no «longe»). Por isso os
  números absolutos dos critérios 1 e 2 e do POST não se comparam com §11.11; só se compara antigo com novo.
- Critérios 1 e 2: o código novo fica ≈ 0,25 s acima na mediana, dentro do ruído (os intervalos sobrepõem-se). O
  único custo novo conhecido é o `_region_sig`, 30–40 ms por pedido.
- Prova byte a byte (`tests/test_regiao_conteudo.py`): uma escrita longe acerta na cache e dá a mesma imagem que uma
  composição a frio; uma escrita na margem, uma pose manual e um «Encaixa» desfeito recompõem e dão a mesma imagem
  que a frio; uma composição cruzada por uma escrita não fica guardada.
- `tests/test_gui_detalhe_escrita.py`: o pedido da região sai menos de 150 ms depois do SSE e antes do fim de
  `/api/board`, e sai uma só vez. Com o código antigo saía 644 ms depois.

### 13.4 «Perto»: proposta, não implementada

O «perto» muda o conteúdo da própria região, por isso a chave muda e a região é recomposta inteira: ≈ 0,85–1,2 s a
quente, ≈ 100 peças. Essa composição corre ao mesmo tempo que as suspeitas (≈ 4–5 s de `evaluate` para uma peça com
vizinhas) e que o ranking. A proposta é refazer só as células alteradas sobre a região em cache:
1. Guardar com o JPEG o array da região (≈ 8,5 MB a ppc 100 no céu; LRU por bytes, com orçamento próprio) e as partes
   da assinatura por peça, não só o sha1.
2. Quando um pedido traz outra assinatura e há em cache uma entrada da mesma região e ppc, comparar as partes para
   obter as peças Δ (entradas, saídas, pose, peça pronta). A zona suja é a união das caixas antigas e novas das peças
   Δ, já com a sangria (`ext`), em píxeis da mesma moldura da região.
3. Repintar só a zona suja: primeiro a arte desses píxeis; depois o mesmo ciclo da composição (mesma ordem, os dois
   passes, prioridade de profundidade) sobre as peças cuja caixa toca a zona. Os warps calculam-se contra a moldura da
   região inteira, com o mesmo recorte `bx0..bx1` aos limites da região, para dar os mesmos números; escreve-se só
   dentro da zona. Cada píxel depende só das peças que o cobrem, pela mesma ordem, por isso o resultado é igual byte a
   byte ao da composição inteira. No fim, o JPEG (6 ms).
4. Teste antes de ligar: o array remendado tem de ser igual byte a byte à composição inteira, ao colocar, tirar e
   mover uma peça, com pose manual e com recorte corrigido, no céu e na relva (sintético e cópia real).

Ganho esperado: ≈ 4–10 peças em vez de ≈ 100, ou seja ≈ 0,1 s em vez de ≈ 1 s [NT]. O resto do «perto» (2,74 s) é a
disputa com as suspeitas e o ranking lançados pela mesma escrita, que este remendo não resolve; terá de ser medido
depois.

### 13.5 Seqlock das suspeitas e o mesmo padrão noutros leitores

- `Gui.wlock` é um `SeqLock`: o contador sobe ao tomar e ao largar o bloqueio, dentro dele, e fica ímpar durante a
  escrita. `Gui.seq_read` só aceita uma leitura se o contador era par no início e igual no fim; uma exceção com uma
  escrita pelo meio conta como tentativa rasgada.
- `suspeitas_json` usa o `seq_read`. À 3.ª tentativa rasgada devolve o resultado anterior com `desatualizada: true` e
  pede outra passagem de fundo, **sem tomar o bloqueio de escrita**. Dentro de uma escrita (`_after_suspect_write`)
  corre uma vez, diretamente.
- Testes (`tests/test_seqlock.py`):
  - cenário «mover» nas pausas 1, 2 e 3: dá o estado final com exatamente 2 avaliações (antes dava 1/1, um estado que
    nunca existiu);
  - uma escrita durante uma avaliação lenta espera menos de 50 ms pelo bloqueio;
  - 3 tentativas rasgadas devolvem o resultado anterior marcado, as escritas não esperam, e a passagem seguinte dá o
    estado final.
- Cenário «mover» forçado nos outros leitores (código de hoje, sintético) [V]:

| leitor | escrita a meio | resultado |
|---|---|---|
| «verificar» (`verify_json`) | na 1.ª / 2.ª / 3.ª de 4 rotações | = depois / **nunca existiu** / **nunca existiu** |
| `rank_all` no fio dos buracos | na pausa 5 / 14 / 25 de ≈ 30–40 | **nunca existiu** / **nunca existiu** / = antes |
| pré-aquecimento (`_prewarm`) | na pausa 1 / 2 | peças prontas iguais às calculadas a frio (a pose não entra nelas) |

- O «verificar» só recomeça quando há uma exceção. O ranking rasgado fica guardado em `_holes_prev`, que é a lista
  que «Vai buscar» mostra durante o recálculo seguinte. A correção dos dois com `seq_read` está proposta, não feita.

### 13.6 «Perto» A/B/C/D: o que a disputa com as suspeitas e o ranking custa, e os critérios 1 e 2 em 10 pares (2026-11-15, `f85c092`) [V]

Medição, sem alterar `src/`, `tests/` nem `tools/`. Dados: `dados/r6_perto_abcd.json`, `dados/r6_criterios12_pares.json`.

**Critério fixado antes de medir.** Se o «perto» com as suspeitas e o `rank_all` desligados (D) ficasse ≤ 1,2 s (mediana), a
alavanca seria a disputa e o remendo de §13.4 não seria prioritário; se ficasse > 1,2 s, o remendo justifica-se.

#### Lançador usado

`scratchpad/abcd/lanca_abcd.py` (fora do repositório). Importa `tools/diagnostico/gui/linha_tempo.py` (linha do tempo de todos os
fios) e, só em memória e só depois do arranque, conforme a variável de ambiente `PPF_DESLIGA`:

- **B** substitui `Gui._suspeitas_bg` por uma função que não faz nada (regista um instante). «Depois do arranque» = depois de
  o 1.º ranking completo ter sido servido por `holes_json`.
- **C** faz `Gui.holes_json` devolver, a seguir a uma escrita, o ranking completo guardado (repõe `_holes` com a chave da versão
  atual), sem lançar o fio `holes` e com `a_calcular` falso; o ranking do arranque corre normalmente e o guião (`_wait_holes`)
  não fica à espera. Não se emite `holes_changed`.
- **D** = B + C; **A** não desliga nada.
- Embrulha ainda `Gui._compose` para registar `time.thread_time()` (CPU do fio) ao lado do tempo de parede.

O corredor é `scratchpad/abcd/rodar_abcd.py`, que corre `perfil_c3.run` (o protocolo de `desempenho.py --so a`: cópia nova da
base, servidor novo, Chromium 1920 × 1080, vista fixa no céu 1,20–14,40, «perto» (5,33) e «longe» (20,60)) 20 vezes **em rotação
A,B,C,D × 5 rondas, na mesma sessão**; `scratchpad/abcd/resumo_abcd.py` produz as tabelas. Não foi preciso tocar em `src/` para
desligar nada. Verificado na linha do tempo: em B/D aparece «suspeitas_bg desligado» e não há `consistency.evaluate` depois do
POST; em C/D aparece «holes_json servido da guarda» e não há `fit.rank_all` depois do POST. O pré-aquecimento (`_prewarm`, fio
`pre-aquecer`) **não** foi desligado em nenhuma condição (ainda corria 20–25 s depois do POST).

#### Resultados (5 corridas por condição; mediana · máximo, em s)

| condição | «perto» (POST → detalhe) | «longe» (controlo) | `_compose` da região (parede) | CPU do fio (`thread_time`) | parede − CPU | `_region_jpg` − `_compose` |
|---|---|---|---|---|---|---|
| A nada desligado | **2,80 · 2,95** | 0,29 · 0,32 | 2,45 · 2,61 | 1,95 · 2,19 | 0,52 · 0,52 | 0,24 · 0,29 |
| B sem suspeitas | 2,73 · 2,81 | 0,28 · 0,30 | 2,47 · 2,55 | 2,00 · 2,17 | 0,47 · 0,51 | 0,24 · 0,27 |
| C sem `rank_all` | 2,71 · 2,78 | 0,25 · 0,26 | 2,45 · 2,52 | 1,91 · 1,92 | 0,54 · 0,60 | 0,22 · 0,26 |
| D sem ambos | **2,74 · 2,80** | 0,23 · 0,27 | 2,46 · 2,55 | 2,00 · 2,11 | 0,44 · 0,56 | 0,22 · 0,25 |

**Conclusão segundo o critério fixado: D = 2,74 s > 1,2 s, logo o remendo de §13.4 justifica-se [V]; «a disputa é a alavanca» é
[F].** Tirar as suspeitas e o ranking juntos poupa 0,06 s (A 2,80 → D 2,74), dentro do ruído entre corridas (≈ 0,1 s). Quase tudo
é a própria composição da região: ≈ 2,0 s de CPU de um só fio, mais ≈ 0,45–0,5 s de espera, mais 0,22–0,24 s fora da composição,
mais ≈ 0,2–0,28 s entre o fim do POST e o pedido da região.

- **Espera pelo bloqueio de escrita no caminho do detalhe: não há.** `_region_jpg` não toma `wlock`: lê `wlock.seq` antes e
  depois (seqlock, sem esperar). O que fica entre `_region_jpg` e `_compose` (≈ 0,22–0,24 s) é a assinatura por conteúdo
  (`_region_sig`, ≈ 100 `os.stat`), o `region_lock`, o bloqueio por cliente e a codificação do JPEG; não se separou por partes
  [NT]. Não depende de A/B/C/D.
- **Parede − CPU** mede o tempo em que o fio da composição não estava a gastar CPU: espera pelo GIL, E/S de disco, trocas de
  contexto e CPU cedida a outros processos. **Não separa** GIL de E/S nem de outros processos (o `thread_time` do Windows conta
  tempo de núcleo e de utilizador do fio, nada mais). É 0,44–0,54 s em todas as condições, sem diferença entre A e D: o que as
  suspeitas e o ranking acrescentam à espera é ≈ 0 [V]; o que fica (≈ 0,45 s) vem de outros fios (as outras respostas do mesmo
  SSE: `/api/board` com `_base` ≈ 0,2 s, `/api/montar`, `/api/ghosts`, o laço de eventos), de E/S e do sistema [NT: não
  separado].
- **Fios concorrentes durante a composição** (sobreposição com a janela do `_compose`, mediana de 5 corridas): em A, as
  suspeitas, o ranking e o pré-aquecimento estão todos «cedidos» à GUI durante a composição inteira (`cede à GUI` soma 7,36 s =
  3 fios × 2,45 s); em B só o ranking e o pré-aquecimento (4,94 s); em C só as suspeitas e o pré-aquecimento (4,90 s); em D só o
  pré-aquecimento (2,46 s). A prioridade (b) já faz o que devia: os trabalhos de fundo estão parados enquanto se compõe, e por
  isso desligá-los não encurta nada.
- Os valores absolutos desta sessão são ≈ 2× os de §13.4 («0,85–1,2 s a quente», ≈ 100 peças): é a deriva da máquina de §13.1,
  por isso só se comparam as quatro condições entre si (mesma sessão, intercaladas).

#### Suspeitas e ranking: mesmo processo, disputa do GIL?

**Mesmo processo, fios diferentes [V].** `Gui._suspeitas_bg` cria `threading.Thread(name="suspeitas")` (`src/server.py` L1058),
`holes_json` cria `threading.Thread(name="holes")` (L1246), o pré-aquecimento `name="pre-aquecer"` (L831) e a composição do
detalhe corre num fio do pool do uvicorn (`AnyIO worker thread`). No lançador, todas as linhas da corrida (cada uma com o nome do
fio) vêm do mesmo `os.getpid()` (32676 numa corrida) e do mesmo ficheiro; não há `multiprocessing` no servidor. Logo, partilham o
GIL (aqui com `sys.setswitchinterval(0,0005)`).

**Mas a disputa medida é pequena [V]:** pela prioridade (b), os três fios de fundo cedem durante toda a composição e A − D =
0,06 s. A disputa só existiria dentro de uma peça em curso quando o pedido chega (os fios só cedem entre peças). Mudanças
possíveis, listadas sem implementar:

| mudança | ganho esperado no «perto» | custo / risco |
|---|---|---|
| adiar suspeitas e ranking até o detalhe da versão nova estar servido | ≈ 0 (já cedem durante a composição); só evitaria a fração de peça em curso no início | simples, mas atrasa suspeitas e sugestões no caso normal |
| ceder com mais granularidade (dentro de uma peça / do `evaluate`) | ≤ 0,1 s [NT] | mexe no interior de `consistency.evaluate` e `fit.rank_all`; o seqlock tem de continuar a valer |
| prioridade do fio da composição | desconhecido; o GIL não tem prioridades | o Python não dá controlo por fio; só serviria contra outros processos, não medido |
| processo à parte (`multiprocessing`) para suspeitas/ranking | tira o GIL de vez, mas o ganho medido é ≈ 0,06 s | custo alto: serializar o projeto e as caches (formas, lados erodidos, `ReadyCache`), memória a duplicar (pico já ≈ 1,1 GB), caches coerentes com o log; risco de versões desfasadas |
| **o remendo de §13.4** (refazer só as células alteradas sobre a região em cache) | o único que ataca os ≈ 2 s de CPU da composição [NT] | já descrito em §13.4: guardar o array da região (≈ 8,5 MB), prova byte a byte antes de ligar |

#### Critérios 1 e 2: 10 pares alternados `987f175` | `f85c092`

Cada par = uma corrida de `desempenho.py --so a --n 1` com `--repo` (worktree em `987f175`), seguida de uma com `--repo` (worktree
em `f85c092`), cópia nova e servidor novo em cada. IC 95 % pelo bootstrap de pares (10 000 reamostragens) da estatística
mediana(novo) − mediana(antigo). Mediana · máximo, em s.

| medida | antigo | novo | diferença das medianas | IC 95 % | exclui +0,25 s? | marca |
|---|---|---|---|---|---|---|
| critério 1: `salto1_ceu` (alvo 4,0) | 6,08 · 7,02 | 6,45 · 6,88 | +0,36 | [−0,14, +0,65] | **não** | [NT] inconclusivo (nem confirma nem exclui regressão); alvo [F] nos dois |
| critério 2 browser: `salto_frio_relva` (alvo 2,0) | 3,37 · 3,44 | 3,27 · 3,47 | −0,10 | [−0,21, +0,07] | sim | [V] sem regressão ≥ 0,25 s; alvo [F] nos dois |
| critério 2 HTTP: `srv_frio_relva_s` | 1,53 · 1,59 | 1,54 · 1,68 | +0,01 | [−0,02, +0,09] | sim | [V] sem regressão |
| critério 2 HTTP: `srv_frio_ceu_s` | 1,19 · 1,23 | 1,21 · 1,27 | +0,02 | [−0,02, +0,11] | sim | [V] sem regressão |
| (controlo) «perto» | 5,01 · 5,35 | 2,87 · 3,00 | −2,15 | [−2,34, −2,04] | sim | [V] melhora |
| (controlo) «longe» | 4,05 · 4,60 | 0,27 · 0,29 | −3,78 | [−3,86, −3,70] | sim | [V] melhora; alvo 0,6 cumprido |

- Critério 1: a diferença das medianas é +0,36 s, mas a média das diferenças emparelhadas é +0,14 s (IC [−0,20, +0,46]). Com
  10 pares e um desvio entre corridas de ≈ 0,4 s o intervalo não exclui +0,25 s: **não se pode afirmar que não há custo** (o
  único custo novo conhecido, o `_region_sig`, é de 30–40 ms por pedido; +0,36 s não se explica só por ele, mas também não se
  confirma) [NT]. Decidir exigiria ≈ 30 pares.
- A deriva da máquina aparece também aqui: o «perto» e o «longe» do código antigo (5,01 / 4,05 s) estão acima de §13.3 (4,83 /
  3,94 s) e o 1.º salto (6,1 s) acima dos 5,7 s de §13.3.

#### O teste «1 skipped» da suite

`tests/test_sheets.py:170`: o teste com o PyMuPDF real salta porque o `.venv` não o tem instalado (mensagem: «PyMuPDF não está
instalado neste Python (o .venv não o tem)»). Confirmado com `.venv/Scripts/python.exe -m pytest tests/ -rs -q`: **621 passed,
1 skipped** em 10 min 13 s [V]. Os outros testes de `test_sheets.py` forçam os dois caminhos com um substituto e passam.

### 13.7 «Perto»: passo 0, remendo das células alteradas, leitores rasgados (2026-11-15)

Plano aprovado pelo Tiago (`docs/prompts/2026-11-15-perto-remendo.md`). Critérios fixados antes de medir: «perto» ≤ 1,2 s
e «longe» ≤ 0,6 s (mediana, pares alternados `8668365 | novo` na mesma sessão); imagem servida igual byte a byte a uma
composição a frio; POST e critério 2 sem regressão (IC 95 % que exclua +0,25 s); pico de memória ≤ +200 MB.

#### Passo 0: onde estão os ≈ 0,45 s que não são CPU e os ≈ 0,22 s fora da composição [V]

Lançador `scratchpad/p0/lanca_p0.py` (fora do repositório): `linha_tempo.py` mais cronómetros por fase (parede e
`time.thread_time()`), só em memória, numa cópia de `compose_board` e de `Gui._region_jpg` de `8668365` (servidor num
worktree nesse commit). Corredor `scratchpad/p0/rodar_p0.py`: o protocolo de `perfil_c3.run`, 5 rondas × 2 condições
intercaladas. Na condição «atrasado», `page.route` retém no browser `/api/board`, `/api/ghosts` e `/api/montar` desde
antes do POST até o detalhe da versão nova aparecer; a rota está instalada também na «normal» (deixa seguir logo), para
custar o mesmo. Dados: `dados/r7_passo0_paralelos.json`. Mediana · máximo, em s; 117 peças desenhadas, 88 delas
registadas na hora (sem entrada válida em `placements`).

| medida | normal | pedidos paralelos atrasados |
|---|---|---|
| «perto» (fim do POST → detalhe) | **2,65 · 2,77** | **1,44 · 1,47** |
| «longe» | 0,26 · 0,27 | 0,18 · 0,21 |
| `_region_jpg` (parede) | 2,53 · 2,63 | 1,37 · 1,40 |
| `_compose` (parede) | 2,32 · 2,46 | 1,19 · 1,25 |
| `_compose` parede − CPU | 0,49 · 0,58 | 0,13 · 0,14 |
| `_region_jpg` fora do `_compose` | 0,19 · 0,21 | 0,17 · 0,18 |
| … `_region_sig` | 0,18 · 0,21 | 0,16 · 0,17 |
| … JPEG / `region_lock` / bloqueio por cliente / repetições de `self.read` | 0,006 / 0 / 0 / 1 | iguais |
| dentro de `compose_board`: registo na hora (88 peças) | **1,00 · 1,07** | **0,07 · 0,07** |
| … peças prontas (`ReadyCache`) | 0,10 | 0,04 |
| … warps (sangria + peças + profundidade) | 0,41 | 0,38 |
| … pré-multiplicação | 0,34 | 0,32 |
| … mistura + `_depth_px` + arte + `clip` | 0,40 | 0,37 |
| pedidos paralelos sobrepostos ao detalhe (parede): `board_json` / `ghosts` / `montar_json` / `_base` | 0,76 / 1,31 / 0,97 / 0,20 | — |
| POST «perto» | 2,27 | 2,20 |
| `srv_frio_relva_s` (referência da máquina) | 1,40 · 1,51 | 1,43 · 1,44 |

- **Hipótese «pedidos paralelos» [V]:** atrasá-los tira 1,21 s ao «perto» (2,65 → 1,44) e 0,08 s ao «longe». O ganho está
  quase todo no código Python da composição (o registo na hora: 1,00 → 0,07 s; as células, as peças prontas); os passos
  em C (warps, mistura) quase não mudam. É o padrão de disputa do GIL: três pedidos em Python correm ao mesmo tempo, todos
  em `foreground()` (os trabalhos de fundo cedem, estes não).
- **Os ≈ 0,45 s «não CPU»:** 0,49 → 0,13 s; ≈ 0,36 s vêm dos pedidos paralelos; os ≈ 0,13 s restantes não se separaram
  (E/S, sistema) [NT]. O `thread_time` do Windows tem grão de 15,6 ms: as somas por fase de CPU de chamadas curtas não
  são fiáveis; o total por composição sim (1,81 → 1,06 s de CPU: a espera do GIL também gasta CPU de núcleo nos
  acordares a cada 0,5 ms [NT, não medido à parte]). Não separa GIL de E/S.
- **Os ≈ 0,22 s fora da composição:** são quase só o `_region_sig` (0,16–0,18 s; 0,13–0,16 s de CPU), não os 30–40 ms
  estimados em §13.2. JPEG 6 ms; bloqueios ≈ 0.
- **Propostas baratas, separadas do remendo, não implementadas:**
  - **P-a** o browser pede `/api/board`, `/api/ghosts` e `/api/montar` só depois de o detalhe da versão nova aparecer
    (ou o servidor faz esses três cederem a uma composição de detalhe em curso). Medido no lançador: −1,2 s antes do
    remendo, e −1,2 s também depois dele (ver a decomposição nova abaixo).
  - **P-b** 88 das 117 peças do céu são registadas na hora em cada composição (a entrada de `placements.json` não vale
    para elas); vale a pena perceber porquê e guardar o registo por `_entry_key` no servidor [NT].
  - **P-c** `_region_sig` / `_region_parts` 0,17–0,20 s por pedido: memorizar `ReadyCache.key` por peça (um `os.stat` e o
    sha1 do `puzzle.json` por peça hoje) [NT a divisão exata].

#### Bloco 1: remendo das células alteradas

**Tabela 1-0 confirmada no código** (`compose_board`, camadas `art` + `pieces`): fundo e `clip` píxel a píxel; a arte lê só
o ficheiro da arte (guarda-se como `base_art`, não se recalcula); `_display_masks`, `_fill_transparent`, `_bleed_rgba`,
`_depth_px` correm no recorte da própria peça, antes do warp; o warp bilinear (com pré-redução `INTER_AREA`) escreve só na
caixa da peça (cantos −1 / +2 px, cortada à região); a mistura dos dois passes (sangria «over», prioridade de
profundidade com `zbuf`) depende só das peças que cobrem o píxel, pela ordem das células. A escolha das peças (célula na
região ± 1) é uma regra de seleção, já na assinatura. **Nenhum passo global** [V].

**O que mudou** (`src/render.py`, `src/server.py`):
- `compose_board` foi partido em auxiliares puros (`_frame`, `_art_layer`, `_piece_jobs`, `_job_geom`, `_job_boxes`,
  `_draw_jobs`); a composição inteira chama o mesmo `_draw_jobs` sem `clip` (mesmos números). Novos `base_art=` e
  `return_parts=` (`{img, art, boxes}`).
- `compose_patch`: zona suja = união das caixas antigas e novas das peças Δ + 2 px; nela, a partir de `base_art` e de um
  `zbuf` limpo, redesenham-se todas as peças cuja caixa a toca, pela ordem normal, cada uma com o warp da caixa inteira;
  fora dela ficam os píxeis antigos. Zona > 35 % da região → composição inteira a partir da base.
- Servidor: `_region_parts` (as partes que já entravam no sha1 de `_region_sig`), `PatchCache` (LRU por bytes, 128 MB,
  `--cache-remendo-mb`, `clear` onde a `ReadyCache` é limpa, `touch` num acerto da LRU de JPEG), `_compose_region` (Δ pela
  comparação das partes; Δ = ∅ → a imagem guardada; > 12 peças, sem entrada ou outra arte → inteira), contadores em
  `/api/status.remendo`. Os arrays só ficam guardados se o seqlock não mudou (a regra de `f85c092`).

**Testes, escritos antes do código** (`tests/test_regiao_remendo.py`, projeto sintético 6 × 8 com arte de céu liso e
relva com textura, 16 peças colocadas, região (1,2)–(6,6) a ppc 120; cada caso contra um servidor acabado de abrir, byte
a byte, e com o contador do remendo): antes 7 falham e 1 passa (a peça «por confirmar», que já era um acerto); depois
8/8 [V].

| caso | resultado |
|---|---|
| colocar no céu e na relva | 2 remendos, iguais a frio |
| vizinha com pose manual gravada e reposta | 2 remendos; a reposta volta ao JPEG de antes |
| desfazer (`unplace` + `desfaz`) | volta ao JPEG de antes, igual a frio |
| tirar do lugar | remendo, igual a frio |
| peça «por confirmar» | acerto na LRU (sem composição), igual a frio |
| peça re-segmentada (contorno manual pelo `POST …/contorno`) | 1 composição (remendo), igual a frio |
| escrita a meio de um remendo | servido; nem os arrays nem o JPEG ficam guardados; o pedido seguinte = a frio |
| sem base / > 12 peças / zona > limiar | composição inteira (`sem_base`, `muitas_pecas`, `zona_grande`), igual a frio |

- `test_concorrencia.py` não foi alterado. Uma sonda mostrou que nele as composições nunca ficam guardadas (as escritas não
  têm pausas: 169 inteiras «sem base», 0 remendos), por isso o esforço com remendos ficou num teste novo,
  `tests/test_remendo_concorrencia.py` (slow): 3 fios pedem regiões enquanto o principal coloca, desfaz, tira e muda poses
  com pausas de 0,4 s (92 remendos e 22 inteiras numa corrida); no fim, mais duas escritas sem concorrência, cada região
  remendada sobre o que ficou guardado durante o esforço e comparada com um servidor novo: iguais [V].
- **Cópia real** (`tools/diagnostico/gui/remendo_iguais.py`, base `base_c3`, semente 20261115, `dados/r7_remendo_iguais.json`):
  12 escritas ao acaso (4 colocar, 3 desfazer, 3 gravar pose manual, 1 repor, 1 tirar), céu (1,20–14,40) e relva
  (34,30–47,50) a ppc 100: **12 remendos, 12 acertos na LRU, 0 composições inteiras depois das 2 bases, 0 diferenças
  byte a byte** [V]. Cada remendo 0,14–0,22 s no processo sem browser.

**10 pares alternados `8668365 | novo`** (`desempenho.py --so a --n 1 --repo <worktree>`; IC 95 % por bootstrap de pares,
10 000 reamostragens, da diferença das medianas; `dados/r7_pares_remendo.json`). Mediana · máximo, em s.

| medida | alvo | `8668365` | novo | diferença | IC 95 % | exclui +0,25? | marca |
|---|---|---|---|---|---|---|---|
| 3 «perto» (5,33) | ≤ 1,2 | 2,51 · 2,57 | **1,60 · 1,80** | −0,90 | [−1,10, −0,76] | sim | melhora [V]; alvo **[F]** |
| 3 «longe» (20,60) | ≤ 0,6 | 0,24 · 0,29 | 0,27 · 0,29 | +0,03 | [−0,01, +0,04] | sim | [V] |
| POST «perto» | — | 2,12 · 2,26 | 2,25 · 2,37 | +0,12 | [+0,01, +0,26] | **não** | regressão não excluída **[F]** |
| POST «longe» | — | 0,86 · 0,96 | 0,88 · 0,92 | +0,02 | [−0,04, +0,06] | sim | [V] |
| 2 salto a frio, relva (browser) | — | 2,90 · 3,20 | 3,06 · 3,24 | +0,17 | [+0,02, +0,32] | **não** | regressão não excluída **[F]** |
| 2 salto a frio, relva (HTTP) `srv_frio_relva_s` | — | 1,38 · 1,47 | 1,47 · 1,52 | +0,09 | [+0,02, +0,14] | sim | [V] sem regressão ≥ 0,25; custo medido ≈ +0,08 |
| 2 salto a frio, céu (HTTP) | — | 1,08 · 1,17 | 1,12 · 1,20 | +0,05 | [−0,00, +0,11] | sim | [V] |
| 1 1.º salto (céu) | ≤ 4,0 | 5,61 · 6,13 | 5,65 · 6,16 | +0,04 | [−0,38, +0,35] | não | [NT] inconclusivo |
| 5 pico do working set | ≤ +200 MB | 1106 MB | 1206 MB | **+99 MB** | [+98, +100] | — | [V] |

- **«Perto» que caíram na composição inteira: 0 de 10** (os 10 remendados; as inteiras de cada corrida são só as 6
  regiões «sem base» dos saltos e dos pedidos a frio) [V]. A `PatchCache` ficou com 98,4 MB (6 regiões) em todas.
- O custo novo da composição a frio (+0,05–0,09 s por HTTP) é o `return_parts`: uma cópia da base, as caixas de todas as
  peças e a escrita na `PatchCache`. No browser aparece +0,15–0,17 s; não se afinou (paragem abaixo).
- O POST «perto» (+0,12 s, IC até +0,26) corre ao mesmo tempo que o pedido do detalhe; não decomposto [NT].

**Paragem: «perto» = 1,60 s > 1,2 s, não se afinou nada.** Decomposição nova (`scratchpad/p0/lanca_novo.py`: embrulhos
de parede/CPU em `_region_parts`, `_compose_region`, `compose_patch`, `_piece_jobs`, `_draw_jobs`, `_jpeg` e nos três
pedidos paralelos; 3 + 3 corridas intercaladas, código novo; `dados/r7_perto_remendo_decomposicao.json`; mediana · máximo):

| medida | normal | pedidos paralelos atrasados |
|---|---|---|
| «perto» | **1,62 · 1,82** | **0,44 · 0,44** |
| `_region_jpg` | 1,52 · 1,71 | 0,36 · 0,37 |
| … `_region_parts` (assinatura) | 0,20 · 0,23 | 0,17 · 0,17 |
| … `compose_patch` | 1,29 · 1,49 | 0,19 · 0,19 |
| …… `_piece_jobs` (pose de todas as 117 peças, 88 registadas na hora, e peças prontas) | **1,21 · 1,38** | 0,12 · 0,12 |
| …… `_draw_jobs` (o redesenho da zona suja) | 0,07 · 0,09 | 0,05 · 0,06 |
| … JPEG | 0,007 | 0,006 |
| fim do POST → pedido / pedido → detalhe no ecrã | 0,05 / 0,06 | 0,04 / 0,03 |
| pedidos paralelos sobrepostos: `board_json` / `ghosts` / `montar_json` | 0,81 / 1,32 / 1,05 | — |

O redesenho em si custa 0,07 s. O que fica é a preparação das 117 peças (`_piece_jobs`, com o registo na hora das 88)
a disputar o GIL com os três pedidos paralelos (1,21 s; 0,12 s sem eles), e a assinatura (0,20 s). Com P-a o «perto»
ficaria em ≈ 0,44 s [V no lançador; não implementado]; P-b e P-c tirariam o resto da preparação e da assinatura [NT].

#### Bloco 2: leitores rasgados

- **`rank_all`** (`Gui._compute_holes`): no fio dos buracos espera que não haja escrita (`wait_even`), lê o contador e só
  publica (`_holes`, `_holes_prev`, `holes_changed`) se ele não mudou; senão não toca em nada e calcula outra vez (a
  lista mostrada continua a anterior, marcada `desatualizada`). Se uma escrita chegar logo depois de publicar, calcula
  outra vez (o pedido dela foi absorvido pelo fio vivo). Dentro de uma escrita, uma passagem.
- **«verificar»** (`Gui.verify_json`): `seq_read` (3 tentativas, nunca o bloqueio de escrita; uma escrita em curso é
  esperada no máximo `VERIF_WAIT_S` = 0,5 s por tentativa, senão a tentativa conta como rasgada: a suite apanhou-o, o
  teste existente `test_f2.py::test_verificar_does_not_wait_for_the_write_lock` deu 10,06 s com a espera de 90 s das
  suspeitas, contra < 3 s exigidos; com o limite passa); à 3.ª tentativa rasgada, o
  resultado anterior da mesma `(l, c, peça, θ)` marcado `desatualizada`; sem nenhum, `estado: "nao_verificado"` (lista
  vazia, sem veredicto). `novo.js` mantém «a verificar…» e pede outra vez a cada 500 ms, até 3 vezes; depois mostra «Não
  consegui verificar: o tabuleiro estava a mudar enquanto verificava». «Pôr aqui» nunca fica bloqueado.
- **Testes, escritos antes** (`tests/test_seqlock_leitores.py`, `tests/test_gui_verificar_repete.py`): com o código do
  bloco 1, **8 falham e 1 passa** (a escrita não espera pelo «verificar», que já era assim); com o bloco 2, **9/9** [V].

| cenário | antes | depois |
|---|---|---|
| `rank_all`, «mover» na pausa 5 / 14 | publicado (e guardado em `_holes_prev`) um ranking que nunca existiu | nada publicado a meio; a 1.ª publicação = processo novo; durante o recálculo, a lista anterior `desatualizada` |
| `rank_all`, 5 colocações a 1 s (ranking de 1,82 s) | publicações de versões antigas | 1 publicação, 2,57 s depois da última escrita (< 1 ranking + 1,5 s); **lista desatualizada no máximo 6,80 s** (da 1.ª escrita à publicação: 4 s de escritas + 1 ranking) |
| «verificar», «mover» na 2.ª chamada de `fit_check` | um estado que nunca existiu | igual a um processo novo depois da escrita |
| «verificar», 3 tentativas rasgadas | — (sem `estado`) | o resultado anterior marcado `desatualizada`; cada escrita esperou < 50 ms |
| «verificar» sem resultado anterior | — | `nao_verificado`; pedido outra vez sem escrita: veredicto |
| browser, 2 respostas `nao_verificado` | lista vazia, presa | 3 pedidos, depois o veredicto |
| browser, 4 respostas `nao_verificado` | lista vazia, presa | 4 pedidos, depois «Não consegui verificar», «Pôr aqui» ativo |

#### Critério 1

Fica **inconclusivo**, por decisão do Tiago: em §13.6, +0,36 s (IC [−0,14, +0,65]); nestes 10 pares, +0,04 s (IC
[−0,38, +0,35]), ainda sem excluir +0,25 s. O alvo de 4 s não se cumpre em nenhum dos lados (≈ 5,6–6,1 s): o 1.º salto
passa a item próprio (HANDOFF).
