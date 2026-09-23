# Fotos do acervo de demonstração

As fotos dos imóveis do acervo simulado moram aqui, separadas por categoria. `scripts/indexar_fotos.py`
normaliza e publica a lista em `data/imoveis/fotos_pool.json`, e `scripts/gerar_imoveis.py` distribui
**2 a 3 fotos por imóvel**, coerentes com o tipo — galpão não recebe foto de sala de estar.

## O que colocar em cada pasta

| Pasta | Serve para | Quantas bastam | O que funciona bem |
|---|---|---|---|
| `residencial/` | apartamento, casa, sobrado, studio, kitnet, cobertura | ~12 | sala, quarto, cozinha, fachada de prédio, fachada de casa, varanda |
| `sala-comercial/` | sala e conjunto comercial, laje corporativa | ~6 | sala vazia, andar corporativo, escritório aberto, recepção |
| `loja/` | loja | ~5 | loja de rua com vitrine, interior de loja, esquina comercial |
| `galpao/` | galpão | ~5 | galpão vazio, doca, pé-direito alto, pátio de manobra |

JPG, PNG, WebP ou HEIC; de preferência horizontal e com 1200 px de largura ou mais. O script
redimensiona, converte para JPEG progressivo e renomeia para `<categoria>-NN.jpg`; o original vai
para `<categoria>/originais/`, que fica fora do git — assim rodar o script duas vezes não converte
o mesmo arquivo de novo.

**Uma convenção no nome do original importa:** se ele contiver `casa` ou `sobrado`, a foto vira
`residencial-casa-NN.jpg` e passa a ser usada **só** em casa e sobrado, sempre como capa. As demais
fotos residenciais nunca aparecem num anúncio de casa como capa, e a fachada de casa nunca aparece
num anúncio de apartamento — nem como segunda foto.

## Licença e procedência

Use banco de imagens com licença de uso livre (Unsplash e Pexels permitem uso comercial sem
atribuição obrigatória). Registre cada arquivo em `PROCEDENCIA.md` — o script cria o arquivo vazio
na primeira execução e nunca o sobrescreve. Acervo de demonstração sem procedência é um problema
jurídico esperando a publicação.

**Evite** foto com rosto de pessoa reconhecível e foto onde apareça placa, logotipo ou nome de
imobiliária real: a Vértice Imóveis é fictícia, e um cartaz de imobiliária de verdade numa foto do
portal passa a afirmar algo sobre uma empresa que existe.

## Como usar

```bash
python scripts/indexar_fotos.py      # normaliza, renomeia e escreve o fotos_pool.json
python scripts/gerar_imoveis.py      # redistribui as fotos pelo acervo
make seed                            # reindexa (os embeddings não dependem das fotos)
```

Pasta vazia não quebra nada: o gerador cai em URLs de um serviço de imagens de exemplo, que servem
para testar galeria e layout e não têm relação com imóvel.

Nas categorias comerciais há uma foto de cada hoje. A capa é sempre do tipo certo (galpão abre com
galpão), e a segunda foto vem de outra categoria comercial — melhor que uma galeria de uma foto só.
Acrescentar mais fotos em `sala-comercial/`, `loja/` e `galpao/` faz esse empréstimo parar sozinho.

## Onde as fotos são servidas

`GET /acervo/{categoria}/{arquivo}` na API da Mora, a partir de `SDR_FOTOS_ACERVO_DIR` (padrão:
esta pasta). O prefixo é `/acervo/` de propósito: `/fotos/` é reservado às fotos **enviadas pelo
painel**, e é por esse prefixo que o `upsert` decide a precedência painel > CRM > arquivo (ADR-0015).
