# E-fit — passo 1: GT de adjacências sem circularidade, e critérios fixados antes de correr

_2026-11-05. Medição, não produto: não há `src/fit.py`; nada em `src/`, na GUI, em `src/state.py` nem em `projects/alpes` foi alterado (só leitura). Código: `tools/diagnostico/fit/common.py`, `tools/diagnostico/fit/gt.py`; saída regenerável (não commitada): `docs/diagnostico/fit/gt_pairs.json`. Etiquetas: **[V]** verificado, **[NT]** não testado, **[F]** falha._

## 1. O problema: o GT não pode vir do encaixe

As posições `legado_scan` (498 peças no estado atual) vêm de `src/legacy.py`: os componentes juntam-se por arestas **validadas por `side_complement`** (T↔B, RMS ≤ 1,6 mm, |ΔL| ≤ 2 mm; `build_components`, Kruskal), a âncora no tabuleiro decide-se por imagem + gémeas + células partilhadas + pistas. Usá-las como GT mediria o encaixe contra uma verdade que o próprio encaixe escolheu **[V, `src/legacy.py`, `docs/diagnostico/legado/LEGADO.md`]**. Por isso a proveniência determina-se **por par**, não por célula.

## 2. Como se determinou a proveniência (e o que o log/scans guardam)

| Proveniência | O que é | Onde está guardada | Entra no GT |
|---|---|---|---|
| **a** layout da vista explodida | adjacência = vizinha por **posição na página** (centros dos corpos), feita à mão pelo Tiago | os contornos de cada página (`pieces/S00xx.npz`, `shape.c`) — não há registo de quais arestas vieram do layout; **reconstruiu-se de novo** a partir das posições, sem olhar para o encaixe | **sim** |
| **b** GT manual | 88 peças (canto BE, canto BD, E-sym): célula por conferência à mão | eventos `placed` com `origin = gt` (88) | **sim** |
| **c** decidida pelo programa | `legado_scan` (e `legado_scan+pista`): imagem, gémeas, encaixe, margem | secções com `anchor.fonte` ∈ {`legado_scan`, `legado_scan+pista`} (498 peças) | **não** (só etiqueta de zona) |
| **d** confirmada fisicamente pelo Tiago | propostas que ele colocou (`placed`, `origin = gemeo`, 15) e secções ancoradas com `fonte = manual` (as âncoras manuais mais recentes) | log | **sim** |

Posições por proveniência (peças, estado atual) **[V, `gt.py`]**: b 88, d 19, c 498. As 6 células `ocupada_legado/foto` e as pistas do Tiago sem peça não têm peça e não entram.

**O que separa (a) de (c).** Os componentes guardados em `sections[*].cells_local` já passaram pelo filtro de encaixe, por isso **não se usam**. O layout (a) reconstrói-se do zero: por página `montado`, rotação da página pela média 4-fold dos ângulos do corpo (`legacy.page_rotation`), cada lado etiquetado N/E/S/W pela normal exterior (`legacy.label_sides`, só usa cantos), e a vizinha de uma peça em E ou S é a **mais próxima** ao longo do eixo (0,9–2,0 células; o espaçamento típico da vista explodida é ≈ 1,6 células), transversal ≤ 0,35 célula, **vizinhança mútua**. Nenhum RMS de perfil entra. Não consegui determinar: (i) quais das arestas aceites em `legacy.py` foram "layout" e quais "encaixe" (não está registado); (ii) se duas peças próximas na página pertencem ao mesmo bloco físico (páginas com vários sub-blocos lado a lado, p02/p03/p06): o layout puro não distingue vizinha de "vizinha de outro sub-bloco" **[NT]**. Por isso (a) leva uma medida de ruído (secção 4).

