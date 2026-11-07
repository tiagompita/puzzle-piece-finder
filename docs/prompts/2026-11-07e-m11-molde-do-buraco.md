# 2026-11-07 (5) — M11 «molde do buraco» como ranking (`src/fit.py`), critérios antes de correr, validação por folha e zona, GUI «Candidatas para este buraco»

## Porquê

O E-fit (passos 1–6) tinha medido que o encaixe solta–solta (M6) falha e que o molde do buraco com 2–4 vizinhas é viável só como ranking (E5 estrito top-1 88–93 % em lotes de 32–100), com três bloqueios: a peça certa falha o filtro **duro** de cordas, a melhor candidata propõe-se sempre (sem calibração absoluta) e a erosão 0,48 mm veio de outro GT. O Tiago pede a 1.ª metade do M11 como produto honesto: «candidatas para este buraco», não proposta autónoma, com critérios e partição afinação/validação fixados e commitados antes de qualquer corrida, e a GUI só se a validação não falhar.

## Decisões

- Critérios commitados antes do código (`docs/diagnostico/fit/M11_CRITERIOS.md`, commit `f6cc2b7`): partição por folha (S_T = páginas `montado` ímpares de céu e relva: 144 buracos de 8 folhas; S_V = 214 buracos de 12 folhas, com todos os b/d, montanha e vale reservados; 120 descartados por partilharem folha); só 3 parâmetros afinados (erosão, corte do filtro mole, quantil da rejeição); confiança com regra fixa; vizinha única nunca `alta`; [F] se o limite superior do IC em S_V ficar abaixo de 60 % → sem GUI.
- Porta de sanidade: `src.fit` reproduz o passo 5 (recalculado hoje sobre o projeto atual, 478 buracos) com Δ 0,00 pt nas 8 comparações; `fit_eval.py` passa a importar de `src.fit` e `buraco.py` dá o JSON bit a bit igual.
- Afinação em S_T (N = 32): erosão **0,60 mm** (92,0 %; 0,48 dava 88,7), corte do filtro mole **2×** (98,3 %, 0 certas a ∞), rejeição q = 0,90 (T_abs 2,67; nenhum quantil cumpre a utilidade). Gravado em `calibration.buraco` do `puzzle.json`.
- Eventos `hole_confirmed`/`hole_rejected` já existiam; ganham `rank, custo, margem, confianca, m, fit_version`; `confirm(hole=…/hole_reject=…)` é a única via de escrita (CLI `--buraco`, servidor).
- A afetação conjunta desempata a custo igual (a 1e-6) para o buraco com mais vizinhas.
- O ranking **não entra em `fetch.json`/«Vai buscar»**; vive na gaveta da célula e na secção «Buracos» (botão no fim de «Vai buscar», sem 7.ª aba).
- Delegação: sem cabeçalho «Agente:», o trabalho ficou na sessão (módulo crítico).

## Prompt verbatim

