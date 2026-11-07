# HANDOFF — 2026-11-07 (ronda «pesquisa na GUI + triagem medida dos reports», fechada)

Lê isto primeiro numa sessão nova; no fim, atualiza-o e fecha o ficheiro do prompt em `docs/prompts/`.

## Estado
- **Commits desta ronda:** `783681e` (pesquisa na barra de topo + linhas de report clicáveis), `a8bb331` (triagem medida, `docs/diagnostico/reports/TRIAGEM-2026-11-07.md`), `a249ad6` (rotação das peças de moldura pelo lado F, `F_ROTATION`), `e5c44a5` (segmentação: recuperação do prado «comido», `_RECOVER_BAYS`), + o commit das docs. Antes: `0877adb` (Tiago, 2026-11-06 23:55: G0084 desancorada, G0077 em (15,59), G0075 em (15,61)).
- **Testes:** suite completa **227 passed, 1 skipped** (≈ 150 s, OpenCV 4.11, venv4); OpenCV 5.0 não corrido [NT].
- **Interpretador:** `C:/Users/Tiago/AppData/Local/Temp/claude/c--Users-Tiago-Desktop-puzzle-piece-finder/f748cb5c-95ce-4ca7-bb40-feccfde7cc64/scratchpad/venv4/Scripts/python.exe` (o `.venv` referido antes não existe; o `python` do PATH não tem numpy).
- **Projeto:** `projects/alpes` com log de 2072 eventos, 607 colocadas; **`render/placements.json` e `render/clean/` não existem localmente** (a GUI regista a pose na hora, por cantos, sem imagem). Nada foi escrito em `projects/alpes` nesta ronda.
- **Reports:** **19 abertos** (R0001–R0012, R0018–R0020, R0022–R0024, R0027); R0013–R0017 e os duplicados R0021/R0025/R0026 fechados. **Nenhum fechado nesta ronda.** R0018–R0020 são P0196 (14,64), P0198 (28,64), P0204 (36,64) (o HANDOFF anterior dizia P0234/P0233: eram alvos do RENDER §7, não reports).
- **GUI:** pesquisa na barra de topo (`P0778`/`p778`/`778`, `R0019`, `S0020`, «4,10» «4 10» «(4,10)» «l4 c10»); Enter localiza (peça colocada → gaveta da célula com zoom; «Guardadas»/«Vai buscar» → cartão realçado; solta → estado real; vazia → «vazia»; nada → «não encontrado»); linhas da aba Reports clicáveis, com miniatura e chips da peça e da célula. ≤ 900 px é uma lupa. Tudo só leitura.

