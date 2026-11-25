# HANDOFF — 2026-11-25 (cache do tabuleiro corrigida; a seguir, o teste físico do Tiago aos grupos)

Lê isto primeiro numa sessão nova; no fim, atualiza-o e fecha o ficheiro do prompt em `docs/prompts/`.

## Sessão de 2026-11-25 (2): `docs/prompts/2026-11-25-miniaturas-intermitencias.md` (fechado)
- **Feito [V]** (`831ba65` + docs): miniaturas dos grupos só quando a linha entra na área visível (`IntersectionObserver`); cache do tabuleiro fica em JPEG (perda entre arranques aceite); `Claude outputs/` no `.gitignore`; `CLAUDE.md` com a cache e as miniaturas. Suite 907 passed, 1 skipped.
- **Intermitências [V]:** 20 corridas de `tests/test_gui*.py`: 7 com 1 falha, sempre num teste diferente (`initPointer/initVista is not defined`, `data-ready` a 60 s, `ERR_NO_BUFFER_SPACE`, 1 asserção de layout); `test_phone_layout_panels` não reproduziu [NT]. Causa [NT]; proposta no ficheiro da ronda e em `docs/decisoes.md`.
- **Para decidir:** registar `requestfailed` no `conftest` antes de mexer nos testes?

## Sessão de 2026-11-25 (cache do tabuleiro, P0395, grupos): `docs/prompts/2026-11-25-cache-tabuleiro-grupos.md` (fechado)
- **Cache do tabuleiro corrigida [V]:** o snapshot de `board_60` inclui agora a entrada de `placements.json` (`placement_digest`, `Gui._raster_snapshot`); a relva em falta (57 peças registadas depois de o tabuleiro se compor) volta a desenhar-se. 1.º arranque depois de atualizar recompõe o tabuleiro uma vez (≈ 20 s). `board_60.*` do projeto real apagado e refeito.
- **P0395:** peça inteira no scan [V com imagem], dados não mexidos (`docs/diagnostico/reports/P0395-2026-11-25.png`).
- **Grupos soltos na GUI nova:** «Corrigir recorte» e «Algo está errado» por peça no painel do grupo; miniatura de cada grupo na lista (PNG em fundo, todos os grupos).
- **Para decidir:** miniaturas de todos os grupos ou só dos da lista visível; cache em disco sem recodificar JPEG entre arranques; duas intermitências de GUI (`test_phone_layout_panels`, carregamento do `board.js`).

## Sessão de 2026-11-24 (F4b): `docs/prompts/2026-11-24-f4b-grupos.md` (fechado)
- **Estado da F4:** fechada do lado do código e do desempenho (`001ca99`..`bec3bb5`, mais a F4b `5bd56e5`). Montar aponta para os grupos soltos, abrir sem esperar pelos grupos, `/api/grupos` e os PNG sob `after_detail`.
- **F4b feita [V] (`5bd56e5`, `docs/decisoes.md` 2026-11-24 «F4b»):** (a) grupos com lugar provável (margem ≥ `margin_min`, zona calibrada, válidos) aparecem sozinhos no tabuleiro, derivados no servidor e nunca gravados; só «Mover»/«Rodar»/«Fixar» escrevem no `mesa.jsonl`; (b) a imagem aparece em todos os grupos mostrados, descarregada em fundo, um PNG de cada vez, depois do «pronto» e do 1.º detalhe. «Abrir + 1.º salto» 0,000 s, IC t [−0,077, +0,076] contra `bec3bb5` (limite +0,10) [V]; dados em `docs/diagnostico/gui/abertura-f4b/`.
- **Para saber:** no projeto real de hoje há 0 grupos derivados (4 com posição própria, 28 sem lugar provável servido): (a) só está exercida pelos testes sintéticos; o stress com 32 PNG saiu ruidoso e inconclusivo [NT]. Um grupo derivado cujo candidato fica ocupado desaparece (não fica «sobreposto»).
- **Falta:** o teste físico do Tiago aos grupos fixados (lista abaixo); texto do Montar «N grupos sem lugar: ver na interface completa» (`novo.js`) por corrigir. A suite da F4b correu uma vez sobre a árvore do código (900 passed, 1 skipped).
- **Achado antigo ainda aberto:** cada arranque do servidor re-codifica `render/gui/board_60.jpg` (anterior à F4, backlog).
- **Lista do teste do Tiago:**
  1. no PC, em `/novo/`: grupos com lugar provável já no tabuleiro; «Grupos soltos» → «Mostrar no tabuleiro» → Ctrl+arrastar e «Mover» … «Feito» → «Rodar» → recarregar (a posição fica);
  2. fixar fisicamente ≥ 3 grupos, um deles de 1 peça: «Fixar aqui» → confirmar na mesa; ver o progresso subir e as gémeas aparecerem; num grupo com aviso âmbar, ver se a rotação está mesmo errada;
  3. «Tirar o grupo inteiro do lugar» (fica onde estava) e o desfazer (faixa e Ctrl+Z) de mover, rodar, fixar e soltar;
  4. no iPhone: «Mover» com um dedo até «Feito», a lista e o painel do grupo a 390 px; [NT] Firefox/Safari, pinça com um dedo sobre o grupo.

## Sessão de 2026-11-23/24 (F4, abertura): `docs/prompts/2026-11-23-f4-abertura.md` (fechado)
- Resumo: `/api/grupos` e os PNG sob `after_detail`; «abrir + 1.º salto» −0,061 s [−0,171, +0,050] contra `cc68ad4` [V] (`docs/diagnostico/gui/abertura-f4/`); regra «todas as fases medem a abertura» em `docs/decisoes.md` (2026-11-24).

## Sessão de 2026-11-19 (F4, B5): medição e fecho (critérios 11–15) — `docs/prompts/2026-11-19-f4-b5-medicao.md` (fechado)
- **Critérios [V]** (cópia de `projects/alpes`, contra `cc68ad4`; números em `docs/decisoes.md` «F4 B5»):
  - 11: 10 «Mover» com 32 grupos mostrados, iguais byte a byte (log, `placements.json`, `render_version()`, `board.jpg`, regiões), e iguais ao `cc68ad4` sem grupos (`tools/diagnostico/gui/f4_iguais.py`);
  - 12: «perto» −0,011 s (IC t [−0,034, +0,012], bootstrap [−0,030, +0,008]); «1.º salto» −0,82 s (IC t [−1,11, −0,52]) (`pa_pares.py` + `f4_ic.py`);
  - 13: mover 23 ms, fixar 1,25 s (medianas; máx. 2,28 s); 14: máx. 16,8 ms, 0 frames > 25 ms; 15: PNG 0,477 s, +47,6 MB (alvos 0,5 s / 50 MB: pouca folga).

