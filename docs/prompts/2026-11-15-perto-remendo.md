# 2026-11-15 — Critério 3 «perto»: passo 0, remendo das células alteradas, leitores rasgados

## Porquê

Depois de §13.6 de `docs/diagnostico/gui/DETALHE.md`, o «perto» (um «Encaixa» dentro da região à vista) ficava em
2,74 s contra o alvo de 1,2 s: quase tudo era a composição da região inteira (≈ 2,0 s de CPU, ≈ 100 peças), e desligar
as suspeitas e o `rank_all` só poupava 0,06 s. No cenário «mover» forçado, o `rank_all` e o «verificar» devolviam
estados que nunca existiram (§13.5).

## Decisões

Do Tiago (2026-11-15), no plano aprovado `agente-implementer-skills-graphify-parsed-brook.md`:
1. Implementar o remendo das células alteradas para o «perto» (§13.4): as células a refazer saem da diferença das
   assinaturas de conteúdo por peça; diferença desconhecida ou grande → composição inteira; um array cruzado por uma
   escrita não é guardado.
2. `rank_all` com seqlock para detetar e descartar; «verificar» com seqlock e repetição; sem resultado anterior,
   «não verificado» (estado explícito, sem veredicto) e o browser volta a pedir.
3. Critério 1 fica inconclusivo (+0,36 s, IC [−0,14, +0,65]); o 1.º salto passa a item próprio, a seguir.

Alterações do Tiago ao plano: (1) o remendo redesenha na zona suja todas as peças cuja caixa a interseta, pela ordem
normal, a partir da base da arte e de um `zbuf` limpo; listar os passos de `compose_board` que leem vizinhança e parar se
algum for global; (2) igualdade byte a byte também numa cópia do projeto real (céu e relva a ppc 100, ≥ 10 escritas ao
acaso) e, nos 10 pares, quantos «perto» caíram na composição inteira; (3) «verificar» sem resultado anterior devolve
«não verificado»; (4) `rank_all`: teste com 5 colocações a 1 s; (5) passo 0 com cronómetros por fase, não
`sys.setprofile`.

Critérios fixados antes de medir: «perto» ≤ 1,2 s e «longe» ≤ 0,6 s (mediana, pares alternados `8668365 | novo`);
imagem igual byte a byte a uma composição a frio; POST e critério 2 sem regressão (IC 95 % que exclua +0,25 s); pico de
memória ≤ +200 MB; reportar `srv_frio_relva_s`.

## Prompt verbatim

> Agente: implementer. Skills: /graphify /systematic-debugging — Consulta o grafo do Graphify antes de grep ou de ler
> ficheiros. No fim de cada bloco, corre `graphify update .`. Decisões do Tiago (2026-11-15): (1) implementar o remendo
> das células alteradas para o «perto» (DETALHE §13.4); (2) `rank_all` com seqlock para DETETAR e descartar, e
> «verificar» com seqlock e repetição; (3) critério 1 fica inconclusivo e o 1.º salto passa a item próprio, a seguir.
> Critérios fixados antes de medir (não ajustar): «perto» ≤ 1,2 s (mediana, 5 pares alternados 8668365 | novo, na mesma
> sessão). «longe» continua ≤ 0,6 s. Imagem servida igual byte a byte a uma composição a frio, em todos os casos de teste
> abaixo. POST «Encaixa» e critério 2 sem regressão (intervalo de 95 % que exclua +0,25 s); pico de memória ≤ +200 MB.
> Em cada medição, reporta também o «salto a frio, só HTTP» (relva) como referência da velocidade da máquina. Passo 0
> (medir, antes de mexer): decompõe os ≈ 0,45 s da composição que não são CPU e os ≈ 0,22 s do pedido fora da composição
> (assinatura, bloqueios, JPEG). Hipótese a testar: os pedidos que o browser faz em paralelo no `board_changed`
> (`/api/board`, `/api/ghosts`, `/api/montar`, todos em `foreground()`) competem com o detalhe. Para testar, compara com
> esses pedidos atrasados, só no lançador de diagnóstico. Se o passo 0 mostrar uma causa barata, propõe-a no plano em
> separado do remendo. Bloco 1, remendo: as células a refazer saem da diferença das assinaturas de conteúdo por célula,
> não da célula da escrita (apanha vizinhas que mudam de pose (relax), a sobreposição de 0,3 mm, a prioridade de
> profundidade, as peças «por confirmar» e os fantasmas). Se a diferença for desconhecida ou maior do que um limiar, faz
> a composição inteira. Um array cruzado por uma escrita não é guardado (mesma regra de f85c092). Testes ANTES do código,
> cada um a comparar byte a byte com uma composição a frio: colocar no céu e na relva; uma vizinha que muda de pose;
> desfazer; pose manual gravada e reposta; tirar do lugar; peça «por confirmar»; peça re-segmentada (contorno manual).
> Bloco 2, leitores rasgados: `rank_all`: se o contador do seqlock mudou durante a leitura, o resultado não é publicado;
> fica a lista anterior marcada `desatualizada` (a escrita já pede o recálculo). «verificar»: repete como as suspeitas;
> à 3.ª falha devolve o resultado anterior marcado. Teste do cenário «mover» forçado para cada um, a falhar antes da
> correção. Bloco 3, docs: em DETALHE, critério 1 inconclusivo (+0,36 s, IC [−0,14, +0,65]); em HANDOFF, o 1.º salto
> (≈ 6 s, alvo 4 s) como próximo item. Regras: trabalha numa cópia; nunca em projects/alpes. Suite completa com
> `.venv/Scripts/python.exe -m pytest tests/`; test_concorrencia 20/20. Não alteres testes existentes sem OK do Tiago;
> lista no commit os testes alterados. Um commit por bloco, sem co-author. [V]/[NT]/[F] em cada afirmação. Paragem: se a
> igualdade byte a byte falhar num caso e não encontrares a causa em 2 tentativas, para e reporta. Se o «perto» ficar
> acima de 1,2 s, não afines nada: reporta a nova decomposição. Se o pico de memória passar o limite, para antes de
> commitar o bloco 1. Fecho: DETALHE §13.7, HANDOFF e o ficheiro do prompt em docs/prompts/.

