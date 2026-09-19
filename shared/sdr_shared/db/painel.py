"""Repositórios do painel administrativo: métricas agregadas, corretores e configurações."""
import json
from datetime import datetime, timedelta, timezone

from ..models import Corretor
from .connection import get_pool

ESTAGIOS_ATIVOS = ("novo", "qualificando", "qualificado", "agendado", "handoff")


def _conn():
    return get_pool().connection()


class MetricasRepository:
    """KPIs do período (com o período anterior para variação), série diária, pipeline em R$ e distribuições."""

    def resumo(self, dias: int = 7) -> dict:
        agora = datetime.now(timezone.utc)
        ini, ini_ant = agora - timedelta(days=dias), agora - timedelta(days=2 * dias)
        with _conn() as c:
            def periodo(a: datetime, b: datetime) -> dict:
                r = c.execute("""
                    SELECT
                      (SELECT count(*) FROM leads WHERE criado_em >= %(a)s AND criado_em < %(b)s)                                   AS leads,
                      (SELECT count(*) FROM leads WHERE criado_em >= %(a)s AND criado_em < %(b)s
                          AND estagio IN ('qualificado','agendado','handoff'))                                                  AS qualificados,
                      (SELECT count(*) FROM visitas WHERE criada_em >= %(a)s AND criada_em < %(b)s AND status = 'confirmada')     AS visitas,
                      (SELECT count(*) FROM leads WHERE criado_em >= %(a)s AND criado_em < %(b)s AND estagio = 'handoff')         AS handoffs,
                      (SELECT count(*) FROM mensagens WHERE em >= %(a)s AND em < %(b)s AND direcao = 'in')                        AS msgs_in,
                      (SELECT count(*) FROM mensagens WHERE em >= %(a)s AND em < %(b)s AND direcao = 'out')                       AS msgs_out,
                      (SELECT avg(EXTRACT(EPOCH FROM (o.primeira - i.primeira)))
                         FROM (SELECT lead_id, min(em) AS primeira FROM mensagens WHERE direcao = 'in' GROUP BY lead_id) i
                         JOIN (SELECT lead_id, min(em) AS primeira FROM mensagens WHERE direcao = 'out' GROUP BY lead_id) o USING (lead_id)
                        WHERE i.primeira >= %(a)s AND i.primeira < %(b)s AND o.primeira >= i.primeira)                          AS resposta_seg
                """, {"a": a, "b": b}).fetchone()
                r = dict(r)
                r["resposta_seg"] = float(r["resposta_seg"]) if r["resposta_seg"] is not None else None
                return r

            atual, anterior = periodo(ini, agora), periodo(ini_ant, ini)

            pipeline = c.execute("""
                SELECT estagio, count(*) AS n,
                       coalesce(sum(coalesce((cartao->>'preco_max')::numeric, (cartao->>'ticket')::numeric)), 0) AS valor
                FROM leads GROUP BY estagio""").fetchall()
            por_estagio = {r["estagio"]: {"n": r["n"], "valor": float(r["valor"])} for r in pipeline}
            ticket = c.execute("""
                SELECT avg(v) AS medio FROM (
                  SELECT coalesce((cartao->>'preco_max')::numeric, (cartao->>'ticket')::numeric) AS v FROM leads
                  WHERE estagio = ANY(%(ativos)s)) t WHERE v IS NOT NULL""", {"ativos": list(ESTAGIOS_ATIVOS)}).fetchone()["medio"]
            valor_visitas = c.execute("""
                SELECT coalesce(sum(i.preco), 0) AS v FROM visitas vi JOIN imoveis i ON i.id = vi.imovel_id
                WHERE vi.status = 'confirmada' AND vi.inicio >= now()""").fetchone()["v"]

            serie = c.execute("""
                WITH dias AS (SELECT generate_series((now() - make_interval(days => %(d)s - 1))::date, now()::date, '1 day')::date AS dia)
                SELECT d.dia,
                       (SELECT count(*) FROM leads    WHERE criado_em::date = d.dia)                     AS leads,
                       (SELECT count(*) FROM visitas  WHERE criada_em::date = d.dia AND status='confirmada') AS visitas,
                       (SELECT count(*) FROM mensagens WHERE em::date = d.dia AND direcao = 'in')       AS mensagens
                FROM dias d ORDER BY d.dia""", {"d": dias}).fetchall()

            por_canal = c.execute("SELECT canal, count(DISTINCT lead_id) AS n FROM canais GROUP BY canal").fetchall()
            por_regiao = c.execute("""SELECT coalesce(cartao->>'regiao', 'indefinida') AS regiao, count(*) AS n
                                      FROM leads GROUP BY 1 ORDER BY n DESC""").fetchall()
            por_intencao = c.execute("""SELECT coalesce(cartao->>'intencao', 'indefinida') AS intencao, count(*) AS n
                                        FROM leads GROUP BY 1 ORDER BY n DESC""").fetchall()
            temperaturas = c.execute("SELECT temperatura, count(*) AS n FROM leads GROUP BY temperatura").fetchall()
            totais = c.execute("""SELECT count(*) AS leads, (SELECT count(*) FROM imoveis) AS imoveis,
                                         (SELECT count(*) FROM visitas WHERE status='confirmada' AND inicio >= now()) AS visitas_futuras,
                                         (SELECT count(*) FROM corretores WHERE ativo) AS corretores FROM leads""").fetchone()

        return {
            "periodo_dias": dias, "gerado_em": agora.isoformat(),
            "kpis": {k: {"atual": atual[k], "anterior": anterior[k]} for k in atual},
            "pipeline": {"por_estagio": por_estagio, "ticket_medio": float(ticket) if ticket is not None else None,
                         "valor_visitas": float(valor_visitas),
                         "total_ativo": sum(v["valor"] for e, v in por_estagio.items() if e in ESTAGIOS_ATIVOS)},
            "serie": [{"dia": r["dia"].isoformat(), "leads": r["leads"], "visitas": r["visitas"], "mensagens": r["mensagens"]} for r in serie],
            "por_canal": {r["canal"]: r["n"] for r in por_canal},
            "por_regiao": {r["regiao"]: r["n"] for r in por_regiao},
            "por_intencao": {r["intencao"]: r["n"] for r in por_intencao},
            "temperaturas": {r["temperatura"]: r["n"] for r in temperaturas},
            "totais": dict(totais),
        }


