# Plano M10 (`src/twin.py`) + mínimo do M12 (`src/state.py`) — para o E-real-3 com lotes de 32 ao acaso

Escrito em 2026-10-31 a pedido do Tiago (ponto 6 da revisão de `9dfdb61`/`3e79b6a`). É só plano: nenhum código deste documento existe ainda. Fontes: `docs/estado-e-plano.md` §0, §6, §7, §10, §11; `docs/diagnostico/gemeos/{RESULTADOS,EREAL,EREAL2}.md`; `docs/diagnostico/ocupacao/OCUPACAO.md` (M14); skill `piece-fit-matching`.

## 0. Objetivo e critério de saída

**Objetivo:** o Tiago despeja um saco numerado (lote N, ≈ 32 peças ao acaso) no scanner, corre um comando e recebe a lista "vai buscar ao lote N, peça X → célula (l, c)" com a imagem de cada peça; coloca, confirma, e a lista regenera-se. Tudo o que o E-real-2 fez à mão (`tools/diagnostico/gemeos/ereal2.py`) passa a código de produto com estado persistente.

**Critério de saída (E-real-3):** 3 lotes de 32 ao acaso, protocolo scan → lista → confirmação do Tiago → log. Métricas (§6 do plano; sem recall, porque não se sabe quantas gémeas há no lote):
- precisão das propostas confirmadas (meta ≥ 90 %; E-real-2: 2/2);
- nº de peças colocadas por lote e por origem (gémea colocada / par de soltas / buraco);
- rejeições corretas: propostas que o Tiago recusa devem ser < 10 %; "sem gémeo" que depois se revelam gémeas (quando a peça acaba colocada por outra via) reportadas como falsos negativos conhecidos;
- tempo por lote (scan → lista) ≤ 2 min numa memória de ≤ 600 soltas;
- `board.json == replay(log.jsonl)` em todos os passos.

## 1. `src/shape.py` — o mínimo do M4 de que o `twin.py` precisa

Promoção de `tools/diagnostico/forma/shapelib.py` e `dist.py` (protótipos validados no E-sym, 20/20) para módulo puro (sem Tkinter nem I/O), tabs, `__all__`, docstrings.

| Função | Origem | Contrato |
|---|---|---|
| `analyse(contour_px, mm_per_px) -> Shape` | `shapelib.analyse_v2` | cantos v2, 4 lados `{tipo ∈ F/T/B, corda_mm, perfil (64 pontos normalizados)}`, `cls` canónica sob rotação (`shapelib.canon`), vetor de forma para a métrica free (`esym.free_vec`), `ok` (4 cantos encontrados), `n_F` |
| `free_dist(a, b) -> (d_mm, shift, phi)` | `dist.free_dist` | invariante a rotação e ponto de partida; `phi` alinha `b` a `a` (sinal confirmado pelo resíduo ao eixo do corpo, EREAL2 §3) |
| `corner_dist(a, b) -> (d_mm, best_k, R)` | `shapelib.shape_dist` | Kabsch sobre os 4 deslocamentos cíclicos; `best_k` alinha os lados |
| `side_tolerance(a, b, k, mode) -> bool` | `ereal2.chord_matrix` | filtro de cordas por lado homólogo; modo `tipo` (2 mm nos lados F e adjacentes a F, 1 mm nos restantes) se o §8 do EREAL2 o confirmar com 0 falsos positivos |
| `mm_per_px(dpi)` | — | 25,4 / dpi; **nunca** px/cm da GUI |
| `side_complement(a, b)` | `cortes.neg_inv` | perfil complementar tab↔blank (invertido e negado) de dois lados, para o RMS do encaixe |
| `transform_contour(shape, T)` | — | fantasma da gémea: contorno transformado (rotação/simetria do perfil) a partir do perfil, para o teste 1-contra-1 |

Testes: sintéticos (par tab/blank gerado = melhor custo, F rejeitado, cordas fora de tolerância rejeitadas) e `tests/test_segment_scan_esym.py` passa a usar `src.shape` em vez do `shapelib` de `tools/`. `src/edges.py` fica obsoleto (a GUI deixa de o chamar) e é removido quando `shape.py` entrar.

## 2. `src/twin.py` — M10

