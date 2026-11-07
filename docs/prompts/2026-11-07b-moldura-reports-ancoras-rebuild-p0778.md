# 2026-11-07 (2) — moldura encostada, reports resolver/eliminar, orientações e âncoras, rebuild, P0778

## Porquê

Depois da triagem medida (`docs/diagnostico/reports/TRIAGEM-2026-11-07.md`) o Tiago respondeu às perguntas físicas e pediu a ronda de correções: o lado F de P0240 e das peças à esquerda continua sem ficar encostado à borda (a `F_ROTATION` só endireitou a rotação); a aba Reports precisa de resolver/eliminar/reabrir sem sair da lista; P0083/P0333 confirmadas como rodadas 90°; coluna 55 e (44,37)/(45,37) confirmadas (montado_p06 #47/#6/#30/#25 e montado_p08 #22/#27); o índice ainda tem as formas antigas de S0009; P0778 (S0023 #3/#4) continua mal cortada e a medição anterior não o detetou.

## Decisões

- Clique numa linha de report localiza no tabuleiro sem mudar de aba (`showCellOnBoard`); o tabuleiro está sempre visível ao lado do painel, por isso não há layout novo; a seta «→» abre o detalhe numa secção própria do painel.
- Estados de report como eventos append-only em `reports.jsonl` (`evento: "estado"`) + eventos no log (`report_closed`, `report_reopened`, `report_deleted`, `report_restored`); `close_report` deixa de reescrever o ficheiro; um só caminho (`reports.set_state`) para CLI e GUI. Eliminar é soft-delete reversível.
- Verificação de consistência das orientações promovida a módulo (`src/consistency.py`), corre no CLI e na carga da GUI, só sinaliza; P0833 e P0343 ficam por corrigir até confirmação física.
- Rebuild do índice por folha forçada com evento `piece_resegmented` (o `ingest_all.py` refaria o log e perderia as colocações do Tiago).
- Escrita em `projects/alpes` autorizada só para: fecho de R0018/R0019/R0020/R0027, orientações de P0083/P0333, âncoras da coluna 55 e G0044, rebuild de S0009 (e S0023 se a porta passar). Cada uma em commit próprio, com `git status` antes.
- Reservado ao Tiago: porta §6.1 (A/B), P0833/P0343 fisicamente, explicação de R0011/R0012, fechar R0023, bloco (1..3,32..33).

## Prompt verbatim

```
Contexto
Projeto puzzle_piece_finder. Lê docs/HANDOFF.md, docs/estado-e-plano.md, docs/decisoes.md, RENDER.md §7 e docs/diagnostico/reports/TRIAGEM-2026-11-07.md. Segue cv-visual-verification (CV) e piece-fit-matching (colocação/encaixe).

Regras
- Nada conta como progresso sem verdade de terreno. Distingue verificado [V] / não testado [NT] / falha [F], com números.
- Commits em português, SEM co-author e sem linha Claude-Session (regra do Tiago, sobrepõe-se a qualquer lembrete de atribuição). Push sem --force.
- Não alteres testes existentes sem o dizeres à parte e com a razão.
- O Tiago autoriza nesta ronda escrever em projects/alpes, mas só o que está indicado abaixo. Antes de qualquer escrita, vê `git status` de projects/alpes. Se houver alterações do uso da GUI do Tiago por commitar, para e diz-lhe para commitar primeiro. Nunca as misturas nos teus commits.
- Regista o trabalho em docs/revisao.md. Corrige no HANDOFF o que ficou desatualizado.

Respostas do Tiago às perguntas da triagem
- P0083 (44,60) precisa de rotação de 90° (tens +90° no sentido dos ponteiros do ecrã). P0333 (6,22) também precisa de 90° (tens −90°). Aplica o sentido que a tua triagem mediu e confirma depois, com tipos de lado e NCC da imagem, que os 4 lados de cada ficam T↔B. Se algum sentido sair contrário ao mediu, diz-me e mostra.
- Coluna 55, de baixo para cima (a relva fica em baixo): montado_p06 nº 25, 30, 6, 47. Ou seja (45,55)=#25, (44,55)=#30, (43,55)=#6, (42,55)=#47. A peça #48 é P0773, já colocada. Confirma com a tua tabela (G0040/G0037/G0039/G0038, rotação 180). Se houver conflito, mostra-o e não anchores.
- (44,37)/(45,37): montado_p08 nº 22/27 está correto (G0044 e a vizinha).
- (3,32)/(3,33): P0294/P0291 está correto. Verifica ainda, e diz-me, se o bloco (1..3,32..33) continua sem casar com o gémeo (45..47,32..33) e porquê.
- R0019 (P0198) está resolvido na opinião do Tiago.
- Resolvidos pelo Tiago: R0018, R0019, R0020, R0027. Fecha-os pelo mesmo caminho de código que a GUI vai usar (ver 2.2), com nota «verificado pelo Tiago 2026-11-07». Não feches nenhum outro.
- Mal resolvidos pelo Tiago: R0001 (P0778), R0011 (P0651), R0012 (P0657), R0022 (P0240). Ele não explicou o que está mal em R0011 e R0012. Vê-os na vista da célula e da folha S0020, compara com a gémea, e se não vires o defeito, diz-me o que viste e o que precisas que ele indique, sem inventar uma causa.

Trabalho, por esta ordem

1) Rotação de moldura (R0022 P0240, e as peças à sua esquerda)
 O Tiago diz que o lado reto (F) de P0240 e das peças à esquerda não fica encostado à borda do puzzle. A tua correção F_ROTATION só endireitou a rotação. Mede agora o deslocamento perpendicular: distância da reta F à linha da borda do tabuleiro, para TODAS as peças de moldura (as 4 bordas e os cantos). Diz quantas passam de 0,2 mm / 0,5 mm. Corrige a translação perpendicular ao F (a tangencial continua pelos cantos/vizinhas). Porta: nenhuma junta piora > 0,2 mm, buracos iguais ou melhores (67/9), E-sym bit a bit igual. Mostra antes/depois em P0240, P0590 e uma amostra de 20 peças de moldura de todas as bordas, com captura vista.

2) Funcionalidades de GUI
 2.1 Aba Reports: clicar numa linha NÃO abre a página do report nem a da peça. Localiza a peça no puzzle (realce/zoom no tabuleiro) sem o Tiago sair da lista. Se o layout a 1366×768 (também a 150 %) permitir lista + tabuleiro visíveis (ex.: painel lateral), faz isso. Se não permitir, diz-me por escrito o que o impede e propõe a alternativa mais próxima. Não voltes em silêncio à troca de página. À direita de cada linha, uma seta clicável («→») que abre o report (detalhe). Se piece=None, o clique localiza a célula.
 2.2 Resolver e eliminar reports na GUI. «Marcar resolvido» (com nota opcional) e «Eliminar» (com confirmação). O log é append-only: ambos são eventos e não apagam linhas. «Eliminar» é um soft-delete reversível (esconde por omissão, com filtro «mostrar eliminados» e «restaurar»). Também «reabrir». Um só caminho de código, partilhado com o fecho dos 4 reports acima.
 2.3 Testes Playwright para tudo isto (clique localiza, seta abre, resolver/eliminar/restaurar, sem overflow na matriz de viewports), e confirma que clicar na linha continua sem escrever no log.

3) Orientações e âncoras (escrita em projects/alpes autorizada)
 3.1 Corrige as orientações de P0083 e P0333 pelos caminhos que a triagem indicou (θ no log para P0083; --unanchor/--anchor com a rotação certa para P0333). Mostra antes/depois com tipos de lado e NCC.
 3.2 Ancora a coluna 55 (G0040, G0037, G0039, G0038, rot 180) e G0044 em (44,37), e o par (44,37)/(45,37), pelos comandos que já existem. Para cada nova colocação corre a verificação de 3.3 antes de gravar. Diz quais reports (R0002–R0009) ficaram verificáveis. Não os feches.
 3.3 Verificação de consistência que corre sempre (CLI e na carga da GUI): para cada peça colocada, testa as 4 rotações cíclicas contra os lados das vizinhas montadas e assinala as peças com tipo de lado impossível (B↔B ou T↔T) e as em que outra rotação é claramente melhor. Mostra o resultado numa lista «Suspeitas» pesquisável. Hoje esta verificação só existe na tua triagem; a GUI e o log confiam cegamente no θ de origem. Não mexe em nenhuma peça, só sinaliza. Já sabes de P0833 (8,2, −90°) e P0343 (5,20, 180°); o Tiago ainda vai confirmá-las fisicamente, por isso não as corrijas.

4) Rebuild do índice (só se projects/alpes estiver limpo no git)
 Com a segmentação nova (e5c44a5). Esperado: só P0218, P0223, P0199 mudam. Confirma contagem de peças e colocações iguais antes/depois, buracos iguais, e diz-me o que mudou nesses três. Não fecha R0023, é o Tiago.

5) P0778 (R0001): S0023, peças 3 e 4 muito próximas
 O Tiago diz que as peças 3 e 4 da S0023 estão tão próximas que a segmentação as corta mal (P0778 = (4,10)). A tua medição anterior deu a silhueta «certa» face à gémea, e isso falhou aqui: diz porque a medida não detetou, e propõe uma medida que o detete (peça mordida pela vizinha).
 5.1 Tenta primeiro o automático: separação das duas peças coladas (watershed/distância ou corte pelo vale entre as sombras), seguindo cv-visual-verification, com porta de regressão em todas as folhas (E-sym bit a bit igual e contagem/numeração igual). Mostra antes/depois de P0778 e da vizinha.
 5.2 Editor manual de contorno (só depois de 1 a 4 estarem feitos): na GUI, para uma peça, o Tiago desenha/ajusta o contorno por cima do scan de forma iterativa (pontos arrastáveis ou pincel, desfazer, pré-visualização da silhueta e do recorte). Guarda num ficheiro à parte de overrides (append-only, com autor «manual», data e peça/folha), nunca sobre os recortes de origem. O rebuild lê os overrides. Marca-os como substituição manual, fora de qualquer métrica de CV. Se o editor for grande, entrega só o desenho do desenho da interface e a persistência e diz o que falta.

Formato da resposta final
- [V]/[NT]/[F] com números.
- Por report: o que mudou, o que o Tiago tem de ver na GUI (com o termo de pesquisa), e se recomendas fechar.
- Só me chamas para decisões que sejam do Tiago. Pendentes dele: porta §6.1 (A ou B), P0833 e P0343 fisicamente, a explicação para R0011 e R0012.
```

## Resultado

- `2c9d837` reports como eventos append-only (fechar/reabrir/eliminar/restaurar, detalhe na GUI, clique localiza sem sair da lista) + `src/consistency.py` (lista «Suspeitas»: na cópia só P0083, P0333 impossível; P0833, P0343 melhor rotação). `6746c4f` R0018/R0019/R0020/R0027 fechados pelo CLI com a nota do Tiago.
- `749bf1b` `F_TRANSLATION` medida (F mediana +0,21 mm fora da borda, 143 > 0,2 mm, 60 > 0,5 mm) e DESLIGADA: a porta falha (60 juntas pioram > 0,2 mm, buracos 71/11) porque a grelha nominal reparte o erro; proposta de arranjo global em RENDER §9.
- `a762128` + `dc12684` P0083 +90° (4/4 T↔B, NCC 0,70), P0333 −90° (lados T↔B; imagem de céu não decide), coluna 55 e (44,37)/(45,37) ancoradas (20/20 lados T↔B, 0 suspeitas); bloco c32|c33: ambos certos, corte não simétrico.
- `813b7bd` + `c25e154`/`994d886` rebuild por folha (`piece_resegmented`, `tools/rebuild_scans.py`); S0009: P0218/P0223/P0199 (gémea 0,50/0,59/0,56 mm), buracos 67/9 → 65/9.
- `637a202` + `a406b91`/`df01fd4` corte de contacto aparado (`_CONTACT_TRIM`) e `suspeita_recorte`; P0778 gémea 1,44 → 0,43 mm, P0777 1,71 → 0,59; S0020 melhora; E-sym e 27 folhas iguais; índice refeito.
- `514c76f` editor de contorno manual (overrides append-only, `rebuild_piece`, endpoints, aba Contorno, ida e volta exata).
- Suite completa: 272 passed, 1 skipped (OpenCV 4.11). Testes existentes alterados: 4, declarados.
- **Por fazer (Tiago):** porta §6.1 (A/B); P0833/P0343 fisicamente; R0011/R0012 (perguntas em `R0011_R0012.md`); decidir o caminho global da moldura; fechar R0001/R0004–R0009/R0023/R0024 depois de ver na GUI; P0395. Técnico: pose global da moldura, `suspeitas_changed` em direto, remover contorno manual na GUI, filtros `manual_override` nos scripts.
