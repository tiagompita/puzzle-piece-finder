# 2026-11-07 (3) — R0011/R0012 com verdade de terreno manual; editor de contorno por traços

## Porquê

O Tiago recortou à mão no Photopea (seleção em 3 zonas: preto fora, cinzento incerto, branco dentro, com refinamento de orla) as duas peças de R0011/R0012 (P0651 (44,1) e P0657 (45,1), S0020) e entregou as máscaras como verdade de terreno (`docs/diagnostico/reports/R0011_R0012_manual/`, commitadas por ele em `06210bc`). Na GUI as peças aparecem «comidas» (a A «parece uma casa com topo em picos»), mas a medida que usávamos (silhueta contra a gémea, `free_dist` 0,55 / 0,37 mm) deu-as como certas: a medida falhou e tem de ser substituída por uma apoiada nesta GT. Além disso o editor de contorno da ronda anterior (arrastar pontinho a pontinho) é impraticável para ele: quer o laço do Photoshop com três marcas e um algoritmo que resolva a zona incerta, tolerante a erros, com pré-visualização ao vivo e janela grande.

## Decisões

- Do Tiago (registadas em `docs/decisoes.md`, nada implementado): porta §6.1 fica como está, nem A nem B, os 49/607 a 1,5 % são exceção aceite; moldura (R0022) não incomoda, `F_TRANSLATION` desligado; P0395 é uma linha escura real; R0002/R0003 certos, corte c32|c33 por confirmar fisicamente.
- Os 4 PNG manuais já estavam commitados pelo Tiago (`06210bc`): não há commit próprio de GT.
- Identidade e alinhamento das máscaras: A = P0651 (FTTT, nº 24, `index_in_scan` 23), B = P0657 (BFBT, nº 30, `index_in_scan` 25); folhas manuais com o tamanho exato do scan S0020 (2544×3504), mesma grelha de coordenadas (a confirmar por busca de translação ±3 px).
- Hipótese de partida (a medir, não conclusão): o contorno do índice não é mais pequeno do que a GT (433 / 345 mm² contra 390 / 287 mm²; sai 0,6–0,9 mm para fora nos lados de sombra); a «mordida» está na silhueta exibida (limpeza `clean_crop` + `paper_pocket_mask` + `shadow_paper_mask`). A correção vai para onde a medida apontar (`src/render.py` ou `src/segmentation.py`), não para `segmentation.py` por defeito.
- Métrica única de comparação de máscaras em `src/maskcmp.py` (IoU, área em falta/a mais em mm², profundidades, distâncias de fronteira p95/máx.), usada pela medição GT e pela medição do solver do editor.
- Editor novo: traços (laço/pincel/borracha × peça/fundo/incerto) → trimap (contorno automático ±1 mm) → solver com marcadores escolhido por medição contra a GT (GrabCut / watershed / limiar na faixa; sem scikit-image) → polígono pelo mesmo contrato (`check_override` → `append_override` → `rebuild_piece`); registo estendido (`metodo:"tracos"`, `tracos`, `solver`, `mascara_rle`, `auto_contour_px`) para medir pares (automático, manual); sobreposição de janela inteira; pegas de vértice só como retoque opcional. `tests/test_gui_contorno.py` é reescrito (declarado).
- Sem aprendizagem por peça: só pares (automático, manual) para medir o erro, calibrar limiares (relatar) e ordenar suspeitas; as peças que o Tiago recortar depois ficam reservadas como validação.

## Prompt verbatim

