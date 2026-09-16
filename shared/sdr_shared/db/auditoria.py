"""Auditoria: quem fez o quê, quando, sobre qual registro e o que mudou.

Serve a três perguntas que aparecem em qualquer operação real: por que este lead mudou de estágio,
quem alterou esta configuração, e quem exportou dados pessoais. Registrar é barato; descobrir depois,
sem registro, é impossível. Falha ao auditar nunca derruba a operação auditada.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from .connection import get_pool

log = logging.getLogger(__name__)

# Ações que tocam dado pessoal — destacadas na tela e relevantes para LGPD.
SENSIVEIS = {"lead.exportado_crm", "lead.listado", "lead.consultado", "corretor.removido",
             "lead.contato_alterado", "auditoria.exportada", "lead.contato_capturado"}


def _conn():
    return get_pool().connection()


def _limpar(valor: Any, _nivel: int = 0) -> Any:
    """Nunca guarda segredo nem payload gigante no registro de auditoria."""
    PROIBIDOS = ("senha", "password", "token", "secret", "authorization", "api_key", "imagem", "foto", "embedding")
    if _nivel > 4:
        return "…"
    if isinstance(valor, dict):
        return {k: ("[omitido]" if any(p in k.lower() for p in PROIBIDOS) else _limpar(v, _nivel + 1))
                for k, v in valor.items() if v is not None}       # chave nula é ruído no detalhe
    if isinstance(valor, (list, tuple)):
        return [_limpar(v, _nivel + 1) for v in valor[:20]]
    if isinstance(valor, str) and len(valor) > 500:
        return valor[:500] + "…"
    return valor


class AuditoriaRepository:
    COLS = "id, em, ator_tipo, ator_id, ator_nome, acao, entidade, entidade_id, dados, origem, resultado, detalhe"

    def registrar(self, *, acao: str, entidade: str, entidade_id: str | None = None,
                  ator_tipo: str = "sistema", ator_id: str | None = None, ator_nome: str | None = None,
                  dados: dict | None = None, origem: str | None = None,
                  resultado: str = "ok", detalhe: str | None = None) -> None:
        try:
            with _conn() as c:
                c.execute("""INSERT INTO auditoria (ator_tipo, ator_id, ator_nome, acao, entidade, entidade_id,
                                                    dados, origem, resultado, detalhe)
                             VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                          (ator_tipo, ator_id, ator_nome, acao, entidade, entidade_id,
                           json.dumps(_limpar(dados or {}), ensure_ascii=False, default=str),
                           origem, resultado, detalhe))
        except Exception:                      # auditoria nunca pode derrubar a ação auditada
            log.exception("falha ao registrar auditoria: %s %s", acao, entidade_id)

    def listar(self, *, dias: int = 30, ator: str | None = None, acao: str | None = None,
               entidade: str | None = None, entidade_id: str | None = None, busca: str | None = None,
               so_sensiveis: bool = False, limite: int = 300) -> list[dict]:
        desde = datetime.now(timezone.utc) - timedelta(days=dias)
        with _conn() as c:
            rows = c.execute(f"""
                SELECT {self.COLS} FROM auditoria
                WHERE em >= %(desde)s
                  AND (%(ator)s::text IS NULL OR ator_id = %(ator)s OR ator_tipo = %(ator)s)
                  AND (%(acao)s::text IS NULL OR acao = %(acao)s)
                  AND (%(entidade)s::text IS NULL OR entidade = %(entidade)s)
                  AND (%(entidade_id)s::text IS NULL OR entidade_id = %(entidade_id)s)
                  AND (NOT %(sensiveis)s::bool OR acao = ANY(%(lista_sensivel)s))
                  AND (%(busca)s::text IS NULL OR acao ILIKE %(busca)s OR entidade_id ILIKE %(busca)s
                       OR coalesce(ator_nome,'') ILIKE %(busca)s OR dados::text ILIKE %(busca)s)
                ORDER BY em DESC LIMIT %(limite)s""",
                {"desde": desde, "ator": ator, "acao": acao, "entidade": entidade, "entidade_id": entidade_id,
                 "sensiveis": so_sensiveis, "lista_sensivel": list(SENSIVEIS),
                 "busca": f"%{busca}%" if busca else None, "limite": limite}).fetchall()
        return [{**dict(r), "em": r["em"].isoformat()} for r in rows]

    def resumo(self, dias: int = 30) -> dict:
        desde = datetime.now(timezone.utc) - timedelta(days=dias)
        with _conn() as c:
            total = c.execute("SELECT count(*) AS n FROM auditoria WHERE em >= %s", (desde,)).fetchone()["n"]
            por_acao = c.execute("""SELECT acao, count(*) AS n FROM auditoria WHERE em >= %s
                                    GROUP BY acao ORDER BY n DESC LIMIT 12""", (desde,)).fetchall()
            por_ator = c.execute("""SELECT ator_tipo, coalesce(ator_nome, ator_id, '—') AS ator, count(*) AS n
                                    FROM auditoria WHERE em >= %s GROUP BY 1,2 ORDER BY n DESC LIMIT 8""", (desde,)).fetchall()
            erros = c.execute("SELECT count(*) AS n FROM auditoria WHERE em >= %s AND resultado <> 'ok'", (desde,)).fetchone()["n"]
            sensiveis = c.execute("SELECT count(*) AS n FROM auditoria WHERE em >= %s AND acao = ANY(%s)",
                                  (desde, list(SENSIVEIS))).fetchone()["n"]
            acoes = [r["acao"] for r in c.execute("SELECT DISTINCT acao FROM auditoria ORDER BY acao").fetchall()]
            entidades = [r["entidade"] for r in c.execute("SELECT DISTINCT entidade FROM auditoria ORDER BY entidade").fetchall()]
        return {"periodo_dias": dias, "total": total, "erros": erros, "sensiveis": sensiveis,
                "por_acao": [dict(r) for r in por_acao], "por_ator": [dict(r) for r in por_ator],
                "acoes_conhecidas": acoes, "entidades_conhecidas": entidades}


def auditar(**kw) -> None:
    """Atalho para quem só quer registrar e seguir a vida."""
    AuditoriaRepository().registrar(**kw)
