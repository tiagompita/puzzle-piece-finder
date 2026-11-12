# Decisões

Registo curto de decisões e hipóteses refutadas, com os números que as sustentam.

## 2026-11-05 — trim de 0,48 mm no desenho do tabuleiro: refutado

**Decisão:** o trim de `calibration.celula_silhueta.offset_mm` (0,48 mm) aplicado às silhuetas no desenho do tabuleiro e nas miniaturas fica fora. O código foi removido do working tree (nunca foi commitado; guardado no bundle `D:\DEKSTOP\ppf-branches-teste.bundle`).

**Evidência:** trim 0,48 mm refutado: piora 44 células, melhora 0; causa dos buracos é pose/recorte, não escala. Medido em `projects/alpes` (589 peças colocadas, `compose_board` a 120 px/célula, fundo magenta, buraco = fração da célula, inset 0,4 mm):

| variante | células com buraco > 5 % | > 10 % | média |
|---|---|---|---|
| sem trim (referência) | 131 | 39 | 0,0309 |
| trim 0,48 mm | 179 | 73 | 0,0464 |
| trim 0,24 mm | 137 | 45 | 0,0335 |
| sem trim + lado reto alinhado (208 peças de borda) | 132 | 38 | 0,0312 |
| trim 0,48 mm + lado reto alinhado | 183 | 74 | 0,0470 |

O trim expõe o fundo nos tabs/blanks porque a pose tem erro de cerca de 1 mm; alinhar a rotação do lado reto das peças de moldura não melhora nada. Rotação dos 588 colocados face a múltiplos de 90°: 363 com desvio > 1,5° (mediana 2,1°); nas 215 de borda a inclinação mediana do lado reto é 0,9°. Folgas entre vizinhas (917 junções): 23 com |folga| > 0,8 mm, mediana 0,19 mm.

**Pendente (não corrigido):** melhorar a pose/recorte; baseline acima.

## 2026-11-06 — verde na borda no tabuleiro: regra do papel escurecido também no `compose_board`, encaixes de papel tirados

**Decisão:** `BOARD_SHADOW = True`: o tabuleiro aplica a regra das miniaturas (`shadow_paper_mask`, 0,4 mm, RENDER §6.1), e a sangria mantém a silhueta limpa com a orla pintada da cor funda, para os buracos não mudarem. `PAPER_POCKETS = True`: as componentes da própria cor do papel (d < 15) que chegam à banda de 0,7 mm saem das miniaturas e do tabuleiro, com um limite de 10 % da peça. Nada muda no índice, em `clean_crop` nem em `render/clean/`.

**Evidência** (RENDER §7):
- **6 peças reportadas:** contorno desenhado com verde 10–53 % → 0,5–21 %.
- **Amostra de 100:** nenhuma piora; esverdeado −80 %.
- **Buracos:** 70/10 iguais com e sem a regra.
- **Encaixe de P0778:** 1694 → 0 píxeis da cor do papel.

**Falha registada [F]:** a porta do §6.1 falha em 7/100 (5 de relva, perda nos lados iluminados 1,55–1,84 % contra 1,5 %, vistas: só sai a orla; P0199 com 62 px; P0555, onde B tira 0,09 mm² de papel do interior).

**Pendente:** as meias-luas a 0,4–0,8 mm dentro dos encaixes (alargar a faixa é outra decisão) e o prado de P0198 com a cor do papel (o «comido» do R0019, [NT]).

## 2026-11-07 — decisões do Tiago (ronda 3): porta §6.1, moldura, P0395, c32|c33

Registo das decisões comunicadas pelo Tiago no prompt da ronda 3 (`docs/prompts/2026-11-07c-r0011-r0012-gt-editor-tracos.md`). Nada destas quatro foi implementado.

