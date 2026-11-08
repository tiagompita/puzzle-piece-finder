# 2026-11-08 (7) — 6 propostas que não encaixam (primeira GT fora do céu), consulta 40× mais lenta, continuidade do M11

## Porquê

Depois de importar os lotes 4–8 o Tiago colocou tudo o que «Vai buscar» propôs menos 6 peças: 2 gémeas (P1014 → (41,62), relva; P1238 → (35,2), vale) e 2 pares (T0003 em (4,63), T0004 em (4,62)) que fisicamente não encaixam, registadas às 18:44 (`twin_rejected`/`pair_rejected`) e com 6 reports (R0029–R0034). Toda a GT de gémeas (44) e de buracos (38, menos 1) é céu: estas são as primeiras falhas fora do céu. Na mesma sessão do servidor o passo «gémeas» da consulta completa levou 202–320 s nos lotes 4–5 e 6–9 s nos lotes 6–7.

## Decisões

- Critérios fixados e commitados antes de medir (`docs/diagnostico/gemeos/R7_CRITERIOS.md`, `8af95b2`): conjunto etiquetado, hipóteses H1–H6 com métrica e critério, partição por folha e zona, critérios de efeito das correções (≤ 2 das 43 aceites mudam de decisão), invariante da velocidade.
- H5 (encaixe contra as vizinhas na pose prevista) explica as 2 gémeas falsas (custo 9,14 e 4,56 > T_abs 2,67; máximo das 42 aceites 2,08) → **3.1 validação cruzada gémea/par × encaixe**: `ambigua` + `encaixe incompatível` + razão, nunca apagada.
- H3: o rótulo «(ceu)» era o *fallback* e o limiar 50 deixa passar 61–97 % das células aleatórias → zonas no perfil (`image_zones` com `rows`), zona verdadeira passada e mostrada, «zona sem p90 calibrado → a imagem não decide → não `aceite`». Os p90 por zona medidos (céu 10,6, relva 16,1) **não são ativados**: despromoveriam 6 das 34 aceites reproduzidas (critério ≤ 2) — decisão para o Tiago.
- H2 [F]: 0 não-gémeos da mesma classe abaixo de t95 em 59 100 pares; o limiar de forma não muda (3.3 não se faz).
- H6: células com X ou twin(X) ocupadas excluídas da localização conjunta dos pares; `pair_locate` com forma e 4 rotações. A relação de gémeas dos pares rejeitados não foi refutada: o estado «par certo, célula errada» é decisão do Tiago.
- Velocidade: o percentil informativo (`PCTL_MAX_N`) sai do caminho de produto (`find_twin(pctl=False)`); 341,5 → 6,5 s no passo «gémeas» com pool ≤ 300, propostas idênticas (diff = 0). Não era cache.
- `ambigua` continua a ser cartão em «Vai buscar» (decisão de produto do Tiago, não desta ronda).

## Prompt verbatim

