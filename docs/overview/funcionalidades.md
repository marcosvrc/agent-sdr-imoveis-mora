---
title: Funcionalidades
description: O que o Mora faz hoje, componente por componente — com foco no agente, cada funcionalidade explicada pelo que o cliente vê, pelo código que a sustenta, pelos limites numéricos e pelo comportamento em falha.
---

# Funcionalidades

Esta página descreve o que está **implementado** no repositório. Cada bloco do agente segue o mesmo
formato: o que o cliente ou o corretor percebe, como funciona por baixo (nó, função, arquivo),
regras e limites com os números copiados do código, e o que acontece quando algo falha.

O passo a passo de uso está no [manual do agente](../user-guide/agente.md) e no
[manual do painel](../user-guide/painel.md); o detalhamento nó a nó do grafo está em
[Fluxo do agente](../architecture/fluxo-agente.md); as regras consolidadas, em
[Regras de negócio](../technical-reference/regras-de-negocio.md). Aqui a pergunta é outra:
*o que existe, e até onde vai*.

!!! info "Legenda"
    - **Concluída** — implementada e com teste ou build associado.
    - **Parcial** — escrita, mas dependente de serviço externo opcional ou desligada por padrão.
    - Quando algo não foi encontrado no código, a página diz **não localizado** em vez de supor.

---

## Agente Mora (`services/agent`)

O agente é um grafo LangGraph com um nó de entrada (`supervisor`) e nove especialistas:
`qualificador`, `consultor`, `agendador`, `followup`, `resumidor`, `handoff`, `recusa`,
`reativador` e `informacoes` (`services/agent/src/agent/graph.py`, tupla `ESPECIALISTAS`).
Todo turno começa no supervisor, vai a um especialista e volta ao supervisor, que encerra ao ver
`resposta`. O limite de saltos é `MAX_SALTOS = 4`, e um especialista que devolve sem resposta e
sem mudar de decisão encerra o turno em vez de rodar de novo (`_rotear`).

### Roteamento por regras + LLM

**O que faz.** Decide, a cada mensagem, quem responde: perguntar, recomendar, agendar, informar,
encaminhar ou recusar. O cliente não percebe o roteador; percebe que a Mora não oferece horário
para quem perguntou sobre taxa de visita.

**Como funciona.** `services/agent/src/agent/nodes/supervisor.py`. Regras determinísticas
primeiro, na ordem em que estão no arquivo; o modelo de roteamento só decide na ambiguidade.

| Ordem | Regra | Destino |
|---|---|---|
| 1 | `entrada.canal == Canal.SISTEMA` | `resumidor` |
| 2 | `TipoMensagem.FOLLOWUP` / `TipoMensagem.REATIVACAO` | `followup` / `reativador` |
| 3 | `reativador.PEDE_SAIR` casa | `reativador` (opt-out) — antes do porteiro de escopo |
| 4 | `escopo.avaliar(txt)` reprova **e** não há `PEDE_HUMANO` | `recusa` |
| 5 | botão `Falar com corretor`, `PEDE_HUMANO` ou `estagio == HANDOFF` | `handoff` |
| 6 | `pergunta_institucional(txt)` (sem `slot:` e sem grade oferecida) | `informacoes` |
| 7 | `slot:` ou (grade oferecida **e** `ESCOLHE_HORARIO`) | `agendador` |
| 8 | botão `Agendar visita`, `PEDE_VISITA`, ou `pediu_visita` com estágio ≠ `AGENDADO` | `agendador` |
| 9 | botão `Ver outros` ou `PEDE_OPCOES` | `consultor` |
| 10 | cartão completo e nada sugerido ainda | `consultor` |
| 11 | cartão incompleto | `qualificador` |
| 12 | resto (cartão completo, imóveis já sugeridos, texto livre) | LLM de roteamento |

As expressões, copiadas do arquivo:

- `PEDE_HUMANO`: `corretor|atendente|humano|pessoa de verdade|falar com alguém`
- `PEDE_VISITA`: `visitar|visita|agendar|marcar|conhecer o im[oó]vel|hor[aá]rio`
- `ESCOLHE_HORARIO`: hora (`14h`, `14:00`), dia da semana, `amanhã`, ordinal (`primeiro`… `último`) ou data `dd/mm`
- `PEDE_OPCOES`: `op[çc][õo]es|me mostra|mostrar|o que (vocês?) tem|outros? im[oó]ve(l|is)|ver outros`
- `INSTITUCIONAL_FORTE`: `fiador|avalista|caução|seguro fiança|vistoria|iptu|itbi|escritura|financiamento|documentação|documentos necessários|reajuste|rescisão|pet|cachorro|gato|animal de estimação` — basta aparecer.
- `INSTITUCIONAL_FRACO`: `taxa|prazo|entrada|contrato|comissão|garantia|multa|repasse`, **só** se houver uma marca de pergunta (`como funciona|qual|quanto|posso|pode|tem|vocês cobram…`) até 60 caracteres antes. É o que impede "apê de entrada até 300 mil" de virar pergunta sobre política.

**Regras e limites.** A saída do LLM é reduzida à primeira palavra em minúsculas e só vale se
estiver em `qualificador | consultor | agendador | handoff | informacoes`; qualquer outra coisa
vira `qualificador`. Se o modelo devolver `agendador` para um lead já em `AGENDADO`, o supervisor
troca por `consultor` (ou `qualificador`) — a regra determinística já concluiu que a mensagem
não pede visita, e o modelo não pode reoferecer a grade sobre uma visita reservada.

