# Editor de contorno «por traços»: solver contra a verdade de terreno (2026-11-07)

Backend do editor que substitui a edição ponto a ponto: **traços → mapa de 5 zonas (trimap) → solver com marcadores → polígono**. Módulo puro `src/strokes.py`; registo em `src/overrides.py`; endpoint `POST /api/pieces/{pid}/contorno/resolver` em `src/server.py`. Medição reproduzível: `tools/diagnostico/editor/tracos_gt.py` (só leitura; números em `tracos_gt.json`, figura `TRACOS_gt.jpg`).

Etiquetas: [V] verificado (com o número), [NT] não testado, [F] testado e falha.

## 1. Dados e cenários

- **Verdade de terreno:** `docs/diagnostico/reports/R0011_R0012_manual/manual_{A,B}_photoshop.png` (recortes à mão do Tiago, alfa > 127, maior componente; a máscara A tem 1 píxel solto que fica de fora) = **P0651** (44,1) e **P0657** (45,1) de S0020, na grelha de `montado_p12_300dpi.jpg` (0,0847 mm/px). Recorte do editor (`crop_window`, bbox + 3 mm): P0651 380 × 416 px, P0657 383 × 322 px.
- **Índice atual contra a GT [V]:** P0651 IoU 0,869, p95 1,29 mm, 51,0 mm² a mais (sombra) e 6,8 mm² em falta; P0657 IoU 0,824, p95 1,42 mm, 59,8 mm² a mais. A sombra projetada nos lados W/S e dentro do blank inferior de P0657 é o grosso do erro (figura, última coluna, ciano).
- **Traços sintéticos** gerados a partir da GT (simulam o utilizador):
  - (i) só o trimap automático (0 traços);
  - (ii) trimap automático + 1 laço «incerto» = maior componente de GT ⊕ automático, dilatado 1,5 mm (no índice é a faixa de sombra W/S);
  - (iii) «um laço largo»: laço «fundo» = recorte inteiro, laço «incerto» = GT dilatada 2,5 mm, laço «peca» = GT erodida 2,5 mm (faixa de 5 mm centrada na GT);
  - (iii-in) / (iii-out): a mesma faixa de 5 mm deslocada 1 mm para dentro / para fora. Acrescentei-os porque em (iii) a linha média da faixa É a GT, o que favorece de forma irreal a regra «incerto mais perto da peça → provável peça» do GrabCut.

## 2. Resultados [V]

Médias das 2 peças (IoU, p95 da distância simétrica entre fronteiras); «em falta» e «a mais» somados nas 2 peças; ms = máximo das 2 peças (mediana de 3 corridas de `strokes.resolver`, trimap + solver + limpeza, sem o servidor). Tabela completa (19 variantes × 5 cenários × 2 peças) no `tracos_gt.json` e na saída do script.