### 2.1 API

```python
find_twin(query, index, profile, art, *, modality, calibration) -> dict
# {'candidates': [{'piece_id', 'd1_mm', 'phi', 'image': {'dE', 'ncc', 'pctl'}}, ... top-3],
#  'decision': 'aceite' | 'ambigua' | 'sem', 'margin': d2/d1, 'twin_cell': (l, c) | None,
#  'reasons': [...]}            # ou {'error': str}
pair_locate(a, b, art, profile, *, rotations=4) -> dict
# {'cells': [{'cell': (l, c), 'score', 'rank'}, ... top-3], 'n_cells_tested'}
```
- `query`: uma `Piece` do índice (solta nova) **ou** uma célula ocupada com silhueta conhecida (peça `colocada` que passou pelo scanner; regra de produto) **ou**, só para legado de céu, uma célula de linha de corte (`modality='celula'`).
- `profile.symmetry(l, c)` dá a célula gémea; **nunca** `(48 − l, 65 − c)` no código (§11).
- `index`: as peças `solta` e `emparelhada` do projeto, com vetores pré-calculados (O(N) por consulta, N ≤ 3008).

### 2.2 Pipeline (ordem = custo crescente; todas as constantes nomeadas)
1. **Classe**: `cls` igual (canónica sob rotação).
2. **Cordas** por lado homólogo (modo `tipo`, §1).
3. **Forma**: `free_dist` → d₁, d₂, margem d₂/d₁.
4. **Decisão de forma por modalidade** (tabela `calibration.json` no perfil; valores iniciais do E-sym e do E-real):

