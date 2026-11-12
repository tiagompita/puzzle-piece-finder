# 2026-11-12 — test_sheets nos dois caminhos, montar.py no CLAUDE.md, gémeas fora da GUI nova, quadrados em JSON, negativos difíceis por zona, decisões no ESPEC

## Porquê

Fecho da ronda dos grupos soltos, antes da F2:
- o Tiago deu OK para mudar o `test_sheets` que dependia do PyMuPDF;
- pediu os 17 quadrados no repositório (estavam só num `.pkl` do scratchpad);
- pediu a tabela dos negativos difíceis por zona com 2 e 3 junções;
- registou três decisões no ESPEC.

Perguntou também onde aparecem na GUI nova as 3 gémeas `ambigua`, porque o Montar sai vazio.

## Decisões

- `test_sheets`: força os dois caminhos (ausente com `sys.modules['fitz'] = None`, mantendo as asserções; presente com um substituto do `fitz`). Há também um teste com o PyMuPDF real, que só corre onde está instalado. A suite corre sempre com `.venv/Scripts/python.exe -m pytest tests/` (`CLAUDE.md`).
- ESPEC:
  - F4c só afirma no céu com ≥ 4 junções; fora do céu responde «não sei» até haver calibração por zona;
  - ordem das fases F2, F4, F4b, F3, F5, F6 (F4c depois da F4b);
  - na F2, desfazer «Encaixa» de uma peça de um par desfaz o par e a posição da outra.
- **Não** se registaram os 17 grupos no projeto. **Não** se arrancou a F2.
- Gémeas sem vizinha na GUI nova: só proposta (ver Resultado), sem implementar.

## Prompt verbatim

«Não arranques a F2. Faz só isto:

1. test_sheets: tens o meu OK para alterar o teste. Cobre os dois caminhos de propósito (PyMuPDF ausente e presente, forçados no teste), mantendo as asserções atuais para o caminho ausente. Diz na mensagem do commit que alteraste um teste existente e porquê. Regista no CLAUDE.md que a suite corre sempre com .venv/Scripts/python.exe -m pytest tests/.
2. CLAUDE.md: acrescenta src/montar.py à tabela de módulos.
3. Com o estado atual de projects/alpes, o fetch.json tem 3 gémeas «ambigua» e 32 grupos «por_ancorar», e o Montar sai vazio. Diz onde essas 3 gémeas aparecem na GUI nova. Se não aparecem em lado nenhum, é capacidade perdida: propõe a correção (a ESPEC prevê «a confirmar por ti»), sem implementar.
4. Guarda no repositório, em docs/diagnostico/grupos_soltos/, um JSON com os 17 quadrados: peças, posição de cada uma no grupo e rotação, e as ligações entre grupos (12 com o 1; 16 e 17 com o 7 e o 8). Hoje esses dados estão no scratchpad.
5. Acrescenta a GRUPOS_JUNCOES.md a tabela dos negativos difíceis (grupo deslocado uma célula) com 2 e 3 junções, nos critérios A e B, por zona.
6. Regista na ESPEC: a F4c afirma só no céu, com 4 ou mais junções, e fora do céu responde «não sei» até haver calibração por zona; a ordem das fases passa a F2, F4, F4b, F3, F5, F6; na F2, desfazer «Encaixa» numa peça de um par desfaz também a confirmação do par e a posição da outra peça.
7. Não registes os 17 grupos no projeto real.

Corre graphify update . no fim. Commits sem Claude como co-author.»

## Resultado

- Commits:
  - `d24cb57`: test_sheets, `montar.py` e regra da suite no `CLAUDE.md`, `decisoes.md`;
  - `8f820a0`: `quadrados_17.json`, script e teste;
  - `6b47a3a`: negativos difíceis por zona;
  - `8201154`: ESPEC e `decisoes.md`;
  - o commit do HANDOFF e deste ficheiro.
- Gémeas na GUI nova: não aparecem em lado nenhum.
  - `montar.fila` só aceita `grupo == 'coloca_agora'`, e as 3 são `guarda_posicao`.
  - As secções não entram no Montar porque não têm peça.
  - A camada «guardadas» do tabuleiro só desenha peças `posicao_conhecida`.
  - A lupa diz «ainda não tem lugar» / «ainda vazio».
  - Só estão na GUI antiga (aba «Guardadas», «Mesa»).
  - A proposta de correção está no HANDOFF («Espera pelo Tiago»).
- Por fazer: a proposta do ponto 3 (decisão do Tiago); registar os 17 grupos (F4b); F2 (à espera de OK).
