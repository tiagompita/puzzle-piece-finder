# Maquete da GUI "mesa de montagem"

Maquete estática do desenho em `docs/gui-design.md` (§8). Páginas HTML + CSS + JS sem framework nem build; abrem com duplo clique (`file://`), sem servidor.

## Como gerar

```
python tools/gui_mock/make_mock.py --project projects/alpes --out docs/gui
```

Idempotente. Lê o estado real do projeto (`src/state.py`: peças, tabuleiro, `pending_twins()`, secções, `fetch.json` se existir) e o perfil (`puzzle.json`: grelha, `cell_mm`, `twin()`, `twin_rotation_deg()`, arte). Escreve `board.svg`, `art.jpg`, `crops/`, `groups/`, `overlays/`, `mock_data.json`, `preview.png` e substitui os marcadores `<!--BOARD-->` e `<script id="mock-data">` nos HTML (os dados ficam embutidos para funcionar offline, sem `fetch()`).

## Como abrir

Abrir `index.html` no browser. Navegação: Progresso, Vai buscar, Lotes, Mesa. `celula.html?c=l,c` é o painel da célula para telemóvel. `preview.png` é um render PIL do tabuleiro para verificação sem browser.

## O que é real e o que é maquete

- **Real:** arte, grelha 64 × 47, peças colocadas com o recorte e a posição do projeto, hachura das células `ocupada_legado`, fantasmas (contorno da peça rodado por `profile.twin_rotation_deg()` na célula `profile.twin()` vazia), progresso, lotes, grupos soltos com o top-3 de zona. Nenhuma regra do puzzle está no JS: a célula gémea e o fantasma vêm calculados.
- **Maquete:** todos os botões ("Coloquei aqui", "Coloquei", "Não encaixa", "Guardar...", "Ancorar...") não gravam nada. Se não existir `fetch.json` (ou tiver menos de 5 entradas), a lista "vai buscar" é completada com exemplos (gémeas pendentes sem peça), marcados `exemplo`.

## Limitações

- Unidade do SVG = largura de uma célula; a altura da célula é `cell_h / cell_w` (≈ 0,968) para os recortes não ficarem deformados.
- No máximo 400 peças colocadas com recorte (`MAX_PIECES`, miniaturas ≤ 48 px); acima disso as restantes aparecem só como estado. O tamanho de `docs/gui/` cresce com o nº de recortes (≈ 1,5 KB por recorte medido com 64 recortes; com 400, estimativa +0,5 MB) e o `index.html` repete o SVG e os dados: pode passar de 2 MB com o projeto cheio (não testado).
- A rotação de uma peça no tabuleiro é `theta_deg` se existir, senão a `rot` da secção ancorada (sem espelho); depende da convenção de `section_cell` (90° = sentido horário).
- JS verificado só por leitura: não havia browser nem node no ambiente de geração.
