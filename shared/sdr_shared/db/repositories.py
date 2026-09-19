"""Repositórios — único lugar com SQL. Serviços nunca escrevem SQL diretamente."""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import ClassVar
import numpy as np
from pgvector.psycopg import register_vector
from ..models import Lead, Imovel, Visita, CartaoQualificacao, Estagio, Temperatura, AnaliseLead

log = logging.getLogger("sdr.db")
from .connection import get_pool


def _conn():
    return get_pool().connection()


DURACAO_PADRAO_MIN = 60


def _colide(inicio: datetime, ocupacao: list[tuple[datetime, datetime]],
            duracao_min: int = DURACAO_PADRAO_MIN) -> bool:
    fim = inicio + timedelta(minutes=duracao_min)
    return any(ini < fim and inicio < f for ini, f in ocupacao)


class LeadRepository:
    COLS = ("id, cliente_id, nome, telefone, email, estagio, temperatura, score, cartao, corretor_id, resumo, analise, "
            "analisado_em, analise_solicitada_em, followups_enviados, criado_em, ultima_mensagem_em, "
            "aceita_reativacao, reativado_em, encerrado_em, sucessora_id")

    @staticmethod
    def _row(r: dict) -> Lead:
        r = dict(r)
        r["cartao"] = CartaoQualificacao.model_validate(r["cartao"] or {})
        r["analise"] = AnaliseLead.model_validate(r["analise"]) if r.get("analise") else None
        return Lead(**r)

    def get(self, lead_id: str) -> Lead | None:
        with _conn() as c:
            r = c.execute(f"SELECT {self.COLS} FROM leads WHERE id = %s", (lead_id,)).fetchone()
        return self._row(r) if r else None

    def get_por_canal(self, canal: str, identificador: str) -> Lead | None:
        with _conn() as c:
            r = c.execute(f"""SELECT {self.COLS} FROM leads l JOIN canais ca ON ca.lead_id = l.id
                              WHERE ca.canal = %s AND ca.identificador = %s""", (canal, identificador)).fetchone()
        return self._row(r) if r else None

    def upsert(self, lead: Lead) -> Lead:
        with _conn() as c:
            c.execute("""
                INSERT INTO leads (id, cliente_id, nome, telefone, email, estagio, temperatura, score, cartao, corretor_id, resumo, analise, analisado_em, analise_solicitada_em, followups_enviados, ultima_mensagem_em, aceita_reativacao, reativado_em)
                VALUES (%(id)s, %(cliente_id)s, %(nome)s, %(telefone)s, %(email)s, %(estagio)s, %(temperatura)s, %(score)s, %(cartao)s, %(corretor_id)s, %(resumo)s, %(analise)s, %(analisado_em)s, %(analise_solicitada_em)s, %(followups_enviados)s, %(ultima_mensagem_em)s, %(aceita_reativacao)s, %(reativado_em)s)
                ON CONFLICT (id) DO UPDATE SET
                  cliente_id = COALESCE(EXCLUDED.cliente_id, leads.cliente_id),
                  nome = COALESCE(EXCLUDED.nome, leads.nome), telefone = COALESCE(EXCLUDED.telefone, leads.telefone),
                  email = COALESCE(EXCLUDED.email, leads.email),
                  estagio = EXCLUDED.estagio, temperatura = EXCLUDED.temperatura, score = EXCLUDED.score,
                  cartao = EXCLUDED.cartao, corretor_id = EXCLUDED.corretor_id, resumo = EXCLUDED.resumo,
                  analise = COALESCE(EXCLUDED.analise, leads.analise), analisado_em = COALESCE(EXCLUDED.analisado_em, leads.analisado_em),
                  analise_solicitada_em = COALESCE(EXCLUDED.analise_solicitada_em, leads.analise_solicitada_em),
                  followups_enviados = EXCLUDED.followups_enviados,
                  ultima_mensagem_em = COALESCE(EXCLUDED.ultima_mensagem_em, leads.ultima_mensagem_em),
                  aceita_reativacao = EXCLUDED.aceita_reativacao,
                  -- COALESCE: o carimbo de reativação é escrito pelo worker, não pelo turno do
                  -- agente. Sem isso, salvar o lead numa conversa qualquer apagaria a cadência.
                  reativado_em = COALESCE(EXCLUDED.reativado_em, leads.reativado_em)
            """, {**lead.model_dump(exclude={"cartao", "criado_em", "analise", "encerrado_em", "sucessora_id"}), "cartao": json.dumps(lead.cartao.model_dump(mode="json")),
                  "analise": json.dumps(lead.analise.model_dump(mode="json")) if lead.analise else None})
        return self.get(lead.id)

    def listar(self, estagio: str | None = None, temperatura: str | None = None, limite: int = 200,
               corretor_id: str | None = None) -> list[Lead]:
        with _conn() as c:
            rows = c.execute(f"""SELECT {self.COLS} FROM leads
                                 WHERE encerrado_em IS NULL      -- a fila do corretor é de oportunidades abertas
                                   AND (%s::text IS NULL OR estagio = %s) AND (%s::text IS NULL OR temperatura = %s)
                                   AND (%s::text IS NULL OR corretor_id = %s)
                                 ORDER BY score DESC, ultima_mensagem_em DESC NULLS LAST LIMIT %s""",
                             (estagio, estagio, temperatura, temperatura, corretor_id, corretor_id, limite)).fetchall()
        return [self._row(r) for r in rows]

    def encerrar(self, lead_id: str, sucessora_id: str | None = None) -> None:
        """Fecha a oportunidade sem apagar nada: o histórico do cliente continua inteiro."""
        with _conn() as c:
            c.execute("UPDATE leads SET encerrado_em = now(), sucessora_id = %s WHERE id = %s",
                      (sucessora_id, lead_id))

    def marcar_analise_pedida(self, lead_id: str) -> None:
        """Registra o pedido de briefing; se `analisado_em` não alcançar isto, o worker não respondeu."""
        with _conn() as c:
            c.execute("UPDATE leads SET analise_solicitada_em = now() WHERE id = %s", (lead_id,))

    def atribuir_corretor(self, lead_id: str, corretor_id: str | None) -> None:
        """Vincula o lead (e suas visitas futuras) a um corretor do cadastro."""
        with _conn() as c:
            c.execute("UPDATE leads SET corretor_id = %s WHERE id = %s", (corretor_id, lead_id))
            c.execute("UPDATE visitas SET corretor_id = %s WHERE lead_id = %s AND inicio >= now()", (corretor_id, lead_id))

    def funil(self) -> dict[str, int]:
        with _conn() as c:
            rows = c.execute("SELECT estagio, count(*) AS n FROM leads GROUP BY estagio").fetchall()
        base = {e.value: 0 for e in Estagio}
        base.update({r["estagio"]: r["n"] for r in rows})
        return base

    def por_temperatura(self) -> dict[str, int]:
        with _conn() as c:
            rows = c.execute("SELECT temperatura, count(*) AS n FROM leads GROUP BY temperatura").fetchall()
        base = {t.value: 0 for t in Temperatura}
        base.update({r["temperatura"]: r["n"] for r in rows})
        return base

    def marcar_atividade(self, lead_id: str) -> None:
        with _conn() as c:
            c.execute("UPDATE leads SET ultima_mensagem_em = now() WHERE id = %s", (lead_id,))

    def definir_aceita_reativacao(self, lead_id: str, aceita: bool) -> bool:
        """Interruptor do aviso de imóvel novo. UPDATE direto (e não upsert do agregado) porque
        quem mexe nisto é o corretor no painel, num turno em que o resto do lead não mudou —
        reescrever o lead inteiro aqui sobrescreveria o que o agente estivesse gravando em paralelo."""
        with _conn() as c:
            r = c.execute("UPDATE leads SET aceita_reativacao = %s WHERE id = %s RETURNING aceita_reativacao",
                          (aceita, lead_id)).fetchone()
        return r is not None

    def marcar_reativacao(self, lead_id: str) -> None:
        """Carimba o aviso enviado — é este carimbo que faz valer a cadência de DIAS_ENTRE_REATIVACOES."""
        with _conn() as c:
            c.execute("UPDATE leads SET reativado_em = now() WHERE id = %s", (lead_id,))