| solver | (i) IoU / p95 | (ii) IoU / p95 / falta / mais / ms | (iii) IoU / p95 / falta / mais / ms | (iii-in) IoU / p95 | (iii-out) IoU / p95 |
|---|---|---|---|---|---|
| índice (`contour_px`) | 0,846 / 1,35 | 0,846 / 1,35 / 8,0 / 110,8 / – | idem | idem | idem |
| **grabcut, Lab só croma (L\* × 0), 2 it. (omissão)** | **0,941 / 0,64** | **0,943 / 0,63 / 12,1 / 28,3 / 236** | **0,939 / 0,67 / 16,4 / 26,4 / 245** | **0,936 / 0,68** | **0,942 / 0,63** |
| grabcut RGB, 3 it. | 0,887 / 0,95 | 0,909 / 0,74 / 63,0 / 0,3 / 325 | 0,905 / 0,80 / 65,8 / 0,3 / 351 | 0,893 / 0,99 | 0,901 / 0,80 |
| grabcut RGB + fundo pelo limiar 28 | 0,853 / 1,19 | 0,840 / 1,43 / 105,4 / 0,1 / 319 | 0,788 / 2,08 / 141,0 / 0,0 / 371 | 0,763 / 2,46 | 0,862 / 1,10 |
| grabcut Lab L\* × 0,25, 3 it. | 0,902 / 0,97 | 0,896 / 1,00 / 58,3 / 16,2 / 339 | 0,902 / 1,00 / 62,5 / 5,9 / 321 | 0,896 / 1,05 | 0,913 / 0,73 |
| watershed cor, Lab só croma | 0,948 / 0,63 | 0,940 / 0,69 / 23,5 / 17,1 / 17 | 0,934 / 0,81 / 27,9 / 17,3 / 18 | **0,721 / 5,72** | 0,939 / 0,69 |
| watershed cor, RGB | 0,872 / 1,13 | 0,844 / 1,41 / 95,8 / 8,9 / 18 | 0,800 / 2,22 / 129,9 / 2,7 / 18 | 0,615 / 6,68 | 0,868 / 1,15 |
| watershed relevo (black-hat + gradiente, `cv2.watershed`) | 0,794 / 1,71 | 0,723 / 2,07 / 183,1 / 1,4 / 25 | 0,604 / 3,69 / 261,2 / 0,0 / 26 | 0,422 / 8,44 | 0,778 / 1,36 |
| watershed inundação (`_priority_flood`, o do contacto) | 0,833 / 1,60 | 0,766 / 1,90 / 153,1 / 7,8 / 329 | 0,695 / 3,35 / 204,9 / 0,5 / 284 | 0,480 / 7,65 | 0,825 / 1,32 |
| limiar do segmentador (d > 28, base) | 0,843 / 1,35 | 0,842 / 1,36 / 7,7 / 114,6 / 15 | 0,829 / 1,51 / 7,9 / 126,5 / 15 | 0,841 / 1,40 | 0,817 / 1,65 |
| limiar só croma (d_ab > 25) | 0,932 / 0,81 | 0,933 / 0,80 / 6,9 / 39,7 / 15 | 0,934 / 0,80 / 6,9 / 38,9 / 14 | 0,934 / 0,80 | 0,934 / 0,80 |

Por peça, solver por omissão, cenário (ii): P0651 IoU 0,944, p95 0,74 mm, em falta 9,9 / a mais 12,8 mm²; P0657 IoU 0,941, p95 0,51 mm, 2,2 / 15,5 mm².

### 2.1 Porque é que o RGB falha e o croma funciona [V]

Medi as distribuições Lab (8 bits, OpenCV) nas zonas da GT (`colours` no histórico desta ronda; reproduzível com `tracos_gt.load` + `strokes._threshold_fg`):

| zona | L\* mediana | a\* mediana (p25–p75) | b\* mediana |
|---|---|---|---|
| sombra (limiar ∧ ¬GT, perto da peça) | 117 / 113 | **91 / 92** (84–102) | 162 / 161 |
| papel (fundo) | 192 / 193 | **79** (78–80) | 174 |
| orla da GT (0,25 mm exteriores da peça) | 152 / 133 (p75 193 / 184) | **106 / 110** | 161 / 156 |
| faixa de 1 mm da peça | 160 / 146 | **112 / 112** (108–118) | 166 / 159 |

A sombra projetada tem a **tonalidade do papel** (verde escurecido: a\* 91 contra 79 do papel e 106–113 da peça) e a orla iluminada da peça (lados N/E) é **clara mas com o a\* da peça**. Em RGB o modelo de cor do GrabCut junta a orla clara ao fundo (falta 60–66 mm², a magenta da 3.ª coluna da figura) e o limiar junta a sombra escura à peça (114–126 mm² a mais). Tirando o L\* às cores que o solver vê (`espaco="lab", peso_l=0`), ambos os erros caem: GrabCut 0,89–0,91 → 0,94 e p95 0,74–0,99 → 0,63–0,68 mm. Um peso intermédio (L\* × 0,25) **não** serve (0,90). Forçar como fundo o que o limiar chama fundo (`limiar=28` no GrabCut) piora sempre (0,76–0,86): refutado, fica só como parâmetro medido.

### 2.2 Escolha do solver por omissão: GrabCut só croma, 2 iterações

