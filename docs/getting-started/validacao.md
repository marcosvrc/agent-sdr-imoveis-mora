---
title: Validando a instalação
description: Health checks e chamadas rápidas para confirmar que o Mora subiu corretamente.
---

# Validando a instalação

## Health checks

```bash
curl -s http://localhost:8000/health      # {"ok": true, "agente": "Mora", ...}
```

- A API responde `GET /health` com `503` quando degradada.
- Os canais respondem `GET /health` em `http://localhost:8001` com `503` se o Redis cair.

## Catálogo

```bash
curl -s "http://localhost:8000/imoveis?limite=3"
```

Se vier vazio, rode `make seed` para popular o catálogo.

## Interfaces

- Site: <http://localhost:5173>
- Painel: <http://localhost:5174> (token `dev-token` no local, quando `SDR_PAINEL_TOKEN` está vazio)
- OpenAPI interativo: <http://localhost:8000/docs>

## Testes de backend

```bash
make lint            # análise estática (ruff)
make test            # host, Python 3.12 (cria e usa o banco sdr_test)
make test-docker     # dentro do container do agente
make eval-fake       # valida o harness de avaliação com dublês, sem gastar token
```

!!! note "O que `make eval-fake` mede"
    O encanamento do harness, não a qualidade: o LLM é falso e o embedder é de trigramas. Os
    números de RAG só significam algo em `make eval-rag`, com o `bge-m3` de verdade
    (exige `make ollama-pull`).

!!! warning "Trava de segurança dos testes"
    As suítes apagam tabelas e uma trava recusa rodar contra um banco sem "test" no nome. Use sempre o
    banco `sdr_test`. Em último caso, `SDR_TEST_ALLOW_WIPE=1` ignora a trava.

Problemas na subida? Veja [Troubleshooting](../quality/troubleshooting.md).
