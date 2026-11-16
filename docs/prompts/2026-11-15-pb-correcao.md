# 2026-11-15 — P-b: completar `placements.json` e não voltar a perder entradas (proposta B), regra de registo pelas juntas

## Porquê

O diagnóstico P-b (`docs/diagnostico/gui/DETALHE.md` §13.8) mostrou 620 de 699 peças colocadas sem entrada em
`render/placements.json`: o ficheiro anterior a `a249ad6` passou a ser ignorado e nunca foi refeito, e um contorno
re-segmentado tirava a entrada sem a repor. O tabuleiro registava essas peças na hora em cada composição (≈ −0,3 s no
«perto» e no salto a frio se as entradas existissem).

## Decisões

- Proposta B do §13.8: o servidor completa as entradas em falta, deixa de as perder e passa a ter uma verificação
  permanente.
- A regra de registo (com ou sem imagem) decide-se pela medição das juntas, com o critério fixado antes; ficou **«sem
  imagem»** (mediana 0,202 vs 0,250 mm, p95 0,499 vs 0,641 mm nas 70 juntas das 24 peças), em todos os caminhos e na
  chave da entrada (`docs/decisoes.md`).
- Correções do Tiago ao plano: medição final contra `8668365`; a regra entra na chave e as 79 entradas atuais são
  refeitas; igualdade conforme a regra; teste 8; o preenchimento grava o ficheiro uma vez, e mede-se a recomposição, o
  1.º salto com preenchimento e um 2.º arranque que não faz nada.
- Plano aprovado: `C:\Users\tiago\.claude\plans\agente-implementer-skills-graphify-parsed-brook.md` (fora do repositório).

## Prompt verbatim

Agente: implementer. Skills: /graphify  /systematic-debugging  

Regra do grafo: `graphify query/path/explain` antes de qualquer grep ou leitura de ficheiros; `graphify update .` no fim de cada bloco. (Se não tiveres a ferramenta de skills, segue estas regras tal como estão escritas aqui.)

Decisões do Tiago (2026-11-15, DETALHE §13.8):
(1) Proposta B: o servidor completa as entradas em falta de placements.json e deixa de as perder, com uma verificação permanente.
(2) A regra de registo (com ou sem imagem) é decidida pela medição das juntas, com o critério abaixo fixado antes.

Trabalho sempre em cópias; nunca em projects/alpes. Suite com `.venv/Scripts/python.exe -m pytest tests/`.

Passo 0 (medir, sem mexer em src/):
a) Juntas das 24 peças em que a pose pelos cantos difere da corrigida pela imagem: |gap| das juntas com as vizinhas colocadas (métrica de RENDER.md), nas duas poses.
   Critério fixado antes (não ajustar): fica «com imagem» só se a mediana do |gap| melhorar E o p95 não piorar. Caso contrário fica «sem imagem», e o caminho das escritas da GUI passa também a sem imagem; mede as 79 entradas atuais da mesma forma e reporta.
b) Lista todos os que leem placements.json (render, query/_cross_check, «verificar», fit, montar, outros). Para os que decidem alguma coisa (propostas, encaixe, verificações), compara numa cópia o fetch.json/fetch.md e as respostas do «verificar» antes e depois de completar as entradas com a regra escolhida. Se alguma proposta mudar, explica cada mudança. Se não conseguires explicar alguma, para.
c) Confirma que o registo nunca escreve por cima de uma pose manual.

Bloco 1, testes primeiro (a falhar antes do código):
- arranque com entradas em falta: ficam todas preenchidas;
- gravar um contorno manual numa peça colocada: a entrada continua lá;
- rebuild_stale de uma folha com peças colocadas: as entradas continuam lá;
- pose manual preservada;
- um placements.json de formato antigo (sem f_rotation) é refeito, não ignorado;
- preenchimento cruzado por uma escrita: nenhuma entrada perdida (seqlock ou bloqueio de escrita só no commit);
- verificação permanente: falta de entrada para uma peça colocada → aviso no arranque, linha em /api/status, e conta em render.stale_assets.

Bloco 1, código:
- O preenchimento corre em fundo no arranque e cede à GUI (yield_to_gui); o cálculo fica fora do bloqueio e só o commit fica sob o bloqueio de escrita.
- A gravação do contorno e o rebuild_stale passam a registar a peça.
- Regra de registo = a do passo 0, a mesma em todos os caminhos.

