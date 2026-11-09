# 2026-11-09 — ronda 9: editor na convenção do índice, os 17 contornos manuais, contorno sugerido pela gémea

## Porquê

Os 17 contornos manuais de 2026-11-07/08 faziam a gémea das peças editadas deixar de ser encontrada (9/9, R7 §1.3), que o R7 atribuiu a um laço «≈ 1,3 mm fora da aresta». O pedido: definir e medir a convenção de silhueta do índice e a do editor, alinhar o editor sem perder as correções reais, corrigir os 17 registos por acréscimo, e oferecer o contorno da gémea como ponto de partida; tudo com critérios fixados antes.

## Decisões

- A leitura do R7 estava invertida: os 17 estão **dentro** do automático (a ajuda do editor mandava pôr «fundo» sobre a linha negra da sombra, e o índice inclui a sombra). Não existe um δ constante nem por zona; o desvio é por lado e por cor (`CONVENCAO.md`).
- O que o editor grava segue a convenção do índice (halo da própria peça + núcleo negro da sombra; traços de sombra ignorados por inteiro; automático bit a bit fora da região de influência; identidade sem traços). O caminho bruto (`tests`, `tracos_gt.py`) não muda.
- Os 17 registos: 16 «reposição» (contorno automático exato, `manual_override` sai), P0045 renormalizado e a confirmar pelo Tiago.
- Sugestão pela gémea só de registos `convencao: "indice"`; registo rígido por cantos + ICP com a correspondência escolhida pelo contorno inteiro; medido em 268 pares colocados e 20 E-sym (mediana 0,13 mm). Os 6 pares acima de 0,6 mm são o corte c32|c33.
- O teste `test_gui_guardadas::test_real_board_cells_without_orthogonal_neighbour_are_not_in_vai_buscar` não depende dos contornos (fetch.json vivo vs log cortado); fica a falhar, a correção da fixture é decisão do Tiago.
- Achado lateral: nesta máquina `projects/alpes` não tinha `pieces/*.npz` das folhas S0028–S0037 (375 peças); as medições refazem os ativos na cópia antes das linhas de base.

Detalhe em `docs/decisoes.md` (2026-11-09) e `docs/diagnostico/editor/CONVENCAO.md`.

## Prompt verbatim

> Contexto
> Projeto puzzle_piece_finder. Faz git pull. Lê docs/diagnostico/gemeos/R7_RESULTADOS.md §1.2–1.3, docs/diagnostico/editor/TRACOS.md, docs/HANDOFF.md e docs/decisoes.md. Regras habituais: [V]/[NT]/[F]; critérios fixados antes de correr; commits em português SEM co-author nem linha Claude-Session; push sem --force; não alteres testes existentes sem o dizeres; não feches reports; servidor da GUI parado; testa em cópia de projects/alpes.
>
> Problema
> Os 17 contornos manuais do Tiago (overrides.jsonl, 16 de 2026-11-08) ficam ≈ 1,3 mm fora do contorno automático (52–68 mm² a mais, IoU 0,82–0,87, p95 1,22–1,52 mm), e a gémea dessas peças deixa de ser encontrada (9/9, R7 §1.3), porque a silhueta editada e a da gémea seguem convenções diferentes. É também a causa do único teste que falha na suite (pré-existente, vem dos dados).
>
> Parte 1 — Alinhar a convenção do editor
> 1.1 Define, com medição, a convenção de silhueta do índice (inclui ≈ 0,5 mm de sombra e franja por desenho; limiares de gémea e erosão calibrados sobre ela) e a do resultado do editor. Mede o desvio sistemático entre elas nas peças em que o automático estava certo (as 17, e as peças de controlo com GT manual do Photoshop em docs/diagnostico/reports/R0011_R0012_manual/).
> 1.2 Faz o editor produzir contornos coerentes com a convenção do índice (por exemplo calibrando o deslocamento da fronteira do solver ou do laço), sem mudar a pré-visualização e sem tornar as correções reais (peça «comida», sombra colada) menos úteis. Critério fixado antes: depois da correção, o desvio médio automático–manual nas peças em que o automático estava certo fica ≤ 0,3 mm, e a gémea de uma peça editada é encontrada tão bem como antes da edição.
> 1.3 Os 17 contornos já gravados: mede, por peça, quanto do desvio é uniforme (convenção) e quanto são correções reais. Propõe e implementa a correção, sem apagar nada (append-only: novo evento de reedição, reversível). Se uma peça tiver correção real que a normalização apagaria, diz qual e deixa-a para revisão do Tiago. Depois da correção, o teste que falha (data-driven) tem de passar sem alterar o teste.
>
> Parte 2 — Contorno sugerido a partir da gémea
> 2.1 Quando o Tiago abre o editor numa peça cuja gémea (relação do índice ou célula gémea) tem contorno manual e ela não, oferece como ponto de partida o contorno da gémea rodado 180° e registado à peça (melhor ajuste rígido), marcado «sugerido pela gémea». Nada é gravado até o Tiago confirmar. Mostra no editor a diferença entre a sugestão e o automático.
> 2.2 Mede, sobre os pares com contorno manual de ambos os lados (se existirem) e sobre as gémeas sem edição, o desvio entre a sugestão e o contorno certo. Diz se a sugestão é um bom ponto de partida (distância média e p95) e em que casos piora o contorno.
> 2.3 Se o editor for aplicado à gémea, não deixes que a peça A fique com convenção diferente da B. Testes Playwright do fluxo (abrir, aceitar, rejeitar a sugestão).
>
> Parte 3 — Verificação
> 3.1 Reconstrói as gémeas das peças editadas e mostra: antes/depois o nº das que voltam a ser encontradas, com as propostas idênticas nas peças sem edição (diff = 0).
> 3.2 Suite completa sem falhas.
>
> Formato da resposta final
> - [V]/[NT]/[F] com números (desvios em mm, IoU, gémeas recuperadas).
> - Que contornos foram corrigidos, quais ficaram para o Tiago rever e porquê.
> - O que o Tiago tem de ver na GUI e onde (termos de pesquisa) e só as decisões que são dele.

(Durante a ronda: «Usa o graphify» — a consulta ao grafo deu os consumidores da convenção: `twin`, `border`, `consistency`, `locate`, `fit`.)

## Resultado

(a preencher no fecho da ronda)
