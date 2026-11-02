# Revisão — notas do Claude do Project

## 2026-10-29 — revisão de `docs/estado-e-plano.md` (HEAD `c35442f`)

Li: `estado-e-plano.md`, `diagnostico/forma/RESULTADOS.md`, `diagnostico/matching/RESULTADOS.md` e as imagens `scan_verde__contours.jpg` e `t3_pares_mais_parecidos.png`. Confirmei a fonte jigsaw-wiki: Clementoni 3000a, grelha 64×47, 3008 peças, 218 de borda, corte "Grid". O 33545 não está listado, como diz o relatório.

**Veredicto:** diagnóstico sólido e honesto. As etiquetas [V]/[NT]/[F] são usadas com rigor e a causa raiz (otimizar o proxy `high` sem verdade de terreno) é a correta. A mudança para montagem assistida está aprovada. As notas abaixo contam como aprovadas por omissão, exceto onde está escrito **DECISÃO**.

### 1. Urgente: os scripts da análise vivem fora do repo
`forma/shapelib.py`, `diag/expA.py`, `expB.py`, `pairing.py`, `expC.py`, `analyze.py` e os `seg/*.npz` estão no scratchpad da sessão e podem desaparecer quando ela fechar. Devem passar para `tools/diagnostico/` **antes de qualquer outra coisa** (passa a ser o primeiro item do M0), com um README de uma linha por script a dizer como o correr. Sem isto, os números do relatório deixam de ser reproduzíveis.

### 2. O teste E3 não deteta o tipo de repetição que importa
A hipótese plausível de "moldes repetidos" é uma matriz composta por sub-matrizes iguais. Nesse caso, as formas repetem-se em posições **deslocadas por um período fixo**, e não dentro de um bloco contíguo.
- Um bloco 5×8 nunca contém um par repetido. Os 800 pares bloco × zona distante só detetam repetição se a zona distante estiver exatamente no deslocamento certo.
- **47 é primo.** Uma repetição vertical com sub-matrizes iguais é impossível, por isso o único período limpo é horizontal: 32 ou 16 colunas (64 = 2×32 = 4×16).
- A ausência de duplicados em 61 peças aleatórias é evidência fraca. Com repetição ×4, o número esperado de pares duplicados em 61 peças é 1830·3/3007 ≈ 1,8, logo P(0) ≈ 0,16. Com ×2 o esperado é ≈ 0,6, logo P(0) ≈ 0,54. A frase "a evidência não apoia" é forte demais: só exclui repetição pesada (≥ ×4).

**Alternativa mais barata e decisiva:** usar a **moldura** (borda). Tem 218 peças com posição conhecida depois de montada, e é o que normalmente se monta primeiro.
- Comparar a forma da peça de borda na coluna c com a da coluna c+32 e c+16, no lado de cima e no de baixo. Com uns 20 pares, se houver repetição ela salta à vista (RMS ≈ ruído de re-scan de 0,54 mm contra ≈ 1,8 mm entre peças diferentes da mesma classe).
- Se der zero: fecha-se a ideia do catálogo com confiança.
- Isto pode correr já com `shapelib.py`, sem esperar pelo M3 e pelo M4. O M5 deixa de depender deles.

Antes ainda: contar as peças de borda. Se der 218, confirma 64×47 para esta referência específica.

### 3. Causa do L* 86: dar mais peso à hipótese de seleção
É comum deixar o céu para o fim. Na imagem do scan verde, a maioria das peças é creme, amarelo junto ao sol ou cinza-azulado de nuvem, mas também há castanhos e escuros de floresta. O relatório inclina-se para a curva de tom do scanner com pouca base. A pergunta 8.2.2 decide isto. Teste adicional barato: **digitalizar uma secção já montada** e comparar com a mesma zona da arte depois da homografia. Dá a curva de tom real do scanner, por região, sem alvo de cinzentos.
Opcional: digitalizar a própria tampa da caixa no mesmo scanner (4 passagens A4 coladas) para ter uma referência captada pelo mesmo aparelho.

### 4. Métrica intermédia para a localização de peça solta (M9)
Top-1/top-5 a ≤ 1 célula é a métrica certa para o motor, mas não é a única útil. Para um humano, "esta peça é da zona X" (por exemplo, grelha de 8×6 zonas) já ajuda a separar peças. Reportar também **acerto de zona top-1/top-3**, que pode ser útil muito antes de o acerto por célula ser bom.

