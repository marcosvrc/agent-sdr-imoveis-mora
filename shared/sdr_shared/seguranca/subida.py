"""Conferências de segurança na subida de cada processo.

Chamado por `sdr_shared.log.configurar(servico)`, que todo ponto de entrada (api, channels, agent,
reativador, scheduler) já chama uma vez ao subir. Ficou ali, e não em cada `main`, porque é o único
gancho comum a todos — inclusive ao canal web, cujo arquivo não importa nada mais cedo.
"""
import logging

from . import painel
from .chaves import SegredoDeExemplo, segredo_configurado

log = logging.getLogger("seguranca")

# Serviços que aceitam a credencial do painel: só neles o `dev-token` abre alguma porta.
USAM_PAINEL = {"api", "channels"}


def verificar(servico: str) -> None:
    """Recusa subir com o SDR_SESSAO_SECRET de exemplo; avisa quando o `dev-token` está valendo."""
    try:
        segredo_configurado()
    except SegredoDeExemplo as e:
        # Subir assim é assinar a sessão do chat e cifrar a agenda com uma chave publicada no
        # repositório. Melhor o container sair com a instrução do que rodar "funcionando".
        log.critical(str(e))
        raise SystemExit(f"[{servico}] {e}") from None
    if servico in USAM_PAINEL and painel.esperado() == painel.TOKEN_DEV:
        log.warning("SDR_PAINEL_TOKEN vazio com SDR_PROFILE=local: o token público `dev-token` dá "
                    "acesso ao painel (todas as conversas e dados dos leads). Só aceitável com as "
                    "portas presas a 127.0.0.1; para expor este ambiente, defina SDR_PAINEL_TOKEN.")