## Sessão de 2026-11-19 (F4, B4 etapas 2 e 3 de 3): mover, rodar, fixar e soltar na GUI nova
- **Feito:** Ctrl+arrastar e «Mover» … «Feito» (rato e toque), «Rodar» ±90, desfazer (faixa e Ctrl+Z), «Fixar aqui» com confirmação de um clique e o aviso âmbar («Esta peça diz outra rotação», «Desfazer» = `unanchor`), soltar = «Tirar o grupo inteiro do lugar» (Q10 a), correções M1–M4 e B1–B2 da revisão. `src/web/novo/grupos.js`, `tests/test_gui_novo_f4.py` (40). Commits `5a8c598`, `99d6c9c` e o da etapa 3. Decisões em `docs/decisoes.md` (2026-11-19). Capturas `docs/gui/screenshots/redesenho/F4_depois_*`. Ficheiro do prompt: `docs/prompts/2026-11-18-f4-b4-gui-grupos.md` (fechado).
- **Medido [V]:** critério 14 (60 passos, 32 grupos mostrados, cópia de `projects/alpes`, Chromium headless): máx. 16,8 ms, p95 16,7–16,8 ms, 0 frames > 25 ms.
- **B4 fechado** (2026-11-19): etapas 1–3 e as correções das revisões (M1–M5, A1, A1b, B1–B3, M3/M4 do implementer em `689c75a`); testes `tests/test_gui_novo_f4.py` (53). Decisão do Tiago M2 (âmbar com outro traço) em `docs/decisoes.md`.
- **Falta (B5):** critérios 11–13 e 15 com o guião de desempenho e o de igualdade byte a byte, o fecho dos documentos (ESPEC §7 se for preciso) e o OK do Tiago (PC e iPhone, fixar fisicamente ≥ 3 grupos, incluindo um de 1 peça). [NT] Firefox/Safari, pinça com um dedo sobre o grupo.
- **Para decidir/anotar:** o painel da peça (F2) mostra o `P####` (`#p-pid`), contra a ESPEC §6.

## Sessão de 2026-11-18 (F4, B4 etapa 1 de 3): desenho e lista dos grupos soltos na GUI nova
- **Feito:** `src/web/novo/grupos.js` (novo), camada `#lyr-grupos`, comutador «Peça a peça · N | Grupos soltos · N», lista com «Mostrar no tabuleiro», painel do grupo, lugar provável a tracejado, «N em grupos soltos», legenda, vazio, `sobreposto` visível, SSE `grupos_changed`; ponto 1 do Tiago no servidor (lugar provável só em zonas com `dE_p90`); `tests/test_gui_novo_f4.py` (13). Decisões 1–3 do Tiago, C1 e C2 e as minhas em `docs/decisoes.md` («F4 B4»). Ficheiro do prompt do B2b criado (reconstrução) em `docs/prompts/2026-11-18-f4-b2b-rotacao-lugar-provavel.md`.
- **Falta (etapas 2 e 3):** Ctrl+arrastar, «Mover» … «Feito», «Rodar», «Fixar» com o aviso âmbar, «Tirar o grupo inteiro do lugar», desfazer; a etapa 2 começa pela C1 (implementer, `src/mesa.py` e `src/server.py`).

## Sessão de 2026-11-18 (F4, B2½ + B2b): correções do diagnóstico da rotação
- **B2½ (diagnóstico, `docs/diagnostico/gui/F4_ROTACAO.md`, `tools/diagnostico/gui/f4_rotacao.py`):**
  - o «Fixar» e as Suspeitas usavam a mesma nota com entradas diferentes: re-scans (P0615), sem vizinhas do grupo, sem «explicada»;
  - o `lugar_provavel` era servido sem validade: 8 dos 10 candidatos 1 com vizinhas estão em células ocupadas; G0095 e G0096 estão sobre P1064.
- **B2b feito (decisões 1–3 do Tiago, `docs/decisoes.md` «F4 B2b»):**
  - `consistency.grade_at` é o único critério de orientação, chamado pelo `evaluate` e pelo «Fixar»;
  - o «Fixar» só avalia os membros que põe no tabuleiro, as vizinhas do grupo contam, uma posição inválida é recusada antes, e o aviso nomeia a peça;
  - `likely_place` só aceita candidatos válidos que a forma não contradiz, com a margem recalculada; nenhum lugar com um membro impossível em todas as rotações.
  - Testes `tests/test_grupos_criterio.py` (15, os 15 falhavam antes).
- **Medido numa cópia** [V]:
  - Suspeitas 18 = 18, item a item;
  - o `evaluate` antigo e o novo dão o mesmo em 5 tabuleiros perturbados;
  - lugares prováveis 6 → 4, e 5 com os candidatos recalculados (`tools/diagnostico/gui/f4_lugar.py`; todos `sem_vizinhas`).
- **Para o Tiago [NT]:**
  - as peças do legado não têm saco, por isso o aviso diz «Peça P####»;
  - recalcular de vez os candidatos dos grupos soltos no projeto real é uma escrita no log (`section_candidates_updated`), e não foi feito.
- **Backlog:** regra «é um re-scan» (n = 1); `anchor_section` põe um re-scan `same_as` numa célula livre (0 casos hoje).
- **Próximo passo:** o **B4 da F4** (GUI).

## Sessão de 2026-11-18 (F4, B2): `docs/prompts/2026-11-18-f4-b2-grupos.md` (fechado)
- **Feito (2 commits, `bf4aa8d` + o seguinte):** `src/grupos.py` (novo, puro), `log_sig` e `rodado` em `src/mesa.py`, `GET /api/grupos`, `POST /api/grupos/{gid}/mostrar|mover|fixar`, `GET /api/grupos/{gid}.png?rot=`, SSE `grupos_changed`, `fora_da_fila.grupos_soltos` em `/api/montar`. Soltar continua a ser o `unanchor` do `/api/confirm` (o grupo fica onde foi fixado, Q10 a). Nada em `src/web/`.
- **Regras (Tiago 1–3 + C1–C3 do orientador, `docs/decisoes.md` 2026-11-18 «F4 B2»):** `rot_fonte` decidido pelo servidor (linhas `rodado` do `mesa.jsonl` desde a última fixação/soltura); a verificação da rotação é peça a peça, só peças com vizinha montada fora do grupo, antes de gravar a âncora; vizinhas que discordam dão sempre `a_confirmar`; fixar recusa (409) um grupo não mostrado ou `sobreposto`; `log_sig` acaba com o passo manual de apagar o `mesa.jsonl` depois de reconstruir o log.
- **Medido numa cópia de `projects/alpes`** [V]: `mover` mediana 5,8 ms; `fixar` mediana 1,30 s (máx. 1,84 s); PNG do grupo de 8 peças a frio mediana 0,38 s, +43,5 MB de pico; verificação peça a peça 0,2 ms–0,26 s. Na própria âncora das 66 secções fixadas a verificação dá 59 confirmam / 5 inconclusivas / 2 discordam (P0343, falso alarme conhecido; P0615 no bloco G0051).
- **Para o Tiago ver [NT]:** nos candidatos 1 dos grupos soltos, 9 dos 10 com vizinhas montadas «discordam» da rotação (candidatos de 2026-11-02; podem estar desatualizados). Não há GUI ainda: o B4 desenha isto.
- **Próximo passo:** o **B4 da F4** (GUI nova, helper revisto pelo implementer nos gestos; `F4_PLANO.md` §5).