class CanalRepository:
    def vincular(self, lead_id: str, canal: str, identificador: str) -> None:
        with _conn() as c:
            c.execute("""INSERT INTO canais (lead_id, canal, identificador) VALUES (%s, %s, %s)
                         ON CONFLICT (canal, identificador) DO UPDATE SET lead_id = EXCLUDED.lead_id""",
                      (lead_id, canal, identificador))

    def canais_do_lead(self, lead_id: str) -> list[dict]:
        with _conn() as c:
            return [dict(r) for r in c.execute("SELECT canal, identificador FROM canais WHERE lead_id = %s", (lead_id,)).fetchall()]

    def migrar(self, de_lead_id: str, para_lead_id: str) -> None:
        """Lead anônimo da web virou lead de WhatsApp: move canais e mensagens, apaga o antigo."""
        with _conn() as c:
            c.execute("UPDATE canais SET lead_id = %s WHERE lead_id = %s", (para_lead_id, de_lead_id))
            c.execute("UPDATE mensagens SET lead_id = %s WHERE lead_id = %s", (para_lead_id, de_lead_id))
            c.execute("DELETE FROM followups_agendados WHERE lead_id = %s", (de_lead_id,))
            c.execute("DELETE FROM leads WHERE id = %s", (de_lead_id,))


