# HANDOFF — 2026-11-07 (ronda 2: moldura, reports, orientações e âncoras, rebuild, P0778; fechada)

Lê isto primeiro numa sessão nova; no fim, atualiza-o e fecha o ficheiro do prompt em `docs/prompts/`.

## Estado
- **Commits desta ronda** (todos em `main`, empurrados): `2c9d837` reports como eventos + `src/consistency.py`; `6746c4f` R0018/R0019/R0020/R0027 fechados; `749bf1b` `F_TRANSLATION` (medida, desligada); `a762128` `confirm --unplace/--theta` + ORIENTACOES; `dc12684` dados (P0083, P0333, coluna 55, G0044); `813b7bd` rebuild por folha + `piece_resegmented`; `c25e154`/`994d886` S0009 refeita + lista; `637a202` corte de contacto aparado + `suspeita_recorte`; `a406b91`/`df01fd4` S0023/S0020/S0003 refeitas + lista; `514c76f` editor de contorno; + o commit das docs.
- **Testes:** suite completa **272 passed, 1 skipped** (216 s, OpenCV 4.11, venv4) no commit `514c76f`; OpenCV 5.0 [NT].
- **Interpretador:** `C:/Users/Tiago/AppData/Local/Temp/claude/c--Users-Tiago-Desktop-puzzle-piece-finder/f748cb5c-95ce-4ca7-bb40-feccfde7cc64/scratchpad/venv4/Scripts/python.exe` (`PYTHONIOENCODING=utf-8`; o `python` do PATH não tem numpy).
- **Projeto `projects/alpes`:** log 2099 eventos, 958 peças (lote 3 incluído), **613 colocadas**, 205 `em_seccao`, 134 `solta`, invariantes OK; `render/placements.json` continua a não existir (a GUI regista na hora, sem imagem). Lista «ir buscar»: 9 propostas gémeas aceites, `p_twin_placed` 102/2395 = 4,3 %.
- **Reports:** **15 abertos** (R0001–R0012, R0022, R0023, R0024); fechados nesta ronda R0018, R0019, R0020, R0027 (nota «verificado pelo Tiago 2026-11-07»). Estados são eventos: `reports.set_state` (close/reopen/delete/restore), CLI `python -m src.reports --close/--reopen/--delete/--restore R#### --nota …`, GUI com detalhe e filtro Eliminados.
- **GUI nova:** clique numa linha de report realça/zoom sem sair da lista; seta «→» abre o detalhe; bloco «Suspeitas (N)» no topo de Reports; botão «Editar contorno» na gaveta/painel da peça (`overrides.jsonl`, `rebuild_piece`).
- **Dados corrigidos:** P0083 (44,60) θ 175,21 (+90°); P0333 (6,22) G0030 a rot 90 (−90°); (42..45,55) = P0442/P0401/P0425/P0420; (44,37)/(45,37) = P0501/P0506; S0009 (P0218 BFBT, P0223, P0199), S0023 (P0777/P0778), S0020 (P0651/P0657) e S0003 (4 descartadas) re-segmentadas com eventos `piece_resegmented`.