## Sessão de 2026-11-18 (F4, B1): posição livre dos grupos soltos em `mesa.jsonl`
- **Feito:** `src/mesa.py` (novo) e `tests/test_mesa.py` (16 testes; os 16 falhavam antes do código). Sem servidor, sem GUI, sem `src/state.py` nem `ACTIONS`. Decisões do implementer em `docs/decisoes.md` (2026-11-18, «F4 B1: `mesa.jsonl`»).
- **API:** `write_position(project, gid, l0, c0, rot, *, wlock, mirror=False, shown=None)` (valida e acrescenta; recusa com `{error, motivo, celula}`; o chamador tem o `wlock`), `read_positions(project) -> (posições, aviso por motivo)`, `effective_position` (linha → última fixação → None), `effective_positions`, `check_position`, `footprint`, `is_loose`, `last_anchor_index` (índice incremental em cache por caminho do log).
- **Medido numa cópia de `projects/alpes`** [V]: índice a frio 4,9 ms, quente 0,13 ms (contra 20 ms de `read_log`); `read_positions` 0,65 ms com os 32 grupos mostrados; `write_position` 1,4 ms; `check_invariants` limpo.
- **Próximo passo:** o B2 da F4 (feito, acima).

## Sessão de 2026-11-18 (F3½): `docs/prompts/2026-11-18-f3meio-pose-manual.md` (fechado)
- **Regra nova (decisão do Tiago):** uma pose manual nunca esconde as suspeitas de orientação; a peça é avaliada com o `k` da pose manual. `consistency.evaluate` perdeu `incluir_pose_manual`; só o falso alarme (assinatura com a pose manual) cala uma suspeita. Substitui a regra das 45° (Q11 a da F4, item 2 do backlog de 2026-11-16). `docs/decisoes.md` (2026-11-18, F3½).
- **Medido numa cópia** (`tools/diagnostico/reports/f3meio_pose_manual.py`) [V]: Suspeitas 18 = 18 (nenhuma nova); P0833 com a âncora antiga (rot 180) + pose +3° fica `melhor_rotacao` −90°; com a âncora certa, +5° nada e +90° sinalizada.
- **Backlog:** P0147 tem a rotação automática errada (Δθ 90,1°) tapada pela pose manual; se a pose for limpa, a rotação errada volta. Corrigir a origem numa ronda futura.
- **Próximo passo:** o B1 da F4 (feito, acima).

## Sessão de 2026-11-18 (F2f): `docs/prompts/2026-11-18-f2f-sugestoes-sempre.md` (fechado)
- **OK do Tiago da F1b à F2e** (ESPEC §7, `docs/decisoes.md`). Ronda **F2f**: as sugestões aparecem sempre no tabuleiro [V em Chromium headless; telemóvel real [NT]].
  - Alvos de todas as entradas da fila desenhados, também com outro lugar selecionado ou o painel aberto; atual forte com rótulo, outros ténues sem rótulo, escondidos com a célula < 16 px no ecrã (limiar escolhido por mim: 14,7 px no tabuleiro inteiro a 1366); tocar num ténue à vista escolhe o cartão (regra de hoje de `S.onBoardTap`, mantida).
  - Seleção de um lugar: branco tracejado com véu, distinto do âmbar. Testes `tests/test_gui_novo_f2f.py` (7; 5 falhavam antes); testes existentes alterados: nenhum; suite 723 passed, 1 skipped. Capturas `F2f_*`; desempenho com 60 cartões: 0 frames perdidos num arrasto.
- **O Tiago vê [NT]:** o aspeto com uma fila real de dezenas de cartões e o limiar de 16 px (se prefere 12, é a constante `FRACO_MIN_PX` em `src/web/novo/novo.js`).

## Sessão de 2026-11-18: `docs/prompts/2026-11-18-correcao-toque-multidedo.md` (fechado)
- **Toque multi-dedo no iPhone [V em Chromium com toque real CDP; iPhone [NT]]:** (a) vinha da F2e (2.º dedo não cancelava o toque pendente), (b) é anterior (`f8151d3`: dedo que fica no mapa de ponteiros). Corrigido em `src/web/board.js`; testes `tests/test_gui_novo_toque.py`; causas e decisões em `docs/decisoes.md` (2026-11-18).
- **O Tiago confirma no iPhone [NT]:** pinça sem aproximar, arrasto e toque depois da pinça, toque duplo. Os `erro_cliente` de 2026-11-18 eram só do Brave (`window.ethereum`).

## Última sessão (2026-11-17): `docs/prompts/2026-11-17-f2e-toque-duplo-transicoes.md` (fechado)
- **F2e [V em Chromium headless com toque emulado; iPhone real [NT]]:** transições de ≈ 180 ms (menu e painéis), «Fechar» com ícone X,
  toque duplo no tabuleiro (só touch: o simples espera 250 ms, o duplo aproxima 2×, limite ⅓ do ecrã), «Ver lugar» com a sugestão do
  cartão ao lado da arte e «Voltar ao cartão». Regras e «decisões minhas» em `docs/decisoes.md` (2026-11-17); capturas em
  `docs/gui/screenshots/redesenho/F2e_{antes,depois}_*` (`tools/gui/f2e_capturas.py`); testes `tests/test_gui_novo_f2e.py`.
- **O que o Tiago tem de ver [NT]:** o toque duplo no iPhone (se o WebKit ainda faz zoom da página), a sensação dos 180 ms e a
  espera de 250 ms no toque simples.
- **Renomeação:** a ronda de 2026-11-16 chama-se agora **F2d** (documentos); o código, `tests/test_gui_novo_f2c.py` e as capturas `F2c_*` da 2.ª ronda mantêm o nome antigo.

## Sessão anterior (2026-11-16): `docs/prompts/2026-11-16-teste-gui-p0833-f2d.md` (fechado)
- **P0833 (8,2) [V, físico]:** rodada 90° anti-horário pela âncora (`--unanchor G0068`, depois `--anchor G0068 8 2 --rot 90`), aplicado e confirmado pelo Tiago.
  - Origem: uma secção de uma só peça ancorada com confiança `alta` e a rotação decidida pela imagem do céu; a pose manual de 2026-11-07 escondia a suspeita.
  - Diagnóstico: `docs/diagnostico/reports/P0833-2026-11-16.md`.
  - R0035 fechado com nota. Os contornos manuais de hoje ficam: cortam a sombra.
  - O Tiago vai afinar à mão a pose de P0833.
- **P0343 (5,20):** confirmada certa pelo Tiago; falso alarme registado. Hoje: 0 suspeitas de orientação, 18 de recorte, 0 reports abertos.
- **F2d (`cbb189b`, antes «F2c, 2.ª ronda»):**
  - alvo do cartão atual: centra o lugar e faz piscar o «localizar»; «Ver lugar» abre o painel do lugar;
  - menu de três barras como separador;
  - grupo «Procurar» com Peça | Lugar;
  - rótulo do alvo escondido abaixo de 9 px de texto (a 390 px só aparece ao aproximar);
  - erros do browser vão para o registo de atividade (`erro_cliente`).
  Regras e «decisões minhas» em `docs/decisoes.md`; capturas em `F2c_{antes,depois}_*`.
