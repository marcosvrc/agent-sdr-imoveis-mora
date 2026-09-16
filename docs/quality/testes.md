---
title: Testes
description: Tipos de teste do Mora, como executar backend e front-ends, CI e o que ainda falta.
---

# Testes

## Tipos de teste

- **Backend** — testes de integração com Postgres real (pgvector) e LLM falso: grafo do agente, API,
  canais, governança e segurança.
- **Front-ends** — build com TypeScript estrito (`web` e `dashboard`).
- **Infraestrutura** — `cdk synth`.
- **Análise estática** — `ruff` no Python, `eslint` (com `react-hooks`) nos front-ends.
- **Cobertura** — combinada das sete suítes, com piso na CI.

## Executar backend

```bash
make test            # host, Python 3.12 (cria e usa o banco sdr_test)
make test-docker     # dentro do container do agente
```

!!! warning "Trava de segurança"
    Ambos usam o banco **`sdr_test`**: as suítes apagam tabelas e uma trava recusa rodar contra um banco
    sem "test" no nome (`SDR_TEST_ALLOW_WIPE=1` ignora a trava). A suíte roda em Python 3.12 sem avisos
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
make eval            # avaliação real (gasta token)
make eval-fake       # valida o harness sem gastar token
```

## Integração contínua

O workflow [`.github/workflows/ci.yml`](https://github.com/marcosvrc/agent-sdr-imoveis-mora/blob/master/.github/workflows/ci.yml)
roda três jobs a cada push / pull request:

| Job | Passos |
| --- | --- |
| `python` | `make lint` (ruff) → `make cobertura` (pytest com pgvector + piso de cobertura) → conferência do `openapi.json` |
| `frontend` | `npm ci && npm run build` (TypeScript estrito) → `npm run lint` (eslint) para `web` e `dashboard` |
| `infra` | `cdk synth` |

O estático roda **antes** dos testes: um nome indefinido ou import quebrado aparece em segundos, sem
esperar o banco subir.

## O que ainda falta

- **Formatação automática** (`ruff format` / Prettier): fora de propósito. O código tem alinhamento e
  comentários posicionados à mão que um formatador desmancharia; o ganho não paga o diff.
- **Teste de front-end de comportamento** (Testing Library / Playwright): hoje o front é coberto por
  build estrito, lint e verificação de acessibilidade, não por teste de interação.
