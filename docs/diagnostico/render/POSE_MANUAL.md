# Pose manual («Editar posicionamento») — backend (2026-11-07)

Parte 4 do plano. O Tiago pode dar à mão a pose de uma peça colocada (rotação e translação) quando o registo automático a desenha mal. A GUI (helper) fica por cima deste contrato.

## Modelo de pose

- A pose é a mesma de `render.register_piece`: `x_board = R(θ) (x_scan − pivô) + centro(l, c) + (dx, dy)`.
  - Unidades: mm do tabuleiro, com +y para baixo.
  - θ em graus, positivo no sentido dos ponteiros no ecrã, normalizado a (−180, 180].
  - `centro(l, c) = ((c − 0,5)·w, (l − 0,5)·h)`.
  - `pivô` = o pivô da pose que o tabuleiro mostra no momento de gravar. Na prática é `locate.body_center_mm(shape)`, a média dos 4 cantos.
- A pose fica em `Piece.pose_manual = {cell, theta_deg, dx_mm, dy_mm, pivot_mm, autor: "manual", t, nota}`.
  - Entra em `Piece.dynamic` (invariantes) e nos `scans/*.json`.
  - Não vai para `flags`, porque `piece_resegmented` reescreve-as.
  - Os `piece_added` novos não levam a chave quando ela é `None`, para não partir checkouts antigos.
- Limites: |dx| ≤ 0,5·w e |dy| ≤ 0,5·h da célula nominal (`state.POSE_MAX_FRAC`). Nos Alpes dá ±9,25 × ±8,95 mm.
- Não há encaixe automático (decisões 2026-11-07): o que o Tiago grava é o que se desenha.

## Eventos (`src/state.py`)

| evento | campos | efeito no replay |
|---|---|---|
| `pose_set` | `piece, cell, theta_deg, dx_mm, dy_mm, pivot_mm, antes: {theta_deg, dx_mm, dy_mm, method, manual}, nota, autor: "manual"` | define `pose_manual` |
| `pose_cleared` | `piece, cell, antes: {theta_deg, dx_mm, dy_mm}` | limpa |

- Também limpam a pose manual: `placed` (colocação nova), `unplaced`, `section_anchored`, `section_unanchored` e `piece_discarded`.
  - O `section_anchored` é um acréscimo meu: uma ancoragem nova é uma colocação nova.
- `piece_resegmented` também limpa, porque o pivô e o contorno mudam. Quando havia pose, o evento leva `pose_manual_limpa: true`.
  - Isto inclui as re-segmentações automáticas no arranque do servidor (`rebuild_stale`).
- Operações:
  - `Project.set_pose(pid, θ, dx, dy, *, nota, antes, pivot_mm=None)`: só para peças `colocada`, sempre na célula atual.
  - `Project.clear_pose(pid, *, antes=None)`: `StateError` se a peça não tiver pose manual.
- `check_invariants` verifica que `pose_manual` só existe em peças `colocada` e que `pose_manual.cell == celula`.
- As peças de secção ancorada estão `colocada`, por isso também aceitam pose manual.
- **Compatibilidade:** um checkout anterior a estes eventos não faz replay de um log que os tenha. É o mesmo preço de `piece_resegmented` e `suspect_dismissed`.

## Quem vê a pose manual

**Os caminhos de desenho mostram-na:**
- `render.register_piece` (`manual=True` por omissão) devolve a pose guardada:
  - `method = rotation = "manual"`, `manual: True`;
  - `corner.k` = a atribuição cíclica com a rotação de cantos mais próxima de θ, entre as 4;
  - `image`, `score` e os resíduos ficam `None`.
- `render._entry_key` acrescenta `["manual", t, θ, dx, dy]`, só quando a peça tem pose manual (as chaves das outras peças não mudam). Com isso caem as caches por chave:
  - `Gui.placements`, `board_pose`, `_susp_pl`;
  - `render.registered_theta`, `query._pose` (fantasma da gémea e pose proposta da gémea), `consistency._k_of`.
- `compose_board` volta a registar uma peça cuja entrada não concorda com a pose manual, mesmo quando recebe a entrada automática antiga.
- `_refresh_render_assets` grava a entrada manual em `placements.json` (via `_after_write`).
- `board_snapshot` passa a `(estado, peça, θ do log, pose_manual.t)`. Uma mudança só de pose recompõe a célula ± 1.
- `relax` não mexe numa entrada `method == "manual"`.
- `register_all(manual=False)` grava as entradas destas peças com a chave seguida de `"auto"`, para a GUI nunca as usar.

