# GUI "mesa de montagem" (interface web local)

Servidor FastAPI fino sobre `src/state.py` + página estática sem build (`src/web/`). Desenho, decisões e o que falta: [`docs/gui-design.md`](../gui-design.md).

## Como correr

```
pip install -r requirements.txt
python -m src.server --project projects/alpes            # só neste PC: http://127.0.0.1:8765
python -m src.server --project projects/alpes --lan      # telemóvel na mesma Wi-Fi: http://<ip-do-pc>:8765
```

- `--lan` escuta em `0.0.0.0` e escreve o endereço na consola. **Sem login**: qualquer pessoa nessa rede vê e altera o projeto. O firewall do Windows pode pedir autorização para a porta.
- `--port N` muda a porta; `--no-image` faz as reconsultas sem desempate pela imagem (mais rápidas); `--no-prepare` não regenera recursos no arranque; `--uploads DIR` muda a pasta dos scans importados (por omissão `images/pieces/lotes/`).
- **Arranque num PC novo**: `pieces/`, `crops/`, `overlays/` e `render/` não estão no git. Se faltarem (ou estiverem vazias), o servidor corre `render.rebuild_assets` numa thread (segmentação dos scans do log, recortes, folhas numeradas, limpeza, registo) com progresso na consola e na página "A preparar o projeto"; a página abre sozinha quando acaba. Precisa dos scans em `images/pieces/` (que estão no git).
- Escritas (Coloquei / Não encaixa / Guardar posição / Ancorar / Desancorar / Descartar / Desfazer) passam por `src/confirm.py` e `Project`, sob um lock; o log continua a ser a fonte de verdade (`board == replay(log)`). Se o `log.jsonl` mudar por fora (CLI), o servidor reabre o projeto no pedido seguinte.

## Capturas (`screenshots/`)

Geradas por `python tools/gui/screenshot.py` (Chromium headless; `pip install -r requirements-dev.txt` e `python -m playwright install chromium`) sobre uma **cópia** de `projects/alpes` (`$PPF_SCRATCH/g_alpes`), estado de 2026-11-01: 575 colocadas, 18 propostas, 51 grupos por ancorar. Cada ficheiro ≤ 300 KB (PNG, ou JPEG quando o PNG passa do limite).

| Ficheiro | Mostra |
|---|---|
| `progresso.jpg` | 1400 × 900. Tabuleiro inteiro: recortes reais limpos e registados sobre a arte a 34 %; caixas âmbar no céu (vai buscar), (1,29) a vermelho (borda em falta), (5,60) a ciano (posição conhecida), tracejado nas células cheias na foto sem silhueta, fantasmas brancos na relva (gémeas das peças de céu colocadas). Painel "Vai buscar" com o primeiro cartão; legenda em baixo. |
| `progresso_zoom_relva.jpg` | Zoom na relva (filas 42–47, colunas 1–8): o raster da região recomposto a 120 px/célula; vê-se o corte real das peças e as juntas. |
| `progresso_zoom_ceu.jpg` | Zoom no céu (filas 1–6, colunas 5–24; a vista cobre mais filas por causa da proporção do ecrã): peças de céu colocadas, células tracejadas sem silhueta, grelha. |
| `celula.jpg` | Painel da célula (3, 37): o tabuleiro a 300 dpi com o fantasma e a caixa âmbar ao lado da arte da caixa, a gémea (45, 28) colocada, a proposta (saco 1, nº 7) com os botões. |
| `vai_buscar.jpg` | Filas 1–7 do céu com as 18 caixas âmbar e o 2.º cartão da lista: peça rodada como fica, fantasma, minimapa, folha do saco com a peça a âmbar, razões em linguagem simples. |
| `lotes.jpg` | Saco 1 (2 folhas, 50 peças): miniaturas das folhas e das peças com número e estado. |
| `mesa.jpg` | Grupos soltos com o top-3 de zonas; "Ver" do 1.º candidato de G0041 desenha a pegada a violeta em (43, 54). |
| `importar.jpg` | Formulário: ficheiro, nº do saco (próximo livre), dpi. |
| `telemovel_progresso.jpg` | 390 × 844: tabuleiro em cima, legenda compacta, painel como folha inferior. |
| `telemovel_vai_buscar.jpg` | 390 × 844 com a folha inferior expandida (pega no topo): cartão "Saco 1 · nº 7". |
| `desktop_{1366,1920}_{100,125,150}.jpg` | Matriz de escala do Windows (viewport CSS = largura/escala): tabuleiro + lista "Vai buscar"; legenda recolhível (aberta por omissão só com altura >= 900 px, escolha guardada em localStorage). |
| `ver_no_tabuleiro.jpg` | "Ver no tabuleiro" aproxima e destaca a célula sem sair da lista. |

Não verificado: uso real num telemóvel pela LAN (Safari/Chrome), importação de um scan real pela página (só testada com um scan sintético em `tests/test_server.py`).
