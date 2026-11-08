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
