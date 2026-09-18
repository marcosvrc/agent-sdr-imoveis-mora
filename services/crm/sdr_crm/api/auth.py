"""Identidades, scopes e sessão (seção 4).

A regra que organiza o arquivo inteiro: **scope não é autorização**. O scope diz o que aquela
credencial pode *pedir*; o papel diz o que aquele ator pode *fazer*. O agente tem
`opportunities:write` e ainda assim não marca uma venda como ganha — quem recusa isso é o papel, e
a checagem mora no domínio (`funil.SOMENTE_HUMANO`), não aqui.

Dois tipos de ator, com propósitos diferentes:

* **serviço** — o backend do agente. Token aleatório, guardado só como hash, com scopes, expiração
  e revogação. O token aparece uma única vez, na criação; o banco nunca vê o segredo.
* **humano** — corretor ou administrador. Senha com Argon2id e sessão revogável em cookie
  HttpOnly. Nunca reutilizar credencial administrativa no MCP.
"""
import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from ..erros import NaoAutenticado, SemPermissao

SCOPES = frozenset({"crm:read", "leads:write", "opportunities:write", "interactions:write",
                    "visits:request", "tasks:write", "handoffs:write"})

# O que cada papel humano pode. Corretor vê tudo da imobiliária (laboratório de uma única
# imobiliária, seção 4) e opera o funil; leitor só lê e não enxerga auditoria.
POR_PAPEL: dict[str, frozenset[str]] = {
    "admin": SCOPES | {"admin"},
    "broker": SCOPES,
    "reader": frozenset({"crm:read"}),
}

_hasher = PasswordHasher()


def hash_token(token: str) -> str:
    """SHA-256 e não Argon2 de propósito: o token é aleatório de 256 bits, não uma senha escolhida
    por gente. Não há dicionário para atacar, e o custo do Argon2 seria pago em TODA requisição do
    agente — que é o cliente mais frequente do sistema."""
    return hashlib.sha256(token.encode()).hexdigest()


def novo_token(prefixo: str = "crm") -> tuple[str, str]:
    """Devolve (token em claro, hash). O claro só existe neste retorno."""
    token = f"{prefixo}_{secrets.token_urlsafe(32)}"
    return token, hash_token(token)


def hash_senha(senha: str) -> str:
    return _hasher.hash(senha)


def conferir_senha(hash_guardado: str | None, senha: str) -> bool:
    if not hash_guardado:
        return False
    try:
        return _hasher.verify(hash_guardado, senha)
    except VerifyMismatchError:
        return False
    except Exception:
        # Hash corrompido ou de outro algoritmo: nega o acesso em vez de estourar 500 — e não conta
        # ao cliente qual dos dois foi.
        return False


@dataclass(frozen=True)
class Ator:
    """Quem está chamando. Vai para a auditoria exatamente como está aqui."""

    tipo: str                       # 'user' | 'service'
    id: str | None
    nome: str
    scopes: frozenset[str] = field(default_factory=frozenset)
    papel: str | None = None        # só para 'user'

    @property
    def humano(self) -> bool:
        """Confirmar visita, marcar ganho/perdido, reabrir e assumir encaminhamento são ações
        humanas (seção 4). `reader` não conta: ele não age."""
        return self.tipo == "user" and self.papel in {"admin", "broker"}

    @property
    def admin(self) -> bool:
        return self.papel == "admin"

    def exigir(self, *scopes: str) -> None:
        faltando = [s for s in scopes if s not in self.scopes]
        if faltando:
            raise SemPermissao("Credencial sem permissão para esta operação.",
                               missing_scopes=faltando)

    def exigir_humano(self, acao: str) -> None:
        if not self.humano:
            raise SemPermissao(f"'{acao}' é ação humana: exige corretor ou administrador.")


def ator_de_credencial(linha: dict | None) -> Ator:
    """Valida a credencial de serviço já buscada pelo hash do token.

    Expiração e revogação são conferidas AQUI, e não na consulta SQL, para que a mensagem possa
    dizer qual dos dois aconteceu — "expirou" e "foi revogada" levam a ações diferentes de quem
    opera o agente.
    """
    if linha is None:
        raise NaoAutenticado("Credencial inválida.")
    agora = datetime.now(UTC)
    if linha.get("revoked_at") is not None:
        raise NaoAutenticado("Credencial revogada.")
    if linha.get("expires_at") is not None and linha["expires_at"] <= agora:
        raise NaoAutenticado("Credencial expirada.")
    scopes = frozenset(linha.get("scopes") or [])
    desconhecidos = scopes - SCOPES
    if desconhecidos:
        # Scope que não existe mais no código é um erro de configuração, não uma permissão a
        # conceder por engano. Ignorar em silêncio esconderia a credencial desatualizada.
        scopes = scopes & SCOPES
    return Ator(tipo="service", id=str(linha["id"]), nome=linha["name"], scopes=scopes)


def ator_de_sessao(linha: dict | None) -> Ator:
    """Valida a sessão humana já buscada pelo hash do cookie."""
    if linha is None:
        raise NaoAutenticado("Sessão inválida.")
    agora = datetime.now(UTC)
    if linha.get("revoked_at") is not None:
        raise NaoAutenticado("Sessão encerrada.")
    if linha["expires_at"] <= agora:
        raise NaoAutenticado("Sessão expirada.")
    if not linha.get("active", True):
        raise NaoAutenticado("Usuário inativo.")
    papel = linha["role"]
    return Ator(tipo="user", id=str(linha["user_id"]), nome=linha["name"],
                scopes=POR_PAPEL.get(papel, frozenset()), papel=papel)
