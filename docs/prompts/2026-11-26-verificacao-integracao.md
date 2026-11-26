# 2026-11-26: verificação ligada ao fluxo de trabalho (regra no CLAUDE.md, skills, pre-commit, lint)

## Porquê

O `python -m tools.verify` já existe (implementação 1, `8b0d896`; regra 4.1 (c) = A, `cac1865`), mas nada obriga a corrê-lo. Esta ronda liga-o ao fluxo:
- regra no CLAUDE.md;
- skills;
- hook pre-commit.

Acrescenta também o lint barato:
- esperas fixas novas;
- regra da gémea escrita à mão;
- módulos novos sem `__all__` ou indentados a espaços.

Não mexe na segmentação.

## Decisões

- Tiago, 2026-11-26: fica aprovada a decisão 3 da ronda anterior: o `tools.verify` simula o arranque do servidor na cópia antes de verificar as regras. Regista-se em `docs/decisoes.md`.
- Na lista branca das esperas fixas entram as 175 atuais, contadas por ficheiro.
- A decisão 2 (cantos chanfrados, P0754/P1064) continua em aberto e fica fora do âmbito.

## Prompt (verbatim)

> Agente: implementer. Skills: cv-visual-verification, piece-fit-matching.
>
> Antes de grep ou leitura de ficheiros, consulta o grafo do Graphify. No fim, corre `graphify update .`.
>
> OBJETIVO
> O tools.verify existe mas nada obriga a corrê-lo. Esta ronda liga-o ao fluxo de trabalho e acrescenta o lint barato. Não mexe na segmentação.
>
> 1. CLAUDE.md: regra curta. `python -m tools.verify` corre antes de cada commit que toque src/, tools/verify/, tests/golden/ ou projects/; exit ≠ 0 = parar e reportar, nunca congelar a baseline para passar. Onde uma regra em prosa já é verificada pelo comando ou por um teste, troca o texto por uma linha a apontar para essa verificação (não apagues a regra sem ela estar coberta).
> 2. Skills cv-visual-verification e piece-fit-matching: secção «Verificação» a apontar para tools.verify e para os testes que cobrem cada regra; o que continua a ser juízo visual fica dito como tal.
> 3. Hook pre-commit versionado em tools/githooks/: corre tools.verify só se os ficheiros em stage tocarem os caminhos do ponto 1. Testa que bloqueia e que deixa passar.
> 4. Lint (teste pytest, lista branca para o legado): falha em esperas fixas NOVAS em tests/ (lista branca = as 175 atuais, por ficheiro e contagem); `48 - l`/`65 - c` fora de profile.py/puzzle.json/testes; módulo novo em src/ sem `__all__` ou indentado a espaços. Corrige `tools/diagnostico/gemeos/ereal2.py` para usar `profile.twin()`. Cada regra do lint falha primeiro num caso sintético.
> 5. Decisão 3 da ronda anterior (arranque simulado no tools.verify): aprovada; regista-a em docs/decisoes.md.
>
> REGRAS
> - Não alteres testes existentes sem OK; lista os novos no commit.
> - Suite completa com .venv no fim e tools.verify com exit 0; [V]/[NT]/[F].
> - Um commit por bloco, sem Claude como co-author; push no fim.
> - Relatório palavra por palavra no «Resultado» de docs/prompts/2026-11-26-verificacao-integracao.md.

## Resultado

**Commits** (sem push; o gestor faz o push):
- `df2cccb`: CLAUDE.md: tools.verify antes de commits em src/, tools/verify/, tests/golden/, projects/; regras cobertas apontam para a verificação (inclui este ficheiro do prompt)
- `649ca05`: skills: secção «Verificação» em cv-visual-verification e piece-fit-matching
- `27c01c5`: pre-commit versionado: tools.verify só quando o stage toca src/, tools/verify/, tests/golden/ ou projects/
- `c4538fa`: lint: esperas fixas novas, regra da gémea à mão, módulos de src/ sem __all__ ou a espaços; ereal2 usa profile.twin()
- `1d733e6`: decisoes: arranque simulado na cópia no tools.verify aprovado (decisão 3 da ronda anterior)
- mais o commit deste «Resultado».