**Rotação do GT (b).** O lado que olha para o vizinho vem do `theta_deg` do log; nas peças GT esse `theta_deg` foi decidido pelos **lados F e pelo tipo T↔B** (`CLAUDE.md`: rotação do tabuleiro das 4 GT: F 20/20 + T↔B 19/19 em A1/B2, T↔B 30/30 BE, 43/45 BD), nunca pelo RMS do perfil. Há aqui uma dependência fraca do **tipo** do lado (não da forma): se um tipo está mal lido, o GT (b) herda-o. Mede-se em 4 (de 228) consultas (b) com tipo incompatível. **[V]**

Estratégia de exclusão: `legado_scan`, `legado_scan+pista`, `foto` e as pistas do Tiago **nunca** decidem um par.

## 3. O GT (resultado)

Número de **lados** = consultas dirigidas (A olha para B; um par físico dá 2). Identidade física: `same_as` do log + (mesma classe, free ≤ t95 = 0,507 mm, ΔE médio ≤ 10, o critério de `src/legacy.py`) → 815 peças físicas distintas em 953 peças ativas (6 ligações extra além do `same_as`); a página `montado_p13` (duplicada da p04, **[V]** LEGADO.md) fica de fora.

| | lados | pares |
|---|---|---|
| total reconstruído | 1532 | 766 |
| com tipo **incompatível** (F, T–T ou B–B) | 90 (a 86, b 4) | 45 (a 43, b 2) |
| **GT primário: T↔B** | **1442** | **721** |

GT primário por proveniência (um par pode ter várias; conta-se na **principal**, b > d > a): **a 1198, b 228, d 16** (166 dos de b também aparecem em a; **244 lados têm evidência b ou d**, 1198 só de layout). 576 peças físicas distintas. Gate (≥ 150 lados independentes): **cumprido** [V].

Por classe do lado consultado: T 721, B 721 (F nunca é consulta no GT primário; os 38 lados com F são ruído do layout ou tipo mal lido).

Por zona (faixas de linhas **fixas**: céu 1–14, montanha/floresta 15–27, vale/aldeia 28–40, relva 41–47; a célula vem do mapa, e só serve para fatiar): relva 735, céu 622, vale/aldeia 45, montanha/floresta 38, sem posição 2. **O GT não cobre o meio do puzzle** (83 lados): as páginas do legado são as faixas de cima e de baixo e as bordas **[V]**. Conclusões sobre vale/montanha são [NT].

Por proveniência × zona: a — céu 569, relva 545, vale/aldeia 45, montanha 37, sem posição 2; b — relva 190, céu 38; d — céu 15, montanha 1.

## 4. Ruído do layout (a) **[V parcial]**

- 728 pares de vizinhança mútua de layout; **43 pares de layout (86 lados) têm tipo fisicamente impossível** (F encara vizinha, T–T, B–B): 5,9 % do layout é ruído **detetável**; concentram-se em p12 (54 lados), p02 (22), p01 (6) e p15 (4) — as páginas dobradas/com sub-blocos. Mais 2 pares do GT (b) (4 lados) têm tipo incompatível. Excluídos do GT primário e mantidos num estrato à parte (podem ser ruído de layout **ou** tipo mal lido, a forma M4; o layout puro não os separa).
- Onde as duas peças têm posição independente (b/d), todas as vizinhas de layout são mesmo células vizinhas: **84/84** **[V]** (precisão do layout nesse subconjunto; a cobertura é só BE/BD, não as páginas problemáticas).
- Ruído **não detetável** (par T–B de peças que não são vizinhas): desconhecido **[NT]**. Pessimismo: conta como falha do encaixe.

## 5. Critérios fixados ANTES de correr (passos 2–3)

Escritos aqui, antes de qualquer execução do E4/E5. Nada abaixo se ajusta depois de ver os resultados.

**Candidatos.** Os lados de **todas** as peças do pool: peças ativas com forma `ok` (≈ 952), um representante por peça física (815), **excluindo** a peça consultada e as suas duplicadas físicas; 4 lados por peça (≈ 3260 candidatos). Sem escolher peças "boas". Compatibilidade de tipo: F nunca com nada, T só com B (`shape.side_complement` devolve ∞ nos outros): F **rejeitado** como parceiro de lado não-F.