- **O que o Tiago tem de ver [NT]:** a F2d no PC e no telemóvel. O rótulo a 390 px, «Ver lugar» e o menu a fechar por «Fechar»/Esc.
- **Backlog por decidir** (`docs/decisoes.md`, 2026-11-16):
  - a pose manual só para ajustes até ±15°; rotações maiores com «Rodar a peça 90°» pela âncora;
  - uma pose manual só esconde a suspeita abaixo de 45° face à âncora (substituído pela F3½ de 2026-11-18: nunca esconde);
  - uma secção de uma só peça só `alta` com a rotação confirmada pelas vizinhas;
  - o «Editar posicionamento» na F5: sem contornos por omissão, «Mostrar contornos» desligado (proposta minha, a confirmar na maquete), folgas como números.
- **Por gravar no git:** as alterações do Tiago em `projects/alpes` (log, overrides, secção G0068, reports).
- **Flake por provar:** `test_gui_novo_p0.py::…localizar_blinks…[fora]` falhou uma vez sob carga.
- **Próximo passo:** o Tiago testa a F2e; depois a **F4** (grupos soltos), com plano em `/plan`.

## Sessão anterior (2026-11-16): `docs/prompts/2026-11-16-pa-detalhe.md` (fechado)
- **Critério 3 fechado [V]** (`docs/diagnostico/gui/DETALHE.md` §13.10): 10 pares `8668365 | novo` (cada um na sua
  cópia completada): «perto» 2,24 → **0,28 s** (alvo 1,2; 10/10 remendados); próximo cartão +0,02 s (IC [−0,02, +0,09],
  alvo ≤ +0,25); POST «perto» −0,14 s; salto a frio no browser −0,05 s; `srv_frio_relva_s` 1,07 → 1,02 s; memória
  +52 MB. Nenhuma paragem.
- **Passo 0 [V]:** cada pedido em separado no «perto» (normal 0,73 s nesta sessão): só `/api/board` retido 0,66, só
  `/api/ghosts` 0,51, só `/api/montar` 0,43, os três 0,33; (a) browser (board + ghosts, ≤ 1 s) 0,37; (b) servidor (os
  três cedem, ≤ 1 s) 0,25. Próximo cartão hoje 1,77 s (quase todo o POST). **Escolha pela regra: (b)**, melhor 0,12 s
  > 0,1 s.
- **Bloco 1 (`a655066`) [V]:** só `src/server.py`: `Gui.priority` (registado num middleware ASGI, `DetailFirst`, à
  chegada do pedido de detalhe) e `Gui.after_detail` no início de `/api/board`, `/api/ghosts`, `/api/montar`, espera
  ≤ `DETALHE_ESPERA_S` = 1,0 s; 409/500 soltam logo; nenhum bloqueio de escrita; `/api/status.espera_detalhe`. Nada no
  browser (cobre as duas GUIs; a GUI antiga só tem o teste). 12 testes novos (11 falhavam antes, vários só por falta
  dos nomes novos), suite 660 passed, 1 skipped, `test_concorrencia` 20/20; testes existentes alterados: nenhum.
- **Fase de desempenho FECHADA (decisão do Tiago, 2026-11-16; DETALHE §11.13, `docs/decisoes.md`):** critérios 3, 4 e 5 [V];
  1 (1.º salto, ≈ 4–6 s conforme a máquina) e 2 (salto a frio 2,19 s contra 2 s) aceites como estão. Sem mais rondas.
- **Próximo passo:** o Tiago testa a GUI nova (`/novo/`; OK pendente da F1b à F2b). Depois, a **F4** (grupos soltos no
  tabuleiro), com plano em `/plan`.

## Sessão anterior (2026-11-15/16): `docs/prompts/2026-11-15-pb-correcao.md` (fechado)
- (O 1.º salto ficou aceite, fase fechada: ver topo.)
- **Regra de registo [V] (DETALHE §13.9, `docs/decisoes.md`):** «sem imagem» (`render.REGISTER_IMAGE = False`): nas 70
  juntas das 24 peças que a imagem movia, |gap| mediana 0,202 / p95 0,499 mm sem imagem contra 0,250 / 0,641 com. A
  regra entra na chave da entrada (`['regra', 'cantos']`) e é a mesma em todos os caminhos (as escritas da GUI usavam
  a imagem). Das 79 entradas antigas nenhuma tinha a imagem aceite.
- **Leitores [V]:** completar as 699 entradas não muda nenhuma proposta, suspeita, buraco nem «verificar»; só 3 textos
  `pose_reason` («registo (cantos, sem imagem)» → «registo»).
- **Bloco 1 (`6c66217`) [V]:** o servidor completa as entradas em falta no arranque, em fundo (depois dos fantasmas; o
  ranking dos buracos começa no fim dele), cede à GUI, commit sob o bloqueio de escrita com chave e `entry_token`
  verificados, grava o ficheiro **uma vez**; `rebuild_piece`/`rebuild_stale` voltam a registar as colocadas; aviso no
  arranque, `/api/status.placements`, `stale_assets.placements_em_falta`. Testes novos `tests/test_placements_completo.py`:
  8 falhavam, 1 passava (o contorno pela GUI já re-registava), 9/9 depois. Composição do tabuleiro igual byte a byte
  (tabuleiro inteiro e céu/relva a ppc 100). Preenchimento 5,2 s no arranque (3,3 s sozinho); **sem recomposição do
  tabuleiro** (a cache do disco recebe o `pl_mtime` novo); o 2.º arranque não preenche nem grava nada.
- **Na sessão do preenchimento** (uma vez): o 1.º salto foi 6,4–7,7 s e o 1.º «perto» recompõe a região inteira
  (`muitas_pecas`, 2,1–2,3 s), porque a região guardada antes do preenchimento tinha as peças «na hora».
- **10 pares `8668365 | novo` [V salvo o «perto»]:** «perto» 2,64 → **1,21 s [F, alvo 1,2]** (10/10 remendados);
  «longe» 0,38 s; POST «perto» −0,29 s; salto a frio −0,08 s (browser) e `srv_frio_relva_s` 1,48 → 1,41 s; memória
  +71 MB. Viés: na cópia completada o `8668365` aceita 0 entradas (chave com a regra) e regista as 699 na hora.
  **Paragem** (não se afinou): decomposição em §13.9, `_piece_jobs` 1,21 → 0,24 s; o resto é a disputa com os três
  pedidos paralelos (sem eles 0,38 s).
- **Para o Tiago:** ao arrancar o servidor em `projects/alpes` com este código, o 1.º arranque mostra o aviso «699
  peças colocadas sem registo… a completar em fundo» e completa-as em segundos; os seguintes não.

## Sessão anterior (2026-11-15): `docs/prompts/2026-11-15-perto-remendo.md` (fechado)
- **Próximo item: o 1.º salto** (critério 1, ≈ 5,6–6,1 s contra o alvo de 4 s). Fica inconclusivo por decisão do Tiago
  (§13.6: +0,36 s, IC [−0,14, +0,65]; nestes 10 pares +0,04 s, IC [−0,38, +0,35]) e passa a item próprio.
