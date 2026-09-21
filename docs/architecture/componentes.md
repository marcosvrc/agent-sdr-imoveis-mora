---
title: Componentes
description: O que é, por que existe assim e como funciona por dentro cada componente da arquitetura do Mora — banco, fila, RAG, ponte MCP com o CRM, agentes, canais, APIs, scheduler e observabilidade — com os limites conhecidos de cada um.
---

# Componentes da arquitetura

Cada componente vive na sua pasta, com dependências e testes independentes, e conversa com os
outros apenas pelos contratos de `shared/sdr_shared` (modelos, `messaging`, `ports`, repositórios).
Todos os serviços Python compartilham uma imagem (`local/Dockerfile.python`); o que muda entre
containers é o comando, como mostra `local/docker-compose.yml`.

Este documento descreve cada componente por dentro. Tudo o que está aqui foi conferido no código;
onde o código e uma página antiga do portal divergem, **o código manda**, e a divergência está
apontada.

| Componente | Onde está | Serviço(s) no compose |
|---|---|---|
| Banco (Postgres + pgvector) | `shared/sdr_shared/db/`, `services/crm/sdr_crm/db/` | `db`, `db-init` |
| Fila (Redis Streams) | `shared/sdr_shared/adapters/local/broker.py` | `redis` |
| RAG | `shared/sdr_shared/db/repositories.py`, `services/agent/src/agent/tools/`, `services/ingestion/` | `agent` (execução pontual), `ollama` (perfil) |
| Ponte MCP com o CRM | `services/crm/sdr_crm/mcp/`, `shared/sdr_shared/ports/crm.py`, `shared/sdr_shared/crm/` | `crm-mcp`, `crm-mcp-stdio` (perfil `mcp`) |
| Agentes (LangGraph) | `services/agent/src/agent/` | `agent`, `resumidor`, `reativador` |
| Canais | `services/channels/local/`, `services/channels/telegram/` | `channels`, `telegram-in`, `telegram-out` |
| APIs e fronts | `services/api/`, `services/crm/sdr_crm/api/`, `apps/*` | `api`, `crm-api`, `web`, `dashboard`, `crm-web` |
| Scheduler | `services/scheduler/sdr_scheduler/local_worker.py` | `scheduler` |
| Observabilidade leve | `shared/sdr_shared/db/monitoramento.py` | (sem processo próprio) |