```
Contexto
Projeto puzzle_piece_finder. Faz git pull. Lê docs/estado-e-plano.md (§0, §6, §7: M11, M6), docs/plano-m10-m12.md, docs/diagnostico/fit/GT.md e RESULTADOS.md (§10, §13, §15.6), docs/gui-design.md, docs/HANDOFF.md. Segue cv-visual-verification e piece-fit-matching.

Regras
- Nada conta como progresso sem verdade de terreno. [V]/[NT]/[F] com números e intervalos de Wilson. Critérios fixados e commitados ANTES de correr, como nos passos 4, 5 e 6 do E-fit. Nada se afina depois de ver os números de validação.
- Commits em português, SEM co-author nem linha Claude-Session. Push sem --force.
- Não alteres testes existentes sem o dizeres à parte, com a razão.
- Não feches reports. Antes de escrever em projects/alpes, vê git status; se houver alterações do Tiago por commitar, para e diz-lhe.
- Não mexas na segmentação nem na pose. Regista em docs/revisao.md e atualiza o HANDOFF.

Objetivo
Implementar o M11 «molde do buraco» (src/fit.py, 1.ª metade) como RANKING: «candidatas para este buraco», não proposta autónoma. O E-fit mediu: com 2–4 vizinhas e a peça no lote, E5 top-1 93 % (N=32, com erosão 0,48 mm; IC acima de 85 %); peça ausente [F] (precisão 4–5 % a π=1 %); M6 solta–solta [F] (não fazer). O piloto real (n=15, só céu) é [NT]. O produto tem de dizer honestamente quando não sabe.

Parte 1 — Critérios antes de código (commit próprio)
Escreve docs/diagnostico/fit/M11_CRITERIOS.md ANTES de qualquer código ou corrida, com:
- Partição afinação / validação: por folha (scan) e por zona, sem partilhar folha entre os dois lados. Valida em peças de folhas e zonas que não entraram na afinação. Diz exatamente o que cada conjunto contém.
- Métricas e alvos: E5 estrito top-1 e top-3 (Wilson); taxa de «propostas falsas por buraco» quando a peça está ausente do lote (a lacuna do §13); direção inversa (cada solta contra os N buracos reais do tabuleiro: falsas por peça); precisão a π=1 % e π=10 %.
- O que será afinado (só estes parâmetros): erosão por validação cruzada (não 0,48 fixo; o §12 diz que veio de outro GT), corte do filtro mole de cordas, limiar de rejeição absoluta.
- Condições de paragem: se a validação cair abaixo do limiar de falha (60 %), reporta [F] e não ligues à GUI como «sugestão».

Parte 2 — src/fit.py
- API rank_hole(célula, pool, contexto) → shortlist (top-3) com custo conjunto, margem e confiança em 3 níveis (alta / média / «sem candidata fiável»). Invariante: o mapa de lados tem orientação única (σ = +1 em 603/603), afirmado em código.
- Componentes: (1) filtro de cordas MOLE (penalização graduada) em vez de duro; (2) E5 conjunto sobre as vizinhas com erosão calibrada; (3) rejeição absoluta: o custo conjunto d1 tem de ser compatível com o de um verdadeiro (calibrado nos buracos com a certa, fora da amostra de validação) antes de propor; (4) afetação conjunta buracos × peças do lote (cada peça num buraco, cada buraco numa peça).
- Vizinha única: marca sempre confiança baixa, nunca «alta» (o §15.1 mostra que 1 vizinha fica em 2.º).
- Reutiliza tools/diagnostico/fit/ (common.py, gt.py, pool.py, real.py). Não dupliques.

Parte 3 — Validação offline
Corre os critérios da Parte 1 sobre: (a) os 467 buracos virtuais do passo 5, (b) os 15 casos reais do passo 6, (c) a direção inversa nos buracos reais do tabuleiro (207–208). Para cada alvo diz [V]/[NT]/[F]. Compara com os números do passo 5 (ganho do filtro mole, da erosão calibrada, da rejeição e da afetação conjunta, isolados e juntos). Mostra figuras vistas dos melhores, dos piores e dos «sem candidata fiável». Se a rejeição só consegue bom resultado à custa de cobertura inaceitável, reporta o compromisso em números e não escolhas por mim.

Parte 4 — GUI e instrumentação de GT (só se a Parte 3 não der [F] no alvo principal)
- Na gaveta de uma célula vazia com ≥ 1 vizinha: «Candidatas para este buraco» com as 3 melhores, cada uma desenhada no buraco com as vizinhas, mostrando custo, margem e confiança. «Sem candidata fiável» é um resultado legítimo. Vizinha única aparece claramente como confiança baixa.
- Lista «buracos por confiança» ordenada (primeiro os de ≥ 2 vizinhas e confiança alta).
- Confirmar/rejeitar fisicamente grava eventos hole_confirmed/hole_rejected (origem «buraco», rank, custo, margem, confiança, versão do fit). É a GT que faltava. Testes Playwright, sem overflow (1366×768 a 150 % e telemóvel).
- python -m src.fit --project projects/alpes --relatorio: top-1/top-3 e Wilson sobre as confirmações acumuladas, por zona, nº de vizinhas e confiança. Diz quando se chega a n ≥ 60 casos (≥ 40 com ≥ 2 vizinhas) e fora do céu, o limite que o §15.6 fixou para decidir o M11.

Fora de âmbito: M6 solta–solta; aceitar automaticamente; segmentação; fotometria entre scans (só mede e reporta se a cor entre scans parece desviar nos casos de outro lote).

Formato da resposta final
- [V]/[NT]/[F] com números, IC de Wilson, partição afinação/validação.
- Que parâmetros foram afinados em quê, e o que ficou de reserva.
- O que o Tiago tem de fazer fisicamente (lotes, peças de fora do céu) e que termos de pesquisa usar para ver os casos na GUI.
- Só me chamas para decisões que sejam do Tiago.
```

## Resultado

Feito: Partes 1–4 completas. Critérios em `docs/diagnostico/fit/M11_CRITERIOS.md` (commit `f6cc2b7`, antes do código); `src/fit.py` + eventos com meta + `confirm --buraco` (`5a7b46c`); afinação em S_T (erosão 0,60 mm, corte 2×, T_abs 2,666) gravada em `calibration.buraco`; validação em S_V: **E5 estrito top-1 98,1 % (95,3–99,3) a N = 32 e 96,2 % (92,8–98,1) a N = 100 [V]**, peça ausente **[F]** na utilidade (falsas `alta` 0,091/buraco, precisão 49 % a π = 10 %), direção inversa 0,06 `alta` por solta [V], 15 casos reais 15/15 [NT]; figuras vistas (`m11_{melhores,piores,sem_fiavel}.jpg`); GUI «Candidatas para este buraco» + secção «Buracos» (botão no fim de «Vai buscar», sem 7.ª aba) + endpoints `/api/holes` + testes; `python -m src.fit --relatorio` (hoje n = 0). Relatório: `docs/diagnostico/fit/M11_RESULTADOS.md`. Por fazer: confirmações físicas (8 buracos `alta` no tabuleiro real), `T_abs` por zona quando houver GT fora de céu/relva.