class CorretorRepository:
    COLS = "id, nome, email, telefone, regioes, ativo, criado_em, foto, crm_user_id"

    def listar(self, somente_ativos: bool = False) -> list[Corretor]:
        with _conn() as c:
            rows = c.execute(f"SELECT {self.COLS} FROM corretores WHERE (NOT %s::bool) OR ativo ORDER BY nome", (somente_ativos,)).fetchall()
        return [Corretor(**dict(r)) for r in rows]

    def get(self, corretor_id: str) -> Corretor | None:
        with _conn() as c:
            r = c.execute(f"SELECT {self.COLS} FROM corretores WHERE id = %s", (corretor_id,)).fetchone()
        return Corretor(**dict(r)) if r else None

    def upsert(self, co: Corretor) -> Corretor:
        with _conn() as c:
            c.execute("""INSERT INTO corretores (id, nome, email, telefone, regioes, ativo, foto, crm_user_id)
                         VALUES (%(id)s, %(nome)s, %(email)s, %(telefone)s, %(regioes)s, %(ativo)s, %(foto)s, %(crm_user_id)s)
                         ON CONFLICT (id) DO UPDATE SET nome = EXCLUDED.nome, email = EXCLUDED.email, telefone = EXCLUDED.telefone,
                           regioes = EXCLUDED.regioes, ativo = EXCLUDED.ativo, foto = EXCLUDED.foto,
                           crm_user_id = EXCLUDED.crm_user_id""",
                      {**co.model_dump(exclude={"criado_em", "regioes"}), "regioes": json.dumps(co.regioes)})
        return self.get(co.id)

    def carteira(self, corretor_id: str) -> dict:
        """O que fica pendurado no corretor: leads abertos e visitas futuras.

        É o que a tela precisa saber ANTES de desligar alguém — desligar sem olhar a carteira é
        como o sistema criava lead fantasma."""
        with _conn() as c:
            leads = c.execute("""SELECT count(*) AS n FROM leads
                                  WHERE corretor_id = %s AND encerrado_em IS NULL""", (corretor_id,)).fetchone()["n"]
            visitas = c.execute("""SELECT count(*) AS n FROM visitas
                                    WHERE corretor_id = %s AND inicio >= now()""", (corretor_id,)).fetchone()["n"]
        return {"leads": int(leads), "visitas": int(visitas)}

    def desativar(self, corretor_id: str, destino: str | None) -> dict:
        """Desliga o corretor e move a carteira. `destino=None` devolve à fila da equipe.

        Desativar em vez de apagar preserva o histórico: quem atendeu qual lead, quem conduziu qual
        visita, o rastro de auditoria. Um corretor apagado levava tudo isso junto.

        Tudo numa transação só: metade da carteira movida é pior que nenhuma, porque ninguém sabe
        qual metade. Devolve o que foi movido, para a resposta da API poder dizer ao usuário.
        """
        with _conn() as c:
            leads = c.execute("""UPDATE leads SET corretor_id = %s
                                  WHERE corretor_id = %s AND encerrado_em IS NULL
                                  RETURNING id""", (destino, corretor_id)).fetchall()
            visitas = c.execute("""UPDATE visitas SET corretor_id = %s
                                    WHERE corretor_id = %s AND inicio >= now()""", (destino, corretor_id)).rowcount
            # Avisos não lidos acompanham a carteira; os lidos ficam com quem os leu (é histórico).
            c.execute("""UPDATE notificacoes SET corretor_id = %s
                          WHERE corretor_id = %s AND lida_em IS NULL""", (destino, corretor_id))
            c.execute("UPDATE corretores SET ativo = false WHERE id = %s", (corretor_id,))
        return {"leads": [r["id"] for r in leads], "visitas": int(visitas)}

    def remover(self, corretor_id: str) -> bool:
        """Remoção física. Só para cadastro criado por engano: a API recusa quando há carteira, e o
        histórico de quem já atendeu alguém deve ser desativado, não apagado."""
        with _conn() as c:
            return c.execute("DELETE FROM corretores WHERE id = %s", (corretor_id,)).rowcount > 0

    def credencial_calendario(self, corretor_id: str) -> str | None:
        with _conn() as c:
            r = c.execute("SELECT calendario_refresh_token FROM corretores WHERE id = %s", (corretor_id,)).fetchone()
        return (r or {}).get("calendario_refresh_token")

    def salvar_credencial_calendario(self, corretor_id: str, refresh_token: str | None) -> None:
        """None desconecta. O token nunca sai daqui — nem para a API, nem para o painel."""
        with _conn() as c:
            c.execute("""UPDATE corretores SET calendario_refresh_token = %s,
                                calendario_conectado_em = CASE WHEN %s::text IS NULL THEN NULL ELSE now() END
                         WHERE id = %s""", (refresh_token, refresh_token, corretor_id))

    def escolher(self, regiao: str | None) -> Corretor | None:
        """Roteamento: corretor ATIVO que atende a região (ou atende todas), com menor carga
        (leads em handoff + visitas futuras). Empate → ordem alfabética. Nenhum → None."""
        ativos = self.listar(somente_ativos=True)
        if not ativos:
            return None
        aptos = [c for c in ativos if not c.regioes or (regiao and regiao in c.regioes)] or \
                [c for c in ativos if not c.regioes] or ativos
        carga = self.carga()
        return min(aptos, key=lambda c: (carga.get(c.id, {}).get("leads_handoff", 0) + carga.get(c.id, {}).get("visitas", 0), c.nome))

    def nomes(self) -> dict[str, str]:
        with _conn() as c:
            return {r["id"]: r["nome"] for r in c.execute("SELECT id, nome FROM corretores").fetchall()}

    def carga(self) -> dict[str, dict]:
        """Leads em handoff e visitas futuras por corretor (para a tela de corretores)."""
        with _conn() as c:
            leads = c.execute("SELECT corretor_id, count(*) AS n FROM leads WHERE corretor_id IS NOT NULL AND estagio = 'handoff' GROUP BY 1").fetchall()
            visitas = c.execute("SELECT corretor_id, count(*) AS n FROM visitas WHERE corretor_id IS NOT NULL AND inicio >= now() GROUP BY 1").fetchall()
        out: dict[str, dict] = {}
        for r in leads:
            out.setdefault(r["corretor_id"], {})["leads_handoff"] = r["n"]
        for r in visitas:
            out.setdefault(r["corretor_id"], {})["visitas"] = r["n"]
        return out


