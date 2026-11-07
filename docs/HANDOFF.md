# HANDOFF — 2026-11-07 (ronda 3: R0011/R0012 contra a máscara manual, ativos desatualizados, baías com tab, editor por traços; fechada)

Lê isto primeiro numa sessão nova; no fim, atualiza-o e fecha o ficheiro do prompt em `docs/prompts/`.

## Estado
- **Commits desta ronda** (todos em `main`, empurrados): `d0bd183` métrica `src/maskcmp.py` + medição GT/detetor (`comido.py`, COMIDO.md) + decisões; `7eea52c` ativos desatualizados (`render.stale_assets`/`rebuild_stale`, `rebuild_scans.py --stale`, `_clean_or_crop` por mtime); `1d9824c` segmentação: baías com tab inteiro e em peças de contacto + razão `baia`; `75345f5` grau `recorte` nas Suspeitas; `bcf0b87` editor de contorno por traços (backend `src/strokes.py` + `/contorno/resolver`, GUI `src/web/editor.js`, verificação de ativos no arranque do servidor); `281d55a` Alpes: S0024/S0025 refeitas (3 `piece_resegmented`, motivo `recover_tabs`) + lista recalculada; `__C7__` docs.
- **Testes:** suite completa **310 passed, 1 skipped (205 s)** (OpenCV 4.11, venv4); OpenCV 5.0 [NT].
- **Interpretador:** `C:/Users/Tiago/AppData/Local/Temp/claude/c--Users-Tiago-Desktop-puzzle-piece-finder/f748cb5c-95ce-4ca7-bb40-feccfde7cc64/scratchpad/venv4/Scripts/python.exe` (`PYTHONIOENCODING=utf-8`; o `python` do PATH não tem numpy).
- **Projeto `projects/alpes`:** log 2113 eventos, 958 peças, **613 colocadas**, 205 `em_seccao`, 134 `solta`, 1 `posicao_conhecida`, 5 `descartada`, invariantes OK. P0844/P0879/P0852 (blocos S0024/S0025, `em_seccao`) têm agora o tab inteiro (classes BTTT/BTTT/BTBT). Lista «ir buscar»: propostas gémeas iguais às da ronda anterior, `p_twin_placed` 102/2395 = 4,3 %, buracos 61, borda em falta 1.
- **Reports: 7 abertos** (R0001, R0010, R0011, R0012, R0022, R0023, R0028); o Tiago fechou R0002–R0009 e R0024 e abriu R0028 (P0833). Nenhum fechado por mim.
- **R0011/R0012 (P0651/P0657), resolvido na forma:** contra a máscara manual do Tiago, o índice atual perde só 6,8 / 1,2 mm² e a miniatura atual tem IoU 0,928 / 0,919; a «casa com topo em picos» é a silhueta do **índice de 2026-11-01** (IoU 0,971 / 0,955 com a captura), anterior ao passo dos contactos. Causa provável: a GUI do Tiago corre em `D:\DEKSTOP\puzzle_piece_finder` (ver `projects/alpes/erro_terminal.txt`) com `pieces/`/`crops/`/`render/` git-ignorados e velhos. **Correção:** o servidor verifica e refaz ativos desatualizados no arranque (`Gui._check_stale`; mensagem no progresso; `ativos` em `GET /api/status`), e `python tools/rebuild_scans.py --stale` faz o mesmo à mão. `docs/diagnostico/segmentacao/COMIDO.md`.
- **GUI nova:** editor de contorno por traços em sobreposição de janela inteira («Editar contorno» na gaveta/painel da peça): laço/pincel/borracha (L/P/B), marcas é peça/não é peça/incerto (1/2/3, Shift/Alt), desfazer/refazer, resolução ao vivo (GrabCut Lab só croma, ~300 ms), 4 vistas (scan, máscara atual, diferença, recorte final), zoom/pan, «Afinar vértices» como retoque, gravar com nota. `docs/gui-design.md` §18; capturas `docs/gui/screenshots/contorno_tracos_*.png`. Bloco Suspeitas ganhou o grau `recorte` (hoje: as 12 peças do bloco c32|c33, marcadas como exceção por confirmar).