## Espera pelo Tiago (decisões que são dele)
1. **Rebuild do índice** com a segmentação nova (`render.rebuild_assets` / `ingest_all.py`): só mudam as formas de P0218, P0223 e P0199 (S0009); P0218 passa a ter o lado F (BFBT). Sem isto, o tabuleiro continua a mostrar o P0218 comido (R0023).
2. **Orientação de P0083 (44,60), R0024:** pelos lados e pela imagem está rodada 90° (NCC 0,70 a +90° contra −0,02); a pose vem do `theta_deg` do log (GT BD, S0004 #18). Confirmar fisicamente e corrigir no log (não há comando; `unplace` + `place` com o θ certo, ou editar a pose com `src.confirm`).
3. **P0333 (6,22), R0010:** orientação atual impossível (N B↔B, E T↔T); −90° é compatível mas o céu não decide; pode ser outra peça. Confirmar fisicamente (gémea (42,43) vazia).
4. **Células só-foto (R0004–R0009):** hipóteses medidas (lados + imagem, identidade [NT]): coluna 55 filas 42–45 = montado_p06 #47, #6, #30, #25 (P0442, P0401, P0425, P0420; G0040/G0037/G0039/G0038, rot 180); (44,37)/(45,37) = montado_p08 #22/#27 (P0501/P0506, G0044 rot 0; a candidata atual (44,55) rot 0 é impossível pelos lados). Ancorar na Mesa («É aqui») se bater.
5. **R0002/R0003 (3,32)/(3,33):** já têm P0294/P0291 (colocadas pelo Tiago em 2026-11-05), **mas** o bloco (1..3, 32..33) da montado_p03 não casa com o bloco gémeo (45..47, 32..33) da montado_p08/G0043 (`free_dist` 2,4–3,1 mm contra 0,17–0,36 nas colunas vizinhas): um dos dois blocos está nas células erradas. Confirmar fisicamente antes de fechar.
6. **Porta §6.1:** nas 607 colocadas, 49 falham o 1,5 % nos lados iluminados (todas relva; mediana 1,12 %, p90 1,68 %, máx. 5,65 % P0462), 13 falham 2,0 %; bolsas interiores tiradas pela regra B todas ≤ 0,093 mm². Opções (TRIAGEM §4): (A) manter 1,5 % mas medir só na faixa de 0,4 mm (precisa de limite novo: mediana 9,2 % na relva); (B) subir para 2,0 % e autorizar bolsas ≤ 0,1 mm², ficando 13 a inspecionar. Nada implementado.
7. **Fechar reports** conforme a tabela de TRIAGEM §6: candidatos a fechar depois de ver na GUI (pesquisa): R0001 P0778, R0011/R0012 P0651/P0657 (dados certos; capturas de 2 de novembro, anteriores ao render atual), R0018 P0196, R0027 (resolvido pelo próprio Tiago), R0022 P0240 (agora a 0° depois do `F_ROTATION`); R0019 P0198 é limite da cor (silhueta certa, 0,44 mm da gémea), decisão do Tiago.

## Pendentes técnicos (por ordem)
1. **Instabilidade da translação por imagem** (`register_all` com imagem): aceite/rejeitada por 0,01–0,05 ΔE; com `F_ROTATION` 3 juntas pioram até 0,29 mm e buracos 67 → 68 só nessa pose (RENDER §8). Exigir ganho mínimo de score, ou não usar a pose com imagem como referência. A GUI não usa imagem.
2. **Lados F ainda inclinados > 3°:** P0655 (31,1) (degrau de orla na silhueta, lado W) e P0199 (resolve-se com o rebuild). 13 lados F com RMS da reta > 0,15 mm ficam com a rotação por cantos (lista em RENDER §8).
3. **(26,1)/(25,1) «por baixo»:** não é prioridade de profundidade [F]; é uma orla preta de sombra de ~0,5 mm no lado S de P0663 (escura, a* > −30, fora da regra do verde). Correção possível: estender a regra da orla a píxeis escuros neutros na faixa de 0,4 mm do lado da sombra, medida com a porta §6.1 (é o «passe de sombra» de RENDER §2, que come relva escura).
4. **Meias-luas verde-escuras** a 0,4–0,8 mm dentro dos encaixes (P0196, P0204): fora da faixa de 0,4 mm (RENDER §7).
5. **`_RECOVER_BAYS`:** disco de 1,1 mm fixado só neste conjunto (margem curta: 0,96 vs 1,34 mm); peças em contacto não são tratadas; prado abaixo do limiar fechado não é recuperado [NT].
6. SSE dos reports (`report_added`/`report_edited`) continua por fazer (ronda anterior).

## Convenções que mordem
- Nunca correr `tools/diagnostico/render/run_render.py` nem `verde_tabuleiro.py` sem `--project` apontado a uma cópia (o primeiro escreve `render/`, o segundo sobrepõe `docs/diagnostico/render/verde_tabuleiro.json`). `tools/diagnostico/reports/triagem_r3.py`, `tools/diagnostico/render/pose_f.py` e `tools/diagnostico/segmentacao/prado.py` só leem.
- Em `Bash`, heredocs com muitas aspas falham: escrever o script com a ferramenta Write.
- Commits em português, sem co-author. Suite completa > 120 s: em segundo plano.
- Testes sobre o Alpes real usam uma cópia (`tests/test_fetch_group_real.py`, log cortado a 2045); nada se escreve em `projects/alpes`.
- Com `F_ROTATION = True`, um `placements.json` antigo é ignorado (campo `f_rotation`): as peças registam-se na hora até se correr `register_all`.

## Links
- Triagem desta ronda: `docs/diagnostico/reports/TRIAGEM-2026-11-07.md` (+ `_tabelas.md`, `.json`, figuras); pose: `docs/diagnostico/render/RENDER.md` §8; segmentação: `docs/diagnostico/segmentacao/PRADO.md`.
- Estado e plano: `docs/estado-e-plano.md`; arquitetura: `ARCHITECTURE.md`; GUI: `docs/gui-design.md` (§12–§13 pesquisa); decisões: `docs/decisoes.md`.
- Prompt desta ronda: `docs/prompts/2026-11-07-pesquisa-gui-triagem-reports.md` (fechado).
- Reports: `python -m src.reports --project projects/alpes --list`.
