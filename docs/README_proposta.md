# Puzzle Piece Finder — proposta de README (rascunho para o Tiago aprovar; não substitui o README atual)

_2026-11-08. Rascunho da ronda 7 (Parte 5.4 do prompt). As fontes de verdade continuam a ser `docs/estado-e-plano.md` e `ARCHITECTURE.md`; isto é a página de entrada que falta._

## O que é

Uma ferramenta de visão por computador que ajuda a montar um puzzle físico grande (hoje: Clementoni 3000 «Os Alpes», 64 × 47 células) a partir de **digitalizações de peças soltas** num scanner de mesa. O programa mantém um índice persistente das peças (silhueta em mm, lados, classe, imagem), um mapa do tabuleiro e um histórico só-acrescentar, e devolve uma lista **«vai buscar ao saco N a peça X e põe-na em (linha, coluna)»**, com a peça desenhada no sítio. O Tiago confirma ou rejeita na GUI; cada decisão é verdade de terreno para medir o programa.

O que o distingue: o molde de corte deste puzzle é simétrico por rotação de 180° (a peça (l, c) tem o mesmo recorte que (48 − l, 65 − c)). Uma peça colocada diz, pela forma, qual é a sua gémea entre as soltas; a imagem desempata. É o sinal mais forte e o primeiro a ser usado.

## Fluxo de uso

1. **Digitalizar um saco** (≈ 30–60 peças soltas, 300 dpi, papel verde, ≥ 5 mm entre peças). `python -m src.ingest --project projects/alpes --lote N scan.jpg` segmenta, mede e numera as peças (nº no saco), e guarda os recortes.
2. **Consultar.** `python -m src.query --project projects/alpes` (ou o servidor) produz `fetch.md`/`fetch.json`: por ordem de força do sinal, (1) gémea de peça colocada, (2) borda em falta, (3) pares de gémeas entre soltas, (4) posições conhecidas, (5) secções por ancorar; o molde do buraco (M11) acrescenta sugestões `alta` em «Vai buscar» e um ranking na página «Buracos».
3. **Montar e confirmar** na GUI web (`python -m src.server --project projects/alpes`, `http://127.0.0.1:8000`): «Coloquei» / «Não encaixa» / «Reportar». Cada confirmação reavalia a memória (consulta incremental) e abre novas consultas (a gémea da peça colocada, os buracos vizinhos).
4. **Rever**: Reports, Suspeitas (orientação e recortes), Atividade (registo do servidor), editor de contorno e de pose para corrigir o índice à mão.

## Arquitetura (resumo; detalhe em `ARCHITECTURE.md`)

| camada | módulos | o que fazem |
|---|---|---|
| aquisição e forma | `src/segmentation.py`, `src/shape.py`, `src/profile.py` | silhueta de cada peça num scan (`segment_scan`), cantos/lados/classe em mm, perfil do puzzle (`projects/<id>/puzzle.json`: grelha, célula, simetria, calibrações, zonas) |
| sinais | `src/twin.py` (gémea), `src/fit.py` (molde do buraco), `src/locate.py` (imagem contra a arte), `src/border.py` (borda), `src/legacy.py` (páginas do legado) | cada sinal devolve candidatas com números e razões legíveis; nada propõe sem imagem |
| estado | `src/state.py`, `src/overrides.py`, `src/reports.py` | `log.jsonl` só-acrescentar é a verdade (`board == replay(log)`); contornos manuais; reports |
| consulta e confirmação | `src/query.py`, `src/confirm.py`, `src/consistency.py` | a lista «vai buscar», a confirmação com reconsulta incremental, as suspeitas |
| apresentação | `src/render.py`, `src/server.py` + `src/web/`, `src/activity.py` | tabuleiro desenhado por registo de cantos, GUI FastAPI, registo de atividade |
| medição | `tools/diagnostico/**`, `docs/diagnostico/**` | scripts reprodutíveis e relatórios com GT; critérios fixados antes de correr |

Regras que valem em todo o lado: nada do puzzle em código (fica no perfil); funções devolvem `{'error': ...}` em vez de lançar; toda a afirmação num relatório leva etiqueta **[V]** (verificado, com n e IC), **[NT]** (não testado) ou **[F]** (falhou).

## Como correr

```
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt            # opencv-python 4.11, numpy < 2.3, Pillow < 12; fastapi/uvicorn para a GUI
pytest tests/ -q -m "not slow"             # suite rápida; a completa demora > 200 s
python -m src.server --project projects/alpes
```

Comandos de sessão: `python -m src.reports --project projects/alpes --list`, `python -m src.consistency --project projects/alpes`, `python -m src.fit --project projects/alpes --relatorio`, `python -m src.overrides --project projects/alpes --pares`. Nunca correr o servidor nem ferramentas de render sobre `projects/alpes` para **medir**: usar uma cópia.

## Estado (2026-11-08)

- Índice: 1333 peças (672 colocadas, 205 em secção, 445 soltas); borda completa menos (1,29).
- Gémea (M10): 44 confirmações físicas, todas céu; as 2 primeiras falhas fora do céu (ronda 7) levaram à validação cruzada com o encaixe das vizinhas e às zonas no perfil.
- Molde do buraco (M11): 38 confirmações físicas (38/38 rank 1 `alta`; 37 céu, 1 montanha); n ≥ 60 e GT fora do céu por atingir.
- Por fazer: encaixe na fronteira (M6), localização de secções (M7), fotometria (M9); fotos de telemóvel como modalidade (bónus).

## Onde está o resto

`docs/HANDOFF.md` (estado da última ronda e decisões que esperam pelo Tiago), `docs/estado-e-plano.md` (plano e marcos com evidência), `docs/decisoes.md`, `docs/revisao.md`, `docs/prompts/` (um ficheiro por ronda), `docs/gui-design.md`.
