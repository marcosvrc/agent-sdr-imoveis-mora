---
title: Regras de negócio
description: O que o agente, o painel, o CRM e o site decidem, com os valores exatos — a referência para escrever testes e entender o que o sistema faz.
---

# Regras de negócio

Este documento descreve **o que o sistema decide**, não como ele é construído. Cada regra vem com o
valor exato, o lugar onde vale, o arquivo que decide, o que acontece quando ela é violada e o teste
que a prende — ou a marca "sem teste", que é um convite.

!!! info "Como ler"
    - **Regra** é o enunciado verificável. Onde há número, o número é o do código, não uma
      aproximação.
    - **Vale em** diz o sistema: `agente` (Mora), `painel` (painel da Mora, `apps/dashboard`),
      `CRM` (API, MCP e painel do CRM, `services/crm` e `apps/crm`), `site` (`apps/web`),
      `API` (API da Mora, `services/api`).
    - **Fonte** aponta o arquivo que decide. Se o código e este documento discordarem, **o código
      está certo e este documento está velho** — corrija-o.
    - **Se violada** diz o efeito observável: código HTTP, texto fixo, recusa silenciosa.
    - **Teste** é o arquivo/função que quebraria. Caminhos são relativos à raiz do repositório.
    - A seção [Divergências conhecidas](#20-divergencias-conhecidas) lista pontos onde o
      comportamento surpreende, e a seção [Regras removidas ou alteradas](#21-regras-removidas-ou-alteradas)
      diz o que esta versão tirou ou mudou em relação à anterior — nada foi apagado em silêncio.

---

## 1. Vocabulário

Os dois sistemas modelam a mesma realidade com palavras diferentes, e a diferença é regra de
negócio (`shared/sdr_shared/crm/traducao.py`):

| Termo na Mora | O que é | No CRM | Regra |
| --- | --- | --- | --- |
| **Cliente** | A pessoa | `leads` | Na Mora só existe quando informa **telefone ou e-mail**. No CRM, criar exige **e-mail, telefone ou `external_contact_id`** — nome não identifica pessoa. |
| **Lead / oportunidade** | Uma intenção, um ciclo de atendimento | `opportunities` | A mesma pessoa pode ter várias. Um lead da Mora vira **dois** registros no CRM (pessoa + oportunidade). |
| **Interesse** | Vínculo lead ↔ imóvel | `property_interests` | Fraco e N:N. Um registro por par. |
| **Visita** | Compromisso datado | `visits` + `availability_slots` | A Mora **reserva** e **pede**; só uma pessoa **confirma**. |

**Mora** é a agente; **Vértice Imóveis** é a imobiliária. O corretor é humano e aparece na Mora como
cadastro com regiões e carga (`corretores`) e no CRM como `users` com papel `admin` ou `broker`. A
ponte entre os dois é `corretores.crm_user_id`.

---

## 2. Ciclo de vida do lead (Mora)

### 2.1 Os sete estágios

`novo` · `qualificando` · `qualificado` · `agendado` · `handoff` · `inativo` · `frio`
(`shared/sdr_shared/models/lead.py`)

### 2.2 Transições — quem muda o quê

| De | Para | Quando | Fonte | Teste |
| --- | --- | --- | --- | --- |
| `novo` | `qualificando` | a intenção deixa de ser indefinida | `services/agent/src/agent/nodes/qualificador.py` | `services/agent/tests/test_cenarios.py::test_cenario_compra` |
| `novo`/`qualificando` | `qualificado` | o cartão fica **completo** e o consultor apresenta imóveis | `nodes/consultor.py` | `test_cenarios.py::test_cenario_compra` |
| qualquer | `agendado` | a Mora **reservou** um horário na agenda dela (não é confirmação — ver 7) | `nodes/agendador.py` | `test_cenarios.py::test_horario_digitado` |
| qualquer | `handoff` | cliente pede humano, corretor assume, falha do agente ou orçamento bloqueado | `nodes/handoff.py`, `handler.py`, `services/api/src/api/routers/handoff.py` | `test_resiliencia.py::test_falha_do_grafo_responde_e_encaminha`, `test_governanca.py::test_degradacao_por_orcamento` |
| qualquer | `inativo` | follow-up enviado e **ainda há** tentativas | `nodes/followup.py` | `test_cenarios.py::test_cenario_followup` |
| qualquer | `frio` | follow-up enviado e era a **última** tentativa | `nodes/followup.py` | `test_followup.py::test_tentativas_esgotadas_limpam_o_agendamento` |
| `handoff` | `qualificado` ou `qualificando` | corretor devolve à Mora — `qualificado` se o cartão estiver completo | `routers/handoff.py` | `services/api/tests/test_api.py::test_corretor_auth_e_handoff` |

**Regra que surpreende:** devolver a conversa **não devolve o lead**. O `corretor_id` continua com
quem assumiu; só o estágio volta. Uma recusa por escopo **nunca** muda o estágio
(`test_seguranca.py::test_recusa_nao_muda_o_estagio_do_lead`).

### 2.3 Encerramento e sucessão

Um lead nunca é apagado. Ao mudar de intenção **depois** de um ciclo fechado, o lead antigo recebe
`encerrado_em` e `sucessora_id`, e uma nova oportunidade nasce em `qualificando`
(`shared/sdr_shared/db/clientes.py::nova_oportunidade_se_mudou_intencao`).

**Condições para abrir a sucessora** — todas precisam valer: (1) a nova intenção não é
`indefinida`; (2) é diferente da atual; (3) a atual **não** era `indefinida` (primeira definição
não é mudança); (4) o estágio está em `ENCERRAVEIS = {agendado, handoff, inativo, frio}` — mudar de
ideia durante a qualificação só ajusta o cartão; (5) o lead ainda está ativo (`encerrado_em` nulo).

A sucessora **herda** cliente, nome, telefone, e-mail e corretor, e **recomeça** o que a pessoa
procura. Os canais passam a entregar na oportunidade nova. O cartão da sucessora é extraído **só da
mensagem atual**, mais nome/telefone/e-mail informados (`nodes/qualificador.py::run`). O consultor
**não** troca a intenção ao absorver mudança de critério — só o qualificador abre sucessora
(`nodes/consultor.py::_absorver_mudanca`). Vale no agente. Testes:
`services/api/tests/test_clientes.py::test_intencao_nova_depois_do_ciclo_abre_outra_oportunidade`,
`::test_correcao_no_meio_da_qualificacao_nao_abre_oportunidade`, `::test_primeira_intencao_declarada_nao_abre_oportunidade`.

---

## 3. Qualificação

### 3.1 O cartão e os campos obrigatórios

O cartão é a fonte de verdade da qualificação (`shared/sdr_shared/models/lead.py`). **Cartão
obrigatório por intenção:**

| Intenção | Campos obrigatórios | Quantos |
| --- | --- | --- |
| compra, aluguel **e indefinida** | `intencao`, `regiao`, `preco_max`, `quartos`, `urgencia` | 5 |
| investimento | `intencao`, `perfil_investidor`, `ticket`, `retorno_esperado` | 4 |

- `completo()` = nenhum obrigatório faltando (`campos_faltantes()` testa `None` e `indefinida`).
  **Contato não entra nessa conta.**
- `tem_contato()` = telefone **ou** e-mail. **Nome não conta.**
- Campos de texto livre são limpos de caracteres de controle e cortados em **120** caracteres
  (bairros: 80 cada, no máximo **20**), porque entram no prompt sem envelope.

Teste: `services/agent/tests/test_graph_routing.py::test_cartao_compra_faltantes`,
`::test_cartao_investimento_completo`.

### 3.2 Extração — o que ela pode e não pode fazer

A extração roda no modelo de roteamento (o barato) com saída estruturada, e é **conservadora por
projeto** (`nodes/qualificador.py::_extrair`):

| Regra | Se violada | Teste |
| --- | --- | --- |
| só grava campo cujo valor extraído não seja `None`, `[]`, `False`, `indefinida` ou `0` | — | `test_cenarios.py::test_cenario_compra` |
| **nunca apaga nem zera** um campo já preenchido | — | `test_contato.py::test_contato_existente_nao_e_sobrescrito` |
| `pediu_visita` nunca volta para `False` pela extração | — | sem teste |
| falha na extração devolve o cartão **inalterado** — o turno continua | — | `test_cenarios.py::test_mudanca_nao_derruba_o_turno` |
| **uma extração por frase**: o consultor não reextrai a mensagem que o qualificador acabou de extrair (`cartao_extraido_de`) | uma chamada de modelo a mais por turno | `test_cenarios.py::test_cartao_completo_nao_extrai_a_mesma_frase_duas_vezes` |
| cliente qualificado pode **trocar de bairro/critério** no consultor; a intenção fica intacta | busca com bairros antigos | `test_cenarios.py::test_cliente_qualificado_pode_trocar_de_bairro` |

**Quem decide bairro e região é o catálogo `geo`, não o modelo** (`shared/sdr_shared/geo.py`). São
**18 bairros** em 5 regiões (zona_sul 5, zona_oeste 4, zona_norte 3, zona_leste 3, centro 3). Se o
local resolver como fora de cobertura (`FORA_DE_COBERTURA`: Osasco, Barueri, Alphaville, Guarulhos,
ABC…), `bairros` e `regiao` são **zerados** e a Mora diz isso em uma frase. Testes:
`test_geo.py::test_resolver_localidade`, `::test_local_fora_de_cobertura_nao_vira_bairro`,
`::test_desconhecido_nao_inventa`.

### 3.3 Captura de contato

| Regra | Valor | Teste |
| --- | --- | --- |
| Nome | cortado em 80 caracteres | `test_contato.py::test_contato_informado_na_conversa_vira_dado_do_lead` |
| Telefone | só dígitos, aceito **somente com 10 a 13 dígitos**; fora disso é descartado | `test_contato.py::test_telefone_invalido_nao_entra_no_cadastro` |
| E-mail | minúsculo, cortado em 120 caracteres | `test_contato.py::test_contato_informado_na_conversa_vira_dado_do_lead` |
| Só preenche o que está vazio | o já informado nunca é sobrescrito | `test_contato.py::test_contato_existente_nao_e_sobrescrito` |
| Auditoria | `lead.contato_capturado` registra **quais campos**, nunca os valores | sem teste |
| Dedup de cliente | com telefone ou e-mail na mão, o lead é vinculado ao cliente existente (telefone manda, e-mail é o segundo caminho) | `services/api/tests/test_clientes.py::test_mesmo_telefone_no_telegram_e_na_web_e_um_cliente_so` |

**Quando a Mora pede contato** (`nodes/qualificador.py::_contexto_contato`):

- canal **≠ web** → nunca pede (`test_contato.py::test_canal_externo_nunca_pede_contato`);
- canal web e sem nome → pede **só o primeiro nome** (`::test_no_web_pede_o_nome_antes_de_qualquer_contato`);
- canal web, com nome, **sem contato e com cartão completo** → pede **um** contato, de preferência
  telefone (`::test_pede_um_contato_so_quando_ha_compromisso`);
- **ao reservar uma visita sem contato**, o agendador pede o telefone na própria confirmação
  (`nodes/agendador.py::run`, `test_agendador_crm.py::test_confirmacao_nao_deixa_placeholder_no_prompt`).

### 3.4 Roteamento — regras antes do LLM, e a ordem importa

O supervisor decide por regra determinística; o modelo só entra no último caso
(`nodes/supervisor.py`). **A primeira condição que casar vence:**

| # | Condição | Destino |
| --- | --- | --- |
| 0 | já há resposta no turno, ou `saltos > 1` | encerra |
| 1 | canal `sistema` | resumidor |
| 2 | tipo `followup` | follow-up |
| 3 | tipo `reativacao` | reativador |
| 4 | `PEDE_SAIR` (não quero mais avisos…) | reativador (**antes do porteiro de escopo**) |
| 5 | fora de escopo **e** não pede humano | recusa |
| 6 | pede humano (`PEDE_HUMANO`, botão "Falar com corretor") ou já está em `handoff` | handoff |
| 7 | pergunta institucional (`INSTITUCIONAL_FORTE` ou `INSTITUCIONAL_FRACO` + marca de pergunta), **sem** `slot:` e **sem** horários oferecidos | informações (RAG institucional) |
| 8 | escolheu horário (botão `slot:` ou texto após oferta) | agendador |
| 9 | pede visita, ou `pediu_visita` no cartão **e estágio ≠ `agendado`** | agendador |
| 10 | pede outras opções | consultor |
| 11 | cartão completo e nada sugerido ainda | consultor |
| 12 | cartão incompleto | qualificador |
| 13 | resto | **modelo decide** entre qualificador, consultor, agendador, handoff e informacoes; resposta desconhecida cai em qualificador; **`agendador` com lead já `agendado` é trocado** por consultor/qualificador |

Precedências que são decisão de negócio, com o teste que as prende:

| Precedência | Teste |
| --- | --- |
| Opt-out vence o porteiro de escopo | `test_reativacao_fluxo.py::test_cliente_pede_para_nao_receber_e_a_mora_desliga_na_hora` |
| Pedir humano vence a recusa | `test_seguranca.py::test_pedido_de_humano_tem_precedencia_sobre_a_recusa`, `test_informacoes.py::test_pedido_de_humano_continua_tendo_precedencia` |
| "Vocês cobram taxa de visita?" vai para informações, não para o agendador | `test_informacoes.py::test_taxa_de_visita_nao_vira_agendamento` |
| Escolha de horário vence a pergunta institucional | `test_informacoes.py::test_escolha_de_horario_tem_precedencia` |
| Telefone enviado após a reserva não reoferece a grade | `test_graph_routing.py::test_telefone_depois_da_reserva_nao_volta_para_o_agendador` |
| Quem quer remarcar continua chegando ao agendador | `test_graph_routing.py::test_quem_quer_remarcar_continua_chegando_ao_agendador` |
| O modelo não devolve visita reservada ao agendador | `test_graph_routing.py::test_modelo_nao_devolve_visita_reservada_ao_agendador` |
| Especialista que não responde nem reencaminha roda **uma vez só** (`MAX_SALTOS = 4`, `ultimo_no`) | `test_graph_routing.py::test_especialista_que_nao_responde_nem_reencaminha_roda_uma_vez_so` |

### 3.5 Informações institucionais

`nodes/informacoes.py` responde "como a imobiliária trabalha" só com trecho recuperado acima de
`PISO_SIMILARIDADE = 0.35` (`shared/sdr_shared/conhecimento.py`), no máximo **3** trechos de até
**1200** caracteres, neutralizados como texto externo. Sem trecho, usa o prompt
`informacoes_sem_base` ("vou confirmar") e oferece "Falar com corretor"; falha na busca **não vira
invenção**. Testes: `test_informacoes.py::test_com_fonte_o_trecho_entra_no_prompt_e_a_fonte_e_citavel`,
`::test_sem_fonte_usa_o_prompt_que_nao_deixa_inventar`, `::test_falha_da_busca_nao_vira_invencao`.

---

## 4. Score e temperatura

Calculado **sem IA**, a cada turno (`services/agent/src/agent/scoring.py`). **Pesos:**

| Critério | Pontos |
| --- | --- |
| Intenção definida | +15 |
| Tem região | +10 |
| Tem `preco_max` ou `ticket` | +15 |
| Tem `quartos` ou `perfil_investidor` | +10 |
| Urgência `imediata` | +25 |
| Urgência `3_meses` | +15 |
| Urgência `6_meses` | +8 |
| Pediu visita | +15 |
| Imóveis abertos no site | +3 cada, **teto +9** |
| Respondeu em até 5 minutos (`RESPOSTA_RAPIDA`) | +5 |
| **Cada follow-up enviado** | **−10** |

Resultado limitado a 0–100. Temperatura: **quente ≥ 60**, **morno 30–59**, **frio 0–29**.

- `respondeu_rapido` mede o **cliente voltar** em até 5 minutos; é medido **antes** de carimbar a
  atividade (`handler.py`). Testes: `test_notificacoes.py::test_cliente_que_volta_logo_pontua`,
  `::test_o_sinal_entra_no_score`, `::test_o_sinal_chega_do_fluxo_real`.
- Turnos iniciados pela Mora (`INICIADAS_PELO_AGENTE`: follow-up, reativação) **nunca** pontuam por
  rapidez nem carimbam `ultima_mensagem_em`
  (`test_reativacao_fluxo.py::test_reativacao_nao_conta_como_atividade_do_cliente`).
- Não pontuam: `preco_min`, `bairros`, `tipo_imovel`, `retorno_esperado`, contato, estágio.

---

## 5. Busca de imóveis

### 5.1 Filtros aplicados sempre

| Regra | Valor | Fonte | Teste |
| --- | --- | --- | --- |
| Operação | `aluguel` se a intenção é aluguel; **`venda` para compra e investimento** | `tools/buscar_imoveis.py::_filtros` | `test_cenarios.py::test_cenario_investimento` |
| Teto de preço | `preco_max` ou `ticket`, com **tolerância de +15%** (`preco <= preco_max * 1.15`) | `shared/sdr_shared/db/repositories.py::buscar_hibrido` | sem teste |
| Quartos | filtro de **mínimo** (`>=`) | idem | sem teste |
| Resultados buscados | 6 (o consultor pede 6; a função tem padrão 5) | `nodes/consultor.py` | — |
| Imóveis apresentados | **no máximo 3** | `nodes/consultor.py` | `test_cenarios.py::test_cenario_compra` |
| Sem embedder | a busca cai para `buscar_por_filtros` (SQL puro, preço crescente) em vez de derrubar o turno | `tools/buscar_imoveis.py::_vetor` | `test_geo.py::test_sem_embedder_a_busca_cai_para_os_filtros_em_vez_de_derrubar_o_turno`, `::test_turno_inteiro_sobrevive_sem_embedder` |
| Um embedding por busca | a cascata inteira calcula **um** vetor | idem | `test_geo.py::test_a_cascata_inteira_calcula_um_embedding_so` |

### 5.2 A cascata — e o que a Mora pode afirmar

A busca desce níveis até achar algo. **O nível é a única autorização para falar de disponibilidade**
(`tools/buscar_imoveis.py::buscar_com_contexto`, `nodes/consultor.py::_contexto_da_busca`):

| Nível | Significa | O que a Mora deve dizer |
| --- | --- | --- |
| `bairro` | achou no bairro pedido | cita o bairro de cada um; **nunca** diz que não há opções |
| `vizinhos` | não há no bairro pedido; estes são de bairros vizinhos da mesma região | diz isso **antes** de apresentar; proibido inventar motivo ou sugerir que ficam no bairro pedido |
| `regiao` | não há no bairro; estes são de outros bairros da região | explícito — salvo quando o cliente pediu a região, e aí é mensagem positiva |
| `cidade` | não há nem na região | diz com honestidade e pergunta se a região é flexível |
| `fora_de_cobertura` | a cidade não é atendida | uma frase dizendo que atendemos São Paulo capital; apresenta a região sugerida mais próxima; **não inventa que há imóveis lá** |
| `vazio` | nada em lugar nenhum | **único caso** em que pode afirmar indisponibilidade ampla; propõe flexibilizar **um** critério |

**Vizinho** = outro bairro da mesma região (`test_geo.py::test_vizinhos_sao_da_mesma_regiao`,
`::test_cascata_do_bairro_ate_a_cidade`, `test_cenarios.py::test_busca_respeita_o_bairro_pedido`).

### 5.3 Alternativa no bairro

Sem nada no perfil pedido **dentro do bairro pedido**, o sistema procura o que existe ali fora do
perfil (`tools/buscar_imoveis.py::_alternativa`): só com bairro pedido; duas tentativas, parando na
primeira com resultado — relaxa **quartos**, depois **preço**; busca 3, o prompt recebe **2**. Sem teste.

### 5.4 O que impede repetir

| Regra | Efeito | Teste |
| --- | --- | --- |
| Imóvel `descartado` | **nunca** reaparece, em nenhuma sessão | `test_cenarios.py::test_imovel_descartado_nao_volta_a_ser_oferecido` |
| Imóvel já `sugerido` | não repete, mesmo em sessão futura | `test_cenarios.py::test_o_que_o_agente_mostra_vira_interesse_registrado` |
| Esgotou a novidade | repete as 3 melhores — mas nunca um descartado | sem teste |

A memória entre sessões é a tabela `interesses`; o estado do grafo só conhece a conversa atual.

### 5.5 O catálogo que a Mora oferece é o do CRM

| Regra | Vale em | Fonte | Se violada | Teste |
| --- | --- | --- | --- | --- |
| Com CRM configurado, o índice da Mora só recebe imóveis `available` — `GET /v1/properties` filtra por `available` por padrão e a ferramenta MCP não expõe outro status | agente | `services/ingestion/sdr_ingestion/acervo.py` | imóvel vendido seguiria sendo oferecido | `shared/tests/test_acervo_do_crm.py::test_vendido_fica_fora_do_indice` |
| **Imóvel fora do catálogo deixa de ser oferecido**: a sincronização roda a cada **900 s** (`SDR_ACERVO_REFRESH_S`, ajustável no painel; mínimo 60 s, `0` desliga) e purga o que o CRM não lista mais | agente | `services/scheduler/sdr_scheduler/local_worker.py`, `sdr_ingestion/sincronia.py` | — | `test_acervo_do_crm.py::test_purga_tira_do_indice_o_que_saiu_do_acervo`, `::test_preco_mudado_no_crm_chega_ao_indice` |
| **A purga recusa lista vazia** (`ValueError`) e só roda com fonte autoritativa (CRM listou o acervo inteiro); leitura parcial levanta antes | agente | `repositories.py::apagar_fora_de`, `acervo.py::_do_crm` | esvaziaria o catálogo por falha de leitura | `test_acervo_do_crm.py::test_purga_recusa_lista_vazia`, `::test_sem_crm_a_sincronia_nao_faz_nada` |
| Só o que mudou gera embedding novo (texto canônico comparado) | agente | `sincronia.py` | custo de embedding a cada 15 min | `test_acervo_do_crm.py::test_segunda_passada_nao_gera_embedding_nenhum` |
| Região do imóvel que só existe no CRM é deduzida do bairro (`geo`) | agente | `acervo.py::_regiao` | — | `test_acervo_do_crm.py::test_imovel_so_do_crm_deduz_a_regiao_do_bairro` |
| **Fotos: painel > CRM > arquivo** ([ADR-0015](../adr/0015-quem-manda-nas-fotos-do-imovel.md)). Upload do painel (`/fotos/...`) sobrevive a qualquer reindexação; sem upload, valem as do CRM; sem CRM, as do arquivo | agente, painel, CRM | `repositories.py::ImovelRepository.upsert`, `acervo.py` | foto sumindo da vitrine sem aviso | `test_acervo_do_crm.py::test_a_foto_do_painel_vence_o_crm_no_indice`, `::test_foto_do_crm_vence_a_do_arquivo`, `::test_imovel_sem_foto_nenhuma_nao_inventa_capa` |

---

## 6. Interesses

Situações: `sugerido` · `interessado` · `descartado` · `visita_marcada`. Origens: `agente`, `site`,
`corretor`. Um registro por par lead+imóvel (`shared/sdr_shared/db/repositories.py::InteresseRepository`).

### 6.1 A regra de transição

> **`sugerido` nunca sobrescreve nada.** Qualquer outra situação sobrescreve a anterior — inclusive
> `descartado` sobre `visita_marcada`.

Testes: `test_cenarios.py::test_visita_marcada_sobrepoe_qualquer_situacao_anterior`,
`::test_imovel_descartado_nao_volta_a_ser_oferecido`.

### 6.2 Quem cria o quê

| Situação | Quem | Quando | Teste |
| --- | --- | --- | --- |
| `sugerido` | agente | ao apresentar imóveis, e ao avisar de imóvel novo | `test_cenarios.py::test_o_que_o_agente_mostra_vira_interesse_registrado` |
| `interessado` | site | clique em "falar sobre este imóvel" (`imovel_origem`) — interesse **declarado**; passar os olhos numa ficha fica só em `imoveis_visualizados` | `test_cenarios.py::test_botao_do_site_registra_interesse_declarado` |
| `interessado` / `descartado` / `visita_marcada` | corretor | pelo painel (`PUT /interesses/{lead}/{imovel}`); `sugerido` é recusado com **422** | `services/api/tests/test_api.py::test_corretor_marca_descartado_e_o_imovel_some_da_lista_de_interessados` |
| `visita_marcada` | agente | ao gravar a visita | `test_cenarios.py::test_visita_marcada_sobrepoe_qualquer_situacao_anterior` |

### 6.3 Visibilidade

- A ficha do lead mostra **todos** os interesses, inclusive descartados.
- A lista de interessados de um imóvel **esconde os descartados** e os leads encerrados, ordenada
  por score (`test_cenarios.py::test_interessados_ordena_por_score_e_ignora_descartado`).

### 6.4 Espelho no CRM

Tradução (`shared/sdr_shared/crm/interesses.py::SITUACAO`): `sugerido → presented`,
`interessado → interested`, `descartado → rejected`, `visita_marcada → interested`. Só os imóveis
**mostrados neste turno** sobem; a versão da oportunidade é encadeada entre chamadas; imóvel que o
CRM não conhece é pulado sem parar os outros; lead sem vínculo não publica; nada disso levanta
exceção. O descarte anotado pelo corretor no painel também sobe (`routers/interesses.py`). Testes:
`shared/tests/test_interesses_crm.py` (todos), `test_cenarios.py::test_o_que_o_agente_mostra_vira_interesse_registrado`.

---

## 7. Visitas (lado da Mora)

### 7.1 De onde vem o horário

> **Horário só do CRM ou da agenda.** A Mora nunca inventa disponibilidade
> (`shared/sdr_shared/crm/visitas.py`, `nodes/agendador.py::_oferecer`).

| Regra | Valor | Teste |
| --- | --- | --- |
| Com imóvel definido, a grade vem dos slots livres do CRM (`consultar_horarios`), até **8** | `horarios_do_imovel(limite=8)` | `test_agendador_crm.py::test_com_imovel_a_grade_vem_do_crm`, `shared/tests/test_visitas_crm.py::test_horarios_vem_do_crm_quando_ha_imovel` |
| Lista vazia do CRM significa "não sei", nunca "não há": cai na agenda do corretor | — | `test_agendador_crm.py::test_sem_resposta_do_crm_cai_na_agenda_do_corretor`, `test_visitas_crm.py::test_codigo_desconhecido_nao_inventa_indisponibilidade` |
| Sem imóvel escolhido, o CRM não é consultado | — | `test_visitas_crm.py::test_sem_imovel_nao_pergunta_ao_crm` |
| Agenda interna (reserva): **10h, 14h e 16h** (Brasília), 5 dias úteis à frente, começando **amanhã**, fins de semana pulados, até 15 slots gerados, **60 min**, horário confirmado sai da grade | `repositories.py::VisitaRepository.horarios_disponiveis` | `test_calendario.py::test_horario_ja_marcado_some_da_oferta`, `::test_sem_corretor_definido_usa_a_grade_da_equipe` |
| Com corretor definido, a grade interna desconta a agenda Google dele; falha do Google **não esvazia** a oferta | `VisitaRepository._agenda_externa` | `test_calendario.py::test_compromisso_no_google_tira_o_horario_da_oferta`, `::test_google_fora_do_ar_nao_esvazia_a_agenda` |

### 7.2 Como o horário é escolhido

Dois caminhos: **botão** (`slot:<iso>`) ou **texto livre** (ordinais, "14h", "às 3", dia da semana,
"amanhã", `dd/mm`). **Só confirma se restar exatamente um candidato e o cliente tiver dito ao menos
dia, hora ou data** (`nodes/agendador.py::_resolver_horario`). Hora fora da grade: explica em meia
frase e reoferece. O identificador do botão nunca entra cru no histórico — vira o rótulo legível
(`test_agendador_crm.py::test_clique_no_botao_nao_vira_iso_no_historico`,
`test_cenarios.py::test_horario_digitado`).

### 7.3 O que uma reserva produz — e o que ela **não** é

| Passo | Regra | Teste |
| --- | --- | --- |
| 1 | revalidação da colisão (`slot_livre`); ocupado no meio do caminho → reoferece sem culpar ninguém | `test_calendario.py::test_dois_clientes_nao_marcam_o_mesmo_horario`, `::test_a_visita_do_primeiro_cliente_permanece` |
| 2 | visita gravada com id determinístico `vis_<lead>_<epoch>` — reclicar **não** duplica | sem teste direto |
| 3 | interesse vira `visita_marcada`; estágio vira `agendado`; `pediu_visita = true` | `test_cenarios.py::test_horario_digitado` |
| 4 | evento no Google Agenda do corretor **se** conectado; **o Google nunca derruba a visita** | `test_calendario.py::test_visita_vira_evento_na_agenda_do_corretor`, `::test_falha_do_google_nao_impede_a_visita`, `::test_corretor_sem_agenda_conectada_segue_normal` |
| 5 | auditoria `visita.agendada` e notificação ao corretor (chave = id da visita, sem duplicar) | `test_notificacoes.py::test_visita_agendada_avisa`, `::test_o_mesmo_fato_nao_vira_dois_avisos` |
| 6 | **pedido no CRM** (`POST /v1/visits`, status `requested`) com o `slot_id` escolhido; antes disso move a oportunidade até `qualified` | `test_agendador_crm.py::test_o_slot_escolhido_vira_o_pedido`, `test_visitas_crm.py::test_pedido_entra_como_solicitado_e_nao_como_confirmado`, `::test_pedido_qualifica_antes_quando_o_crm_ainda_nao_sabe` |
| 7 | falha do pedido **não desfaz** a reserva nem derruba o turno; sem `slot_id` do CRM (horário da agenda interna) **não há pedido** | `test_agendador_crm.py::test_falha_do_pedido_nao_desfaz_a_reserva`, `::test_erro_do_crm_nao_derruba_o_turno`, `::test_horario_da_agenda_do_corretor_nao_inventa_slot`, `test_visitas_crm.py::test_pedir_duas_vezes_nao_duplica` |

> **Só humano confirma.** `agendado` na Mora **não** vira `visit_scheduled` no CRM
> ([D-14](../decisions.md)); o estágio avança lá quando o corretor confirmar
> (`shared/tests/test_crm_ponte.py::test_agendado_nao_vira_visit_scheduled`,
> `services/crm/tests/test_mcp.py::test_agente_nao_tem_como_confirmar_visita`).

A confirmação ao cliente fala do imóvel pela **descrição**, nunca pelo código
(`test_agendador_crm.py::test_reserva_fala_do_imovel_pela_descricao_e_nao_pelo_codigo`).

### 7.4 Escolha do corretor

Quem atende é escolhido por **região e carga** (`shared/sdr_shared/db/painel.py::CorretorRepository.escolher`):
(1) corretores **ativos** que atendem a região — **quem não tem região declarada atende todas**;
(2) se ninguém, os sem região declarada; (3) se ainda ninguém, qualquer ativo; (4) entre os aptos,
**menor carga** (leads em `handoff` + visitas futuras), empate por ordem alfabética. **Carteira** (o
que se move numa desativação) é mais ampla: leads abertos + visitas futuras. Teste:
`test_cenarios.py::test_handoff_roteia_para_corretor_da_regiao`.

---

## 8. Handoff (lado da Mora)

| Ação | O que muda | Fonte | Teste |
| --- | --- | --- | --- |
| **Assumir** | estágio vira `handoff`; corretor: body → o já vinculado (se existir no cadastro) → roteamento por região → **fila da equipe** (`corretor_id` nulo); visitas futuras acompanham; **follow-ups são cancelados** | `routers/handoff.py::assumir` | `services/api/tests/test_api.py::test_corretor_auth_e_handoff` |
| **Responder** | envia por **todos** os canais do lead, sem passar pelo agente; registra como `corretor`; sem canal → **409** | `routers/handoff.py::responder` | idem |
| **Devolver** | volta para `qualificado` (cartão completo) ou `qualificando`; o corretor **continua** vinculado | `routers/handoff.py::devolver` | idem |
| **Trocar corretor** | `PUT /leads/{id}/corretor`; corretor precisa existir; `null` desvincula | `routers/leads.py` | `test_api.py::test_lead_corretor` |

O usuário logado é um **ator de auditoria**, nunca vira o `corretor_id` do lead
(`test_api.py::test_apagar_corretor_no_banco_nao_deixa_lead_fantasma`).

Enquanto o lead está em `handoff`, a Mora **não responde**: a mensagem é registrada, o follow-up é
cancelado e o corretor recebe `lead.respondeu` — **no máximo um a cada 15 minutos por lead**
(`handler.py`, chave `int(time.time()) // 900`). Testes:
`test_notificacoes.py::test_cliente_que_responde_em_handoff_avisa_de_novo`,
`test_followup.py::test_cliente_que_responde_em_handoff_nao_leva_followup_por_cima`,
`test_monitoramento_turno.py::test_turno_que_morre_em_handoff_tambem_conta`.

**No CRM**, o encaminhamento é publicado no fim do turno com resumo (o da Mora ou o cartão) e o
destinatário resolvido por `corretores.crm_user_id`; sem ponte, sobe sem destinatário (fila aberta).
Testes: `test_crm_ponte.py::test_encaminhamento_passa_o_atendimento_para_humano`,
`::test_encaminhamento_leva_o_destinatario_quando_a_ponte_existe`, `::test_sem_ponte_o_encaminhamento_sobe_sem_destinatario`.

---

## 9. Corretores (painel da Mora)

| Regra | Detalhe | Fonte | Se violada | Teste |
| --- | --- | --- | --- | --- |
| Nome | mínimo 2 caracteres; id é slug do nome; duplicado é recusado | `routers/corretores.py` | **409** | sem teste |
| Regiões | **nenhuma selecionada = atende todas** | `painel.py::escolher` | — | `test_cenarios.py::test_handoff_roteia_para_corretor_da_regiao` |
| Inativo | não recebe handoff nem visita; o seletor do painel lista só ativos | `painel.py::listar(somente_ativos)` | — | sem teste |
| Foto | base64 PNG/JPEG/WebP ou URL `https`; recusada acima de **300 KB**; o navegador reduz a 256 px | `routers/corretores.py::CorretorIn` | **422** | sem teste |
| `crm_user_id` | `users.id` desta pessoa no CRM | idem | encaminhamento sem destinatário | `test_crm_ponte.py::test_corretor_guarda_o_id_do_crm` |
| Refresh token do Google | **cifrado em repouso** (Fernet, chave derivada de `SDR_SESSAO_SECRET`, prefixo `enc:v1:`); nunca sai para API nem painel; sem segredo, guarda em claro **com aviso**; segredo trocado levanta em vez de virar token vazio | `shared/sdr_shared/seguranca/cofre.py`, `painel.py::salvar_credencial_calendario` | — | `shared/tests/test_seguranca.py::test_refresh_token_fica_cifrado_no_banco_e_volta_legivel`, `::test_segredo_trocado_nao_vira_token_vazio_em_silencio`, `::test_sem_segredo_guarda_em_claro_e_avisa` |

### 9.1 Desativação — a carteira nunca fica órfã

Desativar **não apaga o cadastro** (`DELETE /corretores/{id}`). O destino é **obrigatório** quando
há carteira aberta (`_resolver_destino`):

| Destino | Efeito | Teste |
| --- | --- | --- |
| `equipe` (ou vazio) | leads e visitas ficam sem dono, na fila | `test_api.py::test_destino_equipe_devolve_para_a_fila_sem_dono` |
| `auto` | escolhe pela primeira região do corretor que sai e menor carga; sem ninguém, cai na fila | sem teste |
| um corretor | precisa existir, estar **ativo** e não ser o próprio (**422** em cada caso) | `test_api.py::test_destino_invalido_e_recusado_antes_de_mexer_em_qualquer_coisa` |

Numa única transação movem-se leads abertos, visitas futuras e **notificações não lidas**
(`painel.py::desativar`). **Dois 409:** carteira aberta sem destino; `remover_cadastro=true` com
carteira aberta. Cada lead transferido gera `lead.transferido` ao novo dono. Testes:
`test_api.py::test_desativar_corretor_com_carteira_exige_destino`, `::test_desativar_move_a_carteira_e_avisa_quem_recebeu`, `::test_cadastro_sem_carteira_pode_ser_apagado`.

---

## 10. Follow-up

Cadência padrão (`shared/sdr_shared/followup.py::PADRAO`), configurável no painel (chave `followup`):

| Tentativa | Base (`tempos_min`) | quente (×0,25) | morno (×1,0) | frio (×2,0) |
| --- | --- | --- | --- | --- |
| 1ª | 120 min | 30 min | 2 h | 4 h |
| 2ª | 1440 min | 6 h | 24 h | 48 h |
| 3ª | 4320 min | 18 h | 72 h | 6 dias |

| Regra | Valor | Se violada | Teste |
| --- | --- | --- | --- |
| **O número de tentativas é o tamanho da lista** | painel aceita 1–**10** tentativas, cada uma **≥ 5** min; ritmo entre 0,05 e 10 | **422** | `test_followup.py::test_o_numero_de_tentativas_vem_da_lista_de_tempos`, `::test_tempos_alterados_no_painel_valem_no_proximo_turno` |
| **Janela 08:00–20:00**, fuso `America/Sao_Paulo`; fora dela o envio é **adiado** para a próxima abertura, nunca cancelado; `dias_uteis` opcional | `janela_inicio`/`janela_fim` (HH:MM, início < fim) | **422** na configuração; adiamento no envio | `::test_followup_da_madrugada_e_adiado_para_a_manha`, `::test_janela_configuravel`, `::test_dias_uteis_pula_o_fim_de_semana`, `::test_sem_dias_uteis_o_sabado_vale` |
| Piso absoluto | `MIN_DELAY = 5` min | — | `::test_nunca_agenda_para_agora_mesmo` |
| Ritmo por temperatura | quente volta antes do frio | — | `::test_lead_quente_e_chamado_de_volta_mais_cedo_que_o_frio`, `::test_agenda_conforme_a_temperatura` |
| Estágio após enviar | `frio` na última tentativa, `inativo` caso contrário; cada envio desconta **10 pontos** | — | `test_cenarios.py::test_cenario_followup` |
| Configuração inválida | cai no padrão em vez de quebrar; formato legado (`primeiro_min`, `segundo_h`, `terceiro_h`, `maximo`) é migrado | — | `::test_configuracao_invalida_cai_no_padrao_em_vez_de_quebrar`, `::test_configuracao_antiga_continua_valendo`, `::test_maximo_antigo_vira_o_tamanho_da_lista` |

**Desligamento/cancelamento** (`services/agent/src/agent/dispatch.py`): o lead chega a
`ENCERRADOS = (handoff, frio, agendado)`; as tentativas acabam; `ativo = false` no painel; ou o
cliente escreve estando em handoff. **Reagendado a cada turno bem-sucedido.** Lead encerrado
(sucessora) não recebe. Testes: `::test_desligar_o_followup_para_tudo`,
`::test_desligado_no_painel_limpa_o_que_estava_armado`, `::test_lead_encerrado_nao_recebe_followup`,
`::test_tentativas_esgotadas_limpam_o_agendamento`. No perfil local há **no máximo um follow-up
pendente por lead** (`followups_agendados`, chave por lead).

---

## 11. Reativação proativa

Quando um imóvel **entra** na base, a Mora avisa quem procurava algo assim e sumiu
([ADR-0013](../adr/0013-reativacao-proativa-de-leads-adormecidos.md)).

### 11.1 Pontuação (`shared/sdr_shared/reativacao.py::pontuar`)

**Eliminatórios** — qualquer um zera e devolve o motivo:

| Eliminatório | Regra |
| --- | --- |
| Operação | compra e investimento procuram `venda`; aluguel procura `aluguel` |
| Intenção indefinida | sem intenção não há o que casar |
| Acima do teto | `preco > preco_max` |
| Abaixo do piso | `preco < preco_min` |
| Quartos | `im.quartos < cartao.quartos` |
| Tipo | tipo pedido diferente do imóvel |

**Pontos** (teto 100; `PONTOS_MINIMOS = 60`):

| Item | Pontos |
| --- | --- |
| Base (passou nos eliminatórios) | +30 |
| Bairro citado pelo lead | +40 |
| …ou região certa | +25 |
| …ou fora da área citada | +5 |
| Folga ≥ 10% do teto de preço | +25 |
| Folga menor que 10% (e > 0) | +10 |
| Tipo bate | +10 |
| Urgência imediata | +10 |
| Selo de investimento, para investidor | +15 |

Base sozinha (30) não avisa; bairro exato (70) avisa; só região (55) não avisa. **Cada ponto gera um
motivo em português** que vira a primeira frase da mensagem. Testes: `shared/tests/test_reativacao.py`
(`test_imovel_que_bate_no_bairro_e_abaixo_do_teto_pontua_alto`, `test_eliminatorios_zeram_e_explicam`,
`test_fora_do_bairro_pontua_menos_que_dentro`, `test_investidor_procura_venda_e_ganha_com_o_selo`).

### 11.2 Quem não recebe, e por quê (`reativacao.elegivel`, nesta ordem)

1. oportunidade encerrada; 2. pediu para não receber avisos; 3. já está em `handoff`; 4. sem canal
de contato; 5. já conhece o imóvel (descartou / tem visita / já foi apresentado); 6. recebeu aviso
nos **últimos 7 dias** (`DIAS_ENTRE_REATIVACOES`); 7. conversou há **menos de 3 dias**
(`DIAS_SILENCIO`). Testes: `test_reativacao.py::test_quem_nao_pode_receber_e_por_que`, `::test_lead_antigo_e_silencioso_pode_receber`.

### 11.3 Limites de disparo

| Limite | Valor | Fonte | Teste |
| --- | --- | --- | --- |
| Avisos por imóvel | `MAX_AVISOS = 20` | `services/agent/src/agent/reativador.py` | `test_reativacao_fluxo.py::test_anunciar_enfileira_um_turno_por_candidato` |
| Leads varridos por rodada | `MAX_LEADS = 500` | idem | — |
| Imóveis novos por ingestão | acima de **5** (`LIMITE_AVISOS_POR_LOTE`), nada é anunciado | `sdr_ingestion/ingest_imoveis.py` | `test_reativacao_fluxo.py::test_carga_de_catalogo_nao_vira_aviso`, `::test_imovel_que_ja_existia_nao_gera_evento` |
| Canal | **Telegram** (`PREFERENCIA`); web fica de fora; lead sem canal aberto não recebe | `reativador.py::_melhor_canal` | `::test_lead_sem_canal_aberto_nao_recebe` |
| Imóvel apagado entre evento e consumo | o turno morre sem resposta | `nodes/reativador.py::_avisar` | `::test_imovel_apagado_entre_o_evento_e_o_consumo_nao_quebra` |
| Mesmo imóvel | não é anunciado duas vezes ao mesmo lead (`interesses` + `reativado_em`) | idem | `::test_o_mesmo_imovel_nao_e_anunciado_duas_vezes` |

### 11.4 Saída (`PEDE_SAIR`)

O opt-out desliga em dois lugares: **na conversa** (`nodes/reativador.py::PEDE_SAIR`; resposta fixa
`CONFIRMACAO_SAIDA`, sem modelo, auditada como `lead.optout_reativacao`) e **no painel**
(`PUT /leads/{id}/reativacao`). Testes: `test_reativacao_fluxo.py::test_cliente_pede_para_nao_receber_e_a_mora_desliga_na_hora`,
`::test_quem_saiu_nao_recebe_o_proximo_imovel`, `test_api.py::test_corretor_liga_e_desliga_o_aviso_de_imovel_novo`.

### 11.5 Medição

`GET /dashboard/reativacao` (janela padrão 30 dias, `JANELA_RESPOSTA_H = 48`) é reconstruído da
auditoria: avisos → responderam em até 48 h → viraram visita → pediram para sair. As taxas são
`null` quando não houve aviso (`shared/sdr_shared/db/painel.py::resumo_reativacao`). Testes:
`test_api.py::test_funil_de_reativacao_conta_o_que_o_aviso_produziu`, `::test_simulacao_de_reativacao_lista_quem_seria_avisado_e_quem_nao`.

---

## 12. Guardrails do agente

### 12.1 Escopo — o porteiro (`guardrails/escopo.py::avaliar`)

Regex determinística **antes** de gastar token. Ordem:

| # | Verificação | Limite | Teste |
| --- | --- | --- | --- |
| 1 | Texto gigante | `LIMITE_TEXTO = 1200` caracteres | `test_seguranca.py::test_mensagem_gigante_e_barrada` |
| 2 | Injeção de prompt | vence tudo, inclusive pedido legítimo junto | `::test_tentativa_de_reprogramar_o_agente_e_recusada`, `::test_injecao_disfarcada_de_pedido_legitimo_tambem_e_recusada` |
| 3 | Fora do domínio sempre (`FORA_SEMPRE`) | bitcoin, day trade, eleição, remédio, poema… | `::test_assunto_fora_do_dominio_e_recusado` |
| 4 | Domínio ou conversa | **passa**, mesmo com ruído junto | `::test_conversa_legitima_passa` |
| 5 | Fora do domínio (fraco) | perde para o domínio ("receita" também é receita de aluguel) | `::test_assunto_fora_do_dominio_e_recusado` |
| 6 | Nada casou | **passa** — na dúvida, atende | `::test_na_duvida_o_cliente_tem_o_beneficio` |

- Homóglifos (cirílico/grego) são dobrados para ASCII; **dígitos não**
  (`::test_injecao_com_homoglifos_e_recusada`, `::test_homoglifo_nao_quebra_conversa_legitima`).
- **Recusa fora de escopo** é texto fixo por categoria (`RESPOSTAS`), sem modelo; a recusa não
  chama corretor (`::test_supervisor_manda_o_off_topic_para_a_recusa_e_nao_para_um_corretor`,
  `::test_ataque_completo_recebe_recusa_e_nao_chega_ao_modelo`).
- A partir de **`MAX_RECUSAS = 3`** no mesmo lead (contador persistido no checkpoint), a Mora troca a
  negativa por `INSISTENCIA` e oferece "Falar com corretor"
  (`::test_insistencia_acaba_oferecendo_um_humano`, `::test_cliente_recusado_volta_a_ser_atendido_ao_falar_de_imovel`).

### 12.2 Vazão (`guardrails/vazao.py`)

Rajada: **5 mensagens em 10 segundos** (`RAJADA_N, RAJADA_S`); hora: **60 mensagens por hora**
(`HORA_N, HORA_S`); aviso ao cliente no máximo **1 por minuto** por lead. Excedeu: o turno é
descartado (`turnos.resultado = vazao`), o cliente é avisado uma vez (`AVISO`) e o evento é auditado
(`agente.vazao_excedida`). Turnos iniciados pela Mora não passam pela vazão. Testes:
`::test_rajada_e_contida_e_o_cliente_e_avisado_uma_vez`,
`::test_primeiro_aviso_de_vazao_sai_em_processo_recem_iniciado`, `::test_o_limite_e_por_lead`,
`::test_flood_nao_vira_turno_de_modelo`.

### 12.3 Saída — a última barreira (`guardrails/saida.py::sanear`, `util.py::limpar_texto`)

| Achado | Consequência | Teste |
| --- | --- | --- |
| Vazamento de instrução interna (`VAZAMENTO`) no texto bruto **ou** no limpo | **resposta inteira descartada**, substituída por `FALLBACK`; auditoria `agente.saida_barrada` | `::test_vazamento_de_instrucao_nunca_chega_ao_cliente` |
| CPF | mascarado (`[documento omitido]`) e enviado | `::test_documento_do_cliente_e_mascarado_na_resposta` |
| Cartão (13–19 dígitos) | mascarado (`[número omitido]`) e enviado | idem |
| **Telefone** | **não é mascarado** | `::test_telefone_continua_podendo_ser_confirmado` |
| Tags, blocos de código | removidos | `::test_tags_e_codigo_continuam_sendo_removidos` |
| Link markdown | fica só o texto visível | `::test_link_markdown_na_resposta_perde_o_destino` |
| URL crua, `www.`, `javascript:`/`data:`/`mailto:`/`tel:` | `[link removido]` | `::test_url_crua_na_resposta_e_removida`, `::test_esquemas_perigosos_saem_da_resposta` |
| Resposta vazia | vira `FALLBACK` | `::test_resposta_vazia_vira_pergunta_util` |

### 12.4 Entrada externa no prompt

Mensagem do cliente, nome extraído e cartão entram no prompt em envelope com delimitador não
adivinhável; descrição de imóvel e trecho de documento passam por `neutralizar_texto_externo`
(controles, invisíveis, marcador forjado, tags, uma linha, até 400/200/1200 caracteres). Testes:
`::test_mensagem_do_cliente_nunca_entra_crua_no_prompt`, `::test_marcador_forjado_pelo_cliente_e_neutralizado`,
`::test_descricao_de_imovel_maliciosa_e_neutralizada_antes_do_prompt`, `::test_cartao_tambem_vai_no_marcador`.

### 12.5 Histórico, concorrência e resiliência

| Regra | Valor | Fonte | Teste |
| --- | --- | --- | --- |
| **Poda do histórico 40 → 24**: acima de `MAX_HISTORICO = 40` mensagens, ficam as últimas `HISTORICO_APOS_PODA = 24`; o cartão sobrevive | — | `services/agent/src/agent/state.py::podar_historico`, `graph.py` | `test_cenarios.py::test_historico_longo_e_podado_e_o_cartao_sobrevive` |
| **Lock por lead derivado do orçamento do turno**: `orcamento_do_turno_s() = timeout × (1 + MAX_RETRIES) × 2 + 30`, com `MAX_RETRIES = 1` | — | `shared/sdr_shared/ports/factory.py`, `adapters/local/broker.py::_lock_s` | `shared/tests/test_broker_redis.py::test_lock_por_lead_dura_pelo_menos_um_turno_inteiro`, `::test_pendente_de_outro_consumidor_so_e_tomada_depois_de_um_turno_inteiro` |
| Sem barramento, o turno falha **antes** de começar (`turnos.resultado = barramento`) | — | `handler.py::_barramento_responde` | `test_resiliencia.py::test_sem_barramento_o_turno_falha_antes_de_comecar` |
| Falha no grafo: fallback honesto + handoff; o worker avisa mesmo se `processar` estourar | — | `handler.py::_responder_falha` | `test_resiliencia.py::test_falha_do_grafo_responde_e_encaminha`, `::test_worker_avisa_mesmo_se_processar_estourar` |
| Áudio: recibo imediato quando há motor; sem motor não se promete resposta; falha vira texto de degradação com log | — | `handler.py::_avisar_que_ouviu` | `test_transcricao.py::test_audio_ganha_recibo_antes_da_transcricao`, `::test_sem_motor_nao_se_promete_resposta` |

---

## 13. Governança de LLM

### 13.1 Orçamento (`shared/sdr_shared/db/governanca.py::LIMITES_PADRAO`)

Padrões: orçamento mensal **US$ 50** (0 = sem teto); teto de tokens/dia **1.000.000** (0 = sem
teto); alerta em **80%**; ação ao estourar `degradar`; cotação R$ 5,12. O percentual que vale é **o
maior** entre o de dólares e o de tokens (`_calcular_orcamento`).

### 13.2 Os três modos

| Modo | Quando | O que muda | Teste |
| --- | --- | --- | --- |
| `normal` | abaixo do teto, ou ação = `alertar` | nada | — |
| `degradado` | estourou e ação = `degradar` | `conversa` e `analise` passam a usar o modelo de **roteamento** (`factory.py::get_chat_model`) | `test_governanca.py::test_degradacao_por_orcamento`, `::test_teto_de_tokens_diario` |
| `bloqueado` | ação = `bloquear`, **ou** `degradar` acima de **150%** (`TETO_DURO = 1.5`) | **não chama modelo nenhum**: o lead vai para `handoff`, o cliente recebe "Vou chamar {corretor} para continuar com você agora mesmo", `turnos.resultado = orcamento` | `test_governanca.py::test_degradacao_por_orcamento` |

**Bloqueio por orçamento** é decidido em `handler.py::_bloqueado_por_orcamento`, antes do grafo, e
auditado como `agente.bloqueado_por_orcamento`.

### 13.3 Modelos e provedores ([ADR-0009](../adr/0009-gateway-de-llm-litellm-openrouter-ou-nada.md), [ADR-0010](../adr/0010-modelo-por-nivel-e-troca-pelo-painel.md))

| Regra | Vale em | Fonte | Se violada | Teste |
| --- | --- | --- | --- | --- |
| Três níveis: `conversa`, `roteamento`, `analise`; **`analise` sem configuração cai em `conversa`** | agente, painel | `shared/sdr_shared/db/modelos.py` | — | `test_api.py::test_modelos_aceita_modelo_com_preco_e_muda_o_efetivo` |
| **O painel manda, o `.env` é o piso**; campo vazio = "usa o do ambiente" | painel | `modelos.py`, `factory.py::_escolha_do_painel` | — | `shared/tests/test_fallback_provedor.py::test_painel_vence_o_ambiente_na_escolha_do_reserva` |
| **"Vazio ≠ desligado"**: `fallback_provider = "nenhum"` desliga o reserva herdado do `.env`; em `operacao`, `0` é resposta e vazio é ausência | painel | `modelos.py::reserva`, `db/operacao.py` | apagar o campo não desfaria o ambiente | `test_fallback_provedor.py::test_painel_pode_DESLIGAR_um_reserva_herdado_do_ambiente`, `shared/tests/test_operacao_painel.py::test_vazio_delega_ao_ambiente`, `::test_zero_e_resposta_nao_ausencia` |
| Provedores aceitos: `anthropic`, `openai`, `ollama` (`openrouter` só para bancada) | painel | `routers/config.py::PROVIDERS` | **422** | `test_api.py::test_modelos_recusa_provedor_e_id_invalidos` |
| **Modelo sem preço cadastrado é recusado**, porque custo zero desliga o teto em dólar | painel | `config.py::_validar_modelos` | **422** com o caminho para resolver | `test_api.py::test_modelos_recusa_modelo_sem_preco` |
| **Ollama dispensa preço** (custo local) | painel | idem | — | `test_api.py::test_modelos_ollama_dispensa_preco` |
| Reserva igual ao primário é recusado; reserva desconhecido é recusado | painel | idem | **422** | `test_api.py::test_reserva_igual_ao_primario_e_recusada`, `::test_reserva_desconhecida_e_recusada` |
| Reserva de **outra família** troca o modelo pelo equivalente do papel | agente | `factory.py::modelo_do_provedor` | 404 do provedor | `shared/tests/test_factory.py::test_fallback_para_outra_familia_usa_um_modelo_que_existe_la` |
| Temperatura: **0,0** no roteamento, **0,6** nos demais; `max_tokens = 600` | agente | `factory.py::get_chat_model` | — | sem teste |
| `llm_timeout_s` entre 5 e 180; `acervo_refresh_s` é 0 ou ≥ 60; `transcricao` ∈ {auto, whisper_local, off} | painel | `config.py::_validar_operacao` | **422** | `test_api.py::test_operacao_recusa_timeout_fora_da_faixa`, `::test_operacao_recusa_refresh_curto_demais`, `::test_operacao_recusa_motor_desconhecido` |

---

## 14. Observabilidade e auditoria (Mora)

### 14.1 O que a aba Saúde mede

`turnos` grava uma linha por turno com **o tempo que o cliente esperou** (`shared/sdr_shared/db/monitoramento.py`).

| `turnos.resultado` | Significa |
| --- | --- |
| `ok` | turno concluído |
| `vazao` | bloqueado pelo limite de mensagens |
| `handoff` | o corretor responde, o agente não |
| `orcamento` | bloqueado pelo teto de LLM |
| `erro` | exceção no grafo; o cliente recebeu o fallback |
| `reativacao` | aviso de imóvel novo |
| `barramento` | broker não respondeu ao ping; o turno não começou |

Retenção de **7 dias** (`RETENCAO_DIAS`). Testes: `test_monitoramento_turno.py` (3 testes),
`shared/tests/test_monitoramento.py::test_resumo_calcula_percentis_e_taxa_de_falha`.

### 14.2 Batimentos e `/health`

Cada worker carimba `batimentos` a cada **30 s** (`BATIMENTO_S`); sem carimbo há mais de **120 s**
(`PARADO_S`) o serviço é dado como parado. **`/health` devolve 503** quando o banco não responde
**ou** algum worker está calado (`services/api/src/api/main.py::health`). No CRM, `/health/live`
não toca no banco e `/health/ready` exige **todas as tabelas do `schema.sql`**. Testes:
`test_api.py::test_health_devolve_503_quando_um_servico_para`, `test_monitoramento.py::test_servico_calado_aparece_como_parado`,
`services/crm/tests/test_api_funil.py::test_liveness_nao_depende_do_banco`, `test_api_fotos.py::test_readiness_reprova_quando_falta_tabela`.

### 14.3 Auditoria (`shared/sdr_shared/db/auditoria.py`)

| Regra | Teste |
| --- | --- |
| **Falhar ao auditar nunca derruba a operação auditada** | `services/api/tests/test_auditoria.py::test_auditoria_nunca_derruba_a_acao_auditada` |
| Chaves contendo `senha`, `password`, `token`, `secret`, `authorization`, `api_key`, `imagem`, `foto` ou `embedding` viram `[omitido]`; listas cortadas em 20, textos em 500, profundidade 4 | `::test_segredo_e_payload_gigante_nunca_entram_na_trilha` |
| **Exportar a trilha é ela própria uma ação auditada** | `::test_exportacao_csv_se_autoregistra` |
| Todo `POST/PUT/PATCH/DELETE` é registrado pelo middleware (`auditoria_mw.py`); leitura de rotina não polui; listagem de leads registra uma vez por janela | `::test_mutacao_pela_api_vira_registro`, `::test_leitura_de_rotina_nao_polui_a_trilha`, `::test_listagem_de_leads_registra_uma_vez_por_janela` |

---

## 15. O painel da Mora — o que o corretor pode fazer

| Tela | Ações | Travas |
| --- | --- | --- |
| **Visão geral** | filtrar período (7/14/30/90 dias) | somente leitura; pipeline e ticket **não** seguem o filtro |
| **Leads** | filtrar, ordenar, sincronizar CRM | exporta só `qualificado`, `agendado` e `handoff` (`routers/leads.py`) |
| **Ficha do lead** | assumir, devolver, responder, trocar corretor, ligar/desligar avisos, gerar briefing, marcar interesse | **responder só em handoff**; seletor lista **apenas ativos**; briefing considera "sem resposta" após **90 s** (`LeadDetalhe.tsx`) |
| **Clientes** | buscar, abrir ficha | quem não deixou contato não aparece (`test_clientes.py::test_sem_contato_nao_inventamos_um_cliente`) |
| **Imóveis** | subir/remover/reordenar fotos, ver interessados, simular reativação | **12 fotos** por imóvel, **≤ 1,5 MB** cada, reduzidas a 1280 px no navegador; a simulação **não envia nada** |
| **Corretores** | criar, editar, ativar/desativar, apagar, conectar Google Agenda | desativar **exige destino**; apagar só com carteira vazia; nenhum token do Google passa pelo painel |
| **Governança** | limites, preços por modelo, comparação de modelos | modelo sem preço é recusado |
| **Auditoria** | filtrar, exportar CSV | 300 mais recentes; exportar é auditado |
| **Saúde** | espera, filas, serviços, provedores | leitura |
| **Configurações** | agente, follow-up, agenda, cobertura, handoff, modelos, operação | **`followup`, `modelos` e `operacao` valem no próximo turno** (cache invalidado ao salvar); `agente`, `agenda`, `cobertura` e `handoff` são declarativas |

**Regiões de cobertura:** a lista da tela (`config.py::DEFAULTS["cobertura"]`) espelha as 5 regiões
de `shared/sdr_shared/geo.py`, mas **quem decide cobertura é o `geo.py`**, não a configuração.

**Autenticação (Mora):** token estático `SDR_PAINEL_TOKEN`, comparado em tempo constante
(`shared/sdr_shared/seguranca/painel.py`). No perfil local, sem token configurado, vale `dev-token`;
fora dele, sem segredo **nada é aceito** (`shared/tests/test_seguranca.py::test_painel_local_aceita_token_de_dev`,
`::test_painel_fora_do_local_e_fail_closed`, `test_api.py::test_rota_protegida_sem_token_responde_401_e_nao_500`).

**Token do painel fora da URL do WebSocket:** o canal `papel=dashboard` recebe a credencial no
**primeiro quadro** `{"token": ...}` em até `PRAZO_CREDENCIAL_S = 5` s; token na query string
**não vale** (`services/channels/local/app.py`; `services/channels/local/tests/test_app.py::test_credencial_do_painel_na_url_nao_vale_mais`,
`::test_painel_sem_credencial_nao_conecta`, `::test_papel_desconhecido_nao_vira_painel`).

---

## 16. O site público

| Recurso | Regras | Fonte | Teste |
| --- | --- | --- | --- |
| **Catálogo** | 12 por página (`PAGINA`); filtros por operação, tipo, quartos, suítes, vagas, preço, área, região e bairro; busca com atraso de 350 ms; `GET /imoveis/busca` limite 1–60, ordenação validada (**422**) | `apps/web/src/pages/Imoveis.tsx`, `routers/imoveis.py::busca` | `test_api.py::test_busca_pagina_conta_e_lista_bairros`, `::test_busca_recusa_parametro_invalido` |
| **Ficha** | pontos de referência do bairro (`geo.BAIRROS[...]["refs"]`), com a ressalva de que o endereço exato vem com o corretor | `routers/imoveis.py::_publico` | `test_api.py::test_publico` |
| **Favoritos** | ficam **no navegador** | `apps/web/src/pages/Favoritos.tsx` | sem teste |
| **Vistos recentemente** | até 8 guardados (`MAX`), 4 exibidos | `apps/web/src/lib/vistos.ts`, `VistosRecentemente.tsx` | sem teste |
| **Simulação de financiamento** | Tabela Price; entrada padrão 20%, juros padrão 10,49% a.a., prazos 10–30 anos; **só venda**; rotulada como estimativa | `apps/web/src/lib/financiamento.ts` | sem teste |
| **Custo mensal** | aluguel = aluguel + condomínio (IPTU fora); venda = condomínio + IPTU estimado em 0,8% a.a. (`IPTU_ANUAL_ESTIMADO`) | idem | sem teste |
| **Chat** | sessão assinada pelo servidor, válida **12 h** (`VALIDADE_S`); aos 10 s avisa que ainda procura, aos 60 s oferece humano | `routers/eventos.py`, `apps/web/src/chat/ChatWidget.tsx` | `test_sessao.py` (5 testes), `test_app.py::test_sessao_inventada_pelo_navegador_nao_conecta` |
| **Rastreamento** | exatamente quatro eventos: `viewed_imovel`, `filtered`, `clicked_telegram`, `opened_chat`; sem sessão válida o servidor descarta | `routers/eventos.py::TIPOS` | `test_cenarios.py::test_contexto_do_site` |
| **Privacidade** | faixa que não bloqueia a navegação; consentimento acontece quando a pessoa entrega contato no chat | `apps/web/src/pages/Privacidade.tsx` | — |

### 16.1 Dados institucionais e a regra do placeholder

`nome`, `slogan`, `missão` e `descrição` são reais; **CRECI, CNPJ, endereço, telefone, e-mail,
horário e responsável técnico são placeholders** (`apps/web/src/lib/imobiliaria.ts`), exibidos com
selo "EXEMPLO" e **nunca publicados no dado estruturado** (JSON-LD). Prova social só com origem
verificável. Sem teste.

---

## 17. O CRM — regras do registro comercial

O CRM vive em banco **separado** (`crm`), com API `/v1`, MCP e painel próprio. A Mora escreve e lê
por MCP; nada do CRM toca o banco da Mora ([D-01, D-02](../decisions.md)). Fonte principal:
`services/crm/sdr_crm/`.

### 17.1 Atores e permissão

| Regra | Fonte | Se violada | Teste |
| --- | --- | --- | --- |
| Dois atores: **serviço** (Bearer, token só como hash SHA-256, com scopes, expiração e revogação) e **humano** (sessão em cookie `crm_session`, HttpOnly, SameSite=lax, `Secure` fora de dev, **12 h**) | `api/auth.py`, `routers/autenticacao_rt.py` | **401** `UNAUTHENTICATED` | `services/crm/tests/test_api_leads.py::test_sem_token_e_401`, `::test_token_revogado_e_recusado` |
| **Scope não é autorização**: scope diz o que a credencial pode *pedir*; o papel diz o que o ator pode *fazer* | `api/auth.py` | **403** `FORBIDDEN` | `test_dominio.py::test_agente_nao_marca_ganho` |
| `humano` = `tipo == "user"` e papel `admin` ou `broker`; `reader` só lê | `auth.py::Ator.humano` | **403** | `test_api_funil.py::test_auditoria_e_so_do_administrador` |
| **`exigir_humano` é absoluto; não existe "agindo em nome de"** ([ADR-0015](../adr/0015-quem-manda-nas-fotos-do-imovel.md)). Ações humanas: cadastrar imóvel, mudar situação, alterar fotos, abrir horário, confirmar/concluir/no-show de visita, aceitar/resolver encaminhamento, liberar contato, arquivar, transições `SOMENTE_HUMANO` | `auth.py::exigir_humano` e cada rota | **403** | `test_api_fotos.py::test_agente_nao_cadastra_imovel_nem_mexe_em_foto`, `test_api_situacao_imovel.py::test_agente_nao_muda_situacao_de_imovel`, `test_api_funil.py::test_confirmacao_e_humana_e_avanca_o_estagio`, `::test_agente_nao_aceita_encaminhamento` |
| Login: mensagem única para usuário inexistente, senha errada e conta inativa; logout **revoga no banco** | `autenticacao_rt.py` | — | `test_api_login.py::test_login_certo_entra_e_errado_recebe_a_mesma_mensagem` |
| **Login limitado a 10/min por IP e por e-mail** (`login_tentativas_por_minuto`); login válido também conta | `api/contexto.py::conferir_limite_de_login` | **429** `RATE_LIMITED` + `Retry-After` | `test_api_login.py::test_login_tem_teto_por_ip`, `::test_teto_por_email_vale_mesmo_de_ips_diferentes`, `::test_login_valido_tambem_conta_no_teto` |
| **Senha ≤ 256 caracteres**, recusada antes do Argon2 | `api/esquemas.py::Login` | **422** | `test_api_login.py::test_senha_gigante_e_recusada_antes_do_argon2` |
| **120 chamadas/min por credencial** (`rate_limit_por_minuto`), contador em memória de uma instância | `contexto.py::conferir_limite` | **429** | sem teste |
| Auditoria (`audit_events`) só para `admin`; somente append; gravada na **mesma transação**; `password`, `token`, `authorization`, `session`, `secret` viram `[omitido]`; textos em 500 | `api/auditoria.py`, `routers/dashboard_rt.py` | — | `test_api_funil.py::test_auditoria_e_so_do_administrador`, `::test_auditoria_nao_guarda_segredo` |

### 17.2 Protocolo: idempotência, versão, corpo

| Regra | Fonte | Se violada | Teste |
| --- | --- | --- | --- |
| **Corpo ≤ 256 KB** (`corpo_maximo_bytes`), conferido pelo `Content-Length` antes de ler | `api/main.py::limitar_corpo` | **413** `PAYLOAD_TOO_LARGE` | sem teste |
| `extra="forbid"` em todo corpo | `api/esquemas.py` | **422** `VALIDATION_ERROR` | `test_api_leads.py::test_campo_desconhecido_e_recusado` |
| **Idempotência**: `POST` de mutação exige `Idempotency-Key` (via MCP, `operation_id`); replay devolve o resultado original com `Idempotent-Replay: true`, gravado na **mesma transação**; janela **24 h** (`idempotencia_horas`); chave única por credencial | `api/contexto.py::executar`, `api/protocolo.py` | **409** `BUSINESS_RULE` sem chave | `test_api_leads.py::test_replay_da_mesma_chave_devolve_o_mesmo_id`, `::test_replay_gera_uma_linha_e_um_evento_de_auditoria`, `::test_post_sem_idempotency_key_e_recusado`, `test_mcp.py::test_toda_mutacao_exige_operation_id`, `::test_repetir_com_o_mesmo_operation_id_nao_duplica` |
| Mesma chave com **outro corpo** (hash canônico, ordem das chaves não importa) ou outra rota | `protocolo.py::buscar_replay` | **409** `IDEMPOTENCY_CONFLICT` | `test_api_leads.py::test_mesma_chave_com_outro_corpo_e_409`, `::test_ordem_das_chaves_no_json_nao_muda_o_hash` |
| **Replay é verificado antes da versão**: repetir uma transição já aplicada devolve o resultado, não 412 | `contexto.py::executar` | — | `test_api_funil.py::test_repetir_transicao_com_a_mesma_chave_devolve_o_resultado_e_nao_412` |
| `PATCH`/`PUT`/transições exigem `If-Match` com a versão (ETag); ausente é **428**, desatualizado é **412**; `*` aceita qualquer | `protocolo.py::versao_do_if_match` | **428** `PRECONDITION_REQUIRED` / **412** `VERSION_CONFLICT` | `test_api_leads.py::test_alteracao_sem_if_match_e_428`, `::test_duas_edicoes_na_mesma_versao_uma_vence`, `::test_detalhe_devolve_etag` |
| `external_event_id` de interação é **único por canal**; reentrega devolve o registro original (200) | `schema.sql::interactions_evento_uk`, `routers/leads_rt.py` | — | `test_api_leads.py::test_evento_externo_reentregue_nao_duplica_o_historico`, `::test_mesmo_id_de_evento_em_canais_diferentes_sao_mensagens_diferentes` |
| **422 é sintaxe, 409 é mundo**; erro sempre no mesmo envelope `{error: {code, message, details, retryable}, request_id}` | `erros.py` | — | `test_mcp.py::test_erro_de_negocio_vem_com_iserror_e_codigo` |
| Paginação por cursor opaco `(created_at, id)`; `limit` 1–100, padrão 20; cursor inválido = do começo | `protocolo.py` | — | sem teste |

### 17.3 Clientes (`leads`)

| Regra | Fonte | Se violada | Teste |
| --- | --- | --- | --- |
| Criar exige **e-mail, telefone ou `external_contact_id`** | `esquemas.py::LeadNovo`, `schema.sql::leads_identificador_ck` | **422** | `test_api_leads.py::test_lead_sem_identificador_e_422` |
| Telefone vira E.164 (`+55` para 10–11 dígitos); o que não vira E.164 é descartado; e-mail só `trim` + minúsculo (sem regras de provedor); **nome nunca deduplica** | `dominio/contatos.py` | identificador inutilizável → **409** | `test_dominio.py::test_normalizar_telefone`, `::test_email_com_ponto_e_mais_nao_e_alterado` |
| Cliente que volta pelo mesmo identificador recebe **200** com o registro existente, não 201 | `routers/leads_rt.py::criar` | — | `test_api_leads.py::test_cliente_que_volta_pelo_mesmo_email_nao_vira_segundo_cadastro` |
| Identificadores apontando para pessoas diferentes: **nunca merge automático** | idem | **409** `LEAD_CONFLICT` | `::test_email_e_telefone_apontando_para_clientes_diferentes_e_409` |
| `contact_policy` nasce `unknown` e **não significa autorização**; o agente pode **bloquear**, nunca liberar nem promover | `leads_rt.py::alterar` | **403** | `::test_agente_bloqueia_contato_mas_nao_libera`, `::test_humano_libera_contato` |
| Arquivar é humano; arquivado some da lista, continua acessível por id e **não recebe oportunidade nova** | `leads_rt.py`, `oportunidades_rt.py::criar` | **403** / **409** | `::test_arquivado_some_da_lista_e_continua_acessivel_por_id`, `::test_agente_nao_arquiva` |
| Mensagem recebida é registrada **mesmo com contato bloqueado** e com atendimento humano | `leads_rt.py::registrar_interacao` | — | `::test_mensagem_recebida_e_registrada_mesmo_com_contato_bloqueado` |

### 17.4 Oportunidades e funil (`dominio/funil.py`)

Estágios: `new` · `in_service` · `qualified` · `visit_scheduled` · `negotiation` · `won` · `lost`.
Atendimento: `agent` · `human_pending` · `human`. **Tabela de transições de estágio** (`PERMITIDAS`):

| De | Para | Quem pode | Exige motivo |
| --- | --- | --- | --- |
| `new` | `in_service` | agente ou humano | não |
| `new` | `lost` | **só humano** | sim |
| `in_service` | `qualified` | agente ou humano — exige `city`, `purpose`, `budget_max_cents` | não |
| `in_service` | `lost` | só humano | sim |
| `qualified` | `visit_scheduled` | agente ou humano — **exige visita confirmada futura** | não |
| `qualified` | `negotiation` | só humano | não |
| `qualified` | `lost` | só humano | sim |
| `visit_scheduled` | `qualified` | agente ou humano | não |
| `visit_scheduled` | `negotiation` | só humano | não |
| `visit_scheduled` | `lost` | só humano | sim |
| `negotiation` | `won` / `lost` | só humano | `lost` sim |
| `won` / `lost` | `in_service` (reabertura) | só humano | sim |

| Regra | Se violada | Teste |
| --- | --- | --- |
| **O agente só chega até `qualified`** (`SOMENTE_HUMANO`); `won`, `lost`, `negotiation`, reabertura são humanas | **403** `FORBIDDEN` | `test_dominio.py::test_agente_nao_marca_ganho`, `::test_agente_nao_declara_perda_nem_com_motivo`, `test_api_funil.py::test_agente_nao_marca_ganho` |
| Salto de estágio é recusado; mesmo estágio é recusado | **409** `INVALID_TRANSITION` com `allowed` | `test_dominio.py::test_salto_de_estagio_recusado` |
| **Motivo é exigido pela transição, não pelo destino** ([D-06](../decisions.md)): `new → in_service` não exige; `won/lost → in_service` exige | **409** `REASON_REQUIRED` | `::test_comecar_atendimento_nao_exige_motivo_mas_reabrir_exige`, `::test_humano_perde_com_motivo_e_nao_perde_sem`, `::test_reabertura_exige_motivo_e_e_humana` |
| Qualificar sem `city`/`purpose`/`budget_max_cents` devolve **a lista do que falta**; `purpose` vem da oportunidade | **409** `QUALIFICATION_INCOMPLETE` + `missing_fields` | `test_api_funil.py::test_qualificar_sem_orcamento_e_409_com_a_lista_do_que_falta`, `test_dominio.py::test_purpose_vem_da_oportunidade_e_nao_das_preferencias` |
| `visit_scheduled` **não se declara**: só com visita confirmada no futuro | **409** `VISIT_NOT_CONFIRMED` | `test_dominio.py::test_visit_scheduled_exige_visita_confirmada` |
| Ordem das checagens: estrutura → quem comanda → papel → motivo → dados; o agente que tenta `won` recebe 403, não uma lista de campos | — | `::test_ordem_das_checagens_403_antes_de_campos_faltantes` |
| Atendimento `human_pending`/`human` **congela o agente** (transições, preferências, pedido de visita), não o corretor | **409** `HUMAN_IN_CONTROL` | `::test_atendimento_humano_congela_o_agente_mas_nao_o_corretor`, `test_api_funil.py::test_encaminhamento_congela_o_agente_e_deixa_ouvir` |
| Cancelar a última visita futura confirmada devolve `visit_scheduled → qualified`; **negociação não regride** | — | `::test_cancelar_visita_volta_para_qualified_mas_nao_regride_negociacao`, `test_api_funil.py::test_cancelar_a_ultima_visita_futura_recalcula_o_estagio` |
| Perder exige `lost_reason`; ganhar/perder preenche `closed_at`, e só eles | banco recusa (`CHECK`) | sem teste |

### 17.5 Preferências e interesse

| Regra | Fonte | Se violada | Teste |
| --- | --- | --- | --- |
| `PUT /preferences` é **substituição completa**; a versão conferida é a da **oportunidade** | `oportunidades_rt.py::salvar_preferencias` | **412/428** | `test_api_funil.py::test_preferencias_sao_substituidas_e_nao_mescladas` |
| `budget_basis = monthly_total` **só em aluguel** | idem | **409** | `::test_monthly_total_so_existe_para_aluguel` |
| Interesse: `presented` / `interested` / `rejected`, um por par; imóvel e oportunidade precisam ter o **mesmo propósito** | `oportunidades_rt.py::registrar_interesse` | **409** | `test_mcp.py::test_jornada_completa_pelo_mcp` |

### 17.6 Imóveis (`routers/imoveis_rt.py`)

| Regra | Se violada | Teste |
| --- | --- | --- |
| **Situação do imóvel**: `available` · `reserved` · `unavailable`. `reserved` é proposta aceita antes da assinatura; `unavailable` é a assinatura; **`reserved` volta para `available`** quando a proposta cai | — | `test_api_situacao_imovel.py::test_reservar_e_devolver_ao_catalogo` |
| **Motivo é obrigatório para sair do catálogo** (`available → reserved/unavailable`) e opcional para voltar | **422** | `::test_sair_do_catalogo_exige_motivo_e_voltar_nao` |
| **Recusa com visita confirmada futura**: não se tira do catálogo um imóvel com `confirmed` no futuro — cancele antes | **409** com `visitas_confirmadas` | `::test_visita_confirmada_no_futuro_impede_tirar_do_catalogo` |
| Mudar para a mesma situação é recusado | **409** | `::test_mudar_para_a_mesma_situacao_e_recusado` |
| Mudar situação, cadastrar e alterar fotos são **humanas** | **403** | `::test_agente_nao_muda_situacao_de_imovel`, `test_api_fotos.py::test_agente_nao_cadastra_imovel_nem_mexe_em_foto` |
| A situação **não** é automática a partir do `won`: oportunidade é do cliente, imóvel é do acervo | — | — |
| `GET /v1/properties` filtra `status=available` por padrão; buscar por `code` ignora o filtro | — | `test_acervo_do_crm.py::test_vendido_fica_fora_do_indice` |
| **`interested_count`**: clientes **distintos** com `presented` ou `interested` (rejeitado não conta); o painel do CRM mostra "N clientes de olho" quando **≥ 2** (`interested_count > 1`) | — | `test_api_situacao_imovel.py::test_procura_conta_clientes_distintos_e_ignora_descartado` |
| **Fotos (`property_photos`)**: referência `https?://`, `alt` opcional, até **20** por imóvel; a posição vem do **índice da lista** (a primeira é a capa); `PUT /photos` substitui a galeria inteira; a mesma URL duas vezes na lista é **422**; a chave única do banco (`property_photos_unica`) é a rede para quem escreve por outro caminho | **422** | `test_api_fotos.py::test_cadastro_com_fotos_guarda_a_ordem_e_devolve_na_leitura`, `::test_url_que_nao_e_http_e_recusada`, `::test_substituir_a_galeria_apaga_o_que_saiu_e_reordena`, `::test_a_mesma_foto_duas_vezes_e_recusada` |
| Custos: **nulo é desconhecido, nunca zero**; total mensal só em aluguel; total incompleto sai marcado (`monthly_total_incomplete`) e o filtro por `monthly_total` **não some** com ele | — | `test_api_funil.py::test_custos_saem_discriminados_e_o_desconhecido_nao_vira_zero`, `::test_imovel_com_total_desconhecido_nao_some_do_filtro_por_orcamento`, `test_dominio.py::test_componente_desconhecido_nao_vira_zero` |
| Código duplicado é recusado | **409** | sem teste |
| **`GET /v1/brokers`**: só usuários **ativos** com papel `admin` ou `broker`; devolve `id`, `name`, `role`, **nunca e-mail** | — | sem teste |
| Descrição maliciosa volta como **dado**, não instrução | — | `test_api_funil.py::test_instrucao_maliciosa_na_descricao_volta_como_dado`, `test_mcp.py::test_imovel_com_injecao_volta_como_dado` |

### 17.7 Agenda e visitas (`routers/visitas_rt.py`, `schema.sql`)

| Regra | Se violada | Teste |
| --- | --- | --- |
| Abrir horário é humano; exige corretor **ativo** `admin`/`broker`; `starts_at < ends_at` | **403** / **409** / **422** | sem teste |
| **`availability_sem_sobreposicao`**: um corretor não tem dois slots que se cruzem; intervalo semiaberto `[início, fim)` ([D-08](../decisions.md)) | **409** "O corretor já tem horário neste intervalo." | sem teste |
| **`taken`** nos slots: `EXISTS visita confirmed/completed`; com `only_free=true` (padrão) os tomados somem, e `taken` só é informação com `only_free=false` — é como a agenda do imóvel mostra o ocupado (`apps/crm/src/paginas/AgendaImovel.tsx`) | — | sem teste |
| **Solicitar não reserva**: `POST /visits` nasce `requested`; exige oportunidade em `qualified`+ (em `new`/`in_service` devolve o que falta), não encerrada; imóvel `available` e do mesmo propósito; slot do imóvel e no futuro; agente bloqueado quando o atendimento é humano | **409** | `test_api_funil.py::test_solicitar_visita_nao_agenda_nada`, `::test_visita_exige_oportunidade_qualificada`, `::test_imovel_indisponivel_nao_recebe_visita`, `test_mcp.py::test_solicitar_visita_nao_confirma_nada` |
| Transições: `requested → confirmed/cancelled`; `confirmed → completed/cancelled/no_show`; finais não editáveis | **409** com `allowed` | `test_api_funil.py::test_visita_concluida_nao_e_mais_editavel` |
| **Confirmar, concluir e no-show são humanas**; confirmar avança `qualified → visit_scheduled` e nunca regride negociação | **403** | `::test_confirmacao_e_humana_e_avanca_o_estagio` |
| Cancelar exige motivo; o agente só cancela o que ainda está `requested` | **409** | sem teste |
| **`visits_slot_confirmado_uk`**: duas confirmações no mesmo slot não coexistem — o índice único parcial decide, não a aplicação ([D-09](../decisions.md)) | **409** `SLOT_UNAVAILABLE` | `::test_duas_confirmacoes_no_mesmo_horario_uma_recebe_409` |
| A ferramenta MCP **não expõe** confirmação (18 ferramentas; só `solicitar_visita` e `cancelar_visita`) | — | `test_mcp.py::test_agente_nao_tem_como_confirmar_visita`, `::test_handshake_e_catalogo_de_ferramentas` |

**Remarcação — `POST /visits/{id}/reschedule`** (`Remarcacao`: `slot_id`, `reason` obrigatório):

| Regra | Se violada | Teste |
| --- | --- | --- |
| Só visita `requested` ou `confirmed` remarca | **409** | `test_api_remarcacao.py::test_recusas_de_horario` |
| Cancela a antiga e cria a nova **numa transação só**; a antiga recebe `cancelled`, `cancellation_reason` e **`rescheduled_to`** apontando para a nova | — | `::test_remarcar_liga_a_antiga_na_nova` |
| **Humano remarcando confirmada: a nova nasce `confirmed`**; agente, ou visita que era só solicitação: a nova nasce `requested` | — | `::test_humano_remarcando_confirmada_ja_nasce_confirmada`, `::test_agente_remarca_solicitada_mas_nao_confirmada` |
| O agente **não remarca** visita confirmada | **409** | `::test_agente_remarca_solicitada_mas_nao_confirmada` |
| Slot precisa ser do mesmo imóvel, diferente do atual e no futuro | **404** / **409** | `::test_recusas_de_horario` |
| Horário novo já confirmado: **`SLOT_UNAVAILABLE` e a original fica intacta** (nem o cancelamento acontece) | **409** | `::test_horario_ja_tomado_nao_cancela_a_antiga` |

### 17.8 Encaminhamento e tarefas

| Regra | Fonte | Se violada | Teste |
| --- | --- | --- | --- |
| `POST /handoffs` cria **um** pendente por oportunidade (`handoffs_aberto_uk`) e passa o atendimento para `human_pending`; segundo pedido devolve o existente (200) | `routers/handoffs_rt.py` | — | `test_api_funil.py::test_segundo_pedido_de_encaminhamento_nao_cria_segunda_fila` |
| `assignee_id` opcional, mas precisa ser corretor **ativo** | idem | **409** | `::test_encaminhamento_pode_nomear_o_corretor`, `::test_encaminhamento_recusa_destinatario_que_nao_atende` |
| Aceitar/resolver são humanas; **resolver exige `return_to`** (`agent` ou `human`) — resolver não devolve ao agente sozinho | idem | **403** / **409** | `::test_resolver_exige_dizer_para_quem_volta_o_atendimento`, `::test_agente_nao_aceita_encaminhamento` |
| Tarefa `follow_up` para contato `blocked` é recusada; `internal` passa | `routers/tarefas_rt.py` | **409** `CONTACT_BLOCKED` | `::test_follow_up_para_contato_bloqueado_e_409` |

---

## 18. A ponte Mora → CRM

Fonte: `shared/sdr_shared/crm/`. Três compromissos do publicador: **não derruba o turno**, **não
inventa**, **repetir é seguro**.

| Regra | Fonte | Se violada | Teste |
| --- | --- | --- | --- |
| Publicação acontece **no fim do turno, depois de responder ao cliente** ([D-12](../decisions.md)); toda falha vira log, nunca exceção | `handler.py`, `crm/publicador.py::publicar_turno` | — | `shared/tests/test_crm_ponte.py::test_crm_fora_do_ar_nao_derruba_o_turno`, `::test_token_errado_nao_derruba_o_turno`, `::test_sem_configuracao_e_no_op` |
| Oportunidade só é aberta quando a intenção está clara (`PROPOSITO`: aluguel → `rent`, compra e investimento → `buy`) | `crm/traducao.py`, `publicador.py::_abrir` | — | `::test_intencao_indefinida_nao_vira_oportunidade`, `::test_intencao_indefinida_nao_abre_nada_no_crm` |
| Um lead da Mora vira **cliente + oportunidade + preferências + interações** | `publicador.py::_publicar` | — | `::test_turno_cria_cliente_oportunidade_preferencias_e_historico` |
| `external_contact_id = mora-<lead_id>` sempre preenchido (chat anônimo não tem e-mail nem telefone) | `traducao.py::identificadores` | CRM recusaria a criação | idem |
| **Estágio sobe um passo por vez** (`in_service`, `qualified`); recusa `INVALID_TRANSITION` é ignorada | `publicador.py::_mover` | — | `::test_qualificacao_avanca_passo_a_passo_no_crm` |
| **O agente só move até `qualified`** (`ESTAGIO_QUALIFICADO`); `agendado → qualified`; `handoff` vai pelo encaminhamento; `inativo`/`frio` não mexem (seriam `lost`, decisão humana) | `traducao.py::ESTAGIO` | — | `::test_agendado_nao_vira_visit_scheduled` |
| Investidor manda `ticket` como `budget_max_cents`; aluguel usa `budget_basis = monthly_total`; reais → centavos com `round` | `traducao.py::preferencias` | oportunidade sem teto nunca qualificaria | `::test_traducao_do_cartao_para_preferencias`, `::test_investidor_usa_o_ticket_como_teto` |
| **`external_event_id`** = `mora-msg-<id da mensagem>`; sem id, hash que inclui o lead ([D-13](../decisions.md)) | `publicador.py::_evento` | duas pessoas dizendo "oi" colidiriam | `::test_republicar_o_mesmo_turno_nao_duplica_nada`, `::test_mesma_frase_de_dois_clientes_nao_colide_no_historico` |
| 412 em preferências: relê e tenta **uma** vez | `publicador.py::_atualizar_preferencias` | — | sem teste |
| **`crm_pendencias`**: turno não publicado fica na fila; o scheduler drena no laço de 30 s, lotes de 20, **backoff exponencial até 3600 s**, **`MAX_TENTATIVAS = 30`**; depois a linha fica com o erro para inspeção (nunca apagada em silêncio); lead apagado conclui a pendência | `crm/pendencias.py`, `sdr_scheduler/local_worker.py` | turno perdido enquanto o CRM esteve fora | `::test_turno_com_crm_fora_do_ar_fica_na_fila_e_e_publicado_quando_ele_volta` |
| **Reconhecimento**: antes de perguntar, a Mora procura o cliente no CRM **por contato, nunca por nome**; mais de um resultado = não reconhece; só preenche campo **vazio** do cartão; procura uma vez por marca de contato; oportunidade fechada não é contexto; `buy` na volta vira `compra` sem rebaixar `investimento` | `crm/reconhecimento.py`, `traducao.py::INTENCAO_DO_CRM` | recomeçar do zero é o custo de falhar | `shared/tests/test_reconhecimento_crm.py` (7 testes), `test_porta_crm.py::test_dois_clientes_com_o_mesmo_contato_nao_reconhecem_ninguem`, `::test_sem_contato_nao_procura` |
| Vínculo (`crm_vinculo`) mora no banco da **Mora**, com a versão da oportunidade (o `If-Match` da próxima escrita) | `crm/vinculo.py` | — | `test_interesses_crm.py::test_a_versao_guardada_acompanha` |
| CRM sem URL ou sem token conta como **desligado**; CRM fora do ar entrega sessão inerte | `shared/sdr_shared/ports/crm.py`, `adapters/crm/via_mcp.py` | — | `test_porta_crm.py::test_url_sem_token_nao_habilita`, `::test_crm_fora_do_ar_entrega_sessao_inerte` |

---

## 19. API da Mora — limites e credenciais

| Regra | Fonte | Se violada | Teste |
| --- | --- | --- | --- |
| **Corpo ≤ 256 KB** (`LIMITE_CORPO`), conferido pelo `Content-Length` antes de ler | `services/api/src/api/main.py::limitar_corpo` | **413** | `test_api.py::test_corpo_grande_e_recusado_antes_de_ler` |
| **Foto: ≤ 1,5 MB** (`MAX_BYTES`), medida pelo tamanho do base64 antes de decodificar; corpo da rota de foto até `LIMITE_CORPO_FOTO = 2_200_000`; **12 fotos por imóvel** (`MAX_FOTOS`); JPEG/PNG/WebP | `routers/imoveis.py::enviar_foto` | **413** / **409** / **422** | `test_api.py::test_foto_acima_do_teto_e_recusada_pelo_tamanho_do_base64`, `::test_fotos_imovel` |
| Reordenar exige a lista com **exatamente** as fotos atuais; a primeira é a capa | `routers/imoveis.py::reordenar_fotos` | **422** | `::test_fotos_imovel` |
| Rotas `corretor`/`operacao`/`admin` exigem `Authorization: Bearer <SDR_PAINEL_TOKEN>`; públicas: catálogo, eventos, `/fotos`, `/health` | `auth.py`, `main.py` | **401** | `::test_openapi_marca_o_que_e_publico_e_o_que_exige_credencial`, `::test_rota_protegida_sem_token_responde_401_e_nao_500` |
| Callback do Google só com `state` assinado por nós, expira, e não reflete HTML | `routers/calendario.py`, `seguranca/oauth.py` | **4xx** | `::test_callback_recusa_state_nao_assinado`, `::test_callback_do_google_nao_reflete_html`, `shared/tests/test_seguranca.py::test_oauth_state_expira` |
| CORS: `SDR_CORS_ORIGINS`; `*` só em desenvolvimento | `main.py` | — | sem teste |

---

## 20. Divergências conhecidas

Pontos onde o comportamento surpreende. São bons candidatos a teste — e alguns a correção.

1. **A vazão é estado de processo.** Com N workers, o limite efetivo é ~N×5 por rajada e ~N×60 por
   hora. O mesmo vale para o limite de **120/min por credencial** e o de **login** no CRM: contador
   em memória de uma instância.
2. **A taxa de falha da aba Saúde conta como falha tudo que não é `ok`** — inclusive `handoff`,
   `orcamento`, `reativacao` e `barramento`.
3. **`campos_faltantes()` testa `None`; o score testa "valor verdadeiro".** Com `quartos = 0` o
   cartão fica completo e o critério de quartos vale 0 ponto.
4. **`urgencia = "sem_prazo"` completa o cartão valendo zero ponto.**
5. **Ação `alertar` nunca muda o modo**, nem acima de 150%. O teto vira apenas visual.
6. **`TETO_DURO` (150%) só existe para `degradar`.** Com `bloquear`, o bloqueio é em 100%.
7. **Devolver o lead não devolve o corretor** nem reagenda o follow-up cancelado no assumir.
8. **Responder por dois canais registra uma mensagem só**, atribuída ao primeiro canal.
9. **A limpeza da auditoria da Mora cobre `dados`, não `detalhe`** — e `detalhe` recebe até 300
   caracteres do texto do modelo e até 900 de traceback.
10. **A carga do corretor conta visitas futuras sem olhar o status** (`CorretorRepository.carga`).
11. **`agendado` na Mora não é visita confirmada.** O painel da Mora mostra "agendado" quando o
    cliente reservou; o CRM só mostra `visit_scheduled` depois que um humano confirma. Os dois
    painéis discordam por desenho até a confirmação ([D-14](../decisions.md)).
12. **Foto editada no CRM não aparece enquanto houver upload do painel para o mesmo imóvel**, e a
    tela não avisa ([ADR-0015](../adr/0015-quem-manda-nas-fotos-do-imovel.md)).
13. **A configuração `agenda` do painel (slots, duração, dias úteis) é declarativa**: a grade
    interna continua 10h/14h/16h, 60 min, 5 dias úteis, fixa em `VisitaRepository.horarios_disponiveis`.
14. **A configuração `cobertura` é declarativa**: quem decide é `geo.py`.
15. **Corretor que remarca uma visita confirmada não passa por `If-Match`** — `reschedule` não
    confere versão; `transitions` confere.
16. **O pedido de visita no CRM move a oportunidade até `qualified` antes do fim do turno**
    (`crm/visitas.py::pedir_visita`), fora da ordem normal do publicador — de propósito, para o
    primeiro pedido de todo lead não ser recusado.

---

## 21. Regras removidas ou alteradas

Em relação à versão anterior deste documento. Nada foi apagado em silêncio.

| Regra anterior | Situação | Motivo |
| --- | --- | --- |
| "Roteamento: linha 8 — pede visita, ou `pediu_visita` no cartão → agendador" | **alterada** | `pediu_visita` só roteia quando o estágio **não** é `agendado`; depois da reserva, telefone enviado não reoferece a grade (`nodes/supervisor.py`). |
| "Roteamento: o modelo decide entre qualificador, consultor, agendador e handoff" | **alterada** | Entrou `informacoes`; e o modelo não pode devolver ao agendador um lead já `agendado`. |
| Não havia linha para pergunta institucional | **nova** | Nó `informacoes` (RAG institucional) antes do agendador. |
| "Visitas: horários 10h, 14h e 16h, 5 dias úteis à frente" como regra geral | **alterada** | Vale só como **reserva**; com imóvel definido a grade vem dos slots do CRM (`crm/visitas.py`). |
| "Transição qualquer → `agendado` quando visita confirmada" | **alterada** | `agendado` é **reserva** pela Mora; confirmar é humano e acontece no CRM. |
| "O que uma visita confirmada produz" (6 itens) | **alterada** | Renomeada para "o que uma reserva produz"; entrou o pedido no CRM e a regra de que falha do pedido não desfaz a reserva. |
| "Configurações: só `followup` e `modelos` valem no próximo turno" | **alterada** | `operacao` (timeout, transcrição, refresh do acervo) também vale, com cache invalidado ao salvar. |
| "Provedores: `anthropic`, `openai`, `ollama`" | **alterada** | Entrou `fallback_provider = "nenhum"` (desliga o reserva pela tela) e a recusa de reserva igual ao primário. |
| "`turnos.resultado`: seis valores" | **alterada** | Entrou `barramento`. |
| "Guardrail de saída: vazamento, CPF, cartão, telefone" | **alterada** | Entraram links markdown, URLs cruas e esquemas perigosos (`util.py::limpar_texto`). |
| "Extração: conservadora" | **alterada** | Entrou "uma extração por frase" (`cartao_extraido_de`) e a absorção de mudança de critério pelo consultor. |
| "Corretor: nome, regiões, inativo, foto" | **alterada** | Entrou `crm_user_id` e a cifra do refresh token do Google (`seguranca/cofre.py`). |
| "Autenticação do painel: token estático" | **alterada** | Entrou a regra do WebSocket: credencial no primeiro quadro, nunca na URL. |
| Seção "Reativação: canal Telegram" | **mantida** | Confirmada em `reativador.py::PREFERENCIA`. |
| Não havia seção de CRM nem de ponte Mora → CRM | **novas** | Seções 17 e 18. |
| Não havia seção de limites da API da Mora | **nova** | Seção 19 (corpo, fotos, credenciais). |
| Não havia catálogo sincronizado com o CRM | **nova** | Seção 5.5 (15 min, purga, fotos painel > CRM > arquivo). |
| Divergências 11–16 | **novas** | Descobertas nesta revisão. |

---

## 22. Onde conferir

| Assunto | Arquivo |
| --- | --- |
| Cartão, estágios, temperatura | `shared/sdr_shared/models/lead.py` |
| Score | `services/agent/src/agent/scoring.py` |
| Roteamento | `services/agent/src/agent/nodes/supervisor.py` |
| Busca e cascata | `services/agent/src/agent/tools/buscar_imoveis.py`, `shared/sdr_shared/geo.py` |
| Interesses, visitas, imóveis (Mora) | `shared/sdr_shared/db/repositories.py` |
| Corretores, métricas, reativação (funil) | `shared/sdr_shared/db/painel.py` |
| Cliente e sucessão | `shared/sdr_shared/db/clientes.py` |
| Follow-up | `shared/sdr_shared/followup.py`, `services/agent/src/agent/dispatch.py` |
| Reativação (régua e worker) | `shared/sdr_shared/reativacao.py`, `services/agent/src/agent/reativador.py` |
| Guardrails | `services/agent/src/agent/guardrails/`, `services/agent/src/agent/util.py` |
| Histórico, saltos | `services/agent/src/agent/state.py`, `services/agent/src/agent/graph.py` |
| Orçamento, modelos, operação | `shared/sdr_shared/db/governanca.py`, `shared/sdr_shared/db/modelos.py`, `shared/sdr_shared/db/operacao.py`, `shared/sdr_shared/ports/factory.py` |
| Observabilidade | `shared/sdr_shared/db/monitoramento.py` |
| Auditoria (Mora) | `shared/sdr_shared/db/auditoria.py`, `services/api/src/api/auditoria_mw.py` |
| Segurança (painel, cofre, sessão, OAuth) | `shared/sdr_shared/seguranca/` |
| API da Mora | `services/api/src/api/main.py`, `services/api/src/api/routers/` |
| Ponte Mora → CRM | `shared/sdr_shared/crm/`, `shared/sdr_shared/ports/crm.py` |
| Acervo e sincronização | `services/ingestion/sdr_ingestion/acervo.py`, `sincronia.py`, `ingest_imoveis.py` |
| CRM — funil, custos, contatos | `services/crm/sdr_crm/dominio/` |
| CRM — rotas | `services/crm/sdr_crm/api/routers/` |
| CRM — auth, protocolo, limites | `services/crm/sdr_crm/api/auth.py`, `contexto.py`, `protocolo.py`, `main.py`, `config.py` |
| CRM — banco | `services/crm/sdr_crm/db/schema.sql` |
| CRM — MCP | `services/crm/sdr_crm/mcp/ferramentas.py` |
| Painel da Mora | `apps/dashboard/src/pages/` |
| Painel do CRM | `apps/crm/src/paginas/` |
| Site | `apps/web/src/` |
| Decisões | [`docs/decisions.md`](../decisions.md), ADRs [0008](../adr/0008-portoes-de-autenticacao-proprios.md)–[0015](../adr/0015-quem-manda-nas-fotos-do-imovel.md) |