```
Contexto
Projeto puzzle_piece_finder. Faz git pull. Lê docs/HANDOFF.md, docs/estado-e-plano.md, docs/decisoes.md, RENDER.md §7–§9, docs/diagnostico/segmentacao/PRADO.md e docs/diagnostico/reports/R0011_R0012.md. Segue cv-visual-verification (CV) e piece-fit-matching.

Regras
- Nada conta como progresso sem verdade de terreno. [V]/[NT]/[F] com números.
- Commits em português, SEM co-author nem linha Claude-Session. Push sem --force.
- Não alteres testes existentes sem o dizeres à parte e com a razão.
- Não feches reports (o Tiago fecha pelos botões). Antes de escrever em projects/alpes, vê git status; se houver alterações do Tiago por commitar, para e diz-lhe.
- Regista em docs/revisao.md e atualiza o HANDOFF no fim.

Decisões do Tiago desta ronda (regista em docs/decisoes.md)
- Porta §6.1: os recortes estão bons no geral e ficam como estão. Não implementes A nem B. Regista como exceção aceite os 49/607 que falham 1,5 %.
- Moldura (R0022, P0240/P0590): não o incomoda. Deixa F_TRANSLATION desligado.
- P0395: concorda que a flag apanhou uma linha escura real.
- R0002/R0003: dados certos. O corte c32|c33 continua por confirmar fisicamente.

Verdade de terreno nova (leitura obrigatória)
O Tiago recortou à mão no Photoshop as duas peças de R0011/R0012. Ficheiros em docs/diagnostico/reports/R0011_R0012_manual/ (por commitar: commita-os como GT, num commit próprio):
- manual_A_photoshop.png e manual_B_photoshop.png: folhas 2544×3504 a 300 dpi, RGBA. O canal alfa é a máscara manual da peça (bordas suaves, 255 níveis). Bounding box da A: x 2212–2503, y 1105–1435; da B: x 2210–2508, y 1431–1661.
- atual_A_gui.png e atual_B_gui.png: miniaturas do que a GUI mostra hoje (peça comida; a A parece uma casa com topo em picos).
Assume A↔atual_A e B↔atual_B, mas CONFIRMA contra a S0020 (#24 = P0651, #30 = P0657) e diz qual é qual. Confirma o alinhamento da folha manual com o scan S0020 (mesmas coordenadas? se não, regista com a transformação mínima e mede o erro de registo).
O Tiago usou no Photopea uma seleção em 3 zonas (preto = fora, cinzento = incerto, branco = dentro) com refinamento de orla (https://www.photopea.com/learn/refine-edge). É a inspiração do editor (Parte 2).

PARTE 1: R0011/R0012, causa e correção com verdade de terreno (fazer primeiro)
1.1 Mede a segmentação atual contra as máscaras manuais: IoU, distância de contorno (média, p95, máx.) em mm, e área dentro/fora em mm². Mostra as sobreposições (figura vista). Explica porque é que a medida contra a gémea (0,55 / 0,37 mm) não detetou; verifica se a gémea também está comida. Substitui as medidas de silhueta contra gémeas por uma que detete peça comida, apoiada nesta GT.
1.2 Diagnóstico: porque é que a segmentação come estas peças (relva clara com cor de papel? contacto? limiar?). Relaciona com _RECOVER_BAYS (PRADO.md) e as suas limitações já registadas (peças em contacto, prado abaixo do limiar fechado).
1.3 Correção em src/segmentation.py, só se medida contra a GT: IoU e distância de contorno melhores, E-sym bit a bit igual, 27 folhas com contagem e numeração iguais, sem piorar as peças de controlo. Evita sobreajuste: as 2 peças manuais são a base; as peças novas recortadas à mão na Parte 2 ficam reservadas como validação. Diz explicitamente o que foi afinado em quê.
1.4 Quantifica o alcance: quantas peças têm a mesma assinatura (detetor de 1.1), em que folhas e linhas/colunas. Repete para P0198 (R0019, fechado pelo Tiago) e as peças das filas 41–47: o diagnóstico anterior usou a medida contra gémeas que acabou de falhar.
1.5 Rebuild do índice só se projects/alpes estiver limpo no git, com estados e contagens iguais antes/depois.

PARTE 2: Editor de contorno (substitui a interação ponto a ponto)
O Tiago acha impraticável arrastar pontinho a pontinho. Quer juntar o laço do Photoshop (segurar o clique e passar pela peça) com algo que tolere erros sem recomeçar do zero.
2.1 Interação (sugestão; propõe melhor se houver, com justificação):
 - Três marcações: «é peça» (branco), «não é peça» (preto), «incerto» (cinzento). Laço à mão livre (segurar e arrastar), pincel com raio ajustável e borracha. Shift/Alt = adicionar/subtrair como no Photoshop. Cada traço é aditivo, com desfazer/refazer, por isso errar não obriga a recomeçar.
 - Com as zonas marcadas, a faixa «incerta» é resolvida por um algoritmo com marcadores (GrabCut, random walker, watershed com marcadores ou matting; escolhe e mede contra a GT) e a pré-visualização atualiza em tempo real. Pegas de vértice ficam só como retoque final opcional.
 - Pré-visualização lado a lado: scan, máscara atual, sobreposição, recorte final. Zoom e pan fluidos.
2.2 Janela maior e ajustável: redimensionável e/ou modo largo/ecrã inteiro. O Tiago sente-se limitado pela janela curta.
2.3 Persistência: overrides.jsonl continua append-only, com autor «manual», data, peça, folha e os traços/máscara. Nunca sobre os recortes de origem. As peças manuais ficam fora das métricas de CV, mas as máscaras servem de verdade de terreno (1.3).
2.4 Aprender com os cortes manuais: não prometas aprendizagem por peça (poucas amostras, cada peça é única). Guarda pares (automático, manual) por peça para medir o erro, calibrar limiares e priorizar peças suspeitas. Diz com honestidade o que é viável.
2.5 Ensaia em cópia primeiro; mostra capturas. Testes Playwright para o fluxo de traços e o desfazer.

Formato da resposta final
- [V]/[NT]/[F] com números; IoU e distâncias em mm.
- Por report (R0011, R0012 e os afetados): o que mudou, o que o Tiago tem de ver na GUI (termo de pesquisa), e se recomendas fechar.
- O que o Tiago tem de fazer: recortar com o editor novo mais peças de relva variadas para validação, e dizer quantas.
- Só me chamas para decisões que sejam do Tiago.
```