```
Contexto
Projeto puzzle_piece_finder. Faz git pull. Lê docs/HANDOFF.md, docs/estado-e-plano.md (§0, §7), docs/diagnostico/gemeos/RESULTADOS.md, EREAL2.md, docs/diagnostico/fit/M11_CRITERIOS.md, docs/diagnostico/fit/RESULTADOS.md §13 e docs/decisoes.md. Segue cv-visual-verification e piece-fit-matching.

Regras
- Nada conta como progresso sem verdade de terreno. [V]/[NT]/[F] com números e intervalos de Wilson. Critérios fixados e commitados ANTES de correr; nada se afina depois de ver os números de validação, e nunca só sobre os 6 casos novos.
- Commits em português, SEM co-author nem linha Claude-Session. Push sem --force. Não alteres testes existentes sem o dizeres. Não feches reports. Vê git status de projects/alpes antes de escrever lá; o servidor da GUI do Tiago está parado enquanto trabalhas.
- Regista em docs/revisao.md e atualiza o HANDOFF no fim.

O problema (verdade de terreno física do Tiago)
Os lotes 4–8 foram importados. O Tiago colocou todas as peças que «Vai buscar» propôs, menos 6. Essas 6 tinham posições que fisicamente NÃO encaixam, e o Tiago já as registou na GUI às 18:44 de 2026-11-08: twin_rejected P1014 em (41,62) e P1238 em (35,2); pair_rejected T0003 e T0004 (duas peças cada: no total 6). NÃO registes rejeições. Evidência indireta no fetch.md anterior (a confirmar por ti): propostas por gémea com d1 colado ao limite t95 = 0,507 mm (P1238 0,477, P1109 0,503, P0112 0,489), «imagem consistente» com ΔE de 32,1 e 41,7 porque o limite p90 do «ceu» é 50 (e (33,3) aparece rotulado «ceu», o que parece zona errada), vários com theta_unknown. Até ao lote 8 toda a GT de gémeas (44 twin_confirmed) e de buracos (38 hole_confirmed, todos alta rank 1) é CÉU (linhas 1–14; mais 1 nas 15–40). Estas falhas são a primeira evidência fora do céu.

Parte 1 — Verdade de terreno
1.1 Lê o log: identifica as 6 peças (as 2 gémeas e as peças dos pares T0003/T0004) e, para cada uma, a proposta que foi rejeitada: célula(s), origem, d1, margem, ΔE, theta, zona atribuída, e a peça colocada de que parte a proposta (a «âncora» da gémea).
1.2 Monta o conjunto etiquetado: positivos = todas as propostas por gémea e por par que o Tiago aceitou (twin_confirmed, pair_registered, e peças colocadas a partir de «Vai buscar») desde a ingestão dos lotes 4–8; negativos = os 4 rejected acima. Diz a composição por zona e por origem. Marca claramente o que é céu e o que não é.

Parte 2 — Causa por hipótese, cada uma medida (não assumas nenhuma)
H1. A peça âncora está ela própria mal colocada ou mal orientada: corre src.consistency sobre as âncoras e as vizinhas.
H2. O limite de aceitação da forma (d1 ≤ 0,507 mm, margem ≥ 1,5) é demasiado largo fora do céu: mede d1/margem das gémeas verdadeiras contra as 2 gémeas falsas e contra não-gémeos da mesma classe.
H3. A verificação de imagem é vazia fora do céu: o limite p90 do «ceu» (50) só foi calibrado em céu. Verifica o mapa de zonas (porque é que (33,3) é «ceu»?) e calibra a distribuição de ΔE por zona com as peças colocadas como GT (positivos) e células aleatórias da mesma zona (negativos). Reporta o poder discriminativo real por zona (AUC ou separação), não só o limite.
H4. theta_unknown: quando a pose da consulta é desconhecida, a imagem usa a melhor das 4 rotações, o que infla a concordância. Mede o efeito.
H5. A gémea tem a forma certa mas a célula tem vizinhas incompatíveis: corre src.fit sobre as 2 gémeas falsas e as peças dos pares falsos (tipos de lado e custo contra as vizinhas colocadas).
H6. Pares: as 2 propostas T0003 e T0004 eram falsas. Mede como o score do par (margem, localização conjunta) se comporta nelas contra os pares verdadeiros (pair_registered); olha a lista de células candidatas conjuntas.
Para cada hipótese: [V]/[NT]/[F], com figura vista.

Parte 3 — Correção, só se a Parte 2 a justificar, por ordem
3.1 Validação cruzada gémea × encaixe: uma proposta por gémea (e por par) cuja célula tenha ≥ 1 vizinha colocada passa pelo src.fit; tipos de lado impossíveis (T↔T, B↔B) ou custo conjunto fora do intervalo rebaixam a proposta para «ambigua» (nunca a apagam em silêncio; a razão fica registada). Efeito medido: nenhuma proposta aceite pelo Tiago perde o estado «aceite»; as 4 falsas deixam de ser «aceite».
3.2 Calibração da imagem por zona (H3), se se confirmar.
3.3 Limite de forma (H2), só se 3.1 e 3.2 não chegarem, calibrado por validação cruzada deixando folhas de fora, critérios fixados antes.
Partição afinação/validação por folha e zona. Nunca afines só com as 4 falsas. Se só houver céu para validar o efeito, diz-me que a validação fora do céu é [NT].

Parte 4 — Velocidade, SEM perder precisão
No log de atividade de 2026-11-08 (projects/alpes/logs/servidor-20261108.log), na MESMA sessão do servidor (arranque 14:38, sem reinício; o Tiago diz que nada mudou entre o lote 5 e o 6) o passo «gémeas» da consulta completa levou 202 s (lote 4, 184 soltas), 215 s, 293 s e 320 s (lote 5, 260–272 soltas) e depois 6,0 s, 8,6 s e 6,4 s (lotes 6 e 7, 336–412 soltas). Explica esta diferença de 40× com medição antes de otimizar: cache que aqueceu (qual, onde?), concorrência de CPU de outros processos Python em segundo plano (lista-os, mas a investigação do CPU em repouso do portátil é de outra sessão), mudança de caminho de código (consulta completa vs incremental), ou outra causa. Se for cache, torna-a persistente em disco para sobreviver a reinícios. Há também um GET /api/suspeitas de 11,9 s no arranque e POSTs de confirmação de 3,5 s. Invariante: as propostas (peça, célula, decisão, d1, margem, ΔE) em projects/alpes idênticas antes e depois numa cópia (diff JSON; diferença ≤ 1e-9 ou explicada). Sem alterar limiares.

Parte 5 — Continuidade do plano
5.1 python -m src.fit --project projects/alpes --relatorio com a GT nova: n total, por zona e nº de vizinhas, por confiança. Diz quando se chega a n ≥ 60 (≥ 40 com ≥ 2 vizinhas) fora do céu.
5.2 python -m src.overrides --project projects/alpes --pares: n de contornos e de poses; desvio por zona. Só medição, sem aprender nada.
5.3 Atualiza docs/estado-e-plano.md (estado do M11 e o ponto em que a GT fora do céu fica por obter) e propõe, sem implementar, o passo seguinte do plano, com justificação por evidência.
5.4 Opcional, baixa prioridade: rascunha docs/README_proposta.md (objetivo, fluxo de uso, arquitetura, como correr, estado) para o Tiago aprovar. Não substituas o README atual.

Formato da resposta final
- [V]/[NT]/[F] com números; causa de cada uma das 6; o que mudou; o que ficou por testar.
- Tempos antes/depois e prova de que as propostas são idênticas.
- O que o Tiago tem de ver na GUI (termos de pesquisa) e só as decisões que são dele.
```

