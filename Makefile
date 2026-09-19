SERVICES = shared services/agent services/channels/whatsapp services/channels/web services/api services/scheduler services/ingestion

setup:
	for s in $(SERVICES); do (cd $$s && uv sync --all-extras 2>/dev/null || pip install -e .); done
	cd apps/web && npm install; cd ../dashboard && npm install
	cd infra && pip install -r requirements.txt

check-env:
	python3 scripts/check_env.py

local: check-env
	cd local && docker compose up --build

local-ollama: check-env
	cd local && docker compose --profile ollama up --build

seed:
	cd local && docker compose exec agent python /app/scripts/gerar_imoveis.py 200
	cd local && docker compose exec -w /app/services/ingestion agent python -m sdr_ingestion.ingest_imoveis /app/data/imoveis/imoveis.json

# Documentos institucionais (FAQ, política de visita, taxas) → base que a Mora consulta.
# Com BUCKET, sobe para o S3 e dispara o job da Knowledge Base. SEM BUCKET (perfil local) indexa
# no pgvector, na tabela `documentos` — exige `make migrate` e `make ollama-pull` antes, porque
# gera embeddings de verdade. Para só conferir a pasta sem indexar nada, use `make docs-secos`.
docs-kb:
	cd services/ingestion && python3 -m sdr_ingestion.ingest_documentos ../../data/documentos $(BUCKET) $(KB_ID) $(DS_ID)

docs-secos:    # lista o que seria indexado, sem tocar no banco nem gerar embedding
	cd services/ingestion && python3 -m sdr_ingestion.ingest_documentos ../../data/documentos --seco

migrate:       # (re)aplica o schema no Postgres do compose — idempotente (CREATE/ALTER ... IF NOT EXISTS)
	cd local && docker compose exec -T db psql -q -U sdr -d sdr -v ON_ERROR_STOP=1 < ../shared/sdr_shared/db/schema.sql

# ============================== CRM imobiliário (docs/decisions.md D-01) ==============================
# Sistema à parte, com banco próprio. A Mora publica nele o que a conversa descobre; nada daqui
# escreve no banco dela.

crm-migrate:   # cria o banco `crm` se não existir e aplica o schema — idempotente, como o da Mora
               # Criar aqui, e não só em `local/00-crm.sql`: aquele arquivo é script de inicialização
               # do Postgres, e o Postgres só roda esses scripts quando o VOLUME é novo. Num volume
               # que já existia antes de o CRM entrar no projeto, ele nunca rodou — e o erro que
               # aparecia era `FATAL: database "crm" does not exist`, sem nada dizendo por quê.
	cd local && printf '%s\n' "SELECT 'CREATE DATABASE crm' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'crm')\\gexec" \
	  | docker compose exec -T db psql -q -U sdr -d postgres
	cd local && docker compose exec -T db psql -q -U sdr -d crm -v ON_ERROR_STOP=1 < ../services/crm/sdr_crm/db/schema.sql

crm-seed:      # massa sintética determinística: mesmos parâmetros, mesmo dataset e mesmos IDs
	cd local && docker compose exec -w /app/services/crm crm-api python -m sdr_crm.seed --seed 42 --reference-date $(CRM_REF)

crm-reset:     # apaga o dataset e reaplica. Recusa se houver qualquer registro sem marca sintética.
	cd local && docker compose exec -w /app/services/crm crm-api python -m sdr_crm.seed --reset --confirm-reset --seed 42 --reference-date $(CRM_REF)

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
	export SDR_DATABASE_DSN=$(TEST_DSN); cd services/channels/whatsapp && PYTHONPATH=../../../shared:. python3 -m pytest -q tests
	export CRM_DATABASE_DSN=$(CRM_TEST_DSN); cd services/crm && PYTHONPATH=. python3 -m pytest -q tests
	export SDR_DATABASE_DSN=$(TEST_DSN); cd services/channels/telegram && PYTHONPATH=../../../shared:. python3 -m pytest -q tests
	export SDR_DATABASE_DSN=$(TEST_DSN); cd services/channels/local && PYTHONPATH=../../../shared:.:../whatsapp python3 -m pytest -q tests

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
	cd services/channels/whatsapp && PYTHONPATH=../../../shared:. coverage run -m pytest -q tests; cd ../../..; \
	cd services/channels/telegram && PYTHONPATH=../../../shared:. coverage run -m pytest -q tests; cd ../../..; \
	cd services/channels/local && PYTHONPATH=../../../shared:.:../whatsapp coverage run -m pytest -q tests; cd ../../..; \
	export CRM_DATABASE_DSN=$(CRM_TEST_DSN); cd services/crm && PYTHONPATH=. coverage run -m pytest -q tests; cd ../..; \
	coverage combine -q && coverage report && coverage xml -o coverage.xml