| Modalidade | t₉₅ (aceite) | t_max (ambígua) | Correção geométrica | Evidência |
|---|---|---|---|---|
| `silhueta↔silhueta` (as duas pelo `segment_scan`) | 0,507 mm | 0,637 mm | nenhuma | E-sym híbrido/scan, 20/20; E-real-2 0 FP em 10 472 pares |
| `celula↔silhueta` (célula de linha de corte vs solta) | a calibrar | a calibrar | encolher a silhueta pelo desvio isotrópico (+0,48 mm; leave-one-out 9/25 → 3/25) | EREAL.md c1_loo |

   `aceite` se d₁ ≤ t₉₅ e margem ≥ 1,5; `ambigua` se d₁ ≤ t_max; senão `sem`. Com um único candidato a passar os filtros, a margem é indefinida → **`sem`, não proposta** (decisão do Tiago, 2026-11-01; antes era «no máximo `ambigua`», caso f1p1 #6): `find_twin` devolve `single_candidate` = `{id, d1_mm, phi_deg, chord_ok, image}` e `decision_shape` = o que a regra da margem infinita daria (`aceite` se d₁ ≤ t₉₅, senão `ambigua`), não testa a imagem, e o `query` guarda o caso em `fetch.json` → `suprimidas` (contado no rodapé do `fetch.md`) para rever mais tarde [V, `tests/test_twin.py`, `tests/test_twin_real.py`].
5. **Imagem, obrigatória**: teste 1-contra-1 contra a célula gémea da arte (recorte da candidata em Lab, orientação = orientação da consulta + `phi` + simetria do perfil, L\* corrigido pelo desvio fotométrico do perfil, máscara erodida 1 px, jitter ±2 px): ΔE médio + NCC em L\*. **É consistência, não identidade**: aceitar se ΔE ≤ p90 da distribuição da zona (perfil guarda as distribuições por zona: céu p90 ≈ 50,0, EREAL2 §3); nunca promove `sem` a `aceite`; pode despromover `aceite` a `ambigua` se ΔE > p90.
6. **Saída** com `reasons` legíveis ("classe diferente", "corda lado 3: 2,3 mm > 2,0", "ΔE 61 > p90 50").

### 2.3 Localização conjunta de um par (`pair_locate`)
Para um par `aceite` entre duas soltas: varrer as células (l, c) compatíveis (classe/borda das duas) com score ΔE(A, (l, c)) + ΔE(B, simetria(l, c)), 4 rotações globais; devolver top-3 com rank. Medido no E-real-2 com n = 20 pares E-sym (mediana 26/3008; 4/214 nas células de borda) e n = 1–2 pares reais (GT em 1.º entre 2790 interiores). Serve para **sugerir**, não para colocar: a colocação de um par exige confirmação do Tiago ou uma vizinha montada.

### 2.4 Testes
- Sintéticos: gémeo gerado por rotação de 180° de um contorno sintético com ruído ≤ 0,2 mm → `aceite`; o mesmo com um lado alterado 1 mm → `sem`; simetria fornecida por um perfil falso (ex. translação) para provar que nada está fixo no código.
- `slow`: E-sym 20/20 em ambas as poses (A1↔B2, A2↔B2) e 0 `aceite` nos pares negativos do E-real-2 (10 472, ou o n novo do §8 do EREAL2); E-real-2 reproduz as 2 propostas confirmadas.

## 3. `src/state.py` — o mínimo do M12

### 3.1 Entidades (ficheiros em `projects/<id>/`)
- `puzzle.json` (perfil, §11): grelha, célula nominal, simetria, fundo Lab, dpi, arte (ficheiro + bbox do M2 ou bbox fixa inicial), `calibration` (§2.2), distribuições de ΔE por zona.
- `project.json`: id, datas, `schema_version`.
- `scans/S0001.json` + `pieces/S0001.npz`: caminho relativo + sha256, dpi, **`lote`** (= número do saco), tipo ∈ {`soltas`, `bloco_relva`}, método/versão de segmentação, lista de peças.
- **Peça** `P0001`: scan, índice, `lote`, `n_no_lote` (numeração `grid_order`, a mesma das folhas de propostas), contorno px e mm, bbox, recorte RGBA, `Shape` (§1), assinatura Lab, flags `touches_frame`/`touches_strip`, **estado** ∈ {`solta`, `emparelhada`, `posicao_conhecida`, `colocada`, `em_seccao`, `descartada`}, `celula` se colocada ou com posição conhecida, `same_as`.
- **Par** `T0001`: A, B, d₁, margem, imagem, células candidatas conjuntas.
- **Secção legada** (página `montado_pNN`): células locais vindas da vista explodida; ancoragem automática quando a confiança é alta (lados F + gémeas entre páginas + arte), senão fica por ancorar e pergunta-se ao Tiago.
- **Mapa** `board.json`: 47 × 64 de `{estado ∈ vazia | ocupada_legado | colocada, peca_id | null, fonte ∈ log | foto, foto_id}`; derivados em memória: gémeas pendentes, buracos, células de `posicao_conhecida` à espera de vizinha.
- **Foto** `photos/F0001.json`: ficheiro, sha256, data, homografia, residual, mapa 47 × 64 de 1/0/−1 (saída do M14).
- `log.jsonl` (só acrescentar): ações do §10 (`placed`, `unplaced`, `twin_confirmed/rejected`, `hole_confirmed/rejected`, `pair_registered/rejected`, `fetch_listed`, `section_*`, `piece_discarded`) + `photo_registered`, `cell_occupied_by_photo`, `cell_cleared_by_photo`, `position_known`, `position_placeable`.
- Invariantes testadas: `board == replay(log)`; célula com ≤ 1 peça; `colocada` ↔ exatamente uma célula; simetria só via perfil; ids nunca reutilizados.

### 3.2 Comandos (CLI primeiro; GUI M8 depois)
- `python -m src.ingest <scan.jpg> --lote N` — soltas ao acaso: `segment_scan`, `shape.analyse`, cria peças `solta`, numera por `grid_order`, grava recortes; devolve o overlay numerado (a folha que o Tiago guarda com o saco).
- `python -m src.ingest <página.jpg> --montado pNN | --blocos pNN` — página do legado em vista explodida (`src/legacy.py`): estrutura da grelha → células locais → registo contra a arte + lados F + gémeas entre páginas; ancoragem automática se a confiança for alta, senão a secção fica por ancorar e pergunta-se ao Tiago. Células ancoradas passam de `ocupada_legado` (foto) a `colocada` com silhueta.
- `python -m src.photo <foto.jpg>` — mapa de ocupação (M14) e **reconciliação**: `colocada` no log mas vazia na foto → aviso; ocupada na foto sem log → `ocupada_legado`; `posicao_conhecida` com vizinha agora ocupada → `position_placeable` e entra na lista.
- `python -m src.query [--lote N]` — reavalia a memória pela ordem do §0: (1) gémea já colocada (silhueta conhecida) → `find_twin` sobre as soltas; (2) pares entre soltas + `pair_locate`; (3) buracos/fronteira (M11/M6, quando existirem); (4) caixa só com textura; (5) resto fica. Escreve `fetch.md` + imagem por lote ("lote N, peça X → (l, c), origem, confiança") e regista `fetch_listed`.
- `python -m src.confirm P0123 --cell 2 61 | --reject | --position-known 5 60` — grava no log, atualiza o mapa, **re-executa `query` só nas células e peças afetadas** (a gémea da célula agora ocupada; vizinhas das células novas).

### 3.3 Reutilização
`segment_scan` (feito), `ereal.loose_pieces`/`segcache.grid_order` (grelha e numeração), `ereal2.{de_cell, cell_scores, joint_locate, build_memory}` (imagem e pares), `ocupacao.py` (M14), `shapelib`/`dist` (§1). Nada do `matching.py` antigo entra no fluxo das gémeas.

## 4. Sequência, esforço, dependências

| Passo | O quê | Quem | Esforço | Depende de |
|---|---|---|---|---|
| 1 | `src/shape.py` + testes sintéticos + E-sym a usar `src.shape` | implementer | 1 sessão | — |
| 2 | `src/twin.py` (`find_twin`, `pair_locate`, calibração por modalidade) + testes `slow` E-sym/E-real-2 | implementer | 1–2 sessões | 1; modo de cordas do EREAL2 §8 |
| 3 | `src/state.py` + `ingest`/`photo`/`query`/`confirm` + round-trip do log; perfil `puzzle.json` (M13 entra aqui) | implementer (modelo e invariantes) + helper (CLI, ficheiros, fichas) | 1–2 sessões | 2; M14 para `photo` |
| 4 | Páginas do legado localizadas e ingeridas (`src/legacy.py`) | implementer + Tiago (confirma overlays) | 1–2 sessões | 3 |
| 5 | **E-real-3**: 3 lotes de 32 ao acaso; relatório `docs/diagnostico/gemeos/EREAL3.md` | Tiago + implementer | 1 sessão | 3 (4 aumenta o rendimento mas não bloqueia) |

Não precisa do planner (Fable): o caminho está traçado pelos diagnósticos; só se escala se a calibração `celula↔silhueta` ou a reconciliação por foto levantarem uma decisão de arquitetura nova.

## 5. Riscos e decisões já tomadas
- **Imagem fraca no céu** (EREAL2 §3: célula certa em 1.º só 3/20): a imagem não promove; aceitar só com forma `aceite` (margem ≥ 1,5) e ΔE ≤ p90. Peças de céu sem gémea colocada ficam na memória até a relva legada ser digitalizada (passo 4).
- **Renumeração entre scans**: ids `P0001` estáveis; o `n_no_lote` é só para o Tiago; as confirmações referem o id.
- **Legado não digitalizado**: bloqueia apenas as gémeas da relva (as que mais interessam ao céu); o fluxo (2)–(5) funciona sem ele. Estimativa: P(peça solta ao acaso tem a gémea colocada) = |células colocadas cuja célula gémea está vazia| / |peças por colocar|; provisório pelas contagens do legado (`images/pieces/legado/README.md`): ≤ 416 / (3008 − 633) = ≤ 17,5 % ≈ 1 em 6 [NT, majorante (majorante; medido depois da ingestão de 2026-11-01: 104 / 2413 = 4,3 % ≈ 1 em 23 [V]); o valor exato sai do `query` depois da ingestão do legado]. Segunda via: pares entre soltas, esperado ≈ M(M−1)/2 / 3007 (M = 200 → ≈ 6,6 pares). A estimativa «~1 em 4» era otimista.
- **Modalidade `celula↔silhueta`**: só para secções de céu legadas (regra de produto); calibração com o E-real (25 pares) — se não chegar a 20/20 fora da amostra, fica `ambigua` por omissão.
- **Dois scans da mesma peça** (`same_as`): detetar por forma (d < ruído de re-scan 0,27 mm) e perguntar; não fundir em silêncio.
