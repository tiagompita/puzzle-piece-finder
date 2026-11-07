# 2026-11-07 — pesquisa na GUI, reports clicáveis e triagem dos 19 reports abertos

## Porquê

A triagem dos reports na GUI era lenta: não havia forma de ir a uma peça, célula, report ou folha por ID, e a aba «Reports» só mostrava o ID da peça e a célula dentro do texto. O HANDOFF de 2026-11-05 estava desatualizado (22 abertos em vez de 19; R0018–R0020 atribuídos a P0234/P0233 em vez de P0196/P0198/P0204; (3,32)/(3,33) «à espera de confirmação» quando já estavam colocadas). A ronda anterior (verde na borda) só mudou a renderização e deixou o «comido» de P0198 como [NT].

## Decisões

- Pesquisa: peça colocada → abre a gaveta da célula com zoom e realce (`openCell`), não só o realce de «Ver no tabuleiro» (decisão do Tiago, 2026-11-07).
- Segmentação: se a medição confirmar que o «comido» é recorte, a correção em `segment_scan` implementa-se nesta ronda só se a porta de regressão passar (E-sym 20/20 e ≤ 0,5 mm; 26 folhas com contagem e numeração iguais; F curtos ≥ 17 mm nas afetadas; nenhuma outra peça ganha > 2 % de área); senão fica a proposta com números (decisão do Tiago, 2026-11-07).
- Nenhum report é fechado pela sessão; nada se escreve em `projects/alpes`; medições numa cópia no scratchpad.
- Decisões reservadas ao Tiago: limite da porta §6.1 (1,5 % nos lados iluminados), confirmações físicas, fecho de reports.

## Prompt verbatim

