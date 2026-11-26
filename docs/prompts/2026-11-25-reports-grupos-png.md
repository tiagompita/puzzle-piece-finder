# 2026-11-25 — reports nos grupos, imagem dos grupos, R0036 (P0395)

## Porquê

Teste do Tiago (25/11, PC) ao ponto 1 da F4b: OK, menos um defeito: um grupo que ainda não estava no tabuleiro, depois de «Mostrar no tabuleiro» e movido (sem Fixar), fica só com o contorno roxo e um fundo escuro, sem a imagem das peças (vários grupos). R0036: P0395 (S0013, folha de peças montadas, grupo G0033 de 1 peça) continua «mal lida» depois de o Tiago lhe gravar um contorno manual às 22:16 (classe BBFT, cordas 22,0 / 20,2 / 21,4 / 18,2 mm). Pedidos de GUI: flag vermelha nos reports abertos e seta de voltar no topo do painel do grupo.

## Decisões (Tiago, 25/11)

- D1. Uma peça ou grupo com report aberto mostra a flag a vermelho.
- D2. Quando o bug de um report é corrigido e verificado, o Claude pode fechá-lo (`--close R#### --nota`); se depende de confirmação física, fica aberto.
- D3. «Voltar à lista» no painel do grupo passa para cima, seta ao lado do título.
- D4. Permissão para push para `origin/main` no fim.
- D5. Um contorno manual do Tiago é a verdade de terreno da silhueta: nenhum código o rejeita, corrige, substitui, alisa, erode ou põe em dúvida; se algo derivado dele sai mal, o erro está no código que o usa.
- D6. A borda está completa: 218/218 células com peça, incluindo (1,29).

## Prompt verbatim

Agente: implementer (blocos B e C); helper (blocos A e D). Skills: systematic-debugging (B), cv-visual-verification (C), piece-fit-matching (C). Fazer até ao fim sem parar para perguntar; decisões pendentes numa lista no fim. Exceção: ação irreversível sobre projects/alpes ou images/ → pára e pergunta.

Ronda: docs/prompts/2026-11-25-reports-grupos-png.md (cria-o com Porquê / Decisões / Prompt verbatim; no fim o relatório final vai palavra por palavra para «Resultado»). Lê primeiro docs/HANDOFF.md. Vigilância de pieces/overlays (39/39) e git status no início, a meio e no fim. Trabalha numa cópia de projects/alpes para testes e medições; o projeto real só no bloco C, com as regras de lá. Suite sempre com .venv/Scripts/python.exe -m pytest tests/. Commits sem Claude como co-author. Teste que falha ANTES de cada correção; não alteres testes existentes para passar (se tiveres de alterar, lista-os no commit e no relatório). Capturas da GUI a 1366×768 e 390×844 em cada bloco de GUI (guarda-as em docs/gui/screenshots/2026-11-25/ e olha para elas).

