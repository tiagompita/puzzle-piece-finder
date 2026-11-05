# Ronda 2026-11-02 → 2026-11-05: cor/recorte das peças e «Coloca agora»

*Fechado em 2026-11-05.* Reconstruído de `docs/revisao.md`, do `CLAUDE.md` e do feedback desta ronda; o texto original dos pedidos do Tiago não foi guardado, por isso a secção «Prompt» é um resumo fiel e não verbatim.

## Porquê
Depois de testar a GUI (ronda «GUI não aprovada», 2026-11-02) o Tiago reportou: peças mal recortadas ou com verde visível (R0001, R0011, R0012, R0018–R0020), peças mal colocadas ((26,1) por baixo de (25,1), (47,2) inclinada, (1,63), (40,64)), e uma lista «Vai buscar» com peças sem nenhuma vizinha ortogonal montada (R0013–R0017: (4,43), (4,49), (4,50), (4,53), (3,54)). Os itens 2–5 da ronda estavam em stage; o Tiago suspeitava de cor nalgumas peças.

## Decisões
- **Item 2 (trim de 0,48 mm no desenho): recusado e removido.** Piora 44 células e melhora 0; células com buraco > 5 %: 131 → 179; > 10 %: 39 → 73; meio trim (0,24 mm) 137 / 45; alinhar o lado reto de 208 peças de borda não muda nada (132 / 38). A causa dos buracos é pose/recorte (erro ~1 mm; 363 de 588 peças a > 1,5° de um múltiplo de 90°), não escala. Registado em `docs/decisoes.md`.
- **Item 4 (reconsulta incremental depois de confirmar):** portado (vizinhas livres + candidatas que saíram do conjunto, `cand_ids`).
- **Item 5 (interface):** portado — legenda com duas setas e mão, Reportar vermelho e afastado da pré-visualização, «Centrar» → «Localizar peça» com ícone.
- **Item 3 (regra do Tiago, inegociável):** peça sem vizinha ortogonal colocada **não aparece em «Vai buscar»** (diagonal e moldura não contam; borda colocada conta). Passa para a aba **«Guardadas»**, recolhida, com «Não procurar ainda». Sem exceção para `posicao_conhecida`.
- **Cor: adiada.** Nenhuma evidência de que a cor explique os casos «comida» / «por baixo» (são geometria/recorte).
- **Painel de Reports** (só leitura) acrescentado; os reports fecham-se no ficheiro.

## Prompt (resumo; não verbatim)
Investigar sem alterar código as 8 células mal recortadas/posicionadas; medir desvios em mm e graus; testar as hipóteses (trim, posição pelo centro da silhueta, problema anterior); propor correção com antes/depois e contagem de células; dizer quantas propostas «Coloca agora» havia. Depois: item 2 fora; commits por item; item 3 só depois de reconciliar «7 listadas vs 16 em Coloca agora» com o que a GUI mostra de facto; painel de Reports; diagnóstico de (3,32)/(3,33); atualizar CLAUDE.md. Por fim: correr `screenshot.py`, commitar, fechar R0013–R0017.

## Resultado
- Commits: `e6ce712` (reconsulta + decisões), `d5cc1a7` (interface), `2c15ef6` (aba Guardadas + `fetch_group`), `25df1a9` (painel de Reports). Testes: 160 passed, 1 skipped; `tools/gui/screenshot.py` verificado (17 capturas).
- «7 vs 16»: os 16 eram entradas `origem=seccao` (grupos para a Mesa), não peças; os 7 cartões eram todos `gemeo/aceite` sem vizinha ortogonal.
- R0013–R0017 fechados («verificado pelo Tiago na GUI, 2026-11-05, + testes»). 22 reports continuam abertos.
- (3,32)/(3,33): diagnosticado (secções de 1 peça sem âncora; pista `ocupada_legado`); indício P0294 em (3,32), P0291 em (3,33) [NT]; espera pelo Tiago.
- Por fazer: recorte «comido», baseline de buracos/pose, (26,1)/(25,1), (1,63)/(47,2), abas na barra de topo, «Editar report» — em `docs/HANDOFF.md`.