**As métricas excluem-na:**
- `consistency.evaluate`:
  - por omissão, os graus de orientação das peças com pose manual ficam fora dos itens e das contagens, com `n_pose_manual` no `summary`;
  - com `incluir_pose_manual=True`, são avaliadas com o `k` da pose manual;
  - os itens destas peças levam `pose_manual: true`;
  - a assinatura do falso alarme usa `Piece.pose_manual` (θ a 0,1°, dx/dy a 0,05 mm; `t` e a nota ficam fora).
- Ferramentas passadas a `manual=False`. Cada uma imprime «N peças com pose manual: medidas com a pose automática (manual=False)» (`render.manual_pose_note`):
  - `src/artreg.py` (`render_board`);
  - `tools/diagnostico/arte/artreg_figura.py`;
  - `render/moldura.py`, `pose_f.py`, `run_render.py` (`register_all`), `verde_tabuleiro.py`;
  - `reports/orientacoes.py`, `triagem_r3.py`, `triagem_r3_vazias_fit.py`;
  - `segmentacao/comido.py`, `recorte.py`.
- `verde_tabuleiro.py`, `triagem_r3.py` e `pose_f.py`, que leem `placements.json`, descartam as entradas manuais.

## Contrato da API

**`GET /api/pieces/{pid}/pose`** devolve:

```json
{"piece", "cell": [l, c], "w_mm", "h_mm", "hr": "h/w", "pivot_mm": [x, y],
 "efetiva": {"theta_deg", "dx_mm", "dy_mm", "method", "manual"},
 "automatica": {"theta_deg", "dx_mm", "dy_mm", "method"},
 "manual": {"theta_deg", "dx_mm", "dy_mm", "pivot_mm", "t", "nota"} | null,
 "limites": {"dx_max_mm", "dy_max_mm"},
 "contorno": [[x, y], ...],
 "svg": {"translate": [tx, ty], "rotate_deg", "transform"},
 "vizinhas": {"N|E|S|W": {"piece", "cell", "theta_deg", "dx_mm", "dy_mm", "manual", "contorno", "svg"} | null}}
```

- `contorno` tem no máximo 300 pontos (`POSE_CONTOUR_PTS`): `Shape.c` menos o pivô, **sem rotação**, dividido por **w nos dois eixos** (unidades de largura de célula, y para baixo).
  - Atenção: os fantasmas de `query.ghost_contour` dividem y por h. Este contorno não.
- `automatica`:
  - quando não há pose manual, é a efetiva (a de `placements.json`, que pode ter o passo de imagem);
  - quando há, é `register_piece(image=False, manual=False)`.
- 404 para peça desconhecida; 400 `{error}` se a peça não estiver colocada.

**Transformação para o SVG do tabuleiro** (viewBox em unidades de célula, x = coluna, y = fila·hr; `app.js` 81–93):

```
x_svg = (c − 0,5) + dx/w + cosθ·px − sinθ·py
y_svg = (l − 0,5)·hr + dy/w + sinθ·px + cosθ·py
<path d="contorno" transform="translate(tx ty) rotate(θ)">,  tx = c − 0,5 + dx/w,  ty = (l − 0,5)·hr + dy/w
```

- O `rotate(θ)` do SVG, com y para baixo, roda no sentido dos ponteiros, tal como `render._R`.
- O campo `svg.transform` já vem pronto para a pose efetiva de cada peça.
- Para uma pose candidata o cliente recalcula `tx`, `ty` e θ com a mesma fórmula.
- O teste `test_pose_get_contour_neighbours_and_svg` confirma que um ponto do contorno transformado assim cai em `board_contour(shape, entrada)/w` (tolerância 1e-3).
- **Exemplo (P0240 (1,63), cópia dos Alpes):**
  - w = 18,5, h = 17,9, hr = 0,96757;
  - pose efetiva θ = 88,9548°, dx = dy = 0 → `translate(62.50000 0.48378) rotate(88.9548)`;
  - com dy = −0,26 mm: ty = 0,48378 − 0,26/18,5 = 0,46973.

