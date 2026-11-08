# Servidor da GUI em repouso: porque é que o portátil aquecia (ronda 8, 2026-11-08)

_Parte 0 do prompt de 2026-11-08 (ronda 8). Método e números abaixo; script `tools/diagnostico/servidor/repouso.py`; dados `repouso_antes.json` / `repouso_depois.json`. Etiquetas **[V]** verificado, **[NT]** não testado, **[F]** falha._

## 1. Processos Python em curso (0.1) — medido às 20:4x de 2026-11-08, servidor do Tiago parado

| PID | processo | início | CPU acumulada | pai | linha de comandos | veredicto |
|---|---|---|---|---|---|---|
| **3168** | `python3.13.exe` | 2026-11-08 03:23:45 | **7 937 s** às 20:20; **9 584 s** às 20:48; **100 % de um núcleo** em duas amostras (10 s e 5 s) | `bash.exe` 14440 ← 14568 ← 5488 ← `claude.exe` 11032 (sessão do Claude Code iniciada às 02:39, a ronda 6) | `…\WindowsApps\python.exe -` (script lido do stdin) | **órfão de uma ferramenta de sessão anterior**: o comando do pai é um heredoc `cat >> docs/gui-design.md <<'EOF' … EOF` seguido de `python - <<'EOF' … 2>/dev/null \|\| true` com as aspas mal fechadas; o `python -` ficou pendurado desde as 03:23 a queimar um núcleo (≈ 17 h). **Terminado por PID às 20:48** (`Stop-Process -Id 3168`), depois de listado aqui e no plano. Não era o servidor nem nada do Tiago. |
| 5044, 9348 | `python3.13.exe` | 2026-11-07 13:35 | 2,4 s / 0,8 s | `Code.exe` | `lsp_server.py` / `lsp_runner.py` do isort (extensão do VS Code) | inofensivos, não tocados |

Portas 8765 / 8766 / 8000: **ninguém à escuta** (nenhum servidor esquecido). Não havia `pytest`, Chromium/Playwright, `rebuild_scans` nem ferramentas de diagnóstico em curso. Regra que fica: **nunca `taskkill //IM python.exe`** (mata a suite ou outros processos); só por PID, listado e justificado; e os heredocs com muitas aspas no Bash desta máquina **falham de forma silenciosa e podem deixar um `python -` a 100 %** — escrever ficheiros `.py` com a ferramenta Write (já na HANDOFF).

Com o PID 3168 terminado, o portátil deixa de ter um núcleo ocupado em permanência: **essa era a causa das ventoinhas** [V: 100 % medido duas vezes; a verificação das ventoinhas em si é do Tiago].

## 2. O servidor em repouso (0.2): o que o código faz sozinho

Leitura do código (sem medição): a única coisa que acorda sem pedidos é o gerador SSE `/api/events` (`server.py:2654–2679`), com **polling a cada 0,4 s por cliente** (`events_after` varre o deque de 500 eventos sob `cond`) e keep-alive a cada 15 s; `emit()` faz `notify_all()` mas ninguém espera na `Condition`. Não há timers, observadores de ficheiros, nem loops: o thread de preparação e o dos buracos são one-shot; o browser não faz polling depois de `estado == pronto` (só um `setInterval` de 3 s durante o arranque), não tem `visibilitychange` nem animações CSS; o painel «Atividade» pede `/api/atividade` uma vez ao abrir e depois só recebe SSE.

### 2.1 Medição «antes» (código até `15376ff`), cópia `alpes_r8`, porta 8766, janelas de 60 s sem pedidos, 60 s de assentamento

Método: `repouso.py` arranca o servidor com o interpretador do venv (no Windows o `Scripts/python.exe` é um lançador: mede-se a **árvore** de processos, o interpretador real é o filho), espera `estado == pronto`, monta o cenário com Playwright/Chromium a 1366×768, deixa assentar e mede `psutil.cpu_times()` da árvore numa janela de 60 s sem nenhum pedido; `top_threads` = CPU por thread do interpretador. Projeto da cópia: 1333 peças, 451 soltas, 209 buracos.

| cenário | separadores | Atividade | SSE | CPU (% de um núcleo) | thread dominante | leitura |
|---|---|---|---|---|---|---|
| a | 0 | — | — | **0,18** | uma thread a 0,18 (`sync` de `/api/status`? não: sem pedidos; é o event loop do uvicorn a acordar nos seus timers) | repouso puro |
| b (1.ª corrida, 60 s de assentamento) | 1 | fechada | sim | **108** | 1 thread a 99,3 % | **não é repouso**: o 1.º `GET /api/fetch` da página arrancou o thread dos buracos (`rank_all`, 373 tiras calculadas em 157 s, `strips.npz` da cópia inválido porque os ativos foram refeitos) — trabalho one-shot que também acontece no portátil a seguir a cada arranque quando as tiras não estão em cache |
| b (2.ª corrida, 240 s de assentamento, `repouso_antes_b.json`) | 1 | fechada | sim | **0,60** | event loop 0,52 | repouso real com 1 separador: SSE a acordar 2,5×/s; na mesma corrida c deu 0,47 (painel aberto não custa) |
| c | 1 | aberta | sim | **0,75** | event loop 0,73 | o painel aberto não acrescenta nada mensurável; o custo é o SSE |
| d | 3 | fechada | sim | **1,07** | event loop 1,04 | ≈ +0,3 por separador (polling de 0,4 s por cliente) |
| e | 1 | fechada | **não** (stub de `EventSource`) | **0,23** | event loop 0,23 | sem SSE a página não custa nada em repouso |

**Fonte → % CPU (antes):** event loop do uvicorn sem clientes 0,18–0,23; **gerador SSE `/api/events` ≈ 0,3–0,5 por separador** (0,47–0,75 com 1, 1,07 com 3): é o único custo de repouso atribuível ao código, e já cumpre a meta de 1 % com 1–2 separadores; com 3 passa-a por pouco. Nada de polling do browser, do painel «Atividade», de observadores ou de threads presos. O que aquece o portátil não é o repouso: é (i) o `python -` órfão (§1) e (ii) os picos one-shot (tiras/buracos a seguir ao arranque, 100 % de um núcleo durante 2–3 min; a consulta completa depois de uma importação), que acabam.

## 3. Correção (0.3) e medição «depois»

(preenchido depois da implementação: SSE por espera com `asyncio.Event` por cliente acordado por `emit()`; meta < 1 % de um núcleo)

## 4. Regra para a fila de importação (0.4)

O trabalhador da fila espera numa `threading.Condition` e só acorda por evento (adicionar, cancelar, repetir, mover, fim de trabalho); o teste `tests/test_server_idle.py` mede o CPU do processo com a fila vazia e um cliente SSE ligado.
