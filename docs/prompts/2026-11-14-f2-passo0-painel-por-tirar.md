# 2026-11-14 — Passo 0 (GIL parado, concorrência) e F2: painel da peça e do lugar, pôr e tirar à mão, desfazer global

## Porquê

O Tiago aprovou o plano da F2 (`C:\Users\tiago\.claude\plans\agente-implementer-skills-systematic-deb-witty-pelican.md`)
com alterações nos pontos c e g do §6, e pediu antes dele um passo 0: a ronda 2 do detalhe reportara o salto a frio a
2,9–3,5 s contra 2,0–2,8 s na ronda 1 (era a forma de medir ou o intervalo do GIL novo?), e o `FileNotFoundError` do
`render.py` tinha sido encontrado por acaso (havia outros?). Acrescentou à F2 o ajuste de cor só de visualização (9).

## Decisões

- **Passo 0a:** o intervalo de 0,5 ms não piora a composição sozinha (3 + 3 corridas: médias +6,6 a +9,3 %, medianas
  +1,0 a +5,8 %; 4 corridas de controlo iguais); fica. A diferença das rondas é a forma de medir (o protocolo da ronda 2
  abria a página e arrancava o ranking dos buracos: 4,6–7,8 s). `DETALHE.md` §8.1.
- **Passo 0b:** auditoria em `DETALHE.md` §8.2; escritas atómicas, apagar com repetição, leitura com repetição enquanto
  um ficheiro é trocado (Windows), cell lida uma vez na composição, geração da forma em cache, caches com a chave (log,
  mtime de `placements.json`). Teste de esforço `tests/test_concorrencia.py`: HEAD de então 21/22 a falhar, 20/20 agora.
- **F2:** a, b, d, e, f, h, i, j como propostos; c e g como o Tiago os mudou; `verificar` sem bloqueio de escrita;
  ponto 9 (cor das peças, brilho inicial 0,92, também no tabuleiro: medido sem frames perdidos). Regras minhas
  (forma/imagem em palavras, toque duplo no alvo, par já colocado, lugar marcado verificável) em `docs/decisoes.md`.
- **Fora (Tiago):** lados em disco, formas por folha, segundo plano no arranque, E e C ficam para a fase de desempenho.
- **`CLAUDE.md` não foi mexido** (as linhas de `state.py`, `server.py`, `montar.py` e a GUI ficam por atualizar pelo
  Tiago ou pelo gestor: um subagente não altera o `CLAUDE.md`).

## Prompt verbatim

Pedido do Tiago (passado pelo gestor com o cabeçalho `Agente: implementer. Skills: frontend-design, systematic-debugging,
verification-before-completion, graphify.` e notas de execução: ordem passo 0 → F2, parar se 0,5 ms piorar > 10 %,
tabela das 12 corridas, auditoria no DETALHE, teste de esforço na suite a reproduzir o `FileNotFoundError` com o
`render.py` anterior a `6399e31`, suite completa com o `.venv`, fechar este ficheiro e o HANDOFF, commits em português
sem co-author, rótulos [V]/[NT]/[F]):

«Passo 0, antes da F2, num commit próprio:
a. Mede o salto a frio com o servidor parado (sem o cálculo do arranque a correr), com o intervalo do GIL a 5 ms e a 0,5 ms, 3 corridas cada, no céu e na relva. A ronda 1 dava 2,0 a 2,8 s e a ronda 2 reporta 2,9 a 3,5 s: diz se é a forma de medir ou se o intervalo novo piorou a composição sozinha. Se piorou mais de 10 %, para e diz-me.
b. Auditoria de concorrência: lista tudo o que a composição do tabuleiro lê fora do bloqueio (ficheiros e estado em memória) e o que os caminhos de escrita podem alterar entretanto. Escreve um teste de esforço que compõe em ciclo enquanto se coloca, tira e re-segmenta peças. Corrige o que falhar. O FileNotFoundError do render.py foi encontrado por acaso: quero saber que não há outros.

Depois, a F2. Plano aprovado, com estas decisões sobre os pontos do §6:
- a, b, d, e, f, h, i, j: aprovados como propostos (em d, a ponte por URL para o editor da GUI antiga).
- c: alterado. «Tirar do lugar» numa peça de par limpa a posição «por confirmar» da outra peça que veio dessa colocação, e o par volta a «proposto» se a confirmação veio dessa colocação. Se o par já estava confirmado antes, fica confirmado.
- g: alterado. «Pôr uma peça à mão» grava `place` só quando o lugar tem pelo menos uma vizinha colocada (com forma no índice). Sem vizinha colocada grava posição conhecida: a peça fica «por confirmar» e não serve de molde nem conta no progresso até uma vizinha encaixar. Com vizinha, «Pôr na mesma» depois de um aviso grava `place`. O texto do botão e o estado no painel dizem qual dos dois casos é.
- O endpoint `verificar` corre sem bloqueio de escrita: aplica-lhe o que a auditoria do passo 0 concluir.

