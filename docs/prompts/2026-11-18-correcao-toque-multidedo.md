# 2026-11-18 — Correção do toque multi-dedo no tabuleiro (iPhone)

## Porquê
Teste do Tiago no iPhone (Brave/WebKit, GUI nova `/novo/`, depois da F2e): (a) a pinça para afastar às vezes aproxima; (b) depois de uma pinça o tabuleiro fica num estado errado (um dedo faz zoom e os toques num lugar deixam de funcionar até recarregar).

## Decisões
- toque duplo = dois toques completos sem outro dedo no ecrã; um 2.º dedo cancela o pendente;
- `pointercancel`, `lostpointercapture` e `pointerup` em qualquer sítio limpam o dedo; sem dedos, estado inicial;
- sai um dedo da pinça: o que fica arrasta sem salto.
- Decisões minhas e causas: `docs/decisoes.md` (2026-11-18).

## Prompt verbatim
Bug no iPhone (Brave/WebKit, teste do Tiago 2026-11-18, GUI nova /novo/, depois da F2e 3dcfcc8):
(a) uma pinça para afastar às vezes aproxima, como se o 2.º dedo contasse como toque duplo;
(b) depois de uma pinça, o tabuleiro fica num estado errado: arrastar com um dedo faz zoom sozinho e os toques num lugar deixam de funcionar (até recarregar).

Antes de corrigir:
1. Lê os erro_cliente de hoje em projects/alpes/logs/servidor-20261118.log (o Tiago testou com --lan) e reporta-os.
2. Reproduz em Chromium com toque REAL multi-dedo (CDP `Input.dispatchTouchEvent`, não só um ponteiro emulado): pinça para afastar; pinça com os dois dedos a pousar com < 250 ms e < 30 px um do outro; um dedo a levantar antes do outro; `pointercancel` a meio (o iOS manda-o); depois de cada um, um arrasto de um dedo e um toque simples.
3. Bisect: o (b) já existia antes da F2e (d510f0a)? Diz qual commit o introduziu.
4. Hipóteses a confirmar ou refutar com evidência: o toque duplo conta um pointerdown com outro dedo ainda pousado; o mapa de ponteiros não remove o dedo em pointercancel / lostpointercapture / pointerup fora do elemento; o estado da pinça não é limpo quando sobra um dedo.

Correção (critérios fixados antes):
- toque duplo = dois toques COMPLETOS (pousar e levantar, sem movimento > limiar) com NENHUM outro dedo no ecrã; um 2.º dedo cancela o toque duplo pendente e o toque simples;
- pointercancel, lostpointercapture e pointerup em qualquer sítio limpam o dedo;
- quando sai um dedo da pinça, o que fica passa a arrasto a partir da posição atual, sem salto;
- quando não há dedos no ecrã, o estado volta ao inicial.

Testes antes do código (a falhar antes), com os cenários do ponto 2. Suite completa com `.venv/Scripts/python.exe -m pytest tests/`; lista no commit os testes existentes alterados, com o motivo; commit sem co-author.

Fecho: docs/decisoes.md (2026-11-18, correção do toque); HANDOFF; docs/prompts/; `graphify update .`; reporta [V]/[NT].

## Resultado
Fechado. Ver `docs/decisoes.md` (2026-11-18). Para o Tiago confirmar no iPhone [NT]: pinça para afastar (nunca aproxima), arrastar e tocar num lugar depois de uma pinça, toque duplo.
