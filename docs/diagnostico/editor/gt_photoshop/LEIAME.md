# Máscaras à mão no Photoshop (P1203, P0045, P1245, P0198)

Cada `P####.png` é o recorte da folha do scan que o editor de contornos mostra: a peça com 3 mm de margem à volta,
à resolução do scan (300 dpi). Feito por `tools/diagnostico/editor/gt_photoshop_recortes.py`; a posição de cada
recorte na folha está em `recortes.json`.

O que fazer, para cada peça:

1. Abrir `P####.png` no Photoshop.
2. Apagar tudo o que não é peça (o papel verde, a sombra escura à volta, outras peças), deixando-o transparente.
3. Não recortar nem mudar o tamanho da imagem.
4. Gravar como PNG com transparência, com o mesmo nome (`P####.png`), nesta pasta, por cima do original (o original
   refaz-se com o script).

Nada disto está ligado ao índice nem ao projeto: as máscaras só servem para medir o editor.
