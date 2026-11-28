---
name: cv-visual-verification
description: Como provar visualmente e com números, contra verdade de terreno, uma mudança de visão computacional neste projeto (segmentação de scans, forma/lados, gémeos, matching). Usar sempre que se alterar src/segmentation.py, src/edges.py, src/matching.py, src/texture.py, src/visualization.py ou os futuros src/shape.py, src/fit.py, src/twin.py, ou quando um resultado de deteção/forma/gémeo parecer estranho.
---

# Verificação visual e numérica de CV (Puzzle Piece Finder)

O script não dar erro não prova nada. Uma mudança de CV só está feita quando **se viu a imagem** e **se mediu o antes/depois contra verdade de terreno**.

## 1. Ver o que a segmentação fez
- Entrada canónica: **scan flatbed a 300 dpi em papel verde** (1 px = 0,0847 mm). `segment_scan` para scans; `segment_pieces` para fotos. Ambos aceitam `debug=True` e devolvem `result["debug"]` com imagens PIL (máscara, mapa de distância, overlay de rótulos...): usa-as em vez de criar um pipeline de debug paralelo.
- DNG/telemóvel são só legado (fotos de secções grandes); não medem o objetivo atual.
- Grava as imagens numa pasta **fora do repositório** (`PPF_SCRATCH` ou temp), nunca em `images/` ou `examples/`.
- **Abre as imagens com a ferramenta de leitura e olha para elas** antes de concluir: sombra, mordidelas em peças escuras, peças fundidas (`is_cluster`), peças junto ao bordo (`touches_frame`), fragmentos.

## 2. Medir com verdade de terreno (§6 de `docs/estado-e-plano.md`), não a olho nem por `high`
- **E-sym**: teste `slow` em `tests/` (gémeo ≤ 0,5 mm e top-1 20/20); tabela completa com `tools/diagnostico/gemeos/esym.py`.
- **E-fundo** (`tools/diagnostico/fundo/efundo.py`): fundos e métodos de contorno. **E-real** (`tools/diagnostico/gemeos/ereal.py`): linhas de corte e a cadeia real (célula da secção montada → gémeo entre as soltas).
- `eval_matching.py` só serve o prior da caixa (M9).
- Rugosidade e corda são **diagnósticos, não portas**. Viés conhecido de `scan`: corda 18,6 mm contra 18,2 nominal (a sombra entra no contorno).
- Convenção de ambiente: `PPF_SCRATCH` fora do repo e dois venvs (OpenCV 4.11 e 5.0); ver `tools/diagnostico/README.md`.
- Constantes afinadas só mudam com números antes/depois no relatório.

## 3. Limites aceites: não os perseguir
- Peças de céu/nuvem sem textura não se localizam na foto da caixa (limite da arte); não gastar iterações a "subir" `high`.
- Os gémeos só se distinguem pela imagem; um teste só de forma não os separa.
- O modelo de sombra está adiado até o E-real mostrar viés; não o implementar antes.

## 4. Regras do projeto que se aplicam aqui
- `src/matching.py`, `src/segmentation.py`, o scoring de `src/features.py` e os futuros `src/shape.py`, `src/fit.py`, `src/twin.py` são **módulos críticos**: mudança algorítmica é desenhada ou revista pelo `implementer` (ver `CLAUDE.md`).
- Tabs, `__all__` (`tests/test_lint.py::test_modulos_src_com_tabs_e_all`), docstrings; helpers puros separados de I/O; em erro, `{'error': str, ...}`.
- `pytest tests/` verde em OpenCV 4.11 e 5.0. Um bug novo ganha um teste sintético que falhe antes da correção.

