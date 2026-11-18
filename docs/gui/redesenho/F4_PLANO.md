# Plano da F4 — grupos soltos no tabuleiro (só os grupos que já existem)

_2026-11-18, base `cc68ad4`. Só plano, sem código. Fontes: ESPEC §4.9, §7, §8.5; F0_INVENTARIO (T2, T7, B9, B10, ME1–ME10, C15, X8, §3 ponto 3); `docs/decisoes.md` (2026-11-14 F2, desfazer do grupo; 2026-11-16 P0833 e backlog; 2026-11-18 respostas da F4). Números de `projects/alpes` lidos em 2026-11-18 (só leitura)._

## Contexto

O Montar já trata peça a peça. Os grupos que já existem (secções e blocos do legado ainda sem lugar) só se veem na Mesa da GUI antiga. A F4 traz esses grupos para o tabuleiro da GUI nova: **desenhar, mover, rodar, fixar e soltar**. Fica fora: acrescentar ou tirar uma peça, desfazer o grupo, os «+», «Junta-se a um grupo», «O grupo já tem lugar», os grupos propostos (F4b) e as junções (F4c).

**O que há hoje em `projects/alpes`:** 100 secções, 66 fixadas e 34 por fixar. Destas 34, 2 só têm re-scans (`same_as`) e não aparecem, por isso ficam **32 grupos visíveis com 73 peças**. Tamanhos: 14 de 1 peça, 11 de 2, 2 de 3, 3 de 4, e um de 5, um de 7 e um de 8. Todos têm 3 candidatos, nenhum espelhado. A margem do 1.º candidato vai de 0,874 a 1,907; só 7 grupos estão em `margin_min` 1,5 ou acima.

**Margem [V, 2026-11-18]:** `margin` = (menor score de imagem entre as alternativas distintas) ÷ (score de imagem do candidato escolhido pela energia), calculada em `legacy._decide`. Uma margem abaixo de 1 não é um bug de ordenação: quer dizer que a energia escolheu um lugar com pior imagem. Só G0049 está nesse caso (0,874), e os seus candidatos 1 e 2 já estão ocupados por peças do legado.

**Pré-requisito: a F3½** (uma pose manual nunca esconde a suspeita de orientação, para todas as peças; substitui a regra «> 45°» da Q11 a) faz-se e fecha antes do B1. Tem plano e commit próprios e fica fora deste plano. *(Feita em 2026-11-18, `docs/decisoes.md`.)*

---

## 1. O que já existe e o que falta

### Já existe
- **Estado (`src/state.py`).** `Section` {id, scan_id, kind, cells_local, anchor, candidates, notes}. `anchor` = {anchored, l0, c0, rot, mirror, fonte, confianca, margin}, mapeado por `section_cell`. As ações `section_registered`, `section_anchored` (peças em `colocada`, fonte de célula `legado_scan`, limpa `pose_manual`, regista os `conflicts` sem os sobrescrever), `section_unanchored` (repõe as células com `restore`, as peças voltam a `em_seccao`, limpa a pose manual) e `section_candidates_updated`. `Project.anchor_section` / `unanchor_section`. Uma peça `em_seccao` não está no `Board`: não é molde, não é vizinha e não conta no progresso.
- **Pose.** `render.initial_theta` dá o θ de uma peça de secção fixada (rotação da página + ângulo do corpo + `anchor.rot`); `_section_rotation` usa `legacy.page_rotation`.
- **Servidor (`src/server.py`).** `sections_json` (`GET /api/sections`) com `pecas` {id, rc, lote, n_no_lote} e `candidatos` {cell0, rot, mirror, score, margin, footprint, fora, ocupadas}. `section_png` é a vista explodida do scan, não o grupo montado. `/api/confirm` com `acao: anchor | unanchor` passa por `confirm()`, que faz a reconsulta incremental. `cell_json.secao` existe, e o painel da peça da GUI nova já tem «Tirar o grupo inteiro do lugar (N peças)», com desfazer = `anchor` com o mesmo `cell0`, `rot` e `mirror` (F2).
- **Ficheiros à parte só a acrescentar:** `overrides.jsonl` (`src/overrides.py`: `append_override`, `latest_overrides`) é o modelo do `mesa.jsonl`. `state.write_atomic` / `read_retry` servem para o Windows.
- **Montar (`src/montar.py`).** `resumo.grupos_sem_lugar` e o texto «por agora só na interface completa» (`novo.js` 452–471, 1245).
- **GUI antiga.** A Mesa (`renderMesa`, `mesaRow`, `drawMesa`). Fica intacta até à F6.

