# 2026-11-26 — verificação determinística (levantamento e plano)

## Porquê

A qualidade do projeto depende de regras escritas em prosa: skills, `docs/prompts/*.md`, `docs/revisao.md`, `docs/decisoes.md` e os prompts de cada ronda. O Tiago quer passar para verificações determinísticas tudo o que der (testes, invariantes, scripts com prova visual e números), para que um erro repetido faça falhar um comando. Esta ronda é só levantamento e plano: não altera código nem testes.

## Decisões

- Ronda só de levantamento: sem código nem testes; medições numa cópia, nunca em `projects/alpes`.
- Ajustes do Tiago ao aprovar o plano (2026-11-26):
  1. A baseline pode ficar [NT] nesta ronda, mas o plano diz explicitamente que o 1.º passo da implementação é congelar a baseline com o próprio `tools.verify`, antes de qualquer alteração ao código, e nunca com scripts provisórios.
  2. O código dos scripts de medição do ponto 4 vai num anexo do «Resultado», para a implementação o reaproveitar.
  3. No ponto 1, cada regra «não automatizável» leva o motivo numa frase; «é difícil» não conta como motivo.
  4. Push autorizado, só do commit desta ronda.

## Prompt verbatim

Agente: helper. Skills: cv-visual-verification, piece-fit-matching.

Antes de grep ou leitura de ficheiros, consulta o grafo do Graphify. No fim, corre `graphify update .`.

