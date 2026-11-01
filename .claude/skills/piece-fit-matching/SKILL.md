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
A célula gémea é `perfil.simetria(l, c)` (perfil do puzzle, M13, §11 do plano). **Nunca escrever `(48 − l, 65 − c)` no código**; só o perfil deste puzzle a define.

## Arquitetura
- A **secção montada** continua a ser a referência local de alta resolução (frente a 300 dpi): localizar por canto e escala conhecidos, casar as soltas contra a fronteira.
- **Índice persistente** (M12: soltas, mapa, `log.jsonl`); cada confirmação gera consultas novas (gémea pendente, buracos vizinhos), §0 e §10.

## Regras
- Módulo puro (sem Tkinter/I/O), testável com contornos sintéticos (par tab/blank gerado = melhor custo; F rejeitado) e com GT (E-sym, E-real, E-buraco).
- A simetria e a rotação do fantasma vêm do perfil (`profile.twin`, `profile.twin_rotation_deg`).
- Módulos críticos: desenho ou revisão do `implementer` (`CLAUDE.md`). Verificação: skill `cv-visual-verification`.
