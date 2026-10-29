---
name: cv-visual-verification
description: Como provar visualmente e com números uma mudança de visão computacional neste projeto (segmentação, classificação de bordas, matching, visualização). Usar sempre que se alterar src/segmentation.py, src/edges.py, src/matching.py, src/texture.py ou src/visualization.py, ou quando um resultado de deteção/matching parecer estranho.
---

# Verificação visual e numérica de CV (Puzzle Piece Finder)

O script não dar erro não prova nada. Uma mudança de CV só está feita quando **se viu a imagem** e **se mediu o antes/depois**.

## 1. Ver o que a segmentação fez
- `segment_pieces(photo, debug=True)` devolve `result["debug"]` com imagens PIL de diagnóstico (`background_model`, `distance_map`, `binary_mask`, `labels_overlay`, ...). Usa-as em vez de criar um pipeline de debug paralelo.
- Grava-as numa pasta **fora do repositório** (scratchpad/temp), nunca em `images/` ou `examples/`, que estão no git.
- **Abre as imagens com a ferramenta de leitura de ficheiros e olha para elas** antes de concluir: halos de sombra, peças fundidas, `is_cluster=True`, fragmentos, rotação.
- Para resultados de matching, gera a imagem anotada com `visualization.annotate_results` / `save_annotated_image` (o ponto vermelho no centro provável) e vê-a também.
- As fotos reais são `.DNG` em `images/pieces/`, abertas diretamente com PIL. A referência é `images/puzzles/PuzzleOriginal.jpeg`.

## 2. Medir com o harness, não a olho
- Mudanças no motor de matching medem-se com `python eval_matching.py` (corre a partir da raiz). Reporta a **distribuição de confiança** (`high`/`ambiguous`, de 64 peças) contra a baseline escrita no próprio ficheiro, e o estado de cada índice em `INDICES_OF_INTEREST` (39 deve ficar `high`; 51/61/36 são falsos-high de sombra que têm de continuar ambíguos; 8/25/41 vigiam-se para regressões).
- Atenção: o `SCRATCH` do harness aponta para um caminho antigo (`...Desktop-puzzle-piece-finder...`). Confirma que existe ou passa outro antes de correr.
- Constantes afinadas (`_CONF_GAP_HIGH`, `_CONF_STRUCT_HIGH`, `_TEXTURE_LAMBDA`, `_STRAIGHT_RATIO`, ...) só mudam com os números antes/depois no relatório.
- `pytest tests/` tem de ficar verde (testes sintéticos: retângulos para segmentação, quadrados para bordas, auto-recorte para matching). Um bug novo ganha um teste sintético que falhe antes da correção.

## 3. Limites aceites: não os perseguir
Ver `docs/ROADMAP.md`. As peças de céu/areia ambíguas por falta de resolução (referência 8064x6048 para 3000 peças) **não são bug**. Não gastes iterações a "subir" peças que a arte não distingue sem um ângulo novo (ex.: secções montadas como referência local).

## 4. Regras do projeto que se aplicam aqui
- `src/matching.py`, `src/segmentation.py` e o scoring de `src/features.py` são **módulos críticos**: qualquer mudança algorítmica é desenhada ou revista pelo `implementer` (ver `CLAUDE.md`, routing helper → implementer → planner; o planner é caro, último recurso).
- Indentação com **tabs**, `__all__`, docstrings; helpers puros separados de I/O.
- Em erro, as funções devolvem `{'error': str, 'count': 0, ...}` como `matching.py`: mantém o contrato.

## Relatório final de uma mudança de CV
1. O que mudou e porquê.
2. Imagens vistas (quais, e o que se observou).
3. Números: distribuição de confiança antes → depois, índices de interesse, `pytest` verde.
4. O que **não** foi verificado.