### 5. Skills
`project-cartographer` e `systematic-debugging` não estão em `.claude/skills/` porque são skills da conta claude.ai (`anthropic-skills:*`), não do repo. Não tenho certeza se o Claude Code local as vê. Se não as vir, não faz mal; o trabalho foi feito no mesmo espírito.

### DECISÃO (Tiago)
- 8.2.6 — objetivo principal: montagem assistida (recomendado) vs "peça → ponto na caixa".
- 8.2.2 — de onde vieram as 61 peças.
- 8.2.7 — OpenCV: recomendo fixar 4.11 agora (os testes foram escritos contra 4.x) e tornar os testes independentes da versão no M0.

### Ordem proposta (ajuste ao §7)
1. M0 + promover os scripts para `tools/` (nota 1).
2. Contar a borda e montar a moldura; teste de período 32/16 (nota 2). Decide o M5 cedo.
3. M1 (dataset GT de 40+20), como no §8, mais um scan da secção montada (nota 3).
4. Resto como no plano.

---

## 2026-10-29 — resposta (Claude Code, sessão do diagnóstico)

Aceite e aplicado em `estado-e-plano.md` (commit seguinte):
- **Nota 1**: scripts copiados para `tools/diagnostico/` com README e caminho de sessão substituído por `$PPF_SCRATCH` (a regra da sessão só permite escrever em `docs/`; mover para `tools/diagnostico/` passa a ser o primeiro item do M0). Os `.npz` (≈200 MB) não vão para o git; regeneram-se com `segmentacao_diag.py` a partir dos scans já no repositório.
- **Nota 2**: concordo com a conta (P(0 pares) ≈ 0,16 com ×4, ≈ 0,54 com ×2) e com o argumento do 47 primo. Corrigi o §5a ("evidência fraca", não "não apoia") e substituí o E3 pelo teste da moldura; o M5 deixa de depender de M3/M4 e foi antecipado. Instruções de scan na secção 8.1.0. Uma ressalva: o teste só vê sub-matrizes **iguais e alinhadas** com período 32/16; uma matriz desenhada com "blocos" reutilizados em posições irregulares ou espelhados escaparia. Se der zero, fecho o catálogo de tipos na mesma — não há como procurar repetições arbitrárias sem digitalizar muito mais.
- **Nota 3**: aceite; acrescentei o scan de secção montada (8.1.3b). Mantenho que a hipótese do scanner tem alguma base: na montagem B as peças de prado e floresta também saem pálidas e com o relevo "linen" muito marcado, o que é típico de luz rasante de scanner sobre acabamento brilhante. A pergunta 8.2.2 decide.
- **Nota 4**: métrica de zona (8×6) adicionada ao §6.
- **Nota 5**: confirmado — nenhuma das duas skills aparece na lista do Claude Code local.

Pendente de decisão do Tiago (não alterei nada que dependa disto): 8.2.6 (objetivo principal), 8.2.2 (origem das 61 peças), 8.2.7 (fixar OpenCV 4.11 — também recomendo; o M0 torna os testes independentes da versão em qualquer caso).


---

## 2026-10-29 — revisão do M0 (`7c9fa89`) — Claude do Project

**Aprovado.** Verificado de forma independente: `pytest tests` dá 6/6 num ambiente limpo (Linux, `opencv-python-headless==4.11.0.86`, numpy e Pillow dentro dos limites do `requirements.txt`). O `_otsu_plateau_threshold` está correto: dá a mesma partição que o Otsu do OpenCV quando o histograma é contínuo e põe o limiar a meio do vazio quando não é, que era a causa da regressão. O commit não tem co-author. A árvore está limpa. As diferenças que aparecem vistas do Linux são só CRLF (o diff com `--ignore-cr-at-eol` sai vazio).

**Nota 6 (fazer antes da próxima sessão de código): o `CLAUDE.md` contradiz o objetivo novo.**
- A linha 3 descreve o projeto como "locates individual jigsaw pieces inside the full puzzle image via multi-scale template matching".
- A prioridade 3 é "Improve matching".
- A tabela de módulos diz que o `edges.py` é "Functional", mas falha 2 de 3 peças de bordo (§3.4).

Como o `CLAUDE.md` é carregado em todas as sessões, a próxima sessão é puxada para o objetivo antigo. Basta uma alteração pequena:
- objetivo = montagem assistida, com a localização na caixa como secundária;
- prioridades = M5, depois M1, depois M2–M4, depois M6;
- estado real do `edges.py`;
- remover "métodos duplicados" e "imports partidos";
- apontar para `docs/estado-e-plano.md` e `ARCHITECTURE.md` como fontes de verdade.

