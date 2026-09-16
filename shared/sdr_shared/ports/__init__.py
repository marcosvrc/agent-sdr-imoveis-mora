"""Portas (interfaces) do que muda entre perfis. Serviços dependem só daqui; adapters/ implementam."""
from .broker import Broker
from .scheduler import FollowupScheduler
from .embeddings import Embedder
from .calendario import Calendario
from .factory import get_broker, get_scheduler, get_embedder, get_chat_model, modo_do_agente, get_calendario
