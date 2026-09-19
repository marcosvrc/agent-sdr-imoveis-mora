SERVICES = shared services/agent services/channels/telegram services/api services/scheduler services/ingestion

# Nada aqui ganha com paralelismo, e vários alvos disputam o mesmo Postgres. Sem isto, um `make -j`
# rodaria `crm-reset` antes de `crm-migrate` e a falha não apontaria para a causa.
.NOTPARALLEL:

.PHONY: ajuda preparar crm-api-pronto setup check-env local local-ollama seed docs-kb docs-secos migrate \
        crm-migrate crm-seed crm-reset crm-token crm-mcp ollama-pull cli test test-db lint \
        cobertura eval eval-fake eval-rag eval-embeddings test-docker openapi docs

# Primeiro alvo do arquivo = o que `make` sozinho executa. Ser a ajuda é deliberado: quem chega ao
# projeto digita `make` antes de ler qualquer coisa, e o que ele precisa saber é a ORDEM.
ajuda:
	@echo "Mora — SDR imobiliário. Ordem de execução a partir de um clone limpo:"
	@echo
	@echo "  1. cp -n local/.env.example local/.env   (-n NÃO sobrescreve um .env que já existe)"
	@echo "     preencha ANTHROPIC_API_KEY e CRM_MCP_TOKEN"
	@echo "  2. make check-env                     confere o .env antes de subir nada"
	@echo "  3. make local-ollama                  sobe o compose (primeiro plano; siga noutro terminal)"
	@echo "  4. make preparar                      massa do CRM (os bancos o compose já criou)"
	@echo "  5. make crm-token                     emite CRM_API_TOKEN -> cole no local/.env"
	@echo "     cd local && docker compose up -d crm-mcp agent      (releem o .env)"
	@echo "  6. make ollama-pull                   baixa o bge-m3 (demora, uma vez só)"
	@echo "  7. make seed && make docs-kb          indexa acervo e documentos institucionais"
	@echo
	@echo "Verificar:  make lint · make test · make eval-fake"
	@echo "Medir RAG:  make eval-rag  (e SDR_RAG_LEXICO=1 make eval-rag para comparar)"
	@echo "Demonstrar: site :5173 · painel da Mora :5174 · CRM :3000"
	@echo "            roteiro em docs/overview/roteiro-demonstracao.md"
	@echo
	@echo "Sem CRM a Mora roda sozinha: pule 4, 5 e a parte de CRM. Os alvos avisam."

# Tudo que precisa acontecer entre "compose no ar" e "emitir o token", na ordem das dependências.
# Existe porque essa ordem já me custou dois enganos: o schema do CRM precisa do banco `crm`, que
# precisa do Postgres no ar; e a massa precisa do schema. Cada alvo isolado é idempotente, então
# rodar este de novo não estraga nada.
preparar: migrate crm-migrate crm-api-pronto crm-reset
	@echo
	@echo "✓ bancos e massa prontos. Agora: make crm-token, cole CRM_API_TOKEN no local/.env e rode"
	@echo "  cd local && docker compose up -d crm-mcp agent"

crm-api-pronto:  # sobe o crm-api e ESPERA ficar saudável
	@# Entre `crm-migrate` e `crm-reset` há um passo que não é óbvio: quando o banco `crm` não
	@# existia, o crm-api subiu, não conseguiu conectar e ficou em laço de falha (ou saiu). Criar o
	@# banco não o traz de volta sozinho, e o `crm-reset` seguinte falharia com um erro do docker
	@# sobre container não estar rodando — que não diz nada sobre o banco.
	cd local && docker compose up -d crm-api
	@echo "aguardando o crm-api ficar saudável…"
	@cd local && for i in $$(seq 1 60); do \
	  estado=$$(docker compose ps --format '{{.Health}}' crm-api 2>/dev/null); \
	  if [ "$$estado" = "healthy" ]; then echo "✓ crm-api saudável"; exit 0; fi; \
	  sleep 2; \
	done; \
	echo "✗ crm-api não ficou saudável em 2 min. Veja: cd local && docker compose logs --tail 30 crm-api"; \
	exit 1

setup:
	for s in $(SERVICES); do (cd $$s && uv sync --all-extras 2>/dev/null || pip install -e .); done
	cd apps/web && npm install; cd ../dashboard && npm install

check-env:
	python3 scripts/check_env.py

local: check-env
	cd local && docker compose up --build

local-ollama: check-env
	cd local && docker compose --profile ollama up --build

seed:
	cd local && docker compose exec agent python /app/scripts/gerar_imoveis.py 200
	cd local && docker compose exec -w /app/services/ingestion agent python -m sdr_ingestion.ingest_imoveis /app/data/imoveis/imoveis.json
	@echo "✓ acervo indexado. Com CRM configurado ele veio de lá; sem CRM, do arquivo."