## Espera pelo Tiago (decisões que são dele)
1. **Porta §6.1:** opções A/B em TRIAGEM-2026-11-07 §4 (49/607 falham 1,5 %, todas relva; 13 falham 2,0 %). Nada implementado.
2. **P0833 (8,2) e P0343 (5,20):** as 2 «melhor rotação» que ficam na lista Suspeitas (−90° / 180°); confirmar fisicamente antes de corrigir (`python -m src.confirm P0833 --unplace` + `--cell 8 2 --theta …`, ou `--unanchor/--anchor` se forem de secção).
3. **R0011/R0012 (P0651/P0657):** a vista atual não mostra defeito e as formas estão ao nível da gémea (0,55/0,37 mm); perguntas concretas em `docs/diagnostico/reports/R0011_R0012.md` (forma? cor/orla? pose? identidade?). Fechar ou explicar.
4. **Moldura (R0022):** encostar o F à borda peça a peça falha a porta (60 juntas pioram; buracos 71/11) porque a grelha nominal distribui o erro; a alternativa é um arranjo global (relax com F bloqueado: mediana 0,082 mm, mas 15 juntas pioram e buracos 75/12) e pede outra porta (mediana/p95/juntas > 0,8 em vez de «nenhuma piora») e uma pose global em cache na GUI. Decidir se se avança por aí. Hipótese não medida [NT]: `celula_silhueta.offset_mm` 0,48 pode estar alto (o F fica 0,27 mm aquém do alvo e as juntas interiores têm folga mediana +0,14 no mesmo sentido).
5. **Confirmações físicas:** P0083 e P0333 rodadas; as 6 peças ancoradas (coluna 55 e (44,37)/(45,37)); corte vertical c32|c33 não simétrico nas filas 1–3/45–47 (os dois blocos encaixam nas vizinhas: fica por pôr a exceção no perfil); R0023 (P0218 já tem o F; fechar?); R0001 (P0778 sem a língua; fechar?); R0024 (P0083; fechar?); R0004–R0009 (ancoradas; fechar?).
6. **P0395 (S0013 #50):** linha escura ao longo do lado de baixo, marcada pela flag `suspeita_recorte` (apêndice 14,5 mm): ver na GUI (`P0395`) e, se for defeito, usar o editor de contorno.

## Pendentes técnicos (por ordem)
1. **Pose global da moldura** (ponto 4 acima) e a instabilidade da translação por imagem (`register_all` com imagem, RENDER §8).
2. **Suspeitas em direto:** o cliente não ouve `suspeitas_changed` (atualiza ao abrir Reports / depois de escrever).
3. **Editor de contorno:** não há «remover contorno manual» na GUI (só gravar outro, ou apagar a linha e `force_scans`); secção por ancorar só reconsulta a peça; scripts de diagnóstico que leem o projeto ainda não filtram `manual_override` (`overrides.is_manual`).
4. **`_CONTACT_TRIM` / `suspeita_recorte`:** limiares fixados em 2 pares de bacia (S0023, S0020) [NT noutro conjunto]; halo de ~1,1 mm na metade de baixo do lado W de P0778 é sombra real (modelo de sombra adiado).
5. **(26,1)/(25,1):** orla preta de sombra no lado S de P0663 (RENDER §7/TRIAGEM §5), fora da regra do verde; meias-luas a 0,4–0,8 mm (P0196, P0204).
6. **Lados F com reta RMS > 0,15 mm** ficam com a rotação por cantos (P0218 0,173, P0199 0,167 mesmo depois do rebuild; p95 dos 220 = 0,161): rever o limite com medição.
7. SSE dos reports (`report_added`/`report_edited`/`report_changed`) já é ouvido pelo cliente; `suspeitas_changed` não (ponto 2).

## Convenções que mordem
- Nunca correr `tools/diagnostico/render/run_render.py` nem `verde_tabuleiro.py` sem `--project` apontado a uma cópia; `tools/diagnostico/render/moldura.py`, `pose_f.py`, `tools/diagnostico/reports/*.py`, `tools/diagnostico/segmentacao/*.py` só leem (e recusam `projects/alpes` onde indicado).
- `tools/rebuild_scans.py --project projects/alpes --scans S####[,…] --motivo … [--dry-run]`: com o servidor parado e sem outro agente a escrever no log; depois `python -m src.query --project projects/alpes` (≈ 2,5 min) e commit de `log.jsonl`, `scans/*.json`, `fetch*`.
- Escrita no log só por `src.confirm`/`src.reports`/`rebuild_scans`; `ingest_all.py` refaz o log e perde as colocações do Tiago: não usar.
- Em `Bash`, heredocs com muitas aspas falham: escrever o script com a ferramenta Write; consola cp1252: `PYTHONIOENCODING=utf-8`.
- Commits em português, sem co-author. Suite completa > 200 s: em segundo plano.

## Links
- Medições desta ronda: `docs/diagnostico/render/RENDER.md` §9 + `moldura.json`/`moldura_antes_depois.jpg`; `docs/diagnostico/reports/ORIENTACOES-2026-11-07.md` (+ json, jpg); `docs/diagnostico/reports/R0011_R0012.md` (+ jpg); `docs/diagnostico/segmentacao/CONTACTOS.md` §6 (+ `contactos_s0023_antes_depois.jpg`); `docs/diagnostico/segmentacao/PRADO.md` §7 (rebuild).
- Ronda anterior: `docs/diagnostico/reports/TRIAGEM-2026-11-07.md`.
- Estado e plano: `docs/estado-e-plano.md`; arquitetura: `ARCHITECTURE.md`; GUI: `docs/gui-design.md` (§12, §17 estados dos reports, §18 editor de contorno); decisões: `docs/decisoes.md`.
- Prompt desta ronda: `docs/prompts/2026-11-07b-moldura-reports-ancoras-rebuild-p0778.md` (fechado).
- Reports: `python -m src.reports --project projects/alpes --list`; suspeitas: `python -m src.consistency --project projects/alpes`.