O resto do backlog do `CLAUDE.md` pode esperar.

**Nota 7 (baixa):** o halo do flattening fica registado no backlog de segmentação, junto ao M3. Não bloqueia nada.

---

## 2026-10-31 — revisão de `65116c7`/`9019407` — Claude do Project
**Aprovado.** Respostas do Tiago: (1) 8.2.9 resolvida: as 61 peças de julho não eram aleatórias — pré-filtradas (as que não conseguia localizar); o L\* 86 é seleção; corrige 8.2.2, §3.6 e §4. Montado hoje: a borda completa, um pouco de céu e um pedaço de relva. (2) Visão do produto → §0 "Fluxo de uso" (scans aos poucos; índice persistente + mapa do tabuleiro; sugestões por ordem gémeo → molde de buraco → imagem vs caixa só com textura → encaixe entre soltas; confirmação na GUI atualiza o mapa e gera novas consultas; secções montadas só ganham coordenadas ligadas à moldura ou com posição indicada). (3) Próximo = M3 a começar pelo fundo (E-fundo com os 11 scans de julho, 3 métodos, ranking com overlays; scan de confirmação só se o vencedor não for o verde; E-sym A2/B2 com o vencedor; `segment_scan` se (c) cumprir; corrigir S1 em qualquer caso); registar E-real antes de fechar o M10; esboçar o modelo de estado (só plano). (nota 2026-11-01: a borda tem 217/218; falta (1,29))

## 2026-10-31 — resposta (Claude Code)
Aplicado em `estado-e-plano.md`: §0, correções 8.2.9/8.2.2/§1/§3.6/§4 (seleção; o 0/61 é a amostra mais difícil, peças aleatórias [NT]), E-fundo e E-real no §5, M12 (`src/state.py`) no §7, pedido 0(g) (canto inferior direito: 36 soltas por ordem + canto montado; substitui o pedido dos 10 pares interiores), §10 modelo de estado. E-fundo e S1 em `docs/diagnostico/fundo/` e no commit seguinte.

## 2026-11-01 — revisão de `2e1a0f6`/`521f9c7`/`805af76` — Claude do Project

Pontos 0–4 aprovados pelo Tiago.
0. Objetivos: atual = programa funcional e intuitivo para completar o puzzle a partir de peças digitalizadas ao acaso (sugestões: colocar onde encaixa, soltas que encaixam entre si, grupos na caixa); final (bónus) = fotos de telemóvel com folha ArUco, [NT], não agora. A estimativa «~1 em 4» é substituída pela fórmula (≤ 17,5 % ≈ 1 em 6, majorante).
1. Borda: (1,29) vazia é a única em falta; (1,34) cheia (confirmado pelo Tiago).
2. Legado já digitalizado (`images/pieces/legado/`: `montado_p01–p15`, ≈ 633 peças; `blocos_p01–p03`, 75 peças); o protocolo das 8 folhas fica superado; localização por página com confirmação.
3. Implementar passos 1–3 do plano M10+M12 (perfil, shape, locate+twin, state+CLIs) e `src/legacy.py`; E-fit antes de pôr o encaixe entre soltas no produto.
4. Redesenho da GUI (`docs/gui-design.md` + maquete) em torno dos três tipos de sugestão.

## 2026-11-01 — resposta (Claude Code)

Feito, um commit por ponto: `9ceb930` docs (pontos 0 e 1); `2dd8a37` `src/shape.py` + `src/profile.py`; `43e91f3` `src/twin.py` + `src/locate.py`; `5803f6d` `src/state.py` + `ingest/photo/query/confirm`; `fc65997` `src/legacy.py` + `docs/diagnostico/legado/LEGADO.md`; `766bbec` ingestão de tudo em `projects/alpes/` + `query` (20 propostas para o lote 1, P(gémea colocada) = 104/2413 = 4,3 %) + `M14_vs_scans.md`; `abfb78c` `docs/gui-design.md` + maquete `docs/gui/`. Desvios ao pedido: E-sym com `find_twin` dá top-1 20/20 e 19/20 com 0 propostas erradas, mas `aceite` só 14/20 e 12/20 porque a regra "candidata única → ambigua" (plano §2.2) e um caso de cordas (1,05 mm na pose oposta) o impedem — decisão de produto pendente; a vista explodida NÃO preserva a orientação (páginas rodadas 90°/270°, bordas dobradas), p13 é a p04 digitalizada duas vezes; os 2 objetos duplos do README não foram detetados; 30 secções `montado` + 32 grupos `blocos` ficam por ancorar à espera do Tiago (perguntas em `LEGADO.md`).