### Falta
1. **A posição livre em `projects/<id>/mesa.jsonl`**, num módulo novo `src/mesa.py` (I/O + validação + leitura tolerante).
   - Cada linha: `{gid, l0, c0, rot, t, log_n}`. `log_n` é o número de eventos do log no momento da escrita.
   - **Uma linha só vale** se `log_n` for maior do que o índice do último `section_anchored` / `section_unanchored` desse grupo, e se o grupo existir e estiver sem lugar. Vale a última linha válida por grupo. Linhas partidas, de grupos desconhecidos ou de grupos fixados são ignoradas e contadas num aviso; não dão erro.
   - **Sem linha válida:** um grupo **nunca fixado** não aparece no tabuleiro até «Mostrar no tabuleiro» (Q3). Um grupo **solto depois de fixado** fica na posição da última fixação (Q10 a), sem escrita extra.
   - **Escrita (`mover`, `mostrar`):** valida e escreve com o `wlock` (é curto). Uma posição é válida se o grupo está sem lugar, todas as células estão dentro da grelha e nenhuma célula tem uma `colocada`, um lugar marcado cheio pelo Tiago (Q7 a; «cheia na foto» não bloqueia) ou outro grupo mostrado.
   - **Nada toca no log:** não há ação nova em `ACTIONS`, o `Board` só muda com fixar e soltar (como hoje), e `render_version()` não muda. Os checkouts antigos continuam a ler o log.
2. **Módulo puro `src/grupos.py`:** `footprint`, `valid`, `effective_position` (linha válida do `mesa.jsonl` → última fixação → nada), `initial_position` (Q3: o candidato 1 se a margem for ≥ `margin_min` e estiver livre, senão a posição válida mais perto do centro da vista que o browser envia), `rotate` (Q5 b: sem deslizar; se não couber devolve «Não cabe aqui rodado: move primeiro»), `sobreposto` (a posição gravada já não é válida: o grupo nunca salta sozinho), `count_loose`.
3. **A imagem do grupo montado**, no referencial local das células e a uma escala fixa por célula: `GET /api/grupos/{gid}.png?rot=`. As peças vão nas poses de `initial_theta` com uma âncora hipotética em (0, 0), compostas pelo caminho de `render.piece_ready`; LRU por (gid, rot, ppc, assinatura das peças).
4. **Endpoints:**
   - `GET /api/grupos`: lista, posição efetiva, footprint, «lugar provável» só com margem ≥ `margin_min` (Q4 b), `sobreposto`, `mostrado`.
   - `POST /api/grupos/{gid}/mostrar` {centro da vista}.
   - `POST /api/grupos/{gid}/mover` {l0, c0, rot}: sem reconsulta.
   - `POST /api/grupos/{gid}/fixar`: o `anchor` na posição atual, com `rot_fonte` e a verificação das vizinhas (§3).
   - Soltar = o `unanchor` de hoje.
   - SSE próprio `grupos_changed`, e **não** `board_changed`.
5. **Contagem no topo:** «N em grupos soltos» (T2), em que N = peças dos grupos visíveis sem lugar.

### Concorrência (orientador)
- `mover` / `mostrar` validam e escrevem dentro do `wlock`, por isso uma escrita do log (por exemplo um «Encaixa») não pode cruzar a validação.
- Um «Encaixa» que ponha uma peça por baixo de um grupo já mostrado é permitido (o alvo de uma sugestão desenha-se por cima do grupo, ESPEC §4.9). O `GET /api/grupos` seguinte marca o grupo `sobreposto`, que é derivado na leitura e nunca gravado. Um grupo nunca fica por cima de uma colocada sem estar marcado `sobreposto`. «Fixar aqui» fica desligado até ele ser movido.
- A escrita no `mesa.jsonl` faz append + flush dentro do `wlock`; a leitura usa `read_retry` e ignora uma última linha incompleta.

