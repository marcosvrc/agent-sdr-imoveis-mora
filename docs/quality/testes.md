---
title: Testes
description: Tipos de teste do Mora, como executar backend e front-ends, CI e o que ainda falta.
---

# Testes

## Tipos de teste

- **Backend** — testes de integração com Postgres real (pgvector) e LLM falso: grafo do agente, API,
  canais, governança e segurança. São **822** em sete suítes (contagem de `pytest --collect-only` em
  2026-10-07): `services/agent` 361, `shared` 191, `services/crm` 135, `services/api` 69,
  `services/channels/local` 12, `services/channels/telegram` 12 e `tests/` na raiz 42 (conferência
  do `.env` e a varredura de segredos de `scripts/checar_segredos.py`).
- **Front-ends** — build com TypeScript estrito (`web`, `dashboard` e `crm`).
- **Análise estática** — `ruff` no Python, `eslint` (com `react-hooks`) nos front-ends.
- **Cobertura** — combinada das sete suítes, com piso na CI.

## Executar backend

```bash
make test            # host, Python 3.12 (cria e usa os bancos sdr_test e crm_test)
make test-docker     # as mesmas sete suítes, dentro do container do agente
```

O `make test` começa pelo `make test-db`, que cria os bancos de teste se faltarem e aplica os dois
schemas. Por padrão ele faz isso **pelo Postgres do compose** (`docker compose exec db`), então o
compose precisa estar no ar — ao menos `cd local && docker compose up -d db`. As variáveis que mudam
isso, passadas na linha do `make`:

| Variável | Padrão | Para quê |
| --- | --- | --- |
| `PREPARO_DB` | `compose` | `psql` cria os bancos com o `psql` do host, direto no servidor do `TEST_DSN` (é o caminho da CI). |
| `TEST_DSN` | `postgresql://sdr:sdr@localhost:5433/sdr_test` | Banco de teste da Mora (a porta segue `DB_HOST_PORT`). |
| `CRM_TEST_DSN` | `postgresql://sdr:sdr@localhost:5433/crm_test` | Banco de teste do CRM. |

!!! warning "Trava de segurança"
    As suítes da Mora usam o **`sdr_test`** e a do CRM o **`crm_test`**: elas apagam tabelas e uma
    trava recusa rodar contra um banco sem "test" no nome (`SDR_TEST_ALLOW_WIPE=1` ignora a trava). A suíte roda em Python 3.12 sem avisos
    de depreciação.

## Análise estática e cobertura

```bash
make lint            # ruff em todo o Python (régua e justificativas em ruff.toml)
make cobertura       # roda as sete suítes medindo cobertura; falha abaixo do piso (.coveragerc)
```

`make cobertura` substitui `make test` quando se quer o número — são as mesmas suítes. O piso é
**75%** (o estado atual é ~81%): existe para uma queda brusca aparecer, não para virar corrida por
porcentagem. O `coverage.xml` fica como artefato do job na CI.

A régua do `ruff` foi escolhida para pegar **erro**, não para impor estilo: cada regra desligada tem o
motivo escrito ao lado dela em `ruff.toml`.

## Front-ends

```bash
cd apps/web && npm run build
cd apps/dashboard && npm run build
cd apps/crm && npm run build
npm run a11y         # (apps/web) verificação de acessibilidade

# lint: as dependências ficam fora do package.json (o container `web` do compose roda
# `npm install` a cada subida da demo). Instale sob demanda:
npm i --no-save --legacy-peer-deps eslint@9 typescript-eslint@8 @eslint/js eslint-plugin-react-hooks@5 globals
npm run lint
```

## Harness de avaliação (opcional, fora do CI)

Mede o **modelo** (chama a API de verdade), enquanto `make test` mede o encanamento com LLM falso.
Fica fora do CI de propósito — custa dinheiro e varia entre execuções.

