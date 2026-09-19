"""Avisos para o corretor.

O agente diz ao cliente que um corretor vai continuar o atendimento. Quem cumpre essa promessa é
uma pessoa — e ela precisa ficar sabendo. Antes, o corretor só descobria abrindo o painel na hora
certa; agora o fato fica registrado e espera por ele.

Persistido em vez de só empurrado por WebSocket de propósito: o corretor que estava almoçando
precisa ver o que aconteceu enquanto esteve fora.
"""
import json
import logging

from .connection import get_pool

log = logging.getLogger("sdr.notificacoes")
COLS = "id, corretor_id, tipo, titulo, detalhe, lead_id, dados, criada_em, lida_em"


def _conn():
    return get_pool().connection()


class NotificacaoRepository:
    def criar(self, *, tipo: str, titulo: str, corretor_id: str | None = None, detalhe: str | None = None,
              lead_id: str | None = None, dados: dict | None = None, chave: str | None = None) -> None:
        """`chave` torna o aviso idempotente: o mesmo fato reprocessado não vira dois avisos."""
        dados = {**(dados or {}), "chave": chave or ""}
        try:
            with _conn() as c:
                c.execute("""INSERT INTO notificacoes (corretor_id, tipo, titulo, detalhe, lead_id, dados)
                              VALUES (%s, %s, %s, %s, %s, %s)
                              ON CONFLICT (tipo, lead_id, (dados->>'chave')) DO NOTHING""",
                          (corretor_id, tipo, titulo[:200], (detalhe or None), lead_id, json.dumps(dados)))
        except Exception:
            # avisar é importante, mas nunca ao ponto de derrubar o atendimento que gerou o aviso
            log.exception("falha ao criar notificação %s do lead %s", tipo, lead_id)

    def listar(self, corretor_id: str | None = None, apenas_nao_lidas: bool = False, limite: int = 50) -> list[dict]:
        """Sem corretor_id, devolve tudo — é assim que o painel de dev (um login só) enxerga a equipe."""
        with _conn() as c:
            rows = c.execute(f"""
                SELECT {COLS}, (SELECT nome FROM leads l WHERE l.id = notificacoes.lead_id) AS lead_nome
                FROM notificacoes
                WHERE (%(cor)s::text IS NULL OR corretor_id = %(cor)s OR corretor_id IS NULL)
                  AND (NOT %(nao_lidas)s::bool OR lida_em IS NULL)
                ORDER BY criada_em DESC LIMIT %(lim)s""",
                {"cor": corretor_id, "nao_lidas": apenas_nao_lidas, "lim": limite}).fetchall()
        return [{**dict(r), "criada_em": r["criada_em"].isoformat(),
                 "lida_em": r["lida_em"].isoformat() if r["lida_em"] else None} for r in rows]

    def nao_lidas(self, corretor_id: str | None = None) -> int:
        with _conn() as c:
            r = c.execute("""SELECT count(*) AS n FROM notificacoes WHERE lida_em IS NULL
                             AND (%(cor)s::text IS NULL OR corretor_id = %(cor)s OR corretor_id IS NULL)""",
                          {"cor": corretor_id}).fetchone()
        return int(r["n"])

    def marcar_lida(self, notificacao_id: int, corretor_id: str | None = None) -> None:
        """`corretor_id=None` = login único do perfil local (vê e marca tudo, ver routers/notificacoes.py).
        Marca só o que é do próprio corretor (ou sem dono) — o id é sequencial e sem este
        filtro dava para marcar como lido o aviso de outra pessoa só iterando números."""
        with _conn() as c:
            c.execute("""UPDATE notificacoes SET lida_em = now()
                         WHERE id = %(id)s AND lida_em IS NULL
                           AND (%(cor)s::text IS NULL OR corretor_id = %(cor)s OR corretor_id IS NULL)""",
                      {"id": notificacao_id, "cor": corretor_id})

    def marcar_todas(self, corretor_id: str | None = None) -> int:
        with _conn() as c:
            r = c.execute("""UPDATE notificacoes SET lida_em = now()
                             WHERE lida_em IS NULL
                               AND (%(cor)s::text IS NULL OR corretor_id = %(cor)s OR corretor_id IS NULL)
                             RETURNING id""", {"cor": corretor_id}).fetchall()
        return len(r)


def notificar(**kw) -> None:
    NotificacaoRepository().criar(**kw)
