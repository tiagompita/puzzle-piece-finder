# 2026-11-08 (8) — ventoinhas em repouso, «pelo encaixe», importação PDF/multi-ficheiro, fila de importação

## Porquê

O Tiago diz que o portátil corre Python em segundo plano e as ventoinhas ficam altas só com o programa ligado; quer dois ajustes de GUI («por buraco» → «pelo encaixe»; «Ver no tabuleiro» nos cartões pelo encaixe só localiza); quer importar PDF (lote 9: 2 páginas com um JPEG cada) e várias imagens de uma vez para um saco, com dpi validado e idempotência; e quer uma fila de importação persistente, um trabalhador de cada vez, sem polling em repouso, com as confirmações a continuarem possíveis durante a importação.

## Decisões

- **Causa das ventoinhas (medida):** um `python.exe -` órfão de um comando `bash` de uma sessão anterior do Claude Code (heredoc mal fechado às 03:23 de 2026-11-08), a 100 % de um núcleo durante ≈ 17 h (9 584 s de CPU); terminado por PID depois de listado e justificado (`docs/diagnostico/servidor/REPOUSO.md`). Não era o servidor do projeto.
- SSE do servidor passa de polling (0,4 s por cliente) a entrega por espera; meta < 1 % de um núcleo em repouso, medida antes/depois.
- PDF sem dependência nova: extração dos JPEG `DCTDecode` tal como estão; páginas vetoriais dão erro claro (rasterizar exigiria PyMuPDF: decisão do Tiago). dpi pelo MediaBox, validado pela corda mediana das peças (aviso fora de [0,95, 1,05]); aviso de fundo se ΔE > 15 ao verde canónico; nenhum aviso recusa.
- Idempotência por sha256 (a 2.ª importação do mesmo ficheiro é ignorada; `tests/test_state.py::test_ingest_synthetic` passa a esperar isso: alteração declarada).
- Fila em `projects/<id>/import_queue.jsonl` (só-acrescentar, replay), trabalhador único por `Condition` (sem polling), segmentação fora do `wlock`, commit e uma só reconsulta completa por trabalho sob o `wlock`; confirmações esperam até 90 s em vez de falhar com 409. Risco declarado: sem lock entre processos (CLI `src.confirm` + servidor): decisão do Tiago.
- Gaveta do fundo com dois separadores («Atividade» | «Fila de importação»), sem botão novo na barra do topo.
- «Ver no tabuleiro» nos cartões pelo encaixe passa a `showCellOnBoard`; a pré-visualização fica no botão «Pré-visualizar encaixe» (`tests/test_gui_holes.py` ajustado: declarado).

## Prompt verbatim

