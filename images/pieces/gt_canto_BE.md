# Canto inferior esquerdo (BE) e peças de céu do E-real-2 — scans de 31-out-2026, 300 dpi, papel verde

## Coordenadas do canto BE

O Tiago usa coordenadas locais (k, j):
- k = linha contada **de baixo para cima** (k = 1 é a borda de baixo);
- j = coluna contada **da esquerda para a direita** (j = 1 é a borda da esquerda).

Conversão para coordenadas globais (l, c), com a grelha 64 × 47: **l = 48 − k, c = j**.

**Gémeo:** o gémeo de BE(k, j) é a peça global **(k, 65 − j)**, ou seja, a peça na linha k a contar de cima e na coluna j a contar da direita, no canto superior direito. As 20 células interiores presentes têm os gémeos em l = 2–5 e c = 58–63.

**Peças em falta:** (4,6), (4,7), (5,6), (5,7), (6,2)–(6,7) e (7,2)–(7,7).

**Interiores presentes:** k = 2–5 × j = 2–7, menos as quatro (4,6), (4,7), (5,6), (5,7). São **20 peças**.

## Ficheiros do canto BE

| Ficheiro | Conteúdo |
|---|---|
| `gt_canto_BE_montadas_300dpi.jpg` | O bloco montado, pela frente, com o canto em baixo à esquerda na imagem (orientação direita). A coluna j = 1 sobe até k = 7, com as peças escuras no topo. As linhas de corte na relva **não servem** (E-real: 1–3/41). Fica só como referência visual. |
| `gt_canto_BE_soltas_300dpi.jpg` | As 20 interiores soltas em vista explodida (cada peça afastada sem rodar), mais a borda em L montada. |

### Disposição das soltas

A disposição é o bloco **rodado 90° no sentido anti-horário**, como no canto BD. Isto é inferido e bate com a imagem.
- A faixa de baixo é a coluna j = 1: o canto fica em baixo à direita e as peças escuras na ponta esquerda.
- A faixa da direita é a linha k = 1.
- Na grelha das soltas:
  - a coluna s do scan (1–4, **da direita para a esquerda**) corresponde a **k = s + 1**;
  - a fila r do scan (1–6, **de baixo para cima**) corresponde a **j = r + 1**.
- As colunas s = 3 e 4 (k = 4 e 5) têm só 4 peças, as de j = 2–5. A coluna k = 5 é a banda escura.

**Verificado no Project:** com o limiar simples saem 20 peças (342–469 mm²) mais a faixa em L.

## Peças de céu do E-real-2

As peças foram escolhidas pelo Tiago **pelo aspeto** da zona do canto superior direito, sem ordem. Os scans originais eram 2 PDFs com 2 páginas cada; as imagens foram extraídas sem perdas (JPEG embutido, 300 ppi, 2544 × 3504).

| Ficheiro | Peças |
|---|---|
| `ereal2_ceu_f1p1_300dpi.jpg` | 35 |
| `ereal2_ceu_f1p2_300dpi.jpg` | 15 |
| `ereal2_ceu_f2p1_300dpi.jpg` | 42 |
| `ereal2_ceu_f2p2_300dpi.jpg` | 8 |
| **Total** | **100** |

**Atenção:** o papel verde não cobre a largura toda do scan. Há uma tira fina de bordo à esquerda e/ou à direita que sai como um componente fino e comprido ao longo do bordo (80–1300 mm², sem forma de peça). Não é uma peça: deve ser rejeitado pela forma ou pela flag `touches_frame`.

O Tiago guardou estas 100 peças. As propostas do programa são verificadas por colocação física: encaixa e a imagem bate certo.

Disposição verificada pela imagem em 2026-10-31 (faixa de baixo = coluna j = 1 com o canto em baixo à direita e as escuras à esquerda; colunas da direita com 6, 6, 4, 4 peças); GT legível por máquina em `docs/diagnostico/gemeos/ereal2_gt_BE.json` (verificações automáticas em `tools/diagnostico/gemeos/ereal2.py`; resultados em `docs/diagnostico/gemeos/EREAL2.md`).
