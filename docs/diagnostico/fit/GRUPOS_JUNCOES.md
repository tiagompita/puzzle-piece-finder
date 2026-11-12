# Verificação de um grupo solto largado junto ao montado: junções, falsos «encaixa» e falsos «não encaixa»

_2026-11-12. Só leitura do programa: `src/` e `projects/alpes` não foram alterados; a medição corre numa **cópia** do projeto (a árvore de trabalho de hoje). Script: `tools/diagnostico/fit/grupos_juncoes.py`. Critérios abaixo escritos e commitados **antes** de correr a medição._

## 1. Critérios (fixados antes de olhar para resultados)

**Pergunta.** Ao largar um grupo solto de peças encostado a peças colocadas (F4c do ESPEC §4.9), o programa verifica as junções e responde «encaixa», «não encaixa» ou «não sei». Com que taxa de erro, em função do número de junções e da zona?

**Grupos de teste.** Blocos retangulares de peças **colocadas** (2×2 = 4, 2×3 e 3×2 = 6, 3×3 = 9 células), todas com forma, pose e 4 lados mapeados (`board_dirs`). Escolhidos sem peças partilhadas dentro de cada tamanho, por ordem aleatória com semente fixa (0). O bloco é retirado do montado (as suas células ficam livres) e tratado como grupo solto: o que mexe é só a posição.

**Posições.**
- **Certa:** a rotação 0 e a translação 0 (onde o bloco está).
- **Gémea:** rotação 180° e as células (l, c) → (L+1−l, C+1−c) (L, C = linhas e colunas da grelha). Tratada à parte; encaixa por forma por construção do corte.
- **Erradas:** todas as outras (rotação 0–3 × translação) em que **todas** as células do grupo estão livres (`Board.occupied` falso: célula de foto conta como livre; dentro da grelha) e há **pelo menos uma junção** com uma peça colocada (fronteira do montado). Inclui deslocar o bloco uma célula ao longo da fronteira e sobre o seu lugar original.

**Junção.** Lado de uma peça do grupo que olha, na posição testada, para uma célula ocupada por uma peça **colocada** (fora do bloco) com forma e pose. Peças vizinhas sem forma/pose, ou células ocupadas sem peça (dica do Tiago, legado sem peça), não são junções. O nº de junções n_j conta as junções existentes, testáveis ou não.

**Custo de uma junção.** `fit.side_costs` (o mesmo do molde do buraco, com a calibração `calibration.buraco` do `puzzle.json`: erosão, corte de corda, `t_abs`): a vizinha entra como `HoleSide` (o lado dela que olha o grupo, erodido, com a sua tira Lab), o lado do grupo que olha a vizinha é o candidato. Custo infinito por «impossível» = tipo incompatível (T com T, B com B, F com qualquer) ou corda acima do corte (`hard`); infinito por falta de imagem (NaN) = junção **não testada**.

**Regra F do grupo.** Em cada célula do grupo, o lado que olha para fora da grelha tem de ser F e só esse (`profile.flat_directions`, mesma regra de `_f_mask`). Violação = impossível.

**Resposta (critério A, o principal).** Seja J a média dos custos das junções testadas.
- **não encaixa:** alguma junção impossível, ou a regra F violada, ou J > `t_abs`.
- **encaixa:** nenhuma junção impossível, regra F cumprida, **todas** as junções testadas (custo finito), n_j ≥ 1 e J ≤ `t_abs`.
- **não sei:** o resto (há junção não testada e J ≤ `t_abs`, ou nenhuma junção testável).

**Critério B (mais estrito, registado em paralelo).** «encaixa» exige também o **máximo** do custo de uma junção ≤ `t_abs`; «não encaixa» é igual a A. Os limiares são os que já existem (`t_abs` calibrado no molde do buraco, para a média de um buraco); **nenhum limiar novo**.

**Taxas.**
- **Falso «encaixa»** = fração das posições **erradas** com resposta «encaixa». **Falso «não encaixa»** = fração das posições **certas** com resposta «não encaixa»; a fração de «não sei» também se reporta nos dois.
- Por n_j ∈ {1, 2, 3, ≥ 4} e por zona (`fit.zone_of` com o perfil: céu / montanha-floresta / vale-aldeia / relva).
- A zona é a do **bloco** (linha mediana das suas células) para ambas as taxas; para as erradas há também a tabela pela zona do lugar testado.
- Posição certa com n_j natural = 1, 2, 3: **subconjuntos** de junções do lugar certo (todos os de tamanho k, ou 60 sorteados com semente fixa, se forem mais), para simular o grupo largado junto de poucas peças. A fração por bloco é a média dos subconjuntos; ≥ 4 = o lugar certo inteiro com n_j ≥ 4.
- Intervalos de Wilson 95 % (`fit.wilson`). Nas certas, n = nº de blocos (contagem fracionária nos subconjuntos, aproximada). Nas erradas, n = nº de posições, **que não são independentes** (as mesmas peças em posições vizinhas): o intervalo é otimista, por isso reporta-se também o nº de blocos com ≥ 1 falso «encaixa».

**Mínimo de junções.** Propõe-se o menor n_j a partir do qual, nos dados, o limite superior de Wilson do falso «encaixa» fica abaixo de 5 % **e** o falso «não encaixa» fica abaixo de 10 % no céu; **estes 5 % e 10 % não saem de dados: são os valores que o Tiago ou a regra do «quase certo» (§8.3 do ESPEC) terão de aceitar ou mudar.** Se nenhum n_j cumprir, diz-se.

**Limites assumidos à partida.**
- O GT são as posições do tabuleiro (colocadas): só o céu tem confirmações físicas do molde (38/38, 37 no céu); relva e vale não têm GT físico, só as posições automáticas do legado.
- Um bloco no meio do montado tem a fronteira cheia; blocos junto ao bordo têm menos junções certas.
- A 180° o corte repete-se: a posição gémea fica de fora das erradas.
