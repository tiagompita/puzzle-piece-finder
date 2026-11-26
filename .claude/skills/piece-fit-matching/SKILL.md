---
name: piece-fit-matching
description: Desenho e implementação do gémeo (M10), molde do buraco (M11) e encaixe na fronteira (M6) a partir de lados de peças (perfis, cordas, classe), com imagem obrigatória e secções montadas como referência local. Usar ao trabalhar em src/shape.py, src/twin.py, src/fit.py, no protótipo tools/diagnostico/forma/shapelib.py ou em qualquer código de "que peça vai aqui / qual é o gémeo".
---

# Gémeo, molde do buraco e encaixe (M10 → M11 → M6)

## Âmbito: consulta interativa, não montagem global
- Ordem de sinal: **gémeo** (M10, 1-contra-1 na célula gémea) → **molde do buraco** (M11) → **encaixe na fronteira** (M6).
- Custo `O(N)` por consulta, N ≤ 3008. **Sem solver global** nem backtracking sobre o puzzle; se uma ideia o exigir, para e reporta. Fora de âmbito: ML e API REST.

## Ponto de partida real
- O protótipo é `tools/diagnostico/forma/shapelib.py` (cantos v2, lados, classe, métricas free/corner), a promover a `src/shape.py` no M4. `src/edges.py` conta lados retos do `minAreaRect` e falha bordas (8/20): vai ser substituído, não estendido.
- Escala em **mm a partir do dpi do scanner** (1 px = 0,0847 mm a 300 dpi), não px/cm da GUI.

## Lado como unidade
Cada lado: tipo F/T/B, corda em mm, perfil normalizado (64 pontos). Compatível: F com nada, T só com B; perfil A contra B invertido e negado (RMS em mm) e |ΔL| em mm. Filtro de cordas por tipo de lado: 2 mm no lado F e nos adjacentes a F, 1 mm nos restantes (E-real-2 §8). Cada lado digitalizado entra na memória de cortes (~2953 cortes distintos).

## Compatibilidade: a forma não chega
- Cada lado tem **≥ 2 parceiros físicos** (o vizinho verdadeiro e o gémeo do vizinho). E4/E5 contam o gémeo do vizinho como acerto.
- **Imagem obrigatória**: continuidade em Lab na fronteira; no gémeo, teste 1-contra-1 contra a arte da célula conhecida (a forma sozinha só serve até ≈ 60 candidatos).
- **Molde do buraco** = lados livres dos vizinhos já colocados; sai a peça certa ou a sua gémea e a imagem decide.
- Pesos como constantes nomeadas; shortlist + confiança por gap diferencial (aceitar se d₁ ≤ 0,5 mm e d₂/d₁ ≥ 1,5 no gémeo).

## Simetria: vem do perfil, nunca fixa no código
A célula gémea é `profile.twin(l, c)` (perfil do puzzle, M13, §11 do plano). **Nunca escrever `(48 − l, 65 − c)` no código**; só o perfil deste puzzle a define (verificado por `tests/test_lint.py::test_regra_gemea_so_no_perfil`, também em `tools/`).

## Arquitetura
- A **secção montada** continua a ser a referência local de alta resolução (frente a 300 dpi): localizar por canto e escala conhecidos, casar as soltas contra a fronteira.
- **Índice persistente** (M12: soltas, mapa, `log.jsonl`); cada confirmação gera consultas novas (gémea pendente, buracos vizinhos), §0 e §10.

## Regras
- Módulo puro (sem Tkinter/I/O), testável com contornos sintéticos (par tab/blank gerado = melhor custo; F rejeitado) e com GT (E-sym, E-real, E-buraco).
- A simetria e a rotação do fantasma vêm do perfil (`profile.twin`, `profile.twin_rotation_deg`).
- Módulos críticos: desenho ou revisão do `implementer` (`CLAUDE.md`). Verificação: skill `cv-visual-verification`.

## Verificação (o que é automático e o que continua a ser juízo)
Antes de cada commit que toque `src/`, `tools/verify/`, `tests/golden/` ou `projects/`: `python -m tools.verify` (exit ≠ 0 = parar e reportar; nunca congelar a baseline para passar; regras e códigos de saída na skill `cv-visual-verification`, «Verificação»). Aqui pesa em especial: `f_por_celula` (lados F = lados da célula fora da grelha), `borda_completa`, `mesma_celula` e, nas peças do golden, classe, cordas (±0,3 mm), célula de borda e pares gémeos novos acima de `TWIN_LOCAL_MAX_MM`.

Passos 1–3 do verify (2026-11-26, `tools/verify/regressao.py`): E-sym (`free_dist`, ≤ 0,5 mm e 20/20), E-real-2 (`find_twin` só forma: 0 `aceite` em negativos, aceites nos pares gémeos não descem), ligações dos 10 quadrados 2×2 (`fit.side_costs`, 40/40 melhor-mútuas) e molde do buraco em leave-one-out (`fit.hole_queries(exclude_piece=)` + `rank_hole` nas peças do golden com ≥ 2 vizinhas: nenhuma peça certa deixa de o ser, nenhuma «alta» errada nova). Mexer em `fit.py`/`twin.py`/`shape.py` faz o pre-commit correr o modo completo.

Testes que cobrem as regras desta skill:
- simetria só do perfil: `tests/test_lint.py::test_regra_gemea_so_no_perfil` (nenhuma fórmula à mão fora de `src/profile.py`), `tests/test_profile.py::test_rot180_twin`, `::test_translate_and_none`, `tests/test_twin.py::test_profile_translate_drives_twin_cell`; exceção da simetria só no perfil e «alpes» fora de `src/`: `tests/test_simetria.py`;
- imagem obrigatória e nunca promove: `tests/test_twin.py::test_image_demotes_wrong_colour_and_never_promotes`; zona sem `dE_p90` nunca dá `aceite`: `tests/test_twin_pctl_zone.py::test_zone_without_p90_never_accepts`;
- candidato único não é proposto: `tests/test_twin.py::test_single_candidate_not_proposed`; lado alterado não aceite: `::test_altered_side_not_accepted`;
- molde do buraco: uma vizinha nunca dá `alta` (`tests/test_fit.py::test_single_neighbour_is_never_alta`), F obrigatório onde a célula é de borda (`::test_f_rule_requires_flat_sides_where_the_cell_is_border`), filtro de cordas suave (`::test_soft_chord_filter_recovers_a_side_that_the_hard_filter_kills`), afetação um-para-um (`::test_assign_gives_each_piece_one_hole`), pausa a ≥ 3 rejeições nas últimas 20 (`tests/test_fit_alta.py`);
- GT real: `tests/test_twin_real.py::test_esym_find_twin`, `::test_ereal2_find_twin`; pares gémeos colocados: `tests/test_simetria.py::test_simetria_dos_pares_colocados`.

Continua a ser **juízo** (nenhum teste o substitui): que uma consulta fique O(N) e sem solver global; a escolha de pesos e limiares novos (com números antes/depois contra GT); se uma proposta faz sentido olhando a peça, a arte da célula e as vizinhas montadas; as confirmações físicas do Tiago, que são a única GT de relva/vale.