![Tópicos do Redis, produtores e consumidores](../assets/diagramas/mensageria-claro.svg#only-light)
![Tópicos do Redis, produtores e consumidores](../assets/diagramas/mensageria-escuro.svg#only-dark)

## Banco de dados (Postgres + pgvector)

**O que é.** Um container `pgvector/pgvector:pg16` (`db` em `local/docker-compose.yml`, publicado
só no loopback do host em `127.0.0.1:5433`) que hospeda **dois bancos separados**: `sdr`, da Mora,
e `crm`, do CRM da imobiliária. Há um terceiro, `langfuse`, criado por `local/00-langfuse.sql`
para o perfil opcional `observability`.

**Por que dois bancos e não dois schemas.** A regra de integração é "fluxo num sentido só": a Mora
escreve no CRM pela ponte MCP e nada do CRM toca o banco da Mora (`docs/decisions.md`, D-01/D-02).
Banco separado torna a regra verificável — uma consulta cruzada precisaria de outra conexão, e o
`crm-api` recebe um ambiente próprio (`CRM_DATABASE_DSN: postgresql://sdr:sdr@db:5432/crm`) sem
herdar o DSN da Mora. O ADR-0004 ("um Postgres para tudo") continua válido no sentido de *uma
instância*; o texto dele fala em banco único porque antecede o CRM.

### Banco da Mora (`shared/sdr_shared/db/schema.sql`)

| Tabela | Papel |
|---|---|
| `leads` | A oportunidade: `estagio`, `temperatura`, `score`, `cartao` (JSONB, o cartão de qualificação), `corretor_id`, `resumo`, `analise`, `aceita_reativacao`, `reativado_em`, `encerrado_em`, `sucessora_id`, `cliente_id`. |
| `clientes` | A pessoa (uma por telefone/e-mail, índices únicos parciais); um cliente pode ter vários leads ao longo do tempo. |
| `canais` | `(canal, identificador) → lead_id`; permite o mesmo lead ter web e Telegram com um único histórico. |
| `mensagens` | Transcrição da conversa: `direcao` ∈ `in`/`out`/`corretor`, `meta` JSONB. O `id` desta linha vira o `external_event_id` no CRM (D-13). |
| `imoveis` | Acervo indexado: campos estruturados + `fotos` JSONB + `embedding vector(1024)`; índice HNSW por cosseno e índice em `(operacao, regiao, quartos, preco)`. |
| `documentos` | Base institucional em **trechos** (`arquivo`, `assunto`, `titulo`, `trecho`, `ordem`, `embedding vector(1024)`) mais a coluna gerada `busca tsvector` com índice GIN. |
| `visitas` | Visita/reunião agendada pela Mora: `inicio`, `duracao_min`, `corretor_id`, `evento_externo_id` (Google). |
| `corretores` | Equipe: `regioes`, `ativo`, `foto`, `crm_user_id` (quem é a pessoa dentro do CRM), tokens do Google Calendar. |
| `interesses` | N:N fraco lead × imóvel com `situacao` (`sugerido`, `interessado`, `descartado`, `visita_marcada`) e `origem`. |
| `eventos_navegacao` | Cliques do site por `session_id` (`viewed_imovel`, `filtered`, `clicked_telegram`); pré-preenchem o cartão. |
| `followups_agendados` | Um agendamento one-shot por lead (`lead_id` é PK), lido pelo scheduler. |
| `notificacoes` | Sino do corretor, com índice único `(tipo, lead_id, dados->>'chave')` para não repetir o mesmo aviso. |
| `configuracoes` | Chave → JSON editável pelo painel. As chaves `modelos` (`db/modelos.py`) e `operacao` (`db/operacao.py`: `llm_timeout_s`, `acervo_refresh_s`, transcrição) vivem aqui. |
| `uso_llm` | Uma linha por chamada de modelo: tokens (inclusive cache), `custo_usd`, `latencia_ms`, `erro`, `no`, `papel`, `provider`. |
| `auditoria` | Rastro de ações (`ator_tipo` ∈ `corretor`/`agente`/`sistema`, `acao`, `entidade`, `dados`). |
| `turnos`, `saude`, `batimentos` | Observabilidade leve (ADR-0011), ver a seção própria. |
| `crm_vinculo` | Para onde este lead foi publicado: `crm_lead_id`, `crm_opportunity_id`, `crm_version` (o próximo `If-Match`). |
| `crm_pendencias` | Turnos que não conseguiram ser publicados no CRM (`chave` única, `turno` JSONB, `tentativas`, `proxima_em`, `ultimo_erro`). |
| `crm_reconhecimento` | Marca de "já procurei este lead no CRM" por hash do contato (`shared/sdr_shared/crm/reconhecimento.py`: busca por e-mail/telefone, nunca por nome; só preenche campo vazio do cartão). |

O schema também cria chaves estrangeiras `ON DELETE SET NULL` de `leads`, `visitas` e
`notificacoes` para `corretores` (bloco `DO $$ ... $$` no fim do arquivo), depois de limpar
referências órfãs.

### Banco do CRM (`services/crm/sdr_crm/db/schema.sql`)

Convenções distintas das da Mora, de propósito: UUID, `timestamptz`, dinheiro em centavos,
`version` nos agregados mutáveis (vira ETag/`If-Match`) e nenhum `ON DELETE CASCADE` no histórico
comercial. Tabelas: `users`, `service_credentials`, `sessions`, `leads`, `opportunities`,
`preferences`, `properties`, `property_photos`, `property_interests`, `interactions`,
`availability_slots` (com `EXCLUDE USING gist` sobre `[início, fim)`), `visits` (índice único
parcial que reserva o slot só em `confirmed`/`completed`), `tasks`, `handoffs`, `audit_events`
(somente append) e `idempotency_records`. `properties.code` é a chave que liga os dois acervos
(`SP-0001` nos dois lados, D-01b).

**Checkpointer do LangGraph.** A memória conversacional do grafo é o `PostgresSaver` de
`langgraph.checkpoint.postgres`, construído em `services/agent/src/agent/graph.py::build_checkpointer`
com `thread_id = lead_id`. Ele abre uma conexão própria (`Connection.connect(..., autocommit=True,
prepare_threshold=0)`) fora do pool e chama `saver.setup()`, que cria as tabelas do próprio
LangGraph no banco `sdr` — elas não estão no `schema.sql`. O que é durável entre conversas (nome,
contato, intenção, orçamento) vive em `leads.cartao`, não no checkpoint
(`services/agent/src/agent/memory/__init__.py`).

**Pool por processo.** `shared/sdr_shared/db/connection.py::get_pool` cria um `ConnectionPool`
(psycopg 3) com `min_size=1`, `max_size=get_settings().db_pool_max`, `row_factory=dict_row` e
`autocommit=True`. O padrão é `4` (`SDR_DB_POOL_MAX`, em `shared/sdr_shared/config/settings.py`); o
compose sobe a `api` para `12` porque ela atende painel, site e canal ao mesmo tempo. Cada processo
tem o seu pool, e a soma é o que conta contra o `max_connections` do Postgres. O pool do CRM
(`services/crm/sdr_crm/db/connection.py`) é diferente de propósito: `autocommit=False`, `max_size=8`,
porque idempotência e auditoria precisam entrar na mesma transação da mutação (D-04).

**Como o schema é aplicado (regra de migração).** O container `db-init` roda a cada
`docker compose up`, depois de `db` ficar saudável e antes de qualquer serviço Python, e aplica em
ordem `local/00-crm.sql`, `local/00-langfuse.sql`, o `schema.sql` da Mora no banco `sdr` e o do CRM
no banco `crm`, com `psql -v ON_ERROR_STOP=1`. Isso substitui a dependência do
`docker-entrypoint-initdb.d`, que o Postgres só executa em volume novo (a página
[Dados e persistência](dados.md) ainda descreve `make migrate` como o caminho; o alvo existe no
`Makefile`, mas o compose já faz isso sozinho). Duas consequências práticas, registradas em
`docs/decisions.md` (D-19) e nos comentários dos dois schemas:

- `docker compose restart` **não** roda o `db-init`; mudança de schema exige `up`;
- `CREATE TABLE IF NOT EXISTS` **não acrescenta coluna** em tabela que já existe. Coluna nova entra
  por `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, que é por isso que o `schema.sql` da Mora tem
  dezenas de `ALTER` depois dos `CREATE`.

**Limites conhecidos.** Não há histórico de migrações versionadas (D-03): o `schema.sql` idempotente
basta enquanto o dado é sintético e recriável. O checkpointer usa uma conexão fora do pool, então
não é contado por `SDR_DB_POOL_MAX`.

## Fila e cache (Redis)

**O que é.** Um `redis:7-alpine` (`redis` no compose, `127.0.0.1:6380` no host) usado como
**barramento entre canais e agente**, com Redis Streams e locks. Implementação única em
`shared/sdr_shared/adapters/local/broker.py` (`RedisBroker`), atrás da porta
`shared/sdr_shared/ports/broker.py` (`publish(topic, body, key)` e `consume(topic, handler)`).

**Por que uma fila.** Um turno do agente leva dezenas de segundos e não cabe no fio de uma requisição
HTTP; a fila desacopla quem recebe a mensagem de quem a responde e permite retomar o que ficou
pendente quando um worker cai.

**O Redis não é cache de dados de negócio.** Nada de lead, imóvel, configuração ou histórico é
lido do Redis; tudo isso vem do Postgres. Os caches que existem no código são em memória de
processo com validade curta (`db/operacao.py`, `db/modelos.py`, `db/governanca.py::estado_do_orcamento`),
e o limite de vazão por lead também é em memória (`services/agent/src/agent/guardrails/vazao.py`).

**Streams e consumer groups.** `publish` faz `XADD` em `sdr:<topico>` com `maxlen=10_000`; `consume`
cria (se preciso) o grupo `<topico>-workers` com `mkstream=True` e lê com `XREADGROUP ... >` de uma
mensagem por vez (`count=1`, `block=5_000` ms; `SOCKET_TIMEOUT_S` é sempre maior que o block). Tópicos
em uso, conforme os `publish`/`consume` do código:

| Tópico (stream `sdr:<tópico>`) | Quem publica | Quem consome |
|---|---|---|
| `inbound` | `services/channels/local/app.py`, `canal_telegram/inbound.py`, scheduler (follow-up vencido), `agent/reativador.py` | `agent.handler.local_worker` |
| `outbound-web` | `agent/dispatch.py::despachar`, `api/routers/handoff.py` | `services/channels/local/app.py` (lifespan) |
| `outbound-telegram` | idem | `canal_telegram/outbound.py` |
| `resumir` | `agent/dispatch.py::publicar_eventos`, `api/routers/leads.py` | `agent/eventos.py` (serviço `resumidor`) |
| `imovel-novo` | `agent/reativador.py::publicar_imovel_novo` (chamado pela ingestão) | `agent/reativador.py` (serviço `reativador`) |
| `events` | `agent/dispatch.py::publicar_eventos` (`lead.stage_changed`) | consumidor não localizado no código |

O `docs/ARCHITECTURE.md` chama esse último tópico de `sdr-events`; o nome real da chave é
`sdr:events`, e hoje ninguém o lê.

**Lock por lead.** Cada mensagem é processada dentro de `redis.lock("sdr:lock:<key>")`, com `key`
= `lead_id`. A validade do lock não é fixa: `_lock_s()` chama
`sdr_shared.ports.factory.orcamento_do_turno_s()`, que é `espera × (1 + MAX_RETRIES) × 2 + 30`
segundos (timeout do LLM, uma tentativa extra, dois provedores no pior caso, folga para banco e
embeddings). Com o padrão `SDR_LLM_TIMEOUT_S=45.0` e `MAX_RETRIES = 1` isso dá 210 s; se o cálculo
falhar, o lock cai em `240.0`. O comentário do código registra o defeito que motivou a mudança: 180 s
fixos expiravam com o turno em curso e a mensagem seguinte do mesmo lead entrava em paralelo.

**Confirmação e falha.** `_processar` sempre faz `XACK` — reprocessar repetiria o erro. Quando o
handler estoura, o broker chama `ao_falhar(body, erro)` se o serviço passou um; o agente usa isso
para responder ao cliente e encaminhar ao corretor em vez de deixá-lo esperando.

**Retomada no boot.** `_retomar_pendentes` roda antes do laço principal, em duas passadas: a PEL
deste consumidor (`XREADGROUP` com id `0`), e depois `XAUTOCLAIM` do que estiver parado há mais que
um turno inteiro (`min_idle_time = _lock_s() × 1000`) em nome de qualquer consumidor. Entradas já
apagadas pelo `maxlen` (dados `None`) são apenas confirmadas. Sem isso, a mensagem que chegou no
instante da queda ficava pendente para sempre.

**`profundidade()`.** Soma `lag` + `pending` do grupo por stream via `XINFO GROUPS`; `XLEN` não
serve porque conta o histórico retido pelo `maxlen`, não o que espera. O scheduler grava esse
dicionário na tabela `saude` a cada ciclo. O canal web usa `ping()` no `/health`, e o handler do
agente faz um `ping` antes de começar o turno — sem barramento não há como entregar a resposta.

**Follow-ups não ficam no Redis.** `PostgresScheduler` (`shared/sdr_shared/adapters/local/scheduler.py`)
grava em `followups_agendados` com `INSERT ... ON CONFLICT (lead_id) DO UPDATE`; `cancel` apaga a
linha; `vencidos()` faz `DELETE ... WHERE disparar_em <= now() RETURNING`. O scheduler republica o
payload (uma `MensagemNormalizada` do tipo `FOLLOWUP`) no tópico `inbound`.

**Limites conhecidos.** Consumidor único por processo (`consumer = "w1"`) e `count=1`: a ordem por
lead vem do lock, não do stream. O tópico `events` é publicado sem leitor.

## RAG (imóveis e base institucional)

**O que é.** Busca vetorial direta no Postgres com pgvector (ADR-0001), em dois acervos: o catálogo
de imóveis (`imoveis.embedding`) e a base institucional em trechos (`documentos.embedding`). Não há
serviço de busca separado.

**Embeddings.** `shared/sdr_shared/ports/factory.py::get_embedder` resolve
`SDR_EMBEDDINGS_PROVIDER`: `ollama` (padrão) instancia `OllamaEmbedder`
(`shared/sdr_shared/adapters/local/embeddings.py`, modelo `SDR_OLLAMA_EMBEDDING_MODEL=bge-m3`, um
`httpx.Client` persistente por processo, timeout 60 s); `openai` instancia `OpenAIEmbedder`
(`shared/sdr_shared/adapters/hospedados/embeddings.py`, modelo `SDR_EMBEDDINGS_MODEL=text-embedding-3-small`,
chave em `OPENAI_API_KEY` sem prefixo). Os dois entregam **1024 dimensões**
(`SDR_EMBEDDINGS_DIMENSOES=1024`), porque é o que `vector(1024)` exige; provedor desconhecido levanta
em vez de cair num padrão, e trocar de modelo obriga a reindexar tudo. A página
[Dados e persistência](dados.md) ainda fala em "provedor único"; o código tem dois.

**Busca híbrida de imóveis.** `ImovelRepository.buscar_hibrido` (`shared/sdr_shared/db/repositories.py`)
aplica filtros SQL — `operacao`, `regiao`, `bairros = ANY(...)`, `preco <= preco_max * 1.15`,
`quartos >=` — e ordena por `embedding <=> vetor` (cosseno), exigindo `embedding IS NOT NULL`.
`buscar_por_filtros` é a mesma consulta sem vetor, ordenada por `preco ASC`, e não exige embedding.

**Cascata por localidade.** `services/agent/src/agent/tools/buscar_imoveis.py::buscar_com_contexto`
resolve o que o cliente disse com `sdr_shared.geo` e desce: (1) bairro pedido → (2) vizinhos →
(3) região (a do local resolvido vence a do cartão) → (4) cidade inteira → `vazio`. O resultado
carrega `nivel`, `ampliou` e `alternativa_no_bairro` (o que existe no bairro pedido relaxando
quartos e depois preço), para o agente dizer a verdade sobre onde achou. Cidade fora de cobertura
vira `fora_de_cobertura` com sugestão de região.

**Um embedding por busca, e fallback sem embedder.** `_vetor` chama `get_embedder().embed` **uma vez**
por turno e reaproveita o vetor em toda a cascata; se o embedder falhar, devolve `None` e
`_executar` usa `buscar_por_filtros`. O resultado sai marcado com `sem_embedding`. Antes, a
exceção subia e o turno inteiro caía no handoff.

**Neutralização de texto externo.** `montar_card` passa a descrição do imóvel por
`services/agent/src/agent/util.py::neutralizar_texto_externo` (remove invisíveis, marcadores
forjados, tags e código; limita o tamanho) antes de ela entrar em qualquer prompt — é a defesa
contra injeção de segunda ordem via RAG. O nó `informacoes` faz o mesmo com os trechos institucionais.

**Base institucional.** `shared/sdr_shared/conhecimento.py` fatia Markdown por cabeçalho
(`MAX_CHARS = 1200`, `MIN_CHARS = 40`), define `PISO_SIMILARIDADE = 0.35` e reescreve perguntas
dependentes de contexto com as falas anteriores do cliente. `DocumentoRepository.buscar` faz busca
vetorial e, quando recebe `consulta`, funde com busca léxica (`tsvector` em português, `ts_rank_cd`)
por RRF (`CANDIDATOS = 20`, `RRF_K = 60`); os dois scores voltam separados para o piso continuar
sendo sobre cosseno. `services/agent/src/agent/tools/conhecimento.py::consultar` liga o léxico só
com `SDR_RAG_LEXICO=1` (`POR_PADRAO_COM_LEXICO = False`), aplica `acima_do_piso` e devolve no máximo
`LIMITE = 3` trechos — lista vazia não é erro, é "não sei, o corretor confirma". O nó
`services/agent/src/agent/nodes/informacoes.py` consome isso e cita a fonte (`titulo`).

**Ingestão e reindexação.** `services/ingestion/sdr_ingestion/ingest_imoveis.py` (`make seed`) e
`ingest_documentos.py` (`make docs-kb`) geram embeddings e fazem `upsert`. `acervo.py::carregar`
decide a fonte: com CRM configurado, o registro comercial (preço, status, quartos) vem do CRM
paginado (`PAGINA = 100`, `PAGINAS_MAX = 50`) e o arquivo `data/imoveis/imoveis.json` entra com os
dados de vitrine (região, suítes, destaque), casados pelo `code`; sem CRM, o arquivo é o acervo
inteiro. `sincronia.py::sincronizar` é a passada incremental que o scheduler roda: compara o
`texto_canonico()` indexado com o que veio do CRM, só gera vetor novo para o que mudou, grava campos
comerciais com `embedding=None` (o `COALESCE` do `upsert` preserva o vetor antigo) e purga o que saiu
do acervo **apenas** quando o CRM listou tudo. `ingest_imoveis.anunciar` publica `imovel-novo` para
o reativador, mas só quando o lote tem até `LIMITE_AVISOS_POR_LOTE = 5` imóveis novos.

**Fotos: painel > CRM > arquivo (ADR-0015).** `acervo.py::_converter` monta `fotos` com as URLs de
`property_photos` do CRM, caindo no arquivo quando o CRM não tem nenhuma; `ImovelRepository.upsert`
fala por último com um `CASE` que mantém `imoveis.fotos` quando já existe alguma foto `/fotos/...`
enviada pelo painel. A ordem é emergente e está presa por teste
([ADR-0015](../adr/0015-quem-manda-nas-fotos-do-imovel.md)).

**Limites conhecidos.** O piso de similaridade e o RRF foram calibrados num ambiente específico; a
fusão léxica está desligada por padrão porque a única medição disponível piorou o recall. Trocar de
modelo de embedding exige reindexar `imoveis` e `documentos` por inteiro; não há migração parcial.

## MCP (ponte Mora ↔ CRM)

**O que é.** O CRM (`services/crm`) é um sistema à parte, com REST própria e banco próprio. A Mora
entra nele **por MCP sobre HTTP**: o serviço `crm-mcp` (`python -m sdr_crm.mcp --http --porta 8200`)
expõe um servidor MCP que traduz cada ferramenta numa chamada à REST do CRM (`crm-api:8100`). O mesmo
servidor sobe por stdio no perfil `mcp` (`crm-mcp-stdio`), para um cliente MCP externo.

![Publicação de um turno no CRM](../assets/diagramas/crm-publicacao-claro.svg#only-light)
![Publicação de um turno no CRM](../assets/diagramas/crm-publicacao-escuro.svg#only-dark)

**Servidor MCP** (`services/crm/sdr_crm/mcp/servidor.py`, `http.py`, `cliente.py`). Usa
`mcp.server.lowlevel.Server` com `tools/list` e `tools/call` registrados à mão, para devolver erro
de negócio com `isError=true` **e** `structuredContent {ok:false, error:{code,...}}` (D-10). O
transporte HTTP é `StreamableHTTPSessionManager(stateless=True, json_response=True)`, montado em
`/mcp`, com `/saude` fora do token para o healthcheck. O servidor **recusa subir sem `CRM_MCP_TOKEN`**
(credencial que ele exige de quem conecta) e autentica-se na REST com `CRM_API_TOKEN` (credencial de
serviço da Mora), mandando `operation_id` como `Idempotency-Key` e `expected_version` como `If-Match`.
As descrições de `consultar_historico` e `buscar_imoveis` carregam o `AVISO_DADO` (conteúdo de
terceiros é dado, não instrução).

**Ferramentas expostas** (`services/crm/sdr_crm/mcp/ferramentas.py`, tabela `T`, 18 entradas):
`buscar_leads`, `consultar_lead`, `criar_lead`, `atualizar_lead`, `criar_oportunidade`,
`consultar_oportunidade`, `atualizar_preferencias`, `mover_oportunidade`, `buscar_imoveis`,
`registrar_interesse`, `registrar_interacao`, `consultar_historico`, `consultar_horarios`,
`solicitar_visita`, `consultar_visita`, `cancelar_visita`, `criar_tarefa`, `encaminhar_para_corretor`.
Toda mutação exige `operation_id` (mínimo 8 caracteres). O que **não** está no catálogo, de
propósito: confirmar visita, SQL, reset e gerência de tokens. `readOnlyHint`/`idempotentHint` são
dica para a interface, não autorização (D-11).

**Por que uma porta, e não tools no modelo.** `shared/sdr_shared/ports/crm.py` define os `Protocol`
`CRM` (`habilitado()`, `sessao()`) e `SessaoCRM` (operações no vocabulário da Mora: `garantir_lead`,
`garantir_oportunidade`, `registrar_interacao`, `atualizar_preferencias`, `mover_estagio`,
`encaminhar`, `buscar_lead_por_contato`, `imovel_por_codigo`, `listar_imoveis`, `horarios_livres`,
`solicitar_visita`, `registrar_interesse`, `consultar_historico`, entre outras). MCP existe para o
*modelo* escolher a ferramenta; o grafo da Mora não delega essa escolha — a decisão fica no código,
o MCP fica no transporte. E o agente precisa rodar sem CRM: `get_crm()` em `ports/factory.py`
devolve `CRMAusente` quando `SDR_CRM_URL` ou `SDR_CRM_TOKEN` está vazio, e a escolha é por
configuração presente, não por `SDR_PROFILE`.

**Adaptador** (`shared/sdr_shared/adapters/crm/via_mcp.py::CRMviaMCP`). `sessao()` abre **uma
conexão por turno**: um portal do anyio (`start_blocking_portal`) faz a ponte entre o cliente MCP
assíncrono (`mcp.client.streamable_http`) e o grafo síncrono, com `Authorization: Bearer <SDR_CRM_TOKEN>`
e `TIMEOUT = 10.0` s. Se a conexão falhar, `sessao()` entrega `_Inerte` — uma sessão que responde
`None` a tudo — para o chamador seguir o mesmo caminho nos dois casos. Nenhum método levanta para
cima; recusas esperadas do CRM (`HUMAN_IN_CONTROL`, `CONTACT_BLOCKED`, `FORBIDDEN`,
`QUALIFICATION_INCOMPLETE`, `INVALID_TRANSITION`) vão a `debug`. O adaptador lê `structured_content`
e `structuredContent` porque o SDK nomeia o campo de dois jeitos conforme a versão.

**Idempotência.** `_op(lead_id, acao, marca)` deriva `operation_id` de um SHA-256 do lead e do fato
(`mora-<acao>-<24 hex>`), nunca do relógio: repetir a publicação encontra o registro já gravado
(`idempotency_records` no CRM, único por `(credential_id, key)`). O `external_event_id` de cada
interação é o `id` da linha em `mensagens` (D-13), único por `(channel, external_event_id)` no CRM.

**Publicador** (`shared/sdr_shared/crm/publicador.py::publicar_turno`). Chamado pelo handler **depois**
de despachar a resposta ao cliente (D-12): garante lead e oportunidade (`crm_vinculo`), registra as
mensagens de entrada e saída, atualiza preferências, move o estágio no máximo até `qualified`
(`agendado` da Mora não vira `visit_scheduled`, D-14) e registra interesses. Nunca levanta. Quando a
publicação falha ou volta incompleta — inclusive quando a sessão era inerte — grava o turno em
`crm_pendencias`.

**Fila de pendências** (`shared/sdr_shared/crm/pendencias.py`). `registrar` faz
`INSERT ... ON CONFLICT (chave) DO UPDATE` com `chave = "<lead>:msg:<id_entrada>"`; `drenar(limite=20)`
roda no laço do scheduler, relê o lead do banco (o CRM quer o estado atual) e republica com backoff
exponencial até `BACKOFF_MAX_S = 3600`; após `MAX_TENTATIVAS = 30` a linha fica com o erro para
inspeção, em vez de sumir.

**Credencial de serviço e `exigir_humano`.** No CRM, scope não é autorização
(`services/crm/sdr_crm/api/auth.py`): a credencial de serviço tem os scopes `crm:read`,
`leads:write`, `opportunities:write`, `interactions:write`, `visits:request`, `tasks:write`,
`handoffs:write` (`make crm-token`, `services/crm/sdr_crm/credenciais.py::PADRAO`; `admin` não pode
ser emitido por essa CLI), e ainda assim `Ator.exigir_humano` recusa qualquer ação que exija sessão
de corretor ou administrador. Nas rotas (`services/crm/sdr_crm/api/routers/`): cadastrar imóvel,
mudar situação do imóvel, alterar fotos, abrir horário na agenda (`imoveis_rt.py`), confirmar/marcar
visita (`visitas_rt.py`), aceitar/resolver encaminhamento (`handoffs_rt.py`), liberar contato e
arquivar cliente (`leads_rt.py`). Por isso **a credencial de serviço nunca escreve o acervo** — e foi
essa parede que decidiu o ADR-0015.

**Limites conhecidos.** A ponte é unidirecional: nada do CRM empurra dado para a Mora; o que a Mora
sabe do CRM é o que ela mesma lê (reconhecimento, horários, acervo). O rate limit do CRM é em
memória, por instância.

## Agentes (LangGraph)

**O que é.** Um grafo `StateGraph` em `services/agent/src/agent/graph.py` sobre um estado único
(`state.py::AgentState`): supervisor na entrada e especialistas que voltam ao supervisor até um
deles produzir `resposta` ou o turno bater `MAX_SALTOS = 4` (ou repetir o mesmo nó sem mudar de
decisão). O `resumidor` é o único que vai direto para `END`. O handler
(`handler.py::processar`) é quem carrega o lead, transcreve áudio, aplica vazão e orçamento, invoca o
grafo com `thread_id = lead.id`, calcula score, persiste, despacha, publica no CRM e reagenda o
follow-up. O detalhe do fluxo, a máquina de estados do lead e a blindagem estão em
[Fluxo do agente e LLM](fluxo-agente.md).

Nós registrados em `graph.py::ESPECIALISTAS` (todos em `services/agent/src/agent/nodes/`):

- `supervisor` — roteia por regex determinística (`PEDE_HUMANO`, `PEDE_VISITA`, `INSTITUCIONAL_*`...)
  e só chama o modelo de roteamento na ambiguidade; é também onde o histórico é podado
  (`podar_historico`: acima de 40 mensagens, ficam 24);
- `qualificador`, `consultor`, `agendador` — os três que falam com o lead;
- `informacoes` — RAG institucional (não constava na versão anterior desta página);
- `recusa` — texto fixo para mensagem fora do escopo, sem chamar o LLM;
- `handoff`, `followup`, `reativador`, `resumidor`.

**Guardrails** (`services/agent/src/agent/guardrails/`): `escopo.py` (porteiro determinístico, com
dobra de homóglifos antes do julgamento), `vazao.py` (5 mensagens em 10 s e 60 por hora, por lead,
em memória) e `saida.py` (regex de vazamento de instrução, PII e formato técnico sobre o texto do
modelo). **Prompts blindados** (`prompts/__init__.py`): as chaves em `NAO_CONFIAVEIS`
(`mensagem`, `conteudo`, `texto_cliente`, `transcricao`) entram num bloco com sentinela aleatória
por chamada; `nome` e `cartao` (`DADOS_DO_CLIENTE`) entram em envelope em linha; chave faltante no
template estoura de propósito.

**Governança de LLM por papel.** `ports/factory.py::get_chat_model(papel)` monta o modelo para
`conversa`, `roteamento` ou `analise`: modelo e provedor vêm da chave `modelos` em `configuracoes`
quando o painel opinou, senão de `SDR_MODEL_CONVERSA`/`SDR_MODEL_ROTEAMENTO` e `SDR_LLM_PROVIDER`
(`anthropic` | `openai` | `ollama`; `openrouter` só para bancada). Timeout vem do painel
(`operacao.llm_timeout_s`) ou de `SDR_LLM_TIMEOUT_S`; `max_retries=MAX_RETRIES=1`, `max_tokens=600`.
Toda chamada recebe o callback `RegistradorUso` (`shared/sdr_shared/governanca/uso.py`), que grava
`uso_llm` com tokens, custo e latência, atribuídos ao nó e ao lead por `ContextVar`. O orçamento
(`shared/sdr_shared/db/governanca.py`, `LIMITES_PADRAO`) define o `modo`: `degradado` rebaixa
`conversa`/`analise` para o modelo de `roteamento`; `bloqueado` (150 % do limite, `TETO_DURO`, ou
`acao_ao_estourar=bloquear`) faz o handler encaminhar ao corretor sem chamar modelo.

**Fallback de provedor.** Com `SDR_LLM_PROVIDER_FALLBACK` (ou a reserva escolhida no painel),
`ModeloComFallback` tenta o primário e, esgotados os retries dele, repete no reserva;
`modelo_do_provedor` traduz o ID do modelo entre famílias (tabela `_EQUIVALENTE`) para o reserva
não devolver 404. O callback registra o provedor que atendeu de fato.

## Canais

**Web** (`services/channels/local/app.py`, serviço `channels`, porta `8001`). Um processo FastAPI com
`POST /sessao`, `GET /health` e `WS /ws?papel=lead|dashboard`. A sessão do widget é **emitida e
assinada pelo servidor** (`shared/sdr_shared/seguranca/sessao.py`: `session_id` aleatório + expiração
+ HMAC-SHA256, `VALIDADE_S = 12 h`; sem `SDR_SESSAO_SECRET` cada processo gera um segredo efêmero, e
as sessões caem no reinício em vez de aceitar qualquer assinatura). A conexão `papel=lead` só é
aceita se `validar(id, token)` passar, e só publica no `inbound` mensagens cujo `session_id` é o da
própria conexão (`lead_id = web_<session_id>`). A conexão `papel=dashboard` recebe o espelho de todas
as conversas e por isso exige a **credencial do painel no primeiro quadro** (`{"token": ...}`, prazo
`PRAZO_CREDENCIAL_S = 5`), nunca na URL; é somente leitura — o corretor responde pelo `/handoff` da
API. O lifespan consome `outbound-web` numa thread e faz push nas conexões abertas; respostas que
chegam com o cliente desconectado ficam em `pendentes` (deque de 20 por sessão) e são entregues na
reconexão se tiverem menos de `JANELA_PENDENTE_S = 600` s. `/health` devolve 503 se o Redis não
responder ao `ping`.

**Telegram** (`services/channels/telegram/canal_telegram/`). `inbound.py::local_worker` faz long
polling em `getUpdates` (`timeout=30`, `allowed_updates: message, callback_query`), resolve
`chat_id → lead` por `canais` (criando `tg_<chat_id>` quando é novo) e publica `MensagemNormalizada`
no `inbound`; o `offset` avança a cada update, então nada é entregue duas vezes mesmo após queda.
`outbound.py` consome `outbound-telegram` e envia pela Bot API o que `adapter.render` produz
(texto, teclado inline, cards). Sem `SDR_TELEGRAM_BOT_TOKEN` o worker de entrada não sobe e avisa.

**Transcrição de áudio.** Não acontece no canal: o Telegram deixa `telegram_file_id` no `meta`, e o
agente transcreve antes do grafo (`handler._transcrever_se_audio` →
`services/agent/src/agent/tools/transcricao.py`), baixando por `getFile` e rodando `faster-whisper`
no próprio processo (`WhisperModel(SDR_WHISPER_MODEL=small, device="cpu", compute_type="int8")`,
idioma `pt`). `SDR_TRANSCRICAO_PROVIDER` ∈ `auto` | `whisper_local` | `off`, sobreponível pelo
painel. O handler manda um recibo ("Recebi seu áudio...") antes de transcrever, e a transcrição
entra no prompt como texto não confiável. O cache do modelo é o volume `whisper` do compose.

**Limites conhecidos.** As conexões e os `pendentes` do canal web são em memória de um processo;
reiniciar o `channels` perde o que estava na deque. A reativação proativa só usa o Telegram
(`reativador.PREFERENCIA = (Canal.TELEGRAM,)`), porque o widget só existe com a aba aberta.

## APIs e painéis

**API da Mora** (`services/api/src/api/`, serviço `api`, porta `8000`, FastAPI com `/docs`, `/redoc`
e `/openapi.json`). Roteadores e etiquetas em `main.py`: `/imoveis` e `/eventos` são públicos (a
vitrine); `/leads`, `/dashboard`, `/handoff`, `/interesses`, `/reativacao` exigem corretor;
`/corretores`, `/config`, `/governanca`, `/auditoria`, `/calendario` são admin; `/clientes` e
`/notificacoes`, operação. A autenticação é um **token estático do painel** (`auth.py::corretor_atual`,
`HTTPBearer`), validado em tempo constante por `shared/sdr_shared/seguranca/painel.py`: vale
`SDR_PAINEL_TOKEN` ou, apenas com `SDR_PROFILE=local`, o `dev-token`; fora desse perfil, sem segredo,
nada entra. É a única coisa que `SDR_PROFILE` decide hoje. Há teto de corpo por `Content-Length`
(`LIMITE_CORPO = 256 KiB`; `LIMITE_CORPO_FOTO = 2_200_000` bytes no `POST /imoveis/{id}/fotos`), um
`AuditoriaMiddleware` que grava em `auditoria` tudo que muda o sistema (mapa `ROTAS` em
`auditoria_mw.py`), `GET /fotos/{imovel_id}/{nome}` servindo o disco (`SDR_FOTOS_DIR`) e `GET /health`
que devolve 503 se o banco não responder ou algum serviço estiver sem batimento. **Rate limit por
requisição não foi localizado nesta API**; o que existe é a vazão por lead no agente.

**Painel do corretor** (`apps/dashboard`, serviço `dashboard`, porta `5174`) e **site vitrine**
(`apps/web`, serviço `web`, porta `5173`): Vite em modo dev, código montado por volume, falando com
a API (`VITE_API_URL=http://localhost:8000`) e com o canal (`VITE_WS_URL=ws://localhost:8001/ws`). O
painel tem as páginas `VisaoGeral`, `Leads`, `LeadDetalhe`, `Conversas`, `Imoveis`, `Corretores`,
`Governanca`, `Configuracoes`, `Auditoria`, `Saude` (`apps/dashboard/src/pages/`).

**API do CRM** (`services/crm/sdr_crm/api/`, serviço `crm-api`, porta `8100`). Dois tipos de ator
(`api/contexto.py::_ator_do_request`): **credencial de serviço** por `Authorization: Bearer`, guardada
só como hash SHA-256 em `service_credentials` com `scopes`, expiração e revogação; e **sessão humana**
pelo cookie `crm_session` (tabela `sessions`, senha com Argon2id, papéis `admin`/`broker`/`reader`).
`conferir_limite` aplica rate limit por ator em memória (`CRM_RATE_LIMIT_POR_MINUTO=120`, resposta
429 com `Retry-After`) e o login tem teto próprio por IP e por e-mail
(`CRM_LOGIN_TENTATIVAS_POR_MINUTO=10`). Teto de corpo `CRM_CORPO_MAXIMO_BYTES = 256 KiB` (413).
Mutações rodam em `executar`, que grava `idempotency_records` e `audit_events` na mesma transação
da mudança; `/health/ready` confere banco **e** todas as tabelas listadas no próprio `schema.sql`
(D-19). Origens permitidas por padrão: `http://localhost:3000` e `http://127.0.0.1:3000`.

**Front do CRM** (`apps/crm`, serviço `crm-web`, porta `3000`): usa sessão em cookie com
`credentials: "include"` e o mesmo host da API no navegador (`VITE_CRM_API=http://localhost:8100`),
sem token de serviço no bundle (D-15). Publica a **mesma porta 3000** do Langfuse opcional; os dois
não sobem juntos.

**Portas publicadas no host** (`local/docker-compose.yml`): `db` 5433 (loopback), `redis` 6380
(loopback), `ollama` 11435 (perfil), `channels` 8001, `api` 8000, `crm-api` 8100, `crm-mcp` 8200,
`crm-web` 3000, `web` 5173, `dashboard` 5174, `langfuse` 3000 (perfil).

## Scheduler

**O que é.** Um processo único (`services/scheduler/sdr_scheduler/local_worker.py`, serviço
`scheduler`) com um laço de `time.sleep(30)`. A versão anterior desta página o descrevia só como
follow-up; hoje o laço faz quatro coisas por ciclo, nesta ordem:

1. **Follow-up**: `get_scheduler().vencidos()` apaga e devolve as linhas de `followups_agendados`
   com `disparar_em <= now()` e publica cada payload no tópico `inbound` com `key=lead_id`. A
   cadência de quem é agendado vem de `shared/sdr_shared/followup.py` e é decidida pelo agente ao
   fim de cada turno (`dispatch.reagendar_followup`); o próprio agente cancela quando o lead
   responde ou sai do fluxo.
2. **Amostra de saúde**: `broker.profundidade(TOPICOS)` para `inbound`, `outbound-web`,
   `outbound-telegram` e `resumir`, e `amostrar(filas)` grava em `saude` (com contagem de conexões
   em `pg_stat_activity`); uma vez por hora apara `saude` e `turnos` além de `RETENCAO_DIAS = 7`.
3. **Drenagem do CRM**: `pendencias.drenar()` republica o que ficou em `crm_pendencias`.
4. **Reindexação do acervo**: `sdr_ingestion.sincronia.sincronizar(ACERVO)` a cada
   `SDR_ACERVO_REFRESH_S` (padrão `900` s), sobreponível pelo painel via `operacao.acervo_refresh_s`
   (`0` desliga de verdade; vazio delega ao ambiente); sem CRM configurado a passada é ignorada.

Cada uma das três tarefas extras é best-effort e não pode derrubar o follow-up. O processo também
bate ponto em `batimentos` como `scheduler` (`iniciar_batimento`).

**Limites conhecidos.** É um processo só, sem eleição de líder; duas réplicas duplicariam a
amostra de saúde e disputariam os `DELETE ... RETURNING` (que, por serem atômicos, não duplicam o
follow-up).

## Observabilidade leve (ADR-0011)

**O que é.** Em vez de coletor, exporter e série temporal externa, três tabelas no Postgres que já
roda e uma tela no painel que já existe
([ADR-0011](../adr/0011-observabilidade-leve-no-postgres.md); o ADR-0005, com OpenTelemetry +
Grafana, foi implementado e revogado no mesmo dia). Toda escrita em
`shared/sdr_shared/db/monitoramento.py` é best-effort e engole a própria exceção — observar nunca
derruba o atendimento.

- **`turnos`** — um `INSERT` por turno com o tempo que o **cliente** esperou (`duracao_ms`), o
  `resultado` (`ok`, `vazao`, `handoff`, `orcamento`, `erro`, `barramento`, `reativacao`), o
  `estagio` e `nos` (o caminho percorrido no grafo, coletado por `ContextVar` em `graph.py`). O
  handler registra inclusive as saídas antecipadas, senão a taxa de falha ficaria sempre em zero.
  `uso_llm.latencia_ms` mede uma chamada de modelo isolada; `turnos` mede o turno inteiro.
- **`saude`** — uma linha a cada tique do scheduler: `filas` (profundidade por stream) e
  `conexoes_db`.
- **`batimentos`** — carimbo de vida por serviço (`servico` é PK), atualizado a cada
  `BATIMENTO_S = 30` por uma thread daemon (`iniciar_batimento`) em `agent`, `resumidor`,
  `reativador`, `telegram-in`, `telegram-out` e `scheduler`. Processo morto não reporta a própria
  morte: quem detecta é o `/health` da API lendo `servicos_parados()` (`PARADO_S = 120`).
- **`uso_llm`** — a mesma tabela da governança respondendo outra pergunta:
  `saude_dos_provedores` calcula erros e p95 por provedor.

**Tela Saúde do painel.** `GET /dashboard/saude?horas=` (`services/api/src/api/routers/dashboard.py`,
1 a 168 h) devolve `resumo_de_turnos` (total, p50, p95, pior, taxa de falha, turnos acima de 30 s,
série por hora), `ultima_amostra`, `batimentos`, `recorte_de_turnos` por canal e por estágio,
`nos_dos_turnos_lentos` (presença de cada nó nos 5 % mais lentos — mede presença, não duração, e
o código avisa isso), `serie_de_amostras` (máximo por balde, não média) e `saude_dos_provedores`.
A página `apps/dashboard/src/pages/Saude.tsx` consome isso (`lib/api.ts::saude`).

**Logs.** `shared/sdr_shared/log.py::configurar` é chamado por cada serviço e carrega
`lead_id`/`canal` como contexto (`contexto`/`limpar_contexto` no handler). O Langfuse
(`--profile observability`) é opcional, para tracing de prompt, e não faz parte do caminho padrão.

**Limites conhecidos.** Retenção de 7 dias em `turnos` e `saude`; não há duração por nó (só o
caminho); a amostra de fila depende do scheduler estar vivo — que é justamente o que `batimentos`
cobre.

## Onde continuar

- [Fluxo do agente e LLM](fluxo-agente.md) — roteamento, blindagem, máquina de estados.
- [Dados e persistência](dados.md) — RAG e ingestão em mais detalhe.
- [Diagramas](diagramas.md) — topologia do compose e sequências.
- [Decisões arquiteturais](decisoes.md) e [Decisões do CRM](../decisions.md) — os porquês.
- [Observabilidade](../quality/observabilidade.md) e [Segurança](../quality/seguranca.md).
