# Teste intermitente: resumo (2026-11-24)

Comando: `.venv/Scripts/python.exe -m pytest <alvos> -x --tb=short -p no:cacheprovider -rf`, saída completa em cada ficheiro; corridas em série pelo `_loop.sh`.

## Lote 1: tests/test_gui_novo*.py + tests/test_gui_layout.py (218 testes)

| corrida | resultado | teste que falhou | duração |
|---|---|---|---|
| corrida_01 | 218 passed, 2 warnings in 381.57s (0:06:21) (rc=0) | nenhum | 382s |
| corrida_02 | 218 passed, 2 warnings in 386.81s (0:06:26) (rc=0) | nenhum | 387s |
| corrida_03 | 218 passed, 2 warnings in 378.89s (0:06:18) (rc=0) | nenhum | 380s |
| corrida_04 | 218 passed, 2 warnings in 377.44s (0:06:17) (rc=0) | nenhum | 378s |
| corrida_05 | 218 passed, 2 warnings in 378.23s (0:06:18) (rc=0) | nenhum | 379s |
| corrida_06 | 218 passed, 2 warnings in 387.50s (0:06:27) (rc=0) | nenhum | 388s |
| corrida_07 | 218 passed, 2 warnings in 376.46s (0:06:16) (rc=0) | nenhum | 377s |
| corrida_08 | 218 passed, 2 warnings in 387.51s (0:06:27) (rc=0) | nenhum | 388s |
| corrida_09 | 218 passed, 2 warnings in 377.91s (0:06:17) (rc=0) | nenhum | 378s |
| corrida_10 | 218 passed, 2 warnings in 380.73s (0:06:20) (rc=0) | nenhum | 382s |

## Lote 2: só tests/test_gui_layout.py (32 testes)

| corrida | resultado | teste que falhou | duração |
|---|---|---|---|
| layout_01 | 32 passed in 34.85s (rc=0) | nenhum | 35s |
| layout_02 | 32 passed in 36.31s (rc=0) | nenhum | 37s |
| layout_03 | 32 passed in 36.22s (rc=0) | nenhum | 37s |
| layout_04 | 32 passed in 34.71s (rc=0) | nenhum | 35s |
| layout_05 | 32 passed in 35.14s (rc=0) | nenhum | 36s |
| layout_06 | 32 passed in 35.29s (rc=0) | nenhum | 36s |
| layout_07 | 32 passed in 35.09s (rc=0) | nenhum | 36s |
| layout_08 | 32 passed in 35.15s (rc=0) | nenhum | 35s |
| layout_09 | 32 passed in 35.13s (rc=0) | nenhum | 36s |
| layout_10 | 32 passed in 35.04s (rc=0) | nenhum | 36s |

Conclusão: 0 falhas em 20 corridas (10 x 218 + 10 x 32 testes). A falha não se reproduziu; causa não provada.