**Ficheiros:**
- `CLAUDE.md`, `.claude/skills/cv-visual-verification/SKILL.md`, `.claude/skills/piece-fit-matching/SKILL.md`;
- novos: `tools/githooks/pre-commit` (LF, 100755), `tests/test_githook_precommit.py`, `tests/test_lint.py`;
- guiões: `tools/diagnostico/gemeos/ereal2.py`, `tools/diagnostico/fit/grupos_juncoes.py`, `tools/diagnostico/reports/p0395_r0036/identidade.py`;
- `docs/decisoes.md`, `docs/prompts/2026-11-26-verificacao-integracao.md`.

**Bloco 1, o que cada regra em prosa passou a apontar.** O texto de cada regra fica; só se acrescentou o apontador ou se encurtou a explicação.
- Regra nova em «Conventions»: o verify corre antes de cada commit em `src/`, `tools/verify/`, `tests/golden/` ou `projects/`. Exit ≠ 0 = parar e reportar; nunca `--no-verify`, nunca `--congelar-baseline` ou `--refresh-golden` para passar. Aponta para o hook `tools/githooks/pre-commit` e para `tests/test_githook_precommit.py`.
- Borda completa 218/218: regra `borda_completa` do `tools.verify` e `tests/test_invariantes_projeto.py::test_borda_completa`.
- Generalization: `tests/test_simetria.py::test_alpes_nao_aparece_no_codigo_de_src` e `tests/test_lint.py::test_regra_gemea_so_no_perfil`. Fica dito que os outros números de grelha, célula, fundo e dpi escritos à mão não são verificados.
- Vigilância de ficheiros apagados: passo 0 do `tools.verify` (`vigilancia`, exit 6) e `tests/test_verify.py::test_vigilancia_conta_contra_scans`; a guarda está em `tests/test_guarda.py`. Que um guião novo use o `guarda.py` continua prosa, porque não é verificado.
- Contorno manual = verdade de terreno: regras `manual_indice_da_linha`, `manual_aresta_no_indice` e `manual_indice_na_banda`, com `tests/test_invariantes_projeto.py::test_manual_indice_igual_ao_da_linha`, `::test_manual_aresta_dentro_do_indice` e `::test_manual_indice_na_banda`. O resto (não rejeitar, não alisar, …) fica dito como juízo de revisão.
- Tabs e `__all__` em `src/`: `tests/test_lint.py::test_modulos_src_com_tabs_e_all`.
- Esperas fixas (regra nova, curta): `tests/test_lint.py::test_sem_esperas_fixas_novas_em_tests`.
- Sem Co-Authored-By e sem Claude como autor: hook `commit-msg` e `tests/test_githook.py::test_recusa`. O `core.hooksPath` é verificado pelo passo 0 (`ambiente`). «Mensagens em português» continua prosa.
- Ficou intacta, por não estar coberta: «suite sempre com `.venv`». O verify só verifica o seu próprio Python, não o da suite.

**Bloco 2:** as duas skills têm uma secção «Verificação» com:
- os códigos de saída do verify;
- os testes de cada regra;
- uma lista explícita do que continua a ser juízo visual.

Corrigi também um nome de API desatualizado na piece-fit-matching: `perfil.simetria(l, c)` passou a `profile.twin(l, c)`.

**Bloco 3, hook pre-commit:**
- Caminhos lidos de `git -c core.quotePath=false diff --cached --name-only --no-renames`: um rename conta pela origem e uma remoção também conta. Sem caminho relevante, sai logo.
- Python: `.venv/Scripts/python.exe`, senão `.venv/bin/python`, senão `python`, senão `python3`.
- O verify lê a árvore de trabalho, não o índice.
- [V] num repositório temporário com `git commit` real e um `tools.verify` falso, com os 18 testes de `tests/test_githook_precommit.py`:
  - bloqueia com exit 4, 3 ou 2 nos 4 caminhos relevantes e num commit misto;
  - deixa passar com exit 0;
  - não corre o verify em 8 caminhos não relevantes, incluindo `srcx/` e `docs/src/`;
  - o ficheiro tem LF e modo 100755.
