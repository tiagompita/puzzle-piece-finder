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

Etiquetas: [V] verificado com evidência, [NT] não testado, [F] testado e falha / não reproduzido.

### Commits (um por bloco; o bloco 3 em dois: código e baseline; o bloco 5 em dois: `puzzle.json` e código)

| Bloco | Commit | Mensagem |
|---|---|---|
| 1 | `2316750` | tools.verify: esqueleto e passo 0 (ambiente, hooksPath, git, vigilância) |
| 2 | `1a3633b` | tools.verify: manifesto do golden (D1) e --refresh-golden |
| 3 | `c896a5a` | tools.verify: regras absolutas, métricas do golden e --congelar-baseline |
| 3 | `f7d8100` | golden: baseline e limiares congelados com tools.verify (antes de mexer em src/) |
| 4 | `f735274` | testes: regras absolutas do projeto (4.1 b/d, 4.3) e tools.verify |
| 5 | `7ea18a8` | alpes: exceção da simetria c32\|c33 passa para symmetry.excecoes do perfil |
| 5 | `1338c6f` | simetria: TWIN_EXCEPTIONS sai do código (symmetry.excecoes do perfil), teste 4.2 com lista por rever e provas |
| 6 | `511e87e` | hook commit-msg versionado (D4): recusa Co-Authored-By e Claude como autor |
| 7 | `c688ee6` | D2: medição da aresta fora do índice nos contornos manuais (sem correção) |
| — | `9455714` | docs: decisões D1–D5 e do planeamento da verificação determinística |

A baseline foi congelada (`f7d8100`) com `src/` igual a `813bdca` (`git diff --stat HEAD -- src` vazio antes do congelamento) [V]. Nenhum teste existente foi alterado [V]. Sem push (o gestor faz).

### Ativação do hook (cada clone / outro PC)

```
git config core.hooksPath tools/githooks
```

Ativado neste repositório [V]; o passo 0 de `tools.verify` falha (código 2) sem isto ou sem `tools/githooks/commit-msg` [V, `tests/test_verify.py::test_hooks_path_lido_do_git`]. Os commits a partir de `511e87e` já passaram pelo hook; um commit de teste com `Co-Authored-By: Claude <noreply@anthropic.com>` neste repositório foi recusado (saída 1, nada gravado) [V].

### 1. `python -m tools.verify` (passo 0)

- `tools/__init__.py`, `tools/verify/{__init__,__main__,ambiente,golden,invariantes,metricas,prova_simetria}.py` [V].
- Passo 0: Python do `.venv`, OpenCV igual ao fixado em `requirements.txt` (4.11.0), `core.hooksPath`, HEAD e `git status --porcelain` no início e no fim (falha se mudarem), vigilância `pieces/*.npz` e `overlays/*.jpg` contra `scans/*.json` do projeto real (só contagem), hashes do golden [V]. Com o Python do sistema: código 2 («Python fora do .venv», «OpenCV 4.10.0 != 4.11.0») [V].
- Códigos de saída: 2 ambiente, 3 golden, 6 vigilância/árvore, 4 regra absoluta, 5 baseline, 1 erro, 0 tudo certo. Saídas `metricas.json` e `comparacao.md` em `$PPF_SCRATCH/verify/<data>` (ou `%TEMP%/ppf_verify_out/verify/<data>`).
- Corre sempre sobre uma cópia leve (sem `crops`, `overlays`, `logs`, `reports`, `render/{gui,clean,fit,sheets}`) feita e apagada com `guarda.copytree`/`guarda.rmtree`; nenhuma pasta `ppf_verify_*` ficou no temporário [V]. ≈ 10 s por corrida [V].
- Pacote `tools`: os guiões continuam a correr como ficheiros. Antes e depois de `tools/__init__.py`: `tools/gui/screenshot.py --help`, `tools/diagnostico/gui/guarda.py` e `tests/test_guarda.py` (14 passed) com saída igual [V].
- **Exit de `python -m tools.verify` agora: 0** [V] (HEAD `9455714`, 10,0 s).

### 2. Golden (D1 = A)

`tests/golden/manifesto.json` (54 KB): 267 peças (218 de borda com a célula, 40 dos quadrados 1–10, 10 com contorno manual ativo; uma peça pode ter vários papéis), sha256 dos 31 ficheiros de scan, de `quadrados_17.json` e das 80 linhas de `overrides.jsonl` [V]. A verificação aceita linhas novas no `overrides.jsonl` e falha em linha alterada ou removida, scan alterado ou em falta, quadrados alterado [V, `tests/test_verify.py`]. `--refresh-golden --porque "..."` reescreve o manifesto e acrescenta uma entrada a `docs/decisoes.md` (a do manifesto inicial está lá) [V]. Os contornos derivados (`pieces/*.npz`) não entram no manifesto: saem do programa; o que deles se mede está na baseline.