Verificação do bloco 1:
- Se ficar «sem imagem», a composição a frio do tabuleiro tem de ser igual byte a byte à de hoje.
- Se ficar «com imagem», as diferenças têm de cair só nas células das 24 peças (mostra um mapa das células que mudaram).
- Mede o tempo do preenchimento no arranque e o tempo até à 1.ª resposta da GUI durante o preenchimento.

Medição final (critério 3, fixado antes): 10 pares alternados b58ae05 | novo, numa cópia em que o servidor completou as entradas.
- «perto» ≤ 1,2 s e «longe» ≤ 0,6 s (mediana);
- POST «Encaixa» e critério 2 com IC 95 % que exclua +0,25 s;
- pico de memória ≤ +200 MB;
- reporta srv_frio_relva_s.

Regras:
- Não alteres testes existentes sem OK do Tiago; lista no commit os testes alterados.
- Um commit por bloco, sem co-author. [V]/[NT]/[F] em cada afirmação.

Paragem:
- uma proposta muda e não consegues explicar porquê;
- a composição deixa de ser igual fora das células esperadas;
- o «perto» fica acima de 1,2 s (não afinar nada, reporta a decomposição).

Fecho:
- DETALHE §13.9 (passo 0, bloco 1, medição final);
- decisoes.md (a regra de registo e porquê);
- HANDOFF (próximo item: 1.º salto, com a ReadyCache fria cronometrada diretamente e não por subtração);
- CLAUDE.md;
- docs/prompts/;
- remove os worktrees temporários.

### Correções do Tiago ao plano (verbatim)

Plano aprovado com estas correções:

1. Medição final: 10 pares alternados 8668365 | novo (não b58ae05, que já tem o remendo e por isso não volta a testar as regressões de b7a88cf), as duas versões na mesma cópia já completada pelo servidor novo. Critérios iguais.

2. A regra de registo (com/sem imagem) entra na chave da entrada (_entry_key ou campo próprio): uma entrada feita com outra regra conta como desatualizada em missing_placements e é refeita, incluindo as 79 atuais. Critério de igualdade corrigido, conforme a regra que ganhar:
   - «sem imagem»: igual byte a byte fora das células das peças (das 79) cuja pose muda; lista e mapa dessas células;
   - «com imagem»: diferenças só nas células das 24.
   Teste novo: uma entrada feita com a outra regra é refeita.

3. Recomposição por causa do mtime: o preenchimento grava placements.json uma vez (ou diz quantas vezes e porquê). Mede e reporta:
   - se a recomposição do tabuleiro (≈ 20 s) acontece na mesma sessão e em paralelo com o ranking a frio e o pré-aquecimento;
   - o 1.º salto num arranque com preenchimento;
   - que um 2.º arranque não preenche nem recompõe nada.

O resto mantém-se, incluindo paragens e fecho.

## Resultado

Ver `docs/diagnostico/gui/DETALHE.md` §13.9 e `docs/diagnostico/gui/dados/r9_pb_*.json`. Resumo:

- **Passo 0 [V]:** regra «sem imagem» pelo critério fixado antes (juntas das 24 peças: mediana 0,202 vs 0,250 mm, p95
  0,499 vs 0,641 mm); nenhuma das 79 entradas antigas tinha a imagem aceite. Completar as entradas não muda nenhuma
  proposta, suspeita, buraco nem «verificar» (só 3 textos `pose_reason`). O registo nunca escreve por cima de uma pose
  manual.
- **Bloco 1 (`6c66217`) [V]:** preenchimento no arranque em fundo, commit sob o bloqueio de escrita, uma gravação;
  `rebuild_*` voltam a registar; regra na chave; verificação permanente. 9 testes novos (8 falhavam antes, 1 já passava);
  nenhum teste existente alterado; suite 648 passed, 1 skipped; `test_concorrencia` 20/20. Tabuleiro igual byte a byte;
  sem recomposição do tabuleiro; 2.º arranque não faz nada. Duas mudanças de ordem medidas (depois dos fantasmas;
  ranking dos buracos no fim do preenchimento).
- **Medição final (10 pares `8668365 | novo`):** «perto» 2,64 → 1,21 s **[F, alvo 1,2 por 0,01 s]** → paragem, sem
  afinar; decomposição: o registo na hora saiu (`_piece_jobs` 1,21 → 0,24 s), o resto é a disputa com os três pedidos
  paralelos (P-a: 0,38 s no lançador). «Longe», POST, critério 2 e memória [V].
- **Por fazer:** o 1.º salto (com a `ReadyCache` fria cronometrada diretamente) e a decisão sobre a P-a.
