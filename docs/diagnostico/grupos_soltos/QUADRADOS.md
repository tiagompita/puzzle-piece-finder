# Quadrados 2×2 entre peças soltas: os 17 testados (17/17 encaixam)

_2026-11-11. Só leitura do programa: nada foi escrito em `projects/alpes`._

## Origem e método

A medição é de 2026-11-10, numa sessão anterior, com o script `tools/diagnostico/grupos_soltos/loose.py` (cópia verbatim). O resultado ficou no ficheiro `loose_res.pkl` do scratchpad dessa sessão, que não está no git.
- **Ligações melhor-mútuas** entre lados T/B das soltas, custo de lado `fit.side_costs` (o mesmo do molde do buraco); margem = custo da 2.ª / custo da 1.ª.
- **Quadrado:** 4 ligações coerentes num 2×2. A margem do quadrado é a mais fraca das 4.
- **Contas:** 525 soltas, 531 ligações, 17 quadrados, todos com zona provável céu.

As figuras 11–17 foram feitas em 2026-11-11 por `tools/diagnostico/grupos_soltos/quadrados_11_17.py`. O script lê o mesmo `loose_res.pkl`, por isso a lista e a ordem são as de 2026-11-10, e usa a função de figura de `loose.py` copiada sem mudanças. Correu sobre uma **cópia** do projeto (a árvore de trabalho de hoje).

## Quadrados 1–10: [V, Tiago, 2026-11-11] encaixam os 10

São os 10 melhores, incluindo os 3 abaixo de 1,05: #8 (1,044), #9 (1,030) e #10 (1,021). **São 10 casos**; o Wilson 95 % de 10/10 é 0,72–1,00. Resumo: [quadrados_01_10_resumo.png](quadrados_01_10_resumo.png).

| # | margem | peças |
|---|---|---|
| 1 | 1,145 | Saco 6 · nº 20 (P1128), Saco 9 · nº 15 (P1348), Saco 6 · nº 25 (P1133), Saco 8 · nº 50 (P1308) |
| 2 | 1,143 | Saco 2 · nº 27 (P0170), Saco 5 · nº 30 (P1063), Saco 6 · nº 21 (P1129), Saco 3 · nº 19 (P0927) |
| 3 | 1,129 | Saco 4 · nº 66 (P1024), Saco 7 · nº 27 (P1210), Saco 2 · nº 39 (P0182), Saco 4 · nº 24 (P0982) |
| 4 | 1,125 | Saco 7 · nº 33 (P1216), Saco 4 · nº 12 (P0970), Saco 2 · nº 31 (P0174), Saco 6 · nº 28 (P1136) |
| 5 | 1,082 | Saco 4 · nº 39 (P0997), Saco 2 · nº 17 (P0160), Saco 9 · nº 85 (P1418), Saco 8 · nº 48 (P1306) |
| 6 | 1,078 | Saco 6 · nº 48 (P1156), Saco 8 · nº 20 (P1278), Saco 8 · nº 4 (P1262), Saco 4 · nº 47 (P1005) |
| 7 | 1,064 | Saco 1 · nº 21 (P0114), Saco 9 · nº 44 (P1377), Saco 4 · nº 23 (P0981), Saco 6 · nº 64 (P1172) |
| 8 | 1,044 | Saco 8 · nº 37 (P1295), Saco 9 · nº 27 (P1360), Saco 7 · nº 10 (P1193), Saco 2 · nº 18 (P0161) |
| 9 | 1,030 | Saco 8 · nº 22 (P1280), Saco 6 · nº 59 (P1167), Saco 7 · nº 36 (P1219), Saco 4 · nº 27 (P0985) |
| 10 | 1,021 | Saco 9 · nº 32 (P1365), Saco 7 · nº 72 (P1255), Saco 9 · nº 97 (P1430), Saco 5 · nº 24 (P1057) |

## Quadrados 11–17: [V, Tiago, 2026-11-11] encaixam os 7 (17/17 com os anteriores; Wilson inferior 0,82)

Todos abaixo de 1,05 e todos com zona provável céu. **Testados pelo Tiago: encaixam os 7 [V, Tiago, 2026-11-11]; a margem não discriminou (encaixou até 1,008) e a lista dos quadrados fica esgotada nas soltas atuais.** Resumo: [quadrados_11_17_resumo.png](quadrados_11_17_resumo.png). Em cada figura, as 4 peças como foram digitalizadas e, à direita, a montagem 2×2 aproximada.

