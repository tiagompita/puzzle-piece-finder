# Scripts das experiências de diagnóstico (2026-10-29)

Copiados do scratchpad da sessão para o repositório para ficarem reproduzíveis (nota 1 da `docs/revisao.md`). Movidos para `tools/diagnostico/` no M0. Nenhum deles altera `src/`.

Pré-requisitos: `pip install Pillow opencv-python numpy` (os números do relatório foram obtidos com OpenCV 4.11, numpy 2.2, Pillow 11, Python 3.13). Correr sempre **a partir da raiz do repositório**. Os scripts escrevem ficheiros intermédios numa pasta de trabalho dada pela variável de ambiente `PPF_SCRATCH` (por omissão `./scratch`, que deve ficar fora do git):

```powershell
$env:PPF_SCRATCH = "C:\tmp\ppf"      # ou qualquer pasta fora do repo
```

| Script | O que faz | Entrada | Saída |
|---|---|---|---|
| `segmentacao_diag.py` | Corre `segment_pieces(debug=True)` + `classify_pieces` em todos os scans/fotos de `images/pieces/`; guarda overlays e `stats.json` em `docs/diagnostico/segmentacao/` e os recortes (`*.npz`: images, masks, contours, bboxes, types, …) em `$PPF_SCRATCH/seg/`. **Correr primeiro**: os outros dependem dos `.npz`. | `images/pieces/*.jpg`, `Phone Link/*.jpeg`, `IMG_2114.DNG` | `segmentacao/*__contours.jpg`, `*__labels.jpg`, `*__mask.png`, `stats.json`; `$PPF_SCRATCH/seg/*.npz` |
| `forma/shapelib.py` | Biblioteca: cantos por quadrilátero ótimo, lados normalizados, classe topológica, distâncias de forma (free/corner/Hu). | — | — |
| `forma/dist.py` | Distância "free" (FFT, cíclica + rotação) e validação por força bruta. | — | — |
| `forma/run_all.py` | Tarefas 1–4 do relatório de forma (tamanho, topologia, duplicados, repetibilidade) sobre `scan_verde` e re-scans. | `$PPF_SCRATCH/seg/*.npz` | `$PPF_SCRATCH/forma/*.json` |
| `forma/analysis.py`, `forma/extra.py`, `forma/t12.py`, `forma/noprior.py`, `forma/posgt.py` | Análises complementares: retangularidade em 278 peças, cantos sem prior, GT por posição (laranja/azul = mesmo layout que verde). | idem | json |
| `forma/figs.py` | Gera as montagens em `docs/diagnostico/forma/*.png`. | json acima | png |
| `matching/common.py` | Carregamento da referência, bbox da arte em `PuzzleOriginal.jpeg`, chamada ao motor, utilitários de crop/montagem. | — | — |
| `matching/expA.py` | Experiência A: auto-recortes sintéticos com máscaras reais, degradação, GT conhecido. | `images/puzzles/PuzzleOriginal.jpeg`, `seg/scan_verde.npz` | `$PPF_SCRATCH/diag/A_*.json` |
| `matching/expB.py` | Experiência B: 61 peças reais contra as duas referências + homografia SIFT. | idem + `1186441_1.jpg` | `diag/B_*.json` |
| `matching/pairing.py`, `matching/expC.py` | Emparelhamento laranja↔verde e experiência C (estabilidade). | `seg/scan_laranja.npz` | `diag/C_*.json` |
| `matching/analyze.py` | Tabelas finais e montagens em `docs/diagnostico/matching/`. | json acima | png + `results.json` |

Ordem: `segmentacao_diag.py` → `forma/run_all.py` → `forma/figs.py`; `matching/expA.py` → `expB.py` → `pairing.py` → `expC.py` → `analyze.py`. Tempo total ≈ 45 min (o matching leva ≈ 8 s por peça por referência).

Os `.npz` (≈200 MB) não estão no git; regeneram-se com o primeiro script a partir dos scans que estão em `images/pieces/`.
