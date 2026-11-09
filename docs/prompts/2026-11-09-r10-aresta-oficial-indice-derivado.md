# 2026-11-09 — ronda 10: o contorno é só a peça (A2: aresta oficial, índice derivado)

## Porquê

Na ronda 9 o editor passou a gravar na convenção do índice: o halo de sombra (≈ 0,2–1,4 mm) ficava incluído, o «não é peça» sobre a sombra era ignorado e a linha laranja (a que se grava) ficava por fora da aresta. O Tiago quer que o contorno gravado seja **só a peça**, sem perder os 17 contornos antigos nem os 4 que gravou hoje, e sem estragar as gémeas e os buracos, que estão calibrados sobre a silhueta com sombra.

## Decisões

- **A2 em vez de A1.** O registo grava duas silhuetas:
  - `aresta_px`: a aresta pintada, que é o contorno oficial do desenho e da sugestão pela gémea;
  - `contour_px`: a silhueta do índice, derivada da aresta.

  A1 (recalibrar tudo para a aresta) fica fora: custaria dias e mudaria «Vai buscar» por definição.
- **Regra única bit a bit** (decisão do Tiago a meio da ronda): «índice igual ao automático» é a comparação exata, no servidor e na ferramenta. A tolerância de 0,5 mm herdada de `renormalizar.py` saiu.
- **Fase 2** (recortar todas as peças pela aresta, zona a zona): adiada até chegarem as máscaras do Photoshop de P1203, P0045, P1245 e P0198 (P0229 opcional). A tolerância por zona foi fixada só com P0651/P0657 e não está validada.
- **Limiares registados como [NT]** em `decisoes.md`: `GANHO_MIN_MM2` 2 mm², `GEMEA_RUIDO_MM` 0,25 mm (não estava no plano), os 3 mm² do teste do laço.
- **Fixture de `test_gui_guardadas`:** o `fetch.json` fica fixo em `bc6b772` (autorizado; asserções iguais).
- **CLAUDE.md:** o início de sessão aponta para `estado-e-plano.md` + `ARCHITECTURE.md` + `HANDOFF.md`. Não se cria `docs/STATUS.md`.
- **Duas paragens com OK explícito do Tiago:** OK 1 (commit do estado de hoje) e OK 2 (aplicar no projeto real, com o servidor parado e cópia de segurança antes). Ambos dados.

Detalhe em `docs/decisoes.md` (ronda 10) e `docs/diagnostico/editor/CONVENCAO.md` §6.

## Prompt verbatim