Alterações do Tiago ao plano (aprovadas), transcritas como vieram:

> (1) compose_patch redesenha na zona suja TODAS as peças cuja caixa a interseta, pela ordem normal, a partir de
> base_art e de um zbuf limpo nessa zona; listar cada passo de compose_board que lê vizinhança com o seu raio e alargar a
> zona suja por esse raio; se algum passo for global, parar. (2) Igualdade byte a byte também numa cópia de
> projects/alpes (céu e relva a ppc 100, ≥ 10 escritas ao acaso: colocar, desfazer, pose manual gravar/repor, tirar); nos
> 10 pares, reportar quantos «perto» caíram na composição inteira (esperado 0). (3) «verificar» sem resultado anterior
> devolve «não verificado» (estado explícito, sem veredicto) e o browser volta a pedir. (4) rank_all: teste com escritas
> seguidas (5 colocações a 1 s) que conte as publicações e prove que publica logo que as escritas param; reportar o tempo
> máximo de lista desatualizada. (5) Passo 0 com cronómetros por fase em compose_board, não sys.setprofile.

## Resultado

Números e tabelas em `docs/diagnostico/gui/DETALHE.md` §13.7; dados em `docs/diagnostico/gui/dados/r7_*.json`.

- **Passo 0 [V]:** atrasar no browser `/api/board`, `/api/ghosts` e `/api/montar` tira ≈ 1,2 s ao «perto» (2,65 → 1,44 s):
  disputa do GIL no código Python da composição (registo na hora de 88 de 117 peças, 1,00 → 0,07 s). Os ≈ 0,22 s fora da
  composição são o `_region_sig` (0,16–0,18 s), não os 30–40 ms estimados. Propostas P-a / P-b / P-c, não implementadas.
- **Bloco 1 (`b7a88cf`):** remendo das regiões (`render.compose_patch`, `PatchCache`). Tabela 1-0 confirmada (nenhum passo
  global). Igual byte a byte em 8 casos sintéticos (7 falhavam antes), num teste de esforço novo e em 12 escritas na cópia
  real (0 diferenças). 10 pares: «perto» 2,51 → 1,60 s **[F, alvo 1,2; paragem, nada afinado]**, 0/10 na composição
  inteira; «longe» 0,27 s [V]; memória +99 MB [V]; POST «perto» +0,12 s e salto a frio no browser +0,17 s com IC que não
  exclui +0,25 s **[F]**. Decomposição nova: o redesenho custa 0,07 s; o resto é a preparação das peças a disputar o GIL
  com os pedidos paralelos (1,21 s; 0,12 s sem eles) e a assinatura (0,20 s); com P-a, 0,44 s no lançador.
- **Bloco 2 (`1ba4b19`):** `rank_all` só publica sem escrita pelo meio; «verificar» com `seq_read` (espera por uma
  escrita em curso no máximo 0,5 s por tentativa), «não verificado» sem resultado anterior e repetição no browser. 8 testes novos falhavam antes, 9/9 depois; 5 colocações a 1 s: 1
  publicação, 2,57 s depois da última escrita, lista desatualizada no máximo 6,80 s.
- **Bloco 3:** este ficheiro, DETALHE §13.7, `docs/decisoes.md`, HANDOFF (próximo item: o 1.º salto), linhas do `CLAUDE.md`.
- Testes existentes alterados: nenhum. `test_concorrencia.py` 20/20 antes de cada commit de código. Suite: 630 passed,
  1 skipped no bloco 1; 639 passed, 1 skipped no bloco 2 (a 1.ª corrida do bloco 2 falhou em
  `test_f2.py::test_verificar_does_not_wait_for_the_write_lock`, 10,06 s: o `seq_read` esperava até 90 s por uma escrita;
  corrigido no código com `VERIF_WAIT_S`).
- **Por decidir pelo Tiago:** P-a / P-b / P-c; aceitar ou não o custo do remendo no salto a frio e no POST «perto».
