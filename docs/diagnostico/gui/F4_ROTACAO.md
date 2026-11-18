# F4 B2½ — a verificação da rotação de «Fixar» contra o critério das Suspeitas (2026-11-18)

Diagnóstico só de leitura, sobre uma cópia de `projects/alpes` (base `56765b8`). Guião:
`python tools/diagnostico/gui/f4_rotacao.py <cópia> [--json out] [--sem-imagem]` (não escreve no projeto).
Correções decididas pelo Tiago no mesmo dia e feitas no B2b (`docs/decisoes.md`, 2026-11-18, «F4 B2b»); a medição
depois das correções está no §5 (`tools/diagnostico/gui/f4_lugar.py`).

## 1. A pergunta

O B2 verifica a rotação de um grupo antes de «Fixar» (`grupos.rotation_check`) com o mesmo `consistency._grade`
das Suspeitas. Os dois dizem o mesmo? E o «lugar provável» que `GET /api/grupos` serve (candidato 1 com margem ≥
`margin_min`) é um lugar onde o grupo pode estar?

## 2. Resposta curta

- **Não diziam o mesmo**, porque as entradas eram outras (a função de nota era a mesma):
  - o B2 avaliava todos os `cells_local`, incluindo re-scans `same_as` e membros cuja célula já tem peça (peças
    que a âncora nunca põe no tabuleiro);
  - o B2 excluía as vizinhas de dentro do grupo;
  - o B2 não tinha a regra «explicada».
- **O `lugar_provavel` era servido sem validade.** Dos 10 candidatos 1 com vizinha montada, 8 caem em células já
  ocupadas por outra peça e 2 são válidos mas a forma contradiz-os.
- **A imagem não decide estes casos.** Na relva (zona sem `dE_p90` calibrado) os ΔE dos 3 candidatos ficam a
  ≤ 1,2 ΔE uns dos outros.

## 3. Secções fixadas (66), na própria âncora

| | B2 | critério das Suspeitas |
|---|---|---|
| confirmam / sem objeção | 59 + 5 `inconclusivas` | 65 |
| discordam | 2: G0028 (P0343), G0051 (P0615) | 1: G0028 (P0343, falso alarme confirmado pelo Tiago a 2026-11-16) |

- **P0615 (G0051, bloco de 34 peças) é um re-scan.** É `same_as` P0041, que está colocada em (45,7); a distância
  livre entre as duas é 0,81 mm. A âncora não a põe no tabuleiro (fica em `conflicts`). O B2 avaliou-a só contra
  as vizinhas de fora do bloco, e aí 180° custa menos. Com as vizinhas do próprio bloco, como fazem as Suspeitas,
  nada a sinaliza.
- O `k` da pose `group_theta` coincide com o `k` registado em todas as peças das 66 secções (0 diferenças).

## 4. Candidatos 1 dos 32 grupos soltos com vizinha montada (10)

Candidatos de 2026-11-02, tabuleiro de 2026-11-18.

- **«ocupada por»:** a peça que já está nessa célula, com a distância livre (`shape.free_dist`) entre ela e o membro.
- **ΔE:** a mediana dos membros nos candidatos 1 / 2 / 3 (`locate.de_cell`).
- **Zona:** a do perfil.

| grupo | n | candidato 1 (célula, rot) | margem | zona | membro com vizinhas | o que se viu | B2 | Suspeitas (hipotético) | ΔE 1 / 2 / 3 |
|---|---|---|---|---|---|---|---|---|---|
| G0033 | 1 | (34,64) 270 | 1,02 | vale | P0395 | ocupada por P0228, 4,95 mm | discordam | não avaliável | 22,2 / 22,5 / 24,6 |
| G0049 | 1 | (44,37) 180 | 0,87 | relva | P0573 | ocupada por P0501, 1,27 mm | confirmam | não avaliável | — |
| G0079 | 1 | (24,1) 270 | 1,15 | montanha | P0844 | ocupada por P0654, 1,96 mm | discordam | não avaliável | 16,7 / 19,3 / 19,5 |
| G0084 | 2 | (14,61) 90 | 1,20 | céu | P0862, P0863 | ocupadas por P0840 (2,29 mm) e P0839 (2,38 mm) | discordam | não avaliável | 13,9 / 15,6 / 16,9 |
| G0090 | 1 | (3,64) 90 | 1,08 | céu | P0879 | ocupada por P0234, 3,11 mm | discordam | não avaliável | 17,6 / 19,1 / 22,3 |
| G0093 | 2 | (15,63) 180 | 1,06 | montanha | P0905, P0907 | P0907 em célula ocupada por P0195 (3,49 mm); P0905 `impossivel` nas 4 rotações | discordam | discordam (P0905) | 21,9 / 24,1 / 24,3 |
| G0094 | 1 | (42,59) 0 | 1,04 | relva | P0898 | válido; `impossivel` nas 4 rotações (E T↔T com P0081) | discordam | discordam | 21,5 / 22,3 / 22,7 |
| G0095 | 1 | (2,63) 0 | **1,66** | céu | P0899 | ocupada por P1064, 3,86 mm | discordam | não avaliável | 11,2 / 18,6 / 16,8 |
| G0096 | 1 | (2,63) 0 | **1,74** | céu | P0900 | ocupada por P1064, 2,45 mm (os 3 candidatos são essa célula) | discordam | não avaliável | 11,8 / 12,1 / 12,3 |
| G0098 | 1 | (42,59) 180 | 1,00 | relva | P0904 | válido; `impossivel` nesta rotação (180° resolve o T↔T; fica com 2 falhas de RMS) | discordam | discordam | 22,6 / 22,7 / 23,4 |