**`POST /api/pieces/{pid}/pose/avaliar`**, corpo `{theta_deg, dx_mm, dy_mm}`:
- Corre sem lock e não escreve nada.
- Resposta: `{juntas: {N|E|S|W: {piece, gap_mm, gap_sil_mm} | null}, pior_mm, pior_dir, consistencia: {grau: null | "melhor_rotacao" | "impossivel", falhas, texto}, ms}`.
- `juntas` vem de `render.seam_gaps` com a candidata e com as vizinhas colocadas na pose efetiva. `gap_mm` positivo é folga, negativo é sobreposição. `gap_mm` estima a linha de corte; `gap_sil_mm` é entre silhuetas.
- `consistencia` vem de `evaluate(..., pieces=[pid], dismissed={}, incluir_pose_manual=True)` com o `k` da candidata.
- 400 `{error}` com o corpo inválido ou fora dos limites; 404 para peça desconhecida.

**`POST /api/pieces/{pid}/pose`**, corpo `{theta_deg, dx_mm, dy_mm, nota?}`:
- Sob `wlock`:
  - `antes` = a pose efetiva;
  - `set_pose` (com o pivô da pose efetiva), `save`, `check_invariants(disk=True)`;
  - reconsulta incremental (`confirm._around`: a célula, a gémea e as vizinhas livres), porque a pose proposta da gémea e o fantasma dependem desta pose;
  - `_after_write` (`board_changed` / `fetch_changed` / `suspeitas_changed`, a entrada manual em `placements.json`), depois `piece_changed`.
- Resposta: `{ok, piece, antes, depois, juntas, invariantes, segundos, celulas_mudadas}`.
- Erros: 400 (não colocada, limites, corpo), 404, 409.

**`POST /api/pieces/{pid}/pose/repor`** (sem corpo):
- Corre `clear_pose` com o mesmo ciclo.
- Resposta: `{ok, piece, antes, automatica, juntas, invariantes, segundos, celulas_mudadas}`.
- 400 se a peça não tiver pose manual.

**`GET /api/pieces/{pid}`** ganha `pose_manual: {theta_deg, dx_mm, dy_mm, t, nota} | null`.

**CLI:** `python -m src.confirm P#### --pose THETA DX DY [--nota TXT]` e `--pose-repor`.
- Reconsultam como as outras ações; `--no-requery` evita a reconsulta.
- Imprimem a pose de antes e a de depois e as «Suspeitas novas».

## Medições (cópia de `projects/alpes`, `scratchpad/pose/alpes`; `medir_pose.py`)

| medição | tempo |
|---|---|
| `GET /pose` P0240 | 112 ms a frio; 12–14 ms depois |
| `avaliar` P0240 (2 vizinhas) | 13–15 ms no servidor, 20–21 ms no cliente (TestClient) |
| `avaliar` P0042 (46,7) (4 vizinhas) | 19 ms no servidor, 26 ms no cliente |
| `avaliar` P0651 (44,1) (3 vizinhas) | 17 ms no servidor, 25 ms no cliente |
| gravar (`POST /pose`) | 9,1 s |
| repor | 4,4 s |

- O alvo de < 100 ms no `avaliar` é cumprido sem cortar pontos **[V]**.
- Os tempos de gravar e repor incluem `save` do projeto (908 peças), invariantes, reconsulta, registo com imagem e reavaliação das Suspeitas (cerca de 5,6 s a frio, `FALSOS_ALARMES.md`). Não decompus o tempo **[NT]**.

**P0240 (1,63), F para fora 0,26 mm** (dy = −0,26; θ = o da pose automática, que já é o da reta F, RENDER §8):

| | junta W com P0245 | junta E com P0236 |
|---|---|---|
| pose automática | −0,615 | −0,078 |
| F 0,26 mm para fora | −0,702 | −0,088 |
| RENDER §9, F +0,74 mm (só a peça) | −0,63 | −0,12 |

- A pose automática bate com o RENDER §9 (−0,61 / −0,08) **[V]**.
- Encostar o F à linha da borda piora as duas juntas, a W em 0,09 mm. É a mesma conclusão do §9: a grelha nominal reparte o erro.
- Orientação: sem falhas nas duas poses.
- **Gravar** P0240:
  - eventos `pose_set` + `fetch_listed` (este é informativo, da reconsulta);
  - invariantes OK;
  - `celulas_mudadas` [[1,63]];
  - na região (1,62)–(2,64) a 120 px/célula mudaram 1066 px, numa faixa de 155 × 115 px à volta da peça (`scratchpad/pose/P0240_antes.jpg` e `P0240_depois.jpg`);
  - Suspeitas: `n_pose_manual` 1, e as outras contagens ficam iguais (0 / 2 / 12).
