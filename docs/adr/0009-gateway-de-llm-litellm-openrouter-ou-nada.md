# ADR-0009 — Gateway de LLM: LiteLLM, OpenRouter ou a camada própria

**Status:** aceito · **Data:** 2026-09-12

## Contexto
A pergunta era se vale adotar um gateway de LLM — LiteLLM ou OpenRouter — para ter "uma camada
controlando o uso da IA". A resposta depende de reconhecer que essa camada **já existe** aqui, feita
à mão e acoplada ao negócio:

- `ports/factory.get_chat_model()` é o ponto único: escolhe o provedor (Bedrock, Anthropic, Ollama),
  traduz o ID do modelo entre eles (`normalizar_modelo` — no Bedrock é `anthropic.claude-sonnet-4-5`,
  na API da Anthropic é `claude-sonnet-4-5`), aplica timeout e retry e pluga o Guardrail do Bedrock.
- `governanca/uso.py` registra **toda** chamada — tokens de entrada/saída/cache, custo, latência,
  erro, modelo — etiquetada por lead, por nó do grafo e por papel.
- `db/governanca.estado_do_orcamento()` impõe teto mensal em dólar e teto diário de tokens.

O ponto decisivo é o que acontece ao estourar o teto. Gateway sabe **recusar** a chamada. Esta
camada sabe **degradar** (Sonnet → Haiku e segue atendendo) ou **bloquear e encaminhar o lead a um
corretor humano**. Isso é regra de negócio, não de infraestrutura: continuaria nossa em qualquer
cenário, e é a parte que mais valeria terceirizar se desse — e não dá.

O buraco real era outro: existia retry dentro do provedor, não existia **troca de provedor** quando
um cai. Um turno perdido nesse caso vira mensagem de desculpa para o cliente.

## Decisão
**Não adotar gateway. Fechar o buraco do fallback dentro da camada que já existe.**

`get_chat_model` passou a montar, opcionalmente, um provedor reserva (`SDR_LLM_PROVIDER_FALLBACK`):
tenta o primário e, se ele falhar depois dos próprios retries, repete no reserva. Vazio = comportamento
de hoje, sem mudança. Foram ~40 linhas, porque a parte chata — traduzir o ID do modelo entre
provedores — já estava resolvida.

Detalhe de implementação que não era óbvio: não dá para usar `Runnable.with_fallbacks` do LangChain,
porque ele devolve um `Runnable` sem `with_structured_output`, e a extração do cartão
(`qualificador._extrair`) depende exatamente disso — metade das chamadas de LLM do sistema. Daí o
wrapper `ModeloComFallback`, que preserva a interface. O `RegistradorUso` também passou a receber
qual provedor atendeu: sem isso, uma chamada servida pelo reserva seria contabilizada no nome do
primário e o painel de Governança mostraria número errado.

## Por que não o LiteLLM
As features que interessam (fallback entre provedores, cache, custo unificado) vivem no **Proxy**,
não no SDK — o SDK entrega abstração de provedor, que já temos. E o Proxy é um serviço sempre ligado,
com Postgres e Redis próprios, no caminho de toda chamada:

- No perfil `aws` tudo é Lambda; o proxy vira ECS/Fargate permanente, custo fixo e ponto único de
  falha na frente de cada conversa — contra a postura serverless das ADR-0002 e 0004.
- No perfil local, é mais um container com banco e cache logo depois de termos removido sete
  containers de observabilidade (ADR-0005) porque a máquina de desenvolvimento não aguentava.
- Segurança: em 2026 o projeto teve a conta PyPI de um mantenedor comprometida (v1.82.7/1.82.8
  publicaram um ladrão de credenciais que exfiltrava variáveis de ambiente e credenciais de nuvem),
  além do CVE-2026-42208 (SQL injection **não autenticado** no caminho de validação do header
  `Authorization: Bearer`), bypass de autenticação por Host header e command injection via MCP SDK.
  A resposta deles foi madura, mas isso é um componente no caminho de dados de toda conversa de
  cliente, no mesmo dia em que a ADR-0008 fechou um WebSocket que vazava essas conversas.
- Manutenção: lançam uma minor por semana e suportam só as quatro linhas mais recentes — cerca de um
  mês por linha. Adotar é assinar uma esteira de atualização mensal; congelar o projeto depois da
  entrega significaria rodar versão fora de suporte com esse histórico.

## Por que não o OpenRouter (em produção)
Ele resolve a objeção de infraestrutura — é hospedado, não há nada para operar, funciona de dentro
de uma Lambda, e fallback é a feature principal. Os preços de token passam sem markup; a cobrança é
~5,5% na compra de créditos. Mesmo assim:

- **PII de cliente sairia da nossa fronteira.** Toda conversa — nome, telefone, orçamento — passaria
  por um terceiro. O opt-out de treinamento que eles oferecem vale para os *provedores*: a
  documentação diz que a configuração "não tem relação com as políticas do próprio OpenRouter e com
  o que fazemos com seus prompts". Para LGPD isso é contrato e mais um operador a documentar, não um
  toggle. Hoje, com Bedrock, o dado não sai da conta AWS.
- **Mudança de controle recente:** a Stripe fechou a compra do OpenRouter por mais de US$ 7 bi em
  agosto de 2026. Termos comerciais e política de dados de empresa recém-adquirida são exatamente o
  que se renegocia; assumir esse risco no meio do projeto não se paga.
- Sair do Bedrock custaria a integração com o Guardrail (`guardrail_id`, já ligada) e enfraqueceria a
  tese cloud-native AWS das ADR-0001 e 0002.

**Mas ele entra como bancada.** `_construir` aceita `provider="openrouter"` (dependência opcional,
import tardio) para o harness de `evals/` comparar modelos alternativos sobre os datasets sintéticos.
Ali os dados são casos de teste, não PII, o que anula a objeção — e responder "por que Claude e não
outro?" com número medido vale mais que opinião.

## Consequências
- (+) Queda de provedor deixa de virar turno perdido, sem serviço novo, sem banco novo e sem
  superfície de ataque nova.
- (+) A governança continua sabendo quem atendeu de verdade, então o custo por provedor no painel
  segue confiável mesmo com fallback ativo.
- (+) Trocar de provedor ou adicionar um novo agora é uma função (`_construir`) — se um dia um
  gateway fizer sentido, ele entra como mais um `provider` sem tocar nos nós do grafo.
- (−) Não temos cache de LLM nem chaves virtuais por time. Nenhum dos dois é necessário hoje: as
  conversas são únicas (cache renderia pouco) e a operação é de um escritório só.
- (−) O fallback dobra a latência do pior caso (timeout do primário + chamada ao reserva). Aceitável
  porque só ocorre quando o primário já falhou, e o widget espera 60s (ver ChatWidget).

## Quando revisitar
Gateway volta à mesa se: precisarmos de mais provedores do que conseguimos manter à mão; aparecerem
times ou clientes distintos exigindo chaves e orçamentos separados; ou alguém não-engenheiro precisar
mudar roteamento sem deploy. Se entrar, que seja pela imagem Docker (foi o caminho protegido no
incidente de cadeia de suprimentos), pinado numa linha suportada e sem exposição à internet.

## Atualização — OpenAI como reserva (2026-09)

O `SDR_LLM_PROVIDER_FALLBACK` existia mas ninguém tinha configurado: na prática, a queda do provedor
primário virava mensagem de desculpa e encaminhamento ao corretor, em todos os turnos. A OpenAI entra
como reserva de **produção** — e é diferente do OpenRouter recusado acima: aqui não há intermediário,
é o próprio fornecedor do modelo. O `check_env.py` passou a avisar quando não há reserva configurado.

Isso obrigou a resolver uma coisa que a decisão original não previa: **o reserva pode ser de outra
família**. `_construir(reserva, model, …)` recebe o mesmo ID do primário, e isso só funcionava entre
Anthropic e Bedrock, que servem o mesmo modelo com prefixo diferente. Mandar `claude-sonnet-4-5` para
a OpenAI devolveria 404 — o reserva falharia exatamente no momento em que existe para servir. Daí a
tabela `_EQUIVALENTE`, que troca o modelo pelo par **do mesmo papel**: conversa ↔ modelo bom,
roteamento ↔ modelo barato. A tradução é nos dois sentidos, porque quem escolher OpenAI como primário
precisa do mesmo cuidado na volta.

Duas consequências que valem registro:

- **Preço é parte do provedor, não detalhe.** Modelo fora de `PRECOS_PADRAO` é registrado com custo
  zero: o painel mostraria gasto menor que o real e a degradação por orçamento nunca dispararia —
  justamente no caminho em que ninguém está olhando na hora. Um teste garante que todo modelo da
  tabela de equivalência tem preço.
- **Mais um operador recebe dado de cliente** (nome, telefone, o que a pessoa procura). A página de
  privacidade fala em "provedores de tecnologia que processam a conversa" sem nomear ninguém — o que
  é verdadeiro, mas genérico. Nomear os subprocessadores continua **pendente**, junto com os demais
  dados institucionais que ainda são placeholder (CRECI, CNPJ, endereço): a lista real depende de
  quais provedores a imobiliária de fato contratar, e inventá-la agora seria pior que a omissão.
- Embeddings continuam fora: os da OpenAI têm 1536 dimensões e a coluna é `vector(1024)`; trocar
  exigiria migração e reingestão do catálogo inteiro.
