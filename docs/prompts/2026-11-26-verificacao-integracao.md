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

(por preencher)
