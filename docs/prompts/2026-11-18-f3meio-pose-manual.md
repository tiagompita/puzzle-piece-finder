# 2026-11-18 — F3½: a pose manual nunca esconde a orientação

## Porquê
`consistency.evaluate(incluir_pose_manual=False)` (omissão do CLI, do painel de Suspeitas e do «Suspeitas novas») deixava de avaliar a orientação de qualquer peça com pose manual. Foi isto que escondeu P0833 de 2026-11-07 a 2026-11-16: uma pose manual só de translação tirou-a das suspeitas e a âncora tinha a rotação errada. Pré-requisito do B1 da F4 (Q11 a).

## Decisões
- Decisão do Tiago, depois da medição do orientador: uma pose manual **nunca** esconde as suspeitas de orientação; a peça é avaliada com o `k` da pose manual. Substitui a regra «< 45°» da Q11 a, que não teria apanhado P0833 (2,9° de diferença).
- `incluir_pose_manual` sai; ficam `n_pose_manual`, `pose_manual: True` e a pose manual na assinatura do falso alarme.
- Fora do âmbito: o limite de ±15° da pose manual (F5) e o «Rodar a peça 90°».
- Plano: `C:\Users\tiago\.claude\plans\agente-implementer-skills-graphify-logical-summit.md` (fora do repositório; resumo em `docs/decisoes.md`, 2026-11-18, F3½).

## Prompt verbatim
Projeto: d:\DEKSTOP\puzzle_piece_finder (Windows; Git Bash e PowerShell). Lê primeiro o CLAUDE.md do projeto: commits em português, SEM linha Co-Authored-By, sem push; suite SEMPRE com `.venv/Scripts/python.exe -m pytest tests/`. És o único agente nesta árvore de trabalho. Skills a seguir: piece-fit-matching e systematic-debugging (se tiveres a ferramenta Skill, carrega-as; senão segue as regras deste prompt).

Regra do grafo: há graphify-out/graph.json. Antes do primeiro grep/leitura para uma pergunta sobre o código, corre `graphify query "<pergunta>"`; lê ficheiros só nas linhas localizadas. Depois de mexer em código, `graphify update .`.

EXECUTA o plano aprovado em C:\Users\tiago\.claude\plans\agente-implementer-skills-graphify-logical-summit.md (lê-o inteiro primeiro; é a especificação). Base: HEAD d43493d.

Resumo do que já foi medido pelo orientador (só leitura, nada gravado), para não repetires a investigação:
- src/consistency.py evaluate(): a linha `if grau is None or (pid in with_pm and not incluir_pose_manual): continue` (≈ linha 463) esconde as suspeitas de orientação de qualquer peça com pose manual. O k0 dessas peças já vem de _k_of → render.register_piece(manual=True) → render._manual_entry (corner.k mais perto do θ manual).
- Reprodução EM MEMÓRIA de P0833 (G0068 com anchor rot 180, o estado anterior a 2026-11-16): sem pose manual → melhor_rotacao −90; pose manual +3° → escondida hoje; com incluir_pose_manual=True → melhor_rotacao −90; +90° → impossivel.
- projects/alpes hoje: 6 peças com pose manual (P0133 Δ4,1°, P0135 0°, P0147 90,1°, P0177 0°, P0833 2,9°, P1023 0°); Suspeitas 18 com a regra de hoje e 18 com incluir_pose_manual=True (nenhuma nova). P0147 rodada 90° à mão; as vizinhas concordam com a pose manual.
- Chamadores de incluir_pose_manual: src/server.py:3059 (pose/avaliar, passa True) e tests/test_consistency.py (test_manual_pose_out_of_orientation_counts_unless_asked, linhas ≈ 289–311). tests/test_server.py ≈ linha 923 afirma `n_impossivel == 0` com pose manual: lê o teste para ver se a peça está rodada antes de mudar.

DECISÃO DO TIAGO: uma pose manual NUNCA esconde as suspeitas de orientação (a peça é graduada com o k da pose manual). O parâmetro incluir_pose_manual deixa de existir. n_pose_manual no summary, it["pose_manual"]=True e a pose manual na assinatura do falso alarme ficam.

