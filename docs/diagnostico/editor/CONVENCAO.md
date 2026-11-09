# Convenção da silhueta: índice vs editor de contorno (2026-11-09, ronda 9)

Medição reproduzível: `tools/diagnostico/editor/convencao.py --project projects/alpes --json convencao.json --fig CONVENCAO_17.jpg` (só leitura; 17 registos + amostra de 129 peças + P0651/P0657 contra a GT do Photoshop). Etiquetas: [V] verificado (com número), [NT] não testado, [F] falha.

## 0. Resumo

1. **O índice inclui a sombra.** A silhueta de `segment_scan` (limiar Lab contra o papel) fica fora da aresta verdadeira: mediana +0,36 / +0,54 mm em P0651/P0657 contra a GT do Photoshop, até +1,2…+1,4 mm nos lados da sombra (W/S no referencial do scanner) e ≈ 0 nos lados iluminados [V]. Os limiares de gémea (`t95`), a erosão do buraco (0,60 mm) e `celula_silhueta.offset_mm` (0,48) estão calibrados sobre esta convenção.
2. **O editor encontra a aresta verdadeira.** `strokes.resolver` com 0 traços encolhe o automático: mediana do desvio assinado da fronteira −0,17…−0,42 mm nos 17 registos; na amostra de 129 peças sem contorno manual, por zona: céu −0,24, montanha −0,24, relva −0,34, vale −0,19 (mín. −0,54, máx. −0,08); em P0651/P0657 −0,49/−0,51 mm, onde o resultado bate com a GT a −0,08/+0,12 mm [V]. **O desvio não é uniforme**: p5 −1,0…−1,5 mm (lados da sombra), p95 +0,08 (lados iluminados). Depende da cor da peça e do lado: não existe um δ constante.
3. **A leitura do R7 §1.3 estava invertida.** Os 17 contornos gravados são **mais apertados** do que o automático (desvio assinado mediano −0,24…−0,51 mm; `--pares` toma o manual como GT, por isso o «a mais 52–68 mm²» é o excesso do automático). Os traços são quase só `pincel/fundo` r = 8 px, com o centro 0,1–0,4 mm **dentro** da aresta automática, sobre a linha negra da sombra: exatamente o que a ajuda do editor mandava fazer. Reproduzem o contorno gravado bit a bit (IoU 1,000, 17/17) [V]. Consequência: silhueta editada (aresta) contra gémea (com halo) → d1 0,69–0,85 mm → `sem` (R7 §1.2).
4. **A decomposição «uniforme + local» não serve de classificador**: com o critério fixado antes (resíduo > 0,5 mm e ≥ 3 mm²) saem 17/17 com «correções locais», todas nos lados da sombra (figura `CONVENCAO_17.jpg`, caixas ciano à esquerda/em baixo): é a anisotropia da sombra, não correção. O classificador operativo é o da §3 (re-correr o pipeline normalizado e medir a profundidade contra o automático).
5. **O teste que falhava** (`tests/test_gui_guardadas.py::test_real_board_cells_without_orthogonal_neighbour_are_not_in_vai_buscar`) não lê contornos: compara o `fetch.json` vivo com um log cortado em 2045 eventos; 5 das 7 células foram preenchidas nas linhas 2669–2738 (P0105 (4,43), P0165 (3,54), P0176 (4,53), P0935 (3,55), P0909 (3,59)). Nenhuma correção de contorno o faz passar [V]. A atribuição aos 17 contornos (HANDOFF, R7) estava errada.

## 1. Os 17 registos (desvio assinado da fronteira ao automático, mm; + = fora) [V]

