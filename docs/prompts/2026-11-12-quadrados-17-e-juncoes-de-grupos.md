# 2026-11-12 — quadrados 11–17 (17/17), ESPEC dos grupos e medição das junções de um grupo solto

## Porquê

O Tiago testou os quadrados 11 a 17 e encaixam todos (17/17 com os 10 anteriores). Pediu para registar isso, acrescentar ao ESPEC duas regras e uma ideia (F4c: verificar as junções ao largar um grupo), medir quanto se pode confiar numa verificação assim com grupos de peças colocadas, e dizer o que falta para o programa propor peças que façam crescer um grupo solto.

## Decisões

- 17/17, todos no céu, Wilson inferior 0,82: registado em `docs/decisoes.md`, `docs/estado-e-plano.md` §3.9, `QUADRADOS.md` e ESPEC §8.6. A margem não discriminou e o método dos quadrados está esgotado nas soltas atuais.
- ESPEC §4.9: «já no grupo N» e F4c (nova fase no §7), pendente de medição.
- Medição só de leitura, sobre uma cópia do projeto; critérios escritos e commitados antes de correr (`7cfe199`). Um erro da primeira versão (somar a imagem ao custo da posição gémea) ficou corrigido e explicado no relatório.
- Mínimo de junções: proposta (≥ 4 para afirmar «encaixa»), a aceitar ou mudar pelo Tiago.

## Prompt verbatim

«1. Regista em docs/decisoes.md e docs/estado-e-plano.md: o Tiago testou os quadrados 11 a 17 e todos encaixam [V, Tiago, 2026-11-11]. Total 17/17, todos no céu, limite inferior de Wilson 0,82. Nota que a margem não discriminou (encaixou até 1,008) e que o método dos quadrados está esgotado nas soltas atuais.

2. Acrescenta à ESPEC (docs/gui/redesenho/ESPEC.md):
- Em qualquer figura, lista ou cartão de grupo, as peças que já estão num grupo aparecem marcadas «já no grupo N»; só as peças novas levam saco e nº em destaque.
- Ideia do Tiago, como F4c pendente de medição: ao largar um grupo solto encostado a peças colocadas, o programa verifica as junções. Três resultados: encaixa (pequeno salto para o lugar e botão «Fixar», sem fixar sozinho), não encaixa (X nas junções que falham), não sei (sem marca). Verificação só ao largar. Complemento: botão «Onde encaixa este grupo?».

3. Medição, sem alterar src/ nem o projeto: usa grupos de peças colocadas (blocos de 4, 6 e 9 células) como se fossem grupos soltos. Para cada um, verifica as junções na posição certa e em posições erradas ao longo da fronteira do que está montado. Reporta a taxa de falsos «encaixa» e falsos «não encaixa» em função do número de junções (1, 2, 3, 4 ou mais) e da zona, e propõe a partir de quantas junções o programa pode afirmar alguma coisa. Lembra que a posição gémea (rotação de 180°) encaixa por forma: trata-a à parte. Diz [V]/[NT].

4. Diz o que falta para propor peças que façam crescer um grupo solto pelos lados livres, reaproveitando o ranking de buracos. Não implementes.»

(Resumo; o texto completo, com as restrições de método, foi o do gestor.)

## Resultado

- Commits: `7cfe199` (critérios), `8710af3` (medição e relatório), `133dfa3` (decisões, estado, QUADRADOS, ESPEC) e `9b27ab6` (HANDOFF e este ficheiro).
- Relatório: `docs/diagnostico/fit/GRUPOS_JUNCOES.md`; scripts `tools/diagnostico/fit/grupos_juncoes.py` e `grupos_juncoes_tabelas.py`; saídas `grupos_juncoes.json` e `grupos_juncoes_tabelas.txt`.
- Por fazer: o Tiago aceitar o mínimo de junções; blocos da montanha e do vale (não há dados); GT físico fora do céu; registar os 17 grupos montados no projeto.
