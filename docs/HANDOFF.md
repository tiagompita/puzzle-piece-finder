# HANDOFF — 2026-11-07 (ronda 4: Reports em linha, report na peça, falso alarme, copiar PNG, «Editar posicionamento»; fechada)

Lê isto primeiro numa sessão nova; no fim, atualiza-o e fecha o ficheiro do prompt em `docs/prompts/`.

## Estado
- **Commits desta ronda** (todos em `main`, empurrados): `d0833c9` falso alarme reversível + junção suspeitas↔reports + SSE; `081c95c` GUI (report expandido na linha, report em linha na gaveta, chip «suspeita», Falso alarme, menu de contexto PNG); `6b9c8e9` pose manual (backend); `a29de9b` GUI «Editar posicionamento» (`src/web/pose.js`); o commit das docs. Ronda 3 (mesmo dia): `d0bd183`…`be51ac5` (R0011/R0012 com GT manual, ativos desatualizados, baías com tab, editor por traços).
- **Testes:** suite completa **339 passed, 1 skipped (228 s)** (OpenCV 4.11, venv4); OpenCV 5.0 [NT].
- **Interpretador:** `C:/Users/Tiago/AppData/Local/Temp/claude/c--Users-Tiago-Desktop-puzzle-piece-finder/f748cb5c-95ce-4ca7-bb40-feccfde7cc64/scratchpad/venv4/Scripts/python.exe` (`PYTHONIOENCODING=utf-8`; o `python` do PATH não tem numpy).
- **Projeto `projects/alpes`:** não foi escrito nesta ronda: log 2113 eventos, 958 peças, 613 colocadas, 205 `em_seccao`, 134 `solta`, 1 `posicao_conhecida`, 5 `descartada`; sem falsos alarmes nem poses manuais (ficam para o Tiago usar). Lista «ir buscar»: 9 propostas aceites, `p_twin_placed` 102/2395 = 4,3 %.
- **Reports: 7 abertos** (R0001, R0010, R0011, R0012, R0022, R0023, R0028). Nenhum fechado por mim. Suspeitas em `projects/alpes`: 0 impossível, 2 melhor rotação (P0833 em R0028 → aparece só na lista de reports com o chip «suspeita»; P0343), 12 recorte (bloco c32|c33, exceção por confirmar).
- **GUI nova:** aba Reports sem seta: clicar numa linha localiza e expande o report ali mesmo (ações dentro); gaveta da peça/célula com o report aberto em linha e as ações; Suspeitas: itens com report aberto saem do bloco (chip «suspeita» na linha do report), botão «Falso alarme» (nota opcional) e lista recolhida «Falsos alarmes» com «Restaurar»; clique direito numa miniatura → «Copiar imagem (PNG)» / «Guardar PNG» (só a peça, fundo transparente; copiar só em localhost/https); «⤧ Editar posicionamento» na gaveta (peça colocada): arrastar/rodar/setas/Q/E, folgas N/E/S/W e consistência ao vivo, Gravar com nota, Repor automática, chip «pose manual». `docs/gui-design.md` §12/§13/§17 revistos, §19 (PNG) e §20 (pose) novos; capturas `docs/gui/screenshots/reports_linha_*.png`, `peca_report_inline.png`, `suspeitas_falso*.png`, `ctx_menu_png.png`, `pose_*.png`.
- **Log:** 4 ações novas (`suspect_dismissed`, `suspect_restored`, `pose_set`, `pose_cleared`): um checkout anterior a `d0833c9`/`6b9c8e9` não consegue ler um log que as tenha. Na máquina da GUI: `git pull` ANTES de usar estas ações (e o arranque refaz ativos desatualizados sozinho, ronda 3).

