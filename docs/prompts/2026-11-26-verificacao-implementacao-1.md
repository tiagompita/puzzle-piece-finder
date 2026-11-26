# 2026-11-26 — verificação determinística, implementação 1

## Porquê

A ronda `2026-11-26-verificacao-deterministica.md` (`63b6066`) fez o levantamento e o plano: `python -m tools.verify`, golden por manifesto de hashes, invariantes como testes, hook de commit. Esta ronda implementa os blocos 1–8: o esqueleto do comando com o passo 0, o manifesto, a baseline congelada antes de mexer em `src/`, os invariantes que passam hoje, a migração da exceção de simetria para o perfil, o hook `commit-msg`, a medição D2 e a recontagem das esperas fixas.

## Decisões

- Decisões do Tiago sobre o levantamento: D1 = A (manifesto de hashes sobre os scans já no git); D2 = C (medir a origem primeiro); D3 = C (lista «por rever»); D4 = A (`commit-msg` versionado); D5 = B (manter `edges.py` e `gui.py`, em lista branca).
- No planeamento (Tiago, 2026-11-26):
  1. O bloco 5 pode alterar **só** `projects/alpes/puzzle.json` (acrescentar `symmetry.excecoes`), num commit próprio e reversível. Nada mais em `projects/alpes`.
  2. **Baseline e projeto vivo:** `projects/alpes` muda a cada digitalização ou colocação, por isso nenhuma baseline compara contagens do projeto inteiro.
     - **Regras absolutas, sem baseline, 0 violações exigidas** (sobre a cópia do projeto vivo): `check_invariants`, mesma célula, borda completa, F por célula, grupos sobrepostos, 4.1 (b) e (d).
     - **A baseline só contém métricas das peças do golden** (manifesto).
     - **Suspeitas:** falha só se surgir uma suspeita nova numa peça do golden; o total de itens não entra na baseline.
     - O relatório explica o que fica em cada grupo.
  3. **Passo 0:** falha se `git config core.hooksPath` não for `tools/githooks`; o relatório traz o comando de ativação, para o outro PC.
  4. **`TWIN_EXCEPTIONS`:** sai de `src/consistency.py` (com `__all__` e o comentário atualizados), e há um teste que falha se «alpes» aparecer em `src/`.
     - Âmbito: só código, com lista branca. O teste analisa o AST e falha com «alpes» em literais e nomes do código executável; ignora comentários e docstrings.
     - Os 6 defaults de `--project` (artreg, fit, ingest `DEFAULT_PROJECT`/`DEFAULT_PROFILE`, render, reports, server) ficam numa lista branca explícita no teste, cada um com o motivo.

## Prompt verbatim

Agente: implementer. Skills: cv-visual-verification, piece-fit-matching.

Antes de grep ou leitura de ficheiros, consulta o grafo do Graphify. No fim, corre `graphify update .`.

CONTEXTO
Implementação da ronda docs/prompts/2026-11-26-verificacao-deterministica.md (lê o «Resultado» inteiro, incluindo o anexo A). Decisões do Tiago:
D1 = A (manifesto de hashes sobre os scans já no git)
D2 = C (medir a origem primeiro)
D3 = C (lista «por rever»)
D4 = A (commit-msg versionado)
D5 = B (manter edges.py e gui.py; lista branca)
Regista estas decisões em docs/decisoes.md.

ÂMBITO DESTA RONDA (só isto, por esta ordem, um commit por bloco)
1. Esqueleto de `python -m tools.verify` com o passo 0: ambiente (.venv, versão do OpenCV), HEAD e git status no início e no fim, hashes do golden, vigilância (pieces/overlays == n.º de scans/*.json, não «39» fixo).
2. `tests/golden/manifesto.json` (D1): sha256 dos ficheiros de scan referidos, de `quadrados_17.json` e de cada linha de `overrides.jsonl` (só acrescentar: as linhas existentes têm de ficar iguais byte a byte). Atualizar o manifesto só com `--refresh-golden --porque "..."`, que escreve uma entrada em docs/decisoes.md.
3. CONGELAR A BASELINE com o próprio `tools.verify --congelar-baseline`, ANTES de qualquer outra alteração ao código de `src/`. Commit só com `baseline.json` e `limiares.json`. Nenhuma opção do comando ajusta limiares a partir de um resultado.
4. Invariantes que passam hoje como testes pytest rápidos: 4.1 (b) e (d); 4.3 completo.
5. Simetria 4.2: migrar `TWIN_EXCEPTIONS` para `symmetry.excecoes` no `puzzle.json` (sem mudar o comportamento: prova-o com o mesmo resultado de `consistency.evaluate`, 18 itens, antes e depois). O teste corre só se o perfil declarar simetria e aceita a lista «por_rever» (D3) com os 3 pares P0140/P0499, P0495/P0938, P0500/P1178. Gera, para cada um, uma imagem de prova lado a lado (peça e gémeo rodado 180°, contornos sobrepostos), para o Tiago avaliar.
6. Hook `commit-msg` em `tools/githooks/` (D4), ativado com `core.hooksPath`: recusa `Co-Authored-By` e menções a Claude. Testa que recusa e que aceita.
7. Medição D2 (sem corrigir nada): para os 8 contornos manuais com aresta fora do índice, explica de onde vem a área fora (rasterização/convenção de pixel, suavização, recorte da banda ou perda real de aresta), com números por peça e uma imagem de prova ampliada das zonas fora. Termina com a regra proposta para o teste 4.1 (c), como opções numa tabela para o Tiago decidir. Lembra-te: o contorno manual é a verdade; se a derivação o contradiz, o erro é do código.
8. Reconta as esperas fixas nos testes (o relatório diz 206 em 70 ficheiros; uma contagem independente dá 175 em 38). Indica o comando usado. Não alteres nenhuma espera.

FORA DO ÂMBITO
Passos 1–3 de segmentação/classificação/matching, lint de convenções, prova da GUI e remoção de legado.

REGRAS
- Trabalha numa cópia para medições; nunca escrevas em projects/alpes.
- Um teste que deve falhar falha primeiro; não alteres testes existentes sem OK do Tiago (lista os alterados no commit).
- Suite completa com .venv no fim; cada afirmação com [V]/[NT]/[F].
- Paragem: se a baseline não puder ser congelada antes de mexer em src/, ou se a migração da exceção mudar o resultado de `consistency.evaluate`, para e reporta.
- Commits sem Claude como co-author. Push no fim.
- Relatório final, palavra por palavra, no «Resultado» de docs/prompts/2026-11-26-verificacao-implementacao-1.md.

## Resultado

(por preencher)
