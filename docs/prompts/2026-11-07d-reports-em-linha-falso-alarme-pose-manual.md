# 2026-11-07 (4) — Reports em linha, report na peça, falso alarme nas Suspeitas, copiar PNG; «Editar posicionamento»

## Porquê

Depois da ronda 3 (R0011/R0012 resolvidos com a GT manual; editor de contorno por traços), o Tiago pede menos saltos entre abas no uso diário: o report deve abrir na própria linha da aba Reports (sem a seta «→»), a gaveta da peça deve mostrar e resolver o report sem ir à aba, uma suspeita com report aberto não deve aparecer em duplicado, deve poder marcar uma suspeita como «falso alarme» (reversível, registado como verdade de terreno) e copiar/guardar a miniatura da peça como PNG transparente. E pede uma pose manual: desbloquear uma peça colocada e afinar rotação/posição com as folgas das juntas e a consistência a atualizar ao vivo, gravada como evento reversível e sinalizada para as métricas a excluírem, sem snap automático sem aviso.

## Decisões

- Linhas da aba Reports passam a `<details>` recolhíveis: clicar localiza no tabuleiro e expande o report na própria linha (uma aberta de cada vez); `#tab-report` e a seta «→» desaparecem; a pesquisa `R####` abre a aba Reports com a linha expandida.
- Gaveta da peça/célula: com report aberto mostra o report em linha com as ações (resolver/reabrir/eliminar/restaurar/editar); os cartões «Vai buscar»/«Guardadas» mantêm o botão «✎ Editar report».
- Suspeitas: a junção com reports abertos é feita no servidor (`report_aberto` por item); a GUI esconde esses itens do bloco e põe o chip «suspeita» na linha do report; escritas de reports passam a emitir `suspeitas_changed` e o cliente passa a ouvi-lo.
- Falso alarme = eventos de estado no log (`suspect_dismissed`/`suspect_restored`), replayados e nos invariantes; a assinatura (célula, classe de 90° `k0`, grau, classe/cordas, contorno manual, pose manual, vizinhas, gémea) decide quando a mesma suspeita volta a ser sinalizada (registada em `docs/decisoes.md`).
- Copiar PNG pela Clipboard API (`ClipboardItem image/png`, só em contexto seguro: localhost/https); fora disso o item fica desativado com a razão e «Guardar PNG» é o fallback.
- Pose manual: `Piece.pose_manual` + eventos `pose_set`/`pose_cleared`; `render.register_piece` devolve a pose manual (retorno antecipado, `method: "manual"`) e aceita `manual=False` para as métricas; sem snap automático (botões explícitos «Pose automática»/«Alinhar a 90°»).
- Routing: backend (estado, consistência, render, endpoints) → implementer; GUI/testes/docs → helper; um só implementer nos ficheiros partilhados (`state.py`, `server.py`, `consistency.py`) para evitar edições concorrentes.

## Prompt verbatim