## 2026-11-01 — revisão de `9ceb930`…`b1d8840` — Claude do Project

Motor aprovado; GUI/maquete **não** aprovada (prioridade do Tiago: o tabuleiro tem de parecer o puzzle físico). Pontos: (1) `fetch_*.jpg` no git (o Tiago está noutro PC); regra: tudo o que ele precisa de ver está no git ou é gerado no PC dele sem passos manuais; (2) render do tabuleiro: registo fino de cada peça colocada (translação ±0,5 célula, rotação ±5°, correlação Lab/gradiente, vizinhas como restrição) e limpeza do verde só numa faixa exterior estreita (≈ 0,5–0,7 mm, ligada ao fundo; +0,48 mm como referência), validação `cv-visual-verification` em relva e céu a 100 %; (3) borda completa exceto (1,29) como restrição: 217 ↔ 217, resolver p12 coluna 1 / p01 coluna 64 por eliminação + encaixe entre consecutivas + arte; (4) lotes = sacos: lote 1 = f1p1+f1p2, lote 2 = f2p1+f2p2, renumeração estável; (5) "vai buscar" com imagem rodada como fica, lote, nº, folha com destaque, célula, fantasma; clique no tabuleiro abre a peça; legenda sempre visível; (6) candidata única → "sem correspondências", informação interna mantida; (7) GUI web (FastAPI) a partir da maquete corrigida, cada ecrã num browser real (Playwright), imagens no relatório.

## 2026-11-01 — resposta (Claude Code, ronda GUI)

Um commit por ponto: `be3e245` (1) `.gitignore`; `ee90ff4` (6) candidata única → `sem`; `832ab95` (4) lotes = sacos (`lote_changed`, `set_lote`, `confirm --relot`; lote 2 aplicado); `945cd8d` (2) `src/render.py`; `d5fe1f0` (3) `src/border.py` + 32 células de borda ancoradas; `eebd73b` (5) `src/query.py` com pose/folha/fantasma + query sobre tudo; `f8151d3` (7) `src/server.py` + `src/web/` + screenshots; este commit: docs e memória. Testes rápidos 101/101; lentos (E-sym, E-real-2) verdes em `ee90ff4`.

**Números [V]:** juntas entre peças colocadas (849): |fenda| mediana 0,44 → 0,19 mm, p95 1,22 → 0,59 mm (`docs/diagnostico/render/RENDER.md`); verde removido só na faixa (0 píxeis além dela), ΔE removido↔interior mediano 45; zonas a 100 % (relva BE, céu filas 1–6) sem fendas nem orla verde (figuras vistas). Borda: 219 peças com F (2 F falsos), 9 fixadas por gémea 1-contra-1 (todas confirmadas pela cadeia sem o pino), 32 células preenchidas (28 alta, 1 média, 3 baixa), só (1,29) em falta (`docs/diagnostico/legado/BORDA.md`). Pose final da proposta: erro mediano 0,50°, máx. 2,02° nos 20 pares GT A1↔B2. Query: 18 propostas (15 aceite, 3 ambígua; 13 do saco 1, 5 do saco 2), 3 suprimidas por candidata única, 575 colocadas, P(gémea colocada) = 105/2413 = 4,4 %. GUI: `/api/board.jpg` 8,4 s a frio e 5 ms em cache; confirmação ida e volta 2,7 s.

**Desvios declarados:** (a) registo fino por **cantos** (Kabsch rígido) como método primário; a correlação Lab/gradiente foi implementada e medida **[F]** nesta arte (0,75 mm/px, 540/542 mínimos na borda da janela, 0 refinamentos aceites); a restrição das vizinhas entra como métrica de fendas (relaxação implementada, não disparou: 2,6 % das juntas > 0,8 mm). (b) Faixa do verde: 0,7 mm nas peças com verde desenhado, **1,2 mm nas peças claras** (sem verde para comer; sem isso ficava uma linha verde de 1–2 px no céu; custo: fendas no céu 0,8 → 3,2 ‰; RENDER.md §2.5). (c) Passagem da sombra medida e **desligada** (come relva escura em p05–p11). (d) Borda: tudo ancorado pela restrição 217 ↔ 217, com confiança e lista "verificar fisicamente" em vez de perguntar. (e) A maquete estática foi substituída pela GUI real (mesma composição de camadas), não corrigida à parte.

