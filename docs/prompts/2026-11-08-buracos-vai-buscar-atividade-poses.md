# 2026-11-08 (6) — sugestões `alta` em «Vai buscar», página «Buracos», contador e pausa; registo de atividade; pares (pose automática, pose manual)

## Porquê

Em uso real o Tiago confirmou fisicamente os 10 buracos de confiança `alta` que o M11 propôs (10 `hole_confirmed`, rank 1, 0 `hole_rejected`; Wilson 95 % inferior 0,72; todos céu). A decisão da ronda 5 («ranking, nada em Vai buscar», pelos números de peça ausente) ficou desmentida pelo uso: as soltas no índice estão de facto no tabuleiro por montar. O Tiago quer as `alta` em «Vai buscar», o resto numa página própria, rejeição em um clique (sem isso a precisão não se mede) e um contador com regra de pausa. Além disso acha os logs curtos («tabuleiro pronto», «tabuleiro 1 células recompostas» duas vezes, 3 min sem progresso) e quer preparar a medição automático-vs-manual das poses sem aprender nada.

## Decisões

- Critérios antes do código (`docs/diagnostico/fit/M11_CRITERIOS.md` §8, commit `af9f2a7`): sugestão `alta` = rank 1 de um buraco `alta` coerente com a afetação conjunta; decisão = `hole_confirmed`/`hole_rejected` com origem `buraco`, `alta`, rank 1; contador com Wilson 95 %; **pausa a ≥ 3 rejeições nas últimas 20 decisões** desde a última reativação (`holes_alta_resumed`), com a sensibilidade documentada (dispara em 7,5 % das janelas a 95 % de precisão verdadeira, 32 % a 90 %, 79 % a 80 %); rótulo «baixa» = `media` com m = 1 (GUI). Registado em `docs/decisoes.md`.
- A fusão «gémea + buraco» para a mesma peça e célula é um só cartão com dois chips; as ações gravam os dois registos (`placed` origem `gemeo` + `twin_confirmed` + `hole_confirmed`, ou `twin_rejected` + `hole_rejected`) numa só escrita. `fetch.json`/`fetch.md` (CLI) não mudam: a fusão é no servidor, que tem a cache dos buracos.
- Registo de atividade com `logging` puro (`src/activity.py`): terminal + `projects/<id>/logs/servidor-AAAAMMDD.log` + anel para o painel; nada por pedido trivial (só > 1 s).
- Painel «Atividade» como gaveta fixa no fundo (não é aba; fechada = `display: none`).
- Pares de pose: `pose_set.antes` passa a levar a pose automática inteira; `--pares` ganha a secção «Poses manuais» (por zona e direção, n, média, IC t). Nenhuma calibração, nada ligado à pose automática.
- A repetição de «tabuleiro 1 células recompostas»: ver «Resultado».

## Prompt verbatim

