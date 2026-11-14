# Ícones da GUI nova (/novo/)

SVG do [Lucide](https://github.com/lucide-icons/lucide), copiados sem alterações do ramo `main` do repositório em
2026-11-14 (pasta `icons/`). Licença: ISC (Lucide Icons and Contributors), com MIT (Cole Bemis) para os ícones
derivados do Feather; o texto completo está em `LICENSE-lucide.txt`, copiado do `LICENSE` do mesmo repositório.

São servidos por este servidor (nada se carrega da internet) e desenhados por máscara CSS em `novo.css`
(`.ico.i-<nome>`), com a cor do texto. Para acrescentar um: copiar o SVG para aqui, verificar que só tem
`svg`/`path`/`circle`/`line`/`rect`/`polyline` (sem `<script>`, `on*=`, `href` nem URLs externas) e acrescentar a classe em
`novo.css`; `tests/test_montar.py::test_novo_icons_local_and_licensed` verifica os dois lados.

F2 (2026-11-14): `rotate-cw`, `settings`, `flag`, `scissors`, `plus`, `sun`, `droplet` e `arrow-up-from-line`, copiados
sem alterações do mesmo ramo `main` nessa data.
