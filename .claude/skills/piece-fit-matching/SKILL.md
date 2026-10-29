---
name: piece-fit-matching
description: Desenho e implementação do encaixe entre peças / montar grupos (feature 1 do ROADMAP), com perfis de lado flat/tab/blank, compatibilidade geométrica e continuidade de imagem, e secções montadas como referência local de alta resolução. Usar ao trabalhar em src/edges.py além da classificação atual, ou em qualquer código de "que peça encaixa aqui".
---

# Encaixe entre peças (feature 1 do ROADMAP)

## Âmbito: consulta interativa, não montagem global
- O objetivo é: **"dado este lado/grupo montado, ranqueia os melhores parceiros"**, com custo `O(N)` por consulta.
- **NÃO** montar as 3000 peças (sem solver global, sem backtracking sobre o puzzle inteiro). Se uma ideia exigir isso, para e reporta.
- Fora de âmbito nesta fase: classificação por ML e API REST.

## Ponto de partida real
`src/edges.py` hoje só **classifica** a peça (`edge`/`corner`/`interior`/`suspect`) contando lados retos do `minAreaRect` (`_STRAIGHT_RATIO`, `_CORNER_MARGIN`, `_MIN_SIDE_POINTS`) e alimenta o *border prior* do matching. O perfil por lado (flat/tab/blank) ainda **não existe**: é a fundação a construir, sem partir `classify_piece_edges`/`classify_pieces` nem os testes em `tests/test_edges.py`.

## Perfil de um lado
1. Divide o contorno da peça (`piece["contour"]`) pelos 4 cantos.
2. Normaliza cada lado: translada o canto inicial para `(0,0)`, roda para o canto final ficar em `(L,0)`, reamostra para N pontos equidistantes e **divide por L**. As fotos têm escalas diferentes; a escala física vem da calibração px/cm que a GUI já pede.
3. Classifica: desvio máximo pequeno → `flat`; para fora → `tab`; para dentro → `blank`.

## Compatibilidade
- Regra dura: `flat` não encaixa em nada; `tab` só com `blank`.
- Geometria: perfil A contra perfil B **invertido e negado** (percorre-se ao contrário e o eixo y troca de sinal); custo = MSE ou Fréchet entre os pontos reamostrados, mais a diferença dos comprimentos L em cm.
- Imagem: continuidade em **Lab** numa faixa fina de cada lado do corte (reutiliza `matching._cie_lab`).
- Combina numa pontuação com pesos nomeados (constantes `_FIT_*`) e devolve a shortlist + uma confiança no mesmo espírito do *gap* diferencial do matching (`high` quando o 1.º se destaca do 2.º).

## Arquitetura em 2 níveis (insight do utilizador)
1. Localizar a **secção montada** na referência (fácil: muito conteúdo).
2. Casar a peça solta contra a **secção de alta resolução**, não contra a referência inteira.
3. A peça que encaixa na **fronteira** da secção (geometria do corte + continuidade da imagem) é a vizinha.

## Regras
- Algoritmo novo em módulo puro (sem Tkinter, sem I/O) e testável com contornos sintéticos: um par tab/blank gerado que tem de dar o melhor custo; flat contra qualquer coisa = rejeitado.
- Mudanças que toquem `matching.py`/`segmentation.py` seguem o routing do `CLAUDE.md` (implementer).
- Verificação visual e números: segue a skill `cv-visual-verification`.
