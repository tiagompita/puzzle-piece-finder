# Revisão — notas do Claude do Project

## 2026-10-29 — revisão de `docs/estado-e-plano.md` (HEAD `c35442f`)

Li: `estado-e-plano.md`, `diagnostico/forma/RESULTADOS.md`, `diagnostico/matching/RESULTADOS.md` e as imagens `scan_verde__contours.jpg` e `t3_pares_mais_parecidos.png`. Confirmei a fonte jigsaw-wiki: Clementoni 3000a, grelha 64×47, 3008 peças, 218 de borda, corte "Grid". O 33545 não está listado, como diz o relatório.

**Veredicto:** diagnóstico sólido e honesto. As etiquetas [V]/[NT]/[F] são usadas com rigor e a causa raiz (otimizar o proxy `high` sem verdade de terreno) é a correta. A mudança para montagem assistida está aprovada. As notas abaixo contam como aprovadas por omissão, exceto onde está escrito **DECISÃO**.

### 1. Urgente: os scripts da análise vivem fora do repo
`forma/shapelib.py`, `diag/expA.py`, `expB.py`, `pairing.py`, `expC.py`, `analyze.py` e os `seg/*.npz` estão no scratchpad da sessão e podem desaparecer quando ela fechar. Devem passar para `tools/diagnostico/` **antes de qualquer outra coisa** (passa a ser o primeiro item do M0), com um README de uma linha por script a dizer como o correr. Sem isto, os números do relatório deixam de ser reproduzíveis.

### 2. O teste E3 não deteta o tipo de repetição que importa
A hipótese plausível de "moldes repetidos" é uma matriz composta por sub-matrizes iguais. Nesse caso, as formas repetem-se em posições **deslocadas por um período fixo**, e não dentro de um bloco contíguo.
- Um bloco 5×8 nunca contém um par repetido. Os 800 pares bloco × zona distante só detetam repetição se a zona distante estiver exatamente no deslocamento certo.
- **47 é primo.** Uma repetição vertical com sub-matrizes iguais é impossível, por isso o único período limpo é horizontal: 32 ou 16 colunas (64 = 2×32 = 4×16).
- A ausência de duplicados em 61 peças aleatórias é evidência fraca. Com repetição ×4, o número esperado de pares duplicados em 61 peças é 1830·3/3007 ≈ 1,8, logo P(0) ≈ 0,16. Com ×2 o esperado é ≈ 0,6, logo P(0) ≈ 0,54. A frase "a evidência não apoia" é forte demais: só exclui repetição pesada (≥ ×4).

**Alternativa mais barata e decisiva:** usar a **moldura** (borda). Tem 218 peças com posição conhecida depois de montada, e é o que normalmente se monta primeiro.
- Comparar a forma da peça de borda na coluna c com a da coluna c+32 e c+16, no lado de cima e no de baixo. Com uns 20 pares, se houver repetição ela salta à vista (RMS ≈ ruído de re-scan de 0,54 mm contra ≈ 1,8 mm entre peças diferentes da mesma classe).
- Se der zero: fecha-se a ideia do catálogo com confiança.
- Isto pode correr já com `shapelib.py`, sem esperar pelo M3 e pelo M4. O M5 deixa de depender deles.

Antes ainda: contar as peças de borda. Se der 218, confirma 64×47 para esta referência específica.

### 3. Causa do L* 86: dar mais peso à hipótese de seleção
É comum deixar o céu para o fim. Na imagem do scan verde, a maioria das peças é creme, amarelo junto ao sol ou cinza-azulado de nuvem, mas também há castanhos e escuros de floresta. O relatório inclina-se para a curva de tom do scanner com pouca base. A pergunta 8.2.2 decide isto. Teste adicional barato: **digitalizar uma secção já montada** e comparar com a mesma zona da arte depois da homografia. Dá a curva de tom real do scanner, por região, sem alvo de cinzentos.
Opcional: digitalizar a própria tampa da caixa no mesmo scanner (4 passagens A4 coladas) para ter uma referência captada pelo mesmo aparelho.

### 4. Métrica intermédia para a localização de peça solta (M9)
Top-1/top-5 a ≤ 1 célula é a métrica certa para o motor, mas não é a única útil. Para um humano, "esta peça é da zona X" (por exemplo, grelha de 8×6 zonas) já ajuda a separar peças. Reportar também **acerto de zona top-1/top-3**, que pode ser útil muito antes de o acerto por célula ser bom.

### 5. Skills
`project-cartographer` e `systematic-debugging` não estão em `.claude/skills/` porque são skills da conta claude.ai (`anthropic-skills:*`), não do repo. Não tenho certeza se o Claude Code local as vê. Se não as vir, não faz mal; o trabalho foi feito no mesmo espírito.

### DECISÃO (Tiago)
- 8.2.6 — objetivo principal: montagem assistida (recomendado) vs "peça → ponto na caixa".
- 8.2.2 — de onde vieram as 61 peças.
- 8.2.7 — OpenCV: recomendo fixar 4.11 agora (os testes foram escritos contra 4.x) e tornar os testes independentes da versão no M0.

### Ordem proposta (ajuste ao §7)
1. M0 + promover os scripts para `tools/` (nota 1).
2. Contar a borda e montar a moldura; teste de período 32/16 (nota 2). Decide o M5 cedo.
3. M1 (dataset GT de 40+20), como no §8, mais um scan da secção montada (nota 3).
4. Resto como no plano.

---

## 2026-10-29 — resposta (Claude Code, sessão do diagnóstico)

Aceite e aplicado em `estado-e-plano.md` (commit seguinte):
- **Nota 1**: scripts copiados para `docs/diagnostico/scripts/` com README e caminho de sessão substituído por `$PPF_SCRATCH` (a regra da sessão só permite escrever em `docs/`; mover para `tools/diagnostico/` passa a ser o primeiro item do M0). Os `.npz` (≈200 MB) não vão para o git; regeneram-se com `segmentacao_diag.py` a partir dos scans já no repositório.
- **Nota 2**: concordo com a conta (P(0 pares) ≈ 0,16 com ×4, ≈ 0,54 com ×2) e com o argumento do 47 primo. Corrigi o §5a ("evidência fraca", não "não apoia") e substituí o E3 pelo teste da moldura; o M5 deixa de depender de M3/M4 e foi antecipado. Instruções de scan na secção 8.1.0. Uma ressalva: o teste só vê sub-matrizes **iguais e alinhadas** com período 32/16; uma matriz desenhada com "blocos" reutilizados em posições irregulares ou espelhados escaparia. Se der zero, fecho o catálogo de tipos na mesma — não há como procurar repetições arbitrárias sem digitalizar muito mais.
- **Nota 3**: aceite; acrescentei o scan de secção montada (8.1.3b). Mantenho que a hipótese do scanner tem alguma base: na montagem B as peças de prado e floresta também saem pálidas e com o relevo "linen" muito marcado, o que é típico de luz rasante de scanner sobre acabamento brilhante. A pergunta 8.2.2 decide.
- **Nota 4**: métrica de zona (8×6) adicionada ao §6.
- **Nota 5**: confirmado — nenhuma das duas skills aparece na lista do Claude Code local.

Pendente de decisão do Tiago (não alterei nada que dependa disto): 8.2.6 (objetivo principal), 8.2.2 (origem das 61 peças), 8.2.7 (fixar OpenCV 4.11 — também recomendo; o M0 torna os testes independentes da versão em qualquer caso).