### Decisões de interface (Tiago, ou orientador aceite pelo Tiago, 2026-11-18; em `docs/decisoes.md`)
| # | Decisão |
|---|---|
| Q1 b | Só o grupo escolhido se desenha com imagem; os outros grupos mostrados ficam com contorno violeta ténue. |
| Q2 c | Os grupos de 1 peça são grupos; «Fixar» só dá confiança «confirmado» com a rotação confirmada (`rot_fonte` tiago ou vizinhas que confirmam). |
| Q3 (orientador) | Um grupo nunca mostrado não aparece no tabuleiro; aparece com «Mostrar no tabuleiro» na lista, que grava a posição. Posição inicial: o candidato 1 se a margem for ≥ `margin_min` e estiver livre, senão a posição válida mais perto do centro da vista. Uma posição gravada nunca muda sozinha. |
| Q4 b | O «lugar provável» a tracejado só aparece com margem ≥ `margin_min`. |
| Q5 b | «Rodar» não desliza; se não couber, diz «Não cabe aqui rodado: move primeiro». |
| Q6 b | No telemóvel só pelo botão «Mover» (um dedo arrasta até «Feito»). Manter o dedo premido fica para depois do teste no iPhone. |
| Q7 a | Bloqueiam: colocadas, lugares marcados cheios pelo Tiago, outros grupos mostrados. «Cheia na foto» não bloqueia. |
| Q8 a | «Fixar o grupo de N peças aqui? Confirma na mesa que está nesta rotação.» · Fixar / Cancelar. |
| Q9 c | Fica fixado, com aviso «As peças ao lado dizem outra rotação», «Desfazer» e as peças nas Suspeitas; um grupo de 1 peça fica «a confirmar» em vez de «confirmado». |
| Q10 a | Depois de «Tirar o grupo inteiro do lugar», o grupo fica no mesmo sítio, como grupo solto. |
| Q11 a | Na F3½, fora deste plano. |

---

## 2. Maquetes: o que cobrem e o que não cobrem

**Cobrem a F4:**
- `GrupoTabuleiro.dc.html`: o grupo violeta com sombra em cima do tabuleiro, o «Lugar provável» a tracejado, a barra Mover · Rodar · Fixar aqui, a legenda «Grupo solto: ainda não conta como montado» e «Ctrl + arrastar move o grupo», o painel «Grupo de 6 peças · Solto · ainda sem lugar certo no puzzle», a lista «Peças do grupo» (Saco · nº), «Levar para o lugar provável» / «Fixar aqui».
- `Grupos.dc.html`, em parte: o comutador «Peça a peça · N | Grupos soltos · N» e as linhas «4 peças · sacos 3, 7 e 9 · a confirmar por ti».

**Fora da F4 nas próprias maquetes:** os «+», «Acrescentar uma peça», «Tirar uma peça do grupo», «Desfazer o grupo»; «Como se juntam», «Vai buscar», «Juntei, encaixam», «Não encaixam», «Só algumas encaixam» (F4b); `JuntarGrupo` e `GrupoLigou`.

**O que nenhuma maquete desenha** (o comportamento já está decidido no §1; o aspeto segue o estilo das maquetes e vai às capturas para o OK do Tiago):
- o botão «Mostrar no tabuleiro» na linha da lista;
- o contorno ténue dos grupos não escolhidos;
- a frase de «Não cabe aqui rodado»;
- o modo «Mover» com «Feito» a 390 px;
- a confirmação de um clique;
- o aviso de rotação depois de fixar;
- o grupo `sobreposto`;
- o estado vazio («Não há grupos soltos.», ME10).

---

## 3. Como um grupo conta para o motor (e como não conta)

- **Grupo solto = nada para o motor.**
  - As peças ficam `em_seccao`, sem `celula`, e o `Board` não muda.
  - A posição vive só no `mesa.jsonl`, que o motor não lê.
  - Não é molde (`fit.hole_queries` só lê o `Board`), não é vizinha (`placed_neighbours_with_shape`, `query.mounted_neighbours`), não cria propostas de gémea colocada e não conta em `montar.progress`.
  - Não entra no raster nem no detalhe: é uma camada SVG por cima.
  - «Mover» e «Mostrar» não escrevem no log, não reconsultam, não emitem `board_changed` e não mudam `render_version()`.