- **P-b diagnosticada (§13.8, `docs/prompts/2026-11-15-pb-placements.md`):** 620/699 peças sem entrada em `placements.json` (ficheiro ignorado desde `a249ad6` e nunca refeito + contornos gravados tiram a entrada); corrigir dá −0,3/−0,4 s, mas no 1.º salto `_piece_jobs` (4,2–4,6 s) é sobretudo a `ReadyCache` fria, não o registo (0,47 s): é aí que o item do 1.º salto deve começar. Correção A/B à espera do Tiago.
- **Passo 0 [V] (DETALHE §13.7):** os pedidos que o browser faz no `board_changed` (`/api/board`, `/api/ghosts`,
  `/api/montar`) custam ≈ 1,2 s ao «perto» (2,65 → 1,44 s, atrasando-os no lançador), sobretudo pela disputa do GIL no
  código Python da composição (registo na hora de 88 de 117 peças: 1,00 → 0,07 s). Fora da composição, os 0,2 s são o
  `_region_sig`. **Propostas, não implementadas, à espera do Tiago:** P-a (pedir esses três só depois do detalhe, ou
  fazê-los ceder ao detalhe; «perto» medido 0,44 s com o remendo), P-b (porque é que 88 peças não têm registo válido),
  P-c (memorizar a assinatura por peça).
- **Bloco 1 (`b7a88cf`), remendo [V em testes e na cópia real; critério 3 «perto» F]:** a região em cache redesenha só a zona das
  peças que mudaram (`render.compose_patch`, `PatchCache` 128 MB). Igual byte a byte em 8 casos sintéticos, no esforço e
  em 12 escritas na cópia real (0 diferenças). 10 pares: «perto» 2,51 → **1,60 s [F, alvo 1,2]**, 0/10 caíram na
  composição inteira; «longe» 0,27 s [V]; memória +99 MB [V]; **POST «perto» +0,12 s e salto a frio no browser +0,17 s
  com IC que não exclui +0,25 s [F]** (por HTTP +0,09 s, IC exclui). Paragem: não se afinou; decomposição nova em §13.7
  (o redesenho custa 0,07 s; o resto é `_piece_jobs` a disputar o GIL e a assinatura).
- **Bloco 2 (`1ba4b19`) [V em testes]:** `rank_all` só publica sem escrita pelo meio (senão recalcula; lista anterior marcada
  `desatualizada`); «verificar» repete e, sem resultado anterior, devolve «não verificado» e o browser pede outra vez
  (500 ms, até 3 vezes). 8 testes novos falhavam antes, 9/9 depois.
- **À espera do Tiago:** P-a / P-b / P-c; aceitar ou não o custo do remendo no salto a frio (+0,05–0,17 s) e no POST
  «perto».

## Sessão anterior (2026-11-15): `docs/prompts/2026-11-15-desempenho.md` (fechado)
- **Estado:** fase de desempenho do plano aprovado (`docs/diagnostico/gui/DETALHE.md` §11). Em `main`:
  - `64ac6e8` **P0 + P1**: a vista do Montar só segue o cartão por ação; «localizar» pisca quando o cartão muda sozinho;
    salto durante um arrasto espera pelo fim; portão no teste da fila; `gui.stop()` por fixture `autouse`; P1a, P1b.
  - `aae3a9d` **P0b** (A1–A4 + B): POST de um «Encaixa» 5,3–7,4 → 0,6–1,8 s; saídas iguais antes/depois; as suspeitas
    chegam depois da resposta.
  - `2d34c19` **parte 1**: formas por folha, lados em `render/fit/sides.npz`, chave das tiras pelo recorte, ranking ao
    arrancar; ranking a frio 33–46 → ≈ 5 s (41,8 s só no 1.º arranque depois de atualizar).
  - `3d616c3` **E**: peças prontas a desenhar (`ReadyCache`, 600 MB, pré-aquecimento); composição igual byte a byte;
    região quente 2,3–2,8 → 0,7–0,8 s.
  - `983ae98` **(b) alargada**: o trabalho de fundo (ranking, suspeitas, pré-aquecimento) cede enquanto há uma região de
    detalhe ou um «verificar» em curso; resultado igual (`tests/test_ceder.py`); 1.º «verificar» 0,21 s.
- **C PARADO, não fundido** (ramo `wip/desempenho-c`, `043435c`): as duas condições dos mosaicos confirmadas (colagens = 0
  px; motor independente, saídas iguais), mas a mudança contra a grelha de hoje na relva (24–38 % dos píxeis, até
  33–55 níveis; invisível à vista) excede o que o Tiago aceitou (≤ 5 níveis em ≤ 0,06 %), e com C os critérios 1 e 2
  pioram (7,2–7,7 s; 4,2 s). **Decisão do Tiago:** aceitar a mudança / outro limite, ou deixar C (§11.10).
- **Critérios em `main` (§11.11):** 1 (1.º salto) 3,76–4,41 s [F numa corrida], 2 (salto a frio no browser) 2,15–2,28 s
  [F], 3 (detalhe depois de um «Encaixa») 3,3–3,4 / 2,7 s [F; o encadeamento de recarga do browser fica ≈ 2,4 s mesmo
  com C], 4 0,21 s [V], 5 1,1 GB [V], POST [V].
- **No arranque as sugestões «pelo encaixe» chegam ≈ 3 s mais tarde** (6 s depois do «pronto»), porque o ranking cede
  ao 1.º salto; depois de uma escrita, iguais.
- **Medições:** `docs/diagnostico/gui/dados/r4_*.json`; guião `tools/diagnostico/gui/desempenho.py` (`--repo`, `--so
  a|b|p|q|r`, ouvinte SSE). As medições depois da parte 1 usam uma base com `sides.npz` (o estado depois do 1.º arranque).
- **Capturas:** `docs/diagnostico/gui/capturas/desempenho_{ceu,relva}_{antes,depois_E_b,depois_C}.jpg` (antes = depois de
  E + (b), byte a byte).
- **Ramos (2026-11-15, Tiago):** C fica fora (etiqueta `archive/desempenho-c`); `teste-a`/`teste-b`/`teste-b3` →
  etiquetas `archive/…`; `wip/desempenho-parte1` apagado. Só resta `main` (`docs/decisoes.md`).
- **Critério 3 e seqlock (2026-11-15, DETALHE §13):**
  - O seqlock das suspeitas está feito (sem bloqueio de escrita à 3.ª falha).
  - A chave das regiões passou a ser o conteúdo e o detalhe pede-se logo depois do SSE.
  - Em 5 pares alternados: «longe» 3,94 → 0,28 s [V]; «perto» 4,83 → 2,74 s [F]; os critérios 1 e 2 e o POST ficam
    iguais dentro do ruído.
  - O passo 0 mostrou que os 1,85 s eram a máquina, não o código; daqui em diante só se mede em pares alternados.
- **À espera do Tiago:** (1) corrigir o «verificar» e o `rank_all`, que no cenário «mover» devolvem estados que nunca
  existiram (§13.5); (2) o remendo das células alteradas para o «perto» (§13.4).

## Sessão anterior (2026-11-14): `docs/prompts/2026-11-14-f2c-correcoes-uso-real.md` (fechado)
- **Saco 9 · nº 89 em 1 · 29 encaixa fisicamente [V, Tiago]:** primeiro caso real de «pôr à mão»; a borda está completa (218/218).
- **Arranque [V em testes]:** `status.preparacao` + SSE `prepare_progress`; as duas GUIs mostram «A refazer imagens: folha n de N»
  (a nova também na barra do topo); `Gui.state` é `a_preparar` desde o 1.º instante. «A preparar sugestões…» na 1.ª vez.