- **Repor:** eventos `pose_cleared` + `fetch_listed`, as juntas voltam a −0,615 / −0,078, e o raster da região volta a ficar igual ao inicial (0 px diferentes) **[V]**.
- **Sensibilidade da métrica de junta (sintético, `test_render.py`):** deslocar 1 mm na normal muda o `gap_mm` de um lado com tab/baía em 0,67 mm (0,96 → 0,289 / 1,631). A mediana ao longo do lado não é linear no deslocamento: o cliente não deve converter a folga em deslocamento 1:1.

## Pares (pose automática, pose manual): medição, sem aprendizagem (2026-11-08)

Pedido do Tiago (ronda 6): guardar o par e resumir o desvio; **não** calibrar nada.

- **O que fica gravado:** `pose_set.antes` passa a levar a pose automática inteira: `{theta_deg, dx_mm, dy_mm, method, manual, pivot_mm, residual_mm, shape_residual_mm, corner_k, rotation}` (`render.pose_brief(e, full=True)`, chamado por `server.set_pose`). Os 4 eventos anteriores têm só `{theta_deg, dx_mm, dy_mm, method, manual}`; como o pivô da pose manual é o da automática (`server.set_pose`, `pivot_mm=e0["pivot_mm"]`) e as duas são absolutas ao centro da célula, o desvio é a diferença direta e lê-se nos eventos antigos também.
- **Relatório:** `python -m src.overrides --project projects/alpes --pares` acrescenta a secção «Poses manuais» (`overrides.pose_pairs` / `pose_summary`): por evento `pose_set` a peça, célula, zona (`fit.zone_of`), se a pose ainda está ativa, Δθ, Δx, Δy (manual − automática, mm do tabuleiro, y para baixo), |d|, direção dominante (N/E/S/W), deslocamento do centro do corpo (igual a |d| quando o pivô é o centro) e o método automático; resumos **por zona** e **por direção** com n, média e IC 95 % t de Student (tabela interna df 1–30; sem scipy). `--json-poses` dá o JSON; `--json` continua a ser a lista dos contornos.
- **Medido em `projects/alpes` (2026-11-08, 4 poses, todas céu, todas `corners` com dx = dy = 0 na automática) [V]:**

| peça | célula | Δθ ° | Δx mm | Δy mm | \|d\| mm | direção |
|---|---|---|---|---|---|---|
| P0833 | (8,2) | 0,00 | +0,27 | −0,37 | 0,46 | N |
| P0133 | (3,28) | −4,08 | +0,64 | +0,55 | 0,84 | E |
| P0177 | (2,37) | 0,00 | +1,01 | 0,00 | 1,01 | E |
| P0135 | (3,46) | 0,00 | +0,09 | +0,82 | 0,83 | S |

  Resumo: Δx média +0,50 IC95 [−0,14, +1,15]; Δy +0,25 [−0,60, +1,10]; Δθ −1,0° [−4,3, +2,2]; |d| 0,78 [0,41, 1,15]. Por direção n = 1–2: sem IC útil.

- **A partir de que n o desvio seria utilizável (resposta, sem agir):** `n ≥ (t·σ/δ)²` por estrato, com δ = metade do passo que se quer resolver e σ o desvio-padrão medido pelo relatório. Com σ ≈ 0,4 mm (a ordem do que os 4 casos sugerem: |d| 0,46–1,01) e δ = 0,2 mm → n ≈ 15 por estrato; com 1/3 de peças de reserva (que nunca entram na calibração) → **≈ 20–25 por zona** (céu, montanha, vale, relva) para um parâmetro isotrópico, ou **≈ 60–100 no total** para um parâmetro que dependa da direção (banda da sombra só nos lados virados à sombra: 4 direções). Hoje n = 4 (uma zona, uma direção com n = 2): não se estima nem σ. **Aviso de viés de seleção:** as poses manuais são as peças que o Tiago achou mal desenhadas (a cauda do erro, como as 61 peças de julho), não uma amostra do registo; para calibrar é preciso juntar peças de reserva escolhidas ao acaso e medir também as que o Tiago não tocou.
- **Parâmetros candidatos (nomes de hoje), nenhum ligado:** `calibration.celula_silhueta.offset_mm` 0,48 (a silhueta está fora da linha de corte, E-real), `calibration.buraco.erosion_mm` 0,60 (M11), a banda da sombra (`render.DISPLAY_SHADOW` 0,4 mm no desenho; S2 em `segmentation.py`, 1,2 mm nos lados virados à sombra), `F_TRANSLATION` (desligado; P0240 refutou o encosto do F), e o refinamento por imagem de `register_piece` (desligado, 0 aceites). Nada disto lê os pares: `--pares` é só medição.