- **Qualidade** nos cenários (ii) e (iii): o melhor ou empatado (0,943 / 0,939), e o único que **não depende** de onde o utilizador põe a faixa (iii-in 0,936, iii-out 0,942). O watershed só croma empata em (i)/(ii)/(iii-out) e é 15× mais rápido, mas **colapsa** quando o marcador de peça não chega a todas as partes da peça: em (iii-in) a erosão de 3,5 mm deixa a P0657 com um triângulo de marcador e a metade direita fica fundo (IoU 0,494, figura, linha 4). Um editor em que um laço «peca» pequeno apaga meia peça não serve.
- **Iterações** (IoU em ii / iii / iii-in / iii-out): 1 it. 0,940 / 0,933 / 0,918 / 0,907 (p95 1,48 em iii-out); **2 it. 0,943 / 0,939 / 0,936 / 0,942**; 3 it. 0,942 / 0,940 / 0,942 / 0,941; 5 it. 0,942 / 0,941 / 0,944 / 0,943. 2 iterações ficam a ≤ 0,006 das 5 com metade do tempo (222–306 ms contra 428–532).
- **Alcance** (`alcance_mm`, quanto das zonas «prováveis» o solver ainda pode mudar): 0,5 / 1,0 / 1,5 mm dão ±0,005 de IoU; fica 1,0 mm (o automático chega a estar 1,5–1,7 mm fora da GT: com banda 1,0 + alcance 1,0 o solver alcança 2 mm). Regra do «incerto» (`perto` / `fgd` / `bgd`) e janela (`livre` / `recorte`): ±0,01, sem preferência estável; ficam `perto` e `livre`.
- **Determinismo:** o `cv2.grabCut` inicializa os GMM com k-means sobre o RNG do OpenCV; sem semente, a mesma entrada deu IoU a variar até 0,005 entre corridas. Agora `cv2.setRNGSeed(0)` antes de cada chamada: 4 corridas iguais píxel a píxel nas 2 peças [V]. Necessário para «desfazer = prefixo da lista» devolver exatamente o resultado anterior (teste `test_undo_prefix_gives_previous_result_and_deterministic`).

### 2.3 Banda de 1,0 mm e limpeza de 0,3 mm [V]

Sensibilidade do solver por omissão (IoU médio em i / ii / iii-out): banda 0,5 / 1,0 / 1,5 mm × limpeza 0 / 0,3 / 0,5 mm: **todas as 27 combinações entre 0,941 e 0,944, p95 0,63–0,64**. Nenhuma das duas constantes decide o resultado nestes dados; ficam os valores pedidos (banda 1,0 mm, limpeza 0,3 mm = disco de 5 px), a banda por ser a meia-largura que cobre o desvio típico do automático (0,6–0,9 mm, R0011/R0012) e a limpeza por tirar picos de 1 px sem custo medido.

### 2.4 Alvo p95 < 0,3 mm: [F]

Nenhum solver chega lá. O melhor p95 em (ii)/(iii) é 0,51 mm (P0657) / 0,74 mm (P0651); médias 0,63–0,68 mm. O resíduo do solver por omissão (figura, 4.ª coluna):

1. **Núcleo negro da sombra** (ciano fino nos lados S/E, ~0,3–0,5 mm): os píxeis mais escuros da sombra (L\* p5 = 5–7) têm croma neutro, por isso, só com croma, não parecem papel; ~26–28 mm² a mais nas 2 peças.
2. **Orla oeste de P0651** (magenta fina): a GT inclui uma orla que o croma põe no fundo; ~10 mm² em falta.

**Experiência (fora do produto):** «pelar» os píxeis escuros (L\* < 60) dos 0,3–0,5 mm exteriores ligados à fronteira (`peel` em `tracos_gt.py`) baixa o p95 de 0,63 para 0,47–0,49 mm e sobe o IoU de 0,943 para 0,950 em (ii), mas troca excesso por falta (+4–6 mm² em falta) e foi afinado nas mesmas 2 máscaras em que é medido, sem conjunto de validação, numa arte (relva) com píxeis negros reais na aresta. Não entra no `src/strokes.py` [NT fora destas 2 peças]. No editor, o resíduo corrige-se com um traço «fundo» de pincel fino ao longo da linha negra.