# Documentos institucionais (FAQ, política de visita, taxas) → base de conhecimento que a Mora
# consulta: fatia, gera embeddings e grava na tabela `documentos` do pgvector. Exige `make migrate`
# e `make ollama-pull` antes, porque gera embeddings de verdade. Para só conferir a pasta sem
# indexar nada, use `make docs-secos`.
#
# Roda DENTRO do container, como `make seed`. Rodava no host, e ali os padrões de conexão são
# localhost:5432 e localhost:11434 — enquanto o compose publica em 5433 e 11435. O melhor desfecho
# era falhar; o pior, numa máquina com Postgres nativo na 5432, era indexar os documentos no banco
# errado, em silêncio, e o agente nunca os ver.
docs-kb:
	cd local && docker compose exec -w /app/services/ingestion agent \
	  python -m sdr_ingestion.ingest_documentos /app/data/documentos
	@echo "✓ documentos institucionais indexados na tabela \`documentos\` — a Mora já consulta daqui."

docs-secos:    # lista o que seria indexado, sem tocar no banco nem gerar embedding
	cd local && docker compose exec -w /app/services/ingestion agent \
	  python -m sdr_ingestion.ingest_documentos /app/data/documentos --seco

migrate:       # (re)aplica o schema no Postgres do compose — idempotente (CREATE/ALTER ... IF NOT EXISTS)
	cd local && docker compose exec -T db psql -q -U sdr -d sdr -v ON_ERROR_STOP=1 < ../shared/sdr_shared/db/schema.sql
	@echo "✓ schema da Mora aplicado no banco \`sdr\` (idempotente)."

# ============================== CRM imobiliário (docs/decisions.md D-01) ==============================
# Sistema à parte, com banco próprio. A Mora publica nele o que a conversa descobre; nada daqui
# escreve no banco dela.

crm-migrate:   # aplica o schema do CRM sem reiniciar nada — idempotente, como o da Mora
               # Criar o banco deixou de ser trabalho deste alvo: quem faz isso agora é o serviço
               # `db-init` do compose, que roda antes de qualquer serviço Python subir. Enquanto era
               # passo de `make`, dependia de alguém rodá-lo ANTES do compose — e o compose sobe
               # primeiro, então o `crm-api` batia em `FATAL: database "crm" does not exist` toda
               # vez. O alvo continua aqui para aplicar uma mudança de schema com o ambiente no ar.
	cd local && printf '%s\n' "SELECT 'CREATE DATABASE crm' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'crm')\\gexec" \
	  | docker compose exec -T db psql -q -U sdr -d postgres
	cd local && docker compose exec -T db psql -q -U sdr -d crm -v ON_ERROR_STOP=1 < ../services/crm/sdr_crm/db/schema.sql
	@echo "✓ banco \`crm\` pronto e schema aplicado. Próximo: make crm-reset"

crm-seed:      # massa sintética determinística: mesmos parâmetros, mesmo dataset e mesmos IDs
	cd local && docker compose exec -w /app/services/crm crm-api python -m sdr_crm.seed --seed 42 --reference-date $(CRM_REF)

crm-reset:     # apaga o dataset e reaplica. Recusa se houver qualquer registro sem marca sintética.
	cd local && docker compose exec -w /app/services/crm crm-api python -m sdr_crm.seed --reset --confirm-reset --seed 42 --reference-date $(CRM_REF)
	@echo "✓ massa do CRM recriada (seed 42). Próximo: make crm-token"

crm-token:     # emite a credencial da Mora. O token aparece UMA vez — copie para local/.env.
	cd local && docker compose exec -w /app/services/crm crm-api python -m sdr_crm.credenciais emitir --nome mora

crm-mcp:       # servidor MCP por stdio, para um cliente MCP externo (Claude Desktop e afins).
	@echo "O servidor HTTP já sobe com o compose — é por ele que a Mora entra (crm-mcp:8200/mcp)."
	@echo "Este alvo é o transporte stdio. -T é obrigatório: sem ele o terminal se mistura ao JSON-RPC."
	cd local && docker compose run --rm -T crm-mcp-stdio

CRM_REF ?= 2026-09-17T12:00:00Z

ollama-pull:   # garante o serviço (profile ollama) de pé antes de baixar o modelo de embeddings
	cd local && docker compose --profile ollama up -d ollama && docker compose --profile ollama exec ollama ollama pull bge-m3

cli: check-env
	cd services/agent && SDR_PROFILE=local python cli.py

