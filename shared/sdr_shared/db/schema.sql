CREATE EXTENSION IF NOT EXISTS vector;
-- busca do site: "Perdizes" tem que achar quem digitou "perdizes" (ver ImovelRepository.buscar_publico)
CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE TABLE IF NOT EXISTS leads (
  id            TEXT PRIMARY KEY,
  nome          TEXT,
  telefone      TEXT,
  estagio       TEXT NOT NULL DEFAULT 'novo',
  temperatura   TEXT NOT NULL DEFAULT 'frio',
  score         INT  NOT NULL DEFAULT 0,
  cartao        JSONB NOT NULL DEFAULT '{}',
  corretor_id   TEXT,
  resumo        TEXT,
  followups_enviados INT NOT NULL DEFAULT 0,
  criado_em     TIMESTAMPTZ NOT NULL DEFAULT now(),
  ultima_mensagem_em TIMESTAMPTZ
);

-- Um lead pode ter vários canais (web anônimo → WhatsApp) com um único histórico (ADR-0003)
CREATE TABLE IF NOT EXISTS canais (
  lead_id       TEXT REFERENCES leads(id),
  canal         TEXT NOT NULL,
  identificador TEXT NOT NULL,
  PRIMARY KEY (canal, identificador)
);

CREATE TABLE IF NOT EXISTS mensagens (
  id        BIGSERIAL PRIMARY KEY,
  lead_id   TEXT REFERENCES leads(id),
  canal     TEXT NOT NULL,
  direcao   TEXT NOT NULL,           -- in | out | corretor
  conteudo  TEXT NOT NULL,
  meta      JSONB DEFAULT '{}',
  em        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS mensagens_lead_idx ON mensagens (lead_id, em);

CREATE TABLE IF NOT EXISTS imoveis (
  id          TEXT PRIMARY KEY,
  tipo        TEXT NOT NULL,
  operacao    TEXT NOT NULL,
  cidade      TEXT NOT NULL,
  regiao      TEXT NOT NULL,
  bairro      TEXT NOT NULL,
  quartos     INT  NOT NULL,
  suites      INT  NOT NULL DEFAULT 0,
  vagas       INT  NOT NULL DEFAULT 0,
  area_m2     NUMERIC NOT NULL,
  preco       NUMERIC NOT NULL,
  condominio  NUMERIC,
  descricao   TEXT NOT NULL,
  fotos       JSONB NOT NULL DEFAULT '[]',
  destaque_investimento BOOLEAN NOT NULL DEFAULT false,
  embedding   vector(1024)
);
CREATE INDEX IF NOT EXISTS imoveis_embedding_idx ON imoveis USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS imoveis_filtro_idx ON imoveis (operacao, regiao, quartos, preco);

-- Tabela usada pela Bedrock Knowledge Base quando Aurora é o vector store (ADR-0001)
CREATE SCHEMA IF NOT EXISTS bedrock_integration;
CREATE TABLE IF NOT EXISTS bedrock_integration.bedrock_kb (
  id        UUID PRIMARY KEY,
  embedding vector(1024),
  chunks    TEXT,
  metadata  JSON
);
CREATE INDEX IF NOT EXISTS bedrock_kb_embedding_idx ON bedrock_integration.bedrock_kb USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS visitas (
  id          TEXT PRIMARY KEY,
  lead_id     TEXT REFERENCES leads(id),
  imovel_id   TEXT REFERENCES imoveis(id),
  tipo        TEXT NOT NULL,
  inicio      TIMESTAMPTZ NOT NULL,
  corretor_id TEXT,
  status      TEXT NOT NULL DEFAULT 'confirmada'
);

CREATE TABLE IF NOT EXISTS eventos_navegacao (
  id         BIGSERIAL PRIMARY KEY,
  session_id TEXT NOT NULL,
  tipo       TEXT NOT NULL,        -- viewed_imovel | filtered | clicked_telegram
  dados      JSONB NOT NULL DEFAULT '{}',
  em         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Perfil local: substitui o EventBridge Scheduler (adapters/local/scheduler.py)
CREATE TABLE IF NOT EXISTS followups_agendados (
  lead_id     TEXT PRIMARY KEY REFERENCES leads(id),
  disparar_em TIMESTAMPTZ NOT NULL,
  payload     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS followups_disparar_idx ON followups_agendados (disparar_em);

-- ===== Painel administrativo =====
ALTER TABLE visitas ADD COLUMN IF NOT EXISTS criada_em TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE TABLE IF NOT EXISTS corretores (
  id          TEXT PRIMARY KEY,
  nome        TEXT NOT NULL,
  email       TEXT,
  telefone    TEXT,
  regioes     JSONB NOT NULL DEFAULT '[]',   -- zonas que atende (roteamento de handoff/visitas)
  ativo       BOOLEAN NOT NULL DEFAULT true,
  criado_em   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Configurações do agente editáveis pelo painel (chave → JSON). Defaults ficam no código (api/routers/config.py).
CREATE TABLE IF NOT EXISTS configuracoes (
  chave         TEXT PRIMARY KEY,
  valor         JSONB NOT NULL,
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE corretores ADD COLUMN IF NOT EXISTS foto TEXT;   -- data URL (perfil local); na AWS vira chave no S3

ALTER TABLE leads ADD COLUMN IF NOT EXISTS analise JSONB;           -- AnaliseLead (sentimento/perfil), gerada pelo Resumidor
ALTER TABLE leads ADD COLUMN IF NOT EXISTS analisado_em TIMESTAMPTZ;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS analise_solicitada_em TIMESTAMPTZ;  -- pedido > analisado = worker do resumidor não respondeu

-- Governança de LLM: uma linha por chamada de modelo (tokens, custo, latência)
CREATE TABLE IF NOT EXISTS uso_llm (
  id            BIGSERIAL PRIMARY KEY,
  em            TIMESTAMPTZ NOT NULL DEFAULT now(),
  lead_id       TEXT,
  no            TEXT,                   -- nó do grafo (qualificador, consultor, resumidor...)
  papel         TEXT,                   -- conversa | roteamento | analise | embeddings
  provider      TEXT NOT NULL,
  modelo        TEXT NOT NULL,
  tokens_entrada        INT NOT NULL DEFAULT 0,
  tokens_saida          INT NOT NULL DEFAULT 0,
  tokens_cache_escrita  INT NOT NULL DEFAULT 0,
  tokens_cache_leitura  INT NOT NULL DEFAULT 0,
  custo_usd     NUMERIC(12,6) NOT NULL DEFAULT 0,
  latencia_ms   INT,
  erro          TEXT
);
CREATE INDEX IF NOT EXISTS uso_llm_em_idx ON uso_llm (em DESC);
CREATE INDEX IF NOT EXISTS uso_llm_modelo_idx ON uso_llm (modelo, em);

ALTER TABLE leads ADD COLUMN IF NOT EXISTS email TEXT;   -- informado pelo cliente na conversa (nunca inferido)

-- Auditoria: rastro de quem fez o quê no sistema e no agente
CREATE TABLE IF NOT EXISTS auditoria (
  id          BIGSERIAL PRIMARY KEY,
  em          TIMESTAMPTZ NOT NULL DEFAULT now(),
  ator_tipo   TEXT NOT NULL,            -- corretor | agente | sistema
  ator_id     TEXT,
  ator_nome   TEXT,
  acao        TEXT NOT NULL,            -- lead.handoff_assumido, corretor.criado, config.alterada...
  entidade    TEXT NOT NULL,            -- lead | corretor | imovel | configuracao | visita
  entidade_id TEXT,
  dados       JSONB NOT NULL DEFAULT '{}',   -- antes/depois ou detalhes da ação (sem segredos)
  origem      TEXT,                     -- IP / canal
  resultado   TEXT NOT NULL DEFAULT 'ok',
  detalhe     TEXT
);
CREATE INDEX IF NOT EXISTS auditoria_em_idx ON auditoria (em DESC);
CREATE INDEX IF NOT EXISTS auditoria_entidade_idx ON auditoria (entidade, entidade_id, em DESC);
CREATE INDEX IF NOT EXISTS auditoria_acao_idx ON auditoria (acao, em DESC);

-- Cliente = a PESSOA (uma por telefone/e-mail, a mesma no WhatsApp e na web).
-- Lead = a OPORTUNIDADE daquela pessoa (uma intenção, um cartão, um ciclo).
-- O mesmo cliente pode ter várias oportunidades ao longo do tempo: comprou em 2024, quer alugar em 2026.
CREATE TABLE IF NOT EXISTS clientes (
  id         TEXT PRIMARY KEY,
  nome       TEXT,
  telefone   TEXT,
  email      TEXT,
  criado_em  TIMESTAMPTZ NOT NULL DEFAULT now(),
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Índices parciais: telefone e e-mail identificam a pessoa quando existem; nulos não colidem entre si.
CREATE UNIQUE INDEX IF NOT EXISTS clientes_telefone_idx ON clientes (telefone) WHERE telefone IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS clientes_email_idx ON clientes (lower(email)) WHERE email IS NOT NULL;

ALTER TABLE leads ADD COLUMN IF NOT EXISTS cliente_id TEXT REFERENCES clientes(id);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS encerrado_em TIMESTAMPTZ;      -- oportunidade fechada: não recebe mais turnos
ALTER TABLE leads ADD COLUMN IF NOT EXISTS sucessora_id TEXT;             -- quando a intenção mudou e abrimos outra
CREATE INDEX IF NOT EXISTS leads_cliente_idx ON leads (cliente_id, criado_em DESC);

-- Aviso para o corretor. O agente promete ao cliente que "o corretor entra em contato";
-- sem isto, a promessa dependia de alguém ter o painel aberto no momento certo.
CREATE TABLE IF NOT EXISTS notificacoes (
  id BIGSERIAL PRIMARY KEY,
  corretor_id TEXT,                       -- NULL = aviso da equipe (ninguém atribuído ainda)
  tipo        TEXT NOT NULL,              -- lead.encaminhado | visita.agendada | briefing.pronto | lead.respondeu
  titulo      TEXT NOT NULL,
  detalhe     TEXT,
  lead_id     TEXT,
  dados       JSONB NOT NULL DEFAULT '{}',
  criada_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
  lida_em     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS notificacoes_corretor_idx ON notificacoes (corretor_id, lida_em, criada_em DESC);
-- Não repete o mesmo aviso do mesmo fato: reprocessar uma fila não enche o sino do corretor.
CREATE UNIQUE INDEX IF NOT EXISTS notificacoes_unicas_idx ON notificacoes (tipo, lead_id, (dados->>'chave'));

-- Calendário do corretor. Guardamos só o refresh token: é o que permite agir depois,
-- e o access token vive em memória por uma hora. Desconectar = apagar esta linha.
ALTER TABLE corretores ADD COLUMN IF NOT EXISTS calendario_refresh_token TEXT;
ALTER TABLE corretores ADD COLUMN IF NOT EXISTS calendario_conectado_em TIMESTAMPTZ;
ALTER TABLE visitas    ADD COLUMN IF NOT EXISTS evento_externo_id TEXT;   -- id do evento no Google
ALTER TABLE visitas    ADD COLUMN IF NOT EXISTS duracao_min INT NOT NULL DEFAULT 60;
CREATE INDEX IF NOT EXISTS visitas_corretor_idx ON visitas (corretor_id, inicio);

-- Observabilidade leve (ADR-0011): o banco que já roda é o armazém, o painel que já existe é a tela.
-- Sem coletor, sem exporter, sem série temporal externa — ver docs/adr/0011.
CREATE TABLE IF NOT EXISTS turnos (
  id         BIGSERIAL PRIMARY KEY,
  em         TIMESTAMPTZ NOT NULL DEFAULT now(),
  lead_id    TEXT,
  canal      TEXT NOT NULL,
  resultado  TEXT NOT NULL,          -- ok | vazao | handoff | orcamento | erro
  duracao_ms INT NOT NULL,           -- o tempo que o CLIENTE esperou, não o de uma chamada de LLM
  estagio    TEXT,
  nos        TEXT[] DEFAULT '{}'     -- caminho percorrido no grafo
);
CREATE INDEX IF NOT EXISTS turnos_em_idx ON turnos (em DESC);

-- Amostra periódica escrita pelo laço do scheduler, que já roda de 30 em 30s.
CREATE TABLE IF NOT EXISTS saude (
  id          BIGSERIAL PRIMARY KEY,
  em          TIMESTAMPTZ NOT NULL DEFAULT now(),
  filas       JSONB NOT NULL DEFAULT '{}',   -- profundidade por stream
  conexoes_db INT
);
CREATE INDEX IF NOT EXISTS saude_em_idx ON saude (em DESC);

-- Carimbo de vida por serviço. Processo morto não escreve métrica: quem detecta é OUTRO processo
-- lendo esta tabela (ver /health da api).
CREATE TABLE IF NOT EXISTS batimentos (
  servico TEXT PRIMARY KEY,
  em      TIMESTAMPTZ NOT NULL DEFAULT now(),
  detalhe JSONB NOT NULL DEFAULT '{}'
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Corretor desligado não pode deixar lead órfão.
--
-- `leads.corretor_id`, `visitas.corretor_id` e `notificacoes.corretor_id` eram TEXT solto: apagar o
-- corretor deixava as linhas apontando para um id inexistente. O lead continuava em handoff,
-- atribuído a um fantasma, e não aparecia para ninguém — some da carteira do corretor removido e
-- nunca entra na de outro.
--
-- O caminho normal é desativar (`ativo = false`) e reatribuir a carteira pela API, que avisa quem
-- recebeu. Estas chaves são a rede de segurança para o caminho anormal (um DELETE manual no psql):
-- em vez de fantasma, o lead volta para a fila da equipe, que é o estado que o sistema já entende.
-- A limpeza antes do ALTER é obrigatória: com referência órfã pendurada, a chave não é criada.
-- ─────────────────────────────────────────────────────────────────────────────
UPDATE leads        SET corretor_id = NULL WHERE corretor_id IS NOT NULL AND corretor_id NOT IN (SELECT id FROM corretores);
UPDATE visitas      SET corretor_id = NULL WHERE corretor_id IS NOT NULL AND corretor_id NOT IN (SELECT id FROM corretores);
UPDATE notificacoes SET corretor_id = NULL WHERE corretor_id IS NOT NULL AND corretor_id NOT IN (SELECT id FROM corretores);

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'leads_corretor_fk') THEN
    ALTER TABLE leads ADD CONSTRAINT leads_corretor_fk
      FOREIGN KEY (corretor_id) REFERENCES corretores(id) ON DELETE SET NULL;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'visitas_corretor_fk') THEN
    ALTER TABLE visitas ADD CONSTRAINT visitas_corretor_fk
      FOREIGN KEY (corretor_id) REFERENCES corretores(id) ON DELETE SET NULL;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'notificacoes_corretor_fk') THEN
    ALTER TABLE notificacoes ADD CONSTRAINT notificacoes_corretor_fk
      FOREIGN KEY (corretor_id) REFERENCES corretores(id) ON DELETE SET NULL;
  END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Interesse: que imóvel importa para qual lead.
--
-- Antes, esse vínculo só existia tarde (`visitas`) ou não sobrevivia à conversa (a lista de
-- sugeridos vivia no estado do grafo). Sem ele, o agente reoferece o que a pessoa já viu na semana
-- passada, o corretor não sabe quem está de olho num imóvel, e não há como avisar alguém quando
-- entra um imóvel que casa com o que ela pediu.
--
-- É N:N e FRACO de propósito: interesse não é reserva. Um imóvel bom tem vários interessados, e
-- exclusividade só existe onde já é registrada — o horário de uma visita (`visitas`).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS interesses (
  lead_id       TEXT NOT NULL REFERENCES leads(id)   ON DELETE CASCADE,
  imovel_id     TEXT NOT NULL REFERENCES imoveis(id) ON DELETE CASCADE,
  -- sugerido: o agente mostrou. interessado: a pessoa demonstrou (abriu a ficha, perguntou).
  -- descartado: disse que não serve. visita_marcada: virou compromisso.
  situacao      TEXT NOT NULL DEFAULT 'sugerido',
  origem        TEXT NOT NULL DEFAULT 'agente',      -- agente | site | corretor
  motivo        TEXT,                                -- por que combina (o texto que o agente já gera)
  criado_em     TIMESTAMPTZ NOT NULL DEFAULT now(),
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (lead_id, imovel_id)
);
CREATE INDEX IF NOT EXISTS interesses_imovel_idx ON interesses (imovel_id, situacao);
CREATE INDEX IF NOT EXISTS interesses_lead_idx   ON interesses (lead_id, atualizado_em DESC);

-- Reativação proativa (imóvel novo → leads antigos que o pediram).
--   • aceita_reativacao: opt-out. Quem pediu para não receber, não recebe — e é uma coluna, não uma
--     regra escondida em código, para o corretor poder desligar pelo painel.
--   • reativado_em: carimbo do último aviso, base da cadência (no máximo um por semana por lead).
--     Sem ele, reprocessar a fila viraria enxurrada de mensagem para a mesma pessoa.
ALTER TABLE leads ADD COLUMN IF NOT EXISTS aceita_reativacao BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS reativado_em TIMESTAMPTZ;

-- Ponte para o CRM (docs/decisions.md, D-01). A tabela fica AQUI, no banco da Mora, porque é dado
-- da Mora sobre a própria integração: quem precisa saber "para onde publiquei este lead" é quem
-- publica. Guardá-la do outro lado obrigaria o CRM a conhecer a existência da Mora.
--   • um lead da Mora vira DOIS registros no CRM: a pessoa (lead) e a intenção (opportunity);
--   • crm_version é o If-Match da próxima escrita — guardá-lo evita um GET por turno, e quando
--     envelhece (o corretor editou pelo painel) o CRM responde 412 e o publicador relê.
CREATE TABLE IF NOT EXISTS crm_vinculo (
  lead_id            TEXT PRIMARY KEY REFERENCES leads(id) ON DELETE CASCADE,
  crm_lead_id        TEXT NOT NULL,
  crm_opportunity_id TEXT NOT NULL,
  crm_version        INT  NOT NULL DEFAULT 1,
  atualizado_em      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Marca de que já procuramos este lead no CRM. Sem ela, um cliente que o CRM não conhece custaria
-- uma busca por turno, para sempre. `marca_contato` é o hash do e-mail/telefone usados: quando o
-- cliente informa um contato novo, a marca muda e vale procurar de novo — que é justamente o caso
-- do chat anônimo do site, onde o e-mail só aparece no meio da conversa.
CREATE TABLE IF NOT EXISTS crm_reconhecimento (
  lead_id        TEXT PRIMARY KEY REFERENCES leads(id) ON DELETE CASCADE,
  marca_contato  TEXT NOT NULL,
  achado         BOOLEAN NOT NULL,
  procurado_em   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Base de conhecimento institucional: como a imobiliária trabalha (taxa, documentação, prazo,
-- política de visita, financiamento). É o RAG que responde o que NÃO está no catálogo.
--
-- Um registro = um TRECHO, não um arquivo. A pergunta do cliente é específica ("preciso de fiador?")
-- e o documento inteiro como unidade traria três páginas de contexto para uma resposta de uma linha
-- — e enterraria o parágrafo certo no meio do irrelevante.
--
-- `assunto` vem da subpasta e serve de filtro grosso antes da similaridade; `titulo` é o cabeçalho
-- da seção, e é ele que vira a citação da fonte na resposta ao cliente. Responder sem poder dizer
-- de onde veio é o que separa RAG de invenção com passos extras.
CREATE TABLE IF NOT EXISTS documentos (
  id            TEXT PRIMARY KEY,           -- <arquivo>#<ordem>: estável entre reingestões
  arquivo       TEXT NOT NULL,
  assunto       TEXT NOT NULL,
  titulo        TEXT,
  trecho        TEXT NOT NULL,
  ordem         INT  NOT NULL,
  embedding     vector(1024),
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS documentos_assunto_idx ON documentos (assunto);

-- Busca léxica, ao lado da vetorial. Embedding denso erra termo EXATO — "fiador", "IPTU", "FGTS",
-- nome de bairro —, justamente as palavras em que o cliente é mais literal e em que errar é mais
-- visível. A coluna é gerada: não há como o texto e o índice divergirem, porque não existe um
-- segundo lugar para atualizar.
ALTER TABLE documentos ADD COLUMN IF NOT EXISTS busca tsvector
  GENERATED ALWAYS AS (
    to_tsvector('portuguese', coalesce(titulo, '') || ' ' || coalesce(trecho, ''))
  ) STORED;
CREATE INDEX IF NOT EXISTS documentos_busca_idx ON documentos USING gin (busca);
