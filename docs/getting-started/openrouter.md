---
title: Usando o OpenRouter
description: Passo a passo para rodar a Mora pelo OpenRouter — chave, modelos por papel, preços, retenção zero, reserva e testes.
---

# Usando o OpenRouter

O [OpenRouter](https://openrouter.ai) dá acesso a centenas de modelos de vários fornecedores com uma
chave só. Na Mora ele pode atender qualquer um dos cinco papéis de modelo e também os embeddings. A
decisão e os trade-offs estão no [ADR-0016](../adr/0016-openrouter-e-modelo-por-funcao.md); o
funcionamento interno, em [Modelos de linguagem](../architecture/modelos.md#openrouter). Esta página é
o caminho prático.

!!! warning "Ele fica no caminho do texto do cliente"
    O OpenRouter é um intermediário: a mensagem do lead passa por ele antes de chegar ao modelo. Por
    isso toda requisição sai com **retenção zero** (`zdr: true`) e `data_collection: deny`. Não desligue
    `SDR_OPENROUTER_ZDR` fora da bancada com dataset sintético.

## 1. Criar a chave

1. Crie uma conta em <https://openrouter.ai> e adicione créditos.
2. Em **Keys**, gere uma chave (começa com `sk-or-`). Se quiser, defina um limite de gasto nela — é
   uma segunda trava além do teto de orçamento da própria Mora.

## 2. Configurar o `local/.env`

O mínimo para o OpenRouter atender os papéis de modelo:

```bash
SDR_LLM_PROVIDER=openrouter
SDR_OPENROUTER_API_KEY=sk-or-...
SDR_OPENROUTER_ZDR=true                 # padrão; deixe ligado

# Reserva DIRETO — recomendado. Se o OpenRouter cair, tudo o que passa por ele cai junto.
SDR_LLM_PROVIDER_FALLBACK=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

Sem `SDR_MODEL_*`, os papéis usam os modelos padrão (`claude-sonnet-4-5` na conversa,
`claude-haiku-4-5` no roteamento), que são traduzidos sozinhos para o ID do OpenRouter
(`anthropic/claude-sonnet-4.5`). Para outro fornecedor, nomeie o modelo de cada papel no formato
`fornecedor/modelo`:

```bash
SDR_MODEL_CONVERSA=openai/gpt-6-sol
SDR_MODEL_ROTEAMENTO=openai/gpt-oss-120b
# vazios herdam: extração → roteamento; informações e análise → conversa
# SDR_MODEL_EXTRACAO=
# SDR_MODEL_INFORMACOES=
# SDR_MODEL_ANALISE=
```

Os IDs acima são exemplos (vêm de `services/agent/evals/matriz.json`). Os válidos são os do
[catálogo do OpenRouter](https://openrouter.ai/models) — e, com a retenção zero ligada, só servem os que
têm **algum endpoint com ZDR**.

Em operação, o caminho preferido é escolher os modelos pelo painel (seção 4); as variáveis servem para
fixar um padrão sem banco ou na bancada.

### Embeddings pelo OpenRouter (opcional)

Para dispensar também a `OPENAI_API_KEY`:

```bash
SDR_EMBEDDINGS_PROVIDER=openrouter
SDR_EMBEDDINGS_MODEL=text-embedding-3-small    # vira openai/text-embedding-3-small
```

É o mesmo modelo da opção `openai`, então **não precisa reindexar** quem já indexou por ela. Trocar de
modelo (por exemplo `baai/bge-m3`) exige `make seed` e `make docs-kb` de novo. Retenção zero não existe
para embeddings no OpenRouter hoje; a requisição vai com `data_collection: deny`.

## 3. Conferir e subir

```bash
make check-env
```

O script acusa **erro** se o provedor `openrouter` estiver em uso (como primário, reserva ou
embeddings) sem `SDR_OPENROUTER_API_KEY`, e **aviso** se o ZDR estiver desligado ou se o OpenRouter for
o primário sem reserva direto. Depois suba normalmente (`make local`). Se o compose já estava no ar,
recrie os serviços para relerem o `.env`:

```bash
cd local && docker compose up -d --force-recreate agent resumidor reativador scheduler api
```

## 4. Escolher os modelos pelo painel

Em **Configurações → Modelos de IA** ([manual do painel](../user-guide/painel.md#modelos-de-ia-adr-0010-adr-0016)):

1. **Sincronize os preços primeiro.** Na caixa **Modelos do OpenRouter**, cole os IDs
   (`fornecedor/modelo`, separados por vírgula ou espaço) e clique em **Sincronizar preços**. Isso grava
   o preço publicado e faz os modelos aparecerem no combo. Sem preço, salvar é recusado — senão o custo
   seria contado como zero e o teto de orçamento pararia de valer.
2. Em cada papel, escolha o provedor **openrouter** e o modelo. Modelos `anthropic/…` e `openai/…`
   usam o preço da tabela do fornecedor e não precisam de sincronização.
3. Clique em **Testar** em cada papel: uma chamada real e curta que mostra *"Respondeu em N ms"* ou
   *"Falhou: …"*.
4. **Salvar** vale a partir do próximo turno do agente, sem reiniciar nada.

A tela avisa em **vermelho** se faltar `SDR_OPENROUTER_API_KEY` e em **amarelo** se o ZDR estiver
desligado.

A sincronização também existe na API, para scripts:

```bash
curl -s -X POST http://localhost:8000/config/modelos/openrouter/sincronizar \
  -H "Authorization: Bearer $SDR_PAINEL_TOKEN" -H "Content-Type: application/json" \
  -d '{"modelos": ["openai/gpt-6-sol", "deepseek/deepseek-v4.1-flash"]}'
# → {"gravados": {...}, "nao_encontrados": [...]}
```

No máximo 50 IDs por chamada; ID sem barra devolve 422 e nenhum preço encontrado devolve 502.

## 5. Comparar candidatos com a matriz

`make eval-matriz` roda as suítes de avaliação de cada papel com cada candidato de
`services/agent/evals/matriz.json` e imprime o resultado lado a lado. Chama modelo de verdade, então
veja o tamanho da conta antes:

```bash
make eval-matriz ARGS="--plano"                        # o que rodaria, sem chamar modelo
make eval-matriz ARGS="--papel extracao"               # só um papel
make eval-matriz ARGS="--papel conversa --modelo openai/gpt-6-sol -n 3"
```

No arquivo, ID com barra vai pelo OpenRouter; para outro provedor use
`{"modelo": "...", "provider": "anthropic"}`. A matriz roda sem reserva (falha do candidato é dado) e
recusa começar se a chave do provedor não estiver no ambiente. Com `EVAL_EM=docker`, uma chave
acrescentada depois de o container subir só aparece após
`cd local && docker compose up -d --force-recreate agent`. Mais em [Testes](../quality/testes.md).

## O que muda no comportamento

- **Roteamento do OpenRouter por papel**: `sort` por latência em roteamento e extração, por vazão em
  conversa e informações e por preço na análise.
- **Saída estruturada** (extração do cartão) só cai em endpoint que respeita o schema
  (`require_parameters`).
- **Custo** vem do `usage.cost` da resposta e vai direto para `uso_llm` — o painel de uso mostra o
  valor cobrado, não uma estimativa pela tabela.
- **Cache de prompt** em modelos `anthropic/…` e `qwen/…`, como na Anthropic direta.
- Não dá para saber qual provedor atendeu por trás do OpenRouter: a resposta não traz esse dado.

## Problemas comuns

| Sintoma | Causa provável | O que fazer |
| --- | --- | --- |
| `make check-env`: *"Provedor openrouter exige SDR_OPENROUTER_API_KEY"* | Chave ausente no `local/.env` | Preencha a chave e rode de novo. |
| Painel com aviso vermelho em Modelos | O serviço `api` não vê a chave | Recrie os containers depois de editar o `.env` (seção 3). |
| *"Falhou: … no endpoints found"* no **Testar** ou na matriz | O modelo não tem endpoint com retenção zero (ou com suporte ao schema, na extração) | Escolha outro modelo; confira na página do modelo no OpenRouter se há provedor com ZDR. |
| Salvar devolve 422 *"sem preço cadastrado"* | O preço não foi sincronizado | Use **Sincronizar preços** antes de salvar. |
| Sincronizar devolve 502 *"não devolveu preço"* | ID inexistente ou digitado errado | Copie o ID exato do catálogo (`fornecedor/modelo`). |
| 401 em toda chamada | Chave revogada ou sem crédito | Verifique a chave e o saldo em openrouter.ai. |
| OpenRouter fora do ar e o agente parado | Primário OpenRouter sem reserva | Defina `SDR_LLM_PROVIDER_FALLBACK=anthropic` (ou `openai`) com a chave correspondente. |

Outros problemas: [Troubleshooting](../quality/troubleshooting.md).