| peça | célula | zona | marcas | 0 traços: mediana (p5, p95) | gravado: mediana (p5, p95) | reprod. |
|---|---|---|---|---|---|---|
| P0045 | (43,5) | relva | fundo 11, peca 5, incerto 4 | −0,42 (−1,27, +0,08) | −0,49 (−1,47, +0,08) | 1,000 |
| P1203 | (4,57) | céu | fundo 3 | −0,19 (−1,19, +0,08) | −0,30 (−1,39, +0,08) | 1,000 |
| P1114 | (4,62) | céu | fundo 3 | −0,17 (−1,49, +0,08) | −0,37 (−1,61, +0,08) | 1,000 |
| P1064 | (2,63) | céu | fundo 8, peca 4 | −0,30 (−1,19, +0,08) | −0,46 (−1,52, +0,08) | 1,000 |
| P0916 | (6,63) | céu | fundo 4 | −0,19 (−1,05, +0,08) | −0,34 (−1,34, +0,08) | 1,000 |
| P1245 | (3,57) | céu | fundo 6 | −0,19 (−1,12, +0,08) | −0,25 (−1,44, +0,08) | 1,000 |
| P1202 | (2,62) | céu | fundo 8 | −0,18 (−1,35, +0,17) | −0,30 (−1,54, +0,17) | 1,000 |
| P1102 | (4,36) | céu | fundo 6 | −0,24 (−1,17, +0,08) | −0,34 (−1,44, +0,08) | 1,000 |
| P0999 | (4,35) | céu | fundo 4 | −0,24 (−1,10, −0,08) | −0,30 (−1,44, −0,08) | 1,000 |
| P0098 | (3,36) | céu | fundo 7 | −0,19 (−1,13, +0,08) | −0,36 (−1,52, +0,08) | 1,000 |
| P0105 | (4,43) | céu | fundo 7 | −0,17 (−1,07, +0,08) | −0,25 (−1,35, −0,08) | 1,000 |
| P0186 | (4,45) | céu | fundo 8 | −0,30 (−1,42, −0,08) | −0,42 (−1,61, −0,08) | 1,000 |
| P1021 | (2,54) | céu | fundo 6 | −0,27 (−1,08, +0,08) | −0,42 (−1,49, −0,08) | 1,000 |
| P0165 | (3,54) | céu | fundo 5 | −0,17 (−1,01, +0,08) | −0,30 (−1,37, −0,08) | 1,000 |
| P0935 | (3,55) | céu | fundo 9 | −0,27 (−1,05, +0,08) | −0,42 (−1,42, −0,08) | 1,000 |
| P0071 | (42,62) | relva | fundo 7, peca 2 | −0,25 (−0,86, +0,08) | −0,51 (−1,32, +0,08) | 1,000 |
| P1089 | (3,62) | céu | fundo 9 | −0,19 (−1,42, +0,08) | −0,24 (−1,49, +0,08) | 1,000 |

Automático menos gravado: 52–68 mm² por peça (IoU 0,82–0,87); gravado fora do automático ≤ 3,8 mm². Os píxeis que os pincéis «fundo» tiraram para além do solver sem traços são o **núcleo negro da sombra**: L\* 8–10, a\* 122, b\* 132 (OpenCV 8 bits; croma ≈ 7), o resíduo que o TRACOS §2.4 já descrevia (o GrabCut só croma mantém-no a não ser que um «fundo» lho ensine).

## 2. P0651/P0657 contra a GT do Photoshop [V]

| peça | índice vs GT: IoU / a mais mm² / desvio | solver 0 traços vs GT | solver 0 traços vs índice |
|---|---|---|---|
| P0651 (44,1) | 0,870 / 51,0 / +0,36 (−0,36, +1,24) | 0,940 / 12,4 / −0,08 (−0,51, +0,69) | 0,880 / 4,8 / −0,49 (−1,44, +0,17) |
| P0657 (45,1) | 0,820 / 59,8 / +0,54 (−0,17, +1,42) | 0,940 / 15,5 / +0,12 (−0,24, +0,51) | 0,850 / 4,3 / −0,51 (−1,52, +0,25) |

## 3. Decisão: o editor grava na convenção do índice (`src/strokes.py`, `normalizar_indice=True` no servidor)

Critérios fixados antes (plano da ronda): C1 gravar sem traços = contorno atual, exato; C2 nas peças em que o automático estava certo, desvio médio |automático − gravado| ≤ 0,3 mm; C3 a gémea de uma peça editada volta a ser encontrada; C4 as correções reais dos testes sintéticos não pioram mais de 0,01 de IoU.

Desenho (as alternativas «δ constante» e «δ por zona» ficam refutadas pela §1: o desvio é por lado e por cor):

