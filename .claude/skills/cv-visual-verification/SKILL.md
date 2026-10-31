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
- Tabs, `__all__`, docstrings; helpers puros separados de I/O; em erro, `{'error': str, ...}`.
- `pytest tests/` verde em OpenCV 4.11 e 5.0. Um bug novo ganha um teste sintético que falhe antes da correção.

## Relatório final de uma mudança de CV
1. O que mudou e porquê.
2. Imagens vistas (quais, e o que se observou).
3. Números antes → depois contra GT (E-sym/E-fundo/E-real conforme o caso), `pytest` nos dois OpenCV.
4. Cada afirmação etiquetada **[V]** verificado (com evidência), **[NT]** não testado ou **[F]** testado e falha; o que **não** foi verificado.
