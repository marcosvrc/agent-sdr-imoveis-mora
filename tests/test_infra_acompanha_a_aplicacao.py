"""A infraestrutura precisa acompanhar a aplicação.

O `api_stack.py` publicava cinco prefixos de rota enquanto o `main.py` já montava catorze: no perfil
aws, metade do painel batia em rota inexistente. Ninguém percebeu porque nada compara os dois — a CI
roda `cdk synth`, que só verifica se o CDK compila, não se ele expõe o sistema.

Estes testes leem os dois arquivos como TEXTO, de propósito: importar o CDK exigiria a stack inteira
instalada e transformaria um teste de segundos numa dependência pesada. O que se quer garantir aqui
é acoplamento de lista, e para isso ler o fonte basta.
"""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MAIN = (RAIZ / "services/api/src/api/main.py").read_text(encoding="utf-8")
API_STACK = (RAIZ / "infra/stacks/api_stack.py").read_text(encoding="utf-8")
CHANNELS_STACK = (RAIZ / "infra/stacks/channels_stack.py").read_text(encoding="utf-8")
MESSAGING_STACK = (RAIZ / "infra/stacks/messaging_stack.py").read_text(encoding="utf-8")
AGENT_STACK = (RAIZ / "infra/stacks/agent_stack.py").read_text(encoding="utf-8")
COMPOSE = (RAIZ / "local/docker-compose.yml").read_text(encoding="utf-8")


def prefixos_da_aplicacao() -> set[str]:
    return set(re.findall(r'include_router\([^)]*prefix="(/[a-z]+)"', MAIN))


def prefixos_da_stack() -> set[str]:
    """Tudo entre aspas nas tuplas PUBLICAS e PROTEGIDAS, mais as rotas soltas."""
    listas = re.findall(r"(?:PUBLICAS|PROTEGIDAS)\s*=\s*\(([^)]*)\)", API_STACK, re.S)
    prefixos = {p for bloco in listas for p in re.findall(r'"(/[a-z]+)"', bloco)}
    prefixos |= {p.rsplit("/", 1)[0] or "/" for p in re.findall(r'add_routes\(path="(/[^"]+)"', API_STACK)}
    return prefixos


def test_toda_rota_da_api_existe_no_api_gateway():
    faltando = prefixos_da_aplicacao() - prefixos_da_stack()
    assert not faltando, (
        f"routers montados no main.py sem rota no api_stack.py: {sorted(faltando)}. "
        "No perfil aws essas chamadas voltariam 404 — inclua o prefixo em PUBLICAS ou PROTEGIDAS.")


def test_a_stack_nao_publica_rota_que_a_api_nao_tem():
    sobrando = prefixos_da_stack() - prefixos_da_aplicacao() - {"/health", "/fotos", "/calendario"}
    assert not sobrando, f"api_stack.py expõe prefixos que o main.py não monta: {sorted(sobrando)}"


def test_o_callback_do_google_continua_publico():
    """Se ele cair atrás do autorizador, conectar a agenda para de funcionar em produção — e o
    sintoma é um 401 no meio do fluxo do Google, difícil de ligar à causa."""
    assert 'add_routes(path="/calendario/callback"' in API_STACK
    assert "authorizer" not in API_STACK.split('path="/calendario/callback"')[1].split("\n")[0]


def test_telegram_e_o_canal_provisionado_por_padrao():
    """ADR-0007 trocou WhatsApp por Telegram. A stack provisionava só WhatsApp."""
    assert "TgInbound" in CHANNELS_STACK and "TgOutbound" in CHANNELS_STACK
    assert '"telegram"' in MESSAGING_STACK, "sem fila de saída, o outbound do Telegram não tem de onde consumir"
    # WhatsApp continua no repositório, mas atrás de um interruptor explícito.
    posicao_wa = CHANNELS_STACK.find("WaInbound")
    assert posicao_wa > 0 and 'try_get_context("whatsapp")' in CHANNELS_STACK[:posicao_wa]


def test_todo_worker_do_agente_existe_nos_dois_perfis():
    """Um worker que só existe no compose funciona na demo e não na AWS; um que só existe na stack
    funciona na AWS e some da demo. O erro é silencioso dos dois lados — nada quebra, a fila
    simplesmente não é consumida —, então a lista é comparada aqui.
    """
    workers = {"agent.handler": "AgentFn", "agent.eventos": "ResumirFn", "agent.reativador": "ReativadorFn"}
    for modulo, construct in workers.items():
        assert f"from {modulo} import local_worker" in COMPOSE, f"{modulo} sem serviço no compose local"
        assert construct in AGENT_STACK, f"{modulo} sem Lambda no agent_stack.py"


def test_o_reativador_tem_fila_e_consegue_devolver_o_turno():
    """Ele consome `imovel-novo` e publica na `inbound`: sem a permissão de escrita, o aviso é
    selecionado, registrado no log e nunca chega a ninguém."""
    assert "sdr-imovel-novo.fifo" in MESSAGING_STACK
    assert "queues.imovel_novo" in AGENT_STACK
    assert "queues.inbound.grant_send_messages(reativador_fn)" in AGENT_STACK
