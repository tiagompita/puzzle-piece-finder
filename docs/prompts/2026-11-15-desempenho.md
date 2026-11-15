# 2026-11-15 — Fase de desempenho (antes da F4): P0, P0b e P1

## Porquê

Antes da F4 o Tiago pediu (2026-11-14) para explicar dois testes que falhavam ao acaso e um plano para o arranque
(1.º salto 13–14 s), o salto a frio (3,8–4,1 s), o detalhe depois de um «Encaixa» (3,3–4,1 s) e o «verificar» a frio
(1,6–2,2 s). O plano foi aprovado em 2026-11-15 com decisões e acrescentos: entre eles o **P0b**, a regressão do POST
de um «Encaixa» (5,9–7,0 s contra 4,4 s em DETALHE §6.2), com critério ≤ 2,0 s.

## Decisões

- Do Tiago (plano `agente-implementer-skills-systematic-deb-eager-lamport.md`): a vista não salta quando o cartão muda
  sozinho («localizar» pisca uma vez; marca estática com `prefers-reduced-motion`); portão no teste da fila e
  `gui.stop()` nas fixtures (aceite como fixture `autouse` em `tests/conftest.py`); mosaicos com duas condições; C2 só
  medido; ordem P0 → P0b → P1a/P1b → 1a → 1b+1c → 1d → E → C; paragens obrigatórias, entre elas «o P0b exige mudar o
  comportamento».
- **P0b: paragem.** Não há regressão de código (bisect de 5 commits sobre a mesma cópia: 5,2–5,9 s em todos); é
  crescimento dos dados mais a recarga do browser a competir pelo GIL. ≤ 2,0 s com a GUI aberta exige mudar o
  comportamento (suspeitas em segundo plano ou responder antes da reconsulta). Tabela por fase e opções em
  `docs/diagnostico/gui/DETALHE.md` §11.3. À espera do Tiago.

## Prompt verbatim

Sessão principal (1.ª mensagem):

> Agente: implementer. O modo de plano JÁ TERMINOU: o Tiago aprovou o plano e podes editar, correr testes e medições e
> fazer commits. Skills (sem a ferramenta Skill; segue os princípios): systematic-debugging (reproduzir, causa raiz com
> evidência antes de corrigir, teste que falha antes da correção), verification-before-completion (nada se declara
> feito/verde sem correr o comando e ler o resultado), graphify (antes do primeiro grep/leitura de código, `graphify
> query "<pergunta>"`; ler só as linhas localizadas; `graphify update .` no fim).
>
> Projeto d:\DEKSTOP\puzzle_piece_finder (Windows, `.venv/Scripts/python.exe`).
>
> Fontes:
> - PLANO APROVADO: C:\Users\tiago\.claude\plans\agente-implementer-skills-systematic-deb-eager-lamport.md. Lê-o por
>   inteiro. As secções «Decisões do Tiago (2026-11-15)» e «Acrescentos do Tiago (2026-11-15)» mandam sobre o resto.
>   Onde o texto antigo as contradiz (o POST do Encaixa «fora do plano»; a ordem dos commits sem o P0b), mandam os
>   Acrescentos. Atualiza essas duas linhas no DETALHE.md quando escreveres o §11.
> - O teu roteiro passo a passo da sessão anterior (escrito em modo de plano, sem nada executado):
>   C:\Users\tiago\.claude\plans\agente-implementer-skills-systematic-deb-eager-lamport-agent-a3458d18a35287639.md. Usa-o.
> - Também: docs/HANDOFF.md e docs/diagnostico/gui/DETALHE.md §5–§10.
> - Scripts e protótipos do diagnóstico: …\scratchpad\t0\.
> - Cópia de partida de projects/alpes: …\scratchpad\alpes_base\. Copia-a de novo por corrida; não a alteres.
>
> Resposta às tuas perguntas da sessão anterior:
> - `gui.stop()`: o fixture `autouse` em `tests/conftest.py` que regista cada `Gui` criada e chama `stop()` no fim fica
>   aceite. É a forma de «as fixtures chamarem gui.stop()» que o Tiago aprovou. Diz na mensagem do commit que foi assim.
> - P0b: a tua leitura (`_emit_suspeitas` → `consistency.evaluate` dentro do POST, com o bloqueio de escrita) é uma
>   hipótese. Mede primeiro:
>   - tempos por fase do POST, sem browser e com browser;
>   - bisect em `git worktree` sobre a mesma `alpes_base`.
>   Corrige a regressão se for uma regressão de código. Se chegar a ≤ 2,0 s exigir mudar o comportamento (responder
>   antes da reconsulta, suspeitas em segundo plano, etc.), PARA e devolve-me a tabela por fase com as opções. Não
>   implementes essa mudança.
>
> Ordem: P0 → P0b → P1a/P1b → 1a → 1b+1c → 1d → E → C. C2 só se mede; não o implementes. P1c (CLAUDE.md) NÃO é teu:
> não edites o CLAUDE.md.
>
> Paragens obrigatórias (para e devolve-me um relatório com os números):
> - um critério de sucesso falha depois da parte que o devia cumprir;
> - um teste de identidade de píxeis falha, ou uma das duas condições dos mosaicos não se confirma;
> - `test_concorrencia` não dá 20/20;
> - o P0b exige mudar o comportamento.
> Fora disso, avança sem parar.
>
> Commits:
> - Um por bloco: P0+P0b+P1, parte 1, E, C. Cada um com a tabela dos 5 critérios antes/depois em DETALHE.md §11, medida
>   com `tools/diagnostico/gui/desempenho.py` (promovido de t0/baseline.py), e com a lista dos testes existentes
>   alterados na mensagem.
> - Mensagens em português, SEM Co-Authored-By.
> - Não mexas em projects/alpes; as medições fazem-se numa cópia.
> - Convenções de src/: tabs, `__all__`, docstrings.
> - Suite: `.venv/Scripts/python.exe -m pytest tests/`.
>
> No fim de tudo:
> - suite completa;
> - capturas do céu e da relva, antes e depois;
> - docs/HANDOFF.md com o estado, não o histórico;
> - o prompt fechado em docs/prompts/ (formato do README de lá);
> - `graphify update .`.
>
> Relatório final curto para mim: […] (por bloco, o que mudou e o hash; a causa do P0b, com evidência; a tabela dos 5
> critérios; a suite e o `test_concorrencia`; as condições dos mosaicos; os testes existentes alterados; [NT]/[F]; os
> factos para o CLAUDE.md). Se parares numa paragem obrigatória, entrega o mesmo relatório até onde chegaste, mais os
> números que motivaram a paragem.