Acrescenta à F2:
9. Ajuste de cor só na visualização, em «⋯ › Definições › Cor das peças»: dois controlos (mais escuro/mais claro; cor mais/menos viva), aplicados às imagens de peça nos cartões e painéis e ao tabuleiro, guardados por aparelho, com «Repor». Valor inicial a partir do desvio scan/arte já medido em docs/estado-e-plano.md. Não altera scans, recortes, índice nem nada que o motor leia: um teste prova-o. Mede se o filtro no tabuleiro atrasa o arrastar e o zoom; se atrasar, aplica só nas imagens de peça e diz-me.

Mantém o resto do plano: guião da peça da borda (linha 1, coluna 29, Saco 9 · nº 89), capturas de cada ecrã novo a 1366×768 e a 390×844, e o telemóvel real como [NT].

Não avances com as opções do arranque (lados em disco, formas por folha, segundo plano): ficam para uma fase de desempenho depois da F2, com E e C.

Fecho: suite completa com o .venv, lista dos testes existentes alterados na mensagem do commit, ESPEC e docs/decisoes.md atualizados com as decisões c e g. Usa `graphify query` antes de grep ou de ler ficheiros e corre `graphify update .` no fim. Commits sem Claude como co-author.»

## Resultado

- **Commits:** `6345154` (passo 0), `32c5f5c` (F2: estado, servidor, GUI nova, testes, mais as leituras com repetição
  achadas pelo teste de esforço com o «verificar»), e o commit de docs e capturas que fecha este ficheiro.
- **Passo 0:** `DETALHE.md` §8 (tabela das corridas, causa, auditoria, teste); dados `dados/r3_p0a_*`; guião
  `tools/diagnostico/gui/salto_frio_gil.py`.
- **F2:** `src/state.py` (`pair_unconfirmed`, `unconfirm_pair`, `place(reposicao=)`, `undone_decisions`), `src/confirm.py`
  (par desfeito no `unplace`, `theta_force`, θ na posição conhecida), `src/server.py` (`por_mao`, `tirar`, `verificar`,
  `lookup`, `piece.png?theta=`, `cell_json` com `posta_em`, `secao`, `vizinhas_com_forma`, `reports_abertos`),
  `src/montar.py` (`verificacoes`), `src/query.py` (`fit_check` público), `src/fit.py` (`include_marked`), `src/web/novo/*`
  (painéis, «Pôr uma peça à mão», desfazer global, Definições, 8 ícones Lucide novos), `src/web/app.js` (`/?peca=&contorno=1`).
- **Medidas:** «verificar» 0,62–0,66 s a frio parado, 3,2–4,5 s a frio durante o ranking, ≤ 0,05 s a quente; filtro de
  cor no tabuleiro +20–70 % de pintura, 0 frames perdidos (`DETALHE.md` §9).
- **Guião da borda (passos 1–7, numa cópia, nas duas larguras) [V no programa]:** lugar «marcado por ti» → Saco 9 · nº 89
  «está solta» → na rotação −171° lado liso, forma e imagem com 3 traços («Tem 3 peças montadas ao lado: fica no
  lugar»), nas outras 3 o lado liso e a forma falham → «Pôr aqui» → painel da peça → «Tirar do lugar» volta a «marcado
  por ti» → «Desfazer» repõe → recarregar e tirar pelo painel volta a «marcado por ti». O encaixe físico (passo 8) é [NT].
- **Testes novos:** `tests/test_concorrencia.py`, `tests/test_f2.py` (11), `tests/test_gui_novo_f2.py` (8, Playwright).
  **Testes existentes alterados:** `tests/test_gui_novo.py` (4 asserções de texto: «sem vizinha montada» → «ainda sem
  peças ao lado»).
- **Por fazer / [NT]:** telemóvel real, Firefox/Safari, GPU real para o filtro; o 404 de um `render/clean` visto 2× na
  HEAD antiga sem origem encontrada; linhas do `CLAUDE.md`.
- **Suite [V]:** `.venv/Scripts/python.exe -m pytest tests/`: no passo 0 517 passed, 1 skipped; no fim 537 passed,
  1 skipped (o PyMuPDF real no `test_sheets`), 0 failed, 405 s com os slow/Playwright.
