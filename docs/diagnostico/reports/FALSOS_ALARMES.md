# Falsos alarmes nas Suspeitas (2026-11-07)

Backend da Parte 3.3: o Tiago pode dizer que uma suspeita de `src/consistency.py` é um falso alarme; a marca fica no log e esconde a suspeita só enquanto os dados com que foi vista não mudarem. A junção com os reports abertos diz que suspeitas já têm report.

## Eventos e estado

- `suspect_dismissed {piece, cell, grau, assinatura, nota, autor: "manual"}` e `suspect_restored {piece, grau}` (`src/state.py`, `ACTIONS`). `Model.falsos_alarmes`: `{(piece, grau): {assinatura, cell, nota, t}}`, refeito no replay; uma marca nova do mesmo par substitui a anterior; `piece_discarded` apaga as marcas da peça; `check_invariants` compara as marcas da memória com o replay.
- Operações: `Project.dismiss_suspect(piece, grau, assinatura, *, cell, nota="")`, `Project.restore_suspect(piece, grau)` (`StateError` se não houver marca).
- Compatibilidade: o log é partilhado entre máquinas; um checkout anterior a estas ações não consegue fazer replay de um log que as tenha (`ação desconhecida`), o mesmo preço já pago por `piece_resegmented`.

## Assinatura

`consistency.suspect_signature(item, project)`: sha1 (12 hex) do JSON canónico de

| campo | valor |
|---|---|
| `cell` | célula da peça |
| `k0` | classe de 90° do registo por cantos (nos itens `recorte`, que levam `k0 = null`, o `evaluate` passa o `k` do registo) |
| `grau` | `impossivel` / `melhor_rotacao` / `recorte` |
| `cls`, `chords` | classe da forma e cordas arredondadas a 0,1 mm |
| `contorno_manual` | `overrides.is_manual(p)` |
| `pose_manual` | `p.pose_manual` arredondada (θ 0,1°, dx/dy 0,05 mm); ainda não existe na `Piece` (lida com `getattr`, `null`) |
| `vizinhas` | id da peça `colocada` a N / E / S / W, ou `null` |
| `gemea`, `nn_max_mm` | só no `recorte` (resíduo a 0,1 mm) |

Semântica: com a mesma pose (a mesma classe de 90°; um θ ligeiramente diferente não conta) e os mesmos dados a suspeita fica escondida; mudar a célula, a classe de 90°, o contorno, uma vizinha ou a gémea faz a suspeita voltar e a marca passa a `obsoleto`.

## Contrato

- `evaluate(..., dismissed=None, incluir_falsos=False)`: cada item leva `assinatura`; com a marca e a mesma assinatura leva `falso_alarme: {t, nota}` e sai de `items` (fica, marcado, com `incluir_falsos=True`). Os falsos alarmes ativos nunca entram nas contagens do `summary`, que não depende de `incluir_falsos`. `summary` ganha `n_falsos_alarmes` (ativos) e `n_falsos_alarmes_obsoletos`. O resultado ganha `falsos_alarmes: [{piece, grau, cell, t, nota, assinatura, assinatura_atual, estado, obsoleto}]`, com `estado` igual a `ativo`, `obsoleto` (sinalizada com outra assinatura) ou `sem_suspeita` (não está sinalizada com esse grau agora: a marca fica à espera).
- `GET /api/suspeitas`: `{summary, items, falsos_alarmes, n_em_reports}`; cada item ganha `report_aberto` (o report aberto mais recente da mesma peça, ou sem peça e na mesma célula; senão `null`).
- `POST /api/suspeitas/{piece}/falso-alarme` `{grau, nota?}` → `{ok, piece, grau, assinatura, summary, invariantes}`; `POST /api/suspeitas/{piece}/restaurar` `{grau}` → `{ok, piece, grau, summary, invariantes}`. 400 `{error}` (não sinalizada com esse grau / sem marca / grau inválido), 404 peça desconhecida, 409 ocupado. Os dois emitem SSE `suspeitas_changed` (summary + `n_em_reports`), tal como a criação, edição e mudança de estado de um report.
- CLI: `python -m src.consistency --project P --falso-alarme P#### --grau G [--nota ...]`, `--restaurar P#### --grau G`, `--list --falsos`; a linha de resumo e `suspects_lines` (fim de `src.confirm`, só quando não é zero) dizem «N falsos alarmes ativos, M obsoletos».

## Medições

Em `projects/alpes` (só leitura; log intacto, confirmado por tamanho e mtime):

| | tempo |
|---|---|
| `evaluate` do HEAD (`be51ac5`), frio | 5,62 s / 5,59 s |
| `GET /api/suspeitas` novo, frio (avaliação + assinaturas + junção) | 5,65 s |
| `evaluate` novo, frio | 5,61 s |
| `GET /api/suspeitas` em cache | 0,006 s |
| junção com os reports, sozinha | 0,33 ms |

Os 14 itens são iguais aos do HEAD (sem contar `assinatura` / `report_aberto`); 0 impossível, 2 melhor rotação, 12 recorte. `n_em_reports = 1`: P0833 (melhor rotação) com R0028.

Numa cópia (`scratchpad/fa/alpes`):

- **Endpoints:** criar um report demora 0,24 s com a captura: o servidor junta outra vez os reports sem reavaliar, porque a avaliação passa para a versão nova do log. Fechar um report demora 0,02 s, marcar um falso alarme 1,75 s e restaurar 1,75 s (com `save` + invariantes + reavaliação com as poses em cache).
- **P0289 (1,33), recorte, bloco c32|c33:** a marcação faz 1 evento `suspect_dismissed` e a peça sai: recorte passa de 12 para 11 e há 1 falso alarme ativo. As invariantes ficam OK.
  - `confirm --unplace P0289` recusa: «P0289 é da secção G0018: usa --unanchor G0018». Por isso tirei e voltei a pôr a peça pela API do `Project` (`unplace` + `place`, 2 eventos).
  - Com o mesmo θ continua escondida. Com θ + 90° também continua: P0289 é de borda (`BFTT`, fila 1) e o registo por cantos volta a pôr o lado F na borda (k = 2, θ 89,55° antes e depois), por isso a pose desenhada é a mesma e a assinatura não muda. Está correto.
- **P0290 (2,33), interior, recorte:** a marcação faz 1 evento.
  - Com o mesmo θ continua escondida.
  - Com θ + 90° o k passa de 2 para 3 (θ 179,04°) e o recorte volta: a marca fica `obsoleto` (assinatura `bd26600e8975` → `855287fb7f96`) e aparece também `impossivel` para P0290. As invariantes ficam OK.

Scripts: `scratchpad/fa/medir.py` (tempos, P0289), `medir2.py` (P0289: tirar e voltar a pôr), `medir3.py P0290 2 33`, `medir4.py` (tempos dos endpoints).