# Testes de integração: usam o banco sdr_test (separado do de desenvolvimento) no Postgres do compose.
# As suítes apagam tabelas — por isso há uma trava que recusa rodar contra um banco sem "test" no nome.
TEST_DSN ?= postgresql://sdr:sdr@localhost:$${DB_HOST_PORT:-5433}/sdr_test
# O CRM tem banco próprio também nos testes — a separação de D-01 vale na suíte.
CRM_TEST_DSN ?= postgresql://sdr:sdr@localhost:$${DB_HOST_PORT:-5433}/crm_test
# Onde o banco de teste é preparado. `compose` usa o Postgres do docker compose (padrão, na máquina
# do desenvolvedor); `psql` fala direto com o TEST_DSN — é o caminho da CI, onde o Postgres é um
# service container do runner e não existe compose nenhum para dar `exec`.
PREPARO_DB ?= compose
ADMIN_DSN = $(dir $(TEST_DSN))postgres

# `\gexec` em vez de `... | grep -q 1 || (cd local && ...)`: naquele padrão a linha inteira já
# rodou `cd local`, então o `cd local` de dentro do parêntese procurava `local/local` e o ramo de
# criação falhava com "No such file or directory". O defeito ficou latente enquanto os bancos já
# existiam — só aparecia na máquina de quem ainda não os tinha, que é exatamente quem depende dele.
test-db:       # cria os bancos de teste (se não existirem) e aplica os dois schemas
               # DOIS bancos: o CRM é sistema à parte (D-01), e a separação vale também na suíte.
               # Faltava criar o `crm_test` aqui: quem clonasse o repositório e rodasse `make test`
               # via a suíte do CRM falhar sem nenhuma pista de que o banco é que não existia.
ifeq ($(PREPARO_DB),compose)
	cd local && printf '%s\n' "SELECT 'CREATE DATABASE sdr_test' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'sdr_test')\\gexec" \
	  | docker compose exec -T db psql -q -U sdr -d postgres
	cd local && docker compose exec -T db psql -q -U sdr -d sdr_test -v ON_ERROR_STOP=1 < ../shared/sdr_shared/db/schema.sql
	cd local && printf '%s\n' "SELECT 'CREATE DATABASE crm_test' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'crm_test')\\gexec" \
	  | docker compose exec -T db psql -q -U sdr -d postgres
	cd local && docker compose exec -T db psql -q -U sdr -d crm_test -v ON_ERROR_STOP=1 < ../services/crm/sdr_crm/db/schema.sql
else
	psql "$(ADMIN_DSN)" -tc "SELECT 1 FROM pg_database WHERE datname='sdr_test'" | grep -q 1 || \
	  psql "$(ADMIN_DSN)" -c "CREATE DATABASE sdr_test"
	psql "$(TEST_DSN)" -q -v ON_ERROR_STOP=1 -f shared/sdr_shared/db/schema.sql
	psql "$(ADMIN_DSN)" -tc "SELECT 1 FROM pg_database WHERE datname='crm_test'" | grep -q 1 || \
	  psql "$(ADMIN_DSN)" -c "CREATE DATABASE crm_test"
	psql "$(CRM_TEST_DSN)" -q -v ON_ERROR_STOP=1 -f services/crm/sdr_crm/db/schema.sql
endif

test: test-db
	export SDR_DATABASE_DSN=$(TEST_DSN); \
	python3 -m pytest -q tests
	export SDR_DATABASE_DSN=$(TEST_DSN); cd shared && PYTHONPATH=. python3 -m pytest -q tests
	export SDR_DATABASE_DSN=$(TEST_DSN); cd services/agent && PYTHONPATH=../../shared:src:. python3 -m pytest -q tests
	export SDR_DATABASE_DSN=$(TEST_DSN); cd services/api && PYTHONPATH=../../shared:src python3 -m pytest -q tests
	export CRM_DATABASE_DSN=$(CRM_TEST_DSN); cd services/crm && PYTHONPATH=. python3 -m pytest -q tests
	export SDR_DATABASE_DSN=$(TEST_DSN); cd services/channels/telegram && PYTHONPATH=../../../shared:. python3 -m pytest -q tests
	export SDR_DATABASE_DSN=$(TEST_DSN); cd services/channels/local && PYTHONPATH=../../../shared:. python3 -m pytest -q tests

lint:          # análise estática do Python; a régua e os porquês estão em ruff.toml
	ruff check .