- [NT] num commit real deste repositório: nenhum dos meus commits tocou os caminhos, por isso o hook nunca correu o verify aqui.
- Para ativar noutro PC: `git config core.hooksPath tools/githooks`.

**Bloco 4, lint** (`tests/test_lint.py`, 7 testes):
- **Esperas fixas:**
  - Definição escolhida: chamadas (AST) cujo nome é `sleep` ou `wait_for_timeout`. São 172 chamadas em 38 ficheiros.
  - A lista branca é exata por ficheiro: acima falha; abaixo também, e pede para baixar a lista.
  - As 175 do grep têm 3 a mais que não são chamadas neste código: um comentário (`tests/test_server.py:1182`), uma docstring (`tests/test_server_queue.py:138`) e código dentro de uma string do `pytester` (`tests/test_net_log.py:45`).
- **Regra da gémea:**
  - Apanha `48 - x`/`65 - x` e `<nome de grelha> + 1 - x` em todos os `.py` versionados, fora de `src/profile.py` e de `tests/`. O 48 e o 65 vêm de `projects/alpes/puzzle.json` (linhas + 1, colunas + 1).
  - Corrigidos para `PuzzleProfile.twin`: `ereal2.twin_cell`, a célula B2 da linha 335 de `ereal2`, `grupos_juncoes.twin_tl_of` e `identidade.twin`.
  - Dão as mesmas células [V]: as 3008 células em escalar e em `np.mgrid`, com o mesmo dtype (fica no teste `test_ereal2_twin_cell_e_o_do_perfil`), e 69 750 retângulos em `grupos_juncoes`.
  - Não corri o guião `ereal2` inteiro [NT]: precisa dos scans e de `PPF_SCRATCH`. A comparação acima substitui essa corrida.
  - Na lista branca, com motivo:
    - as mudanças de referencial dos cantos BD/BE em `ereal.py` e `ereal2.py`, que não são a regra da gémea;
    - o espelho da traseira em `seccao.py`;
    - a GT das folhas B em `seccao.py`. Essa sim é a regra da gémea à mão, num guião congelado sem perfil; não a corrigi.
- **Módulos de `src/`:** falha sem `__all__` ou com INDENT a espaços. Lista branca: `src/__init__.py` (vazio), `src/gui.py` e `src/main.py` (legado a espaços).
- **Cada regra falha num caso sintético** [V]:
  - os testes `*_sintetico_falha`;
  - na árvore real, com ficheiros injetados de propósito e depois apagados, as 3 regras falharam:
    - `[('tests/test_zz_demo_lint.py', 1, 0, [4])]`;
    - `[('tools/zz_demo_lint.py', '48 - l', 1, 0, [2]), ('tools/zz_demo_lint.py', '65 - c', 1, 0, [2])]`;
    - `[('src/zz_demo_lint.py', ['espacos', 'sem_all'], [])]`;
  - as versões antigas (HEAD) de `ereal2`, `grupos_juncoes` e `identidade` davam 7 violações.

**Bloco 5:** entrada em `docs/decisoes.md` (2026-11-26, arranque simulado aprovado).

**Verificação final:**
- Suite completa, `.venv/Scripts/python.exe -m pytest tests/ -q -p no:cacheprovider`, numa corrida só: 1025 passed, 1 skipped, 16 min 57 s, exit 0 [V].
- `python -m tools.verify` (com o `.venv`): código 0 em 22,0 s [V].
- `graphify update .` corrido.
- Vigilância de pieces/overlays/scans: 39/39/39 no início e no fim [V].
- Não escrevi em `projects/alpes`. Não alterei nenhum teste existente.

**Decisões pendentes:**
1. Esperas fixas: a definição é a das chamadas (AST), 172, e não as 175 do grep (diferença explicada acima). Se quiseres a contagem textual, troca-se a definição.
2. `tools/diagnostico/gemeos/seccao.py`, a GT das folhas B (`GRID[0] + 1 - ca`): ficou na lista branca em vez de corrigida (guião de 2026-10-30, sem perfil).
3. O lint de esperas não vê código dentro de strings (o caso do `pytester` em `test_net_log.py`).
4. O pre-commit verifica a árvore de trabalho; com um stage parcial verifica o que está no disco, não o que vai no commit.