## Espera pelo Tiago (decisões que são dele)
1. **Na máquina onde corre a GUI (D:):** depois de `git pull`, arrancar o servidor (refaz sozinho os ativos desatualizados; espera-se «11 peças em 4 folhas … 0 eventos» na primeira vez, ~80 s) ou correr `python tools/rebuild_scans.py --stale`. **Fazer o pull ANTES de abrir a GUI com o código novo**, senão uma folha desatualizada é re-segmentada em D: e gera eventos no log de lá. Depois ver `P0651` e `P0657` na GUI: as miniaturas devem ter o tab N e os cantos; se sim, fechar R0011/R0012.
2. **P0844 (S0024 nº 11), P0879 (S0025 nº 18), P0852 (S0024 nº 19):** confirmar fisicamente que o tab recuperado existe (as peças estão nos blocos legados; GUI: pesquisar o id).
3. **Validação do editor:** recortar com o editor novo **10–12 peças de relva variadas** (3–4 por tipo: relva clara cor do papel, relva escura com sombra W/S, peças em contacto, peças com blank virado ao papel), em sacos/folhas diferentes de S0020. Esses recortes ficam **reservados como validação** (não entram na afinação) e `python -m src.overrides --project projects/alpes --pares` mede o erro automático contra eles. Dizer o que custou mais no editor.
4. **P0833 (8,2, R0028) e P0343 (5,20):** continuam na lista Suspeitas por confirmar fisicamente (−90° / 180°).
5. **R0023 (P0218):** o tab/F já está recuperado desde a ronda anterior; fechar?
6. **R0001 (P0778):** sem a língua desde `_CONTACT_TRIM`; fechar?
7. **Corte c32|c33** não simétrico: continua por confirmar fisicamente (as 12 peças aparecem em Suspeitas como exceção).

## Pendentes técnicos (por ordem)
1. **Editor:** «remover contorno manual» não existe na GUI (só gravar outro); o botão de colapsar a barra não tem atalho; peças claras/céu e traços humanos reais não medidos; p95 do solver 0,54–0,68 mm (meta 0,3 [F]): a experiência «pelar» a orla escura ficou só no script `tools/diagnostico/editor/tracos_gt.py` [NT fora das 2 peças].
2. **Detetor de peça comida:** sinal (b) (perda de exibição) sem positivo de calibração; limiares (a) 1,75 mm e (c) 1,2 mm fixados em 5 positivos + 63 controlos [NT fora].
3. **`stale_assets`:** só data/tamanho para `render/clean`; não deteta um clean mais novo feito com código de limpeza antigo. `check_invariants(disk=True)` continua sem ver ativos desatualizados (ficou em `render`, não em `state`).
4. **Moldura (R0022):** `F_TRANSLATION` desligado por decisão do Tiago; arranjo global não avança.
5. **Suspeitas em direto:** o cliente não ouve `suspeitas_changed`.
6. **(26,1)/(25,1):** orla preta de sombra no lado S de P0663; meias-luas (P0196, P0204). **Lados F com reta RMS > 0,15 mm** ficam com rotação por cantos (P0218, P0199).

## Convenções que mordem
- Nunca correr `tools/diagnostico/render/run_render.py` nem `verde_tabuleiro.py` sem `--project` apontado a uma cópia; `comido.py`, `baias.py`, `tracos_gt.py`, `moldura.py`, `pose_f.py`, `tools/diagnostico/reports/*.py` só leem.
- `tools/rebuild_scans.py --project projects/alpes --scans S####[,…] --motivo … [--dry-run]` ou `--stale`: com o servidor parado e sem outro agente a escrever no log; depois `python -m src.query --project projects/alpes` (≈ 2,5 min) e commit de `log.jsonl`, `scans/*.json`, `fetch*`.
- Escrita no log só por `src.confirm`/`src.reports`/`rebuild_scans`/o arranque do servidor (`rebuild_stale`, só quando há ativos desatualizados); `ingest_all.py` refaz o log e perde as colocações do Tiago: não usar.
- Em `Bash`, heredocs com muitas aspas falham: escrever o ficheiro com a ferramenta Write e depois `cat >>`; consola cp1252: `PYTHONIOENCODING=utf-8`.
- Commits em português, sem co-author. Suite completa > 200 s: em segundo plano.

## Links
- Medições desta ronda: `docs/diagnostico/segmentacao/COMIDO.md` (+ `COMIDO_gt.jpg`, `COMIDO_alcance.jpg`, `COMIDO_baias.jpg`, `comido_resultados.json`, `comido_antigo.npz`), `docs/diagnostico/segmentacao/PRADO.md` §8, `docs/diagnostico/render/RENDER.md` §4.1, `docs/diagnostico/editor/TRACOS.md` (+ `TRACOS_gt.jpg`, `tracos_gt.json`), `docs/diagnostico/reports/R0011_R0012.md` (nota de resolução no topo).
- Decisões: `docs/decisoes.md` (porta §6.1, moldura, P0395, c32|c33; solver do editor).
- Estado e plano: `docs/estado-e-plano.md`; arquitetura: `ARCHITECTURE.md`; GUI: `docs/gui-design.md` (§18 editor por traços).
- Prompt desta ronda: `docs/prompts/2026-11-07c-r0011-r0012-gt-editor-tracos.md` (fechado). Ronda anterior: `docs/prompts/2026-11-07b-moldura-reports-ancoras-rebuild-p0778.md`.
- Reports: `python -m src.reports --project projects/alpes --list`; suspeitas: `python -m src.consistency --project projects/alpes`.