- **Aviso vermelho [V + NT]:** a faixa «Ligação perdida» nunca aparece com o servidor vivo mas ocupado (teste). Reproduzido o
  texto que o Tiago leu: `core.js` velho em cache + `app.js` novo = «watchConnection is not defined». Correção:
  `Cache-Control: no-cache` nos ficheiros da página e `watchConnection` opcional. [NT] não sei qual dos dois ele viu; quem
  tiver o `core.js` velho precisa de um Ctrl+F5 uma vez.
- **Borda [V]:** `missing_border_cells()` = [] (não era defeito); o menu diz «Não falta nenhuma peça de borda.» O botão só existe na nova.
- **Lupa [V em testes; NT com o Tiago]:** dois botões «Peça» / «Posição», uma caixa que desliza (160 ms, desligada com
  `prefers-reduced-motion`), formatos «1,29 1 29 1.29 1-29» e «9 89 9/89 9,89 P1422», mensagens na própria caixa, último
  modo guardado (`novo-lupa-modo`; «/» abre-o). Destaque animado do resultado no tabuleiro até ao próximo toque.
- **Ctrl+C [V]:** uma linha, «Servidor parado.», código 0 (o uvicorn re-levantava o sinal → traceback).
- **Testes:** novo `tests/test_gui_f2c.py` (8), 2 em `tests/test_server_shutdown.py`, lupa reescrita em `tests/test_gui_novo_f2b.py`,
  helpers `_buscar_*` em `tests/test_gui_novo.py`. **Capturas:** `docs/gui/screenshots/F2c_*` (`tools/gui/f2c_capturas.py`).
- **Por ver pelo Tiago:** lupa e destaque no PC e no telemóvel; Ctrl+C no terminal dele; o arranque com ativos por refazer.

## Sessão anterior (2026-11-14): `docs/prompts/2026-11-14-f2b-correcoes-teste-tiago.md` (fechado)
- Lupa de separadores (substituída na F2c), `Gui.begin_shutdown` + `timeout_graceful_shutdown` 3 s, `Last-Event-ID` limitado a
  `gui.seq`, faixa «Ligação perdida» (`watchConnection`), lista `alta` mantida durante o recálculo (`_holes_prev`),
  indicador «A gravar…» / «A atualizar sugestões…». A reconsulta incremental registada em `estado-e-plano.md` não se reproduziu [NT].

## Sessão anterior (2026-11-14): `docs/prompts/2026-11-14-f2-passo0-painel-por-tirar.md` (fechado)
- **Passo 0a [V] (`6345154`, DETALHE.md §8.1):** com o servidor parado o intervalo de 0,5 ms não piora a composição
  sozinha (3 + 3 corridas: médias +6,6 a +9,3 %, medianas +1,0 a +5,8 %; 4 de controlo iguais). A diferença
  ronda 1 / ronda 2 é a forma de medir (o protocolo da ronda 2 sobrepunha o ranking dos buracos: 4,6–7,8 s).
- **Passo 0b [V] (DETALHE.md §8.2):** auditoria do que a composição e o «verificar» leem fora dos bloqueios; teste de
  esforço `tests/test_concorrencia.py` (HEAD de então: 21 em 22 corridas falhavam; agora 20/20). Corrigido: escritas
  atómicas (`state.write_atomic`), apagar e ler com repetição no Windows (`remove_file`, `read_retry`), célula lida uma
  vez na composição, geração da forma em cache, caches com (log, mtime de `placements.json`). Um 404 de `render/clean`
  visto 2× na HEAD antiga ficou sem origem encontrada (não voltou em 30 corridas instrumentadas).
- **F2 [V em testes; NT com o Tiago]** (decisões c e g em `docs/decisoes.md` e ESPEC §7):
  - tocar no tabuleiro: painel da peça (folha com a peça marcada, saco, nº, linha · coluna, P#### pequeno, «Tirar do
    lugar», «Corrigir recorte» → `/?peca=P####&contorno=1` na GUI antiga, «Algo está errado»), do lugar vazio (arte,
    sugestão, «Pôr uma peça aqui», «Já tem peça…») e do lugar marcado por ti; o 2.º toque no alvo do cartão atual abre o
    painel do lugar;
  - «Pôr uma peça à mão»: saco e nº (ou a grelha das soltas do saco), «Rodar», 3 verificações em palavras que não
    bloqueiam (`POST /api/cell/{l}/{c}/verificar`, sem bloqueio de escrita); grava `place` com uma vizinha colocada, senão
    «por confirmar» (decisão g);
  - par: desfazer «Encaixa» e «Tirar do lugar» desfazem só o que essa colocação fez (decisão c; ação nova
    `pair_unconfirmed`);
  - desfazer global de um nível (faixa + Ctrl+Z) para todas as ações dos painéis; «Ainda sem peças ao lado»;
  - «⋯ › Definições (cor das peças)»: brilho e saturação só no browser, inicial 0,92; também no tabuleiro (medido: 0
    frames perdidos, DETALHE.md §9.2).
- **Guião da borda, passos 1–7 numa cópia [V no programa]:** Saco 9 · nº 89 em 1 · 29 dá lado liso, forma e imagem com 3
  traços numa rotação (−171°) e falhas nas outras 3; pôr, tirar, desfazer e recarregar como no plano. «verificar» 0,6 s a
  frio, 3,2–4,5 s durante o ranking a frio, ≤ 0,05 s a quente (DETALHE.md §9.1).
- **Testes:** novos `test_concorrencia`, `test_f2` (11), `test_gui_novo_f2` (8); alterado `test_gui_novo` (4 textos).
- **Suite [V]:** `.venv/Scripts/python.exe -m pytest tests/`: 537 passed, 1 skipped (PyMuPDF real), 0 failed, 405 s com os slow/Playwright (passo 0: 517 passed, 1 skipped). Commits `6345154` (passo 0), `32c5f5c` (F2).
- **`CLAUDE.md` por atualizar** (linhas de `state.py`, `server.py`, `montar.py`/GUI nova): um subagente não lhe mexe.

## O que o Tiago tem de ver (F2)
1. `/novo/` no PC: tocar numa peça, num lugar vazio e em 1 · 29; o guião da borda (plano da F2 §5, passos 1–8): se o
   nº 89 encaixa fisicamente e se as verificações acertaram (1.º caso real de «pôr à mão»).
2. Telemóvel real (`--lan`), Firefox/Safari, e o filtro de cor numa GPU real [NT].
3. OK da F2 para seguir para a F4 (ordem F4, F4b, F4c, F3, F5, F6); a fase de desempenho (lados em disco, formas por
   folha, segundo plano, E, C) vem depois da F2, como pedido.

## Sessão anterior (2026-11-14): `docs/prompts/2026-11-14-detalhe-tabuleiro-ronda2.md` (fechado)
- Saltos sem espera, GIL 0,5 ms adotado, `_clean_or_crop` corrigido, causa do 1.º `/api/montar` (DETALHE.md §6–§7).
  Suite 516 passed, 1 skipped.

## Antes (2026-11-14): `docs/prompts/2026-11-14-detalhe-tabuleiro.md` (fechado)
- A + B do detalhe (`e252dc1`): regiões compostas fora do `rlock`, um só detalhe em voo (AbortController + `X-Detail-Seq`). Medições em `docs/diagnostico/gui/DETALHE.md` §1–§5; o problema é anterior à F1; o fio do browser nunca bloqueou. Suite 513 passed, 1 skipped.