# Harness de avaliação: mede o MODELO (chama a API de verdade), enquanto `test` mede o encanamento
# com LLM falso. Fora do CI de propósito — custa dinheiro e varia entre execuções. Ver services/agent/evals/README.md
eval: test-db
	export SDR_DATABASE_DSN=$(TEST_DSN); cd services/agent && PYTHONPATH=../../shared:src:. python3 -m evals $(ARGS)

eval-fake:     # valida o HARNESS sem gastar token nem precisar do Ollama. Os números não dizem nada
               # sobre qualidade: o LLM é falso e o embedder é de trigramas. É o que roda no CI.
	export SDR_DATABASE_DSN=$(TEST_DSN); cd services/agent && PYTHONPATH=../../shared:src:. python3 -m evals --fake --limite-abstencao 80 $(ARGS)

eval-rag:      # avaliação do RAG institucional com o embedder DE VERDADE (exige `make ollama-pull`).
               # É o único jeito de saber se a busca institucional responde bem, e não só se responde.
	export SDR_DATABASE_DSN=$(TEST_DSN); cd services/agent && PYTHONPATH=../../shared:src:. python3 -m evals --suite rag $(ARGS)

test-docker: test-db   # mesma suíte, rodando dentro do container do agente (não precisa de Python 3.12 no host)
	cd local && docker compose exec -T -e SDR_DATABASE_DSN=postgresql://sdr:sdr@db:5432/sdr_test agent sh -c '\
	  cd /app/services/agent && PYTHONPATH=/app/shared:src:. python -m pytest -q tests && \
	  cd /app/services/api && PYTHONPATH=/app/shared:src python -m pytest -q tests && \
	  cd /app/services/channels/whatsapp && PYTHONPATH=/app/shared:. python -m pytest -q tests && \
	  cd /app/services/channels/telegram && PYTHONPATH=/app/shared:. python -m pytest -q tests && \
	  cd /app/services/channels/local && PYTHONPATH=/app/shared:.:../whatsapp python -m pytest -q tests'


synth:
	cd infra && cdk synth --all --context env=dev

# As VITE_* entram no bundle no momento do BUILD, não em tempo de execução: sem as duas do Cognito
# aqui, o painel publicado cai no login de desenvolvimento (token estático) SEM AVISAR — a stack sobe
# inteira e o erro só aparece quando alguém entra sem senha. Por isso o deploy para antes.
deploy:
	@test -n "$(VITE_COGNITO_USER_POOL_ID)" && test -n "$(VITE_COGNITO_CLIENT_ID)" || \
	  { echo "ERRO: defina VITE_COGNITO_USER_POOL_ID e VITE_COGNITO_CLIENT_ID antes do deploy"; \
	    echo "      (sem elas o painel publicado aceita qualquer login — ver docs/getting-started/configuracao.md)"; \
	    echo "      para publicar mesmo assim, use: make deploy SEM_COGNITO=1"; test -n "$(SEM_COGNITO)"; }
	cd apps/web && npm run build; cd ../dashboard && npm run build
	cd infra && cdk deploy --all --context env=$(ENV) --require-approval never

openapi:       # regera docs/assets/openapi.json a partir do código da API (a CI confere se está em dia)
	python3 scripts/gerar_openapi.py

docs:          # portal de documentação em http://127.0.0.1:8000 (MkDocs Material)
	pip install -r docs-requirements.txt && mkdocs serve