Sessão principal (retoma, a meio):

> Retoma a fase de desempenho, interrompida pelo limite de sessão; segue as instruções do Tiago abaixo. […]
> 1. Não descartes nada. […] 2. Corre os testes do P0 […], 20 vezes os dois que falhavam ao acaso. […] 3. […] refaz as
> medições «antes» com desempenho.py numa cópia do projeto em 9f672c0 […] 4. Continua pela ordem do plano […] com as
> mesmas regras de paragem e um commit por bloco. 5. Faz commit de cada bloco assim que fechar […]. Mantém as paragens
> obrigatórias, entre elas: se chegar a POST ≤ 2,0 s no P0b exigir mudar o comportamento, para e devolve a tabela por
> fase com as opções.

Sessão principal (decisão do Tiago sobre o P0b):

> Decisão do Tiago sobre o P0b: implementa A1–A4 + B; C não. Depois continua com a parte 1, E e C a partir do ramo
> wip/desempenho-parte1. […] A chave de cada cache nova inclui o recorte da peça e a calibração; cobre-as no
> tests/test_concorrencia.py e no teste «corrigir o recorte refaz o que dela depende». `fetch.*`,
> `consistency.evaluate` e o resultado da reconsulta ficam iguais antes/depois na cópia (prova-o). Critério: POST do
> «Encaixa» ≤ 2,0 s, sem browser e com `/novo/` aberto. […] Commit próprio do P0b. Depois, sem parar: parte 1 → E → C,
> pela ordem e com as paragens do plano, um commit por bloco em main (testa e mede o que está no wip antes de fundir;
> não fundas nada sem testes verdes). C2: só se mede. […]

## Resultado

- `64ac6e8` **P0 + P1 [V]** e a medição do P0b (sem regressão de código: bisect de 5 commits iguais).
- `aae3a9d` **P0b [V]:** A1–A4 + B; POST 0,7–1,7 s (sem browser e com a GUI aberta); saídas iguais antes/depois.
- `2d34c19` **parte 1 [V nos testes e no ranking; F nos critérios 1 e 4]:** paragem obrigatória (DETALHE §11.7).
- Suite 596 passed, 1 skipped, 0 failed; `test_concorrencia` 20/20.
- **Por fazer:** decisão do Tiago sobre os critérios 1 e 4; E (no ramo `wip/desempenho-parte1`), C, medição de C2,
  capturas «depois».