## Resultado

Commits (`main`): `d0bd183` métrica `src/maskcmp.py` + medição GT e detetor (`comido.py`, COMIDO.md) + decisões; `7eea52c` ativos desatualizados (`stale_assets`/`rebuild_stale`, `--stale`, `render/clean` por mtime); `1d9824c` baías com tab inteiro e em peças de contacto + razão `baia`; `75345f5` grau `recorte` nas Suspeitas; `bcf0b87` editor por traços (backend + GUI + verificação no arranque); `281d55a` Alpes: S0024/S0025 refeitas + lista; o commit das docs (este). Suite completa 310 passed, 1 skipped (205 s, OpenCV 4.11).

- **Parte 1.** A GT confirmou que o índice e a exibição atuais de P0651/P0657 não estão comidos (IoU exibida 0,928 / 0,919; em falta 11,6 / 2,9 mm²); a mordida vista pelo Tiago é o índice de 2026-11-01 servido por uma cópia com `pieces/`/`crops/` velhos (IoU 0,971 / 0,955 com a captura). Correção: verificação e rebuild automático dos ativos no arranque do servidor + `rebuild_scans.py --stale` (cópia desatualizada: 11 peças, 0 eventos, miniaturas 0,68 → 0,93). A medida contra a gémea foi substituída por um detetor local (máx. ponto a ponto, baía no limiar, folga por lado): 5/5 positivos, 0/63 controlos; no projeto encontrou 3 peças com um tab inteiro fora do contorno (P0844, P0879, P0852), recuperadas por `_BAY_TABS` com a porta completa (E-sym igual, 27 folhas só mudam nestas 3) e refeitas em `projects/alpes` (958 peças e estados iguais). P0198 e as filas 41–47 não disparam. A correção foi em `render.py`/`server.py` (causa) e em `segmentation.py` (os 3 tabs), não em `segmentation.py` para P0651/P0657, que não precisavam.
- **Parte 2.** Editor por traços feito: laço/pincel/borracha × peça/fundo/incerto, desfazer/refazer, GrabCut em Lab só croma (escolhido contra a GT: IoU 0,846 → 0,94, p95 1,35 → 0,63–0,68 mm; meta 0,3 mm [F]), pré-visualização ao vivo, 4 vistas, janela inteira, retoque por vértices, registo com traços/solver/RLE/contorno automático, `--pares`. Ensaio real em P0651: IoU 0,954, p95 0,54 mm com 3 traços.
- **Por fazer / pelo Tiago:** `git pull` e arranque do servidor na máquina da GUI antes de ver `P0651`/`P0657`; confirmar fisicamente os 3 tabs; recortar 10–12 peças de relva variadas com o editor (validação reservada); «remover contorno manual» na GUI; sinal (b) do detetor sem calibração; OpenCV 5.0 [NT].