| # | margem | peças | figura | nota |
|---|---|---|---|---|
| 11 | 1,021 (< 1,05) | Saco 6 · nº 15 (P1123), Saco 8 · nº 74 (P1332), Saco 8 · nº 26 (P1284), Saco 5 · nº 26 (P1059) | [quadrado_11.png](quadrado_11.png) | 4 peças novas |
| 12 | 1,017 (< 1,05) | Saco 8 · nº 56 (P1314), Saco 9 · nº 41 (P1374), Saco 7 · nº 46 (P1229), **Saco 6 · nº 20 (P1128)** | [quadrado_12.png](quadrado_12.png) | P1128 já está no **grupo 1**, mas aqui usa os outros 2 lados (0 e 3; no #1 usa 1 e 2). Se encaixar, o grupo 1 cresce para 7 peças. Testa-se encostando as 3 novas ao grupo 1 montado |
| 13 | 1,015 (< 1,05) | Saco 7 · nº 6 (P1189), Saco 7 · nº 30 (P1213), Saco 8 · nº 69 (P1327), Saco 6 · nº 51 (P1159) | [quadrado_13.png](quadrado_13.png) | 4 peças novas |
| 14 | 1,012 (< 1,05) | Saco 9 · nº 37 (P1370), Saco 2 · nº 29 (P0172), Saco 6 · nº 44 (P1152), Saco 3 · nº 36 (P0944) | [quadrado_14.png](quadrado_14.png) | 4 peças novas |
| 15 | 1,011 (< 1,05) | Saco 4 · nº 75 (P1033), Saco 8 · nº 51 (P1309), Saco 7 · nº 73 (P1256), Saco 9 · nº 53 (P1386) | [quadrado_15.png](quadrado_15.png) | 4 peças novas |
| 16 | 1,008 (< 1,05) | **Saco 2 · nº 18 (P0161)**, Saco 6 · nº 63 (P1171), Saco 8 · nº 12 (P1270), **Saco 9 · nº 44 (P1377)** | [quadrado_16.png](quadrado_16.png) | P0161 está no **grupo 8** (aqui usa os lados 1 e 2; no #8 usa 3 e 0) e P1377 no **grupo 7** (aqui 2 e 3; no #7 0 e 1). Se encaixar, **liga os grupos 7 e 8** através de P1171 e P1270 |
| 17 | 1,008 (< 1,05) | Saco 7 · nº 10 (P1193), Saco 2 · nº 18 (P0161), Saco 9 · nº 17 (P1350), Saco 8 · nº 12 (P1270) | [quadrado_17.png](quadrado_17.png) | Partilha com o **grupo 8** a ligação P0161–P1193 (é o 8 a crescer 1 fila: + P1270 e P1350). P1270 junta-se a P0161 pelo mesmo lado que no #16, por isso #16 e #17 são coerentes entre si |

Sugestão de teste (já feito): 11, 13, 14 e 15 são independentes. 12, 16 e 17 testam-se encostando peças aos grupos 1, 7 e 8 já montados; se 16 e 17 encaixarem, os grupos 7 e 8 passam a um grupo só, de 11 peças.

**Não verificado:** a montagem 2×2 das figuras é aproximada (peças rodadas e postas à distância nominal da célula), não é uma simulação do encaixe.

## Como registar no programa os 10 grupos montados (40 peças fora dos sacos)

No projeto de hoje (lido numa cópia) as 40 peças estão todas `solta`, nenhuma está num par ativo, e há 100 secções.

**O que já existe e serve [V por leitura do código]:**
- `Project.register_section(scan_id=None, kind="seccao", cells_local={pid: (r, c), …}, candidates=[…], notes="…")` (`src/state.py`) aceita peças `solta`/`emparelhada` e passa-as a `em_seccao`. Assim saem do monte de soltas (`loose_pieces`) e das listas «vai buscar», como as secções do legado. O evento `section_registered` já existe e já é replayado.
- As posições locais saem do `lay` de cada quadrado em `loose_res.pkl`; é preciso normalizá-las para (0, 0) no canto de cima à esquerda.
- O resto já funciona com uma secção destas: «Mesa» (`/api/sections`), «É aqui» (`anchor_section`) e «Desfazer «É aqui»» (`unanchor_section`).

**O que falta:**
1. **Uma porta de escrita.** Não há CLI nem endpoint que chame `register_section` com peças já indexadas: hoje só `src/ingest.py --montado/--blocos` (a partir de uma folha em vista explodida) e `src/legacy.py` o fazem. É preciso um `python -m src.confirm --grupo P1128:0,0 P1348:0,1 …` (ou ação `/api/confirm` `acao: "group"`), com o mesmo ciclo de escrita (lock, invariantes, reconsulta). Um script avulso também chega, mas só com o servidor parado e com uma cópia de segurança antes, como as outras escritas reais.
2. **Lugares candidatos.** Sem uma folha do grupo montado, `candidates` fica vazio e a Mesa mostra «sem zonas candidatas». `locate.locate_group(items, …)` já aceita os recortes das peças com a sua célula local (`mean_lab`, `rc`, `rgba`, `theta_deg`); falta o código que monta os `items` a partir de peças soltas (hoje montados pelo `legacy.py` a partir da folha). Em alternativa, o Tiago digitaliza cada grupo montado como uma folha `--blocos`, como no legado, mas isso cria peças novas (re-scans) e liga-as às antigas por `same_as`: é mais trabalho e menos limpo.
3. **Rotação por peça.** `Section.cells_local` só guarda a célula local, não a rotação de cada peça no grupo. O layout de 2026-11-10 tem essa rotação (`rot`). Hoje, ao fixar um grupo, a pose de cada peça vem do registo por cantos do render (`render.initial_theta`), o que funciona com o legado, mas não foi testado com secções sem folha [NT].
4. **Miniatura do grupo.** `Gui._section_png` desenha os recortes «nas posições do scan» (vista explodida). Com peças de 4 folhas diferentes, a miniatura sai sem sentido: precisa de usar o layout local [NT].
5. **Contador da F4b.** Para os acertos e falhas dos grupos propostos (ESPEC §8.6) é preciso um evento informativo de confirmação ou rejeição do grupo proposto (ex.: `group_confirmed`/`group_rejected` com a margem e a origem «quadrado»), ou pelo menos `notes` com «proposto pelo programa, quadrado #n, margem m, confirmado fisicamente 2026-11-11». A forma certa decide-se na F4b; registar os 10 agora com `notes` não impede isso.

**Proposta:** registar os 10 grupos já na F4b, com a porta de escrita do ponto 1 e o evento do ponto 5, para os 10 contarem logo como os primeiros 10 acertos do contador. Até lá, as 40 peças continuam `solta` no índice. **Efeito prático [NT]:** podem aparecer em «Vai buscar» como propostas de gémea ou de buraco; nesse caso o Tiago vai buscá-las ao grupo montado e não ao saco.