## Antes (2026-11-14): `docs/prompts/2026-11-14-f1d-correcoes-gui-nova.md` (fechado)
- **F1d [V em testes; NT com o Tiago]** (regras em `docs/decisoes.md` 2026-11-14 F1d, ESPEC §2 e §7):
  - desfazer: causa = só havia um aviso de 9 s que aparecia ≈ 3 s depois do clique (o `POST` demora 3,4 s no real); agora faixa «última ação» com «Desfazer» no topo do painel até à ação seguinte;
  - cartões sem vizinha montada: «Colocar aqui» / «Não pertence aqui» (por dentro `position_known` / `reject`, sem «Porquê?»); a peça fica no tabuleiro «por confirmar» (imagem ténue + contorno tracejado da própria peça); verificado no código que a célula continua vazia para o motor (não é molde, nem vizinha, nem conta no progresso);
  - «localizar» (só ícone) no cartão; ícones Lucide locais em `src/web/novo/icons/` (ISC + MIT); menu «⋯» a toda a largura a 390 px;
  - ecrã vazio: «N peças guardadas à parte, no tabuleiro «por confirmar»…» (a linha «para guardar» saiu).
- **`test_twin_real` corre:** memória em `tests/data/ereal2_memoria.npz` (53 KB), refaz-se com `tools/diagnostico/gemeos/ereal2_fixture.py`.
- **Máscaras do Photoshop:** recortes do editor (caixa + 3 mm) de P1203, P0045, P1245, P0198 em `docs/diagnostico/editor/gt_photoshop/` com `LEIAME.md` e `recortes.json` (origem na folha); falta o Tiago fazer as máscaras.
- **Capturas:** `docs/gui/screenshots/redesenho/F1d_*` (cópia do estado atual: P0980 por confirmar em 38 · 3, 2 cartões sem vizinha).
- **Suite [V]:** 508 passed, 1 skipped, 0 failed (430 s, com os slow; +9 testes desde a F1c); o único skip é o PyMuPDF real no `test_sheets` (o `test_twin_real` já corre).
- **Scratchpad:** `alpes_base` e `proj` apagadas (nenhum teste/ferramenta as referia; caminhos verificados); cópias desta sessão também apagadas.
- Sessão anterior (2026-11-12): `test_sheets` nos dois caminhos, quadrados em JSON, negativos difíceis por zona (`docs/prompts/2026-11-12-test-sheets-montar-quadrados-json.md`).

## Estado (F1b, sessão anterior)
- **Prompt da sessão:** `docs/prompts/2026-11-11-f1b-casca-nova-montar.md` (fechado).
- **Commits** (em `main`, sem `projects/alpes`):
  - `c241ca0`: interface do `board.js` + prova estrutural da F1a;
  - `7524053`: F1b (código e testes);
  - `3578ad4`: docs e capturas;
  - `graphify update .` corrido no fim (`graphify-out/` está fora do git).
- **Suite [V]:** corre-se com `.venv/Scripts/python.exe -m pytest tests/`, não com o `python` do PATH.
  - O Python do sistema (3.12.6) tem PyMuPDF 1.28; desde `d24cb57` o `test_sheets` passa nos dois.
  - Em `8fedf87`: 460 passed, 1 skipped, 0 failed.
  - Depois da F1b: 477 passed, 1 skipped, 0 failed (293 s, com os `slow`; +17 testes novos).
- **Prova estrutural da F1a [V]** (`tools/gui/f1_estrutura.py`): SVG das camadas e caixas de 184–261 elementos do tabuleiro iguais antes/depois, nos 4 estados × 1366/390. A GUI antiga depois da F1b também é igual a `8fedf87`, na página inteira.
- **Interface do `board.js` [V]:** `S.board`, estados `S.showGrid` / `S.showGhost` / `S.pose`, função `S.onPoseWheel` (era o `poseWheel` global de `pose.js`), gancho `S.onBoardTap`. Está documentada no cabeçalho e testada por `tests/test_board_interface.py`.
- **F1b [V em testes; NT com o Tiago]:** GUI nova em `/novo/` (também `/?ui=novo` e `python -m src.server --ui novo`); a antiga continua em `/`.
  - Topo: «N de 3008 peças» (colocadas + marcadas por ti), abas Montar · Peças · Importar scan, lupa, «⋯».
  - Montar: cartão «Próxima peça» (saco e nº em grande, linha · coluna, confiança em palavras com 3 traços), **Encaixa** / **Não encaixa**, «Saltar por agora», «Porquê esta peça?», «A seguir» (3).
  - Tabuleiro: alvo âmbar «vai aqui», 3 seguintes ténues, legenda curta (2 entradas: «Onde vai a peça», «Por montar»).
  - Fila por saco (§8.2). «quase certo» só por origem × zona com n ≥ 10 e Wilson ≥ 0,80 (§8.3).
  - Desfazer «Encaixa» e «Não encaixa» (toast, «Enganei-me, desfazer», Ctrl+Z); motivo opcional «Porquê?».
  - Teclas: Enter, N, S, Ctrl+Z.
  - Servidor: `src/montar.py`, `GET /api/montar`; eventos `rejection_undone`, `pair_unrejected`, `rejection_noted`, `unplaced desfaz`. As decisões desfeitas não contam (`state.undone_decisions`, também em `fit.alta_counter` / `--relatorio`).
  - Regras que o ESPEC não fixava: `docs/decisoes.md` (2026-11-11, F1b).
- **Capturas [V]:** `docs/gui/screenshots/redesenho/F1b_{antes,montar,porque,nao,vazio}_{1366,390}.png` e `F1b_contagens.json`. No ecrã principal, palavras 951 → 72 e botões visíveis 13 → 15 a 1366 px.
- **No projeto real hoje a fila está vazia [V]:** as 3 gémeas não têm vizinha montada e as 2 `alta` estão em conflito. As capturas com cartões são do estado de `8fedf87`.
- **Reports:** não foram consultados nem tocados nesta sessão.

