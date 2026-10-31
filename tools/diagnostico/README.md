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
| `gemeos/segcache.py` | Corre `segment_pieces(debug=True)` + `classify_pieces` nos 4 scans dos gémeos (A1, A2, B2, B1), sem moldura desde 2026-10-31 (`PAD = 0`; S1 corrigido em `src/`; `PAD = 64` repõe a moldura antiga); guarda os `.npz`. Também é importado por `esym.py` e `cortes.py`. `--force` refaz. | `images/pieces/coluna5-24_*.jpg`, `colunas5-24_*.jpg` | `$PPF_SCRATCH/seg/gemeos_{A1,A2,B2,B1}.npz`; `docs/diagnostico/gemeos/gemeos_*__contours.jpg` |
| `gemeos/esym.py` | E-sym rigoroso: gémeos por rotação de 180° (re-scan A1/A2, gémeo A1/B2 e A2/B2, não-gémeo mais próximo, top-1, NN mútuo, por lado, topologia) com contornos `seg`, `simples`, `hibrido` e `sombra` (2026-10-31) e métricas corner e free; critério M3 (chave `esym.M3`); extrapolação da margem para 3008. Tempo ≈ 50 s. | `gemeos_*.npz` (gera-os por `segcache.py` se faltarem), `seg/scan_verde.npz` | `docs/diagnostico/gemeos/esym_*.png`, `results.json` (chave `esym`); `$PPF_SCRATCH/gemeos/esym.pkl` |
| `gemeos/cortes.py` | Cortes repetidos: ruído por lado verde↔laranja e pares de lados do mesmo tipo de peças diferentes, direto contra invertido (linha de base do acaso). Tempo ≈ 20 s. Correr depois de `esym.py`. | `seg/scan_verde.npz`, `scan_laranja.npz`, `gemeos_{A1,B2}.npz`, `esym.pkl` | `cortes_pares_mais_parecidos.png`, `results.json` (chave `cortes`) |
| `gemeos/seccao.py` | Secção montada de canto: linhas de corte (black-hat, Hessiana, histerese, watershed com prior), frente contra traseira, 300 contra 600 dpi, localização na arte (NCC em L\*) e fotometria (scan, arte, caixa). Tempo ≈ 4,5 min. Lê `PuzzleOriginal.jpeg` com `IMREAD_IGNORE_ORIENTATION` (EXIF orientation = 3). | `images/pieces/{frente,traseira}_{300,600}dpi.jpg`, `1186441_1.jpg`, `PuzzleOriginal.jpeg`, `seg/scan_verde.npz`, `gemeos_{A1,B2}.npz` | `docs/diagnostico/gemeos/seccao_*.png`, `seccao_results.json`, `seccao_celulas.json` |
| `fundo/efundo.py` | E-fundo (2026-10-31): 12 scans de julho (11 cores + impressora; os 3 a 600 dpi reamostrados a 300) × 3 métodos de contorno (`seg` = `segment_pieces`, `simples` = limiar Lab + Voronoi, `sombra` = `simples` + rejeição da sombra por tonalidade, `esym.shadow_mask`); identidade da peça pelo verde (posição ou forma), consistência free mesma/diferente pose, recall, rugosidade, corda, área; ranking pré-registado. Tempo ≈ 5 min. Correr depois de `gemeos/esym.py` (lê o critério M3). | `images/pieces/digitalização_fundo_*.jpg`, `digitalizado com impressora.jpg` | `docs/diagnostico/fundo/` (`results.json`, `fundo_*.png`, `fundo_<cor>__contours.jpg`); `$PPF_SCRATCH/seg/fundo_<cor>.npz` |
| `gemeos_quick.py` | Versão **preliminar** do utilizador (escrita no Project) da verificação dos gémeos: limiar Lab simples, sem suavização. Os seus números (0,28 / 0,34 / 0,56 mm) reproduzem-se no `esym.py`; o rigoroso é o `gemeos/esym.py`. | 3 scans (A1, A2, B) | consola |

Ordem: `segmentacao_diag.py` → `forma/run_all.py` → `forma/figs.py`; `matching/expA.py` → `expB.py` → `pairing.py` → `expC.py` → `analyze.py`. Tempo total ≈ 45 min (o matching leva ≈ 8 s por peça por referência).

Gémeos (2026-10-30): `gemeos/segcache.py` → `gemeos/esym.py` → `gemeos/cortes.py`; `gemeos/seccao.py` é independente (usa os `.npz` dos gémeos se existirem). Definir `PPF_SCRATCH` e, no Windows, `PYTHONIOENCODING=utf-8` (os scripts imprimem acentos):

```powershell
$env:PPF_SCRATCH = "C:\tmp\ppf"
$env:PYTHONIOENCODING = "utf-8"
python tools/diagnostico/gemeos/esym.py     # ≈ 50 s
python tools/diagnostico/gemeos/cortes.py   # ≈ 20 s
python tools/diagnostico/gemeos/seccao.py   # ≈ 4,5 min
```

Resultados em `docs/diagnostico/gemeos/` (`RESULTADOS.md`, `SECCAO.md`).

Os `.npz` (≈200 MB) não estão no git; regeneram-se com o primeiro script a partir dos scans que estão em `images/pieces/`.