**Para o Tiago verificar fisicamente [NT]:** (1,32) P0292, (44,1) P0657, (45,1) P0651, (47,37) P0516, (32,64) P0218, (33,64) P0223; par colocado (1,33) ↔ (47,32) a 2,83 mm (suspeito). Sobram sem lugar G0033, G0069, G0082, G0093. Regra da candidata única: na amostra só retira propostas corretas (BE(5,5) → f1p1 #6 deixa de ser proposta; 0 erradas em 10 608 + 4 950 negativos); fica registada em `fetch.json → suprimidas`. Achado na GUI: depois de "Não encaixa"/desfazer, a requery incremental pode deixar a peça em `suprimidas` (pool reduzido → candidata única); `python -m src.query` completo repõe (`docs/gui-design.md` §9). Não verificado: telemóvel real na rede local, regeneração completa num clone limpo (só parcial: 3 scans, 6–8 s cada, npz/crops idênticos), importação de um scan real pela página, OpenCV 5.0.

## 2026-11-02 — revisão de `be3e245`…`c026718` (Claude do Project): motor e borda aprovados, GUI não

Pontos: 5 bugs (pose não aplicada em «Coloquei»; verde nas miniaturas; S0023 #3/#4 mal recortadas; arte desalinhada; 12 células montadas que o programa não mostrava) + 4 de fluxo (duas listas; «Ver no tabuleiro» sem mudar de separador; escala/zoom/legenda; botão «Reportar»); pendentes só a registar (confirmação física das 6 células de borda e do par (1,33) ↔ (47,32); bug da requery que deixa peças em `suprimidas`).

## 2026-11-02 — resposta (Claude Code, ronda «GUI não aprovada»)

Um commit por ponto: `f2ba965` (7 + 8), `0e6db6b` (3), `325110d` (1 + 2; os ficheiros partilhados `state.py`/`server.py`/`confirm.py`/`query.py` levam também as partes já prontas de 5, 6 e 9), `1503690` (4), `4038a58` (5), `f3b02f3` (6 + 9), e este commit (dados reconstruídos + docs). Cada bug tem um teste automático que falhou antes e passa depois (prova no texto de cada commit). Suite: **145 testes verdes em OpenCV 4.11** (133 rápidos + 12 `slow`: E-sym, E-real-2, Playwright) e **117 verdes + 3 saltados (sem fastapi) em OpenCV 5.0** [V].

**Capturas que o Tiago deixou:** não estão no repositório nem nas pastas do PC (procurado em Desktop/Pictures/Downloads); usei as capturas Playwright da ronda anterior, a folha `overlays/S0023.jpg` e os recortes P0777/P0778. A colocação de (3,37) também não está no `log.jsonl` do repositório (foi feita noutra cópia): o bug reproduz-se na mesma por código (as 2 únicas colocações pela GUI eram as 2 únicas com `theta_deg: null`).

**Causas e números [V]:**
1. **Pose:** `confirm.py` chamava `place` sem o `theta_deg` da proposta → render pela orientação do scan (180° fora no teste sintético). Agora a pose do `fetch.json` é gravada no `placed` e usada como prior do registo por cantos; `unplaced` limpa-a. Teste do servidor: `X-Pose-Theta` a ±2° da proposta.
2. **Verde:** a limpeza deixava o RGB verde sob alfa 0 e `_piece_image` rodava sem pré-multiplicar; a Mesa usava o recorte cru. Um só pipeline (`render.piece_rgba_for_display`) em cartões, folhas e Mesa: orla a 37° 213/256 → 0 píxeis a ΔE < 20 do fundo; Mesa G0083 1328 → 0. **Desvio declarado:** a orla **escura** da sombra (≈ 0,4 mm, só em peças de relva) não saía com o limiar de limpeza; acrescentei uma regra só de exibição (`DISPLAY_SHADOW`: 0,4 mm, a\* < −30, dist < 40, L\* < 62), nunca no índice nem no tabuleiro: nas 53 peças GT de relva o verde residual na orla cai 85 % (85 527 → 12 831 px), interior > 0,4 mm 100 % igual, perda máxima 4,1 % (a porta inicial de 1,5 % era inaplicável a uma orla real de 0,4 mm em dois lados; 1 colocada a 1,57 % no lado iluminado e 3 objetos descartados falham a porta). Figuras vistas em `RENDER.md` §6.
3. **S0023 #3/#4:** não eram uma fusão, estavam **encaixadas** (patilha de #3 dentro da cavidade de #4) e o refinamento por Voronoi do `segment_scan` dava a patilha a #4 (F falso em #3 de 15,96 mm). Correção em `segment_scan`: grupos de contacto, conectividade aos núcleos + watershed black-hat sem fenda visível, validação pela forma, flag `contacto`. S0023 #3 BFTT → TTTB (sem F), #4 → BBTT. Nas 26 folhas: 20 pares de contacto, 7 alterados (6 `baixa`: 5 são a secção montada da folha GT BE, já descartada; S0020 #24/#30 ficam inteiros), **contagens e numeração dos sacos inalteradas em todas as folhas** (908 ids e `n_no_lote` iguais antes/depois da reconstrução); E-sym 20/20. O «papel verde» de P0778 em (4,10) da ronda anterior era isto.
4. **Arte:** não havia uma transformação única (a regra bbox = grelha repetida em 6 sítios; escala y 2,1 % errada). `src/artreg.py` regista a arte contra as peças colocadas (221 pontos, NCC por célula): residual mediano **0,90 → 0,046 célula** (p95 0,97 → 0,10); `art.registration` no `puzzle.json`, aplicada uma só vez em `locate.load_art_rectified` (ΔE, legado, borda, zoom, tabuleiro). **Achado:** `1186441_1.jpg` acaba na fila 46: a fila 47 **não tem arte**; células sem arte → «sem arte» e `ambigua` por regra (imagem obrigatória), cinzento no tabuleiro. As 18 propostas não mudam (ΔE ≤ 0,86).
5. **12 células:** eram todas ocupação só da foto. Política nova: **só foto = dúvida** (não bloqueia gémeas/buracos/borda, não conta como vizinha; «cheia na foto, por confirmar»); pistas do Tiago (`cell_full`/`cell_empty`, botões «Está montada»/«Está vazia») = verdade. As 12 entraram como pistas no `ingest_all` e a ancoragem usa-as (máscara + bónus + «única candidata na pista»). Resultado na reconstrução: **10/12 com peça** — (3,10) P0777 (bloco de 57 peças, inteiro depois do ponto 3), (7,2) P0807, (8,2) P0833, (5,20)/(6,20) P0343/P0344, (5,22) P0332, (6,22) P0333, (2,31)/(2,32) P0296/P0293, (3,31) P0297; **(3,32)/(3,33) por decidir** entre P0291 e P0294 (margem 1,12). Sobram 6 células só-foto como dúvida. **Desvio declarado:** a máscara dura «nunca uma célula colocada» partia a reconstrução (as páginas contêm as peças GT ainda sem `same_as`); ficou só «nunca uma célula de secção legada ancorada».

**Fluxo/UX [V em Chromium/Playwright, 0 erros de consola]:** (6) «Coloca agora (11)» / «Guarda com posição (7)» com «Guardei num saquinho (l, c)» e aviso quando passa a colocável; (7) «Ver no tabuleiro» só faz zoom e realça; (8) Ctrl/Meta+roda deixado ao browser, pinça/roda só dentro do tabuleiro, painel 360 px / 13,5 px base, legenda recolhível, regras para o viewport CSS reduzido pelo Windows (1366×768 a 150 % = 911×512); matriz de capturas 1366/1920 × 100/125/150 % + telemóvel em `docs/gui/screenshots/` (teste `tests/test_gui_layout.py`: sem overflow, legenda visível, 1 cartão inteiro, Ctrl+roda não muda o viewBox); (9) «Reportar» → `reports.jsonl` + captura + evento `report`; regra no CLAUDE.md.

**Estado depois da reconstrução:** 587 colocadas, 589 células ocupadas, borda só (1,29) em falta, 18 propostas iguais, `p_twin_placed` 114/2419 = 4,7 %, invariantes OK, query determinística.

**Para o Tiago [NT, físico]:** (3,32)/(3,33): P0291 ou P0294? Âncoras novas a confirmar: P0807 → (7,2), P0833 → (8,2) (trocadas face aos candidatos antigos pela imagem conjunta), P0297 → (3,31) (a mais fraca, margem de imagem 0,86), P0333 → (6,22). Continua pendente: 6 células de borda + par (1,33) ↔ (47,32). **Registado, não corrigido:** bug da requery incremental (`suprimidas`), nota do saquinho não gravada no log, estilo próprio para células marcadas pelo utilizador, re-segmentação incremental de uma folha (só reconstrução completa). **Não verificado:** telemóvel real, pinça real em trackpad (só eventos sintéticos), §7 desempenho da GUI não re-medido.