```
Contexto
Projeto puzzle_piece_finder. Faz git pull. Lê docs/HANDOFF.md, docs/revisao.md (a sessão anterior fez a segmentação e o editor de contorno), docs/gui-design.md e docs/decisoes.md.

Regras
- Nada conta como progresso sem verdade de terreno. [V]/[NT]/[F].
- Commits em português, SEM co-author nem linha Claude-Session. Push sem --force.
- Não alteres testes existentes sem o dizeres à parte e com a razão.
- Não feches reports (o Tiago fecha pelos botões). Antes de escrever em projects/alpes, vê git status; se houver alterações do Tiago por commitar, para e diz-lhe.
- Regista em docs/revisao.md e atualiza o HANDOFF no fim.

PARTE 3: Aba Reports, peça e suspeitas
3.1 Aba Reports: tira a seta «→». Clicar numa linha continua a localizar a peça no tabuleiro E expande o report na própria linha (desce com a informação da página desse report), como as legendas recolhíveis. Dentro do report expandido: resolver, reabrir, eliminar/restaurar, editar.
3.2 Gaveta da peça: o botão «Editar report» não tem ver/fechar/resolver. Passa a mostrar o report existente e as ações resolver/reabrir/eliminar, para o Tiago não ter de ir à aba.
3.3 Suspeitas: quando a peça tem um report aberto, sai da lista «Suspeitas» e aparece só na lista de reports, com um chip «suspeita». A suspeita continua no CLI e em /api/suspeitas. Acrescenta a ação «falso alarme» (evento, reversível), com nota opcional. A verificação não volta a sinalizar a peça com a mesma pose/rotação, mas volta se os dados mudarem. Os falsos alarmes ficam registados como verdade de terreno para calibrar a verificação (conta-os num resumo).
3.4 Pré-visualização da peça: clique direito → «Copiar imagem (PNG)» e «Guardar PNG», só a peça, fundo transparente (clean_crop), via Clipboard API (ClipboardItem image/png; deve funcionar em localhost). Se o browser não deixar, diz porquê e dá o fallback.
3.5 Testes Playwright, sem overflow nos viewports (1366×768 a 150 %, telemóvel).

PARTE 4: Editar posicionamento
Opção «Editar posicionamento» à semelhança de «Editar contorno»: desbloquear a peça e ajustar levemente rotação e posição (setas de ajuste fino, rotação fina, arrastar), com a folga das juntas e a verificação de consistência a atualizar ao vivo. Grava um evento de pose marcado como manual (autor, data, valores antes/depois), reversível. As poses manuais ficam sinalizadas, para a verificação de suspeitas e as métricas as poderem excluir. Sem snap automático sem avisar.

Formato da resposta final
- [V]/[NT]/[F].
- O que o Tiago tem de ver na GUI e onde, e o que ficou por testar.
- Só me chamas para decisões que sejam do Tiago.
```

## Resultado

Commits (`main`): `d0833c9` falso alarme + junção suspeitas↔reports + SSE; `081c95c` GUI da Parte 3 (report expandido na linha, report em linha na gaveta, chip «suspeita», Falso alarme, menu de contexto PNG) + testes; `6b9c8e9` pose manual (backend: estado, render, consistência, endpoints, CLI, ferramentas com `manual=False`); `a29de9b` GUI «Editar posicionamento» (`src/web/pose.js`) + testes; o commit das docs (este). Suite completa 339 passed, 1 skipped (228 s) (OpenCV 4.11).

- **Parte 3 [V]:** seta removida; clicar numa linha localiza e expande o report na própria linha com todas as ações; gaveta com o report em linha; suspeitas com report aberto saem do bloco e ganham chip; «Falso alarme» reversível (eventos no log, assinatura por célula/rotação/contorno/vizinhas/gémea; na cópia dos Alpes P0290 volta a sinalizar com θ+90 e a marca fica obsoleta); clique direito → copiar/guardar PNG transparente (Chromium em localhost; fallback Guardar fora de contexto seguro). Layout sem overflow em 1366×768 a 150 % e telemóvel.
- **Parte 4 [V]:** pose manual como evento reversível (`pose_set`/`pose_cleared`, antes/depois, autor, nota), vista por todo o render e excluída das métricas e das Suspeitas; GUI sobre o tabuleiro com arrastar/rodar/setas, folgas e consistência ao vivo (13–26 ms no servidor), sem snap automático. Ensaio P0240: encostar o F 0,26 mm piora as juntas (−0,61 → −0,70; −0,08 → −0,09), como o RENDER §9.
- **[NT]:** Firefox/Safari, toque físico, clipboard fora de localhost, tempos de gravar a frio (20–28 s), poses manuais em métricas com dados reais, calibração com os falsos alarmes.
- **Pelo Tiago:** `git pull` + arrancar o servidor na máquina da GUI antes de usar as ações novas (o log ganha 4 ações); ver R0028/P0833 na aba Reports e na gaveta de (8,2); experimentar «Editar posicionamento» em (1,63); marcar as 12 do bloco c32|c33 como falso alarme quando confirmar o corte.