### 3. O que fica em regras absolutas e o que fica na baseline

**Regras absolutas** (projeto vivo, cópia, sem baseline, 0 violações exigidas; código 4): `check_invariants` 0; mesma célula 0 em 699 células com peça; borda completa 218/218; F por célula 0 em 699 colocadas; grupos soltos 6 mostrados, 0 sobreposições; 4.1 (b) contorno guardado = o lido da linha, 10/10; 4.1 (d) índice fora da banda de 2 mm, 0 mm² em 10/10 [V].

**Baseline** (`tests/golden/baseline.json`, só peças do golden; código 5): por peça existência, estado (não descartada), célula das peças de borda (tem de ser a do manifesto), `cls` igual, cordas ±0,3 mm; contornos manuais: aresta fora do índice ≤ baseline + 0,05 mm²; simetria: nenhum par gémeo do golden novo acima de 1,75 mm (hoje 109 pares medidos, 2 acima, ambos na exceção c32|c33); suspeitas: nenhuma `(peça, grau)` nova numa peça do golden (hoje 4, as de P0289/P0292/P0492/P0496, exceção c32|c33). O total das Suspeitas (18) não entra. A baseline guarda o sha256 do manifesto: um manifesto novo exige voltar a congelar (`--congelar-baseline --porque`, com entrada em `decisoes.md`) [V]. Os limiares (`tests/golden/limiares.json`) foram escritos uma vez a partir de constantes com fonte; nenhuma opção os ajusta a partir de um resultado [V]. Informativos, sem comparação: `papel_coroa_pct`, RMS/`nn_max` por par.

### 4. Invariantes como testes

`tests/test_invariantes_projeto.py` (14 testes, ≈ 5 s): as 7 regras passam hoje, e cada uma tem um teste que a faz falhar numa perturbação em memória (tabuleiro ≠ log, duas peças na mesma célula, célula de borda vazia, classe errada, dois grupos na mesma célula, contorno guardado deslocado 1 px, índice longe da aresta) [V]. `tests/test_verify.py` (20 testes): manifesto, comparação com a baseline (7 regressões apanhadas, tolerâncias respeitadas), códigos de saída, vigilância, hooksPath, recusa da guarda [V].

### 5. Simetria 4.2: migração de `TWIN_EXCEPTIONS`

- `projects/alpes/puzzle.json`: `symmetry.excecoes = [{cols [32, 33], rows [[1, 3], [45, 47]], texto igual ao antigo}]` (commit próprio `7ea18a8`; nada mais em `projects/alpes`) [V].
- `src/consistency.py`: `TWIN_EXCEPTIONS` removido (constante, `__all__`, comentário, docstrings); `twin_exception` só lê o perfil [V]. `src/profile.py` já preservava `excecoes` ao ler e gravar (`symmetry` é copiado inteiro); passou a validar a forma (`_check_symmetry_exceptions`) e a documentá-la [V, testes de ida e volta e de recusa].
- **18 = 18** [V]: `consistency.evaluate(incluir_falsos=True)` dá 19 itens (18 sem falso alarme + P0343 falso alarme), iguais item a item, assinaturas incluídas, resumo e falsos alarmes iguais: antes (código antigo + perfil sem `excecoes`) e depois (código novo + perfil com `excecoes`), numa cópia e no projeto real só em leitura.
- `tests/test_simetria.py` (16 testes): «alpes» proibido no código de `src/` por AST (literais e nomes; comentários e docstrings ignorados), lista branca explícita de 7 entradas (6 módulos; ingest com `DEFAULT_PROJECT` e `DEFAULT_PROFILE`), cada uma com o motivo; uma entrada da lista que deixe de ser usada também falha. Teste 4.2 sobre a cópia (só se o perfil declarar simetria): 0 pares fora da exceção e da lista «por rever»; sem a lista falha exatamente nos 3 pares [V].
- **Testes que falharam antes** [V]: o `test_simetria.py` corrido num worktree em `f735274` (antes da migração) deu 9 failed, 2 passed (ida e volta do perfil e o detetor sintético), 3 skipped (sem `pieces/` no worktree): falharam o AST «alpes», `TWIN_EXCEPTIONS` fora de `consistency`, a exceção só do perfil, as 5 recusas de `excecoes` mal formadas e a exceção declarada no perfil. O AST sobre o `src/consistency.py` de `7ea18a8` dá `('src/consistency.py', 'TWIN_EXCEPTIONS', 81, 'alpes')` [V]. Os testes do bloco 4 passam hoje por desenho; a capacidade de falhar está nos testes de perturbação [V].
- Imagens de prova em `docs/diagnostico/verify/simetria/` (peça | gémea alinhada por `free_dist` | contornos sobrepostos, 20 px/mm), vistas [V]:

