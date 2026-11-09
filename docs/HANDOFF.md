# HANDOFF — 2026-11-09 (ronda 9: editor na convenção do índice, os 17 contornos manuais, contorno sugerido pela gémea; fechada)

Lê isto primeiro numa sessão nova; no fim, atualiza-o e fecha o ficheiro do prompt em `docs/prompts/`.

## Estado
- **Commits desta ronda** (em `main`): `f0ed181` medição da convenção; `0664206` normalização em `src/strokes.py`; `a83f8b4` servidor/GUI do editor; `850d7e5` contorno sugerido pela gémea; `b6d4428` reposição + `renormalizar.py` + verificação na cópia; `83fdd5c` **dados do projeto real**; `587bb77` regra dos ganhos pequenos; `d886ac3` P0045 reposto; docs finais. Prompt: `docs/prompts/2026-11-09-r9-convencao-editor-gemea.md`. Relatório: `docs/diagnostico/editor/CONVENCAO.md`.
- **A leitura do R7 §1.3 estava invertida [V]:** os 17 contornos manuais estavam **dentro** do automático (mediana −0,24…−0,51 mm), não fora. O índice inclui ≈ 0,2–0,5 mm de sombra/penumbra (até 1,4 mm nos lados da sombra) e a ajuda do editor mandava pôr «não é peça» sobre a linha negra da sombra.
- **Editor [V]:** o que se grava segue a convenção do índice (halo da própria peça + núcleo negro da sombra; traços «fundo» só sobre a sombra ignorados por inteiro e mostrados a cinzento; automático bit a bit fora da região dos traços; gravar sem traços = contorno atual exato). Ajuda reescrita; aresta detetada a tracejado branco; δ na linha de estado.
- **Projeto real:** os 17 contornos repostos no automático exato (`metodo: "reposicao"`, `manual_override` sai; 0 contornos manuais ativos). P0045 chegou a ficar com 4,2 mm² a mais: era papel fabricado pela normalização (não pelo Tiago) e criava uma suspeita nova em P0046; corrigido (`GANHO_MIN_MM2`, fixado depois de ver o caso) e refeito. Na cópia: reprodução das gémeas do R7 **34/43 → 43/43**, `fetch.json` idêntico antes/depois; Suspeitas iguais às de antes da ronda.
- **Contorno sugerido pela gémea [V]:** faixa no editor quando a gémea tem contorno manual (convenção do índice) e a peça não. Medido em 268 pares colocados: distância mediana 0,13 mm (p95 0,24); 20 pares E-sym 0,13 mm. Os únicos 6 pares acima de 0,6 mm são o corte c32|c33. Pares com contorno manual dos dois lados: nenhum ainda [NT uso real].
- **Achado lateral:** esta máquina não tinha `pieces/*.npz` das folhas S0028–S0037 (lotes 4–8, 375 peças). A lista da ronda 8 (lote 9) foi calculada aqui sem essas formas; refeita agora: +3 gémeas (P0164 (33,3), P1109 (33,4), P1200 (5,48)), +1 par T0007 (P1279 + P1361), +1 candidata suprimida.
- **Testes:** suite completa **451 passed, 1 failed, 1 skipped** (377 s); a falha é a pré-existente `test_gui_guardadas` (fixture, ver «Espera»). Depois da última mudança no `strokes.py`: `test_strokes`, `test_server -k contorno`, `test_gui_contorno`, `test_overrides` verdes.
- **Interpretador:** venv4 (`…/f748cb5c-…/scratchpad/venv4/Scripts/python.exe`, `PYTHONIOENCODING=utf-8`). Cópias: `scratchpad/alpes_r9` (medições), `alpes_pre` (estado antes da ronda).
- **Reports:** 0 abertos (R0029–R0034 já fechados); nenhum tocado.