class MensagemRepository:
    def registrar(self, lead_id: str, canal: str, direcao: str, conteudo: str, meta: dict | None = None) -> int:
        """Devolve o id da linha inserida.

        Ele é o identificador natural da mensagem, e é o que a ponte com o CRM usa como
        `external_event_id`. Derivar esse identificador do TEXTO, como eu fazia antes, junta duas
        mensagens iguais de clientes diferentes numa só — descoberto rodando a suíte duas vezes.
        """
        with _conn() as c:
            linha = c.execute("INSERT INTO mensagens (lead_id, canal, direcao, conteudo, meta) "
                              "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                              (lead_id, canal, direcao, conteudo, json.dumps(meta or {}))).fetchone()
        return linha["id"]

    def historico(self, lead_id: str, limite: int = 100) -> list[dict]:
        with _conn() as c:
            rows = c.execute("""SELECT id, canal, direcao, conteudo, meta, em FROM mensagens
                                WHERE lead_id = %s ORDER BY em DESC LIMIT %s""", (lead_id, limite)).fetchall()
        return [dict(r) for r in reversed(rows)]

    def recentes(self, limite: int = 50) -> list[dict]:
        with _conn() as c:
            rows = c.execute("""SELECT m.id, m.lead_id, l.nome, m.canal, m.direcao, m.conteudo, m.em
                                FROM mensagens m JOIN leads l ON l.id = m.lead_id ORDER BY m.em DESC LIMIT %s""", (limite,)).fetchall()
        return [dict(r) for r in rows]


class InteresseRepository:
    """Quem se interessou por qual imóvel (tabela `interesses`).

    Regra de transição, numa frase: **`sugerido` nunca sobrescreve nada**. Mostrar de novo um imóvel
    que a pessoa já descartou não apaga o descarte, e reapresentar um que ela já pediu para visitar
    não rebaixa a visita. Qualquer outra situação é um ato explícito e vale mais que a anterior.
    """
    SITUACOES = ("sugerido", "interessado", "descartado", "visita_marcada")
    ORIGENS = ("agente", "site", "corretor")

    def registrar(self, lead_id: str, imovel_id: str, situacao: str = "sugerido",
                  origem: str = "agente", motivo: str | None = None) -> None:
        if situacao not in self.SITUACOES:
            raise ValueError(f"situação inválida: {situacao}")
        with _conn() as c:
            c.execute("""
                INSERT INTO interesses (lead_id, imovel_id, situacao, origem, motivo)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (lead_id, imovel_id) DO UPDATE
                   SET situacao = CASE WHEN EXCLUDED.situacao = 'sugerido'
                                       THEN interesses.situacao ELSE EXCLUDED.situacao END,
                       motivo = COALESCE(EXCLUDED.motivo, interesses.motivo),
                       atualizado_em = now()
            """, (lead_id, imovel_id, situacao, origem, motivo))

    def registrar_varios(self, lead_id: str, imoveis: list[tuple[str, str | None]],
                         situacao: str = "sugerido", origem: str = "agente") -> None:
        for imovel_id, motivo in imoveis:
            self.registrar(lead_id, imovel_id, situacao, origem, motivo)

    def do_lead(self, lead_id: str) -> list[dict]:
        """Interesses do lead com o essencial do imóvel — é o que o corretor abre na ficha."""
        with _conn() as c:
            rows = c.execute("""
                SELECT i.imovel_id, i.situacao, i.origem, i.motivo, i.criado_em, i.atualizado_em,
                       m.tipo, m.bairro, m.operacao, m.preco, m.quartos, m.area_m2
                  FROM interesses i JOIN imoveis m ON m.id = i.imovel_id
                 WHERE i.lead_id = %s ORDER BY i.atualizado_em DESC""", (lead_id,)).fetchall()
        return [dict(r) for r in rows]

    def interessados(self, imovel_id: str) -> list[dict]:
        """Quem está de olho neste imóvel. Descartados ficam de fora: a pergunta do corretor é
        "com quem eu falo sobre este imóvel", não "quem já disse não"."""
        with _conn() as c:
            rows = c.execute("""
                SELECT i.lead_id, i.situacao, i.origem, i.atualizado_em,
                       l.nome, l.telefone, l.estagio, l.temperatura, l.score, l.corretor_id
                  FROM interesses i JOIN leads l ON l.id = i.lead_id
                 WHERE i.imovel_id = %s AND i.situacao <> 'descartado'
                   AND l.encerrado_em IS NULL
                 ORDER BY l.score DESC, i.atualizado_em DESC""", (imovel_id,)).fetchall()
        return [dict(r) for r in rows]

    def por_situacao(self, lead_id: str) -> dict[str, set[str]]:
        """{situacao: {imovel_id}} — o consultor usa para não repetir nem reoferecer o descartado."""
        with _conn() as c:
            rows = c.execute("SELECT imovel_id, situacao FROM interesses WHERE lead_id = %s", (lead_id,)).fetchall()
        saida: dict[str, set[str]] = {}
        for r in rows:
            saida.setdefault(r["situacao"], set()).add(r["imovel_id"])
        return saida


class ImovelRepository:
    COLS = "id, tipo, operacao, cidade, regiao, bairro, quartos, suites, vagas, area_m2, preco, condominio, descricao, fotos, destaque_investimento"

    @staticmethod
    def _row(r: dict) -> Imovel:
        return Imovel(**{k: v for k, v in dict(r).items() if k != "score"})

    def get(self, imovel_id: str) -> Imovel | None:
        with _conn() as c:
            r = c.execute(f"SELECT {self.COLS} FROM imoveis WHERE id = %s", (imovel_id,)).fetchone()
        return self._row(r) if r else None

    def upsert(self, im: Imovel, embedding: list[float] | None = None) -> bool:
        """Devolve True quando o imóvel ENTROU agora (não quando foi atualizado).

        A distinção existe por causa da reativação: reprocessar o catálogo é rotina, e sem separar
        inserção de atualização um `make seed` avisaria a base inteira de novo sobre imóveis que já
        estavam lá. `xmax = 0` é o teste canônico do Postgres para "esta linha veio do INSERT".
        """
        with _conn() as c:
            register_vector(c)
            r = c.execute(f"""
                INSERT INTO imoveis ({self.COLS}, embedding)
                VALUES (%(id)s, %(tipo)s, %(operacao)s, %(cidade)s, %(regiao)s, %(bairro)s, %(quartos)s, %(suites)s, %(vagas)s,
                        %(area_m2)s, %(preco)s, %(condominio)s, %(descricao)s, %(fotos)s, %(destaque_investimento)s, %(embedding)s)
                ON CONFLICT (id) DO UPDATE SET
                  tipo = EXCLUDED.tipo, operacao = EXCLUDED.operacao, cidade = EXCLUDED.cidade, regiao = EXCLUDED.regiao,
                  bairro = EXCLUDED.bairro, quartos = EXCLUDED.quartos, suites = EXCLUDED.suites, vagas = EXCLUDED.vagas,
                  area_m2 = EXCLUDED.area_m2, preco = EXCLUDED.preco, condominio = EXCLUDED.condominio, descricao = EXCLUDED.descricao,
                  -- fotos enviadas pelo painel (/fotos/...) sobrevivem a um novo `make seed`
                  fotos = CASE WHEN EXISTS (SELECT 1 FROM jsonb_array_elements_text(imoveis.fotos) f WHERE f LIKE '/fotos/%%')
                               THEN imoveis.fotos ELSE EXCLUDED.fotos END,
                  destaque_investimento = EXCLUDED.destaque_investimento,
                  embedding = COALESCE(EXCLUDED.embedding, imoveis.embedding)
                RETURNING (xmax = 0) AS novo
            """, {**im.model_dump(exclude={"fotos"}), "fotos": json.dumps(im.fotos), "embedding": np.array(embedding, dtype=np.float32) if embedding is not None else None}).fetchone()
        return bool(r and r["novo"])

    def listar_publico(self, operacao: str | None = None, regiao: str | None = None, preco_max: float | None = None,
                       quartos: int | None = None, limite: int = 60) -> list[Imovel]:
        with _conn() as c:
            rows = c.execute(f"""SELECT {self.COLS} FROM imoveis
                                 WHERE (%(op)s::text IS NULL OR operacao = %(op)s) AND (%(reg)s::text IS NULL OR regiao = %(reg)s)
                                   AND (%(pm)s::numeric IS NULL OR preco <= %(pm)s) AND (%(q)s::int IS NULL OR quartos >= %(q)s)
                                 ORDER BY destaque_investimento DESC, preco LIMIT %(lim)s""",
                             {"op": operacao, "reg": regiao, "pm": preco_max, "q": quartos, "lim": limite}).fetchall()
        return [self._row(r) for r in rows]

    # Filtros da busca pública do site. Todos opcionais e todos guardados por NULL, para caber numa
    # consulta só — a alternativa (montar SQL por concatenação) é como se escreve um SQL injection.
    _FILTROS_PUBLICOS = """
          (%(operacao)s::text IS NULL OR operacao = %(operacao)s)
      AND (%(regiao)s::text   IS NULL OR regiao = %(regiao)s)
      AND (%(bairro)s::text   IS NULL OR unaccent(lower(bairro)) = unaccent(lower(%(bairro)s)))
      AND (%(tipo)s::text     IS NULL OR tipo = %(tipo)s)
      AND (%(preco_max)s::numeric IS NULL OR preco <= %(preco_max)s)
      AND (%(preco_min)s::numeric IS NULL OR preco >= %(preco_min)s)
      AND (%(quartos)s::int   IS NULL OR quartos >= %(quartos)s)
      AND (%(suites)s::int    IS NULL OR suites >= %(suites)s)
      AND (%(vagas)s::int     IS NULL OR vagas >= %(vagas)s)
      AND (%(area_min)s::numeric IS NULL OR area_m2 >= %(area_min)s)
      AND (%(texto)s::text IS NULL OR unaccent(lower(bairro || ' ' || tipo || ' ' || descricao)) LIKE '%%' || unaccent(lower(%(texto)s)) || '%%')
    """
    ORDENACOES: ClassVar[dict[str, str]] = {"relevancia": "destaque_investimento DESC, preco",
                  "preco_asc": "preco", "preco_desc": "preco DESC",
                  "area_desc": "area_m2 DESC", "recentes": "id DESC"}

    def buscar_publico(self, filtros: dict, ordenar: str = "relevancia",
                       limite: int = 24, offset: int = 0) -> dict:
        """Busca do catálogo do site: página de resultados + total + contagem por bairro.

        Devolve o total junto porque a página precisa dele para dizer "38 imóveis encontrados" e para
        saber se ainda há próxima página — sem isso o site é obrigado a baixar o catálogo inteiro só
        para contar, que é exatamente o que ele fazia antes.

        A contagem por bairro ignora o filtro de bairro de propósito: ela alimenta a lista de bairros
        da tela, e uma lista que some quando você escolhe um item não serve para trocar de escolha.
        """
        p = {k: filtros.get(k) for k in ("operacao", "regiao", "bairro", "tipo", "preco_max",
                                         "preco_min", "quartos", "suites", "vagas", "area_min", "texto")}
        ordem = self.ORDENACOES.get(ordenar, self.ORDENACOES["relevancia"])
        with _conn() as c:
            itens = c.execute(f"""SELECT {self.COLS} FROM imoveis WHERE {self._FILTROS_PUBLICOS}
                                  ORDER BY {ordem}, id LIMIT %(lim)s OFFSET %(off)s""",
                              {**p, "lim": limite, "off": offset}).fetchall()
            total = c.execute(f"SELECT count(*) AS n FROM imoveis WHERE {self._FILTROS_PUBLICOS}", p).fetchone()["n"]
            bairros = c.execute(f"""SELECT bairro, count(*) AS n FROM imoveis
                                     WHERE {self._FILTROS_PUBLICOS} GROUP BY bairro ORDER BY bairro""",
                                {**p, "bairro": None}).fetchall()
        return {"itens": [self._row(r) for r in itens], "total": int(total),
                "bairros": [{"bairro": b["bairro"], "n": int(b["n"])} for b in bairros]}

    def buscar_hibrido(self, embedding: list[float], filtros: dict, limite: int = 5) -> list[Imovel]:
        """Fallback pgvector (ADR-0001): filtro SQL + ordenação por similaridade cosseno.
        Preço tolera +15% para não descartar bons imóveis por pouco.
        `bairros` restringe ao que o cliente pediu — sem isso a busca devolve a zona inteira e o
        agente conclui, errado, que não há imóvel no bairro pedido."""
        with _conn() as c:
            register_vector(c)
            rows = c.execute(f"""
                SELECT {self.COLS}, 1 - (embedding <=> %(emb)s) AS score FROM imoveis
                WHERE embedding IS NOT NULL
                  AND (%(operacao)s::text IS NULL OR operacao = %(operacao)s)
                  AND (%(regiao)s::text IS NULL OR regiao = %(regiao)s)
                  AND (%(bairros)s::text[] IS NULL OR bairro = ANY(%(bairros)s))
                  AND (%(preco_max)s::numeric IS NULL OR preco <= %(preco_max)s * 1.15)
                  AND (%(quartos)s::int IS NULL OR quartos >= %(quartos)s)
                ORDER BY embedding <=> %(emb)s LIMIT %(limite)s
            """, {"emb": np.array(embedding, dtype=np.float32), "limite": limite, "operacao": filtros.get("operacao"), "regiao": filtros.get("regiao"),
                  "bairros": filtros.get("bairros") or None,
                  "preco_max": filtros.get("preco_max"), "quartos": filtros.get("quartos")}).fetchall()
        return [self._row(r) for r in rows]

    def atualizar_fotos(self, imovel_id: str, fotos: list[str]) -> None:
        with _conn() as c:
            c.execute("UPDATE imoveis SET fotos = %s WHERE id = %s", (json.dumps(fotos), imovel_id))

    def apagar_fora_de(self, ids: list[str]) -> int:
        """Remove do índice os imóveis que a fonte não lista mais. Devolve quantos saíram.

        Recusa lista vazia, e a recusa é o ponto: uma leitura que falhou devolve vazio igual a um
        acervo que esvaziou, e a diferença entre as duas é o catálogo inteiro. O mesmo defeito já
        apareceu na ingestão de documentos — esvaziar tem de ser ato explícito, nunca efeito
        colateral de uma fonte que não respondeu.

        Sem isso, um imóvel vendido continua sendo oferecido pelo agente: é o pior tipo de dado
        velho, o que ninguém sabe que ficou.
        """
        if not ids:
            raise ValueError("apagar_fora_de recusa lista vazia: seria esvaziar o catálogo")
        with get_pool().connection() as conn:
            return conn.execute("DELETE FROM imoveis WHERE id <> ALL(%s)", (list(ids),)).rowcount

    def contar(self) -> int:
        with _conn() as c:
            return c.execute("SELECT count(*) AS n FROM imoveis").fetchone()["n"]

    def contar_com_embedding(self) -> int:
        with _conn() as c:
            return c.execute("SELECT count(*) AS n FROM imoveis WHERE embedding IS NOT NULL").fetchone()["n"]


class VisitaRepository:
    def ocupacao_do_corretor(self, corretor_id: str | None, de: datetime, ate: datetime) -> list[tuple[datetime, datetime]]:
        """O que já está marcado com este corretor no nosso banco, no intervalo pedido."""
        if not corretor_id:
            return []
        with _conn() as c:
            rows = c.execute("""SELECT inicio, duracao_min FROM visitas
                                WHERE corretor_id = %s AND status = 'confirmada'
                                  AND inicio >= %s AND inicio < %s""", (corretor_id, de, ate)).fetchall()
        return [(r["inicio"], r["inicio"] + timedelta(minutes=r["duracao_min"] or 60)) for r in rows]

    def slot_livre(self, inicio: datetime, corretor_id: str | None = None) -> bool:
        """Revalidação no momento de gravar: entre a oferta e o clique, alguém pode ter pegado o horário."""
        with _conn() as c:
            r = c.execute("""SELECT count(*) AS n FROM visitas
                             WHERE status = 'confirmada' AND inicio = %s
                               AND (%s::text IS NULL OR corretor_id = %s OR corretor_id IS NULL)""",
                          (inicio, corretor_id, corretor_id)).fetchone()
        return int(r["n"]) == 0

    def marcar_evento_externo(self, visita_id: str, evento_id: str | None) -> None:
        with _conn() as c:
            c.execute("UPDATE visitas SET evento_externo_id = %s WHERE id = %s", (evento_id, visita_id))

    def horarios_disponiveis(self, dias: int = 5, corretor_id: str | None = None) -> list[datetime]:
        """Slots 10h/14h/16h (Brasília) nos próximos dias úteis, menos o que já está comprometido.

        Com um corretor definido, desconta também a agenda real dele (Google, quando conectada);
        sem corretor, desconta só as visitas do sistema — é a grade da equipe.
        """
        with _conn() as c:
            ocupados = {r["inicio"] for r in c.execute(
                "SELECT inicio FROM visitas WHERE status = 'confirmada' AND inicio > now()").fetchall()}

        slots, d = [], datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        while len(slots) < dias * 3:
            d += timedelta(days=1)
            if d.weekday() >= 5:
                continue
            for h in (10, 14, 16):
                s = d.replace(hour=h + 3)           # UTC-3 → UTC
                if s not in ocupados:
                    slots.append(s)
        if not corretor_id or not slots:
            return slots
        return [s for s in slots if not _colide(s, self._agenda_externa(corretor_id, slots[0], slots[-1]))]

    def _agenda_externa(self, corretor_id: str, de: datetime, ate: datetime) -> list[tuple[datetime, datetime]]:
        """Nunca deixa a indisponibilidade do calendário externo derrubar a oferta: na falha, oferece tudo."""
        try:
            from ..ports import get_calendario
            return get_calendario().ocupado(corretor_id, de, ate + timedelta(hours=2))
        except Exception:
            log.exception("não consegui ler a agenda do corretor %s — ofertando a grade cheia", corretor_id)
            return []

    def agendar(self, v: Visita) -> Visita:
        with _conn() as c:
            c.execute("""INSERT INTO visitas (id, lead_id, imovel_id, tipo, inicio, corretor_id, status)
                         VALUES (%(id)s, %(lead_id)s, %(imovel_id)s, %(tipo)s, %(inicio)s, %(corretor_id)s, %(status)s)
                         ON CONFLICT (id) DO NOTHING""", v.model_dump())
        return v

    def listar(self, futuras: bool = True) -> list[dict]:
        with _conn() as c:
            rows = c.execute("""SELECT v.id, v.lead_id, l.nome, v.imovel_id, i.bairro, v.tipo, v.inicio, v.corretor_id, co.nome AS corretor_nome, v.status
                                FROM visitas v JOIN leads l ON l.id = v.lead_id LEFT JOIN imoveis i ON i.id = v.imovel_id
                                LEFT JOIN corretores co ON co.id = v.corretor_id
                                WHERE (NOT %s::bool) OR v.inicio > now() ORDER BY v.inicio""", (futuras,)).fetchall()
        return [dict(r) for r in rows]


class EventoNavegacaoRepository:
    def registrar(self, session_id: str, tipo: str, dados: dict) -> None:
        with _conn() as c:
            c.execute("INSERT INTO eventos_navegacao (session_id, tipo, dados) VALUES (%s, %s, %s)", (session_id, tipo, json.dumps(dados)))

    def imoveis_vistos(self, session_id: str) -> list[str]:
        with _conn() as c:
            rows = c.execute("""SELECT DISTINCT dados->>'imovel_id' AS im FROM eventos_navegacao
                                WHERE session_id = %s AND tipo = 'viewed_imovel' AND dados ? 'imovel_id'""", (session_id,)).fetchall()
        return [r["im"] for r in rows]


class DocumentoRepository:
    """Trechos da base de conhecimento institucional (tabela `documentos`).

    A busca devolve o `score` de similaridade junto — e não filtra por ele aqui de propósito. Quem
    decide o piso é o domínio (`conhecimento.PISO_SIMILARIDADE`), porque é lá que está escrito o
    porquê; o repositório não deve ter opinião sobre o que é "perto o suficiente".
    """

    COLS = "id, arquivo, assunto, titulo, trecho, ordem"

    def upsert(self, t, embedding: list[float] | None = None) -> None:
        with _conn() as c:
            register_vector(c)
            c.execute("""
                INSERT INTO documentos (id, arquivo, assunto, titulo, trecho, ordem, embedding, atualizado_em)
                VALUES (%(id)s, %(arquivo)s, %(assunto)s, %(titulo)s, %(trecho)s, %(ordem)s, %(embedding)s, now())
                ON CONFLICT (id) DO UPDATE SET
                    arquivo = EXCLUDED.arquivo, assunto = EXCLUDED.assunto, titulo = EXCLUDED.titulo,
                    trecho = EXCLUDED.trecho, ordem = EXCLUDED.ordem,
                    embedding = COALESCE(EXCLUDED.embedding, documentos.embedding),
                    atualizado_em = now()
            """, {"id": t.id, "arquivo": t.arquivo, "assunto": t.assunto, "titulo": t.titulo,
                  "trecho": t.texto, "ordem": t.ordem,
                  "embedding": np.array(embedding, dtype=np.float32) if embedding else None})

    def buscar(self, embedding: list[float], limite: int = 3, assunto: str | None = None) -> list:
        from ..conhecimento import Trecho
        with _conn() as c:
            register_vector(c)
            rows = c.execute(f"""
                SELECT {self.COLS}, 1 - (embedding <=> %(emb)s) AS score FROM documentos
                WHERE embedding IS NOT NULL
                  AND (%(assunto)s::text IS NULL OR assunto = %(assunto)s)
                ORDER BY embedding <=> %(emb)s LIMIT %(limite)s
            """, {"emb": np.array(embedding, dtype=np.float32), "limite": limite,
                  "assunto": assunto}).fetchall()
        return [Trecho(id=r["id"], arquivo=r["arquivo"], assunto=r["assunto"], titulo=r["titulo"],
                       texto=r["trecho"], ordem=r["ordem"], score=float(r["score"])) for r in rows]

    def apagar_do_arquivo(self, arquivo: str) -> int:
        """Reingerir um documento editado precisa remover os trechos que sumiram dele.

        Sem isto, apagar uma seção do FAQ deixa o trecho antigo no banco para sempre — e o agente
        continua respondendo com uma política que a imobiliária já revogou. É o pior tipo de dado
        velho: o que ninguém sabe que ainda está lá."""
        with _conn() as c:
            return c.execute("DELETE FROM documentos WHERE arquivo = %s", (arquivo,)).rowcount

    def contar(self) -> int:
        with _conn() as c:
            return c.execute("SELECT count(*) AS n FROM documentos").fetchone()["n"]
