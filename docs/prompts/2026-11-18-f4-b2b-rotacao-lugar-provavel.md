# 2026-11-18 — F4 B2b: um só critério de rotação e lugar provável válido

## Porquê
O diagnóstico B2½ (`docs/diagnostico/gui/F4_ROTACAO.md`) mostrou que o «Fixar» de um grupo e as Suspeitas usavam a mesma nota com entradas diferentes (re-scans como P0615, sem as vizinhas de dentro do grupo, sem a regra «explicada») e que o `lugar_provavel` era servido sem validade: 8 dos 10 candidatos 1 com vizinhas estavam em células ocupadas, e G0095 e G0096 sobre P1064. O B2b corrige as duas coisas antes de a GUI (B4) mostrar um lugar provável ao Tiago.

## Decisões
- Do Tiago (2026-11-18, `docs/decisoes.md` «F4 B2b»):
  1. um só critério de rotação, `consistency.grade_at`, chamado pelo `evaluate` (Suspeitas, inalteradas) e pelo «Fixar» (só os membros que põe no tabuleiro; vizinhas do grupo contam; regra «explicada»; posição inválida recusada antes; o aviso nomeava a peça);
  2. `lugar_provavel` só com candidatos válidos agora, margem recalculada entre os válidos ≥ `margin_min`, nenhum lugar se um membro for impossível em todas as rotações, a imagem só desempata;
  3. testes primeiro (re-scan não avaliado, lugar ocupado nunca «confirmam», lugar omitido nos casos G0093, G0094, G0095, G0096 e G0098, `evaluate` inalterado).
- Do implementer: assinatura de `grade_at`, «confirmam» só com uma vizinha de fora do grupo, `nao_avaliadas` com motivo, veto antes ou depois do lugar, margem recalculada (regra do candidato 1 do solve e exceção `MARGIN_ROUND`), resposta com `candidato` e `vizinhas`; 3 testes existentes adaptados.
- Backlog: regra «é um re-scan» (n = 1); `anchor_section` põe um re-scan `same_as` numa célula livre (0 casos hoje).
- Mais tarde (B4, decisão 2 do Tiago): o aviso deixa de nomear a peça («Esta peça diz outra rotação», contorno âmbar na imagem do grupo).

## Prompt verbatim
**Reconstrução.** O texto original do pedido não ficou no repositório (nem em `docs/decisoes.md` nem em `docs/HANDOFF.md`, que só guardam as decisões); o que segue é um resumo reconstruído a partir dessas decisões e do commit `a5d2ad4`, não o prompt tal como foi feito.

F4, B2b: dar um só critério de rotação ao «Fixar» e às Suspeitas, e só servir um lugar provável válido. Função pura que avalia uma peça numa célula e numa rotação também hipotéticas (`consistency.grade_at`), chamada pelo `evaluate` (Suspeitas ficam iguais) e pelo «Fixar» de um grupo, só com os membros que o «Fixar» põe no tabuleiro (sem re-scans `same_as`, sem peças já colocadas), com as vizinhas de dentro do grupo e a regra «explicada». Posição inválida: recusa antes de avaliar. `lugar_provavel` de `GET /api/grupos`: só candidatos válidos agora e que a forma não contradiz, margem recalculada entre eles ≥ `margin_min`, nenhum lugar se um membro for impossível em todas as rotações, a imagem só desempata. Testes primeiro; `evaluate` inalterado nas Suspeitas; medir numa cópia de `projects/alpes`. Sem `src/web/`.

## Resultado
Commit `a5d2ad4` («grupos: um só critério de rotação e lugar provável válido»): `consistency.grade_at`, `grupos.rotation_check` / `likely_place` / `aviso_discordam`, `Gui._grupo_row` e `grupo_fixar`; `tests/test_grupos_criterio.py` (15 testes, os 15 falhavam antes do código). Medido numa cópia [V]: Suspeitas 18 = 18, item a item; o `evaluate` antigo e o novo iguais em 5 tabuleiros perturbados; lugares prováveis 6 → 4 (5 com os candidatos recalculados), todos `sem_vizinhas`. Por fazer: recalcular de vez os candidatos dos grupos soltos no projeto real (escrita no log `section_candidates_updated`).
