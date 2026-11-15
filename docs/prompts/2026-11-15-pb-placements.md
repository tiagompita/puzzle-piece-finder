# 2026-11-15 — P-b: porque é que 88 das 117 peças do céu não têm registo válido em `placements.json`

## Porquê

No passo 0 do «perto» (`docs/diagnostico/gui/DETALHE.md` §13.7), 88 das 117 peças da região do céu não tinham entrada
válida em `render/placements.json` e eram registadas na hora (`render.register_piece`) em cada composição: 1,00 s sob
disputa do GIL, 0,07 s sem ela; depois do remendo, `_piece_jobs` custava 1,21 s com os pedidos paralelos. P-b era a
proposta de perceber porquê, antes de mexer.

## Decisões

- Só diagnóstico: `src/` e `tests/` não mudam; embrulhos e simulação só nos lançadores do scratchpad; cópias de
  `base_c3` (igual a `projects/alpes` no log e em `placements.json`), nunca o original.
- A correção fica proposta, à espera do Tiago (§13.8).

## Prompt verbatim

Objetivo: diagnosticar a P-b (DETALHE §13.7): porque é que 88 das 117 peças do céu não têm entrada válida em render/placements.json e são registadas na hora em cada composição. Só diagnóstico: não alteres src/ nem tests/.

Numa cópia de projects/alpes (nunca no original):
1. Define exatamente o que torna uma entrada «válida» (chave, campos, versão, pose manual, relax) e, para o TABULEIRO INTEIRO, conta as peças colocadas em 3 grupos: entrada válida, entrada inválida (diz por que campo falha, agrupado) e sem entrada.
2. Encontra o mecanismo: quem escreve placements.json (register_all, _refresh_render_assets, rebuild_stale, escritas da GUI) e porque é que essas entradas não ficam válidas. Testa o mecanismo: se correres o caminho que devia registar, a contagem muda?
3. Correção: para as peças inválidas, compara a pose calculada na hora com a guardada (Δθ, Δx, Δy em mm). Diz se o tabuleiro desenha poses que não estão em lado nenhum. [V]/[NT]/[F]
4. Peso: tempo de `_piece_jobs` no salto a frio (céu e relva) e no 1.º salto depois de abrir, com e sem registos válidos (simulado só no lançador de diagnóstico), 5 corridas intercaladas, mais `srv_frio_relva_s` como referência da máquina.
5. Propõe a correção com o ganho esperado por critério (1.º salto, salto a frio, «perto») e o risco. Não implementes.

Paragem: se o mecanismo exigir mexer em src/ para ser confirmado, para e diz que mudança mínima farias.

Fecho: DETALHE §13.8. Um commit só de docs e dados, sem co-author. Remove os worktrees temporários.

## Resultado

Ver `docs/diagnostico/gui/DETALHE.md` §13.8 e `docs/diagnostico/gui/dados/r8_*.json`. Resumo: o ficheiro tem só 79
entradas para 699 peças colocadas (0 inválidas, 620 sem entrada); dois mecanismos confirmados numa cópia sem mexer em
`src/` (o ficheiro anterior a `a249ad6` passou a ser ignorado e nunca mais se correu `register_all`; um contorno
gravado tira a entrada e ninguém a repõe). Correção proposta, não implementada.