## O que o Tiago tem de ver na GUI
1. **Arrancar o servidor depois do `git pull`**: o portátil refaz os ativos das 17 peças (16 voltam ao automático). Esperado: 0 avisos de invariantes.
2. **Editor numa peça qualquer, sem traços**: a linha de estado diz «igual ao contorno atual»; um pincel «Não é peça» só sobre a linha negra da sombra fica cinzento (ignorado).
3. **Contorno sugerido pela gémea**: depois de gravares um contorno numa peça cuja gémea esteja colocada, abre o editor na gémea: aparece a faixa «Contorno sugerido pela gémea P####» com «Usar como ponto de partida» / «Ignorar».
4. **«Vai buscar»**: pesquisa `P1200`, `P0164`, `P1109` (gémeas novas) e `P1279` (par T0007).

## Espera pelo Tiago (decisões que são dele)
1. **Teste `test_gui_guardadas::test_real_board_cells_without_orthogonal_neighbour_are_not_in_vai_buscar`**: falha porque a fixture lê o `fetch.json` vivo contra um log cortado em 2045 eventos; não tem nada a ver com contornos. Corrigir a fixture (fixar o `fetch.json` ao mesmo corte) altera o teste: autorizas?
2. Anteriores (ronda 8): PDF vetorial (PyMuPDF), lock entre processos, pares T0001/T0002/T0005, e os da ronda 7 (`ambigua` em «Vai buscar», p90 por zona, T0003/T0004, `docs/README_proposta.md`, P0343/P0833, c32|c33).

## Pendentes técnicos (por ordem)
1. **Verificar ativos ao arrancar qualquer ferramenta, não só o servidor:** a consulta CLI nesta máquina correu uma ronda inteira sem as formas de 375 peças. `rebuild_stale` existe; falta chamá-lo (ou avisar) em `src.query`/`src.ingest`.
2. **Convenção [NT]:** traços humanos novos com a regra nova; peças de duas cores (δ escalar das zonas ganhas é a mediana); material escuro e neutro na aresta (montanha) pode ter um «não é peça» legítimo ignorado.
3. `overrides.append_override` escreve CRLF no Windows (o git normaliza; a leitura aceita os dois).
4. Anteriores: passo «pares» N², arranque a frio, fila, GT fora do céu, pose manual 4–9 s, falso alarme, PNG, detetor de peça comida, (26,1)/(25,1).

## Convenções que mordem
- Nunca `taskkill //IM python.exe`: só por PID, listado e justificado. Nesta ronda dois subagentes deixaram `python -` à espera de stdin; terminados por PID.
- Heredocs com aspas no Bash falham: patches em ficheiros `.py`; `PYTHONIOENCODING=utf-8`; `python -u`.
- Nunca correr servidor/render/ingest sobre `projects/alpes` para medir: cópias. As escritas reais desta ronda (refazer ativos, renormalização, consulta) foram feitas com o servidor parado e commit a seguir.
- `tools/diagnostico/**` precisam de `PPF_SCRATCH`. Commits em português, sem co-author. Suite completa > 300 s: em segundo plano.
- **`rebuild_assets(force_scans=[sid])` sem `scans=[sid]` percorre todas as folhas** (e re-segmenta as que faltam): passar os dois.

## Links
- Ronda 9: `docs/diagnostico/editor/CONVENCAO.md` (+ `convencao.json`, `CONVENCAO_17.jpg`, `RENORM_17.jpg`, `renormalizar.json`, `gemea_sugestao.json`), `docs/decisoes.md` (2026-11-09), `docs/gui-design.md` §18.6b–c, ferramentas `tools/diagnostico/editor/{convencao,renormalizar,gemea_sugestao}.py`.
- Ronda 8: `docs/diagnostico/servidor/REPOUSO.md`. Ronda 7: `docs/diagnostico/gemeos/R7_RESULTADOS.md`.
- Comandos: `python -m src.reports --project projects/alpes --list`; `python -m src.consistency --project projects/alpes`; `python -m src.overrides --project projects/alpes --pares`; `python tools/rebuild_scans.py --project projects/alpes --stale --also-missing`.