## Grupos soltos (sessão de 2026-11-12, só docs e ferramentas, sem `src/` nem `projects/`)
- **Prompt:** `docs/prompts/2026-11-12-quadrados-17-e-juncoes-de-grupos.md` (fechado).
- **Quadrados 17/17 [V, Tiago, 2026-11-11]:** o Tiago testou os 11–17 e encaixam todos; 10/10 + 7/7 = 17/17, todos no céu, Wilson inferior 0,82. A margem não discriminou (encaixou até 1,008); o método dos quadrados está esgotado nas soltas atuais. Registado em `docs/decisoes.md`, `docs/estado-e-plano.md` §3.9, `QUADRADOS.md` e ESPEC §8.6.
- **ESPEC:** «já no grupo N» nas figuras, listas e cartões de grupo; F4c (verificar as junções ao largar um grupo: encaixa com «Fixar», não encaixa com X, não sei sem marca; «Onde encaixa este grupo?»), pendente de medição (§4.9 e §7).
- **Medição das junções [V na amostra, ver limites]** (`docs/diagnostico/fit/GRUPOS_JUNCOES.md`, `tools/diagnostico/fit/grupos_juncoes*.py`): 115 blocos colocados (63 céu, 52 relva; montanha e vale sem dados) como grupos soltos, 86 840 posições erradas. Com 1 junção não se afirma nada (deslocados: falso «encaixa» 14 %, falso «não encaixa» 10 %, relva 20 %); com ≥ 4 junções o «encaixa» (critério B) teve 0 falsos em 4 733 posições e 0 em 115 blocos; na relva as junções custam o dobro do céu e `t_abs` falha mais; a posição gémea encaixa por forma (custo 0,54 contra 0,53) e só a imagem a separa (15 % de falhas na montanha e no vale).
- **O que falta para propor peças que façam crescer um grupo solto:** lista de 9 pontos no §4 do mesmo relatório (layout e rotação por peça guardados, regra F sem posição, pool sem peças de grupos, células virtuais, calibração por zona, eventos, pose no referencial do grupo, zona do grupo). Não implementado.
- **Decisão do Tiago por tomar:** aceitar (ou mudar) o mínimo de junções do relatório §3 (≥ 4 para afirmar «encaixa»; 1 não afirma; fora do céu só ≥ 5 para «não encaixa»). Os cortes de 5 % e 10 % foram escolhas minhas.

## O que o Tiago tem de ver (pendente [NT])
1. Arrancar `python -m src.server --ui novo` e abrir `/novo/`. Num telemóvel, abrir `http://<ip>:8765/novo/` com `--lan`.
2. Montar: o cartão, «Encaixa» num clique, o toast «Desfazer», «Não encaixa» → «Porquê?» → «Próxima peça» / «Enganei-me, desfazer», Ctrl+Z.
3. As palavras: «quase certo» só aparece no céu (gémea 46/46 e buraco 57/57 no log de hoje). Fora do céu diz sempre «a confirmar por ti».
4. F1c: o cartão «Guardar à parte» das 3 gémeas (alvo tracejado, «Guardei à parte» / «Não é esta» e o desfazer), o ecrã vazio com as contagens, a lupa («saco 4 nº 22», «38,3»).
   - Atenção [NT]: a peça do saco 4 nº 22 é clara (céu?) e o lugar 38 · 3 é verde (vale): a imagem pode estar a dizer «Não é esta».
5. F1d: depois de «Colocar aqui», a faixa «Desfazer» no topo do painel; a peça «por confirmar» no tabuleiro; o «localizar»; os ícones; a 390 px o menu «⋯».

## Espera pelo Tiago
1. **Gémeas sem vizinha montada na GUI nova:** feito na F1c (ver acima); falta o OK.
2. **Máscaras do Photoshop para a fase 2 do editor** (ronda 10): os recortes estão em `docs/diagnostico/editor/gt_photoshop/` (ver `LEIAME.md`); o Tiago grava por cima `P####.png` com transparência, mesmo tamanho; `recortes.json` dá a origem na folha.
3. Registar os 17 grupos montados no projeto (dados em `quadrados_17.json`; porta de escrita na F4b; `QUADRADOS.md`, «Como registar»). Não fazer sem ordem.
4. Anteriores: PDF vetorial (PyMuPDF no `.venv`?), lock entre processos, pares T0001/T0002/T0005, T0003/T0004, p90 por zona, P0343/P0833, corte c32|c33.

## Pendentes técnicos (por ordem)
1. **Fase de desempenho: C parado** (decisão do Tiago sobre a mudança de píxeis na relva, `DETALHE.md` §11.10); critérios 1–2 [F] em `main` (§11.11), critério 3 fechado em 2026-11-16 (§13.10); a seguir F4 (ordem F4, F4b, F4c, F3, F5, F6).
2. **Limites da F1b [NT]:**
   - «Peças» é só uma ligação para a interface completa (F3);
   - «⋯ › Atividade» abre a interface antiga noutro separador (F5);
   - «Ver números» mostra as razões técnicas no painel (F5: Diagnóstico).
3. **Traços [NT]:** os fatores de folga (½ do limite, 2× a margem mínima) não estão calibrados.
4. **Ações novas no log** (`rejection_undone`, `pair_unrejected`, `rejection_noted`; F1c: `position_cleared`): checkouts anteriores deixam de ler um log que as tenha.
5. **Limites da F1d [NT]:** a faixa «Desfazer» só existe nesta sessão do browser (recarregar perde-a; Ctrl+Z também); não testado em Firefox/Safari nem no telemóvel real; a imagem «por confirmar» só aparece com rotação conhecida (sem ela, só o tracejado da célula).
6. Da ronda 10: fase 2 do editor (condicional, por zona), possível sobre-corte no lado S, P0045/P0071/P1064 índice manual por 1 píxel, limiares `GANHO_MIN_MM2` / `GEMEA_RUIDO_MM`, cache das miniaturas `?v=`.
7. **Detalhe do tabuleiro** (DETALHE.md §7 e §5; depois da F2): lados erodidos em disco + formas por folha + ranking em segundo plano ao arrancar (o 1.º `/api/montar`) → E (cache por peça; único que ataca o frio de 2,9–3,5 s) → C (mosaicos). H e os saltos sem espera estão feitos.
8. Anteriores: verificar ativos no arranque das CLI; `append_override` escreve CRLF; passo «pares» N²; arranque a frio; GT fora do céu; pose manual 4–9 s; detetor de peça comida; (26,1)/(25,1).

## Convenções que mordem
- **Testes com o `.venv`** (`.venv/Scripts/python.exe -m pytest tests/`); a suite completa demora ≈ 300 s: correr em segundo plano.
- Nunca `taskkill //IM python.exe`: só por PID, listado e justificado. No Git Bash, preferir scripts `.py` no scratchpad a `python -` com heredoc.
- Nunca correr servidor/render/ingest sobre `projects/alpes` para medir: usar cópias (`tools/rebuild_scans.py --stale --also-missing` antes das linhas de base). Escritas reais só com o servidor parado, cópia de segurança e commit a seguir.
- `projects/alpes` tem alterações locais do Tiago no working tree (board, log, scans, fetch, overrides, pairs, `log.jsonl.bak-20261109`): não as tocar nem incluir em commits; `git add` só com caminhos explícitos.
- **Duas silhuetas:** quem lê o índice lê `contour_px` / npz, nunca `aresta_px`.
- `tools/diagnostico/**` precisam de `PPF_SCRATCH`. Commits em português, sem co-author.
- GUI nova: os textos do Montar não podem ter (l, c), P#### (só no `.pid` pequeno), mm, margem, ΔE, aceite/alta/ambígua (`tests/test_gui_novo.py::FORBIDDEN`).

## Links
- Redesenho:
  - `docs/gui/redesenho/ESPEC.md` (§7 fases, §8 decisões);
  - `F0_INVENTARIO.md`;
  - capturas e prova estrutural: `docs/gui/screenshots/redesenho/README.md`;
  - ferramentas: `tools/gui/f1a_capturas.py`, `tools/gui/f1_estrutura.py`, `tools/gui/f1b_capturas.py`.
- Ronda 10: `docs/diagnostico/editor/CONVENCAO.md` §6; decisões em `docs/decisoes.md`.
- Comandos de início de sessão: `python -m src.reports --project projects/alpes --list`; `python -m src.consistency --project projects/alpes`.