## Resultado

Commits: `8af95b2` (critérios), `32b918c` (GT à data, H1–H5, tempo), `2f68664` (H6(b)), `65389d5` (plano + README_proposta), `bab495a` (efeito), `b0bf748` (decisões/revisão), `be82a34` (código), docs finais (HANDOFF, CLAUDE.md, ARCHITECTURE.md, relatório). Relatório completo: `docs/diagnostico/gemeos/R7_RESULTADOS.md`.

- **Parte 1 [V]:** os 6 casos reconstruídos à data; 44 colocações por gémea (33 `aceite`, 10 `ambigua`), 38 buracos; 34/34 decisões reproduzidas nas peças com silhueta inalterada (as 9 outras têm contorno manual de hoje).
- **Parte 2:** H1 [F], H2 [F], H3 [V] (teste quase vazio; rótulo falso), H4 [F] (não material), H5 [V] (explica as 2 gémeas), H6 [V] (ocupação; 1 rotação 30/66 → 4 rotações 64/66).
- **Parte 3:** 3.1 feita (0/44 aceites perdem `aceite`; 2/2 rejeitadas `incompatível`); 3.2 parcial (zonas no perfil; p90 novos não ativados: despromoveriam 6/34); 3.3 não (H2 [F]).
- **Parte 4 [V na cópia]:** percentil `pctl` com pool ≤ 300 → 341,5 s; sem ele 6,5 s; propostas idênticas; não é cache. `GET /api/suspeitas` 10,6 s durante a composição do tabuleiro (2,3 s depois); POST 8–13 s com a thread das tiras a frio.
- **Parte 5:** `--relatorio` 38/38 (37 céu, 1 montanha; §15.6 por atingir); `--pares` 17 contornos, 5 poses; plano atualizado com o passo seguinte (GT fora do céu antes de limiares); `docs/README_proposta.md` rascunhado.
- **Por fazer / decisões do Tiago:** ver `docs/HANDOFF.md`.