class ConfigRepository:
    def todas(self) -> dict:
        with _conn() as c:
            return {r["chave"]: r["valor"] for r in c.execute("SELECT chave, valor FROM configuracoes").fetchall()}

    def salvar(self, chave: str, valor: dict) -> None:
        with _conn() as c:
            c.execute("""INSERT INTO configuracoes (chave, valor, atualizado_em) VALUES (%s, %s, now())
                         ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor, atualizado_em = now()""", (chave, json.dumps(valor)))


# ---------------------------------------------------------------- reativação
#
# Fase 4 do ADR-0013: medir o que o aviso de imóvel novo produz. A leitura é feita da AUDITORIA e
# não de uma tabela de campanha nova — `lead.reativado`, `visita.agendada` e `lead.optout_reativacao`
# já registram tudo que o funil precisa, com carimbo de tempo e o imóvel em `dados`. Criar tabela
# própria seria manter em dois lugares o mesmo fato.
#
# O que se quer saber, em ordem: o aviso interrompeu alguém à toa? (taxa de saída), ele fez a pessoa
# voltar a falar? (taxa de resposta), e virou visita? Sem a taxa de saída ao lado das outras duas, o
# número vira só "quantas mensagens mandamos".
JANELA_RESPOSTA_H = 48      # depois disso, uma resposta é conversa nova, não reação ao aviso