1. **Halo da própria peça** (`delta_peca`): corre-se o solver sem traços com a faixa incerta semeada como fundo (`S0_INCERTO = "bgd"`; com `perto` o prado sintético de cor plana cede uma componente do GMM à sombra e fica com 4301 de 4435 píxeis de sombra, com `bgd` 0 e 0 píxeis de peça perdidos [V]); `H = (auto ∧ ¬S0) ∪ núcleo`, com `núcleo` = píxeis do automático com L\* < 60 e croma < 40 (8 bits) até 2,0 mm da fronteira, ligados à orla exterior ou à penumbra (`nucleo_sombra`). O escalar δ = −mediana do desvio assinado de S0 (zona morta 1 px, clamp [0, 0,8] mm) só serve para dar o mesmo halo às zonas **ganhas** (mordida recuperada).
2. **Traços de sombra** (`tracos_de_sombra`): um `fundo` cuja pegada dentro da peça fica ≥ 60 % sobre H, ou que entra na peça por < 1,5 mm² (roçar da aresta), é ignorado por inteiro e devolvido em `tracos_ignorados` (a GUI mostra-o a cinzento). Razão: a largura do pincel (0,68 mm a r = 8 px) faz com que um pincel sobre a linha negra apanhe sempre uma lasca da orla iluminada; cortar píxel a píxel deixava 7–21 mm² em falta a 1,1 mm de profundidade em 12 das 17 [V, versão intermédia].
3. **Região de influência** I = pegada dos traços restantes dilatada por banda + alcance + δ (≈ 2,2–2,4 mm); laço inteiro; a borracha não conta.
4. **Máscara gravada** = automático fora de I; dentro de I, `bruto ∪ H` mais as zonas ganhas dilatadas por δ; limpeza 0,3 mm só dentro de I; uma componente, sem buracos; marcas «peca» reimpostas, marcas «fundo» **não** (o halo pertence à silhueta). **Sem traços efetivos a máscara é o automático, bit a bit** (C1).

Consequências declaradas: um «fundo» a menos de ≈ 0,5 mm da aresta (sombra, penumbra, núcleo negro) é inócuo; um «fundo» sobre material escuro e neutro a < 2 mm da aresta (rocha preta, árvore) também é tratado como sombra; um corte que entra em cor de peça continua a cortar (`test_deep_fundo_cut_survives_normalisation`); um pincel «fundo» totalmente interior é um buraco e `limpar` preenche-o nos dois caminhos (já era assim). O caminho bruto (`normalizar_indice=False`, omissão da função) é o que `tests/test_strokes.py` e `tracos_gt.py` medem; só o servidor normaliza.

### 3.1 Os 17 registos com os traços originais, pipeline novo (`renormalizar.py`, dry-run) [V]

| resultado | peças |
|---|---|
| identidade (todos os traços eram de sombra) | P1203, P1114, P0916, P1245, P1202, P1102, P0999, P0098, P0105, P0186, P1021, P0165, P0935, P1089 (14) |
| ≈ automático (profundidade ≤ 0,5 mm; traços «peca»/«fundo» restantes sem efeito mensurável) | P1064 (1,9 mm² a mais, prof. 0,37), P0071 (0,0 / 0,0) |
| correção real mantida, **a confirmar pelo Tiago** | P0045 (43,5): 2,5 mm² a mais, prof. 0,54 mm, das marcas «peca»/«incerto» de 2026-11-07 |

Desvio médio |automático − gravado| nas 16 «reposição»: 0,000–0,016 mm (C2 ✓, critério 0,3). Costura em ∂I: p95 ≤ 0,37 mm (P0045), 0 nas identidades.

### 3.2 O que fica por medir [NT]

- Traços humanos novos com a convenção nova (o Tiago só desenhou sob a instrução antiga).
- Peças de duas cores (céu/relva na mesma peça): o `núcleo` e o `S0_bgd` são por píxel, mas o δ escalar das zonas ganhas é a mediana.
- Peças escuras e neutras reais na aresta (montanha): a regra do núcleo pode ignorar um «fundo» legítimo; nenhum caso nos dados.