- **G0095 e G0096 eram os 2 lugares prováveis servidos com vizinhas** (margem ≥ 1,5). Os dois estão sobre P1064,
  que já está colocada.
- **Um re-scan anda a ≲ 1 mm do ocupante:** P0615–P0041 dá 0,81 mm, e G0049 fica no meio, a 1,27 mm. As peças
  diferentes ficam a 1,96–4,95 mm. Uma regra «é um re-scan» fica no backlog: n = 1, decisão do Tiago.
- **A imagem não separa os candidatos.** Na relva (G0094, G0098) os 3 candidatos ficam a ≤ 1,2 ΔE uns dos outros,
  e a zona não tem `dE_p90` calibrado. No céu, G0095 separa (11,2 contra 16,8), mas o lugar está ocupado. A imagem
  só pode desempatar.
- **Os 22 candidatos 1 sem vizinha montada** não têm prova de forma. A margem de imagem é o único sinal.

## 5. Depois das correções (B2b, numa cópia de `projects/alpes`) [V]

Regras de 2026-11-18 (`docs/decisoes.md`, «F4 B2b»):
- **Um só critério:** `consistency.grade_at`, a função das Suspeitas, usada pelo `evaluate` e pelo «Fixar».
- **Membros avaliados:** só os que o «Fixar» põe no tabuleiro.
- **Vizinhas:** as de dentro do grupo contam e a regra «explicada» aplica-se.
- **Posição inválida:** recusada antes de avaliar.
- **Lugar provável:** só candidatos válidos agora que a forma não contradiz, com a margem recalculada entre eles e
  ≥ 1,5. Nenhum lugar se um membro for impossível em todas as rotações.

**Suspeitas:**
- **Antes e depois:** 18 = 18, com a lista, o resumo e os falsos alarmes iguais item a item (3,1 s → 3,0 s).
- **Teste de esforço:** em 5 tabuleiros perturbados (80 peças rodadas cada um), o `evaluate` antigo (`HEAD`) e o
  novo dão itens e resumo iguais. São 600 itens e 474 `explicadas`.

**Lugar provável dos 32 grupos soltos** (`tools/diagnostico/gui/f4_lugar.py`):

| | regra B2 (candidato 1 + margem) | regras B2b |
|---|---|---|
| candidatos guardados (2026-11-02) | 6 (G0071, G0080, G0085, G0088, G0095, G0096) | **4** (G0071, G0080, G0085, G0088) |
| recalculados com o tabuleiro de hoje | 6 | **5** (G0071, G0080, G0084, G0088, G0092) |

- **O recálculo** segue o caminho de `legacy.solve_project_sections`, com os `blocos` incluídos (`prior_expect` 0),
  e grava eventos `section_candidates_updated` só na cópia. Mudou os candidatos dos 32 grupos (9,5 s) e baixou os
  candidatos inválidos de 31 para 10 em 96.
- **G0095 e G0096 continuam sem lugar:** os candidatos continuam sobre P1064, porque a máscara `_section_allowed`
  deixa de propósito as células de peças colocadas pelo log.
- **G0085 perde o lugar:** a margem recalculada é 1,32.
- **G0084 e G0092 ganham lugar:** margens 1,67 e 1,88.
- **Os 5 lugares são `sem_vizinhas`:** a forma não os confirma nem contradiz.
- **Custo:** `GET /api/grupos` demora 60 ms quente (325 ms a frio); `likely_place` demora ≤ 9 ms por grupo.