```
Contexto
Projeto puzzle_piece_finder. Faz git pull. Lê docs/HANDOFF.md, docs/diagnostico/fit/RESULTADOS.md §13, docs/gui-design.md e docs/decisoes.md. Segue as regras habituais: [V]/[NT]/[F], commits em português sem co-author nem linha Claude-Session, push sem --force, não alteres testes existentes sem o dizeres, não feches reports, vê git status de projects/alpes antes de escrever lá.

Decisão do Tiago (regista em docs/decisoes.md)
Em uso real, os 10 buracos de confiança `alta` que o M11 propôs foram todos confirmados fisicamente (10 hole_confirmed, rank 1, 0 hole_rejected; Wilson 95 % inferior ≈ 72 %; todos céu). O Tiago quer as sugestões `alta` (≥ 2 vizinhas) em «Vai buscar», e as de confiança média e baixa numa página própria. Aceita-se com os limites abaixo; o que ainda não está medido fora do céu fica por medir.

Parte 1 — Buracos em «Vai buscar»
1.1 As sugestões por buraco com confiança `alta` aparecem em «Vai buscar», com chip «por buraco · alta» distinto das de gémea. Mostram a peça a ir buscar (saco e nº no lote) e a célula, com a candidata desenhada no buraco com as vizinhas. Não entra nenhuma média/baixa em «Vai buscar». Se um buraco tem gémea aceite E alta por buraco para a mesma peça/célula, mostra uma só, com os dois chips.
1.2 Página «Buracos» (já existe a secção por confiança; mantém-na, agora acessível a partir do «Vai buscar» e por pesquisa `buracos`): os níveis média, baixa e «sem candidata fiável», cada um com as 3 melhores candidatas por buraco («se não for esta, talvez seja uma destas»).
1.3 Rejeição em um clique: «Não encaixa» em cada candidata grava hole_rejected com rank, custo, margem, confiança e versão do fit. Sem isto a precisão não se mede.
1.4 Contador visível das sugestões `alta`: acertos / falhas / total, com Wilson 95 %. Regra declarada e fixada nos critérios antes de implementar: se nas últimas 20 decisões `alta` houver ≥ 3 rejeições, aparece um aviso e as sugestões `alta` passam para a página «Buracos» até o Tiago as reativar. Documenta o limiar e porque o escolheste (o Tiago pode ajustá-lo).
1.5 Testes Playwright (sem overflow a 1366×768 a 150 % e telemóvel), mais testes do contador e da regra de aviso.

Parte 2 — Registo de atividade
O Tiago acha que os logs são curtos e pouco informativos. Hoje o arranque só diz «tabuleiro pronto» e «tabuleiro 1 células recompostas» duas vezes (verifica se a repetição é um defeito) e a primeira abertura de um buraco leva ≈ 3 min sem uma linha de progresso.
2.1 Linhas úteis no terminal e num ficheiro projects/alpes/logs/servidor-AAAAMMDD.log: consulta corrida (nº peças, buracos, tempo por passo), cache usada ou recalculada, ativos desatualizados refeitos, progresso das operações longas (ex.: tiras das ≈ 600 peças: n/N e tempo), cada evento escrito no log (tipo, peça, célula, origem), pedidos lentos (> 1 s). Níveis (info/aviso/erro). Sem ruído: nada por pedido HTTP trivial.
2.2 Painel «Atividade» na GUI: recolhível (não é uma 7.ª aba), com as últimas N linhas em tempo real (SSE), filtro por tipo e nível, e o carimbo de tempo. Não ocupa espaço quando fechado.
2.3 A pasta logs/ vai para o .gitignore. Rotação simples por dia.

Parte 3 — Preparar o terreno para calibrar com as edições manuais (só medição, sem aprender nada)
Hoje há 4 pose_set e 1 linha em overrides.jsonl: pouco para aprender. Não implementes aprendizagem. Faz só: (a) guardar o par (pose automática, pose manual) em cada pose_set, como o --pares já faz para contornos, e um relatório python -m src.overrides --project projects/alpes --pares que resuma o desvio por zona e direção com n, média e IC; (b) diz-me, sem agir, a partir de que n o desvio seria utilizável para calibrar um parâmetro (com peças de reserva), e quais parâmetros candidatos existem (erosão, banda da sombra, deslocamento por F). Não ligues nada à pose automática.

Formato da resposta final
- [V]/[NT]/[F].
- O que o Tiago tem de ver na GUI e onde (termos de pesquisa).
- Só me chamas para decisões que sejam do Tiago.
```

## Resultado

- **Parte 1 [V]:** `fit.alta_counter`/`alta_suggestions`, evento `holes_alta_resumed`, `hole_confirm(place_origin)`, `confirm(gemea=)`; servidor `/api/fetch.buracos_alta`, `GET /api/holes/alta`, `POST /api/holes/alta/reativar`, `gemea: true`; GUI: cartões «por buraco · alta» em «Vai buscar», cartão fundido, contador com Wilson, aviso de pausa + «Reativar», página «Buracos» por grupos com 3 cartões por buraco e «Não encaixa» em um clique. Testes novos: `test_fit_alta` (9), `test_server_alta` (5), `test_gui_buscar_buracos` (4; 1366×768, 911×512 @1,5, 390×844). No projeto real: contador 10/0/10 (Wilson 72–100 %); 0 buracos `alta` na pool atual (38 média, 171 sem) → os cartões só aparecem com soltas novas.
- **Parte 2 [V]:** `src/activity.py` (terminal + `projects/<id>/logs/servidor-AAAAMMDD.log` + anel), linhas de arranque, consulta por passo, caches, tiras n/N (SSE `holes_progress`), um por evento escrito, pedidos lentos > 1 s; painel «Atividade» (gaveta fixa, SSE, filtros); `logs/` no `.gitignore` (já coberto, linha explícita). Testes: `test_activity` (5), `test_gui_atividade` (3). A repetição de «tabuleiro 1 células recompostas» **não se reproduziu** na cópia [NT na máquina do Tiago]; a linha traz agora células, versão a → b e gatilho.
- **Parte 3 [V]:** `pose_brief(full=True)` em `pose_set.antes`; `overrides.pose_pairs`/`pose_summary`/`mean_ci`; `--pares` com a secção «Poses manuais» (n = 4, céu, |d| 0,78 mm [0,41, 1,15]); resposta ao (b) em `POSE_MANUAL.md`: ≈ 20–25 poses por zona ou 60–100 no total para parâmetros direcionais, com peças de reserva ao acaso (viés de seleção); parâmetros candidatos listados; nada ligado. Teste: `test_overrides_poses` (3).
- **Suite completa:** **388 passed, 1 skipped (284 s)** (OpenCV 4.11, venv4; uma primeira corrida deu 5 falhas de layout da barra do topo com o 4.º toggle «Atividade» a 360/390/1181 px, resolvidas pondo o botão nos controlos de zoom abaixo de 1300 px; OpenCV 5.0 [NT]). Nenhum teste existente alterado.
- **Fora [NT]:** precisão fora do céu; tiras a frio no projeto real (na cópia estavam em cache); cartão fundido com uma proposta de gémea real.
