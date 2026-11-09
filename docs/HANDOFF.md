# HANDOFF — 2026-11-09 (ronda 10: contorno = só a peça — aresta oficial, índice derivado (A2); fechada)

Lê isto primeiro numa sessão nova; no fim, atualiza-o e fecha o ficheiro do prompt em `docs/prompts/`.

## Estado
- **Commits desta ronda** (em `main`):
  - `91ef246`: fixture de `test_gui_guardadas` (o `fetch.json` fica fixo em `bc6b772`; teste alterado, asserções iguais);
  - `ac6e495`: CLAUDE.md (início de sessão: `estado-e-plano.md` + `ARCHITECTURE.md` + este ficheiro);
  - `85b5b8d`: código A2;
  - `2cd321e`: ferramentas `reaplicar_aresta.py` e `convencao.py --lados/--gt`;
  - `b23d449`: estado de hoje do Tiago (OK 1);
  - `bb281d9` e `0ede00c`: limiares [NT] em `decisoes.md`;
  - `03e3af5` e `d583411`: regra única bit a bit;
  - `d865e29`: **dados do projeto real** (OK 2);
  - docs de fecho.

  Prompt: `docs/prompts/2026-11-09-r10-aresta-oficial-indice-derivado.md` (fechado). Relatório: `docs/diagnostico/editor/CONVENCAO.md` §6.
- **A2 [V]: o contorno que o Tiago pinta é só a peça.**
  - Cada linha `convencao: "aresta+indice"` de `overrides.jsonl` grava duas silhuetas:
    - `aresta_px`: a aresta pintada, com todos os traços. Um «não é peça» sobre a sombra tira-a. É usada pelo desenho (miniaturas, tabuleiro, `render.aresta_rgba`) e pela sugestão pela gémea.
    - `contour_px`: a silhueta do índice, derivada com o halo de sombra da convenção. É usada pela forma, gémeas, buracos, borda e consistência; nada disto foi recalibrado.
  - Quando o índice derivado é o automático **bit a bit**, a linha diz `indice: "automatico"` e só muda o desenho: não leva `manual_override`, não gera evento e não escreve nada no log.
  - É a mesma regra exata no servidor e no `reaplicar_aresta.py` (decisão do Tiago; a tolerância de 0,5 mm saiu).
- **Projeto real (`d865e29`) [V]:** os 19 contornos por traços foram reaplicados (19 registos, 4 `piece_resegmented`, 0 erros).
  - 14 peças ficaram só com visualização.
  - P0045, P0071 e P1064 passaram a índice manual, cada uma por 1 píxel (0,08 mm).
  - P0198 e P0620 mantêm o índice que o Tiago gravou hoje (IoU 1,000).
  - P1203 foi reposto no automático.
  - `fetch.json` idêntico a `b23d449` (15/15 entradas, suprimidas iguais, tolerância 1e-6); invariantes []; Suspeitas iguais (0 / 1 / 14).
  - Na cópia: reprodução R7 43/43, medida de novo depois de aplicar.
  - Cópia de segurança antes de aplicar: `C:\Users\tiago\AppData\Local\Temp\claude\011f846714d7d8db\00645572-7017-4a80-b59a-3d5f3d9e890a\scratchpad\backup_alpes_20261109_174520` (sha256 verificados; é temporária, a reposição normal é `git revert d865e29` e refazer os ativos).
- **Testes [V]:** suite completa 460 passed, 1 skipped, 0 failed (288 s), com o código A2 antes dos dados reais. O `test_gui_guardadas` volta a passar.
- **Reports:** 0 abertos; nenhum tocado.

## O que o Tiago tem de ver na GUI (pendente [NT]: ainda não reportou nada)
1. Arrancar o servidor depois do `git pull`. Se houver reconstrução de ativos no arranque, ≈ 80 s é normal.
2. As 19 peças editadas aparecem recortadas pela aresta, sem a orla de sombra, nas miniaturas e no tabuleiro:
   - P0045, P0071, P0098, P0105, P0165, P0186, P0198, P0620, P0916;
   - P0935, P0999, P1021, P1064, P1089, P1102, P1114, P1202, P1203, P1245.
3. No editor de uma delas:
   - os traços voltam;
   - laranja = a aresta (o que se grava);
   - linha fina ciano-claro = a silhueta do índice;
   - branco tracejado = a aresta detetada sem traços;
   - gravar sem mexer diz «igual ao contorno atual».
4. O selo «contorno manual» aparece só em P0045, P0071, P0198, P0620 e P1064.
5. «Vai buscar» mostra as mesmas 15 propostas.
6. Se alguma miniatura ainda estiver antiga, recarregar a página uma vez.