### 2.5 Arte cor do papel (prado claro) [V, sintético]

No `tests/synth.meadow_scan` (canto de prado L\* 62, a\* −26 cortado pelo `segment_scan(recover_bays=False)`, contorno automático IoU 0,959):

| traços | grabcut (omissão) | watershed | limiar (base) |
|---|---|---|---|
| nenhum | 0,925 | 0,912 | 0,979 |
| laço «incerto» sobre o canto (dilatado 1 mm) | **0,925** | 0,912 | **0,999** |
| laço «peca» dentro do canto (erodido 4 px) | **0,996** | 0,982 | 0,994 |
| 1 pincel «peca» r = 8 px na diagonal do canto | 0,989 | 0,955 | 0,979 |

O GrabCut perde o canto inteiro quando só lhe dizem «incerto»: o modelo de cor da peça nunca viu aquela cor e o prado fica mais perto do papel. **Não há regra de píxel que resolva isto e a sombra ao mesmo tempo:** o prado e a sombra são o mesmo tipo de píxel (papel mais escuro e menos saturado: prado L\* 62 a\* −26, sombra ≈ L\* 44 a\* −37, papel L\* 79 a\* −50). Quem decide é a marca do utilizador: **«peca» sobre arte clara, «fundo» sobre sombra**. Os testes seguem isto (ver §6).

## 3. Desempenho do endpoint [V]

`TestClient` em processo sobre uma cópia de `projects/alpes` (scratchpad), mediana de 5 pedidos depois de 1 de aquecimento, recortes reais:

| peça (recorte) | solver | total HTTP | servidor | solver | resposta |
|---|---|---|---|---|---|
| P0651 (380 × 416) | grabcut (omissão) | 236 ms | 226–227 ms | 212–213 ms | 16,1–16,2 KB |
| P0657 (383 × 322) | grabcut (omissão) | 208–210 ms | 199–200 ms | 185–188 ms | 15,4 KB |
| ambas | watershed | 35–39 ms | 25–29 ms | 13–15 ms | 15,8–16,4 KB |
| ambas | limiar | 34–41 ms | 25–30 ms | 11–14 ms | 17,1–17,8 KB |

Resposta: contorno 12–14 KB (1074–1243 pontos inteiros), RLE 3,0–3,6 KB (685–787 corridas). O **primeiro** perfil mostrou 377 ms no servidor para 217 no solver: 158 ms eram do `overrides.is_simple` (um ciclo Python por aresta, O(n²) chamadas numpy). Reescrevi-o com um pré-filtro exato por caixas envolventes (sobreposição das caixas fechadas é condição necessária de cruzar ou tocar) em blocos vetorizados: **0 discordâncias** com a versão anterior em 3000 polígonos aleatórios (grelhas inteiras com toques e colineares, cruzamentos, estrelas, vértice arrastado) e em 479 contornos reais do índice, nos dois modos `touch`; 178 → 8,8 ms em média (mediana 1278 pontos); 5000 pontos 152 ms. Beneficia também o gravar e o `preview` existentes.

O alvo de < 300 ms por chamada é cumprido pelo solver por omissão nestes recortes (≤ 236 ms); em (iii-out) (faixa incerta de 5 mm deslocada para fora) o solver sozinho chegou a 303–306 ms [V], no limite. [NT] máquina mais lenta, recortes de peças maiores ou com tabs muito salientes.

## 4. Registo e pares automático/manual

`overrides.append_override(..., extra=None)` aceita só os campos de `EXTRA_KEYS` (os da linha base não podem ser sobrepostos; desconhecidos → `{'error'}` sem escrever). O `POST …/contorno` passa a gravar, para **qualquer** gravação da GUI, `auto_contour_px` (o contorno substituído, inteiros, px do scan), `auto_area_mm2`, `auto_origem` (`segmentacao` ou `manual`, se já havia um override) e `metodo` (`vertices` ou `tracos`); com traços também `tracos` (px do recorte), `origem`, `tamanho`, `solver: {nome, params}` (parâmetros completos, já com as omissões) e `mascara_rle` (o polígono gravado preenchido no recorte, **calculado no servidor**; uma `mascara_rle` enviada pelo cliente só é verificada no tamanho). Linhas antigas continuam a ler; `latest_overrides`, `rebuild_piece` e `piece_resegmented` não mudaram (testado: `test_append_override_extra_fields`, `test_force_rebuild_keeps_manual_contour`).