1. **Porta §6.1 (perda nos lados iluminados ≤ 1,5 %): fica como está.** Os recortes estão bons no geral; **não** se implementam as opções A (medir só na faixa de 0,4 mm) nem B (limite 2,0 % + bolsas interiores ≤ 0,1 mm²) de TRIAGEM-2026-11-07 §4. As **49/607** peças colocadas que falham 1,5 % (todas relva, filas 42–47; mediana da relva 1,12 %, p90 1,68 %; 13 falham 2,0 %; máximo 5,65 % em P0462; bolsas interiores ≤ 0,093 mm²) ficam registadas como **exceção aceite** da porta, não como defeito a corrigir.
2. **Moldura (R0022, P0240/P0590): não incomoda.** `F_TRANSLATION` continua desligado (RENDER §9: porta [F], 60 juntas pioram > 0,2 mm, buracos 67/9 → 71/11); o arranjo global proposto não avança.
3. **P0395 (S0013 #50):** o Tiago concorda que a flag `suspeita_recorte` (apêndice 14,5 mm) apanhou uma linha escura **real** da peça; nada a corrigir no recorte.
4. **R0002/R0003 ((3,32)/(3,33) = P0294/P0291): dados certos.** O corte vertical c32|c33 não simétrico nas filas 1–3/45–47 (ORIENTACOES §D: `free_dist` 2,36–3,08 mm nos 6 pares gémeos, contra mediana 0,31 nos outros 249) **continua por confirmar fisicamente**; a exceção no perfil fica adiada até essa confirmação.

## 2026-11-07 — editor de contorno por traços: solver GrabCut em Lab só croma (2 iterações)

**Decisão:** a zona «incerta» do editor de traços é resolvida no servidor por `cv2.grabCut` sobre a imagem Lab sem o canal L\* (`peso_l = 0`), 2 iterações, faixa automática de ±1,0 mm à volta do contorno atual e alcance de 1,0 mm, limpeza de 0,3 mm (`src/strokes.py`, `SOLVER_OMISSAO`). O watershed com marcadores e o limiar do segmentador ficam disponíveis como alternativas (`solvers`), não por omissão. Sem scikit-image/scipy (random walker fora): nenhuma dependência nova.

**Evidência** (`docs/diagnostico/editor/TRACOS.md`; GT = as 2 máscaras manuais de P0651/P0657, traços sintéticos; média das 2 peças; índice atual IoU 0,846, p95 1,35 mm):

| solver | trimap automático + 1 laço «incerto» na mordida: IoU / p95 mm / ms | só um laço largo do utilizador: IoU / p95 / ms | faixa do utilizador deslocada para dentro: IoU / p95 |
|---|---|---|---|
| **GrabCut Lab só croma, 2 it.** | **0,943 / 0,63 / 236** | **0,939 / 0,67 / 245** | **0,936 / 0,68** |
| GrabCut RGB, 3 it. | 0,909 / 0,74 / 325 | 0,905 / 0,80 / 351 | 0,893 / 0,99 |
| watershed cor (Lab só croma) | 0,940 / 0,69 / 17 | 0,934 / 0,81 / 18 | 0,721 / 5,72 (perde meia peça em P0657) |
| limiar do segmentador | 0,842 / 1,36 / 15 | 0,829 / 1,51 / 15 | 0,841 / 1,40 |

- Porquê só croma: a sombra projetada tem o a\* do papel (91 contra 79 do papel e 106–113 da peça) e a orla iluminada tem o a\* da peça; em RGB o GrabCut perde a orla e o limiar fica com a sombra **[V]**.
- 2 iterações ficam a ≤ 0,006 de IoU das 5, com metade do tempo; banda 0,5/1,0/1,5 mm × limpeza 0/0,3/0,5 mm dão IoU 0,941–0,944 (não decidem) **[V]**.
- Determinismo: `cv2.setRNGSeed(0)` antes do `grabCut` (sem isso varia até 0,005 de IoU entre corridas iguais); desfazer por prefixo reproduz exatamente o resultado anterior **[V]**.
- **Falha registada [F]:** a meta p95 < 0,3 mm não é atingida por nenhum solver (0,63–0,68): o núcleo negro da sombra tem croma neutro e fica colado à peça (~27 mm² a mais), e uma orla fina de P0651 fica de fora (~10 mm²). Tem de ser a marca do utilizador a decidir: «fundo» sobre a linha negra, «peca» sobre arte clara cor do papel (no prado sintético: só «incerto» 0,925, com «peca» 0,996).
- **Refutado [F]:** forçar como fundo o que o limiar diz ser fundo piora sempre (IoU 0,76–0,86).
- **Âmbito [NT]:** 2 peças de relva escura do mesmo scan; traços humanos reais e peças claras/céu não medidos.

## 2026-11-07 — falso alarme nas Suspeitas preso a uma assinatura

**Decisão:** marcar uma suspeita como falso alarme (`suspect_dismissed`, desfeito por `suspect_restored`) guarda a `consistency.suspect_signature` do item: sha1 de 12 hex de {célula, classe de 90° `k0`, grau, classe e cordas a 0,1 mm, contorno manual, pose manual, vizinhas N/E/S/W colocadas, gémea + `nn_max_mm` no recorte}. A suspeita fica escondida só enquanto a assinatura bater certo; quando deixa de bater, a marca fica `obsoleto` e a suspeita volta. Não usei o θ exato porque o registo por cantos o corrige; uma marca sem assinatura ficaria a esconder uma suspeita que entretanto mudou.

**Evidência** (`docs/diagnostico/reports/FALSOS_ALARMES.md`, cópia de `projects/alpes`):
- **P0289 (borda):** tirar e voltar a pôr com θ + 90° mantém k = 2 (o lado F volta à borda), por isso a marca continua escondida. Está correto.
- **P0290 (interior):** k passa de 2 para 3 e a marca fica `obsoleto`.
- **Custo:** a junção com os reports custa 0,33 ms; `/api/suspeitas` a frio fica em 5,65 s, contra 5,62 s no HEAD.

## 2026-11-07 — pose manual: sem encaixe automático; métricas com `manual=False`

**Decisão:** a pose manual (`pose_set` / `pose_cleared`, `Piece.pose_manual`) é desenhada exatamente como foi gravada: não há encaixe automático na borda nem nas vizinhas, e a relaxação não a move. As métricas de pose, de juntas e de arte (`artreg.render_board` e as ferramentas de `tools/diagnostico/{arte,render,reports,segmentacao}`) usam `register_piece(manual=False)` / `register_all(manual=False)` e dizem quantas peças com pose manual mediram com a pose automática. As Suspeitas de orientação deixam essas peças de fora por omissão (`n_pose_manual`). Uma pose dada à mão é uma correção do Tiago, não uma medição: se entrasse nas métricas, os números do registo deixavam de medir o registo.

**Evidência** (`docs/diagnostico/render/POSE_MANUAL.md`, cópia de `projects/alpes`):
- **Tempo do «avaliar»:** 13–19 ms no servidor, sem encaixe nem redução de pontos.
- **P0240:** pôr o F na borda (0,26 mm) piora as juntas W/E de −0,615/−0,078 para −0,702/−0,088. É a conclusão do RENDER §9 (a grelha nominal reparte o erro), por isso um encaixe «F na borda» automático também pioraria.

## 2026-11-08 — buracos `alta` entram em «Vai buscar»; média/baixa/sem numa página própria

**Decisão do Tiago:** em uso real os 10 buracos de confiança `alta` que o M11 propôs foram todos confirmados fisicamente (10 `hole_confirmed`, rank 1, 0 `hole_rejected`; Wilson 95 % inferior 0,72; todos céu). As sugestões `alta` (≥ 2 vizinhas por definição) passam a aparecer em «Vai buscar» com chip «por buraco · alta»; as de confiança média, «baixa» (vizinha única) e «sem candidata fiável» ficam na página «Buracos» com as 3 melhores por buraco. Rejeição em um clique em toda a candidata (`hole_rejected` com rank, custo, margem, confiança e versão do fit), para a precisão se medir. Isto reverte a decisão da ronda 5 («nada entra em Vai buscar», tomada pelos números de peça ausente: precisão 49 % a π = 10 %): o uso real deu 10/10 onde o modelo de peça ausente previa pior, porque as soltas no índice **estão** no tabuleiro por montar (π real alto), e não 10 % ao acaso.

**Rede de segurança (critério fixado antes do código, `M11_CRITERIOS.md` §8):** contador acertos / falhas / total das decisões `alta` com IC de Wilson 95 %; se nas últimas 20 decisões `alta` (desde a última reativação) houver ≥ 3 rejeições, aviso e as `alta` saem de «Vai buscar» até o Tiago as reativar (`holes_alta_resumed`). Sensibilidade do 3/20: dispara em 7,5 % das janelas a 95 % de precisão verdadeira, 32 % a 90 %, 79 % a 80 %. O Tiago pode ajustar `ALTA_JANELA` / `ALTA_MAX_FALHAS` em `src/fit.py`.

**Por medir [NT]:** fora do céu não há nenhuma decisão; `T_abs` único fica de reserva até haver GT de relva/vale.

**Rótulo «baixa» (decisão de GUI, não de métrica):** `fit.confidence` só tem `alta` / `media` / `sem`; na GUI, `media` com m = 1 mostra-se como «baixa (1 vizinha)», `media` com m ≥ 2 como «média».

## 2026-11-08 — ronda 7: 6 propostas que não encaixam (primeira GT fora do céu)

**Decisões (com os critérios fixados antes em `docs/diagnostico/gemeos/R7_CRITERIOS.md`, resultados em `R7_RESULTADOS.md`):**

1. **Validação cruzada gémea/par × encaixe entra no produto** (`query._cross_check`): uma proposta cuja célula tem ≥ 1 vizinha montada é testada com `fit.side_costs` na pose prevista; lado impossível ou custo conjunto > `calibration.buraco.t_abs` (2,666) → `encaixe incompatível`, `aceite` → `ambigua`, razão legível, nunca apagada. Evidência: as 2 gémeas falsas dão custo 9,14 e 4,56 (dominado pela tira de imagem das vizinhas); as 42 aceites com vizinha ficam todas `ok` (máximo 2,08); 0/44 perdem `aceite` à data.
2. **Zonas passam para o perfil** (`image_zones` com `rows`), a zona verdadeira é passada e mostrada, e **zona sem p90 calibrado → a imagem não decide → nunca `aceite`**. Montanha, vale e relva ficam sem p90 até haver GT lá. O 50 do céu não muda.
3. **Os p90 por zona medidos NÃO se ativam** (céu 10,6, relva 16,1, calibrados em S_T e validados em S_V com cobertura 85,5 % / 95,1 % e 4,7 % / 3,5 % de negativos a passar): despromoveriam 6 das 34 aceites reproduzidas, acima do critério fixado (≤ 2). Fica para o Tiago decidir se aceita ≈ 15 % de gémeas certas rotuladas `ambigua` no céu em troca de rejeitar casos como P1238 sem vizinha.
4. **Limite de forma não muda** (H2 [F]): 0 não-gémeos da mesma classe abaixo de t95 em 59 100 pares de peças colocadas; na relva o t95 é apertado (p95 dos gémeos verdadeiros 0,89 mm), não largo.
5. **Pares:** só células X com X e twin(X) livres; `pair_locate` com forma e 4 rotações (top-1 30/66 → 64/66 nos pares gémeos colocados). A relação de gémeas de T0003/T0004 não foi refutada pelos reports: o estado «par certo, célula errada» é decisão do Tiago.
6. **Percentil `pctl` sai do caminho de produto** (`find_twin(pctl=False)`): era a causa dos 202–320 s (pool ≤ 300 soltas: 341,5 s → 6,5 s no passo «gémeas» na cópia, propostas idênticas). Não é cache; nada a persistir.
7. **`ambigua` continua a ser cartão em «Vai buscar»** (10 das 43 colocações certas estavam `ambigua`; 1 errada): mudar isto é decisão de produto do Tiago.

**Achado lateral:** os 17 contornos manuais feitos hoje inflam a silhueta ≈ 1,3 mm (p95) / 52–68 mm²; as gémeas dessas âncoras deixam de ser encontradas pela forma (9/9 medido). Decisão do Tiago: refazer, retirar, ou o editor passar a avisar.

## 2026-11-08 — ronda 8: ventoinhas, importação PDF/multi-ficheiro, fila de importação

1. **Causa das ventoinhas em repouso [V]:** um `python.exe -` órfão de um comando `bash` de uma sessão anterior do Claude Code (heredoc mal fechado às 03:23 de 2026-11-08) a 100 % de um núcleo durante ≈ 17 h (9 584 s de CPU); terminado por PID depois de listado e justificado. O servidor em repouso custava 0,18 % sem separador e 0,47–1,07 % com 1–3 separadores (gerador SSE por polling de 0,4 s); passou a entrega por espera (`asyncio.Event` por cliente). Detalhe: `docs/diagnostico/servidor/REPOUSO.md`.
2. **PDF sem dependência nova:** extração do JPEG `DCTDecode` tal como está (`src/sheets.py`); página vetorial ou com outro filtro dá erro claro na folha; rasterizar exigiria PyMuPDF (não instalado): decisão do Tiago.
3. **dpi** pelo MediaBox (arredondado a 300/600 se a < 2 %), senão JFIF, senão o argumento; validação pela **corda mediana dos lados não-F** contra `√(w·h)` da célula: aviso fora de [0,95, 1,05] (as 11 folhas reais ficam em 0,99–1,03); **fundo**: aviso se ΔE76 > 15 ao `background_lab` do perfil. Nenhum aviso recusa.
4. **Idempotência por sha256:** a 2.ª importação do mesmo ficheiro (ou da mesma página de PDF) é ignorada («já importada como S00xx»). Dois testes existentes mudaram por isso (declarado): `test_ingest_synthetic` espera a repetição ignorada; `test_relot_cli_rewrites_overlays` gera 3 folhas com bytes diferentes.
5. **Fila** em `projects/<id>/import_queue.jsonl` só-acrescentar com replay (a disciplina do `log.jsonl`); trabalhador único por `threading.Condition` (sem polling); segmentação fora do `wlock`, commit por folha e **uma** consulta completa por trabalho sob o lock; as escritas da GUI esperam até 90 s em vez de falhar com 409 (medido: 4,8 s e 1,6 s por commit de folha, 79 s na consulta final com 551 soltas).
6. **Risco declarado, por decidir:** não há lock entre processos; `python -m src.confirm` em simultâneo com o servidor não está protegido (pré-existente). Mitigação possível: ficheiro de lock em `state.py`.
7. **GUI:** «por buraco» → «pelo encaixe» (valores guardados intactos); «Ver no tabuleiro» nos cartões pelo encaixe só localiza; «Pré-visualizar encaixe» desenha; gaveta do fundo com separadores «Atividade» | «Fila de importação» (sem botão novo na barra).
8. **Achado lateral corrigido:** `/api/fetch` escrevia `Infinity` (margem com d1 = 0) e o browser não fazia o `JSON.parse`, deixando a página sem lista; inf/NaN passam a `null` nas respostas JSON.

## 2026-11-09 — ronda 9: o editor grava na convenção do índice; os 17 contornos manuais eram mais apertados, não mais largos

**Achado que inverte o R7 §1.3 [V]:** os 17 contornos manuais de 2026-11-07/08 estão **dentro** do automático (desvio assinado da fronteira mediano −0,24…−0,51 mm; o «a mais 52–68 mm²» do `--pares` é o excesso do automático, porque a tabela toma o manual como verdade). Os traços são quase só `pincel/fundo` r = 8 px sobre a linha negra da sombra, 0,1–0,4 mm dentro da aresta automática: a ajuda do editor mandava fazer exatamente isso. O índice (`segment_scan`) inclui a sombra/penumbra (+0,36/+0,54 mm mediano contra a GT do Photoshop, até +1,4 nos lados da sombra), e os limiares de gémea, a erosão do buraco e `celula_silhueta.offset_mm` estão calibrados sobre ela; o editor encontrava a aresta verdadeira (solver sem traços: −0,17…−0,54 mm conforme a zona e o lado; não há δ constante). Daí a gémea deixar de ser encontrada (d1 0,69–0,85 mm). `docs/diagnostico/editor/CONVENCAO.md`.

**Decisões:**
1. **O que o editor grava segue a convenção do índice** (`src/strokes.py`, `normalizar_indice=True` só no servidor; o caminho bruto não muda): halo da própria peça H = (automático ∧ ¬S0) ∪ núcleo negro da sombra (S0 = solver sem traços semeado como fundo; núcleo = L\* < 60, croma < 40 em 8 bits, até 2 mm da aresta, ligado à orla ou à penumbra), traços «fundo» que só marcam a sombra (≥ 60 % da pegada dentro da peça sobre H, ou < 1,5 mm² dentro da peça) **ignorados por inteiro** e devolvidos à GUI (cinzento), região de influência = pegada dos traços restantes + 2,2–2,4 mm, automático **bit a bit** fora dela, dentro `bruto ∪ H` e zonas ganhas dilatadas pelo δ escalar da peça (zona morta 1 px, clamp 0,8 mm). **Sem traços efetivos, gravar devolve o contorno atual exato** (C1). Consequência declarada: um «fundo» a menos de ≈ 0,5 mm da aresta, ou sobre material escuro e neutro a < 2 mm da aresta, é inócuo; um corte em cor de peça continua a cortar; a sombra sai só no desenho (`DISPLAY_SHADOW`).
2. **Refutado: δ constante ou por zona.** O desvio do solver ao índice é por lado (0 nos lados iluminados, 1,0–1,5 mm nos da sombra) e por cor (céu −0,24, relva −0,34, P0651/P0657 −0,49/−0,51): a decomposição «uniforme + local» classificava 17/17 como correção local, todas nos lados da sombra. A primeira versão da normalização (só ∧ ¬S0, corte píxel a píxel) deixava 12/17 com 7–21 mm² em falta a 1,1 mm (o núcleo negro e a lasca de orla iluminada que um pincel de 0,68 mm apanha).
3. **Os 17 registos: 17 «reposição».** Com os traços originais e o pipeline novo, 14 são identidade (todos os traços eram de sombra) e 3 (P1064, P0071, P0045) ficam a ≤ 0,08–0,49 mm do automático. Na 1.ª aplicação P0045 ficou «renormalizado» com 4,2 mm² a mais: era papel fabricado pela dilatação por δ de uma lasca de 0,75 mm² do solver (os traços «é peça» do Tiago estão dentro do automático) e criava uma suspeita nova em P0046; corrigido com `GANHO_MIN_MM2` = 2 mm² (limiar fixado **depois** de ver o caso, declarado) e refeito (`CONVENCAO.md` §3.2). Registo `metodo: "reposicao"` (contorno automático exato; `latest_overrides` ignora-o, a folha é re-segmentada com `force_scans` e motivo `reposicao`, `manual_override` sai e as flags de segmentação voltam), com `derivado_de`, `motivo: "renormalizacao"`, `convencao: "indice"`, só-acrescentar. `tools/diagnostico/editor/renormalizar.py` (dry-run com guarda: a re-segmentação só pode mudar as peças repostas da folha; `--refazer`). **Verificado na cópia [V]:** reprodução R7 34/43 → **43/43**; `fetch.json` idêntico antes/depois (17 + 1 suprimida); invariantes OK (`CONVENCAO.md` §4).
4. **Contorno sugerido pela gémea** (`shape.register_rigid`: cantos + ICP, correspondência de cantos escolhida pelo contorno inteiro porque numa peça quase quadrada as 4 ajustam os cantos a 0,03 mm; `overrides.twin_suggestion`; `GET /contorno.sugestao_gemea`; `base {tipo: gemea}` no `/resolver` e na gravação, reconstruída no servidor). Só de registos `convencao: "indice"`. Medido [V]: 268 pares gémeos colocados com silhueta automática, d_mean mediana 0,131 mm (p95 0,236), p95 das d_p95 0,60 mm, RMS mediano 0,17; 20 pares E-sym 0,129 / 0,30 / 0,16. **Os únicos 6 pares acima de 0,6 mm são P0289–P0294 ↔ P0492–P0498: o corte c32|c33** (ORIENTACOES §D), confirmação independente da exceção à simetria. Em P0651/P0657 a sugestão vinda de uma gémea automática vale o mesmo que o próprio automático (IoU 0,863/0,828 vs 0,869/0,824): o ganho só existe quando a gémea tem contorno manual.
5. **O teste `test_gui_guardadas::test_real_board_cells_without_orthogonal_neighbour_are_not_in_vai_buscar` não tem a ver com os contornos [F, critério da ronda não cumprido]:** compara o `fetch.json` vivo com o log cortado em 2045 eventos; 5 das 7 células foram preenchidas nas linhas 2669–2738. Fica a falhar; corrigir a fixture (fixar o `fetch.json` ao mesmo corte) é decisão do Tiago.
6. **Achado lateral:** nesta máquina `projects/alpes` não tem `pieces/*.npz` nem recortes das folhas S0028–S0037 (375 peças, lotes 4–8; ativos git-ignorados feitos no portátil). Qualquer consulta aqui sem `rebuild_stale` antes corre sem a forma dessas peças; as medições desta ronda refazem os ativos na cópia antes das linhas de base.

## 2026-11-09 — ronda 10 (A2): limiares por validar [NT]

Os limiares abaixo estão no código ou nos testes da ronda 10, mas nenhum foi validado fora do caso de onde veio. Ficam [NT] até haver as medições indicadas.

1. **`GANHO_MIN_MM2` = 2 mm²** (`src/strokes.py`, ronda 9). Uma componente ganha além do automático com menos de 2 mm² é tratada como ruído da aresta: é descartada, não dilatada por δ. **Origem:** foi fixado **depois** de ver P0045 (43,5), onde a normalização transformava uma lasca de 0,75 mm² do solver em 4,2 mm² de papel (`CONVENCAO.md` §3.2). Referências: as mordidas reais têm ≥ 30 mm² (`COMIDO.md`); o canto sintético dos testes ≈ 20 mm². **Falta para validar:** contar falsos negativos, ou seja, recuperações reais de mordida entre 2 e 30 mm² descartadas. Isso pede traços humanos novos em peças com mordida pequena, com GT (máscaras do Photoshop).
2. **«Índice igual ao automático» = regra única bit a bit** (decisão do Tiago, 2026-11-09; substitui a tolerância de 0,5 mm de profundidade que `reaplicar_aresta.py` herdou de `renormalizar.py`, ronda 9: P1064 0,49 mm, P0071 0,01 mm). A ferramenta usa agora `indice_automatico` de `strokes.resolver`, a mesma comparação exata que o servidor faz em `Gui._solve_a2`; deixa de haver duas regras. **Verificado numa cópia limpa do estado `b23d449` [V]:**
   - 14 das 19 peças ficam com índice = automático (só visualização). 5 passam a contorno manual do índice: P0045 (prof. 0,08 mm, +0,06 / −0,07 mm²), P0071 (0,08; +0,01 / −0,01), P0198 (0,42; +0,57 / −0,02), P0620 (0,08; +0,04 / −0,01) e P1064 (0,08; +0,02 / −0,02).
   - P0198 e P0620 já tinham esse mesmo índice (IoU 1,000 com o gravado pelo Tiago), por isso não há evento. Há 4 `piece_resegmented`: 3 `manual` (P0045, P0071, P1064) e P1203 `reposicao` (bit a bit).
   - `fetch.json` idêntico (15/15 entradas, suprimidas iguais, tolerância 1e-6; nenhuma entrada tem peça editada). Reprodução R7 43/43. `check_invariants(disk=True)` = []. Suspeitas iguais (0 impossível, 1 melhor rotação, 14 recorte).
   - **Efeito nas gémeas:** as 5 peças estão colocadas e as 5 gémeas também (P0099, P0825, P0630, P1203, P0063). Não há consulta `find_twin` e nunca são candidatas. A distância livre ao par muda ≤ 0,003 mm nas 4 sem pose de gémea manual. Em P0620↔P1203 passa de 0,068 para 0,140 mm, porque P1203 deixa o contorno vindo da gémea.
   - **Efeito nos buracos vizinhos:** em 6 células, ordem e confiança iguais (todas `sem`); em 3, só o custo muda (≤ 0,028 de J).
   - **Falta (fica [NT]):** o efeito destas diferenças sub-milimétricas em peças com GT; a regra bit a bit põe 3 peças fora das métricas de CV (`manual_override`) por diferenças ≤ 0,08 mm.
3. **0,5 mm (2 × `GEMEA_RUIDO_MM` = 0,25 mm) de ruído na sugestão pela gémea** (`src/strokes.py`, `indice_de_aresta(..., ruido_mm=)`, usado no servidor quando a base é a gémea). As diferenças entre a aresta da gémea registada e a aresta própria sem traços mais finas do que 0,5 mm (abertura morfológica) não passam para o índice. **Origem:** o p95 de d_mean = 0,24 mm em 268 pares gémeos colocados (ronda 9, `CONVENCAO.md` §5). **Não estava no plano:** foi acrescentado nesta ronda porque, sem ele, o teste sintético mostrava lascas do registo a cortar o índice. **Falta para validar:** pares gémeos com aresta pintada dos dois lados (hoje nenhum) e medir o índice derivado contra o índice da própria peça.
4. **3 mm² em `tests/test_server.py::test_contorno_sugestao_gemea`** (laço `_tip_lasso` sobre o ponto mais à direita da peça sintética `placed`, levado à gémea `tw`). Há três asserções:
   - a saliência da sugestão fora do automático é > 3 mm²;
   - o ganho do índice derivado é > 3 mm²;
   - a perda do índice é < 3 mm².

   **Origem real:** escolhido por mim nesta ronda, sem medição que o justifique. O «> 3» é só «acima de `GANHO_MIN_MM2` = 2 com folga». O «< 3» da perda foi fixado **depois** de ver o valor do próprio caso: perda 319 px ≈ 2,3 mm² (lascas do registo nos blanks), ganho 640 px ≈ 4,6 mm². A margem da perda é pequena (2,3 contra 3).

   O outro «> 3,0 mm²» dos testes (`tests/test_strokes.py::test_deep_fundo_cut_survives_normalisation`, corte de um «fundo» profundo) é anterior a esta ronda e não é o do laço.

## 2026-11-09 — ronda 10: o contorno é só a peça (A2: aresta oficial, índice derivado)

**Decisão: A2.** Cada peça editada passa a ter duas silhuetas.
- `aresta_px`: o que o Tiago pinta, só a peça, sem a sombra. É o contorno oficial do desenho e da sugestão pela gémea.
- `contour_px`: a silhueta do índice, derivada da aresta com o halo de sombra da convenção (`strokes.normalizar`/`delta_peca`, ronda 9). Tudo o que lê o índice (npz, shape, twin, fit, border, consistency, registo do render) continua a ler só esta.

**Porquê A2 e não A1.**
- **A1** era recalibrar tudo para a aresta: re-segmentar ≈ 1300 peças e refazer E-sym, t95/tmax, as tolerâncias de corda, a erosão do buraco (0,60 mm), `t_abs`, `celula_silhueta.offset_mm` (0,48), o registo do render, a borda e a consistência. Seriam dias de trabalho, e «Vai buscar» mudaria por definição, sem forma de garantir que fica igual nas peças sem edição. Além disso, o solver sem traços tem um erro por cor e por zona que não está medido fora do céu.
- **A2** custa pouco e não exige recalibração. Fica garantido por construção que as peças sem edição não mudam.

**Provado [V]:** `fetch.json` idêntico na cópia e no projeto real, R7 43/43, invariantes [], Suspeitas iguais (`CONVENCAO.md` §6.4).

**Regra única bit a bit [V].** Uma linha só muda o desenho (`indice: "automatico"`, sem `manual_override` nem evento) quando o índice derivado é o automático **bit a bit**. É a mesma regra no servidor e no `reaplicar_aresta.py`; a tolerância de 0,5 mm saiu (decisão do Tiago, `03e3af5`). Consequência [NT]: P0045, P0071 e P1064 ficam índice manual por 1 píxel (0,08 mm; 0,01–0,07 mm²) e por isso fora das métricas de CV.

**Fase 2: condicional e por zona, por correr.**
- É o recorte de todas as peças pela aresta S0 (A1 parcial), só depois de a provar zona a zona.
- Candidatas medidas contra as máscaras do Photoshop: (a) o solver sem traços puro; (b) S0 com deslocamento direcional nos lados W/S, estimado em leave-one-out.
- Critério por zona: desvio mediano por lado ≤ 0,3 mm, p95 ≤ 0,6 mm, IoU ≥ 0,93. A zona que passa ativa; a que falha fica com a regra atual e o [F] é registado.
- **A tolerância foi fixada vendo só P0651/P0657: não está validada.** O n por zona é de 1 a 2 peças, e o relatório tem de o dizer.
- À espera das máscaras de P1203, P0045, P1245 e P0198 (P0229 opcional) em `docs/diagnostico/editor/gt_photoshop/`.

## 2026-11-11 — grupos propostos entre peças soltas: os 10 quadrados de 2026-11-10 encaixam

**Evidência [V, Tiago, 2026-11-11]:** Tiago testou fisicamente os 10 quadrados 2×2 propostos em 2026-11-10 (ligações melhor-mútuas entre os lados T/B das soltas, custo de lado do molde do buraco, 4 ligações coerentes por quadrado; todos com zona provável céu). **Encaixam os 10**, incluindo os 3 com margem abaixo de 1,05 (#8 1,044, #9 1,030, #10 1,021).

**Atenção: são 10 casos.** Chegam para abrir a fase F4b do redesenho da GUI (grupos propostos pelo programa), não para calibrar uma precisão.
- O limite inferior de Wilson de 10/10 é 0,72, abaixo do 0,80 da regra do «quase certo».
- Os 10 são os 10 melhores da lista e são todos do céu.

**Seguinte:** os quadrados 11–17 (margens 1,021–1,008, também céu; três partilham peças com os 10) estão listados em `docs/diagnostico/grupos_soltos/QUADRADOS.md`, para o Tiago testar onde o método começa a falhar.

## 2026-11-11 — redesenho da GUI: plano aprovado (fases, interruptor, «quase certo»)

**Decisão do Tiago:** aprovado o plano da F0 (`docs/gui/redesenho/F0_INVENTARIO.md`); as respostas às perguntas estão em `docs/gui/redesenho/ESPEC.md` §8.

**Fases.**
- F1 parte-se em F1a (extrair o tabuleiro para `core.js`/`board.js`/`board.css` sem mudar comportamento) e F1b (casca nova e Montar).
- Desfazer a rejeição e o motivo vêm para a F1b.
- F2: a verificação de uma peça posta à mão não bloqueia.
- F4b nova: grupos propostos pelo programa, cada um confirmado fisicamente antes de passar a grupo, com contador de acertos e falhas.
- F5: o Diagnóstico lista as rejeições, cada uma com «anular».
- Cada fase fecha com a suite verde, capturas a 1366 e a 390 px e o OK do Tiago.

**Interruptor.** A GUI nova vive em `/novo/` (atalhos `/?ui=novo` e `python -m src.server --ui novo`); a antiga fica em `/` até à F6.

**Regra do «quase certo».**
- Só por origem × zona com n ≥ 10 decisões físicas e limite inferior de Wilson (95 %) ≥ 0,80; tudo o resto diz «a confirmar por ti».
- **Uma ação desfeita não conta**, nem como acerto nem como falha.
- «Tirar do lugar» é neutro; passa a falha da sugestão se outra peça acabar nesse lugar.
- No «Porquê», «não testado» tem aspeto próprio (traços vazios, «não verificado»), distinto de «falha».

## 2026-11-11 — test_sheets a falhar: é o interpretador, não um commit

**Diagnóstico [V].** `test_sheets::test_pdf_page_without_image_or_with_flate_is_an_error` não falha por nenhum commit: `src/sheets.py` e `tests/test_sheets.py` não mudam desde `32fc4dc`. Falha quando a suite corre com o Python do sistema (`C:\Users\tiago\AppData\Local\Programs\Python\Python312`, 3.12.6), que tem o **PyMuPDF 1.28.0** instalado desde 2026-06-29. Com o PyMuPDF presente, `sheets._rasterise` rasteriza as páginas sem JPEG único em vez de as dar como erro, que é o que o teste espera. O `.venv` do projeto (3.12.6, sem PyMuPDF) dá `8 passed` em `test_sheets.py` e a suite completa dá **460 passed, 1 skipped, 0 failed** em `8fedf87`. A F1a correu a suite com `python` do PATH (o do sistema).

**Correção:** correr a suite com `.venv/Scripts/python.exe -m pytest tests/` (como a 2026-11-09). Não se mudou código nem o teste.

**Por decidir pelo Tiago:** o teste depende de o PyMuPDF não estar instalado. Torná-lo independente do ambiente exige mudar o teste (por exemplo, substituir `_rasterise` por um que devolve `None` dentro do teste, e um teste à parte para o caminho com PyMuPDF). Não foi feito sem OK.

## 2026-11-11 — F1b do redesenho: regras do ecrã «Montar» que não estavam no ESPEC

Decididas pelo implementer ao fazer a F1b; todas mudáveis sem mexer no motor.

- **Traços do «Porquê» (§8.4).** «Passa com folga» = metade do limite (forma: `d1 ≤ t95/2` ou custo do encaixe `≤ t_abs/2`; imagem: `ΔE ≤ p90/2`) ou margem `≥ 2 × margin_min`. Os fatores ½ e 2× não estão calibrados: só mudam 2 ↔ 3 traços. A imagem de uma sugestão pelo encaixe aparece como «não verificado» (o custo do encaixe já mistura forma e imagem, sem teste de imagem à parte). Numa zona sem `dE_p90` (hoje montanha, vale, relva) a imagem também é «não verificado».
- **«quase certo» (§8.3)** exige também **nenhum traço a falhar** e encaixe não incompatível, além de decisão do motor `aceite`/`colocavel`/`alta` e do histórico origem × zona (n ≥ 10, Wilson ≥ 0,80). Um cartão fundido (gémea + buraco) é «quase certo» se uma das duas origens o for. O histórico do buraco conta só as decisões `alta` de rank 1 (as mesmas do contador `alta`); o da gémea conta `twin_confirmed`/`twin_rejected` por `origin`; o dos pares não tem zona.
- **Fila por saco (§8.2).** «Importação recente» = o saco do último `scan_added` ainda tem peças na fila. O saco que o browser está a esgotar vai no pedido (`/api/montar?saco=N`) e fica primeiro enquanto tiver peças; se entrar um scan novo, a fila passa para o saco dele. «Saltar» guarda-se em `sessionStorage` (sobrevive a recarregar a página, não a fechar o browser).
- **Desfazer.** «Encaixa» desfaz-se com `unplaced` + `desfaz: true`; «Não encaixa» com `rejection_undone` (gémea/borda/buraco) ou `pair_unrejected` (par). O motivo é `rejection_noted` (informativo, `ref_t` = o `t` da rejeição). `state.undone_decisions` diz que decisões foram desfeitas; `fit.alta_counter`, `fit.report` e o histórico do Montar ignoram-nas. Três ações novas no log: checkouts anteriores a este deixam de o ler (o custo já previsto no inventário da F0).
- **Limite conhecido [NT]:** desfazer «Encaixa» de um par não desfaz o `pair_confirmed` nem a posição conhecida dada à outra peça do par.
- **Provisórios até às fases seguintes:** «Peças» mostra uma ligação para a interface completa (F3); «⋯ › Atividade do programa» abre a interface antiga noutro separador com a gaveta aberta (F5); «Ver números» do «Porquê» abre as razões técnicas no próprio painel (F5 leva-as para o Diagnóstico); tocar num lugar do tabuleiro só escolhe a peça da fila desse lugar (F2: painel da célula e do lugar vazio).

## 2026-11-12 — grupos propostos entre soltas: os quadrados 11 a 17 também encaixam (17/17)

**Evidência [V, Tiago, 2026-11-11]:** o Tiago testou fisicamente os quadrados 11 a 17 (margens 1,021 a 1,008, todos céu) e **encaixam os 7**. Somados aos 10 de 2026-11-11: **17/17**, todos no céu; limite inferior de Wilson 95 % **0,82** (calculado com `src.fit.wilson`: 17/17 → 0,816–1,000, que fica acima do 0,80 da regra do «quase certo» do ESPEC §8.3 só por 0,016, e só para a origem «quadrado entre soltas» no céu).

- **A margem não discriminou:** encaixou até 1,008, o último quadrado da lista (o corte de 1,05 do teste anterior não separava nada).
- **O método dos quadrados está esgotado nas soltas atuais:** a lista tinha 17 quadrados e os 17 já foram testados. Para saber onde o método falha é preciso mais soltas (mais scans), margens que baixem de 1,0 ou outra forma de grupo (6 e 9 peças, ver abaixo).
- Continuam só do céu: a precisão fora do céu **não está medida** (nenhum quadrado dessas zonas).

**Verificação das junções de um grupo largado junto ao montado (F4c, medição de 2026-11-12, `docs/diagnostico/fit/GRUPOS_JUNCOES.md`).** Medido sobre blocos de peças colocadas (115 blocos de 4, 6 e 9 peças, 63 do céu e 52 da relva; montanha e vale sem dados) tratados como grupos soltos, em 86 840 posições erradas ao longo da fronteira do montado e nas 4 rotações:
- com **1 junção** não se afirma nada (falso «encaixa» 14 % nas posições deslocadas, falso «não encaixa» 10 %, 20 % na relva);
- com **≥ 4 junções** o «encaixa» (todas as junções testadas, máximo do custo ≤ `t_abs`) teve 0 falsos em 4 733 posições, 0 em 115 blocos;
- na **relva** as junções custam o dobro das do céu (`t_abs` foi afinado no céu): falso «não encaixa» 9–20 % com 1 a 4 junções;
- a **posição gémea** encaixa por forma (custo de forma 0,54, igual ao das junções certas 0,53) e só a imagem a separa; nas zonas do meio (montanha, vale) a imagem não a separa em 15 % dos casos.
Nenhum limiar novo no código; a proposta de mínimo de junções está no relatório (§3) e é uma proposta para o Tiago aceitar ou mudar.

## 2026-11-12 — test_sheets: os dois caminhos do PyMuPDF forçados no teste (OK do Tiago)

- **OK do Tiago** para alterar o teste existente `test_pdf_page_without_image_or_with_flate_is_an_error`. Agora força o caminho «PyMuPDF ausente» (`sys.modules['fitz'] = None`, o `import fitz` dá `ImportError`) e mantém as asserções de antes, literalmente.
- Teste novo para o caminho «presente»: um substituto do `fitz` com as 3 chamadas que `sheets._rasterise` faz (`open`, `get_pixmap(dpi=)`, `save`). Grava um PNG verdadeiro, e o teste verifica nome, 300 dpi, aviso, sha256, página k → índice k − 1 e documentos fechados.
- Teste com o PyMuPDF real (página vazia → 2550 × 3300): só corre onde está instalado (`importorskip`); no `.venv` fica `skipped`.
- **[V]** `.venv`: 9 passed, 1 skipped; `python` do PATH (3.12.6 com PyMuPDF 1.28): 10 passed.
- A suite corre sempre com `.venv/Scripts/python.exe -m pytest tests/` (registado no `CLAUDE.md`).

## 2026-11-12 — F4c só no céu, ordem das fases, desfazer «Encaixa» de um par (Tiago)

- **F4c:** só afirma («encaixa» ou «não encaixa») no **céu** e com **≥ 4 junções**. Fora do céu, e com menos de 4 junções, responde «não sei» até haver calibração por zona. Base: `docs/diagnostico/fit/GRUPOS_JUNCOES.md` §2–§3. No céu, com ≥ 4 junções, o critério B deu 0 falsos «encaixa» e 1,6 % de falsos «não encaixa».
- **Ordem das fases do redesenho:** F2, F4, F4b, F3, F5, F6. A F4c fica a seguir à F4b.
- **F2:** desfazer «Encaixa» numa peça de um par desfaz também a confirmação do par e a posição da outra peça.
- Registado no ESPEC (§4.9 e §7). Nada implementado; a F2 não arrancou.
