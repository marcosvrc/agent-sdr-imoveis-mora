"""Normalização e deduplicação de contato (seção 5).

Duas decisões que valem ser ditas em voz alta:

1. **Não aplicamos regras de provedor.** `a.b+x@gmail.com` e `ab@gmail.com` são o mesmo endereço no
   Gmail, e não são em muitos outros servidores. Adotar a regra do Gmail para todo mundo funde dois
   clientes distintos — e fusão de histórico comercial não tem desfazer.
2. **Nome não deduplica.** Há mais de um "João Silva" em qualquer base real. Nome entra em busca,
   nunca em identidade.
"""
import re

E164 = re.compile(r"^\+[1-9]\d{7,14}$")
SO_DIGITOS = re.compile(r"\D")


def normalizar_email(valor: str | None) -> str | None:
    """Apenas `trim` e caixa baixa — o que é seguro para qualquer provedor."""
    if valor is None:
        return None
    v = valor.strip().lower()
    return v or None


def normalizar_telefone(valor: str | None, *, ddi_padrao: str = "55") -> str | None:
    """Converte para E.164. Devolve `None` quando não dá para afirmar o número.

    Um telefone brasileiro escrito como `(11) 99999-0000` vira `+5511999990000`. O que NÃO fazemos
    é adivinhar o DDI de um número curto demais ou longo demais: guardar um telefone errado é pior
    do que não guardar nenhum, porque ele passa a valer como identificador na deduplicação.
    """
    if valor is None:
        return None
    v = valor.strip()
    if not v:
        return None
    if v.startswith("+"):
        return v if E164.match(v) else None
    digitos = SO_DIGITOS.sub("", v)
    if not digitos:
        return None
    if len(digitos) in (10, 11):            # DDD + número, sem país
        digitos = ddi_padrao + digitos
    candidato = "+" + digitos
    return candidato if E164.match(candidato) else None


def identificadores(dados: dict) -> dict[str, str]:
    """Os identificadores presentes, já normalizados. Chave = coluna do banco."""
    saida: dict[str, str] = {}
    if email := normalizar_email(dados.get("email")):
        saida["email"] = email
    if telefone := normalizar_telefone(dados.get("phone_e164")):
        saida["phone_e164"] = telefone
    if ext := (dados.get("external_contact_id") or "").strip():
        saida["external_contact_id"] = ext
    return saida