```bash
make eval                # avaliação real (gasta token)
make eval-fake           # valida o harness sem gastar token
make eval-rag            # só o RAG institucional, com o embedder real
make eval-recomendacao   # só a recomendação de imóveis, com o embedder real
make eval-matriz ARGS="--plano"   # candidatos por papel: o que rodaria e quantas chamadas faria
make eval-matriz ARGS="--papel extracao -n 3"   # compara os candidatos de um papel
```

Oito suítes, nenhuma com juiz-LLM: `extracao` (um turno, com a pergunta anterior da Mora como
contexto), `coerencia` (o cartão depois de uma conversa inteira), `roteamento` (14 casos decididos
pelo modelo), `adversarial`, `rag`, `recomendacao` (o que a busca devolve respeita o que o cliente
pediu), `informacoes` (a resposta sobre política fica presa ao documento, sem número fora do trecho)
e `analise` (o briefing do corretor sai inteiro).

**Matriz de candidatos** (`make eval-matriz`, ADR-0016): compara os modelos listados em
`services/agent/evals/matriz.json` papel a papel, cada candidato num processo próprio, sem reserva e
sem degradação por orçamento, juntando qualidade, custo, latência, chamadas com erro e quem de fato
atendeu. `EVAL_EM=docker` roda o harness dentro do container do agente quando a máquina não tem as
dependências — vale para os alvos `eval*`, menos o `make eval-embeddings`, que roda sempre no host
(precisa do Ollama e da `OPENAI_API_KEY` no ambiente, e deixa o índice com o provedor da última
passada: rode `make docs-kb` depois). Os resultados ficam em `services/agent/evals/resultados/`, **fora do git**. Detalhe de cada uma em
[`services/agent/evals/README.md`](https://github.com/marcosvrc/agent-sdr-imoveis-mora/blob/master/services/agent/evals/README.md).

## Integração contínua

O workflow [`.github/workflows/ci.yml`](https://github.com/marcosvrc/agent-sdr-imoveis-mora/blob/master/.github/workflows/ci.yml)
roda dois jobs a cada push / pull request:

| Job | Passos |
| --- | --- |
| `python` | `make lint` (ruff) → `make tipos` (pyright básico) → `make cobertura` (pytest com pgvector + piso de cobertura) → `make eval-fake` (harness com dublês) → conferência do `openapi.json` |
| `frontend` | `npm ci && npm run build` (TypeScript estrito) → eslint, em matriz para `web`, `dashboard` e `crm` |
| `seguranca` | `scripts/checar_segredos.py --desde HEAD` (arquivos de credencial e padrões de chave na árvore; sem `.env` na CI, a parte dos valores reais é pulada) → `pip-audit` sobre as dependências que a imagem instala (`local/dependencias.py`, num venv limpo) → `npm audit --omit=dev --audit-level=high` nos três apps |

O workflow roda com `permissions: contents: read` e `concurrency` por ramo (um push novo cancela a
rodada anterior do mesmo ramo); pip e npm usam o cache do `setup-python`/`setup-node`, chaveado
pelos `pyproject.toml` e pelos `package-lock.json`.

Antes de empurrar, `make segredos` roda a mesma varredura com o seu `local/.env`: procura no
histórico os valores das variáveis com nome de segredo (`KEY`, `TOKEN`, `SECRET`, `PASSWORD`…, e DSN
com senha que não seja a de desenvolvimento). Nome de modelo e URL pública não entram.

Havia um terceiro job, de infraestrutura (`cdk synth`); saiu com as stacks em nuvem.

O estático roda **antes** dos testes: um nome indefinido ou import quebrado aparece em segundos, sem
esperar o banco subir.

## O que ainda falta

- **Formatação automática** (`ruff format` / Prettier): fora de propósito. O código tem alinhamento e
  comentários posicionados à mão que um formatador desmancharia; o ganho não paga o diff.
- **Teste de front-end de comportamento** (Testing Library / Playwright): hoje o front é coberto por
  build estrito, lint e verificação de acessibilidade, não por teste de interação.