Decisões do Tiago (25/11):
D1. Uma peça ou grupo com report aberto mostra a flag a vermelho.
D2. Quando tu corriges o bug de um report, podes fechá-lo tu (python -m src.reports --close R#### --nota "<o que foi feito + commit + evidência>"). Só fechas com o bug corrigido e verificado; se a correção depende de confirmação física do Tiago, deixa aberto e diz porquê. Atualiza a regra em CLAUDE.md (secção Reports: «close each report only with Tiago's say-so») e em docs/decisoes.md.
D3. No painel de um grupo, o «Voltar à lista» passa para cima, ao lado do título do grupo (ex.: «Grupo de 5 peças»), como seta (ícone arrow-left, aria-label «Voltar à lista»), sempre acessível sem descer a página.
D4. Tens permissão para fazer push para origin/main no fim (ver bloco E).
D5. Um contorno manual do Tiago é a verdade de terreno da silhueta dessa peça: é exato, sempre. Nenhum código o pode rejeitar, «corrigir», substituir, alisar, erodir ou trocar pelo automático, nem considerá-lo suspeito. Se algo derivado dele sai mal (cantos, lados, classe, cordas, pose, recorte, render, PNG), o erro está no código que o usa. Regista esta regra em CLAUDE.md e docs/decisoes.md (2026-11-25).
D6. A borda está completa: as 218 células têm peça, no programa e fisicamente, incluindo a (1,29). (A nota antiga «(1,29) vazia» do CLAUDE.md está desatualizada: corrige-a.)

Teste do Tiago (25/11, PC): ponto 1 da lista da F4b OK (mostrar, Ctrl+arrastar, Mover…Feito, Rodar, recarregar mantém a posição). Falhou: grupo que ainda não estava no tabuleiro → «Mostrar no tabuleiro» → movido (sem Fixar) → aparece só o contorno roxo e um fundo escuro, sem a imagem das peças. Repete-se com vários grupos.

== Bloco A (helper) — flag vermelha e seta de voltar ==
A1. Servidor: /api/grupos passa a trazer, por grupo, as peças com report aberto (reports_abertos: [{id, tipo, texto, piece}] ou equivalente mínimo) e um booleano tem_report. Usa reports.read_reports (uma leitura por pedido; mede o custo em /api/grupos na cópia, antes e depois, 5 pedidos quentes; critério: +≤ 20 ms na mediana). A cache de /api/grupos tem de se invalidar com escritas em reports.jsonl (o SSE suspeitas_changed já é emitido nas escritas de reports: confirma que a GUI nova recarrega os grupos nele, ou emite grupos_changed também).
A2. GUI nova: o botão «Algo está errado» (ícone flag) fica com a flag vermelha quando há report aberto para:
   - a peça, no painel da peça (novo.js reportBlock; d.reports_abertos já existe);
   - a peça, em cada linha do painel do grupo (grupos.js);
   - o grupo, no título do painel do grupo e na linha da lista «Grupos soltos» (qualquer peça do grupo com report aberto).
   Cor: vermelho com contraste ≥ 3:1 nos dois temas (verifica), mais aria-label/title «Tem um report aberto». Não uses só a cor: o texto «Já reportaste…» mantém-se no painel da peça e aparece também por peça no painel do grupo.
   Depois de enviar um report, a flag fica vermelha sem recarregar a página. Depois de o report ser fechado (CLI), volta ao normal no SSE seguinte.
A3. D3: seta de voltar no cabeçalho do painel do grupo, à esquerda do título; mantém o mesmo id #grp-voltar (ou atualiza os testes que o usam e lista-os). Remove o link de baixo, a menos que os testes de layout mostrem que faz falta. A seta tem alvo ≥ 44 px. Esc/«Voltar» continuam a funcionar como antes.
A4. Testes Playwright: (i) report enviado no painel do grupo → flag vermelha na peça, no título e na linha da lista; (ii) report fechado pelo CLI → flag normal depois do SSE; (iii) seta visível no topo sem scroll num grupo com 8 peças a 390×844, e volta à lista.

== Bloco B (implementer, systematic-debugging) — imagem dos grupos não aparece no tabuleiro ==
B1. Reproduz primeiro, num teste Playwright que falha, o cenário do Tiago: projeto com grupos sem lugar provável; abrir /novo/, «Grupos soltos», «Mostrar no tabuleiro» num grupo que não estava mostrado, Ctrl+arrastar/«Mover»…«Feito». Asserção: o <image class="grupo-img"> do grupo acaba com href igual a data-url e a imagem descodificada (naturalWidth > 0), em ≤ 5 s. Repete também: (a) com outro evento a mudar S.ver pelo meio (ex.: um report, um Encaixa noutro sítio), (b) «Rodar» (?rot= muda o endereço), (c) dois grupos mostrados seguidos.
B2. Hipóteses a provar ou eliminar com evidência (registo de rede do conftest, contagem de pedidos /api/grupos/*.png, estado de pngsOk/pngsP/pngsDeNovo), por esta ordem:
   H1. pngUrl = url + &v=S.ver: S.ver muda e o <image> desenhado tem um data-url que nunca é pedido (ou é pedido com outro v), porque carregarPngs só corre na recarga de /api/grupos e não no redesenho da camada.
   H2. carregarPngs não corre depois do «Mostrar»/«Mover»: o gate (data-ready e S.pngsLivre ou data-detail) ou o pngsP em voo fazem perder o pedido (pngsDeNovo não volta a calcular a lista certa).
   H3. A descarga falha (erro/timeout no servidor, 409/500, decode a falhar) e o catch engole o erro: «fica sem imagem até à próxima recarga dos grupos».
   H4. O servidor devolve a imagem mas com o rot errado, ou vazia/transparente (abre o PNG e olha para ele).
   Na máquina do Tiago, o registo de hoje (projects/alpes/logs/servidor-20261125.log) não tem nenhum pedido lento de /api/grupos/*.png; usa isso como dado, não como prova.
B3. Correção mínima para a causa provada. Requisitos: um grupo mostrado ou movido tem sempre a imagem pedida; uma falha de descarga não é silenciosa (erro para o registo via erro_cliente, uma nova tentativa com recuo, no máximo 2); a regra F4b de só descarregar depois do «pronto» + 1.º detalhe mantém-se; o arrasto não perde o elemento. Não mexas no board.js sem necessidade.
B4. Desempenho: «abrir + 1.º salto» medido como na F4b (pares alternados contra d72b194, limite +0,10 s no IC) e arrasto com 32 grupos (0 frames > 25 ms). Se falhar, diz e não ajustes o critério.

== Bloco C (implementer, cv-visual-verification) — R0036, P0395 «mal lida» ==
Dados: R0036 (aberto, 25/11 22:19, vista novo/grupo): «Peça pertencente à borda, já está colocada, está mal lida.» P0395, S0013 (montado_p05_300dpi.jpg, folha de vista explodida de peças MONTADAS), grupo G0033 de 1 peça, sem âncora. Às 22:16 o Tiago gravou um contorno manual (overrides.jsonl; piece_resegmented motivo manual). Esse contorno é exato (D5). Mesmo assim, o programa leu a partir dele classe BBFT e cordas 22,001 / 20,211 / 21,362 / 18,175 mm (nominal ≈ 18,5 × 17,9), e o Tiago vê a peça «completamente torta»; a captura R0036.png mostra a peça cortada à esquerda. A borda está completa (D6), e a peça está fisicamente colocada numa célula de borda.
C1. Diagnóstico com imagens (guarda em docs/diagnostico/reports/P0395-R0036/ e olha para elas): a folha original à volta da bbox (margem 200 px) com o contorno manual desenhado por cima; o recorte crops/P0395.png; o clean; o PNG do grupo G0033; a captura R0036.png. Mostra os 4 cantos e os 4 lados que o src.shape encontra no contorno manual, a rotação/pose usada e a bbox do recorte. Diz em que passo a leitura se estraga, partindo do contorno manual como verdade: cantos/lados (shape.analyse), classe/cordas, rotação de normalização, bbox/recorte, render/clean, PNG do grupo ou captura do report. Confirma também que o override de 22:16 é o que está a ser usado (latest_overrides) e que nenhum passo o substitui ou altera.
C2. Corrige o código que lê mal o contorno manual (teste que falha antes, com o contorno de P0395 como caso). Requisitos: o contorno manual entra intacto (ida e volta exata, como a regra de overrides); o E-sym fica bit a bit igual; as outras peças da folha S0013 e as outras 17+ peças com contorno manual ficam iguais, ou cada diferença é explicada com imagem e é uma melhoria; nenhuma alteração ao override do Tiago (overrides.jsonl só-acrescentar, e aqui não acrescentas nada a ele).
C3. Identidade da peça: como a borda está completa e P0395 vem de uma folha de peças montadas, a hipótese principal é ser a mesma peça física de uma célula de borda já com peça no índice (duplicado entre folhas montado_*). Com a forma corrigida, compara P0395 com as peças de borda colocadas (forma: shape.free_dist; imagem contra a peça e contra a arte na célula; gémea da célula) e dá o top-5 com custos e margem. Hipóteses alternativas a testar e reportar: a peça colocada nessa célula é outra (troca), ou a P0395 não é de borda (classe mal lida).
C4. Resolução, pelo caminho reversível: se o top-1 for único (margem ≥ margin_min e imagem coerente), liga P0395 a essa peça/célula pela ação do estado que exista para duplicados ou ancora G0033 nessa célula, só se a ação tiver desfazer, e mostra o tabuleiro antes/depois nessa zona. Se não existir ação reversível adequada, ou se o top-1 não for único, não mexes nos dados: decisão pendente com o top-5 e as imagens, e o que o Tiago tem de ver na mesa (célula e imagem).
C5. Fecha R0036 (D2) só se a leitura estiver corrigida e verificada (imagens + números) E a identidade estiver resolvida sem dúvida; senão deixa aberto e diz exatamente o que falta.
C6. Se o defeito de C1 afetar outras peças com contorno manual, lista-as (id, o que mudou, imagem antes/depois).

== Bloco D (helper) — pequenos ==
D-1. Texto do Montar «N grupos sem lugar: ver na interface completa» (novo.js ≈ 476, 488, 1265): aponta para «Grupos soltos» na GUI nova (o separador já existe), sem a palavra «interface completa». Teste.
D-2. CLAUDE.md (D5, D6, regra dos reports D2), ARCHITECTURE.md (se mudarem contratos), docs/decisoes.md (D1–D6 datadas 2026-11-25), docs/HANDOFF.md. graphify update .

== Bloco E — verificação final e push ==
E1. Suite completa (com slow) e 3 corridas de tests/test_gui*.py, uma de cada vez. Registo de rede ligado; se aparecer falha intermitente, guarda a secção «Registo de rede das paginas» e não repitas a corrida para a esconder.
E2. Vigilância 39/39, git status limpo. Confirma: git log origin/main..main --format=%B | grep -ci co-author → 0. Se der > 0, pára e não faças push.
E3. git push origin main. Reporta o hash do HEAD remoto depois do push (git ls-remote origin main).

Regras de paragem: se B1 não reproduzir em 3 tentativas (incluindo com S.ver a mudar e rot), pára o bloco B, entrega o registo do que tentaste e um guião de 5 passos para o Tiago reproduzir com a consola aberta; segue para C, D e E. Se a correção de C2 mudar o E-sym ou peças sem contorno manual de forma que não seja claramente melhoria, não promovas: deixa num ramo e decisão pendente. Em nenhum caso o contorno manual do Tiago é alterado ou posto em dúvida.

Relatório final (palavra por palavra no «Resultado»): commits; ficheiros; por bloco [V]/[NT]/[F] com números e capturas; causa provada do B (ou não); R0036 (passo onde a leitura se estragava, correção, identidade da peça, estado, nota, imagens); medições; suite; push (hash); decisões pendentes para o Tiago.

## Resultado

**Commits:** `d6672aa` (dados do Tiago 25/11), `9dfb6f5` (prompt), `503103b` (A), `c66faf6` + `c2f9c90` (B), `d2e49e9` + `c8272bc` (C), `e729ea5` (D), e o commit que fecha este ficheiro com os registos das falhas do E.

**Bloco A [V]:** `/api/grupos` com `reports_abertos` e `tem_report`. Custo na cópia, 5 pedidos quentes, mediana 55,2 → 54,1 ms. Não há cache no servidor a invalidar. A GUI nova passa a ouvir `suspeitas_changed` e recarrega os grupos. A flag fica vermelha na peça, em cada linha do painel do grupo, no título e na linha da lista, com `aria-label`/`title` «Tem um report aberto» e o texto «Já reportaste…». Contraste de #ff6b5f: 4,27–6,55:1 em todos os fundos do tema escuro. A GUI nova só tem tema escuro; sobre branco daria 2,79:1. Seta `#grp-voltar` no cabeçalho (sticky, 44 px); o link de baixo saiu. Testes: `tests/test_server_grupos_reports.py` (4) e `tests/test_gui_novo_reports_grupos.py` (4); falhavam antes, menos 1 de servidor que já passava. Nenhum teste existente alterado. Capturas: `docs/gui/screenshots/2026-11-25/A_*.png`. O fecho pela CLI está testado com o SSE emitido à mão [NT pelo caminho da mudança externa do log].

**Bloco B: causa provada [V].** `carregarPngs` fazia `pngsP = (async () => {try…finally{pngsP = null}})()`. Sem nada a pedir, o corpo corria todo de forma síncrona e o `finally` corria antes da atribuição. `pngsP` ficava para sempre com uma promessa resolvida, e cada chamada seguinte só marcava `pngsDeNovo` e saía. Depois de uma escrita (`S.ver` novo), a imagem nunca era pedida. Evidência: 0 pedidos de PNG depois da escrita, `pngsP` verdadeiro, nenhum `decode` pendente. H1, H3 e H4 eliminadas: o PNG de G0080 tem conteúdo e o rot está certo. Correção em `c66faf6`: `await null` antes do `try`, `descarregarPng` com 2 novas tentativas (recuo de 500 e 1500 ms) e erro para o registo, e um `<image>` sem `href` chama `carregarPngs` no redesenho. A regra F4b mantém-se e `board.js` não foi tocado. Testes `tests/test_gui_novo_b_grupos_png.py` (8): 4 falhavam antes, 8 passam depois. Capturas: `B_grupo_{mostrado,movido}_{1366,390}.png`, com a imagem visível.
- **B4:** arrasto com 32 grupos [V]: máx. 16,8 ms, 0 frames > 25 ms. «Abrir + 1.º salto» **[F pelo critério]**: −0,139 s, IC t [−0,450, +0,172] contra `d72b194` (limite +0,10). A máquina abrandou a meio da série. Não foi repetido nem ajustado. Dados em `docs/diagnostico/gui/abertura-b-png/`.
- **[NT] na máquina do Tiago:** `git pull`, recarregar e «Mostrar» → mover → ver a imagem.

**Bloco C, R0036.**
- **Onde se estragava [V]:** o override em uso é o de 22:16:40 (`latest_overrides`). A aresta pintada pelo Tiago está exata (BFBT; 17,90 / 17,71 / 17,12 / 18,22 mm). O índice (`contour_px`) que `strokes.normalizar` deriva ao gravar ficou igual ao automático: o halo da convenção do índice não tinha limite de distância e apanhou a faixa escura do scanner, até 13,85 mm fora da aresta. Daí vinham um canto na faixa, BBFT 22,00 / 20,21 / 21,36 / 18,18, θ +8,19° e o centro deslocado 5,9 mm (peça «torta» e cortada à esquerda).
- **Correção `d2e49e9`:** `strokes.limitar_indice` (`INDICE_HALO_MAX_MM` 2,0: aresta + índice a ≤ 2 mm que não seja papel; a aresta fica sempre inteira) e `overrides.index_contour[_from]`, usados em `render.rebuild_assets`, `render._manual_pending`, `server._dense` e `server._solve_a2`. Resultado: BFBT 18,31 / 18,53 / 18,23 / 18,38 mm, 359,4 mm², θ −8,40°, PNG do grupo inteiro e direito. O contorno do Tiago ficou intacto: `overrides.jsonl` igual byte a byte, nada acrescentado.
- **Testes e comparações:** `tests/test_indice_aresta.py` (3) falhava antes. E-sym sem código de segmentação tocado; os testes slow do E-sym e das gémeas reais passam. As outras 9 linhas manuais ativas e as 25 só de ecrã estão dentro da banda (iguais). Em S0013 só mudou P0395.
- **Dados reais (`c8272bc`):** 1 evento `piece_resegmented` (2026-11-25T23:38:59, P0395, motivo `manual`), pelo caminho normal `rebuild_piece`. Invariantes OK.
- **Identidade:** P0395 é um segundo scan de **P0021 em (47,56)** (relva, fila de baixo). Forma: 0,470 mm. Imagem: NCC 0,965 na tabela do `RELATORIO.md`, contra ≤ 0,585 para as outras. As outras do top-5 por forma são céu, com imagem incompatível: P0782 0,390, P0005 0,482 (gémea), P0755, P0820. Nota crítica: os rótulos da figura `07_identidade_top5.png` dizem NCC 0,355 para P0021 e não 0,965. Parece outra variante da métrica (sem registo); a ordem é a mesma e as imagens são visivelmente a mesma peça, mas a incoerência fica por explicar [NT]. A troca e a hipótese de não ser borda foram rejeitadas. Sem arte na fila 47.
- **Estado:** **R0036 aberto.** O `same_as` P0395 → P0021 não tem evento de desfazer, por isso não foi aplicado. Ancorar G0033 poria uma 2.ª peça em (47,56). Imagens e relatório em `docs/diagnostico/reports/P0395-R0036/`.
- **C6:** nenhuma outra peça com contorno manual mudou.

**Bloco D [V]:** o texto do Montar já tinha sido corrigido em `001ca99` («ver em «Grupos soltos»», `#m-ver-grupos`), coberto por `test_empty_screen_counts_groups_only`, por isso não houve teste novo. Capturas `D_*.png`. Atualizados CLAUDE.md (D5, D6, D2, linhas de strokes/overrides e web/novo), ARCHITECTURE.md, `docs/decisoes.md` (2026-11-25) e HANDOFF. `graphify update .` corrido.

**Bloco E:**
- **Suite completa (com slow):** 927 passed, 1 skipped, **1 failed**: `test_gui_novo_f2b.py::test_lupa_box_slides_in_at_most_200ms_and_not_with_reduced_motion`.
- **3 corridas de `tests/test_gui*.py`:** cada uma com 327 passed e **1 failed**, sempre num teste diferente:
  - (1) `test_b3_falha_da_descarga_tenta_de_novo_e_vai_para_o_registo`: `EncodingError` no `decode` do próprio teste, 500 no registo de rede;
  - (2) `test_b2_carregar_sem_nada_a_pedir_nao_fica_em_voo`: `pngsP === null` falso no instante da asserção;
  - (3) `test_gui_fila.py::test_queue_tab_and_live_job[390-844]`: 2 botões de atividade em vez de 1.
- Não repeti nenhuma corrida. As secções de falha com o registo de rede estão em `docs/diagnostico/gui/E-2026-11-25/falha_*.txt`. **Dois dos testes intermitentes são novos desta ronda (b2, b3).** O b2 afirma um estado momentâneo, e pode haver um PNG legítimo em voo (miniaturas). São fragilidade do teste ou um defeito real [NT].
- **Vigilância:** 39/39 no início, a meio e no fim; `git status` limpo; co-author em `origin/main..main` = 0.

**Push:** `git push origin main`; o hash remoto vai no relatório do chat (`git ls-remote origin main`), porque é o do commit que fecha este ficheiro.

**Decisões pendentes para o Tiago:**
1. Confirmar na mesa que a peça em (47,56) é a da folha `montado_p05` (`07_identidade_top5.png`). Depois, autorizar o `same_as` P0395 → P0021 (sem desfazer) ou pedir primeiro um evento que o desfaça; só então se fecha o R0036.
2. «Abrir + 1.º salto» [F] (+0,172 no limite do IC, máquina a abrandar): repetir 10 pares com a máquina parada ou aceitar.
3. Os testes novos b2/b3 intermitentes (2 em 3 corridas): pôr o implementer a torná-los robustos (esperar pelo estado em vez de o ler num instante) ou investigar se há defeito real.
4. Reparos das capturas do B: o painel do grupo abre descido depois do «Mostrar» (1366), e um tracejado «lugar provável» aparece junto a um grupo cujo painel diz «Ainda sem lugar provável fiável».
5. P0395 continua com `touches_frame: true` herdado (informativo); `overrides --pares` ainda mede o `contour_px` gravado e não o índice efetivo.
6. Tema claro: se vier a existir, a flag precisa de um vermelho mais escuro (#ff6b5f sobre branco dá 2,79:1).
7. A incoerência NCC 0,965 (tabela) / 0,355 (figura) no diagnóstico de P0395.