| Par | Células | cls | RMS | nn_max | Leitura das imagens |
|---|---|---|---|---|---|
| P0140 / P0499 | (4,32) / (44,33) | BBBT / BBTT | 2,10 mm | 4,74 mm | silhuetas limpas nas duas; um lado é B numa e T na outra |
| P0495 / P0938 | (44,32) / (4,33) | BBBT / BBTT | 2,14 mm | 4,37 mm | idem |
| P0500 / P1178 | (43,33) / (5,32) | BBBT / BTBT | 2,14 mm | 4,56 mm | idem |
| P0292 / P0496 (exceção) | (1,32) / (47,33) | FTTT / BTTF | 3,08 mm | 5,65 mm | referência da exceção declarada |
| P0119 / P0579 (controlo) | (2,48) / (46,17) | BTTT / BTTT | 0,17 mm | 0,24 mm | sobreposição quase perfeita |

  As 3 diferenças não parecem recortes maus (contornos limpos, sem mordidas) mas um lado com tipo trocado, como na exceção c32|c33 [V visual]; que esse lado é o do corte c32|c33 está [NT]. Isto pesa a favor da opção A da D3 (alargar a exceção às filas 4–5 e 43–44), a confirmar fisicamente pelo Tiago.
- Efeito lateral: `fit._profile_sha` é o sha1 de `puzzle.json`, por isso as caches do encaixe e da GUI ficam inválidas uma vez; o 1.º arranque do servidor depois de atualizar recalcula-as (resultado igual) [V pela leitura do código; tempo NT].

### 6. Hook `commit-msg` (D4 = A)

`tools/githooks/commit-msg` (sh, executável no índice, LF pelo `.gitattributes`). Recusa: qualquer trailer `Co-Authored-By`, `noreply@anthropic.com`, «Generated with/Gerado com … Claude», Claude num trailer de autoria (Signed-off-by, Autor, …), linha de assinatura só com Claude. Aceita caminhos com `.claude/` e `CLAUDE.md`, e menções a Claude na prosa. `tests/test_githook.py` (15 testes, repositório temporário, `git commit` real): 9 mensagens recusadas e 6 aceites (incluindo «docs: atualiza CLAUDE.md e .claude/agents/implementer.md» e «o gestor do Claude Code …») [V]. As linhas começadas por `#` não são retiradas: com `-m`/`-F` o git guarda-as na mensagem.

### 7. D2: origem da aresta fora do índice (sem correção)

`tools/diagnostico/verify/d2_aresta.py` (cópia; repete a derivação do servidor `strokes.resolver(..., normalizar_indice=True)` com os traços, solver e parâmetros gravados); números em `docs/diagnostico/verify/D2/d2.json`, imagens ampliadas 8× em `docs/diagnostico/verify/D2/P####.jpg` (vistas) [V].

| Peça | Fora (mm²) | px | prof. ≤ 1 px | 1–2 | 2–3 | > 3 | prof. máx (mm) | fora da influência dos traços (índice = automático ali) | ganho < 2 mm² descartado | resto |
|---|---|---|---|---|---|---|---|---|---|---|
| P0045 | 0,609 | 85 | 82 | 3 | 0 | 0 | 0,119 | 39 | 45 | 1 |
| P0071 | 1,505 | 210 | 151 | 53 | 5 | 1 | 0,271 | 210 | 0 | 0 |
| P0139 | 0,502 | 70 | 61 | 9 | 0 | 0 | 0,169 | 70 | 0 | 0 |
| P0198 | 1,591 | 222 | 160 | 57 | 5 | 0 | 0,237 | 158 | 64 | 0 |
| P0407 | 1,434 | 200 | 181 | 18 | 1 | 0 | 0,186 | 184 | 16 | 0 |
| P0620 | 1,039 | 145 | 101 | 34 | 10 | 0 | 0,237 | 134 | 2 | 9 |
| P0754 | 0,215 | 30 | 30 | 0 | 0 | 0 | 0,085 | 30 | 0 | 0 |
| P1064 | 0,889 | 124 | 110 | 14 | 0 | 0 | 0,169 | 114 | 10 | 0 |
| **total** | | **1086** | **876 (81 %)** | 188 | 21 | 1 | 0,271 | **939 (86 %)** | **137 (13 %)** | 10 (1 %) |