- **Grupo fixado = peças colocadas.**
  - É o `section_anchored` de hoje, com `fonte: "manual"` e a posição efetiva do grupo.
  - As células ficam `colocada` com `legado_scan`, por isso contam como molde, vizinhas, gémeas («gémea colocada» propõe as gémeas das peças do grupo) e progresso.
  - Corre a reconsulta incremental, como no `anchor` de hoje.
  - Uma linha do `mesa.jsonl` escrita antes da fixação fica inválida por `log_n`.
- **Rotação confirmada pelas vizinhas ou pelo Tiago (lição P0833; no B2):**
  - **`rot_fonte`** ∈ {`tiago`, `programa`} entra no dict `anchor` do `section_anchored`. É uma chave extra num dict que já existe: `dict(_default_anchor(), **ev["anchor"])` aceita-a, e os checkouts antigos leem-na. O valor é `tiago` com o «Rodar» usado ou com a confirmação de um clique de Q8 a.
  - **Depois de fixar** corre a verificação de orientação de `src/consistency.py` (4 atribuições cíclicas, `legacy.side_compat`), só nas peças do grupo com vizinha montada fora do grupo. Dá `vizinhas: confirmam | discordam | sem_vizinhas`, por peça e global, e vai para o `anchor` e para a resposta.
  - **`confianca`**: `confirmado` se `rot_fonte == tiago` ou se as vizinhas confirmam; senão `a_confirmar`. Com Q9 c, um grupo de 1 peça cujas vizinhas discordam fica «a confirmar».
  - **Vizinhas que discordam:** o grupo fica fixado, com o aviso, «Desfazer» e as peças nas Suspeitas (já entram, porque passam a colocadas).
  - A margem dos candidatos compara lugares, não rotações: nunca decide a rotação sozinha.
- **A pose manual** (F3½, já feita antes do B1): `section_anchored` e `section_unanchored` já a limpam, por isso fixar ou soltar nunca herda uma pose antiga.

---

## 4. Critérios de aceitação (fixados antes do código)