`overrides.manual_pairs(project)` e `python -m src.overrides --project <p> --pares [--json]`: por peça com override, o contorno automático **da segmentação** (o `auto_contour_px` da primeira linha com `auto_origem` `segmentacao`; se só houver de outro manual, esse, e a coluna diz `manual`) contra o manual da última linha, via `maskcmp` (IoU, em falta, a mais, p95, profundidades). Linhas sem `auto_contour_px` aparecem com «sem registo». Em `projects/alpes` ainda não há `overrides.jsonl`, por isso a tabela real está vazia [V na cópia]. Isto serve o ponto 2.4 do plano (medir o erro automático com os recortes manuais); não há «aprendizagem por peça».

## 5. Segmentação: extração sem mudar comportamento [V]

`segmentation._blackhat_gradient(lab, mm_per_px)` extrai o cálculo da paisagem do watershed de contacto (black-hat L\* 1,5 mm + gradiente Lab Sobel) para o editor a reutilizar. `segment_scan` em `montado_p12_300dpi.jpg` (S0020) com o código de HEAD e com o novo: 48 peças, **0 contornos diferentes**, 2 delas resolvidas pelo watershed de contacto (P0651/P0657). `pytest tests/test_segmentation.py -m "not slow"` verde.

## 6. Testes

- `tests/test_strokes.py` (novo, 14 testes, 2 s): validação dos traços, rasterização (laço, pincel, ponto = disco, borracha, ordem), tradução, trimap (larguras das bandas, traços por cima), domínio, `limpar` (fenda fechada, buraco preenchido, salpico fora, marcas certas reimpostas), polígono = máscara, RLE ida e volta (incluindo vazia, cheia e 1.º píxel peça), erros do `resolver`; no prado sintético: **laço «peca» dentro do canto → IoU ≥ 0,99 e ≥ base** com o solver por omissão; **laço «incerto» → ≥ 0,99 com o limiar**; desfazer (prefixo) dá exatamente o resultado anterior; os 3 solvers sem traços mantêm a peça (IoU ≥ 0,98 fora do canto).
  - **Desvio declarado em relação ao pedido:** o pedido era «1 laço incerto sobre o canto → IoU ≥ 0,99 para o solver escolhido». Com o GrabCut isso dá 0,925 (§2.5): o teste exige a marca que funciona («peca») para o solver por omissão e o laço «incerto» para o limiar. Não fixei em teste o 0,925 (não se trava comportamento mau).
- `tests/test_server.py` (acrescentados 4 testes, existentes intactos): `/resolver` 200 com os 3 solvers e omissão (`valido`, RLE = polígono preenchido, nada escrito), laço que aumenta a área, `valido: false` com a razão quando a área sai de 50–150 %; 400 (traços não-lista, ferramenta desconhecida, origem fora do scan, tamanho fora do scan, solver desconhecido, `iter` 0, corpo não-objeto, JSON inválido); 404 peça inexistente; gravar com traços (linha `metodo: "tracos"`, `auto_contour_px`, `auto_origem`, `solver`, `mascara_rle` = polígono, exatamente 1 `piece_resegmented`), reabrir devolve os traços traduzidos para o novo recorte, segunda gravação com `auto_origem: "manual"`, 400 em traço ou `mascara_rle` inválidos sem escrever; gravação por vértices regista `metodo: "vertices"` + `auto_contour_px`.
- `tests/test_overrides.py` (acrescentados 2): `extra` (campos aceites, desconhecidos recusados, aplicação intacta) e `manual_pairs` / `--pares` / `--json`.
- `pytest tests/test_overrides.py tests/test_server.py tests/test_strokes.py tests/test_segmentation.py tests/test_maskcmp.py tests/test_render.py tests/test_query.py -m "not slow"`: **99 passed** [V].

## 7. Contrato para a GUI

### 7.1 Coordenadas e recorte