```
Contexto
Projeto puzzle_piece_finder. Faz git pull. Lê docs/HANDOFF.md, docs/gui-design.md, docs/decisoes.md. Regras: [V]/[NT]/[F]; commits em português SEM co-author nem linha Claude-Session; push sem --force; não alteres testes existentes sem o dizeres; não feches reports; vê git status de projects/alpes antes de escrever lá (o servidor da GUI do Tiago está parado enquanto trabalhas). Nunca uses ingest_all.py (perde as colocações do Tiago). Testa em cópias de projects/alpes.

Parte 0 — Porque é que o portátil tem as ventoinhas altas em repouso (fazer primeiro)
O Tiago diz que o portátil corre Python em segundo plano e as ventoinhas ficam altas sem ele estar a fazer nada, só com o programa ligado. Investiga com medição e não mates nada que não tenhas lançado tu sem o listar e justificar primeiro.
0.1 Lista os processos Python em curso (nome, PID, linha de comandos, CPU acumulada, hora de início, processo pai; no Windows com PowerShell/CIM) e quais são do projeto: servidor (src.server), pytest, Playwright/Chromium, rebuild_scans, ferramentas de diagnóstico, servidores esquecidos de sessões anteriores. Sinaliza duplicados (mais de um servidor na porta 8765 ou noutras).
0.2 Mede o CPU do servidor em repouso (a janela de 60 s sem nenhum pedido), com o separador da GUI fechado e depois aberto (com o painel «Atividade» aberto e fechado). Isola a causa: laço sem espera ou com espera curta, SSE/heartbeat, polling do navegador, tarefas em segundo plano (recálculo de buracos, caches, rebuild de ativos desatualizados, observador de ficheiros), threads que não terminam. Usa psutil ou um perfilador se estiver disponível; senão amostragem de stack com threading/faulthandler. Mostra a tabela: fonte → % CPU.
0.3 Corrige o que for atribuível ao código do projeto (esperas bloqueantes em vez de ocupadas, polling com intervalos razoáveis, SSE só com subscritores, tarefas só por evento). Meta declarada: servidor em repouso < 1 % de um núcleo. Se a causa for outra coisa (outro programa), diz qual e o que o Tiago pode fazer.
0.4 Esta linha de base serve para a fila de importação da Parte 3: o trabalhador da fila não pode introduzir polling nem espera ocupada em repouso (event-driven).

Parte 1 — Pequenos ajustes de GUI
1.1 Onde a GUI diz «por buraco» passa a dizer «pelo encaixe» (chips, títulos, textos, docs, testes que o citem). O valor guardado nos eventos (origem «buraco») NÃO muda, para não partir o log nem o contador.
1.2 Nos cartões «pelo encaixe», «Ver no tabuleiro» faz só o que faz nos outros cartões: localizar a posição (zoom e realce da célula). Retira a pré-visualização da peça encaixada desse botão. Pode existir um botão separado «Pré-visualizar encaixe», opcional.

Parte 2 — Importação: PDF e várias fotos por lote
2.1 Aceitar PDF e imagens (JPEG/PNG/TIFF) na importação, vários ficheiros de uma só vez, qualquer mistura. Cada página de PDF e cada imagem é uma folha de scan. Amostra real: images/pieces/lote 9.pdf (2 páginas; cada uma tem um único JPEG incorporado, DCTDecode, RGB 2544×3504, sem metadados de produtor). Extrai a imagem incorporada tal como está (sem recompressão); só rasteriza a 300 dpi se a página for vetorial. O dpi lê-se do tamanho da página (MediaBox) contra os píxeis; atenção: 2544 px de largura não é o A4 a 300 dpi dos outros scans (2480 px), por isso VALIDA a escala contra o tamanho real das peças (≈ 18 mm de célula) e avisa se o dpi calculado e o medido discordarem. Um dpi mal lido estraga as medidas em mm (forma, gémeas). Avisa também se o fundo não for o verde saturado canónico, sem recusar.
2.2 O esquema já suporta vários scans por lote (ex.: lote 4 = S0028 + S0029, «nº no lote» a continuar, até 72). Verifica isso nos dados e no código e NÃO mudes o esquema. O que falta é importar várias folhas de uma só vez (ficheiros e páginas de PDF), mantendo o lote, a ordem das folhas e a continuação do «nº no lote». Se a continuação não estiver garantida para importações em lote, corrige só isso.
2.3 Idempotência: importar o mesmo ficheiro duas vezes (sha256) não duplica peças.
2.4 Testa o fluxo todo, numa cópia, com o lote 9 (o PDF). Só no fim, se git status de projects/alpes estiver limpo e o Tiago não estiver a usar a GUI, importa o lote 9 no projeto real e diz-me o que entrou (nº de folhas e peças, avisos).

Parte 3 — Fila de importação
O Tiago quer pôr na fila vários lotes (ficheiros + identificação do saco/lote) e que, quando um acaba, o seguinte comece sozinho. Cada importação demora minutos.
3.1 Fila persistente em disco (projects/<id>/import_queue.json ou eventos append-only; escolhe e justifica) que sobrevive a reinícios. Cada trabalho: lote/saco, ficheiros, estado (em fila, a correr, concluído, falhado, cancelado), progresso por etapa, hora, erro. Um único trabalhador de cada vez; adicionar enquanto outro corre; reordenar e cancelar os que estão em fila; repetir um falhado.
3.2 Interface: painel «Fila de importação» (não é uma 7.ª aba: recolhível ou junto do painel «Atividade»), com adicionar ficheiros, o campo do lote/saco e o estado em tempo real (SSE). Uma falha não bloqueia a fila. Se o servidor reiniciar a meio de um trabalho, esse trabalho volta ao início de forma segura (idempotência, 2.3).
3.3 Concorrência: o Tiago pode colocar peças e confirmar enquanto a importação corre. Garante que as escritas no log.jsonl continuam atómicas e ordenadas (bloqueio) e que a recomputação das consultas («Vai buscar», buracos) é serializada e corre uma só vez depois de cada trabalho, não a cada peça. Se encontrares um risco real de corrupção, diz-mo antes de avançar.
3.4 Testes: unitários da fila (ordem, cancelar, falha, retoma depois de um reinício simulado), Playwright da interface sem overflow (1366×768 a 150 % e telemóvel), um teste de concorrência (escrita de evento durante um trabalho) e um teste de CPU em repouso com a fila vazia.

Fora de âmbito: aprender com os contornos manuais (fica para o futuro); alterar limiares ou o CV (é a sessão A).

Formato da resposta final
- [V]/[NT]/[F], com números (CPU em repouso antes/depois).
- O que o Tiago tem de ver na GUI e onde; e o que fazer com o portátil, se a causa não for o projeto.
- Só as decisões que são dele.
```

## Resultado

(preenchido no fim da ronda)
