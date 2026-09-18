-- Banco do CRM imobiliário (especificação `crm-imobiliario-especificacao.md`, seção 5).
--
-- Este schema vive num banco SEPARADO do da Mora (`crm`, não `sdr`). A separação é o que sustenta a
-- regra de fluxo num sentido só: a Mora escreve aqui pela API, e nada daqui escreve no banco dela.
-- Compartilhar o banco faria a primeira consulta cruzada parecer inofensiva — e a partir dali não
-- haveria mais como dizer quem é dono de um lead.
--
-- Convenções da seção 5, sem exceção:
--   • identificadores UUID;
--   • timestamps SEMPRE timestamptz (UTC no banco, America/Sao_Paulo só na exibição);
--   • dinheiro em CENTAVOS inteiros — float em preço acumula erro que ninguém consegue explicar
--     depois para um cliente;
--   • `version` nos agregados mutáveis: é o valor que vira ETag e volta como If-Match;
--   • nada de ON DELETE CASCADE no histórico comercial. Apagar um lead não pode apagar a prova do
--     que foi combinado com ele.
--
-- O arquivo é idempotente (IF NOT EXISTS em tudo): rodar de novo num banco populado não derruba
-- nada. É o mesmo contrato do schema.sql da Mora, e o que permite o alvo `migrate` ser repetível.

CREATE EXTENSION IF NOT EXISTS pgcrypto;    -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS btree_gist;  -- EXCLUDE combinando igualdade (corretor) com intervalo

-- ============================================================================
-- Identidades
-- ============================================================================

CREATE TABLE IF NOT EXISTS users (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name          text NOT NULL CHECK (length(btrim(name)) > 0),
    email         text NOT NULL,
    password_hash text,                        -- nulo = identidade sem login (ex.: importada)
    role          text NOT NULL CHECK (role IN ('admin', 'broker', 'reader')),
    active        boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    version       integer NOT NULL DEFAULT 1
);
-- E-mail é a chave de login: unicidade sobre a forma normalizada, não sobre o que foi digitado.
CREATE UNIQUE INDEX IF NOT EXISTS users_email_uk ON users (lower(btrim(email)));