- A derivação repete-se exatamente: aresta e índice recalculados iguais aos gravados em 7/8 (P0407: a aresta difere 130 px, provável retoque de vértices no cliente; o índice é igual) [V]. P0315 e P0395 não têm nada fora [V].
- **Não é rasterização nem convenção de píxel:** aresta e índice são cadeias de píxeis preenchidas da mesma forma e a aresta recalculada coincide bit a bit. **Não é suavização do polígono** nem **recorte da banda** (`limitar_indice` mantém sempre a aresta inteira e não foi aplicado a estas 8) [V].
- **Origem:** (1) 86 %: fora da região de influência dos traços o índice é, por convenção, o contorno automático bit a bit (`strokes.normalizar`), e ali a aresta (GrabCut sem traços perto) fica 1–3 px para fora do automático, sobre a orla clara da peça; 1085 de 1086 píxeis estão fora do contorno automático substituído; (2) 13 %: ganhos da aresta com menos de `GANHO_MIN_MM2` = 2 mm² são descartados do índice; (3) 1 %: limpeza 0,3 mm / bordo da influência. Profundidade máxima 0,27 mm; 81 % dos píxeis a 1 px [V].
- Pela regra D5 (o contorno manual é a verdade), as duas regras da derivação contradizem a aresta: o erro é do código (`strokes.normalizar`), não da aresta.

**Regra para o teste 4.1 (c): opções para o Tiago**

| Opção | Regra do teste | Hoje | O que implica | Recomendação |
|---|---|---|---|---|
| A | aresta ⊆ índice, exato (0 px) | 8/10 falham | corrigir a derivação: índice = derivado ∪ aresta (em `strokes.normalizar`, e ao ler em `overrides.index_contour_from` para as linhas já gravadas); os 8 índices crescem 0,2–1,6 mm² (orla de 1–3 px); re-registo com evento `piece_resegmented`; baseline das 8 peças a voltar a congelar | **Sim**: é a regra D5 e a correção é pequena e local |
| A′ | aresta ⊆ índice com tolerância de 1 px de profundidade | 7/10 falham (só P0754 passa) | a mesma correção; a tolerância só esconderia a convenção «automático» | não: com a correção A não é precisa |
| A″ | tolerância de 3 px (0,25 mm) | 1/10 falha (P0071, 1 píxel a 0,27 mm) | aceita a contradição medida | não: limiar escolhido para passar |
| B | sem teste de contenção (só b e d) | passa | a contradição fica sem guarda | não |
| C | «não piora» contra a baseline (o que está hoje em `tools.verify`) | passa | provisório, até decidir | manter só até A |

### 8. Recontagem das esperas fixas nos testes (nenhuma alterada)

| Contagem | Comando | Resultado |
|---|---|---|
| texto (inclui 1 menção numa docstring) | `grep -rnoE "sleep\(\|wait_for_timeout\(" tests --include=*.py \| wc -l` e o mesmo com `-rlE` para os ficheiros | **175 em 38 ficheiros** [V], igual à contagem independente |
| só `time.sleep(` e `wait_for_timeout(` | `grep -rnoE "time\.sleep\(\|wait_for_timeout\(" tests --include=*.py` | 174 em 38 [V] (75 `time.sleep(`, 99 `wait_for_timeout(`) |
| chamadas reais (AST: atributo ou nome `sleep` / `wait_for_timeout`) | guião `ast.walk` sobre `tests/**/*.py` | **172 chamadas em 38 ficheiros** [V]: 97 `pg.wait_for_timeout`, 1 outra `wait_for_timeout`, 74 `time.sleep`; 126 delas em 25 ficheiros `test_gui*` |

Os «206 em 70 ficheiros» do levantamento não se reproduzem [F]: nenhuma combinação de pastas os dá (`tests`+`tools/gui` 214 em 51, `tests`+`tools/diagnostico` 240 em 54, `tests`+`tools` 279 em 67).

### Suite

`.venv/Scripts/python.exe -m pytest tests/`, uma corrida completa no fim (HEAD `9455714`): **991 passed, 1 skipped, 0 failed** em 16 min 05 s [V]. Sem falhas intermitentes nesta corrida. Ruído antigo no stderr (não falha): «Logging error … I/O operation on closed file» de fios do ranking dos buracos que escrevem no registo depois de o pytest fechar o stream.

### Vigilância

Início: `pieces` 39, `overlays` 39, `scans/*.json` 39, `git status` limpo. A meio (antes da suite): 39/39/39. Fim: 39/39/39, `git status` limpo antes deste commit [V]. `graphify update .` corrido (o `graphify-out/` está no `.gitignore`).

### Decisões pendentes (Tiago)

1. **4.1 (c)** (tabela da secção 7): recomendo A (índice ⊇ aresta, corrigido em `strokes.normalizar` e na leitura).
2. **D3**, os 3 pares c32|c33 das filas 4–5 / 43–44: ver as imagens em `docs/diagnostico/verify/simetria/`; as imagens apontam para A (alargar `symmetry.excecoes`), depois de confirmação física.
3. Se a simetria 4.2 (hoje só pytest) deve também ser uma regra absoluta de `tools.verify` (a decisão 2 do planeamento não a listou; não a acrescentei).
4. Passos 1–3 (segmentação, classificação, matching sobre o golden), lint de convenções e prova da GUI: próxima ronda (fora do âmbito desta).
