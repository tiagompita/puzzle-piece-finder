# ROADMAP — Puzzle Piece Finder

## Estado atual (o que já funciona)

- Segmentação de peças soltas de uma foto (bom com peças espaçadas, fundo contrastante; degrada com peças juntas / baixo contraste).
- Classificação de bordas/cantos (`edges.py`).
- Motor de matching zonal Lab + textura + gap diferencial, com saída shortlist + confiança (Meta B: localiza onde a arte permite, assume ambiguidade onde não permite).
- Baseline honesto: ~12 de 64 peças localizáveis com confiança numa foto de teste; resto ambíguo por limite da arte (paisagem de deserto, grandes zonas uniformes).
- GUI liga tudo: Segment Photo, Match, Match All, Export JSON, Save Annotated. Testes pytest anti-regressão. Ingestão `.DNG` via PIL.

## Limites conhecidos e aceites (não perseguir sem novo ângulo)

- Teto de resolução: referência 8064x6048 / 3000 peças → muitas peças de céu/areia são ambíguas por natureza. Não é bug.
- Recorte perfeito precisa de foto boa (espaçada, contraste). Fotos difíceis dão máscara imperfeita.

## Features planeadas (por ordem de valor)

### 1. Encaixe entre peças / montar grupos (a grande feature)

Objetivo: dada a foto de uma secção JÁ MONTADA do puzzle + fotos de peças soltas, encontrar que peças soltas encaixam adjacentes ao grupo montado. Representar recortando a imagem da peça e colocando-a no sítio onde encaixa.

Insight-chave (do utilizador): o puzzle é enorme (1184x843mm), por isso uma foto de uma secção montada tem MUITO mais detalhe por peça que a imagem de referência da caixa. A secção montada serve de "referência local de alta resolução", contornando o teto de resolução.

Arquitetura proposta (2 níveis):

1. Localizar a secção montada na referência (fácil: uma secção tem muito conteúdo, ao contrário de 1 peça).
2. Casar a peça solta contra a SECÇÃO de alta resolução, não contra a referência inteira → muito mais sinal, menos ambiguidade.
3. Peça que encaixa na FRONTEIRA da secção (geometria de corte do `edges.py` + continuidade da imagem através do corte) = a vizinha.

Fundação: `edges.py` (perfil de cada lado, flat/tab/blank; compatibilidade = perfil A vs perfil B invertido+negado). Corte de âmbito importante: NÃO montagem global das 3000 peças; modo interativo "dado este lado/grupo, ranqueia os melhores parceiros" (O(N) por consulta).

### 2. Escalar a referência pelas secções montadas

Usar as fotos das secções montadas para calibrar/escalar a foto de referência à área real do puzzle. Liga-se à feature 1.

### 3. Câmara live

Alimentar o programa em direto do telemóvel. NOTA técnica: Bluetooth puro para vídeo não é prático; usar Wi-Fi (app IP-webcam, MJPEG) ou USB. Requer disciplina de threads (há riscos de race condition já sinalizados no cancel/worker).

### 4. Correção de perspetiva

Peças fotografadas em ângulo distorcem o recorte. Picker manual de 4 cantos → `getPerspectiveTransform`. Usa as medidas W/H em cm que a GUI já pede → dá px/cm calibrado. Prioridade baixa (a distorção atual é leve; só atacar se incomodar).

### 5. Recalibração de confiança (melhoria, não feature)

Afinar os thresholds de confiança contra um conjunto rotulado à mão (15-20 peças com posição verdadeira marcada pelo utilizador). Sobe peças "soft" a "alta". Requer trabalho manual do utilizador primeiro.

## Melhorias de qualidade registadas (backlog técnico)

- Recorte cosmético: mostrar peça limpa (transparente) em vez de mean-fill.
- Fallback manual de recorte (Load Pieces) para peças mal segmentadas.
- Falso-cluster / multi-peça em fotos de peças juntas / baixo contraste.
- Glare/specular dentro da máscara (tentado com inpaint, revertido: não se pagava; requer fill consciente de textura para valer).
- Strip-split (peça + fragmento numa tira).
- DeprecationWarning do Pillow (`Image.fromarray(arr,"L")`) em `segmentation.py` ~793.
- Persistência de sessão (fechar a app perde tudo).
- Tabela de resultados clicável na GUI (hoje só logs).