## Verificação (o que é automático e o que continua a ser juízo)
Antes de cada commit que toque `src/`, `tools/verify/`, `tests/golden/` ou `projects/`: `python -m tools.verify` (exit ≠ 0 = parar e reportar; nunca `--congelar-baseline` nem `--refresh-golden` para passar; regra do `CLAUDE.md`, «Conventions»). Cobre, sobre uma cópia do projeto:
- **ambiente** (passo 0, exit 2): Python do `.venv`, OpenCV fixado em `requirements.txt` (só a 4.11; a 5.0 continua manual), `core.hooksPath`;
- **golden** (exit 3): scans e linhas do manifesto `tests/golden/manifesto.json` inalterados (`tests/test_verify.py::test_golden_*`);
- **vigilância** (exit 6): `pieces`/`overlays` contra `scans/` no início e no fim (`tests/test_verify.py::test_vigilancia_conta_contra_scans`);
- **regras absolutas** (exit 4, 0 violações): `estado`, `mesma_celula`, `borda_completa`, `f_por_celula`, `grupos_sobrepostos`, `manual_indice_da_linha`, `manual_aresta_no_indice`, `manual_indice_na_banda` (`tests/test_invariantes_projeto.py`, um teste por regra e um caso que a viola);
- **métricas das peças do golden** contra `tests/golden/baseline.json` (exit 5, as outras métricas): classe F/T/B igual, cordas |Δ| ≤ 0,3 mm, célula das peças de borda, nenhum par gémeo novo acima de `TWIN_LOCAL_MAX_MM`, nenhuma suspeita nova (`tests/test_verify.py::test_comparar_*`).
- **passos 1–3** (exit 7, regressões de CV; 2026-11-26, código 7 desde 2026-11-28): segmentação de novo das 31 folhas do golden (n.º de peças, IoU e `d_max` contra o contorno guardado; sem as peças de contorno manual), classificação (`cls`, cordas ±0,3 mm, F por célula), E-sym (≤ 0,5 mm, 20/20 nas 3 direções), E-real-2 (0 `aceite` em negativos), quadrados 2×2 (40/40 ligações melhor-mútuas) e molde em leave-one-out; imagens de prova das piores peças em `<out>/prova/` (abre-as) (`tools/verify/regressao.py`, `tests/test_verify_regressao.py`). `--rapido` (E-sym + 3 folhas + E-real-2 + quadrados, ≈ 1 min) no pre-commit; o completo (≈ 5,5 min) quando o stage toca `segmentation.py`, `shape.py`, `fit.py` ou `twin.py`.

Testes que cobrem as regras desta skill (correr com `.venv/Scripts/python.exe -m pytest tests/`):
- E-sym com o contorno de `segment_scan` (gémeo ≤ 0,5 mm, top-1 20/20): `tests/test_segment_scan_esym.py::test_twins_by_free_shape` e `::test_counts_and_grid` (`slow`); E-sym e E-real-2 na cadeia `find_twin`: `tests/test_twin_real.py::test_esym_find_twin`, `::test_ereal2_find_twin`;
- peça junto ao bordo do scan e à tira branca mantida (S1, S3): `tests/test_segmentation.py::test_piece_near_frame_is_kept`, `::test_piece_touching_white_scan_strip_is_kept`;
- simetria dos pares gémeos colocados: `tests/test_simetria.py::test_simetria_dos_pares_colocados`;
- lint (`tests/test_lint.py`): módulos de `src/` com tabs e `__all__`, regra da gémea só no perfil, nenhuma espera fixa nova nos testes.

Continua a ser **juízo visual** (nenhum teste o substitui): abrir e olhar as imagens de debug (sombra, mordidelas, peças fundidas, fragmentos, orla verde); decidir se uma diferença de contorno é melhor ou pior quando a métrica não a vê (um RMS global esconde uma mordida local); E-fundo/E-real fora dos testes; mudar uma constante afinada (números antes/depois no relatório); a OpenCV 5.0; o teste sintético que um bug novo tem de ganhar.

## Relatório final de uma mudança de CV
1. O que mudou e porquê.
2. Imagens vistas (quais, e o que se observou).
3. Números antes → depois contra GT (E-sym/E-fundo/E-real conforme o caso), `pytest` nos dois OpenCV.
4. Cada afirmação etiquetada **[V]** verificado (com evidência), **[NT]** não testado ou **[F]** testado e falha; o que **não** foi verificado.