**Funcionais [V por testes]**
1. Os grupos mostrados desenham-se na posição efetiva: o escolhido com imagem, contorno violeta e sombra; os outros com contorno ténue (Q1 b). As peças continuam clicáveis e o alvo das sugestões desenha-se por cima.
2. Mover (Ctrl+arrastar; botão «Mover»; no telemóvel só «Mover» … «Feito», Q6 b) anda de célula em célula. Uma posição inválida (fora da grelha, sobre uma colocada, sobre um lugar marcado cheio pelo Tiago, sobre outro grupo) volta para trás com uma frase. A posição sobrevive a recarregar e a outro browser, porque vem do `mesa.jsonl`. Mover → fixar → soltar deixa o grupo onde foi fixado, não na posição de antes.
3. «Mostrar no tabuleiro» (Q3), Rodar (Q5 b), Fixar aqui (confirmação de um clique, Q8 a) e «Tirar o grupo inteiro do lugar» (Q10 a) desfazem-se num clique (faixa «Desfazer» e Ctrl+Z, com o pedido inverso).
4. Fixar = peças colocadas: o progresso sobe N, as células passam a molde e a vizinhas, e as gémeas aparecem na reconsulta. Soltar repõe tudo (`Board` igual ao de antes de fixar).
5. Um grupo solto tem zero efeito no motor: `Board`, `fetch.json`, `/api/montar`, `board.jpg` e regiões ficam iguais antes e depois de N «Mover».
6. As regras de rotação do §3 têm testes: `rot_fonte`; vizinhas que confirmam, discordam ou não existem; grupo de 1 peça «a confirmar» com vizinhas que discordam.
7. Concorrência: um «Encaixa» simultâneo com um «Mover» nunca deixa um grupo por cima de uma colocada sem `sobreposto`.
8. Em `projects/alpes` (numa cópia): o log não muda com «Mover» e «Mostrar»; `check_invariants` limpo; as Suspeitas iguais às de depois da F3½.
9. ESPEC §6: sem termos da coluna «Hoje» na GUI nova (nada de G####, «âncora», «É aqui»); funciona a 1366×768 e a 390 px sem scroll horizontal; alvos ≥ 44 px.
10. A GUI antiga e os testes dela não mudam (Mesa incluída).

**Igualdade byte a byte**
11. Depois de 10 «Mover»: o log, `render_version()` e as bytes de `/api/board.jpg`, das regiões de detalhe e de `render/placements.json` ficam iguais, porque nada toca no log. E, sem grupos mostrados, as mesmas bytes que em `cc68ad4`.

**Desempenho** (guião `tools/diagnostico/gui/desempenho.py`, 10 pares alternados contra `cc68ad4`, na mesma máquina, sem outro agente na árvore)
12. «Perto» e «1.º salto»: o IC 95 % da diferença (depois − antes; t pareado e bootstrap, os dois reportados) **exclui +0,25 s**.
13. `POST …/mover` ≤ 0,3 s (mediana, com o `wlock`, sem reconsulta); `POST …/fixar` ≤ 2,0 s (o critério do POST «Encaixa»).
14. Arrastar um grupo 60 passos com todos os 32 grupos mostrados: 0 frames acima de 25 ms em Chromium headless (como na F2f).
15. `GET /api/grupos/{gid}.png` a frio ≤ 0,5 s para o maior grupo (8 peças); memória de pico a mais ≤ 50 MB.

**[NT] até o Tiago testar:** o iPhone real; fixar fisicamente ≥ 3 grupos (incluindo um de 1 peça); Firefox/Safari.

---

## 5. Testes antes do código, blocos, commits e paragens

Regras gerais:
- TDD: os testes novos falham antes do código, e o relatório diz quantos.
- A suite corre sempre com `.venv/Scripts/python.exe -m pytest tests/`.
- Um agente por árvore de trabalho: nunca a suite ou medições com outro agente a editar.
- `graphify update .` depois de mexer em código.
- Commits em português, sem co-autor.
- `docs/decisoes.md` e o ESPEC atualizados em cada bloco, com as decisões do agente marcadas como dele.

**B0 — Respostas e critérios (só documentos).** As respostas Q1–Q11, `mesa.jsonl`, `log_n`, concorrência e critérios em `docs/decisoes.md`; ESPEC §4.9 e §5.3. Commit `docs: F4, decisões e critérios`.
**PARAGEM 1:** a F3½ fecha antes do B1.

**B1 — `mesa.jsonl` (implementer).**
- Testes primeiro, em `tests/test_mesa.py`:
  - escrita e leitura; vale a última linha por grupo;
  - leitura tolerante (linha partida, última linha incompleta, grupo desconhecido, grupo fixado, posição inválida): ignora e conta, sem erro;
  - `log_n`: mover → fixar → soltar deixa o grupo onde foi fixado, não na posição de antes;
  - grupo nunca fixado sem linha → não mostrado;
  - validação na escrita (fora da grelha, colocada, marcada pelo Tiago, outro grupo; «cheia na foto» passa);
  - o log, o `Board` e `render_version()` iguais depois de N escritas.
- Código: `src/mesa.py`.
- Commit `estado: posição livre dos grupos soltos em mesa.jsonl`.

**B2 — Puro + servidor + rotação (implementer, skill `piece-fit-matching`).**
- Testes primeiro:
  - `tests/test_grupos.py` (puro): `effective_position`, `initial_position` (Q3), `valid`, `rotate` (Q5 b), `sobreposto`, `count_loose`, determinismo.
  - `tests/test_server_grupos.py`:
    - `GET /api/grupos` com o lugar provável só ≥ `margin_min`;
    - `mostrar` e `mover` sem reconsulta e sem `board_changed`;
    - critério 11 byte a byte;
    - `fixar` = `anchor` com `fonte manual`, `rot_fonte` e a verificação das vizinhas (confirmam / discordam / sem vizinhas, tabuleiro sintético; grupo de 1 peça «a confirmar» com vizinhas que discordam);
    - soltar com Q10 a;
    - PNG do grupo;
    - **concorrência**: um «Encaixa» e um «Mover» em fios ao mesmo tempo, 20 corridas, nunca um grupo sobre uma colocada sem `sobreposto`.
- Código: `src/grupos.py`, os endpoints, SSE `grupos_changed`, `montar.resumo` com a contagem, «N em grupos soltos» no `/api/montar`.
- Commit.

**B4 — GUI nova (helper, revisto pelo implementer nos gestos).**
- Testes Playwright primeiro, em `tests/test_gui_novo_f4.py`:
  - comutador «Peça a peça | Grupos soltos» e a lista;
  - «Mostrar no tabuleiro»;
  - desenho (Q1 b);
  - Ctrl+arrastar com encaixe às células e volta atrás numa posição inválida;
  - «Mover» … «Feito» (rato e toque CDP, Q6 b), sem partir os 12 testes de `test_gui_novo_toque.py`;
  - Rodar (Q5 b);
  - Fixar com a confirmação de Q8 a e o aviso de Q9 c;
  - Desfazer;
  - «Tirar o grupo inteiro do lugar»;
  - o alvo por cima do grupo;
  - `sobreposto`;
  - «N em grupos soltos» no topo;
  - a legenda «Grupo ainda sem ligação»;
  - o vazio «Não há grupos soltos.»;
  - 1366 e 390 px sem scroll horizontal.
- Código: `src/web/novo/` (camada `#lyr-grupos` por baixo dos alvos, barra e painel do grupo, lista). `board.js` só ganha um gancho novo declarado em `INTERFACE` (`tests/test_board_interface.py`); a GUI antiga fica sem mudança.
- Três commits: desenho e lista → mover e rodar → fixar e soltar.

**B5 — Medição e fecho.**
- Critérios 11–15 com o guião de desempenho (10 pares contra `cc68ad4`) e um guião de igualdade byte a byte (`tools/diagnostico/gui/f4_iguais.py`).
- Capturas `docs/gui/screenshots/redesenho/F4_{antes,depois}_*` a 1366 e a 390 px.
- Suite completa verde.
- Documentos: `docs/decisoes.md`, ESPEC §7, HANDOFF, `CLAUDE.md` (linhas de `server.py`, `src/web/novo/`, módulos novos `src/mesa.py` e `src/grupos.py`) e o ficheiro do prompt em `docs/prompts/`.
- Commit.
**PARAGEM 2:** se o critério 12 falhar (o IC não exclui +0,25 s) ou o 11 tiver uma diferença de um byte que seja, paro e reporto com os números, sem otimizar por conta própria.
**PARAGEM 3: OK do Tiago** (teste no PC e no iPhone, fixar fisicamente ≥ 3 grupos) antes da F4b.

**Backlog (não é da F4):** no painel de um grupo cuja escolha pela energia difere da imagem (margem < 1; hoje G0049), mostrar «a imagem prefere outro lugar».

## Ficheiros críticos
- `src/mesa.py` (novo: I/O do `mesa.jsonl`, `log_n`, validação, leitura tolerante)
- `src/grupos.py` (novo, puro)
- `src/server.py` (endpoints `/api/grupos*`, `wlock` no mover, `montar_json`)
- `src/state.py` (só lido: `anchor_section` / `unanchor_section`, `section_cell`, `write_atomic` / `read_retry`; o dict `anchor` ganha `rot_fonte` e `vizinhas`)
- `src/consistency.py` (só chamado: a verificação de orientação depois de fixar)
- `src/montar.py` (`resumo`)
- `src/render.py` (`initial_theta`, `piece_ready`, reaproveitados para a imagem do grupo)
- `src/web/novo/novo.js`, `novo.css`, `index.html`; `src/web/board.js` (só um gancho)

## Verificação ponta a ponta
1. `.venv/Scripts/python.exe -m pytest tests/` verde, incluindo `slow` e Playwright.
2. Numa cópia de `projects/alpes`: `python -m src.server` → `/novo/`. Mostrar, mover, rodar, recarregar (a posição fica, o log não mudou). Fixar um grupo (o progresso sobe, aparecem as gémeas), tirar o grupo inteiro (fica onde estava). `check_invariants` limpo.
3. Guiões de igualdade e de desempenho do B5, com os números no relatório e cada afirmação marcada [V] / [NT] / [F].
