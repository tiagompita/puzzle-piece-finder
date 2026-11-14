# 2026-11-14 — F1d: correções à GUI nova (/novo/) depois do teste do Tiago no PC

## Porquê

O Tiago testou a F1c no PC (registo do servidor de 2026-11-14 02:00–02:12): rejeitou e desfez P0980 e depois carregou em «Guardei à parte» na mesma peça, e não viu como desfazer. Pediu também rótulos novos para os cartões sem vizinha montada («Colocar aqui», com a peça desenhada «por confirmar»), um botão «localizar», ícones, a contagem certa no ecrã vazio, o `test_twin_real` a correr, a limpeza do scratchpad e os recortes para as máscaras do Photoshop. A F2 não arranca.

## Decisões

- Ponto 1 (causa [V]): o desfazer era só um aviso de 9 s que aparecia ≈ 3 s depois do clique, quando a recarga por SSE já tinha mostrado o cartão seguinte; depois dos 9 s não havia desfazer à vista. Correção: faixa «última ação» com «Desfazer» no topo do painel até à ação seguinte («A gravar…» enquanto escreve); a 390 px o aviso em baixo deixa de aparecer (tapava «Colocar aqui»).
- Ponto 2: verificado no código que o pedido não contradiz o estado (a `posicao_conhecida` deixa a célula vazia: não é molde, nem vizinha, nem conta no progresso); implementado só na GUI e no `/api/board` (imagem ténue + contorno tracejado da própria peça, legenda «Por confirmar», menu para esconder).
- Ponto 3: «Não pertence aqui» sem «Porquê?»; «Não encaixa» mantém-no.
- Ponto 5: Lucide (ISC + MIT do Feather), 20 SVG locais e a licença em `src/web/novo/icons/`; sem texto só «localizar», «⋯» e o zoom (estes dois já eram símbolos), todos com `aria-label`.
- Vocabulário meu: «Sem vizinha montada» no título do cartão e em «A seguir», «por confirmar» nos avisos e na lupa.
- Ponto 7: memória do E-real-2 no repositório (53 KB) com o script que a refaz.
- Regras completas em `docs/decisoes.md` (2026-11-14, F1d).

## Prompt verbatim

«F1d: correções à GUI nova (/novo/), a partir do teste do Tiago no PC. Não arranques a F2.

1. Erro: depois de «Guardei à parte» o Tiago não vê a opção de desfazer. Reproduz, encontra a causa e corrige. Teste de browser que falha se o desfazer não estiver visível e clicável depois da ação.
2. Cartões de gémea sem vizinha montada: o botão principal passa a «Colocar aqui» e o oposto a «Não pertence aqui». Por dentro continua a ser posição conhecida, não colocação verificada: a peça aparece no lugar no tabuleiro, mais ténue e com contorno tracejado («por confirmar»), e não serve de molde nem conta no progresso até uma vizinha encaixar. Se isto contradisser o código, para e diz-me antes de implementar.
3. «Não pertence aqui» não pergunta «Porquê?».
4. Botão «localizar» no cartão, só com ícone e dica: volta a centrar o tabuleiro no alvo da peça atual, sem mudar de peça.
5. Ícones: usa o Lucide (https://github.com/lucide-icons/lucide). Confirma a licença no repositório e guarda-a com os ícones. Copia os SVG para o repositório (nada carregado da internet). Ícone com texto nas abas Montar, Peças e Importar scan, nos botões principais e nas entradas do menu «⋯» (Diagnóstico, Atividade, Mostrar a forma esperada e as restantes). Só o «localizar» fica sem texto. Todos com aria-label quando não têm texto.
6. Ecrã vazio: troca a contagem «para guardar à parte» (dá sempre 0) pela contagem das peças já guardadas à parte.
7. test_twin_real é saltado por faltar um ficheiro do scratchpad: põe os dados no repositório ou documenta como se geram, para o teste correr.
8. Apaga alpes_base e proj no scratchpad só depois de confirmares que nenhum teste ou ferramenta os usa, com as mesmas verificações de caminho de antes.
9. Máscaras do Photoshop: gera em docs/diagnostico/editor/gt_photoshop/ o recorte da folha de P1203, P0045, P1245 e P0198 (PNG, com margem), e um LEIAME curto: abrir no Photoshop, apagar tudo o que não é peça, gravar como PNG com transparência, com o mesmo tamanho e o nome P####.png.

Fecho: suite completa com o .venv, capturas a 1366×768 e a 390×844, lista dos testes existentes alterados na mensagem do commit. Usa graphify query antes de grep ou de ler ficheiros e corre graphify update . no fim. Commits sem Claude como co-author.»

## Resultado

- Feitos os 9 pontos; a F2 não arrancou. Código, testes e ferramentas em `959b46d`; docs, capturas e recortes no commit seguinte.
- Suite [V]: 508 passed, 1 skipped (PyMuPDF real), 0 failed, 430 s com os slow. Testes novos: `test_undo_visible_after_colocar_aqui` (1366 e 390; falhava antes da correção), `test_colocar_aqui_draws_por_confirmar_not_in_progress`, `test_localizar_recentres_without_changing_piece`, `test_icons_local_aria_and_layout` (1366 e 390), `test_por_confirmar_is_not_a_mould_nor_neighbour_nor_progress`, `test_novo_icons_local_and_licensed`; `test_ereal2_find_twin` deixou de saltar.
- Testes existentes alterados: `test_gui_novo.py` (`test_guardar_card_not_nada_no_encaixa_dashed`, `test_guardar_then_undo_toast_and_ctrl_z`, `test_order_coloca_first_then_guardar`, `test_lupa_shows_piece_and_place_proposals`: rótulos novos; `test_nao_e_esta_undo` → `test_nao_pertence_aqui_no_porque_and_undo`: sem «Porquê?»), `test_twin_real.py` (memória do repositório).
- Por fazer [NT]: o teste do Tiago no PC e no telemóvel; Firefox/Safari; as máscaras do Photoshop.