Ordem:
1. Testes novos primeiro (os 5 do plano) em tests/test_consistency.py; corre-os e guarda a saída de antes (quantos falham). Atualiza os testes existentes que fixavam o erro (só esses), anotando cada um para a mensagem do commit.
2. Mudança em src/consistency.py (código + docstrings) e src/server.py:3059.
3. Guião tools/diagnostico/reports/f3meio_pose_manual.py que COPIA projects/alpes para o scratchpad C:\Users\tiago\AppData\Local\Temp\claude\011f846714d7d8db\49717873-39bc-41e4-8bf3-7df0c0bb8677\scratchpad (nunca escrever em projects/alpes) e mede (a) Suspeitas antes (com o código de d43493d, por exemplo via `git stash`/`git worktree` ou correndo a avaliação antiga com incluir_pose_manual=False antes da mudança e guardando o JSON) e depois; (b) P0833 na cópia: --unanchor G0068 + --anchor G0068 8 2 --rot 180 + set_pose +3° → sinalizada; com a âncora certa (rot 90): +5° não, +90° sim; (c) as 6 peças com pose manual: θ manual, θ automático, Δθ circular, marcando as com Δθ ≥ 45° (P0147) como «rotação automática errada, tapada pela pose manual».
   PARAGEM: se (a) tiver alguma suspeita nova (peça, grau) que não existia antes, NÃO faças commit: devolve a lista (peça, célula, θ manual, θ automático, grau, rot_alt_deg) e para.
4. Documentos (conforme o plano): docs/decisoes.md (entrada nova 2026-11-18 «F3½: a pose manual nunca esconde a orientação», com medição e decisão; nota nas entradas que ela substitui: item 2 do backlog de 2026-11-16 e a Q11 a da entrada F4 de 2026-11-18; e no backlog a linha EXATA: «P0147: rotação automática errada (90°), tapada pela pose manual. Se a pose manual for limpa (re-segmentação, rebuild_stale), a rotação errada volta. Corrigir a origem (θ do log ou da âncora) numa ronda futura.»), docs/HANDOFF.md (estado: F3½ feita, a seguir o B1 da F4), docs/gui/redesenho/F4_PLANO.md e docs/gui/redesenho/ESPEC.md §7 (onde diz «> 45°» / «mais de 45°» passa a «nunca esconde»), CLAUDE.md (linha do src/consistency.py: a frase sobre incluir_pose_manual=False passa à regra nova), docs/prompts/ (ficheiro do prompt conforme docs/prompts/README.md).
5. Suite completa `.venv/Scripts/python.exe -m pytest tests/` (inclui slow e Playwright) e `graphify update .`. Não incluas no commit ficheiros de graphify-out/ se não estiverem já versionados com alterações esperadas; usa `git add` por caminho, não `-A`.
6. Commit: «consistência: pose manual não esconde rotação errada» (corpo: testes existentes mudados e porquê), sem co-autor, sem push.

Relatório final curto: ficheiros mudados; testes novos que falhavam antes (n); resultados (a)/(b)/(c) com números [V]; suite (passed/skipped/failed); hash do commit (ou PARAGEM com a lista).

## Resultado
- `src/consistency.py`: `evaluate` sem `incluir_pose_manual`; uma peça com pose manual é avaliada com o `k` dela; docstrings. `src/server.py` (`pose/avaliar`) deixa de passar o parâmetro.
- Testes (`tests/test_consistency.py`): 5 novos (`test_f3meio_*`); antes da mudança falhavam 3 (os 2 que afirmam «nada» já passavam). Mudado: `test_manual_pose_out_of_orientation_counts_unless_asked` → `test_manual_pose_is_graded_with_its_own_k` (afirmava o erro). `tests/test_server.py::test_pose_evaluate_set_and_reset` não mudou: a pose manual do teste (θ − 90°) corrige a rotação, `n_impossivel == 0` continua certo.
- Medição numa cópia (`tools/diagnostico/reports/f3meio_pose_manual.py`) [V]: (a) 18 = 18, nenhuma suspeita nova; (b) P0833 rot 180 + 3° → `melhor_rotacao` −90°; rot 90 + 5° nada; rot 90 + 90° `melhor_rotacao` −90°; (c) só P0147 com Δθ ≥ 45° (90,1°), para o backlog.
- Documentos: `docs/decisoes.md`, `docs/HANDOFF.md`, `docs/gui/redesenho/F4_PLANO.md`, `docs/gui/redesenho/ESPEC.md`, `CLAUDE.md`.
- Suite completa: 733 passed, 1 skipped, 0 failed (13 min 09 s) [V].
- Commit: ver `git log` («consistência: pose manual não esconde rotação errada»).