## Espera pelo Tiago (decisões que são dele)
1. **Ver na GUI** (depois de `git pull` + arrancar o servidor): aba Reports → clicar em R0028 (P0833): expande na linha, com o chip «suspeita · melhor rotação»; gaveta de (8,2) mostra o report em linha; bloco Suspeitas sem P0833. Clique direito numa miniatura → copiar/guardar PNG. Gaveta de (1,63) → «Editar posicionamento» (P0240): ver as folgas ao vivo; gravar só se quiser (fica registado como pose manual, reversível com «Repor automática»).
2. **Falsos alarmes:** as 12 suspeitas `recorte` do bloco c32|c33 podem ser marcadas «Falso alarme» quando confirmar fisicamente o corte não simétrico; P0343 (5,20) e P0833 (8,2) continuam por confirmar.
3. **Validação do editor de contorno (ronda 3):** recortar 10–12 peças de relva variadas (ficam reservadas; `python -m src.overrides --project projects/alpes --pares`).
4. **P0844/P0879/P0852:** confirmar fisicamente o tab recuperado (ronda 3). **R0011/R0012:** fechar se as miniaturas de `P0651`/`P0657` aparecerem inteiras na máquina da GUI depois do pull. **R0023**, **R0001**: fechar?

## Pendentes técnicos (por ordem)
1. **Pose manual:** gravar/repor demoram 4–9 s (a frio 20–28 s): não decomposto; `rebuild_stale` no arranque apaga poses manuais das folhas que re-segmenta (só testado via `piece_resegmented`); a cache `render/gui/board_60.json` recompõe-se uma vez no próximo arranque; pinça com um dedo sobre a peça [NT]; Firefox/Safari/toque físico [NT].
2. **Falso alarme:** calibração da verificação com os falsos alarmes (hoje só contagem no resumo); a assinatura depende de o `k` do registo ser igual no CLI e no servidor (não comparado peça a peça).
3. **PNG:** copiar só em contexto seguro (localhost/https); `--lan` por http só «Guardar».
4. **Editor de contorno (ronda 3):** sem «remover contorno manual»; p95 do solver 0,54–0,68 mm; peças claras/traços humanos [NT].
5. **Detetor de peça comida (ronda 3):** sinal (b) sem positivo; limiares fixados em 5 positivos + 63 controlos.
6. **(26,1)/(25,1)**, lados F com reta RMS > 0,15 mm: como antes.

## Convenções que mordem
- Nunca correr `tools/diagnostico/render/run_render.py` nem `verde_tabuleiro.py` sem `--project` apontado a uma cópia; os scripts de diagnóstico só leem e agora excluem poses manuais (`manual=False`).
- `tools/rebuild_scans.py --project projects/alpes --scans S####[,…] --motivo … [--dry-run]` ou `--stale`: com o servidor parado; depois `python -m src.query --project projects/alpes` e commit de `log.jsonl`, `scans/*.json`, `fetch*`.
- Escrita no log só por `src.confirm`/`src.reports`/`src.consistency --falso-alarme`/`rebuild_scans`/o servidor (gravar contorno, pose, falso alarme, `rebuild_stale` no arranque); `ingest_all.py` refaz o log e perde as colocações do Tiago: não usar.
- Em `Bash`, heredocs com muitas aspas falham: escrever o ficheiro com a ferramenta Write e depois `cat >>`; consola cp1252: `PYTHONIOENCODING=utf-8`. Nunca `cat > "$VAR/..."` com variável por definir.
- Commits em português, sem co-author. Suite completa > 200 s: em segundo plano.

## Links
- Medições desta ronda: `docs/diagnostico/reports/FALSOS_ALARMES.md`, `docs/diagnostico/render/POSE_MANUAL.md`; decisões (assinatura do falso alarme; sem snap, métricas com `manual=False`) em `docs/decisoes.md`.
- Ronda 3: `docs/diagnostico/segmentacao/COMIDO.md`, `docs/diagnostico/editor/TRACOS.md`, `docs/diagnostico/render/RENDER.md` §4.1.
- Estado e plano: `docs/estado-e-plano.md`; arquitetura: `ARCHITECTURE.md`; GUI: `docs/gui-design.md`.
- Prompt desta ronda: `docs/prompts/2026-11-07d-reports-em-linha-falso-alarme-pose-manual.md` (fechado). Anterior: `docs/prompts/2026-11-07c-r0011-r0012-gt-editor-tracos.md`.
- Reports: `python -m src.reports --project projects/alpes --list`; suspeitas: `python -m src.consistency --project projects/alpes [--list --falsos]`.