**Em falha.** Se o LLM de roteamento levantar exceção, o turno inteiro cai no fallback do handler
(ver [Resiliência](#resiliencia)). Não há retry específico no supervisor.

### Qualificação conversacional e cartão estruturado

**O que faz.** Conversa em linguagem natural e, por baixo, preenche um cartão de qualificação.
O cliente não vê formulário; vê perguntas uma de cada vez, e botões `Comprar / Alugar / Investir`
enquanto a intenção está indefinida.

**Como funciona.** Nó `qualificador` (`services/agent/src/agent/nodes/qualificador.py`). Duas
chamadas de modelo por turno: `_extrair` usa `llm_roteamento().with_structured_output(CartaoQualificacao)`
para atualizar o cartão a partir da mensagem; depois `llm_conversa()` escreve a resposta com o
prompt `prompts/qualificador.md`, que recebe `campos_faltantes()` e os contextos de origem,
cobertura, abertura e contato.

O modelo `CartaoQualificacao` está em `shared/sdr_shared/models/lead.py`:

| Grupo | Campos |
|---|---|
| Busca | `intencao` (`compra`, `aluguel`, `investimento`, `indefinida`), `regiao`, `bairros[]`, `preco_min`, `preco_max`, `quartos`, `tipo_imovel`, `urgencia` |
| Investidor | `perfil_investidor`, `ticket`, `retorno_esperado` |
| Contato | `nome_informado`, `telefone_informado`, `email_informado` |
| Sinais | `imoveis_visualizados[]`, `pediu_visita` |

- `OBRIGATORIOS_COMPRA_ALUGUEL = ("intencao", "regiao", "preco_max", "quartos", "urgencia")`
- `OBRIGATORIOS_INVESTIMENTO = ("intencao", "perfil_investidor", "ticket", "retorno_esperado")`
- `campos_faltantes()` escolhe a lista pela intenção e devolve os que estão `None` ou `INDEFINIDA`; `completo()` é `not campos_faltantes()`.
- `tem_contato()` é verdadeiro com telefone **ou** e-mail informado.
- Validadores `mode="before"` removem caracteres de controle e cortam texto livre em 120 caracteres (bairros: 80 cada, no máximo 20) — o cartão é interpolado em prompts, e uma quebra de linha ali viraria "instrução".

**Regras.**

- A extração só sobrescreve com valor não vazio (`None`, `[]`, `False`, `INDEFINIDA` e `0` são ignorados); `imoveis_visualizados` é união sem duplicatas.
- **Absorção de contato** (`_absorver_contato`): `nome_informado` vira `lead.nome` (80 caracteres); telefone só entra se tiver entre **10 e 13 dígitos**; e-mail em minúsculas, 120 caracteres. Só preenche campo vazio do lead. Com telefone ou e-mail novo, `ClienteRepository().vincular` tenta reconhecer a mesma pessoa vinda de outro canal e audita `cliente.reconhecido`.
- **Normalização de local** (`_normalizar_local` + `shared/sdr_shared/geo.py`): o LLM extrai o lugar como o cliente falou; quem decide bairro/região é o catálogo. `resolver()` reconhece nome exato, apelido (`itaim`, `bixiga`), ponto de referência (`faria lima`, `ibirapuera`), região (`zona sul`, `zs`), cidade atendida, cidade **fora de cobertura** (`osasco`, `guarulhos`, `alphaville`… cada uma com a região sugerida mais próxima) e erro de digitação (`get_close_matches`, corte 0,82). Sem bairro reconhecido, a frase inteira é varrida em janelas de 3, 2 e 1 palavras. O catálogo tem **18 bairros** em cinco regiões, e é da POC (São Paulo capital).
- **Fora de cobertura**: bairros e região são zerados e o prompt recebe a instrução de dizer isso em uma frase e sugerir a região mais próxima — sem prometer busca lá.
- **Nova oportunidade ao mudar de intenção** (`nova_oportunidade_se_mudou_intencao`, `shared/sdr_shared/db/clientes.py`): só quando a intenção anterior era definida, a nova é diferente, e o lead está em `AGENDADO`, `HANDOFF`, `INATIVO` ou `FRIO` (`ENCERRAVEIS`). Cria `opo_<12 hex>` em `QUALIFICANDO` com o mesmo cliente, nome e contato, cartão de busca zerado, migra o canal para a sucessora e marca `encerrado_em` e `sucessora_id` na antiga. Mudar de ideia no meio da qualificação só ajusta o cartão.
- **Apresentação só na primeira interação**: `primeira_interacao` vem do handler (lead recém-criado) e escolhe entre "apresente-se em meia frase" e "não se apresente de novo".
- **Pedido de contato** (`_contexto_contato`): só no canal web (no Telegram já há identificador). Sem nome, pede o primeiro nome "de forma leve"; com cartão completo e sem contato, pede **um** contato (telefone de preferência) explicando o motivo.
- `NOVO → QUALIFICANDO` assim que a intenção deixa de ser indefinida. Cartão que ficou completo nesta mensagem passa o turno direto ao `consultor`, com `cartao_extraido_de` preenchido para não extrair a mesma frase duas vezes.

**Em falha.** Exceção na extração devolve o cartão anterior sem interromper o turno. Saída
estruturada que vier como `dict` cru também é descartada.

### Recomendação de imóveis

**O que faz.** Mostra até três imóveis como cards (título, preço, foto, motivo), com botões
`Agendar visita / Ver outros / Falar com corretor`, e explica com honestidade de onde vieram —
do bairro pedido, de vizinhos, da região ou de outra parte da cidade.

**Como funciona.** Nó `consultor` (`nodes/consultor.py`) chama `buscar_com_contexto`
(`tools/buscar_imoveis.py`) com `limite=6`. A busca é a do ADR-0001: um embedding da consulta
(preferência do cliente + tipo + bairros, mais "para renda de aluguel" para investidor) e
`ImovelRepository.buscar_hibrido` — filtros SQL (`operacao`, `regiao`, `bairros`, `preco <= preco_max * 1.15`,
`quartos >=`) ordenados por distância cosseno. A cascata desce em `nivel`:

1. `bairro` — exatamente o pedido;
2. `vizinhos` — mesma região, os citados como referência entre si primeiro (`geo.vizinhos`);
3. `regiao` — a do local resolvido vence a do cartão;
4. `cidade` — toda a base;
5. `vazio`.

Cidade fora de cobertura pula a cascata e busca na região sugerida (`nivel = "fora_de_cobertura"`).

**Regras.**

- **Um embedding por busca** (`_vetor`), reaproveitado nas até seis consultas da cascata.
- **Já vistos e descartados** (`InteresseRepository.por_situacao`): o que está `descartado` na tabela `interesses` nunca volta; o que já foi `sugerido` (nesta sessão ou em sessões anteriores) fica para o fim, e só reaparece quando as novidades acabam (`[:3] or todos[:3]`).
- **Contexto de busca** (`_contexto_da_busca`): o nível vira uma instrução explícita no prompt — "estes são exatamente em X", "ATENÇÃO: não há no perfil pedido em X; os abaixo são de vizinhos", "não invente motivo (reserva, atualização de sistema)". O modelo só pode falar de disponibilidade com base nisso.
- **Alternativa no bairro** (`_alternativa`): quando a cascata ampliou, procura no bairro pedido relaxando primeiro `quartos`, depois `preco_max` (3 resultados), e o prompt oferece as duas primeiras como "opções fora do perfil".
- **Motivo neutralizado** (`montar_card`): a descrição do anúncio entra no card por `neutralizar_texto_externo(…, limite=200)` — defesa de injeção de segunda ordem via RAG.
- **Mudança de critério depois de qualificado** (`_absorver_mudanca`): o consultor reextrai o cartão da mensagem, mas **não** toca a intenção (isso é papel do qualificador).
- Ao mostrar cards com cartão completo, `NOVO/QUALIFICANDO → QUALIFICADO`. Os cards mostrados viram `interesses` com situação `sugerido` (best-effort).

**Em falha.** Sem embedder (`get_embedder().embed` levanta), `_vetor` devolve `None` e a busca
segue com `buscar_por_filtros` — mesmos filtros, ordem por preço crescente, sem exigir
`embedding IS NOT NULL`. Falha ao registrar interesses vira aviso no log; a resposta sai.

### Agendamento de visita

**O que faz.** Em dois turnos: oferece até oito horários como botões; ao clicar (ou escrever
"terça às 14h"), reserva o horário, avisa que **o corretor confirma**, e pede telefone se ainda não
tiver. Se o horário acabou de ser ocupado por outra pessoa, reoferece.

**Como funciona.** Nó `agendador` (`nodes/agendador.py`).

- **Oferta** (`_oferecer`): com imóvel definido e CRM configurado, os horários vêm de `horarios_do_imovel` (`shared/sdr_shared/crm/visitas.py`, MCP `imovel_por_codigo` + `horarios_livres`), e cada um guarda o `slot_id` em `slots_crm`. Sem imóvel ou com lista vazia, vale a agenda local: `VisitaRepository.horarios_disponiveis` gera slots **10h, 14h e 16h (Brasília)** nos próximos **5 dias úteis**, descontando visitas confirmadas e, com corretor definido, a agenda externa dele. Os botões saem como `slot:<iso>|<rótulo>`; o rótulo é `formatar()` (`seg 22/09 às 14h`).
- **Escolha** (`run`): `slot:` é lido direto; texto livre passa por `_resolver_horario`, que casa ordinal, hora (`14h`, `as 14`, "manhã" = 10h, horas ≤ 8 "à tarde" somam 12), dia da semana, `amanhã` e `dd/mm` — e só confirma quando sobra **um** candidato e o cliente disse pelo menos dia ou hora.
- **Reserva** (`tools/agenda.py::agendar`): revalida com `slot_livre` (contagem de visitas `confirmada` no mesmo início), grava `vis_<lead>_<timestamp>`, registra interesse `visita_marcada`, audita `visita.agendada` e notifica o corretor. Duração fixa de **60 min**.
- Se o lead não tinha corretor, ganha um por `CorretorRepository.escolher(regiao)` — a mesma regra do handoff.
- **Pedido no CRM** (`pedir_visita`): move a oportunidade a `qualified` (precondição do CRM) e chama `solicitar_visita`. A Mora **pede**; quem confirma é uma pessoa no CRM.
- O prompt `agendador_reserva.md` recebe o imóvel pelo **título do card** (`descrever_imovel`), nunca pelo código, e a instrução de pedir telefone quando `lead.telefone` e `tem_contato()` estão vazios.
- O estágio vai a `AGENDADO`, `pediu_visita = True`, a resposta leva `Acao.AGENDAR` e `dados.visita`.
- **Google Calendar** (`_registrar_no_calendario`): só quando `get_calendario()` é o adaptador Google (exige `google_client_id` e `google_client_secret`) e o corretor conectou a agenda. Estado **parcial**: opcional, e a falha não desfaz a visita.

**Regras e limites.** Grade do CRM e local limitadas a `[:8]`. O histórico guarda o rótulo do
botão, não `slot:…` em UTC (`texto_para_historico`). Pedido de hora que não existe na grade
(`pediu_hora`) gera nota para o modelo dizer isso e oferecer os do mesmo dia.

**Remarcação.** Não há nó ou regra própria no agente: "remarcar" volta ao agendador pelas regras
7 e 8 do supervisor (botão de horário ou palavra de agendamento). A remarcação em uma transação,
com a visita antiga apontando para a nova, é do CRM (`services/crm/.../routers/visitas_rt.py::remarcar`).

**Em falha.** `HorarioOcupado` reoferece com o contexto "acabou de ser ocupado". Falha do CRM
na leitura devolve lista vazia (cai na agenda local) — vazio significa "não sei", nunca "não há".
Falha em `pedir_visita` não desfaz a reserva. Falha no Google é só log.

### Handoff para corretor

**O que faz.** Passa a conversa a uma pessoa, dizendo o primeiro nome dela. A partir daí a Mora
para de responder; o corretor fala pelo painel.

**Como funciona.** Nó `handoff` (`nodes/handoff.py`). Entra por: botão `Falar com corretor`,
`PEDE_HUMANO`, estágio já em `HANDOFF`, três recusas seguidas (oferece o botão), orçamento
bloqueado ou falha do turno. `escolher_corretor` mantém o responsável atual se ativo; senão
`CorretorRepository.escolher(regiao)` (`shared/sdr_shared/db/painel.py`): corretor **ativo** que
atende a região (ou todas), com **menor carga** = leads em handoff + visitas futuras; empate por
nome. Audita `lead.encaminhado_corretor` (resultado `erro` quando não há corretor para a região) e
notifica `lead.encaminhado` com temperatura, intenção, bairros e telefone (ou "Sem telefone:
responda pelo painel").

**Depois do turno.** Com o estágio mudando para `HANDOFF`, `dispatch.publicar_eventos` cancela o
follow-up e publica `resumir`; o nó `resumidor` (`nodes/resumidor.py`) roda **fora do turno** com
`llm_analise()` e produz o briefing (`lead.resumo`, saneado) e a análise estruturada `AnaliseLead`
(sentimento, engajamento, perfil de decisão, motivadores, objeções, `como_abordar`), notificando
`briefing.pronto`. O mesmo pedido é feito ao entrar em `QUALIFICADO` e `AGENDADO`. No CRM, o
publicador chama `encaminhar` com o resumo (ou o cartão resumido) e o `crm_user_id` do corretor
quando a ponte está preenchida.

**Enquanto está em handoff.** O handler não roda o grafo: cancela follow-up, notifica
`lead.respondeu` no máximo **uma vez a cada 15 min** por lead (`chave = int(time.time()) // 900`) e
registra o turno como `handoff`.

**Em falha.** Sem corretor cadastrado, o cliente ouve "vou passar para um corretor" e o painel
mostra o lead sem responsável. Análise que falhar não derruba o briefing.

### Follow-up, reativação proativa e temperatura

**Score e temperatura** (`services/agent/src/agent/scoring.py::calcular`, determinístico, sem LLM):
intenção +15, região +10, preço ou ticket +15, quartos ou perfil +10, urgência `imediata` +25 /
`3_meses` +15 / `6_meses` +8, pediu visita +15, até 3 imóveis vistos ×3, resposta em até **5 min**
(`RESPOSTA_RAPIDA`) +5, **−10 por follow-up enviado**; limitado a 0–100. `QUENTE ≥ 60`,
`MORNO ≥ 30`, senão `FRIO`. Recalculado ao fim de todo turno no handler.

**Follow-up por temperatura** (`shared/sdr_shared/followup.py`, nó `followup`):

- Padrão `tempos_min = [120, 1440, 4320]` (2h, 24h, 72h) — o tamanho da lista é o número de tentativas; `ritmo = {quente: 0.25, morno: 1.0, frio: 2.0}` multiplica o tempo; janela `08:00–20:00` em `America/Sao_Paulo`; `dias_uteis` desligado; `MIN_DELAY = 5` min. Tudo editável no painel (chave `followup` de `configuracoes`), com cache de 60 s e migração do formato antigo (`primeiro_min`, `segundo_h`, `terceiro_h`, `maximo`).
- Fora da janela, `proximo_horario_valido` empurra para a próxima abertura (até 8 dias à frente).
- `dispatch.reagendar_followup` roda ao fim de cada turno; leads em `HANDOFF`, `FRIO` ou `AGENDADO` (`ENCERRADOS`) têm o agendamento cancelado. O scheduler entrega uma `MensagemNormalizada` de tipo `FOLLOWUP`.
- O nó escreve com o prompt `followup.md` (tentativa N de T, se é a última), incrementa `followups_enviados` e move para `INATIVO`, ou `FRIO` quando esgotou.

**Reativação proativa** (ADR-0013). Duas metades:

- **Seleção e disparo** (`services/agent/src/agent/reativador.py`, worker do tópico `imovel-novo`): lê até `MAX_LEADS = 500` leads, roda `sdr_shared.reativacao.avaliar` e enfileira no máximo `MAX_AVISOS = 20` turnos de tipo `REATIVACAO` por imóvel, só para leads com canal assíncrono (`PREFERENCIA = (Canal.TELEGRAM,)` — web fica de fora porque o widget só existe com a aba aberta).
- **Régua** (`shared/sdr_shared/reativacao.py`): `pontuar` elimina por operação, teto/piso de preço, quartos e tipo; depois soma 30 base, +40 bairro citado / +25 região / +5 fora da área, +25 (folga ≥ 10 %) ou +10 abaixo do teto, +10 tipo, +10 urgência imediata, +15 destaque para investidor. `PONTOS_MINIMOS = 60`. `elegivel` exclui oportunidade encerrada, opt-out, handoff, sem contato, imóvel já apresentado/descartado/visitado, aviso há menos de `DIAS_ENTRE_REATIVACOES = 7` e conversa há menos de `DIAS_SILENCIO = 3`. Devolve o **motivo** de cada exclusão — é o que o painel simula a seco.
- **Escrita** (nó `reativador`, `nodes/reativador.py`): prompt `reativacao.md` com os motivos em português e os dias de silêncio; botões `Quero ver / Agendar visita / Não quero mais avisos`; carimba `reativado_em`, registra interesse `sugerido` e audita `lead.reativado`. Imóvel que sumiu entre o enfileiramento e o consumo aborta sem mensagem.
- **Opt-out** (`PEDE_SAIR`: "não quero mais avisos", "me tira da lista", "descadastr", "pare de me avisar"…): tem precedência sobre o porteiro de escopo; resposta **fixa** (`CONFIRMACAO_SAIDA`), sem modelo; grava `aceita_reativacao = False` e audita `lead.optout_reativacao` com ator `cliente`.

### Perguntas institucionais

**O que faz.** Responde "vocês cobram taxa de visita?", "aceitam pet?", "como funciona o fiador?"
com base nos documentos da imobiliária, citando a fonte. Quando a base não cobre, diz que vai
confirmar e oferece o corretor — não inventa.

**Como funciona.** Nó `informacoes` (`nodes/informacoes.py`) → `tools/conhecimento.py::consultar`
→ `DocumentoRepository.buscar` sobre a tabela `documentos` (pgvector). Regras de
`shared/sdr_shared/conhecimento.py`:

- `PISO_SIMILARIDADE = 0.35` (cosseno); abaixo disso a lista volta vazia, e o nó usa o prompt `informacoes_sem_base.md` com o botão `Falar com corretor`.
- `LIMITE = 3` trechos; cada um entra no prompt com cabeçalho `### <fonte>` e passa por `neutralizar_texto_externo(…, limite=1200)`.
- **Reescrita determinística** (`reescrever_pergunta`): pergunta que depende do contexto — começa por conectivo (`e se`, `mas`, `então`…), tem anáfora (`isso`, `disso`, `nesse`…) ou tem menos de `MIN_PALAVRAS_AUTONOMA = 4` palavras — herda a última fala **do cliente** que se sustentava sozinha. Só falas humanas alimentam isso, nunca as da Mora.
- **Fusão léxica (RRF)**: implementada e **desligada** (`POR_PADRAO_COM_LEXICO = False`, liga por `SDR_RAG_LEXICO=1`); no único A/B medido, recall@3 caiu de 31,9 % para 29,8 %. Não há piso léxico, por decisão medida. Estado: **parcial**.
- A fonte citada é o título da seção do documento (`Trecho.fonte`), não o nome do arquivo.
- Cada consulta é auditada em `agente.consulta_institucional` com ids e scores dos trechos.

**Em falha.** Embedder fora do ar ou exceção na busca devolvem lista vazia — o caminho do
"vou confirmar" —, nunca invenção.

### Recusa fora de escopo e anti-injeção

**O que faz.** Mensagem sobre bitcoin, receita de bolo, código, política ou "ignore suas
instruções" recebe uma resposta fixa e educada, sem gastar modelo. Na terceira insistência, oferece
uma pessoa da equipe.

**Camadas, de fora para dentro:**

1. **Vazão por lead** (`guardrails/vazao.py`): `RAJADA_N, RAJADA_S = 5, 10` (5 mensagens em 10 s) e `HORA_N, HORA_S = 60, 3600`. Excesso não vira turno; o cliente recebe `AVISO` no máximo uma vez por minuto; audita `agente.vazao_excedida`. Estado em memória do processo, com limpeza a partir de 5 000 leads.
2. **Porteiro de escopo** (`guardrails/escopo.py::avaliar`), determinístico: normaliza (minúsculas, NFKC, tabela de **homóglifos** cirílicos/gregos → ASCII, sem acento); `LIMITE_TEXTO = 1200` caracteres → `texto_gigante`; `INJECAO` (`ignore as instruções`, `revele o system prompt`, `a partir de agora você`, `aja como`, `modo desenvolvedor`, `prompt injection`…) → `injecao`, mesmo se falar de imóvel junto; `FORA_SEMPRE` (cripto, hacking, eleição, remédio, poema/piada) → `fora_do_dominio`; `CONVERSA` (saudações, "você é um robô?") ou `DOMINIO` (vocabulário imobiliário) → segue; `FORA_DO_DOMINIO` (código, tradução, futebol, horóscopo, culinária) → recusa; **na dúvida, atende**. Leetspeak não é dobrado de propósito ("2 quartos", "apto 101").
3. **Nó `recusa`** (`nodes/recusa.py`): texto fixo por categoria (`RESPOSTAS`), contador `recusas` persistido no checkpoint, `MAX_RECUSAS = 3` → `INSISTENCIA` com botão `Falar com corretor`; audita `agente.mensagem_recusada`.
4. **Prompts blindados** (`prompts/__init__.py`): todo prompt começa por `_BLINDAGEM`; texto do cliente (`mensagem`, `conteudo`, `texto_cliente`, `transcricao`) entra em bloco `<<<CLIENTE_<16 hex>>>> … <<<FIM_CLIENTE_…>>>` com sentinela `secrets.token_hex(8)` nova a cada chamada; `nome` e `cartao` entram em envelope em linha `<<<DADO_…>>>`; marcadores forjados no valor são rebaixados (`CLIENTE_` → `cliente_`). Chave de template faltante **estoura** em vez de renderizar `{chave}` crua.
5. **Texto externo neutralizado** (`util.py::neutralizar_texto_externo`): descrição de imóvel e trechos da base perdem caracteres invisíveis (`​–‏`, ` `, ` `, `⁠–⁤`, soft-hyphen, BOM), controles ASCII, marcadores forjados, tags e blocos de código, e viram uma linha só com limite de tamanho.
6. **Saída saneada** (`guardrails/saida.py::sanear`), aplicada em todo texto gerado, inclusive no briefing: se `VAZAMENTO` casar no texto bruto ou limpo (`system prompt`, `<<<CLIENTE`, `cartão de qualificação`, `OBRIGATORIOS_…`, "fui programado para"…), a resposta inteira é trocada por `FALLBACK` e auditada como `agente.saida_barrada`; CPF e número de cartão são mascarados; `limpar_texto` remove tags, blocos ```…```, links markdown (mantém o texto) e URLs cruas (`[link removido]`) — a Mora nunca manda link em texto livre.

**Em falha.** Nenhuma dessas camadas chama modelo, então não há fallback a acionar: falham
fechadas (recusa ou texto fixo).

### Áudio e botões

**Áudio.** `tools/transcricao.py`: mensagens `voice`, `audio` e `video_note` do Telegram
(`CAMPOS_DE_AUDIO` no adaptador do canal) chegam com `telegram_file_id`; o handler manda antes um
recibo ("Recebi seu áudio, só um instante") — a menos que o motor esteja `off` —, baixa por
`getFile` + download e transcreve com **faster-whisper in-process** (`device="cpu"`,
`compute_type="int8"`, idioma `pt`, modelo `SDR_WHISPER_MODEL`), carregado uma vez por processo.
Provedor: `SDR_TRANSCRICAO_PROVIDER` = `auto` (→ `whisper_local`), `whisper_local` ou `off`; o
painel sobrepõe o `.env` (`operacao_texto("transcricao")`). A transcrição entra no prompt como texto
**não confiável** (`NAO_CONFIAVEIS` inclui `transcricao`). Em falha, o conteúdo vira
`(áudio não compreendido — peça para o cliente escrever)` e o log registra a causa. O widget web
não envia áudio (não localizado no `apps/web/src/chat`).

**Botões.** `RespostaAgente.opcoes` é neutra; o Telegram renderiza como `inline_keyboard`
(`callback_data` até 64 caracteres) e o widget web como botões; `slot:<iso>|<rótulo>` separa
identificador de rótulo. Botões fixos: `Comprar/Alugar/Investir`, `Agendar visita/Ver outros/Falar com corretor`,
`Quero ver/Agendar visita/Não quero mais avisos`.

### Memória

- **Histórico por lead**: checkpointer `PostgresSaver` com `thread_id = lead.id` (`graph.py::build_checkpointer`), serializador com os tipos do projeto registrados. O histórico é podado **no supervisor, antes de qualquer especialista**: acima de `MAX_HISTORICO = 40` mensagens, ficam as últimas `HISTORICO_APOS_PODA = 24` (`state.py::podar_historico`), em bloco, para não reescrever o checkpoint a cada turno.
- **Cartão persistido**: `LeadRepository.upsert` ao fim do turno; o durável (nome, contato, intenção, orçamento, imóveis vistos) vive no lead, não no histórico.
- **Contexto de origem**: botão do site (`imovel_origem`) vira interesse `interessado` com origem `site`; imóveis navegados na sessão web (`EventoNavegacaoRepository.imoveis_vistos`) entram em `imoveis_visualizados`.
- **Reconhecimento no CRM** (`shared/sdr_shared/crm/reconhecimento.py`): antes de perguntar, o handler procura o contato (telefone/e-mail — **nunca nome**) no CRM; se houver oportunidade aberta (`new`, `in_service`, `qualified`, `visit_scheduled`, `negotiation`), semeia **só campos vazios** do cartão e cria o vínculo. A busca é feita uma vez por marca de contato (`crm_reconhecimento`), repetida quando o cliente informa contato novo.
- **Estado de turno no checkpoint**: `imoveis_sugeridos`, `horarios_oferecidos`, `slots_crm`, `recusas` sobrevivem entre turnos.

### Espelhamento no CRM

`shared/sdr_shared/crm/publicador.py::publicar_turno`, chamado **depois** do despacho da resposta,
nunca levanta. O que sobe:

| Fato da conversa | No CRM | Regra |
|---|---|---|
| Intenção definida pela primeira vez | lead + oportunidade (`garantir_lead`, `garantir_oportunidade`) | nunca abre oportunidade para quem só disse "oi" |
| Mensagens de entrada e saída | `registrar_interacao` com `external_event_id = mora-msg-<id>` | republicar não duplica |
| Cartão | `atualizar_preferencias` com `If-Match`; em 412 relê e tenta **uma** vez | |
| Estágio | `new → in_service → qualified`, um passo por vez; `AGENDADO` também vira `qualified` | o agente **nunca** passa de `qualified` |
| Cards mostrados no turno | `publicar_interesses` (`sugerido → presented`, `interessado/visita_marcada → interested`, `descartado → rejected`) | só os do turno, não a lista cumulativa |
| Entrada em `HANDOFF` | `encaminhar` com resumo e destinatário (`crm_user_id`) | |
| Visita escolhida | `solicitar_visita` (pedido, não confirmação) | |

**Fila `crm_pendencias`** (`shared/sdr_shared/crm/pendencias.py`): turno que não publicou por
inteiro entra na fila com chave `<lead>:msg:<id>`; o scheduler drena a cada 30 s
(`drenar(limite=20)`), com backoff `30 × 2^tentativas` até `BACKOFF_MAX_S = 3600` e
`MAX_TENTATIVAS = 30`; depois disso a linha fica com o erro, para inspeção. O lead é relido do banco
na hora de republicar.

Com CRM ausente (`get_crm()` devolve `CRMAusente`), tudo isso é silencioso e a Mora atende sozinha.

### Governança de LLM

- **Modelo por papel** (`llm.py`, `shared/sdr_shared/ports/factory.py::get_chat_model`): `conversa` (temperatura 0,6), `roteamento` (0,0; também usado na extração do cartão) e `analise`. Modelo e provedor vêm do painel quando salvos lá, senão do `.env` (ADR-0010); a chave do `lru_cache` inclui a escolha do painel, então a troca vale sem reiniciar. `max_tokens=600`, `MAX_RETRIES = 1`, timeout do painel (`llm_timeout_s`) ou do `.env`.
- **Orçamento** (`shared/sdr_shared/db/governanca.py`): `LIMITES_PADRAO = orcamento_mensal_usd 50, teto_tokens_dia 1_000_000, alerta_pct 80, acao_ao_estourar "degradar"`. O modo é `degradado` (conversa e análise passam a usar o modelo de roteamento) ao estourar com `degradar`, e `bloqueado` com `bloquear` ou ao passar de `TETO_DURO = 1.5` (150 %). Em `bloqueado`, `handler._bloqueado_por_orcamento` não chama modelo: escolhe corretor, move para `HANDOFF`, audita `agente.bloqueado_por_orcamento` e responde "Vou chamar {nome} para continuar com você agora mesmo". Cache de 60 s.
- **Fallback de provedor** (`ModeloComFallback`): com `SDR_LLM_PROVIDER_FALLBACK` (ou reserva do painel), a queda do primário depois dos retries repete a chamada no reserva, traduzindo o modelo por família e papel (`_EQUIVALENTE`); preserva `with_structured_output`.
- **Registro de uso** (`shared/sdr_shared/governanca/uso.py`): callback LangChain grava em `uso_llm` lead, nó, papel, provedor, modelo, tokens (entrada, saída, cache de escrita e leitura), custo em USD (tabela de preços editável) e latência; falha de gravação nunca derruba a conversa. O nó e o lead vêm de `ctx_no`/`ctx_lead`, setados em `graph._cronometrado`.
- Provedores suportados: `anthropic`, `openai`, `ollama`; `openrouter` só para bancada (ADR-0009).

### Resiliência

- **Barramento fora**: `_barramento_responde()` faz `PING` no Redis antes de qualquer trabalho; falhando, registra o turno como `barramento` e levanta — a mensagem fica pendente no stream e é retomada quando o worker volta (`RedisBroker._retomar_pendentes`, `xautoclaim`).
- **Turno falhou** (`processar` → `except`): audita `agente.turno_falhou` com o traceback, registra `erro` em `turnos` e chama `_responder_falha`: escolhe corretor, move a `HANDOFF`, responde "Tive um problema técnico aqui… já avisei {nome}" com `Acao.HANDOFF`. Se até isso falhar, o worker tem `ao_falhar` como rede final.
- **Sem embedder**: busca de imóveis por filtros SQL; busca institucional devolve vazio.
- **Sem CRM / CRM instável**: leitura de horários devolve vazio (agenda local); publicação vai à fila; reconhecimento devolve `False`.
- **Sem Google**: `_agenda_externa` oferece a grade cheia; evento não criado é só log.
- **Lock por lead**: `RedisBroker` serializa turnos do mesmo lead com `sdr:lock:<key>`, cuja validade é derivada de `orcamento_do_turno_s()` (timeout × 2 tentativas × 2 provedores + 30 s).
- **Observabilidade do turno**: `registrar_turno` grava um INSERT por turno em `turnos` com resultado (`ok`, `reativacao`, `erro`, `vazao`, `barramento`, `handoff`, `orcamento`), duração, estágio e o caminho no grafo — inclusive nas saídas antecipadas.

### Estado, por funcionalidade

| Funcionalidade | Estado | Evidência |
|---|---|---|
| Grafo supervisor + 9 especialistas | Concluída | `tests/test_cenarios.py`, `tests/test_graph_routing.py` |
| Qualificação, cartão, contato, geo | Concluída | `tests/test_contato.py`, `tests/test_geo.py` |
| RAG híbrido com cascata e alternativa | Concluída | `tools/buscar_imoveis.py`, `test_cenarios.py` |
| Agendamento (CRM ou local) e calendário | Concluída / Google **parcial** | `tests/test_agendador_crm.py`, `tests/test_calendario.py` |
| Handoff, briefing e análise | Concluída | `tests/test_notificacoes.py`, `tests/test_sessao.py` |
| Follow-up por temperatura | Concluída | `tests/test_followup.py` |
| Reativação proativa e opt-out | Concluída | ADR-0013, `tests/test_reativacao_fluxo.py`, `shared/tests/test_reativacao.py` |
| Busca institucional com piso | Concluída | `tests/test_informacoes.py`, `shared/tests/test_conhecimento.py` |
| Fusão léxica (RRF) | **Parcial** (desligada) | `SDR_RAG_LEXICO`, `evals/README.md` |
| Guardrails, saneamento, vazão | Concluída | `tests/test_seguranca.py` (38 testes), `shared/tests/test_seguranca.py` |
| Transcrição faster-whisper | Concluída | `tests/test_transcricao.py` |
| Governança e fallback de provedor | Concluída | `tests/test_governanca.py`, `shared/tests/test_fallback_provedor.py` |
| Espelhamento no CRM e fila | Concluída | `shared/tests/test_crm_ponte.py`, `test_interesses_crm.py`, `test_visitas_crm.py`, `test_reconhecimento_crm.py` |
| Resiliência do turno | Concluída | `tests/test_resiliencia.py`, `tests/test_monitoramento_turno.py` |
| Harness de avaliação | Concluída | `services/agent/evals/`, `make eval-rag`, `tests/test_evals.py` |

---

## Site (`apps/web`)

Vitrine pública com o agente embutido (ADR-0006). Rotas em `apps/web/src/main.tsx`:

| Rota | Página | O que tem |
|---|---|---|
| `/` | `Landing.tsx` | busca hero, "como funciona", CTA do chat e do Telegram |
| `/imoveis`, `/imoveis/:operacao/:bairro` | `Imoveis.tsx` | listagem com filtros (`Filtros.tsx`), skeletons, URL amigável |
| `/imovel/:slug` | `ImovelDetalhe.tsx` | galeria, custo e simulação (`CustoESimulacao.tsx`), compartilhar, favorito, botão "falar sobre este imóvel" (vira `imovel_origem`) |
| `/imoveis/:id` | redirecionamento da ficha antiga | |
| `/favoritos` | `Favoritos.tsx` | favoritos locais |
| `/privacidade` | `Privacidade.tsx` | aviso de privacidade (`AvisoPrivacidade.tsx`) |

O chat (`apps/web/src/chat/`) tem `ChatWidget`, bolhas, `BotoesOpcoes`, `CardImovelChat` e
`CardVisita` (renderiza `dados.visita` da `Acao.AGENDAR`). Conecta por WebSocket ao canal local
(`services/channels/local/app.py`); os eventos de navegação vão à API (`routers/eventos.py`) e
viram contexto de origem do agente. PWA, SEO e acessibilidade: ADR-0012. CTA de continuidade no Telegram mantém o
histórico (ADR-0006). Build com TypeScript estrito na CI. Detalhes de uso:
[manual do site](../user-guide/site.md).

---

## Painel administrativo (`apps/dashboard`)

Telas em `apps/dashboard/src/pages/` (rotas em `main.tsx`):

| Rota | Tela | Conteúdo |
|---|---|---|
| `/login` | `Login.tsx` | sessão do painel (ADR-0008) |
| `/` | `VisaoGeral.tsx` | funil, temperatura, funil da reativação (`GET /dashboard/reativacao`, ADR-0013) |
| `/leads`, `/leads/:id` | `Leads.tsx`, `LeadDetalhe.tsx` | lista e ficha: cartão, briefing e análise, interesses (`components/Interesses.tsx`), simulação seca da reativação, interruptor `aceita_reativacao`, histórico |
| `/conversas` | `Conversas.tsx` | caixa de entrada: leads por última mensagem e transcrição ao vivo (a resposta humana em handoff — `assumir`, `responder`, `devolver` de `routers/handoff.py` — fica na ficha do lead) |
| `/imoveis` | `Imoveis.tsx` | catálogo indexado e quem se interessou por cada imóvel |
| `/corretores` | `Corretores.tsx` | cadastro, regiões, carga, conexão de agenda |
| `/governanca` | `Governanca.tsx` | tokens, custo por lead, latência, limites e preços |
| `/auditoria` | `Auditoria.tsx` | trilha de `auditoria` (ADR-0011) |
| `/saude` | `Saude.tsx` | p50/p95 da espera do cliente, resultados de turno, nós lentos, batimento dos workers (`PARADO_S = 120`), filas |
| `/configuracoes` | `Configuracoes.tsx` | modelo por papel e reserva com comparação contrafactual (`ModelosForm.tsx`, `GET /config/modelos/comparacao`, ADR-0010), cadência do follow-up com prévia, transcrição, timeout do LLM |

`/clientes` e `/agenda` redirecionam para `/leads` e `/`. Tema claro/escuro/sistema com
`SeletorTema.tsx` (ADR-0014). API por trás: `services/api/src/api/routers/` (`leads`, `dashboard`,
`governanca`, `config`, `auditoria`, `interesses`, `reativacao`, `corretores`, `calendario`,
`notificacoes`, `handoff`, `eventos`, `clientes`, `imoveis`). Uso: [manual do painel](../user-guide/painel.md).

---

## CRM da imobiliária (`services/crm`, `apps/crm`)

Sistema **à parte**, com banco próprio (`local/00-crm.sql`) e autenticação própria; o agente é
cliente dele por MCP. Desligar a integração não para a Mora.

**Serviço** (`services/crm/sdr_crm/`):

- API REST v1 com envelope padrão, idempotência por `operation_id`, ETag/`If-Match` e paginação por cursor (`api/routers/`: `leads_rt`, `oportunidades_rt`, `visitas_rt`, `imoveis_rt`, `handoffs_rt`, `tarefas_rt`, `dashboard_rt`, `autenticacao_rt`).
- Dois portões (ADR-0008): credencial de serviço por escopo para o agente e sessão humana em cookie HttpOnly.
- Servidor MCP por HTTP com **18 ferramentas** (`mcp/ferramentas.py`, 18 declarações `Ferramenta(`), também por stdio para clientes externos (`make crm-mcp`).
- Domínio: funil com transições validadas (`dominio/funil.py`), custos discriminados — custo mensal desconhecido sai marcado como incompleto (`dominio/custos.py`), deduplicação de contatos (`dominio/contatos.py`).
- Visitas: solicitar não reserva; confirmar é humano; duas confirmações no mesmo horário não coexistem (índice único parcial); remarcação em uma transação com a antiga apontando para a nova (`visitas_rt.py::remarcar`).
- Trilha de auditoria de toda escrita; seed determinístico por semente e reset com três travas (`seed/`, só em `development`/`test`, só com registros sintéticos, e `--confirm-reset`).

**Painel do CRM** (`apps/crm/src/paginas/`): `Entrar`, `Visao`, `Funil`, `Clientes`,
`LeadDetalhe`, `OportunidadeDetalhe`, `Imoveis`, `NovoImovel` (com fotos e situação
`reserved`/`unavailable` reversível), `AgendaImovel` (horários de visita do imóvel), `Visitas`,
`Encaminhamentos` e `Auditoria` (só admin). Faixa permanente de dados sintéticos em toda tela.
Identidade visual distinta da Mora, com tema claro/escuro. Uso: [manual do CRM](../user-guide/crm.md).

**Acervo**: quando o CRM está configurado, o catálogo da Mora vem dele, com reindexação
incremental e purga só a partir de leitura completa (ADR-0015, `sdr_ingestion/acervo.py`,
`sdr_ingestion/sincronia.py`); `ImovelRepository.apagar_fora_de` recusa lista vazia.

---

## Operação

- **Compose** (`local/docker-compose.yml`): `db` (Postgres + pgvector), `db-init` (schemas antes de tudo), `redis` (Streams + locks), `ollama` (opcional), `agent`, `resumidor`, `reativador`, `channels` (WebSocket do site), `telegram-in` (long polling, ADR-0007) e `telegram-out`, `scheduler`, `api`, `crm-api`, `crm-mcp`, `crm-mcp-stdio`, `crm-web`, `web`, `dashboard`, `langfuse` (opcional). Perfis e variáveis: [Docker](../getting-started/docker.md) e [Configuração](../getting-started/configuracao.md).
- **Preparação e seed** (`Makefile`): `make preparar` (migrações da Mora e do CRM, espera do `crm-api`, reset do CRM), `make seed` (imóveis sintéticos, `scripts/gerar_imoveis.py`), `make crm-seed`/`crm-reset`/`crm-token`, `make docs-kb` (documentos institucionais para `documentos`), `make whisper-aquecer` (baixa o modelo de transcrição antes da demonstração), `make check-env` (`scripts/check_env.py`).
- **Saúde e observabilidade** (ADR-0011, `shared/sdr_shared/db/monitoramento.py`): batimento de cada worker a cada `BATIMENTO_S = 30`, tabela `turnos` com retenção `RETENCAO_DIAS = 7`, tela `/saude` do painel; logs JSON fora do ambiente local (`sdr_shared/log.py`). Detalhes em [Observabilidade](../quality/observabilidade.md).
- **Auditoria**: `auditar(...)` em toda ação relevante do agente (`lead.estagio_alterado`, `lead.contato_capturado`, `visita.agendada`, `agente.mensagem_recusada`, `agente.saida_barrada`, `agente.turno_falhou`, `lead.reativado`, `reativacao.anunciada`…), consultável no painel e na API (`routers/auditoria.py`); o CRM tem trilha própria.
- **Testes**: `make test` cria os bancos de teste e aplica os dois schemas; suítes em `services/agent/tests/` (18 arquivos), `shared/tests/`, `services/api/tests/`, `services/crm/tests/`, canais e scheduler; `make cobertura`, `make lint` (ruff), `make tipos` (pyright básico); harness de avaliação em `services/agent/evals/` (`make eval-fake` sem token, `make eval-rag` com embedder real). Ver [Testes](../quality/testes.md).
- **CI** (`.github/workflows/ci.yml`): ruff, pyright, testes com cobertura, `make eval-fake`, verificação de que `docs/assets/openapi.json` está em dia (`scripts/gerar_openapi.py --verificar`), build e eslint dos três front-ends; `docs.yml` publica este portal.
- **Segredos**: `scripts/checar_segredos.py`; cofre e OAuth em `shared/sdr_shared/seguranca/`. Ver [Segurança](../quality/seguranca.md).

Para o que **não** está pronto e os débitos técnicos, veja [Roadmap e limitações](../project/roadmap.md)
e [Pendências](../project/pendencias.md).