CREATE TABLE IF NOT EXISTS service_credentials (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name       text NOT NULL,
    token_hash text NOT NULL UNIQUE,           -- só o hash: o segredo aparece uma única vez, na criação
    scopes     text[] NOT NULL DEFAULT '{}',
    expires_at timestamptz,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sessions (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid NOT NULL REFERENCES users (id),
    token_hash text NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS sessions_user_idx ON sessions (user_id);

-- ============================================================================
-- Clientes e oportunidades
-- ============================================================================

CREATE TABLE IF NOT EXISTS leads (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name                text NOT NULL CHECK (length(btrim(name)) > 0),
    email               text,
    phone_e164          text CHECK (phone_e164 IS NULL OR phone_e164 ~ '^\+[1-9][0-9]{7,14}$'),
    external_contact_id text,
    source              text NOT NULL,
    -- `unknown` é o estado inicial e NÃO significa autorização: a seção 6 proíbe inferir permissão
    -- de contato da mera existência de um cadastro.
    contact_policy      text NOT NULL DEFAULT 'unknown'
                        CHECK (contact_policy IN ('unknown', 'allowed', 'blocked')),
    synthetic           boolean NOT NULL DEFAULT true,
    dataset_id          text,                  -- marca do lote de seed; nulo = criado em uso normal
    archived_at         timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    version             integer NOT NULL DEFAULT 1,
    -- Criar exige pelo menos um identificador: nome não identifica pessoa (seção 5), e sem nenhum
    -- deles a deduplicação não tem em que se apoiar — cada conversa viraria um lead novo.
    CONSTRAINT leads_identificador_ck CHECK (
        email IS NOT NULL OR phone_e164 IS NOT NULL OR external_contact_id IS NOT NULL)
);
-- Índices únicos PARCIAIS: só valem onde o dado existe. Um UNIQUE comum deixaria passar o primeiro
-- nulo e barrar o segundo em alguns bancos; aqui a intenção fica explícita.
CREATE UNIQUE INDEX IF NOT EXISTS leads_email_uk ON leads (lower(btrim(email)))
    WHERE email IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS leads_phone_uk ON leads (phone_e164)
    WHERE phone_e164 IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS leads_external_uk ON leads (source, external_contact_id)
    WHERE external_contact_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS leads_criado_idx ON leads (created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS opportunities (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id     uuid NOT NULL REFERENCES leads (id),
    owner_id    uuid REFERENCES users (id),
    purpose     text NOT NULL CHECK (purpose IN ('rent', 'buy')),
    stage       text NOT NULL DEFAULT 'new'
                CHECK (stage IN ('new', 'in_service', 'qualified', 'visit_scheduled',
                                 'negotiation', 'won', 'lost')),
    -- Quem está conduzindo: `human_pending` é o encaminhamento aberto, `human` é o corretor que
    -- assumiu. Nos dois, o agente registra mensagem recebida e nada mais (seção 6).
    atendimento text NOT NULL DEFAULT 'agent'
                CHECK (atendimento IN ('agent', 'human_pending', 'human')),
    lost_reason text,
    closed_at   timestamptz,
    dataset_id  text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    version     integer NOT NULL DEFAULT 1,
    -- Perder exige motivo; ganhar, não. A assimetria é de propósito: "por que não fechou" é a única
    -- informação que o funil não consegue reconstruir sozinha depois.
    CONSTRAINT opportunities_perda_ck CHECK (stage <> 'lost' OR lost_reason IS NOT NULL),
    CONSTRAINT opportunities_fechamento_ck CHECK (
        (stage IN ('won', 'lost')) = (closed_at IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS opportunities_lead_idx ON opportunities (lead_id);
CREATE INDEX IF NOT EXISTS opportunities_stage_idx ON opportunities (stage);
CREATE INDEX IF NOT EXISTS opportunities_criado_idx ON opportunities (created_at DESC, id DESC);

-- 1:1 com a oportunidade, e não com o lead: a seção 5 é explícita em que a mesma pessoa pode
-- comprar e alugar ao mesmo tempo, com exigências diferentes. Preferência pendurada no lead
-- obrigaria as duas intenções a concordarem sobre orçamento.
CREATE TABLE IF NOT EXISTS preferences (
    opportunity_id    uuid PRIMARY KEY REFERENCES opportunities (id),
    city              text,
    neighborhoods     text[] NOT NULL DEFAULT '{}',
    property_types    text[] NOT NULL DEFAULT '{}',
    budget_min_cents  bigint CHECK (budget_min_cents IS NULL OR budget_min_cents >= 0),
    budget_max_cents  bigint CHECK (budget_max_cents IS NULL OR budget_max_cents >= 0),
    -- `monthly_total` só faz sentido em aluguel; a validação de coerência com o propósito da
    -- oportunidade fica na aplicação, que enxerga as duas tabelas.
    budget_basis      text NOT NULL DEFAULT 'base_price'
                      CHECK (budget_basis IN ('base_price', 'monthly_total')),
    bedrooms_min      integer CHECK (bedrooms_min IS NULL OR bedrooms_min >= 0),
    parking_min       integer CHECK (parking_min IS NULL OR parking_min >= 0),
    move_by           date,
    requirements      text[] NOT NULL DEFAULT '{}',
    updated_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT preferences_orcamento_ck CHECK (
        budget_min_cents IS NULL OR budget_max_cents IS NULL
        OR budget_min_cents <= budget_max_cents)
);

-- ============================================================================
-- Catálogo
-- ============================================================================

CREATE TABLE IF NOT EXISTS properties (
    id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code                     text NOT NULL UNIQUE,
    title                    text NOT NULL,
    description              text,
    city                     text NOT NULL,
    neighborhood             text NOT NULL,
    type                     text NOT NULL,
    purpose                  text NOT NULL CHECK (purpose IN ('rent', 'buy')),
    base_price_cents         bigint NOT NULL CHECK (base_price_cents >= 0),
    -- Cada custo mensal é separado e pode ser NULO. Nulo significa DESCONHECIDO, nunca zero: a
    -- seção 6 exige que o total saia marcado como incompleto em vez de mentir um número menor.
    condo_monthly_cents      bigint CHECK (condo_monthly_cents IS NULL OR condo_monthly_cents >= 0),
    property_tax_monthly_cents bigint CHECK (property_tax_monthly_cents IS NULL OR property_tax_monthly_cents >= 0),
    other_monthly_cents      bigint CHECK (other_monthly_cents IS NULL OR other_monthly_cents >= 0),
    bedrooms                 integer NOT NULL CHECK (bedrooms >= 0),
    parking                  integer NOT NULL CHECK (parking >= 0),
    area_m2                  numeric(10, 2) CHECK (area_m2 IS NULL OR area_m2 > 0),
    status                   text NOT NULL DEFAULT 'available'
                             CHECK (status IN ('available', 'reserved', 'unavailable')),
    synthetic                boolean NOT NULL DEFAULT true,
    dataset_id               text,
    created_at               timestamptz NOT NULL DEFAULT now(),
    updated_at               timestamptz NOT NULL DEFAULT now(),
    version                  integer NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS properties_busca_idx ON properties (purpose, city, status);
CREATE INDEX IF NOT EXISTS properties_criado_idx ON properties (created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS property_interests (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    opportunity_id uuid NOT NULL REFERENCES opportunities (id),
    property_id    uuid NOT NULL REFERENCES properties (id),
    status         text NOT NULL CHECK (status IN ('presented', 'interested', 'rejected')),
    notes          text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (opportunity_id, property_id)
);

-- ============================================================================
-- Histórico
-- ============================================================================

CREATE TABLE IF NOT EXISTS interactions (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id           uuid NOT NULL REFERENCES leads (id),
    opportunity_id    uuid REFERENCES opportunities (id),
    channel           text NOT NULL,
    direction         text NOT NULL CHECK (direction IN ('inbound', 'outbound', 'internal')),
    summary           text NOT NULL CHECK (length(summary) <= 4000),
    external_event_id text,
    occurred_at       timestamptz NOT NULL,
    actor_type        text NOT NULL DEFAULT 'service' CHECK (actor_type IN ('user', 'service')),
    actor_id          uuid,
    dataset_id        text,
    created_at        timestamptz NOT NULL DEFAULT now()
);
-- A especificação pede "único por source"; a entidade não tem coluna `source`, e quem cumpre esse
-- papel é o canal — o mesmo id de evento pode existir no Telegram e no chat do site sem ser a
-- mesma mensagem. Registrado em docs/decisions.md.
CREATE UNIQUE INDEX IF NOT EXISTS interactions_evento_uk ON interactions (channel, external_event_id)
    WHERE external_event_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS interactions_lead_idx ON interactions (lead_id, occurred_at DESC, id DESC);

-- ============================================================================
-- Agenda e visitas
-- ============================================================================

CREATE TABLE IF NOT EXISTS availability_slots (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id uuid NOT NULL REFERENCES properties (id),
    broker_id   uuid NOT NULL REFERENCES users (id),
    starts_at   timestamptz NOT NULL,
    ends_at     timestamptz NOT NULL,
    dataset_id  text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT availability_intervalo_ck CHECK (starts_at < ends_at),
    -- Intervalo semiaberto [início, fim): 14h–15h e 15h–16h NÃO se sobrepõem. Com '[]' o banco
    -- recusaria a agenda cheia de qualquer corretor, hora após hora.
    CONSTRAINT availability_sem_sobreposicao EXCLUDE USING gist (
        broker_id WITH =, tstzrange(starts_at, ends_at, '[)') WITH &&)
);
CREATE INDEX IF NOT EXISTS availability_imovel_idx ON availability_slots (property_id, starts_at);

CREATE TABLE IF NOT EXISTS visits (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    opportunity_id      uuid NOT NULL REFERENCES opportunities (id),
    property_id         uuid NOT NULL REFERENCES properties (id),
    slot_id             uuid NOT NULL REFERENCES availability_slots (id),
    status              text NOT NULL DEFAULT 'requested'
                        CHECK (status IN ('requested', 'confirmed', 'completed', 'cancelled', 'no_show')),
    notes               text,
    cancellation_reason text,
    dataset_id          text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    version             integer NOT NULL DEFAULT 1
);
-- A regra que o teste de concorrência da seção 14 persegue: solicitar NÃO reserva, confirmar sim, e
-- duas confirmações no mesmo horário não podem coexistir. Deixar isso só na aplicação significa
-- perder a corrida entre o SELECT e o UPDATE de duas transações simultâneas — o banco é o único
-- lugar onde a garantia é real.
CREATE UNIQUE INDEX IF NOT EXISTS visits_slot_confirmado_uk ON visits (slot_id)
    WHERE status IN ('confirmed', 'completed');
CREATE INDEX IF NOT EXISTS visits_oportunidade_idx ON visits (opportunity_id);

-- ============================================================================
-- Trabalho do corretor
-- ============================================================================

CREATE TABLE IF NOT EXISTS tasks (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    opportunity_id uuid NOT NULL REFERENCES opportunities (id),
    assignee_id    uuid REFERENCES users (id),
    title          text NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
    due_at         timestamptz,
    status         text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done', 'cancelled')),
    kind           text NOT NULL CHECK (kind IN ('follow_up', 'internal')),
    dataset_id     text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    version        integer NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS tasks_oportunidade_idx ON tasks (opportunity_id);
CREATE INDEX IF NOT EXISTS tasks_vencidas_idx ON tasks (due_at) WHERE status = 'open';

CREATE TABLE IF NOT EXISTS handoffs (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    opportunity_id uuid NOT NULL REFERENCES opportunities (id),
    reason         text NOT NULL,
    summary        text NOT NULL,
    assignee_id    uuid REFERENCES users (id),
    status         text NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending', 'accepted', 'resolved')),
    dataset_id     text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    version        integer NOT NULL DEFAULT 1
);
-- "Um único Handoff pendente por oportunidade" (seção 6). Sem isto, duas mensagens seguidas de
-- "quero falar com um humano" criam duas filas para o mesmo atendimento.
CREATE UNIQUE INDEX IF NOT EXISTS handoffs_aberto_uk ON handoffs (opportunity_id)
    WHERE status IN ('pending', 'accepted');

-- ============================================================================
-- Auditoria e idempotência
-- ============================================================================

-- Somente append. Não há UPDATE nem DELETE nesta tabela em lugar nenhum do código: auditoria que
-- pode ser corrigida depois não serve para responder "quem mudou isto".
CREATE TABLE IF NOT EXISTS audit_events (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_type  text NOT NULL CHECK (actor_type IN ('user', 'service', 'system')),
    actor_id    uuid,
    actor_name  text,
    action      text NOT NULL,
    entity_type text NOT NULL,
    entity_id   uuid,
    request_id  uuid,
    changes_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS audit_entidade_idx ON audit_events (entity_type, entity_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS audit_ocorrido_idx ON audit_events (occurred_at DESC, id DESC);

-- Gravado na MESMA transação da mutação (seção 7). Gravar depois abriria a janela em que a
-- operação aconteceu e o registro de idempotência não existe — que é exatamente o instante em que
-- o cliente repete a chamada por timeout.
CREATE TABLE IF NOT EXISTS idempotency_records (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    credential_id   uuid,
    key             text NOT NULL,
    method          text NOT NULL,
    route           text NOT NULL,
    body_hash       text NOT NULL,
    response_status integer NOT NULL,
    response_body   jsonb NOT NULL,
    expires_at      timestamptz NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);
-- coalesce porque a credencial pode ser nula (sessão humana): o índice precisa de um valor para
-- comparar, e NULL nunca é igual a NULL.
CREATE UNIQUE INDEX IF NOT EXISTS idempotency_uk
    ON idempotency_records (coalesce(credential_id, '00000000-0000-0000-0000-000000000000'::uuid), key);