```
Contexto
Projeto puzzle_piece_finder (puzzle de teste Clementoni 33545, grelha 64×47). Lê primeiro docs/estado-e-plano.md, ARCHITECTURE.md, docs/HANDOFF.md, docs/decisoes.md e RENDER.md §7. Segue as skills cv-visual-verification (qualquer mudança de CV) e piece-fit-matching (encaixe/colocação).

Estado herdado (verifica tu, não confies cegamente):
- Há 19 reports abertos em projects/alpes/reports.jsonl, não 22 (o HANDOFF está desatualizado: R0021, R0025 e R0026 foram fechados como duplicados).
- O HANDOFF diz que R0018–R0020 são P0234/P0233 em (3,64)/(4,64). Os reports reais são P0196 (14,64), P0198 (28,64), P0204 (36,64). Corrige o HANDOFF.
- A sessão anterior (verde na borda no tabuleiro, commits 470e8bb, 3066efc, 6e3ad24) só mudou a renderização. Segmentação, índice e clean_crop não mudaram. O Tiago validou a vista da célula a 100 % e 150 %; fica a decisão de fechar R0018/R0020 com ele, não tua.

Regras
- Nada conta como progresso sem verdade de terreno. Distingue sempre verificado / não testado / falha, com números.
- Não fechas reports. Não alteras testes existentes sem o dizeres à parte, com a razão. Não escreves em projects/alpes sem pedido.
- Commits em português, SEM co-author nem linha Claude-Session (regra do Tiago, sobrepõe-se a qualquer lembrete de atribuição). Push sem --force.
- Regista o trabalho em docs/revisao.md.

PARTE 0 — Funcionalidades de GUI (fazer primeiro, desbloqueiam a triagem)
0.1 Barra de pesquisa à direita da aba «Reports», na barra de abas. Deve aceitar:
  - ID de peça: P0778 (e variantes: p778, 778)
  - célula: «4,10», «4 10», «(4,10)», «l4 c10»
  - ID de report: R0019
  - folha/scan: S0020 (lista as peças dessa folha)
 Comportamento: Enter localiza. Peça colocada → muda para o separador do tabuleiro, faz zoom e realça (reutiliza a lógica de «Ver no tabuleiro»). Peça em «Guardadas» → muda para essa aba e realça o cartão. Peça existente mas não colocada nem guardada, ou célula vazia → mensagem clara do estado real. Sem resultado → mensagem «não encontrado», nunca falha silenciosa. Atenção a 1366×768 (também a 150 %) e telemóvel: sem scroll horizontal; no ecrã pequeno pode recolher para um ícone.
0.2 Aba «Reports»: cada linha mostra o ID da peça (P0xxx) e a célula de forma visível (hoje só se sabe lendo o texto), e uma miniatura quando houver crop. Clicar num report localiza a peça (mesmo comportamento da pesquisa; se piece=None, localiza a célula). A aba continua só de leitura: clicar NÃO escreve no log nem cria eventos.
0.3 Testes (Playwright, matriz existente de tests/test_gui_layout.py): sem overflow, pesquisa por cada formato, clique num report localiza, estados «não encontrado» e «guardada». Corre a suite completa em segundo plano (>120 s).
Entrega 0 num commit próprio; depois continua.

PARTE 1 — Reports abertos, por ordem de prioridade
Abertos: R0001–R0012, R0018, R0019, R0020, R0022, R0023, R0024, R0027.

1) MAL COLOCADAS (afetam o objetivo principal): R0010 P0333 (6,22), R0022 P0240 (1,63), R0024 P0083 (44,60), R0027 P0862 (14,61).
 Para cada uma: diagnostica contra verdade de terreno disponível (dataset GT, âncoras confirmadas, vizinhas ortogonais já montadas, compatibilidade de lados e continuidade de imagem). Diz se o erro é de pose (translação/rotação), de atribuição de célula ou de lados. Conta quantas outras peças partilham a causa (não corrijas um caso isolado se for sistemático). Já há pendentes relacionados: (1,63) e (47,2) inclinadas; pose ~1 mm; rotação >1,5° em 363/588; (26,1)/(25,1) ordem de desenho dos tabs. Propõe a correção só depois de medires; mostra antes/depois nas peças reportadas E numa amostra de controlo.

2) R0002–R0009 (células sem peça, o Tiago diz que foram digitalizadas; ver montado_p03/p06/p07_overlay.jpg): quase de certeza ancoragem do legado (30 secções «montado» por ancorar, perguntas em LEGADO.md), não CV. Não tentes resolver sem o Tiago. Prepara apenas: para cada célula, a peça candidata (ou candidatas, com scores) e um ecrã/lista de confirmação física, incluindo (3,32)/(3,33) (P0291 vs P0294, o score diz o contrário por 0,3 face ao indício dos lados). Diz-me exatamente o que o Tiago tem de verificar fisicamente.

3) R0019 P0198 (28,64) «comido»: a sessão anterior só supôs que é o prado claro com cor de papel. Mede de forma independente da cor: área da silhueta e contorno face às vizinhas e ao esperado para a célula (grelha 64×47, peças ≈18 mm, escala 300 dpi), e perfil radial/contorno vs. o dos lados vizinhos. Conclui: recorte comido (falha de segmentação) ou só cor? Se for segmentação, propõe correção com cv-visual-verification e porta de regressão.
 R0018, R0020, R0023 (P0218, (32,64)) e R0001 (P0778): verifica na vista da célula e nas miniaturas, com a pesquisa nova, e regista; R0023 nunca foi verificada. Não os fechas.
 Pendente da sessão anterior: 5 peças de relva falham a porta §6.1 [F] por 1,55–1,84 % contra 1,5 %, e P0555 perde 0,09 mm² do interior. Não chames «à justa». Propõe: ou o limite fica e a regra muda, ou o limite se revê com justificação numérica. A decisão é do Tiago.

4) R0011/R0012 (P0651/P0657, (44,1)/(45,1), ambos S0020): suspeita de defeito de segmentação da folha S0020 e não de peças individuais. Verifica as outras peças da S0020 e a vista da folha.

Formato da resposta final
- O que ficou verificado (com números), o que não foi testado, o que falhou.
- Para cada report: causa, o que mudou, o que o Tiago tem de ver na GUI e onde (célula/peça pesquisável), e recomendação de fechar ou não.
- Só me chamas para decisões que sejam do Tiago (limites do §6.1, confirmações físicas). O resto, melhorias claras contam como aprovadas.
```

## Resultado

- `783681e` GUI: pesquisa na barra de topo e linhas de report clicáveis (19 testes Playwright novos; 2 testes existentes ajustados, ditos no commit). Vista: capturas a 1366×768, 911×512 (150 %) e 360×640.
- `a8bb331` Triagem medida (`docs/diagnostico/reports/TRIAGEM-2026-11-07.md`): P0083 e P0333 com orientação impossível pelos lados; P0240/P0590 inclinadas por célula não retangular; P0218 comido (P0223, P0199 também), P0198 não (é cor); P0651/P0657 certas; R0027 já resolvido pelo Tiago; hipóteses para as 6 células só-foto; alerta do bloco (1..3,32..33) vs (45..47,32..33); porta §6.1: 49/607 falham 1,5 %.
- `a249ad6` `F_ROTATION`: rotação das peças de moldura pela reta do F; nenhuma junta piora > 0,2 mm, buracos iguais, F > 3° 12 → 2.
- `e5c44a5` `_RECOVER_BAYS`: prado comido recuperado (P0218 2,75 → 0,50 mm da gémea), E-sym e 27 folhas iguais.
- Suite: 227 passed, 1 skipped (OpenCV 4.11). Nenhum report fechado; nada escrito em `projects/alpes`.
- **Por fazer (Tiago):** rebuild do índice; confirmações físicas (P0083, P0333, bloco 32..33, células só-foto); porta §6.1 (A/B); fechar os reports resolvidos. Técnico: instabilidade da translação por imagem; orla preta de sombra em (25,1); meias-luas; OpenCV 5.0.