**Aceites (o que conta como acerto).** O lado que olha para a consulta, da peça física B (qualquer das suas digitalizações, com o índice de lado mapeado por `shape.homologous_k`) **ou** o lado homólogo da gémea de B (gémea por silhueta: mesma classe, `free_dist ≤ t95`, ΔE médio > 10, vizinhança mútua; o lado homólogo por `homologous_k`; a rotação de 180° e a simetria vêm do perfil — `profile.twin_rotation_deg()` / a regra do perfil — **nada de `48 − l, 65 − c` no código**). Reporta-se também o estrito (só B).

**E4 (geometria).** Ordena os candidatos que passam o filtro de cordas (|ΔL| ≤ 1,0 mm, 2,0 mm se o lado da consulta ou o candidato é F ou adjacente a F; `profile.calibration['chord']`) por `side_complement` RMS (mm), a partir do menor. Rank = a melhor posição entre os aceites; aceites fora do filtro de cordas contam como **falha** (e reportam-se à parte). Alvos: **top-1 ≥ 60 %, top-3 ≥ 90 %**; falha: top-3 < 60 %. Variante secundária (declarada, não escolhida depois): custo `rms + 0,5 |ΔL|` como em `legacy.side_compat`.

**E5 (geometria + imagem).** Score = `rms / 1,1 mm + ΔE_img / 10`. As escalas são constantes escolhidas **antes**: 1,1 mm = RMS mediano das adjacências verdadeiras do canto BE (LEGADO.md, 1,09), 10 = o ΔE de "mesma peça" de `legacy.py`; pesos iguais; **não se otimizam**. `ΔE_img`: mediana de 12 pontos ao longo do arco do lado (de 0,08 a 0,92) da distância Lab entre a tira interior da peça A (pixels do recorte limpo entre 1,0 e 2,5 mm de profundidade a partir da silhueta, janela de ±1/24 do arco) e a tira do candidato na posição espelhada (`1 − t`), só nos candidatos que passam o filtro de cordas. Alvo: **top-1 ≥ 85 %**; falha: top-1 < 60 %. Baseline de imagem sozinha: ordenar só por `ΔE_img`.

**Baselines obrigatórias.** (1) acaso = |aceites| / N sobre todos os lados do pool e sobre os T/B compatíveis; (2) **filtro de cordas sozinho** (+ compatibilidade de tipo): ordem aleatória dentro dos que passam; esperança de top-1 / top-3 por hipergeométrica, para mostrar o ganho real da forma (E4) e da imagem (E5).

**Estatística.** n e intervalo de Wilson a 95 % por métrica; fatias por classe (T, B), zona, proveniência (a / b+d) e tipo; mostram-se as **piores fatias** (n ≥ 20) e não só a média. Sem otimização de limiares; se algo se ajustar, diz-se o quê e mede-se fora da amostra (metade/metade).

**Classificação das falhas (fixa).** Por ordem: (1) *forma do lado mal lida (M3/M4)*: o lado verdadeiro não passa o filtro de cordas, ou o tipo é incompatível, ou o seu RMS ≥ 2,0 mm; (2) *gémeo/ambiguidade genuína*: o vencedor tem RMS dentro de 0,15 mm do verdadeiro, ou é uma peça física distinta cujo lado é geometricamente equivalente (RMS ao lado verdadeiro ≤ 0,5 mm); (3) *imagem enganadora* (só E5): o rank no E4 era ≤ 3 e passa a pior no E5; (4) *pose/escala*: os lados são em mm e independentes da pose, por isso só pode entrar via a tira de imagem; fica "inconcluso" quando nenhuma das anteriores explica. Os exemplos visuais (6 acertos, 6 falhas escolhidas pelo **pior rank**) saem no passo 3.

**Honestidade sobre o que o GT não prova.** O layout é a verdade física que o Tiago construiu à mão **[assumida, 84/84 onde verificável]**; o ruído não detetável pessimiza; o GT não cobre o meio do puzzle; os lados F e os cantos ficam fora (só adjacências internas T↔B).
