# Redesenho da GUI — especificação (opção A, «Próximo passo»)

_2026-11-11. Decidido pelo Tiago a partir de maquetes feitas no Project. Este ficheiro descreve o destino; o plano por fases está no fim. As maquetes em `maquetes/*.dc.html` são a referência de aspeto (cores, tamanhos, textos): são HTML com estilos inline, legíveis mas não executáveis fora do editor onde foram feitas._

## 1. Objetivo e utilizador

- Utilizador: o Tiago, ou uma pessoa que perceba o programa com uma explicação rápida.
- O ecrã principal responde a uma pergunta: «que peça vou buscar agora e onde a ponho?».
- Tudo o que só serve a quem desenvolve sai do ecrã principal e vai para «Diagnóstico».
- Regra de confiança honesta: as palavras de confiança só dizem «quase certo» onde há precisão medida que o sustente. No resto, «a confirmar por ti». Critério numérico decidido em 2026-11-11: §8.3.

## 2. Vocabulário visível

| Hoje | Passa a |
|---|---|
| (4, 57) | Linha 4 · coluna 57 |
| aceite / alta | quase certo |
| ambígua / média | a confirmar por ti |
| Coloquei | Encaixa |
| Não encaixa | Não encaixa (mantém) |
| Vai buscar | Montar (aba) / Próxima peça (cartão) |
| Lotes + Guardadas | Peças |
| Mesa / grupos por ancorar | Grupos soltos |
| É aqui | Fixar aqui |
| P1203, classe BBBT, fonte log, mm, margem, ΔE, fit_version | só em Diagnóstico (o identificador P#### aparece em pequeno no painel da peça) |

## 3. Navegação

Barra de topo: nome do puzzle e progresso («672 de 3008 peças», mais «N em grupos soltos» quando houver); três abas **Montar · Peças · Importar scan**; lupa (procurar peça ou célula); botão «⋯» (Diagnóstico e definições).

## 4. Ecrãs

### 4.1 Montar (`maquetes/Main.dc.html`)
- Tabuleiro à esquerda; alvo da peça atual a âmbar com etiqueta «vai aqui»; o tabuleiro desloca-se para mostrar o alvo.
- Painel à direita com **um cartão**: peça rodada como fica, «Saco N» e «peça nº X» em grande, «Linha · coluna», confiança em palavras com 3 traços, botões **Encaixa** e **Não encaixa**, ligações «Saltar por agora» e «Porquê esta peça?».
- Fila ordenada por saco: esgota um saco antes de passar ao seguinte; dentro do saco, por confiança. Contador «1 de 3 neste saco · 10 no total».
- Lista «A seguir» com as 3 seguintes.
- Legenda curta por baixo do tabuleiro (3 entradas).
- Atalhos de teclado (não anunciados no ecrã, listados em Diagnóstico): Enter = Encaixa, N = Não encaixa, S = Saltar, Ctrl+Z = desfazer a última ação.
- Estados a desenhar: fila vazia («Nada para ir buscar. Digitaliza mais um saco.» com botão para Importar), a preparar/reconstruir (progresso), erro.

### 4.2 Depois de «Não encaixa» (`NaoEncaixa.dc.html`)
- Pergunta opcional «Porquê?» com três respostas: «A forma não entra», «Entra, mas a imagem não bate», «Não sei». Não bloqueia: «Próxima peça» avança sem responder.
- «Enganei-me, desfazer».

### 4.3 «Porquê esta peça?» (`Porque.dc.html`)
- Três frases com 3 traços cada: forma, imagem, distância para a segunda candidata. Botão «Ver números» abre o Diagnóstico nessa sugestão.

### 4.4 Tocar numa peça do tabuleiro (`Celula.dc.html`)
- Saco e nº em grande, linha e coluna, estado («No lugar · posta por ti a …»), **a folha original com a peça marcada** (toca para ampliar), identificador P#### em pequeno.
- Ações: **Tirar do lugar** (sem confirmação, desfaz-se), «Corrigir recorte», «Algo está errado» (abre o report).

### 4.5 Tocar num lugar vazio (`CelulaVazia.dc.html`)
- «Pôr uma peça aqui»; a sugestão do programa, se houver; «Já tem peça, mas não a digitalizei» (o `cell_full` de hoje).

### 4.6 Pôr uma peça à mão (`PorPeca.dc.html`)
- Entra-se pelo lugar. Passo 1: saco e nº, ou «Escolher na folha». Passo 2: pré-visualização da peça no lugar com as vizinhas, botão «Rodar», e três verificações em palavras (lado direito se for borda, forma com as vizinhas, imagem com as vizinhas).
- Se uma verificação falhar: aviso claro e «Pôr na mesma» (não bloqueia).
- Usa a ação `place` existente (origem manual).

### 4.7 Peças (`Pecas.dc.html`)
- Um bloco por saco, grelha de peças com nº; filtros por estado: Todas, Para ir buscar, Em grupos soltos, Já no tabuleiro, À espera. Estado pela moldura da peça, com legenda nos próprios filtros.

### 4.8 Importar scan (`Importar.dc.html`)
- Três passos numerados (ficheiro, nº do saco proposto, Importar) e as três regras de captura em imagens (fundo verde, peças afastadas, 300 dpi).

### 4.9 Grupos soltos
- **No tabuleiro** (`GrupoTabuleiro.dc.html`): o grupo aparece em cima do tabuleiro sem estar no lugar certo, com contorno violeta e sombra. Move-se com **Ctrl + arrastar** ou pelo botão «Mover»; no telemóvel, manter o dedo. Move-se de célula em célula; não sai do tabuleiro nem se sobrepõe a peças colocadas ou a outros grupos. As peças continuam clicáveis. Barra do grupo: Mover, Rodar, Fixar aqui. «+» nos lados livres para acrescentar peça. «Lugar provável» a tracejado quando o programa tem uma zona.
- A posição livre não significa nada para o motor: as células por baixo continuam vazias e o alvo de uma sugestão desenha-se por cima do grupo. Um grupo solto não conta no progresso.
- A posição livre tem de ficar guardada (sobrevive a recarregar e a outro dispositivo).
- Painel do grupo: Acrescentar uma peça, Levar para o lugar provável, Fixar aqui (o `anchor` de hoje), Tirar uma peça do grupo, Desfazer o grupo.
- **Lista** (`Grupos.dc.html`), **peça que se junta a um grupo** (`JuntarGrupo.dc.html`) e **o grupo já tem lugar** (`GrupoLigou.dc.html`).
- **Âmbito:** primeiro os grupos que já existem (secções e blocos sem lugar, a aba Mesa de hoje). Os grupos propostos pelo programa entre peças soltas ficam **fora** até o Tiago fazer o teste físico dos 10 quadrados (medição de 2026-11-10: 7 quadrados com margem ≥ 1,05 em 525 soltas, todos céu, precisão real por medir).
- **Atualização 2026-11-11:** o teste físico deu 10/10 (§8.6), por isso os grupos propostos entram na F4b (§7), sempre com confirmação física antes de passarem a grupo.

### 4.10 Corrigir recorte (`Editor.dc.html`)
- Dois pincéis: «Tirar» (sombra, fundo) e «Acrescentar» (peça que ficou cortada); tamanho; Desfazer; Recomeçar; «Como fica»; Guardar / Cancelar. «Usar o recorte da peça gémea» e «Mais opções» (vértices, vistas, incerto) recolhidos. O motor (A2, ronda 10) não muda.

### 4.11 Diagnóstico (`Diagnostico.dc.html`)
- Números das sugestões, Atividade, Problemas reportados, Peças suspeitas, Rejeições e acertos, Manutenção. É para onde vai tudo o que sai dos outros ecrãs.

## 5. O que o servidor ainda não faz (confirmado no código em 2026-11-11, ver `F0_INVENTARIO.md` §3)

1. **Desfazer uma rejeição** (`twin_rejected` / `hole_rejected`): hoje não há evento que a anule.
2. **Motivo da rejeição** (forma / imagem / não sei), campo opcional no evento.
3. **Posição livre de um grupo solto** guardada no log.
4. **Verificações de uma peça escolhida à mão** para um lugar (forma e imagem com as vizinhas) antes de `place`.
5. **Ordenação da fila por saco.**

## 6. Critérios de aceitação

- No ecrã Montar não aparece nenhum termo da coluna «Hoje» da tabela do §2.
- Contagem de palavras e de botões visíveis no ecrã principal, antes e depois (como se fez para a Mesa em `docs/gui-design.md` §15).
- Confirmar uma peça: no máximo 1 clique a partir do ecrã Montar. Desfazer a última ação: 1 clique.
- Funciona a 1366×768 e a 390 px de largura, sem scroll horizontal, alvos de toque ≥ 44 px.
- Nenhuma capacidade de hoje se perde: cada elemento da GUI atual tem destino (ação, Diagnóstico ou removido com justificação) na tabela de inventário da fase 0.

## 7. Fases

_(Revisto 2026-11-11 depois do inventário da F0: F1 partida em F1a/F1b; desfazer a rejeição e o motivo passam para a F1; F4b nova. O plano detalhado está no inventário, [`F0_INVENTARIO.md`](F0_INVENTARIO.md).)_

- **F0 — Inventário, sem código.** Tabela com cada elemento e texto da GUI atual → destino. Lista dos testes `tests/test_gui_*` e `test_server` que dependem de textos ou estrutura que vão mudar. Confirmação dos 5 pontos do §5. **Feito 2026-11-11:** [`F0_INVENTARIO.md`](F0_INVENTARIO.md).
- **F1a — Extrair o tabuleiro (2026-11-11).** O código do tabuleiro sai de `app.js`/`app.css` para `src/web/core.js`, `src/web/board.js` e `src/web/board.css`, sem mudar comportamento; o toque no tabuleiro passa por um gancho `S.onBoardTap` que a GUI atual define com o código de hoje. Suite antiga verde com as mesmas asserções, capturas antes e depois iguais, commit próprio. OK do Tiago antes da F1b.
- **F1b — Casca nova e Montar**, atrás de um interruptor (`/novo/`, com `/?ui=novo` e `python -m src.server --ui novo` como atalhos), com a GUI atual intacta por omissão. Inclui §4.1 a §4.3, a ordenação por saco (§8.2), **desfazer a rejeição e o motivo** (§5.1, §5.2; antes estavam na F2) e o desfazer de «Encaixa».
- **F2 — Célula, lugar vazio, pôr e tirar à mão, desfazer global.** A verificação de uma peça posta à mão **não bloqueia** (2026-11-11): enquanto calcula, mostra «a verificar…» e deixa «Pôr na mesma».
- **F3 — Peças e Importar.**
- **F4 — Grupos soltos no tabuleiro**, só para os grupos que já existem.
- **F4b — Grupos propostos pelo programa entre peças soltas (nova, 2026-11-11).** O teste físico dos 10 quadrados de 2026-11-10 deu 10/10 (§8.6). Cada grupo proposto só passa a grupo depois de o Tiago o confirmar fisicamente; a confiança segue a regra do §8.3; há contador de acertos e falhas.
- **F5 — Corrigir recorte e Diagnóstico.** O Diagnóstico lista as rejeições, cada uma com «anular», para desfazer rejeições de sessões anteriores (2026-11-11).
- **F6 — A GUI nova passa a ser a de omissão;** remove-se a antiga e o interruptor; atualiza-se `docs/gui-design.md`.

Cada fase fecha com a suite verde, capturas a 1366 e a 390 px, e o OK do Tiago antes da seguinte. Os testes existentes que tenham de mudar estão listados no inventário; o commit que os muda diz quais e porquê.

## 8. Decisões do Tiago sobre o plano (2026-11-11)

Respostas às perguntas P1–P14 do plano da F0, tal como o Tiago as deu.

### 8.1 Desfazer e motivo (P1)
- Desfazer a rejeição e o motivo entram na F1 (F1b). O motivo é um **evento à parte**, ligado à rejeição, porque a pergunta «Porquê?» não bloqueia e a rejeição já está gravada quando a resposta chega.
- **Uma ação desfeita não conta**, nem como acerto nem como falha (contador `alta`, `python -m src.fit --relatorio`, contadores futuros).

### 8.2 Fila por saco (P2)
- A fila começa pelo **saco do último scan importado**. Sem importação recente, começa pelo saco com mais «quase certo».
- O saco fica fixo até esgotar.
- «Saltar» manda a peça para o fim do saco; saltada uma segunda vez, para o fim de tudo. Só nesta sessão (não sobrevive a fechar o browser).

### 8.3 Regra do «quase certo» (P3)
- «quase certo» só por **origem × zona** com **n ≥ 10** decisões físicas e **limite inferior de Wilson (95 %) ≥ 0,80**. Tudo o resto diz «a confirmar por ti».
- Vale para gémeas, buracos e (F4b) grupos propostos.

### 8.4 Traços do «Porquê» (P4)
- 3 traços = passa com folga; 2 = passa; 1 = falha.
- **«Não testado» tem aspeto próprio**: traços vazios e as palavras «não verificado». Não se confunde com «falha».

### 8.5 Grupos (P5, P6)
- F4 fica com desenhar, mover, rodar, fixar e soltar os grupos que já existem. «Acrescentar / tirar uma peça», «Desfazer o grupo», os «+», «Junta-se a um grupo» e «O grupo já tem lugar» ficam para depois.
- «Tirar do lugar» numa peça de um grupo fixado **solta o grupo inteiro**, e o texto do botão diz isso. Tirar só uma peça fica para depois.
- «Fixar aqui» num grupo «a confirmar por ti» mantém uma confirmação de um clique.

### 8.6 Grupos propostos entre soltas: teste físico (alteração 4)
- **[V, Tiago, 2026-11-11]** Os 10 quadrados 2×2 propostos em 2026-11-10 (ligações melhor-mútuas entre soltas, todas do céu) **encaixam os 10**, incluindo os 3 com margem abaixo de 1,05 (1,044, 1,030 e 1,021). **São 10 casos**: chegam para abrir a F4b, não para calibrar uma precisão. Os quadrados 11–17 ficam para o Tiago testar onde o método começa a falhar (`docs/diagnostico/grupos_soltos/QUADRADOS.md`).

### 8.7 Cartão, painéis e peças (P7–P13)
- **P7:** o cartão do Montar não tem ligação «ver na folha». Tocar na imagem da peça amplia-a e mostra a folha.
- **P7b:** «Tirar do lugar» é **neutro**. Passa a contar como falha da sugestão se outra peça acabar nesse lugar.
- **P8:** «Afinal está vazio» fica no painel, visível quando o lugar foi marcado pelo Tiago. A pose manual («Ajustar posição») fica em «Mais opções» do painel.
- **P9:** os saquinhos continuam (painel da peça em Peças, filtro «À espera»). «Descartar» fica em «Mais opções».
- **P10:** o Lugar vazio mostra a arte da caixa.
- **P10b:** em «Pôr uma peça à mão», o «Rodar» do Tiago manda, e as verificações recalculam para essa rotação.
- **P11:** as regras de captura em Importar são desenhos simples.
- **P12:** o progresso conta as colocadas mais os lugares marcados cheios pelo Tiago. «Cheia na foto, por confirmar» não conta. A barra fica.
- **P13:** «À espera» = soltas sem sugestão + guardadas à parte + pares; as descartadas só aparecem em «Todas», com marca própria.
- **P14:** o interruptor é `/novo/` (com `/?ui=novo` e `--ui novo`).