Tudo o que o cliente desenha está em **px do recorte** do `GET /api/pieces/{pid}/contorno`: origem `origem = [x0, y0]` (px do scan), tamanho `tamanho = [w, h]`, imagem `crop_png_url` à escala 1. O cliente devolve sempre `origem` e `tamanho` que recebeu (o servidor valida-os contra o scan; sem eles usa o recorte atual, que muda quando o bbox da peça muda depois de gravar).

`GET …/contorno` passa a trazer também:
- `tracos`: os traços do último override com `metodo: "tracos"`, **já traduzidos para o recorte atual** (lista vazia se não há ou se a última gravação foi por vértices); permite reabrir e continuar;
- `banda_mm` (1,0), `solver_omissao` (`"grabcut"`), `solvers` (`["grabcut", "watershed", "limiar"]`).
Os campos existentes (`denso`, `contour`, `indices`, …) não mudaram: as pegas continuam como retoque opcional.

### 7.2 Traços

Lista ordenada (cada traço aplica-se por cima dos anteriores):

```json
{"ferramenta": "laco" | "pincel" | "borracha",
 "marca": "peca" | "fundo" | "incerto" | null,
 "raio_px": 6.0,
 "pontos": [[x, y], ...]}
```

- `laco`: polígono fechado dos pontos (≥ 3) preenchido com a marca; `raio_px` ignorado.
- `pincel`: polilinha de espessura 2·`raio_px` com pontas redondas; 1 ponto = disco. `raio_px` em (0, 500].
- `borracha`: geometria do pincel; devolve os píxeis a «não marcado» (volta a valer o trimap automático). `marca` ausente ou `null`.
- Pontos `float` permitidos (rasterização sub-píxel); podem sair do recorte até um tamanho do recorte (o que sai é cortado). Limites: 2000 traços, 200 000 pontos no total.
- **Semântica das marcas:** `peca` = peça certa, `fundo` = fundo certo (o solver nunca os muda); `incerto` = o solver decide ali. Sem traços, o trimap automático põe «incerto» numa faixa de ±`banda_mm` à volta do contorno atual, «provável peça» dentro e «provável fundo» fora; o solver pode ainda mudar o provável até 1 mm (`alcance_mm`) da faixa. Para mover a fronteira mais longe do que ~2 mm do contorno atual, o utilizador marca «incerto» (ou «peca»/«fundo») na zona.
- **O que dizer ao utilizador (medido, §2.4–2.5):** «fundo» com pincel fino sobre a **linha negra da sombra** que fica colada à peça; «peca» sobre **arte clara cor do papel** (prado, céu) que o automático cortou: «incerto» não chega com o solver por omissão.
- **Desfazer/refazer:** é do cliente; envia o prefixo da lista. O servidor não guarda estado entre chamadas e o resultado é determinista (o mesmo prefixo dá o mesmo polígono).

### 7.3 `POST /api/pieces/{pid}/contorno/resolver`

Corpo:

```json
{"tracos": [...], "origem": [x0, y0], "tamanho": [w, h],
 "solver": "grabcut" | "watershed" | "limiar" | {"nome": "...", "params": {...}},
 "iter": 2}
```

`solver` e `iter` opcionais (omissão: GrabCut, 2 iterações; `iter` inteiro 1–10, só conta para o GrabCut). `params` (forma objeto) aceita apenas as chaves de `strokes.SOLVER_PARAMS[nome]`; para a GUI, não é preciso usar.

Resposta 200:

```json
{"contour": [[x, y], ...],          // px do recorte, inteiros: a cadeia de píxeis exterior, já limpa
 "area_mm2": 389.4,
 "valido": true,                      // o mesmo teste que o gravar (check_override)
 "erro": null,                        // razão em português quando valido = false
 "solver": "grabcut", "params": {...},// parâmetros completos usados
 "mascara_rle": {"w": 380, "h": 416, "runs": [...]},
 "n_pontos": 1112, "origem": [x0, y0], "tamanho": [w, h],
 "ms_solver": 213.0, "ms": 227.0}
```