## Espera pelo Tiago
1. **Máscaras do Photoshop para a fase 2:** P1203, P0045, P1245 e P0198 (P0229 opcional, só se a fase 2 avançar).
   - Onde: `docs/diagnostico/editor/gt_photoshop/P####.png`.
   - Formato: PNG com alfa = a peça, na grelha de píxeis do scan inteiro, como R0011/R0012.
   - As ferramentas estão prontas (comandos em CONVENCAO §6.6).
2. As verificações da secção anterior.
3. Anteriores (rondas 7–8):
   - PDF vetorial (PyMuPDF), lock entre processos;
   - pares T0001/T0002/T0005, T0003/T0004;
   - `ambigua` em «Vai buscar», p90 por zona;
   - `docs/README_proposta.md`, P0343/P0833, corte c32|c33.

## Pendentes técnicos (por ordem)
1. **Fase 2 (§5.4 do plano), condicional, por zona.** Medir contra as máscaras do Photoshop duas candidatas:
   - (a) o solver sem traços puro;
   - (b) S0 com deslocamento direcional nos lados W/S, estimado em leave-one-out.

   Critério por zona: desvio mediano por lado ≤ 0,3 mm, p95 ≤ 0,6 mm, IoU ≥ 0,93. **A tolerância foi fixada vendo só P0651/P0657: não está validada.** O n por zona é de 1 a 2 peças.
2. **Possível sobre-corte no lado S [NT].** Nas 19 arestas, o lado S fica 0,5–0,9 mm dentro de S0. Contra a GT de P0651/P0657, S0 só está ≈ +0,25 mm fora no lado S. Os 17 traços antigos (feitos com a instrução antiga) podem entrar 0,3–0,6 mm na peça. As máscaras do Photoshop decidem.
3. **[NT]** P0045, P0071 e P1064 ficam índice manual por 1 píxel (0,08 mm; diferenças de 0,01–0,07 mm²) e por isso saem das métricas de CV (`manual_override`). O custo não foi medido.
4. **Limiares [NT]** (`decisoes.md`, ronda 10): `GANHO_MIN_MM2` 2 mm², `GEMEA_RUIDO_MM` 0,25 mm, os 3 mm² do teste do laço.
5. Miniaturas pedidas com `?v=versão` podem ficar em cache no browser depois de uma gravação só de visualização, porque o log não muda.
6. Anteriores:
   - verificar ativos no arranque das CLI (`src.query`/`src.ingest`);
   - `append_override` escreve CRLF;
   - passo «pares» N²; arranque a frio;
   - GT fora do céu; pose manual 4–9 s; falso alarme; PNG;
   - detetor de peça comida; (26,1)/(25,1).

## Convenções que mordem
- Nunca `taskkill //IM python.exe`: só por PID, listado e justificado. Não usar `python -` com heredoc no Git Bash (fica à espera do stdin): escrever scripts `.py` no scratchpad.
- Nunca correr servidor/render/ingest sobre `projects/alpes` para medir: usar cópias, com `tools/rebuild_scans.py --stale --also-missing` antes das linhas de base. Escritas reais só com o servidor parado (verificar `netstat -ano | grep LISTEN | grep :8765` vazio e nenhum `python.exe` com `src.server`), cópia de segurança e commit a seguir.
- `rebuild_assets(force_scans=[sid])` sem `scans=[sid]` percorre todas as folhas: passar os dois.
- **Duas silhuetas:** quem lê o índice lê `contour_px` / npz, nunca `aresta_px`; `aresta_px` é só desenho e sugestão pela gémea.
- `tools/diagnostico/**` precisam de `PPF_SCRATCH`. Commits em português, sem co-author. A suite completa demora > 300 s: correr em segundo plano.

## Links
- Ronda 10:
  - relatório: `docs/diagnostico/editor/CONVENCAO.md` §6;
  - figuras e dados: `REAPLICAR_19.jpg`, `REAPLICAR_zoom_WS.jpg`, `reaplicar_aresta.json`, `lados_r10.json`;
  - decisões: `docs/decisoes.md` (2026-11-09, ronda 10);
  - GUI: `docs/gui-design.md` §18.6d;
  - ferramentas: `tools/diagnostico/editor/{reaplicar_aresta,convencao}.py`.
- Ronda 9: `CONVENCAO.md` §0–§5. Ronda 7: `docs/diagnostico/gemeos/R7_RESULTADOS.md`.
- Comandos de início de sessão: `python -m src.reports --project projects/alpes --list`; `python -m src.consistency --project projects/alpes`.