def resumo_reativacao(dias: int = 30, janela_h: int = JANELA_RESPOSTA_H) -> dict:
    p = {"d": dias, "h": janela_h}
    with _conn() as c:
        funil = c.execute("""
            WITH avisos AS (
              SELECT entidade_id AS lead_id, em, dados->>'imovel_id' AS imovel_id
                FROM auditoria
               WHERE acao = 'lead.reativado' AND em >= now() - make_interval(days => %(d)s))
            SELECT count(*)                          AS avisos,
                   count(DISTINCT lead_id)           AS leads,
                   count(DISTINCT imovel_id)         AS imoveis,
                   count(*) FILTER (WHERE EXISTS (
                     SELECT 1 FROM mensagens m
                      WHERE m.lead_id = a.lead_id AND m.direcao = 'in'
                        AND m.em > a.em AND m.em <= a.em + make_interval(hours => %(h)s))) AS responderam,
                   count(*) FILTER (WHERE EXISTS (
                     SELECT 1 FROM auditoria v
                      WHERE v.acao = 'visita.agendada' AND v.em > a.em
                        AND v.dados->>'lead_id' = a.lead_id)) AS visitas
              FROM avisos a""", p).fetchone()

        saidas = c.execute("""
            SELECT count(*) AS n FROM auditoria
             WHERE em >= now() - make_interval(days => %(d)s)
               AND (acao = 'lead.optout_reativacao'
                    OR (acao = 'lead.preferencia_reativacao' AND dados->>'aceita_reativacao' = 'false'))""",
                           p).fetchone()

        # Quanto a régua descarta: sai do próprio worker (`reativacao.anunciada`). É o número que diz
        # se ela está apertada demais — muita gente avaliada e ninguém avisado.
        selecao = c.execute("""
            SELECT coalesce(sum((dados->>'avaliados')::int), 0)  AS avaliados,
                   coalesce(sum((dados->>'avisados')::int), 0)   AS avisados,
                   coalesce(sum((dados->>'sem_canal')::int), 0)  AS sem_canal,
                   count(*)                                      AS anuncios
              FROM auditoria
             WHERE acao = 'reativacao.anunciada' AND em >= now() - make_interval(days => %(d)s)""",
                            p).fetchone()

        ultimos = c.execute("""
            WITH avisos AS (
              SELECT entidade_id AS lead_id, em, dados->>'imovel_id' AS imovel_id,
                     dados->'motivos' AS motivos
                FROM auditoria
               WHERE acao = 'lead.reativado' AND em >= now() - make_interval(days => %(d)s)
               ORDER BY em DESC LIMIT 20)
            SELECT a.lead_id, a.em, a.imovel_id, a.motivos, l.nome, l.temperatura,
                   i.bairro, i.tipo, i.preco,
                   EXISTS (SELECT 1 FROM mensagens m
                            WHERE m.lead_id = a.lead_id AND m.direcao = 'in'
                              AND m.em > a.em AND m.em <= a.em + make_interval(hours => %(h)s)) AS respondeu,
                   EXISTS (SELECT 1 FROM auditoria v
                            WHERE v.acao = 'visita.agendada' AND v.em > a.em
                              AND v.dados->>'lead_id' = a.lead_id) AS visitou
              FROM avisos a
              LEFT JOIN leads l   ON l.id = a.lead_id
              LEFT JOIN imoveis i ON i.id = a.imovel_id
             ORDER BY a.em DESC""", p).fetchall()

    avisos = int(funil["avisos"])
    return {
        "dias": dias, "janela_resposta_h": janela_h,
        "avisos": avisos, "leads": int(funil["leads"]), "imoveis": int(funil["imoveis"]),
        "responderam": int(funil["responderam"]), "visitas": int(funil["visitas"]),
        "saidas": int(saidas["n"]),
        # Percentuais calculados aqui, e não no front: é uma divisão por zero esperando acontecer,
        # e três telas diferentes fariam a conta de três jeitos.
        "taxa_resposta": round(100 * funil["responderam"] / avisos, 1) if avisos else None,
        "taxa_visita": round(100 * funil["visitas"] / avisos, 1) if avisos else None,
        "taxa_saida": round(100 * saidas["n"] / avisos, 1) if avisos else None,
        "selecao": {k: int(selecao[k]) for k in ("avaliados", "avisados", "sem_canal", "anuncios")},
        "ultimos": [{"lead_id": r["lead_id"], "nome": r["nome"], "temperatura": r["temperatura"],
                     "em": r["em"].isoformat(), "imovel_id": r["imovel_id"], "bairro": r["bairro"],
                     "tipo": r["tipo"], "preco": float(r["preco"]) if r["preco"] is not None else None,
                     "motivos": r["motivos"] or [], "respondeu": bool(r["respondeu"]),
                     "visitou": bool(r["visitou"])}
                    for r in ultimos],
    }