> Agente: implementer. Skills: cv-visual-verification, piece-fit-matching, graphify.
>
> Repo: D:\DEKSTOP\puzzle_piece_finder (Windows; Bash = Git Bash). Lê primeiro o plano aprovado, que é a tua especificação: C:\Users\tiago\.claude\plans\agente-implementer-skills-cv-visual-veri-shimmering-tarjan.md. Lê também docs/HANDOFF.md e docs/diagnostico/editor/CONVENCAO.md.
>
> Regra do graphify: graphify-out/graph.json existe — corre `graphify query "<pergunta>"` antes do primeiro grep/leitura de código; lê ficheiros só nas linhas que o grafo ou uma leitura anterior já localizaram; `graphify update .` no fim.
>
> Interpretador: D:\DEKSTOP\puzzle_piece_finder\.venv\Scripts\python.exe (OpenCV 4.11), com PYTHONIOENCODING=utf-8. ATENÇÃO: `python -` com heredoc no Git Bash entra em modo interativo e fica pendurado — escreve scripts em ficheiros .py (no scratchpad C:\Users\tiago\AppData\Local\Temp\claude\011f846714d7d8db\00645572-7017-4a80-b59a-3d5f3d9e890a\scratchpad) ou usa `python -c "$(cat <<'EOF' ... EOF)"`. Nunca `taskkill /IM python.exe`. Suite completa > 300 s: em segundo plano. `tools/diagnostico/**` precisam de PPF_SCRATCH.
>
> O que fazer NESTA execução (por esta ordem), e parar onde indicado:
>
> 1. Fixture de `tests/test_gui_guardadas.py` (já autorizado): na fixture `real`, o `fetch.json` vem de `git show bc6b772:projects/alpes/fetch.json` (o log nesse commit tem 2045 linhas = LOG_EVENTS) em vez do ficheiro vivo; skip se git/commit indisponível. NÃO mexas nas asserções. Corre o teste. Commit só desse ficheiro, mensagem em português que diga explicitamente que alterou um teste existente (asserções iguais). Sem linha Co-Authored-By.
>
> 2. CLAUDE.md do projeto: a frase «No início da sessão, ler primeiro docs/STATUS.md.» passa a apontar para docs/estado-e-plano.md e ARCHITECTURE.md (e docs/HANDOFF.md). NÃO cries docs/STATUS.md.
>
> 3. Implementar A2 conforme §2 e §4 do plano: `src/strokes.py` (resolver normalizado devolve a aresta bruta com TODOS os traços — «não é peça» sobre a sombra respeitado — e o índice derivado com `normalizar`/`delta_peca`), `src/overrides.py` (`aresta_px` em EXTRA_KEYS, `convencao: "aresta+indice"`, registos antigos lidos como hoje, `twin_suggestion` a partir da aresta da gémea), `src/server.py` (gravar os dois; `contour_px` continua a ser o índice), `src/render.py` (recorte de visualização das peças editadas usa `aresta_px`; peças sem edição ficam com a regra atual), `src/web/editor.js` (laranja = aresta; linha fina = índice derivado; texto de ajuda do §4 SEM o número «≈ 0,5 mm»; CED_LEGENDA), `docs/gui-design.md`. Peças cujo índice derivado é o automático bit a bit: registo só de visualização (sem manual_override, sem piece_resegmented). Testes do §5.1 escritos e verdes.
>
> 4. Ferramenta `tools/diagnostico/editor/reaplicar_aresta.py` (padrão de renormalizar.py, dry-run por omissão) para os registos 0–16 e 35–38 de projects/alpes/overrides.jsonl (P0198, P0620, P1203×2 gravados hoje pelo Tiago). Generalizar convencao.py com medição por lado (E/S/N/W no referencial do scanner) e `--gt DIR`.
>
> 5. Verificação numa CÓPIA (`<scratchpad>/alpes_r10`; nunca escrever em projects/alpes): ativos refeitos antes (`tools/rebuild_scans.py --stale --also-missing`), linha de base, `reaplicar_aresta.py --aplicar` na cópia, consulta completa, `fetch.json` idêntico nas entradas sem peça editada, reprodução R7 43/43 (`r7_gt.py`), `check_invariants(disk=True)`, Suspeitas iguais. Mosaico visual antes/depois das 21 peças (vermelho automático, laranja aresta, ciano índice derivado, magenta GT do Photoshop para P0651/P0657). Tabela por lado do §1 refeita.
>
> 6. Commits do código e testes (português, sem co-author). Os ficheiros de projects/alpes que estão modificados no working tree (log.jsonl, overrides.jsonl, fetch*) são trabalho do Tiago de hoje: NÃO os stages nem os commites, nem os alteres.
>
> PARAGENS OBRIGATÓRIAS — não as ultrapasses:
> - OK 1: antes de commitar o estado de hoje do Tiago (projects/alpes). Pára e reporta.
> - OK 2: antes de aplicar no projeto real com o servidor parado. Pára e reporta.
> - Fase 2 (§5.4: solver sem traços puro e deslocamento direcional W/S, critério por zona, tolerância declarada como fixada só com P0651/P0657, não validada) depende das 4 máscaras do Photoshop que o Tiago vai fazer (P1203, P0045, P1245, P0198, em docs/diagnostico/editor/gt_photoshop/); P0229 só entra se a fase 2 avançar. Não a corras agora; deixa a ferramenta pronta para quando as máscaras chegarem.
>
> Relatório final (em português): o que foi feito com evidência numérica, etiquetas [V]/[NT]/[F], hashes dos commits, resultado dos testes (com contagens), números da cópia (fetch idêntico? R7 x/43? invariantes? suspeitas?), caminhos absolutos das figuras, e o que fica à espera do OK 1 / OK 2 / máscaras.

Mensagens seguintes do gestor, resumidas e não verbatim:
1. OK 1: commit dos 13 ficheiros do estado de hoje, mais o registo dos limiares [NT] em `decisoes.md`.
2. Regra única bit a bit no `reaplicar_aresta.py`, com as provas repetidas numa cópia limpa e o efeito em gémeas e buracos.
3. OK 2, primeira parte: R7 medido de novo, cópia de segurança com sha256, paragem antes de escrever.
4. OK 2, segunda parte (servidor confirmado parado): `--aplicar` no projeto real, consulta, verificações, commit.
5. Fecho da ronda: estes documentos.

## Resultado

**Commits:**
- `91ef246`: fixture;
- `ac6e495`: CLAUDE.md;
- `85b5b8d`: código A2 (strokes, overrides, server, render, editor.js, testes, gui-design §18.6d, ARCHITECTURE);
- `2cd321e`: ferramentas e figuras;
- `b23d449`: estado de hoje do Tiago;
- `bb281d9` e `0ede00c`: limiares [NT];
- `03e3af5` e `d583411`: regra bit a bit;
- `d865e29`: dados do projeto real;
- docs de fecho.

**Testes [V]:** suite completa 460 passed, 1 skipped, 0 failed (288 s).

**Projeto real [V]:**
- `--aplicar`: 19 registos, 4 `piece_resegmented`, 0 erros.
  - 14 peças só com visualização.
  - P0045, P0071 e P1064 com índice manual, por 1 píxel cada.
  - P0198 e P0620 com o índice que o Tiago gravou.
  - P1203 reposto no automático.
- `fetch.json` idêntico (15/15), invariantes [], Suspeitas iguais.
- Na cópia: R7 43/43.

**Por fazer:**
- Fase 2, à espera das máscaras do Photoshop (a candidata (b), deslocamento direcional, ainda não tem ferramenta).
- As verificações do Tiago na GUI: [NT], ele ainda não reportou nada.
- O possível sobre-corte no lado S dos 17 traços antigos [NT].
- O custo das 3 peças fora das métricas de CV [NT].

Ficheiro fechado em 2026-11-09.