- `valido: false` vem com 200 (o resultado existe e mostra-se, mas o gravar recusá-lo-ia): área fora de 50–150 % da atual, < 20 pontos, cruzamentos. Se não sobrar peça nenhuma, `contour: []` e `erro` com a razão.
- **Máscara: escolhi devolver as duas formas numa só chamada.** O `contour` preenchido **é** a máscara: o servidor devolve `mascara_rle` = esse mesmo polígono preenchido com `cv2.fillPoly` (não a saída bruta do solver). Convenção de píxel: os vértices são **centros** de píxel e o `fillPoly` inclui os píxeis da própria fronteira. No canvas, um caminho pelas coordenadas inteiras cobre só metade desses píxeis; para a pré-visualização chega desenhar o caminho com +0,5 px (`moveTo(x + 0.5, y + 0.5)`…), `fill()` e um `stroke()` de 1 px. Para exatidão ao píxel, pintar a `mascara_rle`: ordem por linhas, corridas alternadas fundo/peça a começar em fundo (primeira corrida 0 se o 1.º píxel for peça), por exemplo num `ImageData` com alfa. Custo: ~3–3,6 KB a mais numa resposta de 15–18 KB.
- Erros: 400 `{"error": "..."}` (corpo não-objeto, JSON inválido, traço inválido, `origem`/`tamanho` fora do scan, solver ou `iter` inválidos); 404 peça desconhecida ou scan em falta; 503 enquanto o servidor prepara os assets. Não escreve nada e não usa o `wlock`: pode correr durante uma gravação (o contorno «atual» é o de antes ou o de depois, conforme a ordem).

### 7.4 Gravar

`POST /api/pieces/{pid}/contorno` como até agora (`{contour, origem, tamanho, nota?}`, `contour` em px do recorte) e, para gravar o resultado dos traços, acrescentar `tracos` (a lista ativa, sem o que foi desfeito), `solver` (e `iter`) usados. O `contour` a enviar é o do último `/resolver` (ou esse retocado com as pegas). `mascara_rle` é opcional e ignorada (só se verifica o tamanho); o servidor guarda a RLE do polígono gravado. A resposta é a mesma de sempre; o `override` devolvido não traz os campos pesados (`tracos`, `mascara_rle`, `auto_contour_px`).

### 7.5 Recomendações ao cliente

- Desenhar o traço **localmente e já** (canvas por cima do recorte), sem esperar pelo servidor.
- Pedir `/resolver` com **debounce de ~150 ms** depois do fim do traço (`pointerup`) ou de desfazer/refazer, sempre com a lista completa; com o GrabCut a pré-visualização chega ~350–400 ms depois da pausa (150 + 208–236 ms medidos). Durante o arrasto não pedir.
- Numerar os pedidos e **descartar respostas antigas** (a resposta não ecoa um id; guardar o número do pedido em curso e ignorar respostas cuja requisição já não é a última). Nunca mais de 1 pedido em voo: se chegar outro traço, esperar a resposta e pedir de novo com a lista atual.
- Mostrar `valido`/`erro` junto ao botão Gravar e desativá-lo quando `valido` é falso.
- Se se quiser pré-visualização durante o arrasto, `watershed` responde em 35–39 ms, mas falha quando o marcador de peça não cobre toda a peça (§2.2); usar só como esboço e voltar a pedir com o solver por omissão no `pointerup`. [NT na GUI.]

## 8. O que não foi verificado

- **Só 2 peças de verdade de terreno**, ambas de relva escura em fundo verde, do mesmo scan e em contacto; nada em céu/peças claras reais, noutros fundos ou noutros scans [NT]. Os traços dos cenários são sintéticos (offsets suaves da GT); traços humanos reais não foram medidos [NT].
- Latência medida em processo (`TestClient`) nesta máquina; sem rede nem browser [NT]. A GUI (JS) não existe ainda: o contrato acima não foi exercido por um cliente real.
- O resíduo do núcleo negro da sombra e o p95 < 0,3 mm: **[F]** (§2.4). A experiência «pele» melhora estas 2 peças mas não está validada fora delas.
- `manual_pairs` em dados reais: sem overrides no projeto, só testado em sintético e com a tabela vazia na cópia.