OBJETIVO
Hoje a qualidade do projeto depende de regras escritas em prosa (skills, docs/prompts/*.md, docs/revisao.md, prompts de cada ronda). Quero passar para verificações determinísticas tudo o que der: testes, invariantes, scripts com prova visual e números. Assim, um erro repetido passa a fazer falhar um comando, em vez de depender de alguém se lembrar. Esta ronda é SÓ levantamento e plano. Não alteres código nem testes.

1. LEVANTAMENTO DE REGRAS E CORREÇÕES REPETIDAS
Lê as skills do projeto, docs/revisao.md, docs/prompts/*.md e o histórico de commits. Faz uma tabela com:
regra/correção | onde aparece | n.º de vezes | dá para impor automaticamente? (teste / invariante / script / lint / não) | como.
O que só pode ficar em prosa (decisões de juízo) fica marcado como tal, com o motivo.

2. CONJUNTO DE REFERÊNCIA ("golden")
Propõe um conjunto fixo, versionado em git, com dados cuja verdade já é conhecida:
- peças da borda (completa, incluindo a (1,29));
- os 10 quadrados 2×2 de peças soltas confirmados fisicamente a 11 nov 2026;
- os contornos manuais (são a verdade absoluta da silhueta: o programa nunca os altera nem os contradiz).
Indica que ficheiros entram, o tamanho e como garantir que estes dados nunca mudam sem querer (por exemplo, hashes).

3. COMANDO ÚNICO DE VERIFICAÇÃO
Desenha um comando (por exemplo, `python -m tools.verify`) que corre a segmentação, a classificação de bordas e o matching sobre o conjunto de referência e:
- escreve métricas num ficheiro (JSON) e gera imagens de prova numa pasta;
- compara com uma baseline medida AGORA, antes de qualquer melhoria; os limiares ficam fixados e nunca se ajustam para passar;
- falha com código de saída ≠ 0 se alguma métrica descer.
Indica que métricas propões e porquê.

4. INVARIANTES COMO TESTES
Propõe testes para, pelo menos:
- contorno manual inalterado (hash) e contorno gravado só com a peça, sem sombra;
- simetria de recortes em pares do puzzle "Os Alpes": (l,c) ↔ (48−l, 65−c) rodada 180°. Esta propriedade é do puzzle, não do programa: tem de viver na configuração do projeto e ser opcional para outros puzzles;
- coerência do tabuleiro: duas peças nunca na mesma posição, peças de grupos soltos nunca sobrepostas.
Para cada teste, diz se passaria hoje ou não (mede, não adivinhes).

5. PROVA DA GUI
Propõe um script que abre a GUI com dados de teste e guarda capturas a 1366×768 e 390×844 dos ecrãs principais, para a revisão ser feita sobre imagens e não sobre descrições.

6. CÓDIGO QUE ENSINA MAUS PADRÕES
Lista workarounds, código morto, parâmetros "mágicos" afinados à mão e comentários que justificam gambiarras, com uma proposta para cada um (remover, substituir por uma regra verificável ou manter, e porquê). Não apagues nada.

7. LONGEVIDADE
Separa o que é genérico (qualquer puzzle) do que é específico de "Os Alpes" e diz onde vive cada parte.

REGRAS
- Trabalha numa cópia; nunca em projects/alpes.
- Marca cada afirmação como [V] verificado, [NT] não testado ou [F] falso.
- Se algo exigir decisão minha, apresenta as opções comparadas numa tabela, com recomendação.
- Paragem: termina quando o plano estiver completo. Não implementes.
- Escreve o relatório final, palavra por palavra, na secção «Resultado» de docs/prompts/2026-11-26-verificacao-deterministica.md e faz commit desse ficheiro (sem Claude como co-author).

## Resultado

Ronda só de levantamento e plano. Não alterei código, testes, `tools/` nem dados. Medições feitas numa cópia de `projects/alpes` (criada com `tools/diagnostico/gui/guarda.py`, `copytree`; apagada no fim com `guarda.rmtree`), com `.venv/Scripts/python.exe`; o código dos dois scripts de medição está inteiro no anexo A (ajuste 2). Etiquetas: [V] verificado, [NT] não testado, [F] falso/falha medida.

**Vigilância:** início `projects/alpes/pieces` 39 e `overlays` 39, `git status` só com o ficheiro deste prompt por seguir; fim: ver a última linha desta secção (secção 10).

### 0. Resumo executivo

- O repositório já tem boa parte do que se pede: `Project.check_invariants`, a regra de simetria no perfil (`PuzzleProfile.twin`, `projects/alpes/puzzle.json`), `consistency.twin_local_residual`, `tests/test_segment_scan_esym.py`, `tests/test_twin_real.py`, `tests/test_guarda.py`, `tests/test_quadrados_json.py`. Falta: (a) um comando único com baseline e saída ≠ 0; (b) um conjunto de referência com hashes; (c) lint das regras de processo (tabs, `__all__`, co-author, vigilância 39/39); (d) uma captura de GUI padronizada.
- Medido hoje na cópia [V]: passam o estado/coerência do tabuleiro, a borda 218/218, o contorno guardado == o lido da linha manual (10/10) e os grupos soltos sem sobreposição. **Falham**: a simetria de pares (3 pares, 6 peças fora da exceção `c32|c33`, todas já listadas nas Suspeitas como «recorte») e a regra literal «aresta do Tiago contida no índice guardado» (8 de 10 contornos manuais ativos, 0,2 a 1,6 mm²; [NT] se é convenção ou erro, ver 4.1).
- Decisões para o Tiago: 5, na secção 8.

### 1. Levantamento de regras e correções repetidas

Fontes lidas: `.claude/skills/cv-visual-verification`, `piece-fit-matching`, `docs/revisao.md` (13 rondas, 2026-10-29 a 2026-11-08), `docs/decisoes.md` (63 secções), 46 ficheiros em `docs/prompts/` (45 antes deste), `CLAUDE.md`, e as mensagens dos 317 commits (`git log --format=%s`). A coluna «n.º» é medida por grep e diz o que é: ocorrências em documentos/commits, não bugs distintos.

| Regra / correção | Onde aparece | n.º de vezes | Automatizável? | Como (ou motivo de ficar em prosa) |
|---|---|---|---|---|
| Testes de GUI intermitentes (esperas fixas, rotas de contexto fechado, miniaturas) | `decisoes.md` 2026-11-18, 11-19, 11-25, 11-26; prompts `11-24-regra-e-intermitente`, `11-25-miniaturas-intermitencias`; 4 commits «intermit» | 4 rondas, 6 ficheiros [V] | Lint + teste | Lint que falha em `time.sleep`/`wait_for_timeout` novos em `tests/` fora de uma lista branca (hoje 206 ocorrências em 70 ficheiros [V]); preferir `wait_for_function`. `tools.verify --estabilidade` corre cada ficheiro de GUI N=10 vezes. |
| `projects/alpes/pieces` e `overlays` apagadas sem se ver (o `.gitignore` esconde) | CLAUDE.md «Vigilância», `decisoes.md` 2026-11-24, `tests/test_guarda.py` | 1 ocorrência, causa [NT] | Script | `tools.verify --vigilancia`: conta `pieces/*.npz` e `overlays/*.jpg` contra `scans/*.json` (hoje 39/39 [V]); sai ≠ 0 se menor. A guarda de `rmtree/copytree` já existe (`guarda.py`). |
| Uma árvore de trabalho, um agente de cada vez | CLAUDE.md, `decisoes.md` 2026-11-18 | 1 incidente (suite sobre `3dcfcc8`) | Parcial | `tools.verify` regista `git rev-parse HEAD` e `git status --porcelain` no início e no fim e falha se mudarem durante a corrida (deteta o efeito). Impedir que dois agentes editem a mesma árvore não é automatizável aqui: o repositório não vê quem está a escrever, e não há mecanismo de bloqueio entre agentes [NT]. |
| Suite só com `.venv/Scripts/python.exe` | CLAUDE.md, `decisoes.md` 2026-11-11 (`test_sheets`) | 1 + regra | Script | `tools.verify` recusa correr se `sys.executable` não for o do `.venv` ou se `cv2.__version__` diferir do fixado em `requirements.txt`. |
| Contorno manual do Tiago = verdade exata (D5) | CLAUDE.md Conventions, `decisoes.md` 2026-11-25 | ≥ 4 rondas de correção: aresta oficial e índice derivado (R10, 2026-11-09), convenção do editor (R9), reposição, R0036 (11-25) [V pelo log de commits] | Teste | Invariantes de 4.1 (hash da linha, contorno guardado == lido da linha, aresta contida, banda de 2 mm). |
| Contorno gravado só com a peça (sem sombra) | `strokes.py` (`limitar_indice`, `INDICE_HALO_MAX_MM`), R0036 | 2 rondas (R9, R0036) | Parcial | Proxies medidos: índice a ≤ 2,0 mm da aresta; papel na coroa interior. A fronteira exata peça/sombra fica em prosa e na decisão visual do Tiago: a sombra projetada tem a cor e a textura da própria peça escura (núcleo negro L* < 60 coincide com peças de relva, TRACOS.md), por isso nenhuma regra de cor fixada separa os dois sem GT que não existe. |
| Borda completa 218/218 | CLAUDE.md (2026-11-25), `decisoes.md` D6 | 1 decisão; as notas «217/218» ficaram como histórico | Teste | `Project.missing_border_cells() == []` e 218 `colocada` na borda (hoje 218/218 [V]); cada peça com tantos F quantos os lados fora da grelha (hoje 699/699 [V]). |
| Simetria rot180 só no perfil, nunca `(48−l, 65−c)` no código | skill `piece-fit-matching`, `profile.py` | 1 regra; 1 violação fora de `src/` (`tools/diagnostico/gemeos/ereal2.py`) e 1 exceção por id no `src/` (`consistency.TWIN_EXCEPTIONS`, chave `"alpes"`) [V] | Lint | `grep` determinístico: o padrão `48 *- *l` / `65 *- *c` e a cadeia `"alpes"` fora de `profile.py`/`puzzle.json`/testes falham. |
| Simetria verdadeira nos dados (pares com resíduo ≤ limiar) | `CLAUDE.md` Symmetry, `consistency.py` | 1 | Teste (opcional por perfil) | 4.2. |
| Quadrados 2×2 confirmados continuam a encaixar | `QUADRADOS.md`, `decisoes.md` 2026-11-11 | 2 testes físicos (10 + 7) | Teste | `tools.verify` recalcula as 4 ligações e a margem de cada quadrado com `fit.side_costs` e compara com `quadrados_17.json` (limiar fixo). |
| Etiquetas [V]/[NT]/[F] nos relatórios | CLAUDE.md Conventions, skills | 7 dos 45 «Resultado» fechados não têm nenhuma etiqueta [V]/[NT]/[F] | Lint | `tools.verify --docs`: falha se um `docs/prompts/*.md` com «Resultado» preenchido não contiver `[V`, `[NT` ou `[F`. Verifica a presença, não a verdade: o valor de cada etiqueta exige ler a evidência, e isso fica em prosa. |
| Sem Co-Authored-By nos commits | CLAUDE.md global e do projeto | 7 históricos, o último em 2026-07-11; 0 desde então [V] | Hook | `commit-msg` que rejeita `Co-Authored-By:` e menção a Claude. Hoje não há hooks ativos (`.git/hooks` só tem `.sample`) [V]. |
| Tabs, `__all__`, docstrings em `src/` | CLAUDE.md Conventions | exceções: `edges.py`, `gui.py`, `main.py` indentados a espaços; `__init__`, `gui`, `main` sem `__all__` [V] | Lint | Teste que percorre `src/*.py` (AST) e falha em módulo novo sem `__all__` ou indentado a espaços, com lista branca dos legados. A qualidade de uma docstring não é verificável; só a sua presença. |
| Tabela de módulos do CLAUDE.md desatualizada | CLAUDE.md | `segmentation.py` diz ~1790 linhas e tem 3279; `server.py` ≈ 4906 → 4976 [V] | Script | Gerar a coluna de linhas a partir de `wc -l`. |
| Cada mudança de CV com antes/depois e imagens vistas | skill `cv-visual-verification` | regra permanente | Parcial | Os números: `tools.verify` (antes/depois contra a baseline). «Olhar para a imagem» não é automatizável porque exige reconhecer artefactos novos que nenhuma métrica fixada prevê (a skill cita sombra, mordidelas, fusões); o script gera as imagens de prova, e aceitar ou não é decisão humana. |
| Constantes afinadas só mudam com números | skill | 193 constantes comentadas em `src/` (grep) [V] | Parcial | Teste «constantes congeladas»: um JSON versionado com o valor das de calibração (`puzzle.json` `calibration`, `TWIN_LOCAL_MAX_MM`, `INDICE_HALO_MAX_MM`, …); mudar o valor obriga a mudar o JSON no mesmo commit. A justificação do valor fica em prosa porque é a medição que a sustenta. |
| Módulos críticos só alteráveis pelo implementer | CLAUDE.md | permanente | Não | Regra de organização: o repositório não sabe qual agente escreveu a mudança. |
| Prompts até ao fim; decisões no fim | CLAUDE.md, memória | permanente | Não | Comportamento do agente: não deixa artefacto verificável no repositório. |
| Cada bug corrigido ganha um teste que falhava antes | skill | ≈ 37 commits com «corrig/fix/bug/erro» (grep) [V] | Não | Exigia ligar commit a teste novo; um hook «tests/ alterado» nos commits `fix` daria falsos positivos (correções de dados, docs) e não prova que o teste falhava antes. Fica como convenção de revisão. |

### 2. Conjunto de referência («golden»)

Princípio: não duplicar imagens. Os scans já estão no git (`git ls-files images/pieces`: 620 ficheiros [V]). Os 13 ficheiros de scan que contêm as 218 peças da borda ocupam 27,7 MB; os dos 10 quadrados ≈ 20,7 MB [V]; todos rastreados. O conjunto de referência é um **manifesto** (`tests/golden/manifesto.json`) com ids, células e hashes; a verificação lê os scans onde já estão.

| Parte | O que entra | Verdade de terreno | Tamanho |
|---|---|---|---|
| Borda (218) | por peça: id, `scan_id`, caminho e sha256 do ficheiro de scan, célula (l,c), `cls` e nº de F esperados, sha256 e `.npz` comprimido do `contour_px` | célula física confirmada (218/218, 2026-11-25); F pela geometria da grelha | manifesto ≈ 100 KB; contornos ≈ 0,3 MB [NT, estimativa] |
| 10 quadrados 2×2 | `docs/diagnostico/grupos_soltos/quadrados_17.json` (no git), grupos 1–10: peças, posição local, rotação, 4 ligações, margem; sha256 do JSON | teste físico 2026-11-11 (10/10) | 0 + 10 KB de manifesto |
| Contornos manuais | `projects/alpes/overrides.jsonl` (80 linhas, 4,58 MB, 35 peças; 10 com contorno ativo e 25 repostas ao automático [V]) | o próprio contorno do Tiago (D5) | 4,6 MB (já no git); o golden guarda só o sha256 por linha |
| Pares de simetria | lista dos pares gémeos colocados e o resíduo medido na baseline | simetria do corte (E-sym 20/20) | ≈ 20 KB |
| E-sym (20 pares) | scans A1/A2/B2 e `gt_canto_BE.md` já usados por `tests/test_segment_scan_esym.py` | GT por célula | 0 |

Como garantir que não mudam sem querer [NT, desenho]:
1. `tests/golden/manifesto.json` com sha256 de **cada ficheiro** referido (scans, `overrides.jsonl` linha a linha, `quadrados_17.json`) e de cada contorno guardado.
2. `tools.verify` calcula os hashes no início e falha com um código próprio («golden alterado») se algum diferir. Atualizar o manifesto é um comando explícito (`--refresh-golden --porque "..."`) que escreve uma entrada em `docs/decisoes.md`.
3. `overrides.jsonl` é só-acrescentar: o teste exige que as primeiras N linhas do manifesto continuem iguais byte a byte (uma linha nova não falha; uma alterada ou removida falha).
4. Um `pre-commit` recusa diffs em `tests/golden/` sem a linha «golden:» na mensagem.

Limite honesto: os contornos guardados da borda **vêm do próprio programa** (índice derivado), não são independentes. A parte independente da verdade é: célula, nº de F, simetria, os quadrados e os contornos manuais. O resto é baseline de regressão, e o plano di-lo (ver 3).

### 3. Comando único: `python -m tools.verify`

**Passos** (cada um escreve num JSON e gera imagens de prova):

| Passo | O que corre | Fonte existente que reaproveita |
|---|---|---|
| 0 ambiente | `.venv`, versão do OpenCV, `git rev-parse HEAD`, `git status`, hashes do golden, vigilância 39/39 | `guarda.py`, ponto 4 |
| 1 segmentação | `segment_scan` nos scans do golden (13 ficheiros da borda + os dos quadrados + E-sym) com `debug=True`; compara cada contorno com o guardado | `tests/test_segment_scan_esym.py`, `segment_scan` |
| 2 classificação de bordas | `shape.analyse` por peça: nº de F, `cls`, cantos; confronta com a célula (F esperado) | `src/shape.py`, 4.3 |
| 3 matching | gémeo (`find_twin` nos pares E-sym e E-real-2), molde do buraco (`fit.rank_hole`), ligações dos 10 quadrados (`fit.side_costs`) | `tests/test_twin_real.py`, `fit.py`, `quadrados_17.json` |
| 4 invariantes | 4.1 a 4.3 | `check_invariants`, `consistency` |
| 5 imagens de prova | sobreposição contorno/folha das peças com pior métrica, tabela de pares, quadrados reconstruídos | `debug` de `segment_scan`, `tools/diagnostico/grupos_soltos/` |

**Saídas:** `$PPF_SCRATCH/verify/<data>/metricas.json`, `prova/*.png`, `comparacao.md`. Código de saída ≠ 0 se: golden alterado, qualquer métrica pior do que a baseline além do limiar fixo, invariante violado, ambiente errado.

**Métricas e porquê:**

| Métrica | Porquê | Falha se |
|---|---|---|
| Nº de peças segmentadas por folha vs esperado | a contagem exata foi o primeiro sinal de fusão e de perda (S1, S3) | ≠ esperado |
| Distância ponto-a-ponto máxima e IoU do contorno vs guardado, por peça (`maskcmp.mask_metrics`) | um RMS global esconde uma mordida local (nota de `maskcmp.py`) | máx. > baseline + margem; IoU < baseline |
| Corda dos 4 lados (mm) e `cls` por peça | é o que o encaixe lê | \|Δcorda\| > 0,3 mm (repetibilidade do E-sym) ou `cls` diferente |
| Borda: peças com F certo / 218; `missing_border_cells` | critério direto da D6 | < 218 |
| E-sym: RMS gémeo e top-1 | critério do projeto desde M5 | RMS > 0,5 mm ou top-1 < 20/20 |
| E-real-2: propostas (2) e falsos positivos em negativos conhecidos (0 em 10 608) | precisão do `find_twin` | FP > 0 |
| Molde do buraco: top-1 nos buracos de referência e `alta` falsas | critério M11 | top-1 desce |
| Quadrados 2×2: 10/10 com as 4 ligações mútuas e margem ≥ valor guardado − tolerância | a única verdade física independente do matching | 1 quadrado perde uma ligação |
| Invariantes: violações por regra | 0, exceto as conhecidas | > baseline |

**Baseline [NT nesta ronda]:** só medi os invariantes do ponto 4 (valores no ponto 4). A baseline completa dos passos 1–3 não foi medida e fica [NT]. **O 1.º passo da implementação é congelar a baseline com o próprio `tools.verify`** (`python -m tools.verify --congelar-baseline`), **antes de qualquer alteração ao código**, num commit só com `tests/golden/baseline.json` e `limiares.json`, **nunca com scripts provisórios** (ajuste 1 do Tiago). Os limiares ficam fixados nesse commit e só mudam por decisão do Tiago registada em `decisoes.md`; o comando não tem opção para os ajustar a partir do resultado.

Tempo de corrida [NT, não medido]: o E-sym `slow` demora segundos a minutos; as 25 folhas completas não foram cronometradas. Se o passo 1 passar de ≈ 10 min, ganha um modo `--rapido` (E-sym + 3 folhas) e o completo corre antes de cada commit que toque `segmentation.py`, `shape.py`, `fit.py` ou `twin.py`.

### 4. Invariantes como testes (medidos hoje na cópia)

Medição: cópia de `projects/alpes` (1433 peças no índice, 699 células com peça colocada ou de posição conhecida, 39 folhas) em pasta temporária, `Project.open` sobre a cópia, nenhuma escrita. Scripts no anexo A.

#### 4.1 Contorno manual inalterado e só com a peça

`overrides.jsonl`: 80 linhas, 35 peças, 4 575 526 bytes, sha256 `5625fac032bebecba19a0b0acb18e3a5e22ed1d40f1922094befe6b88b9b162a`; 10 peças com contorno ativo (P0045, P0071, P0139, P0198, P0315, P0395, P0407, P0620, P0754, P1064) e 25 repostas ao automático [V].

| Teste proposto | Resultado hoje | Números |
|---|---|---|
| (a) sha256 de cada linha do `overrides.jsonl` igual ao do golden (só-acrescentar) | **passa** por construção na cópia [V]; o valor medido é a baseline do golden | 80 linhas |
| (b) o `contour_px` guardado em `pieces/<scan>.npz` é igual, bit a bit, ao que o programa lê da linha (`rasterize_polygon(index_contour(...))`) | **passa** [V] | 10/10, 0 violações |
| (c) a aresta do Tiago está contida no índice guardado (D5): área da aresta fora do índice ≤ 0,05 mm² | **falha** [V] | 8/10 violam: P0045 0,609; P0071 1,505; P0139 0,502; P0198 1,591; P0407 1,434; P0620 1,039; P0754 0,215; P1064 0,889 (mm²). Passam P0315 e P0395. [NT] se é a convenção do índice («índice igual ao automático bit a bit» fora das regiões ganhas) ou perda de aresta: a regra tem de ser definida antes de ser teste (D2). |
| (d) índice a ≤ 2,0 mm da aresta (R0036): área fora da banda ≤ 1 mm² | **passa** [V] | 0 peças acima de 1 mm² |
| (e) «só a peça, sem sombra/fundo»: percentagem de papel (distância ao fundo < 28, a do segmentador) numa coroa de 0,5 mm dentro da aresta | **proxy, não prova**: máx. 10,64 % (P0395), p95 8,75 %; acima de 5 %: P0071 5,70, P0198 6,44, P0395 10,64 | limiar [NT, não fixado: sem GT de uma aresta «com sombra» para o calibrar]; a prova exata continua visual (secção 1) |

#### 4.2 Simetria de pares (opcional, vive no perfil)

Desenho: `puzzle.json` ganha `symmetry.verificar = {"limiar_nn_max_mm": 1.75, "excecoes": [...]}`; o texto de `TWIN_EXCEPTIONS` migra para aí, como o comentário de `src/consistency.py` já prevê. O teste só corre se `profile.symmetry.type != "none"`, e usa `profile.twin()` e `consistency.twin_local_residual`. Um puzzle sem simetria declarada ignora-o. [NT] para `translate`: `twin_local_residual` alinha por `free_dist` (rotação livre), o que serve `rot180` mas não foi exercitado noutro tipo.

Medido [V]: 309 pares de células gémeas com as duas peças colocadas; nn_max ≤ 1,75 mm em 300; RMS livre mediana 0,337 mm, p95 0,689 mm. **Violações: 9 pares.** 6 estão na exceção declarada (`c32|c33`, filas 1–3 e 45–47): P0289/P0492, P0290/P0493, P0291/P0494, P0292/P0496, P0293/P0497, P0294/P0498 (nn_max 3,7 a 5,7 mm). **3 pares ficam fora da exceção** (o mesmo corte `c32|c33`, filas 4–5 e 43–44): P0140 (4,32) / P0499 (44,33) 4,73 mm; P0495 (44,32) / P0938 (4,33) 4,37 mm; P0500 (43,33) / P1178 (5,32) 4,56 mm. As 6 peças já são Suspeitas «recorte» (`consistency.evaluate` dá 18 itens = 12 da exceção + estas 6) [V]. **O teste falharia hoje por esses 3 pares**, e a falha é informação real: ou a exceção do corte `c32|c33` se estende a mais duas filas, ou há 6 recortes maus. Decisão: D3.

#### 4.3 Coerência do tabuleiro

| Teste | Resultado hoje | Números |
|---|---|---|
| `Project.check_invariants()` vazio (board == replay do log, ≤ 1 peça por célula, `n_no_lote` único, lote da peça = lote do scan) | **passa** [V] | 0 violações |
| Duas peças na mesma célula (pelo campo `celula` das peças colocadas ou de posição conhecida) | **passa** [V] | 699 células com peça, 0 duplicadas |
| Borda completa: `missing_border_cells() == []` e 218 `colocada` na borda | **passa** [V] | 218/218 |
| F por tipo de célula (canto 2, borda 1, interior 0) em todas as colocadas | **passa** [V] | 699/699 (4 cantos, 214 bordas, 481 interiores) |
| Grupos soltos mostrados: nenhum recusado por `GR.sobreposto`, 0 células com 2 grupos, 0 sobre peça colocada | **passa** [V] | 6 grupos mostrados, 0 sobreposições |

Para os grupos soltos, «nunca sobrepostos» só está garantido na escrita (`mesa.check_position`) e derivado na leitura (`sobreposto`); o teste conta as células por grupo de forma independente, por isso apanharia um `mesa.jsonl` editado à mão.

### 5. Prova da GUI

A base já existe: `tools/gui/d1_capturas.py` (cópia do projeto com `guarda`, servidor num porto, Playwright, 1366×768 e 390×844), `tools/gui/f4_capturas.py` e as capturas em `docs/gui/screenshots/2026-11-25/`. Proposta: `python -m tools.gui.prova --base projects/alpes`:

- copia o projeto com `guarda.copytree` (melhor: um projeto mínimo versionado em `tests/data/projeto_mini/`, [NT] ainda não existe, para as capturas serem reprodutíveis; com o projeto real o ecrã muda sempre que o Tiago usa a GUI);
- arranca `src.server --ui novo` e espera pelo «pronto» (`gil_intervalo._wait_ready` e `_wait_holes`);
- guarda PNG a 1366×768 e 390×844 de: Montar (cartão atual e vazio), tabuleiro geral, detalhe com zoom, painel da peça, painel do lugar, lupa, «Grupos soltos» (lista e painel), Reports, Suspeitas, menu/definições;
- escreve `indice.html` com as capturas lado a lado e `capturas.json` com sha256 e tempos;
- falha se houver erro de consola do browser (`erro_cliente`), resposta ≥ 500, scroll horizontal a 390 px ou ecrã em branco (todos os pixels iguais).

Não propus comparação pixel a pixel: a data, o tabuleiro e o texto mudam. A revisão estética continua humana, mas sobre imagens.

### 6. Código que ensina maus padrões (não apaguei nada)

| Item | Onde | Proposta | Porquê |
|---|---|---|---|
| `src/edges.py` obsoleto (usado por `src/gui.py:391`, `tests/test_edges.py` e 2 ferramentas) | `src/edges.py` | **Manter agora; remover com a GUI Tkinter** | O CLAUDE.md declara-o obsoleto; apagar parte a GUI antiga e dois diagnósticos. Decisão D5. |
| `src/gui.py`, `src/main.py`, `src/acquisition.py` (legado) a espaços e/ou sem `__all__` | `src/` | **Manter**, na lista branca do lint | É o legado declarado; o lint não deve fingir que cumpre. |
| `F_TRANSLATION = False`, `REGISTER_IMAGE = False` | `src/render.py:99,149` | **Manter e acrescentar um teste de que ficam em `False`** | Decididos com números (RENDER.md §9; DETALHE §13.9); o teste evita ligá-los sem querer. |
| `TWIN_EXCEPTIONS = {"alpes": …}` por id no `src/` | `src/consistency.py:81` | **Substituir por `symmetry.excecoes` no `puzzle.json`** | O comentário já pede; é o único sítio do `src/` com conhecimento de um puzzle (secção 7). |
| `48 - l` / `65 - c` em ferramenta | `tools/diagnostico/gemeos/ereal2.py` | **Substituir por `profile.twin`** | Viola a regra de `piece-fit-matching`; o lint passa a apanhar. |
| Esperas fixas nos testes | 206 ocorrências de `time.sleep`/`wait_for_timeout` em 70 ficheiros de `tests/` [V] | **Substituir por `wait_for_function`/eventos, aos poucos; lint trava novas** | Causa de 4 rondas de testes intermitentes. Não troquei nenhuma: cada uma exige perceber o que espera. |
| `except Exception` amplo | 70 em `src/`, 42 com `# noqa: BLE001` [V] | **Manter os anotados; rever os 28 sem anotação** | Um `except` largo esconde bugs; sem anotação não se sabe se é intencional. [NT] quais dos 28 são. |
| Parâmetros afinados à mão | 193 constantes comentadas em `src/` (ex.: `GIL_SWITCH_S` 0,5 ms, `YIELD_MAX_S` 30 s, `DETALHE_ESPERA_S` 1,0 s, `WRITE_WAIT_S` 90 s, `READY_MB` 600, `TWIN_LOCAL_MAX_MM` 1,75, `INDICE_HALO_MAX_MM` 2,0) | **Manter e congelar o valor num teste; exigir número antes/depois no commit** | Foram medidas (os comentários citam a medição): não são «mágicas», o risco é mudarem sem ela. |
| Historial datado nas docstrings e linhas gigantes na tabela de módulos do CLAUDE.md | `CLAUDE.md`, docstrings | **Mover para `docs/decisoes.md`; deixar só a regra atual** | A tabela tem contagens de linhas erradas (`segmentation.py` 1790 → 3279) [V] e é paga em todas as sessões. Fora do âmbito desta ronda. |
| Marcadores `TODO/FIXME/hack/workaround` | `src/` | **Nada a fazer** | 69 linhas de grep, quase todas `todo` = «lista a fazer» (`strips_todo`, `todo_l`) [V]; não encontrei `FIXME` nem `HACK` verdadeiros. |

### 7. Longevidade: genérico vs específico de «Os Alpes»

| Parte | Vive em | Estado |
|---|---|---|
| Grelha, célula, dpi, simetria, fundo, arte, calibrações por modalidade, zonas de imagem | `projects/<id>/puzzle.json` + `src/profile.py` | Genérico [V] (`PuzzleProfile`; `twin` é a única implementação) |
| Segmentação, forma, lados, gémeo, molde do buraco, estado, render | `src/segmentation.py`, `shape.py`, `twin.py`, `fit.py`, `state.py`, `render.py` | Genérico; calibrações lidas do perfil |
| Exceção do corte `c32|c33` | `src/consistency.py:81`, por id `"alpes"` | **Específico no sítio errado** → `symmetry.excecoes` do perfil |
| Zonas (céu, montanha, vale, relva) | `puzzle.json` `image_zones` | Específico no sítio certo |
| Legado explodido, borda por cantos/F | `src/legacy.py`, `src/border.py` | Lógica genérica, dados específicos (páginas `montado_pNN`, 9 gémeos fixados); [NT] se `border.py` assume 218 de borda e 217 ↔ 217 |
| Verdade de terreno | `images/pieces/gemeos_2026-10-30.md`, `gt_canto_BE.md`, `quadrados_17.json`, `overrides.jsonl` | Específico dos Alpes → `tests/golden/` com manifesto |
| Invariantes do ponto 4 | `tools/verify` | Estado (4.3) e manual (4.1): genéricos; simetria (4.2): só se o perfil a declarar |
| Regras de processo (co-author, `.venv`, vigilância) | hooks + `tools.verify` | Genéricas do repositório; o «39» passa a ser o nº de `scans/*.json`, não fixo |

### 8. Decisões para o Tiago

| # | Decisão | Opções | Recomendação |
|---|---|---|---|
| D1 | Onde guardar o golden e como o proteger | A) manifesto com hashes sobre os scans já no git (0 MB novos); B) copiar tudo para `tests/golden/` (≈ 50 MB); C) só baseline, sem GT independente | **A**: os scans já estão rastreados; B duplica ≈ 48 MB. |
| D2 | Regra do contorno manual no índice: a aresta do Tiago tem de estar contida no índice guardado? (hoje 8/10 não, 0,2–1,6 mm²) | A) sim, exato (corrigir o código que deriva o índice); B) não: o índice é convenção e o teste exige só 4.1 (b) e (d); C) medir primeiro a origem da diferença | **C**, depois A ou B. Não sei se é bug ou convenção [NT]; a D5 diz que, se uma derivação sai mal, o erro é do código. É trabalho do implementer, não do helper. |
| D3 | Os 3 pares fora da exceção `c32|c33` (P0140/P0499, P0495/P0938, P0500/P1178) | A) alargar a exceção a filas 4–5 e 43–44 (depois de confirmar fisicamente); B) tratar as 6 peças como recortes maus; C) o teste aceita uma lista «conhecidas por rever» | **C** até olhar as 3 imagens, depois **A** ou **B**. |
| D4 | Hooks Git: `commit-msg` (co-author/Claude) e `pre-commit` (tabs, `__all__`, golden) | A) ativar, versionados em `tools/githooks/` com `core.hooksPath`; B) só `tools.verify` à mão; C) nada | **A** para o `commit-msg` (custo nulo, regra já escrita); o `pre-commit` com testes lentos fica manual. |
| D5 | `src/edges.py` + `src/gui.py` (Tkinter) | A) remover os dois e `tests/test_edges.py`; B) manter; C) mover para `legacy/` | **B** nesta fase; a remoção é do Tiago (GUI antiga). |

### 9. Ordem de implementação (para o implementer; nada feito)

1. Esqueleto de `tools/verify` + passo 0 (ambiente, hashes, vigilância) e **congelar a baseline com o próprio `tools.verify`** (commit só com `baseline.json` e `limiares.json`), antes de qualquer outra alteração ao código.
2. Invariantes 4.1 (b) e (d) e 4.3 como testes `pytest` rápidos (passam hoje); 4.1 (c) e 4.2 só depois de D2 e D3.
3. Passos 1–3 (segmentação, classificação, matching) sobre o golden, com imagens de prova.
4. Lint de convenções (`__all__`, tabs, twin hardcode, sleeps) e hooks (D4).
5. `tools.gui.prova` (secção 5).

### 10. Vigilância final

Fim: `projects/alpes/pieces` 39 e `overlays` 39 (esperado 39/39), cópia de medição apagada com `guarda.rmtree`; `git status` antes do commit: ?? docs/prompts/2026-11-26-verificacao-deterministica.md (só este ficheiro; `graphify update .` corre a seguir e pode mexer em `graphify-out/`).

### Anexo A: código dos scripts de medição do ponto 4

Ficheiros no scratchpad `C:\Users\tiago\AppData\Local\Temp\claude\3add34662e8ccffd\cdec8ab8-1b2f-4910-8c75-f0324c9fbafa\scratchpad\` (`cp.py`, `m_estado.py`, `m_manual.py`); corridos com `.venv/Scripts/python.exe <script> <cópia do projeto>`. A cópia é `%TEMP%\ppf_verif_copia\alpes`. Indentação por tabs, como `src/`.


#### `cp.py`: Cópia para a pasta temporária (guarda.copytree)

```python
import sys
sys.path.insert(0, "D:/DEKSTOP/puzzle_piece_finder/tools/diagnostico/gui")
import guarda, os, tempfile
dst = os.path.join(tempfile.gettempdir(), "ppf_verif_copia", "alpes")
if os.path.exists(dst): guarda.rmtree(dst)
os.makedirs(os.path.dirname(dst), exist_ok=True)
guarda.copytree("D:/DEKSTOP/puzzle_piece_finder/projects/alpes", dst)
print(dst)
```

#### `m_estado.py`: Estado, borda, simetria e grupos soltos

```python
"""Ponto 4 (medicao): coerencia do tabuleiro, borda completa e simetria de pares. So leitura; corre sobre uma COPIA.
Uso: .venv/Scripts/python.exe m_estado.py <copia do projeto>"""
import json, os, sys, collections
sys.path.insert(0, "D:/DEKSTOP/puzzle_piece_finder")
from src.state import Project
from src import consistency as CS, grupos as GR, mesa
from src.overrides import is_manual

pr = Project.open(sys.argv[1])
prof = pr.profile
out = {}

# 1) invariantes do estado
errs = pr.check_invariants()
out["check_invariants"] = {"n": len(errs), "erros": errs[:10]}

# 2) duas pecas na mesma celula (pelo campo celula das pecas e pelo tabuleiro)
por_cel = collections.defaultdict(list)
for pid, p in pr.pieces.items():
	if p.estado in ("colocada", "posicao_conhecida") and p.celula is not None:
		por_cel[tuple(p.celula)].append(pid)
dup = {f"{k[0]},{k[1]}": v for k, v in por_cel.items() if len(v) > 1}
out["mesma_celula"] = {"celulas_com_pecas": len(por_cel), "duplicadas": dup}

# 3) borda completa 218/218 e F por tipo de celula
bordas = [lc for lc, _ in pr.board.iter_cells() if prof.is_border(*lc)]
colocadas = [lc for lc in bordas if pr.board.cell(*lc)["estado"] == "colocada"] if hasattr(pr.board, "cell") else None
if colocadas is None:
	colocadas = [lc for lc, c in pr.board.iter_cells() if prof.is_border(*lc) and c["estado"] == "colocada"]
falta = [list(lc) for lc in bordas if lc not in set(colocadas)]
out["borda"] = {"celulas_borda": len(bordas), "colocadas": len(colocadas), "em_falta": falta,
				"missing_border_cells": [list(x) for x in pr.missing_border_cells()]}
nF = collections.Counter(); viol = []
for pid, p in pr.pieces.items():
	if p.estado != "colocada" or p.celula is None: continue
	esperado = sum(1 for (dl, dc) in ((-1, 0), (1, 0), (0, -1), (0, 1))
				   if not (1 <= p.celula[0] + dl <= prof.rows and 1 <= p.celula[1] + dc <= prof.cols))
	cls = p.cls or ""
	got = cls.count("F")
	nF[(esperado, got)] += 1
	if esperado != got: viol.append([pid, list(p.celula), cls, esperado, got])
out["borda_F"] = {"pares_(esperado,obtido)": {f"{k[0]},{k[1]}": v for k, v in nF.items()}, "violacoes": viol[:30], "n_violacoes": len(viol)}

# 4) simetria de pares: celulas gemeas ambas colocadas
by_cell = {tuple(p.celula): pid for pid, p in pr.pieces.items() if p.estado == "colocada" and p.celula is not None}
vistos = set(); pares = []
for lc, pid in by_cell.items():
	tc = prof.twin(*lc)
	if tc is None or tuple(tc) not in by_cell: continue
	key = frozenset([lc, tuple(tc)])
	if key in vistos: continue
	vistos.add(key)
	qid = by_cell[tuple(tc)]
	a, b = pr.shape(pid), pr.shape(qid)
	r = CS.twin_local_residual(a, b) if (a is not None and b is not None and a.ok and b.ok) else None
	pares.append({"a": pid, "ca": list(lc), "b": qid, "cb": list(tc), "r": r,
				  "manual": bool(is_manual(pr.piece(pid)) or is_manual(pr.piece(qid))),
				  "exc": CS.twin_exception(prof, lc) is not None})
medidos = [x for x in pares if x["r"]]
viols = [x for x in medidos if x["r"]["nn_max_mm"] > CS.TWIN_LOCAL_MAX_MM]
viol_sem_exc = [x for x in viols if not x["exc"]]
rms = sorted(x["r"]["rms_mm"] for x in medidos)
out["simetria"] = {"pares_gemeos_ambos_colocados": len(pares), "medidos": len(medidos),
	"limiar_nn_max_mm": CS.TWIN_LOCAL_MAX_MM, "violacoes": len(viols), "violacoes_fora_da_excecao": len(viol_sem_exc),
	"rms_mediana": rms[len(rms)//2] if rms else None, "rms_p95": rms[int(len(rms)*0.95)] if rms else None,
	"ids_violacao_fora_excecao": [[x["a"], x["b"], x["ca"], x["cb"], round(x["r"]["nn_max_mm"], 2), x["manual"]] for x in viol_sem_exc],
	"ids_violacao_na_excecao": [[x["a"], x["b"], x["ca"], x["cb"], round(x["r"]["nn_max_mm"], 2)] for x in viols if x["exc"]]}

# 5) grupos soltos: sobreposicao
shown = mesa.effective_positions(pr)
bad = {}
for gid, pos in shown.items():
	r = GR.sobreposto(pr, gid, pos, shown)
	if r: bad[gid] = r
# sobreposicao entre grupos mostrados, celula a celula, recalculada de forma independente
occ = collections.defaultdict(list)
for gid, pos in shown.items():
	for pid, lc in mesa.footprint(pr.sections[gid], pos) if isinstance(mesa.footprint(pr.sections[gid], pos)[0], tuple) and len(mesa.footprint(pr.sections[gid], pos)[0])==3 else [(None, c) for c in mesa.footprint(pr.sections[gid], pos)]:
		occ[tuple(lc)].append(gid)
dupg = {f"{k[0]},{k[1]}": v for k, v in occ.items() if len(set(v)) > 1}
sobre_colocada = [f"{k[0]},{k[1]}" for k in occ if k in by_cell]
out["grupos"] = {"mostrados": len(shown), "sobreposto_por_GR.sobreposto": {k: {"motivo": v.get("motivo"), "celula": v.get("celula")} for k, v in bad.items()},
				 "celulas_com_2_grupos": dupg, "celulas_sobre_peca_colocada": sobre_colocada}
print(json.dumps(out, ensure_ascii=False, default=str))
```

#### `m_manual.py`: Contornos manuais

```python
"""Ponto 4 (medicao): contornos manuais. So leitura; corre sobre uma COPIA.
Uso: .venv/Scripts/python.exe m_manual.py <copia do projeto>"""
import hashlib, json, sys, collections
import numpy as np, cv2
sys.path.insert(0, "D:/DEKSTOP/puzzle_piece_finder")
from src.state import Project
from src import overrides as OV, strokes as ST
from src.overrides import _mmpp

pr = Project.open(sys.argv[1])
fp = OV.overrides_path(pr)
raw = open(fp, "rb").read()
linhas = raw.splitlines()
out = {"ficheiro": {"linhas": len(linhas), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}}
out["sha256_por_linha_primeiras3"] = [hashlib.sha256(l).hexdigest()[:12] for l in linhas[:3]]
ov_all = OV.latest_overrides(pr, incluir_reposicao=True)
ov = OV.latest_overrides(pr)
out["pecas_com_linha"] = len(ov_all); out["pecas_com_contorno_ativo"] = len(ov)
out["reposicao_ativa(auto)"] = sorted(set(ov_all) - set(ov))

bg = np.array(pr.profile.background_lab if hasattr(pr.profile, "background_lab") else [79.2, -50.0, 47.0], float)
def lab(rgb): return cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32) * np.array([100/255, 1, 1], np.float32) - np.array([0, 128, 128], np.float32)

rows = []; rgb_cache = {}
for pid, o in sorted(ov.items()):
	sid = o["scan_id"]; mm = _mmpp(pr, sid)
	rgb = rgb_cache.get(sid)
	if rgb is None: rgb = rgb_cache[sid] = OV.load_scan_rgb(pr, sid)
	H, W = rgb.shape[:2]
	# 1) contorno guardado no indice == o que as regras leem da linha do Tiago
	p = pr.piece(pid)
	z = np.load(pr.p("pieces", f"{p.scan_id}.npz"), allow_pickle=False)
	stored = z[f"{pid}__contour_px"].astype(np.int32)
	_, _, expect = OV.rasterize_polygon(OV.index_contour(pr, o, rgb), W, H)
	same = stored.shape == expect.shape and bool(np.array_equal(stored, expect))
	r = {"piece": pid, "scan": sid, "contorno_igual_ao_da_linha": same, "tem_aresta": bool(o.get("aresta_px"))}
	# mascara do indice guardado
	def fill(c):
		m = np.zeros((H, W), np.uint8); cv2.fillPoly(m, [np.round(np.asarray(c, float)).astype(np.int32).reshape(-1, 1, 2)], 1); return m > 0
	mi = fill(stored)
	if o.get("aresta_px"):
		ma = fill(np.asarray(o["aresta_px"], float).reshape(-1, 2))
		r["aresta_fora_do_indice_mm2"] = round(float((ma & ~mi).sum()) * mm * mm, 3)       # D5: a aresta nunca fica de fora
		r["indice_fora_da_banda_2mm_mm2"] = round(float(ST.indice_fora_mm2(mi, ma, mm)), 3)  # R0036
		# "sem sombra/fundo": fracao de papel (dist. ao fundo < 28) numa coroa de 0,5 mm DENTRO da aresta
		d_in = cv2.distanceTransform(ma.astype(np.uint8), cv2.DIST_L2, 5)
		ring = ma & (d_in <= 0.5 / mm)
		L = lab(rgb)
		dd = np.sqrt(0.5 * (L[..., 0] - bg[0]) ** 2 + (L[..., 1] - bg[1]) ** 2 + (L[..., 2] - bg[2]) ** 2)
		r["papel_na_coroa_interior_0.5mm_%"] = round(float((dd[ring] < ST.PAPEL_LIMIAR).mean() * 100), 2)
		r["aresta_area_mm2"] = round(float(ma.sum()) * mm * mm, 2); r["indice_area_mm2"] = round(float(mi.sum()) * mm * mm, 2)
	rows.append(r)
n = len(rows)
out["contorno_igual_ao_da_linha"] = {"n": n, "violacoes": [r["piece"] for r in rows if not r["contorno_igual_ao_da_linha"]]}
ar = [r for r in rows if r["tem_aresta"]]
out["com_aresta"] = {"n": len(ar),
	"aresta_fora_do_indice>0.05mm2": [(r["piece"], r["aresta_fora_do_indice_mm2"]) for r in ar if r["aresta_fora_do_indice_mm2"] > 0.05],
	"indice_fora_banda>1mm2": [(r["piece"], r["indice_fora_da_banda_2mm_mm2"]) for r in ar if r["indice_fora_da_banda_2mm_mm2"] > ST.INDICE_FORA_MIN_MM2],
	"papel_coroa_max_%": max(r["papel_na_coroa_interior_0.5mm_%"] for r in ar) if ar else None,
	"papel_coroa_p95_%": float(np.percentile([r["papel_na_coroa_interior_0.5mm_%"] for r in ar], 95)) if ar else None,
	"papel_coroa>5%": [(r["piece"], r["papel_na_coroa_interior_0.5mm_%"]) for r in ar if r["papel_na_coroa_interior_0.5mm_%"] > 5]}
out["sem_aresta"] = [r["piece"] for r in rows if not r["tem_aresta"]]
print(json.dumps(out, ensure_ascii=False, default=str))
```

#### `rm.py`: Apagar a cópia (guarda.rmtree)

```python
import sys, os, tempfile
sys.path.insert(0, "D:/DEKSTOP/puzzle_piece_finder/tools/diagnostico/gui")
import guarda
d = os.path.join(tempfile.gettempdir(), "ppf_verif_copia")
guarda.rmtree(d); print("apagada", not os.path.exists(d))
```