# Cobertura combinada das sete suítes. `set -e` porque as chamadas estão encadeadas num shell só:
# sem isso uma suíte quebrada seguiria em frente e o relatório sairia como se estivesse tudo bem.
cobertura: test-db
	set -e; export SDR_DATABASE_DSN=$(TEST_DSN); export COVERAGE_FILE=$(CURDIR)/.coverage; \
	export COVERAGE_RCFILE=$(CURDIR)/.coveragerc; \
	coverage erase; \
	coverage run -m pytest -q tests; \
	cd shared && PYTHONPATH=. coverage run -m pytest -q tests; cd ..; \
	cd services/agent && PYTHONPATH=../../shared:src:. coverage run -m pytest -q tests; cd ../..; \
	cd services/api && PYTHONPATH=../../shared:src coverage run -m pytest -q tests; cd ../..; \
	cd services/channels/telegram && PYTHONPATH=../../../shared:. coverage run -m pytest -q tests; cd ../../..; \
	cd services/channels/local && PYTHONPATH=../../../shared:. coverage run -m pytest -q tests; cd ../../..; \
	export CRM_DATABASE_DSN=$(CRM_TEST_DSN); cd services/crm && PYTHONPATH=. coverage run -m pytest -q tests; cd ../..; \
	coverage combine -q && coverage report && coverage xml -o coverage.xml

# Harness de avaliação: mede o MODELO (chama a API de verdade), enquanto `test` mede o encanamento
# com LLM falso. Fora do CI de propósito — custa dinheiro e varia entre execuções. Ver services/agent/evals/README.md
eval: test-db
	export SDR_DATABASE_DSN=$(TEST_DSN); cd services/agent && PYTHONPATH=../../shared:src:. python3 -m evals $(ARGS)

eval-fake:     # valida o HARNESS sem gastar token nem precisar do Ollama. Os números não dizem nada
               # sobre qualidade: o LLM é falso e o embedder é de trigramas. É o que roda no CI.
	export SDR_DATABASE_DSN=$(TEST_DSN); cd services/agent && PYTHONPATH=../../shared:src:. python3 -m evals --fake --limite-abstencao 80 $(ARGS)

eval-rag:      # avaliação do RAG institucional com o embedder DE VERDADE (o do seu local/.env).
               # É o único jeito de saber se a busca institucional responde bem, e não só se responde.
	export SDR_DATABASE_DSN=$(TEST_DSN); cd services/agent && PYTHONPATH=../../shared:src:. python3 -m evals --suite rag $(ARGS)

# Compara os DOIS provedores de embeddings no mesmo dataset, um depois do outro. Existe porque a
# pergunta "qual recupera melhor em português" não se responde por catálogo: o `bge-m3` é
# fortemente multilíngue, o `text-embedding-3-small` é mais barato e dispensa o container, e qual
# ganha no SEU corpus é medida.
#
# Cada passada REINDEXA a base institucional com o embedder da vez — é obrigatório, porque comparar
# contra um índice gerado por outro modelo compararia coisas diferentes sem avisar. No fim, o índice
# fica com o provedor do seu `.env`; se você trocar depois, rode `make docs-kb` e `make seed`.
#
# Exige as duas pontas prontas: Ollama no ar com o bge-m3 (`make ollama-pull`) e OPENAI_API_KEY no
# local/.env. O custo da passada da OpenAI é de frações de centavo.
eval-embeddings:
	@echo "───────── ollama (bge-m3)"
	@export SDR_DATABASE_DSN=$(TEST_DSN) SDR_EMBEDDINGS_PROVIDER=ollama; \
	  cd services/agent && PYTHONPATH=../../shared:src:. python3 -m evals --suite rag $(ARGS)
	@echo
	@echo "───────── openai (text-embedding-3-small, 1024 dims)"
	@export SDR_DATABASE_DSN=$(TEST_DSN) SDR_EMBEDDINGS_PROVIDER=openai; \
	  cd services/agent && PYTHONPATH=../../shared:src:. python3 -m evals --suite rag $(ARGS)
	@echo
	@echo "Compare recall@3 e abstenção. Diferença dentro do ruído: fique no mais barato (openai)."
	@echo "O índice ficou com o provedor da ÚLTIMA passada — rode 'make docs-kb' para voltar ao do .env."

test-docker: test-db   # mesma suíte, rodando dentro do container do agente (não precisa de Python 3.12 no host)
	cd local && docker compose exec -T -e SDR_DATABASE_DSN=postgresql://sdr:sdr@db:5432/sdr_test agent sh -c '\
	  cd /app/services/agent && PYTHONPATH=/app/shared:src:. python -m pytest -q tests && \
	  cd /app/services/api && PYTHONPATH=/app/shared:src python -m pytest -q tests && \
	  cd /app/services/channels/telegram && PYTHONPATH=/app/shared:. python -m pytest -q tests && \
	  cd /app/services/channels/local && PYTHONPATH=/app/shared:. python -m pytest -q tests'


openapi:       # regera docs/assets/openapi.json a partir do código da API (a CI confere se está em dia)
	python3 scripts/gerar_openapi.py

docs:          # portal de documentação em http://127.0.0.1:8000 (MkDocs Material)
	pip install -r docs-requirements.txt && mkdocs serve
